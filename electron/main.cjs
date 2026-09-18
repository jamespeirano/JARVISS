const {app,BrowserWindow,ipcMain,dialog,protocol,Menu,screen,shell,Notification,nativeTheme}=require('electron');
const {spawn}=require('node:child_process');
const fs=require('node:fs');
const path=require('node:path');
const readline=require('node:readline');
const {atlasHandler}=require('./atlas-protocol.cjs');
const {watchStartup,serviceGone,rpcTimeout,killTree,MIN_SIZE,defaultBounds,clampBounds,importable,openTarget,menuTemplate}=require('./startup.cjs');
const pkg=require('./package.json');
const RELEASES_URL=pkg.homepage+'/releases/latest';
app.setName('JARVISS');
app.setAppUserModelId('org.jarviss.desktop'); // Windows toasts need the installer's app id.
// Overlay scrollbars: Chromium reads --enable-features=OverlayScrollbar only from the real process command line here;
// app.commandLine.appendSwitch is too late in this build (measured: 15px stays), so base.css styles the classic bar instead.
protocol.registerSchemesAsPrivileged([{scheme:'atlas',privileges:{standard:true,secure:true,supportFetchAPI:true,corsEnabled:true,stream:true}}]);
let archivePath;
let win, child, startup, sequence=0, quitting=false, restarting=false, loaded=false;
const pending=new Map();
const paths={};
app.setPath('userData',process.env.JARVISS_APP_DATA||path.join(app.getPath('appData'),'JARVISS'));
const allowed=new Set(['setup_plan','setup_run','setup_pause','setup_skip','location_parts','import_note','library_delete','library_rename','document','planner_save','planner_delete','planner_done','planner_energy','board_start','board_stop','board_state','board_send','state','chat','save_profile','set_map_position','search_locations','voice','clear','start_model','stop_model','nearest','route','download_voice','download_us_maps','audio_devices','audio_settings','test_speaker','stop_speaker','prompt_settings']);
for(const method of ['reference','reference_search'])allowed.add(method);
if(!app.requestSingleInstanceLock()){app.quit();return;} // Without return, a second launch starts a second backend.
app.on('second-instance',()=>{if(win){win.show();win.focus();}});
const gone=()=>serviceGone(child);
function rpc(method,args={}){
 return new Promise((resolve,reject)=>{
  if(gone()) return reject(new Error('Local service is unavailable. Restart it from Settings → About.'));
  const id=++sequence;
  const timer=setTimeout(()=>{pending.delete(id);reject(new Error('Operation timed out. Check Settings.'));},rpcTimeout(method));
  pending.set(id,{resolve,reject,timer,child}); child.stdin.write(JSON.stringify({id,method,args})+'\n');
 });
}
const send=(event,data)=>{if(win&&!win.isDestroyed())win.webContents.send('service-event',{event,data});};
const sendApp=(event,data)=>{if(win&&!win.isDestroyed())win.webContents.send('app-event',{event,data});};
const sender=event=>{if(!win||event.sender!==win.webContents)throw new Error('Invalid sender');};
app.whenReady().then(()=>{
 const root=process.env.JARVISS_ROOT||(app.isPackaged?path.join(app.getPath('userData'),'workspace'):path.resolve(__dirname,'..'));
 fs.mkdirSync(root,{recursive:true});
 paths.data=process.env.JARVISS_DATA||path.join(root,'local-data');paths.logs=path.join(root,'service.log');
 archivePath=path.join(root,'local-maps','us-z15.pmtiles');
 protocol.handle('atlas',atlasHandler({assets:path.join(__dirname,'map-assets'),getArchive:()=>archivePath}));
 const log=paths.logs;
 let logSize=0,logging=Promise.resolve();try{logSize=fs.statSync(log).size;}catch{}
 // Serialized off the UI thread; a chatty backend must not stall the window or fill the disk.
 const record=text=>{logging=logging.then(async()=>{if(logSize>4e6){await fs.promises.rename(log,log+'.1').catch(()=>{});logSize=0;}logSize+=Buffer.byteLength(text);await fs.promises.appendFile(log,text);}).catch(()=>{});};
 function startService(){
  const python=app.isPackaged?path.join(process.resourcesPath,'backend',process.platform==='win32'?'jarviss-service.exe':'jarviss-service'):path.join(root,'.venv',process.platform==='win32'?'Scripts/python.exe':'bin/python');
  const current=child=spawn(python,app.isPackaged?[]:['-u',path.join(root,'service.py')],{cwd:root,windowsHide:true,detached:process.platform!=='win32',env:{...process.env,JARVISS_ROOT:root,...(app.isPackaged?{JARVISS_BUNDLED_RUNTIME:path.join(process.resourcesPath,'runtime')}:{}),PYTHONIOENCODING:'utf-8'}});
  current.on('error',e=>send('error',e.message));
  current.stderr.on('data',record);
  readline.createInterface({input:current.stdout}).on('line',line=>{
   let msg;try{msg=JSON.parse(line);}catch{record('Unreadable service output: '+line+'\n');return;}
   if(msg.id){const p=pending.get(msg.id);if(p){clearTimeout(p.timer);pending.delete(msg.id);if(msg.result?.basemap?.path)archivePath=msg.result.basemap.path;if(msg.result?.paths?.data)Object.assign(paths,msg.result.paths);msg.error?p.reject(new Error(msg.error)):p.resolve(msg.result);}}
   else send(msg.event,msg.data);
  });
  current.on('exit',()=>{
   for(const [id,p] of pending){if(p.child!==current)continue;clearTimeout(p.timer);pending.delete(id);p.reject(new Error('Local service stopped.'));}
   if(current!==child||restarting||quitting)return;
   send('error','Local service stopped. Restart it from Settings → About.');sendApp('service-stopped');
  });
 }
 startService();
 ipcMain.handle('command',(event,method,args)=>{
  if(event.sender!==win.webContents||!allowed.has(method))throw new Error('Unsupported operation');
  if(method==='state'){startup?.ready();loaded=true;}
  return rpc(method,args);
 });
 ipcMain.handle('pick',async(event,kind)=>{
  sender(event);
  const filters={model:[{name:'GGUF model',extensions:['gguf']}],basemap:[{name:'Offline vector basemap',extensions:['pmtiles']}],document:[{name:'Documents',extensions:['pdf','txt','md']}]};
  if(!filters[kind])throw new Error('Unsupported file type');
  const result=await dialog.showOpenDialog(win,{properties:['openFile'],filters:filters[kind]});
  if(result.canceled)return null;
  if(kind==='model')return result.filePaths[0];
  return rpc(kind==='basemap'?'import_basemap':'import_document',{path:result.filePaths[0]});
 });
 ipcMain.handle('import-paths',async(event,candidates)=>{
  sender(event);
  const results=[];
  for(const file of importable(candidates)){
   try{results.push({path:file,title:await rpc('import_document',{path:file})});}
   catch(error){results.push({path:file,error:error.message});}
  }
  return results;
 });
 const openKnown=async kind=>{
  const target=openTarget(kind,paths);
  if(!target)throw new Error('Unknown folder');
  if(target.method==='openPath'){fs.mkdirSync(target.target,{recursive:true});return !(await shell.openPath(target.target));}
  if(!fs.existsSync(target.target))return !(await shell.openPath(path.dirname(target.target)));
  shell.showItemInFolder(target.target);return true;
 };
 ipcMain.handle('open-path',(event,kind)=>{sender(event);return openKnown(kind);});
 ipcMain.handle('check-updates',event=>{sender(event);return shell.openExternal(RELEASES_URL).then(()=>true);});
 ipcMain.handle('version',event=>{sender(event);return app.getVersion();});
 ipcMain.handle('notify',(event,title,body)=>{
  sender(event);
  if(win.isFocused()||!Notification.isSupported())return false;
  new Notification({title:String(title??'').slice(0,100),body:String(body??'').slice(0,300)}).show();return true;
 });
 ipcMain.handle('set-progress',(event,fraction)=>{
  sender(event);
  if(typeof fraction!=='number'||!(fraction>=-1&&fraction<=1))throw new Error('Progress must be between -1 and 1');
  win.setProgressBar(fraction);return true;
 });
 ipcMain.handle('set-title',(event,text)=>{sender(event);win.setTitle(String(text??'JARVISS').slice(0,120)||'JARVISS');return true;});
 let restart=Promise.resolve();
 ipcMain.handle('restart-service',event=>{
  sender(event);
  // Same wiring as startup; the renderer reloads its state once this resolves.
  restart=restart.catch(()=>{}).then(async()=>{
   restarting=true;
   const old=child;
   if(!serviceGone(old)){
    const exited=new Promise(resolve=>old.once('exit',resolve));
    try{old.stdin.end(JSON.stringify({id:0,method:'shutdown'})+'\n');}catch{}
    const timer=setTimeout(()=>killTree(old),8000);
    await exited;clearTimeout(timer);
   }
   startService();
   restarting=false;
   return true;
  });
  return restart;
 });
 let fullscreenTransition=Promise.resolve();
 ipcMain.handle('map-fullscreen',(event,enabled)=>{
  if(event.sender!==win.webContents||typeof enabled!=='boolean')throw new Error('Unsupported operation');
  fullscreenTransition=fullscreenTransition.catch(()=>{}).then(()=>new Promise(resolve=>{
   if(win.isDestroyed()||win.isFullScreen()===enabled){resolve(enabled);return;}
   // macOS changes Spaces asynchronously. Finish one transition before another,
   // but never wait forever: a closed window or a refused transition emits nothing.
   const name=enabled?'enter-full-screen':'leave-full-screen';
   const done=()=>{clearTimeout(timer);win.removeListener(name,done);resolve(enabled);};
   const timer=setTimeout(done,1500);
   win.once(name,done);win.setFullScreen(enabled);
  }));
  return fullscreenTransition;
 });
 let pdfWindow,pdfSequence=0;
 ipcMain.handle('open-reference-pdf',async(event,id,section)=>{
  if(event.sender!==win.webContents||typeof id!=='string'||(section!==undefined&&typeof section!=='string'))throw new Error('Unsupported operation');
  const sequence=++pdfSequence;
  // Resolve only bundled document IDs, including the original-to-excerpt page offset.
  const doc=await rpc('reference',{id}),file=await rpc('reference_pdf',{id});
  let page=1;
  if(section){
   const found=doc.sections.find(s=>s.id===section);
   if(!found)throw new Error('This section is not in the document.');
   const original=Number(found.heading.match(/PDF page (\d+)/)?.[1]);
   const [first,last]=(doc.source_pages||'').split('–').map(Number);
   if(original>=first&&original<=last)page=original-first+2; // Excerpts include one cover page.
  }
  if(sequence!==pdfSequence)return false;
  if(!pdfWindow||pdfWindow.isDestroyed()){
   pdfWindow=new BrowserWindow({parent:win,width:1040,height:820,show:false,title:doc.title,autoHideMenuBar:true,webPreferences:{contextIsolation:true,nodeIntegration:false,sandbox:true,plugins:true}});
   pdfWindow.webContents.setWindowOpenHandler(()=>({action:'deny'}));
   pdfWindow.webContents.on('will-navigate',event=>event.preventDefault());
  }
  const viewer=pdfWindow;
  // Chromium's PDF viewer can ignore a hash-only page change. A fresh local
  // document URL reloads the viewer while keeping this one window.
  try{await viewer.loadFile(file,{query:{view:String(sequence)},hash:`page=${page}&view=FitH`});}
  catch(e){if(sequence!==pdfSequence||viewer.isDestroyed())return false;throw e;}
  if(sequence!==pdfSequence||viewer.isDestroyed())return false;
  viewer.setTitle(doc.title);viewer.show();viewer.focus();return true;
 });
 ipcMain.handle('save-reference',async(event,id,format='md')=>{
  if(event.sender!==win.webContents||typeof id!=='string'||!['md','pdf'].includes(format))throw new Error('Unsupported operation');
  const doc=await rpc('reference',{id});
  const source=format==='pdf'?await rpc('reference_pdf',{id}):null;
  const result=await dialog.showSaveDialog(win,{defaultPath:doc.id+'.'+format,filters:[{name:format==='pdf'?'Illustrated PDF':'Markdown document',extensions:[format]}]});
  if(result.canceled)return false;
  if(source){await fs.promises.copyFile(source,result.filePath);return true;}
  const attribution=[doc.title,doc.publisher,`Edition: ${doc.date}`,doc.url,doc.note||'',doc.editing_note||'',doc.attribution||'',doc.license_note||''].filter(Boolean).join('\n');
  await fs.promises.writeFile(result.filePath,attribution+'\n\n'+doc.text+'\n\nSources\n'+(doc.sources||[doc.url]).join('\n'),'utf8');
  return true;
 });
 nativeTheme.themeSource='dark';
 app.setAboutPanelOptions({applicationName:'JARVISS',applicationVersion:app.getVersion(),version:app.getVersion(),copyright:'MIT license',website:pkg.homepage,iconPath:path.join(__dirname,'icons','icon.png')});
 const act=(name,data)=>{
  if(name==='open-data-folder')return openKnown('data').catch(()=>{});
  if(name==='show-logs')return openKnown('logs').catch(()=>{});
  if(name==='report-problem')return shell.openExternal(pkg.bugs.url);
  sendApp(name,data);
 };
 Menu.setApplicationMenu(Menu.buildFromTemplate(menuTemplate({packaged:app.isPackaged,platform:process.platform,act})));
 const boundsFile=path.join(app.getPath('userData'),'window.json');
 let saved={};try{saved=JSON.parse(fs.readFileSync(boundsFile,'utf8'));}catch{}
 const bounds=clampBounds(saved,screen.getAllDisplays().map(d=>d.workArea),defaultBounds(screen.getPrimaryDisplay().workAreaSize));
 // Hidden title bar: the page draws its own (drag regions in base.css); Windows and Linux keep the caption buttons as an
 // overlay the stylesheet reserves via env(titlebar-area-*), macOS keeps its traffic lights. Alt still shows the menu.
 const titleBar=process.platform==='darwin'?{titleBarStyle:'hidden',trafficLightPosition:{x:12,y:12}}:{titleBarStyle:'hidden',titleBarOverlay:{color:'#1b1b1e',symbolColor:'#b4b4bc',height:40}};
 win=new BrowserWindow({...bounds,...titleBar,minWidth:MIN_SIZE.width,minHeight:MIN_SIZE.height,autoHideMenuBar:true,backgroundColor:'#141416',title:'JARVISS',webPreferences:{preload:path.join(__dirname,'preload.cjs'),contextIsolation:true,nodeIntegration:false,sandbox:true}});
 if(saved.maximized)win.maximize();
 const remember=()=>{if(win.isDestroyed()||win.isFullScreen())return saved;return saved={...win.getNormalBounds(),maximized:win.isMaximized()};};
 let saveTimer;
 for(const name of ['resize','move','maximize','unmaximize'])win.on(name,()=>{clearTimeout(saveTimer);saveTimer=setTimeout(()=>fs.promises.writeFile(boundsFile,JSON.stringify(remember())).catch(()=>{}),400);});
 win.on('close',()=>{clearTimeout(saveTimer);try{fs.writeFileSync(boundsFile,JSON.stringify(remember()));}catch{}});
 win.webContents.setWindowOpenHandler(()=>({action:'deny'}));
 win.webContents.on('will-navigate',e=>e.preventDefault());
 win.on('leave-full-screen',()=>send('map_fullscreen',false));
 win.webContents.session.setPermissionRequestHandler((_w,permission,callback)=>callback(permission==='clipboard-sanitized-write')); // Copy buttons; nothing else.
 startup=watchStartup(win,{app,dialog,report:reason=>fs.appendFileSync(path.join(root,'startup.log'),`${new Date().toISOString()} ${reason}\n`)});
 // After the first successful load, a renderer crash reloads the page instead of relaunching the app.
 win.webContents.on('render-process-gone',(_event,details)=>{if(loaded&&details.reason!=='clean-exit'&&!win.isDestroyed())win.webContents.reload();});
 win.loadFile(path.join(__dirname,'index.html')).catch(error=>startup.failed(error.message));
});
app.on('window-all-closed',()=>app.quit());
app.on('before-quit',event=>{
 if(gone()||quitting)return; event.preventDefault();quitting=true;
 child.stdin.end(JSON.stringify({id:0,method:'shutdown'})+'\n');
 const timer=setTimeout(()=>{killTree(child);app.quit();},8000);
 child.once('exit',()=>{clearTimeout(timer);app.quit();});
});
