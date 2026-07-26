#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "backend"))

from app.attestation import verify_attestation_receipt  # noqa: E402


def read_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Could not read JSON object {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{path} does not contain a JSON object.")
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
    raise ValueError(
        f"The key document does not contain receipt key {key_id}."
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Verify a TCGA-TRACE detached Ed25519 receipt against an exact "
            "audit report and a public key document obtained from the declared "
            "HTTPS issuer or an independently archived release."
        )
    )
    parser.add_argument("receipt", type=Path)
    parser.add_argument("audit_report", type=Path)
    parser.add_argument(
        "--key",
        type=Path,
        required=True,
        help="Single public-key document or keyset JSON.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        receipt = read_object(args.receipt)
        signature = receipt.get("signature") or {}
        key_id = str(signature.get("key_id") or "")
        key_document = select_key_document(
            read_object(args.key),
            key_id,
        )
        result = verify_attestation_receipt(
            receipt,
            key_document,
            audit_bytes=args.audit_report.read_bytes(),
        )
    except (OSError, ValueError) as exc:
        result = {
            "status": "failed",
            "checks": [
                {
                    "name": "verification_input",
                    "passed": False,
                    "detail": str(exc),
                }
            ],
        }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "passed" else 5


if __name__ == "__main__":
    raise SystemExit(main())
