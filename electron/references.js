// Docs page: imported files, the field library, guides and the continuous document reader. Source text is never HTML.
const referenceEntries=new Map(),readerSections=new Map(),documentCache=new Map();
let referenceSearch=0,referenceTimer,readerSequence=0,readingDocument=null,readerReturn=null,readerJumpScroll=null;
const DOC_LIMIT=30,planNames={tasks:'Today',people:'People',messages:'Group messages',supplies:'Supplies',power:'Power',garden:'Garden',log:'Log'};
// Shared UI helpers; renderer.js may provide its own, in which case these stay unused.
// Toasts one after another so several drop results are all seen; window.toast (renderer.js) shows one at a time.
const toastQueue=[];let toastBusy=false;
function queueToast(text){toastQueue.push(String(text));if(!toastBusy)drainToasts();}
function drainToasts(){const text=toastQueue.shift();toastBusy=!!text;if(!text)return;(window.toast||(t=>{$('#toast').textContent=t;}))(text);setTimeout(drainToasts,2600);}
window.twoStep??=typeof confirmInline==='function'?confirmInline:(button,label,onYes)=>{
 const box=document.createElement('span');box.className='confirm';box.setAttribute('role','group');box.setAttribute('aria-label',label);
 const text=document.createElement('span');text.textContent=label;
 const yes=document.createElement('button');yes.type='button';yes.className='danger compact';yes.textContent='Yes';yes.dataset.action='confirm';
 const no=document.createElement('button');no.type='button';no.className='compact';no.textContent='No';
 const restore=focus=>{if(box.isConnected)box.replaceWith(button);if(focus)button.focus();};
 no.onclick=()=>restore(true);box.onkeydown=e=>{if(e.key==='Escape'){e.preventDefault();e.stopPropagation();restore(true);}};
 yes.onclick=async()=>{yes.disabled=no.disabled=true;try{await onYes();restore(document.activeElement===document.body||document.activeElement===yes);}catch{restore(true);}};
 box.append(text,yes,no);button.replaceWith(box);yes.focus();return box;
};
function referenceButton(label,action){
 const button=document.createElement('button');button.textContent=label;
 button.onclick=async()=>{button.disabled=true;$('#error').hidden=true;try{await action();}catch(e){error(e);}finally{button.disabled=false;}};return button;
}
// One row recipe for the field library and Your files: the whole row opens the document (its main button carries
// title + meta), trailing actions sit in .doc-row-actions. Rename swaps the main button for a form, so it is never nested in one.
function docRow({title,meta,open,mine=false,actions=[]}){
 const row=document.createElement('article');row.className='doc-row'+(mine?' mine':'');
 const main=document.createElement('button');main.type='button';main.className='doc-row-main';main.dataset.action='open';
 const name=document.createElement('strong');name.className='doc-title';name.textContent=title;
 const info=document.createElement('span');info.className='meta';info.textContent=meta;
 main.append(name,info);
 main.onclick=async()=>{main.disabled=true;$('#error').hidden=true;try{await open();}catch(e){error(e);}finally{main.disabled=false;}};
 const tools=document.createElement('div');tools.className='doc-row-actions';tools.append(...actions);
 if(!mine)tools.append(icon('chevron-right'));
 row.append(main,tools);
 row.onclick=e=>{if(e.target.closest('button,form,input,.confirm'))return;row.querySelector('.doc-row-main')?.click();};
 return row;
}
function renderReferences(){
 const docs=state.references||[];
 $('#reference-summary').textContent=`${docs.length} field documents · ${Math.round(docs.reduce((n,d)=>n+d.words,0)/1000).toLocaleString()}k words · Available offline`;
 $('#reference-summary').dataset.fullSummary=$('#reference-summary').textContent;
 $('#reference-pdfs').textContent=`With illustrations (${docs.filter(d=>d.pdf).length})`;
 if(referenceEntries.size===docs.length)return;
 referenceEntries.clear();$('#references').replaceChildren();
 for(const doc of docs){
  const actions=[];
  if(doc.pdf){const pdf=referenceButton('Open illustrated PDF',()=>window.jarviss.openReferencePDF(doc.id));pdf.className='quiet compact';actions.push(pdf);}
  const entry=docRow({title:doc.title,meta:`${doc.topic} · ${doc.words.toLocaleString()} words`,open:()=>openReference(doc.id),actions});
  entry.dataset.reference=doc.id;
  referenceEntries.set(doc.id,{doc,entry,loaded:null});$('#references').append(entry);
 }
}
async function loadReference(id){
 const item=referenceEntries.get(id);if(!item)throw new Error('This reference is not in the installed library.');
 if(!item.loaded)item.loaded=call('reference',{id}).catch(e=>{item.loaded=null;throw e;});
 return item.loaded;
}
async function loadDocument(title){
 let loaded=documentCache.get(title);
 if(!loaded){loaded=call('document',{title}).catch(e=>{documentCache.delete(title);throw e;});documentCache.set(title,loaded);}
 return loaded;
}
// Your files: rows that open on click, with inline Rename and a two-step Remove as compact actions.
const importedLabel=doc=>`Imported ${window.formatDate?.(doc.imported_at,'earlier')||String(doc.imported_at||'').slice(0,10)||'earlier'} · ${(doc.words||0).toLocaleString()} words`;
const documentCard_=doc=>[...document.querySelectorAll('#documents .doc-row.mine')].find(card=>card.dataset.document===doc);
const documentButton=(title,action)=>documentCard_(title)?.querySelector(`[data-action="${action}"]`);
function documentCard(doc){
 const rename=document.createElement('button');rename.type='button';rename.className='quiet compact';rename.textContent='Rename';rename.dataset.action='rename';
 const remove=document.createElement('button');remove.type='button';remove.className='quiet compact';remove.textContent='Remove';remove.dataset.action='remove';
 const card=docRow({title:doc.title,meta:importedLabel(doc),open:()=>openDocument(doc.title),mine:true,actions:[rename,remove]});
 card.dataset.document=doc.title;
 rename.onclick=()=>renameDocument(doc,card.querySelector('.doc-row-main'),rename);
 remove.onclick=()=>twoStep(remove,'Remove this file?',async()=>{
  const titles=(state.documents||[]).map(d=>d.title),at=titles.indexOf(doc.title),next=titles[at+1]??titles[at-1];
  try{await call('library_delete',{title:doc.title});await refresh();}catch{return;}
  queueToast(`Removed "${doc.title}"`);(documentButton(next,'remove')||$('#import-document')).focus();
 });
 return card;
}
function renameDocument(doc,title,button){
 const form=document.createElement('form');form.className='rename-form';
 const input=document.createElement('input');input.value=doc.title;input.maxLength=120;input.required=true;input.setAttribute('aria-label','New name for '+doc.title);
 const save=document.createElement('button');save.className='primary compact';save.textContent='Save';
 const cancel=document.createElement('button');cancel.type='button';cancel.className='quiet compact';cancel.textContent='Cancel';
 const restore=()=>{form.replaceWith(title);button.focus();};
 cancel.onclick=restore;form.onkeydown=e=>{if(e.key==='Escape'){e.preventDefault();e.stopPropagation();restore();}};
 form.onsubmit=async e=>{
  e.preventDefault();const name=input.value.trim();if(!name||name===doc.title){restore();return;}
  save.disabled=cancel.disabled=true;
  try{const renamed=await call('library_rename',{title:doc.title,new_title:name});await refresh();queueToast(`Renamed to "${renamed}"`);(documentButton(renamed,'rename')||$('#docs-search')).focus();}
  catch{save.disabled=cancel.disabled=false;input.focus();}
 };
 form.append(input,save,cancel);title.replaceWith(form);input.focus();input.select();
}
function guideEntry(guide){
 const entry=document.createElement('details');entry.className='doc-entry';
 const summary=document.createElement('summary'),name=document.createElement('span'),meta=document.createElement('small');
 name.textContent=guide.title;meta.textContent=guide.url?'Source: '+new URL(guide.url).hostname:'JARVISS planning checklist';summary.append(name,meta);
 const body=documentBody(guide.text||'');body.classList.add('doc-body');
 const ask=document.createElement('button');ask.className='doc-ask';ask.textContent='Ask about this';ask.onclick=()=>{askDocument(guide.title);if(guide.prompt)$('#question').value=guide.prompt;};
 entry.append(summary,body,ask);
 if(guide.plan){const open=document.createElement('button');open.textContent='Open '+(planNames[guide.plan]||guide.plan);open.onclick=()=>window.openPlan?.(guide.plan);entry.append(open);}
 return entry;
}
function recoveryEntry(){
 const entry=document.createElement('details');entry.className='doc-entry';
 const summary=document.createElement('summary'),name=document.createElement('span'),meta=document.createElement('small');
 name.textContent='Regroup and rebuild';meta.textContent='A short group checklist';summary.append(name,meta);
 const body=documentBody(state.recovery||'');body.classList.add('doc-body');
 const ask=document.createElement('button');ask.className='doc-ask';ask.textContent='Ask about this';ask.onclick=()=>askDocument('Regroup and rebuild');
 entry.append(summary,body,ask);return entry;
}
if(!$('.recovery-entry .doc-ask')){const ask=document.createElement('button');ask.className='doc-ask';ask.textContent='Ask about this';ask.onclick=()=>askDocument('Regroup and rebuild');$('.recovery-entry').append(ask);}
function renderDocuments(current=state){
 const docs=current.documents||[];documentCache.clear();
 $('#documents').replaceChildren(...docs.map(documentCard));
 if(!docs.length){
  const empty=document.createElement('div');empty.className='empty';const text=document.createElement('p');text.textContent='No files yet. Add a PDF, text or Markdown file, or paste text.';
  const add=document.createElement('button');add.className='compact';add.textContent='Add a file';add.onclick=()=>$('#import-document').click();empty.append(text,add);$('#documents').append(empty);
 }
 const cap=$('#docs-cap');cap.className='notice '+(docs.length>=DOC_LIMIT?'danger':'warn');cap.textContent=`${docs.length} of ${DOC_LIMIT} files used — remove one to add more`;
 $('#guides').replaceChildren(...(current.guides||[]).map(guideEntry));
 const recovery=documentBody(current.recovery||'');recovery.classList.add('doc-body');$('#recovery-document').replaceChildren(recovery);
 renderReferences();filterDocs();
}
// Drag and drop: paths are resolved in the preload, then imported one by one. A FileList does not cross the context bridge; an array of File objects does.
async function importDropped(files){
 const list=$('#documents');list.setAttribute('aria-busy','true');
 try{
  const results=await window.jarviss.importPaths(Array.from(files||[]));
  if(!results.length){queueToast('Drop a PDF, text or Markdown file.');return;}
  for(const result of results)queueToast(result.error?`${String(result.path).split(/[\\/]/).pop()}: ${result.error}`:`Added "${result.title}"`);
  if(results.some(r=>!r.error))await refresh();
 }catch(e){error(e);}finally{list.removeAttribute('aria-busy');}
}
// The whole Docs page is the drop target. A .drop-overlay appears on the first dragenter and leaves when the drag
// leaves the page or drops; the counter absorbs the enter/leave pairs fired by every child element crossed.
{
 const docs=$('#docs'),hasFiles=e=>[...(e.dataTransfer?.types||[])].includes('Files');let depth=0,overlay=null;
 const show=()=>{
  if(overlay)return;
  overlay=docs.querySelector(':scope > .drop-overlay'); // the page may ship the overlay; otherwise it is built here
  if(!overlay){
   overlay=document.createElement('div');overlay.className='drop-overlay';overlay.setAttribute('aria-hidden','true');overlay.dataset.built='1';
   const text=document.createElement('p');text.append(icon('docs'),'Drop to add');
   const meta=document.createElement('p');meta.className='meta';meta.textContent='PDF, text or Markdown · up to 30 files';
   overlay.append(text,meta);docs.append(overlay);
  }
  overlay.classList.add('show');docs.classList.add('over');
 };
 const hide=()=>{depth=0;docs.classList.remove('over');if(overlay?.dataset.built)overlay.remove();else overlay?.classList.remove('show');overlay=null;};
 docs.addEventListener('dragenter',e=>{if(!hasFiles(e))return;e.preventDefault();depth++;show();});
 docs.addEventListener('dragover',e=>{if(!hasFiles(e))return;e.preventDefault();e.dataTransfer.dropEffect='copy';});
 docs.addEventListener('dragleave',()=>{if(--depth<=0)hide();});
 docs.addEventListener('drop',e=>{e.preventDefault();hide();if(hasFiles(e))importDropped(e.dataTransfer.files);});
 // A file dropped anywhere else must not navigate the window.
 document.addEventListener('dragover',e=>{if(hasFiles(e)&&!docs.contains(e.target))e.preventDefault();});
 document.addEventListener('drop',e=>{if(!docs.contains(e.target))e.preventDefault();});
}
// Light markdown to DOM: headings, lists, tables, **bold** and `code`. Never innerHTML.
function inlineText(node,text){
 for(const part of text.split(/(\*\*[^*\n]+\*\*|`[^`\n]+`)/)){
  if(!part)continue;
  if(part.length>4&&part.startsWith('**')&&part.endsWith('**')){const strong=document.createElement('strong');strong.textContent=part.slice(2,-2);node.append(strong);}
  else if(part.length>2&&part.startsWith('`')&&part.endsWith('`')){const code=document.createElement('code');code.textContent=part.slice(1,-1);node.append(code);}
  else node.append(document.createTextNode(part));
 }
 return node;
}
function documentBody(text){
 const body=document.createElement('div');body.className='reference-prose';
 const lines=String(text??'').split('\n');let paragraph=[],lists=[];
 const flush=()=>{if(paragraph.length){body.append(inlineText(document.createElement('p'),paragraph.join(' ')));paragraph=[];}};
 const cells=line=>line.trim().replace(/^\||\|$/g,'').split('|').map(s=>s.trim());
 for(let i=0;i<lines.length;i++){
  const line=lines[i].trim();
  if(!line){flush();continue;}
  let next=i+1;while(next<lines.length&&!lines[next].trim())next++;
  if(line.includes('|')&&next<lines.length&&/^\|?\s*:?-{3,}/.test(lines[next].trim())){
   flush();lists=[];const table=document.createElement('table'),head=document.createElement('thead'),row=document.createElement('tr');
   for(const value of cells(line)){const th=document.createElement('th');th.scope='col';inlineText(th,value);row.append(th);}head.append(row);table.append(head);
   const rows=document.createElement('tbody');i=next;
   while(i+1<lines.length){
    if(!lines[i+1].trim()){i++;continue;}
    if(!lines[i+1].includes('|'))break;
    const row=document.createElement('tr');for(const value of cells(lines[++i]))row.append(inlineText(document.createElement('td'),value));rows.append(row);
   }
   table.append(rows);const wrap=document.createElement('div');wrap.className='reference-table';wrap.append(table);body.append(wrap);continue;
  }
  const heading=line.match(/^#{1,6}\s+(.+)/),bullet=line.match(/^([-*•]|\d+[.)])\s+(.*)/);
  if(heading){flush();lists=[];body.append(inlineText(document.createElement('h4'),heading[1]));}
  else if(bullet){
   flush();const tag=/^\d/.test(bullet[1])?'OL':'UL',indent=lines[i].match(/^\s*/)[0].length;
   while(lists.length&&(lists.at(-1).indent>indent||(lists.at(-1).indent===indent&&lists.at(-1).node.tagName!==tag)))lists.pop();
   if(!lists.length||lists.at(-1).indent<indent){
    const node=document.createElement(tag),parent=lists.at(-1)?.node.lastElementChild||body;
    parent.append(node);lists.push({indent,node});
   }
   const li=inlineText(document.createElement('li'),bullet[2]);if(tag==='OL')li.value=parseInt(bullet[1],10);lists.at(-1).node.append(li);
  }else{lists=[];paragraph.push(line);}
 }
 flush();return body;
}
function referenceSectionLabel(section){
 if(section.path?.length>2)return section.path.slice(-2).join(' · ');
 if(/^(?:PDF page |[A-Z0-9]+-\d+ · |Unit \d+, page )/.test(section.heading)){
  const title=[...section.text.matchAll(/^#### (.+)$/gm)].map(m=>m[1]).find(s=>! /^(?:Figure|Table|Appendix)\s+[A-Z0-9]/i.test(s));
  if(title)return title+' · '+section.heading;
 }
 return section.heading;
}
const setWindowTitle=text=>{document.title=text;window.jarviss.setTitle?.(text)?.catch?.(()=>{});};
const sameHeading=(a,b)=>String(a||'').toLowerCase().replace(/[^\p{L}\p{N}]+/gu,' ').trim()===String(b||'').toLowerCase().replace(/[^\p{L}\p{N}]+/gu,' ').trim();
const BOILERPLATE=/text edition|figures? (?:and visual charts |and logos )?(?:are|is) omitted|read the text here|page numbers refer to|open the illustrated pdf|not used automatically in chat/i;
function shortNote(note){return (note.match(/[^.!?]+[.!?]+(?:\s|$)/g)||[note]).map(s=>s.trim()).filter(s=>s&&!BOILERPLATE.test(s)).join(' ');}
window.shortNote=shortNote;
function openReference(id,section,heading){return openReader(()=>loadReference(id),{section,heading});}
function openDocument(title){return openReader(()=>loadDocument(title),{});}
// One reader for field documents and imported files; a file has no id, PDF or publisher.
async function openReader(load,{section,heading}){
 const sequence=++readerSequence,navigation=pageSequence,origin=document.activeElement,scroll=document.querySelector('main').scrollTop;
 const doc=await load();if(sequence!==readerSequence||navigation!==pageSequence)return;
 const imported=!doc.id,key=doc.id||'file';
 if(!$('#reference-reader').classList.contains('visible'))readerReturn={origin,scroll,page:$('.page.visible')?.id||'docs'};
 readingDocument=doc;readerJumpScroll=null;page('reference-reader');setWindowTitle(doc.title+' · JARVISS');
 $('#reference-back-label').textContent=readerReturn?.page==='assistant'?'Back to Chat':'Back to Docs'; // UI hook: label span keeps the SVG icon
 $('#reference-title').textContent=doc.title;
 $('#reference-meta').textContent=imported?`Your file · ${importedLabel(doc)}`:`${doc.publisher} · ${window.formatDate?.(doc.date,doc.date)||doc.date} · ${doc.words.toLocaleString()} words`;
 $('#reference-format').textContent=imported?'Searched when you ask JARVISS':doc.pdf?`Illustrated PDF available · Original pages ${doc.source_pages}`:'Text-only edition — figures and charts are not included.';
 $('#reference-open-pdf').hidden=$('#reference-save-pdf').hidden=$('#reference-page-pdf').hidden=!doc.pdf;
 $('#reference-save-text').textContent='Save as text';$('#reference-save-pdf').textContent='Save PDF';
 closeSectionMenu();readerSections.clear();$('#reference-section-list').replaceChildren();$('#reference-text').replaceChildren();
 for(const part of doc.sections){
  const block=document.createElement('section');block.className='reference-section';block.id='reference-'+key+'-'+part.id;block.dataset.section=part.id;block.tabIndex=-1;
  const label=referenceSectionLabel(part);
  const h3=document.createElement('h3');h3.textContent=label;
  const body=documentBody(part.text),first=body.firstElementChild;
  if(first?.tagName==='H4'&&(sameHeading(first.textContent,label)||sameHeading(first.textContent,part.heading)))first.remove(); // the section title already says it
  block.append(h3,body);$('#reference-text').append(block);
  const choice=referenceButton(label,()=>{closeSectionMenu();showReferenceSection(block);});choice.dataset.target=block.id;
  $('#reference-section-list').append(choice);readerSections.set(block.id,{block,choice,label,heading:part.heading});
 }
 // The note keeps only the document-specific cautions; the edition boilerplate is now the format line, and the full note stays under Source and edition.
 const note=imported||doc.note==='Source titles appear in each section. Use the edition and conditions shown.'?'':shortNote(doc.note||'');
 $('#reference-note').textContent=note;$('#reference-note').hidden=!note;
 $('#reference-attribution').textContent=imported?'':[doc.note&&doc.note!==note?doc.note:'',...(doc.sources||[doc.url]),doc.editing_note||'',doc.attribution||'',doc.license_note||''].filter(Boolean).join('\n\n');
 $('#reference-source').open=false;$('#reference-source').hidden=imported;
 // Saved links outlive section-id changes: fall back to the first section with the cited heading.
 const target=(section&&document.getElementById('reference-'+key+'-'+section))||(heading&&[...readerSections.values()].find(item=>item.heading===heading)?.block)||null;
 $('#reference-link-status').hidden=!(section||heading)||!!target;
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
 // A short final section cannot always reach the top. Keep an explicit jump
 // selected until the reader scrolls, so its illustrated-page button stays exact.
 readerJumpScroll=document.querySelector('main').scrollTop;
}
function closeSectionMenu(focus=false){$('#reference-section-list').hidden=true;$('#reference-contents').setAttribute('aria-expanded','false');if(focus)$('#reference-contents').focus();}
// The list hangs off #reference-picker (its offset parent), so the budget is measured from the picker's edge plus the
// stylesheet's own offset; the list must be visible first so that offset can be read.
function positionSectionMenu(){
 const list=$('#reference-section-list'),anchor=$('#reference-picker').getBoundingClientRect();
 list.classList.remove('open-above');
 const gap=Math.max(4,list.offsetTop-anchor.height)+12;
 const below=innerHeight-anchor.bottom-gap,above=anchor.top-gap,up=below<180&&above>below;
 list.classList.toggle('open-above',up);list.style.boxSizing='border-box';list.style.maxHeight=Math.min(360,Math.max(100,up?above:below))+'px'; // the limit is the outer box, padding included
}
function openSectionMenu(){
 const button=$('#reference-contents'),list=$('#reference-section-list');
 list.hidden=false;positionSectionMenu();button.setAttribute('aria-expanded','true');
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
$('#reference-picker').addEventListener('focusout',event=>{if(!$('#reference-picker').contains(event.relatedTarget))closeSectionMenu();});
document.addEventListener('click',event=>{if(!$('#reference-picker').contains(event.target))closeSectionMenu();});
window.addEventListener('resize',()=>{if(!$('#reference-section-list').hidden)positionSectionMenu();});
let readerScrollFrame;
document.querySelector('main').addEventListener('scroll',()=>{
 if(!$('#reference-section-list').hidden)positionSectionMenu();
 if(readerScrollFrame||!$('#reference-reader').classList.contains('visible'))return;
 readerScrollFrame=requestAnimationFrame(()=>{readerScrollFrame=null;let current=readerSections.keys().next().value;
  if(!$('#reference-reader').classList.contains('visible'))return;
  if(readerJumpScroll===document.querySelector('main').scrollTop)return;
  readerJumpScroll=null;
  const edge=$('.reference-jump').getBoundingClientRect().bottom+24;
  for(const [id,item] of readerSections){if(item.block.getBoundingClientRect().top<=edge)current=id;else break;}setReaderSection(current);
 });
},{passive:true});
$('#reference-back').onclick=()=>{readerSequence++;const chat=readerReturn?.page==='assistant';page(chat?'assistant':'docs');setWindowTitle((chat?'Chat':'Docs')+' · JARVISS');document.querySelector('main').scrollTop=readerReturn?.scroll||0;readerReturn?.origin?.focus({preventScroll:true});};
document.addEventListener('keydown',event=>{if(event.key==='Escape'&&$('#reference-reader').classList.contains('visible')){if(!$('#reference-section-list').hidden)closeSectionMenu(true);else $('#reference-back').click();}});
$('#reference-open-pdf').onclick=()=>window.jarviss.openReferencePDF(readingDocument.id).catch(error);
$('#reference-page-pdf').onclick=()=>window.jarviss.openReferencePDF(readingDocument.id,document.getElementById($('#reference-contents').dataset.target).dataset.section).catch(error);
// Imported files are saved from the renderer: the main process only serves catalog ids.
function saveDocumentText(doc){
 const text='# '+doc.title+'\n\n'+doc.sections.map(s=>'## '+s.heading+'\n\n'+s.text).join('\n\n')+'\n';
 const url=URL.createObjectURL(new Blob([text],{type:'text/markdown'})),link=document.createElement('a');
 link.href=url;link.download=doc.title.replace(/[\\/:*?"<>|]+/g,' ').trim()+'.md';document.body.append(link);link.click();link.remove();
 setTimeout(()=>URL.revokeObjectURL(url),60000);return true;
}
for(const [selector,format,label] of [['#reference-save-text','md','Saved as text'],['#reference-save-pdf','pdf','PDF saved']]){
 $(selector).onclick=async()=>{const doc=readingDocument;try{const saved=doc.id?await window.jarviss.saveReference(doc.id,format):saveDocumentText(doc);if(saved)queueToast(label);}catch(e){error(e);}};
}
$('#reference-ask').onclick=()=>askDocument(readingDocument.title);
function resultGroup(label,nodes){
 const group=document.createElement('section');group.className='result-group';
 const heading=document.createElement('h4');heading.className='eyebrow';heading.textContent=`${label} (${nodes.length})`;
 group.append(heading,...nodes);return group;
}
function filterDocs(){
 const q=$('#docs-search').value.trim().toLowerCase(),sequence=++referenceSearch,pdfs=$('#reference-pdfs').getAttribute('aria-pressed')==='true';
 for(const id of ['documents','documents-heading','guides','guides-heading'])$('#'+id).hidden=!!q||pdfs; // UI hook: the situation card now lives in the chat inspector
 $('#docs-cap').hidden=!!q||pdfs||(state.documents||[]).length<DOC_LIMIT-3;
 $('.recovery-entry').hidden=!!q||pdfs;
 $('#field-library-heading').hidden=!!q;
 for(const item of referenceEntries.values())item.entry.hidden=pdfs&&!item.doc.pdf;
 clearTimeout(referenceTimer);$('#references').hidden=!!q;$('#reference-results').hidden=!q;
 if(!q){
  const illustrated=[...referenceEntries.values()].filter(item=>item.doc.pdf).length;
  $('#reference-summary').textContent=pdfs?`Showing ${illustrated} illustrated PDF${illustrated===1?'':'s'} · text-only field documents, your files and guides are hidden`:$('#reference-summary').dataset.fullSummary;
  $('#reference-results').replaceChildren();return;
 }
 $('#reference-summary').textContent='Searching documents…';
 const local=[];
 if(!pdfs){
  const files=(state.documents||[]).filter(d=>d.title.toLowerCase().includes(q)).map(documentCard);
  if(files.length)local.push(resultGroup('Your files',files));
  const guides=(state.guides||[]).filter(g=>`${g.title} ${g.keywords||''} ${g.text||''}`.toLowerCase().includes(q)).map(guideEntry);
  if(('Regroup and rebuild '+(state.recovery||'')).toLowerCase().includes(q))guides.push(recoveryEntry());
  if(guides.length)local.push(resultGroup('Using JARVISS',guides));
 }
 const localCount=local.reduce((n,group)=>n+group.children.length-1,0);
 const searching=document.createElement('p');searching.className='meta';searching.textContent='Searching field library…';
 $('#reference-results').replaceChildren(...local,searching);
 const clearSearch=()=>{$('#docs-search').value='';filterDocs();$('#docs-search').focus();};
 referenceTimer=setTimeout(async()=>{
  try{const results=await window.jarviss.command('reference_search',{query:q});if(sequence!==referenceSearch)return;
   const matching=results.filter(ref=>!pdfs||referenceEntries.get(ref.id)?.doc.pdf);
   const count=localCount+new Set(matching.map(ref=>ref.id)).size;
   $('#reference-summary').textContent=`${count} matching document${count===1?'':'s'}`;
   const nodes=matching.map(ref=>{const b=referenceButton(ref.title+' · '+ref.heading,()=>openReference(ref.id,ref.section,ref.heading));b.className='reference-result';return b;});
   const groups=[...local];if(nodes.length)groups.push(resultGroup('Field library',nodes));
   if(!groups.length){
    const empty=document.createElement('div');empty.className='empty';const text=document.createElement('p');text.textContent='No matching documents.';
    const clear=document.createElement('button');clear.className='compact';clear.textContent='Clear search';clear.onclick=clearSearch;empty.append(text,clear);groups.push(empty);
   }
   $('#reference-results').replaceChildren(...groups);
  }catch(e){
   if(sequence!==referenceSearch)return;
   $('#reference-summary').textContent='Field library search incomplete';
   const message=document.createElement('p');message.textContent='Search could not finish.';
   $('#reference-results').replaceChildren(...local,message,referenceButton('Try search again',()=>filterDocs()));
  }
 },180);
}
$('#docs-search').oninput=filterDocs;
$('#reference-pdfs').onclick=()=>{const button=$('#reference-pdfs');button.setAttribute('aria-pressed',String(button.getAttribute('aria-pressed')!=='true'));filterDocs();};
Object.assign(window,{renderDocuments,renderLibrary:()=>renderDocuments(state),filterDocs,documentBody,openDocument,openReference,importDropped});
