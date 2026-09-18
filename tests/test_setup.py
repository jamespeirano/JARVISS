import hashlib
import ssl
import tempfile
import threading
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import Mock, patch
from jarviss.hardware import recommend, GIB
from jarviss.setup import Setup, SetupPaused, model_catalog, prepare_model, choose, TRANSIENT_BYTES
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
        self.service.model.start.assert_called_once()
        self.assertTrue(self.service.ready)
        self.assertEqual(self.service.settings['model_id'],'compact')

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
        with patch('jarviss.setup.inspect',return_value=self.hardware()),patch('jarviss.setup.prepare_runtime'),patch('jarviss.setup.prepare_model',return_value=self.root/'new.gguf'),patch('jarviss.setup.prepare_voice'),patch('jarviss.setup.prepare_routing'),patch('jarviss.us_routing.USRouter',return_value=self.service.us_router), \
             patch('jarviss.setup.verify_us',return_value=[]) as verify,patch('jarviss.setup.prepare_basemap') as basemap:
            result=self.setup.run('compact')
        verify.assert_called_once_with(self.setup.progress);basemap.assert_not_called();self.service.swap_map.assert_not_called()
        self.assertEqual(result['run']['status'],'ready');self.assertTrue(self.service.ready)
        self.assertEqual(self.service.settings['model_id'],'compact')
        self.service.model.start.assert_called_once_with(self.root/'new.gguf','auto',context=choose('compact')['context'])
        self.assertFalse((self.root/'conversation.json').exists())

    def installed(self):
        self.service.model.chat.return_value='Ready'
        self.service.archive=Mock(path=self.root/'local-maps'/'us-z15.pmtiles')
        self.service.us_router.status.return_value={'ready':True};self.service.state.return_value={'voiceReady':True}
        return [patch('jarviss.setup.inspect',return_value=self.hardware()),patch('jarviss.setup.prepare_runtime'),patch('jarviss.setup.prepare_model',return_value=self.root/'new.gguf'),
                patch('jarviss.setup.prepare_voice'),patch('jarviss.setup.prepare_routing'),patch('jarviss.us_routing.USRouter',return_value=self.service.us_router)]

    def test_check_setup_replaces_a_map_that_fails_verification(self):
        patches=self.installed();archive=self.root/'local-maps'/'us-z15.pmtiles'
        def clear(**fields):
            self.assertEqual((fields['archive'],fields['location_index']),(None,None));self.assertIn('failed verification',fields['archive_error']);self.service.archive=None
        self.service.swap_map.side_effect=clear
        self.service.command.side_effect=lambda method,args:setattr(self.service,'archive',Mock(path=archive))
        with patch('jarviss.setup.basemap_path',return_value=archive),patch('jarviss.setup.verify_us',return_value=[archive]) as verify, \
             patch('jarviss.setup.prepare_basemap',return_value=archive) as basemap:
            for p in patches:p.start();self.addCleanup(p.stop)
            result=self.setup.run('compact')
        verify.assert_called_once();basemap.assert_called_once_with(self.setup.progress,cancel=self.setup.cancel)
        self.service.command.assert_called_once_with('import_basemap',{'path':str(archive)})
        self.assertEqual(result['run']['status'],'ready')

    def test_first_run_never_hashes_map_data(self):
        patches=self.installed();self.service.archive=None
        with patch('jarviss.setup.verify_us') as verify,patch('jarviss.setup.prepare_basemap',return_value=self.root/'map.pmtiles'):
            for p in patches:p.start();self.addCleanup(p.stop)
            self.setup.run('compact')
        verify.assert_not_called()

    def test_pause_during_the_map_extract_says_it_must_restart(self):
        patches=self.installed();self.service.archive=None
        with patch('jarviss.setup.prepare_basemap',side_effect=SetupPaused(note=' The unfinished US map must restart; other files are kept.')):
            for p in patches:p.start();self.addCleanup(p.stop)
            result=self.setup.run('compact')
        self.assertEqual(result['run']['status'],'paused');self.assertEqual(result['run']['detail'],'Setup paused. Continue to reuse downloaded files. The unfinished US map must restart; other files are kept.')

    def test_failed_validation_restarts_the_previous_model(self):
        self.service.ready=True
        self.service.settings={'model':'previous.gguf','model_id':'balanced','gpu_layers':'auto','model_context':4096}
        self.service.model.chat.return_value=''
        with patch('jarviss.setup.inspect',return_value=self.hardware()),patch('jarviss.setup.prepare_runtime'),patch('jarviss.setup.prepare_model',return_value=self.root/'new.gguf'):
            with self.assertRaisesRegex(ValueError,'did not produce'):self.setup.run('compact',only_model=True)
        starts=self.service.model.start.call_args_list
        self.assertEqual(len(starts),2);self.assertEqual(starts[1].args[0].name,'previous.gguf');self.assertEqual(starts[1].kwargs,{'context':4096})
        self.assertTrue(self.service.ready)
        self.assertEqual(self.service.settings['model_id'],'balanced')
        self.assertEqual(read_json(self.root/'settings.json',{})['model_id'],'balanced')
        self.assertEqual(self.setup.snapshot()['status'],'failed')

    def test_restart_failure_is_reported_and_leaves_chat_stopped(self):
        self.service.ready=True;self.service.settings={'model':'previous.gguf','model_id':'balanced'}
        self.service.model.start.side_effect=[RuntimeError('Not enough memory'),RuntimeError('Port busy')]
        with patch('jarviss.setup.inspect',return_value=self.hardware()),patch('jarviss.setup.prepare_runtime'),patch('jarviss.setup.prepare_model',return_value=self.root/'new.gguf'),              patch('jarviss.setup.traceback.print_exc'):
            with self.assertRaisesRegex(RuntimeError,'Not enough memory'):self.setup.run('compact',only_model=True)
        self.assertFalse(self.service.ready)
        self.assertIn('did not restart: Port busy',self.setup.snapshot()['detail'])

    def test_download_failure_leaves_a_running_model_alone(self):
        self.service.ready=True;self.service.settings={'model':'previous.gguf','model_id':'balanced'}
        with patch('jarviss.setup.inspect',return_value=self.hardware()),patch('jarviss.setup.prepare_runtime'),patch('jarviss.setup.prepare_model',side_effect=OSError('Connection lost')):
            with self.assertRaises(OSError):self.setup.run('compact',only_model=True)
        self.service.model.stop.assert_not_called();self.service.model.start.assert_not_called()
        self.assertTrue(self.service.ready)
        self.assertEqual(read_json(self.root/'settings.json',{})['model'],'previous.gguf')

    def test_pause_while_testing_restarts_the_previous_model(self):
        self.service.ready=True;self.service.settings={'model':'previous.gguf','model_id':'balanced','model_context':4096}
        self.service.model.start.side_effect=lambda *a,**k: self.cancel_after_first_start()
        with patch('jarviss.setup.inspect',return_value=self.hardware()),patch('jarviss.setup.prepare_runtime'),patch('jarviss.setup.prepare_model',return_value=self.root/'new.gguf'):
            result=self.setup.run('compact',only_model=True)
        self.assertEqual(result['run']['status'],'paused')
        self.assertEqual(self.service.model.start.call_args_list[-1].args[0].name,'previous.gguf')
        self.assertTrue(self.service.ready);self.assertEqual(self.service.settings['model_id'],'balanced')

    def cancel_after_first_start(self):
        if not self.cancel_seen:self.cancel_seen=True;self.setup.cancel.set()
    cancel_seen=False

    def test_summary_failure_after_validation_keeps_the_model_ready(self):
        self.service.model.chat.return_value='Ready'
        with patch('jarviss.setup.inspect',return_value=self.hardware()):
            real=self.setup.plan('compact')
        with patch('jarviss.setup.inspect',return_value=self.hardware()),patch('jarviss.setup.prepare_runtime'),patch('jarviss.setup.prepare_model',return_value=self.root/'new.gguf'), \
             patch.object(self.setup,'plan',side_effect=[real,RuntimeError('Hardware probe failed')]):
            with self.assertRaisesRegex(RuntimeError,'summary could not be refreshed: Hardware probe failed'):self.setup.run('compact',only_model=True)
        self.assertEqual(self.setup.snapshot()['status'],'model_ready')
        self.assertTrue(self.service.ready);self.service.model.stop.assert_called_once()
        self.assertEqual(self.service.settings['model_id'],'compact')
        self.assertEqual(read_json(self.root/'settings.json',{})['model_id'],'compact')

    def test_catalog_names_carry_no_abliterated_label(self):
        for m in model_catalog(): self.assertNotIn('bliterated', m['name'])

    def test_progress_percent_is_weighted_by_bytes_and_eta_covers_the_whole_run(self):
        events=[]
        self.service.setup_progress.side_effect=lambda: events.append(dict(self.setup.info))
        self.service.model.chat.return_value='Ready'
        model=choose('compact');archive=self.root/'map.pmtiles'
        def download_model(_id,progress):
            progress('AI model · 1.7 GB / 3.4 GB · 50% · 10.0 MB/s · about 3 min left');return self.root/'new.gguf'
        def basemap(progress,cancel=None):
            progress('US map · 10.5 GB / 21.0 GB · 50% · 20.0 MB/s');return archive
        def routing(progress):
            progress('US directions: 1 / 4 files saved');progress('US directions · Walking directions · 1 MB / 2 MB · 50%');progress('US directions: 4 / 4 files saved')
        with patch('jarviss.setup.inspect',return_value=self.hardware()),patch('jarviss.setup.prepare_runtime',side_effect=lambda p:p('Model engine · 5 MB / 10 MB · 50%')), \
             patch('jarviss.setup.prepare_model',side_effect=download_model),patch('jarviss.setup.prepare_voice',side_effect=lambda p:p('Voice engine · 100 MB / 200 MB · 50%')), \
             patch('jarviss.setup.prepare_basemap',side_effect=basemap),patch('jarviss.setup.prepare_routing',side_effect=routing),patch('jarviss.us_routing.USRouter',return_value=self.service.us_router):
            result=self.setup.run('compact')
        total=model['bytes']+520_000_000+21_000_000_000+2_000_000_000
        by_detail={e['detail']:e for e in events}
        self.assertEqual(by_detail['Model engine · 5 MB / 10 MB · 50%']['percent'],0)
        self.assertEqual(by_detail['AI model · 1.7 GB / 3.4 GB · 50% · 10.0 MB/s · about 3 min left']['percent'],int(50*model['bytes']/total))
        self.assertEqual(by_detail['AI model · 1.7 GB / 3.4 GB · 50% · 10.0 MB/s · about 3 min left']['eta'],f'about {(round((total-model["bytes"]/2)/1e7)+59)//60} min left')
        self.assertEqual(by_detail['Voice engine · 100 MB / 200 MB · 50%']['percent'],int(100*(model['bytes']+260_000_000)/total))
        self.assertEqual(by_detail['US map · 10.5 GB / 21.0 GB · 50% · 20.0 MB/s']['percent'],int(100*(model['bytes']+520_000_000+10_500_000_000)/total))
        self.assertEqual(by_detail['US directions: 1 / 4 files saved']['percent'],int(100*(total-1_500_000_000)/total))
        self.assertEqual(by_detail['US directions · Walking directions · 1 MB / 2 MB · 50%']['percent'],int(100*(total-1_500_000_000)/total))
        self.assertEqual(by_detail['US directions: 4 / 4 files saved']['percent'],100)
        self.assertEqual((result['run']['percent'],result['run']['eta'],result['run']['skipped']),(100,'',False))
        percents=[e['percent'] for e in events]
        self.assertEqual(percents,sorted(percents))

    def test_chat_only_run_counts_only_the_model_and_skip_is_forgotten(self):
        self.service.model.chat.return_value='Ready'
        self.setup.save(skipped=True)
        self.assertTrue(Setup(self.service).snapshot()['skipped'])
        with patch('jarviss.setup.inspect',return_value=self.hardware()),patch('jarviss.setup.prepare_runtime'), \
             patch('jarviss.setup.prepare_model',side_effect=lambda _id,progress:(progress('AI model · 1.7 GB / 3.4 GB · 50%'),self.root/'new.gguf')[1]), \
             patch('jarviss.setup.prepare_voice') as voice:
            result=self.setup.run('compact',only_model=True)
        voice.assert_not_called()
        self.assertEqual(self.setup.weights,{'model':choose('compact')['bytes']})
        self.assertEqual((result['run']['status'],result['run']['percent'],result['run']['skipped']),('model_ready',100,False))
        self.assertFalse(read_json(self.root/'setup.json',{})['skipped'])
        self.assertEqual(result['component_bytes']['model'],choose('compact')['bytes'])

    def test_missing_selection_and_damaged_catalog_are_reported_as_advice(self):
        with self.assertRaisesRegex(ValueError,'Choose a model'):self.setup.run(None)
        for content in ('{}','[]','{"models":[]}'):
            with self.subTest(content=content):
                (self.root/'model-catalog.json').write_text(content)
                with patch('jarviss.setup.RESOURCES',self.root),self.assertRaisesRegex(RuntimeError,'model catalog'):model_catalog()
        with patch('jarviss.setup.RESOURCES',self.root/'missing'),self.assertRaisesRegex(RuntimeError,'model catalog'):model_catalog()

    def test_required_space_includes_runtime_and_voice_extraction(self):
        with patch('jarviss.setup.inspect',return_value=self.hardware()):
            plan=self.setup.plan('compact')
            self.assertEqual(plan['required_bytes']-plan['download_bytes'],2*GIB+TRANSIENT_BYTES)
            self.service.state.return_value={'voiceReady':True}
            with patch('jarviss.setup.find_server',return_value=Path('llama-server')):
                plan=self.setup.plan('compact')
            self.assertEqual(plan['required_bytes']-plan['download_bytes'],2*GIB)

    def test_low_disk_message_uses_decimal_gigabytes(self):
        hw=self.hardware();hw['disk']=GIB
        with patch('jarviss.setup.inspect',return_value=hw):
            needed=self.setup.plan('advanced')['required_bytes']
            with self.assertRaisesRegex(ValueError,f'Free at least {needed/1e9:.1f} GB'):self.setup.run('advanced')

    def test_pause_has_a_default_message(self):
        self.assertEqual(str(SetupPaused()),'Download paused. Continue from setup to reuse saved files.')
        self.assertIsInstance(SetupPaused(),RuntimeError)


if __name__=='__main__':unittest.main()
