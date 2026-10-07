"""Retrieve the locked scientific R libraries as native arm64 macOS archives."""
from concurrent.futures import ThreadPoolExecutor, as_completed
import gzip,hashlib,json,tarfile,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
CACHE=ROOT/'desktop/build/macos/downloads/r-packages';CACHE.mkdir(parents=True,exist_ok=True)
LOCK=json.loads((ROOT/'backend/renv.lock').read_text())['Packages']
BUILTIN={'KernSmooth','MASS','Matrix','boot','class','cluster','foreign','lattice','mgcv','nlme','nnet','rpart','spatial'}
def fetch(item):
 name,meta=item;version=meta['Version']
 if name in BUILTIN:return {'package':name,'version':version,'status':'bundled_recommended'}
 if name=='littler':return {'package':name,'version':version,'status':'excluded_unused_cli'}
 repo='https://bioconductor.posit.co/packages/3.20/bioc' if meta['Source']=='Bioconductor' else 'https://p3m.dev/cran/2026-07-25'
 url=repo+'/bin/macosx/big-sur-arm64/contrib/4.4/'+f'{name}_{version}.tgz';p=CACHE/f'{name}_{version}.tgz'
 errors=[]
 for attempt in range(2):
  try:
   if not p.exists():
    with urllib.request.urlopen(url,timeout=90) as r:p.write_bytes(r.read())
   with tarfile.open(p):pass
   return {'package':name,'version':version,'status':'macos_binary','url':url,'path':str(p.relative_to(ROOT)),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
  except Exception as e:errors.append(str(e))
 if name=='GenomeInfoDbData':source='https://bioconductor.posit.co/packages/3.20/data/annotation/src/contrib/'+f'{name}_{version}.tar.gz'
 elif meta['Source']=='Bioconductor':source=repo+'/src/contrib/'+f'{name}_{version}.tar.gz'
 else:source='https://cloud.r-project.org/src/contrib/Archive/'+name+'/'+f'{name}_{version}.tar.gz'
 try:
  p=CACHE/f'{name}_{version}.tar.gz'
  if not p.exists():
   with urllib.request.urlopen(source,timeout=90) as r:p.write_bytes(r.read())
  return {'package':name,'version':version,'status':'source_pending','url':source,'path':str(p.relative_to(ROOT)),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
 except Exception as e:return {'package':name,'version':version,'status':'failed','errors':errors+[str(e)]}
results=[]
with ThreadPoolExecutor(max_workers=8) as ex:
 for future in as_completed([ex.submit(fetch,item) for item in LOCK.items()]):
  r=future.result();results.append(r);print(r['package'],r['status'],flush=True)
  (CACHE/'manifest.json').write_text(json.dumps(sorted(results,key=lambda r:r['package']),indent=2)+'\n')
if any(r['status']=='failed' for r in results):raise SystemExit(1)
