#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = (
    ROOT
    / "docs"
    / "publication"
    / "benchmark"
    / "server_attestation"
)
AUDIT_FILENAME = "audit_report.json"
RECEIPT_FILENAME = "attestation_receipt.json"
KEY_FILENAME = "public_key.json"
RESULT_FILENAME = "verification_results.raw.json"
SUMMARY_FILENAME = "summary.md"

sys.path.insert(0, str(ROOT / "backend"))

from app.attestation import (  # noqa: E402
    canonical_json_bytes,
    verify_attestation_receipt,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Freeze and verify one TCGA-TRACE detached Ed25519 receipt, "
            "including negative controls for report replacement and unsigned "
            "digest recomputation."
        )
    )
    parser.add_argument("--audit", type=Path)
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--key", type=Path)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Recompute and compare the already frozen evidence.",
    )
    return parser.parse_args()


def read_json_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Could not read JSON object {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise RuntimeError(f"{path} does not contain a JSON object.")
    return value


def select_key_document(
    value: dict[str, Any],
    key_id: str,
) -> dict[str, Any]:
    if value.get("key_id") == key_id:
        return value
    for document in value.get("keys") or []:
        if isinstance(document, dict) and document.get("key_id") == key_id:
            return document
    raise RuntimeError(
        f"The public-key document does not contain receipt key {key_id}."
    )


def mutate_audit_report(audit: dict[str, Any]) -> bytes:
    mutated = copy.deepcopy(audit)
    original = str(mutated.get("generated_at") or "not-recorded")
    mutated["generated_at"] = f"{original}-negative-control"
    return json.dumps(
        mutated,
        ensure_ascii=False,
        allow_nan=False,
        indent=2,
    ).encode("utf-8")


def recompute_unsigned_receipt_fields(
    receipt: dict[str, Any],
    mutated_audit_bytes: bytes,
) -> dict[str, Any]:
    forged = copy.deepcopy(receipt)
    mutated_audit = json.loads(mutated_audit_bytes)
    audit_binding = forged["payload"]["audit_report"]
    audit_binding["bytes"] = len(mutated_audit_bytes)
    audit_binding["sha256"] = hashlib.sha256(
        mutated_audit_bytes
    ).hexdigest()
    audit_binding["schema_version"] = mutated_audit.get("schema_version")
    audit_binding["reproducibility_hash"] = mutated_audit.get(
        "reproducibility_hash"
    )
    forged["signature"]["signed_payload_sha256"] = hashlib.sha256(
        canonical_json_bytes(forged["payload"])
    ).hexdigest()
    return forged


def check_value(
    result: dict[str, Any],
    name: str,
) -> bool | None:
    for item in result.get("checks") or []:
        if item.get("name") == name:
            return bool(item.get("passed"))
    return None


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def build_evidence(
    *,
    audit_bytes: bytes,
    receipt_bytes: bytes,
    key_bytes: bytes,
) -> dict[str, Any]:
    audit = json.loads(audit_bytes)
    receipt = json.loads(receipt_bytes)
    key_value = json.loads(key_bytes)
    signature = receipt.get("signature") or {}
    key_id = str(signature.get("key_id") or "")
    key_document = select_key_document(key_value, key_id)

    exact = verify_attestation_receipt(
        receipt,
        key_document,
        audit_bytes=audit_bytes,
    )
    mutated_audit_bytes = mutate_audit_report(audit)
    report_replacement = verify_attestation_receipt(
        receipt,
        key_document,
        audit_bytes=mutated_audit_bytes,
    )
    recomputed_receipt = recompute_unsigned_receipt_fields(
        receipt,
        mutated_audit_bytes,
    )
    unsigned_recomputation = verify_attestation_receipt(
        recomputed_receipt,
        key_document,
        audit_bytes=mutated_audit_bytes,
    )

    assertions = {
        "exact_report_passes": exact.get("status") == "passed",
        "altered_report_is_rejected": (
            report_replacement.get("status") == "failed"
            and check_value(
                report_replacement,
                "audit_report_sha256",
            )
            is False
        ),
        "recomputed_unsigned_fields_do_not_forge_signature": (
            unsigned_recomputation.get("status") == "failed"
            and check_value(
                unsigned_recomputation,
                "signed_payload_sha256",
            )
            is True
            and check_value(
                unsigned_recomputation,
                "audit_report_sha256",
            )
            is True
            and check_value(
                unsigned_recomputation,
                "ed25519_signature",
            )
            is False
        ),
    }
    if not all(assertions.values()):
        raise RuntimeError(
            "Server-attestation acceptance controls did not behave as expected."
        )

    payload = receipt.get("payload") or {}
    audit_binding = payload.get("audit_report") or {}
    public_key = key_document.get("public_key") or {}
    return {
        "schema_version": "tcga-trace-server-attestation-benchmark-v1",
        "status": "passed",
        "design": {
            "positive_control": (
                "Verify the exact frozen audit bytes against the detached "
                "receipt and independently archived Ed25519 public key."
            ),
            "report_replacement_control": (
                "Alter an audit field outside the internal reproducibility "
                "hash while retaining the original receipt; exact-report "
                "binding must fail."
            ),
            "unsigned_recomputation_control": (
                "Alter the audit, recompute its SHA-256 and the canonical "
                "payload SHA-256, but retain the original Ed25519 signature; "
                "all recomputable digest checks pass while signature "
                "verification must fail."
            ),
            "trust_model": {
                "covered": (
                    "Server origin and exact audit-report bytes, provided the "
                    "public key was obtained from the declared HTTPS issuer "
                    "or matched to an independently archived fingerprint."
                ),
                "excluded": (
                    "Scientific correctness, user prespecification, "
                    "append-only publication time, server-key compromise and "
                    "a malicious server that legitimately signs a new report."
                ),
            },
        },
        "subject": payload.get("subject"),
        "issuer": payload.get("issuer"),
        "issued_at": payload.get("issued_at"),
        "audit_report": {
            "schema_version": audit.get("schema_version"),
            "bytes": len(audit_bytes),
            "sha256": sha256_bytes(audit_bytes),
            "reproducibility_hash": audit.get("reproducibility_hash"),
            "receipt_binding": audit_binding,
        },
        "public_key": {
            "key_id": key_id,
            "fingerprint_sha256": key_document.get(
                "fingerprint_sha256"
            ),
            "algorithm": key_document.get("algorithm"),
            "format": public_key.get("format"),
            "encoding": public_key.get("encoding"),
            "created_at": key_document.get("created_at"),
        },
        "receipt": {
            "schema_version": receipt.get("schema_version"),
            "signed_payload_sha256": signature.get(
                "signed_payload_sha256"
            ),
            "sha256": sha256_bytes(receipt_bytes),
        },
        "frozen_files": {
            AUDIT_FILENAME: {
                "bytes": len(audit_bytes),
                "sha256": sha256_bytes(audit_bytes),
            },
            RECEIPT_FILENAME: {
                "bytes": len(receipt_bytes),
                "sha256": sha256_bytes(receipt_bytes),
            },
            KEY_FILENAME: {
                "bytes": len(key_bytes),
                "sha256": sha256_bytes(key_bytes),
            },
        },
        "acceptance_assertions": assertions,
        "verification": {
            "exact_report": exact,
            "altered_report": report_replacement,
            "recomputed_unsigned_fields": unsigned_recomputation,
        },
    }


def render_summary(evidence: dict[str, Any]) -> str:
    subject = evidence.get("subject") or {}
    audit = evidence.get("audit_report") or {}
    key = evidence.get("public_key") or {}
    assertions = evidence.get("acceptance_assertions") or {}
    lines = [
        "# Server Attestation Benchmark",
        "",
        f"Status: **{evidence.get('status')}**.",
        "",
        "## Frozen Subject",
        "",
        f"- Type: `{subject.get('type')}`",
        f"- ID: `{subject.get('id')}`",
        f"- Audit schema: `{audit.get('schema_version')}`",
        f"- Audit SHA-256: `{audit.get('sha256')}`",
        f"- Reproducibility hash: `{audit.get('reproducibility_hash')}`",
        f"- Ed25519 key ID: `{key.get('key_id')}`",
        "",
        "## Acceptance Controls",
        "",
        (
            "- Exact report verifies: "
            f"`{str(bool(assertions.get('exact_report_passes'))).lower()}`"
        ),
        (
            "- Altered report is rejected: "
            f"`{str(bool(assertions.get('altered_report_is_rejected'))).lower()}`"
        ),
        (
            "- Recomputed unsigned digests cannot forge the signature: "
            f"`{str(bool(assertions.get('recomputed_unsigned_fields_do_not_forge_signature'))).lower()}`"
        ),
        "",
        "The receipt establishes server origin for the exact audit bytes only "
        "when the public key is trusted through the declared HTTPS issuer or "
        "an independently archived matching fingerprint. It does not establish "
        "scientific correctness, prespecification or append-only publication time.",
        "",
    ]
    return "\n".join(lines)


def write_evidence(
    output_dir: Path,
    *,
    audit_bytes: bytes,
    receipt_bytes: bytes,
    key_bytes: bytes,
    evidence: dict[str, Any],
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / AUDIT_FILENAME).write_bytes(audit_bytes)
    (output_dir / RECEIPT_FILENAME).write_bytes(receipt_bytes)
    (output_dir / KEY_FILENAME).write_bytes(key_bytes)
    (output_dir / RESULT_FILENAME).write_text(
        json.dumps(
            evidence,
            ensure_ascii=False,
            allow_nan=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (output_dir / SUMMARY_FILENAME).write_text(
        render_summary(evidence),
        encoding="utf-8",
    )


def check_frozen_evidence(output_dir: Path) -> None:
    audit_bytes = (output_dir / AUDIT_FILENAME).read_bytes()
    receipt_bytes = (output_dir / RECEIPT_FILENAME).read_bytes()
    key_bytes = (output_dir / KEY_FILENAME).read_bytes()
    observed = read_json_object(output_dir / RESULT_FILENAME)
    expected = build_evidence(
        audit_bytes=audit_bytes,
        receipt_bytes=receipt_bytes,
        key_bytes=key_bytes,
    )
    if observed != expected:
        raise RuntimeError(
            "Frozen server-attestation evidence does not match recomputation."
        )
    expected_summary = render_summary(expected)
    observed_summary = (output_dir / SUMMARY_FILENAME).read_text(
        encoding="utf-8"
    )
    if observed_summary != expected_summary:
        raise RuntimeError(
            "Frozen server-attestation summary does not match recomputation."
        )


def main() -> int:
    args = parse_args()
    if args.check_only:
        check_frozen_evidence(args.output_dir)
        print(
            "Server attestation evidence OK: exact report accepted; "
            "report replacement and unsigned digest recomputation rejected."
        )
        return 0

    missing = [
        name
        for name, value in (
            ("--audit", args.audit),
            ("--receipt", args.receipt),
            ("--key", args.key),
        )
        if value is None
    ]
    if missing:
        raise SystemExit(
            "Generation requires " + ", ".join(missing) + "."
        )
    audit_bytes = args.audit.read_bytes()
    receipt_bytes = args.receipt.read_bytes()
    key_bytes = args.key.read_bytes()
    evidence = build_evidence(
        audit_bytes=audit_bytes,
        receipt_bytes=receipt_bytes,
        key_bytes=key_bytes,
    )
    write_evidence(
        args.output_dir,
        audit_bytes=audit_bytes,
        receipt_bytes=receipt_bytes,
        key_bytes=key_bytes,
        evidence=evidence,
    )
    print(f"Wrote {args.output_dir / RESULT_FILENAME}")
    print(f"Wrote {args.output_dir / SUMMARY_FILENAME}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
