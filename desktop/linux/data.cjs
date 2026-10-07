const cancerNames={"ACC": "Adrenocortical carcinoma", "BLCA": "Bladder urothelial carcinoma", "BRCA": "Breast invasive carcinoma", "CESC": "Cervical squamous cell carcinoma and endocervical adenocarcinoma", "CHOL": "Cholangiocarcinoma", "CLL": "Chronic lymphocytic leukemia / small lymphocytic lymphoma", "COAD": "Colon adenocarcinoma", "DLBC": "Diffuse large B-cell lymphoma", "ESCA": "Esophageal carcinoma", "GBM": "Glioblastoma multiforme", "HNSC": "Head and neck squamous cell carcinoma", "KICH": "Kidney chromophobe", "KIRC": "Kidney renal clear cell carcinoma", "KIRP": "Kidney renal papillary cell carcinoma", "LAML": "Acute myeloid leukemia", "LGG": "Brain lower grade glioma", "LIHC": "Liver hepatocellular carcinoma", "LUAD": "Lung adenocarcinoma", "LUSC": "Lung squamous cell carcinoma", "MESO": "Mesothelioma", "OV": "Ovarian serous cystadenocarcinoma", "PAAD": "Pancreatic adenocarcinoma", "PCPG": "Pheochromocytoma and paraganglioma", "PLGG": "Pediatric low-grade glioma", "PRAD": "Prostate adenocarcinoma", "READ": "Rectum adenocarcinoma", "SARC": "Sarcoma", "SKCM": "Skin cutaneous melanoma", "STAD": "Stomach adenocarcinoma", "TGCT": "TGCT", "THCA": "Thyroid carcinoma", "THYM": "THYM", "UCEC": "Uterine corpus endometrial carcinoma", "UCS": "UCS", "UVM": "Uveal melanoma"};
const api=window.traceDesktop,$=id=>document.getElementById(id);
let installed=[],packages=[],localFiles=[],addedFiles=new Set(),busy=false,configured=false,catalogLoading=false;
const sourceName=value=>value==='tcga_reference'?'TCGA':'External studies';
const sizeName=bytes=>bytes>=1024**3?`${(bytes/1024**3).toFixed(1)} GB`:`${Math.max(1,Math.ceil(bytes/1024**2))} MB`;
function cancerName(entry){return `${entry.cancer_name||cancerNames[entry.cancer_code]||entry.cancer_code}${entry.cancer_name||cancerNames[entry.cancer_code]?` (${entry.cancer_code})`:''}`;}
function status(message,error=false){$('status').textContent=message;$('status').dataset.error=String(error);}
function setBusy(value){busy=value;document.querySelectorAll('button').forEach(button=>{if(button.getAttribute('role')!=='tab')button.disabled=value||button.dataset.stableDisabled==='true'||(button.id==='check'&&catalogLoading);});$('catalog-url').disabled=value;if(!value)$('progress').hidden=true;}
async function action(task){if(busy)return;setBusy(true);try{await task();}catch(error){status(error.message.replace(/^Error invoking remote method '[^']+': Error: /,''),true);}finally{setBusy(false);}}
function row(title,detail,label,click,disabled=false){const li=document.createElement('li'),text=document.createElement('div'),strong=document.createElement('strong'),small=document.createElement('small'),button=document.createElement('button');strong.textContent=title;small.textContent=detail;text.append(strong,small);button.textContent=label;button.dataset.stableDisabled=String(disabled);button.disabled=busy||disabled;button.addEventListener('click',()=>action(click));li.append(text,button);return li;}
function empty(id,text){const item=document.createElement('li');item.className='empty';item.textContent=text;$(id).replaceChildren(item);}
function render(){
 $('installed-count').textContent=installed.length?`(${installed.length} ${installed.length===1?'package':'packages'})`:'';
 $('installed').replaceChildren(...installed.map(entry=>row(cancerName(entry),`${sourceName(entry.source)}${entry.source==='external'?` · ${entry.studies} independent ${entry.studies===1?'study':'studies'}`:''}`,'Save a copy',async()=>{status('Preparing your copy…');const result=await api.exportPackage(entry);status(result?.canceled?'':'Copy saved as a .tar.gz package.');})));
 if(!installed.length)empty('installed','No cohorts added yet. Choose a local package or download one above.');
 const visible=packages.filter(entry=>($('source').value==='all'||entry.source===$('source').value)&&`${entry.cancer_code} ${entry.cancer_name||cancerNames[entry.cancer_code]||''}`.toLowerCase().includes($('search').value.trim().toLowerCase()));
 $('available').replaceChildren(...visible.map(entry=>{
  const local=installed.find(item=>item.cancer_code===entry.cancer_code&&item.source===entry.source),same=local?.snapshot===entry.snapshot;
  return row(cancerName(entry),`${sourceName(entry.source)} · ${sizeName(entry.bytes)}${entry.source==='external'&&entry.studies?` · ${entry.studies} ${entry.studies===1?'study':'studies'}`:''}${local&&!same?' · New version available':''}`,same?'Up to date':local?'Update':'Download',async()=>{status(`Downloading ${entry.cancer_code} · ${sourceName(entry.source)}…`);await api.download(entry.id);await loadInstalled();status('Data ready. Return to TRACE and choose the cohort.');},same);
 }));
 if(configured&&!visible.length)empty('available',packages.length?'No cancers match your search.':'No packages are listed at this download source.');
 $('remote-filters').hidden=!packages.length;
}
async function loadInstalled(){installed=await api.installed();render();}
async function check(){
 if(catalogLoading)return;catalogLoading=true;$('check').disabled=true;$('check').dataset.stableDisabled='false';
 try{const result=await api.catalog();packages=result.packages;configured=result.configured;$('catalog-url').value=result.url||'';$('catalog-note').textContent=configured?'Choose a cancer and source. Downloaded data will be ready for local analysis.':'Online downloads are not connected yet. Add a catalog link below, or use a package from this computer.';$('download-settings').open=!configured;$('check').dataset.stableDisabled=String(!configured);render();}
 catch(error){packages=[];configured=false;render();$('catalog-note').textContent='The download list could not be loaded. Check your connection and catalog link. Local packages are still available.';$('download-settings').open=true;throw error;}
 finally{catalogLoading=false;$('check').disabled=busy||$('check').dataset.stableDisabled==='true';}
}
function selectTab(id,focus=false){for(const tab of ['local','remote']){const selected=id===tab;$(tab+'-tab').setAttribute('aria-selected',String(selected));$(tab+'-tab').tabIndex=selected?0:-1;$(tab+'-panel').hidden=!selected;}if(focus)$(id+'-tab').focus();}
for(const id of ['local','remote']){$(id+'-tab').onclick=()=>selectTab(id);$(id+'-tab').onkeydown=event=>{if(['ArrowLeft','ArrowRight','Home','End'].includes(event.key)){event.preventDefault();selectTab(event.key==='Home'?'local':event.key==='End'?'remote':id==='local'?'remote':'local',true);}};}
$('back').onclick=()=>api.closeDataManager();
$('check').onclick=()=>action(async()=>{status('Refreshing the download list…');await check();status('Download list updated.');});
async function imported(result){if(result?.canceled){status('');return;}await loadInstalled();status('Data ready. Return to TRACE and choose the cohort.');}
$('import').onclick=()=>action(async()=>{status('Choose a TRACE data package…');await imported(await api.importPackage());});
$('browse').onclick=()=>action(async()=>{
 status('Choose the folder containing your data packages…');const result=await api.browseFolder();if(result.canceled){status('');return;}
 localFiles=result.files;$('local-folder').textContent=result.folder;$('local-folder').hidden=false;
 $('local-note').textContent=localFiles.length?`${localFiles.length} ${localFiles.length===1?'package found':'packages found'} in this folder${result.limited?' (showing the first 500)':''}. Choose one to add to TRACE.`:'No .tar.gz packages in this folder. Choose another folder or select a file.';
 $('local-search-label').hidden=!localFiles.length;addedFiles.clear();renderLocal();
 status('');
});
function renderLocal(){
 const query=$('local-search').value.trim().toLowerCase();
 const visible=localFiles.filter(entry=>`${entry.name} ${cancerNames[entry.name.match(/^TRACE-([A-Z0-9-]+)-(?:TCGA|external)(?:-|\.)/)?.[1]]||''}`.toLowerCase().includes(query));
 $('local-files').replaceChildren(...visible.map(entry=>{
  const match=entry.name.match(/^TRACE-([A-Z0-9-]+)-(TCGA|external)(?:-|\.)/),code=match?.[1];
  const title=code&&cancerNames[code]?`${cancerNames[code]} (${code}) · ${match[2]==='TCGA'?'TCGA':'External studies'}`:entry.name;
  return row(title,`${entry.name} · ${sizeName(entry.bytes)}`,addedFiles.has(entry.id)?'Added':'Add to TRACE',async()=>{
   status('Checking and adding the data package…');$('progress').removeAttribute('value');$('progress').hidden=false;
   await imported(await api.importLocal(entry.id));addedFiles.add(entry.id);renderLocal();
  },addedFiles.has(entry.id));
 }));
 if(localFiles.length&&!visible.length)empty('local-files','No packages match your search.');
}
$('local-search').oninput=renderLocal;
$('folder').onclick=()=>action(async()=>{const error=await api.openFolder();if(error)throw new Error(error);});
$('source-form').onsubmit=event=>{event.preventDefault();action(async()=>{status('Connecting to the download source…');await api.setCatalog($('catalog-url').value.trim());await check();status('Download source connected. Choose a cancer above.');});};
$('search').oninput=render;$('source').onchange=render;
api.onProgress(value=>{if(value.phase==='importing'){status('Download complete. Checking and adding the data…');$('progress').removeAttribute('value');}else{status(`Downloading ${sizeName(value.received)} of ${sizeName(value.total)}…`);$('progress').max=value.total;$('progress').value=value.received;}$('progress').hidden=false;});
// A slow or unreachable catalog must not block local data imports.
action(loadInstalled).then(()=>check().catch(error=>{if(!busy)status(error.message,true);}));
