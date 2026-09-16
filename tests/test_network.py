"""Exercise real TLS with no build-machine trust store or external network."""
import hashlib
import http.server
import shutil
import ssl
import subprocess
import tempfile
import threading
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

from jarviss.assets import fetch_json
from jarviss.map_setup import download_file
from jarviss.network import tls_context


class BundledTrustTests(unittest.TestCase):
    def test_bundled_roots_work_without_system_certificates(self):
        tls_context.cache_clear()
        self.addCleanup(tls_context.cache_clear)
        with patch.object(ssl.SSLContext, 'load_default_certs'):
            context = tls_context()
        self.assertGreater(context.cert_store_stats()['x509_ca'], 100)
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(context.check_hostname)


@unittest.skipUnless(shutil.which('openssl'), 'Local TLS fixture requires OpenSSL')
class DownloadTLSTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        cls.cert = cls.root / 'localhost.pem'
        key = cls.root / 'localhost.key'
        subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes',
                        '-days', '1', '-subj', '/CN=localhost',
                        '-addext', 'subjectAltName=DNS:localhost',
                        '-addext', 'basicConstraints=critical,CA:TRUE',
                        '-addext', 'keyUsage=critical,keyCertSign,digitalSignature,keyEncipherment',
                        '-keyout', str(key), '-out', str(cls.cert)],
                       check=True, capture_output=True)

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == '/redirect':
                    self.send_response(302)
                    self.send_header('Location', '/data')
                    self.end_headers()
                    return
                data = b'{"ok": true}'
                self.send_response(200)
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *_):
                pass

        cls.server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(cls.cert, key)
        cls.server.socket = context.wrap_socket(cls.server.socket, server_side=True)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.port = cls.server.server_port

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()
        cls.temp.cleanup()

    def setUp(self):
        tls_context.cache_clear()
        self.addCleanup(tls_context.cache_clear)
        no_system = patch.object(ssl.SSLContext, 'load_default_certs')
        no_system.start()
        self.addCleanup(no_system.stop)

    def test_downloads_and_metadata_use_bundled_trust_through_redirects(self):
        # A test CA replaces the bundled roots; no machine certificates are used.
        with patch('certifi.where', return_value=str(self.cert)):
            url = f'https://localhost:{self.port}/redirect'
            self.assertEqual(fetch_json(url), {'ok': True})
            digest = hashlib.sha256(b'{"ok": true}').hexdigest()
            target = self.root / 'download.json'
            self.assertEqual(download_file(url, target, lambda _: None, checksum=digest), digest)
            self.assertEqual(target.read_bytes(), b'{"ok": true}')

    def test_untrusted_certificate_is_rejected_by_both_download_paths(self):
        url = f'https://localhost:{self.port}/data'
        for download in (lambda: fetch_json(url),
                         lambda: download_file(url, self.root / 'untrusted.json', lambda _: None)):
            with self.subTest(download=download), patch('time.sleep'):
                with self.assertRaises(urllib.error.URLError) as failure:
                    download()
                self.assertIsInstance(failure.exception.reason, ssl.SSLCertVerificationError)
        self.assertFalse((self.root / 'untrusted.json').exists())

    def test_trusted_certificate_for_wrong_hostname_is_rejected(self):
        with patch('certifi.where', return_value=str(self.cert)):
            with self.assertRaises(urllib.error.URLError) as failure:
                fetch_json(f'https://127.0.0.1:{self.port}/data')
        self.assertIsInstance(failure.exception.reason, ssl.SSLCertVerificationError)


if __name__ == '__main__':
    unittest.main()
