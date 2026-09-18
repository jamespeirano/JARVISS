"""Long conversations must leave room for a complete answer."""
import io
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from jarviss.model import CONTEXT_MARKER, MATERIAL_MARKER, OMITTED, QUESTION_MARKER, LocalModel, trim_context


class ModelContextTests(unittest.TestCase):
    def setUp(self):
        self.model = LocalModel()
        self.model.context = 4096

    def tokenizer(self, counts):
        values = iter(counts)
        def post(endpoint, payload):
            if endpoint == '/apply-template':
                return {'prompt':'formatted'}
            return {'tokens':[0] * next(values)}
        return post

    def test_uses_token_count_and_keeps_complete_current_sources(self):
        messages = [dict(role='system', content='Sources and saved facts'),
                    dict(role='user', content='Old question'), dict(role='assistant', content='Old answer'),
                    dict(role='user', content='Current question')]
        with patch.object(self.model, '_post', side_effect=self.tokenizer([4056, 1000])):
            self.assertEqual(self.model._fit_messages(messages, 600), [messages[0], messages[-1]])
        self.assertEqual(len(messages), 4)

    def test_leaves_fitting_history_unchanged(self):
        messages = [dict(role='system', content='Sources'), dict(role='user', content='Question')]
        with patch.object(self.model, '_post', side_effect=self.tokenizer([3400])):
            self.assertEqual(self.model._fit_messages(messages, 600), messages)

    def test_long_multilingual_background_does_not_consume_answer_budget(self):
        messages = [dict(role='system', content='Saved situation and complete reference passages'),
                    dict(role='user', content='Current question')]
        with patch.object(self.model, '_post', side_effect=self.tokenizer([4056])):
            with self.assertRaisesRegex(ValueError, 'Shorten your question or saved situation') as raised:
                self.model._fit_messages(messages, 600)
        self.assertNotIn('Settings', str(raised.exception))

    @staticmethod
    def layout(question='Question'):
        context = {'map':{'nearby':[{'name':'Well'}]}, 'reference_notes':[], 'planner':{'tasks':[{'name':'fix pump'}], 'note':'saved'}}
        material = {'person':{'supplies':'4 liters', 'lat':0.5}, 'local_documents':[{'title':'manual', 'text':'long'}]}
        return [dict(role='system', content='Role' + CONTEXT_MARKER + json.dumps(context)),
                dict(role='user', content=MATERIAL_MARKER + json.dumps(material) + QUESTION_MARKER + question)]

    @staticmethod
    def blocks(messages):
        context = json.loads(messages[0]['content'].split(CONTEXT_MARKER)[1])
        material = json.loads(messages[-1]['content'].split(MATERIAL_MARKER)[1].split(QUESTION_MARKER)[0])
        return material['local_documents'], material['person'], context['planner'], context['map']['nearby']

    def test_context_is_shed_in_order_before_giving_up(self):
        messages = self.layout('Question:\nwith a marker inside')
        with patch.object(self.model, '_post', side_effect=self.tokenizer([5000, 4500, 4200, 4000, 3000])):
            fitted = self.model._fit_messages(messages, 600)
        self.assertEqual(fitted[0]['content'].split(CONTEXT_MARKER)[0], 'Role')
        self.assertEqual(self.blocks(fitted), (OMITTED, OMITTED, OMITTED, OMITTED))
        self.assertTrue(fitted[-1]['content'].endswith(QUESTION_MARKER + 'Question:\nwith a marker inside'))
        self.assertEqual(json.loads(fitted[0]['content'].split(CONTEXT_MARKER)[1])['reference_notes'], [])
        self.assertIn('4 liters', messages[-1]['content'])
        with patch.object(self.model, '_post', side_effect=self.tokenizer([5000, 4500, 4200, 4100, 4050])):
            with self.assertRaisesRegex(ValueError, 'Too much text'):
                self.model._fit_messages(messages, 600)

    def test_imported_files_go_first_and_the_persons_notes_before_saved_records(self):
        messages = self.layout()
        expected = [(OMITTED, {'supplies':'4 liters', 'lat':0.5}, {'tasks':[{'name':'fix pump'}], 'note':'saved'}, [{'name':'Well'}]),
                    (OMITTED, OMITTED, {'tasks':[{'name':'fix pump'}], 'note':'saved'}, [{'name':'Well'}]),
                    (OMITTED, OMITTED, OMITTED, [{'name':'Well'}]), (OMITTED, OMITTED, OMITTED, OMITTED)]
        for step in expected:
            messages = trim_context(messages)
            self.assertEqual(self.blocks(messages), step)
            self.assertEqual([m['role'] for m in messages], ['system', 'user'])
        self.assertIsNone(trim_context(messages))

    def test_trim_returns_none_for_messages_without_context_data(self):
        self.assertIsNone(trim_context([dict(role='system', content='plain prompt'), dict(role='user', content='Question')]))
        self.assertIsNone(trim_context([dict(role='system', content='Role' + CONTEXT_MARKER + json.dumps({'planner':{}})),
                                        dict(role='user', content=MATERIAL_MARKER + json.dumps({'person':{}, 'local_documents':[]}) + QUESTION_MARKER + 'Q')]))
        self.assertIsNone(trim_context([dict(role='system', content='Role' + CONTEXT_MARKER + 'not json')]))
        # Markers typed by the user carry no context blocks; a block in the wrong role is not trimmed either.
        self.assertIsNone(trim_context([dict(role='user', content='Role' + CONTEXT_MARKER + json.dumps({'planner':{'a':1}})),
                                        dict(role='system', content=MATERIAL_MARKER + json.dumps({'local_documents':[1]}))]))

    def test_reply_budget_is_clamped_to_half_the_context(self):
        self.model.context = 1024
        self.model.process = type('Running', (), {'poll':lambda _: None})(); self.model.url = 'http://127.0.0.1:1'
        body = json.dumps({'choices':[{'message':{'content':'Ready.<think>unfinished reasoning'}}]}).encode()
        with patch.object(self.model, '_post', side_effect=self.tokenizer([100])), \
             patch('urllib.request.urlopen', return_value=io.BytesIO(body)) as request:
            answer = self.model.chat([dict(role='user', content='Hi')], max_tokens=600)
        self.assertEqual(json.loads(request.call_args.args[0].data)['max_tokens'], 512)
        # An unterminated reasoning block is never shown as part of the answer.
        self.assertEqual(answer, 'Ready.')


class ModelStartTests(unittest.TestCase):
    def test_port_race_is_retried_once_and_log_closed_on_spawn_failure(self):
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            data = Path(folder); model = LocalModel()
            gguf = data / 'm.gguf'; gguf.write_bytes(b'x')
            ports = []
            class Process:
                def __init__(self, args, stdout, **_):
                    ports.append(args[args.index('--port') + 1]); self.stdout = stdout
                    if len(ports) == 1: stdout.write("couldn't bind HTTP server socket, hostname: 127.0.0.1, port: " + ports[-1]); stdout.flush()
                def poll(self): return 1 if len(ports) == 1 else None
                def terminate(self): pass
                def wait(self, timeout=None): pass
            healthy = type('Response', (), {'status':200, '__enter__':lambda s: s, '__exit__':lambda *_: None})()
            with patch('jarviss.model.DATA', data), patch('jarviss.model.find_server', return_value=gguf), \
                 patch('jarviss.model.subprocess.Popen', Process), patch('urllib.request.urlopen', return_value=healthy):
                model.start(gguf)
            self.assertEqual(len(ports), 2)
            self.assertNotEqual(ports[0], ports[1])
            self.assertIn("couldn't bind", (data / 'model.log').read_text())
            model.log.close()
            with patch('jarviss.model.DATA', data), patch('jarviss.model.find_server', return_value=gguf), \
                 patch('jarviss.model.subprocess.Popen', side_effect=OSError('no exec')):
                with self.assertRaises(OSError): model.start(gguf)
            self.assertIsNone(model.log)


if __name__ == '__main__':
    unittest.main()
