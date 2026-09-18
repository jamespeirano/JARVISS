"""Resumable transfers against a local HTTP fixture, and the US listing checks."""
import hashlib
import http.server
import io
import itertools
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from jarviss.map_setup import download_file, select_us_files, prepare_routing, prepare_basemap, verify_us, basemap_path
from jarviss.setup import SetupPaused
from jarviss.storage import write_json, read_json
from jarviss.us_routing import USRouter, BROUTER_VERSION

BODY = bytes(range(256))*80  # 20 480 bytes


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        server = self.server
        wanted = self.headers.get('Range')
        server.requests.append(wanted); server.paths.append(self.path)
        offset = int(wanted.removeprefix('bytes=').rstrip('-')) if wanted else 0
        if server.mode == 'dead':
            self.send_error(503); return
        if self.path.endswith('/'):
            self.send_response(200); self.send_header('Content-Length', '9'); self.end_headers(); self.wfile.write(b'<listing>'); return
        if wanted and server.mode == '416':
            self.send_error(416); return
        if wanted and server.mode == 'bad':
            self.send_response(206); self.send_header('Content-Range', f'bytes 0-{len(BODY)-1}/{len(BODY)}')
            self.send_header('Content-Length', str(len(BODY))); self.end_headers(); self.wfile.write(BODY); return
        remaining = BODY[offset:]
        self.send_response(206 if wanted else 200)
        if wanted: self.send_header('Content-Range', f'bytes {offset}-{len(BODY)-1}/{len(BODY)}')
        self.send_header('Content-Length', str(len(remaining))); self.end_headers()
        # 'cut' delivers a slice and drops the connection: progress without completion.
        self.wfile.write(remaining[:3000] if server.mode == 'cut' else remaining)
        self.close_connection = True

    def log_message(self, *_): pass


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        cls.server.mode, cls.server.requests, cls.server.paths = 'ok', [], []
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True); cls.thread.start()
        cls.base = f'http://127.0.0.1:{cls.server.server_port}/'
        cls.url = cls.base+'network.rd5'

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown(); cls.server.server_close(); cls.thread.join()

    def setUp(self):
        self.server.mode, self.server.requests, self.server.paths = 'ok', [], []


class ResumeTests(ServerTests):
    def setUp(self):
        super().setUp()
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.target = Path(self.temp.name)/'network.rd5'
        self.part = self.target.with_suffix('.rd5.part')
        self.sleeps = []
        sleeper = patch('jarviss.map_setup.time.sleep', self.sleeps.append); sleeper.start(); self.addCleanup(sleeper.stop)

    def partial(self, size):
        self.part.write_bytes(BODY[:size])
        write_json(self.part.with_suffix('.part.json'), {'url':self.url, 'size':len(BODY), 'checksum':None})

    def test_416_discards_the_partial_and_restarts_from_zero(self):
        self.partial(5000); self.server.mode = '416'
        download_file(self.url, self.target, lambda _: None, size=len(BODY))
        self.assertEqual(self.server.requests, ['bytes=5000-', None])
        self.assertEqual(self.target.read_bytes(), BODY); self.assertFalse(self.part.exists())

    def test_incorrect_range_discards_the_partial_and_restarts_from_zero(self):
        self.partial(5000); self.server.mode = 'bad'
        download_file(self.url, self.target, lambda _: None, size=len(BODY))
        self.assertEqual(self.server.requests, ['bytes=5000-', None])
        self.assertEqual(self.target.read_bytes(), BODY)

    def test_delivered_bytes_renew_the_retry_budget(self):
        self.server.mode = 'cut'
        download_file(self.url, self.target, lambda _: None, size=len(BODY))
        self.assertEqual(self.target.read_bytes(), BODY)
        self.assertGreater(len(self.server.requests), 4, 'Each slice was resumed rather than abandoned after three tries')
        self.assertEqual(self.server.requests[1], 'bytes=3000-')

    def test_dead_link_stops_after_four_tries_with_backoff(self):
        self.server.mode = 'dead'
        with self.assertRaises(OSError): download_file(self.url, self.target, lambda _: None, size=len(BODY))
        self.assertEqual(len(self.server.requests), 4)
        self.assertEqual(self.sleeps, [1, 2, 4])
        self.assertFalse(self.target.exists())


def listing(rows):
    return ''.join(f'<a href="{name}">{name}</a>                14-Sep-2026 01:03  {size}\n' for name, size in rows)


class ListingTests(unittest.TestCase):
    def rows(self):
        lower48 = [(f'W{x}_N{y}.rd5', 1000) for x in range(70, 130, 5) for y in range(25, 50, 5)]
        alaska = [(f'W{x}_N{y}.rd5', 1000) for x in range(130, 185, 5) for y in range(50, 75, 5)]
        return lower48 + alaska

    def test_full_listing_is_accepted_and_foreign_tiles_are_skipped(self):
        rows = self.rows() + [('E10_N50.rd5', 5), ('W75_S40.rd5', 5)]
        files = select_us_files(listing(rows))
        self.assertEqual(len(files), len(self.rows()))
        self.assertEqual(files[0], {'name':'W70_N25.rd5', 'size':1000, 'provider_modified':'14-Sep-2026 01:03'})

    def test_linked_tile_without_details_is_a_coverage_hole(self):
        rows = self.rows()
        html = listing(rows[:-1]) + f'<a href="{rows[-1][0]}">{rows[-1][0]}</a>                14-Sep-2026 01:03  -\n'
        with self.assertRaisesRegex(ValueError, 'full US routing'): select_us_files(html)


class RoutingReceiptTests(unittest.TestCase):
    def test_tile_without_receipt_is_downloaded_again(self):
        with tempfile.TemporaryDirectory() as temp:
            rows = [{'name':'W100_N30.rd5', 'size':3, 'provider_modified':'stamp'}]
            segments = Path(temp)/'segments4'; segments.mkdir()
            stale = segments/'W100_N30.rd5'; stale.write_bytes(b'old')
            seen = []
            def download(url, target, report, size):
                seen.append(target.exists()); target.write_bytes(b'new'); return 'digest'
            with patch('jarviss.map_setup.USRouter', return_value=USRouter(temp)), patch('jarviss.map_setup.prepare_engine'), \
                 patch('jarviss.map_setup.select_us_files', return_value=rows), patch('urllib.request.urlopen', return_value=io.BytesIO(b'listing')), \
                 patch('jarviss.map_setup.download_file', side_effect=download):
                prepare_routing(lambda _: None)
            self.assertEqual(seen, [False], 'A tile without a receipt must be discarded before downloading')
            self.assertEqual(json.loads(stale.with_suffix('.receipt.json').read_text())['provider_modified'], 'stamp')


def corrupted(): return b'\xff'+BODY[1:]


class VerifyTests(ServerTests):
    """Check setup re-hashes against download-time records; nothing upstream publishes checksums."""
    def setUp(self):
        super().setUp()
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup); self.root = Path(self.temp.name)
        self.segments = self.root/'local-maps'/'routing-us'/'segments4'; self.segments.mkdir(parents=True)
        self.rows = [{'name':f'W{x}_N30.rd5', 'size':len(BODY), 'provider_modified':'stamp', 'sha256':hashlib.sha256(BODY).hexdigest()} for x in (100, 105, 110)]
        write_json(self.segments.parent/'manifest.json', {'version':1, 'complete':True, 'files':self.rows})
        jar = self.root/'runtime'/'brouter'/f'brouter-{BROUTER_VERSION}'/f'brouter-{BROUTER_VERSION}-all.jar'; jar.parent.mkdir(parents=True); jar.touch()
        for name in ('jarviss.map_setup.ROOT', 'jarviss.us_routing.ROOT'): self.enter(patch(name, self.root))
        self.enter(patch('jarviss.us_routing.RUNTIME', self.root/'runtime')); self.enter(patch('jarviss.us_routing.java_path', return_value=jar))
        self.enter(patch('jarviss.map_setup.SEGMENTS_URL', self.base)); self.enter(patch('jarviss.map_setup.prepare_engine'))
        self.enter(patch('jarviss.map_setup.select_us_files', return_value=[dict(r, sha256=None) for r in self.rows]))
        self.events = []

    def enter(self, patcher): patcher.start(); self.addCleanup(patcher.stop)

    def tile(self, row, content=BODY, receipt=True):
        path = self.segments/row['name']; path.write_bytes(content)
        if receipt: write_json(path.with_suffix('.receipt.json'), row)
        return path

    def test_good_install_passes_without_downloads(self):
        for row in self.rows: self.tile(row)
        self.assertEqual(verify_us(self.events.append), [])
        self.assertEqual((self.events[0], self.events[-1]), ('Checking US map files… 0%', 'Checking US map files… 100%'))
        prepare_routing(self.events.append)
        self.assertEqual(self.server.paths, []); self.assertTrue(USRouter().status()['ready'])

    def test_corrupt_and_unreceipted_tiles_are_replaced_and_good_ones_kept(self):
        good, bad, orphan = self.tile(self.rows[0]), self.tile(self.rows[1], corrupted()), self.tile(self.rows[2], receipt=False)
        self.assertEqual(sorted(p.name for p in verify_us(self.events.append)), [bad.name, orphan.name])
        self.assertFalse(bad.exists()); self.assertFalse(bad.with_suffix('.receipt.json').exists()); self.assertTrue(good.exists())
        self.assertFalse(USRouter().status()['ready'])
        prepare_routing(self.events.append)
        self.assertEqual(sorted(self.server.paths), ['/', '/'+bad.name, '/'+orphan.name])
        for path in (bad, orphan):
            self.assertEqual(path.read_bytes(), BODY)
            self.assertEqual(read_json(path.with_suffix('.receipt.json'), {})['sha256'], self.rows[0]['sha256'])
        self.assertTrue(USRouter().status()['ready']); self.assertEqual(verify_us(self.events.append), [])

    def test_basemap_hash_is_checked_or_recorded(self):
        target = basemap_path(); target.write_bytes(BODY); manifest = target.parent/'manifest.json'
        write_json(manifest, {'file':target.name, 'size_bytes':len(BODY)})
        self.assertEqual(verify_us(self.events.append), []); self.assertEqual(read_json(manifest, {})['sha256'], self.rows[0]['sha256'])
        target.write_bytes(corrupted())
        self.assertEqual(verify_us(self.events.append), [target]); self.assertFalse(target.exists())

    def test_pause_stops_verification_before_any_removal(self):
        bad = self.tile(self.rows[0], corrupted())
        def progress(text):
            self.events.append(text)
            if len(self.events) == 2: raise SetupPaused()
        with patch('jarviss.map_setup.time.monotonic', side_effect=itertools.count(1, 2)), self.assertRaises(SetupPaused): verify_us(progress)
        self.assertTrue(bad.exists()); self.assertEqual(len(self.events), 2)


class FakeExtract:
    """Stands in for `pmtiles extract`: writes a partial and either idles until terminated or exits with 1."""
    def __init__(self, args, **_):
        Path(args[3]).write_bytes(b'half'); self.stdout = io.StringIO(''); self.returncode = None

    def poll(self): return self.returncode
    def terminate(self): self.returncode = -15
    kill = terminate

    def wait(self, timeout=None):
        if self.returncode is None: self.returncode = 1
        return self.returncode


class BasemapTests(unittest.TestCase):
    def test_pause_and_failure_remove_the_partial_extract(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); partial = root/'local-maps'/'us-z15.partial'; cancel = threading.Event(); cancel.set()
            with patch('jarviss.map_setup.ROOT', root), patch('jarviss.map_setup.prepare_map_tool', return_value=Path('pmtiles')), \
                 patch('jarviss.map_setup.fetch_json', return_value=[{'key':'20260916.pmtiles', 'version':'4.1'}]), \
                 patch('jarviss.map_setup.subprocess.Popen', FakeExtract):
                with self.assertRaisesRegex(SetupPaused, 'Download paused.*unfinished US map must restart'): prepare_basemap(lambda _: None, cancel)
                self.assertFalse(partial.exists()); self.assertTrue((root/'local-maps'/'us-coverage.geojson').is_file())
                with self.assertRaisesRegex(ValueError, 'did not finish'): prepare_basemap(lambda _: None)
                self.assertFalse(partial.exists())

    def test_unreadable_saved_basemap_is_replaced(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); target = root/'local-maps'/'us-z15.pmtiles'
            target.parent.mkdir(); target.write_bytes(b'not a map')
            events = []
            with patch('jarviss.map_setup.ROOT', root), patch('jarviss.atlas.TileArchive', side_effect=ValueError('Incomplete map archive')), \
                 patch('jarviss.map_setup.prepare_map_tool', return_value=Path('pmtiles')), \
                 patch('jarviss.map_setup.fetch_json', side_effect=OSError('offline')) as builds:
                with self.assertRaisesRegex(OSError, 'offline'): prepare_basemap(events.append)
            builds.assert_called_once()
            self.assertFalse(target.exists())
            self.assertTrue(any('unreadable' in e and 'Incomplete map archive' in e for e in events))


if __name__ == '__main__': unittest.main()
