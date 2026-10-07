from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, timezone
import csv
from app import file_lock as fcntl
import hashlib
import io
import json
import logging
import math
import re
import secrets
import shutil
import tempfile
import time
import uuid
import zipfile
from pathlib import Path
from typing import Annotated, Any

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import FileResponse, Response
from sqlalchemy import desc, distinct, func, select
from sqlalchemy.orm import Session
from pydantic import ValidationError

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
    write_attestation_receipt,
)
from app.config import get_settings
from app.api_docs import install_api_docs
from app.client_identity import request_client_ip
from app.clinical_grouping import (
    CLINICAL_GROUPING_CATALOG_VERSION,
    TCGA_ANNOTATION_FIELDS,
    clinical_grouping_context,
    resolve_clinical_grouping_variable,
)
from app.database import SessionLocal, get_db, init_db, wait_for_database
from app.data_sync.sync import current_sync_status
from app.expression import (
    GeneNotFoundError,
    expression_scale_label,
    expression_scale_options,
    get_expression_for_gene,
)
from app.expression_comparison import (
    EXPRESSION_COMPARISON_RESULT_SCHEMA,
    extract_expression_value_rows,
    finalize_expression_comparison_artifacts,
    resolve_expression_genes,
    run_expression_comparison_engine,
)
from app.external_covariates import prepare_external_covariates
from app.gene_aliases import GENE_ALIASES, resolve_gene_symbol
from app.gsea import (
    GSEA_RESULT_SCHEMA,
    clinical_group_assignments,
    combine_camera_inference_with_preranked_effects,
    dataset_samples,
    expression_group_assignments,
    group_assignment_rows,
    gsea_summary,
    prepare_camera_expression_matrix,
    public_gene_set_catalog,
    read_gmt,
    resolve_expression_matrix,
    resolve_gene_set_collection,
    run_camera_gene_set_test,
    run_preranked_effects,
    select_gsea_samples,
    survival_group_assignments,
    validate_group_assignments,
    write_gsea_artifacts,
)
from app.hierarchical_pancancer_service import (
    build_hierarchical_preflight,
    hierarchical_download_files,
    hierarchical_downloads,
    hierarchical_repository_version,
    hierarchical_result_path,
    hierarchical_scan_identity,
    run_hierarchical_pancancer_analysis,
)
from app.importer import (
    COMPETING_ENDPOINT_COLUMNS,
    TCGA_CDR_SOURCE_ID,
    TCGA_RNA_SOURCE_ID,
    ensure_gene_index,
    import_cohorts_and_samples,
    import_tcga_cdr,
)
from app.models import (
    AnalysisJob,
    CancerType,
    ClinicalEndpoint,
    Cohort,
    DataManifest,
    DataSource,
    GeneIndex,
    RepositoryDataset,
    RepositoryRelease,
    Sample,
)
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
    GSEA_PIPELINE_VERSION,
    EXPRESSION_COMPARISON_PIPELINE_VERSION,
    HIERARCHICAL_PANCANCER_PIPELINE_VERSION,
    MULTIVERSE_PIPELINE_VERSION,
    PANCANCER_PIPELINE_VERSION,
    SESSION_HISTORY_PIPELINE_VERSION,
    SIGNATURE_PANEL_PIPELINE_VERSION,
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
from app.repository import sync_repository_catalog
from app.repository.capabilities import available_repository_modules
from app.repository.candidates import (
    CandidateRegistryError,
    list_dataset_candidates,
)
from app.repository.importer import load_manifest as load_repository_manifest
from app.repository.service import (
    RepositoryContext,
    list_repository_datasets,
    repository_data_provenance,
    repository_dataset_detail,
    repository_endpoint_options,
    repository_endpoint_outcomes,
    repository_expression_layer_paths,
    repository_expression_layer_coverage,
    repository_expression_layers,
    repository_filter_options,
    repository_gene_expression,
    require_repository_capability,
    repository_capabilities,
    repository_samples,
    repository_requires_independent_arm,
    repository_release_storage_path,
    resolve_expression_layer,
    resolve_repository_context,
    search_repository_genes,
)
from app.repository.storage import safe_bundle_path
from app.schemas import (
    AnalysisBatchItemOut,
    AnalysisBatchOut,
    AnalysisBatchRequest,
    AnalysisFilters,
    AnalysisOut,
    AnalysisRequest,
    CombinedSignatureAnalysisRequest,
    CohortOut,
    ExpressionComparisonOut,
    ExpressionComparisonRequest,
    ExpressionScaleOut,
    ExploratorySessionExportRequest,
    ExploratorySessionOut,
    FilterOptions,
    GeneSearchOut,
    GseaAnalysisOut,
    GseaAnalysisRequest,
    HierarchicalPanCancerOut,
    HierarchicalPanCancerPreflightOut,
    HierarchicalPanCancerRequest,
    MultiverseAnalysisOut,
    MultiverseAnalysisRequest,
    PanCancerSurvivalOut,
    PanCancerSurvivalRequest,
    PublicAnalysisBatchRequest,
    SignaturePanelAnalysisRequest,
    SignatureSpec,
    UserDatasetMapping,
    UserDatasetCreatedOut,
    UserDatasetOut,
)
from app.session_history import (
    build_exploratory_session_report,
    write_exploratory_session_artifacts,
)
from app.sample_population import (
    EXPLICIT_POPULATION_COHORTS,
    SAMPLE_POPULATION_CONTRACT_VERSION,
    resolve_tcga_sample_population,
    sample_matches_population,
    sample_population_metadata_conflict,
    tcga_population_options,
)
from app.signature_panel import (
    build_signature_panel_records,
    run_signature_panel_r,
    signature_gene_overlap,
    standardize_signature_scores,
    write_signature_panel_audit,
    write_signature_panel_reproduction_capsule,
)
from app.signature_scoring import (
    EXPECTED_PACKAGE_VERSIONS,
    RANK_BASED_METHODS,
    SIGNATURE_SCORING_CONTRACT_VERSION,
    effective_direction,
    run_rank_based_signature_score,
    signature_method_label,
)
from app.tutorial_assets import (
    TutorialAssetNotFound,
    build_tutorial_asset,
    tutorial_asset_catalog,
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
from app.user_datasets import (
    UserDatasetError,
    authorize_user_dataset,
    authorize_user_datasets_in_payload,
    create_user_dataset,
    delete_user_dataset,
    expire_user_datasets,
    get_user_dataset,
    private_dataset_ids as private_dataset_ids_in_payload,
    user_dataset_access_token_hash,
)

settings = get_settings()
logger = logging.getLogger(__name__)
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
    if not settings.public_api_enabled:
        yield
        return
    from app.mcp_server import mcp

    async with mcp.session_manager.run():
        yield


app = FastAPI(
    title=f"{settings.app_name} Public API",
    description=(
        "Public, endpoint-aware transcriptomic survival analysis API for TCGA, "
        "curated independent cohorts and temporary private user datasets. "
        "Results are exploratory research outputs and are not intended for clinical decision-making."
    ),
    version="1.0.0",
    docs_url=None,
    redoc_url=None,
    openapi_url="/api/openapi.json",
    servers=[{"url": settings.public_base_url.rstrip("/"), "description": "Production"}],
    openapi_tags=[
        {"name": "Service", "description": "Public readiness and version information."},
        {"name": "Dataset", "description": "TCGA dataset, sources, endpoints, and expression scales."},
        {"name": "Cohorts", "description": "Cohort metadata, filters, endpoint availability, and genes."},
        {"name": "User data", "description": "Temporary private expression and patient-metadata datasets; survival outcomes are optional."},
        {"name": "Examples", "description": "Reproducible figures and benchmark cases from the application paper."},
        {"name": "Tutorials", "description": "Versioned synthetic datasets for guided, reproducible learning workflows."},
        {"name": "Analyses", "description": "Asynchronous survival analyses and reproducible artifacts."},
        {"name": "GSEA", "description": "Preranked gene-set enrichment between two traceable patient groups."},
        {"name": "Pan-cancer", "description": "Pan-cancer survival scans and immune screens."},
        {"name": "Attestation", "description": "Server signing keys for independent receipt verification."},
        {"name": "Jobs", "description": "Persistent compute job status and results."},
    ],
    root_path=settings.public_path_prefix.rstrip("/"),
    root_path_in_servers=False,
    lifespan=app_lifespan,
)
install_api_docs(app)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=[
        "Accept",
        "Authorization",
        "Content-Type",
        "X-Request-ID",
        "X-TRACE-Dataset-Token",
    ],
    expose_headers=["Retry-After", "X-Request-ID"],
    max_age=600,
)
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=settings.allowed_host_list,
)


def _private_dataset_access_token(request: Request) -> str | None:
    authorization = request.headers.get("authorization", "").strip()
    if authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    else:
        token = request.headers.get("x-trace-dataset-token", "").strip()
    return token if token and len(token) <= 256 else None


@app.middleware("http")
async def private_response_cache_middleware(request: Request, call_next):
    response = await call_next(request)
    if _private_dataset_access_token(request):
        response.headers["Cache-Control"] = "private, no-store"
        response.headers["Pragma"] = "no-cache"
    return response


def startup() -> None:
    wait_for_database()
    init_db()
    settings.artifact_dir.mkdir(parents=True, exist_ok=True)
    settings.derived_expression_dir.mkdir(parents=True, exist_ok=True)
    settings.user_dataset_dir.mkdir(parents=True, exist_ok=True)
    with SessionLocal() as db:
        expire_user_datasets(db, settings)
    if settings.bootstrap_on_startup:
        with SessionLocal() as db:
            import_cohorts_and_samples(db, settings.tcga_data_dir)
            import_tcga_cdr(db, settings.tcga_cdr_path)
            sync_repository_catalog(
                db, settings.cancer_repository_registry_dir
            )
            if settings.preload_cache_on_startup:
                warm_startup_cache(db, settings)
                build_dataset_summary(db)


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
    return f"rest-ip:{request_client_ip(request)}"


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
        authorize_user_datasets_in_payload(
            db,
            payload,
            _private_dataset_access_token(request),
        )
        _preflight_repository_capabilities(
            db,
            kind=kind,
            payload=payload,
        )
        job = submit_compute_job(
            db,
            kind=kind,
            request_payload=payload,
            client_key=_legacy_client_key(request),
            settings=settings,
            cache_context=compute_cache_context(kind, data_version=current_data_version(db)),
        )
    except UserDatasetError as exc:
        db.rollback()
        raise _user_dataset_http_error(exc) from exc
    except ComputeQueueError as exc:
        db.rollback()
        headers = {"Retry-After": str(exc.retry_after)} if exc.retry_after else None
        raise HTTPException(
            status_code=exc.status_code,
            detail={
                "code": exc.code,
                "message": exc.message,
                "details": exc.details,
            },
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
    repository_coverage = build_repository_coverage(db)
    return {
        "status": "ok",
        "app_version": app.version,
        "release": application_release_identity(),
        "pipeline_versions": {
            "analysis": ANALYSIS_PIPELINE_VERSION,
            "combined_signatures": COMBINED_SIGNATURE_PIPELINE_VERSION,
            "signature_panel": SIGNATURE_PANEL_PIPELINE_VERSION,
            "gsea": GSEA_PIPELINE_VERSION,
            "expression_comparison": EXPRESSION_COMPARISON_PIPELINE_VERSION,
            "multiverse": MULTIVERSE_PIPELINE_VERSION,
            "pancancer": PANCANCER_PIPELINE_VERSION,
            "pancancer_hierarchical": HIERARCHICAL_PANCANCER_PIPELINE_VERSION,
            "exploratory_session": SESSION_HISTORY_PIPELINE_VERSION,
            "immune_atlas": IMMUNE_ATLAS_PIPELINE_VERSION,
            "clinical_grouping_catalog": CLINICAL_GROUPING_CATALOG_VERSION,
            "signature_scoring": SIGNATURE_SCORING_CONTRACT_VERSION,
        },
        "signature_scoring": {
            "contract_version": SIGNATURE_SCORING_CONTRACT_VERSION,
            "rank_based_methods": sorted(RANK_BASED_METHODS),
            "package_versions": EXPECTED_PACKAGE_VERSIONS,
        },
        "cohorts": cohorts,
        "external_repository": {
            "status": (
                "ready"
                if settings.cancer_repository_dir.is_dir()
                else "storage_unavailable"
            ),
            "datasets": repository_coverage["datasets"],
            "patient_records_across_active_releases": repository_coverage[
                "patient_records_across_active_releases"
            ],
            "rna_samples_across_active_releases": repository_coverage[
                "rna_samples_across_active_releases"
            ],
            "represented_cancer_types": repository_coverage[
                "represented_cancer_types"
            ],
            "available_cancer_types": repository_coverage[
                "available_cancer_types"
            ],
            "total_cancer_types": repository_coverage[
                "total_cancer_types"
            ],
            "evidence_gaps": repository_coverage["evidence_gaps"],
            "search_in_progress": repository_coverage[
                "search_in_progress"
            ],
        },
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
    _require_tcga_catalog(cohort_id, db, resource="endpoints")
    return {"cohort": cohort_id, "endpoints": endpoint_options_for_cohort(db, cohort_id)}


def _require_tcga_catalog(cohort_id: str, db: Session, *, resource: str) -> None:
    cohort = db.get(Cohort, cohort_id)
    if cohort is None:
        raise HTTPException(status_code=404, detail="Cohort not found.")
    if cohort.status == "external_only":
        raise HTTPException(
            status_code=422,
            detail={
                "code": "DATASET_REQUIRED",
                "message": (
                    "This cancer is available through external datasets, not TCGA. "
                    "Choose a dataset first using /api/v1/datasets, then use "
                    f"/api/v1/datasets/{{dataset_id}}/{resource}. "
                    "Endpoint availability and clinical metadata belong to the "
                    "selected study and release."
                ),
            },
        )


def _require_tcga_gene_catalog(cohort_id: str, db: Session) -> None:
    _require_tcga_catalog(cohort_id, db, resource="genes")


@app.get("/api/cohorts/{cohort_id}/genes/resolve")
def resolve_gene(cohort_id: str, db: SessionDep, query: str) -> dict:
    _require_tcga_gene_catalog(cohort_id, db)
    return resolve_gene_symbol(db, settings.tcga_data_dir, cohort_id, query)


_DATASET_SUMMARY_CACHE: dict[tuple[Any, ...], dict[str, Any]] = {}


def _dataset_summary_revision(db: Session) -> tuple[Any, ...]:
    """Return a cheap revision key for every table used by the summary."""
    return (
        db.scalar(select(func.max(Cohort.imported_at))),
        int(db.scalar(select(func.count()).select_from(Sample)) or 0),
        int(db.scalar(select(func.max(DataManifest.id))) or 0),
        db.scalar(select(func.max(DataSource.imported_at))),
    )


def build_dataset_summary(
    db: Session,
    cohort: str | None = None,
    *,
    include_data_sources: bool = True,
    include_data_sync: bool = True,
) -> dict:
    revision = _dataset_summary_revision(db)
    cache_key = (cohort or "__all__", *revision)
    cached = _DATASET_SUMMARY_CACHE.get(cache_key)
    if cached is None:
        cached = _compute_dataset_summary(db, cohort)
        for stale_key in list(_DATASET_SUMMARY_CACHE):
            if stale_key[1:] != revision:
                _DATASET_SUMMARY_CACHE.pop(stale_key, None)
        _DATASET_SUMMARY_CACHE[cache_key] = cached
    summary = dict(cached)
    if not include_data_sources:
        summary.pop("data_sources", None)
    if not include_data_sync:
        summary.pop("data_sync", None)
    return summary


def _compute_dataset_summary(db: Session, cohort: str | None = None) -> dict:
    if cohort and db.get(Cohort, cohort) is None:
        raise HTTPException(status_code=404, detail="Cohort not found.")
    if cohort and not cohort.startswith("TCGA-"):
        raise HTTPException(status_code=400, detail={
            "code": "DATASET_REQUIRED",
            "message": "The TCGA summary requires a TCGA cohort; inspect external studies through the dataset repository.",
        })
    cache_manifest = load_cache_manifest(settings.derived_expression_dir)
    cohort_stmt = select(Cohort).where(Cohort.id.like("TCGA-%")).order_by(Cohort.id)
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
        "biological_annotations": biological_annotations(cohort, db),
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
    cohorts = [cohort] if cohort else list(db.scalars(
        select(Cohort.id).where(Cohort.id.like("TCGA-%")).order_by(Cohort.id)
    ).all())
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


def repository_context_for_request(
    db: Session,
    request: (
        AnalysisRequest
        | CombinedSignatureAnalysisRequest
        | ExpressionComparisonRequest
        | GseaAnalysisRequest
        | SignaturePanelAnalysisRequest
    ),
    *,
    required_analysis: str | None = None,
) -> RepositoryContext | None:
    if not request.dataset_id:
        return None
    context = resolve_repository_context(
        db,
        request.dataset_id,
        request.dataset_release_id,
        include_private=request.dataset_id.startswith("user-"),
    )
    if context.cohort != request.cohort:
        raise ValueError(
            f"Dataset {context.dataset.id} belongs to {context.cohort}, "
            f"not {request.cohort}."
        )
    if required_analysis:
        require_repository_capability(context, required_analysis)
    return context


def selected_analysis_inputs(
    db: Session,
    request: (
        AnalysisRequest
        | CombinedSignatureAnalysisRequest
        | SignaturePanelAnalysisRequest
    ),
    context: RepositoryContext | None,
) -> tuple[list, dict[str, ClinicalOutcome] | None, dict, dict]:
    if context is None:
        endpoint_by_patient, endpoint_option = selected_endpoint_outcomes(
            db, request.cohort, request.endpoint
        )
        samples = list(
            db.scalars(
                select(Sample).where(Sample.cohort == request.cohort)
            ).all()
        )
        selection = {
            "selection_rule": "tcga",
            "endpoint_source": endpoint_option["source"],
            "clinical_filter_cohort": request.cohort,
            "clinical_filter_tcga_data_dir": getattr(
                settings, "tcga_data_dir", None
            ),
            "clinical_filter_tcga_cdr_path": getattr(
                settings, "tcga_cdr_path", None
            ),
            "clinical_filter_repository": False,
        }
        return samples, endpoint_by_patient, endpoint_option, selection
    endpoint_by_patient, endpoint_option = repository_endpoint_outcomes(
        db, context, request.endpoint
    )
    return (
        repository_samples(db, context),
        endpoint_by_patient,
        endpoint_option,
        {
            "selection_rule": (
                "user_supplied"
                if context.dataset.visibility == "private"
                else "external_curated"
            ),
            "endpoint_source": endpoint_option["source"],
            "required_single_study_arm": (
                repository_requires_independent_arm(context, request.endpoint)
            ),
            "clinical_filter_cohort": request.cohort,
            "clinical_filter_repository": True,
        },
    )


def analysis_expression_metadata(
    db: Session,
    request: (
        AnalysisRequest
        | CombinedSignatureAnalysisRequest
        | SignaturePanelAnalysisRequest
    ),
    context: RepositoryContext | None,
) -> tuple[str, str]:
    if context is None:
        return (
            request.expression_scale,
            expression_scale_label(request.expression_scale),
        )
    layer = resolve_expression_layer(
        db, context, request.expression_layer_id
    )
    return layer.layer_id, layer.label


def analysis_dataset_dates(
    db: Session, context: RepositoryContext | None
) -> dict:
    dates = dataset_dates(
        db, load_cache_manifest(settings.derived_expression_dir)
    )
    if context is not None:
        is_private = context.dataset.visibility == "private"
        dates = {
            **dates,
            "user_dataset" if is_private else "external_dataset": {
                "dataset_id": context.dataset.id,
                "release_id": context.release.id,
                "version": context.release.version,
                "manifest_hash": context.release.manifest_hash,
                "source_snapshot": context.release.source_snapshot,
                "expires_at": (
                    context.dataset.expires_at.isoformat() + "Z"
                    if context.dataset.expires_at
                    else None
                ),
                "published_at": (
                    context.release.published_at.isoformat()
                    if context.release.published_at
                    else None
                ),
            },
        }
    return dates


def repository_version_payload(context: RepositoryContext) -> dict:
    return {
        "dataset_id": context.dataset.id,
        "release_id": context.release.id,
        "version": context.release.version,
        "manifest_hash": context.release.manifest_hash,
        "source_snapshot": context.release.source_snapshot,
        "expires_at": (
            context.dataset.expires_at.isoformat() + "Z"
            if context.dataset.expires_at
            else None
        ),
    }


def analysis_dataset_payload(
    context: RepositoryContext | None,
    cohort: str,
) -> dict:
    if context is None:
        return {
            "kind": "tcga",
            "dataset_id": cohort,
            "release_id": None,
        }
    return {
        "kind": (
            "user"
            if context.dataset.visibility == "private"
            else "external"
        ),
        "dataset_id": context.dataset.id,
        "release_id": context.release.id,
        "name": context.dataset.name,
        "cancer_code": context.cancer.code,
        "manifest_hash": context.release.manifest_hash,
        "cohort_context": context.dataset.cohort_context,
        "expires_at": (
            context.dataset.expires_at.isoformat() + "Z"
            if context.dataset.expires_at
            else None
        ),
    }


@app.get("/api/expression-scales", response_model=list[ExpressionScaleOut])
def list_expression_scales() -> list[dict[str, str]]:
    return expression_scale_options()


def build_repository_coverage(
    db: Session,
    *,
    include_search: bool = True,
) -> dict:
    dataset_rows = list(
        db.execute(
            select(
                RepositoryDataset.id,
                RepositoryDataset.cancer_code,
                RepositoryRelease.patient_count,
                RepositoryRelease.sample_count,
            )
            .outerjoin(
                RepositoryRelease,
                (
                    RepositoryRelease.id
                    == RepositoryDataset.active_release_id
                )
                & (RepositoryRelease.dataset_id == RepositoryDataset.id),
            )
            .where(RepositoryDataset.status == "available")
            .where(RepositoryDataset.visibility == "public")
        ).all()
    )
    by_cancer: dict[str, list[str]] = {}
    patient_records_across_active_releases = 0
    rna_samples_across_active_releases = 0
    for dataset_id, cancer_code, patient_count, sample_count in dataset_rows:
        by_cancer.setdefault(cancer_code, []).append(dataset_id)
        patient_records_across_active_releases += int(patient_count or 0)
        rna_samples_across_active_releases += int(sample_count or 0)
    tcga_cohort_ids = set(
        db.scalars(
            select(Cohort.id).where(
                (Cohort.status.is_(None))
                | (Cohort.status != "external_only")
            )
        ).all()
    )
    represented_cancer_codes = set(by_cancer)
    rows = []
    for cancer in db.scalars(
        select(CancerType).order_by(CancerType.sort_order)
    ).all():
        if cancer.tcga_cohort in tcga_cohort_ids:
            represented_cancer_codes.add(cancer.code)
        available = sorted(by_cancer.get(cancer.code, []))
        row = {
                "code": cancer.code,
                "tcga_cohort": cancer.tcga_cohort,
                "name": cancer.name,
                "primary_site": cancer.primary_site,
                "coverage_status": (
                    "available" if available else cancer.coverage_status
                ),
                "dataset_count": len(available),
                "datasets": available,
            }
        if include_search:
            row["search"] = cancer.coverage_metadata or {}
        rows.append(row)
    return {
        "schema_version": "tcga-trace-repository-coverage-v2",
        "total_cancer_types": len(rows),
        "represented_cancer_types": len(represented_cancer_codes),
        "available_cancer_types": sum(
            row["coverage_status"] == "available" for row in rows
        ),
        "evidence_gaps": sum(
            row["coverage_status"] == "evidence_gap" for row in rows
        ),
        "search_in_progress": sum(
            row["coverage_status"] == "search_in_progress" for row in rows
        ),
        "datasets": len(dataset_rows),
        "patient_records_across_active_releases": (
            patient_records_across_active_releases
        ),
        "rna_samples_across_active_releases": (
            rna_samples_across_active_releases
        ),
        "cancers": rows,
    }


@app.get("/api/cancer-types")
def list_cancer_types(db: SessionDep) -> dict:
    return build_repository_coverage(db)


@app.get("/api/datasets")
def list_datasets(
    db: SessionDep,
    cancer_code: str | None = None,
    analysis_type: str | None = None,
) -> dict:
    try:
        datasets = list_repository_datasets(
            db,
            cancer_code=cancer_code,
            analysis_type=analysis_type,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "INVALID_ANALYSIS_TYPE",
                "message": str(exc),
            },
        ) from exc
    return {"datasets": datasets}


@app.get("/api/dataset-candidates")
def dataset_candidates(
    disease_id: str | None = None,
    status: str | None = None,
    analysis_type: str | None = None,
    query: str | None = None,
) -> dict:
    """List adjudicated candidates without presenting them as ready datasets."""
    try:
        return list_dataset_candidates(
            disease_id=disease_id,
            status=status,
            analysis_type=analysis_type,
            query=query,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "INVALID_CANDIDATE_FILTER",
                "message": str(exc),
            },
        ) from exc
    except (CandidateRegistryError, FileNotFoundError, OSError) as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "CANDIDATE_REGISTRY_UNAVAILABLE",
                "message": "The reviewed-candidate registry is temporarily unavailable.",
            },
        ) from exc


@app.get("/api/datasets/{dataset_id}")
def get_dataset(dataset_id: str, db: SessionDep) -> dict:
    try:
        context = resolve_repository_context(db, dataset_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return repository_dataset_detail(db, context)


@app.get("/api/datasets/{dataset_id}/endpoints")
def get_dataset_endpoints(
    dataset_id: str,
    db: SessionDep,
    release_id: str | None = None,
) -> dict:
    try:
        context = resolve_repository_context(db, dataset_id, release_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "dataset_id": dataset_id,
        "release_id": context.release.id,
        "endpoints": repository_endpoint_options(db, context),
    }


@app.get("/api/datasets/{dataset_id}/expression-layers")
def get_dataset_expression_layers(
    dataset_id: str,
    db: SessionDep,
    release_id: str | None = None,
) -> dict:
    try:
        context = resolve_repository_context(db, dataset_id, release_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "dataset_id": dataset_id,
        "release_id": context.release.id,
        "expression_layers": repository_expression_layers(db, context),
    }


@app.get("/api/datasets/{dataset_id}/filters", response_model=FilterOptions)
def get_dataset_filters(
    dataset_id: str,
    db: SessionDep,
    release_id: str | None = None,
) -> FilterOptions:
    try:
        context = resolve_repository_context(db, dataset_id, release_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return FilterOptions(**repository_filter_options(db, context))


@app.get("/api/datasets/{dataset_id}/genes", response_model=GeneSearchOut)
def search_dataset_genes(
    dataset_id: str,
    db: SessionDep,
    query: str = "",
    limit: int = 25,
    release_id: str | None = None,
    expression_layer_id: str | None = None,
) -> GeneSearchOut:
    try:
        context = resolve_repository_context(db, dataset_id, release_id)
        genes = search_repository_genes(
            db,
            context,
            query,
            layer_id=expression_layer_id,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return GeneSearchOut(cohort=context.cohort, query=query, genes=genes)


@app.get("/api/datasets/{dataset_id}/genes/resolve")
def resolve_dataset_gene(
    dataset_id: str,
    db: SessionDep,
    query: str,
    release_id: str | None = None,
    expression_layer_id: str | None = None,
) -> dict:
    try:
        context = resolve_repository_context(db, dataset_id, release_id)
        _, _, gene = repository_gene_expression(
            db, context, query, expression_layer_id
        )
    except GeneNotFoundError as exc:
        return {
            "query": query.strip().upper(),
            "resolved": None,
            "status": "not_found",
            "warnings": [str(exc)],
        }
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    normalized = query.strip().upper()
    return {
        "query": normalized,
        "resolved": gene.gene_symbol,
        "status": (
            "exact" if normalized == gene.gene_symbol else "alias"
        ),
        "warnings": (
            []
            if normalized == gene.gene_symbol
            else [f"Gene alias {normalized} was resolved to {gene.gene_symbol}."]
        ),
    }


@app.get("/api/datasets/{dataset_id}/download/{kind}")
def download_dataset_resource(
    dataset_id: str,
    kind: str,
    db: SessionDep,
    release_id: str | None = None,
    expression_layer_id: str | None = None,
) -> Response:
    try:
        context = resolve_repository_context(db, dataset_id, release_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if kind == "manifest":
        release_path = repository_release_storage_path(context)
        return FileResponse(
            release_path / "manifest.json",
            filename=f"{dataset_id}-{context.release.version}-manifest.json",
            media_type="application/json",
        )
    if kind == "qc":
        return Response(
            content=json.dumps(
                context.release.qc_json or {},
                indent=2,
                sort_keys=True,
            ),
            media_type="application/json",
            headers={
                "Content-Disposition": (
                    f'attachment; filename="{dataset_id}-{context.release.version}-qc.json"'
                )
            },
        )
    if kind in {"matrix", "matrix-metadata", "genes"}:
        layer = resolve_expression_layer(
            db, context, expression_layer_id
        )
        if not (
            context.dataset.redistribution_allowed and layer.downloadable
        ):
            raise HTTPException(
                status_code=403,
                detail="The source terms do not allow matrix redistribution.",
            )
        release_path = repository_release_storage_path(context)
        matrix_path, metadata_path = repository_expression_layer_paths(
            context, layer
        )
        manifest = load_repository_manifest(release_path)
        layer_manifest = next(
            (
                row
                for row in manifest.get("expression_layers") or []
                if row.get("layer_id") == layer.layer_id
            ),
            None,
        )
        if layer_manifest is None:
            raise HTTPException(
                status_code=500,
                detail="Expression layer is absent from its release manifest.",
            )
        if kind == "matrix-metadata":
            return FileResponse(
                metadata_path,
                filename=(
                    f"{dataset_id}-{context.release.version}-"
                    f"{layer.layer_id}-metadata.json"
                ),
                media_type="application/json",
            )
        if kind == "genes":
            return FileResponse(
                safe_bundle_path(
                    release_path,
                    str(layer_manifest["genes_file"]),
                ),
                filename=(
                    f"{dataset_id}-{context.release.version}-"
                    f"{layer.layer_id}-genes.tsv"
                ),
                media_type="text/tab-separated-values",
            )
        return FileResponse(
            matrix_path,
            filename=f"{dataset_id}-{context.release.version}-{layer.layer_id}.float32le.bin",
            media_type="application/octet-stream",
        )
    if kind == "license":
        release_path = repository_release_storage_path(context)
        manifest = load_repository_manifest(release_path)
        relative = (manifest.get("source_files") or {}).get("license")
        if not relative:
            raise HTTPException(
                status_code=404,
                detail="No license file is included in this release.",
            )
        return FileResponse(
            safe_bundle_path(
                release_path, str(relative)
            ),
            filename=f"{dataset_id}-{context.release.version}-LICENSE.txt",
            media_type="text/plain",
        )
    raise HTTPException(status_code=404, detail="Unsupported dataset download.")


@app.get("/api/cohorts", response_model=list[CohortOut])
def list_cohorts(db: SessionDep) -> list[Cohort]:
    return list(db.scalars(select(Cohort).order_by(Cohort.id)).all())


@app.get("/api/cohorts/{cohort_id}/genes", response_model=GeneSearchOut)
def search_genes(cohort_id: str, db: SessionDep, query: str = "", limit: int = 25) -> GeneSearchOut:
    _require_tcga_gene_catalog(cohort_id, db)
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
def filter_options(
    cohort_id: str,
    db: SessionDep,
    sample_population: str | None = None,
) -> FilterOptions:
    _require_tcga_catalog(cohort_id, db, resource="filters")

    samples = list(
        db.scalars(select(Sample).where(Sample.cohort == cohort_id)).all()
    )
    try:
        population_policy, selected_population = resolve_tcga_sample_population(
            cohort_id,
            sample_population,
            require_explicit_skcm=False,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    population_samples = [
        sample
        for sample in samples
        if sample_matches_population(sample, population_policy)
    ]

    def population_values(attribute: str) -> list[str]:
        return sorted(
            {
                str(value)
                for sample in population_samples
                if (value := getattr(sample, attribute, None)) not in (None, "")
            },
            key=str.casefold,
        )

    age_values = [
        float(sample.age_at_index)
        for sample in population_samples
        if sample.age_at_index is not None
    ]
    os_values = [
        float(sample.os_time_days)
        for sample in population_samples
        if sample.os_time_days is not None
    ]
    clinical_variables, _ = clinical_grouping_context(
        population_samples,
        cohort=cohort_id,
        tcga_data_dir=settings.tcga_data_dir,
        tcga_cdr_path=settings.tcga_cdr_path,
    )
    return FilterOptions(
        sample_types=population_values("sample_type"),
        sample_populations=tcga_population_options(cohort_id, samples),
        selected_sample_population=selected_population,
        population_selection_required=(
            cohort_id in EXPLICIT_POPULATION_COHORTS
            and sample_population is None
        ),
        sample_population_metadata_conflicts=sum(
            sample_population_metadata_conflict(sample) for sample in samples
        ),
        stages=population_values("stage"),
        grades=population_values("grade"),
        genders=population_values("gender"),
        races=population_values("race"),
        age_min=min(age_values) if age_values else None,
        age_max=max(age_values) if age_values else None,
        os_time_max_days=max(os_values) if os_values else None,
        clinical_grouping_variables=clinical_variables,
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
    repository_context = repository_context_for_request(
        db, request, required_analysis="survival"
    )
    payload = request.model_dump(mode="json")
    payload["pipeline_version"] = ANALYSIS_PIPELINE_VERSION
    payload["signature_scoring_contract"] = SIGNATURE_SCORING_CONTRACT_VERSION
    payload["sample_population_contract"] = SAMPLE_POPULATION_CONTRACT_VERSION
    payload["data_version"] = current_data_version(db)
    if repository_context is not None:
        payload[
            "user_data_version"
            if repository_context.dataset.visibility == "private"
            else "external_data_version"
        ] = repository_version_payload(repository_context)
    params_hash = stable_hash(payload)
    existing = db.scalar(select(AnalysisJob).where(AnalysisJob.params_hash == params_hash))
    if existing and existing.status == "completed" and _artifacts_exist(existing):
        existing.cached = True
        db.commit()
        return analysis_out(existing)

    cohort = db.get(Cohort, request.cohort)
    if repository_context is None and cohort is None:
        raise HTTPException(status_code=404, detail="Cohort not found.")

    if existing:
        analysis_id = existing.id
        job = existing
        job.status = "running"
        job.cohort = request.cohort
        job.dataset_id = request.dataset_id
        job.dataset_release_id = request.dataset_release_id
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
            dataset_id=request.dataset_id,
            dataset_release_id=request.dataset_release_id,
            gene_symbol=request.gene_symbol.strip().upper(),
            cutpoint_method=request.cutpoint_method,
            request_payload=payload,
            warnings=[],
        )
        db.add(job)
    db.commit()

    try:
        (
            samples,
            endpoint_by_patient,
            endpoint_option,
            selection_options,
        ) = selected_analysis_inputs(db, request, repository_context)
        endpoint_label = endpoint_option["label"]
        candidates, filter_warnings, sample_selection = filter_sample_candidates(
            samples,
            request.filters,
            endpoint_by_patient=endpoint_by_patient,
            endpoint=request.endpoint,
            endpoint_label=endpoint_label,
            **selection_options,
        )
        candidate_expression, _, _, _ = expression_for_request(
            db,
            request,
            eligible_barcodes={sample.barcode for sample in candidates},
            repository_context=repository_context,
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
            repository_context=repository_context,
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
        if repository_context is None:
            data_provenance = analysis_data_provenance(
                settings,
                cohort=request.cohort,
                expression_scale=request.expression_scale,
                selected_barcodes=set(expression),
            )
        else:
            layer = resolve_expression_layer(
                db, repository_context, request.expression_layer_id
            )
            data_provenance = repository_data_provenance(
                repository_context,
                layer,
                selected_sample_ids=set(expression),
            )
        analysis_data_dates = analysis_dataset_dates(
            db, repository_context
        )
        effective_expression_scale, effective_expression_label = (
            analysis_expression_metadata(db, request, repository_context)
        )
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
            expression_scale=effective_expression_scale,
            expression_scale_label=effective_expression_label,
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
        metrics["expression_scale"] = effective_expression_scale
        metrics["expression_scale_label"] = effective_expression_label
        metrics["endpoint_source"] = endpoint_option["source"]
        metrics["endpoint_qc"] = endpoint_option
        metrics["dataset"] = analysis_dataset_payload(
            repository_context,
            request.cohort,
        )
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
    repository_context = repository_context_for_request(
        db, request, required_analysis="survival"
    )
    payload = request.model_dump(mode="json")
    payload["pipeline_version"] = COMBINED_SIGNATURE_PIPELINE_VERSION
    payload["signature_scoring_contract"] = SIGNATURE_SCORING_CONTRACT_VERSION
    payload["sample_population_contract"] = SAMPLE_POPULATION_CONTRACT_VERSION
    payload["data_version"] = current_data_version(db)
    if repository_context is not None:
        payload[
            "user_data_version"
            if repository_context.dataset.visibility == "private"
            else "external_data_version"
        ] = repository_version_payload(repository_context)
    params_hash = stable_hash(payload)
    existing = db.scalar(select(AnalysisJob).where(AnalysisJob.params_hash == params_hash))
    if existing and existing.status == "completed" and _artifacts_exist(existing):
        existing.cached = True
        db.commit()
        return analysis_out(existing)

    cohort = db.get(Cohort, request.cohort)
    if repository_context is None and cohort is None:
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
        job.dataset_id = request.dataset_id
        job.dataset_release_id = request.dataset_release_id
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
            dataset_id=request.dataset_id,
            dataset_release_id=request.dataset_release_id,
            gene_symbol=combined_label,
            cutpoint_method=cutpoint_method,
            request_payload=payload,
            warnings=[],
        )
        db.add(job)
    db.commit()

    try:
        (
            samples,
            endpoint_by_patient,
            endpoint_option,
            selection_options,
        ) = selected_analysis_inputs(db, request, repository_context)
        endpoint_label = endpoint_option["label"]
        signature_request_a = analysis_request_for_signature_spec(request, request.signature_a)
        signature_request_b = analysis_request_for_signature_spec(request, request.signature_b)

        candidates, filter_warnings, sample_selection = filter_sample_candidates(
            samples,
            request.filters,
            endpoint_by_patient=endpoint_by_patient,
            endpoint=request.endpoint,
            endpoint_label=endpoint_label,
            **selection_options,
        )
        candidate_barcodes = {sample.barcode for sample in candidates}
        candidate_expression_a, _, _, _ = expression_for_request(
            db,
            signature_request_a,
            eligible_barcodes=candidate_barcodes,
            repository_context=repository_context,
        )
        candidate_expression_b, _, _, _ = expression_for_request(
            db,
            signature_request_b,
            eligible_barcodes=candidate_barcodes,
            repository_context=repository_context,
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
            repository_context=repository_context,
        )
        expression_b, signature_info_b, warnings_b, scoring_provenance_b = expression_for_request(
            db,
            signature_request_b,
            eligible_barcodes=eligible_barcodes,
            repository_context=repository_context,
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
        selected_expression_samples = set(expression_a) & set(expression_b)
        if repository_context is None:
            data_provenance = analysis_data_provenance(
                settings,
                cohort=request.cohort,
                expression_scale=request.expression_scale,
                selected_barcodes=selected_expression_samples,
            )
        else:
            layer = resolve_expression_layer(
                db, repository_context, request.expression_layer_id
            )
            data_provenance = repository_data_provenance(
                repository_context,
                layer,
                selected_sample_ids=selected_expression_samples,
            )
        analysis_data_dates = analysis_dataset_dates(
            db, repository_context
        )
        effective_expression_scale, effective_expression_label = (
            analysis_expression_metadata(db, request, repository_context)
        )
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
            expression_scale=effective_expression_scale,
            expression_scale_label=effective_expression_label,
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
        metrics["expression_scale"] = effective_expression_scale
        metrics["expression_scale_label"] = effective_expression_label
        metrics["endpoint_source"] = endpoint_option["source"]
        metrics["endpoint_qc"] = endpoint_option
        metrics["dataset"] = analysis_dataset_payload(
            repository_context,
            request.cohort,
        )
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


@app.post("/api/analyses/signature-panel", response_model=AnalysisOut)
def create_signature_panel_analysis(
    request_body: SignaturePanelAnalysisRequest,
    request: Request,
    db: SessionDep,
) -> AnalysisOut:
    result = _legacy_submit_and_wait(
        kind="signature_panel",
        payload=request_body.model_dump(mode="json"),
        request=request,
        db=db,
    )
    return AnalysisOut(**result)


def _create_signature_panel_analysis(
    request: SignaturePanelAnalysisRequest,
    db: Session,
) -> AnalysisOut:
    lock_key = stable_hash(
        {
            "kind": "signature_panel",
            "request": request.model_dump(mode="json"),
        }
    )
    with _compute_file_lock(lock_key):
        return _create_signature_panel_analysis_unlocked(request, db)


def _create_signature_panel_analysis_unlocked(
    request: SignaturePanelAnalysisRequest,
    db: Session,
) -> AnalysisOut:
    repository_context = repository_context_for_request(
        db, request, required_analysis="survival"
    )
    payload = request.model_dump(mode="json")
    payload["pipeline_version"] = SIGNATURE_PANEL_PIPELINE_VERSION
    payload["signature_scoring_contract"] = SIGNATURE_SCORING_CONTRACT_VERSION
    payload["sample_population_contract"] = SAMPLE_POPULATION_CONTRACT_VERSION
    payload["data_version"] = current_data_version(db)
    if repository_context is not None:
        payload[
            "user_data_version"
            if repository_context.dataset.visibility == "private"
            else "external_data_version"
        ] = repository_version_payload(repository_context)
    params_hash = stable_hash(payload)
    existing = db.scalar(
        select(AnalysisJob).where(AnalysisJob.params_hash == params_hash)
    )
    if (
        existing
        and existing.status == "completed"
        and _artifacts_exist(existing)
    ):
        existing.cached = True
        db.commit()
        return analysis_out(existing)

    cohort = db.get(Cohort, request.cohort)
    if repository_context is None and cohort is None:
        raise HTTPException(status_code=404, detail="Cohort not found.")

    signature_names = [
        normalized_signature_name(signature.name, f"Signature {index}")
        for index, signature in enumerate(request.signatures, start=1)
    ]
    panel_label = (
        request.panel_name
        or f"Signature panel ({len(request.signatures)})"
    )
    panel_label = panel_label[:128]
    cutpoint_method = "signature_panel_continuous"

    if existing:
        analysis_id = existing.id
        job = existing
        job.status = "running"
        job.cohort = request.cohort
        job.dataset_id = request.dataset_id
        job.dataset_release_id = request.dataset_release_id
        job.gene_symbol = panel_label
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
            dataset_id=request.dataset_id,
            dataset_release_id=request.dataset_release_id,
            gene_symbol=panel_label,
            cutpoint_method=cutpoint_method,
            request_payload=payload,
            warnings=[],
        )
        db.add(job)
    db.commit()

    try:
        (
            samples,
            endpoint_by_patient,
            endpoint_option,
            selection_options,
        ) = selected_analysis_inputs(db, request, repository_context)
        endpoint_label = endpoint_option["label"]
        signature_requests = [
            analysis_request_for_signature_spec(request, signature)
            for signature in request.signatures
        ]
        candidates, filter_warnings, sample_selection = (
            filter_sample_candidates(
                samples,
                request.filters,
                endpoint_by_patient=endpoint_by_patient,
                endpoint=request.endpoint,
                endpoint_label=endpoint_label,
                **selection_options,
            )
        )
        candidate_barcodes = {
            sample.barcode for sample in candidates
        }
        candidate_expressions = []
        for signature_request in signature_requests:
            expression, _, _, _ = expression_for_request(
                db,
                signature_request,
                eligible_barcodes=candidate_barcodes,
                repository_context=repository_context,
            )
            candidate_expressions.append(expression)
        common_candidate_barcodes = set(candidate_barcodes)
        for expression in candidate_expressions:
            common_candidate_barcodes &= set(expression)
        filtered, selection_warnings, sample_selection = (
            select_expression_complete_samples(
                candidates,
                common_candidate_barcodes,
                warnings=filter_warnings,
                summary=sample_selection,
            )
        )
        eligible_barcodes = {
            sample.barcode for sample in filtered
        }

        expressions: list[dict[str, float]] = []
        signature_info: list[dict] = []
        scoring_provenance: list[dict] = []
        signature_warnings: list[str] = []
        for index, (
            signature_request,
            signature_name,
        ) in enumerate(
            zip(
                signature_requests,
                signature_names,
                strict=True,
            ),
            start=1,
        ):
            (
                expression,
                info,
                warnings,
                provenance,
            ) = expression_for_request(
                db,
                signature_request,
                eligible_barcodes=eligible_barcodes,
                repository_context=repository_context,
            )
            expressions.append(expression)
            signature_info.append(
                {
                    **info,
                    "name": signature_name,
                    "column": f"signature_{index}",
                }
            )
            scoring_provenance.append(
                {
                    **provenance,
                    "name": signature_name,
                    "column": f"signature_{index}",
                }
            )
            signature_warnings.extend(
                prefixed_warnings(signature_name, warnings)
            )

        resolved_definitions = [
            (
                request.signatures[index].signature_method,
                tuple(
                    sorted(
                        (
                            str(gene.get("resolved_symbol") or ""),
                            (
                                float(
                                    gene.get("weight")
                                    if gene.get("weight") is not None
                                    else 1.0
                                )
                                if request.signatures[index].signature_method
                                in {"zscore", "weighted"}
                                else 1.0
                            ),
                        )
                        for gene in info.get("genes") or []
                    )
                ),
            )
            for index, info in enumerate(signature_info)
        ]
        if len(resolved_definitions) != len(
            set(resolved_definitions)
        ):
            raise ValueError(
                "Two panel signatures resolve to the same score definition."
            )

        standardized_scores, standardization = (
            standardize_signature_scores(
                filtered,
                expressions,
                signature_names,
            )
        )
        for info, standardization_item in zip(
            signature_info,
            standardization,
            strict=True,
        ):
            info["panel_standardization"] = standardization_item

        external_covariates = prepare_external_covariates(
            request.external_covariates,
            request.external_adjustment_covariates,
            cohort_patient_ids={
                sample.patient_id for sample in samples
            },
            analysis_patient_ids={
                sample.patient_id for sample in filtered
            },
        )
        warnings = (
            signature_warnings
            + selection_warnings
            + external_covariates.warnings
        )
        if request.filters.max_time_days is not None:
            warnings.append(
                "Patients with follow-up time exceeding "
                f"{request.filters.max_time_days:.0f} days are "
                "administratively censored at that time point (event = 0)."
            )
        records = build_signature_panel_records(
            filtered,
            standardized_scores,
            endpoint_by_patient=endpoint_by_patient,
            endpoint=request.endpoint,
            max_time_days=request.filters.max_time_days,
            external_covariates_by_patient=(
                external_covariates.values_by_patient
            ),
        )

        selected_expression_samples = {
            str(record["sample_barcode"])
            for record in records
        }
        if repository_context is None:
            data_provenance = analysis_data_provenance(
                settings,
                cohort=request.cohort,
                expression_scale=request.expression_scale,
                selected_barcodes=selected_expression_samples,
            )
        else:
            layer = resolve_expression_layer(
                db,
                repository_context,
                request.expression_layer_id,
            )
            data_provenance = repository_data_provenance(
                repository_context,
                layer,
                selected_sample_ids=selected_expression_samples,
            )
        analysis_data_dates = analysis_dataset_dates(
            db,
            repository_context,
        )
        effective_expression_scale, effective_expression_label = (
            analysis_expression_metadata(
                db,
                request,
                repository_context,
            )
        )
        r_payload = {
            **payload,
            "panel_name": panel_label,
            "signatures": signature_info,
            "external_covariates": {
                "definitions": external_covariates.definitions,
            },
        }
        metrics = run_signature_panel_r(
            settings=settings,
            analysis_id=analysis_id,
            payload=r_payload,
            records=records,
        )
        metrics["endpoint"] = request.endpoint
        metrics["endpoint_label"] = endpoint_label
        metrics["endpoint_source"] = endpoint_option["source"]
        metrics["endpoint_qc"] = endpoint_option
        metrics["expression_scale"] = effective_expression_scale
        metrics["expression_scale_label"] = (
            effective_expression_label
        )
        metrics["dataset"] = analysis_dataset_payload(
            repository_context,
            request.cohort,
        )
        metrics["signature"] = {
            "method": "panel",
            "label": panel_label,
            "signatures": signature_info,
        }
        metrics["signature_panel"] = {
            "schema_version": "tcga-trace-signature-panel-design-v1",
            "name": panel_label,
            "model_boundary": "continuous_main_effects_only",
            "effect_unit": "+1 within-panel score SD",
            "common_population": {
                "n_patients": len(records),
                "n_events": sum(
                    int(record["event"]) for record in records
                ),
                "rule": (
                    "intersection of patients with complete endpoint data "
                    "and every requested signature score"
                ),
            },
            "signatures": signature_info,
            "gene_overlap": signature_gene_overlap(
                signature_info
            ),
        }
        metrics["sample_selection"] = sample_selection
        metrics["data_provenance"] = data_provenance
        metrics["quality"] = {
            "n_patients": len(records),
            "n_events": sum(
                int(record["event"]) for record in records
            ),
            "score_complete": len(records),
            "constant_signatures": [
                item["name"]
                for item in standardization
                if not item["has_variation"]
            ],
        }
        artifacts = metrics.pop("artifact_paths")
        audit = write_signature_panel_audit(
            settings=settings,
            analysis_id=analysis_id,
            request_payload=payload,
            metrics=metrics,
            records=records,
            scoring_provenance={
                "schema_version": (
                    "tcga-trace-signature-panel-scoring-v1"
                ),
                "analysis_type": "signature_panel",
                "common_population": {
                    "barcodes": sorted(selected_expression_samples),
                    "n": len(selected_expression_samples),
                },
                "signatures": scoring_provenance,
                "final_score_standardization": standardization,
            },
            data_provenance=data_provenance,
            data_dates=analysis_data_dates,
            warnings=warnings + (metrics.get("warnings") or []),
        )
        metrics["audit_report"] = audit
        Path(artifacts["json"]).write_text(
            json.dumps(
                metrics,
                ensure_ascii=False,
                allow_nan=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        job.status = "completed"
        job.metrics = metrics
        job.warnings = warnings + (metrics.get("warnings") or [])
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
        code = (
            "R_FAILED"
            if "Rscript failed" in str(exc)
            else "ANALYSIS_FAILED"
        )
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
    from app.grouped_inference import batch_grouped_family

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
        grouped_family=batch_grouped_family(
            [item.model_dump(mode="json") for item in finalized],
            [analysis.cutpoint_method for analysis in request.analyses],
        ),
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
    if request.dataset_id:
        try:
            repository_context = resolve_repository_context(
                db,
                request.dataset_id,
                request.dataset_release_id,
                include_private=request.dataset_id.startswith("user-"),
            )
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        if repository_context.cohort != request.cohort:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Dataset {repository_context.dataset.id} belongs to "
                    f"{repository_context.cohort}, not {request.cohort}."
                ),
            )
        data_version = {
            **data_version,
            (
                "user_dataset"
                if repository_context.dataset.visibility == "private"
                else "external_repository"
            ): {
                "dataset_id": repository_context.dataset.id,
                "release_id": repository_context.release.id,
                "version": repository_context.release.version,
                "manifest_hash": repository_context.release.manifest_hash,
                "source_snapshot": repository_context.release.source_snapshot,
            },
        }
    identity = {
        "kind": "multiverse",
        "pipeline_version": MULTIVERSE_PIPELINE_VERSION,
        "sample_population_contract": SAMPLE_POPULATION_CONTRACT_VERSION,
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
    payload["signature_scoring_contract"] = SIGNATURE_SCORING_CONTRACT_VERSION
    payload["sample_population_contract"] = SAMPLE_POPULATION_CONTRACT_VERSION
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


def _create_hierarchical_pancancer(
    request: HierarchicalPanCancerRequest,
    db: Session,
) -> HierarchicalPanCancerOut:
    tcga_version = current_data_version(db)
    repository_version = hierarchical_repository_version(db, settings)
    identity = hierarchical_scan_identity(
        request,
        tcga_data_version=tcga_version,
        repository_version=repository_version,
    )
    scan_id = f"pch_{stable_hash(identity)[:24]}"
    lock_key = f"pancancer-hierarchical-{scan_id}"
    with _compute_file_lock(lock_key):
        result_path = hierarchical_result_path(settings, scan_id)
        if result_path.is_file():
            payload = json.loads(result_path.read_text(encoding="utf-8"))
            payload["cached"] = True
            payload["downloads"] = hierarchical_downloads(scan_id)
            return HierarchicalPanCancerOut(**payload)
        try:
            payload = run_hierarchical_pancancer_analysis(
                request,
                db,
                settings,
                scan_id=scan_id,
                tcga_data_version=tcga_version,
            )
        except GeneNotFoundError as exc:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "GENE_NOT_AVAILABLE",
                    "message": str(exc),
                },
            ) from exc
        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "HIERARCHICAL_PREFLIGHT_FAILED",
                    "message": str(exc),
                },
            ) from exc
        return HierarchicalPanCancerOut(**payload)


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
        "signature_scoring",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for row in result.get("results", []):
        csv_row = {field: row.get(field) for field in fieldnames}
        if isinstance(csv_row.get("signature_scoring"), dict):
            csv_row["signature_scoring"] = json.dumps(
                csv_row["signature_scoring"],
                ensure_ascii=False,
                sort_keys=True,
            )
        writer.writerow(csv_row)
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
def get_analysis(
    analysis_id: str,
    request: Request,
    db: SessionDep,
) -> AnalysisOut:
    _ensure_public_result_retained(
        db,
        analysis_id,
        {"analysis", "combined", "signature_panel"},
    )
    job = db.get(AnalysisJob, analysis_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Analysis not found.")
    _authorize_analysis_job_access(db, job, request)
    return analysis_out(job)


@app.get("/api/analyses/{analysis_id}/download/{kind}")
def download_analysis(
    analysis_id: str,
    kind: str,
    request: Request,
    db: SessionDep,
) -> Response:
    _ensure_public_result_retained(
        db,
        analysis_id,
        {"analysis", "combined", "signature_panel"},
    )
    job = db.get(AnalysisJob, analysis_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Analysis not found.")
    _authorize_analysis_job_access(db, job, request)
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
    cox_univariable_png_path = (
        settings.artifact_dir / analysis_id / "cox_univariable.png"
    )
    cox_univariable_svg_path = (
        settings.artifact_dir / analysis_id / "cox_univariable.svg"
    )
    cox_multivariable_png_path = (
        settings.artifact_dir / analysis_id / "cox_multivariable.png"
    )
    cox_multivariable_svg_path = (
        settings.artifact_dir / analysis_id / "cox_multivariable.svg"
    )
    continuous_effect_png_path = settings.artifact_dir / analysis_id / "continuous_effect.png"
    continuous_effect_svg_path = settings.artifact_dir / analysis_id / "continuous_effect.svg"
    cumulative_incidence_png_path = (
        settings.artifact_dir / analysis_id / "cumulative_incidence.png"
    )
    cumulative_incidence_svg_path = (
        settings.artifact_dir / analysis_id / "cumulative_incidence.svg"
    )
    signature_panel_joint_png_path = (
        settings.artifact_dir / analysis_id / "signature_panel_joint.png"
    )
    signature_panel_joint_svg_path = (
        settings.artifact_dir / analysis_id / "signature_panel_joint.svg"
    )
    signature_panel_adjusted_png_path = (
        settings.artifact_dir / analysis_id / "signature_panel_adjusted.png"
    )
    signature_panel_adjusted_svg_path = (
        settings.artifact_dir / analysis_id / "signature_panel_adjusted.svg"
    )
    model_results_csv_path = (
        settings.artifact_dir / analysis_id / "model_results.csv"
    )
    score_correlations_csv_path = (
        settings.artifact_dir / analysis_id / "score_correlations.csv"
    )
    continuous_csv_path = settings.artifact_dir / analysis_id / "continuous_data.csv"
    needs_svg_render = job.svg_path is None or not Path(job.svg_path).exists()
    if kind == "cox_svg" and not cox_forest_svg_path.exists():
        needs_svg_render = True
    if kind == "cox_univariable_svg" and not cox_univariable_svg_path.exists():
        needs_svg_render = True
    if kind == "cox_multivariable_svg" and not cox_multivariable_svg_path.exists():
        needs_svg_render = True
    if kind == "continuous_svg" and not continuous_effect_svg_path.exists():
        needs_svg_render = True
    if kind == "cumulative_incidence_svg" and not cumulative_incidence_svg_path.exists():
        needs_svg_render = True
    if (
        kind == "signature_panel_joint_svg"
        and not signature_panel_joint_svg_path.exists()
    ):
        needs_svg_render = True
    if (
        kind == "signature_panel_adjusted_svg"
        and not signature_panel_adjusted_svg_path.exists()
    ):
        needs_svg_render = True
    if kind in {
        "svg",
        "cox_svg",
        "cox_univariable_svg",
        "cox_multivariable_svg",
        "continuous_svg",
        "cumulative_incidence_svg",
        "signature_panel_joint_svg",
        "signature_panel_adjusted_svg",
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
        "cox_univariable_png": str(cox_univariable_png_path),
        "cox_univariable_svg": str(cox_univariable_svg_path),
        "cox_multivariable_png": str(cox_multivariable_png_path),
        "cox_multivariable_svg": str(cox_multivariable_svg_path),
        "continuous_png": str(continuous_effect_png_path),
        "continuous_svg": str(continuous_effect_svg_path),
        "cumulative_incidence_png": str(cumulative_incidence_png_path),
        "cumulative_incidence_svg": str(cumulative_incidence_svg_path),
        "signature_panel_joint_png": str(signature_panel_joint_png_path),
        "signature_panel_joint_svg": str(signature_panel_joint_svg_path),
        "signature_panel_adjusted_png": str(
            signature_panel_adjusted_png_path
        ),
        "signature_panel_adjusted_svg": str(
            signature_panel_adjusted_svg_path
        ),
        "model_results_csv": str(model_results_csv_path),
        "score_correlations_csv": str(score_correlations_csv_path),
        "continuous_csv": str(continuous_csv_path),
        "csv": job.csv_path,
        "json": job.json_path,
        "audit_json": str(audit_report_json_path(analysis_id)),
        "audit_html": str(audit_report_html_path(analysis_id)),
        "cohort_manifest": str(settings.artifact_dir / analysis_id / "cohort_manifest.csv"),
        "source_files": str(settings.artifact_dir / analysis_id / "source_files.csv"),
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
        "cox_univariable_png": "image/png",
        "cox_univariable_svg": "image/svg+xml",
        "cox_multivariable_png": "image/png",
        "cox_multivariable_svg": "image/svg+xml",
        "continuous_png": "image/png",
        "continuous_svg": "image/svg+xml",
        "cumulative_incidence_png": "image/png",
        "cumulative_incidence_svg": "image/svg+xml",
        "signature_panel_joint_png": "image/png",
        "signature_panel_joint_svg": "image/svg+xml",
        "signature_panel_adjusted_png": "image/png",
        "signature_panel_adjusted_svg": "image/svg+xml",
        "model_results_csv": "text/csv",
        "score_correlations_csv": "text/csv",
        "continuous_csv": "text/csv",
        "csv": "text/csv",
        "json": "application/json",
        "audit_json": "application/json",
        "audit_html": "text/html",
        "cohort_manifest": "text/csv",
        "source_files": "text/csv",
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
        "cox_univariable_png": f"{analysis_id}.cox_univariable.png",
        "cox_univariable_svg": f"{analysis_id}.cox_univariable.svg",
        "cox_multivariable_png": f"{analysis_id}.cox_multivariable.png",
        "cox_multivariable_svg": f"{analysis_id}.cox_multivariable.svg",
        "continuous_png": f"{analysis_id}.continuous_effect.png",
        "continuous_svg": f"{analysis_id}.continuous_effect.svg",
        "cumulative_incidence_png": f"{analysis_id}.cumulative_incidence.png",
        "cumulative_incidence_svg": f"{analysis_id}.cumulative_incidence.svg",
        "signature_panel_joint_png": (
            f"{analysis_id}.signature_panel_joint.png"
        ),
        "signature_panel_joint_svg": (
            f"{analysis_id}.signature_panel_joint.svg"
        ),
        "signature_panel_adjusted_png": (
            f"{analysis_id}.signature_panel_adjusted.png"
        ),
        "signature_panel_adjusted_svg": (
            f"{analysis_id}.signature_panel_adjusted.svg"
        ),
        "model_results_csv": f"{analysis_id}.model_results.csv",
        "score_correlations_csv": (
            f"{analysis_id}.score_correlations.csv"
        ),
        "continuous_csv": f"{analysis_id}.continuous_data.csv",
        "audit_json": f"{analysis_id}.audit_report.json",
        "audit_html": f"{analysis_id}.audit_report.html",
        "cohort_manifest": f"{analysis_id}.cohort_manifest.csv",
        "source_files": f"{analysis_id}.source_files.csv",
        "attestation": f"{analysis_id}.attestation_receipt.json",
        "r_script": f"{analysis_id}.rerun_analysis.R",
        "reproduction_manifest": f"{analysis_id}.reproduction_manifest.json",
    }.get(kind, f"{analysis_id}.{kind}")
    return FileResponse(path, media_type=media_type, filename=filename)


def analysis_zip_response(job: AnalysisJob, db: Session) -> Response:
    if job.status != "completed":
        raise HTTPException(status_code=404, detail="Analysis is not completed.")
    ensured_svg_path = str(ensure_svg_artifact(settings, job.id))
    if job.svg_path != ensured_svg_path:
        job.svg_path = ensured_svg_path
        db.commit()

    analysis_dir = settings.artifact_dir / job.id
    is_signature_panel = (
        job.cutpoint_method == "signature_panel_continuous"
    )
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
        ("input.json", str(analysis_dir / "input.json")),
        ("rerun_analysis.R", str(analysis_dir / "rerun_analysis.R")),
        (
            "clinical_covariates.R",
            str(analysis_dir / "clinical_covariates.R"),
        ),
        ("cox_diagnostics.R", str(analysis_dir / "cox_diagnostics.R")),
        ("renv.lock", str(analysis_dir / "renv.lock")),
        (
            "Dockerfile.reproduce",
            str(analysis_dir / "Dockerfile.reproduce"),
        ),
        ("REPRODUCE.md", str(analysis_dir / "REPRODUCE.md")),
        (
            "reproduction_manifest.json",
            str(analysis_dir / "reproduction_manifest.json"),
        ),
    ]
    if is_signature_panel:
        files.extend(
            [
                (
                    "expected_results.json",
                    str(analysis_dir / "expected_results.json"),
                ),
                (
                    "signature_panel.R",
                    str(analysis_dir / "signature_panel.R"),
                ),
            ]
        )
    else:
        files.extend([
            ("km_analysis.R", str(analysis_dir / "km_analysis.R")),
        (
            "competing_risks.R",
                str(analysis_dir / "competing_risks.R"),
        ),
        ])
    optional_files = [
        ("cohort_manifest.csv", str(analysis_dir / "cohort_manifest.csv")),
        ("source_files.csv", str(analysis_dir / "source_files.csv")),
        ("cox_forest.png", str(analysis_dir / "cox_forest.png")),
        ("cox_forest.svg", str(analysis_dir / "cox_forest.svg")),
        ("cox_univariable.png", str(analysis_dir / "cox_univariable.png")),
        ("cox_univariable.svg", str(analysis_dir / "cox_univariable.svg")),
        ("cox_multivariable.png", str(analysis_dir / "cox_multivariable.png")),
        ("cox_multivariable.svg", str(analysis_dir / "cox_multivariable.svg")),
        ("continuous_effect.png", str(analysis_dir / "continuous_effect.png")),
        ("continuous_effect.svg", str(analysis_dir / "continuous_effect.svg")),
        ("cumulative_incidence.png", str(analysis_dir / "cumulative_incidence.png")),
        ("cumulative_incidence.svg", str(analysis_dir / "cumulative_incidence.svg")),
        ("continuous_data.csv", str(analysis_dir / "continuous_data.csv")),
        ("signature_panel_joint.png", str(analysis_dir / "signature_panel_joint.png")),
        ("signature_panel_joint.svg", str(analysis_dir / "signature_panel_joint.svg")),
        ("signature_panel_adjusted.png", str(analysis_dir / "signature_panel_adjusted.png")),
        ("signature_panel_adjusted.svg", str(analysis_dir / "signature_panel_adjusted.svg")),
        ("model_results.csv", str(analysis_dir / "model_results.csv")),
        ("score_correlations.csv", str(analysis_dir / "score_correlations.csv")),
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
            expression, cohort_signature, gene_warnings, scoring_provenance = expression_for_request(
                db,
                analysis_request,
                eligible_barcodes={sample.barcode for sample in filtered},
            )
            if request.signature_method == "single":
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
                    "signature_scoring": (
                        compact_cohort_signature_scoring(
                            cohort=cohort.id,
                            signature=cohort_signature,
                            provenance=scoring_provenance,
                        )
                        if request.signature_method != "single"
                        else None
                    ),
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

    if request.signature_method != "single":
        signature_info = pancancer_signature_request_definition(request)

    result = {
        "scan_id": scan_id,
        "status": "completed",
        "cached": False,
        "gene_symbol": (signature_info or {}).get("label") or request.gene_symbol.strip().upper(),
        "signature": signature_info,
        "signature_scoring_scope": (
            {
                "scope": "cohort_specific",
                "cohort_contracts": sum(
                    bool(row.get("signature_scoring")) for row in rows
                ),
                "interpretation": (
                    "The requested signature is computed independently in each "
                    "cohort. Inspect each cohort contract for its resolved genes, "
                    "coverage, scoring population and, where applicable, frozen "
                    "expression universe; no first-cohort contract is presented "
                    "as global."
                ),
            }
            if request.signature_method != "single"
            else {"scope": "shared_request_definition"}
        ),
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


def pancancer_signature_request_definition(
    request: PanCancerSurvivalRequest,
) -> dict[str, Any]:
    """Describe the requested signature without borrowing cohort provenance."""

    genes = signature_entries(request)
    gene_labels = []
    for gene in genes:
        symbol = str(gene["gene_symbol"]).strip().upper()
        if request.signature_method in {"zscore", "weighted"}:
            gene_labels.append(f"{symbol}:{float(gene.get('weight', 1.0)):g}")
        else:
            gene_labels.append(
                ("-" if effective_direction(gene) == "down" else "")
                + symbol
            )
    return {
        "scope": "request_definition",
        "method": request.signature_method,
        "label": (
            f"{signature_method_label(request.signature_method)}("
            f"{', '.join(gene_labels)})"
        ),
        "genes": [
            {
                "query": str(gene["gene_symbol"]).strip().upper(),
                "weight": float(gene.get("weight", 1.0)),
                "direction": gene.get("direction"),
                "effective_direction": effective_direction(gene),
            }
            for gene in genes
        ],
        "cohort_specific_scoring": True,
    }


def compact_cohort_signature_scoring(
    *,
    cohort: str,
    signature: dict[str, Any],
    provenance: dict[str, Any],
) -> dict[str, Any]:
    """Keep the auditable scoring contract while excluding patient-level values."""

    coverage = provenance.get("coverage") or signature.get("coverage") or {}
    population = (
        provenance.get("scoring_population")
        or signature.get("scoring_population")
        or {}
    )
    scoring_parameters = dict(provenance.get("parameters") or {})
    if provenance.get("weight_denominator") is not None:
        scoring_parameters["weight_denominator"] = provenance[
            "weight_denominator"
        ]
    if signature.get("standardization"):
        scoring_parameters["gene_standardization"] = signature[
            "standardization"
        ]
    component_contracts = [
        {
            key: component.get(key)
            for key in (
                "query",
                "resolved_symbol",
                "weight",
                "direction",
                "effective_direction",
                "source_value_count",
                "selected_value_count",
                "selected_values_sha256",
                "standardization",
            )
            if key in component
        }
        for component in provenance.get("components") or []
    ]
    return {
        "scope": "cohort",
        "cohort": cohort,
        "schema_version": provenance.get("schema_version"),
        "contract_version": provenance.get("contract_version"),
        "method": signature.get("method") or provenance.get("method"),
        "label": signature.get("label"),
        "genes": signature.get("genes") or [],
        "coverage": {
            key: coverage.get(key)
            for key in (
                "requested_n",
                "mapped_n",
                "unique_resolved_n",
                "resolved_n",
                "missing_n",
                "fraction",
                "missing_queries",
                "duplicate_queries",
                "duplicate_resolutions",
                "fail_closed_on_missing",
                "up_n",
                "down_n",
            )
            if key in coverage
        },
        "direction": provenance.get("direction") or {},
        "scoring_parameters": scoring_parameters,
        "component_contracts": component_contracts,
        "gene_universe": provenance.get("gene_universe") or {},
        "engine": provenance.get("engine") or {},
        "scoring_population": {
            key: population.get(key)
            for key in (
                "timing",
                "rule",
                "canonical_barcode_count",
                "canonical_barcodes_sha256",
                "returned_barcode_count",
                "returned_barcodes_sha256",
                "aucell_tie_seeds_sha256",
                "eligible_barcode_count",
                "complete_case_barcode_count",
                "score_values_sha256",
                "component_value_hashes",
            )
            if key in population
        },
        "hashes": {
            "canonical_scores_sha256": provenance.get(
                "canonical_score_values_sha256"
            ),
            "returned_scores_sha256": provenance.get("score_values_sha256"),
            "cache_key_sha256": (provenance.get("cache") or {}).get(
                "key_sha256"
            ),
        },
    }


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
    elif request.signature_method == "zscore":
        common_unit = "not transportable"
        common_description = (
            "The z-score signature is standardized separately inside each "
            "cohort and has no common raw score unit."
        )
    else:
        common_unit = "not pooled across expression layers"
        common_description = (
            f"{request.signature_method} is scored within each release's "
            "frozen feature universe. Cohort effects are reported, but raw "
            "score units are not mixed across assays or feature universes."
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
            if request.signature_method == "zscore"
            else (
                f"{request.signature_method} scores use release-specific "
                "feature universes; within-cohort effects are reported and "
                "no common-raw-unit pooled estimate is produced."
            )
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
        cohort_ids = list(
            db.scalars(
                select(Cohort.id).where(Cohort.id.like("TCGA-%")).order_by(Cohort.id)
            ).all()
        )
    if request.index_cohort and request.index_cohort not in cohort_ids:
        cohort_ids.append(request.index_cohort)
    outside_reference = [cohort_id for cohort_id in cohort_ids if not cohort_id.startswith("TCGA-")]
    if outside_reference:
        raise HTTPException(
            status_code=400,
            detail="TCGA reference scans accept only TCGA cohorts; use hierarchical analysis for external studies.",
        )
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
    elif request.signature_method in RANK_BASED_METHODS:
        warnings.append(
            f"{request.signature_method} was computed once per cohort on its "
            "frozen canonical molecular population. Within-cohort effects are "
            "reported; raw scores are not pooled across differing feature universes."
        )
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


_PRIVATE_IMMUNE_PATH = object()


def public_immune_screen_payload(payload: dict) -> dict:
    public_payload = sanitize_immune_screen_paths(payload)
    if not isinstance(public_payload, dict):
        raise RuntimeError("Immune screen payload must be an object.")
    return publicize_download_links(public_payload)


def sanitize_immune_screen_paths(value):
    if isinstance(value, dict):
        cleaned = {}
        for key, item in value.items():
            if key in {"path", "paths"}:
                continue
            public_item = sanitize_immune_screen_paths(item)
            if public_item is not _PRIVATE_IMMUNE_PATH:
                cleaned[key] = public_item
        return cleaned
    if isinstance(value, list):
        cleaned = []
        for item in value:
            public_item = sanitize_immune_screen_paths(item)
            if public_item is not _PRIVATE_IMMUNE_PATH:
                cleaned.append(public_item)
        return cleaned
    if isinstance(value, str) and (
        value == "/app" or value.startswith("/app/")
    ):
        return _PRIVATE_IMMUNE_PATH
    return value


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
    return db.scalar(
        select(DataManifest)
        .where(
            DataManifest.source_id.in_(
                [TCGA_RNA_SOURCE_ID, TCGA_CDR_SOURCE_ID]
            )
        )
        .order_by(desc(DataManifest.created_at))
        .limit(1)
    )


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
    request: CombinedSignatureAnalysisRequest | SignaturePanelAnalysisRequest,
    signature: SignatureSpec,
) -> AnalysisRequest:
    return AnalysisRequest(
        cohort=request.cohort,
        dataset_id=request.dataset_id,
        dataset_release_id=request.dataset_release_id,
        expression_layer_id=request.expression_layer_id,
        gene_symbol=signature.gene_symbol,
        signature_method=signature.signature_method,
        signature_genes=signature.signature_genes,
        endpoint=request.endpoint,
        expression_scale=request.expression_scale,
        cutpoint_method="median",
        filters=request.filters,
        adjustment_covariates=request.adjustment_covariates,
        external_covariates=request.external_covariates,
        external_adjustment_covariates=(
            request.external_adjustment_covariates
        ),
        time_unit=request.time_unit,
        show_confidence_interval=getattr(
            request,
            "show_confidence_interval",
            True,
        ),
        show_risk_table=getattr(
            request,
            "show_risk_table",
            False,
        ),
        plot_style=request.plot_style,
    )


def normalized_signature_name(value: str | None, fallback: str) -> str:
    normalized = (value or "").strip()
    return normalized[:48] if normalized else fallback


def prefixed_warnings(prefix: str, warnings: list[str]) -> list[str]:
    return [f"{prefix}: {warning}" for warning in warnings]


def canonical_signature_scoring_population(
    db: Session,
    request: AnalysisRequest,
    matrix,
    repository_context: RepositoryContext | None,
) -> tuple[list[str], dict[str, Any], list[str]]:
    """Freeze scoring before endpoint and clinical-analysis restrictions."""

    population_filters = AnalysisFilters(
        # Molecular restrictions precede specimen deduplication. Only clinical
        # and endpoint restrictions are deferred until after rank scoring.
        sample_types=request.filters.sample_types,
        sample_population=(
            request.filters.sample_population
            if repository_context is None
            else None
        )
    )
    selected, summary, warnings = select_gsea_samples(
        dataset_samples(
            db,
            cohort=request.cohort,
            repository_context=repository_context,
        ),
        population_filters,
        matrix.sample_ids,
        analysis_context="signature scoring",
        selection_rule=(
            "external" if repository_context is not None else "tcga"
        ),
    )
    selected_ids = {str(sample.barcode) for sample in selected}
    ordered = [
        sample_id for sample_id in matrix.sample_ids if sample_id in selected_ids
    ]
    summary = {
        **summary,
        "timing": "before endpoint and clinical filters",
        "analysis_filters_applied": False,
        "declared_sample_population": request.filters.sample_population,
        "declared_sample_types": list(request.filters.sample_types),
    }
    return ordered, summary, warnings


def signature_scoring_cache_root(
    repository_context: RepositoryContext | None,
) -> Path:
    if (
        repository_context is not None
        and repository_context.dataset.visibility == "private"
    ):
        return (
            repository_release_storage_path(repository_context)
            / ".signature_scoring_cache"
        )
    return settings.derived_expression_dir / "signature_scoring"


def signature_scoring_dataset_identity(
    request: AnalysisRequest,
    repository_context: RepositoryContext | None,
) -> dict[str, Any]:
    if repository_context is None:
        return {
            "dataset_id": request.cohort,
            "release_id": None,
            "expression_layer_id": request.expression_layer_id
            or request.expression_scale,
            "sample_population": request.filters.sample_population,
        }
    return {
        "dataset_id": repository_context.dataset.id,
        "release_id": repository_context.release.id,
        "release_version": repository_context.release.version,
        "manifest_hash": repository_context.release.manifest_hash,
        "expression_layer_id": request.expression_layer_id,
        "visibility": repository_context.dataset.visibility,
    }


def expression_for_request(
    db: Session,
    request: AnalysisRequest,
    *,
    eligible_barcodes: set[str] | None = None,
    repository_context: RepositoryContext | None = None,
) -> tuple[dict[str, float], dict, list[str], dict]:
    entries = signature_entries(request)
    warnings: list[str] = []
    resolved_entries: list[dict] = []
    first_by_symbol: dict[str, dict[str, Any]] = {}
    mapping_records: list[dict[str, Any]] = []
    missing_queries: list[str] = []
    duplicate_queries: list[str] = []
    duplicate_resolutions: list[dict[str, str]] = []

    def register_resolution(
        entry: dict[str, Any],
        *,
        resolved_symbol: str,
        status: str,
        values: dict[str, float] | None = None,
    ) -> None:
        query = str(entry["gene_symbol"]).strip().upper()
        resolved_symbol = resolved_symbol.strip().upper()
        record = {
            "query": query,
            "resolved_symbol": resolved_symbol,
            "status": status,
            "weight": float(entry.get("weight", 1.0)),
            "direction": entry.get("direction"),
            "effective_direction": (
                effective_direction(entry)
                if request.signature_method in RANK_BASED_METHODS
                else None
            ),
        }
        mapping_records.append(record)
        prior = first_by_symbol.get(resolved_symbol)
        if prior is not None:
            if request.signature_method in RANK_BASED_METHODS:
                conflicts = (
                    prior["effective_direction"] != record["effective_direction"]
                )
            elif request.signature_method in {"zscore", "weighted"}:
                conflicts = not math.isclose(
                    float(prior["weight"]), float(record["weight"])
                )
            else:
                conflicts = False
            if conflicts:
                raise ValueError(
                    f"Gene {resolved_symbol} was specified more than once with "
                    "conflicting weights or directions."
                )
            if prior["query"] == query:
                duplicate_queries.append(query)
            else:
                duplicate_resolutions.append(
                    {
                        "query": query,
                        "resolved_symbol": resolved_symbol,
                        "first_query": str(prior["query"]),
                    }
                )
            warnings.append(
                f"Duplicate gene {resolved_symbol} was specified more than once "
                "and was collapsed to its first occurrence."
            )
            return
        first_by_symbol[resolved_symbol] = record
        resolved_entries.append(
            {
                **entry,
                "resolved_symbol": resolved_symbol,
                "status": status,
                **({"values": values} if values is not None else {}),
            }
        )

    if repository_context is None:
        for entry in entries:
            resolved = resolve_gene_symbol(
                db,
                settings.tcga_data_dir,
                request.cohort,
                entry["gene_symbol"],
            )
            warnings.extend(resolved["warnings"])
            if not resolved["resolved"]:
                missing_queries.append(entry["gene_symbol"])
                continue
            register_resolution(
                entry,
                resolved_symbol=resolved["resolved"],
                status=resolved["status"],
            )
    else:
        for entry in entries:
            try:
                values, _, gene = repository_gene_expression(
                    db,
                    repository_context,
                    entry["gene_symbol"],
                    request.expression_layer_id,
                )
            except GeneNotFoundError:
                missing_queries.append(entry["gene_symbol"])
                continue
            query = entry["gene_symbol"].strip().upper()
            resolved_symbol = gene.gene_symbol
            if query != resolved_symbol:
                warnings.append(
                    f"Gene alias {query} was resolved to {resolved_symbol}."
                )
            register_resolution(
                entry,
                resolved_symbol=resolved_symbol,
                status="exact" if query == resolved_symbol else "alias",
                values=values,
            )

    if missing_queries:
        dataset_label = (
            repository_context.dataset.id
            if repository_context is not None
            else request.cohort
        )
        raise GeneNotFoundError(
            "Signature scoring failed closed because the following requested "
            f"gene(s) were not found in {dataset_label}: "
            + ", ".join(sorted(set(missing_queries)))
            + "."
        )
    if not resolved_entries:
        raise GeneNotFoundError("No valid genes were provided.")
    if request.signature_method == "single" and len(resolved_entries) != 1:
        raise ValueError("Single-gene analysis requires exactly one resolved gene.")
    if request.signature_method != "single" and len(resolved_entries) < 2:
        raise ValueError(
            "Multi-gene signature scoring requires at least two distinct "
            "resolved genes; aliases or duplicates collapsed this request to "
            f"{len(resolved_entries)} feature."
        )

    resolution_summary = {
        "requested_n": len(entries),
        "mapped_n": len(mapping_records),
        "unique_resolved_n": len(resolved_entries),
        "resolved_n": len(resolved_entries),
        "missing_n": 0,
        "fraction": 1.0,
        "missing_queries": [],
        "duplicate_queries": sorted(set(duplicate_queries)),
        "duplicate_resolutions": duplicate_resolutions,
        "mapping": mapping_records,
    }

    values_by_gene = []
    for entry in resolved_entries:
        if repository_context is not None:
            loaded_entry = entry
        else:
            loaded_entry = {
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
        source_values = loaded_entry["values"]
        finite_values: dict[str, float] = {}
        nonfinite_count = 0
        for barcode, raw_value in source_values.items():
            value = float(raw_value)
            if math.isfinite(value):
                finite_values[str(barcode)] = value
            else:
                nonfinite_count += 1
        if nonfinite_count:
            warnings.append(
                f"{loaded_entry['resolved_symbol']} had {nonfinite_count} "
                "non-finite expression value(s); those samples were treated "
                "as expression-incomplete."
            )
        values_by_gene.append(
            {
                **loaded_entry,
                "values": finite_values,
                "source_value_count_before_nonfinite_exclusion": len(source_values),
                "nonfinite_value_count": nonfinite_count,
            }
        )

    if request.signature_method in RANK_BASED_METHODS:
        matrix = resolve_expression_matrix(
            db,
            settings,
            cohort=request.cohort,
            expression_scale=request.expression_scale,
            expression_layer_id=request.expression_layer_id,
            repository_context=repository_context,
        )
        (
            canonical_barcodes,
            canonical_population,
            canonical_warnings,
        ) = canonical_signature_scoring_population(
            db,
            request,
            matrix,
            repository_context,
        )
        canonical_scores, scoring_provenance, scoring_warnings = (
            run_rank_based_signature_score(
                matrix=matrix,
                canonical_sample_ids=canonical_barcodes,
                entries=values_by_gene,
                method=request.signature_method,
                cache_root=signature_scoring_cache_root(repository_context),
                dataset_identity=signature_scoring_dataset_identity(
                    request, repository_context
                ),
                resolution_summary=resolution_summary,
            )
        )
        selected_barcodes = set(canonical_scores)
        if eligible_barcodes is not None:
            selected_barcodes &= eligible_barcodes
        expression = {
            barcode: canonical_scores[barcode]
            for barcode in canonical_barcodes
            if barcode in selected_barcodes
        }
        if len(expression) < 10:
            raise ValueError(
                "The rank-based signature has fewer than 10 eligible patients "
                "after the analysis filters are applied."
            )
        component_provenance = []
        for gene in values_by_gene:
            selected_values = [
                {
                    "sample_barcode": barcode,
                    "expression_value": gene["values"][barcode],
                }
                for barcode in sorted(selected_barcodes)
                if barcode in gene["values"]
            ]
            component_provenance.append(
                {
                    "query": gene["gene_symbol"],
                    "resolved_symbol": gene["resolved_symbol"],
                    "weight": gene["weight"],
                    "direction": gene.get("direction"),
                    "effective_direction": effective_direction(gene),
                    "source_value_count": len(gene["values"]),
                    "selected_value_count": len(selected_values),
                    "selected_values_sha256": stable_hash(
                        {"values": selected_values}
                    ),
                    "selected_values": selected_values,
                }
            )
        score_values = [
            {"sample_barcode": barcode, "score": expression[barcode]}
            for barcode in sorted(expression)
        ]
        scoring_provenance.update(
            {
                "population_rule": scoring_provenance[
                    "scoring_population"
                ]["rule"],
                "eligible_barcode_count": (
                    len(eligible_barcodes)
                    if eligible_barcodes is not None
                    else len(canonical_barcodes)
                ),
                "complete_case_barcode_count": len(expression),
                "returned_barcode_count": len(expression),
                "components": component_provenance,
                "score_values_sha256": stable_hash(
                    {"values": score_values}
                ),
                "score_values": score_values,
            }
        )
        scoring_provenance["scoring_population"].update(
            {
                "canonical_selection": canonical_population,
                "returned_barcode_count": len(expression),
                "returned_barcodes_sha256": stable_hash(
                    sorted(expression)
                ),
            }
        )
        label = (
            f"{signature_method_label(request.signature_method)}("
            + ", ".join(
                (
                    "-" if effective_direction(gene) == "down" else ""
                )
                + gene["resolved_symbol"]
                for gene in values_by_gene
            )
            + ")"
        )
        return (
            expression,
            {
                "method": request.signature_method,
                "label": label,
                "genes": signature_gene_payload(
                    values_by_gene, method=request.signature_method
                ),
                "sample_overlap": len(expression),
                "coverage": scoring_provenance["coverage"],
                "scoring_parameters": scoring_provenance["parameters"],
                "gene_universe": scoring_provenance["gene_universe"],
                "engine": scoring_provenance["engine"],
                "scoring_population": scoring_provenance[
                    "scoring_population"
                ],
            },
            warnings + canonical_warnings + scoring_warnings,
            scoring_provenance,
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
        if len(set(expression.values())) == 1 and expression:
            warnings.append(
                f"{gene['resolved_symbol']} is constant across the selected "
                "analysis population."
            )
        scoring_provenance = build_scoring_provenance(
            request=request,
            values_by_gene=values_by_gene,
            selected_barcodes=selected_barcodes,
            expression=expression,
            standardization=[],
            eligible_barcode_count=len(eligible_barcodes) if eligible_barcodes is not None else None,
            resolution_summary=resolution_summary,
        )
        return expression, {
            "method": "single",
            "label": gene["resolved_symbol"],
            "genes": signature_gene_payload(
                values_by_gene, method=request.signature_method
            ),
            "coverage": resolution_summary,
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
    ordered_common_barcodes = sorted(common_barcodes)

    standardization: list[dict] = []
    if request.signature_method == "zscore":
        z_values = {}
        for gene in values_by_gene:
            vals = [
                gene["values"][barcode]
                for barcode in ordered_common_barcodes
            ]
            mean = sum(vals) / len(vals)
            variance = sum((value - mean) ** 2 for value in vals) / max(len(vals) - 1, 1)
            raw_sd = math.sqrt(variance)
            constant = raw_sd == 0.0
            scaling_sd = raw_sd or 1.0
            standardization.append(
                {
                    "resolved_symbol": gene["resolved_symbol"],
                    "center": mean,
                    "sample_standard_deviation": raw_sd,
                    "scaling_standard_deviation": scaling_sd,
                    "constant": constant,
                    "n": len(vals),
                }
            )
            if constant:
                warnings.append(
                    f"{gene['resolved_symbol']} is constant in the z-score "
                    "standardization population and contributes zero variation."
                )
            z_values[gene["resolved_symbol"]] = {
                barcode: (gene["values"][barcode] - mean) / scaling_sd
                for barcode in ordered_common_barcodes
            }
        expression = {}
        weight_total = sum(abs(gene["weight"]) for gene in values_by_gene) or 1.0
        for barcode in ordered_common_barcodes:
            expression[barcode] = sum(gene["weight"] * z_values[gene["resolved_symbol"]][barcode] for gene in values_by_gene) / weight_total
    else:
        expression = {}
        if request.signature_method == "weighted":
            weight_total = sum(abs(gene["weight"]) for gene in values_by_gene) or 1.0
            for barcode in ordered_common_barcodes:
                expression[barcode] = sum(gene["weight"] * gene["values"][barcode] for gene in values_by_gene) / weight_total
        else:
            for barcode in ordered_common_barcodes:
                expression[barcode] = sum(gene["values"][barcode] for gene in values_by_gene) / len(values_by_gene)

    label = (
        f"{signature_method_label(request.signature_method)}("
        f"{'+'.join(gene['resolved_symbol'] for gene in values_by_gene)})"
    )
    scoring_provenance = build_scoring_provenance(
        request=request,
        values_by_gene=values_by_gene,
        selected_barcodes=set(ordered_common_barcodes),
        expression=expression,
        standardization=standardization,
        eligible_barcode_count=len(eligible_barcodes) if eligible_barcodes is not None else None,
        resolution_summary=resolution_summary,
    )
    return expression, {
        "method": request.signature_method,
        "label": label,
        "genes": signature_gene_payload(
            values_by_gene, method=request.signature_method
        ),
        "coverage": resolution_summary,
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
    resolution_summary: dict[str, Any],
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
            "direction": gene.get("direction"),
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
        "schema_version": "tcga-trace-scoring-provenance-v2",
        "dataset_id": request.dataset_id or request.cohort,
        "dataset_release_id": request.dataset_release_id,
        "expression_layer_id": request.expression_layer_id,
        "method": "single" if len(values_by_gene) == 1 else request.signature_method,
        "population_rule": (
            "samples after user filters and endpoint completeness, followed by complete "
            "expression for the requested gene or every signature component, then "
            "one-expression-complete-sample-per-participant selection using the "
            "dataset's prespecified sample-priority rule"
        ),
        "eligible_barcode_count": eligible_barcode_count,
        "complete_case_barcode_count": len(ordered_barcodes),
        "weight_denominator": (
            (sum(abs(gene["weight"]) for gene in values_by_gene) or 1.0)
            if request.signature_method in {"zscore", "weighted"} and len(values_by_gene) > 1
            else len(values_by_gene)
        ),
        "coverage": resolution_summary,
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
            {
                "gene_symbol": item.gene_symbol.strip().upper(),
                "weight": float(item.weight),
                "direction": item.direction,
            }
            for item in request.signature_genes
            if item.gene_symbol.strip()
        ]
    raw = request.gene_symbol.replace(";", ",").replace("+", ",")
    tokens = [item.strip() for item in raw.split(",") if item.strip()]
    if not tokens:
        tokens = [request.gene_symbol.strip()]
    entries: list[dict[str, Any]] = []
    for token in tokens:
        symbol = token
        weight = 1.0
        direction = None
        if request.signature_method in RANK_BASED_METHODS and ":" in token:
            symbol, raw_direction = token.rsplit(":", 1)
            normalized_direction = raw_direction.strip().casefold()
            direction_aliases = {
                "up": "up",
                "down": "down",
                "1": "up",
                "1.0": "up",
                "-1": "down",
                "-1.0": "down",
            }
            if normalized_direction not in direction_aliases:
                raise ValueError(
                    "Rank-based gene strings use GENE:1 or GENE:-1 "
                    "(GENE:up and GENE:down are also accepted). "
                    "For richer signatures, submit signature_genes explicitly."
                )
            direction = direction_aliases[normalized_direction]
            weight = -1.0 if direction == "down" else 1.0
        elif request.signature_method in {"weighted", "zscore"} and ":" in token:
            symbol, raw_weight = token.rsplit(":", 1)
            try:
                weight = float(raw_weight.strip())
            except ValueError as exc:
                raise ValueError(
                    f"Signature gene {symbol.strip()} has an invalid weight."
                ) from exc
            if not math.isfinite(weight) or weight == 0:
                raise ValueError(
                    "Signature gene weights must be finite and non-zero."
                )
        elif ":" in token:
            raise ValueError(
                f"{request.signature_method} scoring does not accept weighted "
                "or directional gene tokens."
            )
        symbol = symbol.strip().upper()
        if not symbol:
            raise ValueError("Signature gene symbols cannot be empty.")
        entries.append(
            {
                "gene_symbol": symbol,
                "weight": weight,
                "direction": direction,
            }
        )
    return entries


def signature_gene_payload(
    values_by_gene: list[dict], *, method: str
) -> list[dict]:
    return [
        {
            "query": gene["gene_symbol"],
            "resolved_symbol": gene["resolved_symbol"],
            "weight": gene["weight"],
            "direction": gene.get("direction"),
            "effective_direction": (
                effective_direction(gene)
                if method in RANK_BASED_METHODS
                else None
            ),
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


def _create_gsea_analysis(
    request: GseaAnalysisRequest,
    db: Session,
) -> GseaAnalysisOut:
    collection = resolve_gene_set_collection(
        settings.gsea_gene_set_dir,
        request.gene_set_collection,
    )
    lock_key = stable_hash(
        {
            "kind": "gsea",
            "pipeline_version": GSEA_PIPELINE_VERSION,
            "sample_population_contract": SAMPLE_POPULATION_CONTRACT_VERSION,
            "signature_scoring_contract": SIGNATURE_SCORING_CONTRACT_VERSION,
            "gene_set_sha256": collection["sha256"],
            "request": request.model_dump(mode="json"),
        }
    )
    with _compute_file_lock(lock_key):
        return _create_gsea_analysis_unlocked(
            request,
            db,
            collection=collection,
        )


def _resolved_clinical_group_assignments(
    samples: list[Any],
    grouping: Any,
    *,
    cohort: str,
    repository_context: RepositoryContext | None,
) -> tuple[
    dict[str, str],
    dict[str, Any],
    list[str],
    dict[str, str | float | None],
]:
    variable = str(grouping.clinical_variable or "")
    definition, variable_values = resolve_clinical_grouping_variable(
        samples,
        variable,
        cohort=cohort,
        tcga_data_dir=(
            None
            if repository_context is not None
            else getattr(settings, "tcga_data_dir", None)
        ),
        tcga_cdr_path=(
            None
            if repository_context is not None
            else getattr(settings, "tcga_cdr_path", None)
        ),
        repository=repository_context is not None,
    )
    if definition.get("value_type") == "numeric":
        if grouping.group_a_values or grouping.group_b_values:
            raise ValueError(
                f"Numeric clinical variable {definition['label']} requires a "
                "numeric cutpoint, not categorical levels."
            )
    elif not grouping.group_a_values or not grouping.group_b_values:
        raise ValueError(
            f"Categorical clinical variable {definition['label']} requires "
            "at least one level in each group."
        )
    if definition.get("value_type") == "categorical":
        levels_by_value = {
            str(level["value"]).casefold(): level
            for level in definition.get("levels") or []
        }
        known_levels = set(levels_by_value)
        requested_levels = [
            *grouping.group_a_values,
            *grouping.group_b_values,
        ]
        unknown = sorted(
            {
                value
                for value in requested_levels
                if value.casefold() not in known_levels
            },
            key=str.casefold,
        )
        if unknown:
            raise ValueError(
                f"Clinical grouping contains levels not observed for "
                f"{definition['label']}: {', '.join(unknown)}."
            )
        unavailable = sorted(
            {
                value
                for value in requested_levels
                if not levels_by_value[value.casefold()].get(
                    "analysis_eligible", True
                )
            },
            key=str.casefold,
        )
        if unavailable:
            raise ValueError(
                "Clinical grouping contains levels with fewer than 5 patients: "
                f"{', '.join(unavailable)}."
            )
    assignments, details = clinical_group_assignments(
        samples,
        grouping,
        variable_values=variable_values,
        variable_definition=definition,
    )
    missing_values = sum(
        variable_values.get(str(sample.barcode)) is None
        for sample in samples
    )
    details["assignment_audit"] = {
        "patients_considered": len(samples),
        "patients_assigned": len(assignments),
        "missing_clinical_value": missing_values,
        "unselected_clinical_level": max(
            0,
            len(samples) - len(assignments) - missing_values,
        ),
    }
    warnings = [definition["analysis_note"]] if definition.get("analysis_note") else []
    return assignments, details, warnings, variable_values


def _create_gsea_analysis_unlocked(
    request: GseaAnalysisRequest,
    db: Session,
    *,
    collection: dict[str, Any],
) -> GseaAnalysisOut:
    repository_context = repository_context_for_request(
        db, request, required_analysis="gsea"
    )
    if repository_context is None and db.get(Cohort, request.cohort) is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "COHORT_NOT_FOUND", "message": "Cohort not found."},
        )

    matrix = resolve_expression_matrix(
        db,
        settings,
        cohort=request.cohort,
        expression_scale=request.expression_scale,
        expression_layer_id=request.expression_layer_id,
        repository_context=repository_context,
    )
    all_samples = dataset_samples(
        db,
        cohort=request.cohort,
        repository_context=repository_context,
    )
    warnings: list[str] = []
    grouping = request.grouping
    source_rows: list[dict[str, str]] = []
    clinical_variable_values: dict[str, str | float | None] | None = None

    if grouping.source == "survival":
        assignments, grouping_details, source_rows = (
            survival_group_assignments(
                db,
                cohort=request.cohort,
                dataset_id=request.dataset_id,
                dataset_release_id=request.dataset_release_id,
                grouping=grouping,
            )
        )
        matrix_sample_ids = set(matrix.sample_ids)
        selected_samples = [
            sample
            for sample in all_samples
            if sample.barcode in assignments
            and sample.barcode in matrix_sample_ids
        ]
        selected_barcodes = {
            sample.barcode for sample in selected_samples
        }
        inherited_assignment_count = len(assignments)
        assignments = {
            barcode: group
            for barcode, group in assignments.items()
            if barcode in selected_barcodes
        }
        selection_summary = {
            "selection_rule": (
                "Exact sample barcodes and two-group assignments were reused "
                "from the completed source survival analysis."
            ),
            "source_records": len(source_rows),
            "matched_current_matrix_samples": len(selected_samples),
            "filters_reapplied": False,
            "sample_population": grouping_details.get("sample_population"),
        }
        if inherited_assignment_count > len(assignments):
            warnings.append(
                f"{inherited_assignment_count - len(assignments)} inherited "
                "sample assignments were absent from the current release "
                "metadata or broad expression matrix and were excluded."
            )
        if grouping_details.get("group_a_label") == "Group A":
            grouping_details["group_a_label"] = grouping_details[
                "source_group_a"
            ]
        if grouping_details.get("group_b_label") == "Group B":
            grouping_details["group_b_label"] = grouping_details[
                "source_group_b"
            ]
    else:
        selected_samples, selection_summary, selection_warnings = (
            select_gsea_samples(
                all_samples,
                request.filters,
                matrix.sample_ids,
                selection_rule=(
                    "external" if repository_context is not None else "tcga"
                ),
                clinical_filter_cohort=request.cohort,
                clinical_filter_tcga_data_dir=getattr(
                    settings, "tcga_data_dir", None
                ),
                clinical_filter_tcga_cdr_path=getattr(
                    settings, "tcga_cdr_path", None
                ),
                clinical_filter_repository=repository_context is not None,
            )
        )
        warnings.extend(selection_warnings)
        if grouping.source == "clinical":
            (
                assignments,
                grouping_details,
                grouping_warnings,
                clinical_variable_values,
            ) = (
                _resolved_clinical_group_assignments(
                    selected_samples,
                    grouping,
                    cohort=request.cohort,
                    repository_context=repository_context,
                )
            )
            warnings.extend(grouping_warnings)
        else:
            signature = grouping.signature
            if signature is None:
                raise ValueError(
                    "Expression-derived GSEA grouping requires a signature."
                )
            signature_request = AnalysisRequest(
                cohort=request.cohort,
                dataset_id=request.dataset_id,
                dataset_release_id=request.dataset_release_id,
                expression_layer_id=request.expression_layer_id,
                gene_symbol=signature.gene_symbol,
                signature_method=signature.signature_method,
                signature_genes=signature.signature_genes,
                endpoint="OS",
                expression_scale=request.expression_scale,
                cutpoint_method="median",
                filters=request.filters,
                adjustment_covariates=[],
            )
            scores, signature_info, score_warnings, _ = expression_for_request(
                db,
                signature_request,
                eligible_barcodes={
                    sample.barcode for sample in selected_samples
                },
                repository_context=repository_context,
            )
            warnings.extend(score_warnings)
            assignments, grouping_details = expression_group_assignments(
                selected_samples,
                scores,
                grouping,
            )
            grouping_details["signature_resolved"] = signature_info
            if grouping_details.get("group_a_label") == "Group A":
                grouping_details["group_a_label"] = grouping_details[
                    "group_a_source_level"
                ]
            if grouping_details.get("group_b_label") == "Group B":
                grouping_details["group_b_label"] = grouping_details[
                    "group_b_source_level"
                ]

    counts = validate_group_assignments(
        assignments,
        available_sample_ids=matrix.sample_ids,
    )
    grouping_details["group_counts"] = {
        grouping_details["group_a_label"]: counts["a"],
        grouping_details["group_b_label"]: counts["b"],
    }
    grouping_details["positive_nes_favors"] = grouping_details[
        "group_b_label"
    ]
    grouping_details["negative_nes_favors"] = grouping_details[
        "group_a_label"
    ]
    if min(counts.values()) < 10:
        warnings.append(
            "At least one group contains fewer than 10 patients; pathway ranks may be unstable."
        )
    if grouping_details.get("circularity_notice"):
        warnings.append(grouping_details["circularity_notice"])

    independent_group_definition = (
        grouping_details.get("source") == "clinical"
        and not bool(grouping_details.get("expression_derived_grouping"))
    )
    inferential_role = (
        "associational"
        if independent_group_definition
        else "conditional_exploratory"
    )
    if not independent_group_definition:
        warnings.append(
            "The groups were derived from the tested transcriptome or from an "
            "expression-based source analysis. CAMERA p-values and FDR are "
            "conditional exploratory summaries, not independent confirmation."
        )

    compute_started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="trace-gsea-camera-") as temporary:
        camera_work_dir = Path(temporary)
        matrix_started = time.perf_counter()
        ranked_rows, ranking_details, camera_matrix = (
            prepare_camera_expression_matrix(
                matrix,
                assignments,
                ranking_metric=request.ranking_metric,
                camera_matrix_path=camera_work_dir / "expression.float32le.bin",
            )
        )
        ranking_details["matrix_preparation_seconds"] = (
            time.perf_counter() - matrix_started
        )
        if len(ranked_rows) < max(100, request.min_gene_set_size):
            raise ValueError(
                "Fewer than 100 complete-case variable genes could be ranked "
                "for correlation-aware pathway analysis."
            )
        pathways = read_gmt(Path(collection["file"]))
        effect_results, enrichment_details = run_preranked_effects(
            ranked_rows,
            pathways,
            min_size=request.min_gene_set_size,
            max_size=request.max_gene_set_size,
            permutations=request.permutations,
            seed=request.seed,
        )
        camera_results, camera_details = run_camera_gene_set_test(
            camera_matrix,
            gene_set_path=Path(collection["file"]),
            min_size=request.min_gene_set_size,
            max_size=request.max_gene_set_size,
            work_dir=camera_work_dir,
        )
        pathway_results, direction_details = (
            combine_camera_inference_with_preranked_effects(
                effect_results,
                camera_results,
            )
        )
    analysis_compute_wall_seconds = time.perf_counter() - compute_started
    if not pathway_results:
        raise ValueError(
            "No pathways overlap the ranked gene universe within the selected size limits."
        )

    ranking_payload = {
        **ranking_details,
        **enrichment_details,
        "permutations": request.permutations,
        "seed": request.seed,
        "top_positive_genes": [
            {
                "gene": row["gene"],
                "score": row["score"],
            }
            for row in ranked_rows[:10]
        ],
        "top_negative_genes": [
            {
                "gene": row["gene"],
                "score": row["score"],
            }
            for row in ranked_rows[-10:][::-1]
        ],
    }
    inference_payload = {
        **camera_details,
        **direction_details,
        "primary_method": "limma_camera",
        "hypothesis": "competitive_two_sided",
        "contrast": "group_b_minus_group_a",
        "inter_gene_correlation": "estimated_per_gene_set",
        "allow_negative_correlation": False,
        "trend_variance": True,
        "multiplicity": "Benjamini-Hochberg across all eligible pathways",
        "inferential_role": inferential_role,
        "independent_group_definition": independent_group_definition,
        "preranked_effect_role": "descriptive",
        "p_value_source": "limma CAMERA two-sided competitive test",
        "fdr_source": "BH adjustment of CAMERA p-values",
        "analysis_compute_wall_seconds": analysis_compute_wall_seconds,
    }
    summary_payload = gsea_summary(
        pathway_results,
        fdr_threshold=request.fdr_threshold,
        group_a_label=grouping_details["group_a_label"],
        group_b_label=grouping_details["group_b_label"],
    )
    summary_payload.update(
        {
            "inferential_role": inferential_role,
            "independent_group_definition": independent_group_definition,
            "evidence_method": "limma CAMERA with per-set estimated correlation",
            "effect_method": "weighted preranked NES and leading edge",
        }
    )
    gsea_id = f"gsea-{uuid.uuid4().hex}"
    downloads = {
        "csv": f"/api/v1/analyses/gsea/{gsea_id}/download/csv",
        "ranking_csv": (
            f"/api/v1/analyses/gsea/{gsea_id}/download/ranking_csv"
        ),
        "groups_csv": (
            f"/api/v1/analyses/gsea/{gsea_id}/download/groups_csv"
        ),
        "leading_edges_csv": (
            f"/api/v1/analyses/gsea/{gsea_id}/download/leading_edges_csv"
        ),
        "svg": f"/api/v1/analyses/gsea/{gsea_id}/download/svg",
        "dotplot_svg": (
            f"/api/v1/analyses/gsea/{gsea_id}/download/dotplot_svg"
        ),
        "json": f"/api/v1/analyses/gsea/{gsea_id}/download/json",
        "input": f"/api/v1/analyses/gsea/{gsea_id}/download/input",
        "gene_set_manifest": (
            f"/api/v1/analyses/gsea/{gsea_id}/download/gene_set_manifest"
        ),
        "methodology": (
            f"/api/v1/analyses/gsea/{gsea_id}/download/methodology"
        ),
        "camera_r_script": (
            f"/api/v1/analyses/gsea/{gsea_id}/download/camera_r_script"
        ),
        "audit_json": (
            f"/api/v1/analyses/gsea/{gsea_id}/download/audit_json"
        ),
        "attestation": (
            f"/api/v1/analyses/gsea/{gsea_id}/download/attestation"
        ),
        "zip": f"/api/v1/analyses/gsea/{gsea_id}/download/zip",
    }
    public_collection = {
        key: value
        for key, value in collection.items()
        if key != "file"
    }
    data_version = current_data_version(db)
    result_payload = {
        "schema_version": GSEA_RESULT_SCHEMA,
        "gsea_id": gsea_id,
        "status": "completed",
        "pipeline_version": GSEA_PIPELINE_VERSION,
        "sample_population_contract": SAMPLE_POPULATION_CONTRACT_VERSION,
        "signature_scoring_contract": SIGNATURE_SCORING_CONTRACT_VERSION,
        "cohort": request.cohort,
        "dataset_id": request.dataset_id,
        "dataset_release_id": request.dataset_release_id,
        "expression_scale": matrix.expression_scale,
        "expression_scale_label": matrix.expression_scale_label,
        "grouping": {
            **grouping_details,
            "sample_selection": selection_summary,
        },
        "gene_set_collection": public_collection,
        "ranking": ranking_payload,
        "inference": inference_payload,
        "summary": summary_payload,
        "pathways": pathway_results,
        "warnings": warnings,
        "downloads": downloads,
        "data_provenance": {
            "dataset": analysis_dataset_payload(
                repository_context,
                request.cohort,
            ),
            "data_version": data_version,
            "matrix_path_not_exported": True,
            "matrix_sha256": matrix.source_sha256,
        },
        "cached": False,
    }
    assignments_export = group_assignment_rows(
        selected_samples,
        assignments,
        grouping_details,
        clinical_values=clinical_variable_values,
    )
    artifact_dir = settings.artifact_dir / "gsea" / gsea_id
    try:
        _, audit = write_gsea_artifacts(
            artifact_dir,
            request_payload={
                **request.model_dump(mode="json"),
                "pipeline_version": GSEA_PIPELINE_VERSION,
                "signature_scoring_contract": SIGNATURE_SCORING_CONTRACT_VERSION,
                "gene_set_sha256": collection["sha256"],
                "matrix_sha256": matrix.source_sha256,
                "data_version": data_version,
            },
            result_payload=result_payload,
            ranked_rows=ranked_rows,
            assignment_rows=assignments_export,
            collection=collection,
            pipeline_version=GSEA_PIPELINE_VERSION,
        )
        write_attestation_receipt(
            settings,
            subject_type="preranked_gsea",
            subject_id=gsea_id,
            audit_path=artifact_dir / "audit_report.json",
            reproducibility_hash=audit["result_core_sha256"],
            report_schema_version=audit["schema_version"],
        )
    except Exception:
        shutil.rmtree(artifact_dir, ignore_errors=True)
        raise
    return GseaAnalysisOut(**{**result_payload, "audit": audit})


def _survival_grouping_gene_queries(job: AnalysisJob | None) -> list[str]:
    if job is None:
        return []
    payload = job.request_payload or {}
    signature_genes = payload.get("signature_genes") or []
    if signature_genes:
        return list(
            dict.fromkeys(
                str(item.get("gene_symbol") or "").strip().upper()
                for item in signature_genes
                if isinstance(item, dict)
                and str(item.get("gene_symbol") or "").strip()
            )
        )
    raw = str(payload.get("gene_symbol") or job.gene_symbol or "")
    return list(
        dict.fromkeys(
            item.strip().upper()
            for item in raw.replace(";", ",").replace("+", ",").split(",")
            if item.strip()
        )
    )


def _create_expression_comparison(
    request: ExpressionComparisonRequest,
    db: Session,
) -> ExpressionComparisonOut:
    lock_key = stable_hash(
        {
            "kind": "expression_comparison",
            "pipeline_version": EXPRESSION_COMPARISON_PIPELINE_VERSION,
            "sample_population_contract": SAMPLE_POPULATION_CONTRACT_VERSION,
            "signature_scoring_contract": SIGNATURE_SCORING_CONTRACT_VERSION,
            "request": request.model_dump(mode="json"),
            "data_version": current_data_version(db),
        }
    )
    with _compute_file_lock(lock_key):
        return _create_expression_comparison_unlocked(request, db)


def _create_expression_comparison_unlocked(
    request: ExpressionComparisonRequest,
    db: Session,
) -> ExpressionComparisonOut:
    repository_context = repository_context_for_request(
        db, request, required_analysis="expression_comparison"
    )
    if repository_context is None and db.get(Cohort, request.cohort) is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "COHORT_NOT_FOUND", "message": "Cohort not found."},
        )

    matrix = resolve_expression_matrix(
        db,
        settings,
        cohort=request.cohort,
        expression_scale=request.expression_scale,
        expression_layer_id=request.expression_layer_id,
        repository_context=repository_context,
    )
    all_samples = dataset_samples(
        db,
        cohort=request.cohort,
        repository_context=repository_context,
    )
    warnings: list[str] = []
    grouping = request.grouping
    source_job: AnalysisJob | None = None
    clinical_variable_values: dict[str, str | float | None] | None = None

    if grouping.source == "survival":
        assignments, grouping_details, source_rows = survival_group_assignments(
            db,
            cohort=request.cohort,
            dataset_id=request.dataset_id,
            dataset_release_id=request.dataset_release_id,
            grouping=grouping,
        )
        source_job = db.get(AnalysisJob, str(grouping.survival_analysis_id or ""))
        matrix_sample_ids = set(matrix.sample_ids)
        selected_samples = [
            sample
            for sample in all_samples
            if sample.barcode in assignments
            and sample.barcode in matrix_sample_ids
        ]
        selected_barcodes = {sample.barcode for sample in selected_samples}
        inherited_assignment_count = len(assignments)
        assignments = {
            barcode: group
            for barcode, group in assignments.items()
            if barcode in selected_barcodes
        }
        selection_summary = {
            "selection_rule": (
                "Exact sample barcodes and two-group assignments were reused "
                "from the completed source survival analysis."
            ),
            "source_records": len(source_rows),
            "matched_current_matrix_samples": len(selected_samples),
            "filters_reapplied": False,
            "sample_population": grouping_details.get("sample_population"),
        }
        if inherited_assignment_count > len(assignments):
            warnings.append(
                f"{inherited_assignment_count - len(assignments)} inherited "
                "sample assignments were absent from the current release "
                "metadata or expression matrix and were excluded."
            )
        if grouping_details.get("group_a_label") == "Group A":
            grouping_details["group_a_label"] = grouping_details["source_group_a"]
        if grouping_details.get("group_b_label") == "Group B":
            grouping_details["group_b_label"] = grouping_details["source_group_b"]
    else:
        selected_samples, selection_summary, selection_warnings = select_gsea_samples(
            all_samples,
            request.filters,
            matrix.sample_ids,
            analysis_context="expression",
            selection_rule=(
                "external" if repository_context is not None else "tcga"
            ),
            clinical_filter_cohort=request.cohort,
            clinical_filter_tcga_data_dir=getattr(
                settings, "tcga_data_dir", None
            ),
            clinical_filter_tcga_cdr_path=getattr(
                settings, "tcga_cdr_path", None
            ),
            clinical_filter_repository=repository_context is not None,
        )
        warnings.extend(
            warning.replace(
                "not applied to GSEA",
                "not applied to the expression comparison",
            )
            for warning in selection_warnings
        )
        if grouping.source == "clinical":
            (
                assignments,
                grouping_details,
                grouping_warnings,
                clinical_variable_values,
            ) = (
                _resolved_clinical_group_assignments(
                    selected_samples,
                    grouping,
                    cohort=request.cohort,
                    repository_context=repository_context,
                )
            )
            warnings.extend(grouping_warnings)
        else:
            signature = grouping.signature
            if signature is None:
                raise ValueError(
                    "Expression-derived grouping requires a gene or signature."
                )
            signature_request = AnalysisRequest(
                cohort=request.cohort,
                dataset_id=request.dataset_id,
                dataset_release_id=request.dataset_release_id,
                expression_layer_id=request.expression_layer_id,
                gene_symbol=signature.gene_symbol,
                signature_method=signature.signature_method,
                signature_genes=signature.signature_genes,
                endpoint="OS",
                expression_scale=request.expression_scale,
                cutpoint_method="median",
                filters=request.filters,
                adjustment_covariates=[],
            )
            scores, signature_info, score_warnings, _ = expression_for_request(
                db,
                signature_request,
                eligible_barcodes={sample.barcode for sample in selected_samples},
                repository_context=repository_context,
            )
            warnings.extend(score_warnings)
            assignments, grouping_details = expression_group_assignments(
                selected_samples,
                scores,
                grouping,
            )
            grouping_details["signature_resolved"] = signature_info
            if grouping_details.get("group_a_label") == "Group A":
                grouping_details["group_a_label"] = grouping_details[
                    "group_a_source_level"
                ]
            if grouping_details.get("group_b_label") == "Group B":
                grouping_details["group_b_label"] = grouping_details[
                    "group_b_source_level"
                ]

    try:
        counts = validate_group_assignments(
            assignments,
            available_sample_ids=matrix.sample_ids,
        )
    except ValueError as exc:
        message = str(exc)
        if message.startswith("GSEA requires at least"):
            message = message.replace(
                "GSEA requires at least",
                "Expression comparison requires at least",
                1,
            )
        raise ValueError(message) from exc
    group_a_label = str(grouping_details["group_a_label"])
    group_b_label = str(grouping_details["group_b_label"])
    grouping_details["group_counts"] = {
        group_a_label: counts["a"],
        group_b_label: counts["b"],
    }
    if min(counts.values()) < 10:
        warnings.append(
            "At least one group contains fewer than 10 patients; gene-level "
            "estimates may be unstable."
        )
    clinical_expression_derived = (
        grouping.source == "clinical"
        and bool(grouping_details.get("expression_derived_grouping"))
    )
    if clinical_expression_derived:
        grouping_details["circularity_notice"] = (
            "The selected clinical grouping was derived from transcriptomic "
            "expression profiles. All target-gene comparisons are descriptive "
            "and are not independent inferential tests."
        )
    elif grouping.source == "expression":
        grouping_details["circularity_notice"] = (
            "Groups were derived from the same expression matrix used for "
            "comparison. This expression comparison is exploratory and is "
            "not an independent inferential validation."
        )
    elif (
        grouping.source == "survival"
        and grouping_details.get("source_cutpoint_method") == "maxstat"
    ):
        grouping_details["circularity_notice"] = (
            "The inherited maxstat groups were optimized against a survival "
            "endpoint. This expression comparison is exploratory and "
            "outcome-informed."
        )
    if grouping_details.get("circularity_notice"):
        warnings.append(str(grouping_details["circularity_notice"]))

    resolver_warnings: list[str] = []

    def tcga_resolver(query: str) -> str | None:
        resolved = resolve_gene_symbol(
            db,
            settings.tcga_data_dir,
            request.cohort,
            query,
        )
        resolver_warnings.extend(resolved.get("warnings") or [])
        return resolved.get("resolved")

    resolved_genes, gene_warnings = resolve_expression_genes(
        matrix,
        request.genes,
        resolver=tcga_resolver if repository_context is None else None,
    )
    warnings.extend(resolver_warnings)
    warnings.extend(gene_warnings)

    grouping_gene_queries: list[str] = []
    if grouping.source == "expression":
        grouping_gene_queries = [
            str(item.get("resolved_symbol") or "").strip().upper()
            for item in (
                (grouping_details.get("signature_resolved") or {}).get("genes")
                or []
            )
            if str(item.get("resolved_symbol") or "").strip()
        ]
    elif grouping.source == "survival":
        grouping_gene_queries = _survival_grouping_gene_queries(source_job)

    grouping_symbols: set[str] = set()
    for grouping_query in grouping_gene_queries:
        try:
            resolved_component, component_warnings = resolve_expression_genes(
                matrix,
                [grouping_query],
                resolver=(
                    tcga_resolver if repository_context is None else None
                ),
            )
            grouping_symbols.update(
                str(item["gene_symbol"]) for item in resolved_component
            )
            warnings.extend(component_warnings)
        except ValueError:
            raw_symbol = grouping_query.strip().upper()
            if raw_symbol:
                grouping_symbols.add(
                    GENE_ALIASES.get(raw_symbol, raw_symbol)
                )

    gene_policies: dict[str, dict[str, Any]] = {}
    descriptive_only: list[str] = []
    for gene in resolved_genes:
        symbol = str(gene["gene_symbol"])
        if clinical_expression_derived:
            descriptive_only.append(symbol)
            gene_policies[symbol] = {
                "inferential_status": "descriptive_only",
                "included_in_multiplicity": False,
                "circularity_reason": (
                    "The clinical grouping was derived from transcriptomic "
                    "expression profiles."
                ),
            }
        elif symbol in grouping_symbols:
            descriptive_only.append(symbol)
            gene_policies[symbol] = {
                "inferential_status": "descriptive_only",
                "included_in_multiplicity": False,
                "circularity_reason": (
                    "The gene participated in defining the compared groups."
                ),
            }
        elif grouping.source == "expression" or (
            grouping.source == "survival"
            and grouping_details.get("source_cutpoint_method") == "maxstat"
        ):
            gene_policies[symbol] = {
                "inferential_status": "exploratory",
                "included_in_multiplicity": True,
                "circularity_reason": (
                    "The grouping is expression-derived or outcome-informed."
                ),
            }
        else:
            gene_policies[symbol] = {
                "inferential_status": "inferential",
                "included_in_multiplicity": True,
            }
    if clinical_expression_derived:
        warnings.append(
            "All analyzed target genes are descriptive-only and were excluded "
            "from both BH families because the clinical grouping itself was "
            "derived from transcriptomic expression."
        )
    elif descriptive_only:
        warnings.append(
            "Genes used to define their own groups are descriptive-only and "
            "were excluded from both BH families: "
            + ", ".join(descriptive_only)
            + "."
        )
    grouping_details["comparison_inference"] = {
        "grouping_genes": sorted(grouping_symbols),
        "descriptive_only_genes": descriptive_only,
        "expression_derived_clinical_grouping": clinical_expression_derived,
        "all_targets_descriptive_only": clinical_expression_derived,
        "bh_excludes_descriptive_only": True,
    }

    assignment_rows = group_assignment_rows(
        selected_samples,
        assignments,
        grouping_details,
        clinical_values=clinical_variable_values,
    )
    value_rows = extract_expression_value_rows(
        matrix,
        resolved_genes,
        assignments,
        selected_samples,
        group_a_label=group_a_label,
        group_b_label=group_b_label,
    )
    data_version = current_data_version(db)
    comparison_id = f"exprcmp-{uuid.uuid4().hex}"
    artifact_dir = (
        settings.artifact_dir / "expression_comparisons" / comparison_id
    )
    downloads = {
        kind: (
            f"/api/v1/analyses/expression-comparisons/{comparison_id}"
            f"/download/{kind}"
        )
        for kind in [
            "values_csv",
            "groups_csv",
            "statistics_csv",
            "violin_svg",
            "boxplot_svg",
            "heatmap_svg",
            "json",
            "input",
            "methodology",
            "audit_json",
            "attestation",
            "zip",
        ]
    }
    scientific_input = {
        "schema_version": "tcga-trace-expression-comparison-input-v1",
        "pipeline_version": EXPRESSION_COMPARISON_PIPELINE_VERSION,
        "sample_population_contract": SAMPLE_POPULATION_CONTRACT_VERSION,
        "signature_scoring_contract": SIGNATURE_SCORING_CONTRACT_VERSION,
        "request": request.model_dump(mode="json"),
        "genes_resolved": resolved_genes,
        "grouping_resolved": {
            **grouping_details,
            "sample_selection": selection_summary,
        },
        "matrix_sha256": matrix.source_sha256,
        "data_version": data_version,
    }
    try:
        engine_result = run_expression_comparison_engine(
            artifact_dir,
            request_payload=scientific_input,
            value_rows=value_rows,
            assignment_rows=assignment_rows,
            resolved_genes=resolved_genes,
            gene_policies=gene_policies,
            group_a_label=group_a_label,
            group_b_label=group_b_label,
            fdr_threshold=request.fdr_threshold,
            heatmap_max_samples=request.heatmap_max_samples,
            pipeline_version=EXPRESSION_COMPARISON_PIPELINE_VERSION,
        )
        statistics_payload = list(engine_result.get("statistics") or [])
        insufficient = [
            str(row.get("gene_symbol"))
            for row in statistics_payload
            if row.get("status") != "analyzed"
        ]
        if insufficient:
            warnings.append(
                "Fewer than five finite observations remained in at least one "
                "group for: " + ", ".join(insufficient) + "."
            )
        engine_summary = engine_result.get("summary") or {}
        summary_payload = {
            "genes_requested": len(request.genes),
            "genes_analyzed": int(engine_summary.get("genes_analyzed") or 0),
            "genes_at_fdr_welch": int(
                engine_summary.get("genes_at_fdr_welch") or 0
            ),
            "genes_at_fdr_mann_whitney": int(
                engine_summary.get("genes_at_fdr_mann_whitney") or 0
            ),
            "patients": counts["a"] + counts["b"],
            "group_counts": {
                group_a_label: counts["a"],
                group_b_label: counts["b"],
            },
            "fdr_threshold": request.fdr_threshold,
            "heatmap_samples": int(engine_summary.get("heatmap_samples") or 0),
        }
        result_payload = {
            "schema_version": EXPRESSION_COMPARISON_RESULT_SCHEMA,
            "comparison_id": comparison_id,
            "status": "completed",
            "pipeline_version": EXPRESSION_COMPARISON_PIPELINE_VERSION,
            "signature_scoring_contract": SIGNATURE_SCORING_CONTRACT_VERSION,
            "cohort": request.cohort,
            "dataset_id": request.dataset_id,
            "dataset_release_id": request.dataset_release_id,
            "expression_scale": matrix.expression_scale,
            "expression_scale_label": matrix.expression_scale_label,
            "grouping": {
                **grouping_details,
                "sample_selection": selection_summary,
            },
            "summary": summary_payload,
            "statistics": statistics_payload,
            "warnings": list(dict.fromkeys(warnings)),
            "downloads": downloads,
            "data_provenance": {
                "dataset": analysis_dataset_payload(
                    repository_context,
                    request.cohort,
                ),
                "data_version": data_version,
                "matrix_path_not_exported": True,
                "matrix_sha256": matrix.source_sha256,
                "statistical_engine": engine_result.get("engine") or {},
            },
            "cached": False,
        }
        audit = finalize_expression_comparison_artifacts(
            artifact_dir,
            request_payload=scientific_input,
            result_payload=result_payload,
            pipeline_version=EXPRESSION_COMPARISON_PIPELINE_VERSION,
        )
        write_attestation_receipt(
            settings,
            subject_type="expression_comparison",
            subject_id=comparison_id,
            audit_path=artifact_dir / "audit_report.json",
            reproducibility_hash=audit["result_core_sha256"],
            report_schema_version=audit["schema_version"],
        )
    except Exception:
        shutil.rmtree(artifact_dir, ignore_errors=True)
        raise
    return ExpressionComparisonOut(**{**result_payload, "audit": audit})


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


def biological_annotations(cohort: str | None, db: Session) -> dict:
    cohorts = (
        [cohort]
        if cohort
        else sorted(TCGA_ANNOTATION_FIELDS)
    )
    result: dict[str, Any] = {}
    for cohort_id in cohorts:
        samples = list(
            db.scalars(select(Sample).where(Sample.cohort == cohort_id)).all()
        )
        catalog, _ = clinical_grouping_context(
            samples,
            cohort=cohort_id,
            tcga_data_dir=settings.tcga_data_dir,
            tcga_cdr_path=settings.tcga_cdr_path,
        )
        annotations = [
            variable
            for variable in catalog
            if variable["category"] == "tumor_specific"
            and variable["non_missing_count"] > 0
        ]
        if not annotations:
            continue
        result[cohort_id] = {
            "available": any(
                variable["analysis_eligible"] for variable in annotations
            ),
            "catalog_version": annotations[0]["catalog_version"],
            "fields": [
                {
                    "name": variable["source_field"],
                    "label": variable["label"],
                    "non_missing_patients": variable["non_missing_count"],
                    "patient_count": variable["patient_count"],
                    "analysis_eligible": variable["analysis_eligible"],
                    "distribution": variable["levels"],
                }
                for variable in annotations
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
    analysis_dir = settings.artifact_dir / analysis_id
    if (analysis_dir / "signature_panel.R").is_file():
        return write_signature_panel_reproduction_capsule(
            analysis_dir,
            script_path=(
                Path(__file__).resolve().parents[1]
                / "scripts"
                / "signature_panel.R"
            ),
            renv_lock_path=(
                Path(__file__).resolve().parents[1] / "renv.lock"
            ),
        )
    return write_reproduction_capsule(
        analysis_dir,
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
        for kind in ("cohort_manifest", "source_files"):
            if (settings.artifact_dir / job.id / f"{kind}.csv").exists():
                downloads[kind] = f"/api/analyses/{job.id}/download/{kind}"
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
        if (settings.artifact_dir / job.id / "cox_univariable.png").exists():
            downloads["cox_univariable_png"] = (
                f"/api/analyses/{job.id}/download/cox_univariable_png"
            )
            downloads["cox_univariable_svg"] = (
                f"/api/analyses/{job.id}/download/cox_univariable_svg"
            )
        if (settings.artifact_dir / job.id / "cox_multivariable.png").exists():
            downloads["cox_multivariable_png"] = (
                f"/api/analyses/{job.id}/download/cox_multivariable_png"
            )
            downloads["cox_multivariable_svg"] = (
                f"/api/analyses/{job.id}/download/cox_multivariable_svg"
            )
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
        if (
            settings.artifact_dir
            / job.id
            / "signature_panel_joint.png"
        ).exists():
            downloads["signature_panel_joint_png"] = (
                f"/api/analyses/{job.id}/download/signature_panel_joint_png"
            )
            downloads["signature_panel_joint_svg"] = (
                f"/api/analyses/{job.id}/download/signature_panel_joint_svg"
            )
        if (
            settings.artifact_dir
            / job.id
            / "signature_panel_adjusted.png"
        ).exists():
            downloads["signature_panel_adjusted_png"] = (
                f"/api/analyses/{job.id}/download/signature_panel_adjusted_png"
            )
            downloads["signature_panel_adjusted_svg"] = (
                f"/api/analyses/{job.id}/download/signature_panel_adjusted_svg"
            )
        if (
            settings.artifact_dir / job.id / "model_results.csv"
        ).exists():
            downloads["model_results_csv"] = (
                f"/api/analyses/{job.id}/download/model_results_csv"
            )
        if (
            settings.artifact_dir / job.id / "score_correlations.csv"
        ).exists():
            downloads["score_correlations_csv"] = (
                f"/api/analyses/{job.id}/download/score_correlations_csv"
            )
    notices, diagnostics = build_analysis_diagnostics(job.warnings, job.metrics)
    payload_scale = job.request_payload.get("expression_scale", "log2_tpm")
    effective_scale = (
        job.request_payload.get("expression_layer_id")
        if job.dataset_id
        else payload_scale
    ) or payload_scale
    effective_label = (
        (job.metrics or {}).get("expression_scale_label")
        or (
            ((job.metrics or {}).get("data_provenance") or {})
            .get("expression_layer", {})
            .get("analysis_unit")
        )
        or expression_scale_label(payload_scale)
    )
    return AnalysisOut(
        id=job.id,
        status=job.status,
        cohort=job.cohort,
        dataset_id=job.dataset_id,
        dataset_release_id=job.dataset_release_id,
        gene_symbol=job.gene_symbol,
        expression_scale=effective_scale,
        expression_scale_label=effective_label,
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
    anonymous_client_key,
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
    supplied_request_id = request.headers.get("x-request-id", "").strip()
    request_id = (
        supplied_request_id
        if re.fullmatch(r"[A-Za-z0-9._-]{1,64}", supplied_request_id)
        else uuid.uuid4().hex
    )
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
    validation_errors = exc.errors()
    public_validation_errors = [
        {key: value for key, value in item.items() if key != "input"}
        for item in validation_errors
    ]

    def readable_error(item: dict[str, Any]) -> str:
        location = [
            str(part)
            for part in item.get("loc") or []
            if str(part) not in {"body", "query", "path", "request", "__root__"}
        ]
        field = next(
            (part for part in reversed(location) if not part.isdigit()),
            "analysis design",
        ).replace("_", " ")
        message = re.sub(
            r"^Value error,\s*",
            "",
            str(item.get("msg") or "Check this value."),
            flags=re.IGNORECASE,
        )
        return f"{field}: {message}"

    readable = [readable_error(item) for item in validation_errors[:3]]
    remaining = max(0, len(validation_errors) - len(readable))
    message = "Check the following request settings: " + "; ".join(readable)
    if remaining:
        message += f"; plus {remaining} more invalid setting{'s' if remaining != 1 else ''}"
    message += "."
    return JSONResponse(
        status_code=422,
        headers={"X-Request-ID": request.state.request_id},
        content={
            "error": {
                "code": "VALIDATION_ERROR",
                "message": message,
                "details": {
                    "errors": jsonable_encoder(public_validation_errors)
                },
                "request_id": request.state.request_id,
            }
        },
    )


@app.exception_handler(Exception)
async def public_unhandled_exception_handler(request: Request, exc: Exception):
    request_id = getattr(request.state, "request_id", uuid.uuid4().hex)
    logger.exception("Unhandled request failure [%s].", request_id)
    if not request.url.path.startswith(API_V1_PREFIX):
        return JSONResponse(
            status_code=500,
            headers={"X-Request-ID": request_id},
            content={"detail": "The request could not be completed."},
        )
    return JSONResponse(
        status_code=500,
        headers={"X-Request-ID": request_id},
        content={
            "error": {
                "code": "INTERNAL_ERROR",
                "message": (
                    "The request could not be completed. Use the request ID "
                    "when contacting the service operator."
                ),
                "details": {},
                "request_id": request_id,
            }
        },
    )


def _public_client_key(request: Request) -> str:
    # Browser and MCP identifiers are caller-controlled and can be rotated.
    # Public quotas are bound to the address normalized by the trusted edge.
    return f"rest-ip:{request_client_ip(request)}"


def _queue_http_error(exc: ComputeQueueError) -> HTTPException:
    headers = {"Retry-After": str(exc.retry_after)} if exc.retry_after else None
    return HTTPException(
        status_code=exc.status_code,
        detail={
            "code": exc.code,
            "message": exc.message,
            "details": exc.details,
        },
        headers=headers,
    )


_PUBLIC_JOB_CAPABILITY = {
    "analysis": "survival",
    "combined": "survival",
    "signature_panel": "survival",
    "multiverse": "survival",
    "gsea": "gsea",
    "expression_comparison": "expression_comparison",
}


def _candidate_record(dataset_id: str) -> dict | None:
    """Return a discovery record without treating it as a compute release."""
    try:
        registry = list_dataset_candidates()
    except (CandidateRegistryError, FileNotFoundError, OSError) as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "CANDIDATE_REGISTRY_UNAVAILABLE",
                "message": (
                    "Dataset eligibility records are temporarily unavailable."
                ),
            },
        ) from exc
    return next(
        (
            row
            for row in registry.get("candidates") or []
            if row.get("id") == dataset_id
        ),
        None,
    )


def _public_job_capability_requests(
    kind: str, payload: dict
) -> list[tuple[dict, str]]:
    if kind == "batch":
        return [
            (row, "survival")
            for row in payload.get("analyses") or []
            if isinstance(row, dict)
        ]
    capability = _PUBLIC_JOB_CAPABILITY.get(kind)
    return [(payload, capability)] if capability else []


def _payload_uses_rank_signature(payload: dict[str, Any]) -> bool:
    """Detect rank-scored signatures in every public compute request shape."""

    if str(payload.get("signature_method") or "").casefold() in RANK_BASED_METHODS:
        return True
    if any(
        str(method or "").casefold() in RANK_BASED_METHODS
        for method in payload.get("scoring_methods") or []
    ):
        return True
    for key in ("signature", "signature_a", "signature_b"):
        nested = payload.get(key)
        if isinstance(nested, dict) and _payload_uses_rank_signature(nested):
            return True
    grouping = payload.get("grouping")
    if isinstance(grouping, dict) and _payload_uses_rank_signature(grouping):
        return True
    return any(
        isinstance(item, dict) and _payload_uses_rank_signature(item)
        for item in payload.get("signatures") or []
    )


def _preflight_repository_capabilities(
    db: Session,
    *,
    kind: str,
    payload: dict,
) -> None:
    """Reject unsupported repository workflows before they enter the queue."""
    coverage_by_layer: dict[tuple[str, str, str], dict] = {}
    for request_payload, analysis_type in _public_job_capability_requests(
        kind, payload
    ):
        dataset_id = str(request_payload.get("dataset_id") or "").strip()
        if not dataset_id:
            continue
        try:
            context = resolve_repository_context(
                db,
                dataset_id,
                request_payload.get("dataset_release_id"),
                include_private=dataset_id.startswith("user-"),
            )
        except ValueError as exc:
            candidate = _candidate_record(dataset_id)
            if candidate is not None and candidate.get("status") != "promoted":
                raise HTTPException(
                    status_code=422,
                    detail={
                        "code": "DATASET_NOT_PROMOTED",
                        "message": (
                            "This cohort has been reviewed but is not a "
                            "compute-ready TRACE release."
                        ),
                        "details": {
                            "dataset_id": dataset_id,
                            "status": candidate.get("status"),
                            "requested_analysis": analysis_type,
                            "blockers": candidate.get("blockers") or [],
                        },
                    },
                ) from exc
            raise HTTPException(
                status_code=404,
                detail={
                    "code": "DATASET_NOT_FOUND",
                    "message": "The selected dataset release was not found.",
                    "details": {"dataset_id": dataset_id},
                },
            ) from exc

        required_capabilities = [analysis_type]
        if _payload_uses_rank_signature(request_payload):
            required_capabilities.append("rank_based_signature_scoring")
        expression_layer_id = str(
            request_payload.get("expression_layer_id") or ""
        ).strip() or None
        layer_coverage = None
        if expression_layer_id and context.dataset.visibility != "private":
            try:
                layer = resolve_expression_layer(db, context, expression_layer_id)
            except ValueError as exc:
                raise HTTPException(status_code=422, detail={
                    "code": "EXPRESSION_LAYER_UNAVAILABLE",
                    "message": "Choose an expression layer available in this dataset release.",
                    "details": {"dataset_id": dataset_id, "expression_layer_id": expression_layer_id},
                }) from exc
            try:
                coverage_key = (dataset_id, context.release.id, expression_layer_id)
                if coverage_key not in coverage_by_layer:
                    coverage_by_layer[coverage_key] = repository_expression_layer_coverage(db, context, layer)
                layer_coverage = coverage_by_layer[coverage_key]
            except (OSError, ValueError) as exc:
                raise HTTPException(status_code=503, detail={
                    "code": "DATASET_ARTIFACT_UNAVAILABLE",
                    "message": "The selected expression data could not be verified. Please try again later.",
                    "details": {"dataset_id": dataset_id, "expression_layer_id": expression_layer_id},
                }) from exc
        for required_analysis in required_capabilities:
            try:
                require_repository_capability(
                    context,
                    required_analysis,
                    expression_layer_id=expression_layer_id,
                    layer_coverage=layer_coverage,
                )
            except ValueError as exc:
                capabilities = repository_capabilities(
                    context,
                    expression_layer_id=expression_layer_id,
                    layer_coverage=layer_coverage,
                )
                available = available_repository_modules(capabilities)
                required = capabilities.get(required_analysis) or {}
                raise HTTPException(
                    status_code=422,
                    detail={
                        "code": "DATASET_CAPABILITY_UNAVAILABLE",
                        "message": str(
                            required.get("reason")
                            or "The selected dataset does not support this analysis."
                        ),
                        "details": {
                            "dataset_id": dataset_id,
                            "expression_layer_id": expression_layer_id,
                            "requested_analysis": required_analysis,
                            "available_analyses": available,
                            "gene_count": required.get("gene_count"),
                            "sample_count": required.get("sample_count"),
                            "matrix_entry_count": required.get(
                                "matrix_entry_count"
                            ),
                            "maximum_matrix_entries": required.get(
                                "maximum_matrix_entries"
                            ),
                            "missing_value_count": required.get(
                                "missing_value_count"
                            ),
                            "complete_matrix_verified": required.get(
                                "complete_matrix_verified"
                            ),
                        },
                    },
                ) from exc


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
        authorize_user_datasets_in_payload(
            db,
            payload,
            _private_dataset_access_token(request),
        )
        _preflight_repository_capabilities(
            db,
            kind=kind,
            payload=payload,
        )
        job = submit_compute_job(
            db,
            kind=kind,
            request_payload=payload,
            client_key=_public_client_key(request),
            settings=settings,
            cache_context=cache_context,
        )
    except UserDatasetError as exc:
        db.rollback()
        raise _user_dataset_http_error(exc) from exc
    except ComputeQueueError as exc:
        db.rollback()
        raise _queue_http_error(exc) from exc
    output = compute_job_out(job, settings)
    response.headers["Location"] = output.status_url
    response.headers["Retry-After"] = "2"
    return output


def _public_analysis(job: AnalysisJob) -> AnalysisOut:
    payload = publicize_download_links(analysis_out(job).model_dump(mode="json"))
    return AnalysisOut(**payload)


def _ensure_public_result_retained(db: Session, result_id: str, kinds: set[str]) -> None:
    if kinds.issubset(
        {"analysis", "combined", "signature_panel"}
    ):
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


def _authorize_compute_job_access(
    db: Session,
    job: ComputeJob,
    request: Request,
) -> None:
    try:
        authorize_user_datasets_in_payload(
            db,
            job.request_payload,
            _private_dataset_access_token(request),
        )
    except UserDatasetError as exc:
        raise _user_dataset_http_error(exc) from exc


def _authorize_analysis_job_access(
    db: Session,
    job: AnalysisJob,
    request: Request,
) -> None:
    if not (job.dataset_id or "").startswith("user-"):
        return
    try:
        authorize_user_dataset(
            db,
            str(job.dataset_id),
            _private_dataset_access_token(request),
        )
    except UserDatasetError as exc:
        raise _user_dataset_http_error(exc) from exc


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
            "Stable public API for exploratory transcriptomic survival and "
            "gene-set enrichment analysis across TCGA, curated independent "
            "cohorts and temporary private uploads. Use the health resource "
            "for live service and dataset readiness."
        ),
        links={
            "web_application": f"{base_url}/",
            "health": f"{base_url}/api/v1/health",
            "cancer_repository": f"{base_url}/api/v1/cancer-types",
            "external_datasets": f"{base_url}/api/v1/datasets",
            "reviewed_dataset_candidates": (
                f"{base_url}/api/v1/dataset-candidates"
            ),
            "user_dataset_template": (
                f"{base_url}/api/v1/user-datasets/template"
            ),
            "tutorial_assets": f"{base_url}/api/v1/tutorial-assets",
            "gsea_collections": f"{base_url}/api/v1/gsea/collections",
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
    repository_coverage = build_repository_coverage(db)
    return PublicHealthOut(
        status="ok" if cache_summary.get("status") == "ready" else "degraded",
        app_version=app.version,
        api_version="v1",
        release=application_release_identity(),
        pipeline_versions={
            "analysis": ANALYSIS_PIPELINE_VERSION,
            "combined_signatures": COMBINED_SIGNATURE_PIPELINE_VERSION,
            "signature_panel": SIGNATURE_PANEL_PIPELINE_VERSION,
            "gsea": GSEA_PIPELINE_VERSION,
            "expression_comparison": EXPRESSION_COMPARISON_PIPELINE_VERSION,
            "multiverse": MULTIVERSE_PIPELINE_VERSION,
            "pancancer": PANCANCER_PIPELINE_VERSION,
            "pancancer_hierarchical": HIERARCHICAL_PANCANCER_PIPELINE_VERSION,
            "exploratory_session": SESSION_HISTORY_PIPELINE_VERSION,
            "immune_atlas": IMMUNE_ATLAS_PIPELINE_VERSION,
            "clinical_grouping_catalog": CLINICAL_GROUPING_CATALOG_VERSION,
        },
        cohorts=cohort_count,
        external_repository={
            "status": (
                "ready"
                if settings.cancer_repository_dir.is_dir()
                else "storage_unavailable"
            ),
            "datasets": repository_coverage["datasets"],
            "patient_records_across_active_releases": repository_coverage[
                "patient_records_across_active_releases"
            ],
            "rna_samples_across_active_releases": repository_coverage[
                "rna_samples_across_active_releases"
            ],
            "represented_cancer_types": repository_coverage[
                "represented_cancer_types"
            ],
            "available_cancer_types": repository_coverage[
                "available_cancer_types"
            ],
            "total_cancer_types": repository_coverage[
                "total_cancer_types"
            ],
            "evidence_gaps": repository_coverage["evidence_gaps"],
            "search_in_progress": repository_coverage[
                "search_in_progress"
            ],
        },
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
def public_dataset_summary(
    db: SessionDep,
    cohort: str | None = None,
    include_data_sources: bool = True,
    include_data_sync: bool = True,
) -> dict:
    summary = build_dataset_summary(
        db,
        cohort,
        include_data_sources=include_data_sources,
        include_data_sync=include_data_sync,
    )
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
    "/cancer-types",
    tags=["External repository"],
    operation_id="listRepositoryCancerTypes",
)
def public_cancer_types(
    db: SessionDep,
    include_search: bool = True,
) -> dict:
    return build_repository_coverage(db, include_search=include_search)


@public_router.get(
    "/datasets",
    tags=["External repository"],
    operation_id="listRepositoryDatasets",
)
def public_datasets(
    db: SessionDep,
    cancer_code: str | None = None,
    analysis_type: str | None = None,
    include_metadata: bool = True,
) -> dict:
    try:
        datasets = list_repository_datasets(
            db,
            cancer_code=cancer_code,
            analysis_type=analysis_type,
            include_metadata=include_metadata,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "INVALID_ANALYSIS_TYPE",
                "message": str(exc),
            },
        ) from exc
    return {"datasets": datasets}


@public_router.get(
    "/dataset-candidates",
    tags=["External repository"],
    operation_id="listDatasetCandidates",
)
def public_dataset_candidates(
    disease_id: str | None = None,
    status: str | None = None,
    analysis_type: str | None = None,
    query: str | None = None,
) -> dict:
    return dataset_candidates(
        disease_id=disease_id,
        status=status,
        analysis_type=analysis_type,
        query=query,
    )


@public_router.get(
    "/datasets/{dataset_id}",
    tags=["External repository"],
    operation_id="getRepositoryDataset",
)
def public_dataset(dataset_id: str, db: SessionDep) -> dict:
    return get_dataset(dataset_id, db)


@public_router.get(
    "/datasets/{dataset_id}/endpoints",
    tags=["External repository"],
    operation_id="getRepositoryDatasetEndpoints",
)
def public_dataset_endpoints(
    dataset_id: str,
    db: SessionDep,
    release_id: str | None = None,
) -> dict:
    return get_dataset_endpoints(dataset_id, db, release_id)


@public_router.get(
    "/datasets/{dataset_id}/expression-layers",
    tags=["External repository"],
    operation_id="getRepositoryExpressionLayers",
)
def public_dataset_expression_layers(
    dataset_id: str,
    db: SessionDep,
    release_id: str | None = None,
) -> dict:
    return get_dataset_expression_layers(dataset_id, db, release_id)


@public_router.get(
    "/datasets/{dataset_id}/filters",
    response_model=FilterOptions,
    tags=["External repository"],
    operation_id="getRepositoryFilterOptions",
)
def public_dataset_filters(
    dataset_id: str,
    db: SessionDep,
    release_id: str | None = None,
) -> FilterOptions:
    return get_dataset_filters(dataset_id, db, release_id)


@public_router.get(
    "/datasets/{dataset_id}/genes",
    response_model=GeneSearchOut,
    tags=["External repository"],
    operation_id="searchRepositoryGenes",
)
def public_dataset_genes(
    dataset_id: str,
    db: SessionDep,
    query: str = "",
    limit: int = 25,
    release_id: str | None = None,
    expression_layer_id: str | None = None,
) -> GeneSearchOut:
    if limit < 1 or limit > 100:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "INVALID_LIMIT",
                "message": "limit must be between 1 and 100.",
            },
        )
    return search_dataset_genes(
        dataset_id,
        db,
        query,
        limit,
        release_id,
        expression_layer_id,
    )


@public_router.get(
    "/datasets/{dataset_id}/genes/resolve",
    tags=["External repository"],
    operation_id="resolveRepositoryGene",
)
def public_resolve_dataset_gene(
    dataset_id: str,
    db: SessionDep,
    query: str,
    release_id: str | None = None,
    expression_layer_id: str | None = None,
) -> dict:
    return resolve_dataset_gene(
        dataset_id,
        db,
        query,
        release_id,
        expression_layer_id,
    )


@public_router.get(
    "/datasets/{dataset_id}/download/{kind}",
    tags=["External repository"],
    operation_id="downloadRepositoryResource",
)
def public_download_dataset_resource(
    dataset_id: str,
    kind: str,
    db: SessionDep,
    release_id: str | None = None,
    expression_layer_id: str | None = None,
) -> Response:
    return download_dataset_resource(
        dataset_id,
        kind,
        db,
        release_id,
        expression_layer_id,
    )


def _user_dataset_http_error(exc: UserDatasetError) -> HTTPException:
    status_code = {
        "USER_DATASET_NOT_FOUND": 404,
        "USER_DATASET_EXPIRED": 410,
        "USER_DATASET_IN_USE": 409,
        "USER_DATASET_LIMIT": 429,
    }.get(exc.code, 422)
    return HTTPException(
        status_code=status_code,
        detail={
            "code": exc.code,
            "message": exc.message,
            "details": exc.as_details(),
        },
    )


def _private_repository_context(
    db: Session,
    dataset_id: str,
    request: Request,
    release_id: str | None = None,
) -> RepositoryContext:
    try:
        authorize_user_dataset(
            db,
            dataset_id,
            _private_dataset_access_token(request),
        )
        get_user_dataset(db, dataset_id)
        context = resolve_repository_context(
            db,
            dataset_id,
            release_id,
            include_private=True,
        )
    except UserDatasetError as exc:
        raise _user_dataset_http_error(exc) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "USER_DATASET_NOT_FOUND",
                "message": str(exc),
            },
        ) from exc
    if context.dataset.visibility != "private":
        raise HTTPException(
            status_code=404,
            detail={
                "code": "USER_DATASET_NOT_FOUND",
                "message": "The private dataset was not found.",
            },
        )
    return context


@public_router.get(
    "/user-datasets/template",
    tags=["User data"],
    operation_id="downloadUserDatasetTemplate",
    response_class=Response,
)
def public_user_dataset_template() -> Response:
    sample_count = 18
    expression = io.StringIO()
    expression_writer = csv.writer(expression)
    expression_writer.writerow(
        ["gene_symbol", *[f"S{index:02d}" for index in range(1, sample_count + 1)]]
    )
    expression_writer.writerow(
        ["TP53", *[f"{2.0 + index * 0.15:.2f}" for index in range(sample_count)]]
    )
    expression_writer.writerow(
        ["MKI67", *[f"{4.1 + index * 0.08:.2f}" for index in range(sample_count)]]
    )
    expression_writer.writerow(
        ["BAX", *[f"{3.7 - index * 0.05:.2f}" for index in range(sample_count)]]
    )
    clinical = io.StringIO()
    clinical_writer = csv.writer(clinical)
    clinical_writer.writerow(
        ["sample_id", "breast_subtype", "os_months", "os_status", "age", "stage", "grade"]
    )
    subtypes = ["Luminal A", "Luminal B", "Basal-like"]
    for index in range(1, sample_count + 1):
        clinical_writer.writerow(
            [
                f"S{index:02d}",
                subtypes[(index - 1) // 6],
                8 + index * 4,
                "event" if index % 2 == 0 else "censored",
                45 + index,
                f"Stage {1 + (index % 4)}",
                f"G{1 + (index % 3)}",
            ]
        )
    readme = (
        "TRACE user dataset template\n\n"
        "expression.csv uses genes in rows and samples in columns.\n"
        "clinical.csv contains one row per matching patient and demonstrates a three-level subtype variable.\n"
        "There are 18 synthetic patients, six per subtype, so any two subtypes meet the minimum group size.\n"
        "Choose Breast Invasive Carcinoma (BRCA) as the cancer context.\n"
        "To use the subtypes, add breast_subtype as a categorical custom variable with Baseline timing.\n"
        "The survival columns demonstrate the optional time-to-event mapping; they may be omitted when no outcome is available.\n"
        "The example values are synthetic and use normalized log-scale expression.\n"
        "For this template, choose 'Other normalized log scale' during mapping.\n"
        "These values demonstrate the upload workflow, not biological evidence. The three-gene matrix is too small for GSEA.\n"
        "Upload only de-identified research data.\n"
    )
    archive = io.BytesIO()
    with zipfile.ZipFile(
        archive,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
    ) as bundle:
        bundle.writestr("expression.csv", expression.getvalue())
        bundle.writestr("clinical.csv", clinical.getvalue())
        bundle.writestr("README.txt", readme)
    return Response(
        content=archive.getvalue(),
        media_type="application/zip",
        headers={
            "Content-Disposition": (
                'attachment; filename="trace-user-dataset-template.zip"'
            )
        },
    )


@public_router.post(
    "/user-datasets",
    response_model=UserDatasetCreatedOut,
    status_code=status.HTTP_201_CREATED,
    tags=["User data"],
    operation_id="createUserDataset",
)
def public_create_user_dataset(
    request: Request,
    db: SessionDep,
    expression_file: Annotated[UploadFile, File()],
    clinical_file: Annotated[UploadFile, File()],
    mapping_json: Annotated[str, Form(alias="mapping")],
) -> UserDatasetCreatedOut:
    try:
        mapping = UserDatasetMapping.model_validate_json(mapping_json)
    except ValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "INVALID_USER_DATASET_MAPPING",
                "message": "The selected upload mapping is incomplete or invalid.",
                "details": {"errors": jsonable_encoder(exc.errors())},
            },
        ) from exc
    try:
        access_token = secrets.token_urlsafe(32)
        result = create_user_dataset(
            db,
            settings,
            expression_source=expression_file.file,
            clinical_source=clinical_file.file,
            mapping=mapping,
            owner_key_hash=anonymous_client_key(
                _public_client_key(request)
            ),
            access_token_hash=user_dataset_access_token_hash(access_token),
        )
        return UserDatasetCreatedOut(
            **result,
            access_token=access_token,
        )
    except UserDatasetError as exc:
        raise _user_dataset_http_error(exc) from exc
    except (UnicodeDecodeError, csv.Error) as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "INVALID_TABLE_ENCODING",
                "message": (
                    "Expression and patient-metadata files must be UTF-8 CSV or TSV tables."
                ),
            },
        ) from exc
    finally:
        expression_file.file.close()
        clinical_file.file.close()


@public_router.get(
    "/user-datasets/{dataset_id}",
    response_model=UserDatasetOut,
    tags=["User data"],
    operation_id="getUserDataset",
)
def public_user_dataset(
    dataset_id: str,
    request: Request,
    db: SessionDep,
) -> UserDatasetOut:
    try:
        authorize_user_dataset(
            db,
            dataset_id,
            _private_dataset_access_token(request),
        )
        return UserDatasetOut(**get_user_dataset(db, dataset_id))
    except UserDatasetError as exc:
        raise _user_dataset_http_error(exc) from exc


@public_router.delete(
    "/user-datasets/{dataset_id}",
    tags=["User data"],
    operation_id="deleteUserDataset",
)
def public_delete_user_dataset(
    dataset_id: str,
    request: Request,
    db: SessionDep,
) -> dict:
    try:
        authorize_user_dataset(
            db,
            dataset_id,
            _private_dataset_access_token(request),
        )
        return delete_user_dataset(db, settings, dataset_id)
    except UserDatasetError as exc:
        raise _user_dataset_http_error(exc) from exc


@public_router.get(
    "/user-datasets/{dataset_id}/endpoints",
    tags=["User data"],
    operation_id="getUserDatasetEndpoints",
)
def public_user_dataset_endpoints(
    dataset_id: str,
    request: Request,
    db: SessionDep,
    release_id: str | None = None,
) -> dict:
    context = _private_repository_context(db, dataset_id, request, release_id)
    return {
        "dataset_id": dataset_id,
        "release_id": context.release.id,
        "endpoints": repository_endpoint_options(db, context),
    }


@public_router.get(
    "/user-datasets/{dataset_id}/expression-layers",
    tags=["User data"],
    operation_id="getUserDatasetExpressionLayers",
)
def public_user_dataset_expression_layers(
    dataset_id: str,
    request: Request,
    db: SessionDep,
    release_id: str | None = None,
) -> dict:
    context = _private_repository_context(db, dataset_id, request, release_id)
    return {
        "dataset_id": dataset_id,
        "release_id": context.release.id,
        "expression_layers": repository_expression_layers(db, context),
    }


@public_router.get(
    "/user-datasets/{dataset_id}/filters",
    response_model=FilterOptions,
    tags=["User data"],
    operation_id="getUserDatasetFilterOptions",
)
def public_user_dataset_filters(
    dataset_id: str,
    request: Request,
    db: SessionDep,
    release_id: str | None = None,
) -> FilterOptions:
    context = _private_repository_context(db, dataset_id, request, release_id)
    return FilterOptions(**repository_filter_options(db, context))


@public_router.get(
    "/user-datasets/{dataset_id}/genes",
    response_model=GeneSearchOut,
    tags=["User data"],
    operation_id="searchUserDatasetGenes",
)
def public_user_dataset_genes(
    dataset_id: str,
    request: Request,
    db: SessionDep,
    query: str = "",
    limit: int = 25,
    release_id: str | None = None,
    expression_layer_id: str | None = None,
) -> GeneSearchOut:
    if limit < 1 or limit > 100:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "INVALID_LIMIT",
                "message": "limit must be between 1 and 100.",
            },
        )
    context = _private_repository_context(db, dataset_id, request, release_id)
    genes = search_repository_genes(
        db,
        context,
        query,
        layer_id=expression_layer_id,
        limit=limit,
    )
    return GeneSearchOut(cohort=context.cohort, query=query, genes=genes)


@public_router.get(
    "/user-datasets/{dataset_id}/genes/resolve",
    tags=["User data"],
    operation_id="resolveUserDatasetGene",
)
def public_resolve_user_dataset_gene(
    dataset_id: str,
    request: Request,
    db: SessionDep,
    query: str,
    release_id: str | None = None,
    expression_layer_id: str | None = None,
) -> dict:
    context = _private_repository_context(db, dataset_id, request, release_id)
    try:
        _, _, gene = repository_gene_expression(
            db,
            context,
            query,
            expression_layer_id,
        )
    except GeneNotFoundError as exc:
        return {
            "query": query.strip().upper(),
            "resolved": None,
            "status": "not_found",
            "warnings": [str(exc)],
        }
    normalized = query.strip().upper()
    return {
        "query": normalized,
        "resolved": gene.gene_symbol,
        "status": (
            "exact" if normalized == gene.gene_symbol else "alias"
        ),
        "warnings": [],
    }


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
    "/tutorial-assets",
    tags=["Tutorials"],
    operation_id="listTutorialAssets",
    summary="List versioned synthetic tutorial datasets",
)
def list_public_tutorial_assets(response: Response) -> dict:
    response.headers["Cache-Control"] = "public, max-age=3600"
    return tutorial_asset_catalog()


@public_router.get(
    "/tutorial-assets/{asset_id}",
    tags=["Tutorials"],
    operation_id="downloadTutorialAsset",
    summary="Download one deterministic synthetic tutorial dataset",
    response_class=Response,
)
def download_public_tutorial_asset(asset_id: str) -> Response:
    try:
        content, filename = build_tutorial_asset(asset_id)
    except TutorialAssetNotFound as exc:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "TUTORIAL_ASSET_NOT_FOUND",
                "message": "The requested tutorial asset is not available.",
            },
        ) from exc
    digest = hashlib.sha256(content).hexdigest()
    return Response(
        content=content,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "public, max-age=86400, immutable",
            "ETag": f'"sha256-{digest}"',
            "X-Content-SHA256": digest,
        },
    )


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
def public_cohort_filters(
    cohort_id: str,
    db: SessionDep,
    sample_population: str | None = None,
) -> FilterOptions:
    return filter_options(cohort_id, db, sample_population)


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
    "/analyses/signature-panel",
    response_model=ComputeJobOut,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["Analyses"],
    operation_id="submitSignaturePanelAnalysis",
)
def submit_public_signature_panel_analysis(
    request_body: SignaturePanelAnalysisRequest,
    request: Request,
    response: Response,
    db: SessionDep,
) -> ComputeJobOut:
    return _submit_public_job(
        "signature_panel",
        request_body.model_dump(mode="json"),
        request,
        response,
        db,
    )


@public_router.get(
    "/gsea/collections",
    tags=["GSEA"],
    operation_id="listGseaGeneSetCollections",
)
def list_public_gsea_collections() -> dict:
    return {
        "collections": public_gene_set_catalog(
            settings.gsea_gene_set_dir
        ),
        "default_collection": "immport",
        "ranking_metrics": [
            {
                "value": "welch_t",
                "label": "Welch t statistic",
                "note": (
                    "Ranks group B minus group A without assuming equal variance."
                ),
            },
            {
                "value": "signal_to_noise",
                "label": "Signal-to-noise",
                "note": (
                    "Ranks the mean difference divided by the sum of group standard deviations."
                ),
            },
        ],
        "contrast": "group_b_minus_group_a",
    }


@public_router.post(
    "/analyses/gsea",
    response_model=ComputeJobOut,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["GSEA"],
    operation_id="submitGseaAnalysis",
)
def submit_public_gsea_analysis(
    request_body: GseaAnalysisRequest,
    request: Request,
    response: Response,
    db: SessionDep,
) -> ComputeJobOut:
    try:
        collection = resolve_gene_set_collection(
            settings.gsea_gene_set_dir,
            request_body.gene_set_collection,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "INVALID_GENE_SET_COLLECTION", "message": str(exc)},
        ) from exc
    return _submit_public_job(
        "gsea",
        request_body.model_dump(mode="json"),
        request,
        response,
        db,
        cache_context_extra={
            "gene_set_collection": collection["id"],
            "gene_set_sha256": collection["sha256"],
        },
    )


@public_router.post(
    "/analyses/expression-comparisons",
    response_model=ComputeJobOut,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["Analyses"],
    operation_id="submitExpressionComparison",
)
def submit_public_expression_comparison(
    request_body: ExpressionComparisonRequest,
    request: Request,
    response: Response,
    db: SessionDep,
) -> ComputeJobOut:
    return _submit_public_job(
        "expression_comparison",
        request_body.model_dump(mode="json"),
        request,
        response,
        db,
    )


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
def get_public_analysis_batch(
    batch_id: str,
    request: Request,
    db: SessionDep,
) -> AnalysisBatchOut:
    job = db.get(ComputeJob, batch_id)
    if job is None or job.kind != "batch":
        raise HTTPException(status_code=404, detail={"code": "JOB_NOT_FOUND", "message": "Batch not found."})
    _authorize_compute_job_access(db, job, request)
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
    request: Request,
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
    _authorize_compute_job_access(db, job, request)
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
    request: Request,
    db: SessionDep,
) -> Response:
    _ensure_public_result_retained(db, session_id, {"multiverse"})
    job = db.scalar(
        select(ComputeJob)
        .where(ComputeJob.kind == "multiverse")
        .where(ComputeJob.result_id == session_id)
    )
    if job is None:
        raise HTTPException(status_code=404, detail="Multiverse not found.")
    _authorize_compute_job_access(db, job, request)
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
    session_private_dataset_ids: set[str] = set()
    for job_id in sorted(
        {entry.job_id for entry in request_body.entries}
    ):
        source = db.get(ComputeJob, job_id)
        if source is not None:
            _authorize_compute_job_access(db, source, request)
            session_private_dataset_ids.update(
                private_dataset_ids_in_payload(source.request_payload)
            )
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
    payload = request_body.model_dump(mode="json")
    payload["private_dataset_ids"] = sorted(session_private_dataset_ids)
    return _submit_public_job(
        "session",
        payload,
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
    request: Request,
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
    _authorize_compute_job_access(db, job, request)
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
    request: Request,
    db: SessionDep,
) -> Response:
    _ensure_public_result_retained(db, report_id, {"session"})
    job = db.scalar(
        select(ComputeJob)
        .where(ComputeJob.kind == "session")
        .where(ComputeJob.result_id == report_id)
    )
    if job is None:
        raise HTTPException(status_code=404, detail="Session report not found.")
    _authorize_compute_job_access(db, job, request)
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


def _public_gsea_job(
    gsea_id: str,
    db: Session,
    request: Request,
) -> ComputeJob:
    _ensure_public_result_retained(db, gsea_id, {"gsea"})
    job = db.scalar(
        select(ComputeJob)
        .where(ComputeJob.kind == "gsea")
        .where(ComputeJob.result_id == gsea_id)
    )
    if job is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "GSEA_NOT_FOUND",
                "message": "GSEA result not found.",
            },
        )
    _authorize_compute_job_access(db, job, request)
    if job.status != "completed" or job.result_json is None:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "JOB_NOT_COMPLETE",
                "message": f"GSEA status is {job.status}.",
            },
        )
    return job


@public_router.get(
    "/analyses/gsea/{gsea_id}",
    response_model=GseaAnalysisOut,
    tags=["GSEA"],
    operation_id="getGseaAnalysis",
)
def get_public_gsea_analysis(
    gsea_id: str,
    request: Request,
    db: SessionDep,
) -> GseaAnalysisOut:
    job = _public_gsea_job(gsea_id, db, request)
    return GseaAnalysisOut(**job.result_json)


@public_router.get(
    "/analyses/gsea/{gsea_id}/download/{kind}",
    tags=["GSEA"],
    operation_id="downloadGseaArtifact",
    response_class=Response,
)
def download_public_gsea_artifact(
    gsea_id: str,
    kind: str,
    request: Request,
    db: SessionDep,
) -> Response:
    _public_gsea_job(gsea_id, db, request)
    result_dir = settings.artifact_dir / "gsea" / gsea_id
    files = {
        "csv": ("gsea_results.csv", "text/csv"),
        "ranking_csv": ("ranked_genes.csv", "text/csv"),
        "groups_csv": ("sample_groups.csv", "text/csv"),
        "leading_edges_csv": ("leading_edges.csv", "text/csv"),
        "svg": ("gsea_landscape.svg", "image/svg+xml"),
        "dotplot_svg": ("gsea_dotplot.svg", "image/svg+xml"),
        "json": ("result.json", "application/json"),
        "input": ("input.json", "application/json"),
        "gene_set_manifest": (
            "gene_set_manifest.json",
            "application/json",
        ),
        "audit_json": ("audit_report.json", "application/json"),
        "attestation": (
            "attestation_receipt.json",
            "application/json",
        ),
        "methodology": ("methodology.txt", "text/plain"),
        "camera_r_script": ("camera_gsea.R", "text/plain"),
    }
    if kind == "zip":
        buffer = io.BytesIO()
        with zipfile.ZipFile(
            buffer,
            mode="w",
            compression=zipfile.ZIP_DEFLATED,
        ) as archive:
            for filename, _media_type in files.values():
                path = result_dir / filename
                if path.is_file():
                    archive.write(path, arcname=filename)
        return Response(
            content=buffer.getvalue(),
            media_type="application/zip",
            headers={
                "Content-Disposition": (
                    f'attachment; filename="{gsea_id}.gsea.zip"'
                )
            },
        )
    if kind not in files:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "INVALID_DOWNLOAD_KIND",
                "message": (
                    "Download kind must be csv, ranking_csv, groups_csv, "
                    "leading_edges_csv, svg, dotplot_svg, json, input, "
                    "gene_set_manifest, audit_json, attestation, methodology, "
                    "camera_r_script "
                    "or zip."
                ),
            },
        )
    filename, media_type = files[kind]
    path = result_dir / filename
    if not path.is_file():
        raise HTTPException(
            status_code=404,
            detail={
                "code": "ARTIFACT_NOT_FOUND",
                "message": f"GSEA artifact {kind} is not available.",
            },
        )
    return FileResponse(
        path,
        media_type=media_type,
        filename=f"{gsea_id}.{filename}",
    )


def _public_expression_comparison_job(
    comparison_id: str,
    db: Session,
    request: Request,
) -> ComputeJob:
    _ensure_public_result_retained(
        db,
        comparison_id,
        {"expression_comparison"},
    )
    job = db.scalar(
        select(ComputeJob)
        .where(ComputeJob.kind == "expression_comparison")
        .where(ComputeJob.result_id == comparison_id)
    )
    if job is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "EXPRESSION_COMPARISON_NOT_FOUND",
                "message": "Expression comparison result not found.",
            },
        )
    _authorize_compute_job_access(db, job, request)
    if job.status != "completed" or job.result_json is None:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "JOB_NOT_COMPLETE",
                "message": f"Expression comparison status is {job.status}.",
            },
        )
    return job


@public_router.get(
    "/analyses/expression-comparisons/{comparison_id}",
    response_model=ExpressionComparisonOut,
    tags=["Analyses"],
    operation_id="getExpressionComparison",
)
def get_public_expression_comparison(
    comparison_id: str,
    request: Request,
    db: SessionDep,
) -> ExpressionComparisonOut:
    job = _public_expression_comparison_job(comparison_id, db, request)
    return ExpressionComparisonOut(**job.result_json)


@public_router.get(
    "/analyses/expression-comparisons/{comparison_id}/download/{kind}",
    tags=["Analyses"],
    operation_id="downloadExpressionComparisonArtifact",
    response_class=Response,
)
def download_public_expression_comparison_artifact(
    comparison_id: str,
    kind: str,
    request: Request,
    db: SessionDep,
) -> Response:
    _public_expression_comparison_job(comparison_id, db, request)
    result_dir = (
        settings.artifact_dir / "expression_comparisons" / comparison_id
    )
    files = {
        "values_csv": ("expression_values.csv", "text/csv"),
        "groups_csv": ("sample_groups.csv", "text/csv"),
        "statistics_csv": ("gene_statistics.csv", "text/csv"),
        "violin_svg": ("violin_plot.svg", "image/svg+xml"),
        "boxplot_svg": ("boxplot.svg", "image/svg+xml"),
        "heatmap_svg": ("heatmap.svg", "image/svg+xml"),
        "json": ("result.json", "application/json"),
        "input": ("input.json", "application/json"),
        "methodology": ("methodology.txt", "text/plain"),
        "audit_json": ("audit_report.json", "application/json"),
        "attestation": ("attestation_receipt.json", "application/json"),
    }
    if kind == "zip":
        missing = [
            filename
            for filename, _media_type in files.values()
            if not (result_dir / filename).is_file()
        ]
        if missing:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "ARTIFACT_BUNDLE_INCOMPLETE",
                    "message": (
                        "Expression comparison bundle is incomplete: "
                        + ", ".join(sorted(missing))
                        + "."
                    ),
                },
            )
        buffer = io.BytesIO()
        with zipfile.ZipFile(
            buffer,
            mode="w",
            compression=zipfile.ZIP_DEFLATED,
        ) as archive:
            for filename, _media_type in files.values():
                path = result_dir / filename
                if path.is_file():
                    archive.write(path, arcname=filename)
        return Response(
            content=buffer.getvalue(),
            media_type="application/zip",
            headers={
                "Content-Disposition": (
                    f'attachment; filename="{comparison_id}.expression-comparison.zip"'
                )
            },
        )
    if kind not in files:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "INVALID_DOWNLOAD_KIND",
                "message": (
                    "Download kind must be values_csv, groups_csv, "
                    "statistics_csv, violin_svg, boxplot_svg, heatmap_svg, "
                    "json, input, methodology, audit_json, attestation or zip."
                ),
            },
        )
    filename, media_type = files[kind]
    path = result_dir / filename
    if not path.is_file():
        raise HTTPException(
            status_code=404,
            detail={
                "code": "ARTIFACT_NOT_FOUND",
                "message": (
                    f"Expression comparison artifact {kind} is not available."
                ),
            },
        )
    return FileResponse(
        path,
        media_type=media_type,
        filename=f"{comparison_id}.{filename}",
    )


@public_router.get(
    "/analyses/{analysis_id}",
    response_model=AnalysisOut,
    tags=["Analyses"],
    operation_id="getSurvivalAnalysis",
)
def get_public_analysis(
    analysis_id: str,
    request: Request,
    db: SessionDep,
) -> AnalysisOut:
    _ensure_public_result_retained(
        db,
        analysis_id,
        {"analysis", "combined", "signature_panel"},
    )
    job = db.get(AnalysisJob, analysis_id)
    if job is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "ANALYSIS_NOT_FOUND", "message": "Analysis not found."},
        )
    _authorize_analysis_job_access(db, job, request)
    return _public_analysis(job)


@public_router.get(
    "/analyses/{analysis_id}/download/{kind}",
    tags=["Analyses"],
    operation_id="downloadAnalysisArtifact",
    response_class=Response,
)
def download_public_analysis(
    analysis_id: str,
    kind: str,
    request: Request,
    db: SessionDep,
) -> Response:
    _ensure_public_result_retained(
        db,
        analysis_id,
        {"analysis", "combined", "signature_panel"},
    )
    job = db.get(AnalysisJob, analysis_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Analysis not found.")
    _authorize_analysis_job_access(db, job, request)
    return download_analysis(analysis_id, kind, request, db)


@public_router.post(
    "/pancancer/hierarchical/preflight",
    response_model=HierarchicalPanCancerPreflightOut,
    tags=["Pan-cancer"],
    operation_id="preflightHierarchicalPanCancerSurvival",
)
def preflight_public_hierarchical_pancancer(
    request_body: HierarchicalPanCancerRequest,
    db: SessionDep,
) -> HierarchicalPanCancerPreflightOut:
    try:
        bundle = build_hierarchical_preflight(request_body, db, settings)
    except (ValueError, OSError) as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "HIERARCHICAL_PREFLIGHT_FAILED",
                "message": str(exc),
            },
        ) from exc
    return HierarchicalPanCancerPreflightOut(**bundle.payload)


@public_router.post(
    "/pancancer/hierarchical-survival",
    response_model=ComputeJobOut,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["Pan-cancer"],
    operation_id="submitHierarchicalPanCancerSurvival",
)
def submit_public_hierarchical_pancancer(
    request_body: HierarchicalPanCancerRequest,
    request: Request,
    response: Response,
    db: SessionDep,
) -> ComputeJobOut:
    repository_version = hierarchical_repository_version(db, settings)
    # Preserve the literal user query through the queue/worker boundary. The
    # worker resolves it to the same canonical estimand, while the provenance-
    # bound artifact identity keeps P53, TP53, HER2, etc. auditable separately.
    request_payload = request_body.worker_payload()
    return _submit_public_job(
        "pancancer_hierarchical",
        request_payload,
        request,
        response,
        db,
        cache_context_extra={
            "hierarchical_repository_version": repository_version,
        },
    )


@public_router.get(
    "/pancancer/hierarchical-survival/{scan_id}",
    response_model=HierarchicalPanCancerOut,
    tags=["Pan-cancer"],
    operation_id="getHierarchicalPanCancerSurvival",
)
def get_public_hierarchical_pancancer(
    scan_id: str,
    db: SessionDep,
) -> HierarchicalPanCancerOut:
    _ensure_public_result_retained(db, scan_id, {"pancancer_hierarchical"})
    try:
        path = hierarchical_result_path(settings, scan_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "SCAN_NOT_FOUND",
                "message": "Hierarchical pan-cancer scan not found.",
            },
        ) from exc
    if not path.is_file():
        raise HTTPException(
            status_code=404,
            detail={
                "code": "SCAN_NOT_FOUND",
                "message": "Hierarchical pan-cancer scan not found.",
            },
        )
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["downloads"] = publicize_download_links(
        hierarchical_downloads(scan_id)
    )
    return HierarchicalPanCancerOut(**payload)


@public_router.get(
    "/pancancer/hierarchical-survival/{scan_id}/download/{kind}",
    tags=["Pan-cancer"],
    operation_id="downloadHierarchicalPanCancerArtifact",
    response_class=Response,
)
def download_public_hierarchical_pancancer_artifact(
    scan_id: str,
    kind: str,
    db: SessionDep,
) -> Response:
    _ensure_public_result_retained(db, scan_id, {"pancancer_hierarchical"})
    try:
        result_dir = hierarchical_result_path(settings, scan_id).parent
    except ValueError as exc:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "SCAN_NOT_FOUND",
                "message": "Hierarchical pan-cancer scan not found.",
            },
        ) from exc
    files = hierarchical_download_files()
    if kind == "zip":
        paths = [
            result_dir / filename
            for filename, _media_type in files.values()
        ]
        missing = [path.name for path in paths if not path.is_file()]
        if missing:
            raise HTTPException(
                status_code=404,
                detail={
                    "code": "ARTIFACT_BUNDLE_INCOMPLETE",
                    "message": (
                        "Hierarchical pan-cancer bundle is incomplete: "
                        + ", ".join(sorted(missing))
                        + "."
                    ),
                },
            )
        buffer = io.BytesIO()
        with zipfile.ZipFile(
            buffer,
            mode="w",
            compression=zipfile.ZIP_DEFLATED,
        ) as archive:
            for path in paths:
                archive.write(path, arcname=path.name)
        return Response(
            content=buffer.getvalue(),
            media_type="application/zip",
            headers={
                "Content-Disposition": (
                    f'attachment; filename="{scan_id}.hierarchical-pancancer.zip"'
                )
            },
        )
    if kind not in files:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "INVALID_DOWNLOAD_KIND",
                "message": (
                    "Download kind must be studies, cancers, ledger, "
                    "methodology, audit_json, audit_html, attestation, "
                    "result_json or zip."
                ),
            },
        )
    filename, media_type = files[kind]
    path = result_dir / filename
    if not path.is_file():
        raise HTTPException(
            status_code=404,
            detail={
                "code": "ARTIFACT_NOT_FOUND",
                "message": f"Hierarchical artifact {kind} is not available.",
            },
        )
    return FileResponse(
        path,
        media_type=media_type,
        filename=f"{scan_id}.{filename}",
    )


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
def get_public_compute_job(
    job_id: str,
    request: Request,
    db: SessionDep,
) -> ComputeJobOut:
    job = db.get(ComputeJob, job_id)
    if job is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "JOB_NOT_FOUND", "message": "Compute job not found."},
        )
    _authorize_compute_job_access(db, job, request)
    return compute_job_out(job, settings)


if settings.public_api_enabled:
    app.include_router(public_router)

    from app.mcp_server import mcp, mcp_http_app

    mcp.settings.streamable_http_path = "/mcp"
    app.mount("/", mcp_http_app(), name="mcp")


from fastapi.openapi.utils import get_openapi


def public_openapi() -> dict:
    if app.openapi_schema is not None:
        return app.openapi_schema
    # FastAPI 0.141 keeps included routers as a lazy route group. Build the
    # deliberately public schema from its source router instead of depending
    # on internal route-flattening behavior.
    public_routes = list(public_router.routes)
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
