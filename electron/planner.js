(()=>{
const sections={supplies:'Supplies',tasks:'Today',power:'Power',garden:'Garden',people:'People',log:'Log'};
const units={supplies:'item',tasks:'task',power:'device',garden:'crop',people:'person',log:'entry'};
const notes={supplies:'Amounts and daily use must use the same unit.',tasks:'Choose what matters now. Mark finished tasks Done.',power:'Watts × hours = energy used each day. Estimates use your inputs.',garden:'Use your seed packet and local planting guide for dates.',people:'Keep skills, needs and responsibilities together.',log:'Record what you know. Label reports and assumptions.'};
let section='supplies',edit=null,formKey='',tabsReady=false;
const cards=new Map(); // record id → card, so a refresh re-renders in place and keeps focus
const el=(tag,text)=>{const n=document.createElement(tag);if(text!=null)n.textContent=text;return n;};
const firstField=()=>$('#plan-form input,#plan-form select,#plan-form textarea');
// APG tabs: arrow keys move and activate, one tab in the sequence. renderer.js may provide initTabs.
function localTabs(container,{onSelect}={}){
 container.addEventListener('click',e=>{const tab=e.target.closest('[role=tab]');if(tab)onSelect?.(tab);});
 container.addEventListener('keydown',e=>{
  const tabs=[...container.querySelectorAll('[role=tab]')],at=tabs.indexOf(document.activeElement);if(at<0)return;
  const next={ArrowRight:at+1,ArrowLeft:at-1,Home:0,End:tabs.length-1}[e.key];if(next==null)return;
  e.preventDefault();const tab=tabs[(next+tabs.length)%tabs.length];tab.focus();onSelect?.(tab);
 });
}
const tabKey=tab=>tab.id==='plan-messages-tab'?'messages':tab.id.slice(9);
function buildTabs(){
 if(tabsReady)return;tabsReady=true;
 for(const [key,label] of Object.entries(sections)){const b=el('button',label);b.id='plan-tab-'+key;b.type='button';b.dataset.tab=key;b.setAttribute('role','tab');b.setAttribute('aria-controls','plan-records');b.setAttribute('aria-selected',String(key===section));$('#plan-tab-group').append(b);}
 (window.initTabs||localTabs)($('#plan-tabs'),{onSelect:tab=>openSection(tabKey(tab))});
}
function selectTabs(){
 for(const tab of $('#plan-tabs').querySelectorAll('[role=tab]')){const on=tabKey(tab)===section;tab.setAttribute('aria-selected',String(on));tab.tabIndex=on?0:-1;tab.classList.toggle('selected',on);}
 if(section!=='messages')$('#plan-records').setAttribute('aria-labelledby','plan-tab-'+section);
}
// Several tabs share one panel, so the panel visibility is settled here after any generic tab handler ran.
function openSection(key){if(key!==section){section=key;edit=null;}render();if(key==='messages')pollBoard();}
function input(key,spec){const [name,kind,required]=spec;const label=el('label',name);let field;
 if(kind.startsWith('select:')){field=el('select');for(const option of kind.slice(7).split(','))field.add(new Option(option,option));}
 else{field=el(kind==='text'&&['notes','needs','resources','responsibility'].includes(key)?'textarea':'input');if(field.tagName==='INPUT')field.type=kind==='number'?'number':kind==='date'?'date':'text';if(kind==='number'){field.min='0';field.step='any';}field.maxLength=2000;}
 field.name=key;field.required=required;field.value=edit?.[key]??(kind.startsWith('select:')?kind.slice(7).split(',')[0]:'');label.append(field);return label;}
function renderForm(){
 const key=section+'|'+(edit?.id||'');if(key===formKey)return;formKey=key;
 const form=$('#plan-form');form.replaceChildren();
 for(const [k,spec] of Object.entries(state.plannerSchemas[section]))form.append(input(k,spec));
 const actions=el('div');actions.className='form-actions';
 const add=el('button',edit?'Save changes':'Add '+units[section]);add.type='submit';add.className='primary';actions.append(add);
 if(edit){const cancel=el('button','Cancel');cancel.type='button';cancel.className='quiet';cancel.onclick=()=>{edit=null;render();firstField()?.focus();};actions.append(cancel);}
 form.append(actions);
}
function focusMemo(){
 const active=document.activeElement,card=active?.closest?.('#plan-list .plan-record');
 if(card)return {id:card.dataset.id,action:active.dataset.action||'edit'};
 if(active?.closest?.('#plan-form'))return {form:active.name||true};
 return null;
}
function restoreFocus(memo){
 if(!memo||document.activeElement!==document.body)return;
 if(memo.form){(typeof memo.form==='string'&&$('#plan-form [name="'+memo.form+'"]')||firstField())?.focus();return;}
 const card=cards.get(memo.id);(card?.querySelector('[data-action="'+memo.action+'"]')||card?.querySelector('button')||firstField())?.focus();
}
// One meta sentence per record, written the way a person would say it ("30 liters · 15 a day · Blue jugs in the garage").
const has=v=>v!==''&&v!=null;
const date=v=>window.formatDate?window.formatDate(v,String(v)):String(v);
const recordMeta={
 supplies:r=>[has(r.quantity)?`${r.quantity} ${r.unit||''}`.trim():'',has(r.daily)?`${r.daily} a day`:'',r.notes],
 tasks:r=>[r.priority,r.owner,has(r.due)?`Due ${date(r.due)}`:'',r.needs?`Needs ${r.needs}`:'',has(r.check)?`Check ${date(r.check)}`:'',r.notes],
 power:r=>[`${r.watts} W`,`${r.hours} h a day`,`${Number((r.watts*r.hours).toFixed(2))} Wh a day`],
 garden:r=>[has(r.quantity)?`${r.quantity} left`:'',has(r.plant_on)?`Planted ${date(r.plant_on)}`:'',has(r.days)?`${r.days} days to harvest`:'',r.harvest_on?`Harvest around ${date(r.harvest_on)}`:'',has(r.next_check)?`Check ${date(r.next_check)}`:'',r.notes],
 people:r=>[r.skills,r.resources?`Can share ${r.resources}`:'',r.needs?`Needs ${r.needs}`:'',r.responsibility?`Responsible for ${r.responsibility}`:'',r.contact],
 log:r=>[r.status,r.place,r.observer?`Reported by ${r.observer}`:'',r.notes],
};
// "About N days left", rounded; three days or fewer is a warning.
function daysLeft(days){if(days==null)return {text:'Add daily use to estimate how long it lasts.',warn:false};const n=Math.round(days);return {text:n<1?'Less than a day left':`About ${n} day${n===1?'':'s'} left`,warn:days<=3};}
function recordCard(r){
 let card=cards.get(r.id);if(!card){card=el('article');card.className='plan-record';card.dataset.id=r.id;cards.set(r.id,card);}
 card.replaceChildren();card.classList.toggle('done',!!r.done);
 const title=el('strong',r.name);title.className='record-title';card.append(title);
 const detail=(recordMeta[section]?.(r)||[]).map(s=>String(s??'').trim()).filter(Boolean).join(' · ');
 if(detail){const meta=el('p',detail);meta.className='record-meta desc';card.append(meta);}
 if(section==='supplies'){const {text,warn}=daysLeft(r.days_left);const line=el('p',text);line.className='record-note'+(warn?' warn':'');card.append(line);}
 const actions=el('div');actions.className='record-actions';
 const change=el('button','Edit');change.type='button';change.dataset.action='edit';change.onclick=()=>{edit=r;render();firstField()?.focus();};actions.append(change);
 if(section==='tasks'){const done=el('button',r.done?'Reopen':'Done');done.type='button';done.dataset.action='done';done.onclick=async()=>{try{state.planner=await call('planner_done',{kind:section,id:r.id});render();}catch{}};actions.append(done);}
 const remove=el('button','Remove');remove.type='button';remove.className='quiet';remove.dataset.action='remove';
 remove.onclick=()=>twoStep(remove,'Remove?',async()=>{
  const ids=(state.planner?.[section]||[]).map(x=>x.id),at=ids.indexOf(r.id),next=ids[at+1]??ids[at-1];
  try{state.planner=await call('planner_delete',{kind:section,id:r.id});}catch{return;}
  render();(cards.get(next)?.querySelector('[data-action="remove"]')||firstField())?.focus();
 });
 actions.append(remove);card.append(actions);return card;
}
function renderRecords(){
 const list=$('#plan-list'),records=state.planner?.[section]||[],keep=new Set(records.map(r=>r.id));
 for(const [id,card] of cards)if(!keep.has(id)){card.remove();cards.delete(id);}
 list.querySelector('.empty')?.remove();
 if(!records.length){
  const empty=el('div');empty.className='empty';empty.append(el('p','Nothing added yet.'));
  const add=el('button','Add your first '+units[section]);add.type='button';add.className='compact';add.onclick=()=>firstField()?.focus();empty.append(add);list.append(empty);
 }
 for(const r of records)list.append(recordCard(r)); // append moves existing cards into the current order
}
function renderPower(){
 const power=section==='power';$('#energy-form').hidden=!power;$('#power-summary').hidden=!power;if(!power)return;
 if(!$('#energy-form').contains(document.activeElement))for(const k of ['battery_wh','solar_watts','sun_hours','efficiency'])$('#energy-form').elements[k].value=state.planner.energy?.[k]??'';
 const p=state.planner.power_summary||{},stats=[['Daily use',`${p.daily_wh} Wh`],['Estimated solar',`${p.solar_wh} Wh`],['Daily shortfall',`${p.shortfall_wh} Wh`]];
 if(p.battery_days!=null)stats.push(['Battery alone',`${p.battery_days} days`]);
 $('#power-summary').replaceChildren(...stats.map(([label,value])=>{const item=el('div');item.append(el('dt',label),el('dd',value));return item;}));
}
function render(){
 if(!state.plannerSchemas)return;
 buildTabs();selectTabs();applyBoard(state.board||{});scheduleBoard();
 const messages=section==='messages';$('#plan-records').hidden=messages;$('#board-panel').hidden=!messages;
 if(messages){renderBoardChrome();return;}
 const memo=focusMemo();
 $('#plan-title').textContent=sections[section];$('#plan-note').textContent=notes[section];
 renderForm();renderRecords();renderPower();restoreFocus(memo);
}
$('#plan-form').onsubmit=async e=>{
 e.preventDefault();const kind=section,editing=edit,payload={kind,...Object.fromEntries(new FormData(e.target)),...(edit?{id:edit.id}:{})};
 const controls=[...e.target.elements],active=document.activeElement;let after=null;controls.forEach(c=>c.disabled=true);
 try{
  const planner=await call('planner_save',payload);state.planner=planner;
  if(section===kind&&edit===editing){edit=null;if(!editing)e.target.reset();render();after=editing?cards.get(editing.id)?.querySelector('[data-action="edit"]'):firstField();}
 }catch{}
 finally{controls.forEach(c=>c.disabled=false);if(after)after.focus();else if(document.activeElement===document.body)(active?.isConnected?active:firstField())?.focus();}
};
$('#energy-form').onsubmit=async e=>{e.preventDefault();const active=document.activeElement;try{state.planner=await call('planner_energy',Object.fromEntries(new FormData(e.target)));render();toast('Power budget saved');}catch{}finally{if(document.activeElement===document.body)active?.focus();}};
$('#plan-ask').onclick=()=>{page('assistant');$('#question').value=({supplies:'Using my saved supplies, what will run out first?',tasks:'Using my saved tasks, supplies and situation, what should we do first today?',power:'Using my saved power budget, how can we keep essential devices running longer?',garden:'Using my garden records, what should I plant or check next?',people:'Using my people records, help assign the most urgent work.',log:'Summarize my situation log. Separate observed facts, reports, assumptions and decisions.'}[section]);$('#question').focus();};
// Group messages: append-only log, unread badge while the tab is out of sight, slow poll when hidden.
const seen=new Set(),boardToggle=$('#board-toggle');let unread=0,boardReady=false,boardTimer=null,shownAddress=null;
const boardVisible=()=>section==='messages'&&$('#plan').classList.contains('visible');
const messageKey=m=>`${m.at}\n${m.name}\n${m.text}`;
// "just now" for the first minute, "N min ago" for the first hour, then the clock time (with the date once it is not today).
function relativeTime(iso,now=Date.now()){
 const d=window.parseDate?window.parseDate(iso):new Date(iso);if(!d||Number.isNaN(d.getTime()))return '';
 const age=now-d.getTime();
 if(age<60e3)return 'just now';
 if(age<3600e3)return `${Math.max(1,Math.round(age/60e3))} min ago`;
 const time=window.formatTime?window.formatTime(d):d.toLocaleTimeString();
 return d.toDateString()===new Date(now).toDateString()?time:`${window.formatDate?window.formatDate(d):d.toLocaleDateString()} ${time}`;
}
function refreshBoardTimes(){for(const t of $('#board-messages').querySelectorAll('time[datetime]'))t.textContent=relativeTime(t.dateTime);}
function applyBoard(board){
 state.board=board;
 const fresh=(board.messages||[]).filter(m=>!seen.has(messageKey(m)));
 for(const m of fresh){seen.add(messageKey(m));const item=el('article');item.className='plan-record board-message';const when=el('time');when.className='meta';when.dateTime=m.at;when.title=new Date(m.at).toLocaleString();item.append(el('strong',m.name),el('p',m.text),when);$('#board-messages').append(item);}
 refreshBoardTimes();
 if(boardVisible())unread=0;else if(boardReady)unread+=fresh.length;boardReady=true;
 const badge=$('#board-unread');badge.hidden=!unread;badge.textContent=unread?String(unread):'';badge.setAttribute('aria-label',unread?`${unread} unread`:'');
}
function renderBoardChrome(){
 const b=state.board||{};boardToggle.textContent=b.active?'Stop local board':'Start local board';
 $('#board-live').hidden=!b.active;
 if(b.active&&(b.address!==shownAddress||$('#board-code').textContent!==b.code)){$('#board-address').textContent=b.address;$('#board-code').textContent=b.code;shownAddress=b.address;}
 if(!b.active)shownAddress=null;
 $('#board-note').textContent=b.active?'Share only with your group on a trusted local network. Messages are not encrypted.':'Start the board to let nearby devices read and post messages.';
}
async function pollBoard(){if(!state.board?.active)return;try{applyBoard(await call('board_state'));}catch{}}
function scheduleBoard(){clearTimeout(boardTimer);boardTimer=null;if(!state.board?.active)return;boardTimer=setTimeout(async()=>{await pollBoard();scheduleBoard();},boardVisible()?5000:20000);}
boardToggle.onclick=async()=>{
 const button=boardToggle;
 if(state.board?.active){twoStep(button,'Stop the board?',async()=>{try{applyBoard(await call('board_stop'));}catch{return;}renderBoardChrome();scheduleBoard();});return;}
 button.disabled=true;
 try{applyBoard(await call('board_start'));renderBoardChrome();scheduleBoard();}catch{}
 finally{button.disabled=false;if(document.activeElement===document.body)button.focus();}
};
// The session denies the async clipboard permission, so fall back to the selection command.
function copyFallback(text){const box=document.createElement('textarea');box.value=text;box.setAttribute('aria-hidden','true');box.style.position='fixed';box.style.opacity='0';document.body.append(box);box.select();let ok=false;try{ok=document.execCommand('copy');}catch{}box.remove();if(!ok)throw new Error('copy failed');}
$('#copy-board-address').onclick=async()=>{const text=state.board?.address||'',active=document.activeElement;try{try{await navigator.clipboard.writeText(text);}catch{copyFallback(text);}toast('Address copied');}catch{toast('Could not copy. Type the address instead.');}finally{if(document.activeElement!==active)active?.focus();}};
$('#board-form').onsubmit=async e=>{e.preventDefault();const active=document.activeElement;try{applyBoard(await call('board_send',Object.fromEntries(new FormData(e.target))));e.target.elements.text.value='';e.target.elements.text.focus();}catch{if(document.activeElement===document.body)active?.focus();}};
window.renderPlanner=render;window.openPlan=key=>{page('plan');openSection(key);};window.pollBoard=pollBoard;window.relativeTime=relativeTime;render();
})();
