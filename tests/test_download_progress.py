import hashlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from jarviss.download_progress import map_transfer_text, transfer_text
from jarviss.map_setup import download_file, prepare_basemap
from jarviss.setup import SetupPaused


class DownloadProgressTests(unittest.TestCase):
    def test_real_map_counters_hide_ansi_mojibake_and_internal_logs(self):
        # Formats captured from the pinned map tool; both repeated units and
        # shared units occur during the same transfer.
        for bar in ('█', 'â–ˆ', '\x1b[32m█\x1b[0m'):
            for counters in ('546 MB/20 GB, 47 MB/s', '1.6/20 GB, 36 MB/s'):
                with self.subTest(bar=bar,counters=counters):
                    text = map_transfer_text(f'fetching chunks 7% |{bar}| ({counters}) [41s:8m47s]')
                    self.assertIn('US map',text);self.assertIn('7%',text)
                    self.assertIn('GB',text);self.assertIn('MB/s',text);self.assertIn('left',text)
                    self.assertNotIn(bar,text)
        for line in ('extract.go:612 completed', 'Extract transferred 20 GB (overfetch 0.05)', 'fetching 122 dirs', 'random 15%'):
            self.assertIsNone(map_transfer_text(line))

    def test_download_uses_friendly_decimal_units_and_verifies_before_publish(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp)/'long-abliterated-model.Q4_K_M.gguf'
            body = b'a'*1_100_000
            response = io.BytesIO(body);response.status=200;response.headers={'Content-Length':str(len(body))}
            events = []
            def progress(text):
                self.assertFalse(target.exists(),'Incomplete or unverified file became visible')
                events.append(text)
            with patch('urllib.request.urlopen',return_value=response):
                download_file('https://example.org/model',target,progress,len(body),hashlib.sha256(body).hexdigest())
            self.assertEqual(target.read_bytes(),body)
            self.assertTrue(any('AI model' in e for e in events))
            self.assertTrue(any('Checking AI model download' in e for e in events))
            self.assertFalse(any(target.name in e for e in events))
        text=transfer_text('AI model',1_000_000_000,5_300_000_000,10_000_000)
        self.assertIn('1.0 GB / 5.3 GB',text);self.assertIn('10.0 MB/s',text)
        self.assertIn('8 min left',text)
        self.assertNotIn('left',transfer_text('AI model',5,0,2))
        self.assertNotIn('left',transfer_text('AI model',5,5,2))

    def test_corrupt_download_is_never_published(self):
        with tempfile.TemporaryDirectory() as temp:
            target=Path(temp)/'bad.gguf'
            def response(*a,**k):
                result=io.BytesIO(b'bad');result.status=200;result.headers={'Content-Length':'3'};return result
            with patch('urllib.request.urlopen',side_effect=response),patch('time.sleep'):
                with self.assertRaisesRegex(ValueError,'checksum'):
                    download_file('https://example.org/model',target,lambda _:None,3,'0'*64)
            self.assertFalse(target.exists())

    def test_basemap_utf8_filter_check_stage_and_cancel(self):
        for pause in (False,True):
            with self.subTest(pause=pause),tempfile.TemporaryDirectory() as temp:
                root=Path(temp);partial=root/'local-maps/us-z15.partial'
                process=Mock();process.stdout=io.StringIO('fetching chunks 100% |â–ˆ| (20/20 GB, 36 MB/s) [1s:0s]\nextract.go:612 overfetch\n');process.wait.return_value=0;process.poll.return_value=0
                events=[]
                def spawn(*a,**k):partial.write_bytes(b'map');return process
                def progress(text):
                    events.append(text)
                    if pause and 'Checking US map' in text:raise SetupPaused()
                build={'key':'20260915.pmtiles','version':'4.0'}  # gitleaks:allow -- public map filename
                with patch('jarviss.map_setup.ROOT',root),patch('jarviss.map_setup.prepare_map_tool',return_value=Path('pmtiles')), \
                     patch('jarviss.map_setup.fetch_json',return_value=[build]), \
                     patch('jarviss.map_setup.shutil.copyfile'),patch('jarviss.map_setup.subprocess.Popen',side_effect=spawn) as start, \
                     patch('jarviss.map_setup.subprocess.run') as verify,patch('jarviss.atlas.TileArchive',return_value=Mock(pack={'osm_timestamp':'test'})):
                    if pause:
                        with self.assertRaises(SetupPaused):prepare_basemap(progress)
                        self.assertFalse(partial.with_suffix('.pmtiles').exists());verify.assert_not_called()
                    else:
                        self.assertTrue(prepare_basemap(progress).is_file());verify.assert_called_once()
                    self.assertEqual(start.call_args.kwargs['encoding'],'utf-8')
                    self.assertEqual(start.call_args.kwargs['errors'],'replace')
                    self.assertIn('Checking US map download…',events)
                    self.assertFalse(any('extract.go' in e or 'â' in e or 'overfetch' in e for e in events))


if __name__=='__main__':unittest.main()
