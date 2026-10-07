const { app, BrowserWindow, dialog, Menu, shell, ipcMain } = require('electron');
const { spawn } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const PORT = 3100;
const ORIGIN = `http://127.0.0.1:${PORT}`;
const children = [];
let window;
let stopping = false;

function health() {
 return new Promise(resolve => {
  const req = http.get(`${ORIGIN}/tcga_explorer/api/v1/health`, response => {
   let body = '';
   response.on('data',chunk => body += chunk);
   response.on('end',() => {try {resolve(response.statusCode === 200 ? JSON.parse(body) : null);} catch {resolve(null);}});
  });
  req.setTimeout(1000,() => req.destroy());
  req.on('error',() => resolve(null));
 });
}
function verifyHomepage() {
 return new Promise((resolve, reject) => {
  const req = http.get(`${ORIGIN}/tcga_explorer/`, response => {
   let body = '';
   response.on('data', chunk => body += chunk);
   response.on('end', () => {
    if(response.statusCode === 200 && String(response.headers['content-type']).includes('text/html') && body.includes('id="root"')) resolve();
    else reject(new Error('The local interface could not be loaded. See engine.log in the data folder.'));
   });
   response.on('error', reject);
  });
  req.setTimeout(10000, () => req.destroy(new Error('The local interface did not respond.')));
  req.on('error', reject);
 });
}
function launchEngine(runtime, home, worker = false) {
 const log = fs.openSync(path.join(home,worker ? 'worker.log' : 'engine.log'),'a');
 const child = spawn(path.join(runtime,'python','python.exe'),
  [path.join(runtime,'engine.py'), ...(worker ? ['--worker'] : [])], {
   cwd:runtime, windowsHide:true, stdio:['ignore',log,log],
   env:{...process.env,TRACE_DESKTOP_HOME:home,TRACE_DESKTOP_PORT:String(PORT),PYTHONUNBUFFERED:'1'}
  });
 fs.closeSync(log);
 child.on('error', error => {if(!stopping) dialog.showErrorBox('TRACE could not start',error.message);});
 children.push(child);
 return child;
}
function runDataCommand(runtime,home,args) {
 return new Promise((resolve,reject)=>{
  const log=fs.createWriteStream(path.join(home,'data-packages.log'),{flags:'a'});
  let stdout='',stderr='';
  const child=spawn(path.join(runtime,'python','python.exe'),[path.join(runtime,'engine.py'),...args],
   {cwd:runtime,windowsHide:true,stdio:['ignore','pipe','pipe'],env:{...process.env,TRACE_DESKTOP_HOME:home,TRACE_DESKTOP_PORT:String(PORT),PYTHONUNBUFFERED:'1'}});
  children.push(child);
  child.stdout.on('data',chunk=>{stdout=(stdout+chunk).slice(-2*1024*1024);log.write(chunk);});
  child.stderr.pipe(log,{end:false});
  child.stderr.on('data',chunk=>{stderr=(stderr+chunk).slice(-8192);});
  child.once('error',error=>{log.end();reject(error);});
  child.once('close',code=>{log.end();if(code!==0){const detail=stderr.trim().split(/\r?\n/).findLast(line=>/^(ValueError|RuntimeError): /.test(line));reject(new Error(detail?detail.replace(/^[^:]+: /,''):'The data operation failed. See data-packages.log in the data folder.'));}
   else {try{resolve(JSON.parse(stdout.trim().split(/\r?\n/).at(-1)));}catch(error){reject(error);}}});
 });
}
async function start() {
 const home = path.join(app.getPath('userData'),'workspace');
 fs.mkdirSync(home,{recursive:true});
 const runtime = app.isPackaged ? path.join(process.resourcesPath,'runtime') : path.resolve(__dirname,'../build/runtime/windows');
 window = new BrowserWindow({width:1440,height:1000,minWidth:900,minHeight:650,
  title:'TRACE Explorer',icon:path.join(__dirname,'icons','trace-desktop.ico'),autoHideMenuBar:true,webPreferences:{preload:path.join(__dirname,'preload.cjs'),nodeIntegration:false,contextIsolation:true,sandbox:true}});
 window.webContents.session.setPermissionRequestHandler((_contents,_permission,callback)=>callback(false));
 window.webContents.setWindowOpenHandler(()=>({action:'deny'}));
 window.webContents.on('will-navigate',(event,url)=>{if(new URL(url).origin !== ORIGIN) event.preventDefault();});
 Menu.setApplicationMenu(null);
 let server,worker;
 const terminate=child=>new Promise((resolve,reject)=>{
  if(!child || child.exitCode!==null || child.signalCode!==null)return resolve();
  const timeout=setTimeout(()=>reject(new Error('The local engine did not stop. Restart TRACE and retry.')),15000);
  child.once('close',()=>{clearTimeout(timeout);resolve();});child.kill();
 });
 async function importData(archive,update=false) {
  await terminate(server);
  try {
   await runDataCommand(runtime,home,['--data-idle']);
   await terminate(worker);
   return await runDataCommand(runtime,home,[update?'--package-update':'--package-import',archive]);
  } finally {
   if(!stopping){
    server=launchEngine(runtime,home);
    const deadline=Date.now()+180000;
    while(!(await health())){if(server.exitCode!==null||Date.now()>deadline)throw new Error('Restart TRACE to reopen the local engine.');await new Promise(resolve=>setTimeout(resolve,300));}
    if(!worker || worker.exitCode!==null || worker.signalCode!==null)worker=launchEngine(runtime,home,true);
    if(!window.isDestroyed())window.reload();
   }
  }
 }
 require('./data-actions.cjs').installDataActions({ipcMain,BrowserWindow,dialog,shell,window,runtime,home,origin:ORIGIN,runDataCommand,importData});
 await window.loadFile(path.join(__dirname,'loading.html'));
 const prior = await health();
 if(prior) throw new Error('Port 3100 is already in use. Close the other local TRACE instance and retry.');
 server = launchEngine(runtime,home);
 const deadline = Date.now()+180000;
 let ready;
 while(Date.now()<deadline) {
  if(server.exitCode !== null) throw new Error('The analysis engine stopped. Details are in the data folder: engine.log.');
  ready = await health();
  if(ready) break;
  await new Promise(resolve=>setTimeout(resolve,300));
 }
 if(!ready) throw new Error('The local engine did not become ready. See engine.log in the data folder.');
 await verifyHomepage();
 worker=launchEngine(runtime,home,true);
 await window.loadURL(`${ORIGIN}/tcga_explorer/`);
 window.webContents.session.on('will-download',(_event,item)=>{
  item.setSaveDialogOptions({title:'Save TRACE result',defaultPath:path.join(app.getPath('downloads'),path.basename(item.getFilename()))});
 });
}
function stopChildren() {
 stopping = true;
 for(const child of children) {
  if(child.exitCode !== null || child.signalCode !== null || !child.pid) continue;
  if(process.platform==='win32') spawn('taskkill',['/PID',String(child.pid),'/T','/F'],{windowsHide:true,stdio:'ignore'});
  else child.kill('SIGTERM');
 }
}
if(!app.requestSingleInstanceLock()) app.quit();
else {
 app.on('second-instance',()=>{if(window){if(window.isMinimized())window.restore();window.focus();}});
 app.whenReady().then(start).catch(error=>{dialog.showErrorBox('TRACE could not start',error.message);app.quit();});
 app.on('before-quit',stopChildren);
 app.on('window-all-closed',()=>app.quit());
}
