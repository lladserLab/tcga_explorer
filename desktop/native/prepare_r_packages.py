"""Download exact Windows R libraries from the scientific lock, with checksums."""
from concurrent.futures import ThreadPoolExecutor, as_completed
import gzip
import hashlib
import json
import shutil
from pathlib import Path
import urllib.request
import zipfile

ROOT=Path(__file__).resolve().parents[2]
CACHE=ROOT/'desktop/build/downloads/r-packages'
LIB=ROOT/'desktop/build/runtime/windows/R/library'
CACHE.mkdir(parents=True,exist_ok=True)
LIB.mkdir(parents=True,exist_ok=True)
LOCK=json.loads((ROOT/'backend/renv.lock').read_text())['Packages']
CRAN='https://p3m.dev/cran/2026-07-25'
BIOC='https://bioconductor.posit.co/packages/3.20/bioc'
# These exact recommended versions are included with the pinned R 4.4.2 runtime.
BUILTIN={'KernSmooth','MASS','Matrix','boot','class','cluster','foreign','lattice','mgcv','nlme','nnet','rpart','spatial'}

def fetch(name,meta):
    version=meta['Version']
    # BiocParallel 1.40.2 has no Windows binary in Bioconductor 3.20.
    # Keep the release's Windows build; all TRACE scoring uses serial execution.
    if name == 'BiocParallel': version='1.40.0'
    if name=='littler':
        return {'package':name,'version':version,'status':'excluded_unix_cli','reason':'Not imported by TRACE; littler is a Unix Rscript alternative.'}
    if name in BUILTIN:
        return {'package':name,'version':version,'status':'verify_bundled_recommended'}
    repo=BIOC if meta['Source']=='Bioconductor' else CRAN
    filename=f'{name}_{version}.zip'
    path=CACHE/filename
    url=repo+'/bin/windows/contrib/4.4/'+filename
    errors=[]
    for attempt in range(3):
        try:
            if not path.exists() or not zipfile.is_zipfile(path):
                req=urllib.request.Request(url,headers={'User-Agent':'TRACE-Desktop-build/0.1'})
                with urllib.request.urlopen(req,timeout=90) as response:
                    data=response.read()
                path.write_bytes(data)
            with zipfile.ZipFile(path) as archive:
                for member in archive.namelist():
                    if Path(member).is_absolute() or '..' in Path(member).parts:
                        raise ValueError('Unsafe package path')
                shutil.rmtree(LIB/name, ignore_errors=True)
                archive.extractall(LIB)
            return {'package':name,'version':version,'status':'windows_binary','url':url,'bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
        except Exception as exc:
            errors.append(str(exc))
    # Pure-R source packages can be installed using the bundled R, without Rtools.
    source_url=(BIOC.rsplit('/bioc',1)[0]+'/data/annotation'+'/src/contrib/'+f'{name}_{version}.tar.gz') if name=='GenomeInfoDbData' else 'https://cloud.r-project.org/src/contrib/Archive/'+name+'/'+f'{name}_{version}.tar.gz'
    source_path=CACHE/f'{name}_{version}.tar.gz'
    if meta.get('NeedsCompilation','no')!='yes':
        try:
            urllib.request.urlretrieve(source_url,source_path)
            return {'package':name,'version':version,'status':'source_pending_install','url':source_url,'sha256':hashlib.sha256(source_path.read_bytes()).hexdigest()}
        except Exception as exc:errors.append(str(exc))
    return {'package':name,'version':version,'status':'failed','errors':errors}

results=[]
with ThreadPoolExecutor(max_workers=6) as executor:
    futures={executor.submit(fetch,name,meta):name for name,meta in LOCK.items()}
    for future in as_completed(futures):
        result=future.result();results.append(result)
        print(result['package'],result['status'],flush=True)
        (CACHE/'manifest.json').write_text(json.dumps(sorted(results,key=lambda r:r['package']),indent=2))
failures=[r for r in results if r['status']=='failed']
print('Failed:',json.dumps(failures),flush=True)
if failures:raise SystemExit(1)
