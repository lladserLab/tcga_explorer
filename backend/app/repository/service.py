from __future__ import annotations

from app.retention import persistent_local_dataset

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import math
from pathlib import Path
from typing import Any, Mapping

from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session

from app.clinical_grouping import clinical_grouping_context
from app.config import get_settings
from app.gene_aliases import GENE_ALIASES
from app.models import (
    CancerType,
    RepositoryDataset,
    RepositoryEndpointDefinition,
    RepositoryEndpointValue,
    RepositoryExpressionLayer,
    RepositoryGene,
    RepositoryPatient,
    RepositoryRelease,
    RepositorySample,
)
from app.repository.capabilities import (
    CAPABILITY_EXPRESSION,
    CAPABILITY_EXPRESSION_COMPARISON,
    CAPABILITY_GSEA,
    CAPABILITY_RANK_BASED_SIGNATURE_SCORING,
    CAPABILITY_SURVIVAL,
    available_repository_modules,
    capability_for_analysis_type,
    derive_repository_capabilities,
    rank_signature_capability_from_qc,
)
from app.repository.paths import (
    resolve_repository_artifact_path,
    resolve_repository_release_path,
)
from app.repository.storage import read_float32le_row, read_matrix_metadata
from app.survival import ClinicalOutcome


CLINICAL_GROUPING_CACHE_KEY = "clinical_grouping_variables_v2"
_CLINICAL_GROUPING_MEMORY_CACHE: dict[tuple[str, str], list[dict[str, Any]]] = {}

IMMOTION150_DATASET_ID = "cbioportal-kirc-iatlas-immotion150-2018"


@dataclass(frozen=True)
class RepositoryAnalysisSample:
    patient_id: str
    barcode: str
    sample_type: str | None
    stage: str | None
    grade: str | None
    gender: str | None
    race: str | None
    age_at_index: float | None
    selection_rank: int
    sample_role: str | None
    raw_metadata: dict[str, Any] | None
    study_arm: str | None = None
    os_time_days: float | None = None
    os_event: int | None = None


def _nonmissing_treatment(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text or text.casefold() in {"na", "n/a", "none", "null"}:
        return None
    return text


def repository_study_arm(
    context: RepositoryContext,
    patient_metadata: dict[str, Any] | None,
    sample_metadata: dict[str, Any] | None,
) -> str | None:
    """Return the prespecified trial arm without inferring it from outcomes."""

    if context.dataset.id != IMMOTION150_DATASET_ID:
        return None
    patient_metadata = patient_metadata or {}
    sample_metadata = sample_metadata or {}
    treatments = [
        _nonmissing_treatment(patient_metadata.get("ICI_RX")),
        _nonmissing_treatment(sample_metadata.get("NON_ICI_RX")),
    ]
    unique = list(dict.fromkeys(item for item in treatments if item))
    return " + ".join(unique) if unique else None


def repository_requires_independent_arm(
    context: RepositoryContext,
    endpoint_id: str,
) -> bool:
    return (
        context.dataset.id == IMMOTION150_DATASET_ID
        and endpoint_id.strip().upper() == "PFS"
    )


@dataclass(frozen=True)
class RepositoryContext:
    dataset: RepositoryDataset
    release: RepositoryRelease
    cancer: CancerType

    @property
    def cohort(self) -> str:
        return self.cancer.tcga_cohort


def repository_release_storage_path(context: RepositoryContext) -> Path:
    is_private = context.dataset.visibility == "private"
    if is_private:
        release_path = Path(context.release.repository_path).resolve()
        if (
            release_path.name != context.dataset.id
            or not release_path.is_dir()
            or not (release_path / "manifest.json").is_file()
        ):
            raise ValueError(
                "Private dataset storage does not match its dataset identity."
            )
        return release_path
    repository_root = get_settings().cancer_repository_dir
    return resolve_repository_release_path(
        repository_root,
        dataset_id=context.dataset.id,
        release_id=context.release.id,
        stored_path=context.release.repository_path,
        allow_legacy=True,
    )


def repository_expression_layer_paths(
    context: RepositoryContext,
    layer: RepositoryExpressionLayer,
) -> tuple[Path, Path]:
    is_private = context.dataset.visibility == "private"
    if is_private:
        release_path = repository_release_storage_path(context)
        paths = (
            Path(layer.matrix_path).resolve(),
            Path(layer.metadata_path).resolve(),
        )
        for path in paths:
            try:
                path.relative_to(release_path)
            except ValueError as exc:
                raise ValueError(
                    "Private dataset artifact escapes its dataset directory."
                ) from exc
            if not path.is_file():
                raise FileNotFoundError(
                    f"Private dataset artifact is unavailable: {path}."
                )
        return paths
    repository_root = get_settings().cancer_repository_dir
    common = {
        "repository_root": repository_root,
        "dataset_id": context.dataset.id,
        "release_id": context.release.id,
        "stored_release_path": context.release.repository_path,
        "allow_legacy": True,
    }
    matrix_path = resolve_repository_artifact_path(
        **common,
        stored_artifact_path=layer.matrix_path,
    )
    metadata_path = resolve_repository_artifact_path(
        **common,
        stored_artifact_path=layer.metadata_path,
    )
    return matrix_path, metadata_path


def resolve_repository_context(
    db: Session,
    dataset_id: str,
    release_id: str | None = None,
    *,
    include_private: bool = False,
) -> RepositoryContext:
    dataset = db.get(RepositoryDataset, dataset_id)
    if dataset is None or dataset.status != "available":
        raise ValueError(f"External dataset {dataset_id!r} is not available.")
    visibility = dataset.visibility or "public"
    if visibility != "public" and not include_private:
        raise ValueError(f"External dataset {dataset_id!r} is not available.")
    if (
        visibility == "private"
        and (
            not dataset_id.startswith("user-")
            or (not persistent_local_dataset(dataset) and (
                dataset.expires_at is None
                or dataset.expires_at <= datetime.now(timezone.utc).replace(tzinfo=None)
            ))
        )
    ):
        raise ValueError(
            f"Private dataset {dataset_id!r} has expired or is unavailable."
        )
    selected_release = release_id or dataset.active_release_id
    if not selected_release:
        raise ValueError(f"External dataset {dataset_id!r} has no active release.")
    release = db.get(RepositoryRelease, selected_release)
    if (
        release is None
        or release.dataset_id != dataset.id
        or release.status != "published"
        or release.qc_status != "passed"
    ):
        raise ValueError(
            f"External release {selected_release!r} is not a published release of {dataset_id!r}."
        )
    cancer = db.get(CancerType, dataset.cancer_code)
    if cancer is None:
        raise ValueError(f"Cancer type {dataset.cancer_code!r} is not registered.")
    return RepositoryContext(dataset=dataset, release=release, cancer=cancer)


def repository_samples(
    db: Session, context: RepositoryContext
) -> list[RepositoryAnalysisSample]:
    patients = {
        patient.patient_id: patient
        for patient in db.scalars(
            select(RepositoryPatient).where(
                RepositoryPatient.release_id == context.release.id
            )
        ).all()
    }
    rows = db.scalars(
        select(RepositorySample)
        .where(RepositorySample.release_id == context.release.id)
        .order_by(
            RepositorySample.patient_id,
            RepositorySample.selection_rank,
            RepositorySample.sample_id,
        )
    ).all()
    return [
        RepositoryAnalysisSample(
            patient_id=row.patient_id,
            barcode=row.sample_id,
            sample_type=row.sample_type,
            sample_role=row.sample_role,
            selection_rank=row.selection_rank,
            stage=patients.get(row.patient_id).stage
            if patients.get(row.patient_id)
            else None,
            grade=patients.get(row.patient_id).grade
            if patients.get(row.patient_id)
            else None,
            gender=patients.get(row.patient_id).gender
            if patients.get(row.patient_id)
            else None,
            race=patients.get(row.patient_id).race
            if patients.get(row.patient_id)
            else None,
            age_at_index=patients.get(row.patient_id).age_at_index
            if patients.get(row.patient_id)
            else None,
            raw_metadata=(
                {
                    "patient": dict(
                        patients.get(row.patient_id).raw_metadata or {}
                    ),
                    "sample": dict(row.raw_metadata or {}),
                }
                if patients.get(row.patient_id) or row.raw_metadata
                else None
            ),
            study_arm=repository_study_arm(
                context,
                (
                    dict(patients.get(row.patient_id).raw_metadata or {})
                    if patients.get(row.patient_id)
                    else None
                ),
                dict(row.raw_metadata or {}),
            ),
        )
        for row in rows
    ]


def repository_endpoint_options(
    db: Session, context: RepositoryContext
) -> list[dict[str, Any]]:
    definitions = db.scalars(
        select(RepositoryEndpointDefinition)
        .where(RepositoryEndpointDefinition.release_id == context.release.id)
        .order_by(RepositoryEndpointDefinition.endpoint_id)
    ).all()
    return [
        {
            "value": row.endpoint_id,
            "label": row.label,
            "available": bool(row.available),
            "source": (
                "user_upload"
                if context.dataset.visibility == "private"
                else f"external:{context.dataset.source_provider}"
            ),
            "reason": row.reason,
            "patient_count": row.patient_count,
            "event_count": row.event_count,
            "time_origin": row.time_origin,
            "event_definition": row.event_definition,
            "source_time_unit": row.source_time_unit,
            "standard_code": row.standard_code,
        }
        for row in definitions
    ]


def repository_endpoint_outcomes(
    db: Session,
    context: RepositoryContext,
    endpoint_id: str,
) -> tuple[dict[str, ClinicalOutcome], dict[str, Any]]:
    options = repository_endpoint_options(db, context)
    option = next((row for row in options if row["value"] == endpoint_id), None)
    if option is None:
        raise ValueError(
            f"Endpoint {endpoint_id!r} is not defined for {context.dataset.id}."
        )
    if not option["available"]:
        raise ValueError(
            f"Endpoint {endpoint_id!r} is not available: {option['reason']}"
        )
    rows = db.scalars(
        select(RepositoryEndpointValue)
        .where(RepositoryEndpointValue.release_id == context.release.id)
        .where(RepositoryEndpointValue.endpoint_id == endpoint_id)
    ).all()
    return (
        {
            row.patient_id: ClinicalOutcome(
                endpoint=endpoint_id,
                time_days=float(row.time_days),
                event=int(row.event),
                source=(
                    "user_upload"
                    if context.dataset.visibility == "private"
                    else f"external:{context.dataset.source_provider}"
                ),
            )
            for row in rows
        },
        option,
    )


def repository_expression_layers(
    db: Session, context: RepositoryContext
) -> list[dict[str, Any]]:
    rows = db.scalars(
        select(RepositoryExpressionLayer)
        .where(RepositoryExpressionLayer.release_id == context.release.id)
        .order_by(
            RepositoryExpressionLayer.is_default.desc(),
            RepositoryExpressionLayer.layer_id,
        )
    ).all()
    result = []
    for row in rows:
        coverage = repository_expression_layer_coverage(db, context, row)
        result.append({
            "value": row.layer_id,
            "label": row.label,
            "source_unit": row.source_unit,
            "analysis_unit": row.analysis_unit,
            "transform": row.transform,
            "is_default": row.is_default,
            "gene_count": row.gene_count,
            "sample_count": row.sample_count,
            "downloadable": row.downloadable,
            "scale_note": (row.metadata_json or {}).get("scale_note"),
            "coverage": coverage,
            "capabilities": repository_capabilities(
                context,
                expression_layer_id=row.layer_id,
                layer_coverage=coverage,
            ),
        })
    return result


def repository_expression_layer_coverage(
    db: Session,
    context: RepositoryContext,
    layer: RepositoryExpressionLayer,
) -> dict[str, Any]:
    """Count the selected matrix's linked patients, never infer them from columns.

    Older releases did not freeze per-layer patient/endpoint counts in QC.
    Resolve their immutable matrix IDs against release-scoped linkage records;
    published QC, matrices and patient selection rules remain unchanged.
    """
    layer_qc = ((context.release.qc_json or {}).get("layers") or {}).get(layer.layer_id, {})
    if "patients" in layer_qc and "endpoints" in layer_qc:
        return {
            "patient_count": int(layer_qc["patients"]),
            "sample_count": int(layer_qc["samples"]),
            "observation_unit": "paired_contrast" if layer.transform == "paired_difference" else "rna_profile",
            "sample_roles": layer_qc.get("sample_roles", {}),
            "endpoints": layer_qc["endpoints"],
            "scope": "expression_layer_before_sample_selection_and_filters",
        }
    _, metadata_path = repository_expression_layer_paths(context, layer)
    metadata = read_matrix_metadata(metadata_path)
    sample_ids = [str(value) for value in metadata.get("sample_ids") or []]
    if (
        len(sample_ids) != layer.sample_count
        or len(sample_ids) != len(set(sample_ids))
    ):
        raise ValueError("Expression-layer sample coverage could not be verified.")
    matrix_ids = set(sample_ids)
    samples = db.execute(
        select(RepositorySample.sample_id, RepositorySample.patient_id,
               RepositorySample.sample_role)
        .where(RepositorySample.release_id == context.release.id)
    ).all()
    selected = [row for row in samples if row.sample_id in matrix_ids]
    if len(selected) != len(matrix_ids):
        raise ValueError("Expression-layer patient linkage could not be verified.")
    patients = {row.patient_id for row in selected}
    roles: dict[str, int] = {}
    for row in selected:
        role = row.sample_role or "unknown"
        roles[role] = roles.get(role, 0) + 1

    endpoint_values = db.execute(
        select(RepositoryEndpointValue.endpoint_id,
               RepositoryEndpointValue.patient_id,
               RepositoryEndpointValue.time_days, RepositoryEndpointValue.event)
        .where(RepositoryEndpointValue.release_id == context.release.id)
    ).all()
    thresholds = (context.release.qc_json or {}).get("thresholds") or {}
    endpoints = {}
    for option in repository_endpoint_options(db, context):
        linked = {
            row.patient_id: row.event
            for row in endpoint_values
            if row.endpoint_id == option["value"] and row.patient_id in patients
            and math.isfinite(row.time_days) and row.time_days > 0
            and row.event in (0, 1)
        }
        events = sum(linked.values())
        censored = len(linked) - events
        # Private upload eligibility is attested under its own QC thresholds.
        sufficient = context.dataset.visibility == "private" or (
            len(linked) >= int(thresholds.get("minimum_patients", 10))
            and events >= int(thresholds.get("minimum_events", 5))
            and censored >= int(thresholds.get("minimum_censored", 5))
        )
        available = bool(option["available"] and sufficient and linked)
        endpoints[option["value"]] = {
            "patients": len(linked), "events": events, "censored": censored,
            "available": available,
            "reason": option["reason"] if not option["available"] else (
                None if available else "Too few patients, events or censored observations in this expression layer."
            ),
        }
    return {
        "patient_count": len(patients),
        "sample_count": len(sample_ids),
        "observation_unit": "paired_contrast" if layer.transform == "paired_difference" else "rna_profile",
        "sample_roles": roles,
        "endpoints": endpoints,
        "scope": "expression_layer_before_sample_selection_and_filters",
    }


def resolve_expression_layer(
    db: Session,
    context: RepositoryContext,
    layer_id: str | None,
) -> RepositoryExpressionLayer:
    stmt = select(RepositoryExpressionLayer).where(
        RepositoryExpressionLayer.release_id == context.release.id
    )
    if layer_id:
        stmt = stmt.where(RepositoryExpressionLayer.layer_id == layer_id)
    else:
        stmt = stmt.where(RepositoryExpressionLayer.is_default.is_(True))
    layer = db.scalar(stmt.limit(1))
    if layer is None:
        raise ValueError(
            f"Expression layer {layer_id or 'default'!r} is unavailable for {context.dataset.id}."
        )
    return layer


def repository_gene_expression(
    db: Session,
    context: RepositoryContext,
    gene_symbol: str,
    layer_id: str | None = None,
) -> tuple[dict[str, float], RepositoryExpressionLayer, RepositoryGene]:
    layer = resolve_expression_layer(db, context, layer_id)
    symbol = canonical_repository_symbol(db, layer, gene_symbol)
    gene = db.scalar(
        select(RepositoryGene)
        .where(RepositoryGene.expression_layer_id == layer.id)
        .where(RepositoryGene.gene_symbol == symbol)
    )
    if gene is None:
        from app.expression import GeneNotFoundError

        raise GeneNotFoundError(
            f"Gene {gene_symbol.strip().upper()} not found in {context.dataset.id}."
        )
    matrix_path, metadata_path = repository_expression_layer_paths(
        context, layer
    )
    metadata = read_matrix_metadata(metadata_path)
    expression = read_float32le_row(
        matrix_path,
        row_number=gene.row_number,
        sample_ids=list(metadata["sample_ids"]),
    )
    return expression, layer, gene


def canonical_repository_symbol(
    db: Session,
    layer: RepositoryExpressionLayer,
    query: str,
) -> str:
    normalized = query.strip().upper()
    candidate = GENE_ALIASES.get(normalized, normalized)
    exists = db.scalar(
        select(RepositoryGene.id)
        .where(RepositoryGene.expression_layer_id == layer.id)
        .where(RepositoryGene.gene_symbol == candidate)
        .limit(1)
    )
    return candidate if exists else normalized


def search_repository_genes(
    db: Session,
    context: RepositoryContext,
    query: str,
    *,
    layer_id: str | None = None,
    limit: int = 25,
) -> list[str]:
    layer = resolve_expression_layer(db, context, layer_id)
    normalized = query.strip().upper()
    stmt = select(RepositoryGene.gene_symbol).where(
        RepositoryGene.expression_layer_id == layer.id
    )
    if normalized:
        stmt = stmt.where(
            RepositoryGene.gene_symbol.like(f"{normalized}%")
            | RepositoryGene.gene_symbol.like(f"%{normalized}%")
        )
    return list(
        db.scalars(
            stmt.order_by(RepositoryGene.gene_symbol).limit(min(limit, 100))
        ).all()
    )


def repository_filter_options(
    db: Session, context: RepositoryContext
) -> dict[str, Any]:
    release_id = context.release.id

    def values(column) -> list[str]:
        return [
            value
            for value in db.scalars(
                select(distinct(column))
                .where(RepositoryPatient.release_id == release_id)
                .where(column.is_not(None))
                .order_by(column)
            ).all()
            if value
        ]

    sample_types = [
        value
        for value in db.scalars(
            select(distinct(RepositorySample.sample_type))
            .where(RepositorySample.release_id == release_id)
            .where(RepositorySample.sample_type.is_not(None))
            .order_by(RepositorySample.sample_type)
        ).all()
        if value
    ]
    max_time = db.scalar(
        select(func.max(RepositoryEndpointValue.time_days)).where(
            RepositoryEndpointValue.release_id == release_id
        )
    )
    cache_identity = (context.release.id, context.release.manifest_hash)
    persisted_cache = (context.release.qc_json or {}).get(
        CLINICAL_GROUPING_CACHE_KEY
    )
    clinical_variables = None
    if (
        isinstance(persisted_cache, dict)
        and persisted_cache.get("manifest_hash") == context.release.manifest_hash
        and isinstance(persisted_cache.get("variables"), list)
    ):
        clinical_variables = persisted_cache["variables"]
    if clinical_variables is None:
        clinical_variables = _CLINICAL_GROUPING_MEMORY_CACHE.get(cache_identity)
    if clinical_variables is None:
        analysis_samples = repository_samples(db, context)
        clinical_variables, _ = clinical_grouping_context(
            analysis_samples,
            cohort=context.cohort,
            repository=True,
        )
        _CLINICAL_GROUPING_MEMORY_CACHE[cache_identity] = clinical_variables
    return {
        "sample_types": sample_types,
        "stages": values(RepositoryPatient.stage),
        "grades": values(RepositoryPatient.grade),
        "genders": values(RepositoryPatient.gender),
        "races": values(RepositoryPatient.race),
        "age_min": db.scalar(
            select(func.min(RepositoryPatient.age_at_index)).where(
                RepositoryPatient.release_id == release_id
            )
        ),
        "age_max": db.scalar(
            select(func.max(RepositoryPatient.age_at_index)).where(
                RepositoryPatient.release_id == release_id
            )
        ),
        "os_time_max_days": max_time,
        "clinical_grouping_variables": clinical_variables,
    }


def repository_capabilities(
    source: RepositoryContext
    | RepositoryRelease
    | Mapping[str, Any]
    | None,
    expression_layer_id: str | None = None,
    *,
    layer_coverage: Mapping[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    """Return normalized capability details for a release or QC payload."""

    if isinstance(source, RepositoryContext):
        private_capabilities = _private_repository_capabilities(source)
        if private_capabilities is not None:
            expression = private_capabilities[CAPABILITY_EXPRESSION]
            private_capabilities[
                CAPABILITY_RANK_BASED_SIGNATURE_SCORING
            ] = rank_signature_capability_from_qc(
                source.release.qc_json,
                expression_layer_id=expression_layer_id,
                prerequisite_available=bool(expression.get("available")),
                prerequisite_reason=expression.get("reason"),
            )
            return private_capabilities
        qc = source.release.qc_json
    elif isinstance(source, RepositoryRelease):
        qc = source.qc_json
    elif source is None or isinstance(source, Mapping):
        qc = source
    else:
        raise TypeError(
            "repository_capabilities expects RepositoryContext, "
            "RepositoryRelease, a QC mapping, or None."
        )
    if layer_coverage is not None and expression_layer_id:
        # A transient view: never rewrite the frozen release QC.
        qc = dict(qc or {})
        layers = dict(qc.get("layers") or {})
        layers[expression_layer_id] = {
            **layers.get(expression_layer_id, {}),
            "patients": layer_coverage["patient_count"],
            "endpoints": layer_coverage["endpoints"],
        }
        qc["layers"] = layers
    return derive_repository_capabilities(
        qc,
        expression_layer_id=expression_layer_id,
    )


def _private_repository_capabilities(
    context: RepositoryContext,
) -> dict[str, dict[str, Any]] | None:
    """Use upload-time QC thresholds for private, targeted matrices.

    External releases require broad transcriptomes, while a private upload may
    validly run a targeted survival or expression comparison with fewer genes.
    The upload validator persists those module-specific decisions in dataset
    metadata, so they must not be replaced by the external 10,000-gene rule.
    """

    if context.dataset.visibility != "private":
        return None
    declared = (context.dataset.metadata_json or {}).get("capabilities")
    if not isinstance(declared, Mapping):
        return None

    def detail(name: str) -> dict[str, Any]:
        raw = declared.get(name)
        if not isinstance(raw, Mapping):
            return {
                "available": False,
                "reason": "Capability was not attested during upload QC.",
            }
        normalized = dict(raw)
        normalized["available"] = bool(raw.get("available"))
        normalized.setdefault(
            "reason",
            None
            if normalized["available"]
            else "Capability was not attested during upload QC.",
        )
        return normalized

    expression_comparison = detail(CAPABILITY_EXPRESSION_COMPARISON)
    return {
        CAPABILITY_EXPRESSION: dict(expression_comparison),
        CAPABILITY_EXPRESSION_COMPARISON: expression_comparison,
        CAPABILITY_GSEA: detail(CAPABILITY_GSEA),
        CAPABILITY_SURVIVAL: detail(CAPABILITY_SURVIVAL),
    }


def require_repository_capability(
    source: RepositoryContext
    | RepositoryRelease
    | Mapping[str, Any]
    | None,
    analysis_type: str,
    *,
    expression_layer_id: str | None = None,
    layer_coverage: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return capability details or reject an unsupported analysis."""

    capability = capability_for_analysis_type(analysis_type)
    details = repository_capabilities(
        source,
        expression_layer_id=expression_layer_id,
        layer_coverage=layer_coverage,
    )[capability]
    if not bool(details.get("available")):
        reason = str(details.get("reason") or "Capability is unavailable.")
        raise ValueError(
            f"Repository data do not support {analysis_type!r}: {reason}"
        )
    return details


def list_repository_datasets(
    db: Session,
    *,
    cancer_code: str | None = None,
    analysis_type: str | None = None,
    include_unavailable: bool = False,
    include_metadata: bool = True,
) -> list[dict[str, Any]]:
    required_capability = (
        capability_for_analysis_type(analysis_type)
        if analysis_type is not None
        else None
    )
    stmt = (
        select(RepositoryDataset, RepositoryRelease, CancerType)
        .join(
            RepositoryRelease,
            RepositoryRelease.id == RepositoryDataset.active_release_id,
            isouter=True,
        )
        .join(CancerType, CancerType.code == RepositoryDataset.cancer_code)
        .order_by(CancerType.sort_order, RepositoryDataset.name)
    )
    if cancer_code:
        stmt = stmt.where(RepositoryDataset.cancer_code == cancer_code.upper())
    if not include_unavailable:
        stmt = stmt.where(
            RepositoryDataset.status == "available",
            RepositoryRelease.status == "published",
            RepositoryRelease.qc_status == "passed",
        )
    stmt = stmt.where(RepositoryDataset.visibility == "public")
    rows = db.execute(stmt).all()
    release_ids = [
        release.id
        for _, release, _ in rows
        if release is not None
    ]
    default_layers_by_release: dict[str, RepositoryExpressionLayer] = {}
    endpoints_by_release: dict[
        str, list[RepositoryEndpointDefinition]
    ] = {}
    if release_ids:
        for layer in db.scalars(
            select(RepositoryExpressionLayer)
            .where(
                RepositoryExpressionLayer.release_id.in_(release_ids),
                RepositoryExpressionLayer.is_default.is_(True),
            )
            .order_by(
                RepositoryExpressionLayer.release_id,
                RepositoryExpressionLayer.layer_id,
            )
        ).all():
            default_layers_by_release.setdefault(layer.release_id, layer)
        for endpoint in db.scalars(
            select(RepositoryEndpointDefinition)
            .where(
                RepositoryEndpointDefinition.release_id.in_(release_ids),
                RepositoryEndpointDefinition.available.is_(True),
            )
            .order_by(
                RepositoryEndpointDefinition.release_id,
                RepositoryEndpointDefinition.endpoint_id,
            )
        ).all():
            endpoints_by_release.setdefault(endpoint.release_id, []).append(
                endpoint
            )
    payload: list[dict[str, Any]] = []
    for dataset, release, cancer in rows:
        default_layer = (
            default_layers_by_release.get(release.id)
            if release
            else None
        )
        endpoints = (
            endpoints_by_release.get(release.id, [])
            if release
            else []
        )
        capabilities = repository_capabilities(
            release,
            expression_layer_id=(
                default_layer.layer_id if default_layer is not None else None
            ),
        )
        if required_capability and not capabilities[
            required_capability
        ]["available"]:
            continue
        item = {
                "id": dataset.id,
                "kind": "external",
                "cancer_code": cancer.code,
                "tcga_cohort": cancer.tcga_cohort,
                "cancer_name": cancer.name,
                "name": dataset.name,
                "description": dataset.description,
                "cohort_context": dataset.cohort_context,
                "source_provider": dataset.source_provider,
                "source_accession": dataset.source_accession,
                "source_url": dataset.source_url,
                "publication_citation": dataset.publication_citation,
                "publication_id": dataset.publication_id,
                "assay": dataset.assay,
                "independence_status": dataset.independence_status,
                "license_id": dataset.license_id,
                "license_url": dataset.license_url,
                "redistribution_allowed": dataset.redistribution_allowed,
                "status": dataset.status,
                "active_release_id": release.id if release else None,
                "release_version": release.version if release else None,
                "manifest_hash": release.manifest_hash if release else None,
                "patient_count": release.patient_count if release else 0,
                "sample_count": release.sample_count if release else 0,
                "gene_count": release.gene_count if release else 0,
                "qc_status": release.qc_status if release else None,
                "capabilities": capabilities,
                "available_modules": available_repository_modules(
                    capabilities
                ),
                "endpoints": [
                    {
                        "value": endpoint.endpoint_id,
                        "label": endpoint.label,
                        "standard_code": endpoint.standard_code,
                        "patient_count": endpoint.patient_count,
                        "event_count": endpoint.event_count,
                        "time_origin": endpoint.time_origin,
                        "event_definition": endpoint.event_definition,
                        "source_time_unit": endpoint.source_time_unit,
                    }
                    for endpoint in endpoints
                ],
                "expression_layer": (
                    {
                        "layer_id": default_layer.layer_id,
                        "label": default_layer.label,
                        "source_unit": default_layer.source_unit,
                        "analysis_unit": default_layer.analysis_unit,
                        "transform": default_layer.transform,
                        "scale_note": (
                            default_layer.metadata_json or {}
                        ).get("scale_note"),
                    }
                    if default_layer
                    else None
                ),
            }
        if include_metadata:
            item["metadata"] = dataset.metadata_json or {}
        payload.append(item)
    return payload


def repository_dataset_detail(
    db: Session, context: RepositoryContext
) -> dict[str, Any]:
    summary = next(
        row
        for row in list_repository_datasets(
            db, cancer_code=context.cancer.code, include_unavailable=True
        )
        if row["id"] == context.dataset.id
    )
    summary["endpoints"] = repository_endpoint_options(db, context)
    summary["expression_layers"] = repository_expression_layers(db, context)
    summary["qc"] = context.release.qc_json
    return summary


def repository_data_provenance(
    context: RepositoryContext,
    layer: RepositoryExpressionLayer,
    *,
    selected_sample_ids: set[str],
) -> dict[str, Any]:
    _, metadata_path = repository_expression_layer_paths(context, layer)
    metadata = read_matrix_metadata(metadata_path)
    is_private = context.dataset.visibility == "private"
    return {
        "schema_version": (
            "trace-user-data-provenance-v1"
            if is_private
            else "tcga-trace-external-data-provenance-v1"
        ),
        "dataset_kind": "user" if is_private else "external",
        "dataset_id": context.dataset.id,
        "dataset_release_id": context.release.id,
        "manifest_hash": context.release.manifest_hash,
        "source_provider": context.dataset.source_provider,
        "source_accession": context.dataset.source_accession,
        "source_snapshot": context.release.source_snapshot,
        "source_url": context.dataset.source_url,
        "license_id": context.dataset.license_id,
        "independence_status": context.dataset.independence_status,
        "privacy": (
            {
                "visibility": "private",
                "expires_at": (
                    context.dataset.expires_at.isoformat() + "Z"
                    if context.dataset.expires_at
                    else None
                ),
                "original_files_retained": False,
            }
            if is_private
            else None
        ),
        "expression_layer": {
            "layer_id": layer.layer_id,
            "source_unit": layer.source_unit,
            "analysis_unit": layer.analysis_unit,
            "transform": layer.transform,
            "matrix_sha256": layer.matrix_sha256,
            "mapping_source": (layer.metadata_json or {}).get("mapping_source"),
            "scale_note": (layer.metadata_json or {}).get("scale_note"),
        },
        "sample_selection": {
            "selected_sample_ids": sorted(selected_sample_ids),
            "selected_sample_count": len(selected_sample_ids),
            "matrix_sample_count": len(metadata.get("sample_ids") or []),
        },
    }
