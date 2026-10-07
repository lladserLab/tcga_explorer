"""Keep redistribution notices and exact build information beside the runtime."""
from pathlib import Path
import json,shutil
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'desktop/build/runtime/linux-x64/licenses'
OUT.mkdir(exist_ok=True)
(OUT/'SOURCES.txt').write_text('''TRACE includes Electron 44.5.1, standalone CPython 3.13.16 and R 4.4.2.
Python binary and checksum: runtime-archives.json
Python source: https://www.python.org/ftp/python/3.13.16/Python-3.13.16.tgz
R source: https://cran.r-project.org/src/base/R-4/R-4.4.2.tar.gz
R COPYING is retained in runtime/R/COPYING.
R package versions and source locations: r-packages.json and backend/renv.lock.
Python package licenses: python/lib/python3.13/site-packages/*.dist-info.
Electron LICENSE and third-party notices: the application root.
Linux runtime ELF libraries and build origins: r-link-audit.json.
Linux launcher/runtime changes: packaging-sources/.
TRACE source: https://github.com/lladserLab/tcga_explorer
''')
rows=[]
for name,m in json.loads((ROOT/'backend/renv.lock').read_text())['Packages'].items():
    version=m['Version']
    repo=('https://bioconductor.posit.co/packages/3.20/data/annotation' if name=='GenomeInfoDbData' else 'https://bioconductor.posit.co/packages/3.20/bioc') if m['Source']=='Bioconductor' else 'https://p3m.dev/cran/2026-07-25'
    rows.append({'package':name,'version':version,'source':repo+'/src/contrib/'+name+'_'+version+'.tar.gz'})
(OUT/'r-packages.json').write_text(json.dumps(rows,indent=2)+'\n')
for name in ['runtime-archives.json']:
    shutil.copy2(ROOT/'desktop/linux'/name,OUT/name)
shutil.copy2(ROOT/'desktop/build/linux/r-link-audit.json',OUT/'r-link-audit.json')
p=OUT/'packaging-sources';p.mkdir(exist_ok=True)
for source in (ROOT/'desktop/linux').iterdir():
    if source.is_file() and source.suffix in ['.py','.R','.cjs','.json','.html','.css','.md']:shutil.copy2(source,p/source.name)
shutil.copy2(ROOT/'backend/requirements.lock',p/'requirements.lock')
