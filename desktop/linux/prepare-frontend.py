"""Copy a desktop Vite build and only its reviewed tutorial assets."""
from pathlib import Path
import hashlib,json,shutil

ROOT=Path(__file__).resolve().parents[2]
source=ROOT/'frontend/dist'
videos=source/'tutorial-videos'
manifest=json.loads((videos/'manifest.json').read_text())
keep={'manifest.json'}
for entry in manifest:
    video=videos/entry['path']
    assert video.stat().st_size==entry['bytes']
    digest=hashlib.sha256()
    with video.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):digest.update(chunk)
    assert digest.hexdigest()==entry['sha256']
    keep.update((entry['path'],str(Path(entry['path']).with_suffix('.jpg'))))
for asset in videos.rglob('*'):
    if asset.is_file() and asset.relative_to(videos).as_posix() not in keep:
        asset.unlink()
target=ROOT/'desktop/build/runtime/linux-x64/frontend'
if target.exists():shutil.rmtree(target)
shutil.copytree(source,target)
print('Desktop frontend and',len(manifest),'verified offline videos copied.')
