from __future__ import annotations

import importlib.util
import io
import json
import sys
import threading
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest


MODULE_PATH = Path(__file__).resolve().parents[1] / "tcga_trace_cli.py"
SPEC = importlib.util.spec_from_file_location("tcga_trace_cli", MODULE_PATH)
assert SPEC is not None
cli = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = cli
assert SPEC.loader is not None
SPEC.loader.exec_module(cli)


def file_record(path: Path) -> dict:
    return {
        "filename": path.name,
        "bytes": path.stat().st_size,
        "sha256": cli.file_sha256(path),
    }


def make_analysis_package(root: Path) -> Path:
    package = root / "analysis"
    package.mkdir()
    artifact = package / "result.txt"
    artifact.write_text("analysis result\n", encoding="utf-8")
    records = [
        {
            "patient_id": "TCGA-00-0001",
            "sample_barcode": "TCGA-00-0001-01A",
            "expression_value": 1.25,
        }
    ]
    scoring = {"method": "single", "components": [], "score_values": []}
    data = {
        "data_dates": {"rna": "2026-07-25"},
        "provenance": {"source": "test"},
    }
    results = {"n_patients": 1, "n_events": 1}
    request = {"cohort": "TCGA-TEST", "gene_symbol": "GENE1"}
    patient_digest = cli.stable_hash({"records": records})
    scoring_digest = cli.stable_hash(scoring)
    reproducibility = {
        "request": request,
        "data_dates": data["data_dates"],
        "data_provenance": data["provenance"],
        "scoring_provenance_sha256": scoring_digest,
        "record_digest": patient_digest,
        "continuous_record_digest": patient_digest,
        "core_results": results,
    }
    audit = {
        "schema_version": "tcga-trace-analysis-audit-v3",
        "report_type": "survival_analysis_audit",
        "analysis_id": "analysis-test",
        "reproducibility_hash": cli.stable_hash(reproducibility),
        "request": request,
        "data": data,
        "analysis_design": {
            "scoring_provenance": scoring,
            "scoring_provenance_sha256": scoring_digest,
        },
        "cohort_selection": {
            "patient_records": records,
            "patient_records_sha256": patient_digest,
            "continuous_patient_records": records,
            "continuous_patient_records_sha256": patient_digest,
        },
        "results": results,
        "artifacts": {"result": file_record(artifact)},
    }
    (package / "audit_report.json").write_text(
        json.dumps(audit),
        encoding="utf-8",
    )
    return zip_directory(package, root / "analysis.zip")


def make_multiverse_package(root: Path) -> Path:
    package = root / "multiverse"
    package.mkdir()
    request = {
        "cohort": "TCGA-TEST",
        "genes": [{"gene_symbol": "GENE1", "weight": 1}],
    }
    rows = [
        {
            "specification_id": "S001",
            "analysis_request_hash": "a" * 64,
            "analysis_id": "analysis-test",
            "audit_reproducibility_hash": "b" * 64,
            "status": "completed",
        }
    ]
    family_core = {
        "pipeline_version": "multiverse-test-v1",
        "data_version": {"rna": "test"},
        "request": request,
        "specifications": rows,
    }
    result = {
        "session_id": "mv_test",
        "pipeline_version": "multiverse-test-v1",
        "request_snapshot": request,
        "specifications": rows,
    }
    audit = {
        "schema_version": "tcga-trace-multiverse-audit-v1",
        "report_type": "prespecified_multiverse_audit",
        "session_id": "mv_test",
        "data_version": {"rna": "test"},
        "request_sha256": cli.stable_hash(request),
        "family_reproducibility_hash": cli.stable_hash(family_core),
        "child_analysis_count": 1,
    }
    (package / "multiverse_result.json").write_text(
        json.dumps(result),
        encoding="utf-8",
    )
    (package / "audit_report.json").write_text(
        json.dumps(audit),
        encoding="utf-8",
    )
    return zip_directory(package, root / "multiverse.zip")


def make_pancancer_package(root: Path) -> Path:
    package = root / "pancancer"
    package.mkdir()
    artifact = package / "cohort_results.csv"
    artifact.write_text("cohort,status\nTCGA-TEST,completed\n", encoding="utf-8")
    request = {"gene_symbol": "GENE1", "endpoint": "OS"}
    results = {"summary": {"completed": 1}, "cohort_results": []}
    data = {
        "version": {"rna": "test"},
        "patient_records_sha256": "c" * 64,
    }
    payload = {
        "request": request,
        "pipeline_version": "pancancer-test-v1",
        "data_version": data["version"],
        "patient_records_sha256": data["patient_records_sha256"],
        "core_results": results,
    }
    audit = {
        "schema_version": "tcga-explorer-pancancer-audit-v2",
        "report_type": "pancancer_survival_audit",
        "scan_id": "pc_test",
        "reproducibility_hash": cli.stable_hash(payload),
        "request": request,
        "pipeline": {"version": "pancancer-test-v1"},
        "data": data,
        "results": results,
        "artifacts": {"cohort_results": file_record(artifact)},
    }
    (package / "audit_report.json").write_text(
        json.dumps(audit),
        encoding="utf-8",
    )
    return zip_directory(package, root / "pancancer.zip")


def make_session_package(root: Path) -> Path:
    package = root / "session"
    package.mkdir()
    request_snapshot = {
        "browser_session_id": "browser_test",
        "session_label": "Test",
        "entries": [],
    }
    source_jobs = [
        {
            "job_id": "a" * 32,
            "kind": "analysis",
            "status": "completed",
        }
    ]
    result = {
        "report_id": "sh_test",
        "pipeline_version": "session-test-v1",
        "request_snapshot": request_snapshot,
        "analysis_families": {
            "continuous_primary": {"evaluable_tests": 1}
        },
        "hypotheses": [{"hypothesis_id": "C001", "p_value": 0.01}],
        "managed_family_references": [],
        "runs": [{"event_id": "event-001", "captured": True}],
    }
    family_core = {
        "pipeline_version": result["pipeline_version"],
        "request_snapshot": request_snapshot,
        "source_jobs": source_jobs,
        "report_id": result["report_id"],
        "analysis_families": result["analysis_families"],
        "hypotheses": result["hypotheses"],
        "managed_family_references": [],
        "runs": result["runs"],
    }
    audit = {
        "schema_version": "tcga-trace-exploratory-session-audit-v1",
        "report_type": "exploratory_session_audit",
        "report_id": result["report_id"],
        "request_sha256": cli.stable_hash(request_snapshot),
        "family_reproducibility_hash": cli.stable_hash(family_core),
        "source_job_count": 1,
        "source_jobs": source_jobs,
    }
    (package / "session_report.json").write_text(
        json.dumps(result),
        encoding="utf-8",
    )
    (package / "audit_report.json").write_text(
        json.dumps(audit),
        encoding="utf-8",
    )
    return zip_directory(package, root / "session.zip")


def zip_directory(source: Path, target: Path) -> Path:
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(source.iterdir()):
            archive.write(path, arcname=path.name)
    return target


def test_api_base_normalization_and_relative_link_resolution() -> None:
    assert cli.normalize_api_base("https://example.test/tcga_explorer") == (
        "https://example.test/tcga_explorer/api/v1/"
    )
    assert cli.normalize_api_base(
        "https://example.test/tcga_explorer/api/v1/"
    ) == "https://example.test/tcga_explorer/api/v1/"

    client = cli.ApiClient("https://example.test/tcga_explorer")
    assert client.resolve_link("/api/v1/jobs/abc") == (
        "https://example.test/tcga_explorer/api/v1/jobs/abc"
    )
    assert client.service_url("api/openapi.json") == (
        "https://example.test/tcga_explorer/api/openapi.json"
    )
    with pytest.raises(cli.CliError, match="cross-origin"):
        client.resolve_link("https://other.test/file.zip")


@pytest.mark.parametrize(
    ("builder", "expected_type"),
    [
        (make_analysis_package, "survival_analysis_audit"),
        (make_multiverse_package, "prespecified_multiverse_audit"),
        (make_pancancer_package, "pancancer_survival_audit"),
        (make_session_package, "exploratory_session_audit"),
    ],
)
def test_verifier_accepts_all_public_bundle_families(
    tmp_path: Path,
    builder,
    expected_type: str,
) -> None:
    bundle = builder(tmp_path)
    result = cli.verify_targets([bundle])

    assert result["status"] == "passed"
    package = result["targets"][0]["checks"][-1]["detail"]
    assert package["status"] == "passed"
    audit = json.loads(
        zipfile.ZipFile(bundle).read("audit_report.json").decode("utf-8")
    )
    assert audit["report_type"] == expected_type


def test_verifier_rejects_artifact_mutation(tmp_path: Path) -> None:
    bundle = make_analysis_package(tmp_path)
    extracted = tmp_path / "mutated"
    with zipfile.ZipFile(bundle) as archive:
        archive.extractall(extracted)
    (extracted / "result.txt").write_text("changed\n", encoding="utf-8")

    result = cli.verify_targets([extracted])

    assert result["status"] == "failed"
    package = result["targets"][0]["packages"][0]
    failed = [
        item["name"] for item in package["checks"] if not item["passed"]
    ]
    assert "artifact_result_bytes" in failed
    assert "artifact_result_sha256" in failed


def test_verifier_rejects_unsafe_zip_member(tmp_path: Path) -> None:
    bundle = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(bundle, "w") as archive:
        archive.writestr("../outside.txt", "unsafe")

    result = cli.verify_targets([bundle])

    assert result["status"] == "failed"
    assert result["targets"][0]["checks"][-1]["name"] == "zip_member_safety"


class ApiFixture:
    def __init__(self, tmp_path: Path) -> None:
        self.bundles = {
            "analysis": make_analysis_package(tmp_path / "a"),
            "combined": make_analysis_package(tmp_path / "c"),
            "batch": make_analysis_package(tmp_path / "b"),
            "multiverse": make_multiverse_package(tmp_path / "m"),
            "pancancer": make_pancancer_package(tmp_path / "p"),
            "session": make_session_package(tmp_path / "s"),
        }
        self.requests: list[tuple[str, str, dict | None]] = []
        fixture = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, _format: str, *_args) -> None:
                return

            def do_GET(self) -> None:
                fixture.requests.append(("GET", self.path, None))
                if self.path == "/tcga_explorer/api/openapi.json":
                    operations = {
                        operation_id: {
                            "operationId": operation_id,
                            "responses": {"200": {"description": "ok"}},
                        }
                        for operation_id in cli.REQUIRED_OPERATION_IDS
                    }
                    paths = {
                        f"/api/v1/test/{index}": {"get": operation}
                        for index, operation in enumerate(operations.values())
                    }
                    self.send_json(
                        {
                            "openapi": "3.1.0",
                            "info": {
                                "title": "TCGA-TRACE",
                                "version": "test",
                            },
                            "paths": paths,
                        }
                    )
                    return
                if "/download/" in self.path:
                    family = self.path.rsplit("/", 2)[-2]
                    bundle = fixture.bundles[family]
                    body = bundle.read_bytes()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/zip")
                    self.send_header(
                        "Content-Disposition",
                        f'attachment; filename="{family}.zip"',
                    )
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                self.send_json(
                    {
                        "error": {
                            "code": "NOT_FOUND",
                            "message": "Not found.",
                            "details": {},
                        }
                    },
                    status=404,
                )

            def do_POST(self) -> None:
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length) or b"{}")
                fixture.requests.append(("POST", self.path, payload))
                family = next(
                    key
                    for key, path in cli.FAMILY_PATHS.items()
                    if self.path.endswith(f"/api/v1/{path}")
                )
                identifier_key = {
                    "analysis": "id",
                    "combined": "id",
                    "multiverse": "session_id",
                    "pancancer": "scan_id",
                    "session": "report_id",
                }.get(family)
                if family == "batch":
                    result = {
                        "results": [
                            {
                                "status": "completed",
                                "result": {
                                    "id": "analysis-batch",
                                    "downloads": {
                                        "zip": (
                                            "/api/v1/download/batch/zip"
                                        )
                                    },
                                },
                            }
                        ]
                    }
                else:
                    result = {
                        identifier_key: f"{family}-result",
                        "downloads": {
                            "zip": f"/api/v1/download/{family}/zip"
                        },
                    }
                self.send_json(
                    {
                        "id": f"job-{family}",
                        "kind": family,
                        "status": "completed",
                        "cached": False,
                        "result_id": f"{family}-result",
                        "result": result,
                    },
                    status=202,
                )

            def send_json(self, value: dict, status: int = 200) -> None:
                body = json.dumps(value).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(
            target=self.server.serve_forever,
            daemon=True,
        )
        self.thread.start()

    @property
    def base_url(self) -> str:
        host, port = self.server.server_address
        return f"http://{host}:{port}/tcga_explorer/"

    def close(self) -> None:
        self.server.shutdown()
        self.thread.join(timeout=5)
        self.server.server_close()


@pytest.mark.parametrize("family", tuple(cli.FAMILY_PATHS))
def test_run_submits_polls_downloads_and_verifies_every_family(
    tmp_path: Path,
    family: str,
) -> None:
    fixture_root = tmp_path / "fixture"
    for name in ("a", "b", "c", "m", "p", "s"):
        (fixture_root / name).mkdir(parents=True)
    fixture = ApiFixture(fixture_root)
    request_path = tmp_path / f"{family}.json"
    request_path.write_text(
        json.dumps({"test_family": family}),
        encoding="utf-8",
    )
    download_dir = tmp_path / "downloads" / family
    stdout = io.StringIO()
    stderr = io.StringIO()
    try:
        exit_code = cli.main(
            [
                "--base-url",
                fixture.base_url,
                "run",
                family,
                str(request_path),
                "--artifacts",
                "zip",
                "--download-dir",
                str(download_dir),
                "--verify",
                "--poll-interval",
                "0",
            ],
            stdout=stdout,
            stderr=stderr,
        )
    finally:
        fixture.close()

    payload = json.loads(stdout.getvalue())
    assert exit_code == 0
    assert payload["family"] == family
    assert payload["contract"]["status"] == "compatible"
    assert payload["job"]["status"] == "completed"
    assert payload["verification"]["status"] == "passed"
    assert (download_dir / cli.DOWNLOAD_MANIFEST).is_file()
    expected_path = f"/tcga_explorer/api/v1/{cli.FAMILY_PATHS[family]}"
    assert any(
        method == "POST" and path == expected_path
        for method, path, _body in fixture.requests
    )


def test_api_error_is_structured(tmp_path: Path) -> None:
    fixture_root = tmp_path / "fixture"
    for name in ("a", "b", "c", "m", "p", "s"):
        (fixture_root / name).mkdir(parents=True)
    fixture = ApiFixture(fixture_root)
    stderr = io.StringIO()
    try:
        exit_code = cli.main(
            [
                "--base-url",
                fixture.base_url,
                "job",
                "missing",
            ],
            stdout=io.StringIO(),
            stderr=stderr,
        )
    finally:
        fixture.close()

    payload = json.loads(stderr.getvalue())
    assert exit_code == 3
    assert payload["error"]["code"] == "NOT_FOUND"
