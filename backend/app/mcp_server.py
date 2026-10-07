from __future__ import annotations

from contextvars import ContextVar
import json
from typing import Any

from fastapi import HTTPException
from mcp.server.fastmcp import Context, FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations

from app.config import get_settings
from app.client_identity import scope_client_ip
from app.database import SessionLocal
from app.jobs import ComputeQueueError, compute_job_out, publicize_download_links, submit_compute_job
from app.models import AnalysisJob, ComputeJob
from app.pipeline_versions import (
    COMPUTE_PIPELINE_VERSIONS,
    IMMUNE_ATLAS_PIPELINE_VERSION,
    compute_cache_context,
)
from app.schemas import (
    AnalysisRequest,
    CombinedSignatureAnalysisRequest,
    ExpressionComparisonRequest,
    GseaAnalysisRequest,
    HierarchicalPanCancerRequest,
    MultiverseAnalysisRequest,
    PanCancerSurvivalRequest,
    PublicAnalysisBatchRequest,
    SignaturePanelAnalysisRequest,
)
from app.signature_scoring import SIGNATURE_SCORING_CONTRACT_VERSION
from app.user_datasets import (
    UserDatasetError,
    authorize_user_dataset,
    authorize_user_datasets_in_payload,
)


settings = get_settings()
MCP_RESULT_PREVIEW_LIMIT = 20
MCP_PREFLIGHT_UNIVERSE_PREVIEW_LIMIT = 50
_mcp_client_identity: ContextVar[str] = ContextVar(
    "tcga_trace_mcp_client_identity",
    default="mcp:anonymous",
)
_mcp_dataset_token: ContextVar[str | None] = ContextVar(
    "tcga_trace_mcp_dataset_token",
    default=None,
)

mcp = FastMCP(
    name="TRACE Explorer",
    instructions=(
        "Use TRACE Explorer for exploratory transcriptomic survival, grouped-expression, "
        "gene-set enrichment, robustness, and pan-cancer analyses over TCGA, "
        "curated independent cohorts, or a temporary private dataset previously uploaded through "
        "the web application or REST API. Candidate cohorts are discovery records, not compute-ready "
        "datasets; only submit IDs returned by trace_list_datasets. Before submitting an analysis, verify the dataset release, "
        "endpoint, expression layer, gene resolution, cohort context, molecular sample population, filters and "
        "per-analysis capabilities. Curated and private datasets may contain expression and patient metadata "
        "without a survival endpoint; inspect trace_get_dataset capabilities and do not request a survival "
        "workflow when survival.available is false. "
        "For private uploads, qc.custom_clinical summarizes only expression-matched patients; "
        "qc.clinical describes the original metadata table. Check endpoint exclusion counts and "
        "QC notices before interpreting missing outcomes or subgroup availability. "
        "For TCGA, obtain trace_get_tcga_filter_options and pass filters.sample_population; never infer "
        "treatment-naive status from primary tissue or missing prior-treatment metadata. Keep each clinical "
        "filter variable ID exactly as returned in clinical_grouping_variables. To restrict an analysis, "
        "place selected levels in filters.custom_filters: levels within a variable use OR and different "
        "variables use AND. Read each variable's provenance object before interpreting a subtype: it states "
        "whether the value is harmonized clinical metadata, a source-reported annotation, or user-declared; "
        "whether it is expression-derived; and whether TRACE recomputed it. PAM50 is expression-derived and "
        "source-reported in TCGA-BRCA; preserve its circularity and cross-study comparability warnings, and never "
        "call Basal-like PAM50 triple-negative breast cancer without observed ER, PR, and HER2 status. Keep each dataset "
        "as its own analytical universe; for IMmotion150 PFS, select exactly one study arm and never "
        "pool arms. "
        "For signatures, single, mean, z-score and weighted scoring remain "
        "available alongside Bioconductor singscore, ssGSEA and AUCell. The "
        "rank-based methods require the dataset capability "
        "rank_based_signature_scoring and a broad expression layer; use "
        "GENE:1 and GENE:-1 (or explicit up/down direction fields) for signed "
        "components. Their scores are frozen on the canonical molecular "
        "population before endpoint or clinical filters. Compute tools return asynchronous "
        "jobs; call trace_get_job until the status is completed or failed. "
        "Failed resubmissions count towards the same rolling hourly limits as REST; "
        "returning an identical active or retained completed job does not consume another submission. "
        "Do not automatically resubmit failed jobs without inspecting the error. "
        "Never present these results as clinical advice. Preserve warnings, neutral not-evaluable states, sample "
        "counts, endpoint provenance, model family, and multiple-testing context when explaining results. "
        "For single-marker survival, metrics.hazard_ratio describes the grouped contrast; continuous effects "
        "and their units are in metrics.continuous_analysis.linear_models. Do not interchange them. "
        "For combined predictors, inspect signature_interaction_cox_models; for signature panels, inspect "
        "signature_panel_cox_models. Report each model's own population and diagnostics. A small proportional-"
        "hazards diagnostic p value concerns time variation, not evidence for an association. Use dataset_id "
        "and dataset_release_id to identify the study; cohort alone may be a cancer-type compatibility label."
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
    # Context client IDs and MCP session IDs are controlled by callers and can
    # be rotated. The ASGI boundary binds compute quotas to the edge-verified IP.
    client_key = _mcp_client_identity.get()
    try:
        with SessionLocal() as db:
            # Imported lazily because the web application mounts this MCP
            # server during its own lifespan initialization.
            from app.main import (
                _preflight_repository_capabilities,
                current_data_version,
            )

            try:
                cache_context = compute_cache_context(
                    kind,
                    data_version=current_data_version(db),
                )
                if kind == "gsea":
                    from app.gsea import resolve_gene_set_collection

                    collection = resolve_gene_set_collection(
                        settings.gsea_gene_set_dir,
                        str(payload.get("gene_set_collection") or "immport"),
                    )
                    cache_context = {
                        **cache_context,
                        "gene_set_collection": collection["id"],
                        "gene_set_sha256": collection["sha256"],
                    }
                if kind == "pancancer_hierarchical":
                    from app.hierarchical_pancancer_service import (
                        hierarchical_repository_version,
                    )

                    cache_context = {
                        **cache_context,
                        "hierarchical_repository_version": (
                            hierarchical_repository_version(db, settings)
                        ),
                    }
                authorize_user_datasets_in_payload(
                    db,
                    payload,
                    _mcp_dataset_token.get(),
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
                    client_key=client_key,
                    settings=settings,
                    cache_context=cache_context,
                )
            except (ComputeQueueError, UserDatasetError):
                db.rollback()
                raise
            result = compute_job_out(job, settings).model_dump(mode="json")
    except UserDatasetError as exc:
        return {
            "ok": False,
            "error": {
                "code": exc.code,
                "message": exc.message,
            },
        }
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, dict) else {}
        return {
            "ok": False,
            "error": {
                "code": str(detail.get("code") or f"HTTP_{exc.status_code}"),
                "message": str(detail.get("message") or exc.detail),
                "details": detail.get("details") or {},
            },
        }
    except ValueError as exc:
        return {
            "ok": False,
            "error": {
                "code": "INVALID_REQUEST",
                "message": str(exc),
            },
        }
    except OSError:
        return {
            "ok": False,
            "error": {
                "code": (
                    "HIERARCHICAL_REPOSITORY_UNAVAILABLE"
                    if kind == "pancancer_hierarchical"
                    else "COMPUTE_PREPARATION_FAILED"
                ),
                "message": (
                    "The hierarchical repository is not available."
                    if kind == "pancancer_hierarchical"
                    else "The analysis inputs could not be prepared."
                ),
            },
        }
    except ComputeQueueError as exc:
        return {
            "ok": False,
            "error": {
                "code": exc.code,
                "message": exc.message,
                "retry_after_seconds": exc.retry_after,
                "details": exc.details,
            },
        }
    result["result"] = _compact_result(kind, result.get("result"))
    return _absolute_links({"ok": True, "job": result})


def _compact_continuous_analysis(value: dict[str, Any]) -> dict[str, Any]:
    """Keep the continuous estimand and diagnostics without spline plotting arrays."""
    summary = {
        key: value[key]
        for key in (
            "status", "reason", "population", "cutpoint_independent", "n_patients",
            "n_events", "predictor", "linear_models",
        )
        if key in value
    }
    spline = value.get("spline")
    if isinstance(spline, dict):
        summary["spline"] = {
            key: spline[key]
            for key in (
                "status", "reason", "method", "implementation", "n_patients", "n_events",
                "degrees_freedom", "events_per_parameter", "information_diagnostics",
                "nonlinear_degrees_freedom", "knot_percentiles", "knots_expression",
                "knots_z", "reference_percentile", "reference_expression", "reference_z",
                "overall_p_value", "nonlinearity_chisq", "nonlinearity_p_value",
                "aic_linear", "aic_spline", "ph_global_p_value", "warnings",
            )
            if key in spline
        }
    return summary


def _compact_result(kind: str, result: dict[str, Any] | None) -> dict[str, Any] | None:
    if result is None:
        return None
    if kind in {"analysis", "combined", "signature_panel"}:
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
            "combined_signature",
            "signature_interaction_cox_models",
            "signature_panel",
            "signature_panel_cox_models",
            "model_families",
            "clinical_adjustment",
            "multiplicity",
            "score_correlations",
            "competing_risks",
            "cox_forest_output",
            "audit_report",
            "dataset",
        ]
        compact_metrics = {key: metrics.get(key) for key in metric_keys if key in metrics}
        if isinstance(metrics.get("continuous_analysis"), dict):
            compact_metrics["continuous_analysis"] = _compact_continuous_analysis(
                metrics["continuous_analysis"],
            )
        return {
            "id": result.get("id"),
            "status": result.get("status"),
            "cohort": result.get("cohort"),
            "dataset_id": result.get("dataset_id"),
            "dataset_release_id": result.get("dataset_release_id"),
            "expression_scale": result.get("expression_scale"),
            "expression_scale_label": result.get("expression_scale_label"),
            "gene_symbol": result.get("gene_symbol"),
            "cutpoint_method": result.get("cutpoint_method"),
            "metrics": compact_metrics,
            "warnings": result.get("warnings") or [],
            "notices": result.get("notices") or [],
            "diagnostics": result.get("diagnostics") or {},
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
            "grouped_family": result.get("grouped_family"),
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
    if kind == "gsea":
        return {
            "schema_version": result.get("schema_version"),
            "gsea_id": result.get("gsea_id"),
            "status": result.get("status"),
            "pipeline_version": result.get("pipeline_version"),
            "cohort": result.get("cohort"),
            "dataset_id": result.get("dataset_id"),
            "expression_scale": result.get("expression_scale"),
            "grouping": result.get("grouping"),
            "gene_set_collection": result.get("gene_set_collection"),
            "ranking": result.get("ranking"),
            "inference": result.get("inference"),
            "summary": result.get("summary"),
            "top_pathways": (result.get("pathways") or [])[:20],
            "audit": result.get("audit"),
            "warnings": result.get("warnings") or [],
            "downloads": result.get("downloads") or {},
        }
    if kind == "expression_comparison":
        return {
            "comparison_id": result.get("comparison_id"),
            "status": result.get("status"),
            "pipeline_version": result.get("pipeline_version"),
            "cohort": result.get("cohort"),
            "dataset_id": result.get("dataset_id"),
            "expression_scale": result.get("expression_scale"),
            "grouping": result.get("grouping"),
            "summary": result.get("summary"),
            "top_genes": (result.get("statistics") or [])[:20],
            "audit": result.get("audit"),
            "warnings": result.get("warnings") or [],
            "downloads": result.get("downloads") or {},
        }
    if kind == "multiverse":
        return {
            "session_id": result.get("session_id"),
            "status": result.get("status"),
            "pipeline_version": result.get("pipeline_version"),
            "dataset_id": result.get("dataset_id"),
            "dataset_release_id": result.get("dataset_release_id"),
            "expression_layer_id": result.get("expression_layer_id"),
            "analysis_family": result.get("analysis_family") or {},
            "summary": result.get("summary") or {},
            "continuous_reference_preview": _bounded_preview(
                result.get("continuous_references") or [],
            ),
            "specification_preview": _bounded_preview(
                [
                    _compact_multiverse_specification(row)
                    for row in (result.get("specifications") or [])
                ],
            ),
            "execution_ledger_preview": _bounded_preview(
                result.get("execution_ledger") or [],
            ),
            "audit": result.get("audit") or {},
            "warnings": result.get("warnings") or [],
            "downloads": result.get("downloads") or {},
        }
    if kind == "pancancer_hierarchical":
        preflight = result.get("preflight") or {}
        return {
            "scan_id": result.get("scan_id"),
            "status": result.get("status"),
            "pipeline_version": result.get("pipeline_version"),
            "registry_version": result.get("registry_version"),
            "analysis_mode": result.get("analysis_mode"),
            "gene_symbol": result.get("gene_symbol"),
            "requested_gene_symbol": result.get("requested_gene_symbol"),
            "resolved_gene_symbol": result.get("resolved_gene_symbol"),
            "endpoint": result.get("endpoint"),
            "effect_scale": result.get("effect_scale") or {},
            "summary": result.get("summary") or {},
            "preflight_summary": preflight.get("summary") or {},
            "study_result_preview": _bounded_preview(
                [
                    _compact_hierarchical_study(row)
                    for row in (result.get("study_results") or [])
                ],
            ),
            "cancer_result_preview": _bounded_preview(
                result.get("cancer_results") or [],
            ),
            "global_result": result.get("global_result") or {},
            "global_result_scope": {
                "role": "deployed_two_stage_evidence_summary",
                "evidence_threshold_meaning": (
                    "Counts replicated cancers and events; it is not a "
                    "guarantee of nominal interval calibration."
                ),
                "cannot_conclude": (
                    "The summary and its classification do not establish a "
                    "universal biological direction across cancers."
                ),
            },
            "leave_one_out_preview": _compact_leave_one_out(
                result.get("leave_one_out") or {},
            ),
            "sensitivities": _compact_hierarchical_sensitivities(
                result.get("sensitivities") or {},
            ),
            "audit": result.get("audit") or {},
            "warnings": result.get("warnings") or [],
            "downloads": result.get("downloads") or {},
        }
    return result


def _bounded_preview(
    rows: list[dict[str, Any]],
    limit: int = MCP_RESULT_PREVIEW_LIMIT,
) -> dict[str, Any]:
    total = len(rows)
    returned = min(total, limit)
    return {
        "total": total,
        "returned": returned,
        "truncated": total > returned,
        "items": rows[:returned],
    }


def _compact_multiverse_specification(row: dict[str, Any]) -> dict[str, Any]:
    fields = (
        "specification_id",
        "index",
        "endpoint",
        "scoring_method",
        "cutpoint_method",
        "custom_percentile",
        "status",
        "analysis_id",
        "n_patients",
        "n_events",
        "group_counts",
        "event_counts",
        "inference_test",
        "inference_p_value",
        "grouped_bh_q_value",
        "grouped_bonferroni_p_value",
        "grouped_effect",
        "continuous_reference_id",
        "rmst",
        "marker_ph_p_value",
        "global_ph_p_value",
        "error_code",
        "error",
    )
    return {field: row.get(field) for field in fields if field in row}


def _compact_hierarchical_study(row: dict[str, Any]) -> dict[str, Any]:
    fields = (
        "universe_id",
        "study_id",
        "name",
        "cancer_code",
        "source_kind",
        "evidence_tier",
        "pooling_eligible",
        "status",
        "code",
        "reason",
        "n_patients",
        "n_events",
        "n_censored",
        "expression_iqr",
        "log_hr",
        "standard_error",
        "hazard_ratio",
        "hr_conf_low",
        "hr_conf_high",
        "p_value",
        "ph_p_value",
        "expression_scale",
        "gene_mapping",
        "warnings",
    )
    return {field: row.get(field) for field in fields if field in row}


def _compact_leave_one_out(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "studies": _bounded_preview(payload.get("studies") or []),
        "cancers": _bounded_preview(payload.get("cancers") or []),
    }


def _compact_hierarchical_sensitivities(
    sensitivities: dict[str, Any],
) -> dict[str, Any]:
    compact: dict[str, Any] = {}
    for name, value in sensitivities.items():
        payload = value if isinstance(value, dict) else {}
        compact[name] = {
            key: payload.get(key)
            for key in (
                "description",
                "available",
                "model",
                "classification",
                "formal_pan_cancer_support",
                "within_cancer_replication",
                "comparability",
                "reason",
                "summary",
                "global_effect",
            )
            if key in payload
        }
        compact[name]["cancer_effect_preview"] = _bounded_preview(
            payload.get("cancer_effects") or [],
        )
    return compact


def _compact_hierarchical_preflight(payload: dict[str, Any]) -> dict[str, Any]:
    universe_fields = (
        "universe_id",
        "name",
        "cancer_code",
        "source_kind",
        "study_cluster_id",
        "status",
        "included",
        "analysis_eligible",
        "patients",
        "events",
        "censored",
        "reasons",
        "preparation_error",
        "expression_scale",
        "gene_mapping",
    )
    return {
        "schema_version": payload.get("schema_version"),
        "pipeline_version": payload.get("pipeline_version"),
        "registry_version": payload.get("registry_version"),
        "requested_gene_symbol": payload.get("requested_gene_symbol"),
        "resolved_gene_symbol": payload.get("resolved_gene_symbol"),
        "request": payload.get("request") or {},
        "summary": payload.get("summary") or {},
        "universe_preview": _bounded_preview(
            [
                {
                    field: row.get(field)
                    for field in universe_fields
                    if field in row
                }
                for row in (payload.get("universes") or [])
            ],
            MCP_PREFLIGHT_UNIVERSE_PREVIEW_LIMIT,
        ),
        "cancer_group_preview": _bounded_preview(
            payload.get("cancer_groups") or [],
        ),
        "warnings": payload.get("warnings") or [],
    }


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
    name="trace_list_tcga_cohorts",
    title="List analysis cohorts",
    description=(
        "Use this compatibility tool to list the TCGA and external-only "
        "disease cohorts available for analysis. Check status before assuming "
        "that a cohort is a TCGA project."
    ),
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
                "status": row.status,
            }
            for row in list_cohorts(db)
        ]
    return {"cohorts": cohorts}


@mcp.tool(
    name="trace_list_cancer_types",
    title="List cancer types and external-cohort coverage",
    description=(
        "Use this to inspect the cancer contexts recognized by TRACE Cohort "
        "Explorer and the availability of curated independent cohorts."
    ),
    annotations=READ_ONLY,
)
def trace_list_cancer_types() -> dict[str, Any]:
    from app.main import build_repository_coverage

    with SessionLocal() as db:
        return build_repository_coverage(db)


@mcp.tool(
    name="trace_list_datasets",
    title="List curated external datasets",
    description=(
        "Use this to discover public, versioned bulk RNA-seq cohorts. Optionally "
        "filter by a cancer code such as LUAD or SKCM and by the intended "
        "analysis. Read capabilities before submitting compute."
    ),
    annotations=READ_ONLY,
)
def trace_list_datasets(
    cancer_code: str | None = None,
    analysis_type: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    from app.repository.service import list_repository_datasets

    try:
        if limit < 1 or limit > 100 or offset < 0:
            raise ValueError(
                "limit must be between 1 and 100, and offset cannot be negative."
            )
        with SessionLocal() as db:
            rows = list_repository_datasets(
                db,
                cancer_code=cancer_code,
                analysis_type=analysis_type,
                include_metadata=False,
            )
            return {
                "count": len(rows[offset : offset + limit]),
                "total_count": len(rows),
                "limit": limit,
                "offset": offset,
                "datasets": rows[offset : offset + limit],
            }
    except ValueError as exc:
        return {
            "ok": False,
            "error": {
                "code": "INVALID_ANALYSIS_TYPE",
                "message": str(exc),
            },
        }


@mcp.tool(
    name="trace_list_dataset_candidates",
    title="List reviewed dataset candidates",
    description=(
        "Use this to inspect public cohorts TRACE has reviewed but has not necessarily "
        "promoted for analysis. Candidate status and per-analysis decisions are explicit; "
        "only datasets returned by trace_list_datasets can be submitted to compute tools."
    ),
    annotations=READ_ONLY,
)
def trace_list_dataset_candidates(
    disease_id: str | None = None,
    status: str | None = None,
    analysis_type: str | None = None,
    query: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    from app.repository.candidates import (
        CandidateRegistryError,
        list_dataset_candidates,
    )

    try:
        if limit < 1 or limit > 100 or offset < 0:
            raise ValueError(
                "limit must be between 1 and 100, and offset cannot be negative."
            )
        payload = list_dataset_candidates(
            disease_id=disease_id,
            status=status,
            analysis_type=analysis_type,
            query=query,
        )
        rows = payload["candidates"]
        return {
            **payload,
            "total_count": payload["count"],
            "count": len(rows[offset : offset + limit]),
            "limit": limit,
            "offset": offset,
            "candidates": rows[offset : offset + limit],
        }
    except (CandidateRegistryError, OSError) as exc:
        return {
            "ok": False,
            "error": {
                "code": "CANDIDATE_REGISTRY_UNAVAILABLE",
                "message": str(exc),
            },
        }
    except ValueError as exc:
        return {
            "ok": False,
            "error": {
                "code": "INVALID_CANDIDATE_FILTER",
                "message": str(exc),
            },
        }


@mcp.tool(
    name="trace_get_dataset",
    title="Get a dataset",
    description=(
        "Use this to inspect one curated external dataset or a temporary private "
        "expression-and-patient-metadata dataset when its user-* ID is known and the "
        "transport supplies its access token. Inspect capabilities before requesting survival."
    ),
    annotations=READ_ONLY,
)
def trace_get_dataset(dataset_id: str) -> dict[str, Any]:
    if dataset_id.startswith("user-"):
        from app.user_datasets import get_user_dataset

        with SessionLocal() as db:
            authorize_user_dataset(
                db,
                dataset_id,
                _mcp_dataset_token.get(),
            )
            return get_user_dataset(db, dataset_id)

    from app.main import get_dataset

    with SessionLocal() as db:
        return get_dataset(dataset_id, db)


def _repository_discovery_error(exc: Exception) -> dict[str, Any]:
    if isinstance(exc, UserDatasetError):
        return {
            "ok": False,
            "error": {"code": exc.code, "message": exc.message},
        }
    return {
        "ok": False,
        "error": {"code": "DATASET_NOT_FOUND", "message": str(exc)},
    }


@mcp.tool(
    name="trace_get_dataset_endpoints",
    title="Get dataset survival endpoints",
    description=(
        "Use this before survival analysis to inspect endpoint definitions, "
        "availability, patient and event counts, time origin, and provenance for "
        "one curated external or temporary private dataset release. A private dataset "
        "may legitimately return no endpoints when it was uploaded for molecular analyses only."
    ),
    annotations=READ_ONLY,
)
def trace_get_dataset_endpoints(
    dataset_id: str,
    release_id: str | None = None,
) -> dict[str, Any]:
    from app.repository.service import (
        repository_endpoint_options,
        resolve_repository_context,
    )
    from app.user_datasets import get_user_dataset

    is_private = dataset_id.startswith("user-")
    try:
        with SessionLocal() as db:
            if is_private:
                authorize_user_dataset(db, dataset_id, _mcp_dataset_token.get())
                get_user_dataset(db, dataset_id)
            context = resolve_repository_context(
                db,
                dataset_id,
                release_id,
                include_private=is_private,
            )
            endpoints = repository_endpoint_options(db, context)
    except (UserDatasetError, ValueError) as exc:
        return _repository_discovery_error(exc)
    return {
        "ok": True,
        "dataset_id": dataset_id,
        "release_id": context.release.id,
        "endpoints": endpoints,
    }


@mcp.tool(
    name="trace_list_dataset_expression_layers",
    title="List dataset expression layers",
    description=(
        "Use this before gene search or analysis to inspect the available "
        "expression layers, transforms, dimensions, default layer, and download "
        "eligibility for one curated external or temporary private dataset release. "
        "Coverage counts patients and endpoints linked to each layer before tissue "
        "selection and filters. A paired_difference layer measures tumor minus "
        "matched adjacent expression per patient, not additional RNA profiles or "
        "a healthy-control cohort; changing layers can change the eligible patients."
    ),
    annotations=READ_ONLY,
)
def trace_list_dataset_expression_layers(
    dataset_id: str,
    release_id: str | None = None,
) -> dict[str, Any]:
    from app.repository.service import (
        repository_expression_layers,
        resolve_repository_context,
    )
    from app.user_datasets import get_user_dataset

    is_private = dataset_id.startswith("user-")
    try:
        with SessionLocal() as db:
            if is_private:
                authorize_user_dataset(db, dataset_id, _mcp_dataset_token.get())
                get_user_dataset(db, dataset_id)
            context = resolve_repository_context(
                db,
                dataset_id,
                release_id,
                include_private=is_private,
            )
            layers = repository_expression_layers(db, context)
    except (UserDatasetError, ValueError) as exc:
        return _repository_discovery_error(exc)
    return {
        "ok": True,
        "dataset_id": dataset_id,
        "release_id": context.release.id,
        "expression_layers": layers,
    }


@mcp.tool(
    name="trace_resolve_dataset_gene",
    title="Resolve a gene in a dataset",
    description=(
        "Use this after choosing a dataset expression layer to resolve an exact "
        "gene symbol or supported alias before submitting an analysis."
    ),
    annotations=READ_ONLY,
)
def trace_resolve_dataset_gene(
    dataset_id: str,
    query: str,
    release_id: str | None = None,
    expression_layer_id: str | None = None,
) -> dict[str, Any]:
    from app.expression import GeneNotFoundError
    from app.repository.service import (
        repository_gene_expression,
        resolve_repository_context,
    )
    from app.user_datasets import get_user_dataset

    is_private = dataset_id.startswith("user-")
    normalized = query.strip().upper()
    try:
        with SessionLocal() as db:
            if is_private:
                authorize_user_dataset(db, dataset_id, _mcp_dataset_token.get())
                get_user_dataset(db, dataset_id)
            context = resolve_repository_context(
                db,
                dataset_id,
                release_id,
                include_private=is_private,
            )
            _, layer, gene = repository_gene_expression(
                db,
                context,
                query,
                expression_layer_id,
            )
    except GeneNotFoundError as exc:
        return {
            "ok": True,
            "dataset_id": dataset_id,
            "release_id": release_id,
            "expression_layer_id": expression_layer_id,
            "query": normalized,
            "resolved": None,
            "status": "not_found",
            "warnings": [str(exc)],
        }
    except (UserDatasetError, ValueError) as exc:
        return _repository_discovery_error(exc)
    return {
        "ok": True,
        "dataset_id": dataset_id,
        "release_id": context.release.id,
        "expression_layer_id": layer.layer_id,
        "query": normalized,
        "resolved": gene.gene_symbol,
        "status": "exact" if normalized == gene.gene_symbol else "alias",
        "warnings": (
            []
            if normalized == gene.gene_symbol
            else [f"Gene alias {normalized} was resolved to {gene.gene_symbol}."]
        ),
    }


@mcp.tool(
    name="trace_get_dataset_filter_options",
    title="Get external or private dataset filter options",
    description=(
        "Use this before an analysis to inspect sample filters and the versioned "
        "clinical-grouping catalog for one curated external or temporary private "
        "dataset, including subtype annotations and patient-level counts."
    ),
    annotations=READ_ONLY,
)
def trace_get_dataset_filter_options(
    dataset_id: str,
    release_id: str | None = None,
) -> dict[str, Any]:
    from app.repository.service import (
        repository_filter_options,
        resolve_repository_context,
    )
    from app.user_datasets import get_user_dataset

    is_private = dataset_id.startswith("user-")
    try:
        with SessionLocal() as db:
            if is_private:
                authorize_user_dataset(
                    db,
                    dataset_id,
                    _mcp_dataset_token.get(),
                )
                get_user_dataset(db, dataset_id)
            context = resolve_repository_context(
                db,
                dataset_id,
                release_id,
                include_private=is_private,
            )
            filters = repository_filter_options(db, context)
    except UserDatasetError as exc:
        return {
            "ok": False,
            "error": {
                "code": exc.code,
                "message": exc.message,
            },
        }
    except ValueError as exc:
        return {
            "ok": False,
            "error": {
                "code": "DATASET_NOT_FOUND",
                "message": str(exc),
            },
        }
    return {
        "ok": True,
        "dataset_id": dataset_id,
        "release_id": context.release.id,
        "filter_options": filters,
    }


@mcp.tool(
    name="trace_search_dataset_genes",
    title="Search genes in a dataset",
    description=(
        "Use this to find gene symbols in one curated or temporary private "
        "dataset before submitting an analysis."
    ),
    annotations=READ_ONLY,
)
def trace_search_dataset_genes(
    dataset_id: str,
    query: str = "",
    limit: int = 25,
    release_id: str | None = None,
    expression_layer_id: str | None = None,
) -> dict[str, Any]:
    safe_limit = min(max(limit, 1), 100)
    if dataset_id.startswith("user-"):
        from app.repository.service import (
            resolve_repository_context,
            search_repository_genes,
        )
        from app.user_datasets import get_user_dataset

        with SessionLocal() as db:
            authorize_user_dataset(
                db,
                dataset_id,
                _mcp_dataset_token.get(),
            )
            get_user_dataset(db, dataset_id)
            context = resolve_repository_context(
                db,
                dataset_id,
                release_id,
                include_private=True,
            )
            genes = search_repository_genes(
                db,
                context,
                query,
                layer_id=expression_layer_id,
                limit=safe_limit,
            )
        return {
            "dataset_id": dataset_id,
            "query": query,
            "genes": genes,
        }

    from app.main import search_dataset_genes

    with SessionLocal() as db:
        result = search_dataset_genes(
            dataset_id,
            db,
            query,
            safe_limit,
            release_id,
            expression_layer_id,
        )
    return result.model_dump(mode="json")


@mcp.tool(
    name="trace_get_tcga_dataset_summary",
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
    name="trace_list_survival_endpoints",
    title="List survival endpoints",
    description="Use this when you need the globally available OS, PFI, DFI, or DSS endpoint definitions.",
    annotations=READ_ONLY,
)
def tcga_list_survival_endpoints() -> dict[str, Any]:
    from app.main import endpoint_options

    with SessionLocal() as db:
        return endpoint_options(db)


@mcp.tool(
    name="trace_get_tcga_cohort_endpoints",
    title="Get cohort survival endpoints",
    description=(
        "Verify endpoint availability, linked patients, events and source for a "
        "TCGA reference cohort. External-only cancers require a selected study: "
        "use trace_get_dataset_endpoints with its dataset_id instead. An external "
        "cohort is rejected with DATASET_REQUIRED, never reported as zero patients."
    ),
    annotations=READ_ONLY,
)
def tcga_get_cohort_endpoints(cohort_id: str) -> dict[str, Any]:
    from app.main import cohort_endpoint_options

    with SessionLocal() as db:
        return cohort_endpoint_options(cohort_id, db)


@mcp.tool(
    name="trace_list_expression_scales",
    title="List RNA expression scales",
    description="Use this when choosing among log2 TPM, CPM, FPKM, and FPKM-UQ expression scales.",
    annotations=READ_ONLY,
)
def tcga_list_expression_scales() -> dict[str, Any]:
    from app.main import list_expression_scales

    return {"expression_scales": list_expression_scales()}


@mcp.tool(
    name="trace_list_gsea_collections",
    title="List GSEA gene-set collections",
    description=(
        "Use this before GSEA to inspect the frozen, checksum-verified "
        "gene-set collections available on the server."
    ),
    annotations=READ_ONLY,
)
def trace_list_gsea_collections() -> dict[str, Any]:
    from app.main import list_public_gsea_collections

    return list_public_gsea_collections()


@mcp.tool(
    name="trace_get_tcga_filter_options",
    title="Get cohort filter options",
    description=(
        "Use this before TCGA analysis to choose an allowed molecular sample "
        "population and inspect the dataset-aware clinical_grouping_variables "
        "catalog, including BRCA PAM50, patient counts, derivation provenance, method notes, "
        "reference and cross-study comparability policy. Pass sample_population again "
        "after the user chooses it; TCGA-SKCM primary and metastatic samples are "
        "separate populations and are never pooled or used as fallback. Returned "
        "clinical options are population-specific; barcode/sample-type conflicts "
        "are excluded and counted. Catalog variables can be combined through "
        "filters.custom_filters with OR within a variable and AND across variables."
        " For external datasets use trace_get_dataset_filter_options with the "
        "selected dataset_id; external-only cohorts return DATASET_REQUIRED."
    ),
    annotations=READ_ONLY,
)
def tcga_get_filter_options(
    cohort_id: str,
    sample_population: str | None = None,
) -> dict[str, Any]:
    from app.main import filter_options

    with SessionLocal() as db:
        return filter_options(
            cohort_id,
            db,
            sample_population,
        ).model_dump(mode="json")


@mcp.tool(
    name="trace_search_tcga_genes",
    title="Search TCGA cohort genes",
    description=(
        "Find valid gene symbols in a TCGA reference cohort before an analysis. "
        "For external datasets, including FU-GBC gallbladder cancer, use "
        "trace_search_dataset_genes with the selected dataset_id instead."
    ),
    annotations=READ_ONLY,
)
def tcga_search_genes(cohort_id: str, query: str = "", limit: int = 25) -> dict[str, Any]:
    from app.main import search_genes

    safe_limit = min(max(limit, 1), 100)
    with SessionLocal() as db:
        return search_genes(cohort_id, db, query, safe_limit).model_dump(mode="json")


@mcp.tool(
    name="trace_resolve_tcga_gene",
    title="Resolve a TCGA gene symbol",
    description=(
        "Resolve a submitted symbol or supported legacy alias in a TCGA reference "
        "cohort. For external data use trace_resolve_dataset_gene with dataset_id."
    ),
    annotations=READ_ONLY,
)
def tcga_resolve_gene(cohort_id: str, query: str) -> dict[str, Any]:
    from app.main import resolve_gene

    with SessionLocal() as db:
        return resolve_gene(cohort_id, db, query)


@mcp.tool(
    name="trace_run_survival_analysis",
    title="Run a survival analysis",
    description=(
        "Use this to submit one gene or RNA signature. Continuous Cox is the "
        "primary estimand; grouped Kaplan-Meier, grouped Cox, RMST, proportional-"
        "hazards diagnostics, and aligned univariable/multivariable forest plots "
        "support interpretation and sensitivity analysis. Without a declared "
        "clinical adjustment, the continuous unadjusted model remains primary; "
        "stage and grade models are sensitivities. An exact requested adjustment "
        "is fixed before fitting. The Cox plot can retain "
        "all evaluable adjusted rows or a declared subset in a new recorded run. "
        "Catalog-declared clinical restrictions, such as one BRCA PAM50 subtype, "
        "can be supplied through filters.custom_filters. A single-gene request "
        "requires exactly one symbol; mean, z-score, weighted, singscore, "
        "ssGSEA and AUCell signatures require at least two distinct genes. "
        "Rank-based methods require a broad expression layer, accept explicit "
        "up/down directions, and are scored on the release's canonical molecular "
        "population before endpoint or clinical filters. If percentile grouping "
        "is selected, custom_percentile is "
        "required from 1 through 99. Ages must remain from 0 through 150, minimum "
        "cannot exceed maximum, and maximum follow-up must be positive."
    ),
    annotations=COMPUTE,
)
def tcga_run_survival_analysis(request: AnalysisRequest, context: Context) -> dict[str, Any]:
    return _submit("analysis", request.model_dump(mode="json"), context)


@mcp.tool(
    name="trace_run_combined_analysis",
    title="Run a combined-signature analysis",
    description=(
        "Use this to evaluate two RNA signatures jointly with continuous Cox "
        "main effects and interaction models, clinical adjustment when requested, "
        "diagnostics, grouped views, and aligned forest-plot outputs. Unadjusted "
        "models remain primary unless the request declares an exact adjustment."
        " Each signature supports the scoring methods documented in the TRACE "
        "methods resource."
    ),
    annotations=COMPUTE,
)
def tcga_run_combined_analysis(
    request: CombinedSignatureAnalysisRequest,
    context: Context,
) -> dict[str, Any]:
    return _submit("combined", request.model_dump(mode="json"), context)


@mcp.tool(
    name="trace_run_signature_panel",
    title="Run a multiple-signature Cox panel",
    description=(
        "Use this to compare 2 to 6 RNA signatures through common-population "
        "univariable, joint and clinically adjusted continuous Cox main-effects "
        "models. The joint unadjusted model remains primary unless the request "
        "declares an exact adjustment. This panel does not fit interactions or "
        "Kaplan-Meier groups. Each signature supports the scoring methods "
        "documented in the TRACE methods resource."
    ),
    annotations=COMPUTE,
)
def tcga_run_signature_panel(
    request: SignaturePanelAnalysisRequest,
    context: Context,
) -> dict[str, Any]:
    return _submit(
        "signature_panel",
        request.model_dump(mode="json"),
        context,
    )


@mcp.tool(
    name="trace_run_gsea_analysis",
    title="Run correlation-aware two-group GSEA",
    description=(
        "Use this to compare frozen, checksum-verified ImmPort or Gene Ontology "
        "BP/MF/CC pathways between two traceable groups. Primary p-values use "
        "limma CAMERA with residual inter-gene correlation estimated separately "
        "for each eligible set; FDR is Benjamini-Hochberg across that family. "
        "Weighted preranked NES and leading-edge genes are retained as descriptive "
        "effect summaries, and their gene-set-permutation p-values are not used or "
        "reported. Results include the CAMERA correlation estimate, CAMERA and NES "
        "directions, their concordance, and DotPlot downloads. Counts of pathways "
        "meeting CAMERA FDR are assigned to groups by CAMERA direction, not by NES. Additional "
        "catalog-declared clinical restrictions can be combined through "
        "filters.custom_filters. Expression-derived groups may use any signature "
        "method documented in the TRACE methods resource."
    ),
    annotations=COMPUTE,
)
def trace_run_gsea_analysis(
    request: GseaAnalysisRequest,
    context: Context,
) -> dict[str, Any]:
    return _submit(
        "gsea",
        request.model_dump(mode="json"),
        context,
    )


@mcp.tool(
    name="trace_run_expression_comparison",
    title="Compare expression between two groups",
    description=(
        "Use this to compare gene expression between two traceable clinical, "
        "survival-derived or expression-derived groups with Welch and "
        "Mann-Whitney tests, effect sizes, method-specific across-gene BH-FDR, "
        "and violin, boxplot, and heatmap downloads. Additional catalog-declared "
        "clinical restrictions can be combined through filters.custom_filters; "
        "do not reuse the grouping variable as a restriction. Expression-derived "
        "groups may use any documented signature method."
    ),
    annotations=COMPUTE,
)
def trace_run_expression_comparison(
    request: ExpressionComparisonRequest,
    context: Context,
) -> dict[str, Any]:
    return _submit(
        "expression_comparison",
        request.model_dump(mode="json"),
        context,
    )


@mcp.tool(
    name="trace_run_robustness_analysis",
    title="Run a prespecified Robustness analysis",
    description=(
        "Use this to submit one declared endpoint-by-scoring-by-cutpoint "
        "specification family. The result keeps separate continuous and grouped "
        "multiplicity families plus the complete execution ledger. If percentile "
        "is selected, custom_percentile must be a number from 1 through 99. "
        "scoring_methods may include the documented Bioconductor rank-based "
        "methods when the dataset capability permits them."
    ),
    annotations=COMPUTE,
)
def trace_run_robustness_analysis(
    request: MultiverseAnalysisRequest,
    context: Context,
) -> dict[str, Any]:
    planned = (
        len(request.endpoints)
        * len(request.scoring_methods)
        * len(request.cutpoint_methods)
    )
    if planned > settings.public_multiverse_max_analyses:
        return {
            "ok": False,
            "error": {
                "code": "MULTIVERSE_TOO_LARGE",
                "message": (
                    "Public Robustness analyses are limited to "
                    f"{settings.public_multiverse_max_analyses} specifications."
                ),
            },
        }
    return _submit(
        "multiverse",
        request.model_dump(mode="json"),
        context,
    )


@mcp.tool(
    name="trace_run_batch_analysis",
    title="Run a bounded analysis batch",
    description=("Use this to compare up to 25 survival-analysis requests in one asynchronous batch. "
                 "The completed result includes grouped_family: selection-corrected maxstat or log-rank p-values, "
                 "BH and Bonferroni across valid grouped tests, and requested/completed/failed/evaluable counts. "
                 "Continuous Cox, grouped Cox and RMST estimates are separate from this correction family."),
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
    name="trace_run_pancancer_analysis",
    title="Run a pan-cancer survival scan",
    description=(
        "Use this to scan one gene or RNA signature across selected TCGA cohorts "
        "with FDR and eligible common-unit meta-analysis. Every multi-gene signature "
        "is scored and audited independently inside each cohort. Mean and weighted "
        "scores can support common-unit synthesis; cohort-standardized Z-score and "
        "rank-based effects remain cohort-level."
    ),
    annotations=COMPUTE,
)
def tcga_run_pancancer_analysis(
    request: PanCancerSurvivalRequest,
    context: Context,
) -> dict[str, Any]:
    return _submit("pancancer", request.model_dump(mode="json"), context)


@mcp.tool(
    name="trace_preflight_hierarchical_pancancer",
    title="Preflight a hierarchical pan-cancer analysis",
    description=(
        "Use this before hierarchical computation to inspect the versioned "
        "study universe, independent clusters, exclusions, information counts, "
        "and cancer-level replication without pooling expression matrices."
    ),
    annotations=READ_ONLY,
)
def trace_preflight_hierarchical_pancancer(
    request: HierarchicalPanCancerRequest,
) -> dict[str, Any]:
    from app.hierarchical_pancancer_service import build_hierarchical_preflight

    try:
        with SessionLocal() as db:
            bundle = build_hierarchical_preflight(request, db, settings)
    except (ValueError, OSError) as exc:
        return {
            "ok": False,
            "error": {
                "code": "HIERARCHICAL_PREFLIGHT_FAILED",
                "message": str(exc),
            },
        }
    return {
        "ok": True,
        "preflight": _compact_hierarchical_preflight(bundle.payload),
        "rest_endpoint": (
            f"{settings.public_base_url.rstrip('/')}"
            "/api/v1/pancancer/hierarchical/preflight"
        ),
    }


@mcp.tool(
    name="trace_run_hierarchical_pancancer_analysis",
    title="Run a hierarchical pan-cancer analysis",
    description=(
        "Use this after reviewing preflight to fit one single-gene, strict-OS, "
        "within-study IQR Cox effect per eligible study and synthesize study to cancer to "
        "a two-stage evidence summary with heterogeneity and modified-HKSJ "
        "intervals. Its replication threshold measures information, not "
        "nominal calibration or a universal effect."
    ),
    annotations=COMPUTE,
)
def trace_run_hierarchical_pancancer_analysis(
    request: HierarchicalPanCancerRequest,
    context: Context,
) -> dict[str, Any]:
    return _submit(
        "pancancer_hierarchical",
        request.worker_payload(),
        context,
    )


@mcp.tool(
    name="trace_get_job",
    title="Get compute job status",
    description="Use this after a compute submission to poll status and retrieve a compact result when completed.",
    annotations=READ_ONLY,
)
def tcga_get_job(job_id: str) -> dict[str, Any]:
    with SessionLocal() as db:
        job = db.get(ComputeJob, job_id)
        if job is None:
            return {"ok": False, "error": {"code": "JOB_NOT_FOUND", "message": "Compute job not found."}}
        try:
            authorize_user_datasets_in_payload(
                db,
                job.request_payload,
                _mcp_dataset_token.get(),
            )
        except UserDatasetError as exc:
            return {
                "ok": False,
                "error": {"code": exc.code, "message": exc.message},
            }
        result = compute_job_out(job, settings).model_dump(mode="json")
    result["result"] = _compact_result(job.kind, result.get("result"))
    return _absolute_links({"ok": True, "job": result})


@mcp.tool(
    name="trace_get_analysis",
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
        if str(analysis.dataset_id or "").startswith("user-"):
            try:
                authorize_user_dataset(
                    db,
                    str(analysis.dataset_id),
                    _mcp_dataset_token.get(),
                )
            except UserDatasetError as exc:
                return {
                    "ok": False,
                    "error": {"code": exc.code, "message": exc.message},
                }
        try:
            _ensure_public_result_retained(
                db,
                analysis_id,
                {"analysis", "combined", "signature_panel"},
            )
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
    name="trace_list_immune_screens",
    title="List immune pan-cancer screens",
    description="Use this to discover precomputed immune pan-cancer screening datasets.",
    annotations=READ_ONLY,
)
def tcga_list_immune_screens() -> dict[str, Any]:
    from app.main import list_immune_pancancer_screens

    return _absolute_links(list_immune_pancancer_screens())


@mcp.tool(
    name="trace_get_immune_screen",
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
    "trace-explorer://dataset/version",
    title="TRACE Explorer dataset version",
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
    "trace-explorer://methods",
    title="TRACE Explorer methods",
    description="Methodological scope, interpretation constraints, and public API links.",
    mime_type="text/markdown",
)
def methods_resource() -> str:
    base = settings.public_base_url.rstrip("/")
    versions = COMPUTE_PIPELINE_VERSIONS
    return (
        "# TRACE Explorer methods\n\n"
        "TRACE Explorer performs exploratory transcriptomic analyses over TCGA, "
        "curated public cohorts and temporary private user datasets. MCP exposes "
        "single- and multi-signature survival analysis, bounded comparison batches, "
        "prespecified Robustness families, two-group targeted expression comparison, "
        "correlation-aware two-group pathway testing against frozen ImmPort or Gene "
        "Ontology BP/MF/CC collections, "
        "the TCGA reference pan-cancer scan, and an opt-in hierarchical study to "
        "cancer to global synthesis. Frozen immune pan-cancer screens are available "
        "as read-only evidence resources. The hierarchical workflow keeps every study as "
        "a separate analytical universe and requires preflight before interpretation. "
        "Its deployed cross-cancer result is a structured two-stage evidence summary; "
        "meeting the replicated-cancer/event threshold does not certify interval "
        "calibration or a universal biological direction. "
        "MCP preflight responses disclose any bounded preview, while the complete REST "
        "preflight remains authoritative. "
        "Temporary private datasets must be uploaded or deleted through the web or "
        "REST API; their patient metadata may include categorical or numeric variables, "
        "and a time-to-event outcome is optional. Inspect the returned capabilities: "
        "Expression Comparison and GSEA can remain available when Survival is not. "
        "Browser-selected session export is also intentionally outside MCP. "
        "For external or private data, discover the release endpoints, expression "
        "layers, filters and resolved genes before constructing a compute request. "
        "Dataset capabilities expose `rank_based_signature_scoring`. Singscore, "
        "ssGSEA and AUCell require that capability and a broad expression layer; "
        "signed components use `GENE:1` and `GENE:-1` or explicit up/down fields. "
        "These methods are scored once on the canonical molecular population before "
        "endpoint or clinical filters, so scores are stable across filters within "
        "the same frozen expression release. They are not assumed comparable across "
        "different feature universes. "
        "For TCGA, the molecular sample population is declared before filtering or "
        "patient-level sample selection. Primary solid tumor, primary blood-derived "
        "disease, metastatic and recurrent tissue are distinct populations; normal "
        "or control tissue never enters prognostic or tumor-group comparisons as a "
        "fallback. TCGA-SKCM requires an explicit primary-versus-metastatic choice, "
        "and TCGA-LAML uses its hematologic primary-disease rule. Sample origin, "
        "clinical extent and prior treatment are independent dimensions; missing "
        "prior-treatment data are unknown, not treatment-naive. "
        "GSEA uses limma CAMERA for two-sided competitive p-values, estimates residual "
        "inter-gene correlation separately for each eligible set, and applies BH "
        "across the tested pathway family. Weighted preranked NES and leading edges "
        "describe effect direction and concentration but do not supply p-values or "
        "FDR. When groups are expression-derived, CAMERA inference is explicitly "
        "conditional and exploratory rather than independent confirmation. "
        "IMmotion150 PFS analyses require exactly one study arm; arms are not pooled. "
        "Diagnostic notices distinguish the primary result, requested adjustment, "
        "auxiliary sensitivities and "
        "provenance. Results are not clinical advice.\n\n"
        "## Current compute contracts\n\n"
        f"- Signature scoring: `{SIGNATURE_SCORING_CONTRACT_VERSION}`\n"
        f"- Survival: `{versions['analysis']}`\n"
        f"- Two signatures: `{versions['combined']}`\n"
        f"- Signature panel: `{versions['signature_panel']}`\n"
        f"- Robustness: `{versions['multiverse']}`\n"
        f"- GSEA: `{versions['gsea']}`\n"
        f"- Expression comparison: `{versions['expression_comparison']}`\n"
        f"- Pan-cancer · TCGA reference: `{versions['pancancer']}`\n"
        f"- Pan-cancer · hierarchical: `{versions['pancancer_hierarchical']}`\n"
        f"- Frozen immune pan-cancer screens: `{IMMUNE_ATLAS_PIPELINE_VERSION}`\n\n"
        f"- Static signature-scoring contract: {base}/methods/signature-scoring/\n"
        f"- API documentation: {base}/api/docs\n"
        f"- Integration guide: {base}/api/guide\n"
        f"- Web application: {base}/\n"
    )


class MCPClientIdentityMiddleware:
    """Bind anonymous MCP quotas and private access to edge-verified requests."""

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
        authorization = headers.get("authorization", "").strip()
        if authorization.lower().startswith("bearer "):
            dataset_token = authorization[7:].strip()
        else:
            dataset_token = headers.get(
                "x-trace-dataset-token",
                "",
            ).strip()
        if not dataset_token or len(dataset_token) > 256:
            dataset_token = None
        identity = f"mcp-ip:{scope_client_ip(scope)}"

        token = _mcp_client_identity.set(identity)
        dataset_token_context = _mcp_dataset_token.set(dataset_token)
        try:
            await self.app(scope, receive, send)
        finally:
            _mcp_dataset_token.reset(dataset_token_context)
            _mcp_client_identity.reset(token)


def mcp_http_app():
    return MCPClientIdentityMiddleware(mcp.streamable_http_app())
