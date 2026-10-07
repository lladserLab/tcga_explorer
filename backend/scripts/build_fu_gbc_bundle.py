#!/usr/bin/env python3
"""Build the FU-GBC release using TRACE's external RNA-seq bundle contract."""

from __future__ import annotations

import argparse
from array import array
import csv
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import sys
from typing import Any, Iterable


BUNDLE_SCHEMA_VERSION = "tcga-trace-external-rnaseq-bundle-v1"
DATASET_ID = "fu-gbc-cancer-cell-2026"
MONTH_TO_DAY = 365.25 / 12.0
PUBLICATION_DOI = "10.1016/j.ccell.2025.12.014"
PUBLICATION_URL = (
    "https://www.sciencedirect.com/science/article/pii/S1535610825005483"
)
SOURCE_INPUTS = (
    "README.md",
    "SHA256SUMS",
    "clinical_all.tsv",
    "clinical_field_dictionary.tsv",
    "clinical_tumor_rna.tsv",
    "expression_nat_log2_tpm.tsv.gz",
    "expression_tumor_log2_tpm.tsv.gz",
    "qc.json",
    "sample_manifest.tsv",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8", errors="strict") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def write_tsv(path: Path, rows: Iterable[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fields,
            delimiter="\t",
            lineterminator="\n",
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def normalized_stage(value: str) -> str:
    return value.strip().upper()


def json_cell(payload: dict[str, Any]) -> str:
    return json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def build_clinical_tables(
    source_dir: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, str]]]:
    clinical_by_patient = {
        row["patient_id"]: row
        for row in read_tsv(source_dir / "clinical_all.tsv")
    }
    source_samples = read_tsv(source_dir / "sample_manifest.tsv")
    sample_ids_by_patient: dict[str, dict[str, str]] = {}
    for row in source_samples:
        sample_ids_by_patient.setdefault(row["patient_id"], {})[
            row["tissue_type"]
        ] = row["expression_sample_id"]

    rna_patient_ids = sorted(sample_ids_by_patient)
    missing = sorted(set(rna_patient_ids) - set(clinical_by_patient))
    if missing:
        raise ValueError(
            f"Clinical metadata are missing for {len(missing)} RNA patients."
        )

    patients: list[dict[str, Any]] = []
    endpoints: list[dict[str, Any]] = []
    for patient_id in rna_patient_ids:
        raw = clinical_by_patient[patient_id]
        stage = normalized_stage(raw.get("tnm_stage_normalized", ""))
        patients.append(
            {
                "patient_id": patient_id,
                "stage": stage,
                "grade": "",
                "gender": raw.get("sex", ""),
                "race": "",
                "age_at_index": raw.get("age_years", ""),
                "raw_metadata_json": json_cell(raw),
            }
        )
        months = float(raw["survival_months"])
        endpoints.append(
            {
                "patient_id": patient_id,
                "time_days": f"{months * MONTH_TO_DAY:.10g}",
                "event": raw["death_event"],
                "raw_time": f"{months:.10g}",
                "raw_event": raw.get("status_raw", ""),
                "raw_metadata_json": json_cell(
                    {
                        "conversion_days_per_month": MONTH_TO_DAY,
                        "source_status_normalized": raw.get(
                            "status_normalized", ""
                        ),
                        "source_time_origin_confirmed": False,
                    }
                ),
            }
        )

    samples: list[dict[str, Any]] = []
    for raw in source_samples:
        patient_id = raw["patient_id"]
        tissue = raw["tissue_type"]
        partner_tissue = "nat" if tissue == "tumor" else "tumor"
        partner_id = sample_ids_by_patient[patient_id].get(partner_tissue, "")
        sample_type = (
            "Primary Tumor" if tissue == "tumor" else "Solid Tissue Normal"
        )
        samples.append(
            {
                "sample_id": raw["expression_sample_id"],
                "patient_id": patient_id,
                "sample_type": sample_type,
                "sample_role": (
                    "primary_tumor"
                    if tissue == "tumor"
                    else "adjacent_non_tumor"
                ),
                "selection_rank": 0 if tissue == "tumor" else 10,
                "raw_metadata_json": json_cell(
                    {
                        **raw,
                        "paired_sample_id": partner_id or None,
                        "tissue_interpretation": (
                            "resected primary tumor"
                            if tissue == "tumor"
                            else "patient-matched non-cancerous adjacent tissue; not an independent healthy control"
                        ),
                    }
                ),
            }
        )

    pairs = [
        {
            "patient_id": patient_id,
            "tumor_sample_id": sample_ids["tumor"],
            "adjacent_sample_id": sample_ids["nat"],
        }
        for patient_id, sample_ids in sorted(sample_ids_by_patient.items())
        if sample_ids.get("tumor") and sample_ids.get("nat")
    ]
    return patients, samples, endpoints, pairs


def float32le(values: Iterable[float]) -> array:
    result = array("f", (float(value) for value in values))
    if sys.byteorder != "little":
        result.byteswap()
    return result


def build_expression_layers(
    source_dir: Path,
    derived_dir: Path,
    pairs: list[dict[str, str]],
) -> tuple[list[dict[str, Any]], int]:
    tumor_path = source_dir / "expression_tumor_log2_tpm.tsv.gz"
    adjacent_path = source_dir / "expression_nat_log2_tpm.tsv.gz"
    matrix_path = derived_dir / "fu_gbc_log2_tpm.float32le.bin"
    delta_path = derived_dir / "fu_gbc_paired_delta.float32le.bin"
    genes_path = derived_dir / "genes.tsv"
    genes: list[dict[str, Any]] = []

    with gzip.open(tumor_path, "rt", newline="", encoding="utf-8") as tumor_handle, gzip.open(
        adjacent_path, "rt", newline="", encoding="utf-8"
    ) as adjacent_handle, matrix_path.open("wb") as matrix_handle, delta_path.open(
        "wb"
    ) as delta_handle:
        tumor_reader = csv.reader(tumor_handle, delimiter="\t")
        adjacent_reader = csv.reader(adjacent_handle, delimiter="\t")
        tumor_samples = next(tumor_reader)[1:]
        adjacent_samples = next(adjacent_reader)[1:]
        all_samples = tumor_samples + adjacent_samples
        if len(all_samples) != len(set(all_samples)):
            raise ValueError("FU-GBC expression sample IDs are not unique.")
        tumor_index = {sample_id: index for index, sample_id in enumerate(tumor_samples)}
        adjacent_index = {
            sample_id: index for index, sample_id in enumerate(adjacent_samples)
        }
        ordered_pairs = sorted(
            pairs,
            key=lambda row: tumor_index[row["tumor_sample_id"]],
        )
        paired_tumor_samples = [row["tumor_sample_id"] for row in ordered_pairs]

        sentinel = object()
        row_number = 0
        while True:
            tumor_row = next(tumor_reader, sentinel)
            adjacent_row = next(adjacent_reader, sentinel)
            if tumor_row is sentinel and adjacent_row is sentinel:
                break
            if tumor_row is sentinel or adjacent_row is sentinel:
                raise ValueError(
                    "Tumor and adjacent matrices contain different gene counts."
                )
            tumor_gene = tumor_row[0].strip().upper()
            adjacent_gene = adjacent_row[0].strip().upper()
            if not tumor_gene or tumor_gene != adjacent_gene:
                raise ValueError(
                    f"Gene mismatch at expression row {row_number}: "
                    f"{tumor_gene!r} != {adjacent_gene!r}."
                )
            tumor_values = [float(value) for value in tumor_row[1:]]
            adjacent_values = [float(value) for value in adjacent_row[1:]]
            if len(tumor_values) != len(tumor_samples):
                raise ValueError(f"Tumor row {tumor_gene} has the wrong width.")
            if len(adjacent_values) != len(adjacent_samples):
                raise ValueError(f"Adjacent row {tumor_gene} has the wrong width.")
            float32le(tumor_values + adjacent_values).tofile(matrix_handle)
            float32le(
                tumor_values[tumor_index[pair["tumor_sample_id"]]]
                - adjacent_values[
                    adjacent_index[pair["adjacent_sample_id"]]
                ]
                for pair in ordered_pairs
            ).tofile(delta_handle)
            genes.append(
                {
                    "gene_symbol": tumor_gene,
                    "original_gene_id": tumor_gene,
                    "row_number": row_number,
                    "mapping_source": "source-provided protein-coding gene symbol",
                }
            )
            row_number += 1

    symbols = [row["gene_symbol"] for row in genes]
    if len(symbols) != len(set(symbols)):
        raise ValueError("FU-GBC contains duplicate canonical gene symbols.")
    write_tsv(
        genes_path,
        genes,
        ["gene_symbol", "original_gene_id", "row_number", "mapping_source"],
    )
    write_json(
        derived_dir / "fu_gbc_log2_tpm.metadata.json",
        {
            "dtype": "float32_le",
            "layout": "row_major_gene_by_sample",
            "gene_count": len(genes),
            "sample_count": len(all_samples),
            "sample_ids": all_samples,
        },
    )
    write_json(
        derived_dir / "fu_gbc_paired_delta.metadata.json",
        {
            "dtype": "float32_le",
            "layout": "row_major_gene_by_sample",
            "gene_count": len(genes),
            "sample_count": len(paired_tumor_samples),
            "sample_ids": paired_tumor_samples,
            "sample_interpretation": (
                "Tumor sample identifiers anchor patient-matched tumor-minus-adjacent contrasts."
            ),
        },
    )
    shared_metadata = {
        "mapping_source": "source-provided protein-coding gene_symbol",
        "feature_id_type": "HUGO-like source gene symbol",
        "duplicate_feature_policy": "reject",
    }
    layers = [
        {
            "layer_id": "fu_gbc_log2_tpm",
            "label": "FU-GBC source log2(TPM + 1)",
            "source_unit": "log2(TPM + 1)",
            "analysis_unit": "log2(TPM + 1)",
            "transform": "identity",
            "matrix_file": "derived/fu_gbc_log2_tpm.float32le.bin",
            "metadata_file": "derived/fu_gbc_log2_tpm.metadata.json",
            "genes_file": "derived/genes.tsv",
            "is_default": True,
            "downloadable": False,
            "metadata": {
                **shared_metadata,
                "scale_note": (
                    "Values are the source-declared log2(TPM + 1) matrix. "
                    "Primary tumor has selection_rank 0; adjacent non-tumor can "
                    "be selected explicitly with the sample-type filter."
                ),
            },
        },
        {
            "layer_id": "fu_gbc_paired_delta",
            "label": "Paired Δ: tumor − adjacent log2(TPM + 1)",
            "source_unit": "log2(TPM + 1)",
            "analysis_unit": "tumor-minus-adjacent log2(TPM + 1)",
            "transform": "paired_difference",
            "matrix_file": "derived/fu_gbc_paired_delta.float32le.bin",
            "metadata_file": "derived/fu_gbc_paired_delta.metadata.json",
            "genes_file": "derived/genes.tsv",
            "is_default": False,
            "downloadable": False,
            "metadata": {
                **shared_metadata,
                "scale_note": (
                    "For each of 66 matched patients, TRACE subtracts adjacent "
                    "log2(TPM + 1) from tumor log2(TPM + 1). Tumor identifiers "
                    "anchor the patient-level contrast."
                ),
                "paired_patient_count": len(pairs),
                "pair_manifest": "derived/pairs.tsv",
            },
        },
    ]
    return layers, len(genes)


def copy_source_files(
    source_dir: Path,
    source_workbook: Path,
    output_source_dir: Path,
) -> dict[str, str]:
    output_source_dir.mkdir(parents=True, exist_ok=True)
    copied: dict[str, str] = {}
    for name in SOURCE_INPUTS:
        source = source_dir / name
        if not source.is_file():
            raise FileNotFoundError(source)
        destination_name = (
            "analysis_ready_SHA256SUMS" if name == "SHA256SUMS" else name
        )
        destination = output_source_dir / destination_name
        shutil.copy2(source, destination)
        copied[name] = f"source/{destination_name}"
    if not source_workbook.is_file():
        raise FileNotFoundError(source_workbook)
    workbook_destination = output_source_dir / "FU-GBC_mmc2.xlsx"
    shutil.copy2(source_workbook, workbook_destination)
    copied["source_workbook"] = "source/FU-GBC_mmc2.xlsx"
    return copied


def build_bundle(
    source_dir: Path,
    source_workbook: Path,
    output_dir: Path,
) -> dict[str, Any]:
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(
            f"Output directory is not empty; choose a fresh path: {output_dir}"
        )
    source_output = output_dir / "source"
    derived = output_dir / "derived"
    derived.mkdir(parents=True, exist_ok=True)
    source_files = copy_source_files(
        source_dir, source_workbook, source_output
    )
    patients, samples, endpoints, pairs = build_clinical_tables(source_dir)
    write_tsv(
        derived / "patients.tsv",
        patients,
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
        derived / "samples.tsv",
        samples,
        [
            "sample_id",
            "patient_id",
            "sample_type",
            "sample_role",
            "selection_rank",
            "raw_metadata_json",
        ],
    )
    write_tsv(
        derived / "endpoint_os.tsv",
        endpoints,
        [
            "patient_id",
            "time_days",
            "event",
            "raw_time",
            "raw_event",
            "raw_metadata_json",
        ],
    )
    write_tsv(
        derived / "pairs.tsv",
        pairs,
        ["patient_id", "tumor_sample_id", "adjacent_sample_id"],
    )
    expression_layers, gene_count = build_expression_layers(
        source_dir, derived, pairs
    )

    license_evidence = {
        "schema_version": "trace-source-license-evidence-v1",
        "publication_doi": PUBLICATION_DOI,
        "publication_url": PUBLICATION_URL,
        "copyright_notice": "Copyright © 2025 Elsevier Inc. All rights reserved.",
        "evidence_url": "https://pubmed.ncbi.nlm.nih.gov/41512870/",
        "license_interpretation": (
            "No open redistribution license was identified. TRACE retains this "
            "release for local analysis, disables matrix downloads, and does not "
            "represent the source supplement or derived matrices as redistributable."
        ),
        "redistribution_allowed": False,
    }
    write_json(source_output / "SOURCE_LICENSE_EVIDENCE.json", license_evidence)
    source_files["license"] = "source/SOURCE_LICENSE_EVIDENCE.json"

    input_hashes = {
        relative: sha256_file(output_dir / relative)
        for relative in sorted(source_files.values())
        if relative != source_files["license"]
    }
    source_snapshot = canonical_sha256(input_hashes)
    recipe_hash = sha256_file(Path(__file__).resolve())
    release_id = f"{DATASET_ID}-{source_snapshot[:12]}-{recipe_hash[:12]}"
    retrieved_at = datetime.fromtimestamp(
        source_workbook.stat().st_mtime, tz=timezone.utc
    ).isoformat()

    endpoint_events = sum(int(row["event"]) for row in endpoints)
    manifest: dict[str, Any] = {
        "schema_version": BUNDLE_SCHEMA_VERSION,
        "dataset": {
            "id": DATASET_ID,
            "cancer_code": "GBC",
            "name": "FU-GBC gallbladder cancer cohort (2026)",
            "description": (
                "Independent FU-GBC bulk RNA-seq cohort with source-reported "
                "survival, primary tumors, adjacent non-cancerous tissue and "
                "patient-matched tumor-minus-adjacent expression contrasts."
            ),
            "cohort_context": (
                "135 RNA-profiled patients: 135 primary tumors and 66 matched "
                "adjacent non-cancerous tissues. Tumor is the default survival "
                "view; NAT is an adjacent comparator, not an independent healthy "
                "control. The source does not explicitly define survival time zero."
            ),
            "source_provider": "elsevier_supplement",
            "source_accession": f"DOI:{PUBLICATION_DOI}",
            "source_url": PUBLICATION_URL,
            "publication_citation": "Fu et al. Cancer Cell 2026;44:405-423.e13",
            "publication_id": f"DOI:{PUBLICATION_DOI}",
            "organism": "Homo sapiens",
            "assay": "bulk_rna_seq",
            "independence_status": "verified_external",
            "license_id": "Elsevier-All-Rights-Reserved",
            "license_url": "https://pubmed.ncbi.nlm.nih.gov/41512870/",
            "redistribution_allowed": False,
            "metadata": {
                "cohort_accessions": [
                    "HRA011141",
                    "PRJCA037941",
                    "PRJCA038692",
                    "PDC000606",
                    "PDC000607",
                ],
                "curation_note": (
                    "The accessions are molecular layers of one FU-GBC cohort, "
                    "not independent validation cohorts."
                ),
                "endpoint_note": (
                    "The source supplies Survival (month) and Status but does not "
                    "explicitly state the time origin; TRACE therefore labels it "
                    "source-reported survival while retaining OS as the API code."
                ),
                "sample_selection_rule": (
                    "Primary tumor selection_rank 0, adjacent tissue rank 10; "
                    "selection occurs after filters and expression completeness."
                ),
                "paired_patient_count": len(pairs),
                "redistribution_note": license_evidence[
                    "license_interpretation"
                ],
            },
        },
        "release": {
            "id": release_id,
            "version": (
                f"supplement-{source_snapshot[:12]}-recipe-{recipe_hash[:12]}"
            ),
            "source_snapshot": source_snapshot,
            "source_snapshot_date": retrieved_at[:10],
            "retrieved_at": retrieved_at,
        },
        "endpoints": [
            {
                "endpoint_id": "OS",
                "standard_code": "OS",
                "label": "Source-reported survival",
                "time_origin": "Not explicitly defined in the source supplement",
                "event_definition": (
                    "Source Status = dead is event 1; alive is censored (event 0)"
                ),
                "source_time_column": "Survival (month)",
                "source_event_column": "Status",
                "source_time_unit": "months",
                "values_file": "derived/endpoint_os.tsv",
                "metadata": {
                    "internal_time_unit": "days",
                    "conversion_days_per_month": MONTH_TO_DAY,
                    "time_origin_confirmed": False,
                },
            }
        ],
        "expression_layers": expression_layers,
        "files": {
            "patients": "derived/patients.tsv",
            "samples": "derived/samples.tsv",
        },
        "source_files": {
            "license": source_files["license"],
            "source_workbook": source_files["source_workbook"],
            "source_manifest": source_files["sample_manifest.tsv"],
            "clinical": source_files["clinical_all.tsv"],
            "expression_tumor": source_files[
                "expression_tumor_log2_tpm.tsv.gz"
            ],
            "expression_adjacent": source_files[
                "expression_nat_log2_tpm.tsv.gz"
            ],
            "analysis_qc": source_files["qc.json"],
        },
        "build": {
            "adapter": "fu_gbc_supplement_v1",
            "adapter_sha256": recipe_hash,
            "build_recipe_sha256": recipe_hash,
            "source_snapshot_sha256": source_snapshot,
            "source_clinical_patients": 195,
            "selected_rna_patients": len(patients),
            "expression_samples": len(samples),
            "tumor_samples": sum(
                row["sample_role"] == "primary_tumor" for row in samples
            ),
            "adjacent_samples": sum(
                row["sample_role"] == "adjacent_non_tumor"
                for row in samples
            ),
            "paired_patients": len(pairs),
            "mapped_complete_genes": gene_count,
            "endpoints": {
                "OS": {
                    "patients": len(endpoints),
                    "events": endpoint_events,
                    "time_origin_confirmed": False,
                }
            },
            "source_expression_unit": "log2(TPM + 1)",
            "source_sample_selection_outcome_independent": True,
        },
    }
    checksum_paths = sorted(
        path
        for path in output_dir.rglob("*")
        if path.is_file() and path.name != "manifest.json"
    )
    manifest["checksums"] = {
        str(path.relative_to(output_dir)): sha256_file(path)
        for path in checksum_paths
    }
    write_json(output_dir / "manifest.json", manifest)
    return {
        "bundle": str(output_dir),
        "dataset_id": DATASET_ID,
        "release_id": release_id,
        "patients": len(patients),
        "samples": len(samples),
        "paired_patients": len(pairs),
        "genes": gene_count,
        "events": endpoint_events,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--source-workbook", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = build_bundle(
        args.source_dir.resolve(),
        args.source_workbook.resolve(),
        args.output.resolve(),
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
