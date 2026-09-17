import hashlib
import ssl
import tempfile
import threading
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import Mock, patch
from jarviss.hardware import recommend, GIB
from jarviss.setup import Setup, SetupPaused, model_catalog, prepare_model, choose
from jarviss.storage import read_json


class SetupTests(unittest.TestCase):
    def hardware(self, memory=36, available=30, gpu=0, unified=True):
        return {'system':'Darwin' if unified else 'Windows', 'arch':'arm64' if unified else 'AMD64',
                'memory':memory*GIB, 'available':available*GIB, 'disk':100*GIB, 'cores':8,
                'unified':unified, 'gpus':[{'name':'Test GPU','available':gpu*GIB,'total':gpu*GIB}] if gpu else [], 'accelerated':unified or bool(gpu)}

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.patches=[patch('jarviss.setup.DATA',self.root),patch('jarviss.setup.MODELS',self.root/'models'),patch('jarviss.setup.ROOT',self.root)]
        for p in self.patches:p.start()
        self.service=Mock();self.service.model.process=None;self.service.model.allocated_memory=0;self.service.archive=None
        self.service.us_router.status.return_value={'ready':False};self.service.state.return_value={'voiceReady':False}
        self.service.settings={'model':'previous.gguf'};self.service.ready=False
        self.setup=Setup(self.service)

    def tearDown(self):
        for p in reversed(self.patches):p.stop()
        self.temp.cleanup()

    def test_current_models_are_pinned_and_no_qwen_35(self):
        for m in model_catalog():
            self.assertNotIn('3.5',m['name']);self.assertIn('abliterated',m['filename'].lower())
            self.assertEqual(len(m['sha256']),64);self.assertEqual(len(m['revision']),40)
            self.assertIn(m['revision'],m['url'])
        with self.assertRaises(ValueError):choose('../../anything')

    def test_recommendations_use_available_memory_and_acceleration(self):
        models=model_catalog()
        for hw,expected in [(self.hardware(), 'advanced'),(self.hardware(16,12),'balanced'),
                            (self.hardware(12,8),'compact'),(self.hardware(8,4),None),
                            (self.hardware(64,50,unified=False),'balanced'),
                            (self.hardware(16,10,24,False),'advanced'),
                            (self.hardware(64,5),None)]:
            with self.subTest(hw=hw):self.assertEqual(recommend(models,hw)[1],expected)

    def test_download_validates_pinned_size_and_hash(self):
        model=choose('compact')
        with patch('jarviss.setup.download_file') as fetch:
            path=prepare_model('compact',lambda _:None)
            self.assertEqual(fetch.call_args.args[3:],(model['bytes'],model['sha256']))
            self.assertEqual(read_json(path.with_suffix('.source.json'),{})['revision'],model['revision'])

    def test_running_model_is_not_rejected_for_its_own_gpu_memory(self):
        self.service.model.process=Mock(pid=123)
        self.service.model.process.poll.return_value=None
        self.service.settings['model_id']='advanced';self.service.ready=True
        with patch('jarviss.setup.inspect',return_value=self.hardware(36,4)):
            plan=self.setup.plan('advanced')
        self.assertEqual(plan['recommended'],'advanced')
        self.assertTrue(next(r for r in plan['models'] if r['id']=='advanced')['fits'])

    def test_low_disk_stops_before_any_download(self):
        hw=self.hardware();hw['disk']=GIB
        with patch('jarviss.setup.inspect',return_value=hw),patch('jarviss.setup.prepare_runtime') as start:
            with self.assertRaisesRegex(ValueError,'Free at least'):self.setup.run('advanced')
            start.assert_not_called()

    def test_pause_survives_restart_and_releases_work(self):
        def download(_id, progress):
            self.setup.cancel.set();progress('Part downloaded')
        with patch('jarviss.setup.inspect',return_value=self.hardware()),patch('jarviss.setup.prepare_runtime'),patch('jarviss.setup.prepare_model',side_effect=download):
            result=self.setup.run('compact')
        self.assertEqual(result['run']['status'],'paused');self.service.model.start.assert_not_called()
        self.assertEqual(Setup(self.service).snapshot()['status'],'paused')

    def test_validation_failure_preserves_previous_selection(self):
        self.service.model.start.side_effect=RuntimeError('Not enough memory')
        with patch('jarviss.setup.inspect',return_value=self.hardware()),patch('jarviss.setup.prepare_runtime'),patch('jarviss.setup.prepare_model',return_value=self.root/'new.gguf'):
            with self.assertRaisesRegex(RuntimeError,'Not enough memory'):self.setup.run('compact',only_model=True)
        self.assertEqual(self.service.settings['model'],'previous.gguf')
        self.assertEqual(self.setup.snapshot()['status'],'failed')

    def test_pause_during_routing_keeps_completed_map_and_remaining_space(self):
        hardware=self.hardware();hardware['disk']=30*GIB
        archive=self.root/'map.pmtiles';model=choose('compact')
        def prepare_model(_id,progress):
            path=self.root/'models'/model['filename'];path.parent.mkdir()
            with path.open('wb') as f:f.truncate(model['bytes'])
            return path
        def import_map(method,args):
            self.assertEqual((method,args),('import_basemap',{'path':str(archive)}))
            self.service.archive=Mock(path=archive)
            hardware['disk']=8*GIB
        def pause(progress):
            self.setup.cancel.set();progress('Partial routing download')
        self.service.command.side_effect=import_map
        self.service.state.return_value={'voiceReady':True}
        with patch('jarviss.setup.inspect',return_value=hardware), \
             patch('jarviss.setup.prepare_runtime'), \
             patch('jarviss.setup.prepare_model',side_effect=prepare_model), \
             patch('jarviss.setup.prepare_voice'), \
             patch('jarviss.setup.prepare_basemap',return_value=archive), \
             patch('jarviss.setup.prepare_routing',side_effect=pause):
            result=self.setup.run('compact')
        self.assertEqual(result['run']['status'],'paused')
        self.assertTrue(result['components']['map'])
        self.assertEqual(result['download_bytes'],2_000_000_000)
        self.assertTrue(result['space_ok'])
        self.service.model.start.assert_not_called()

    def test_certificate_failure_has_a_retry_message_and_keeps_setup_incomplete(self):
        failure=urllib.error.URLError(ssl.SSLCertVerificationError('unable to get local issuer certificate'))
        with patch('jarviss.setup.inspect',return_value=self.hardware()),patch('jarviss.setup.prepare_runtime'),patch('jarviss.setup.prepare_model',side_effect=failure):
            with self.assertRaisesRegex(RuntimeError,'Could not verify the download server'):
                self.setup.run('compact')
        self.assertEqual(Setup(self.service).snapshot()['status'],'failed')
        self.assertNotIn('_ssl',self.setup.snapshot()['error'])
        self.service.model.start.assert_not_called()

    def test_complete_setup_checks_response_without_chat_history(self):
        self.service.model.chat.return_value='Ready'
        self.service.archive=Mock(path=self.root/'map.pmtiles')
        self.service.us_router.status.return_value={'ready':True};self.service.state.return_value={'voiceReady':True}
        with patch('jarviss.setup.inspect',return_value=self.hardware()),patch('jarviss.setup.prepare_runtime'),patch('jarviss.setup.prepare_model',return_value=self.root/'new.gguf'),patch('jarviss.setup.prepare_voice'),patch('jarviss.setup.prepare_routing'),patch('jarviss.us_routing.USRouter',return_value=self.service.us_router):
            result=self.setup.run('compact')
        self.assertEqual(result['run']['status'],'ready');self.assertTrue(self.service.ready)
        self.assertEqual(self.service.settings['model_id'],'compact')
        self.service.model.start.assert_called_once_with(self.root/'new.gguf','auto',context=4096)
        self.assertFalse((self.root/'conversation.json').exists())


if __name__=='__main__':unittest.main()
