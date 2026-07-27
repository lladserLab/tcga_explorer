from __future__ import annotations

from array import array
import csv
from concurrent.futures import ThreadPoolExecutor
import gzip
import hashlib
import io
import json
import math
from pathlib import Path
import re
import shutil
from typing import Any, Iterable
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from app.repository.adapters.cbioportal import (
    NETWORK_ATTEMPTS,
    RETRYABLE_HTTP_CODES,
    USER_AGENT,
    download,
    write_tsv,
)
from app.repository.storage import sha256_file


ICGC_ADAPTER_VERSION = "icgc25k_release28_v1"
DEFAULT_ENDPOINT = "https://object.genomeinformatics.org"
DEFAULT_BUCKET = "icgc25k-open"
DEFAULT_RELEASE_PREFIX = "release_28"
REQUIRED_ROLES = ("donor", "sample", "specimen", "exp_seq")
DEFAULT_SPECIMEN_PRIORITY = (
    "Primary tumour - solid tissue",
    "Recurrent tumour - solid tissue",
    "Metastatic tumour - lymph node",
    "Metastatic tumour - metastasis to distant location",
    "Metastatic tumour - additional metastatic",
)
MISSING_VALUES = {
    "",
    "na",
    "n/a",
    "null",
    "unknown",
    "not available",
    "not applicable",
}


def materialize_icgc_source(
    spec: dict[str, Any],
    source_dir: Path,
) -> tuple[dict[str, Path], str, str | None, dict[str, Any]]:
    source_spec = spec["source"]
    endpoint = str(
        source_spec.get("object_endpoint") or DEFAULT_ENDPOINT
    ).rstrip("/")
    bucket = str(source_spec.get("bucket") or DEFAULT_BUCKET).strip("/")
    release_prefix = str(
        source_spec.get("release_prefix") or DEFAULT_RELEASE_PREFIX
    ).strip("/")
    project_code = str(source_spec.get("project_code") or "").strip()
    license_url = str(
        source_spec.get("license_evidence_url") or ""
    ).strip()
    readme_key = str(
        source_spec.get("release_readme_key")
        or f"{release_prefix}/projects_files/README.txt"
    ).strip("/")
    if not project_code or not license_url:
        raise ValueError(
            "ICGC sources require project_code and license_evidence_url."
        )
    if project_code.upper().startswith(("TCGA-", "TARGET-", "PCAWG-")):
        raise ValueError(
            "ICGC repository releases must be independent of TCGA, "
            "TARGET and PCAWG."
        )

    project_prefix = f"{release_prefix}/data/{project_code}/"
    project_objects = list_icgc_objects(
        endpoint, bucket, project_prefix
    )
    objects_by_role: dict[str, list[dict[str, Any]]] = {
        role: [] for role in REQUIRED_ROLES
    }
    for record in project_objects:
        role = object_role(str(record["key"]))
        if role in objects_by_role:
            objects_by_role[role].append(record)
    if not objects_by_role["exp_seq"]:
        raise ValueError(
            f"ICGC project {project_code} has no open exp_seq objects."
        )

    expression_donors = sorted(
        {
            object_donor_id(str(record["key"]))
            for record in objects_by_role["exp_seq"]
        }
    )
    if len(expression_donors) < 10:
        raise ValueError(
            "ICGC project has fewer than 10 donors with open RNA-seq "
            "expression."
        )
    expression_donor_set = set(expression_donors)
    selected_project_objects = sorted(
        (
            record
            for role_records in objects_by_role.values()
            for record in role_records
            if object_donor_id(str(record["key"]))
            in expression_donor_set
        ),
        key=lambda record: str(record["key"]),
    )

    header_records = []
    header_paths: dict[str, Path] = {}
    for role in REQUIRED_ROLES:
        key = f"{release_prefix}/headers/{role}.tsv.gz"
        records = list_icgc_objects(endpoint, bucket, key)
        exact = [record for record in records if record["key"] == key]
        if len(exact) != 1:
            raise ValueError(f"ICGC header object not found: {key}")
        header_records.extend(exact)
    readme_records = list_icgc_objects(endpoint, bucket, readme_key)
    readme_exact = [
        record for record in readme_records if record["key"] == readme_key
    ]
    if len(readme_exact) != 1:
        raise ValueError(f"ICGC release README not found: {readme_key}")

    raw_dir = source_dir / ".icgc_objects"
    raw_dir.mkdir()
    utilized_objects = sorted(
        [*selected_project_objects, *header_records, *readme_exact],
        key=lambda record: str(record["key"]),
    )
    local_paths = download_icgc_objects(
        endpoint,
        bucket,
        utilized_objects,
        raw_dir,
        max_workers=int(source_spec.get("download_workers") or 12),
    )

    for role in REQUIRED_ROLES:
        key = f"{release_prefix}/headers/{role}.tsv.gz"
        target = source_dir / f"icgc_{role}_header.tsv.gz"
        shutil.copyfile(local_paths[key], target)
        header_paths[role] = target
    headers = {
        role: read_icgc_header(path)
        for role, path in header_paths.items()
    }
    readme_path = source_dir / "ICGC_RELEASE_28_README.txt"
    shutil.copyfile(local_paths[readme_key], readme_path)
    license_suffix = (
        Path(urllib.parse.urlparse(license_url).path).suffix or ".html"
    )
    license_path = source_dir / (
        f"ICGC_PUBLICATION_POLICY{license_suffix}"
    )
    download(license_url, license_path)

    records_by_donor_role: dict[
        str, dict[str, list[dict[str, str]]]
    ] = {
        donor_id: {role: [] for role in REQUIRED_ROLES[:-1]}
        for donor_id in expression_donors
    }
    exp_paths_by_donor: dict[str, list[Path]] = {
        donor_id: [] for donor_id in expression_donors
    }
    for record in selected_project_objects:
        key = str(record["key"])
        role = object_role(key)
        donor_id = object_donor_id(key)
        if role == "exp_seq":
            exp_paths_by_donor[donor_id].append(local_paths[key])
        elif role in records_by_donor_role[donor_id]:
            records_by_donor_role[donor_id][role].extend(
                read_icgc_rows(local_paths[key], headers[role])
            )

    specimen_priority = tuple(
        str(value).strip()
        for value in (
            source_spec.get("specimen_type_priority")
            or DEFAULT_SPECIMEN_PRIORITY
        )
        if str(value).strip()
    )
    required_gene_model = clean(
        source_spec.get("required_gene_model")
    )
    required_normalization = clean(
        source_spec.get("required_normalization_algorithm")
    )
    selected_analyses: list[dict[str, Any]] = []
    excluded_endpoint_donors: list[str] = []
    excluded_tumor_donors: list[str] = []
    for donor_id in expression_donors:
        clinical = records_by_donor_role[donor_id]
        donor = one_consistent_row(
            clinical["donor"],
            id_field="icgc_donor_id",
            expected_id=donor_id,
        )
        endpoint_value = resolve_icgc_os(donor)
        if endpoint_value is None:
            excluded_endpoint_donors.append(donor_id)
            continue
        sample_by_id = unique_rows_by_id(
            clinical["sample"], "icgc_sample_id"
        )
        specimen_by_id = unique_rows_by_id(
            clinical["specimen"], "icgc_specimen_id"
        )
        analyses = inspect_expression_analyses(
            exp_paths_by_donor[donor_id],
            headers["exp_seq"],
            project_code=project_code,
        )
        selected = select_expression_analysis(
            analyses,
            sample_by_id,
            specimen_by_id,
            specimen_priority=specimen_priority,
            required_gene_model=required_gene_model,
            required_normalization_algorithm=required_normalization,
        )
        if selected is None:
            excluded_tumor_donors.append(donor_id)
            continue
        selected_analyses.append(
            {
                "donor_id": donor_id,
                "donor": donor,
                "endpoint": endpoint_value,
                "sample": sample_by_id[selected["icgc_sample_id"]],
                "specimen": specimen_by_id[selected["icgc_specimen_id"]],
                "analysis": selected,
                "expression_paths": sorted(
                    exp_paths_by_donor[donor_id], key=str
                ),
            }
        )
    selected_analyses.sort(key=lambda row: row["donor_id"])
    if len(selected_analyses) < 10:
        raise ValueError(
            "Fewer than 10 ICGC donors have usable survival and an "
            "eligible tumor RNA-seq analysis."
        )

    patient_rows = []
    sample_rows = []
    events = 0
    censored = 0
    for selected in selected_analyses:
        donor = selected["donor"]
        sample = selected["sample"]
        specimen = selected["specimen"]
        analysis = selected["analysis"]
        endpoint_value = selected["endpoint"]
        event = int(endpoint_value["event"])
        events += event
        censored += 1 - event
        patient_rows.append(
            {
                "PATIENT_ID": selected["donor_id"],
                "ICGC_PROJECT_CODE": project_code,
                "ICGC_OS_DAYS": format(
                    float(endpoint_value["time_days"]), ".17g"
                ),
                "ICGC_OS_STATUS": (
                    "1:DECEASED" if event else "0:CENSORED"
                ),
                "STAGE": first_clean(
                    specimen.get("tumour_stage"),
                    donor.get("donor_tumour_stage_at_diagnosis"),
                ),
                "GRADE": clean(specimen.get("tumour_grade")) or "",
                "SEX": clean(donor.get("donor_sex")) or "",
                "RACE": "",
                "AGE_AT_INDEX": (
                    clean(donor.get("donor_age_at_diagnosis")) or ""
                ),
                "ICGC_DONOR_METADATA_JSON": canonical_json(donor),
                "ICGC_ENDPOINT_TIME_SOURCE": endpoint_value["time_source"],
            }
        )
        sample_rows.append(
            {
                "SAMPLE_ID": analysis["icgc_sample_id"],
                "PATIENT_ID": selected["donor_id"],
                "SAMPLE_TYPE": specimen["specimen_type"],
                "ICGC_SPECIMEN_ID": specimen["icgc_specimen_id"],
                "ICGC_ANALYSIS_ID": analysis["analysis_id"],
                "ICGC_SAMPLE_METADATA_JSON": canonical_json(sample),
                "ICGC_SPECIMEN_METADATA_JSON": canonical_json(specimen),
                "ICGC_EXPRESSION_METADATA_JSON": canonical_json(
                    analysis["metadata"]
                ),
            }
        )

    expression_path = source_dir / "data_expression_icgc.tsv.gz"
    expression_summary = write_icgc_expression_table(
        expression_path,
        selected_analyses,
        headers["exp_seq"],
    )
    patient_table = source_dir / "data_clinical_patient.txt"
    sample_table = source_dir / "data_clinical_sample.txt"
    write_tsv(
        patient_table,
        patient_rows,
        [
            "PATIENT_ID",
            "ICGC_PROJECT_CODE",
            "ICGC_OS_DAYS",
            "ICGC_OS_STATUS",
            "STAGE",
            "GRADE",
            "SEX",
            "RACE",
            "AGE_AT_INDEX",
            "ICGC_DONOR_METADATA_JSON",
            "ICGC_ENDPOINT_TIME_SOURCE",
        ],
    )
    write_tsv(
        sample_table,
        sample_rows,
        [
            "SAMPLE_ID",
            "PATIENT_ID",
            "SAMPLE_TYPE",
            "ICGC_SPECIMEN_ID",
            "ICGC_ANALYSIS_ID",
            "ICGC_SAMPLE_METADATA_JSON",
            "ICGC_SPECIMEN_METADATA_JSON",
            "ICGC_EXPRESSION_METADATA_JSON",
        ],
    )

    inventory = {
        "schema_version": "tcga-trace-icgc-object-inventory-v1",
        "endpoint": endpoint,
        "bucket": bucket,
        "release_prefix": release_prefix,
        "project_code": project_code,
        "objects": utilized_objects,
        "selection": {
            "project_expression_donors": len(expression_donors),
            "selected_donors": len(selected_analyses),
            "excluded_missing_endpoint": excluded_endpoint_donors,
            "excluded_no_eligible_tumor_analysis": (
                excluded_tumor_donors
            ),
            "specimen_type_priority": list(specimen_priority),
            "required_gene_model": required_gene_model,
            "required_normalization_algorithm": required_normalization,
        },
    }
    inventory_path = source_dir / "icgc_object_inventory.json"
    inventory_path.write_text(
        canonical_json(inventory) + "\n", encoding="utf-8"
    )
    source_paths = {
        "expression": expression_path,
        "patients": patient_table,
        "samples": sample_table,
        "object_inventory": inventory_path,
        "release_readme": readme_path,
        "license": license_path,
        **{
            f"{role}_header": path
            for role, path in header_paths.items()
        },
    }
    source_hashes = {
        role: sha256_file(path)
        for role, path in sorted(source_paths.items())
    }
    source_snapshot = hashlib.sha256(
        canonical_json(
            {
                "object_inventory": inventory,
                "source_file_sha256": source_hashes,
            }
        ).encode("utf-8")
    ).hexdigest()
    shutil.rmtree(raw_dir)
    return (
        source_paths,
        source_snapshot,
        str(source_spec.get("release_date") or "2019-11-26"),
        {
            "source_api": endpoint,
            "source_bucket": bucket,
            "source_release": release_prefix,
            "source_project_code": project_code,
            "source_project_objects": len(project_objects),
            "source_objects_used": len(utilized_objects),
            "source_expression_donors": len(expression_donors),
            "icgc_selected_donors": len(selected_analyses),
            "icgc_events": events,
            "icgc_censored": censored,
            "icgc_excluded_missing_endpoint": len(
                excluded_endpoint_donors
            ),
            "icgc_excluded_missing_endpoint_donors": (
                excluded_endpoint_donors
            ),
            "icgc_excluded_no_eligible_tumor_analysis": (
                len(excluded_tumor_donors)
            ),
            "icgc_excluded_no_eligible_tumor_analysis_donors": (
                excluded_tumor_donors
            ),
            **expression_summary,
        },
    )


def list_icgc_objects(
    endpoint: str,
    bucket: str,
    prefix: str,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    continuation_token: str | None = None
    while True:
        query = {
            "list-type": "2",
            "prefix": prefix,
            "max-keys": "1000",
        }
        if continuation_token:
            query["continuation-token"] = continuation_token
        request = urllib.request.Request(
            f"{endpoint}/{bucket}?{urllib.parse.urlencode(query)}",
            headers={"User-Agent": USER_AGENT},
        )
        with urllib.request.urlopen(request, timeout=90) as response:
            root = ET.fromstring(response.read())
        page, truncated, continuation_token = parse_object_listing(root)
        records.extend(page)
        if not truncated:
            break
        if not continuation_token:
            raise ValueError(
                "ICGC object listing is truncated without a continuation "
                "token."
            )
    return sorted(records, key=lambda record: str(record["key"]))


def parse_object_listing(
    root: ET.Element,
) -> tuple[list[dict[str, Any]], bool, str | None]:
    records = []
    for contents in (
        element
        for element in root.iter()
        if local_name(element.tag) == "Contents"
    ):
        values = {
            local_name(child.tag): child.text or ""
            for child in contents
        }
        key = values.get("Key", "")
        if not key:
            continue
        records.append(
            {
                "key": key,
                "etag": values.get("ETag", "").strip('"'),
                "size": int(values.get("Size") or 0),
                "last_modified": values.get("LastModified") or None,
            }
        )
    truncated = next(
        (
            (element.text or "").lower() == "true"
            for element in root.iter()
            if local_name(element.tag) == "IsTruncated"
        ),
        False,
    )
    token = next(
        (
            element.text
            for element in root.iter()
            if local_name(element.tag) == "NextContinuationToken"
        ),
        None,
    )
    return records, truncated, token


def download_icgc_objects(
    endpoint: str,
    bucket: str,
    records: Iterable[dict[str, Any]],
    output_dir: Path,
    *,
    max_workers: int,
) -> dict[str, Path]:
    records = list(records)
    if max_workers < 1 or max_workers > 32:
        raise ValueError("ICGC download_workers must be between 1 and 32.")

    def fetch(record: dict[str, Any]) -> tuple[str, Path]:
        key = str(record["key"])
        suffix = "".join(Path(key).suffixes)
        filename = hashlib.sha256(key.encode("utf-8")).hexdigest() + suffix
        path = output_dir / filename
        download_icgc_object(endpoint, bucket, record, path)
        return key, path

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        return dict(pool.map(fetch, records))


def download_icgc_object(
    endpoint: str,
    bucket: str,
    record: dict[str, Any],
    path: Path,
) -> None:
    key = str(record["key"])
    url = (
        f"{endpoint}/{bucket}/"
        f"{urllib.parse.quote(key, safe='/')}"
    )
    last_error: Exception | None = None
    for attempt in range(NETWORK_ATTEMPTS):
        try:
            request = urllib.request.Request(
                url, headers={"User-Agent": USER_AGENT}
            )
            with urllib.request.urlopen(request, timeout=120) as response:
                payload = response.read()
            expected_size = int(record["size"])
            if len(payload) != expected_size:
                raise ValueError(
                    f"ICGC object {key} has {len(payload)} bytes; "
                    f"expected {expected_size}."
                )
            etag = str(record.get("etag") or "").lower()
            if re.fullmatch(r"[0-9a-f]{32}", etag):
                actual_md5 = hashlib.md5(
                    payload, usedforsecurity=False
                ).hexdigest()
                if actual_md5 != etag:
                    raise ValueError(
                        f"ICGC object {key} failed ETag/MD5 validation."
                    )
            path.write_bytes(payload)
            return
        except urllib.error.HTTPError as error:
            last_error = error
            if error.code not in RETRYABLE_HTTP_CODES:
                break
        except (OSError, ValueError) as error:
            last_error = error
        if attempt + 1 < NETWORK_ATTEMPTS:
            import time

            time.sleep(2**attempt)
    raise RuntimeError(f"Could not download ICGC object {key}.") from last_error


def read_icgc_header(path: Path) -> list[str]:
    with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
        row = next(csv.reader(handle, delimiter="\t"))
    if not row or len(row) != len(set(row)):
        raise ValueError(f"Invalid ICGC header: {path.name}")
    return row


def read_icgc_rows(
    path: Path,
    header: list[str],
) -> list[dict[str, str]]:
    rows = []
    with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
        for values in csv.reader(handle, delimiter="\t"):
            if not values:
                continue
            if len(values) != len(header):
                raise ValueError(
                    f"ICGC row has {len(values)} fields; expected "
                    f"{len(header)} in {path.name}."
                )
            rows.append(dict(zip(header, values, strict=True)))
    return rows


def inspect_expression_analyses(
    paths: Iterable[Path],
    header: list[str],
    *,
    project_code: str,
) -> list[dict[str, Any]]:
    analyses: dict[tuple[str, str], dict[str, Any]] = {}
    for row in iter_expression_rows(paths, header):
        if row["project_code"] != project_code:
            raise ValueError(
                "ICGC expression row belongs to a different project."
            )
        key = (row["icgc_sample_id"], row["analysis_id"])
        metadata = expression_metadata(row)
        current = analyses.setdefault(
            key,
            {
                **metadata,
                "metadata": metadata,
                "gene_rows": 0,
            },
        )
        if current["metadata"] != metadata:
            raise ValueError(
                "ICGC analysis metadata changes across expression rows."
            )
        current["gene_rows"] += 1
    return sorted(
        analyses.values(),
        key=lambda row: (
            row["icgc_sample_id"],
            row["analysis_id"],
        ),
    )


def select_expression_analysis(
    analyses: Iterable[dict[str, Any]],
    sample_by_id: dict[str, dict[str, str]],
    specimen_by_id: dict[str, dict[str, str]],
    *,
    specimen_priority: tuple[str, ...],
    required_gene_model: str | None,
    required_normalization_algorithm: str | None,
) -> dict[str, Any] | None:
    priority = {
        specimen_type.casefold(): index
        for index, specimen_type in enumerate(specimen_priority)
    }
    candidates = []
    for analysis in analyses:
        sample = sample_by_id.get(str(analysis["icgc_sample_id"]))
        specimen = specimen_by_id.get(
            str(analysis["icgc_specimen_id"])
        )
        if sample is None or specimen is None:
            continue
        if (
            sample.get("icgc_specimen_id")
            != analysis["icgc_specimen_id"]
        ):
            continue
        specimen_type = clean(specimen.get("specimen_type"))
        if specimen_type is None or specimen_type.casefold() not in priority:
            continue
        if (
            required_gene_model
            and clean(analysis.get("gene_model")) != required_gene_model
        ):
            continue
        if (
            required_normalization_algorithm
            and clean(analysis.get("normalization_algorithm"))
            != required_normalization_algorithm
        ):
            continue
        if int(analysis.get("gene_rows") or 0) < 10_000:
            continue
        candidates.append(
            (
                priority[specimen_type.casefold()],
                str(sample.get("submitted_sample_id") or ""),
                str(analysis["icgc_sample_id"]),
                str(analysis["analysis_id"]),
                analysis,
            )
        )
    return min(candidates)[-1] if candidates else None


def write_icgc_expression_table(
    path: Path,
    selected_analyses: list[dict[str, Any]],
    header: list[str],
) -> dict[str, Any]:
    sample_ids = [
        str(row["analysis"]["icgc_sample_id"])
        for row in selected_analyses
    ]
    if len(sample_ids) != len(set(sample_ids)):
        raise ValueError("Selected ICGC expression sample IDs are not unique.")
    first = selected_analyses[0]
    first_values = selected_expression_values(first, header)
    genes = sorted(first_values)
    gene_index = {gene: index for index, gene in enumerate(genes)}
    sample_count = len(selected_analyses)
    values = array("d", [0.0]) * (len(genes) * sample_count)
    presence = array("I", [0]) * len(genes)

    for sample_index, selected in enumerate(selected_analyses):
        sample_values = (
            first_values
            if sample_index == 0
            else selected_expression_values(selected, header)
        )
        for gene, value in sample_values.items():
            index = gene_index.get(gene)
            if index is None:
                continue
            values[index * sample_count + sample_index] = value
            presence[index] += 1
    complete_indexes = [
        index
        for index, count in enumerate(presence)
        if count == sample_count
    ]
    if len(complete_indexes) < 10_000:
        raise ValueError(
            "Fewer than 10,000 ICGC genes are complete across selected "
            "samples."
        )

    with path.open("wb") as raw_handle:
        with gzip.GzipFile(
            filename="",
            mode="wb",
            fileobj=raw_handle,
            mtime=0,
        ) as gzip_handle:
            with io.TextIOWrapper(
                gzip_handle, encoding="utf-8", newline=""
            ) as text_handle:
                writer = csv.writer(
                    text_handle,
                    delimiter="\t",
                    lineterminator="\n",
                )
                writer.writerow(["Hugo_Symbol", *sample_ids])
                for index in complete_indexes:
                    offset = index * sample_count
                    writer.writerow(
                        [
                            genes[index],
                            *(
                                format(value, ".17g")
                                for value in values[
                                    offset : offset + sample_count
                                ]
                            ),
                        ]
                    )
    selected_gene_counts = [
        int(row["analysis"]["gene_rows"])
        for row in selected_analyses
    ]
    metadata_values = [
        row["analysis"]["metadata"] for row in selected_analyses
    ]
    return {
        "icgc_expression_samples": sample_count,
        "icgc_expression_complete_genes": len(complete_indexes),
        "icgc_expression_gene_rows_min": min(selected_gene_counts),
        "icgc_expression_gene_rows_max": max(selected_gene_counts),
        "icgc_gene_models": sorted(
            {str(row.get("gene_model") or "") for row in metadata_values}
        ),
        "icgc_normalization_algorithms": sorted(
            {
                str(row.get("normalization_algorithm") or "")
                for row in metadata_values
            }
        ),
        "icgc_assembly_versions": sorted(
            {
                str(row.get("assembly_version") or "")
                for row in metadata_values
            }
        ),
    }


def selected_expression_values(
    selected: dict[str, Any],
    header: list[str],
) -> dict[str, float]:
    analysis = selected["analysis"]
    target = (
        str(analysis["icgc_sample_id"]),
        str(analysis["analysis_id"]),
    )
    values: dict[str, float] = {}
    for row in iter_expression_rows(
        selected["expression_paths"], header
    ):
        if (row["icgc_sample_id"], row["analysis_id"]) != target:
            continue
        gene = str(row.get("gene_id") or "").strip().upper()
        if not gene:
            continue
        try:
            value = float(row["normalized_read_count"])
        except (TypeError, ValueError) as error:
            raise ValueError(
                f"ICGC analysis {target[1]} has non-numeric expression."
            ) from error
        if not math.isfinite(value) or value < 0:
            raise ValueError(
                f"ICGC analysis {target[1]} has invalid expression."
            )
        if gene in values:
            raise ValueError(
                f"ICGC analysis {target[1]} contains duplicate gene "
                f"{gene}."
            )
        values[gene] = value
    if len(values) < 10_000:
        raise ValueError(
            f"ICGC analysis {target[1]} has fewer than 10,000 genes."
        )
    return values


def iter_expression_rows(
    paths: Iterable[Path],
    header: list[str],
):
    for path in sorted(paths, key=str):
        yield from read_icgc_rows(path, header)


def expression_metadata(row: dict[str, str]) -> dict[str, str]:
    return {
        key: row.get(key, "")
        for key in (
            "icgc_donor_id",
            "project_code",
            "icgc_specimen_id",
            "icgc_sample_id",
            "submitted_sample_id",
            "analysis_id",
            "gene_model",
            "assembly_version",
            "platform",
            "total_read_count",
            "experimental_protocol",
            "alignment_algorithm",
            "normalization_algorithm",
            "other_analysis_algorithm",
            "sequencing_strategy",
            "raw_data_repository",
            "raw_data_accession",
            "reference_sample_type",
        )
    }


def resolve_icgc_os(
    donor: dict[str, str],
) -> dict[str, Any] | None:
    status = (clean(donor.get("donor_vital_status")) or "").casefold()
    survival_time = positive_number(donor.get("donor_survival_time"))
    followup_time = positive_number(
        donor.get("donor_interval_of_last_followup")
    )
    if status in {"deceased", "dead"}:
        time_days = survival_time or followup_time
        event = 1
        source = (
            "donor_survival_time"
            if survival_time is not None
            else "donor_interval_of_last_followup"
        )
    elif status in {"alive", "living"}:
        time_days = followup_time or survival_time
        event = 0
        source = (
            "donor_interval_of_last_followup"
            if followup_time is not None
            else "donor_survival_time"
        )
    else:
        return None
    if time_days is None:
        return None
    return {
        "time_days": time_days,
        "event": event,
        "time_source": source,
    }


def one_consistent_row(
    rows: Iterable[dict[str, str]],
    *,
    id_field: str,
    expected_id: str,
) -> dict[str, str]:
    unique = {
        canonical_json(row): row
        for row in rows
        if row.get(id_field) == expected_id
    }
    if len(unique) != 1:
        raise ValueError(
            f"Expected one consistent ICGC {id_field} row for "
            f"{expected_id}; found {len(unique)}."
        )
    return next(iter(unique.values()))


def unique_rows_by_id(
    rows: Iterable[dict[str, str]],
    id_field: str,
) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    for row in rows:
        value = str(row.get(id_field) or "")
        if not value:
            continue
        existing = result.get(value)
        if existing is not None and existing != row:
            raise ValueError(
                f"Conflicting ICGC rows for {id_field}={value}."
            )
        result[value] = row
    return result


def object_role(key: str) -> str:
    parts = key.split("/")
    return parts[-2] if len(parts) >= 2 else ""


def object_donor_id(key: str) -> str:
    parts = key.split("/")
    if len(parts) < 4:
        raise ValueError(f"Invalid ICGC project object key: {key}")
    return parts[3]


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def clean(value: Any) -> str | None:
    text = str(value or "").strip()
    return None if text.casefold() in MISSING_VALUES else text


def positive_number(value: Any) -> float | None:
    cleaned = clean(value)
    if cleaned is None:
        return None
    try:
        number = float(cleaned)
    except ValueError:
        return None
    return number if math.isfinite(number) and number > 0 else None


def first_clean(*values: Any) -> str:
    return next(
        (clean(value) for value in values if clean(value) is not None),
        "",
    )


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
