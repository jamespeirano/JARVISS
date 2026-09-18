import json
import os
import sys
import threading
from pathlib import Path

ROOT = Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent.parent
ROOT = Path(os.environ.get('JARVISS_ROOT', ROOT)).resolve()
RESOURCES = Path(os.environ.get('JARVISS_RESOURCES', Path(getattr(sys, '_MEIPASS', ROOT)) / 'resources'))
DATA = Path(os.environ.get('JARVISS_DATA', ROOT / 'local-data')).resolve()
MODELS = ROOT / 'models'
RUNTIME = ROOT / 'runtime'
BUNDLED_RUNTIME = Path(os.environ.get('JARVISS_BUNDLED_RUNTIME', RUNTIME)).resolve()


_locks, _registry = {}, threading.Lock()


def _lock(path):
    with _registry:
        return _locks.setdefault(str(path), threading.Lock())


def read_json(path, default):
    path = Path(path)
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except FileNotFoundError:
        return default
    except (ValueError, UnicodeDecodeError):
        # Keep the damaged file for recovery instead of refusing to start.
        os.replace(path, path.with_suffix(path.suffix + '.corrupt'))
        return default


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(f'{path.suffix}.{os.getpid()}.tmp')
    # Requests run on separate threads; serialize writers of the same file.
    with _lock(path):
        temp.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding='utf-8')
        os.replace(temp, path)


def model_path(value):
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def portable_path(path):
    try:
        return str(Path(path).resolve().relative_to(ROOT))
    except ValueError:
        return str(Path(path).resolve())
