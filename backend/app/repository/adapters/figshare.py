from __future__ import annotations

import csv
import hashlib
import json
import math
from pathlib import Path
from typing import Any
import urllib.parse

from app.repository.adapters.cbioportal import (
    download,
    request_json,
    write_tsv,
)
from app.repository.adapters.pmc import (
    canonical_json,
    row_passes_rules,
)
from app.repository.storage import sha256_file


FIGSHARE_ADAPTER_VERSION = "figshare_publication_v1"
DEFAULT_FIGSHARE_API = "https://api.figshare.com/v2"


def materialize_figshare_source(
    spec: dict[str, Any],
    source_dir: Path,
) -> tuple[dict[str, Path], str, str | None, dict[str, Any]]:
    source_spec = spec["source"]
    article_id = int(source_spec.get("article_id") or 0)
    private_link = str(source_spec.get("private_link") or "").strip()
    api_base = str(
        source_spec.get("api_base") or DEFAULT_FIGSHARE_API
    ).rstrip("/")
    if article_id <= 0:
        raise ValueError("Figshare sources require a positive article_id.")

    query = (
        f"?{urllib.parse.urlencode({'private_link': private_link})}"
        if private_link
        else ""
    )
    article_url = f"{api_base}/articles/{article_id}{query}"
    article = request_json(article_url)
    if int(article.get("id") or 0) != article_id:
        raise ValueError("Figshare API returned the wrong article.")

    license_name = str(
        (article.get("license") or {}).get("name") or ""
    ).strip()
    expected_license = str(
        source_spec.get("expected_license") or ""
    ).strip()
    if not license_name or (
        expected_license and license_name != expected_license
    ):
        raise ValueError(
            "Figshare license does not match the reviewed study "
            f"specification: {license_name!r}."
        )

    remote_files = {
        int(item["id"]): item
        for item in article.get("files") or []
        if item.get("id")
    }
    downloaded: dict[str, Path] = {}
    pinned_files: dict[str, dict[str, Any]] = {}
    for role in ("clinical", "expression"):
        file_spec = (source_spec.get("files") or {}).get(role) or {}
        file_id = int(file_spec.get("file_id") or 0)
        remote = remote_files.get(file_id)
        if remote is None:
            raise ValueError(
                f"Figshare article is missing pinned {role} file {file_id}."
            )
        expected_name = str(file_spec.get("name") or "").strip()
        remote_name = str(remote.get("name") or "").strip()
        if not expected_name or remote_name != expected_name:
            raise ValueError(
                f"Figshare {role} filename changed: {remote_name!r}."
            )
        expected_md5 = str(file_spec.get("md5") or "").strip().lower()
        remote_md5 = str(remote.get("supplied_md5") or "").strip().lower()
        if (
            len(expected_md5) != 32
            or remote_md5 != expected_md5
        ):
            raise ValueError(
                f"Figshare {role} MD5 does not match the pinned value."
            )
        target = source_dir / expected_name
        download(str(remote["download_url"]), target)
        if md5_file(target) != expected_md5:
            raise ValueError(
                f"Downloaded Figshare {role} file failed MD5 validation."
            )
        downloaded[role] = target
        pinned_files[role] = {
            "file_id": file_id,
            "name": expected_name,
            "size": int(remote.get("size") or target.stat().st_size),
            "md5": expected_md5,
            "download_url": str(remote["download_url"]),
            "sha256": sha256_file(target),
        }

    clinical_spec = source_spec.get("clinical") or {}
    clinical_rows = read_csv_records(
        downloaded["clinical"],
        delimiter=str(clinical_spec.get("delimiter") or ","),
    )
    sample_id_column = str(
        clinical_spec.get("sample_id_column") or ""
    ).strip()
    patient_id_column = str(
        clinical_spec.get("patient_id_column") or ""
    ).strip()
    if not sample_id_column or not patient_id_column:
        raise ValueError(
            "Figshare clinical sample and patient ID columns are required."
        )

    expression_spec = source_spec.get("expression") or {}
    expression_sample_ids = set(
        read_counts_sample_ids(
            downloaded["expression"],
            delimiter=str(expression_spec.get("delimiter") or ","),
            sample_start_column=int(
                expression_spec.get("sample_start_column") or 3
            ),
        )
    )
    eligible_rows = [
        row
        for row in clinical_rows
        if row_passes_rules(
            row, clinical_spec.get("eligibility_rules") or []
        )
        and str(row.get(sample_id_column) or "").strip()
        in expression_sample_ids
    ]
    eligible_rows.sort(
        key=lambda row: (
            str(row.get(patient_id_column) or "").strip(),
            str(row.get(sample_id_column) or "").strip(),
        )
    )
    if len(eligible_rows) < 10:
        raise ValueError(
            "Figshare source has fewer than 10 eligible clinical rows."
        )

    sample_ids = [
        str(row.get(sample_id_column) or "").strip()
        for row in eligible_rows
    ]
    patient_ids = [
        str(row.get(patient_id_column) or "").strip()
        for row in eligible_rows
    ]
    if (
        any(not value for value in sample_ids)
        or len(sample_ids) != len(set(sample_ids))
        or any(not value for value in patient_ids)
    ):
        raise ValueError(
            "Figshare eligible sample IDs must be unique and all patient "
            "IDs must be present."
        )
    ensure_patient_fields_are_consistent(
        eligible_rows,
        patient_id_column=patient_id_column,
        fields=clinical_spec.get("patient_consistency_columns") or [],
    )

    patient_rows_by_id: dict[str, dict[str, str]] = {}
    sample_rows = []
    sample_type = str(
        clinical_spec.get("sample_type") or "Primary tumor"
    )
    for row, patient_id, sample_id in zip(
        eligible_rows, patient_ids, sample_ids, strict=True
    ):
        patient_rows_by_id.setdefault(
            patient_id,
            {
                "PATIENT_ID": patient_id,
                **row,
                "FIGSHARE_CLINICAL_METADATA_JSON": canonical_json(row),
            },
        )
        sample_rows.append(
            {
                "SAMPLE_ID": sample_id,
                "PATIENT_ID": patient_id,
                "SAMPLE_TYPE": sample_type,
                "FIGSHARE_CLINICAL_METADATA_JSON": canonical_json(row),
            }
        )

    patient_table = source_dir / "data_clinical_patient.txt"
    sample_table = source_dir / "data_clinical_sample.txt"
    patient_fields = [
        "PATIENT_ID",
        *[
            field
            for field in clinical_rows[0]
            if field != "PATIENT_ID"
        ],
        "FIGSHARE_CLINICAL_METADATA_JSON",
    ]
    write_tsv(
        patient_table,
        list(patient_rows_by_id.values()),
        patient_fields,
    )
    write_tsv(
        sample_table,
        sample_rows,
        [
            "SAMPLE_ID",
            "PATIENT_ID",
            "SAMPLE_TYPE",
            "FIGSHARE_CLINICAL_METADATA_JSON",
        ],
    )

    filtered_expression = source_dir / "data_expression_selected.tsv"
    expression_summary = materialize_figshare_counts_matrix(
        downloaded["expression"],
        filtered_expression,
        sample_ids,
        delimiter=str(expression_spec.get("delimiter") or ","),
        feature_column=str(
            expression_spec.get("feature_column") or ""
        ).strip(),
        sample_start_column=int(
            expression_spec.get("sample_start_column") or 3
        ),
    )

    article_metadata_path = source_dir / "figshare_article.json"
    article_metadata_path.write_text(
        canonical_json(article) + "\n",
        encoding="utf-8",
    )
    source_snapshot_payload = {
        "article_id": article_id,
        "article_version": int(article.get("version") or 0),
        "license": license_name,
        "files": pinned_files,
    }
    source_snapshot = hashlib.sha256(
        canonical_json(source_snapshot_payload).encode("utf-8")
    ).hexdigest()
    source_manifest_path = source_dir / "figshare_source_manifest.json"
    source_manifest_path.write_text(
        canonical_json(
            {
                "schema_version": (
                    "tcga-trace-figshare-source-manifest-v1"
                ),
                **source_snapshot_payload,
                "article_url": article_url,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    return (
        {
            "expression": filtered_expression,
            "patients": patient_table,
            "samples": sample_table,
            "clinical_source": downloaded["clinical"],
            "expression_source": downloaded["expression"],
            "article_metadata": article_metadata_path,
            "source_manifest": source_manifest_path,
            "license": article_metadata_path,
        },
        source_snapshot,
        str(source_spec.get("publication_date") or "") or None,
        {
            "source_api": api_base,
            "source_figshare_article_id": article_id,
            "source_figshare_article_version": int(
                article.get("version") or 0
            ),
            "source_license": license_name,
            "source_clinical_rows": len(clinical_rows),
            "source_eligible_rows": len(eligible_rows),
            "source_eligible_patients": len(patient_rows_by_id),
            "source_eligibility_rules": (
                clinical_spec.get("eligibility_rules") or []
            ),
            "source_pinned_files": pinned_files,
            **expression_summary,
        },
    )


def materialize_figshare_counts_matrix(
    source: Path,
    target: Path,
    sample_ids: list[str],
    *,
    delimiter: str,
    feature_column: str,
    sample_start_column: int,
    minimum_gene_rows: int = 10_000,
) -> dict[str, Any]:
    if not feature_column or sample_start_column < 2:
        raise ValueError(
            "Figshare count matrices require a feature column and a valid "
            "sample_start_column."
        )
    with source.open(
        newline="", encoding="utf-8-sig", errors="strict"
    ) as handle:
        reader = csv.reader(handle, delimiter=delimiter)
        header = next(reader)
        try:
            feature_index = header.index(feature_column)
        except ValueError as error:
            raise ValueError(
                f"Count-matrix feature column {feature_column!r} is absent."
            ) from error
        sample_start_index = sample_start_column - 1
        source_index = {
            value.strip(): index
            for index, value in enumerate(header[sample_start_index:])
            if value.strip()
        }
        source_index = {
            sample_id: sample_start_index + index
            for sample_id, index in source_index.items()
        }
        missing = [
            sample_id
            for sample_id in sample_ids
            if sample_id not in source_index
        ]
        if missing:
            raise ValueError(
                "Clinical samples are absent from the Figshare count "
                f"matrix: {missing[:5]}"
            )
        indexes = [source_index[sample_id] for sample_id in sample_ids]
        library_sizes = [0.0] * len(sample_ids)
        gene_rows = 0
        for row in reader:
            if not row:
                continue
            if len(row) != len(header):
                raise ValueError(
                    "Figshare count-matrix row width is inconsistent."
                )
            feature = row[feature_index].strip()
            if not feature:
                continue
            values = parse_nonnegative_counts(row, indexes, feature)
            library_sizes = [
                current + value
                for current, value in zip(
                    library_sizes, values, strict=True
                )
            ]
            gene_rows += 1
    if gene_rows < minimum_gene_rows:
        raise ValueError(
            "Figshare expression matrix has fewer than "
            f"{minimum_gene_rows:,} gene rows."
        )
    if any(value <= 0 for value in library_sizes):
        raise ValueError(
            "Figshare count matrix contains an empty selected library."
        )

    with source.open(
        newline="", encoding="utf-8-sig", errors="strict"
    ) as input_handle, target.open(
        "w", newline="", encoding="utf-8"
    ) as output_handle:
        reader = csv.reader(input_handle, delimiter=delimiter)
        next(reader)
        writer = csv.writer(
            output_handle, delimiter="\t", lineterminator="\n"
        )
        writer.writerow([feature_column, *sample_ids])
        written_rows = 0
        for row in reader:
            if not row:
                continue
            feature = row[feature_index].strip()
            if not feature:
                continue
            values = parse_nonnegative_counts(row, indexes, feature)
            normalized = [
                math.log2((value / library_size) * 1_000_000.0 + 1.0)
                for value, library_size in zip(
                    values, library_sizes, strict=True
                )
            ]
            writer.writerow(
                [feature, *(format(value, ".17g") for value in normalized)]
            )
            written_rows += 1
    return {
        "source_expression_layout": "wide_gene_counts_csv",
        "source_expression_columns": len(header) - sample_start_index,
        "selected_expression_columns": len(sample_ids),
        "source_expression_gene_rows": gene_rows,
        "normalized_expression_gene_rows": written_rows,
        "source_expression_feature_column": feature_column,
        "source_expression_sample_start_column": sample_start_column,
        "expression_normalization": "log2(CPM + 1)",
        "expression_library_sizes": {
            sample_id: format(value, ".17g")
            for sample_id, value in zip(
                sample_ids, library_sizes, strict=True
            )
        },
    }


def parse_nonnegative_counts(
    row: list[str],
    indexes: list[int],
    feature: str,
) -> list[float]:
    try:
        values = [float(row[index]) for index in indexes]
    except (IndexError, ValueError) as error:
        raise ValueError(
            f"Invalid count value at feature {feature!r}."
        ) from error
    if any(not math.isfinite(value) or value < 0 for value in values):
        raise ValueError(
            f"Non-finite or negative count at feature {feature!r}."
        )
    return values


def read_counts_sample_ids(
    source: Path,
    *,
    delimiter: str,
    sample_start_column: int,
) -> list[str]:
    with source.open(
        newline="", encoding="utf-8-sig", errors="strict"
    ) as handle:
        header = next(csv.reader(handle, delimiter=delimiter))
    sample_start_index = sample_start_column - 1
    if sample_start_index >= len(header):
        raise ValueError(
            "Figshare count-matrix sample_start_column is outside the "
            "header."
        )
    sample_ids = [
        value.strip()
        for value in header[sample_start_index:]
        if value.strip()
    ]
    if len(sample_ids) != len(set(sample_ids)):
        raise ValueError("Figshare expression sample IDs are duplicated.")
    return sample_ids


def read_csv_records(
    path: Path,
    *,
    delimiter: str,
) -> list[dict[str, str]]:
    with path.open(
        newline="", encoding="utf-8-sig", errors="strict"
    ) as handle:
        rows = list(csv.DictReader(handle, delimiter=delimiter))
    if not rows:
        raise ValueError("Figshare clinical table is empty.")
    return [
        {
            str(key).strip(): (
                "" if value is None else str(value).strip()
            )
            for key, value in row.items()
        }
        for row in rows
    ]


def ensure_patient_fields_are_consistent(
    rows: list[dict[str, str]],
    *,
    patient_id_column: str,
    fields: list[str],
) -> None:
    observed: dict[tuple[str, str], str] = {}
    for row in rows:
        patient_id = str(row.get(patient_id_column) or "").strip()
        for field in fields:
            value = str(row.get(field) or "").strip()
            key = (patient_id, str(field))
            previous = observed.setdefault(key, value)
            if previous != value:
                raise ValueError(
                    f"Patient {patient_id!r} has conflicting {field!r} "
                    "values across expression samples."
                )


def md5_file(path: Path) -> str:
    digest = hashlib.md5(usedforsecurity=False)
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
