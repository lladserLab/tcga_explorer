from __future__ import annotations

from contextvars import ContextVar
import json
from typing import Any

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations

from app.config import get_settings
from app.database import SessionLocal
from app.jobs import ComputeQueueError, compute_job_out, publicize_download_links, submit_compute_job
from app.models import AnalysisJob, ComputeJob
from app.pipeline_versions import compute_cache_context
from app.schemas import (
    AnalysisRequest,
    CombinedSignatureAnalysisRequest,
    PanCancerSurvivalRequest,
    PublicAnalysisBatchRequest,
)


settings = get_settings()
_mcp_client_identity: ContextVar[str] = ContextVar(
    "tcga_trace_mcp_client_identity",
    default="mcp:anonymous",
)

mcp = FastMCP(
    name="TCGA-TRACE",
    instructions=(
        "Use TCGA-TRACE for exploratory transcriptomic survival analyses over public TCGA data. "
        "Before submitting an analysis, verify the cohort, gene, endpoint, expression scale, and filters. "
        "Compute tools return asynchronous jobs; call tcga_get_job until the status is completed or failed. "
        "Never present these results as clinical advice. Preserve warnings, neutral not-evaluable states, sample "
        "counts, endpoint provenance, model family, and multiple-testing context when explaining results."
    ),
    website_url=settings.public_base_url.rstrip("/"),
    stateless_http=True,
    json_response=True,
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=settings.mcp_allowed_host_list,
        allowed_origins=settings.mcp_allowed_origin_list,
    ),
)

READ_ONLY = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    openWorldHint=False,
)
COMPUTE = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)


def _absolute_links(value: Any) -> Any:
    base = settings.public_base_url.rstrip("/")
    if isinstance(value, str) and value.startswith("/"):
        public_path = publicize_download_links(value)
        return f"{base}{public_path}"
    if isinstance(value, list):
        return [_absolute_links(item) for item in value]
    if isinstance(value, dict):
        return {key: _absolute_links(item) for key, item in value.items()}
    return value


def _submit(
    kind: str,
    payload: dict[str, Any],
    context: Context | None = None,
) -> dict[str, Any]:
    client_key = _mcp_client_identity.get()
    if context is not None and context.client_id:
        client_key = f"mcp-client:{context.client_id}"
    try:
        with SessionLocal() as db:
            # Imported lazily because the web application mounts this MCP
            # server during its own lifespan initialization.
            from app.main import current_data_version

            job = submit_compute_job(
                db,
                kind=kind,
                request_payload=payload,
                client_key=client_key,
                settings=settings,
                cache_context=compute_cache_context(kind, data_version=current_data_version(db)),
            )
            result = compute_job_out(job, settings).model_dump(mode="json")
    except ComputeQueueError as exc:
        return {
            "ok": False,
            "error": {
                "code": exc.code,
                "message": exc.message,
                "retry_after_seconds": exc.retry_after,
            },
        }
    result["result"] = _compact_result(kind, result.get("result"))
    return _absolute_links({"ok": True, "job": result})


def _compact_result(kind: str, result: dict[str, Any] | None) -> dict[str, Any] | None:
    if result is None:
        return None
    if kind in {"analysis", "combined"}:
        metrics = result.get("metrics") or {}
        metric_keys = [
            "n_patients",
            "n_events",
            "endpoint",
            "endpoint_label",
            "endpoint_source",
            "expression_scale",
            "expression_scale_label",
            "logrank_p_value",
            "group_counts",
            "event_counts",
            "median_survival_days",
            "cutpoint_details",
            "hazard_ratio",
            "hr_conf_low",
            "hr_conf_high",
            "hr_p_value",
            "cox_models",
            "hr_ph_test",
            "hr_qc_status",
            "quality",
            "signature",
            "audit_report",
        ]
        return {
            "id": result.get("id"),
            "status": result.get("status"),
            "cohort": result.get("cohort"),
            "gene_symbol": result.get("gene_symbol"),
            "cutpoint_method": result.get("cutpoint_method"),
            "metrics": {key: metrics.get(key) for key in metric_keys if key in metrics},
            "warnings": result.get("warnings") or [],
            "downloads": result.get("downloads") or {},
        }
    if kind == "batch":
        items = []
        for item in result.get("results", []):
            nested = item.get("result") or {}
            items.append(
                {
                    "index": item.get("index"),
                    "status": item.get("status"),
                    "analysis_id": nested.get("id"),
                    "cohort": nested.get("cohort"),
                    "gene_symbol": nested.get("gene_symbol"),
                    "error": item.get("error"),
                    "code": item.get("code"),
                }
            )
        return {
            "total": result.get("total"),
            "completed": result.get("completed"),
            "failed": result.get("failed"),
            "results": items,
        }
    if kind == "pancancer":
        return {
            "scan_id": result.get("scan_id"),
            "status": result.get("status"),
            "gene_symbol": result.get("gene_symbol"),
            "endpoint": result.get("endpoint"),
            "endpoint_mode": result.get("endpoint_mode"),
            "summary": result.get("summary"),
            "reference": result.get("reference"),
            "meta_analysis": result.get("meta_analysis"),
            "clinical_sensitivity": result.get("clinical_sensitivity"),
            "pipeline_version": result.get("pipeline_version"),
            "audit": result.get("audit"),
            "warnings": result.get("warnings") or [],
            "downloads": result.get("downloads") or {},
        }
    return result


def _compact_immune_gene(row: dict[str, Any]) -> dict[str, Any]:
    fields = (
        "gene_symbol",
        "source_list_count",
        "go_term_count",
        "reactome_term_count",
        "completed_cohorts",
        "global_fdr_hits",
        "harmful_global_fdr_hits",
        "protective_global_fdr_hits",
        "min_global_fdr",
        "top_cohort",
        "top_cohort_direction",
        "top_cohort_hr",
        "top_cohort_global_fdr",
        "meta_hr",
        "meta_hr_conf_low",
        "meta_hr_conf_high",
        "meta_fdr",
        "meta_i_squared",
    )
    return {
        field: row.get(field)
        for field in fields
        if row.get(field) is not None
    }


@mcp.tool(
    name="tcga_list_cohorts",
    title="List TCGA cohorts",
    description="Use this when you need the TCGA cancer cohorts available for analysis.",
    annotations=READ_ONLY,
)
def tcga_list_cohorts() -> dict[str, Any]:
    from app.main import list_cohorts

    with SessionLocal() as db:
        cohorts = [
            {
                "id": row.id,
                "disease_type": row.disease_type,
                "primary_site": row.primary_site,
                "n_samples_paired": row.n_samples_paired,
                "n_patients_paired": row.n_patients_paired,
                "n_genes": row.n_genes,
            }
            for row in list_cohorts(db)
        ]
    return {"cohorts": cohorts}


@mcp.tool(
    name="tcga_get_dataset_summary",
    title="Get TCGA dataset summary",
    description="Use this when you need cohort coverage, clinical metadata coverage, or dataset provenance.",
    annotations=READ_ONLY,
)
def tcga_get_dataset_summary(cohort: str | None = None) -> dict[str, Any]:
    from app.main import build_dataset_summary

    with SessionLocal() as db:
        result = build_dataset_summary(db, cohort)
    result.pop("cache", None)
    return _absolute_links(result)


@mcp.tool(
    name="tcga_list_survival_endpoints",
    title="List survival endpoints",
    description="Use this when you need the globally available OS, PFI, DFI, or DSS endpoint definitions.",
    annotations=READ_ONLY,
)
def tcga_list_survival_endpoints() -> dict[str, Any]:
    from app.main import endpoint_options

    with SessionLocal() as db:
        return endpoint_options(db)


@mcp.tool(
    name="tcga_get_cohort_endpoints",
    title="Get cohort survival endpoints",
    description="Use this before analysis to verify endpoint availability, linked patients, events, and source for one cohort.",
    annotations=READ_ONLY,
)
def tcga_get_cohort_endpoints(cohort_id: str) -> dict[str, Any]:
    from app.main import cohort_endpoint_options

    with SessionLocal() as db:
        return cohort_endpoint_options(cohort_id, db)


@mcp.tool(
    name="tcga_list_expression_scales",
    title="List RNA expression scales",
    description="Use this when choosing among log2 TPM, CPM, FPKM, and FPKM-UQ expression scales.",
    annotations=READ_ONLY,
)
def tcga_list_expression_scales() -> dict[str, Any]:
    from app.main import list_expression_scales

    return {"expression_scales": list_expression_scales()}


@mcp.tool(
    name="tcga_get_filter_options",
    title="Get cohort filter options",
    description="Use this before analysis to inspect available sample types, stages, grades, demographics, ages, and follow-up range.",
    annotations=READ_ONLY,
)
def tcga_get_filter_options(cohort_id: str) -> dict[str, Any]:
    from app.main import filter_options

    with SessionLocal() as db:
        return filter_options(cohort_id, db).model_dump(mode="json")


@mcp.tool(
    name="tcga_search_genes",
    title="Search cohort genes",
    description="Use this to find valid gene symbols in a selected cohort before submitting an analysis.",
    annotations=READ_ONLY,
)
def tcga_search_genes(cohort_id: str, query: str = "", limit: int = 25) -> dict[str, Any]:
    from app.main import search_genes

    safe_limit = min(max(limit, 1), 100)
    with SessionLocal() as db:
        return search_genes(cohort_id, db, query, safe_limit).model_dump(mode="json")


@mcp.tool(
    name="tcga_resolve_gene",
    title="Resolve a gene symbol",
    description="Use this to resolve a submitted symbol or a supported legacy alias in one cohort.",
    annotations=READ_ONLY,
)
def tcga_resolve_gene(cohort_id: str, query: str) -> dict[str, Any]:
    from app.main import resolve_gene

    with SessionLocal() as db:
        return resolve_gene(cohort_id, db, query)


@mcp.tool(
    name="tcga_run_survival_analysis",
    title="Run a survival analysis",
    description="Use this to submit one gene or RNA signature for Kaplan-Meier, Cox, RMST, and diagnostic analysis.",
    annotations=COMPUTE,
)
def tcga_run_survival_analysis(request: AnalysisRequest, context: Context) -> dict[str, Any]:
    return _submit("analysis", request.model_dump(mode="json"), context)


@mcp.tool(
    name="tcga_run_combined_analysis",
    title="Run a combined-signature analysis",
    description="Use this to evaluate two RNA signatures jointly, including continuous Cox interaction models.",
    annotations=COMPUTE,
)
def tcga_run_combined_analysis(
    request: CombinedSignatureAnalysisRequest,
    context: Context,
) -> dict[str, Any]:
    return _submit("combined", request.model_dump(mode="json"), context)


@mcp.tool(
    name="tcga_run_batch_analysis",
    title="Run a bounded analysis batch",
    description="Use this to compare up to 25 survival-analysis requests in one asynchronous batch.",
    annotations=COMPUTE,
)
def tcga_run_batch_analysis(
    request: PublicAnalysisBatchRequest,
    context: Context,
) -> dict[str, Any]:
    if len(request.analyses) > settings.public_batch_max_analyses:
        return {
            "ok": False,
            "error": {
                "code": "BATCH_TOO_LARGE",
                "message": f"Public batches are limited to {settings.public_batch_max_analyses} analyses.",
            },
        }
    payload = request.model_dump(mode="json")
    payload["max_concurrency"] = 1
    return _submit("batch", payload, context)


@mcp.tool(
    name="tcga_run_pancancer_analysis",
    title="Run a pan-cancer survival scan",
    description="Use this to scan one gene or RNA signature across selected TCGA cohorts with FDR and meta-analysis.",
    annotations=COMPUTE,
)
def tcga_run_pancancer_analysis(
    request: PanCancerSurvivalRequest,
    context: Context,
) -> dict[str, Any]:
    return _submit("pancancer", request.model_dump(mode="json"), context)


@mcp.tool(
    name="tcga_get_job",
    title="Get compute job status",
    description="Use this after a compute submission to poll status and retrieve a compact result when completed.",
    annotations=READ_ONLY,
)
def tcga_get_job(job_id: str) -> dict[str, Any]:
    with SessionLocal() as db:
        job = db.get(ComputeJob, job_id)
        if job is None:
            return {"ok": False, "error": {"code": "JOB_NOT_FOUND", "message": "Compute job not found."}}
        result = compute_job_out(job, settings).model_dump(mode="json")
    result["result"] = _compact_result(job.kind, result.get("result"))
    return _absolute_links({"ok": True, "job": result})


@mcp.tool(
    name="tcga_get_analysis",
    title="Get survival-analysis result",
    description="Use this to retrieve a completed analysis by ID with core metrics, warnings, and artifact links.",
    annotations=READ_ONLY,
)
def tcga_get_analysis(analysis_id: str) -> dict[str, Any]:
    from fastapi import HTTPException

    from app.main import _ensure_public_result_retained, analysis_out

    with SessionLocal() as db:
        analysis = db.get(AnalysisJob, analysis_id)
        if analysis is None:
            return {"ok": False, "error": {"code": "ANALYSIS_NOT_FOUND", "message": "Analysis not found."}}
        try:
            _ensure_public_result_retained(db, analysis_id, {"analysis", "combined"})
        except HTTPException as exc:
            detail = exc.detail if isinstance(exc.detail, dict) else {}
            return {
                "ok": False,
                "error": {
                    "code": str(detail.get("code") or "ARTIFACT_EXPIRED"),
                    "message": str(detail.get("message") or exc.detail),
                },
            }
        result = analysis_out(analysis).model_dump(mode="json")
    return _absolute_links({"ok": True, "analysis": _compact_result("analysis", result)})


@mcp.tool(
    name="tcga_list_immune_screens",
    title="List immune pan-cancer screens",
    description="Use this to discover precomputed immune pan-cancer screening datasets.",
    annotations=READ_ONLY,
)
def tcga_list_immune_screens() -> dict[str, Any]:
    from app.main import list_immune_pancancer_screens

    return _absolute_links(list_immune_pancancer_screens())


@mcp.tool(
    name="tcga_get_immune_screen",
    title="Get an immune pan-cancer screen",
    description="Use this to retrieve a precomputed immune screen summary and its biological result downloads.",
    annotations=READ_ONLY,
)
def tcga_get_immune_screen(screen_id: str) -> dict[str, Any]:
    from app.main import (
        get_immune_pancancer_screen,
        public_immune_screen_payload,
    )

    payload = public_immune_screen_payload(
        get_immune_pancancer_screen(screen_id)
    )
    model_views = {}
    for model, view in (payload.get("model_views") or {}).items():
        model_views[model] = {
            "model": view.get("model"),
            "label": view.get("label"),
            "role": view.get("role"),
            "headline": view.get("headline") or {},
            "direction_counts_global_fdr": (
                view.get("direction_counts_global_fdr") or {}
            ),
            "recurrence_summary": (
                (view.get("recurrence") or {}).get("summary") or {}
            ),
            "top_genes": [
                _compact_immune_gene(row)
                for row in (view.get("top_genes") or [])[:5]
            ],
        }
    compact = {
        "screen_id": payload.get("screen_id"),
        "created_at": payload.get("created_at"),
        "pipeline_version": payload.get("pipeline_version"),
        "data_version": payload.get("data_version") or {},
        "headline": payload.get("headline") or {},
        "clinical_sensitivity": {
            "available": (
                (payload.get("clinical_sensitivity") or {}).get("available")
            ),
            "selection_hierarchy": (
                (payload.get("clinical_sensitivity") or {}).get(
                    "selection_hierarchy"
                )
                or []
            ),
            "summary": (
                (payload.get("clinical_sensitivity") or {}).get("summary")
                or {}
            ),
            "notes": (
                (payload.get("clinical_sensitivity") or {}).get("notes")
                or []
            ),
        },
        "model_views": model_views,
        "audit": payload.get("audit") or {},
        "method_notes": payload.get("method_notes") or [],
        "downloads": payload.get("downloads") or {},
    }
    return _absolute_links(compact)


@mcp.resource(
    "tcga-trace://dataset/version",
    title="TCGA-TRACE dataset version",
    description="Current public dataset dates and reproducibility hash.",
    mime_type="application/json",
)
def dataset_version_resource() -> str:
    from app.cache_warmup import load_cache_manifest
    from app.main import dataset_dates

    with SessionLocal() as db:
        payload = dataset_dates(db, load_cache_manifest(settings.derived_expression_dir))
    return json.dumps(payload, ensure_ascii=False, indent=2)


@mcp.resource(
    "tcga-trace://methods",
    title="TCGA-TRACE methods",
    description="Methodological scope, interpretation constraints, and public API links.",
    mime_type="text/markdown",
)
def methods_resource() -> str:
    base = settings.public_base_url.rstrip("/")
    return (
        "# TCGA-TRACE methods\n\n"
        "TCGA-TRACE performs exploratory transcriptomic survival analysis over public TCGA RNA-seq "
        "and clinical endpoint data. It supports Kaplan-Meier, log-rank, Cox models, proportional-hazards "
        "diagnostics, restricted mean survival time, cutpoint sensitivity, combined signatures, and "
        "pan-cancer scans. Results are not clinical advice.\n\n"
        f"- API documentation: {base}/api/docs\n"
        f"- Integration guide: {base}/api/guide\n"
        f"- Web application: {base}/\n"
    )


class MCPClientIdentityMiddleware:
    """Bind anonymous MCP quotas to the proxy-verified session or client IP."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        headers = {
            key.decode("latin-1").lower(): value.decode("latin-1")
            for key, value in scope.get("headers", [])
        }
        session_id = headers.get("mcp-session-id", "").strip()
        real_ip = headers.get("x-real-ip", "").strip()
        if not real_ip:
            real_ip = headers.get("x-forwarded-for", "").split(",", 1)[0].strip()
        if not real_ip and scope.get("client"):
            real_ip = str(scope["client"][0])
        identity = f"mcp-session:{session_id}" if session_id else f"mcp-ip:{real_ip or 'anonymous'}"

        token = _mcp_client_identity.set(identity)
        try:
            await self.app(scope, receive, send)
        finally:
            _mcp_client_identity.reset(token)


def mcp_http_app():
    return MCPClientIdentityMiddleware(mcp.streamable_http_app())
