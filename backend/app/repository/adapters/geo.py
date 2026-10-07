from __future__ import annotations

from array import array
import csv
from datetime import datetime, timedelta
import gzip
import hashlib
import io
import json
import math
import os
from pathlib import Path
from pathlib import PurePosixPath
import re
import shutil
import tarfile
from typing import Any
import urllib.parse
import urllib.request
import zipfile

from app.repository.adapters.cbioportal import (
    USER_AGENT,
    download,
    download_with_http_ranges,
    write_tsv,
)
from app.repository.storage import sha256_file


GEO_ADAPTER_VERSION = "geo_reanalysis_matrix_v24"
RANGE_DOWNLOAD_MINIMUM_BYTES = 512 * 1024 * 1024


def materialize_geo_download(
    url: str,
    path: Path,
    *,
    expected_size: int | None,
    cache_name: str | None = None,
) -> None:
    cache_dir = str(
        os.environ.get("GEO_DOWNLOAD_CACHE_DIR") or ""
    ).strip()
    resolved_cache_name = (
        str(cache_name or "").strip()
        or Path(urllib.parse.urlparse(url).path).name
    )
    cached = (
        Path(cache_dir) / resolved_cache_name
        if cache_dir and resolved_cache_name
        else None
    )
    if cached is not None and cached.is_file():
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(cached, path)
        return
    if (
        expected_size is not None
        and expected_size >= RANGE_DOWNLOAD_MINIMUM_BYTES
        and urllib.parse.urlparse(url).scheme in {"http", "https"}
    ):
        download_with_http_ranges(
            url,
            path,
            total_size=expected_size,
        )
        return
    download(url, path)


def materialize_geo_expression_files(
    value: Any,
    source_dir: Path,
) -> tuple[Path, Path, dict[str, Any]]:
    if not isinstance(value, list) or not value:
        raise ValueError(
            "source.expression_files must be a non-empty list."
        )

    normalized_files: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    seen_urls: set[str] = set()
    for raw_file in value:
        if not isinstance(raw_file, dict):
            raise ValueError(
                "Each GEO expression file must be an object."
            )
        name = str(raw_file.get("name") or "").strip()
        url = str(raw_file.get("url") or "").strip()
        parsed_url = urllib.parse.urlparse(url)
        try:
            size = int(raw_file.get("size"))
        except (TypeError, ValueError) as error:
            raise ValueError(
                "Each GEO expression file requires a positive size."
            ) from error
        digest = str(raw_file.get("sha256") or "").strip().lower()
        if (
            not name
            or not name.isascii()
            or name in {".", ".."}
            or PurePosixPath(name).name != name
            or "\\" in name
            or name in seen_names
            or not url
            or parsed_url.scheme not in {"ftp", "http", "https"}
            or not parsed_url.netloc
            or url in seen_urls
            or size <= 0
            or re.fullmatch(r"[0-9a-f]{64}", digest) is None
        ):
            raise ValueError(
                "GEO expression files require unique safe names and URLs, "
                "a positive size and a valid SHA-256."
            )
        normalized_files.append(
            {
                "name": name,
                "url": url,
                "size": size,
                "sha256": digest,
            }
        )
        seen_names.add(name)
        seen_urls.add(url)

    normalized_files.sort(key=lambda item: item["name"])
    files_dir = source_dir / "geo_expression_files"
    files_dir.mkdir(parents=True, exist_ok=True)
    materialized_paths: dict[str, Path] = {}
    for file_spec in normalized_files:
        path = files_dir / file_spec["name"]
        materialize_geo_download(
            file_spec["url"],
            path,
            expected_size=file_spec["size"],
            cache_name=file_spec["name"],
        )
        verify_pinned_file(
            path,
            expected_size=file_spec["size"],
            expected_sha256=file_spec["sha256"],
            label=f"GEO expression file {file_spec['name']}",
        )
        materialized_paths[file_spec["name"]] = path

    archive_path = source_dir / "geo_expression_files.tar"
    with tarfile.open(
        archive_path,
        mode="w",
        format=tarfile.PAX_FORMAT,
    ) as archive:
        for file_spec in normalized_files:
            path = materialized_paths[file_spec["name"]]
            member = tarfile.TarInfo(file_spec["name"])
            member.size = file_spec["size"]
            member.mtime = 0
            member.uid = 0
            member.gid = 0
            member.uname = ""
            member.gname = ""
            member.mode = 0o644
            member.pax_headers = {}
            with path.open("rb") as handle:
                archive.addfile(member, handle)

    manifest_path = source_dir / "geo_expression_file_manifest.json"
    manifest = {
        "schema_version": (
            "tcga-trace-geo-expression-file-manifest-v1"
        ),
        "files": normalized_files,
    }
    manifest_path.write_text(
        canonical_json(manifest) + "\n",
        encoding="utf-8",
    )
    archive_sha256 = sha256_file(archive_path)
    manifest_sha256 = sha256_file(manifest_path)
    return (
        archive_path,
        manifest_path,
        {
            "geo_source_expression_file_count": len(normalized_files),
            "geo_source_expression_file_manifest_sha256": (
                manifest_sha256
            ),
            "geo_source_expression_archive_sha256": archive_sha256,
            "files": normalized_files,
        },
    )


def materialize_geo_source(
    spec: dict[str, Any],
    source_dir: Path,
) -> tuple[dict[str, Path], str, str | None, dict[str, Any]]:
    source_spec = spec["source"]
    accession = str(source_spec.get("accession") or "").strip().upper()
    expression_url = str(
        source_spec.get("expression_url") or ""
    ).strip()
    expression_files = source_spec.get("expression_files")
    soft_url = str(source_spec.get("soft_url") or "").strip()
    license_url = str(
        source_spec.get("license_evidence_url") or ""
    ).strip()
    if (
        not re.fullmatch(r"GSE[0-9]+", accession)
        or (bool(expression_url) == (expression_files is not None))
        or not soft_url
        or not license_url
    ):
        raise ValueError(
            "GEO sources require a GSE accession, exactly one of "
            "expression_url or expression_files, soft_url and "
            "license_evidence_url."
        )

    expression_file_manifest_path: Path | None = None
    expression_file_metadata: dict[str, Any] = {}
    if expression_files is not None:
        (
            expression_path,
            expression_file_manifest_path,
            expression_file_metadata,
        ) = materialize_geo_expression_files(
            expression_files,
            source_dir,
        )
    else:
        expression_path = source_dir / geo_source_filename(
            expression_url,
            configured_name=source_spec.get("expression_filename"),
            label="expression",
        )
    soft_path = source_dir / geo_source_filename(
        soft_url,
        configured_name=source_spec.get("soft_filename"),
        label="family SOFT",
    )
    license_path = source_dir / "NCBI_GEO_DISCLAIMER.html"
    expected_expression_size = source_spec.get("expression_size")
    if expression_files is None:
        materialize_geo_download(
            expression_url,
            expression_path,
            expected_size=(
                int(expected_expression_size)
                if expected_expression_size is not None
                else None
            ),
            cache_name=expression_path.name,
        )
    materialize_geo_download(
        soft_url,
        soft_path,
        expected_size=(
            int(source_spec["soft_size"])
            if source_spec.get("soft_size") is not None
            else None
        ),
        cache_name=soft_path.name,
    )
    materialize_geo_download(
        license_url,
        license_path,
        expected_size=None,
    )
    if expression_files is None:
        verify_pinned_file(
            expression_path,
            expected_size=source_spec.get("expression_size"),
            expected_sha256=source_spec.get("expression_sha256"),
            label="GEO expression matrix",
        )
    verify_pinned_file(
        soft_path,
        expected_size=source_spec.get("soft_size"),
        expected_sha256=source_spec.get("soft_sha256"),
        label="GEO family SOFT",
    )

    characteristic_conflict_policy = (
        normalize_geo_characteristic_conflict_policy(
            source_spec.get("characteristic_conflict_policy")
        )
    )
    series, primary_soft_samples = parse_geo_family_soft(
        soft_path,
        characteristic_conflict_policy=characteristic_conflict_policy,
    )
    samples = list(primary_soft_samples)
    additional_soft_sources = materialize_geo_additional_soft_sources(
        source_spec.get("additional_soft_sources"),
        source_dir,
    )
    additional_series = []
    additional_soft_paths = []
    seen_accessions = {
        str(sample["geo_accession"])
        for sample in samples
    }
    for additional in additional_soft_sources:
        duplicate_accessions = sorted(
            seen_accessions
            & {
                str(sample["geo_accession"])
                for sample in additional["samples"]
            }
        )
        if duplicate_accessions:
            raise ValueError(
                "Additional GEO family SOFT repeats sample accessions: "
                f"{duplicate_accessions[:5]}"
            )
        samples.extend(additional["samples"])
        seen_accessions.update(
            str(sample["geo_accession"])
            for sample in additional["samples"]
        )
        additional_series.append(additional["series"])
        additional_soft_paths.append(additional["path"])
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

    clinical_spec = dict(source_spec.get("clinical") or {})
    clinical_metadata: dict[str, Any] = {}
    clinical_manifest_path: Path | None = None
    clinical_terms_path: Path | None = None
    clinical_evidence_path: Path | None = None
    expression_support_paths: dict[str, Path] = {}
    expression_support_urls: dict[str, str] = {}
    if clinical_spec:
        if not clinical_spec.get("records"):
            (
                clinical_spec,
                clinical_evidence_path,
            ) = materialize_geo_curated_clinical_evidence(
                clinical_spec,
                source_dir,
            )
        clinical_metadata = attach_geo_curated_clinical_records(
            primary_samples,
            clinical_spec,
        )
        clinical_manifest_path = (
            source_dir / "geo_curated_clinical_manifest.json"
        )
        clinical_manifest_path.write_text(
            canonical_json(
                {
                    "schema_version": (
                        "tcga-trace-geo-curated-clinical-manifest-v1"
                    ),
                    "evidence_url": clinical_spec["evidence_url"],
                    "evidence_size": int(clinical_spec["evidence_size"]),
                    "evidence_sha256": str(
                        clinical_spec["evidence_sha256"]
                    ).lower(),
                    "record_id_column": clinical_spec[
                        "record_id_column"
                    ],
                    "sample_metadata_field": clinical_spec[
                        "sample_metadata_field"
                    ],
                    "sample_id_pattern": clinical_spec[
                        "sample_id_pattern"
                    ],
                    "sample_id_replacement": clinical_spec.get(
                        "sample_id_replacement"
                    ),
                    "field_name_map": clinical_spec.get(
                        "field_name_map"
                    )
                    or {},
                    "evidence_format": clinical_spec.get(
                        "evidence_format"
                    ),
                    "download_mode": clinical_spec.get("download_mode")
                    or "standard",
                    "evidence_pin_scope": clinical_spec.get(
                        "evidence_pin_scope"
                    )
                    or "downloaded_file",
                    "evidence_container_size": clinical_spec.get(
                        "evidence_container_size"
                    ),
                    "archive_member": clinical_spec.get("archive_member"),
                    "sheet_name": clinical_spec.get("sheet_name"),
                    "header_row": clinical_spec.get("header_row"),
                    "header_name_overrides": clinical_spec.get(
                        "header_name_overrides"
                    )
                    or {},
                    "derived_fields": clinical_spec.get("derived_fields")
                    or [],
                    "derived_field_summary": clinical_spec.get(
                        "derived_field_summary"
                    )
                    or {},
                    "allow_unmatched_records": bool(
                        clinical_spec.get("allow_unmatched_records")
                    ),
                    "records": clinical_spec["records"],
                    "records_sha256": clinical_metadata[
                        "geo_curated_clinical_records_sha256"
                    ],
                }
            )
            + "\n",
            encoding="utf-8",
        )
        clinical_terms_url = str(
            clinical_spec.get("terms_url") or ""
        ).strip()
        if clinical_terms_url:
            clinical_terms_path = (
                source_dir / "PMC_COPYRIGHT_NOTICE.html"
            )
            download(clinical_terms_url, clinical_terms_path)
    characteristic_filters = (
        source_spec.get("sample_characteristic_filters") or []
    )
    filtered_primary_samples = [
        sample
        for sample in primary_samples
        if sample_passes_characteristic_filters(
            {
                **sample["characteristics"],
                "source name": sample.get("source_name"),
            },
            characteristic_filters,
        )
    ]
    expected_filtered = source_spec.get(
        "expected_characteristic_eligible_samples"
    )
    if (
        expected_filtered is not None
        and len(filtered_primary_samples) != int(expected_filtered)
    ):
        raise ValueError(
            "GEO characteristic-eligible sample count changed: "
            f"{len(filtered_primary_samples)} != {expected_filtered}."
        )
    if len(filtered_primary_samples) < 10:
        raise ValueError(
            "GEO source has fewer than 10 characteristic-eligible samples."
        )

    patient_id_characteristic = str(
        source_spec.get("patient_id_characteristic") or ""
    ).strip().casefold()
    (
        selected_primary_samples,
        patient_selection_metadata,
    ) = select_geo_patient_samples(
        filtered_primary_samples,
        patient_id_characteristic=patient_id_characteristic,
        selection_spec=source_spec.get("patient_sample_selection"),
    )

    endpoint_spec = spec["endpoints"][0]
    time_characteristic = str(
        source_spec.get("time_characteristic")
        or endpoint_spec["time_column"]
    ).strip().casefold()
    time_start_characteristic = str(
        source_spec.get("time_start_characteristic") or ""
    ).strip().casefold()
    time_end_characteristic = str(
        source_spec.get("time_end_characteristic") or ""
    ).strip().casefold()
    if bool(time_start_characteristic) != bool(time_end_characteristic):
        raise ValueError(
            "GEO date-derived endpoints require both "
            "time_start_characteristic and time_end_characteristic."
        )
    event_characteristic = str(
        source_spec.get("event_characteristic")
        or endpoint_spec["event_column"]
    ).strip().casefold()
    event_value_map = normalized_event_value_map(
        source_spec.get("event_value_map")
    )
    endpoint_time_column = str(endpoint_spec["time_column"]).strip()
    endpoint_event_column = str(endpoint_spec["event_column"]).strip()
    expression_sample_characteristic = str(
        source_spec.get("expression_sample_characteristic") or ""
    ).strip().casefold()
    expression_sample_metadata_field = str(
        source_spec.get("expression_sample_metadata_field") or ""
    ).strip().casefold()
    if (
        expression_sample_characteristic
        and expression_sample_metadata_field
    ):
        raise ValueError(
            "GEO expression sample IDs may use either a characteristic "
            "or a metadata field, not both."
        )
    age_characteristic = str(
        source_spec.get("age_characteristic") or ""
    ).strip().casefold()
    try:
        age_divisor = float(source_spec.get("age_divisor") or 1.0)
    except (TypeError, ValueError) as error:
        raise ValueError("source.age_divisor must be a positive number.") from error
    if not math.isfinite(age_divisor) or age_divisor <= 0:
        raise ValueError("source.age_divisor must be a positive number.")
    grade_characteristic = str(
        source_spec.get("grade_characteristic") or ""
    ).strip().casefold()
    stage_characteristic = str(
        source_spec.get("stage_characteristic") or ""
    ).strip().casefold()
    sex_characteristic = str(
        source_spec.get("sex_characteristic") or ""
    ).strip().casefold()
    race_characteristic = str(
        source_spec.get("race_characteristic") or ""
    ).strip().casefold()
    stage_value_map = {
        str(key).strip().casefold(): str(value).strip()
        for key, value in (
            source_spec.get("stage_value_map") or {}
        ).items()
        if str(key).strip() and str(value).strip()
    }
    grade_value_map = {
        str(key).strip().casefold(): str(value).strip()
        for key, value in (
            source_spec.get("grade_value_map") or {}
        ).items()
        if str(key).strip() and str(value).strip()
    }
    sex_value_map = normalized_geo_categorical_value_map(
        source_spec.get("sex_value_map"),
        field="sex",
    )
    expression_sample_aliases = normalized_aliases(
        source_spec.get("expression_sample_aliases")
    )
    expression_sample_id_pattern = str(
        source_spec.get("expression_sample_id_pattern") or ""
    ).strip()
    expression_sample_id_replacement = str(
        source_spec.get("expression_sample_id_replacement") or ""
    )
    patient_rows = []
    sample_rows = []
    events = 0
    censored = 0
    excluded_missing_endpoint = 0
    excluded_nonpositive_time = 0
    for sample in selected_primary_samples:
        title = str(sample["title"])
        characteristics = sample["characteristics"]
        if time_start_characteristic:
            raw_start = clean(
                characteristics.get(time_start_characteristic)
            )
            raw_end = clean(
                characteristics.get(time_end_characteristic)
            )
            raw_time = derive_date_interval_days(raw_start, raw_end)
        else:
            raw_time = clean(characteristics.get(time_characteristic))
        raw_event = clean(characteristics.get(event_characteristic))
        event = map_geo_event(raw_event, event_value_map)
        if raw_time is None or event is None:
            excluded_missing_endpoint += 1
            continue
        try:
            time_value = float(raw_time)
        except ValueError:
            excluded_missing_endpoint += 1
            continue
        if time_value <= 0:
            excluded_nonpositive_time += 1
            continue
        events += event
        censored += 1 - event
        raw_stage = (
            clean(characteristics.get(stage_characteristic))
            if stage_characteristic
            else None
        )
        stage = (
            stage_value_map.get(raw_stage.casefold(), raw_stage)
            if raw_stage is not None
            else ""
        )
        raw_grade = (
            clean(characteristics.get(grade_characteristic))
            if grade_characteristic
            else None
        )
        grade = (
            grade_value_map.get(raw_grade.casefold(), raw_grade)
            if raw_grade is not None
            else ""
        )
        raw_sex = (
            clean(characteristics.get(sex_characteristic))
            if sex_characteristic
            else None
        )
        sex = (
            sex_value_map.get(raw_sex.casefold(), raw_sex)
            if raw_sex is not None
            else str(source_spec.get("sex_default") or "").strip()
        )
        patient_id = geo_sample_identifier(
            title,
            characteristics,
            patient_id_characteristic,
            label="patient",
            geo_accession=str(sample["geo_accession"]),
        )
        if expression_sample_metadata_field:
            expression_sample_id = geo_sample_metadata_identifier(
                sample,
                expression_sample_metadata_field,
                label="expression sample",
            )
        else:
            expression_sample_id = geo_sample_identifier(
                title,
                characteristics,
                expression_sample_characteristic,
                label="expression sample",
                geo_accession=str(sample["geo_accession"]),
            )
        expression_sample_id = normalize_geo_identifier(
            expression_sample_id,
            expression_sample_id_pattern,
            expression_sample_id_replacement,
            label="expression sample",
        )
        sample_id = expression_sample_aliases.get(
            expression_sample_id,
            expression_sample_id,
        )
        patient_rows.append(
            {
                "PATIENT_ID": patient_id,
                "GEO_ACCESSION": sample["geo_accession"],
                endpoint_time_column: format(time_value, ".17g"),
                endpoint_event_column: (
                    "1:EVENT" if event else "0:CENSORED"
                ),
                "STAGE": stage,
                "GRADE": grade,
                "SEX": sex,
                "RACE": (
                    clean(characteristics.get(race_characteristic))
                    if race_characteristic
                    else ""
                ),
                "AGE_AT_INDEX": normalized_geo_age(
                    characteristics.get(age_characteristic),
                    divisor=age_divisor,
                ) if age_characteristic else "",
                "GEO_SAMPLE_METADATA_JSON": canonical_json(sample),
            }
        )
        sample_rows.append(
            {
                "SAMPLE_ID": sample_id,
                "PATIENT_ID": patient_id,
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
    patient_ids = [row["PATIENT_ID"] for row in patient_rows]
    sample_ids = [row["SAMPLE_ID"] for row in sample_rows]
    if len(patient_ids) != len(set(patient_ids)):
        raise ValueError(
            "GEO endpoint-complete samples do not map one-to-one to patients."
        )
    if len(sample_ids) != len(set(sample_ids)):
        raise ValueError(
            "GEO endpoint-complete samples map to duplicate expression IDs."
        )
    expected_endpoint_complete = source_spec.get(
        "expected_endpoint_complete_samples"
    )
    if (
        expected_endpoint_complete is not None
        and len(patient_rows) != int(expected_endpoint_complete)
    ):
        raise ValueError(
            "GEO endpoint-complete sample count changed: "
            f"{len(patient_rows)} != {expected_endpoint_complete}."
        )
    expected_events = source_spec.get("expected_events")
    if expected_events is not None and events != int(expected_events):
        raise ValueError(
            f"GEO event count changed: {events} != {expected_events}."
        )
    expected_censored = source_spec.get("expected_censored")
    if expected_censored is not None and censored != int(expected_censored):
        raise ValueError(
            "GEO censored count changed: "
            f"{censored} != {expected_censored}."
        )

    source_expression_path = expression_path
    expression_layout = str(
        (source_spec.get("expression") or {}).get("layout")
        or "delimited_matrix"
    ).strip()
    expression_mapping_metadata: dict[str, Any] = {}
    gene_reference_spec = source_spec.get("gene_reference")
    gene_reference_path: Path | None = None
    gene_reference_consumed = False
    if expression_layout == "xlsx_matrix":
        from app.repository.adapters.pmc import (
            materialize_xlsx_expression_matrix,
        )

        expression_spec = source_spec.get("expression") or {}
        expression_path = source_dir / "geo_expression_selected.tsv"
        expression_mapping_metadata = (
            materialize_xlsx_expression_matrix(
                source_expression_path,
                expression_path,
                [row["SAMPLE_ID"] for row in sample_rows],
                sheet_name=str(
                    expression_spec.get("sheet_name") or ""
                ).strip(),
                header_row=int(
                    expression_spec.get("header_row") or 1
                ),
                feature_column=str(
                    expression_spec.get("feature_column") or ""
                ).strip(),
                sample_start_column=int(
                    expression_spec.get("sample_start_column") or 2
                ),
                feature_replacements=(
                    expression_spec.get("feature_replacements") or {}
                ),
                case_insensitive_samples=bool(
                    expression_spec.get("case_insensitive_samples")
                ),
                drop_all_missing_features=bool(
                    expression_spec.get("drop_all_missing_features")
                ),
                missing_value_tokens=[
                    str(value)
                    for value in (
                        expression_spec.get("missing_value_tokens") or []
                    )
                ],
                duplicate_feature_policy=str(
                    expression_spec.get("duplicate_feature_policy")
                    or "allow"
                ).strip(),
                duplicate_feature_case_insensitive=bool(
                    expression_spec.get(
                        "duplicate_feature_case_insensitive"
                    )
                ),
            )
        )
    elif expression_layout == "xlsx_gene_counts":
        expression_spec = source_spec.get("expression") or {}
        expression_path = source_dir / "geo_expression_log2_cpm.tsv"
        expression_mapping_metadata = (
            materialize_geo_xlsx_count_matrix(
                source_expression_path,
                expression_path,
                [row["SAMPLE_ID"] for row in sample_rows],
                sheet_name=str(
                    expression_spec.get("sheet_name") or ""
                ).strip(),
                header_row=int(
                    expression_spec.get("header_row") or 1
                ),
                feature_column=str(
                    expression_spec.get("feature_column") or ""
                ).strip(),
                feature_column_output=str(
                    expression_spec.get("feature_column_output") or ""
                ).strip(),
                sample_start_column=int(
                    expression_spec.get("sample_start_column") or 2
                ),
                feature_replacements=(
                    expression_spec.get("feature_replacements") or {}
                ),
                case_insensitive_samples=bool(
                    expression_spec.get("case_insensitive_samples")
                ),
                duplicate_feature_policy=str(
                    expression_spec.get("duplicate_feature_policy")
                    or "allow"
                ).strip(),
                duplicate_feature_case_insensitive=bool(
                    expression_spec.get(
                        "duplicate_feature_case_insensitive"
                    )
                ),
                count_value_type=str(
                    expression_spec.get("count_value_type") or "integer"
                ).strip(),
            )
        )
    elif expression_layout == "wide_gene_counts":
        expression_spec = source_spec.get("expression") or {}
        expression_path = source_dir / "geo_expression_log2_cpm.tsv"
        expression_mapping_metadata = materialize_geo_count_matrix(
            source_expression_path,
            expression_path,
            [row["SAMPLE_ID"] for row in sample_rows],
            feature_column=str(
                expression_spec.get("feature_column") or ""
            ).strip(),
            feature_column_index=(
                int(expression_spec["feature_column_index"])
                if expression_spec.get("feature_column_index") is not None
                else None
            ),
            feature_column_output=str(
                expression_spec.get("feature_column_output") or ""
            ).strip(),
            sample_start_column=int(
                expression_spec.get("sample_start_column") or 2
            ),
            feature_split_delimiter=str(
                expression_spec.get("feature_split_delimiter") or ""
            ),
            feature_part_indexes=[
                int(value)
                for value in (
                    expression_spec.get("feature_part_indexes") or []
                )
            ],
            expected_feature_parts=(
                int(expression_spec["expected_feature_parts"])
                if expression_spec.get("expected_feature_parts")
                is not None
                else None
            ),
            count_value_type=str(
                expression_spec.get("count_value_type") or "integer"
            ).strip(),
            drop_all_missing_features=bool(
                expression_spec.get("drop_all_missing_features")
            ),
            missing_value_tokens=[
                str(value)
                for value in (
                    expression_spec.get("missing_value_tokens") or []
                )
            ],
        )
    elif expression_layout == "wide_transcript_counts":
        expression_spec = source_spec.get("expression") or {}
        gene_reference_path = materialize_gene_reference(
            gene_reference_spec,
            source_dir,
        )
        if gene_reference_path is None or str(
            (gene_reference_spec or {}).get("format") or "ensembl_gtf"
        ).strip().casefold() != "ensembl_gtf":
            raise ValueError(
                "GEO transcript-count matrices require a pinned Ensembl "
                "GTF gene reference."
            )
        expression_path = (
            source_dir / "geo_expression_gene_log2_cpm.tsv"
        )
        expression_mapping_metadata = (
            materialize_geo_transcript_count_matrix(
                source_expression_path,
                expression_path,
                [row["SAMPLE_ID"] for row in sample_rows],
                gene_reference=gene_reference_path,
                feature_column=str(
                    expression_spec.get("feature_column") or ""
                ).strip(),
                feature_column_index=(
                    int(expression_spec["feature_column_index"])
                    if expression_spec.get("feature_column_index")
                    is not None
                    else None
                ),
                sample_start_column=int(
                    expression_spec.get("sample_start_column") or 2
                ),
                count_value_type=str(
                    expression_spec.get("count_value_type") or "integer"
                ).strip(),
                require_complete_reference=bool(
                    expression_spec.get("require_complete_reference")
                ),
            )
        )
        gene_reference_consumed = True
    elif expression_layout == "transcript_count_files_tar":
        expression_spec = source_spec.get("expression") or {}
        gene_reference_path = materialize_gene_reference(
            gene_reference_spec,
            source_dir,
        )
        if gene_reference_path is None or str(
            (gene_reference_spec or {}).get("format") or "ensembl_gtf"
        ).strip().casefold() != "ensembl_gtf":
            raise ValueError(
                "GEO transcript-count archives require a pinned Ensembl "
                "GTF gene reference."
            )
        supplementary_pattern_text = str(
            expression_spec.get("supplementary_file_pattern")
            or r".+_quant\.sf\.gz"
        ).strip()
        try:
            supplementary_pattern = re.compile(
                supplementary_pattern_text
            )
        except re.error as error:
            raise ValueError(
                "Invalid GEO transcript-count supplementary-file pattern."
            ) from error
        samples_by_accession = {
            str(sample["geo_accession"]): sample
            for sample in selected_primary_samples
        }
        selected_count_files = []
        for row in sample_rows:
            sample = samples_by_accession.get(row["GEO_ACCESSION"])
            if sample is None:
                raise ValueError(
                    "GEO endpoint sample is absent from the selected "
                    "sample metadata."
                )
            matching_urls = [
                str(url)
                for url in sample.get("supplementary_files", [])
                if supplementary_pattern.fullmatch(
                    PurePosixPath(
                        urllib.parse.urlparse(str(url)).path
                    ).name
                )
            ]
            if len(matching_urls) != 1:
                raise ValueError(
                    "Each GEO endpoint sample must resolve to exactly one "
                    "transcript-count supplementary file."
                )
            selected_count_files.append(
                {
                    "sample_id": row["SAMPLE_ID"],
                    "geo_accession": row["GEO_ACCESSION"],
                    "url": matching_urls[0],
                    "member_name": PurePosixPath(
                        urllib.parse.urlparse(matching_urls[0]).path
                    ).name,
                }
            )
        transcript_matrix_path = (
            source_dir / "geo_expression_transcript_counts.tsv"
        )
        archive_metadata = materialize_geo_transcript_count_files_tar(
            source_expression_path,
            transcript_matrix_path,
            selected_count_files,
            feature_column=str(
                expression_spec.get("feature_column") or "Name"
            ).strip(),
            count_column=str(
                expression_spec.get("count_column") or "NumReads"
            ).strip(),
            supplementary_file_pattern=supplementary_pattern,
        )
        expression_path = (
            source_dir / "geo_expression_gene_log2_cpm.tsv"
        )
        matrix_metadata = materialize_geo_transcript_count_matrix(
            transcript_matrix_path,
            expression_path,
            [row["SAMPLE_ID"] for row in sample_rows],
            gene_reference=gene_reference_path,
            feature_column=str(
                expression_spec.get("feature_column") or "Name"
            ).strip(),
            sample_start_column=2,
            count_value_type="nonnegative_numeric",
            require_complete_reference=bool(
                expression_spec.get("require_complete_reference")
            ),
        )
        transcript_matrix_path.unlink()
        expression_mapping_metadata = {
            **matrix_metadata,
            **archive_metadata,
            "source_expression_layout": (
                "transcript_count_files_tar"
            ),
        }
        gene_reference_consumed = True
    elif expression_layout == "wide_normalized_matrix":
        expression_spec = source_spec.get("expression") or {}
        expression_path = source_dir / "geo_expression_selected.tsv"
        expression_mapping_metadata = (
            materialize_geo_wide_normalized_matrix(
                source_expression_path,
                expression_path,
                [row["SAMPLE_ID"] for row in sample_rows],
                feature_column=str(
                    expression_spec.get("feature_column") or ""
                ).strip(),
                feature_column_index=(
                    int(expression_spec["feature_column_index"])
                    if expression_spec.get("feature_column_index")
                    is not None
                    else None
                ),
                feature_column_output=str(
                    expression_spec.get("feature_column_output") or ""
                ).strip(),
                sample_start_column=int(
                    expression_spec.get("sample_start_column") or 2
                ),
                header_missing_feature_column=bool(
                    expression_spec.get(
                        "header_missing_feature_column"
                    )
                ),
                header_missing_leading_column=bool(
                    expression_spec.get(
                        "header_missing_leading_column"
                    )
                ),
                value_transform=str(
                    expression_spec.get("value_transform") or "identity"
                ).strip(),
                duplicate_feature_policy=str(
                    expression_spec.get("duplicate_feature_policy")
                    or "error"
                ).strip(),
                duplicate_feature_case_insensitive=bool(
                    expression_spec.get(
                        "duplicate_feature_case_insensitive"
                    )
                ),
                drop_incomplete_features=bool(
                    expression_spec.get("drop_incomplete_features")
                ),
                missing_value_tokens=[
                    str(value)
                    for value in (
                        expression_spec.get("missing_value_tokens") or []
                    )
                ],
                allow_negative_values=bool(
                    expression_spec.get("allow_negative_values")
                ),
                source_sample_id_pattern=str(
                    expression_spec.get("source_sample_id_pattern") or ""
                ).strip(),
                source_sample_id_replacement=str(
                    expression_spec.get("source_sample_id_replacement") or ""
                ),
            )
        )
    elif expression_layout == "normalized_files_tar":
        expression_spec = source_spec.get("expression") or {}
        supplementary_pattern_text = str(
            expression_spec.get("supplementary_file_pattern")
            or r".+\.tsv\.gz"
        ).strip()
        try:
            supplementary_pattern = re.compile(
                supplementary_pattern_text
            )
        except re.error as error:
            raise ValueError(
                "Invalid GEO normalized-file supplementary pattern."
            ) from error
        samples_by_accession = {
            str(sample["geo_accession"]): sample
            for sample in selected_primary_samples
        }
        selected_normalized_files = []
        for row in sample_rows:
            sample = samples_by_accession.get(row["GEO_ACCESSION"])
            if sample is None:
                raise ValueError(
                    "GEO endpoint sample is absent from the selected "
                    "sample metadata."
                )
            matching_urls = [
                str(url)
                for url in sample.get("supplementary_files", [])
                if supplementary_pattern.fullmatch(
                    PurePosixPath(
                        urllib.parse.urlparse(str(url)).path
                    ).name
                )
            ]
            if len(matching_urls) != 1:
                raise ValueError(
                    "Each GEO endpoint sample must resolve to exactly one "
                    "normalized supplementary file."
                )
            selected_normalized_files.append(
                {
                    "sample_id": row["SAMPLE_ID"],
                    "geo_accession": row["GEO_ACCESSION"],
                    "url": matching_urls[0],
                    "member_name": PurePosixPath(
                        urllib.parse.urlparse(matching_urls[0]).path
                    ).name,
                }
            )
        expression_path = source_dir / "geo_expression_selected.tsv"
        expression_mapping_metadata = (
            materialize_geo_normalized_files_tar(
                source_expression_path,
                expression_path,
                selected_normalized_files,
                feature_column=str(
                    expression_spec.get("feature_column") or ""
                ).strip(),
                feature_column_output=str(
                    expression_spec.get("feature_column_output") or ""
                ).strip(),
                value_column_index=int(
                    expression_spec.get("value_column_index") or 2
                ),
                supplementary_file_pattern=supplementary_pattern,
                value_transform=str(
                    expression_spec.get("value_transform") or "identity"
                ).strip(),
                duplicate_feature_policy=str(
                    expression_spec.get("duplicate_feature_policy")
                    or "error"
                ).strip(),
                duplicate_feature_case_insensitive=bool(
                    expression_spec.get(
                        "duplicate_feature_case_insensitive"
                    )
                ),
                feature_order_policy=str(
                    expression_spec.get("feature_order_policy")
                    or "strict"
                ).strip(),
                require_nonnegative=bool(
                    expression_spec.get("require_nonnegative")
                ),
                require_value_header_matches_sample_id=bool(
                    expression_spec.get(
                        "require_value_header_matches_sample_id"
                    )
                ),
            )
        )
    elif expression_layout == "recount3_gene_sums":
        expression_spec = source_spec.get("expression") or {}
        (
            expression_support_paths,
            expression_support_urls,
        ) = materialize_geo_recount3_support(
            expression_spec,
            source_dir,
        )
        expression_path = (
            source_dir / "geo_expression_recount3_log2_scaled.tsv"
        )
        expression_mapping_metadata = (
            materialize_geo_recount3_matrix(
                source_expression_path,
                expression_path,
                [row["SAMPLE_ID"] for row in sample_rows],
                sample_metadata=expression_support_paths[
                    "recount3_sra_metadata"
                ],
                qc_metadata=expression_support_paths[
                    "recount3_qc_metadata"
                ],
                run_id_column=str(
                    expression_spec.get("run_id_column")
                    or "external_id"
                ).strip(),
                sample_id_column=str(
                    expression_spec.get("sample_id_column")
                    or "sample_title"
                ).strip(),
                auc_column=str(
                    expression_spec.get("auc_column")
                    or "bc_auc.all_reads_all_bases"
                ).strip(),
                target_size=float(
                    expression_spec.get("target_size") or 40_000_000
                ),
                expected_annotation=str(
                    expression_spec.get("expected_annotation") or ""
                ).strip(),
                expected_source_runs=(
                    int(expression_spec["expected_source_runs"])
                    if expression_spec.get("expected_source_runs")
                    is not None
                    else None
                ),
            )
        )
    elif expression_layout == "featurecounts_tar":
        expression_spec = source_spec.get("expression") or {}
        supplementary_pattern_text = str(
            expression_spec.get("supplementary_file_pattern")
            or r".+\.counts\.txt\.gz"
        ).strip()
        try:
            supplementary_pattern = re.compile(
                supplementary_pattern_text
            )
        except re.error as error:
            raise ValueError(
                "Invalid GEO featureCounts supplementary-file pattern."
            ) from error
        samples_by_accession = {
            str(sample["geo_accession"]): sample
            for sample in selected_primary_samples
        }
        selected_count_files = []
        for row in sample_rows:
            sample = samples_by_accession.get(row["GEO_ACCESSION"])
            if sample is None:
                raise ValueError(
                    "GEO endpoint sample is absent from the selected "
                    "sample metadata."
                )
            matching_urls = [
                str(url)
                for url in sample.get("supplementary_files", [])
                if supplementary_pattern.fullmatch(
                    PurePosixPath(
                        urllib.parse.urlparse(str(url)).path
                    ).name
                )
            ]
            if len(matching_urls) != 1:
                raise ValueError(
                    "Each GEO endpoint sample must resolve to exactly one "
                    "featureCounts supplementary file."
                )
            selected_count_files.append(
                {
                    "sample_id": row["SAMPLE_ID"],
                    "geo_accession": row["GEO_ACCESSION"],
                    "url": matching_urls[0],
                    "member_name": PurePosixPath(
                        urllib.parse.urlparse(matching_urls[0]).path
                    ).name,
                }
            )
        expression_path = source_dir / "geo_expression_log2_cpm.tsv"
        expression_mapping_metadata = (
            materialize_geo_featurecounts_tar(
                source_expression_path,
                expression_path,
                selected_count_files,
                feature_column=str(
                    expression_spec.get("feature_column") or "Geneid"
                ).strip(),
                feature_column_output=str(
                    expression_spec.get("feature_column_output")
                    or "Ensembl_Gene_Id"
                ).strip(),
                count_column_index=int(
                    expression_spec.get("count_column_index") or 7
                ),
                supplementary_file_pattern=supplementary_pattern,
            )
        )
    elif expression_layout != "delimited_matrix":
        raise ValueError(
            "Unsupported GEO expression layout: "
            f"{expression_layout!r}."
        )
    expected_source_expression_files = source_spec.get(
        "expected_source_expression_files"
    )
    observed_source_expression_files = expression_mapping_metadata.get(
        "source_expression_columns"
    )
    if (
        expected_source_expression_files is not None
        and observed_source_expression_files
        != int(expected_source_expression_files)
    ):
        raise ValueError(
            "GEO source expression-file count changed: "
            f"{observed_source_expression_files} != "
            f"{expected_source_expression_files}."
        )
    expected_dropped_features = source_spec.get(
        "expected_dropped_all_missing_features"
    )
    observed_dropped_features = expression_mapping_metadata.get(
        "source_expression_dropped_all_missing_features"
    )
    if (
        expected_dropped_features is not None
        and observed_dropped_features != int(expected_dropped_features)
    ):
        raise ValueError(
            "GEO all-missing expression feature count changed: "
            f"{observed_dropped_features} != "
            f"{expected_dropped_features}."
        )
    expected_dropped_incomplete = source_spec.get(
        "expected_dropped_incomplete_features"
    )
    observed_dropped_incomplete = expression_mapping_metadata.get(
        "source_expression_dropped_incomplete_features"
    )
    if (
        expected_dropped_incomplete is not None
        and observed_dropped_incomplete
        != int(expected_dropped_incomplete)
    ):
        raise ValueError(
            "GEO incomplete expression-feature count changed: "
            f"{observed_dropped_incomplete} != "
            f"{expected_dropped_incomplete}."
        )
    expected_feature_replacements = source_spec.get(
        "expected_feature_replacements"
    )
    observed_feature_replacements = expression_mapping_metadata.get(
        "source_expression_feature_replacements"
    )
    if (
        expected_feature_replacements is not None
        and observed_feature_replacements
        != int(expected_feature_replacements)
    ):
        raise ValueError(
            "GEO expression feature-replacement count changed: "
            f"{observed_feature_replacements} != "
            f"{expected_feature_replacements}."
        )
    expected_sample_id_normalizations = source_spec.get(
        "expected_source_sample_id_normalizations"
    )
    observed_sample_id_normalizations = expression_mapping_metadata.get(
        "source_expression_sample_id_normalizations"
    )
    if (
        expected_sample_id_normalizations is not None
        and observed_sample_id_normalizations
        != int(expected_sample_id_normalizations)
    ):
        raise ValueError(
            "GEO expression sample-ID normalization count changed: "
            f"{observed_sample_id_normalizations} != "
            f"{expected_sample_id_normalizations}."
        )
    expected_duplicate_features = source_spec.get(
        "expected_duplicate_feature_symbols"
    )
    observed_duplicate_features = expression_mapping_metadata.get(
        "source_expression_duplicate_feature_symbols"
    )
    if (
        expected_duplicate_features is not None
        and observed_duplicate_features
        != int(expected_duplicate_features)
    ):
        raise ValueError(
            "GEO duplicate expression-feature count changed: "
            f"{observed_duplicate_features} != "
            f"{expected_duplicate_features}."
        )
    expected_excluded_duplicate_rows = source_spec.get(
        "expected_excluded_duplicate_feature_rows"
    )
    observed_excluded_duplicate_rows = expression_mapping_metadata.get(
        "source_expression_excluded_duplicate_feature_rows"
    )
    if (
        expected_excluded_duplicate_rows is not None
        and observed_excluded_duplicate_rows
        != int(expected_excluded_duplicate_rows)
    ):
        raise ValueError(
            "GEO excluded duplicate expression-row count changed: "
            f"{observed_excluded_duplicate_rows} != "
            f"{expected_excluded_duplicate_rows}."
        )
    if gene_reference_path is None:
        gene_reference_path = materialize_gene_reference(
            gene_reference_spec,
            source_dir,
        )
    if gene_reference_path is not None and not gene_reference_consumed:
        mapped_expression_path = (
            source_dir / "geo_expression_mapped.tsv.gz"
        )
        reference_format = str(
            gene_reference_spec.get("format") or "ensembl_gtf"
        ).strip().casefold()
        if reference_format == "ensembl_gtf":
            mapping_summary = materialize_ensembl_expression(
                expression_path,
                mapped_expression_path,
                gene_reference_path,
                expression_sample_aliases=expression_sample_aliases,
                feature_id_pattern=str(
                    source_spec.get("expression_feature_id_pattern") or ""
                ).strip(),
            )
        elif reference_format == "ncbi_gene_info":
            mapping_summary = materialize_entrez_expression(
                expression_path,
                mapped_expression_path,
                gene_reference_path,
                expression_sample_aliases=expression_sample_aliases,
                feature_id_pattern=str(
                    source_spec.get("expression_feature_id_pattern") or ""
                ).strip(),
            )
        else:
            raise ValueError(
                "Unsupported GEO gene-reference format: "
                f"{reference_format!r}."
            )
        expression_mapping_metadata.update(mapping_summary)
        expression_mapping_metadata["geo_gene_reference_format"] = (
            reference_format
        )
        expression_path = mapped_expression_path
    elif gene_reference_path is not None:
        expression_mapping_metadata["geo_gene_reference_format"] = (
            "ensembl_gtf"
        )
    expected_gene_rows = source_spec.get(
        "expected_expression_gene_rows"
    )
    observed_gene_rows = expression_mapping_metadata.get(
        "source_expression_gene_rows"
    )
    if observed_gene_rows is None:
        observed_gene_rows = expression_mapping_metadata.get(
            "geo_source_expression_gene_rows"
        )
    if (
        expected_gene_rows is not None
        and observed_gene_rows != int(expected_gene_rows)
    ):
        raise ValueError(
            "GEO expression gene-row count changed: "
            f"{observed_gene_rows} != {expected_gene_rows}."
        )
    expected_transcript_rows = source_spec.get(
        "expected_expression_transcript_rows"
    )
    observed_transcript_rows = expression_mapping_metadata.get(
        "source_expression_transcript_rows"
    )
    if (
        expected_transcript_rows is not None
        and observed_transcript_rows != int(expected_transcript_rows)
    ):
        raise ValueError(
            "GEO expression transcript-row count changed: "
            f"{observed_transcript_rows} != {expected_transcript_rows}."
        )
    expected_normalized_gene_rows = source_spec.get(
        "expected_normalized_expression_gene_rows"
    )
    observed_normalized_gene_rows = expression_mapping_metadata.get(
        "normalized_expression_gene_rows"
    )
    if (
        expected_normalized_gene_rows is not None
        and observed_normalized_gene_rows
        != int(expected_normalized_gene_rows)
    ):
        raise ValueError(
            "GEO normalized expression gene-row count changed: "
            f"{observed_normalized_gene_rows} != "
            f"{expected_normalized_gene_rows}."
        )

    expression_samples = read_compressed_header(expression_path)[1:]
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
            endpoint_time_column,
            endpoint_event_column,
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
        "family_soft": fetch_url_metadata(soft_url),
        "license": fetch_url_metadata(license_url),
    }
    if expression_files is None:
        http_metadata["expression"] = fetch_url_metadata(expression_url)
    else:
        http_metadata["expression_files"] = {
            "count": expression_file_metadata[
                "geo_source_expression_file_count"
            ],
            "files": expression_file_metadata["files"],
        }
    if additional_soft_sources:
        http_metadata["additional_family_softs"] = [
            fetch_url_metadata(str(additional["url"]))
            for additional in additional_soft_sources
        ]
    if clinical_evidence_path is not None:
        http_metadata["curated_clinical_evidence"] = fetch_url_metadata(
            str(clinical_spec["evidence_url"])
        )
    if gene_reference_path is not None:
        http_metadata["gene_reference"] = fetch_url_metadata(
            str(source_spec["gene_reference"]["url"])
        )
    for role, url in sorted(expression_support_urls.items()):
        http_metadata[role] = fetch_url_metadata(url)
    metadata_path = source_dir / "geo_http_metadata.json"
    metadata_path.write_text(
        canonical_json(http_metadata) + "\n", encoding="utf-8"
    )
    series_path = source_dir / "geo_series_metadata.json"
    series_path.write_text(
        canonical_json(series) + "\n", encoding="utf-8"
    )
    additional_series_path: Path | None = None
    if additional_series:
        additional_series_path = (
            source_dir / "geo_additional_series_metadata.json"
        )
        additional_series_path.write_text(
            canonical_json(additional_series) + "\n",
            encoding="utf-8",
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
    for index, path in enumerate(additional_soft_paths, start=1):
        source_paths[f"geo_family_soft_additional_{index}"] = path
    if additional_series_path is not None:
        source_paths["geo_additional_series_metadata"] = (
            additional_series_path
        )
    if clinical_manifest_path is not None:
        source_paths["curated_clinical_manifest"] = (
            clinical_manifest_path
        )
    if clinical_evidence_path is not None:
        source_paths["curated_clinical_evidence"] = (
            clinical_evidence_path
        )
    if clinical_terms_path is not None:
        source_paths["clinical_terms"] = clinical_terms_path
    if expression_path != source_expression_path:
        source_paths["expression_original"] = source_expression_path
    if expression_file_manifest_path is not None:
        source_paths["geo_expression_file_manifest"] = (
            expression_file_manifest_path
        )
    if gene_reference_path is not None:
        source_paths["gene_reference"] = gene_reference_path
    source_paths.update(expression_support_paths)
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
            "geo_primary_family_samples": len(primary_soft_samples),
            "geo_additional_family_samples": (
                len(samples) - len(primary_soft_samples)
            ),
            "geo_additional_family_series": len(additional_series),
            "geo_additional_family_accessions": [
                additional["accession"]
                for additional in additional_soft_sources
            ],
            "geo_primary_samples": len(primary_samples),
            "geo_characteristic_eligible_samples": len(
                filtered_primary_samples
            ),
            "geo_patient_selected_samples": len(
                selected_primary_samples
            ),
            "geo_endpoint_complete_samples": len(patient_rows),
            "geo_events": events,
            "geo_censored": censored,
            "geo_excluded_missing_endpoint": excluded_missing_endpoint,
            "geo_excluded_nonpositive_time": excluded_nonpositive_time,
            "geo_expression_columns": len(expression_samples),
            "geo_expression_sha256": sha256_file(expression_path),
            "geo_source_expression_sha256": sha256_file(
                source_expression_path
            ),
            **{
                key: value
                for key, value in expression_file_metadata.items()
                if key != "files"
            },
            "geo_family_soft_sha256": sha256_file(soft_path),
            "geo_primary_sample_title_pattern": title_pattern.pattern,
            "geo_sample_characteristic_filters": characteristic_filters,
            "geo_characteristic_conflict_policy": (
                characteristic_conflict_policy
            ),
            "geo_characteristic_conflicts": sum(
                len(sample.get("characteristic_conflicts") or {})
                for sample in samples
            ),
            "geo_patient_id_characteristic": patient_id_characteristic,
            "geo_expression_sample_characteristic": (
                expression_sample_characteristic
            ),
            "geo_expression_sample_metadata_field": (
                expression_sample_metadata_field
            ),
            "geo_expression_sample_aliases": expression_sample_aliases,
            "geo_expression_sample_id_pattern": (
                expression_sample_id_pattern
            ),
            "geo_expression_sample_id_replacement": (
                expression_sample_id_replacement
            ),
            "geo_event_value_map": event_value_map,
            "geo_stage_value_map": stage_value_map,
            "geo_grade_value_map": grade_value_map,
            "geo_sex_value_map": sex_value_map,
            "geo_age_divisor": age_divisor,
            **patient_selection_metadata,
            **clinical_metadata,
            **expression_mapping_metadata,
        },
    )


def geo_source_filename(
    url: str,
    *,
    configured_name: Any = None,
    label: str,
) -> str:
    name = str(configured_name or "").strip()
    if not name:
        name = PurePosixPath(
            urllib.parse.unquote(urllib.parse.urlparse(url).path)
        ).name
    if (
        not name
        or name in {".", ".."}
        or PurePosixPath(name).name != name
        or "\\" in name
    ):
        raise ValueError(
            f"GEO {label} URL requires a safe source filename."
        )
    return name


def normalize_geo_characteristic_conflict_policy(
    value: Any,
) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(
            "source.characteristic_conflict_policy must be an object."
        )
    normalized: dict[str, str] = {}
    for raw_key, raw_policy in value.items():
        key = str(raw_key).strip().casefold()
        policy = str(raw_policy).strip().casefold()
        if not key or policy not in {"first", "last"}:
            raise ValueError(
                "GEO characteristic conflict policies require a non-empty "
                "key and either 'first' or 'last'."
            )
        normalized[key] = policy
    return normalized


def parse_geo_family_soft(
    path: Path,
    *,
    characteristic_conflict_policy: dict[str, str] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    conflict_policy = normalize_geo_characteristic_conflict_policy(
        characteristic_conflict_policy
    )
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

    with path.open("rb") as raw_handle:
        is_gzip = raw_handle.read(2) == b"\x1f\x8b"
    text_handle = (
        gzip.open(
            path,
            mode="rt",
            encoding="utf-8",
            errors="strict",
        )
        if is_gzip
        else path.open(
            mode="rt",
            encoding="utf-8",
            errors="strict",
        )
    )
    with text_handle as handle:
        for raw_line in handle:
            line = raw_line.rstrip("\r\n")
            if line.startswith("^SERIES = "):
                series["accession"] = line.split("=", 1)[1].strip()
                continue
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
                elif line.startswith("!Sample_source_name_ch1 = "):
                    current["source_name"] = line.split(
                        "=", 1
                    )[1].strip()
                elif line.startswith("!Sample_geo_accession = "):
                    current["geo_accession"] = line.split(
                        "=", 1
                    )[1].strip()
                elif line.startswith("!Sample_description = "):
                    current.setdefault("descriptions", []).append(
                        line.split("=", 1)[1].strip()
                    )
                elif re.match(
                    r"!Sample_supplementary_file(?:_[0-9]+)? = ",
                    line,
                ):
                    current.setdefault("supplementary_files", []).append(
                        line.split("=", 1)[1].strip()
                    )
                elif line.startswith("!Sample_characteristics_ch1 = "):
                    text = line.split("=", 1)[1].strip()
                    key, separator, value = text.partition(":")
                    if separator:
                        normalized_key = key.strip().casefold()
                        existing = current["characteristics"].get(
                            normalized_key
                        )
                        if existing is not None and existing != value.strip():
                            policy = conflict_policy.get(normalized_key)
                            if policy is None:
                                raise ValueError(
                                    "GEO sample contains conflicting "
                                    f"characteristic {normalized_key!r}."
                                )
                            conflicts = current.setdefault(
                                "characteristic_conflicts",
                                {},
                            )
                            observed_values = conflicts.setdefault(
                                normalized_key,
                                [existing],
                            )
                            if value.strip() not in observed_values:
                                observed_values.append(value.strip())
                            if policy == "first":
                                continue
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


def materialize_geo_additional_soft_sources(
    value: Any,
    source_dir: Path,
) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(
            "source.additional_soft_sources must be a list."
        )
    source_dir.mkdir(parents=True, exist_ok=True)
    materialized = []
    seen_accessions: set[str] = set()
    for index, raw_spec in enumerate(value, start=1):
        if not isinstance(raw_spec, dict):
            raise ValueError(
                "Each additional GEO family SOFT source must be an object."
            )
        accession = str(raw_spec.get("accession") or "").strip().upper()
        url = str(raw_spec.get("url") or "").strip()
        source_name = PurePosixPath(
            urllib.parse.urlparse(url).path
        ).name
        if (
            not re.fullmatch(r"GSE[0-9]+", accession)
            or accession in seen_accessions
            or not source_name
            or source_name in {".", ".."}
        ):
            raise ValueError(
                "Additional GEO family SOFT sources require unique GSE "
                "accessions and safe URLs."
            )
        path = source_dir / f"additional_{index}_{source_name}"
        download(url, path)
        verify_pinned_file(
            path,
            expected_size=raw_spec.get("size"),
            expected_sha256=raw_spec.get("sha256"),
            label=f"Additional GEO family SOFT {accession}",
        )
        series, samples = parse_geo_family_soft(
            path,
            characteristic_conflict_policy=(
                raw_spec.get("characteristic_conflict_policy")
            ),
        )
        parsed_accession = str(series.get("accession") or "").upper()
        if parsed_accession != accession:
            raise ValueError(
                "Additional GEO family SOFT accession changed: "
                f"{parsed_accession!r} != {accession!r}."
            )
        seen_accessions.add(accession)
        materialized.append(
            {
                "accession": accession,
                "url": url,
                "path": path,
                "series": series,
                "samples": samples,
            }
        )
    return materialized


def materialize_geo_curated_clinical_evidence(
    clinical_spec: dict[str, Any],
    source_dir: Path,
) -> tuple[dict[str, Any], Path]:
    evidence_url = str(
        clinical_spec.get("evidence_url") or ""
    ).strip()
    evidence_name = PurePosixPath(
        urllib.parse.urlparse(evidence_url).path
    ).name
    evidence_format = str(
        clinical_spec.get("evidence_format") or ""
    ).strip()
    evidence_pin_scope = str(
        clinical_spec.get("evidence_pin_scope") or "downloaded_file"
    ).strip()
    supported_formats = {
        "csv",
        "csv.gz",
        "geo_soft",
        "tsv",
        "tsv.gz",
        "xlsx",
        "zip_xlsx",
    }
    if (
        evidence_format not in supported_formats
        or evidence_pin_scope
        not in {"downloaded_file", "archive_member"}
        or (
            evidence_pin_scope == "archive_member"
            and evidence_format != "zip_xlsx"
        )
        or not evidence_name
        or evidence_name in {".", ".."}
    ):
        raise ValueError(
            "GEO generated clinical records require pinned GEO SOFT, XLSX, "
            "ZIP/XLSX, CSV or TSV evidence."
        )
    source_dir.mkdir(parents=True, exist_ok=True)
    evidence_path = source_dir / evidence_name
    download_mode = str(
        clinical_spec.get("download_mode") or "standard"
    ).strip().casefold()
    if download_mode not in {"standard", "pmc_pow"}:
        raise ValueError(
            "GEO curated clinical download_mode must be 'standard' or "
            "'pmc_pow'."
        )
    if download_mode == "pmc_pow":
        from app.repository.adapters.pmc import (
            download_publication_source,
        )

        download_publication_source(
            evidence_url,
            evidence_path,
            mode=download_mode,
        )
    else:
        download(evidence_url, evidence_path)
    observed_container_size = evidence_path.stat().st_size
    if evidence_pin_scope == "downloaded_file":
        verify_pinned_file(
            evidence_path,
            expected_size=clinical_spec.get("evidence_size"),
            expected_sha256=clinical_spec.get("evidence_sha256"),
            label="GEO curated clinical evidence",
        )
    else:
        try:
            expected_container_size = int(
                clinical_spec.get("evidence_container_size")
            )
        except (TypeError, ValueError) as error:
            raise ValueError(
                "Archive-member clinical evidence requires a positive "
                "evidence_container_size."
            ) from error
        if (
            expected_container_size <= 0
            or observed_container_size != expected_container_size
        ):
            raise ValueError(
                "GEO curated clinical evidence container changed size."
            )
    header_row = int(clinical_spec.get("header_row") or 1)
    clinical_table_path = evidence_path
    if evidence_format == "zip_xlsx":
        archive_member = str(
            clinical_spec.get("archive_member") or ""
        ).strip()
        member_path = PurePosixPath(archive_member)
        if (
            not archive_member
            or member_path.is_absolute()
            or ".." in member_path.parts
            or member_path.suffix.casefold() != ".xlsx"
        ):
            raise ValueError(
                "GEO ZIP/XLSX clinical evidence requires a safe XLSX "
                "archive_member."
            )
        with zipfile.ZipFile(evidence_path) as archive:
            try:
                member_info = archive.getinfo(archive_member)
            except KeyError as error:
                raise ValueError(
                    "GEO ZIP/XLSX clinical archive member was not found."
                ) from error
            if member_info.is_dir():
                raise ValueError(
                    "GEO ZIP/XLSX clinical archive member is a directory."
                )
            clinical_table_path = (
                source_dir / f"clinical_{member_path.name}"
            )
            with (
                archive.open(member_info) as source,
                clinical_table_path.open("wb") as target,
            ):
                shutil.copyfileobj(source, target)
        if evidence_pin_scope == "archive_member":
            verify_pinned_file(
                clinical_table_path,
                expected_size=clinical_spec.get("evidence_size"),
                expected_sha256=clinical_spec.get("evidence_sha256"),
                label="GEO curated clinical archive member",
            )
            evidence_path.unlink()
    if evidence_format == "geo_soft":
        _, clinical_samples = parse_geo_family_soft(evidence_path)
        records = [
            {
                "sample_title": str(sample["title"]),
                "geo_accession": str(sample["geo_accession"]),
                **{
                    str(key): str(value)
                    for key, value in (
                        sample.get("characteristics") or {}
                    ).items()
                },
            }
            for sample in clinical_samples
        ]
    elif evidence_format in {"xlsx", "zip_xlsx"}:
        from app.repository.adapters.pmc import read_xlsx_sheet

        records = read_xlsx_sheet(
            clinical_table_path,
            sheet_name=str(
                clinical_spec.get("sheet_name") or ""
            ).strip()
            or None,
            header_row=header_row,
            header_name_overrides={
                int(index): str(name)
                for index, name in (
                    clinical_spec.get("header_name_overrides") or {}
                ).items()
            },
        )
    else:
        records = read_geo_delimited_clinical_evidence(
            evidence_path,
            delimiter="\t" if evidence_format.startswith("tsv") else ",",
            compressed=evidence_format.endswith(".gz"),
            header_row=header_row,
        )
    record_id_column = str(
        clinical_spec.get("record_id_column") or ""
    ).strip()
    sample_id_pattern = str(
        clinical_spec.get("sample_id_pattern") or ""
    ).strip()
    try:
        compiled_pattern = re.compile(sample_id_pattern)
    except re.error as error:
        raise ValueError(
            "Invalid GEO curated-clinical sample-ID pattern."
        ) from error
    if compiled_pattern.groups != 1:
        raise ValueError(
            "GEO curated-clinical sample-ID pattern requires exactly one "
            "capturing group."
        )
    selected_records = [
        record
        for record in records
        if compiled_pattern.fullmatch(
            str(record.get(record_id_column) or "").strip()
        )
        is not None
    ]
    (
        selected_records,
        derived_field_summary,
    ) = derive_geo_curated_clinical_fields(
        selected_records,
        clinical_spec.get("derived_fields"),
    )
    resolved_spec = dict(clinical_spec)
    resolved_spec["download_mode"] = download_mode
    resolved_spec["evidence_pin_scope"] = evidence_pin_scope
    resolved_spec["evidence_container_size"] = observed_container_size
    resolved_spec["records"] = selected_records
    resolved_spec["derived_field_summary"] = derived_field_summary
    return (
        resolved_spec,
        (
            clinical_table_path
            if evidence_pin_scope == "archive_member"
            else evidence_path
        ),
    )


def read_geo_delimited_clinical_evidence(
    path: Path,
    *,
    delimiter: str,
    compressed: bool,
    header_row: int,
) -> list[dict[str, str]]:
    if delimiter not in {",", "\t"}:
        raise ValueError("Unsupported GEO clinical-evidence delimiter.")
    if header_row < 1:
        raise ValueError("GEO clinical-evidence header_row must be positive.")
    open_text = gzip.open if compressed else Path.open
    with open_text(
        path,
        mode="rt",
        newline="",
        encoding="utf-8-sig",
        errors="strict",
    ) as handle:
        for _ in range(header_row - 1):
            if next(handle, None) is None:
                raise ValueError(
                    "GEO clinical-evidence header row is outside the file."
                )
        reader = csv.DictReader(handle, delimiter=delimiter)
        fieldnames = [
            str(value or "").strip()
            for value in (reader.fieldnames or [])
        ]
        if (
            not fieldnames
            or any(not value for value in fieldnames)
            or len(fieldnames) != len(set(fieldnames))
        ):
            raise ValueError(
                "GEO clinical evidence has missing or duplicate columns."
            )
        reader.fieldnames = fieldnames
        records: list[dict[str, str]] = []
        for raw_record in reader:
            if None in raw_record:
                raise ValueError(
                    "GEO clinical evidence contains an overlong row."
                )
            record = {
                field: str(raw_record.get(field) or "").strip()
                for field in fieldnames
            }
            if any(record.values()):
                records.append(record)
    if not records:
        raise ValueError("GEO clinical evidence contains no data records.")
    return records


def derive_geo_curated_clinical_fields(
    records: list[dict[str, str]],
    raw_rules: Any,
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    if raw_rules is None:
        return records, {}
    if not isinstance(raw_rules, list) or not all(
        isinstance(rule, dict) for rule in raw_rules
    ):
        raise ValueError(
            "GEO curated clinical derived_fields must be a list of objects."
        )

    summaries: dict[str, Any] = {}
    for rule in raw_rules:
        operation = str(rule.get("operation") or "").strip()
        target = str(rule.get("target") or "").strip()
        if not target:
            raise ValueError(
                "GEO curated clinical derived fields require a target."
            )
        if any(target in record for record in records):
            raise ValueError(
                f"GEO derived clinical target {target!r} already exists."
            )

        if operation == "numeric_difference_scaled":
            start_field = str(
                rule.get("start_field") or ""
            ).strip()
            end_field = str(rule.get("end_field") or "").strip()
            try:
                scale = float(rule.get("scale"))
            except (TypeError, ValueError) as error:
                raise ValueError(
                    "GEO numeric_difference_scaled rules require a "
                    "positive finite scale."
                ) from error
            available_fields = {
                field
                for record in records
                for field in record
            }
            if (
                not start_field
                or not end_field
                or start_field not in available_fields
                or end_field not in available_fields
                or not math.isfinite(scale)
                or scale <= 0
            ):
                raise ValueError(
                    "GEO numeric_difference_scaled rules require existing "
                    "start/end fields and a positive finite scale."
                )
            require_positive = bool(rule.get("require_positive"))
            derived_records = 0
            unresolved_records = 0
            for record in records:
                try:
                    start = float(
                        str(record.get(start_field) or "").strip()
                    )
                    end = float(
                        str(record.get(end_field) or "").strip()
                    )
                except (TypeError, ValueError):
                    start = math.nan
                    end = math.nan
                derived = (end - start) * scale
                if (
                    not math.isfinite(start)
                    or not math.isfinite(end)
                    or not math.isfinite(derived)
                    or (require_positive and derived <= 0)
                ):
                    record[target] = ""
                    unresolved_records += 1
                else:
                    record[target] = format(derived, ".17g")
                    derived_records += 1
            summaries[target] = {
                "operation": operation,
                "records": len(records),
                "derived_records": derived_records,
                "unresolved_records": unresolved_records,
                "start_field": start_field,
                "end_field": end_field,
                "scale": scale,
                "require_positive": require_positive,
            }
            continue

        if operation == "event_time_or_censor_time":
            status_target = str(
                rule.get("status_target") or ""
            ).strip()
            event_time_field = str(
                rule.get("event_time_field") or ""
            ).strip()
            censor_time_field = str(
                rule.get("censor_time_field") or ""
            ).strip()
            event_value = str(
                rule.get("event_value") or "Event"
            ).strip()
            censor_value = str(
                rule.get("censor_value") or "Censored"
            ).strip()
            available_fields = {
                field
                for record in records
                for field in record
            }
            if (
                not status_target
                or status_target == target
                or event_time_field not in available_fields
                or censor_time_field not in available_fields
                or not event_value
                or not censor_value
                or event_value.casefold() == censor_value.casefold()
                or any(status_target in record for record in records)
            ):
                raise ValueError(
                    "GEO event_time_or_censor_time rules require distinct "
                    "time/status targets, existing event/censor time "
                    "fields and distinct status labels."
                )
            event_records = 0
            censor_records = 0
            unresolved_records = 0
            for record in records:
                try:
                    event_time = float(
                        str(
                            record.get(event_time_field) or ""
                        ).strip()
                    )
                except (TypeError, ValueError):
                    event_time = math.nan
                try:
                    censor_time = float(
                        str(
                            record.get(censor_time_field) or ""
                        ).strip()
                    )
                except (TypeError, ValueError):
                    censor_time = math.nan
                if math.isfinite(event_time) and event_time > 0:
                    record[target] = format(event_time, ".17g")
                    record[status_target] = event_value
                    event_records += 1
                elif math.isfinite(censor_time) and censor_time > 0:
                    record[target] = format(censor_time, ".17g")
                    record[status_target] = censor_value
                    censor_records += 1
                else:
                    record[target] = ""
                    record[status_target] = ""
                    unresolved_records += 1
            summaries[target] = {
                "operation": operation,
                "records": len(records),
                "event_records": event_records,
                "censor_records": censor_records,
                "unresolved_records": unresolved_records,
                "status_target": status_target,
                "event_time_field": event_time_field,
                "censor_time_field": censor_time_field,
                "event_value": event_value,
                "censor_value": censor_value,
            }
            continue

        status_field = str(rule.get("status_field") or "").strip()
        event_time_field = str(
            rule.get("event_time_field") or ""
        ).strip()
        censor_start_field = str(
            rule.get("censor_start_date_field") or ""
        ).strip()
        censor_end_field = str(
            rule.get("censor_end_date_field") or ""
        ).strip()
        offset_field = str(
            rule.get("censor_start_offset_days_field") or ""
        ).strip()
        date_format = str(
            rule.get("date_format") or "%Y-%m-%d"
        ).strip()
        event_values = {
            str(value).strip().casefold()
            for value in (rule.get("event_values") or [])
            if str(value).strip()
        }
        censor_values = {
            str(value).strip().casefold()
            for value in (rule.get("censor_values") or [])
            if str(value).strip()
        }
        if (
            operation != "event_time_or_censor_interval"
            or not target
            or not status_field
            or not event_time_field
            or not censor_start_field
            or not censor_end_field
            or not date_format
            or not event_values
            or not censor_values
            or event_values & censor_values
        ):
            raise ValueError(
                "GEO event_time_or_censor_interval rules require a "
                "target, explicit event/censor labels, a direct event-time "
                "field and censoring date fields."
            )
        direct_event_records = 0
        date_derived_censor_records = 0
        unresolved_records = 0
        for record in records:
            status = clean(record.get(status_field))
            status_key = status.casefold() if status is not None else ""
            derived: float | int | None = None
            if status_key in event_values:
                try:
                    event_time = float(
                        str(record.get(event_time_field) or "").strip()
                    )
                except ValueError:
                    event_time = math.nan
                if math.isfinite(event_time) and event_time > 0:
                    derived = event_time
                    direct_event_records += 1
            elif status_key in censor_values:
                try:
                    start = datetime.strptime(
                        str(record.get(censor_start_field) or "").strip(),
                        date_format,
                    ).date()
                    end = datetime.strptime(
                        str(record.get(censor_end_field) or "").strip(),
                        date_format,
                    ).date()
                    offset = (
                        float(str(record.get(offset_field) or "").strip())
                        if offset_field
                        else 0.0
                    )
                except (TypeError, ValueError):
                    start = None
                    end = None
                    offset = math.nan
                if (
                    start is not None
                    and end is not None
                    and math.isfinite(offset)
                    and offset.is_integer()
                ):
                    censor_time = (
                        end - (start + timedelta(days=int(offset)))
                    ).days
                    if censor_time > 0:
                        derived = censor_time
                        date_derived_censor_records += 1
            if derived is None:
                record[target] = ""
                unresolved_records += 1
            else:
                record[target] = format(derived, ".17g")

        summaries[target] = {
            "operation": operation,
            "records": len(records),
            "direct_event_records": direct_event_records,
            "date_derived_censor_records": (
                date_derived_censor_records
            ),
            "unresolved_records": unresolved_records,
            "date_format": date_format,
            "censor_start_offset_days_field": offset_field or None,
        }
    return records, summaries


def attach_geo_curated_clinical_records(
    samples: list[dict[str, Any]],
    clinical_spec: Any,
) -> dict[str, Any]:
    if not isinstance(clinical_spec, dict):
        raise ValueError("GEO clinical configuration must be an object.")
    records = clinical_spec.get("records")
    record_id_column = str(
        clinical_spec.get("record_id_column") or ""
    ).strip()
    sample_metadata_field = str(
        clinical_spec.get("sample_metadata_field") or ""
    ).strip()
    sample_id_pattern = str(
        clinical_spec.get("sample_id_pattern") or ""
    ).strip()
    sample_id_replacement_configured = (
        "sample_id_replacement" in clinical_spec
    )
    sample_id_replacement = str(
        clinical_spec.get("sample_id_replacement") or ""
    )
    evidence_url = str(
        clinical_spec.get("evidence_url") or ""
    ).strip()
    evidence_sha256 = str(
        clinical_spec.get("evidence_sha256") or ""
    ).strip().lower()
    raw_field_name_map = clinical_spec.get("field_name_map") or {}
    if not isinstance(raw_field_name_map, dict):
        raise ValueError(
            "GEO curated clinical field_name_map must be an object."
        )
    field_name_map = {
        str(source).strip(): str(target).strip().casefold()
        for source, target in raw_field_name_map.items()
        if str(source).strip() and str(target).strip()
    }
    if len(field_name_map) != len(raw_field_name_map):
        raise ValueError(
            "GEO curated clinical field_name_map contains empty names."
        )
    allow_unmatched_records = bool(
        clinical_spec.get("allow_unmatched_records")
    )
    try:
        evidence_size = int(clinical_spec.get("evidence_size"))
    except (TypeError, ValueError) as error:
        raise ValueError(
            "GEO curated clinical evidence requires a positive size."
        ) from error
    if (
        not isinstance(records, list)
        or not records
        or not all(isinstance(record, dict) for record in records)
        or not record_id_column
        or not sample_metadata_field
        or not sample_id_pattern
        or not evidence_url
        or evidence_size <= 0
        or not re.fullmatch(r"[0-9a-f]{64}", evidence_sha256)
    ):
        raise ValueError(
            "GEO curated clinical records require records, an ID column, "
            "a sample metadata field and pattern, plus pinned source "
            "evidence."
        )
    try:
        compiled_pattern = re.compile(sample_id_pattern)
    except re.error as error:
        raise ValueError(
            "Invalid GEO curated-clinical sample-ID pattern."
        ) from error
    if compiled_pattern.groups != 1:
        raise ValueError(
            "GEO curated-clinical sample-ID pattern requires exactly one "
            "capturing group."
        )

    def linked_record_id(value: str) -> str | None:
        match = compiled_pattern.fullmatch(value)
        if match is None:
            return None
        linked_id = (
            match.expand(sample_id_replacement)
            if sample_id_replacement_configured
            else match.group(1)
        ).strip()
        if not linked_id:
            raise ValueError(
                "GEO curated-clinical sample-ID normalization produced "
                "an empty linkage key."
            )
        return linked_id

    records_by_id: dict[str, dict[str, Any]] = {}
    for record in records:
        record_id = clean(record.get(record_id_column))
        if record_id is None:
            raise ValueError(
                "GEO curated clinical record is missing its configured ID."
            )
        linked_id = (
            linked_record_id(record_id)
            if sample_id_replacement_configured
            else record_id
        )
        if linked_id is None:
            raise ValueError(
                f"GEO curated clinical record ID {record_id!r} does not "
                "match its configured sample-ID pattern."
            )
        if linked_id in records_by_id:
            raise ValueError(
                "GEO curated clinical record linkage key "
                f"{linked_id!r} is duplicated."
            )
        records_by_id[linked_id] = record
    expected_records = clinical_spec.get("expected_records")
    if (
        expected_records is not None
        and len(records_by_id) != int(expected_records)
    ):
        raise ValueError(
            "GEO curated clinical record count changed: "
            f"{len(records_by_id)} != {expected_records}."
        )

    matched_record_ids: set[str] = set()
    for sample in samples:
        metadata_values = geo_sample_metadata_values(
            sample,
            sample_metadata_field,
        )
        matched_ids = {
            linked_id
            for value in metadata_values
            if (linked_id := linked_record_id(value)) is not None
        }
        if len(matched_ids) > 1:
            raise ValueError(
                "GEO sample metadata maps one sample to multiple curated "
                "clinical IDs."
            )
        if not matched_ids:
            continue
        record_id = next(iter(matched_ids))
        record = records_by_id.get(record_id)
        if record is None:
            continue
        if record_id in matched_record_ids:
            raise ValueError(
                f"GEO curated clinical record {record_id!r} maps to "
                "multiple samples."
            )
        matched_record_ids.add(record_id)
        sample["curated_clinical_record"] = record
        for raw_key, raw_value in record.items():
            if raw_value is None:
                continue
            source_key = str(raw_key).strip()
            key = field_name_map.get(
                source_key,
                source_key.casefold(),
            )
            if not key:
                raise ValueError(
                    "GEO curated clinical record contains an empty field."
                )
            existing = sample["characteristics"].get(key)
            if (
                existing is not None
                and str(existing).strip() != str(raw_value).strip()
            ):
                raise ValueError(
                    "GEO curated clinical field conflicts with GEO sample "
                    f"metadata for {key!r}."
                )
            sample["characteristics"][key] = raw_value
    missing_record_ids = sorted(
        set(records_by_id) - matched_record_ids
    )
    if missing_record_ids and not allow_unmatched_records:
        raise ValueError(
            "GEO curated clinical records are absent from the configured "
            f"sample metadata: {missing_record_ids[:5]}"
        )
    expected_matched_records = clinical_spec.get(
        "expected_matched_records"
    )
    if (
        expected_matched_records is not None
        and len(matched_record_ids) != int(expected_matched_records)
    ):
        raise ValueError(
            "GEO curated clinical matched-record count changed: "
            f"{len(matched_record_ids)} != {expected_matched_records}."
        )
    expected_unmatched_records = clinical_spec.get(
        "expected_unmatched_records"
    )
    if (
        expected_unmatched_records is not None
        and len(missing_record_ids) != int(expected_unmatched_records)
    ):
        raise ValueError(
            "GEO curated clinical unmatched-record count changed: "
            f"{len(missing_record_ids)} != {expected_unmatched_records}."
        )
    records_sha256 = hashlib.sha256(
        canonical_json(records).encode("utf-8")
    ).hexdigest()
    return {
        "geo_curated_clinical_records": len(records_by_id),
        "geo_curated_clinical_records_matched": len(matched_record_ids),
        "geo_curated_clinical_records_unmatched": len(
            missing_record_ids
        ),
        "geo_curated_clinical_allow_unmatched_records": (
            allow_unmatched_records
        ),
        "geo_curated_clinical_record_id_column": record_id_column,
        "geo_curated_clinical_sample_metadata_field": (
            sample_metadata_field
        ),
        "geo_curated_clinical_sample_id_pattern": sample_id_pattern,
        "geo_curated_clinical_sample_id_replacement": (
            sample_id_replacement
            if sample_id_replacement_configured
            else None
        ),
        "geo_curated_clinical_field_name_map": field_name_map,
        "geo_curated_clinical_derived_fields": (
            clinical_spec.get("derived_fields") or []
        ),
        "geo_curated_clinical_derived_field_summary": (
            clinical_spec.get("derived_field_summary") or {}
        ),
        "geo_curated_clinical_records_sha256": records_sha256,
        "geo_curated_clinical_evidence_url": evidence_url,
        "geo_curated_clinical_evidence_size": evidence_size,
        "geo_curated_clinical_evidence_sha256": evidence_sha256,
        "geo_curated_clinical_download_mode": (
            clinical_spec.get("download_mode") or "standard"
        ),
    }


def geo_sample_metadata_values(
    sample: dict[str, Any],
    field: str,
) -> list[str]:
    normalized = field.strip().casefold()
    if normalized == "title":
        values = [sample.get("title")]
    elif normalized == "source_name":
        values = [sample.get("source_name")]
    elif normalized == "geo_accession":
        values = [sample.get("geo_accession")]
    elif normalized in {"description", "descriptions"}:
        values = sample.get("descriptions") or []
    elif normalized in {
        "supplementary_file",
        "supplementary_files",
    }:
        values = sample.get("supplementary_files") or []
    elif normalized.startswith("characteristic:"):
        key = normalized.split(":", 1)[1].strip()
        values = [sample.get("characteristics", {}).get(key)]
    else:
        raise ValueError(
            "GEO curated-clinical sample_metadata_field must be title, "
            "source_name, geo_accession, description, supplementary_file "
            "or characteristic:<key>."
        )
    return [
        str(value).strip()
        for value in values
        if value is not None and str(value).strip()
    ]


def sample_passes_characteristic_filters(
    characteristics: dict[str, Any],
    filters: Any,
) -> bool:
    if not isinstance(filters, list):
        raise ValueError(
            "source.sample_characteristic_filters must be a list."
        )
    for rule in filters:
        if not isinstance(rule, dict) or not str(
            rule.get("key") or ""
        ).strip():
            raise ValueError(
                "Each GEO characteristic filter requires a key."
            )
        key = str(rule["key"]).strip().casefold()
        value = clean(characteristics.get(key))
        normalized = value.casefold() if value is not None else None
        included = {
            str(item).strip().casefold()
            for item in rule.get("include") or []
        }
        excluded = {
            str(item).strip().casefold()
            for item in rule.get("exclude") or []
        }
        minimum_numeric = rule.get("minimum_numeric")
        maximum_numeric = rule.get("maximum_numeric")
        has_numeric_bound = (
            minimum_numeric is not None or maximum_numeric is not None
        )
        if included and normalized not in included:
            return False
        if excluded and normalized in excluded:
            return False
        if bool(rule.get("required")) and value is None:
            return False
        if has_numeric_bound:
            if value is None:
                return False
            try:
                numeric_value = float(value)
                minimum = (
                    float(minimum_numeric)
                    if minimum_numeric is not None
                    else None
                )
                maximum = (
                    float(maximum_numeric)
                    if maximum_numeric is not None
                    else None
                )
            except (TypeError, ValueError) as error:
                raise ValueError(
                    f"GEO characteristic {key!r} requires numeric values."
                ) from error
            if (
                not math.isfinite(numeric_value)
                or (minimum is not None and not math.isfinite(minimum))
                or (maximum is not None and not math.isfinite(maximum))
                or (
                    minimum is not None
                    and maximum is not None
                    and minimum > maximum
                )
            ):
                raise ValueError(
                    f"GEO characteristic filter {key!r} has invalid "
                    "numeric bounds or values."
                )
            if minimum is not None and numeric_value < minimum:
                return False
            if maximum is not None and numeric_value > maximum:
                return False
    return True


def select_geo_patient_samples(
    samples: list[dict[str, Any]],
    *,
    patient_id_characteristic: str,
    selection_spec: Any,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if selection_spec is None:
        return list(samples), {}
    if (
        not isinstance(selection_spec, dict)
        or not patient_id_characteristic
    ):
        raise ValueError(
            "GEO patient-sample selection requires an object and an "
            "explicit patient_id_characteristic."
        )
    rank_by = selection_spec.get("rank_by")
    equal_characteristics = selection_spec.get(
        "require_equal_characteristics"
    ) or []
    if (
        not isinstance(rank_by, list)
        or not rank_by
        or not isinstance(equal_characteristics, list)
    ):
        raise ValueError(
            "GEO patient-sample selection requires rank_by and an "
            "optional require_equal_characteristics list."
        )

    normalized_rank_by: list[dict[str, Any]] = []
    for rule in rank_by:
        if not isinstance(rule, dict):
            raise ValueError(
                "Each GEO patient-sample rank rule must be an object."
            )
        key = str(rule.get("key") or "").strip().casefold()
        value_type = str(rule.get("type") or "").strip().casefold()
        order = str(rule.get("order") or "").strip().casefold()
        if (
            not key
            or value_type not in {"numeric", "text"}
            or order not in {"asc", "desc"}
        ):
            raise ValueError(
                "Each GEO patient-sample rank rule requires a key, "
                "numeric/text type and asc/desc order."
            )
        normalized_rank_by.append(
            {"key": key, "type": value_type, "order": order}
        )
    normalized_equal_characteristics = [
        str(key).strip().casefold()
        for key in equal_characteristics
        if str(key).strip()
    ]
    if len(normalized_equal_characteristics) != len(
        equal_characteristics
    ):
        raise ValueError(
            "GEO patient-sample invariant characteristics cannot be empty."
        )

    groups: dict[str, list[dict[str, Any]]] = {}
    for sample in samples:
        patient_id = geo_sample_identifier(
            str(sample.get("title") or ""),
            sample.get("characteristics") or {},
            patient_id_characteristic,
            label="patient",
        )
        groups.setdefault(patient_id, []).append(sample)

    selected: list[dict[str, Any]] = []
    duplicate_groups = 0
    for patient_id, patient_samples in sorted(groups.items()):
        if len(patient_samples) > 1:
            duplicate_groups += 1
        for key in normalized_equal_characteristics:
            values = {
                clean(sample["characteristics"].get(key))
                for sample in patient_samples
            }
            if len(values) > 1:
                raise ValueError(
                    f"GEO patient {patient_id!r} has conflicting {key!r} "
                    "values across eligible samples."
                )

        ranked = sorted(patient_samples, key=geo_sample_sort_key)
        for rule in reversed(normalized_rank_by):
            ranked.sort(
                key=lambda sample, current_rule=rule: (
                    geo_patient_sample_rank_value(
                        sample,
                        current_rule,
                    )
                ),
                reverse=rule["order"] == "desc",
            )
        selected.append(ranked[0])

    selected.sort(key=geo_sample_sort_key)
    removed_samples = len(samples) - len(selected)
    expected_selected = selection_spec.get("expected_selected_samples")
    expected_duplicate_groups = selection_spec.get(
        "expected_duplicate_patient_groups"
    )
    expected_removed = selection_spec.get("expected_removed_samples")
    expectations = (
        (
            "selected sample",
            len(selected),
            expected_selected,
        ),
        (
            "duplicate-patient group",
            duplicate_groups,
            expected_duplicate_groups,
        ),
        (
            "duplicate sample removal",
            removed_samples,
            expected_removed,
        ),
    )
    for label, observed, expected in expectations:
        if expected is not None and observed != int(expected):
            raise ValueError(
                f"GEO patient-sample {label} count changed: "
                f"{observed} != {expected}."
            )
    return selected, {
        "geo_patient_sample_selection_strategy": (
            "prespecified_characteristic_rank"
        ),
        "geo_patient_sample_selection_rank_by": normalized_rank_by,
        "geo_patient_sample_selection_equal_characteristics": (
            normalized_equal_characteristics
        ),
        "geo_patient_groups_before_endpoint_qc": len(groups),
        "geo_duplicate_patient_groups": duplicate_groups,
        "geo_duplicate_samples_removed": removed_samples,
    }


def geo_patient_sample_rank_value(
    sample: dict[str, Any],
    rule: dict[str, Any],
) -> float | str:
    key = rule["key"]
    value = clean(sample.get("characteristics", {}).get(key))
    if value is None:
        raise ValueError(
            f"GEO patient-sample rank characteristic {key!r} is missing."
        )
    if rule["type"] == "text":
        return value.casefold()
    try:
        numeric_value = float(value)
    except ValueError as error:
        raise ValueError(
            f"GEO patient-sample rank characteristic {key!r} is not "
            "numeric."
        ) from error
    if not math.isfinite(numeric_value):
        raise ValueError(
            f"GEO patient-sample rank characteristic {key!r} is not "
            "finite."
        )
    return numeric_value


def derive_date_interval_days(
    raw_start: Any,
    raw_end: Any,
) -> str | None:
    start = clean(raw_start)
    end = clean(raw_end)
    if start is None or end is None:
        return None
    try:
        start_date = datetime.strptime(start, "%Y-%m-%d").date()
        end_date = datetime.strptime(end, "%Y-%m-%d").date()
    except ValueError:
        return None
    return str((end_date - start_date).days)


def normalized_aliases(value: Any) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(
            "source.expression_sample_aliases must be an object."
        )
    aliases = {
        str(source).strip(): str(target).strip()
        for source, target in value.items()
        if str(source).strip() and str(target).strip()
    }
    if len(aliases.values()) != len(set(aliases.values())):
        raise ValueError(
            "GEO expression sample aliases must have unique targets."
        )
    return aliases


def normalized_event_value_map(value: Any) -> dict[str, int]:
    mapping = {"0": 0, "1": 1}
    if value is None:
        return mapping
    if not isinstance(value, dict):
        raise ValueError("source.event_value_map must be an object.")
    for raw_value, event in value.items():
        key = str(raw_value).strip().casefold()
        if not key or isinstance(event, bool) or event not in {0, 1}:
            raise ValueError(
                "GEO event mappings require non-empty labels and 0/1 values."
            )
        mapping[key] = int(event)
    return mapping


def normalized_geo_categorical_value_map(
    value: Any,
    *,
    field: str,
) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"source.{field}_value_map must be an object.")
    mapping = {
        str(source).strip().casefold(): str(target).strip()
        for source, target in value.items()
        if str(source).strip() and str(target).strip()
    }
    if len(mapping) != len(value):
        raise ValueError(
            f"GEO {field} mappings require non-empty source and target labels."
        )
    return mapping


def map_geo_event(
    value: Any,
    event_value_map: dict[str, int],
) -> int | None:
    normalized = clean(value)
    if normalized is None:
        return None
    return event_value_map.get(normalized.casefold())


def normalized_geo_age(value: Any, *, divisor: float) -> str:
    normalized = clean(value)
    if normalized is None:
        return ""
    if divisor == 1.0:
        return normalized
    try:
        numeric = float(normalized)
    except (TypeError, ValueError) as error:
        raise ValueError(
            "GEO age values must be numeric when age_divisor is configured."
        ) from error
    if not math.isfinite(numeric) or numeric < 0:
        raise ValueError(
            "GEO age values must be finite and non-negative."
        )
    return format(numeric / divisor, ".17g")


def geo_sample_identifier(
    title: str,
    characteristics: dict[str, Any],
    characteristic: str,
    *,
    label: str,
    geo_accession: str | None = None,
) -> str:
    if not characteristic:
        return title
    if characteristic.strip().casefold() == "geo_accession":
        identifier = clean(geo_accession)
    else:
        identifier = clean(characteristics.get(characteristic))
    if identifier is None:
        raise ValueError(
            f"GEO sample {title!r} lacks the configured {label} "
            f"characteristic {characteristic!r}."
        )
    return identifier


def geo_sample_metadata_identifier(
    sample: dict[str, Any],
    field: str,
    *,
    label: str,
) -> str:
    values = geo_sample_metadata_values(sample, field)
    if len(values) != 1:
        raise ValueError(
            f"GEO sample {str(sample.get('title') or '')!r} must have "
            f"exactly one {field!r} metadata value for its {label} ID."
        )
    return values[0]


def normalize_geo_identifier(
    identifier: str,
    pattern: str,
    replacement: str,
    *,
    label: str,
) -> str:
    if not pattern:
        return identifier
    try:
        normalized, replacements = re.subn(
            pattern,
            replacement,
            identifier,
        )
    except re.error as error:
        raise ValueError(
            f"Invalid GEO {label} normalization pattern."
        ) from error
    normalized = normalized.strip()
    if replacements != 1 or not normalized:
        raise ValueError(
            f"GEO {label} {identifier!r} did not match its configured "
            "normalization pattern exactly once."
        )
    return normalized


def verify_pinned_file(
    path: Path,
    *,
    expected_size: Any,
    expected_sha256: Any,
    label: str,
) -> None:
    has_size = expected_size is not None
    has_sha256 = bool(str(expected_sha256 or "").strip())
    if not has_size and not has_sha256:
        return
    if not has_size or not has_sha256:
        raise ValueError(
            f"{label} pin requires both size and SHA-256."
        )
    size = int(expected_size)
    digest = str(expected_sha256).strip().lower()
    if size <= 0 or len(digest) != 64:
        raise ValueError(f"{label} pin is invalid.")
    if path.stat().st_size != size:
        raise ValueError(f"{label} changed size.")
    if sha256_file(path) != digest:
        raise ValueError(f"{label} changed SHA-256.")


def materialize_gene_reference(
    reference_spec: Any,
    source_dir: Path,
) -> Path | None:
    if reference_spec is None:
        return None
    if not isinstance(reference_spec, dict):
        raise ValueError("GEO gene_reference must be an object.")
    url = str(reference_spec.get("url") or "").strip()
    name = str(reference_spec.get("name") or "").strip()
    if not url or not name or Path(name).name != name:
        raise ValueError(
            "GEO gene_reference requires a URL and a safe file name."
        )
    path = source_dir / name
    download(url, path)
    verify_pinned_file(
        path,
        expected_size=reference_spec.get("size"),
        expected_sha256=reference_spec.get("sha256"),
        label="GEO gene reference",
    )
    return path


def parse_ensembl_gene_map(path: Path) -> dict[str, str]:
    mapping: dict[str, str] = {}
    conflicts: set[str] = set()
    with gzip.open(
        path,
        mode="rt",
        newline="",
        encoding="utf-8",
        errors="strict",
    ) as handle:
        for line in handle:
            if not line or line.startswith("#"):
                continue
            fields = line.rstrip("\n").split("\t")
            if len(fields) != 9:
                continue
            attributes = {
                key: value
                for key, value in re.findall(
                    r'([A-Za-z0-9_]+) "([^"]*)"', fields[8]
                )
            }
            gene_id = str(attributes.get("gene_id") or "").strip()
            symbol = str(attributes.get("gene_name") or "").strip().upper()
            if not gene_id.startswith("ENSG") or not symbol:
                continue
            for key in {gene_id, gene_id.split(".", 1)[0]}:
                existing = mapping.get(key)
                if existing is not None and existing != symbol:
                    conflicts.add(key)
                else:
                    mapping[key] = symbol
    for key in conflicts:
        mapping.pop(key, None)
    if len(mapping) < 10_000:
        raise ValueError(
            "Pinned Ensembl reference maps fewer than 10,000 genes."
        )
    return mapping


def parse_ensembl_transcript_gene_map(
    path: Path,
) -> dict[str, tuple[str, str]]:
    mapping: dict[str, tuple[str, str]] = {}
    conflicts: set[str] = set()
    with gzip.open(
        path,
        mode="rt",
        newline="",
        encoding="utf-8",
        errors="strict",
    ) as handle:
        for line in handle:
            if not line or line.startswith("#"):
                continue
            fields = line.rstrip("\n").split("\t")
            if len(fields) != 9 or fields[2] != "transcript":
                continue
            attributes = {
                key: value
                for key, value in re.findall(
                    r'([A-Za-z0-9_]+) "([^"]*)"', fields[8]
                )
            }
            transcript_id = str(
                attributes.get("transcript_id") or ""
            ).strip()
            gene_id = str(attributes.get("gene_id") or "").strip()
            symbol = str(
                attributes.get("gene_name") or ""
            ).strip().upper()
            if (
                not transcript_id.startswith("ENST")
                or not gene_id.startswith("ENSG")
                or not symbol
            ):
                continue
            target = (gene_id.split(".", 1)[0], symbol)
            for key in {
                transcript_id,
                transcript_id.split(".", 1)[0],
            }:
                existing = mapping.get(key)
                if existing is not None and existing != target:
                    conflicts.add(key)
                else:
                    mapping[key] = target
    for key in conflicts:
        mapping.pop(key, None)
    if len(mapping) < 10_000:
        raise ValueError(
            "Pinned Ensembl reference maps fewer than 10,000 transcripts."
        )
    return mapping


def materialize_ensembl_expression(
    source: Path,
    target: Path,
    gene_reference: Path,
    *,
    expression_sample_aliases: dict[str, str],
    feature_id_pattern: str = "",
) -> dict[str, Any]:
    gene_map = parse_ensembl_gene_map(gene_reference)
    delimiter = expression_delimiter(source)
    compiled_feature_pattern: re.Pattern[str] | None = None
    if feature_id_pattern:
        try:
            compiled_feature_pattern = re.compile(feature_id_pattern)
        except re.error as error:
            raise ValueError(
                "Invalid GEO expression feature-ID pattern."
            ) from error
        if compiled_feature_pattern.groups != 1:
            raise ValueError(
                "GEO expression feature-ID pattern requires exactly one "
                "capturing group."
            )
    mapped_rows = 0
    unmapped_rows = 0
    seen_gene_ids: set[str] = set()
    symbol_counts: dict[str, int] = {}
    with open_expression_text(source) as input_handle:
        reader = csv.reader(input_handle, delimiter=delimiter)
        header = next(reader)
        if (
            len(header) < 11
            or not header[0].strip()
            or len(header) != len(set(header))
        ):
            raise ValueError(
                "GEO Ensembl expression header is missing or duplicated."
            )
        source_samples = set(header[1:])
        missing_alias_targets = sorted(
            target_name
            for target_name in expression_sample_aliases.values()
            if target_name not in source_samples
        )
        if missing_alias_targets:
            raise ValueError(
                "GEO expression alias targets are absent from the matrix: "
                f"{missing_alias_targets[:5]}"
            )
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
                        ["Ensembl_Gene_Id|Hugo_Symbol", *header[1:]]
                    )
                    for row in reader:
                        if not row:
                            continue
                        if len(row) != len(header):
                            raise ValueError(
                                "GEO expression row width is inconsistent."
                            )
                        raw_feature = row[0].strip()
                        if compiled_feature_pattern is None:
                            gene_id = raw_feature
                        else:
                            match = compiled_feature_pattern.fullmatch(
                                raw_feature
                            )
                            if match is None or not match.group(1).strip():
                                raise ValueError(
                                    "GEO expression feature does not match "
                                    "the configured Ensembl-ID pattern: "
                                    f"{raw_feature!r}."
                                )
                            gene_id = match.group(1).strip()
                        if gene_id in seen_gene_ids:
                            raise ValueError(
                                "GEO expression matrix has duplicate "
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
                        writer.writerow(
                            [f"{gene_id}|{symbol}", *row[1:]]
                        )
                        mapped_rows += 1
                        symbol_counts[symbol] = (
                            symbol_counts.get(symbol, 0) + 1
                        )
    if mapped_rows < 10_000:
        raise ValueError(
            "Fewer than 10,000 GEO expression rows map to gene symbols."
        )
    ambiguous_symbols = {
        symbol
        for symbol, count in symbol_counts.items()
        if count > 1
    }
    return {
        "geo_gene_reference_sha256": sha256_file(gene_reference),
        "geo_source_expression_gene_rows": len(seen_gene_ids),
        "geo_mapped_expression_gene_rows": mapped_rows,
        "geo_unmapped_expression_gene_rows": unmapped_rows,
        "geo_unique_mapped_symbols": len(symbol_counts),
        "geo_ambiguous_mapped_symbols": len(ambiguous_symbols),
        "geo_unambiguous_mapped_symbols": sum(
            count == 1 for count in symbol_counts.values()
        ),
        "geo_expression_feature_id_pattern": feature_id_pattern,
    }


def parse_ncbi_gene_info_map(path: Path) -> dict[str, str]:
    mapping: dict[str, str] = {}
    conflicts: set[str] = set()
    with gzip.open(
        path,
        mode="rt",
        newline="",
        encoding="utf-8",
        errors="strict",
    ) as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        required = {"#tax_id", "GeneID", "Symbol"}
        if not reader.fieldnames or not required.issubset(
            set(reader.fieldnames)
        ):
            raise ValueError(
                "Pinned NCBI gene_info reference lacks required columns."
            )
        for row in reader:
            if str(row.get("#tax_id") or "").strip() != "9606":
                continue
            gene_id = str(row.get("GeneID") or "").strip()
            symbol = str(row.get("Symbol") or "").strip().upper()
            if not gene_id.isdigit() or not symbol or symbol == "-":
                continue
            existing = mapping.get(gene_id)
            if existing is not None and existing != symbol:
                conflicts.add(gene_id)
            else:
                mapping[gene_id] = symbol
    for gene_id in conflicts:
        mapping.pop(gene_id, None)
    if len(mapping) < 10_000:
        raise ValueError(
            "Pinned NCBI gene_info reference maps fewer than 10,000 genes."
        )
    return mapping


def materialize_entrez_expression(
    source: Path,
    target: Path,
    gene_reference: Path,
    *,
    expression_sample_aliases: dict[str, str],
    feature_id_pattern: str = "",
) -> dict[str, Any]:
    gene_map = parse_ncbi_gene_info_map(gene_reference)
    delimiter = expression_delimiter(source)
    compiled_feature_pattern: re.Pattern[str] | None = None
    if feature_id_pattern:
        try:
            compiled_feature_pattern = re.compile(feature_id_pattern)
        except re.error as error:
            raise ValueError(
                "Invalid GEO expression feature-ID pattern."
            ) from error
        if compiled_feature_pattern.groups != 1:
            raise ValueError(
                "GEO expression feature-ID pattern requires exactly one "
                "capturing group."
            )

    mapped_rows = 0
    unmapped_rows = 0
    seen_gene_ids: set[str] = set()
    symbol_counts: dict[str, int] = {}
    with open_expression_text(source) as input_handle:
        reader = csv.reader(input_handle, delimiter=delimiter)
        header = next(reader)
        if (
            len(header) < 11
            or not header[0].strip()
            or len(header) != len(set(header))
        ):
            raise ValueError(
                "GEO Entrez expression header is missing or duplicated."
            )
        source_samples = set(header[1:])
        missing_alias_targets = sorted(
            target_name
            for target_name in expression_sample_aliases.values()
            if target_name not in source_samples
        )
        if missing_alias_targets:
            raise ValueError(
                "GEO expression alias targets are absent from the matrix: "
                f"{missing_alias_targets[:5]}"
            )
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
                        ["Hugo_Symbol|Entrez_Gene_Id", *header[1:]]
                    )
                    for row in reader:
                        if not row:
                            continue
                        if len(row) != len(header):
                            raise ValueError(
                                "GEO expression row width is inconsistent."
                            )
                        raw_feature = row[0].strip()
                        if compiled_feature_pattern is None:
                            gene_id = raw_feature
                        else:
                            match = compiled_feature_pattern.fullmatch(
                                raw_feature
                            )
                            if match is None or not match.group(1).strip():
                                raise ValueError(
                                    "GEO expression feature does not match "
                                    "the configured Entrez-ID pattern: "
                                    f"{raw_feature!r}."
                                )
                            gene_id = match.group(1).strip()
                        if gene_id in seen_gene_ids:
                            raise ValueError(
                                "GEO expression matrix has duplicate "
                                f"Entrez ID {gene_id!r}."
                            )
                        seen_gene_ids.add(gene_id)
                        symbol = gene_map.get(gene_id)
                        if not symbol:
                            unmapped_rows += 1
                            continue
                        writer.writerow(
                            [f"{symbol}|{gene_id}", *row[1:]]
                        )
                        mapped_rows += 1
                        symbol_counts[symbol] = (
                            symbol_counts.get(symbol, 0) + 1
                        )
    if mapped_rows < 10_000:
        raise ValueError(
            "Fewer than 10,000 GEO expression rows map from Entrez IDs."
        )
    ambiguous_symbols = {
        symbol
        for symbol, count in symbol_counts.items()
        if count > 1
    }
    return {
        "geo_gene_reference_sha256": sha256_file(gene_reference),
        "geo_source_expression_gene_rows": len(seen_gene_ids),
        "geo_mapped_expression_gene_rows": mapped_rows,
        "geo_unmapped_expression_gene_rows": unmapped_rows,
        "geo_unique_mapped_symbols": len(symbol_counts),
        "geo_ambiguous_mapped_symbols": len(ambiguous_symbols),
        "geo_unambiguous_mapped_symbols": sum(
            count == 1 for count in symbol_counts.values()
        ),
        "geo_expression_feature_id_pattern": feature_id_pattern,
    }


def materialize_geo_recount3_support(
    expression_spec: dict[str, Any],
    source_dir: Path,
) -> tuple[dict[str, Path], dict[str, str]]:
    support_fields = {
        "recount3_sra_metadata": (
            "sample_metadata_url",
            "sample_metadata_size",
            "sample_metadata_sha256",
        ),
        "recount3_qc_metadata": (
            "qc_metadata_url",
            "qc_metadata_size",
            "qc_metadata_sha256",
        ),
    }
    paths: dict[str, Path] = {}
    urls: dict[str, str] = {}
    for role, (url_key, size_key, sha_key) in support_fields.items():
        url = str(expression_spec.get(url_key) or "").strip()
        source_name = PurePosixPath(
            urllib.parse.urlparse(url).path
        ).name
        if (
            not url
            or not source_name
            or source_name in {".", ".."}
        ):
            raise ValueError(
                "GEO recount3 expression requires pinned sample and QC "
                "metadata URLs."
            )
        path = source_dir / f"{role}_{source_name}"
        download(url, path)
        verify_pinned_file(
            path,
            expected_size=expression_spec.get(size_key),
            expected_sha256=expression_spec.get(sha_key),
            label=role.replace("_", " "),
        )
        paths[role] = path
        urls[role] = url
    return paths, urls


def materialize_geo_recount3_matrix(
    source: Path,
    target: Path,
    sample_ids: list[str],
    *,
    sample_metadata: Path,
    qc_metadata: Path,
    run_id_column: str,
    sample_id_column: str,
    auc_column: str,
    target_size: float,
    expected_annotation: str = "",
    expected_source_runs: int | None = None,
) -> dict[str, Any]:
    if (
        len(sample_ids) != len(set(sample_ids))
        or not sample_ids
        or not run_id_column
        or not sample_id_column
        or not auc_column
        or not math.isfinite(target_size)
        or target_size <= 0
    ):
        raise ValueError(
            "GEO recount3 normalization requires unique sample IDs, "
            "metadata columns and a positive finite target size."
        )

    sample_records = read_geo_recount3_metadata(
        sample_metadata,
        required_columns={run_id_column, sample_id_column},
        label="SRA sample metadata",
    )
    qc_records = read_geo_recount3_metadata(
        qc_metadata,
        required_columns={run_id_column, auc_column},
        label="QC metadata",
    )
    samples_by_id: dict[str, dict[str, str]] = {}
    runs_in_metadata: set[str] = set()
    for record in sample_records:
        run_id = str(record.get(run_id_column) or "").strip()
        sample_id = str(record.get(sample_id_column) or "").strip()
        if not run_id or not sample_id or run_id in runs_in_metadata:
            raise ValueError(
                "GEO recount3 sample metadata has missing or duplicate "
                "run/sample identifiers."
            )
        if sample_id in samples_by_id:
            raise ValueError(
                f"GEO recount3 sample {sample_id!r} maps to multiple runs."
            )
        runs_in_metadata.add(run_id)
        samples_by_id[sample_id] = record

    qc_by_run: dict[str, dict[str, str]] = {}
    for record in qc_records:
        run_id = str(record.get(run_id_column) or "").strip()
        if not run_id or run_id in qc_by_run:
            raise ValueError(
                "GEO recount3 QC metadata has missing or duplicate run IDs."
            )
        qc_by_run[run_id] = record

    missing_samples = [
        sample_id
        for sample_id in sample_ids
        if sample_id not in samples_by_id
    ]
    if missing_samples:
        raise ValueError(
            "GEO clinical samples are absent from recount3 metadata: "
            f"{missing_samples[:5]}"
        )
    selected_runs = [
        str(samples_by_id[sample_id][run_id_column]).strip()
        for sample_id in sample_ids
    ]
    missing_qc = [
        run_id for run_id in selected_runs if run_id not in qc_by_run
    ]
    if missing_qc:
        raise ValueError(
            "GEO recount3 runs are absent from QC metadata: "
            f"{missing_qc[:5]}"
        )
    auc_values = []
    for run_id in selected_runs:
        try:
            auc = float(qc_by_run[run_id][auc_column])
        except (TypeError, ValueError) as error:
            raise ValueError(
                f"GEO recount3 AUC is not numeric for {run_id!r}."
            ) from error
        if not math.isfinite(auc) or auc <= 0:
            raise ValueError(
                f"GEO recount3 AUC is not positive for {run_id!r}."
            )
        auc_values.append(auc)

    annotation = ""
    generated_at = ""
    with gzip.open(
        source,
        mode="rt",
        newline="",
        encoding="utf-8",
        errors="strict",
    ) as input_handle:
        header: list[str] | None = None
        for line in input_handle:
            if line.startswith("##"):
                key, _, value = line[2:].rstrip("\n").partition("=")
                if key == "annotation":
                    annotation = value.strip()
                elif key == "date.generated":
                    generated_at = value.strip()
                continue
            header = line.rstrip("\n").split("\t")
            break
        if (
            header is None
            or len(header) < 11
            or header[0].strip() != "gene_id"
            or len(header) != len(set(header))
        ):
            raise ValueError(
                "GEO recount3 gene-sums header is missing or duplicated."
            )
        source_runs = header[1:]
        if (
            expected_source_runs is not None
            and len(source_runs) != expected_source_runs
        ):
            raise ValueError(
                "GEO recount3 source run count changed: "
                f"{len(source_runs)} != {expected_source_runs}."
            )
        if expected_annotation and annotation != expected_annotation:
            raise ValueError(
                "GEO recount3 annotation changed: "
                f"{annotation!r} != {expected_annotation!r}."
            )
        source_run_set = set(source_runs)
        if source_run_set != runs_in_metadata:
            raise ValueError(
                "GEO recount3 gene-sums runs differ from SRA metadata."
            )
        if source_run_set != set(qc_by_run):
            raise ValueError(
                "GEO recount3 gene-sums runs differ from QC metadata."
            )
        source_index = {
            run_id: index + 1
            for index, run_id in enumerate(source_runs)
        }
        selected_indexes = [
            source_index[run_id] for run_id in selected_runs
        ]
        scale_factors = [
            target_size / auc for auc in auc_values
        ]

        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open(
            "w",
            newline="",
            encoding="utf-8",
        ) as output_handle:
            writer = csv.writer(
                output_handle,
                delimiter="\t",
                lineterminator="\n",
            )
            writer.writerow(["Ensembl_Gene_Id", *sample_ids])
            seen_features: set[str] = set()
            gene_rows = 0
            for line in input_handle:
                if not line.strip():
                    continue
                row = line.rstrip("\n").split("\t")
                if len(row) != len(header):
                    raise ValueError(
                        "GEO recount3 gene-sums row width is inconsistent."
                    )
                feature = row[0].strip()
                if not feature or feature in seen_features:
                    raise ValueError(
                        "GEO recount3 gene-sums contains a missing or "
                        f"duplicate feature: {feature!r}."
                    )
                seen_features.add(feature)
                normalized_values = []
                for index, scale_factor in zip(
                    selected_indexes,
                    scale_factors,
                    strict=True,
                ):
                    try:
                        raw_value = int(row[index])
                    except ValueError as error:
                        raise ValueError(
                            "GEO recount3 gene-sums contains a non-integer "
                            f"value for {feature!r}."
                        ) from error
                    if raw_value < 0:
                        raise ValueError(
                            "GEO recount3 gene-sums contains a negative "
                            f"value for {feature!r}."
                        )
                    scaled_value = round(raw_value * scale_factor)
                    normalized_values.append(
                        math.log2(scaled_value + 1.0)
                    )
                writer.writerow(
                    [
                        feature,
                        *(
                            format(value, ".17g")
                            for value in normalized_values
                        ),
                    ]
                )
                gene_rows += 1
    if gene_rows < 10_000:
        raise ValueError(
            "GEO recount3 matrix has fewer than 10,000 gene rows."
        )
    return {
        "source_expression_layout": "recount3_gene_sums",
        "source_expression_columns": len(source_runs),
        "selected_expression_columns": len(sample_ids),
        "source_expression_gene_rows": gene_rows,
        "normalized_expression_gene_rows": gene_rows,
        "recount3_annotation": annotation,
        "recount3_generated_at": generated_at or None,
        "recount3_run_id_column": run_id_column,
        "recount3_sample_id_column": sample_id_column,
        "recount3_auc_column": auc_column,
        "recount3_target_size": target_size,
        "recount3_scale_factor_min": min(scale_factors),
        "recount3_scale_factor_max": max(scale_factors),
        "recount3_sample_metadata_sha256": sha256_file(sample_metadata),
        "recount3_qc_metadata_sha256": sha256_file(qc_metadata),
        "expression_normalization": (
            "log2(round(raw base-pair coverage * target_size / "
            "sample AUC) + 1)"
        ),
    }


def read_geo_recount3_metadata(
    path: Path,
    *,
    required_columns: set[str],
    label: str,
) -> list[dict[str, str]]:
    with gzip.open(
        path,
        mode="rt",
        newline="",
        encoding="utf-8",
        errors="strict",
    ) as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        fieldnames = set(reader.fieldnames or [])
        if not required_columns.issubset(fieldnames):
            raise ValueError(
                f"GEO recount3 {label} lacks required columns: "
                f"{sorted(required_columns - fieldnames)}."
            )
        records = [
            {
                str(key): str(value or "").strip()
                for key, value in record.items()
                if key is not None
            }
            for record in reader
            if record and any(str(value or "").strip() for value in record.values())
        ]
    if not records:
        raise ValueError(f"GEO recount3 {label} contains no records.")
    return records


def materialize_geo_wide_normalized_matrix(
    source: Path,
    target: Path,
    sample_ids: list[str],
    *,
    feature_column: str,
    feature_column_index: int | None = None,
    feature_column_output: str = "",
    sample_start_column: int,
    header_missing_feature_column: bool = False,
    header_missing_leading_column: bool = False,
    value_transform: str,
    duplicate_feature_policy: str = "error",
    duplicate_feature_case_insensitive: bool = False,
    drop_incomplete_features: bool = False,
    missing_value_tokens: list[str] | None = None,
    allow_negative_values: bool = False,
    source_sample_id_pattern: str = "",
    source_sample_id_replacement: str = "",
) -> dict[str, Any]:
    normalized_missing_tokens = {
        str(value).strip()
        for value in (missing_value_tokens or [])
        if str(value).strip()
    }
    if (
        sample_start_column < 2
        or bool(feature_column) == (feature_column_index is not None)
        or (
            header_missing_feature_column
            and header_missing_leading_column
        )
        or (
            header_missing_feature_column
            and feature_column_index != 1
        )
        or value_transform not in {"identity", "log2p"}
        or (allow_negative_values and value_transform != "identity")
        or duplicate_feature_policy
        not in {"error", "exclude_ambiguous"}
        or bool(normalized_missing_tokens)
        != bool(drop_incomplete_features)
    ):
        raise ValueError(
            "GEO normalized matrices require exactly one feature-column "
            "name or one-based index, a valid sample_start_column and an "
            "identity or log2p transform. Negative source values may be "
            "allowed only with the identity transform. A source header "
            "that omits its feature label must use "
            "feature_column_index=1. A missing leading-column label must "
            "be declared separately. Duplicate features must either "
            "raise an error or be excluded as ambiguous. Missing-value "
            "tokens require explicit incomplete-feature exclusion."
        )
    try:
        sample_id_pattern = (
            re.compile(source_sample_id_pattern)
            if source_sample_id_pattern
            else None
        )
    except re.error as error:
        raise ValueError(
            "Invalid GEO normalized-matrix source sample-ID pattern."
        ) from error
    if sample_id_pattern is not None and not source_sample_id_replacement:
        raise ValueError(
            "GEO normalized-matrix source sample-ID normalization requires "
            "a non-empty replacement."
        )

    delimiter = expression_delimiter(source)
    with open_expression_text(source) as input_handle:
        reader = csv.reader(input_handle, delimiter=delimiter)
        header = next(reader)
        if (
            header_missing_feature_column
            or header_missing_leading_column
        ):
            header = ["", *header]
        if len(header) != len(set(header)):
            raise ValueError(
                "GEO normalized-matrix header contains duplicate columns."
            )
        if feature_column_index is None:
            try:
                feature_index = header.index(feature_column)
            except ValueError as error:
                raise ValueError(
                    "GEO normalized-matrix feature column "
                    f"{feature_column!r} is absent."
                ) from error
        else:
            feature_index = feature_column_index - 1
            if feature_index < 0 or feature_index >= len(header):
                raise ValueError(
                    "GEO normalized-matrix feature_column_index falls "
                    "outside the source header."
                )
        normalized_feature_column = (
            feature_column_output or header[feature_index].strip()
        )
        if not normalized_feature_column:
            raise ValueError(
                "GEO normalized matrix requires a non-empty feature "
                "column in its output."
            )
        sample_start_index = sample_start_column - 1
        if (
            sample_start_index <= feature_index
            or sample_start_index >= len(header)
        ):
            raise ValueError(
                "GEO normalized-matrix sample_start_column must follow "
                "the feature column and fall inside the header."
            )
        source_index: dict[str, int] = {}
        sample_id_normalizations = 0
        for index, value in enumerate(header):
            if index < sample_start_index or not value.strip():
                continue
            source_id = value.strip()
            normalized_source_id = source_id
            if sample_id_pattern is not None:
                match = sample_id_pattern.fullmatch(source_id)
                if match is None:
                    raise ValueError(
                        "GEO normalized-matrix source sample ID does not "
                        f"match its configured pattern: {source_id!r}."
                    )
                normalized_source_id = match.expand(
                    source_sample_id_replacement
                ).strip()
                if not normalized_source_id:
                    raise ValueError(
                        "GEO normalized-matrix sample-ID normalization "
                        "produced an empty identifier."
                    )
                if normalized_source_id != source_id:
                    sample_id_normalizations += 1
            if normalized_source_id in source_index:
                raise ValueError(
                    "GEO normalized-matrix sample-ID normalization "
                    f"produced a collision for {normalized_source_id!r}."
                )
            source_index[normalized_source_id] = index
        missing = [
            sample_id
            for sample_id in sample_ids
            if sample_id not in source_index
        ]
        if missing:
            raise ValueError(
                "GEO clinical samples are absent from the normalized "
                f"matrix: {missing[:5]}"
            )
        indexes = [source_index[sample_id] for sample_id in sample_ids]

        feature_counts: dict[str, int] = {}
        incomplete_features: set[str] = set()
        incomplete_feature_rows = 0
        source_feature_rows = 0
        for row in reader:
            if not row:
                continue
            if len(row) != len(header):
                raise ValueError(
                    "GEO normalized-matrix row width is inconsistent."
                )
            feature = row[feature_index].strip()
            if not feature:
                continue
            feature_key = (
                feature.casefold()
                if duplicate_feature_case_insensitive
                else feature
            )
            feature_counts[feature_key] = (
                feature_counts.get(feature_key, 0) + 1
            )
            if any(
                row[index].strip() in normalized_missing_tokens
                for index in indexes
            ):
                incomplete_features.add(feature_key)
                incomplete_feature_rows += 1
            source_feature_rows += 1

    duplicate_features = {
        feature
        for feature, count in feature_counts.items()
        if count > 1
    }
    duplicate_feature_rows = sum(
        feature_counts[feature]
        for feature in duplicate_features
    )
    if duplicate_features and duplicate_feature_policy == "error":
        raise ValueError(
            "GEO normalized matrix repeats features: "
            f"{sorted(duplicate_features)[:5]}."
        )

    with open_expression_text(source) as input_handle, target.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as output_handle:
        reader = csv.reader(input_handle, delimiter=delimiter)
        next(reader)
        writer = csv.writer(
            output_handle,
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writerow([normalized_feature_column, *sample_ids])
        written_rows = 0
        for row in reader:
            if not row:
                continue
            if len(row) != len(header):
                raise ValueError(
                    "GEO normalized-matrix row width is inconsistent."
                )
            feature = row[feature_index].strip()
            if not feature:
                continue
            feature_key = (
                feature.casefold()
                if duplicate_feature_case_insensitive
                else feature
            )
            if feature_key in duplicate_features:
                continue
            if feature_key in incomplete_features:
                continue
            values = parse_geo_normalized_values(
                row,
                indexes,
                feature,
                allow_negative_values=allow_negative_values,
            )
            if value_transform == "log2p":
                values = [math.log2(value + 1.0) for value in values]
            writer.writerow(
                [
                    feature,
                    *(format(value, ".17g") for value in values),
                ]
            )
            written_rows += 1
    if written_rows < 10_000:
        raise ValueError(
            "GEO normalized matrix has fewer than 10,000 gene rows."
        )
    return {
        "source_expression_layout": "wide_normalized_matrix",
        "source_expression_columns": (
            len(header) - sample_start_index
        ),
        "selected_expression_columns": len(sample_ids),
        "source_expression_gene_rows": source_feature_rows,
        "normalized_expression_gene_rows": written_rows,
        "source_expression_feature_column": header[feature_index],
        "source_expression_feature_column_index": feature_index + 1,
        "normalized_expression_feature_column": normalized_feature_column,
        "source_expression_sample_start_column": sample_start_column,
        "source_expression_sample_id_pattern": (
            source_sample_id_pattern or None
        ),
        "source_expression_sample_id_replacement": (
            source_sample_id_replacement
            if source_sample_id_pattern
            else None
        ),
        "source_expression_sample_id_normalizations": (
            sample_id_normalizations
        ),
        "source_expression_header_missing_feature_column": (
            header_missing_feature_column
        ),
        "source_expression_header_missing_leading_column": (
            header_missing_leading_column
        ),
        "source_expression_value_transform": value_transform,
        "source_expression_allow_negative_values": allow_negative_values,
        "source_expression_duplicate_feature_policy": (
            duplicate_feature_policy
        ),
        "source_expression_duplicate_feature_case_insensitive": (
            duplicate_feature_case_insensitive
        ),
        "source_expression_duplicate_feature_symbols": len(
            duplicate_features
        ),
        "source_expression_duplicate_feature_rows": duplicate_feature_rows,
        "source_expression_excluded_duplicate_feature_rows": (
            duplicate_feature_rows
            if duplicate_feature_policy == "exclude_ambiguous"
            else 0
        ),
        "source_expression_dropped_incomplete_features": len(
            incomplete_features
        ),
        "source_expression_dropped_incomplete_feature_rows": (
            incomplete_feature_rows
        ),
        "source_expression_missing_value_tokens": sorted(
            normalized_missing_tokens
        ),
        "expression_normalization": (
            "log2(source normalized value + 1)"
            if value_transform == "log2p"
            else "source normalized value"
        ),
    }


def materialize_geo_transcript_count_matrix(
    source: Path,
    target: Path,
    sample_ids: list[str],
    *,
    gene_reference: Path,
    feature_column: str,
    feature_column_index: int | None = None,
    sample_start_column: int,
    count_value_type: str = "integer",
    require_complete_reference: bool = False,
) -> dict[str, Any]:
    if (
        sample_start_column < 2
        or count_value_type
        not in {"integer", "nonnegative_numeric"}
        or bool(feature_column) == (feature_column_index is not None)
    ):
        raise ValueError(
            "GEO transcript-count matrices require exactly one "
            "feature-column name or one-based index and a valid "
            "sample_start_column."
        )
    transcript_map = parse_ensembl_transcript_gene_map(gene_reference)
    delimiter = expression_delimiter(source)
    with open_expression_text(source) as input_handle:
        reader = csv.reader(input_handle, delimiter=delimiter)
        header = next(reader)
        if len(header) != len(set(header)):
            raise ValueError(
                "GEO transcript-count header contains duplicate columns."
            )
        if feature_column_index is None:
            try:
                feature_index = header.index(feature_column)
            except ValueError as error:
                raise ValueError(
                    "GEO transcript-count feature column "
                    f"{feature_column!r} is absent."
                ) from error
        else:
            feature_index = feature_column_index - 1
            if feature_index < 0 or feature_index >= len(header):
                raise ValueError(
                    "GEO transcript-count feature_column_index falls "
                    "outside the source header."
                )
        sample_start_index = sample_start_column - 1
        if (
            sample_start_index <= feature_index
            or sample_start_index >= len(header)
        ):
            raise ValueError(
                "GEO transcript-count sample_start_column must follow "
                "the feature column and fall inside the header."
            )
        source_index = {
            value.strip(): index
            for index, value in enumerate(header)
            if index >= sample_start_index and value.strip()
        }
        missing = [
            sample_id
            for sample_id in sample_ids
            if sample_id not in source_index
        ]
        if missing:
            raise ValueError(
                "GEO clinical samples are absent from the transcript "
                f"count matrix: {missing[:5]}"
            )
        indexes = [source_index[sample_id] for sample_id in sample_ids]
        library_sizes = [0.0] * len(sample_ids)
        aggregated: dict[str, tuple[str, list[float]]] = {}
        seen_transcripts: set[str] = set()
        mapped_transcripts = 0
        unmapped_transcripts = 0
        for row in reader:
            if not row:
                continue
            if len(row) != len(header):
                raise ValueError(
                    "GEO transcript-count row width is inconsistent."
                )
            raw_transcript = row[feature_index].strip()
            if not raw_transcript:
                continue
            transcript_id = raw_transcript.split(".", 1)[0]
            if not transcript_id.startswith("ENST"):
                raise ValueError(
                    "GEO transcript-count feature is not an Ensembl "
                    f"transcript ID: {raw_transcript!r}."
                )
            if transcript_id in seen_transcripts:
                raise ValueError(
                    "GEO transcript-count matrix repeats transcript "
                    f"{transcript_id!r}."
                )
            seen_transcripts.add(transcript_id)
            values = parse_geo_counts(
                row,
                indexes,
                transcript_id,
                require_integer=count_value_type == "integer",
            )
            library_sizes = [
                current + value
                for current, value in zip(
                    library_sizes,
                    values,
                    strict=True,
                )
            ]
            target_gene = transcript_map.get(transcript_id)
            if target_gene is None:
                unmapped_transcripts += 1
                continue
            mapped_transcripts += 1
            gene_id, symbol = target_gene
            current = aggregated.get(gene_id)
            if current is None:
                aggregated[gene_id] = (symbol, list(values))
                continue
            current_symbol, current_values = current
            if current_symbol != symbol:
                raise ValueError(
                    "Pinned Ensembl reference assigns conflicting symbols "
                    f"to gene {gene_id!r}."
                )
            aggregated[gene_id] = (
                symbol,
                [
                    total + value
                    for total, value in zip(
                        current_values,
                        values,
                        strict=True,
                    )
                ],
            )
    if len(seen_transcripts) < 10_000:
        raise ValueError(
            "GEO transcript-count matrix has fewer than 10,000 rows."
        )
    if require_complete_reference and unmapped_transcripts:
        raise ValueError(
            "Pinned Ensembl reference does not cover every source "
            f"transcript: {unmapped_transcripts} unmapped."
        )
    if len(aggregated) < 10_000:
        raise ValueError(
            "Fewer than 10,000 genes remain after transcript aggregation."
        )
    if any(value <= 0 for value in library_sizes):
        raise ValueError(
            "GEO transcript-count matrix contains an empty selected "
            "library."
        )

    symbol_counts: dict[str, int] = {}
    with target.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as output_handle:
        writer = csv.writer(
            output_handle,
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writerow(
            ["Ensembl_Gene_Id|Hugo_Symbol", *sample_ids]
        )
        for gene_id in sorted(aggregated):
            symbol, values = aggregated[gene_id]
            symbol_counts[symbol] = symbol_counts.get(symbol, 0) + 1
            normalized = [
                math.log2(
                    (value / library_size) * 1_000_000.0 + 1.0
                )
                for value, library_size in zip(
                    values,
                    library_sizes,
                    strict=True,
                )
            ]
            writer.writerow(
                [
                    f"{gene_id}|{symbol}",
                    *(
                        format(value, ".17g")
                        for value in normalized
                    ),
                ]
            )
    ambiguous_symbols = sum(
        count > 1 for count in symbol_counts.values()
    )
    return {
        "source_expression_layout": "wide_transcript_counts",
        "source_expression_columns": (
            len(header) - sample_start_index
        ),
        "selected_expression_columns": len(sample_ids),
        "source_expression_transcript_rows": len(seen_transcripts),
        "normalized_expression_gene_rows": len(aggregated),
        "source_expression_feature_column": header[feature_index],
        "source_expression_feature_column_index": feature_index + 1,
        "source_expression_sample_start_column": sample_start_column,
        "source_expression_count_value_type": count_value_type,
        "expression_normalization": (
            "transcript counts summed by Ensembl gene, then "
            "log2(CPM + 1)"
        ),
        "expression_library_sizes": {
            sample_id: format(value, ".17g")
            for sample_id, value in zip(
                sample_ids,
                library_sizes,
                strict=True,
            )
        },
        "geo_gene_reference_sha256": sha256_file(gene_reference),
        "geo_source_expression_transcript_rows": len(
            seen_transcripts
        ),
        "geo_mapped_expression_transcript_rows": mapped_transcripts,
        "geo_unmapped_expression_transcript_rows": unmapped_transcripts,
        "geo_aggregated_expression_gene_rows": len(aggregated),
        "geo_unique_mapped_symbols": len(symbol_counts),
        "geo_ambiguous_mapped_symbols": ambiguous_symbols,
        "geo_unambiguous_mapped_symbols": (
            len(symbol_counts) - ambiguous_symbols
        ),
        "geo_transcript_reference_complete": (
            unmapped_transcripts == 0
        ),
    }


def materialize_geo_xlsx_count_matrix(
    source: Path,
    target: Path,
    sample_ids: list[str],
    *,
    sheet_name: str,
    header_row: int,
    feature_column: str,
    sample_start_column: int,
    feature_replacements: dict[str, Any],
    case_insensitive_samples: bool,
    feature_column_output: str = "",
    duplicate_feature_policy: str = "allow",
    duplicate_feature_case_insensitive: bool = False,
    count_value_type: str = "integer",
) -> dict[str, Any]:
    from app.repository.adapters.pmc import (
        materialize_xlsx_expression_matrix,
    )

    selected_counts = target.with_name(
        f"{target.stem}_selected_counts.tsv"
    )
    xlsx_metadata = materialize_xlsx_expression_matrix(
        source,
        selected_counts,
        sample_ids,
        sheet_name=sheet_name,
        header_row=header_row,
        feature_column=feature_column,
        sample_start_column=sample_start_column,
        feature_replacements=feature_replacements,
        case_insensitive_samples=case_insensitive_samples,
        duplicate_feature_policy=duplicate_feature_policy,
        duplicate_feature_case_insensitive=(
            duplicate_feature_case_insensitive
        ),
    )
    count_metadata = materialize_geo_count_matrix(
        selected_counts,
        target,
        sample_ids,
        feature_column=feature_column,
        feature_column_output=feature_column_output,
        sample_start_column=2,
        count_value_type=count_value_type,
    )
    return {
        **xlsx_metadata,
        **count_metadata,
        "source_expression_layout": "xlsx_gene_counts",
        "source_expression_columns": xlsx_metadata[
            "source_expression_columns"
        ],
        "source_expression_sheet": xlsx_metadata[
            "source_expression_sheet"
        ],
        "source_expression_header_row": xlsx_metadata[
            "source_expression_header_row"
        ],
        "source_expression_feature_replacements": xlsx_metadata[
            "source_expression_feature_replacements"
        ],
        "source_expression_duplicate_feature_policy": xlsx_metadata[
            "source_expression_duplicate_feature_policy"
        ],
        "source_expression_duplicate_feature_case_insensitive": (
            xlsx_metadata[
                "source_expression_duplicate_feature_case_insensitive"
            ]
        ),
        "source_expression_duplicate_feature_symbols": xlsx_metadata[
            "source_expression_duplicate_feature_symbols"
        ],
        "source_expression_duplicate_feature_rows": xlsx_metadata[
            "source_expression_duplicate_feature_rows"
        ],
        "source_expression_excluded_duplicate_feature_rows": (
            xlsx_metadata[
                "source_expression_excluded_duplicate_feature_rows"
            ]
        ),
    }


def materialize_geo_count_matrix(
    source: Path,
    target: Path,
    sample_ids: list[str],
    *,
    feature_column: str,
    feature_column_index: int | None = None,
    feature_column_output: str = "",
    sample_start_column: int,
    feature_split_delimiter: str = "",
    feature_part_indexes: list[int] | None = None,
    expected_feature_parts: int | None = None,
    count_value_type: str = "integer",
    drop_all_missing_features: bool = False,
    missing_value_tokens: list[str] | None = None,
) -> dict[str, Any]:
    feature_part_indexes = feature_part_indexes or []
    normalized_missing_tokens = {
        str(value).strip()
        for value in (missing_value_tokens or [])
        if str(value).strip()
    }
    if (
        sample_start_column < 2
        or count_value_type
        not in {"integer", "nonnegative_numeric"}
        or bool(feature_column) == (feature_column_index is not None)
        or bool(feature_split_delimiter) != bool(feature_part_indexes)
        or any(index < 1 for index in feature_part_indexes)
        or len(feature_part_indexes) != len(set(feature_part_indexes))
        or (
            expected_feature_parts is not None
            and expected_feature_parts < 1
        )
        or bool(normalized_missing_tokens)
        != bool(drop_all_missing_features)
    ):
        raise ValueError(
            "GEO count matrices require exactly one feature-column name "
            "or one-based index, a valid sample_start_column and a "
            "complete feature-part and missing-value configuration."
        )
    delimiter = expression_delimiter(source)
    with open_expression_text(source) as input_handle:
        reader = csv.reader(input_handle, delimiter=delimiter)
        header = next(reader)
        nonempty_header = [
            value.strip()
            for value in header
            if value.strip()
        ]
        if len(nonempty_header) != len(set(nonempty_header)):
            raise ValueError(
                "GEO count-matrix header contains duplicate non-empty "
                "columns."
            )
        if feature_column_index is None:
            try:
                feature_index = header.index(feature_column)
            except ValueError as error:
                raise ValueError(
                    f"GEO count-matrix feature column {feature_column!r} "
                    "is absent."
                ) from error
        else:
            feature_index = feature_column_index - 1
            if feature_index < 0 or feature_index >= len(header):
                raise ValueError(
                    "GEO count-matrix feature_column_index falls outside "
                    "the source header."
                )
        normalized_feature_column = (
            feature_column_output or header[feature_index].strip()
        )
        if not normalized_feature_column:
            raise ValueError(
                "GEO count-matrix feature column requires a non-empty "
                "output name."
            )
        sample_start_index = sample_start_column - 1
        if (
            sample_start_index <= feature_index
            or sample_start_index >= len(header)
        ):
            raise ValueError(
                "GEO count-matrix sample_start_column must follow the "
                "feature column and fall inside the header."
            )
        source_index = {
            value.strip(): index
            for index, value in enumerate(header)
            if index >= sample_start_index and value.strip()
        }
        missing = [
            sample_id
            for sample_id in sample_ids
            if sample_id not in source_index
        ]
        if missing:
            raise ValueError(
                "GEO clinical samples are absent from the count matrix: "
                f"{missing[:5]}"
            )
        indexes = [source_index[sample_id] for sample_id in sample_ids]
        library_sizes = [0.0] * len(sample_ids)
        gene_rows = 0
        dropped_all_missing_features = 0
        seen_features: set[str] = set()
        for row in reader:
            if not row:
                continue
            if len(row) != len(header):
                raise ValueError(
                    "GEO count-matrix row width is inconsistent."
                )
            raw_feature = row[feature_index].strip()
            if not raw_feature:
                continue
            feature = normalize_geo_count_feature(
                raw_feature,
                delimiter=feature_split_delimiter,
                part_indexes=feature_part_indexes,
                expected_parts=expected_feature_parts,
            )
            if feature in seen_features:
                raise ValueError(
                    f"GEO count matrix repeats feature {feature!r}."
                )
            seen_features.add(feature)
            gene_rows += 1
            if should_drop_geo_count_row(
                row,
                indexes,
                feature,
                missing_value_tokens=normalized_missing_tokens,
                drop_all_missing_features=drop_all_missing_features,
            ):
                dropped_all_missing_features += 1
                continue
            values = parse_geo_counts(
                row,
                indexes,
                feature,
                require_integer=count_value_type == "integer",
            )
            library_sizes = [
                current + value
                for current, value in zip(
                    library_sizes,
                    values,
                    strict=True,
                )
            ]
    if gene_rows < 10_000:
        raise ValueError(
            "GEO count matrix has fewer than 10,000 gene rows."
        )
    if any(value <= 0 for value in library_sizes):
        raise ValueError(
            "GEO count matrix contains an empty selected library."
        )

    with open_expression_text(source) as input_handle, target.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as output_handle:
        reader = csv.reader(input_handle, delimiter=delimiter)
        next(reader)
        writer = csv.writer(
            output_handle,
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writerow([normalized_feature_column, *sample_ids])
        written_rows = 0
        for row in reader:
            if not row:
                continue
            raw_feature = row[feature_index].strip()
            if not raw_feature:
                continue
            feature = normalize_geo_count_feature(
                raw_feature,
                delimiter=feature_split_delimiter,
                part_indexes=feature_part_indexes,
                expected_parts=expected_feature_parts,
            )
            if should_drop_geo_count_row(
                row,
                indexes,
                feature,
                missing_value_tokens=normalized_missing_tokens,
                drop_all_missing_features=drop_all_missing_features,
            ):
                continue
            values = parse_geo_counts(
                row,
                indexes,
                feature,
                require_integer=count_value_type == "integer",
            )
            normalized = [
                math.log2(
                    (value / library_size) * 1_000_000.0 + 1.0
                )
                for value, library_size in zip(
                    values,
                    library_sizes,
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
        "source_expression_layout": "wide_gene_counts",
        "source_expression_columns": (
            len(header) - sample_start_index
        ),
        "selected_expression_columns": len(sample_ids),
        "source_expression_gene_rows": gene_rows,
        "normalized_expression_gene_rows": written_rows,
        "source_expression_feature_column": header[feature_index],
        "source_expression_feature_column_index": feature_index + 1,
        "normalized_expression_feature_column": normalized_feature_column,
        "source_expression_sample_start_column": sample_start_column,
        "source_expression_feature_split_delimiter": (
            feature_split_delimiter
        ),
        "source_expression_feature_part_indexes": feature_part_indexes,
        "source_expression_expected_feature_parts": (
            expected_feature_parts
        ),
        "source_expression_count_value_type": count_value_type,
        "source_expression_dropped_all_missing_features": (
            dropped_all_missing_features
        ),
        "source_expression_missing_value_tokens": sorted(
            normalized_missing_tokens
        ),
        "expression_normalization": "log2(CPM + 1)",
        "expression_library_sizes": {
            sample_id: format(value, ".17g")
            for sample_id, value in zip(
                sample_ids,
                library_sizes,
                strict=True,
            )
        },
    }


def should_drop_geo_count_row(
    row: list[str],
    indexes: list[int],
    feature: str,
    *,
    missing_value_tokens: set[str],
    drop_all_missing_features: bool,
) -> bool:
    if not missing_value_tokens:
        return False
    missing = [
        row[index].strip() in missing_value_tokens
        for index in indexes
    ]
    if not any(missing):
        return False
    if drop_all_missing_features and all(missing):
        return True
    raise ValueError(
        "GEO count matrix contains partially missing selected values at "
        f"{feature!r}; count values are never imputed."
    )


def normalize_geo_count_feature(
    feature: str,
    *,
    delimiter: str,
    part_indexes: list[int],
    expected_parts: int | None,
) -> str:
    if not delimiter:
        return feature
    parts = feature.split(delimiter)
    if expected_parts is not None and len(parts) != expected_parts:
        raise ValueError(
            "GEO count-matrix feature has an unexpected number of "
            f"parts: {feature!r}."
        )
    if max(part_indexes) > len(parts):
        raise ValueError(
            "GEO count-matrix feature-part index falls outside "
            f"{feature!r}."
        )
    selected = [
        parts[index - 1].strip()
        for index in part_indexes
    ]
    if any(not value for value in selected):
        raise ValueError(
            f"GEO count-matrix feature has an empty selected part: "
            f"{feature!r}."
        )
    return "|".join(selected)


def materialize_geo_featurecounts_tar(
    source: Path,
    target: Path,
    samples: list[dict[str, str]],
    *,
    feature_column: str,
    feature_column_output: str,
    count_column_index: int,
    supplementary_file_pattern: re.Pattern[str],
    minimum_gene_rows: int = 10_000,
) -> dict[str, Any]:
    if (
        len(samples) < 10
        or not feature_column
        or not feature_column_output
        or count_column_index < 2
        or minimum_gene_rows < 1
    ):
        raise ValueError(
            "GEO featureCounts tar materialization requires at least ten "
            "samples and valid feature/count columns."
        )
    sample_ids = [str(sample["sample_id"]) for sample in samples]
    expected_members = [
        str(sample["member_name"]) for sample in samples
    ]
    if (
        len(sample_ids) != len(set(sample_ids))
        or len(expected_members) != len(set(expected_members))
    ):
        raise ValueError(
            "GEO featureCounts samples and archive members must be unique."
        )

    with tarfile.open(source, mode="r:*") as archive:
        members_by_name: dict[str, tarfile.TarInfo] = {}
        duplicate_members: set[str] = set()
        matching_members = 0
        for member in archive.getmembers():
            path = PurePosixPath(member.name)
            if path.is_absolute() or ".." in path.parts:
                raise ValueError(
                    "GEO expression tar contains an unsafe member path."
                )
            if not member.isfile():
                continue
            name = path.name
            if name in members_by_name:
                duplicate_members.add(name)
            members_by_name[name] = member
            if supplementary_file_pattern.fullmatch(name):
                matching_members += 1
        if duplicate_members:
            raise ValueError(
                "GEO expression tar contains duplicate member names: "
                f"{sorted(duplicate_members)[:5]}."
            )
        missing_members = [
            name for name in expected_members if name not in members_by_name
        ]
        if missing_members:
            raise ValueError(
                "GEO featureCounts files are absent from the expression "
                f"tar: {missing_members[:5]}."
            )

        gene_ids: list[str] = []
        seen_gene_ids: set[str] = set()
        counts_by_sample: list[array] = []
        library_sizes: list[int] = []
        source_count_columns: dict[str, str] = {}
        source_headers: list[str] | None = None
        for sample_index, (sample_id, member_name) in enumerate(
            zip(sample_ids, expected_members, strict=True)
        ):
            member_handle = archive.extractfile(
                members_by_name[member_name]
            )
            if member_handle is None:
                raise ValueError(
                    f"GEO tar member {member_name!r} cannot be read."
                )
            with member_handle:
                with gzip.GzipFile(fileobj=member_handle) as gzip_handle:
                    with io.TextIOWrapper(
                        gzip_handle,
                        encoding="utf-8",
                        errors="strict",
                        newline="",
                    ) as text_handle:
                        reader = csv.reader(
                            (
                                line
                                for line in text_handle
                                if line.strip()
                            ),
                            delimiter="\t",
                        )
                        header = next(
                            (
                                row
                                for row in reader
                                if row
                                and not row[0].lstrip().startswith("#")
                            ),
                            None,
                        )
                        if header is None:
                            raise ValueError(
                                f"GEO featureCounts file {member_name!r} "
                                "is empty."
                            )
                        if len(header) != len(set(header)):
                            raise ValueError(
                                f"GEO featureCounts file {member_name!r} "
                                "contains duplicate header columns."
                            )
                        try:
                            feature_index = header.index(feature_column)
                        except ValueError as error:
                            raise ValueError(
                                "GEO featureCounts feature column "
                                f"{feature_column!r} is absent."
                            ) from error
                        count_index = count_column_index - 1
                        if (
                            count_index >= len(header)
                            or count_index == feature_index
                            or not header[count_index].strip()
                        ):
                            raise ValueError(
                                "GEO featureCounts count_column_index is "
                                "invalid."
                            )
                        structural_header = [
                            value
                            for index, value in enumerate(header)
                            if index != count_index
                        ]
                        if source_headers is None:
                            source_headers = structural_header
                        elif source_headers != structural_header:
                            raise ValueError(
                                "GEO featureCounts structural columns "
                                "differ between samples."
                            )
                        source_count_columns[sample_id] = (
                            header[count_index].strip()
                        )
                        counts = array("Q")
                        row_count = 0
                        for row in reader:
                            if len(row) != len(header):
                                raise ValueError(
                                    "GEO featureCounts row width is "
                                    f"inconsistent in {member_name!r}."
                                )
                            gene_id = row[feature_index].strip()
                            if not gene_id:
                                raise ValueError(
                                    "GEO featureCounts contains an empty "
                                    "feature ID."
                                )
                            try:
                                count = int(row[count_index])
                            except ValueError as error:
                                raise ValueError(
                                    "GEO featureCounts contains a "
                                    f"non-integer count in {member_name!r}."
                                ) from error
                            if count < 0:
                                raise ValueError(
                                    "GEO featureCounts contains a negative "
                                    f"count in {member_name!r}."
                                )
                            if sample_index == 0:
                                if gene_id in seen_gene_ids:
                                    raise ValueError(
                                        "GEO featureCounts repeats feature "
                                        f"{gene_id!r}."
                                    )
                                seen_gene_ids.add(gene_id)
                                gene_ids.append(gene_id)
                            elif (
                                row_count >= len(gene_ids)
                                or gene_ids[row_count] != gene_id
                            ):
                                raise ValueError(
                                    "GEO featureCounts feature order "
                                    "differs between samples."
                                )
                            counts.append(count)
                            row_count += 1
            if len(counts) != len(gene_ids):
                raise ValueError(
                    "GEO featureCounts samples have different gene counts."
                )
            library_size = sum(counts)
            if library_size <= 0:
                raise ValueError(
                    f"GEO featureCounts library {member_name!r} is empty."
                )
            counts_by_sample.append(counts)
            library_sizes.append(library_size)
        if len(gene_ids) < minimum_gene_rows:
            raise ValueError(
                "GEO featureCounts tar has fewer than 10,000 gene rows."
            )

        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open(
            "w", newline="", encoding="utf-8"
        ) as output_handle:
            writer = csv.writer(
                output_handle,
                delimiter="\t",
                lineterminator="\n",
            )
            writer.writerow([feature_column_output, *sample_ids])
            for row_index, gene_id in enumerate(gene_ids):
                writer.writerow(
                    [
                        gene_id,
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
                                ".17g",
                            )
                            for counts, library_size in zip(
                                counts_by_sample,
                                library_sizes,
                                strict=True,
                            )
                        ],
                    ]
                )

    return {
        "source_expression_layout": "featurecounts_tar",
        "source_expression_columns": matching_members,
        "selected_expression_columns": len(samples),
        "source_expression_gene_rows": len(gene_ids),
        "normalized_expression_gene_rows": len(gene_ids),
        "source_expression_feature_column": feature_column,
        "normalized_expression_feature_column": feature_column_output,
        "source_expression_count_column_index": count_column_index,
        "source_expression_selected_members": {
            sample_id: member_name
            for sample_id, member_name in zip(
                sample_ids,
                expected_members,
                strict=True,
            )
        },
        "source_expression_count_columns": source_count_columns,
        "expression_normalization": "log2(CPM + 1)",
        "expression_library_sizes": {
            sample_id: str(library_size)
            for sample_id, library_size in zip(
                sample_ids,
                library_sizes,
                strict=True,
            )
        },
    }


def materialize_geo_transcript_count_files_tar(
    source: Path,
    target: Path,
    samples: list[dict[str, str]],
    *,
    feature_column: str,
    count_column: str,
    supplementary_file_pattern: re.Pattern[str],
    minimum_transcript_rows: int = 10_000,
) -> dict[str, Any]:
    if (
        len(samples) < 10
        or not feature_column
        or not count_column
        or feature_column == count_column
        or minimum_transcript_rows < 1
    ):
        raise ValueError(
            "GEO transcript-count tar materialization requires at least "
            "ten samples and distinct feature/count columns."
        )
    sample_ids = [str(sample["sample_id"]) for sample in samples]
    expected_members = [
        str(sample["member_name"]) for sample in samples
    ]
    if (
        len(sample_ids) != len(set(sample_ids))
        or len(expected_members) != len(set(expected_members))
    ):
        raise ValueError(
            "GEO transcript-count samples and archive members must be "
            "unique."
        )

    with tarfile.open(source, mode="r:*") as archive:
        members_by_name: dict[str, tarfile.TarInfo] = {}
        duplicate_members: set[str] = set()
        matching_members = 0
        for member in archive.getmembers():
            path = PurePosixPath(member.name)
            if path.is_absolute() or ".." in path.parts:
                raise ValueError(
                    "GEO expression tar contains an unsafe member path."
                )
            if not member.isfile():
                continue
            name = path.name
            if name in members_by_name:
                duplicate_members.add(name)
            members_by_name[name] = member
            if supplementary_file_pattern.fullmatch(name):
                matching_members += 1
        if duplicate_members:
            raise ValueError(
                "GEO expression tar contains duplicate member names: "
                f"{sorted(duplicate_members)[:5]}."
            )
        missing_members = [
            name for name in expected_members if name not in members_by_name
        ]
        if missing_members:
            raise ValueError(
                "GEO transcript-count files are absent from the expression "
                f"tar: {missing_members[:5]}."
            )

        transcript_ids: list[str] = []
        seen_transcript_ids: set[str] = set()
        counts_by_sample: list[array] = []
        source_headers: list[str] | None = None
        for sample_index, member_name in enumerate(expected_members):
            member_handle = archive.extractfile(
                members_by_name[member_name]
            )
            if member_handle is None:
                raise ValueError(
                    f"GEO tar member {member_name!r} cannot be read."
                )
            with member_handle:
                with gzip.GzipFile(fileobj=member_handle) as gzip_handle:
                    with io.TextIOWrapper(
                        gzip_handle,
                        encoding="utf-8",
                        errors="strict",
                        newline="",
                    ) as text_handle:
                        reader = csv.reader(
                            (
                                line
                                for line in text_handle
                                if line.strip()
                            ),
                            delimiter="\t",
                        )
                        header = next(reader, None)
                        if header is None:
                            raise ValueError(
                                "GEO transcript-count file "
                                f"{member_name!r} is empty."
                            )
                        if (
                            len(header) != len(set(header))
                            or feature_column not in header
                            or count_column not in header
                        ):
                            raise ValueError(
                                "GEO transcript-count files require unique "
                                "headers containing the configured feature "
                                "and count columns."
                            )
                        if source_headers is None:
                            source_headers = header
                        elif source_headers != header:
                            raise ValueError(
                                "GEO transcript-count headers differ "
                                "between samples."
                            )
                        feature_index = header.index(feature_column)
                        count_index = header.index(count_column)
                        counts = array("d")
                        row_count = 0
                        for row in reader:
                            if len(row) != len(header):
                                raise ValueError(
                                    "GEO transcript-count row width is "
                                    f"inconsistent in {member_name!r}."
                                )
                            raw_transcript = row[feature_index].strip()
                            transcript_id = raw_transcript.split(".", 1)[0]
                            if not transcript_id.startswith("ENST"):
                                raise ValueError(
                                    "GEO transcript-count feature is not "
                                    "an Ensembl transcript ID: "
                                    f"{raw_transcript!r}."
                                )
                            try:
                                count = float(row[count_index])
                            except ValueError as error:
                                raise ValueError(
                                    "GEO transcript-count file contains a "
                                    f"non-numeric count in {member_name!r}."
                                ) from error
                            if not math.isfinite(count) or count < 0:
                                raise ValueError(
                                    "GEO transcript-count file contains an "
                                    f"invalid count in {member_name!r}."
                                )
                            if sample_index == 0:
                                if transcript_id in seen_transcript_ids:
                                    raise ValueError(
                                        "GEO transcript-count file repeats "
                                        f"transcript {transcript_id!r}."
                                    )
                                seen_transcript_ids.add(transcript_id)
                                transcript_ids.append(raw_transcript)
                            elif (
                                row_count >= len(transcript_ids)
                                or transcript_ids[row_count]
                                != raw_transcript
                            ):
                                raise ValueError(
                                    "GEO transcript-count feature order "
                                    "differs between samples."
                                )
                            counts.append(count)
                            row_count += 1
            if len(counts) != len(transcript_ids):
                raise ValueError(
                    "GEO transcript-count samples have different feature "
                    "counts."
                )
            if sum(counts) <= 0:
                raise ValueError(
                    f"GEO transcript-count library {member_name!r} is empty."
                )
            counts_by_sample.append(counts)
        if len(transcript_ids) < minimum_transcript_rows:
            raise ValueError(
                "GEO transcript-count tar has fewer than 10,000 "
                "transcript rows."
            )

        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open(
            "w", newline="", encoding="utf-8"
        ) as output_handle:
            writer = csv.writer(
                output_handle,
                delimiter="\t",
                lineterminator="\n",
            )
            writer.writerow([feature_column, *sample_ids])
            for row_index, transcript_id in enumerate(transcript_ids):
                writer.writerow(
                    [
                        transcript_id,
                        *[
                            format(counts[row_index], ".17g")
                            for counts in counts_by_sample
                        ],
                    ]
                )

    return {
        "source_expression_layout": "transcript_count_files_tar",
        "source_expression_columns": matching_members,
        "selected_expression_columns": len(samples),
        "source_expression_transcript_rows": len(transcript_ids),
        "source_expression_feature_column": feature_column,
        "source_expression_count_column": count_column,
        "source_expression_selected_members": {
            sample_id: member_name
            for sample_id, member_name in zip(
                sample_ids,
                expected_members,
                strict=True,
            )
        },
    }


def materialize_geo_normalized_files_tar(
    source: Path,
    target: Path,
    samples: list[dict[str, str]],
    *,
    feature_column: str,
    feature_column_output: str,
    value_column_index: int,
    supplementary_file_pattern: re.Pattern[str],
    value_transform: str = "identity",
    duplicate_feature_policy: str = "error",
    duplicate_feature_case_insensitive: bool = False,
    feature_order_policy: str = "strict",
    require_nonnegative: bool = False,
    require_value_header_matches_sample_id: bool = False,
    minimum_gene_rows: int = 10_000,
) -> dict[str, Any]:
    if (
        len(samples) < 10
        or not feature_column
        or not feature_column_output
        or value_column_index < 2
        or value_transform not in {"identity", "log2p"}
        or duplicate_feature_policy
        not in {"error", "exclude_ambiguous"}
        or feature_order_policy not in {"strict", "align"}
        or minimum_gene_rows < 1
    ):
        raise ValueError(
            "GEO normalized-file tar materialization requires at least "
            "ten samples, valid feature/value columns, an identity or "
            "log2p transform and supported duplicate-feature/order "
            "policies."
        )
    sample_ids = [str(sample["sample_id"]) for sample in samples]
    expected_members = [
        str(sample["member_name"]) for sample in samples
    ]
    if (
        len(sample_ids) != len(set(sample_ids))
        or len(expected_members) != len(set(expected_members))
    ):
        raise ValueError(
            "GEO normalized-file samples and archive members must be "
            "unique."
        )

    with tarfile.open(source, mode="r:*") as archive:
        members_by_name: dict[str, tarfile.TarInfo] = {}
        duplicate_members: set[str] = set()
        matching_members = 0
        for member in archive.getmembers():
            path = PurePosixPath(member.name)
            if path.is_absolute() or ".." in path.parts:
                raise ValueError(
                    "GEO expression tar contains an unsafe member path."
                )
            if not member.isfile():
                continue
            name = path.name
            if name in members_by_name:
                duplicate_members.add(name)
            members_by_name[name] = member
            if supplementary_file_pattern.fullmatch(name):
                matching_members += 1
        if duplicate_members:
            raise ValueError(
                "GEO expression tar contains duplicate member names: "
                f"{sorted(duplicate_members)[:5]}."
            )
        missing_members = [
            name for name in expected_members if name not in members_by_name
        ]
        if missing_members:
            raise ValueError(
                "GEO normalized files are absent from the expression "
                f"tar: {missing_members[:5]}."
            )

        gene_ids: list[str] = []
        values_by_sample: list[array] = []
        source_value_columns: dict[str, str] = {}
        structural_header: list[str] | None = None
        for sample_index, (sample_id, member_name) in enumerate(
            zip(sample_ids, expected_members, strict=True)
        ):
            member_handle = archive.extractfile(
                members_by_name[member_name]
            )
            if member_handle is None:
                raise ValueError(
                    f"GEO tar member {member_name!r} cannot be read."
                )
            with member_handle:
                with gzip.GzipFile(fileobj=member_handle) as gzip_handle:
                    with io.TextIOWrapper(
                        gzip_handle,
                        encoding="utf-8",
                        errors="strict",
                        newline="",
                    ) as text_handle:
                        reader = csv.reader(
                            (
                                line
                                for line in text_handle
                                if line.strip()
                            ),
                            delimiter="\t",
                        )
                        try:
                            header = next(reader)
                        except StopIteration as error:
                            raise ValueError(
                                f"GEO normalized file {member_name!r} "
                                "is empty."
                            ) from error
                        if len(header) != len(set(header)):
                            raise ValueError(
                                "GEO normalized-file header contains "
                                "duplicate columns."
                            )
                        try:
                            feature_index = header.index(feature_column)
                        except ValueError as error:
                            raise ValueError(
                                "GEO normalized-file feature column "
                                f"{feature_column!r} is absent."
                            ) from error
                        value_index = value_column_index - 1
                        if (
                            value_index >= len(header)
                            or value_index == feature_index
                            or not header[value_index].strip()
                        ):
                            raise ValueError(
                                "GEO normalized-file value_column_index "
                                "is invalid."
                            )
                        current_structural_header = [
                            value
                            for index, value in enumerate(header)
                            if index != value_index
                        ]
                        if structural_header is None:
                            structural_header = current_structural_header
                        elif (
                            structural_header
                            != current_structural_header
                        ):
                            raise ValueError(
                                "GEO normalized-file structural columns "
                                "differ between samples."
                            )
                        source_value_column = header[value_index].strip()
                        if (
                            require_value_header_matches_sample_id
                            and source_value_column != sample_id
                        ):
                            raise ValueError(
                                "GEO normalized-file value header does "
                                "not match its linked sample ID."
                            )
                        source_value_columns[sample_id] = (
                            source_value_column
                        )

                        values = array("d")
                        current_gene_ids: list[str] = []
                        for row in reader:
                            if len(row) != len(header):
                                raise ValueError(
                                    "GEO normalized-file row width is "
                                    f"inconsistent in {member_name!r}."
                                )
                            gene_id = row[feature_index].strip()
                            if not gene_id:
                                raise ValueError(
                                    "GEO normalized file contains an "
                                    "empty feature ID."
                                )
                            try:
                                value = float(row[value_index])
                            except ValueError as error:
                                raise ValueError(
                                    "GEO normalized file contains a "
                                    f"non-numeric value in {member_name!r}."
                                ) from error
                            if (
                                not math.isfinite(value)
                                or (
                                    require_nonnegative
                                    and value < 0
                                )
                                or (
                                    value_transform == "log2p"
                                    and value < 0
                                )
                            ):
                                raise ValueError(
                                    "GEO normalized file contains an "
                                    f"invalid value in {member_name!r}."
                                )
                            if value_transform == "log2p":
                                value = math.log2(value + 1.0)
                            current_gene_ids.append(gene_id)
                            values.append(value)
            if sample_index == 0:
                gene_ids = current_gene_ids
            elif feature_order_policy == "strict":
                if current_gene_ids != gene_ids:
                    raise ValueError(
                        "GEO normalized-file feature order differs "
                        "between samples."
                    )
            else:
                reference_keys = [
                    (
                        gene_id.casefold()
                        if duplicate_feature_case_insensitive
                        else gene_id
                    )
                    for gene_id in gene_ids
                ]
                current_keys = [
                    (
                        gene_id.casefold()
                        if duplicate_feature_case_insensitive
                        else gene_id
                    )
                    for gene_id in current_gene_ids
                ]
                reference_counts: dict[str, int] = {}
                current_counts: dict[str, int] = {}
                current_indexes: dict[str, int] = {}
                for key in reference_keys:
                    reference_counts[key] = (
                        reference_counts.get(key, 0) + 1
                    )
                for index, key in enumerate(current_keys):
                    current_counts[key] = current_counts.get(key, 0) + 1
                    current_indexes.setdefault(key, index)
                if current_counts != reference_counts:
                    raise ValueError(
                        "GEO normalized files contain different feature "
                        "multisets."
                    )
                values = array(
                    "d",
                    (
                        values[current_indexes[key]]
                        for key in reference_keys
                    ),
                )
            if len(values) != len(gene_ids):
                raise ValueError(
                    "GEO normalized-file samples have different gene "
                    "counts."
                )
            values_by_sample.append(values)

    feature_counts: dict[str, int] = {}
    for gene_id in gene_ids:
        key = (
            gene_id.casefold()
            if duplicate_feature_case_insensitive
            else gene_id
        )
        feature_counts[key] = feature_counts.get(key, 0) + 1
    duplicate_features = {
        feature
        for feature, count in feature_counts.items()
        if count > 1
    }
    duplicate_feature_rows = sum(
        feature_counts[feature]
        for feature in duplicate_features
    )
    if duplicate_features and duplicate_feature_policy == "error":
        raise ValueError(
            "GEO normalized files repeat features: "
            f"{sorted(duplicate_features)[:5]}."
        )
    retained_indexes = [
        index
        for index, gene_id in enumerate(gene_ids)
        if (
            gene_id.casefold()
            if duplicate_feature_case_insensitive
            else gene_id
        )
        not in duplicate_features
    ]
    if len(retained_indexes) < minimum_gene_rows:
        raise ValueError(
            "GEO normalized-file tar has fewer than 10,000 gene rows."
        )

    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open(
        "w", newline="", encoding="utf-8"
    ) as output_handle:
        writer = csv.writer(
            output_handle,
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writerow([feature_column_output, *sample_ids])
        for row_index in retained_indexes:
            writer.writerow(
                [
                    gene_ids[row_index],
                    *[
                        format(values[row_index], ".17g")
                        for values in values_by_sample
                    ],
                ]
            )

    return {
        "source_expression_layout": "normalized_files_tar",
        "source_expression_columns": matching_members,
        "selected_expression_columns": len(samples),
        "source_expression_gene_rows": len(gene_ids),
        "normalized_expression_gene_rows": len(retained_indexes),
        "source_expression_feature_column": feature_column,
        "normalized_expression_feature_column": feature_column_output,
        "source_expression_value_column_index": value_column_index,
        "source_expression_selected_members": {
            sample_id: member_name
            for sample_id, member_name in zip(
                sample_ids,
                expected_members,
                strict=True,
            )
        },
        "source_expression_value_columns": source_value_columns,
        "source_expression_value_transform": value_transform,
        "source_expression_require_nonnegative": require_nonnegative,
        "source_expression_duplicate_feature_policy": (
            duplicate_feature_policy
        ),
        "source_expression_duplicate_feature_case_insensitive": (
            duplicate_feature_case_insensitive
        ),
        "source_expression_feature_order_policy": feature_order_policy,
        "source_expression_duplicate_feature_symbols": len(
            duplicate_features
        ),
        "source_expression_duplicate_feature_rows": duplicate_feature_rows,
        "source_expression_excluded_duplicate_feature_rows": (
            duplicate_feature_rows
            if duplicate_feature_policy == "exclude_ambiguous"
            else 0
        ),
        "expression_normalization": (
            "log2(source normalized value + 1)"
            if value_transform == "log2p"
            else "source normalized value"
        ),
    }


def parse_geo_counts(
    row: list[str],
    indexes: list[int],
    feature: str,
    *,
    require_integer: bool = True,
) -> list[float]:
    try:
        values = [float(row[index]) for index in indexes]
    except (IndexError, TypeError, ValueError) as error:
        raise ValueError(
            f"GEO count matrix has a non-numeric value at {feature!r}."
        ) from error
    if any(
        not math.isfinite(value)
        or value < 0
        or (require_integer and not value.is_integer())
        for value in values
    ):
        raise ValueError(
            "GEO count matrix requires finite non-negative "
            f"{'integer ' if require_integer else ''}values at "
            f"{feature!r}."
        )
    return values


def parse_geo_normalized_values(
    row: list[str],
    indexes: list[int],
    feature: str,
    *,
    allow_negative_values: bool = False,
) -> list[float]:
    try:
        values = [float(row[index]) for index in indexes]
    except (IndexError, TypeError, ValueError) as error:
        raise ValueError(
            "GEO normalized matrix has a non-numeric value at "
            f"{feature!r}."
        ) from error
    if any(
        not math.isfinite(value)
        or (value < 0 and not allow_negative_values)
        for value in values
    ):
        raise ValueError(
            "GEO normalized matrix requires finite "
            f"{'values' if allow_negative_values else 'non-negative values'} "
            f"at {feature!r}."
        )
    return values


def expression_delimiter(path: Path) -> str:
    suffixes = [suffix.lower() for suffix in path.suffixes]
    return "," if ".csv" in suffixes else "\t"


def read_compressed_header(path: Path) -> list[str]:
    with open_expression_text(path) as handle:
        return next(csv.reader(handle, delimiter=expression_delimiter(path)))


def open_expression_text(path: Path):
    if path.suffix.lower() == ".gz":
        return gzip.open(
            path,
            mode="rt",
            newline="",
            encoding="utf-8",
            errors="strict",
        )
    return path.open(
        newline="",
        encoding="utf-8",
        errors="strict",
    )


def read_compressed_csv_header(path: Path) -> list[str]:
    return read_compressed_header(path)


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
