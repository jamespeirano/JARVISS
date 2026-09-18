// Real offline references through Electron, including actual PDF windows.
const {_electron:electron}=require('playwright');
const {expect}=require('playwright/test');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path'),assert=require('node:assert/strict');
(async()=>{
 const root=path.resolve(__dirname,'../..'),test=fs.mkdtempSync(path.join(os.tmpdir(),'jarviss reader ü-'));
 const catalog=JSON.parse(fs.readFileSync(path.join(root,'resources/references/catalog.json')));
 let app;
 try{
  fs.symlinkSync(path.join(root,'.venv'),path.join(test,'.venv'),process.platform==='win32'?'junction':'dir');
  fs.cpSync(path.join(root,'resources'),path.join(test,'resources'),{recursive:true});
  fs.writeFileSync(path.join(test,'service.py'),`import sys,time,urllib.request
sys.path.insert(0,${JSON.stringify(root)})
from jarviss import service
from jarviss.storage import ROOT
def offline(*args,**kwargs):raise AssertionError('Network forbidden')
urllib.request.urlopen=offline
OriginalService=service.Service
class TestService(OriginalService):
 def command(self,method,args=None):
  args=args or {}
  if method=='reference_search' and (ROOT/'fail-search').exists():raise ValueError('Search interrupted. Try again.')
  if method=='reference':
   ident=args.get('id','')
   if (ROOT/('fail-'+ident)).exists():raise ValueError('The document could not be read. Try again.')
   if (ROOT/('hold-'+ident)).exists():
    (ROOT/('started-'+ident)).touch()
    while (ROOT/('hold-'+ident)).exists():time.sleep(.02)
  return super().command(method,args)
service.Service=TestService
service.main()
`);
  const env={...process.env,JARVISS_ROOT:test,JARVISS_DATA:path.join(test,'data'),JARVISS_APP_DATA:path.join(test,'app')};delete env.ELECTRON_RUN_AS_NODE;
  app=await electron.launch({args:[path.join(root,'electron')],env});const page=await app.firstWindow();
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await app.evaluate(({session})=>{
   globalThis.readerExternalRequests=[];
   session.defaultSession.webRequest.onBeforeRequest((request,done)=>{
    if(/^https?:/.test(request.url)){globalThis.readerExternalRequests.push(request.url);done({cancel:true});}else done({});
   });
  });
  const touch=name=>fs.writeFileSync(path.join(test,name),'');
  const remove=name=>fs.rmSync(path.join(test,name),{force:true});
  const row=id=>page.locator(`[data-reference="${id}"]`);
  const read=id=>row(id).locator('.doc-row-main').click(); // the row itself opens the document
  const mediumDate=d=>page.evaluate(iso=>new Intl.DateTimeFormat(undefined,{dateStyle:'medium'}).format(new Date(iso)),d.toISOString());
  const waitReader=title=>page.waitForFunction(title=>document.querySelector('#reference-reader').classList.contains('visible')&&document.querySelector('#reference-title').textContent===title,title);
  const back=()=>page.locator('#reference-back').click();
  const words=text=>(text.match(/[\p{L}\p{N}]+/gu)||[]).join(' ');
  await page.locator('#setup-later').click();await page.locator('[data-page="docs"]').click();
  assert.equal(await page.locator('#references .doc-row').count(),38);
  assert.equal(await page.getByRole('button',{name:'Open illustrated PDF',exact:true}).count(),3); // Only the three available PDF rows are exposed.
  assert.match(await page.locator('#references .doc-row .meta').first().innerText(),/^[^·]+ · [\d,]+ words$/,'Row meta is topic · words');
  assert.equal(await page.locator('#reference-pdfs').innerText(),'With illustrations (3)');
  if(process.env.JARVISS_UX_SCREENSHOTS)fs.mkdirSync(process.env.JARVISS_UX_SCREENSHOTS,{recursive:true});
  // Every bundled document is complete, readable, and browsable without a model.
  for(const entry of catalog){
   await read(entry.id);await waitReader(entry.title);
   const doc=await page.evaluate(id=>window.jarviss.command('reference',{id}),entry.id);
   assert.equal(await page.locator('#reference-text > section').count(),doc.sections.length);
   assert.equal(await page.locator('#reference-section-list button').count(),doc.sections.length);
   assert.equal(await page.locator('#reference-open-pdf').isVisible(),!!entry.pdf);
   assert.equal(await page.locator('#reference-save-pdf').isVisible(),!!entry.pdf);
   const labels=await page.locator('#reference-text > section > h3').allInnerTexts();
   for(let i=0;i<doc.sections.length;i++){
    // The reader drops a leading sub-heading that only repeats the section title; everything else must survive.
    let text=doc.sections[i].text.trimStart();const repeated=/^#{1,6}[ \t]+(.+)/.exec(text);
    if(repeated&&(words(repeated[1]).toLowerCase()===words(labels[i]).toLowerCase()||words(repeated[1]).toLowerCase()===words(doc.sections[i].heading).toLowerCase()))text=text.slice(repeated[0].length);
    const source=text.replace(/^\s*(?:[-*•]|\d+[.)])[ \t]+/gm,'');
    const shown=await page.locator('#reference-text .reference-prose').nth(i).innerText();
    assert.equal(words(shown),words(source),`${entry.id}: all words and quantities must survive formatting (${doc.sections[i].heading})`);
   }
   assert.equal(await page.locator('#reference-text h4').evaluateAll((hs,labels)=>hs.filter(h=>h.previousElementSibling===null&&labels.includes(h.textContent)).length,labels),0,'No sub-heading repeats its section title');
   assert.equal(await page.locator('#reference-text details').count(),0,'No collapsed advice');
   // A page cited only by number takes its first sub-heading as the jump-menu title.
   for(const [id,heading,title] of [['army-navigation','7-3 · PDF page 155','Desert Movement'],['army-shelter','6-2 · PDF page 136','SHELTER CONSIDERATIONS']]){
    if(entry.id!==id)continue;
    const bare=doc.sections.find(s=>s.heading===heading);assert.ok(bare,`${id} still has ${heading}`);
    assert.equal(await page.locator(`#reference-section-list button[data-target="reference-${id}-${bare.id}"]`).textContent(),`${title} · ${heading}`);
   }
   if(process.env.JARVISS_UX_SCREENSHOTS&&['fda-food-flood','cdc-respirators','fema-preparedness','cert-4'].includes(entry.id)){
    const target=entry.id==='cert-4'?doc.sections.find(s=>s.text.includes('1. Head;')):entry.id==='fema-preparedness'?doc.sections.find(s=>s.heading==='PDF page 10'):null;
    if(target)await page.evaluate(({id,section})=>openReference(id,section),{id:entry.id,section:target.id});
    await page.screenshot({path:path.join(process.env.JARVISS_UX_SCREENSHOTS,entry.id+'-text.png')});
   }
   await back();
  }
  console.log('PASS all 38 full documents: complete text and quantities, sections, format labels, and PDF availability; no model or internet');
  const formatting=await page.evaluate(()=>{
   const body=documentBody('3. Keep 2 litres.\n\n4. Wait 30 minutes.\n\n9. Check again.');
   const nested=documentBody('• Main step\n  - First part\n  - Second part\n• Next step');
   return {numbers:[...body.querySelectorAll('li')].map(el=>el.value),nested:nested.querySelectorAll('ul>li>ul>li').length,top:nested.querySelectorAll(':scope>ul>li').length,label:referenceSectionLabel({heading:'A-5 · PDF page 199',text:'#### Figure-eight knot\n\nSteps.'})};
  });
  assert.deepEqual(formatting.numbers,[3,4,9]);assert.match(formatting.label,/^Figure-eight knot/);
  assert.equal(formatting.nested,2);assert.equal(formatting.top,2);
  const last=catalog.at(-1);await row(last.id).scrollIntoViewIfNeeded();
  const libraryScroll=await page.locator('main').evaluate(el=>el.scrollTop);
  await read(last.id);await waitReader(last.title);await back();
  assert.equal(await page.locator('main').evaluate(el=>el.scrollTop),libraryScroll,'Back must restore a scrolled library');
  assert.equal(await row(last.id).locator('.doc-row-main').evaluate(el=>el===document.activeElement),true);
  await read('fda-food-flood');await waitReader('Food and water after storms');
  assert.equal(await page.locator('#reference-text > section').count(),3);
  assert.equal(await page.locator('#reference-format').innerText(),'Text-only edition — figures and charts are not included.');
  assert.match(await page.locator('#reference-meta').innerText(),/^.+ · .+ · [\d,]+ words$/);
  assert.equal(await page.locator('#reference-save-text').innerText(),'Save as text');
  // The reader note keeps the document's own cautions and drops edition boilerplate, which now lives under Source and edition.
  const noteCheck=await page.evaluate(()=>shortNote('Great Lakes regional guide. Planting dates and growing conditions are regional, not nationwide. Text edition; figures and visual charts are omitted. Read the text here; answers use the reviewed field-guide sections to keep tables and qualifications together.'));
  assert.equal(noteCheck,'Great Lakes regional guide. Planting dates and growing conditions are regional, not nationwide.');
  assert.doesNotMatch(await page.locator('#reference-text').innerText(),/WATCH|1-888|Questions\?|Get Assistance|Links for|Ask about this/);
  await page.locator('#reference-contents').click();
  await page.locator('#reference-section-list').getByRole('button',{name:'After a Storm',exact:true}).click();
  await page.locator('.reference-selected').filter({hasText:'When in doubt, throw it out.'}).waitFor();
  const position=await page.locator('.reference-selected').evaluate(el=>({top:el.getBoundingClientRect().top,bar:document.querySelector('.reference-jump').getBoundingClientRect().bottom}));
  assert.ok(position.top>=position.bar,'Jump target must stay below the sticky section picker');
  await page.locator('#reference-ask').click();
  assert.equal(await page.locator('#question').inputValue(),'Using the document "Food and water after storms", ');
  await page.locator('[data-page="docs"]').click();
  // A search applies to the entire library, including user imports.
  await page.evaluate(async()=>{await call('import_note',{title:'Zentro G40 manual',text:'E04 means the oil level must be checked before restarting.'});await refresh();});
  await page.locator('#docs-search').fill('zentro');
  await expect(page.locator('#reference-results')).not.toContainText('Searching');
  await expect(page.locator('#reference-results')).toContainText('Zentro G40 manual');
  await expect(page.locator('#reference-summary')).toHaveText('1 matching document');
  assert.equal(await page.locator('#references .doc-row:visible').count(),0,'No unrelated field documents during search');
  assert.equal(await page.getByText('No matching documents.',{exact:true}).isVisible(),false);
  assert.equal(await page.locator('#documents').isVisible(),false);
  assert.equal((await page.locator('#reference-results .result-group h4').first().evaluate(el=>el.textContent)),'Your files (1)');
  if(process.env.JARVISS_UX_SCREENSHOTS)await page.screenshot({path:path.join(process.env.JARVISS_UX_SCREENSHOTS,'import-search.png')});
  await page.locator('#reference-results .doc-row.mine .doc-row-main').click();await waitReader('Zentro G40 manual');
  assert.match(await page.locator('#reference-text').innerText(),/E04 means the oil level/);await back();
  await page.locator('#reference-pdfs').click();
  await page.getByText('No matching documents.',{exact:true}).waitFor();
  assert.equal(await page.locator('#reference-results .doc-row.mine').count(),0,'PDF-only search excludes text imports');
  await page.getByRole('button',{name:'Clear search',exact:true}).click();
  assert.equal(await page.locator('#docs-search').inputValue(),'');assert.equal(await page.locator('#docs-search').evaluate(el=>el===document.activeElement),true);
  assert.match(await page.locator('#reference-summary').innerText(),/^Showing 3 illustrated PDFs · .*hidden$/);
  await page.locator('#reference-pdfs').click();await page.locator('#docs-search').fill('zentro');
  await expect(page.locator('#reference-results')).toContainText('Zentro G40 manual');
  await page.locator('#docs-search').fill('');
  assert.equal(await page.locator('#references .doc-row:visible').count(),38);
  assert.equal(await page.locator('#documents .doc-row.mine:visible').count(),1);
  await page.locator('#docs-search').fill('bowline');
  const result=page.locator('#reference-results button').filter({hasText:'Knots, rope and lashings'}).first();
  await result.click();await waitReader('Knots, rope and lashings');
  assert.match(await page.locator('.reference-selected').innerText(),/bowline/i);
  assert.equal(await page.locator('#reference-link-status').isVisible(),false);
  await back();assert.equal(await page.locator('#docs-search').inputValue(),'bowline');
  assert.equal(await result.evaluate(el=>el===document.activeElement),true);
  await page.locator('#docs-search').fill('zzqxy77');
  await page.getByText('No matching documents.',{exact:true}).waitFor();
  await page.locator('#docs-search').fill('');await page.locator('#reference-pdfs').click();
  assert.equal(await page.locator('#references .doc-row:visible').count(),3);
  await page.locator('#docs-search').fill('insulin');
  await page.getByText('No matching documents.',{exact:true}).waitFor();
  await page.locator('#reference-pdfs').click();
  await page.locator('#reference-results button').filter({hasText:'Insulin'}).first().waitFor();
  await page.locator('#docs-search').fill('');
  touch('fail-search');await page.locator('#docs-search').fill('water');
  await page.getByText('Search could not finish.',{exact:true}).waitFor();remove('fail-search');
  await page.getByRole('button',{name:'Try search again',exact:true}).click();
  await page.locator('#reference-results button').filter({hasText:'Drinking water'}).first().waitFor();
  await page.locator('#docs-search').fill('');
  console.log('PASS usable FDA sections, section jumps, Ask JARVISS, preserved search/back/focus, empty results and PDF filtering');
  // The actual offline Chromium PDF viewer must open at the cited excerpt page.
  for(const id of ['army-rope','army-navigation','army-shelter']){
   const doc=await page.evaluate(id=>window.jarviss.command('reference',{id}),id);
   const section=doc.sections[Math.floor(doc.sections.length/2)];
   await page.evaluate(({id,section})=>openReference(id,section),{id,section:section.id});
   const original=Number(section.heading.match(/PDF page (\d+)/)[1]),first=Number(doc.source_pages.split('–')[0]);
   await page.locator('#reference-page-pdf').click();
   await page.waitForFunction(()=>document.querySelector('#error').hidden);
   let viewer;
   for(let i=0;i<100;i++){
    viewer=app.windows().find(w=>w!==page&&w.url().includes(doc.pdf)&&w.url().includes(`page=${original-first+2}`));
    if(viewer)break;await new Promise(resolve=>setTimeout(resolve,50));
   }
   assert.ok(viewer,`${id} must open its real local PDF at the referenced page`);
   assert.ok(viewer.url().startsWith('file:'));
   const pdfFrame=viewer.frames().find(f=>f.url().startsWith('chrome-extension:'))||await viewer.waitForEvent('framenavigated',{predicate:f=>f.url().startsWith('chrome-extension:')});
   await expect(pdfFrame.getByRole('textbox',{name:'Page number',exact:true})).toHaveValue(String(original-first+2),{timeout:20000});
   if(process.env.JARVISS_UX_SCREENSHOTS){
    fs.mkdirSync(process.env.JARVISS_UX_SCREENSHOTS,{recursive:true});
    await viewer.screenshot({path:path.join(process.env.JARVISS_UX_SCREENSHOTS,id+'.png')});
   }
   await viewer.close();
   await page.locator('#reference-open-pdf').click();
   await expect.poll(()=>app.windows().some(w=>w!==page&&w.url().includes(doc.pdf)&&w.url().includes('#page=1&view=FitH'))).toBe(true);
   viewer=app.windows().find(w=>w!==page&&w.url().includes(doc.pdf));
   const coverFrame=viewer.frames().find(f=>f.url().startsWith('chrome-extension:'))||await viewer.waitForEvent('framenavigated',{predicate:f=>f.url().startsWith('chrome-extension:')});
   await expect(coverFrame.getByRole('textbox',{name:'Page number',exact:true})).toHaveValue('1');
   // Reuse the same viewer at both ends of the excerpt, including its cover offset.
   for(const edge of [doc.sections[0],doc.sections.at(-1)]){
    const expected=Number(edge.heading.match(/PDF page (\d+)/)[1])-first+2;
    await page.evaluate(({id,section})=>openReference(id,section),{id,section:edge.id});
    await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
    assert.equal(await page.locator('#reference-contents').getAttribute('data-target'),`reference-${id}-${edge.id}`,'A short final section must stay selected after jumping');
    await page.locator('#reference-page-pdf').click();
    await expect.poll(()=>viewer.url()).toContain(`#page=${expected}&view=FitH`);
    const frame=viewer.frames().find(f=>f.url().startsWith('chrome-extension:'))||await viewer.waitForEvent('framenavigated',{predicate:f=>f.url().startsWith('chrome-extension:')});
    await expect(frame.getByRole('textbox',{name:'Page number',exact:true})).toHaveValue(String(expected),{timeout:20000});
   }
   await viewer.close();await back();
  }
  const competing=await page.evaluate(()=>Promise.allSettled(['army-shelter','army-rope','army-navigation'].map(id=>window.jarviss.openReferencePDF(id))));
  assert.ok(competing.every(r=>r.status==='fulfilled'),'Rapid PDF requests must not produce aborted-load errors');
  const latestViewer=app.windows().find(w=>w!==page);
  assert.equal(app.windows().length,2,'Reuse one document window');
  assert.match(latestViewer.url(),/army-navigation\.pdf\?view=\d+#page=1&view=FitH/);
  await latestViewer.close();
  console.log('PASS three real offline PDFs, first/middle/last cited pages, cover opening, close/reopen and rapid requests');
  // Stale saved citation remains understandable, and untrusted text stays literal.
  const water=await page.evaluate(()=>window.jarviss.command('reference',{id:'field-water'})),cited=water.sections[1];
  await page.evaluate(heading=>openReference('field-water','removed-section',heading),cited.heading);
  await page.locator('.reference-selected').waitFor();
  assert.equal(await page.locator('.reference-selected').getAttribute('data-section'),cited.id,'A stale section id must fall back to the cited heading');
  assert.equal(await page.locator('#reference-link-status').isVisible(),false);
  await page.evaluate(()=>openReference('field-water','removed-section','No such heading'));
  assert.equal(await page.locator('#reference-link-status').isVisible(),true);
  assert.ok(await page.locator('#reference-text > section').count());
  const escaped=await page.evaluate(()=>{
   const body=documentBody('<script>window.readerInjected=true</script>\n\n<img src=x onerror=alert(1)>');
   document.querySelector('#reference-text').append(body);
   return {text:body.textContent,htmlElements:body.querySelectorAll('script,img').length,injected:!!window.readerInjected};
  });
  assert.equal(escaped.htmlElements,0);assert.equal(escaped.injected,false);assert.match(escaped.text,/<script>/);
  await back();
  // Real missing file, safe path rejection, failed read/retry, and cancellation.
  const pdf=path.join(test,'resources/references/army-rope.pdf'),backup=pdf+'.temporarily-hidden';fs.renameSync(pdf,backup);
  await row('army-rope').getByRole('button',{name:'Open illustrated PDF',exact:true}).click();
  await page.getByRole('alert').filter({hasText:'PDF is missing'}).waitFor();fs.renameSync(backup,pdf);
  assert.match(await page.evaluate(()=>window.jarviss.openReferencePDF('../private').catch(e=>e.message)),/not in the installed library/);
  assert.match(await page.evaluate(()=>window.jarviss.openReferencePDF('army-rope','wrong-section').catch(e=>e.message)),/not in the document/);
  await app.evaluate(({dialog})=>{dialog.showSaveDialog=async()=>({canceled:true});});
  assert.equal(await page.evaluate(()=>window.jarviss.saveReference('army-rope','pdf')),false);
  // Reset renderer cache so failures reach the real backend again.
  await page.reload();await page.locator('#setup-later').click();await page.locator('[data-page="docs"]').click();
  touch('fail-field-water');await read('field-water');await page.getByRole('alert').filter({hasText:'could not be read'}).waitFor();
  assert.equal(await page.locator('#docs').isVisible(),true);
  remove('fail-field-water');await read('field-water');await waitReader('Drinking water');
  assert.equal(await page.locator('#error').isVisible(),false);await back();
  touch('hold-field-food');await read('field-food');
  await page.locator('[data-page="plan"]').click();remove('hold-field-food');
  await page.waitForTimeout(300);assert.equal(await page.locator('#plan').isVisible(),true,'Late document must not pull user away from another page');
  await page.locator('[data-page="docs"]').click();
  touch('hold-field-power');await read('field-power');await read('field-team');
  await waitReader('Working together after a disaster');remove('hold-field-power');
  await page.waitForTimeout(300);assert.equal(await page.locator('#reference-title').innerText(),'Working together after a disaster');
  console.log('PASS stale citations, literal HTML, missing PDF, invalid paths/sections, cancel, read failure/retry, and late/reordered navigation');
  // Keyboard and resized windows, including larger text, must retain usable controls.
  for(const size of [{width:1024,height:720},{width:1440,height:940}]){
   await page.setViewportSize(size);
   for(const zoom of [1,1.25,1.5]){
    await app.evaluate(({BrowserWindow},zoom)=>BrowserWindow.getAllWindows()[0].webContents.setZoomFactor(zoom),zoom);
    await page.evaluate(()=>openReference('army-rope'));
    assert.equal(await page.locator('#reference-title').evaluate(el=>el===document.activeElement),true);
    await page.bringToFront();await page.locator('#reference-contents').focus();await page.keyboard.press('Enter');
    await expect(page.locator('#reference-section-list')).toBeVisible();
    const menu=await page.locator('#reference-section-list').evaluate(el=>{const r=el.getBoundingClientRect();return {top:r.top,bottom:r.bottom,height:innerHeight};});
    assert.ok(menu.top>=0&&menu.bottom<=menu.height,`Section menu must stay in the viewport: ${JSON.stringify(menu)}`);
    if(process.env.JARVISS_UX_SCREENSHOTS)await page.screenshot({path:path.join(process.env.JARVISS_UX_SCREENSHOTS,`menu-${size.width}-${zoom}.png`)});
    await page.keyboard.press('Escape');assert.equal(await page.locator('#reference-reader').isVisible(),true,`Escape closes only menu at ${size.width}, zoom ${zoom}`);
    assert.equal(await page.locator('#reference-contents').evaluate(el=>el===document.activeElement),true);
    await page.keyboard.press('Enter');await page.locator('#reference-page-pdf').focus();
    assert.equal(await page.locator('#reference-section-list').isVisible(),false,'Leaving the picker closes its menu');
    await page.locator('#reference-contents').focus();
    await page.keyboard.press('Enter');await page.keyboard.press('End');await page.keyboard.press('Enter');
    await page.waitForFunction(()=>document.querySelector('.reference-selected'));
    const layout=await page.evaluate(()=>{
     const main=document.querySelector('main'),select=document.querySelector('#reference-contents').getBoundingClientRect();
     return {overflow:main.scrollWidth>main.clientWidth,selectWidth:select.width};
    });
    assert.equal(layout.overflow,false,`No horizontal page overflow at ${size.width}, zoom ${zoom}`);
    assert.ok(layout.selectWidth>=160,'Section picker must remain usable');
    if(process.env.JARVISS_UX_SCREENSHOTS)await page.screenshot({path:path.join(process.env.JARVISS_UX_SCREENSHOTS,`reader-${size.width}-${zoom}.png`)});
   }
  }
  assert.deepEqual(errors,[]);assert.deepEqual(await app.evaluate(()=>globalThis.readerExternalRequests),[]);
  console.log('PASS keyboard, anchored menu bounds, 1024/1440 windows, 100/125/150% zoom, no script errors or external requests');
  // Your files: imported documents open in the same reader, rename inline, remove in two steps, arrive by drop, and stop at the cap.
  await page.setViewportSize({width:1280,height:900});await app.evaluate(({BrowserWindow})=>BrowserWindow.getAllWindows()[0].webContents.setZoomFactor(1));
  await back();await page.locator('[data-page="docs"]').click();
  await page.evaluate(async()=>{await call('import_note',{title:'Pump TP1 manual',text:'# Start-up\n\nE04: **Intake obstruction**. Switch off and check the `filter`.\n\n| Code | Meaning |\n|---|---|\n| E04 | Intake |\n\n## Storage\n\n1. Drain.\n2. Cover.'});await refresh();});
  const fileCard=title=>page.locator('#documents .doc-row.mine').filter({has:page.locator('.doc-title',{hasText:title})});
  const today=await mediumDate(new Date()),pumpWords=(await page.evaluate(()=>window.jarviss.command('state'))).documents.find(d=>d.title==='Pump TP1 manual').words;
  assert.equal(await fileCard('Pump TP1 manual').locator('.meta').innerText(),`Imported ${today} · ${pumpWords} words`,'Import dates read as medium dates');
  assert.deepEqual(await fileCard('Pump TP1 manual').locator('.doc-row-actions button').allInnerTexts(),['Rename','Remove'],'Your-files rows carry compact Rename and Remove');
  await fileCard('Pump TP1 manual').locator('.doc-row-main').click();await waitReader('Pump TP1 manual');
  assert.equal(await page.locator('#reference-text > section').count(),2);assert.equal(await page.locator('#reference-section-list button').count(),2);
  for(const id of ['#reference-open-pdf','#reference-save-pdf','#reference-page-pdf','#reference-source'])assert.equal(await page.locator(id).isVisible(),false,id+' is not offered for an imported file');
  assert.equal(await page.locator('#reference-text strong').first().innerText(),'Intake obstruction');assert.equal(await page.locator('#reference-text code').first().innerText(),'filter');
  assert.equal(await page.locator('#reference-text table td').first().innerText(),'E04');assert.equal(await page.locator('#reference-text ol li').count(),2);
  assert.equal(await page.locator('#reference-meta').innerText(),`Your file · Imported ${today} · ${pumpWords} words`);
  assert.equal(await page.locator('#reference-format').innerText(),'Searched when you ask JARVISS');
  assert.equal(await page.evaluate(()=>document.title),'Pump TP1 manual · JARVISS');assert.equal(await app.evaluate(({BrowserWindow})=>BrowserWindow.getAllWindows()[0].getTitle()),'Pump TP1 manual · JARVISS');
  assert.equal(await page.locator('#reference-title').evaluate(el=>el===document.activeElement),true);
  await app.evaluate(({session})=>{globalThis.savedDownloads=[];session.defaultSession.once('will-download',(event,item)=>{globalThis.savedDownloads.push(item.getFilename());item.cancel();});});
  await page.locator('#reference-save-text').click();
  await expect.poll(()=>app.evaluate(()=>globalThis.savedDownloads)).toEqual(['Pump TP1 manual.md']);
  await expect(page.locator('#toast')).toHaveText('Saved as text');assert.equal(await page.locator('#reference-save-text').innerText(),'Save as text','The button keeps its label; the toast is the feedback');
  await page.locator('#reference-ask').click();assert.equal(await page.locator('#question').inputValue(),'Using the document "Pump TP1 manual", ');
  await page.locator('[data-page="docs"]').click();assert.equal(await page.evaluate(()=>document.title),'Docs · JARVISS');
  await fileCard('Pump TP1 manual').getByRole('button',{name:'Rename',exact:true}).click();
  const renameBox=page.locator('#documents .rename-form input');assert.equal(await renameBox.evaluate(el=>el===document.activeElement),true);
  await page.keyboard.press('Escape');assert.equal(await page.locator('#documents .rename-form').count(),0);
  assert.equal(await fileCard('Pump TP1 manual').getByRole('button',{name:'Rename',exact:true}).evaluate(el=>el===document.activeElement),true,'Escape returns focus to Rename');
  await fileCard('Pump TP1 manual').getByRole('button',{name:'Rename',exact:true}).click();await renameBox.fill('Pump TP1 handbook');await page.keyboard.press('Enter');
  await fileCard('Pump TP1 handbook').waitFor();assert.equal(await fileCard('Pump TP1 manual').count(),0);
  await expect(page.locator('#toast')).toHaveText('Renamed to "Pump TP1 handbook"');
  assert.equal(await fileCard('Pump TP1 handbook').getByRole('button',{name:'Rename',exact:true}).evaluate(el=>el===document.activeElement),true,'Focus follows the renamed file');
  assert.equal(await page.evaluate(()=>window.jarviss.command('library_rename',{title:'Pump TP1 handbook',new_title:'Zentro G40 manual'}).catch(e=>e.message)).then(m=>/already has that name/.test(m)),true);
  await fileCard('Zentro G40 manual').getByRole('button',{name:'Remove',exact:true}).click();
  const confirmBox=fileCard('Zentro G40 manual').locator('.confirm');await expect(confirmBox).toContainText('Remove this file?');
  assert.equal(await confirmBox.getByRole('button',{name:'Yes',exact:true}).evaluate(el=>el===document.activeElement),true);
  await page.keyboard.press('Escape');assert.equal(await confirmBox.count(),0);
  assert.equal(await fileCard('Zentro G40 manual').getByRole('button',{name:'Remove',exact:true}).evaluate(el=>el===document.activeElement),true,'No/Escape restores the Remove button and its focus');
  await fileCard('Zentro G40 manual').getByRole('button',{name:'Remove',exact:true}).click();await confirmBox.getByRole('button',{name:'Yes',exact:true}).click();
  await expect(fileCard('Zentro G40 manual')).toHaveCount(0);await expect(page.locator('#toast')).toHaveText('Removed "Zentro G40 manual"');
  assert.equal(await fileCard('Pump TP1 handbook').getByRole('button',{name:'Remove',exact:true}).evaluate(el=>el===document.activeElement),true,'Focus moves to the neighbouring file');
  assert.equal((await page.evaluate(()=>window.jarviss.command('state'))).documents.length,1);
  // Dropped files travel through the preload path bridge; a bad PDF reports its own error and a stray .exe is ignored.
  fs.writeFileSync(path.join(test,'Pump notes.txt'),'Pump primer: bleed the line before starting.');fs.writeFileSync(path.join(test,'broken.pdf'),'not a pdf');fs.writeFileSync(path.join(test,'setup.exe'),'');
  await page.evaluate(()=>{const input=document.createElement('input');input.type='file';input.multiple=true;input.id='drop-probe';input.hidden=true;document.body.append(input);});
  await page.locator('#drop-probe').setInputFiles(['Pump notes.txt','broken.pdf','setup.exe'].map(name=>path.join(test,name)));
  await page.evaluate(()=>{const files=document.querySelector('#drop-probe').files,transfer=new DataTransfer();for(const file of files)transfer.items.add(file);
   const zone=document.querySelector('#docs');zone.dispatchEvent(new DragEvent('dragenter',{dataTransfer:transfer,bubbles:true}));zone.dispatchEvent(new DragEvent('dragover',{dataTransfer:transfer,bubbles:true,cancelable:true}));
   const overlay=zone.querySelector(':scope > .drop-overlay');window.dropProbeOver=zone.classList.contains('over')&&!!overlay&&getComputedStyle(overlay).display!=='none';zone.dispatchEvent(new DragEvent('drop',{dataTransfer:transfer,bubbles:true,cancelable:true}));});
  assert.equal(await page.evaluate(()=>window.dropProbeOver),true,'Dragging files over the Docs page shows the drop overlay');assert.equal(await page.evaluate(()=>document.querySelector('#docs').classList.contains('over')||[...document.querySelectorAll('#docs > .drop-overlay')].some(o=>getComputedStyle(o).display!=='none')),false,'The overlay leaves on drop');
  await expect(page.locator('#toast')).toHaveText('Added "Pump notes.txt"');await fileCard('Pump notes.txt').waitFor();
  await expect(page.locator('#toast')).toHaveText(/^broken\.pdf: /,{timeout:5000});
  assert.equal(await page.locator('#documents .doc-row.mine').count(),2);assert.equal(await page.locator('#docs-cap').isVisible(),false);
  for(let n=3;n<=30;n++)await page.evaluate(n=>call('import_note',{title:'Note '+n,text:'Filler text '+n}),n);
  await page.evaluate(()=>refresh());await expect(page.locator('#docs-cap')).toHaveText('30 of 30 files used — remove one to add more');
  assert.match(await page.evaluate(()=>window.jarviss.command('import_note',{title:'Note 31',text:'x'}).catch(e=>e.message)),/reached 30/);
  await fileCard('Note 30').getByRole('button',{name:'Remove',exact:true}).click();await fileCard('Note 30').locator('.confirm').getByRole('button',{name:'Yes',exact:true}).click();
  await expect(page.locator('#docs-cap')).toHaveText('29 of 30 files used — remove one to add more');
  for(const n of [29,28,27])await page.evaluate(n=>call('library_delete',{title:'Note '+n}),n);
  await page.evaluate(()=>refresh());await expect(page.locator('#docs-cap')).toBeHidden();assert.equal(await page.locator('#documents .doc-row.mine').count(),26);
  await page.locator('#docs-search').fill('note');await expect(page.locator('#docs-cap')).toBeHidden();await page.locator('#docs-search').fill('');
  assert.deepEqual(errors,[]);
  console.log('PASS imported files: reader, inline bold/code/tables, window title, save, rename, two-step remove, drop-overlay import and the 30-file cap');
 }finally{
  for(const name of fs.readdirSync(test).filter(n=>n.startsWith('hold-')))fs.rmSync(path.join(test,name));
  if(app)await app.close();fs.rmSync(test,{recursive:true,force:true});
 }
})().catch(e=>{console.error(e);process.exitCode=1;});
