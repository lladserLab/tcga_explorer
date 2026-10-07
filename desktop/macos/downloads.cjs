const fs = require('node:fs');
const path = require('node:path');
const https = require('node:https');
const http = require('node:http');
const crypto = require('node:crypto');
const { pipeline } = require('node:stream/promises');

function checkedUrl(value) {
 const url=new URL(value);
 if(url.username || url.password || (url.protocol!=='https:' && !(url.protocol==='http:' && ['127.0.0.1','localhost'].includes(url.hostname)))) throw new Error('Use an HTTPS download address.');
 return url;
}
function responseFor(value, redirects=0) {
 const url=checkedUrl(value);
 return new Promise((resolve,reject)=>{
  const req=(url.protocol==='https:'?https:http).get(url,{headers:{'User-Agent':'TRACE-Explorer-Desktop'}},response=>{
   if([301,302,303,307,308].includes(response.statusCode)) {
    response.resume();if(redirects>=5 || !response.headers.location)return reject(new Error('Too many download redirects.'));
    responseFor(new URL(response.headers.location,url).href,redirects+1).then(resolve,reject);return;
   }
   if(response.statusCode!==200){response.resume();reject(new Error(`Download server returned HTTP ${response.statusCode}.`));return;}
   resolve(response);
  });
  req.setTimeout(60000,()=>req.destroy(new Error('The download server stopped responding.')));req.on('error',reject);
 });
}
async function fetchCatalog(value) {
 const base=checkedUrl(value).href,response=await responseFor(base);
 const chunks=[];let size=0;
 for await(const chunk of response){size+=chunk.length;if(size>2*1024*1024){response.destroy();throw new Error('Download catalog is too large.');}chunks.push(chunk);}
 const catalog=JSON.parse(Buffer.concat(chunks).toString());
 if(catalog.schema_version!=='trace-desktop-download-catalog-v1' || !Array.isArray(catalog.packages) || catalog.packages.length>500)throw new Error('Unsupported download catalog.');
 const ids=new Set();
 const packages=catalog.packages.map(entry=>{
  if(!/^[A-Z0-9-]{2,32}$/.test(entry.cancer_code) || !['tcga_reference','external'].includes(entry.source) || !/^[a-f0-9]{64}$/.test(entry.sha256) || !Number.isSafeInteger(entry.bytes) || entry.bytes<=0 || entry.bytes>20*1024**3 || !/^[a-f0-9]{16}$/.test(entry.snapshot)) throw new Error('Invalid data package in catalog.');
  const id=entry.cancer_code+':'+entry.source;if(ids.has(id))throw new Error('Duplicate cancer/source in catalog.');ids.add(id);
  return {...entry,id,url:checkedUrl(new URL(entry.url,base).href).href};
 });
 return {packages};
}
async function downloadPackage(entry, directory, onProgress=()=>{}) {
 fs.mkdirSync(directory,{recursive:true});
 const target=path.join(directory,`TRACE-${entry.cancer_code}-${entry.source}-${entry.snapshot}.tar.gz`),temporary=target+'.partial';
 if(fs.existsSync(target)&&fs.statSync(target).size===entry.bytes){
  const cached=crypto.createHash('sha256');for await(const chunk of fs.createReadStream(target))cached.update(chunk);
  if(cached.digest('hex')===entry.sha256){onProgress({phase:'importing',received:entry.bytes,total:entry.bytes});return target;}
 }
 const hash=crypto.createHash('sha256');let received=0,last=0;
 const response=await responseFor(entry.url);
 response.on('data',chunk=>{received+=chunk.length;hash.update(chunk);if(received>entry.bytes){response.destroy(new Error('Downloaded file exceeds its declared size.'));return;}
  if(Date.now()-last>200){last=Date.now();onProgress({phase:'downloading',received,total:entry.bytes});}});
 try {
  await pipeline(response,fs.createWriteStream(temporary));
  if(received!==entry.bytes || hash.digest('hex')!==entry.sha256)throw new Error('Data package verification failed. Download it again.');
  fs.renameSync(temporary,target);onProgress({phase:'importing',received,total:entry.bytes});return target;
 } finally {fs.rmSync(temporary,{force:true});}
}
module.exports={checkedUrl,fetchCatalog,downloadPackage};
