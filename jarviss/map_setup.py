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

SEGMENTS_URL = 'https://brouter.de/brouter/segments4/'
JAVA_TAG = 'jdk-21.0.12.1+1'
PMTILES_TAG = 'v1.31.2'
HEADERS = {'User-Agent':'JARVIS-Survival/1.0'}


def sha256(path):
    with Path(path).open('rb') as source: return hashlib.file_digest(source,'sha256').hexdigest()


def download_file(url, target, progress=print, size=None, checksum=None):
    """Retain partial downloads, validate ranges, and publish only complete files."""
    target = Path(target); target.parent.mkdir(parents=True,exist_ok=True)
    if target.is_file() and (size is None or target.stat().st_size == size) and (not checksum or sha256(target)==checksum):
        return sha256(target)
    part = target.with_suffix(target.suffix+'.part')
    marker = part.with_suffix(part.suffix+'.json')
    identity = {'url':url,'size':size,'checksum':checksum}
    if read_json(marker,{}) != identity:
        part.unlink(missing_ok=True)
        write_json(marker,identity)
    for attempt in range(3):
        try:
            offset = part.stat().st_size if part.exists() else 0
            if size and offset >= size:
                part.unlink(); offset=0
            headers = dict(HEADERS)
            if offset: headers['Range']=f'bytes={offset}-'
            with urllib.request.urlopen(urllib.request.Request(url,headers=headers),timeout=90,context=tls_context()) as response:
                resumed = response.status == 206
                if resumed and not response.headers.get('Content-Range','').startswith(f'bytes {offset}-'):
                    raise ValueError('Server returned an incorrect download range.')
                if not resumed: offset=0
                total = size or (int(response.headers.get('Content-Length',0))+offset)
                done, last = offset, 0
                with part.open('ab' if resumed else 'wb') as output:
                    while chunk := response.read(64*1024):
                        output.write(chunk); done+=len(chunk)
                        if time.monotonic()-last>1:
                            progress(f'{target.name}: {done/1048576:.0f} MB'+(f' / {total/1048576:.0f} MB' if total else ''))
                            last=time.monotonic()
                if total and done != total: raise ValueError('Incomplete download; retry to resume.')
            digest=sha256(part)
            if checksum and digest!=checksum:
                part.unlink(); raise ValueError('Download checksum mismatch; retrying.')
            part.replace(target); marker.unlink(missing_ok=True)
            return digest
        except (OSError,ValueError):
            if attempt==2: raise
            time.sleep(1)


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


def select_us_files(html):
    files=[]
    pattern=r'href="([EW]\d+_[NS]\d+\.rd5)"[^\n]*?</a>\s+([^\n]+?)\s+(\d+)\s*\n'
    for name,stamp,size in re.findall(pattern,html):
        a,b=re.findall(r'([EWNS])(\d+)',name)
        x=int(a[1])*(-1 if a[0]=='W' else 1);y=int(b[1])*(-1 if b[0]=='S' else 1)
        if any(x<e and x+5>w and y<n and y+5>s for w,s,e,n in US_BOUNDS):
            files.append({'name':name,'size':int(size),'provider_modified':stamp.strip()})
    if len(files)<100: raise ValueError('Could not verify the full US routing download list. Retry setup while connected.')
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
        if path.exists() and receipt and receipt.get('provider_modified')!=row['provider_modified']: path.unlink()
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
    target=ROOT/'local-maps'/'us-z15.pmtiles'
    if target.is_file():
        TileArchive(target);progress('US basemap is already installed.');return target
    executable=prepare_map_tool(progress)
    builds=fetch_json('https://build-metadata.protomaps.dev/builds.json')
    build=next(b for b in sorted(builds,key=lambda b:b['key'],reverse=True) if re.fullmatch(r'\d{8}\.pmtiles',b['key']) and str(b.get('version','')).startswith('4.'))
    source='https://build.protomaps.com/'+build['key']
    target.parent.mkdir(parents=True,exist_ok=True)
    coverage=target.parent/'us-coverage.geojson';shutil.copyfile(RESOURCES/'routing'/'us-coverage.geojson',coverage)
    partial=target.with_suffix('.partial');partial.unlink(missing_ok=True)
    progress('Downloading the US basemap (about 19 GB). Keep Jarvis open until setup finishes.')
    process=subprocess.Popen([str(executable),'extract',source,str(partial),f'--region={coverage}','--maxzoom=15','--download-threads=3'],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,
                             creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    lines=queue.Queue()
    def read():
        for line in process.stdout: lines.put(line)
        lines.put(None)
    threading.Thread(target=read,daemon=True).start()
    try:
        while True:
            if cancel and cancel.is_set():
                from .setup import SetupPaused
                raise SetupPaused()
            try: line=lines.get(timeout=.2)
            except queue.Empty: continue
            if line is None: break
            if line.strip():progress('US basemap · '+line.strip()[-250:])
        if process.wait():raise ValueError('US basemap download did not finish. Retry setup while connected.')
    finally:
        if process.poll() is None:
            process.terminate()
            try:process.wait(timeout=5)
            except subprocess.TimeoutExpired:process.kill();process.wait()
        process.stdout.close()
    subprocess.run([str(executable),'verify',str(partial)],check=True,capture_output=True)
    archive=TileArchive(partial)
    partial.replace(target)
    write_json(target.parent/'manifest.json',{'file':target.name,'size_bytes':target.stat().st_size,'source':source,
        'completed_at':datetime.now(timezone.utc).isoformat(),'source_osm_replication_time':archive.pack['osm_timestamp'],
        'coverage_file':coverage.name,'sha256':sha256(target)})
    return target


def prepare_us(progress=print, cancel=None):
    archive=prepare_basemap(progress, cancel)
    prepare_routing(progress)
    return archive
