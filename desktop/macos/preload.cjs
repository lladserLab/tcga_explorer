const {contextBridge,ipcRenderer}=require('electron');
contextBridge.exposeInMainWorld('traceDesktop',{
 openDataManager:()=>ipcRenderer.invoke('trace:data-open'),
 closeDataManager:()=>ipcRenderer.invoke('trace:data-close'),
 browseFolder:()=>ipcRenderer.invoke('trace:data-browse'),
 importLocal:id=>ipcRenderer.invoke('trace:data-import-local',id),
 installed:()=>ipcRenderer.invoke('trace:data-installed'),
 importPackage:()=>ipcRenderer.invoke('trace:data-import'),
 exportPackage:entry=>ipcRenderer.invoke('trace:data-export',entry),
 catalog:()=>ipcRenderer.invoke('trace:data-catalog'),
 setCatalog:url=>ipcRenderer.invoke('trace:data-catalog-set',url),
 download:id=>ipcRenderer.invoke('trace:data-download',id),
 openFolder:()=>ipcRenderer.invoke('trace:data-folder'),
 onProgress:callback=>{const listener=(_event,value)=>callback(value);ipcRenderer.on('trace:data-progress',listener);return()=>ipcRenderer.removeListener('trace:data-progress',listener);}
});
