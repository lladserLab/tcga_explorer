from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any
import uuid

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from app.config import Settings


ATTESTATION_RECEIPT_SCHEMA = "tcga-trace-server-attestation-v1"
ATTESTATION_KEY_SCHEMA = "tcga-trace-attestation-key-v1"
ATTESTATION_KEYSET_SCHEMA = "tcga-trace-attestation-keyset-v1"
CANONICALIZATION = "tcga-trace-canonical-json-v1"
KEY_ID_PATTERN = re.compile(r"^ed25519-sha256-[0-9a-f]{64}$")


class AttestationError(RuntimeError):
    pass


@dataclass(frozen=True)
class AttestationKey:
    private_key: Ed25519PrivateKey
    key_id: str
    fingerprint_sha256: str
    public_key_base64url: str
    created_at: str


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def attestation_issuer(settings: Settings) -> str:
    return (
        getattr(settings, "attestation_issuer", None)
        or getattr(
            settings,
            "public_base_url",
            "https://apps.cienciavida.org/tcga_explorer",
        )
    ).rstrip("/")


def ensure_attestation_key(settings: Settings) -> AttestationKey:
    if not getattr(settings, "attestation_enabled", True):
        raise AttestationError("Server attestation is disabled.")

    path = _private_key_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.parent.chmod(0o700)
    except OSError:
        pass

    lock_path = path.parent / ".key-generation.lock"
    with lock_path.open("a+", encoding="utf-8") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            if not path.exists():
                if not getattr(
                    settings,
                    "attestation_auto_generate",
                    True,
                ):
                    raise AttestationError(
                        f"Attestation private key does not exist at {path}."
                    )
                _generate_private_key(path)
            key = _load_private_key(path)
            document = _key_document(settings, key)
            _persist_public_key_document(settings, document)
            return key
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def attestation_metadata(
    settings: Settings,
    *,
    subject_type: str,
    subject_id: str,
) -> dict[str, Any]:
    key = ensure_attestation_key(settings)
    issuer = attestation_issuer(settings)
    return {
        "status": "detached_receipt",
        "schema_version": ATTESTATION_RECEIPT_SCHEMA,
        "algorithm": "Ed25519",
        "canonicalization": CANONICALIZATION,
        "issuer": issuer,
        "key_id": key.key_id,
        "public_key_url": (
            f"{issuer}/api/v1/attestation/keys/{key.key_id}"
        ),
        "receipt_url": _receipt_url(
            issuer,
            subject_type=subject_type,
            subject_id=subject_id,
        ),
        "receipt_filename": "attestation_receipt.json",
        "scope": (
            "The detached server receipt signs the exact audit_report.json "
            "SHA-256, byte count, audit schema and recorded reproducibility hash."
        ),
        "trust_model": (
            "Origin is established only after the Ed25519 signature is checked "
            "against the key obtained from the declared HTTPS endpoint or an "
            "independently archived matching fingerprint. The receipt does not "
            "establish scientific correctness or append-only publication time."
        ),
    }


def write_attestation_receipt(
    settings: Settings,
    *,
    subject_type: str,
    subject_id: str,
    audit_path: Path,
    reproducibility_hash: str,
    report_schema_version: str,
) -> dict[str, Any]:
    key = ensure_attestation_key(settings)
    metadata = attestation_metadata(
        settings,
        subject_type=subject_type,
        subject_id=subject_id,
    )
    audit_bytes = audit_path.read_bytes()
    issued_at = datetime.now(timezone.utc).isoformat()
    payload = {
        "issuer": metadata["issuer"],
        "issued_at": issued_at,
        "subject": {
            "type": subject_type,
            "id": subject_id,
        },
        "audit_report": {
            "filename": audit_path.name,
            "bytes": len(audit_bytes),
            "sha256": hashlib.sha256(audit_bytes).hexdigest(),
            "schema_version": report_schema_version,
            "reproducibility_hash": reproducibility_hash,
        },
        "verification": {
            "key_id": key.key_id,
            "public_key_url": metadata["public_key_url"],
            "receipt_url": metadata["receipt_url"],
        },
    }
    signed_payload = canonical_json_bytes(payload)
    signature = key.private_key.sign(signed_payload)
    receipt = {
        "schema_version": ATTESTATION_RECEIPT_SCHEMA,
        "payload": payload,
        "signature": {
            "algorithm": "Ed25519",
            "canonicalization": CANONICALIZATION,
            "key_id": key.key_id,
            "signed_payload_sha256": hashlib.sha256(
                signed_payload
            ).hexdigest(),
            "value_base64url": _base64url_encode(signature),
        },
    }
    receipt_path = audit_path.parent / "attestation_receipt.json"
    _atomic_write_json(receipt_path, receipt, mode=0o644)
    return {
        **metadata,
        "issued_at": issued_at,
        "audit_report_sha256": payload["audit_report"]["sha256"],
        "signed_payload_sha256": receipt["signature"][
            "signed_payload_sha256"
        ],
    }


def attestation_keyset(settings: Settings) -> dict[str, Any]:
    active = ensure_attestation_key(settings)
    documents: dict[str, dict[str, Any]] = {}
    public_dir = _public_key_directory(settings)
    for path in sorted(public_dir.glob("ed25519-sha256-*.json")):
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        key_id = str(document.get("key_id") or "")
        if KEY_ID_PATTERN.fullmatch(key_id):
            documents[key_id] = document
    active_document = _key_document(settings, active)
    documents[active.key_id] = active_document
    keys = []
    for key_id, document in sorted(documents.items()):
        keys.append(
            {
                **document,
                "status": "active" if key_id == active.key_id else "retired",
            }
        )
    return {
        "schema_version": ATTESTATION_KEYSET_SCHEMA,
        "issuer": attestation_issuer(settings),
        "active_key_id": active.key_id,
        "keys": keys,
        "verification_note": (
            "Retrieve this keyset over the declared HTTPS origin or compare the "
            "full SHA-256 fingerprint with an independently archived release."
        ),
    }


def attestation_key_document(
    settings: Settings,
    key_id: str,
) -> dict[str, Any]:
    if not KEY_ID_PATTERN.fullmatch(key_id):
        raise AttestationError("Invalid attestation key identifier.")
    keyset = attestation_keyset(settings)
    for document in keyset["keys"]:
        if document.get("key_id") == key_id:
            return document
    raise AttestationError(f"Attestation key {key_id} is not available.")


def verify_attestation_receipt(
    receipt: dict[str, Any],
    key_document: dict[str, Any],
    *,
    audit_bytes: bytes | None = None,
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def add(name: str, passed: bool, detail: Any) -> None:
        checks.append(
            {"name": name, "passed": bool(passed), "detail": detail}
        )

    payload = receipt.get("payload")
    signature = receipt.get("signature")
    if not isinstance(payload, dict) or not isinstance(signature, dict):
        add(
            "receipt_structure",
            False,
            "Receipt payload and signature must be JSON objects.",
        )
        return _verification_result(checks)

    add(
        "receipt_schema",
        receipt.get("schema_version") == ATTESTATION_RECEIPT_SCHEMA,
        receipt.get("schema_version"),
    )
    add(
        "signature_algorithm",
        signature.get("algorithm") == "Ed25519",
        signature.get("algorithm"),
    )
    add(
        "canonicalization",
        signature.get("canonicalization") == CANONICALIZATION,
        signature.get("canonicalization"),
    )
    key_id = str(signature.get("key_id") or "")
    add(
        "key_id",
        key_id == key_document.get("key_id"),
        {
            "receipt": key_id,
            "key_document": key_document.get("key_id"),
        },
    )
    add(
        "issuer",
        payload.get("issuer") == key_document.get("issuer"),
        {
            "receipt": payload.get("issuer"),
            "key_document": key_document.get("issuer"),
        },
    )

    signed_payload = canonical_json_bytes(payload)
    observed_payload_hash = hashlib.sha256(signed_payload).hexdigest()
    add(
        "signed_payload_sha256",
        observed_payload_hash == signature.get("signed_payload_sha256"),
        {
            "observed": observed_payload_hash,
            "expected": signature.get("signed_payload_sha256"),
        },
    )

    signature_valid = False
    try:
        public_value = (
            (key_document.get("public_key") or {}).get("value_base64url")
        )
        public_raw = _base64url_decode(str(public_value or ""))
        public_key = Ed25519PublicKey.from_public_bytes(public_raw)
        fingerprint = hashlib.sha256(public_raw).hexdigest()
        add(
            "public_key_fingerprint",
            fingerprint == key_document.get("fingerprint_sha256")
            and key_id == f"ed25519-sha256-{fingerprint}",
            {
                "observed": fingerprint,
                "expected": key_document.get("fingerprint_sha256"),
            },
        )
        public_key.verify(
            _base64url_decode(
                str(signature.get("value_base64url") or "")
            ),
            signed_payload,
        )
        signature_valid = True
    except (ValueError, TypeError, InvalidSignature):
        signature_valid = False
    add(
        "ed25519_signature",
        signature_valid,
        "valid" if signature_valid else "invalid",
    )

    if audit_bytes is not None:
        audit_record = payload.get("audit_report") or {}
        audit_sha256 = hashlib.sha256(audit_bytes).hexdigest()
        add(
            "audit_report_bytes",
            len(audit_bytes) == audit_record.get("bytes"),
            {
                "observed": len(audit_bytes),
                "expected": audit_record.get("bytes"),
            },
        )
        add(
            "audit_report_sha256",
            audit_sha256 == audit_record.get("sha256"),
            {
                "observed": audit_sha256,
                "expected": audit_record.get("sha256"),
            },
        )
        try:
            audit_report = json.loads(audit_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            audit_report = None
        add(
            "audit_report_json",
            isinstance(audit_report, dict),
            "valid object" if isinstance(audit_report, dict) else "invalid",
        )
        if isinstance(audit_report, dict):
            add(
                "audit_schema_version",
                audit_report.get("schema_version")
                == audit_record.get("schema_version"),
                {
                    "observed": audit_report.get("schema_version"),
                    "expected": audit_record.get("schema_version"),
                },
            )
            observed_reproducibility_hash = (
                audit_report.get("reproducibility_hash")
                or audit_report.get("family_reproducibility_hash")
            )
            add(
                "audit_reproducibility_hash",
                observed_reproducibility_hash
                == audit_record.get("reproducibility_hash"),
                {
                    "observed": observed_reproducibility_hash,
                    "expected": audit_record.get(
                        "reproducibility_hash"
                    ),
                },
            )
    return _verification_result(checks)


def _generate_private_key(path: Path) -> None:
    key = Ed25519PrivateKey.generate()
    payload = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    descriptor = os.open(
        temporary,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
        0o600,
    )
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        path.chmod(0o600)
    finally:
        temporary.unlink(missing_ok=True)


def _load_private_key(path: Path) -> AttestationKey:
    try:
        value = serialization.load_pem_private_key(
            path.read_bytes(),
            password=None,
        )
    except (OSError, ValueError, TypeError) as exc:
        raise AttestationError(
            f"Could not load attestation private key {path}: {exc}"
        ) from exc
    if not isinstance(value, Ed25519PrivateKey):
        raise AttestationError(
            f"Attestation key {path} is not an Ed25519 private key."
        )
    public_raw = value.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    fingerprint = hashlib.sha256(public_raw).hexdigest()
    created_at = datetime.fromtimestamp(
        path.stat().st_mtime,
        timezone.utc,
    ).isoformat()
    return AttestationKey(
        private_key=value,
        key_id=f"ed25519-sha256-{fingerprint}",
        fingerprint_sha256=fingerprint,
        public_key_base64url=_base64url_encode(public_raw),
        created_at=created_at,
    )


def _key_document(
    settings: Settings,
    key: AttestationKey,
) -> dict[str, Any]:
    return {
        "schema_version": ATTESTATION_KEY_SCHEMA,
        "issuer": attestation_issuer(settings),
        "key_id": key.key_id,
        "status": "active",
        "algorithm": "Ed25519",
        "created_at": key.created_at,
        "fingerprint_sha256": key.fingerprint_sha256,
        "public_key": {
            "format": "raw",
            "encoding": "base64url-no-padding",
            "value_base64url": key.public_key_base64url,
        },
    }


def _persist_public_key_document(
    settings: Settings,
    document: dict[str, Any],
) -> None:
    path = _public_key_directory(settings) / (
        f"{document['key_id']}.json"
    )
    if not path.exists():
        _atomic_write_json(path, document, mode=0o644)


def _public_key_directory(settings: Settings) -> Path:
    path = (
        getattr(settings, "attestation_public_key_dir", None)
        or _private_key_path(settings).parent / "public_keys"
    )
    path.mkdir(parents=True, exist_ok=True)
    return path


def _private_key_path(settings: Settings) -> Path:
    configured = getattr(settings, "attestation_private_key_path", None)
    if configured is not None:
        return Path(configured)
    artifact_dir = Path(getattr(settings, "artifact_dir", "."))
    return artifact_dir / ".attestation" / "ed25519-private.pem"


def _receipt_url(
    issuer: str,
    *,
    subject_type: str,
    subject_id: str,
) -> str:
    if subject_type == "survival_analysis":
        relative = f"/api/v1/analyses/{subject_id}/download/attestation"
    elif subject_type == "prespecified_multiverse":
        relative = (
            f"/api/v1/analyses/multiverses/{subject_id}"
            "/download/attestation"
        )
    elif subject_type == "pancancer_survival":
        relative = (
            f"/api/v1/pancancer/survival/{subject_id}"
            "/download/attestation"
        )
    elif subject_type == "exploratory_session":
        relative = (
            f"/api/v1/analyses/sessions/{subject_id}"
            "/download/attestation"
        )
    else:
        relative = f"/api/v1/attestation/receipts/{subject_id}"
    return f"{issuer}{relative}"


def _atomic_write_json(
    path: Path,
    value: dict[str, Any],
    *,
    mode: int,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    descriptor = os.open(
        temporary,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
        mode,
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(
                value,
                handle,
                ensure_ascii=False,
                allow_nan=False,
                indent=2,
            )
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        path.chmod(mode)
    finally:
        temporary.unlink(missing_ok=True)


def _base64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _base64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(f"{value}{padding}".encode("ascii"))


def _verification_result(
    checks: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "status": (
            "passed"
            if checks and all(check["passed"] for check in checks)
            else "failed"
        ),
        "checks": checks,
    }
