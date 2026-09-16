"""Offline streaming recognition, neural speech, and explicit audio lifecycle."""
import json
import queue
import re
import threading
import time
from contextlib import closing
from .storage import MODELS
from .assets import VOICE_NAME


class _TypedSession:
    """Adapt kokoro-onnx 0.4.9's integer speed input to this export's float input."""
    def __init__(self, session):
        self.session = session
        self._model_path = session._model_path

    def get_inputs(self): return self.session.get_inputs()

    def run(self, outputs, inputs):
        import numpy as np
        values = dict(inputs)
        values['speed'] = np.asarray(values['speed'], dtype=np.float32)
        # The library already cast 1.05 to integer; preserve configured speech rate.
        values['speed'][:] = 1.05
        return self.session.run(outputs, values)


def devices():
    import sounddevice as sd
    hosts = sd.query_hostapis()
    return [{'id': i, 'name': d['name'], 'host': hosts[d['hostapi']]['name'],
             'input': d['max_input_channels'] > 0, 'output': d['max_output_channels'] > 0}
            for i, d in enumerate(sd.query_devices())]


def resolve_device(saved, direction):
    if not saved:
        import sys
        import sounddevice as sd
        if sys.platform == 'win32':
            # Use the modern Windows shared audio endpoint, not legacy MME mapping.
            for host in sd.query_hostapis():
                if host['name'] == 'Windows WASAPI':
                    value = host['default_input_device' if direction == 'input' else 'default_output_device']
                    if value >= 0: return value
        return None
    matches = [d for d in devices() if d[direction] and d['name'] == saved['name'] and d['host'] == saved['host']]
    if not matches: raise RuntimeError(f"Selected {direction} device is disconnected. Choose another in Settings.")
    return matches[0]['id']


class Voice:
    def __init__(self, on_text, on_status, on_error, on_event=None):
        self.on_text, self.on_status, self.on_error = on_text, on_status, on_error
        self.on_event = on_event or (lambda kind, value: None)
        self.enabled = threading.Event()
        self.closed = threading.Event()
        self.busy = threading.Event()
        self.speaking = threading.Event()
        self.started = threading.Event()
        self.audio = queue.Queue(maxsize=50)
        self.speech = queue.Queue()
        self.listener = self.speaker = self.model = self.tts = None
        self.start_error = None
        self.input_device = self.output_device = None
        self.voice_name = 'bm_george'
        self.epoch = 0
        self.load_lock = threading.Lock()
        self.start_lock = threading.Lock()
        self.last_meter = 0

    def configure(self, settings):
        self.input_device = settings.get('input_device')
        self.output_device = settings.get('output_device')
        self.voice_name = settings.get('voice_name', 'bm_george')

    def prepare_tts(self):
        with self.load_lock:
            if self.tts is not None: return
            import onnxruntime as ort
            ort.disable_telemetry_events()
            from kokoro_onnx import Kokoro
            folder = MODELS / 'kokoro'
            if not (folder / 'kokoro-v1.0.onnx').exists() or not (folder / 'voices-v1.0.bin').exists():
                raise RuntimeError('Download the voice models in Settings first.')
            options = ort.SessionOptions(); options.intra_op_num_threads = 4; options.inter_op_num_threads = 1
            session = ort.InferenceSession(str(folder / 'kokoro-v1.0.onnx'), sess_options=options, providers=['CPUExecutionProvider'])
            self.tts = Kokoro.from_session(_TypedSession(session), str(folder / 'voices-v1.0.bin'))

    def start(self):
        with self.start_lock:
            if self.enabled.is_set(): return
            if self.closed.is_set(): raise RuntimeError('Voice service is closed.')
            if not (MODELS / VOICE_NAME / 'am/final.mdl').exists():
                raise RuntimeError('Download the voice models in Settings first.')
            self.on_status('Starting voice')
            try:
                self.prepare_tts()
                import sounddevice as sd
                output = resolve_device(self.output_device, 'output')
                info = sd.query_devices(output, kind='output')
                sd.check_output_settings(device=output, channels=min(2,info['max_output_channels']), dtype='float32', samplerate=info['default_samplerate'])
                if self.listener and self.listener.is_alive(): self.listener.join(timeout=2)
                self.started.clear(); self.start_error = None; self.enabled.set()
                self.listener = threading.Thread(target=self._listen, daemon=True); self.listener.start()
                if not self.started.wait(30):
                    self.enabled.clear(); raise TimeoutError('Microphone did not start. Check audio permissions and selected device.')
                if self.start_error: raise RuntimeError(self.start_error)
            except Exception:
                self.enabled.clear(); self.on_status('Voice off'); raise

    def pause(self):
        self.enabled.clear(); self.epoch += 1
        self._drain(self.speech)
        self.on_status('Voice off'); self.on_event('mic_level', 0)

    @staticmethod
    def _drain(q):
        while True:
            try: q.get_nowait()
            except queue.Empty: break

    def speak(self, text):
        text = re.sub(r'https?://\S+|[*#`]', '', text).strip()
        if not text: return
        self.speaking.set()
        self.speech.put((self.epoch, text))
        if not self.speaker or not self.speaker.is_alive():
            self.speaker = threading.Thread(target=self._speak, daemon=True); self.speaker.start()

    def make_recognizer(self, rate):
        from vosk import Model, KaldiRecognizer, SetLogLevel
        SetLogLevel(-1)
        if self.model is None: self.model = Model(str(MODELS / VOICE_NAME))
        rec = KaldiRecognizer(self.model, rate); rec.SetWords(True)
        return rec

    def accept_audio(self, recognizer, data):
        if recognizer.AcceptWaveform(data):
            result = json.loads(recognizer.Result())
            text = result.get('text', '').strip()
            words = result.get('result', [])
            confidence = sum(w.get('conf', 0) for w in words) / len(words) if words else 0
            self.on_event('partial', '')
            if not text: return
            if text in ('stop listening', 'go to sleep', 'stop voice'):
                self.pause(); return
            if confidence < .65:
                self.on_status('Please repeat'); return
            self.busy.set(); self.on_status('Thinking'); self.on_text(text)
        else:
            self.on_event('partial', json.loads(recognizer.PartialResult()).get('partial', ''))

    def _listen(self):
        import sys
        if sys.platform == 'win32':
            import pythoncom
            pythoncom.CoInitialize()
        try:
            import sounddevice as sd
            import numpy as np
            device = resolve_device(self.input_device, 'input')
            rate = int(sd.query_devices(device, kind='input')['default_samplerate'])
            recognizer = self.make_recognizer(rate)
            self._drain(self.audio)
            def callback(data, frames, timing, status):
                if not self.enabled.is_set(): return
                now = time.monotonic()
                if now-self.last_meter > .1:
                    self.last_meter = now
                    samples = np.frombuffer(data, dtype=np.int16).astype(np.float32)
                    self.on_event('mic_level', min(1.0, float(np.sqrt(np.mean(samples*samples))) / 5000))
                if not self.busy.is_set() and not self.speaking.is_set():
                    try: self.audio.put_nowait(bytes(data))
                    except queue.Full: pass
            stream = None
            for attempt in range(3):
                try:
                    stream = sd.RawInputStream(device=device, samplerate=rate, blocksize=int(rate*.08), dtype='int16', channels=1, callback=callback)
                    stream.start()
                    break
                except sd.PortAudioError:
                    if stream: stream.close()
                    if attempt == 2: raise
                    self.closed.wait(.4)
            with closing(stream):
                self.on_status('Listening'); self.started.set(); paused = False
                while self.enabled.is_set() and not self.closed.is_set():
                    if self.busy.is_set() or self.speaking.is_set():
                        recognizer.Reset(); self._drain(self.audio); paused = True
                        self.closed.wait(.05); continue
                    if paused: self.on_status('Listening'); paused = False
                    try: data = self.audio.get(timeout=.15)
                    except queue.Empty: continue
                    self.accept_audio(recognizer, data)
        except Exception as error:
            self.start_error = f'Microphone: {error}'
            self.enabled.clear(); self.on_status('Voice off'); self.on_error(self.start_error)
        finally:
            self.started.set(); self.on_event('mic_level', 0)
            if sys.platform == 'win32': pythoncom.CoUninitialize()

    def _speak(self):
        import sys
        if sys.platform == 'win32':
            import pythoncom
            pythoncom.CoInitialize()
        try:
            import sounddevice as sd
            self.prepare_tts()
            while not self.closed.is_set():
                try: epoch, text = self.speech.get(timeout=.15)
                except queue.Empty: continue
                if epoch != self.epoch: continue
                self.speaking.set(); self.on_status('Preparing speech')
                started = time.monotonic()
                # Split long model output to bound first-audio latency and pause delay.
                sentences = re.split(r'(?<=[.!?])\s+|\n+', text)
                for sentence in sentences:
                    if not sentence.strip() or self.closed.is_set() or epoch != self.epoch: continue
                    audio, rate = self.tts.create(sentence, voice=self.voice_name, lang='en-gb' if self.voice_name.startswith('b') else 'en-us', speed=1.05)
                    self.on_event('speech_timing', {'synthesis_seconds':round(time.monotonic()-started,3), 'audio_seconds':round(len(audio)/rate,3)})
                    if self.closed.is_set() or epoch != self.epoch: break
                    self.on_status('Speaking')
                    self.play_audio(audio, rate, epoch)
                    started = time.monotonic()
                if self.speech.empty():
                    self.closed.wait(.3); self.speaking.clear()
                    self.on_status('Thinking' if self.busy.is_set() else 'Listening' if self.enabled.is_set() else 'Voice off')
        except Exception as error:
            self.on_error(f'Speech output: {error}. Check the speaker selection in Settings.')
            self.enabled.clear(); self.on_status('Voice off')
        finally:
            self.speaking.clear()
            if sys.platform == 'win32': pythoncom.CoUninitialize()

    def play_audio(self, audio, rate, epoch=None):
        import sounddevice as sd
        import numpy as np
        import soxr
        device = resolve_device(self.output_device, 'output')
        info = sd.query_devices(device, kind='output')
        target_rate = int(info['default_samplerate'])
        channels = min(2, info['max_output_channels'])
        if target_rate != rate: audio = soxr.resample(audio, rate, target_rate, quality='HQ')
        pcm = np.repeat(np.asarray(audio,dtype=np.float32).reshape(-1,1),channels,axis=1)
        with sd.OutputStream(device=device, samplerate=target_rate, channels=channels, dtype='float32', blocksize=0) as output:
            for i in range(0,len(pcm),int(target_rate*.05)):
                if self.closed.is_set() or (epoch is not None and epoch != self.epoch): break
                output.write(pcm[i:i+int(target_rate*.05)])

    def close(self):
        self.pause(); self.closed.set()
        for thread in (self.listener, self.speaker):
            if thread and thread is not threading.current_thread(): thread.join(timeout=2)
