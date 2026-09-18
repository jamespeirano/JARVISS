# JARVISS

**Just A Rather Very Intelligent Survival System.**

JARVISS is an offline assistant for extended outages: local AI, voice, US maps, walking directions, practical guides and group planning.

## Download

[Get JARVISS at jarviss.live](https://jarviss.live)

**Version 0.2.6** · [What's new and known issues](docs/releases/0.2.6.md)

### [Download for Windows](https://github.com/jamespeirano/JARVISS/releases/latest/download/JARVISS-Windows-x64.exe)

**About 280 MB.** Windows 10 or 11, 64-bit Intel/AMD. Open the installer. Publisher: **James Peirano**.

### [Download for Mac](https://github.com/jamespeirano/JARVISS/releases/latest/download/JARVISS-Mac-Apple-Silicon.dmg)

**About 340 MB.** Apple silicon (M1 or newer), macOS 13 or newer. Open the disk image and drag JARVISS to Applications. Publisher: **Abito Inc.**; notarized by Apple.

Exact sizes and SHA-256 checksums are on the [release page](https://github.com/jamespeirano/JARVISS/releases/latest). These downloads contain the software engines. Models, voice and maps download during setup.

**Hardware:** 16 GB RAM recommended. Setup checks available memory and storage and recommends a model that fits. Plan for roughly 35–50 GB of free storage for the US map, walking data, voice and a model. Larger models need more memory. Intel Mac and Linux installers are not included in this release.

## Start

1. Install and open JARVISS. No Python, Node, terminal or separate model app is needed.
2. Choose **Download everything** while you have internet.
3. Wait for **Ready offline**.
4. In **Chat → Situation → Edit**, describe your group. In **Maps**, enter a street or landmark, city and state, then confirm your point on the map. Coordinates are not required.

## Use it

- **Chat:** ask a question, translate text, or select **Start voice mode**.
- **Maps:** find recorded resources, check miles and follow walking directions.
- **Plan:** track supplies, tasks, power, crops, people and observations.
- **Docs:** search 38 offline references (about 105,000 words), including FEMA disaster-response and Army field-skills chapters. Open source passages from chat, save text or illustrated PDFs, and add your own manuals. [Library details](docs/reference-library.md).
- **Group messages:** connect devices to the same local network. Internet is not needed. Messages are not encrypted.

After setup, answers, voice and map searches run locally. Maps do not confirm current access, safe drinking water or available supplies. AI answers can be wrong; [model and scenario limitations](docs/use-case-verification.md) are documented.

## Contribute

Bug reports, documentation, accessibility improvements, translations and code are welcome.

1. Read [CONTRIBUTING.md](CONTRIBUTING.md).
2. Pick a [good first issue](https://github.com/jamespeirano/JARVISS/issues?q=is%3Aissue+is%3Aopen+label%3A%22good+first+issue%22), or open an issue with your idea.
3. Fork the repo and submit a pull request. A maintainer reviews it before it enters the official app.

[Report a bug](https://github.com/jamespeirano/JARVISS/issues/new/choose) · [Discuss an idea](https://github.com/jamespeirano/JARVISS/discussions) · [Report a security issue privately](SECURITY.md)

## Develop

Use Python 3.12 and Node 24. From a clone:

```sh
python -m venv .venv
# Activate .venv (instructions in CONTRIBUTING.md), then:
python -m pip install -r requirements.txt -c constraints.txt
npm ci --prefix electron
npm start --prefix electron
```

[Build and test](docs/electron-desktop.md) · [Map coverage](docs/offline-atlas.md) · [Release process](docs/releases.md)

## Licenses

Original project code is [MIT](LICENSE). The packaged Python service includes GPL components and is distributed under [GPLv3](COPYING), with the original MIT permissions retained for this project's own files. Other bundled software keeps its own licenses.

Each release provides [third-party notices and corresponding source](docs/distribution-notices.md) alongside its installers. Models and map data have separate terms. Imported documents remain yours; do not upload private records or copyrighted manuals to this repository.

This software uses [FFmpeg](https://ffmpeg.org/) under LGPL 2.1 or later. [Source downloads](https://github.com/jamespeirano/JARVISS/releases/latest) accompany the installers.
