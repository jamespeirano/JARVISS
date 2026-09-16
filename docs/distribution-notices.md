# Distribution and licenses

Official Windows downloads are signed by **James Peirano**. Official Apple silicon downloads are signed by **Abito Inc.**, notarized by Apple and stapled. Community builds use the builder's own identity or remain unsigned.

## Original project code

The project's original files remain MIT-licensed, including the Electron interface, Python application source and project-created icon. Retain [LICENSE](../LICENSE) and its copyright notice.

## Packaged Python service

The service combines this project's MIT code with **phonemizer-fork and eSpeak NG (GPLv3)**. The combined service is distributed under [GPLv3](../COPYING). The MIT grant for the original project files remains available. Do not describe the complete installer as MIT-only.

LGPL components include **Python-SoXR/libsoxr** and **GEOS** through Shapely. Their license notices and source are included with the release. Users may modify and rebuild the service and replace these components. There is no application-level signature check requiring the maintainers' identities to run a modified build.

PyInstaller's bootloader has its own distribution exception. Python uses the PSF license. Other Python dependencies retain their upstream licenses and notices.

## Other bundled software

- **Electron/Node.js:** MIT and the bundled Chromium third-party notices. FFmpeg and other constituent libraries retain their own terms.
- **llama.cpp and BRouter:** MIT and their constituent notices.
- **PMTiles tools and Protomaps basemap styles:** BSD licenses and constituent notices.
- **Temurin/OpenJDK:** GPLv2 with the Classpath Exception; the Java runtime's complete `legal/` directory is retained.
- **MapLibre:** BSD-3-Clause; retain its notices.
- **Noto Sans glyphs:** SIL Open Font License; retain the font notices.
- **OpenStreetMap example/map records:** ODbL, with attribution to OpenStreetMap contributors. Boundaries also retain their recorded public source attribution.

License texts and component/source manifests are in [third_party](../third_party/). The application bundle retains the runtime's own legal files.

## Source accompanies each release

The [release page](https://github.com/jamespeirano/JARVISS/releases/latest) provides the installer and **JARVISS-corresponding-source.tar.gz** plus **chromium-152.0.7977.78.tar.gz** and **windows-python-sources.tar.gz** through the same free download mechanism. The archive contains the matching application source, dependency source archives, build instructions, upstream patches/build scripts where applicable, and SHA-256 provenance. **THIRD-PARTY-NOTICES.txt** is provided alongside it and in the app.

Follow [CONTRIBUTING.md](../CONTRIBUTING.md) and [release instructions](releases.md) to rebuild. An unsigned development build does not require an Apple Developer account or Azure signing access. The maintainers' private keys and credentials are not part of the source or required build inputs.

When distributing an installer or modified service, preserve the applicable licenses and provide its corresponding source. If you change dependencies, refresh the source archive and notices for that exact release.

## Downloaded during setup

Language models, voice weights and US map datasets are not inside the installer. The model catalog records pinned revisions, hashes and reported license metadata. Preserve each original model's terms and attribution when redistributing weights; a modified model's label does not replace its original terms.

Kokoro and the selected Vosk voice model retain their publisher terms. OpenStreetMap data uses ODbL; preserve attribution and applicable database-sharing obligations. Imported manuals retain their original rights.

User documents, conversations, locations, access codes and personal records are excluded from releases.
