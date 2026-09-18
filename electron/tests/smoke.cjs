const {_electron:electron}=require('playwright');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path'),assert=require('node:assert/strict');
(async()=>{
 const data=fs.mkdtempSync(path.join(os.tmpdir(),'jarviss-electron-'));
 const shots=process.env.JARVISS_TEST_SHOTS||data; // never the user's own local-data
 let app;
 try{
  const env={...process.env,JARVISS_DATA:data,JARVISS_APP_DATA:data};delete env.ELECTRON_RUN_AS_NODE;
  app=await electron.launch(process.env.TEST_PACKAGED?{executablePath:process.env.TEST_PACKAGED,args:[],env}:{args:[path.resolve(__dirname,'..')],env});
  const page=await app.firstWindow();const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.waitForFunction(()=>document.querySelector('#status').textContent==='Model off');
  await page.locator('#setup-later').click();
  assert.equal(await page.evaluate(()=>typeof window.require),'undefined');
  async function checkEmptyChat(){
   const layout=await page.evaluate(()=>{
    const rect=s=>{const r=document.querySelector(s).getBoundingClientRect();return {x:r.x,y:r.y,width:r.width,bottom:r.bottom};};
    return {heading:rect('.welcome .greeting'),actions:rect('#quick-actions'),composer:rect('#composer'),column:rect('.conversation-column'),header:rect('header'),height:innerHeight,overflow:document.documentElement.scrollWidth>innerWidth};
   });
   assert.ok(layout.heading.y>=layout.header.bottom,'Welcome must stay below the header');
   assert.ok(layout.actions.y-layout.heading.bottom>=18,'Prompts must sit below the heading');
   assert.ok(layout.composer.y-layout.actions.bottom>=12&&layout.composer.y-layout.actions.bottom<=28,'Composer must sit directly below the prompts'); // 16px under the compact-height rule
   assert.ok(layout.composer.width<=760,'Empty composer must remain a comfortable reading width');
   assert.ok(Math.abs(layout.composer.x+layout.composer.width/2-layout.column.x-layout.column.width/2)<2,'Empty composer must be centered');
   const block=layout.composer.bottom-layout.heading.y,above=layout.heading.y-layout.header.bottom,below=layout.height-layout.composer.bottom;
   assert.ok(Math.abs(above-below)<block,'Greeting, prompts and composer must read as one centred block');
   assert.ok(layout.composer.bottom<layout.height&&!layout.overflow,'Chat must fit without horizontal overflow');
   assert.equal(await page.locator('#clear').isVisible(),false);
  }
  for(const size of [{width:1024,height:720},{width:1440,height:940},{width:2240,height:1300}]){
   await page.setViewportSize(size);
   await checkEmptyChat();
   await page.screenshot({path:path.join(shots,`chat-empty-${size.width}.png`)});
  }
  await page.locator('#panel-toggle').click();
  await checkEmptyChat();
  await page.locator('#panel-toggle').click();
  await page.setViewportSize({width:1440,height:940});
  const prompts=await page.evaluate(async()=>(await window.jarviss.command('state')).quick_prompts);
  assert.equal(prompts.length,6);
  assert.deepEqual(await page.locator('#quick-actions button').allInnerTexts(),prompts.map(p=>p.label));
  for(const prompt of prompts.filter(p=>p.prompt.trimEnd().endsWith(':'))){
   await page.locator('#quick-actions button').filter({hasText:prompt.label}).click();
   assert.equal(await page.locator('#question').inputValue(),prompt.prompt.trimEnd()+' ');
   assert.equal(await page.locator('#question').evaluate(el=>el===document.activeElement),true);
  }
  await page.locator('#question').fill('');
  await require('./orb.cjs')(page);
  await page.screenshot({path:path.join(shots,'electron-assistant.png')});
  // The Situation card summarises the profile; Edit reveals the form, Save updates the card.
  assert.equal(await page.locator('#situation-summary-text').innerText(),'Not set');
  await page.locator('#situation-editor summary').click();
  await page.locator('[name="situation"]').fill('Testing an offline family plan.');
  await page.locator('[name="supplies"]').fill('Two people, blankets, bottled water.');
  assert.equal(await page.locator('[name="lat"], [name="lon"]').count(),0);
  await page.locator('[name="location_text"]').fill('Central Park, New York, NY');
  await page.locator('#profile-form button.primary').click();
  await page.waitForFunction(()=>document.querySelector('#toast').classList.contains('show')&&document.querySelector('#toast').textContent==='Situation saved'); // the toast is the one feedback channel
  assert.equal(JSON.parse(fs.readFileSync(path.join(data,'profile.json'))).location_text,'Central Park, New York, NY');
  assert.equal(await page.locator('#situation-summary-location').innerText(),'Central Park, New York, NY');
  assert.equal(await page.locator('#situation-summary-text').innerText(),'Testing an offline family plan.');
  assert.equal(await page.locator('#situation-editor').evaluate(el=>el.open),false,'Save closes the editor');
  await page.evaluate(async()=>{await window.jarviss.command('set_map_position',{lat:40.7736,lon:-73.9712,name:'Central Park'});await refresh();});
  assert.equal(await page.locator('#situation-summary-location').innerText(),'Central Park');
  await page.locator('nav [data-page="atlas"]').click();
  assert.equal(await page.locator('#radius, #download-map, #import-map, #example-map, #use-basemap, .map-download').count(),0);
  // A checkout with local-maps/ installed shows the real map; otherwise the HTML empty state stands in for the old canvas text.
  const hasMap=await page.evaluate(async()=>!!(await window.jarviss.command('state')).basemap);
  assert.equal(await page.locator('#map-empty').isVisible(),!hasMap,'Without a map the HTML empty state shows');
  assert.equal(await page.locator('#map-canvas').count(),0,'The legacy canvas is gone; #map-empty is the fallback');
  assert.equal(await page.locator('#location-picker').isVisible(),false,'The location picker stays hidden until asked');
  assert.match(await page.locator('#places').innerText(),hasMap?/straight-line|Searching|No matching/:/Map not ready/);
  await page.locator('nav [data-page="docs"]').click();
  await page.locator('.recovery-entry summary').click();
  assert.match(await page.locator('#recovery-document').innerText(),/NIST/);
  await page.locator('.recovery-entry .doc-ask').click();
  assert.match(await page.locator('#question').inputValue(),/Regroup and rebuild/);
  assert.equal(await page.locator('#assistant').isVisible(),true);
  assert.equal(await page.locator('nav [data-page="recovery"]').count(),0);
  assert.equal(await page.locator('#page-title').count(),0);
  await page.locator('nav [data-page="assistant"]').click();
  // Without a model the reply is a reference answer or an inline notice; either way the history layout applies.
  await page.locator('#question').fill('Can I use this water? Source: a river');await page.locator('#send').click();
  await page.waitForFunction(()=>document.querySelector('.message.assistant')||!document.querySelector('#composer-notice').hidden);
  assert.equal(await page.locator('.welcome').isVisible(),false);
  assert.equal(await page.locator('#clear').isVisible(),true);
  assert.equal(await page.locator('#error').isVisible(),false,'Chat errors never use the top banner');
  for(const size of [{width:1024,height:720},{width:1440,height:940}]){
   await page.setViewportSize(size);
   const box=await page.locator('#composer').boundingBox();
   assert.ok(box.y>size.height-260&&box.y+box.height<size.height,'History must keep the composer at the bottom of the window');
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  }
  await page.screenshot({path:path.join(shots,'chat-design.png')});
  await page.locator('#panel-toggle').click();
  assert.equal(await page.locator('#voice-panel').isVisible(),false);
  assert.equal(await page.locator('#composer').isVisible(),true);
  const centred=await page.evaluate(()=>{
   const grid=document.querySelector('.assistant-grid').getBoundingClientRect();
   const composer=document.querySelector('#composer').getBoundingClientRect();
   return composer.width<=760&&Math.abs(grid.x+grid.width/2-composer.x-composer.width/2)<2;
  });
  assert.ok(centred,'Closing the inspector keeps the chat column at its reading width, centred');
  assert.equal(await page.locator('.message.user').last().evaluate(el=>getComputedStyle(el).backgroundColor),'rgb(42, 42, 47)');
  await page.screenshot({path:path.join(shots,'chat-full-width.png')});
  await page.locator('#panel-toggle').click();
  assert.equal(await page.locator('#voice-panel').isVisible(),true);
  await page.locator('#clear').click();
  await page.locator('.chat-footer .confirm button').filter({hasText:'Yes'}).click();
  await page.waitForFunction(()=>!document.body.classList.contains('has-history'));
  await checkEmptyChat();
  assert.equal(await page.locator('nav [data-page="situation"]').count(),0);
  await page.locator('[data-page="settings"]').click();
  assert.equal(await page.locator('#voice-max-sentences').inputValue(),'3');
  await page.locator('[data-settings="responses"]').click();
  // Advanced fields autosave: two quick edits become one debounced save and one "Saved" toast.
  await page.evaluate(()=>{window.toastShows=0;new MutationObserver(()=>{const t=document.querySelector('#toast');if(t.classList.contains('show')&&t.textContent==='Saved')window.toastShows++;}).observe(document.querySelector('#toast'),{attributes:true,attributeFilter:['class']});});
  await page.locator('#voice-max-sentences').fill('2');
  await page.locator('#voice-prompt').fill('Use short spoken answers.');
  await page.waitForFunction(()=>document.querySelector('#toast').classList.contains('show')&&document.querySelector('#toast').textContent==='Saved');
  await page.waitForTimeout(600);
  assert.equal(await page.evaluate(()=>window.toastShows),1,'One toast for the debounced save');
  const saved=JSON.parse(fs.readFileSync(path.join(data,'settings.json')));
  assert.equal(saved.voice_max_sentences,2);
  assert.equal(saved.voice_prompt,'Use short spoken answers.');
  assert.equal(saved.units,'imperial');
  await page.locator('#voice-max-sentences').fill('');
  await page.waitForTimeout(600);
  assert.equal(JSON.parse(fs.readFileSync(path.join(data,'settings.json'))).voice_max_sentences,2,'An invalid value is not saved');
  await page.reload();
  await page.waitForFunction(()=>document.querySelector('#voice-max-sentences').value==='2');
  await page.locator('#setup-later').click();
  await page.locator('[data-page="settings"]').click();await page.locator('[data-settings="responses"]').click();
  await page.locator('#reset-prompts').click();
  await page.waitForFunction(()=>document.querySelector('#toast').classList.contains('show')&&document.querySelector('#toast').textContent==='Defaults restored');
  assert.equal(await page.locator('#voice-max-sentences').inputValue(),'3');
  assert.equal(JSON.parse(fs.readFileSync(path.join(data,'settings.json'))).voice_max_sentences,3,'Restore defaults saves, since there is no Save button');
  assert.equal(await page.locator('#units').inputValue(),'imperial');
  await page.locator('.prompt-disclosure summary').click();
  const editor=await page.locator('#system-prompt').boundingBox();
  assert.ok(editor.width>500,'System prompt must have a usable full-width editor');
  await page.screenshot({path:path.join(shots,'settings-design.png')});
  assert.deepEqual(errors,[]);
  await page.setViewportSize({width:1024,height:720});
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  console.log('PASS: Electron isolation, navigation, situation card, map empty state, recovery document; empty chat at 1024/1440/2240px, quick prompts, idle/active orb animation and reduced motion, history and clear transitions, inspector layouts');
 }finally{if(app)await app.close();fs.rmSync(data,{recursive:true,force:true});}
})().catch(e=>{console.error(e);process.exitCode=1;});
