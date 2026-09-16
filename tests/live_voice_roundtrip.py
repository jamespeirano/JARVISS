"""Real Qwen + Vosk + Kokoro roundtrip, using generated input and real speaker output."""
import json
import os
import tempfile
import time
from pathlib import Path


def main():
    with tempfile.TemporaryDirectory(prefix='jarvis-roundtrip-') as folder:
        os.environ['JARVISS_DATA'] = folder
        from jarviss import service as module
        from jarviss.storage import ROOT
        events=[]
        module.emit=lambda item: events.append((time.monotonic(),item))
        service=module.Service()
        try:
            settings=json.loads((ROOT/'local-data/settings.json').read_text())
            start=time.monotonic();service.command('start_model',{'path':settings['model'],'layers':os.environ.get('JARVIS_TEST_GPU',settings['gpu_layers'])})
            load=time.monotonic()-start
            service.command('voice',{'enabled':True})
            service.voice.busy.set()
            import numpy as np
            samples,rate=service.voice.tts.create('Please say offline systems ready.',voice='bm_george',lang='en-gb')
            recognizer=service.voice.make_recognizer(rate)
            pcm=(samples*32767).astype(np.int16).tobytes()+bytes(rate*4)
            start=time.monotonic();events.clear()
            for i in range(0,len(pcm),4000):service.voice.accept_audio(recognizer,pcm[i:i+4000])
            deadline=time.monotonic()+180
            while time.monotonic()<deadline:
                if any(e.get('event')=='answer' for _,e in events) and not service.voice.speaking.is_set() and not service.voice.busy.is_set():break
                if any(e.get('event')=='error' for _,e in events):raise AssertionError([e for _,e in events if e.get('event')=='error'])
                time.sleep(.1)
            answers=[e for _,e in events if e.get('event')=='answer']
            assert answers,'No answer completed'
            heard=[e for _,e in events if e.get('event')=='heard']
            assert heard,'Recognition did not submit a turn'
            speaking=[t for t,e in events if e.get('event')=='voice' and e.get('data')=='Speaking']
            assert speaking,'No neural voice playback'
            assert service.voice.enabled.is_set()
            result={'model_load_seconds':round(load,2),'recognized_test_phrase':heard[0]['data'],
                    'first_playback_seconds':round(speaking[0]-start,2),
                    'roundtrip_seconds':round(time.monotonic()-start,2),'answer':answers[0]['data']['text'],
                    'returned_to_listening':any(e.get('event')=='voice' and e.get('data')=='Listening' for _,e in events),
                    'input_type':'Generated audio fed to production recognizer; physical microphone pickup tested separately'}
            print(json.dumps(result,indent=2))
            (ROOT/'local-data/voice-roundtrip.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        finally:service.close()


if __name__=='__main__':main()
