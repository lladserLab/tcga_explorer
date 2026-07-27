from __future__ import annotations

import csv
from datetime import datetime
import gzip
import hashlib
import json
from pathlib import Path
import re
from typing import Any
import urllib.request

from app.repository.adapters.cbioportal import (
    USER_AGENT,
    download,
    write_tsv,
)
from app.repository.storage import sha256_file


GEO_ADAPTER_VERSION = "geo_supplementary_matrix_v1"


def materialize_geo_source(
    spec: dict[str, Any],
    source_dir: Path,
) -> tuple[dict[str, Path], str, str | None, dict[str, Any]]:
    source_spec = spec["source"]
    accession = str(source_spec.get("accession") or "").strip().upper()
    expression_url = str(
        source_spec.get("expression_url") or ""
    ).strip()
    soft_url = str(source_spec.get("soft_url") or "").strip()
    license_url = str(
        source_spec.get("license_evidence_url") or ""
    ).strip()
    if (
        not re.fullmatch(r"GSE[0-9]+", accession)
        or not expression_url
        or not soft_url
        or not license_url
    ):
        raise ValueError(
            "GEO sources require a GSE accession, expression_url, soft_url "
            "and license_evidence_url."
        )

    expression_path = source_dir / Path(
        expression_url.removesuffix("/")
    ).name
    soft_path = source_dir / Path(soft_url.removesuffix("/")).name
    license_path = source_dir / "NCBI_GEO_DISCLAIMER.html"
    download(expression_url, expression_path)
    download(soft_url, soft_path)
    download(license_url, license_path)

    series, samples = parse_geo_family_soft(soft_path)
    title_pattern = re.compile(
        str(source_spec.get("primary_sample_title_pattern") or ".+")
    )
    primary_samples = [
        sample
        for sample in samples
        if title_pattern.fullmatch(str(sample.get("title") or ""))
    ]
    primary_samples.sort(key=geo_sample_sort_key)
    expected_primary = source_spec.get("expected_primary_samples")
    if (
        expected_primary is not None
        and len(primary_samples) != int(expected_primary)
    ):
        raise ValueError(
            f"GEO primary-sample count changed: {len(primary_samples)} "
            f"!= {expected_primary}."
        )
    if len(primary_samples) < 10:
        raise ValueError("GEO source has fewer than 10 primary samples.")

    endpoint_spec = spec["endpoints"][0]
    time_characteristic = str(
        source_spec.get("time_characteristic")
        or endpoint_spec["time_column"]
    ).strip().casefold()
    event_characteristic = str(
        source_spec.get("event_characteristic")
        or endpoint_spec["event_column"]
    ).strip().casefold()
    age_characteristic = str(
        source_spec.get("age_characteristic") or ""
    ).strip().casefold()
    grade_characteristic = str(
        source_spec.get("grade_characteristic") or ""
    ).strip().casefold()
    patient_rows = []
    sample_rows = []
    events = 0
    censored = 0
    for sample in primary_samples:
        title = str(sample["title"])
        characteristics = sample["characteristics"]
        raw_time = clean(characteristics.get(time_characteristic))
        raw_event = clean(characteristics.get(event_characteristic))
        if raw_time is None or raw_event not in {"0", "1"}:
            continue
        try:
            time_days = float(raw_time)
        except ValueError:
            continue
        if time_days <= 0:
            continue
        event = int(raw_event)
        events += event
        censored += 1 - event
        patient_rows.append(
            {
                "PATIENT_ID": title,
                "GEO_ACCESSION": sample["geo_accession"],
                "OS_DAYS": format(time_days, ".17g"),
                "OS_STATUS": (
                    "1:DECEASED" if event else "0:CENSORED"
                ),
                "STAGE": "",
                "GRADE": (
                    clean(characteristics.get(grade_characteristic))
                    if grade_characteristic
                    else ""
                ),
                "SEX": str(
                    source_spec.get("sex_default") or ""
                ).strip(),
                "RACE": "",
                "AGE_AT_INDEX": (
                    clean(characteristics.get(age_characteristic))
                    if age_characteristic
                    else ""
                ),
                "GEO_SAMPLE_METADATA_JSON": canonical_json(sample),
            }
        )
        sample_rows.append(
            {
                "SAMPLE_ID": title,
                "PATIENT_ID": title,
                "SAMPLE_TYPE": str(
                    source_spec.get("sample_type") or "Primary Tumor"
                ),
                "GEO_ACCESSION": sample["geo_accession"],
                "SOURCE_TITLE": title,
                "GEO_SAMPLE_METADATA_JSON": canonical_json(sample),
            }
        )
    if len(patient_rows) < 10:
        raise ValueError(
            "Fewer than 10 GEO primary samples have usable survival."
        )

    expression_samples = read_compressed_csv_header(expression_path)[1:]
    expression_sample_set = set(expression_samples)
    missing_expression = sorted(
        row["SAMPLE_ID"]
        for row in sample_rows
        if row["SAMPLE_ID"] not in expression_sample_set
    )
    if missing_expression:
        raise ValueError(
            "GEO endpoint-complete samples are absent from the expression "
            f"matrix: {missing_expression[:5]}"
        )
    expected_expression = source_spec.get("expected_expression_columns")
    if (
        expected_expression is not None
        and len(expression_samples) != int(expected_expression)
    ):
        raise ValueError(
            f"GEO expression sample count changed: "
            f"{len(expression_samples)} != {expected_expression}."
        )

    patient_table = source_dir / "data_clinical_patient.txt"
    sample_table = source_dir / "data_clinical_sample.txt"
    write_tsv(
        patient_table,
        patient_rows,
        [
            "PATIENT_ID",
            "GEO_ACCESSION",
            "OS_DAYS",
            "OS_STATUS",
            "STAGE",
            "GRADE",
            "SEX",
            "RACE",
            "AGE_AT_INDEX",
            "GEO_SAMPLE_METADATA_JSON",
        ],
    )
    write_tsv(
        sample_table,
        sample_rows,
        [
            "SAMPLE_ID",
            "PATIENT_ID",
            "SAMPLE_TYPE",
            "GEO_ACCESSION",
            "SOURCE_TITLE",
            "GEO_SAMPLE_METADATA_JSON",
        ],
    )

    http_metadata = {
        "expression": fetch_url_metadata(expression_url),
        "family_soft": fetch_url_metadata(soft_url),
        "license": fetch_url_metadata(license_url),
    }
    metadata_path = source_dir / "geo_http_metadata.json"
    metadata_path.write_text(
        canonical_json(http_metadata) + "\n", encoding="utf-8"
    )
    series_path = source_dir / "geo_series_metadata.json"
    series_path.write_text(
        canonical_json(series) + "\n", encoding="utf-8"
    )
    source_paths = {
        "expression": expression_path,
        "patients": patient_table,
        "samples": sample_table,
        "geo_family_soft": soft_path,
        "geo_series_metadata": series_path,
        "geo_http_metadata": metadata_path,
        "license": license_path,
    }
    source_hashes = {
        role: sha256_file(path)
        for role, path in sorted(source_paths.items())
    }
    source_snapshot = hashlib.sha256(
        canonical_json(source_hashes).encode("utf-8")
    ).hexdigest()
    source_date = parse_geo_date(series.get("last_update_date"))
    return (
        source_paths,
        source_snapshot,
        source_date,
        {
            "source_api": "NCBI Gene Expression Omnibus",
            "source_accession": accession,
            "geo_series_title": series.get("title"),
            "geo_family_samples": len(samples),
            "geo_primary_samples": len(primary_samples),
            "geo_endpoint_complete_samples": len(patient_rows),
            "geo_events": events,
            "geo_censored": censored,
            "geo_expression_columns": len(expression_samples),
            "geo_expression_sha256": sha256_file(expression_path),
            "geo_family_soft_sha256": sha256_file(soft_path),
            "geo_primary_sample_title_pattern": title_pattern.pattern,
        },
    )


def parse_geo_family_soft(
    path: Path,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    series: dict[str, Any] = {}
    samples: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None

    def finish_sample() -> None:
        nonlocal current
        if current is None:
            return
        if not current.get("title") or not current.get("geo_accession"):
            raise ValueError("GEO SOFT sample is missing title or accession.")
        samples.append(current)
        current = None

    with gzip.open(
        path,
        mode="rt",
        encoding="utf-8",
        errors="strict",
    ) as handle:
        for raw_line in handle:
            line = raw_line.rstrip("\r\n")
            if line.startswith("^SAMPLE = "):
                finish_sample()
                current = {
                    "geo_accession": line.split("=", 1)[1].strip(),
                    "characteristics": {},
                }
                continue
            if line.startswith("^") and current is not None:
                finish_sample()
            if current is not None:
                if line.startswith("!Sample_title = "):
                    current["title"] = line.split("=", 1)[1].strip()
                elif line.startswith("!Sample_geo_accession = "):
                    current["geo_accession"] = line.split(
                        "=", 1
                    )[1].strip()
                elif line.startswith("!Sample_characteristics_ch1 = "):
                    text = line.split("=", 1)[1].strip()
                    key, separator, value = text.partition(":")
                    if separator:
                        normalized_key = key.strip().casefold()
                        existing = current["characteristics"].get(
                            normalized_key
                        )
                        if existing is not None and existing != value.strip():
                            raise ValueError(
                                "GEO sample contains conflicting "
                                f"characteristic {normalized_key!r}."
                            )
                        current["characteristics"][
                            normalized_key
                        ] = value.strip()
                continue
            if line.startswith("!Series_title = "):
                series["title"] = line.split("=", 1)[1].strip()
            elif line.startswith("!Series_last_update_date = "):
                series["last_update_date"] = line.split(
                    "=", 1
                )[1].strip()
            elif line.startswith("!Series_pubmed_id = "):
                series.setdefault("pubmed_ids", []).append(
                    line.split("=", 1)[1].strip()
                )
            elif line.startswith("!Series_supplementary_file = "):
                series.setdefault("supplementary_files", []).append(
                    line.split("=", 1)[1].strip()
                )
    finish_sample()
    if not samples:
        raise ValueError("GEO family SOFT contains no samples.")
    return series, samples


def read_compressed_csv_header(path: Path) -> list[str]:
    with gzip.open(
        path,
        mode="rt",
        newline="",
        encoding="utf-8",
        errors="strict",
    ) as handle:
        return next(csv.reader(handle))


def geo_sample_sort_key(sample: dict[str, Any]) -> tuple[Any, ...]:
    title = str(sample.get("title") or "")
    match = re.fullmatch(r"([A-Za-z_-]+)([0-9]+)", title)
    if match:
        return match.group(1), int(match.group(2)), title
    return title, 0, title


def fetch_url_metadata(url: str) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        method="HEAD",
        headers={"User-Agent": USER_AGENT},
    )
    with urllib.request.urlopen(request, timeout=180) as response:
        return {
            "url": response.geturl(),
            "status": response.status,
            "content_length": response.headers.get("Content-Length"),
            "content_type": response.headers.get("Content-Type"),
            "last_modified": response.headers.get("Last-Modified"),
            "etag": response.headers.get("ETag"),
        }


def parse_geo_date(value: Any) -> str | None:
    text = clean(value)
    if text is None:
        return None
    for template in ("%b %d %Y", "%Y-%m-%d"):
        try:
            parsed = datetime.strptime(text, template)
            return parsed.strftime("%Y-%m-%dT00:00:00Z")
        except ValueError:
            continue
    return None


def clean(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return (
        text
        if text and text.casefold() not in {"na", "n/a", "unknown"}
        else None
    )


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
