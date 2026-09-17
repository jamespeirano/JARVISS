"""JSON-lines desktop bridge. No listening socket, no Tk dependency."""
import json
import sys
import threading
from pathlib import Path
from .storage import DATA, RESOURCES, MODELS, ROOT, read_json, write_json, model_path, portable_path
from .model import LocalModel
from .voice import Voice, devices
from .assistant import messages, map_answer, reference_answer, location, GUIDES, PROMPT_DEFAULTS
from .maps import OfflineMap, coordinate, download_area, route_to_place
from .atlas import TileArchive, MapCatalog
from .location_search import LocationIndex
from .us_routing import USRouter
from .map_setup import prepare_us
from . import planner
from .local_board import LocalBoard
from .assets import prepare_qwen, prepare_voice, VOICE_NAME
from .setup import Setup
from .library import import_text, import_note, retrieve, reference_catalog, reference_document, reference_pdf, search_references
from .calculations import supply_duration

output_lock = threading.Lock()
OPERATION_LABELS = {'download_model':'Preparing model and voice', 'download_voice':'Preparing offline voice',
                    'setup_run':'Preparing Jarvis',
                    'download_map':'Downloading walking area', 'download_us_maps':'Preparing US offline maps', 'start_model':'Loading local model',
                    'chat':'Thinking', 'route':'Calculating walking directions', 'clear':'Clearing conversation'}


def emit(value):
    with output_lock:
        print(json.dumps(value, ensure_ascii=False), flush=True)


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
            try: self.archive = TileArchive(path)
            except Exception as error: self.archive_error = str(error)
        self.places_by_id = {}
        self.location_index = LocationIndex(self.archive) if self.archive else None
        self.us_router = USRouter(ROOT / "local-maps" / "routing-us")
        self.route = None
        self.position_revision = 0
        self.model = LocalModel()
        self.ready = False
        self.lock = threading.Lock()
        self.setup_lock = threading.Lock()
        self.operation = None
        self.board = LocalBoard()
        self.voice = Voice(self.heard, lambda text: emit({'event':'voice', 'data':text}),
                           lambda text: emit({'event':'error', 'data':text}),
                           lambda kind, value: emit({'event':kind, 'data':value}))
        self.voice.configure(self.settings)
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
                'documents':read_json(DATA / 'library.json', []), 'guides':GUIDES, 'references':reference_catalog(),
                'planner':planner.state(), 'plannerSchemas':planner.SCHEMAS, 'board':self.board.state(),
                'recovery':(RESOURCES / 'collective-recovery.md').read_text(encoding='utf-8')}

    def catalog(self):
        if self.example_active: return self.area
        return MapCatalog(self.areas, self.archive, self.us_router, self.location_index) if self.areas or self.archive else None

    def progress(self, text):
        if self.operation:
            self.operation = dict(self.operation, progress=text)
            emit({'event':'operation', 'data':self.operation})
        emit({'event':'progress', 'data':text})

    def setup_progress(self):
        # Map downloads can overlap chat. Never replace its operation or status.
        emit({'event':'setup', 'data':dict(self.setup.snapshot(), running=self.setup_lock.locked(), modelReady=self.ready, mapReady=bool(self.archive))})

    def save_area(self, area):
        import hashlib
        key = hashlib.sha256(json.dumps(area.pack['bounds']).encode()).hexdigest()[:16]
        write_json(DATA / 'maps' / (key + '.json'), area.pack)
        write_json(DATA / 'area.json', area.pack)
        self.areas = [a for a in self.areas if a.pack['bounds'] != area.pack['bounds']] + [area]
        self.area, self.route, self.example_active = area, None, False

    def heard(self, text):
        emit({'event':'heard', 'data':text})
        def work():
            try: self.command('chat', {'text':text})
            except Exception as error: emit({'event':'error', 'data':str(error)})
            finally: self.voice.busy.clear()
        threading.Thread(target=work, daemon=True).start()

    def command(self, method, args):
        if method == 'state': return self.state()
        if method == 'reference': return reference_document(args.get('id'))
        if method == 'reference_pdf': return reference_pdf(args.get('id'))
        if method == 'reference_search': return search_references(args.get('query',''))
        if method == 'setup_plan': return self.setup.plan(args.get('model_id'))
        if method == 'setup_pause': self.setup.cancel.set(); return True
        if method.startswith('planner_'): return planner.command(method,args)
        if method == 'board_start': return self.board.start()
        if method == 'board_stop': self.board.close(); return self.board.state()
        if method == 'board_state': return self.board.state()
        if method == 'board_send': return self.board.add(args.get('name',''),args.get('text',''))
        if method == 'location_parts':
            text=str(args.get('text',''))[:200]
            return self.location_index.address_parts(text,self.progress) if self.location_index else {'city':text,'street':''}
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
            self.settings.update(updated); write_json(DATA / 'settings.json', self.settings)
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
                    device = next((d for d in available if d['id'] == int(value) and d[direction]), None)
                    if device is None: raise ValueError('Audio device disconnected. Choose another in Settings → Voice.')
                    updated[key] = {'name':device['name'],'host':device['host']}
            name = args.get('voice_name','bm_george')
            if name not in ('bm_george','bm_lewis','am_michael','af_heart','bf_emma'): raise ValueError('Unknown voice.')
            self.voice.pause()
            self.settings.update(updated, voice_name=name)
            self.voice.configure(self.settings); write_json(DATA / 'settings.json', self.settings)
            return self.settings
        if method == 'test_speaker':
            self.voice.speak('This is my voice.', preview=True)
            return True
        if method == 'stop_speaker':
            self.voice.pause()
            return True
        if method == 'save_profile':
            profile = {**self.profile, **{k:str(args.get(k, ''))[:2000] for k in ('situation','supplies','location_text')}}
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
            lat, lon = coordinate(args['lat'], args['lon'])
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
                return list(found.values())[:20]
            if self.location_index:
                return self.location_index.search(query, lambda text: emit({'event':'progress', 'data':text}))
            catalog = self.catalog()
            if not catalog: return []
            return catalog.nearest(catalog.pack['center'], query, 20)
        if method == 'import_document': return import_text(args['path'])
        if method == 'import_note': return import_note(args.get('title',''),args.get('text',''))
        if method == 'nearest':
            catalog, point = self.catalog(), location(self.profile)
            if not catalog or not point: return []
            if not catalog.contains(point): raise ValueError('Your position is outside the downloaded map coverage.')
            rows = catalog.nearest(point, str(args.get('query',''))[:200], 30)
            self.places_by_id = {p['id']: p for p in rows}
            return rows
        if method == 'import_basemap':
            archive = TileArchive(Path(args['path']).resolve())
            self.settings['map_archive'] = portable_path(archive.path)
            write_json(DATA / 'settings.json', self.settings)
            self.archive, self.archive_error = archive, None
            self.location_index = LocationIndex(archive)
            self.example_active, self.route = False, None
            return self.state()
        if method == 'use_basemap':
            self.example_active, self.route = False, None
            self.area = self.areas[-1] if self.areas else None
            return self.state()
        if method == 'import_map' or method == 'example_map':
            path = Path(args['path']) if method == 'import_map' else RESOURCES / 'example-map.json'
            if path.stat().st_size > 80*1024*1024: raise ValueError('Map is too large.')
            area = OfflineMap(read_json(path, None))
            if method == 'import_map': self.save_area(area)
            else: self.area, self.route, self.example_active = area, None, True
            return area.pack
        if self.setup_lock.locked() and method in ('setup_run','start_model','download_model','download_voice','download_us_maps'):
            raise RuntimeError('Setup is running. Open setup to check progress or pause it.')
        if not self.lock.acquire(blocking=False):
            label = self.operation['label'] if self.operation else 'Another operation is running'
            raise RuntimeError(label + '. Wait for it to finish before starting another operation.')
        if self.setup_lock.locked() and method in ('setup_run','start_model','download_model','download_voice','download_us_maps'):
            self.lock.release()
            raise RuntimeError('Setup is running. Open setup to check progress or pause it.')
        self.operation = {'method':method, 'label':OPERATION_LABELS.get(method, 'Working'), 'progress':''}
        emit({'event':'operation', 'data':self.operation})
        foreground = True
        def release_foreground():
            nonlocal foreground
            self.voice.busy.clear()
            self.operation = None
            emit({'event':'operation', 'data':None})
            emit({'event':'status','data':'Ready' if self.ready else 'Model not started'})
            foreground = False
            self.lock.release()
        try:
            if method == 'setup_run':
                # Claim setup while holding the foreground lock, so a second
                # request cannot start changing model files between phases.
                if not self.setup_lock.acquire(blocking=False): raise RuntimeError('Setup is already running.')
                try:
                    return self.setup.run(args.get('model_id'), background=release_foreground)
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
                revision = self.position_revision
                result = route_to_place(catalog, location(self.profile), place)
                if revision != self.position_revision:
                    raise ValueError('Your position changed while directions were calculated. Request directions again from the new position.')
                self.route = result
                return result
            if method == 'clear':
                self.history = []; write_json(DATA / 'conversation.json', []); return True
            if method == 'start_model':
                layers = args.get('layers', self.settings.get('gpu_layers','auto'))
                if layers != 'auto':
                    layers = int(layers)
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
                self.settings.update(model=path, gpu_layers=layers)
                write_json(DATA / 'settings.json', self.settings)
                self.ready = True
                emit({'event':'status','data':'Ready'})
                return self.settings
            if method == 'chat':
                text = str(args.get('text','')).strip()[:4000]
                if not text: raise ValueError('Enter a question.')
                catalog = self.catalog()
                revision = self.position_revision
                direct = map_answer(text, self.profile, catalog, self.route)
                is_map_answer = direct is not None
                if not direct:
                    calculation = supply_duration(text)
                    if calculation: direct = (calculation, None)
                if not direct and not self.ready: direct = reference_answer(text)
                if is_map_answer and revision != self.position_revision:
                    direct = ('Your position changed while directions were calculated. Request directions again from the new position.', None)
                if not direct and not self.ready: raise RuntimeError('Start your model in Settings first.')
                self.voice.busy.set(); emit({'event':'status','data':'Thinking'})
                spoken = self.voice.enabled.is_set()
                preferences = {**PROMPT_DEFAULTS, **self.settings}
                documents = retrieve(text) if not direct else []
                references = [{k:d[k] for k in ('id','section','title','heading')} for d in documents if d.get('id')]
                payload = messages(self.profile, self.history, text, catalog, self.route, preferences, spoken, documents) if not direct else None
                def speak_sentence(sentence):
                    if self.voice.enabled.is_set(): self.voice.speak(sentence)
                answer, route = direct or (self.model.chat(payload, on_sentence=speak_sentence if spoken else None,
                    max_tokens=preferences['voice_max_tokens' if spoken else 'text_max_tokens'],
                    max_sentences=preferences['voice_max_sentences'] if spoken else None), None)
                self.history += [{'role':'user','content':text},{'role':'assistant','content':answer,'references':references}]
                self.history = self.history[-100:]
                write_json(DATA / 'conversation.json', self.history)
                if is_map_answer: self.route = route
                if direct and self.voice.enabled.is_set():
                    # Keep full map records on screen; speak a short orientation only.
                    summary = (f"The recorded destination is {route['destination']}; the mapped walk is {route['distance_m']/1609.344:.2f} miles. " + (route['steps'][0]['instruction'] if route.get('steps') else '') + ' Conditions and access are unverified; full directions are in chat.'
                               if route else ' '.join(answer.splitlines()[:1]))
                    import re
                    self.voice.speak(' '.join(re.split(r'(?<=[.!?])\s+', summary)[:preferences['voice_max_sentences']]))
                emit({'event':'answer','data':{'text':answer,'question':text,'route':self.route,'references':references}})
                return answer
            if method in ('download_model','download_voice'):
                fn = prepare_qwen if method == 'download_model' else prepare_voice
                fn(self.progress)
                self.settings = {**PROMPT_DEFAULTS, **read_json(DATA / 'settings.json', {})}
                return True
            if method == 'download_us_maps':
                path = prepare_us(self.progress)
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
        self.board.close(); self.voice.close(); self.model.close()


def main():
    sys.stdin.reconfigure(encoding='utf-8'); sys.stdout.reconfigure(encoding='utf-8')
    service = Service()
    def request(item):
        try: emit({'id':item['id'], 'result':service.command(item['method'], item.get('args',{}))})
        except Exception as error: emit({'id':item['id'], 'error':str(error)})
    try:
        for line in sys.stdin:
            item = json.loads(line)
            if item['method'] == 'shutdown': break
            threading.Thread(target=request, args=(item,), daemon=True).start()
    finally: service.close()
