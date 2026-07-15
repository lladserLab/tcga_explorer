from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import csv
import io
import json
import math
import uuid
import zipfile
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from sqlalchemy import desc, distinct, func, select
from sqlalchemy.orm import Session

from app.cache_warmup import load_cache_manifest, summarize_cache_manifest, warm_startup_cache
from app.config import get_settings
from app.database import SessionLocal, get_db, init_db, wait_for_database
from app.data_sync.sync import current_sync_status
from app.expression import (
    GeneNotFoundError,
    expression_scale_label,
    expression_scale_options,
    get_expression_for_gene,
)
from app.gene_aliases import GENE_ALIASES, resolve_gene_symbol
from app.importer import ensure_gene_index, import_cohorts_and_samples, import_tcga_cdr
from app.models import AnalysisJob, ClinicalEndpoint, Cohort, DataManifest, DataSource, GeneIndex, Sample
from app.pancancer import (
    add_concordance_labels,
    add_effect_labels,
    adjust_p_values_bh,
    meta_analysis_from_rows,
    summarize_pancancer_results,
)
from app.r_runner import compute_maxstat_cutpoint, ensure_svg_artifact, run_r_km, stable_hash
from app.r_runner import run_r_pancancer_cox
from app.schemas import (
    AnalysisBatchItemOut,
    AnalysisBatchOut,
    AnalysisBatchRequest,
    AnalysisOut,
    AnalysisRequest,
    CombinedSignatureAnalysisRequest,
    CohortOut,
    ExpressionScaleOut,
    FilterOptions,
    GeneSearchOut,
    PanCancerSurvivalOut,
    PanCancerSurvivalRequest,
    SignatureSpec,
)
from app.survival import (
    ClinicalOutcome,
    build_combined_survival_records,
    build_survival_records,
    filter_samples,
    percentile,
    sample_os_outcome,
    validate_records,
)

settings = get_settings()
ANALYSIS_PIPELINE_VERSION = "clinical-adjusted-cox-v4.0"
COMBINED_SIGNATURE_PIPELINE_VERSION = "combined-signatures-clinical-adjusted-cox-v2.0"
PANCANCER_PIPELINE_VERSION = "pancancer-cox-v1.0"
ENDPOINT_LABELS = {
    "OS": "Overall survival",
    "PFI": "Progression-free interval",
    "DFI": "Disease-free interval",
    "DSS": "Disease-specific survival",
}
ENDPOINT_MIN_PATIENTS = 10
ENDPOINT_MIN_EVENTS = 5

app = FastAPI(title=settings.app_name, version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup() -> None:
    wait_for_database()
    init_db()
    settings.artifact_dir.mkdir(parents=True, exist_ok=True)
    settings.derived_expression_dir.mkdir(parents=True, exist_ok=True)
    if settings.bootstrap_on_startup:
        with SessionLocal() as db:
            import_cohorts_and_samples(db, settings.tcga_data_dir)
            import_tcga_cdr(db, settings.tcga_cdr_path)
            if settings.preload_cache_on_startup:
                warm_startup_cache(db, settings)


SessionDep = Annotated[Session, Depends(get_db)]


@app.get("/api/health")
def health(db: SessionDep) -> dict:
    cohorts = db.scalar(select(func.count()).select_from(Cohort))
    cache_manifest = load_cache_manifest(settings.derived_expression_dir)
    return {
        "status": "ok",
        "cohorts": cohorts,
        "data_dir": str(settings.tcga_data_dir),
        "cache": summarize_cache_manifest(cache_manifest),
        "data_dates": dataset_dates(db, cache_manifest),
    }


@app.get("/api/cache/status")
def cache_status() -> dict:
    manifest = load_cache_manifest(settings.derived_expression_dir)
    if manifest is None:
        return {"status": "missing"}
    return manifest


@app.get("/api/dataset/summary")
def dataset_summary(db: SessionDep, cohort: str | None = None) -> dict:
    return build_dataset_summary(db, cohort)


@app.get("/api/dataset/summary/download/{kind}")
def dataset_summary_download(kind: str, db: SessionDep, cohort: str | None = None) -> Response:
    if kind != "csv":
        raise HTTPException(status_code=404, detail="Unsupported summary download type.")
    summary = build_dataset_summary(db, cohort)
    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=[
            "id",
            "primary_site",
            "sample_count",
            "patient_count",
            "event_count",
            "n_primary_tumor",
            "n_solid_normal",
            "n_other_samples",
            "n_genes",
            "disease_type",
        ],
    )
    writer.writeheader()
    for row in summary["cohorts"]:
        writer.writerow(row)
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=tcga_dataset_summary.csv"},
    )


@app.get("/api/data-sources")
def data_sources(db: SessionDep) -> dict:
    return {"sources": list_data_sources(db)}


@app.get("/api/data-sync/status")
def data_sync_status() -> dict:
    return current_sync_status()


@app.get("/api/endpoints")
def endpoint_options(db: SessionDep) -> dict:
    return {
        "endpoints": [
            global_endpoint_status(db, endpoint)
            for endpoint in ENDPOINT_LABELS
        ]
    }


@app.get("/api/cohorts/{cohort_id}/endpoints")
def cohort_endpoint_options(cohort_id: str, db: SessionDep) -> dict:
    if db.get(Cohort, cohort_id) is None:
        raise HTTPException(status_code=404, detail="Cohort not found.")
    return {"cohort": cohort_id, "endpoints": endpoint_options_for_cohort(db, cohort_id)}


@app.get("/api/cohorts/{cohort_id}/genes/resolve")
def resolve_gene(cohort_id: str, db: SessionDep, query: str) -> dict:
    if db.get(Cohort, cohort_id) is None:
        raise HTTPException(status_code=404, detail="Cohort not found.")
    return resolve_gene_symbol(db, settings.tcga_data_dir, cohort_id, query)


def build_dataset_summary(db: Session, cohort: str | None = None) -> dict:
    if cohort and db.get(Cohort, cohort) is None:
        raise HTTPException(status_code=404, detail="Cohort not found.")
    cache_manifest = load_cache_manifest(settings.derived_expression_dir)
    cohort_stmt = select(Cohort).order_by(Cohort.id)
    if cohort:
        cohort_stmt = cohort_stmt.where(Cohort.id == cohort)
    cohort_rows = list(db.scalars(cohort_stmt).all())
    total_cohorts = len(cohort_rows)
    total_samples = int(db.scalar(sample_count_stmt(cohort)) or 0)
    patient_stmt = select(Sample.cohort, func.count(distinct(Sample.patient_id)))
    sample_stmt = select(Sample.cohort, func.count())
    if cohort:
        patient_stmt = patient_stmt.where(Sample.cohort == cohort)
        sample_stmt = sample_stmt.where(Sample.cohort == cohort)
    patient_counts = dict(
        db.execute(
            patient_stmt.group_by(Sample.cohort)
        ).all()
    )
    sample_counts = dict(
        db.execute(
            sample_stmt.group_by(Sample.cohort)
        ).all()
    )
    event_stmt = select(Sample.cohort, func.count()).where(Sample.os_event == 1)
    if cohort:
        event_stmt = event_stmt.where(Sample.cohort == cohort)
    event_counts = dict(db.execute(event_stmt.group_by(Sample.cohort)).all())
    total_patients = int(sum(patient_counts.values()))
    usable_stmt = select(func.count()).select_from(Sample).where(Sample.os_time_days.is_not(None)).where(Sample.os_event.is_not(None))
    events_stmt = select(func.count()).select_from(Sample).where(Sample.os_event == 1)
    age_stmt = select(func.count()).select_from(Sample).where(Sample.age_at_index.is_not(None))
    if cohort:
        usable_stmt = usable_stmt.where(Sample.cohort == cohort)
        events_stmt = events_stmt.where(Sample.cohort == cohort)
        age_stmt = age_stmt.where(Sample.cohort == cohort)
    usable_os = int(db.scalar(usable_stmt) or 0)
    events = int(db.scalar(events_stmt) or 0)
    age_available = int(db.scalar(age_stmt) or 0)

    cohort_overview = [
        {
            "id": cohort.id,
            "disease_type": cohort.disease_type,
            "primary_site": cohort.primary_site,
            "sample_count": int(sample_counts.get(cohort.id, 0)),
            "patient_count": int(patient_counts.get(cohort.id, 0)),
            "event_count": int(event_counts.get(cohort.id, 0)),
            "n_primary_tumor": cohort.n_primary_tumor,
            "n_solid_normal": cohort.n_solid_normal,
            "n_other_samples": cohort.n_other_samples,
            "n_genes": cohort.n_genes,
        }
        for cohort in cohort_rows
    ]

    return {
        "data_dates": dataset_dates(db, cache_manifest),
        "data_sync": data_sync_summary(db),
        "data_sources": list_data_sources(db),
        "endpoint_coverage": endpoint_coverage(db, cohort),
        "totals": {
            "cohorts": total_cohorts,
            "samples": total_samples,
            "patients": total_patients,
            "usable_os_samples": usable_os,
            "events": events,
            "age_available": age_available,
            "genes_per_cohort": cohort_rows[0].n_genes if cohort_rows else None,
        },
        "metadata_coverage": metadata_coverage(db, total_samples, cohort),
        "distributions": {
            "sample_types": distribution(db, Sample.sample_type, cohort=cohort),
            "vital_status": distribution(db, Sample.vital_status, cohort=cohort),
            "gender": distribution(db, Sample.gender, cohort=cohort),
            "race": distribution(db, Sample.race, cohort=cohort),
            "stage": distribution(db, Sample.stage, cohort=cohort),
            "grade": distribution(db, Sample.grade, cohort=cohort),
            "primary_site": cohort_weighted_distribution(db, cohort),
            "age_bins": age_bins(db, cohort),
        },
        "cohorts": cohort_overview,
        "biological_annotations": biological_annotations(cohort),
        "cache": summarize_cache_manifest(cache_manifest),
    }


def list_data_sources(db: Session) -> list[dict]:
    rows = list(db.scalars(select(DataSource).order_by(DataSource.id)).all())
    return [
        {
            "id": row.id,
            "label": row.label,
            "kind": row.kind,
            "status": row.status,
            "source_url": row.source_url,
            "source_path": row.source_path,
            "source_file_modified_at": iso_datetime(row.source_file_modified_at),
            "imported_at": iso_datetime(row.imported_at),
            "metadata": row.metadata_json or {},
        }
        for row in rows
    ]


def global_endpoint_status(db: Session, endpoint: str) -> dict:
    source = db.get(DataSource, "tcga_cdr")
    records = int(
        db.scalar(select(func.count()).select_from(ClinicalEndpoint).where(ClinicalEndpoint.endpoint == endpoint))
        or 0
    )
    if records:
        return {
            "value": endpoint,
            "label": ENDPOINT_LABELS[endpoint],
            "available": True,
            "source": "tcga_cdr",
            "reason": f"{records} TCGA-CDR patient endpoint records imported.",
        }
    if endpoint == "OS":
        return {
            "value": endpoint,
            "label": ENDPOINT_LABELS[endpoint],
            "available": True,
            "source": "derived_sample_metadata",
            "reason": "Fallback OS derived from TCGA clinical/sample metadata.",
        }
    return {
        "value": endpoint,
        "label": ENDPOINT_LABELS[endpoint],
        "available": False,
        "source": "tcga_cdr",
        "reason": f"TCGA-CDR is {source.status if source else 'not configured'}.",
    }


def endpoint_options_for_cohort(db: Session, cohort_id: str) -> list[dict]:
    return [endpoint_option_for_cohort(db, cohort_id, endpoint) for endpoint in ENDPOINT_LABELS]


def endpoint_option_for_cohort(db: Session, cohort_id: str, endpoint: str) -> dict:
    cdr_outcomes = clinical_endpoint_outcomes(db, cohort_id, endpoint)
    if cdr_outcomes:
        patients = len(cdr_outcomes)
        events = sum(outcome.event for outcome in cdr_outcomes.values())
        available = patients >= ENDPOINT_MIN_PATIENTS and events >= ENDPOINT_MIN_EVENTS
        reason = (
            f"{patients} linked patients and {events} events from TCGA-CDR."
            if available
            else f"Requires at least {ENDPOINT_MIN_PATIENTS} linked patients and {ENDPOINT_MIN_EVENTS} events; found {patients} patients and {events} events."
        )
        return {
            "value": endpoint,
            "label": ENDPOINT_LABELS[endpoint],
            "available": available,
            "source": "tcga_cdr",
            "patients": patients,
            "events": events,
            "reason": reason,
        }

    if endpoint == "OS":
        patients = int(
            db.scalar(
                select(func.count(distinct(Sample.patient_id)))
                .where(Sample.cohort == cohort_id)
                .where(Sample.os_time_days.is_not(None))
                .where(Sample.os_event.is_not(None))
            )
            or 0
        )
        events = int(
            db.scalar(
                select(func.count(distinct(Sample.patient_id)))
                .where(Sample.cohort == cohort_id)
                .where(Sample.os_event == 1)
            )
            or 0
        )
        available = patients >= ENDPOINT_MIN_PATIENTS and events >= ENDPOINT_MIN_EVENTS
        return {
            "value": "OS",
            "label": ENDPOINT_LABELS["OS"],
            "available": available,
            "source": "derived_sample_metadata",
            "patients": patients,
            "events": events,
            "reason": "Fallback OS derived from TCGA clinical/sample metadata.",
        }

    source = db.get(DataSource, "tcga_cdr")
    return {
        "value": endpoint,
        "label": ENDPOINT_LABELS[endpoint],
        "available": False,
        "source": "tcga_cdr",
        "patients": 0,
        "events": 0,
        "reason": f"TCGA-CDR endpoint data are not available for this cohort; source status is {source.status if source else 'not configured'}.",
    }


def endpoint_coverage(db: Session, cohort: str | None = None) -> list[dict]:
    cohorts = [cohort] if cohort else list(db.scalars(select(Cohort.id).order_by(Cohort.id)).all())
    result = []
    for cohort_id in cohorts:
        for option in endpoint_options_for_cohort(db, cohort_id):
            result.append({"cohort": cohort_id, **option})
    return result


def clinical_endpoint_outcomes(db: Session, cohort_id: str, endpoint: str) -> dict[str, ClinicalOutcome]:
    rows = list(
        db.scalars(
            select(ClinicalEndpoint)
            .where(ClinicalEndpoint.source_id == "tcga_cdr")
            .where(ClinicalEndpoint.cohort == cohort_id)
            .where(ClinicalEndpoint.endpoint == endpoint)
        ).all()
    )
    if not rows:
        return {}
    sample_patients = set(db.scalars(select(Sample.patient_id).where(Sample.cohort == cohort_id)).all())
    return {
        row.patient_id: ClinicalOutcome(
            endpoint=row.endpoint,
            time_days=float(row.time_days),
            event=int(row.event),
            source=row.source_id,
        )
        for row in rows
        if row.patient_id in sample_patients
    }


def selected_endpoint_outcomes(db: Session, cohort_id: str, endpoint: str) -> tuple[dict[str, ClinicalOutcome] | None, dict]:
    option = endpoint_option_for_cohort(db, cohort_id, endpoint)
    if not option["available"]:
        raise ValueError(f"Endpoint {endpoint} is not available for {cohort_id}: {option['reason']}")
    if option["source"] == "tcga_cdr":
        return clinical_endpoint_outcomes(db, cohort_id, endpoint), option
    return None, option


@app.get("/api/expression-scales", response_model=list[ExpressionScaleOut])
def list_expression_scales() -> list[dict[str, str]]:
    return expression_scale_options()


@app.get("/api/cohorts", response_model=list[CohortOut])
def list_cohorts(db: SessionDep) -> list[Cohort]:
    return list(db.scalars(select(Cohort).order_by(Cohort.id)).all())


@app.get("/api/cohorts/{cohort_id}/genes", response_model=GeneSearchOut)
def search_genes(cohort_id: str, db: SessionDep, query: str = "", limit: int = 25) -> GeneSearchOut:
    cohort = db.get(Cohort, cohort_id)
    if cohort is None:
        raise HTTPException(status_code=404, detail="Cohort not found.")
    ensure_gene_index(db, settings.tcga_data_dir, cohort_id)
    max_limit = min(limit, 100)
    normalized = query.strip().upper()
    genes: list[str] = []

    def add_gene(symbol: str | None) -> None:
        if symbol and symbol not in genes:
            genes.append(symbol)

    if normalized:
        for alias, current_symbol in GENE_ALIASES.items():
            if alias.startswith(normalized) or current_symbol.startswith(normalized):
                exists = db.scalar(
                    select(GeneIndex.id)
                    .where(GeneIndex.cohort == cohort_id)
                    .where(GeneIndex.gene_symbol == current_symbol)
                    .limit(1)
                )
                if exists:
                    add_gene(current_symbol)
        prefix_stmt = (
            select(GeneIndex.gene_symbol)
            .where(GeneIndex.cohort == cohort_id)
            .where(GeneIndex.gene_symbol.like(f"{normalized}%"))
            .order_by(GeneIndex.gene_symbol)
            .limit(max_limit)
        )
        for symbol in db.scalars(prefix_stmt).all():
            add_gene(symbol)
        if len(genes) < max_limit:
            contains_stmt = (
                select(GeneIndex.gene_symbol)
                .where(GeneIndex.cohort == cohort_id)
                .where(GeneIndex.gene_symbol.like(f"%{normalized}%"))
                .order_by(GeneIndex.gene_symbol)
                .limit(max_limit)
            )
            for symbol in db.scalars(contains_stmt).all():
                add_gene(symbol)
                if len(genes) >= max_limit:
                    break
    else:
        stmt = select(GeneIndex.gene_symbol).where(GeneIndex.cohort == cohort_id).order_by(GeneIndex.gene_symbol).limit(max_limit)
        genes = list(db.scalars(stmt).all())
    return GeneSearchOut(cohort=cohort_id, query=query, genes=genes)


@app.get("/api/cohorts/{cohort_id}/filters", response_model=FilterOptions)
def filter_options(cohort_id: str, db: SessionDep) -> FilterOptions:
    if db.get(Cohort, cohort_id) is None:
        raise HTTPException(status_code=404, detail="Cohort not found.")

    def values(column) -> list[str]:
        stmt = (
            select(distinct(column))
            .where(Sample.cohort == cohort_id)
            .where(column.is_not(None))
            .order_by(column)
        )
        return [value for value in db.scalars(stmt).all() if value]

    age_min = db.scalar(select(func.min(Sample.age_at_index)).where(Sample.cohort == cohort_id))
    age_max = db.scalar(select(func.max(Sample.age_at_index)).where(Sample.cohort == cohort_id))
    os_max = db.scalar(select(func.max(Sample.os_time_days)).where(Sample.cohort == cohort_id))
    return FilterOptions(
        sample_types=values(Sample.sample_type),
        stages=values(Sample.stage),
        grades=values(Sample.grade),
        genders=values(Sample.gender),
        races=values(Sample.race),
        age_min=age_min,
        age_max=age_max,
        os_time_max_days=os_max,
    )


@app.post("/api/analyses", response_model=AnalysisOut)
def create_analysis(request: AnalysisRequest, db: SessionDep) -> AnalysisOut:
    return _create_analysis(request, db)


def _create_analysis(request: AnalysisRequest, db: Session) -> AnalysisOut:
    payload = request.model_dump(mode="json")
    payload["pipeline_version"] = ANALYSIS_PIPELINE_VERSION
    payload["data_version"] = current_data_version(db)
    params_hash = stable_hash(payload)
    existing = db.scalar(select(AnalysisJob).where(AnalysisJob.params_hash == params_hash))
    if existing and existing.status == "completed" and _artifacts_exist(existing):
        existing.cached = True
        db.commit()
        return analysis_out(existing)

    cohort = db.get(Cohort, request.cohort)
    if cohort is None:
        raise HTTPException(status_code=404, detail="Cohort not found.")

    if existing:
        analysis_id = existing.id
        job = existing
        job.status = "running"
        job.cohort = request.cohort
        job.gene_symbol = request.gene_symbol.strip().upper()
        job.cutpoint_method = request.cutpoint_method
        job.request_payload = payload
        job.metrics = None
        job.warnings = []
        job.png_path = None
        job.svg_path = None
        job.csv_path = None
        job.json_path = None
        job.error = None
        job.cached = False
    else:
        analysis_id = uuid.uuid4().hex
        job = AnalysisJob(
            id=analysis_id,
            params_hash=params_hash,
            status="running",
            cohort=request.cohort,
            gene_symbol=request.gene_symbol.strip().upper(),
            cutpoint_method=request.cutpoint_method,
            request_payload=payload,
            warnings=[],
        )
        db.add(job)
    db.commit()

    try:
        endpoint_by_patient, endpoint_option = selected_endpoint_outcomes(db, request.cohort, request.endpoint)
        endpoint_label = endpoint_option["label"]
        expression, signature_info, gene_warnings = expression_for_request(
            db,
            request,
        )
        job.gene_symbol = signature_info["label"]
        samples = list(db.scalars(select(Sample).where(Sample.cohort == request.cohort)).all())
        filtered, filter_warnings, sample_selection = filter_samples(
            samples,
            request.filters,
            endpoint_by_patient=endpoint_by_patient,
            endpoint=request.endpoint,
            endpoint_label=endpoint_label,
        )
        warnings = gene_warnings + filter_warnings
        if request.filters.max_time_days is not None:
            warnings.append(
                f"Patients with follow-up time exceeding {request.filters.max_time_days:.0f} days are administratively censored at that time point (event = 0)."
            )
        precomputed_cutpoint = None
        if request.cutpoint_method == "maxstat":
            maxstat_records = _maxstat_records(filtered, expression, endpoint_by_patient, request.filters.max_time_days)
            precomputed_cutpoint = compute_maxstat_cutpoint(settings, analysis_id, maxstat_records)
        records, group_levels, cutpoint_details = build_survival_records(
            filtered,
            expression,
            request.cutpoint_method,
            request.custom_percentile,
            endpoint_by_patient=endpoint_by_patient,
            endpoint=request.endpoint,
            precomputed_cutpoint=precomputed_cutpoint,
            max_time_days=request.filters.max_time_days,
        )
        validate_records(records, endpoint_label)
        metrics = run_r_km(
            settings=settings,
            analysis_id=analysis_id,
            cohort=request.cohort,
            gene_symbol=job.gene_symbol,
            endpoint=request.endpoint,
            endpoint_label=endpoint_label,
            cutpoint_method=request.cutpoint_method,
            records=records,
            group_levels=group_levels,
            cutpoint_details=cutpoint_details,
            show_confidence_interval=request.show_confidence_interval,
            show_risk_table=request.show_risk_table,
            plot_style=request.plot_style.model_dump(mode="json"),
            expression_scale=request.expression_scale,
            expression_scale_label=expression_scale_label(request.expression_scale),
            time_unit=request.time_unit,
            request_payload=payload,
            analysis_warnings=warnings,
            data_dates=dataset_dates(db, load_cache_manifest(settings.derived_expression_dir)),
            sample_selection=sample_selection,
        )
        metrics["endpoint"] = request.endpoint
        metrics["endpoint_label"] = endpoint_label
        metrics["endpoint_source"] = endpoint_option["source"]
        metrics["endpoint_qc"] = endpoint_option
        metrics["signature"] = signature_info
        metrics["sample_selection"] = sample_selection
        metrics["expression_distribution"] = expression_distribution(filtered, expression)
        metrics["quality"] = quality_summary(records)
        artifacts = metrics.pop("artifact_paths")
        job.status = "completed"
        job.metrics = metrics
        job.warnings = warnings + metrics.get("warnings", [])
        job.png_path = artifacts["png"]
        job.svg_path = artifacts["svg"]
        job.csv_path = artifacts["csv"]
        job.json_path = artifacts["json"]
        job.error = None
        db.commit()
    except GeneNotFoundError as exc:
        _fail_job(db, job, str(exc))
        raise analysis_http_error(404, "NO_GENE", str(exc)) from exc
    except ValueError as exc:
        _fail_job(db, job, str(exc))
        code = classify_value_error(str(exc))
        raise analysis_http_error(422, code, str(exc)) from exc
    except Exception as exc:
        _fail_job(db, job, str(exc))
        code = "R_FAILED" if "Rscript failed" in str(exc) else "ANALYSIS_FAILED"
        raise analysis_http_error(500, code, str(exc)) from exc

    return analysis_out(job)


@app.post("/api/analyses/combined", response_model=AnalysisOut)
def create_combined_analysis(request: CombinedSignatureAnalysisRequest, db: SessionDep) -> AnalysisOut:
    return _create_combined_analysis(request, db)


def _create_combined_analysis(request: CombinedSignatureAnalysisRequest, db: Session) -> AnalysisOut:
    payload = request.model_dump(mode="json")
    payload["pipeline_version"] = COMBINED_SIGNATURE_PIPELINE_VERSION
    payload["data_version"] = current_data_version(db)
    params_hash = stable_hash(payload)
    existing = db.scalar(select(AnalysisJob).where(AnalysisJob.params_hash == params_hash))
    if existing and existing.status == "completed" and _artifacts_exist(existing):
        existing.cached = True
        db.commit()
        return analysis_out(existing)

    cohort = db.get(Cohort, request.cohort)
    if cohort is None:
        raise HTTPException(status_code=404, detail="Cohort not found.")

    signature_a_name = normalized_signature_name(request.signature_a.name, "Signature A")
    signature_b_name = normalized_signature_name(request.signature_b.name, "Signature B")
    combined_label = f"{signature_a_name} x {signature_b_name}"
    cutpoint_method = f"combined_{request.combination_method}"

    if existing:
        analysis_id = existing.id
        job = existing
        job.status = "running"
        job.cohort = request.cohort
        job.gene_symbol = combined_label
        job.cutpoint_method = cutpoint_method
        job.request_payload = payload
        job.metrics = None
        job.warnings = []
        job.png_path = None
        job.svg_path = None
        job.csv_path = None
        job.json_path = None
        job.error = None
        job.cached = False
    else:
        analysis_id = uuid.uuid4().hex
        job = AnalysisJob(
            id=analysis_id,
            params_hash=params_hash,
            status="running",
            cohort=request.cohort,
            gene_symbol=combined_label,
            cutpoint_method=cutpoint_method,
            request_payload=payload,
            warnings=[],
        )
        db.add(job)
    db.commit()

    try:
        endpoint_by_patient, endpoint_option = selected_endpoint_outcomes(db, request.cohort, request.endpoint)
        endpoint_label = endpoint_option["label"]
        signature_request_a = analysis_request_for_signature_spec(request, request.signature_a)
        signature_request_b = analysis_request_for_signature_spec(request, request.signature_b)
        expression_a, signature_info_a, warnings_a = expression_for_request(db, signature_request_a)
        expression_b, signature_info_b, warnings_b = expression_for_request(db, signature_request_b)
        signature_info_a = {**signature_info_a, "name": signature_a_name}
        signature_info_b = {**signature_info_b, "name": signature_b_name}

        samples = list(db.scalars(select(Sample).where(Sample.cohort == request.cohort)).all())
        filtered, filter_warnings, sample_selection = filter_samples(
            samples,
            request.filters,
            endpoint_by_patient=endpoint_by_patient,
            endpoint=request.endpoint,
            endpoint_label=endpoint_label,
        )
        warnings = prefixed_warnings("Signature A", warnings_a) + prefixed_warnings("Signature B", warnings_b) + filter_warnings
        if request.filters.max_time_days is not None:
            warnings.append(
                f"Patients with follow-up time exceeding {request.filters.max_time_days:.0f} days are administratively censored at that time point (event = 0)."
            )
        records, group_levels, cutpoint_details = build_combined_survival_records(
            filtered,
            expression_a,
            expression_b,
            request.combination_method,
            endpoint_by_patient=endpoint_by_patient,
            endpoint=request.endpoint,
            max_time_days=request.filters.max_time_days,
        )
        validate_records(records, endpoint_label)
        metrics = run_r_km(
            settings=settings,
            analysis_id=analysis_id,
            cohort=request.cohort,
            gene_symbol=combined_label,
            endpoint=request.endpoint,
            endpoint_label=endpoint_label,
            cutpoint_method=cutpoint_method,
            records=records,
            group_levels=group_levels,
            cutpoint_details=cutpoint_details,
            show_confidence_interval=request.show_confidence_interval,
            show_risk_table=request.show_risk_table,
            plot_style=request.plot_style.model_dump(mode="json"),
            expression_scale=request.expression_scale,
            expression_scale_label=expression_scale_label(request.expression_scale),
            time_unit=request.time_unit,
            request_payload=payload,
            analysis_warnings=warnings,
            data_dates=dataset_dates(db, load_cache_manifest(settings.derived_expression_dir)),
            sample_selection=sample_selection,
        )
        metrics["endpoint"] = request.endpoint
        metrics["endpoint_label"] = endpoint_label
        metrics["endpoint_source"] = endpoint_option["source"]
        metrics["endpoint_qc"] = endpoint_option
        metrics["signature"] = {
            "method": "combined",
            "label": combined_label,
            "signatures": [signature_info_a, signature_info_b],
        }
        metrics["combined_signature"] = {
            "method": request.combination_method,
            "label": combined_label,
            "signature_a": signature_info_a,
            "signature_b": signature_info_b,
            "sample_overlap": len(
                [
                    sample
                    for sample in filtered
                    if sample.barcode in expression_a and sample.barcode in expression_b
                ]
            ),
            "group_levels": group_levels,
        }
        metrics["sample_selection"] = sample_selection
        samples_with_both_scores = [
            sample for sample in filtered if sample.barcode in expression_a and sample.barcode in expression_b
        ]
        metrics["expression_distribution_a"] = expression_distribution(samples_with_both_scores, expression_a)
        metrics["expression_distribution_b"] = expression_distribution(samples_with_both_scores, expression_b)
        metrics["quality"] = quality_summary(records)
        artifacts = metrics.pop("artifact_paths")
        job.status = "completed"
        job.metrics = metrics
        job.warnings = warnings + metrics.get("warnings", [])
        job.png_path = artifacts["png"]
        job.svg_path = artifacts["svg"]
        job.csv_path = artifacts["csv"]
        job.json_path = artifacts["json"]
        job.error = None
        db.commit()
    except GeneNotFoundError as exc:
        _fail_job(db, job, str(exc))
        raise analysis_http_error(404, "NO_GENE", str(exc)) from exc
    except ValueError as exc:
        _fail_job(db, job, str(exc))
        code = classify_value_error(str(exc))
        raise analysis_http_error(422, code, str(exc)) from exc
    except Exception as exc:
        _fail_job(db, job, str(exc))
        code = "R_FAILED" if "Rscript failed" in str(exc) else "ANALYSIS_FAILED"
        raise analysis_http_error(500, code, str(exc)) from exc

    return analysis_out(job)


@app.post("/api/analyses/batch", response_model=AnalysisBatchOut)
def create_analysis_batch(request: AnalysisBatchRequest) -> AnalysisBatchOut:
    max_allowed = max(1, min(settings.analysis_batch_max_concurrency, 10))
    requested = request.max_concurrency or max_allowed
    max_concurrency = max(1, min(requested, max_allowed, len(request.analyses)))
    results: list[AnalysisBatchItemOut | None] = [None] * len(request.analyses)

    def run_item(index: int, analysis_request: AnalysisRequest) -> AnalysisBatchItemOut:
        with SessionLocal() as worker_db:
            try:
                result = _create_analysis(analysis_request, worker_db)
                return AnalysisBatchItemOut(index=index, status="completed", result=result)
            except HTTPException as exc:
                code, message = http_exception_payload(exc)
                return AnalysisBatchItemOut(index=index, status="failed", code=code, error=message)
            except Exception as exc:
                return AnalysisBatchItemOut(index=index, status="failed", code="ANALYSIS_FAILED", error=str(exc))

    with ThreadPoolExecutor(max_workers=max_concurrency) as executor:
        futures = {
            executor.submit(run_item, index, analysis_request): index
            for index, analysis_request in enumerate(request.analyses)
        }
        for future in as_completed(futures):
            item = future.result()
            results[item.index] = item

    finalized = [item for item in results if item is not None]
    completed = sum(1 for item in finalized if item.status == "completed")
    failed = len(finalized) - completed
    return AnalysisBatchOut(
        total=len(request.analyses),
        completed=completed,
        failed=failed,
        max_concurrency=max_concurrency,
        results=finalized,
    )


@app.post("/api/pancancer/survival", response_model=PanCancerSurvivalOut)
def create_pancancer_survival(request: PanCancerSurvivalRequest, db: SessionDep) -> PanCancerSurvivalOut:
    payload = request.model_dump(mode="json")
    payload["pipeline_version"] = PANCANCER_PIPELINE_VERSION
    payload["data_version"] = current_data_version(db)
    scan_id = f"pc_{stable_hash(payload)[:24]}"
    result_path = pancancer_result_path(scan_id)
    if result_path.exists():
        result = json.loads(result_path.read_text(encoding="utf-8"))
        result["cached"] = True
        result["downloads"] = pancancer_downloads(scan_id)
        result["results"] = normalize_pancancer_rows(result.get("results", []))
        return PanCancerSurvivalOut(**result)

    result = run_pancancer_survival_scan(request, db, scan_id, payload)
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(json.dumps(result, ensure_ascii=False, allow_nan=False, indent=2), encoding="utf-8")
    return PanCancerSurvivalOut(**result)


@app.get("/api/pancancer/survival/{scan_id}/download/csv")
def download_pancancer_survival(scan_id: str) -> Response:
    result_path = pancancer_result_path(scan_id)
    if not result_path.exists():
        raise HTTPException(status_code=404, detail="Pan-cancer scan not found.")
    result = json.loads(result_path.read_text(encoding="utf-8"))
    output = io.StringIO()
    fieldnames = [
        "cohort",
        "cohort_label",
        "primary_site",
        "disease_type",
        "endpoint",
        "endpoint_label",
        "endpoint_source",
        "status",
        "code",
        "reason",
        "n_patients",
        "n_events",
        "hazard_ratio",
        "hr_conf_low",
        "hr_conf_high",
        "log_hr",
        "standard_error",
        "p_value",
        "fdr",
        "ph_p_value",
        "direction",
        "effect_category",
        "significant",
        "concordance",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for row in result.get("results", []):
        writer.writerow({field: row.get(field) for field in fieldnames})
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={scan_id}.pancancer_survival.csv"},
    )


@app.get("/api/pancancer/immune-screens")
def list_immune_pancancer_screens() -> dict:
    root = settings.artifact_dir / "immune_pancancer"
    screens = []
    for summary_path in sorted(root.glob("*/screen_summary.json"), key=lambda path: path.stat().st_mtime, reverse=True):
        try:
            payload = json.loads(summary_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        screen_id = summary_path.parent.name
        screens.append(
            {
                "screen_id": screen_id,
                "headline": payload.get("headline", {}),
                "created_at": payload.get("created_at"),
                "downloads": immune_screen_downloads(screen_id),
            }
        )
    return {"screens": screens}


@app.get("/api/pancancer/immune-screens/{screen_id}")
def get_immune_pancancer_screen(screen_id: str) -> dict:
    summary_path = immune_screen_path(screen_id) / "screen_summary.json"
    if not summary_path.exists():
        raise HTTPException(status_code=404, detail="Immune pan-cancer screen not found.")
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    payload["downloads"] = immune_screen_downloads(screen_id)
    return payload


@app.get("/api/pancancer/immune-screens/{screen_id}/download/{kind}")
def download_immune_pancancer_screen(screen_id: str, kind: str) -> FileResponse:
    file_map = {
        "genes": ("gene_summary.csv", "text/csv"),
        "cohorts": ("cohort_summary.csv", "text/csv"),
        "terms": ("term_summary.csv", "text/csv"),
        "results": ("results_long.csv", "text/csv"),
        "panel": ("immune_gene_panel.tsv", "text/tab-separated-values"),
        "manifest": ("manifest.json", "application/json"),
        "methodology": ("methodology.txt", "text/plain"),
    }
    if kind not in file_map:
        raise HTTPException(status_code=404, detail="Unsupported immune screen download type.")
    filename, media_type = file_map[kind]
    path = immune_screen_path(screen_id) / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="Immune screen file is not available.")
    return FileResponse(path, media_type=media_type, filename=f"{screen_id}.{filename}")


@app.get("/api/analyses/{analysis_id}", response_model=AnalysisOut)
def get_analysis(analysis_id: str, db: SessionDep) -> AnalysisOut:
    job = db.get(AnalysisJob, analysis_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Analysis not found.")
    return analysis_out(job)


@app.get("/api/analyses/{analysis_id}/download/{kind}")
def download_analysis(analysis_id: str, kind: str, db: SessionDep) -> Response:
    job = db.get(AnalysisJob, analysis_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Analysis not found.")
    if kind == "zip":
        try:
            return analysis_zip_response(job, db)
        except HTTPException:
            raise
        except Exception as exc:
            raise analysis_http_error(500, "R_FAILED", str(exc)) from exc
    cox_forest_png_path = settings.artifact_dir / analysis_id / "cox_forest.png"
    cox_forest_svg_path = settings.artifact_dir / analysis_id / "cox_forest.svg"
    needs_svg_render = job.svg_path is None or not Path(job.svg_path).exists()
    if kind == "cox_svg" and not cox_forest_svg_path.exists():
        needs_svg_render = True
    if kind in {"svg", "cox_svg"} and needs_svg_render:
        try:
            job.svg_path = str(ensure_svg_artifact(settings, analysis_id))
            db.commit()
        except Exception as exc:
            raise analysis_http_error(500, "R_FAILED", str(exc)) from exc
    path_map = {
        "png": job.png_path,
        "svg": job.svg_path,
        "cox_png": str(cox_forest_png_path),
        "cox_svg": str(cox_forest_svg_path),
        "csv": job.csv_path,
        "txt": str(methodology_path(analysis_id)),
        "methodology": str(methodology_path(analysis_id)),
    }
    if kind not in path_map:
        raise HTTPException(status_code=404, detail="Unsupported download type.")
    path = path_map[kind]
    if path is None or not Path(path).exists():
        raise HTTPException(status_code=404, detail="File is not available.")
    media_type = {
        "png": "image/png",
        "svg": "image/svg+xml",
        "cox_png": "image/png",
        "cox_svg": "image/svg+xml",
        "csv": "text/csv",
        "txt": "text/plain",
        "methodology": "text/plain",
    }[kind]
    filename = {
        "methodology": f"{analysis_id}.methodology.txt",
        "cox_png": f"{analysis_id}.cox_forest.png",
        "cox_svg": f"{analysis_id}.cox_forest.svg",
    }.get(kind, f"{analysis_id}.{kind}")
    return FileResponse(path, media_type=media_type, filename=filename)


def analysis_zip_response(job: AnalysisJob, db: Session) -> Response:
    if job.status != "completed":
        raise HTTPException(status_code=404, detail="Analysis is not completed.")
    if job.svg_path is None or not Path(job.svg_path).exists():
        job.svg_path = str(ensure_svg_artifact(settings, job.id))
        db.commit()

    files = [
        ("plot.png", job.png_path),
        ("plot.svg", job.svg_path),
        ("raw_data.csv", job.csv_path),
        ("methodology.txt", str(methodology_path(job.id))),
    ]
    optional_files = [
        ("cox_forest.png", str(settings.artifact_dir / job.id / "cox_forest.png")),
        ("cox_forest.svg", str(settings.artifact_dir / job.id / "cox_forest.svg")),
    ]
    missing = [name for name, path in files if path is None or not Path(path).exists()]
    if missing:
        raise HTTPException(status_code=404, detail=f"Missing artifact files: {', '.join(missing)}.")

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, path in files:
            archive.write(Path(path), arcname=name)
        for name, path in optional_files:
            if path and Path(path).exists():
                archive.write(Path(path), arcname=name)
    return Response(
        content=buffer.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={job.id}.artifacts.zip"},
    )


def run_pancancer_survival_scan(
    request: PanCancerSurvivalRequest,
    db: Session,
    scan_id: str,
    payload: dict,
) -> dict:
    cohort_rows = pancancer_cohorts(db, request)
    prepared: list[dict] = []
    skipped_results: list[dict] = []
    signature_info: dict | None = None

    for cohort in cohort_rows:
        endpoint_option = choose_pancancer_endpoint(db, cohort.id, request.endpoint, request.endpoint_mode)
        base_result = pancancer_base_result(cohort)
        if endpoint_option is None:
            skipped_results.append(
                {
                    **base_result,
                    "endpoint": request.endpoint,
                    "endpoint_label": ENDPOINT_LABELS.get(request.endpoint, request.endpoint),
                    "status": "skipped",
                    "code": "ENDPOINT_UNAVAILABLE",
                    "reason": pancancer_endpoint_unavailable_reason(db, cohort.id, request.endpoint, request.endpoint_mode),
                    "warnings": [],
                }
            )
            continue

        try:
            analysis_request = AnalysisRequest(
                cohort=cohort.id,
                gene_symbol=request.gene_symbol,
                signature_method=request.signature_method,
                signature_genes=request.signature_genes,
                endpoint=endpoint_option["value"],
                expression_scale=request.expression_scale,
                filters=request.filters,
                cutpoint_method="median",
            )
            endpoint_by_patient, selected_option = selected_endpoint_outcomes(db, cohort.id, endpoint_option["value"])
            expression, cohort_signature, gene_warnings = expression_for_request(db, analysis_request)
            signature_info = signature_info or cohort_signature
            samples = list(db.scalars(select(Sample).where(Sample.cohort == cohort.id)).all())
            filtered, filter_warnings, sample_selection = filter_samples(
                samples,
                request.filters,
                endpoint_by_patient=endpoint_by_patient,
                endpoint=endpoint_option["value"],
                endpoint_label=selected_option["label"],
            )
            records = pancancer_continuous_records(filtered, expression, endpoint_by_patient, request.filters.max_time_days)
            prepared.append(
                {
                    **base_result,
                    "endpoint": selected_option["value"],
                    "endpoint_label": selected_option["label"],
                    "endpoint_source": selected_option["source"],
                    "records": records,
                    "warnings": gene_warnings + filter_warnings,
                    "sample_selection": sample_selection,
                }
            )
        except GeneNotFoundError as exc:
            skipped_results.append(
                {
                    **base_result,
                    "endpoint": endpoint_option["value"],
                    "endpoint_label": endpoint_option["label"],
                    "endpoint_source": endpoint_option["source"],
                    "status": "failed",
                    "code": "NO_GENE",
                    "reason": str(exc),
                    "warnings": [],
                }
            )
        except ValueError as exc:
            skipped_results.append(
                {
                    **base_result,
                    "endpoint": endpoint_option["value"],
                    "endpoint_label": endpoint_option["label"],
                    "endpoint_source": endpoint_option["source"],
                    "status": "skipped",
                    "code": classify_value_error(str(exc)),
                    "reason": str(exc),
                    "warnings": [],
                }
            )

    r_payload = (
        run_r_pancancer_cox(
            settings=settings,
            scan_id=scan_id,
            cohorts=prepared,
            min_patients=request.min_patients,
            min_events=request.min_events,
            request_payload=payload,
        )
        if prepared
        else {"results": []}
    )
    rows = skipped_results + list(r_payload.get("results", []))
    rows = apply_pancancer_postprocessing(rows, request)
    reference = add_concordance_labels(rows, request.index_cohort)
    summary = summarize_pancancer_results(rows, request.index_cohort, request.fdr_threshold)
    meta_analysis = meta_analysis_from_rows(rows)

    return {
        "scan_id": scan_id,
        "status": "completed",
        "cached": False,
        "gene_symbol": (signature_info or {}).get("label") or request.gene_symbol.strip().upper(),
        "signature": signature_info,
        "index_cohort": request.index_cohort,
        "endpoint": request.endpoint,
        "endpoint_mode": request.endpoint_mode,
        "expression_scale": request.expression_scale,
        "expression_scale_label": expression_scale_label(request.expression_scale),
        "fdr_threshold": request.fdr_threshold,
        "summary": summary,
        "reference": reference,
        "meta_analysis": meta_analysis,
        "results": rows,
        "warnings": pancancer_warnings(request),
        "downloads": pancancer_downloads(scan_id),
    }


def pancancer_cohorts(db: Session, request: PanCancerSurvivalRequest) -> list[Cohort]:
    if request.cohorts:
        cohort_ids = list(dict.fromkeys(request.cohorts))
    else:
        cohort_ids = list(db.scalars(select(Cohort.id).order_by(Cohort.id)).all())
    if request.index_cohort and request.index_cohort not in cohort_ids:
        cohort_ids.append(request.index_cohort)
    rows = list(db.scalars(select(Cohort).where(Cohort.id.in_(cohort_ids)).order_by(Cohort.id)).all())
    found = {row.id for row in rows}
    missing = [cohort_id for cohort_id in cohort_ids if cohort_id not in found]
    if missing:
        raise HTTPException(status_code=404, detail=f"Cohorts not found: {', '.join(missing)}.")
    return rows


def choose_pancancer_endpoint(db: Session, cohort_id: str, endpoint: str, endpoint_mode: str) -> dict | None:
    for candidate in pancancer_endpoint_candidates(endpoint, endpoint_mode):
        option = endpoint_option_for_cohort(db, cohort_id, candidate)
        if option["available"]:
            return option
    return None


def pancancer_endpoint_candidates(endpoint: str, endpoint_mode: str) -> list[str]:
    if endpoint_mode == "same_endpoint":
        candidates = [endpoint]
    elif endpoint_mode == "death_like":
        candidates = [endpoint if endpoint in {"OS", "DSS"} else None, "DSS", "OS"]
    elif endpoint_mode == "progression_like":
        candidates = [endpoint if endpoint in {"PFI", "DFI"} else None, "PFI", "DFI"]
    else:
        candidates = [endpoint, "DSS", "PFI", "DFI", "OS"]
    return [item for item in dict.fromkeys(candidates) if item]


def pancancer_endpoint_unavailable_reason(db: Session, cohort_id: str, endpoint: str, endpoint_mode: str) -> str:
    reasons = []
    for candidate in pancancer_endpoint_candidates(endpoint, endpoint_mode):
        option = endpoint_option_for_cohort(db, cohort_id, candidate)
        reasons.append(f"{candidate}: {option['reason']}")
    return "No endpoint passed QC for this endpoint mode. " + " ".join(reasons)


def pancancer_base_result(cohort: Cohort) -> dict:
    return {
        "cohort": cohort.id,
        "cohort_label": cohort.id,
        "disease_type": cohort.disease_type,
        "primary_site": cohort.primary_site,
    }


def pancancer_continuous_records(
    samples: list[Sample],
    expression: dict[str, float],
    endpoint_by_patient: dict[str, ClinicalOutcome] | None,
    max_time_days: float | None = None,
) -> list[dict]:
    records = []
    for sample in samples:
        if sample.barcode not in expression:
            continue
        outcome = endpoint_by_patient.get(sample.patient_id) if endpoint_by_patient is not None else sample_os_outcome(sample)
        if outcome is None:
            continue
        time_days = float(outcome.time_days)
        event = int(outcome.event)
        if max_time_days is not None and time_days > max_time_days:
            time_days = max_time_days
            event = 0
        records.append(
            {
                "patient_id": sample.patient_id,
                "sample_barcode": sample.barcode,
                "expression_value": float(expression[sample.barcode]),
                "time_days": time_days,
                "event": event,
                "sample_type": sample.sample_type,
                "stage": sample.stage,
                "gender": sample.gender,
                "race": sample.race,
                "age_at_index": sample.age_at_index,
            }
        )
    return records


def apply_pancancer_postprocessing(rows: list[dict], request: PanCancerSurvivalRequest) -> list[dict]:
    rows = normalize_pancancer_rows(rows)
    fdr_values = adjust_p_values_bh(
        [
            row.get("p_value")
            if row.get("status") == "completed"
            else None
            for row in rows
        ]
    )
    for row, fdr in zip(rows, fdr_values):
        row["fdr"] = fdr
    add_effect_labels(rows, request.fdr_threshold)
    return sorted(rows, key=lambda row: row.get("cohort") or "")


def normalize_pancancer_rows(rows: list[dict]) -> list[dict]:
    for row in rows:
        warnings = row.get("warnings")
        if warnings is None:
            row["warnings"] = []
        elif isinstance(warnings, str):
            row["warnings"] = [warnings]
        elif not isinstance(warnings, list):
            row["warnings"] = list(warnings) if isinstance(warnings, tuple) else [str(warnings)]
    return rows


def pancancer_warnings(request: PanCancerSurvivalRequest) -> list[str]:
    warnings = [
        "Primary pan-cancer effect estimates use continuous Cox models with expression z-scored within each cohort.",
        "Kaplan-Meier cutpoints are not used for the pan-cancer primary statistic.",
    ]
    if request.endpoint_mode != "same_endpoint":
        warnings.append("Endpoint mode can select different but biologically related endpoints across cohorts; compare exact endpoint labels before interpreting concordance.")
    if request.filters.max_time_days is not None:
        warnings.append(
            f"Patients with follow-up time exceeding {request.filters.max_time_days:.0f} days are administratively censored at that time point (event = 0)."
        )
    return warnings


def pancancer_result_path(scan_id: str) -> Path:
    return settings.artifact_dir / "pancancer" / scan_id / "result.json"


def pancancer_downloads(scan_id: str) -> dict[str, str]:
    return {"csv": f"/api/pancancer/survival/{scan_id}/download/csv"}


def immune_screen_path(screen_id: str) -> Path:
    if not screen_id or any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-." for char in screen_id):
        raise HTTPException(status_code=404, detail="Immune pan-cancer screen not found.")
    return settings.artifact_dir / "immune_pancancer" / screen_id


def immune_screen_downloads(screen_id: str) -> dict[str, str]:
    base = f"/api/pancancer/immune-screens/{screen_id}/download"
    return {
        "genes": f"{base}/genes",
        "cohorts": f"{base}/cohorts",
        "terms": f"{base}/terms",
        "results": f"{base}/results",
        "panel": f"{base}/panel",
        "manifest": f"{base}/manifest",
        "methodology": f"{base}/methodology",
    }


def dataset_dates(db: Session, cache_manifest: dict | None) -> dict:
    latest_source = latest_source_modified_at(settings.tcga_data_dir)
    summary_path = settings.tcga_data_dir / "summary_table.tsv"
    imported_at = db.scalar(select(func.max(Cohort.imported_at)))
    cdr_source = db.get(DataSource, "tcga_cdr")
    latest_manifest = latest_data_manifest(db)
    return {
        "source_summary_file": iso_from_path(summary_path),
        "source_latest_metadata_file": latest_source,
        "database_imported_at": iso_datetime(imported_at),
        "rna_cache_generated_at": (cache_manifest or {}).get("generated_at"),
        "tcga_cdr_source_file": iso_datetime(cdr_source.source_file_modified_at) if cdr_source else None,
        "tcga_cdr_imported_at": iso_datetime(cdr_source.imported_at) if cdr_source else None,
        "data_through_date": iso_datetime(latest_manifest.data_through_date) if latest_manifest else latest_source,
        "data_manifest_hash": latest_manifest.manifest_hash if latest_manifest else None,
    }


def latest_data_manifest(db: Session) -> DataManifest | None:
    return db.scalar(select(DataManifest).order_by(desc(DataManifest.created_at)).limit(1))


def data_sync_summary(db: Session) -> dict:
    manifests = list(db.scalars(select(DataManifest).order_by(desc(DataManifest.created_at))).all())
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
                "created_at": iso_datetime(manifest.created_at),
            }
            for source, manifest in sorted(latest_by_source.items())
        ]
    }


def current_data_version(db: Session) -> dict:
    manifests = data_sync_summary(db).get("sources", [])
    if not manifests:
        return {
            "tcga_rna_source": iso_from_path(settings.tcga_data_dir / "summary_table.tsv"),
            "tcga_cdr_source": iso_from_path(settings.tcga_cdr_path),
        }
    return {
        item["source"]: {
            "manifest_hash": item["manifest_hash"],
            "data_through_date": item["data_through_date"],
            "data_release": item["data_release"],
        }
        for item in manifests
    }


def latest_source_modified_at(tcga_data_dir: Path) -> str | None:
    paths = [tcga_data_dir / "summary_table.tsv"]
    for cohort_dir in sorted(tcga_data_dir.glob("TCGA-*")):
        paths.extend(
            [
                cohort_dir / "col_data.tsv",
                cohort_dir / "clinical_data.tsv",
                cohort_dir / "count_matrix.tsv",
            ]
        )
    timestamps = [path.stat().st_mtime for path in paths if path.exists()]
    if not timestamps:
        return None
    return datetime.fromtimestamp(max(timestamps), tz=timezone.utc).isoformat()


def iso_from_path(path: Path) -> str | None:
    if not path.exists():
        return None
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat()


def iso_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def distribution(db: Session, column, limit: int = 12, cohort: str | None = None) -> list[dict]:
    stmt = select(column, func.count()).where(column.is_not(None))
    if cohort:
        stmt = stmt.where(Sample.cohort == cohort)
    rows = db.execute(stmt.group_by(column).order_by(func.count().desc(), column).limit(limit)).all()
    return [{"label": str(label), "count": int(count)} for label, count in rows if label]


def cohort_weighted_distribution(db: Session, cohort: str | None = None, limit: int = 12) -> list[dict]:
    stmt = (
        select(Cohort.primary_site, func.count(Sample.id))
        .join(Sample, Sample.cohort == Cohort.id)
        .where(Cohort.primary_site.is_not(None))
    )
    if cohort:
        stmt = stmt.where(Cohort.id == cohort)
    rows = db.execute(stmt.group_by(Cohort.primary_site).order_by(func.count(Sample.id).desc(), Cohort.primary_site).limit(limit)).all()
    return [{"label": str(label), "count": int(count)} for label, count in rows if label]


def metadata_coverage(db: Session, total_samples: int, cohort: str | None = None) -> list[dict]:
    fields = [
        ("Sample type", Sample.sample_type),
        ("Stage", Sample.stage),
        ("Grade", Sample.grade),
        ("Gender", Sample.gender),
        ("Race", Sample.race),
        ("Age at index", Sample.age_at_index),
        ("Vital status", Sample.vital_status),
        ("Overall survival time", Sample.os_time_days),
    ]
    coverage = []
    for label, column in fields:
        stmt = select(func.count()).select_from(Sample).where(column.is_not(None))
        if cohort:
            stmt = stmt.where(Sample.cohort == cohort)
        count = int(db.scalar(stmt) or 0)
        coverage.append(
            {
                "label": label,
                "count": count,
                "percent": round((count / total_samples) * 100, 1) if total_samples else 0,
            }
        )
    return coverage


def age_bins(db: Session, cohort: str | None = None) -> list[dict]:
    stmt = select(Sample.age_at_index).where(Sample.age_at_index.is_not(None))
    if cohort:
        stmt = stmt.where(Sample.cohort == cohort)
    ages = [float(age) for age in db.scalars(stmt).all() if age is not None]
    bins = [
        ("<40", None, 40),
        ("40-49", 40, 50),
        ("50-59", 50, 60),
        ("60-69", 60, 70),
        ("70-79", 70, 80),
        ("80+", 80, None),
    ]
    result = []
    for label, lower, upper in bins:
        count = 0
        for age in ages:
            if lower is not None and age < lower:
                continue
            if upper is not None and age >= upper:
                continue
            count += 1
        result.append({"label": label, "count": count})
    return result


def analysis_request_for_signature_spec(
    request: CombinedSignatureAnalysisRequest,
    signature: SignatureSpec,
) -> AnalysisRequest:
    return AnalysisRequest(
        cohort=request.cohort,
        gene_symbol=signature.gene_symbol,
        signature_method=signature.signature_method,
        signature_genes=signature.signature_genes,
        endpoint=request.endpoint,
        expression_scale=request.expression_scale,
        cutpoint_method="median",
        filters=request.filters,
        time_unit=request.time_unit,
        show_confidence_interval=request.show_confidence_interval,
        show_risk_table=request.show_risk_table,
        plot_style=request.plot_style,
    )


def normalized_signature_name(value: str | None, fallback: str) -> str:
    normalized = (value or "").strip()
    return normalized[:48] if normalized else fallback


def prefixed_warnings(prefix: str, warnings: list[str]) -> list[str]:
    return [f"{prefix}: {warning}" for warning in warnings]


def expression_for_request(db: Session, request: AnalysisRequest) -> tuple[dict[str, float], dict, list[str]]:
    entries = signature_entries(request)
    warnings: list[str] = []
    resolved_entries = []
    seen: set[str] = set()
    for entry in entries:
        resolved = resolve_gene_symbol(db, settings.tcga_data_dir, request.cohort, entry["gene_symbol"])
        warnings.extend(resolved["warnings"])
        if not resolved["resolved"]:
            raise GeneNotFoundError(f"Gene {entry['gene_symbol']} was not found in {request.cohort}.")
        if resolved["resolved"] in seen:
            warnings.append(f"Duplicate gene {resolved['resolved']} was specified more than once and was collapsed.")
            continue
        seen.add(resolved["resolved"])
        resolved_entries.append({**entry, "resolved_symbol": resolved["resolved"], "status": resolved["status"]})

    if request.signature_method == "single" and len(resolved_entries) > 1:
        resolved_entries = resolved_entries[:1]
    if not resolved_entries:
        raise GeneNotFoundError("No valid genes were provided.")

    values_by_gene = []
    for entry in resolved_entries:
        values_by_gene.append(
            {
                **entry,
                "values": get_expression_for_gene(
                    db,
                    settings.tcga_data_dir,
                    settings.derived_expression_dir,
                    request.cohort,
                    entry["resolved_symbol"],
                    request.expression_scale,
                ),
            }
        )

    if request.signature_method == "single" or len(values_by_gene) == 1:
        gene = values_by_gene[0]
        return gene["values"], {
            "method": "single",
            "label": gene["resolved_symbol"],
            "genes": signature_gene_payload(values_by_gene),
        }, warnings

    common_barcodes = set(values_by_gene[0]["values"])
    for gene in values_by_gene[1:]:
        common_barcodes &= set(gene["values"])
    if len(common_barcodes) < 10:
        raise ValueError("The multi-gene signature has fewer than 10 samples with expression for all genes.")

    if request.signature_method == "zscore":
        z_values = {}
        for gene in values_by_gene:
            vals = [gene["values"][barcode] for barcode in common_barcodes]
            mean = sum(vals) / len(vals)
            variance = sum((value - mean) ** 2 for value in vals) / max(len(vals) - 1, 1)
            sd = math.sqrt(variance) or 1.0
            z_values[gene["resolved_symbol"]] = {
                barcode: (gene["values"][barcode] - mean) / sd for barcode in common_barcodes
            }
        expression = {}
        weight_total = sum(abs(gene["weight"]) for gene in values_by_gene) or 1.0
        for barcode in common_barcodes:
            expression[barcode] = sum(gene["weight"] * z_values[gene["resolved_symbol"]][barcode] for gene in values_by_gene) / weight_total
    else:
        expression = {}
        if request.signature_method == "weighted":
            weight_total = sum(abs(gene["weight"]) for gene in values_by_gene) or 1.0
            for barcode in common_barcodes:
                expression[barcode] = sum(gene["weight"] * gene["values"][barcode] for gene in values_by_gene) / weight_total
        else:
            for barcode in common_barcodes:
                expression[barcode] = sum(gene["values"][barcode] for gene in values_by_gene) / len(values_by_gene)

    label = f"{request.signature_method.upper()}({'+'.join(gene['resolved_symbol'] for gene in values_by_gene)})"
    return expression, {
        "method": request.signature_method,
        "label": label,
        "genes": signature_gene_payload(values_by_gene),
        "sample_overlap": len(common_barcodes),
    }, warnings


def signature_entries(request: AnalysisRequest) -> list[dict]:
    if request.signature_genes:
        return [
            {"gene_symbol": item.gene_symbol.strip().upper(), "weight": float(item.weight)}
            for item in request.signature_genes
            if item.gene_symbol.strip()
        ]
    raw = request.gene_symbol.replace(";", ",").replace("+", ",")
    genes = [item.strip().upper() for item in raw.split(",") if item.strip()]
    if not genes:
        genes = [request.gene_symbol.strip().upper()]
    return [{"gene_symbol": gene, "weight": 1.0} for gene in genes]


def signature_gene_payload(values_by_gene: list[dict]) -> list[dict]:
    return [
        {
            "query": gene["gene_symbol"],
            "resolved_symbol": gene["resolved_symbol"],
            "weight": gene["weight"],
            "status": gene["status"],
        }
        for gene in values_by_gene
    ]


def expression_distribution(samples: list[Sample], expression: dict[str, float]) -> dict:
    values = sorted(expression[sample.barcode] for sample in samples if sample.barcode in expression)
    if not values:
        return {"n": 0, "bins": []}
    min_value = values[0]
    max_value = values[-1]
    if min_value == max_value:
        bins = [{"label": f"{min_value:.2f}", "count": len(values)}]
    else:
        bins = []
        bin_count = 10
        step = (max_value - min_value) / bin_count
        for index in range(bin_count):
            lower = min_value + index * step
            upper = max_value if index == bin_count - 1 else lower + step
            count = sum(
                1
                for value in values
                if value >= lower and (value <= upper if index == bin_count - 1 else value < upper)
            )
            bins.append({"label": f"{lower:.2f}-{upper:.2f}", "count": count})
    return {
        "n": len(values),
        "min": min_value,
        "q1": quantile(values, 0.25),
        "median": quantile(values, 0.5),
        "q3": quantile(values, 0.75),
        "max": max_value,
        "bins": bins,
    }


def quantile(values: list[float], proportion: float) -> float:
    return percentile(values, proportion * 100.0)


def quality_summary(records) -> dict:
    groups: dict[str, dict[str, int]] = {}
    for record in records:
        item = groups.setdefault(record.group, {"patients": 0, "events": 0})
        item["patients"] += 1
        item["events"] += int(record.event)
    low_event_groups = [group for group, item in groups.items() if item["events"] < 5]
    return {
        "groups": groups,
        "low_event_groups": low_event_groups,
        "interpretation": "Exploratory research analysis only; not for clinical decision-making.",
    }


def classify_value_error(message: str) -> str:
    text = message.lower()
    if "endpoint" in text and "not available" in text:
        return "ENDPOINT_UNAVAILABLE"
    if "maxstat requires at least 10" in text:
        return "INSUFFICIENT_PATIENTS"
    if "maxstat requires at least one survival event" in text:
        return "NO_EVENTS"
    if "maxstat cannot find an eligible cutpoint" in text or "maxstat requires expression variation" in text:
        return "INVALID_GROUPS"
    if "at least 10 patients" in text or "fewer than 10" in text:
        return "INSUFFICIENT_PATIENTS"
    if "no survival events" in text:
        return "NO_EVENTS"
    if "fewer than two groups" in text or "undersized groups" in text:
        return "INVALID_GROUPS"
    if "cache" in text or "map" in text:
        return "CACHE_INCOMPLETE"
    return "INVALID_ANALYSIS"


def analysis_http_error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


def http_exception_payload(exc: HTTPException) -> tuple[str, str]:
    detail = exc.detail
    if isinstance(detail, dict):
        code = str(detail.get("code") or f"HTTP_{exc.status_code}")
        message = str(detail.get("message") or exc.status_code)
        return code, message
    return f"HTTP_{exc.status_code}", str(detail or exc.status_code)


def sample_count_stmt(cohort: str | None):
    stmt = select(func.count()).select_from(Sample)
    if cohort:
        stmt = stmt.where(Sample.cohort == cohort)
    return stmt


def biological_annotations(cohort: str | None) -> dict:
    wanted = {
        "TCGA-BRCA": ["paper_BRCA_Subtype_PAM50"],
        "TCGA-LGG": ["paper_IDH.status", "paper_IDH.codel.subtype", "paper_IDH1.Somatic.Mutation"],
        "TCGA-GBM": ["paper_IDH.status", "paper_IDH1.Somatic.Mutation"],
        "TCGA-HNSC": ["paper_HPV_Status", "paper_CLIN.HPV_status"],
        "TCGA-CESC": ["paper_HPV_Status", "paper_CLIN.HPV_status", "paper_CLIN.HPV_Hcall"],
    }
    cohorts = [cohort] if cohort else sorted(wanted)
    result = {}
    for cohort_id in cohorts:
        fields = wanted.get(cohort_id, [])
        path = settings.tcga_data_dir / cohort_id / "col_data.tsv"
        if not fields or not path.exists():
            continue
        with path.open(newline="", encoding="utf-8", errors="replace") as handle:
            reader = csv.DictReader(handle, delimiter="\t")
            available = [field for field in fields if field in (reader.fieldnames or [])]
            field_counts = {field: {} for field in available}
            for row in reader:
                for field in available:
                    value = (row.get(field) or "").strip()
                    if not value or value in {"NA", "N/A", "null", "None", "not reported", "--"}:
                        continue
                    field_counts[field][value] = field_counts[field].get(value, 0) + 1
        result[cohort_id] = {
            "available": bool(available),
            "fields": [
                {
                    "name": field,
                    "distribution": [
                        {"label": label, "count": count}
                        for label, count in sorted(field_counts[field].items(), key=lambda item: item[1], reverse=True)
                    ],
                }
                for field in available
            ],
        }
    return result


def _fail_job(db: Session, job: AnalysisJob, message: str) -> None:
    job.status = "failed"
    job.error = message
    db.commit()


def _maxstat_records(
    samples: list[Sample],
    expression: dict[str, float],
    endpoint_by_patient: dict[str, ClinicalOutcome] | None = None,
    max_time_days: float | None = None,
) -> list[dict]:
    records = []
    for sample in samples:
        if sample.barcode not in expression:
            continue
        if endpoint_by_patient is not None:
            outcome = endpoint_by_patient.get(sample.patient_id)
        elif sample.os_time_days is not None and sample.os_event is not None:
            outcome = ClinicalOutcome(
                endpoint="OS",
                time_days=float(sample.os_time_days),
                event=int(sample.os_event),
                source="derived_sample_metadata",
            )
        else:
            outcome = None
        if outcome is None:
            continue
        time_days = float(outcome.time_days)
        event = int(outcome.event)
        if max_time_days is not None and time_days > max_time_days:
            time_days = max_time_days
            event = 0
        records.append(
            {
                "patient_id": sample.patient_id,
                "expression_value": expression[sample.barcode],
                "time_days": time_days,
                "event": event,
            }
        )
    return records


def _artifacts_exist(job: AnalysisJob) -> bool:
    paths = [job.png_path, job.csv_path, job.json_path, str(methodology_path(job.id))]
    return all(path and Path(path).exists() for path in paths)


def methodology_path(analysis_id: str) -> Path:
    return settings.artifact_dir / analysis_id / "methodology.txt"


def analysis_out(job: AnalysisJob) -> AnalysisOut:
    downloads = {}
    if job.status == "completed":
        downloads = {
            "png": f"/api/analyses/{job.id}/download/png",
            "svg": f"/api/analyses/{job.id}/download/svg",
            "csv": f"/api/analyses/{job.id}/download/csv",
            "zip": f"/api/analyses/{job.id}/download/zip",
        }
        if methodology_path(job.id).exists():
            downloads["txt"] = f"/api/analyses/{job.id}/download/txt"
        if (settings.artifact_dir / job.id / "cox_forest.png").exists():
            downloads["cox_png"] = f"/api/analyses/{job.id}/download/cox_png"
            downloads["cox_svg"] = f"/api/analyses/{job.id}/download/cox_svg"
    return AnalysisOut(
        id=job.id,
        status=job.status,
        cohort=job.cohort,
        gene_symbol=job.gene_symbol,
        expression_scale=job.request_payload.get("expression_scale", "log2_tpm"),
        expression_scale_label=expression_scale_label(job.request_payload.get("expression_scale", "log2_tpm")),
        cutpoint_method=job.cutpoint_method,
        metrics=job.metrics,
        warnings=job.warnings or [],
        error=job.error,
        downloads=downloads,
        cached=job.cached,
    )
