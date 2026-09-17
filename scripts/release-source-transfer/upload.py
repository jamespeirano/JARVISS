"""Upload only the verified sources, reporting bytes sent every 30 seconds."""
from concurrent.futures import ThreadPoolExecutor, wait
import http.client
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from urllib.parse import urlencode

out = Path(sys.argv[1])
report = json.loads((out / 'verification.json').read_text())
endpoint = 'repos/jamespeirano/JARVISS/releases/390856464'
release = json.loads(subprocess.check_output(['gh', 'api', endpoint]))
assert release['draft'] and release['target_commitish'] == report['commit']
assert set(report['archives']) == {'JARVISS-corresponding-source.tar.gz', 'chromium-152.0.7977.78.tar.gz'}
assets = {a['name']: a for a in release['assets']}
pending = {}
for name, row in report['archives'].items():
    existing = assets.get(name)
    if existing and existing['state'] == 'uploaded':
        assert existing['size'] == row['bytes'] and existing['digest'] == 'sha256:' + row['sha256'], name
        print('Already uploaded and verified:', name, flush=True)
        continue
    if existing:
        assert existing['state'] == 'starter', name
        subprocess.run(['gh', 'api', '--method', 'DELETE', 'repos/jamespeirano/JARVISS/releases/assets/' + str(existing['id'])], check=True)
    pending[name] = {'sent': 0, 'total': row['bytes'], 'phase': 'connecting', 'start': time.monotonic()}

def upload(name):
    row = report['archives'][name]
    state = pending[name]
    connection = http.client.HTTPSConnection('uploads.github.com', timeout=600)
    try:
        path = '/' + endpoint + '/assets?' + urlencode({'name': name})
        connection.putrequest('POST', path)
        connection.putheader('Authorization', 'Bearer ' + os.environ['GH_TOKEN'])
        connection.putheader('Accept', 'application/vnd.github+json')
        connection.putheader('User-Agent', 'JARVISS-release-source-transfer')
        connection.putheader('Content-Type', 'application/gzip')
        connection.putheader('Content-Length', str(row['bytes']))
        connection.endheaders()
        state['phase'] = 'sending'
        with (out / name).open('rb') as source:
            while block := source.read(256 * 1024):
                connection.send(block)
                state['sent'] += len(block)
        state['phase'] = 'awaiting GitHub confirmation'
        response = connection.getresponse()
        payload = json.loads(response.read())
        if response.status != 201:
            raise RuntimeError(f"{name}: HTTP {response.status}: {payload.get('message', 'upload failed')}")
        assert payload['name'] == name and payload['state'] == 'uploaded'
        assert payload['size'] == row['bytes'] and payload['digest'] == 'sha256:' + row['sha256'], name
        state['phase'] = 'uploaded and hash verified'
    except BaseException:
        state['phase'] = 'failed'
        raise
    finally:
        connection.close()

with ThreadPoolExecutor(max_workers=2) as pool:
    futures = [pool.submit(upload, name) for name in pending]
    remaining = set(futures)
    while remaining:
        _, remaining = wait(remaining, timeout=30)
        for name, state in pending.items():
            elapsed = max(time.monotonic() - state['start'], 0.01)
            sent, total = state['sent'], state['total']
            rate = sent / elapsed
            eta = (total - sent) / rate if rate > 0 else None
            estimate = f'{eta / 60:.1f} min transfer remaining' if eta is not None else 'transfer estimate unavailable'
            print(f"{name}: {sent / total:.1%} ({sent / 1048576:.1f}/{total / 1048576:.1f} MiB), {rate / 1048576:.2f} MiB/s average, {estimate}; {state['phase']}", flush=True)
    for future in futures:
        future.result()
