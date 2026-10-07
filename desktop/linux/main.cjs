const { app, BrowserWindow, dialog, Menu, shell, ipcMain } = require('electron');
const { spawn } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
let PORT = 3100;
let ORIGIN = `http://127.0.0.1:${PORT}`;
if(process.env.TRACE_DESKTOP_TEST_USER_DATA) app.setPath('userData',path.resolve(process.env.TRACE_DESKTOP_TEST_USER_DATA));
async function choosePort() {
 const net=require('node:net');
 const file=path.join(app.getPath('userData'),'desktop-server.json');
 let saved;
 if(fs.existsSync(file)){saved=JSON.parse(fs.readFileSync(file,'utf8')).port;if(!Number.isInteger(saved)||saved<1024||saved>65535)throw new Error('The saved local port is invalid. See desktop-server.json in the data folder.');}
 const bind=port=>new Promise((resolve,reject)=>{const server=net.createServer();server.once('error',reject);server.listen(port,'127.0.0.1',()=>{const selected=server.address().port;server.close(()=>resolve(selected));});});
 if(saved){try{PORT=await bind(saved);}catch(error){if(error.code==='EADDRINUSE')throw new Error(`Local port ${saved} is in use. Close the other service and reopen TRACE.`);throw error;}}
 else{try{PORT=await bind(3100);}catch(error){if(error.code!=='EADDRINUSE')throw error;PORT=await bind(0);}fs.mkdirSync(path.dirname(file),{recursive:true});fs.writeFileSync(file,JSON.stringify({port:PORT}));}
 ORIGIN=`http://127.0.0.1:${PORT}`;
}

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
 const child = spawn(path.join(runtime,'python','bin','python3'),
  ['-I','-B',path.join(runtime,'engine.py'), ...(worker ? ['--worker'] : [])], {
   cwd:runtime, detached:true, windowsHide:true, stdio:['ignore',log,log],
   env:{...process.env,TRACE_DESKTOP_HOME:home,TRACE_DESKTOP_PORT:String(PORT),PYTHONUNBUFFERED:'1',PYTHONDONTWRITEBYTECODE:'1'}
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
  const child=spawn(path.join(runtime,'python','bin','python3'),['-I','-B',path.join(runtime,'engine.py'),...args],
   {cwd:runtime,detached:true,windowsHide:true,stdio:['ignore','pipe','pipe'],env:{...process.env,TRACE_DESKTOP_HOME:home,TRACE_DESKTOP_PORT:String(PORT),PYTHONUNBUFFERED:'1',PYTHONDONTWRITEBYTECODE:'1'}});
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
 require("./platform.cjs").requireSupportedGlibc(process.report?.getReport?.()?.header?.glibcVersionRuntime);
 await choosePort();
 const home = path.join(app.getPath('userData'),'workspace');
 fs.mkdirSync(home,{recursive:true});
 const runtime = app.isPackaged ? path.join(process.resourcesPath,'runtime') : path.resolve(__dirname,'../build/runtime/linux-x64');
 window = new BrowserWindow({width:1440,height:1000,minWidth:900,minHeight:650,
  title:'TRACE Explorer',icon:path.join(__dirname,'icons','trace-desktop.png'),autoHideMenuBar:true,webPreferences:{preload:path.join(__dirname,'preload.cjs'),nodeIntegration:false,contextIsolation:true,sandbox:true}});
 window.webContents.session.setPermissionRequestHandler((_contents,_permission,callback)=>callback(false));
 window.webContents.setWindowOpenHandler(()=>({action:'deny'}));
 window.webContents.on('will-navigate',(event,url)=>{if(new URL(url).origin !== ORIGIN) event.preventDefault();});
 window.webContents.on('will-prevent-unload',event=>{
  const choice=dialog.showMessageBoxSync(window,{type:'question',title:'Close TRACE?',message:'This page has unsaved changes.',buttons:['Close without saving','Keep working'],defaultId:1,cancelId:1});
  if(choice===0)event.preventDefault();
 });
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
 if(prior) throw new Error('The selected local port is already in use. Close the other local TRACE instance and retry.');
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
  else {try{process.kill(-child.pid,'SIGTERM');}catch(error){if(error.code!=='ESRCH')throw error;}}
 }
}
if(!app.requestSingleInstanceLock()) app.quit();
else {
 app.on('activate',()=>{if(window&&!window.isDestroyed()){window.show();window.focus();}});
 app.on('second-instance',()=>{if(window){if(window.isMinimized())window.restore();window.focus();}});
 app.whenReady().then(start).catch(error=>{dialog.showErrorBox('TRACE could not start',error.message);app.quit();});
 app.on('will-quit',event=>{
  if(stopping)return;
  event.preventDefault();
  stopChildren();
  const deadline=Date.now()+10000;
  const timer=setInterval(()=>{
   const active=children.filter(child=>child.pid&&child.exitCode===null&&child.signalCode===null);
   if(active.length&&Date.now()<deadline)return;
   clearInterval(timer);
   for(const child of active){try{process.kill(-child.pid,'SIGKILL');}catch(error){if(error.code!=='ESRCH')throw error;}}
   app.quit();
  },100);
 });
 app.on('window-all-closed',()=>app.quit());
}
