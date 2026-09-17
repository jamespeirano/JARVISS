const $=s=>document.querySelector(s);
let state={},busy=false,voice=false,route=null,searchTimer,pendingMethod=null,remoteOperation=null;
let chatFinished=false,voiceStarting=false,preview=false,audioSaving=false;
let voicePhase='Voice off';
const exclusiveMethods=new Set(['setup_run','chat','route','clear','start_model','download_model','download_voice','download_us_maps']);
const operationLabels={setup_run:'Preparing JARVISS',download_model:'Preparing model and voice',download_voice:'Preparing offline voice',download_us_maps:'Preparing US offline maps',start_model:'Loading local model',chat:'Thinking',route:'Calculating walking directions',clear:'Clearing conversation'};
const titles={assistant:'Assistant',situation:'My situation',atlas:'Offline atlas',knowledge:'Knowledge',recovery:'Recovery plan',settings:'Settings'};
function renderOperation(){
 const method=pendingMethod||remoteOperation?.method;
 const label=remoteOperation?.label||operationLabels[method];
 const active=!!(method||remoteOperation);
 window.renderSetupOperation?.(active, method);
 for(const id of ['download-model','download-voice','download-us-maps','clear','choose-model'])$('#'+id).disabled=active||(id==='download-us-maps'&&!!(state.basemap&&state.usRouting?.ready));
 $('#start-model').disabled=active||!state.settings?.model||state.modelAvailable===false;
 $('#send').disabled=active||busy;
 $('#voice-toggle').disabled=voiceStarting||(!voice&&(active||!state.ready));
 const waiting=method==='chat'&&!chatFinished;
 $('#messages').setAttribute('aria-busy',String(waiting));
 if(waiting&&!$('#response-wait')){
  document.body.classList.add('has-history');
  const loader=document.createElement('div');loader.id='response-wait';loader.setAttribute('role','status');
  const dots=document.createElement('span');dots.className='thinking-dots';dots.setAttribute('aria-hidden','true');
  for(let i=0;i<3;i++)dots.append(document.createElement('i'));
  loader.append(dots,document.createTextNode('Thinking…'));$('#messages').append(loader);$('#messages').scrollTop=$('#messages').scrollHeight;
 }else if(!waiting)$('#response-wait')?.remove();
 $('#status').textContent=voice&&waiting?'Generating response…':label||(state.ready?'Ready':'Model not started');
 $('#status-dot').classList.toggle('working',waiting);
 renderVoiceActivity(waiting);
 $('#model-setup-status').textContent=active?`${label}. ${remoteOperation?.progress||'Please wait for this operation to finish.'}`:state.ready?'Model is running locally.':state.settings?.model?state.modelAvailable===false?'The selected model file is missing. Choose an existing GGUF or prepare the model again.':'Model selected. Ready to start.':'Choose an existing GGUF or prepare the model and voice files first.';
 if(remoteOperation?.progress)$('#progress').textContent=remoteOperation.progress;
}
function renderVoiceActivity(waiting=(pendingMethod||remoteOperation?.method)==='chat'&&!chatFinished){
 const generating=voice&&waiting&&!['Preparing speech','Speaking'].includes(voicePhase);
 $('#voice-badge').textContent=generating?'GENERATING RESPONSE…':voicePhase.toUpperCase();
 $('#voice-badge').classList.toggle('generating',generating);
 $('#orb').classList.toggle('active',generating||['Starting voice','Preparing speech','Listening','Speaking'].includes(voicePhase));
}
function mapFullscreen(enabled){
 document.body.classList.toggle('map-fullscreen',enabled);
 $('#map-fullscreen').textContent=enabled?'Exit full screen':'Full screen';
 $('#map-fullscreen').setAttribute('aria-pressed',String(enabled));
 requestAnimationFrame(()=>{window.offlineAtlas?.resize();draw();});
}
$('#map-fullscreen').onclick=async()=>{const button=$('#map-fullscreen'),enabled=!document.body.classList.contains('map-fullscreen');button.disabled=true;try{await window.jarviss.mapFullscreen(enabled);mapFullscreen(enabled);}catch(e){error(e);}finally{button.disabled=false;}};
document.addEventListener('keydown',event=>{if(event.key==='Escape'&&document.body.classList.contains('map-fullscreen')){window.jarviss.mapFullscreen(false).then(()=>mapFullscreen(false)).catch(error);}});
function error(e){
 const text=(e.message||String(e)).replace(/^Error invoking remote method '[^']+': (?:Error: )?/,'');
 const inSetup=$('#setup').classList.contains('visible');
 $('#error').hidden=inSetup;
 $(inSetup?'#setup-warning':'#error').textContent=text;
 renderOperation();
}
async function call(method,args){
 const exclusive=exclusiveMethods.has(method);
 if(exclusive&&(pendingMethod||remoteOperation)){
  const problem=new Error((remoteOperation?.label||operationLabels[pendingMethod]||'Another operation is running')+'. Wait for it to finish.');error(problem);throw problem;
 }
 if(exclusive){pendingMethod=method;if(method==='chat')chatFinished=false;$('#error').hidden=true;renderOperation();}
 try{return await window.jarviss.command(method,args);}catch(e){error(e);throw e;}
 finally{if(exclusive){pendingMethod=null;renderOperation();}}
}
function page(name){if(name!=='atlas'&&document.body.classList.contains('map-fullscreen')){window.jarviss.mapFullscreen(false).catch(error);mapFullscreen(false);}document.body.classList.toggle('setup-screen',name==='setup'||name==='startup');document.querySelectorAll('.page').forEach(el=>el.classList.toggle('visible',el.id===name));document.querySelectorAll('[data-page]').forEach(el=>el.classList.toggle('selected',el.dataset.page===name));if(name==='atlas'){draw();window.offlineAtlas?.resize();}}
document.querySelectorAll('[data-page]').forEach(el=>el.onclick=()=>page(el.dataset.page));
function message(role,text,references=[]){const node=document.createElement('div');node.className='message '+role;const label=document.createElement('span');label.className='speaker';label.textContent=role==='user'?'YOU':'JARVISS';node.append(label,document.createTextNode(text));if(references.length){const sources=document.createElement('div');sources.className='answer-references';const heading=document.createElement('small');heading.textContent='Reference passages';sources.append(heading);for(const ref of references){const button=document.createElement('button');button.textContent=ref.title+' · '+ref.heading;button.onclick=()=>openReference(ref.id,ref.section).catch(error);sources.append(button);}node.append(sources);}$('#messages').insertBefore(node,$('#response-wait'));$('#messages').scrollTop=$('#messages').scrollHeight;document.body.classList.add('has-history');}
function card(title,text,detail){const el=document.createElement('div');el.className='panel';for(const [tag,value] of [['h3',title],['p',text],['small',detail]]){const n=document.createElement(tag);n.textContent=value||'';el.append(n);}return el;}
function renderState(initial=false){
 if(Object.hasOwn(state,'operation'))remoteOperation=state.operation;renderOperation();
 $('#model-name').textContent=state.settings?.model||'No model selected';$('#gpu').value=state.settings?.gpu_layers==='auto'?'':state.settings?.gpu_layers??'';$('#voice-ready').textContent=state.voiceReady?'Offline voice pack is installed.':'Offline voice pack is missing.';
 if(initial){renderPrompts(state.settings);for(const k of ['situation','supplies','location_text'])$('#profile-form').elements[k].value=state.profile?.[k]??'';for(const item of state.history||[])message(item.role,item.content,item.references);}
 $('#documents').replaceChildren(...(state.documents||[]).map(d=>docEntry(d.title,d.text,`Imported ${d.imported_at.slice(0,10)}`)));
 if(!state.documents?.length){const empty=document.createElement('p');empty.className='docs-empty';empty.textContent='No imported documents yet.';$('#documents').append(empty);}
 renderReferences();
 $('#guides').replaceChildren(...(state.guides||[]).map(d=>docEntry(d.title,d.text,d.url?'Source: '+new URL(d.url).hostname:'JARVISS planning checklist',d.prompt,d.plan)));
 $('#recovery-document').replaceChildren();for(const line of (state.recovery||'').split('\n')){if(!line.trim())continue;const tag=line.startsWith('## ')?'h3':line.startsWith('# ')?'h2':'p';const el=document.createElement(tag);el.textContent=line.replace(/^#{1,2} /,'');$('#recovery-document').append(el);}
 if(state.map){$('#map-caption').textContent=`${state.map.label||'Your saved area'} · OSM snapshot ${state.map.osm_timestamp||'unknown'} · Conditions unverified`;}renderAtlas();draw();window.renderPlanner?.();
}
async function refresh(){state=await call('state');route=state.route||null;renderState();}
async function send(text){if(busy||pendingMethod||remoteOperation)return;text=text.trim();if(!text)return;busy=true;$('#send').disabled=true;$('#error').hidden=true;$('#question').value='';message('user',text);try{await call('chat',{text});}finally{busy=false;renderOperation();}}
$('#composer').onsubmit=e=>{e.preventDefault();send($('#question').value).catch(()=>{});};
$('#question').onkeydown=e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();$('#composer').requestSubmit();}};
document.querySelectorAll('[data-prompt]').forEach(el=>el.onclick=()=>send(el.dataset.prompt).catch(()=>{}));
$('#profile-form').onsubmit=async e=>{e.preventDefault();try{state.profile=await call('save_profile',Object.fromEntries(new FormData(e.target)));$('#saved').textContent='Saved';route=null;renderState();}catch{}};
$('#voice-toggle').onclick=async()=>{const button=$('#voice-toggle');voiceStarting=true;button.disabled=true;button.textContent=voice?'Stopping…':'Starting voice…';$('#error').hidden=true;try{const result=await call('voice',{enabled:!voice});voice=result.enabled;}catch{voice=false;}finally{voiceStarting=false;button.textContent=voice?'Stop voice mode':'Start voice mode';renderOperation();}};

$('#clear').onclick=async()=>{try{await call('clear');$('#messages').replaceChildren();document.body.classList.remove('has-history');}catch{}};
$('#start-model').onclick=async()=>{try{await call('start_model',{layers:$('#gpu').value===''?'auto':Number($('#gpu').value),path:state.settings?.model});await refresh();}catch{}};
$('#choose-model').onclick=async()=>{try{const path=await window.jarviss.pick('model');if(path){state.settings.model=path;$('#model-name').textContent=path;state.modelAvailable=true;renderOperation();}}catch(e){error(e);}};
for(const [id,method] of [['download-voice','download_voice'],['download-us-maps','download_us_maps']])$('#'+id).onclick=async()=>{const b=$('#'+id);b.disabled=true;try{await call(method,{});$('#progress').textContent='Download complete.';if(method==='download_us_maps')$('#map-progress').textContent='US map and walking directions are ready offline.';await refresh();}catch{}finally{renderOperation();}};
$('#import-document').onclick=async()=>{try{await window.jarviss.pick('document');await refresh();}catch(e){error(e);}};
$('#map-search').oninput=()=>{clearTimeout(searchTimer);searchTimer=setTimeout(places,180);};
let searchSequence=0,locationSequence=0,locationCenter=null;
const miles=m=>`${(m/1609.344).toFixed(2)} miles (${Math.round(m).toLocaleString()} m)`;
function renderRoute(){
 const container=$('#route-info');container.replaceChildren();
 if(route){
  const heading=document.createElement('strong');heading.textContent=`Walk ${route.destination_note?'near':'to'} ${route.destination||'destination'} · ${miles(route.distance_m)}`;container.append(heading);
  if(route.destination_note){const note=document.createElement('p');note.textContent=route.destination_note;container.append(note);}
  const steps=route.steps||[];let index=0;
  if(steps.length){
   const current=document.createElement('p'),controls=document.createElement('div'),back=document.createElement('button'),next=document.createElement('button');back.textContent='Back';next.textContent='Next';controls.className='route-step-controls';controls.append(back,next);
   const show=()=>{current.textContent=`${index+1} of ${steps.length} · ${steps[index].instruction}`;back.disabled=index===0;next.disabled=index===steps.length-1;};
   back.onclick=()=>{index--;show();if(steps[index].point)window.offlineAtlas?.focus(steps[index].point);};next.onclick=()=>{index++;show();if(steps[index].point)window.offlineAtlas?.focus(steps[index].point);};show();container.append(current,controls);
   const all=document.createElement('details'),summary=document.createElement('summary'),list=document.createElement('p');summary.textContent='All directions';list.textContent=steps.map((s,i)=>`${i+1}. ${s.instruction}`).join('\n');all.append(summary,list);container.append(all);
  }
  if(route.start_gap_m||route.end_gap_m){const gaps=document.createElement('small');gaps.textContent=`Unmapped connections: ${Math.round(route.start_gap_m)} m at the start; ${Math.round(route.end_gap_m)} m at the end. Check these on foot.`;container.append(gaps);}
 }
 window.offlineAtlas?.route(route);
}
function renderAtlas(){
 window.offlineAtlas?.update(state,route);
 const p=state.profile;
 const located=p?.lat!==''&&p?.lat!=null&&p?.lon!==''&&p?.lon!=null;
 $('#map-caption').textContent=state.basemap?.enabled?`OSM snapshot ${state.basemap.osm_timestamp} · Nearby resources: search within 5 km of your position.`:state.map?`${state.map.label||'Prepared area'} · OSM snapshot ${state.map.osm_timestamp||'unknown'}`:'Download US offline maps to begin.';
 if(!located)$('#location-picker').open=true;
 $('#map-position-note').textContent=located?`Your position: ${p.position_name||'Confirmed on map'}`:'Choose Find my location, then confirm where you are.';
 $('#situation-location-status').textContent=located?'Position confirmed on map':'Position not confirmed';
 $('#use-basemap').hidden=!(state.basemap&&!state.basemap.enabled);
 const installed=!!(state.basemap && state.usRouting?.ready);
 $('#us-map-status').textContent=installed?'US map and walking directions are ready offline.':state.basemap?'US basemap installed. Download walking directions once for the full US coverage.':'Download the US basemap and walking directions once (about 23 GB total).';
 $('#download-us-maps').textContent=installed?'Installed':state.basemap?'Download US walking directions':'Download US offline maps';
 $('#download-us-maps').disabled=installed||!!(pendingMethod||remoteOperation);
 if(state.mapError)$('#map-local-status').textContent=state.mapError;
 renderRoute();places();
}
async function places(){
 const sequence=++searchSequence;
 if(!state.profile||state.profile.lat===''||state.profile.lat==null){$('#places').textContent='Set your position to search nearby.';return;}
 $('#places').textContent='Searching local map…';
 try{
  const rows=await call('nearest',{query:$('#map-search').value});if(sequence!==searchSequence)return;
  window.offlineAtlas?.results(rows);$('#places').replaceChildren();
  if(!rows.length){$('#places').textContent='No matching records in the searched area. Try another name or resource.';return;}
  for(const p of rows){
   const item=document.createElement('div');item.className='place-card';
   const title=document.createElement('strong');title.textContent=p.name;
   const info=document.createElement('small');info.textContent=`${p.kind} · ${miles(p.distance_m)} straight-line`;
   const coords=document.createElement('small');coords.textContent='';
   const actions=document.createElement('div');actions.className='place-actions';
   const show=document.createElement('button');show.textContent='Show';show.onclick=()=>window.offlineAtlas?.focus(p.point);
   const walk=document.createElement('button');walk.textContent='Directions';walk.onclick=async()=>{route=null;renderRoute();try{route=await call('route',{id:p.id});renderRoute();draw();}catch{route=null;renderRoute();draw();}};
   actions.append(show,walk);item.append(title,info,coords,actions);$('#places').append(item);
  }
 }catch{}
}
$('#find-location').onclick=()=>{$('#location-picker').open=true;$('#city-search').focus();};
$('#locate-this-view').onclick=()=>{locationCenter=window.offlineAtlas?.viewCenter();$('#location-area-name').textContent=locationCenter?'Searching the area currently shown · not your saved position':'Choose a basemap first.';$('#landmark-search').focus();};
async function searchLocation(near){
 const query=$(near?'#landmark-search':'#city-search').value.trim();
 if(query.length<2){$('#location-search-status').textContent='Enter at least two letters.';return;}
 if(near&&!locationCenter){$('#location-search-status').textContent='Find an area first, or pan the map and choose “Search the area shown”.';return;}
 const sequence=++locationSequence;$('#location-search-status').textContent='Searching your local map…';
 try{
  const rows=await call('search_locations',{query,...(near?{near:locationCenter}:{})});if(sequence!==locationSequence)return;
  $('#location-results').replaceChildren();
  $('#location-search-status').textContent=rows.length?near?'Select a result to inspect it, then choose “I am here” only if it matches your position.':'Select an area to explore. This does not set your position.':'No matching labels in this search. Try a nearby larger town, a shorter road name, or pan the map to a familiar area.';
  for(const place of rows){
   const button=document.createElement('button');const name=document.createElement('strong');name.textContent=place.name;
   const detail=document.createElement('small');detail.textContent=near?`${place.kind} · inspect on map`:`${place.kind}${place.state?' · '+place.state:''} · ${place.population?Number(place.population).toLocaleString()+' recorded population · ':''}preview region on map`;
   button.append(name,detail);
   button.onclick=()=>{
    if(near){window.offlineAtlas?.preview(place);$('#location-picker').open=false;}
    else{locationCenter=place.point;$('#location-area-name').textContent=`Exploring ${place.name} · your position is not changed`;window.offlineAtlas?.explore(place.point,['state','province','country'].includes(place.kind)?6:12);$('#landmark-search').focus();}
   };
   $('#location-results').append(button);
  }
 }catch{}
}
$('#city-search-form').onsubmit=e=>{e.preventDefault();searchLocation(false);};
$('#landmark-search-form').onsubmit=e=>{e.preventDefault();searchLocation(true);};
$('#choose-basemap').onclick=async()=>{try{const result=await window.jarviss.pick('basemap');if(result)await refresh();}catch(e){error(e);}};
$('#use-basemap').onclick=async()=>{try{await call('use_basemap');await refresh();}catch{}};
$('#center-map').onclick=()=>window.offlineAtlas?.center();
$('#set-position').onclick=()=>{if(state.basemap?.enabled)window.offlineAtlas?.mode('position');else{error('Download US offline maps first.');}};
window.addEventListener('atlas-point',async({detail})=>{
 route=null;renderRoute();
 try{
  if(detail.action==='position'){
   state.profile=await call('set_map_position',{lat:detail.point[0],lon:detail.point[1],name:detail.name});
   $('#location-picker').open=false;
   $('#situation-location-status').textContent=state.profile.position_name||'Position confirmed';
   renderAtlas();
  }else{route=await call('route',{point:detail.point});renderRoute();}
 }catch{}
});
function draw(){if(state.basemap?.enabled){window.offlineAtlas?.update(state,route);return;}const c=$('#map-canvas'),ctx=c.getContext('2d'),r=c.getBoundingClientRect();if(!r.width)return;c.width=r.width*devicePixelRatio;c.height=r.height*devicePixelRatio;ctx.scale(devicePixelRatio,devicePixelRatio);if(!state.map){ctx.fillStyle='#8497ae';ctx.font='14px sans-serif';ctx.fillText('Download US offline maps to begin.',30,50);return;}const p=state.map,[s,w,n,e]=p.bounds,cos=Math.cos((s+n)/2*Math.PI/180),scale=Math.min((r.width-40)/((e-w)*cos),(r.height-40)/(n-s));const xy=v=>[r.width/2+(v[1]-(w+e)/2)*cos*scale,r.height/2-(v[0]-(s+n)/2)*scale];ctx.lineWidth=1;for(const road of p.roads){ctx.strokeStyle=road.walkable?'#40586b':'#253447';for(let i=1;i<road.nodes.length;i++){const a=p.nodes[road.nodes[i-1]],b=p.nodes[road.nodes[i]];if(a&&b){ctx.beginPath();ctx.moveTo(...xy(a));ctx.lineTo(...xy(b));ctx.stroke();}}}for(const place of p.places){ctx.fillStyle=place.kind.includes('water')?'#8bd6e5':'#deb492';ctx.beginPath();ctx.arc(...xy(place.point),3,0,Math.PI*2);ctx.fill();}if(route){ctx.strokeStyle='#b7e6ce';ctx.lineWidth=3;ctx.beginPath();route.points.forEach((p,i)=>i?ctx.lineTo(...xy(p)):ctx.moveTo(...xy(p)));ctx.stroke();}ctx.fillStyle='#c9dbe4';ctx.fillText('N ↑',15,22);}
new ResizeObserver(draw).observe($('#map-canvas'));
window.jarviss.subscribe(({event,data})=>{window.jarvisState?.(event,data);if(event==='operation'){const completed=remoteOperation?.method;if(data?.method==='chat'&&completed!=='chat')chatFinished=false;remoteOperation=data;renderOperation();if(!data&&!pendingMethod&&(completed?.startsWith('download')||completed==='start_model'||completed==='setup_run')){refresh().catch(()=>{});if(completed==='setup_run')window.refreshSetup?.();}}if(event==='status'){if(data==='Ready'||data==='Model not started'){state.ready=data==='Ready';if(remoteOperation?.legacy){remoteOperation=null;refresh().catch(()=>{});}}renderOperation();}if(event==='voice'){voicePhase=data;if(data==='Voice off'){voice=false;$('#voice-toggle').textContent='Start voice mode';}renderOperation();}if(event==='map_fullscreen')mapFullscreen(data);if(event==='mic_level')$('#mic-level').value=data;if(event==='partial')$('#heard-partial').textContent=data;if(event==='heard')message('user',data);if(event==='answer'){chatFinished=true;renderOperation();message('assistant',data.text,data.references);route=data.route||null;renderRoute();draw();}if(event==='voice_preview'){preview=!!data;renderPreview();}if(event==='error'){if(data.startsWith('Local service stopped'))remoteOperation=null;error(data);}if(event==='progress'){window.setupProgress?.(data);if(!Object.hasOwn(state,'operation')&&!pendingMethod&&!/index/i.test(data)){remoteOperation={method:'download_model',label:'Preparing offline files',progress:data,legacy:true};renderOperation();}$('#progress').textContent=data;if((pendingMethod||remoteOperation?.method)==='download_us_maps')$('#map-progress').textContent=data;if(/index/i.test(data))$('#location-search-status').textContent=data;}});
window.addEventListener('DOMContentLoaded',async()=>{
 try{
  state=await call('state');renderState(true);voice=!!state.voiceEnabled;voicePhase=voice?'Listening':'Voice off';preview=!!state.voicePreview;renderPreview();$('#voice-toggle').textContent=voice?'Stop voice mode':'Start voice mode';
  const needsSetup=state.setup?.status!=='ready'||!state.modelAvailable||!state.voiceReady||!state.basemap||!state.usRouting?.ready||remoteOperation?.method==='setup_run';
  if(needsSetup)await window.openSetup();else page('assistant');
  await audioDevices();renderOperation();
  if(!needsSetup&&state.settings?.model&&!state.ready&&!remoteOperation)await call('start_model');
 }catch{}
});

function docEntry(title,text,detail,prompt,plan){
 const el=document.createElement('details');el.className='doc-entry';
 const summary=document.createElement('summary');const name=document.createElement('span');name.textContent=title;
 const meta=document.createElement('small');meta.textContent=detail;summary.append(name,meta);
 const body=document.createElement('div');body.className='doc-body';body.textContent=text;
 const ask=document.createElement('button');ask.className='doc-ask';ask.textContent='Ask about this';ask.onclick=()=>{askDocument(title);if(prompt)$('#question').value=prompt;};el.append(summary,body,ask);if(plan){const open=document.createElement('button');open.textContent='Open '+({tasks:'Today',people:'People',messages:'Messages',supplies:'Supplies',power:'Power',garden:'Garden',log:'Log'}[plan]);open.onclick=()=>window.openPlan?.(plan);el.append(open);}return el;
}

function askDocument(title){page('assistant');$('#question').value=`Using the document "${title}", `;$('#question').focus();}
const referenceEntries=new Map();
function renderReferences(){
 const docs=state.references||[];
 $('#reference-summary').textContent=`${docs.length} documents · ${Math.round(docs.reduce((n,d)=>n+d.words,0)/1000).toLocaleString()}k words · Available offline`;
 // Keep expanded sections and their scroll position when unrelated state changes.
 if(referenceEntries.size===docs.length)return;
 referenceEntries.clear();$('#references').replaceChildren();
 for(const doc of docs){
  const entry=document.createElement('details');entry.className='doc-entry';
  const summary=document.createElement('summary'),title=document.createElement('span'),meta=document.createElement('small');
  title.textContent=doc.title;meta.textContent=`${doc.topic} · ${doc.publisher} · ${doc.words.toLocaleString()} words`;summary.append(title,meta);entry.append(summary);
  const body=document.createElement('div');body.className='reference-body';entry.append(body);
  const item={entry,body,sections:new Map(),loaded:null};referenceEntries.set(doc.id,item);
  entry.addEventListener('toggle',()=>{if(entry.open)loadReference(doc.id).catch(error);});
  $('#references').append(entry);
 }
}
async function loadReference(id){
 const item=referenceEntries.get(id);if(!item)throw new Error('This reference is not in the installed library.');
 if(item.loaded)return item.loaded;
 item.loaded=(async()=>{
  const doc=await call('reference',{id});
  const metadata=document.createElement('p');metadata.className='reference-note';metadata.textContent=`${doc.publisher} · Edition ${doc.date}\n${doc.note||''}`;item.body.append(metadata);
  const save=document.createElement('button');save.textContent='Save a copy';save.onclick=async()=>{try{if(await window.jarviss.saveReference(id)){save.textContent='Saved';setTimeout(()=>save.textContent='Save a copy',2000);}}catch(e){error(e);}};item.body.append(save);
  if(doc.pdf){const pdf=document.createElement('button');pdf.textContent='Save illustrated PDF';pdf.onclick=()=>window.jarviss.saveReference(id,'pdf').catch(error);item.body.append(pdf);}
  for(const section of doc.sections){
   const block=document.createElement('details');block.className='reference-section';block.id='reference-'+id+'-'+section.id;
   const heading=document.createElement('summary');heading.textContent=section.heading;
   const text=document.createElement('div');text.className='doc-body';text.textContent=section.text;
   const ask=document.createElement('button');ask.className='doc-ask';ask.textContent='Ask about this';ask.onclick=()=>askDocument(doc.title+' · '+section.heading);
   block.append(heading,text,ask);item.body.append(block);item.sections.set(section.id,block);
  }
  const source=document.createElement('details');source.className='reference-source';const heading=document.createElement('summary');heading.textContent='Source and reuse';
  const text=document.createElement('p');text.textContent=[...(doc.sources||[doc.url]),doc.attribution||'',doc.license_note].filter(Boolean).join('\n');source.append(heading,text);item.body.append(source);
 })().catch(e=>{item.loaded=null;throw e;});return item.loaded;
}
async function openReference(id,section){
 page('docs');$('#docs-search').value='';filterDocs();
 const item=referenceEntries.get(id);if(!item)throw new Error('This reference is not in the installed library.');
 item.entry.open=true;await loadReference(id);
 const target=item.sections.get(section)||item.entry;
 if(target!==item.entry)target.open=true;
 target.scrollIntoView({block:'start'});target.classList.add('reference-selected');
 setTimeout(()=>target.classList.remove('reference-selected'),4000);
}
const recoveryAsk=document.createElement('button');recoveryAsk.className='doc-ask';recoveryAsk.textContent='Ask about this';recoveryAsk.onclick=()=>askDocument('Regroup and rebuild');$('.recovery-entry').append(recoveryAsk);

async function audioDevices(){const list=await call('audio_devices');for(const [id,kind,key] of [['input-device','input','input_device'],['output-device','output','output_device']]){const select=$('#'+id);select.replaceChildren(new Option('System default',''));for(const d of list.filter(d=>d[kind])){const o=new Option(`${d.name} · ${d.host}`,d.id);select.add(o);if(state.settings?.[key]?.name===d.name&&state.settings[key].host===d.host)o.selected=true;}}$('#voice-name').value=state.settings?.voice_name||'bm_george';}
function renderPreview(){
 $('#test-speaker').textContent=preview?'Stop preview':'Preview voice';
 $('#test-speaker').disabled=audioSaving&&!preview;
 $('#audio-status').textContent=audioSaving?'Saving…':preview?'Playing selected voice…':'';
}
async function saveAudio(){
 if(audioSaving)return;
 audioSaving=true;renderPreview();
 for(const id of ['input-device','output-device','voice-name'])$('#'+id).disabled=true;
 try{
  state.settings=await call('audio_settings',{input_device:$('#input-device').value?Number($('#input-device').value):null,output_device:$('#output-device').value?Number($('#output-device').value):null,voice_name:$('#voice-name').value});
 }finally{audioSaving=false;for(const id of ['input-device','output-device','voice-name'])$('#'+id).disabled=false;renderPreview();}
}
for(const id of ['input-device','output-device','voice-name'])$('#'+id).onchange=()=>saveAudio().catch(()=>{});
$('#test-speaker').onclick=async()=>{
 try{
  if(preview){await call('stop_speaker');return;}
  if(audioSaving)return;
  await saveAudio();
  preview=true;renderPreview();$('#error').hidden=true;
  await call('test_speaker');
 }catch{preview=false;renderPreview();}
};

const promptFields={'system_prompt':'system-prompt','voice_prompt':'voice-prompt','voice_max_sentences':'voice-max-sentences','voice_max_tokens':'voice-max-tokens','text_max_tokens':'text-max-tokens'};
function renderPrompts(settings){for(const [key,id] of Object.entries(promptFields))$('#'+id).value=settings[key];}
$('#prompt-form').onsubmit=async e=>{e.preventDefault();const values={};for(const [key,id] of Object.entries(promptFields))values[key]=key.endsWith('prompt')?$('#'+id).value:Number($('#'+id).value);try{state.settings=await call('prompt_settings',values);$('#prompts-saved').textContent='Saved';}catch{}};
$('#reset-prompts').onclick=()=>{renderPrompts(state.promptDefaults);$('#prompts-saved').textContent='Defaults restored. Save to apply.';};

document.querySelectorAll('[data-settings]').forEach(button=>button.onclick=()=>{
 document.querySelectorAll('[data-settings]').forEach(tab=>tab.setAttribute('aria-selected',String(tab===button)));
 document.querySelectorAll('[data-settings-view]').forEach(view=>view.hidden=view.dataset.settingsView!==button.dataset.settings);
});

$('#panel-toggle').onclick=()=>{const hidden=document.body.classList.toggle('voice-panel-hidden');$('#panel-toggle').setAttribute('aria-expanded',String(!hidden));};

$('#situation-find').onclick=async()=>{try{state.profile=await call('save_profile',Object.fromEntries(new FormData($('#profile-form'))));route=null;renderAtlas();page('atlas');$('#location-picker').open=true;const parts=await call('location_parts',{text:state.profile.location_text||''});$('#city-search').value=parts.city;$('#landmark-search').value=parts.street;$('#city-search').focus();}catch{}};

$('#paste-document').onclick=()=>{$('#note-form').hidden=false;$('#note-form input').focus();};
$('#cancel-note').onclick=()=>{$('#note-form').hidden=true;};
$('#note-form').onsubmit=async e=>{e.preventDefault();try{await call('import_note',Object.fromEntries(new FormData(e.target)));e.target.reset();e.target.hidden=true;await refresh();filterDocs();}catch{}};
let referenceSearch=0,referenceTimer;
function filterDocs(){
 const q=$('#docs-search').value.trim().toLowerCase(),sequence=++referenceSearch;
 for(const d of document.querySelectorAll('#guides .doc-entry,#documents .doc-entry,.recovery-entry'))d.hidden=!!q&&!d.textContent.toLowerCase().includes(q);
 clearTimeout(referenceTimer);$('#references').hidden=!!q;$('#reference-results').hidden=!q;
 if(!q){$('#reference-results').replaceChildren();return;}
 referenceTimer=setTimeout(async()=>{
  try{const results=await call('reference_search',{query:q});if(sequence!==referenceSearch)return;
   const nodes=results.map(ref=>{const b=document.createElement('button');b.className='reference-result';b.textContent=ref.title+' · '+ref.heading;b.onclick=()=>openReference(ref.id,ref.section).catch(error);return b;});
   if(!nodes.length){const p=document.createElement('p');p.textContent='No matching field references.';nodes.push(p);}
   $('#reference-results').replaceChildren(...nodes);
  }catch{}
 },180);
}
$('#docs-search').oninput=filterDocs;
