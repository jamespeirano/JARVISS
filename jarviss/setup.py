"""One local setup flow. Downloaded data stays outside the installer."""
import hashlib
import ssl
import threading
import time
import urllib.error
from pathlib import Path
from .storage import ROOT, DATA, MODELS, RESOURCES, read_json, write_json, portable_path
from .hardware import inspect, recommend, GIB
from .assets import prepare_runtime, prepare_voice, VOICE_NAME
from .map_setup import prepare_basemap, prepare_routing, download_file, remaining_bytes, SEGMENTS_URL


class SetupPaused(Exception):
    pass


def model_catalog():
    return read_json(RESOURCES / 'model-catalog.json', {})['models']


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

    def snapshot(self):
        return dict(self.info)

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
        shared_bytes = (0 if basemap else 21_000_000_000) + routing_bytes + (0 if voice else 520_000_000)
        return {'hardware':hardware, 'models':rows, 'recommended':recommended, 'selected':selected,
                'download_bytes':model_bytes+shared_bytes, 'required_bytes':model_bytes+shared_bytes+2*GIB,
                'space_ok':hardware['disk'] >= model_bytes+shared_bytes+2*GIB,
                'components':{'model':row['installed'], 'voice':voice, 'map':basemap, 'directions':routing, 'guides':True},
                'directory':str(ROOT), 'run':self.snapshot()}

    def save(self, **values):
        self.info.update(values)
        write_json(DATA / 'setup.json', self.info)

    def progress(self, text):
        if self.cancel.is_set(): raise SetupPaused()
        self.info.update(detail=text)
        self.service.setup_progress()

    def run(self, model_id, only_model=False, background=None):
        plan = self.plan(model_id)
        row = next(r for r in plan['models'] if r['id'] == model_id)
        if not row['fits']: raise ValueError(row['reason'])
        needed = (0 if row['installed'] else row['bytes'])+2*GIB if only_model else plan['required_bytes']
        if plan['hardware']['disk'] < needed:
            raise ValueError(f'Free at least {needed/GIB:.1f} GB in the data folder before downloading.')
        self.cancel.clear()
        self.save(status='downloading', model_id=model_id, stage=0, detail='Preparing files', error=None, model_ready=False)
        previous_settings = dict(self.service.settings)
        validated = False
        try:
            prepare_runtime(self.progress)
            self.save(stage=1); self.progress('Downloading model')
            path = prepare_model(model_id, self.progress)
            if not only_model:
                self.save(stage=2); self.progress('Preparing voice')
                prepare_voice(self.progress)
            self.progress('Testing model on this computer')
            self.save(status='testing', stage=2)
            self.service.voice.pause()
            self.service.ready = False
            self.service.model.stop()
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
                self.save(stage=3); self.progress('Preparing US map and walking directions')
                if not self.service.archive:
                    archive = prepare_basemap(self.progress, cancel=self.cancel)
                    self.service.command('import_basemap', {'path':str(archive)})
                self.save(stage=4); self.progress('Preparing US walking directions')
                prepare_routing(self.progress)
                from .us_routing import USRouter
                self.service.us_router = USRouter()
            full = bool(self.service.archive and self.service.us_router.status()['ready'] and self.service.state()['voiceReady'])
            self.save(status='ready' if full else 'model_ready', stage=5, seconds=round(elapsed,1),
                      detail='Ready offline' if full else 'Model is ready', error=None)
            return self.plan(model_id)
        except SetupPaused:
            if self.info.get('status') == 'testing': self.service.model.stop()
            detail = 'Setup paused. Continue to reuse downloaded files.'
            if (ROOT/'local-maps/us-z15.partial').exists():
                detail += ' The unfinished US map must restart; other files are kept.'
            self.save(status='paused', detail=detail)
            return self.plan(model_id)
        except Exception as error:
            # Keep the user's last selected model if validation of the new one failed.
            if not self.service.ready: self.service.model.stop()
            if not validated:
                self.service.settings.update({k:v for k,v in previous_settings.items() if k in ('model','model_id','gpu_layers','model_context')})
            if isinstance(error, ssl.SSLCertVerificationError) or (
                    isinstance(error, urllib.error.URLError) and isinstance(error.reason, ssl.SSLCertVerificationError)):
                error = RuntimeError('Could not verify the download server. Check this computer’s date and internet connection, then retry.')
                self.save(status='failed', error=str(error), detail='Setup stopped. Retry to reuse downloaded files.')
                raise error
            self.save(status='failed', error=str(error), detail='Setup stopped. Retry to reuse downloaded files.')
            raise
