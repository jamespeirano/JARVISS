const {contextBridge,ipcRenderer}=require('electron');
contextBridge.exposeInMainWorld('jarviss',{
 command:(method,args)=>ipcRenderer.invoke('command',method,args),
 pick:kind=>ipcRenderer.invoke('pick',kind),
 mapFullscreen:enabled=>ipcRenderer.invoke('map-fullscreen',enabled),
 saveReference:(id,format)=>ipcRenderer.invoke('save-reference',id,format),
 subscribe:callback=>{const listener=(_event,data)=>callback(data);ipcRenderer.on('service-event',listener);return()=>ipcRenderer.removeListener('service-event',listener);}
});
