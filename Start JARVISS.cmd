@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  py -3.12 -m venv .venv
  if errorlevel 1 goto failed
  .venv\Scripts\python.exe -m pip install -r requirements.txt -c constraints.txt
  if errorlevel 1 goto failed
)
.venv\Scripts\python.exe -c "import vosk, sounddevice, win32com.client, pmtiles, mapbox_vector_tile, pypdf"
if errorlevel 1 (
  .venv\Scripts\python.exe -m pip install -r requirements.txt -c constraints.txt
  if errorlevel 1 goto failed
)
cd electron
if not exist "node_modules\electron" call npm ci
if not exist "node_modules\maplibre-gl" call npm ci
if not exist "node_modules\esbuild" call npm ci
if errorlevel 1 goto failed
call npm start
exit /b
:failed
echo Setup failed. Install Python 3.12 and Node 24, then run this file while online.
pause
