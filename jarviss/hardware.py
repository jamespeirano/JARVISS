"""Local hardware inspection and conservative, explainable model selection."""
import csv
import platform
import re
import shutil
import subprocess
import psutil
from .storage import ROOT

GIB = 1024 ** 3


def inspect(model_pid=None, allocated_memory=0):
    memory = psutil.virtual_memory()
    reclaimable = 0
    if model_pid:
        try:
            reclaimable = max(psutil.Process(model_pid).memory_info().rss, allocated_memory)
        except psutil.Error: pass
    unified = platform.system() == 'Darwin' and platform.machine().lower() == 'arm64'
    gpus = []
    executable = shutil.which('nvidia-smi')
    if executable:
        try:
            result = subprocess.run([executable, '--query-gpu=name,memory.total,memory.free', '--format=csv,noheader,nounits'],
                                    capture_output=True, text=True, timeout=5,
                                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            if result.returncode == 0:
                for name, total, free in csv.reader(result.stdout.splitlines()):
                    gpus.append({'name':name.strip(), 'total':int(total.strip())*1048576, 'available':int(free.strip())*1048576})
        except (OSError, ValueError, subprocess.SubprocessError): pass
    if not gpus and not unified:
        from .assets import find_server
        server = find_server()
        if server:
            try:
                result = subprocess.run([str(server), '--list-devices'], capture_output=True, text=True, timeout=10,
                                        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                for name, total, free in re.findall(r'^\s+(?:Vulkan|CUDA|SYCL)\d+: (.+?) \((\d+) MiB, (\d+) MiB free\)', result.stdout+result.stderr, re.M):
                    gpus.append({'name':name, 'total':int(total)*1048576, 'available':int(free)*1048576})
            except (OSError, subprocess.SubprocessError): pass
    return {'system':platform.system(), 'arch':platform.machine(), 'cpu':platform.processor() or platform.machine(),
            'cores':psutil.cpu_count(logical=False) or 1, 'memory':memory.total,
            'available':min(memory.total, memory.available + reclaimable), 'disk':shutil.disk_usage(ROOT).free,
            'unified':unified, 'gpus':gpus, 'accelerated':unified or bool(gpus)}


def recommend(models, hardware):
    # Leave memory for the OS, Electron, voice and the walking engine.
    budget = max(0, min(hardware['available'], hardware['memory']*.8) - 2*GIB)
    gpu_budget = max((g['available']*.9 for g in hardware['gpus']), default=0)
    rows = []
    for model in models:
        need = model['memory_gib']*GIB
        fits_ram = need <= budget
        fits_gpu = need <= gpu_budget and hardware['available'] >= 4*GIB
        fits = fits_ram or fits_gpu
        accelerated = hardware['unified'] or fits_gpu
        reason = 'Fits available memory.' if fits else 'Close other apps or choose a smaller model.'
        if fits and not accelerated: reason = 'Uses the CPU; replies may be slower.'
        rows.append({**model, 'fits':fits, 'reason':reason, 'accelerated':accelerated})
    candidates = [r for r in rows if r['fits'] and (r['accelerated'] or r['id'] != 'advanced')]
    selected = candidates[-1]['id'] if candidates else None
    return rows, selected
