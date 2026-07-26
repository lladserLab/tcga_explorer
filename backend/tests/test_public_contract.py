import asyncio
import json

import httpx

from app.main import app, application_release_identity, settings
from app.mcp_server import mcp, tcga_get_immune_screen


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


def test_openapi_contains_only_stable_public_v1_routes():
    schema = app.openapi()
    paths = schema["paths"]

    assert len(paths) == 36
    assert all(path.startswith("/api/v1/") for path in paths)
    assert "/api/v1/" in paths
    assert "/api/v1/analyses" in paths
    assert "/api/v1/analyses/multiverse" in paths
    assert "/api/v1/analyses/multiverses/{session_id}" in paths
    assert "/api/v1/analyses/multiverses/{session_id}/download/{kind}" in paths
    assert "/api/v1/analyses/sessions/export" in paths
    assert "/api/v1/analyses/sessions/{report_id}" in paths
    assert "/api/v1/analyses/sessions/{report_id}/download/{kind}" in paths
    assert "/api/v1/examples/paper" in paths
    assert "/api/v1/examples/paper/figures/{analysis_id}/{kind}" in paths
    assert "/api/v1/pancancer/survival/{scan_id}/download/{kind}" in paths
    assert "/api/v1/attestation/keys" in paths
    assert "/api/v1/attestation/keys/{key_id}" in paths
    assert paths["/api/v1/analyses"]["post"]["responses"]["202"]
    assert paths["/api/v1/analyses/multiverse"]["post"]["responses"]["202"]
    assert paths["/api/v1/analyses/sessions/export"]["post"]["responses"]["202"]
    assert "/api/cache/status" not in paths
    assert schema["info"]["x-artifact-retention-days"] == 90
    public_health = schema["components"]["schemas"]["PublicHealthOut"]
    assert "release" in public_health["required"]
    assert app.docs_url == "/api/docs"
    assert app.redoc_url == "/api/redoc"
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
    assert payload["links"]["swagger_ui"].endswith("/tcga_explorer/api/docs")
    assert payload["links"]["attestation_keys"].endswith(
        "/tcga_explorer/api/v1/attestation/keys"
    )


def test_mcp_catalog_has_all_public_scientific_tools():
    tools = asyncio.run(mcp.list_tools())
    by_name = {tool.name: tool for tool in tools}

    assert len(by_name) == 16
    assert {
        "tcga_list_cohorts",
        "tcga_search_genes",
        "tcga_run_survival_analysis",
        "tcga_run_combined_analysis",
        "tcga_run_batch_analysis",
        "tcga_run_pancancer_analysis",
        "tcga_get_job",
        "tcga_get_analysis",
    }.issubset(by_name)
    assert by_name["tcga_list_cohorts"].annotations.readOnlyHint is True
    assert by_name["tcga_run_survival_analysis"].annotations.destructiveHint is False
    assert by_name["tcga_run_survival_analysis"].annotations.idempotentHint is True


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
    assert payload["result"]["serverInfo"]["name"] == "TCGA-TRACE"


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
