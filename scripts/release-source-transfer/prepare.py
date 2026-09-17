"""Transfer existing public sources; never rebuild installers or access signing keys."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import tarfile

here = Path(__file__).resolve().parent
application = Path(sys.argv[1]).resolve()
output = Path(sys.argv[2]).resolve()
output.mkdir(parents=True, exist_ok=True)
staging = output / 'staging'
staging.mkdir()
manifest = json.loads((here / 'expected.json').read_text())
expected = {r['name']: r for r in manifest['members']}
assert subprocess.check_output(['git', '-C', str(application), 'rev-parse', 'HEAD'], text=True).strip() == manifest['commit']

def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def download(name, sha256, target):
    url = 'https://github.com/jamespeirano/JARVISS/releases/download/v0.2.2/' + name
    subprocess.run(['curl', '--fail', '--location', '--retry', '3', '--output', str(target), url], check=True)
    assert digest(target) == sha256, name
    print('Verified public archive:', name, flush=True)

old = output / 'previous-source.tar.gz'
download('JARVISS-corresponding-source.tar.gz', 'd303426cc68b1a58af9fb629d97a1c12e6fc5727b00551ab605ceebbef2adeaf', old)
seen = set()
with tarfile.open(old, 'r:gz') as archive:
    for member in archive:
        name = member.name
        if name.startswith('JARVISS/app/') or name == 'JARVISS/README.txt' or member.isdir():
            continue
        assert name in expected and member.isfile() and name not in seen, name
        assert not PurePosixPath(name).is_absolute() and '..' not in PurePosixPath(name).parts
        target = staging / name
        target.parent.mkdir(parents=True, exist_ok=True)
        with archive.extractfile(member) as source, target.open('wb') as destination:
            shutil.copyfileobj(source, destination)
        seen.add(name)

for name, row in expected.items():
    target = staging / name
    if name.startswith('JARVISS/app/'):
        source = application / name.removeprefix('JARVISS/app/')
        assert source.is_file() and not source.is_symlink(), name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    elif name == 'JARVISS/README.txt':
        shutil.copyfile(here / 'README-source.txt', target)
    assert target.is_file() and target.stat().st_size == row['size'], name
    assert digest(target) == row['sha256'], name
    target.chmod(row['mode'])

assert {p.relative_to(staging).as_posix() for p in staging.rglob('*') if p.is_file()} == set(expected)
print('All', len(expected), 'source files match the validated 0.2.3 archive.', flush=True)
packed = output / 'JARVISS-corresponding-source.tar.gz'
with tarfile.open(packed, 'w:gz', compresslevel=1) as archive:
    for name, row in expected.items():
        info = tarfile.TarInfo(name)
        info.size = row['size']
        info.mode = row['mode']
        with (staging / name).open('rb') as source:
            archive.addfile(info, source)

# Verify the output archive, not only the staging directory.
seen = set()
with tarfile.open(packed, 'r:gz') as archive:
    for member in archive:
        row = expected[member.name]
        assert member.isfile() and member.name not in seen
        assert member.size == row['size'] and member.mode == row['mode']
        assert hashlib.file_digest(archive.extractfile(member), 'sha256').hexdigest() == row['sha256'], member.name
        seen.add(member.name)
assert seen == set(expected)

chromium = output / 'chromium-152.0.7977.78.tar.gz'
download(chromium.name, 'ed53dda9001fcd609ba3204f5bd968a131e7e1e6fe26c6ba1c48915a4045f622', chromium)
report = {
    'commit': manifest['commit'],
    'source_files_verified': len(expected),
    'installers_unchanged': True,
    'archives': {p.name: {'bytes': p.stat().st_size, 'sha256': digest(p)} for p in (packed, chromium)},
}
(output / 'verification.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2), flush=True)
