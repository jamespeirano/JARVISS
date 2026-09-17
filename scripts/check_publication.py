"""Check release prerequisites and prevent accidental signing access in public CI."""
import json
import re
import subprocess
from pathlib import Path

root = Path(__file__).resolve().parent.parent
files = subprocess.check_output(['git', 'ls-files', '-z'], cwd=root).decode().split('\0')
required_source = {'jarviss/__init__.py', 'jarviss/app.py', 'jarviss/service.py', 'jarviss/setup.py', 'launch.py', 'service.py'}
assert not (required_source - set(files)), f'Backend source missing from Git: {sorted(required_source - set(files))}'
for path in (root / 'jarviss').glob('*.py'):
    assert str(path.relative_to(root)) in files, f'Backend module is not tracked: {path.name}'
for name in filter(None, files):
    path = Path(name)
    assert path.suffix.lower() not in {'.p12', '.pfx', '.pem', '.key', '.mobileprovision'}, name
    assert not any(part in {'local-data', 'models', 'local-maps', '.azure', '.signing', '.venv'} for part in path.parts), name
    assert path.name not in {'.env', 'TRANSCRIPT_SUMMARY.md'}, name

for path in (root / '.github/workflows').glob('*.yml'):
    text = path.read_text()
    forbidden = ['secrets.', 'id-token: write', 'contents: write', 'self-hosted',
                 'pull_request_target', 'azure/login', 'codesigning.azure.net',
                 'CSC_LINK', 'APPLE_ID_PASSWORD', 'notarytool', 'sign_files.py']
    assert not any(value in text for value in forbidden), f'Public workflow crosses signing boundary: {path.name}'
    for action in re.findall(r'uses:\s*([^\s#]+)', text):
        assert re.fullmatch(r'[^@]+@[a-f0-9]{40}', action), f'Action must use an immutable revision: {action}'
    assert 'contents: read' in text, path.name

assert (root / 'electron/icons/icon.png').read_bytes().startswith(b'\x89PNG\r\n\x1a\n')
assert (root / 'electron/icons/icon.icns').read_bytes().startswith(b'icns')
assert (root / 'electron/icons/icon.ico').read_bytes()[:4] == b'\0\0\1\0'
assert 'GNU GENERAL PUBLIC LICENSE' in (root / 'COPYING').read_text()
assert (root / 'third_party/THIRD-PARTY-NOTICES.txt').stat().st_size > 1000
assert json.loads((root / 'third_party/source-manifest.json').read_text())['components']
assert 'jamespeirano/survival-jarvis/releases' not in (root / 'README.md').read_text()
print('PASS: tracked files, credential-free CI, pinned actions, app icons, licenses and source manifest')
