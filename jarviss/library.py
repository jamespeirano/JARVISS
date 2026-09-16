import re
from datetime import datetime, timezone
from pathlib import Path
from .storage import DATA, RESOURCES, read_json, write_json


def import_note(title,text):
    title=str(title).strip();text=str(text).strip()
    if not title or len(title)>120:raise ValueError('Enter a document name of up to 120 characters.')
    if not text or len(text)>2000000:raise ValueError('Enter document text of up to 2 million characters.')
    docs=read_json(DATA/'library.json',[])
    docs=[d for d in docs if d['title']!=title]
    if len(docs)>=30:raise ValueError('The library has reached 30 documents.')
    docs.append({'title':title,'imported_at':datetime.now(timezone.utc).isoformat(),'text':text})
    write_json(DATA/'library.json',docs)
    return title


def import_text(path):
    path = Path(path)
    if path.suffix.lower() not in ('.txt', '.md', '.pdf'):
        raise ValueError('Add a PDF, TXT or Markdown file.')
    if path.stat().st_size > 30 * 1024 * 1024:
        raise ValueError('Use files smaller than 30 MB.')
    if path.suffix.lower()=='.pdf':
        from pypdf import PdfReader
        pdf=PdfReader(path)
        if pdf.is_encrypted: raise ValueError('This PDF is locked. Add an unlocked copy.')
        if len(pdf.pages)>500: raise ValueError('Use a PDF with 500 pages or fewer.')
        text='\n\n'.join(f'Page {i+1}\n'+(page.extract_text() or '') for i,page in enumerate(pdf.pages))
        if len(re.sub(r'Page \d+|\s','',text))<30: raise ValueError('This PDF contains pictures without readable text. Use Docs → Paste text to add the words you can read.')
    else:
        text = path.read_text(encoding='utf-8-sig')
    if len(text)>2000000: raise ValueError('Use a shorter document or split it into chapters.')
    docs = read_json(DATA / 'library.json', [])
    docs = [d for d in docs if d['title'] != path.name]
    if len(docs) >= 30:
        raise ValueError('The library has reached 30 documents.')
    docs.append({'title': path.name, 'imported_at': datetime.now(timezone.utc).isoformat(), 'text': text})
    write_json(DATA / 'library.json', docs)
    return path.name


def retrieve(question, docs=None):
    if docs is None:
        docs = read_json(DATA / 'library.json', [])
        recovery = RESOURCES / 'collective-recovery.md'
        if recovery.exists():
            docs = docs + [{'title': 'Regroup and rebuild',
                            'imported_at': 'Bundled planning draft',
                            'text': recovery.read_text(encoding='utf-8')}]
    stop = {'the', 'and', 'what', 'how', 'can', 'with', 'for', 'that', 'this', 'have', 'where', 'are', 'you',
            'please', 'say', 'tell', 'ready', 'offline', 'systems', 'system', 'jarvis', 'help'}
    def tokens(text):
        return {word for word in re.findall(r'\w+',text.lower()) if len(word)>=3 or any(c.isdigit() for c in word)}
    words = tokens(question) - stop
    # A shared fault code must not retrieve a different equipment model's manual.
    # Alphanumeric model labels (TP1, EU2200i, R1) are more specific than E04.
    fault_codes=set(re.findall(r'\b(?:shows?|code|error|fault|warning)\s*[:#-]?\s*([a-z]+\d+[a-z0-9]*)',question.lower()))
    models={w for w in words if re.fullmatch(r'[a-z]+\d+[a-z0-9]*',w)
            and not re.fullmatch(r'e\d+',w) and w not in fault_codes}
    if models:
        docs=[d for d in docs if models & tokens(d['title']+' '+d['text'])]
    matches = []
    for doc in docs:
        for start in range(0, len(doc['text']), 650):
            chunk = doc['text'][start:start+850]
            matched = words & tokens(doc['title']+' '+chunk)
            score = sum(3 if any(c.isdigit() for c in word) else 1 for word in matched)
            if score:
                matches.append((score, {'title': doc['title'], 'imported_at': doc['imported_at'], 'text': chunk,
                                       'status': 'User-supplied reference; not independently verified.'}))
    return [m[1] for m in sorted(matches, key=lambda m: m[0], reverse=True)[:3]]
