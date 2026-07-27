from __future__ import annotations

import csv
from concurrent.futures import ThreadPoolExecutor
import hashlib
from itertools import zip_longest
import json
import math
from pathlib import Path
import shutil
from typing import Any, Iterable, Iterator
import urllib.parse

from app.repository.adapters.cbioportal import (
    GDC_API,
    download,
    fetch_gdc_project_survival,
    request_json,
    write_tsv,
)
from app.repository.storage import sha256_file


GDC_ADAPTER_VERSION = "gdc_star_counts_v1"
STAR_FILE_FIELDS = ",".join(
    [
        "file_id",
        "file_name",
        "md5sum",
        "file_size",
        "data_release",
        "updated_datetime",
        "analysis.workflow_type",
        "associated_entities.entity_id",
        "associated_entities.entity_submitter_id",
        "associated_entities.entity_type",
        "cases.case_id",
        "cases.submitter_id",
        "cases.samples.sample_id",
        "cases.samples.submitter_id",
        "cases.samples.sample_type",
        "cases.samples.tissue_type",
        "cases.samples.portions.portion_id",
        "cases.samples.portions.submitter_id",
        "cases.samples.portions.analytes.analyte_id",
        "cases.samples.portions.analytes.submitter_id",
        "cases.samples.portions.analytes.aliquots.aliquot_id",
        "cases.samples.portions.analytes.aliquots.submitter_id",
    ]
)
DEFAULT_SAMPLE_TYPE_PRIORITY = [
    "Primary Tumor",
    "Recurrent Tumor",
    "Metastatic",
    "Tumor",
]
DISALLOWED_PROJECT_PREFIXES = ("TCGA-", "TARGET-", "PCAWG-")


def materialize_gdc_source(
    spec: dict[str, Any],
    source_dir: Path,
) -> tuple[dict[str, Path], str, str | None, dict[str, Any]]:
    source_spec = spec["source"]
    project_id = str(source_spec.get("project_id") or "").strip()
    license_url = str(source_spec.get("license_evidence_url") or "").strip()
    if not project_id or not license_url:
        raise ValueError(
            "GDC API sources require project_id and license_evidence_url."
        )
    if project_id.upper().startswith(DISALLOWED_PROJECT_PREFIXES):
        raise ValueError(
            "Direct GDC repository releases must be independent of TCGA, "
            "TARGET and PCAWG."
        )

    sample_type_priority = [
        str(value).strip()
        for value in (
            source_spec.get("sample_type_priority")
            or DEFAULT_SAMPLE_TYPE_PRIORITY
        )
        if str(value).strip()
    ]
    if not sample_type_priority:
        raise ValueError("sample_type_priority cannot be empty.")

    license_path = source_dir / "GDC_POLICIES.html"
    download(license_url, license_path)
    project_payload = request_json(
        f"{GDC_API}/projects/{urllib.parse.quote(project_id, safe='')}"
    )
    status_payload = request_json(f"{GDC_API}/status")
    files_payload = fetch_gdc_star_files(project_id)
    cases_payload = fetch_gdc_cases(project_id)
    survival_payload = fetch_gdc_project_survival(project_id)

    project = payload_data(project_payload)
    if str(project.get("project_id") or "") != project_id:
        raise ValueError("GDC returned metadata for a different project.")
    file_hits = payload_hits(files_payload, "files")
    case_hits = payload_hits(cases_payload, "cases")
    cases_by_submitter_id = {
        str(case.get("submitter_id") or "").strip(): case
        for case in case_hits
        if str(case.get("submitter_id") or "").strip()
    }
    case_eligibility_rules = (
        source_spec.get("case_eligibility_rules") or []
    )
    eligible_case_ids = {
        patient_id
        for patient_id, case in cases_by_submitter_id.items()
        if gdc_case_passes_eligibility(case, case_eligibility_rules)
    }
    survival_by_patient = usable_gdc_survival(
        survival_payload, project_id=project_id
    )
    selected_files, selection_summary = select_gdc_expression_files(
        file_hits,
        set(survival_by_patient),
        sample_type_priority=sample_type_priority,
        eligible_patient_ids=eligible_case_ids,
    )
    if len(selected_files) < 10:
        raise ValueError(
            "Fewer than 10 GDC expression patients have usable survival."
        )

    missing_cases = sorted(
        {
            record["patient_id"]
            for record in selected_files
            if record["patient_id"] not in cases_by_submitter_id
        }
    )
    if missing_cases:
        raise ValueError(
            "Selected GDC expression patients are absent from case metadata: "
            f"{missing_cases[:5]}"
        )

    raw_dir = source_dir / "raw_star_counts"
    raw_dir.mkdir()
    raw_paths_by_file_id = download_selected_gdc_files(
        selected_files,
        raw_dir,
        max_workers=int(source_spec.get("download_workers") or 4),
    )

    patient_rows = []
    sample_rows = []
    for record in selected_files:
        patient_id = record["patient_id"]
        case = cases_by_submitter_id[patient_id]
        survival = survival_by_patient[patient_id]
        diagnosis = select_primary_diagnosis(case.get("diagnoses") or [])
        demographic = case.get("demographic") or {}
        patient_rows.append(
            {
                "PATIENT_ID": patient_id,
                "GDC_CASE_ID": record["case_id"],
                "GDC_PROJECT_ID": project_id,
                "GDC_OS_DAYS": format(survival["time_days"], ".17g"),
                "GDC_OS_STATUS": (
                    "1:DECEASED" if survival["event"] else "0:CENSORED"
                ),
                "STAGE": first_nonmissing(
                    diagnosis,
                    [
                        "ajcc_pathologic_stage",
                        "ajcc_clinical_stage",
                        "figo_stage",
                        "ann_arbor_pathologic_stage",
                        "ann_arbor_clinical_stage",
                    ],
                ),
                "GRADE": first_nonmissing(
                    diagnosis,
                    [
                        "tumor_grade",
                        "gleason_grade_group",
                        "inpc_grade",
                    ],
                ),
                "SEX": clean_value(
                    demographic.get("sex_at_birth")
                    or demographic.get("gender")
                ),
                "RACE": clean_value(demographic.get("race")),
                "AGE_AT_INDEX": resolve_age_at_index(
                    demographic, diagnosis
                ),
                "PRIMARY_SITE": clean_value(case.get("primary_site")),
                "DISEASE_TYPE": clean_value(case.get("disease_type")),
                "SELECTED_DIAGNOSIS_ID": clean_value(
                    diagnosis.get("diagnosis_id")
                ),
                "GDC_CASE_METADATA_JSON": canonical_json(case),
            }
        )
        sample_rows.append(
            {
                "SAMPLE_ID": record["sample_id"],
                "PATIENT_ID": patient_id,
                "SAMPLE_TYPE": record["sample_type"],
                "TISSUE_TYPE": record["tissue_type"],
                "GDC_FILE_ID": record["file_id"],
                "GDC_FILE_NAME": record["file_name"],
                "GDC_SAMPLE_ID": record["sample_uuid"],
                "GDC_ALIQUOT_ID": record["aliquot_id"],
                "GDC_ALIQUOT_SUBMITTER_ID": record[
                    "aliquot_submitter_id"
                ],
                "GDC_LINKED_SAMPLE_CANDIDATES": record[
                    "linked_sample_candidates"
                ],
                "GDC_FILE_METADATA_JSON": canonical_json(
                    record["source_record"]
                ),
            }
        )

    patient_table = source_dir / "data_clinical_patient.txt"
    sample_table = source_dir / "data_clinical_sample.txt"
    write_tsv(
        patient_table,
        patient_rows,
        [
            "PATIENT_ID",
            "GDC_CASE_ID",
            "GDC_PROJECT_ID",
            "GDC_OS_DAYS",
            "GDC_OS_STATUS",
            "STAGE",
            "GRADE",
            "SEX",
            "RACE",
            "AGE_AT_INDEX",
            "PRIMARY_SITE",
            "DISEASE_TYPE",
            "SELECTED_DIAGNOSIS_ID",
            "GDC_CASE_METADATA_JSON",
        ],
    )
    write_tsv(
        sample_table,
        sample_rows,
        [
            "SAMPLE_ID",
            "PATIENT_ID",
            "SAMPLE_TYPE",
            "TISSUE_TYPE",
            "GDC_FILE_ID",
            "GDC_FILE_NAME",
            "GDC_SAMPLE_ID",
            "GDC_ALIQUOT_ID",
            "GDC_ALIQUOT_SUBMITTER_ID",
            "GDC_LINKED_SAMPLE_CANDIDATES",
            "GDC_FILE_METADATA_JSON",
        ],
    )

    expression_table = source_dir / "data_expression_gdc_tpm.tsv"
    matrix_summary = materialize_gdc_star_tpm_matrix(
        selected_files,
        raw_paths_by_file_id,
        expression_table,
        shard_size=int(source_spec.get("matrix_shard_size") or 32),
    )

    source_paths: dict[str, Path] = {
        "expression": expression_table,
        "patients": patient_table,
        "samples": sample_table,
        "license": license_path,
    }
    json_sources = {
        "gdc_project_api": ("gdc_project_api.json", project_payload),
        "gdc_status_api": ("gdc_status_api.json", status_payload),
        "gdc_files_api": ("gdc_files_api.json", files_payload),
        "gdc_cases_api": ("gdc_cases_api.json", cases_payload),
        "gdc_survival_api": ("gdc_survival_api.json", survival_payload),
        "gdc_selected_files": (
            "gdc_selected_files.json",
            [
                {
                    key: value
                    for key, value in record.items()
                    if key != "source_record"
                }
                for record in selected_files
            ],
        ),
    }
    for role, (filename, payload) in json_sources.items():
        path = source_dir / filename
        path.write_text(canonical_json(payload) + "\n", encoding="utf-8")
        source_paths[role] = path
    for record in selected_files:
        source_paths[f"star_counts_{record['file_id']}"] = (
            raw_paths_by_file_id[record["file_id"]]
        )

    source_hashes = {
        role: sha256_file(path)
        for role, path in sorted(source_paths.items())
    }
    source_snapshot = hashlib.sha256(
        canonical_json(source_hashes).encode("utf-8")
    ).hexdigest()
    release_version = status_payload.get("data_release_version") or {}
    release_date = clean_value(release_version.get("release_date"))
    source_snapshot_date = (
        f"{release_date}T00:00:00Z" if release_date else None
    )
    return (
        source_paths,
        source_snapshot,
        source_snapshot_date,
        {
            "source_api": GDC_API,
            "source_project_id": project_id,
            "gdc_api_version": status_payload.get("tag"),
            "gdc_data_release": status_payload.get("data_release"),
            "gdc_expression_files_discovered": len(file_hits),
            "gdc_expression_patients_discovered": selection_summary[
                "expression_patients"
            ],
            "gdc_survival_patients": len(survival_by_patient),
            "gdc_case_eligibility_rules": case_eligibility_rules,
            "gdc_case_eligible_patients": len(eligible_case_ids),
            "gdc_selected_expression_patients": len(selected_files),
            "gdc_selected_events": sum(
                survival_by_patient[row["patient_id"]]["event"]
                for row in selected_files
            ),
            "gdc_selected_censored": sum(
                1 - survival_by_patient[row["patient_id"]]["event"]
                for row in selected_files
            ),
            "gdc_sample_selection": selection_summary,
            "gdc_star_matrix": matrix_summary,
        },
    )


def fetch_gdc_star_files(project_id: str) -> dict[str, Any]:
    filters = {
        "op": "and",
        "content": [
            equality_filter("cases.project.project_id", [project_id]),
            equality_filter(
                "data_category", ["Transcriptome Profiling"]
            ),
            equality_filter(
                "data_type", ["Gene Expression Quantification"]
            ),
            equality_filter("experimental_strategy", ["RNA-Seq"]),
            equality_filter("analysis.workflow_type", ["STAR - Counts"]),
            equality_filter("access", ["open"]),
        ],
    }
    query = urllib.parse.urlencode(
        {
            "filters": canonical_json(filters),
            "fields": STAR_FILE_FIELDS,
            "expand": "cases.samples.portions.analytes.aliquots",
            "size": 10000,
        }
    )
    return request_json(f"{GDC_API}/files?{query}")


def fetch_gdc_cases(project_id: str) -> dict[str, Any]:
    filters = equality_filter("project.project_id", [project_id])
    query = urllib.parse.urlencode(
        {
            "filters": canonical_json(filters),
            "expand": "demographic,diagnoses,follow_ups,project",
            "size": 10000,
        }
    )
    return request_json(f"{GDC_API}/cases?{query}")


def equality_filter(field: str, values: list[str]) -> dict[str, Any]:
    return {
        "op": "=",
        "content": {"field": field, "value": values},
    }


def payload_data(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("GDC returned a non-object response.")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise ValueError("GDC response has no data object.")
    return data


def payload_hits(payload: Any, label: str) -> list[dict[str, Any]]:
    data = payload_data(payload)
    hits = data.get("hits")
    if not isinstance(hits, list):
        raise ValueError(f"GDC {label} response has no hits array.")
    pagination = data.get("pagination") or {}
    total = int(pagination.get("total") or len(hits))
    if total != len(hits):
        raise ValueError(
            f"GDC {label} response was truncated ({len(hits)}/{total})."
        )
    return hits


def usable_gdc_survival(
    payload: dict[str, Any],
    *,
    project_id: str,
) -> dict[str, dict[str, Any]]:
    by_patient: dict[str, dict[str, Any]] = {}
    for result in payload.get("results") or []:
        for donor in result.get("donors") or []:
            patient_id = str(donor.get("submitter_id") or "").strip()
            if not patient_id:
                continue
            if str(donor.get("project_id") or "") != project_id:
                raise ValueError(
                    "GDC survival response contains another project."
                )
            if patient_id in by_patient:
                raise ValueError(
                    f"Duplicate GDC survival donor {patient_id!r}."
                )
            try:
                time_days = float(donor.get("time"))
            except (TypeError, ValueError):
                continue
            censored = donor.get("censored")
            if (
                not math.isfinite(time_days)
                or time_days <= 0
                or not isinstance(censored, bool)
            ):
                continue
            by_patient[patient_id] = {
                "time_days": time_days,
                "event": int(not censored),
                "case_id": donor.get("id"),
            }
    return by_patient


def select_gdc_expression_files(
    file_hits: Iterable[dict[str, Any]],
    survival_patient_ids: set[str],
    *,
    sample_type_priority: list[str],
    eligible_patient_ids: set[str] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    priority = {
        value.casefold(): index
        for index, value in enumerate(sample_type_priority)
    }
    by_patient: dict[str, list[dict[str, Any]]] = {}
    expression_patients: set[str] = set()
    case_eligible_expression_patients: set[str] = set()
    excluded_sample_types: dict[str, int] = {}
    for hit in file_hits:
        record = normalize_gdc_file_hit(hit)
        patient_id = record["patient_id"]
        expression_patients.add(patient_id)
        if (
            eligible_patient_ids is not None
            and patient_id not in eligible_patient_ids
        ):
            continue
        case_eligible_expression_patients.add(patient_id)
        sample_type_key = record["sample_type"].casefold()
        if sample_type_key not in priority:
            excluded_sample_types[record["sample_type"]] = (
                excluded_sample_types.get(record["sample_type"], 0) + 1
            )
            continue
        if patient_id not in survival_patient_ids:
            continue
        record["sample_type_rank"] = priority[sample_type_key]
        by_patient.setdefault(patient_id, []).append(record)

    selected: list[dict[str, Any]] = []
    duplicate_candidates = 0
    for patient_id in sorted(by_patient):
        candidates = by_patient[patient_id]
        duplicate_candidates += max(0, len(candidates) - 1)
        candidates.sort(
            key=lambda row: (
                row["sample_type_rank"],
                row["sample_id"],
                row["aliquot_submitter_id"],
                row["file_id"],
            )
        )
        selected.append(candidates[0])
    sample_ids = [row["sample_id"] for row in selected]
    if len(sample_ids) != len(set(sample_ids)):
        raise ValueError("Selected GDC sample submitter IDs are not unique.")
    return (
        selected,
        {
            "sample_type_priority": sample_type_priority,
            "expression_patients": len(expression_patients),
            "case_eligible_expression_patients": len(
                case_eligible_expression_patients
            ),
            "survival_expression_overlap": len(by_patient),
            "selected_patients": len(selected),
            "discarded_duplicate_file_candidates": duplicate_candidates,
            "selected_files_with_ambiguous_sample_labels": sum(
                row["linked_sample_candidates"] > 1 for row in selected
            ),
            "excluded_sample_types": excluded_sample_types,
            "tie_break_order": [
                "sample_type_priority",
                "sample_submitter_id",
                "aliquot_submitter_id",
                "file_id",
            ],
        },
    )


def gdc_case_passes_eligibility(
    case: dict[str, Any],
    rules: Any,
) -> bool:
    if not isinstance(rules, list):
        raise ValueError("case_eligibility_rules must be an array.")
    diagnosis = select_primary_diagnosis(case.get("diagnoses") or [])
    demographic = case.get("demographic") or {}
    sources = {
        "case": case,
        "diagnosis": diagnosis,
        "demographic": demographic,
    }
    for rule in rules:
        if not isinstance(rule, dict):
            raise ValueError(
                "Each GDC case eligibility rule must be an object."
            )
        source_name, separator, field = str(
            rule.get("field") or ""
        ).partition(".")
        if (
            not separator
            or source_name not in sources
            or not field
        ):
            raise ValueError(
                "GDC case rule fields must use "
                "case.FIELD, diagnosis.FIELD or demographic.FIELD."
            )
        raw_value = sources[source_name].get(field)
        value = clean_value(raw_value)
        if rule.get("required") and not value:
            return False
        normalized = value.casefold()
        include = {
            str(item).strip().casefold()
            for item in rule.get("include") or []
        }
        exclude = {
            str(item).strip().casefold()
            for item in rule.get("exclude") or []
        }
        if include and normalized not in include:
            return False
        if exclude and normalized in exclude:
            return False
    return True


def normalize_gdc_file_hit(hit: dict[str, Any]) -> dict[str, Any]:
    cases = hit.get("cases") or []
    if len(cases) != 1:
        raise ValueError(
            "Each GDC STAR-counts file must map to exactly one case."
        )
    case = cases[0]
    samples = case.get("samples") or []
    if not samples:
        raise ValueError(
            "Each GDC STAR-counts file must map to at least one sample."
        )
    associated_ids = {
        str(entity.get("entity_id") or "").strip()
        for entity in hit.get("associated_entities") or []
        if str(entity.get("entity_id") or "").strip()
    }
    linked_samples = [
        sample
        for sample in samples
        if associated_ids.intersection(sample_biospecimen_ids(sample))
    ]
    if not linked_samples and len(samples) == 1:
        linked_samples = samples
    if not linked_samples:
        raise ValueError(
            "GDC STAR-counts associated entities cannot be linked to a "
            "sample."
        )
    linked_samples.sort(
        key=lambda row: (
            str(row.get("submitter_id") or ""),
            str(row.get("sample_id") or ""),
        )
    )
    sample = linked_samples[0]
    aliquots = sorted(
        [
            aliquot
            for portion in sample.get("portions") or []
            for analyte in portion.get("analytes") or []
            for aliquot in analyte.get("aliquots") or []
        ],
        key=lambda row: (
            str(row.get("aliquot_id") or "") not in associated_ids,
            str(row.get("submitter_id") or ""),
            str(row.get("aliquot_id") or ""),
        ),
    )
    if not aliquots:
        raise ValueError("GDC STAR-counts file has no linked aliquot.")
    patient_id = str(case.get("submitter_id") or "").strip()
    sample_id = str(sample.get("submitter_id") or "").strip()
    file_id = str(hit.get("file_id") or hit.get("id") or "").strip()
    md5sum = str(hit.get("md5sum") or "").strip().lower()
    if not all((patient_id, sample_id, file_id, md5sum)):
        raise ValueError("GDC STAR-counts metadata is incomplete.")
    return {
        "patient_id": patient_id,
        "case_id": str(case.get("case_id") or "").strip(),
        "sample_id": sample_id,
        "sample_uuid": str(sample.get("sample_id") or "").strip(),
        "sample_type": str(sample.get("sample_type") or "").strip(),
        "tissue_type": str(sample.get("tissue_type") or "").strip(),
        "linked_sample_candidates": len(linked_samples),
        "aliquot_id": str(aliquots[0].get("aliquot_id") or "").strip(),
        "aliquot_submitter_id": str(
            aliquots[0].get("submitter_id") or ""
        ).strip(),
        "file_id": file_id,
        "file_name": str(hit.get("file_name") or "").strip(),
        "file_size": int(hit.get("file_size") or 0),
        "md5sum": md5sum,
        "data_release": hit.get("data_release"),
        "updated_datetime": hit.get("updated_datetime"),
        "source_record": hit,
    }


def sample_biospecimen_ids(sample: dict[str, Any]) -> set[str]:
    identifiers = {
        str(sample.get("sample_id") or "").strip(),
    }
    for portion in sample.get("portions") or []:
        identifiers.add(str(portion.get("portion_id") or "").strip())
        for analyte in portion.get("analytes") or []:
            identifiers.add(str(analyte.get("analyte_id") or "").strip())
            identifiers.update(
                str(aliquot.get("aliquot_id") or "").strip()
                for aliquot in analyte.get("aliquots") or []
            )
    return {value for value in identifiers if value}


def download_selected_gdc_files(
    selected_files: list[dict[str, Any]],
    raw_dir: Path,
    *,
    max_workers: int,
) -> dict[str, Path]:
    if max_workers < 1 or max_workers > 8:
        raise ValueError("download_workers must be between 1 and 8.")

    def retrieve(record: dict[str, Any]) -> tuple[str, Path]:
        file_id = record["file_id"]
        path = raw_dir / f"{file_id}.tsv"
        download(f"{GDC_API}/data/{file_id}", path)
        observed_md5 = md5_file(path)
        if observed_md5 != record["md5sum"]:
            path.unlink(missing_ok=True)
            raise ValueError(
                f"GDC MD5 mismatch for {file_id}: "
                f"{observed_md5} != {record['md5sum']}"
            )
        if record["file_size"] and path.stat().st_size != record["file_size"]:
            path.unlink(missing_ok=True)
            raise ValueError(
                f"GDC file-size mismatch for {file_id}."
            )
        return file_id, path

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        return dict(pool.map(retrieve, selected_files))


def materialize_gdc_star_tpm_matrix(
    selected_files: list[dict[str, Any]],
    raw_paths_by_file_id: dict[str, Path],
    output_path: Path,
    *,
    shard_size: int = 32,
) -> dict[str, Any]:
    if shard_size < 2 or shard_size > 64:
        raise ValueError("matrix_shard_size must be between 2 and 64.")
    shard_dir = output_path.parent / ".gdc_matrix_shards"
    if shard_dir.exists():
        shutil.rmtree(shard_dir)
    shard_dir.mkdir()
    shard_paths: list[Path] = []
    gene_count: int | None = None
    gene_models: set[str] = set()
    try:
        for start in range(0, len(selected_files), shard_size):
            records = selected_files[start : start + shard_size]
            shard_path = shard_dir / f"shard_{start // shard_size:04d}.tsv"
            count, models = write_star_matrix_shard(
                records,
                raw_paths_by_file_id,
                shard_path,
            )
            if gene_count is not None and count != gene_count:
                raise ValueError(
                    "GDC STAR-counts shards contain different gene counts."
                )
            gene_count = count
            gene_models.update(models)
            shard_paths.append(shard_path)
        merge_star_matrix_shards(shard_paths, output_path)
    finally:
        shutil.rmtree(shard_dir, ignore_errors=True)
    return {
        "source_files": len(selected_files),
        "materialized_genes": gene_count or 0,
        "gene_models": sorted(gene_models),
        "source_value_column": "tpm_unstranded",
        "feature_key": "gene_id|gene_name",
        "shard_size": shard_size,
    }


def write_star_matrix_shard(
    records: list[dict[str, Any]],
    raw_paths_by_file_id: dict[str, Path],
    output_path: Path,
) -> tuple[int, set[str]]:
    iterators = []
    gene_models: set[str] = set()
    for record in records:
        path = raw_paths_by_file_id[record["file_id"]]
        iterator, gene_model = gdc_star_tpm_iterator(path)
        iterators.append(iterator)
        if gene_model:
            gene_models.add(gene_model)
    count = 0
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(
            ["Ensembl_Gene_Id|Hugo_Symbol", *[r["sample_id"] for r in records]]
        )
        for rows in zip_longest(*iterators):
            if any(row is None for row in rows):
                raise ValueError(
                    "GDC STAR-counts files contain different gene counts."
                )
            keys = {(row[0], row[1]) for row in rows if row is not None}
            if len(keys) != 1:
                raise ValueError(
                    "GDC STAR-counts files do not share gene order."
                )
            gene_id, gene_name = next(iter(keys))
            writer.writerow(
                [
                    f"{gene_id}|{gene_name}",
                    *[row[2] for row in rows if row is not None],
                ]
            )
            count += 1
    if count < 10_000:
        raise ValueError(
            f"GDC STAR-counts matrix contains only {count} genes."
        )
    return count, gene_models


def merge_star_matrix_shards(
    shard_paths: list[Path],
    output_path: Path,
) -> None:
    handles = [
        path.open(newline="", encoding="utf-8") for path in shard_paths
    ]
    try:
        readers = [csv.reader(handle, delimiter="\t") for handle in handles]
        headers = [next(reader) for reader in readers]
        with output_path.open("w", newline="", encoding="utf-8") as output:
            writer = csv.writer(
                output, delimiter="\t", lineterminator="\n"
            )
            writer.writerow(
                [headers[0][0], *[value for header in headers for value in header[1:]]]
            )
            for rows in zip_longest(*readers):
                if any(row is None for row in rows):
                    raise ValueError(
                        "GDC matrix shards contain different gene counts."
                    )
                feature_ids = {row[0] for row in rows if row is not None}
                if len(feature_ids) != 1:
                    raise ValueError(
                        "GDC matrix shards do not share gene order."
                    )
                writer.writerow(
                    [
                        next(iter(feature_ids)),
                        *[
                            value
                            for row in rows
                            if row is not None
                            for value in row[1:]
                        ],
                    ]
                )
    finally:
        for handle in handles:
            handle.close()


def gdc_star_tpm_iterator(
    path: Path,
) -> tuple[Iterator[tuple[str, str, str]], str | None]:
    handle = path.open(newline="", encoding="utf-8")
    gene_model: str | None = None
    header_line: str | None = None
    for line in handle:
        if line.startswith("#"):
            if line.lower().startswith("# gene-model:"):
                gene_model = line.split(":", 1)[1].strip()
            continue
        header_line = line
        break
    if header_line is None:
        handle.close()
        raise ValueError(f"GDC STAR-counts file {path.name} has no header.")
    fieldnames = next(csv.reader([header_line], delimiter="\t"))
    required = {"gene_id", "gene_name", "tpm_unstranded"}
    if not required.issubset(fieldnames):
        handle.close()
        raise ValueError(
            f"GDC STAR-counts file {path.name} lacks {sorted(required)}."
        )
    reader = csv.DictReader(handle, fieldnames=fieldnames, delimiter="\t")

    def rows() -> Iterator[tuple[str, str, str]]:
        try:
            for row in reader:
                gene_id = str(row.get("gene_id") or "").strip()
                gene_name = str(row.get("gene_name") or "").strip()
                raw_value = str(row.get("tpm_unstranded") or "").strip()
                if not gene_id.startswith("ENSG") or not gene_name:
                    continue
                if "|" in gene_id or "|" in gene_name:
                    raise ValueError(
                        "GDC gene identifiers cannot contain '|'."
                    )
                try:
                    value = float(raw_value)
                except ValueError as exc:
                    raise ValueError(
                        f"Invalid GDC TPM for {gene_id} in {path.name}."
                    ) from exc
                if not math.isfinite(value) or value < 0:
                    raise ValueError(
                        f"Invalid GDC TPM for {gene_id} in {path.name}."
                    )
                yield gene_id, gene_name, format(value, ".17g")
        finally:
            handle.close()

    return rows(), gene_model


def select_primary_diagnosis(
    diagnoses: Iterable[dict[str, Any]],
) -> dict[str, Any]:
    rows = [row for row in diagnoses if isinstance(row, dict)]
    if not rows:
        return {}
    rows.sort(
        key=lambda row: (
            row.get("diagnosis_is_primary_disease") is not True,
            str(row.get("classification_of_tumor") or "").casefold()
            != "primary",
            str(row.get("diagnosis_id") or ""),
            str(row.get("submitter_id") or ""),
        )
    )
    return rows[0]


def resolve_age_at_index(
    demographic: dict[str, Any],
    diagnosis: dict[str, Any],
) -> str:
    value = demographic.get("age_at_index")
    if value is not None:
        return clean_value(value)
    days = diagnosis.get("age_at_diagnosis")
    try:
        return format(float(days) / 365.25, ".8g")
    except (TypeError, ValueError):
        return ""


def first_nonmissing(row: dict[str, Any], fields: list[str]) -> str:
    for field in fields:
        value = clean_value(row.get(field))
        if value:
            return value
    return ""


def clean_value(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if not text or text.casefold() in {
        "not reported",
        "not allowed to collect",
        "unknown",
        "na",
        "n/a",
    }:
        return ""
    return text


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )


def md5_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.md5(usedforsecurity=False)
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()
