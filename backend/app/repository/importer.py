from __future__ import annotations

import csv
from datetime import datetime
import json
import math
import os
from pathlib import Path
import re
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
from app.pancancer_study_universes import (
    SourceKind,
    StudyUniverseCategory,
    StudyUniverseDefinition,
    require_study_registry_disposition,
)
from app.repository.capabilities import (
    CAPABILITY_NAMES,
    available_repository_modules,
    derive_repository_capabilities,
)
from app.repository.candidates import (
    CandidateRegistryError,
    load_dataset_candidate_registry,
)
from app.repository.contracts import (
    BUNDLE_SCHEMA_VERSION_V1,
    BUNDLE_SCHEMA_VERSION_V2,
    SUPPORTED_BUNDLE_SCHEMA_VERSIONS,
    is_capability_first_schema,
)
from app.repository.paths import resolve_repository_release_path
from app.repository.storage import (
    canonical_json_sha256,
    read_matrix_metadata,
    safe_bundle_path,
    scan_float32le_matrix,
    sha256_file,
)


# Backward-compatible import used by existing v1 bundle builders and tests.
BUNDLE_SCHEMA_VERSION = BUNDLE_SCHEMA_VERSION_V1
MIN_PATIENTS = 10
MIN_EVENTS = 5
MIN_CENSORED = 5
MIN_GENES = 10_000
REPOSITORY_IDENTIFIER_PATTERN = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._-]*$"
)
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8", errors="strict") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def load_manifest(bundle_dir: Path) -> dict[str, Any]:
    path = bundle_dir / "manifest.json"
    if not path.is_file():
        raise FileNotFoundError(f"Bundle manifest not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") not in SUPPORTED_BUNDLE_SCHEMA_VERSIONS:
        raise ValueError("Unsupported external repository bundle schema.")
    return payload


def referenced_bundle_files(manifest: dict[str, Any]) -> set[str]:
    """Return every payload file whose bytes determine a release.

    Extra checksummed provenance files are allowed, but every explicit file
    reference used for import, source provenance or licensing must be covered
    by the manifest checksum map.
    """

    referenced: set[str] = set()
    for section in ("files", "source_files"):
        values = manifest.get(section) or {}
        if isinstance(values, dict):
            referenced.update(
                str(value).strip()
                for value in values.values()
                if str(value or "").strip()
            )
    for layer in manifest.get("expression_layers") or []:
        if not isinstance(layer, dict):
            continue
        for field in ("matrix_file", "metadata_file", "genes_file"):
            value = str(layer.get(field) or "").strip()
            if value:
                referenced.add(value)
    for endpoint in manifest.get("endpoints") or []:
        if not isinstance(endpoint, dict):
            continue
        value = str(endpoint.get("values_file") or "").strip()
        if value:
            referenced.add(value)
    return referenced


def validate_bundle(bundle_dir: Path) -> dict[str, Any]:
    manifest = load_manifest(bundle_dir)
    errors: list[str] = []
    checksums = manifest.get("checksums") or {}
    if not isinstance(checksums, dict) or not checksums:
        errors.append("No source or derived file checksums were declared.")
        checksums = {}
    referenced_files = referenced_bundle_files(manifest)
    for relative in sorted(referenced_files - set(checksums)):
        errors.append(
            f"Referenced bundle file is not checksum-protected: {relative}."
        )
    for relative, expected in checksums.items():
        expected = str(expected or "").strip()
        if not SHA256_PATTERN.fullmatch(expected):
            errors.append(
                f"Invalid SHA-256 checksum for {relative}: expected 64 "
                "lowercase hexadecimal characters."
            )
            continue
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
    for field, maximum in (
        ("id", 128),
        ("source_provider", 64),
        ("source_accession", 128),
        ("publication_id", 128),
        ("organism", 64),
        ("assay", 64),
        ("independence_status", 32),
        ("license_id", 64),
    ):
        value = str(dataset.get(field) or "")
        if value and len(value) > maximum:
            errors.append(
                f"Dataset field {field} exceeds {maximum} characters."
            )
    for field, maximum in (
        ("id", 128),
        ("version", 128),
        ("source_snapshot", 256),
    ):
        value = str(release.get(field) or "")
        if value and len(value) > maximum:
            errors.append(
                f"Release field {field} exceeds {maximum} characters."
            )
    for label, value in (
        ("dataset", dataset.get("id")),
        ("release", release.get("id")),
    ):
        if value and not REPOSITORY_IDENTIFIER_PATTERN.fullmatch(
            str(value)
        ):
            errors.append(
                f"The {label} ID contains unsafe path characters."
            )
    if str(dataset.get("id") or "").casefold().startswith("user-"):
        errors.append(
            "Public repository dataset IDs cannot use the reserved user- prefix."
        )
    if dataset.get("assay") != "bulk_rna_seq":
        errors.append("Only bulk_rna_seq datasets can be promoted.")
    if dataset.get("independence_status") != "verified_external":
        errors.append("Dataset independence from TCGA is not verified.")
    source_files = manifest.get("source_files") or {}
    if not source_files.get("license"):
        errors.append("An immutable source license record is required.")

    schema_version = str(manifest["schema_version"])
    capability_first = is_capability_first_schema(schema_version)
    layers = manifest.get("expression_layers") or []
    if not isinstance(layers, list) or not layers:
        errors.append("At least one expression layer is required.")
        layers = []
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
    patient_id_set = set(patient_ids)
    sample_id_set = set(sample_ids)
    if not patient_ids or any(not value for value in patient_ids):
        errors.append("Every patient row requires patient_id.")
    if len(patient_ids) != len(patient_id_set):
        errors.append("Patient identifiers are not unique.")
    if not sample_ids or any(not value for value in sample_ids):
        errors.append("Every sample row requires sample_id.")
    if len(sample_ids) != len(sample_id_set):
        errors.append("Sample identifiers are not unique.")
    unknown_patient_ids = sorted(
        {
            row.get("patient_id", "")
            for row in sample_rows
            if row.get("patient_id", "") not in patient_id_set
        }
    )
    if unknown_patient_ids:
        errors.append(
            f"{len(unknown_patient_ids)} samples reference unknown patients."
        )
    sample_patient_by_id = {
        row.get("sample_id", ""): row.get("patient_id", "")
        for row in sample_rows
        if row.get("sample_id", "")
    }
    if capability_first:
        for row in sample_rows:
            raw_rank = row.get("selection_rank")
            if raw_rank in {None, ""}:
                errors.append(
                    "Every v2 sample row requires a deterministic "
                    "selection_rank."
                )
                break
            try:
                rank = int(raw_rank)
            except (TypeError, ValueError):
                errors.append("Sample selection_rank must be an integer.")
                break
            if rank < 0:
                errors.append("Sample selection_rank cannot be negative.")
                break

    endpoint_definitions = manifest.get("endpoints") or []
    if not isinstance(endpoint_definitions, list):
        errors.append("Manifest endpoints must be an array.")
        endpoint_definitions = []
    endpoint_qc: dict[str, dict[str, int | bool]] = {}
    endpoint_events_by_patient: dict[str, dict[str, int]] = {}
    endpoint_ids: list[str] = []
    required_endpoint_fields = (
        "endpoint_id",
        "label",
        "time_origin",
        "event_definition",
        "source_time_column",
        "source_event_column",
        "source_time_unit",
        "values_file",
    )
    for definition in endpoint_definitions:
        endpoint_id = str(definition.get("endpoint_id") or "").strip()
        endpoint_ids.append(endpoint_id)
        for field in required_endpoint_fields:
            if not definition.get(field):
                errors.append(
                    f"Endpoint {endpoint_id or '<unnamed>'} requires {field}."
                )
        if not endpoint_id or not definition.get("values_file"):
            continue
        endpoint_rows = read_tsv(
            safe_bundle_path(bundle_dir, str(definition["values_file"]))
        )
        row_patient_ids = [
            str(row.get("patient_id") or "") for row in endpoint_rows
        ]
        duplicate_endpoint_patients = len(row_patient_ids) - len(
            set(row_patient_ids)
        )
        if duplicate_endpoint_patients:
            errors.append(
                f"Endpoint {endpoint_id} contains duplicate patient rows."
            )
        complete_patients: set[str] = set()
        endpoint_events_by_patient[endpoint_id] = {}
        event_count = 0
        for row in endpoint_rows:
            patient_id = str(row.get("patient_id") or "")
            try:
                time_days = float(row.get("time_days", ""))
                event = int(row.get("event", ""))
            except (TypeError, ValueError):
                errors.append(
                    f"Endpoint {endpoint_id} contains a non-numeric time or event."
                )
                continue
            valid = True
            if not patient_id or patient_id not in patient_id_set:
                errors.append(
                    f"Endpoint {endpoint_id} references unknown patient {patient_id!r}."
                )
                valid = False
            if not math.isfinite(time_days) or time_days <= 0:
                errors.append(
                    f"Endpoint {endpoint_id} contains non-positive or "
                    "non-finite follow-up."
                )
                valid = False
            if event not in {0, 1}:
                errors.append(
                    f"Endpoint {endpoint_id} contains an event outside 0/1."
                )
                valid = False
            if valid:
                complete_patients.add(patient_id)
                endpoint_events_by_patient[endpoint_id][patient_id] = event
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
    if len(endpoint_ids) != len(set(endpoint_ids)):
        errors.append("Endpoint identifiers are not unique.")

    capability_policy = manifest.get("capability_policy") or {}
    if not isinstance(capability_policy, dict):
        errors.append("capability_policy must be an object.")
        capability_policy = {}
    prohibited = capability_policy.get("prohibited") or {}
    if not isinstance(prohibited, dict):
        errors.append("capability_policy.prohibited must be an object.")
        prohibited = {}
    for capability, reason in prohibited.items():
        if capability not in CAPABILITY_NAMES:
            errors.append(
                f"Unknown prohibited capability {capability!r}."
            )
        if not str(reason or "").strip():
            errors.append(
                f"Prohibited capability {capability!r} requires a reason."
            )
    if (
        not capability_first
        and not endpoint_definitions
        and not str(prohibited.get("survival") or "").strip()
    ):
        errors.append(
            "A v1 bundle without endpoint definitions must explicitly "
            "prohibit survival analysis with a documented reason."
        )

    layer_qc: dict[str, dict[str, Any]] = {}
    default_metadata_samples: list[str] = []
    default_gene_count = 0
    layer_ids: list[str] = []
    for layer in layers:
        layer_id = str(layer.get("layer_id") or "")
        layer_ids.append(layer_id)
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
        metadata_path = safe_bundle_path(
            bundle_dir, str(layer["metadata_file"])
        )
        matrix_path = safe_bundle_path(
            bundle_dir, str(layer["matrix_file"])
        )
        genes_path = safe_bundle_path(
            bundle_dir, str(layer["genes_file"])
        )
        metadata = read_matrix_metadata(metadata_path)
        genes = read_tsv(genes_path)
        symbols = [row.get("gene_symbol", "") for row in genes]
        if len(symbols) != len(set(symbols)):
            errors.append(f"Layer {layer_id} has duplicate canonical symbols.")
        if any(not symbol for symbol in symbols):
            errors.append(f"Layer {layer_id} has missing canonical symbols.")
        if len(symbols) < MIN_GENES:
            errors.append(
                f"Layer {layer_id} has {len(symbols)} genes; at least "
                f"{MIN_GENES} are required."
            )
        if int(metadata.get("gene_count") or 0) != len(genes):
            errors.append(
                f"Layer {layer_id} gene metadata does not match genes.tsv."
            )
        row_numbers: list[int] = []
        for row in genes:
            raw_row_number = str(row.get("row_number") or "").strip()
            try:
                row_number = int(raw_row_number)
            except (TypeError, ValueError):
                errors.append(
                    f"Layer {layer_id} has a non-integer gene row_number."
                )
                row_numbers = []
                break
            row_numbers.append(row_number)
        if row_numbers and row_numbers != list(range(len(genes))):
            errors.append(
                f"Layer {layer_id} gene row_number values must be unique, "
                "contiguous and match matrix row order from 0."
            )
        metadata_samples = [
            str(value) for value in metadata.get("sample_ids") or []
        ]
        if len(metadata_samples) != len(set(metadata_samples)):
            errors.append(
                f"Layer {layer_id} contains duplicate matrix sample IDs."
            )
        if int(metadata.get("sample_count") or 0) != len(metadata_samples):
            errors.append(f"Layer {layer_id} sample_count is inconsistent.")
        if set(metadata_samples) - sample_id_set:
            errors.append(f"Layer {layer_id} contains unknown sample IDs.")
        expected_bytes = len(genes) * len(metadata_samples) * 4
        actual_bytes = matrix_path.stat().st_size
        if actual_bytes != expected_bytes:
            errors.append(
                f"Layer {layer_id} matrix size is {actual_bytes}; "
                f"expected {expected_bytes} bytes."
            )
        numerical_qc = {
            "finite_values": 0,
            "nonfinite_values": 0,
            "constant_genes": len(genes),
            "variable_genes": 0,
        }
        if actual_bytes == expected_bytes:
            numerical_qc = scan_float32le_matrix(
                matrix_path,
                gene_count=len(genes),
                sample_count=len(metadata_samples),
            )
            if numerical_qc["nonfinite_values"]:
                errors.append(
                    f"Layer {layer_id} contains "
                    f"{numerical_qc['nonfinite_values']} non-finite expression "
                    "values; repository matrices use a strict no-missing-values "
                    "policy."
                )
            if numerical_qc["variable_genes"] == 0:
                errors.append(
                    f"Layer {layer_id} contains no gene with variable expression."
                )
        layer_patients = {
            sample_patient_by_id[sample_id] for sample_id in metadata_samples
            if sample_id in sample_patient_by_id
        }
        layer_endpoints = {}
        for endpoint_id, values in endpoint_events_by_patient.items():
            linked = [event for patient_id, event in values.items() if patient_id in layer_patients]
            events = sum(linked)
            censored = len(linked) - events
            layer_endpoints[endpoint_id] = {
                "patients": len(linked), "events": events, "censored": censored,
                "available": len(linked) >= MIN_PATIENTS and events >= MIN_EVENTS and censored >= MIN_CENSORED,
            }
        layer_qc[layer_id] = {
            "genes": len(genes),
            "samples": len(metadata_samples),
            "patients": len(layer_patients),
            "endpoints": layer_endpoints,
            "is_default": bool(layer.get("is_default")),
            "valid_size": actual_bytes == expected_bytes,
            "missing_value_policy": "forbid_non_finite",
            **numerical_qc,
        }
        if bool(layer.get("is_default")):
            default_metadata_samples = metadata_samples
            default_gene_count = len(genes)
    if len(layer_ids) != len(set(layer_ids)):
        errors.append("Expression layer identifiers are not unique.")

    default_sample_set = set(default_metadata_samples)
    molecular_patient_ids = {
        sample_patient_by_id[sample_id]
        for sample_id in default_sample_set
        if sample_id in sample_patient_by_id
    }
    if capability_first and default_sample_set != sample_id_set:
        errors.append(
            "The v2 default expression layer must contain every declared "
            "molecular sample exactly once."
        )
    if capability_first and molecular_patient_ids != patient_id_set:
        errors.append(
            "Every v2 patient must be represented in the default expression "
            "layer."
        )
    if capability_first and (
        len(molecular_patient_ids) < MIN_PATIENTS
        or len(default_metadata_samples) < MIN_PATIENTS
    ):
        errors.append(
            f"The molecular population requires at least {MIN_PATIENTS} "
            "expression-linked patients and samples."
        )

    qc = {
        "schema_version": "tcga-trace-external-repository-qc-v2",
        "bundle_schema_version": schema_version,
        "status": "passed" if not errors else "failed",
        "errors": errors,
        "patients": len(patient_ids),
        "samples": len(sample_ids),
        "molecular_population": {
            "patients": len(molecular_patient_ids),
            "samples": len(default_metadata_samples),
            "genes": default_gene_count,
        },
        "endpoints": endpoint_qc,
        "layers": layer_qc,
        "default_expression_layer_id": next(
            (
                str(layer.get("layer_id"))
                for layer in layers
                if bool(layer.get("is_default"))
            ),
            None,
        ),
        "capability_policy": {"prohibited": dict(prohibited)},
        "thresholds": {
            "minimum_patients": MIN_PATIENTS,
            "minimum_events": MIN_EVENTS,
            "minimum_censored": MIN_CENSORED,
            "minimum_genes": MIN_GENES,
        },
    }
    qc["capabilities"] = derive_repository_capabilities(qc)
    qc["available_modules"] = available_repository_modules(
        qc["capabilities"]
    )
    return {"manifest": manifest, "qc": qc}


def preflight_bundle_promotion(
    bundle_dir: Path,
    registry_root: Path,
) -> dict[str, Any]:
    """Validate a bundle and its scientific-registry disposition.

    This function is deliberately read-only.  The CLI runs it before database
    initialization or catalog synchronization, and :func:`promote_bundle`
    repeats it so direct callers cannot bypass the registry gate.
    """

    validation = validate_bundle(bundle_dir)
    if validation["qc"]["status"] != "passed":
        raise ValueError(
            "Bundle failed validation: "
            + "; ".join(validation["qc"]["errors"][:10])
        )
    manifest = validation["manifest"]
    dataset_id = str(manifest["dataset"]["id"])
    disposition = require_study_registry_disposition(
        registry_root,
        dataset_id,
    )
    _validate_promotion_registry_compatibility(
        manifest,
        validation["qc"],
        disposition,
    )
    _validate_candidate_promotion_compatibility(
        registry_root,
        manifest,
        validation["qc"],
        disposition,
    )
    return validation


def _validate_promotion_registry_compatibility(
    manifest: dict[str, Any],
    qc: dict[str, Any],
    disposition: StudyUniverseDefinition,
) -> None:
    """Fail closed when a validated bundle contradicts registry policy."""

    dataset_payload = manifest["dataset"]
    dataset_id = str(dataset_payload["id"])
    bundle_cancer = str(dataset_payload["cancer_code"]).strip().upper()

    if disposition.universe_id != dataset_id:
        raise ValueError(
            "Study registry disposition ID does not match the bundle: "
            f"expected {dataset_id!r}, got {disposition.universe_id!r}."
        )
    if disposition.source_kind is not SourceKind.EXTERNAL:
        raise ValueError(
            f"Study registry disposition for {dataset_id!r} is not an "
            "external-study target."
        )
    if (
        not disposition.active
        or disposition.registry_category is StudyUniverseCategory.INACTIVE
    ):
        raise ValueError(
            f"Study registry disposition for {dataset_id!r} is inactive; "
            "the bundle cannot be promoted."
        )
    if not disposition.capabilities.catalog.available:
        raise ValueError(
            f"Study registry disposition for {dataset_id!r} does not permit "
            "catalog publication."
        )

    registry_cancer = str(disposition.cancer_code).strip().upper()
    if registry_cancer != bundle_cancer:
        raise ValueError(
            f"Cancer code mismatch for {dataset_id!r}: bundle declares "
            f"{bundle_cancer!r}, while the study registry declares "
            f"{registry_cancer!r}."
        )

    bundle_capabilities = qc.get("capabilities") or {}
    registry_capabilities = disposition.capabilities
    for capability_name in (
        "expression_comparison",
        "gsea",
        "survival",
    ):
        bundle_capability = bundle_capabilities.get(capability_name)
        if not isinstance(bundle_capability, dict) or not isinstance(
            bundle_capability.get("available"), bool
        ):
            raise ValueError(
                f"Bundle QC does not declare capability {capability_name!r}."
            )
        bundle_available = bool(bundle_capability["available"])
        registry_available = bool(
            getattr(registry_capabilities, capability_name).available
        )
        if bundle_available != registry_available:
            raise ValueError(
                f"Capability mismatch for {dataset_id!r} and "
                f"{capability_name!r}: bundle QC declares "
                f"available={bundle_available}, while the study registry "
                f"declares available={registry_available}."
            )

    hierarchical_target = (
        disposition.registry_category
        is StudyUniverseCategory.HIERARCHICAL_ACTIVE
    )
    hierarchical_available = bool(
        registry_capabilities.hierarchical_pancancer.available
    )
    if hierarchical_available != hierarchical_target:
        raise ValueError(
            f"Hierarchical target mismatch for {dataset_id!r}: category "
            f"{disposition.registry_category.value!r} and capability "
            f"available={hierarchical_available} are incompatible."
        )
    if hierarchical_target:
        survival = bundle_capabilities["survival"]
        endpoint_ids = {
            str(value) for value in survival.get("endpoint_ids") or []
        }
        if not survival["available"]:
            raise ValueError(
                f"Hierarchical target {dataset_id!r} requires an available "
                "survival endpoint in bundle QC."
            )
        if disposition.endpoint_class != "OS":
            raise ValueError(
                f"Hierarchical target {dataset_id!r} must declare an OS "
                "endpoint class."
            )
        if (
            not disposition.endpoint_id
            or disposition.endpoint_id not in endpoint_ids
        ):
            raise ValueError(
                f"Hierarchical target {dataset_id!r} requires registry "
                f"endpoint {disposition.endpoint_id!r} to be available in "
                "bundle QC."
            )


def _validate_candidate_promotion_compatibility(
    registry_root: Path,
    manifest: dict[str, Any],
    qc: dict[str, Any],
    disposition: StudyUniverseDefinition,
) -> None:
    """Require a finalized ledger decision when a dataset was a candidate."""

    dataset_id = str(manifest["dataset"]["id"])
    candidate_registry_path = Path(registry_root) / "dataset_candidates_v1.json"
    try:
        registry = load_dataset_candidate_registry(candidate_registry_path)
    except (FileNotFoundError, CandidateRegistryError) as exc:
        raise ValueError(
            "Dataset candidate promotion ledger could not be validated: "
            f"{exc}"
        ) from exc

    candidate = next(
        (
            row
            for row in registry["candidates"]
            if str(row.get("id") or "").strip() == dataset_id
        ),
        None,
    )
    # Historical releases can predate this candidate ledger. Its absence is
    # not retroactively interpreted as a pending promotion decision.
    if candidate is None:
        return

    decisions = candidate["decisions"]
    if candidate["status"] != "promoted":
        raise ValueError(
            f"Candidate ledger still marks {dataset_id!r} as "
            f"{candidate['status']!r}; status='promoted' is required."
        )
    if decisions["promotion_state"] != "promoted":
        raise ValueError(
            f"Candidate ledger for {dataset_id!r} requires "
            "promotion_state='promoted'."
        )
    if decisions["catalog_state"] != "promoted_release":
        raise ValueError(
            f"Candidate ledger for {dataset_id!r} requires "
            "catalog_state='promoted_release'."
        )
    if candidate.get("blockers"):
        raise ValueError(
            f"Candidate ledger for {dataset_id!r} still contains unresolved "
            "promotion blockers."
        )
    target_category = str(decisions.get("target_category") or "").strip()
    if target_category != disposition.registry_category.value:
        raise ValueError(
            f"Candidate target mismatch for {dataset_id!r}: ledger declares "
            f"{target_category!r}, while the study registry declares "
            f"{disposition.registry_category.value!r}."
        )

    bundle_capabilities = qc["capabilities"]
    expected_availability = {
        "catalog": True,
        "expression_comparison": bool(
            bundle_capabilities["expression_comparison"]["available"]
        ),
        "gsea": bool(bundle_capabilities["gsea"]["available"]),
        "survival": bool(bundle_capabilities["survival"]["available"]),
        "hierarchical_pancancer": bool(
            disposition.capabilities.hierarchical_pancancer.available
        ),
    }
    for capability_name, expected_available in expected_availability.items():
        candidate_capability = candidate["capabilities"][capability_name]
        expected_decision = "enabled" if expected_available else "disabled"
        if (
            candidate_capability["available"] != expected_available
            or candidate_capability["decision"] != expected_decision
        ):
            raise ValueError(
                f"Candidate capability mismatch for {dataset_id!r} and "
                f"{capability_name!r}: expected available="
                f"{expected_available} and decision={expected_decision!r}."
            )


def promote_bundle(
    db: Session,
    bundle_dir: Path,
    repository_root: Path,
    registry_root: Path,
) -> dict[str, Any]:
    validation = preflight_bundle_promotion(bundle_dir, registry_root)
    manifest = validation["manifest"]
    dataset_payload = manifest["dataset"]
    release_payload = manifest["release"]
    dataset_id = str(dataset_payload["id"])
    release_id = str(release_payload["id"])
    manifest_hash = canonical_json_sha256(manifest)

    # Resolve all catalog and immutable-ID conflicts before touching the
    # repository filesystem. This avoids the most common orphan-release mode.
    cancer = db.get(CancerType, str(dataset_payload["cancer_code"]))
    if cancer is None:
        raise ValueError(
            f"Unknown cancer type {dataset_payload['cancer_code']!r}; "
            "sync the catalog first."
        )
    dataset = db.get(RepositoryDataset, dataset_id)
    if dataset is not None and dataset.cancer_code != cancer.code:
        raise ValueError(
            f"Dataset {dataset_id!r} is already registered for cancer "
            f"{dataset.cancer_code!r}, not {cancer.code!r}."
        )
    existing_release = db.get(RepositoryRelease, release_id)
    if existing_release is not None:
        if existing_release.dataset_id != dataset_id:
            raise ValueError(
                f"Release ID {release_id!r} belongs to another dataset."
            )
        if existing_release.manifest_hash != manifest_hash:
            raise ValueError(
                "Release ID already exists with a different manifest."
            )

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
                "Immutable release path already exists with different "
                f"content: {destination}"
            )

    temporary: Path | None = None
    installed_destination = False
    try:
        if not destination.exists():
            destination.parent.mkdir(parents=True, exist_ok=True)
            temporary = (
                destination.parent / f".promoting-{uuid.uuid4().hex}"
            )
            shutil.copytree(bundle_dir, temporary)
            copied_manifest = load_manifest(temporary)
            if canonical_json_sha256(copied_manifest) != manifest_hash:
                raise ValueError(
                    "The staged release manifest changed during promotion."
                )
            os.replace(temporary, destination)
            temporary = None
            installed_destination = True

        if dataset is None:
            dataset = RepositoryDataset(
                id=dataset_id, cancer_code=cancer.code
            )
            db.add(dataset)
        _assign_dataset(dataset, dataset_payload)

        if existing_release is not None:
            _rebase_release_storage_paths(
                db,
                existing_release,
                destination,
                manifest,
            )
            dataset.active_release_id = existing_release.id
            dataset.status = "available"
            _register_data_source(
                db, dataset, existing_release, manifest
            )
            db.flush()
            summary = _promotion_summary(dataset, existing_release)
            db.commit()
            return summary

        release = RepositoryRelease(
            id=release_id,
            dataset_id=dataset_id,
            version=str(release_payload["version"]),
            status="published",
            manifest_hash=manifest_hash,
            manifest_path=str(destination / "manifest.json"),
            repository_path=str(destination),
            source_snapshot=str(release_payload["source_snapshot"]),
            source_retrieved_at=_parse_datetime(
                release_payload.get("retrieved_at")
            ),
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
        _import_release_rows(
            db, release, destination, manifest, validation["qc"]
        )

        dataset.active_release_id = release.id
        dataset.status = "available"
        cancer.coverage_status = "available"
        cancer.coverage_metadata = {
            **(cancer.coverage_metadata or {}),
            "status": "available",
            "active_dataset_id": dataset.id,
            "active_release_id": release.id,
        }
        _register_data_source(db, dataset, release, manifest)
        # Force database constraints before committing the release path as the
        # published state. A failed flush or commit rolls back rows and removes
        # only the destination installed by this call.
        db.flush()
        summary = _promotion_summary(dataset, release)
        db.commit()
        return summary
    except Exception:
        db.rollback()
        if installed_destination and destination.exists():
            shutil.rmtree(destination)
        raise
    finally:
        if temporary is not None and temporary.exists():
            shutil.rmtree(temporary)


def revalidate_active_releases(
    db: Session, repository_root: Path
) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    datasets = db.scalars(
        select(RepositoryDataset)
        .where(RepositoryDataset.active_release_id.is_not(None))
        .where(RepositoryDataset.visibility == "public")
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
        release_path = resolve_repository_release_path(
            repository_root,
            dataset_id=dataset.id,
            release_id=release.id,
            stored_path=release.repository_path,
        )
        stored_path_rebased = (
            release.repository_path != str(release_path)
            or release.manifest_path
            != str(release_path / "manifest.json")
        )
        validation = validate_bundle(release_path)
        manifest = validation["manifest"]
        if stored_path_rebased:
            _rebase_release_storage_paths(
                db,
                release,
                release_path,
                manifest,
            )
            _register_data_source(db, dataset, release, manifest)
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
                "storage_path_rebased": stored_path_rebased,
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
        "independence_status",
        "license_id",
        "license_url",
    ):
        setattr(dataset, field, payload.get(field))
    dataset.organism = payload.get("organism") or "Homo sapiens"
    dataset.assay = payload.get("assay") or "bulk_rna_seq"
    dataset.redistribution_allowed = bool(
        payload.get("redistribution_allowed", False)
    )
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

    for raw in manifest.get("endpoints") or []:
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
                reason=(
                    None
                    if endpoint_qc["available"]
                    else endpoint_qc_failure_reason(endpoint_qc)
                ),
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
    manifest: dict[str, Any],
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
                file_count=len((manifest.get("checksums") or {})),
                manifest_path=release.manifest_path,
                metadata_json={"release_id": release.id},
            )
        )
    else:
        existing.status = "ready"
        existing.data_release = release.version
        existing.file_count = len(
            (manifest.get("checksums") or {})
        )
        existing.manifest_path = release.manifest_path
        existing.metadata_json = {"release_id": release.id}


def _rebase_release_storage_paths(
    db: Session,
    release: RepositoryRelease,
    destination: Path,
    manifest: dict[str, Any],
) -> None:
    """Point an immutable release at its current repository mount."""
    release.repository_path = str(destination)
    release.manifest_path = str(destination / "manifest.json")
    layers = {
        layer.layer_id: layer
        for layer in db.scalars(
            select(RepositoryExpressionLayer).where(
                RepositoryExpressionLayer.release_id == release.id
            )
        ).all()
    }
    for raw in manifest["expression_layers"]:
        layer_id = str(raw["layer_id"])
        layer = layers.get(layer_id)
        if layer is None:
            raise ValueError(
                f"Published release {release.id} is missing layer {layer_id}."
            )
        layer.matrix_path = str(
            safe_bundle_path(destination, str(raw["matrix_file"]))
        )
        layer.metadata_path = str(
            safe_bundle_path(destination, str(raw["metadata_file"]))
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
