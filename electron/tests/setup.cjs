const {_electron:electron}=require('playwright');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path'),assert=require('node:assert/strict');
(async()=>{
 const root=path.resolve(__dirname,'../..'),test=fs.mkdtempSync(path.join(os.tmpdir(),'jarvis-setup-'));
 let app;
 try{
  fs.symlinkSync(path.join(root,'.venv'),path.join(test,'.venv'),'dir');
  fs.symlinkSync(path.join(root,'resources'),path.join(test,'resources'),'dir');
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
setup.prepare_basemap=lambda progress,cancel=None:ROOT/'fixture.pmtiles'
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
  assert.equal(await page.locator('aside').isVisible(),false);
  fs.writeFileSync(path.join(test,'startup-release'),'');
  await page.waitForFunction(()=>document.querySelector('#setup-download').disabled===false);
  assert.equal(await page.locator('#setup').isVisible(),true);
  assert.equal(await page.locator('aside').isVisible(),false);
  await page.locator('#setup-later').click();
  assert.equal(await page.locator('#assistant').isVisible(),true);
  assert.equal(await page.locator('aside').isVisible(),true);
  await page.reload();
  await page.waitForFunction(()=>!document.querySelector('#setup-download').disabled);
  assert.equal(await page.locator('#setup').isVisible(),true);
  assert.match(await page.locator('#recommended-model').innerText(),/Qwen 3.8/);
  assert.equal(await page.locator('#setup-models input').count(),3);
  for(const size of [{width:1024,height:720},{width:1440,height:940}]){
   await page.setViewportSize(size);
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
   await page.screenshot({path:path.join(root,`local-data/setup-${size.width}.png`)});
  }
  fs.writeFileSync(path.join(test,'hardware.json'),JSON.stringify({...hw,disk:2**30}));
  await page.locator('.setup-storage summary').click();await page.locator('#setup-recheck').click();
  await page.waitForFunction(()=>document.querySelector('#setup-warning').textContent.includes('storage'));
  assert.equal(await page.locator('#setup-download').isDisabled(),true);
  fs.writeFileSync(path.join(test,'hardware.json'),JSON.stringify(hw));await page.locator('#setup-recheck').click();
  await page.waitForFunction(()=>!document.querySelector('#setup-download').disabled);
  await page.locator('#model-options summary').click();await page.locator('input[value="compact"]').check();
  await page.waitForFunction(()=>document.querySelector('#recommended-model').textContent.includes('E2B'));
  await page.locator('#setup-download').click();
  await page.waitForFunction(()=>document.querySelector('#setup-detail').textContent==='Downloading model');
  assert.equal(await page.locator('#send').isDisabled(),true);
  await page.reload();
  await page.waitForFunction(()=>document.querySelector('#setup-pause').hidden===false);
  await page.locator('#setup-pause').click();
  await page.waitForFunction(()=>document.querySelector('#status').textContent==='Model not started');
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
  fs.unlinkSync(path.join(test,'fail'));await page.locator('#setup-download').click();
  await page.waitForFunction(()=>document.querySelector('#setup-size').textContent==='Ready offline');
  assert.equal(JSON.parse(fs.readFileSync(path.join(test,'data/settings.json'))).model_id,'compact');
  assert.equal(fs.existsSync(path.join(test,'data/conversation.json')),false);
  await page.locator('#setup-done').click();assert.equal(await page.locator('#assistant').isVisible(),true);
  await page.reload();await page.locator('#assistant').waitFor({state:'visible'});
  const model=JSON.parse(fs.readFileSync(path.join(test,'data/settings.json'))).model;
  fs.unlinkSync(path.resolve(test,model));
  await page.reload();await page.locator('#setup').waitFor({state:'visible'});
  console.log('PASS: startup hides chat, fresh setup first, explicit skip, failed setup/relaunch/retry, missing model recovery, recommendation, low storage, two window sizes, pause/reload, all components, unchanged conversation');
 }finally{fs.writeFileSync(path.join(test,'release'),'');if(app)await app.close();fs.rmSync(test,{recursive:true,force:true});}
})().catch(e=>{console.error(e);process.exitCode=1;});
