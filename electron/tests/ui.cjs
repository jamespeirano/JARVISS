// Renderer behaviours that need no real model or map: settings tabs, Start/Stop model, the
// set-position menu, the hidden location picker, result counts, route panel, units (cards and
// map popups), app events and keyboard shortcuts. The backend map calls are stubbed so the
// MapLibre view exists without a 20 GB archive; start_model is stubbed so Stop model has
// something to stop.
const {_electron:electron}=require('playwright');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path'),assert=require('node:assert/strict');
(async()=>{
 const root=path.resolve(__dirname,'../..'),test=fs.mkdtempSync(path.join(os.tmpdir(),'jarvis-ui-'));
 let app;
 try{
  const linkType=process.platform==='win32'?'junction':'dir';
  fs.symlinkSync(path.join(root,'.venv'),path.join(test,'.venv'),linkType);
  fs.symlinkSync(path.join(root,'resources'),path.join(test,'resources'),linkType);
  fs.writeFileSync(path.join(test,'service.py'),`import sys
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,${JSON.stringify(root)})
from jarviss import service
original=service.Service.command
def command(self,method,args):
 if method=='start_model':
  self.ready=True
  return True
 if method=='import_basemap':
  self.archive=SimpleNamespace(path=Path(args['path']),pack={'osm_timestamp':'2026-01-01'})
  return self.state()
 if method=='nearest':
  return [{'id':'a','name':'Town well','kind':'drinking water','distance_m':2500,'point':[30.2760,-97.7400]},{'id':'b','name':'Corner pharmacy','kind':'pharmacy','distance_m':400,'point':[30.2700,-97.7460]},{'id':'c','name':'Unnamed swimming pool','kind':'untreated water','distance_m':150,'point':[30.2680,-97.7440]}]
 if method=='route':
  return {'destination':'Town well','distance_m':3000,'points':[[30.2672,-97.7431],[30.2760,-97.7400]],'steps':[{'instruction':'Head north on Congress Avenue','point':[30.2672,-97.7431]},{'instruction':'Arrive at Town well','point':[30.2760,-97.7400]}]}
 return original(self,method,args)
service.Service.command=command
service.main()
`);
  // A model file on disk makes Start model available; the stub never loads anything.
  fs.mkdirSync(path.join(test,'models'),{recursive:true});fs.writeFileSync(path.join(test,'models/test.gguf'),'test-only');
  fs.mkdirSync(path.join(test,'data'),{recursive:true});fs.writeFileSync(path.join(test,'data/settings.json'),JSON.stringify({model:'models/test.gguf',gpu_layers:0}));
  const env={...process.env,JARVISS_ROOT:test,JARVISS_DATA:path.join(test,'data'),JARVISS_APP_DATA:path.join(test,'app')};delete env.ELECTRON_RUN_AS_NODE;
  app=await electron.launch({args:[path.join(root,'electron')],env});const page=await app.firstWindow(),errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.waitForFunction(()=>document.querySelector('#status').textContent==='Model off');
  await page.locator('#setup-later').click();
  await page.locator('#assistant.visible').waitFor();
  // Native title-bar clearance and responsive page bounds on Mac and Windows.
  for(const [width,height,zoom] of [[900,600,1],[1024,768,1.25],[1440,900,1.5]]){
   await app.evaluate(({BrowserWindow},{width,height,zoom})=>{const win=BrowserWindow.getAllWindows()[0];win.setSize(width,height);win.webContents.setZoomFactor(zoom);},{width,height,zoom});
   for(const name of ['assistant','atlas','plan','docs','settings']){
    await page.locator(`[data-page="${name}"]`).click();
    await page.waitForTimeout(100);
    const bounds=await page.evaluate(()=>{
     const main=document.querySelector('main'),active=document.querySelector('.page.visible'),brand=document.querySelector('.wordmark');
     const range=document.createRange();range.selectNodeContents(brand);const brandTop=range.getBoundingClientRect().top;
     return {overflow:main.scrollWidth-main.clientWidth,pageOverflow:active.scrollWidth-active.clientWidth,brandTop};
    });
    assert.ok(bounds.overflow<=1&&bounds.pageOverflow<=1,`${name} overflows at ${width}x${height}, zoom ${zoom}: ${JSON.stringify(bounds)}`);
    if(name==='assistant'){
     const fits=await page.evaluate(()=>{const column=document.querySelector('.conversation-column').getBoundingClientRect();return [...document.querySelectorAll('#quick-actions button')].every(b=>{const r=b.getBoundingClientRect();return r.left>=column.left-1&&r.right<=column.right+1;});});
     assert.ok(fits,`Chat prompts stay inside their column at ${width}, zoom ${zoom}`);
    }
    if(process.platform==='darwin')assert.ok(bounds.brandTop*zoom>=30,'Brand clears the macOS traffic lights');
    const toggle=await page.locator('#navigation-toggle').boundingBox();
    assert.ok(toggle.x<=24&&toggle.y>=0,'Navigation toggle stays at the left edge');
    assert.ok(toggle.y+toggle.height<=bounds.brandTop,'Navigation toggle sits above the brand');
    if(process.platform==='darwin')assert.ok(toggle.y*zoom>=32,'Navigation toggle stays below the traffic lights');
    if(name==='assistant'){
     const controls=await page.evaluate(()=>['#header-voice-toggle','#panel-toggle'].map(s=>{const r=document.querySelector(s).getBoundingClientRect();return {left:r.left,right:r.right,top:r.top,bottom:r.bottom};}));
     assert.ok(controls[0].right<=controls[1].left,'Voice and right-sidebar buttons are separate and do not overlap');
     assert.ok(controls[1].right<=await page.evaluate(()=>innerWidth-parseFloat(getComputedStyle(document.querySelector('header')).paddingRight))+1,'Sidebar toggle clears the native window-control area');
     if(process.env.JARVISS_TEST_SHOTS){fs.mkdirSync(process.env.JARVISS_TEST_SHOTS,{recursive:true});await page.screenshot({path:path.join(process.env.JARVISS_TEST_SHOTS,`shell-${process.platform}-${width}-${zoom}.png`)});}
    }
   }
  }
  await app.evaluate(({BrowserWindow})=>{const win=BrowserWindow.getAllWindows()[0];win.setSize(1440,900);win.webContents.setZoomFactor(1);});
  await page.locator('[data-page="assistant"]').click();
  console.log('PASS native title-bar clearance, separate sidebar/voice buttons and page bounds at 900/1024/1440 widths and 100/125/150% zoom');
  // Both sidebars resize independently, collapse to Chat, and retain their preferences.
  const panelWidth=id=>page.locator(id).evaluate(el=>el.getBoundingClientRect().width);
  const dragDivider=async(id,delta)=>{
   const box=await page.locator(id).boundingBox(),x=box.x+box.width/2,y=box.y+Math.min(box.height/2,180);
   await page.mouse.move(x,y);await page.mouse.down();await page.mouse.move(x+delta,y,{steps:8});await page.mouse.up();
  };
  const navStart=await panelWidth('#navigation-panel'),voiceStart=await panelWidth('#voice-panel');
  await dragDivider('#navigation-resize',40);
  assert.ok(Math.abs(await panelWidth('#navigation-panel')-navStart-40)<2,'Dragging navigation divider widens navigation');
  await dragDivider('#voice-resize',-40);
  assert.ok(Math.abs(await panelWidth('#voice-panel')-voiceStart-40)<2,'Dragging voice divider left widens voice');
  const navSaved=await panelWidth('#navigation-panel'),voiceSaved=await panelWidth('#voice-panel');
  const narrowChat=await panelWidth('.conversation-column'),narrowArea=await panelWidth('.assistant-grid');
  await page.locator('#navigation-toggle').click();await page.locator('#panel-toggle').click();
  assert.equal(await page.locator('#navigation-panel').isVisible(),false);
  assert.equal(await page.locator('#voice-panel').isVisible(),false);
  assert.ok(await panelWidth('.assistant-grid')>narrowArea+100,'Collapsing navigation expands the Chat area');
  assert.ok(await panelWidth('.conversation-column')>=narrowChat,'Chat keeps its reading width when both panels are hidden');
  assert.equal(await page.locator('.assistant-grid').evaluate(el=>getComputedStyle(el).gridTemplateColumns.split(' ').length),1,'Collapsed Chat has a single column');
  assert.equal(await page.locator('#navigation-toggle').getAttribute('aria-expanded'),'false');
  const restore=await page.locator('#navigation-toggle').boundingBox();
  assert.ok(restore.x<=24,'Restore control stays at the left edge');
  if(process.platform==='darwin')assert.ok(restore.y>=32,'Restore control stays below Mac traffic lights');
  assert.ok(restore.y+restore.height<=(await page.locator('header').boundingBox()).height,'Restore control stays clear of page content');
  assert.equal(await page.locator('#header-voice-toggle').isVisible(),true,'Voice remains available when both sidebars are closed');
  await page.reload();await page.locator('#assistant.visible').waitFor();
  assert.equal(await page.locator('#navigation-panel').isVisible(),false,'Hidden navigation persists');
  assert.equal(await page.locator('#voice-panel').isVisible(),false,'Hidden voice panel persists');
  await page.locator('#navigation-toggle').click();await page.locator('#panel-toggle').click();
  assert.ok(Math.abs(await panelWidth('#navigation-panel')-navSaved)<2,'Navigation width persists');
  assert.ok(Math.abs(await panelWidth('#voice-panel')-voiceSaved)<2,'Voice width persists');
  const divider=await page.locator('#navigation-resize').boundingBox();
  await page.mouse.move(divider.x+4,divider.y+160);await page.mouse.down();await page.mouse.move(divider.x+44,divider.y+160);
  await page.keyboard.press('Escape');await page.mouse.up();
  assert.ok(Math.abs(await panelWidth('#navigation-panel')-navSaved)<2,'Escape cancels an unfinished resize');
  assert.equal(await page.locator('body').evaluate(el=>el.classList.contains('resizing-sidebar')),false);
  await page.locator('#navigation-resize').focus();await page.keyboard.press('Home');
  assert.equal(await panelWidth('#navigation-panel'),160);
  await page.keyboard.press('ArrowRight');assert.equal(await panelWidth('#navigation-panel'),170);
  await page.keyboard.press('End');assert.equal(await panelWidth('#navigation-panel'),320);
  await page.locator('#voice-resize').focus();await page.keyboard.press('Home');
  assert.equal(await panelWidth('#voice-panel'),240);
  await page.keyboard.press('ArrowLeft');assert.equal(await panelWidth('#voice-panel'),250);
  await page.keyboard.press('End');assert.equal(await panelWidth('#voice-panel'),440);
  await page.locator('[data-page="docs"]').click();
  assert.equal(await page.locator('#voice-panel').isVisible(),false,'Voice sidebar stays on Chat');
  assert.equal(await page.locator('#panel-toggle').isVisible(),false);
  await page.locator('[data-page="assistant"]').click();
  await app.evaluate(({BrowserWindow})=>BrowserWindow.getAllWindows()[0].setSize(900,600));
  await page.waitForFunction(()=>innerWidth<=900);
  assert.equal(await page.locator('#voice-resize').isVisible(),false,'Stacked voice panel has no horizontal resize handle');
  assert.ok(await page.evaluate(()=>document.querySelector('main').scrollWidth-document.querySelector('main').clientWidth<=1),'Saved widths fit a smaller window');
  await app.evaluate(({BrowserWindow})=>BrowserWindow.getAllWindows()[0].setSize(1440,900));
  await page.waitForFunction(()=>innerWidth>980);
  await page.locator('#navigation-resize').dblclick();await page.locator('#voice-resize').dblclick();
  assert.ok(Math.abs(await panelWidth('#navigation-panel')-navStart)<2,'Double-click restores navigation width');
  assert.ok(Math.abs(await panelWidth('#voice-panel')-voiceStart)<2,'Double-click restores voice width');
  console.log('PASS both sidebars: drag, keyboard, cancellation, collapse, reload, smaller windows and reset');
  // Idle: the pill says "Model off" with an idle dot, and Start voice mode is not the primary action.
  assert.equal(await page.locator('#status-dot').getAttribute('class'),'status-dot idle');
  assert.equal(await page.locator('#status').isVisible(),true);
  assert.equal(await page.locator('#voice-toggle').evaluate(el=>el.classList.contains('primary')),false,'Voice is not primary while the model is off');
  assert.equal(await app.evaluate(({BrowserWindow})=>BrowserWindow.getAllWindows()[0].getTitle()),'Chat · JARVISS');
  assert.equal(await page.locator('aside [data-page="assistant"]').getAttribute('aria-current'),'page');
  assert.equal(await page.locator('#app-version').innerText(),'v'+require('../package.json').version);
  // Settings tabs follow the APG pattern: one tab in the sequence, arrows move focus and selection, panels follow aria-controls.
  await page.locator('[data-page="settings"]').click();
  assert.equal(await page.locator('#settings .page-title').evaluate(el=>el===document.activeElement),true,'Page changes focus the title');
  assert.deepEqual(await page.locator('#settings-tabs [role=tab]').evaluateAll(tabs=>tabs.map(t=>t.tabIndex)),[0,-1,-1,-1]);
  await page.locator('[data-settings="model"]').focus();await page.keyboard.press('ArrowRight');
  assert.equal(await page.locator('[data-settings="audio"]').evaluate(el=>el===document.activeElement&&el.getAttribute('aria-selected')==='true'),true);
  assert.equal(await page.locator('#settings-audio').isVisible(),true);assert.equal(await page.locator('#settings-model').isVisible(),false);
  await page.keyboard.press('End');assert.equal(await page.locator('#settings-about').isVisible(),true);
  await page.keyboard.press('ArrowRight');assert.equal(await page.locator('#settings-model').isVisible(),true,'Arrow keys wrap');
  await page.keyboard.press('ArrowLeft');assert.equal(await page.locator('#settings-about').isVisible(),true);
  assert.match(await page.locator('#about-version').innerText(),/^Version \d/);
  // About → Keyboard shortcuts opens the same dialog as the ? key.
  await page.locator('#settings-about button').filter({hasText:'Keyboard shortcuts'}).click();
  await page.waitForFunction(()=>document.querySelector('#shortcuts-dialog').open);
  await page.keyboard.press('Escape');await page.waitForFunction(()=>!document.querySelector('#shortcuts-dialog').open);
  console.log('PASS settings tabs keyboard navigation, page title, rail state, About shortcuts button');
  // Start/Stop model: Stop only exists while the model runs; stopping restores Start and the status pill.
  await page.locator('[data-settings="model"]').click();
  assert.equal(await page.locator('#stop-model').isVisible(),false,'No Stop model button before the model runs');
  assert.equal(await page.locator('#start-model').isEnabled(),true);
  assert.equal(await page.locator('#download-model').innerText(),'Change model');
  // Without any model, Start has nothing to start: it hides and "Download a model" becomes the primary action.
  await page.evaluate(()=>{const model=state.settings.model;state.settings.model='';renderOperation();window.savedModel=model;});
  assert.equal(await page.locator('#start-model').isVisible(),false,'No Start button without a model');
  assert.equal(await page.locator('#download-model').innerText(),'Download a model');
  assert.equal(await page.locator('#download-model').evaluate(el=>el.classList.contains('primary')),true);
  await page.evaluate(()=>{state.settings.model=window.savedModel;renderOperation();});
  assert.equal(await page.locator('#start-model').isVisible(),true);assert.equal(await page.locator('#download-model').evaluate(el=>el.classList.contains('primary')),false);
  await page.locator('#start-model').click();
  await page.waitForFunction(()=>document.querySelector('#status').textContent==='Ready');
  await page.locator('#stop-model').waitFor({state:'visible'});
  // Ready is the dot alone: the label stays in the DOM for assistive tech but is visually hidden.
  assert.equal(await page.locator('#status-dot').getAttribute('class'),'status-dot ok');
  assert.equal(await page.locator('#status').evaluate(el=>el.classList.contains('visually-hidden')&&el.closest('.status-pill').classList.contains('dot-only')),true,'Ready shows the dot only');
  assert.equal(await page.locator('#voice-toggle').evaluate(el=>el.classList.contains('primary')),true,'Voice becomes primary once the model runs');
  assert.equal(await page.locator('#start-model').isVisible(),false,'Start model gives way to Stop model');
  assert.equal(await page.locator('#model-setup-status').innerText(),'Running on this computer.');
  await page.locator('#stop-model').click();
  await page.waitForFunction(()=>document.querySelector('#status').textContent==='Model off');
  assert.equal(await page.locator('#status').evaluate(el=>el.classList.contains('visually-hidden')),false);
  await page.locator('#start-model').waitFor({state:'visible'});
  assert.equal(await page.locator('#stop-model').isVisible(),false);
  // The operation-ended event and the RPC reply travel on different IPC channels and can land a few ms apart; wait for the settled state.
  await page.waitForFunction(()=>!document.querySelector('#start-model').disabled);
  assert.equal(await page.evaluate(()=>document.activeElement.classList.contains('page-title')),true,'Focus lands on the title when the pressed button goes away');
  assert.equal(await page.locator('#error').isVisible(),false);
  // The chat notice for a model problem offers Start model (the file exists) next to Open Settings.
  await page.locator('[data-page="assistant"]').click();
  await page.evaluate(()=>composerNotice('The model is not running.'));
  assert.deepEqual(await page.locator('#composer-notice button:not(.dismiss)').allInnerTexts(),['Start model','Open Settings']);
  await page.locator('#composer-notice button').filter({hasText:'Start model'}).click();
  await page.waitForFunction(()=>document.querySelector('#status').textContent==='Ready'&&document.querySelector('#composer-notice').hidden);
  await page.evaluate(()=>call('stop_model',{}));
  await page.waitForFunction(()=>document.querySelector('#status').textContent==='Model off');
  await page.evaluate(()=>composerNotice('The model is not running.'));
  assert.equal(await page.locator('#composer-notice').getAttribute('class'),'notice warn','A plain notice is a warning; only failures are danger');
  assert.equal(await page.locator('#composer-notice').getAttribute('role'),'status');
  await page.locator('#composer-notice button').filter({hasText:'Open Settings'}).click();
  await page.locator('#settings.visible').waitFor();assert.equal(await page.locator('#settings-model').isVisible(),true);
  console.log('PASS Start/Stop model in Settings and from the chat notice');
  // Maps with a stubbed archive: the MapLibre view exists, so "Use map centre" has a centre to read.
  await app.evaluate(({dialog},file)=>{dialog.showOpenDialog=async()=>({canceled:false,filePaths:[file]});},path.join(test,'fixture.pmtiles'));
  await page.evaluate(async()=>{await window.jarviss.pick('basemap');await refresh();});
  await page.locator('[data-page="atlas"]').click();
  await page.waitForFunction(()=>!!window.jarvisDetailMap);
  assert.equal(await page.locator('#location-picker').isVisible(),false,'The picker stays hidden until asked');
  assert.equal(await page.locator('#map-empty').isVisible(),false);
  assert.equal(await page.locator('#map-canvas').count(),0);
  // Search a place opens the picker with the city field focused; Escape or Close hides it again and returns focus to the menu.
  await page.locator('#set-position-menu summary').click();await page.locator('#find-location').click();
  await page.locator('#location-picker').waitFor({state:'visible'});
  assert.equal(await page.evaluate(()=>document.activeElement.id),'city-search');
  await page.keyboard.press('Escape');
  await page.waitForFunction(()=>document.querySelector('#location-picker').hidden);
  assert.equal(await page.evaluate(()=>document.activeElement.matches('#set-position-menu>summary')),true,'Escape closes the picker and returns to the menu');
  await page.locator('#set-position-menu summary').click();await page.locator('#find-location').click();
  await page.locator('#location-picker-close').click();
  assert.equal(await page.locator('#location-picker').isVisible(),false);
  assert.equal(await page.evaluate(()=>document.activeElement.matches('#set-position-menu>summary')),true);
  await page.locator('#set-position-menu summary').click();
  await page.waitForFunction(()=>document.querySelector('#set-position-menu').open&&document.activeElement?.id==='find-location');
  await page.keyboard.press('ArrowDown');assert.equal(await page.evaluate(()=>document.activeElement.id),'map-use-centre');
  await page.keyboard.press('Enter');
  await page.locator('#map-confirm').filter({hasText:'Set position here?'}).waitFor();
  assert.equal(await page.locator('#set-position-menu').evaluate(el=>el.open),false,'Choosing an item closes the menu');
  await page.locator('#map-confirm button').filter({hasText:'No'}).click();
  assert.equal(await page.locator('#map-confirm').isVisible(),false);
  assert.equal(fs.existsSync(path.join(test,'data/profile.json')),false,'No answers without confirmation');
  await page.locator('#set-position-menu summary').click();await page.locator('#map-use-centre').click();
  await page.locator('#map-confirm button').filter({hasText:'Yes'}).click();
  await page.waitForFunction(()=>document.querySelector('#map-position-note').textContent.includes('Map centre'));
  assert.equal(typeof JSON.parse(fs.readFileSync(path.join(test,'data/profile.json'))).lat,'number');
  assert.equal(await page.locator('#toast').innerText(),'Position set');
  assert.equal(await page.locator('#toast').evaluate(el=>el.classList.contains('show')),true,'Toasts show through a class, not text emptiness');
  await page.waitForFunction(()=>document.querySelector('#map-result-count').textContent==='3 places');
  assert.equal(await page.locator('#map-show-all').isVisible(),true);
  assert.ok(await page.evaluate(()=>{const a=document.querySelector('#map-search').getBoundingClientRect(),b=document.querySelector('#map-show-all').getBoundingClientRect();return Math.abs(a.top-b.top)<8&&b.right<=document.querySelector('.map-search').getBoundingClientRect().right;}),'Show all sits inside the search row');
  const mediumDate=(y,m,d)=>page.evaluate(([y,m,d])=>new Intl.DateTimeFormat(undefined,{dateStyle:'medium'}).format(new Date(y,m-1,d)),[y,m,d]);
  assert.equal(await page.locator('#map-caption').innerText(),`Map data from ${await mediumDate(2026,1,1)} · Searches cover 3 mi around you`,'The caption carries a readable date and the units in use');
  assert.match(await page.locator('#places').innerText(),/drinking water · 1\.6 miles/);
  assert.match(await page.locator('#places').innerText(),/pharmacy · 0\.2 miles/);
  assert.doesNotMatch(await page.locator('#places').innerText(),/miles straight line/,'"straight line" is said once, not per card');
  assert.equal(await page.locator('#places .places-footnote').innerText(),'Distances are straight-line');
  const unnamedCard=page.locator('#places .place-card').filter({hasText:'Swimming pool'});
  assert.equal(await unnamedCard.locator('strong').innerText(),'Swimming pool','"Unnamed swimming pool" reads as the kind');
  assert.equal(await unnamedCard.locator('.meta').innerText(),'Unnamed · untreated water · 492 ft','The gap moves into the meta line');
  // Refining the search keeps the current list on screen (dimmed) until the new results land.
  await page.evaluate(()=>{window.busyDuringSearch=null;const list=document.querySelector('#places');new MutationObserver(()=>{if(list.getAttribute('aria-busy')==='true'&&list.querySelector('.place-card'))window.busyDuringSearch=true;}).observe(list,{attributes:true,attributeFilter:['aria-busy']});});
  await page.locator('#map-search').fill('well');
  await page.waitForFunction(()=>window.busyDuringSearch===true&&document.querySelector('#places').getAttribute('aria-busy')!=='true');
  await page.locator('#map-search').fill('');
  await page.waitForFunction(()=>document.querySelector('#places').getAttribute('aria-busy')!=='true'&&document.querySelectorAll('#places .place-card').length===3);
  // Installed maps show a check row where the download button used to be.
  await page.evaluate(()=>{state.usRouting={ready:true};renderAtlas();});
  assert.equal(await page.locator('#download-us-maps').isVisible(),false,'No disabled primary for finished work');
  assert.equal(await page.locator('#us-map-ready').innerText(),'Installed');
  assert.equal(await page.locator('#us-map-ready').evaluate(el=>el.classList.contains('ready-row')&&!!el.querySelector('svg use[href="#i-check"]')),true);
  await page.evaluate(()=>{state.usRouting={ready:false};renderAtlas();});
  assert.equal(await page.locator('#download-us-maps').isVisible(),true);assert.equal(await page.locator('#us-map-ready').isVisible(),false);
  // Map popups use the same distance formatter as the cards (miles until Units changes).
  // A synthetic click in the viewport corner (a real Point: a plain {x,y} would be read as options and query the whole view): at zoom 3 every stub result shares one pixel, so a bare point must be far away in pixel space.
  const popupAt=()=>page.evaluate(()=>{const m=window.jarvisDetailMap,lngLat=m.unproject([6,6]);m.fire('click',{lngLat,point:m.project(lngLat)});if(document.querySelectorAll('.maplibregl-popup-content').length!==1)return 'popup count '+document.querySelectorAll('.maplibregl-popup-content').length;return document.querySelector('.maplibregl-popup-content .popup-distance')?.textContent;});
  assert.match(await popupAt(),/^[\d.,]+ (miles|ft) from you · straight line$/);
  assert.equal(await page.locator('.maplibregl-popup-content strong').innerText(),'Selected point');
  await page.evaluate(()=>document.querySelector('.maplibregl-popup-close-button').click());
  await page.evaluate(()=>{window.copied=[];navigator.clipboard.writeText=text=>{window.copied.push(text);return Promise.resolve();};});
  await page.locator('#places button').filter({hasText:'Directions'}).first().click();
  await page.waitForFunction(()=>document.querySelector('#route-info').textContent.includes('Walk to Town well'));
  assert.match(await page.locator('#route-info').innerText(),/1\.9 miles/);
  assert.match(await page.locator('#route-info > p').first().innerText(),/^1 of 2/);
  await page.locator('#copy-route').click();
  assert.match(await page.evaluate(()=>window.copied[0]),/^Walk to Town well · 1\.9 miles\n1\. Head north on Congress Avenue\n2\. Arrive at Town well$/);
  assert.equal(await page.locator('#toast').innerText(),'Directions copied');
  await page.locator('#clear-route').click();
  assert.equal(await page.locator('#route-info').innerText(),'');
  assert.equal(await page.locator('#route-panel').isVisible(),false);
  assert.equal(await page.evaluate(()=>route),null);
  // Click-on-the-map mode has a visible exit and Escape cancels it.
  await page.locator('#set-position-menu summary').click();await page.locator('#set-position').click();
  assert.equal(await page.locator('#map-click-cancel').isVisible(),true);
  assert.equal(await page.locator('#map-click-hint').innerText(),'Click your current position.');
  await page.keyboard.press('Escape');
  assert.equal(await page.locator('#map-click-cancel').isVisible(),false);
  assert.equal(await page.locator('#map-click-hint').innerText(),'Click a point for position or directions.');
  console.log('PASS set-position menu, map-centre confirmation, result count, route panel copy and clear, click mode exit');
  // Units apply to every distance the renderer shows. Advanced settings save themselves: one "Saved" toast per change.
  await page.locator('[data-page="settings"]').click();await page.locator('[data-settings="responses"]').click();
  await page.evaluate(()=>document.querySelector('#toast').classList.remove('show'));
  await page.locator('#units').selectOption('metric');
  await page.waitForFunction(()=>document.querySelector('#toast').classList.contains('show')&&document.querySelector('#toast').textContent==='Saved');
  assert.equal(JSON.parse(fs.readFileSync(path.join(test,'data/settings.json'))).units,'metric');
  await page.locator('[data-page="atlas"]').click();
  assert.equal(await page.locator('#map-caption').innerText(),`Map data from ${await mediumDate(2026,1,1)} · Searches cover 5 km around you`);
  await page.waitForFunction(()=>document.querySelector('#places').textContent.includes('2.5 km'));
  assert.match(await page.locator('#places').innerText(),/pharmacy · 400 m/);
  assert.match(await page.locator('#places').innerText(),/untreated water · 150 m/);
  assert.match(await popupAt(),/^[\d.,]+ (km|m) from you · straight line$/,'Popups follow the Units setting too');
  await page.evaluate(()=>document.querySelector('.maplibregl-popup-close-button').click());
  await page.locator('#places button').filter({hasText:'Directions'}).first().click();
  await page.waitForFunction(()=>document.querySelector('#route-info').textContent.includes('3.0 km'));
  console.log('PASS units toggle re-renders card and popup distances');
  // Menu and keyboard events from the main process.
  const sendApp=(event,data)=>app.evaluate(({BrowserWindow},payload)=>BrowserWindow.getAllWindows()[0].webContents.send('app-event',payload),{event,data});
  await sendApp('open-page',{page:'docs'});await page.locator('#docs.visible').waitFor();
  assert.equal(await app.evaluate(({BrowserWindow})=>BrowserWindow.getAllWindows()[0].getTitle()),'Docs · JARVISS');
  await sendApp('focus-composer');await page.waitForFunction(()=>document.activeElement?.id==='question');
  await sendApp('show-shortcuts');await page.waitForFunction(()=>document.querySelector('#shortcuts-dialog').open);
  await page.keyboard.press('Escape');await page.waitForFunction(()=>!document.querySelector('#shortcuts-dialog').open);
  await page.locator('#assistant .page-title').focus();await page.keyboard.press('?');
  await page.waitForFunction(()=>document.querySelector('#shortcuts-dialog').open);
  await page.locator('[data-close-dialog]').click();
  // Plan records: one meta sentence and a rounded "About N days left" that warns at three days or fewer.
  await page.evaluate(async()=>{await call('planner_save',{kind:'supplies',name:'Water',quantity:30,unit:'liters',daily:10,notes:'Blue jugs in the garage'});state.planner=await call('planner_save',{kind:'supplies',name:'Rice',quantity:100,unit:'meals',daily:7});renderPlanner();});
  await page.locator('[data-page="plan"]').click();
  const water=page.locator('#plan-list .plan-record').filter({hasText:'Water'}),rice=page.locator('#plan-list .plan-record').filter({hasText:'Rice'});
  assert.equal(await water.locator('.record-meta.desc').innerText(),'30 liters · 10 a day · Blue jugs in the garage');
  assert.equal(await water.locator('.record-note').innerText(),'About 3 days left');assert.equal(await water.locator('.record-note.warn').count(),1,'Three days or fewer warns');
  assert.equal(await rice.locator('.record-note').innerText(),'About 14 days left');assert.equal(await rice.locator('.record-note.warn').count(),0,'14.29 days rounds and does not warn');
  // Board times read relative to now, then as a clock time after an hour.
  const times=await page.evaluate(()=>[10e3,120e3,2*3600e3].map(ms=>relativeTime(new Date(Date.now()-ms).toISOString())));
  assert.equal(times[0],'just now');assert.equal(times[1],'2 min ago');assert.match(times[2],/^\d{2}:\d{2}$/,'After an hour the clock time is shown');
  assert.match(await page.evaluate(()=>relativeTime(new Date(Date.now()-3*86400e3).toISOString())),/^\S.* \d{2}:\d{2}$/,'Older messages carry the date too');
  // Docs: the whole library row opens the reader; dragging files over the page raises an overlay that leaves with the drag.
  await page.locator('[data-page="docs"]').click();
  await page.locator('#references .doc-row').first().click({position:{x:4,y:4}});
  await page.locator('#reference-reader.visible').waitFor();
  assert.equal(await page.locator('#reference-back-label').innerText(),'Back to Docs');
  await page.locator('#reference-back').click();await page.locator('#docs.visible').waitFor();
  const overlayShown=()=>page.evaluate(()=>{const o=document.querySelector('#docs > .drop-overlay');return !!o&&getComputedStyle(o).display!=='none'&&document.querySelector('#docs').classList.contains('over');});
  assert.equal(await overlayShown(),false,'No overlay before a drag');
  await page.evaluate(()=>{const transfer=new DataTransfer();transfer.items.add(new File(['notes'],'notes.txt',{type:'text/plain'}));window.dragTransfer=transfer;document.querySelector('#docs').dispatchEvent(new DragEvent('dragenter',{dataTransfer:transfer,bubbles:true,cancelable:true}));});
  assert.equal(await overlayShown(),true,'Drag-enter shows the overlay');
  await page.evaluate(()=>{const docs=document.querySelector('#docs');docs.querySelector('#documents').dispatchEvent(new DragEvent('dragenter',{dataTransfer:window.dragTransfer,bubbles:true,cancelable:true}));docs.querySelector('#documents').dispatchEvent(new DragEvent('dragleave',{dataTransfer:window.dragTransfer,bubbles:true}));});
  assert.equal(await overlayShown(),true,'Crossing child elements keeps the overlay');
  await page.evaluate(()=>document.querySelector('#docs').dispatchEvent(new DragEvent('dragleave',{dataTransfer:window.dragTransfer,bubbles:true})));
  assert.equal(await overlayShown(),false,'Leaving the page removes the overlay');
  console.log('PASS plan record meta and days left, relative board times, library row click, drop overlay');
  await sendApp('toggle-voice-panel');await page.waitForFunction(()=>document.body.classList.contains('voice-panel-hidden'));
  assert.equal(await page.locator('#panel-toggle').getAttribute('aria-expanded'),'false');
  await page.reload();await page.waitForFunction(()=>document.querySelector('#status').textContent==='Model off');
  assert.equal(await page.evaluate(()=>document.body.classList.contains('voice-panel-hidden')),true,'Inspector state persists');
  await page.locator('#assistant.visible').waitFor(); // "Set up later" is remembered because a model file exists
  await page.locator('#panel-toggle').click();
  assert.equal(await page.locator('#voice-panel').isVisible(),true);
  await sendApp('service-stopped');
  await page.getByRole('alert').filter({hasText:'local service stopped'}).waitFor();
  assert.equal(await page.locator('#error button').filter({hasText:'Restart local service'}).count(),1);
  assert.equal(await page.locator('#status').innerText(),'Local service stopped');
  assert.deepEqual(errors,[]);
  console.log('PASS app events: open-page, focus-composer, shortcuts dialog and ? key, persisted voice panel, service-stopped notice');
 }finally{if(app)await app.close();fs.rmSync(test,{recursive:true,force:true});}
})().catch(e=>{console.error(e);process.exitCode=1;});
