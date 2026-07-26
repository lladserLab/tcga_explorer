import copy
import json

import pytest

from app.attestation import (
    ATTESTATION_RECEIPT_SCHEMA,
    AttestationError,
    attestation_key_document,
    attestation_keyset,
    attestation_metadata,
    ensure_attestation_key,
    verify_attestation_receipt,
    write_attestation_receipt,
)
from app.config import Settings


@pytest.fixture()
def attestation_settings(tmp_path):
    return Settings(
        _env_file=None,
        public_base_url="https://example.test/tcga-trace",
        artifact_dir=tmp_path / "artifacts",
        attestation_enabled=True,
        attestation_auto_generate=True,
        attestation_private_key_path=(
            tmp_path / "keys" / "ed25519-private.pem"
        ),
    )


def test_generated_key_is_persistent_and_public_document_has_no_secret(
    attestation_settings,
) -> None:
    first = ensure_attestation_key(attestation_settings)
    second = ensure_attestation_key(attestation_settings)

    assert first.key_id == second.key_id
    assert first.fingerprint_sha256 == second.fingerprint_sha256
    assert (
        attestation_settings.attestation_private_key_path.stat().st_mode
        & 0o777
    ) == 0o600

    keyset = attestation_keyset(attestation_settings)
    assert keyset["active_key_id"] == first.key_id
    assert len(keyset["keys"]) == 1
    document = attestation_key_document(
        attestation_settings,
        first.key_id,
    )
    serialized = json.dumps(document)
    assert document["algorithm"] == "Ed25519"
    assert document["fingerprint_sha256"] == first.fingerprint_sha256
    assert "private" not in serialized.lower()


def test_receipt_verifies_exact_audit_and_rejects_mutations(
    attestation_settings,
    tmp_path,
) -> None:
    audit_path = tmp_path / "audit_report.json"
    audit_path.write_text(
        json.dumps(
            {
                "schema_version": "tcga-trace-analysis-audit-v4",
                "report_type": "survival_analysis_audit",
                "reproducibility_hash": "a" * 64,
                "results": {"hazard_ratio": 1.25},
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    receipt_summary = write_attestation_receipt(
        attestation_settings,
        subject_type="survival_analysis",
        subject_id="analysis-1",
        audit_path=audit_path,
        reproducibility_hash="a" * 64,
        report_schema_version="tcga-trace-analysis-audit-v4",
    )
    assert "receipt_path" not in receipt_summary
    assert "/tmp/" not in json.dumps(receipt_summary)
    receipt_path = tmp_path / "attestation_receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    key = attestation_key_document(
        attestation_settings,
        receipt_summary["key_id"],
    )

    verified = verify_attestation_receipt(
        receipt,
        key,
        audit_bytes=audit_path.read_bytes(),
    )
    assert receipt["schema_version"] == ATTESTATION_RECEIPT_SCHEMA
    assert verified["status"] == "passed"

    mutated_audit = audit_path.read_bytes().replace(b"1.25", b"9.25")
    audit_failure = verify_attestation_receipt(
        receipt,
        key,
        audit_bytes=mutated_audit,
    )
    assert audit_failure["status"] == "failed"
    assert next(
        check
        for check in audit_failure["checks"]
        if check["name"] == "audit_report_sha256"
    )["passed"] is False

    mutated_receipt = copy.deepcopy(receipt)
    mutated_receipt["payload"]["subject"]["id"] = "analysis-2"
    signature_failure = verify_attestation_receipt(
        mutated_receipt,
        key,
        audit_bytes=audit_path.read_bytes(),
    )
    assert signature_failure["status"] == "failed"
    assert next(
        check
        for check in signature_failure["checks"]
        if check["name"] == "ed25519_signature"
    )["passed"] is False


def test_metadata_declares_https_key_and_receipt_locations(
    attestation_settings,
) -> None:
    metadata = attestation_metadata(
        attestation_settings,
        subject_type="prespecified_multiverse",
        subject_id="mv-1",
    )

    assert metadata["algorithm"] == "Ed25519"
    assert metadata["public_key_url"].startswith(
        "https://example.test/tcga-trace/api/v1/attestation/keys/"
    )
    assert metadata["receipt_url"].endswith(
        "/api/v1/analyses/multiverses/mv-1/download/attestation"
    )
    assert "scientific correctness" in metadata["trust_model"]


def test_revoked_key_remains_discoverable_but_fails_trust_check(
    attestation_settings,
    tmp_path,
) -> None:
    active = ensure_attestation_key(attestation_settings)
    audit_path = tmp_path / "audit_report.json"
    audit_path.write_text(
        json.dumps(
            {
                "schema_version": "tcga-trace-analysis-audit-v4",
                "report_type": "survival_analysis_audit",
                "reproducibility_hash": "b" * 64,
            }
        ),
        encoding="utf-8",
    )
    summary = write_attestation_receipt(
        attestation_settings,
        subject_type="survival_analysis",
        subject_id="analysis-revoked",
        audit_path=audit_path,
        reproducibility_hash="b" * 64,
        report_schema_version="tcga-trace-analysis-audit-v4",
    )
    receipt = json.loads(
        (tmp_path / "attestation_receipt.json").read_text(encoding="utf-8")
    )
    key_document = attestation_key_document(
        attestation_settings,
        summary["key_id"],
    )
    key_document["status"] = "revoked"

    result = verify_attestation_receipt(
        receipt,
        key_document,
        audit_bytes=audit_path.read_bytes(),
    )

    assert summary["key_id"] == active.key_id
    assert result["status"] == "failed"
    key_status = next(
        check for check in result["checks"] if check["name"] == "key_status"
    )
    assert key_status["passed"] is False


def test_disabled_attestation_fails_closed(tmp_path) -> None:
    settings = Settings(
        _env_file=None,
        attestation_enabled=False,
        attestation_private_key_path=tmp_path / "key.pem",
    )

    with pytest.raises(AttestationError, match="disabled"):
        ensure_attestation_key(settings)
