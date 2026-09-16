"""Real local models and audio devices. Run explicitly, not in headless CI."""
import json
import time
import urllib.request
import numpy as np
import sounddevice as sd
from jarviss.voice import Voice, resolve_device
from jarviss.storage import DATA


def wait_for(predicate, seconds=15):
    end = time.monotonic()+seconds
    while time.monotonic()<end:
        if predicate(): return
        time.sleep(.05)
    raise AssertionError('Timed out waiting for voice lifecycle state')


def main():
    original = urllib.request.urlopen
    urllib.request.urlopen = lambda *a, **k: (_ for _ in ()).throw(AssertionError('Unexpected network access'))
    statuses, errors, heard, metrics = [], [], [], []
    voice = Voice(heard.append, statuses.append, errors.append, lambda k,v: metrics.append((k,v)))
    results = {}
    try:
        start=time.monotonic();voice.prepare_tts();results['tts_load_seconds']=round(time.monotonic()-start,3)
        fixtures=[]; timings=[]
        for phrase, required in [('Where is the nearest water?', ['nearest','water']),
                                 ('I have two bottles of water and a flashlight.', ['water','flashlight']),
                                 ('Stop listening.', ['stop','listening'])]:
            start=time.monotonic();audio,rate=voice.tts.create(phrase,voice='bm_george',lang='en-gb',speed=1.05)
            timings.append({'text':phrase,'synthesis_seconds':round(time.monotonic()-start,3),'audio_seconds':round(len(audio)/rate,3)})
            rec=voice.make_recognizer(rate)
            pcm=(np.clip(audio,-1,1)*32767).astype('int16').tobytes()+bytes(rate*2*2)
            recognized=[]
            for i in range(0,len(pcm),int(rate*.08)*2):
                if rec.AcceptWaveform(pcm[i:i+int(rate*.08)*2]): recognized.append(json.loads(rec.Result()).get('text',''))
            recognized.append(json.loads(rec.FinalResult()).get('text',''))
            text=' '.join(recognized)
            assert all(word in text for word in required), (phrase,text)
            fixtures.append((audio,rate))
        results['synthesis']=timings
        results['recognition_fixtures']=3
        # Exercise the production acceptance path, including spoken pause.
        rec=voice.make_recognizer(fixtures[-1][1]);voice.enabled.set()
        pcm=(fixtures[-1][0]*32767).astype('int16').tobytes()+bytes(fixtures[-1][1]*4)
        for i in range(0,len(pcm),4000): voice.accept_audio(rec,pcm[i:i+4000])
        assert not voice.enabled.is_set()
        voice.busy.clear()
        for _ in range(3):
            voice.start();assert voice.enabled.is_set();assert statuses[-1]=='Listening'
            time.sleep(.3);voice.pause()
            if voice.listener:voice.listener.join(3)
            assert not voice.listener.is_alive()
        results['start_pause_cycles']=3
        voice.start();voice.busy.set()
        voice.speak('The speaker test is complete. I am listening again.');voice.busy.clear()
        wait_for(lambda:'Speaking' in statuses)
        wait_for(lambda:not voice.speaking.is_set(),20)
        assert voice.enabled.is_set()
        wait_for(lambda:statuses[-1]=='Listening')
        results['speaker_and_resume']=True
        assert any(k=='mic_level' for k,v in metrics)
        assert not errors, errors
        # Genuine speaker-to-microphone loop; report separately from digital fixtures.
        heard.clear();metrics.clear();audio,rate=fixtures[0];voice.play_audio(audio,rate)
        end=time.monotonic()+7
        while time.monotonic()<end and not heard:time.sleep(.05)
        results['acoustic_loop_water_detected']=any('water' in text for text in heard)
        results['mic_peak_level']=round(max((v for k,v in metrics if k=='mic_level'),default=0),3)
        results['partial_transcription_seen']=any(k=='partial' and v for k,v in metrics)
        voice.busy.clear();voice.pause()
        voice.input_device={'name':'Deliberately missing test device','host':'None'}
        try:voice.start();raise AssertionError('Missing device incorrectly started')
        except RuntimeError:pass
        assert not voice.enabled.is_set()
        results['missing_device_rejected']=True
        print(json.dumps(results,indent=2))
        (DATA/'voice-verification.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
    finally:
        voice.close();sd.stop();urllib.request.urlopen=original


if __name__=='__main__':main()
