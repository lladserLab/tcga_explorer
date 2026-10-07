from __future__ import annotations

import csv
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import math
from pathlib import Path
import re
import time
from typing import Any
import urllib.parse

import httpx

from app.repository.adapters.cbioportal import request_json, write_tsv
from app.repository.storage import sha256_file


DRYAD_ADAPTER_VERSION = "dryad_publication_v1"
DRYAD_API = "https://datadryad.org/api/v2"
DRYAD_WEB = "https://datadryad.org"
DRYAD_BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0 Safari/537.36"
)
ANUBIS_CHALLENGE_PATTERN = re.compile(
    r'<script id="anubis_challenge" type="application/json">'
    r"(.*?)</script>",
    flags=re.DOTALL,
)
DOWNLOAD_ATTEMPTS = 4
PARALLEL_DOWNLOAD_THRESHOLD = 1024 * 1024
PARALLEL_DOWNLOAD_WORKERS = 16


def materialize_dryad_source(
    spec: dict[str, Any],
    source_dir: Path,
) -> tuple[dict[str, Path], str, str | None, dict[str, Any]]:
    source_spec = spec["source"]
    identifier = str(source_spec.get("identifier") or "").strip()
    version_id = int(source_spec.get("version_id") or 0)
    if not identifier or version_id <= 0:
        raise ValueError(
            "Dryad sources require an identifier and positive version_id."
        )

    quoted_identifier = urllib.parse.quote(identifier, safe="")
    dataset_api_url = f"{DRYAD_API}/datasets/{quoted_identifier}"
    dataset = request_json(dataset_api_url)
    validate_dryad_dataset(dataset, source_spec)

    files_api_url = (
        f"{DRYAD_API}/versions/{version_id}/files?"
        + urllib.parse.urlencode({"per_page": 100})
    )
    file_payload = request_json(files_api_url)
    remote_files = (
        (file_payload.get("_embedded") or {}).get("stash:files")
        if isinstance(file_payload, dict)
        else None
    )
    if not isinstance(remote_files, list):
        raise ValueError("Dryad files endpoint returned an invalid payload.")
    remote_by_id = {
        dryad_file_id(row): row
        for row in remote_files
        if isinstance(row, dict) and dryad_file_id(row) > 0
    }

    declared_files = source_spec.get("files") or {}
    required_roles = {"clinical", "expression"}
    if not required_roles.issubset(declared_files):
        raise ValueError(
            "Dryad sources require pinned clinical and expression files."
        )
    downloaded: dict[str, Path] = {}
    pinned_files: dict[str, dict[str, Any]] = {}
    for role, file_spec in declared_files.items():
        file_id = int(file_spec.get("file_id") or 0)
        remote = remote_by_id.get(file_id)
        if remote is None:
            raise ValueError(
                f"Dryad dataset is missing pinned {role} file {file_id}."
            )
        pin = validate_dryad_file_pin(file_spec, remote)
        target = source_dir / pin["name"]
        download_dryad_public_file(
            identifier,
            file_id,
            target,
            expected_size=pin["size"],
        )
        if target.stat().st_size != pin["size"]:
            raise ValueError(
                f"Downloaded Dryad {role} file failed size validation."
            )
        if md5_file(target) != pin["md5"]:
            raise ValueError(
                f"Downloaded Dryad {role} file failed MD5 validation."
            )
        if sha256_file(target) != pin["sha256"]:
            raise ValueError(
                f"Downloaded Dryad {role} file failed SHA-256 validation."
            )
        downloaded[role] = target
        pinned_files[role] = pin

    clinical_rows = read_dryad_clinical(downloaded["clinical"])
    expected_patients = int(
        source_spec.get("expected_eligible_patients") or 0
    )
    expected_events = int(source_spec.get("expected_events") or 0)
    expected_censored = int(source_spec.get("expected_censored") or 0)
    observed_events = sum(int(row["event"]) for row in clinical_rows)
    observed_censored = len(clinical_rows) - observed_events
    if (
        (
            expected_patients
            and len(clinical_rows) != expected_patients
        )
        or (expected_events and observed_events != expected_events)
        or (
            expected_censored
            and observed_censored != expected_censored
        )
    ):
        raise ValueError(
            "Dryad eligible cohort changed from the reviewed pin: "
            f"patients={len(clinical_rows)}, events={observed_events}, "
            f"censored={observed_censored}."
        )

    patient_table = source_dir / "data_clinical_patient.txt"
    sample_table = source_dir / "data_clinical_sample.txt"
    patient_rows: list[dict[str, str]] = []
    sample_rows: list[dict[str, str]] = []
    for row in clinical_rows:
        raw_metadata = canonical_json(row["source_row"])
        patient_rows.append(
            {
                "PATIENT_ID": row["patient_id"],
                "RFS_YEARS": row["raw_time"],
                "RFS_STATUS": row["raw_event"],
                "DRYAD_CLINICAL_METADATA_JSON": raw_metadata,
            }
        )
        sample_rows.append(
            {
                "SAMPLE_ID": row["patient_id"],
                "PATIENT_ID": row["patient_id"],
                "SAMPLE_TYPE": "Primary breast cancer FFPE tumor",
                "DRYAD_CLINICAL_METADATA_JSON": raw_metadata,
            }
        )
    write_tsv(
        patient_table,
        patient_rows,
        [
            "PATIENT_ID",
            "RFS_YEARS",
            "RFS_STATUS",
            "DRYAD_CLINICAL_METADATA_JSON",
        ],
    )
    write_tsv(
        sample_table,
        sample_rows,
        [
            "SAMPLE_ID",
            "PATIENT_ID",
            "SAMPLE_TYPE",
            "DRYAD_CLINICAL_METADATA_JSON",
        ],
    )

    selected_expression = source_dir / "data_expression_log2_cpm.tsv"
    expression_summary = materialize_dryad_counts_matrix(
        downloaded["expression"],
        selected_expression,
        [row["patient_id"] for row in clinical_rows],
        expected_gene_rows=int(source_spec.get("expected_gene_rows") or 0),
    )
    expected_unique_symbols = int(
        source_spec.get("expected_unique_source_symbols") or 0
    )
    expected_normalized_rows = int(
        source_spec.get("expected_normalized_gene_rows") or 0
    )
    if (
        (
            expected_unique_symbols
            and expression_summary["source_unique_nonempty_symbols"]
            != expected_unique_symbols
        )
        or (
            expected_normalized_rows
            and expression_summary["normalized_expression_gene_rows"]
            != expected_normalized_rows
        )
    ):
        raise ValueError(
            "Dryad expression symbols changed from the reviewed pin: "
            f"unique={expression_summary['source_unique_nonempty_symbols']}, "
            "normalized="
            f"{expression_summary['normalized_expression_gene_rows']}."
        )

    stable_snapshot = {
        "identifier": str(dataset.get("identifier") or ""),
        "version_id": version_id,
        "version_number": int(dataset.get("versionNumber") or 0),
        "title": str(dataset.get("title") or ""),
        "publication_date": str(dataset.get("publicationDate") or ""),
        "last_modification_date": str(
            dataset.get("lastModificationDate") or ""
        ),
        "visibility": str(dataset.get("visibility") or ""),
        "license": str(dataset.get("license") or ""),
        "related_works": dataset.get("relatedWorks") or [],
        "files": pinned_files,
    }
    source_snapshot = hashlib.sha256(
        canonical_json(stable_snapshot).encode("utf-8")
    ).hexdigest()
    snapshot_path = source_dir / "dryad_dataset_snapshot.json"
    snapshot_path.write_text(
        json.dumps(stable_snapshot, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    source_manifest_path = source_dir / "dryad_source_manifest.json"
    source_manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "tcga-trace-dryad-source-manifest-v1",
                "dataset_api_url": dataset_api_url,
                "files_api_url": files_api_url,
                "source_snapshot_sha256": source_snapshot,
                **stable_snapshot,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    return (
        {
            "expression": selected_expression,
            "patients": patient_table,
            "samples": sample_table,
            "clinical_source": downloaded["clinical"],
            "expression_source": downloaded["expression"],
            "dataset_metadata": snapshot_path,
            "source_manifest": source_manifest_path,
            "license": snapshot_path,
        },
        source_snapshot,
        str(dataset.get("publicationDate") or "") or None,
        {
            "source_api": DRYAD_API,
            "source_dryad_identifier": identifier,
            "source_dryad_version_id": version_id,
            "source_license": str(dataset.get("license") or ""),
            "source_eligible_patients": len(clinical_rows),
            "source_events": observed_events,
            "source_censored": observed_censored,
            "source_pinned_files": pinned_files,
            **expression_summary,
        },
    )


def validate_dryad_dataset(
    dataset: Any,
    source_spec: dict[str, Any],
) -> None:
    if not isinstance(dataset, dict):
        raise ValueError("Dryad dataset endpoint returned invalid data.")
    identifier = str(source_spec.get("identifier") or "").strip()
    expected_version = int(source_spec.get("version_number") or 0)
    expected_license = str(source_spec.get("expected_license") or "").strip()
    observed_license = str(dataset.get("license") or "").strip()
    version_href = str(
        ((dataset.get("_links") or {}).get("stash:version") or {}).get(
            "href"
        )
        or ""
    )
    observed_version_id = int(version_href.rsplit("/", 1)[-1] or 0)
    if str(dataset.get("identifier") or "") != identifier:
        raise ValueError("Dryad API returned the wrong dataset identifier.")
    if str(dataset.get("visibility") or "") != "public":
        raise ValueError("Dryad dataset is not a public release.")
    if str(dataset.get("curationStatus") or "") != "Published":
        raise ValueError("Dryad dataset is not in Published curation state.")
    if (
        observed_version_id != int(source_spec.get("version_id") or 0)
        or (
            expected_version
            and int(dataset.get("versionNumber") or 0)
            != expected_version
        )
    ):
        raise ValueError("Dryad dataset version changed from the reviewed pin.")
    if not observed_license or (
        expected_license and observed_license != expected_license
    ):
        raise ValueError(
            "Dryad license changed from the reviewed pin: "
            f"{observed_license!r}."
        )


def validate_dryad_file_pin(
    file_spec: dict[str, Any],
    remote: dict[str, Any],
) -> dict[str, Any]:
    file_id = int(file_spec.get("file_id") or 0)
    name = str(file_spec.get("name") or "").strip()
    size = int(file_spec.get("size") or 0)
    md5 = str(file_spec.get("md5") or "").strip().lower()
    sha256 = str(file_spec.get("sha256") or "").strip().lower()
    remote_md5 = str(remote.get("digest") or "").strip().lower()
    if (
        file_id <= 0
        or dryad_file_id(remote) != file_id
        or not name
        or name != Path(name).name
        or str(remote.get("path") or "") != name
        or size <= 0
        or int(remote.get("size") or 0) != size
    ):
        raise ValueError("Dryad file identifier, name or size pin failed.")
    if (
        str(remote.get("digestType") or "").casefold() != "md5"
        or not re.fullmatch(r"[0-9a-f]{32}", md5)
        or remote_md5 != md5
    ):
        raise ValueError("Dryad file MD5 pin failed.")
    if not re.fullmatch(r"[0-9a-f]{64}", sha256):
        raise ValueError("Dryad file SHA-256 pin is invalid.")
    return {
        "file_id": file_id,
        "name": name,
        "size": size,
        "md5": md5,
        "sha256": sha256,
    }


def dryad_file_id(remote: dict[str, Any]) -> int:
    raw_id = remote.get("id")
    if str(raw_id or "").isdigit():
        return int(raw_id)
    self_href = str(
        ((remote.get("_links") or {}).get("self") or {}).get("href")
        or ""
    )
    candidate = self_href.rsplit("/", 1)[-1]
    return int(candidate) if candidate.isdigit() else 0


def read_dryad_clinical(path: Path) -> list[dict[str, Any]]:
    with path.open(
        newline="", encoding="utf-8-sig", errors="strict"
    ) as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if reader.fieldnames != ["SampleID", "VSCode", "Years"]:
            raise ValueError("Dryad recurrence table has an unexpected header.")
        source_rows = list(reader)
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for source_row in source_rows:
        cleaned = {
            str(key).strip(): (
                "" if value is None else str(value).strip()
            )
            for key, value in source_row.items()
        }
        patient_id = cleaned["SampleID"]
        raw_event = cleaned["VSCode"]
        raw_time = cleaned["Years"]
        if not patient_id or patient_id in seen:
            raise ValueError(
                "Dryad recurrence table has a missing or duplicate sample ID."
            )
        if raw_event not in {"0", "1"}:
            raise ValueError("Dryad recurrence status must be exactly 0 or 1.")
        try:
            time_years = float(raw_time)
        except ValueError as error:
            raise ValueError(
                "Dryad recurrence table contains a non-numeric time."
            ) from error
        if not math.isfinite(time_years) or time_years <= 0:
            raise ValueError(
                "Dryad recurrence table contains non-positive follow-up."
            )
        selected.append(
            {
                "patient_id": patient_id,
                "event": int(raw_event),
                "raw_event": raw_event,
                "raw_time": raw_time,
                "source_row": cleaned,
            }
        )
        seen.add(patient_id)
    if not selected:
        raise ValueError("Dryad recurrence table is empty.")
    return selected


def materialize_dryad_counts_matrix(
    source: Path,
    target: Path,
    selected_sample_ids: list[str],
    *,
    minimum_gene_rows: int = 10_000,
    expected_gene_rows: int = 0,
) -> dict[str, Any]:
    with source.open(
        newline="", encoding="utf-8-sig", errors="strict"
    ) as handle:
        reader = csv.reader(handle, delimiter="\t")
        header = next(reader)
        if len(header) < 2 or header[0].strip():
            raise ValueError("Dryad count matrix has an unexpected header.")
        source_sample_ids = [value.strip() for value in header[1:]]
        if (
            any(not value for value in source_sample_ids)
            or len(source_sample_ids) != len(set(source_sample_ids))
        ):
            raise ValueError(
                "Dryad count matrix has missing or duplicate sample IDs."
            )
        source_indexes = {
            sample_id: index
            for index, sample_id in enumerate(source_sample_ids, start=1)
        }
        if len(selected_sample_ids) != len(set(selected_sample_ids)):
            raise ValueError("Selected Dryad sample IDs contain duplicates.")
        missing = [
            sample_id
            for sample_id in selected_sample_ids
            if sample_id not in source_indexes
        ]
        unexpected = sorted(
            set(source_sample_ids) - set(selected_sample_ids)
        )
        if missing or unexpected:
            raise ValueError(
                "Dryad expression and endpoint sample IDs do not match "
                f"exactly: missing={missing[:5]}, unexpected={unexpected[:5]}."
            )
        indexes = [
            source_indexes[sample_id] for sample_id in selected_sample_ids
        ]
        library_sizes = [0.0] * len(indexes)
        symbol_counts: Counter[str] = Counter()
        gene_rows = 0
        for row in reader:
            if not row:
                continue
            if len(row) != len(header):
                raise ValueError(
                    "Dryad count-matrix row width is inconsistent."
                )
            symbol = dryad_feature_symbol(row[0])
            values = parse_nonnegative_counts(row, indexes)
            library_sizes = [
                total + value
                for total, value in zip(
                    library_sizes, values, strict=True
                )
            ]
            symbol_counts[symbol] += 1
            gene_rows += 1
    if gene_rows < minimum_gene_rows:
        raise ValueError(
            "Dryad expression matrix has fewer than "
            f"{minimum_gene_rows:,} gene rows."
        )
    if expected_gene_rows and gene_rows != expected_gene_rows:
        raise ValueError(
            "Dryad expression row count changed from the reviewed pin: "
            f"{gene_rows} != {expected_gene_rows}."
        )
    if any(value <= 0 for value in library_sizes):
        raise ValueError("Dryad count matrix contains an empty library.")

    target.parent.mkdir(parents=True, exist_ok=True)
    with source.open(
        newline="", encoding="utf-8-sig", errors="strict"
    ) as input_handle, target.open(
        "w", newline="", encoding="utf-8"
    ) as output_handle:
        reader = csv.reader(input_handle, delimiter="\t")
        next(reader)
        writer = csv.writer(
            output_handle, delimiter="\t", lineterminator="\n"
        )
        writer.writerow(["Hugo_Symbol", *selected_sample_ids])
        written_rows = 0
        for row in reader:
            if not row:
                continue
            symbol = dryad_feature_symbol(row[0])
            if symbol_counts[symbol] != 1:
                continue
            values = parse_nonnegative_counts(row, indexes)
            normalized = [
                math.log2((value / library_size) * 1_000_000.0 + 1.0)
                for value, library_size in zip(
                    values, library_sizes, strict=True
                )
            ]
            writer.writerow(
                [
                    symbol,
                    *(format(value, ".17g") for value in normalized),
                ]
            )
            written_rows += 1
    if written_rows < minimum_gene_rows:
        raise ValueError(
            "Dryad matrix has fewer than "
            f"{minimum_gene_rows:,} unambiguous gene symbols."
        )
    duplicated_symbols = {
        symbol: count
        for symbol, count in symbol_counts.items()
        if count > 1
    }
    return {
        "source_expression_layout": "wide_gene_counts_tsv",
        "source_expression_columns": len(source_sample_ids),
        "selected_expression_columns": len(selected_sample_ids),
        "source_expression_gene_rows": gene_rows,
        "source_unique_nonempty_symbols": len(symbol_counts),
        "source_duplicated_symbol_labels": len(duplicated_symbols),
        "source_duplicated_symbol_rows": sum(
            duplicated_symbols.values()
        ),
        "normalized_expression_gene_rows": written_rows,
        "expression_normalization": "log2(CPM + 1)",
        "expression_library_size_basis": "all source gene rows",
        "expression_library_sizes": {
            sample_id: format(value, ".17g")
            for sample_id, value in zip(
                selected_sample_ids, library_sizes, strict=True
            )
        },
    }


def dryad_feature_symbol(raw_feature: str) -> str:
    feature = str(raw_feature).strip()
    symbol = feature.rsplit("~", 1)[-1].strip().upper()
    if not feature or "~" not in feature or not symbol:
        raise ValueError(f"Cannot parse Dryad gene feature {raw_feature!r}.")
    return symbol


def parse_nonnegative_counts(
    row: list[str],
    indexes: list[int],
) -> list[float]:
    try:
        values = [float(row[index]) for index in indexes]
    except (IndexError, ValueError) as error:
        raise ValueError(
            f"Invalid Dryad count at feature {row[:1]!r}."
        ) from error
    if any(not math.isfinite(value) or value < 0 for value in values):
        raise ValueError(
            f"Non-finite or negative Dryad count at {row[:1]!r}."
        )
    return values


def parse_anubis_challenge(html: str) -> dict[str, Any]:
    match = ANUBIS_CHALLENGE_PATTERN.search(html)
    if match is None:
        raise ValueError("Dryad download did not expose an Anubis challenge.")
    payload = json.loads(match.group(1))
    challenge = payload.get("challenge") or {}
    rules = payload.get("rules") or {}
    difficulty = int(rules.get("difficulty") or challenge.get("difficulty") or 0)
    random_data = str(challenge.get("randomData") or "")
    challenge_id = str(challenge.get("id") or "")
    if (
        str(rules.get("algorithm") or "") != "fast"
        or not challenge_id
        or not random_data
        or difficulty <= 0
        or difficulty > 12
    ):
        raise ValueError("Dryad returned an unsupported Anubis challenge.")
    return {
        "id": challenge_id,
        "random_data": random_data,
        "difficulty": difficulty,
    }


def solve_anubis_pow(
    random_data: str,
    difficulty: int,
    *,
    start_nonce: int = 0,
) -> tuple[str, int]:
    if not random_data or difficulty <= 0 or difficulty > 12:
        raise ValueError("Invalid Anubis proof-of-work input.")
    target_prefix = "0" * difficulty
    nonce = start_nonce
    while True:
        digest = hashlib.sha256(
            f"{random_data}{nonce}".encode("utf-8")
        ).hexdigest()
        if digest.startswith(target_prefix):
            return digest, nonce
        nonce += 1


def resolve_dryad_signed_url(
    identifier: str,
    file_id: int,
) -> str:
    quoted_identifier = urllib.parse.quote(identifier, safe=":/")
    landing_url = f"{DRYAD_WEB}/dataset/{quoted_identifier}"
    download_url = f"{DRYAD_WEB}/downloads/file_stream/{file_id}"
    headers = {
        "User-Agent": DRYAD_BROWSER_USER_AGENT,
        "Accept-Encoding": "identity",
    }
    with httpx.Client(
        headers=headers,
        follow_redirects=False,
        timeout=180,
    ) as client:
        landing = client.get(landing_url)
        landing.raise_for_status()
        challenge_response = client.get(
            download_url,
            headers={"Referer": landing_url},
        )
        challenge_response.raise_for_status()
        challenge = parse_anubis_challenge(challenge_response.text)
        started = time.monotonic()
        response_hash, nonce = solve_anubis_pow(
            challenge["random_data"],
            challenge["difficulty"],
        )
        elapsed_ms = max(1, round((time.monotonic() - started) * 1000))
        pass_url = (
            f"{DRYAD_WEB}/.within.website/x/cmd/anubis/"
            "api/pass-challenge"
        )
        response = client.get(
            pass_url,
            params={
                "id": challenge["id"],
                "response": response_hash,
                "nonce": nonce,
                "redir": download_url,
                "elapsedTime": elapsed_ms,
            },
            headers={"Referer": download_url},
        )
        for _ in range(6):
            if response.status_code not in {301, 302, 303, 307, 308}:
                raise ValueError(
                    "Dryad challenge did not redirect to a public file."
                )
            location = urllib.parse.urljoin(
                str(response.request.url),
                str(response.headers.get("location") or ""),
            )
            parsed = urllib.parse.urlparse(location)
            if (
                parsed.scheme == "https"
                and parsed.hostname
                and parsed.hostname.endswith("amazonaws.com")
            ):
                return location
            response = client.get(location)
    raise ValueError("Dryad download redirect chain exceeded six steps.")


def download_dryad_public_file(
    identifier: str,
    file_id: int,
    target: Path,
    *,
    expected_size: int,
) -> None:
    signed_url = resolve_dryad_signed_url(identifier, file_id)
    download_signed_url(
        signed_url,
        target,
        expected_size=expected_size,
    )


def download_signed_url(
    url: str,
    target: Path,
    *,
    expected_size: int,
) -> None:
    if expected_size <= 0:
        raise ValueError("Dryad download size must be positive.")
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f"{target.name}.part")
    temporary.unlink(missing_ok=True)
    try:
        if expected_size < PARALLEL_DOWNLOAD_THRESHOLD:
            payload = download_http_bytes(url)
            if len(payload) != expected_size:
                raise OSError(
                    "Dryad response size differs from the pinned file size."
                )
            temporary.write_bytes(payload)
        else:
            workers = PARALLEL_DOWNLOAD_WORKERS
            chunk_size = math.ceil(expected_size / workers)
            intervals = [
                (
                    index,
                    index * chunk_size,
                    min((index + 1) * chunk_size, expected_size) - 1,
                )
                for index in range(workers)
                if index * chunk_size < expected_size
            ]
            parts: list[bytes | None] = [None] * len(intervals)
            with ThreadPoolExecutor(max_workers=workers) as executor:
                futures = {
                    executor.submit(
                        download_http_range,
                        url,
                        start,
                        end,
                        expected_size,
                    ): index
                    for index, start, end in intervals
                }
                for future in as_completed(futures):
                    index = futures[future]
                    parts[index] = future.result()
            with temporary.open("wb") as handle:
                for part in parts:
                    if part is None:
                        raise OSError("A Dryad download interval is missing.")
                    handle.write(part)
        if temporary.stat().st_size != expected_size:
            raise OSError(
                "Dryad download is truncated: "
                f"{temporary.stat().st_size} != {expected_size} bytes."
            )
        temporary.replace(target)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def download_http_bytes(url: str) -> bytes:
    last_error: Exception | None = None
    for attempt in range(DOWNLOAD_ATTEMPTS):
        try:
            response = httpx.get(
                url,
                headers={
                    "User-Agent": DRYAD_BROWSER_USER_AGENT,
                    "Accept-Encoding": "identity",
                },
                follow_redirects=True,
                timeout=180,
            )
            response.raise_for_status()
            return response.content
        except httpx.HTTPError as error:
            last_error = error
            if attempt + 1 < DOWNLOAD_ATTEMPTS:
                time.sleep(2**attempt)
    assert last_error is not None
    raise last_error


def download_http_range(
    url: str,
    start: int,
    end: int,
    total_size: int,
) -> bytes:
    expected_size = end - start + 1
    expected_content_range = f"bytes {start}-{end}/{total_size}"
    last_error: Exception | None = None
    for attempt in range(DOWNLOAD_ATTEMPTS):
        try:
            response = httpx.get(
                url,
                headers={
                    "User-Agent": DRYAD_BROWSER_USER_AGENT,
                    "Accept-Encoding": "identity",
                    "Range": f"bytes={start}-{end}",
                },
                follow_redirects=True,
                timeout=180,
            )
            response.raise_for_status()
            if (
                response.status_code != 206
                or str(response.headers.get("content-range") or "")
                != expected_content_range
                or len(response.content) != expected_size
            ):
                raise OSError(
                    "Dryad range response does not match the requested "
                    "source interval."
                )
            return response.content
        except (httpx.HTTPError, OSError) as error:
            last_error = error
            if attempt + 1 < DOWNLOAD_ATTEMPTS:
                time.sleep(2**attempt)
    assert last_error is not None
    raise last_error


def md5_file(path: Path) -> str:
    digest = hashlib.md5(usedforsecurity=False)
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
