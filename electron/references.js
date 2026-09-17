// Offline library browser and continuous document reader. Source text is never HTML.
const referenceEntries=new Map();
let referenceSearch=0,referenceTimer,readerSequence=0,readingDocument=null,readerReturn=null;
const readerSections=new Map();
function referenceButton(label,action){
 const button=document.createElement('button');button.textContent=label;
 button.onclick=async()=>{button.disabled=true;$('#error').hidden=true;try{await action();}catch(e){error(e);}finally{button.disabled=false;}};return button;
}
function renderReferences(){
 const docs=state.references||[];
 $('#reference-summary').textContent=`${docs.length} documents · ${Math.round(docs.reduce((n,d)=>n+d.words,0)/1000).toLocaleString()}k words · Available offline`;
 $('#reference-pdfs').textContent=`Illustrated PDFs (${docs.filter(d=>d.pdf).length})`;
 if(referenceEntries.size===docs.length)return;
 referenceEntries.clear();$('#references').replaceChildren();
 for(const doc of docs){
  const entry=document.createElement('article');entry.className='reference-card';entry.dataset.reference=doc.id;
  const title=document.createElement('h3');title.textContent=doc.title;
  const meta=document.createElement('p');meta.textContent=`${doc.topic} · ${doc.publisher} · ${doc.words.toLocaleString()} words`;
  const actions=document.createElement('div');actions.className='reference-actions';
  actions.append(referenceButton('Read full document',()=>openReference(doc.id)));
  if(doc.pdf)actions.append(referenceButton('Open illustrated PDF',()=>window.jarviss.openReferencePDF(doc.id)));
  entry.append(title,meta,actions);referenceEntries.set(doc.id,{doc,entry,loaded:null});$('#references').append(entry);
 }
}
async function loadReference(id){
 const item=referenceEntries.get(id);if(!item)throw new Error('This reference is not in the installed library.');
 if(!item.loaded)item.loaded=call('reference',{id}).catch(e=>{item.loaded=null;throw e;});
 return item.loaded;
}
function documentBody(text){
 const body=document.createElement('div');body.className='reference-prose';
 const lines=text.split('\n');let paragraph=[],list=null;
 const flush=()=>{if(paragraph.length){const p=document.createElement('p');p.textContent=paragraph.join(' ');body.append(p);paragraph=[];}};
 const cells=line=>line.trim().replace(/^\||\|$/g,'').split('|').map(s=>s.trim());
 for(let i=0;i<lines.length;i++){
  const line=lines[i].trim();
  if(!line){flush();continue;}
  let next=i+1;while(next<lines.length&&!lines[next].trim())next++;
  if(line.includes('|')&&next<lines.length&&/^\|?\s*:?-{3,}/.test(lines[next].trim())){
   flush();list=null;const table=document.createElement('table'),head=document.createElement('thead'),row=document.createElement('tr');
   for(const value of cells(line)){const th=document.createElement('th');th.scope='col';th.textContent=value;row.append(th);}head.append(row);table.append(head);
   const rows=document.createElement('tbody');i=next;
   while(i+1<lines.length){
    if(!lines[i+1].trim()){i++;continue;}
    if(!lines[i+1].includes('|'))break;
    const row=document.createElement('tr');for(const value of cells(lines[++i])){const td=document.createElement('td');td.textContent=value;row.append(td);}rows.append(row);
   }
   table.append(rows);const wrap=document.createElement('div');wrap.className='reference-table';wrap.append(table);body.append(wrap);continue;
  }
  const heading=line.match(/^#{1,6}\s+(.+)/),bullet=line.match(/^([-*•]|\d+[.)])\s+(.*)/);
  if(heading){flush();list=null;const h=document.createElement('h4');h.textContent=heading[1];body.append(h);}
  else if(bullet){
   flush();const tag=/^\d/.test(bullet[1])?'OL':'UL';
   if(!list||list.tagName!==tag){list=document.createElement(tag);body.append(list);}
   const li=document.createElement('li');li.textContent=bullet[2];if(tag==='OL')li.value=parseInt(bullet[1],10);list.append(li);
  }else{list=null;paragraph.push(line);}
 }
 flush();return body;
}
async function openReference(id,section){
 const sequence=++readerSequence,navigation=pageSequence,origin=document.activeElement,scroll=document.querySelector('main').scrollTop;
 const doc=await loadReference(id);if(sequence!==readerSequence||navigation!==pageSequence)return;
 if(!$('#reference-reader').classList.contains('visible'))readerReturn={origin,scroll,page:$('.page.visible')?.id||'docs'};
 readingDocument=doc;page('reference-reader');
 $('#reference-back').textContent=readerReturn?.page==='assistant'?'← Back to chat':'← Back to Docs';
 $('#reference-title').textContent=doc.title;
 $('#reference-meta').textContent=`${doc.publisher} · ${doc.date} · ${doc.words.toLocaleString()} words`;
 $('#reference-format').textContent=doc.pdf?`Text and illustrated PDF chapter · Original PDF pages ${doc.source_pages}`:'Full text available below · Text edition';
 $('#reference-open-pdf').hidden=$('#reference-save-pdf').hidden=$('#reference-page-pdf').hidden=!doc.pdf;
 $('#reference-save-text').textContent='Save text (.md)';$('#reference-save-pdf').textContent='Save PDF';
 closeSectionMenu();readerSections.clear();$('#reference-section-list').replaceChildren();$('#reference-text').replaceChildren();
 for(const section of doc.sections){
  const block=document.createElement('section');block.className='reference-section';block.id='reference-'+id+'-'+section.id;block.dataset.section=section.id;block.tabIndex=-1;
  const label=section.path?.length>2?section.path.slice(-2).join(' · '):section.heading;
  const heading=document.createElement('h3');heading.textContent=label;
  block.append(heading,documentBody(section.text));$('#reference-text').append(block);
  const choice=referenceButton(label,()=>{closeSectionMenu();showReferenceSection(block);});choice.dataset.target=block.id;
  $('#reference-section-list').append(choice);readerSections.set(block.id,{block,choice,label});
 }
 $('#reference-note').textContent=doc.note==='Source titles appear in each section. Use the edition and conditions shown.'?'':doc.note||'';
 $('#reference-note').hidden=!$('#reference-note').textContent;
 $('#reference-attribution').textContent=[...(doc.sources||[doc.url]),doc.editing_note||'',doc.attribution||'',doc.license_note||''].filter(Boolean).join('\n\n');
 $('#reference-source').open=false;
 const target=section&&document.getElementById('reference-'+id+'-'+section);
 $('#reference-link-status').hidden=!section||!!target;
 if(target)showReferenceSection(target);
 else{setReaderSection(readerSections.keys().next().value);$('#reference-title').focus({preventScroll:true});document.querySelector('main').scrollTop=0;}
}
function setReaderSection(id){
 const selected=readerSections.get(id);if(!selected)return;
 $('#reference-contents').textContent=selected.label;$('#reference-contents').dataset.target=id;
 $('#reference-contents').setAttribute('aria-label','Jump to section: '+selected.label);
 for(const item of readerSections.values())item.choice.setAttribute('aria-current',String(item===selected));
}
function showReferenceSection(target){
 setReaderSection(target.id);
 document.querySelectorAll('.reference-selected').forEach(el=>el.classList.remove('reference-selected'));
 target.classList.add('reference-selected');target.focus({preventScroll:true});target.scrollIntoView({block:'start'});
}
function closeSectionMenu(focus=false){$('#reference-section-list').hidden=true;$('#reference-contents').setAttribute('aria-expanded','false');if(focus)$('#reference-contents').focus();}
function openSectionMenu(){
 const button=$('#reference-contents'),list=$('#reference-section-list'),rect=button.getBoundingClientRect();
 const below=innerHeight-rect.bottom-16,above=rect.top-16,up=below<180&&above>below;
 list.classList.toggle('open-above',up);list.style.maxHeight=Math.min(360,Math.max(100,up?above:below))+'px';
 list.hidden=false;button.setAttribute('aria-expanded','true');
 const selected=readerSections.get(button.dataset.target)?.choice;
 selected?.focus({preventScroll:true});if(selected)list.scrollTop=selected.offsetTop-list.clientHeight/2;
}
$('#reference-contents').onclick=()=>$('#reference-section-list').hidden?openSectionMenu():closeSectionMenu(true);
$('#reference-picker').onkeydown=event=>{
 if(event.key==='Escape'){event.preventDefault();event.stopPropagation();closeSectionMenu(true);return;}
 if(!['ArrowDown','ArrowUp','Home','End'].includes(event.key))return;
 event.preventDefault();if($('#reference-section-list').hidden){openSectionMenu();return;}
 const choices=[...readerSections.values()].map(item=>item.choice),index=choices.indexOf(document.activeElement);
 const next=event.key==='Home'?0:event.key==='End'?choices.length-1:Math.max(0,Math.min(choices.length-1,index+(event.key==='ArrowDown'?1:-1)));
 choices[next]?.focus();
};
document.addEventListener('click',event=>{if(!$('#reference-picker').contains(event.target))closeSectionMenu();});
window.addEventListener('resize',()=>closeSectionMenu());
let readerScrollFrame;
document.querySelector('main').addEventListener('scroll',()=>{
 closeSectionMenu();if(readerScrollFrame||!$('#reference-reader').classList.contains('visible'))return;
 readerScrollFrame=requestAnimationFrame(()=>{readerScrollFrame=null;let current=readerSections.keys().next().value;
  const edge=$('.reference-jump').getBoundingClientRect().bottom+24;
  for(const [id,item] of readerSections){if(item.block.getBoundingClientRect().top<=edge)current=id;else break;}setReaderSection(current);
 });
},{passive:true});
$('#reference-back').onclick=()=>{readerSequence++;page(readerReturn?.page==='assistant'?'assistant':'docs');document.querySelector('main').scrollTop=readerReturn?.scroll||0;readerReturn?.origin?.focus({preventScroll:true});};
document.addEventListener('keydown',event=>{if(event.key==='Escape'&&$('#reference-reader').classList.contains('visible'))$('#reference-back').click();});
$('#reference-open-pdf').onclick=()=>window.jarviss.openReferencePDF(readingDocument.id).catch(error);
$('#reference-page-pdf').onclick=()=>window.jarviss.openReferencePDF(readingDocument.id,document.getElementById($('#reference-contents').dataset.target).dataset.section).catch(error);
for(const [selector,format,label] of [['#reference-save-text','md','Text saved'],['#reference-save-pdf','pdf','PDF saved']]){
 $(selector).onclick=async()=>{const doc=readingDocument;try{if(await window.jarviss.saveReference(doc.id,format)&&readingDocument===doc)$(selector).textContent=label;}catch(e){error(e);}};
}
$('#reference-ask').onclick=()=>askDocument(readingDocument.title);
function filterDocs(){
 const q=$('#docs-search').value.trim().toLowerCase(),sequence=++referenceSearch,pdfs=$('#reference-pdfs').getAttribute('aria-pressed')==='true';
 for(const d of document.querySelectorAll('#guides .doc-entry,#documents .doc-entry,.recovery-entry'))d.hidden=!!q&&!d.textContent.toLowerCase().includes(q);
 for(const item of referenceEntries.values())item.entry.hidden=pdfs&&!item.doc.pdf;
 clearTimeout(referenceTimer);$('#references').hidden=!!q;$('#reference-results').hidden=!q;
 if(!q){$('#reference-results').replaceChildren();return;}
 $('#reference-results').textContent='Searching…';
 referenceTimer=setTimeout(async()=>{
  try{const results=await call('reference_search',{query:q});if(sequence!==referenceSearch)return;
   const nodes=results.filter(ref=>!pdfs||referenceEntries.get(ref.id)?.doc.pdf).map(ref=>{
    const b=referenceButton(ref.title+' · '+ref.heading,()=>openReference(ref.id,ref.section));b.className='reference-result';return b;
   });
   if(!nodes.length){const p=document.createElement('p');p.textContent='No matching documents.';nodes.push(p);}
   $('#reference-results').replaceChildren(...nodes);
  }catch{}
 },180);
}
$('#docs-search').oninput=filterDocs;
$('#reference-pdfs').onclick=()=>{const button=$('#reference-pdfs');button.setAttribute('aria-pressed',String(button.getAttribute('aria-pressed')!=='true'));filterDocs();};
