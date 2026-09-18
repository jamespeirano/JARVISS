// Exercise the packaged Python sidecar and actual local neural speech output.
const {_electron:electron}=require('playwright');
const fs=require('node:fs'),path=require('node:path'),os=require('node:os'),assert=require('node:assert/strict');
(async()=>{
 const data=fs.mkdtempSync(path.join(os.tmpdir(),'jarvis-audio-'));let app;
 try{
  const env={...process.env,JARVISS_ROOT:path.resolve(__dirname,'../..'),JARVISS_DATA:data,JARVISS_APP_DATA:data};delete env.ELECTRON_RUN_AS_NODE;
  app=await electron.launch({executablePath:process.env.TEST_PACKAGED,args:[],env});
  const page=await app.firstWindow();
  await page.waitForFunction(()=>document.querySelector('#status').textContent==='Model off');await page.locator('#setup-later').click();
  await page.evaluate(()=>{window.audioEvents=[];window.jarviss.subscribe(e=>window.audioEvents.push(e));});
  await page.locator('[data-page="settings"]').click();
  await page.locator('[data-settings="audio"]').click();
  assert.ok(await page.locator('#input-device option').count()>1);
  await page.locator('#test-speaker').click();
  await page.waitForFunction(()=>window.audioEvents.some(e=>e.event==='voice'&&e.data==='Speaking')||!document.querySelector('#error').hidden,null,{timeout:60000});
  assert.equal(await page.locator('#error').isVisible(),false,await page.locator('#error').textContent());
  await page.waitForFunction(()=>window.audioEvents.some(e=>e.event==='voice'&&e.data==='Voice off'),null,{timeout:30000});
  const events=await page.evaluate(()=>window.audioEvents);
  assert.deepEqual(events.filter(e=>e.event==='error'),[]);
  console.log('PASS: packaged Kokoro model, phonemizer, ONNX inference, device enumeration, native speaker playback, lifecycle completion');
  const settings=JSON.parse(fs.readFileSync(path.resolve(__dirname,'../../local-data/settings.json'),'utf8'));
  await page.evaluate(s=>window.jarviss.command('start_model',{path:s.model,layers:s.gpu_layers}),settings);
  for(let cycle=0;cycle<2;cycle++){
   const started=await page.evaluate(()=>window.jarviss.command('voice',{enabled:true}));
   assert.equal(started.enabled,true);
   await page.waitForFunction(()=>document.querySelector('#voice-badge').textContent==='LISTENING');
   const stopped=await page.evaluate(()=>window.jarviss.command('voice',{enabled:false}));
   assert.equal(stopped.enabled,false);
  }
  assert.deepEqual(await page.evaluate(()=>window.audioEvents.filter(e=>e.event==='error')),[]);
  console.log('PASS: packaged Qwen load and two real microphone start/pause cycles');
 }finally{if(app)await app.close();fs.rmSync(data,{recursive:true,force:true});}
})().catch(e=>{console.error(e);process.exitCode=1;});
