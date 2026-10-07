"""Copy only runtime source/assets into the Windows bundle; never private data."""
from pathlib import Path
import shutil

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'desktop/build/runtime/windows'
OUT.mkdir(parents=True,exist_ok=True)
ignore=shutil.ignore_patterns('__pycache__','*.pyc','.DS_Store')
for source,target in [
 ('backend/app','backend/app'), ('backend/scripts','backend/scripts'),
 ('backend/gene_sets','backend/gene_sets'), ('frontend/dist','frontend')]:
 shutil.copytree(ROOT/source,OUT/target,dirs_exist_ok=True,ignore=ignore)
# The upload registry needs taxonomy only; discovery snapshots are not shipped.
(OUT/'repository_registry').mkdir(exist_ok=True)
shutil.copytree(ROOT/'repository_registry',OUT/'repository_registry',dirs_exist_ok=True,ignore=shutil.ignore_patterns('discovery', 'candidate_specs'))
(OUT/'backend/docs').mkdir(exist_ok=True)
for name in ['API.md','API_ES.md']:
 shutil.copy2(ROOT/'docs'/name,OUT/'backend/docs'/name)
for source,target in [('backend/renv.lock','backend/renv.lock'), ('desktop/initialize.py','initialize.py'),
 ('desktop/native/engine.py','engine.py'), ('desktop/native/serving.py','serving.py'), ('desktop/native/cohorts.py','cohorts.py'), ('desktop/native/data_packages.py','data_packages.py'), ('desktop/native/tcga_packages.py','tcga_packages.py'), ('desktop/native/cohort-pins.json','cohort-pins.json'), ('LICENSE','LICENSE')]:
 shutil.copy2(ROOT/source,OUT/target)
print(OUT)
shutil.copy2(ROOT/'desktop/native/reference_updates.py',OUT/'reference_updates.py')
