import json
import os
import re
import secrets
import socket
import subprocess
import threading
import time
import urllib.request
from .storage import DATA
from .assets import find_server


class LocalModel:
    def __init__(self):
        self.process = None
        self.url = None
        self.log = None
        self.lock = threading.Lock()
        self.closed = threading.Event()
        self.api_key = secrets.token_urlsafe(32)
        self.allocated_memory = 0

    def start(self, path, gpu_layers='auto', context=8192):
        import psutil
        available_before = psutil.virtual_memory().available
        server = find_server()
        if not server:
            raise RuntimeError('Prepare the local runtime in Setup first.')
        if not path.is_file() or path.suffix.lower() != '.gguf':
            raise ValueError('Choose a downloaded GGUF model in Setup.')
        with self.lock:
            if self.closed.is_set():
                raise RuntimeError('Assistant is closing.')
            with socket.socket() as sock:
                sock.bind(('127.0.0.1', 0))
                port = sock.getsockname()[1]
            DATA.mkdir(parents=True, exist_ok=True)
            self.log = (DATA / 'model.log').open('w', encoding='utf-8')
            args = [str(server), '-m', str(path), '--host', '127.0.0.1', '--port', str(port),
                    '-c', str(context), '-ngl', str(gpu_layers), '--parallel', '1', '--jinja',
                    '--chat-template-kwargs', '{"enable_thinking":false}']
            self.process = subprocess.Popen(args, cwd=server.parent, stdout=self.log, stderr=self.log,
                                            env={**os.environ, 'LLAMA_API_KEY':self.api_key},
                                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            self.url = f'http://127.0.0.1:{port}'
        for _ in range(240):
            if self.closed.is_set():
                raise RuntimeError('Assistant closed.')
            if self.process.poll() is not None:
                self.stop()
                raise RuntimeError('Model failed to load. See local-data/model.log. Try CPU mode in Setup.')
            try:
                health=urllib.request.Request(self.url + '/health',headers={'Authorization':'Bearer '+self.api_key})
                with urllib.request.urlopen(health, timeout=1) as response:
                    if response.status == 200:
                        self.allocated_memory = max(0, available_before - psutil.virtual_memory().available)
                        return
            except (OSError, ValueError):
                pass
            self.closed.wait(0.5)
        self.stop()
        raise TimeoutError('Model did not load within two minutes.')

    def chat(self, messages, on_sentence=None, max_tokens=600, max_sentences=None):
        if not self.process or self.process.poll() is not None:
            raise RuntimeError('Start a local model in Setup.')
        payload = {'messages': messages, 'temperature': 0.25, 'max_tokens': max_tokens,
                   'stream': bool(on_sentence), 'chat_template_kwargs': {'enable_thinking': False}}
        request = urllib.request.Request(self.url + '/v1/chat/completions',
                                        data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json','Authorization':'Bearer '+self.api_key})
        with urllib.request.urlopen(request, timeout=240) as response:
            if on_sentence:
                answer, pending = '', ''
                delivered = []
                for line in response:
                    if not line.startswith(b'data: '): continue
                    data = line[6:].strip()
                    if data == b'[DONE]': break
                    delta = json.loads(data)['choices'][0].get('delta', {}).get('content') or ''
                    answer += delta; pending += delta
                    # Never speak a reasoning section even if a template emits one.
                    if '<think>' in pending:
                        if '</think>' not in pending: continue
                        pending = re.sub(r'<think>.*?</think>', '', pending, flags=re.S)
                    while match := re.search(r'[.!?][\s\n]+|\n', pending):
                        sentence = pending[:match.end()].strip(); pending = pending[match.end():]
                        if sentence:
                            on_sentence(sentence); delivered.append(sentence)
                        if max_sentences and len(delivered) >= max_sentences: break
                    if max_sentences and len(delivered) >= max_sentences:
                        pending = ''; break
                if pending.strip() and '<think>' not in pending:
                    on_sentence(pending.strip()); delivered.append(pending.strip())
                if max_sentences: answer = ' '.join(delivered)
            else:
                result = json.load(response)
                answer = result['choices'][0]['message'].get('content') or ''
        answer = re.sub(r'<think>.*?</think>', '', answer, flags=re.S).strip()
        if not answer:
            raise RuntimeError('Model returned no answer. Try another GGUF model.')
        return answer

    def stop(self):
        with self.lock:
            if self.process and self.process.poll() is None:
                self.process.terminate()
                try:
                    self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=5)
            self.process = None
            self.allocated_memory = 0
            if self.log:
                self.log.close()
                self.log = None

    def close(self):
        self.closed.set()
        self.stop()
