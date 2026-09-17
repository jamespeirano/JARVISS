// Exercise delayed/failing chat and audio controls through the real desktop bridge.
const {_electron:electron}=require('playwright');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path'),assert=require('node:assert/strict');
(async()=>{
 const root=path.resolve(__dirname,'../..'),test=fs.mkdtempSync(path.join(os.tmpdir(),'jarvis-feedback-'));
 let app;
 try{
  const linkType=process.platform==='win32'?'junction':'dir';
  fs.symlinkSync(path.join(root,'.venv'),path.join(test,'.venv'),linkType);
  fs.symlinkSync(path.join(root,'resources'),path.join(test,'resources'),linkType);
  fs.writeFileSync(path.join(test,'service.py'),`import sys,time,json
sys.path.insert(0,${JSON.stringify(root)})
from jarviss import service
from jarviss.storage import ROOT
from jarviss.voice import Voice
OriginalService=service.Service
class TestService(OriginalService):
 def __init__(self):
  super().__init__()
  self.ready=True
  self.model.chat=self.chat
  self.voice.start=self.start_voice
  self.voice.prepare_tts=lambda:None
  self.voice.tts=self
  self.voice.play_audio=self.play_audio
 def command(self,method,args):
  if method=='state':
   if (ROOT/'startup-fail').exists():raise RuntimeError('Operation timed out. Check Settings.')
   while (ROOT/'startup-hold').exists():time.sleep(.02)
  return super().command(method,args)
 def chat(self,*args,**kwargs):
  while not (ROOT/'reply').exists():time.sleep(.02)
  if (ROOT/'fail').exists():raise RuntimeError('Model test failure')
  return 'Local answer.'
 def start_voice(self):
  self.voice.on_status('Starting voice')
  while not (ROOT/'start-voice').exists():time.sleep(.02)
  if (ROOT/'fail-voice').exists():
   self.voice.on_status('Voice off')
   raise RuntimeError('Microphone is unavailable')
  self.voice.enabled.set();self.voice.on_status('Listening')
 def create(self,text,**kwargs):
  with (ROOT/'previews').open('a') as output:output.write(json.dumps(kwargs)+'\\n')
  return [0]*240,24000
 def play_audio(self,audio,rate,epoch,device):
  while epoch==self.voice.epoch and not (ROOT/'finish-preview').exists() and not self.voice.closed.is_set():time.sleep(.02)
service.Service=TestService
service.devices=lambda:[{'id':1,'name':'Test mic','host':'Test','input':True,'output':False},{'id':2,'name':'Test speaker','host':'Test','input':False,'output':True}]
service.main()
`);
  const env={...process.env,JARVISS_ROOT:test,JARVISS_DATA:path.join(test,'data'),JARVISS_APP_DATA:path.join(test,'app')};delete env.ELECTRON_RUN_AS_NODE;
  fs.writeFileSync(path.join(test,'startup-fail'),'');
  app=await electron.launch({args:[path.join(root,'electron')],env});const page=await app.firstWindow();
  const touch=name=>fs.writeFileSync(path.join(test,name),'');
  const remove=name=>fs.rmSync(path.join(test,name),{force:true});
  await page.locator('#startup-retry').waitFor({state:'visible'});
  assert.equal(await page.locator('#startup-message').innerText(),'Connecting took too long. Try again.');
  assert.equal(await page.locator('#error').isVisible(),false);
  assert.equal(await page.locator('aside').isVisible(),false);
  await page.locator('#startup-retry').click();
  await page.waitForFunction(()=>!document.querySelector('#startup-retry').hidden&&!document.querySelector('#startup-retry').disabled);
  remove('startup-fail');touch('startup-hold');
  await page.locator('#startup-retry').click();
  assert.equal(await page.locator('#startup-retry').isDisabled(),true);
  assert.equal(await page.locator('#startup-message').innerText(),'Checking setup…');
  remove('startup-hold');
  await page.waitForFunction(()=>document.querySelector('#status').textContent==='Ready');
  console.log('PASS startup timeout, repeated failure and retry with a delayed backend');
  await page.locator('#setup-later').click();
  await page.locator('#panel-toggle').click();
  await page.locator('#question').fill('Hello');await page.locator('#send').click();
  await page.locator('#response-wait').waitFor({state:'visible'});
  if(process.env.JARVISS_TEST_SCREENSHOT)await page.screenshot({path:process.env.JARVISS_TEST_SCREENSHOT});
  assert.equal(await page.locator('#messages').getAttribute('aria-busy'),'true');
  assert.equal(await page.locator('#send').isDisabled(),true);
  // Reload during inference restores progress from the service operation.
  await page.reload();await page.locator('#setup-later').click();
  await page.locator('#response-wait').waitFor({state:'visible'});
  touch('reply');
  await page.locator('.message.assistant').filter({hasText:'Local answer.'}).waitFor();
  await page.locator('#response-wait').waitFor({state:'detached'});
  await page.waitForFunction(()=>!document.querySelector('#send').disabled);
  assert.equal(await page.locator('#messages').getAttribute('aria-busy'),'false');
  touch('fail');remove('reply');
  await page.locator('#question').fill('Another question');await page.locator('#send').click();
  await page.locator('#response-wait').waitFor({state:'visible'});touch('reply');
  await page.getByRole('alert').filter({hasText:'Model test failure'}).waitFor();
  await page.locator('#response-wait').waitFor({state:'detached'});
  await page.waitForFunction(()=>!document.querySelector('#send').disabled);
  remove('fail');
  // Spoken questions also display the loader; it is not tied to clicking Send.
  remove('reply');await page.evaluate(()=>{window.jarviss.command('chat',{text:'Spoken question'}).catch(()=>{});});
  await page.locator('#response-wait').waitFor({state:'visible'});touch('reply');
  await page.locator('#response-wait').waitFor({state:'detached'});
  console.log('PASS chat loader: delayed text, backend/voice request, renderer reload, success and error');
  touch('fail-voice');
  await page.locator('#voice-toggle').click();
  await page.getByRole('button',{name:'Starting voice…',exact:true}).waitFor();
  assert.equal(await page.locator('#voice-toggle').isDisabled(),true);
  touch('start-voice');
  await page.getByRole('alert').filter({hasText:'Microphone is unavailable'}).waitFor();
  await page.waitForFunction(()=>!document.querySelector('#voice-toggle').disabled);
  remove('fail-voice');await page.locator('#voice-toggle').click();
  await page.getByRole('button',{name:'Stop voice mode',exact:true}).waitFor();
  assert.equal(await page.locator('#error').isVisible(),false);
  remove('reply');
  await page.evaluate(()=>{window.jarviss.command('chat',{text:'Voice question with a delayed answer'}).catch(()=>{});});
  await page.waitForFunction(()=>document.querySelector('#voice-badge').textContent==='GENERATING RESPONSE…');
  assert.equal(await page.locator('#orb').evaluate(el=>el.classList.contains('active')),true);
  await page.locator('[data-page="atlas"]').click();
  await page.locator('#map-fullscreen').click();
  await page.waitForFunction(()=>document.body.classList.contains('map-fullscreen'));
  assert.equal(await page.locator('#map-fullscreen').getAttribute('aria-pressed'),'true');
  assert.equal(await app.evaluate(({BrowserWindow})=>BrowserWindow.getAllWindows()[0].isFullScreen()),true);
  assert.equal(await page.locator('#status').innerText(),'Generating response…');
  assert.equal(await page.locator('aside').isVisible(),false);
  assert.equal(await page.locator('#map-search').isVisible(),true);
  await page.keyboard.press('Escape');
  await page.waitForFunction(()=>!document.body.classList.contains('map-fullscreen'));
  await page.locator('#map-fullscreen').click();
  await page.getByRole('button',{name:'Exit full screen',exact:true}).click();
  await page.waitForFunction(()=>!document.body.classList.contains('map-fullscreen'));
  assert.equal(await app.evaluate(({BrowserWindow})=>BrowserWindow.getAllWindows()[0].isFullScreen()),false);
  await page.locator('[data-page="assistant"]').click();
  await page.locator('#voice-toggle').click();
  assert.equal(await page.locator('#voice-badge').innerText(),'VOICE OFF');
  touch('reply');await page.locator('#response-wait').waitFor({state:'detached'});
  console.log('PASS full-screen map entry/button/Escape exits and voice generation feedback across pages; stopping voice clears its indicator');
  await page.locator('[data-page="settings"]').click();await page.locator('[data-settings="audio"]').click();
  await page.locator('#voice-name').selectOption('af_heart');
  await page.waitForFunction(()=>!document.querySelector('#voice-name').disabled);
  await page.locator('#test-speaker').click();
  await page.getByRole('button',{name:'Stop preview',exact:true}).waitFor();
  await page.waitForFunction(()=>document.querySelector('#voice-badge').textContent==='SPEAKING');
  assert.equal(JSON.parse(fs.readFileSync(path.join(test,'previews'),'utf8').trim()).voice,'af_heart');
  // Changing voice stops the old preview and saves immediately, without queueing.
  await page.locator('#voice-name').selectOption('am_michael');
  await page.waitForFunction(()=>!document.querySelector('#voice-name').disabled);
  await page.getByRole('button',{name:'Preview voice',exact:true}).waitFor();
  await page.locator('#test-speaker').click();
  await page.waitForFunction(()=>document.querySelector('#voice-badge').textContent==='SPEAKING');
  assert.deepEqual(fs.readFileSync(path.join(test,'previews'),'utf8').trim().split('\n').map(line=>JSON.parse(line).voice),['af_heart','am_michael']);
  await page.locator('#test-speaker').click();
  await page.getByRole('button',{name:'Preview voice',exact:true}).waitFor();
  assert.equal(await page.locator('#voice-badge').innerText(),'VOICE OFF');
  touch('finish-preview');await page.locator('#test-speaker').click();
  await page.getByRole('button',{name:'Stop preview',exact:true}).waitFor();
  await page.getByRole('button',{name:'Preview voice',exact:true}).waitFor();
  await page.reload();await page.locator('#setup-later').click();
  await page.locator('[data-page="settings"]').click();await page.locator('[data-settings="audio"]').click();
  assert.equal(await page.locator('#voice-name').inputValue(),'am_michael');
  assert.equal(await page.locator('#error').isVisible(),false);
  console.log('PASS voice controls: startup feedback, failure/retry, selected voice autosave, cancel, replace, completion and reload');
  // Reference links open their exact offline section, including after a reload.
  await page.locator('[data-page="assistant"]').click();
  await page.locator('#question').fill('How do I boil river water at 7000 feet?');await page.locator('#send').click();
  await page.locator('.answer-references button').first().waitFor();
  await page.reload();await page.locator('#setup-later').click();
  const reference=page.locator('.answer-references button').last();
  const sourceLabel=await reference.innerText();await reference.click();
  await page.locator('.reference-selected').waitFor();
  assert.equal(await page.locator('#reference-reader').isVisible(),true);
  assert.equal(await page.locator('.reference-selected > h3').innerText(),sourceLabel.split(' · ').slice(1).join(' · '));
  await page.locator('#reference-back').click();
  assert.equal(await page.locator('#assistant').isVisible(),true);
  await page.locator('[data-page="docs"]').click();
  await page.locator('#docs-search').fill('bowline');
  await page.locator('#reference-results button').filter({hasText:'Knots, rope and lashings'}).first().click();
  assert.equal(await page.locator('#docs-search').inputValue(),'bowline');
  await page.locator('.reference-selected').filter({hasText:'Bowline'}).waitFor();
  // Save dialog cancellation does not write; both exports preserve provenance.
  await app.evaluate(({dialog})=>{dialog.showSaveDialog=async()=>({canceled:true});});
  assert.equal(await page.evaluate(()=>window.jarviss.saveReference('field-water')),false);
  const markdown=path.join(test,'water.md'),pdf=path.join(test,'rope.pdf');
  await app.evaluate(({dialog},filePath)=>{dialog.showSaveDialog=async()=>({canceled:false,filePath});},markdown);
  assert.equal(await page.evaluate(()=>window.jarviss.saveReference('field-water')),true);
  assert.match(fs.readFileSync(markdown,'utf8'),/https:\/\/www.cdc.gov/);
  await app.evaluate(({dialog},filePath)=>{dialog.showSaveDialog=async()=>({canceled:false,filePath});},pdf);
  assert.equal(await page.evaluate(()=>window.jarviss.saveReference('army-rope','pdf')),true);
  assert.deepEqual(fs.readFileSync(pdf),fs.readFileSync(path.join(root,'resources/references/army-rope.pdf')));
  assert.match(await page.evaluate(()=>window.jarviss.saveReference('../private').catch(e=>e.message)),/not in the installed library/);
  if(process.env.JARVISS_DOCS_SCREENSHOT)await page.screenshot({path:process.env.JARVISS_DOCS_SCREENSHOT});
  console.log('PASS offline reference links, persisted conversation, section search, cancelled export, attributed Markdown/PDF export, unknown document rejection');

 }finally{
  for(const name of ['reply','start-voice','finish-preview'])fs.writeFileSync(path.join(test,name),'');
  if(app)await app.close();fs.rmSync(test,{recursive:true,force:true});
 }
})().catch(e=>{console.error(e);process.exitCode=1;});
