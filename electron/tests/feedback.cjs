// Exercise delayed/failing chat and audio controls through the real desktop bridge.
const {_electron:electron}=require('playwright');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path'),assert=require('node:assert/strict');
const pageErrors=[];
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
 def chat(self,payload,*args,**kwargs):
  while not (ROOT/'reply').exists():time.sleep(.02)
  if (ROOT/'fail').exists():raise RuntimeError('Model test failure')
  if 'Give me the steps' in json.dumps(payload[-1]):return 'Do this:\\n\\n1. Filter it\\n2. Boil it\\n\\n**Do not** drink it cold.'
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
  fs.mkdirSync(path.join(test,'data'));
  fs.writeFileSync(path.join(test,'data/conversation.json'),JSON.stringify([{role:'user',content:'Earlier question'},{role:'assistant',content:'Earlier partial answer',references:[],truncated:true}]));
  fs.writeFileSync(path.join(test,'startup-fail'),'');
  app=await electron.launch({args:[path.join(root,'electron')],env});const page=await app.firstWindow();
  page.on('pageerror',e=>pageErrors.push(e.message));
  const touch=name=>fs.writeFileSync(path.join(test,name),'');
  const remove=name=>fs.rmSync(path.join(test,name),{force:true});
  await page.locator('#startup-retry').waitFor({state:'visible'});
  assert.equal(await page.locator('#startup-message').innerText(),'Connecting took too long. Try again.');
  assert.equal(await page.locator('#error').isVisible(),false);
  assert.equal(await page.locator('aside').evaluate(el=>el.inert),true,'The rail stays visible but inert during startup');
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
  // The seeded transcript carries a cut-short reply; the last assistant message owns the only Retry.
  await page.locator('.message.assistant .cut-short').filter({hasText:'Reply was cut short'}).waitFor();
  assert.equal(await page.locator('.message').first().getAttribute('role'),'group');
  assert.equal(await page.locator('.message.assistant .retry').count(),1);
  assert.equal(await page.locator('#response-wait').evaluate(el=>!el.closest('#messages')),true,'The thinking status lives outside the log');
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
  await page.locator('#response-wait').waitFor({state:'hidden'});
  await page.waitForFunction(()=>!document.querySelector('#send').disabled);
  assert.equal(await page.locator('#messages').getAttribute('aria-busy'),'false');
  touch('fail');remove('reply');
  await page.locator('#question').fill('Another question');await page.locator('#send').click();
  await page.locator('#response-wait').waitFor({state:'visible'});touch('reply');
  await page.getByRole('alert').filter({hasText:'Model test failure'}).waitFor();
  assert.equal(await page.locator('#composer-notice').isVisible(),true,'Chat errors sit under the composer');
  assert.equal(await page.locator('#error').isVisible(),false);
  assert.equal(await page.locator('#composer-notice button').filter({hasText:'Open Settings'}).count(),1);
  await page.locator('#response-wait').waitFor({state:'hidden'});
  await page.waitForFunction(()=>!document.querySelector('#send').disabled);
  remove('fail');
  // Spoken questions also display the loader; it is not tied to clicking Send.
  remove('reply');await page.evaluate(()=>{window.jarviss.command('chat',{text:'Spoken question'}).catch(()=>{});});
  await page.locator('#response-wait').waitFor({state:'visible'});touch('reply');
  await page.locator('#response-wait').waitFor({state:'hidden'});
  console.log('PASS chat loader: delayed text, backend/voice request, renderer reload, success and error');
  // Light markdown in replies, Copy, Retry and the two-step Clear.
  await page.locator('#question').fill('Give me the steps');await page.locator('#send').click();
  await page.locator('.message.assistant ol li').filter({hasText:'Boil it'}).waitFor();
  const last=page.locator('.message.assistant').last();
  assert.equal(await last.locator('strong').innerText(),'Do not');
  assert.equal(await page.locator('.message.assistant .retry').count(),1);
  assert.equal(await last.locator('.retry').count(),1,'Retry moves to the newest reply');
  await page.evaluate(()=>{window.copied=[];navigator.clipboard.writeText=text=>{window.copied.push(text);return Promise.resolve();};});
  await last.locator('.copy').click();
  assert.match(await page.evaluate(()=>window.copied[0]),/^Do this:\n\n1\. Filter it/);
  assert.equal(await page.locator('#toast').innerText(),'Copied');
  const before=await page.locator('.message.assistant').count();
  await last.locator('.retry').click();
  assert.match(await page.locator('.message.user').last().innerText(),/^You:\s*Give me the steps$/); // the speaker label is visually hidden but read out
  await page.waitForFunction(n=>document.querySelectorAll('.message.assistant').length===n+1,before);
  await page.locator('#clear').click();
  await page.locator('.chat-footer .confirm').filter({hasText:'Clear the conversation?'}).waitFor();
  await page.locator('.chat-footer .confirm button').filter({hasText:'No'}).click();
  assert.equal(await page.locator('.message.assistant').count(),before+1,'No keeps the transcript');
  await page.locator('#clear').click();await page.locator('.chat-footer .confirm button').filter({hasText:'Yes'}).click();
  await page.waitForFunction(()=>!document.body.classList.contains('has-history'));
  assert.equal(await page.locator('.message').count(),0);
  // Quick prompts come from the backend guides: a prompt ending in ":" is inserted, a complete one is sent.
  assert.deepEqual(await page.locator('#quick-actions button').allInnerTexts(),['Water','Food after a power cut','First aid basics','Check a building','Choose what comes first','Make supplies last']);
  await page.locator('#quick-actions button').filter({hasText:'Water'}).click();
  assert.equal(await page.locator('#question').inputValue(),'Can I use this water? Source: ');
  assert.equal(await page.locator('#question').evaluate(el=>el===document.activeElement),true);
  await page.locator('#question').fill('');
  await page.locator('#quick-actions button').filter({hasText:'Make supplies last'}).click();
  await page.locator('.message.user').filter({hasText:'Using my saved supplies, what will run out first?'}).waitFor();
  await page.locator('#response-wait').waitFor({state:'hidden'});
  console.log('PASS quick prompts from state, list rendering, Copy, Retry, two-step Clear');
  touch('fail-voice');
  await page.locator('#panel-toggle').click(); // the hidden inspector persisted across the reload
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
  await page.waitForFunction(()=>document.querySelector('#voice-badge').textContent==='Thinking…');
  assert.equal(await page.locator('#orb').evaluate(el=>el.classList.contains('active')),true);
  await page.locator('[data-page="atlas"]').click();
  await page.locator('#map-fullscreen').click();
  await page.waitForFunction(()=>document.body.classList.contains('map-fullscreen'));
  assert.equal(await page.locator('#map-fullscreen').getAttribute('aria-pressed'),'true');
  assert.equal(await app.evaluate(({BrowserWindow})=>BrowserWindow.getAllWindows()[0].isFullScreen()),true);
  assert.equal(await page.locator('#status').innerText(),'Thinking');
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
  assert.equal(await page.locator('#voice-badge').evaluate(el=>el.textContent),'Voice off');
  touch('reply');await page.locator('#response-wait').waitFor({state:'hidden'});
  console.log('PASS full-screen map entry/button/Escape exits and voice generation feedback across pages; stopping voice clears its indicator');
  await page.locator('[data-page="settings"]').click();await page.locator('[data-settings="audio"]').click();
  await page.locator('#voice-name').selectOption('af_heart');
  await page.waitForFunction(()=>!document.querySelector('#voice-name').disabled);
  await page.locator('#test-speaker').click();
  await page.getByRole('button',{name:'Stop preview',exact:true}).waitFor();
  await page.waitForFunction(()=>document.querySelector('#voice-badge').textContent==='Speaking');
  assert.equal(JSON.parse(fs.readFileSync(path.join(test,'previews'),'utf8').trim()).voice,'af_heart');
  // Changing voice stops the old preview and saves immediately, without queueing.
  await page.locator('#voice-name').selectOption('am_michael');
  await page.waitForFunction(()=>!document.querySelector('#voice-name').disabled);
  await page.getByRole('button',{name:'Preview voice',exact:true}).waitFor();
  await page.locator('#test-speaker').click();
  await page.waitForFunction(()=>document.querySelector('#voice-badge').textContent==='Speaking');
  assert.deepEqual(fs.readFileSync(path.join(test,'previews'),'utf8').trim().split('\n').map(line=>JSON.parse(line).voice),['af_heart','am_michael']);
  await page.locator('#test-speaker').click();
  await page.getByRole('button',{name:'Preview voice',exact:true}).waitFor();
  assert.equal(await page.locator('#voice-badge').evaluate(el=>el.textContent),'Voice off');
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
  await page.locator('.answer-references .ref-row').first().waitFor();
  await page.reload();await page.locator('#setup-later').click();
  const reference=page.locator('.answer-references .ref-row').last();
  assert.equal(await reference.evaluate(el=>el.tagName==='BUTTON'&&!!el.querySelector('svg use[href="#i-docs"]')),true,'Reference passages are quiet rows with a docs icon');
  const sourceLabel=await reference.innerText();await reference.click();
  await page.locator('.reference-selected').waitFor();
  assert.equal(await page.locator('#reference-reader').isVisible(),true);
  assert.equal(await page.locator('.reference-selected > h3').innerText(),sourceLabel.split(' · ').slice(1).join(' · '));
  assert.equal(await page.locator('#reference-back-label').innerText(),'Back to Chat');
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
  assert.deepEqual(pageErrors,[]);
 }finally{
  for(const name of ['reply','start-voice','finish-preview'])fs.writeFileSync(path.join(test,name),'');
  if(app)await app.close();fs.rmSync(test,{recursive:true,force:true});
 }
})().catch(e=>{console.error(e);if(pageErrors.length)console.error('Renderer errors:',pageErrors);process.exitCode=1;});
