"""JSON-lines desktop bridge. No listening socket, no Tk dependency."""
import json
import sys
import threading
import time
import traceback
from pathlib import Path
from .storage import DATA, RESOURCES, MODELS, ROOT, read_json, write_json, model_path, portable_path
from .model import LocalModel
from .voice import Voice, devices
from .assistant import messages, map_answer, reference_answer, location, quick_prompts, GUIDES, PROMPT_DEFAULTS
from .maps import OfflineMap, coordinate, download_area, route_to_place, format_distance, set_units, with_distance_text
from .atlas import TileArchive, MapCatalog
from .location_search import LocationIndex
from .us_routing import USRouter
from .map_setup import prepare_us, basemap_issue
from . import planner
from .local_board import LocalBoard
from .assets import prepare_qwen, prepare_voice, VOICE_NAME
from .setup import Setup
from .library import import_text, import_note, retrieve, reference_catalog, reference_document, reference_pdf, search_references, library_catalog, document, delete_document, rename_document
from .calculations import supply_duration

output_lock = threading.Lock()
OPERATION_LABELS = {'download_model':'Preparing model and voice', 'download_voice':'Preparing offline voice',
                    'setup_run':'Preparing JARVISS',
                    'download_map':'Downloading walking area', 'download_us_maps':'Preparing US offline maps', 'start_model':'Loading local model', 'stop_model':'Stopping model',
                    'chat':'Thinking', 'route':'Calculating walking directions', 'clear':'Clearing conversation'}


def emit(value):
    with output_lock:
        print(json.dumps(value, ensure_ascii=False), flush=True)


def chosen_file(args, kind):
    path = args.get('path')
    if not isinstance(path, str) or not path.strip(): raise ValueError(f'Choose a {kind} file.')
    path = Path(path)
    if not path.is_file(): raise ValueError(f'The {kind} file was not found: {path.name}')
    return path


class Service:
    def __init__(self):
        self.profile = read_json(DATA / 'profile.json', {})
        self.settings = {**PROMPT_DEFAULTS, **read_json(DATA / 'settings.json', {})}
        self.history = read_json(DATA / 'conversation.json', [])
        pack = read_json(DATA / 'area.json', None)
        self.area = OfflineMap(pack) if pack else None
        self.areas = [OfflineMap(read_json(p, None)) for p in sorted((DATA / 'maps').glob('*.json'))]
        if self.area and not any(a.pack == self.area.pack for a in self.areas): self.areas.append(self.area)
        self.example_active = False
        self.archive_error = None
        self.archive = None
        path = model_path(self.settings.get('map_archive', 'local-maps/us-z15.pmtiles'))
        if path.exists():
            try: self.archive = TileArchive(path); self.archive_error = basemap_issue(path)
            except Exception as error: self.archive_error = str(error)
        self.places_by_id = {}
        self.location_index = LocationIndex(self.archive) if self.archive else None
        self.us_router = USRouter(ROOT / "local-maps" / "routing-us")
        self.route = None
        self.position_revision = self.map_revision = 0
        self.model = LocalModel()
        self.ready = False
        self.lock = threading.Lock()
        self.setup_lock = threading.Lock()
        # Position saves, map swaps and route commits run on separate request threads.
        self.profile_lock = threading.Lock()
        self.settings_lock = threading.Lock()
        self.operation_lock = threading.Lock()
        self.operation = None
        self.board = LocalBoard()
        self.voice = Voice(self.heard, lambda text: emit({'event':'voice', 'data':text}),
                           lambda text: emit({'event':'error', 'data':text}),
                           lambda kind, value: emit({'event':kind, 'data':value}))
        self.voice.configure(self.settings)
        set_units(self.settings.get('units') if self.settings.get('units') in ('imperial','metric') else 'imperial')
        self.setup = Setup(self)

    def state(self):
        return {'profile':self.profile, 'history':self.history[-100:], 'settings':self.settings,
                'ready':self.ready, 'voiceReady':all(p.is_file() for p in (MODELS / VOICE_NAME / 'am/final.mdl', MODELS / 'kokoro/kokoro-v1.0.onnx', MODELS / 'kokoro/voices-v1.0.bin')),
                'operation':dict(self.operation) if self.operation else None,
                'modelAvailable':bool(self.settings.get('model') and model_path(self.settings['model']).is_file()),
                'voiceEnabled':self.voice.enabled.is_set(),
                'voicePreview':self.voice.previewing,
                'setup':self.setup.snapshot(),
                'setupRunning':self.setup_lock.locked(),
                'map':self.area.pack if self.area else None,
                'basemap':dict(self.archive.pack, path=str(self.archive.path), enabled=not self.example_active) if self.archive else None,
                'mapError':self.archive_error, 'route':self.route,
                'usRouting':self.us_router.status(),
                'routingPacks':[{'label':a.pack.get('label', 'Prepared walking area'), 'bounds':a.pack['bounds'],
                    'center':a.pack['center'], 'downloaded_at':a.pack['downloaded_at'], 'roads':len(a.pack['roads']),
                    'places':len(a.pack['places'])} for a in self.areas],
                'promptDefaults':PROMPT_DEFAULTS,
                'documents':library_catalog(), 'guides':GUIDES, 'quick_prompts':quick_prompts(), 'references':reference_catalog(),
                'paths':{'data':str(DATA), 'logs':str(ROOT / 'service.log')},
                'planner':planner.state(), 'plannerSchemas':planner.SCHEMAS, 'board':self.board.state(),
                'recovery':(RESOURCES / 'collective-recovery.md').read_text(encoding='utf-8')}

    def catalog(self):
        if self.example_active: return self.area
        return MapCatalog(self.areas, self.archive, self.us_router, self.location_index) if self.areas or self.archive else None

    def progress(self, text):
        with self.operation_lock:
            if self.operation:
                self.operation = dict(self.operation, progress=text)
                emit({'event':'operation', 'data':self.operation})
        emit({'event':'progress', 'data':text})

    def revision(self):
        return (self.position_revision, self.map_revision)

    def stale(self, revision):
        # Directions computed for an old position or map must never be shown as current.
        if revision == self.revision(): return None
        return ('Your position' if revision[0] != self.position_revision else 'The map') + ' changed while directions were calculated. Request directions again.'

    def swap_map(self, **fields):
        with self.profile_lock:
            for name, value in fields.items(): setattr(self, name, value)
            self.route, self.places_by_id = None, {}
            self.map_revision += 1

    def setup_progress(self):
        # Map downloads can overlap chat. Never replace its operation or status.
        emit({'event':'setup', 'data':dict(self.setup.snapshot(), running=self.setup_lock.locked(), modelReady=self.ready, mapReady=bool(self.archive))})

    def save_area(self, area):
        import hashlib
        key = hashlib.sha256(json.dumps(area.pack['bounds']).encode()).hexdigest()[:16]
        write_json(DATA / 'maps' / (key + '.json'), area.pack)
        write_json(DATA / 'area.json', area.pack)
        self.areas = [a for a in self.areas if a.pack['bounds'] != area.pack['bounds']] + [area]
        self.swap_map(area=area, example_active=False)

    def heard(self, text):
        emit({'event':'heard', 'data':text})
        def work():
            try: self.command('chat', {'text':text, 'spoken':True})
            except Exception as error:
                emit({'event':'error', 'data':str(error)})
                # A refused request must not clear the flag the running typed chat owns.
                if not self.lock.locked(): self.voice.busy.clear()
        threading.Thread(target=work, daemon=True).start()

    def command(self, method, args):
        if method == 'state': return self.state()
        if method == 'reference': return reference_document(args.get('id'))
        if method == 'reference_pdf': return reference_pdf(args.get('id'))
        if method == 'reference_search': return search_references(args.get('query',''))
        if method == 'setup_plan': return self.setup.plan(args.get('model_id'))
        if method == 'setup_pause': self.setup.cancel.set(); return True
        if method == 'setup_skip': self.setup.save(skipped=True); return self.setup.snapshot()
        if method == 'document': return document(args.get('title'))
        if method == 'library_delete': return delete_document(args.get('title'))
        if method == 'library_rename': return rename_document(args.get('title'), args.get('new_title'))
        if method.startswith('planner_'): return planner.command(method,args)
        if method == 'board_start': return self.board.start()
        if method == 'board_stop': self.board.close(); return self.board.state()
        if method == 'board_state': return self.board.state()
        if method == 'board_send': return self.board.add(args.get('name',''),args.get('text',''))
        if method == 'location_parts':
            text=str(args.get('text',''))[:200]
            # Index progress must not overwrite a running download's operation state.
            return self.location_index.address_parts(text,lambda text: emit({'event':'progress', 'data':text})) if self.location_index else {'city':text,'street':''}
        if method == 'prompt_settings':
            updated = {}
            for key in ('system_prompt', 'voice_prompt'):
                value = args.get(key)
                if not isinstance(value, str) or not value.strip() or len(value) > 12000:
                    raise ValueError('Prompts must contain 1–12000 characters.')
                updated[key] = value.strip()
            for key, low, high in [('voice_max_sentences',1,20),('voice_max_tokens',32,2048),('text_max_tokens',32,4096)]:
                value = args.get(key)
                if type(value) is not int or not low <= value <= high: raise ValueError(f'{key} must be between {low} and {high}.')
                updated[key] = value
            if 'units' in args: updated['units'] = set_units(args['units'])
            with self.settings_lock: self.settings.update(updated); write_json(DATA / 'settings.json', self.settings)
            return self.settings
        if method == 'voice':
            if args.get('enabled') and not self.ready: raise RuntimeError('Wait for the model to finish loading before starting voice.')
            self.voice.start() if args.get('enabled') else self.voice.pause()
            return {'enabled':self.voice.enabled.is_set()}
        if method == 'audio_devices': return devices()
        if method == 'audio_settings':
            available = devices()
            updated = {}
            for key, direction in [('input_device','input'),('output_device','output')]:
                value = args.get(key)
                if value is None: updated[key] = None
                else:
                    try: wanted = int(value)
                    except (TypeError, ValueError): raise ValueError('Choose an audio device from the list.') from None
                    device = next((d for d in available if d['id'] == wanted and d[direction]), None)
                    if device is None: raise ValueError('Audio device disconnected. Choose another in Settings → Voice.')
                    updated[key] = {'name':device['name'],'host':device['host']}
            name = args.get('voice_name','bm_george')
            if name not in ('bm_george','bm_lewis','am_michael','af_heart','bf_emma'): raise ValueError('Unknown voice.')
            self.voice.pause()
            with self.settings_lock: self.settings.update(updated, voice_name=name)
            self.voice.configure(self.settings); write_json(DATA / 'settings.json', self.settings)
            return self.settings
        if method == 'test_speaker':
            self.voice.speak('This is my voice.', preview=True)
            return True
        if method == 'stop_speaker':
            # Stopping a preview must not end a voice session.
            (getattr(self.voice, 'stop_speaking', None) or self.voice.pause)()
            return True
        if method == 'save_profile':
            if any(not isinstance(args.get(k) or '', str) for k in ('situation','supplies','location_text')):
                raise ValueError('Situation, supplies and location must be text.')
            with self.profile_lock:
                profile = {**self.profile, **{k:(args.get(k) or '')[:2000] for k in ('situation','supplies','location_text')}}
                if profile['location_text'] != self.profile.get('location_text',''):
                    profile.update(lat='',lon='',position_name='')
                for key in ('lat','lon'):
                    if key in args: profile[key]=args[key]
                if profile.get('lat','') or profile.get('lon',''):
                    profile['lat'], profile['lon'] = coordinate(profile['lat'], profile['lon'])
                self.profile = profile
                self.position_revision += 1
                self.route = None
                write_json(DATA / 'profile.json', profile)
            return profile
        if method == 'set_map_position':
            lat, lon = coordinate(args.get('lat'), args.get('lon'))
            with self.profile_lock:
                self.profile = dict(self.profile, lat=lat, lon=lon, position_name=str(args.get('name') or self.profile.get('location_text') or 'Confirmed map position')[:200])
                self.position_revision += 1
                self.route = None
                write_json(DATA / 'profile.json', self.profile)
            return self.profile
        if method == 'search_locations':
            query = str(args.get('query', '')).strip()[:200]
            if len(query) < 2: return []
            if not self.catalog(): raise ValueError('The map is not ready. Open setup to download it or check progress.')
            if args.get('near') is not None:
                point = coordinate(*args['near'])
                catalog = self.catalog()
                if not catalog: return []
                # Exploration is independent of saved current coordinates.
                import re
                street_query=re.sub(r'^\d+[A-Za-z]?(?:[-/]\d+)?\s+', '', query)
                for short,long in [('st','street'),('rd','road'),('ave','avenue'),('blvd','boulevard'),('dr','drive'),('ln','lane'),('ct','court'),('hwy','highway')]:
                    street_query=re.sub(r'\b'+short+r'\.?$',long,street_query,flags=re.I)
                rows = catalog.nearest(point, street_query, 30)
                found = {}
                for place in rows:
                    key = (place['kind'], place['name']) if place['kind'] == 'road' else place['id']
                    found.setdefault(key, place)
                return with_distance_text(list(found.values())[:20])
            if self.location_index:
                return self.location_index.search(query, lambda text: emit({'event':'progress', 'data':text}))
            catalog = self.catalog()
            if not catalog: return []
            return with_distance_text(catalog.nearest(catalog.pack['center'], query, 20))
        if method == 'import_document': return import_text(chosen_file(args, 'document'))
        if method == 'import_note': return import_note(args.get('title',''),args.get('text',''))
        if method == 'nearest':
            catalog, point = self.catalog(), location(self.profile)
            if not catalog or not point: return []
            if not catalog.contains(point): raise ValueError('Your position is outside the downloaded map coverage.')
            rows = catalog.nearest(point, str(args.get('query',''))[:200], 30)
            # The map re-runs this after every operation; a Directions click may target an earlier list.
            listed = {p['id']: p for p in rows}
            self.places_by_id = dict(list({**{k:v for k,v in self.places_by_id.items() if k not in listed}, **listed}.items())[-300:])
            return with_distance_text(rows)
        if method == 'import_basemap':
            archive = TileArchive(chosen_file(args, 'map').resolve())
            index = LocationIndex(archive)
            with self.settings_lock: self.settings['map_archive'] = portable_path(archive.path)
            self.swap_map(archive=archive, archive_error=None, location_index=index, example_active=False)
            write_json(DATA / 'settings.json', self.settings)
            return self.state()
        if method == 'use_basemap':
            self.swap_map(example_active=False, area=self.areas[-1] if self.areas else None)
            return self.state()
        if method == 'import_map' or method == 'example_map':
            path = chosen_file(args, 'map') if method == 'import_map' else RESOURCES / 'example-map.json'
            if path.stat().st_size > 80*1024*1024: raise ValueError('Map is too large.')
            area = OfflineMap(read_json(path, None))
            if method == 'import_map': self.save_area(area)
            else: self.swap_map(area=area, example_active=True)
            return area.pack
        if self.setup_lock.locked() and method in ('setup_run','start_model','download_model','download_voice','download_us_maps'):
            raise RuntimeError('Setup is running. Open setup to check progress or pause it.')
        if not self.lock.acquire(blocking=False):
            operation = self.operation
            label = operation['label'] if operation else 'Another operation is running'
            raise RuntimeError(label + '. Wait for it to finish before starting another operation.')
        if self.setup_lock.locked() and method in ('setup_run','start_model','download_model','download_voice','download_us_maps'):
            self.lock.release()
            raise RuntimeError('Setup is running. Open setup to check progress or pause it.')
        foreground = True
        def release_foreground():
            nonlocal foreground
            try:
                self.voice.busy.clear()
                with self.operation_lock:
                    self.operation = None
                    emit({'event':'operation', 'data':None})
                emit({'event':'status','data':'Ready' if self.ready else 'Model not started'})
            finally:
                foreground = False
                self.lock.release()
        try:
            # Inside the try: a failed emit must still release the lock.
            with self.operation_lock:
                self.operation = {'method':method, 'label':OPERATION_LABELS.get(method, 'Working'), 'progress':''}
                emit({'event':'operation', 'data':self.operation})
            if method == 'setup_run':
                # Claim setup while holding the foreground lock, so a second
                # request cannot start changing model files between phases.
                if not self.setup_lock.acquire(blocking=False): raise RuntimeError('Setup is already running.')
                try:
                    return self.setup.run(args.get('model_id'), only_model=bool(args.get('only_model')), background=release_foreground)
                finally:
                    self.setup_lock.release()
                    self.setup_progress()
            if method == 'route':
                catalog = self.catalog()
                self.route = None
                if not catalog or not location(self.profile): raise ValueError('Confirm your position in Maps first.')
                if 'point' in args:
                    name = args.get('name')
                    name = ' '.join(name.split())[:200] if isinstance(name,str) else ''
                    place = {'point':coordinate(*args['point']), 'name':name or 'Selected map point', 'kind':'coordinates'}
                else:
                    place = self.places_by_id.get(args.get('id'))
                    if not place: raise ValueError('Search again and select the destination.')
                revision = self.revision()
                result = route_to_place(catalog, location(self.profile), place)
                with self.profile_lock:
                    if message := self.stale(revision): raise ValueError(message)
                    self.route = result
                return result
            if method == 'clear':
                self.history = []; write_json(DATA / 'conversation.json', []); return True
            if method == 'stop_model':
                self.voice.pause(); self.ready = False; self.model.stop()
                return True
            if method == 'start_model':
                layers = args.get('layers', self.settings.get('gpu_layers','auto'))
                if layers != 'auto':
                    try: layers = int(layers)
                    except (TypeError, ValueError): raise ValueError('GPU layers must be a whole number between 0 and 999, or automatic.') from None
                    if not 0 <= layers <= 999: raise ValueError('GPU layers must be between 0 and 999, or automatic.')
                path = args.get('path') or self.settings.get('model','')
                if not path:
                    raise ValueError('Choose a GGUF model or finish preparing the model before starting it.')
                resolved = model_path(path)
                if not resolved.is_file() or resolved.suffix.lower() != '.gguf':
                    raise ValueError('The selected GGUF model is missing or incomplete. Finish its download or choose an existing GGUF file.')
                self.voice.busy.set()
                self.ready = False
                emit({'event':'status','data':'Loading local model'})
                self.model.stop(); self.model.start(model_path(path), layers, context=self.settings.get('model_context',8192))
                with self.settings_lock: self.settings.update(model=path, gpu_layers=layers)
                write_json(DATA / 'settings.json', self.settings)
                self.ready = True
                emit({'event':'status','data':'Ready'})
                return self.settings
            if method == 'chat':
                text = str(args.get('text','')).strip()[:4000]
                if not text: raise ValueError('Enter a question.')
                catalog = self.catalog()
                revision = self.revision()
                direct = map_answer(text, self.profile, catalog, self.route)
                is_map_answer = direct is not None
                if not direct:
                    calculation = supply_duration(text)
                    if calculation: direct = (calculation, None)
                if not direct and not self.ready: direct = reference_answer(text)
                if is_map_answer and (message := self.stale(revision)): direct = (message, None)
                if not direct and not self.ready: raise RuntimeError('Start your model in Settings first.')
                self.voice.busy.set(); emit({'event':'status','data':'Thinking'})
                # Hands-free budgets apply to what was heard; a typed question keeps text limits even while the mic is on.
                spoken = bool(args.get('spoken'))
                preferences = {**PROMPT_DEFAULTS, **self.settings}
                documents = retrieve(text) if not direct else []
                references = [{k:d[k] for k in ('id','section','title','heading')} for d in documents if d.get('id')]
                payload = messages(self.profile, self.history, text, catalog, self.route, preferences, spoken, documents) if not direct else None
                delivered = []
                def speak_sentence(sentence):
                    delivered.append(sentence)
                    if self.voice.enabled.is_set(): self.voice.speak(sentence)
                def commit(answer, truncated=False):
                    self.history += [{'role':'user','content':text},{'role':'assistant','content':answer,'references':references, **({'truncated':True} if truncated else {})}]
                    self.history = self.history[-100:]
                    write_json(DATA / 'conversation.json', self.history)
                    emit({'event':'answer','data':{'text':answer,'question':text,'route':self.route,'references':references, **({'truncated':True} if truncated else {})}})
                try:
                    answer, route = direct or (self.model.chat(payload, on_sentence=speak_sentence if self.voice.enabled.is_set() else None,
                        max_tokens=preferences['voice_max_tokens' if spoken else 'text_max_tokens'],
                        max_sentences=preferences['voice_max_sentences'] if spoken else None), None)
                except Exception:
                    # What the user already heard must exist in the transcript.
                    if delivered: commit(' '.join(delivered), truncated=True)
                    raise
                if route:
                    # Only a new successful directions answer replaces the route in use.
                    with self.profile_lock:
                        if not self.stale(revision): self.route = route
                if direct and self.voice.enabled.is_set():
                    # Keep full map records on screen; speak a short orientation only.
                    summary = (f"The recorded destination is {route['destination']}; the mapped walk is {format_distance(route['distance_m']).split(' (')[0]}. " + (route['steps'][0]['instruction'] if route.get('steps') else '') + ' Conditions and access are unverified; full directions are in chat.'
                               if route else ' '.join(answer.splitlines()[:1]))
                    import re
                    self.voice.speak(' '.join(re.split(r'(?<=[.!?])\s+', summary)[:preferences['voice_max_sentences']]))
                commit(answer)
                return answer
            if method in ('download_model','download_voice'):
                fn = prepare_qwen if method == 'download_model' else prepare_voice
                fn(self.progress)
                with self.settings_lock: self.settings.update(read_json(DATA / 'settings.json', {}))
                return True
            if method == 'download_us_maps':
                self.setup.cancel.clear()
                path = prepare_us(self.progress, cancel=self.setup.cancel)
                self.us_router = USRouter(ROOT / "local-maps" / "routing-us")
                return self.command('import_basemap', {'path':str(path)})
            if method == 'download_map':
                point = location(self.profile)
                if not point: raise ValueError('Save your coordinates first.')
                pack = download_area(*point, args.get('radius',2), self.progress)
                self.save_area(OfflineMap(pack))
                return pack
            raise ValueError('Unknown operation.')
        finally:
            if foreground: release_foreground()

    def close(self):
        self.setup.cancel.set()
        # Let a running map download stop its extractor before this process ends.
        deadline = time.monotonic() + 6
        for lock in (self.lock, self.setup_lock): lock.acquire(timeout=max(0, deadline - time.monotonic()))
        stop_router = getattr(self.us_router, 'close', None)
        if stop_router: stop_router()
        self.board.close(); self.voice.close(); self.model.close()


def main():
    sys.stdin.reconfigure(encoding='utf-8'); sys.stdout.reconfigure(encoding='utf-8')
    service = Service()
    def request(item):
        try: emit({'id':item['id'], 'result':service.command(item['method'], item.get('args',{}))})
        except (ValueError, RuntimeError, OSError) as error: emit({'id':item['id'], 'error':str(error) or type(error).__name__})
        except Exception as error:
            # A KeyError or TypeError is a defect, not advice for the user.
            traceback.print_exc()
            emit({'id':item['id'], 'error':f'Unexpected {type(error).__name__} in {item["method"]}. Details are in service.log.'})
    try:
        for line in sys.stdin:
            try: item = json.loads(line)
            except ValueError: continue
            if item['method'] == 'shutdown': break
            threading.Thread(target=request, args=(item,), daemon=True).start()
    finally: service.close()
