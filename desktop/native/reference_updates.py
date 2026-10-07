"""Preserve a local TCGA reference before replacing it while the engine is idle."""
import json
from contextlib import closing
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile


def require_idle():
    from sqlalchemy import select, func
    from app.database import SessionLocal
    from app.models import AnalysisJob, ComputeJob
    with SessionLocal() as db:
        for model in [AnalysisJob, ComputeJob]:
            if db.scalar(select(func.count()).select_from(model).where(model.status.in_(['queued','running']))):
                raise ValueError('Finish or cancel active analyses before updating data.')


def update_reference(package, staging):
    from app.config import get_settings
    from app.database import SessionLocal
    from app.models import Cohort, DataSource
    from app.importer import TCGA_RNA_SOURCE_ID
    from data_packages import identifier
    from tcga_packages import install_reference
    settings=get_settings();cohort_id='TCGA-'+identifier(package['cancer_code'])
    with SessionLocal() as db:
        cohort=db.get(Cohort,cohort_id);source=db.get(DataSource,TCGA_RNA_SOURCE_ID)
        old=((source.metadata_json or {}).get('desktop_packages') or {}).get(cohort_id) if source else None
        unchanged_or_new = not cohort or cohort.status=='external_only' or (old and old['snapshot']==package['snapshot'])
    if unchanged_or_new:
        return install_reference(package,staging)
    require_idle()
    home=settings.tcga_data_dir.parent
    history=home/'reference_history'/cohort_id
    history.mkdir(parents=True,exist_ok=True)
    backup=Path(tempfile.mkdtemp(prefix=(old or {}).get('snapshot','unversioned')+'-',dir=history))
    sqlite_file=home/'trace.sqlite'
    # SQLite backup includes committed WAL content; a raw file copy does not.
    with closing(sqlite3.connect(sqlite_file)) as current,closing(sqlite3.connect(backup/'trace.sqlite')) as saved:
        current.backup(saved)
    targets=[settings.tcga_data_dir/cohort_id,settings.derived_expression_dir/'matrices'/cohort_id]
    for index,target in enumerate(targets):
        if target.exists():shutil.copytree(target,backup/str(index))
    summary=settings.tcga_data_dir/'summary_table.tsv'
    if summary.exists():shutil.copy2(summary,backup/'summary_table.tsv')
    (backup/'reference.json').write_text(json.dumps(old or {},indent=2))
    try:
        result=install_reference(package,staging,replace_existing=True)
        return {**result,'previous_reference_preserved':str(backup)}
    except Exception:
        for index,target in enumerate(targets):
            shutil.rmtree(target,ignore_errors=True)
            if (backup/str(index)).exists():shutil.copytree(backup/str(index),target)
        if (backup/'summary_table.tsv').exists():shutil.copy2(backup/'summary_table.tsv',summary)
        # Close pooled SQLite handles before replacing the database and its WAL.
        # Keeping old handles alive can expose stale pages after a restore.
        from app.database import engine
        engine.dispose()
        for suffix in ['-wal','-shm']:
            Path(str(sqlite_file)+suffix).unlink(missing_ok=True)
        restored=sqlite_file.with_suffix('.restore')
        shutil.copy2(backup/'trace.sqlite',restored)
        os.replace(restored,sqlite_file)
        raise
