const {_electron:electron}=require('playwright');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path'),assert=require('node:assert/strict');
(async()=>{
 const root=path.resolve(__dirname,'../..'),test=fs.mkdtempSync(path.join(os.tmpdir(),'jarvis-setup-'));
 const shots=process.env.JARVISS_TEST_SHOTS||test; // never the user's own local-data
 let app;
 try{
  fs.symlinkSync(path.join(root,'.venv'),path.join(test,'.venv'),process.platform==='win32'?'junction':'dir');
  fs.symlinkSync(path.join(root,'resources'),path.join(test,'resources'),process.platform==='win32'?'junction':'dir');
  const hw={system:'Darwin',arch:'arm64',memory:36*2**30,available:30*2**30,disk:100*2**30,cores:8,unified:true,gpus:[],accelerated:true};
  fs.writeFileSync(path.join(test,'hardware.json'),JSON.stringify(hw));
  fs.writeFileSync(path.join(test,'service.py'),`import sys,time,json
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,${JSON.stringify(root)})
from jarviss import service,setup,us_routing
from jarviss.storage import ROOT,MODELS,write_json
while not (ROOT/'startup-release').exists():time.sleep(.03)
setup.inspect=lambda *_:json.loads((ROOT/'hardware.json').read_text())
class Router:
 def __init__(self,*a,**k):pass
 def status(self):return {'ready':(ROOT/'map-ready').exists(),'engineReady':True,'installedFiles':0,'totalFiles':0}
service.USRouter=us_routing.USRouter=Router
setup.prepare_runtime=lambda _:None
def model(id,progress):
 while not (ROOT/'release').exists():
  progress('Downloading model');time.sleep(.03)
 if (ROOT/'fail').exists():raise RuntimeError('Download interrupted. Retry setup.')
 m=setup.choose(id);p=MODELS/m['filename'];p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('wb') as f:f.truncate(m['bytes'])
 return p
setup.prepare_model=model
def voice(progress):
 for f in ['vosk-model-en-us-0.22-lgraph/am/final.mdl','kokoro/kokoro-v1.0.onnx','kokoro/voices-v1.0.bin']:
  p=MODELS/f;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b'fixture')
setup.prepare_voice=voice
def basemap(progress,cancel=None):
 while (ROOT/'hold-map').exists():
  progress('US map · 12%');time.sleep(.03)
 return ROOT/'fixture.pmtiles'
setup.prepare_basemap=basemap
def routing(progress):
 (ROOT/'map-ready').touch()
setup.prepare_routing=routing
original_init=service.Service.__init__
def init(self):
 original_init(self)
 self.model.start=lambda *a,**k:None
 self.model.chat=lambda *a,**k:'Ready'
 self.voice.prepare_tts=lambda:None
 self.voice.make_recognizer=lambda _:None
service.Service.__init__=init
original_command=service.Service.command
def command(self,method,args):
 if method=='import_basemap':
  self.archive=SimpleNamespace(path=Path(args['path']),pack={'osm_timestamp':'test'})
  return self.state()
 return original_command(self,method,args)
service.Service.command=command
service.main()
`);
  const env={...process.env,JARVISS_ROOT:test,JARVISS_DATA:path.join(test,'data'),JARVISS_APP_DATA:path.join(test,'app')};delete env.ELECTRON_RUN_AS_NODE;
  app=await electron.launch({args:[path.join(root,'electron')],env});let page=await app.firstWindow();
  await page.locator('#startup').waitFor({state:'visible'});
  assert.equal(await page.locator('#assistant').isVisible(),false);
  assert.equal(await page.locator('aside').evaluate(el=>el.inert),true,'The rail stays visible but inert during startup');
  fs.writeFileSync(path.join(test,'startup-release'),'');
  await page.waitForFunction(()=>document.querySelector('#setup-download').disabled===false);
  assert.equal(await page.locator('#setup').isVisible(),true);
  assert.equal(await page.locator('aside').evaluate(el=>el.inert),true,'The rail stays visible but inert during setup');
  await page.locator('#setup-later').click();
  await page.locator('#assistant.visible').waitFor(); // the skip is saved before the page changes
  assert.equal(await page.locator('#assistant').isVisible(),true);
  assert.equal(await page.locator('aside').isVisible(),true);
  assert.equal(await page.locator('aside').evaluate(el=>el.inert),false);
  await page.reload();
  await page.waitForFunction(()=>!document.querySelector('#setup-download').disabled);
  assert.equal(await page.locator('#setup').isVisible(),true);
  assert.match(await page.locator('#setup-components li').first().innerText(),/Qwen 3.8/,'The recommended model is named in the AI model row');
  assert.doesNotMatch(await page.locator('#setup').innerText(),/Abliterated/);
  assert.equal(await page.locator('#setup-models input').count(),3);
  // Component rows carry the size still to fetch; chat-only names the model download alone.
  const rows=await page.locator('#setup-components li').allInnerTexts();
  assert.equal(rows.length,5);
  assert.match(rows[0],/^AI model · Qwen 3.8[^\n]*\s+\d+\.\d GB\s+To download\s+Change$/,'The model row names the chosen model and offers Change');assert.match(rows[1],/Voice\s+0\.5 GB\s+To download/);assert.match(rows[4],/Guides\s+Ready/);
  assert.match(await page.locator('#setup-chat-only').innerText(),/^Download chat only \(≈\d+\.\d GB\)$/);
  assert.equal(await page.locator('#setup-bar').getAttribute('max'),'100');
  for(const size of [{width:1024,height:720},{width:1440,height:940}]){
   await page.setViewportSize(size);
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
   await page.screenshot({path:path.join(shots,`setup-${size.width}.png`)});
  }
  fs.writeFileSync(path.join(test,'hardware.json'),JSON.stringify({...hw,disk:2**30}));
  await page.locator('.setup-storage summary').click();await page.locator('#setup-recheck').click();
  await page.waitForFunction(()=>document.querySelector('#setup-warning').textContent.includes('storage'));
  assert.equal(await page.locator('#setup-download').isDisabled(),true);
  fs.writeFileSync(path.join(test,'hardware.json'),JSON.stringify(hw));await page.locator('#setup-recheck').click();
  await page.waitForFunction(()=>!document.querySelector('#setup-download').disabled);
  await page.locator('#setup-components button').filter({hasText:'Change'}).click(); // Change opens the other models
  await page.waitForFunction(()=>document.querySelector('#model-options').open);
  await page.locator('#setup-models label').filter({has:page.locator('input[value="compact"]')}).click();
  await page.waitForFunction(()=>document.querySelector('#setup-components li').textContent.includes('E2B'),null,{timeout:10000}); // the model row follows the selection
  await page.locator('#setup-download').click();
  await page.waitForFunction(()=>document.querySelector('#setup-detail').textContent==='Downloading model');
  assert.equal(await page.locator('#setup-chat-only').isVisible(),false,'Chat-only is not offered mid-run');
  assert.equal(await page.locator('#send').isDisabled(),true);
  await page.locator('#setup-later').click();
  await page.locator('[data-page="settings"]').click();
  await page.locator('[data-settings="model"]').click();
  assert.equal(await page.locator('#download-model').isEnabled(),true,'Active setup must remain accessible');
  await page.locator('#download-model').click();
  await page.locator('#setup-pause').waitFor({state:'visible'});
  await page.reload();
  await page.waitForFunction(()=>document.querySelector('#setup-pause').hidden===false);
  await page.locator('#setup-pause').click();
  await page.waitForFunction(()=>document.querySelector('#status').textContent==='Model off');
  await page.waitForFunction(()=>document.querySelector('#setup-download').textContent==='Continue setup');
  fs.writeFileSync(path.join(test,'fail'),'');
  fs.writeFileSync(path.join(test,'release'),'');await page.locator('#setup-download').click();
  await page.waitForFunction(()=>document.querySelector('#setup-warning').textContent.includes('Download interrupted'));
  assert.equal(await page.locator('#setup').isVisible(),true);
  assert.equal(await page.locator('#error').isVisible(),false);
  await app.close();
  app=await electron.launch({args:[path.join(root,'electron')],env});page=await app.firstWindow();
  await page.waitForFunction(()=>!document.querySelector('#setup-download').disabled);
  assert.equal(await page.locator('#setup').isVisible(),true);
  assert.match(await page.locator('#setup-warning').innerText(),/Download interrupted/);
  fs.unlinkSync(path.join(test,'fail'));fs.writeFileSync(path.join(test,'hold-map'),'');
  await page.locator('#setup-download').click();
  await page.waitForFunction(()=>document.querySelector('#setup-detail').textContent==='US map · 12%');
  await page.locator('#setup-later').click();
  await page.waitForFunction(()=>!document.querySelector('#send').disabled);
  await page.locator('#question').fill('Hello Jarvis');await page.locator('#send').click();
  await page.locator('.message.assistant').filter({hasText:'Ready'}).waitFor();
  await page.locator('[data-page="atlas"]').click();
  assert.equal(await page.locator('#city-search-form button').isDisabled(),true);
  assert.match(await page.locator('#location-search-status').evaluate(el=>el.textContent),/Map not ready/); // inside the collapsed picker
  await page.locator('#map-view-setup').click();
  // An unfinished basemap extract restarts from zero, so the first click only asks.
  await page.locator('#setup-pause').click();
  assert.equal(await page.locator('#setup-pause').innerText(),'Restart map later? Pause anyway');
  await page.waitForTimeout(150);assert.equal(await page.locator('#setup-pause').innerText(),'Restart map later? Pause anyway','Progress ticks must not clear the confirmation');
  assert.equal(await page.locator('#status').innerText(),'Ready');assert.notEqual(await page.locator('#setup-download').innerText(),'Continue setup','The first click must not pause');
  await page.locator('#setup-pause').focus();await page.keyboard.press('Enter');
  await page.waitForFunction(()=>document.querySelector('#setup-download').textContent==='Continue setup');
  assert.equal(await page.locator('#status').innerText(),'Ready','Pause must keep the validated model running');
  await app.close();
  // "Set up later" was remembered: with a working model the next launch opens Chat with a slim notice, not Setup.
  app=await electron.launch({args:[path.join(root,'electron')],env});page=await app.firstWindow();
  await page.waitForFunction(()=>document.querySelector('#status').textContent==='Ready');
  await page.locator('#assistant.visible').waitFor();
  assert.equal(await page.locator('#setup').isVisible(),false);
  assert.match(await page.locator('#setup-skipped').innerText(),/US maps not downloaded/);
  assert.equal(JSON.parse(fs.readFileSync(path.join(test,'data/setup.json'))).skipped,true);
  await page.locator('#question').fill('Hello again');await page.locator('#send').click();
  await page.locator('.message.assistant').filter({hasText:'Ready'}).nth(1).waitFor();
  await page.locator('#setup-skipped-open').click();await page.locator('#setup.visible').waitFor();
  fs.unlinkSync(path.join(test,'hold-map'));
  await page.locator('#setup-download').click();
  await page.waitForFunction(()=>document.querySelector('#setup-size').textContent==='Ready offline');
  assert.equal(JSON.parse(fs.readFileSync(path.join(test,'data/settings.json'))).model_id,'compact');
  assert.equal(JSON.parse(fs.readFileSync(path.join(test,'data/conversation.json'))).length,4,'Setup must not add its validation exchange to chat');
  await page.locator('#setup-done').click();assert.equal(await page.locator('#assistant').isVisible(),true);
  assert.equal(await page.locator('#setup-skipped').isVisible(),false,'The notice goes away once maps are installed');
  await page.reload();await page.locator('#assistant').waitFor({state:'visible'});
  const model=JSON.parse(fs.readFileSync(path.join(test,'data/settings.json'))).model;
  fs.unlinkSync(path.resolve(test,model));
  await page.reload();await page.locator('#setup').waitFor({state:'visible'});
  console.log('PASS: startup hides chat, fresh setup first, explicit skip remembered across relaunch, failed setup/relaunch/retry, missing model recovery, recommendation, component sizes, chat-only label, low storage, two window sizes, pause/reload, basemap pause confirmation, all components, unchanged conversation');
 }finally{fs.writeFileSync(path.join(test,'release'),'');fs.rmSync(path.join(test,'hold-map'),{force:true});if(app)await app.close();fs.rmSync(test,{recursive:true,force:true});}
})().catch(e=>{console.error(e);process.exitCode=1;});
