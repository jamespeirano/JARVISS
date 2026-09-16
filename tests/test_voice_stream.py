import io
import json
import unittest
from unittest.mock import patch
from jarviss.model import LocalModel


class VoiceStreamTests(unittest.TestCase):
    def test_voice_limit_stops_long_response(self):
        chunks=['One. Two. Three. Four. ', 'Five.']
        body=b''.join(b'data: '+json.dumps({'choices':[{'delta':{'content':text}}]}).encode()+b'\n\n' for text in chunks)
        model=LocalModel();model.process=type('Running',(),{'poll':lambda _:None})();model.url='http://127.0.0.1:1';spoken=[]
        with patch('urllib.request.urlopen',return_value=io.BytesIO(body)) as request:
            answer=model.chat([],on_sentence=spoken.append,max_sentences=3,max_tokens=180)
        self.assertEqual(answer,'One. Two. Three.')
        self.assertEqual(spoken,['One.','Two.','Three.'])
        self.assertEqual(json.loads(request.call_args.args[0].data)['max_tokens'],180)

    def test_voice_prompt_only_applies_when_enabled(self):
        from jarviss.assistant import messages
        settings={'system_prompt':'Custom role','voice_prompt':'Speak briefly','voice_max_sentences':2}
        text=messages({},[],'Hello',settings=settings)[0]['content']
        voice=messages({},[],'Hello',settings=settings,spoken=True)[0]['content']
        self.assertTrue(text.startswith('Custom role'))
        self.assertNotIn('Speak briefly',text)
        self.assertIn('Speak briefly',voice)
        self.assertIn('at most 2 sentences',voice)

    def test_sentences_arrive_before_stream_ends(self):
        events=[]
        chunks=['Ready. ', 'What equipment do you have?']
        class Stream(io.BytesIO):
            def __next__(self):
                line=super().__next__()
                if b'[DONE]' in line:
                    self_test.assertTrue(events, 'Speech must start before completion')
                return line
        self_test=self
        body=b''.join(b'data: '+json.dumps({'choices':[{'delta':{'content':text}}]}).encode()+b'\n\n' for text in chunks)+b'data: [DONE]\n'
        model=LocalModel();model.process=type('Running',(),{'poll':lambda _:None})();model.url='http://127.0.0.1:1'
        with patch('urllib.request.urlopen',return_value=Stream(body)):
            answer=model.chat([],on_sentence=events.append)
        self.assertEqual(answer,''.join(chunks))
        self.assertEqual(events,[x.strip() for x in chunks])

    def test_reasoning_is_not_spoken(self):
        chunks=['<think>Private reasoning.', '</think>Use your saved map.']
        body=b''.join(b'data: '+json.dumps({'choices':[{'delta':{'content':text}}]}).encode()+b'\n\n' for text in chunks)+b'data: [DONE]\n'
        model=LocalModel();model.process=type('Running',(),{'poll':lambda _:None})();model.url='http://127.0.0.1:1';spoken=[]
        with patch('urllib.request.urlopen',return_value=io.BytesIO(body)):
            answer=model.chat([],on_sentence=spoken.append)
        self.assertEqual(answer,'Use your saved map.')
        self.assertEqual(spoken,['Use your saved map.'])
