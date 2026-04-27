from __future__ import annotations

import csv
import hashlib
import json
import os
import shutil
import time
import urllib.error
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import desc, select

from app.config import Settings, get_settings
from app.database import SessionLocal, init_db
from app.importer import import_cohorts_and_samples, import_tcga_cdr, register_tcga_rna_source
from app.models import DataManifest, DataSource, DataSyncRun

TCGA_COHORTS = [
    "TCGA-ACC",
    "TCGA-BLCA",
    "TCGA-BRCA",
    "TCGA-CESC",
    "TCGA-CHOL",
    "TCGA-COAD",
    "TCGA-DLBC",
    "TCGA-ESCA",
    "TCGA-GBM",
    "TCGA-HNSC",
    "TCGA-KICH",
    "TCGA-KIRC",
    "TCGA-KIRP",
    "TCGA-LAML",
    "TCGA-LGG",
    "TCGA-LIHC",
    "TCGA-LUAD",
    "TCGA-LUSC",
    "TCGA-MESO",
    "TCGA-OV",
    "TCGA-PAAD",
    "TCGA-PCPG",
    "TCGA-PRAD",
    "TCGA-READ",
    "TCGA-SARC",
    "TCGA-SKCM",
    "TCGA-STAD",
    "TCGA-TGCT",
    "TCGA-THCA",
    "TCGA-THYM",
    "TCGA-UCEC",
    "TCGA-UCS",
    "TCGA-UVM",
]

TCGA_CDR_FILE_ID = "1b5f413e-a8d1-4d10-92eb-7c4ae739ed81"
TCGA_CDR_URL = f"https://api.gdc.cancer.gov/data/{TCGA_CDR_FILE_ID}"
TCGA_CDR_MANIFEST_URL = "https://gdc.cancer.gov/system/files/public/file/PanCan-Clinical_Open_GDC-Manifest_1.txt"
STAR_REQUIRED_COLUMNS = {
    "gene_name",
    "unstranded",
    "tpm_unstranded",
    "fpkm_unstranded",
    "fpkm_uq_unstranded",
}
CDR_REQUIRED_COLUMNS = {"OS", "OS.time", "PFI", "PFI.time", "DFI", "DFI.time", "DSS", "DSS.time"}


class SyncError(RuntimeError):
    pass


@dataclass
class SyncResult:
    source: str
    status: str
    changed: bool
    manifest_hash: str | None = None
    data_through_date: str | None = None
    file_count: int | None = None
    changes: dict[str, Any] | None = None
    manifest_path: str | None = None
    errors: list[str] | None = None


def run_sync(source: str = "all", apply: bool = False, max_workers: int = 10) -> dict[str, Any]:
    settings = get_settings()
    selected = ["tcga_rna", "tcga_cdr"] if source == "all" else [source]
    results: list[SyncResult] = []
    for item in selected:
        if item == "tcga_rna":
            results.append(sync_tcga_rna(settings, apply=apply, max_workers=max_workers))
        elif item == "tcga_cdr":
            results.append(sync_tcga_cdr(settings, apply=apply))
        else:
            raise SyncError(f"Unsupported sync source: {item}")
    return {
        "status": "updated" if any(result.changed for result in results) else "unchanged",
        "apply": apply,
        "results": [result.__dict__ for result in results],
    }


def sync_tcga_rna(settings: Settings, apply: bool, max_workers: int = 10) -> SyncResult:
    state_dir = settings.tcga_sync_state_dir
    with sync_lock(state_dir / "tcga_rna.lock"):
        run_id = new_run_id("tcga-rna")
        run = start_sync_run(run_id, "tcga_rna", {"apply": apply, "max_workers": max_workers})
        try:
            remote = build_remote_tcga_manifest(settings)
            local = read_current_manifest(state_dir, "tcga_rna") or build_local_tcga_manifest(settings.tcga_data_dir)
            diff = diff_manifests(remote["files"], local.get("files", []))
            changed = bool(diff["added"] or diff["changed"])
            if not apply:
                finish_sync_run(run_id, "checked", diff)
                return SyncResult(
                    source="tcga_rna",
                    status="changes_available" if changed else "unchanged",
                    changed=changed,
                    manifest_hash=remote["manifest_hash"],
                    data_through_date=remote.get("data_through_date"),
                    file_count=len(remote["files"]),
                    changes=diff_summary(diff),
                )
            if not changed:
                manifest_path = write_current_manifest(state_dir, "tcga_rna", remote)
                record_manifest("tcga_rna", remote, manifest_path, "ready")
                refresh_tcga_rna_source(settings, remote, manifest_path)
                finish_sync_run(run_id, "unchanged", diff)
                return SyncResult(
                    source="tcga_rna",
                    status="unchanged",
                    changed=False,
                    manifest_hash=remote["manifest_hash"],
                    data_through_date=remote.get("data_through_date"),
                    file_count=len(remote["files"]),
                    changes=diff_summary(diff),
                    manifest_path=str(manifest_path),
                )

            staging_dir = state_dir / "staging" / run_id
            backup_dir = state_dir / "backups" / run_id
            staging_dir.mkdir(parents=True, exist_ok=True)
            backup_dir.mkdir(parents=True, exist_ok=True)
            downloaded = download_changed_tcga_files(settings, diff, staging_dir, max_workers=max_workers)
            affected = promote_tcga_files(settings, downloaded, backup_dir)
            materialize_affected_cohorts(settings.tcga_data_dir, affected, remote["files"])
            invalidate_derived_caches(settings.derived_expression_dir, affected)
            manifest_path = write_current_manifest(state_dir, "tcga_rna", remote)
            record_manifest("tcga_rna", remote, manifest_path, "ready")
            refresh_tcga_rna_source(settings, remote, manifest_path)
            finish_sync_run(run_id, "updated", {**diff, "affected_cohorts": sorted(affected)})
            return SyncResult(
                source="tcga_rna",
                status="updated",
                changed=True,
                manifest_hash=remote["manifest_hash"],
                data_through_date=remote.get("data_through_date"),
                file_count=len(remote["files"]),
                changes={**diff_summary(diff), "affected_cohorts": sorted(affected)},
                manifest_path=str(manifest_path),
            )
        except Exception as exc:
            finish_sync_run(run_id, "failed", {}, str(exc))
            raise


def sync_tcga_cdr(settings: Settings, apply: bool) -> SyncResult:
    state_dir = settings.clinical_sync_state_dir
    with sync_lock(state_dir / "tcga_cdr.lock"):
        run_id = new_run_id("tcga-cdr")
        run = start_sync_run(run_id, "tcga_cdr", {"apply": apply})
        try:
            remote_file = gdc_file_metadata(settings, TCGA_CDR_FILE_ID)
            local_hash = sha256_file(settings.tcga_cdr_path) if settings.tcga_cdr_path.exists() else None
            remote_md5 = remote_file.get("md5sum")
            local_md5_value = local_md5(settings.tcga_cdr_path)
            changed = local_hash is None or bool(remote_md5 and remote_md5 != local_md5_value)
            manifest = cdr_manifest(remote_file, local_hash)
            if not apply:
                finish_sync_run(run_id, "checked", {"changed": changed})
                return SyncResult(
                    source="tcga_cdr",
                    status="changes_available" if changed else "unchanged",
                    changed=changed,
                    manifest_hash=manifest["manifest_hash"],
                    data_through_date=manifest.get("data_through_date"),
                    file_count=1,
                    changes={"changed": changed},
                )
            if changed:
                staging_dir = state_dir / "staging" / run_id
                backup_dir = state_dir / "backups" / run_id
                staging_dir.mkdir(parents=True, exist_ok=True)
                backup_dir.mkdir(parents=True, exist_ok=True)
                staged_path = staging_dir / "TCGA-CDR-SupplementalTableS1.xlsx"
                gdc_download_file(settings, TCGA_CDR_FILE_ID, staged_path)
                validate_downloaded_file(staged_path, remote_file.get("md5sum"), int(remote_file.get("file_size") or 0))
                validate_tcga_cdr_file(staged_path)
                if settings.tcga_cdr_path.exists():
                    backup_file(settings.tcga_cdr_path, backup_dir)
                atomic_replace(staged_path, settings.tcga_cdr_path)
                manifest = cdr_manifest(remote_file, sha256_file(settings.tcga_cdr_path))
            manifest_path = write_current_manifest(state_dir, "tcga_cdr", manifest)
            record_manifest("tcga_cdr", manifest, manifest_path, "ready")
            import_cdr_if_database_ready(settings)
            finish_sync_run(run_id, "updated" if changed else "unchanged", {"changed": changed})
            return SyncResult(
                source="tcga_cdr",
                status="updated" if changed else "unchanged",
                changed=changed,
                manifest_hash=manifest["manifest_hash"],
                data_through_date=manifest.get("data_through_date"),
                file_count=1,
                changes={"changed": changed},
                manifest_path=str(manifest_path),
            )
        except Exception as exc:
            finish_sync_run(run_id, "failed", {}, str(exc))
            raise


def build_remote_tcga_manifest(settings: Settings) -> dict[str, Any]:
    files: list[dict[str, Any]] = []
    for cohort in TCGA_COHORTS:
        files.extend(fetch_tcga_star_count_files(settings, cohort))
    data_through = max((item.get("updated_datetime") for item in files if item.get("updated_datetime")), default=None)
    data_release = latest_release(files)
    manifest = {
        "source": "tcga_rna",
        "generated_at": now_iso(),
        "data_through_date": data_through,
        "data_release": data_release,
        "files": sorted(files, key=lambda item: (item.get("cohort") or "", item.get("file_id") or "")),
    }
    manifest["manifest_hash"] = stable_manifest_hash(manifest["files"])
    return manifest


def fetch_tcga_star_count_files(settings: Settings, cohort: str) -> list[dict[str, Any]]:
    filters = {
        "op": "and",
        "content": [
            {"op": "=", "content": {"field": "cases.project.project_id", "value": [cohort]}},
            {"op": "=", "content": {"field": "data_category", "value": ["Transcriptome Profiling"]}},
            {"op": "=", "content": {"field": "data_type", "value": ["Gene Expression Quantification"]}},
            {"op": "=", "content": {"field": "analysis.workflow_type", "value": ["STAR - Counts"]}},
            {"op": "=", "content": {"field": "access", "value": ["open"]}},
            {"op": "=", "content": {"field": "state", "value": ["released"]}},
        ],
    }
    fields = ",".join(
        [
            "file_id",
            "file_name",
            "md5sum",
            "file_size",
            "updated_datetime",
            "created_datetime",
            "data_release",
            "state",
            "associated_entities.entity_submitter_id",
            "associated_entities.entity_type",
            "cases.submitter_id",
            "cases.project.project_id",
            "cases.samples.submitter_id",
            "cases.samples.sample_type",
            "cases.samples.sample_type_id",
            "cases.samples.tissue_type",
            "cases.samples.portions.submitter_id",
            "cases.samples.portions.analytes.submitter_id",
            "cases.samples.portions.analytes.aliquots.submitter_id",
            "cases.demographic.gender",
            "cases.demographic.race",
            "cases.demographic.vital_status",
            "cases.demographic.days_to_death",
            "cases.demographic.age_at_index",
            "cases.diagnoses.ajcc_pathologic_stage",
            "cases.diagnoses.age_at_diagnosis",
            "cases.diagnoses.primary_diagnosis",
            "cases.diagnoses.days_to_last_follow_up",
            "cases.follow_ups.days_to_follow_up",
            "cases.follow_ups.disease_response",
        ]
    )
    hits = gdc_paginated_post(settings, "/files", {"filters": filters, "fields": fields, "format": "JSON"})
    return [normalize_tcga_file_hit(hit, cohort) for hit in hits]


def normalize_tcga_file_hit(hit: dict[str, Any], cohort: str) -> dict[str, Any]:
    file_id = hit.get("file_id") or hit.get("id")
    file_name = hit.get("file_name") or f"{file_id}.rna_seq.augmented_star_gene_counts.tsv"
    case = first(hit.get("cases"))
    sample = first(case.get("samples") if isinstance(case, dict) else None)
    barcode = best_barcode(hit, sample)
    patient_id = clean_value(case.get("submitter_id") if isinstance(case, dict) else None) or (barcode[:12] if barcode else None)
    sample_type = clean_value(sample.get("sample_type") if isinstance(sample, dict) else None)
    return {
        "file_id": file_id,
        "file_name": file_name,
        "md5sum": hit.get("md5sum"),
        "file_size": int(hit.get("file_size") or 0),
        "updated_datetime": hit.get("updated_datetime"),
        "created_datetime": hit.get("created_datetime"),
        "data_release": hit.get("data_release"),
        "state": hit.get("state"),
        "cohort": cohort,
        "barcode": barcode,
        "patient_id": patient_id,
        "sample_type": sample_type,
        "relative_path": tcga_cache_relative_path(cohort, file_id, file_name),
        "metadata": minimal_clinical_metadata(hit, case, sample),
    }


def build_local_tcga_manifest(tcga_data_dir: Path) -> dict[str, Any]:
    files: list[dict[str, Any]] = []
    for path in sorted((tcga_data_dir / "gdc_cache").glob("TCGA-*/*/*/*/*.rna_seq.augmented_star_gene_counts.tsv")):
        cohort = path.relative_to(tcga_data_dir / "gdc_cache").parts[0]
        stat = path.stat()
        files.append(
            {
                "file_id": path.parent.name,
                "file_name": path.name,
                "md5sum": md5_file(path),
                "file_size": stat.st_size,
                "updated_datetime": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
                "data_release": None,
                "state": "local",
                "cohort": cohort,
                "barcode": None,
                "patient_id": None,
                "sample_type": None,
                "relative_path": str(path.relative_to(tcga_data_dir)),
                "metadata": {},
            }
        )
    manifest = {
        "source": "tcga_rna",
        "generated_at": now_iso(),
        "data_through_date": max((item["updated_datetime"] for item in files), default=None),
        "data_release": None,
        "files": files,
    }
    manifest["manifest_hash"] = stable_manifest_hash(files)
    return manifest


def diff_manifests(remote_files: list[dict[str, Any]], local_files: list[dict[str, Any]]) -> dict[str, Any]:
    remote_by_key = {manifest_key(item): item for item in remote_files}
    local_by_key = {manifest_key(item): item for item in local_files}
    added = [remote_by_key[key] for key in sorted(remote_by_key.keys() - local_by_key.keys())]
    stale = [local_by_key[key] for key in sorted(local_by_key.keys() - remote_by_key.keys())]
    changed: list[dict[str, Any]] = []
    for key in sorted(remote_by_key.keys() & local_by_key.keys()):
        remote = remote_by_key[key]
        local = local_by_key[key]
        if remote.get("md5sum") and local.get("md5sum") and remote.get("md5sum") != local.get("md5sum"):
            changed.append({"remote": remote, "local": local})
        elif int(remote.get("file_size") or 0) and int(local.get("file_size") or 0) and int(remote["file_size"]) != int(local["file_size"]):
            changed.append({"remote": remote, "local": local})
    return {"added": added, "changed": changed, "stale": stale}


def download_changed_tcga_files(settings: Settings, diff: dict[str, Any], staging_dir: Path, max_workers: int) -> list[dict[str, Any]]:
    tasks: list[tuple[dict[str, Any], str, dict[str, Any] | None]] = [
        (item, "added", None)
        for item in diff.get("added", [])
    ] + [
        (item["remote"], "changed", item.get("local"))
        for item in diff.get("changed", [])
    ]
    if not tasks:
        return []
    worker_count = max(1, min(int(max_workers or 1), 10, len(tasks)))
    downloads: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = [
            executor.submit(download_one_tcga_file, settings, file_item, staging_dir, action, local_item)
            for file_item, action, local_item in tasks
        ]
        for future in as_completed(futures):
            downloads.append(future.result())
    return downloads


def download_one_tcga_file(
    settings: Settings,
    file_item: dict[str, Any],
    staging_dir: Path,
    action: str,
    local_item: dict[str, Any] | None = None,
) -> dict[str, Any]:
    staged_path = staging_dir / file_item["relative_path"]
    staged_path.parent.mkdir(parents=True, exist_ok=True)
    gdc_download_file(settings, file_item["file_id"], staged_path)
    validate_downloaded_file(staged_path, file_item.get("md5sum"), int(file_item.get("file_size") or 0))
    validate_star_count_file(staged_path)
    return {"action": action, "remote": file_item, "local": local_item, "staged_path": str(staged_path)}


def promote_tcga_files(settings: Settings, downloads: list[dict[str, Any]], backup_dir: Path) -> set[str]:
    affected: set[str] = set()
    for item in downloads:
        remote = item["remote"]
        final_path = settings.tcga_data_dir / remote["relative_path"]
        staged_path = Path(item["staged_path"])
        if final_path.exists():
            backup_file(final_path, backup_dir)
        final_path.parent.mkdir(parents=True, exist_ok=True)
        atomic_replace(staged_path, final_path)
        affected.add(remote["cohort"])
    return affected


def materialize_affected_cohorts(tcga_data_dir: Path, affected_cohorts: set[str], files: list[dict[str, Any]]) -> None:
    by_cohort: dict[str, list[dict[str, Any]]] = {}
    for item in files:
        if item.get("cohort") in affected_cohorts and item.get("barcode"):
            by_cohort.setdefault(item["cohort"], []).append(item)
    for cohort, items in by_cohort.items():
        values_by_barcode: dict[str, dict[str, str]] = {}
        metadata_by_barcode: dict[str, dict[str, Any]] = {}
        for item in items:
            path = tcga_data_dir / item["relative_path"]
            if not path.exists():
                continue
            barcode = item.get("barcode")
            if not barcode:
                continue
            values_by_barcode[barcode] = read_star_unstranded_counts(path)
            metadata_by_barcode[barcode] = item
        if values_by_barcode:
            update_count_matrix_columns(tcga_data_dir / cohort / "count_matrix.tsv", values_by_barcode)
            upsert_col_data_rows(tcga_data_dir / cohort / "col_data.tsv", metadata_by_barcode)
    if affected_cohorts:
        rebuild_summary_table(tcga_data_dir)


def update_count_matrix_columns(matrix_path: Path, values_by_barcode: dict[str, dict[str, str]]) -> None:
    if not matrix_path.exists():
        return
    tmp_path = matrix_path.with_suffix(".tsv.tmp")
    with matrix_path.open(newline="", encoding="utf-8", errors="replace") as source, tmp_path.open(
        "w", newline="", encoding="utf-8"
    ) as target:
        reader = csv.reader(source, delimiter="\t")
        writer = csv.writer(target, delimiter="\t", lineterminator="\n")
        header = next(reader)
        first_header = header[0] if header else ""
        existing_barcodes = header[1:]
        appended = [barcode for barcode in values_by_barcode if barcode not in existing_barcodes]
        output_barcodes = existing_barcodes + appended
        writer.writerow([first_header] + output_barcodes)
        index_by_barcode = {barcode: index + 1 for index, barcode in enumerate(existing_barcodes)}
        for row in reader:
            if not row:
                continue
            gene = row[0].strip().upper()
            out = list(row)
            if len(out) < len(existing_barcodes) + 1:
                out.extend(["0"] * (len(existing_barcodes) + 1 - len(out)))
            for barcode, values in values_by_barcode.items():
                if barcode in index_by_barcode:
                    if gene in values:
                        out[index_by_barcode[barcode]] = values[gene]
                else:
                    out.append(values.get(gene, "0"))
            writer.writerow(out[: len(output_barcodes) + 1])
    tmp_path.replace(matrix_path)


def upsert_col_data_rows(path: Path, metadata_by_barcode: dict[str, dict[str, Any]]) -> None:
    if not path.exists():
        return
    rows: dict[str, dict[str, str]] = {}
    with path.open(newline="", encoding="utf-8", errors="replace") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        fieldnames = list(reader.fieldnames or [])
        for row in reader:
            barcode = clean_value(row.get("")) or clean_value(row.get("barcode"))
            if barcode:
                rows[barcode] = row
    for barcode, item in metadata_by_barcode.items():
        row = rows.get(barcode, {})
        values = col_data_row_from_manifest(item)
        for key in values:
            if key not in fieldnames:
                fieldnames.append(key)
        rows[barcode] = {**row, **values}
    tmp_path = path.with_suffix(".tsv.tmp")
    with tmp_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        for barcode in sorted(rows):
            writer.writerow({name: rows[barcode].get(name, "") for name in fieldnames})
    tmp_path.replace(path)


def col_data_row_from_manifest(item: dict[str, Any]) -> dict[str, str]:
    metadata = item.get("metadata") or {}
    barcode = item.get("barcode") or ""
    patient_id = item.get("patient_id") or barcode[:12]
    sample = barcode[:16] if len(barcode) >= 16 else barcode
    return {
        "": barcode,
        "patient_id": patient_id,
        "barcode": barcode,
        "patient": patient_id,
        "sample": sample,
        "sample_submitter_id": sample,
        "sample_type": item.get("sample_type") or metadata.get("sample_type") or "",
        "definition": item.get("sample_type") or metadata.get("sample_type") or "",
        "project_id": item.get("cohort") or "",
        "gender": clean_value(metadata.get("gender")) or "",
        "race": clean_value(metadata.get("race")) or "",
        "vital_status": clean_value(metadata.get("vital_status")) or "",
        "age_at_index": str(clean_value(metadata.get("age_at_index")) or ""),
        "days_to_death": str(clean_value(metadata.get("days_to_death")) or ""),
        "days_to_last_follow_up": str(clean_value(metadata.get("days_to_last_follow_up")) or ""),
        "ajcc_pathologic_stage": clean_value(metadata.get("ajcc_pathologic_stage")) or "",
        "primary_diagnosis": clean_value(metadata.get("primary_diagnosis")) or "",
        "updated_datetime": clean_value(item.get("updated_datetime")) or "",
    }


def rebuild_summary_table(tcga_data_dir: Path) -> None:
    rows = []
    for cohort_dir in sorted(path for path in tcga_data_dir.glob("TCGA-*") if path.is_dir()):
        cohort = cohort_dir.name
        col_path = cohort_dir / "col_data.tsv"
        matrix_path = cohort_dir / "count_matrix.tsv"
        if not col_path.exists() or not matrix_path.exists():
            continue
        sample_rows = read_tsv_rows(col_path)
        barcodes = [clean_value(row.get("")) or clean_value(row.get("barcode")) for row in sample_rows]
        patients = {barcode[:12] for barcode in barcodes if barcode}
        sample_types = [clean_value(row.get("sample_type")) for row in sample_rows]
        genes = count_lines(matrix_path) - 1
        rows.append(
            {
                "cohort": cohort,
                "disease_type": first_nonempty(row.get("disease_type") for row in sample_rows),
                "primary_site": first_nonempty(row.get("primary_site") for row in sample_rows),
                "n_samples_downloaded": "",
                "n_samples_paired": len([barcode for barcode in barcodes if barcode]),
                "n_patients_paired": len(patients),
                "n_primary_tumor": sum(1 for value in sample_types if value == "Primary Tumor"),
                "n_solid_normal": sum(1 for value in sample_types if value == "Solid Tissue Normal"),
                "n_other_samples": sum(1 for value in sample_types if value not in {"Primary Tumor", "Solid Tissue Normal", None}),
                "n_genes": max(genes, 0),
                "design_formula": "~sample_type" if len(set(value for value in sample_types if value)) > 1 else "~1",
                "status": "success",
                "notes": "updated by incremental sync",
            }
        )
    if not rows:
        return
    path = tcga_data_dir / "summary_table.tsv"
    tmp_path = path.with_suffix(".tsv.tmp")
    fieldnames = [
        "cohort",
        "disease_type",
        "primary_site",
        "n_samples_downloaded",
        "n_samples_paired",
        "n_patients_paired",
        "n_primary_tumor",
        "n_solid_normal",
        "n_other_samples",
        "n_genes",
        "design_formula",
        "status",
        "notes",
    ]
    with tmp_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    tmp_path.replace(path)


def invalidate_derived_caches(derived_expression_dir: Path, affected_cohorts: set[str]) -> None:
    if not affected_cohorts:
        return
    for cohort in affected_cohorts:
        for path in [
            derived_expression_dir / "maps" / f"{cohort}.json",
            derived_expression_dir / "matrices" / cohort,
            derived_expression_dir / "gene_cache" / cohort,
        ]:
            if path.is_dir():
                shutil.rmtree(path)
            elif path.exists():
                path.unlink()
    manifest = derived_expression_dir / "startup_cache_manifest.json"
    if manifest.exists():
        manifest.unlink()


def gdc_file_metadata(settings: Settings, file_id: str) -> dict[str, Any]:
    if file_id == TCGA_CDR_FILE_ID:
        return tcga_cdr_manifest_metadata()
    payload = gdc_get_json(settings, f"/files/{file_id}?pretty=false")
    data = payload.get("data") or {}
    if not data:
        raise SyncError(f"GDC file metadata not found for {file_id}")
    return data


def tcga_cdr_manifest_metadata() -> dict[str, Any]:
    request = urllib.request.Request(TCGA_CDR_MANIFEST_URL, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            text = response.read().decode("utf-8")
    except urllib.error.URLError as exc:
        raise SyncError(f"TCGA-CDR manifest request failed: {exc}") from exc
    rows = text.strip().splitlines()
    if len(rows) < 2:
        raise SyncError("TCGA-CDR manifest did not contain a data row.")
    header = rows[0].split()
    values = rows[1].split()
    payload = dict(zip(header, values, strict=False))
    if payload.get("id") != TCGA_CDR_FILE_ID:
        raise SyncError("TCGA-CDR manifest file id does not match the configured file id.")
    return {
        "file_id": payload.get("id"),
        "file_name": payload.get("filename"),
        "md5sum": payload.get("md5"),
        "file_size": int(payload.get("size") or 0),
        "updated_datetime": None,
        "data_release": None,
        "source_url": TCGA_CDR_MANIFEST_URL,
    }


def cdr_manifest(remote_file: dict[str, Any], local_hash: str | None) -> dict[str, Any]:
    file_item = {
        "file_id": TCGA_CDR_FILE_ID,
        "file_name": remote_file.get("file_name") or "TCGA-CDR-SupplementalTableS1.xlsx",
        "md5sum": remote_file.get("md5sum"),
        "sha256": local_hash,
        "file_size": remote_file.get("file_size"),
        "updated_datetime": remote_file.get("updated_datetime"),
        "data_release": remote_file.get("data_release"),
        "source_url": TCGA_CDR_URL,
    }
    manifest = {
        "source": "tcga_cdr",
        "generated_at": now_iso(),
        "data_through_date": remote_file.get("updated_datetime"),
        "data_release": remote_file.get("data_release"),
        "files": [file_item],
    }
    manifest["manifest_hash"] = stable_manifest_hash(manifest["files"])
    return manifest


def validate_tcga_cdr_file(path: Path) -> None:
    from app.importer import read_tcga_cdr_rows

    rows = read_tcga_cdr_rows(path)
    if not rows:
        raise SyncError("Downloaded TCGA-CDR file is empty.")
    headers = set(rows[0].keys())
    missing = sorted(CDR_REQUIRED_COLUMNS - headers)
    if missing:
        raise SyncError(f"Downloaded TCGA-CDR file is missing required columns: {', '.join(missing)}")


def refresh_tcga_rna_source(settings: Settings, manifest: dict[str, Any], manifest_path: Path) -> None:
    try:
        init_db()
        with SessionLocal() as db:
            register_tcga_rna_source(db, settings.tcga_data_dir)
            source = db.get(DataSource, "tcga_rna")
            if source:
                source.metadata_json = {
                    **(source.metadata_json or {}),
                    "manifest_hash": manifest.get("manifest_hash"),
                    "data_release": manifest.get("data_release"),
                    "data_through_date": manifest.get("data_through_date"),
                    "manifest_path": str(manifest_path),
                }
                db.commit()
    except Exception:
        # CLI sync can still be useful without a reachable database; the next backend
        # startup imports the new files and records source metadata.
        return


def import_cdr_if_database_ready(settings: Settings) -> None:
    try:
        init_db()
        with SessionLocal() as db:
            import_tcga_cdr(db, settings.tcga_cdr_path, force=True)
    except Exception:
        return


def record_manifest(source_id: str, manifest: dict[str, Any], manifest_path: Path, status: str) -> None:
    try:
        init_db()
        with SessionLocal() as db:
            db.add(
                DataManifest(
                    source_id=source_id,
                    status=status,
                    manifest_hash=manifest["manifest_hash"],
                    data_release=manifest.get("data_release"),
                    data_through_date=parse_datetime(manifest.get("data_through_date")),
                    file_count=len(manifest.get("files") or []),
                    manifest_path=str(manifest_path),
                    metadata_json={
                        "generated_at": manifest.get("generated_at"),
                        "source": manifest.get("source"),
                    },
                )
            )
            db.commit()
    except Exception:
        return


def start_sync_run(run_id: str, source: str, metadata: dict[str, Any]) -> DataSyncRun:
    run = DataSyncRun(id=run_id, source=source, status="running", metadata_json=metadata)
    try:
        init_db()
        with SessionLocal() as db:
            db.add(run)
            db.commit()
    except Exception:
        pass
    return run


def finish_sync_run(run_id: str, status: str, changes: dict[str, Any], error: str | None = None) -> None:
    try:
        init_db()
        with SessionLocal() as db:
            run = db.get(DataSyncRun, run_id)
            if run is None:
                return
            run.status = status
            run.finished_at = datetime.utcnow()
            run.changes_json = json_slim(changes)
            run.error = error
            db.commit()
    except Exception:
        return


def current_sync_status() -> dict[str, Any]:
    init_db()
    with SessionLocal() as db:
        manifests = list(db.scalars(select(DataManifest).order_by(desc(DataManifest.created_at))).all())
        runs = list(db.scalars(select(DataSyncRun).order_by(desc(DataSyncRun.started_at)).limit(10)).all())
        latest_by_source: dict[str, DataManifest] = {}
        for manifest in manifests:
            latest_by_source.setdefault(manifest.source_id, manifest)
        return {
            "sources": [
                {
                    "source": source,
                    "status": manifest.status,
                    "manifest_hash": manifest.manifest_hash,
                    "data_release": manifest.data_release,
                    "data_through_date": iso_datetime(manifest.data_through_date),
                    "file_count": manifest.file_count,
                    "manifest_path": manifest.manifest_path,
                    "created_at": iso_datetime(manifest.created_at),
                }
                for source, manifest in sorted(latest_by_source.items())
            ],
            "recent_runs": [
                {
                    "id": run.id,
                    "source": run.source,
                    "status": run.status,
                    "started_at": iso_datetime(run.started_at),
                    "finished_at": iso_datetime(run.finished_at),
                    "changes": run.changes_json or {},
                    "error": run.error,
                }
                for run in runs
            ],
        }


def gdc_paginated_post(settings: Settings, endpoint: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    offset = 0
    size = 1000
    while True:
        page_payload = {**payload, "from": offset, "size": size}
        data = gdc_post_json(settings, endpoint, page_payload).get("data") or {}
        page_hits = data.get("hits") or []
        hits.extend(page_hits)
        total = int((data.get("pagination") or {}).get("total") or len(hits))
        if len(hits) >= total or not page_hits:
            return hits
        offset += size


def gdc_post_json(settings: Settings, endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
    url = f"{settings.gdc_api_base_url.rstrip('/')}{endpoint}"
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    return urlopen_json(request)


def gdc_get_json(settings: Settings, endpoint: str) -> dict[str, Any]:
    url = f"{settings.gdc_api_base_url.rstrip('/')}{endpoint}"
    return urlopen_json(urllib.request.Request(url, method="GET"))


def gdc_download_file(settings: Settings, file_id: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    url = f"{settings.gdc_api_base_url.rstrip('/')}/data/{file_id}"
    request = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(request, timeout=900) as response, destination.open("wb") as handle:
        shutil.copyfileobj(response, handle)


def urlopen_json(request: urllib.request.Request) -> dict[str, Any]:
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise SyncError(f"GDC request failed ({exc.code}): {body[:500]}") from exc
    except urllib.error.URLError as exc:
        raise SyncError(f"GDC request failed: {exc}") from exc


def validate_downloaded_file(path: Path, expected_md5: str | None, expected_size: int | None) -> None:
    if not path.exists():
        raise SyncError(f"Downloaded file does not exist: {path}")
    if expected_size and path.stat().st_size != expected_size:
        raise SyncError(f"Downloaded file size mismatch for {path.name}")
    if expected_md5 and md5_file(path) != expected_md5:
        raise SyncError(f"Downloaded file md5 mismatch for {path.name}")


def validate_star_count_file(path: Path) -> None:
    with path.open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if line.startswith("#"):
                continue
            columns = set(line.rstrip("\n").split("\t"))
            missing = sorted(STAR_REQUIRED_COLUMNS - columns)
            if missing:
                raise SyncError(f"STAR-count file {path.name} is missing columns: {', '.join(missing)}")
            return
    raise SyncError(f"STAR-count file {path.name} has no header.")


def read_star_unstranded_counts(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    with path.open(newline="", encoding="utf-8", errors="replace") as handle:
        reader = csv.DictReader(skip_comment_lines(handle), delimiter="\t")
        for row in reader:
            symbol = clean_value(row.get("gene_name"))
            if not symbol:
                continue
            key = symbol.upper()
            if key not in values:
                values[key] = str(int(float(row.get("unstranded") or 0)))
    return values


def skip_comment_lines(handle):
    for line in handle:
        if line.startswith("#"):
            continue
        yield line


def best_barcode(hit: dict[str, Any], sample: dict[str, Any] | None) -> str | None:
    for entity in hit.get("associated_entities") or []:
        value = clean_value(entity.get("entity_submitter_id"))
        if value and value.startswith("TCGA-"):
            return value
    for value in nested_values(sample or {}, "submitter_id"):
        text = clean_value(value)
        if text and text.startswith("TCGA-") and len(text) >= 16:
            return text
    return clean_value((sample or {}).get("submitter_id"))


def minimal_clinical_metadata(hit: dict[str, Any], case: dict[str, Any] | None, sample: dict[str, Any] | None) -> dict[str, Any]:
    demographic = (case or {}).get("demographic") or {}
    diagnosis = first((case or {}).get("diagnoses")) or {}
    follow_up = latest_follow_up((case or {}).get("follow_ups") or [])
    return {
        "sample_type": (sample or {}).get("sample_type"),
        "sample_type_id": (sample or {}).get("sample_type_id"),
        "tissue_type": (sample or {}).get("tissue_type"),
        "gender": demographic.get("gender"),
        "race": demographic.get("race"),
        "vital_status": demographic.get("vital_status"),
        "days_to_death": demographic.get("days_to_death"),
        "age_at_index": demographic.get("age_at_index"),
        "ajcc_pathologic_stage": diagnosis.get("ajcc_pathologic_stage"),
        "age_at_diagnosis": diagnosis.get("age_at_diagnosis"),
        "primary_diagnosis": diagnosis.get("primary_diagnosis"),
        "days_to_last_follow_up": follow_up.get("days_to_follow_up") or diagnosis.get("days_to_last_follow_up"),
        "disease_response": follow_up.get("disease_response"),
    }


def latest_follow_up(rows: list[dict[str, Any]]) -> dict[str, Any]:
    valid = [row for row in rows if isinstance(row, dict)]
    if not valid:
        return {}
    return max(valid, key=lambda row: float(row.get("days_to_follow_up") or -1))


def nested_values(value: Any, key: str) -> list[Any]:
    found: list[Any] = []
    if isinstance(value, dict):
        for item_key, item_value in value.items():
            if item_key == key:
                found.append(item_value)
            found.extend(nested_values(item_value, key))
    elif isinstance(value, list):
        for item in value:
            found.extend(nested_values(item, key))
    return found


def manifest_key(item: dict[str, Any]) -> str:
    return str(item.get("file_id") or item.get("file_name") or item.get("relative_path"))


def stable_manifest_hash(files: list[dict[str, Any]]) -> str:
    normalized = [
        {
            "file_id": item.get("file_id"),
            "file_name": item.get("file_name"),
            "md5sum": item.get("md5sum"),
            "file_size": item.get("file_size"),
            "updated_datetime": item.get("updated_datetime"),
            "data_release": item.get("data_release"),
            "cohort": item.get("cohort"),
        }
        for item in sorted(files, key=manifest_key)
    ]
    payload = json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def latest_release(files: list[dict[str, Any]]) -> str | None:
    releases = sorted({str(item.get("data_release")) for item in files if item.get("data_release")})
    return releases[-1] if releases else None


def read_current_manifest(state_dir: Path, source: str) -> dict[str, Any] | None:
    return read_json_file(state_dir / "manifests" / f"{source}_current.json")


def write_current_manifest(state_dir: Path, source: str, manifest: dict[str, Any]) -> Path:
    path = state_dir / "manifests" / f"{source}_current.json"
    write_json_atomic(path, manifest)
    return path


def read_json_file(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def tcga_cache_relative_path(cohort: str, file_id: str, file_name: str) -> str:
    return str(Path("gdc_cache") / cohort / "Transcriptome_Profiling" / "Gene_Expression_Quantification" / file_id / file_name)


def backup_file(path: Path, backup_dir: Path) -> None:
    relative = path.anchor and str(path).lstrip("/") or str(path)
    destination = backup_dir / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, destination)


def atomic_replace(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    tmp = destination.with_name(f"{destination.name}.{uuid.uuid4().hex}.tmp")
    shutil.move(str(source), str(tmp))
    tmp.replace(destination)


@contextmanager
def sync_lock(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd: int | None = None
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, str(os.getpid()).encode("utf-8"))
        yield
    except FileExistsError as exc:
        raise SyncError(f"Sync lock already exists: {path}") from exc
    finally:
        if fd is not None:
            os.close(fd)
            try:
                path.unlink()
            except FileNotFoundError:
                pass


def md5_file(path: Path) -> str:
    digest = hashlib.md5()  # nosec - GDC manifests use md5 checksums.
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def local_md5(path: Path) -> str | None:
    return md5_file(path) if path.exists() else None


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc).replace(tzinfo=None)


def iso_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_run_id(prefix: str) -> str:
    return f"{prefix}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"


def first(value: Any) -> Any:
    if isinstance(value, list):
        return value[0] if value else {}
    return value if value is not None else {}


def clean_value(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def read_tsv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8", errors="replace") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def first_nonempty(values) -> str:
    for value in values:
        if value:
            return str(value)
    return ""


def count_lines(path: Path) -> int:
    with path.open(encoding="utf-8", errors="replace") as handle:
        return sum(1 for _ in handle)


def json_slim(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: json_slim(item) for key, item in value.items()}
    if isinstance(value, list):
        if len(value) > 20:
            return {"count": len(value), "first_items": [json_slim(item) for item in value[:5]]}
        return [json_slim(item) for item in value]
    return value


def diff_summary(diff: dict[str, Any]) -> dict[str, Any]:
    return {
        "added": len(diff.get("added") or []),
        "changed": len(diff.get("changed") or []),
        "stale": len(diff.get("stale") or []),
        "stale_retained": len(diff.get("stale") or []),
    }


def import_after_sync(settings: Settings) -> None:
    init_db()
    with SessionLocal() as db:
        import_cohorts_and_samples(db, settings.tcga_data_dir, force=True)
        import_tcga_cdr(db, settings.tcga_cdr_path, force=True)
