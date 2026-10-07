from __future__ import annotations

from array import array
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
from typing import Any
import urllib.parse
import zipfile

from app.repository.adapters.cbioportal import download, write_tsv
from app.repository.adapters.pmc import (
    canonical_json,
    parse_gencode_gene_map,
)
from app.repository.storage import sha256_file


BIOSTUDIES_ADAPTER_VERSION = "biostudies_arrayexpress_v2"
UVM_FEATURECOUNTS_LAYOUT = "featurecounts_archives_uvm"
PROCESSED_FPKM_SDRF_LAYOUT = "processed_fpkm_matrix_sdrf"
UVM_CLINICAL_ROW = re.compile(
    r"^(\d+) ([\d.]+) (ND|[\d.]+) (T\d) (Yes|No) "
    r"(?:(p\.[A-Z]\d+[A-Z]) )?"
    r"(Spindle cell|Epithelioid cell|Mixed) "
    r"(\d+) (NED|AWD|DFD|DFO)$"
)
UVM_COUNT_FILENAME = re.compile(
    r"^[A-Z]\d+[TR](\d+)\.hg19\.ensembl\.gene_id\.counts$"
)


def materialize_biostudies_download(url: str, path: Path) -> None:
    cache_dir = str(
        os.environ.get("BIOSTUDIES_DOWNLOAD_CACHE_DIR") or ""
    ).strip()
    cache_name = Path(urllib.parse.urlparse(url).path).name
    cached = Path(cache_dir) / cache_name if cache_dir else None
    if cached is not None and cached.is_file():
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(cached, path)
        return
    download(url, path)


def materialize_biostudies_source(
    spec: dict[str, Any],
    source_dir: Path,
) -> tuple[dict[str, Path], str, str | None, dict[str, Any]]:
    source_spec = spec["source"]
    accession = str(source_spec.get("accession") or "").strip()
    if not accession:
        raise ValueError("BioStudies sources require an accession.")
    layout = str(
        source_spec.get("layout") or UVM_FEATURECOUNTS_LAYOUT
    ).strip()
    if layout not in {
        UVM_FEATURECOUNTS_LAYOUT,
        PROCESSED_FPKM_SDRF_LAYOUT,
    }:
        raise ValueError(f"Unsupported BioStudies layout: {layout!r}.")

    downloaded: dict[str, Path] = {}
    pinned_files: dict[str, dict[str, Any]] = {}
    for role, file_spec in (source_spec.get("files") or {}).items():
        url = str(file_spec.get("url") or "").strip()
        name = str(file_spec.get("name") or "").strip()
        expected_sha256 = str(
            file_spec.get("sha256") or ""
        ).strip().lower()
        if (
            not url
            or not name
            or len(expected_sha256) != 64
        ):
            raise ValueError(
                f"BioStudies file {role!r} is not fully pinned."
            )
        target = source_dir / name
        materialize_biostudies_download(url, target)
        observed_sha256 = sha256_file(target)
        if observed_sha256 != expected_sha256:
            raise ValueError(
                f"BioStudies file {role!r} failed SHA-256 validation."
            )
        expected_size = int(file_spec.get("size") or 0)
        if expected_size and target.stat().st_size != expected_size:
            raise ValueError(
                f"BioStudies file {role!r} changed size."
            )
        downloaded[role] = target
        pinned_files[role] = {
            "url": url,
            "name": name,
            "size": target.stat().st_size,
            "sha256": observed_sha256,
        }

    required_roles = {"idf", "sdrf", "license"}
    if layout == UVM_FEATURECOUNTS_LAYOUT:
        required_roles.update({"clinical", "gene_reference"})
    else:
        required_roles.add("expression")
    count_archive_roles = sorted(
        role for role in downloaded if role.startswith("counts_archive_")
    )
    missing_roles = sorted(required_roles - downloaded.keys())
    if missing_roles or (
        layout == UVM_FEATURECOUNTS_LAYOUT
        and not count_archive_roles
    ):
        raise ValueError(
            "BioStudies source is missing required pinned files: "
            f"{missing_roles or ['counts_archive_*']}."
        )

    idf_text = downloaded["idf"].read_text(
        encoding="utf-8", errors="strict"
    )
    if accession not in idf_text:
        raise ValueError(
            "BioStudies IDF does not contain the expected accession."
        )

    if layout == PROCESSED_FPKM_SDRF_LAYOUT:
        return materialize_processed_fpkm_sdrf_source(
            spec,
            source_dir,
            downloaded,
            pinned_files,
        )

    clinical_records = extract_uvm_clinical_records(
        downloaded["clinical"]
    )
    sdrf_records = parse_biostudies_sdrf(downloaded["sdrf"])
    clinical_tumors = {
        int(record["tumor_number"]) for record in clinical_records
    }
    expression_tumors = set(sdrf_records)
    if clinical_tumors != expression_tumors:
        raise ValueError(
            "Clinical and BioStudies expression tumor identifiers differ: "
            f"clinical_only={sorted(clinical_tumors - expression_tumors)}, "
            f"expression_only={sorted(expression_tumors - clinical_tumors)}."
        )

    patient_rows: list[dict[str, Any]] = []
    sample_rows: list[dict[str, Any]] = []
    matrix_samples: list[dict[str, Any]] = []
    for clinical in sorted(
        clinical_records, key=lambda row: int(row["tumor_number"])
    ):
        tumor_number = int(clinical["tumor_number"])
        expression = sdrf_records[tumor_number]
        patient_id = f"{accession}-P{tumor_number:03d}"
        sample_id = f"{accession}-T{tumor_number:03d}"
        status = str(clinical["latest_status"])
        event = 1 if status in {"DFD", "DFO"} else 0
        merged_metadata = {
            **clinical,
            **expression,
            "patient_id": patient_id,
            "sample_id": sample_id,
        }
        patient_rows.append(
            {
                "PATIENT_ID": patient_id,
                "OS_MONTHS": clinical["follow_up_months"],
                "OS_EVENT": event,
                "LATEST_STATUS": status,
                "TNM": clinical["tnm"],
                "METASTASIS": clinical["metastasis"],
                "LARGEST_TUMOR_DIAMETER_MM": clinical[
                    "largest_tumor_diameter_mm"
                ],
                "THICKNESS_MM": clinical["thickness_mm"],
                "SF3B1_MUTATION": clinical["sf3b1_mutation"],
                "HISTOTYPE": clinical["histotype"],
                "BIOSTUDIES_CLINICAL_METADATA_JSON": canonical_json(
                    merged_metadata
                ),
            }
        )
        sample_rows.append(
            {
                "SAMPLE_ID": sample_id,
                "PATIENT_ID": patient_id,
                "SAMPLE_TYPE": "Primary uveal melanoma",
                "SOURCE_NAME": expression["source_name"],
                "SOURCE_COUNT_FILE": expression["count_file"],
                "SOURCE_GENOTYPE": expression["genotype"],
                "BIOSTUDIES_SAMPLE_METADATA_JSON": canonical_json(
                    merged_metadata
                ),
            }
        )
        matrix_samples.append(
            {
                "sample_id": sample_id,
                "count_file": expression["count_file"],
                "tumor_number": tumor_number,
            }
        )

    patient_table = source_dir / "data_clinical_patient.txt"
    sample_table = source_dir / "data_clinical_sample.txt"
    write_tsv(
        patient_table,
        patient_rows,
        [
            "PATIENT_ID",
            "OS_MONTHS",
            "OS_EVENT",
            "LATEST_STATUS",
            "TNM",
            "METASTASIS",
            "LARGEST_TUMOR_DIAMETER_MM",
            "THICKNESS_MM",
            "SF3B1_MUTATION",
            "HISTOTYPE",
            "BIOSTUDIES_CLINICAL_METADATA_JSON",
        ],
    )
    write_tsv(
        sample_table,
        sample_rows,
        [
            "SAMPLE_ID",
            "PATIENT_ID",
            "SAMPLE_TYPE",
            "SOURCE_NAME",
            "SOURCE_COUNT_FILE",
            "SOURCE_GENOTYPE",
            "BIOSTUDIES_SAMPLE_METADATA_JSON",
        ],
    )

    gene_map = parse_gencode_gene_map(downloaded["gene_reference"])
    expression_table = source_dir / "data_expression_selected.tsv"
    expression_summary = materialize_featurecounts_archives(
        [downloaded[role] for role in count_archive_roles],
        expression_table,
        matrix_samples,
        gene_map,
    )

    source_snapshot_payload = {
        "accession": accession,
        "files": pinned_files,
    }
    source_snapshot = hashlib.sha256(
        canonical_json(source_snapshot_payload).encode("utf-8")
    ).hexdigest()
    source_manifest_path = (
        source_dir / "biostudies_source_manifest.json"
    )
    source_manifest_path.write_text(
        canonical_json(
            {
                "schema_version": (
                    "tcga-trace-biostudies-source-manifest-v1"
                ),
                **source_snapshot_payload,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    events = sum(int(row["OS_EVENT"]) for row in patient_rows)
    return (
        {
            "expression": expression_table,
            "patients": patient_table,
            "samples": sample_table,
            "clinical_source": downloaded["clinical"],
            "idf": downloaded["idf"],
            "sdrf": downloaded["sdrf"],
            "gene_reference": downloaded["gene_reference"],
            "license": downloaded["license"],
            "source_manifest": source_manifest_path,
            **{
                role: downloaded[role]
                for role in count_archive_roles
            },
        },
        source_snapshot,
        str(source_spec.get("publication_date") or "") or None,
        {
            "source_accession": accession,
            "source_pinned_files": pinned_files,
            "source_clinical_rows": len(patient_rows),
            "source_expression_rows": len(matrix_samples),
            "source_events": events,
            "source_censored": len(patient_rows) - events,
            "source_status_counts": status_counts(patient_rows),
            "source_gene_reference_entries": len(gene_map),
            **expression_summary,
        },
    )


def materialize_processed_fpkm_sdrf_source(
    spec: dict[str, Any],
    source_dir: Path,
    downloaded: dict[str, Path],
    pinned_files: dict[str, dict[str, Any]],
) -> tuple[dict[str, Path], str, str | None, dict[str, Any]]:
    source_spec = spec["source"]
    accession = str(source_spec["accession"]).strip()
    records = parse_uromol_sdrf(downloaded["sdrf"])

    expected_samples = int(
        source_spec.get("expected_source_samples") or 0
    )
    if expected_samples and len(records) != expected_samples:
        raise ValueError(
            "BioStudies SDRF sample count changed: "
            f"{len(records)} != {expected_samples}."
        )

    endpoint_complete = [
        record
        for record in records
        if float(record["progression_free_survival_months"]) > 0
    ]
    events = sum(
        int(record["progression_event"]) for record in endpoint_complete
    )
    censored = len(endpoint_complete) - events
    expected_endpoint_complete = int(
        source_spec.get("expected_endpoint_complete_samples") or 0
    )
    expected_events = int(source_spec.get("expected_events") or 0)
    expected_censored = int(source_spec.get("expected_censored") or 0)
    if (
        expected_endpoint_complete
        and len(endpoint_complete) != expected_endpoint_complete
    ):
        raise ValueError(
            "BioStudies endpoint-complete sample count changed: "
            f"{len(endpoint_complete)} != {expected_endpoint_complete}."
        )
    if expected_events and events != expected_events:
        raise ValueError(
            f"BioStudies event count changed: {events} != {expected_events}."
        )
    if expected_censored and censored != expected_censored:
        raise ValueError(
            "BioStudies censored count changed: "
            f"{censored} != {expected_censored}."
        )

    zero_time_source_names = sorted(
        str(record["source_name"])
        for record in records
        if float(record["progression_free_survival_months"]) == 0
    )
    expected_zero_time_source_names = sorted(
        str(value)
        for value in source_spec.get(
            "expected_zero_time_source_names"
        )
        or []
    )
    if (
        expected_zero_time_source_names
        and zero_time_source_names != expected_zero_time_source_names
    ):
        raise ValueError(
            "BioStudies zero-time endpoint records changed: "
            f"{zero_time_source_names} != "
            f"{expected_zero_time_source_names}."
        )

    patient_rows: list[dict[str, Any]] = []
    sample_rows: list[dict[str, Any]] = []
    expression_samples: list[dict[str, str]] = []
    for record in records:
        source_name = str(record["source_name"])
        patient_id = f"{accession}-{source_name}"
        sample_id = f"{patient_id}-RNA"
        progression_event = int(record["progression_event"])
        metadata = {
            **record,
            "patient_id": patient_id,
            "sample_id": sample_id,
        }
        patient_rows.append(
            {
                "PATIENT_ID": patient_id,
                "PFS_MONTHS": record[
                    "progression_free_survival_months"
                ],
                "PFS_EVENT": (
                    "1:PROGRESSION_TO_T2_PLUS"
                    if progression_event
                    else "0:CENSORED"
                ),
                "STAGE": record["stage"],
                "GRADE": record["grade"],
                "SEX": record["sex"],
                "AGE_AT_INDEX": record["age"],
                "CLINICAL_CENTER": record["clinical_center"],
                "TUMOR_SIZE": record["tumor_size"],
                "GROWTH_PATTERN": record["growth_pattern"],
                "BCG_TREATMENT": record["bcg_treatment"],
                "CIS_IN_DISEASE_COURSE": record[
                    "cis_in_disease_course"
                ],
                "CYSTECTOMY": record["cystectomy"],
                "BIOSTUDIES_CLINICAL_METADATA_JSON": canonical_json(
                    metadata
                ),
            }
        )
        sample_rows.append(
            {
                "SAMPLE_ID": sample_id,
                "PATIENT_ID": patient_id,
                "SAMPLE_TYPE": "Primary urothelial bladder tumor",
                "SOURCE_NAME": source_name,
                "BIOSTUDIES_SAMPLE_METADATA_JSON": canonical_json(
                    metadata
                ),
            }
        )
        expression_samples.append(
            {
                "source_name": source_name,
                "sample_id": sample_id,
            }
        )

    patient_table = source_dir / "data_clinical_patient.txt"
    sample_table = source_dir / "data_clinical_sample.txt"
    write_tsv(
        patient_table,
        patient_rows,
        [
            "PATIENT_ID",
            "PFS_MONTHS",
            "PFS_EVENT",
            "STAGE",
            "GRADE",
            "SEX",
            "AGE_AT_INDEX",
            "CLINICAL_CENTER",
            "TUMOR_SIZE",
            "GROWTH_PATTERN",
            "BCG_TREATMENT",
            "CIS_IN_DISEASE_COURSE",
            "CYSTECTOMY",
            "BIOSTUDIES_CLINICAL_METADATA_JSON",
        ],
    )
    write_tsv(
        sample_table,
        sample_rows,
        [
            "SAMPLE_ID",
            "PATIENT_ID",
            "SAMPLE_TYPE",
            "SOURCE_NAME",
            "BIOSTUDIES_SAMPLE_METADATA_JSON",
        ],
    )

    expression_table = source_dir / "data_expression_selected.tsv"
    expression_summary = materialize_processed_fpkm_matrix(
        downloaded["expression"],
        expression_table,
        expression_samples,
        expected_gene_rows=(
            int(source_spec.get("expected_source_gene_rows") or 0)
            or None
        ),
        expected_malformed_rows=source_spec.get(
            "expected_malformed_expression_rows"
        )
        or [],
    )

    source_snapshot_payload = {
        "accession": accession,
        "layout": PROCESSED_FPKM_SDRF_LAYOUT,
        "files": pinned_files,
    }
    source_snapshot = hashlib.sha256(
        canonical_json(source_snapshot_payload).encode("utf-8")
    ).hexdigest()
    source_manifest_path = (
        source_dir / "biostudies_source_manifest.json"
    )
    source_manifest_path.write_text(
        canonical_json(
            {
                "schema_version": (
                    "tcga-trace-biostudies-source-manifest-v1"
                ),
                **source_snapshot_payload,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    return (
        {
            "expression": expression_table,
            "expression_source": downloaded["expression"],
            "patients": patient_table,
            "samples": sample_table,
            "idf": downloaded["idf"],
            "sdrf": downloaded["sdrf"],
            "license": downloaded["license"],
            "source_manifest": source_manifest_path,
        },
        source_snapshot,
        str(source_spec.get("publication_date") or "") or None,
        {
            "source_accession": accession,
            "source_pinned_files": pinned_files,
            "source_clinical_rows": len(patient_rows),
            "source_expression_rows": len(expression_samples),
            "source_endpoint_complete_rows": len(endpoint_complete),
            "source_endpoint_excluded_nonpositive_time": (
                len(records) - len(endpoint_complete)
            ),
            "source_zero_time_source_names": zero_time_source_names,
            "source_events": events,
            "source_censored": censored,
            **expression_summary,
        },
    )


def parse_uromol_sdrf(path: Path) -> list[dict[str, Any]]:
    with path.open(
        newline="", encoding="utf-8-sig", errors="strict"
    ) as handle:
        reader = csv.reader(handle, delimiter="\t")
        header = next(reader)
        indexes = {
            "source_name": sdrf_column_index(header, "Source Name"),
            "disease": sdrf_column_index(
                header, "Characteristics[disease]"
            ),
            "grade": sdrf_column_index(
                header, "Characteristics[tumor grading]"
            ),
            "stage": sdrf_column_index(
                header, "Characteristics[disease staging]"
            ),
            "sex": sdrf_column_index(
                header, "Characteristics[sex]"
            ),
            "age": sdrf_column_index(
                header, "Characteristics[age]"
            ),
            "clinical_center": sdrf_column_index(
                header, "Characteristics[clinical center]"
            ),
            "tumor_size": sdrf_column_index(
                header, "Characteristics[tumor size]"
            ),
            "growth_pattern": sdrf_column_index(
                header, "Characteristics[growth pattern]"
            ),
            "bcg_treatment": sdrf_column_index(
                header, "Characteristics[BCG treatment]"
            ),
            "cis_in_disease_course": sdrf_column_index(
                header, "Characteristics[CIS in disease course]"
            ),
            "cystectomy": sdrf_column_index(
                header, "Characteristics[cystectomy]"
            ),
            "progression_event": sdrf_column_index(
                header, "Characteristics[progression to T2+]"
            ),
            "progression_time": sdrf_column_index(
                header,
                "Characteristics[progression free survival]",
            ),
            "progression_time_unit": sdrf_column_index(
                header, "Unit[time unit]", occurrence=2
            ),
        }
        records: list[dict[str, Any]] = []
        for line_number, row in enumerate(reader, start=2):
            if len(row) != len(header):
                raise ValueError(
                    "BioStudies SDRF row width changed at line "
                    f"{line_number}: {len(row)} != {len(header)}."
                )
            source_name = row[indexes["source_name"]].strip()
            if not source_name:
                raise ValueError(
                    f"BioStudies SDRF line {line_number} has no source name."
                )
            disease = row[indexes["disease"]].strip().lower()
            if disease != "bladder tumor":
                raise ValueError(
                    "UROMOL SDRF contains an unexpected disease at line "
                    f"{line_number}: {disease!r}."
                )
            raw_time = row[indexes["progression_time"]].strip()
            try:
                time_months = float(raw_time)
            except ValueError as error:
                raise ValueError(
                    "UROMOL SDRF contains a non-numeric progression time "
                    f"at line {line_number}: {raw_time!r}."
                ) from error
            if not math.isfinite(time_months) or time_months < 0:
                raise ValueError(
                    "UROMOL SDRF contains a negative or non-finite "
                    f"progression time at line {line_number}."
                )
            time_unit = row[
                indexes["progression_time_unit"]
            ].strip().lower()
            if time_unit != "month":
                raise ValueError(
                    "UROMOL progression time unit changed at line "
                    f"{line_number}: {time_unit!r}."
                )
            raw_event = row[indexes["progression_event"]].strip().lower()
            if raw_event not in {"yes", "no"}:
                raise ValueError(
                    "UROMOL SDRF contains an unsupported progression "
                    f"status at line {line_number}: {raw_event!r}."
                )
            event = int(raw_event == "yes")
            if event and time_months <= 0:
                raise ValueError(
                    "UROMOL SDRF contains a progression event with "
                    f"non-positive follow-up at line {line_number}."
                )
            records.append(
                {
                    "source_name": source_name,
                    "progression_free_survival_months": format(
                        time_months, ".12g"
                    ),
                    "progression_event": event,
                    "raw_progression_status": raw_event,
                    "stage": row[indexes["stage"]].strip(),
                    "grade": row[indexes["grade"]].strip(),
                    "sex": row[indexes["sex"]].strip(),
                    "age": row[indexes["age"]].strip(),
                    "clinical_center": row[
                        indexes["clinical_center"]
                    ].strip(),
                    "tumor_size": row[indexes["tumor_size"]].strip(),
                    "growth_pattern": row[
                        indexes["growth_pattern"]
                    ].strip(),
                    "bcg_treatment": row[
                        indexes["bcg_treatment"]
                    ].strip(),
                    "cis_in_disease_course": row[
                        indexes["cis_in_disease_course"]
                    ].strip(),
                    "cystectomy": row[indexes["cystectomy"]].strip(),
                }
            )

    source_names = [
        str(record["source_name"]) for record in records
    ]
    if len(records) < 10 or len(source_names) != len(set(source_names)):
        raise ValueError(
            "UROMOL SDRF did not yield at least 10 unique samples."
        )
    return records


def sdrf_column_index(
    header: list[str],
    name: str,
    *,
    occurrence: int = 1,
) -> int:
    matches = [
        index for index, value in enumerate(header) if value == name
    ]
    if occurrence < 1 or len(matches) < occurrence:
        raise ValueError(
            f"BioStudies SDRF lacks occurrence {occurrence} of {name!r}."
        )
    return matches[occurrence - 1]


def materialize_processed_fpkm_matrix(
    source: Path,
    target: Path,
    samples: list[dict[str, str]],
    *,
    expected_gene_rows: int | None = None,
    expected_malformed_rows: list[dict[str, Any]] | None = None,
    minimum_gene_rows: int = 10_000,
) -> dict[str, Any]:
    source_names = [str(sample["source_name"]) for sample in samples]
    output_sample_ids = [str(sample["sample_id"]) for sample in samples]
    if (
        len(samples) < 10
        or len(source_names) != len(set(source_names))
        or len(output_sample_ids) != len(set(output_sample_ids))
    ):
        raise ValueError(
            "Processed FPKM materialization requires at least 10 unique "
            "source and output sample identifiers."
        )

    source_rows = 0
    complete_rows = 0
    malformed_rows: list[dict[str, Any]] = []
    seen_feature_ids: set[str] = set()
    target.parent.mkdir(parents=True, exist_ok=True)
    with source.open(
        newline="", encoding="utf-8", errors="strict"
    ) as source_handle, target.open(
        "w", newline="", encoding="utf-8"
    ) as target_handle:
        reader = csv.reader(source_handle, delimiter="\t")
        writer = csv.writer(
            target_handle, delimiter="\t", lineterminator="\n"
        )
        header = next(reader)
        expected_metadata_columns = [
            "tracking_id",
            "gene.type",
            "gene.status",
            "gene.name",
        ]
        if header[:4] != expected_metadata_columns:
            raise ValueError(
                "Processed FPKM matrix metadata columns changed: "
                f"{header[:4]} != {expected_metadata_columns}."
            )
        if header[4:] != source_names:
            raise ValueError(
                "Processed FPKM matrix sample columns do not match the "
                "SDRF in exact source order."
            )
        writer.writerow(
            [
                "Ensembl_Gene_Id|Hugo_Symbol",
                *output_sample_ids,
            ]
        )

        expected_width = len(header)
        for line_number, row in enumerate(reader, start=2):
            source_rows += 1
            if len(row) != expected_width:
                malformed_rows.append(
                    {
                        "source_line": line_number,
                        "feature_id": row[0].strip() if row else "",
                        "gene_symbol": (
                            row[3].strip() if len(row) > 3 else ""
                        ),
                        "observed_columns": len(row),
                        "expected_columns": expected_width,
                    }
                )
                continue
            source_feature_id = row[0].strip()
            gene_symbol = row[3].strip().upper()
            if (
                not source_feature_id.startswith("ENSG")
                or not gene_symbol
            ):
                raise ValueError(
                    "Processed FPKM matrix contains an invalid feature at "
                    f"line {line_number}."
                )
            feature_id = source_feature_id.split(".", 1)[0]
            if feature_id in seen_feature_ids:
                raise ValueError(
                    "Processed FPKM matrix contains duplicate versionless "
                    f"Ensembl ID {feature_id!r}."
                )
            seen_feature_ids.add(feature_id)
            try:
                values = [float(value) for value in row[4:]]
            except ValueError as error:
                raise ValueError(
                    "Processed FPKM matrix contains a non-numeric value at "
                    f"line {line_number}."
                ) from error
            if any(
                not math.isfinite(value) or value < 0
                for value in values
            ):
                raise ValueError(
                    "Processed FPKM matrix contains a negative or "
                    f"non-finite value at line {line_number}."
                )
            writer.writerow(
                [
                    f"{feature_id}|{gene_symbol}",
                    *row[4:],
                ]
            )
            complete_rows += 1

    if expected_gene_rows and source_rows != expected_gene_rows:
        raise ValueError(
            "Processed FPKM source row count changed: "
            f"{source_rows} != {expected_gene_rows}."
        )
    expected_malformed = expected_malformed_rows or []
    if malformed_rows != expected_malformed:
        raise ValueError(
            "Processed FPKM malformed-row ledger changed: "
            f"{malformed_rows} != {expected_malformed}."
        )
    if complete_rows < minimum_gene_rows:
        raise ValueError(
            "Processed FPKM matrix has fewer than the required number "
            f"of complete genes ({minimum_gene_rows})."
        )
    return {
        "source_fpkm_samples": len(samples),
        "source_fpkm_gene_rows": source_rows,
        "source_fpkm_complete_gene_rows": complete_rows,
        "source_fpkm_malformed_rows": malformed_rows,
        "source_expression_unit": "FPKM",
    }


def extract_uvm_clinical_records(path: Path) -> list[dict[str, str]]:
    try:
        from pypdf import PdfReader
    except ImportError as error:  # pragma: no cover - dependency guard
        raise RuntimeError(
            "pypdf is required to extract BioStudies clinical tables."
        ) from error
    reader = PdfReader(path)
    text = "\n".join(
        page.extract_text() or "" for page in reader.pages
    )
    return parse_uvm_clinical_text(text)


def parse_uvm_clinical_text(text: str) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    for line in text.splitlines():
        match = UVM_CLINICAL_ROW.fullmatch(line.strip())
        if match is None:
            continue
        (
            tumor_number,
            largest_diameter,
            thickness,
            tnm,
            metastasis,
            mutation,
            histotype,
            follow_up,
            status,
        ) = match.groups()
        records.append(
            {
                "tumor_number": tumor_number,
                "largest_tumor_diameter_mm": largest_diameter,
                "thickness_mm": thickness,
                "tnm": tnm,
                "metastasis": metastasis,
                "sf3b1_mutation": mutation or "",
                "histotype": histotype,
                "follow_up_months": follow_up,
                "latest_status": status,
            }
        )
    tumor_numbers = [
        int(record["tumor_number"]) for record in records
    ]
    if len(records) < 10 or len(tumor_numbers) != len(set(tumor_numbers)):
        raise ValueError(
            "Clinical PDF did not yield unique patient-level records."
        )
    invalid_statuses = {
        record["latest_status"]
        for record in records
        if record["latest_status"] not in {"NED", "AWD", "DFD", "DFO"}
    }
    if invalid_statuses:
        raise ValueError(
            f"Unsupported UVM clinical statuses: {sorted(invalid_statuses)}."
        )
    return records


def parse_biostudies_sdrf(path: Path) -> dict[int, dict[str, str]]:
    with path.open(
        newline="", encoding="utf-8-sig", errors="strict"
    ) as handle:
        reader = csv.reader(handle, delimiter="\t")
        header = next(reader)
        derived_indexes = [
            index
            for index, value in enumerate(header)
            if value == "Derived Array Data File"
        ]
        genotype_indexes = [
            index
            for index, value in enumerate(header)
            if value in {
                "Characteristics[genotype]",
                "Factor Value[genotype]",
            }
        ]
        if not derived_indexes or not genotype_indexes:
            raise ValueError(
                "BioStudies SDRF lacks count-file or genotype columns."
            )
        records: dict[int, dict[str, str]] = {}
        for row in reader:
            count_files = [
                row[index].strip()
                for index in derived_indexes
                if index < len(row)
                and row[index].strip().endswith(".counts")
            ]
            if len(count_files) != 1:
                raise ValueError(
                    "Each BioStudies SDRF row must resolve to one count file."
                )
            count_file = count_files[0]
            match = UVM_COUNT_FILENAME.fullmatch(count_file)
            if match is None:
                raise ValueError(
                    f"Unexpected BioStudies count filename: {count_file!r}."
                )
            tumor_number = int(match.group(1))
            if tumor_number in records:
                raise ValueError(
                    f"Duplicate BioStudies tumor number {tumor_number}."
                )
            records[tumor_number] = {
                "source_name": row[0].strip(),
                "count_file": count_file,
                "genotype": next(
                    (
                        row[index].strip()
                        for index in genotype_indexes
                        if index < len(row) and row[index].strip()
                    ),
                    "",
                ),
            }
    if len(records) < 10:
        raise ValueError("BioStudies SDRF has fewer than 10 RNA samples.")
    return records


def materialize_featurecounts_archives(
    archives: list[Path],
    target: Path,
    samples: list[dict[str, Any]],
    gene_map: dict[str, str],
    *,
    minimum_gene_rows: int = 10_000,
) -> dict[str, Any]:
    if len(samples) < 10 or not archives:
        raise ValueError(
            "FeatureCounts materialization requires samples and archives."
        )
    zip_handles = [zipfile.ZipFile(path) for path in archives]
    try:
        member_locations: dict[str, zipfile.ZipFile] = {}
        duplicate_members: set[str] = set()
        for archive in zip_handles:
            for member in archive.namelist():
                if not member.endswith(".counts"):
                    continue
                name = Path(member).name
                if name in member_locations:
                    duplicate_members.add(name)
                member_locations[name] = archive
        if duplicate_members:
            raise ValueError(
                "Count archives contain duplicate members: "
                f"{sorted(duplicate_members)[:5]}."
            )

        expected_files = [
            str(sample["count_file"]) for sample in samples
        ]
        if len(expected_files) != len(set(expected_files)):
            raise ValueError("Requested count filenames are not unique.")
        missing = [
            name for name in expected_files if name not in member_locations
        ]
        extra = sorted(set(member_locations) - set(expected_files))
        if missing or extra:
            raise ValueError(
                "Pinned count archives do not match the SDRF: "
                f"missing={missing[:5]}, extra={extra[:5]}."
            )

        gene_ids: list[str] = []
        counts_by_sample: list[array] = []
        library_sizes: list[int] = []
        for sample_index, filename in enumerate(expected_files):
            archive = member_locations[filename]
            with archive.open(filename) as handle:
                comment = handle.readline().decode("utf-8", errors="strict")
                header = handle.readline().decode(
                    "utf-8", errors="strict"
                ).rstrip("\r\n").split("\t")
                if (
                    not comment.startswith("# Program:featureCounts")
                    or not header
                    or header[0] != "Geneid"
                ):
                    raise ValueError(
                        f"{filename!r} is not a supported featureCounts file."
                    )
                counts = array("Q")
                for row_index, raw_line in enumerate(handle):
                    row = raw_line.decode(
                        "utf-8", errors="strict"
                    ).rstrip("\r\n").split("\t")
                    if len(row) != len(header):
                        raise ValueError(
                            f"{filename!r} has inconsistent row widths."
                        )
                    gene_id = row[0].strip().split(".", 1)[0]
                    try:
                        count = int(row[-1])
                    except ValueError as error:
                        raise ValueError(
                            f"{filename!r} contains a non-integer count."
                        ) from error
                    if count < 0:
                        raise ValueError(
                            f"{filename!r} contains a negative count."
                        )
                    if sample_index == 0:
                        gene_ids.append(gene_id)
                    elif (
                        row_index >= len(gene_ids)
                        or gene_ids[row_index] != gene_id
                    ):
                        raise ValueError(
                            "FeatureCounts genes differ between samples."
                        )
                    counts.append(count)
            if len(counts) != len(gene_ids):
                raise ValueError(
                    "FeatureCounts samples have different gene counts."
                )
            library_size = sum(counts)
            if library_size <= 0:
                raise ValueError(
                    f"{filename!r} has an empty count library."
                )
            counts_by_sample.append(counts)
            library_sizes.append(library_size)

        mapped_rows = sum(gene_id in gene_map for gene_id in gene_ids)
        if mapped_rows < minimum_gene_rows:
            raise ValueError(
                "Fewer than 10,000 featureCounts rows map to the pinned "
                "gene reference."
            )
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open(
            "w", newline="", encoding="utf-8"
        ) as output_handle:
            writer = csv.writer(
                output_handle, delimiter="\t", lineterminator="\n"
            )
            writer.writerow(
                [
                    "Ensembl_Gene_Id|Hugo_Symbol",
                    *[str(sample["sample_id"]) for sample in samples],
                ]
            )
            for row_index, gene_id in enumerate(gene_ids):
                symbol = gene_map.get(gene_id)
                if not symbol:
                    continue
                writer.writerow(
                    [
                        f"{gene_id}|{symbol}",
                        *[
                            format(
                                math.log2(
                                    (
                                        counts[row_index]
                                        / library_size
                                        * 1_000_000.0
                                    )
                                    + 1.0
                                ),
                                ".10g",
                            )
                            for counts, library_size in zip(
                                counts_by_sample,
                                library_sizes,
                                strict=True,
                            )
                        ],
                    ]
                )
    finally:
        for archive in zip_handles:
            archive.close()

    return {
        "source_count_archives": len(archives),
        "source_count_samples": len(samples),
        "source_count_gene_rows": len(gene_ids),
        "mapped_expression_gene_rows": mapped_rows,
        "unmapped_expression_gene_rows": len(gene_ids) - mapped_rows,
        "expression_normalization": "log2(CPM + 1)",
        "library_size_min": min(library_sizes),
        "library_size_max": max(library_sizes),
    }


def status_counts(
    patient_rows: list[dict[str, Any]],
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in patient_rows:
        status = str(row["LATEST_STATUS"])
        counts[status] = counts.get(status, 0) + 1
    return dict(sorted(counts.items()))
