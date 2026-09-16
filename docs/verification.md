# Local verification

## Neural voice update

The rebuilt Windows Electron executable passed actual Kokoro/George playback, bundled phonemizer data loading, audio-device enumeration, Qwen 27B loading, and two real microphone start/pause cycles. Windows native-library initialization, COM initialization, and output sample-rate conversion fixes are included. The packaged renderer integration test and all 15 Python core/streaming tests passed.

The source integration suite passed three synthesized recognition fixtures, spoken pause, three microphone restart cycles, playback followed by listening, and disconnected-device rejection with network requests blocked. A separate production-recognizer → Qwen → Kokoro test completed and returned to listening. The user approved George's voice. Physical speaker-to-microphone phrase recognition remained inconclusive, despite input signal and partial transcription; live user speech accuracy is not established by synthesized fixtures.

On this laptop, the 40-layer Qwen test took 13.69 seconds to first audio and 16.28 seconds through completion. This does not meet realtime conversation latency. See [voice setup, exact test commands, and limitations](voice.md). Mac execution remains untested.

## Electron 0.2

Both development Electron and the packaged Windows executable passed the renderer integration test: isolated renderer (no Node access), navigation, persisted coordinates, real example map search, map-grounded chat without a model, recovery document display, and a 1024-pixel layout. No renderer exceptions occurred. The test uses temporary profile data. The 13 Python core tests also passed.

Windows packaging includes the Python service. Mac packaging is configured in CI but has not run here. Vosk uses 0.3.44 on macOS because that release supplies a universal2 wheel; Windows uses 0.3.45. Mac signing, notarization, permissions, and actual execution remain unverified.

## Earlier Python prototype checks

Desktop redesign: six sidebar destinations, conversation workspace, state-driven voice animation, separate situation editor, and bundled recovery reader. Native Windows navigation to the recovery document and automatic 27B startup were visually checked. Repeated native integration checks passed after restructuring the interface. The design remains a prototype; this is not a claim of production hardening.

Windows 11, 32 GB RAM, RTX 5070 Ti laptop GPU.

- 13 unit tests passed: offline routing, map boundary/access restrictions, missing data, reference retrieval, and archive traversal rejection.
- Desktop integration passed: native Tk interface, saved context, microphone capture, and Windows speech synthesis transcribed locally by Vosk.
- Packaged Windows executable starts and enables hands-free listening.
- Qwen3.8-27B-UD-Q4_K_M.gguf downloaded with SHA-256 verification. Local llama.cpp loaded it with 20 GPU layers in 20.5 seconds; a short response took 6.0 seconds. This is a smoke test, not a performance benchmark.
- Real OpenStreetMap example downloaded, parsed, and bundled with attribution and snapshot dates.

macOS execution and emergency advice quality have not been validated. No physical network-disconnection test was performed. The implementation uses loopback for inference and local files for speech and prepared maps.
