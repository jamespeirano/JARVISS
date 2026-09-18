import io
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
import jarviss.service as module
from jarviss.service import Service, main
from jarviss.setup import SetupPaused
from jarviss.storage import write_json, read_json


class OperationStateTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.patches=[patch('jarviss.service.DATA',self.root),patch('jarviss.service.ROOT',self.root),patch('jarviss.setup.DATA',self.root),
                      patch('jarviss.service.model_path',side_effect=lambda p:self.root/p),patch('jarviss.service.emit')]
        for p in self.patches:p.start()
        self.service=Service()

    def tearDown(self):
        self.service.close()
        for p in reversed(self.patches):p.stop()
        self.tmp.cleanup()

    def test_download_state_survives_read_and_rejects_conflicting_start(self):
        started=threading.Event();release=threading.Event();failures=[]
        def download(progress):
            progress('kokoro-v1.0.onnx: 60 MB / 310 MB');started.set()
            if not release.wait(5):raise RuntimeError('Test did not release download')
        def run():
            try:self.service.command('download_model',{})
            except Exception as e:failures.append(e)
        with patch('jarviss.service.prepare_qwen',download):
            worker=threading.Thread(target=run);worker.start()
            try:
                self.assertTrue(started.wait(3))
                state=self.service.command('state',{})
                self.assertEqual(state['operation']['method'],'download_model')
                self.assertIn('kokoro',state['operation']['progress'])
                self.assertFalse(state['modelAvailable'])
                with self.assertRaisesRegex(RuntimeError,'Preparing model and voice'):
                    self.service.command('start_model',{})
                self.assertEqual(self.service.state()['operation'],state['operation'])
            finally:release.set();worker.join(5)
        self.assertFalse(failures)
        self.assertIsNone(self.service.state()['operation'])
        self.assertFalse(self.service.lock.locked())

    def test_stop_model_ends_the_session_and_reports_not_started(self):
        self.service.ready=True
        with patch.object(self.service.model,'stop') as stop,patch.object(self.service.voice,'pause') as pause:
            self.assertTrue(self.service.command('stop_model',{}))
            stop.assert_called_once();pause.assert_called_once()
        self.assertFalse(self.service.ready);self.assertFalse(self.service.lock.locked())
        self.assertIsNone(self.service.state()['operation'])

    def test_no_model_selection_does_not_stop_an_existing_model(self):
        with patch.object(self.service.model,'stop') as stop,patch.object(self.service.model,'start') as start:
            with self.assertRaisesRegex(ValueError,'Choose a GGUF'):
                self.service.command('start_model',{})
            stop.assert_not_called();start.assert_not_called()
        self.assertIsNone(self.service.state()['operation'])

    def test_failed_preparation_clears_operation_and_allows_retry(self):
        with patch('jarviss.service.prepare_voice',side_effect=OSError('Download unavailable')):
            with self.assertRaises(OSError):self.service.command('download_voice',{})
        self.assertIsNone(self.service.state()['operation'])
        self.assertFalse(self.service.lock.locked())
        with patch('jarviss.service.prepare_voice'):
            self.assertTrue(self.service.command('download_voice',{}))

    def test_position_change_rejects_route_computed_from_old_start(self):
        from unittest.mock import Mock
        started=threading.Event();release=threading.Event();failures=[]
        self.service.command('set_map_position',{'lat':30.27,'lon':-97.74})
        def route(*_):
            started.set()
            if not release.wait(5):raise RuntimeError('Test did not release routing')
            return {'distance_m':100,'steps':[]}
        catalog=Mock();catalog.route.side_effect=route
        def run():
            try:self.service.command('route',{'point':[30.28,-97.73]})
            except Exception as e:failures.append(e)
        with patch.object(self.service,'catalog',return_value=catalog):
            worker=threading.Thread(target=run);worker.start()
            try:
                self.assertTrue(started.wait(3))
                self.service.command('set_map_position',{'lat':40.7,'lon':-74})
            finally:release.set();worker.join(5)
        self.assertEqual(len(failures),1)
        self.assertIn('position changed',str(failures[0]))
        self.assertIsNone(self.service.route)
        self.assertIsNone(self.service.operation)

    def events(self,kind):
        return [c.args[0]['data'] for c in module.emit.call_args_list if c.args[0].get('event')==kind]

    def wait_for(self,condition):
        deadline=time.monotonic()+3
        while not condition() and time.monotonic()<deadline:time.sleep(.01)
        self.assertTrue(condition())

    def test_emit_failure_still_releases_the_lock(self):
        module.emit.side_effect=[OSError('Broken pipe')]+[None]*50
        with self.assertRaises(OSError):self.service.command('clear',{})
        self.assertFalse(self.service.lock.locked());self.assertIsNone(self.service.operation)
        module.emit.side_effect=None
        self.assertTrue(self.service.command('clear',{}))

    def test_late_progress_never_republishes_a_finished_operation(self):
        with patch('jarviss.service.prepare_voice'):self.service.command('download_voice',{})
        module.emit.reset_mock()
        self.service.progress('kokoro-v1.0.onnx: 310 MB / 310 MB')
        self.assertEqual(self.events('operation'),[]);self.assertIsNone(self.service.operation)
        self.assertEqual(len(self.events('progress')),1)

    def test_us_map_download_receives_the_setup_cancel_flag(self):
        seen=[]
        def prepare(progress,cancel=None):seen.append(cancel);raise OSError('offline')
        self.service.setup.cancel.set()
        with patch('jarviss.service.prepare_us',prepare),self.assertRaises(OSError):self.service.command('download_us_maps',{})
        self.assertEqual(seen,[self.service.setup.cancel]);self.assertFalse(self.service.setup.cancel.is_set())

    def test_paused_us_map_download_reports_the_pause_and_leaves_setup_untouched(self):
        def prepare(progress,cancel=None):raise SetupPaused(note=' The unfinished US map must restart; other files are kept.')
        with patch('jarviss.service.prepare_us',prepare),self.assertRaisesRegex(SetupPaused,r'^Download paused\..*must restart'):
            self.service.command('download_us_maps',{})
        self.assertFalse((self.root/'setup.json').exists());self.assertEqual(self.service.setup.snapshot(),{'skipped':False,'percent':0,'eta':''})
        self.assertIsNone(self.service.operation);self.assertFalse(self.service.lock.locked())
        self.assertIsNone(self.events('operation')[-1])

    def test_lock_refusal_reads_the_operation_once(self):
        service=self.service
        class Vanishing(dict):
            def __len__(self):service.operation=None;return 1  # The running operation finishes between the truthiness test and the label read.
        self.service.lock.acquire()
        try:
            self.service.operation=Vanishing(label='Thinking')
            with self.assertRaisesRegex(RuntimeError,'Thinking. Wait for it'):self.service.command('chat',{'text':'hi'})
        finally:self.service.lock.release();self.service.operation=None

    def test_downloaded_settings_merge_with_concurrent_edits(self):
        def download(progress):
            write_json(self.root/'settings.json',{'model':'models/new.gguf','model_id':'compact'})
            self.service.settings['voice_name']='bf_emma'
        with patch('jarviss.service.prepare_qwen',download):self.service.command('download_model',{})
        self.assertEqual(self.service.settings['model'],'models/new.gguf')
        self.assertEqual(self.service.settings['voice_name'],'bf_emma');self.assertIn('system_prompt',self.service.settings)

    def test_typed_questions_keep_text_budgets_while_the_microphone_is_on(self):
        self.service.ready=True;self.service.voice.enabled.set();self.addCleanup(self.service.voice.enabled.clear)
        self.service.settings.update(voice_max_tokens=180,text_max_tokens=900,voice_max_sentences=3)
        budgets=[]
        def chat(payload,on_sentence=None,max_tokens=None,max_sentences=None):
            budgets.append((max_tokens,max_sentences))
            if on_sentence:on_sentence('Spoken.')
            return 'Spoken.'
        with patch.object(self.service.model,'chat',side_effect=chat),patch.object(self.service.voice,'speak') as speak, \
             patch('jarviss.service.messages',return_value=[]) as prompt:
            self.service.command('chat',{'text':'Typed question'})
            self.assertEqual(budgets[-1],(900,None));self.assertFalse(prompt.call_args.args[6])
            speak.assert_called_with('Spoken.')
            self.service.command('chat',{'text':'Heard question','spoken':True})
            self.assertEqual(budgets[-1],(180,3));self.assertTrue(prompt.call_args.args[6])

    def test_spoken_sentences_survive_a_failed_stream(self):
        self.service.ready=True;self.service.voice.enabled.set();self.addCleanup(self.service.voice.enabled.clear)
        def chat(payload,on_sentence=None,**_):
            on_sentence('Move to high ground.');raise RuntimeError('Model connection lost')
        with patch.object(self.service.model,'chat',side_effect=chat),patch.object(self.service.voice,'speak'),patch('jarviss.service.messages',return_value=[]):
            with self.assertRaisesRegex(RuntimeError,'connection lost'):self.service.command('chat',{'text':'Flood coming'})
        last=self.service.history[-1]
        self.assertEqual((last['role'],last['content'],last['truncated']),('assistant','Move to high ground.',True))
        self.assertEqual(read_json(self.root/'conversation.json',[]),self.service.history)
        answer=self.events('answer')[-1]
        self.assertEqual(answer['text'],'Move to high ground.');self.assertTrue(answer['truncated'])
        self.assertIsNone(self.service.operation);self.assertFalse(self.service.lock.locked())

    def test_heard_speech_does_not_clear_busy_owned_by_a_typed_chat(self):
        self.service.lock.acquire();self.service.voice.busy.set()
        try:
            self.service.heard('hello')
            self.wait_for(lambda:any('Wait for it' in e for e in self.events('error')))
            self.assertTrue(self.service.voice.busy.is_set())
        finally:self.service.lock.release()
        self.service.heard('   ')
        self.wait_for(lambda:any('Enter a question' in e for e in self.events('error')))
        self.assertFalse(self.service.voice.busy.is_set())

    def test_heard_questions_use_hands_free_budgets(self):
        self.service.ready=True;budgets=[]
        def chat(payload,on_sentence=None,max_tokens=None,max_sentences=None):budgets.append((max_tokens,max_sentences));return 'Yes.'
        with patch.object(self.service.model,'chat',side_effect=chat),patch('jarviss.service.messages',return_value=[]):
            self.service.heard('is it safe')
            self.wait_for(lambda:bool(budgets))
            self.wait_for(lambda:not self.service.lock.locked())
        self.assertEqual(budgets,[(180,3)])

    def test_invalid_arguments_are_reported_as_advice(self):
        cases=[('start_model',{'layers':'abc'},'whole number'),('start_model',{'layers':float('nan')},'whole number'),
               ('audio_settings',{'input_device':'zz'},'audio device'),
               ('import_map',{},'Choose a map file'),('import_map',{'path':str(self.root/'missing.json')},'not found: missing.json'),
               ('import_basemap',{'path':' '},'Choose a map file'),('import_basemap',{'path':str(self.root/'gone.pmtiles')},'not found'),
               ('import_document',{},'Choose a document file'),('import_document',{'path':str(self.root/'gone.pdf')},'not found'),
               ('save_profile',{'situation':{'a':1}},'must be text'),('save_profile',{'supplies':['x']},'must be text')]
        with patch('jarviss.service.devices',return_value=[]),patch.object(self.service.model,'start') as start:
            for method,args,message in cases:
                with self.subTest(method=method,args=args),self.assertRaisesRegex(ValueError,message):self.service.command(method,args)
            start.assert_not_called()
        self.assertFalse(self.service.lock.locked());self.assertFalse((self.root/'profile.json').exists())
        self.service.command('save_profile',{'situation':None,'supplies':'tent'})
        self.assertEqual(self.service.profile['situation'],'')


class FakeStream(io.StringIO):
    def reconfigure(self,**_):pass


class MainLoopTests(unittest.TestCase):
    def test_malformed_lines_are_skipped_and_defects_are_named(self):
        def command(method,args):
            if method=='chat':raise ValueError()
            if method=='nearest':raise KeyError('id')
            if method=='download_us_maps':raise SetupPaused()
            return {'ok':method}
        service=Mock();service.command.side_effect=command
        lines=['not json\n','{"id":1,"method":"chat","args":{}}\n','{"id":2,"method":"nearest"}\n','{"id":3,"method":"state"}\n','{"id":4,"method":"download_us_maps"}\n','{"method":"shutdown"}\n']
        with patch('jarviss.service.Service',return_value=service),patch('jarviss.service.emit') as emit, \
             patch('jarviss.service.traceback.print_exc'),patch('sys.stdin',FakeStream(''.join(lines))),patch('sys.stdout',FakeStream()):
            main()
            deadline=time.monotonic()+3
            while len(emit.call_args_list)<4 and time.monotonic()<deadline:time.sleep(.01)
        replies={c.args[0]['id']:c.args[0] for c in emit.call_args_list}
        self.assertEqual(replies[1]['error'],'ValueError')
        self.assertEqual(replies[4]['error'],'Download paused. Continue from setup to reuse saved files.')
        self.assertEqual(replies[2]['error'],'Unexpected KeyError in nearest. Details are in service.log.')
        self.assertEqual(replies[3]['result'],{'ok':'state'})
        service.close.assert_called_once()


if __name__=='__main__':unittest.main()
