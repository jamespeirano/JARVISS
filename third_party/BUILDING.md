# Rebuilding a release

## Application and Python service

Use Windows x64 or Apple silicon, Python 3.12 and Node.js 24. Windows releases and GitHub checks use Python 3.12.10; the signed Mac release uses Python 3.12.13. Follow CONTRIBUTING.md to create a virtual environment. Install the pinned dependencies:

```sh
python -m pip install -r requirements.txt pyinstaller==6.22.3 -c constraints.txt
npm ci --prefix electron
python scripts/build_electron.py
```

The build script collects the local Python service into `electron/backend`, copies the separate engines into `electron/bundled-runtime`, builds the renderer assets, then invokes electron-builder. The source archive includes every project build script and the exact dependency source versions. No project patches are applied to upstream libraries.

For a modified Python dependency, extract its archive from `python/` or `upstream/`, follow its build instructions, and install the resulting wheel into the virtual environment before packaging. Do not reinstall the original wheel afterward. The normal build consumes the installed environment. Replace GEOS or libsoxr by rebuilding Shapely or Python-SoXR against the modified library; their source archives include their own build instructions.

## Native speech dependencies

- `espeakng-loader`: its `build.sh`, CMake settings and Python packaging files are included. Populate its `espeak-ng` directory with the separate eSpeak NG archive whose commit is in the manifest. That is the loader's pinned submodule. Build the wheel and install it before packaging.
- `phonemizer-fork`: build the included Python source distribution with a standard PEP 517 build frontend; install the resulting wheel.
- `Vosk`: the matching API source includes `src/Makefile` and `travis/` platform recipes. OpenBLAS v0.3.20, CLAPACK v3.2.1, OpenFST and Kaldi source are also provided. Upstream recipes clone some moving branches; the included manifest identifies the archived snapshots and does not claim bit-for-bit reproduction of upstream wheels.
- `ONNX Runtime`: use its `build.py` and `docs/Build.md`; the ONNX submodule has a separate source archive. Its other build dependencies are included in `onnx-dependencies/`, with upstream checksums in `cmake/deps.txt`.

## Separate engines and desktop runtime

The manifest includes source for llama.cpp, BRouter, PMTiles, Temurin/OpenJDK, Electron and Chromium/FFmpeg. Follow each upstream build's instructions. Runtime download URLs, versions and checksums are in `jarviss/assets.py`, `jarviss/us_routing.py` and `scripts/bundle_runtime.py`. Java's build source is separate from the complete OpenJDK source archive.

Electron's `DEPS`, `patches/` and build tools describe its pinned Chromium, Node and related source dependencies. Chromium's `DEPS` records its dependencies. FFmpeg source includes Chromium's platform configuration files. Replace a rebuilt Electron runtime through electron-builder's `electronDist` setting. Replace separate engines in `electron/bundled-runtime` before the final electron-builder packaging step.

The source set also includes Python native-library sources and Homebrew build recipes in `python-native/` and `app/third_party/build-recipes/`.

## Running modified builds

Public build configuration does not require signing. You can run the source with `npm start --prefix electron`, or package using the commands above. Official release signatures are not checked by application code. The maintainers' signing identities, private keys and account access are not required to modify, rebuild or run Jarvis. Your operating system may ask you to allow an unsigned app; you can also sign your build with your own identity.
