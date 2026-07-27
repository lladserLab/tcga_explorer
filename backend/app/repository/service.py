from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session

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
from app.repository.storage import read_float32le_row, read_matrix_metadata
from app.survival import ClinicalOutcome


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
    os_time_days: float | None = None
    os_event: int | None = None


@dataclass(frozen=True)
class RepositoryContext:
    dataset: RepositoryDataset
    release: RepositoryRelease
    cancer: CancerType

    @property
    def cohort(self) -> str:
        return self.cancer.tcga_cohort


def resolve_repository_context(
    db: Session,
    dataset_id: str,
    release_id: str | None = None,
) -> RepositoryContext:
    dataset = db.get(RepositoryDataset, dataset_id)
    if dataset is None or dataset.status != "available":
        raise ValueError(f"External dataset {dataset_id!r} is not available.")
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
            "source": f"external:{context.dataset.source_provider}",
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
                source=f"external:{context.dataset.source_provider}",
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
    return [
        {
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
        }
        for row in rows
    ]


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
    metadata = read_matrix_metadata(Path(layer.metadata_path))
    expression = read_float32le_row(
        Path(layer.matrix_path),
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
    }


def list_repository_datasets(
    db: Session,
    *,
    cancer_code: str | None = None,
    include_unavailable: bool = False,
) -> list[dict[str, Any]]:
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
        stmt = stmt.where(RepositoryDataset.status == "available")
    rows = db.execute(stmt).all()
    payload: list[dict[str, Any]] = []
    for dataset, release, cancer in rows:
        default_layer = (
            db.scalar(
                select(RepositoryExpressionLayer)
                .where(
                    RepositoryExpressionLayer.release_id == release.id,
                    RepositoryExpressionLayer.is_default.is_(True),
                )
                .limit(1)
            )
            if release
            else None
        )
        payload.append(
            {
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
                "metadata": dataset.metadata_json or {},
                "active_release_id": release.id if release else None,
                "release_version": release.version if release else None,
                "manifest_hash": release.manifest_hash if release else None,
                "patient_count": release.patient_count if release else 0,
                "sample_count": release.sample_count if release else 0,
                "gene_count": release.gene_count if release else 0,
                "qc_status": release.qc_status if release else None,
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
        )
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
    metadata = read_matrix_metadata(Path(layer.metadata_path))
    return {
        "schema_version": "tcga-trace-external-data-provenance-v1",
        "dataset_id": context.dataset.id,
        "dataset_release_id": context.release.id,
        "manifest_hash": context.release.manifest_hash,
        "source_provider": context.dataset.source_provider,
        "source_accession": context.dataset.source_accession,
        "source_snapshot": context.release.source_snapshot,
        "source_url": context.dataset.source_url,
        "license_id": context.dataset.license_id,
        "independence_status": context.dataset.independence_status,
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
