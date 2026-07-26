#!/usr/bin/env python3
"""Dependency-free command-line client for the TCGA-TRACE public API."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, TextIO


CLI_VERSION = "1.1.0"
DEFAULT_API_BASE = (
    "https://apps.cienciavida.org/tcga_explorer/api/v1/"
)
TERMINAL_JOB_STATUSES = {"completed", "failed", "expired"}
FAMILY_PATHS = {
    "analysis": "analyses",
    "combined": "analyses/combined",
    "batch": "analyses/batch",
    "multiverse": "analyses/multiverse",
    "pancancer": "pancancer/survival",
    "session": "analyses/sessions/export",
}
FAMILY_OPERATION_IDS = {
    "analysis": "submitSurvivalAnalysis",
    "combined": "submitCombinedSignatureAnalysis",
    "batch": "submitAnalysisBatch",
    "multiverse": "submitPrespecifiedMultiverse",
    "pancancer": "submitPanCancerSurvival",
    "session": "exportExploratorySession",
}
REQUIRED_OPERATION_IDS = {
    *FAMILY_OPERATION_IDS.values(),
    "getComputeJob",
    "getSurvivalAnalysis",
    "getAnalysisBatch",
    "getPrespecifiedMultiverse",
    "getPanCancerSurvival",
    "getExploratorySession",
}
DOWNLOAD_MANIFEST = "tcga-trace-download-manifest.json"


class CliError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        exit_code: int = 2,
        code: str = "CLI_ERROR",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.exit_code = exit_code
        self.code = code
        self.details = details or {}


class ApiError(CliError):
    def __init__(
        self,
        message: str,
        *,
        status: int,
        code: str,
        request_id: str | None,
        details: dict[str, Any] | None = None,
        retry_after: str | None = None,
    ) -> None:
        merged = dict(details or {})
        if request_id:
            merged["request_id"] = request_id
        if retry_after:
            merged["retry_after"] = retry_after
        super().__init__(
            message,
            exit_code=3,
            code=code,
            details={"http_status": status, **merged},
        )
        self.status = status
        self.request_id = request_id
        self.retry_after = retry_after


class ApiClient:
    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = 60.0,
        request_id: str | None = None,
    ) -> None:
        self.base_url = normalize_api_base(base_url)
        self.timeout = timeout
        self.request_id = request_id
        parsed = urllib.parse.urlsplit(self.base_url)
        self._origin = (parsed.scheme, parsed.netloc)
        self._deployment_prefix = deployment_prefix(parsed.path)

    def api_url(self, path: str = "") -> str:
        clean = path.lstrip("/")
        return urllib.parse.urljoin(self.base_url, clean)

    def service_url(self, path: str) -> str:
        parsed = urllib.parse.urlsplit(self.base_url)
        target_path = (
            f"{self._deployment_prefix}/{path.lstrip('/')}"
            if self._deployment_prefix
            else f"/{path.lstrip('/')}"
        )
        return urllib.parse.urlunsplit(
            (parsed.scheme, parsed.netloc, target_path, "", "")
        )

    def resolve_link(self, value: str) -> str:
        parsed = urllib.parse.urlsplit(value)
        if parsed.scheme or parsed.netloc:
            if (parsed.scheme, parsed.netloc) != self._origin:
                raise CliError(
                    "The API returned a cross-origin artifact link.",
                    code="CROSS_ORIGIN_LINK",
                    details={"link": value, "api_base": self.base_url},
                )
            return value
        if value.startswith("/api/v1/"):
            path = f"{self._deployment_prefix}{value}"
            base = urllib.parse.urlsplit(self.base_url)
            return urllib.parse.urlunsplit(
                (base.scheme, base.netloc, path, parsed.query, parsed.fragment)
            )
        if value.startswith("/"):
            base = urllib.parse.urlsplit(self.base_url)
            return urllib.parse.urlunsplit(
                (
                    base.scheme,
                    base.netloc,
                    value,
                    parsed.query,
                    parsed.fragment,
                )
            )
        return self.api_url(value)

    def request_json(
        self,
        method: str,
        path_or_url: str,
        payload: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any] | list[Any], dict[str, str]]:
        url = (
            self.resolve_link(path_or_url)
            if looks_like_link(path_or_url)
            else self.api_url(path_or_url)
        )
        body = None
        headers = {
            "Accept": "application/json",
            "User-Agent": f"tcga-trace-cli/{CLI_VERSION}",
        }
        if self.request_id:
            headers["X-Request-ID"] = self.request_id
        if payload is not None:
            body = json.dumps(
                payload,
                ensure_ascii=True,
                allow_nan=False,
                separators=(",", ":"),
            ).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            url,
            data=body,
            headers=headers,
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read()
                response_headers = {
                    key.lower(): value for key, value in response.headers.items()
                }
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            raise api_error_from_response(exc.code, raw, exc.headers) from exc
        except urllib.error.URLError as exc:
            raise CliError(
                f"Could not reach TCGA-TRACE: {exc.reason}",
                exit_code=3,
                code="NETWORK_ERROR",
                details={"url": url},
            ) from exc
        try:
            value = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CliError(
                "The API returned a non-JSON response.",
                exit_code=3,
                code="INVALID_API_RESPONSE",
                details={"url": url},
            ) from exc
        if not isinstance(value, (dict, list)):
            raise CliError(
                "The API returned an unsupported JSON value.",
                exit_code=3,
                code="INVALID_API_RESPONSE",
                details={"url": url},
            )
        return value, response_headers

    def get(self, path_or_url: str) -> dict[str, Any] | list[Any]:
        value, _headers = self.request_json("GET", path_or_url)
        return value

    def post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        value, _headers = self.request_json("POST", path, payload)
        if not isinstance(value, dict):
            raise CliError(
                "A compute submission did not return a job object.",
                exit_code=3,
                code="INVALID_JOB_RESPONSE",
            )
        return value

    def openapi(self) -> dict[str, Any]:
        value = self.get(self.service_url("api/openapi.json"))
        if not isinstance(value, dict):
            raise CliError(
                "The OpenAPI resource is not an object.",
                exit_code=3,
                code="INVALID_OPENAPI",
            )
        return value

    def check_contract(self, family: str | None = None) -> dict[str, Any]:
        schema = self.openapi()
        operations = {
            operation.get("operationId")
            for methods in (schema.get("paths") or {}).values()
            if isinstance(methods, dict)
            for operation in methods.values()
            if isinstance(operation, dict)
        }
        required = (
            {FAMILY_OPERATION_IDS[family], "getComputeJob"}
            if family
            else REQUIRED_OPERATION_IDS
        )
        missing = sorted(required - operations)
        if missing:
            raise CliError(
                "The server OpenAPI contract lacks required operations.",
                exit_code=3,
                code="INCOMPATIBLE_OPENAPI",
                details={"missing_operation_ids": missing},
            )
        return {
            "status": "compatible",
            "openapi": schema.get("openapi"),
            "title": (schema.get("info") or {}).get("title"),
            "version": (schema.get("info") or {}).get("version"),
            "sha256": stable_hash(schema),
            "checked_operation_ids": sorted(required),
        }

    def download(
        self,
        link: str,
        destination_dir: Path,
        *,
        fallback_name: str,
    ) -> dict[str, Any]:
        url = self.resolve_link(link)
        request = urllib.request.Request(
            url,
            headers={
                "Accept": "*/*",
                "User-Agent": f"tcga-trace-cli/{CLI_VERSION}",
                **(
                    {"X-Request-ID": self.request_id}
                    if self.request_id
                    else {}
                ),
            },
            method="GET",
        )
        destination_dir.mkdir(parents=True, exist_ok=True)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                disposition = response.headers.get("Content-Disposition", "")
                filename = safe_filename(
                    content_disposition_filename(disposition)
                    or fallback_name
                )
                target = unique_target(destination_dir / filename)
                temporary = target.with_name(f".{target.name}.part")
                digest = hashlib.sha256()
                size = 0
                with temporary.open("wb") as handle:
                    while True:
                        chunk = response.read(1024 * 1024)
                        if not chunk:
                            break
                        handle.write(chunk)
                        digest.update(chunk)
                        size += len(chunk)
                temporary.replace(target)
                content_type = response.headers.get_content_type()
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            raise api_error_from_response(exc.code, raw, exc.headers) from exc
        except urllib.error.URLError as exc:
            raise CliError(
                f"Could not download artifact: {exc.reason}",
                exit_code=3,
                code="DOWNLOAD_ERROR",
                details={"url": url},
            ) from exc
        return {
            "path": str(target),
            "filename": target.name,
            "bytes": size,
            "sha256": digest.hexdigest(),
            "content_type": content_type,
            "url": url,
        }


def normalize_api_base(value: str) -> str:
    raw = value.strip()
    if not raw:
        raise CliError("API base URL cannot be empty.", code="INVALID_API_URL")
    parsed = urllib.parse.urlsplit(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise CliError(
            "API base URL must be an absolute HTTP or HTTPS URL.",
            code="INVALID_API_URL",
            details={"value": value},
        )
    path = re.sub(r"/+", "/", parsed.path or "/").rstrip("/")
    if path.endswith("/api/v1"):
        api_path = f"{path}/"
    elif path.endswith("/api"):
        api_path = f"{path}/v1/"
    else:
        api_path = f"{path}/api/v1/" if path else "/api/v1/"
    return urllib.parse.urlunsplit(
        (parsed.scheme, parsed.netloc, api_path, "", "")
    )


def deployment_prefix(api_path: str) -> str:
    suffix = "/api/v1/"
    if not api_path.endswith(suffix):
        raise CliError(
            "Normalized API URL does not end in /api/v1/.",
            code="INVALID_API_URL",
        )
    return api_path[: -len(suffix)].rstrip("/")


def looks_like_link(value: str) -> bool:
    return value.startswith("/") or "://" in value


def api_error_from_response(
    status: int,
    raw: bytes,
    headers: Any,
) -> ApiError:
    payload: dict[str, Any] = {}
    try:
        decoded = json.loads(raw.decode("utf-8"))
        if isinstance(decoded, dict):
            payload = decoded
    except (UnicodeDecodeError, json.JSONDecodeError):
        pass
    detail = payload.get("error") or payload.get("detail") or {}
    if isinstance(detail, dict):
        code = str(detail.get("code") or f"HTTP_{status}")
        message = str(
            detail.get("message")
            or detail.get("detail")
            or f"HTTP request failed with status {status}."
        )
        details = detail.get("details")
        request_id = detail.get("request_id")
    else:
        code = f"HTTP_{status}"
        message = str(detail or f"HTTP request failed with status {status}.")
        details = {}
        request_id = None
    return ApiError(
        message,
        status=status,
        code=code,
        request_id=request_id or headers.get("X-Request-ID"),
        details=details if isinstance(details, dict) else {},
        retry_after=headers.get("Retry-After"),
    )


def load_json_source(value: str, stdin: TextIO) -> dict[str, Any]:
    try:
        raw = stdin.read() if value == "-" else Path(value).read_text(
            encoding="utf-8"
        )
    except OSError as exc:
        raise CliError(
            f"Could not read request JSON: {exc}",
            code="REQUEST_READ_ERROR",
        ) from exc
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise CliError(
            f"Request JSON is invalid at line {exc.lineno}, column {exc.colno}.",
            code="INVALID_REQUEST_JSON",
        ) from exc
    if not isinstance(payload, dict):
        raise CliError(
            "Request JSON must contain one object.",
            code="INVALID_REQUEST_JSON",
        )
    return payload


def wait_for_job(
    client: ApiClient,
    job: dict[str, Any],
    *,
    poll_interval: float,
    wait_timeout: float,
    stderr: TextIO,
) -> dict[str, Any]:
    job_id = str(job.get("id") or "")
    if not job_id:
        raise CliError(
            "The API response lacks a job ID.",
            exit_code=3,
            code="INVALID_JOB_RESPONSE",
        )
    deadline = time.monotonic() + wait_timeout
    current = job
    previous_status: str | None = None
    while True:
        status = str(current.get("status") or "")
        if status != previous_status:
            print(f"[{job_id}] {status or 'unknown'}", file=stderr)
            previous_status = status
        if status in TERMINAL_JOB_STATUSES:
            break
        if time.monotonic() >= deadline:
            raise CliError(
                f"Timed out waiting for job {job_id}.",
                exit_code=6,
                code="JOB_WAIT_TIMEOUT",
                details={"job_id": job_id, "last_status": status},
            )
        time.sleep(max(0.0, poll_interval))
        value = client.get(f"jobs/{urllib.parse.quote(job_id, safe='')}")
        if not isinstance(value, dict):
            raise CliError(
                "The job status resource is not an object.",
                exit_code=3,
                code="INVALID_JOB_RESPONSE",
            )
        current = value
    if current.get("status") != "completed":
        error = current.get("error") or {}
        raise CliError(
            str(error.get("message") or f"Job {job_id} did not complete."),
            exit_code=4,
            code=str(error.get("code") or "JOB_NOT_COMPLETED"),
            details={"job_id": job_id, "status": current.get("status")},
        )
    return current


def result_identifier(value: dict[str, Any], fallback: str) -> str:
    for key in ("id", "analysis_id", "session_id", "scan_id"):
        if value.get(key):
            return safe_filename(str(value[key]))
    return safe_filename(fallback)


def collect_download_links(
    value: Any,
    *,
    path: tuple[str, ...] = (),
) -> list[dict[str, str]]:
    links: list[dict[str, str]] = []
    if isinstance(value, dict):
        downloads = value.get("downloads")
        if isinstance(downloads, dict):
            identifier = result_identifier(
                value,
                "-".join(path[-3:]) or "result",
            )
            for kind, link in sorted(downloads.items()):
                if isinstance(link, str) and link:
                    links.append(
                        {
                            "identifier": identifier,
                            "kind": str(kind),
                            "label": ".".join((*path, "downloads", str(kind))),
                            "url": link,
                        }
                    )
        for key, child in value.items():
            if key != "downloads":
                links.extend(
                    collect_download_links(child, path=(*path, str(key)))
                )
    elif isinstance(value, list):
        for index, child in enumerate(value):
            links.extend(
                collect_download_links(child, path=(*path, str(index)))
            )
    deduplicated: dict[tuple[str, str], dict[str, str]] = {}
    for item in links:
        deduplicated[(item["identifier"], item["url"])] = item
    return list(deduplicated.values())


def download_job_artifacts(
    client: ApiClient,
    job: dict[str, Any],
    destination: Path,
    *,
    mode: str,
) -> dict[str, Any]:
    result = job.get("result")
    links = collect_download_links(result, path=("result",))
    if mode == "zip":
        links = [item for item in links if item["kind"] == "zip"]
    if not links:
        raise CliError(
            "The completed result exposes no matching artifact links.",
            code="NO_ARTIFACT_LINKS",
            details={"mode": mode, "job_id": job.get("id")},
        )
    destination.mkdir(parents=True, exist_ok=True)
    files: list[dict[str, Any]] = []
    for item in links:
        target_dir = destination / safe_filename(item["identifier"])
        fallback = f"{safe_filename(item['identifier'])}.{safe_filename(item['kind'])}"
        if item["kind"] == "zip":
            fallback += ".zip"
        record = client.download(
            item["url"],
            target_dir,
            fallback_name=fallback,
        )
        record["relative_path"] = str(
            Path(record["path"]).relative_to(destination)
        )
        record["label"] = item["label"]
        record["kind"] = item["kind"]
        files.append(record)
    manifest_core = {
        "schema_version": "tcga-trace-cli-download-v1",
        "cli_version": CLI_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "api_base": client.base_url,
        "job_id": job.get("id"),
        "job_kind": job.get("kind"),
        "result_id": job.get("result_id"),
        "mode": mode,
        "files": [
            {
                key: item[key]
                for key in (
                    "relative_path",
                    "bytes",
                    "sha256",
                    "content_type",
                    "url",
                    "label",
                    "kind",
                )
            }
            for item in files
        ],
    }
    manifest = {
        **manifest_core,
        "record_sha256": stable_hash(manifest_core),
    }
    manifest_path = destination / DOWNLOAD_MANIFEST
    write_json_file(manifest_path, manifest)
    return {
        "directory": str(destination),
        "manifest": str(manifest_path),
        "files": files,
        "record_sha256": manifest["record_sha256"],
    }


def content_disposition_filename(value: str) -> str | None:
    encoded = re.search(
        r"filename\*\s*=\s*UTF-8''([^;]+)",
        value,
        flags=re.IGNORECASE,
    )
    if encoded:
        return urllib.parse.unquote(encoded.group(1).strip())
    quoted = re.search(
        r'filename\s*=\s*"([^"]+)"',
        value,
        flags=re.IGNORECASE,
    )
    if quoted:
        return quoted.group(1)
    plain = re.search(
        r"filename\s*=\s*([^;]+)",
        value,
        flags=re.IGNORECASE,
    )
    return plain.group(1).strip() if plain else None


def safe_filename(value: str) -> str:
    name = Path(value.replace("\\", "/")).name.strip()
    name = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip(".-")
    return name[:180] or "artifact"


def unique_target(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    for index in range(2, 10_000):
        candidate = path.with_name(f"{stem}-{index}{suffix}")
        if not candidate.exists():
            return candidate
    raise CliError(
        f"Could not choose a unique artifact filename under {path.parent}.",
        code="DOWNLOAD_NAME_EXHAUSTED",
    )


def verify_targets(paths: Iterable[Path]) -> dict[str, Any]:
    targets = [verify_target(path) for path in paths]
    return {
        "schema_version": "tcga-trace-cli-verification-v1",
        "status": (
            "passed"
            if targets and all(item["status"] == "passed" for item in targets)
            else "failed"
        ),
        "targets": targets,
    }


def verify_target(path: Path) -> dict[str, Any]:
    if not path.exists():
        return verification_result(
            path,
            [check("target_exists", False, "Path does not exist.")],
        )
    if path.is_file() and zipfile.is_zipfile(path):
        return verify_zip(path)
    if path.is_file() and path.name.endswith(".json"):
        return verify_package_directory(path.parent)
    if path.is_dir():
        checks: list[dict[str, Any]] = []
        manifest_path = path / DOWNLOAD_MANIFEST
        if manifest_path.exists():
            checks.extend(verify_download_manifest(path, manifest_path))
        zip_paths = sorted(path.rglob("*.zip"))
        package_marker = path / "audit_report.json"
        children: list[dict[str, Any]] = []
        if package_marker.exists():
            children.append(verify_package_directory(path))
        children.extend(verify_zip(item) for item in zip_paths)
        if not checks and not children:
            checks.append(
                check(
                    "verifiable_content_present",
                    False,
                    "No download manifest, audit report or ZIP bundle found.",
                )
            )
        status = (
            "passed"
            if all(item["passed"] for item in checks)
            and all(item["status"] == "passed" for item in children)
            else "failed"
        )
        return {
            "target": str(path),
            "status": status,
            "checks": checks,
            "packages": children,
        }
    return verification_result(
        path,
        [check("supported_target", False, "Unsupported verification target.")],
    )


def verify_download_manifest(
    root: Path,
    manifest_path: Path,
) -> list[dict[str, Any]]:
    try:
        manifest = read_json(manifest_path)
    except CliError as exc:
        return [check("download_manifest_json", False, str(exc))]
    core = {
        key: value
        for key, value in manifest.items()
        if key != "record_sha256"
    }
    checks = [
        check(
            "download_manifest_record_sha256",
            stable_hash(core) == manifest.get("record_sha256"),
            {
                "observed": stable_hash(core),
                "expected": manifest.get("record_sha256"),
            },
        )
    ]
    for index, record in enumerate(manifest.get("files") or []):
        relative = str(record.get("relative_path") or "")
        candidate = safe_child(root, relative)
        label = f"download_{index + 1}"
        if candidate is None or not candidate.is_file():
            checks.append(
                check(
                    f"{label}_exists",
                    False,
                    f"Missing or unsafe path: {relative}",
                )
            )
            continue
        checks.extend(
            verify_file_record(candidate, record, prefix=label)
        )
    return checks


def verify_zip(path: Path) -> dict[str, Any]:
    checks: list[dict[str, Any]] = [
        check("zip_sha256", True, file_sha256(path))
    ]
    with tempfile.TemporaryDirectory(prefix="tcga-trace-cli-verify-") as raw:
        target = Path(raw)
        try:
            with zipfile.ZipFile(path) as archive:
                seen: set[str] = set()
                for info in archive.infolist():
                    member = PurePosixPath(info.filename)
                    unsafe = (
                        member.is_absolute()
                        or ".." in member.parts
                        or "\\" in info.filename
                        or info.filename in seen
                        or is_zip_symlink(info)
                    )
                    if unsafe:
                        checks.append(
                            check(
                                "zip_member_safety",
                                False,
                                f"Unsafe member: {info.filename}",
                            )
                        )
                        return verification_result(path, checks)
                    seen.add(info.filename)
                archive.extractall(target)
        except (OSError, zipfile.BadZipFile) as exc:
            checks.append(check("zip_readable", False, str(exc)))
            return verification_result(path, checks)
        package = verify_package_directory(target)
    checks.append(
        check(
            "package_integrity",
            package["status"] == "passed",
            package,
        )
    )
    return verification_result(path, checks)


def is_zip_symlink(info: zipfile.ZipInfo) -> bool:
    mode = (info.external_attr >> 16) & 0o170000
    return mode == 0o120000


def verify_package_directory(root: Path) -> dict[str, Any]:
    audit_path = root / "audit_report.json"
    if not audit_path.is_file():
        return verification_result(
            root,
            [check("audit_report_present", False, "audit_report.json missing.")],
        )
    try:
        report = read_json(audit_path)
    except CliError as exc:
        return verification_result(
            root,
            [check("audit_report_json", False, str(exc))],
        )
    report_type = report.get("report_type")
    if report_type in {"analysis_audit", "survival_analysis_audit"}:
        checks = verify_analysis_audit(root, report)
    elif report_type == "prespecified_multiverse_audit":
        checks = verify_multiverse_audit(root, report)
    elif report_type == "pancancer_survival_audit":
        checks = verify_pancancer_audit(root, report)
    elif report_type == "exploratory_session_audit":
        checks = verify_exploratory_session_audit(root, report)
    else:
        checks = [
            check(
                "supported_audit_type",
                False,
                f"Unsupported report_type: {report_type!r}",
            )
        ]
    return verification_result(root, checks)


def verify_analysis_audit(
    root: Path,
    report: dict[str, Any],
) -> list[dict[str, Any]]:
    cohort = report.get("cohort_selection") or {}
    analysis_design = report.get("analysis_design") or {}
    data = report.get("data") or {}
    patient_records = cohort.get("patient_records") or []
    patient_digest = stable_hash({"records": patient_records})
    continuous_records = cohort.get("continuous_patient_records") or []
    continuous_digest = (
        stable_hash({"records": continuous_records})
        if continuous_records
        else None
    )
    scoring = analysis_design.get("scoring_provenance") or {}
    checks = [
        equality_check(
            "patient_records_sha256",
            patient_digest,
            cohort.get("patient_records_sha256"),
        ),
        equality_check(
            "continuous_patient_records_sha256",
            continuous_digest,
            cohort.get("continuous_patient_records_sha256"),
        ),
        equality_check(
            "scoring_provenance_sha256",
            stable_hash(scoring),
            analysis_design.get("scoring_provenance_sha256"),
        ),
    ]
    schema = report.get("schema_version")
    if schema in {
        "tcga-trace-analysis-audit-v4",
        "tcga-trace-analysis-audit-v3",
    }:
        payload = {
            "request": report.get("request"),
            "data_dates": data.get("data_dates") or {},
            "data_provenance": data.get("provenance") or {},
            "scoring_provenance_sha256": stable_hash(scoring),
            "record_digest": patient_digest,
            "continuous_record_digest": continuous_digest,
            "core_results": report.get("results") or {},
        }
    elif schema == "tcga-trace-analysis-audit-v2":
        payload = {
            "request": report.get("request"),
            "data_dates": data.get("data_dates") or {},
            "data_provenance": data.get("provenance") or {},
            "scoring_provenance_sha256": stable_hash(scoring),
            "record_digest": patient_digest,
            "core_results": report.get("results") or {},
        }
    else:
        payload = {
            "request": report.get("request"),
            "data_dates": data.get("data_dates") or {},
            "record_digest": patient_digest,
            "core_results": report.get("results") or {},
        }
    checks.append(
        equality_check(
            "reproducibility_hash",
            stable_hash(payload),
            report.get("reproducibility_hash"),
        )
    )
    checks.extend(verify_artifact_records(root, report.get("artifacts") or {}))
    manifest_path = root / "reproduction_manifest.json"
    if manifest_path.exists():
        manifest = read_json(manifest_path)
        checks.extend(
            verify_artifact_records(
                root,
                manifest.get("files") or {},
                prefix="capsule",
            )
        )
    return checks


def verify_multiverse_audit(
    root: Path,
    report: dict[str, Any],
) -> list[dict[str, Any]]:
    result_path = root / "multiverse_result.json"
    if not result_path.is_file():
        return [
            check(
                "multiverse_result_present",
                False,
                "multiverse_result.json missing.",
            )
        ]
    result = read_json(result_path)
    request = result.get("request_snapshot") or {}
    rows = result.get("specifications") or []
    family_core = {
        "pipeline_version": result.get("pipeline_version"),
        "data_version": report.get("data_version") or {},
        "request": request,
        "specifications": [
            {
                "specification_id": row.get("specification_id"),
                "analysis_request_hash": row.get("analysis_request_hash"),
                "analysis_id": row.get("analysis_id"),
                "audit_reproducibility_hash": row.get(
                    "audit_reproducibility_hash"
                ),
                "status": row.get("status"),
            }
            for row in rows
        ],
    }
    return [
        equality_check(
            "multiverse_request_sha256",
            stable_hash(request),
            report.get("request_sha256"),
        ),
        equality_check(
            "multiverse_family_reproducibility_hash",
            stable_hash(family_core),
            report.get("family_reproducibility_hash"),
        ),
        equality_check(
            "multiverse_session_id",
            result.get("session_id"),
            report.get("session_id"),
        ),
        equality_check(
            "multiverse_child_count",
            len(rows),
            report.get("child_analysis_count"),
        ),
    ]


def verify_pancancer_audit(
    root: Path,
    report: dict[str, Any],
) -> list[dict[str, Any]]:
    data = report.get("data") or {}
    payload = {
        "request": report.get("request"),
        "pipeline_version": (report.get("pipeline") or {}).get("version"),
        "data_version": data.get("version") or {},
        "patient_records_sha256": data.get("patient_records_sha256"),
        "core_results": report.get("results") or {},
    }
    checks = [
        equality_check(
            "pancancer_reproducibility_hash",
            stable_hash(payload),
            report.get("reproducibility_hash"),
        )
    ]
    checks.extend(verify_artifact_records(root, report.get("artifacts") or {}))
    return checks


def verify_exploratory_session_audit(
    root: Path,
    report: dict[str, Any],
) -> list[dict[str, Any]]:
    result_path = root / "session_report.json"
    if not result_path.is_file():
        return [
            check(
                "session_report_present",
                False,
                "session_report.json missing.",
            )
        ]
    result = read_json(result_path)
    request_snapshot = result.get("request_snapshot") or {}
    family_core = {
        "pipeline_version": result.get("pipeline_version"),
        "request_snapshot": request_snapshot,
        "source_jobs": report.get("source_jobs") or [],
        "report_id": result.get("report_id"),
        "analysis_families": result.get("analysis_families") or {},
        "hypotheses": result.get("hypotheses") or [],
        "managed_family_references": (
            result.get("managed_family_references") or []
        ),
        "runs": result.get("runs") or [],
    }
    return [
        equality_check(
            "session_request_sha256",
            stable_hash(request_snapshot),
            report.get("request_sha256"),
        ),
        equality_check(
            "session_family_reproducibility_hash",
            stable_hash(family_core),
            report.get("family_reproducibility_hash"),
        ),
        equality_check(
            "session_report_id",
            result.get("report_id"),
            report.get("report_id"),
        ),
        equality_check(
            "session_source_job_count",
            len(report.get("source_jobs") or []),
            report.get("source_job_count"),
        ),
    ]


def verify_artifact_records(
    root: Path,
    records: dict[str, Any],
    *,
    prefix: str = "artifact",
) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    for label, record in sorted(records.items()):
        if not isinstance(record, dict):
            checks.append(
                check(
                    f"{prefix}_{label}_record",
                    False,
                    "Artifact metadata is not an object.",
                )
            )
            continue
        filename = str(record.get("filename") or "")
        path = safe_child(root, filename)
        if path is None or not path.is_file():
            checks.append(
                check(
                    f"{prefix}_{label}_exists",
                    False,
                    f"Missing or unsafe artifact: {filename}",
                )
            )
            continue
        checks.extend(
            verify_file_record(path, record, prefix=f"{prefix}_{label}")
        )
    return checks


def verify_file_record(
    path: Path,
    record: dict[str, Any],
    *,
    prefix: str,
) -> list[dict[str, Any]]:
    return [
        equality_check(
            f"{prefix}_bytes",
            path.stat().st_size,
            record.get("bytes"),
        ),
        equality_check(
            f"{prefix}_sha256",
            file_sha256(path),
            record.get("sha256"),
        ),
    ]


def safe_child(root: Path, relative: str) -> Path | None:
    candidate_relative = Path(relative)
    if (
        not relative
        or candidate_relative.is_absolute()
        or ".." in candidate_relative.parts
    ):
        return None
    root_resolved = root.resolve()
    candidate = (root / candidate_relative).resolve()
    try:
        candidate.relative_to(root_resolved)
    except ValueError:
        return None
    return candidate


def check(name: str, passed: bool, detail: Any) -> dict[str, Any]:
    return {"name": name, "passed": bool(passed), "detail": detail}


def equality_check(name: str, observed: Any, expected: Any) -> dict[str, Any]:
    return check(
        name,
        observed == expected,
        {"observed": observed, "expected": expected},
    )


def verification_result(
    path: Path,
    checks: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "target": str(path),
        "status": (
            "passed"
            if checks and all(item["passed"] for item in checks)
            else "failed"
        ),
        "checks": checks,
    }


def stable_hash(payload: Any) -> str:
    raw = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CliError(
            f"Could not read JSON file {path}: {exc}",
            code="INVALID_LOCAL_JSON",
        ) from exc
    if not isinstance(value, dict):
        raise CliError(
            f"JSON file {path} does not contain an object.",
            code="INVALID_LOCAL_JSON",
        )
    return value


def write_json_file(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(
            value,
            indent=2,
            sort_keys=True,
            ensure_ascii=True,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def emit_json(value: Any, args: argparse.Namespace, stdout: TextIO) -> None:
    encoded = json.dumps(
        value,
        indent=None if args.compact else 2,
        sort_keys=True,
        ensure_ascii=True,
        allow_nan=False,
    )
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(encoded + "\n", encoding="utf-8")
    else:
        print(encoded, file=stdout)


def add_wait_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=2.0,
        help="Seconds between job polls (default: 2).",
    )
    parser.add_argument(
        "--wait-timeout",
        type=float,
        default=3600.0,
        help="Maximum seconds to wait for a job (default: 3600).",
    )


def add_download_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--download-dir",
        type=Path,
        help="Directory for retained artifacts.",
    )
    parser.add_argument(
        "--artifacts",
        choices=("none", "zip", "all"),
        default="none",
        help="Download no artifacts, each result ZIP, or all exposed files.",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Verify downloaded manifests, checksums and reproducibility hashes.",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tcga-trace",
        description=(
            "Submit, monitor, download and verify TCGA-TRACE public analyses "
            "without third-party Python packages."
        ),
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {CLI_VERSION}",
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get("TCGA_TRACE_API_URL", DEFAULT_API_BASE),
        help=(
            "Deployment root or API v1 base URL. Can also be set with "
            "TCGA_TRACE_API_URL."
        ),
    )
    parser.add_argument(
        "--request-timeout",
        type=float,
        default=60.0,
        help="Per-request network timeout in seconds (default: 60).",
    )
    parser.add_argument(
        "--request-id",
        default="",
        help="Optional X-Request-ID value for server log correlation.",
    )
    parser.add_argument(
        "--output",
        help="Write the JSON response to this file instead of stdout.",
    )
    parser.add_argument(
        "--compact",
        action="store_true",
        help="Emit compact JSON.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    for command, help_text in (
        ("index", "Discover canonical service links."),
        ("health", "Inspect service, data and queue readiness."),
        ("cohorts", "List TCGA cohorts."),
        ("endpoints", "List global survival endpoint availability."),
        ("expression-scales", "List supported RNA expression scales."),
        ("openapi", "Download the live OpenAPI document."),
        ("contract-check", "Check CLI-required OpenAPI operation IDs."),
    ):
        subparsers.add_parser(command, help=help_text)

    cohort_endpoints = subparsers.add_parser(
        "cohort-endpoints",
        help="Inspect endpoint QC for one cohort.",
    )
    cohort_endpoints.add_argument("cohort")

    filters = subparsers.add_parser(
        "filters",
        help="List clinical filter values for one cohort.",
    )
    filters.add_argument("cohort")

    genes = subparsers.add_parser(
        "genes",
        help="Search valid gene symbols in one cohort.",
    )
    genes.add_argument("cohort")
    genes.add_argument("query", nargs="?", default="")
    genes.add_argument("--limit", type=int, default=25)

    resolve = subparsers.add_parser(
        "resolve",
        help="Resolve a gene symbol or supported alias.",
    )
    resolve.add_argument("cohort")
    resolve.add_argument("query")

    submit = subparsers.add_parser(
        "submit",
        help="Submit one public compute request and return its persistent job.",
    )
    submit.add_argument("family", choices=tuple(FAMILY_PATHS))
    submit.add_argument("request_json", help="Request JSON path or - for stdin.")
    submit.add_argument(
        "--skip-contract-check",
        action="store_true",
        help="Submit without checking the live OpenAPI operation IDs.",
    )

    run = subparsers.add_parser(
        "run",
        help="Check, submit and poll one compute request.",
    )
    run.add_argument("family", choices=tuple(FAMILY_PATHS))
    run.add_argument("request_json", help="Request JSON path or - for stdin.")
    run.add_argument(
        "--skip-contract-check",
        action="store_true",
        help="Run without checking the live OpenAPI operation IDs.",
    )
    add_wait_arguments(run)
    add_download_arguments(run)

    job = subparsers.add_parser(
        "job",
        help="Retrieve or wait for a persistent compute job.",
    )
    job.add_argument("job_id")
    job.add_argument("--wait", action="store_true")
    add_wait_arguments(job)

    download = subparsers.add_parser(
        "download",
        help="Download artifacts exposed by a completed job.",
    )
    download.add_argument("job_id")
    download.add_argument(
        "--download-dir",
        type=Path,
        required=True,
    )
    download.add_argument(
        "--artifacts",
        choices=("zip", "all"),
        default="zip",
    )
    download.add_argument("--wait", action="store_true")
    download.add_argument("--verify", action="store_true")
    add_wait_arguments(download)

    verify = subparsers.add_parser(
        "verify",
        help="Verify downloaded directories, ZIP bundles or audit packages.",
    )
    verify.add_argument("paths", nargs="+", type=Path)
    return parser


def validate_runtime_arguments(args: argparse.Namespace) -> None:
    if args.request_timeout <= 0:
        raise CliError(
            "--request-timeout must be greater than zero.",
            code="INVALID_TIMEOUT",
        )
    if hasattr(args, "poll_interval") and args.poll_interval < 0:
        raise CliError(
            "--poll-interval cannot be negative.",
            code="INVALID_POLL_INTERVAL",
        )
    if hasattr(args, "wait_timeout") and args.wait_timeout <= 0:
        raise CliError(
            "--wait-timeout must be greater than zero.",
            code="INVALID_WAIT_TIMEOUT",
        )
    if args.command == "genes" and not 1 <= args.limit <= 100:
        raise CliError(
            "--limit must be between 1 and 100.",
            code="INVALID_LIMIT",
        )


def dispatch(
    args: argparse.Namespace,
    *,
    stdin: TextIO,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    validate_runtime_arguments(args)
    if args.command == "verify":
        result = verify_targets(args.paths)
        emit_json(result, args, stdout)
        return 0 if result["status"] == "passed" else 5

    client = ApiClient(
        args.base_url,
        timeout=args.request_timeout,
        request_id=args.request_id or None,
    )
    simple_paths = {
        "index": "",
        "health": "health",
        "cohorts": "cohorts",
        "endpoints": "endpoints",
        "expression-scales": "expression-scales",
    }
    if args.command in simple_paths:
        emit_json(client.get(simple_paths[args.command]), args, stdout)
        return 0
    if args.command == "openapi":
        emit_json(client.openapi(), args, stdout)
        return 0
    if args.command == "contract-check":
        emit_json(client.check_contract(), args, stdout)
        return 0
    if args.command == "cohort-endpoints":
        path = f"cohorts/{urllib.parse.quote(args.cohort, safe='')}/endpoints"
        emit_json(client.get(path), args, stdout)
        return 0
    if args.command == "filters":
        path = f"cohorts/{urllib.parse.quote(args.cohort, safe='')}/filters"
        emit_json(client.get(path), args, stdout)
        return 0
    if args.command == "genes":
        query = urllib.parse.urlencode(
            {"query": args.query, "limit": args.limit}
        )
        path = (
            f"cohorts/{urllib.parse.quote(args.cohort, safe='')}/genes?{query}"
        )
        emit_json(client.get(path), args, stdout)
        return 0
    if args.command == "resolve":
        query = urllib.parse.urlencode({"query": args.query})
        path = (
            "cohorts/"
            f"{urllib.parse.quote(args.cohort, safe='')}/genes/resolve?{query}"
        )
        emit_json(client.get(path), args, stdout)
        return 0
    if args.command == "submit":
        contract = (
            None
            if args.skip_contract_check
            else client.check_contract(args.family)
        )
        payload = load_json_source(args.request_json, stdin)
        job = client.post(FAMILY_PATHS[args.family], payload)
        emit_json(
            {
                "cli_version": CLI_VERSION,
                "api_base": client.base_url,
                "family": args.family,
                "contract": contract,
                "job": job,
            },
            args,
            stdout,
        )
        return 0
    if args.command == "job":
        value = client.get(
            f"jobs/{urllib.parse.quote(args.job_id, safe='')}"
        )
        if not isinstance(value, dict):
            raise CliError(
                "The job resource is not an object.",
                exit_code=3,
                code="INVALID_JOB_RESPONSE",
            )
        if args.wait:
            value = wait_for_job(
                client,
                value,
                poll_interval=args.poll_interval,
                wait_timeout=args.wait_timeout,
                stderr=stderr,
            )
        emit_json(value, args, stdout)
        return 0
    if args.command == "run":
        contract = (
            None
            if args.skip_contract_check
            else client.check_contract(args.family)
        )
        payload = load_json_source(args.request_json, stdin)
        job = client.post(FAMILY_PATHS[args.family], payload)
        completed = wait_for_job(
            client,
            job,
            poll_interval=args.poll_interval,
            wait_timeout=args.wait_timeout,
            stderr=stderr,
        )
        mode = "zip" if args.verify and args.artifacts == "none" else args.artifacts
        download_dir = args.download_dir
        if mode != "none" and download_dir is None:
            download_dir = Path(f"tcga-trace-{completed['id']}")
        downloads = (
            download_job_artifacts(
                client,
                completed,
                download_dir,
                mode=mode,
            )
            if mode != "none" and download_dir is not None
            else None
        )
        verification = (
            verify_targets([download_dir])
            if args.verify and download_dir is not None
            else None
        )
        result = {
            "schema_version": "tcga-trace-cli-run-v1",
            "cli_version": CLI_VERSION,
            "api_base": client.base_url,
            "family": args.family,
            "contract": contract,
            "job": completed,
            "downloads": downloads,
            "verification": verification,
        }
        emit_json(result, args, stdout)
        return (
            0
            if verification is None or verification["status"] == "passed"
            else 5
        )
    if args.command == "download":
        value = client.get(
            f"jobs/{urllib.parse.quote(args.job_id, safe='')}"
        )
        if not isinstance(value, dict):
            raise CliError(
                "The job resource is not an object.",
                exit_code=3,
                code="INVALID_JOB_RESPONSE",
            )
        if args.wait:
            value = wait_for_job(
                client,
                value,
                poll_interval=args.poll_interval,
                wait_timeout=args.wait_timeout,
                stderr=stderr,
            )
        if value.get("status") != "completed":
            raise CliError(
                "Artifacts are available only after job completion.",
                exit_code=4,
                code="JOB_NOT_COMPLETED",
                details={"job_id": args.job_id, "status": value.get("status")},
            )
        downloads = download_job_artifacts(
            client,
            value,
            args.download_dir,
            mode=args.artifacts,
        )
        verification = (
            verify_targets([args.download_dir]) if args.verify else None
        )
        result = {
            "job_id": args.job_id,
            "downloads": downloads,
            "verification": verification,
        }
        emit_json(result, args, stdout)
        return (
            0
            if verification is None or verification["status"] == "passed"
            else 5
        )
    raise CliError(
        f"Unsupported command: {args.command}",
        code="UNSUPPORTED_COMMAND",
    )


def main(
    argv: list[str] | None = None,
    *,
    stdin: TextIO = sys.stdin,
    stdout: TextIO = sys.stdout,
    stderr: TextIO = sys.stderr,
) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return dispatch(
            args,
            stdin=stdin,
            stdout=stdout,
            stderr=stderr,
        )
    except CliError as exc:
        print(
            json.dumps(
                {
                    "error": {
                        "code": exc.code,
                        "message": str(exc),
                        "details": exc.details,
                    }
                },
                sort_keys=True,
            ),
            file=stderr,
        )
        return exc.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
