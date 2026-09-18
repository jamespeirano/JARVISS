const childProcess=require('node:child_process');
const RETRY_FLAG='--jarviss-startup-retry';
const serviceGone=child=>!child||child.exitCode!==null||child.signalCode!==null;
// Downloads and setup run for hours. Chat and model starts must outlast the
// backend's own worst case (tokenize retries plus a 240 s model request, or a
// 360 s model start), or the renderer gives up while the backend holds its lock.
const rpcTimeout=method=>(method.startsWith('download')||method==='setup_run')?86400000:(method==='chat'||method==='start_model')?600000:300000;
// A forced stop must take llama-server and the map extractor with it: the whole
// tree on Windows, the backend's own process group (spawned detached) elsewhere.
function killTree(child,{platform=process.platform,spawn=childProcess.spawn,kill=process.kill.bind(process)}={}){
 if(platform==='win32'){spawn('taskkill',['/pid',String(child.pid),'/T','/F'],{windowsHide:true});return 'tree';}
 try{kill(-child.pid,'SIGKILL');return 'group';}catch{child.kill();return 'child';}
}

// Stop watching as soon as the renderer can use its isolated bridge. A slow
// model or backend request after that point is not a failed window startup.
function watchStartup(win,{app,dialog,report=()=>{},argv=process.argv,timers=globalThis,timeout=120000}){
 let settled=false;
 const retried=argv.includes(RETRY_FLAG);
 const args=argv.slice(1).filter(arg=>arg!==RETRY_FLAG);
 const restart=()=>{app.relaunch({args:[...args,RETRY_FLAG]});app.quit();};
 const stop=()=>{
  settled=true;timers.clearTimeout(timer);
  if(win.isDestroyed?.())return; // Closed during startup: webContents is already gone.
  win.webContents.removeListener('preload-error',preloadError);
  win.webContents.removeListener('render-process-gone',rendererGone);
  win.removeListener('closed',stop);
 };
 const fail=async reason=>{
  if(settled)return;
  stop();
  try{report(String(reason));}catch{}
  if(!retried){restart();return;}
  const {response}=await dialog.showMessageBox(win,{
   type:'error',message:'JARVISS could not open.',
   detail:'Try again. Your downloaded files will be kept.',
   buttons:['Try again','Quit'],defaultId:0,cancelId:1,
  }).catch(()=>({response:1}));
  if(response===0)restart();else app.quit();
 };
 const preloadError=(_event,_file,error)=>{void fail(error.message);};
 const rendererGone=(_event,details)=>{void fail(`Renderer stopped: ${details.reason}`);};
 const timer=timers.setTimeout(()=>{void fail('The setup window did not start within two minutes.');},timeout);
 win.webContents.on('preload-error',preloadError);
 win.webContents.on('render-process-gone',rendererGone);
 win.once('closed',stop);
 return {ready:stop,failed:fail};
}
module.exports={watchStartup,serviceGone,rpcTimeout,killTree,RETRY_FLAG};
