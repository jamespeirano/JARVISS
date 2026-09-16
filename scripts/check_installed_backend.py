import json, os, subprocess, sys, tempfile, threading
from pathlib import Path
installed = Path(sys.argv[1])
backend = installed / 'resources/backend/jarviss-service.exe'
with tempfile.TemporaryDirectory(prefix='jarvis-signed-check-') as folder:
    env = dict(os.environ, JARVISS_ROOT=folder,
        JARVISS_BUNDLED_RUNTIME=str(installed / 'resources/runtime'), PYTHONIOENCODING='utf-8')
    process = subprocess.Popen([str(backend)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True, encoding='utf-8', env=env, cwd=folder)
    timeout = threading.Timer(90, process.kill)
    timeout.start()
    try:
        for request_id, method in [(1, 'state'), (2, 'setup_plan')]:
            process.stdin.write(json.dumps({'id': request_id, 'method': method, 'args': {}})+'\n')
            process.stdin.flush()
            for line in process.stdout:
                response = json.loads(line)
                if response.get('id') != request_id: continue
                assert 'error' not in response, response
                result = response['result']
                if method == 'state':
                    assert result['ready'] is False
                    assert result['history'] == []
                else:
                    assert result['hardware']['system'] == 'Windows', result['hardware']
                    assert len(result['models']) >= 2
                    assert result['components']['guides'] is True
                    assert result['download_bytes'] > 0
                print('PASS installed backend:', method)
                break
            else:
                raise RuntimeError('Backend stopped before responding: '+process.stderr.read())
        process.stdin.write('{"id":0,"method":"shutdown"}\n')
        process.stdin.flush()
        process.wait(timeout=20)
        assert process.returncode == 0, process.stderr.read()
    finally:
        timeout.cancel()
        if process.poll() is None: process.kill()
