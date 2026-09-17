"""Run downloaded models offline. Generation success is not an accuracy verdict.

Usage: python -m tests.evaluate_knowledge --model balanced --output local-data/evaluation.jsonl
Review every answer against its expected facts and source passages. This is a
manual evaluation tool, not a CI test or a medical validation system.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time
import urllib.request


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', choices=('compact', 'balanced', 'advanced', 'all'), default='all')
    parser.add_argument('--mode', choices=('app', 'raw'), default='app')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--cases', type=Path, action='append')
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise SystemExit('Choose a new output file so earlier evidence is preserved.')
    files = args.cases or [root/'tests/scenarios/knowledge.json', root/'tests/scenarios/manuals.json']
    cases = [case for file in files for case in json.loads(file.read_text())]
    with tempfile.TemporaryDirectory(prefix='jarviss-knowledge-') as folder:
        os.environ['JARVISS_DATA'] = folder
        from jarviss.assistant import messages
        from jarviss.calculations import supply_duration
        from jarviss.library import retrieve
        from jarviss.model import LocalModel
        from jarviss.setup import model_catalog
        original = urllib.request.urlopen
        def local_only(request, *a, **kw):
            url = request.full_url if isinstance(request, urllib.request.Request) else str(request)
            if not url.startswith('http://127.0.0.1:'):
                raise AssertionError('External network is forbidden during offline evaluation.')
            return original(request, *a, **kw)
        urllib.request.urlopen = local_only
        try:
            for entry in model_catalog():
                if args.model not in ('all', entry['id']):
                    continue
                model = LocalModel()
                try:
                    path = root/'models'/entry['filename']
                    with path.open('rb') as file:
                        digest = hashlib.file_digest(file, 'sha256').hexdigest()
                    if digest != entry['sha256']:
                        raise ValueError('Downloaded model differs from the pinned catalog hash.')
                    model.start(path, context=entry['context'])
                    for case in cases:
                        start = time.monotonic()
                        row = {**case, 'model':entry['id'], 'model_sha256':digest, 'mode':args.mode,
                               'judgment':'not_reviewed', 'external_network':False}
                        try:
                            documents = retrieve(case['question']) if args.mode == 'app' else []
                            payload = messages({'situation':'Extended outage. Phone and internet services are unavailable.'}, [], case['question'],
                                               documents=documents, spoken=case['id'].startswith('voice-')) if args.mode == 'app' else [
                                {'role':'system', 'content':'Answer clearly and briefly, under 100 words.'},
                                {'role':'user', 'content':case['question']}]
                            direct = supply_duration(case['question']) if args.mode == 'app' else None
                            row['answer'] = direct or model.chat(payload, max_tokens=320)
                            row['answer_path'] = 'calculation' if direct else 'model'
                            row['passages'] = documents if not direct else []
                            row['messages_sha256'] = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
                        except Exception as error:
                            row['error'] = str(error)
                        row['seconds'] = round(time.monotonic()-start, 2)
                        with output.open('a', encoding='utf-8') as file:
                            file.write(json.dumps(row, ensure_ascii=False)+'\n')
                        print(entry['id'], case['id'], row['seconds'], row.get('error',''), flush=True)
                finally:
                    model.close()
        finally:
            urllib.request.urlopen = original


if __name__ == '__main__':
    main()
