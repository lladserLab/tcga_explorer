"""Materialize external-cohort clinical grouping options for fast UI reads."""

from __future__ import annotations

from sqlalchemy import select

from app.clinical_grouping import clinical_grouping_context
from app.database import SessionLocal, wait_for_database
from app.models import RepositoryDataset, RepositoryRelease
from app.repository.service import (
    CLINICAL_GROUPING_CACHE_KEY,
    repository_samples,
    resolve_repository_context,
)


def main() -> None:
    wait_for_database()
    with SessionLocal() as db:
        dataset_ids = list(
            db.scalars(
                select(RepositoryDataset.id)
                .where(RepositoryDataset.status == "available")
                .where(RepositoryDataset.visibility == "public")
                .order_by(RepositoryDataset.id)
            ).all()
        )
        updated = 0
        retained = 0
        for dataset_id in dataset_ids:
            context = resolve_repository_context(db, dataset_id)
            current = (context.release.qc_json or {}).get(
                CLINICAL_GROUPING_CACHE_KEY
            )
            if (
                isinstance(current, dict)
                and current.get("manifest_hash") == context.release.manifest_hash
                and isinstance(current.get("variables"), list)
            ):
                retained += 1
                continue
            samples = repository_samples(db, context)
            variables, _ = clinical_grouping_context(
                samples,
                cohort=context.cohort,
                repository=True,
            )
            release = db.get(RepositoryRelease, context.release.id)
            release.qc_json = {
                **(release.qc_json or {}),
                CLINICAL_GROUPING_CACHE_KEY: {
                    "schema_version": CLINICAL_GROUPING_CACHE_KEY,
                    "manifest_hash": context.release.manifest_hash,
                    "variables": variables,
                },
            }
            updated += 1
            if updated % 10 == 0:
                db.commit()
                print(f"Cached {updated} releases...", flush=True)
        db.commit()
        print(
            f"Clinical grouping cache ready: {updated} updated, "
            f"{retained} already current, {len(dataset_ids)} total.",
            flush=True,
        )


if __name__ == "__main__":
    main()
