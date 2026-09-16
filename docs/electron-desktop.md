# Electron desktop

The current desktop is Electron. Tkinter files are retained only as legacy prototype code; Electron does not import or display them.

## Development on Windows or macOS

Use Python 3.12 and Node 24. In the repository root, create `.venv` and install `requirements.txt`. In `electron`, run `npm ci` and `npm start`. Both platforms run the same HTML/CSS/JavaScript interface. The native Python service uses Vosk for speech recognition and Kokoro ONNX for neural speech output. Microphone access requires the OS's permission.

## Native packages

Install PyInstaller 6.22.3, then run `python scripts/build_electron.py` using the prepared Python environment. The result in `dist` is a macOS DMG/ZIP or Windows installer. It includes Electron/Node, the frozen Python service, llama.cpp, BRouter, Java and PMTiles. End users install no development tools. Build on the target operating system and CPU architecture.

The GitHub Actions workflow builds Windows and macOS artifacts on their native runners when manually triggered or when a version tag is pushed. The Mac artifact follows the runner's architecture; build separately on Intel and Apple Silicon hosts when distributing both. This workflow has not been executed here. The Apple silicon DMG was built and launched locally. Signing and notarization are disabled; security prompts are expected. See [distribution notes](distribution-notices.md) before publishing binaries.

## Existing models and data

Development uses the repository's `models`, `runtime`, and `local-data` folders. Packaged builds use `workspace` inside Electron's per-user application-data directory. The setup wizard shows that location. Large weights and map datasets are excluded from the installer and downloaded during setup. Runtimes come from the app's bundled resources. To reuse a GGUF, choose it in Settings; for a full migration copy `models`, `local-data` and `local-maps` into the new workspace. Keep source records with downloaded assets.

## Hardware recommendations

The catalog supplies pinned URLs, sizes, SHA-256 hashes, context limits and estimated working memory. The wizard checks currently available RAM, Apple unified memory or discrete GPU memory, and free disk space. It reserves memory for the OS, voice and routing; CPU-only machines get a smaller recommendation. Unknown graphics devices use conservative CPU estimates. A successful response is required before replacing the saved model selection. This is a compatibility check, not a guarantee of answer quality or speed on every computer.

## Process boundaries

The sandboxed renderer has no Node access. A context-isolated preload exposes only application operations, native file selection, and service events. The main process validates operation names, denies navigation and new windows, and spawns the Python service with fixed arguments. JSON messages travel over private stdin/stdout pipes; the bridge opens no HTTP port. Model inference continues to use a loopback llama.cpp server. Imported text and model replies render as text, never executable HTML. A local `atlas:` protocol streams the selected PMTiles archive in byte ranges and serves bundled map assets; no map server or HTTP listener is started. See [offline atlas and location discovery](offline-atlas.md).

These choices follow Electron's [security guidance](https://www.electronjs.org/docs/latest/tutorial/security) and [context isolation guidance](https://www.electronjs.org/docs/latest/tutorial/context-isolation). They reduce exposure; they are not a substitute for a security review.

## Validation boundary

Automated route and context checks cover the Python core. Electron integration tests check the actual Chromium renderer, navigation, profile persistence, example maps, and offline document display using isolated test data. Real model and speech tests are separate. A Windows pass does not establish a Mac pass. Full offline cold-start, power consumption, long-duration reliability, and emergency advice quality remain separate validation tasks.
