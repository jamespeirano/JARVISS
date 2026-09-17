import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from jarviss.assets import prepare_voice, VOICE_NAME, VOICE_SHA256, VOICE_URLS
from jarviss.setup import SetupPaused
from jarviss.storage import read_json


class VoiceDownloadTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.models = Path(temp.name)
        for replacement in (patch('jarviss.assets.MODELS', self.models),
                            patch('jarviss.assets.prepare_tts'), patch('jarviss.assets.extract')):
            replacement.start()
            self.addCleanup(replacement.stop)

    def test_mirror_uses_upstream_checksum_and_records_provenance(self):
        with patch('jarviss.assets.download', return_value=VOICE_SHA256) as download:
            dest = prepare_voice(lambda _: None)
        self.assertEqual(download.call_args.args[0], VOICE_URLS[0])
        self.assertEqual(download.call_args.args[3], VOICE_SHA256)
        self.assertEqual(read_json(dest / 'download-source.json', {})['url'], VOICE_URLS[0])

    def test_failed_or_corrupt_mirror_falls_back_with_same_checksum(self):
        for failure in (OSError('unavailable'), ValueError('checksum mismatch')):
            with self.subTest(failure=failure), patch('jarviss.assets.download', side_effect=[failure, VOICE_SHA256]) as download:
                dest = prepare_voice(lambda _: None)
                self.assertEqual([call.args[0] for call in download.call_args_list], list(VOICE_URLS))
                self.assertTrue(all(call.args[3] == VOICE_SHA256 for call in download.call_args_list))
                self.assertEqual(read_json(dest / 'download-source.json', {})['url'], VOICE_URLS[1])

    def test_pause_is_not_treated_as_a_failed_mirror(self):
        with patch('jarviss.assets.download', side_effect=SetupPaused) as download:
            with self.assertRaises(SetupPaused):
                prepare_voice(lambda _: None)
            self.assertEqual(download.call_count, 1)

    def test_existing_voice_model_is_reused(self):
        model = self.models / VOICE_NAME / 'am' / 'final.mdl'
        model.parent.mkdir(parents=True)
        model.write_bytes(b'fixture')
        with patch('jarviss.assets.download') as download:
            prepare_voice(lambda _: None)
            download.assert_not_called()


if __name__ == '__main__':
    unittest.main()
