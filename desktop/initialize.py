"""Register cancer names for local uploads without importing public cohorts.

Run after schema migrations using the administrator connection. Never copy
public coverage counts or create cohort/patient records from the registry.
"""
import json
from pathlib import Path

from app.database import SessionLocal
from app.models import CancerType
from app.config import get_settings


def initialize() -> None:
    registry = json.loads((get_settings().cancer_repository_registry_dir / 'cancer_types.json').read_text())
    added = 0
    with SessionLocal() as db:
        for index, entry in enumerate(registry['cancer_types']):
            if db.get(CancerType, entry['code']) is not None:
                continue
            db.add(CancerType(
                code=entry['code'], tcga_cohort=entry['tcga_cohort'],
                name=entry['name'], primary_site=entry.get('primary_site'),
                sort_order=index, coverage_status='unsearched',
                coverage_metadata={'local_catalog': True},
            ))
            added += 1
        db.commit()
    print(json.dumps({'local_cancer_contexts_added': added}))


if __name__ == '__main__':
    initialize()
