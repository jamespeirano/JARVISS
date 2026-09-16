"""Prepare only executable engines for the installer; never download user datasets."""
import json
import os
import platform
import shutil
import sys
from pathlib import Path

root = Path(__file__).resolve().parent.parent
work = root / 'build' / ('runtime-' + platform.system() + '-' + platform.machine())
work.mkdir(parents=True, exist_ok=True)
os.environ['JARVISS_ROOT'] = str(work)
os.environ['JARVISS_RESOURCES'] = str(root / 'resources')
sys.path.insert(0, str(root))
from jarviss.assets import prepare_runtime
from jarviss.map_setup import prepare_engine, prepare_map_tool

prepare_runtime()
prepare_engine()
prepare_map_tool()
dest = root / 'electron' / 'bundled-runtime'
if dest.exists(): shutil.rmtree(dest)
shutil.copytree(work / 'runtime', dest, ignore=shutil.ignore_patterns('*.zip', '*.tar.gz', '*.apk', '*.sh', '*.cmd'))
(dest / 'bundle.json').write_text(json.dumps({'platform':platform.system(), 'arch':platform.machine(),
    'contents':['llama.cpp', 'BRouter', 'Temurin Java runtime', 'PMTiles tool'], 'datasets_included':False}, indent=2))
print('Bundled engines ready. Models, voice data and maps are excluded.')
