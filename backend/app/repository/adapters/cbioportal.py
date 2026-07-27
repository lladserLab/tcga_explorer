from __future__ import annotations

import csv
from datetime import datetime, timezone
import io
import json
import math
from pathlib import Path
import shutil
from typing import Any, Iterable
import urllib.parse
import urllib.error
import urllib.request

from app.repository.importer import BUNDLE_SCHEMA_VERSION
from app.repository.storage import sha256_file, write_float32le_matrix


GITHUB_API = "https://api.github.com"
CBIOPORTAL_API = "https://www.cbioportal.org/api"
USER_AGENT = "TCGA-TRACE-curated-repository/1.0"
MONTH_DAYS = 365.25 / 12.0
YEAR_DAYS = 365.25


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
    repository = str(source_spec["repository"])
    branch = str(source_spec.get("branch") or "master")
    study_path = str(source_spec["study_path"]).strip("/")
    commit = latest_path_commit(repository, study_path, branch)
    commit_sha = str(commit["sha"])
    commit_date = (
        commit.get("commit", {}).get("committer", {}).get("date")
        or commit.get("commit", {}).get("author", {}).get("date")
    )

    source_paths: dict[str, Path] = {}
    for role, filename in source_spec["files"].items():
        relative = f"{study_path}/{filename}"
        media_url = (
            "https://media.githubusercontent.com/media/"
            f"{repository}/{commit_sha}/{relative}"
        )
        raw_url = (
            "https://raw.githubusercontent.com/"
            f"{repository}/{commit_sha}/{relative}"
        )
        target = source_dir / filename
        download_with_fallback([media_url, raw_url], target)
        source_paths[role] = target

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
    eligible_samples: list[str] = []
    patient_rows: list[dict[str, Any]] = []
    sample_rows: list[dict[str, Any]] = []
    seen_patients: set[str] = set()
    for sample_id in source_sample_ids:
        sample = sample_by_id.get(sample_id)
        if sample is None:
            continue
        patient_id = str(sample.get("PATIENT_ID") or "").strip()
        patient = patient_by_id.get(patient_id)
        if patient is None:
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
                    sample_spec.get("selection_rank", 0)
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
    duplicate_symbols = duplicated_mapping_symbols(mapping)
    filtered_rows: list[tuple[str, str, list[float]]] = []
    dropped_missing_mapping = 0
    dropped_duplicate_mapping = 0
    collapsed_source_duplicate_rows = 0
    dropped_incomplete = 0
    duplicate_policy = expression_spec.get("duplicate_feature_policy")
    retained_by_symbol: dict[str, tuple[str, list[float], int]] = {}
    transform = str(expression_spec.get("transform") or "identity").lower()
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
            raw_values = [float(row[index + 1]) for index in selected_indexes]
        except (IndexError, TypeError, ValueError):
            dropped_incomplete += 1
            continue
        if any(not math.isfinite(value) for value in raw_values):
            dropped_incomplete += 1
            continue
        if transform == "log2p" and any(value < 0 for value in raw_values):
            dropped_incomplete += 1
            continue
        existing = retained_by_symbol.get(symbol)
        if existing is not None:
            if (
                existing[0] == original_id
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
                f"Canonical symbol {symbol} maps to non-identical source rows "
                f"{existing[0]} and {original_id}; provide an explicit curation override."
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
        for symbol, (original_id, sums, count) in retained_by_symbol.items()
    ]

    filtered_rows.sort(key=lambda row: (row[1], row[0]))
    if len(filtered_rows) < 10_000:
        raise ValueError(
            f"Only {len(filtered_rows)} uniquely mapped complete genes remain."
        )

    layer_id = str(expression_spec["layer_id"])
    matrix_path = derived_dir / f"{layer_id}.float32le.bin"
    write_float32le_matrix(
        matrix_path, (values for _, _, values in filtered_rows)
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
    release_id = f"{dataset['id']}-{commit_sha[:12]}"
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
            "version": f"datahub-{commit_sha[:12]}",
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
            "adapter": "cbioportal_datahub_v1",
            "source_expression_samples": len(source_sample_ids),
            "eligible_expression_endpoint_samples": len(eligible_samples),
            "endpoints": {
                endpoint_id: {
                    "patients": len(rows),
                    "events": sum(int(row["event"]) for row in rows),
                }
                for endpoint_id, rows in endpoint_rows_by_id.items()
            },
            "mapped_complete_genes": len(filtered_rows),
        },
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
    )
    return manifest


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


def duplicated_mapping_symbols(mapping: dict[str, str]) -> set[str]:
    counts: dict[str, int] = {}
    for symbol in mapping.values():
        counts[symbol] = counts.get(symbol, 0) + 1
    return {symbol for symbol, count in counts.items() if count > 1}


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
    with path.open(newline="", encoding="utf-8", errors="strict") as handle:
        reader = csv.reader(handle, delimiter="\t")
        return next(reader)


def iter_expression_rows(path: Path) -> Iterable[list[str]]:
    with path.open(newline="", encoding="utf-8", errors="strict") as handle:
        reader = csv.reader(handle, delimiter="\t")
        next(reader)
        yield from (row for row in reader if row)


def expression_feature_ids(path: Path) -> list[str]:
    return [
        row[0].strip()
        for row in iter_expression_rows(path)
        if row and row[0].strip()
    ]


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
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=180) as response:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as handle:
            shutil.copyfileobj(response, handle)


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
    request = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
        },
    )
    with urllib.request.urlopen(request, timeout=180) as response:
        return json.load(response)


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
    return text if text and text.upper() not in {"NA", "N/A", "NULL"} else None
