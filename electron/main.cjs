const {app,BrowserWindow,ipcMain,dialog,protocol}=require('electron');
const {spawn}=require('node:child_process');
const fs=require('node:fs');
const path=require('node:path');
const readline=require('node:readline');
const {atlasHandler}=require('./atlas-protocol.cjs');
const {watchStartup,serviceGone,rpcTimeout,killTree}=require('./startup.cjs');
app.setName('JARVISS');
protocol.registerSchemesAsPrivileged([{scheme:'atlas',privileges:{standard:true,secure:true,supportFetchAPI:true,corsEnabled:true,stream:true}}]);
let archivePath;
let win, child, startup, sequence=0, quitting=false;
const pending=new Map();
app.setPath('userData',process.env.JARVISS_APP_DATA||path.join(app.getPath('appData'),'JARVISS'));
const allowed=new Set(['setup_plan','setup_run','setup_pause','location_parts','import_note','planner_save','planner_delete','planner_done','planner_energy','board_start','board_stop','board_state','board_send','state','chat','save_profile','set_map_position','search_locations','use_basemap','voice','clear','start_model','nearest','route','example_map','download_model','download_voice','download_us_maps','download_map','audio_devices','audio_settings','test_speaker','stop_speaker','prompt_settings']);
for(const method of ['reference','reference_search'])allowed.add(method);
if(!app.requestSingleInstanceLock()){app.quit();return;} // Without return, a second launch starts a second backend.
app.on('second-instance',()=>{if(win){win.show();win.focus();}});
const gone=()=>serviceGone(child);
function rpc(method,args={}){
 return new Promise((resolve,reject)=>{
  if(gone()) return reject(new Error('Local service is unavailable. Restart the app.'));
  const id=++sequence;
  const timer=setTimeout(()=>{pending.delete(id);reject(new Error('Operation timed out. Check Settings.'));},rpcTimeout(method));
  pending.set(id,{resolve,reject,timer}); child.stdin.write(JSON.stringify({id,method,args})+'\n');
 });
}
app.whenReady().then(()=>{
 const root=process.env.JARVISS_ROOT||(app.isPackaged?path.join(app.getPath('userData'),'workspace'):path.resolve(__dirname,'..'));
 fs.mkdirSync(root,{recursive:true});
 archivePath=path.join(root,'local-maps','us-z15.pmtiles');
 protocol.handle('atlas',atlasHandler({assets:path.join(__dirname,'map-assets'),getArchive:()=>archivePath}));
 const python=app.isPackaged?path.join(process.resourcesPath,'backend',process.platform==='win32'?'jarviss-service.exe':'jarviss-service'):path.join(root,'.venv',process.platform==='win32'?'Scripts/python.exe':'bin/python');
 child=spawn(python,app.isPackaged?[]:['-u',path.join(root,'service.py')],{cwd:root,windowsHide:true,detached:process.platform!=='win32',env:{...process.env,JARVISS_ROOT:root,...(app.isPackaged?{JARVISS_BUNDLED_RUNTIME:path.join(process.resourcesPath,'runtime')}:{}),PYTHONIOENCODING:'utf-8'}});
 const send=(event,data)=>{if(win&&!win.isDestroyed())win.webContents.send('service-event',{event,data});};
 child.on('error',e=>send('error',e.message));
 const log=path.join(root,'service.log');
 let logSize=0,logging=Promise.resolve();try{logSize=fs.statSync(log).size;}catch{}
 // Serialized off the UI thread; a chatty backend must not stall the window or fill the disk.
 const record=text=>{logging=logging.then(async()=>{if(logSize>4e6){await fs.promises.rename(log,log+'.1').catch(()=>{});logSize=0;}logSize+=Buffer.byteLength(text);await fs.promises.appendFile(log,text);}).catch(()=>{});};
 child.stderr.on('data',record);
 readline.createInterface({input:child.stdout}).on('line',line=>{
  let msg;try{msg=JSON.parse(line);}catch{record('Unreadable service output: '+line+'\n');return;}
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
 win=new BrowserWindow({width:1440,height:940,minWidth:1024,minHeight:720,backgroundColor:'#181818',title:'JARVISS',autoHideMenuBar:true,webPreferences:{preload:path.join(__dirname,'preload.cjs'),contextIsolation:true,nodeIntegration:false,sandbox:true}});
 win.webContents.setWindowOpenHandler(()=>({action:'deny'}));
 win.webContents.on('will-navigate',e=>e.preventDefault());
 win.on('leave-full-screen',()=>send('map_fullscreen',false));
 win.webContents.session.setPermissionRequestHandler((_w,_p,callback)=>callback(false));
 startup=watchStartup(win,{app,dialog,report:reason=>fs.appendFileSync(path.join(root,'startup.log'),`${new Date().toISOString()} ${reason}\n`)});
 win.loadFile(path.join(__dirname,'index.html')).catch(error=>startup.failed(error.message));
});
app.on('window-all-closed',()=>app.quit());
app.on('before-quit',event=>{
 if(gone()||quitting)return; event.preventDefault();quitting=true;
 child.stdin.end(JSON.stringify({id:0,method:'shutdown'})+'\n');
 const timer=setTimeout(()=>{killTree(child);app.quit();},8000);
 child.once('exit',()=>{clearTimeout(timer);app.quit();});
});
