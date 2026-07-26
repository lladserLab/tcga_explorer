import importlib.util
import json
from pathlib import Path
import sys

import pytest

from app.attestation import (
    attestation_key_document,
    write_attestation_receipt,
)
from app.config import Settings


MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "run_server_attestation_benchmark.py"
)
SPEC = importlib.util.spec_from_file_location(
    "run_server_attestation_benchmark",
    MODULE_PATH,
)
assert SPEC is not None
benchmark = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = benchmark
assert SPEC.loader is not None
SPEC.loader.exec_module(benchmark)


def build_inputs(tmp_path):
    settings = Settings(
        _env_file=None,
        public_base_url="https://example.test/tcga-trace",
        artifact_dir=tmp_path / "artifacts",
        attestation_private_key_path=tmp_path / "keys" / "private.pem",
    )
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    audit_path = bundle / "audit_report.json"
    audit_path.write_text(
        json.dumps(
            {
                "schema_version": "tcga-trace-analysis-audit-v4",
                "analysis_id": "analysis-1",
                "generated_at": "2026-07-26T00:00:00+00:00",
                "reproducibility_hash": "a" * 64,
                "results": {"hazard_ratio": 1.25},
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    summary = write_attestation_receipt(
        settings,
        subject_type="survival_analysis",
        subject_id="analysis-1",
        audit_path=audit_path,
        reproducibility_hash="a" * 64,
        report_schema_version="tcga-trace-analysis-audit-v4",
    )
    key_bytes = json.dumps(
        attestation_key_document(settings, summary["key_id"]),
        indent=2,
    ).encode("utf-8")
    return (
        audit_path.read_bytes(),
        (bundle / "attestation_receipt.json").read_bytes(),
        key_bytes,
    )


def test_benchmark_proves_signature_boundary_and_freezes_evidence(
    tmp_path,
) -> None:
    audit_bytes, receipt_bytes, key_bytes = build_inputs(tmp_path)
    evidence = benchmark.build_evidence(
        audit_bytes=audit_bytes,
        receipt_bytes=receipt_bytes,
        key_bytes=key_bytes,
    )

    assert evidence["status"] == "passed"
    assert all(evidence["acceptance_assertions"].values())
    recomputed = evidence["verification"]["recomputed_unsigned_fields"]
    assert recomputed["status"] == "failed"
    signature = next(
        item
        for item in recomputed["checks"]
        if item["name"] == "ed25519_signature"
    )
    assert signature["passed"] is False

    output_dir = tmp_path / "evidence"
    benchmark.write_evidence(
        output_dir,
        audit_bytes=audit_bytes,
        receipt_bytes=receipt_bytes,
        key_bytes=key_bytes,
        evidence=evidence,
    )
    benchmark.check_frozen_evidence(output_dir)
    assert "private" not in (
        output_dir / benchmark.KEY_FILENAME
    ).read_text(encoding="utf-8").lower()


def test_frozen_evidence_gate_rejects_changed_result(tmp_path) -> None:
    audit_bytes, receipt_bytes, key_bytes = build_inputs(tmp_path)
    evidence = benchmark.build_evidence(
        audit_bytes=audit_bytes,
        receipt_bytes=receipt_bytes,
        key_bytes=key_bytes,
    )
    output_dir = tmp_path / "evidence"
    benchmark.write_evidence(
        output_dir,
        audit_bytes=audit_bytes,
        receipt_bytes=receipt_bytes,
        key_bytes=key_bytes,
        evidence=evidence,
    )
    result_path = output_dir / benchmark.RESULT_FILENAME
    changed = json.loads(result_path.read_text(encoding="utf-8"))
    changed["status"] = "changed"
    result_path.write_text(json.dumps(changed), encoding="utf-8")

    with pytest.raises(RuntimeError, match="does not match"):
        benchmark.check_frozen_evidence(output_dir)
