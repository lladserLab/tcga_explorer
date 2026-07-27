from __future__ import annotations

import csv
from datetime import datetime, timezone
import gzip
import hashlib
import io
import json
import math
from pathlib import Path
import re
import shutil
import time
from typing import Any, Iterable
import urllib.parse
import urllib.error
import urllib.request

from app.repository.importer import BUNDLE_SCHEMA_VERSION
from app.repository.storage import sha256_file, write_float32le_matrix


GITHUB_API = "https://api.github.com"
CBIOPORTAL_API = "https://www.cbioportal.org/api"
GDC_API = "https://api.gdc.cancer.gov"
USER_AGENT = "TCGA-TRACE-curated-repository/1.0"
MONTH_DAYS = 365.25 / 12.0
YEAR_DAYS = 365.25
ADAPTER_VERSION = "cbioportal_datahub_v2"
API_ADAPTER_VERSION = "cbioportal_api_v2"
NETWORK_ATTEMPTS = 4
RETRYABLE_HTTP_CODES = {429, 500, 502, 503, 504}


def build_cbioportal_bundle(
    spec_path: Path,
    output_dir: Path,
    *,
    force: bool = False,
) -> dict[str, Any]:
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    if spec.get("schema_version") != "tcga-trace-study-spec-v1":
        raise ValueError("Unsupported repository study specification.")
    if output_dir.exists():
        if not force:
            raise FileExistsError(output_dir)
        shutil.rmtree(output_dir)
    source_dir = output_dir / "source"
    derived_dir = output_dir / "derived"
    source_dir.mkdir(parents=True)
    derived_dir.mkdir(parents=True)

    source_spec = spec["source"]
    source_build_metadata: dict[str, Any] = {}
    adapter_files = [Path(__file__)]
    provider = str(source_spec.get("provider") or "cbioportal_datahub")
    if provider == "cbioportal_api":
        (
            source_paths,
            commit_sha,
            commit_date,
            source_build_metadata,
        ) = materialize_cbioportal_api_source(spec, source_dir)
        adapter_version = API_ADAPTER_VERSION
        release_version_prefix = "cbioportal-api"
    elif provider == "gdc_api":
        from app.repository.adapters import gdc

        (
            source_paths,
            commit_sha,
            commit_date,
            source_build_metadata,
        ) = gdc.materialize_gdc_source(spec, source_dir)
        adapter_version = gdc.GDC_ADAPTER_VERSION
        adapter_files.append(Path(gdc.__file__))
        release_version_prefix = "gdc"
    elif provider == "geo":
        from app.repository.adapters import geo

        (
            source_paths,
            commit_sha,
            commit_date,
            source_build_metadata,
        ) = geo.materialize_geo_source(spec, source_dir)
        adapter_version = geo.GEO_ADAPTER_VERSION
        adapter_files.append(Path(geo.__file__))
        release_version_prefix = "geo"
    elif provider == "icgc_release28":
        from app.repository.adapters import icgc

        (
            source_paths,
            commit_sha,
            commit_date,
            source_build_metadata,
        ) = icgc.materialize_icgc_source(spec, source_dir)
        adapter_version = icgc.ICGC_ADAPTER_VERSION
        adapter_files.append(Path(icgc.__file__))
        release_version_prefix = "icgc"
    elif provider in {
        "europe_pmc_supplement",
        "europe_pmc_geo_supplement",
    }:
        from app.repository.adapters import pmc

        (
            source_paths,
            commit_sha,
            commit_date,
            source_build_metadata,
        ) = pmc.materialize_europe_pmc_source(spec, source_dir)
        adapter_version = pmc.EUROPE_PMC_ADAPTER_VERSION
        adapter_files.append(Path(pmc.__file__))
        release_version_prefix = "pmc"
    else:
        repository = str(source_spec["repository"])
        branch = str(source_spec.get("branch") or "master")
        study_path = str(source_spec["study_path"]).strip("/")
        commit = latest_path_commit(repository, study_path, branch)
        commit_sha = str(commit["sha"])
        commit_date = (
            commit.get("commit", {}).get("committer", {}).get("date")
            or commit.get("commit", {}).get("author", {}).get("date")
        )
        source_paths = {}
        used_target_names: set[str] = set()
        for role, file_spec in source_spec["files"].items():
            relative, target_name = resolve_source_file_spec(
                study_path, file_spec
            )
            if target_name in used_target_names:
                raise ValueError(
                    "Source files resolve to duplicate target name "
                    f"{target_name!r}."
                )
            used_target_names.add(target_name)
            media_url = (
                "https://media.githubusercontent.com/media/"
                f"{repository}/{commit_sha}/{relative}"
            )
            raw_url = (
                "https://raw.githubusercontent.com/"
                f"{repository}/{commit_sha}/{relative}"
            )
            target = source_dir / target_name
            download_with_fallback([media_url, raw_url], target)
            source_paths[role] = target
        adapter_version = ADAPTER_VERSION
        release_version_prefix = "datahub"

    patients_all = read_cbioportal_table(source_paths["patients"])
    samples_all = read_cbioportal_table(source_paths["samples"])
    patient_by_id = {
        str(row.get("PATIENT_ID") or "").strip(): row
        for row in patients_all
        if str(row.get("PATIENT_ID") or "").strip()
    }
    sample_by_id = {
        str(row.get("SAMPLE_ID") or "").strip(): row
        for row in samples_all
        if str(row.get("SAMPLE_ID") or "").strip()
    }

    expression_header = read_expression_header(source_paths["expression"])
    source_sample_ids = expression_header[1:]
    endpoint_specs = list(spec["endpoints"])
    if not endpoint_specs:
        raise ValueError("At least one endpoint specification is required.")
    endpoint_rows_by_id: dict[str, list[dict[str, Any]]] = {
        str(endpoint["endpoint_id"]): [] for endpoint in endpoint_specs
    }
    parsed_endpoints_by_patient = {
        patient_id: {
            str(endpoint["endpoint_id"]): parsed
            for endpoint in endpoint_specs
            if (parsed := parse_endpoint(patient, endpoint)) is not None
        }
        for patient_id, patient in patient_by_id.items()
    }
    sample_spec = spec.get("samples") or {}
    excluded_patient_patterns = [
        re.compile(str(pattern), flags=re.IGNORECASE)
        for pattern in sample_spec.get("exclude_patient_id_patterns") or []
    ]
    eligibility_rules = sample_spec.get("eligibility_rules") or []
    eligible_samples: list[str] = []
    patient_rows: list[dict[str, Any]] = []
    sample_rows: list[dict[str, Any]] = []
    seen_patients: set[str] = set()
    excluded_by_patient_pattern = 0
    excluded_by_sample_eligibility = 0
    for sample_id in source_sample_ids:
        sample = sample_by_id.get(sample_id)
        if sample is None:
            continue
        patient_id = str(sample.get("PATIENT_ID") or "").strip()
        patient = patient_by_id.get(patient_id)
        if patient is None:
            continue
        if any(
            pattern.search(patient_id)
            for pattern in excluded_patient_patterns
        ):
            excluded_by_patient_pattern += 1
            continue
        if not sample_passes_eligibility(
            patient, sample, eligibility_rules
        ):
            excluded_by_sample_eligibility += 1
            continue
        patient_endpoints = parsed_endpoints_by_patient.get(patient_id) or {}
        if not patient_endpoints:
            continue
        eligible_samples.append(sample_id)
        sample_rows.append(
            {
                "sample_id": sample_id,
                "patient_id": patient_id,
                "sample_type": (
                    _clean(
                        sample.get(
                            str(
                                sample_spec.get("sample_type_column")
                                or "SAMPLE_TYPE"
                            )
                        )
                    )
                    or str(
                        sample_spec.get("sample_type_default")
                        or "Tumor"
                    )
                ),
                "sample_role": str(
                    sample_spec.get("sample_role")
                    or "RNA-seq tumor sample"
                ),
                "selection_rank": str(
                    sample_selection_rank(patient, sample, sample_spec)
                ),
                "raw_metadata_json": json.dumps(
                    sample, sort_keys=True, separators=(",", ":")
                ),
            }
        )
        if patient_id not in seen_patients:
            for endpoint_spec in endpoint_specs:
                endpoint_id = str(endpoint_spec["endpoint_id"])
                endpoint = patient_endpoints.get(endpoint_id)
                if endpoint is None:
                    continue
                endpoint_rows_by_id[endpoint_id].append(
                    {
                        "patient_id": patient_id,
                        **endpoint,
                        "raw_metadata_json": json.dumps(
                            {
                                "source_time_column": endpoint_spec[
                                    "time_column"
                                ],
                                "source_event_column": endpoint_spec[
                                    "event_column"
                                ],
                            },
                            sort_keys=True,
                            separators=(",", ":"),
                        ),
                    }
                )
            patient_rows.append(
                {
                    "patient_id": patient_id,
                    "stage": resolve_patient_attribute(
                        patient,
                        sample,
                        sample_spec.get("stage_fields"),
                        ["sample.TUMOR_STAGE", "patient.M_STAGE"],
                    ),
                    "grade": resolve_patient_attribute(
                        patient,
                        sample,
                        sample_spec.get("grade_fields"),
                        [],
                    ),
                    "gender": resolve_patient_attribute(
                        patient,
                        sample,
                        sample_spec.get("gender_fields"),
                        ["patient.SEX", "patient.GENDER"],
                    ),
                    "race": resolve_patient_attribute(
                        patient,
                        sample,
                        sample_spec.get("race_fields"),
                        ["patient.RACE"],
                    ),
                    "age_at_index": resolve_patient_attribute(
                        patient,
                        sample,
                        sample_spec.get("age_fields"),
                        ["patient.AGE", "patient.AGE_AT_DIAGNOSIS"],
                    ),
                    "raw_metadata_json": json.dumps(
                        patient, sort_keys=True, separators=(",", ":")
                    ),
                }
            )
            seen_patients.add(patient_id)

    if len(eligible_samples) < 10:
        raise ValueError(
            "Fewer than 10 expression-complete samples have a usable endpoint."
        )
    source_index = {sample_id: index for index, sample_id in enumerate(source_sample_ids)}
    selected_indexes = [source_index[sample_id] for sample_id in eligible_samples]

    expression_spec = spec["expression"]
    feature_id_type = str(
        expression_spec.get("feature_id_type") or ""
    ).lower()
    original_ids = expression_feature_ids(source_paths["expression"])
    mapping = fetch_gene_mapping(original_ids, feature_id_type)
    duplicate_symbols = (
        duplicated_mapping_symbols(mapping)
        | duplicated_source_feature_symbols(
            original_ids, feature_id_type
        )
    )
    filtered_rows: list[tuple[str, str, list[float] | None]] = []
    dropped_missing_mapping = 0
    dropped_duplicate_mapping = 0
    collapsed_source_duplicate_rows = 0
    dropped_incomplete = 0
    duplicate_policy = expression_spec.get("duplicate_feature_policy")
    transform = str(expression_spec.get("transform") or "identity").lower()
    layer_id = str(expression_spec["layer_id"])
    matrix_path = derived_dir / f"{layer_id}.float32le.bin"
    stream_source_order = bool(
        expression_spec.get("stream_source_order")
    )

    def mapped_expression_rows():
        nonlocal dropped_missing_mapping
        nonlocal dropped_duplicate_mapping
        nonlocal dropped_incomplete
        for row in iter_expression_rows(source_paths["expression"]):
            if not row:
                continue
            original_id = row[0].strip()
            mapping_key = (
                original_id
                if feature_id_type == "entrez_gene_id"
                else original_id.upper()
            )
            symbol = mapping.get(mapping_key)
            if not symbol:
                dropped_missing_mapping += 1
                continue
            if symbol in duplicate_symbols:
                dropped_duplicate_mapping += 1
                continue
            try:
                raw_values = [
                    float(row[index + 1]) for index in selected_indexes
                ]
            except (IndexError, TypeError, ValueError):
                dropped_incomplete += 1
                continue
            if any(not math.isfinite(value) for value in raw_values):
                dropped_incomplete += 1
                continue
            if transform == "log2p" and any(
                value < 0 for value in raw_values
            ):
                dropped_incomplete += 1
                continue
            yield original_id, symbol, raw_values

    if stream_source_order:
        if duplicate_policy:
            raise ValueError(
                "stream_source_order requires unique source features and "
                "does not support duplicate_feature_policy."
            )
        seen_symbols: set[str] = set()

        def streaming_matrix_rows():
            for original_id, symbol, raw_values in mapped_expression_rows():
                if symbol in seen_symbols:
                    raise ValueError(
                        f"Canonical symbol {symbol} occurs more than once; "
                        "streaming source-order mode cannot collapse rows."
                    )
                seen_symbols.add(symbol)
                filtered_rows.append((original_id, symbol, None))
                yield apply_expression_transform(raw_values, transform)

        write_float32le_matrix(matrix_path, streaming_matrix_rows())
    else:
        retained_by_symbol: dict[
            str, tuple[str, list[float], int]
        ] = {}
        for original_id, symbol, raw_values in mapped_expression_rows():
            existing = retained_by_symbol.get(symbol)
            if existing is not None:
                if (
                    source_feature_ids_match(
                        existing[0], original_id, feature_id_type
                    )
                    and duplicate_policy
                    in {"mean_within_entrez_id", "mean_within_source_id"}
                ):
                    retained_by_symbol[symbol] = (
                        original_id,
                        [
                            current + incoming
                            for current, incoming in zip(
                                existing[1], raw_values, strict=True
                            )
                        ],
                        existing[2] + 1,
                    )
                    collapsed_source_duplicate_rows += 1
                    continue
                raise ValueError(
                    f"Canonical symbol {symbol} maps to non-identical source "
                    f"rows {existing[0]} and {original_id}; provide an "
                    "explicit curation override."
                )
            retained_by_symbol[symbol] = (original_id, raw_values, 1)

        filtered_rows = [
            (
                original_id,
                symbol,
                apply_expression_transform(
                    [value_sum / count for value_sum in sums], transform
                ),
            )
            for symbol, (
                original_id,
                sums,
                count,
            ) in retained_by_symbol.items()
        ]
        filtered_rows.sort(key=lambda row: (row[1], row[0]))
        write_float32le_matrix(
            matrix_path,
            (
                values
                for _, _, values in filtered_rows
                if values is not None
            ),
        )

    if len(filtered_rows) < 10_000:
        raise ValueError(
            f"Only {len(filtered_rows)} uniquely mapped complete genes remain."
        )
    matrix_metadata_path = derived_dir / f"{layer_id}.metadata.json"
    matrix_metadata = {
        "schema_version": "tcga-trace-expression-matrix-v1",
        "dtype": "float32_le",
        "layout": "row_major_gene_by_sample",
        "gene_count": len(filtered_rows),
        "sample_count": len(eligible_samples),
        "sample_ids": eligible_samples,
        "source_unit": expression_spec["source_unit"],
        "analysis_unit": expression_spec["analysis_unit"],
        "transform": transform,
    }
    matrix_metadata_path.write_text(
        json.dumps(matrix_metadata, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    genes_path = derived_dir / "genes.tsv"
    write_tsv(
        genes_path,
        [
            {
                "original_gene_id": original_id,
                "gene_symbol": symbol,
                "row_number": index,
                "mapping_source": expression_spec["mapping_source"],
            }
            for index, (original_id, symbol, _) in enumerate(filtered_rows)
        ],
        ["original_gene_id", "gene_symbol", "row_number", "mapping_source"],
    )
    patients_path = derived_dir / "patients.tsv"
    samples_path = derived_dir / "samples.tsv"
    write_tsv(
        patients_path,
        patient_rows,
        [
            "patient_id",
            "stage",
            "grade",
            "gender",
            "race",
            "age_at_index",
            "raw_metadata_json",
        ],
    )
    write_tsv(
        samples_path,
        sample_rows,
        [
            "sample_id",
            "patient_id",
            "sample_type",
            "sample_role",
            "selection_rank",
            "raw_metadata_json",
        ],
    )
    endpoint_paths: dict[str, Path] = {}
    for endpoint_spec in endpoint_specs:
        endpoint_id = str(endpoint_spec["endpoint_id"])
        endpoint_path = derived_dir / f"endpoint_{endpoint_id.lower()}.tsv"
        endpoint_paths[endpoint_id] = endpoint_path
        write_tsv(
            endpoint_path,
            endpoint_rows_by_id[endpoint_id],
            [
                "patient_id",
                "time_days",
                "event",
                "raw_time",
                "raw_event",
                "raw_metadata_json",
            ],
        )

    mapping_path = source_dir / f"{feature_id_type}_to_hugo.json"
    mapping_path.write_text(
        json.dumps(mapping, indent=2, sort_keys=True), encoding="utf-8"
    )
    dataset = dict(spec["dataset"])
    adapter_sha256 = adapter_files_sha256(adapter_files)
    recipe = build_recipe_metadata(
        spec,
        commit_sha,
        adapter_sha256,
        adapter_version=adapter_version,
    )
    specification_sha256 = recipe["specification_sha256"]
    build_recipe_sha256 = recipe["build_recipe_sha256"]
    release_id = (
        f"{dataset['id']}-{commit_sha[:12]}-{build_recipe_sha256[:12]}"
    )
    relative_files = [
        path.relative_to(output_dir)
        for path in [
            *source_paths.values(),
            mapping_path,
            matrix_path,
            matrix_metadata_path,
            genes_path,
            patients_path,
            samples_path,
            *endpoint_paths.values(),
        ]
    ]
    checksums = {
        str(path): sha256_file(output_dir / path)
        for path in sorted(relative_files, key=str)
    }
    manifest = {
        "schema_version": BUNDLE_SCHEMA_VERSION,
        "dataset": dataset,
        "release": {
            "id": release_id,
            "version": (
                f"{release_version_prefix}-{commit_sha[:12]}-recipe-"
                f"{build_recipe_sha256[:8]}"
            ),
            "source_snapshot": commit_sha,
            "source_snapshot_date": commit_date,
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
        },
        "files": {
            "patients": str(patients_path.relative_to(output_dir)),
            "samples": str(samples_path.relative_to(output_dir)),
        },
        "expression_layers": [
            {
                "layer_id": layer_id,
                "label": expression_spec["label"],
                "source_unit": expression_spec["source_unit"],
                "analysis_unit": expression_spec["analysis_unit"],
                "transform": transform,
                "matrix_file": str(matrix_path.relative_to(output_dir)),
                "metadata_file": str(matrix_metadata_path.relative_to(output_dir)),
                "genes_file": str(genes_path.relative_to(output_dir)),
                "is_default": True,
                "downloadable": bool(dataset["redistribution_allowed"]),
                "metadata": {
                    "feature_id_type": feature_id_type,
                    "mapping_source": expression_spec["mapping_source"],
                    "mapping_snapshot_sha256": sha256_file(mapping_path),
                    "dropped_missing_mapping": dropped_missing_mapping,
                    "dropped_duplicate_mapping": dropped_duplicate_mapping,
                    "duplicate_feature_policy": duplicate_policy,
                    "duplicate_feature_rationale": expression_spec.get(
                        "duplicate_feature_rationale"
                    ),
                    "collapsed_source_duplicate_rows": collapsed_source_duplicate_rows,
                    "dropped_incomplete": dropped_incomplete,
                    "scale_note": expression_spec.get("scale_note"),
                    "matrix_build_mode": (
                        "streaming_source_order"
                        if stream_source_order
                        else "sorted_in_memory"
                    ),
                },
            }
        ],
        "endpoints": [
            {
                "endpoint_id": endpoint_spec["endpoint_id"],
                "standard_code": endpoint_spec.get("standard_code"),
                "label": endpoint_spec["label"],
                "time_origin": endpoint_spec["time_origin"],
                "event_definition": endpoint_spec["event_definition"],
                "source_time_column": endpoint_spec["time_column"],
                "source_event_column": endpoint_spec["event_column"],
                "source_time_unit": endpoint_spec["time_unit"],
                "values_file": str(
                    endpoint_paths[str(endpoint_spec["endpoint_id"])].relative_to(
                        output_dir
                    )
                ),
            }
            for endpoint_spec in endpoint_specs
        ],
        "source_files": {
            role: str(path.relative_to(output_dir))
            for role, path in source_paths.items()
        },
        "checksums": checksums,
        "build": {
            "adapter": adapter_version,
            "adapter_sha256": adapter_sha256,
            "specification_sha256": specification_sha256,
            "build_recipe_sha256": build_recipe_sha256,
            "source_expression_samples": len(source_sample_ids),
            "eligible_expression_endpoint_samples": len(eligible_samples),
            "excluded_by_patient_id_pattern": excluded_by_patient_pattern,
            "excluded_by_sample_eligibility": excluded_by_sample_eligibility,
            "sample_eligibility_rules": eligibility_rules,
            "sample_selection_rank_rules": (
                sample_spec.get("selection_rank_rules") or []
            ),
            "endpoints": {
                endpoint_id: {
                    "patients": len(rows),
                    "events": sum(int(row["event"]) for row in rows),
                }
                for endpoint_id, rows in endpoint_rows_by_id.items()
            },
            "mapped_complete_genes": len(filtered_rows),
            **source_build_metadata,
        },
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
    )
    return manifest


def materialize_cbioportal_api_source(
    spec: dict[str, Any],
    source_dir: Path,
) -> tuple[dict[str, Path], str, str | None, dict[str, Any]]:
    source_spec = spec["source"]
    study_id = str(source_spec.get("study_id") or "").strip()
    profile_id = str(source_spec.get("molecular_profile_id") or "").strip()
    sample_list_id = str(source_spec.get("sample_list_id") or "").strip()
    license_url = str(source_spec.get("license_evidence_url") or "").strip()
    if not all((study_id, profile_id, sample_list_id, license_url)):
        raise ValueError(
            "cBioPortal API sources require study_id, "
            "molecular_profile_id, sample_list_id and "
            "license_evidence_url."
        )

    quoted_study = urllib.parse.quote(study_id, safe="")
    quoted_profile = urllib.parse.quote(profile_id, safe="")
    study = request_json(f"{CBIOPORTAL_API}/studies/{quoted_study}")
    profile = request_json(
        f"{CBIOPORTAL_API}/molecular-profiles/{quoted_profile}"
    )
    if (
        not study.get("publicStudy")
        or str(profile.get("studyId") or "") != study_id
        or profile.get("molecularAlterationType") != "MRNA_EXPRESSION"
        or profile.get("datatype") != "CONTINUOUS"
    ):
        raise ValueError(
            "The requested cBioPortal profile is not a public continuous "
            "mRNA-expression profile for the requested study."
        )

    license_suffix = (
        Path(urllib.parse.urlparse(license_url).path).suffix or ".html"
    )
    license_path = source_dir / (
        f"SOURCE_LICENSE_EVIDENCE{license_suffix}"
    )
    download(license_url, license_path)

    sample_lists = request_json(
        f"{CBIOPORTAL_API}/studies/{quoted_study}/sample-lists"
        "?projection=DETAILED"
    )
    selected_lists = [
        row
        for row in sample_lists
        if str(row.get("sampleListId") or "") == sample_list_id
    ]
    if len(selected_lists) != 1:
        raise ValueError(
            f"Expected one cBioPortal sample list {sample_list_id!r}."
        )
    sample_list = selected_lists[0]
    sample_ids = sorted(
        {
            str(sample_id)
            for sample_id in sample_list.get("sampleIds") or []
            if str(sample_id)
        }
    )
    if len(sample_ids) < 10:
        raise ValueError(
            "The cBioPortal expression sample list contains fewer than "
            "10 samples."
        )

    patients = request_json(
        f"{CBIOPORTAL_API}/studies/{quoted_study}/patients"
        "?projection=DETAILED&pageSize=10000000"
    )
    samples = request_json(
        f"{CBIOPORTAL_API}/studies/{quoted_study}/samples"
        "?projection=DETAILED&pageSize=10000000"
    )
    patient_clinical = request_json(
        f"{CBIOPORTAL_API}/studies/{quoted_study}/clinical-data"
        "?clinicalDataType=PATIENT&projection=DETAILED&pageSize=10000000"
    )
    sample_clinical = request_json(
        f"{CBIOPORTAL_API}/studies/{quoted_study}/clinical-data"
        "?clinicalDataType=SAMPLE&projection=DETAILED&pageSize=10000000"
    )
    clinical_attributes = request_json(
        f"{CBIOPORTAL_API}/studies/{quoted_study}/clinical-attributes"
    )

    patient_rows_by_id: dict[str, dict[str, Any]] = {
        str(row["patientId"]): {"PATIENT_ID": str(row["patientId"])}
        for row in patients
        if row.get("patientId")
    }
    for row in patient_clinical:
        patient_id = str(row.get("patientId") or "")
        attribute_id = str(row.get("clinicalAttributeId") or "")
        if not patient_id or not attribute_id:
            continue
        patient_rows_by_id.setdefault(
            patient_id, {"PATIENT_ID": patient_id}
        )[attribute_id] = row.get("value")

    samples_by_id = {
        str(row["sampleId"]): row
        for row in samples
        if row.get("sampleId")
    }
    missing_samples = [
        sample_id
        for sample_id in sample_ids
        if sample_id not in samples_by_id
    ]
    if missing_samples:
        raise ValueError(
            "Expression sample IDs are absent from cBioPortal sample "
            f"metadata: {missing_samples[:5]}"
        )
    sample_rows_by_id: dict[str, dict[str, Any]] = {}
    for sample_id in sample_ids:
        source_sample = samples_by_id[sample_id]
        patient_id = str(source_sample.get("patientId") or "")
        if not patient_id:
            raise ValueError(
                f"Sample {sample_id!r} has no patient identifier."
            )
        sample_rows_by_id[sample_id] = {
            "SAMPLE_ID": sample_id,
            "PATIENT_ID": patient_id,
            "SAMPLE_TYPE": source_sample.get("sampleType"),
        }
        patient_rows_by_id.setdefault(
            patient_id, {"PATIENT_ID": patient_id}
        )
    for row in sample_clinical:
        sample_id = str(row.get("sampleId") or "")
        attribute_id = str(row.get("clinicalAttributeId") or "")
        if (
            sample_id not in sample_rows_by_id
            or not attribute_id
        ):
            continue
        sample_rows_by_id[sample_id][attribute_id] = row.get("value")

    source_sample_count = len(sample_ids)
    source_eligibility_rules = (
        source_spec.get("sample_eligibility_rules") or []
    )
    if source_eligibility_rules:
        sample_ids = [
            sample_id
            for sample_id in sample_ids
            if sample_passes_eligibility(
                patient_rows_by_id[
                    str(sample_rows_by_id[sample_id]["PATIENT_ID"])
                ],
                sample_rows_by_id[sample_id],
                source_eligibility_rules,
            )
        ]
        if len(sample_ids) < 10:
            raise ValueError(
                "Fewer than 10 samples remain after applying the "
                "cBioPortal API source eligibility rules."
            )

    gdc_survival_payload: dict[str, Any] | None = None
    gdc_status_payload: dict[str, Any] | None = None
    gdc_survival_metadata: dict[str, Any] | None = None
    gdc_survival_spec = source_spec.get("gdc_survival")
    if gdc_survival_spec is not None:
        if not isinstance(gdc_survival_spec, dict):
            raise ValueError("source.gdc_survival must be an object.")
        gdc_project_id = str(
            gdc_survival_spec.get("project_id") or ""
        ).strip()
        if not gdc_project_id:
            raise ValueError(
                "source.gdc_survival.project_id is required."
            )
        expression_patient_ids = {
            str(row["PATIENT_ID"])
            for row in sample_rows_by_id.values()
        }
        gdc_survival_payload = fetch_gdc_project_survival(gdc_project_id)
        gdc_status_payload = request_json(f"{GDC_API}/status")
        gdc_survival_metadata = merge_gdc_survival_into_patients(
            patient_rows_by_id,
            expression_patient_ids,
            gdc_survival_payload,
            project_id=gdc_project_id,
            time_column=str(
                gdc_survival_spec.get("time_column")
                or "GDC_OS_DAYS"
            ),
            event_column=str(
                gdc_survival_spec.get("event_column")
                or "GDC_OS_STATUS"
            ),
        )
        gdc_survival_metadata["api_version"] = gdc_status_payload.get(
            "tag"
        )
        gdc_survival_metadata["data_release"] = gdc_status_payload.get(
            "data_release"
        )

    patient_rows = [
        patient_rows_by_id[patient_id]
        for patient_id in sorted(patient_rows_by_id)
    ]
    sample_rows = [
        sample_rows_by_id[sample_id] for sample_id in sample_ids
    ]
    patient_fields = [
        "PATIENT_ID",
        *sorted(
            {
                key
                for row in patient_rows
                for key in row
                if key != "PATIENT_ID"
            }
        ),
    ]
    sample_fields = [
        "SAMPLE_ID",
        "PATIENT_ID",
        *sorted(
            {
                key
                for row in sample_rows
                for key in row
                if key not in {"SAMPLE_ID", "PATIENT_ID"}
            }
        ),
    ]
    patient_table = source_dir / "data_clinical_patient.txt"
    sample_table = source_dir / "data_clinical_sample.txt"
    write_tsv(patient_table, patient_rows, patient_fields)
    write_tsv(sample_table, sample_rows, sample_fields)

    expression_table = source_dir / "data_expression_api.tsv"
    seed_rows = request_json(
        f"{CBIOPORTAL_API}/molecular-profiles/{quoted_profile}"
        "/molecular-data/fetch?projection=SUMMARY",
        method="POST",
        body={"sampleIds": [sample_ids[0]]},
    )
    gene_ids = sorted(
        {
            int(row["entrezGeneId"])
            for row in seed_rows
            if int(row.get("entrezGeneId") or 0) > 0
        }
    )
    if len(gene_ids) < 10_000:
        raise ValueError(
            "The cBioPortal API profile exposes fewer than 10,000 genes."
        )
    sample_index = {
        sample_id: index for index, sample_id in enumerate(sample_ids)
    }
    batch_size = int(source_spec.get("gene_batch_size") or 500)
    if batch_size < 10 or batch_size > 1000:
        raise ValueError("gene_batch_size must be between 10 and 1000.")
    expression_observations = 0
    expression_batches = 0
    with expression_table.open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.writer(
            handle, delimiter="\t", lineterminator="\n"
        )
        writer.writerow(["Entrez_Gene_Id", *sample_ids])
        for start in range(0, len(gene_ids), batch_size):
            batch = gene_ids[start : start + batch_size]
            payload = request_json(
                f"{CBIOPORTAL_API}/molecular-profiles/{quoted_profile}"
                "/molecular-data/fetch?projection=SUMMARY",
                method="POST",
                body={
                    "sampleIds": sample_ids,
                    "entrezGeneIds": batch,
                },
            )
            expression_batches += 1
            values_by_gene: dict[int, list[float | None]] = {
                gene_id: [None] * len(sample_ids) for gene_id in batch
            }
            for row in payload:
                gene_id = int(row.get("entrezGeneId") or 0)
                sample_id = str(row.get("sampleId") or "")
                if (
                    gene_id not in values_by_gene
                    or sample_id not in sample_index
                ):
                    raise ValueError(
                        "cBioPortal returned molecular data outside the "
                        "requested gene/sample batch."
                    )
                index = sample_index[sample_id]
                if values_by_gene[gene_id][index] is not None:
                    raise ValueError(
                        "cBioPortal returned duplicate molecular data for "
                        f"gene {gene_id}, sample {sample_id}."
                    )
                value = float(row["value"])
                if not math.isfinite(value):
                    raise ValueError(
                        "cBioPortal returned a non-finite expression value."
                    )
                values_by_gene[gene_id][index] = value
                expression_observations += 1
            for gene_id in batch:
                writer.writerow(
                    [
                        gene_id,
                        *[
                            "" if value is None else format(value, ".17g")
                            for value in values_by_gene[gene_id]
                        ],
                    ]
                )

    source_paths = {
        "expression": expression_table,
        "patients": patient_table,
        "samples": sample_table,
    }
    json_sources = {
        "study_metadata": ("study.json", study),
        "expression_metadata": ("molecular_profile.json", profile),
        "sample_list_metadata": ("sample_list.json", sample_list),
        "patients_api": (
            "patients_api.json",
            sorted(patients, key=lambda row: str(row.get("patientId") or "")),
        ),
        "samples_api": (
            "samples_api.json",
            sorted(samples, key=lambda row: str(row.get("sampleId") or "")),
        ),
        "patient_clinical_api": (
            "patient_clinical_api.json",
            sorted(
                patient_clinical,
                key=lambda row: (
                    str(row.get("patientId") or ""),
                    str(row.get("clinicalAttributeId") or ""),
                ),
            ),
        ),
        "sample_clinical_api": (
            "sample_clinical_api.json",
            sorted(
                sample_clinical,
                key=lambda row: (
                    str(row.get("sampleId") or ""),
                    str(row.get("clinicalAttributeId") or ""),
                ),
            ),
        ),
        "clinical_attributes_api": (
            "clinical_attributes_api.json",
            sorted(
                clinical_attributes,
                key=lambda row: str(
                    row.get("clinicalAttributeId") or ""
                ),
            ),
        ),
        "expression_gene_ids": (
            "expression_gene_ids.json",
            gene_ids,
        ),
    }
    if gdc_survival_payload is not None and gdc_status_payload is not None:
        json_sources.update(
            {
                "gdc_survival_api": (
                    "gdc_survival_api.json",
                    gdc_survival_payload,
                ),
                "gdc_status_api": (
                    "gdc_status_api.json",
                    gdc_status_payload,
                ),
            }
        )
    for role, (filename, payload) in json_sources.items():
        path = source_dir / filename
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

    source_paths["license"] = license_path
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
    import_date = str(study.get("importDate") or "").strip()
    source_snapshot_date = (
        import_date.replace(" ", "T") + "Z"
        if import_date
        else None
    )
    return (
        source_paths,
        source_snapshot,
        source_snapshot_date,
        {
            "source_api": CBIOPORTAL_API,
            "source_study_id": study_id,
            "source_molecular_profile_id": profile_id,
            "source_sample_list_id": sample_list_id,
            "api_sample_list_samples": source_sample_count,
            "api_expression_samples_requested": len(sample_ids),
            "source_sample_eligibility_rules": source_eligibility_rules,
            "api_expression_genes_requested": len(gene_ids),
            "api_expression_batches": expression_batches,
            "api_expression_observations": expression_observations,
            **(
                {"gdc_survival": gdc_survival_metadata}
                if gdc_survival_metadata is not None
                else {}
            ),
        },
    )


def fetch_gdc_project_survival(project_id: str) -> dict[str, Any]:
    filters = [
        {
            "op": "=",
            "content": {
                "field": "cases.project.project_id",
                "value": project_id,
            },
        }
    ]
    query = urllib.parse.urlencode(
        {
            "filters": json.dumps(
                filters,
                separators=(",", ":"),
            )
        }
    )
    payload = request_json(f"{GDC_API}/analysis/survival?{query}")
    if not isinstance(payload, dict) or not isinstance(
        payload.get("results"), list
    ):
        raise ValueError("GDC returned an invalid survival response.")
    return payload


def merge_gdc_survival_into_patients(
    patient_rows_by_id: dict[str, dict[str, Any]],
    expression_patient_ids: set[str],
    payload: dict[str, Any],
    *,
    project_id: str,
    time_column: str = "GDC_OS_DAYS",
    event_column: str = "GDC_OS_STATUS",
) -> dict[str, Any]:
    donors_by_submitter_id: dict[str, dict[str, Any]] = {}
    for result in payload.get("results") or []:
        for donor in result.get("donors") or []:
            submitter_id = str(donor.get("submitter_id") or "").strip()
            if not submitter_id:
                continue
            donor_project = str(donor.get("project_id") or "").strip()
            if donor_project != project_id:
                raise ValueError(
                    "GDC survival response contains a donor outside "
                    f"project {project_id!r}."
                )
            if submitter_id in donors_by_submitter_id:
                raise ValueError(
                    "GDC survival response contains duplicate submitter ID "
                    f"{submitter_id!r}."
                )
            donors_by_submitter_id[submitter_id] = donor

    matched = 0
    events = 0
    censored = 0
    excluded_nonpositive_time = 0
    status_updates = 0
    for patient_id in sorted(expression_patient_ids):
        patient = patient_rows_by_id.get(patient_id)
        donor = donors_by_submitter_id.get(patient_id)
        if patient is None or donor is None:
            continue
        try:
            time_days = float(donor.get("time"))
        except (TypeError, ValueError):
            continue
        if not math.isfinite(time_days) or time_days <= 0:
            excluded_nonpositive_time += 1
            continue
        donor_censored = donor.get("censored")
        if not isinstance(donor_censored, bool):
            raise ValueError(
                f"GDC survival donor {patient_id!r} has no boolean "
                "censoring status."
            )
        source_status = (
            _clean(patient.get("OS_STATUS"))
            or _clean(patient.get("VITAL_STATUS"))
            or ""
        ).upper()
        source_event = (
            source_status.startswith("1:")
            or source_status in {"DEAD", "DECEASED"}
        )
        source_censored = (
            source_status.startswith("0:")
            or source_status in {"ALIVE", "LIVING"}
        )
        if source_event and donor_censored:
            raise ValueError(
                "GDC marks a cBioPortal-deceased patient as censored: "
                f"{patient_id}."
            )
        if source_censored and not donor_censored:
            status_updates += 1
        event = int(not donor_censored)
        patient[time_column] = format(time_days, ".17g")
        patient[event_column] = (
            "1:DECEASED" if event else "0:CENSORED"
        )
        patient["GDC_SURVIVAL_CASE_ID"] = donor.get("id")
        patient["GDC_SURVIVAL_PROJECT_ID"] = project_id
        matched += 1
        events += event
        censored += int(donor_censored)

    return {
        "api": f"{GDC_API}/analysis/survival",
        "project_id": project_id,
        "expression_patients": len(expression_patient_ids),
        "matched_patients": matched,
        "events": events,
        "censored": censored,
        "missing_patients": len(expression_patient_ids) - matched,
        "excluded_nonpositive_time": excluded_nonpositive_time,
        "source_status_updates": status_updates,
        "time_column": time_column,
        "event_column": event_column,
    }


def resolve_source_file_spec(
    study_path: str,
    file_spec: Any,
) -> tuple[str, str]:
    if isinstance(file_spec, str):
        source_path = file_spec
        scope = "study"
        target_name = Path(file_spec).name
    elif isinstance(file_spec, dict):
        source_path = str(file_spec.get("path") or "")
        scope = str(file_spec.get("scope") or "study")
        target_name = str(
            file_spec.get("target_name") or Path(source_path).name
        )
    else:
        raise ValueError("Source file specifications must be strings or objects.")
    source_path = source_path.strip("/")
    if (
        not source_path
        or source_path.startswith("../")
        or "/../" in source_path
        or scope not in {"study", "repository"}
    ):
        raise ValueError(f"Invalid source file specification: {file_spec!r}")
    if (
        not target_name
        or target_name != Path(target_name).name
        or target_name in {".", ".."}
    ):
        raise ValueError(f"Invalid source target name: {target_name!r}")
    relative = (
        source_path
        if scope == "repository"
        else f"{study_path}/{source_path}"
    )
    return relative, target_name


def build_recipe_metadata(
    spec: dict[str, Any],
    source_snapshot: str,
    adapter_sha256: str,
    *,
    adapter_version: str = ADAPTER_VERSION,
) -> dict[str, str]:
    specification_sha256 = hashlib.sha256(
        json.dumps(
            spec, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()
    build_recipe_sha256 = hashlib.sha256(
        json.dumps(
            {
                "adapter_sha256": adapter_sha256,
                "adapter_version": adapter_version,
                "source_snapshot": source_snapshot,
                "specification_sha256": specification_sha256,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return {
        "adapter_sha256": adapter_sha256,
        "specification_sha256": specification_sha256,
        "build_recipe_sha256": build_recipe_sha256,
    }


def source_attribute(
    patient: dict[str, str],
    sample: dict[str, str],
    field: Any,
) -> str | None:
    source_name, separator, column = str(field).partition(".")
    if not separator or source_name not in {"patient", "sample"}:
        raise ValueError(
            f"Invalid sample rule field {field!r}; use patient.COLUMN or sample.COLUMN."
        )
    source = patient if source_name == "patient" else sample
    return _clean(source.get(column))


def sample_passes_eligibility(
    patient: dict[str, str],
    sample: dict[str, str],
    rules: Any,
) -> bool:
    if not isinstance(rules, list):
        raise ValueError("samples.eligibility_rules must be a list.")
    for rule in rules:
        if not isinstance(rule, dict) or not rule.get("field"):
            raise ValueError("Each sample eligibility rule requires a field.")
        value = source_attribute(patient, sample, rule["field"])
        normalized = value.casefold() if value is not None else None
        included = {
            str(item).strip().casefold()
            for item in rule.get("include") or []
        }
        excluded = {
            str(item).strip().casefold()
            for item in rule.get("exclude") or []
        }
        if included and normalized not in included:
            return False
        if excluded and normalized in excluded:
            return False
        if bool(rule.get("required")) and value is None:
            return False
    return True


def sample_selection_rank(
    patient: dict[str, str],
    sample: dict[str, str],
    sample_spec: dict[str, Any],
) -> int:
    rules = sample_spec.get("selection_rank_rules") or []
    if not rules:
        return int(sample_spec.get("selection_rank", 0))
    rank = 0
    for rule in rules:
        if not isinstance(rule, dict) or not rule.get("field"):
            raise ValueError("Each sample selection-rank rule requires a field.")
        order = [str(item).strip().casefold() for item in rule.get("order") or []]
        if len(order) >= 1000:
            raise ValueError("A sample selection-rank rule cannot exceed 999 values.")
        value = source_attribute(patient, sample, rule["field"])
        normalized = value.casefold() if value is not None else None
        default_rank = int(rule.get("default_rank", len(order)))
        component = (
            order.index(normalized)
            if normalized in order
            else default_rank
        )
        if component < 0 or component >= 1000:
            raise ValueError("Sample selection-rank components must be between 0 and 999.")
        rank = rank * 1000 + component
    return rank


def latest_path_commit(
    repository: str, path: str, branch: str
) -> dict[str, Any]:
    query = urllib.parse.urlencode(
        {"path": path, "sha": branch, "per_page": 1}
    )
    payload = request_json(
        f"{GITHUB_API}/repos/{repository}/commits?{query}"
    )
    if not isinstance(payload, list) or not payload:
        raise ValueError(f"No commits found for {repository}/{path}.")
    return payload[0]


def fetch_gene_mapping(
    ids: Iterable[str], feature_id_type: str
) -> dict[str, str]:
    if feature_id_type == "entrez_gene_id":
        return fetch_entrez_mapping(ids)
    if feature_id_type == "hugo_symbol":
        return fetch_hugo_mapping(ids)
    if feature_id_type == "provided_ensembl_hugo":
        return fetch_provided_ensembl_hugo_mapping(ids)
    if feature_id_type == "provided_hugo_symbol":
        return {
            str(value).strip().upper(): str(value).strip().upper()
            for value in ids
            if str(value).strip()
        }
    raise ValueError(
        f"Unsupported expression feature_id_type: {feature_id_type!r}"
    )


def fetch_entrez_mapping(ids: Iterable[str]) -> dict[str, str]:
    unique = sorted({value for value in ids if value and value != "0"})
    mapping: dict[str, str] = {}
    for start in range(0, len(unique), 500):
        chunk = unique[start : start + 500]
        payload = request_json(
            f"{CBIOPORTAL_API}/genes/fetch?geneIdType=ENTREZ_GENE_ID&projection=DETAILED",
            method="POST",
            body=chunk,
        )
        for row in payload:
            entrez = str(row.get("entrezGeneId") or "").strip()
            symbol = str(row.get("hugoGeneSymbol") or "").strip().upper()
            if entrez and symbol:
                mapping[entrez] = symbol
    return mapping


def fetch_hugo_mapping(ids: Iterable[str]) -> dict[str, str]:
    unique = sorted({value.upper() for value in ids if value})
    unique_set = set(unique)
    mapping: dict[str, str] = {}
    for start in range(0, len(unique), 500):
        chunk = unique[start : start + 500]
        payload = request_json(
            f"{CBIOPORTAL_API}/genes/fetch?geneIdType=HUGO_GENE_SYMBOL&projection=DETAILED",
            method="POST",
            body=chunk,
        )
        for row in payload:
            symbol = str(row.get("hugoGeneSymbol") or "").strip().upper()
            if symbol and symbol in unique_set:
                mapping[symbol] = symbol
    return mapping


def fetch_provided_ensembl_hugo_mapping(
    ids: Iterable[str],
) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for value in ids:
        source_id = str(value).strip()
        ensembl_id, separator, symbol = source_id.partition("|")
        symbol = symbol.strip().upper()
        if (
            not separator
            or not ensembl_id.startswith("ENSG")
            or not symbol
        ):
            continue
        mapping[source_id.upper()] = symbol
    return mapping


def duplicated_mapping_symbols(mapping: dict[str, str]) -> set[str]:
    counts: dict[str, int] = {}
    for symbol in mapping.values():
        counts[symbol] = counts.get(symbol, 0) + 1
    return {symbol for symbol, count in counts.items() if count > 1}


def duplicated_source_feature_symbols(
    ids: Iterable[str],
    feature_id_type: str,
) -> set[str]:
    if feature_id_type not in {
        "hugo_symbol",
        "provided_hugo_symbol",
    }:
        return set()
    counts: dict[str, int] = {}
    for value in ids:
        symbol = str(value).strip().upper()
        if symbol:
            counts[symbol] = counts.get(symbol, 0) + 1
    return {
        symbol for symbol, count in counts.items() if count > 1
    }


def source_feature_ids_match(
    first: str, second: str, feature_id_type: str
) -> bool:
    if first == second:
        return True
    return (
        feature_id_type
        in {
            "hugo_symbol",
            "provided_ensembl_hugo",
            "provided_hugo_symbol",
        }
        and first.upper() == second.upper()
    )


def adapter_files_sha256(paths: Iterable[Path]) -> str:
    resolved = sorted({path.resolve() for path in paths}, key=str)
    if len(resolved) == 1:
        return sha256_file(resolved[0])
    payload = {
        path.name: sha256_file(path)
        for path in resolved
    }
    return hashlib.sha256(
        json.dumps(
            payload, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()


def parse_endpoint(
    patient: dict[str, str], spec: dict[str, Any]
) -> dict[str, Any] | None:
    raw_time = _clean(patient.get(spec["time_column"]))
    raw_event = _clean(patient.get(spec["event_column"]))
    if raw_time is None or raw_event is None:
        return None
    try:
        value = float(raw_time)
    except ValueError:
        return None
    if value <= 0:
        return None
    event_prefix = str(spec.get("event_prefix") or "1:")
    censor_prefix = str(spec.get("censor_prefix") or "0:")
    if raw_event.startswith(event_prefix):
        event = 1
    elif raw_event.startswith(censor_prefix):
        event = 0
    else:
        return None
    unit = str(spec["time_unit"]).lower()
    if unit == "days":
        time_days = value
    elif unit == "months":
        time_days = value * MONTH_DAYS
    elif unit == "years":
        time_days = value * YEAR_DAYS
    else:
        raise ValueError(f"Unsupported endpoint time unit: {unit}")
    return {
        "time_days": f"{time_days:.12g}",
        "event": str(event),
        "raw_time": raw_time,
        "raw_event": raw_event,
    }


def read_cbioportal_table(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8", errors="strict") as handle:
        lines = (line for line in handle if not line.startswith("#"))
        return list(csv.DictReader(lines, delimiter="\t"))


def read_expression_header(path: Path) -> list[str]:
    with open_expression_text(path) as handle:
        reader = csv.reader(handle, delimiter=expression_delimiter(path))
        return next(reader)


def iter_expression_rows(path: Path) -> Iterable[list[str]]:
    with open_expression_text(path) as handle:
        reader = csv.reader(handle, delimiter=expression_delimiter(path))
        next(reader)
        yield from (row for row in reader if row)


def expression_feature_ids(path: Path) -> list[str]:
    return [
        row[0].strip()
        for row in iter_expression_rows(path)
        if row and row[0].strip()
    ]


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
        newline="", encoding="utf-8", errors="strict"
    )


def expression_delimiter(path: Path) -> str:
    suffixes = [suffix.lower() for suffix in path.suffixes]
    return "," if ".csv" in suffixes else "\t"


def apply_expression_transform(
    values: list[float], transform: str
) -> list[float]:
    if transform == "identity":
        return values
    if transform == "log2p":
        return [math.log2(value + 1.0) for value in values]
    raise ValueError(f"Unsupported expression transform: {transform!r}")


def resolve_patient_attribute(
    patient: dict[str, str],
    sample: dict[str, str],
    configured_fields: Any,
    default_fields: list[str],
) -> str:
    fields = configured_fields if isinstance(configured_fields, list) else default_fields
    for field in fields:
        source_name, separator, column = str(field).partition(".")
        if not separator or source_name not in {"patient", "sample"}:
            raise ValueError(
                f"Invalid patient attribute source {field!r}; use patient.COLUMN or sample.COLUMN."
            )
        source = patient if source_name == "patient" else sample
        value = _clean(source.get(column))
        if value is not None:
            return value
    return ""


def download(url: str, path: Path) -> None:
    last_error: Exception | None = None
    for attempt in range(NETWORK_ATTEMPTS):
        request = urllib.request.Request(
            url, headers={"User-Agent": USER_AGENT}
        )
        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                path.parent.mkdir(parents=True, exist_ok=True)
                with path.open("wb") as handle:
                    shutil.copyfileobj(response, handle)
            return
        except urllib.error.HTTPError as exc:
            if exc.code not in RETRYABLE_HTTP_CODES:
                raise
            last_error = exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_error = exc
        if attempt + 1 < NETWORK_ATTEMPTS:
            time.sleep(2**attempt)
    if last_error is not None:
        raise last_error
    raise RuntimeError(f"Could not download {url}.")


def download_with_fallback(urls: list[str], path: Path) -> None:
    errors: list[str] = []
    for url in urls:
        try:
            download(url, path)
            return
        except urllib.error.HTTPError as exc:
            errors.append(f"{url}: HTTP {exc.code}")
    raise RuntimeError(
        f"Could not download {path.name}. " + "; ".join(errors)
    )


def request_json(
    url: str,
    *,
    method: str = "GET",
    body: Any = None,
) -> Any:
    data = (
        json.dumps(body, separators=(",", ":")).encode("utf-8")
        if body is not None
        else None
    )
    last_error: Exception | None = None
    for attempt in range(NETWORK_ATTEMPTS):
        request = urllib.request.Request(
            url,
            data=data,
            method=method,
            headers={
                "Accept": "application/json",
                "Accept-Encoding": "gzip",
                "Content-Type": "application/json",
                "User-Agent": USER_AGENT,
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                if response.headers.get("Content-Encoding") == "gzip":
                    with gzip.GzipFile(fileobj=response) as compressed:
                        return json.load(compressed)
                return json.load(response)
        except urllib.error.HTTPError as exc:
            if exc.code not in RETRYABLE_HTTP_CODES:
                raise
            last_error = exc
        except (
            urllib.error.URLError,
            TimeoutError,
            OSError,
            json.JSONDecodeError,
        ) as exc:
            last_error = exc
        if attempt + 1 < NETWORK_ATTEMPTS:
            time.sleep(2**attempt)
    if last_error is not None:
        raise last_error
    raise RuntimeError(f"Could not retrieve JSON from {url}.")


def write_tsv(
    path: Path, rows: list[dict[str, Any]], fieldnames: list[str]
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fieldnames,
            delimiter="\t",
            lineterminator="\n",
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(rows)


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    missing_values = {
        "NA",
        "N/A",
        "NULL",
        "[NOT AVAILABLE]",
        "[NOT APPLICABLE]",
    }
    return text if text and text.upper() not in missing_values else None
