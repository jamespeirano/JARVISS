(()=>{
const sections={supplies:'Supplies',tasks:'Today',power:'Power',garden:'Garden',people:'People',log:'Log',messages:'Messages'};
const notes={supplies:'Amounts and daily use must use the same unit.',tasks:'Choose what matters now. Mark finished tasks Done.',power:'Watts × hours = energy used each day. Estimates use your inputs.',garden:'Use your seed packet and local planting guide for dates.',people:'Keep skills, needs and responsibilities together.',log:'Record what you know. Label reports and assumptions.'};
let section='supplies',edit=null,boardTimer=null;
const el=(tag,text)=>{const n=document.createElement(tag);if(text!=null)n.textContent=text;return n;};
function openSection(key){section=key;edit=null;render();}
function input(key,spec){const [name,kind,required]=spec;const label=el('label',name);let field;
 if(kind.startsWith('select:')){field=el('select');for(const option of kind.slice(7).split(','))field.add(new Option(option,option));}
 else{field=el(kind==='text'&&['notes','needs','resources','responsibility'].includes(key)?'textarea':'input');if(field.tagName==='INPUT')field.type=kind==='number'?'number':kind==='date'?'date':'text';if(kind==='number'){field.min='0';field.step='any';}field.maxLength=2000;}
 field.name=key;field.required=required;field.value=edit?.[key]??(kind.startsWith('select:')?kind.slice(7).split(',')[0]:'');label.append(field);return label;}
function render(){
 if(!state.plannerSchemas)return;
 $('#plan-tabs').replaceChildren();for(const [key,label] of Object.entries(sections)){const b=el('button',label);b.classList.toggle('selected',key===section);b.setAttribute('aria-pressed',String(key===section));b.onclick=()=>openSection(key);$('#plan-tabs').append(b);}
 const messages=section==='messages';$('#plan-records').hidden=messages;$('#board-panel').hidden=!messages;if(messages){renderBoard();return;}
 $('#plan-title').textContent=sections[section];$('#plan-note').textContent=notes[section];const form=$('#plan-form');form.replaceChildren();
 for(const [key,spec] of Object.entries(state.plannerSchemas[section]))form.append(input(key,spec));
 const add=el('button',edit?'Save changes':'Add '+({supplies:'item',tasks:'task',power:'device',garden:'crop',people:'person',log:'entry'}[section]));add.type='submit';form.append(add);
 if(edit){const cancel=el('button','Cancel');cancel.type='button';cancel.onclick=()=>{edit=null;render();};form.append(cancel);}
 $('#plan-list').replaceChildren();const records=state.planner?.[section]||[];
 if(!records.length)$('#plan-list').append(el('p','Nothing added yet.'));
 for(const r of records){const card=el('article');card.className='plan-record';card.append(el('strong',r.name));
  let detail=Object.entries(state.plannerSchemas[section]).filter(([key])=>key!=='name'&&r[key]!==''&&r[key]!=null).map(([key,spec])=>`${spec[0]}: ${r[key]}`).join(' · ');
  card.append(el('p',detail));
  if(section==='supplies')card.append(el('strong',r.days_left==null?'Add daily use to estimate how long it lasts.':`${r.days_left} days left`));
  if(section==='power')card.append(el('strong',`${Number((r.watts*r.hours).toFixed(2))} watt-hours/day`));
  if(r.harvest_on)card.append(el('strong','Estimated harvest: '+r.harvest_on));
  const actions=el('div');actions.className='record-actions';const change=el('button','Edit');change.onclick=()=>{edit=r;render();$('#plan-form input')?.focus();};actions.append(change);
  if(section==='tasks'){const done=el('button',r.done?'Reopen':'Done');card.classList.toggle('done',!!r.done);done.onclick=async()=>{try{state.planner=await call('planner_done',{kind:section,id:r.id});render();}catch{}};actions.append(done);}
  const remove=el('button','Remove');remove.onclick=async()=>{try{state.planner=await call('planner_delete',{kind:section,id:r.id});render();}catch{}};actions.append(remove);card.append(actions);$('#plan-list').append(card);}
 $('#energy-form').hidden=section!=='power';$('#power-summary').hidden=section!=='power';if(section==='power'){
  for(const k of ['battery_wh','solar_watts','sun_hours','efficiency'])$('#energy-form').elements[k].value=state.planner.energy?.[k]??'';
  const p=state.planner.power_summary;$('#power-summary').textContent=`Daily use: ${p.daily_wh} Wh · Estimated solar: ${p.solar_wh} Wh · Daily shortfall: ${p.shortfall_wh} Wh${p.battery_days!=null?' · Battery alone: '+p.battery_days+' days':''}`;
 }
}
$('#plan-form').onsubmit=async e=>{e.preventDefault();const kind=section,editing=edit,payload={kind,...Object.fromEntries(new FormData(e.target)),...(edit?{id:edit.id}:{})};const controls=[...e.target.elements];controls.forEach(e=>e.disabled=true);try{state.planner=await call('planner_save',payload);if(section===kind&&edit===editing){edit=null;render();}}catch{}finally{controls.forEach(e=>e.disabled=false);}};
$('#energy-form').onsubmit=async e=>{e.preventDefault();try{state.planner=await call('planner_energy',Object.fromEntries(new FormData(e.target)));render();}catch{}};
$('#plan-ask').onclick=()=>{page('assistant');$('#question').value=({supplies:'Using my saved supplies, what will run out first?',tasks:'Using my saved tasks, supplies and situation, what should we do first today?',power:'Using my saved power budget, how can we keep essential devices running longer?',garden:'Using my garden records, what should I plant or check next?',people:'Using my people records, help assign the most urgent work.',log:'Summarize my situation log. Separate observed facts, reports, assumptions and decisions.'}[section]);$('#question').focus();};
function renderBoard(){const b=state.board||{};$('#board-toggle').textContent=b.active?'Stop local board':'Start local board';$('#board-address').textContent=b.active?`Open ${b.address} on another device. Code: ${b.code}`:'';$('#board-note').textContent=b.active?'Share only with your group on a trusted local network. Messages are not encrypted.':'Start the board to let nearby devices read and post messages.';$('#board-messages').replaceChildren();for(const r of b.messages||[]){const item=el('article');item.className='plan-record';item.append(el('strong',r.name),el('p',r.text),el('small',new Date(r.at).toLocaleString()));$('#board-messages').append(item);}}
$('#board-toggle').onclick=async()=>{try{state.board=await call(state.board?.active?'board_stop':'board_start');renderBoard();}catch{}};
$('#board-form').onsubmit=async e=>{e.preventDefault();try{state.board=await call('board_send',Object.fromEntries(new FormData(e.target)));e.target.elements.text.value='';renderBoard();}catch{}};
boardTimer=setInterval(async()=>{if(section==='messages'&&$('#plan').classList.contains('visible')){try{state.board=await call('board_state');renderBoard();}catch{}}},5000);
window.renderPlanner=render;window.openPlan=key=>{page('plan');openSection(key);};render();
const quick=[['Water','Is this water usable?'],['Food','Can I still eat this food after the power went out?'],['Fix something','Help me fix my equipment using its manual.'],['What first?','Which task matters first today?']];
for(const [label,prompt] of quick){const b=el('button',label);b.onclick=()=>{$('#question').value=prompt;$('#question').focus();};$('#quick-actions').append(b);}
})();
