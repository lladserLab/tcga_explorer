from __future__ import annotations

import csv
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
from pathlib import PurePosixPath
import re
import shutil
import subprocess
import tarfile
import tempfile
import time
from typing import Any, Iterable
import urllib.error
import urllib.parse
import urllib.request

from app.repository.adapters.cbioportal import USER_AGENT, write_tsv
from app.repository.adapters.pmc import canonical_json
from app.repository.storage import sha256_file


NOTTINGHAM_ADAPTER_VERSION = "nottingham_biostudies_raw_v3"
ICART1_LAYOUT = "icart1_bcss"
ICART1_2_LAYOUT = "icart1_2_bcss_dmfs"
SUPPORTED_LAYOUTS = {ICART1_LAYOUT, ICART1_2_LAYOUT}
DEFAULT_MIN_MAPPED_FRAGMENTS = 1_000_000
DEFAULT_MIN_MAPPING_RATE = 10.0
PARTIAL_DECOY_METHOD = "mashmap2_exon_masked_v1"
PREBUILT_PARTIAL_INDEX_METHOD = "refgenie_salmon_partial_sa_index_v1"
DOWNLOAD_ATTEMPTS = 6
GENCODE_TRANSCRIPT_PATTERN = re.compile(r'transcript_id "([^"]+)"')
GENCODE_TRANSCRIPT_VERSION_PATTERN = re.compile(
    r'transcript_version "([^"]+)"'
)
GENCODE_GENE_PATTERN = re.compile(r'gene_id "([^"]+)"')
GENCODE_GENE_VERSION_PATTERN = re.compile(r'gene_version "([^"]+)"')
GENCODE_SYMBOL_PATTERN = re.compile(r'gene_name "([^"]+)"')
GENTROME_GENE_PATTERN = re.compile(r"(?:^| )gene:([^ ]+)")
GENTROME_SYMBOL_PATTERN = re.compile(r"(?:^| )gene_symbol:([^ ]+)")


def materialize_nottingham_source(
    spec: dict[str, Any],
    source_dir: Path,
) -> tuple[dict[str, Path], str, str | None, dict[str, Any]]:
    source_spec = spec["source"]
    accession = required_text(source_spec, "accession")
    layout = required_text(source_spec, "layout")
    if layout not in SUPPORTED_LAYOUTS:
        raise ValueError(f"Unsupported Nottingham layout: {layout!r}.")

    cache_root = Path(
        os.environ.get("NOTTINGHAM_QUANT_CACHE_DIR")
        or Path(tempfile.gettempdir()) / "tcga-trace-nottingham"
    ).expanduser()
    cache_root.mkdir(parents=True, exist_ok=True)
    source_dir.mkdir(parents=True, exist_ok=True)

    metadata_specs = source_spec.get("files") or {}
    required_roles = {"idf", "sdrf", "ena_report", "license"}
    missing_roles = sorted(required_roles - metadata_specs.keys())
    if missing_roles:
        raise ValueError(
            "Nottingham source is missing pinned files: "
            + ", ".join(missing_roles)
        )
    downloaded: dict[str, Path] = {}
    pinned_metadata: dict[str, dict[str, Any]] = {}
    for role in sorted(required_roles):
        file_spec = validate_pinned_file_spec(
            metadata_specs[role], label=role
        )
        cached = (
            cache_root
            / "metadata"
            / f"{file_spec['sha256'][:12]}-{file_spec['name']}"
        )
        materialize_sha256_download(file_spec, cached)
        target = source_dir / file_spec["name"]
        shutil.copy2(cached, target)
        downloaded[role] = target
        pinned_metadata[role] = file_manifest_entry(file_spec, target)

    if accession not in downloaded["idf"].read_text(
        encoding="utf-8", errors="strict"
    ):
        raise ValueError(
            "Nottingham IDF does not contain the expected accession."
        )

    ena_runs = parse_ena_report(
        downloaded["ena_report"],
        expected_study_accession=required_text(
            source_spec, "ena_study_accession"
        ),
    )
    participants = parse_nottingham_sdrf(
        downloaded["sdrf"],
        layout=layout,
        ena_runs=ena_runs,
    )
    validate_nottingham_expectations(
        participants,
        expected_participants=int(
            source_spec.get("expected_source_participants") or 0
        ),
        expected_bcss_events=int(
            source_spec.get("expected_bcss_events") or 0
        ),
        expected_dmfs_events=(
            int(source_spec["expected_dmfs_events"])
            if source_spec.get("expected_dmfs_events") is not None
            else None
        ),
    )

    salmon_binary = str(
        os.environ.get("SALMON_BINARY")
        or source_spec.get("salmon_binary")
        or shutil.which("salmon")
        or ""
    ).strip()
    if not salmon_binary:
        raise RuntimeError(
            "Salmon is required; set SALMON_BINARY or install salmon."
        )
    salmon_binary = str(
        Path(shutil.which(salmon_binary) or salmon_binary)
        .expanduser()
        .resolve()
    )
    if not Path(salmon_binary).is_file():
        raise RuntimeError(f"Salmon binary not found: {salmon_binary}.")
    salmon_version = resolve_salmon_version(salmon_binary)
    salmon_binary_sha256 = sha256_file(Path(salmon_binary))
    expected_salmon_version = str(
        source_spec.get("salmon_version") or ""
    ).strip()
    if (
        expected_salmon_version
        and salmon_version != expected_salmon_version
    ):
        raise ValueError(
            "Salmon version changed: "
            f"{salmon_version!r} != {expected_salmon_version!r}."
        )

    threads = int(
        os.environ.get("NOTTINGHAM_SALMON_THREADS")
        or source_spec.get("salmon_threads")
        or min(8, os.cpu_count() or 1)
    )
    if threads < 1:
        raise ValueError("salmon_threads must be positive.")
    min_mapped_fragments = int(
        source_spec.get("min_mapped_fragments")
        or DEFAULT_MIN_MAPPED_FRAGMENTS
    )
    min_mapping_rate = float(
        source_spec.get("min_mapping_rate")
        or DEFAULT_MIN_MAPPING_RATE
    )
    if min_mapped_fragments < 1 or not 0 <= min_mapping_rate <= 100:
        raise ValueError("Invalid Nottingham quantification QC thresholds.")

    prebuilt_reference_value = source_spec.get(
        "prebuilt_salmon_reference"
    )
    reference_specs = source_spec.get("reference_files") or {}
    if prebuilt_reference_value is not None:
        if reference_specs or source_spec.get("partial_decoy") is not None:
            raise ValueError(
                "Configure either prebuilt_salmon_reference or the local "
                "reference_files/partial_decoy route, not both."
            )
        reference = prepare_prebuilt_salmon_reference(
            prebuilt_reference_value,
            cache_root=cache_root,
            salmon_version=salmon_version,
            salmon_binary_sha256=salmon_binary_sha256,
        )
    else:
        partial_decoy = validate_partial_decoy_spec(
            source_spec.get("partial_decoy")
        )
        mashmap_binary = resolve_required_binary(
            env_name="NOTTINGHAM_MASHMAP_BINARY",
            configured=source_spec.get("mashmap_binary"),
            default_name="mashmap",
            label="MashMap",
        )
        bedtools_binary = resolve_required_binary(
            env_name="NOTTINGHAM_BEDTOOLS_BINARY",
            configured=source_spec.get("bedtools_binary"),
            default_name="bedtools",
            label="bedtools",
        )
        mashmap_binary_sha256 = sha256_file(Path(mashmap_binary))
        bedtools_binary_sha256 = sha256_file(Path(bedtools_binary))
        if mashmap_binary_sha256 != partial_decoy[
            "mashmap_executable_sha256"
        ]:
            raise ValueError("MashMap executable checksum changed.")
        observed_bedtools_version = resolve_bedtools_version(
            bedtools_binary
        )
        if observed_bedtools_version != partial_decoy[
            "bedtools_version"
        ]:
            raise ValueError(
                "bedtools version changed: "
                f"{observed_bedtools_version!r} != "
                f"{partial_decoy['bedtools_version']!r}."
            )
        if bedtools_binary_sha256 != partial_decoy[
            "bedtools_executable_sha256"
        ]:
            raise ValueError("bedtools executable checksum changed.")
        reference = prepare_salmon_reference(
            reference_specs,
            cache_root=cache_root,
            salmon_binary=salmon_binary,
            salmon_version=salmon_version,
            salmon_binary_sha256=salmon_binary_sha256,
            partial_decoy=partial_decoy,
            mashmap_binary=mashmap_binary,
            mashmap_binary_sha256=mashmap_binary_sha256,
            bedtools_binary=bedtools_binary,
            bedtools_binary_sha256=bedtools_binary_sha256,
            threads=threads,
        )
    quant_options = salmon_quant_options(
        threads=threads,
        extra_options=source_spec.get("salmon_quant_options") or [],
    )
    quant_signature = hashlib.sha256(
        canonical_json(
            {
                "adapter_version": NOTTINGHAM_ADAPTER_VERSION,
                "salmon_version": salmon_version,
                "salmon_binary_sha256": salmon_binary_sha256,
                "reference_snapshot": reference["snapshot"],
                "quant_options": quant_options,
                "min_mapped_fragments": min_mapped_fragments,
                "min_mapping_rate": min_mapping_rate,
            }
        ).encode("utf-8")
    ).hexdigest()

    selected: list[dict[str, Any]] = []
    run_ledger: list[dict[str, Any]] = []
    for participant_id in sorted(
        participants, key=natural_identifier_key
    ):
        participant = participants[participant_id]
        ranked_runs = rank_participant_runs(participant["runs"])
        selected_result: dict[str, Any] | None = None
        for rank, run in enumerate(ranked_runs, start=1):
            quant_result = quantify_nottingham_run(
                run,
                cache_root=cache_root,
                accession=accession,
                salmon_binary=salmon_binary,
                salmon_version=salmon_version,
                salmon_binary_sha256=salmon_binary_sha256,
                index_dir=reference["index_dir"],
                tx2gene_path=reference["tx2gene_path"],
                quant_options=quant_options,
                quant_signature=quant_signature,
                min_mapped_fragments=min_mapped_fragments,
                min_mapping_rate=min_mapping_rate,
            )
            ledger_row = {
                "participant_source_id": participant_id,
                "rank": rank,
                "run_accession": run["run_accession"],
                "base_count": run["base_count"],
                "read_count": run["read_count"],
                "status": (
                    "selected"
                    if quant_result["qc_passed"]
                    else "failed_qc"
                ),
                "mapping_rate": quant_result["mapping_rate"],
                "mapped_fragments": quant_result["mapped_fragments"],
                "processed_fragments": quant_result[
                    "processed_fragments"
                ],
                "quant_genes_sha256": quant_result[
                    "quant_genes_sha256"
                ],
                "fastq_input_signature": quant_result[
                    "fastq_input_signature"
                ],
                "quant_reused": quant_result["quant_reused"],
                "quant_source_accession": quant_result[
                    "source_accession"
                ],
                "quant_source_run_accession": quant_result[
                    "run_accession"
                ],
                "qc_reason": quant_result.get("qc_reason") or "",
            }
            run_ledger.append(ledger_row)
            if quant_result["qc_passed"]:
                selected_result = {
                    "participant": participant,
                    "run": run,
                    "rank": rank,
                    "quant": quant_result,
                }
                break
        if selected_result is None:
            run_ledger.append(
                {
                    "participant_source_id": participant_id,
                    "rank": "",
                    "run_accession": "",
                    "base_count": "",
                    "read_count": "",
                    "status": "participant_excluded_no_qc_run",
                    "mapping_rate": "",
                    "mapped_fragments": "",
                    "processed_fragments": "",
                    "quant_genes_sha256": "",
                    "fastq_input_signature": "",
                    "quant_reused": "",
                    "quant_source_accession": "",
                    "quant_source_run_accession": "",
                    "qc_reason": (
                        "No candidate run satisfied the prespecified "
                        "quantification QC thresholds."
                    ),
                }
            )
            continue
        selected.append(selected_result)

    if len(selected) < 10:
        raise ValueError(
            "Fewer than 10 Nottingham participants retained a "
            "QC-passing expression profile."
        )

    patient_table, sample_table = materialize_nottingham_clinical_tables(
        selected,
        source_dir=source_dir,
        accession=accession,
        layout=layout,
    )
    expression_table = source_dir / "data_expression_selected.tsv"
    expression_summary = materialize_nottingham_expression(
        selected,
        expression_table,
    )
    run_ledger_path = source_dir / "nottingham_run_selection.tsv"
    write_tsv(
        run_ledger_path,
        run_ledger,
        [
            "participant_source_id",
            "rank",
            "run_accession",
            "base_count",
            "read_count",
            "status",
            "mapping_rate",
            "mapped_fragments",
            "processed_fragments",
            "quant_genes_sha256",
            "fastq_input_signature",
            "quant_reused",
            "quant_source_accession",
            "quant_source_run_accession",
            "qc_reason",
        ],
    )

    quant_manifest_payload = {
        "schema_version": (
            "tcga-trace-nottingham-quantification-manifest-v1"
        ),
        "accession": accession,
        "layout": layout,
        "adapter_version": NOTTINGHAM_ADAPTER_VERSION,
        "salmon": {
            "version": salmon_version,
            "binary_sha256": salmon_binary_sha256,
            "options": quant_options,
        },
        "reference": {
            "snapshot": reference["snapshot"],
            "method": reference["method"],
            "files": reference["files"],
            "details": reference["details"],
        },
        "qc": {
            "minimum_mapped_fragments": min_mapped_fragments,
            "minimum_mapping_rate_percent": min_mapping_rate,
        },
        "source_participants": len(participants),
        "retained_participants": len(selected),
        "excluded_participants": len(participants) - len(selected),
        "runs": run_ledger,
    }
    quant_manifest_path = (
        source_dir / "nottingham_quantification_manifest.json"
    )
    quant_manifest_path.write_text(
        canonical_json(quant_manifest_payload) + "\n",
        encoding="utf-8",
    )

    source_snapshot_payload = {
        "accession": accession,
        "layout": layout,
        "metadata_files": pinned_metadata,
        "quantification_manifest_sha256": sha256_file(
            quant_manifest_path
        ),
    }
    source_snapshot = hashlib.sha256(
        canonical_json(source_snapshot_payload).encode("utf-8")
    ).hexdigest()
    source_manifest_path = source_dir / "nottingham_source_manifest.json"
    source_manifest_path.write_text(
        canonical_json(
            {
                "schema_version": (
                    "tcga-trace-nottingham-source-manifest-v1"
                ),
                **source_snapshot_payload,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    endpoint_summary = summarize_selected_endpoints(selected, layout)
    source_paths = {
        "expression": expression_table,
        "patients": patient_table,
        "samples": sample_table,
        "idf": downloaded["idf"],
        "sdrf": downloaded["sdrf"],
        "ena_report": downloaded["ena_report"],
        "license": downloaded["license"],
        "run_selection": run_ledger_path,
        "quantification_manifest": quant_manifest_path,
        "source_manifest": source_manifest_path,
    }
    return (
        source_paths,
        source_snapshot,
        str(source_spec.get("publication_date") or "") or None,
        {
            "source_accession": accession,
            "source_pinned_files": pinned_metadata,
            "source_participants": len(participants),
            "source_runs": len(ena_runs),
            "retained_participants": len(selected),
            "excluded_participants": len(participants) - len(selected),
            "selected_fallback_runs": sum(
                int(int(row["rank"]) > 1)
                for row in run_ledger
                if row["status"] == "selected"
            ),
            "reused_quantifications": sum(
                int(row["quant_reused"] is True)
                for row in run_ledger
                if row["status"] in {"selected", "failed_qc"}
            ),
            "salmon_version": salmon_version,
            "salmon_quant_options": quant_options,
            "reference_snapshot": reference["snapshot"],
            "quantification_qc": quant_manifest_payload["qc"],
            "source_endpoint_summary": endpoint_summary,
            **expression_summary,
        },
    )


def parse_ena_report(
    path: Path,
    *,
    expected_study_accession: str,
) -> dict[str, dict[str, Any]]:
    required = {
        "run_accession",
        "study_accession",
        "sample_accession",
        "experiment_accession",
        "library_layout",
        "read_count",
        "base_count",
        "fastq_ftp",
        "fastq_md5",
        "fastq_bytes",
        "submitted_ftp",
        "submitted_md5",
        "submitted_bytes",
    }
    with path.open(
        newline="", encoding="utf-8-sig", errors="strict"
    ) as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        missing = sorted(required - set(reader.fieldnames or []))
        if missing:
            raise ValueError(
                "ENA report lacks required columns: " + ", ".join(missing)
            )
        runs: dict[str, dict[str, Any]] = {}
        for line_number, row in enumerate(reader, start=2):
            run_accession = str(row["run_accession"]).strip()
            if (
                not re.fullmatch(r"[SED]RR\d+", run_accession)
                or run_accession in runs
            ):
                raise ValueError(
                    f"Invalid or duplicate ENA run at line {line_number}."
                )
            study_accession = str(row["study_accession"]).strip()
            if study_accession != expected_study_accession:
                raise ValueError(
                    "ENA study accession changed at line "
                    f"{line_number}: {study_accession!r}."
                )
            library_layout = str(row["library_layout"]).strip().upper()
            if library_layout != "PAIRED":
                raise ValueError(
                    f"ENA run {run_accession} is not paired-end."
                )
            submitted_files = parse_ena_file_set(
                row,
                prefix="submitted",
                run_accession=run_accession,
            )
            generated_files = parse_ena_file_set(
                row,
                prefix="fastq",
                run_accession=run_accession,
            )
            if len(submitted_files) == 2:
                files = submitted_files
                fastq_source = "submitted"
            elif len(generated_files) == 2:
                files = generated_files
                fastq_source = "archive_generated"
            else:
                raise ValueError(
                    f"ENA run {run_accession} has no pinned mate pair."
                )
            runs[run_accession] = {
                "run_accession": run_accession,
                "study_accession": study_accession,
                "sample_accession": str(
                    row["sample_accession"]
                ).strip(),
                "experiment_accession": str(
                    row["experiment_accession"]
                ).strip(),
                "read_count": parse_positive_int(
                    row["read_count"], "read count"
                ),
                "base_count": parse_positive_int(
                    row["base_count"], "base count"
                ),
                "library_layout": library_layout,
                "fastq_source": fastq_source,
                "fastq_files": files,
                "reported_fastq_name_sets": [
                    sorted(item["name"] for item in file_set)
                    for file_set in (submitted_files, generated_files)
                    if file_set
                ],
            }
    if not runs:
        raise ValueError("ENA report contains no runs.")
    return runs


def parse_ena_file_set(
    row: dict[str, Any],
    *,
    prefix: str,
    run_accession: str,
) -> list[dict[str, Any]]:
    paths = split_semicolon_field(row.get(f"{prefix}_ftp"))
    md5_values = split_semicolon_field(row.get(f"{prefix}_md5"))
    raw_sizes = split_semicolon_field(row.get(f"{prefix}_bytes"))
    if not paths and not md5_values and not raw_sizes:
        return []
    if not (len(paths) == len(md5_values) == len(raw_sizes)):
        raise ValueError(
            f"ENA run {run_accession} has incomplete {prefix} pins."
        )
    files = []
    for ftp_path, md5_value, raw_size in zip(
        paths, md5_values, raw_sizes, strict=True
    ):
        normalized_md5 = md5_value.lower()
        if not re.fullmatch(r"[0-9a-f]{32}", normalized_md5):
            raise ValueError(
                f"ENA run {run_accession} has an invalid {prefix} MD5."
            )
        parsed = urllib.parse.urlparse(ftp_path)
        url = ftp_path if parsed.scheme else f"https://{ftp_path}"
        if url.startswith("ftp://"):
            url = "https://" + url.removeprefix("ftp://")
        files.append(
            {
                "url": url,
                "name": Path(urllib.parse.urlparse(url).path).name,
                "size": parse_positive_int(raw_size, f"{prefix} FASTQ size"),
                "md5": normalized_md5,
            }
        )
    return files


def parse_nottingham_sdrf(
    path: Path,
    *,
    layout: str,
    ena_runs: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    if layout not in SUPPORTED_LAYOUTS:
        raise ValueError(f"Unsupported Nottingham layout: {layout!r}.")
    with path.open(
        newline="", encoding="utf-8-sig", errors="strict"
    ) as handle:
        reader = csv.reader(handle, delimiter="\t")
        header = next(reader)
        indexes = nottingham_sdrf_indexes(header, layout)
        rows = list(reader)

    run_rows: dict[str, list[list[str]]] = {}
    for line_number, row in enumerate(rows, start=2):
        if len(row) != len(header):
            raise ValueError(
                "Nottingham SDRF row width changed at line "
                f"{line_number}: {len(row)} != {len(header)}."
            )
        run_accession = row[indexes["run_accession"]].strip()
        if run_accession not in ena_runs:
            raise ValueError(
                f"SDRF run {run_accession!r} is absent from ENA."
            )
        run_rows.setdefault(run_accession, []).append(row)

    if set(run_rows) != set(ena_runs):
        raise ValueError(
            "Nottingham SDRF and ENA run inventories differ."
        )

    participants: dict[str, dict[str, Any]] = {}
    for run_accession in sorted(run_rows):
        mates = run_rows[run_accession]
        if len(mates) != 2:
            raise ValueError(
                f"SDRF run {run_accession} does not have two mate rows."
            )
        first = mates[0]
        stable_columns = [
            name
            for name in indexes
            if name not in {"fastq_uri", "submitted_file"}
        ]
        for name in stable_columns:
            values = {
                row[indexes[name]].strip()
                for row in mates
            }
            if len(values) != 1:
                raise ValueError(
                    f"SDRF run {run_accession} changes {name} by mate."
                )

        ena_run = dict(ena_runs[run_accession])
        biosd_sample = first[indexes["biosd_sample"]].strip()
        if ena_run["sample_accession"] != biosd_sample:
            raise ValueError(
                f"SDRF/ENA sample mismatch for {run_accession}."
            )
        sdrf_fastq_names = sorted(
            Path(
                urllib.parse.urlparse(
                    row[indexes["fastq_uri"]].strip()
                ).path
            ).name
            for row in mates
        )
        sdrf_submitted_names = sorted(
            Path(row[indexes["submitted_file"]].strip()).name
            for row in mates
        )
        if not any(
            names in ena_run["reported_fastq_name_sets"]
            for names in (sdrf_fastq_names, sdrf_submitted_names)
        ):
            raise ValueError(
                f"SDRF/ENA FASTQ mismatch for {run_accession}."
            )

        clinical = parse_nottingham_clinical(first, indexes, layout)
        participant_id = (
            first[indexes["individual"]].strip()
            if layout == ICART1_LAYOUT
            else first[indexes["source_name"]].strip()
        )
        if not participant_id:
            raise ValueError(
                f"SDRF run {run_accession} has no participant identifier."
            )
        run_record = {
            **ena_run,
            "source_name": first[indexes["source_name"]].strip(),
            "ena_sample": first[indexes["ena_sample"]].strip(),
            "biosd_sample": biosd_sample,
            "rna_identifier": first[indexes["rna_identifier"]].strip(),
            "clinical": clinical,
        }
        participant = participants.setdefault(
            participant_id,
            {
                "participant_source_id": participant_id,
                "clinical": clinical,
                "runs": [],
            },
        )
        assert_consistent_clinical_core(
            participant["clinical"],
            clinical,
            participant_id=participant_id,
        )
        participant["runs"].append(run_record)

    if len(participants) < 10:
        raise ValueError(
            "Nottingham SDRF yielded fewer than 10 participants."
        )
    return participants


def nottingham_sdrf_indexes(
    header: list[str], layout: str
) -> dict[str, int]:
    common = {
        "source_name": "Source Name",
        "ena_sample": "Comment[ENA_SAMPLE]",
        "biosd_sample": "Comment[BioSD_SAMPLE]",
        "rna_identifier": (
            "Comment[id assigned at time of rna-sequencing]"
        ),
        "disease": "Characteristics[disease]",
        "run_accession": "Comment[ENA_RUN]",
        "fastq_uri": "Comment[FASTQ_URI]",
        "submitted_file": "Comment[SUBMITTED_FILE_NAME]",
    }
    if layout == ICART1_LAYOUT:
        common.update(
            {
                "individual": "Characteristics[individual]",
                "age": "Characteristics[age at diagnosis]",
                "grade": "Characteristics[nottingham grade]",
                "bcss_status": (
                    "Characteristics[censoring for breast "
                    "cancer-specific survival]"
                ),
                "bcss_time": (
                    "Characteristics[breast cancer-specific "
                    "survival in months]"
                ),
            }
        )
    else:
        common.update(
            {
                "age": "Characteristics[age]",
                "sex": "Characteristics[sex]",
                "stage": "Characteristics[disease staging]",
                "bcss_status": "Characteristics[organism status]",
                "bcss_time": "Characteristics[survival time]",
                "dmfs_status": (
                    "Characteristics[distant metastasis status]"
                ),
                "dmfs_time": (
                    "Characteristics[distant metastasis time]"
                ),
            }
        )
    indexes = {}
    for key, name in common.items():
        matches = [
            index for index, value in enumerate(header) if value == name
        ]
        if len(matches) != 1:
            raise ValueError(
                f"Nottingham SDRF requires exactly one {name!r} column."
            )
        indexes[key] = matches[0]
    return indexes


def parse_nottingham_clinical(
    row: list[str],
    indexes: dict[str, int],
    layout: str,
) -> dict[str, Any]:
    disease = row[indexes["disease"]].strip().casefold()
    if disease != "triple-negative breast cancer":
        raise ValueError(
            f"Unexpected Nottingham disease label: {disease!r}."
        )
    age = parse_positive_float(row[indexes["age"]], "age")
    bcss_months = parse_positive_float(
        row[indexes["bcss_time"]], "BCSS time"
    )
    raw_bcss_status = row[indexes["bcss_status"]].strip()
    normalized_bcss = raw_bcss_status.casefold()
    if layout == ICART1_LAYOUT:
        if normalized_bcss == "death from breast cancer":
            bcss_event = 1
        elif normalized_bcss == (
            "alive, death from other causes, death from unknown cause"
        ):
            bcss_event = 0
        else:
            raise ValueError(
                f"Unsupported ICART1 BCSS status: {raw_bcss_status!r}."
            )
        return {
            "age": age,
            "grade": row[indexes["grade"]].strip(),
            "stage": "",
            "sex": "",
            "bcss_months": bcss_months,
            "bcss_event": bcss_event,
            "raw_bcss_status": raw_bcss_status,
        }

    if normalized_bcss == "died from breast cancer":
        bcss_event = 1
    elif normalized_bcss in {"alive", "dead - unknown cause"}:
        bcss_event = 0
    else:
        raise ValueError(
            f"Unsupported ICART1-2 BCSS status: {raw_bcss_status!r}."
        )
    raw_dmfs_status = row[indexes["dmfs_status"]].strip()
    normalized_dmfs = raw_dmfs_status.casefold()
    if normalized_dmfs not in {"yes", "no"}:
        raise ValueError(
            f"Unsupported ICART1-2 DMFS status: {raw_dmfs_status!r}."
        )
    dmfs_months = parse_nonnegative_float(
        row[indexes["dmfs_time"]], "DMFS time"
    )
    return {
        "age": age,
        "grade": "",
        "stage": row[indexes["stage"]].strip(),
        "sex": row[indexes["sex"]].strip(),
        "bcss_months": bcss_months,
        "bcss_event": bcss_event,
        "raw_bcss_status": raw_bcss_status,
        "dmfs_months": dmfs_months,
        "dmfs_event": int(normalized_dmfs == "yes"),
        "raw_dmfs_status": raw_dmfs_status,
    }


def assert_consistent_clinical_core(
    first: dict[str, Any],
    second: dict[str, Any],
    *,
    participant_id: str,
) -> None:
    fields = {
        "age",
        "bcss_months",
        "bcss_event",
        "dmfs_months",
        "dmfs_event",
    }
    changed = sorted(
        field
        for field in fields
        if field in first or field in second
        if first.get(field) != second.get(field)
    )
    if changed:
        raise ValueError(
            "Nottingham participant "
            f"{participant_id!r} has inconsistent clinical fields: "
            + ", ".join(changed)
        )


def validate_nottingham_expectations(
    participants: dict[str, dict[str, Any]],
    *,
    expected_participants: int,
    expected_bcss_events: int,
    expected_dmfs_events: int | None,
) -> None:
    if expected_participants and len(participants) != expected_participants:
        raise ValueError(
            "Nottingham participant count changed: "
            f"{len(participants)} != {expected_participants}."
        )
    bcss_events = sum(
        int(row["clinical"]["bcss_event"])
        for row in participants.values()
    )
    if expected_bcss_events and bcss_events != expected_bcss_events:
        raise ValueError(
            "Nottingham BCSS event count changed: "
            f"{bcss_events} != {expected_bcss_events}."
        )
    if expected_dmfs_events is not None:
        dmfs_events = sum(
            int(row["clinical"]["dmfs_event"])
            for row in participants.values()
        )
        if dmfs_events != expected_dmfs_events:
            raise ValueError(
                "Nottingham DMFS event count changed: "
                f"{dmfs_events} != {expected_dmfs_events}."
            )


def rank_participant_runs(
    runs: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    return sorted(
        runs,
        key=lambda row: (
            -int(row["base_count"]),
            str(row["run_accession"]),
        ),
    )


def prepare_salmon_reference(
    reference_specs: dict[str, Any],
    *,
    cache_root: Path,
    salmon_binary: str,
    salmon_version: str,
    salmon_binary_sha256: str,
    partial_decoy: dict[str, Any],
    mashmap_binary: str,
    mashmap_binary_sha256: str,
    bedtools_binary: str,
    bedtools_binary_sha256: str,
    threads: int,
) -> dict[str, Any]:
    required = {"transcripts", "annotation", "genome"}
    missing = sorted(required - reference_specs.keys())
    if missing:
        raise ValueError(
            "Nottingham reference is missing pinned files: "
            + ", ".join(missing)
        )
    validated = {
        role: validate_pinned_file_spec(
            reference_specs[role], label=f"reference {role}"
        )
        for role in sorted(required)
    }
    snapshot_payload = {
        "adapter_version": NOTTINGHAM_ADAPTER_VERSION,
        "reference_files": validated,
        "salmon_version": salmon_version,
        "salmon_binary_sha256": salmon_binary_sha256,
        "partial_decoy": {
            **partial_decoy,
            "mashmap_binary_sha256": mashmap_binary_sha256,
            "bedtools_binary_sha256": bedtools_binary_sha256,
        },
        "index_options": [
            "--gencode",
            "--decoys",
            "decoys.txt",
            "-k",
            "31",
        ],
    }
    snapshot = hashlib.sha256(
        canonical_json(snapshot_payload).encode("utf-8")
    ).hexdigest()
    index_root = cache_root / "index" / snapshot[:20]
    index_dir = index_root / "salmon_index"
    tx2gene_path = index_root / "tx2gene.tsv"
    manifest_path = index_root / "reference_manifest.json"
    if (
        manifest_path.is_file()
        and index_dir.is_dir()
        and tx2gene_path.is_file()
    ):
        observed = json.loads(manifest_path.read_text(encoding="utf-8"))
        if (
            observed.get("snapshot") == snapshot
            and (index_dir / "versionInfo.json").is_file()
        ):
            return {
                "snapshot": snapshot,
                "index_dir": index_dir,
                "tx2gene_path": tx2gene_path,
                "method": PARTIAL_DECOY_METHOD,
                "files": observed["reference_files"],
                "details": {
                    "partial_decoy": observed["partial_decoy"]
                },
            }

    reference_paths = {}
    for role, file_spec in validated.items():
        target = (
            cache_root
            / "reference"
            / f"{file_spec['sha256'][:12]}-{file_spec['name']}"
        )
        materialize_sha256_download(file_spec, target)
        reference_paths[role] = target

    staging = index_root.with_name(
        f"{index_root.name}.tmp-{os.getpid()}"
    )
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    staging_index = staging / "salmon_index"
    staging_tx2gene = staging / "tx2gene.tsv"
    build_tx2gene(
        reference_paths["annotation"],
        staging_tx2gene,
    )
    gentrome_path = staging / "gentrome.fa"
    decoys_path = staging / "decoys.txt"
    partial_decoy_summary = build_partial_decoy_gentrome(
        reference_paths["transcripts"],
        reference_paths["annotation"],
        reference_paths["genome"],
        gentrome_path,
        decoys_path,
        work_dir=staging / "partial_decoy_work",
        mashmap_binary=mashmap_binary,
        bedtools_binary=bedtools_binary,
        threads=threads,
        identity_percent=partial_decoy["identity_percent"],
        segment_length=partial_decoy["segment_length"],
    )
    command = [
        salmon_binary,
        "index",
        "-t",
        str(gentrome_path),
        "-d",
        str(decoys_path),
        "-i",
        str(staging_index),
        "--gencode",
        "-k",
        "31",
        "-p",
        str(threads),
    ]
    run_logged_command(
        command,
        stdout_path=staging / "salmon-index.stdout.log",
        stderr_path=staging / "salmon-index.stderr.log",
    )
    if not (staging_index / "versionInfo.json").is_file():
        raise RuntimeError("Salmon did not produce a valid index.")
    partial_decoy_manifest = {
        **partial_decoy,
        "mashmap_binary_sha256": mashmap_binary_sha256,
        "bedtools_binary_sha256": bedtools_binary_sha256,
        **partial_decoy_summary,
    }
    gentrome_path.unlink()
    shutil.rmtree(staging / "partial_decoy_work")
    manifest_payload = {
        "schema_version": (
            "tcga-trace-nottingham-reference-manifest-v1"
        ),
        "snapshot": snapshot,
        "salmon_version": salmon_version,
        "salmon_binary_sha256": salmon_binary_sha256,
        "command": command,
        "partial_decoy": partial_decoy_manifest,
        "reference_files": {
            role: {
                "url": validated[role]["url"],
                "name": validated[role]["name"],
                "size": reference_paths[role].stat().st_size,
                "sha256": sha256_file(reference_paths[role]),
            }
            for role in sorted(reference_paths)
        },
        "tx2gene_sha256": sha256_file(staging_tx2gene),
    }
    (staging / "reference_manifest.json").write_text(
        canonical_json(manifest_payload) + "\n",
        encoding="utf-8",
    )
    if index_root.exists():
        shutil.rmtree(index_root)
    staging.rename(index_root)
    return {
        "snapshot": snapshot,
        "index_dir": index_dir,
        "tx2gene_path": tx2gene_path,
        "method": PARTIAL_DECOY_METHOD,
        "files": manifest_payload["reference_files"],
        "details": {"partial_decoy": partial_decoy_manifest},
    }


def prepare_prebuilt_salmon_reference(
    value: Any,
    *,
    cache_root: Path,
    salmon_version: str,
    salmon_binary_sha256: str,
) -> dict[str, Any]:
    spec = validate_prebuilt_salmon_reference_spec(value)
    snapshot_payload = {
        "adapter_version": NOTTINGHAM_ADAPTER_VERSION,
        "prebuilt_salmon_reference": spec,
        "quant_salmon_version": salmon_version,
        "quant_salmon_binary_sha256": salmon_binary_sha256,
    }
    snapshot = hashlib.sha256(
        canonical_json(snapshot_payload).encode("utf-8")
    ).hexdigest()
    index_root = cache_root / "index" / snapshot[:20]
    index_dir = index_root / "salmon_index"
    tx2gene_path = index_root / "tx2gene.tsv"
    manifest_path = index_root / "reference_manifest.json"
    if (
        manifest_path.is_file()
        and index_dir.is_dir()
        and tx2gene_path.is_file()
        and (index_dir / "versionInfo.json").is_file()
    ):
        observed = json.loads(manifest_path.read_text(encoding="utf-8"))
        if observed.get("snapshot") == snapshot:
            return {
                "snapshot": snapshot,
                "index_dir": index_dir,
                "tx2gene_path": tx2gene_path,
                "method": PREBUILT_PARTIAL_INDEX_METHOD,
                "files": observed["reference_files"],
                "details": observed["prebuilt_index"],
            }

    archive_spec = spec["archive"]
    archive_path = (
        cache_root
        / "reference"
        / f"{archive_spec['sha256'][:12]}-{archive_spec['name']}"
    )
    materialize_sha256_download(archive_spec, archive_path)
    staging = index_root.with_name(
        f"{index_root.name}.tmp-{os.getpid()}"
    )
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    staging_index = staging / "salmon_index"
    staging_index.mkdir()
    staging_tx2gene = staging / "tx2gene.tsv"
    extracted_files, tx2gene_rows = extract_prebuilt_salmon_index(
        archive_path,
        staging_index,
        tx2gene_path=staging_tx2gene,
        archive_root=spec["archive_root"],
        gentrome_name=spec["gentrome_name"],
    )
    if tx2gene_rows != spec["expected_tx2gene_rows"]:
        raise ValueError(
            "Prebuilt reference transcript-to-gene row count changed: "
            f"{tx2gene_rows} != {spec['expected_tx2gene_rows']}."
        )

    version_info = json.loads(
        (staging_index / "versionInfo.json").read_text(
            encoding="utf-8"
        )
    )
    info = json.loads(
        (staging_index / "info.json").read_text(encoding="utf-8")
    )
    if (
        int(version_info.get("indexVersion") or -1)
        != spec["index_version"]
        or str(version_info.get("salmonVersion") or "")
        != spec["built_salmon_version"]
    ):
        raise ValueError("Prebuilt Salmon index version metadata changed.")
    if (
        int(info.get("num_decoys") or -1)
        != spec["expected_decoys"]
        or int(info.get("first_decoy_index") or -1)
        != spec["expected_first_decoy_index"]
        or int(info.get("num_kmers") or -1)
        != spec["expected_kmers"]
    ):
        raise ValueError("Prebuilt Salmon index content metadata changed.")

    reference_files = {
        "archive": {
            key: archive_spec[key]
            for key in ("url", "name", "size", "sha256")
        },
        "tx2gene_source": {
            "archive_member": (
                f"{spec['archive_root']}/{spec['gentrome_name']}"
            ),
            "method": (
                "transcript, gene and gene_symbol fields parsed from "
                "the exact indexed gentrome FASTA headers"
            ),
        },
    }
    index_summary = {
        "archive_root": spec["archive_root"],
        "refgenie_genome_digest": spec["refgenie_genome_digest"],
        "refgenie_asset_digest": spec["refgenie_asset_digest"],
        "built_salmon_version": spec["built_salmon_version"],
        "index_version": spec["index_version"],
        "quant_salmon_version": salmon_version,
        "extracted_index_files": extracted_files,
        "index_info": info,
        "tx2gene_rows": tx2gene_rows,
        "tx2gene_sha256": sha256_file(staging_tx2gene),
        "omitted_archive_members": [
            "gentrome.fa",
            "*.gtf",
            "pre_indexing.log",
            "ref_indexing.log",
        ],
    }
    manifest_payload = {
        "schema_version": (
            "tcga-trace-nottingham-reference-manifest-v2"
        ),
        "snapshot": snapshot,
        "method": PREBUILT_PARTIAL_INDEX_METHOD,
        "quant_salmon_binary_sha256": salmon_binary_sha256,
        "reference_files": reference_files,
        "prebuilt_index": index_summary,
    }
    (staging / "reference_manifest.json").write_text(
        canonical_json(manifest_payload) + "\n",
        encoding="utf-8",
    )
    if index_root.exists():
        shutil.rmtree(index_root)
    staging.rename(index_root)
    return {
        "snapshot": snapshot,
        "index_dir": index_dir,
        "tx2gene_path": tx2gene_path,
        "method": PREBUILT_PARTIAL_INDEX_METHOD,
        "files": reference_files,
        "details": index_summary,
    }


def extract_prebuilt_salmon_index(
    archive_path: Path,
    index_dir: Path,
    *,
    tx2gene_path: Path,
    archive_root: str,
    gentrome_name: str,
    minimum_tx2gene_rows: int = 100_000,
) -> tuple[list[str], int]:
    required_index_files = {
        "complete_ref_lens.bin",
        "ctable.bin",
        "ctg_offsets.bin",
        "info.json",
        "mphf.bin",
        "pos.bin",
        "rank.bin",
        "refAccumLengths.bin",
        "reflengths.bin",
        "refseq.bin",
        "seq.bin",
        "versionInfo.json",
    }
    skipped = {
        "pre_indexing.log",
        "ref_indexing.log",
    }
    extracted: list[str] = []
    tx2gene_rows: int | None = None
    with tarfile.open(archive_path, "r:gz") as archive:
        for member in archive:
            member_path = PurePosixPath(member.name)
            if (
                member_path.is_absolute()
                or ".." in member_path.parts
                or not member_path.parts
                or member_path.parts[0] != archive_root
            ):
                raise ValueError(
                    f"Unsafe or unexpected reference member: "
                    f"{member.name!r}."
                )
            relative = PurePosixPath(*member_path.parts[1:])
            if not relative.parts:
                if not member.isdir():
                    raise ValueError("Reference archive root is not a dir.")
                continue
            if len(relative.parts) != 1:
                raise ValueError(
                    f"Nested reference member is not supported: "
                    f"{member.name!r}."
                )
            name = relative.name
            if member.isdir():
                continue
            if not member.isfile():
                raise ValueError(
                    f"Reference member is not a regular file: "
                    f"{member.name!r}."
                )
            if name in skipped:
                continue
            source = archive.extractfile(member)
            if source is None:
                raise ValueError(
                    f"Could not read reference member {member.name!r}."
                )
            if name == gentrome_name:
                with source:
                    tx2gene_rows = build_tx2gene_from_gentrome(
                        source,
                        tx2gene_path,
                        minimum_rows=minimum_tx2gene_rows,
                    )
                continue
            if name.endswith(".gtf"):
                source.close()
                continue
            target = index_dir / name
            target.parent.mkdir(parents=True, exist_ok=True)
            with source, target.open("wb") as output:
                shutil.copyfileobj(
                    source, output, length=8 * 1024 * 1024
                )
            extracted.append(name)
    if tx2gene_rows is None:
        raise ValueError("Reference archive gentrome FASTA is missing.")
    missing = sorted(required_index_files - set(extracted))
    if missing:
        raise ValueError(
            "Reference archive is missing index files: "
            + ", ".join(missing)
        )
    return sorted(extracted), tx2gene_rows


def build_tx2gene_from_gentrome(
    source: Any,
    output_path: Path,
    *,
    minimum_rows: int = 100_000,
) -> int:
    rows: dict[str, str] = {}
    for raw_line in source:
        if not raw_line.startswith(b">"):
            continue
        header = raw_line[1:].decode(
            "utf-8", errors="strict"
        ).rstrip("\r\n")
        transcript_id = header.split(" ", 1)[0].strip()
        gene_match = GENTROME_GENE_PATTERN.search(header)
        symbol_match = GENTROME_SYMBOL_PATTERN.search(header)
        if not transcript_id or not gene_match:
            continue
        if not symbol_match:
            raise ValueError(
                f"Gentrome transcript {transcript_id} has no gene symbol."
            )
        gene_id = gene_match.group(1).strip()
        symbol = symbol_match.group(1).strip().upper()
        if not gene_id or not symbol or "|" in symbol:
            raise ValueError(
                f"Gentrome transcript {transcript_id} has invalid genes."
            )
        gene_key = f"{gene_id}|{symbol}"
        existing = rows.setdefault(transcript_id, gene_key)
        if existing != gene_key:
            raise ValueError(
                f"Transcript {transcript_id} maps to multiple genes."
            )
    if len(rows) < minimum_rows:
        raise ValueError(
            f"Only {len(rows)} gentrome transcript rows were parsed."
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        for transcript_id, gene_key in sorted(rows.items()):
            writer.writerow([transcript_id, gene_key])
    return len(rows)


def build_tx2gene(
    annotation_path: Path,
    output_path: Path,
    *,
    minimum_rows: int = 100_000,
) -> int:
    opener = gzip.open if annotation_path.suffix == ".gz" else open
    rows: dict[str, str] = {}
    with opener(
        annotation_path, "rt", encoding="utf-8", errors="strict"
    ) as handle:
        for line in handle:
            if line.startswith("#"):
                continue
            columns = line.rstrip("\n").split("\t")
            if len(columns) != 9 or columns[2] != "transcript":
                continue
            attributes = columns[8]
            transcript_match = GENCODE_TRANSCRIPT_PATTERN.search(attributes)
            gene_match = GENCODE_GENE_PATTERN.search(attributes)
            symbol_match = GENCODE_SYMBOL_PATTERN.search(attributes)
            if not transcript_match or not gene_match or not symbol_match:
                continue
            transcript_id = transcript_match.group(1)
            gene_id = gene_match.group(1)
            transcript_version_match = (
                GENCODE_TRANSCRIPT_VERSION_PATTERN.search(attributes)
            )
            gene_version_match = GENCODE_GENE_VERSION_PATTERN.search(
                attributes
            )
            if (
                transcript_version_match
                and "." not in transcript_id
            ):
                transcript_id = (
                    f"{transcript_id}."
                    f"{transcript_version_match.group(1)}"
                )
            if gene_version_match and "." not in gene_id:
                gene_id = f"{gene_id}.{gene_version_match.group(1)}"
            symbol = symbol_match.group(1).strip().upper()
            if not symbol or "|" in symbol:
                continue
            gene_key = f"{gene_id}|{symbol}"
            existing = rows.setdefault(transcript_id, gene_key)
            if existing != gene_key:
                raise ValueError(
                    f"Transcript {transcript_id} maps to multiple genes."
                )
    if len(rows) < minimum_rows:
        raise ValueError(
            f"Only {len(rows)} transcript-to-gene rows were parsed."
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        for transcript_id, gene_key in sorted(rows.items()):
            writer.writerow([transcript_id, gene_key])
    return len(rows)


def build_partial_decoy_gentrome(
    transcripts_path: Path,
    annotation_path: Path,
    genome_path: Path,
    gentrome_path: Path,
    decoys_path: Path,
    *,
    work_dir: Path,
    mashmap_binary: str,
    bedtools_binary: str,
    threads: int,
    identity_percent: int,
    segment_length: int,
) -> dict[str, Any]:
    if threads < 1 or not 1 <= identity_percent <= 100:
        raise ValueError("Invalid partial-decoy processing parameters.")
    if segment_length < 1:
        raise ValueError("Partial-decoy segment length must be positive.")

    work_dir.mkdir(parents=True, exist_ok=False)
    transcripts_fasta = work_dir / "transcripts.fa"
    annotation_gtf = work_dir / "annotation.gtf"
    genome_fasta = work_dir / "genome.fa"
    decompress_reference_file(transcripts_path, transcripts_fasta)
    decompress_reference_file(annotation_path, annotation_gtf)
    decompress_reference_file(genome_path, genome_fasta)

    genome_contigs = fasta_record_names(genome_fasta)
    if not genome_contigs or len(genome_contigs) != len(
        set(genome_contigs)
    ):
        raise ValueError("Genome FASTA did not yield unique contigs.")

    exons_bed = work_dir / "exons.bed"
    exon_count = write_exon_bed(annotation_gtf, exons_bed)
    masked_genome = work_dir / "reference.masked.genome.fa"
    run_logged_command(
        [
            bedtools_binary,
            "maskfasta",
            "-fi",
            str(genome_fasta),
            "-bed",
            str(exons_bed),
            "-fo",
            str(masked_genome),
        ],
        stdout_path=work_dir / "bedtools-maskfasta.stdout.log",
        stderr_path=work_dir / "bedtools-maskfasta.stderr.log",
    )

    mashmap_output = work_dir / "mashmap.out"
    run_logged_command(
        [
            mashmap_binary,
            "-r",
            str(masked_genome),
            "-q",
            str(transcripts_fasta),
            "-t",
            str(threads),
            "--pi",
            str(identity_percent),
            "-s",
            str(segment_length),
            "-o",
            str(mashmap_output),
        ],
        stdout_path=work_dir / "mashmap.stdout.log",
        stderr_path=work_dir / "mashmap.stderr.log",
    )
    intervals = parse_mashmap_intervals(
        mashmap_output,
        allowed_contigs=set(genome_contigs),
    )
    found_bed = work_dir / "genome_found.sorted.bed"
    write_bed_intervals(found_bed, intervals)

    merged_bed = work_dir / "genome_found_merged.bed"
    run_logged_command(
        [bedtools_binary, "merge", "-i", str(found_bed)],
        stdout_path=merged_bed,
        stderr_path=work_dir / "bedtools-merge.stderr.log",
    )
    merged_intervals = read_bed_intervals(
        merged_bed,
        allowed_contigs=set(genome_contigs),
    )
    found_fasta = work_dir / "genome_found.fa"
    run_logged_command(
        [
            bedtools_binary,
            "getfasta",
            "-fi",
            str(masked_genome),
            "-bed",
            str(merged_bed),
            "-fo",
            str(found_fasta),
        ],
        stdout_path=work_dir / "bedtools-getfasta.stdout.log",
        stderr_path=work_dir / "bedtools-getfasta.stderr.log",
    )

    found_sequences = list(read_fasta_sequences(found_fasta))
    if len(found_sequences) != len(merged_intervals):
        raise ValueError(
            "Partial-decoy interval and FASTA record counts differ."
        )
    decoy_parts: dict[str, list[str]] = {}
    for interval, (_, sequence) in zip(
        merged_intervals, found_sequences, strict=True
    ):
        decoy_parts.setdefault(interval[0], []).append(sequence)
    decoy_sequences = [
        (contig, "".join(decoy_parts[contig]))
        for contig in genome_contigs
        if contig in decoy_parts
    ]
    if not decoy_sequences:
        raise ValueError("MashMap yielded no partial decoy sequences.")

    decoy_fasta = work_dir / "decoy.fa"
    write_fasta_sequences(decoy_fasta, decoy_sequences)
    decoys_path.parent.mkdir(parents=True, exist_ok=True)
    decoys_path.write_text(
        "".join(f"{name}\n" for name, _ in decoy_sequences),
        encoding="ascii",
    )
    gentrome_path.parent.mkdir(parents=True, exist_ok=True)
    with gentrome_path.open("wb") as output:
        for source in (transcripts_fasta, decoy_fasta):
            with source.open("rb") as handle:
                shutil.copyfileobj(handle, output, length=1024 * 1024)

    return {
        "exon_mask_coordinate_conversion": (
            "GTF 1-based inclusive to BED 0-based half-open"
        ),
        "exons_masked": exon_count,
        "mashmap_hits": len(intervals),
        "merged_decoy_intervals": len(merged_intervals),
        "decoy_sequences": len(decoy_sequences),
        "decoy_bases": sum(
            len(sequence) for _, sequence in decoy_sequences
        ),
        "decoys_sha256": sha256_file(decoys_path),
        "decoy_fasta_sha256": sha256_file(decoy_fasta),
        "gentrome_sha256": sha256_file(gentrome_path),
    }


def decompress_reference_file(source: Path, target: Path) -> None:
    opener = gzip.open if source.suffix == ".gz" else open
    target.parent.mkdir(parents=True, exist_ok=True)
    with opener(source, "rb") as input_handle, target.open(
        "wb"
    ) as output_handle:
        shutil.copyfileobj(
            input_handle,
            output_handle,
            length=4 * 1024 * 1024,
        )


def fasta_record_names(path: Path) -> list[str]:
    names = []
    with path.open("rt", encoding="ascii", errors="strict") as handle:
        for line in handle:
            if not line.startswith(">"):
                continue
            name = line[1:].split(None, 1)[0].strip()
            if not name:
                raise ValueError(f"Blank FASTA record name in {path}.")
            names.append(name)
    return names


def write_exon_bed(annotation_path: Path, output_path: Path) -> int:
    count = 0
    with annotation_path.open(
        "rt", encoding="utf-8", errors="strict"
    ) as input_handle, output_path.open(
        "w", encoding="ascii", newline=""
    ) as output_handle:
        writer = csv.writer(
            output_handle, delimiter="\t", lineterminator="\n"
        )
        for line_number, line in enumerate(input_handle, start=1):
            interval = parse_gtf_exon_interval(
                line,
                line_number=line_number,
            )
            if interval is None:
                continue
            writer.writerow(interval)
            count += 1
    if count < 100_000:
        raise ValueError(f"Only {count} exon intervals were parsed.")
    return count


def parse_gtf_exon_interval(
    line: str,
    *,
    line_number: int,
) -> tuple[str, int, int] | None:
    if line.startswith("#"):
        return None
    columns = line.rstrip("\n").split("\t")
    if len(columns) != 9 or columns[2] != "exon":
        return None
    try:
        start = int(columns[3]) - 1
        end = int(columns[4])
    except ValueError as error:
        raise ValueError(
            f"Invalid GTF coordinates at line {line_number}."
        ) from error
    if start < 0 or end <= start:
        raise ValueError(f"Invalid GTF interval at line {line_number}.")
    return columns[0], start, end


def parse_mashmap_intervals(
    path: Path,
    *,
    allowed_contigs: set[str],
) -> list[tuple[str, int, int]]:
    intervals = []
    with path.open("rt", encoding="utf-8", errors="strict") as handle:
        for line_number, line in enumerate(handle, start=1):
            fields = line.split()
            if len(fields) < 9:
                raise ValueError(
                    f"Malformed MashMap output at line {line_number}."
                )
            contig = fields[5]
            try:
                start = int(fields[7])
                end = int(fields[8])
            except ValueError as error:
                raise ValueError(
                    f"Invalid MashMap interval at line {line_number}."
                ) from error
            if (
                contig not in allowed_contigs
                or start < 0
                or end <= start
            ):
                raise ValueError(
                    f"Unexpected MashMap interval at line {line_number}."
                )
            intervals.append((contig, start, end))
    if not intervals:
        raise ValueError("MashMap output contains no intervals.")
    return sorted(intervals, key=lambda row: (row[0], row[1], row[2]))


def write_bed_intervals(
    path: Path,
    intervals: Iterable[tuple[str, int, int]],
) -> None:
    with path.open("w", encoding="ascii", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerows(intervals)


def read_bed_intervals(
    path: Path,
    *,
    allowed_contigs: set[str],
) -> list[tuple[str, int, int]]:
    intervals = []
    with path.open(
        "r", encoding="ascii", errors="strict", newline=""
    ) as handle:
        reader = csv.reader(handle, delimiter="\t")
        for line_number, row in enumerate(reader, start=1):
            if len(row) < 3:
                raise ValueError(
                    f"Malformed BED output at line {line_number}."
                )
            try:
                interval = (row[0], int(row[1]), int(row[2]))
            except ValueError as error:
                raise ValueError(
                    f"Invalid BED output at line {line_number}."
                ) from error
            if (
                interval[0] not in allowed_contigs
                or interval[1] < 0
                or interval[2] <= interval[1]
            ):
                raise ValueError(
                    f"Unexpected BED output at line {line_number}."
                )
            intervals.append(interval)
    if not intervals:
        raise ValueError("Merged partial-decoy BED is empty.")
    return intervals


def read_fasta_sequences(path: Path) -> Iterable[tuple[str, str]]:
    name = ""
    chunks: list[str] = []
    with path.open("rt", encoding="ascii", errors="strict") as handle:
        for line_number, line in enumerate(handle, start=1):
            value = line.strip()
            if value.startswith(">"):
                if name:
                    yield name, "".join(chunks)
                name = value[1:].split(None, 1)[0].strip()
                chunks = []
                if not name:
                    raise ValueError(
                        f"Blank FASTA record at line {line_number}."
                    )
            elif value:
                if not name:
                    raise ValueError(
                        f"FASTA sequence precedes header at line {line_number}."
                    )
                chunks.append(value)
    if name:
        yield name, "".join(chunks)


def write_fasta_sequences(
    path: Path,
    records: Iterable[tuple[str, str]],
) -> None:
    with path.open("w", encoding="ascii", newline="") as handle:
        for name, sequence in records:
            if not name or not sequence:
                raise ValueError("Cannot write a blank FASTA record.")
            handle.write(f">{name}\n")
            for offset in range(0, len(sequence), 80):
                handle.write(sequence[offset : offset + 80] + "\n")


def salmon_quant_options(
    *,
    threads: int,
    extra_options: Iterable[Any],
) -> list[str]:
    options = [
        "-l",
        "A",
        "--seqBias",
        "--gcBias",
        "--posBias",
        "-p",
        str(threads),
    ]
    forbidden = {
        "-1",
        "-2",
        "-i",
        "-o",
        "-g",
        "--mates1",
        "--mates2",
        "--index",
        "--output",
        "--geneMap",
    }
    extra = [str(value).strip() for value in extra_options]
    if any(not value for value in extra):
        raise ValueError("Salmon extra options cannot be blank.")
    if any(value in forbidden for value in extra):
        raise ValueError(
            "Salmon paths are controlled by the Nottingham adapter."
        )
    return [*options, *extra]


def quantify_nottingham_run(
    run: dict[str, Any],
    *,
    cache_root: Path,
    accession: str,
    salmon_binary: str,
    salmon_version: str,
    salmon_binary_sha256: str,
    index_dir: Path,
    tx2gene_path: Path,
    quant_options: list[str],
    quant_signature: str,
    min_mapped_fragments: int,
    min_mapping_rate: float,
) -> dict[str, Any]:
    run_accession = str(run["run_accession"])
    fastq_input_signature = hashlib.sha256(
        canonical_json(
            [
                {
                    "md5": file_spec["md5"],
                    "size": file_spec["size"],
                }
                for file_spec in run["fastq_files"]
            ]
        ).encode("utf-8")
    ).hexdigest()
    quant_root = cache_root / "quant" / "by-input"
    quant_dir = quant_root / f"{fastq_input_signature}-{quant_signature}"
    state_path = quant_dir / "run_state.json"
    existing = validated_quant_state(
        state_path,
        quant_signature=quant_signature,
        fastq_input_signature=fastq_input_signature,
    )
    if existing is not None:
        existing["quant_reused"] = True
        return existing

    fastq_dir = cache_root / "fastq" / run_accession
    fastq_paths = []
    quant_completed = False
    try:
        for file_spec in run["fastq_files"]:
            target = fastq_dir / file_spec["name"]
            materialize_md5_download(file_spec, target)
            fastq_paths.append(target)
        staging = quant_root / (
            f"{fastq_input_signature}-{quant_signature}.tmp-{os.getpid()}"
        )
        if staging.exists():
            shutil.rmtree(staging)
        staging.mkdir(parents=True)
        salmon_output = staging / "salmon"
        command = [
            salmon_binary,
            "quant",
            "-i",
            str(index_dir),
            *quant_options,
            "-1",
            str(fastq_paths[0]),
            "-2",
            str(fastq_paths[1]),
            "-g",
            str(tx2gene_path),
            "-o",
            str(salmon_output),
        ]
        run_logged_command(
            command,
            stdout_path=staging / "salmon-quant.stdout.log",
            stderr_path=staging / "salmon-quant.stderr.log",
        )
        quant_genes = salmon_output / "quant.genes.sf"
        meta_info = salmon_output / "aux_info" / "meta_info.json"
        if not quant_genes.is_file() or not meta_info.is_file():
            raise RuntimeError(
                f"Salmon output is incomplete for {run_accession}."
            )
        meta = json.loads(meta_info.read_text(encoding="utf-8"))
        processed = int(meta.get("num_processed") or 0)
        mapped = int(meta.get("num_mapped") or 0)
        mapping_rate = float(meta.get("percent_mapped") or 0.0)
        qc_passed, qc_reason = nottingham_quant_passes_qc(
            processed_fragments=processed,
            mapped_fragments=mapped,
            mapping_rate=mapping_rate,
            min_mapped_fragments=min_mapped_fragments,
            min_mapping_rate=min_mapping_rate,
        )
        state = {
            "schema_version": "tcga-trace-nottingham-run-state-v1",
            "run_accession": run_accession,
            "source_accession": accession,
            "quant_signature": quant_signature,
            "fastq_input_signature": fastq_input_signature,
            "salmon_version": salmon_version,
            "salmon_binary_sha256": salmon_binary_sha256,
            "fastq_files": run["fastq_files"],
            "processed_fragments": processed,
            "mapped_fragments": mapped,
            "mapping_rate": mapping_rate,
            "qc_passed": qc_passed,
            "qc_reason": qc_reason,
            "quant_genes_relative_path": "salmon/quant.genes.sf",
            "quant_genes_sha256": sha256_file(quant_genes),
        }
        (staging / "run_state.json").write_text(
            canonical_json(state) + "\n",
            encoding="utf-8",
        )
        quant_root.mkdir(parents=True, exist_ok=True)
        if quant_dir.exists():
            shutil.rmtree(quant_dir)
        staging.rename(quant_dir)
        quant_completed = True
        state["quant_genes_path"] = (
            quant_dir / "salmon" / "quant.genes.sf"
        )
        state["quant_reused"] = False
        return state
    finally:
        if quant_completed and fastq_dir.exists():
            shutil.rmtree(fastq_dir)


def validated_quant_state(
    state_path: Path,
    *,
    quant_signature: str,
    fastq_input_signature: str,
) -> dict[str, Any] | None:
    if not state_path.is_file():
        return None
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
        quant_path = state_path.parent / str(
            state["quant_genes_relative_path"]
        )
        if (
            state.get("quant_signature") != quant_signature
            or state.get("fastq_input_signature")
            != fastq_input_signature
            or not quant_path.is_file()
            or sha256_file(quant_path) != state["quant_genes_sha256"]
        ):
            return None
        state["quant_genes_path"] = quant_path
        return state
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None


def nottingham_quant_passes_qc(
    *,
    processed_fragments: int,
    mapped_fragments: int,
    mapping_rate: float,
    min_mapped_fragments: int = DEFAULT_MIN_MAPPED_FRAGMENTS,
    min_mapping_rate: float = DEFAULT_MIN_MAPPING_RATE,
) -> tuple[bool, str]:
    reasons = []
    if processed_fragments <= 0:
        reasons.append("no processed fragments")
    if mapped_fragments < min_mapped_fragments:
        reasons.append(
            f"mapped fragments {mapped_fragments} < "
            f"{min_mapped_fragments}"
        )
    if not math.isfinite(mapping_rate) or mapping_rate < min_mapping_rate:
        reasons.append(
            f"mapping rate {mapping_rate:.6g}% < "
            f"{min_mapping_rate:.6g}%"
        )
    return not reasons, "; ".join(reasons)


def materialize_nottingham_clinical_tables(
    selected: list[dict[str, Any]],
    *,
    source_dir: Path,
    accession: str,
    layout: str,
) -> tuple[Path, Path]:
    patient_rows = []
    sample_rows = []
    for item in selected:
        participant = item["participant"]
        run = item["run"]
        clinical = participant["clinical"]
        source_id = str(participant["participant_source_id"])
        patient_id = f"{accession}-P{sanitize_identifier(source_id)}"
        sample_id = f"{patient_id}-RNA"
        patient_row = {
            "PATIENT_ID": patient_id,
            "BCSS_MONTHS": format(clinical["bcss_months"], ".12g"),
            "BCSS_EVENT": (
                "1:DEATH_FROM_BREAST_CANCER"
                if clinical["bcss_event"]
                else "0:CENSORED"
            ),
            "AGE_AT_INDEX": format(clinical["age"], ".12g"),
            "STAGE": clinical.get("stage") or "",
            "GRADE": clinical.get("grade") or "",
            "SEX": clinical.get("sex") or "",
            "SOURCE_PARTICIPANT_ID": source_id,
        }
        if layout == ICART1_2_LAYOUT:
            patient_row.update(
                {
                    "DMFS_MONTHS": format(
                        clinical["dmfs_months"], ".12g"
                    ),
                    "DMFS_EVENT": (
                        "1:DISTANT_METASTASIS"
                        if clinical["dmfs_event"]
                        else "0:CENSORED"
                    ),
                }
            )
        patient_row["NOTTINGHAM_CLINICAL_METADATA_JSON"] = (
            canonical_json(clinical)
        )
        patient_rows.append(patient_row)
        sample_metadata = {
            "source_name": run["source_name"],
            "rna_identifier": run["rna_identifier"],
            "ena_run": run["run_accession"],
            "ena_sample": run["ena_sample"],
            "biosd_sample": run["biosd_sample"],
            "selection_rank": item["rank"],
        }
        sample_rows.append(
            {
                "SAMPLE_ID": sample_id,
                "PATIENT_ID": patient_id,
                "SAMPLE_TYPE": "Primary triple-negative breast cancer",
                "SOURCE_NAME": run["source_name"],
                "ENA_RUN": run["run_accession"],
                "ENA_SAMPLE": run["ena_sample"],
                "SELECTION_RANK": item["rank"],
                "NOTTINGHAM_SAMPLE_METADATA_JSON": canonical_json(
                    sample_metadata
                ),
            }
        )
        item["patient_id"] = patient_id
        item["sample_id"] = sample_id

    patient_fields = [
        "PATIENT_ID",
        "BCSS_MONTHS",
        "BCSS_EVENT",
    ]
    if layout == ICART1_2_LAYOUT:
        patient_fields.extend(["DMFS_MONTHS", "DMFS_EVENT"])
    patient_fields.extend(
        [
            "AGE_AT_INDEX",
            "STAGE",
            "GRADE",
            "SEX",
            "SOURCE_PARTICIPANT_ID",
            "NOTTINGHAM_CLINICAL_METADATA_JSON",
        ]
    )
    patient_path = source_dir / "data_clinical_patient.txt"
    sample_path = source_dir / "data_clinical_sample.txt"
    write_tsv(patient_path, patient_rows, patient_fields)
    write_tsv(
        sample_path,
        sample_rows,
        [
            "SAMPLE_ID",
            "PATIENT_ID",
            "SAMPLE_TYPE",
            "SOURCE_NAME",
            "ENA_RUN",
            "ENA_SAMPLE",
            "SELECTION_RANK",
            "NOTTINGHAM_SAMPLE_METADATA_JSON",
        ],
    )
    return patient_path, sample_path


def materialize_nottingham_expression(
    selected: list[dict[str, Any]],
    output_path: Path,
) -> dict[str, Any]:
    if not selected:
        raise ValueError("No Nottingham quantifications were selected.")
    matrices = []
    gene_ids: set[str] | None = None
    for item in selected:
        values = read_salmon_gene_tpm(
            Path(item["quant"]["quant_genes_path"])
        )
        current_ids = set(values)
        if gene_ids is None:
            gene_ids = current_ids
        elif current_ids != gene_ids:
            raise ValueError(
                "Salmon gene inventories differ between selected runs."
            )
        matrices.append(values)
    assert gene_ids is not None
    ordered_genes = sorted(gene_ids)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(
            ["GENE_ID", *(item["sample_id"] for item in selected)]
        )
        for gene_id in ordered_genes:
            writer.writerow(
                [
                    gene_id,
                    *(
                        format(values[gene_id], ".10g")
                        for values in matrices
                    ),
                ]
            )
    return {
        "source_expression_rows": len(ordered_genes),
        "source_expression_samples": len(selected),
        "source_expression_unit": "Salmon gene-level TPM",
    }


def read_salmon_gene_tpm(path: Path) -> dict[str, float]:
    with path.open(
        newline="", encoding="utf-8", errors="strict"
    ) as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        required = {"Name", "TPM"}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError(f"Invalid Salmon gene table: {path}.")
        values = {}
        for row in reader:
            gene_id = str(row["Name"]).strip()
            try:
                value = float(row["TPM"])
            except (TypeError, ValueError) as error:
                raise ValueError(
                    f"Invalid TPM for {gene_id!r} in {path}."
                ) from error
            if (
                not gene_id
                or gene_id in values
                or not math.isfinite(value)
                or value < 0
            ):
                raise ValueError(
                    f"Invalid or duplicate Salmon gene {gene_id!r}."
                )
            values[gene_id] = value
    if len(values) < 10_000:
        raise ValueError(
            f"Salmon gene table has only {len(values)} rows."
        )
    return values


def summarize_selected_endpoints(
    selected: list[dict[str, Any]],
    layout: str,
) -> dict[str, dict[str, int]]:
    result = {
        "BCSS": {
            "patients": len(selected),
            "events": sum(
                int(item["participant"]["clinical"]["bcss_event"])
                for item in selected
            ),
        }
    }
    if layout == ICART1_2_LAYOUT:
        usable_dmfs = [
            item
            for item in selected
            if item["participant"]["clinical"]["dmfs_months"] > 0
        ]
        result["DMFS"] = {
            "patients": len(usable_dmfs),
            "events": sum(
                int(item["participant"]["clinical"]["dmfs_event"])
                for item in usable_dmfs
            ),
            "excluded_nonpositive_time": len(selected) - len(usable_dmfs),
        }
    return result


def materialize_sha256_download(
    file_spec: dict[str, Any],
    target: Path,
) -> None:
    if (
        target.is_file()
        and target.stat().st_size == file_spec["size"]
        and sha256_file(target) == file_spec["sha256"]
    ):
        return
    if target.exists():
        target.unlink()
    canonicalizer = str(file_spec.get("canonicalizer") or "").strip()
    if canonicalizer:
        if canonicalizer != "ena_read_run_tsv":
            raise ValueError(
                f"Unsupported source canonicalizer: {canonicalizer!r}."
            )
        raw_path = target.with_name(target.name + ".download")
        download_with_resume(
            file_spec["url"],
            raw_path,
            total_size=file_spec["size"],
        )
        canonicalize_ena_report(raw_path, target)
        raw_path.unlink()
    else:
        download_with_resume(
            file_spec["url"],
            target,
            total_size=file_spec["size"],
        )
    if (
        target.stat().st_size != file_spec["size"]
        or sha256_file(target) != file_spec["sha256"]
    ):
        target.unlink(missing_ok=True)
        raise ValueError(
            f"SHA-256 validation failed for {file_spec['name']}."
        )


def materialize_md5_download(
    file_spec: dict[str, Any],
    target: Path,
) -> None:
    if (
        target.is_file()
        and target.stat().st_size == int(file_spec["size"])
        and file_digest(target, "md5") == file_spec["md5"]
    ):
        return
    if target.exists():
        target.unlink()
    download_with_resume(
        file_spec["url"],
        target,
        total_size=int(file_spec["size"]),
    )
    if file_digest(target, "md5") != file_spec["md5"]:
        target.unlink(missing_ok=True)
        raise ValueError(f"MD5 validation failed for {target.name}.")


def download_with_resume(
    url: str,
    target: Path,
    *,
    total_size: int,
) -> None:
    if (
        urllib.parse.urlparse(url).scheme not in {"http", "https"}
        or total_size <= 0
    ):
        raise ValueError(
            "Resumable downloads require an HTTP(S) URL and size."
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(target.name + ".part")
    if target.is_file() and target.stat().st_size == total_size:
        return
    if target.exists():
        target.unlink()
    if partial.exists() and partial.stat().st_size > total_size:
        partial.unlink()

    attempts = 0
    while (partial.stat().st_size if partial.exists() else 0) < total_size:
        start = partial.stat().st_size if partial.exists() else 0
        headers = {
            "User-Agent": USER_AGENT,
            "Accept-Encoding": "identity",
        }
        if start:
            headers["Range"] = f"bytes={start}-"
        request = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=300) as response:
                status = int(getattr(response, "status", 200))
                if start and status != 206:
                    partial.unlink(missing_ok=True)
                    attempts += 1
                    if attempts >= DOWNLOAD_ATTEMPTS:
                        raise OSError(
                            "Server did not honor resumable download."
                        )
                    continue
                mode = "ab" if start else "wb"
                with partial.open(mode) as handle:
                    while chunk := response.read(4 * 1024 * 1024):
                        handle.write(chunk)
            attempts = 0
        except (
            urllib.error.URLError,
            TimeoutError,
            OSError,
        ):
            attempts += 1
            if attempts >= DOWNLOAD_ATTEMPTS:
                raise
            time.sleep(min(2**attempts, 30))
    observed_size = partial.stat().st_size
    if observed_size != total_size:
        raise OSError(
            f"Downloaded size changed: {observed_size} != {total_size}."
        )
    partial.replace(target)


def validate_pinned_file_spec(
    value: Any,
    *,
    label: str,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} file specification must be an object.")
    url = str(value.get("url") or "").strip()
    name = str(value.get("name") or "").strip()
    sha256 = str(value.get("sha256") or "").strip().lower()
    size = int(value.get("size") or 0)
    if (
        urllib.parse.urlparse(url).scheme not in {"http", "https"}
        or not name
        or name != Path(name).name
        or size <= 0
        or not re.fullmatch(r"[0-9a-f]{64}", sha256)
    ):
        raise ValueError(f"{label} is not fully pinned.")
    return {
        **value,
        "url": url,
        "name": name,
        "size": size,
        "sha256": sha256,
    }


def validate_partial_decoy_spec(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(
            "Nottingham source requires a partial_decoy object."
        )
    method = str(value.get("method") or "").strip()
    mashmap_version = str(value.get("mashmap_version") or "").strip()
    bedtools_version = str(value.get("bedtools_version") or "").strip()
    mashmap_sha256 = str(
        value.get("mashmap_executable_sha256") or ""
    ).strip().lower()
    bedtools_sha256 = str(
        value.get("bedtools_executable_sha256") or ""
    ).strip().lower()
    identity_percent = int(value.get("identity_percent") or 0)
    segment_length = int(value.get("segment_length") or 0)
    if (
        method != PARTIAL_DECOY_METHOD
        or not mashmap_version
        or not bedtools_version
        or not re.fullmatch(r"[0-9a-f]{64}", mashmap_sha256)
        or not re.fullmatch(r"[0-9a-f]{64}", bedtools_sha256)
        or not 1 <= identity_percent <= 100
        or segment_length < 1
    ):
        raise ValueError(
            "Nottingham partial-decoy processing is not fully pinned."
        )
    return {
        **value,
        "method": method,
        "mashmap_version": mashmap_version,
        "mashmap_executable_sha256": mashmap_sha256,
        "bedtools_version": bedtools_version,
        "bedtools_executable_sha256": bedtools_sha256,
        "identity_percent": identity_percent,
        "segment_length": segment_length,
    }


def validate_prebuilt_salmon_reference_spec(
    value: Any,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(
            "prebuilt_salmon_reference must be an object."
        )
    method = str(value.get("method") or "").strip()
    archive_root = str(value.get("archive_root") or "").strip().strip(
        "/"
    )
    gentrome_name = str(value.get("gentrome_name") or "").strip()
    built_salmon_version = str(
        value.get("built_salmon_version") or ""
    ).strip()
    refgenie_genome_digest = str(
        value.get("refgenie_genome_digest") or ""
    ).strip().lower()
    refgenie_asset_digest = str(
        value.get("refgenie_asset_digest") or ""
    ).strip().lower()
    integer_fields = {
        name: int(value.get(name) or 0)
        for name in (
            "index_version",
            "expected_tx2gene_rows",
            "expected_decoys",
            "expected_first_decoy_index",
            "expected_kmers",
        )
    }
    if (
        method != PREBUILT_PARTIAL_INDEX_METHOD
        or not archive_root
        or archive_root != Path(archive_root).name
        or not gentrome_name
        or gentrome_name != Path(gentrome_name).name
        or not re.fullmatch(
            r"[0-9a-f]{40,64}", refgenie_genome_digest
        )
        or not re.fullmatch(
            r"[0-9a-f]{32,64}", refgenie_asset_digest
        )
        or not re.fullmatch(r"\d+\.\d+\.\d+", built_salmon_version)
        or any(number <= 0 for number in integer_fields.values())
    ):
        raise ValueError(
            "Nottingham prebuilt Salmon reference is not fully pinned."
        )
    archive = validate_pinned_file_spec(
        value.get("archive"), label="prebuilt Salmon reference archive"
    )
    return {
        **value,
        **integer_fields,
        "method": method,
        "archive": archive,
        "archive_root": archive_root,
        "gentrome_name": gentrome_name,
        "built_salmon_version": built_salmon_version,
        "refgenie_genome_digest": refgenie_genome_digest,
        "refgenie_asset_digest": refgenie_asset_digest,
    }


def canonicalize_ena_report(source: Path, target: Path) -> None:
    with source.open(
        newline="", encoding="utf-8-sig", errors="strict"
    ) as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)
    if not fieldnames or "run_accession" not in fieldnames:
        raise ValueError("ENA report cannot be canonicalized.")
    run_accessions = [
        str(row.get("run_accession") or "").strip() for row in rows
    ]
    if (
        not run_accessions
        or any(not value for value in run_accessions)
        or len(run_accessions) != len(set(run_accessions))
    ):
        raise ValueError(
            "ENA report contains missing or duplicate run accessions."
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = target.with_name(target.name + ".canonicalizing")
    with staging.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fieldnames,
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(
            sorted(rows, key=lambda row: str(row["run_accession"]))
        )
    staging.replace(target)


def file_manifest_entry(
    file_spec: dict[str, Any],
    path: Path,
) -> dict[str, Any]:
    return {
        "url": file_spec["url"],
        "name": file_spec["name"],
        "size": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def resolve_salmon_version(salmon_binary: str) -> str:
    result = subprocess.run(
        [salmon_binary, "--version"],
        check=True,
        capture_output=True,
        text=True,
    )
    output = (result.stdout or result.stderr).strip()
    match = re.search(r"\b(\d+\.\d+\.\d+)\b", output)
    if not match:
        raise ValueError(f"Could not parse Salmon version from {output!r}.")
    return match.group(1)


def resolve_required_binary(
    *,
    env_name: str,
    configured: Any,
    default_name: str,
    label: str,
) -> str:
    requested = str(
        os.environ.get(env_name) or configured or default_name
    ).strip()
    resolved = Path(
        shutil.which(requested) or requested
    ).expanduser().resolve()
    if not resolved.is_file() or not os.access(resolved, os.X_OK):
        raise RuntimeError(
            f"{label} executable not found; set {env_name}."
        )
    return str(resolved)


def resolve_bedtools_version(bedtools_binary: str) -> str:
    result = subprocess.run(
        [bedtools_binary, "--version"],
        check=True,
        capture_output=True,
        text=True,
    )
    output = (result.stdout or result.stderr).strip()
    match = re.search(r"\b(?:v)?(\d+\.\d+\.\d+)\b", output)
    if not match:
        raise ValueError(
            f"Could not parse bedtools version from {output!r}."
        )
    return match.group(1)


def run_logged_command(
    command: list[str],
    *,
    stdout_path: Path,
    stderr_path: Path,
) -> None:
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    with (
        stdout_path.open("w", encoding="utf-8") as stdout_handle,
        stderr_path.open("w", encoding="utf-8") as stderr_handle,
    ):
        subprocess.run(
            command,
            check=True,
            stdout=stdout_handle,
            stderr=stderr_handle,
        )


def required_text(mapping: dict[str, Any], key: str) -> str:
    value = str(mapping.get(key) or "").strip()
    if not value:
        raise ValueError(f"Nottingham source requires {key}.")
    return value


def split_semicolon_field(value: Any) -> list[str]:
    return [
        item.strip()
        for item in str(value or "").split(";")
        if item.strip()
    ]


def parse_positive_int(value: Any, label: str) -> int:
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError) as error:
        raise ValueError(f"Invalid {label}: {value!r}.") from error
    if parsed <= 0:
        raise ValueError(f"{label} must be positive.")
    return parsed


def parse_positive_float(value: Any, label: str) -> float:
    try:
        parsed = float(str(value).strip())
    except (TypeError, ValueError) as error:
        raise ValueError(f"Invalid {label}: {value!r}.") from error
    if not math.isfinite(parsed) or parsed <= 0:
        raise ValueError(f"{label} must be finite and positive.")
    return parsed


def parse_nonnegative_float(value: Any, label: str) -> float:
    try:
        parsed = float(str(value).strip())
    except (TypeError, ValueError) as error:
        raise ValueError(f"Invalid {label}: {value!r}.") from error
    if not math.isfinite(parsed) or parsed < 0:
        raise ValueError(f"{label} must be finite and non-negative.")
    return parsed


def file_digest(path: Path, algorithm: str) -> str:
    digest = hashlib.new(algorithm)
    with path.open("rb") as handle:
        while chunk := handle.read(4 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def natural_identifier_key(value: str) -> tuple[Any, ...]:
    return tuple(
        int(part) if part.isdigit() else part.casefold()
        for part in re.split(r"(\d+)", str(value))
    )


def sanitize_identifier(value: str) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9]+", "-", value).strip("-")
    if not sanitized:
        raise ValueError(f"Cannot sanitize participant ID {value!r}.")
    return sanitized
