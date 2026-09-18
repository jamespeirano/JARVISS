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
  return plan;
 }
 function render(){
  const h=plan.hardware,model=plan.models.find(m=>m.id===selected);
  at('hardware-summary').textContent=`${Math.round(h.memory/1073741824)} GB memory · ${h.unified?'Apple silicon':h.gpus.length?h.gpus.map(g=>g.name).join(', '):'CPU graphics fallback'} · ${gb(h.disk)} free storage`;
  // The chosen model lives in the "AI model" row below; the option list carries each model's size, reason and any caution.
  at('setup-models').replaceChildren();
  for(const m of plan.models){
   const label=make('label',''),input=document.createElement('input');label.className='model-option'+(m.id===selected?' selected':'');input.type='radio';input.name='setup-model';input.value=m.id;input.checked=m.id===selected;input.disabled=running||!m.fits;
   input.onchange=()=>check(m.id);
   const text=make('span',m.name+(m.id===plan.recommended?' · Recommended':''));text.append(make('small',[gb(m.bytes),m.reason,m.note].filter(Boolean).join(' · ')));label.append(input,text);at('setup-models').append(label);
  }
  // The chosen model's caution stays visible without opening the list.
  let note=at('setup-model-note');if(!note){note=make('p','');note.id='setup-model-note';note.className='desc';at('setup-components').after(note);}
  note.textContent=[selected===plan.recommended?'Recommended for your computer.':'',model.note||''].filter(Boolean).join(' ');note.hidden=!note.textContent;
  at('setup-components').replaceChildren();
  const sizes=plan.component_bytes||{};
  for(const [id,name] of Object.entries({model:'AI model',voice:'Voice',map:'US map',directions:'Walking directions',guides:'Guides'})){
   const ready=!!plan.components[id],row=make('li','');row.classList.toggle('ready',ready);
   if(ready){const icon=document.createElementNS('http://www.w3.org/2000/svg','svg'),use=document.createElementNS('http://www.w3.org/2000/svg','use');icon.setAttribute('class','icon');icon.setAttribute('aria-hidden','true');use.setAttribute('href','#i-check');icon.append(use);row.append(icon);}
   const label=make('span',name);
   if(id==='model'){label.append(make('small',` · ${model.name}`));label.lastChild.className='meta';} // the chosen model lives in its row
   const size=make('small',ready?'':sizes[id]?gb(sizes[id]):id==='guides'?'Included':''),status=make('small',ready?'Ready':'To download');size.className='size';status.className='state';
   row.append(label,size,status);
   if(id==='model'&&plan.models.length>1){const change=make('button','Change');change.type='button';change.className='quiet compact';change.disabled=running;change.onclick=()=>{at('model-options').open=true;at('setup-models').querySelector('input:checked,input:not(:disabled)')?.focus();};row.append(change);}
   at('setup-components').append(row);
  }
  at('setup-size').textContent=plan.download_bytes?`About ${gb(plan.download_bytes)} left to download. Keep ${gb(plan.required_bytes)} free.`:'All files are downloaded. Run setup to check they work together.';
  at('setup-directory').textContent='Data folder: '+plan.directory;
  at('setup-warning').textContent=!plan.space_ok?'Not enough free storage.':!model.fits?model.reason:plan.run.error||'';
  const ready=plan.run.status==='ready'&&Object.values(plan.components).every(Boolean);
  at('setup-download').textContent=ready?'Check setup':plan.run.status==='paused'?'Continue setup':plan.download_bytes?'Download everything':'Finish setup';
  // Chat-only skips voice, map and directions; it is only worth offering while any of those is still missing.
  const mapsMissing=!plan.components.map||!plan.components.directions||!plan.components.voice;
  at('setup-chat-only').hidden=ready||running||!mapsMissing||plan.run.status==='paused';
  at('setup-chat-only').textContent=sizes.model?`Download chat only (≈${gb(sizes.model)})`:'Set up chat only';
  at('setup-later').textContent=running&&state.ready?'Use chat while maps download':'Set up later';
  at('setup-download').disabled=running||!plan.space_ok||!model.fits;
  at('setup-chat-only').disabled=running||!model.fits;
  at('setup-done').hidden=!ready;
  at('setup-later').hidden=ready;
  if(ready){at('setup-size').textContent='Ready offline';at('setup-warning').textContent=plan.run.seconds>90?'The model works, but replies may be slow. A smaller model is available above.':'';}
  at('setup-activity').hidden=!running&&!['failed','paused','testing','downloading'].includes(plan.run.status);
  progress(plan.run.detail||'',plan.run);
 }
 function progress(text,run=state.setup||{}){
  at('setup-detail').textContent=[text,run.eta].filter(Boolean).join(' · ');
  at('setup-bar').value=Math.max(0,Math.min(100,Number(run.percent)||0));
  at('setup-bar').setAttribute('aria-valuetext',`${at('setup-bar').value}%${run.eta?' · '+run.eta:''}`);
 }
 window.renderSetupOperation=(active,method,setupRunning)=>{
  running=setupRunning||active&&method==='setup_run';
  syncPause(running,state.setup?.stage===3&&/^US map ·/.test(state.setup?.detail||''));
  const fits=!!plan?.models.find(m=>m.id===selected)?.fits;
  at('setup-download').disabled=active||running||!plan||!plan.space_ok||!fits;
  at('setup-chat-only').disabled=active||running||!plan||!fits;
  at('setup-recheck').disabled=active||running;
  for(const input of document.querySelectorAll('[name="setup-model"]'))input.disabled=active||running||!plan.models.find(m=>m.id===input.value).fits;
  for(const change of at('setup-components').querySelectorAll('button'))change.disabled=active||running;
  if(running){at('setup-activity').hidden=false;at('setup-chat-only').hidden=true;}
 };
 window.setupProgress=text=>{if(running)progress(text);at('setup-later').textContent=state.ready?'Use chat while maps download':'Set up later';};
 window.refreshSetup=()=>{if(at('setup').classList.contains('visible'))check(selected);};
 window.openSetup=()=>{page('setup');at('error').hidden=true;return check();};
 // Settings shows the catalog name for the selected model; the plan is fetched once when it is not loaded yet.
 window.setupModelName=id=>plan?.models.find(m=>m.id===id)?.name;
 window.ensureSetupPlan=()=>plan?Promise.resolve(plan):check();
 for(const id of ['download-model','view-setup','map-view-setup'])at(id).onclick=window.openSetup;
 at('setup-recheck').onclick=()=>check(selected);
 at('setup-done').onclick=()=>page('assistant');
 at('setup-later').onclick=()=>guardFocus(at('setup-later'),async()=>{try{state.setup=await call('setup_skip',{});}catch{}page('assistant');renderOperation();});
 const syncPause=pauseButton(at('setup-pause'),{onPause:()=>{at('setup-detail').textContent='Pausing…';}});
 const start=(button,only_model)=>async()=>{
  if(!plan||running)return;
  at('setup-warning').textContent='';at('setup-activity').hidden=false;at('setup-bar').value=0;
  window.setupWillDownload?.(!!plan.download_bytes); // a check-only run ends without an OS notification
  const focused=button;
  try{await call('setup_run',{model_id:selected,...(only_model?{only_model:true}:{})});}
  catch(e){error(e);}
  finally{await refresh();await check(selected);if(document.activeElement===document.body)(focused.hidden||focused.disabled?at('setup').querySelector('.page-title'):focused).focus({preventScroll:true});}
 };
 at('setup-download').onclick=start(at('setup-download'),false);
 at('setup-chat-only').onclick=start(at('setup-chat-only'),true);
})();
