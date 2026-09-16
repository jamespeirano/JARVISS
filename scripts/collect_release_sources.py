"""Fetch and verify the source archives listed for this release. No credentials needed."""
import argparse
import hashlib
import json
from pathlib import Path
import urllib.request


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination', type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    components = json.loads((root / 'third_party/source-manifest.json').read_text())['components']
    supplement = root / 'third_party/windows-source-manifest.json'
    if supplement.exists():
        for item in json.loads(supplement.read_text())['components']:
            components.append({**item, 'file': 'windows-python-sources/' + item['file']})
    for item in components:
        relative = Path(item['file'])
        if relative.is_absolute() or '..' in relative.parts:
            raise ValueError(f'Unsafe archive path: {relative}')
        target = args.destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            with target.open('rb') as stream:
                if hashlib.file_digest(stream, 'sha256').hexdigest() == item['sha256']:
                    continue
        temporary = target.with_suffix(target.suffix + '.partial')
        with urllib.request.urlopen(item['url'], timeout=300) as response, temporary.open('wb') as output:
            while chunk := response.read(1024 * 1024):
                output.write(chunk)
        with temporary.open('rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        if digest != item['sha256']:
            temporary.unlink()
            raise ValueError(f'Source checksum mismatch: {item["name"]}')
        temporary.replace(target)
        print(f'Verified {item["name"]}', flush=True)


if __name__ == '__main__':
    main()
