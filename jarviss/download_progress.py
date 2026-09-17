"""User-facing transfer progress, with decimal units matching the setup totals."""
from pathlib import Path
import re


def size_text(size):
    return f'{size/1e9:.1f} GB' if size >= 1e9 else f'{size/1e6:.1f} MB'


def download_label(path):
    name = Path(path).name.lower()
    if name.endswith('.gguf'): return 'AI model'
    if name.endswith('.rd5'): return 'Walking directions'
    if 'vosk' in name: return 'Speech recognition'
    if 'kokoro' in name: return 'Voice engine'
    if 'voices' in name: return 'Voice choices'
    if 'pmtiles' in name: return 'Map engine'
    if 'brouter' in name or 'openjdk' in name: return 'Walking directions engine'
    return 'Model engine'


def transfer_text(label, done, total=0, rate=0):
    text = f'{label} · {size_text(done)}'
    if total: text += f' / {size_text(total)} · {min(100, int(done*100/total))}%'
    if rate > 0:
        text += f' · {size_text(rate)}/s'
        if total > done:
            seconds = max(1, round((total-done)/rate))
            text += f' · about {seconds} sec left' if seconds < 60 else f' · about {(seconds+59)//60} min left'
    return text


def map_transfer_text(line):
    """Read only the pinned PMTiles tool's transfer counters, never its logs.

    The tool preallocates a sparse output file, so file size is not progress.
    Both its progressbar and our setup estimates use decimal byte units.
    """
    match = re.search(r'fetching chunks\s+(\d+)%.*?\(([\d.]+)\s*([kMGT]?B)?/([\d.]+)\s*([kMGT]?B),\s*([\d.]+)\s*([kMGT]?B)/s\)', line)
    if not match: return None
    percent, done, unit, total, total_unit, rate, rate_unit = match.groups()
    units = {'B':1,'kB':1000,'MB':1e6,'GB':1e9,'TB':1e12}
    done, total, rate = float(done)*units[unit or total_unit], float(total)*units[total_unit], float(rate)*units[rate_unit]
    text = transfer_text('US map',done,total,rate)
    # Counts are rounded by the upstream tool; retain its more precise percent.
    return re.sub(r'\d+%', f'{min(100,int(percent))}%', text, count=1)
