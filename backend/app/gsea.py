from __future__ import annotations

from array import array
from bisect import bisect_left, bisect_right
import csv
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from html import escape
import json
import math
from pathlib import Path
import random
import statistics
import subprocess
import sys
import time
from types import SimpleNamespace
from typing import Any, Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.expression import (
    ensure_gdc_expression_matrix_cache,
    load_gdc_expression_matrix_metadata,
)
from app.models import AnalysisJob, RepositoryGene, Sample
from app.repository.service import (
    RepositoryContext,
    repository_expression_layer_paths,
    repository_samples,
    resolve_expression_layer,
)
from app.repository.storage import read_matrix_metadata
from app.sample_population import (
    POPULATIONS,
    count_sample_types,
    resolve_tcga_sample_population,
    sample_matches_population,
)
from app.schemas import AnalysisFilters, GseaGroupingDefinition
from app.survival import assign_groups_with_cutpoint, percentile, sample_selection_key


GSEA_AUDIT_SCHEMA = "tcga-trace-camera-preranked-gsea-audit-v2"
GSEA_RESULT_SCHEMA = "tcga-trace-camera-preranked-gsea-result-v2"
CAMERA_ENGINE_SCHEMA = "trace-camera-gene-set-test-v1"
CAMERA_LIMMA_VERSION = "3.62.2"
# genes × samples passed to the pinned limma CAMERA engine. 100 M float64 entries is ~0.8 GB in R, within the 6 GB
# worker; it admits a whole-transcriptome TCGA-BRCA contrast (~60k genes × ~1.1k patients).
CAMERA_MAX_MATRIX_ENTRIES = 100_000_000
CAMERA_MAX_MATRIX_ENTRIES_LABEL = f"{CAMERA_MAX_MATRIX_ENTRIES // 1_000_000} million"
GSEA_DOTPLOT_MAX_PATHWAYS = 30
GSEA_DOTPLOT_NEG_LOG10_FDR_CAP = 10.0
MIN_GROUP_SAMPLES = 5
MIN_GENE_SAMPLES_PER_GROUP = 3
SUPPORTED_SURVIVAL_GROUPING_METHODS = {
    "maxstat",
    "median",
    "upper_quartile",
    "upper_lower_quartile",
    "percentile",
}


@dataclass(frozen=True)
class MatrixGene:
    symbol: str
    row_number: int


@dataclass(frozen=True)
class ExpressionMatrix:
    path: Path
    sample_ids: list[str]
    genes: list[MatrixGene]
    dtype: str
    byte_order: str
    expression_scale: str
    expression_scale_label: str
    source_sha256: str | None


@dataclass(frozen=True)
class CameraExpressionMatrix:
    path: Path
    sample_ids: list[str]
    groups: list[str]
    genes: list[str]
    dtype: str = "float32"
    byte_order: str = "little"


def _sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def _stable_hash(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def _safe_collection_path(root: Path, relative: str) -> Path:
    if not relative or Path(relative).is_absolute():
        raise ValueError("Gene-set collection paths must be relative.")
    resolved_root = root.resolve()
    candidate = (root / relative).resolve()
    if candidate != resolved_root and resolved_root not in candidate.parents:
        raise ValueError("Gene-set collection path escapes its configured root.")
    return candidate


def load_gene_set_catalog(root: Path) -> list[dict[str, Any]]:
    manifest_path = root / "collections.json"
    if not manifest_path.is_file():
        return []
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    collections = payload.get("collections") or []
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in collections:
        collection_id = str(raw.get("id") or "").strip().lower()
        if not collection_id or collection_id in seen:
            raise ValueError("Gene-set collection IDs must be non-empty and unique.")
        seen.add(collection_id)
        path = _safe_collection_path(root, str(raw.get("file") or ""))
        available = path.is_file()
        actual_sha256 = _sha256_file(path) if available else None
        expected_sha256 = str(raw.get("sha256") or "").strip().lower()
        if available and expected_sha256 and actual_sha256 != expected_sha256:
            raise ValueError(
                f"Gene-set collection {collection_id} failed its SHA-256 check."
            )
        result.append(
            {
                "id": collection_id,
                "label": str(raw.get("label") or collection_id),
                "version": str(raw.get("version") or "unversioned"),
                "species": str(raw.get("species") or "Homo sapiens"),
                "identifier_type": str(
                    raw.get("identifier_type") or "HGNC symbol"
                ),
                "source": str(raw.get("source") or ""),
                "source_url": str(raw.get("source_url") or ""),
                "license": str(raw.get("license") or ""),
                "license_url": str(raw.get("license_url") or ""),
                "release_doi": str(raw.get("release_doi") or ""),
                "attribution": str(raw.get("attribution") or ""),
                "source_artifacts": raw.get("source_artifacts") or [],
                "generation": raw.get("generation") or {},
                "file": path,
                "sha256": actual_sha256,
                "available": available,
                "gene_set_count": _count_gmt_sets(path) if available else 0,
            }
        )
    return result


def public_gene_set_catalog(root: Path) -> list[dict[str, Any]]:
    return [
        {
            key: value
            for key, value in item.items()
            if key != "file"
        }
        for item in load_gene_set_catalog(root)
    ]


def resolve_gene_set_collection(root: Path, collection_id: str) -> dict[str, Any]:
    normalized = collection_id.strip().lower()
    collection = next(
        (
            item
            for item in load_gene_set_catalog(root)
            if item["id"] == normalized
        ),
        None,
    )
    if collection is None:
        raise ValueError(f"Unknown gene-set collection: {collection_id}.")
    if not collection["available"]:
        raise ValueError(
            f"Gene-set collection {collection_id} is configured but unavailable."
        )
    return collection


def _count_gmt_sets(path: Path) -> int:
    with path.open(encoding="utf-8", errors="replace") as handle:
        return sum(1 for line in handle if line.strip() and not line.startswith("#"))


def read_gmt(path: Path) -> list[dict[str, Any]]:
    pathways: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    with path.open(encoding="utf-8", errors="replace") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip() or line.startswith("#"):
                continue
            fields = line.rstrip("\r\n").split("\t")
            if len(fields) < 3:
                raise ValueError(
                    f"Invalid GMT row {line_number}: expected a name, description and genes."
                )
            name = fields[0].strip()
            if not name or name in seen_names:
                raise ValueError(
                    f"GMT pathway names must be non-empty and unique; invalid row {line_number}."
                )
            seen_names.add(name)
            genes = list(
                dict.fromkeys(
                    gene.strip().upper()
                    for gene in fields[2:]
                    if gene.strip()
                )
            )
            if not genes:
                continue
            pathways.append(
                {
                    "name": name,
                    "description": fields[1].strip(),
                    "genes": genes,
                }
            )
    if not pathways:
        raise ValueError("The selected GMT collection contains no usable pathways.")
    return pathways


def resolve_expression_matrix(
    db: Session,
    settings: Settings,
    *,
    cohort: str,
    expression_scale: str,
    expression_layer_id: str | None,
    repository_context: RepositoryContext | None,
) -> ExpressionMatrix:
    if repository_context is not None:
        layer = resolve_expression_layer(
            db,
            repository_context,
            expression_layer_id,
        )
        matrix_path, metadata_path = repository_expression_layer_paths(
            repository_context, layer
        )
        metadata = read_matrix_metadata(metadata_path)
        genes = [
            MatrixGene(symbol=row.gene_symbol, row_number=int(row.row_number))
            for row in db.scalars(
                select(RepositoryGene)
                .where(RepositoryGene.expression_layer_id == layer.id)
                .order_by(RepositoryGene.row_number, RepositoryGene.gene_symbol)
            ).all()
        ]
        if not genes:
            raise ValueError(
                f"Expression layer {layer.layer_id} contains no indexed genes."
            )
        return ExpressionMatrix(
            path=matrix_path,
            sample_ids=list(metadata["sample_ids"]),
            genes=genes,
            dtype="float32",
            byte_order="little",
            expression_scale=layer.layer_id,
            expression_scale_label=layer.label,
            source_sha256=layer.matrix_sha256,
        )

    ensure_gdc_expression_matrix_cache(
        settings.tcga_data_dir,
        settings.derived_expression_dir,
        cohort,
    )
    metadata = load_gdc_expression_matrix_metadata(
        settings.derived_expression_dir,
        cohort,
    )
    if not metadata:
        raise ValueError(f"The broad expression matrix for {cohort} is unavailable.")
    scale = (metadata.get("scales") or {}).get(expression_scale)
    if scale is None:
        available = ", ".join(sorted((metadata.get("scales") or {}).keys()))
        raise ValueError(
            f"GSEA requires a materialized broad expression matrix. "
            f"{expression_scale} is unavailable for {cohort}; available scales: {available}."
        )
    genes = [
        MatrixGene(symbol=str(symbol).upper(), row_number=index)
        for index, symbol in enumerate(metadata.get("genes") or [])
    ]
    matrix_path = (
        settings.derived_expression_dir
        / "matrices"
        / cohort
        / str(scale["file"])
    )
    return ExpressionMatrix(
        path=matrix_path,
        sample_ids=list(metadata.get("barcodes") or []),
        genes=genes,
        dtype="float32",
        byte_order="native",
        expression_scale=expression_scale,
        expression_scale_label={
            "log2_tpm": "log2(TPM + 1)",
            "log2_fpkm": "log2(FPKM + 1)",
            "log2_fpkm_uq": "log2(FPKM-UQ + 1)",
        }.get(expression_scale, expression_scale),
        source_sha256=_sha256_file(matrix_path),
    )


def dataset_samples(
    db: Session,
    *,
    cohort: str,
    repository_context: RepositoryContext | None,
) -> list[Any]:
    if repository_context is not None:
        return repository_samples(db, repository_context)
    return list(
        db.scalars(select(Sample).where(Sample.cohort == cohort)).all()
    )


def select_gsea_samples(
    samples: list[Any],
    filters: AnalysisFilters,
    matrix_sample_ids: Iterable[str],
    *,
    analysis_context: str = "gsea",
    selection_rule: str = "tcga",
    clinical_filter_cohort: str | None = None,
    clinical_filter_tcga_data_dir: Path | None = None,
    clinical_filter_tcga_cdr_path: Path | None = None,
    clinical_filter_repository: bool | None = None,
) -> tuple[list[Any], dict[str, Any], list[str]]:
    input_count = len(samples)
    is_tcga = selection_rule == "tcga"
    population: dict[str, Any] | None = None
    population_excluded: list[Any] = []
    population_selected = list(samples)
    if is_tcga:
        cohort_ids = {
            str(getattr(sample, "cohort", "") or "").strip()
            for sample in samples
            if str(getattr(sample, "cohort", "") or "").strip()
        }
        if len(cohort_ids) != 1:
            raise ValueError(
                "TCGA sample selection requires exactly one cohort at a time."
            )
        cohort = next(iter(cohort_ids))
        policy, population = resolve_tcga_sample_population(
            cohort,
            getattr(filters, "sample_population", None),
            getattr(filters, "sample_types", []) or [],
        )
        if getattr(filters, "sample_types", None):
            requested_types = {
                value.strip().casefold()
                for value in filters.sample_types
                if value.strip()
            }
            allowed_types = {
                value.casefold() for value in policy.allowed_sample_types
            }
            if not requested_types.issubset(allowed_types):
                raise ValueError(
                    "Sample type filters cannot expand or cross the declared "
                    "molecular population."
                )
        population_excluded = [
            sample
            for sample in samples
            if not sample_matches_population(sample, policy)
        ]
        population_selected = [
            sample for sample in samples if sample_matches_population(sample, policy)
        ]
    allowed_barcodes = set(matrix_sample_ids)
    selected = [
        sample
        for sample in population_selected
        if sample.barcode in allowed_barcodes
    ]
    matrix_matched_count = len(selected)

    if filters.sample_types and not is_tcga:
        allowed = set(filters.sample_types)
        selected = [
            sample for sample in selected if sample.sample_type in allowed
        ]
    if filters.stages:
        allowed = set(filters.stages)
        selected = [sample for sample in selected if sample.stage in allowed]
    if filters.grades:
        allowed = set(filters.grades)
        selected = [sample for sample in selected if sample.grade in allowed]
    if filters.genders:
        allowed = {value.casefold() for value in filters.genders}
        selected = [
            sample
            for sample in selected
            if sample.gender and sample.gender.casefold() in allowed
        ]
    if filters.races:
        allowed = {value.casefold() for value in filters.races}
        selected = [
            sample
            for sample in selected
            if sample.race and sample.race.casefold() in allowed
        ]
    if filters.age_min is not None:
        selected = [
            sample
            for sample in selected
            if sample.age_at_index is not None
            and sample.age_at_index >= filters.age_min
        ]
    if filters.age_max is not None:
        selected = [
            sample
            for sample in selected
            if sample.age_at_index is not None
            and sample.age_at_index <= filters.age_max
        ]
    warnings: list[str] = []
    custom_filter_audit: list[dict[str, Any]] = []
    custom_filters = list(getattr(filters, "custom_filters", []) or [])
    if custom_filters:
        from app.clinical_grouping import apply_custom_clinical_filters

        selected, custom_filter_audit, custom_warnings = (
            apply_custom_clinical_filters(
                selected,
                custom_filters,
                analysis_context=analysis_context,
                cohort=clinical_filter_cohort or (
                    cohort if is_tcga else None
                ),
                tcga_data_dir=clinical_filter_tcga_data_dir,
                tcga_cdr_path=clinical_filter_tcga_cdr_path,
                repository=(
                    clinical_filter_repository
                    if clinical_filter_repository is not None
                    else not is_tcga
                ),
            )
        )
        warnings.extend(custom_warnings)

    after_filters = len(selected)
    retained_by_patient: dict[str, Any] = {}
    for sample in sorted(selected, key=sample_selection_key):
        retained_by_patient.setdefault(sample.patient_id, sample)
    retained = list(retained_by_patient.values())
    if is_tcga:
        population_policy = POPULATIONS.get(str((population or {}).get("id") or ""))
        if population_policy is None or any(
            not sample_matches_population(sample, population_policy)
            for sample in retained
        ):
            raise RuntimeError(
                "TCGA molecular-population invariant failed during grouped-expression selection."
            )
    duplicate_count = after_filters - len(retained)
    if duplicate_count:
        warnings.append(
            f"{duplicate_count} additional eligible samples were removed so each patient contributes once."
        )
    if filters.max_time_days is not None:
        warnings.append(
            "Maximum follow-up is not applied to GSEA because clinical and expression grouping do not use event time."
        )
    return (
        retained,
        {
            "input_samples": input_count,
            "sample_population": population,
            "population_filter_applied": is_tcga,
            "population_excluded_samples": len(population_excluded),
            "population_excluded_sample_types": count_sample_types(
                population_excluded
            ),
            "matrix_matched_samples": matrix_matched_count,
            "after_clinical_filters": after_filters,
            "retained_patients": len(retained),
            "duplicate_samples_removed": duplicate_count,
            "retained_sample_types": count_sample_types(retained),
            "custom_clinical_filters": custom_filter_audit,
            "custom_clinical_filter_count": len(custom_filter_audit),
            "custom_clinical_automatic_cox_adjustment": False,
            "selection_rule": (
                "declared molecular population, clinical filters, matrix availability, "
                "then one deterministic sample per patient without cross-population fallback"
                if is_tcga
                else "release eligibility, clinical filters, matrix availability, then "
                "one sample per patient using the curated release selection rule"
            ),
        },
        warnings,
    )


def clinical_group_assignments(
    samples: list[Any],
    grouping: GseaGroupingDefinition,
    *,
    variable_values: dict[str, str | float | None] | None = None,
    variable_definition: dict[str, Any] | None = None,
) -> tuple[dict[str, str], dict[str, Any]]:
    variable = grouping.clinical_variable
    if variable is None:
        raise ValueError("Clinical grouping requires a variable.")
    assignments: dict[str, str] = {}
    details: dict[str, Any] = {
        "source": "clinical",
        "variable": variable,
        "contrast": "group_b_minus_group_a",
        "group_a_label": grouping.group_a_label,
        "group_b_label": grouping.group_b_label,
    }
    if variable_definition:
        details.update(
            {
                "variable_label": variable_definition.get("label"),
                "variable_type": variable_definition.get("value_type"),
                "variable_source": variable_definition.get("source"),
                "variable_source_field": variable_definition.get("source_field"),
                "catalog_version": variable_definition.get("catalog_version"),
                "variable_provenance": variable_definition.get("provenance"),
                "non_missing_patients": variable_definition.get(
                    "non_missing_count"
                ),
                "missing_patients": variable_definition.get("missing_count"),
                "expression_derived_grouping": bool(
                    variable_definition.get("expression_derived")
                ),
            }
        )
    numeric_variable = (
        variable_definition is not None
        and variable_definition.get("value_type") == "numeric"
    ) or variable == "age_at_index"
    if numeric_variable:
        numeric_values: dict[str, float] = {}
        for sample in samples:
            raw = (
                variable_values.get(str(sample.barcode))
                if variable_values is not None
                else getattr(sample, variable, None)
            )
            if raw is None:
                continue
            try:
                numeric = float(raw)
            except (TypeError, ValueError):
                continue
            if math.isfinite(numeric):
                numeric_values[str(sample.barcode)] = numeric
        observed = list(numeric_values.values())
        if not observed:
            raise ValueError(
                f"No finite values remain for {details.get('variable_label') or variable}."
            )
        threshold = (
            statistics.median(observed)
            if grouping.clinical_cutpoint_method == "median"
            else float(grouping.clinical_cutpoint)
        )
        for sample in samples:
            value = numeric_values.get(str(sample.barcode))
            if value is None:
                continue
            assignments[sample.barcode] = "a" if value <= threshold else "b"
        field_label = details.get("variable_label") or variable
        details.update(
            {
                "cutpoint_method": grouping.clinical_cutpoint_method,
                "threshold": threshold,
                "group_a_definition": f"{field_label} <= {threshold:.6g}",
                "group_b_definition": f"{field_label} > {threshold:.6g}",
            }
        )
        return assignments, details

    values_a = {value.casefold() for value in grouping.group_a_values}
    values_b = {value.casefold() for value in grouping.group_b_values}
    for sample in samples:
        raw = (
            variable_values.get(str(sample.barcode))
            if variable_values is not None
            else getattr(sample, variable, None)
        )
        if raw is None:
            continue
        normalized = str(raw).strip().casefold()
        if normalized in values_a:
            assignments[sample.barcode] = "a"
        elif normalized in values_b:
            assignments[sample.barcode] = "b"
    details.update(
        {
            "group_a_values": grouping.group_a_values,
            "group_b_values": grouping.group_b_values,
            "group_a_definition": ", ".join(grouping.group_a_values),
            "group_b_definition": ", ".join(grouping.group_b_values),
        }
    )
    return assignments, details


def expression_group_assignments(
    samples: list[Any],
    scores: dict[str, float],
    grouping: GseaGroupingDefinition,
) -> tuple[dict[str, str], dict[str, Any]]:
    complete = [
        sample
        for sample in samples
        if sample.barcode in scores and math.isfinite(float(scores[sample.barcode]))
    ]
    values = [float(scores[sample.barcode]) for sample in complete]
    labels, levels, cutpoint = assign_groups_with_cutpoint(
        values,
        grouping.cutpoint_method,
        grouping.custom_percentile,
    )
    if len(levels) != 2:
        raise ValueError("Expression-derived GSEA grouping must produce two groups.")
    low_level, high_level = levels[0], levels[1]
    assignments: dict[str, str] = {}
    for sample, source_label in zip(complete, labels, strict=True):
        if source_label is None:
            continue
        assignments[sample.barcode] = (
            "a" if source_label == low_level else "b"
        )
    signature = grouping.signature
    return assignments, {
        "source": "expression",
        "contrast": "group_b_minus_group_a",
        "group_a_label": grouping.group_a_label,
        "group_b_label": grouping.group_b_label,
        "group_a_source_level": low_level,
        "group_b_source_level": high_level,
        "signature": (
            signature.model_dump(mode="json") if signature is not None else None
        ),
        "cutpoint": cutpoint,
        "circularity_notice": (
            "Groups were derived from the same expression matrix used for ranking. "
            "This GSEA is descriptive and is not an independent inferential validation."
        ),
    }


def survival_group_assignments(
    db: Session,
    *,
    cohort: str,
    dataset_id: str | None,
    dataset_release_id: str | None,
    grouping: GseaGroupingDefinition,
) -> tuple[dict[str, str], dict[str, Any], list[dict[str, str]]]:
    analysis_id = str(grouping.survival_analysis_id or "")
    job = db.get(AnalysisJob, analysis_id)
    if job is None:
        raise ValueError(f"Source survival analysis {analysis_id!r} was not found.")
    if job.status != "completed":
        raise ValueError(
            f"Source survival analysis {analysis_id!r} is not completed."
        )
    if job.cohort != cohort:
        raise ValueError(
            "The source survival analysis belongs to a different cohort."
        )
    if (job.dataset_id or None) != (dataset_id or None) or (
        job.dataset_release_id or None
    ) != (dataset_release_id or None):
        raise ValueError(
            "The source survival analysis belongs to a different dataset release."
        )
    if job.cutpoint_method not in SUPPORTED_SURVIVAL_GROUPING_METHODS:
        raise ValueError(
            "The source survival analysis does not contain an eligible two-group dichotomization."
        )
    if not job.csv_path or not Path(job.csv_path).is_file():
        raise ValueError(
            "The exact patient groups for the source survival analysis have expired or are unavailable."
        )

    rows: list[dict[str, str]] = []
    with Path(job.csv_path).open(
        newline="",
        encoding="utf-8",
        errors="replace",
    ) as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            barcode = str(row.get("sample_barcode") or "").strip()
            patient_id = str(row.get("patient_id") or "").strip()
            group = str(row.get("group") or "").strip()
            if barcode and group:
                rows.append(
                    {
                        "sample_barcode": barcode,
                        "patient_id": patient_id,
                        "source_group": group,
                    }
                )
    present = list(dict.fromkeys(row["source_group"] for row in rows))
    if len(present) != 2:
        raise ValueError(
            "The source survival analysis does not contain exactly two observed groups."
        )

    source_population: dict[str, Any] | None = None
    if dataset_id is None:
        source_filters = (job.request_payload or {}).get("filters") or {}
        policy, source_population = resolve_tcga_sample_population(
            cohort,
            source_filters.get("sample_population"),
            source_filters.get("sample_types") or [],
        )
        population_violations = [
            row["sample_barcode"]
            for row in rows
            if not sample_matches_population(
                SimpleNamespace(
                    barcode=row["sample_barcode"],
                    sample_type=None,
                ),
                policy,
            )
        ]
        if population_violations:
            raise ValueError(
                "The source survival analysis contains sample barcodes outside "
                "its declared molecular population. Repeat the survival analysis "
                "under the current sample-population contract before reusing its groups."
            )

    requested_a = (
        grouping.group_a_values[0] if grouping.group_a_values else None
    )
    requested_b = (
        grouping.group_b_values[0] if grouping.group_b_values else None
    )
    if requested_a or requested_b:
        if not requested_a or not requested_b:
            raise ValueError(
                "Both source survival group values must be selected together."
            )
        canonical = {value.casefold(): value for value in present}
        source_a = canonical.get(requested_a.casefold())
        source_b = canonical.get(requested_b.casefold())
        if source_a is None or source_b is None or source_a == source_b:
            raise ValueError(
                "Selected survival group values do not match the source analysis."
            )
    else:
        high = next(
            (value for value in present if value.casefold() == "high"),
            None,
        )
        if high is not None:
            source_b = high
            source_a = next(value for value in present if value != high)
        else:
            source_a, source_b = present

    assignments = {
        row["sample_barcode"]: (
            "a" if row["source_group"] == source_a else "b"
        )
        for row in rows
        if row["source_group"] in {source_a, source_b}
    }
    circular = job.cutpoint_method == "maxstat"
    return (
        assignments,
        {
            "source": "survival",
            "source_analysis_id": job.id,
            "source_cutpoint_method": job.cutpoint_method,
            "source_request_sha256": _stable_hash(job.request_payload or {}),
            "sample_population": source_population,
            "source_group_a": source_a,
            "source_group_b": source_b,
            "group_a_label": grouping.group_a_label,
            "group_b_label": grouping.group_b_label,
            "contrast": "group_b_minus_group_a",
            "circularity_notice": (
                "The inherited maxstat groups were optimized against a survival endpoint. "
                "Downstream GSEA is exploratory and outcome-informed."
                if circular
                else None
            ),
        },
        rows,
    )


def validate_group_assignments(
    assignments: dict[str, str],
    *,
    available_sample_ids: Iterable[str],
) -> dict[str, int]:
    available = set(available_sample_ids)
    counts = {
        "a": sum(
            1
            for barcode, group in assignments.items()
            if barcode in available and group == "a"
        ),
        "b": sum(
            1
            for barcode, group in assignments.items()
            if barcode in available and group == "b"
        ),
    }
    small = {
        group: count
        for group, count in counts.items()
        if count < MIN_GROUP_SAMPLES
    }
    if small:
        raise ValueError(
            "GSEA requires at least "
            f"{MIN_GROUP_SAMPLES} patients in each group; observed {counts}."
        )
    return counts


def _rank_expression_matrix(
    matrix: ExpressionMatrix,
    assignments: dict[str, str],
    *,
    ranking_metric: str,
    camera_matrix_path: Path | None = None,
) -> tuple[
    list[dict[str, Any]],
    dict[str, Any],
    CameraExpressionMatrix | None,
]:
    if ranking_metric not in {"welch_t", "signal_to_noise"}:
        raise ValueError(f"Unsupported GSEA ranking metric: {ranking_metric}.")
    group_a_indices = [
        index
        for index, sample_id in enumerate(matrix.sample_ids)
        if assignments.get(sample_id) == "a"
    ]
    group_b_indices = [
        index
        for index, sample_id in enumerate(matrix.sample_ids)
        if assignments.get(sample_id) == "b"
    ]
    analysis_indices = [
        index
        for index, sample_id in enumerate(matrix.sample_ids)
        if assignments.get(sample_id) in {"a", "b"}
    ]
    analysis_sample_ids = [matrix.sample_ids[index] for index in analysis_indices]
    analysis_groups = [
        str(assignments[matrix.sample_ids[index]]) for index in analysis_indices
    ]
    sample_count = len(matrix.sample_ids)
    item_size = array("f").itemsize
    ranked: list[dict[str, Any]] = []
    camera_genes: list[str] = []
    excluded = {
        "insufficient_finite_values": 0,
        "zero_within_group_variance": 0,
        "nonfinite_statistic": 0,
    }
    if camera_matrix_path is not None:
        excluded["incomplete_selected_samples"] = 0
    seen_genes: set[str] = set()

    camera_handle = (
        camera_matrix_path.open("xb") if camera_matrix_path is not None else None
    )
    try:
        matrix_handle = matrix.path.open("rb")
        with matrix_handle as handle:
            for gene in matrix.genes:
                symbol = gene.symbol.strip().upper()
                if not symbol or symbol in seen_genes:
                    continue
                seen_genes.add(symbol)
                values = array("f")
                handle.seek(gene.row_number * sample_count * item_size)
                values.fromfile(handle, sample_count)
                if matrix.byte_order == "little" and sys.byteorder != "little":
                    values.byteswap()
                if len(values) != sample_count:
                    raise ValueError(
                        f"Expression row {gene.row_number} is truncated in {matrix.path}."
                    )
                analysis_values = [float(values[index]) for index in analysis_indices]
                if camera_handle is not None and any(
                    not math.isfinite(value) for value in analysis_values
                ):
                    excluded["incomplete_selected_samples"] += 1
                    continue
                values_a = [
                    float(values[index])
                    for index in group_a_indices
                    if math.isfinite(float(values[index]))
                ]
                values_b = [
                    float(values[index])
                    for index in group_b_indices
                    if math.isfinite(float(values[index]))
                ]
                if (
                    len(values_a) < MIN_GENE_SAMPLES_PER_GROUP
                    or len(values_b) < MIN_GENE_SAMPLES_PER_GROUP
                ):
                    excluded["insufficient_finite_values"] += 1
                    continue
                mean_a = statistics.fmean(values_a)
                mean_b = statistics.fmean(values_b)
                variance_a = statistics.variance(values_a)
                variance_b = statistics.variance(values_b)
                if variance_a <= 0 and variance_b <= 0:
                    excluded["zero_within_group_variance"] += 1
                    continue
                if ranking_metric == "welch_t":
                    denominator = math.sqrt(
                        variance_a / len(values_a)
                        + variance_b / len(values_b)
                    )
                else:
                    denominator = math.sqrt(variance_a) + math.sqrt(variance_b)
                if denominator <= 0:
                    excluded["zero_within_group_variance"] += 1
                    continue
                score = (mean_b - mean_a) / denominator
                if not math.isfinite(score):
                    excluded["nonfinite_statistic"] += 1
                    continue
                if camera_handle is not None:
                    camera_values = array("f", analysis_values)
                    if sys.byteorder != "little":
                        camera_values.byteswap()
                    camera_handle.write(camera_values.tobytes())
                    camera_genes.append(symbol)
                ranked.append(
                    {
                        "gene": symbol,
                        "score": score,
                        "mean_group_a": mean_a,
                        "mean_group_b": mean_b,
                        "difference_b_minus_a": mean_b - mean_a,
                        "n_group_a": len(values_a),
                        "n_group_b": len(values_b),
                    }
                )
    finally:
        if camera_handle is not None:
            camera_handle.close()

    ranked.sort(key=lambda row: (-row["score"], row["gene"]))
    for index, row in enumerate(ranked, start=1):
        row["rank"] = index
    tie_count = sum(
        1
        for previous, current in zip(ranked, ranked[1:], strict=False)
        if previous["score"] == current["score"]
    )
    metadata = {
        "metric": ranking_metric,
        "contrast": "group_b_minus_group_a",
        "positive_scores_favor": "group_b",
        "negative_scores_favor": "group_a",
        "genes_in_matrix_index": len(matrix.genes),
        "genes_ranked": len(ranked),
        "genes_excluded": sum(excluded.values()),
        "exclusions": excluded,
        "adjacent_ties": tie_count,
        "tie_breaker": "HGNC symbol ascending",
        "minimum_finite_samples_per_group": MIN_GENE_SAMPLES_PER_GROUP,
        "complete_case_genes_for_pathway_analysis": camera_handle is not None,
    }
    camera_matrix = None
    if camera_matrix_path is not None:
        if camera_matrix_path.stat().st_size != (
            len(camera_genes) * len(analysis_sample_ids) * item_size
        ):
            raise RuntimeError("The temporary CAMERA matrix has an invalid size.")
        if len(camera_genes) * len(analysis_sample_ids) > CAMERA_MAX_MATRIX_ENTRIES:
            raise ValueError(
                f"Correlation-aware pathway testing exceeds the {CAMERA_MAX_MATRIX_ENTRIES_LABEL} "
                "matrix-entry limit after complete-case gene filtering."
            )
        camera_matrix = CameraExpressionMatrix(
            path=camera_matrix_path,
            sample_ids=analysis_sample_ids,
            groups=analysis_groups,
            genes=camera_genes,
        )
    return ranked, metadata, camera_matrix


def rank_expression_matrix(
    matrix: ExpressionMatrix,
    assignments: dict[str, str],
    *,
    ranking_metric: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    ranked, metadata, _ = _rank_expression_matrix(
        matrix,
        assignments,
        ranking_metric=ranking_metric,
    )
    return ranked, metadata


def prepare_camera_expression_matrix(
    matrix: ExpressionMatrix,
    assignments: dict[str, str],
    *,
    ranking_metric: str,
    camera_matrix_path: Path,
) -> tuple[list[dict[str, Any]], dict[str, Any], CameraExpressionMatrix]:
    ranked, metadata, camera_matrix = _rank_expression_matrix(
        matrix,
        assignments,
        ranking_metric=ranking_metric,
        camera_matrix_path=camera_matrix_path,
    )
    if camera_matrix is None:
        raise RuntimeError("The temporary CAMERA matrix was not prepared.")
    return ranked, metadata, camera_matrix


def _enrichment_score_from_positions(
    scores: list[float],
    positions: list[int],
) -> tuple[float, int]:
    gene_count = len(scores)
    set_size = len(positions)
    if set_size == 0 or set_size >= gene_count:
        return 0.0, 0
    hit_weights = [abs(scores[position]) for position in positions]
    hit_total = sum(hit_weights)
    if hit_total <= 0:
        hit_weights = [1.0] * set_size
        hit_total = float(set_size)
    miss_penalty = 1.0 / (gene_count - set_size)
    running = 0.0
    maximum = 0.0
    minimum = 0.0
    maximum_position = 0
    minimum_position = 0
    previous = -1
    for position, weight in zip(positions, hit_weights, strict=True):
        misses = position - previous - 1
        if misses:
            running -= misses * miss_penalty
            if running < minimum:
                minimum = running
                minimum_position = position - 1
        running += weight / hit_total
        if running > maximum:
            maximum = running
            maximum_position = position
        if running < minimum:
            minimum = running
            minimum_position = position
        previous = position
    trailing = gene_count - previous - 1
    if trailing:
        running -= trailing * miss_penalty
        if running < minimum:
            minimum = running
            minimum_position = gene_count - 1
    if abs(maximum) >= abs(minimum):
        return maximum, maximum_position
    return minimum, minimum_position


def _benjamini_hochberg(p_values: list[float]) -> list[float]:
    if not p_values:
        return []
    adjusted = [1.0] * len(p_values)
    ordered = sorted(range(len(p_values)), key=lambda index: p_values[index])
    running = 1.0
    total = len(p_values)
    for rank_index in range(total - 1, -1, -1):
        original_index = ordered[rank_index]
        rank = rank_index + 1
        candidate = min(1.0, p_values[original_index] * total / rank)
        running = min(running, candidate)
        adjusted[original_index] = running
    return adjusted


def run_preranked_gsea(
    ranked_rows: list[dict[str, Any]],
    pathways: list[dict[str, Any]],
    *,
    min_size: int,
    max_size: int,
    permutations: int,
    seed: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    genes = [row["gene"] for row in ranked_rows]
    scores = [float(row["score"]) for row in ranked_rows]
    gene_to_position = {gene: index for index, gene in enumerate(genes)}
    results: list[dict[str, Any]] = []
    null_distributions: dict[int, dict[str, Any]] = {}
    excluded = {
        "below_minimum_overlap": 0,
        "above_maximum_overlap": 0,
        "no_overlap": 0,
    }

    for pathway in pathways:
        original_genes = pathway["genes"]
        positions = sorted(
            gene_to_position[gene]
            for gene in original_genes
            if gene in gene_to_position
        )
        size = len(positions)
        if size == 0:
            excluded["no_overlap"] += 1
            continue
        if size < min_size:
            excluded["below_minimum_overlap"] += 1
            continue
        if size > max_size:
            excluded["above_maximum_overlap"] += 1
            continue
        observed_es, peak_position = _enrichment_score_from_positions(
            scores,
            positions,
        )
        null_distribution = null_distributions.get(size)
        if null_distribution is None:
            size_seed = int.from_bytes(
                sha256(
                    f"{seed}:overlap-size:{size}".encode("utf-8")
                ).digest()[:8],
                "big",
            )
            rng = random.Random(size_seed)
            null_scores = [
                _enrichment_score_from_positions(
                    scores,
                    sorted(rng.sample(range(len(scores)), size)),
                )[0]
                for _ in range(permutations)
            ]
            positive_scores = sorted(
                value for value in null_scores if value >= 0
            )
            negative_scores = sorted(
                value for value in null_scores if value < 0
            )
            absolute_mean = statistics.fmean(
                abs(value) for value in null_scores
            )
            null_distribution = {
                "positive": positive_scores,
                "negative": negative_scores,
                "positive_mean": (
                    statistics.fmean(positive_scores)
                    if positive_scores
                    else absolute_mean
                ),
                "negative_absolute_mean": (
                    statistics.fmean(
                        abs(value) for value in negative_scores
                    )
                    if negative_scores
                    else absolute_mean
                ),
            }
            null_distributions[size] = null_distribution
        if observed_es >= 0:
            same_side = null_distribution["positive"]
            denominator = float(null_distribution["positive_mean"])
            extreme = len(same_side) - bisect_left(
                same_side,
                observed_es,
            )
        else:
            same_side = null_distribution["negative"]
            denominator = float(
                null_distribution["negative_absolute_mean"]
            )
            extreme = bisect_right(same_side, observed_es)
        nominal_p = (extreme + 1) / (len(same_side) + 1)
        nes = observed_es / denominator if denominator > 0 else 0.0
        if observed_es >= 0:
            leading_positions = [
                position for position in positions if position <= peak_position
            ]
            direction = "group_b"
        else:
            leading_positions = [
                position for position in positions if position >= peak_position
            ]
            direction = "group_a"
        results.append(
            {
                "pathway": pathway["name"],
                "description": pathway["description"],
                "size_original": len(original_genes),
                "size_used": size,
                "es": observed_es,
                "nes": nes,
                "p_value": nominal_p,
                "fdr": 1.0,
                "direction": direction,
                "rank_at_max": peak_position + 1,
                "leading_edge": [genes[position] for position in leading_positions],
                "leading_edge_size": len(leading_positions),
            }
        )

    adjusted = _benjamini_hochberg(
        [float(row["p_value"]) for row in results]
    )
    for row, fdr in zip(results, adjusted, strict=True):
        row["fdr"] = fdr
    results.sort(
        key=lambda row: (
            row["fdr"],
            row["p_value"],
            -abs(row["nes"]),
            row["pathway"],
        )
    )
    return results, {
        "pathways_in_collection": len(pathways),
        "pathways_tested": len(results),
        "pathways_excluded": sum(excluded.values()),
        "exclusions": excluded,
        "permutations": permutations,
        "seed": seed,
        "unique_overlap_sizes": len(null_distributions),
        "null_enrichment_scores_generated": (
            len(null_distributions) * permutations
        ),
        "null_distribution_reuse": (
            "one deterministic reference distribution per observed "
            "gene-set overlap size"
        ),
        "algorithm": (
            "weighted preranked GSEA with gene-set permutations conditional on "
            "overlap size, a shared deterministic null per overlap size and BH "
            "correction across tested pathways"
        ),
        "weight_exponent": 1,
    }


def run_preranked_effects(
    ranked_rows: list[dict[str, Any]],
    pathways: list[dict[str, Any]],
    *,
    min_size: int,
    max_size: int,
    permutations: int,
    seed: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Return directional GSEA effects without exposing gene-permutation inference."""
    started = time.perf_counter()
    results, details = run_preranked_gsea(
        ranked_rows,
        pathways,
        min_size=min_size,
        max_size=max_size,
        permutations=permutations,
        seed=seed,
    )
    for row in results:
        row.pop("p_value", None)
        row.pop("fdr", None)
        row["effect_method"] = "weighted_preranked_gsea"
        row["effect_inferential_role"] = "descriptive"
    results.sort(
        key=lambda row: (-abs(float(row["nes"])), row["pathway"])
    )
    return results, {
        **details,
        "algorithm": (
            "weighted preranked GSEA effect calculation with exponent 1 and "
            "a deterministic gene-set-permutation reference distribution for "
            "NES normalization only"
        ),
        "inferential_role": "descriptive_effect_only",
        "gene_set_permutation_p_values_reported": False,
        "effect_elapsed_seconds": time.perf_counter() - started,
    }


def _camera_engine_path() -> Path:
    return Path(__file__).resolve().parent.parent / "scripts" / "camera_gsea.R"


def run_camera_gene_set_test(
    camera_matrix: CameraExpressionMatrix,
    *,
    gene_set_path: Path,
    min_size: int,
    max_size: int,
    work_dir: Path,
    r_script_path: Path | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Run correlation-aware competitive inference with pinned limma CAMERA."""
    if len(camera_matrix.genes) * len(camera_matrix.sample_ids) > (
        CAMERA_MAX_MATRIX_ENTRIES
    ):
        raise ValueError(
            f"Correlation-aware pathway testing exceeds the {CAMERA_MAX_MATRIX_ENTRIES_LABEL} "
            "matrix-entry limit."
        )
    script_path = (r_script_path or _camera_engine_path()).resolve()
    if not script_path.is_file():
        raise RuntimeError("The pinned CAMERA engine is unavailable.")
    work_dir.mkdir(parents=True, exist_ok=True)
    input_path = work_dir / "camera_input.json"
    output_path = work_dir / "camera_output.json"
    input_payload = {
        "schema_version": CAMERA_ENGINE_SCHEMA,
        "matrix_path": str(camera_matrix.path.resolve()),
        "output_path": str(output_path.resolve()),
        "gene_set_path": str(gene_set_path.resolve()),
        "genes": camera_matrix.genes,
        "sample_ids": camera_matrix.sample_ids,
        "groups": camera_matrix.groups,
        "min_gene_set_size": min_size,
        "max_gene_set_size": max_size,
        "expected_limma_version": CAMERA_LIMMA_VERSION,
    }
    input_path.write_text(
        json.dumps(input_payload, ensure_ascii=True, allow_nan=False),
        encoding="utf-8",
    )
    process_started = time.perf_counter()
    completed = subprocess.run(
        ["Rscript", str(script_path), str(input_path)],
        check=False,
        capture_output=True,
        text=True,
        timeout=900,
    )
    process_wall_seconds = time.perf_counter() - process_started
    if completed.returncode != 0 or not output_path.is_file():
        detail = (completed.stderr or completed.stdout or "").strip()
        raise RuntimeError(
            "Correlation-aware CAMERA inference failed. "
            f"{detail[-2000:] if detail else 'No R output was produced.'}"
        )
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != CAMERA_ENGINE_SCHEMA:
        raise RuntimeError("The CAMERA engine returned an unknown schema.")
    if payload.get("limma_version") != CAMERA_LIMMA_VERSION:
        raise RuntimeError("The CAMERA engine returned an unexpected limma version.")
    raw_rows = payload.get("pathways") or []
    p_values = [float(row["p_value"]) for row in raw_rows]
    adjusted = _benjamini_hochberg(p_values)
    rows: list[dict[str, Any]] = []
    for raw, fdr in zip(raw_rows, adjusted, strict=True):
        direction = str(raw.get("direction") or "").strip().casefold()
        if direction not in {"up", "down"}:
            raise RuntimeError("CAMERA returned an invalid effect direction.")
        correlation = float(raw["correlation"])
        p_value = float(raw["p_value"])
        if not math.isfinite(correlation) or not 0 <= p_value <= 1:
            raise RuntimeError("CAMERA returned a non-finite pathway result.")
        rows.append(
            {
                "pathway": str(raw["pathway"]),
                "size_used": int(raw["size_used"]),
                "camera_correlation": correlation,
                "camera_direction": "group_b" if direction == "up" else "group_a",
                "p_value": p_value,
                "fdr": fdr,
            }
        )
    details = {
        key: value
        for key, value in payload.items()
        if key not in {"pathways", "elapsed_seconds"}
    }
    details.update(
        {
            "camera_engine_seconds": float(payload["elapsed_seconds"]),
            "camera_process_wall_seconds": process_wall_seconds,
            "engine_sha256": _sha256_file(script_path),
            "gene_set_sha256": _sha256_file(gene_set_path),
            "matrix_entries": len(camera_matrix.genes)
            * len(camera_matrix.sample_ids),
            "complete_case_genes": len(camera_matrix.genes),
            "multiplicity": "Benjamini-Hochberg across all eligible pathways",
        }
    )
    return rows, details


def combine_camera_inference_with_preranked_effects(
    effect_rows: list[dict[str, Any]],
    camera_rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    inference_by_pathway = {row["pathway"]: row for row in camera_rows}
    if len(inference_by_pathway) != len(camera_rows):
        raise RuntimeError("CAMERA pathway identifiers are not unique.")
    combined: list[dict[str, Any]] = []
    missing: list[str] = []
    for effect in effect_rows:
        inference = inference_by_pathway.get(effect["pathway"])
        if inference is None:
            missing.append(str(effect["pathway"]))
            continue
        if int(effect["size_used"]) != int(inference["size_used"]):
            raise RuntimeError(
                f"CAMERA overlap size disagrees for {effect['pathway']}."
            )
        nes_direction = "group_b" if float(effect["nes"]) >= 0 else "group_a"
        camera_direction = str(inference["camera_direction"])
        combined.append(
            {
                **effect,
                **inference,
                "direction": nes_direction,
                "nes_direction": nes_direction,
                "direction_concordant": nes_direction == camera_direction,
                "inference_method": "limma_camera",
                "inference_hypothesis": "competitive_two_sided",
            }
        )
    unexpected = sorted(set(inference_by_pathway) - {row["pathway"] for row in effect_rows})
    if missing or unexpected:
        raise RuntimeError(
            "CAMERA and preranked pathway families disagree: "
            f"missing={len(missing)}, unexpected={len(unexpected)}."
        )
    combined.sort(
        key=lambda row: (
            float(row["fdr"]),
            float(row["p_value"]),
            -abs(float(row["nes"])),
            str(row["pathway"]),
        )
    )
    discordant = sum(not bool(row["direction_concordant"]) for row in combined)
    return combined, {
        "pathways_tested": len(combined),
        "direction_concordant_pathways": len(combined) - discordant,
        "direction_discordant_pathways": discordant,
        "direction_comparison": (
            "CAMERA direction is based on its correlation-adjusted competitive "
            "test; NES direction is based on the descriptive weighted running-sum effect."
        ),
    }


def group_assignment_rows(
    samples: list[Any],
    assignments: dict[str, str],
    grouping_details: dict[str, Any],
    *,
    clinical_values: dict[str, str | float | None] | None = None,
) -> list[dict[str, Any]]:
    labels = {
        "a": grouping_details["group_a_label"],
        "b": grouping_details["group_b_label"],
    }
    rows: list[dict[str, Any]] = []
    clinical_source = grouping_details.get("source") == "clinical"
    for sample in samples:
        barcode = str(sample.barcode)
        group_key = assignments.get(barcode)
        clinical_value = (
            clinical_values.get(barcode)
            if clinical_values is not None
            else None
        )
        exclusion_reason = None
        if group_key is None:
            if clinical_source and clinical_value is None:
                exclusion_reason = "missing_clinical_value"
            elif clinical_source:
                exclusion_reason = "unselected_clinical_level"
            else:
                exclusion_reason = "not_assigned_by_grouping_source"
        rows.append({
            "patient_id": sample.patient_id,
            "sample_barcode": barcode,
            "analysis_included": group_key is not None,
            "exclusion_reason": exclusion_reason,
            "group_key": group_key,
            "group_label": labels.get(group_key),
            "clinical_variable_id": grouping_details.get("variable")
            if clinical_source
            else None,
            "clinical_variable_label": grouping_details.get("variable_label")
            if clinical_source
            else None,
            "clinical_source": grouping_details.get("variable_source")
            if clinical_source
            else None,
            "clinical_source_field": grouping_details.get(
                "variable_source_field"
            )
            if clinical_source
            else None,
            "clinical_value": clinical_value,
            "sample_type": sample.sample_type,
            "stage": sample.stage,
            "grade": sample.grade,
            "gender": sample.gender,
            "race": sample.race,
            "age_at_index": sample.age_at_index,
        })
    return rows


def _write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _gsea_landscape_svg(
    pathways: list[dict[str, Any]],
    *,
    group_a_label: str,
    group_b_label: str,
) -> str:
    selected = sorted(
        pathways[:30],
        key=lambda row: (float(row["nes"]), row["pathway"]),
        reverse=True,
    )
    width = 960
    row_height = 27
    margin_top = 82
    margin_bottom = 54
    height = max(260, margin_top + len(selected) * row_height + margin_bottom)
    center = 500
    maximum = max([abs(float(row["nes"])) for row in selected] or [1.0])
    scale = 315 / maximum
    parts = [
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
            f'height="{height}" viewBox="0 0 {width} {height}" '
            'role="img" aria-labelledby="title desc">'
        ),
        "<title id=\"title\">GSEA normalized enrichment scores</title>",
        (
            "<desc id=\"desc\">Positive scores favor "
            f"{escape(group_b_label)}; negative scores favor {escape(group_a_label)}."
            "</desc>"
        ),
        '<rect width="100%" height="100%" fill="#fafcfc"/>',
        (
            '<text x="28" y="34" fill="#1d2d38" font-family="IBM Plex Sans, sans-serif" '
            'font-size="20" font-weight="700">Normalized enrichment score</text>'
        ),
        (
            f'<text x="28" y="58" fill="#52616a" font-family="IBM Plex Sans, sans-serif" '
            f'font-size="12">Negative: {escape(group_a_label)} · Positive: '
            f'{escape(group_b_label)}</text>'
        ),
        (
            f'<line x1="{center}" x2="{center}" y1="{margin_top - 14}" '
            f'y2="{height - margin_bottom + 10}" stroke="#9aa8ae" stroke-width="1"/>'
        ),
    ]
    for index, row in enumerate(selected):
        y = margin_top + index * row_height
        nes = float(row["nes"])
        bar_width = abs(nes) * scale
        x = center if nes >= 0 else center - bar_width
        fill = "#1f6f8b" if nes >= 0 else "#536973"
        pathway = escape(str(row["pathway"]))
        parts.extend(
            [
                (
                    f'<line x1="28" x2="930" y1="{y + 11}" y2="{y + 11}" '
                    'stroke="#dce4e6" stroke-width="1"/>'
                ),
                (
                    f'<text x="28" y="{y + 7}" fill="#23343d" '
                    'font-family="IBM Plex Sans, sans-serif" font-size="11">'
                    f"{pathway[:54]}</text>"
                ),
                (
                    f'<rect x="{x:.2f}" y="{y - 4}" width="{bar_width:.2f}" '
                    f'height="12" rx="1" fill="{fill}"/>'
                ),
                (
                    f'<text x="{center + (8 if nes >= 0 else -8)}" y="{y + 7}" '
                    f'text-anchor="{"start" if nes >= 0 else "end"}" fill="#23343d" '
                    'font-family="IBM Plex Mono, monospace" font-size="10">'
                    f"{nes:.2f}</text>"
                ),
            ]
        )
    parts.append("</svg>")
    return "\n".join(parts)


def _interpolate_hex_color(
    start: str,
    end: str,
    fraction: float,
) -> str:
    bounded = min(1.0, max(0.0, fraction))
    start_channels = tuple(
        int(start[index : index + 2], 16) for index in (1, 3, 5)
    )
    end_channels = tuple(
        int(end[index : index + 2], 16) for index in (1, 3, 5)
    )
    channels = tuple(
        round(left + (right - left) * bounded)
        for left, right in zip(start_channels, end_channels, strict=True)
    )
    return "#" + "".join(f"{channel:02x}" for channel in channels)


def _gsea_dotplot_svg(
    pathways: list[dict[str, Any]],
    *,
    group_a_label: str,
    group_b_label: str,
) -> str:
    """Render a deterministic, ggplot-inspired GSEA DotPlot."""
    selected = pathways[:GSEA_DOTPLOT_MAX_PATHWAYS]
    selected_count = len(selected)
    width = 1180
    row_height = 30
    plot_top = 142
    panel_height = max(row_height, selected_count * row_height)
    plot_bottom = plot_top + panel_height
    height = max(360, plot_bottom + 86)
    plot_left = 54
    plot_right = 650
    plot_width = plot_right - plot_left
    pathway_label_x = plot_right + 20
    maximum_nes = max(
        [abs(float(row["nes"])) for row in selected] or [1.0]
    )
    maximum_nes = max(1.0, maximum_nes)
    position_limit = maximum_nes * 1.06
    maximum_radius = 12.0
    negative_color = "#00008b"
    neutral_color = "#ffffff"
    positive_color = "#ff0000"

    def x_position(nes: float) -> float:
        bounded = min(max(nes, -position_limit), position_limit)
        return plot_left + (
            (bounded + position_limit) / (2.0 * position_limit)
        ) * plot_width

    def point_color(nes: float) -> str:
        bounded = min(max(nes, -maximum_nes), maximum_nes)
        if bounded < 0:
            return _interpolate_hex_color(
                negative_color,
                neutral_color,
                (bounded + maximum_nes) / maximum_nes,
            )
        return _interpolate_hex_color(
            neutral_color,
            positive_color,
            bounded / maximum_nes,
        )

    parts = [
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
            f'height="{height}" viewBox="0 0 {width} {height}" '
            'role="img" aria-labelledby="dotplot-title dotplot-desc">'
        ),
        "<title id=\"dotplot-title\">GSEA pathway DotPlot</title>",
        (
            f'<desc id="dotplot-desc">The {selected_count} pathways with the '
            "lowest CAMERA FDR are shown. Horizontal position and dark-blue-to-white-"
            "to-red color encode normalized enrichment score, centered at zero. "
            "Pathway labels are placed on the right. Circle area is proportional "
            "to minus log base "
            f"10 CAMERA FDR, capped at {GSEA_DOTPLOT_NEG_LOG10_FDR_CAP:g}. "
            "An FDR of 1 has zero circle area and is marked by a small cross "
            "for visibility. A dashed vertical reference marks NES zero. "
            f"Negative NES favors {escape(group_a_label)} and positive NES "
            f"favors {escape(group_b_label)}.</desc>"
        ),
        "<defs>",
        (
            '<linearGradient id="nes-color-scale" x1="0%" y1="0%" '
            'x2="100%" y2="0%">'
        ),
        f'<stop offset="0%" stop-color="{negative_color}"/>',
        f'<stop offset="50%" stop-color="{neutral_color}"/>',
        f'<stop offset="100%" stop-color="{positive_color}"/>',
        "</linearGradient>",
        "</defs>",
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        (
            '<text x="24" y="32" fill="#1d2d38" '
            'font-family="IBM Plex Sans, sans-serif" font-size="20" '
            'font-weight="700">GSEA pathway DotPlot</text>'
        ),
        (
            '<text x="24" y="55" fill="#52616a" '
            'font-family="IBM Plex Sans, sans-serif" font-size="12">'
            f"Top {selected_count} by CAMERA FDR · x and blue-white-red color: NES · "
            "circle area: "
            f"min(-log10(FDR), {GSEA_DOTPLOT_NEG_LOG10_FDR_CAP:g})</text>"
        ),
        '<g id="dotplot-legends" data-position="top">',
        (
            '<text x="24" y="86" fill="#23343d" '
            'font-family="IBM Plex Sans, sans-serif" font-size="11" '
            'font-weight="600">Color · NES</text>'
        ),
        (
            '<rect x="104" y="74" width="220" height="14" '
            'fill="url(#nes-color-scale)" stroke="#4f5f67" '
            'stroke-width="0.8"/>'
        ),
        (
            f'<text x="104" y="106" fill="#52616a" '
            'font-family="IBM Plex Mono, monospace" font-size="9">'
            f"{-maximum_nes:.2f}</text>"
        ),
        (
            '<text x="214" y="106" text-anchor="middle" fill="#52616a" '
            'font-family="IBM Plex Mono, monospace" font-size="9">0</text>'
        ),
        (
            '<text x="324" y="106" text-anchor="end" fill="#52616a" '
            'font-family="IBM Plex Mono, monospace" font-size="9">'
            f"{maximum_nes:.2f}</text>"
        ),
        (
            '<text x="370" y="86" fill="#23343d" '
            'font-family="IBM Plex Sans, sans-serif" font-size="11" '
            'font-weight="600">Point area · -log10(CAMERA FDR)</text>'
        ),
        (
            '<text x="690" y="86" fill="#52616a" '
            'font-family="IBM Plex Sans, sans-serif" font-size="9">'
            f"capped at {GSEA_DOTPLOT_NEG_LOG10_FDR_CAP:g}</text>"
        ),
        (
            '<text x="820" y="82" fill="#52616a" '
            'font-family="IBM Plex Sans, sans-serif" font-size="10">'
            f"Blue / negative: {escape(group_a_label)}</text>"
        ),
        (
            '<text x="820" y="103" fill="#52616a" '
            'font-family="IBM Plex Sans, sans-serif" font-size="10">'
            f"Red / positive: {escape(group_b_label)}</text>"
        ),
    ]

    for legend_index, significance in enumerate((1.0, 3.0, 10.0)):
        radius = maximum_radius * math.sqrt(
            significance / GSEA_DOTPLOT_NEG_LOG10_FDR_CAP
        )
        x = 520 + legend_index * 65
        parts.extend(
            [
                (
                    f'<circle cx="{x}" cy="82" r="{radius:.2f}" '
                    'fill="#ffffff" stroke="#33454f" stroke-width="0.8"/>'
                ),
                (
                    f'<text x="{x}" y="108" text-anchor="middle" '
                    'fill="#52616a" font-family="IBM Plex Mono, monospace" '
                    f'font-size="9">{significance:g}</text>'
                ),
            ]
        )
    parts.extend(
        [
            (
                '<text x="690" y="106" fill="#52616a" '
                'font-family="IBM Plex Sans, sans-serif" font-size="9">'
                "× marks FDR = 1</text>"
            ),
            "</g>",
            (
                f'<rect data-role="dotplot-panel" x="{plot_left}" '
                f'y="{plot_top}" width="{plot_width}" height="{panel_height}" '
                'fill="#ffffff" stroke="#4f5f67" stroke-width="1"/>'
            ),
            (
                f'<line data-role="nes-zero-reference" '
                f'x1="{x_position(0):.2f}" x2="{x_position(0):.2f}" '
                f'y1="{plot_top}" y2="{plot_bottom}" stroke="#111111" '
                'stroke-width="1" stroke-dasharray="5 4"/>'
            ),
            '<g id="nes-axis" data-position="bottom">',
        ]
    )

    tick_values = [
        -maximum_nes,
        -maximum_nes / 2.0,
        0.0,
        maximum_nes / 2.0,
        maximum_nes,
    ]
    for tick in tick_values:
        x = x_position(tick)
        parts.extend(
            [
                (
                    f'<line x1="{x:.2f}" x2="{x:.2f}" '
                    f'y1="{plot_bottom}" y2="{plot_bottom + 5}" '
                    'stroke="#87969d" stroke-width="1"/>'
                ),
                (
                    f'<text x="{x:.2f}" y="{plot_bottom + 22}" '
                    'text-anchor="middle" fill="#52616a" '
                    'font-family="IBM Plex Mono, monospace" font-size="10">'
                    f"{tick:.2f}</text>"
                ),
            ]
        )
    parts.extend(
        [
            (
                f'<text x="{(plot_left + plot_right) / 2:.2f}" '
                f'y="{plot_bottom + 49}" text-anchor="middle" fill="#23343d" '
                'font-family="IBM Plex Sans, sans-serif" font-size="12" '
                'font-weight="600">Normalized enrichment score (NES)</text>'
            ),
            "</g>",
        ]
    )

    for index, row in enumerate(selected):
        y = plot_top + index * row_height + row_height / 2.0
        nes = float(row["nes"])
        fdr = min(1.0, max(0.0, float(row["fdr"])))
        negative_log10_fdr = (
            GSEA_DOTPLOT_NEG_LOG10_FDR_CAP
            if fdr == 0
            else min(
                GSEA_DOTPLOT_NEG_LOG10_FDR_CAP,
                max(0.0, -math.log10(fdr)),
            )
        )
        radius = maximum_radius * math.sqrt(
            negative_log10_fdr / GSEA_DOTPLOT_NEG_LOG10_FDR_CAP
        )
        raw_pathway = str(row["pathway"])
        pathway_label = (
            raw_pathway
            if len(raw_pathway) <= 52
            else f"{raw_pathway[:51]}…"
        )
        accessible_label = escape(
            f"{raw_pathway}: NES {nes:.3f}; CAMERA FDR {fdr:.4g}; "
            f"-log10 CAMERA FDR {negative_log10_fdr:.3f}"
        )
        parts.extend(
            [
                (
                    f'<text data-role="pathway-label" data-axis-side="right" '
                    f'x="{pathway_label_x}" y="{y + 4:.2f}" '
                    'text-anchor="start" fill="#23343d" '
                    'font-family="IBM Plex Sans, sans-serif" font-size="11">'
                    f"{escape(pathway_label)}</text>"
                ),
                (
                    f'<circle cx="{x_position(nes):.2f}" cy="{y:.2f}" '
                    f'r="{radius:.4f}" fill="{point_color(nes)}" '
                    'stroke="#33454f" stroke-width="0.8" fill-opacity="0.94" '
                    f'data-nes="{nes:.12g}" data-fdr="{fdr:.12g}" '
                    f'data-negative-log10-fdr="{negative_log10_fdr:.12g}" '
                    f'aria-label="{accessible_label}">'
                    f"<title>{accessible_label}</title></circle>"
                ),
            ]
        )
        if negative_log10_fdr == 0:
            x = x_position(nes)
            cross_path = (
                f"M {x - 3:.2f} {y - 3:.2f} L {x + 3:.2f} {y + 3:.2f} "
                f"M {x - 3:.2f} {y + 3:.2f} L {x + 3:.2f} {y - 3:.2f}"
            )
            parts.extend(
                [
                    (
                        f'<path d="{cross_path}" fill="none" stroke="#33454f" '
                        'stroke-width="2.8" stroke-linecap="round" '
                        'aria-hidden="true"/>'
                    ),
                    (
                        f'<path d="{cross_path}" fill="none" '
                        f'stroke="{point_color(nes)}" stroke-width="1.4" '
                        'stroke-linecap="round" aria-hidden="true"/>'
                    ),
                ]
            )
    parts.append("</svg>")
    return "\n".join(parts)


def write_gsea_artifacts(
    output_dir: Path,
    *,
    request_payload: dict[str, Any],
    result_payload: dict[str, Any],
    ranked_rows: list[dict[str, Any]],
    assignment_rows: list[dict[str, Any]],
    collection: dict[str, Any],
    pipeline_version: str,
) -> tuple[dict[str, str], dict[str, Any]]:
    output_dir.mkdir(parents=True, exist_ok=False)
    input_path = output_dir / "input.json"
    ranking_path = output_dir / "ranked_genes.csv"
    groups_path = output_dir / "sample_groups.csv"
    pathways_path = output_dir / "gsea_results.csv"
    leading_edge_path = output_dir / "leading_edges.csv"
    svg_path = output_dir / "gsea_landscape.svg"
    dotplot_svg_path = output_dir / "gsea_dotplot.svg"
    methods_path = output_dir / "methodology.txt"
    camera_engine_path = output_dir / "camera_gsea.R"
    collection_path = output_dir / "gene_set_manifest.json"
    result_path = output_dir / "result.json"
    audit_path = output_dir / "audit_report.json"

    input_path.write_text(
        json.dumps(
            request_payload,
            ensure_ascii=True,
            allow_nan=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    _write_csv(
        ranking_path,
        ranked_rows,
        [
            "rank",
            "gene",
            "score",
            "mean_group_a",
            "mean_group_b",
            "difference_b_minus_a",
            "n_group_a",
            "n_group_b",
        ],
    )
    _write_csv(
        groups_path,
        assignment_rows,
        [
            "patient_id",
            "sample_barcode",
            "analysis_included",
            "exclusion_reason",
            "group_key",
            "group_label",
            "clinical_variable_id",
            "clinical_variable_label",
            "clinical_source",
            "clinical_source_field",
            "clinical_value",
            "sample_type",
            "stage",
            "grade",
            "gender",
            "race",
            "age_at_index",
        ],
    )
    pathway_rows = [
        {
            **row,
            "leading_edge": ";".join(row["leading_edge"]),
        }
        for row in result_payload["pathways"]
    ]
    _write_csv(
        pathways_path,
        pathway_rows,
        [
            "pathway",
            "description",
            "size_original",
            "size_used",
            "es",
            "nes",
            "p_value",
            "fdr",
            "inference_method",
            "inference_hypothesis",
            "camera_correlation",
            "camera_direction",
            "nes_direction",
            "direction_concordant",
            "effect_method",
            "effect_inferential_role",
            "direction",
            "rank_at_max",
            "leading_edge_size",
            "leading_edge",
        ],
    )
    rank_by_gene = {
        row["gene"]: row["rank"]
        for row in ranked_rows
    }
    leading_rows = [
        {
            "pathway": row["pathway"],
            "direction": row["direction"],
            "gene": gene,
            "rank": rank_by_gene[gene],
        }
        for row in result_payload["pathways"]
        for gene in row["leading_edge"]
    ]
    _write_csv(
        leading_edge_path,
        leading_rows,
        ["pathway", "direction", "gene", "rank"],
    )
    svg_path.write_text(
        _gsea_landscape_svg(
            result_payload["pathways"],
            group_a_label=result_payload["grouping"]["group_a_label"],
            group_b_label=result_payload["grouping"]["group_b_label"],
        ),
        encoding="utf-8",
    )
    dotplot_svg_path.write_text(
        _gsea_dotplot_svg(
            result_payload["pathways"],
            group_a_label=result_payload["grouping"]["group_a_label"],
            group_b_label=result_payload["grouping"]["group_b_label"],
        ),
        encoding="utf-8",
    )
    public_collection = {
        key: value
        for key, value in collection.items()
        if key != "file"
    }
    collection_path.write_text(
        json.dumps(
            public_collection,
            ensure_ascii=True,
            allow_nan=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    methods_path.write_text(
        "\n".join(
            [
                "TRACE Explorer correlation-aware pathway analysis",
                "",
                (
                    "Samples were filtered using the declared clinical restrictions, "
                    "matched to the broad normalized expression matrix and reduced to "
                    "one sample per patient using the source-specific priority rule."
                ),
                (
                    "Primary pathway inference uses limma CAMERA with a group B "
                    "minus group A design. CAMERA estimates residual inter-gene "
                    "correlation separately for every eligible set, does not allow "
                    "negative correlation to reduce its variance inflation factor, "
                    "uses empirical-Bayes variance moderation with a mean-variance "
                    "trend, and reports a two-sided competitive p-value."
                ),
                (
                    "Benjamini-Hochberg FDR is calculated from CAMERA p-values "
                    "across all pathways that pass the declared overlap-size limits."
                ),
                (
                    "The descriptive gene ranking is computed as group B minus group A. "
                    "Welch t uses the unmoderated unequal-variance statistic; "
                    "signal-to-noise divides the mean difference by the sum of the "
                    "within-group sample standard deviations. Only genes with finite "
                    "values in every selected patient enter either pathway layer."
                ),
                (
                    "Weighted enrichment scores use absolute ranking statistics with "
                    "exponent 1. Deterministic gene-set permutations normalize ES to "
                    "NES; their p-values are not reported or used for inference. "
                    "Positive NES favors group B and negative NES favors group A. "
                    "Leading-edge genes are descriptive."
                ),
                (
                    "The DotPlot selects up to 30 pathways with lowest CAMERA FDR. "
                    "Horizontal position and a dark-blue-to-white-to-red scale "
                    "centered at zero encode NES; pathway labels are on the right, "
                    "legends are above the panel and a dashed vertical reference "
                    "marks NES zero. Circle area is proportional to "
                        "min(-log10(CAMERA FDR), 10); the cap is explicit in the plot and "
                    "prevents vanishingly small FDR values from dominating the "
                    "size scale."
                ),
                (
                    "CAMERA direction and NES direction are recorded separately because "
                    "the competitive test and running-sum effect are related but not "
                    "identical summaries. Their agreement is reported per pathway."
                ),
                (
                    "When groups were derived from the tested transcriptome, an "
                    "expression-based survival split or an expression-derived clinical "
                    "annotation, p-values and FDR are conditional exploratory summaries "
                    "rather than independent confirmation. No result is causal or "
                    "clinically actionable."
                ),
                "",
                f"Pipeline version: {pipeline_version}",
                f"Gene-set collection: {collection['label']} ({collection['version']})",
                f"Gene-set SHA-256: {collection['sha256']}",
                *(
                    [f"Gene-set release DOI: {collection['release_doi']}"]
                    if collection.get("release_doi")
                    else []
                ),
                *(
                    [f"Gene-set attribution: {collection['attribution']}"]
                    if collection.get("attribution")
                    else []
                ),
                *(
                    [f"Gene-set license: {collection['license']}"]
                    if collection.get("license")
                    else []
                ),
                f"Permutations: {result_payload['ranking']['permutations']}",
                f"Seed: {result_payload['ranking']['seed']}",
                f"CAMERA engine: limma {result_payload['inference']['limma_version']}",
                "CAMERA inter-gene correlation: estimated separately for each set",
                f"Inferential role: {result_payload['inference']['inferential_role']}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    camera_engine_path.write_text(
        _camera_engine_path().read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    artifact_paths = {
        "input": input_path,
        "ranking": ranking_path,
        "groups": groups_path,
        "pathways": pathways_path,
        "leading_edges": leading_edge_path,
        "svg": svg_path,
        "dotplot_svg": dotplot_svg_path,
        "methodology": methods_path,
        "camera_engine": camera_engine_path,
        "gene_set_manifest": collection_path,
    }
    audit = {
        "report_type": "camera_preranked_gsea_audit",
        "schema_version": GSEA_AUDIT_SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "pipeline_version": pipeline_version,
        "request_sha256": _stable_hash(request_payload),
        "group_assignments_sha256": _sha256_file(groups_path),
        "ranked_genes_sha256": _sha256_file(ranking_path),
        "gene_set_collection_sha256": collection["sha256"],
        "matrix_sha256": (
            result_payload.get("data_provenance") or {}
        ).get("matrix_sha256"),
        "data_version": (
            result_payload.get("data_provenance") or {}
        ).get("data_version") or {},
        "result_core_sha256": _stable_hash(
            {
                "grouping": result_payload["grouping"],
                "ranking": result_payload["ranking"],
                "inference": result_payload["inference"],
                "summary": result_payload["summary"],
                "pathways": result_payload["pathways"],
                "data_provenance": result_payload.get("data_provenance")
                or {},
            }
        ),
        "artifacts": {
            name: {
                "filename": path.name,
                "file": path.name,
                "sha256": _sha256_file(path),
                "bytes": path.stat().st_size,
            }
            for name, path in artifact_paths.items()
        },
        "limitations": [
            (
                "CAMERA controls competitive pathway inference by estimating "
                "residual inter-gene correlation for each set; the displayed NES "
                "and leading edge remain descriptive running-sum summaries."
            ),
            (
                "The analysis is exploratory and is not intended for clinical "
                "decision-making."
            ),
        ],
    }
    if result_payload["grouping"].get("circularity_notice"):
        audit["limitations"].append(
            result_payload["grouping"]["circularity_notice"]
        )
    audit_path.write_text(
        json.dumps(audit, ensure_ascii=True, allow_nan=False, indent=2),
        encoding="utf-8",
    )
    result_with_audit = {**result_payload, "audit": audit}
    result_path.write_text(
        json.dumps(
            result_with_audit,
            ensure_ascii=True,
            allow_nan=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return (
        {
            **{name: str(path) for name, path in artifact_paths.items()},
            "audit": str(audit_path),
            "result": str(result_path),
        },
        audit,
    )


def gsea_summary(
    pathways: list[dict[str, Any]],
    *,
    fdr_threshold: float,
    group_a_label: str,
    group_b_label: str,
) -> dict[str, Any]:
    supported = [
        row for row in pathways if float(row["fdr"]) <= fdr_threshold
    ]

    def supported_direction(row: dict[str, Any]) -> str:
        camera_direction = str(row.get("camera_direction") or "")
        if camera_direction in {"group_a", "group_b"}:
            return camera_direction
        nes = float(row["nes"])
        if nes > 0:
            return "group_b"
        if nes < 0:
            return "group_a"
        return "none"

    group_b_supported = [
        row for row in supported if supported_direction(row) == "group_b"
    ]
    group_a_supported = [
        row for row in supported if supported_direction(row) == "group_a"
    ]
    direction_basis = (
        "camera_direction"
        if any(row.get("camera_direction") for row in pathways)
        else "nes_direction"
    )
    return {
        "fdr_threshold": fdr_threshold,
        "pathways_tested": len(pathways),
        "pathways_at_fdr": len(supported),
        "enriched_in_group_b": len(group_b_supported),
        "enriched_in_group_a": len(group_a_supported),
        "supported_direction_basis": direction_basis,
        "group_a_label": group_a_label,
        "group_b_label": group_b_label,
        "positive_nes_means": f"enriched in {group_b_label}",
        "negative_nes_means": f"enriched in {group_a_label}",
        "top_group_b_pathway": (
            min(
                group_b_supported,
                key=lambda row: (
                    float(row["fdr"]),
                    float(row.get("p_value", 1.0)),
                    str(row["pathway"]),
                ),
            )["pathway"]
            if group_b_supported
            else None
        ),
        "top_group_a_pathway": (
            min(
                group_a_supported,
                key=lambda row: (
                    float(row["fdr"]),
                    float(row.get("p_value", 1.0)),
                    str(row["pathway"]),
                ),
            )["pathway"]
            if group_a_supported
            else None
        ),
    }
