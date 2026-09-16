"""Native UI, microphone, speech synthesis and offline recognition smoke test."""
import json
import os
import tempfile
import wave
from pathlib import Path

temp = tempfile.TemporaryDirectory()
os.environ['JARVISS_DATA'] = temp.name
from jarviss.app import App
from jarviss.maps import OfflineMap
from tests.test_core import fixture

app = App()
app.withdraw()
app.update()
app.lat.set('40.0'); app.lon.set('-74.0')
app.supplies.insert('1.0', 'Two people, 4 liters of water, blankets.')
assert app.save_profile()
app.area = OfflineMap(fixture())
app.refresh_map()
app.send('Where is the nearest water?')
app.poll()
assert 'Recorded fountain' in app.transcript.get('1.0', 'end')
assert app.route['distance_m'] > 190
assert not app.working
app.close()
print('PASS: native UI, profile persistence, grounded chat, route state')

import sounddevice as sd
rate = int(sd.query_devices(kind='input')['default_samplerate'])
with sd.RawInputStream(samplerate=rate, channels=1, dtype='int16') as mic:
    data, overflow = mic.read(rate // 4)
    assert len(data) > 0
print('PASS: native microphone capture (not saved)')

if os.name == 'nt':
    import pythoncom
    import win32com.client
    pythoncom.CoInitialize()
    speaker = win32com.client.Dispatch('SAPI.SpVoice')
    stream = win32com.client.Dispatch('SAPI.SpFileStream')
    stream.Format.Type = 22
    path = str(Path(temp.name) / 'voice.wav')
    stream.Open(path, 3)
    speaker.AudioOutputStream = stream
    speaker.Speak('Where is the nearest water?')
    stream.Close()
    from vosk import Model, KaldiRecognizer, SetLogLevel
    from jarviss.storage import MODELS
    from jarviss.assets import VOICE_NAME
    SetLogLevel(-1)
    model = Model(str(MODELS / VOICE_NAME))
    with wave.open(path) as audio:
        rec = KaldiRecognizer(model, audio.getframerate())
        assert audio.getnchannels() == 1
        rec.AcceptWaveform(audio.readframes(audio.getnframes()))
        text = json.loads(rec.FinalResult())['text']
    assert 'water' in text, text
    speaker = None; stream = None
    pythoncom.CoUninitialize()
    print('PASS: Windows offline speech synthesis -> Vosk transcription:', text)

temp.cleanup()
