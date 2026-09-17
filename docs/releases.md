# Releases

[0.2.4: downloads, changes and known issues](releases/0.2.4.md)

[Previous release: 0.2.3](releases/0.2.3.md)

## Official downloads

Official installers are attached to a versioned [GitHub release](https://github.com/jamespeirano/JARVISS/releases). The Mac installer is signed by Abito Inc. and notarized by Apple. The Windows installer is signed by James Peirano.

Release filenames are stable for README download links:

- `JARVISS-Windows-x64.exe`
- `JARVISS-Mac-Apple-Silicon.dmg`
- `SHA256SUMS.txt`
- `JARVISS-corresponding-source.tar.gz` and `chromium-152.0.7977.78.tar.gz` and `windows-python-sources.tar.gz`
- `THIRD-PARTY-NOTICES.txt`

Include the exact app source, dependency sources, licenses and build instructions in the corresponding-source archive. Keep it available alongside the matching installer. Do not publish an installer before that archive is complete.

## Build your own

After the setup in CONTRIBUTING.md:

```sh
python -m pip install pyinstaller==6.22.3 -c constraints.txt
python scripts/build_electron.py
```

Build on the target OS. The build downloads executable runtimes; it does not bundle models, voice weights, maps or personal records. Output is in `dist/`. Contributor builds have no maintainer signature. A maintainer's Apple or Azure account is not required to run modified builds.

The desktop workflow also produces unsigned build artifacts on GitHub-hosted runners. It cannot sign or publish releases. No signing credentials, private keys, cloud identity tokens or self-hosted runners are available to it.

## Maintainer checklist

1. Review changes and pass backend/UI checks. Use a clean, pinned source revision.
2. Run the secret and private-data review, including new history and generated artifacts.
3. Collect licenses, exact upstream sources, build scripts and the app source. Verify every source hash.
4. Build both platforms. Check the installer icon and first launch on each.
5. Sign only the reviewed build from the maintainer's separate signing environment. Notarize and staple the Mac app and DMG; verify Windows signatures and timestamps.
6. Create checksums, upload installers and source material, and verify downloads before publishing.

Keep signing credentials outside this repository and outside its GitHub Actions settings. Do not add a repository OIDC trust to the signing account. Never sign artifacts from an unreviewed pull request.

Public certificates and publisher names in installers are verification information, not signing credentials.
