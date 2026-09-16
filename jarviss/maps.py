"""Offline OSM geometry, resource search, and pedestrian graph routing."""
import heapq
import json
import math
import re
import urllib.parse
import urllib.request
from .network import tls_context
from datetime import datetime, timezone

ATTRIBUTION = '© OpenStreetMap contributors · ODbL · openstreetmap.org/copyright'
RESOURCE_TAGS = {'drinking_water': 'water', 'water_point': 'water', 'hospital': 'medical',
                 'clinic': 'medical', 'doctors': 'medical', 'pharmacy': 'medical',
                 'fire_station': 'fire station', 'shelter': 'shelter', 'police': 'police'}

# Keep specific categories searchable; a pharmacy is not interchangeable with a hospital.
CATEGORIES = {
    'water': {'water', 'drinking_water', 'water_point', 'spring', 'well', 'water_well', 'river', 'stream', 'lake', 'pond', 'reservoir', 'canal', 'swimming_pool', 'untreated water'},
    'drinking water': {'drinking_water', 'water_point'},
    'running water': {'river', 'stream', 'spring'},
    'food': {'food', 'supermarket', 'convenience', 'grocery', 'greengrocer', 'bakery', 'farm', 'farm_shop'},
    'medical': {'medical', 'hospital', 'clinic', 'doctors', 'pharmacy'},
    'supplies': {'supplies', 'hardware', 'outdoor', 'doityourself'},
    'shelter': {'shelter', 'community_centre', 'townhall'},
    'fuel': {'fuel', 'gas_station'},
}
RESOURCE_CATEGORIES = {c.replace(' ', '_') for group in CATEGORIES.values() for c in group} | RESOURCE_TAGS.keys()
ALIASES = {'grocery store': 'food', 'groceries': 'food', 'gas station': 'fuel', 'fire station': 'fire_station',
           'hardware store': 'hardware', 'drugstore': 'pharmacy', 'river': 'river', 'creek': 'stream',
           'flowing water': 'running water'}


def normalized(text):
    text = re.sub(r'[^\w\s]', ' ', str(text).lower()).strip()
    words = {'rd': 'road', 'st': 'street', 'ave': 'avenue', 'blvd': 'boulevard', 'dr': 'drive',
             'hwy': 'highway', 'ln': 'lane', 'ct': 'court', 'n': 'north', 's': 'south', 'e': 'east', 'w': 'west'}
    return ' '.join(words.get(w, w) for w in text.split())


def matches_place(place, query):
    query = query.lower().strip()
    if not query:
        return True
    query = ALIASES.get(query, query)
    category = place.get('category', place['kind'])
    if query == 'drinking water' and place['kind'] == 'water' and 'category' not in place:
        return True  # Legacy packs label drinking-water amenities as "water".
    if query in CATEGORIES:
        return category in CATEGORIES[query] or place['kind'] in CATEGORIES[query]
    resource = query.replace(' ', '_')
    if resource in RESOURCE_CATEGORIES:
        return resource in {str(category).replace(' ', '_'), place['kind'].replace(' ', '_')}
    return normalized(query.replace('_', ' ')) in normalized(' '.join(str(place.get(k, '')) for k in ('name', 'kind', 'category')).replace('_', ' '))


def format_distance(meters):
    return f'{meters / 1609.344:.2f} miles ({round(meters):,} m)'


def project(point, a, b):
    """Nearest point on a short segment, in a local equirectangular plane."""
    scale = math.cos(math.radians(point[0]))
    dx, dy = (b[1] - a[1]) * scale, b[0] - a[0]
    length = dx * dx + dy * dy
    t = max(0, min(1, (((point[1]-a[1])*scale)*dx + (point[0]-a[0])*dy) / length)) if length else 0
    return [a[0] + t*(b[0]-a[0]), a[1] + t*(b[1]-a[1])], t


def bearing(a, b):
    lat1, lat2 = math.radians(a[0]), math.radians(b[0])
    dlon = math.radians(b[1] - a[1])
    return (math.degrees(math.atan2(math.sin(dlon)*math.cos(lat2),
            math.cos(lat1)*math.sin(lat2)-math.sin(lat1)*math.cos(lat2)*math.cos(dlon))) + 360) % 360


def route_steps(points, names):
    steps, previous_heading = [], None
    for a, b, name in zip(points, points[1:], names):
        meters = distance(a, b)
        if meters < .1:
            continue
        heading = bearing(a, b)
        if steps and steps[-1]['road'] == name:
            steps[-1]['distance_m'] += meters
        else:
            delta = (heading - previous_heading + 180) % 360 - 180 if previous_heading is not None else 0
            action = ('Head ' + ['north', 'northeast', 'east', 'southeast', 'south', 'southwest', 'west', 'northwest'][round(heading/45) % 8]
                      if previous_heading is None else 'Turn around' if abs(delta) > 150 else
                      'Turn right' if delta > 30 else 'Turn left' if delta < -30 else 'Continue')
            steps.append({'road': name, 'action': action, 'distance_m': meters})
        previous_heading = heading
    for step in steps:
        step['distance_m'] = round(step['distance_m'])
        step['instruction'] = f"{step['action']} on {step['road']} for {format_distance(step['distance_m'])}."
    return steps


def coordinate(lat, lon):
    lat, lon = float(lat), float(lon)
    if not math.isfinite(lat) or not math.isfinite(lon) or not -85 <= lat <= 85 or not -180 <= lon <= 180:
        raise ValueError('Enter latitude −85 to 85 and longitude −180 to 180.')
    return lat, lon


def distance(a, b):
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    term = math.sin((lat2-lat1)/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin((lon2-lon1)/2)**2
    return 6371000 * 2 * math.asin(min(1, math.sqrt(term)))


def download_area(lat, lon, radius_km, progress=lambda _: None):
    lat, lon = coordinate(lat, lon)
    radius = float(radius_km)
    if not math.isfinite(radius) or not 0.25 <= radius <= 10:
        raise ValueError('Choose a radius from 0.25 to 10 km.')
    dlat, dlon = radius / 111.32, radius / (111.32 * math.cos(math.radians(lat)))
    bounds = [lat-dlat, lon-dlon, lat+dlat, lon+dlon]
    if bounds[1] < -180 or bounds[3] > 180:
        raise ValueError('Choose an area that does not cross the date line.')
    box = ','.join(str(round(x, 6)) for x in bounds)
    query = f'''[out:json][timeout:90][bbox:{box}];
    (way[highway]; nwr[amenity]; nwr[shop]; nwr[tourism];
     nwr[natural~"^(water|spring)$"]; nwr[waterway~"^(river|stream|canal)$"]; nwr[man_made=water_well];);
    out body center; >; out skel qt;'''
    progress('Downloading roads and resources…')
    errors = []
    for endpoint in ('https://overpass-api.de/api/interpreter', 'https://overpass.kumi.systems/api/interpreter'):
        request = urllib.request.Request(endpoint + '?' + urllib.parse.urlencode({'data': query}),
                                        headers={'User-Agent': 'JARVISS/0.2'})
        try:
            with urllib.request.urlopen(request, timeout=100, context=tls_context()) as response:
                raw = response.read(80 * 1024 * 1024 + 1)
            if len(raw) > 80 * 1024 * 1024:
                raise ValueError('Area is too large. Choose a smaller radius.')
            payload = json.loads(raw)
            if payload.get('remark'):
                raise RuntimeError('Incomplete map response.')
            pack = build_pack(payload, [lat, lon], bounds, radius)
            pack['source'] = endpoint
            return pack
        except (OSError, RuntimeError) as error:
            errors.append(str(error))
            progress('Map service busy; trying the alternate provider…')
    raise RuntimeError('Map download failed. Retry a smaller area or import a prepared pack. ' + '; '.join(errors))


def build_pack(payload, center, bounds, radius):
    elements = payload.get('elements', [])
    nodes = {str(e['id']): [e['lat'], e['lon']] for e in elements if e['type'] == 'node'}
    blocked = {str(e['id']) for e in elements if e['type'] == 'node' and
               (e.get('tags', {}).get('foot') in ('no', 'private') or
                (e.get('tags', {}).get('access') in ('no', 'private') and
                 e.get('tags', {}).get('foot') not in ('yes', 'designated', 'permissive')))}
    roads, places = [], []
    seen = set()
    for e in elements:
        tags = e.get('tags', {})
        highway = tags.get('highway')
        if e['type'] == 'way' and highway:
            foot = tags.get('foot')
            walkable = highway not in ('motorway', 'motorway_link', 'trunk', 'trunk_link', 'construction', 'proposed')
            if tags.get('access') in ('no', 'private') and foot not in ('yes', 'designated', 'permissive'):
                walkable = False
            if foot in ('no', 'private'):
                walkable = False
            roads.append({'nodes': [str(n) for n in e.get('nodes', [])], 'name': tags.get('name', 'Unnamed ' + highway.replace('_', ' ')),
                          'walkable': walkable, 'oneway': tags.get('oneway:foot', 'no')})
        kind = RESOURCE_TAGS.get(tags.get('amenity'))
        if tags.get('shop') in ('supermarket', 'convenience'):
            kind = 'food'
        elif tags.get('shop') in ('hardware', 'outdoor'):
            kind = 'supplies'
        elif tags.get('natural') in ('water', 'spring') or tags.get('waterway') or tags.get('man_made') == 'water_well':
            kind = 'untreated water'
        category = tags.get('amenity') or tags.get('shop') or tags.get('tourism') or tags.get('waterway') or tags.get('water') or tags.get('natural') or tags.get('man_made')
        if not kind and category:
            kind = str(category).replace('_', ' ')
        if kind and (e['type'], e['id']) not in seen:
            point = [e['lat'], e['lon']] if 'lat' in e else [e.get('center', {}).get('lat'), e.get('center', {}).get('lon')]
            if None not in point:
                seen.add((e['type'], e['id']))
                places.append({'id': f"{e['type']}/{e['id']}", 'name': tags.get('name', kind.title()),
                               'kind': kind, 'category': category, 'point': point, 'access': tags.get('access', 'unknown')})
    pack = {'version': 1, 'center': center, 'bounds': bounds, 'radius_km': radius,
            'downloaded_at': datetime.now(timezone.utc).isoformat(),
            'osm_timestamp': payload.get('osm3s', {}).get('timestamp_osm_base', 'unknown'),
            'attribution': ATTRIBUTION, 'nodes': nodes, 'roads': roads, 'places': places,
            'blocked_nodes': sorted(blocked)}
    validate_pack(pack)
    return pack


def validate_pack(pack):
    if pack.get('version') != 1:
        raise ValueError('Unsupported map pack.')
    coordinate(*pack['center'])
    if len(pack['bounds']) != 4:
        raise ValueError('Invalid map bounds.')
    s, w, n, e = pack['bounds']
    coordinate(s, w); coordinate(n, e)
    if not s < n or not w < e:
        raise ValueError('Invalid map bounds.')
    if len(pack['nodes']) > 500000 or len(pack['places']) > 100000:
        raise ValueError('Map pack is too large.')
    for point in pack['nodes'].values():
        coordinate(*point)
    for place in pack['places']:
        coordinate(*place['point'])
        for key in ('id', 'name', 'kind'):
            if not isinstance(place[key], str):
                raise ValueError('Invalid place.')
    for road in pack['roads']:
        if not isinstance(road.get('walkable'), bool) or not isinstance(road['nodes'], list):
            raise ValueError('Invalid road.')


class OfflineMap:
    def __init__(self, pack):
        validate_pack(pack)
        self.pack = pack
        self.nodes = pack['nodes']
        self.graph, self.segments = {}, []
        blocked = set(pack.get('blocked_nodes', []))
        for road in pack['roads']:
            if not road['walkable']:
                continue
            for a, b in zip(road['nodes'], road['nodes'][1:]):
                if a not in self.nodes or b not in self.nodes or a == b or a in blocked or b in blocked:
                    continue
                name = road.get('name', 'Unnamed path')
                cost = distance(self.nodes[a], self.nodes[b])
                forward = road.get('oneway') != '-1'
                reverse = road.get('oneway') not in ('yes', '1')
                self.segments.append((a, b, cost, name, forward, reverse))
                if forward:
                    self.graph.setdefault(a, []).append((b, cost, name))
                if reverse:
                    self.graph.setdefault(b, []).append((a, cost, name))
                self.graph.setdefault(a, []); self.graph.setdefault(b, [])

    def contains(self, point):
        s, w, n, e = self.pack['bounds']
        return s <= point[0] <= n and w <= point[1] <= e

    def nearest(self, point, query='', limit=8):
        result = [dict(p, distance_m=round(distance(point, p['point'])))
                  for p in self.pack['places'] if matches_place(p, query)]
        return sorted(result, key=lambda p: p['distance_m'])[:limit]

    def resolve_location(self, text, near=None):
        """Resolve coordinates, an exact place, or a real shared-node intersection.

        A lone street needs a nearby known position; never substitute its midpoint.
        """
        text = text.strip().strip('.,?!')
        pair = re.fullmatch(r'(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)', text)
        if pair:
            point = coordinate(*pair.groups())
            if not self.contains(point):
                raise ValueError('That location is outside the downloaded routing area.')
            return {'name': text, 'point': point}
        exact = [p for p in self.pack['places'] if normalized(p['name']) == normalized(text)]
        if exact:
            if len(exact) > 1:
                raise ValueError('Several locations share that name. Select one in Maps.')
            return exact[0]
        cross = re.split(r'\s+(?:and|at|&|intersection with)\s+|\s*&\s*', text, maxsplit=1, flags=re.I)
        def roads(name):
            return [r for r in self.pack['roads'] if normalized(r.get('name', '')) == normalized(name)]
        if len(cross) == 2:
            first = {n for r in roads(cross[0]) for n in r['nodes'] if n in self.nodes}
            second = {n for r in roads(cross[1]) for n in r['nodes'] if n in self.nodes}
            common = first & second
            # Several adjacent nodes at a junction may represent one intersection.
            if not common:
                raise ValueError('No shared intersection with those road names is recorded in the routing data. Select your position in Maps.')
            choices = [self.nodes[n] for n in common]
            if any(distance(choices[0], p) > 100 for p in choices):
                raise ValueError('Those roads meet in several places. Select the intersection in Maps.')
            point = min(choices, key=lambda p: distance(near, p)) if near else choices[0]
            return {'name': text, 'point': point, 'location_note': 'Starting at the recorded intersection.'}
        candidates = roads(text)
        if candidates:
            if near is None:
                raise ValueError(f'Where on {text} are you? Give a cross street or set your position in Maps.')
            points = [project(near, self.nodes[a], self.nodes[b])[0] for r in candidates
                      for a, b in zip(r['nodes'], r['nodes'][1:]) if a in self.nodes and b in self.nodes]
            if points:
                point = min(points, key=lambda p: distance(near, p))
                if distance(near, point) <= 250:
                    return {'name': text, 'point': point, 'location_note': f'Using the point on {text} nearest your saved position; confirm it matches where you are.'}
            raise ValueError(f'Your saved position is not close to {text}. Give a cross street or select your position in Maps.')
        raise ValueError(f'No exact location named “{text}” found in the local routing data. Give a cross street or select it in Maps.')

    def route(self, origin, destination):
        origin, destination = coordinate(*origin), coordinate(*destination)
        if not self.contains(origin) or not self.contains(destination):
            raise ValueError('Route endpoint is outside this downloaded area.')
        if not self.segments:
            raise ValueError('No walking network in this map.')
        def snap(point):
            best = None
            for index, segment in enumerate(self.segments):
                a, b = segment[:2]
                projected, t = project(point, self.nodes[a], self.nodes[b])
                gap = distance(point, projected)
                if best is None or gap < best[0]:
                    best = (gap, index, projected, t)
            return best
        start_gap, si, sp, st = snap(origin)
        end_gap, ei, ep, et = snap(destination)
        if max(start_gap, end_gap) > 250:
            raise ValueError('No mapped walking connection within 250 m of an endpoint.')
        # Split only snapped segments. Share endpoint IDs so snapping at a junction
        # cannot strand a route on the wrong one-way edge.
        nodes = dict(self.nodes)
        extra = {}
        def attach(index, point, fraction, key):
            a, b = self.segments[index][:2]
            if fraction < 1e-8: return a
            if fraction > 1-1e-8: return b
            nodes[key] = point
            extra.setdefault(index, []).append((fraction, key))
            return key
        start = attach(si, sp, st, '__route_start')
        end = attach(ei, ep, et, '__route_end')
        graph = {n: list(edges) for n, edges in self.graph.items()}
        for index, cuts in extra.items():
            a, b, length, name, forward, reverse = self.segments[index]
            sequence = sorted([(0, a), *cuts, (1, b)])
            for (t1, n1), (t2, n2) in zip(sequence, sequence[1:]):
                cost = (t2-t1)*length
                if forward: graph.setdefault(n1, []).append((n2, cost, name))
                if reverse: graph.setdefault(n2, []).append((n1, cost, name))
        queue, costs, previous = [(0, start)], {start: 0}, {}
        while queue:
            cost, node = heapq.heappop(queue)
            if cost != costs[node]:
                continue
            if node == end:
                break
            for other, step, name in graph.get(node, []):
                candidate = cost + step
                if candidate < costs.get(other, math.inf):
                    costs[other] = candidate
                    previous[other] = (node, name)
                    heapq.heappush(queue, (candidate, other))
        if end not in costs:
            raise ValueError('No connected walking route in the downloaded map.')
        path, names = [end], []
        while path[-1] != start:
            parent, name = previous[path[-1]]
            names.append(name); path.append(parent)
        points = [nodes[n] for n in reversed(path)]
        names.reverse()
        steps = route_steps(points, names)
        return {'points': points, 'roads': [s['road'] for s in steps], 'steps': steps,
                'distance_m': round(costs[end]), 'distance_miles': round(costs[end]/1609.344, 3),
                'start_gap_m': round(start_gap), 'end_gap_m': round(end_gap),
                'origin': list(origin), 'destination_point': list(destination),
                'osm_timestamp': self.pack.get('osm_timestamp', 'unknown'),
                'downloaded_at': self.pack.get('downloaded_at', 'unknown'),
                'note': 'Mapped walking route only. Endpoint connections, access, hazards, and facility operation are unverified.'}
