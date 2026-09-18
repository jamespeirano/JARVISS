"""Offline location discovery; searching never changes the user's position."""
import gzip
import hashlib
import math
import re
import threading
from pathlib import Path
from functools import lru_cache
from .maps import distance, normalized
from .storage import DATA, RESOURCES, read_json, write_json


@lru_cache(maxsize=1)
def state_boundaries():
    from shapely.geometry import shape
    return [(f['properties'],shape(f['geometry'])) for f in read_json(RESOURCES/'routing'/'us-states.geojson',{'features':[]})['features']]


def in_state(point, geometry):
    from shapely.geometry import Point
    return geometry.covers(Point(point[1],point[0]))


class LocationIndex:
    def __init__(self, archive, cache_dir=None):
        self.archive = archive
        info = archive.path.stat()
        identity = f'{archive.path.resolve()}:{info.st_size}:{info.st_mtime_ns}:places-v1-z9'
        self.path = Path(cache_dir or DATA / 'map-index') / (hashlib.sha256(identity.encode()).hexdigest()[:24]+'.json')
        self.lock = threading.Lock()
        self.records = None

    def load(self, progress=lambda _: None):
        with self.lock:
            if self.records is not None: return self.records
            cached = read_json(self.path, None)
            if cached is not None:
                self.records = cached['places']; return self.records
            from mapbox_vector_tile import decode
            from mapbox_vector_tile.Mapbox import vector_tile_pb2
            z = min(9, self.archive.header['max_zoom'])
            # Index overview labels only, bounded to actual downloaded cutouts.
            boxes = []
            for polygon in self.archive.regions:
                ring = polygon[0]
                boxes.append([min(p[1] for p in ring), min(p[0] for p in ring), max(p[1] for p in ring), max(p[0] for p in ring)])
            if not boxes: boxes = [self.archive.pack['bounds']]
            tiles = set()
            for s,w,n,e in boxes:
                x0,y0 = self.archive.tile_xy((n,w),z); x1,y1 = self.archive.tile_xy((s,e),z)
                tiles.update((x,y) for x in range(x0,x1+1) for y in range(y0,y1+1))
            if len(tiles) > 40000:
                raise ValueError('This archive is too large for the overview place index. Pan to your region and search a road or landmark there.')
            places = {}
            for i,(x,y) in enumerate(sorted(tiles)):
                if i % 400 == 0: progress(f'Indexing city and town names from your local map… {i*100//len(tiles)}%')
                raw = self.archive.reader.get(z,x,y)
                if not raw: continue
                message = vector_tile_pb2.tile()
                message.ParseFromString(gzip.decompress(raw) if self.archive.compressed else raw)
                selected = vector_tile_pb2.tile()
                selected.layers.extend(layer for layer in message.layers if layer.name == 'places')
                layer = decode(selected.SerializeToString(), default_options={'y_coord_down':True}).get('places',{})
                extent = layer.get('extent',4096)
                for f in layer.get('features',[]):
                    p=f['properties']; name=p.get('name:en') or p.get('name')
                    if not name or p.get('kind') not in ('locality','region','country'): continue
                    if f['geometry']['type'] != 'Point': continue
                    px,py=f['geometry']['coordinates']
                    point=[math.degrees(math.atan(math.sinh(math.pi*(1-2*(y+py/extent)/2**z)))), (x+px/extent)/2**z*360-180]
                    if not self.archive.contains(point): continue
                    key=str(f.get('id') or f'{name}:{point}')
                    places[key]={'id':'overview/'+key, 'name':name, 'kind':p.get('kind_detail',p['kind']),
                                 'point':point, 'population':p.get('population',0), 'abbreviation':p.get('ref:USPS') or p.get('ref',''),
                                 'note':'Area label for orientation. Confirm your actual position on the map.'}
            self.records=list(places.values())
            write_json(self.path, {'osm_timestamp':self.archive.pack['osm_timestamp'],'zoom':z,'places':self.records})
            progress(f'Offline place index ready: {len(self.records):,} city, town and region labels.')
            return self.records

    def search(self, query, progress=lambda _: None, limit=20):
        if len(query.strip()) < 2: return []
        records=self.load(progress)
        parts=query.split(',',1);needle=normalized(parts[0])
        if len(needle) < 2: return []  # Punctuation alone would match every label.
        region=normalized(parts[1]) if len(parts)>1 else ''
        hints=[p for p in records if p['kind'] in ('state','province','region') and region and region in (normalized(p['name']),normalized(p['abbreviation']))]
        found=[p for p in records if needle in normalized(p['name']) or needle == normalized(p['abbreviation'])]
        states=state_boundaries()
        selected=next(((meta,geom) for meta,geom in states if region in (normalized(meta['name']),normalized(meta['code']))),None)
        if selected:
            meta,geom=selected
            found=[dict(p,state=meta['name'],state_code=meta['code']) for p in found if in_state(p['point'],geom)]
        elif region and not hints:
            return []
        # Known US states filter by actual boundaries; other region hints only order matches.
        return sorted(found,key=lambda p:(normalized(p['name'])!=needle, not normalized(p['name']).startswith(needle),
                      min(distance(p['point'],h['point']) for h in hints) if hints else -p['population']))[:limit]

    def address_parts(self, text, progress=lambda _: None):
        """Split familiar address text for discovery; never infer a house position."""
        text=re.sub(r'\s+\d{5}(?:-\d{4})?$', '',text.strip()).rstrip(', ')
        parts=[p.strip() for p in text.split(',') if p.strip()]
        if len(parts)>=3:return {'city':', '.join(parts[-2:]),'street':', '.join(parts[:-2])}
        states=state_boundaries()
        if len(parts)==2:
            if any(normalized(parts[-1]) in (normalized(meta['name']),normalized(meta['code'])) for meta,_ in states):
                return {'city':text,'street':''}
            return {'city':parts[-1],'street':parts[0]}
        for meta,geom in states:
            for suffix in (meta['name'],meta['code']):
                match=re.search(r'\s+'+re.escape(suffix)+r'$',text,re.I)
                if not match:continue
                before=text[:match.start()]
                cities=[p for p in self.load(progress) if p['kind'] not in ('state','province','region','country')
                        and re.search(r'(?:^|\s)'+re.escape(p['name'])+r'$',before,re.I) and in_state(p['point'],geom)]
                if cities:
                    city=max(cities,key=lambda p:len(p['name']))['name']
                    return {'city':city+', '+meta['code'],'street':before[:-len(city)].strip(' ,')}
                return {'city':before+', '+meta['code'],'street':''}
        return {'city':text,'street':''}
