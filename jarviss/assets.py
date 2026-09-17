"""Explicit online preparation only. Chat never calls this module."""
import hashlib
import json
import os
import platform
import tarfile
import tempfile
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path
from .storage import MODELS, RUNTIME, BUNDLED_RUNTIME, DATA, write_json, read_json, portable_path
from .network import tls_context

LLAMA_TAG = 'b10948'
VOICE_NAME = 'vosk-model-en-us-0.22-lgraph'
VOICE_SHA256 = 'd9838b4aaa82a75c4a17f5aca300eaca129aaab2a7cbf951bafbb500eb9c4334'
VOICE_URLS = (
    'https://huggingface.co/rhasspy/vosk-models/resolve/8e5f85a35b402c35022b5af62c101dd6a06d0219/en/' + VOICE_NAME + '.zip',
    f'https://alphacephei.com/vosk/models/{VOICE_NAME}.zip',
)
TTS_FILES = {
    'kokoro-v1.0.onnx': 'beb0d1848dee9a49da392cc3df26958d46cfa35d321edf434f52949153f0df3a',
    'voices-v1.0.bin': 'bca610b8308e8d99f32e6fe4197e7ec01679264efed0cac9140fe9c29f1fbf7d',
}
HEADERS = {'User-Agent': 'JARVISS/0.2'}


def fetch_json(url):
    headers = dict(HEADERS)
    # CI runners share a small anonymous GitHub API quota. Keep the build's
    # short-lived token confined to GitHub metadata requests.
    parsed = urllib.parse.urlsplit(url)
    token = os.environ.get('JARVIS_BUILD_GITHUB_TOKEN')
    if token and parsed.scheme == 'https' and parsed.netloc == 'api.github.com':
        headers['Authorization'] = 'Bearer ' + token
    opener = urllib.request.build_opener(_MetadataRedirectHandler(),
                                         urllib.request.HTTPSHandler(context=tls_context()))
    with opener.open(urllib.request.Request(url, headers=headers), timeout=60) as response:
        return json.load(response)


class _MetadataRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
        if redirected is not None:
            redirected.remove_header('Authorization')
        return redirected


def download(url, target, progress=print, expected_sha=None):
    # Shared resumable transfer; kept here for older preparation callers.
    from .map_setup import download_file
    return download_file(url, target, progress, checksum=expected_sha.removeprefix('sha256:') if expected_sha else None)


def extract(archive, dest):
    dest = Path(dest).resolve()
    dest.mkdir(parents=True, exist_ok=True)
    if zipfile.is_zipfile(archive):
        with zipfile.ZipFile(archive) as package:
            for info in package.infolist():
                entry = (dest / info.filename).resolve()
                if not entry.is_relative_to(dest) or (info.external_attr >> 16) & 0o170000 == 0o120000:
                    raise ValueError('Unsafe archive entry')
            package.extractall(dest)
    else:
        with tarfile.open(archive) as package:
            package.extractall(dest, filter='data')


def find_server():
    name = 'llama-server.exe' if platform.system() == 'Windows' else 'llama-server'
    return next((p for root in (BUNDLED_RUNTIME, RUNTIME) if root.exists() for p in root.rglob(name)), None)


def prepare_runtime(progress=print):
    existing = find_server()
    if existing:
        return existing
    system, machine = platform.system(), platform.machine().lower()
    if system == 'Windows' and machine in ('amd64', 'x86_64'):
        suffix = 'bin-win-vulkan-x64.zip'
    elif system == 'Darwin':
        suffix = 'bin-macos-' + ('arm64' if machine == 'arm64' else 'x64') + '.tar.gz'
    elif system == 'Linux' and machine in ('amd64', 'x86_64'):
        suffix = 'bin-ubuntu-x64.tar.gz'
    else:
        raise RuntimeError('This processor is not supported by the bundled model engine.')
    release = fetch_json(f'https://api.github.com/repos/ggml-org/llama.cpp/releases/tags/{LLAMA_TAG}')
    asset = next(a for a in release['assets'] if a['name'].endswith(suffix))
    with tempfile.TemporaryDirectory() as temp:
        archive = Path(temp) / asset['name']
        sha = download(asset['browser_download_url'], archive, progress, asset.get('digest'))
        extract(archive, RUNTIME)
    server = find_server()
    if not server:
        raise RuntimeError('Downloaded runtime contains no llama-server.')
    if system != 'Windows':
        server.chmod(server.stat().st_mode | 0o111)
    write_json(RUNTIME / 'source.json', {'tag': LLAMA_TAG, 'url': asset['browser_download_url'], 'sha256': sha})
    return server


def prepare_voice(progress=print):
    prepare_tts(progress)
    dest = MODELS / VOICE_NAME
    if (dest / 'am' / 'final.mdl').exists():
        return dest
    archive = MODELS / '.downloads' / (VOICE_NAME + '.zip')
    # Both hosts must supply the exact same, checksum-pinned upstream archive.
    for index, url in enumerate(VOICE_URLS):
        try:
            sha = download(url, archive, progress, VOICE_SHA256)
            break
        except (OSError, ValueError):
            if index == len(VOICE_URLS) - 1:
                raise
            progress('Retrying voice download…')
    extract(archive, MODELS)
    archive.unlink(missing_ok=True)
    write_json(dest / 'download-source.json', {'url': url, 'sha256': sha, 'license': 'Apache-2.0'})
    return dest


def prepare_tts(progress=print):
    dest = MODELS / 'kokoro'
    records = []
    for name, expected in TTS_FILES.items():
        path = dest / name
        url = f'https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1/{name}'
        if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            download(url, path, progress, expected)
        records.append({'url': url, 'sha256': expected})
    write_json(dest / 'source.json', {'model': 'Kokoro 82M v1.0', 'license': 'Apache-2.0', 'files': records})
    return dest


def prepare_qwen(progress=print):
    # Settings downloads use the same hardware recommendations as setup.
    from .setup import model_catalog, prepare_model
    from .hardware import inspect, recommend
    rows, selected = recommend(model_catalog(), inspect())
    if not selected: raise RuntimeError('Not enough available memory. Close other apps and check again.')
    prepare_runtime(progress); prepare_voice(progress)
    dest = prepare_model(selected, progress)
    settings = read_json(DATA / 'settings.json', {})
    settings.update(model=portable_path(dest), model_id=selected, gpu_layers='auto', model_context=next(r['context'] for r in rows if r['id']==selected))
    write_json(DATA / 'settings.json', settings)
    return dest
