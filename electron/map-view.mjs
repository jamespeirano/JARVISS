import {Map, Marker, NavigationControl, ScaleControl, Popup, setWorkerUrl, addProtocol} from 'maplibre-gl';
import {Protocol} from 'pmtiles';
import {layers, namedFlavor} from '@protomaps/basemaps';

setWorkerUrl('atlas://local/maplibre-gl-worker.mjs');
const protocol=new Protocol();addProtocol('pmtiles',protocol.tile);
const empty=()=>({type:'FeatureCollection',features:[]});
const pointFeature=(point,properties={})=>({type:'Feature',properties,geometry:{type:'Point',coordinates:[point[1],point[0]]}});
// Overlay colours come from the stylesheet tokens (accent family) so the map matches the app.
const token=name=>getComputedStyle(document.documentElement).getPropertyValue(name).trim();
let map,current={},route=null,results=[],popup,previewMarker,clickMode=null,lastArchive;
function style(){
 return {version:8,glyphs:'atlas://local/fonts/{fontstack}/{range}.pbf',sprite:'atlas://local/sprites/v4/light',
 sources:{basemap:{type:'vector',url:'pmtiles://atlas://local/archive.pmtiles',attribution:'© OpenStreetMap contributors · ODbL'}},
 layers:layers('basemap',namedFlavor('dark'),{lang:'en'})};
}
function position(){const p=current.profile;return p?.lat!==''&&p?.lat!=null&&p?.lon!==''&&p?.lon!=null?[Number(p.lat),Number(p.lon)]:null;}
function metersBetween(a,b){
 const rad=d=>d*Math.PI/180,dLat=rad(b[0]-a[0]),dLon=rad(b[1]-a[1]);
 const s=Math.sin(dLat/2)**2+Math.cos(rad(a[0]))*Math.cos(rad(b[0]))*Math.sin(dLon/2)**2;
 return 2*6371000*Math.asin(Math.sqrt(s));
}
// Units come from the renderer's formatter (Settings → Units); miles are the fallback when it is not loaded.
function formatDistance(m){
 if(typeof window.formatDistance==='function')return window.formatDistance(m);
 const miles=m/1609.344;return miles<.1?`${Math.round(m*3.28084)} ft`:`${miles<10?miles.toFixed(1):Math.round(miles)} miles`;
}
function distanceText(point){
 const here=position();if(!here)return 'Set your position to see the distance.';
 return `${formatDistance(metersBetween(here,point))} from you · straight line`;
}
// MapLibre's controls ship inverted PNG/SVG icons; the app sprite (index.html) replaces them so every glyph shares one stroke.
function sprite(name){
 const svg=document.createElementNS('http://www.w3.org/2000/svg','svg'),use=document.createElementNS('http://www.w3.org/2000/svg','use');
 svg.setAttribute('class','icon');svg.setAttribute('aria-hidden','true');use.setAttribute('href','#i-'+name);svg.append(use);return svg;
}
function restyleControls(){
 const root=map.getContainer();
 for(const [selector,name] of [['.maplibregl-ctrl-zoom-in','plus'],['.maplibregl-ctrl-zoom-out','minus'],['.maplibregl-ctrl-attrib-button','info']]){
  const el=root.querySelector(selector);if(el&&!el.querySelector('.icon'))el.replaceChildren(sprite(name));
 }
}
function closeIcon(p){const button=p.getElement()?.querySelector('.maplibregl-popup-close-button');if(button&&!button.querySelector('.icon'))button.replaceChildren(sprite('close'));return p;}
function placePopup(name,point,{note,walk=true}={}){
 const content=document.createElement('div');
 const named=window.placeName?.(name); // "Unnamed swimming pool" → title "Swimming pool", meta "Unnamed · …"
 const title=window.placeTitle?window.placeTitle('strong',name):Object.assign(document.createElement('strong'),{textContent:named?.label||name||'Selected point'});
 const distance=document.createElement('p');distance.className='popup-distance';distance.textContent=(named?.unnamed?'Unnamed · ':'')+(note||distanceText(point));
 const actions=document.createElement('div');actions.className='popup-actions';
 const here=document.createElement('button');here.textContent='Set as my position';
 here.onclick=()=>{popup?.remove();previewMarker?.remove();previewMarker=null;window.dispatchEvent(new CustomEvent('atlas-point',{detail:{point,action:'position',name}}));};
 actions.append(here);
 if(walk){const go=document.createElement('button');go.textContent='Walk here';go.onclick=()=>{popup?.remove();window.dispatchEvent(new CustomEvent('atlas-point',{detail:{point,action:'route',name}}));};actions.append(go);}
 content.append(title,distance,actions);return content;
}
function overlay(){
 if(!map?.isStyleLoaded())return;
 for(const name of ['position','route','results','coverage'])if(!map.getSource(name))map.addSource(name,{type:'geojson',data:empty()});
 if(!map.getLayer('coverage-fill')){
  const accent=token('--accent'),strong=token('--accent-strong'),ink=token('--bg-0'),fg=token('--fg-1');
  map.addLayer({id:'coverage-fill',source:'coverage',type:'fill',paint:{'fill-color':accent,'fill-opacity':.06}});
  map.addLayer({id:'coverage-line',source:'coverage',type:'line',paint:{'line-color':accent,'line-width':1,'line-dasharray':[4,4]}});
  map.addLayer({id:'route-casing',source:'route',type:'line',layout:{'line-cap':'round','line-join':'round'},paint:{'line-color':ink,'line-width':8,'line-opacity':.8}});
  map.addLayer({id:'route-line',source:'route',type:'line',layout:{'line-cap':'round','line-join':'round'},paint:{'line-color':strong,'line-width':4}});
  map.addLayer({id:'results-points',source:'results',type:'circle',paint:{'circle-radius':6,'circle-color':['case',['in','water',['get','kind']],strong,accent],'circle-stroke-color':ink,'circle-stroke-width':2}});
  map.addLayer({id:'position-dot',source:'position',type:'circle',paint:{'circle-radius':6,'circle-color':fg,'circle-stroke-color':accent,'circle-stroke-width':4}});
 }
 const here=position();
 map.getSource('position').setData({type:'FeatureCollection',features:here?[pointFeature(here)]:[]});
 map.getSource('route').setData({type:'FeatureCollection',features:route?.points?.length>1?[{type:'Feature',properties:{},geometry:{type:'LineString',coordinates:route.points.map(p=>[p[1],p[0]])}}]:[]});
 map.getSource('results').setData({type:'FeatureCollection',features:results.map(p=>pointFeature(p.point,p))});
 map.getSource('coverage').setData({type:'FeatureCollection',features:(current.routingPacks||[]).map(p=>{
  const [s,w,n,e]=p.bounds;return {type:'Feature',properties:{},geometry:{type:'Polygon',coordinates:[[[w,s],[e,s],[e,n],[w,n],[w,s]]]}};
 })});
}
function ensureMap(){
 if(map)return;
 map=new Map({container:'detail-map',style:style(),center:[-98,39],zoom:3,maxZoom:19,attributionControl:true});
 map.addControl(new NavigationControl({showCompass:false}),'top-right');map.addControl(new ScaleControl({unit:'imperial'}),'bottom-left');
 restyleControls();
 map.on('load',()=>{overlay();center();restyleControls();document.querySelector('#map-local-status').textContent='Local US map · Offline';});
 map.on('error',e=>{document.querySelector('#map-local-status').textContent='Map asset unavailable: '+e.error.message;});
 map.on('click',event=>{
  const point=[event.lngLat.lat,event.lngLat.lng];
  if(clickMode){const action=clickMode;setMode(null);window.dispatchEvent(new CustomEvent('atlas-point',{detail:{point,action}}));return;}
  previewMarker?.remove();previewMarker=null; // A rejected landmark preview must not linger.
  const place=map.queryRenderedFeatures(event.point,{layers:['results-points']})[0]?.properties;
  popup?.remove();popup=closeIcon(new Popup().setLngLat(event.lngLat).setDOMContent(placePopup(place?.name,point)).addTo(map));
 });
 window.jarvisDetailMap=map;
}
function center(){
 const here=position();
 if(map&&here)map.jumpTo({center:[here[1],here[0]],zoom:14});
}
// The map's current centre as [lat, lng]; lets a keyboard "Use map centre" action set a position without a click.
function centerPoint(){if(!map)return null;const c=map.getCenter();return [c.lat,c.lng];}
function setMode(mode){clickMode=mode;if(map)map.getCanvas().style.cursor=mode?'crosshair':'';document.querySelector('#map-click-hint').textContent=mode==='position'?'Click your current position.':mode==='route'?'Click your destination.':'Click a point for position or directions.';}
window.offlineAtlas={
 update(state,newRoute){current=state;route=newRoute;const enabled=state.basemap?.enabled;
  document.querySelector('#detail-map').hidden=!enabled; // #map-empty (renderer.js) is the fallback when there is no archive
  if(enabled){if(lastArchive&&lastArchive!==state.basemap.path&&map){map.remove();map=null;}lastArchive=state.basemap.path;ensureMap();overlay();map.resize();}},
 results(rows){results=rows;overlay();},
 route(value){route=value;overlay();if(value?.points?.length&&map){const lngs=value.points.map(p=>p[1]),lats=value.points.map(p=>p[0]);map.fitBounds([[Math.min(...lngs),Math.min(...lats)],[Math.max(...lngs),Math.max(...lats)]],{padding:65,maxZoom:17,duration:250});}},
 focus(point){map?.flyTo({center:[point[1],point[0]],zoom:16,duration:250});},
 explore(point,zoom=12){map?.flyTo({center:[point[1],point[0]],zoom,duration:250});},
 viewCenter:centerPoint,
 preview(place){
  if(!map)return;const point=place.point;
  map.flyTo({center:[point[1],point[0]],zoom:17,duration:250});
  previewMarker?.remove();previewMarker=new Marker({color:token('--accent')}).setLngLat([point[1],point[0]]).addTo(map);
  popup?.remove();popup=closeIcon(new Popup().setLngLat([point[1],point[0]]).setDOMContent(placePopup(place.name,point,{note:'Check the nearby streets. Is this where you are?',walk:false})).addTo(map));
 },
 center, centerPoint, mode:setMode, resize(){map?.resize();}
};
