// Explicit integration check: real installed data and bundled engines, isolated records.
const {_electron:electron}=require('playwright');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path'),assert=require('node:assert/strict');
(async()=>{
 const executable=process.env.TEST_PACKAGED;
 if(!executable)throw new Error('Set TEST_PACKAGED to the built application executable.');
 const root=path.resolve(__dirname,'../..'),test=fs.mkdtempSync(path.join(os.tmpdir(),'jarvis-packaged-'));
 let app;
 try{
  fs.mkdirSync(path.join(test,'models'));
  const catalog=JSON.parse(fs.readFileSync(path.join(root,'resources/model-catalog.json')));
  for(const name of [...catalog.models.map(m=>m.filename),'kokoro','vosk-model-en-us-0.22-lgraph'])fs.symlinkSync(path.join(root,'models',name),path.join(test,'models',name));
  fs.symlinkSync(path.join(root,'local-maps'),path.join(test,'local-maps'));
  const env={...process.env,JARVISS_ROOT:test,JARVISS_DATA:path.join(test,'local-data'),JARVISS_APP_DATA:path.join(test,'app'),PATH:'/usr/bin:/bin'};
  delete env.ELECTRON_RUN_AS_NODE;delete env.JARVISS_RESOURCES;delete env.JARVISS_BUNDLED_RUNTIME;
  app=await electron.launch({executablePath:executable,env});const page=await app.firstWindow();
  await app.evaluate(({session})=>{globalThis.externalRequests=[];session.defaultSession.webRequest.onBeforeRequest((d,done)=>{if(/^https?:/.test(d.url)){globalThis.externalRequests.push(d.url);done({cancel:true});}else done({});});});
  await page.waitForFunction(()=>!document.querySelector('#setup-download').disabled,{},{timeout:60000});
  const plan=await page.evaluate(()=>window.jarviss.command('setup_plan'));
  assert.ok(plan.recommended);assert.equal(plan.selected,plan.recommended);assert.equal(plan.download_bytes,0);
  await page.locator('#setup-download').click();
  await page.waitForFunction(()=>document.querySelector('#setup-size').textContent==='Ready offline',{},{timeout:180000});
  assert.equal(fs.existsSync(path.join(test,'runtime')),false,'No runtime installed outside the app');
  assert.equal(fs.existsSync(path.join(test,'.venv')),false);
  const state=await page.evaluate(()=>window.jarviss.command('state'));
  assert.equal(state.ready,true);assert.equal(state.voiceReady,true);assert.equal(state.usRouting.ready,true);
  assert.equal(state.settings.model_id,plan.recommended);assert.equal(state.history.length,0);
  await page.locator('#setup-done').click();
  await page.locator('#question').fill('Translate into English: Mantener seco.');await page.locator('#send').click();
  await page.waitForFunction(()=>document.querySelectorAll('.message.assistant').length>0,{},{timeout:120000});
  assert.match(await page.locator('.message.assistant').last().innerText(),/keep dry/i);
  await page.locator('[data-page="atlas"]').click();
  await page.waitForFunction(()=>window.jarvisDetailMap?.isStyleLoaded(),{},{timeout:30000});
  await page.evaluate(async()=>{await window.jarviss.command('set_map_position',{lat:30.2672,lon:-97.7431});await refresh();window.offlineAtlas.center();});
  await page.waitForFunction(()=>window.jarvisDetailMap?.areTilesLoaded(),{},{timeout:30000});
  await page.locator('[data-page="assistant"]').click();
  await page.locator('#question').fill('Where is the nearest water?');await page.locator('#send').click();
  await page.waitForFunction(()=>document.querySelectorAll('.message.assistant').length===2,{},{timeout:120000});
  const answer=await page.locator('.message.assistant').last().innerText();assert.match(answer,/miles/);assert.match(answer,/Mapped walk/);
  assert.deepEqual(await app.evaluate(()=>globalThis.externalRequests),[]);
  await page.screenshot({path:path.join(root,'local-data/packaged-setup.png')});
  console.log('PASS: packaged hardware recommendation, cached full setup, real model response, voice engines, map render and walking route; no external renderer requests or separate Python/Node/runtime installation');
 }finally{if(app)await app.close();fs.rmSync(test,{recursive:true,force:true});}
})().catch(e=>{console.error(e);process.exitCode=1;});
