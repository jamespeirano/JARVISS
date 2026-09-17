"""Regressions reported by the physical Windows v0.2.3 acceptance test."""
import tempfile
import threading
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import Mock, patch
from jarviss.service import Service
from jarviss.setup import choose
from jarviss.storage import write_json
from tests.test_core import fixture


class WindowsUXTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        for module in ('service', 'setup'):
            for name, value in [('DATA', self.root), ('ROOT', self.root), ('MODELS', self.root/'models')]:
                self.stack.enter_context(patch(f'jarviss.{module}.{name}', value))
        self.stack.enter_context(patch('jarviss.service.model_path', side_effect=lambda p: self.root/p))
        self.events = self.stack.enter_context(patch('jarviss.service.emit'))
        self.service = Service()
        self.addCleanup(self.stack.close)
        self.addCleanup(self.service.close)

    def test_missing_map_is_not_reported_as_no_matching_town(self):
        for args in ({'query':'Austin'}, {'query':'Congress Ave', 'near':[30.27,-97.74]}):
            with self.subTest(args=args), self.assertRaisesRegex(ValueError, 'map.*not ready'):
                self.service.command('search_locations', args)

    def test_map_click_keeps_destination_name_and_validates_coordinates(self):
        area = self.root/'area-input.json';write_json(area, fixture())
        self.service.command('import_map', {'path':str(area)})
        self.service.command('set_map_position', {'lat':40,'lon':-74})
        for name, expected in [('Quattro Gatti Ristorante','Quattro Gatti Ristorante'), ('  Café <test>  ','Café <test>'), ('  ','Selected map point'), ('X'*300,'X'*200)]:
            with self.subTest(name=name):
                route = self.service.command('route', {'point':[40.001,-74], 'name':name})
                self.assertEqual(route['destination'], expected)
        with self.assertRaises(ValueError):
            self.service.command('route', {'point':[999,-74], 'name':'Somewhere'})

    def test_resumable_model_bytes_reduce_remaining_download(self):
        model = choose('compact');part = self.root/'models'/(model['filename']+'.part')
        part.parent.mkdir();part.write_bytes(b'a'*1000)
        marker = part.with_suffix(part.suffix+'.json')
        write_json(marker, {'url':model['url'], 'size':model['bytes'], 'checksum':model['sha256']})
        with patch('jarviss.setup.inspect', return_value={'memory':64*2**30,'available':50*2**30,'disk':100*2**30,'unified':True,'gpus':[],'accelerated':True}):
            saved = self.service.setup.plan('compact')['download_bytes']
            marker.unlink()
            unsaved = self.service.setup.plan('compact')['download_bytes']
        self.assertEqual(unsaved-saved, 1000)

    def test_chat_and_pause_work_while_maps_download(self):
        started = threading.Event();release = threading.Event();failures = []
        model = self.root/'new.gguf';model.write_bytes(b'model')
        plan = {'models':[{'id':'compact','fits':True,'installed':True,'bytes':5,'context':4096}],
                'hardware':{'disk':100*2**30},'required_bytes':1}
        def download(progress, cancel=None):
            started.set()
            if not release.wait(5):raise RuntimeError('Test did not release download')
            progress('US map: downloading')
            return self.root/'map.pmtiles'
        def run():
            try:self.service.command('setup_run', {'model_id':'compact'})
            except Exception as e:failures.append(e)
        with patch.object(self.service.setup,'plan',return_value=plan), \
             patch('jarviss.setup.prepare_runtime'), patch('jarviss.setup.prepare_model',return_value=model), \
             patch('jarviss.setup.prepare_voice'), patch('jarviss.setup.prepare_basemap',side_effect=download), \
             patch.object(self.service.voice,'prepare_tts'), patch.object(self.service.voice,'make_recognizer'), \
             patch.object(self.service.model,'start'), patch.object(self.service.model,'chat',return_value='Ready'):
            worker = threading.Thread(target=run);worker.start()
            try:
                self.assertTrue(started.wait(3))
                self.assertTrue(self.service.ready, 'The model must be usable before the map finishes')
                self.assertIsNone(self.service.operation)
                self.assertEqual(self.service.command('chat', {'text':'Hello Jarvis'}),'Ready')
                for method in ('setup_run','start_model','download_voice','download_us_maps','download_model'):
                    with self.subTest(method=method), self.assertRaisesRegex(RuntimeError,'Setup'):
                        self.service.command(method, {'model_id':'compact'})
                self.service.command('setup_pause', {})
            finally:release.set();worker.join(5)
        self.assertFalse(worker.is_alive())
        self.assertFalse(failures)
        self.assertTrue(self.service.ready)
        self.assertEqual(self.service.setup.snapshot()['status'],'paused')
        self.assertEqual(self.service.settings['model_id'],'compact')

    def test_map_failure_does_not_interrupt_active_chat_or_restore_old_model(self):
        map_started=threading.Event();map_release=threading.Event()
        chat_started=threading.Event();chat_release=threading.Event();failures=[]
        plan={'models':[{'id':'compact','fits':True,'installed':True,'bytes':5,'context':4096}],
              'hardware':{'disk':100*2**30},'required_bytes':1}
        def download(progress,cancel=None):
            map_started.set()
            if not map_release.wait(5):raise TimeoutError('Test did not release map')
            progress('US map · 50%')
            raise OSError('Connection lost')
        def chat(*a,**k):
            if not map_started.is_set():return 'Ready'
            chat_started.set()
            if not chat_release.wait(5):raise TimeoutError('Test did not release chat')
            return 'Hello'
        def run(method,args):
            try:self.service.command(method,args)
            except Exception as error:failures.append((method,error))
        with patch.object(self.service.setup,'plan',return_value=plan),patch('jarviss.setup.prepare_runtime'), \
             patch('jarviss.setup.prepare_model',return_value=self.root/'model.gguf'),patch('jarviss.setup.prepare_voice'), \
             patch('jarviss.setup.prepare_basemap',side_effect=download),patch.object(self.service.voice,'prepare_tts'), \
             patch.object(self.service.voice,'make_recognizer'),patch.object(self.service.model,'start'), \
             patch.object(self.service.model,'chat',side_effect=chat):
            setup=threading.Thread(target=run,args=('setup_run',{'model_id':'compact'}));setup.start()
            conversation=None
            try:
                self.assertTrue(map_started.wait(3))
                conversation=threading.Thread(target=run,args=('chat',{'text':'Hello'}));conversation.start()
                self.assertTrue(chat_started.wait(3))
                map_release.set();setup.join(3)
                self.assertEqual(self.service.operation['method'],'chat')
                self.assertEqual(self.service.operation['progress'],'')
                self.assertTrue(self.service.voice.busy.is_set())
                self.assertTrue(self.service.ready)
                self.assertTrue(self.service.lock.locked())
                self.assertFalse(self.service.state()['setupRunning'])
                self.assertEqual(self.service.setup.snapshot()['status'],'failed')
                self.assertEqual(self.service.settings['model_id'],'compact')
                with self.assertRaisesRegex(RuntimeError,'Thinking'):self.service.command('clear',{})
            finally:
                map_release.set();chat_release.set();setup.join(5)
                if conversation:conversation.join(5)
        self.assertEqual([(m,str(e)) for m,e in failures],[('setup_run','Connection lost')])
        self.assertIsNone(self.service.operation)
        self.assertFalse(self.service.voice.busy.is_set())
        self.assertEqual(self.service.history[-1]['content'],'Hello')


if __name__ == '__main__':unittest.main()
