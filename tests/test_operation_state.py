import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from jarviss.service import Service


class OperationStateTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.patches=[patch('jarviss.service.DATA',self.root),patch('jarviss.service.ROOT',self.root),
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


if __name__=='__main__':unittest.main()
