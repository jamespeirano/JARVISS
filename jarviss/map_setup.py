"""Explicit one-time US preparation. Downloading is never part of routing/search."""
import hashlib
import json
import platform
import queue
import re
import shutil
import subprocess
import threading
import time
import urllib.request
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from .assets import fetch_json, extract
from .network import tls_context
from .storage import ROOT, RUNTIME, BUNDLED_RUNTIME, RESOURCES, read_json, write_json
from .us_routing import USRouter, US_BOUNDS, BROUTER_VERSION, java_path
from .download_progress import download_label, transfer_text, map_transfer_text

SEGMENTS_URL = 'https://brouter.de/brouter/segments4/'
JAVA_TAG = 'jdk-21.0.12.1+1'
PMTILES_TAG = 'v1.31.2'
HEADERS = {'User-Agent':'JARVIS-Survival/1.0'}


def sha256(path):
    with Path(path).open('rb') as source: return hashlib.file_digest(source,'sha256').hexdigest()


def basemap_path(): return ROOT/'local-maps'/'us-z15.pmtiles'


def basemap_issue(path):
    """Cheap startup check. Neither provider publishes checksums, so the size recorded at download is the reference."""
    path=Path(path);manifest=read_json(path.parent/'manifest.json',{})
    if manifest.get('file')==path.name and type(manifest.get('size_bytes')) is int and manifest['size_bytes']!=path.stat().st_size:
        return (f'The saved US map is {path.stat().st_size:,} bytes but its download record says {manifest["size_bytes"]:,}. '
                'Open setup and choose Check setup to verify and repair it.')
    return None


def verify_us(progress=print):
    """Re-hash installed US data against the hashes recorded at download and remove what no longer matches.
    Reads in chunks so pause and progress land between them; the map alone is about 21 GB."""
    target=basemap_path();manifest=read_json(target.parent/'manifest.json',{});router=USRouter();checks=[]
    if target.is_file() and manifest.get('file')==target.name: checks.append((target,manifest.get('sha256')))
    for row in router.manifest.get('files',[]):
        path=router.directory/'segments4'/row['name']
        if path.is_file(): checks.append((path,read_json(path.with_suffix('.receipt.json'),{}).get('sha256')))
    total=sum(path.stat().st_size for path,_ in checks) or 1;done=0;last=0;removed=[]
    progress('Checking US map files… 0%')
    for path,expected in checks:
        digest=hashlib.sha256()
        with path.open('rb') as source:
            while chunk:=source.read(8*1024*1024):
                digest.update(chunk);done+=len(chunk)
                if time.monotonic()-last>=1: progress(f'Checking US map files… {done*100//total}%');last=time.monotonic()
        if path==target and not expected:
            # A 0.2.3 map was verified by the extractor but never hashed; record it rather than discard it.
            write_json(target.parent/'manifest.json',dict(manifest,sha256=digest.hexdigest()));continue
        if digest.hexdigest()!=expected:
            path.unlink();removed.append(path)
            if path!=target: path.with_suffix('.receipt.json').unlink(missing_ok=True)
    progress('Checking US map files… 100%')
    return removed


def remaining_bytes(target, url, size, checksum=None):
    """Credit only completed files or partials belonging to this exact transfer."""
    target = Path(target)
    try:
        if target.is_file() and target.stat().st_size == size: return 0
        part = target.with_suffix(target.suffix+'.part')
        identity = {'url':url, 'size':size, 'checksum':checksum}
        if part.is_file() and read_json(part.with_suffix(part.suffix+'.json'),{}) == identity:
            # A full but unverified partial may need downloading again.
            saved = part.stat().st_size
            if saved < size: return size-saved
    except FileNotFoundError:
        pass  # The download may have just renamed the partial.
    return size


def download_file(url, target, progress=print, size=None, checksum=None):
    """Retain partial downloads, validate ranges, and publish only complete files."""
    target = Path(target); target.parent.mkdir(parents=True,exist_ok=True)
    label = download_label(target)
    checking = label if label.startswith('AI ') else label.lower()
    progress(f'Checking {checking} files…')
    if target.is_file() and (size is None or target.stat().st_size == size) and (not checksum or sha256(target)==checksum):
        return sha256(target)
    part = target.with_suffix(target.suffix+'.part')
    marker = part.with_suffix(part.suffix+'.json')
    identity = {'url':url,'size':size,'checksum':checksum}
    if read_json(marker,{}) != identity:
        part.unlink(missing_ok=True)
        write_json(marker,identity)
    attempt = failures = 0
    while True:
        received = 0
        try:
            offset = part.stat().st_size if part.exists() else 0
            if size and offset >= size:
                part.unlink(); offset=0
            headers = dict(HEADERS)
            if offset: headers['Range']=f'bytes={offset}-'
            with urllib.request.urlopen(urllib.request.Request(url,headers=headers),timeout=90,context=tls_context()) as response:
                resumed = response.status == 206
                if resumed and not response.headers.get('Content-Range','').startswith(f'bytes {offset}-'):
                    part.unlink(); raise ValueError('Server returned an incorrect download range.')
                if not resumed: offset=0
                total = size or (int(response.headers.get('Content-Length',0))+offset)
                done, last, started = offset, 0, time.monotonic()
                with part.open('ab' if resumed else 'wb') as output:
                    while chunk := response.read(64*1024):
                        output.write(chunk); done+=len(chunk); received+=len(chunk)
                        if time.monotonic()-last>1:
                            elapsed = time.monotonic()-started
                            progress(transfer_text(label,done,total,(done-offset)/elapsed if elapsed >= 1 else 0))
                            last=time.monotonic()
                if total and done != total: raise ValueError('Incomplete download; retry to resume.')
            progress(f'Checking {checking} download…')
            digest=sha256(part)
            if checksum and digest!=checksum:
                part.unlink(); raise ValueError('Download checksum mismatch; retrying.')
            part.replace(target); marker.unlink(missing_ok=True)
            return digest
        except (OSError,ValueError) as error:
            # A partial that already spans the whole file (killed before publishing) can never resume.
            if getattr(error,'code',None)==416: part.unlink(missing_ok=True)
            # A link that keeps delivering bytes earns fresh attempts; a dead one gets four, 1/2/4 s apart.
            attempt, failures = (0 if received else attempt+1), failures+1
            if attempt>3 or failures>=12: raise
            time.sleep(min(4, 2**(attempt-1)) if attempt else 1)


def platform_name():
    system = {'Darwin':'mac','Windows':'windows','Linux':'linux'}.get(platform.system())
    arch = {'arm64':'aarch64','aarch64':'aarch64','amd64':'x64','x86_64':'x64'}.get(platform.machine().lower())
    if not system or not arch: raise ValueError('Offline map setup does not yet support this operating system or processor.')
    return system,arch


def prepare_engine(progress=print):
    router = USRouter()
    base=RUNTIME/'brouter';base.mkdir(parents=True,exist_ok=True)
    if not router.jar.exists():
        release=fetch_json(f'https://api.github.com/repos/abrensch/brouter/releases/tags/v{BROUTER_VERSION}')
        asset=next(a for a in release['assets'] if a['name']==f'brouter-{BROUTER_VERSION}.zip')
        archive=base/asset['name']
        download_file(asset['browser_download_url'],archive,progress,asset['size'],(asset.get('digest') or '').removeprefix('sha256:') or None)
        extract(archive,base)
    if not java_path():
        system,arch=platform_name()
        release=fetch_json('https://api.github.com/repos/adoptium/temurin21-binaries/releases/tags/'+urllib.parse.quote(JAVA_TAG,safe=''))
        asset=next((a for a in release['assets'] if a['name'].startswith(f'OpenJDK21U-jre_{arch}_{system}_hotspot_') and a['name'].endswith(('.tar.gz','.zip'))),None)
        if not asset: raise ValueError('No offline Java runtime is available for this processor.')
        with urllib.request.urlopen(asset['browser_download_url']+'.sha256.txt',timeout=60,context=tls_context()) as response: checksum=response.read().decode().split()[0]
        archive=base/asset['name']
        download_file(asset['browser_download_url'],archive,progress,asset['size'],checksum)
        extract(archive,base/'java')
        if java_path() and system!='windows': java_path().chmod(0o755)
    if not java_path() or not router.jar.is_file(): raise ValueError('Offline routing engine installation is incomplete.')


def in_us(name):
    a,b=re.findall(r'([EWNS])(\d+)',name)
    x=int(a[1])*(-1 if a[0]=='W' else 1);y=int(b[1])*(-1 if b[0]=='S' else 1)
    return any(x<e and x+5>w and y<n and y+5>s for w,s,e,n in US_BOUNDS)


def select_us_files(html):
    pattern=r'href="([EW]\d+_[NS]\d+\.rd5)"[^\n]*?</a>\s+([^\n]+?)\s+(\d+)\s*\n'
    files=[{'name':name,'size':int(size),'provider_modified':stamp.strip()} for name,stamp,size in re.findall(pattern,html) if in_us(name)]
    # Every US tile the page links must also have parsed a date and size; otherwise coverage silently ends at a hole.
    linked=sum(in_us(name) for name in re.findall(r'href="([EW]\d+_[NS]\d+\.rd5)"',html))
    if len(files)<100 or len(files)<linked: raise ValueError('Could not verify the full US routing download list. Retry setup while connected.')
    return files


def prepare_routing(progress=print):
    router=USRouter()
    if router.status()['ready']:
        progress('US walking directions are already installed.');return
    prepare_engine(progress)
    progress('Checking the US-wide walking network…')
    with urllib.request.urlopen(SEGMENTS_URL,timeout=60,context=tls_context()) as response: files=select_us_files(response.read().decode())
    manifest={'version':1,'complete':False,'source':SEGMENTS_URL,'coverage':US_BOUNDS,'engine':BROUTER_VERSION,'files':files}
    write_json(router.directory/'manifest.json',manifest)
    lock=threading.Lock();done=0
    def fetch(row):
        nonlocal done
        # Check pause before queued work opens another network connection.
        progress(f'US directions: {done} / {len(files)} files saved')
        path=router.directory/'segments4'/row['name']
        # The provider refreshes the graph. Do not mix a stale completed tile with a new revision of equal size.
        receipt=read_json(path.with_suffix('.receipt.json'),{})
        if path.exists() and receipt.get('provider_modified')!=row['provider_modified']: path.unlink()
        row['sha256']=download_file(SEGMENTS_URL+row['name'],path,lambda text: progress('US directions · '+text),row['size'])
        write_json(path.with_suffix('.receipt.json'),row)
        with lock:
            done+=1;progress(f'US directions: {done} / {len(files)} files saved')
    with ThreadPoolExecutor(max_workers=3) as pool:list(pool.map(fetch,files))
    manifest.update(complete=True,downloaded_at=datetime.now(timezone.utc).isoformat())
    write_json(router.directory/'manifest.json',manifest)
    progress('US walking directions are installed for offline use.')


def prepare_map_tool(progress=print):
    name='pmtiles.exe' if platform.system()=='Windows' else 'pmtiles'
    bundled=BUNDLED_RUNTIME/'pmtiles'/name
    if bundled.is_file(): return bundled
    root=RUNTIME/'pmtiles';root.mkdir(parents=True,exist_ok=True)
    executable=root/name
    if not executable.exists():
        release=fetch_json('https://api.github.com/repos/protomaps/go-pmtiles/releases/tags/'+PMTILES_TAG)
        _,arch=platform_name();arch='arm64' if arch=='aarch64' else 'x86_64'
        asset=next(a for a in release['assets'] if f'_{platform.system()}_{arch}.' in a['name'])
        archive=root/asset['name']
        download_file(asset['browser_download_url'],archive,progress,asset['size'],(asset.get('digest') or '').removeprefix('sha256:') or None)
        extract(archive,root)
        if platform.system()!='Windows': executable.chmod(0o755)
    return executable


def prepare_basemap(progress=print, cancel=None):
    from .atlas import TileArchive
    target=basemap_path()
    if target.is_file():
        try: TileArchive(target);progress('US basemap is already installed.');return target
        except ValueError as error:
            progress(f'The saved US map is unreadable ({error}). Downloading it again.')
            target.unlink()
    executable=prepare_map_tool(progress)
    builds=fetch_json('https://build-metadata.protomaps.dev/builds.json')
    build=next(b for b in sorted(builds,key=lambda b:b['key'],reverse=True) if re.fullmatch(r'\d{8}\.pmtiles',b['key']) and str(b.get('version','')).startswith('4.'))
    source='https://build.protomaps.com/'+build['key']
    target.parent.mkdir(parents=True,exist_ok=True)
    coverage=target.parent/'us-coverage.geojson';shutil.copyfile(RESOURCES/'routing'/'us-coverage.geojson',coverage)
    partial=target.with_suffix('.partial');partial.unlink(missing_ok=True)
    progress('Downloading US map. Keep Jarvis open; chat is available once its model is ready.')
    process=subprocess.Popen([str(executable),'extract',source,str(partial),f'--region={coverage}','--maxzoom=15','--download-threads=3'],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace',
                             creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    lines=queue.Queue()
    def read():
        try:
            for line in process.stdout: lines.put(line)
        finally: lines.put(None)
    threading.Thread(target=read,daemon=True).start()
    last_update = 0; extracted = False
    try:
        while True:
            if cancel and cancel.is_set():
                from .setup import SetupPaused
                raise SetupPaused(note=' The unfinished US map must restart; other files are kept.')
            try: line=lines.get(timeout=.2)
            except queue.Empty: continue
            if line is None: break
            text = map_transfer_text(line)
            if text and (time.monotonic()-last_update >= 1 or '100%' in text):
                progress(text);last_update=time.monotonic()
        if process.wait():raise ValueError('US basemap download did not finish. Retry setup while connected.')
        extracted = True
    finally:
        if process.poll() is None:
            process.terminate()
            try:process.wait(timeout=5)
            except subprocess.TimeoutExpired:process.kill();process.wait()
        process.stdout.close()
        # The extractor cannot resume, so a paused or failed partial is only wasted space.
        if not extracted: partial.unlink(missing_ok=True)
    progress('Checking US map download…')
    subprocess.run([str(executable),'verify',str(partial)],check=True,capture_output=True)
    archive=TileArchive(partial)
    digest=sha256(partial)
    progress('US map verified')
    partial.replace(target)
    write_json(target.parent/'manifest.json',{'file':target.name,'size_bytes':target.stat().st_size,'source':source,
        'completed_at':datetime.now(timezone.utc).isoformat(),'source_osm_replication_time':archive.pack['osm_timestamp'],
        'coverage_file':coverage.name,'sha256':digest})
    return target


def prepare_us(progress=print, cancel=None):
    archive=prepare_basemap(progress, cancel)
    prepare_routing(progress)
    return archive
