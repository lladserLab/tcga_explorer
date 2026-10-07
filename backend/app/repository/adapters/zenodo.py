from __future__ import annotations

import csv
import hashlib
import io
import json
import math
from pathlib import Path
import re
import shutil
from typing import Any
import zipfile

from app.repository.adapters.cbioportal import (
    download,
    request_json,
    write_tsv,
)
from app.repository.adapters.pmc import (
    canonical_json,
    read_xlsx_sheet,
)
from app.repository.storage import sha256_file


ZENODO_ADAPTER_VERSION = "zenodo_publication_v3"
DEFAULT_ZENODO_API = "https://zenodo.org/api/records"


def materialize_zenodo_publication_source(
    spec: dict[str, Any],
    source_dir: Path,
) -> tuple[dict[str, Path], str, str | None, dict[str, Any]]:
    source_spec = spec["source"]
    record_id = int(source_spec.get("record_id") or 0)
    api_base = str(
        source_spec.get("api_base") or DEFAULT_ZENODO_API
    ).rstrip("/")
    if record_id <= 0:
        raise ValueError("Zenodo sources require a positive record_id.")

    record_url = f"{api_base}/{record_id}"
    record = request_json(record_url)
    validate_zenodo_record(record, source_spec, record_id=record_id)

    remote_files = {
        str(item.get("key") or ""): item
        for item in record.get("files") or []
        if item.get("key")
    }
    if source_spec.get("expression_matrix"):
        return materialize_direct_zenodo_matrix_source(
            spec,
            source_dir,
            record=record,
            record_url=record_url,
            api_base=api_base,
            remote_files=remote_files,
        )

    archive_spec = source_spec.get("expression_archive") or {}
    archive_key = str(archive_spec.get("key") or "").strip()
    archive_member = str(archive_spec.get("member") or "").strip()
    if (
        not archive_key
        or not archive_member
        or Path(archive_member).is_absolute()
        or ".." in Path(archive_member).parts
    ):
        raise ValueError(
            "Zenodo expression_archive requires a safe key and member."
        )
    remote_archive = remote_files.get(archive_key)
    if remote_archive is None:
        raise ValueError(
            f"Zenodo record is missing pinned file {archive_key!r}."
        )
    archive_path = source_dir / Path(archive_key).name
    expected_md5 = validate_zenodo_file_pin(
        remote_archive, archive_spec
    )
    download(
        str((remote_archive.get("links") or {}).get("self") or ""),
        archive_path,
    )
    if md5_file(archive_path) != expected_md5:
        raise ValueError("Downloaded Zenodo archive failed MD5 validation.")
    expected_archive_sha256 = str(
        archive_spec.get("sha256") or ""
    ).strip().lower()
    if (
        expected_archive_sha256
        and sha256_file(archive_path) != expected_archive_sha256
    ):
        raise ValueError(
            "Downloaded Zenodo archive failed SHA-256 validation."
        )

    clinical_spec = source_spec.get("clinical") or {}
    clinical_url = str(clinical_spec.get("url") or "").strip()
    clinical_name = str(clinical_spec.get("name") or "").strip()
    if (
        not clinical_url
        or not clinical_name
        or Path(clinical_name).name != clinical_name
    ):
        raise ValueError(
            "Zenodo publication sources require a safe clinical filename "
            "and URL."
        )
    clinical_path = source_dir / clinical_name
    download(clinical_url, clinical_path)
    verify_size_and_sha256(
        clinical_path,
        expected_size=clinical_spec.get("size"),
        expected_sha256=clinical_spec.get("sha256"),
        label="Clinical supplement",
    )

    license_url = str(
        source_spec.get("license_evidence_url") or ""
    ).strip()
    if not license_url:
        raise ValueError(
            "Zenodo publication sources require license_evidence_url."
        )
    license_path = source_dir / "SOURCE_LICENSE_EVIDENCE.json"
    download(license_url, license_path)
    license_evidence = json.loads(
        license_path.read_text(encoding="utf-8")
    )
    validate_crossref_license(
        license_evidence,
        expected_doi=str(source_spec.get("publication_doi") or ""),
        expected_license_url=str(
            source_spec.get("expected_clinical_license_url") or ""
        ),
    )

    clinical_rows = read_xlsx_sheet(
        clinical_path,
        sheet_name=str(
            clinical_spec.get("patient_sheet") or ""
        ).strip(),
        header_row=int(clinical_spec.get("patient_header_row") or 1),
    )
    sample_map_rows = read_xlsx_sheet(
        clinical_path,
        sheet_name=str(
            clinical_spec.get("sample_sheet") or ""
        ).strip(),
        header_row=int(clinical_spec.get("sample_header_row") or 1),
    )
    patient_id_column = str(
        clinical_spec.get("patient_id_column") or ""
    ).strip()
    sample_patient_column = str(
        clinical_spec.get("sample_patient_column") or patient_id_column
    ).strip()
    sample_region_column = str(
        clinical_spec.get("sample_region_column") or ""
    ).strip()
    sample_type_column = str(
        clinical_spec.get("sample_type_column") or ""
    ).strip()
    allowed_sample_types = {
        str(value).strip().casefold()
        for value in clinical_spec.get("allowed_sample_types") or []
        if str(value).strip()
    }
    if not all(
        (
            patient_id_column,
            sample_patient_column,
            sample_region_column,
        )
    ):
        raise ValueError(
            "Zenodo clinical and sample-map identifier columns are "
            "required."
        )

    clinical_by_patient = unique_rows_by_field(
        clinical_rows, patient_id_column, label="clinical patient"
    )
    mapped_samples: dict[str, dict[str, str]] = {}
    for row in sample_map_rows:
        patient_id = str(row.get(sample_patient_column) or "").strip()
        region = str(row.get(sample_region_column) or "").strip()
        sample_type = str(row.get(sample_type_column) or "").strip()
        if (
            not patient_id
            or not region
            or (
                allowed_sample_types
                and sample_type.casefold() not in allowed_sample_types
            )
        ):
            continue
        sample_id = f"{patient_id}_{region}"
        if sample_id in mapped_samples:
            raise ValueError(
                f"Sample map contains duplicate sample {sample_id!r}."
            )
        if patient_id not in clinical_by_patient:
            raise ValueError(
                f"Sample {sample_id!r} has no clinical patient row."
            )
        mapped_samples[sample_id] = {
            **row,
            "_PATIENT_ID": patient_id,
            "_SAMPLE_ID": sample_id,
        }

    expression_spec = source_spec.get("expression") or {}
    materialized = materialize_patient_level_counts(
        archive_path,
        archive_member=archive_member,
        target=source_dir / "data_expression_selected.tsv",
        mapped_samples=mapped_samples,
        delimiter=str(expression_spec.get("delimiter") or "\t"),
        feature_column=str(
            expression_spec.get("feature_column") or ""
        ).strip(),
        sample_start_column=int(
            expression_spec.get("sample_start_column") or 4
        ),
        allowed_unmapped_sample_patterns=[
            str(value)
            for value in (
                expression_spec.get("allowed_unmapped_sample_patterns")
                or []
            )
        ],
        expected_source_sample_columns=optional_int(
            expression_spec.get("expected_source_sample_columns")
        ),
        expected_mapped_sample_columns=optional_int(
            expression_spec.get("expected_mapped_sample_columns")
        ),
        expected_selected_patients=optional_int(
            expression_spec.get("expected_selected_patients")
        ),
        minimum_gene_rows=int(
            expression_spec.get("minimum_gene_rows") or 10_000
        ),
    )
    selected_samples = materialized["selected_samples"]
    selected_patient_ids = [
        str(selected_samples[sample_id]["_PATIENT_ID"])
        for sample_id in selected_samples
    ]

    patient_table = source_dir / "data_clinical_patient.txt"
    patient_fields = [
        "PATIENT_ID",
        *[
            field
            for field in clinical_rows[0]
            if field != "PATIENT_ID"
        ],
        "ZENODO_CLINICAL_METADATA_JSON",
    ]
    write_tsv(
        patient_table,
        [
            {
                "PATIENT_ID": patient_id,
                **clinical_by_patient[patient_id],
                "ZENODO_CLINICAL_METADATA_JSON": canonical_json(
                    clinical_by_patient[patient_id]
                ),
            }
            for patient_id in selected_patient_ids
        ],
        patient_fields,
    )

    sample_table = source_dir / "data_clinical_sample.txt"
    sample_type = str(
        clinical_spec.get("output_sample_type")
        or "Primary tumor"
    )
    write_tsv(
        sample_table,
        [
            {
                "SAMPLE_ID": sample_id,
                "PATIENT_ID": selected_samples[sample_id][
                    "_PATIENT_ID"
                ],
                "SAMPLE_TYPE": sample_type,
                "LIBRARY_SIZE": format(
                    float(selected_samples[sample_id]["_LIBRARY_SIZE"]),
                    ".17g",
                ),
                "SELECTION_METHOD": (
                    "highest total raw-count library within patient; "
                    "sample ID resolves exact ties"
                ),
                "ZENODO_SAMPLE_METADATA_JSON": canonical_json(
                    {
                        key: value
                        for key, value in selected_samples[sample_id].items()
                        if not key.startswith("_")
                    }
                ),
            }
            for sample_id in selected_samples
        ],
        [
            "SAMPLE_ID",
            "PATIENT_ID",
            "SAMPLE_TYPE",
            "LIBRARY_SIZE",
            "SELECTION_METHOD",
            "ZENODO_SAMPLE_METADATA_JSON",
        ],
    )

    record_path = source_dir / "zenodo_record.json"
    record_path.write_text(
        canonical_json(record) + "\n", encoding="utf-8"
    )
    source_snapshot_payload = {
        "record_id": record_id,
        "record_revision": int(record.get("revision") or 0),
        "record_updated": str(record.get("updated") or ""),
        "record_doi": str(record.get("doi") or ""),
        "expression_archive": {
            "key": archive_key,
            "size": archive_path.stat().st_size,
            "md5": expected_md5,
            "sha256": sha256_file(archive_path),
            "member": archive_member,
        },
        "clinical_supplement": {
            "url": clinical_url,
            "size": clinical_path.stat().st_size,
            "sha256": sha256_file(clinical_path),
        },
        "license_evidence_sha256": sha256_file(license_path),
    }
    source_snapshot = hashlib.sha256(
        canonical_json(source_snapshot_payload).encode("utf-8")
    ).hexdigest()
    source_manifest_path = source_dir / "zenodo_source_manifest.json"
    source_manifest_path.write_text(
        canonical_json(
            {
                "schema_version": (
                    "tcga-trace-zenodo-source-manifest-v1"
                ),
                **source_snapshot_payload,
                "record_url": record_url,
                "selection": {
                    "rule": (
                        "highest total raw-count library per patient, "
                        "then lexical sample ID"
                    ),
                    "outcome_independent": True,
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )

    public_summary = {
        key: value
        for key, value in materialized.items()
        if key != "selected_samples"
    }
    return (
        {
            "expression": source_dir / "data_expression_selected.tsv",
            "patients": patient_table,
            "samples": sample_table,
            "expression_archive": archive_path,
            "clinical_supplement": clinical_path,
            "zenodo_record": record_path,
            "source_manifest": source_manifest_path,
            "license": license_path,
        },
        source_snapshot,
        str(source_spec.get("publication_date") or "") or None,
        {
            "source_api": api_base,
            "source_zenodo_record_id": record_id,
            "source_zenodo_revision": int(record.get("revision") or 0),
            "source_zenodo_doi": str(record.get("doi") or ""),
            "source_zenodo_license": str(
                ((record.get("metadata") or {}).get("license") or {}).get(
                    "id"
                )
                or ""
            ),
            "source_clinical_rows": len(clinical_rows),
            "source_sample_map_rows": len(sample_map_rows),
            "source_sample_selection_rule": (
                "highest total raw-count library per patient, then sample ID"
            ),
            "source_sample_selection_outcome_independent": True,
            **public_summary,
        },
    )


def materialize_direct_zenodo_matrix_source(
    spec: dict[str, Any],
    source_dir: Path,
    *,
    record: dict[str, Any],
    record_url: str,
    api_base: str,
    remote_files: dict[str, dict[str, Any]],
) -> tuple[dict[str, Path], str, str | None, dict[str, Any]]:
    source_spec = spec["source"]
    matrix_spec = source_spec.get("expression_matrix") or {}
    clinical_spec = source_spec.get("clinical") or {}
    matrix_path = download_pinned_zenodo_file(
        remote_files,
        matrix_spec,
        source_dir,
        label="Expression matrix",
    )
    (
        clinical_path,
        clinical_archive_path,
        clinical_snapshot,
    ) = materialize_direct_clinical_file(
        remote_files,
        clinical_spec,
        source_dir,
    )

    clinical_rows = read_xlsx_sheet(
        clinical_path,
        sheet_name=str(clinical_spec.get("patient_sheet") or "").strip(),
        header_row=int(clinical_spec.get("patient_header_row") or 1),
    )
    patient_id_column = str(
        clinical_spec.get("patient_id_column") or ""
    ).strip()
    if not patient_id_column:
        raise ValueError(
            "Direct Zenodo matrices require a clinical patient ID column."
        )
    clinical_by_patient = unique_rows_by_field(
        clinical_rows, patient_id_column, label="clinical patient"
    )
    eligibility_column = str(
        clinical_spec.get("expression_eligibility_column") or ""
    ).strip()
    allowed_eligibility_values = {
        str(value).strip().casefold()
        for value in (
            clinical_spec.get("expression_eligibility_values") or []
        )
        if str(value).strip()
    }
    patient_id_include_patterns = [
        re.compile(str(value))
        for value in (
            clinical_spec.get("patient_id_include_patterns") or []
        )
        if str(value).strip()
    ]
    eligible_clinical = {
        patient_id: row
        for patient_id, row in clinical_by_patient.items()
        if (
            (
                not eligibility_column
                or str(row.get(eligibility_column) or "")
                .strip()
                .casefold()
                in allowed_eligibility_values
            )
            and (
                not patient_id_include_patterns
                or any(
                    pattern.search(patient_id)
                    for pattern in patient_id_include_patterns
                )
            )
        )
    }
    expected_eligible = optional_int(
        clinical_spec.get("expected_expression_eligible_patients")
    )
    if (
        expected_eligible is not None
        and len(eligible_clinical) != expected_eligible
    ):
        raise ValueError(
            "Zenodo clinical expression-eligibility count changed."
        )

    expression_spec = source_spec.get("expression") or {}
    materialized = materialize_direct_patient_matrix(
        matrix_path,
        target=source_dir / "data_expression_selected.tsv",
        clinical_by_patient=eligible_clinical,
        delimiter=str(expression_spec.get("delimiter") or "\t"),
        feature_column=str(
            expression_spec.get("feature_column") or ""
        ).strip(),
        sample_start_column=int(
            expression_spec.get("sample_start_column") or 2
        ),
        sample_to_patient_replacements=[
            (str(pair[0]), str(pair[1]))
            for pair in (
                expression_spec.get("sample_to_patient_replacements")
                or []
            )
            if isinstance(pair, list) and len(pair) == 2
        ],
        allowed_unmapped_sample_patterns=[
            str(value)
            for value in (
                expression_spec.get("allowed_unmapped_sample_patterns")
                or []
            )
        ],
        allow_negative_values=bool(
            expression_spec.get("allow_negative_values")
        ),
        expected_source_sample_columns=optional_int(
            expression_spec.get("expected_source_sample_columns")
        ),
        expected_selected_sample_columns=optional_int(
            expression_spec.get("expected_selected_sample_columns")
        ),
        expected_gene_rows=optional_int(
            expression_spec.get("expected_gene_rows")
        ),
        minimum_gene_rows=int(
            expression_spec.get("minimum_gene_rows") or 10_000
        ),
    )
    selected_samples = materialized["selected_samples"]
    selected_patient_ids = [
        str(selected_samples[sample_id]["_PATIENT_ID"])
        for sample_id in selected_samples
    ]
    if set(selected_patient_ids) != set(eligible_clinical):
        missing = sorted(set(eligible_clinical) - set(selected_patient_ids))
        unexpected = sorted(
            set(selected_patient_ids) - set(eligible_clinical)
        )
        raise ValueError(
            "Zenodo expression and expression-eligible clinical patients "
            f"differ (missing={missing[:5]}, unexpected={unexpected[:5]})."
        )

    patient_table = source_dir / "data_clinical_patient.txt"
    patient_fields = [
        "PATIENT_ID",
        *[
            field
            for field in clinical_rows[0]
            if field != "PATIENT_ID"
        ],
        "ZENODO_CLINICAL_METADATA_JSON",
    ]
    write_tsv(
        patient_table,
        [
            {
                "PATIENT_ID": patient_id,
                **clinical_by_patient[patient_id],
                "ZENODO_CLINICAL_METADATA_JSON": canonical_json(
                    clinical_by_patient[patient_id]
                ),
            }
            for patient_id in selected_patient_ids
        ],
        patient_fields,
    )

    sample_type = str(
        clinical_spec.get("output_sample_type")
        or "Primary tumor"
    )
    sample_table = source_dir / "data_clinical_sample.txt"
    write_tsv(
        sample_table,
        [
            {
                "SAMPLE_ID": sample_id,
                "PATIENT_ID": selected_samples[sample_id]["_PATIENT_ID"],
                "SAMPLE_TYPE": sample_type,
                "SELECTION_METHOD": (
                    "one source RNA profile per patient; exact normalized "
                    "identifier map"
                ),
                "ZENODO_SAMPLE_METADATA_JSON": canonical_json(
                    {
                        "source_sample_id": sample_id,
                        "source_patient_id": selected_samples[sample_id][
                            "_PATIENT_ID"
                        ],
                    }
                ),
            }
            for sample_id in selected_samples
        ],
        [
            "SAMPLE_ID",
            "PATIENT_ID",
            "SAMPLE_TYPE",
            "SELECTION_METHOD",
            "ZENODO_SAMPLE_METADATA_JSON",
        ],
    )

    record_path = source_dir / "zenodo_record.json"
    record_path.write_text(
        canonical_json(record) + "\n", encoding="utf-8"
    )
    clinical_license_path: Path | None = None
    clinical_license_sha256: str | None = None
    clinical_license_url = str(
        source_spec.get("license_evidence_url") or ""
    ).strip()
    if clinical_license_url:
        clinical_license_path = (
            source_dir / "CLINICAL_LICENSE_EVIDENCE.json"
        )
        download(clinical_license_url, clinical_license_path)
        clinical_license_evidence = json.loads(
            clinical_license_path.read_text(encoding="utf-8")
        )
        validate_crossref_license(
            clinical_license_evidence,
            expected_doi=str(
                source_spec.get("publication_doi") or ""
            ),
            expected_license_url=str(
                source_spec.get("expected_clinical_license_url") or ""
            ),
        )
        clinical_license_sha256 = sha256_file(
            clinical_license_path
        )
    elif clinical_spec.get("url"):
        raise ValueError(
            "An externally hosted direct clinical table requires "
            "license_evidence_url."
        )

    license_path = source_dir / "SOURCE_LICENSE_EVIDENCE.json"
    license_path.write_text(
        canonical_json(
            {
                "record_id": int(record.get("id") or 0),
                "record_doi": str(record.get("doi") or ""),
                "license": (record.get("metadata") or {}).get("license"),
                "record_url": record_url,
                "clinical_publication": (
                    {
                        "doi": str(
                            source_spec.get("publication_doi") or ""
                        ),
                        "license_url": str(
                            source_spec.get(
                                "expected_clinical_license_url"
                            )
                            or ""
                        ),
                        "evidence_sha256": clinical_license_sha256,
                    }
                    if clinical_license_path
                    else None
                ),
            }
        )
        + "\n",
        encoding="utf-8",
    )
    source_snapshot_payload = {
        "record_id": int(record.get("id") or 0),
        "record_revision": int(record.get("revision") or 0),
        "record_updated": str(record.get("updated") or ""),
        "record_doi": str(record.get("doi") or ""),
        "expression_matrix": pinned_file_snapshot(
            matrix_path, matrix_spec
        ),
        "clinical_table": clinical_snapshot,
        "license_evidence_sha256": sha256_file(license_path),
        "clinical_license_evidence_sha256": clinical_license_sha256,
    }
    source_snapshot = hashlib.sha256(
        canonical_json(source_snapshot_payload).encode("utf-8")
    ).hexdigest()
    source_manifest_path = source_dir / "zenodo_source_manifest.json"
    source_manifest_path.write_text(
        canonical_json(
            {
                "schema_version": (
                    "tcga-trace-zenodo-source-manifest-v2"
                ),
                **source_snapshot_payload,
                "record_url": record_url,
                "selection": {
                    "rule": (
                        "one expression column per exact normalized patient "
                        "identifier"
                    ),
                    "outcome_independent": True,
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )

    public_summary = {
        key: value
        for key, value in materialized.items()
        if key != "selected_samples"
    }
    source_files = {
        "expression": source_dir / "data_expression_selected.tsv",
        "patients": patient_table,
        "samples": sample_table,
        "expression_matrix": matrix_path,
        "clinical_table": clinical_path,
        "zenodo_record": record_path,
        "source_manifest": source_manifest_path,
        "license": license_path,
    }
    if clinical_archive_path is not None:
        source_files["clinical_archive"] = clinical_archive_path
    if clinical_license_path is not None:
        source_files["clinical_license"] = clinical_license_path

    return (
        source_files,
        source_snapshot,
        str(source_spec.get("publication_date") or "") or None,
        {
            "source_api": api_base,
            "source_zenodo_record_id": int(record.get("id") or 0),
            "source_zenodo_revision": int(record.get("revision") or 0),
            "source_zenodo_doi": str(record.get("doi") or ""),
            "source_zenodo_license": str(
                ((record.get("metadata") or {}).get("license") or {}).get(
                    "id"
                )
                or ""
            ),
            "source_clinical_rows": len(clinical_rows),
            "source_expression_eligible_clinical_rows": len(
                eligible_clinical
            ),
            "source_sample_selection_rule": (
                "one source RNA profile per patient; exact normalized "
                "identifier map"
            ),
            "source_sample_selection_outcome_independent": True,
            **public_summary,
        },
    )


def materialize_direct_clinical_file(
    remote_files: dict[str, dict[str, Any]],
    clinical_spec: dict[str, Any],
    source_dir: Path,
) -> tuple[Path, Path | None, dict[str, Any]]:
    if clinical_spec.get("key"):
        clinical_path = download_pinned_zenodo_file(
            remote_files,
            clinical_spec,
            source_dir,
            label="Clinical table",
        )
        return (
            clinical_path,
            None,
            pinned_file_snapshot(clinical_path, clinical_spec),
        )

    source_url = str(clinical_spec.get("url") or "").strip()
    source_name = str(clinical_spec.get("name") or "").strip()
    if (
        not source_url
        or not source_name
        or Path(source_name).name != source_name
    ):
        raise ValueError(
            "External direct clinical tables require a safe name and URL."
        )
    source_path = source_dir / source_name
    download(source_url, source_path)
    verify_size_and_sha256(
        source_path,
        expected_size=clinical_spec.get("size"),
        expected_sha256=clinical_spec.get("sha256"),
        label="Clinical source",
    )

    archive_member = str(
        clinical_spec.get("archive_member") or ""
    ).strip()
    if not archive_member:
        return (
            source_path,
            None,
            {
                "url": source_url,
                "name": source_name,
                "size": source_path.stat().st_size,
                "sha256": sha256_file(source_path),
            },
        )
    if (
        Path(archive_member).is_absolute()
        or ".." in Path(archive_member).parts
    ):
        raise ValueError("Clinical archive member must be a safe path.")
    extracted_name = str(
        clinical_spec.get("extracted_name")
        or Path(archive_member).name
    ).strip()
    if (
        not extracted_name
        or Path(extracted_name).name != extracted_name
    ):
        raise ValueError("Extracted clinical filename must be safe.")
    clinical_path = source_dir / extracted_name
    with zipfile.ZipFile(source_path) as archive:
        if archive_member not in archive.namelist():
            raise ValueError(
                f"Clinical archive is missing member {archive_member!r}."
            )
        with archive.open(archive_member) as source, clinical_path.open(
            "wb"
        ) as target:
            shutil.copyfileobj(source, target)
    verify_size_and_sha256(
        clinical_path,
        expected_size=clinical_spec.get("member_size"),
        expected_sha256=clinical_spec.get("member_sha256"),
        label="Extracted clinical table",
    )
    return (
        clinical_path,
        source_path,
        {
            "url": source_url,
            "archive": {
                "name": source_name,
                "size": source_path.stat().st_size,
                "sha256": sha256_file(source_path),
            },
            "member": {
                "path": archive_member,
                "name": extracted_name,
                "size": clinical_path.stat().st_size,
                "sha256": sha256_file(clinical_path),
            },
        },
    )


def download_pinned_zenodo_file(
    remote_files: dict[str, dict[str, Any]],
    file_spec: dict[str, Any],
    source_dir: Path,
    *,
    label: str,
) -> Path:
    key = str(file_spec.get("key") or "").strip()
    if not key or Path(key).name != key:
        raise ValueError(f"{label} requires a safe Zenodo file key.")
    remote = remote_files.get(key)
    if remote is None:
        raise ValueError(f"Zenodo record is missing pinned file {key!r}.")
    expected_md5 = validate_zenodo_file_pin(remote, file_spec)
    target = source_dir / key
    download(str((remote.get("links") or {}).get("self") or ""), target)
    if md5_file(target) != expected_md5:
        raise ValueError(f"{label} failed MD5 validation.")
    expected_sha256 = str(
        file_spec.get("sha256") or ""
    ).strip().lower()
    if (
        expected_sha256
        and sha256_file(target) != expected_sha256
    ):
        raise ValueError(f"{label} failed SHA-256 validation.")
    return target


def pinned_file_snapshot(
    path: Path, file_spec: dict[str, Any]
) -> dict[str, Any]:
    return {
        "key": str(file_spec.get("key") or ""),
        "size": path.stat().st_size,
        "md5": md5_file(path),
        "sha256": sha256_file(path),
    }


def materialize_direct_patient_matrix(
    source_path: Path,
    *,
    target: Path,
    clinical_by_patient: dict[str, dict[str, str]],
    delimiter: str,
    feature_column: str,
    sample_start_column: int,
    sample_to_patient_replacements: list[tuple[str, str]],
    allowed_unmapped_sample_patterns: list[str] | None = None,
    allow_negative_values: bool = False,
    expected_source_sample_columns: int | None,
    expected_selected_sample_columns: int | None = None,
    expected_gene_rows: int | None,
    minimum_gene_rows: int,
) -> dict[str, Any]:
    if not feature_column or sample_start_column < 2:
        raise ValueError(
            "Direct Zenodo matrices require a feature column and valid "
            "sample_start_column."
        )
    with source_path.open(
        newline="", encoding="utf-8-sig"
    ) as source, target.open(
        "w", newline="", encoding="utf-8"
    ) as output:
        reader = csv.reader(source, delimiter=delimiter)
        header = next(reader)
        try:
            feature_index = header.index(feature_column)
        except ValueError as error:
            raise ValueError(
                f"Feature column {feature_column!r} is absent."
            ) from error
        sample_start_index = sample_start_column - 1
        source_sample_ids = [
            value.strip() for value in header[sample_start_index:]
        ]
        if (
            not all(source_sample_ids)
            or len(source_sample_ids) != len(set(source_sample_ids))
        ):
            raise ValueError(
                "Direct Zenodo expression sample IDs are missing or "
                "duplicated."
            )
        if (
            expected_source_sample_columns is not None
            and len(source_sample_ids) != expected_source_sample_columns
        ):
            raise ValueError(
                "Direct Zenodo source sample-column count changed."
            )

        patterns = [
            re.compile(value)
            for value in (allowed_unmapped_sample_patterns or [])
        ]
        selected_samples: dict[str, dict[str, str]] = {}
        selected_patient_ids: set[str] = set()
        for sample_id in source_sample_ids:
            patient_id = sample_id
            for source_value, target_value in (
                sample_to_patient_replacements
            ):
                patient_id = patient_id.replace(
                    source_value, target_value
                )
            if patient_id not in clinical_by_patient:
                if any(
                    pattern.search(sample_id)
                    or pattern.search(patient_id)
                    for pattern in patterns
                ):
                    continue
                raise ValueError(
                    "Direct Zenodo expression sample has no eligible "
                    f"clinical patient: {sample_id!r} -> {patient_id!r}."
                )
            if patient_id in selected_patient_ids:
                raise ValueError(
                    "Direct Zenodo expression maps multiple samples to "
                    f"patient {patient_id!r}."
                )
            selected_patient_ids.add(patient_id)
            selected_samples[sample_id] = {
                "_PATIENT_ID": patient_id,
                "_SAMPLE_ID": sample_id,
            }
        if (
            expected_selected_sample_columns is not None
            and len(selected_samples)
            != expected_selected_sample_columns
        ):
            raise ValueError(
                "Direct Zenodo selected sample-column count changed."
            )

        writer = csv.writer(
            output, delimiter="\t", lineterminator="\n"
        )
        selected_sample_ids = list(selected_samples)
        writer.writerow([feature_column, *selected_sample_ids])
        seen_features: set[str] = set()
        gene_rows = 0
        sample_indexes = [
            header.index(sample_id)
            for sample_id in selected_sample_ids
        ]
        for row in reader:
            if not row:
                continue
            if len(row) != len(header):
                raise ValueError(
                    "Direct Zenodo matrix row width is inconsistent."
                )
            feature = row[feature_index].strip()
            if not feature:
                raise ValueError(
                    "Direct Zenodo matrix contains an empty feature."
                )
            normalized_feature = feature.upper()
            if normalized_feature in seen_features:
                raise ValueError(
                    "Direct Zenodo matrix contains duplicate feature "
                    f"{feature!r}."
                )
            seen_features.add(normalized_feature)
            values = parse_finite_expression_values(
                row,
                sample_indexes,
                feature,
                allow_negative_values=allow_negative_values,
            )
            writer.writerow(
                [
                    feature,
                    *(format(value, ".17g") for value in values),
                ]
            )
            gene_rows += 1

    if gene_rows < minimum_gene_rows:
        raise ValueError(
            "Direct Zenodo expression has fewer than "
            f"{minimum_gene_rows:,} genes."
        )
    if (
        expected_gene_rows is not None
        and gene_rows != expected_gene_rows
    ):
        raise ValueError("Direct Zenodo expression gene count changed.")
    return {
        "source_expression_layout": "zenodo_wide_expression_matrix",
        "source_expression_sample_columns": len(source_sample_ids),
        "source_unmapped_allowed_columns": (
            len(source_sample_ids) - len(selected_samples)
        ),
        "source_expression_gene_rows": gene_rows,
        "normalized_expression_gene_rows": gene_rows,
        "source_expression_feature_column": feature_column,
        "selected_expression_patients": len(selected_samples),
        "expression_normalization": (
            "publisher-provided finite values retained"
        ),
        "source_expression_allows_negative_values": (
            allow_negative_values
        ),
        "selected_samples": selected_samples,
    }


def validate_zenodo_record(
    record: dict[str, Any],
    source_spec: dict[str, Any],
    *,
    record_id: int,
) -> None:
    if int(record.get("id") or 0) != record_id:
        raise ValueError("Zenodo API returned the wrong record.")
    expected_doi = str(source_spec.get("record_doi") or "").strip()
    if expected_doi and str(record.get("doi") or "") != expected_doi:
        raise ValueError("Zenodo record DOI changed.")
    expected_revision = optional_int(
        source_spec.get("expected_revision")
    )
    if (
        expected_revision is not None
        and int(record.get("revision") or 0) != expected_revision
    ):
        raise ValueError("Zenodo record revision changed.")
    license_id = str(
        ((record.get("metadata") or {}).get("license") or {}).get("id")
        or ""
    ).strip()
    expected_license = str(
        source_spec.get("expected_zenodo_license") or ""
    ).strip()
    if not license_id or (
        expected_license and license_id != expected_license
    ):
        raise ValueError(
            f"Zenodo license does not match: {license_id!r}."
        )


def validate_zenodo_file_pin(
    remote: dict[str, Any],
    file_spec: dict[str, Any],
) -> str:
    expected_size = int(file_spec.get("size") or 0)
    expected_md5 = str(file_spec.get("md5") or "").strip().lower()
    remote_checksum = str(remote.get("checksum") or "").strip().lower()
    download_url = str(
        (remote.get("links") or {}).get("self") or ""
    ).strip()
    if (
        expected_size <= 0
        or int(remote.get("size") or 0) != expected_size
        or not re.fullmatch(r"[0-9a-f]{32}", expected_md5)
        or remote_checksum != f"md5:{expected_md5}"
        or not download_url
    ):
        raise ValueError("Zenodo expression archive pin changed.")
    return expected_md5


def validate_crossref_license(
    payload: dict[str, Any],
    *,
    expected_doi: str,
    expected_license_url: str,
) -> None:
    message = payload.get("message") or {}
    if (
        not expected_doi
        or str(message.get("DOI") or "").casefold()
        != expected_doi.casefold()
    ):
        raise ValueError("Crossref license record has the wrong DOI.")
    licenses = {
        str(item.get("URL") or "").replace("http://", "https://").rstrip("/")
        for item in message.get("license") or []
    }
    expected = expected_license_url.replace(
        "http://", "https://"
    ).rstrip("/")
    if not expected or expected not in licenses:
        raise ValueError(
            "Crossref does not expose the reviewed clinical license."
        )


def materialize_patient_level_counts(
    archive_path: Path,
    *,
    archive_member: str,
    target: Path,
    mapped_samples: dict[str, dict[str, str]],
    delimiter: str,
    feature_column: str,
    sample_start_column: int,
    allowed_unmapped_sample_patterns: list[str],
    expected_source_sample_columns: int | None,
    expected_mapped_sample_columns: int | None,
    expected_selected_patients: int | None,
    minimum_gene_rows: int,
) -> dict[str, Any]:
    if not feature_column or sample_start_column < 2:
        raise ValueError(
            "Zenodo count matrices require a feature column and valid "
            "sample_start_column."
        )
    patterns = [re.compile(value) for value in allowed_unmapped_sample_patterns]
    with zipfile.ZipFile(archive_path) as archive:
        if archive_member not in archive.namelist():
            raise ValueError(
                f"Zenodo archive is missing member {archive_member!r}."
            )
        with archive.open(archive_member) as binary:
            text = io.TextIOWrapper(
                binary, encoding="utf-8-sig", newline=""
            )
            reader = csv.reader(text, delimiter=delimiter)
            header = next(reader)
            try:
                feature_index = header.index(feature_column)
            except ValueError as error:
                raise ValueError(
                    f"Feature column {feature_column!r} is absent."
                ) from error
            sample_start_index = sample_start_column - 1
            source_sample_ids = [
                value.strip()
                for value in header[sample_start_index:]
                if value.strip()
            ]
            if len(source_sample_ids) != len(set(source_sample_ids)):
                raise ValueError(
                    "Zenodo expression sample IDs are duplicated."
                )
            if (
                expected_source_sample_columns is not None
                and len(source_sample_ids)
                != expected_source_sample_columns
            ):
                raise ValueError(
                    "Zenodo source sample-column count changed."
                )
            mapped_ids = [
                sample_id
                for sample_id in source_sample_ids
                if sample_id in mapped_samples
            ]
            unexpected = [
                sample_id
                for sample_id in source_sample_ids
                if sample_id not in mapped_samples
                and not any(
                    pattern.search(sample_id) for pattern in patterns
                )
            ]
            if unexpected:
                raise ValueError(
                    "Zenodo expression contains unmapped non-eligible "
                    f"samples: {unexpected[:5]}"
                )
            if (
                expected_mapped_sample_columns is not None
                and len(mapped_ids) != expected_mapped_sample_columns
            ):
                raise ValueError(
                    "Zenodo mapped tumor-column count changed."
                )
            indexes = [
                header.index(sample_id) for sample_id in mapped_ids
            ]
            library_sizes = [0.0] * len(mapped_ids)
            gene_rows = 0
            for row in reader:
                if not row:
                    continue
                if len(row) != len(header):
                    raise ValueError(
                        "Zenodo count-matrix row width is inconsistent."
                    )
                feature = row[feature_index].strip()
                if not feature:
                    continue
                values = parse_nonnegative_counts(
                    row, indexes, feature
                )
                library_sizes = [
                    current + incoming
                    for current, incoming in zip(
                        library_sizes, values, strict=True
                    )
                ]
                gene_rows += 1
    if gene_rows < minimum_gene_rows:
        raise ValueError(
            f"Zenodo expression has fewer than {minimum_gene_rows:,} genes."
        )
    if any(value <= 0 for value in library_sizes):
        raise ValueError(
            "Zenodo count matrix contains an empty mapped library."
        )

    selected_samples = select_deepest_library_per_patient(
        {
            sample_id: {
                **mapped_samples[sample_id],
                "_LIBRARY_SIZE": library_size,
            }
            for sample_id, library_size in zip(
                mapped_ids, library_sizes, strict=True
            )
        }
    )
    if (
        expected_selected_patients is not None
        and len(selected_samples) != expected_selected_patients
    ):
        raise ValueError(
            "Zenodo patient-level selected sample count changed."
        )
    selected_ids = list(selected_samples)
    selected_library_sizes = [
        float(selected_samples[sample_id]["_LIBRARY_SIZE"])
        for sample_id in selected_ids
    ]

    with zipfile.ZipFile(archive_path) as archive:
        with archive.open(archive_member) as binary, target.open(
            "w", newline="", encoding="utf-8"
        ) as output:
            text = io.TextIOWrapper(
                binary, encoding="utf-8-sig", newline=""
            )
            reader = csv.reader(text, delimiter=delimiter)
            header = next(reader)
            indexes = [header.index(sample_id) for sample_id in selected_ids]
            writer = csv.writer(
                output, delimiter="\t", lineterminator="\n"
            )
            writer.writerow([feature_column, *selected_ids])
            written_rows = 0
            for row in reader:
                if not row:
                    continue
                feature = row[feature_index].strip()
                if not feature:
                    continue
                values = parse_nonnegative_counts(
                    row, indexes, feature
                )
                normalized = [
                    math.log2(
                        (value / library_size) * 1_000_000.0 + 1.0
                    )
                    for value, library_size in zip(
                        values,
                        selected_library_sizes,
                        strict=True,
                    )
                ]
                writer.writerow(
                    [
                        feature,
                        *(
                            format(value, ".17g")
                            for value in normalized
                        ),
                    ]
                )
                written_rows += 1
    return {
        "source_expression_layout": "zenodo_zip_wide_gene_counts_tsv",
        "source_expression_sample_columns": len(source_sample_ids),
        "source_mapped_tumor_columns": len(mapped_ids),
        "source_unmapped_allowed_columns": (
            len(source_sample_ids) - len(mapped_ids)
        ),
        "source_expression_gene_rows": gene_rows,
        "normalized_expression_gene_rows": written_rows,
        "source_expression_feature_column": feature_column,
        "selected_expression_patients": len(selected_samples),
        "expression_normalization": "log2(CPM + 1)",
        "selected_samples": selected_samples,
    }


def select_deepest_library_per_patient(
    samples: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    by_patient: dict[str, list[tuple[str, dict[str, Any]]]] = {}
    for sample_id, row in samples.items():
        patient_id = str(row.get("_PATIENT_ID") or "").strip()
        library_size = float(row.get("_LIBRARY_SIZE") or 0)
        if not patient_id or not math.isfinite(library_size) or library_size <= 0:
            raise ValueError(
                f"Sample {sample_id!r} has invalid patient or library size."
            )
        by_patient.setdefault(patient_id, []).append((sample_id, row))
    selected: dict[str, dict[str, Any]] = {}
    for patient_id in sorted(by_patient):
        sample_id, row = min(
            by_patient[patient_id],
            key=lambda item: (
                -float(item[1]["_LIBRARY_SIZE"]),
                item[0],
            ),
        )
        selected[sample_id] = row
    return selected


def unique_rows_by_field(
    rows: list[dict[str, str]],
    field: str,
    *,
    label: str,
) -> dict[str, dict[str, str]]:
    output: dict[str, dict[str, str]] = {}
    for row in rows:
        value = str(row.get(field) or "").strip()
        if not value:
            raise ValueError(f"A {label} row is missing {field!r}.")
        if value in output:
            raise ValueError(f"Duplicate {label} identifier {value!r}.")
        output[value] = row
    return output


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


def parse_finite_expression_values(
    row: list[str],
    indexes: list[int],
    feature: str,
    *,
    allow_negative_values: bool,
) -> list[float]:
    try:
        values = [float(row[index]) for index in indexes]
    except (IndexError, ValueError) as error:
        raise ValueError(
            f"Invalid expression value at feature {feature!r}."
        ) from error
    if any(
        not math.isfinite(value)
        or (not allow_negative_values and value < 0)
        for value in values
    ):
        qualifier = "non-finite" if allow_negative_values else (
            "non-finite or negative"
        )
        raise ValueError(
            f"{qualifier.capitalize()} expression value at feature "
            f"{feature!r}."
        )
    return values


def verify_size_and_sha256(
    path: Path,
    *,
    expected_size: Any,
    expected_sha256: Any,
    label: str,
) -> None:
    size = int(expected_size or 0)
    digest = str(expected_sha256 or "").strip().lower()
    if (
        size <= 0
        or not re.fullmatch(r"[0-9a-f]{64}", digest)
        or path.stat().st_size != size
        or sha256_file(path) != digest
    ):
        raise ValueError(f"{label} failed its pinned size/SHA-256 check.")


def optional_int(value: Any) -> int | None:
    if value is None or str(value).strip() == "":
        return None
    return int(value)


def md5_file(path: Path) -> str:
    digest = hashlib.md5(usedforsecurity=False)
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
