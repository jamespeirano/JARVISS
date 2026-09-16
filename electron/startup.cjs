const RETRY_FLAG='--jarviss-startup-retry';

// Stop watching as soon as the renderer can use its isolated bridge. A slow
// model or backend request after that point is not a failed window startup.
function watchStartup(win,{app,dialog,report=()=>{},argv=process.argv,timers=globalThis,timeout=120000}){
 let settled=false;
 const retried=argv.includes(RETRY_FLAG);
 const args=argv.slice(1).filter(arg=>arg!==RETRY_FLAG);
 const restart=()=>{app.relaunch({args:[...args,RETRY_FLAG]});app.quit();};
 const stop=()=>{
  settled=true;timers.clearTimeout(timer);
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
module.exports={watchStartup,RETRY_FLAG};
