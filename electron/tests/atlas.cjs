const {_electron:electron}=require('playwright');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path'),assert=require('node:assert/strict');
(async()=>{
 const data=fs.mkdtempSync(path.join(os.tmpdir(),'jarvis-atlas-'));
 const shots=process.env.JARVISS_TEST_SHOTS||data; // screenshots never land in the user's own local-data
 const cachedIndex=path.resolve(__dirname,'../../local-data/map-index');
 if(fs.existsSync(cachedIndex))fs.cpSync(cachedIndex,path.join(data,'map-index'),{recursive:true});
 let app;
 try{
  const env={...process.env,JARVISS_DATA:data,JARVISS_APP_DATA:data};delete env.ELECTRON_RUN_AS_NODE;
  app=await electron.launch({args:[path.resolve(__dirname,'..')],env});
  await app.evaluate(({session})=>{globalThis.externalRequests=[];session.defaultSession.webRequest.onBeforeRequest((details,done)=>{if(/^https?:/.test(details.url)){globalThis.externalRequests.push(details.url);done({cancel:true});}else done({});});});
  const page=await app.firstWindow();const errors=[];page.on('pageerror',e=>errors.push(e.message));
  page.on('console',m=>{if(m.type()==='error')console.error('renderer:',m.text());});
  await page.waitForFunction(()=>document.querySelector('#status').textContent==='Model off');await page.locator('#setup-later').click();
  await page.locator('#assistant.visible').waitFor();
  await page.locator('[data-page="atlas"]').click();
  await page.waitForFunction(()=>window.jarvisDetailMap?.isStyleLoaded(),{},{timeout:30000});
  assert.match(await page.locator('#map-local-status').innerText(),/Offline/);
  // Search by human place names; neither search nor city selection may set a position.
  assert.equal(await page.evaluate(async()=>(await window.jarviss.command('state')).profile.lat),undefined);
  await page.locator('#set-position-menu summary').click();await page.locator('#find-location').click();await page.locator('#city-search').fill('Austin, Texas');
  await page.locator('#city-search-form button').click();
  await page.waitForFunction(()=>document.querySelectorAll('#location-results button').length>0,{},{timeout:120000});
  await page.locator('#location-results button').first().click();
  assert.equal(await page.evaluate(async()=>(await window.jarviss.command('state')).profile.lat),undefined);
  assert.equal(fs.existsSync(path.join(data,'profile.json')),false);
  await page.locator('#landmark-search').fill('CVS Pharmacy');await page.locator('#landmark-search-form button').click();
  await page.waitForFunction(()=>document.querySelector('#location-results')?.textContent.includes('CVS Pharmacy'));
  await page.locator('#location-results button').first().click();
  await page.locator('.maplibregl-popup-content button').filter({hasText:'Set as my position'}).click();
  await page.waitForFunction(async()=>(await window.jarviss.command('state')).profile.lat!=null);
  assert.equal(typeof JSON.parse(fs.readFileSync(path.join(data,'profile.json'))).lat,'number');
  await page.screenshot({path:path.join(shots,'location-confirmed.png')});
  await page.evaluate(async()=>{await window.jarviss.command('set_map_position',{lat:30.2672,lon:-97.7431});await refresh();window.offlineAtlas.center();});
  await page.locator('#map-search').fill('pharmacy');
  await page.waitForFunction(()=>document.querySelectorAll('#places .place-card').length>0);
  assert.match(await page.locator('#places').innerText(),/pharmacy · [\d.]+ (miles|ft)/);
  assert.equal(await page.locator('#places .places-footnote').innerText(),'Distances are straight-line');
  assert.match(await page.locator('#map-caption').innerText(),/^Map data from .+ · Searches cover 3 mi around you$/);
  assert.match(await page.locator('#map-result-count').innerText(),/^\d+ places?$/);
  await page.waitForFunction(()=>window.jarvisDetailMap?.areTilesLoaded(),{},{timeout:30000});
  // Click a named result on the actual map, then route through the popup.
  const named=await page.evaluate(async()=>{
   const rows=await window.jarviss.command('nearest',{query:'pharmacy'});
   const place=rows.find(p=>p.distance_m>20&&p.distance_m<5000);if(!place)throw new Error('No suitable route destination');
   window.offlineAtlas.results([place]);window.jarvisDetailMap.jumpTo({center:[place.point[1],place.point[0]],zoom:17});
   return place;
  });
  await page.waitForFunction(()=>window.jarvisDetailMap.areTilesLoaded()&&!window.jarvisDetailMap.isMoving());
  const click=await page.evaluate(p=>{const q=window.jarvisDetailMap.project([p.point[1],p.point[0]]);return {x:q.x,y:q.y};},named);
  await page.locator('#detail-map').click({position:click});
  assert.equal(await page.locator('.maplibregl-popup-content strong').innerText(),named.name);
  await page.locator('.maplibregl-popup-content button').filter({hasText:'Walk here'}).click();
  await page.waitForFunction(name=>document.querySelector('#route-info').textContent.includes(name),named.name,{timeout:60000});
  assert.match(await page.locator('#route-info').innerText(),/miles/);
  await page.screenshot({path:path.join(shots,'offline-atlas.png')});
  await page.locator('#map-fullscreen').click();
  assert.equal(await app.evaluate(({BrowserWindow})=>BrowserWindow.getAllWindows()[0].isFullScreen()),true);
  await page.waitForFunction(()=>window.jarvisDetailMap.areTilesLoaded()&&!window.jarvisDetailMap.isMoving());
  await page.locator('body.map-fullscreen').waitFor();
  assert.equal(await page.locator('aside').isVisible(),false);
  await page.screenshot({path:path.join(shots,'offline-atlas-fullscreen.png')});
  await page.keyboard.press('Escape');
  await page.waitForFunction(()=>!document.body.classList.contains('map-fullscreen'));
  assert.equal(await app.evaluate(({BrowserWindow})=>BrowserWindow.getAllWindows()[0].isFullScreen()),false);
  const routeStep=page.locator('#route-info > p').first();assert.match(await routeStep.innerText(),/^1 of/);
  if(await page.locator('#route-info button').filter({hasText:'Next'}).isEnabled()){ // a real route may be a single step
   await page.locator('#route-info button').filter({hasText:'Next'}).click();assert.match(await routeStep.innerText(),/^2 of/);
   await page.locator('#route-info button').filter({hasText:'Back'}).click();assert.match(await routeStep.innerText(),/^1 of/);
  }
  assert.equal(await page.locator('#route-info details').getAttribute('open'),null);
  assert.equal(await page.locator('#clear-route').isVisible(),true);assert.equal(await page.locator('#copy-route').isVisible(),true);
  await page.locator('#set-position-menu summary').click();await page.locator('#set-position').click();
  await page.locator('#detail-map').click({position:{x:320,y:210}});
  await page.waitForFunction(()=>document.querySelector('#map-click-cancel').hidden);
  const stored=JSON.parse(fs.readFileSync(path.join(data,'profile.json')));
  assert.equal(typeof stored.lat,'number');
  assert.equal(await page.evaluate(()=>route),null,'A new position clears the route');
  await page.locator('[data-page="assistant"]').click();
  await page.locator('#question').fill('Where is the nearest water?');await page.locator('#send').click();
  await page.waitForFunction(()=>document.querySelectorAll('.message.assistant').length>0);
  const answer=await page.locator('.message.assistant').last().innerText();
  assert.match(answer,/miles/);assert.match(answer,/Mapped walk|connected walking route|250 m/);assert.match(answer,/safe to drink/);
  await page.locator('#question').fill('How many miles to Atlantis?');await page.locator('#send').click();
  await page.waitForFunction(()=>document.querySelectorAll('.message.assistant').length===2);
  // The panel always mirrors the backend's current route, whatever the answer did with it.
  assert.equal(await page.evaluate(async()=>JSON.stringify(route)===JSON.stringify((await window.jarviss.command('state')).route)),true);
  await page.locator('[data-page="atlas"]').click();await page.locator('#clear-route').click();
  assert.equal(await page.evaluate(()=>route),null);assert.equal(await page.locator('#route-info').innerText(),'');
  assert.deepEqual(await app.evaluate(()=>globalThis.externalRequests),[]);
  assert.deepEqual(errors,[]);
  console.log('PASS: no default position, city/landmark discovery and explicit confirmation, real US map render, local fonts/tiles, position selection, feature search, grounded chat and stale-route clearing with external HTTP blocked');
 }finally{if(app)await app.close();fs.rmSync(data,{recursive:true,force:true});}
})().catch(e=>{console.error(e);process.exitCode=1;});
