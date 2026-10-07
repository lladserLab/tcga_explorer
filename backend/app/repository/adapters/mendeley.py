from __future__ import annotations

import csv
from collections import Counter
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any
import urllib.parse

from app.repository.adapters.cbioportal import (
    download,
    request_json,
    write_tsv,
)
from app.repository.adapters.pmc import canonical_json
from app.repository.storage import sha256_file


MENDELEY_ADAPTER_VERSION = "mendeley_publication_v1"
DEFAULT_MENDELEY_API = "https://data.mendeley.com/public-api"
CLINICAL_SAMPLE_PATTERN = re.compile(r"^KR-3539-(\d+)$")
MATRIX_SAMPLE_PATTERN = re.compile(r"^3539-KR-(\d+)(?:-|$)")


def materialize_mendeley_source(
    spec: dict[str, Any],
    source_dir: Path,
) -> tuple[dict[str, Path], str, str | None, dict[str, Any]]:
    source_spec = spec["source"]
    dataset_id = str(source_spec.get("dataset_id") or "").strip()
    dataset_version = int(source_spec.get("dataset_version") or 0)
    api_base = str(
        source_spec.get("api_base") or DEFAULT_MENDELEY_API
    ).rstrip("/")
    if not dataset_id or dataset_version <= 0:
        raise ValueError(
            "Mendeley sources require dataset_id and a positive "
            "dataset_version."
        )

    quoted_dataset_id = urllib.parse.quote(dataset_id, safe="")
    snapshot_url = (
        f"{api_base}/datasets/{quoted_dataset_id}/snapshot/"
        f"{dataset_version}"
    )
    snapshot = request_json(snapshot_url)
    validate_mendeley_snapshot(snapshot, source_spec)

    files_url = (
        f"{api_base}/datasets/{quoted_dataset_id}/files?"
        + urllib.parse.urlencode(
            {"folder_id": "root", "version": dataset_version}
        )
    )
    remote_files = request_json(files_url)
    if not isinstance(remote_files, list):
        raise ValueError("Mendeley files endpoint returned an invalid payload.")
    remote_by_id = {
        str(row.get("id") or ""): row
        for row in remote_files
        if str(row.get("id") or "").strip()
    }

    downloaded: dict[str, Path] = {}
    pinned_files: dict[str, dict[str, Any]] = {}
    required_roles = {"clinical", "expression", "analysis_script"}
    declared_files = source_spec.get("files") or {}
    if not required_roles.issubset(declared_files):
        raise ValueError(
            "Mendeley sources require clinical, expression and "
            "analysis_script file pins."
        )
    for role, file_spec in declared_files.items():
        file_id = str(file_spec.get("file_id") or "").strip()
        remote = remote_by_id.get(file_id)
        if remote is None:
            raise ValueError(
                f"Mendeley dataset is missing pinned {role} file {file_id}."
            )
        pin = validate_mendeley_file_pin(file_spec, remote)
        target = source_dir / pin["name"]
        download(pin["download_url"], target)
        if target.stat().st_size != pin["size"]:
            raise ValueError(
                f"Downloaded Mendeley {role} file failed size validation."
            )
        if sha256_file(target) != pin["sha256"]:
            raise ValueError(
                f"Downloaded Mendeley {role} file failed SHA-256 validation."
            )
        downloaded[role] = target
        pinned_files[role] = {
            key: value
            for key, value in pin.items()
            if key != "download_url"
        }

    clinical_rows = read_csv_records(downloaded["clinical"])
    matrix_header = read_matrix_header(downloaded["expression"])
    matrix_sample_keys = parse_matrix_sample_columns(matrix_header)
    clinical_spec = source_spec.get("clinical") or {}
    eligible_rows, eligibility_summary = select_validation_rows(
        clinical_rows,
        set(matrix_sample_keys),
        excluded_sample_keys={
            str(value).strip()
            for value in clinical_spec.get("excluded_sample_keys") or []
            if str(value).strip()
        },
    )
    validate_expected_cohort(eligible_rows, source_spec)

    patient_table = source_dir / "data_clinical_patient.txt"
    sample_table = source_dir / "data_clinical_sample.txt"
    patient_rows: list[dict[str, str]] = []
    sample_rows: list[dict[str, str]] = []
    for selected in eligible_rows:
        source_row = selected["source_row"]
        patient_id = selected["patient_id"]
        sample_key = selected["sample_key"]
        raw_metadata = canonical_json(source_row)
        patient_rows.append(
            {
                "PATIENT_ID": patient_id,
                "RFS_DAYS": str(selected["time_days"]),
                "RFS_STATUS": str(selected["event"]),
                "MENDELEY_SAMPLE_KEY": sample_key,
                **source_row,
                "MENDELEY_CLINICAL_METADATA_JSON": raw_metadata,
            }
        )
        sample_rows.append(
            {
                "SAMPLE_ID": patient_id,
                "PATIENT_ID": patient_id,
                "SAMPLE_TYPE": "Primary ccRCC tumor",
                "MENDELEY_SAMPLE_KEY": sample_key,
                "MENDELEY_CLINICAL_METADATA_JSON": raw_metadata,
            }
        )

    clinical_fields = list(clinical_rows[0])
    write_tsv(
        patient_table,
        patient_rows,
        [
            "PATIENT_ID",
            "RFS_DAYS",
            "RFS_STATUS",
            "MENDELEY_SAMPLE_KEY",
            *clinical_fields,
            "MENDELEY_CLINICAL_METADATA_JSON",
        ],
    )
    write_tsv(
        sample_table,
        sample_rows,
        [
            "SAMPLE_ID",
            "PATIENT_ID",
            "SAMPLE_TYPE",
            "MENDELEY_SAMPLE_KEY",
            "MENDELEY_CLINICAL_METADATA_JSON",
        ],
    )

    selected_expression = source_dir / "data_expression_selected.tsv"
    expression_summary = materialize_mendeley_counts_matrix(
        downloaded["expression"],
        selected_expression,
        [
            (row["sample_key"], row["patient_id"])
            for row in eligible_rows
        ],
    )

    snapshot_path = source_dir / "mendeley_dataset_snapshot.json"
    snapshot_path.write_text(
        canonical_json(snapshot) + "\n",
        encoding="utf-8",
    )
    source_snapshot_payload = {
        "dataset_id": dataset_id,
        "dataset_version": dataset_version,
        "doi": str(snapshot.get("doi") or ""),
        "license": str(
            (snapshot.get("licence") or {}).get("short_name") or ""
        ),
        "published_at": str(snapshot.get("publish_date") or ""),
        "files": pinned_files,
    }
    source_snapshot = hashlib.sha256(
        canonical_json(source_snapshot_payload).encode("utf-8")
    ).hexdigest()
    source_manifest_path = source_dir / "mendeley_source_manifest.json"
    source_manifest_path.write_text(
        canonical_json(
            {
                "schema_version": (
                    "tcga-trace-mendeley-source-manifest-v1"
                ),
                **source_snapshot_payload,
                "snapshot_url": snapshot_url,
                "files_url": files_url,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    events = sum(int(row["event"]) for row in eligible_rows)
    return (
        {
            "expression": selected_expression,
            "patients": patient_table,
            "samples": sample_table,
            "clinical_source": downloaded["clinical"],
            "expression_source": downloaded["expression"],
            "analysis_script": downloaded["analysis_script"],
            "dataset_metadata": snapshot_path,
            "source_manifest": source_manifest_path,
            "license": snapshot_path,
        },
        source_snapshot,
        str(snapshot.get("publish_date") or "") or None,
        {
            "source_api": api_base,
            "source_mendeley_dataset_id": dataset_id,
            "source_mendeley_dataset_version": dataset_version,
            "source_doi": str(snapshot.get("doi") or ""),
            "source_license": str(
                (snapshot.get("licence") or {}).get("short_name") or ""
            ),
            "source_clinical_rows": len(clinical_rows),
            "source_eligible_patients": len(eligible_rows),
            "source_events": events,
            "source_censored": len(eligible_rows) - events,
            "source_eligibility": eligibility_summary,
            "source_pinned_files": pinned_files,
            **expression_summary,
        },
    )


def validate_mendeley_snapshot(
    snapshot: Any,
    source_spec: dict[str, Any],
) -> None:
    if not isinstance(snapshot, dict):
        raise ValueError("Mendeley snapshot endpoint returned invalid data.")
    dataset_id = str(source_spec.get("dataset_id") or "").strip()
    dataset_version = int(source_spec.get("dataset_version") or 0)
    if (
        str(snapshot.get("id") or "") != dataset_id
        or int(snapshot.get("version") or 0) != dataset_version
    ):
        raise ValueError("Mendeley API returned the wrong dataset snapshot.")
    if snapshot.get("is_confidential") is not False:
        raise ValueError("Mendeley dataset is not a public release.")
    expected_doi = str(source_spec.get("expected_doi") or "").strip()
    if expected_doi and str(snapshot.get("doi") or "") != expected_doi:
        raise ValueError("Mendeley DOI does not match the reviewed pin.")
    expected_license = str(
        source_spec.get("expected_license") or ""
    ).strip()
    observed_license = str(
        (snapshot.get("licence") or {}).get("short_name") or ""
    ).strip()
    if (
        not observed_license
        or expected_license
        and observed_license != expected_license
    ):
        raise ValueError(
            "Mendeley license does not match the reviewed pin: "
            f"{observed_license!r}."
        )


def validate_mendeley_file_pin(
    file_spec: dict[str, Any],
    remote: dict[str, Any],
) -> dict[str, Any]:
    file_id = str(file_spec.get("file_id") or "").strip()
    expected_name = str(file_spec.get("name") or "").strip()
    expected_size = int(file_spec.get("size") or 0)
    expected_sha256 = str(
        file_spec.get("sha256") or ""
    ).strip().lower()
    details = remote.get("content_details") or {}
    if str(remote.get("id") or "") != file_id:
        raise ValueError("Mendeley file ID does not match its reviewed pin.")
    if str(remote.get("filename") or "") != expected_name:
        raise ValueError(
            f"Mendeley filename changed for file {file_id!r}."
        )
    if (
        expected_size <= 0
        or int(details.get("size") or remote.get("size") or 0)
        != expected_size
    ):
        raise ValueError(
            f"Mendeley size does not match the pin for {expected_name!r}."
        )
    remote_sha256 = str(
        details.get("sha256_hash") or ""
    ).strip().lower()
    if (
        len(expected_sha256) != 64
        or remote_sha256 != expected_sha256
    ):
        raise ValueError(
            f"Mendeley SHA-256 does not match the pin for {expected_name!r}."
        )
    download_url = str(details.get("download_url") or "").strip()
    if not download_url.startswith("https://"):
        raise ValueError(
            f"Mendeley download URL is invalid for {expected_name!r}."
        )
    return {
        "file_id": file_id,
        "name": expected_name,
        "size": expected_size,
        "sha256": expected_sha256,
        "download_url": download_url,
    }


def select_validation_rows(
    rows: list[dict[str, str]],
    matrix_sample_keys: set[str],
    *,
    excluded_sample_keys: set[str],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    exclusions: Counter[str] = Counter()
    seen_patients: set[str] = set()
    seen_samples: set[str] = set()
    for row in rows:
        patient_id = str(row.get("Record ID") or "").strip()
        raw_rna_id = str(row.get("rna seq") or "").strip()
        match = CLINICAL_SAMPLE_PATTERN.fullmatch(raw_rna_id)
        if not patient_id or match is None:
            exclusions["missing_or_invalid_rna_identifier"] += 1
            continue
        if "DUPLICATE" in str(row.get("Batch ID") or "").upper():
            exclusions["source_duplicate_row"] += 1
            continue
        sample_key = match.group(1)
        if sample_key not in matrix_sample_keys:
            exclusions["expression_unlinked"] += 1
            continue
        if (
            str(
                row.get("Metastasectomy or [met] Biopsy") or ""
            ).strip()
            != "No"
        ):
            exclusions["not_primary_resection_profile"] += 1
            continue
        if (
            str(row.get("Primary Histology") or "").strip().casefold()
            != "ccrcc"
        ):
            exclusions["histology_mismatch"] += 1
            continue
        if sample_key in excluded_sample_keys:
            exclusions["source_qc_outlier"] += 1
            continue
        endpoint = parse_recurrence_endpoint(row)
        if endpoint is None:
            exclusions["missing_or_invalid_endpoint"] += 1
            continue
        if patient_id in seen_patients or sample_key in seen_samples:
            raise ValueError(
                "Eligible Mendeley patient or RNA sample is duplicated: "
                f"{patient_id!r}, {sample_key!r}."
            )
        seen_patients.add(patient_id)
        seen_samples.add(sample_key)
        selected.append(
            {
                "patient_id": patient_id,
                "sample_key": sample_key,
                **endpoint,
                "source_row": row,
            }
        )
    selected.sort(
        key=lambda row: (
            str(row["patient_id"]),
            str(row["sample_key"]),
        )
    )
    events = sum(int(row["event"]) for row in selected)
    return selected, {
        "eligible_patients": len(selected),
        "events": events,
        "censored": len(selected) - events,
        "exclusions": dict(sorted(exclusions.items())),
        "rules": [
            "valid public RNA identifier linked to the pinned count matrix",
            "source duplicate rows excluded",
            "primary resection profile only",
            "exact clear-cell RCC histology",
            "source-listed RNA quality outliers excluded",
            "exact recurrence date for events",
            "exact last-contact date for censored observations",
            "positive interval from resection or complete response",
        ],
    }


def parse_recurrence_endpoint(
    row: dict[str, str],
) -> dict[str, int] | None:
    recurrence = str(row.get("Recurrence") or "").strip().casefold()
    if recurrence not in {"yes", "no"}:
        return None
    origin = parse_source_date(row.get("Date of resection or CR"))
    endpoint_column = (
        "Date of recurrence"
        if recurrence == "yes"
        else "Date of last contact"
    )
    endpoint = parse_source_date(row.get(endpoint_column))
    if origin is None or endpoint is None:
        return None
    time_days = (endpoint - origin).days
    if time_days <= 0:
        return None
    return {
        "time_days": time_days,
        "event": int(recurrence == "yes"),
    }


def parse_source_date(value: Any) -> datetime | None:
    cleaned = str(value or "").strip()
    if not cleaned:
        return None
    try:
        return datetime.strptime(cleaned, "%m/%d/%y")
    except ValueError:
        return None


def read_matrix_header(path: Path) -> list[str]:
    with path.open(
        newline="", encoding="utf-8", errors="strict"
    ) as handle:
        return next(csv.reader(handle, delimiter="\t"))


def parse_matrix_sample_columns(header: list[str]) -> dict[str, int]:
    if len(header) < 3 or header[:2] != ["Name", "Description"]:
        raise ValueError("Mendeley count matrix has an unexpected header.")
    indexes: dict[str, int] = {}
    for index, value in enumerate(header[2:], start=2):
        match = MATRIX_SAMPLE_PATTERN.match(str(value).strip())
        if match is None:
            raise ValueError(
                f"Cannot parse Mendeley RNA column {value!r}."
            )
        sample_key = match.group(1)
        if sample_key in indexes:
            raise ValueError(
                f"Mendeley RNA sample {sample_key!r} occurs twice."
            )
        indexes[sample_key] = index
    return indexes


def materialize_mendeley_counts_matrix(
    source: Path,
    target: Path,
    selected_samples: list[tuple[str, str]],
    *,
    minimum_gene_rows: int = 10_000,
) -> dict[str, Any]:
    with source.open(
        newline="", encoding="utf-8", errors="strict"
    ) as handle:
        reader = csv.reader(handle, delimiter="\t")
        header = next(reader)
        sample_indexes = parse_matrix_sample_columns(header)
        missing = [
            sample_key
            for sample_key, _ in selected_samples
            if sample_key not in sample_indexes
        ]
        if missing:
            raise ValueError(
                "Eligible clinical samples are absent from the Mendeley "
                f"matrix: {missing[:5]}"
            )
        indexes = [
            sample_indexes[sample_key]
            for sample_key, _ in selected_samples
        ]
        library_sizes = [0.0] * len(indexes)
        symbol_counts: Counter[str] = Counter()
        gene_rows = 0
        blank_symbol_rows = 0
        for row in reader:
            if not row:
                continue
            if len(row) != len(header):
                raise ValueError(
                    "Mendeley count-matrix row width is inconsistent."
                )
            values = parse_nonnegative_counts(row, indexes)
            library_sizes = [
                total + value
                for total, value in zip(
                    library_sizes, values, strict=True
                )
            ]
            symbol = str(row[1]).strip().upper()
            if symbol:
                symbol_counts[symbol] += 1
            else:
                blank_symbol_rows += 1
            gene_rows += 1
    if gene_rows < minimum_gene_rows:
        raise ValueError(
            "Mendeley expression matrix has fewer than "
            f"{minimum_gene_rows:,} gene rows."
        )
    if any(value <= 0 for value in library_sizes):
        raise ValueError(
            "Mendeley count matrix contains an empty selected library."
        )

    target.parent.mkdir(parents=True, exist_ok=True)
    with source.open(
        newline="", encoding="utf-8", errors="strict"
    ) as input_handle, target.open(
        "w", newline="", encoding="utf-8"
    ) as output_handle:
        reader = csv.reader(input_handle, delimiter="\t")
        next(reader)
        writer = csv.writer(
            output_handle, delimiter="\t", lineterminator="\n"
        )
        patient_ids = [
            patient_id for _, patient_id in selected_samples
        ]
        writer.writerow(["Hugo_Symbol", *patient_ids])
        written_rows = 0
        for row in reader:
            if not row:
                continue
            symbol = str(row[1]).strip().upper()
            if not symbol or symbol_counts[symbol] != 1:
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
            "Mendeley matrix has fewer than "
            f"{minimum_gene_rows:,} unambiguous gene symbols."
        )
    duplicated_symbols = {
        symbol: count
        for symbol, count in symbol_counts.items()
        if count > 1
    }
    return {
        "source_expression_layout": "wide_gene_counts_gct",
        "source_expression_columns": len(header) - 2,
        "selected_expression_columns": len(selected_samples),
        "source_expression_gene_rows": gene_rows,
        "source_blank_symbol_rows": blank_symbol_rows,
        "source_unique_nonempty_symbols": len(symbol_counts),
        "source_duplicated_symbol_labels": len(duplicated_symbols),
        "source_duplicated_symbol_rows": sum(
            duplicated_symbols.values()
        ),
        "normalized_expression_gene_rows": written_rows,
        "expression_normalization": "log2(CPM + 1)",
        "expression_library_size_basis": "all source gene rows",
        "expression_library_sizes": {
            patient_id: format(value, ".17g")
            for (_, patient_id), value in zip(
                selected_samples, library_sizes, strict=True
            )
        },
    }


def parse_nonnegative_counts(
    row: list[str],
    indexes: list[int],
) -> list[float]:
    try:
        values = [float(row[index]) for index in indexes]
    except (IndexError, ValueError) as error:
        raise ValueError(
            f"Invalid Mendeley count at feature {row[:2]!r}."
        ) from error
    if any(not math.isfinite(value) or value < 0 for value in values):
        raise ValueError(
            f"Non-finite or negative Mendeley count at {row[:2]!r}."
        )
    return values


def read_csv_records(path: Path) -> list[dict[str, str]]:
    with path.open(
        newline="", encoding="utf-8-sig", errors="strict"
    ) as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError("Mendeley clinical table is empty.")
    return [
        {
            str(key).strip(): (
                "" if value is None else str(value).strip()
            )
            for key, value in row.items()
        }
        for row in rows
    ]


def validate_expected_cohort(
    selected: list[dict[str, Any]],
    source_spec: dict[str, Any],
) -> None:
    expected_patients = int(
        source_spec.get("expected_eligible_patients") or 0
    )
    expected_events = int(source_spec.get("expected_events") or 0)
    expected_censored = int(source_spec.get("expected_censored") or 0)
    observed_events = sum(int(row["event"]) for row in selected)
    observed_censored = len(selected) - observed_events
    if (
        expected_patients
        and len(selected) != expected_patients
        or expected_events
        and observed_events != expected_events
        or expected_censored
        and observed_censored != expected_censored
    ):
        raise ValueError(
            "Mendeley eligible cohort changed from the reviewed pin: "
            f"patients={len(selected)}, events={observed_events}, "
            f"censored={observed_censored}."
        )
