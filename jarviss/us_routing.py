"""Nationwide, file-only BRouter walking directions. No network in this module."""
import json
import math
import platform
import subprocess
import tempfile
from pathlib import Path
from .storage import ROOT, RUNTIME, BUNDLED_RUNTIME, RESOURCES, read_json
from .maps import coordinate, distance, bearing, format_distance

BROUTER_VERSION = '1.7.10'
US_BOUNDS = [(-125, 24, -66, 50), (-180, 51, -129, 72), (172, 51, 180, 55), (-161, 18, -154, 23)]
TURNS = {1:'Continue straight', 2:'Turn left', 3:'Bear left', 4:'Turn sharply left',
         5:'Turn right', 6:'Bear right', 7:'Turn sharply right', 8:'Keep left', 9:'Keep right',
         10:'Make a left U-turn', 11:'Make a right U-turn', 15:'Make a U-turn',
         17:'Take the left exit', 18:'Take the right exit'}


def java_path(runtime=None):
    name = 'java.exe' if platform.system() == 'Windows' else 'java'
    roots = (Path(runtime),) if runtime is not None else (BUNDLED_RUNTIME, RUNTIME)
    return next((p for root in roots for p in (root / 'brouter' / 'java').rglob(name)), None)


def segment_name(point):
    lat, lon = coordinate(*point)
    x, y = math.floor(lon/5)*5, math.floor(lat/5)*5
    return f"{'W' if x < 0 else 'E'}{abs(x)}_{'S' if y < 0 else 'N'}{abs(y)}.rd5"


class USRouter:
    def __init__(self, directory=None, runtime=None):
        self.directory = Path(directory or ROOT / 'local-maps' / 'routing-us')
        bundled = BUNDLED_RUNTIME / 'brouter' / f'brouter-{BROUTER_VERSION}' / f'brouter-{BROUTER_VERSION}-all.jar'
        self.runtime = Path(runtime or (BUNDLED_RUNTIME if bundled.is_file() and java_path(BUNDLED_RUNTIME) else RUNTIME))
        self.manifest = read_json(self.directory / 'manifest.json', {})

    def status(self):
        files = self.manifest.get('files', [])
        installed = sum((self.directory / 'segments4' / f['name']).is_file() and
                        (self.directory / 'segments4' / f['name']).stat().st_size == f['size'] for f in files)
        engine = bool(java_path(self.runtime) and self.jar.is_file())
        ready = bool(files and installed == len(files) and engine and self.manifest.get('complete'))
        return {'ready':ready, 'installedFiles':installed, 'totalFiles':len(files),
                'bytes':sum(f['size'] for f in files), 'downloaded_at':self.manifest.get('downloaded_at'),
                'label':'United States · lower 48, Alaska and Hawaii', 'engineReady':engine}

    @property
    def jar(self):
        return self.runtime / 'brouter' / f'brouter-{BROUTER_VERSION}' / f'brouter-{BROUTER_VERSION}-all.jar'

    def contains(self, point):
        lat, lon = coordinate(*point)
        return any(w <= lon <= e and s <= lat <= n for w,s,e,n in US_BOUNDS)

    def route(self, origin, destination):
        origin, destination = coordinate(*origin), coordinate(*destination)
        if not self.status()['ready']:
            raise ValueError('US offline directions are not fully installed. Use Download US offline maps in Maps while connected, then directions work offline throughout that coverage.')
        if not self.contains(origin) or not self.contains(destination):
            raise ValueError('An endpoint is outside the downloaded US coverage.')
        for point in (origin, destination):
            if not (self.directory / 'segments4' / segment_name(point)).is_file():
                raise ValueError('No recorded walking network exists at this endpoint in the downloaded data.')
        # Fixed arguments and private output directory: no server, shell, shared track file, or online fallback.
        params = f'lonlats={origin[1]},{origin[0]}|{destination[1]},{destination[0]}&profile=walking&format=geojson&alternativeidx=0&timode=2'
        with tempfile.TemporaryDirectory(prefix='jarvis-route-') as temp:
            output = Path(temp) / 'route'
            command = [str(java_path(self.runtime)), '-Xmx2048m', '-DmaxRunningTime=180', '-cp', str(self.jar),
                       'btools.server.BRouter', str(self.directory / 'segments4'), str(RESOURCES / 'routing'), params, str(output)]
            try:
                result = subprocess.run(command, cwd=temp, capture_output=True, text=True, timeout=190,
                                        **({'creationflags':subprocess.CREATE_NO_WINDOW} if platform.system() == 'Windows' else {}))
            except subprocess.TimeoutExpired:
                raise ValueError('This route exceeded the local calculation time. Choose an intermediate destination along your trip; the US data is already installed.') from None
            path = Path(str(output) + '0.geojson')
            if result.returncode or not path.is_file():
                log = result.stdout + result.stderr
                if 'timeout' in log.lower() or 'memory' in log.lower():
                    raise ValueError('This route exceeded local calculation resources. Choose an intermediate destination; no additional area download is needed.')
                if '.rd5' in log and ('not found' in log or 'does not exist' in log):
                    raise ValueError('The walking route would need map data outside the installed US coverage. Choose a destination connected within that coverage.')
                raise ValueError('No connected walking route was found in the offline network. Check both endpoints. Ferries, restricted paths and difficult mountain routes are excluded.')
            return self.decode(json.loads(path.read_text()), origin, destination)

    def decode(self, data, origin, destination):
        feature = next(f for f in data['features'] if f['geometry']['type'] == 'LineString')
        props = feature['properties']
        points = [[p[1], p[0]] for p in feature['geometry']['coordinates']]
        if len(points) < 2: raise ValueError('No walking distance between these endpoints was found.')
        start_gap, end_gap = distance(origin, points[0]), distance(destination, points[-1])
        if max(start_gap, end_gap) > 250:
            raise ValueError('An endpoint is more than 250 m from the recorded walking network. Select a point on a mapped road or path; Jarvis cannot assume the connection is passable.')
        cumulative = [0.0]
        for a,b in zip(points, points[1:]): cumulative.append(cumulative[-1] + distance(a,b))
        total = float(props['track-length'])
        scale = total / cumulative[-1] if cumulative[-1] else 1
        heading = bearing(points[0], next((p for p in points[1:] if distance(points[0], p)>3),points[-1]))
        compass = ['north','northeast','east','southeast','south','southwest','west','northwest'][round(heading/45)%8]
        actions = [(0, f'Head {compass}')]
        for index,cmd,exit_number,*_ in props.get('voicehints', []):
            if not 0 <= index < len(points): raise ValueError('Invalid turn in the local routing result.')
            if cmd == 1: continue  # Continuing straight at each junction does not require a separate instruction.
            if cmd in (12,16): raise ValueError('The route contains an unmapped direct segment; choose endpoints on connected walking paths.')
            action = f'At the roundabout, take exit {abs(exit_number)}' if cmd in (13,14) else TURNS.get(cmd)
            if not action: raise ValueError('Unrecognized turn in the local routing result.')
            actions.append((index, action))
        actions.sort(key=lambda a:a[0])
        steps = []
        for i,(index,action) in enumerate(actions):
            end = actions[i+1][0] if i+1 < len(actions) else len(points)-1
            meters = round((cumulative[end]-cumulative[index])*scale)
            steps.append({'action':action,'road':'mapped path','point':points[index], 'distance_m':meters,
                          'instruction':f'{action}, then continue for {format_distance(meters)}.'})
        return {'points':points, 'steps':steps, 'roads':[], 'distance_m':round(total), 'distance_miles':round(total/1609.344,3),
                'origin':list(origin), 'destination_point':list(destination), 'start_gap_m':round(start_gap), 'end_gap_m':round(end_gap),
                'downloaded_at':self.manifest.get('downloaded_at','unknown'), 'osm_timestamp':'not supplied by routing provider',
                'engine':'BRouter '+BROUTER_VERSION, 'note':'Offline mapped walking route. Turn cues and distances come from the routing network; road names are not included. Access and current conditions are unverified.'}
