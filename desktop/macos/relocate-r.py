"""Audit and rewrite R Mach-O references to paths inside the desktop runtime."""
from pathlib import Path
import subprocess,json,os
ROOT=Path(__file__).resolve().parents[2];R=ROOT/'desktop/build/runtime/macos-arm64/R'
MACH={b'\xcf\xfa\xed\xfe',b'\xce\xfa\xed\xfe',b'\xca\xfe\xba\xbe',b'\xfe\xed\xfa\xcf'}
def mach(p):
 try:
  with p.open('rb') as f:return f.read(4) in MACH
 except OSError:return False
files=[p for p in R.rglob('*') if p.is_file() and not p.is_symlink() and p.suffix != ".class" and mach(p)]
external=set();patches=[]
for p in files:
 output=subprocess.check_output(['otool','-L',str(p)],text=True)
 for line in output.splitlines()[1:]:
  old=line.strip().split(' (',1)[0]
  if old.startswith('/Library/Frameworks/R.framework/'):
   relative=old.split('/Resources/',1)[-1];target=R/relative
   if not target.exists():external.add(old);continue
   new='@loader_path/'+os.path.relpath(target,p.parent)
   patches.append((p,old,new))
  elif old.startswith(str(R)):
   target=Path(old);patches.append((p,old,'@loader_path/'+os.path.relpath(target,p.parent)))
  elif old.startswith('/opt/X11/lib/'):
   target=R/'lib'/Path(old).name
   if target.exists():patches.append((p,old,'@loader_path/'+os.path.relpath(target,p.parent)))
   else:external.add(old)
  elif old.startswith('/') and not old.startswith(('/System/Library/','/usr/lib/')):external.add(old)
report={'mach_o_files':len(files),'external_dependencies':sorted(external),'patches':len(patches)}
print(json.dumps(report,indent=2),flush=True)
(ROOT/'desktop/runtime/probe/macos/r-link-audit.json').write_text(json.dumps(report,indent=2)+'\n')
if external:raise SystemExit(1)
for p,old,new in patches:
 subprocess.run(['install_name_tool','-change',old,new,str(p)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
for p in files:
 subprocess.run(['codesign','--force','--sign','-',str(p)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
print('Relocated and ad-hoc signed',len(files),'Mach-O files')
