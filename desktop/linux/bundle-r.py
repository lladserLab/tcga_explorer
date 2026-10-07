"""Run in the pinned x86_64 build environment after restoring renv.lock.

Copy R and its non-glibc ELF closure, with no development OS in the installer.
"""
from pathlib import Path
import os,shutil,subprocess,json,re
ROOT=Path('/project');OUT=ROOT/'desktop/build/runtime/linux-x64';R=OUT/'R'
if R.exists():shutil.rmtree(R)
shutil.copytree('/usr/local/lib/R',R,symlinks=False,ignore=shutil.ignore_patterns('site-library'))
# RenV may install links into its external cache; resolve them into the bundle.
for p in Path('/usr/local/lib/R/site-library').iterdir():
    if p.is_dir() and not p.name.startswith('00LOCK'):
        t=R/'library'/p.name
        if t.exists():shutil.rmtree(t)
        shutil.copytree(p,t,symlinks=False)
(R/'site-library').mkdir()
# The Tcl/Tk GUI is unused and would introduce dependencies on system GUI assets.
shutil.rmtree(R/'library/tcltk',ignore_errors=True)
for name in ['doc','include']:shutil.rmtree(R/name,ignore_errors=True)
(R/'doc').mkdir();(R/'include').mkdir()
bundled=R/'lib/bundled';bundled.mkdir(parents=True)
SYSTEM={'libc.so.6','libm.so.6','libpthread.so.0','libdl.so.2','librt.so.1','libresolv.so.2','libutil.so.1','ld-linux-x86-64.so.2'}
def elf(p):
    try:
        with p.open('rb') as f:return f.read(4)==b'\x7fELF'
    except OSError:return False
queue=[p for p in R.rglob('*') if p.is_file() and elf(p)];processed=set();deps={}
while queue:
    p=queue.pop()
    if str(p) in processed:continue
    processed.add(str(p))
    text=subprocess.run(['ldd',str(p)],capture_output=True,text=True,env={**os.environ,'LD_LIBRARY_PATH':str(R/'lib')+':'+str(bundled)}).stdout
    if 'not found' in text:raise RuntimeError(f'Unresolved dependency: {p}\n{text}')
    for line in text.splitlines():
        m=re.match(r'\s*(\S+) => (/\S+)',line)
        if not m:continue
        name,source=m.groups()
        if name in SYSTEM or name=='libR.so':continue
        dest=bundled/name
        if not dest.exists():shutil.copy2(source,dest);queue.append(dest);deps[name]=source
# Every object prefers its bundle closure over absolute build-time search paths.
for p in [p for p in R.rglob('*') if p.is_file() and elf(p)]:
    relative=os.path.relpath(bundled,p.parent)
    subprocess.run(['patchelf','--set-rpath','$ORIGIN/'+relative+':$ORIGIN/'+os.path.relpath(R/'lib',p.parent),str(p)],check=True)
# R_HOME, R_SHARE_DIR etc must be derived from the installed path, which may include spaces.
launcher=R/'bin/R';s=launcher.read_text();s=re.sub(r'R_HOME_DIR=.*?\n','R_HOME_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"\n',s,count=1)
s=s[:s.index('if test "${R_HOME_DIR}"')] + s[s.index('if test -n "${R_HOME}"'):]
s=s.replace('/usr/local/lib/R', '${R_HOME_DIR}')
# R encodes spaces as ~+~ when dispatching script files; accept the real path.
launcher.write_text(s)
(R/'etc/ldpaths').write_text('LD_LIBRARY_PATH="${R_HOME}/lib/bundled:${R_HOME}/lib"\nexport LD_LIBRARY_PATH\n')
conf=R/'etc/Renviron';s=conf.read_text().replace('/usr/local/lib/R','${R_HOME}')
conf.write_text(s)
# Do not overwrite system fonts configuration or depend on it.
fonts=R/'fonts';fonts.mkdir();shutil.copytree('/usr/share/fonts/truetype/dejavu',fonts/'dejavu',dirs_exist_ok=True)
(R/'etc/fonts.conf').write_text('<?xml version="1.0"?><!DOCTYPE fontconfig SYSTEM "urn:fontconfig:fonts.dtd"><fontconfig><dir prefix="relative">../fonts</dir><cachedir prefix="xdg">fontconfig</cachedir></fontconfig>\n')
notices=OUT/'licenses/linux-libraries';notices.mkdir(parents=True,exist_ok=True)
for source in list(deps.values())+['/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf']:
    query=subprocess.run(['dpkg-query','-S',str(Path(source).resolve())],capture_output=True,text=True)
    if query.returncode:query=subprocess.run(['dpkg-query','-S',source],capture_output=True,text=True)
    if not query.returncode:
        package=query.stdout.split(': ',1)[0].split(':')[0]
        notice=Path('/usr/share/doc')/package/'copyright'
        if notice.exists():shutil.copy2(notice,notices/(package+'.txt'))
report={'R':'4.4.2','architecture':'x86_64','glibc_minimum':'2.39','bundled_non_glibc_libraries':deps,'elf_objects':len(processed)}
(ROOT/'desktop/build/linux/r-link-audit.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report))
