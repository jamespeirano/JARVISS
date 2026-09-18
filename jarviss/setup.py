"""One local setup flow. Downloaded data stays outside the installer."""
import hashlib
import re
import ssl
import threading
import time
import traceback
import urllib.error
from pathlib import Path
from .storage import ROOT, DATA, MODELS, RESOURCES, read_json, write_json, portable_path, model_path
from .hardware import inspect, recommend, GIB, gb
from .assets import prepare_runtime, prepare_voice, VOICE_NAME, find_server
from .map_setup import prepare_basemap, prepare_routing, verify_us, basemap_path, download_file, remaining_bytes, SEGMENTS_URL


class SetupPaused(RuntimeError):  # A pause is expected, not a defect, when reported to the UI.
    def __init__(self, message='Download paused. Continue from setup to reuse saved files.', note=''):
        super().__init__(message+note); self.note = note


# The llama runtime archive plus the voice zip while its copy is extracted.
TRANSIENT_BYTES = 400_000_000


def model_catalog():
    catalog = read_json(RESOURCES / 'model-catalog.json', {})
    models = catalog.get('models') if isinstance(catalog, dict) else None
    if not isinstance(models, list) or not models:
        raise RuntimeError('The model catalog is missing or damaged. Reinstall JARVISS to restore its resources.')
    return models


def friendly(error):
    if isinstance(error, ssl.SSLCertVerificationError) or (
            isinstance(error, urllib.error.URLError) and isinstance(error.reason, ssl.SSLCertVerificationError)):
        return RuntimeError('Could not verify the download server. Check this computer’s date and internet connection, then retry.')
    if not str(error):
        # A bare StopIteration (release asset or map build missing) must not show an empty warning.
        traceback.print_exc()
        return RuntimeError(f'Setup stopped at an unexpected {type(error).__name__}. Details are in service.log.')
    return error


def choose(model_id):
    model = next((m for m in model_catalog() if m['id'] == model_id), None)
    if not model: raise ValueError('Choose a model from the list.')
    return model


def prepare_model(model_id, progress=print):
    model = choose(model_id)
    dest = MODELS / model['filename']
    MODELS.mkdir(parents=True, exist_ok=True)
    download_file(model['url'], dest, progress, model['bytes'], model['sha256'])
    write_json(dest.with_suffix('.source.json'), model)
    return dest


class Setup:
    def __init__(self, service):
        self.service = service
        self.cancel = threading.Event()
        self.info = read_json(DATA / 'setup.json', {})
        if self.info.get('status') in ('downloading', 'testing'):
            self.info.update(status='paused', detail='Setup was interrupted. Continue to reuse downloaded files.')
        self.phase, self.weights, self.fraction = None, {}, {}

    def snapshot(self):
        return {'skipped':False, 'percent':0, 'eta':'', **self.info}

    def plan(self, selected=None):
        process = self.service.model.process
        active = bool(process and process.poll() is None)
        hardware = inspect(process.pid if active else None, self.service.model.allocated_memory if active else 0)
        rows, recommended = recommend(model_catalog(), hardware)
        # Metal and Vulkan allocations are not fully reflected in process RSS.
        # A successfully running model is stronger compatibility evidence than
        # a new estimate made while that same model occupies device memory.
        if self.service.ready and process and process.poll() is None:
            current = next((r for r in rows if r['id'] == self.service.settings.get('model_id')), None)
            if current:
                current.update(fits=True, reason='Already running on this computer.')
                if recommended is None or rows.index(current) > next(i for i,r in enumerate(rows) if r['id']==recommended):
                    recommended = current['id']
        if selected is not None: choose(selected)
        selected = selected or self.info.get('model_id') or recommended or rows[0]['id']
        if selected not in [r['id'] for r in rows]: selected = recommended or rows[0]['id']
        model = choose(selected)
        basemap = bool(self.service.archive)
        routing = self.service.us_router.status()['ready']
        voice = self.service.state()['voiceReady']
        for row in rows:
            dest = MODELS / row['filename']
            row['installed'] = dest.is_file() and dest.stat().st_size == row['bytes']
        row = next(r for r in rows if r['id'] == selected)
        model_bytes = remaining_bytes(MODELS / model['filename'], model['url'], model['bytes'], model['sha256'])
        routing_bytes = 0 if routing else 2_000_000_000
        directory = ROOT/'local-maps'/'routing-us'
        manifest = read_json(directory/'manifest.json',{})
        if not routing and manifest.get('files'):
            import re
            files = [f for f in manifest['files'] if re.fullmatch(r'[EW]\d+_[NS]\d+\.rd5',f.get('name','')) and type(f.get('size')) is int and f['size']>0]
            if len(files) == len(manifest['files']):
                routing_bytes = sum(remaining_bytes(directory/'segments4'/f['name'],SEGMENTS_URL+f['name'],f['size']) for f in files)
        component_bytes = {'model':model_bytes, 'voice':0 if voice else 520_000_000, 'map':0 if basemap else 21_000_000_000, 'directions':routing_bytes}
        shared_bytes = component_bytes['voice'] + component_bytes['map'] + routing_bytes
        required = model_bytes+shared_bytes+2*GIB + (0 if voice and find_server() else TRANSIENT_BYTES)
        return {'hardware':hardware, 'models':rows, 'recommended':recommended, 'selected':selected,
                'download_bytes':model_bytes+shared_bytes, 'required_bytes':required, 'component_bytes':component_bytes,
                'space_ok':hardware['disk'] >= required,
                'components':{'model':row['installed'], 'voice':voice, 'map':basemap, 'directions':routing, 'guides':True},
                'directory':str(ROOT), 'run':self.snapshot()}

    def save(self, **values):
        self.info.update(values)
        write_json(DATA / 'setup.json', self.info)

    def progress(self, text):
        if self.cancel.is_set(): raise SetupPaused()
        self.info.update(detail=text, **self.estimate(text))
        self.service.setup_progress()

    def begin(self, phase):
        # Everything before this phase is complete; its bytes now count in full.
        for name in self.fraction: self.fraction[name] = 1.0
        self.phase = phase; self.fraction.setdefault(phase, 0.0)
        self.info.update(eta='')

    def estimate(self, text):
        """Progress across the whole run, each phase weighted by the bytes it still has to fetch."""
        total = sum(self.weights.values())
        if self.phase is None or not total: return {}
        files = re.search(r'(\d+) / (\d+) files saved', text)
        percent = re.search(r'(\d+)%', text)
        # Directions download three files at once; only the saved-file count is monotonic.
        fraction = int(files[1])/max(1,int(files[2])) if files else int(percent[1])/100 if percent and self.phase != 'directions' else 0
        self.fraction[self.phase] = max(self.fraction.get(self.phase, 0), min(1, fraction))
        done = sum(self.weights.get(p, 0)*f for p, f in self.fraction.items())
        result = {'percent':min(100, int(done*100/total))}
        rate = re.search(r'· ([\d.]+) (MB|GB)/s', text)
        if rate and self.weights.get(self.phase):
            seconds = (total-done)/max(1, float(rate[1])*(1e6 if rate[2] == 'MB' else 1e9))
            result['eta'] = 'about ' + (f'{max(1,round(seconds))} sec left' if seconds < 60 else f'{(round(seconds)+59)//60} min left' if seconds < 5400 else f'{seconds/3600:.1f} h left')
        return result

    def restore(self, settings, replaced, running):
        """Put the previous selection back in memory, on disk and, if it was running, in service."""
        self.service.settings.update({k:v for k,v in settings.items() if k in ('model','model_id','gpu_layers','model_context')})
        write_json(DATA / 'settings.json', self.service.settings)
        if not replaced: return ''
        self.service.model.stop()
        if not running or not settings.get('model'): return ''
        try:
            self.service.model.start(model_path(settings['model']), settings.get('gpu_layers','auto'), context=settings.get('model_context',8192))
            self.service.ready = True
            return ''
        except Exception as error:
            traceback.print_exc()
            return f' The previous model did not restart: {error}'

    def complete(self):
        try: return bool(self.service.archive and self.service.us_router.status()['ready'] and self.service.state()['voiceReady'])
        except Exception:
            # An unreadable component counts as missing; the validated model stays usable.
            traceback.print_exc(); return False

    def run(self, model_id, only_model=False, background=None):
        choose(model_id)
        plan = self.plan(model_id)
        row = next(r for r in plan['models'] if r['id'] == model_id)
        if not row['fits']: raise ValueError(row['reason'])
        needed = (0 if row['installed'] else row['bytes'])+2*GIB if only_model else plan['required_bytes']
        if plan['hardware']['disk'] < needed:
            raise ValueError(f'Free at least {gb(needed)} in the data folder before downloading.')
        self.cancel.clear()
        sizes = plan.get('component_bytes', {})
        self.weights = {k:v for k, v in sizes.items() if k == 'model' or not only_model}
        if not any(self.weights.values()): self.weights = {k:1 for k in self.weights}  # Check setup: nothing to fetch, count phases.
        self.fraction = {}; self.begin('runtime')
        self.save(status='downloading', model_id=model_id, stage=0, detail='Preparing files', error=None, model_ready=False, skipped=False, percent=0, eta='')
        previous_settings = dict(self.service.settings)
        previous_running = bool(self.service.ready)
        validated = replaced = False
        try:
            prepare_runtime(self.progress)
            self.save(stage=1); self.begin('model'); self.progress('Downloading model')
            path = prepare_model(model_id, self.progress)
            if not only_model:
                self.save(stage=2); self.begin('voice'); self.progress('Preparing voice')
                prepare_voice(self.progress)
            self.begin('test'); self.progress('Testing model on this computer')
            self.save(status='testing', stage=2)
            self.service.voice.pause()
            self.service.ready = False
            self.service.model.stop(); replaced = True
            if not only_model:
                self.progress('Checking voice files')
                self.service.voice.prepare_tts()
                self.service.voice.make_recognizer(16000)
            started = time.monotonic()
            self.service.model.start(path, 'auto', context=row['context'])
            self.progress('Checking the first response')
            answer = self.service.model.chat([{'role':'user','content':'Reply with the single word Ready.'}], max_tokens=24)
            elapsed = time.monotonic()-started
            if not answer.strip(): raise ValueError('The model did not produce a response.')
            self.service.settings.update(model=portable_path(path), model_id=model_id, gpu_layers='auto', model_context=row['context'])
            write_json(DATA / 'settings.json', self.service.settings)
            self.service.ready = True
            validated = True
            self.save(status='downloading', stage=3, seconds=round(elapsed,1), model_ready=True)
            self.progress('Chat is ready. Preparing US map and walking directions.' if not only_model else 'Model is ready')
            if background: background()
            if not only_model:
                self.save(stage=3); self.begin('map'); self.progress('Preparing US map and walking directions')
                if self.service.archive and self.service.us_router.status()['ready']:
                    # Only an explicit Check setup on a complete install re-hashes the map data; a first run never does.
                    if basemap_path() in verify_us(self.progress):
                        self.service.swap_map(archive=None, location_index=None, archive_error='The saved US map failed verification and is being downloaded again.')
                if not self.service.archive:
                    archive = prepare_basemap(self.progress, cancel=self.cancel)
                    self.service.command('import_basemap', {'path':str(archive)})
                self.save(stage=4); self.begin('directions'); self.progress('Preparing US walking directions')
                prepare_routing(self.progress)
                from .us_routing import USRouter
                self.service.us_router = USRouter()
            full = self.complete()
            self.save(status='ready' if full else 'model_ready', stage=5, seconds=round(elapsed,1),
                      detail='Ready offline' if full else 'Model is ready', error=None, percent=100, eta='')
            return self.plan(model_id)
        except SetupPaused as paused:
            note = '' if validated else self.restore(previous_settings, replaced, previous_running)
            self.save(status='paused', detail='Setup paused. Continue to reuse downloaded files.'+paused.note+note, eta='')
            return self.plan(model_id)
        except Exception as error:
            error = friendly(error)
            if self.info.get('status') in ('ready','model_ready'):
                # Everything is installed and the model answers; only the closing summary failed.
                self.save(error=f'Setup finished, but its summary could not be refreshed: {error}')
                raise RuntimeError(self.info['error'])
            # Keep the user's last selected model if validation of the new one failed.
            note = '' if validated else self.restore(previous_settings, replaced, previous_running)
            self.save(status='failed', error=str(error), detail='Setup stopped. Retry to reuse downloaded files.'+note, eta='')
            raise error
