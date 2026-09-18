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
