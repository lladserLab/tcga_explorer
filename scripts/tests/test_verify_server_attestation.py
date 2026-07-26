import importlib.util
import json
from pathlib import Path
import sys

from app.attestation import (
    attestation_key_document,
    write_attestation_receipt,
)
from app.config import Settings


MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "verify_server_attestation.py"
)
SPEC = importlib.util.spec_from_file_location(
    "verify_server_attestation",
    MODULE_PATH,
)
assert SPEC is not None
verifier = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = verifier
assert SPEC.loader is not None
SPEC.loader.exec_module(verifier)


def test_verifier_accepts_exact_report_and_rejects_mutation(
    tmp_path,
    capsys,
) -> None:
    settings = Settings(
        _env_file=None,
        public_base_url="https://example.test/tcga-trace",
        artifact_dir=tmp_path,
        attestation_private_key_path=tmp_path / "key.pem",
    )
    audit = tmp_path / "audit_report.json"
    audit.write_text(
        json.dumps(
            {
                "schema_version": "tcga-trace-analysis-audit-v4",
                "reproducibility_hash": "b" * 64,
                "results": {"p_value": 0.01},
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    summary = write_attestation_receipt(
        settings,
        subject_type="survival_analysis",
        subject_id="analysis-1",
        audit_path=audit,
        reproducibility_hash="b" * 64,
        report_schema_version="tcga-trace-analysis-audit-v4",
    )
    key = tmp_path / "public_key.json"
    key.write_text(
        json.dumps(
            attestation_key_document(settings, summary["key_id"]),
            indent=2,
        ),
        encoding="utf-8",
    )
    receipt = tmp_path / "attestation_receipt.json"

    assert (
        verifier.main(
            [str(receipt), str(audit), "--key", str(key)]
        )
        == 0
    )
    passed = json.loads(capsys.readouterr().out)
    assert passed["status"] == "passed"

    audit.write_text(
        audit.read_text(encoding="utf-8").replace("0.01", "0.99"),
        encoding="utf-8",
    )
    assert (
        verifier.main(
            [str(receipt), str(audit), "--key", str(key)]
        )
        == 5
    )
    failed = json.loads(capsys.readouterr().out)
    assert failed["status"] == "failed"
