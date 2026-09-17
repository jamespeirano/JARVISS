import json
from pathlib import Path
import sys

output = Path(sys.argv[1])
report = json.loads((output / 'verification.json').read_text())
release = json.loads((output / 'release.json').read_text())
assert release['draft'] and release['id'] == 390856464
assert release['target_commitish'] == report['commit']
assets = {a['name']: a for a in release['assets']}
for name, row in report['archives'].items():
    asset = assets[name]
    assert asset['state'] == 'uploaded' and asset['size'] == row['bytes']
    assert asset['digest'] == 'sha256:' + row['sha256'], name
    print('Verified uploaded archive:', name, row['sha256'])
