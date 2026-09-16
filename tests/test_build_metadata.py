"""Build credentials must stay confined to GitHub API metadata requests."""
import io
import os
import unittest
import urllib.request
from unittest.mock import patch

from jarviss.assets import fetch_json, _MetadataRedirectHandler


class BuildMetadataTests(unittest.TestCase):
    def test_token_only_sent_to_exact_https_github_api_origin(self):
        for url, expected in (
            ('https://api.github.com/repos/example/releases', 'Bearer test-token'),
            ('https://huggingface.co/api/models/example', None),
            ('http://api.github.com/repos/example', None),
            ('https://api.github.com.example.com/repos/example', None),
        ):
            with self.subTest(url=url), patch.dict(os.environ, {'JARVIS_BUILD_GITHUB_TOKEN': 'test-token'}), \
                    patch('urllib.request.build_opener') as build:
                build.return_value.open.return_value = io.BytesIO(b'{"ok": true}')
                self.assertEqual(fetch_json(url), {'ok': True})
                request = build.return_value.open.call_args.args[0]
                self.assertEqual(request.get_header('Authorization'), expected)

    def test_redirect_does_not_forward_build_token(self):
        request = urllib.request.Request('https://api.github.com/example',
                                         headers={'Authorization': 'Bearer test-token'})
        redirected = _MetadataRedirectHandler().redirect_request(
            request, None, 302, 'Found', {}, 'https://downloads.example.com/file')
        self.assertIsNone(redirected.get_header('Authorization'))


if __name__ == '__main__':
    unittest.main()
