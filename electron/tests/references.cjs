// Real offline references through Electron, including actual PDF windows.
const {_electron:electron}=require('playwright');
const {expect}=require('playwright/test');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path'),assert=require('node:assert/strict');
(async()=>{
 const root=path.resolve(__dirname,'../..'),test=fs.mkdtempSync(path.join(os.tmpdir(),'jarviss-reader-'));
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
  const read=id=>row(id).getByRole('button',{name:'Read full document',exact:true}).click();
  const waitReader=title=>page.waitForFunction(title=>document.querySelector('#reference-reader').classList.contains('visible')&&document.querySelector('#reference-title').textContent===title,title);
  const back=()=>page.locator('#reference-back').click();
  const words=text=>(text.match(/[\p{L}\p{N}]+/gu)||[]).join(' ');
  await page.locator('#setup-later').click();await page.locator('[data-page="docs"]').click();
  assert.equal(await page.locator('.reference-card').count(),38);
  assert.equal(await page.getByRole('button',{name:'Open illustrated PDF',exact:true}).count(),3); // Only the three available PDF cards are exposed.
  // Every bundled document is complete, readable, and browsable without a model.
  for(const entry of catalog){
   await read(entry.id);await waitReader(entry.title);
   const doc=await page.evaluate(id=>window.jarviss.command('reference',{id}),entry.id);
   assert.equal(await page.locator('#reference-text > section').count(),doc.sections.length);
   assert.equal(await page.locator('#reference-section-list button').count(),doc.sections.length);
   assert.equal(await page.locator('#reference-open-pdf').isVisible(),!!entry.pdf);
   assert.equal(await page.locator('#reference-save-pdf').isVisible(),!!entry.pdf);
   for(let i=0;i<doc.sections.length;i++){
    const source=doc.sections[i].text.replace(/^\s*(?:[-*•]|\d+[.)])[ \t]+/gm,'');
    const shown=await page.locator('.reference-prose').nth(i).innerText();
    assert.equal(words(shown),words(source),`${entry.id}: all words and quantities must survive formatting (${doc.sections[i].heading})`);
   }
   assert.equal(await page.locator('#reference-text details').count(),0,'No collapsed advice');
   await back();
  }
  console.log('PASS all 38 full documents: complete text and quantities, sections, format labels, and PDF availability; no model or internet');
  await read('fda-food-flood');await waitReader('Food and water after storms');
  assert.equal(await page.locator('#reference-text > section').count(),3);
  assert.doesNotMatch(await page.locator('#reference-text').innerText(),/WATCH|1-888|Questions\?|Get Assistance|Links for|Ask about this/);
  await page.locator('#reference-contents').click();
  await page.locator('#reference-section-list').getByRole('button',{name:'After a Storm',exact:true}).click();
  await page.locator('.reference-selected').filter({hasText:'When in doubt, throw it out.'}).waitFor();
  const position=await page.locator('.reference-selected').evaluate(el=>({top:el.getBoundingClientRect().top,bar:document.querySelector('.reference-jump').getBoundingClientRect().bottom}));
  assert.ok(position.top>=position.bar,'Jump target must stay below the sticky section picker');
  await page.locator('#reference-ask').click();
  assert.equal(await page.locator('#question').inputValue(),'Using the document "Food and water after storms", ');
  await page.locator('[data-page="docs"]').click();
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
  assert.equal(await page.locator('.reference-card:visible').count(),3);
  await page.locator('#docs-search').fill('insulin');
  await page.getByText('No matching documents.',{exact:true}).waitFor();
  await page.locator('#reference-pdfs').click();
  await page.locator('#reference-results button').filter({hasText:'Insulin'}).first().waitFor();
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
   await viewer.close();await back();
  }
  console.log('PASS three real offline PDFs, cited-page mapping, cover opening, close/reopen');
  // Stale saved citation remains understandable, and untrusted text stays literal.
  await page.evaluate(()=>openReference('field-water','removed-section'));
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
   for(const zoom of [1,1.25]){
    await app.evaluate(({BrowserWindow},zoom)=>BrowserWindow.getAllWindows()[0].webContents.setZoomFactor(zoom),zoom);
    await page.evaluate(()=>openReference('army-rope'));
    assert.equal(await page.locator('#reference-title').evaluate(el=>el===document.activeElement),true);
    await page.bringToFront();await page.locator('#reference-contents').focus();await page.keyboard.press('Enter');await page.keyboard.press('End');await page.keyboard.press('Enter');
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
  console.log('PASS keyboard, 1024/1440 windows, 100/125% zoom, no script errors or external requests');
 }finally{
  for(const name of fs.readdirSync(test).filter(n=>n.startsWith('hold-')))fs.rmSync(path.join(test,name));
  if(app)await app.close();fs.rmSync(test,{recursive:true,force:true});
 }
})().catch(e=>{console.error(e);process.exitCode=1;});
