"""Assemble macOS source/assets without reading production or user workspaces."""
from pathlib import Path
import shutil
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'desktop/build/runtime/macos-arm64'
OUT.mkdir(parents=True,exist_ok=True)
ignore=shutil.ignore_patterns('__pycache__','*.pyc','.DS_Store')
for source,target in [('backend/app','backend/app'),('backend/scripts','backend/scripts'),('backend/gene_sets','backend/gene_sets'),('frontend/dist','frontend')]:
 target=OUT/target
 if target.exists():shutil.rmtree(target)
 shutil.copytree(ROOT/source,target,ignore=ignore)
shutil.copytree(ROOT/'repository_registry',OUT/'repository_registry',dirs_exist_ok=True,ignore=shutil.ignore_patterns('discovery','candidate_specs'))
for name in ['serving.py','cohorts.py','data_packages.py','tcga_packages.py','reference_updates.py','cohort-pins.json']:shutil.copy2(ROOT/'desktop/native'/name,OUT/name)
shutil.copy2(ROOT/'desktop/macos/engine.py',OUT/'engine.py');shutil.copy2(ROOT/'desktop/initialize.py',OUT/'initialize.py');shutil.copy2(ROOT/'LICENSE',OUT/'LICENSE');shutil.copy2(ROOT/'backend/renv.lock',OUT/'backend/renv.lock')
(OUT/'backend/docs').mkdir(exist_ok=True)
for name in ['API.md','API_ES.md']:shutil.copy2(ROOT/'docs'/name,OUT/'backend/docs'/name)
print(OUT)
