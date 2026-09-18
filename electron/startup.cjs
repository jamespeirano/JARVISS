const childProcess=require('node:child_process');
const nodePath=require('node:path');
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

const MIN_SIZE={width:900,height:600};
// 90% of the primary work area, capped at the design's reference size.
const defaultBounds=({width,height})=>({width:Math.max(MIN_SIZE.width,Math.min(1440,Math.round(width*.9))),height:Math.max(MIN_SIZE.height,Math.min(940,Math.round(height*.9)))});
// Saved bounds are reused only while their title bar still lands on a connected display.
function clampBounds(saved,displays,fallback){
 if(!saved||![saved.x,saved.y,saved.width,saved.height].every(Number.isFinite))return fallback;
 const width=Math.max(MIN_SIZE.width,Math.round(saved.width)),height=Math.max(MIN_SIZE.height,Math.round(saved.height));
 const visible=displays.some(d=>saved.x+width-80>d.x&&saved.x+80<d.x+d.width&&saved.y>=d.y-8&&saved.y+40<d.y+d.height);
 return visible?{x:Math.round(saved.x),y:Math.round(saved.y),width,height}:fallback;
}
const IMPORTABLE=new Set(['.pdf','.txt','.md']);
const importable=(paths,limit=30)=>Array.isArray(paths)?[...new Set(paths.filter(p=>typeof p==='string'&&IMPORTABLE.has(nodePath.extname(p).toLowerCase())))].slice(0,limit):[];
// The renderer names a place, never a path: only the two known folders can be opened.
const openTarget=(kind,paths)=>kind==='data'&&paths.data?{method:'openPath',target:paths.data}:kind==='logs'&&paths.logs?{method:'showItemInFolder',target:paths.logs}:null;
// act(name,data): 'open-page' {page}, 'focus-composer', 'toggle-voice', 'toggle-voice-panel' and
// 'show-shortcuts' go to the renderer; 'open-data-folder', 'show-logs' and 'report-problem' stay in main.
function menuTemplate({packaged,platform,act}){
 const mac=platform==='darwin';
 const page=(label,page,n)=>({label,accelerator:`CmdOrCtrl+${n}`,click:()=>act('open-page',{page})});
 return [
  {label:'JARVISS',submenu:[{role:'about',label:'About JARVISS'},{type:'separator'},
   {label:'Open data folder',click:()=>act('open-data-folder')},{label:'Show logs',click:()=>act('show-logs')},{type:'separator'},
   ...(mac?[{role:'hide'},{role:'hideOthers'},{role:'unhide'},{type:'separator'}]:[]),{role:'quit'}]},
  {label:'Edit',submenu:[{role:'undo'},{role:'redo'},{type:'separator'},{role:'cut'},{role:'copy'},{role:'paste'},{role:'selectAll'},{type:'separator'},
   {label:'Focus composer',accelerator:'CmdOrCtrl+L',click:()=>act('focus-composer')}]},
  {label:'View',submenu:[page('Chat','chat',1),page('Maps','maps',2),page('Plan','plan',3),page('Docs','docs',4),page('Settings','settings',5),{type:'separator'},
   {label:'Toggle voice panel',click:()=>act('toggle-voice-panel')},{label:'Start or stop voice',accelerator:'CmdOrCtrl+Shift+V',click:()=>act('toggle-voice')},{type:'separator'},
   {role:'zoomIn'},{role:'zoomOut'},{role:'resetZoom'},{type:'separator'},{role:'togglefullscreen'},
   ...(packaged?[]:[{type:'separator'},{role:'reload'},{role:'toggleDevTools'}])]},
  {label:'Help',submenu:[{label:'Docs',click:()=>act('open-page',{page:'docs'})},{label:'Keyboard shortcuts',click:()=>act('show-shortcuts')},{type:'separator'},
   {label:'Report a problem',click:()=>act('report-problem')}]},
 ];
}
module.exports={watchStartup,serviceGone,rpcTimeout,killTree,RETRY_FLAG,MIN_SIZE,defaultBounds,clampBounds,importable,openTarget,menuTemplate};
