from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.config import get_settings
from app.database import SessionLocal, init_db
from app.repository.adapters.cbioportal import build_cbioportal_bundle
from app.repository.catalog import sync_repository_catalog
from app.repository.discovery import discover_cbioportal_candidates
from app.repository.importer import (
    preflight_bundle_promotion,
    promote_bundle,
    revalidate_active_releases,
    validate_bundle,
)
from app.repository.rank_attestation import attest_legacy_rank_layers


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(
        description="Curate and publish external bulk RNA-seq datasets."
    )
    subcommands = command.add_subparsers(dest="command", required=True)

    subcommands.add_parser("sync-catalog")
    subcommands.add_parser("revalidate-active")
    attest_rank = subcommands.add_parser(
        "attest-rank-layer",
        help=(
            "Scan one historical public release for rank-scoring matrix "
            "completeness; dry-run unless --apply is supplied."
        ),
    )
    attest_rank.add_argument("--release-id", required=True)
    attest_rank.add_argument("--apply", action="store_true")

    for name in ("build-study", "build-cbioportal"):
        build = subcommands.add_parser(name)
        build.add_argument("--spec", type=Path, required=True)
        build.add_argument("--output", type=Path, required=True)
        build.add_argument("--force", action="store_true")

    validate = subcommands.add_parser("validate")
    validate.add_argument("--bundle", type=Path, required=True)

    discover = subcommands.add_parser("discover-cbioportal")
    discover.add_argument("--output", type=Path, required=True)
    discover.add_argument("--registry-dir", type=Path)

    promote = subcommands.add_parser("promote")
    promote.add_argument("--bundle", type=Path, required=True)
    promote.add_argument("--repository-root", type=Path)
    promote.add_argument("--registry-root", type=Path)

    report = subcommands.add_parser("coverage-report")
    report.add_argument("--output", type=Path)
    return command


def main() -> None:
    args = parser().parse_args()
    settings = get_settings()
    if args.command in {"build-study", "build-cbioportal"}:
        result = build_cbioportal_bundle(
            args.spec, args.output, force=args.force
        )
        print(
            json.dumps(
                {
                    "dataset_id": result["dataset"]["id"],
                    "release_id": result["release"]["id"],
                    "build": result["build"],
                    "bundle": str(args.output),
                },
                indent=2,
            )
        )
        return
    if args.command == "validate":
        result = validate_bundle(args.bundle)
        print(json.dumps(result["qc"], indent=2, sort_keys=True))
        if result["qc"]["status"] != "passed":
            raise SystemExit(1)
        return
    if args.command == "discover-cbioportal":
        result = discover_cbioportal_candidates(
            args.registry_dir or settings.cancer_repository_registry_dir
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(
            json.dumps(
                {
                    **result["summary"],
                    "output": str(args.output),
                },
                indent=2,
                sort_keys=True,
            )
        )
        return

    registry_root = settings.cancer_repository_registry_dir
    if args.command == "promote":
        registry_root = args.registry_root or registry_root
        # Run the complete read-only gate before database initialization or
        # catalog synchronization can mutate persistent state. promote_bundle
        # repeats the same gate for direct-call safety.
        preflight_bundle_promotion(args.bundle, registry_root)

    init_db()
    with SessionLocal() as db:
        if args.command == "sync-catalog":
            result = sync_repository_catalog(
                db, settings.cancer_repository_registry_dir
            )
        elif args.command == "revalidate-active":
            sync_repository_catalog(
                db, settings.cancer_repository_registry_dir
            )
            result = revalidate_active_releases(
                db, settings.cancer_repository_dir
            )
        elif args.command == "promote":
            sync_repository_catalog(
                db, registry_root
            )
            result = promote_bundle(
                db,
                args.bundle,
                args.repository_root or settings.cancer_repository_dir,
                registry_root,
            )
        elif args.command == "coverage-report":
            sync_repository_catalog(
                db, settings.cancer_repository_registry_dir
            )
            result = coverage_report(db)
            if args.output:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(
                    json.dumps(result, indent=2, sort_keys=True),
                    encoding="utf-8",
                )
        elif args.command == "attest-rank-layer":
            result = attest_legacy_rank_layers(
                db,
                release_id=args.release_id,
                apply=args.apply,
            )
        else:  # pragma: no cover
            raise AssertionError(args.command)
    print(json.dumps(result, indent=2, sort_keys=True))


def coverage_report(db) -> dict:
    from sqlalchemy import select

    from app.models import CancerType, RepositoryDataset

    datasets_by_cancer: dict[str, list[str]] = {}
    for dataset in db.scalars(
        select(RepositoryDataset)
        .where(RepositoryDataset.status == "available")
        .order_by(RepositoryDataset.id)
    ).all():
        datasets_by_cancer.setdefault(dataset.cancer_code, []).append(
            dataset.id
        )
    rows = []
    for cancer in db.scalars(
        select(CancerType).order_by(CancerType.sort_order)
    ).all():
        rows.append(
            {
                "code": cancer.code,
                "tcga_cohort": cancer.tcga_cohort,
                "name": cancer.name,
                "status": (
                    "available"
                    if datasets_by_cancer.get(cancer.code)
                    else cancer.coverage_status
                ),
                "datasets": datasets_by_cancer.get(cancer.code, []),
                "search": cancer.coverage_metadata or {},
            }
        )
    return {
        "schema_version": "tcga-trace-external-coverage-report-v1",
        "total_cancer_types": len(rows),
        "available": sum(row["status"] == "available" for row in rows),
        "evidence_gaps": sum(
            row["status"] == "evidence_gap" for row in rows
        ),
        "search_in_progress": sum(
            row["status"] == "search_in_progress" for row in rows
        ),
        "cancers": rows,
    }


if __name__ == "__main__":
    main()
