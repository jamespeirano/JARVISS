const {app,BrowserWindow,ipcMain,dialog,protocol}=require('electron');
const {spawn}=require('node:child_process');
const fs=require('node:fs');
const path=require('node:path');
const readline=require('node:readline');
const {atlasHandler}=require('./atlas-protocol.cjs');
const {watchStartup}=require('./startup.cjs');
app.setName('JARVISS');
protocol.registerSchemesAsPrivileged([{scheme:'atlas',privileges:{standard:true,secure:true,supportFetchAPI:true,corsEnabled:true,stream:true}}]);
let archivePath;
let win, child, startup, sequence=0, quitting=false;
const pending=new Map();
app.setPath('userData',process.env.JARVISS_APP_DATA||path.join(app.getPath('appData'),'JARVISS'));
const allowed=new Set(['setup_plan','setup_run','setup_pause','location_parts','import_note','planner_save','planner_delete','planner_done','planner_energy','board_start','board_stop','board_state','board_send','state','chat','save_profile','set_map_position','search_locations','use_basemap','voice','clear','start_model','nearest','route','example_map','download_model','download_voice','download_us_maps','download_map','audio_devices','audio_settings','test_speaker','stop_speaker','prompt_settings']);
if(!app.requestSingleInstanceLock()) app.quit();
app.on('second-instance',()=>{if(win){win.show();win.focus();}});
function rpc(method,args={}){
 return new Promise((resolve,reject)=>{
  if(!child||child.exitCode!==null) return reject(new Error('Local service is unavailable. Restart the app.'));
  const id=++sequence;
  const timer=setTimeout(()=>{pending.delete(id);reject(new Error('Operation timed out. Check Settings.'));},(method.startsWith('download')||method==='setup_run')?86400000:300000);
  pending.set(id,{resolve,reject,timer}); child.stdin.write(JSON.stringify({id,method,args})+'\n');
 });
}
app.whenReady().then(()=>{
 const root=process.env.JARVISS_ROOT||(app.isPackaged?path.join(app.getPath('userData'),'workspace'):path.resolve(__dirname,'..'));
 fs.mkdirSync(root,{recursive:true});
 archivePath=path.join(root,'local-maps','us-z15.pmtiles');
 protocol.handle('atlas',atlasHandler({assets:path.join(__dirname,'map-assets'),getArchive:()=>archivePath}));
 const python=app.isPackaged?path.join(process.resourcesPath,'backend',process.platform==='win32'?'jarviss-service.exe':'jarviss-service'):path.join(root,'.venv',process.platform==='win32'?'Scripts/python.exe':'bin/python');
 child=spawn(python,app.isPackaged?[]:['-u',path.join(root,'service.py')],{cwd:root,windowsHide:true,env:{...process.env,JARVISS_ROOT:root,...(app.isPackaged?{JARVISS_BUNDLED_RUNTIME:path.join(process.resourcesPath,'runtime')}:{}),PYTHONIOENCODING:'utf-8'}});
 const send=(event,data)=>{if(win&&!win.isDestroyed())win.webContents.send('service-event',{event,data});};
 child.on('error',e=>send('error',e.message));
 child.stderr.on('data',d=>fs.appendFileSync(path.join(root,'service.log'),d));
 readline.createInterface({input:child.stdout}).on('line',line=>{
  let msg;try{msg=JSON.parse(line);}catch{return;}
  if(msg.id){const p=pending.get(msg.id);if(p){clearTimeout(p.timer);pending.delete(msg.id);if(msg.result?.basemap?.path)archivePath=msg.result.basemap.path;msg.error?p.reject(new Error(msg.error)):p.resolve(msg.result);}}
  else send(msg.event,msg.data);
 });
 child.on('exit',()=>{for(const p of pending.values()){clearTimeout(p.timer);p.reject(new Error('Local service stopped.'));}pending.clear();send('error','Local service stopped. Restart the application.');});
 ipcMain.handle('command',(event,method,args)=>{
  if(event.sender!==win.webContents||!allowed.has(method))throw new Error('Unsupported operation');
  if(method==='state')startup?.ready();
  return rpc(method,args);
 });
 ipcMain.handle('pick',async(event,kind)=>{
  if(event.sender!==win.webContents)throw new Error('Invalid sender');
  const filters={model:[{name:'GGUF model',extensions:['gguf']}],map:[{name:'Walking route pack',extensions:['json']}],basemap:[{name:'Offline vector basemap',extensions:['pmtiles']}],document:[{name:'Documents',extensions:['pdf','txt','md']}]};
  if(!filters[kind])throw new Error('Unsupported file type');
  const result=await dialog.showOpenDialog(win,{properties:['openFile'],filters:filters[kind]});
  if(result.canceled)return null;
  if(kind==='model')return result.filePaths[0];
  return rpc(kind==='map'?'import_map':kind==='basemap'?'import_basemap':'import_document',{path:result.filePaths[0]});
 });
 win=new BrowserWindow({width:1440,height:940,minWidth:1024,minHeight:720,backgroundColor:'#181818',title:'JARVISS',autoHideMenuBar:true,webPreferences:{preload:path.join(__dirname,'preload.cjs'),contextIsolation:true,nodeIntegration:false,sandbox:true}});
 win.webContents.setWindowOpenHandler(()=>({action:'deny'}));
 win.webContents.on('will-navigate',e=>e.preventDefault());
 win.webContents.session.setPermissionRequestHandler((_w,_p,callback)=>callback(false));
 startup=watchStartup(win,{app,dialog,report:reason=>fs.appendFileSync(path.join(root,'startup.log'),`${new Date().toISOString()} ${reason}\n`)});
 win.loadFile(path.join(__dirname,'index.html')).catch(error=>startup.failed(error.message));
});
app.on('window-all-closed',()=>app.quit());
app.on('before-quit',event=>{
 if(!child||quitting)return; event.preventDefault();quitting=true;
 child.stdin.end(JSON.stringify({id:0,method:'shutdown'})+'\n');
 const timer=setTimeout(()=>{child.kill();app.quit();},8000);
 child.once('exit',()=>{clearTimeout(timer);app.quit();});
});
