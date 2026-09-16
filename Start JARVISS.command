#!/bin/bash
set -e
cd "$(dirname "$0")"
if ! command -v python3 >/dev/null; then
  echo 'Install Python 3.12 from python.org, then open this file again.'
  read -r
  exit 1
fi
if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
  .venv/bin/python -m pip install -r requirements.txt -c constraints.txt
fi
.venv/bin/python -c 'import vosk, sounddevice, pmtiles, mapbox_vector_tile, pypdf' 2>/dev/null || .venv/bin/python -m pip install -r requirements.txt -c constraints.txt
cd electron
if [ ! -d node_modules/electron ] || [ ! -d node_modules/maplibre-gl ] || [ ! -d node_modules/esbuild ]; then npm ci; fi
exec npm start
