const $=s=>document.querySelector(s);
const SVG='http://www.w3.org/2000/svg';
let state={},busy=false,voice=false,route=null,searchTimer,pendingMethod=null,remoteOperation=null,pendingSetup=false,setupStarting=false,remoteSetup=false;
let chatFinished=false,voiceStarting=false,preview=false,audioSaving=false,pageSequence=0,lastQuestion='',serviceDown=false,mapClickMode=false,toastTimer;
let voicePhase='Voice off';
const exclusiveMethods=new Set(['chat','route','clear','start_model','stop_model','download_voice','download_us_maps']);
const operationLabels={setup_run:'Preparing JARVISS',download_voice:'Preparing offline voice',download_us_maps:'Preparing US offline maps',start_model:'Loading local model',stop_model:'Stopping model',chat:'Thinking',route:'Calculating walking directions',clear:'Clearing conversation'};
const pageTitles={assistant:'Chat',atlas:'Maps',plan:'Plan',docs:'Docs',settings:'Settings',setup:'Set up',startup:'Starting','reference-reader':'Reader'};
const typing=el=>el&&(el.closest('input,textarea,select,[contenteditable]')||el.closest('dialog'));
function icon(name){const svg=document.createElementNS(SVG,'svg'),use=document.createElementNS(SVG,'use');svg.setAttribute('class','icon');svg.setAttribute('aria-hidden','true');use.setAttribute('href','#i-'+name);svg.append(use);return svg;}
function showToast(text){const t=$('#toast');t.textContent=text;t.classList.add('show');clearTimeout(toastTimer);toastTimer=setTimeout(()=>t.classList.remove('show'),2500);}
window.toast=showToast;
// Dates and times: one formatter each, so every page shows "Sep 17, 2026" and "14:32" the same way. Date-only strings are read as local dates.
const dateFormat=new Intl.DateTimeFormat(undefined,{dateStyle:'medium'}),timeFormat=new Intl.DateTimeFormat(undefined,{hour:'2-digit',minute:'2-digit',hourCycle:'h23'});
function parseDate(value){const s=String(value??'').trim();if(!s)return null;const m=/^(\d{4})-(\d{2})-(\d{2})$/.exec(s);const d=m?new Date(+m[1],+m[2]-1,+m[3]):new Date(s);return Number.isNaN(d.getTime())?null:d;}
function formatDate(value,fallback='unknown date'){const d=parseDate(value);return d?dateFormat.format(d):fallback;}
function formatTime(value){const d=parseDate(value);return d?timeFormat.format(d):'';}
Object.assign(window,{parseDate,formatDate,formatTime});
// A check-icon row that replaces a button once its work is done ("Installed"), created next to the button on first use.
function readyRow(id,text){let el=document.getElementById(id);if(!el){el=document.createElement('p');el.id=id;el.className='ready-row';el.append(icon('check'),document.createTextNode(text));}return el;}
// Disabling the focused control drops focus to <body>; put it back on the control, or on the page title when the control went away.
async function guardFocus(button,fn){button.disabled=true;try{return await fn();}finally{button.disabled=false;if(document.activeElement===document.body)(button.isConnected&&!button.hidden&&button.offsetParent?button:$('.page.visible .page-title'))?.focus({preventScroll:true});}}
function notice(el,text,{kind='danger',action,actions=[],onDismiss}={}){
 el.className='notice '+kind;el.hidden=!text;el.replaceChildren();if(!text)return;
 const span=document.createElement('span');span.className='notice-text';span.textContent=text;el.append(span);
 for(const item of [...actions,action].filter(Boolean)){const b=document.createElement('button');b.className='compact'+(item.primary?' primary':'');b.textContent=item.label;b.onclick=()=>guardFocus(b,item.run);el.append(b);}
 const close=document.createElement('button');close.className='quiet compact dismiss';close.setAttribute('aria-label','Dismiss');close.append(icon('close'));close.onclick=()=>{el.hidden=true;onDismiss?.();};el.append(close);
}
// The two-step pattern: "Question? Yes / No" takes the button's place until Yes finishes or No (or Escape) restores it.
// The button itself only hides, so renderOperation() can still find it by id while the question is open.
function confirmInline(button,question,run){
 if(button.hidden)return;
 const box=document.createElement('span');box.className='confirm';box.setAttribute('role','group');box.setAttribute('aria-label',question);
 const text=document.createElement('span');text.textContent=question;
 const yes=document.createElement('button');yes.className='compact';yes.textContent='Yes';
 const no=document.createElement('button');no.className='quiet compact';no.textContent='No';
 const restore=focus=>{if(!box.isConnected)return;box.remove();button.hidden=false;if(focus)button.focus();};
 yes.onclick=async()=>{yes.disabled=no.disabled=true;try{await run();}finally{restore(false);if(document.activeElement===document.body)(button.offsetParent?button:$('.page.visible .page-title'))?.focus({preventScroll:true});}};
 no.onclick=()=>restore(true);
 box.onkeydown=e=>{if(e.key==='Escape'){e.stopPropagation();restore(true);}};
 box.append(text,yes,no);button.after(box);button.hidden=true;yes.focus();
}
function renderOperation(){
 const method=pendingMethod||remoteOperation?.method||(setupStarting?'setup_run':null);
 const label=remoteOperation?.label||operationLabels[method];
 const active=!!(method||remoteOperation);
 const setupRunning=pendingSetup||remoteSetup;
 window.renderSetupOperation?.(active,method,setupRunning);
 $('#view-setup').hidden=!setupRunning&&!['paused','failed','model_ready'].includes(state.setup?.status);
 const noModel=!state.settings?.model;
 $('#download-model').disabled=false;
 $('#download-model').textContent=setupRunning?'View setup':noModel?'Download a model':'Change model'; // without a model, downloading one is the primary action
 $('#download-model').classList.toggle('primary',noModel&&!setupRunning);
 for(const id of ['download-voice','download-us-maps','clear'])$('#'+id).disabled=active||(setupRunning&&id!=='clear');
 $('#choose-model').disabled=active||setupRunning;
 $('#start-model').disabled=active||setupRunning||noModel||state.modelAvailable===false;
 $('#start-model').hidden=!!state.ready||noModel;$('#stop-model').hidden=!state.ready;$('#stop-model').disabled=active||setupRunning;
 $('#send').disabled=active||busy;
 $('#voice-toggle').disabled=voiceStarting||(!voice&&(active||!state.ready));
 $('#voice-toggle').classList.toggle('primary',!!state.ready);
 const waiting=method==='chat'&&!chatFinished;
 $('#messages').setAttribute('aria-busy',String(waiting));
 if(waiting)document.body.classList.add('has-history');
 $('#response-wait').hidden=!waiting;
 if(waiting)$('#messages').scrollTop=$('#messages').scrollHeight;
 // The pill reads "Model off" (idle dot) until the model runs; a ready model is the dot alone, with "Ready" kept for assistive tech.
 const dotOnly=!serviceDown&&!label&&!!state.ready;
 $('#status').textContent=serviceDown?'Local service stopped':label||(state.ready?'Ready':'Model off');
 $('#status').classList.toggle('visually-hidden',dotOnly);
 const pill=$('.status-pill');pill.classList.toggle('dot-only',dotOnly);pill.title=dotOnly?'Ready':'';
 $('#status-dot').className='status-dot '+(serviceDown?'error':active||setupRunning?'working':state.ready?'ok':'idle');
 renderVoiceActivity(waiting);
 $('#model-setup-status').textContent=active?`${label}. ${remoteOperation?.progress||'Please wait for this operation to finish.'}`:state.ready?'Running on this computer.':state.settings?.model?state.modelAvailable===false?'The model file is missing. Open Setup to download it again, or choose a model file.':'Downloaded. Not running yet.':'No model yet. Download one to start chatting.';
 if(remoteOperation?.progress){$('#progress').textContent=remoteOperation.progress;if(remoteOperation.method==='download_us_maps')$('#map-progress').textContent=remoteOperation.progress;}
 renderMapPause();renderSkipped();
}
// A basemap extract cannot resume, so a pause during that phase asks once before discarding it.
function pauseButton(button,{onPause,onPaused}={}){
 button.onclick=async()=>{
  if(button.dataset.phase==='basemap'&&!button.dataset.confirm){button.dataset.confirm='1';button.textContent='Restart map later? Pause anyway';return;}
  button.disabled=true;delete button.dataset.confirm;button.textContent='Pausing…';button.dataset.pausing='1';onPause?.();
  try{await call('setup_pause');}catch{}
 };
 return (active,basemap)=>{ // Reset when the operation ends or the extract phase moves on, never mid-pause.
  button.hidden=!active;button.dataset.phase=basemap?'basemap':'';
  if(!active&&button.dataset.pausing){delete button.dataset.pausing;onPaused?.();if(document.activeElement===document.body)$('.page.visible .page-title')?.focus({preventScroll:true});}
  if(!active||(button.dataset.confirm&&!basemap)){button.disabled=false;button.textContent='Pause';delete button.dataset.confirm;}
 };
}
const syncMapPause=pauseButton($('#map-pause'),{onPaused:()=>{$('#map-progress').textContent='Download paused.';}});
function renderMapPause(){syncMapPause((pendingMethod||remoteOperation?.method)==='download_us_maps',/^US map ·/.test($('#map-progress').textContent));}
function renderVoiceActivity(waiting=(pendingMethod||remoteOperation?.method)==='chat'&&!chatFinished){
 const generating=voice&&waiting&&!['Preparing speech','Speaking'].includes(voicePhase);
 $('#voice-badge').textContent=generating?'Thinking…':voicePhase;
 $('#voice-badge').classList.toggle('generating',generating);
 $('#orb').classList.toggle('active',generating||['Starting voice','Preparing speech','Listening','Speaking'].includes(voicePhase));
}
function mapFullscreen(enabled){
 document.body.classList.toggle('map-fullscreen',enabled);
 $('#map-fullscreen').textContent=enabled?'Exit full screen':'Full screen';
 $('#map-fullscreen').setAttribute('aria-pressed',String(enabled));
 requestAnimationFrame(()=>window.offlineAtlas?.resize());
}
$('#map-fullscreen').onclick=()=>{const enabled=!document.body.classList.contains('map-fullscreen');return guardFocus($('#map-fullscreen'),async()=>{try{await window.jarviss.mapFullscreen(enabled);mapFullscreen(enabled);}catch(e){error(e);}});};
const errorText=e=>(e.message||String(e)).replace(/^Error invoking remote method '[^']+': (?:Error: )?/,'');
// A model problem offers the two ways out: start the downloaded model right here, or open Settings → Model. Only failures are 'danger'.
function composerNotice(text,kind='warn'){
 const el=$('#composer-notice');el.setAttribute('role',kind==='danger'?'alert':'status');
 const actions=[];
 if(/model/i.test(text)){
  if(!state.ready&&state.settings?.model&&state.modelAvailable!==false)actions.push({label:'Start model',primary:true,run:async()=>{try{await startModel();el.hidden=true;if(document.activeElement===document.body)$('#question').focus();}catch{}}});
  actions.push({label:'Open Settings',run:()=>{page('settings');settingsTabs.select('model');}});
 }
 notice(el,text,{kind,actions});
}
function error(e,method){
 const text=errorText(e);
 if($('#startup').classList.contains('visible')){
  $('#error').hidden=true;
  $('#startup-message').textContent=text==='Operation timed out. Check Settings.'?'Connecting took too long. Try again.':text;
  $('#startup-retry').hidden=false;
  return;
 }
 if($('#setup').classList.contains('visible'))$('#setup-warning').textContent=text;
 else if(method==='chat'||method==='clear')composerNotice(text,'danger');
 else notice($('#error'),text);
 renderOperation();
}
async function call(method,args){
 const setup=method==='setup_run',exclusive=exclusiveMethods.has(method);
 if(setup&& (pendingSetup||remoteSetup))throw new Error('Setup is already running.');
 if((exclusive||setup)&&(pendingMethod||remoteOperation||setupStarting)){
  const problem=new Error((remoteOperation?.label||operationLabels[pendingMethod]||'Another operation is running')+'. Wait for it to finish.');error(problem,method);throw problem;
 }
 if(setup){pendingSetup=true;setupStarting=true;renderOperation();}
 if(exclusive){pendingMethod=method;if(method==='chat'){chatFinished=false;$('#composer-notice').hidden=true;}else $('#error').hidden=true;renderOperation();}
 try{return await window.jarviss.command(method,args);}catch(e){error(e,method);throw e;}
 finally{if(setup){pendingSetup=false;setupStarting=false;}if(exclusive)pendingMethod=null;renderOperation();}
}
function page(name){
 pageSequence++;
 if(name!=='atlas'&&document.body.classList.contains('map-fullscreen')){window.jarviss.mapFullscreen(false).catch(error);mapFullscreen(false);}
 document.body.classList.toggle('setup-screen',name==='setup'||name==='startup');document.querySelector('aside').inert=document.body.classList.contains('setup-screen');/* UI hook: the rail stays visible but inert during startup/setup */
 document.querySelectorAll('.page').forEach(el=>el.classList.toggle('visible',el.id===name));
 const rail=name==='reference-reader'?'docs':name;
 document.querySelectorAll('[data-page]').forEach(el=>{const on=el.dataset.page===rail;el.classList.toggle('selected',on);if(on)el.setAttribute('aria-current','page');else el.removeAttribute('aria-current');});
 const title=pageTitles[name]?`${pageTitles[name]} · JARVISS`:'JARVISS';document.title=title;window.jarviss.setTitle(title).catch(()=>{});
 if(name==='atlas')window.offlineAtlas?.resize();
 if(name!=='reference-reader')$('#'+name+' .page-title')?.focus({preventScroll:true}); // the reader focuses its own title once loaded
}
document.querySelectorAll('[data-page]').forEach(el=>el.onclick=()=>page(el.dataset.page));
function copyText(text,label){return navigator.clipboard.writeText(text).then(()=>showToast(label),()=>showToast('Could not copy'));}
function actionButton(name,label,run){const b=document.createElement('button');b.className='quiet compact '+name;b.append(icon(name),label);b.onclick=run;return b;}
function message(role,text,references=[],{truncated=false}={}){
 const node=document.createElement('div');node.className='message '+role;node.setAttribute('role','group');
 const label=document.createElement('span');label.className='speaker';label.textContent=role==='user'?'You: ':'JARVISS: ';
 node.append(label,role==='assistant'&&window.documentBody?window.documentBody(text):document.createTextNode(text));
 if(references.length){const sources=document.createElement('div');sources.className='answer-references';const heading=document.createElement('small');heading.className='meta';heading.textContent='Reference passages';sources.append(heading);for(const ref of references){const button=document.createElement('button');button.className='ref-row';button.append(icon('docs'),document.createTextNode(ref.title+' · '+ref.heading));button.onclick=()=>openReference(ref.id,ref.section,ref.heading).catch(error);sources.append(button);}node.append(sources);}
 if(truncated){const cut=document.createElement('p');cut.className='cut-short';cut.append(icon('warning'),'Reply was cut short');node.append(cut);}
 $('#messages').querySelectorAll('.message-actions .retry').forEach(b=>b.remove()); // Retry only ever re-sends the latest question
 if(role==='assistant'){const actions=document.createElement('div');actions.className='message-actions';actions.append(actionButton('copy','Copy',()=>copyText(text,'Copied')),actionButton('retry','Retry',()=>send(lastQuestion).catch(()=>{})));node.append(actions);}
 else lastQuestion=text;
 $('#messages').append(node);$('#messages').scrollTop=$('#messages').scrollHeight;document.body.classList.add('has-history');
}
function renderQuickPrompts(){
 const box=$('#quick-actions');box.replaceChildren();
 for(const {label,prompt} of (state.quick_prompts||[]).slice(0,6)){ // two rows of three, never an orphan
  const b=document.createElement('button');b.textContent=label;
  // A prompt ending in ":" wants the person's own details; anything else is a complete question.
  b.onclick=()=>{if(/:\s*$/.test(prompt)){const q=$('#question');q.value=prompt.trimEnd()+' ';q.focus();q.setSelectionRange(q.value.length,q.value.length);}else send(prompt).catch(()=>{});};
  box.append(b);
 }
}
function renderSituation(initial=false){
 const p=state.profile||{};
 for(const [id,value] of [['situation-summary-location',p.position_name||p.location_text],['situation-summary-text',p.situation],['situation-summary-supplies',p.supplies]]){const dd=$('#'+id);dd.textContent=value||'Not set';dd.classList.toggle('unset',!value);}
 if(initial||!$('#situation-editor').open)for(const k of ['situation','supplies','location_text'])$('#profile-form').elements[k].value=p[k]??'';
 const located=p.lat!==''&&p.lat!=null&&p.lon!==''&&p.lon!=null;
 $('#situation-location-status').textContent=located?'Position confirmed on map':'Position not confirmed';
}
function renderSkipped(){const mapsReady=!!(state.basemap&&state.usRouting?.ready);$('#setup-skipped').hidden=!(state.setup?.skipped&&!mapsReady&&!remoteSetup);}
function renderModel(){
 const s=state.settings||{};
 const name=s.model?window.setupModelName?.(s.model_id)||s.model.split(/[\\/]/).pop():'';
 $('#model-name').textContent=name||'No model selected';
 if(s.model_id&&!window.setupModelName?.(s.model_id)&&!renderModel.asked){renderModel.asked=true;window.ensureSetupPlan?.().then(renderModel).catch(()=>{});}
 const layers=s.gpu_layers==='auto'||s.gpu_layers==null?'':String(s.gpu_layers);
 if(layers&&![...$('#gpu').options].some(o=>o.value===layers))$('#gpu').add(new Option(`${layers} layers`,layers));
 $('#gpu').value=layers;
}
function renderState(initial=false){
 if(Object.hasOwn(state,'operation'))remoteOperation=state.operation;remoteSetup=!!state.setupRunning;renderOperation();
 renderModel();$('#voice-ready').textContent=state.voiceReady?'Voice pack installed':'Voice pack not installed';renderVoicePack();
 if(initial){renderPrompts(state.settings);for(const item of state.history||[])message(item.role,item.content,item.references,{truncated:!!item.truncated});}
 renderQuickPrompts();renderSituation(initial);
 window.renderDocuments?.(state); // Docs page lives in references.js
 renderAtlas();window.renderPlanner?.();
}
async function refresh(){state=await call('state');route=state.route||null;renderState();}
async function send(text){if(busy||pendingMethod||remoteOperation||setupStarting)return;text=(text||'').trim();if(!text)return;busy=true;$('#send').disabled=true;$('#composer-notice').hidden=true;$('#question').value='';message('user',text);try{await call('chat',{text});}finally{busy=false;renderOperation();if(document.activeElement===document.body)$('#question').focus();}}
$('#composer').onsubmit=e=>{e.preventDefault();send($('#question').value).catch(()=>{});};
$('#question').onkeydown=e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();$('#composer').requestSubmit();}};
$('#profile-form').onsubmit=async e=>{e.preventDefault();const button=e.target.querySelector('button.primary');await guardFocus(button,async()=>{try{state.profile=await call('save_profile',Object.fromEntries(new FormData(e.target)));route=null;renderState();$('#situation-editor').open=false;$('#situation-edit').focus();showToast('Situation saved');}catch{}});};
$('#voice-toggle').onclick=async()=>{const button=$('#voice-toggle');if(!voice&&!state.voiceReady){voicePackDismissed=false;renderVoicePack();}voiceStarting=true;button.disabled=true;button.textContent=voice?'Stopping…':'Starting voice…';$('#error').hidden=true;try{const result=await call('voice',{enabled:!voice});voice=result.enabled;}catch{voice=false;}finally{voiceStarting=false;button.textContent=voice?'Stop voice mode':'Start voice mode';renderOperation();if(document.activeElement===document.body)button.focus();}};
$('#voice-pack-setup').onclick=()=>window.openSetup();
// The missing-pack note shows once per session; pressing Start voice without the pack brings it back.
let voicePackDismissed=false;
function renderVoicePack(){$('#voice-pack-note').hidden=!!state.voiceReady||voicePackDismissed;}
$('#voice-pack-dismiss').onclick=()=>{voicePackDismissed=true;renderVoicePack();$('#voice-toggle').focus();};
$('#clear').onclick=()=>confirmInline($('#clear'),'Clear the conversation?',async()=>{try{await call('clear');$('#messages').replaceChildren();document.body.classList.remove('has-history');lastQuestion='';$('#question').focus();}catch{}});
async function startModel(){await call('start_model',{layers:$('#gpu').value===''?'auto':Number($('#gpu').value),path:state.settings?.model});await refresh();}
$('#start-model').onclick=()=>guardFocus($('#start-model'),async()=>{try{await startModel();}catch{}});
$('#stop-model').onclick=()=>guardFocus($('#stop-model'),async()=>{try{await call('stop_model',{});state.ready=false;renderOperation();}catch{}});
$('#gpu').onchange=async()=>{if(!state.ready||pendingMethod||remoteOperation||remoteSetup)return;try{await call('start_model',{layers:$('#gpu').value===''?'auto':Number($('#gpu').value),path:state.settings?.model});await refresh();showToast('Model restarted');}catch{}};
$('#choose-model').onclick=()=>guardFocus($('#choose-model'),async()=>{try{const path=await window.jarviss.pick('model');if(path){state.settings.model=path;state.settings.model_id=null;state.modelAvailable=true;renderModel();renderOperation();}}catch(e){error(e);}});
const percentOf=text=>{const m=/(\d+(?:\.\d+)?)%/.exec(text||'');return m?Math.min(1,Number(m[1])/100):null;};
for(const [id,method] of [['download-voice','download_voice'],['download-us-maps','download_us_maps']])$('#'+id).onclick=()=>guardFocus($('#'+id),async()=>{
 try{await call(method,{});$('#progress').textContent='Download complete.';if(method==='download_us_maps'){$('#map-progress').textContent='US map and walking directions are ready offline.';window.jarviss.notify('JARVISS','US maps are ready offline.').catch(()=>{});}await refresh();}
 catch(e){if(method==='download_us_maps'){$('#map-progress').textContent=errorText(e);window.jarviss.notify('JARVISS','The US map download stopped: '+errorText(e)).catch(()=>{});}}
 finally{window.jarviss.setProgress(-1).catch(()=>{});renderOperation();}
});
$('#import-document').onclick=()=>guardFocus($('#import-document'),async()=>{try{await window.jarviss.pick('document');await refresh();}catch(e){error(e);}});
$('#map-search').oninput=()=>{clearTimeout(searchTimer);searchTimer=setTimeout(places,180);};
let searchSequence=0,locationSequence=0,locationCenter=null,placesKey=null,lastResults=[];
// Every distance the renderer shows goes through here so the Units setting applies everywhere at once.
function distance(m){
 if(state.settings?.units==='metric')return m<1000?`${Math.round(m)} m`:`${m<10000?(m/1000).toFixed(1):Math.round(m/1000)} km`;
 const miles=m/1609.344;return miles<.1?`${Math.round(m*3.28084)} ft`:`${miles<10?miles.toFixed(1):Math.round(miles)} miles`;
}
window.formatDistance=distance; // map popups (map-view.mjs) use the same units
// OSM features without a name arrive as "Unnamed swimming pool"; the title shows the kind and the meta line says "Unnamed".
function placeName(name){const m=/^Unnamed\s+(.+)$/i.exec(String(name||'').trim());return m?{label:m[1][0].toUpperCase()+m[1].slice(1),unnamed:true}:{label:name||'Selected point',unnamed:false};}
function placeTitle(tag,name){const el=document.createElement(tag),{label,unnamed}=placeName(name);el.textContent=label;if(unnamed)el.dataset.unnamed='1';return el;}
Object.assign(window,{placeTitle,placeName});
function renderRoute(){
 const container=$('#route-info');container.replaceChildren();
 if(route){
  const heading=document.createElement('strong');heading.textContent=`Walk ${route.destination_note?'near':'to'} ${route.destination||'destination'} · ${distance(route.distance_m)}`;container.append(heading);
  if(route.destination_note){const note=document.createElement('p');note.textContent=route.destination_note;container.append(note);}
  const steps=route.steps||[];let index=0;
  if(steps.length){
   const current=document.createElement('p'),controls=document.createElement('div'),back=document.createElement('button'),next=document.createElement('button');back.textContent='Back';next.textContent='Next';controls.className='route-step-controls';controls.append(back,next);
   const show=()=>{current.textContent=`${index+1} of ${steps.length} · ${steps[index].instruction}`;back.disabled=index===0;next.disabled=index===steps.length-1;if(document.activeElement===document.body)(index===0?next:back).focus();};
   back.onclick=()=>{index--;show();if(steps[index].point)window.offlineAtlas?.focus(steps[index].point);};next.onclick=()=>{index++;show();if(steps[index].point)window.offlineAtlas?.focus(steps[index].point);};show();container.append(current,controls);
   const all=document.createElement('details'),summary=document.createElement('summary'),list=document.createElement('p');summary.textContent='All directions';list.textContent=steps.map((s,i)=>`${i+1}. ${s.instruction}`).join('\n');all.append(summary,list);container.append(all);
  }
  if(route.start_gap_m||route.end_gap_m){const gaps=document.createElement('small');gaps.textContent=`Unmapped connections: ${distance(route.start_gap_m||0)} at the start; ${distance(route.end_gap_m||0)} at the end. Check these on foot.`;container.append(gaps);}
 }
 window.offlineAtlas?.route(route);
}
$('#clear-route').onclick=()=>{route=null;renderRoute();showToast('Route cleared');$('#map-search').focus();};
$('#copy-route').onclick=()=>{if(!route)return;const lines=[`Walk to ${route.destination||'destination'} · ${distance(route.distance_m)}`,...(route.steps||[]).map((s,i)=>`${i+1}. ${s.instruction}`)];copyText(lines.join('\n'),'Directions copied');};
function renderAtlas(){
 window.offlineAtlas?.update(state,route);
 const p=state.profile;
 const located=p?.lat!==''&&p?.lat!=null&&p?.lon!==''&&p?.lon!=null;
 $('#map-empty').hidden=!!(state.basemap?.enabled||state.map);
 const reach=state.settings?.units==='metric'?'5 km':'3 mi';
 $('#map-caption').textContent=state.basemap?.enabled?`Map data from ${formatDate(state.basemap.osm_timestamp)} · Searches cover ${reach} around you`:state.map?`${state.map.label||'Prepared area'} · Map data from ${formatDate(state.map.osm_timestamp)}`:'Download US offline maps to begin.';
 $('#map-position-note').textContent=located?`Your position: ${p.position_name||'Confirmed on map'}`:'Position not set. Use “Set my position” to choose it.';
 const installed=!!(state.basemap && state.usRouting?.ready);
 $('#us-map-status').textContent=installed?'US map and walking directions are ready offline.':state.basemap?'US map installed. Download walking directions once for full US coverage.':'Download the US map and walking directions once (about 23 GB total).';
 const download=$('#download-us-maps'),ready=readyRow('us-map-ready','Installed');if(!ready.isConnected)download.before(ready);
 download.textContent=state.basemap?'Download US walking directions':'Download US offline maps';
 download.hidden=installed;ready.hidden=!installed; // done work is a check row, never a disabled primary
 download.disabled=!!(pendingMethod||remoteOperation||pendingSetup||remoteSetup);
 const available=!!(state.basemap||state.map);
 for(const selector of ['#city-search-form button','#landmark-search-form button','#map-search'])$(selector).disabled=!available;
 $('#map-view-setup').hidden=available;
 if(!available)$('#location-search-status').textContent='Map not ready. Open setup to download it or check progress.';
 if(state.mapError)$('#map-local-status').textContent=state.mapError;
 renderSituation();renderRoute();places();
}
async function places(){
 const sequence=++searchSequence,list=$('#places');
 const empty=text=>{placesKey=null;lastResults=[];placesEmpty(text);$('#map-result-count').textContent='';$('#map-show-all').hidden=true;};
 if(!state.basemap&&!state.map)return empty('Map not ready. Open setup to download it or check progress.');
 if(!state.profile||state.profile.lat===''||state.profile.lat==null)return empty('Set your position to search nearby.');
 // Background refreshes must not re-query and replace result ids a user is about to route to.
 const key=JSON.stringify([$('#map-search').value,state.profile.lat,state.profile.lon,state.basemap?.path,state.basemap?.enabled,state.map?.label,state.settings?.units]);
 if(key===placesKey)return;placesKey=key;
 // Typing refines the list in place: the previous results stay (dimmed via aria-busy) until the new ones arrive.
 if(list.querySelector('.place-card'))list.setAttribute('aria-busy','true');else placesEmpty('Searching local map…');
 try{
  const rows=await call('nearest',{query:$('#map-search').value});if(sequence!==searchSequence)return;
  lastResults=rows;window.offlineAtlas?.results(rows);list.replaceChildren();list.removeAttribute('aria-busy');
  $('#map-result-count').textContent=rows.length?`${rows.length} place${rows.length===1?'':'s'}`:'';$('#map-show-all').hidden=!rows.length;
  if(!rows.length){placesEmpty('No matching records in the searched area. Try another name or resource.');return;}
  for(const p of rows){
   const item=document.createElement('div');item.className='place-card';
   const title=placeTitle('strong',p.name);
   const info=document.createElement('small');info.className='meta';info.textContent=`${title.dataset.unnamed?'Unnamed · ':''}${p.kind} · ${distance(p.distance_m)}`;
   const actions=document.createElement('div');actions.className='place-actions';
   const show=document.createElement('button');show.textContent='Show';show.onclick=()=>window.offlineAtlas?.focus(p.point);
   const walk=document.createElement('button');walk.textContent='Directions';walk.onclick=()=>guardFocus(walk,async()=>{route=null;renderRoute();try{route=await call('route',{id:p.id});renderRoute();}catch{route=null;renderRoute();}});
   actions.append(show,walk);item.append(title,info,actions);list.append(item);
  }
  const note=document.createElement('p');note.className='meta places-footnote';note.textContent='Distances are straight-line';list.append(note); // said once, not on every card
 }catch{if(sequence===searchSequence){placesKey=null;placesEmpty('Nearby search did not finish. Check the message above.');}}
}
function placesEmpty(text){const box=document.createElement('div');box.className='empty';const p=document.createElement('p');p.textContent=text;box.append(p);$('#places').replaceChildren(box);$('#places').removeAttribute('aria-busy');}
$('#map-show-all').onclick=()=>{
 const map=window.jarvisDetailMap;if(!map||!lastResults.length)return;
 const lats=lastResults.map(p=>p.point[0]),lngs=lastResults.map(p=>p.point[1]),here=state.profile;
 if(here?.lat!=null&&here.lat!==''){lats.push(Number(here.lat));lngs.push(Number(here.lon));}
 map.fitBounds([[Math.min(...lngs),Math.min(...lats)],[Math.max(...lngs),Math.max(...lats)]],{padding:65,maxZoom:16,duration:250});
};
const closeMenu=(menu,focus)=>{menu.open=false;if(focus)menu.querySelector('summary').focus();};
for(const menu of document.querySelectorAll('details.menu')){
 menu.addEventListener('toggle',()=>{if(menu.open)menu.querySelector('[role=menuitem]')?.focus();});
 menu.addEventListener('keydown',e=>{
  const items=[...menu.querySelectorAll('[role=menuitem]')],i=items.indexOf(document.activeElement);
  if(e.key==='ArrowDown'||e.key==='ArrowUp'){e.preventDefault();if(!menu.open){menu.open=true;return;}items[(i+(e.key==='ArrowDown'?1:-1)+items.length)%items.length]?.focus();}
  if(e.key==='Escape'&&menu.open){e.preventDefault();e.stopPropagation();closeMenu(menu,true);}
 });
 menu.addEventListener('focusout',e=>{if(!menu.contains(e.relatedTarget))menu.open=false;});
 menu.querySelectorAll('[role=menuitem]').forEach(item=>item.addEventListener('click',()=>closeMenu(menu,false)));
}
document.addEventListener('click',e=>{for(const menu of document.querySelectorAll('details.menu[open]'))if(!menu.contains(e.target))menu.open=false;});
// The picker is hidden until a user action asks for it (Set my position → Search a place, or Situation → Find on map); it never reopens itself.
function showPicker(open){const picker=$('#location-picker');picker.hidden=!open;if(open)$('#city-search').focus();}
$('#find-location').onclick=()=>showPicker(true);
$('#location-picker-close').onclick=()=>{showPicker(false);$('#set-position-menu summary').focus();};
$('#location-picker').addEventListener('keydown',e=>{if(e.key==='Escape'&&!e.target.closest('.confirm')){e.preventDefault();e.stopPropagation();$('#location-picker-close').click();}});
$('#locate-this-view').onclick=()=>{locationCenter=window.offlineAtlas?.viewCenter();$('#location-area-name').textContent=locationCenter?'Searching the area currently shown · not your saved position':'Choose a map first.';$('#landmark-search').focus();};
async function searchLocation(near){
 if(!state.basemap&&!state.map){$('#location-search-status').textContent='Map not ready. Open setup to download it or check progress.';return;}
 const query=$(near?'#landmark-search':'#city-search').value.trim();
 if(query.length<2){$('#location-search-status').textContent='Enter at least two letters.';return;}
 if(near&&!locationCenter){$('#location-search-status').textContent='Find an area first, or pan the map and choose “Search the area shown”.';return;}
 const sequence=++locationSequence;$('#location-search-status').textContent='Searching your local map…';
 try{
  const rows=await call('search_locations',{query,...(near?{near:locationCenter}:{})});if(sequence!==locationSequence)return;
  $('#location-results').replaceChildren();
  $('#location-search-status').textContent=rows.length?near?'Select a result to inspect it, then choose “Set as my position” only if it matches where you are.':'Select an area to explore. This does not set your position.':'No matching labels in this search. Try a nearby larger town, a shorter road name, or pan the map to a familiar area.';
  for(const place of rows){
   const button=document.createElement('button');const name=document.createElement('strong');name.textContent=place.name;
   const detail=document.createElement('small');detail.textContent=near?`${place.kind} · inspect on map`:`${place.kind}${place.state?' · '+place.state:''} · ${place.population?Number(place.population).toLocaleString()+' recorded population · ':''}preview region on map`;
   button.append(name,detail);
   button.onclick=()=>{
    if(near){window.offlineAtlas?.preview(place);showPicker(false);}
    else{locationCenter=place.point;$('#location-area-name').textContent=`Exploring ${place.name} · your position is not changed`;window.offlineAtlas?.explore(place.point,['state','province','country'].includes(place.kind)?6:12);$('#landmark-search').focus();}
   };
   $('#location-results').append(button);
  }
 }catch{}
}
$('#city-search-form').onsubmit=e=>{e.preventDefault();searchLocation(false);};
$('#landmark-search-form').onsubmit=e=>{e.preventDefault();searchLocation(true);};
async function setPosition(point,name){
 route=null;renderRoute();
 state.profile=await call('set_map_position',{lat:point[0],lon:point[1],name});
 showPicker(false);renderAtlas();showToast('Position set');
}
// Keyboard path for "click the map": the map centre stands in for the pointer, after one inline confirmation.
$('#map-use-centre').onclick=()=>{
 const point=window.offlineAtlas?.centerPoint?.();
 if(!point){notice($('#error'),'Download US offline maps first.');return;}
 const host=$('#map-confirm');host.hidden=false;host.replaceChildren();
 const text=document.createElement('span');text.textContent='Set position here?';
 const yes=document.createElement('button');yes.className='compact';yes.textContent='Yes';
 const no=document.createElement('button');no.className='quiet compact';no.textContent='No';
 const done=()=>{host.hidden=true;host.replaceChildren();if(document.activeElement===document.body)$('#set-position-menu summary').focus();};
 yes.onclick=async()=>{yes.disabled=no.disabled=true;try{await setPosition(point,'Map centre');}catch{}finally{done();}};
 no.onclick=done;host.onkeydown=e=>{if(e.key==='Escape'){e.stopPropagation();done();}};
 host.append(text,yes,no);yes.focus();
};
function cancelMapClick(){mapClickMode=false;window.offlineAtlas?.mode(null);$('#map-click-cancel').hidden=true;if(document.activeElement===document.body)$('#set-position-menu summary').focus();}
$('#set-position').onclick=()=>{if(!state.basemap?.enabled){notice($('#error'),'Download US offline maps first.');return;}mapClickMode=true;window.offlineAtlas?.mode('position');$('#map-click-cancel').hidden=false;$('#map-click-cancel').focus();};
$('#map-click-cancel').onclick=cancelMapClick;
window.addEventListener('atlas-point',async({detail})=>{
 mapClickMode=false;$('#map-click-cancel').hidden=true;
 route=null;renderRoute();
 try{
  if(detail.action==='position')await setPosition(detail.point,detail.name);
  else{route=await call('route',{point:detail.point,name:detail.name});renderRoute();}
 }catch{}
});
$('#choose-basemap').onclick=()=>guardFocus($('#choose-basemap'),async()=>{try{const result=await window.jarviss.pick('basemap');if(result)await refresh();}catch(e){error(e);}});
$('#center-map').onclick=()=>window.offlineAtlas?.center();
let setupWasRunning=false,setupDownloads=null; // null = unknown (started before this renderer loaded); false = a check-only run
window.setupWillDownload=value=>{setupDownloads=!!value;};
window.jarviss.subscribe(({event,data})=>{
 window.jarvisState?.(event,data);
 if(event==='setup'){
  const milestone=data.model_ready&&!state.setup?.model_ready||data.mapReady&&!state.basemap;remoteSetup=!!data.running;state.setup=data;if(data.modelReady)state.ready=true;renderOperation();window.setupProgress?.(data.detail);$('#progress').textContent=data.detail||'';if(data.stage>=3)$('#map-progress').textContent=data.detail||'';
  window.jarviss.setProgress(data.running?(data.percent||0)/100:-1).catch(()=>{});
  // A run that had nothing to download ("Check setup") finishes in seconds; no OS notification for that.
  if(setupWasRunning&&!data.running&&setupDownloads!==false)window.jarviss.notify('JARVISS',{ready:'Setup finished. JARVISS is ready offline.',model_ready:'Chat is ready. US maps were not downloaded.',paused:'Setup paused.',failed:'Setup stopped: '+(data.error||'see Setup for details.')}[data.status]||'Setup finished.').catch(()=>{});
  if(!data.running)setupDownloads=null;
  setupWasRunning=!!data.running;
  if(!remoteSetup||milestone)refresh().then(()=>window.refreshSetup?.()).catch(()=>{});
 }
 if(event==='operation'){setupStarting=false;const completed=remoteOperation?.method;if(data?.method==='chat'&&completed!=='chat')chatFinished=false;remoteOperation=data;renderOperation();if(!data&&!pendingMethod&&(completed?.startsWith('download')||completed==='start_model'||completed==='setup_run')){refresh().catch(()=>{});if(completed==='setup_run')window.refreshSetup?.();}}
 if(event==='status'){if(data==='Ready'||data==='Model not started'){state.ready=data==='Ready';if(!state.ready&&voice){voice=false;$('#voice-toggle').textContent='Start voice mode';}}renderOperation();}
 if(event==='voice'){voicePhase=data;if(data==='Voice off'){voice=false;$('#voice-toggle').textContent='Start voice mode';}renderOperation();}
 if(event==='map_fullscreen')mapFullscreen(data);
 if(event==='mic_level')$('#mic-level').value=data;
 if(event==='partial')$('#heard-partial').textContent=data;
 if(event==='heard')message('user',data);
 if(event==='answer'){chatFinished=true;renderOperation();message('assistant',data.text,data.references,{truncated:!!data.truncated});route=data.route||null;renderRoute();}
 if(event==='voice_preview'){preview=!!data;renderPreview();}
 if(event==='error'){if(data.startsWith('Local service stopped')){remoteOperation=null;serviceDown=true;}error(data,voice&&$('#assistant').classList.contains('visible')?'chat':undefined);}
 // Before the first `state` reply the running operation is unknown; it arrives with that reply.
 if(event==='progress'){window.setupProgress?.(data);$('#progress').textContent=data;if((pendingMethod||remoteOperation?.method)==='download_us_maps'){$('#map-progress').textContent=data;renderMapPause();const fraction=percentOf(data);if(fraction!=null)window.jarviss.setProgress(fraction).catch(()=>{});}if(/index/i.test(data))$('#location-search-status').textContent=data;}
});
async function restartService(){
 try{await window.jarviss.restartService();serviceDown=false;remoteOperation=null;remoteSetup=false;$('#error').hidden=true;await initialize();}
 catch(e){error(e);}
}
window.jarviss.onAppEvent(({event,data})=>{
 if($('#startup').classList.contains('visible')&&event!=='service-stopped'&&event!=='show-shortcuts')return;
 if(event==='open-page')page({chat:'assistant',maps:'atlas'}[data?.page]||data?.page||'assistant');
 if(event==='focus-composer'){page('assistant');$('#question').focus();}
 if(event==='toggle-voice'){if(!$('#voice-toggle').disabled)$('#voice-toggle').click();}
 if(event==='toggle-voice-panel')$('#panel-toggle').click();
 if(event==='show-shortcuts')$('#shortcuts-dialog').showModal();
 if(event==='service-stopped'){serviceDown=true;notice($('#error'),'The local service stopped. Chat, voice and maps are paused until it restarts.',{action:{label:'Restart local service',run:restartService}});renderOperation();}
});
$('[data-close-dialog]').onclick=()=>$('#shortcuts-dialog').close();
// About → "Keyboard shortcuts" opens the same dialog as the ? key; the button is created here if the page has none.
{
 let button=[...document.querySelectorAll('#settings-about button')].find(b=>/keyboard shortcuts/i.test(b.textContent));
 if(!button){button=document.createElement('button');button.id='show-shortcuts';button.textContent='Keyboard shortcuts';$('#settings-about .button-row')?.append(button);}
 button.onclick=()=>$('#shortcuts-dialog').showModal();
}
// Escape closes the innermost thing first: dialog (handled natively), then an open menu, then a map click mode, then full screen.
document.addEventListener('keydown',event=>{
 if(event.key==='?'&&!typing(event.target)&&!event.ctrlKey&&!event.metaKey){event.preventDefault();$('#shortcuts-dialog').showModal();return;}
 if(event.key!=='Escape'||$('#shortcuts-dialog').open)return;
 const menu=document.querySelector('details.menu[open]');if(menu){closeMenu(menu,true);return;}
 if(mapClickMode){cancelMapClick();return;}
 if(document.body.classList.contains('map-fullscreen'))window.jarviss.mapFullscreen(false).then(()=>mapFullscreen(false)).catch(error);
});
let initializing=false;
async function initialize(){
 if(initializing)return;
 initializing=true;$('#startup-retry').disabled=true;$('#startup-retry').hidden=true;
 $('#error').hidden=true;$('#startup-message').textContent='Checking setup…';
 try{
  state=await call('state');serviceDown=false;renderState(true);voice=!!state.voiceEnabled;voicePhase=voice?'Listening':'Voice off';preview=!!state.voicePreview;renderPreview();$('#voice-toggle').textContent=voice?'Stop voice mode':'Start voice mode';
  const skipped=!!state.setup?.skipped&&!!state.modelAvailable; // "Set up later" is remembered as long as chat can work
  const needsSetup=!skipped&&(state.setup?.status!=='ready'||!state.modelAvailable||!state.voiceReady||!state.basemap||!state.usRouting?.ready||remoteOperation?.method==='setup_run'||remoteSetup);
  if(needsSetup)await window.openSetup();else page('assistant');
  await audioDevices();renderOperation();
  if(state.settings?.model&&!state.ready&&!remoteOperation&&!remoteSetup&&(!needsSetup||state.setup?.model_ready))await call('start_model');
 }catch(e){error(e);}
 finally{initializing=false;$('#startup-retry').disabled=false;}
}
$('#startup-retry').onclick=initialize;
window.addEventListener('DOMContentLoaded',initialize);
window.jarviss.version().then(v=>{$('#app-version').textContent='v'+v;$('#about-version').textContent='Version '+v;}).catch(()=>{});

function askDocument(title){page('assistant');$('#question').value=`Using the document "${title}", `;$('#question').focus();}

async function audioDevices(){const list=await call('audio_devices');for(const [id,kind,key] of [['input-device','input','input_device'],['output-device','output','output_device']]){const select=$('#'+id);select.replaceChildren(new Option('System default',''));for(const d of list.filter(d=>d[kind])){const o=new Option(`${d.name} · ${d.host}`,d.id);select.add(o);if(state.settings?.[key]?.name===d.name&&state.settings[key].host===d.host)o.selected=true;}}$('#voice-name').value=state.settings?.voice_name||'bm_george';}
function renderPreview(){
 $('#test-speaker').textContent=preview?'Stop preview':'Preview voice';
 $('#test-speaker').disabled=audioSaving&&!preview;
 $('#audio-status').textContent=audioSaving?'Saving…':preview?'Playing selected voice…':'';
}
async function saveAudio(){
 if(audioSaving)return;
 audioSaving=true;renderPreview();
 const focused=document.activeElement;
 for(const id of ['input-device','output-device','voice-name'])$('#'+id).disabled=true;
 try{
  state.settings=await call('audio_settings',{input_device:$('#input-device').value?Number($('#input-device').value):null,output_device:$('#output-device').value?Number($('#output-device').value):null,voice_name:$('#voice-name').value});
 }finally{audioSaving=false;for(const id of ['input-device','output-device','voice-name'])$('#'+id).disabled=false;renderPreview();if(document.activeElement===document.body)focused?.focus?.();}
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
function renderPrompts(settings){for(const [key,id] of Object.entries(promptFields))$('#'+id).value=settings[key];$('#units').value=settings.units==='metric'?'metric':'imperial';}
function promptValues(){const values={};for(const [key,id] of Object.entries(promptFields))values[key]=key.endsWith('prompt')?$('#'+id).value:Number($('#'+id).value);values.units=$('#units').value;return values;}
// Advanced settings save themselves: each edit is debounced into one request and one "Saved" toast; invalid values wait until fixed.
let promptSaveTimer=null;
async function savePrompts(message='Saved'){
 clearTimeout(promptSaveTimer);promptSaveTimer=null;
 if(!$('#prompt-form').checkValidity())return;
 try{state.settings=await call('prompt_settings',promptValues());showToast(message);placesKey=null;renderAtlas();}catch{}
}
function schedulePromptSave(){clearTimeout(promptSaveTimer);promptSaveTimer=setTimeout(()=>savePrompts(),400);}
$('#prompt-form').onsubmit=e=>{e.preventDefault();savePrompts();};
for(const id of [...Object.values(promptFields),'units']){$('#'+id).addEventListener('input',schedulePromptSave);$('#'+id).addEventListener('change',schedulePromptSave);}
$('#reset-prompts').onclick=()=>{renderPrompts({...state.promptDefaults,units:state.settings?.units});savePrompts('Defaults restored');}; // Units is a preference, not a prompt default

// APG tabs: arrow keys move focus and selection, one tab in the tab order, panels via aria-controls. Shared with the Plan page.
function initTabs(container,{onSelect}={}){
 const tabs=()=>[...container.querySelectorAll('[role=tab]')];
 const panelOf=t=>t.getAttribute('aria-controls')&&document.getElementById(t.getAttribute('aria-controls'));
 const select=tab=>{
  const shown=panelOf(tab); // several tabs may share one panel (Plan records)
  for(const t of tabs()){const on=t===tab;t.setAttribute('aria-selected',String(on));t.tabIndex=on?0:-1;t.classList.toggle('selected',on);const panel=panelOf(t);if(panel&&panel!==shown)panel.hidden=true;}
  if(shown)shown.hidden=false;onSelect?.(tab);
 };
 container.addEventListener('click',e=>{const tab=e.target.closest('[role=tab]');if(tab&&container.contains(tab))select(tab);});
 container.addEventListener('keydown',e=>{
  const list=tabs(),i=list.indexOf(e.target);if(i<0)return;
  const next={ArrowRight:i+1,ArrowLeft:i-1,Home:0,End:list.length-1}[e.key];if(next==null)return;
  e.preventDefault();const tab=list[(next+list.length)%list.length];tab.focus();tab.click(); // click runs the tab's own handler too
 });
 const sync=()=>{const list=tabs(),current=list.find(t=>t.getAttribute('aria-selected')==='true')||list[0];if(current)select(current);};
 sync();
 return {select:name=>{const tab=tabs().find(t=>t===name||t.id===name||t.dataset.settings===name||t.dataset.tab===name);tab?.click();},sync};
}
window.initTabs=initTabs;
const settingsTabs=initTabs($('#settings-tabs'));

function setInspector(hidden){document.body.classList.toggle('voice-panel-hidden',hidden);$('#panel-toggle').setAttribute('aria-expanded',String(!hidden));try{localStorage.setItem('jarviss.inspector',hidden?'hidden':'shown');}catch{}}
$('#panel-toggle').onclick=()=>setInspector(!document.body.classList.contains('voice-panel-hidden'));
try{setInspector(localStorage.getItem('jarviss.inspector')==='hidden');}catch{}

$('#situation-find').onclick=async()=>{try{state.profile=await call('save_profile',Object.fromEntries(new FormData($('#profile-form'))));route=null;renderAtlas();page('atlas');showPicker(true);const parts=await call('location_parts',{text:state.profile.location_text||''});$('#city-search').value=parts.city;$('#landmark-search').value=parts.street;$('#city-search').focus();}catch{}};
$('#setup-skipped-open').onclick=()=>window.openSetup();

for(const [id,run,label] of [['open-data-folder',()=>window.jarviss.openDataFolder(),'Opening the data folder'],['show-logs',()=>window.jarviss.showLogs(),'Showing the log file'],['check-updates',()=>window.jarviss.checkUpdates(),'Opening the releases page']])
 $('#'+id).onclick=()=>guardFocus($('#'+id),async()=>{try{if(await run())showToast(label);}catch(e){error(e);}});
$('#restart-service').onclick=()=>confirmInline($('#restart-service'),'Restart the local service?',restartService);

$('#paste-document').onclick=()=>{$('#note-form').hidden=false;$('#note-form input').focus();};
$('#cancel-note').onclick=()=>{$('#note-form').hidden=true;$('#paste-document').focus();};
$('#note-form').onsubmit=async e=>{e.preventDefault();try{await call('import_note',Object.fromEntries(new FormData(e.target)));e.target.reset();e.target.hidden=true;await refresh();showToast('Document saved');$('#paste-document').focus();}catch{}};
