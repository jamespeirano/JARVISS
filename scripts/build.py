"""Run on the target OS: python scripts/build.py (PyInstaller required)."""
import platform
import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parent.parent
args = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--onefile', '--windowed',
        '--name', 'JARVISS', '--distpath', str(root / 'dist'), '--add-data', f'{root / "resources"}:resources',
        '--collect-all', 'vosk', '--collect-all', 'sounddevice', '--collect-data', 'certifi', '--hidden-import', 'jarviss.library']
if platform.system() == 'Windows':
    args += ['--hidden-import', 'win32com.client', '--hidden-import', 'pythoncom']
args += [str(root / 'launch.py')]
subprocess.run(args, cwd=root, check=True)
