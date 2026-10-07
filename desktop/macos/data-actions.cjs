const fs=require('node:fs');
const path=require('node:path');
const {pathToFileURL}=require('node:url');
const {randomUUID}=require('node:crypto');
const {fetchCatalog,checkedUrl,downloadPackage}=require('./downloads.cjs');

function installDataActions({ipcMain,BrowserWindow,dialog,shell,window,runtime,home,origin,runDataCommand,importData}) {
 let manager,busy=false,catalog=[],localFiles=new Map();
 const file=pathToFileURL(path.join(__dirname,'data.html')).href,settingsPath=path.join(home,'downloads.json');
 function settings(){try{return JSON.parse(fs.readFileSync(settingsPath,'utf8'));}catch{return {};}}
 function handle(name,fn){ipcMain.handle(name,async(event,...args)=>{
  const url=event.senderFrame?.url;
  if(url!==file && !(url && new URL(url).origin===origin && new URL(url).pathname.startsWith('/tcga_explorer/')))throw new Error('This action is only available inside TRACE.');
  return fn(event,...args);
 });}
 async function operation(task){if(busy)throw new Error('Wait for the current data operation to finish.');busy=true;try{return await task();}finally{busy=false;}}
 handle('trace:data-open',()=>{
  if(manager&&!manager.isDestroyed()){manager.focus();return;}
  manager=new BrowserWindow({width:900,height:850,minWidth:500,minHeight:500,parent:window,icon:path.join(__dirname,'icons','trace-desktop.png'),autoHideMenuBar:true,title:'Manage data · TRACE Explorer',webPreferences:{preload:path.join(__dirname,'preload.cjs'),nodeIntegration:false,contextIsolation:true,sandbox:true}});
  manager.webContents.setWindowOpenHandler(()=>({action:'deny'}));manager.webContents.on('will-navigate',(event,url)=>{if(url!==file)event.preventDefault();});
  return manager.loadFile(path.join(__dirname,'data.html'));
 });
 handle('trace:data-close',()=>{if(manager&&!manager.isDestroyed())manager.close();if(!window.isDestroyed()){window.show();window.focus();}});
 handle('trace:data-installed',()=>runDataCommand(runtime,home,['--package-list']));
 handle('trace:data-folder',()=>shell.openPath(home));
 handle('trace:data-catalog',async()=>{
  const url=settings().catalog_url||process.env.TRACE_DATA_CATALOG_URL||'';
  if(!url){catalog=[];return {configured:false,url:'',packages:[]};}
  const result=await fetchCatalog(url);catalog=result.packages;
  return {configured:true,url,packages:catalog};
 });
 handle('trace:data-catalog-set',(_event,url)=>{
  if(typeof url!=='string'||url.length>2048)throw new Error('Invalid catalog address.');if(url)checkedUrl(url);
  fs.writeFileSync(settingsPath,JSON.stringify({catalog_url:url},null,2));catalog=[];
 });
 // Only the folder chosen in the native dialog grants access to package files.
 handle('trace:data-browse',()=>operation(async()=>{
  const selection=await dialog.showOpenDialog(manager||window,{title:'Find TRACE data packages',properties:['openDirectory']});
  if(selection.canceled)return {canceled:true};
  const folder=selection.filePaths[0],found=[];localFiles.clear();
  const entries=await fs.promises.readdir(folder,{withFileTypes:true});
  for(const entry of entries.sort((a,b)=>a.name.localeCompare(b.name))){
   if(!entry.isFile()||!entry.name.toLowerCase().endsWith('.tar.gz'))continue;
   if(found.length>=500)break;
   const filePath=path.join(folder,entry.name),info=await fs.promises.stat(filePath),id=randomUUID();
   localFiles.set(id,filePath);found.push({id,name:entry.name,bytes:info.size});
  }
  return {folder,files:found,limited:entries.filter(entry=>entry.isFile()&&entry.name.toLowerCase().endsWith('.tar.gz')).length>500};
 }));
 handle('trace:data-import-local',(_event,id)=>operation(async()=>{
  const filePath=localFiles.get(id);
  if(!filePath)throw new Error('Choose a folder again to find this data package.');
  const info=await fs.promises.lstat(filePath);
  if(!info.isFile())throw new Error('This file is no longer available. Choose the folder again.');
  return importData(filePath);
 }));
 handle('trace:data-import',()=>operation(async()=>{
  const selection=await dialog.showOpenDialog(manager||window,{title:'Choose a TRACE data package',properties:['openFile'],filters:[{name:'TRACE data package',extensions:['tar.gz']}]});
  if(selection.canceled)return {canceled:true};
  return importData(selection.filePaths[0]);
 }));
 handle('trace:data-export',(_event,entry)=>operation(async()=>{
  const installed=await runDataCommand(runtime,home,['--package-list']);
  const selected=installed.find(row=>row.cancer_code===entry?.cancer_code&&row.source===entry?.source);
  if(!selected)throw new Error('This cancer source is not installed.');
  const selection=await dialog.showSaveDialog(manager||window,{title:'Export cancer data',defaultPath:`TRACE-${selected.cancer_code}-${selected.source}.tar.gz`,filters:[{name:'TRACE data package',extensions:['tar.gz']}]});
  if(selection.canceled)return {canceled:true};
  return runDataCommand(runtime,home,[selected.source==='tcga_reference'?'--package-export-tcga':'--package-export',selected.cancer_code,selection.filePath]);
 }));
 handle('trace:data-download',(event,id)=>operation(async()=>{
  const entry=catalog.find(row=>row.id===id);if(!entry)throw new Error('Check for updates before choosing a package.');
  const archive=await downloadPackage(entry,path.join(home,'downloads'),value=>{if(!event.sender.isDestroyed())event.sender.send('trace:data-progress',value);});
  return importData(archive,true);
 }));
}
module.exports={installDataActions};
