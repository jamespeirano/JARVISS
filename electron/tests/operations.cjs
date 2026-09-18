const {_electron:electron}=require('playwright');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path'),assert=require('node:assert/strict');
(async()=>{
 const root=path.resolve(__dirname,'../..'),test=fs.mkdtempSync(path.join(os.tmpdir(),'jarvis-operations-'));
 let app;
 try{
  const linkType=process.platform==='win32'?'junction':'dir';
  fs.symlinkSync(path.join(root,'.venv'),path.join(test,'.venv'),linkType);
  fs.symlinkSync(path.join(root,'resources'),path.join(test,'resources'),linkType);
  fs.writeFileSync(path.join(test,'service.py'),`import sys,time\nfrom pathlib import Path\nsys.path.insert(0,${JSON.stringify(root)})\nfrom jarviss import service\nfrom jarviss.storage import ROOT,DATA,write_json\ndef prepare(progress):\n    progress('kokoro-v1.0.onnx: 60 MB / 310 MB')\n    while not (ROOT/'release').exists(): time.sleep(.03)\n    model=ROOT/'models'/'test.gguf'\n    model.parent.mkdir(parents=True,exist_ok=True)\n    model.write_bytes(b'test-only')\n    write_json(DATA/'settings.json',{'model':'models/test.gguf','gpu_layers':0})\nservice.prepare_qwen=prepare\nfrom jarviss.setup import SetupPaused\ndef prepare_us(progress,cancel=None):\n    while not (ROOT/'map-release').exists():\n        progress('US map · 1.0 GB / 20 GB · 5%' if (ROOT/'map-extract').exists() else 'Downloading map tool')\n        if cancel is not None and cancel.is_set(): raise SetupPaused()\n        time.sleep(.03)\n    raise RuntimeError('map fixture finished')\nservice.prepare_us=prepare_us\nservice.main()\n`);
  const env={...process.env,JARVISS_ROOT:test,JARVISS_DATA:path.join(test,'data'),JARVISS_APP_DATA:path.join(test,'app')};delete env.ELECTRON_RUN_AS_NODE;
  app=await electron.launch({args:[path.join(root,'electron')],env});const page=await app.firstWindow();
  await page.waitForFunction(()=>document.querySelector('#status').textContent==='Model not started');
  await page.locator('#setup-later').click();
  assert.equal(await page.locator('#start-model').isDisabled(),true);
  await page.locator('[data-page="settings"]').click();await page.locator('[data-settings="model"]').click();
  await page.evaluate(()=>{call('download_model',{}).catch(()=>{});});
  await page.waitForFunction(()=>document.querySelector('#progress').textContent.includes('60 MB'));
  assert.equal(await page.locator('#start-model').isDisabled(),true);
  assert.equal(await page.locator('#download-voice').isDisabled(),true);
  assert.equal(await page.locator('#send').isDisabled(),true);
  assert.match(await page.locator('#status').innerText(),/Preparing model and voice/);
  assert.match(await page.locator('#model-setup-status').innerText(),/60 MB/);
  // A renderer reload must restore the backend's ongoing work, not start a second operation.
  await page.reload();
  await page.waitForFunction(()=>document.querySelector('#status').textContent==='Preparing model and voice');
  await page.locator('#setup-later').click();
  assert.equal(await page.locator('#start-model').isDisabled(),true);
  assert.match(await page.locator('#progress').innerText(),/60 MB/);
  assert.equal(await page.locator('#error').isVisible(),false);
  fs.writeFileSync(path.join(test,'release'),'');
  await page.waitForFunction(()=>document.querySelector('#status').textContent==='Model not started');
  await page.waitForFunction(()=>document.querySelector('#model-name').textContent.includes('test.gguf'));
  assert.equal(await page.locator('#start-model').isDisabled(),false);
  assert.equal(await page.locator('#download-model').isDisabled(),false);
  assert.match(await page.locator('#model-name').innerText(),/test.gguf/);
  assert.equal(await page.locator('#error').isVisible(),false);
  // The Maps tab can pause its own download; a basemap extract asks once because it cannot resume.
  await page.locator('[data-page="atlas"]').click();
  const pause=page.locator('#map-pause'),download=page.locator('#download-us-maps');
  assert.equal(await pause.isVisible(),false);
  for(const extract of [false,true]){
   if(extract)fs.writeFileSync(path.join(test,'map-extract'),'');
   await download.click();
   await pause.waitFor({state:'visible'});
   await page.waitForFunction(extract=>document.querySelector('#map-progress').textContent.startsWith(extract?'US map ·':'Downloading map tool'),extract);
   assert.equal(await download.isDisabled(),true);assert.equal(await pause.innerText(),'Pause');
   await page.reload();
   await page.waitForFunction(()=>document.querySelector('#status').textContent==='Preparing US offline maps');
   await page.locator('#setup-later').click();await page.locator('[data-page="atlas"]').click();
   await pause.waitFor({state:'visible'});
   assert.match(await page.locator('#map-progress').innerText(),extract?/^US map ·/:/map tool/,'Reload restores the map download progress');
   await pause.click();
   if(extract){
    assert.equal(await pause.innerText(),'Restart map later? Pause anyway');assert.equal(await pause.isEnabled(),true);
    await page.waitForTimeout(150);assert.equal(await pause.innerText(),'Restart map later? Pause anyway','Progress ticks must not clear the confirmation');
    assert.equal(await page.locator('#status').innerText(),'Preparing US offline maps','The first click must not pause');
    await pause.click();
   }
   await page.waitForFunction(()=>document.querySelector('#status').textContent==='Model not started');
   await page.waitForFunction(()=>document.querySelector('#map-pause').hidden);
   assert.match(await page.locator('#map-progress').innerText(),/paused/i);
   assert.equal(await download.isEnabled(),true);assert.equal(await page.locator('#start-model').isEnabled(),true);
  }
  console.log('PASS: no empty model start, conflicting controls disabled, progress visible, reload preserves preparation, completion restores controls, Maps-tab pause with basemap confirmation');
 }finally{fs.writeFileSync(path.join(test,'release'),'');fs.writeFileSync(path.join(test,'map-release'),'');if(app)await app.close();fs.rmSync(test,{recursive:true,force:true});}
})().catch(e=>{console.error(e);process.exitCode=1;});
