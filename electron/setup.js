/* The model catalog and hardware advice come from the local backend. */
(() => {
 let plan=null, selected=null, running=false, request=0;
 const at=id=>document.getElementById(id);
 const gb=n=>(n/1e9).toFixed(1)+' GB';
 const make=(tag,text)=>{const node=document.createElement(tag);node.textContent=text;return node;};
 async function check(id){
  const token=++request;
  at('setup-download').disabled=true;
  try {
   const next=await call('setup_plan',id?{model_id:id}:{});
   if(token!==request)return;
   plan=next;selected=plan.selected;render();renderOperation();
  }catch(e){at('setup-warning').textContent=e.message;}
 }
 function render(){
  const h=plan.hardware,model=plan.models.find(m=>m.id===selected);
  at('hardware-summary').textContent=`${Math.round(h.memory/1073741824)} GB memory · ${h.unified?'Apple silicon':h.gpus.length?h.gpus.map(g=>g.name).join(', '):'CPU graphics fallback'} · ${gb(h.disk)} free storage`;
  const card=at('recommended-model');card.replaceChildren();
  card.append(make('small',selected===plan.recommended?'Recommended for your computer':'Selected model'),make('h3',model.name),make('p',`${gb(model.bytes)} · ${model.reason}`));
  if(model.note)card.append(make('p',model.note));
  at('setup-models').replaceChildren();
  for(const m of plan.models){
   const label=make('label',''),input=document.createElement('input');input.type='radio';input.name='setup-model';input.value=m.id;input.checked=m.id===selected;input.disabled=running||!m.fits;
   input.onchange=()=>check(m.id);
   const text=make('span',m.name+(m.id===plan.recommended?' · Recommended':''));text.append(make('small',`${gb(m.bytes)} · ${m.reason}`));label.append(input,text);at('setup-models').append(label);
  }
  at('setup-components').replaceChildren();
  for(const [id,name] of Object.entries({model:'AI model',voice:'Voice',map:'US map',directions:'Walking directions',guides:'Guides'})){
   at('setup-components').append(make('li',`${plan.components[id]?'✓ ':''}${name}`));
  }
  at('setup-size').textContent=plan.download_bytes?`About ${gb(plan.download_bytes)} left to download. Keep ${gb(plan.required_bytes)} free.`:'All files are downloaded. Run setup to check they work together.';
  at('setup-directory').textContent='Data folder: '+plan.directory;
  at('setup-warning').textContent=!plan.space_ok?'Not enough free storage.':!model.fits?model.reason:plan.run.error||'';
  const ready=plan.run.status==='ready'&&Object.values(plan.components).every(Boolean);
  at('setup-download').textContent=ready?'Check setup':plan.run.status==='paused'?'Continue setup':plan.download_bytes?'Download everything':'Finish setup';
  at('setup-later').textContent=running&&state.ready?'Use chat while maps download':'Set up later';
  at('setup-download').disabled=running||!plan.space_ok||!model.fits;
  at('setup-done').hidden=!ready;
  at('setup-later').hidden=ready;
  if(ready){at('setup-size').textContent='Ready offline';at('setup-warning').textContent=plan.run.seconds>90?'The model works, but replies may be slow. A smaller model is available above.':'';}
  at('setup-activity').hidden=!running&&!['failed','paused','testing','downloading'].includes(plan.run.status);
  at('setup-detail').textContent=plan.run.detail||'';
  at('setup-bar').value=plan.run.stage||0;
 }
 window.renderSetupOperation=(active,method,setupRunning)=>{
  running=setupRunning||active&&method==='setup_run';
  syncPause(running,state.setup?.stage===3&&/^US map ·/.test(state.setup?.detail||''));
  at('setup-download').disabled=active||running||!plan||!plan.space_ok||!plan.models.find(m=>m.id===selected)?.fits;
  at('setup-recheck').disabled=active||running;
  for(const input of document.querySelectorAll('[name="setup-model"]'))input.disabled=active||running||!plan.models.find(m=>m.id===input.value).fits;
  if(running)at('setup-activity').hidden=false;
 };
 window.setupProgress=text=>{if(running){at('setup-detail').textContent=text;at('setup-bar').value=state.setup?.stage||0;}at('setup-later').textContent=state.ready?'Use chat while maps download':'Set up later';};
 window.refreshSetup=()=>{if(at('setup').classList.contains('visible'))check(selected);};
 window.openSetup=()=>{page('setup');at('error').hidden=true;return check();};
 for(const id of ['download-model','view-setup','map-view-setup'])at(id).onclick=window.openSetup;
 at('setup-recheck').onclick=()=>check(selected);
 at('setup-later').onclick=at('setup-done').onclick=()=>page('assistant');
 const syncPause=pauseButton(at('setup-pause'),{onPause:()=>{at('setup-detail').textContent='Pausing…';}});
 at('setup-download').onclick=async()=>{
  if(!plan||running)return;
  at('setup-warning').textContent='';at('setup-activity').hidden=false;at('setup-bar').removeAttribute('value');
  try{await call('setup_run',{model_id:selected});}
  catch(e){error(e);}
  finally{await refresh();await check(selected);}
 };
})();
