const {contextBridge,ipcRenderer}=require('electron');
contextBridge.exposeInMainWorld('jarviss',{
 command:(method,args)=>ipcRenderer.invoke('command',method,args),
 pick:kind=>ipcRenderer.invoke('pick',kind),
 subscribe:callback=>{const listener=(_event,data)=>callback(data);ipcRenderer.on('service-event',listener);return()=>ipcRenderer.removeListener('service-event',listener);}
});
