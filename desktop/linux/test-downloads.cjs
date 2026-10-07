const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const os=require('node:os');
const path=require('node:path');
const http=require('node:http');
const crypto=require('node:crypto');
const {checkedUrl,fetchCatalog,downloadPackage}=require('./downloads.cjs');
const {installDataActions}=require('./data-actions.cjs');

test('Catalog downloads validate size/hash and remove corrupt partial files',async()=>{
 const bytes=Buffer.from('public package');const entry={cancer_code:'KIRC',source:'tcga_reference',snapshot:'a'.repeat(16),sha256:crypto.createHash('sha256').update(bytes).digest('hex'),bytes:bytes.length,url:'package.tar.gz'};
 const server=http.createServer((request,response)=>{
  if(request.url==='/catalog.json')response.end(JSON.stringify({schema_version:'trace-desktop-download-catalog-v1',packages:[entry]}));
  else response.end(bytes);
 });
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'trace-download-'));
 try{
  const catalog=await fetchCatalog(`http://127.0.0.1:${server.address().port}/catalog.json`);
  assert.equal(catalog.packages[0].id,'KIRC:tcga_reference');
  const progress=[];const file=await downloadPackage(catalog.packages[0],root,value=>progress.push(value));
  assert.deepEqual(fs.readFileSync(file),bytes);assert.equal(progress.at(-1).phase,'importing');
  await assert.rejects(downloadPackage({...catalog.packages[0],sha256:'0'.repeat(64)},root),/verification failed/);
  await assert.rejects(downloadPackage({...catalog.packages[0],bytes:1},root),/declared size/);
  assert.deepEqual(fs.readFileSync(file),bytes);assert(!fs.readdirSync(root).some(name=>name.endsWith('.partial')));
  assert.throws(()=>checkedUrl('http://example.com/catalog.json'),/HTTPS/);
  assert.throws(()=>checkedUrl('https://user:secret@example.com/catalog.json'),/HTTPS/);
 }finally{server.closeAllConnections();await new Promise(resolve=>server.close(resolve));fs.rmSync(root,{recursive:true,force:true});}
});

test('Folder discovery only imports files chosen through the native dialog',async()=>{
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'trace-folder-')),handlers={},imports=[];
 const event={senderFrame:{url:'http://127.0.0.1:3100/tcga_explorer/'}};
 const archive=path.join(root,'TRACE-KIRC-TCGA.tar.gz');fs.writeFileSync(archive,'test');
 fs.writeFileSync(path.join(root,'notes.txt'),'ignore');fs.mkdirSync(path.join(root,'nested'));
 fs.writeFileSync(path.join(root,'nested','hidden.tar.gz'),'ignore');
 fs.symlinkSync(archive,path.join(root,'link.tar.gz'));
 let canceled=false;
 try{
  installDataActions({ipcMain:{handle:(name,fn)=>handlers[name]=fn},dialog:{showOpenDialog:async()=>({canceled,filePaths:[root]})},home:root,origin:'http://127.0.0.1:3100',importData:async file=>{imports.push(file);return {};}});
  const result=await handlers['trace:data-browse'](event);
  assert.equal(result.files.length,1);assert.equal(result.files[0].name,'TRACE-KIRC-TCGA.tar.gz');assert.equal(result.files[0].bytes,4);
  assert.equal(result.files[0].filePath,undefined);
  await assert.rejects(handlers['trace:data-import-local'](event,archive),/Choose a folder again/);
  await handlers['trace:data-import-local'](event,result.files[0].id);assert.deepEqual(imports,[archive]);
  canceled=true;assert.deepEqual(await handlers['trace:data-browse'](event),{canceled:true});
  canceled=false;await handlers['trace:data-browse'](event);
  await assert.rejects(handlers['trace:data-import-local'](event,result.files[0].id),/Choose a folder again/);
  fs.unlinkSync(archive);
  await assert.rejects(handlers['trace:data-import-local'](event,result.files[0].id),/Choose a folder again/);
 }finally{fs.rmSync(root,{recursive:true,force:true});}
});

test('Native data actions reject foreign frames and uninstalled export sources',async()=>{
 const handlers={};const root=fs.mkdtempSync(path.join(os.tmpdir(),'trace-ipc-'));
 const event={senderFrame:{url:'http://127.0.0.1:3100/tcga_explorer/'}};
 try{
  installDataActions({ipcMain:{handle:(name,fn)=>handlers[name]=fn},window:{isDestroyed:()=>false},runtime:'/runtime',home:root,origin:'http://127.0.0.1:3100',runDataCommand:async()=>[{cancer_code:'KIRC',source:'tcga_reference'}]});
  await assert.rejects(handlers['trace:data-installed']({senderFrame:{url:'https://malicious.example/'}}),/only available/);
  await assert.rejects(handlers['trace:data-export'](event,{cancer_code:'SKCM',source:'external'}),/not installed/);
  assert.deepEqual(await handlers['trace:data-catalog'](event),{configured:false,url:'',packages:[]});
  await assert.rejects(handlers['trace:data-download'](event,'forged'),/Check for updates/);
  await handlers['trace:data-catalog-set'](event,'https://example.org/catalog.json');
  assert.equal(JSON.parse(fs.readFileSync(path.join(root,'downloads.json'))).catalog_url,'https://example.org/catalog.json');
 }finally{fs.rmSync(root,{recursive:true,force:true});}
});
