import io
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from jarviss.us_routing import USRouter, segment_name
from jarviss.map_setup import download_file, select_us_files, prepare_us, prepare_routing
from jarviss.setup import SetupPaused


class DownloadTests(unittest.TestCase):
    def test_resume_and_atomic_completion(self):
        with tempfile.TemporaryDirectory() as temp:
            target=Path(temp)/'network.rd5';part=target.with_suffix('.rd5.part')
            part.write_bytes(b'abc')
            part.with_suffix('.part.json').write_text(json.dumps({'url':'https://example.org/a','size':6,'checksum':None}))
            response=io.BytesIO(b'def');response.status=206;response.headers={'Content-Range':'bytes 3-5/6','Content-Length':'3'}
            with patch('urllib.request.urlopen',return_value=response) as request:
                download_file('https://example.org/a',target,lambda _:None,size=6)
            self.assertEqual(request.call_args.args[0].get_header('Range'),'bytes=3-')
            self.assertEqual(target.read_bytes(),b'abcdef');self.assertFalse(part.exists())

    def test_partial_failure_is_not_published_or_deleted(self):
        with tempfile.TemporaryDirectory() as temp:
            target=Path(temp)/'network.rd5'
            with patch('urllib.request.urlopen',side_effect=OSError('connection lost')),patch('time.sleep'):
                with self.assertRaises(OSError):download_file('https://example.org/a',target,lambda _:None,size=6)
            self.assertFalse(target.exists())

    def test_national_manifest_rejects_incomplete_listing(self):
        with self.assertRaisesRegex(ValueError,'full US'):select_us_files('<a href="W100_N30.rd5">W100_N30.rd5</a> 14-Sep-2026 01:03 10\n')

    def test_routing_pause_does_not_start_queued_downloads(self):
        with tempfile.TemporaryDirectory() as temp:
            rows=[{'name':f'W{x}_N30.rd5','size':100,'provider_modified':'test'} for x in range(60,120,5)]
            cancelled=threading.Event(); others_finished=threading.Event()
            lock=threading.Lock(); stopped=0; started=[]
            def progress(text):
                nonlocal stopped
                with lock:
                    if cancelled.is_set() or text.startswith('US directions ·'):
                        cancelled.set(); stopped+=1
                        if stopped>=len(rows)-1:others_finished.set()
                        raise SetupPaused()
            def download(url,target,report,size):
                started.append(target.name)
                # Keep the first result pending while another worker requests
                # pause. Queued work must observe it before opening a connection.
                if target.name==rows[0]['name']:
                    self.assertTrue(others_finished.wait(2))
                report('Partial file saved')
            with patch('jarviss.map_setup.USRouter',return_value=USRouter(temp)), \
                 patch('jarviss.map_setup.prepare_engine'), \
                 patch('jarviss.map_setup.select_us_files',return_value=rows), \
                 patch('urllib.request.urlopen',return_value=io.BytesIO(b'listing')), \
                 patch('jarviss.map_setup.download_file',side_effect=download):
                with self.assertRaises(SetupPaused):prepare_routing(progress)
            self.assertLessEqual(len(started),3,'Pause started downloads beyond the three already active workers')
            self.assertFalse(json.loads((Path(temp)/'manifest.json').read_text())['complete'])


class RoutingTests(unittest.TestCase):
    def test_segments_cover_us_without_a_current_position(self):
        self.assertEqual(segment_name((39.9526,-75.1636)),'W80_N35.rd5')
        self.assertEqual(segment_name((40.7128,-74.006)),'W75_N40.rd5')
        router=USRouter()
        self.assertTrue(router.contains((61.2181,-149.9003)))
        self.assertTrue(router.contains((21.3069,-157.8583)))
        self.assertFalse(router.contains((51.5,-0.1)))

    def test_readiness_detects_missing_file_even_with_complete_manifest(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'manifest.json').write_text(json.dumps({'complete':True,'files':[{'name':'W100_N30.rd5','size':10}]}))
            self.assertFalse(USRouter(root).status()['ready'])

    def test_engine_turns_and_distances_do_not_invent_road_names(self):
        router=USRouter();data={'features':[{'geometry':{'type':'LineString','coordinates':[[0,0],[0,.001],[.001,.001]]},'properties':{'track-length':'222','voicehints':[[1,5,0,111,90]]}}]}
        result=router.decode(data,(0,0),(.001,.001))
        self.assertEqual(result['distance_m'],222)
        self.assertEqual(result['steps'][0]['action'],'Head north')
        self.assertEqual(result['steps'][1]['action'],'Turn right')
        self.assertEqual(sum(s['distance_m'] for s in result['steps']),222)
        self.assertIn('road names are not included',result['note'])
        with self.assertRaisesRegex(ValueError,'250 m'):router.decode(data,(1,1),(.001,.001))
        data['features'][0]['properties']['voicehints']=[[1,12,0,111,90]]
        with self.assertRaisesRegex(ValueError,'unmapped direct'):router.decode(data,(0,0),(.001,.001))

    @unittest.skipUnless(USRouter().status()['ready'],'Install US maps for real offline route verification')
    def test_real_route_crosses_file_and_state_boundaries(self):
        # Philadelphia → NYC traverses several internal files. No per-area setup or Python network access.
        with patch('socket.socket',side_effect=AssertionError('Network forbidden')):
            result=USRouter().route((39.9526,-75.1636),(40.7128,-74.006))
        self.assertGreater(result['distance_m'],150000)
        self.assertLess(result['distance_m'],300000)
        self.assertGreater(len(result['steps']),10)
        self.assertLess(result['start_gap_m'],250)
        self.assertLess(result['end_gap_m'],250)

    @unittest.skipUnless(USRouter().status()['ready'],'Install US maps for real offline verification')
    def test_installed_setup_uses_no_network(self):
        with patch('urllib.request.urlopen',side_effect=AssertionError('Network forbidden')):
            self.assertTrue(prepare_us(lambda _:None).is_file())


if __name__=='__main__':unittest.main()
