// Desktop variant of the canonical TRACE vector mark; no web assets are modified.
const {chromium}=require('playwright');
const fs=require('node:fs/promises');
const path=require('node:path');
(async()=>{
 const dir=path.join(__dirname,'icons');await fs.mkdir(dir,{recursive:true});
 const source=await fs.readFile(path.join(__dirname,'../../frontend/public/brand/trace-mark.svg'),'utf8');
 const svg=source.replace('<rect width="64" height="64" fill="#182235"/>','<rect x="1" y="1" width="62" height="62" rx="13" fill="#F4FAFB"/>').replace('stroke="#86D3E2"','stroke="#182235"').replace('rx="1.5" fill="#F4FAFB"','rx="1.5" fill="#86D3E2"');
 await fs.writeFile(path.join(dir,'trace-desktop.svg'),svg);
 const browser=await chromium.launch({headless:true});const frames=[];
 try{for(const size of [16,24,32,48,64,128,256]){
  const page=await browser.newPage({viewport:{width:size,height:size},deviceScaleFactor:1});
  await page.setContent(`<style>html,body{margin:0;background:transparent}svg{display:block;width:${size}px;height:${size}px}</style>${svg}`);
  const data=await page.screenshot({omitBackground:true});frames.push({size,data});
  if(size===256)await fs.writeFile(path.join(dir,'trace-desktop.png'),data);
  await page.close();
 }}finally{await browser.close();}
 const header=Buffer.alloc(6);header.writeUInt16LE(1,2);header.writeUInt16LE(frames.length,4);let offset=6+16*frames.length;
 const entries=frames.map(({size,data})=>{const entry=Buffer.alloc(16);entry[0]=entry[1]=size===256?0:size;entry.writeUInt16LE(1,4);entry.writeUInt16LE(32,6);entry.writeUInt32LE(data.length,8);entry.writeUInt32LE(offset,12);offset+=data.length;return entry;});
 await fs.writeFile(path.join(dir,'trace-desktop.ico'),Buffer.concat([header,...entries,...frames.map(f=>f.data)]));
 console.log('Generated transparent desktop icon in seven Windows sizes.');
})();
