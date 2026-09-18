const {test}=require('node:test');
const assert=require('node:assert/strict');
const {EventEmitter}=require('node:events');
const {watchStartup,serviceGone,rpcTimeout,killTree,RETRY_FLAG}=require('../startup.cjs');

function fixture({retried=false,response=1}={}){
 const win=new EventEmitter();win.webContents=new EventEmitter();
 const calls=[],pending=new Set();
 const options={
  app:{relaunch:options=>calls.push(['relaunch',options]),quit:()=>calls.push(['quit'])},
  dialog:{showMessageBox:async(_win,options)=>{calls.push(['dialog',options]);return {response};}},
  report:reason=>calls.push(['report',reason]),
  argv:['JARVISS.exe',...(retried?[RETRY_FLAG]:[])],
  timers:{setTimeout:callback=>{pending.add(callback);return callback;},clearTimeout:callback=>pending.delete(callback)},
 };
 return {win,calls,pending,guard:watchStartup(win,options),expire:()=>{for(const callback of [...pending])callback();}};
}

test('a blank first startup retries once without changing renderer protections',()=>{
 const f=fixture();f.expire();f.expire();
 assert.deepEqual(f.calls.map(c=>c[0]),['report','relaunch','quit']);
 assert.deepEqual(f.calls[1][1],{args:[RETRY_FLAG]});
});
test('a repeated failure asks instead of restarting in a loop',async()=>{
 const f=fixture({retried:true});await f.guard.failed('Startup failed');f.expire();
 assert.deepEqual(f.calls.map(c=>c[0]),['report','dialog','quit']);
});
test('explicit retry keeps the retry marker so automatic retries stay bounded',async()=>{
 const f=fixture({retried:true,response:0});await f.guard.failed('Startup failed');
 assert.deepEqual(f.calls.map(c=>c[0]),['report','dialog','relaunch','quit']);
 assert.deepEqual(f.calls[2][1],{args:[RETRY_FLAG]});
});
test('a working renderer never restarts during slow backend or model operations',async()=>{
 const f=fixture();f.guard.ready();f.expire();await f.guard.failed('Late failure');
 f.win.webContents.emit('render-process-gone',{}, {reason:'crashed'});
 assert.deepEqual(f.calls,[]);assert.equal(f.pending.size,0);
});
test('closing the app cancels startup recovery',()=>{
 const f=fixture();f.win.emit('closed');f.expire();assert.deepEqual(f.calls,[]);
});
test('a destroyed window stops watching without touching its gone webContents',()=>{
 const f=fixture();f.win.isDestroyed=()=>true;
 Object.defineProperty(f.win,'webContents',{get(){throw new Error('Object has been destroyed');}});
 assert.doesNotThrow(()=>f.win.emit('closed'));assert.doesNotThrow(()=>f.guard.ready());
 f.expire();assert.deepEqual(f.calls,[]);assert.equal(f.pending.size,0);
});
test('service liveness and request deadlines follow the backend',()=>{
 assert.equal(serviceGone(null),true);
 assert.equal(serviceGone({exitCode:null,signalCode:null}),false);
 assert.equal(serviceGone({exitCode:1,signalCode:null}),true);
 assert.equal(serviceGone({exitCode:null,signalCode:'SIGKILL'}),true);
 for(const method of ['download_model','download_us_maps','setup_run'])assert.equal(rpcTimeout(method),86400000);
 for(const method of ['chat','start_model'])assert.ok(rpcTimeout(method)>=600000,method);
 assert.equal(rpcTimeout('state'),300000);
});
test('renderer and preload failures recover without waiting for the timeout',()=>{
 for(const event of ['preload-error','render-process-gone']){
  const f=fixture();
  if(event==='preload-error')f.win.webContents.emit(event,{},'preload.cjs',new Error('Cannot start bridge'));
  else f.win.webContents.emit(event,{}, {reason:'crashed'});
  f.expire();assert.deepEqual(f.calls.map(c=>c[0]),['report','relaunch','quit']);
 }
});
test('a forced stop kills the backend process group, then the child alone, then the Windows tree',()=>{
 const calls=[],child={pid:4321,kill:()=>calls.push(['child'])};
 const spawn=(cmd,args,options)=>calls.push(['spawn',cmd,args,options]);
 for(const platform of ['linux','darwin']){
  calls.length=0;
  assert.equal(killTree(child,{platform,spawn,kill:(pid,signal)=>calls.push(['kill',pid,signal])}),'group');
  assert.deepEqual(calls,[['kill',-4321,'SIGKILL']],platform);
 }
 calls.length=0;
 assert.equal(killTree(child,{platform:'linux',spawn,kill:()=>{throw new Error('ESRCH');}}),'child');
 assert.deepEqual(calls,[['child']]);
 calls.length=0;
 assert.equal(killTree(child,{platform:'win32',spawn,kill:()=>calls.push(['kill'])}),'tree');
 assert.deepEqual(calls,[['spawn','taskkill',['/pid','4321','/T','/F'],{windowsHide:true}]]);
});
const {MIN_SIZE,defaultBounds,clampBounds,importable,openTarget,menuTemplate}=require('../startup.cjs');
test('the default window is 90% of the work area, capped at 1440x940 and never below the minimum',()=>{
 assert.deepEqual(defaultBounds({width:1920,height:1080}),{width:1440,height:940});
 assert.deepEqual(defaultBounds({width:1280,height:800}),{width:1152,height:720});
 assert.deepEqual(defaultBounds({width:800,height:500}),MIN_SIZE);
});
test('saved bounds are restored on a connected display and dropped otherwise',()=>{
 const displays=[{x:0,y:0,width:1920,height:1040},{x:1920,y:0,width:1920,height:1040}];
 const fallback={width:1440,height:940};
 assert.deepEqual(clampBounds({x:2000,y:100,width:1000,height:700},displays,fallback),{x:2000,y:100,width:1000,height:700});
 assert.deepEqual(clampBounds({x:100,y:100,width:400,height:300},displays,fallback),{x:100,y:100,width:900,height:600});
 assert.deepEqual(clampBounds({x:5000,y:100,width:1000,height:700},displays,fallback),fallback);
 assert.deepEqual(clampBounds({x:100,y:2000,width:1000,height:700},displays,fallback),fallback);
 for(const saved of [null,{},{x:'1',y:0,width:1000,height:700},{x:NaN,y:0,width:1000,height:700}])assert.deepEqual(clampBounds(saved,displays,fallback),fallback);
});
test('dropped files are limited to documents and known folders are the only open targets',()=>{
 assert.deepEqual(importable(['C:\a\manual.PDF','/b/notes.txt','/b/notes.txt','/c/plan.md','/c/app.exe','/c/photo.png','',7,null]),['C:\a\manual.PDF','/b/notes.txt','/c/plan.md']);
 assert.deepEqual(importable('/b/notes.txt'),[]);
 assert.equal(importable(Array.from({length:40},(_,i)=>`/d/${i}.md`)).length,30);
 const paths={data:'/root/local-data',logs:'/root/service.log'};
 assert.deepEqual(openTarget('data',paths),{method:'openPath',target:'/root/local-data'});
 assert.deepEqual(openTarget('logs',paths),{method:'showItemInFolder',target:'/root/service.log'});
 for(const kind of ['/etc/passwd','..','',undefined,'data/../x'])assert.equal(openTarget(kind,paths),null);
 assert.equal(openTarget('data',{}),null);
});
test('the application menu carries the shortcuts and hides developer items when packaged',()=>{
 const actions=[];
 const template=menuTemplate({packaged:true,platform:'win32',act:(name,data)=>actions.push([name,data])});
 assert.deepEqual(template.map(m=>m.label),['JARVISS','Edit','View','Help']);
 const items=template.flatMap(m=>m.submenu);
 const roles=items.map(i=>i.role).filter(Boolean);
 for(const role of ['about','quit','undo','redo','cut','copy','paste','selectAll','zoomIn','zoomOut','resetZoom','togglefullscreen'])assert.ok(roles.includes(role),role);
 assert.ok(!roles.includes('toggleDevTools')&&!roles.includes('reload'));
 const dev=menuTemplate({packaged:false,platform:'linux',act(){}}).flatMap(m=>m.submenu).map(i=>i.role);
 assert.ok(dev.includes('toggleDevTools')&&dev.includes('reload'));
 assert.ok(menuTemplate({packaged:true,platform:'darwin',act(){}})[0].submenu.some(i=>i.role==='hide'));
 const accelerators=Object.fromEntries(items.filter(i=>i.accelerator).map(i=>[i.accelerator,i]));
 for(const [key,expected] of [['CmdOrCtrl+1',['open-page',{page:'chat'}]],['CmdOrCtrl+2',['open-page',{page:'maps'}]],['CmdOrCtrl+3',['open-page',{page:'plan'}]],['CmdOrCtrl+4',['open-page',{page:'docs'}]],['CmdOrCtrl+5',['open-page',{page:'settings'}]],['CmdOrCtrl+L',['focus-composer',undefined]],['CmdOrCtrl+Shift+V',['toggle-voice',undefined]]]){
  actions.length=0;accelerators[key].click();assert.deepEqual(actions,[expected],key);
 }
 for(const [label,expected] of [['Toggle voice panel',['toggle-voice-panel',undefined]],['Open data folder',['open-data-folder',undefined]],['Show logs',['show-logs',undefined]],['Docs',['open-page',{page:'docs'}]],['Keyboard shortcuts',['show-shortcuts',undefined]],['Report a problem',['report-problem',undefined]]]){
  actions.length=0;items.find(i=>i.label===label).click();assert.deepEqual(actions,[expected],label);
 }
});
