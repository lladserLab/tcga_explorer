from pathlib import Path
import json,os,subprocess
root=Path(__file__).resolve().parents[2];r=root/'desktop/build/runtime/macos-arm64/R'
env={**os.environ,'RHOME':str(r),'R_HOME':str(r),'R_LIBS_USER':str(r/'library'),'LC_ALL':'en_US.UTF-8'}
manifest=json.loads((root/'desktop/build/macos/downloads/r-packages/manifest.json').read_text())
for item in manifest:
 if item['status']=='source_pending':
  subprocess.run([str(r/'bin/R'),'CMD','INSTALL','--library='+str(r/'library'),str(root/item['path'])],env=env,check=True)
