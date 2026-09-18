"""Local hardware inspection and conservative, explainable model selection."""
import csv
import platform
import re
import shutil
import subprocess
import tempfile
import psutil
from .storage import ROOT

GIB = 1024 ** 3
# Integrated adapters report the host's RAM as their heap; it is not extra memory.
SHARED_GPU = re.compile(r'Intel.*(?:Iris|UHD Graphics|HD Graphics|Arc(?:\(TM\))? Graphics$)|Radeon.*(?:Graphics$|\b\d{3}M\b)|\bAPU\b|integrated', re.I)


def gb(count):
    """Decimal gigabytes, formatted the same way as the setup page (setup.js gb())."""
    return f'{count/1e9:.1f} GB'


def free_disk():
    # Downloads land under ROOT, but the runtime archive is staged in the system temp folder first.
    volumes = {ROOT, tempfile.gettempdir()}
    return min(shutil.disk_usage(v).free for v in volumes)


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
                    gpus.append({'name':name.strip(), 'total':int(total.strip())*1048576, 'available':int(free.strip())*1048576, 'shared':False})
        except (OSError, ValueError, subprocess.SubprocessError): pass
    if not gpus and not unified:
        from .assets import find_server
        server = find_server()
        if server:
            try:
                result = subprocess.run([str(server), '--list-devices'], capture_output=True, text=True, timeout=10,
                                        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                output = result.stdout + result.stderr
                # ggml prints "ggml_vulkan: 0 = NAME (driver) | uma: 1 | ..." while initialising.
                uma = {int(i) for i, flag in re.findall(r'^ggml_vulkan: (\d+) = .* \| uma: (\d) \|', output, re.M) if flag == '1'}
                for index, (name, total, free) in enumerate(re.findall(r'^\s+(?:Vulkan|CUDA|SYCL)\d+: (.+?) \((\d+) MiB, (\d+) MiB free\)', output, re.M)):
                    gpus.append({'name':name, 'total':int(total)*1048576, 'available':int(free)*1048576,
                                 'shared':index in uma or bool(SHARED_GPU.search(name))})
            except (OSError, subprocess.SubprocessError): pass
    return {'system':platform.system(), 'arch':platform.machine(), 'cpu':platform.processor() or platform.machine(),
            'cores':psutil.cpu_count(logical=False) or 1, 'memory':memory.total,
            'available':min(memory.total, memory.available + reclaimable), 'disk':free_disk(),
            'unified':unified, 'gpus':gpus, 'accelerated':unified or bool(gpus)}


def recommend(models, hardware):
    # Leave memory for the OS, Electron, voice and the walking engine.
    budget = max(0, min(hardware['available'], hardware['memory']*.8) - 2*GIB)
    # A shared (integrated) heap is the same RAM already counted in budget.
    gpu_budget = max((g['available']*.9 for g in hardware['gpus'] if not g.get('shared')), default=0)
    shared = any(g.get('shared') for g in hardware['gpus'])
    rows = []
    for model in models:
        need = model['memory_gib']*GIB
        fits_ram = need <= budget
        fits_gpu = need <= gpu_budget and hardware['available'] >= 4*GIB
        fits = fits_ram or fits_gpu
        accelerated = hardware['unified'] or fits_gpu
        reason = 'Fits available memory.' if fits else 'Close other apps or choose a smaller model.'
        if fits and not accelerated: reason = 'Uses shared graphics memory; replies may be slower.' if shared else 'Uses the CPU; replies may be slower.'
        rows.append({**model, 'fits':fits, 'reason':reason, 'accelerated':accelerated})
    candidates = [r for r in rows if r['fits'] and (r['accelerated'] or r['id'] != 'advanced')]
    selected = candidates[-1]['id'] if candidates else None
    return rows, selected
