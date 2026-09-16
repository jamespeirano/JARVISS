const {_electron:electron}=require('playwright');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path'),assert=require('node:assert/strict');
(async()=>{
 const data=fs.mkdtempSync(path.join(os.tmpdir(),'jarviss-electron-'));
 let app;
 try{
  const env={...process.env,JARVISS_DATA:data,JARVISS_APP_DATA:data};delete env.ELECTRON_RUN_AS_NODE;
  app=await electron.launch(process.env.TEST_PACKAGED?{executablePath:process.env.TEST_PACKAGED,args:[],env}:{args:[path.resolve(__dirname,'..')],env});
  const page=await app.firstWindow();const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.waitForFunction(()=>document.querySelector('#status').textContent==='Model not started');
  await page.locator('#setup-later').click();
  assert.equal(await page.evaluate(()=>typeof window.require),'undefined');
  async function checkEmptyChat(){
   const layout=await page.evaluate(()=>{
    const rect=s=>{const r=document.querySelector(s).getBoundingClientRect();return {x:r.x,y:r.y,width:r.width,bottom:r.bottom};};
    return {heading:rect('.welcome h2'),actions:rect('#quick-actions'),composer:rect('#composer'),column:rect('.conversation-column'),header:rect('header'),height:innerHeight,overflow:document.documentElement.scrollWidth>innerWidth};
   });
   assert.ok(layout.heading.y>=layout.header.bottom,'Welcome must stay below the header');
   assert.ok(layout.actions.y-layout.heading.bottom>=18,'Shortcuts must sit below the heading');
   assert.ok(layout.composer.y-layout.actions.bottom>=18&&layout.composer.y-layout.actions.bottom<=28,'Composer must sit directly below the shortcuts');
   assert.ok(layout.composer.width<=681,'Empty composer must remain a comfortable reading width');
   assert.ok(Math.abs(layout.composer.x+layout.composer.width/2-layout.column.x-layout.column.width/2)<2,'Empty composer must be centered');
   assert.ok(layout.composer.bottom<layout.height&&!layout.overflow,'Chat must fit without horizontal overflow');
   assert.equal(await page.locator('#clear').isVisible(),false);
  }
  for(const size of [{width:1024,height:720},{width:1440,height:940},{width:2240,height:1300}]){
   await page.setViewportSize(size);
   await checkEmptyChat();
   await page.screenshot({path:path.resolve(__dirname,`../../local-data/chat-empty-${size.width}.png`)});
  }
  await page.locator('#panel-toggle').click();
  await checkEmptyChat();
  await page.locator('#panel-toggle').click();
  await page.setViewportSize({width:1440,height:940});
  for(const shortcut of await page.locator('#quick-actions button').all()){
   await shortcut.click();
   assert.ok((await page.locator('#question').inputValue()).length>10);
   assert.equal(await page.locator('#question').evaluate(el=>el===document.activeElement),true);
  }
  await page.locator('#question').fill('');
  const first = await page.locator('#orb canvas').screenshot();
  await page.waitForTimeout(250);
  const second = await page.locator('#orb canvas').screenshot();
  assert.notDeepEqual(first, second, 'JARVIS rings must animate');
  await page.evaluate(()=>window.jarvisState('voice','Speaking'));
  assert.equal(await page.locator('#orb').getAttribute('data-state'),'speaking');
  await page.evaluate(()=>window.jarvisState('voice','Voice off'));
  await page.screenshot({path:path.resolve(__dirname,'../../local-data/electron-assistant.png')});
  await page.locator('nav [data-page="docs"]').click();
  await page.locator('#situation-document summary').click();
  await page.locator('[name="situation"]').fill('Testing an offline family plan.');
  await page.locator('[name="supplies"]').fill('Two people, blankets, bottled water.');
  assert.equal(await page.locator('[name="lat"], [name="lon"]').count(),0);
  await page.locator('[name="location_text"]').fill('Central Park, New York, NY');
  await page.locator('#profile-form button.primary').click();
  await page.waitForFunction(()=>document.querySelector('#saved').textContent.includes('Saved'));
  assert.equal(JSON.parse(fs.readFileSync(path.join(data,'profile.json'))).location_text,'Central Park, New York, NY');
  await page.evaluate(async()=>{await window.jarviss.command('set_map_position',{lat:40.7736,lon:-73.9712,name:'Central Park'});await refresh();});
  await page.locator('nav [data-page="atlas"]').click();await page.evaluate(async()=>{await window.jarviss.command('example_map');await refresh();});
  assert.equal(await page.locator('#radius, #download-map, #import-map, #example-map, .map-download').count(),0);
  await page.waitForFunction(()=>document.querySelectorAll('#places button').length>0);
  await page.locator('nav [data-page="docs"]').click();
  await page.locator('.recovery-entry summary').click();
  assert.match(await page.locator('#recovery-document').innerText(),/NIST/);
  await page.locator('.recovery-entry .doc-ask').click();
  assert.match(await page.locator('#question').inputValue(),/Regroup and rebuild/);
  assert.equal(await page.locator('#assistant').isVisible(),true);
  assert.equal(await page.locator('nav [data-page="recovery"]').count(),0);
  assert.equal(await page.locator('#page-title').count(),0);
  await page.locator('nav [data-page="assistant"]').click();
  await page.locator('#question').fill('Where is the nearest water?');await page.locator('#send').click();
  await page.waitForFunction(()=>document.querySelectorAll('.message.assistant').length>0);
  assert.match(await page.locator('.message.assistant').last().innerText(),/recorded|records/i);
  assert.equal(await page.locator('.welcome').isVisible(),false);
  assert.equal(await page.locator('#clear').isVisible(),true);
  for(const size of [{width:1024,height:720},{width:1440,height:940}]){
   await page.setViewportSize(size);
   const box=await page.locator('#composer').boundingBox();
   assert.ok(box.y>size.height-200&&box.y+box.height<size.height,'History must keep the composer at the bottom of the window');
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  }
  await page.screenshot({path:path.resolve(__dirname,'../../local-data/chat-design.png')});
  await page.locator('#panel-toggle').click();
  assert.equal(await page.locator('#voice-panel').isVisible(),false);
  assert.equal(await page.locator('#composer').isVisible(),true);
  const fullWidth=await page.evaluate(()=>{
   const grid=document.querySelector('.assistant-grid').getBoundingClientRect();
   const composer=document.querySelector('#composer').getBoundingClientRect();
   return Math.abs(grid.width-composer.width)<2;
  });
  assert.ok(fullWidth,'Closing voice must expand the composer across the entire workspace');
  assert.equal(await page.locator('.message.user').last().evaluate(el=>getComputedStyle(el).backgroundColor),'rgb(47, 47, 47)');
  await page.screenshot({path:path.resolve(__dirname,'../../local-data/chat-full-width.png')});
  await page.locator('#panel-toggle').click();
  assert.equal(await page.locator('#voice-panel').isVisible(),true);
  await page.locator('#clear').click();
  await page.waitForFunction(()=>!document.body.classList.contains('has-history'));
  await checkEmptyChat();
  assert.equal(await page.locator('nav [data-page="situation"]').count(),0);
  await page.locator('[data-page="settings"]').click();
  assert.equal(await page.locator('#voice-max-sentences').inputValue(),'3');
  await page.locator('#voice-max-sentences').fill('2');
  await page.locator('#voice-prompt').fill('Use short spoken answers.');
  await page.locator('#prompt-form button[type="submit"]').click();
  await page.waitForFunction(()=>document.querySelector('#prompts-saved').textContent==='Saved');
  const saved=JSON.parse(fs.readFileSync(path.join(data,'settings.json')));
  assert.equal(saved.voice_max_sentences,2);
  assert.equal(saved.voice_prompt,'Use short spoken answers.');
  await page.reload();
  await page.waitForFunction(()=>document.querySelector('#voice-max-sentences').value==='2');
  await page.locator('#setup-later').click();
  await page.locator('[data-page="settings"]').click();
  await page.locator('#reset-prompts').click();
  assert.equal(await page.locator('#voice-max-sentences').inputValue(),'3');
  assert.equal(JSON.parse(fs.readFileSync(path.join(data,'settings.json'))).voice_max_sentences,2);
  await page.locator('.prompt-disclosure summary').click();
  const editor=await page.locator('#system-prompt').boundingBox();
  assert.ok(editor.width>500,'System prompt must have a usable full-width editor');
  await page.screenshot({path:path.resolve(__dirname,'../../local-data/settings-design.png')});
  assert.deepEqual(errors,[]);
  await page.setViewportSize({width:1024,height:720});
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  console.log('PASS: Electron isolation, navigation, profile, map records, grounded chat, recovery document; empty chat at 1024/1440/2240px, shortcuts, history and clear transitions, voice panel layouts');
 }finally{if(app)await app.close();fs.rmSync(data,{recursive:true,force:true});}
})().catch(e=>{console.error(e);process.exitCode=1;});
