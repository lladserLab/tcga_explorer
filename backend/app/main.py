from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, timezone
import csv
import fcntl
import io
import json
import math
import time
import uuid
import zipfile
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from sqlalchemy import desc, distinct, func, select
from sqlalchemy.orm import Session

from app.cache_warmup import load_cache_manifest, summarize_cache_manifest, warm_startup_cache
from app.analysis_notices import (
    COMPETING_RISK_ENDPOINTS,
    ZSCORE_TRANSPORTABILITY_MESSAGE,
    build_analysis_diagnostics,
)
from app.attestation import (
    AttestationError,
    attestation_key_document,
    attestation_keyset,
)
from app.config import get_settings
from app.database import SessionLocal, get_db, init_db, wait_for_database
from app.data_sync.sync import current_sync_status
from app.expression import (
    GeneNotFoundError,
    expression_scale_label,
    expression_scale_options,
    get_expression_for_gene,
)
from app.external_covariates import prepare_external_covariates
from app.gene_aliases import GENE_ALIASES, resolve_gene_symbol
from app.importer import (
    COMPETING_ENDPOINT_COLUMNS,
    ensure_gene_index,
    import_cohorts_and_samples,
    import_tcga_cdr,
)
from app.models import AnalysisJob, ClinicalEndpoint, Cohort, DataManifest, DataSource, GeneIndex, Sample
from app.multiverse import (
    expand_multiverse_request,
    summarize_multiverse,
    write_multiverse_artifacts,
)
from app.paper_examples import build_paper_examples, publication_figure_path
from app.pancancer import (
    add_clinical_sensitivity,
    add_concordance_labels,
    add_effect_labels,
    adjust_p_values_bh,
    attach_effect_scale_metadata,
    attach_preparation_metadata,
    common_scale_meta_analysis_from_rows,
    summarize_pancancer_results,
)
from app.pipeline_versions import (
    ANALYSIS_PIPELINE_VERSION,
    COMBINED_SIGNATURE_PIPELINE_VERSION,
    IMMUNE_ATLAS_PIPELINE_VERSION,
    MULTIVERSE_PIPELINE_VERSION,
    PANCANCER_PIPELINE_VERSION,
    SESSION_HISTORY_PIPELINE_VERSION,
    compute_cache_context,
)
from app.provenance import analysis_data_provenance, publication_snapshot_summary
from app.r_runner import (
    compute_maxstat_cutpoint,
    ensure_svg_artifact,
    run_r_km,
    run_r_pancancer_cox,
    stable_hash,
    write_audit_report,
    write_pancancer_artifacts,
)
from app.reproduction_capsule import write_reproduction_capsule
from app.schemas import (
    AnalysisBatchItemOut,
    AnalysisBatchOut,
    AnalysisBatchRequest,
    AnalysisOut,
    AnalysisRequest,
    CombinedSignatureAnalysisRequest,
    CohortOut,
    ExpressionScaleOut,
    ExploratorySessionExportRequest,
    ExploratorySessionOut,
    FilterOptions,
    GeneSearchOut,
    MultiverseAnalysisOut,
    MultiverseAnalysisRequest,
    PanCancerSurvivalOut,
    PanCancerSurvivalRequest,
    PublicAnalysisBatchRequest,
    SignatureSpec,
)
from app.session_history import (
    build_exploratory_session_report,
    write_exploratory_session_artifacts,
)
from app.survival import (
    ClinicalOutcome,
    build_combined_survival_records,
    build_continuous_survival_records,
    build_survival_records,
    filter_sample_candidates,
    percentile,
    sample_os_outcome,
    select_expression_complete_samples,
    select_rmst_tau,
    validate_records,
)

settings = get_settings()
ENDPOINT_LABELS = {
    "OS": "Overall survival",
    "PFI": "Progression-free interval",
    "DFI": "Disease-free interval",
    "DSS": "Disease-specific survival",
}
ENDPOINT_MIN_PATIENTS = 10
ENDPOINT_MIN_EVENTS = 5


@contextmanager
def _compute_file_lock(key: str):
    """Serialize identical scientific work across web and worker containers."""
    lock_dir = settings.artifact_dir / ".compute_locks"
    lock_dir.mkdir(parents=True, exist_ok=True)
    lock_path = lock_dir / f"{key}.lock"
    with lock_path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


@asynccontextmanager
async def app_lifespan(_app: FastAPI):
    startup()
    from app.mcp_server import mcp

    async with mcp.session_manager.run():
        yield


app = FastAPI(
    title=f"{settings.app_name} Public API",
    description=(
        "Public, endpoint-aware TCGA transcriptomic survival analysis API. "
        "Results are exploratory research outputs and are not intended for clinical decision-making."
    ),
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    servers=[{"url": settings.public_base_url.rstrip("/"), "description": "Production"}],
    openapi_tags=[
        {"name": "Service", "description": "Public readiness and version information."},
        {"name": "Dataset", "description": "TCGA dataset, sources, endpoints, and expression scales."},
        {"name": "Cohorts", "description": "Cohort metadata, filters, endpoint availability, and genes."},
        {"name": "Examples", "description": "Reproducible figures and benchmark cases from the application paper."},
        {"name": "Analyses", "description": "Asynchronous survival analyses and reproducible artifacts."},
        {"name": "Pan-cancer", "description": "Pan-cancer survival scans and immune screens."},
        {"name": "Attestation", "description": "Server signing keys for independent receipt verification."},
        {"name": "Jobs", "description": "Persistent compute job status and results."},
    ],
    root_path=settings.public_path_prefix.rstrip("/"),
    root_path_in_servers=False,
    lifespan=app_lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


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


def _public_guide(filename: str) -> Response:
    candidates = [
        Path("/app/docs") / filename,
        Path(__file__).resolve().parents[2] / "docs" / filename,
    ]
    path = next((candidate for candidate in candidates if candidate.is_file()), None)
    if path is None:
        raise HTTPException(status_code=404, detail="Public guide is not available.")
    return Response(content=path.read_text(encoding="utf-8"), media_type="text/markdown")


@app.get("/api/guide", include_in_schema=False, response_class=Response)
def public_api_guide() -> Response:
    return _public_guide("API.md")


@app.get("/api/guia", include_in_schema=False, response_class=Response)
def public_api_guide_es() -> Response:
    return _public_guide("API_ES.md")


SessionDep = Annotated[Session, Depends(get_db)]


def _legacy_client_key(request: Request) -> str:
    real_ip = request.headers.get("x-real-ip")
    if not real_ip:
        forwarded = request.headers.get("x-forwarded-for", "")
        real_ip = forwarded.split(",", 1)[0].strip() if forwarded else ""
    if not real_ip and request.client is not None:
        real_ip = request.client.host
    return f"rest:{real_ip or 'anonymous'}"


def _legacy_submit_and_wait(
    *,
    kind: str,
    payload: dict,
    request: Request,
    db: Session,
    timeout_seconds: int = 600,
) -> dict:
    """Compatibility facade backed by the same bounded public compute queue."""
    from app.jobs import ComputeQueueError, submit_compute_job

    try:
        job = submit_compute_job(
            db,
            kind=kind,
            request_payload=payload,
            client_key=_legacy_client_key(request),
            settings=settings,
            cache_context=compute_cache_context(kind, data_version=current_data_version(db)),
        )
    except ComputeQueueError as exc:
        headers = {"Retry-After": str(exc.retry_after)} if exc.retry_after else None
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": exc.message},
            headers=headers,
        ) from exc

    deadline = time.monotonic() + timeout_seconds
    while job.status in {"queued", "running"} and time.monotonic() < deadline:
        time.sleep(1)
        db.expire_all()
        db.refresh(job)

    if job.status == "completed" and job.result_json is not None:
        return job.result_json
    if job.status == "expired":
        raise HTTPException(
            status_code=410,
            detail={
                "code": "ARTIFACT_EXPIRED",
                "message": "Generated artifacts expired. Submit the request again to regenerate them.",
            },
        )
    if job.status == "failed":
        error = job.error_json or {}
        details = error.get("details") or {}
        failure_status = int(details.get("status_code") or 500)
        if failure_status < 400 or failure_status > 599:
            failure_status = 500
        raise HTTPException(
            status_code=failure_status,
            detail={
                "code": str(error.get("code") or "COMPUTE_FAILED"),
                "message": str(error.get("message") or "Compute job failed."),
            },
        )
    raise HTTPException(
        status_code=504,
        detail={
            "code": "COMPUTE_TIMEOUT",
            "message": f"Compute job {job.id} is still running and can be polled through API v1.",
        },
    )


@app.get("/api/health")
def health(db: SessionDep) -> dict:
    cohorts = db.scalar(select(func.count()).select_from(Cohort))
    cache_manifest = load_cache_manifest(settings.derived_expression_dir)
    return {
        "status": "ok",
        "app_version": app.version,
        "release": application_release_identity(),
        "pipeline_versions": {
            "analysis": ANALYSIS_PIPELINE_VERSION,
            "combined_signatures": COMBINED_SIGNATURE_PIPELINE_VERSION,
            "multiverse": MULTIVERSE_PIPELINE_VERSION,
            "pancancer": PANCANCER_PIPELINE_VERSION,
            "exploratory_session": SESSION_HISTORY_PIPELINE_VERSION,
            "immune_atlas": IMMUNE_ATLAS_PIPELINE_VERSION,
        },
        "cohorts": cohorts,
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
        competing_events = sum(
            int(outcome.competing_event or 0)
            for outcome in cdr_outcomes.values()
        )
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
            "competing_events": competing_events,
            "competing_risk_available": (
                endpoint in COMPETING_ENDPOINT_COLUMNS
                and all(
                    outcome.competing_risk_status in {0, 1, 2}
                    for outcome in cdr_outcomes.values()
                )
            ),
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
    os_by_patient: dict[str, ClinicalEndpoint] = {}
    if endpoint in COMPETING_ENDPOINT_COLUMNS:
        os_by_patient = {
            row.patient_id: row
            for row in db.scalars(
                select(ClinicalEndpoint)
                .where(ClinicalEndpoint.source_id == "tcga_cdr")
                .where(ClinicalEndpoint.cohort == cohort_id)
                .where(ClinicalEndpoint.endpoint == "OS")
            ).all()
        }

    outcomes: dict[str, ClinicalOutcome] = {}
    for row in rows:
        if row.patient_id not in sample_patients:
            continue
        raw_metadata = row.raw_metadata or {}
        raw_status = raw_metadata.get("competing_risk_status")
        try:
            competing_status = int(raw_status)
        except (TypeError, ValueError):
            competing_status = None
        competing_source = None
        if competing_status in {0, 1, 2}:
            competing_source = (
                "TCGA-CDR ExtraEndpoints:"
                f"{raw_metadata.get('source_competing_status_column')}"
            )
        elif endpoint in COMPETING_ENDPOINT_COLUMNS:
            os_outcome = os_by_patient.get(row.patient_id)
            if int(row.event) == 1:
                competing_status = 1
            elif (
                os_outcome is not None
                and int(os_outcome.event) == 1
                and abs(float(os_outcome.time_days) - float(row.time_days)) <= 1e-8
            ):
                competing_status = 2
            else:
                competing_status = 0
            competing_source = "paired TCGA-CDR endpoint and OS fallback"
        outcomes[row.patient_id] = ClinicalOutcome(
            endpoint=row.endpoint,
            time_days=float(row.time_days),
            event=int(row.event),
            source=row.source_id,
            competing_risk_status=competing_status,
            competing_event=(
                int(competing_status == 2)
                if competing_status in {0, 1, 2}
                else None
            ),
            competing_risk_source=competing_source,
        )
    return outcomes


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
def create_analysis(request_body: AnalysisRequest, request: Request, db: SessionDep) -> AnalysisOut:
    result = _legacy_submit_and_wait(
        kind="analysis",
        payload=request_body.model_dump(mode="json"),
        request=request,
        db=db,
    )
    return AnalysisOut(**result)


def _create_analysis(request: AnalysisRequest, db: Session) -> AnalysisOut:
    lock_key = stable_hash(
        {"kind": "analysis", "request": request.model_dump(mode="json")}
    )
    with _compute_file_lock(lock_key):
        return _create_analysis_unlocked(request, db)


def _create_analysis_unlocked(request: AnalysisRequest, db: Session) -> AnalysisOut:
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
        samples = list(db.scalars(select(Sample).where(Sample.cohort == request.cohort)).all())
        candidates, filter_warnings, sample_selection = filter_sample_candidates(
            samples,
            request.filters,
            endpoint_by_patient=endpoint_by_patient,
            endpoint=request.endpoint,
            endpoint_label=endpoint_label,
        )
        candidate_expression, _, _, _ = expression_for_request(
            db,
            request,
            eligible_barcodes={sample.barcode for sample in candidates},
        )
        filtered, selection_warnings, sample_selection = (
            select_expression_complete_samples(
                candidates,
                set(candidate_expression),
                warnings=filter_warnings,
                summary=sample_selection,
            )
        )
        expression, signature_info, gene_warnings, scoring_provenance = expression_for_request(
            db,
            request,
            eligible_barcodes={sample.barcode for sample in filtered},
        )
        job.gene_symbol = signature_info["label"]
        external_covariates = prepare_external_covariates(
            request.external_covariates,
            request.external_adjustment_covariates,
            cohort_patient_ids={sample.patient_id for sample in samples},
            analysis_patient_ids={sample.patient_id for sample in filtered},
        )
        warnings = (
            gene_warnings
            + selection_warnings
            + external_covariates.warnings
        )
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
            external_covariates_by_patient=external_covariates.values_by_patient,
        )
        validate_records(records, endpoint_label)
        continuous_records = build_continuous_survival_records(
            filtered,
            expression,
            endpoint_by_patient=endpoint_by_patient,
            endpoint=request.endpoint,
            max_time_days=request.filters.max_time_days,
            external_covariates_by_patient=external_covariates.values_by_patient,
        )
        rmst_tau = select_rmst_tau(
            filtered,
            set(expression),
            endpoint_by_patient=endpoint_by_patient,
            max_time_days=request.filters.max_time_days,
        )
        data_provenance = analysis_data_provenance(
            settings,
            cohort=request.cohort,
            expression_scale=request.expression_scale,
            selected_barcodes=set(expression),
        )
        analysis_data_dates = dataset_dates(db, load_cache_manifest(settings.derived_expression_dir))
        metrics = run_r_km(
            settings=settings,
            analysis_id=analysis_id,
            cohort=request.cohort,
            gene_symbol=job.gene_symbol,
            endpoint=request.endpoint,
            endpoint_label=endpoint_label,
            cutpoint_method=request.cutpoint_method,
            records=records,
            continuous_records=continuous_records,
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
            data_dates=analysis_data_dates,
            sample_selection=sample_selection,
            rmst_tau=rmst_tau,
            external_covariates=external_covariates,
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
        audit_artifacts = {
            key: value
            for key, value in artifacts.items()
            if key != "json"
        }
        audit_artifacts["methodology"] = str(methodology_path(analysis_id))
        audit = write_audit_report(
            settings=settings,
            analysis_id=analysis_id,
            request_payload=payload,
            metrics=metrics,
            records=records,
            continuous_records=continuous_records,
            artifact_paths=audit_artifacts,
            analysis_warnings=warnings,
            data_dates=analysis_data_dates,
            scoring_provenance=scoring_provenance,
            data_provenance=data_provenance,
        )
        metrics["median_survival_status"] = audit["median_survival_status"]
        metrics["audit_report"] = {
            "schema_version": audit["schema_version"],
            "generated_at": audit["generated_at"],
            "reproducibility_hash": audit["reproducibility_hash"],
            "server_attestation": audit["server_attestation"],
            "patient_records_sha256": audit["patient_records_sha256"],
            "continuous_patient_records_sha256": audit["continuous_patient_records_sha256"],
        }
        Path(artifacts["json"]).write_text(json.dumps(metrics, ensure_ascii=False, allow_nan=False, indent=2), encoding="utf-8")
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
def create_combined_analysis(
    request_body: CombinedSignatureAnalysisRequest,
    request: Request,
    db: SessionDep,
) -> AnalysisOut:
    result = _legacy_submit_and_wait(
        kind="combined",
        payload=request_body.model_dump(mode="json"),
        request=request,
        db=db,
    )
    return AnalysisOut(**result)


def _create_combined_analysis(request: CombinedSignatureAnalysisRequest, db: Session) -> AnalysisOut:
    lock_key = stable_hash(
        {"kind": "combined", "request": request.model_dump(mode="json")}
    )
    with _compute_file_lock(lock_key):
        return _create_combined_analysis_unlocked(request, db)


def _create_combined_analysis_unlocked(
    request: CombinedSignatureAnalysisRequest,
    db: Session,
) -> AnalysisOut:
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

        samples = list(db.scalars(select(Sample).where(Sample.cohort == request.cohort)).all())
        candidates, filter_warnings, sample_selection = filter_sample_candidates(
            samples,
            request.filters,
            endpoint_by_patient=endpoint_by_patient,
            endpoint=request.endpoint,
            endpoint_label=endpoint_label,
        )
        candidate_barcodes = {sample.barcode for sample in candidates}
        candidate_expression_a, _, _, _ = expression_for_request(
            db,
            signature_request_a,
            eligible_barcodes=candidate_barcodes,
        )
        candidate_expression_b, _, _, _ = expression_for_request(
            db,
            signature_request_b,
            eligible_barcodes=candidate_barcodes,
        )
        filtered, selection_warnings, sample_selection = (
            select_expression_complete_samples(
                candidates,
                set(candidate_expression_a) & set(candidate_expression_b),
                warnings=filter_warnings,
                summary=sample_selection,
            )
        )
        eligible_barcodes = {sample.barcode for sample in filtered}
        expression_a, signature_info_a, warnings_a, scoring_provenance_a = expression_for_request(
            db,
            signature_request_a,
            eligible_barcodes=eligible_barcodes,
        )
        expression_b, signature_info_b, warnings_b, scoring_provenance_b = expression_for_request(
            db,
            signature_request_b,
            eligible_barcodes=eligible_barcodes,
        )
        signature_info_a = {**signature_info_a, "name": signature_a_name}
        signature_info_b = {**signature_info_b, "name": signature_b_name}
        external_covariates = prepare_external_covariates(
            request.external_covariates,
            request.external_adjustment_covariates,
            cohort_patient_ids={sample.patient_id for sample in samples},
            analysis_patient_ids={sample.patient_id for sample in filtered},
        )
        warnings = (
            prefixed_warnings("Signature A", warnings_a)
            + prefixed_warnings("Signature B", warnings_b)
            + selection_warnings
            + external_covariates.warnings
        )
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
            external_covariates_by_patient=external_covariates.values_by_patient,
        )
        validate_records(records, endpoint_label)
        rmst_tau = select_rmst_tau(
            filtered,
            set(expression_a) & set(expression_b),
            endpoint_by_patient=endpoint_by_patient,
            max_time_days=request.filters.max_time_days,
        )
        data_provenance = analysis_data_provenance(
            settings,
            cohort=request.cohort,
            expression_scale=request.expression_scale,
            selected_barcodes=set(expression_a) & set(expression_b),
        )
        analysis_data_dates = dataset_dates(db, load_cache_manifest(settings.derived_expression_dir))
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
            data_dates=analysis_data_dates,
            sample_selection=sample_selection,
            rmst_tau=rmst_tau,
            external_covariates=external_covariates,
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
        audit_artifacts = {
            key: value
            for key, value in artifacts.items()
            if key != "json"
        }
        audit_artifacts["methodology"] = str(methodology_path(analysis_id))
        audit = write_audit_report(
            settings=settings,
            analysis_id=analysis_id,
            request_payload=payload,
            metrics=metrics,
            records=records,
            artifact_paths=audit_artifacts,
            analysis_warnings=warnings,
            data_dates=analysis_data_dates,
            scoring_provenance={
                "schema_version": "tcga-trace-scoring-provenance-v1",
                "analysis_type": "combined_signatures",
                "signature_a": scoring_provenance_a,
                "signature_b": scoring_provenance_b,
            },
            data_provenance=data_provenance,
        )
        metrics["median_survival_status"] = audit["median_survival_status"]
        metrics["audit_report"] = {
            "schema_version": audit["schema_version"],
            "generated_at": audit["generated_at"],
            "reproducibility_hash": audit["reproducibility_hash"],
            "server_attestation": audit["server_attestation"],
            "patient_records_sha256": audit["patient_records_sha256"],
        }
        Path(artifacts["json"]).write_text(json.dumps(metrics, ensure_ascii=False, allow_nan=False, indent=2), encoding="utf-8")
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
def create_analysis_batch(
    request_body: PublicAnalysisBatchRequest,
    request: Request,
    db: SessionDep,
) -> AnalysisBatchOut:
    if len(request_body.analyses) > settings.public_batch_max_analyses:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "BATCH_TOO_LARGE",
                "message": f"Public batches are limited to {settings.public_batch_max_analyses} analyses.",
            },
        )
    payload = request_body.model_dump(mode="json")
    payload["max_concurrency"] = 1
    result = _legacy_submit_and_wait(
        kind="batch",
        payload=payload,
        request=request,
        db=db,
    )
    return AnalysisBatchOut(**result)


def _create_analysis_batch(request: AnalysisBatchRequest) -> AnalysisBatchOut:
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


def _create_multiverse_analysis(
    request: MultiverseAnalysisRequest,
    db: Session,
) -> MultiverseAnalysisOut:
    planned = (
        len(request.endpoints)
        * len(request.scoring_methods)
        * len(request.cutpoint_methods)
    )
    if planned > settings.public_multiverse_max_analyses:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "MULTIVERSE_TOO_LARGE",
                "message": (
                    "Public multiverses are limited to "
                    f"{settings.public_multiverse_max_analyses} specifications."
                ),
            },
        )
    data_version = current_data_version(db)
    identity = {
        "kind": "multiverse",
        "pipeline_version": MULTIVERSE_PIPELINE_VERSION,
        "data_version": data_version,
        "request": request.model_dump(mode="json"),
    }
    session_id = f"mv_{stable_hash(identity)[:24]}"
    result_path = (
        settings.artifact_dir
        / "multiverse"
        / session_id
        / "multiverse_result.json"
    )
    lock_key = f"multiverse-{session_id}"
    with _compute_file_lock(lock_key):
        if result_path.exists():
            return MultiverseAnalysisOut(
                **json.loads(result_path.read_text(encoding="utf-8"))
            )

        specifications = expand_multiverse_request(request)
        items: list[dict] = []
        for specification in specifications:
            analysis_request = specification["analysis_request"]
            try:
                analysis = _create_analysis(analysis_request, db)
                items.append(
                    {
                        "index": specification["index"],
                        "status": "completed",
                        "result": analysis.model_dump(mode="json"),
                    }
                )
            except HTTPException as exc:
                code, message = http_exception_payload(exc)
                items.append(
                    {
                        "index": specification["index"],
                        "status": "failed",
                        "code": code,
                        "error": message,
                    }
                )
            except Exception as exc:
                items.append(
                    {
                        "index": specification["index"],
                        "status": "failed",
                        "code": "ANALYSIS_FAILED",
                        "error": str(exc),
                    }
                )

        result = summarize_multiverse(
            session_id=session_id,
            request=request,
            specifications=specifications,
            completed_items=items,
            pipeline_version=MULTIVERSE_PIPELINE_VERSION,
            data_version=data_version,
        )
        write_multiverse_artifacts(
            settings.artifact_dir,
            result,
            settings=settings,
        )
        return MultiverseAnalysisOut(**result)


def _create_exploratory_session(
    request: ExploratorySessionExportRequest,
    db: Session,
) -> ExploratorySessionOut:
    result = build_exploratory_session_report(
        request=request,
        db=db,
        pipeline_version=SESSION_HISTORY_PIPELINE_VERSION,
    )
    result_path = (
        settings.artifact_dir
        / "sessions"
        / result["report_id"]
        / "session_report.json"
    )
    with _compute_file_lock(f"session-{result['report_id']}"):
        if result_path.exists():
            return ExploratorySessionOut(
                **json.loads(result_path.read_text(encoding="utf-8"))
            )
        write_exploratory_session_artifacts(
            settings.artifact_dir,
            result,
            settings=settings,
        )
    return ExploratorySessionOut(**result)


@app.post("/api/pancancer/survival", response_model=PanCancerSurvivalOut)
def create_pancancer_survival(
    request_body: PanCancerSurvivalRequest,
    request: Request,
    db: SessionDep,
) -> PanCancerSurvivalOut:
    result = _legacy_submit_and_wait(
        kind="pancancer",
        payload=request_body.model_dump(mode="json"),
        request=request,
        db=db,
    )
    return PanCancerSurvivalOut(**result)


def _create_pancancer_survival(
    request: PanCancerSurvivalRequest,
    db: Session,
) -> PanCancerSurvivalOut:
    lock_key = stable_hash(
        {"kind": "pancancer", "request": request.model_dump(mode="json")}
    )
    with _compute_file_lock(lock_key):
        return _create_pancancer_survival_unlocked(request, db)


def _create_pancancer_survival_unlocked(
    request: PanCancerSurvivalRequest,
    db: Session,
) -> PanCancerSurvivalOut:
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
def download_pancancer_survival(scan_id: str, db: SessionDep) -> Response:
    _ensure_public_result_retained(db, scan_id, {"pancancer"})
    result_path = pancancer_result_path(scan_id)
    if not result_path.exists():
        raise HTTPException(status_code=404, detail="Pan-cancer scan not found.")
    cohort_csv_path = result_path.parent / "cohort_results.csv"
    if cohort_csv_path.exists():
        return FileResponse(
            cohort_csv_path,
            media_type="text/csv",
            filename=f"{scan_id}.pancancer_survival.csv",
        )
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
        "selected_adjusted_model",
        "adjusted_status",
        "adjusted_reason",
        "adjusted_n_patients",
        "adjusted_n_events",
        "adjusted_hazard_ratio",
        "adjusted_hr_conf_low",
        "adjusted_hr_conf_high",
        "adjusted_p_value",
        "adjusted_fdr",
        "adjusted_direction",
        "adjusted_significant",
        "clinical_sensitivity",
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


@app.get("/api/pancancer/survival/{scan_id}/download/{kind}")
def download_pancancer_survival_artifact(
    scan_id: str,
    kind: str,
    db: SessionDep,
) -> Response:
    _ensure_public_result_retained(db, scan_id, {"pancancer"})
    scan_dir = pancancer_result_path(scan_id).parent
    if kind == "zip":
        files = [
            "result.json",
            "cohort_results.csv",
            "patient_records.csv",
            "methodology.txt",
            "audit_report.json",
            "audit_report.html",
            "attestation_receipt.json",
            "cox_results.json",
        ]
        existing = [scan_dir / name for name in files if (scan_dir / name).exists()]
        if not existing:
            raise HTTPException(status_code=404, detail="Pan-cancer artifacts not found.")
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in existing:
                archive.write(path, arcname=path.name)
        return Response(
            content=buffer.getvalue(),
            media_type="application/zip",
            headers={
                "Content-Disposition": (
                    f"attachment; filename={scan_id}.pancancer_artifacts.zip"
                )
            },
        )

    artifacts = {
        "patients": ("patient_records.csv", "text/csv"),
        "methodology": ("methodology.txt", "text/plain"),
        "audit_json": ("audit_report.json", "application/json"),
        "audit_html": ("audit_report.html", "text/html"),
        "attestation": ("attestation_receipt.json", "application/json"),
        "raw_r_json": ("cox_results.json", "application/json"),
        "result_json": ("result.json", "application/json"),
    }
    artifact = artifacts.get(kind)
    if artifact is None:
        raise HTTPException(
            status_code=404,
            detail=(
                "Unknown pan-cancer artifact. Use patients, methodology, "
                "audit_json, audit_html, attestation, raw_r_json, result_json "
                "or zip."
            ),
        )
    filename, media_type = artifact
    path = scan_dir / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="Pan-cancer artifact not found.")
    return FileResponse(
        path,
        media_type=media_type,
        filename=f"{scan_id}.{filename}",
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
                "pipeline_version": payload.get("pipeline_version"),
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
def download_immune_pancancer_screen(screen_id: str, kind: str) -> Response:
    screen_dir = immune_screen_path(screen_id)
    if kind == "zip":
        filenames = [
            "screen_summary.json",
            "manifest.json",
            "audit_report.json",
            "methodology.txt",
            "immune_gene_panel.tsv",
            "immune_terms.tsv",
            "model_results.csv",
            "selected_sensitivity.csv",
            "model_family_summary.csv",
            "gene_model_summary.csv",
            "cohort_model_summary.csv",
            "term_model_summary.csv",
        ]
        existing = [
            screen_dir / filename
            for filename in filenames
            if (screen_dir / filename).exists()
        ]
        if not existing:
            raise HTTPException(
                status_code=404,
                detail="Immune screen bundle is not available.",
            )
        bundle_path = immune_atlas_bundle_path(
            screen_id,
            screen_dir,
            existing,
        )
        return FileResponse(
            bundle_path,
            media_type="application/zip",
            filename=f"{screen_id}.atlas_bundle.zip",
        )

    file_map = {
        "genes": ("gene_summary.csv", "text/csv"),
        "cohorts": ("cohort_summary.csv", "text/csv"),
        "terms": ("term_summary.csv", "text/csv"),
        "gene_models": ("gene_model_summary.csv", "text/csv"),
        "cohort_models": ("cohort_model_summary.csv", "text/csv"),
        "term_models": ("term_model_summary.csv", "text/csv"),
        "sensitivity": ("selected_sensitivity.csv", "text/csv"),
        "family_summary": ("model_family_summary.csv", "text/csv"),
        "audit": ("audit_report.json", "application/json"),
        "raw_results": ("model_results.raw.csv", "text/csv"),
        "panel": ("immune_gene_panel.tsv", "text/tab-separated-values"),
        "manifest": ("manifest.json", "application/json"),
        "methodology": ("methodology.txt", "text/plain"),
    }
    if kind == "results":
        filename = (
            "model_results.csv"
            if (screen_dir / "model_results.csv").exists()
            else "results_long.csv"
        )
        file_map["results"] = (filename, "text/csv")
    if kind not in file_map:
        raise HTTPException(status_code=404, detail="Unsupported immune screen download type.")
    filename, media_type = file_map[kind]
    path = screen_dir / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="Immune screen file is not available.")
    return FileResponse(path, media_type=media_type, filename=f"{screen_id}.{filename}")


@app.get("/api/analyses/{analysis_id}", response_model=AnalysisOut)
def get_analysis(analysis_id: str, db: SessionDep) -> AnalysisOut:
    _ensure_public_result_retained(db, analysis_id, {"analysis", "combined"})
    job = db.get(AnalysisJob, analysis_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Analysis not found.")
    return analysis_out(job)


@app.get("/api/analyses/{analysis_id}/download/{kind}")
def download_analysis(analysis_id: str, kind: str, db: SessionDep) -> Response:
    _ensure_public_result_retained(db, analysis_id, {"analysis", "combined"})
    job = db.get(AnalysisJob, analysis_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Analysis not found.")
    if kind in {"zip", "r_script", "reproduction_manifest"}:
        try:
            ensure_reproduction_capsule(analysis_id)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
    if kind == "zip":
        try:
            return analysis_zip_response(job, db)
        except HTTPException:
            raise
        except Exception as exc:
            raise analysis_http_error(500, "R_FAILED", str(exc)) from exc
    cox_forest_png_path = settings.artifact_dir / analysis_id / "cox_forest.png"
    cox_forest_svg_path = settings.artifact_dir / analysis_id / "cox_forest.svg"
    continuous_effect_png_path = settings.artifact_dir / analysis_id / "continuous_effect.png"
    continuous_effect_svg_path = settings.artifact_dir / analysis_id / "continuous_effect.svg"
    cumulative_incidence_png_path = (
        settings.artifact_dir / analysis_id / "cumulative_incidence.png"
    )
    cumulative_incidence_svg_path = (
        settings.artifact_dir / analysis_id / "cumulative_incidence.svg"
    )
    continuous_csv_path = settings.artifact_dir / analysis_id / "continuous_data.csv"
    needs_svg_render = job.svg_path is None or not Path(job.svg_path).exists()
    if kind == "cox_svg" and not cox_forest_svg_path.exists():
        needs_svg_render = True
    if kind == "continuous_svg" and not continuous_effect_svg_path.exists():
        needs_svg_render = True
    if kind == "cumulative_incidence_svg" and not cumulative_incidence_svg_path.exists():
        needs_svg_render = True
    if kind in {
        "svg",
        "cox_svg",
        "continuous_svg",
        "cumulative_incidence_svg",
    } and needs_svg_render:
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
        "continuous_png": str(continuous_effect_png_path),
        "continuous_svg": str(continuous_effect_svg_path),
        "cumulative_incidence_png": str(cumulative_incidence_png_path),
        "cumulative_incidence_svg": str(cumulative_incidence_svg_path),
        "continuous_csv": str(continuous_csv_path),
        "csv": job.csv_path,
        "json": job.json_path,
        "audit_json": str(audit_report_json_path(analysis_id)),
        "audit_html": str(audit_report_html_path(analysis_id)),
        "attestation": str(attestation_receipt_path(analysis_id)),
        "txt": str(methodology_path(analysis_id)),
        "methodology": str(methodology_path(analysis_id)),
        "r_script": str(settings.artifact_dir / analysis_id / "rerun_analysis.R"),
        "reproduction_manifest": str(
            settings.artifact_dir / analysis_id / "reproduction_manifest.json"
        ),
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
        "continuous_png": "image/png",
        "continuous_svg": "image/svg+xml",
        "cumulative_incidence_png": "image/png",
        "cumulative_incidence_svg": "image/svg+xml",
        "continuous_csv": "text/csv",
        "csv": "text/csv",
        "json": "application/json",
        "audit_json": "application/json",
        "audit_html": "text/html",
        "attestation": "application/json",
        "txt": "text/plain",
        "methodology": "text/plain",
        "r_script": "text/plain",
        "reproduction_manifest": "application/json",
    }[kind]
    filename = {
        "methodology": f"{analysis_id}.methodology.txt",
        "cox_png": f"{analysis_id}.cox_forest.png",
        "cox_svg": f"{analysis_id}.cox_forest.svg",
        "continuous_png": f"{analysis_id}.continuous_effect.png",
        "continuous_svg": f"{analysis_id}.continuous_effect.svg",
        "cumulative_incidence_png": f"{analysis_id}.cumulative_incidence.png",
        "cumulative_incidence_svg": f"{analysis_id}.cumulative_incidence.svg",
        "continuous_csv": f"{analysis_id}.continuous_data.csv",
        "audit_json": f"{analysis_id}.audit_report.json",
        "audit_html": f"{analysis_id}.audit_report.html",
        "attestation": f"{analysis_id}.attestation_receipt.json",
        "r_script": f"{analysis_id}.rerun_analysis.R",
        "reproduction_manifest": f"{analysis_id}.reproduction_manifest.json",
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
        ("metrics.json", job.json_path),
        ("methodology.txt", str(methodology_path(job.id))),
        ("audit_report.json", str(audit_report_json_path(job.id))),
        ("audit_report.html", str(audit_report_html_path(job.id))),
        (
            "attestation_receipt.json",
            str(attestation_receipt_path(job.id)),
        ),
        ("input.json", str(settings.artifact_dir / job.id / "input.json")),
        ("rerun_analysis.R", str(settings.artifact_dir / job.id / "rerun_analysis.R")),
        ("km_analysis.R", str(settings.artifact_dir / job.id / "km_analysis.R")),
        (
            "clinical_covariates.R",
            str(settings.artifact_dir / job.id / "clinical_covariates.R"),
        ),
        ("cox_diagnostics.R", str(settings.artifact_dir / job.id / "cox_diagnostics.R")),
        (
            "competing_risks.R",
            str(settings.artifact_dir / job.id / "competing_risks.R"),
        ),
        ("renv.lock", str(settings.artifact_dir / job.id / "renv.lock")),
        (
            "Dockerfile.reproduce",
            str(settings.artifact_dir / job.id / "Dockerfile.reproduce"),
        ),
        ("REPRODUCE.md", str(settings.artifact_dir / job.id / "REPRODUCE.md")),
        (
            "reproduction_manifest.json",
            str(settings.artifact_dir / job.id / "reproduction_manifest.json"),
        ),
    ]
    optional_files = [
        ("cox_forest.png", str(settings.artifact_dir / job.id / "cox_forest.png")),
        ("cox_forest.svg", str(settings.artifact_dir / job.id / "cox_forest.svg")),
        ("continuous_effect.png", str(settings.artifact_dir / job.id / "continuous_effect.png")),
        ("continuous_effect.svg", str(settings.artifact_dir / job.id / "continuous_effect.svg")),
        ("cumulative_incidence.png", str(settings.artifact_dir / job.id / "cumulative_incidence.png")),
        ("cumulative_incidence.svg", str(settings.artifact_dir / job.id / "cumulative_incidence.svg")),
        ("continuous_data.csv", str(settings.artifact_dir / job.id / "continuous_data.csv")),
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
            samples = list(db.scalars(select(Sample).where(Sample.cohort == cohort.id)).all())
            candidates, filter_warnings, sample_selection = filter_sample_candidates(
                samples,
                request.filters,
                endpoint_by_patient=endpoint_by_patient,
                endpoint=endpoint_option["value"],
                endpoint_label=selected_option["label"],
            )
            candidate_expression, _, _, _ = expression_for_request(
                db,
                analysis_request,
                eligible_barcodes={sample.barcode for sample in candidates},
            )
            filtered, selection_warnings, sample_selection = (
                select_expression_complete_samples(
                    candidates,
                    set(candidate_expression),
                    warnings=filter_warnings,
                    summary=sample_selection,
                )
            )
            expression, cohort_signature, gene_warnings, _scoring_provenance = expression_for_request(
                db,
                analysis_request,
                eligible_barcodes={sample.barcode for sample in filtered},
            )
            signature_info = signature_info or cohort_signature
            records = pancancer_continuous_records(filtered, expression, endpoint_by_patient, request.filters.max_time_days)
            prepared.append(
                {
                    **base_result,
                    "endpoint": selected_option["value"],
                    "endpoint_label": selected_option["label"],
                    "endpoint_source": selected_option["source"],
                    "records": records,
                    "warnings": gene_warnings + selection_warnings,
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
    modeled_rows = attach_preparation_metadata(
        list(r_payload.get("results", [])),
        prepared,
    )
    rows = skipped_results + modeled_rows
    rows = apply_pancancer_postprocessing(rows, request)
    effect_scale, pooling_eligible, pooling_reason = (
        pancancer_effect_scale_policy(request)
    )
    rows = attach_effect_scale_metadata(
        rows,
        effect_scale,
        pooling_eligible,
    )
    clinical_sensitivity = add_clinical_sensitivity(
        rows,
        request.fdr_threshold,
        effect_scale=effect_scale,
        pooling_eligible=pooling_eligible,
        pooling_reason=pooling_reason,
    )
    reference = add_concordance_labels(rows, request.index_cohort)
    summary = summarize_pancancer_results(rows, request.index_cohort, request.fdr_threshold)
    meta_analysis = (
        common_scale_meta_analysis_from_rows(
            rows,
            effect_scale=effect_scale,
        )
        if pooling_eligible
        else {
            "available": False,
            "reason": pooling_reason,
            "comparability": "common_scale_unavailable",
            "effect_scale": effect_scale,
        }
    )

    result = {
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
        "effect_scale": effect_scale,
        "fdr_threshold": request.fdr_threshold,
        "pipeline_version": payload.get("pipeline_version"),
        "data_version": payload.get("data_version"),
        "request_snapshot": payload,
        "software_versions": r_payload.get("software_versions") or {},
        "summary": summary,
        "reference": reference,
        "meta_analysis": meta_analysis,
        "clinical_sensitivity": clinical_sensitivity,
        "results": rows,
        "warnings": pancancer_warnings(request, rows),
        "downloads": pancancer_downloads(scan_id),
    }
    result["audit"] = write_pancancer_artifacts(
        settings=settings,
        scan_id=scan_id,
        request_payload=payload,
        prepared_cohorts=prepared,
        result_payload=result,
        r_software_versions=r_payload.get("software_versions") or {},
    )
    return result


def pancancer_effect_scale_policy(
    request: PanCancerSurvivalRequest,
) -> tuple[dict[str, Any], bool, str | None]:
    scale_label = expression_scale_label(request.expression_scale)
    if request.signature_method == "single":
        common_unit = f"per +1 {scale_label}"
        common_description = (
            "Unstandardized single-gene expression coefficient on the "
            "request-wide RNA scale."
        )
    elif request.signature_method in {"mean", "weighted"}:
        common_unit = f"per +1 signature-score unit on {scale_label}"
        common_description = (
            "Unstandardized signature score using the same genes, weights "
            "and RNA scale in every cohort."
        )
    else:
        common_unit = "not transportable"
        common_description = (
            "The z-score signature is standardized separately inside each "
            "cohort and has no common raw score unit."
        )
    pooling_eligible = request.signature_method in {
        "single",
        "mean",
        "weighted",
    }
    pooling_reason = (
        None
        if pooling_eligible
        else (
            "Cohort-standardized z-score signatures are not numerically "
            "transportable across cohorts; no pooled estimate is reported."
        )
    )
    return (
        {
            "cohort_display": {
                "id": "within_cohort_standard_deviation",
                "unit": "per +1 within-cohort SD",
                "role": "descriptive cohort effect",
                "pooled": False,
            },
            "synthesis": {
                "id": "common_input_score_unit",
                "unit": common_unit,
                "description": common_description,
                "eligible": pooling_eligible,
            },
        },
        pooling_eligible,
        pooling_reason,
    )


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
                "grade": sample.grade,
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


def pancancer_warnings(
    request: PanCancerSurvivalRequest,
    rows: list[dict] | None = None,
) -> list[str]:
    warnings = []
    if request.endpoint_mode != "same_endpoint":
        warnings.append("Endpoint mode can select different but biologically related endpoints across cohorts; compare exact endpoint labels before interpreting concordance.")
    if request.filters.max_time_days is not None:
        warnings.append(
            f"Patients with follow-up time exceeding {request.filters.max_time_days:.0f} days are administratively censored at that time point (event = 0)."
        )
    if request.signature_method == "zscore":
        warnings.append(ZSCORE_TRANSPORTABILITY_MESSAGE)
    competing_endpoints = {
        str(row.get("endpoint") or "").upper()
        for row in rows or []
        if row.get("status") == "completed"
    } & COMPETING_RISK_ENDPOINTS
    if competing_endpoints:
        warnings.append(
            "Pan-cancer continuous models for "
            f"{', '.join(sorted(competing_endpoints))} are cause-specific Cox "
            "models that censor competing deaths; the per-analysis cumulative-"
            "incidence and Fine-Gray module is not synthesized pan-cancer."
        )
    return list(dict.fromkeys(warnings))


def pancancer_result_path(scan_id: str) -> Path:
    return settings.artifact_dir / "pancancer" / scan_id / "result.json"


def pancancer_downloads(scan_id: str) -> dict[str, str]:
    base = f"/api/pancancer/survival/{scan_id}/download"
    return {
        "csv": f"{base}/csv",
        "patients": f"{base}/patients",
        "methodology": f"{base}/methodology",
        "audit_json": f"{base}/audit_json",
        "audit_html": f"{base}/audit_html",
        "attestation": f"{base}/attestation",
        "raw_r_json": f"{base}/raw_r_json",
        "result_json": f"{base}/result_json",
        "zip": f"{base}/zip",
    }


def immune_screen_path(screen_id: str) -> Path:
    if not screen_id or any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-." for char in screen_id):
        raise HTTPException(status_code=404, detail="Immune pan-cancer screen not found.")
    return settings.artifact_dir / "immune_pancancer" / screen_id


def immune_screen_downloads(screen_id: str) -> dict[str, str]:
    base = f"/api/pancancer/immune-screens/{screen_id}/download"
    downloads = {
        "genes": f"{base}/genes",
        "cohorts": f"{base}/cohorts",
        "terms": f"{base}/terms",
        "results": f"{base}/results",
        "panel": f"{base}/panel",
        "manifest": f"{base}/manifest",
        "methodology": f"{base}/methodology",
    }
    screen_dir = immune_screen_path(screen_id)
    optional = {
        "gene_models": "gene_model_summary.csv",
        "cohort_models": "cohort_model_summary.csv",
        "term_models": "term_model_summary.csv",
        "sensitivity": "selected_sensitivity.csv",
        "family_summary": "model_family_summary.csv",
        "audit": "audit_report.json",
        "raw_results": "model_results.raw.csv",
        "zip": "model_results.csv",
    }
    for kind, filename in optional.items():
        if (screen_dir / filename).exists():
            downloads[kind] = f"{base}/{kind}"
    return downloads


def immune_atlas_bundle_path(
    screen_id: str,
    screen_dir: Path,
    source_paths: list[Path],
) -> Path:
    bundle_path = screen_dir / f"{screen_id}.atlas_bundle.zip"

    def is_current() -> bool:
        if not bundle_path.exists():
            return False
        bundle_mtime = bundle_path.stat().st_mtime_ns
        return all(
            bundle_mtime >= path.stat().st_mtime_ns
            for path in source_paths
        )

    if is_current():
        return bundle_path

    with _compute_file_lock(f"immune-atlas-bundle-{screen_id}"):
        if is_current():
            return bundle_path
        temporary_path = screen_dir / (
            f".{screen_id}.{uuid.uuid4().hex}.atlas_bundle.tmp"
        )
        try:
            with zipfile.ZipFile(
                temporary_path,
                mode="w",
                compression=zipfile.ZIP_DEFLATED,
            ) as archive:
                for path in source_paths:
                    archive.write(path, arcname=path.name)
            temporary_path.replace(bundle_path)
        finally:
            if temporary_path.exists():
                temporary_path.unlink()
    return bundle_path


def public_immune_screen_payload(payload: dict) -> dict:
    public_payload = dict(payload)
    public_payload.pop("paths", None)
    if isinstance(public_payload.get("audit"), dict):
        public_payload["audit"] = {
            key: value
            for key, value in public_payload["audit"].items()
            if key != "path"
        }
    return publicize_download_links(public_payload)


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
    versions = {
        item["source"]: {
            "manifest_hash": item["manifest_hash"],
            "data_through_date": item["data_through_date"],
            "data_release": item["data_release"],
        }
        for item in manifests
    }
    if "tcga_rna" not in versions:
        snapshot = publication_snapshot_summary(settings)
        versions["tcga_rna"] = {
            "source_summary_mtime": iso_from_path(settings.tcga_data_dir / "summary_table.tsv"),
            "publication_snapshot_manifest_hash": snapshot.get("manifest_hash"),
            "publication_snapshot_status": snapshot.get("status"),
        }
    if "tcga_cdr" not in versions:
        versions["tcga_cdr"] = {
            "source_file_mtime": iso_from_path(settings.tcga_cdr_path),
        }
    versions["clinical_metadata"] = {
        "latest_source_modified_at": latest_source_modified_at(settings.tcga_data_dir),
    }
    return versions


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
        adjustment_covariates=request.adjustment_covariates,
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


def expression_for_request(
    db: Session,
    request: AnalysisRequest,
    *,
    eligible_barcodes: set[str] | None = None,
) -> tuple[dict[str, float], dict, list[str], dict]:
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
        selected_barcodes = set(gene["values"])
        if eligible_barcodes is not None:
            selected_barcodes &= eligible_barcodes
        expression = {
            barcode: gene["values"][barcode]
            for barcode in sorted(selected_barcodes)
        }
        scoring_provenance = build_scoring_provenance(
            request=request,
            values_by_gene=values_by_gene,
            selected_barcodes=selected_barcodes,
            expression=expression,
            standardization=[],
            eligible_barcode_count=len(eligible_barcodes) if eligible_barcodes is not None else None,
        )
        return expression, {
            "method": "single",
            "label": gene["resolved_symbol"],
            "genes": signature_gene_payload(values_by_gene),
            "scoring_population": scoring_population_summary(scoring_provenance),
        }, warnings, scoring_provenance

    common_barcodes = set(values_by_gene[0]["values"])
    for gene in values_by_gene[1:]:
        common_barcodes &= set(gene["values"])
    if eligible_barcodes is not None:
        common_barcodes &= eligible_barcodes
    if len(common_barcodes) < 10:
        raise ValueError(
            "The multi-gene signature has fewer than 10 eligible patients with expression for all genes."
        )

    standardization: list[dict] = []
    if request.signature_method == "zscore":
        z_values = {}
        for gene in values_by_gene:
            vals = [gene["values"][barcode] for barcode in common_barcodes]
            mean = sum(vals) / len(vals)
            variance = sum((value - mean) ** 2 for value in vals) / max(len(vals) - 1, 1)
            sd = math.sqrt(variance) or 1.0
            standardization.append(
                {
                    "resolved_symbol": gene["resolved_symbol"],
                    "center": mean,
                    "sample_standard_deviation": sd,
                    "n": len(vals),
                }
            )
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
    scoring_provenance = build_scoring_provenance(
        request=request,
        values_by_gene=values_by_gene,
        selected_barcodes=common_barcodes,
        expression=expression,
        standardization=standardization,
        eligible_barcode_count=len(eligible_barcodes) if eligible_barcodes is not None else None,
    )
    return expression, {
        "method": request.signature_method,
        "label": label,
        "genes": signature_gene_payload(values_by_gene),
        "sample_overlap": len(common_barcodes),
        "standardization": standardization,
        "scoring_population": scoring_population_summary(scoring_provenance),
    }, warnings, scoring_provenance


def build_scoring_provenance(
    *,
    request: AnalysisRequest,
    values_by_gene: list[dict],
    selected_barcodes: set[str],
    expression: dict[str, float],
    standardization: list[dict],
    eligible_barcode_count: int | None,
) -> dict:
    ordered_barcodes = sorted(selected_barcodes)
    components = []
    standardization_by_gene = {
        item["resolved_symbol"]: item
        for item in standardization
    }
    for gene in values_by_gene:
        selected_values = [
            {
                "sample_barcode": barcode,
                "expression_value": gene["values"][barcode],
            }
            for barcode in ordered_barcodes
        ]
        component = {
            "query": gene["gene_symbol"],
            "resolved_symbol": gene["resolved_symbol"],
            "weight": gene["weight"],
            "source_value_count": len(gene["values"]),
            "selected_value_count": len(selected_values),
            "selected_values_sha256": stable_hash({"values": selected_values}),
            "selected_values": selected_values,
        }
        if gene["resolved_symbol"] in standardization_by_gene:
            component["standardization"] = standardization_by_gene[gene["resolved_symbol"]]
        components.append(component)

    score_values = [
        {
            "sample_barcode": barcode,
            "score": expression[barcode],
        }
        for barcode in ordered_barcodes
    ]
    return {
        "schema_version": "tcga-trace-scoring-provenance-v1",
        "method": "single" if len(values_by_gene) == 1 else request.signature_method,
        "population_rule": (
            "samples after user filters and endpoint completeness, followed by complete "
            "expression for the requested gene or every signature component, then "
            "one-expression-complete-sample-per-participant biospecimen selection"
        ),
        "eligible_barcode_count": eligible_barcode_count,
        "complete_case_barcode_count": len(ordered_barcodes),
        "weight_denominator": (
            (sum(abs(gene["weight"]) for gene in values_by_gene) or 1.0)
            if request.signature_method in {"zscore", "weighted"} and len(values_by_gene) > 1
            else len(values_by_gene)
        ),
        "components": components,
        "score_values_sha256": stable_hash({"values": score_values}),
        "score_values": score_values,
    }


def scoring_population_summary(scoring_provenance: dict) -> dict:
    return {
        "rule": scoring_provenance["population_rule"],
        "eligible_barcode_count": scoring_provenance["eligible_barcode_count"],
        "complete_case_barcode_count": scoring_provenance["complete_case_barcode_count"],
        "score_values_sha256": scoring_provenance["score_values_sha256"],
        "component_value_hashes": {
            item["resolved_symbol"]: item["selected_values_sha256"]
            for item in scoring_provenance["components"]
        },
    }


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
    paths = [
        job.png_path,
        job.csv_path,
        job.json_path,
        str(methodology_path(job.id)),
        str(audit_report_json_path(job.id)),
        str(audit_report_html_path(job.id)),
        str(attestation_receipt_path(job.id)),
    ]
    return all(path and Path(path).exists() for path in paths)


def methodology_path(analysis_id: str) -> Path:
    return settings.artifact_dir / analysis_id / "methodology.txt"


def audit_report_json_path(analysis_id: str) -> Path:
    return settings.artifact_dir / analysis_id / "audit_report.json"


def audit_report_html_path(analysis_id: str) -> Path:
    return settings.artifact_dir / analysis_id / "audit_report.html"


def attestation_receipt_path(analysis_id: str) -> Path:
    return settings.artifact_dir / analysis_id / "attestation_receipt.json"


def ensure_reproduction_capsule(analysis_id: str) -> dict[str, str]:
    return write_reproduction_capsule(
        settings.artifact_dir / analysis_id,
        r_script_path=settings.r_script_path,
        renv_lock_path=Path(__file__).resolve().parents[1] / "renv.lock",
    )


def analysis_out(job: AnalysisJob) -> AnalysisOut:
    downloads = {}
    if job.status == "completed":
        downloads = {
            "png": f"/api/analyses/{job.id}/download/png",
            "svg": f"/api/analyses/{job.id}/download/svg",
            "csv": f"/api/analyses/{job.id}/download/csv",
            "json": f"/api/analyses/{job.id}/download/json",
            "zip": f"/api/analyses/{job.id}/download/zip",
        }
        if methodology_path(job.id).exists():
            downloads["txt"] = f"/api/analyses/{job.id}/download/txt"
        if audit_report_json_path(job.id).exists():
            downloads["audit_json"] = f"/api/analyses/{job.id}/download/audit_json"
        if audit_report_html_path(job.id).exists():
            downloads["audit_html"] = f"/api/analyses/{job.id}/download/audit_html"
        if attestation_receipt_path(job.id).exists():
            downloads["attestation"] = (
                f"/api/analyses/{job.id}/download/attestation"
            )
        if (settings.artifact_dir / job.id / "rerun_analysis.R").exists():
            downloads["r_script"] = f"/api/analyses/{job.id}/download/r_script"
            downloads["reproduction_manifest"] = (
                f"/api/analyses/{job.id}/download/reproduction_manifest"
            )
        if (settings.artifact_dir / job.id / "cox_forest.png").exists():
            downloads["cox_png"] = f"/api/analyses/{job.id}/download/cox_png"
            downloads["cox_svg"] = f"/api/analyses/{job.id}/download/cox_svg"
        if (settings.artifact_dir / job.id / "continuous_effect.png").exists():
            downloads["continuous_png"] = f"/api/analyses/{job.id}/download/continuous_png"
            downloads["continuous_svg"] = f"/api/analyses/{job.id}/download/continuous_svg"
        if (settings.artifact_dir / job.id / "continuous_data.csv").exists():
            downloads["continuous_csv"] = f"/api/analyses/{job.id}/download/continuous_csv"
        if (settings.artifact_dir / job.id / "cumulative_incidence.png").exists():
            downloads["cumulative_incidence_png"] = (
                f"/api/analyses/{job.id}/download/cumulative_incidence_png"
            )
            downloads["cumulative_incidence_svg"] = (
                f"/api/analyses/{job.id}/download/cumulative_incidence_svg"
            )
    notices, diagnostics = build_analysis_diagnostics(job.warnings, job.metrics)
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
        notices=notices,
        diagnostics=diagnostics,
        error=job.error,
        downloads=downloads,
        cached=job.cached,
    )


# ---------------------------------------------------------------------------
# Public API v1
# ---------------------------------------------------------------------------

from fastapi import APIRouter, status
from fastapi.encoders import jsonable_encoder
from fastapi.exception_handlers import (
    http_exception_handler as default_http_exception_handler,
    request_validation_exception_handler as default_validation_exception_handler,
)
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.jobs import (
    ComputeQueueError,
    compute_jobs_referencing_analysis,
    compute_job_out,
    job_retains_artifacts,
    publicize_download_links,
    queue_summary,
    submit_compute_job,
)
from app.models import ComputeJob
from app.schemas import ComputeJobOut, ErrorOut, PublicApiIndexOut, PublicHealthOut


API_V1_PREFIX = "/api/v1"
public_router = APIRouter(
    prefix=API_V1_PREFIX,
    responses={
        404: {"model": ErrorOut, "description": "The requested public resource was not found."},
        409: {"model": ErrorOut, "description": "The resource exists but is not ready."},
        410: {"model": ErrorOut, "description": "The retained public artifact has expired."},
        422: {"model": ErrorOut, "description": "The request failed contract or scientific validation."},
        429: {"model": ErrorOut, "description": "The anonymous compute quota was exceeded."},
        503: {"model": ErrorOut, "description": "The bounded public compute queue is full."},
    },
)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


@app.exception_handler(HTTPException)
async def public_http_exception_handler(request: Request, exc: HTTPException):
    if not request.url.path.startswith(API_V1_PREFIX):
        return await default_http_exception_handler(request, exc)
    detail = exc.detail
    if isinstance(detail, dict):
        code = str(detail.get("code") or f"HTTP_{exc.status_code}")
        message = str(detail.get("message") or detail.get("detail") or "Request failed.")
        details = detail.get("details") or {}
    else:
        code = f"HTTP_{exc.status_code}"
        message = str(detail)
        details = {}
    headers = dict(exc.headers or {})
    headers["X-Request-ID"] = request.state.request_id
    return JSONResponse(
        status_code=exc.status_code,
        headers=headers,
        content={
            "error": {
                "code": code,
                "message": message,
                "details": details,
                "request_id": request.state.request_id,
            }
        },
    )


@app.exception_handler(RequestValidationError)
async def public_validation_exception_handler(request: Request, exc: RequestValidationError):
    if not request.url.path.startswith(API_V1_PREFIX):
        return await default_validation_exception_handler(request, exc)
    return JSONResponse(
        status_code=422,
        headers={"X-Request-ID": request.state.request_id},
        content={
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "The request did not match the documented API contract.",
                "details": {"errors": jsonable_encoder(exc.errors())},
                "request_id": request.state.request_id,
            }
        },
    )


def _public_client_key(request: Request) -> str:
    session_id = request.headers.get("mcp-session-id")
    if session_id:
        return f"mcp:{session_id}"
    real_ip = request.headers.get("x-real-ip")
    if not real_ip:
        forwarded = request.headers.get("x-forwarded-for", "")
        real_ip = forwarded.split(",", 1)[0].strip() if forwarded else ""
    if not real_ip and request.client is not None:
        real_ip = request.client.host
    return f"rest:{real_ip or 'anonymous'}"


def _queue_http_error(exc: ComputeQueueError) -> HTTPException:
    headers = {"Retry-After": str(exc.retry_after)} if exc.retry_after else None
    return HTTPException(
        status_code=exc.status_code,
        detail={"code": exc.code, "message": exc.message},
        headers=headers,
    )


def _submit_public_job(
    kind: str,
    payload: dict,
    request: Request,
    response: Response,
    db: Session,
    cache_context_extra: dict | None = None,
) -> ComputeJobOut:
    cache_context = compute_cache_context(
        kind,
        data_version=current_data_version(db),
    )
    if cache_context_extra:
        cache_context = {
            **cache_context,
            **cache_context_extra,
        }
    try:
        job = submit_compute_job(
            db,
            kind=kind,
            request_payload=payload,
            client_key=_public_client_key(request),
            settings=settings,
            cache_context=cache_context,
        )
    except ComputeQueueError as exc:
        raise _queue_http_error(exc) from exc
    output = compute_job_out(job, settings)
    response.headers["Location"] = output.status_url
    response.headers["Retry-After"] = "2"
    return output


def _public_analysis(job: AnalysisJob) -> AnalysisOut:
    payload = publicize_download_links(analysis_out(job).model_dump(mode="json"))
    return AnalysisOut(**payload)


def _ensure_public_result_retained(db: Session, result_id: str, kinds: set[str]) -> None:
    if kinds == {"analysis", "combined"}:
        references = compute_jobs_referencing_analysis(db, result_id)
    else:
        references = list(
            db.scalars(
                select(ComputeJob)
                .where(ComputeJob.result_id == result_id)
                .where(ComputeJob.kind.in_(kinds))
            ).all()
        )
    if not references:
        return
    if not any(job_retains_artifacts(reference) for reference in references):
        raise HTTPException(
            status_code=410,
            detail={
                "code": "ARTIFACT_EXPIRED",
                "message": "Generated artifacts expired after the public retention period. Submit the request again to regenerate them.",
            },
        )


@public_router.get(
    "/",
    response_model=PublicApiIndexOut,
    tags=["Service"],
    operation_id="getPublicApiIndex",
    summary="Discover the public API",
)
def public_api_index() -> PublicApiIndexOut:
    base_url = settings.public_base_url.rstrip("/")
    return PublicApiIndexOut(
        name=app.title,
        app_version=app.version,
        api_version="v1",
        status="available",
        description=(
            "Stable public API for exploratory TCGA transcriptomic survival analysis. "
            "Use the health resource for live service and dataset readiness."
        ),
        links={
            "web_application": f"{base_url}/",
            "health": f"{base_url}/api/v1/health",
            "swagger_ui": f"{base_url}/api/docs",
            "redoc": f"{base_url}/api/redoc",
            "openapi": f"{base_url}/api/openapi.json",
            "attestation_keys": (
                f"{base_url}/api/v1/attestation/keys"
            ),
            "mcp": f"{base_url}/mcp",
        },
    )


@public_router.get(
    "/attestation/keys",
    tags=["Attestation"],
    operation_id="listAttestationKeys",
    summary="List server attestation keys",
)
def list_public_attestation_keys() -> dict:
    try:
        return attestation_keyset(settings)
    except AttestationError as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "ATTESTATION_UNAVAILABLE",
                "message": str(exc),
            },
        ) from exc


@public_router.get(
    "/attestation/keys/{key_id}",
    tags=["Attestation"],
    operation_id="getAttestationKey",
    summary="Retrieve one server attestation key",
)
def get_public_attestation_key(key_id: str) -> dict:
    try:
        return attestation_key_document(settings, key_id)
    except AttestationError as exc:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "ATTESTATION_KEY_NOT_FOUND",
                "message": str(exc),
            },
        ) from exc


@public_router.get(
    "/health",
    response_model=PublicHealthOut,
    tags=["Service"],
    operation_id="getPublicHealth",
)
def public_health(db: SessionDep) -> PublicHealthOut:
    cohort_count = int(db.scalar(select(func.count()).select_from(Cohort)) or 0)
    cache_manifest = load_cache_manifest(settings.derived_expression_dir)
    cache_summary = summarize_cache_manifest(cache_manifest)
    return PublicHealthOut(
        status="ok" if cache_summary.get("status") == "ready" else "degraded",
        app_version=app.version,
        api_version="v1",
        release=application_release_identity(),
        pipeline_versions={
            "analysis": ANALYSIS_PIPELINE_VERSION,
            "combined_signatures": COMBINED_SIGNATURE_PIPELINE_VERSION,
            "multiverse": MULTIVERSE_PIPELINE_VERSION,
            "pancancer": PANCANCER_PIPELINE_VERSION,
            "exploratory_session": SESSION_HISTORY_PIPELINE_VERSION,
            "immune_atlas": IMMUNE_ATLAS_PIPELINE_VERSION,
        },
        cohorts=cohort_count,
        cache_status=str(cache_summary.get("status") or "unknown"),
        data_dates=dataset_dates(db, cache_manifest),
        queue=queue_summary(db, settings),
    )


def application_release_identity() -> dict[str, str]:
    return {
        "commit": settings.app_release_commit.strip() or "development",
        "ref": settings.app_release_ref.strip() or "development",
    }


@public_router.get(
    "/dataset/summary",
    tags=["Dataset"],
    operation_id="getDatasetSummary",
)
def public_dataset_summary(db: SessionDep, cohort: str | None = None) -> dict:
    summary = build_dataset_summary(db, cohort)
    summary.pop("cache", None)
    return summary


@public_router.get(
    "/dataset/summary/download/csv",
    tags=["Dataset"],
    operation_id="downloadDatasetSummaryCsv",
    response_class=Response,
)
def public_dataset_summary_csv(db: SessionDep, cohort: str | None = None) -> Response:
    return dataset_summary_download("csv", db, cohort)


@public_router.get(
    "/data-sources",
    tags=["Dataset"],
    operation_id="listPublicDataSources",
)
def public_data_sources(db: SessionDep) -> dict:
    sources = []
    for source in list_data_sources(db):
        sources.append(
            {
                key: value
                for key, value in source.items()
                if key not in {"source_path"}
            }
        )
    return {"sources": sources}


@public_router.get(
    "/endpoints",
    tags=["Dataset"],
    operation_id="listSurvivalEndpoints",
)
def public_endpoints(db: SessionDep) -> dict:
    return endpoint_options(db)


@public_router.get(
    "/expression-scales",
    response_model=list[ExpressionScaleOut],
    tags=["Dataset"],
    operation_id="listExpressionScales",
)
def public_expression_scales() -> list[dict[str, str]]:
    return list_expression_scales()


@public_router.get(
    "/examples/paper",
    tags=["Examples"],
    operation_id="getPaperExamples",
)
def get_public_paper_examples(response: Response) -> dict:
    response.headers["Cache-Control"] = "no-store"
    try:
        return build_paper_examples(
            settings.publication_benchmark_dir,
            settings.artifact_dir,
        )
    except (FileNotFoundError, OSError, csv.Error, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "EXAMPLES_UNAVAILABLE",
                "message": "The reproducible paper example catalog is unavailable.",
            },
        ) from exc


@public_router.get(
    "/examples/paper/figures/{analysis_id}/{kind}",
    tags=["Examples"],
    operation_id="getPaperExampleFigure",
    response_class=FileResponse,
)
def get_public_paper_example_figure(analysis_id: str, kind: str) -> FileResponse:
    path = publication_figure_path(
        settings.publication_benchmark_dir,
        settings.artifact_dir,
        analysis_id,
        kind,
    )
    if path is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "EXAMPLE_FIGURE_NOT_FOUND",
                "message": "The requested paper example figure is not available.",
            },
        )
    return FileResponse(
        path,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=86400"},
    )


@public_router.get(
    "/cohorts",
    response_model=list[CohortOut],
    tags=["Cohorts"],
    operation_id="listCohorts",
)
def public_cohorts(db: SessionDep) -> list[Cohort]:
    return list_cohorts(db)


@public_router.get(
    "/cohorts/{cohort_id}/endpoints",
    tags=["Cohorts"],
    operation_id="getCohortEndpoints",
)
def public_cohort_endpoints(cohort_id: str, db: SessionDep) -> dict:
    return cohort_endpoint_options(cohort_id, db)


@public_router.get(
    "/cohorts/{cohort_id}/filters",
    response_model=FilterOptions,
    tags=["Cohorts"],
    operation_id="getCohortFilterOptions",
)
def public_cohort_filters(cohort_id: str, db: SessionDep) -> FilterOptions:
    return filter_options(cohort_id, db)


@public_router.get(
    "/cohorts/{cohort_id}/genes",
    response_model=GeneSearchOut,
    tags=["Cohorts"],
    operation_id="searchCohortGenes",
)
def public_cohort_genes(
    cohort_id: str,
    db: SessionDep,
    query: str = "",
    limit: int = 25,
) -> GeneSearchOut:
    if limit < 1 or limit > 100:
        raise HTTPException(
            status_code=422,
            detail={"code": "INVALID_LIMIT", "message": "limit must be between 1 and 100."},
        )
    return search_genes(cohort_id, db, query, limit)


@public_router.get(
    "/cohorts/{cohort_id}/genes/resolve",
    tags=["Cohorts"],
    operation_id="resolveCohortGene",
)
def public_resolve_gene(cohort_id: str, db: SessionDep, query: str) -> dict:
    return resolve_gene(cohort_id, db, query)


@public_router.post(
    "/analyses",
    response_model=ComputeJobOut,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["Analyses"],
    operation_id="submitSurvivalAnalysis",
)
def submit_public_analysis(
    request_body: AnalysisRequest,
    request: Request,
    response: Response,
    db: SessionDep,
) -> ComputeJobOut:
    return _submit_public_job("analysis", request_body.model_dump(mode="json"), request, response, db)


@public_router.post(
    "/analyses/combined",
    response_model=ComputeJobOut,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["Analyses"],
    operation_id="submitCombinedSignatureAnalysis",
)
def submit_public_combined_analysis(
    request_body: CombinedSignatureAnalysisRequest,
    request: Request,
    response: Response,
    db: SessionDep,
) -> ComputeJobOut:
    return _submit_public_job("combined", request_body.model_dump(mode="json"), request, response, db)


@public_router.post(
    "/analyses/batch",
    response_model=ComputeJobOut,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["Analyses"],
    operation_id="submitAnalysisBatch",
)
def submit_public_analysis_batch(
    request_body: PublicAnalysisBatchRequest,
    request: Request,
    response: Response,
    db: SessionDep,
) -> ComputeJobOut:
    if len(request_body.analyses) > settings.public_batch_max_analyses:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "BATCH_TOO_LARGE",
                "message": f"Public batches are limited to {settings.public_batch_max_analyses} analyses.",
            },
        )
    payload = request_body.model_dump(mode="json")
    payload["max_concurrency"] = 1
    return _submit_public_job("batch", payload, request, response, db)


@public_router.post(
    "/analyses/multiverse",
    response_model=ComputeJobOut,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["Analyses"],
    operation_id="submitPrespecifiedMultiverse",
)
def submit_public_multiverse(
    request_body: MultiverseAnalysisRequest,
    request: Request,
    response: Response,
    db: SessionDep,
) -> ComputeJobOut:
    planned = (
        len(request_body.endpoints)
        * len(request_body.scoring_methods)
        * len(request_body.cutpoint_methods)
    )
    if planned > settings.public_multiverse_max_analyses:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "MULTIVERSE_TOO_LARGE",
                "message": (
                    "Public multiverses are limited to "
                    f"{settings.public_multiverse_max_analyses} specifications."
                ),
            },
        )
    return _submit_public_job(
        "multiverse",
        request_body.model_dump(mode="json"),
        request,
        response,
        db,
    )


@public_router.get(
    "/analyses/batches/{batch_id}",
    response_model=AnalysisBatchOut,
    tags=["Analyses"],
    operation_id="getAnalysisBatch",
)
def get_public_analysis_batch(batch_id: str, db: SessionDep) -> AnalysisBatchOut:
    job = db.get(ComputeJob, batch_id)
    if job is None or job.kind != "batch":
        raise HTTPException(status_code=404, detail={"code": "JOB_NOT_FOUND", "message": "Batch not found."})
    if job.status == "expired":
        raise HTTPException(status_code=410, detail={"code": "ARTIFACT_EXPIRED", "message": "Batch artifacts expired."})
    if job.status != "completed" or job.result_json is None:
        raise HTTPException(
            status_code=409,
            detail={"code": "JOB_NOT_COMPLETE", "message": f"Batch status is {job.status}."},
        )
    return AnalysisBatchOut(**job.result_json)


@public_router.get(
    "/analyses/multiverses/{session_id}",
    response_model=MultiverseAnalysisOut,
    tags=["Analyses"],
    operation_id="getPrespecifiedMultiverse",
)
def get_public_multiverse(
    session_id: str,
    db: SessionDep,
) -> MultiverseAnalysisOut:
    _ensure_public_result_retained(db, session_id, {"multiverse"})
    job = db.scalar(
        select(ComputeJob)
        .where(ComputeJob.kind == "multiverse")
        .where(ComputeJob.result_id == session_id)
    )
    if job is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "MULTIVERSE_NOT_FOUND",
                "message": "Multiverse session not found.",
            },
        )
    if job.status != "completed" or job.result_json is None:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "JOB_NOT_COMPLETE",
                "message": f"Multiverse status is {job.status}.",
            },
        )
    return MultiverseAnalysisOut(**job.result_json)


@public_router.get(
    "/analyses/multiverses/{session_id}/download/{kind}",
    tags=["Analyses"],
    operation_id="downloadPrespecifiedMultiverseArtifact",
    response_class=Response,
)
def download_public_multiverse_artifact(
    session_id: str,
    kind: str,
    db: SessionDep,
) -> Response:
    _ensure_public_result_retained(db, session_id, {"multiverse"})
    session_dir = settings.artifact_dir / "multiverse" / session_id
    files = {
        "svg": ("specification_curve.svg", "image/svg+xml"),
        "csv": ("specifications.csv", "text/csv"),
        "continuous_csv": ("continuous_references.csv", "text/csv"),
        "json": ("multiverse_result.json", "application/json"),
        "ledger": ("execution_ledger.json", "application/json"),
        "audit_json": ("audit_report.json", "application/json"),
        "audit_html": ("audit_report.html", "text/html"),
        "attestation": ("attestation_receipt.json", "application/json"),
        "methodology": ("methodology.txt", "text/plain"),
    }
    if kind == "zip":
        buffer = io.BytesIO()
        with zipfile.ZipFile(
            buffer,
            mode="w",
            compression=zipfile.ZIP_DEFLATED,
        ) as archive:
            for filename, _media_type in files.values():
                path = session_dir / filename
                if path.exists():
                    archive.write(path, arcname=filename)
        return Response(
            content=buffer.getvalue(),
            media_type="application/zip",
            headers={
                "Content-Disposition": (
                    f'attachment; filename="{session_id}.multiverse.zip"'
                )
            },
        )
    if kind not in files:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "INVALID_DOWNLOAD_KIND",
                "message": (
                    "Download kind must be svg, csv, continuous_csv, json, "
                    "ledger, audit_json, audit_html, attestation, methodology "
                    "or zip."
                ),
            },
        )
    filename, media_type = files[kind]
    path = session_dir / filename
    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail={
                "code": "ARTIFACT_NOT_FOUND",
                "message": f"Multiverse artifact {kind} is not available.",
            },
        )
    return FileResponse(
        path,
        media_type=media_type,
        filename=f"{session_id}.{filename}",
    )


@public_router.post(
    "/analyses/sessions/export",
    response_model=ComputeJobOut,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["Analyses"],
    operation_id="exportExploratorySession",
    summary="Export selected browser runs as one exploratory record",
)
def submit_public_exploratory_session(
    request_body: ExploratorySessionExportRequest,
    request: Request,
    response: Response,
    db: SessionDep,
) -> ComputeJobOut:
    source_context = []
    for job_id in sorted(
        {entry.job_id for entry in request_body.entries}
    ):
        source = db.get(ComputeJob, job_id)
        source_context.append(
            {
                "job_id": job_id,
                "kind": source.kind if source is not None else None,
                "status": source.status if source is not None else "missing",
                "params_hash": (
                    source.params_hash if source is not None else None
                ),
                "result_id": (
                    source.result_id if source is not None else None
                ),
                "result_sha256": (
                    stable_hash(source.result_json)
                    if source is not None
                    and source.result_json is not None
                    else None
                ),
            }
        )
    return _submit_public_job(
        "session",
        request_body.model_dump(mode="json"),
        request,
        response,
        db,
        cache_context_extra={"source_jobs": source_context},
    )


@public_router.get(
    "/analyses/sessions/{report_id}",
    response_model=ExploratorySessionOut,
    tags=["Analyses"],
    operation_id="getExploratorySession",
)
def get_public_exploratory_session(
    report_id: str,
    db: SessionDep,
) -> ExploratorySessionOut:
    _ensure_public_result_retained(db, report_id, {"session"})
    job = db.scalar(
        select(ComputeJob)
        .where(ComputeJob.kind == "session")
        .where(ComputeJob.result_id == report_id)
    )
    if job is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "SESSION_REPORT_NOT_FOUND",
                "message": "Exploratory session report not found.",
            },
        )
    if job.status != "completed" or job.result_json is None:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "JOB_NOT_COMPLETE",
                "message": f"Exploratory session status is {job.status}.",
            },
        )
    return ExploratorySessionOut(**job.result_json)


@public_router.get(
    "/analyses/sessions/{report_id}/download/{kind}",
    tags=["Analyses"],
    operation_id="downloadExploratorySessionArtifact",
    response_class=Response,
)
def download_public_exploratory_session_artifact(
    report_id: str,
    kind: str,
    db: SessionDep,
) -> Response:
    _ensure_public_result_retained(db, report_id, {"session"})
    report_dir = settings.artifact_dir / "sessions" / report_id
    files = {
        "json": ("session_report.json", "application/json"),
        "runs_csv": ("runs.csv", "text/csv"),
        "hypotheses_csv": ("hypotheses.csv", "text/csv"),
        "ledger": ("execution_ledger.json", "application/json"),
        "audit_json": ("audit_report.json", "application/json"),
        "audit_html": ("audit_report.html", "text/html"),
        "attestation": ("attestation_receipt.json", "application/json"),
        "methodology": ("methodology.txt", "text/plain"),
    }
    if kind == "zip":
        buffer = io.BytesIO()
        with zipfile.ZipFile(
            buffer,
            mode="w",
            compression=zipfile.ZIP_DEFLATED,
        ) as archive:
            for filename, _media_type in files.values():
                path = report_dir / filename
                if path.exists():
                    archive.write(path, arcname=filename)
        return Response(
            content=buffer.getvalue(),
            media_type="application/zip",
            headers={
                "Content-Disposition": (
                    f'attachment; filename="{report_id}.session.zip"'
                )
            },
        )
    if kind not in files:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "INVALID_DOWNLOAD_KIND",
                "message": (
                    "Download kind must be json, runs_csv, hypotheses_csv, "
                    "ledger, audit_json, audit_html, attestation, methodology "
                    "or zip."
                ),
            },
        )
    filename, media_type = files[kind]
    path = report_dir / filename
    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail={
                "code": "ARTIFACT_NOT_FOUND",
                "message": (
                    f"Exploratory session artifact {kind} is not available."
                ),
            },
        )
    return FileResponse(
        path,
        media_type=media_type,
        filename=f"{report_id}.{filename}",
    )


@public_router.get(
    "/analyses/{analysis_id}",
    response_model=AnalysisOut,
    tags=["Analyses"],
    operation_id="getSurvivalAnalysis",
)
def get_public_analysis(analysis_id: str, db: SessionDep) -> AnalysisOut:
    _ensure_public_result_retained(db, analysis_id, {"analysis", "combined"})
    job = db.get(AnalysisJob, analysis_id)
    if job is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "ANALYSIS_NOT_FOUND", "message": "Analysis not found."},
        )
    return _public_analysis(job)


@public_router.get(
    "/analyses/{analysis_id}/download/{kind}",
    tags=["Analyses"],
    operation_id="downloadAnalysisArtifact",
    response_class=Response,
)
def download_public_analysis(analysis_id: str, kind: str, db: SessionDep) -> Response:
    _ensure_public_result_retained(db, analysis_id, {"analysis", "combined"})
    return download_analysis(analysis_id, kind, db)


@public_router.post(
    "/pancancer/survival",
    response_model=ComputeJobOut,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["Pan-cancer"],
    operation_id="submitPanCancerSurvival",
)
def submit_public_pancancer(
    request_body: PanCancerSurvivalRequest,
    request: Request,
    response: Response,
    db: SessionDep,
) -> ComputeJobOut:
    return _submit_public_job("pancancer", request_body.model_dump(mode="json"), request, response, db)


@public_router.get(
    "/pancancer/survival/{scan_id}",
    response_model=PanCancerSurvivalOut,
    tags=["Pan-cancer"],
    operation_id="getPanCancerSurvival",
)
def get_public_pancancer(scan_id: str, db: SessionDep) -> PanCancerSurvivalOut:
    _ensure_public_result_retained(db, scan_id, {"pancancer"})
    path = pancancer_result_path(scan_id)
    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail={"code": "SCAN_NOT_FOUND", "message": "Pan-cancer scan not found."},
        )
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["downloads"] = publicize_download_links(pancancer_downloads(scan_id))
    payload["results"] = normalize_pancancer_rows(payload.get("results", []))
    return PanCancerSurvivalOut(**payload)


@public_router.get(
    "/pancancer/survival/{scan_id}/download/csv",
    tags=["Pan-cancer"],
    operation_id="downloadPanCancerCsv",
    response_class=Response,
)
def download_public_pancancer(scan_id: str, db: SessionDep) -> Response:
    _ensure_public_result_retained(db, scan_id, {"pancancer"})
    return download_pancancer_survival(scan_id, db)


@public_router.get(
    "/pancancer/survival/{scan_id}/download/{kind}",
    tags=["Pan-cancer"],
    operation_id="downloadPanCancerArtifact",
    response_class=Response,
)
def download_public_pancancer_artifact(
    scan_id: str,
    kind: str,
    db: SessionDep,
) -> Response:
    return download_pancancer_survival_artifact(scan_id, kind, db)


@public_router.get(
    "/pancancer/immune-screens",
    tags=["Pan-cancer"],
    operation_id="listImmunePanCancerScreens",
)
def list_public_immune_screens() -> dict:
    return publicize_download_links(list_immune_pancancer_screens())


@public_router.get(
    "/pancancer/immune-screens/{screen_id}",
    tags=["Pan-cancer"],
    operation_id="getImmunePanCancerScreen",
)
def get_public_immune_screen(screen_id: str) -> dict:
    return public_immune_screen_payload(
        get_immune_pancancer_screen(screen_id)
    )


@public_router.get(
    "/pancancer/immune-screens/{screen_id}/download/{kind}",
    tags=["Pan-cancer"],
    operation_id="downloadImmunePanCancerArtifact",
    response_class=FileResponse,
)
def download_public_immune_screen(screen_id: str, kind: str) -> Response:
    return download_immune_pancancer_screen(screen_id, kind)


@public_router.get(
    "/jobs/{job_id}",
    response_model=ComputeJobOut,
    tags=["Jobs"],
    operation_id="getComputeJob",
)
def get_public_compute_job(job_id: str, db: SessionDep) -> ComputeJobOut:
    job = db.get(ComputeJob, job_id)
    if job is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "JOB_NOT_FOUND", "message": "Compute job not found."},
        )
    return compute_job_out(job, settings)


app.include_router(public_router)


from app.mcp_server import mcp, mcp_http_app

mcp.settings.streamable_http_path = "/mcp"
app.mount("/", mcp_http_app(), name="mcp")


from fastapi.openapi.utils import get_openapi


def public_openapi() -> dict:
    if app.openapi_schema is not None:
        return app.openapi_schema
    public_routes = [
        route
        for route in app.routes
        if getattr(route, "path", "").startswith(API_V1_PREFIX)
    ]
    schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=public_routes,
    )
    schema["servers"] = app.servers
    schema["tags"] = app.openapi_tags
    schema["externalDocs"] = {
        "description": "Public API and MCP integration guide",
        "url": f"{settings.public_base_url.rstrip('/')}/api/guide",
    }
    schema["info"]["x-artifact-retention-days"] = settings.artifact_retention_days
    schema["info"]["x-clinical-use"] = "not-intended"
    app.openapi_schema = schema
    return schema


app.openapi = public_openapi
