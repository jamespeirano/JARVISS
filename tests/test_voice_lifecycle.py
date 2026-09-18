import json
import sys
import threading
import time
import types
import unittest
from unittest.mock import Mock, patch

import numpy as np
from jarviss.voice import Voice


def wait_for(condition):
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        if condition(): return
        time.sleep(.01)
    raise AssertionError('Voice worker did not finish')


class VoiceLifecycleTests(unittest.TestCase):
    def setUp(self):
        # These are deterministic lifecycle/device fixtures, not live hardware tests.
        # Importing PortAudio on a cold Windows runner can take several seconds.
        native = patch.dict(sys.modules, sounddevice=Mock(), pythoncom=Mock())
        native.start()
        self.addCleanup(native.stop)

    def make_voice(self):
        events, errors, statuses = [], [], []
        voice = Voice(lambda _: None, statuses.append, errors.append,
                      lambda kind, value: events.append((kind, value)))
        self.addCleanup(voice.close)
        return voice, events, errors, statuses

    def test_microphone_native_channels_are_converted_to_mono(self):
        for supported in (1, 2, 4):
            with self.subTest(channels=supported):
                voice, events, errors, statuses = self.make_voice()
                voice.enabled.set()
                opened, streams, received = [], [], []
                class AudioError(Exception): pass
                def stream(**kwargs):
                    opened.append(kwargs['channels'])
                    if kwargs['channels'] != supported:
                        raise AudioError('Invalid number of channels', -9998)
                    result = Mock()
                    samples = np.tile(np.arange(1, supported+1) * 1000, 8).astype(np.int16)
                    result.start.side_effect = lambda: kwargs['callback'](samples.tobytes(), 8, None, None)
                    streams.append(result)
                    return result
                sd = types.SimpleNamespace(PortAudioError=AudioError, RawInputStream=stream,
                    query_devices=lambda *_args, **_kwargs: {'default_samplerate':48000, 'max_input_channels':supported})
                recognizer = Mock()
                def accept(data):
                    received.extend(np.frombuffer(data, dtype=np.int16))
                    voice.enabled.clear()
                    return False
                recognizer.AcceptWaveform.side_effect = accept
                recognizer.PartialResult.return_value = json.dumps({'partial':''})
                com = Mock()
                with patch.dict(sys.modules, sounddevice=sd, pythoncom=com), \
                     patch('sys.platform', 'win32'), \
                     patch('jarviss.voice.resolve_device', return_value=7), \
                     patch.object(voice, 'make_recognizer', return_value=recognizer):
                    voice._listen()
                self.assertEqual(opened, list(dict.fromkeys([1, min(2,supported), supported])))
                self.assertEqual(received, [int((supported+1)*500)]*8)
                self.assertEqual(errors, [])
                self.assertIn('Listening', statuses)
                streams[0].close.assert_called_once()
                com.CoInitialize.assert_called_once()
                com.CoUninitialize.assert_called_once()

    def test_unavailable_microphone_finishes_startup_and_can_retry(self):
        voice, _, errors, statuses = self.make_voice()
        voice.enabled.set()
        with patch('sounddevice.query_devices', return_value={'default_samplerate':48000,'max_input_channels':0}), \
             patch('jarviss.voice.resolve_device', return_value=7):
            voice._listen()
        self.assertTrue(voice.started.is_set())
        self.assertFalse(voice.enabled.is_set())
        self.assertIn('No microphone', errors[0])
        self.assertEqual(statuses[-1], 'Voice off')

    def test_preview_replaces_queue_uses_selected_voice_and_stops(self):
        voice, events, errors, _ = self.make_voice()
        synthesizing, release = threading.Event(), threading.Event()
        calls, played = [], []
        def create(text, **kwargs):
            calls.append(kwargs['voice'])
            if len(calls) == 1:
                synthesizing.set()
                if not release.wait(3): raise RuntimeError('Test did not release synthesis')
            return np.zeros(240, dtype=np.float32), 24000
        voice.tts = types.SimpleNamespace(create=create)
        voice.prepare_tts = lambda: None
        voice.play_audio = lambda audio, rate, epoch, device: played.append((epoch, device))
        try:
            voice.speak('First.', preview=True)
            self.assertTrue(synthesizing.wait(2))
            voice.configure({'voice_name':'af_heart', 'output_device':{'name':'Selected speaker','host':'Test'}})
            for _ in range(10): voice.speak('Latest.', preview=True)
            release.set()
            wait_for(lambda: not voice.previewing)
            self.assertEqual(calls, ['bm_george','af_heart'])
            self.assertEqual(len(played), 1)
            self.assertEqual(played[0][1]['name'], 'Selected speaker')
            self.assertFalse(voice.enabled.is_set())
            self.assertFalse(voice.speaking.is_set())
            self.assertEqual(events[-1], ('voice_preview', False))
            self.assertEqual(errors, [])
        finally: release.set()

    def test_stop_during_synthesis_prevents_late_playback(self):
        voice, events, errors, _ = self.make_voice()
        started, release = threading.Event(), threading.Event()
        def create(*_args, **_kwargs):
            started.set()
            release.wait(3)
            return np.zeros(240, dtype=np.float32), 24000
        voice.tts = types.SimpleNamespace(create=create)
        voice.prepare_tts = lambda: None
        voice.play_audio = Mock()
        try:
            voice.speak('Preview.', preview=True)
            self.assertTrue(started.wait(2))
            voice.pause()
            release.set()
            voice.close()
            voice.play_audio.assert_not_called()
            self.assertFalse(voice.previewing)
            self.assertEqual(events[-1], ('voice_preview', False))
            self.assertEqual(errors, [])
        finally: release.set()

    def test_stuck_listener_blocks_a_second_microphone_session(self):
        voice, events, errors, statuses = self.make_voice()
        release = threading.Event()
        voice.listener = threading.Thread(target=release.wait, daemon=True); voice.listener.start()
        voice.prepare_tts = lambda: None
        opened = []
        def listen(session): opened.append(session); voice.started.set()
        with patch('jarviss.voice.MODELS', self.voice_files()), patch('jarviss.voice.resolve_device', return_value=7), \
             patch('sounddevice.query_devices', return_value={'default_samplerate':48000, 'max_output_channels':2}), \
             patch('sounddevice.check_output_settings'), patch.object(voice, '_listen', listen):
            with self.assertRaisesRegex(RuntimeError, 'still closing'): voice.start()
            release.set(); voice.listener.join(1)
            voice.start()
        self.assertEqual(opened, [voice.session])
        self.assertFalse(errors)

    def test_superseded_listener_touches_nothing(self):
        voice, events, errors, statuses = self.make_voice()
        voice.enabled.set(); voice.session = 3
        streams = []
        with patch('sounddevice.RawInputStream', side_effect=lambda **k: streams.append(k)), \
             patch('sounddevice.query_devices', return_value={'default_samplerate':48000, 'max_input_channels':1}), \
             patch('jarviss.voice.resolve_device', side_effect=RuntimeError('old device gone')):
            voice._listen(2)
        self.assertEqual(streams, [])
        self.assertTrue(voice.enabled.is_set())
        self.assertFalse(voice.started.is_set())
        self.assertEqual((errors, statuses, events), ([], [], []))

    def test_pause_clears_partial_text_and_preview_keeps_voice_mode_on(self):
        voice, events, errors, _ = self.make_voice()
        voice.pause()
        self.assertIn(('partial', ''), events)
        voice.enabled.set()
        voice.tts = types.SimpleNamespace(create=lambda text, **k: (np.zeros(240, dtype=np.float32), 24000))
        voice.prepare_tts = lambda: None
        voice.play_audio = Mock()
        voice.speak('Preview.', preview=True)
        wait_for(lambda: not voice.previewing)
        self.assertTrue(voice.enabled.is_set())
        self.assertFalse(voice.speaking.is_set())
        self.assertEqual(errors, [])

    def voice_files(self):
        import tempfile
        from pathlib import Path
        from jarviss.assets import VOICE_NAME
        folder = tempfile.TemporaryDirectory(); self.addCleanup(folder.cleanup)
        model = Path(folder.name) / VOICE_NAME / 'am' / 'final.mdl'
        model.parent.mkdir(parents=True); model.write_bytes(b'fixture')
        return Path(folder.name)


if __name__ == '__main__': unittest.main()
