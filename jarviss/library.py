import re
import hashlib
import math
from collections import Counter
from functools import lru_cache
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


@lru_cache(maxsize=1)
def references():
    """Bundled, versioned texts; no network or user-controlled file paths."""
    result = []
    for entry in read_json(RESOURCES / 'references' / 'catalog.json', []):
        name = entry['file']
        if Path(name).name != name or not name.endswith('.md'):
            raise ValueError('Invalid reference filename.')
        text = (RESOURCES / 'references' / name).read_text(encoding='utf-8')
        result.append({**entry, 'text': text, 'sections': sections(text)})
    return result


def sections(text):
    result = []
    occurrences = Counter()
    heading, body = 'Overview', []
    def finish():
        value = '\n'.join(body).strip()
        if value:
            # Adding another chapter must not invalidate saved chat links.
            anchor = hashlib.sha256((heading + str(occurrences[heading])).encode()).hexdigest()[:12]
            occurrences[heading] += 1
            result.append({'id': anchor, 'heading': heading, 'text': value})
    for line in text.splitlines():
        if re.match(r'^#{1,3} ', line):
            finish(); heading = line.lstrip('# ').strip(); body = []
        else:
            body.append(line)
    finish()
    return result


def reference_catalog():
    return [{k: v for k, v in d.items() if k not in ('text', 'sections')} for d in references()]


def reference_document(identifier):
    found = next((d for d in references() if d['id'] == identifier), None)
    if not found:
        raise ValueError('This reference is not in the installed library.')
    return found


def reference_pdf(identifier):
    name = reference_document(identifier).get('pdf', '')
    if not name or Path(name).name != name or not name.endswith('.pdf'):
        raise ValueError('This reference has no illustrated PDF.')
    path = RESOURCES / 'references' / name
    if not path.is_file():
        raise ValueError('The illustrated PDF is missing. Reinstall the application.')
    return str(path.resolve())


_STOP = set('the and what why when which how can with for that this have where are you please say tell ready offline systems system jarvis jarviss help from into about should would could does just some there they them then need want using use give explain know all only any been after before more than out get make still now will has our but its enough even though already really mean means describe according'.split())


def _tokens(text):
    text = re.sub(r'(?<=\d),(?=\d{3}\b)', '', text.lower())
    text = re.sub(r'\b(?:burning|burned|burnt) out\b', 'burnout', text)
    text = re.sub(r'\b(?:[a-z]\.){2,}[a-z]?\.?', lambda m:m[0].replace('.', ''), text)
    words = re.findall(r'[a-z0-9]+', text)
    # Small lexical normalization, without altering model labels or quantities.
    aliases = {'fridge':'refrigerator', 'refrigerated':'refrigerator', 'refrigeration':'refrigerator',
               'frozen':'freez', 'froze':'freez', 'freeze':'freez', 'freezing':'freez',
               'boiling':'boil', 'boiled':'boil', 'canned':'canning', 'medication':'medicine',
               'medications':'medicine', 'medicines':'medicine', 'drugs':'medicine',
               'growing':'grow', 'planting':'plant', 'cooking':'cook', 'cooked':'cook',
               'stressed':'stress', 'stressful':'stress', 'burnout':'stress',
               'gasoline':'fuel', 'petrol':'fuel', 'pesticides':'pesticide',
               'different':'unequal', 'thickness':'diameter',
               'rinsed':'rinse', 'rinsing':'rinse', 'washed':'wash', 'washing':'wash'}
    return [aliases.get(w, w[:-1] if w.endswith('s') and len(w)>4 else w)
            for w in words if w not in _STOP and (len(w)>2 or any(c.isdigit() for c in w))]


def _chunks(section, maximum=2400):
    """Keep paragraphs/lists whole: never cut off a condition halfway through."""
    paragraphs = re.split(r'\n\s*\n', section['text'])
    current = []
    for paragraph in paragraphs:
        if current and sum(map(len, current)) + len(paragraph) > maximum:
            yield '\n\n'.join(current); current = []
        current.append(paragraph)
    if current:
        yield '\n\n'.join(current)


@lru_cache(maxsize=1)
def _reference_chunks():
    chunks = []
    for doc in references():
        if not doc.get('searchable', True):
            continue
        for section in doc['sections']:
            for text in _chunks(section):
                chunks.append({'id': doc['id'], 'section': section['id'], 'title': doc['title'],
                    'heading': section['heading'], 'text': text, 'url': doc['url'],
                    'imported_at': doc['reviewed'], 'priority': doc.get('priority', 1),
                    'status': f"{doc['publisher']}; {doc['date']}. {doc.get('note', '')}".strip()})
    return chunks


def retrieve(question, docs=None, limit=3, budget=5600):
    if docs is None:
        docs = read_json(DATA / 'library.json', [])
        recovery = RESOURCES / 'collective-recovery.md'
        if recovery.exists():
            docs = docs + [{'title': 'Regroup and rebuild',
                            'imported_at': 'Bundled planning draft',
                            'text': recovery.read_text(encoding='utf-8')}]
        bundled = list(_reference_chunks())
    else:
        bundled = []
    words = set(_tokens(question))
    # A shared fault code must not retrieve a different equipment model's manual.
    # Alphanumeric model labels (TP1, EU2200i, R1) are more specific than E04.
    fault_codes=set(re.findall(r'\b(?:shows?|code|error|fault|warning)\s*[:#-]?\s*([a-z]+\d+[a-z0-9]*)',question.lower()))
    models={w for w in words if re.fullmatch(r'[a-z]+\d+[a-z0-9]*',w)
            and not re.fullmatch(r'e\d+',w) and w not in fault_codes}
    if models:
        docs=[d for d in docs if models & set(_tokens(d['title']+' '+d['text']))]
        bundled=[d for d in bundled if models & set(_tokens(d['title']+' '+d['text']))]
    chunks = bundled
    for doc in docs:
        for section in sections(doc['text']):
            for chunk in _chunks(section):
                chunks.append({'title':doc['title'], 'heading':section['heading'],
                    'imported_at':doc.get('imported_at',''), 'text':chunk,
                    'status':'User-supplied reference; not independently verified.'})
    counts = [Counter(_tokens(c['text'])) for c in chunks]
    frequencies = Counter(w for c in counts for w in c)
    average = sum(sum(c.values()) for c in counts) / max(1,len(counts))
    scored = []
    for chunk, terms in zip(chunks, counts):
        heading = set(_tokens(chunk['heading']))
        title = set(_tokens(chunk['title']))
        matched = words & (terms.keys() | heading | title)
        if not matched:
            continue
        score = 0
        for word in matched:
            rarity = math.log(1 + (len(chunks) + 1) / (frequencies[word] + 1))
            count = terms[word]
            score += rarity * (count * 2.2 / (count + 1.2 * (.25 + .75 * sum(terms.values()) / max(average,1)))
                               + (1.6 if word in heading else .2 if word in title else 0))
        score *= chunk.get('priority',1)
        if chunk['title'].lower() in question.lower():
            score *= 2
        scored.append((score, chunk))
    found, used, remaining = [], set(), budget
    strongest = max((score for score, _ in scored), default=0)
    for score, chunk in sorted(scored, key=lambda item:item[0], reverse=True):
        if score < strongest * .55:
            break
        key = (chunk['title'],chunk['heading'])
        if key in used or len(chunk['text'])>remaining:
            continue
        found.append({k:v for k,v in chunk.items() if k!='priority'})
        used.add(key);remaining-=len(chunk['text'])
        if len(found)>=limit:
            break
    return found


def search_references(question):
    words=set(_tokens(str(question)[:300]))
    found=[]
    for doc in references():
        for section in doc['sections']:
            matched=words & set(_tokens(doc['title']+' '+section['heading']+' '+section['text']))
            if matched:
                found.append((len(matched),{'id':doc['id'],'section':section['id'],
                    'title':doc['title'],'heading':section['heading']}))
    return [item for score,item in sorted(found,key=lambda x:x[0],reverse=True)[:30]]
