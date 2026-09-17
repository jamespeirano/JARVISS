# Local voice

## Setup

1. In Settings, download the voice models: Kokoro 82M v1.0, its voice bank, and Vosk en-US 0.22-lgraph. Approximately 490 MB downloads, plus application dependencies.
2. Select microphone, speaker, and voice, then save audio settings. Device identity is saved by name and audio host, not an unstable device index.
3. Use Test speaker. George (British English) is the default and was approved by the user during local testing.
4. Wait for the language model to load, then start hands-free. The microphone level meter and partial transcript show whether capture and recognition are working.

Voice off means it is paused. Listening is reported only after the input stream starts. A disconnected selected device produces an error rather than silently routing audio somewhere else. Saving audio settings pauses voice; start it again after a change.

## Response settings

Settings → Responses controls the internal system prompt, additional hands-free instructions, hands-free sentence limit (default 3), hands-free generation budget (default 180 tokens), and text generation budget (default 600 tokens). Changes apply to the next request without reloading the model. Restore defaults fills the editor; Save applies it. Prompts are stored locally in settings.json.

Hands-free instructions apply whenever hands-free is enabled, including typed questions during that session. Streaming stops after the configured number of sentence segments, limiting both the spoken reply and the saved answer. Punctuation/newlines identify segments; abbreviations may count as boundaries. The token budget bounds generation independently and may cut an answer short if set too low. These controls reduce long replies and playback time; they do not remove Qwen's initial processing delay.

Map replies give a brief route summary; the complete directions are in Maps. Situation is an editable entry in Docs, included in every request along with relevant local references. Existing situation data is preserved.

## Pipeline

Microphone → streaming Vosk recognition → Qwen → sentence queue → Kokoro synthesis → device-native audio output → listening resumes.

The current loop is half duplex: microphone audio is not transcribed while Qwen is processing or JARVIS is speaking. Say “stop listening” while listening, or click Stop hands-free to stop playback. There is no voice barge-in or software acoustic echo cancellation. Speaking bars are a state animation, not measured vocal amplitude. The microphone meter is measured input level.

Qwen sentences are queued as the model generates them instead of waiting for the complete answer. This reduces waiting but does not make 27B inference instantaneous. First-response delay depends on hardware, context length, and GPU allocation.

Kokoro produces 24 kHz audio. Output is resampled with libsoxr to the selected device's native rate and channel count. Windows audio worker threads initialize COM, and transient input startup failures are retried. Default Windows routing uses WASAPI; other hosts remain selectable. The packaged service initializes NumPy and ONNX on the main thread before reading requests to avoid a Windows native-library import deadlock.

## Reproducible tests

- `python -m unittest discover -s tests -p "test_*.py"`: core and streaming-response regression tests.
- `python -m tests.voice_integration`: real Kokoro synthesis, three recognition fixtures, spoken pause, three microphone start/pause cycles, speaker playback, listening recovery, missing-device handling, and a separately reported acoustic loop test. Plays audio. No microphone recording is saved.
- `python -m tests.live_voice_roundtrip`: generated input through the production recognizer, real Qwen inference, real Kokoro playback, and recovery to listening. Uses a temporary conversation; does not alter user chat history.
- `node electron/tests/audio.cjs` with `TEST_PACKAGED` set to the executable: packaged ONNX, phonemizer, audio-device enumeration, and native speaker playback.

Machine-readable observations are written to `local-data/voice-verification.json` and `local-data/voice-roundtrip.json`. Generated input is explicitly distinguished from physical microphone pickup.

## Earlier Windows verification

Kokoro loaded in about 1.0–1.2 seconds. Short samples generated 1.2–2.9 seconds of audio in 0.28–0.64 seconds. These are local observations, not a general performance guarantee. The user confirmed that the voice sounded right.

Digital recognition fixtures, spoken pause, repeated starts, playback, and listening recovery passed. The acoustic speaker-to-microphone check did not recognize the expected phrase, despite showing microphone signal and partial transcription. That check does not establish recognition accuracy for the user's live voice; headset routing, speaker suppression, ambient conditions, and speech characteristics require interactive testing.

With 40 GPU layers on the RTX 5070 Ti laptop, a cold Qwen 27B turn took 13.69 seconds from generated input processing to first playback and 16.28 seconds through playback completion; model loading took 12.11 seconds separately. The recognized request was “please say offline systems ready,” and the response was “Offline systems ready.” These results include recognition and speech preparation, not just token generation. This is not realtime conversational latency. The local setting uses 40 layers; other machines need their own memory budget.

These Windows results describe the earlier build. This revision was verified on Apple silicon macOS; rerun platform tests before distributing a new Windows package.

## Current Mac verification

The physical speaker-to-microphone test passed, along with three recognition fixtures, start/pause cycles, spoken pause and listening recovery. A full Qwen → Kokoro conversation reached first playback in 4.48 seconds and completed in 6.96 seconds, then returned to listening. The process exited cleanly. These are observations on this Mac, not guaranteed latency.

ONNX Runtime 1.30 is pinned. The app sets `ORT_DISABLE_TELEMETRY=1` before importing it, then calls its telemetry-disable API. This prevents the native uploader from being created on Mac/Linux and fixed the observed shutdown crash in that uploader. See [ONNX Runtime privacy controls](https://github.com/microsoft/onnxruntime/blob/v1.30.0/docs/Privacy.md).

## Sources and distribution

- [Kokoro ONNX runtime](https://github.com/thewh1teagle/kokoro-onnx): engine and model-download instructions.
- [Kokoro 82M](https://huggingface.co/hexgrad/Kokoro-82M): model weights, Apache 2.0.
- [Vosk model catalog](https://alphacephei.com/vosk/models): 0.22-lgraph is the 128 MB English dynamic-graph model, Apache 2.0.
- Setup downloads this archive from the [Rhasspy mirror](https://huggingface.co/rhasspy/vosk-models/tree/8e5f85a35b402c35022b5af62c101dd6a06d0219/en), with the original host as a fallback. Both downloads must match the same pinned SHA-256 checksum.
- [eSpeak NG](https://github.com/espeak-ng/espeak-ng) and [phonemizer](https://github.com/bootphon/phonemizer): phonemization dependencies include GPL licensing. Public binary distribution needs their license notices and corresponding-source compliance; the current build is a local test artifact, not a completed public release package.

Kokoro downloads are checked against pinned SHA-256 digests. Vosk's downloaded archive hash is recorded, but the upstream catalog provides no independently pinned digest in this implementation. All assets must be prepared while online; inference and playback then use local files.
