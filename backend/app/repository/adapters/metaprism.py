from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import math
from pathlib import Path
from typing import Any, Iterable
import urllib.parse

from app.repository.adapters.cbioportal import (
    download,
    download_with_http_ranges,
    read_expression_header,
    request_json,
)
from app.repository.adapters.geo import parse_ensembl_gene_map
from app.repository.storage import sha256_file


METAPRISM_ADAPTER_VERSION = "metaprism_public_v1"
DEFAULT_PAGE_SIZE = 250
DEFAULT_RANGE_CHUNK_SIZE = 8 * 1024 * 1024


def materialize_metaprism_source(
    spec: dict[str, Any],
    source_dir: Path,
) -> tuple[dict[str, Path], str, str | None, dict[str, Any]]:
    source_spec = spec["source"]
    api_base_url = str(
        source_spec.get("api_base_url")
        or "https://cbioportal.gustaveroussy.fr/api"
    ).rstrip("/")
    study_id = str(source_spec.get("study_id") or "").strip()
    cohort_values = {
        str(value).strip()
        for value in source_spec.get("cohort_values") or []
        if str(value).strip()
    }
    if not study_id or not cohort_values:
        raise ValueError(
            "META-PRISM sources require study_id and cohort_values."
        )

    expression_path = materialize_pinned_download(
        source_spec["expression"],
        source_dir,
        default_name="Data_Table_2.rna_gene_tpm.tsv.gz",
        use_ranges=True,
    )
    reference_path = materialize_pinned_download(
        source_spec["gene_reference"],
        source_dir,
        default_name="gencode.v27.annotation.gtf.gz",
    )
    readme_path = materialize_pinned_download(
        source_spec["readme"],
        source_dir,
        default_name="META_PRISM_DATA_README.md",
    )

    quoted_study = urllib.parse.quote(study_id, safe="")
    study = request_json(
        f"{api_base_url}/studies/{quoted_study}?projection=DETAILED"
    )
    if not study.get("publicStudy"):
        raise ValueError("The META-PRISM cBioPortal study is not public.")

    cohort_rows = fetch_clinical_attribute(
        api_base_url,
        study_id,
        clinical_data_type="SAMPLE",
        attribute_id="CANCER_COHORT",
    )
    rna_id_rows = fetch_clinical_attribute(
        api_base_url,
        study_id,
        clinical_data_type="SAMPLE",
        attribute_id="RNASEQ_SAMPLE_ID",
    )
    expression_sample_ids = set(
        read_expression_header(expression_path)[1:]
    )
    selected = select_metaprism_samples(
        cohort_rows,
        rna_id_rows,
        cohort_values=cohort_values,
        expression_sample_ids=expression_sample_ids,
    )

    patient_rows: dict[str, dict[str, Any]] = {}
    sample_rows: list[dict[str, Any]] = []
    sample_clinical_payload: list[dict[str, Any]] = []
    patient_clinical_payload: list[dict[str, Any]] = []
    for record in selected:
        source_sample_id = record["source_sample_id"]
        patient_id = record["patient_id"]
        expression_sample_id = record["expression_sample_id"]
        quoted_sample = urllib.parse.quote(source_sample_id, safe="")
        quoted_patient = urllib.parse.quote(patient_id, safe="")
        sample_clinical = request_json(
            f"{api_base_url}/studies/{quoted_study}/samples/"
            f"{quoted_sample}/clinical-data?projection=SUMMARY"
        )
        patient_clinical = request_json(
            f"{api_base_url}/studies/{quoted_study}/patients/"
            f"{quoted_patient}/clinical-data?projection=SUMMARY"
        )
        sample_clinical_payload.extend(sample_clinical)
        patient_clinical_payload.extend(patient_clinical)

        sample_row = {
            "SAMPLE_ID": expression_sample_id,
            "PATIENT_ID": patient_id,
            "CBIOPORTAL_SAMPLE_ID": source_sample_id,
        }
        for row in sample_clinical:
            attribute_id = str(
                row.get("clinicalAttributeId") or ""
            ).strip()
            if attribute_id:
                sample_row[attribute_id] = row.get("value")
        if sample_row.get("RNASEQ_SAMPLE_ID") != expression_sample_id:
            raise ValueError(
                "META-PRISM RNA sample identifier changed during "
                "clinical-data materialization."
            )
        sample_rows.append(sample_row)

        patient_row = patient_rows.setdefault(
            patient_id, {"PATIENT_ID": patient_id}
        )
        for row in patient_clinical:
            attribute_id = str(
                row.get("clinicalAttributeId") or ""
            ).strip()
            if attribute_id:
                patient_row[attribute_id] = row.get("value")

    patient_table = source_dir / "data_clinical_patient.txt"
    sample_table = source_dir / "data_clinical_sample.txt"
    write_rows(patient_table, patient_rows.values(), "PATIENT_ID")
    write_rows(sample_table, sample_rows, "SAMPLE_ID", "PATIENT_ID")

    mapped_expression_path = (
        source_dir / "data_expression_selected_mapped.tsv.gz"
    )
    expression_metadata = materialize_metaprism_expression(
        expression_path,
        mapped_expression_path,
        reference_path,
        selected_sample_ids=[
            record["expression_sample_id"] for record in selected
        ],
    )

    json_payloads = {
        "study_metadata": ("study.json", study),
        "cohort_clinical_api": (
            "cancer_cohort_clinical_api.json",
            cohort_rows,
        ),
        "rna_id_clinical_api": (
            "rnaseq_sample_id_clinical_api.json",
            rna_id_rows,
        ),
        "selected_sample_clinical_api": (
            "selected_sample_clinical_api.json",
            sample_clinical_payload,
        ),
        "selected_patient_clinical_api": (
            "selected_patient_clinical_api.json",
            patient_clinical_payload,
        ),
        "expression_materialization": (
            "expression_materialization.json",
            expression_metadata,
        ),
    }
    source_paths: dict[str, Path] = {
        "expression": mapped_expression_path,
        "expression_original": expression_path,
        "gene_reference": reference_path,
        "license": readme_path,
        "patients": patient_table,
        "samples": sample_table,
        "readme": readme_path,
    }
    for role, (name, payload) in json_payloads.items():
        path = source_dir / name
        path.write_text(
            json.dumps(
                payload,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n",
            encoding="utf-8",
        )
        source_paths[role] = path

    source_hashes = {
        role: sha256_file(path)
        for role, path in sorted(source_paths.items())
    }
    source_snapshot = hashlib.sha256(
        json.dumps(
            source_hashes,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    expected_snapshot = str(
        source_spec.get("source_snapshot_sha256") or ""
    ).strip()
    if expected_snapshot and source_snapshot != expected_snapshot:
        raise ValueError(
            "META-PRISM source snapshot does not match the pinned SHA256."
        )
    import_date = str(study.get("importDate") or "").strip()
    source_snapshot_date = (
        import_date.replace(" ", "T") + "Z"
        if import_date
        else None
    )
    events = sum(
        str(row.get("OS_STATUS") or "").startswith("1:")
        for row in patient_rows.values()
    )
    return (
        source_paths,
        source_snapshot,
        source_snapshot_date,
        {
            "source_api": api_base_url,
            "source_study_id": study_id,
            "source_cohort_values": sorted(cohort_values),
            "source_expression_samples": len(expression_sample_ids),
            "selected_expression_samples": len(selected),
            "selected_patients": len(patient_rows),
            "selected_os_events": events,
            "selected_os_censored": len(patient_rows) - events,
            **expression_metadata,
        },
    )


def materialize_pinned_download(
    file_spec: dict[str, Any],
    source_dir: Path,
    *,
    default_name: str,
    use_ranges: bool = False,
) -> Path:
    url = str(file_spec.get("url") or "").strip()
    name = str(file_spec.get("name") or default_name).strip()
    expected_size = int(file_spec.get("size") or 0)
    expected_sha256 = str(file_spec.get("sha256") or "").strip().lower()
    if (
        not url
        or not name
        or Path(name).name != name
        or expected_size <= 0
        or len(expected_sha256) != 64
    ):
        raise ValueError(
            "META-PRISM source files require a safe name, positive size "
            "and SHA256."
        )
    target = source_dir / name
    if use_ranges:
        download_with_http_ranges(
            url,
            target,
            total_size=expected_size,
            chunk_size=int(
                file_spec.get("range_chunk_size")
                or DEFAULT_RANGE_CHUNK_SIZE
            ),
        )
    else:
        download(url, target)
    if target.stat().st_size != expected_size:
        raise ValueError(
            f"META-PRISM source size mismatch for {name!r}."
        )
    if sha256_file(target) != expected_sha256:
        raise ValueError(
            f"META-PRISM source SHA256 mismatch for {name!r}."
        )
    return target


def fetch_clinical_attribute(
    api_base_url: str,
    study_id: str,
    *,
    clinical_data_type: str,
    attribute_id: str,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> list[dict[str, Any]]:
    if page_size <= 0:
        raise ValueError("META-PRISM clinical page size must be positive.")
    quoted_study = urllib.parse.quote(study_id, safe="")
    query_base = {
        "clinicalDataType": clinical_data_type,
        "attributeId": attribute_id,
        "projection": "SUMMARY",
        "pageSize": str(page_size),
    }
    rows: list[dict[str, Any]] = []
    page_number = 0
    while True:
        query = urllib.parse.urlencode(
            {**query_base, "pageNumber": str(page_number)}
        )
        page = request_json(
            f"{api_base_url.rstrip('/')}/studies/{quoted_study}/"
            f"clinical-data?{query}"
        )
        if not isinstance(page, list):
            raise ValueError(
                "META-PRISM clinical API returned a non-list page."
            )
        rows.extend(page)
        if len(page) < page_size:
            break
        page_number += 1
    return sorted(
        rows,
        key=lambda row: (
            str(row.get("sampleId") or ""),
            str(row.get("patientId") or ""),
            str(row.get("clinicalAttributeId") or ""),
        ),
    )


def select_metaprism_samples(
    cohort_rows: Iterable[dict[str, Any]],
    rna_id_rows: Iterable[dict[str, Any]],
    *,
    cohort_values: set[str],
    expression_sample_ids: set[str],
    minimum_patients: int = 10,
) -> list[dict[str, str]]:
    rna_by_source_sample: dict[str, str] = {}
    for row in rna_id_rows:
        source_sample_id = str(row.get("sampleId") or "").strip()
        expression_sample_id = str(row.get("value") or "").strip()
        if not source_sample_id or not expression_sample_id:
            continue
        previous = rna_by_source_sample.setdefault(
            source_sample_id, expression_sample_id
        )
        if previous != expression_sample_id:
            raise ValueError(
                "META-PRISM source sample maps to multiple RNA samples."
            )

    selected: list[dict[str, str]] = []
    seen_patients: set[str] = set()
    seen_expression_samples: set[str] = set()
    for row in cohort_rows:
        if str(row.get("value") or "").strip() not in cohort_values:
            continue
        source_sample_id = str(row.get("sampleId") or "").strip()
        patient_id = str(row.get("patientId") or "").strip()
        expression_sample_id = rna_by_source_sample.get(
            source_sample_id, ""
        )
        if (
            not source_sample_id
            or not patient_id
            or not expression_sample_id
            or expression_sample_id not in expression_sample_ids
        ):
            continue
        if patient_id in seen_patients:
            raise ValueError(
                "META-PRISM target cohort contains multiple RNA samples "
                "for one patient."
            )
        if expression_sample_id in seen_expression_samples:
            raise ValueError(
                "META-PRISM RNA sample maps to multiple patients."
            )
        seen_patients.add(patient_id)
        seen_expression_samples.add(expression_sample_id)
        selected.append(
            {
                "source_sample_id": source_sample_id,
                "expression_sample_id": expression_sample_id,
                "patient_id": patient_id,
            }
        )
    selected.sort(
        key=lambda row: (
            row["patient_id"],
            row["expression_sample_id"],
        )
    )
    if len(selected) < minimum_patients:
        raise ValueError(
            "Fewer than the required META-PRISM patients have public "
            "expression and deterministic clinical linkage."
        )
    return selected


def materialize_metaprism_expression(
    source: Path,
    target: Path,
    gene_reference: Path,
    *,
    selected_sample_ids: list[str],
    minimum_mapped_genes: int = 10_000,
) -> dict[str, Any]:
    if (
        len(selected_sample_ids) != len(set(selected_sample_ids))
        or len(selected_sample_ids) < 1
    ):
        raise ValueError(
            "META-PRISM selected RNA sample IDs must be unique."
        )
    gene_map = parse_ensembl_gene_map(gene_reference)
    mapped_rows = 0
    unmapped_rows = 0
    seen_gene_ids: set[str] = set()
    with gzip.open(source, mode="rt", newline="", encoding="utf-8") as src:
        reader = csv.reader(src, delimiter="\t")
        header = next(reader)
        if len(header) < 2 or header[0] != "ensembl_gene_id":
            raise ValueError(
                "META-PRISM expression header is not the expected "
                "Ensembl-by-sample matrix."
            )
        sample_index = {
            sample_id: index
            for index, sample_id in enumerate(header[1:], start=1)
        }
        missing_samples = [
            sample_id
            for sample_id in selected_sample_ids
            if sample_id not in sample_index
        ]
        if missing_samples:
            raise ValueError(
                "META-PRISM selected RNA samples are absent from TPM: "
                f"{missing_samples[:5]}"
            )
        selected_indexes = [
            sample_index[sample_id]
            for sample_id in selected_sample_ids
        ]
        with target.open("wb") as raw_handle:
            with gzip.GzipFile(
                filename="",
                mode="wb",
                fileobj=raw_handle,
                mtime=0,
            ) as gzip_handle:
                with io.TextIOWrapper(
                    gzip_handle,
                    encoding="utf-8",
                    newline="",
                ) as output_handle:
                    writer = csv.writer(
                        output_handle,
                        delimiter="\t",
                        lineterminator="\n",
                    )
                    writer.writerow(
                        [
                            "Ensembl_Gene_Id|Hugo_Symbol",
                            *selected_sample_ids,
                        ]
                    )
                    for row in reader:
                        if not row:
                            continue
                        if len(row) != len(header):
                            raise ValueError(
                                "META-PRISM expression row width changed."
                            )
                        gene_id = row[0].strip()
                        if gene_id in seen_gene_ids:
                            raise ValueError(
                                "META-PRISM expression has duplicate "
                                f"Ensembl ID {gene_id!r}."
                            )
                        seen_gene_ids.add(gene_id)
                        symbol = (
                            gene_map.get(gene_id)
                            or gene_map.get(gene_id.split(".", 1)[0])
                        )
                        if not symbol:
                            unmapped_rows += 1
                            continue
                        values = [row[index] for index in selected_indexes]
                        try:
                            parsed_values = [float(value) for value in values]
                        except ValueError as error:
                            raise ValueError(
                                "META-PRISM TPM contains a non-numeric "
                                "selected value."
                            ) from error
                        if any(
                            not math.isfinite(value) or value < 0
                            for value in parsed_values
                        ):
                            raise ValueError(
                                "META-PRISM TPM contains invalid selected "
                                "values."
                            )
                        writer.writerow(
                            [f"{gene_id}|{symbol}", *values]
                        )
                        mapped_rows += 1
    if mapped_rows < minimum_mapped_genes:
        raise ValueError(
            "Fewer than the required META-PRISM genes map to GENCODE "
            "symbols."
        )
    return {
        "source_expression_gene_rows": (
            mapped_rows + unmapped_rows
        ),
        "mapped_expression_gene_rows": mapped_rows,
        "unmapped_expression_gene_rows": unmapped_rows,
        "selected_expression_sample_ids": selected_sample_ids,
    }


def write_rows(
    path: Path,
    rows: Iterable[dict[str, Any]],
    *leading_fields: str,
) -> None:
    materialized = list(rows)
    fields = [
        *leading_fields,
        *sorted(
            {
                key
                for row in materialized
                for key in row
                if key not in leading_fields
            }
        ),
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fields,
            delimiter="\t",
            lineterminator="\n",
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(materialized)
