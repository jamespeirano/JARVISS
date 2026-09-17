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
  app=await electron.launch({args:[path.join(root,'electron')],env});const page=await app.firstWindow();
  const touch=name=>fs.writeFileSync(path.join(test,name),'');
  const remove=name=>fs.rmSync(path.join(test,name),{force:true});
  await page.waitForFunction(()=>document.querySelector('#status').textContent==='Ready');
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
  await page.locator('#voice-toggle').click();
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
 }finally{
  for(const name of ['reply','start-voice','finish-preview'])fs.writeFileSync(path.join(test,name),'');
  if(app)await app.close();fs.rmSync(test,{recursive:true,force:true});
 }
})().catch(e=>{console.error(e);process.exitCode=1;});
