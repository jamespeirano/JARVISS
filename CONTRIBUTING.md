# Contributing

Help with code, bug reports, guides, translations, accessibility or testing. Start small: one fix or improvement per pull request.

## Propose a change

1. Check existing issues. For a large feature, discuss the idea first.
2. Fork this repository and create a branch in your fork.
3. Make the change and run the relevant checks below.
4. Open a pull request describing the problem, the change and how you checked it. Include a screenshot for visible UI changes.

A maintainer reviews and merges accepted changes. You do not need write access to contribute. Use an issue or Discussion if you do not write code.

## Run locally

Install Python 3.12 and Node 24 for development. End users only need the installer.

```sh
git clone https://github.com/YOUR-USERNAME/JARVISS.git
cd JARVISS
python -m venv .venv
```

Activate the environment:

- macOS/Linux: `source .venv/bin/activate`
- Windows PowerShell: `.venv\Scripts\Activate.ps1`
- Windows Command Prompt: `.venv\Scripts\activate.bat`

```sh
python -m pip install -r requirements.txt -c constraints.txt
npm ci --prefix electron
npm start --prefix electron
```

You can inspect the UI and run unit tests without downloading models or the US map. To test real AI, voice or directions, use setup to download the required data.

For later launches from a source checkout, use `Start JARVISS.command` on Mac or `Start JARVISS.cmd` on Windows. Installed copies launch from the normal JARVISS app shortcut.

## Checks

```sh
python -m unittest discover -s tests -p 'test_*.py' -v
node electron/tests/atlas-protocol.cjs
npm run build:map --prefix electron
```

For UI changes, run the relevant scripts in `electron/tests/` on a desktop session, such as `node electron/tests/setup.cjs` or `node electron/tests/smoke.cjs`. These use temporary test records. Do not run them against your personal workspace. Packaged and full-map tests are explained in [verification](docs/use-case-verification.md).

## Where things live

- `electron/`: screens, styles, the desktop bridge and app icons.
- `jarviss/`: local assistant, models, maps, voice, setup and planning.
- `resources/`: bundled guides, model catalog and routing definitions.
- `tests/` and `electron/tests/`: backend and UI checks.
- `scripts/`: development packaging and release checks.
- `docs/`: usage, architecture notes and verification evidence.
- `third_party/`: license notices and source provenance.

## Keep changes easy to use

- Use short, ordinary language. Avoid extra screens and settings.
- Keep offline features offline. Explain any new network request.
- Add a regression test for a bug when it can fail for the original problem.
- Keep observations, assumptions and estimates distinct. Cite primary sources for factual guide changes.
- Include upstream licenses and source provenance for added dependencies or data.
- Use synthetic test records. Never commit conversations, addresses, credentials, downloaded models or private documents.

## Licensing and signing

By contributing, you confirm you have the right to submit your work under the project's applicable licenses. Original project contributions use MIT; third-party code retains its license. See [distribution notes](docs/distribution-notices.md).

Contributor builds do not use the maintainers' signing identities. Public CI has no Apple certificate/private key, notarization credential, Azure credential or signing permission. Build your own unsigned copy, or sign your fork with your own identity. See [release process](docs/releases.md).

Follow the [code of conduct](CODE_OF_CONDUCT.md). Report vulnerabilities using [SECURITY.md](SECURITY.md), not a public issue.
