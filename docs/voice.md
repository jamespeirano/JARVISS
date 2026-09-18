# Local voice

## Use voice

1. Finish **Download everything** in setup. Voice uses Kokoro and Vosk; files are verified against pinned SHA-256 hashes.
2. In **Settings → Voice**, select your microphone, speaker and voice. Changes save automatically. Use **Preview voice** to listen; **Stop preview** cancels it.
3. Start the model, then select **Start voice mode**. Say “stop listening” to pause.

The microphone meter shows input level; partial text shows what Vosk recognizes. Device choices are saved by name and audio host. An unavailable selected device produces an error. Previewing a voice only pauses listening while the preview plays; voice mode stays on. Changing audio settings stops the current preview and pauses voice mode.

## Responses

**Settings → Responses** controls the prompt, extra voice instructions, sentence limit and token budgets. Defaults are three spoken sentences, 180 voice tokens and 600 text tokens. Changes apply to the next question. Very small budgets can cut replies short.

Map answers speak a short orientation; full directions remain on screen. Situation notes and relevant local references are included in model questions.

## How it works

Microphone → Vosk recognition → selected local model → Kokoro speech → listening resumes.

Listening pauses during model processing and playback. There is no voice interruption or software echo cancellation. Speaking bars are an animation; the input meter measures microphone level. Speed depends on the model, hardware and context.

Kokoro's 24 kHz output is resampled to the selected device. Microphones that require stereo or multiple channels are mixed to mono for recognition. Windows audio workers initialize COM. NumPy and ONNX initialize before backend requests to avoid a Windows import deadlock. ONNX telemetry is disabled before initialization and through its API.

## Test

- `python -m unittest discover -s tests -p "test_*.py"`: core and streaming regressions.
- `node electron/tests/feedback.cjs`: delayed/failed replies, startup retry, voice selection, preview cancellation and reload.
- `python -m tests.voice_integration`: synthesis, recognition fixtures, pause/restart, playback recovery and a separately reported physical microphone check. Plays audio; saves no microphone recording.
- `python -m tests.live_voice_roundtrip`: generated input through the production recognizer, local model and speech playback, using a temporary conversation.
- `TEST_PACKAGED` plus `node electron/tests/audio.cjs`: packaged voice engine, device enumeration and playback.

Real audio tests require downloaded voice files and working audio devices. Model round trips also require a downloaded model. Results go to `local-data/voice-verification.json` and `voice-roundtrip.json`. Generated speech tests do not establish live microphone accuracy. See [testing and limitations](use-case-verification.md).

## Sources and licenses

[Kokoro ONNX](https://github.com/thewh1teagle/kokoro-onnx) · [Kokoro weights](https://huggingface.co/hexgrad/Kokoro-82M) · [Vosk model catalog](https://alphacephei.com/vosk/models)

Setup uses a pinned Vosk mirror with the original host as fallback; both must match the same checksum. After setup, recognition and playback use local files. eSpeak NG and phonemizer include GPL components; notices and corresponding source accompany official releases. See [distribution notices](distribution-notices.md).
