import asyncio
import json
from types import SimpleNamespace

import httpx
import pytest

import app.mcp_server as mcp_module
from app.main import analysis_out, app, application_release_identity, settings
from app.mcp_server import (
    _compact_hierarchical_preflight,
    _compact_result,
    mcp,
    methods_resource,
    tcga_get_immune_screen,
    trace_get_dataset_endpoints,
    trace_get_dataset_filter_options,
    trace_list_dataset_expression_layers,
    trace_resolve_dataset_gene,
    trace_run_hierarchical_pancancer_analysis,
    trace_run_robustness_analysis,
)
from app.models import AnalysisJob
from app.pipeline_versions import COMPUTE_PIPELINE_VERSIONS
from app.schemas import HierarchicalPanCancerRequest, MultiverseAnalysisRequest


IMMUNE_SCREEN_ID = "immune_contract_fixture"


def write_immune_screen_fixture(artifact_dir):
    screen_dir = artifact_dir / "immune_pancancer" / IMMUNE_SCREEN_ID
    screen_dir.mkdir(parents=True)
    summary = {
        "screen_id": IMMUNE_SCREEN_ID,
        "created_at": "2026-07-25T00:00:00Z",
        "pipeline_version": "test",
        "data_version": {"fixture": "contract"},
        "headline": {"immune_genes": 7},
        "clinical_sensitivity": {
            "available": True,
            "selection_hierarchy": ["stage_grade_adjusted"],
            "summary": {"retained": 1},
            "notes": [],
        },
        "model_views": {
            "primary": {
                "model": "primary",
                "label": "Primary continuous expression",
                "role": "primary_estimand",
                "headline": {"completed_models": 1},
                "direction_counts_global_fdr": {"harmful": 1},
                "recurrence": {"summary": {"genes_ge5": 1}},
                "top_genes": [
                    {
                        "gene_symbol": "BIRC5",
                        "global_fdr_hits": 3,
                        "meta_fdr": 0.01,
                        "term_links": ["/app/private/terms.tsv"],
                    }
                ],
            }
        },
        "audit": {
            "path": "/app/private/audit_report.json",
            "analysis_hash": "fixture-hash",
        },
        "paths": {"root": "/app/private"},
        "method_notes": ["Synthetic contract fixture."],
    }
    (screen_dir / "screen_summary.json").write_text(
        json.dumps(summary),
        encoding="utf-8",
    )
    (screen_dir / "audit_report.json").write_text(
        json.dumps({"analysis_hash": "fixture-hash"}),
        encoding="utf-8",
    )


def test_application_release_identity_is_explicit_and_trimmed(monkeypatch):
    monkeypatch.setattr(settings, "app_release_commit", "  abc123  ")
    monkeypatch.setattr(settings, "app_release_ref", "  v1.2.3  ")

    assert application_release_identity() == {
        "commit": "abc123",
        "ref": "v1.2.3",
    }


def test_analysis_result_exposes_separate_cox_downloads(
    monkeypatch,
    tmp_path,
):
    analysis_id = "split-cox-fixture"
    analysis_dir = tmp_path / analysis_id
    analysis_dir.mkdir()
    (analysis_dir / "cox_univariable.png").write_bytes(b"png")
    (analysis_dir / "cox_multivariable.png").write_bytes(b"png")
    monkeypatch.setattr(settings, "artifact_dir", tmp_path)
    job = AnalysisJob(
        id=analysis_id,
        params_hash="split-cox-hash",
        status="completed",
        cohort="TCGA-LIHC",
        dataset_id=None,
        dataset_release_id=None,
        gene_symbol="CDC20",
        cutpoint_method="median",
        request_payload={"expression_scale": "log2_tpm"},
        metrics={},
        warnings=[],
        png_path=str(analysis_dir / "plot.png"),
        svg_path=None,
        csv_path=str(analysis_dir / "raw_data.csv"),
        json_path=str(analysis_dir / "metrics.json"),
        error=None,
        cached=False,
    )

    downloads = analysis_out(job).downloads

    assert downloads["cox_univariable_png"].endswith(
        "/download/cox_univariable_png"
    )
    assert downloads["cox_univariable_svg"].endswith(
        "/download/cox_univariable_svg"
    )
    assert downloads["cox_multivariable_png"].endswith(
        "/download/cox_multivariable_png"
    )
    assert downloads["cox_multivariable_svg"].endswith(
        "/download/cox_multivariable_svg"
    )


def test_openapi_contains_only_stable_public_v1_routes():
    schema = app.openapi()
    paths = schema["paths"]

    assert len(paths) == 68
    assert all(path.startswith("/api/v1/") for path in paths)
    assert "/api/v1/" in paths
    assert "/api/v1/analyses" in paths
    assert "/api/v1/analyses/signature-panel" in paths
    assert "/api/v1/analyses/multiverse" in paths
    assert "/api/v1/analyses/multiverses/{session_id}" in paths
    assert "/api/v1/analyses/multiverses/{session_id}/download/{kind}" in paths
    assert "/api/v1/analyses/sessions/export" in paths
    assert "/api/v1/analyses/sessions/{report_id}" in paths
    assert "/api/v1/analyses/sessions/{report_id}/download/{kind}" in paths
    assert "/api/v1/gsea/collections" in paths
    assert "/api/v1/analyses/gsea" in paths
    assert "/api/v1/analyses/gsea/{gsea_id}" in paths
    assert "/api/v1/analyses/gsea/{gsea_id}/download/{kind}" in paths
    assert "/api/v1/analyses/expression-comparisons" in paths
    assert (
        "/api/v1/analyses/expression-comparisons/{comparison_id}" in paths
    )
    assert (
        "/api/v1/analyses/expression-comparisons/{comparison_id}/download/{kind}"
        in paths
    )
    assert "/api/v1/examples/paper" in paths
    assert "/api/v1/tutorial-assets" in paths
    assert "/api/v1/tutorial-assets/{asset_id}" in paths
    assert "/api/v1/cancer-types" in paths
    assert "/api/v1/datasets" in paths
    assert "/api/v1/dataset-candidates" in paths
    assert "/api/v1/datasets/{dataset_id}" in paths
    assert "/api/v1/datasets/{dataset_id}/endpoints" in paths
    assert "/api/v1/datasets/{dataset_id}/expression-layers" in paths
    assert "/api/v1/datasets/{dataset_id}/filters" in paths
    assert "/api/v1/datasets/{dataset_id}/genes" in paths
    assert "/api/v1/datasets/{dataset_id}/genes/resolve" in paths
    assert "/api/v1/datasets/{dataset_id}/download/{kind}" in paths
    assert "/api/v1/user-datasets/template" in paths
    assert "/api/v1/user-datasets" in paths
    assert "/api/v1/user-datasets/{dataset_id}" in paths
    assert "/api/v1/user-datasets/{dataset_id}/endpoints" in paths
    assert "/api/v1/user-datasets/{dataset_id}/expression-layers" in paths
    assert "/api/v1/user-datasets/{dataset_id}/filters" in paths
    assert "/api/v1/user-datasets/{dataset_id}/genes" in paths
    assert "/api/v1/user-datasets/{dataset_id}/genes/resolve" in paths
    assert "/api/v1/examples/paper/figures/{analysis_id}/{kind}" in paths
    assert "/api/v1/pancancer/survival/{scan_id}/download/{kind}" in paths
    assert "/api/v1/pancancer/hierarchical/preflight" in paths
    assert "/api/v1/pancancer/hierarchical-survival" in paths
    assert "/api/v1/pancancer/hierarchical-survival/{scan_id}" in paths
    assert (
        "/api/v1/pancancer/hierarchical-survival/{scan_id}/download/{kind}"
        in paths
    )
    assert paths["/api/v1/pancancer/hierarchical-survival"]["post"][
        "responses"
    ]["202"]
    assert "/api/v1/attestation/keys" in paths
    assert "/api/v1/attestation/keys/{key_id}" in paths
    assert paths["/api/v1/analyses"]["post"]["responses"]["202"]
    assert paths["/api/v1/analyses/multiverse"]["post"]["responses"]["202"]
    assert paths["/api/v1/analyses/sessions/export"]["post"]["responses"]["202"]
    assert paths["/api/v1/analyses/gsea"]["post"]["responses"]["202"]
    assert paths["/api/v1/analyses/expression-comparisons"]["post"]["responses"]["202"]
    assert "/api/cache/status" not in paths
    assert schema["info"]["x-artifact-retention-days"] == 90
    public_health = schema["components"]["schemas"]["PublicHealthOut"]
    assert "release" in public_health["required"]
    assert "external_repository" in public_health["required"]
    assert app.docs_url is None  # Custom same-origin, CSP-compatible viewers.
    assert app.redoc_url is None
    assert {"/api/docs", "/api/redoc"} <= {getattr(route, "path", None) for route in app.routes}
    assert app.openapi_url == "/api/openapi.json"
    assert app.root_path == "/tcga_explorer"


def test_public_api_index_exposes_discovery_links():
    async def fetch_index():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.get("/api/v1/")

    response = asyncio.run(fetch_index())
    payload = response.json()

    assert response.status_code == 200
    assert payload["api_version"] == "v1"
    assert payload["status"] == "available"
    assert payload["links"]["health"].endswith("/tcga_explorer/api/v1/health")
    assert payload["links"]["cancer_repository"].endswith(
        "/tcga_explorer/api/v1/cancer-types"
    )
    assert payload["links"]["swagger_ui"].endswith("/tcga_explorer/api/docs")
    assert payload["links"]["attestation_keys"].endswith(
        "/tcga_explorer/api/v1/attestation/keys"
    )


def test_public_validation_error_names_the_setting_that_needs_review():
    async def submit_invalid_robustness():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.post(
                "/api/v1/analyses/multiverse",
                json={
                    "cohort": "TCGA-BRCA",
                    "genes": [{"gene_symbol": "ESR1", "weight": 1}],
                    "endpoints": ["OS"],
                    "scoring_methods": ["single"],
                    "cutpoint_methods": ["percentile"],
                    "custom_percentile": 0,
                    "filters": {"sample_population": "primary_disease"},
                },
            )

    response = asyncio.run(submit_invalid_robustness())
    payload = response.json()["error"]

    assert response.status_code == 422
    assert payload["code"] == "VALIDATION_ERROR"
    assert "custom percentile" in payload["message"].lower()
    assert "documented API contract" not in payload["message"]
    assert payload["details"]["errors"][0]["loc"][-1] == "custom_percentile"
    assert "input" not in payload["details"]["errors"][0]


@pytest.mark.parametrize(
    ("filters", "expected_field"),
    [
        (
            {"sample_population": "primary_disease", "max_time_days": 0},
            "max_time_days",
        ),
        (
            {
                "sample_population": "primary_disease",
                "age_min": 80,
                "age_max": 40,
            },
            "filters",
        ),
    ],
)
def test_public_analysis_rejects_invalid_scientific_ranges(
    filters,
    expected_field,
):
    async def submit_invalid_range():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.post(
                "/api/v1/analyses",
                json={
                    "cohort": "TCGA-BRCA",
                    "gene_symbol": "ESR1",
                    "filters": filters,
                },
            )

    response = asyncio.run(submit_invalid_range())
    errors = response.json()["error"]["details"]["errors"]

    assert response.status_code == 422
    assert any(
        expected_field in [str(part) for part in item["loc"]]
        for item in errors
    )


def test_public_analysis_requires_percentile_value_when_selected():
    async def submit_missing_percentile():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.post(
                "/api/v1/analyses",
                json={
                    "cohort": "TCGA-BRCA",
                    "gene_symbol": "ESR1",
                    "cutpoint_method": "percentile",
                    "custom_percentile": None,
                    "filters": {"sample_population": "primary_disease"},
                },
            )

    response = asyncio.run(submit_missing_percentile())

    assert response.status_code == 422
    assert "custom_percentile" in response.json()["error"]["message"]


def test_mcp_catalog_exposes_the_declared_analysis_surface():
    tools = asyncio.run(mcp.list_tools())
    by_name = {tool.name: tool for tool in tools}

    assert len(by_name) == 32
    assert "grouped_family" in by_name["trace_run_batch_analysis"].description
    assert {
        "trace_list_tcga_cohorts",
        "trace_list_cancer_types",
        "trace_list_datasets",
        "trace_list_dataset_candidates",
        "trace_get_dataset",
        "trace_get_dataset_endpoints",
        "trace_get_dataset_filter_options",
        "trace_list_dataset_expression_layers",
        "trace_resolve_dataset_gene",
        "trace_search_dataset_genes",
        "trace_search_tcga_genes",
        "trace_list_gsea_collections",
        "trace_run_survival_analysis",
        "trace_run_combined_analysis",
        "trace_run_signature_panel",
        "trace_run_gsea_analysis",
        "trace_run_expression_comparison",
        "trace_run_robustness_analysis",
        "trace_run_batch_analysis",
        "trace_run_pancancer_analysis",
        "trace_preflight_hierarchical_pancancer",
        "trace_run_hierarchical_pancancer_analysis",
        "trace_get_job",
        "trace_get_analysis",
    }.issubset(by_name)
    assert "trace_export_session" not in by_name
    assert "trace_upload_user_dataset" not in by_name
    assert "trace_delete_user_dataset" not in by_name
    assert by_name["trace_list_tcga_cohorts"].annotations.readOnlyHint is True
    assert by_name["trace_get_dataset"].annotations.readOnlyHint is True
    assert by_name[
        "trace_get_dataset_filter_options"
    ].annotations.readOnlyHint is True
    assert by_name[
        "trace_get_dataset_endpoints"
    ].annotations.readOnlyHint is True
    assert by_name[
        "trace_list_dataset_expression_layers"
    ].annotations.readOnlyHint is True
    assert by_name[
        "trace_resolve_dataset_gene"
    ].annotations.readOnlyHint is True
    assert by_name[
        "trace_preflight_hierarchical_pancancer"
    ].annotations.readOnlyHint is True
    assert by_name["trace_run_survival_analysis"].annotations.destructiveHint is False
    assert by_name["trace_run_survival_analysis"].annotations.idempotentHint is True
    cox_schema = by_name["trace_run_survival_analysis"].inputSchema["$defs"][
        "CoxForestPlotStyle"
    ]["properties"]
    assert cox_schema["multivariable_display"]["enum"] == ["all", "selected"]
    assert cox_schema["multivariable_model_ids"]["items"]["enum"] == [
        "stage_adjusted",
        "grade_adjusted",
        "stage_grade_adjusted",
        "user_adjusted",
    ]
    clinical_filter_schema = by_name[
        "trace_run_expression_comparison"
    ].inputSchema["$defs"]["AnalysisFilters"]["properties"]["custom_filters"]
    assert clinical_filter_schema["maxItems"] == 10
    assert "different variables use AND" in clinical_filter_schema["description"]
    assert "filters.custom_filters" in by_name[
        "trace_run_expression_comparison"
    ].description
    assert "filters.custom_filters" in by_name[
        "trace_run_gsea_analysis"
    ].description
    assert by_name[
        "trace_run_robustness_analysis"
    ].annotations.idempotentHint is True
    assert by_name[
        "trace_run_hierarchical_pancancer_analysis"
    ].annotations.idempotentHint is True


def test_mcp_gsea_result_is_compact_and_keeps_multiple_testing_context():
    compact = _compact_result(
        "gsea",
        {
            "schema_version": "tcga-trace-camera-preranked-gsea-result-v2",
            "gsea_id": "gsea-fixture",
            "status": "completed",
            "cohort": "TCGA-LUAD",
            "grouping": {"group_counts": {"Low": 20, "High": 20}},
            "gene_set_collection": {"id": "immport", "sha256": "abc"},
            "ranking": {"metric": "welch_t", "seed": 17291},
            "inference": {
                "primary_method": "limma_camera",
                "inter_gene_correlation": "estimated_per_gene_set",
            },
            "summary": {"pathways_tested": 153, "fdr_threshold": 0.25},
            "pathways": [
                {"pathway": f"PATH-{index}", "fdr": index / 100}
                for index in range(25)
            ],
            "audit": {"result_core_sha256": "fixture-hash"},
            "downloads": {"zip": "/api/v1/fixture.zip"},
        },
    )

    assert compact["gsea_id"] == "gsea-fixture"
    assert compact["schema_version"] == (
        "tcga-trace-camera-preranked-gsea-result-v2"
    )
    assert compact["inference"]["primary_method"] == "limma_camera"
    assert compact["summary"]["pathways_tested"] == 153
    assert len(compact["top_pathways"]) == 20
    assert compact["audit"]["result_core_sha256"] == "fixture-hash"

    legacy = _compact_result(
        "gsea",
        {
            "schema_version": "tcga-trace-preranked-gsea-result-v1",
            "gsea_id": "gsea-v1-fixture",
            "status": "completed",
            "pathways": [],
        },
    )
    assert legacy["schema_version"] == "tcga-trace-preranked-gsea-result-v1"
    assert legacy["inference"] is None


def test_mcp_survival_result_keeps_forest_plot_layout_metadata():
    compact = _compact_result(
        "analysis",
        {
            "id": "analysis-fixture",
            "status": "completed",
            "cohort": "TCGA-LIHC",
            "metrics": {
                "cox_forest_output": {
                    "model_layout": "separate",
                    "shared_axis_across_model_families": True,
                    "shared_log10_axis_limits": [-1.0, 1.0],
                }
            },
        },
    )

    assert compact["metrics"]["cox_forest_output"]["model_layout"] == "separate"
    assert compact["metrics"]["cox_forest_output"][
        "shared_axis_across_model_families"
    ] is True


def test_mcp_survival_keeps_continuous_effect_distinct_from_grouped_and_study():
    source = {
        "id": "external-survival", "cohort": "TCGA-LUAD",
        "dataset_id": "external-luad", "dataset_release_id": "external-release",
        "expression_scale": "log2_tpm", "expression_scale_label": "log2(TPM + 1)",
        "metrics": {
            "hazard_ratio": 2.1,
            "group_counts": {"Low": 104, "High": 103},
            "dataset": {"kind": "external", "name": "External lung cohort"},
            "continuous_analysis": {
                "status": "completed", "n_patients": 207, "n_events": 57,
                "predictor": {"effect_unit": "hazard ratio per +1 SD expression"},
                "linear_models": [{
                    "model": "continuous_univariable", "hazard_ratio": 1.7,
                    "hr_conf_low": 1.3, "hr_conf_high": 2.2,
                    "n_patients": 207, "n_events": 57, "ph_p_value": 0.97,
                }],
                "spline": {"overall_p_value": 0.002, "nonlinearity_p_value": 0.4,
                           "profile": [{"x": i} for i in range(1000)]},
            },
        },
    }
    compact = _compact_result("analysis", source)
    continuous = compact["metrics"]["continuous_analysis"]
    assert compact["dataset_id"] == "external-luad"
    assert compact["dataset_release_id"] == "external-release"
    assert compact["expression_scale"] == "log2_tpm"
    assert compact["metrics"]["dataset"]["kind"] == "external"
    assert compact["metrics"]["hazard_ratio"] == 2.1
    assert continuous["linear_models"][0]["hazard_ratio"] == 1.7
    assert continuous["predictor"]["effect_unit"] == "hazard ratio per +1 SD expression"
    assert continuous["linear_models"][0]["ph_p_value"] == 0.97
    assert continuous["spline"] == {"overall_p_value": 0.002, "nonlinearity_p_value": 0.4}
    assert len(source["metrics"]["continuous_analysis"]["spline"]["profile"]) == 1000


def test_mcp_combined_keeps_fitted_interaction_when_single_marker_path_is_skipped():
    fitted = [{"model": "signature_interaction_unadjusted", "status": "completed",
               "n_patients": 504, "n_events": 182,
               "marker_terms": [{"term": "signature_a:signature_b", "hazard_ratio": 0.96}]}]
    definitions = {"signature_a": {"name": "BIRC5"},
                   "signature_b": {"name": "Proliferation program"}}
    compact = _compact_result("combined", {"metrics": {
        "continuous_analysis": {"status": "skipped", "reason": "Single-marker path not used"},
        "combined_signature": definitions, "signature_interaction_cox_models": fitted,
    }})
    assert compact["metrics"]["signature_interaction_cox_models"] == fitted
    assert compact["metrics"]["combined_signature"] == definitions
    assert compact["metrics"]["continuous_analysis"]["status"] == "skipped"


def test_mcp_expression_comparison_is_bounded_and_keeps_across_gene_fdr():
    compact = _compact_result(
        "expression_comparison",
        {
            "comparison_id": "exprcmp-fixture",
            "status": "completed",
            "cohort": "TCGA-LUAD",
            "grouping": {"group_counts": {"Low": 20, "High": 20}},
            "summary": {"genes_tested": 25, "fdr_threshold": 0.05},
            "statistics": [
                {
                    "gene_symbol": f"GENE-{index}",
                    "welch_t": {"fdr": index / 100},
                    "mann_whitney": {"fdr": index / 100},
                }
                for index in range(25)
            ],
            "audit": {"result_core_sha256": "fixture-hash"},
            "downloads": {"zip": "/api/v1/fixture.zip"},
        },
    )

    assert compact["comparison_id"] == "exprcmp-fixture"
    assert compact["summary"]["genes_tested"] == 25
    assert len(compact["top_genes"]) == 20
    assert compact["top_genes"][0]["welch_t"]["fdr"] == 0
    assert compact["audit"]["result_core_sha256"] == "fixture-hash"


def test_mcp_robustness_result_keeps_both_families_and_failed_cells():
    compact = _compact_result(
        "multiverse",
        {
            "session_id": "multiverse-fixture",
            "status": "completed_with_failures",
            "pipeline_version": COMPUTE_PIPELINE_VERSIONS["multiverse"],
            "analysis_family": {
                "declared_before_execution": True,
                "primary_continuous_family": {"planned_tests": 25},
                "grouped_sensitivity_family": {"planned_tests": 25},
            },
            "summary": {"planned": 25, "completed": 24, "failed": 1},
            "continuous_references": [
                {
                    "reference_id": f"endpoint-{index}::single",
                    "continuous_bh_q_value": 0.04,
                }
                for index in range(25)
            ],
            "specifications": [
                {
                    "specification_id": f"spec-{index}",
                    "endpoint": "OS",
                    "scoring_method": "single",
                    "cutpoint_method": "maxstat" if index == 1 else "median",
                    "status": "failed" if index == 1 else "completed",
                    "grouped_bh_q_value": 0.08,
                    "analysis_request_hash": "internal-hash",
                    "error_code": "LOW_EVENTS" if index == 1 else None,
                    "error": "Not enough events." if index == 1 else None,
                }
                for index in range(25)
            ],
            "execution_ledger": [
                {
                    "specification_id": f"spec-{index}",
                    "status": "failed" if index == 1 else "completed",
                }
                for index in range(25)
            ],
            "warnings": ["One planned cell failed."],
            "downloads": {"zip": "/api/v1/multiverse.zip"},
        },
    )

    assert compact["summary"] == {"planned": 25, "completed": 24, "failed": 1}
    continuous = compact["continuous_reference_preview"]
    specifications = compact["specification_preview"]
    ledger = compact["execution_ledger_preview"]
    assert continuous["total"] == 25
    assert continuous["returned"] == 20
    assert continuous["truncated"] is True
    assert specifications["total"] == 25
    assert specifications["returned"] == 20
    assert specifications["truncated"] is True
    assert specifications["items"][0]["grouped_bh_q_value"] == 0.08
    assert specifications["items"][1]["error_code"] == "LOW_EVENTS"
    assert ledger["total"] == 25
    assert ledger["returned"] == 20
    assert ledger["truncated"] is True
    assert "analysis_request_hash" not in specifications["items"][0]


def test_mcp_hierarchical_result_keeps_study_cancer_global_evidence():
    compact = _compact_result(
        "pancancer_hierarchical",
        {
            "scan_id": "pch-fixture",
            "status": "completed",
            "pipeline_version": COMPUTE_PIPELINE_VERSIONS[
                "pancancer_hierarchical"
            ],
            "registry_version": "registry-v1",
            "analysis_mode": "hierarchical",
            "gene_symbol": "TP53",
            "requested_gene_symbol": "P53",
            "resolved_gene_symbol": "TP53",
            "endpoint": "OS",
            "effect_scale": {"id": "within_study_iqr"},
            "summary": {"completed_primary_studies": 2},
            "preflight": {"summary": {"primary_studies": 2}},
            "study_results": [
                {
                    "universe_id": f"study-{index}",
                    "cancer_code": "LUAD",
                    "status": "completed",
                    "hazard_ratio": 1.4,
                    "patient_records": [{"patient_id": "not-for-mcp"}],
                }
                for index in range(25)
            ],
            "cancer_results": [
                {
                    "cancer_code": f"C{index:02d}",
                    "hazard_ratio": 1.3,
                    "fdr": 0.04,
                }
                for index in range(25)
            ],
            "global_result": {"hazard_ratio": 1.2, "i_squared": 35.0},
            "leave_one_out": {
                "studies": [{"omitted": index} for index in range(25)],
                "cancers": [{"omitted": index} for index in range(25)],
            },
            "sensitivities": {},
            "warnings": [],
            "downloads": {"zip": "/api/v1/hierarchical.zip"},
        },
    )

    assert compact["requested_gene_symbol"] == "P53"
    assert compact["resolved_gene_symbol"] == "TP53"
    assert compact["preflight_summary"]["primary_studies"] == 2
    studies = compact["study_result_preview"]
    cancers = compact["cancer_result_preview"]
    assert studies["total"] == 25
    assert studies["returned"] == 20
    assert studies["truncated"] is True
    assert studies["items"][0]["hazard_ratio"] == 1.4
    assert "patient_records" not in studies["items"][0]
    assert cancers["total"] == 25
    assert cancers["returned"] == 20
    assert cancers["truncated"] is True
    assert cancers["items"][0]["fdr"] == 0.04
    assert compact["leave_one_out_preview"]["studies"]["returned"] == 20
    assert compact["leave_one_out_preview"]["studies"]["truncated"] is True
    assert compact["global_result"]["i_squared"] == 35.0
    assert compact["global_result_scope"]["role"] == (
        "deployed_two_stage_evidence_summary"
    )
    assert "not a guarantee" in compact["global_result_scope"][
        "evidence_threshold_meaning"
    ]
    assert "universal" in compact["global_result_scope"]["cannot_conclude"]


def test_mcp_hierarchical_preflight_is_bounded_and_reports_counts():
    preflight = _compact_hierarchical_preflight(
        {
            "schema_version": "tcga-trace-hierarchical-pancancer-preflight-v1",
            "pipeline_version": COMPUTE_PIPELINE_VERSIONS[
                "pancancer_hierarchical"
            ],
            "registry_version": "registry-v1",
            "summary": {
                "selected_universes": 55,
                "primary_studies": 12,
                "excluded_studies": 43,
            },
            "universes": [
                {
                    "universe_id": f"study-{index}",
                    "name": f"Study {index}",
                    "status": "primary" if index < 12 else "excluded",
                    "reasons": [] if index < 12 else [{"code": "LOW_EVENTS"}],
                    "internal_manifest_path": "/not/public",
                }
                for index in range(55)
            ],
            "cancer_groups": [
                {"cancer_code": f"C{index:02d}"} for index in range(25)
            ],
            "warnings": ["Review excluded studies."],
        }
    )

    assert preflight["summary"]["selected_universes"] == 55
    assert preflight["universe_preview"]["total"] == 55
    assert preflight["universe_preview"]["returned"] == 50
    assert preflight["universe_preview"]["truncated"] is True
    assert "internal_manifest_path" not in preflight["universe_preview"]["items"][0]
    assert preflight["cancer_group_preview"]["total"] == 25
    assert preflight["cancer_group_preview"]["returned"] == 20
    assert preflight["cancer_group_preview"]["truncated"] is True


def test_mcp_new_compute_tools_reuse_versioned_request_contracts(monkeypatch):
    submissions = []

    def fake_submit(kind, payload, context=None):
        submissions.append((kind, payload, context))
        return {"ok": True}

    monkeypatch.setattr(mcp_module, "_submit", fake_submit)
    robustness = MultiverseAnalysisRequest(
        cohort="TCGA-LIHC",
        genes=[{"gene_symbol": "CDC20", "weight": 1}],
        endpoints=["OS"],
        scoring_methods=["single"],
        cutpoint_methods=["median"],
    )
    hierarchical = HierarchicalPanCancerRequest(gene_symbol="P53")

    assert trace_run_robustness_analysis(robustness, None) == {"ok": True}
    assert trace_run_hierarchical_pancancer_analysis(
        hierarchical,
        None,
    ) == {"ok": True}
    assert submissions[0][0] == "multiverse"
    assert submissions[0][1]["genes"][0]["gene_symbol"] == "CDC20"
    assert submissions[1][0] == "pancancer_hierarchical"
    assert submissions[1][1]["gene_symbol"] == "P53"


def test_mcp_dataset_filters_support_private_capability_ids(monkeypatch):
    import app.repository.service as repository_service
    import app.user_datasets as user_datasets

    calls = {}

    class DummySession:
        def __enter__(self):
            return "database-session"

        def __exit__(self, exc_type, exc, traceback):
            return False

    context = SimpleNamespace(release=SimpleNamespace(id="user-release-1"))

    def fake_resolve(db, dataset_id, release_id, include_private=False):
        calls["resolve"] = (db, dataset_id, release_id, include_private)
        return context

    monkeypatch.setattr(mcp_module, "SessionLocal", DummySession)
    monkeypatch.setattr(
        mcp_module,
        "authorize_user_dataset",
        lambda db, dataset_id, access_token: calls.setdefault(
            "authorize",
            (db, dataset_id, access_token),
        ),
    )
    monkeypatch.setattr(user_datasets, "get_user_dataset", lambda db, dataset_id: {})
    monkeypatch.setattr(
        repository_service,
        "resolve_repository_context",
        fake_resolve,
    )
    monkeypatch.setattr(
        repository_service,
        "repository_filter_options",
        lambda db, resolved: {
            "clinical_grouping_variables": [
                {"id": "subtype", "levels": [{"value": "Basal"}]}
            ]
        },
    )

    result = trace_get_dataset_filter_options(
        "user-private-fixture",
        "user-release-1",
    )

    assert result["ok"] is True
    assert calls["authorize"][1] == "user-private-fixture"
    assert result["release_id"] == "user-release-1"
    assert result["filter_options"]["clinical_grouping_variables"][0][
        "id"
    ] == "subtype"
    assert calls["resolve"][-1] is True


def test_mcp_dataset_discovery_supports_private_releases(monkeypatch):
    import app.repository.service as repository_service
    import app.user_datasets as user_datasets

    calls = {"authorized": 0}

    class DummySession:
        def __enter__(self):
            return "database-session"

        def __exit__(self, exc_type, exc, traceback):
            return False

    context = SimpleNamespace(release=SimpleNamespace(id="user-release-2"))

    def fake_resolve(db, dataset_id, release_id, include_private=False):
        assert dataset_id == "user-private-fixture"
        assert release_id == "user-release-2"
        assert include_private is True
        return context

    def fake_authorize(db, dataset_id, access_token):
        calls["authorized"] += 1

    monkeypatch.setattr(mcp_module, "SessionLocal", DummySession)
    monkeypatch.setattr(mcp_module, "authorize_user_dataset", fake_authorize)
    monkeypatch.setattr(user_datasets, "get_user_dataset", lambda db, dataset_id: {})
    monkeypatch.setattr(
        repository_service,
        "resolve_repository_context",
        fake_resolve,
    )
    monkeypatch.setattr(
        repository_service,
        "repository_endpoint_options",
        lambda db, resolved: [{"value": "OS", "available": True}],
    )
    monkeypatch.setattr(
        repository_service,
        "repository_expression_layers",
        lambda db, resolved: [{"value": "rna", "is_default": True}],
    )
    monkeypatch.setattr(
        repository_service,
        "repository_gene_expression",
        lambda db, resolved, query, layer_id: (
            {"P1": 1.0},
            SimpleNamespace(layer_id="rna"),
            SimpleNamespace(gene_symbol="TP53"),
        ),
    )

    endpoints = trace_get_dataset_endpoints(
        "user-private-fixture",
        "user-release-2",
    )
    layers = trace_list_dataset_expression_layers(
        "user-private-fixture",
        "user-release-2",
    )
    gene = trace_resolve_dataset_gene(
        "user-private-fixture",
        "P53",
        "user-release-2",
        "rna",
    )

    assert calls["authorized"] == 3
    assert endpoints["endpoints"][0]["value"] == "OS"
    assert layers["expression_layers"][0]["value"] == "rna"
    assert gene["resolved"] == "TP53"
    assert gene["status"] == "alias"
    assert gene["expression_layer_id"] == "rna"


def test_mcp_methods_resource_tracks_current_scientific_scope():
    methods = methods_resource()

    assert "correlation-aware two-group pathway testing" in methods
    assert "Gene Ontology BP/MF/CC" in methods
    assert "limma CAMERA" in methods
    assert "Weighted preranked NES" in methods
    assert "prespecified Robustness" in methods
    assert "hierarchical study to cancer to global synthesis" in methods
    assert "Frozen immune pan-cancer screens" in methods
    assert COMPUTE_PIPELINE_VERSIONS["gsea"] in methods
    assert COMPUTE_PIPELINE_VERSIONS["multiverse"] in methods
    assert COMPUTE_PIPELINE_VERSIONS["pancancer_hierarchical"] in methods
    assert mcp_module.IMMUNE_ATLAS_PIPELINE_VERSION in methods
    assert "uploaded or deleted through the web or REST API" in methods
    assert "molecular sample population is declared" in methods
    assert "missing prior-treatment data are unknown" in methods


def test_streamable_http_mcp_initialize_handshake():
    async def exchange():
        async with mcp.session_manager.run():
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport,
                base_url="http://testserver",
                headers={
                    "Accept": "application/json, text/event-stream",
                    "Content-Type": "application/json",
                },
            ) as client:
                return await client.post(
                    "/mcp",
                    json={
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "initialize",
                        "params": {
                            "protocolVersion": "2025-06-18",
                            "capabilities": {},
                            "clientInfo": {"name": "contract-test", "version": "1.0"},
                        },
                    },
                )

    response = asyncio.run(exchange())
    payload = response.json()

    assert response.status_code == 200
    assert payload["jsonrpc"] == "2.0"
    assert payload["id"] == 1
    assert payload["result"]["serverInfo"]["name"] == "TRACE Explorer"


def test_public_immune_atlas_hides_internal_paths(tmp_path, monkeypatch):
    write_immune_screen_fixture(tmp_path)
    monkeypatch.setattr(settings, "artifact_dir", tmp_path)

    async def fetch_screen():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.get(
                "/api/v1/pancancer/immune-screens/"
                f"{IMMUNE_SCREEN_ID}"
            )

    response = asyncio.run(fetch_screen())
    payload = response.json()

    assert response.status_code == 200
    assert "paths" not in payload
    assert "path" not in payload["audit"]
    assert payload["downloads"]["audit"].startswith(
        "/api/v1/pancancer/immune-screens/"
    )
    assert "/app/" not in response.text


def test_mcp_immune_atlas_is_compact_and_keeps_decision_fields(
    tmp_path,
    monkeypatch,
):
    write_immune_screen_fixture(tmp_path)
    monkeypatch.setattr(settings, "artifact_dir", tmp_path)

    payload = tcga_get_immune_screen(IMMUNE_SCREEN_ID)
    encoded = json.dumps(payload)
    primary_gene = payload["model_views"]["primary"]["top_genes"][0]

    assert len(encoded) < 20_000
    assert payload["headline"]["immune_genes"] == 7
    assert primary_gene["gene_symbol"]
    assert "global_fdr_hits" in primary_gene
    assert "meta_fdr" in primary_gene
    assert "term_links" not in primary_gene
    assert "/app/" not in encoded
