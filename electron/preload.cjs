const {contextBridge,ipcRenderer,webUtils}=require('electron');
const listen=channel=>callback=>{const listener=(_event,data)=>callback(data);ipcRenderer.on(channel,listener);return()=>ipcRenderer.removeListener(channel,listener);};
// Dropped File objects become paths here; the renderer never handles a path string itself.
const filePath=file=>{try{return typeof file==='object'&&file?webUtils.getPathForFile(file):'';}catch{return '';}};
contextBridge.exposeInMainWorld('jarviss',{
 command:(method,args)=>ipcRenderer.invoke('command',method,args),
 pick:kind=>ipcRenderer.invoke('pick',kind),
 importPaths:files=>ipcRenderer.invoke('import-paths',Array.from(files||[],filePath).filter(Boolean)),
 mapFullscreen:enabled=>ipcRenderer.invoke('map-fullscreen',enabled),
 saveReference:(id,format)=>ipcRenderer.invoke('save-reference',id,format),
 openReferencePDF:(id,section)=>ipcRenderer.invoke('open-reference-pdf',id,section),
 openDataFolder:()=>ipcRenderer.invoke('open-path','data'),
 showLogs:()=>ipcRenderer.invoke('open-path','logs'),
 checkUpdates:()=>ipcRenderer.invoke('check-updates'),
 version:()=>ipcRenderer.invoke('version'),
 notify:(title,body)=>ipcRenderer.invoke('notify',title,body),
 setProgress:fraction=>ipcRenderer.invoke('set-progress',fraction),
 setTitle:text=>ipcRenderer.invoke('set-title',text),
 restartService:()=>ipcRenderer.invoke('restart-service'),
 subscribe:listen('service-event'),
 onAppEvent:listen('app-event'),
});
