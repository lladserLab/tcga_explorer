from __future__ import annotations

import csv
from datetime import datetime
import json
import os
from pathlib import Path
import shutil
from typing import Any
import uuid

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import (
    CancerType,
    DataManifest,
    DataSource,
    RepositoryDataset,
    RepositoryEndpointDefinition,
    RepositoryEndpointValue,
    RepositoryExpressionLayer,
    RepositoryGene,
    RepositoryPatient,
    RepositoryRelease,
    RepositorySample,
)
from app.repository.storage import (
    canonical_json_sha256,
    read_matrix_metadata,
    safe_bundle_path,
    sha256_file,
)


BUNDLE_SCHEMA_VERSION = "tcga-trace-external-rnaseq-bundle-v1"
MIN_PATIENTS = 10
MIN_EVENTS = 5
MIN_CENSORED = 5
MIN_GENES = 10_000


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8", errors="strict") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def load_manifest(bundle_dir: Path) -> dict[str, Any]:
    path = bundle_dir / "manifest.json"
    if not path.is_file():
        raise FileNotFoundError(f"Bundle manifest not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != BUNDLE_SCHEMA_VERSION:
        raise ValueError("Unsupported external repository bundle schema.")
    return payload


def validate_bundle(bundle_dir: Path) -> dict[str, Any]:
    manifest = load_manifest(bundle_dir)
    errors: list[str] = []
    checksums = manifest.get("checksums") or {}
    if not checksums:
        errors.append("No source or derived file checksums were declared.")
    for relative, expected in checksums.items():
        path = safe_bundle_path(bundle_dir, str(relative))
        if not path.is_file():
            errors.append(f"Missing bundle file: {relative}")
            continue
        actual = sha256_file(path)
        if actual != expected:
            errors.append(
                f"Checksum mismatch for {relative}: expected {expected}, got {actual}."
            )

    dataset = manifest.get("dataset") or {}
    release = manifest.get("release") or {}
    for field in (
        "id",
        "cancer_code",
        "name",
        "source_provider",
        "source_accession",
        "source_url",
        "independence_status",
        "license_id",
        "license_url",
    ):
        if not dataset.get(field):
            errors.append(f"Dataset field {field!r} is required.")
    for field in ("id", "version", "source_snapshot"):
        if not release.get(field):
            errors.append(f"Release field {field!r} is required.")
    if dataset.get("assay") != "bulk_rna_seq":
        errors.append("Only bulk_rna_seq datasets can be promoted.")
    if dataset.get("independence_status") != "verified_external":
        errors.append("Dataset independence from TCGA is not verified.")
    source_files = manifest.get("source_files") or {}
    if not source_files.get("license"):
        errors.append("An immutable source license record is required.")

    layers = manifest.get("expression_layers") or []
    if not layers:
        errors.append("At least one expression layer is required.")
    if sum(bool(layer.get("is_default")) for layer in layers) != 1:
        errors.append("Exactly one expression layer must be the default.")

    patient_rows = read_tsv(
        safe_bundle_path(bundle_dir, manifest["files"]["patients"])
    )
    sample_rows = read_tsv(
        safe_bundle_path(bundle_dir, manifest["files"]["samples"])
    )
    patient_ids = [row.get("patient_id", "") for row in patient_rows]
    sample_ids = [row.get("sample_id", "") for row in sample_rows]
    if not patient_ids or any(not value for value in patient_ids):
        errors.append("Every patient row requires patient_id.")
    if len(patient_ids) != len(set(patient_ids)):
        errors.append("Patient identifiers are not unique.")
    if not sample_ids or any(not value for value in sample_ids):
        errors.append("Every sample row requires sample_id.")
    if len(sample_ids) != len(set(sample_ids)):
        errors.append("Sample identifiers are not unique.")
    unknown_patient_ids = sorted(
        {
            row.get("patient_id", "")
            for row in sample_rows
            if row.get("patient_id", "") not in set(patient_ids)
        }
    )
    if unknown_patient_ids:
        errors.append(
            f"{len(unknown_patient_ids)} samples reference unknown patients."
        )

    endpoint_qc: dict[str, dict[str, int | bool]] = {}
    for definition in manifest.get("endpoints") or []:
        endpoint_id = str(definition.get("endpoint_id") or "")
        endpoint_rows = read_tsv(
            safe_bundle_path(bundle_dir, str(definition["values_file"]))
        )
        complete_patients: set[str] = set()
        event_count = 0
        for row in endpoint_rows:
            patient_id = row.get("patient_id", "")
            try:
                time_days = float(row.get("time_days", ""))
                event = int(row.get("event", ""))
            except ValueError:
                errors.append(
                    f"Endpoint {endpoint_id} contains a non-numeric time or event."
                )
                continue
            if patient_id not in set(patient_ids):
                errors.append(
                    f"Endpoint {endpoint_id} references unknown patient {patient_id!r}."
                )
            if time_days <= 0:
                errors.append(
                    f"Endpoint {endpoint_id} contains non-positive follow-up."
                )
            if event not in {0, 1}:
                errors.append(
                    f"Endpoint {endpoint_id} contains an event outside 0/1."
                )
            complete_patients.add(patient_id)
            event_count += int(event == 1)
        available = (
            len(complete_patients) >= MIN_PATIENTS
            and event_count >= MIN_EVENTS
            and len(complete_patients) - event_count >= MIN_CENSORED
        )
        censored_count = len(complete_patients) - event_count
        endpoint_qc[endpoint_id] = {
            "patients": len(complete_patients),
            "events": event_count,
            "censored": censored_count,
            "available": available,
        }
    if not any(row["available"] for row in endpoint_qc.values()):
        errors.append(
            f"No endpoint reaches {MIN_PATIENTS} patients, {MIN_EVENTS} events, "
            f"and {MIN_CENSORED} censored observations."
        )

    layer_qc: dict[str, dict[str, int | bool]] = {}
    for layer in layers:
        layer_id = str(layer.get("layer_id") or "")
        for field, maximum in (
            ("layer_id", 64),
            ("source_unit", 64),
            ("analysis_unit", 128),
            ("transform", 64),
        ):
            value = str(layer.get(field) or "")
            if not value:
                errors.append(
                    f"Layer {layer_id or '<unnamed>'} requires {field}."
                )
            elif len(value) > maximum:
                errors.append(
                    f"Layer {layer_id or '<unnamed>'} field {field} "
                    f"exceeds {maximum} characters."
                )
        metadata_path = safe_bundle_path(bundle_dir, str(layer["metadata_file"]))
        matrix_path = safe_bundle_path(bundle_dir, str(layer["matrix_file"]))
        genes_path = safe_bundle_path(bundle_dir, str(layer["genes_file"]))
        metadata = read_matrix_metadata(metadata_path)
        genes = read_tsv(genes_path)
        symbols = [row.get("gene_symbol", "") for row in genes]
        if len(symbols) != len(set(symbols)):
            errors.append(f"Layer {layer_id} has duplicate canonical symbols.")
        if any(not symbol for symbol in symbols):
            errors.append(f"Layer {layer_id} has missing canonical symbols.")
        if len(symbols) < MIN_GENES:
            errors.append(
                f"Layer {layer_id} has {len(symbols)} genes; at least {MIN_GENES} are required."
            )
        if int(metadata.get("gene_count") or 0) != len(genes):
            errors.append(f"Layer {layer_id} gene metadata does not match genes.tsv.")
        metadata_samples = list(metadata.get("sample_ids") or [])
        if int(metadata.get("sample_count") or 0) != len(metadata_samples):
            errors.append(f"Layer {layer_id} sample_count is inconsistent.")
        if set(metadata_samples) - set(sample_ids):
            errors.append(f"Layer {layer_id} contains unknown sample IDs.")
        expected_bytes = len(genes) * len(metadata_samples) * 4
        if matrix_path.stat().st_size != expected_bytes:
            errors.append(
                f"Layer {layer_id} matrix size is {matrix_path.stat().st_size}; "
                f"expected {expected_bytes} bytes."
            )
        layer_qc[layer_id] = {
            "genes": len(genes),
            "samples": len(metadata_samples),
            "valid_size": matrix_path.stat().st_size == expected_bytes,
        }

    qc = {
        "status": "passed" if not errors else "failed",
        "errors": errors,
        "patients": len(patient_ids),
        "samples": len(sample_ids),
        "endpoints": endpoint_qc,
        "layers": layer_qc,
        "thresholds": {
            "minimum_patients": MIN_PATIENTS,
            "minimum_events": MIN_EVENTS,
            "minimum_censored": MIN_CENSORED,
            "minimum_genes": MIN_GENES,
        },
    }
    return {"manifest": manifest, "qc": qc}


def promote_bundle(
    db: Session,
    bundle_dir: Path,
    repository_root: Path,
) -> dict[str, Any]:
    validation = validate_bundle(bundle_dir)
    if validation["qc"]["status"] != "passed":
        raise ValueError(
            "Bundle failed validation: "
            + "; ".join(validation["qc"]["errors"][:10])
        )
    manifest = validation["manifest"]
    dataset_payload = manifest["dataset"]
    release_payload = manifest["release"]
    dataset_id = str(dataset_payload["id"])
    release_id = str(release_payload["id"])
    manifest_hash = canonical_json_sha256(manifest)

    destination = (
        repository_root
        / "studies"
        / dataset_id
        / "releases"
        / release_id
    )
    if destination.exists():
        existing_manifest = load_manifest(destination)
        if canonical_json_sha256(existing_manifest) != manifest_hash:
            raise ValueError(
                f"Immutable release path already exists with different content: {destination}"
            )
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.parent / f".promoting-{uuid.uuid4().hex}"
        shutil.copytree(bundle_dir, temporary)
        os.replace(temporary, destination)

    cancer = db.get(CancerType, str(dataset_payload["cancer_code"]))
    if cancer is None:
        raise ValueError(
            f"Unknown cancer type {dataset_payload['cancer_code']!r}; sync the catalog first."
        )
    dataset = db.get(RepositoryDataset, dataset_id)
    if dataset is None:
        dataset = RepositoryDataset(id=dataset_id, cancer_code=cancer.code)
        db.add(dataset)
    _assign_dataset(dataset, dataset_payload)

    existing_release = db.get(RepositoryRelease, release_id)
    if existing_release is not None:
        if existing_release.manifest_hash != manifest_hash:
            raise ValueError("Release ID already exists with a different manifest.")
        return _promotion_summary(dataset, existing_release)

    release = RepositoryRelease(
        id=release_id,
        dataset_id=dataset_id,
        version=str(release_payload["version"]),
        status="published",
        manifest_hash=manifest_hash,
        manifest_path=str(destination / "manifest.json"),
        repository_path=str(destination),
        source_snapshot=str(release_payload["source_snapshot"]),
        source_retrieved_at=_parse_datetime(release_payload.get("retrieved_at")),
        patient_count=int(validation["qc"]["patients"]),
        sample_count=int(validation["qc"]["samples"]),
        gene_count=max(
            int(layer["genes"])
            for layer in validation["qc"]["layers"].values()
        ),
        qc_status="passed",
        qc_json=validation["qc"],
        published_at=datetime.utcnow(),
    )
    db.add(release)
    db.flush()
    _import_release_rows(db, release, destination, manifest, validation["qc"])

    dataset.active_release_id = release.id
    dataset.status = "available"
    cancer.coverage_status = "available"
    cancer.coverage_metadata = {
        **(cancer.coverage_metadata or {}),
        "status": "available",
        "active_dataset_id": dataset.id,
        "active_release_id": release.id,
    }
    _register_data_source(db, dataset, release)
    db.commit()
    return _promotion_summary(dataset, release)


def revalidate_active_releases(db: Session) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    datasets = db.scalars(
        select(RepositoryDataset)
        .where(RepositoryDataset.active_release_id.is_not(None))
        .order_by(RepositoryDataset.id)
    ).all()
    for dataset in datasets:
        release = db.get(RepositoryRelease, dataset.active_release_id)
        if release is None:
            dataset.status = "qc_failed"
            results.append(
                {
                    "dataset_id": dataset.id,
                    "release_id": dataset.active_release_id,
                    "status": "failed",
                    "errors": ["Active release record is missing."],
                }
            )
            continue
        validation = validate_bundle(Path(release.repository_path))
        qc = validation["qc"]
        release.patient_count = int(qc["patients"])
        release.sample_count = int(qc["samples"])
        release.gene_count = max(
            (int(layer["genes"]) for layer in qc["layers"].values()),
            default=0,
        )
        release.qc_status = str(qc["status"])
        release.qc_json = qc
        definitions = db.scalars(
            select(RepositoryEndpointDefinition).where(
                RepositoryEndpointDefinition.release_id == release.id
            )
        ).all()
        for definition in definitions:
            endpoint_qc = qc["endpoints"].get(definition.endpoint_id)
            if endpoint_qc is None:
                definition.available = False
                definition.reason = (
                    "Endpoint is absent from the current bundle validation."
                )
                continue
            definition.patient_count = int(endpoint_qc["patients"])
            definition.event_count = int(endpoint_qc["events"])
            definition.available = bool(endpoint_qc["available"])
            definition.reason = (
                None
                if definition.available
                else endpoint_qc_failure_reason(endpoint_qc)
            )
        dataset.status = (
            "available" if qc["status"] == "passed" else "qc_failed"
        )
        results.append(
            {
                "dataset_id": dataset.id,
                "release_id": release.id,
                "status": qc["status"],
                "endpoints": qc["endpoints"],
                "errors": qc["errors"],
            }
        )
    db.commit()
    return {
        "datasets": results,
        "available": sum(row["status"] == "passed" for row in results),
        "qc_failed": sum(row["status"] != "passed" for row in results),
    }


def endpoint_qc_failure_reason(endpoint_qc: dict[str, Any]) -> str:
    requirements: list[str] = []
    if int(endpoint_qc.get("patients") or 0) < MIN_PATIENTS:
        requirements.append(f"{MIN_PATIENTS} patients")
    if int(endpoint_qc.get("events") or 0) < MIN_EVENTS:
        requirements.append(f"{MIN_EVENTS} events")
    if int(endpoint_qc.get("censored") or 0) < MIN_CENSORED:
        requirements.append(f"{MIN_CENSORED} censored observations")
    if not requirements:
        return "Endpoint failed the current repository QC policy."
    return "Requires at least " + ", ".join(requirements) + "."


def _assign_dataset(dataset: RepositoryDataset, payload: dict[str, Any]) -> None:
    for field in (
        "cancer_code",
        "name",
        "description",
        "cohort_context",
        "source_provider",
        "source_accession",
        "source_url",
        "publication_citation",
        "publication_id",
        "organism",
        "assay",
        "independence_status",
        "license_id",
        "license_url",
        "redistribution_allowed",
    ):
        setattr(dataset, field, payload.get(field))
    dataset.metadata_json = payload.get("metadata") or {}


def _import_release_rows(
    db: Session,
    release: RepositoryRelease,
    root: Path,
    manifest: dict[str, Any],
    qc: dict[str, Any],
) -> None:
    patients = read_tsv(safe_bundle_path(root, manifest["files"]["patients"]))
    samples = read_tsv(safe_bundle_path(root, manifest["files"]["samples"]))
    for row in patients:
        db.add(
            RepositoryPatient(
                release_id=release.id,
                patient_id=row["patient_id"],
                stage=_clean(row.get("stage")),
                grade=_clean(row.get("grade")),
                gender=_clean(row.get("gender")),
                race=_clean(row.get("race")),
                age_at_index=_optional_float(row.get("age_at_index")),
                raw_metadata=_json_field(row.get("raw_metadata_json")),
            )
        )
    for row in samples:
        db.add(
            RepositorySample(
                release_id=release.id,
                sample_id=row["sample_id"],
                patient_id=row["patient_id"],
                sample_type=_clean(row.get("sample_type")),
                sample_role=_clean(row.get("sample_role")),
                selection_rank=int(row.get("selection_rank") or 0),
                raw_metadata=_json_field(row.get("raw_metadata_json")),
            )
        )

    for raw in manifest["endpoints"]:
        endpoint_id = str(raw["endpoint_id"])
        endpoint_qc = qc["endpoints"][endpoint_id]
        db.add(
            RepositoryEndpointDefinition(
                release_id=release.id,
                endpoint_id=endpoint_id,
                standard_code=raw.get("standard_code"),
                label=str(raw["label"]),
                time_origin=str(raw["time_origin"]),
                event_definition=str(raw["event_definition"]),
                source_time_column=str(raw["source_time_column"]),
                source_event_column=str(raw["source_event_column"]),
                source_time_unit=str(raw["source_time_unit"]),
                patient_count=int(endpoint_qc["patients"]),
                event_count=int(endpoint_qc["events"]),
                available=bool(endpoint_qc["available"]),
                reason=None if endpoint_qc["available"] else "Below endpoint QC thresholds.",
                metadata_json=raw.get("metadata") or {},
            )
        )
        for row in read_tsv(safe_bundle_path(root, str(raw["values_file"]))):
            db.add(
                RepositoryEndpointValue(
                    release_id=release.id,
                    endpoint_id=endpoint_id,
                    patient_id=row["patient_id"],
                    time_days=float(row["time_days"]),
                    event=int(row["event"]),
                    raw_time=_optional_float(row.get("raw_time")),
                    raw_event=_clean(row.get("raw_event")),
                    raw_metadata=_json_field(row.get("raw_metadata_json")),
                )
            )

    for raw in manifest["expression_layers"]:
        layer = RepositoryExpressionLayer(
            release_id=release.id,
            layer_id=str(raw["layer_id"]),
            label=str(raw["label"]),
            source_unit=str(raw["source_unit"]),
            analysis_unit=str(raw["analysis_unit"]),
            transform=str(raw["transform"]),
            matrix_path=str(safe_bundle_path(root, str(raw["matrix_file"]))),
            matrix_sha256=sha256_file(
                safe_bundle_path(root, str(raw["matrix_file"]))
            ),
            metadata_path=str(
                safe_bundle_path(root, str(raw["metadata_file"]))
            ),
            gene_count=int(qc["layers"][str(raw["layer_id"])]["genes"]),
            sample_count=int(qc["layers"][str(raw["layer_id"])]["samples"]),
            is_default=bool(raw.get("is_default")),
            downloadable=bool(raw.get("downloadable")),
            metadata_json=raw.get("metadata") or {},
        )
        db.add(layer)
        db.flush()
        for row in read_tsv(safe_bundle_path(root, str(raw["genes_file"]))):
            db.add(
                RepositoryGene(
                    expression_layer_id=layer.id,
                    gene_symbol=row["gene_symbol"].strip().upper(),
                    original_gene_id=row["original_gene_id"],
                    row_number=int(row["row_number"]),
                    mapping_source=row["mapping_source"],
                )
            )


def _register_data_source(
    db: Session,
    dataset: RepositoryDataset,
    release: RepositoryRelease,
) -> None:
    source_id = f"external:{dataset.id}"
    source = db.get(DataSource, source_id)
    if source is None:
        source = DataSource(
            id=source_id,
            label=dataset.name,
            kind="external_bulk_rna_seq",
            status="ready",
        )
        db.add(source)
    source.label = dataset.name
    source.status = "ready"
    source.source_url = dataset.source_url
    source.source_path = release.repository_path
    source.imported_at = datetime.utcnow()
    source.metadata_json = {
        "dataset_id": dataset.id,
        "release_id": release.id,
        "manifest_hash": release.manifest_hash,
        "license_id": dataset.license_id,
        "redistribution_allowed": dataset.redistribution_allowed,
    }
    existing = db.query(DataManifest).filter_by(
        source_id=source_id, manifest_hash=release.manifest_hash
    ).first()
    if existing is None:
        db.add(
            DataManifest(
                source_id=source_id,
                status="ready",
                manifest_hash=release.manifest_hash,
                data_release=release.version,
                file_count=len((load_manifest(Path(release.repository_path)).get("checksums") or {})),
                manifest_path=release.manifest_path,
                metadata_json={"release_id": release.id},
            )
        )


def _promotion_summary(
    dataset: RepositoryDataset, release: RepositoryRelease
) -> dict[str, Any]:
    return {
        "dataset_id": dataset.id,
        "release_id": release.id,
        "status": release.status,
        "manifest_hash": release.manifest_hash,
        "patients": release.patient_count,
        "samples": release.sample_count,
        "genes": release.gene_count,
        "qc_status": release.qc_status,
    }


def _parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value).replace("Z", "+00:00")
    return datetime.fromisoformat(text).replace(tzinfo=None)


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    missing_values = {
        "NA",
        "N/A",
        "NULL",
        "[NOT AVAILABLE]",
        "[NOT APPLICABLE]",
    }
    return text if text and text.upper() not in missing_values else None


def _optional_float(value: Any) -> float | None:
    cleaned = _clean(value)
    if cleaned is None:
        return None
    return float(cleaned)


def _json_field(value: Any) -> dict | None:
    cleaned = _clean(value)
    if cleaned is None:
        return None
    payload = json.loads(cleaned)
    return payload if isinstance(payload, dict) else {"value": payload}
