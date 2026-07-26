from __future__ import annotations

from functools import lru_cache
import hashlib
import json
from pathlib import Path, PurePosixPath
from typing import Any

from app.config import Settings


def analysis_data_provenance(
    settings: Settings,
    *,
    cohort: str,
    expression_scale: str,
    selected_barcodes: set[str],
) -> dict[str, Any]:
    expression_files: list[dict[str, Any]] = []
    source_identifiers: list[dict[str, str]] = []

    if expression_scale == "log2_cpm":
        count_matrix = settings.tcga_data_dir / cohort / "count_matrix.tsv"
        expression_files.append(file_record(count_matrix, "TCGA unstranded count matrix"))
        expression_source = "count_matrix.tsv"
    else:
        matrix_dir = settings.derived_expression_dir / "matrices" / cohort
        metadata_path = matrix_dir / "metadata.json"
        metadata = read_json(metadata_path) or {}
        scale_info = (metadata.get("scales") or {}).get(expression_scale) or {}
        matrix_path = matrix_dir / str(scale_info.get("file") or f"{expression_scale}.float32.bin")
        map_path = settings.derived_expression_dir / "maps" / f"{cohort}.json"
        expression_files.extend(
            [
                file_record(matrix_path, f"Derived {expression_scale} expression matrix"),
                file_record(metadata_path, "Derived expression matrix metadata"),
                file_record(map_path, "TCGA barcode to GDC file map"),
            ]
        )
        source_identifiers = selected_gdc_identifiers(map_path, selected_barcodes)
        expression_source = "derived GDC STAR-count matrix cache"

    clinical_files = [
        file_record(settings.tcga_cdr_path, "TCGA Clinical Data Resource"),
    ]
    rna_sync_manifest = settings.tcga_sync_state_dir / "manifests" / "tcga_rna_current.json"
    if rna_sync_manifest.exists():
        expression_files.append(file_record(rna_sync_manifest, "TCGA RNA GDC synchronization manifest"))

    snapshot = publication_snapshot_summary(settings, cohort)
    return {
        "schema_version": "tcga-trace-data-provenance-v1",
        "cohort": cohort,
        "expression_scale": expression_scale,
        "expression_source": expression_source,
        "expression_files": expression_files,
        "clinical_files": clinical_files,
        "selected_gdc_file_identifiers": source_identifiers,
        "selected_gdc_file_count": len(source_identifiers),
        "publication_snapshot": snapshot,
        "provenance_completeness": {
            "exact_expression_artifact_hashed": any(
                item.get("status") == "available" and item.get("sha256")
                for item in expression_files
            ),
            "selected_gdc_identifiers_recorded": (
                expression_scale == "log2_cpm"
                or len(source_identifiers) == len(selected_barcodes)
            ),
            "publication_manifest_available": snapshot.get("status") == "available",
            "rna_sync_manifest_available": rna_sync_manifest.exists(),
        },
    }


def publication_snapshot_summary(settings: Settings, cohort: str | None = None) -> dict[str, Any]:
    path = settings.publication_benchmark_dir / "data_snapshot_manifest.json"
    payload = read_json(path)
    if payload is None:
        return {
            "status": "missing",
            "logical_name": "publication data snapshot manifest",
        }

    summary: dict[str, Any] = {
        "status": "available",
        "schema_version": payload.get("schema_version"),
        "manifest_hash": payload.get("manifest_hash"),
        "file": file_record(path, "Publication data snapshot manifest"),
    }
    if cohort:
        rows = ((payload.get("rna_snapshot") or {}).get("cohorts") or [])
        cohort_record = next((item for item in rows if item.get("cohort") == cohort), None)
        if cohort_record:
            summary["cohort"] = {
                "cohort": cohort,
                "count_matrix": compact_file_record(cohort_record.get("count_matrix")),
                "col_data": compact_file_record(cohort_record.get("col_data")),
                "clinical_data": compact_file_record(cohort_record.get("clinical_data")),
            }
    return summary


def selected_gdc_identifiers(map_path: Path, selected_barcodes: set[str]) -> list[dict[str, str]]:
    payload = read_json(map_path) or {}
    barcode_to_file = payload.get("barcode_to_file") or {}
    rows: list[dict[str, str]] = []
    for barcode in sorted(selected_barcodes):
        raw_path = barcode_to_file.get(barcode)
        if not raw_path:
            continue
        source_path = PurePosixPath(str(raw_path))
        rows.append(
            {
                "sample_barcode": barcode,
                "gdc_case_file_uuid": source_path.parent.name,
                "gdc_file_uuid": source_path.name.split(".", 1)[0],
                "gdc_filename": source_path.name,
            }
        )
    return rows


def file_record(path: Path, logical_name: str) -> dict[str, Any]:
    if not path.exists() or not path.is_file():
        return {
            "logical_name": logical_name,
            "filename": path.name,
            "status": "missing",
        }
    stat = path.stat()
    return {
        "logical_name": logical_name,
        "filename": path.name,
        "status": "available",
        "bytes": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
        "sha256": cached_file_sha256(str(path.resolve()), stat.st_size, stat.st_mtime_ns),
    }


def compact_file_record(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    return {
        key: value.get(key)
        for key in ("path", "bytes", "sha256", "sha256_status", "status")
    }


def read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists() or not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


@lru_cache(maxsize=256)
def cached_file_sha256(path_value: str, _size: int, _mtime_ns: int) -> str:
    digest = hashlib.sha256()
    with Path(path_value).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
