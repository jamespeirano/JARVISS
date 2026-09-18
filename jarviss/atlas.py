"""Local PMTiles feature lookup. Rendering tiles are never treated as routing topology."""
import gzip
import hashlib
import json
import math
import threading
from functools import lru_cache
from pathlib import Path

from .maps import coordinate, distance, matches_place, normalized, format_distance
from .storage import read_json

SEARCH_RADIUS_M = 5000


def feature_key(name, kind, geom):
    """Identity for features without an id: the tile clip must not make one lake several places."""
    c = geom.centroid
    return hashlib.sha256(f'{normalized(name)}|{kind}|{c.y:.3f}|{c.x:.3f}'.encode()).hexdigest()[:20]


def same_feature(a, b):
    return normalized(a['name']) == normalized(b['name']) and distance(a['point'], b['point']) < 100


class TileArchive:
    def __init__(self, path):
        from pmtiles.reader import Reader
        from pmtiles.tile import TileType, Compression
        self.path = Path(path)
        self.lock = threading.RLock()
        # Each read has its own handle: no shared file seek state across chat/UI threads.
        self.reader = Reader(self._read)
        self.header = self.reader.header()
        if self.header['tile_type'] != TileType.MVT:
            raise ValueError('Use a vector PMTiles archive for offline place search.')
        if self.header['tile_compression'] not in (Compression.GZIP, Compression.NONE):
            raise ValueError('Unsupported tile compression. Use gzip or uncompressed vector tiles.')
        self.compressed = self.header['tile_compression'] == Compression.GZIP
        self.metadata = self.reader.metadata()
        layers = {item.get('id') for item in self.metadata.get('vector_layers', [])}
        if not {'roads', 'pois', 'water'} <= layers:
            raise ValueError('Offline search needs a Protomaps vector basemap with roads, pois, and water layers.')
        manifest = read_json(self.path.parent / 'manifest.json', {})
        # Only use a sidecar that actually describes this archive.
        if manifest.get('file') != self.path.name or manifest.get('size_bytes') != self.path.stat().st_size:
            manifest = {}
        self.regions = []
        if manifest.get('coverage_file'):
            coverage_path = (self.path.parent / manifest['coverage_file']).resolve()
            if coverage_path.parent == self.path.parent.resolve():
                coverage = read_json(coverage_path, {})
                geometry = coverage.get('geometry', coverage)
                polygons = geometry.get('coordinates', [])
                if geometry.get('type') == 'Polygon': polygons = [polygons]
                if geometry.get('type') == 'MultiPolygon' or geometry.get('type') == 'Polygon':
                    from shapely.geometry import shape
                    self.coverage = shape(geometry)
                    self.regions = polygons
        h = self.header
        self.pack = {'label': self.metadata.get('name', self.path.stem),
                     'bounds': [h['min_lat_e7']/1e7, h['min_lon_e7']/1e7, h['max_lat_e7']/1e7, h['max_lon_e7']/1e7],
                     'center': [h['center_lat_e7']/1e7, h['center_lon_e7']/1e7],
                     'downloaded_at': manifest.get('completed_at', 'unknown'),
                     'osm_timestamp': self.metadata.get('planetiler:osm:osmosisreplicationtime', 'unknown'),
                     'places': [], 'roads': [], 'nodes': {}, 'search_radius_m': SEARCH_RADIUS_M}

    @lru_cache(maxsize=8)
    def _read(self, offset, length):
        if length > 32 * 1024 * 1024:
            raise ValueError('Archive entry exceeds the local read limit.')
        with self.path.open('rb') as source:
            source.seek(offset)
            value = source.read(length)
        if len(value) != length:
            raise ValueError('Incomplete map archive. Reimport a complete file.')
        return value

    def contains(self, point):
        s, w, n, e = self.pack['bounds']
        if not (s <= point[0] <= n and w <= point[1] <= e): return False
        if self.regions:
            from shapely.geometry import Point
            return self.coverage.covers(Point(point[1], point[0]))
        return True

    @staticmethod
    def tile_xy(point, z):
        lat, lon = coordinate(*point)
        size = 2**z
        return (min(size-1, max(0, int((lon+180)/360*size))),
                min(size-1, max(0, int((1-math.asinh(math.tan(math.radians(lat)))/math.pi)/2*size))))

    @lru_cache(maxsize=64)
    def _features(self, z, x, y):
        from mapbox_vector_tile import decode
        from shapely.geometry import shape
        from shapely.ops import transform
        raw = self.reader.get(z, x, y)
        if raw is None: return None
        tile = decode(gzip.decompress(raw) if self.compressed else raw, default_options={'y_coord_down': True})
        result = []
        for layer_name in ('pois', 'water', 'physical_point', 'places', 'roads', 'landuse'):
            layer = tile.get(layer_name, {})
            extent = layer.get('extent', 4096)
            def convert(px, py, _z=None):
                return ((x+px/extent)/2**z*360-180,
                        math.degrees(math.atan(math.sinh(math.pi*(1-2*(y+py/extent)/2**z)))))
            for feature in layer.get('features', []):
                props = feature.get('properties', {})
                category = props.get('kind_detail') if layer_name == 'roads' else props.get('kind')
                category = category or 'place'
                if layer_name == 'landuse' and not props.get('name'): continue
                if layer_name == 'roads' and not props.get('name'): continue
                if layer_name == 'water' and category in ('ocean', 'sea'): continue
                geom = shape(feature['geometry'])
                if geom.is_empty: continue
                # Polygon label points are not shore access; distances use the mapped boundary.
                if geom.geom_type in ('Polygon', 'MultiPolygon'):
                    geom = geom.boundary
                geom = transform(convert, geom)
                kind = category.replace('_', ' ')
                if layer_name == 'water' or category in ('spring', 'water_well'):
                    kind = 'untreated water'
                if layer_name == 'roads': kind = 'road'
                name = props.get('name:en') or props.get('name') or ('Unnamed ' + category.replace('_', ' '))
                identity = feature.get('id') or feature_key(name, kind, geom)
                result.append(({'id': f'tile/{layer_name}/{identity}', 'name': name, 'kind': kind,
                                'category': category, 'access': 'unknown', 'source': 'offline basemap',
                                'point_note': 'Nearest mapped geometry; access is not established.'}, geom))
        return result

    def nearest(self, point, query='', limit=8, radius_m=SEARCH_RADIUS_M, include_roads=False):
        from shapely.geometry import Point
        from shapely.ops import nearest_points, transform
        if not self.contains(point): return []
        z = min(15, self.header['max_zoom'])
        lat, lon = coordinate(*point)
        dlat = radius_m/110500
        dlon = radius_m/(110500*math.cos(math.radians(lat)))
        _, ymin = self.tile_xy((min(85, lat+dlat), lon), z)
        _, ymax = self.tile_xy((max(-85, lat-dlat), lon), z)
        # Wrap x at the date line; Alaska includes the Aleutian islands on both sides.
        size = 2**z
        xmin, xmax = math.floor((lon-dlon+180)/360*size), math.floor((lon+dlon+180)/360*size)
        if (xmax-xmin+1)*(ymax-ymin+1) > 1024:
            raise ValueError('Search area is too large. Choose a smaller search radius.')
        scale = math.cos(math.radians(lat))
        target = Point(lon*scale, lat)
        result = {}
        with self.lock:
            for x in range(xmin, xmax+1):
                for y in range(ymin, ymax+1):
                    for record, geom in self._features(z, x % size, y) or []:
                        if record['kind'] == 'road' and not (include_roads or query): continue
                        if not matches_place(record, query): continue
                        closest = nearest_points(target, transform(lambda a, b: (a*scale, b), geom))[1]
                        where = [closest.y, closest.x/scale]
                        meters = distance(point, where)
                        if meters > radius_m: continue
                        old = result.get(record['id'])
                        if old is None or meters < old['distance_m']:
                            result[record['id']] = dict(record, point=where, distance_m=round(meters))
        return sorted(result.values(), key=lambda p: p['distance_m'])[:limit]

    def resolve_location(self, text, near=None):
        if near is None:
            raise ValueError('Confirm your position in Maps first. Offline name search covers 5 km around that position.')
        records = [p for p in self.nearest(near, text, limit=100, include_roads=True)
                   if normalized(p['name']) == normalized(text)]
        places = [p for p in records if p['kind'] != 'road']
        if len(places) == 1: return places[0]
        if len(places) > 1:
            raise ValueError('Several nearby places share that name. Select the intended place in Maps.')
        if records:
            if records[0]['distance_m'] <= 250:
                return dict(records[0], location_note=f'Using the point on {text} nearest your saved position; confirm it matches where you are.')
            raise ValueError(f'Where on {text} are you? Find a familiar landmark and confirm your position in Maps.')
        raise ValueError(f'No exact location named “{text}” found within 5 km of your position in the offline map.')


class MapCatalog:
    def __init__(self, areas=(), archive=None, router=None, location_index=None):
        self.areas = list(areas)
        self.archive = archive
        self.router = router
        self.location_index = location_index
        self.pack = archive.pack if archive else self.areas[0].pack if self.areas else {}

    def contains(self, point):
        return any(a.contains(point) for a in self.areas) or bool(self.archive and self.archive.contains(point))

    def nearest(self, point, query='', limit=8):
        records = {}
        for area in self.areas:
            for record in area.nearest(point, query, limit):
                records.setdefault(record['id'], record)
        if self.archive:
            for record in self.archive.nearest(point, query, limit*2):
                if any(same_feature(p, record) for p in records.values()):
                    continue
                records[record['id']] = record
        return sorted(records.values(), key=lambda p: p['distance_m'])[:limit]

    def resolve_location(self, text, near=None):
        errors, found = [], []
        for area in sorted(self.areas, key=lambda a: 0 if near and a.contains(near) else 1):
            try:
                candidate = area.resolve_location(text, near)
                if not any(distance(candidate['point'], p['point']) < 40 for p in found): found.append(candidate)
            except ValueError as error: errors.append(str(error))
        if len(found) > 1:
            raise ValueError('That name identifies several locations in your prepared areas. Select the intended point in Maps.')
        if found: return found[0]
        if self.archive:
            try: return self.archive.resolve_location(text, near)
            except ValueError as error: errors.append(str(error))
        if self.location_index:
            candidates = self.location_index.search(text)
            if len(candidates) == 1:
                return dict(candidates[0], location_note='Using the recorded town/city label. Select a specific street or landmark for a more precise destination.')
            if candidates:
                raise ValueError('That name matches several areas. Use Maps to select the intended town or city and then a destination point.')
        raise ValueError(errors[0] if errors else 'No offline map is loaded.')

    def route(self, origin, destination):
        if self.router and self.router.status()['ready']:
            return self.router.route(origin, destination)
        candidates = [a for a in self.areas if a.contains(origin) and a.contains(destination)]
        if not candidates:
            raise ValueError('US offline directions are not installed. Use Download US offline maps in Maps while connected. No individual area preparation is needed.')
        errors, routes = [], []
        for area in candidates:
            try: routes.append(area.route(origin, destination))
            except ValueError as error: errors.append(str(error))
        if not routes: raise ValueError(errors[0])
        return min(routes, key=lambda r: r['distance_m'])

    def search_note(self):
        if self.archive:
            return f'Basemap search covers {format_distance(5000)} around your position, plus all imported routing packs. Results are recorded features, not an exhaustive inventory.'
        return 'Search covers the imported routing packs only. Results are recorded features, not an exhaustive inventory.'
