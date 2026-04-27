from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.expression import (
    ensure_count_matrix_library_sizes,
    ensure_gdc_expression_matrix_cache,
    list_cache_gene_files,
    load_or_build_cache_file_map,
)
from app.importer import ensure_gene_index
from app.models import Cohort

logger = logging.getLogger(__name__)


class CacheWarmupError(RuntimeError):
    pass


def warm_startup_cache(db: Session, settings: Settings) -> dict[str, Any]:
    started = time.monotonic()
    cohort_ids = list(db.scalars(select(Cohort.id).order_by(Cohort.id)).all())
    manifest: dict[str, Any] = {
        "status": "running",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "tcga_data_dir": str(settings.tcga_data_dir),
        "derived_expression_dir": str(settings.derived_expression_dir),
        "mode": "startup_preload",
        "steps": [
            "gene_index",
            "count_matrix_library_sizes",
            "gdc_barcode_file_maps",
            "gdc_expression_matrices",
        ],
        "cohort_count": len(cohort_ids),
        "cohorts": [],
        "errors": [],
    }
    write_cache_manifest(settings.derived_expression_dir, manifest)

    logger.warning("Starting TCGA cache warmup for %s cohorts.", len(cohort_ids))
    for index, cohort_id in enumerate(cohort_ids, start=1):
        cohort_started = time.monotonic()
        cohort_report: dict[str, Any] = {
            "cohort": cohort_id,
            "status": "running",
            "gene_index_count": None,
            "library_size_count": None,
            "gdc_cache_files": None,
            "gdc_mapped_samples": None,
            "gdc_expression_matrix": None,
            "warnings": [],
            "duration_seconds": None,
        }
        manifest["cohorts"].append(cohort_report)
        logger.warning("Warming cache for %s (%s/%s).", cohort_id, index, len(cohort_ids))
        try:
            cohort_report["gene_index_count"] = ensure_gene_index(db, settings.tcga_data_dir, cohort_id)

            library_sizes = ensure_count_matrix_library_sizes(db, settings.tcga_data_dir, cohort_id)
            cohort_report["library_size_count"] = len(library_sizes)

            cache_files = list_cache_gene_files(settings.tcga_data_dir, cohort_id)
            cohort_report["gdc_cache_files"] = len(cache_files)
            if cache_files:
                mapping = load_or_build_cache_file_map(
                    settings.tcga_data_dir,
                    settings.derived_expression_dir,
                    cohort_id,
                )
                cohort_report["gdc_mapped_samples"] = len(mapping)
                if settings.preload_gdc_expression_matrices_on_startup:
                    cohort_report["gdc_expression_matrix"] = ensure_gdc_expression_matrix_cache(
                        settings.tcga_data_dir,
                        settings.derived_expression_dir,
                        cohort_id,
                    )
            else:
                cohort_report["warnings"].append("No GDC STAR-count cache files were found.")

            cohort_report["status"] = "ready"
        except Exception as exc:  # pragma: no cover - exercised by local data shape
            message = f"{cohort_id}: {exc}"
            logger.exception("Cache warmup failed for %s.", cohort_id)
            cohort_report["status"] = "failed"
            cohort_report["error"] = str(exc)
            manifest["errors"].append(message)
        finally:
            cohort_report["duration_seconds"] = round(time.monotonic() - cohort_started, 3)
            write_cache_manifest(settings.derived_expression_dir, manifest)

    manifest["duration_seconds"] = round(time.monotonic() - started, 3)
    manifest["generated_at"] = datetime.now(timezone.utc).isoformat()
    manifest["status"] = "degraded" if manifest["errors"] else "ready"
    write_cache_manifest(settings.derived_expression_dir, manifest)

    if manifest["errors"] and settings.preload_cache_strict:
        raise CacheWarmupError(
            "Startup cache warmup failed; set PRELOAD_CACHE_STRICT=false to allow degraded startup. "
            + " | ".join(manifest["errors"])
        )

    logger.warning(
        "Finished TCGA cache warmup with status=%s in %.1fs.",
        manifest["status"],
        manifest["duration_seconds"],
    )
    return manifest


def load_cache_manifest(derived_expression_dir: Path) -> dict[str, Any] | None:
    path = cache_manifest_path(derived_expression_dir)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def write_cache_manifest(derived_expression_dir: Path, manifest: dict[str, Any]) -> None:
    path = cache_manifest_path(derived_expression_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")


def cache_manifest_path(derived_expression_dir: Path) -> Path:
    return derived_expression_dir / "startup_cache_manifest.json"


def summarize_cache_manifest(manifest: dict[str, Any] | None) -> dict[str, Any]:
    if manifest is None:
        return {"status": "missing"}
    cohorts = manifest.get("cohorts") or []
    ready = sum(1 for cohort in cohorts if cohort.get("status") == "ready")
    failed = sum(1 for cohort in cohorts if cohort.get("status") == "failed")
    return {
        "status": manifest.get("status", "unknown"),
        "cohorts_ready": ready,
        "cohorts_failed": failed,
        "cohort_count": manifest.get("cohort_count", len(cohorts)),
        "duration_seconds": manifest.get("duration_seconds"),
        "generated_at": manifest.get("generated_at"),
        "errors": manifest.get("errors", []),
    }
