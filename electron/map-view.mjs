import {Map, Marker, NavigationControl, ScaleControl, Popup, setWorkerUrl, addProtocol} from 'maplibre-gl';
import {Protocol} from 'pmtiles';
import {layers, namedFlavor} from '@protomaps/basemaps';

setWorkerUrl('atlas://local/maplibre-gl-worker.mjs');
const protocol=new Protocol();addProtocol('pmtiles',protocol.tile);
const empty=()=>({type:'FeatureCollection',features:[]});
const pointFeature=(point,properties={})=>({type:'Feature',properties,geometry:{type:'Point',coordinates:[point[1],point[0]]}});
let map,current={},route=null,results=[],popup,previewMarker,clickMode=null,lastArchive;
function style(){
 return {version:8,glyphs:'atlas://local/fonts/{fontstack}/{range}.pbf',sprite:'atlas://local/sprites/v4/light',
 sources:{basemap:{type:'vector',url:'pmtiles://atlas://local/archive.pmtiles',attribution:'© OpenStreetMap contributors · ODbL'}},
 layers:layers('basemap',namedFlavor('dark'),{lang:'en'})};
}
function overlay(){
 if(!map?.isStyleLoaded())return;
 for(const name of ['position','route','results','coverage'])if(!map.getSource(name))map.addSource(name,{type:'geojson',data:empty()});
 if(!map.getLayer('coverage-fill')){
  map.addLayer({id:'coverage-fill',source:'coverage',type:'fill',paint:{'fill-color':'#79e6bf','fill-opacity':.06}});
  map.addLayer({id:'coverage-line',source:'coverage',type:'line',paint:{'line-color':'#79e6bf','line-width':1,'line-dasharray':[4,4]}});
  map.addLayer({id:'route-line',source:'route',type:'line',paint:{'line-color':'#85f1c4','line-width':5}});
  map.addLayer({id:'results-points',source:'results',type:'circle',paint:{'circle-radius':5,'circle-color':['case',['in','water',['get','kind']],'#5ac8fa','#ffc279'],'circle-stroke-color':'#101820','circle-stroke-width':2}});
  map.addLayer({id:'position-dot',source:'position',type:'circle',paint:{'circle-radius':7,'circle-color':'#fff','circle-stroke-color':'#2793ff','circle-stroke-width':4}});
 }
 const p=current.profile;
 map.getSource('position').setData({type:'FeatureCollection',features:p?.lat!==''&&p?.lat!=null&&p?.lon!==''&&p?.lon!=null?[pointFeature([Number(p.lat),Number(p.lon)])]:[]});
 map.getSource('route').setData({type:'FeatureCollection',features:route?.points?.length>1?[{type:'Feature',properties:{},geometry:{type:'LineString',coordinates:route.points.map(p=>[p[1],p[0]])}}]:[]});
 map.getSource('results').setData({type:'FeatureCollection',features:results.map(p=>pointFeature(p.point,p))});
 map.getSource('coverage').setData({type:'FeatureCollection',features:(current.routingPacks||[]).map(p=>{
  const [s,w,n,e]=p.bounds;return {type:'Feature',properties:{},geometry:{type:'Polygon',coordinates:[[[w,s],[e,s],[e,n],[w,n],[w,s]]]}};
 })});
}
function ensureMap(){
 if(map)return;
 map=new Map({container:'detail-map',style:style(),center:[-98,39],zoom:3,maxZoom:19,attributionControl:true});
 map.addControl(new NavigationControl(),'top-right');map.addControl(new ScaleControl({unit:'imperial'}),'bottom-left');
 map.on('load',()=>{overlay();center();document.querySelector('#map-local-status').textContent='Local US basemap · Offline';});
 map.on('error',e=>{document.querySelector('#map-local-status').textContent='Map asset unavailable: '+e.error.message;});
 map.on('click',event=>{
  const point=[event.lngLat.lat,event.lngLat.lng];
  if(clickMode){const action=clickMode;setMode(null);window.dispatchEvent(new CustomEvent('atlas-point',{detail:{point,action}}));return;}
  const features=map.queryRenderedFeatures(event.point,{layers:['results-points']});
  const place=features[0]?.properties;
  const content=document.createElement('div');
  const title=document.createElement('strong');title.textContent=place?.name||'Selected point';
  const coords=document.createElement('p');coords.textContent='Confirm this point on the map.';
  const here=document.createElement('button');here.textContent='I am here';here.onclick=()=>{popup.remove();window.dispatchEvent(new CustomEvent('atlas-point',{detail:{point,action:'position',name:place?.name}}));};
  const go=document.createElement('button');go.textContent='Walking directions';go.onclick=()=>{popup.remove();window.dispatchEvent(new CustomEvent('atlas-point',{detail:{point,action:'route'}}));};
  content.append(title,coords,here,go);popup?.remove();popup=new Popup().setLngLat(event.lngLat).setDOMContent(content).addTo(map);
 });
 window.jarvisDetailMap=map;
}
function center(){
 const p=current.profile;
 if(map&&p?.lat!==''&&p?.lat!=null&&p?.lon!==''&&p?.lon!=null)map.jumpTo({center:[Number(p.lon),Number(p.lat)],zoom:14});
}
function setMode(mode){clickMode=mode;if(map)map.getCanvas().style.cursor=mode?'crosshair':'';document.querySelector('#map-click-hint').textContent=mode==='position'?'Click your current position.':mode==='route'?'Click your destination.':'Click a point for position or directions.';}
window.offlineAtlas={
 update(state,newRoute){current=state;route=newRoute;const enabled=state.basemap?.enabled;
  document.querySelector('#detail-map').hidden=!enabled;document.querySelector('#map-canvas').hidden=!!enabled;
  if(enabled){if(lastArchive&&lastArchive!==state.basemap.path&&map){map.remove();map=null;}lastArchive=state.basemap.path;ensureMap();overlay();map.resize();}},
 results(rows){results=rows;overlay();},
 route(value){route=value;overlay();if(value?.points?.length&&map){const lngs=value.points.map(p=>p[1]),lats=value.points.map(p=>p[0]);map.fitBounds([[Math.min(...lngs),Math.min(...lats)],[Math.max(...lngs),Math.max(...lats)]],{padding:65,maxZoom:17,duration:250});}},
 focus(point){map?.flyTo({center:[point[1],point[0]],zoom:16,duration:250});},
 explore(point,zoom=12){map?.flyTo({center:[point[1],point[0]],zoom,duration:250});},
 viewCenter(){if(!map)return null;const c=map.getCenter();return [c.lat,c.lng];},
 preview(place){
  if(!map)return;const point=place.point;
  map.flyTo({center:[point[1],point[0]],zoom:17,duration:250});
  previewMarker?.remove();previewMarker=new Marker({color:'#ffc279'}).setLngLat([point[1],point[0]]).addTo(map);
  popup?.remove();const content=document.createElement('div');
  const title=document.createElement('strong');title.textContent=place.name;
  const note=document.createElement('p');note.textContent='Check the nearby streets. Is this where you are?';
  const confirm=document.createElement('button');confirm.textContent='I am here';confirm.onclick=()=>{popup.remove();previewMarker.remove();window.dispatchEvent(new CustomEvent('atlas-point',{detail:{point,action:'position',name:place?.name}}));};
  content.append(title,note,confirm);popup=new Popup().setLngLat([point[1],point[0]]).setDOMContent(content).addTo(map);
 },
 center, mode:setMode, resize(){map?.resize();}
};
