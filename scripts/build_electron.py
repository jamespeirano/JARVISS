"""Build the native Python sidecar and Electron application on the target OS."""
import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parent.parent
subprocess.run([sys.executable, str(root / 'scripts/bundle_runtime.py')], cwd=root, check=True)
args = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--onefile',
        '--name', 'jarviss-service', '--distpath', str(root / 'electron/backend'),
        '--add-data', f'{root / "resources"}:resources', '--collect-all', 'vosk',
        '--collect-all', 'sounddevice', '--collect-all', 'kokoro_onnx',
        '--collect-all', 'espeakng_loader', '--collect-all', 'phonemizer',
        '--collect-all', 'language_tags',
        '--collect-all', 'onnxruntime', '--copy-metadata', 'kokoro-onnx',
        '--copy-metadata', 'phonemizer-fork', '--collect-all', 'psutil', '--collect-all', 'pypdf']
if sys.platform == 'win32': args += ['--icon', str(root / 'electron/icons/icon.ico')]
if sys.platform == 'win32': args += ['--hidden-import','win32com.client','--hidden-import','pythoncom']
subprocess.run(args + [str(root / 'service.py')], cwd=root, check=True)
subprocess.run(['npm', 'run', 'installer'], cwd=root / 'electron', check=True, shell=sys.platform == 'win32')
