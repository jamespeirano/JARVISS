"""Real offline integration sweep. Writes evidence; does not change user position."""
import json,time,math
from pathlib import Path
from unittest.mock import patch
from shapely.geometry import LineString
from jarviss.atlas import TileArchive
from jarviss.location_search import LocationIndex,state_boundaries,in_state
from jarviss.us_routing import USRouter
from jarviss.maps import distance,normalized
from jarviss.storage import ROOT

CAPITALS={'AL':'Montgomery','AK':'Juneau','AZ':'Phoenix','AR':'Little Rock','CA':'Sacramento','CO':'Denver','CT':'Hartford','DE':'Dover','FL':'Tallahassee','GA':'Atlanta','HI':'Honolulu','ID':'Boise','IL':'Springfield','IN':'Indianapolis','IA':'Des Moines','KS':'Topeka','KY':'Frankfort','LA':'Baton Rouge','ME':'Augusta','MD':'Annapolis','MA':'Boston','MI':'Lansing','MN':'Saint Paul','MS':'Jackson','MO':'Jefferson City','MT':'Helena','NE':'Lincoln','NV':'Carson City','NH':'Concord','NJ':'Trenton','NM':'Santa Fe','NY':'Albany','NC':'Raleigh','ND':'Bismarck','OH':'Columbus','OK':'Oklahoma City','OR':'Salem','PA':'Harrisburg','RI':'Providence','SC':'Columbia','SD':'Pierre','TN':'Nashville','TX':'Austin','UT':'Salt Lake City','VT':'Montpelier','VA':'Richmond','WA':'Olympia','WV':'Charleston','WI':'Madison','WY':'Cheyenne','DC':'Washington'}

def main():
 archive=TileArchive(ROOT/'local-maps/us-z15.pmtiles');index=LocationIndex(archive);router=USRouter()
 folder=ROOT/'local-data/state-verification';folder.mkdir(parents=True,exist_ok=True);results=[]
 assert router.status()['ready']
 boundaries=state_boundaries()
 assert {meta['code'] for meta,_ in boundaries}==set(CAPITALS),'State boundary resources are missing or incomplete; cannot verify all states.'
 with patch('socket.socket',side_effect=AssertionError('Network forbidden')):
  for meta,geom in sorted(boundaries,key=lambda item:item[0]['code']):
   code=meta['code'];capital=CAPITALS[code];start=time.monotonic();row={'state':meta['name'],'code':code,'city':capital}
   try:
    cities=[p for p in index.search(f'{capital}, {code}') if normalized(p['name'])==normalized(capital)]
    if not cities and capital=='Saint Paul':cities=index.search(f'St. Paul, {code}')
    assert cities,'City label missing in intended state'
    center=cities[0]['point'];assert in_state(center,geom),'Wrong state returned'
    roads=[p for p in archive.nearest(center,'',limit=5000,include_roads=True,radius_m=1800) if p['kind']=='road' and in_state(p['point'],geom)]
    assert roads,'No roads in local basemap'
    origin=roads[0];destinations=[]
    # A long street's nearest point may stay close to the city center. Choose separate
    # destination neighborhoods before snapping to road geometry, as a map click would.
    for dy,dx in [(0,1),(1,0),(0,-1),(-1,0)]:
     target=[center[0]+dy/111,center[1]+dx/(111*math.cos(math.radians(center[0])))]
     found=[p for p in archive.nearest(target,'',limit=3000,include_roads=True,radius_m=350) if p['kind']=='road' and in_state(p['point'],geom)]
     destinations.extend(found[:3])
    assert destinations,'No distinct destination road found'
    attempts=[];routes=[]
    for dest in destinations[:12]:
     try:
      route=router.route(origin['point'],dest['point'])
      assert route['distance_m']>600,'Route unexpectedly short'
      assert route['steps'],'Missing turn instructions'
      assert geom.covers(LineString([(p[1],p[0]) for p in route['points']])),'Route leaves intended state'
      routes.append({'origin':origin['point'],'origin_label':origin['name'],'destination':dest['point'],'destination_label':dest['name'],'miles':route['distance_miles'],'steps':len(route['steps']),'gaps':[route['start_gap_m'],route['end_gap_m']]})
      if len(routes)==2:break
     except Exception as e:attempts.append({'destination':dest['name'],'error':str(e)})
    assert len(routes)==2,f'Only {len(routes)} successful walks; attempts: {attempts}'
    water=archive.nearest(center,'water',limit=3)
    row.update(passed=True,routes=routes,water_records=len(water),rejected_candidates=attempts)
   except Exception as error:row.update(passed=False,error=str(error))
   row['seconds']=round(time.monotonic()-start,2);results.append(row)
   (folder/'results.json').write_text(json.dumps(results,indent=2))
   print(('PASS' if row['passed'] else 'FAIL'),code,capital,row.get('error',''),row['seconds'],flush=True)
 failed=[r for r in results if not r['passed']]
 print(f'{len(results)-len(failed)} / {len(results)} jurisdictions passed; {sum(len(r.get("routes",[])) for r in results)} walks',flush=True)
 if failed:raise SystemExit(1)

if __name__=='__main__':main()
