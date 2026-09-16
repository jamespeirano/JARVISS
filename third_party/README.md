# Third-party software

The original application code is MIT. The packaged Python service is distributed under GPLv3 because it includes phonemizer-fork and eSpeak NG. See [distribution notes](../docs/distribution-notices.md).

- `THIRD-PARTY-NOTICES.txt`: copyright and license notices, also included in installers.
- `licenses/`: individual license texts.
- `source-manifest.json`: versions, source URLs and SHA-256 hashes.
- `python-packages.json`: Python package metadata.

Each official release provides matching application and dependency source alongside its installers. Download `JARVISS-corresponding-source.tar.gz` and `chromium-152.0.7977.78.tar.gz` and `windows-python-sources.tar.gz` on the [release page](https://github.com/jamespeirano/JARVISS/releases). Large source components may be separate attachments listed in the manifest.

To fetch the same dependency archives yourself:

```sh
python scripts/collect_release_sources.py /path/to/source-archives
```

Rebuild instructions are in [BUILDING.md](BUILDING.md). Keep notices and corresponding source with redistributed installers. Do not add private signing keys to a source package.
