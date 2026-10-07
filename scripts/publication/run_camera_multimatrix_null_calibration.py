#!/usr/bin/env python3
"""Freeze and run paired CAMERA null checks in three real expression matrices.

This publication-only runner has two deliberately separate extensions:

* paired per-set-estimated and fixed-rho CAMERA null experiments in three
  matrices selected before outcomes were inspected; and
* completion of the historical gene-set-permutation comparator to the same
  500 outer labels at 1,000 internal permutations.

Neither extension changes TRACE's production GSEA implementation. Every long
phase checkpoints incrementally and can be resumed without regenerating labels.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import csv
from datetime import datetime, timezone
import json
import math
import multiprocessing
import os
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import time
from typing import Any, Iterable, Sequence


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from scripts.publication import run_molecular_null_calibration as molecular  # noqa: E402
from scripts.publication.run_molecular_null_calibration import (  # noqa: E402
    GSEA_MAX_SIZE,
    GSEA_MIN_SIZE,
    GSEA_SEED,
    build_permutations,
    load_expression_matrix,
    parse_positions,
    read_csv,
    sha256_file,
    wilson_interval,
    workspace_path,
    write_csv,
    write_json,
)


SCHEMA_VERSION = "trace-camera-multimatrix-null-calibration-v1"
LEGACY_SCHEMA_VERSION = "trace-legacy-gene-set-null-extension-v1"
EXPECTED_LIMMA_VERSION = "3.62.2"
REPLICATES = 500
LEGACY_INNER_PERMUTATIONS = 1000
Q_THRESHOLDS = (0.05, 0.10, 0.25)
DEFAULT_COLLECTION = ROOT / "backend" / "gene_sets" / "go-bp-20260619.gmt"
DEFAULT_COLLECTION_MANIFEST = ROOT / "backend" / "gene_sets" / "collections.json"
DEFAULT_R_ENGINE = ROOT / "scripts" / "publication" / "camera_multimatrix_null_calibration.R"
DEFAULT_OUTPUT = (
    ROOT
    / "docs"
    / "publication"
    / "benchmark"
    / "major_revision_2026-08-27"
    / "camera_multimatrix_null_calibration"
)


MATRIX_SPECS: tuple[dict[str, Any], ...] = (
    {
        "key": "luad_cas_n51",
        "label": "LUAD-CAS",
        "release": (
            ROOT
            / "external_repository"
            / "studies"
            / "cbioportal-luad-cas-2020"
            / "releases"
            / "cbioportal-luad-cas-2020-86690e1ed975-a398e2f4773e"
        ),
        "layer": "log2_fpkm",
        "expected_samples": 51,
        "master_seed": 20260826,
        "selection_stratum": "small",
    },
    {
        "key": "luad_cptac_n208",
        "label": "LUAD-CPTAC-GDC",
        "release": (
            ROOT
            / "external_repository"
            / "studies"
            / "cbioportal-luad-cptac-gdc-2025"
            / "releases"
            / "cbioportal-luad-cptac-gdc-2025-baefda4952c1-e566c0a2f8d1"
        ),
        "layer": "log2_tpm",
        "expected_samples": 208,
        "master_seed": 2026082702,
        "selection_stratum": "medium",
    },
    {
        "key": "blca_uromol_n462",
        "label": "BLCA-UROMOL",
        "release": (
            ROOT
            / "external_repository"
            / "studies"
            / "biostudies-blca-uromol-2016"
            / "releases"
            / "biostudies-blca-uromol-2016-84f4f3418df6-c104a5f68211"
        ),
        "layer": "biostudies_log2_fpkm",
        "expected_samples": 462,
        "master_seed": 2026082703,
        "selection_stratum": "large",
    },
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _command_output(command: Sequence[str]) -> str | None:
    try:
        completed = subprocess.run(
            list(command), check=False, capture_output=True, text=True
        )
    except OSError:
        return None
    if completed.returncode:
        return None
    return (completed.stdout or completed.stderr).strip() or None


def environment_metadata() -> dict[str, Any]:
    return {
        "python": sys.version.replace("\n", " "),
        "platform": platform.platform(),
        "r": _command_output(["Rscript", "-e", "cat(R.version.string)"]),
        "limma": _command_output(
            ["Rscript", "-e", 'cat(as.character(packageVersion("limma")))']
        ),
        "git_commit": _command_output(["git", "rev-parse", "HEAD"]),
        "container_image": os.environ.get("TRACE_CALIBRATION_CONTAINER_IMAGE"),
    }


def matrix_spec(key: str) -> dict[str, Any]:
    for spec in MATRIX_SPECS:
        if spec["key"] == key:
            return spec
    raise KeyError(f"Unknown frozen matrix key: {key}")


def build_fixed_null_tasks(replicates: int = REPLICATES) -> list[dict[str, Any]]:
    if replicates < 1:
        raise ValueError("replicates must be positive")
    return [
        {"task_id": f"N{replicate:04d}", "replicate": replicate}
        for replicate in range(1, replicates + 1)
    ]


def validate_labels(
    rows: Sequence[dict[str, Any]], *, sample_count: int, replicates: int
) -> None:
    if len(rows) != replicates:
        raise ValueError(f"Expected {replicates} labels; observed {len(rows)}.")
    expected_b = sample_count // 2
    for expected_replicate, row in enumerate(rows, start=1):
        if int(row["replicate"]) != expected_replicate:
            raise ValueError("Frozen labels are not the ordered replicate sequence.")
        positions = parse_positions(str(row["group_b_zero_based_positions"]))
        if int(row["group_b_n"]) != expected_b:
            raise ValueError("Frozen labels changed the balanced group-B size.")
        if int(row["group_a_n"]) + expected_b != sample_count:
            raise ValueError("Frozen label group counts are inconsistent.")
        if len(positions) != expected_b or len(set(positions)) != expected_b:
            raise ValueError("Frozen labels contain missing or duplicate positions.")
        if any(position < 0 or position >= sample_count for position in positions):
            raise ValueError("Frozen labels contain an out-of-range position.")


def _source_records(
    spec: dict[str, Any], matrix: Any, source_paths: dict[str, Path]
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for role, path in sorted(source_paths.items()):
        if path.is_file():
            records.append(
                {
                    "matrix_key": spec["key"],
                    "role": role,
                    "path": workspace_path(path),
                    "sha256": sha256_file(path),
                    "bytes": path.stat().st_size,
                }
            )
    if not any(row["role"] == "matrix" for row in records):
        records.append(
            {
                "matrix_key": spec["key"],
                "role": "matrix",
                "path": workspace_path(matrix.path),
                "sha256": matrix.source_sha256,
                "bytes": matrix.path.stat().st_size,
            }
        )
    return records


def freeze_protocol(output: Path) -> None:
    if output.exists() and any(output.iterdir()):
        raise RuntimeError(f"Refusing to overwrite frozen protocol: {output}")
    output.mkdir(parents=True, exist_ok=True)
    labels_dir = output / "frozen_labels"
    labels_dir.mkdir()

    matrix_records: list[dict[str, Any]] = []
    frozen_inputs: list[dict[str, Any]] = []
    for spec in MATRIX_SPECS:
        matrix, metadata, source_paths = load_expression_matrix(
            spec["release"], spec["layer"]
        )
        if len(matrix.sample_ids) != spec["expected_samples"]:
            raise RuntimeError(
                f"{spec['key']} expected {spec['expected_samples']} samples; "
                f"observed {len(matrix.sample_ids)}."
            )
        labels = build_permutations(
            sample_count=len(matrix.sample_ids),
            group_b_size=len(matrix.sample_ids) // 2,
            replicates=REPLICATES,
            seed=spec["master_seed"],
        )
        validate_labels(
            labels, sample_count=len(matrix.sample_ids), replicates=REPLICATES
        )
        label_path = labels_dir / f"{spec['key']}.csv"
        write_csv(label_path, labels)
        source_records = _source_records(spec, matrix, source_paths)
        frozen_inputs.extend(source_records)
        matrix_records.append(
            {
                "key": spec["key"],
                "label": spec["label"],
                "selection_stratum": spec["selection_stratum"],
                "selection_status": "fixed before null outcomes",
                "release_dir": workspace_path(spec["release"]),
                "release_id": spec["release"].name,
                "layer": spec["layer"],
                "analysis_unit": metadata.get("analysis_unit"),
                "samples": len(matrix.sample_ids),
                "genes": len(matrix.genes),
                "matrix_sha256": matrix.source_sha256,
                "master_seed": spec["master_seed"],
                "group_a_n": len(matrix.sample_ids) - len(matrix.sample_ids) // 2,
                "group_b_n": len(matrix.sample_ids) // 2,
                "labels_path": workspace_path(label_path),
                "labels_sha256": sha256_file(label_path),
            }
        )

    prior_labels = (
        ROOT
        / "docs"
        / "publication"
        / "benchmark"
        / "major_revision_2026-08-26"
        / "expression_gsea_null_calibration"
        / "full"
        / "outer_label_permutations.csv"
    )
    if not prior_labels.is_file():
        raise FileNotFoundError(f"Prior frozen LUAD labels are absent: {prior_labels}")
    cas_labels = labels_dir / "luad_cas_n51.csv"
    if sha256_file(cas_labels) != sha256_file(prior_labels):
        raise RuntimeError("LUAD-CAS labels do not reproduce the prior frozen 500.")

    common_files = {
        "gene_set_collection": DEFAULT_COLLECTION,
        "gene_set_manifest": DEFAULT_COLLECTION_MANIFEST,
        "camera_engine": DEFAULT_R_ENGINE,
        "runner": Path(__file__).resolve(),
        "legacy_gsea_core": ROOT / "backend" / "app" / "gsea.py",
        "prior_luad_labels": prior_labels,
    }
    for role, path in common_files.items():
        if not path.is_file():
            raise FileNotFoundError(f"Frozen input is unavailable: {path}")
        frozen_inputs.append(
            {
                "matrix_key": None,
                "role": role,
                "path": workspace_path(path),
                "sha256": sha256_file(path),
                "bytes": path.stat().st_size,
            }
        )
    for path in sorted(labels_dir.glob("*.csv")):
        frozen_inputs.append(
            {
                "matrix_key": path.stem,
                "role": "frozen_outer_labels",
                "path": workspace_path(path),
                "sha256": sha256_file(path),
                "bytes": path.stat().st_size,
            }
        )

    design = {
        "schema_version": SCHEMA_VERSION,
        "status": "frozen before pilot or formal outcomes",
        "generated_at": utc_now(),
        "scientific_question": (
            "How do paired strict per-set estimated-correlation CAMERA and "
            "fixed-rho 0.01 behave under complete sample-label nulls in three "
            "predefined real bulk-RNA matrices?"
        ),
        "selection_rationale": (
            "The matrices were fixed before null results to span small, medium "
            "and large patient-level cohorts, two tumour contexts and distinct "
            "normalized bulk-RNA scales. They are empirical contexts, not an "
            "experiment that isolates sample size."
        ),
        "matrices": matrix_records,
        "outer_label_null": {
            "replicates_per_matrix": REPLICATES,
            "operation": (
                "Assign floor(n/2) complete sample columns to group B by a "
                "frozen simple random sample; retain complete transcriptomes, "
                "marginal distributions and gene-gene correlation."
            ),
            "contrast": "group B minus group A",
            "labels_regenerated_after_results": False,
        },
        "camera": {
            "function": "limma::camera",
            "version": EXPECTED_LIMMA_VERSION,
            "design": "intercept plus B-minus-A",
            "use_ranks": False,
            "allow_negative_correlation": False,
            "trend_variance": True,
            "directional": True,
            "paired_modes": ["estimated_per_set", "fixed_0_01"],
            "multiplicity": "BH across every eligible GO-BP pathway",
            "collection": workspace_path(DEFAULT_COLLECTION),
            "collection_sha256": sha256_file(DEFAULT_COLLECTION),
            "minimum_observed_genes": GSEA_MIN_SIZE,
            "maximum_observed_genes": GSEA_MAX_SIZE,
            "thresholds": list(Q_THRESHOLDS),
        },
        "primary_null_outcome": (
            "probability that a complete null family contains at least one "
            "BH q<=0.05 rejection"
        ),
        "secondary_null_outcomes": [
            "same probability at q<=0.10 and q<=0.25",
            "number of rejected pathways per replicate",
            "minimum FDR",
            "distribution of estimated within-set residual correlations",
            "paired estimated-only, fixed-only, both and neither decisions",
        ],
        "interval_interpretation": (
            "Two-sided 95% Wilson intervals quantify Monte Carlo uncertainty "
            "over the 500 frozen label assignments; they are not population "
            "sampling confidence intervals."
        ),
        "legacy_comparator_extension": {
            "status": "frozen before extension outcomes",
            "matrix_key": "luad_cas_n51",
            "outer_labels": REPLICATES,
            "inner_gene_set_permutations": LEGACY_INNER_PERMUTATIONS,
            "fixed_inner_seed": GSEA_SEED,
            "ranking": "Welch t statistic, group B minus group A",
            "multiplicity": "BH across all eligible GO-BP pathways",
            "role": (
                "historical correlation-ignorant comparator; not production "
                "pathway inference"
            ),
        },
        "scope_boundary": (
            "Three matrices broaden the empirical calibration but do not prove "
            "universal error control or isolate sample size from cohort and "
            "assay structure."
        ),
        "frozen_inputs": frozen_inputs,
        "environment_at_freeze": environment_metadata(),
    }
    design_path = output / "preregistered_design.json"
    write_json(design_path, design)
    markdown = (
        "# Multi-matrix CAMERA null calibration\n\n"
        "Status: frozen before any pilot or formal result was generated.\n\n"
        "Three real patient-level bulk-RNA matrices were fixed: LUAD-CAS "
        "(51 samples), LUAD-CPTAC-GDC (208) and BLCA-UROMOL (462). For each "
        "matrix, 500 balanced sample-label assignments were generated once and "
        "stored explicitly.\n\n"
        "Every assignment will run the same GO Biological Process family "
        "(15--500 observed genes) twice: CAMERA with correlation estimated "
        "separately for each set and CAMERA with rho fixed at 0.01. The two "
        "results are paired by matrix and label assignment. BH covers the full "
        "eligible family.\n\n"
        "The primary outcome is the probability of at least one BH q<=0.05 "
        "rejection under the complete label null. Wilson intervals describe "
        "Monte Carlo uncertainty only. Matrix, labels, collection, code and "
        "engine identities are SHA-256 frozen in preregistered_design.json.\n\n"
        "The historical gene-set-permutation comparator is separately frozen "
        "to the same 500 LUAD-CAS labels and 1,000 internal permutations. It "
        "remains a comparator and does not alter production inference.\n"
    )
    (output / "PREREGISTERED_DESIGN.md").write_text(markdown, encoding="utf-8")
    frozen_files = [design_path, output / "PREREGISTERED_DESIGN.md", *sorted(labels_dir.glob("*.csv"))]
    (output / "FROZEN_SHA256SUMS").write_text(
        "".join(
            f"{sha256_file(path)}  {path.relative_to(output)}\n"
            for path in frozen_files
        ),
        encoding="utf-8",
    )
    print(f"Frozen protocol: {output}")


def load_frozen_design(output: Path) -> dict[str, Any]:
    path = output / "preregistered_design.json"
    if not path.is_file():
        raise RuntimeError("Run the freeze command before any result-generating phase.")
    design = json.loads(path.read_text(encoding="utf-8"))
    if design.get("schema_version") != SCHEMA_VERSION:
        raise RuntimeError("Frozen protocol schema is incompatible.")
    return design


def verify_frozen_inputs(output: Path) -> dict[str, Any]:
    design = load_frozen_design(output)
    for item in design.get("frozen_inputs") or []:
        path = Path(item["path"])
        if not path.is_absolute():
            path = ROOT / path
        if not path.is_file() or sha256_file(path) != item["sha256"]:
            raise RuntimeError(f"Frozen input checksum mismatch: {path}")
    for record in design["matrices"]:
        label_path = Path(record["labels_path"])
        if not label_path.is_absolute():
            label_path = ROOT / label_path
        if sha256_file(label_path) != record["labels_sha256"]:
            raise RuntimeError(f"Frozen label checksum mismatch: {label_path}")
    return design


def _split_tasks(
    tasks: Sequence[dict[str, Any]], workers: int
) -> list[list[dict[str, Any]]]:
    chunks: list[list[dict[str, Any]]] = [[] for _ in range(workers)]
    for index, task in enumerate(tasks):
        chunks[index % workers].append(task)
    return [chunk for chunk in chunks if chunk]


def _run_r(payload_path: Path) -> None:
    completed = subprocess.run(
        ["Rscript", str(DEFAULT_R_ENGINE), str(payload_path)],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode:
        detail = (completed.stderr or completed.stdout or "unknown error").strip()
        raise RuntimeError(
            f"CAMERA worker failed for {payload_path.name}:\n{detail[-5000:]}"
        )


def _expected_result_keys(
    tasks: Sequence[dict[str, Any]],
) -> set[tuple[str, str]]:
    return {
        (str(task["task_id"]), mode)
        for task in tasks
        for mode in ("estimated_per_set", "fixed_0_01")
    }


def merge_checkpoints(
    phase_dir: Path, tasks: Sequence[dict[str, Any]]
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for path in sorted(phase_dir.glob("checkpoint_worker_*.csv")):
        rows.extend(read_csv(path))
    expected = _expected_result_keys(tasks)
    observed = {(row["task_id"], row["correlation_mode"]) for row in rows}
    if len(rows) != len(expected) or observed != expected:
        raise RuntimeError(
            f"Incomplete checkpoints in {phase_dir}: expected {len(expected)} "
            f"paired rows; observed {len(rows)}."
        )
    rows.sort(key=lambda row: (int(row["replicate"]), row["correlation_mode"]))
    return rows


def _mean(values: Iterable[float]) -> float:
    collected = [float(value) for value in values]
    return statistics.fmean(collected) if collected else math.nan


def _median(values: Iterable[float]) -> float:
    collected = [float(value) for value in values]
    return statistics.median(collected) if collected else math.nan


def summarize_matrix_results(
    rows: Sequence[dict[str, str]], *, matrix_record: dict[str, Any]
) -> dict[str, Any]:
    by_mode: dict[str, list[dict[str, str]]] = {
        "estimated_per_set": [],
        "fixed_0_01": [],
    }
    paired: dict[str, dict[str, dict[str, str]]] = {}
    for row in rows:
        by_mode[row["correlation_mode"]].append(row)
        paired.setdefault(row["task_id"], {})[row["correlation_mode"]] = row
    if len(paired) != REPLICATES or any(len(item) != 2 for item in paired.values()):
        raise ValueError("Results are not paired across all frozen labels.")

    methods: dict[str, Any] = {}
    for mode, mode_rows in by_mode.items():
        thresholds: dict[str, Any] = {}
        for threshold in Q_THRESHOLDS:
            field = f"rejections_q_le_{threshold:.2f}".replace(".", "_")
            successes = sum(int(float(row[field])) > 0 for row in mode_rows)
            low, high = wilson_interval(successes, len(mode_rows))
            thresholds[f"q_le_{threshold:.2f}"] = {
                "replicates": len(mode_rows),
                "replicates_with_any_rejection": successes,
                "probability_any_rejection": successes / len(mode_rows),
                "monte_carlo_wilson_95_interval": [low, high],
                "mean_rejections": _mean(float(row[field]) for row in mode_rows),
                "median_rejections": _median(float(row[field]) for row in mode_rows),
                "maximum_rejections": max(int(float(row[field])) for row in mode_rows),
            }
        method: dict[str, Any] = {
            "replicates": len(mode_rows),
            "thresholds": thresholds,
            "minimum_fdr": {
                "mean": _mean(float(row["min_fdr"]) for row in mode_rows),
                "median": _median(float(row["min_fdr"]) for row in mode_rows),
                "minimum": min(float(row["min_fdr"]) for row in mode_rows),
            },
            "mean_camera_seconds": _mean(
                float(row["camera_seconds"]) for row in mode_rows
            ),
            "pathway_counts": sorted(
                {int(float(row["pathways_tested"])) for row in mode_rows}
            ),
        }
        if mode == "estimated_per_set":
            method["estimated_correlation_across_replicates"] = {
                field: {
                    "mean": _mean(float(row[field]) for row in mode_rows),
                    "median": _median(float(row[field]) for row in mode_rows),
                }
                for field in (
                    "camera_correlation_mean",
                    "camera_correlation_median",
                    "camera_correlation_p05",
                    "camera_correlation_p95",
                    "camera_correlation_minimum",
                    "camera_correlation_maximum",
                    "camera_correlation_mean_absolute",
                    "camera_correlation_proportion_above_0_01",
                )
            }
        methods[mode] = method

    paired_decisions: dict[str, Any] = {}
    for threshold in Q_THRESHOLDS:
        field = f"rejections_q_le_{threshold:.2f}".replace(".", "_")
        counts = {"both": 0, "estimated_only": 0, "fixed_only": 0, "neither": 0}
        for values in paired.values():
            estimated = int(float(values["estimated_per_set"][field])) > 0
            fixed = int(float(values["fixed_0_01"][field])) > 0
            key = (
                "both"
                if estimated and fixed
                else "estimated_only"
                if estimated
                else "fixed_only"
                if fixed
                else "neither"
            )
            counts[key] += 1
        paired_decisions[f"q_le_{threshold:.2f}"] = counts

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": utc_now(),
        "matrix": matrix_record,
        "complete_null_interpretation": (
            "Every rejected hypothesis is false; probability of any rejection "
            "therefore equals the realized false-discovery rate for the family."
        ),
        "interval_interpretation": (
            "Wilson intervals quantify Monte Carlo uncertainty across frozen "
            "label assignments, not population sampling uncertainty."
        ),
        "methods": methods,
        "paired_any_rejection_decisions": paired_decisions,
        "environment": environment_metadata(),
    }


def _matrix_record(design: dict[str, Any], key: str) -> dict[str, Any]:
    records = [row for row in design["matrices"] if row["key"] == key]
    if len(records) != 1:
        raise RuntimeError(f"Frozen matrix record is missing or duplicated: {key}")
    return records[0]


def _write_phase_manifest(
    phase_dir: Path,
    *,
    matrix_record: dict[str, Any],
    output_root: Path,
) -> None:
    excluded = {"manifest.json", "SHA256SUMS"}
    outputs = [
        path
        for path in sorted(phase_dir.iterdir())
        if path.is_file() and path.name not in excluded
    ]
    inputs = [
        output_root / "preregistered_design.json",
        ROOT / matrix_record["labels_path"],
        DEFAULT_COLLECTION,
        DEFAULT_R_ENGINE,
        Path(__file__).resolve(),
    ]
    manifest = {
        "schema_version": "trace-camera-multimatrix-phase-manifest-v1",
        "generated_at": utc_now(),
        "matrix_key": matrix_record["key"],
        "inputs": [
            {
                "path": workspace_path(path),
                "sha256": sha256_file(path),
                "bytes": path.stat().st_size,
            }
            for path in inputs
        ],
        "outputs": [
            {
                "file": path.name,
                "sha256": sha256_file(path),
                "bytes": path.stat().st_size,
            }
            for path in outputs
        ],
    }
    write_json(phase_dir / "manifest.json", manifest)
    checksum_files = [*outputs, phase_dir / "manifest.json"]
    (phase_dir / "SHA256SUMS").write_text(
        "".join(f"{sha256_file(path)}  {path.name}\n" for path in checksum_files),
        encoding="utf-8",
    )


def run_matrix(
    output: Path, *, key: str, workers: int, resume: bool
) -> None:
    design = verify_frozen_inputs(output)
    spec = matrix_spec(key)
    record = _matrix_record(design, key)
    matrix, _, _ = load_expression_matrix(spec["release"], spec["layer"])
    if matrix.source_sha256 != record["matrix_sha256"]:
        raise RuntimeError(f"Frozen matrix changed: {key}")
    labels_path = ROOT / record["labels_path"]
    labels = read_csv(labels_path)
    validate_labels(labels, sample_count=len(matrix.sample_ids), replicates=REPLICATES)
    tasks = build_fixed_null_tasks()

    phase_dir = output / "matrices" / key
    if phase_dir.exists() and any(phase_dir.iterdir()) and not resume:
        raise RuntimeError(f"Refusing to overwrite {phase_dir}; pass --resume.")
    phase_dir.mkdir(parents=True, exist_ok=True)
    tasks_path = phase_dir / "tasks.csv"
    if not tasks_path.exists():
        write_csv(tasks_path, tasks)
    elif read_csv(tasks_path) != [
        {name: str(value) for name, value in row.items()} for row in tasks
    ]:
        raise RuntimeError(f"Checkpoint tasks changed for {key}.")

    chunks = _split_tasks(tasks, workers)
    payload_paths: list[Path] = []
    for index, chunk in enumerate(chunks, start=1):
        worker_tasks = phase_dir / f"tasks_worker_{index:02d}.csv"
        checkpoint = phase_dir / f"checkpoint_worker_{index:02d}.csv"
        payload_path = phase_dir / f"input_worker_{index:02d}.json"
        if not worker_tasks.exists():
            write_csv(worker_tasks, chunk)
        elif read_csv(worker_tasks) != [
            {name: str(value) for name, value in row.items()} for row in chunk
        ]:
            raise RuntimeError(f"Worker task partition changed for {key}.")
        payload = {
            "schema_version": SCHEMA_VERSION,
            "matrix_path": str(matrix.path.resolve()),
            "gmt_path": str(DEFAULT_COLLECTION.resolve()),
            "genes": [gene.symbol for gene in matrix.genes],
            "sample_ids": list(matrix.sample_ids),
            "labels_path": str(labels_path.resolve()),
            "tasks_path": str(worker_tasks.resolve()),
            "output_path": str(checkpoint.resolve()),
            "min_gene_set_size": GSEA_MIN_SIZE,
            "max_gene_set_size": GSEA_MAX_SIZE,
            "expected_limma_version": EXPECTED_LIMMA_VERSION,
        }
        if payload_path.exists():
            observed = json.loads(payload_path.read_text(encoding="utf-8"))
            if observed != payload:
                raise RuntimeError(f"Worker payload changed for {key}.")
        else:
            write_json(payload_path, payload)
        payload_paths.append(payload_path)

    started = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(payload_paths)) as pool:
        futures = [pool.submit(_run_r, path) for path in payload_paths]
        for future in concurrent.futures.as_completed(futures):
            future.result()
    elapsed = time.perf_counter() - started

    rows = merge_checkpoints(phase_dir, tasks)
    raw_path = phase_dir / "raw_results.csv"
    write_csv(raw_path, rows)
    summary = summarize_matrix_results(rows, matrix_record=record)
    summary["runtime"] = {
        "wall_seconds_this_invocation": elapsed,
        "workers": workers,
        "resumed": resume,
    }
    write_json(phase_dir / "summary.json", summary)
    _write_phase_manifest(phase_dir, matrix_record=record, output_root=output)
    print(f"Completed paired CAMERA null calibration: {key}", flush=True)


def _legacy_completed_replicates(path: Path) -> set[int]:
    if not path.is_file() or path.stat().st_size == 0:
        return set()
    rows = read_csv(path)
    observed = [int(row["replicate"]) for row in rows]
    if len(observed) != len(set(observed)):
        raise RuntimeError("Legacy checkpoint contains duplicate replicates.")
    return set(observed)


def _append_legacy_checkpoint(
    path: Path, row: dict[str, Any], *, fieldnames: Sequence[str]
) -> None:
    append = path.is_file() and path.stat().st_size > 0
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fieldnames))
        if not append:
            writer.writeheader()
        writer.writerow(row)
        handle.flush()
        os.fsync(handle.fileno())


def _write_legacy_manifest(legacy_dir: Path, output: Path) -> None:
    excluded = {"manifest.json", "SHA256SUMS"}
    files = [
        path
        for path in sorted(legacy_dir.iterdir())
        if path.is_file() and path.name not in excluded
    ]
    manifest = {
        "schema_version": "trace-legacy-gene-set-null-manifest-v1",
        "generated_at": utc_now(),
        "inputs": [
            {
                "path": workspace_path(path),
                "sha256": sha256_file(path),
                "bytes": path.stat().st_size,
            }
            for path in (
                output / "preregistered_design.json",
                output / "frozen_labels" / "luad_cas_n51.csv",
                DEFAULT_COLLECTION,
                ROOT / "backend" / "app" / "gsea.py",
                Path(__file__).resolve(),
            )
        ],
        "outputs": [
            {
                "file": path.name,
                "sha256": sha256_file(path),
                "bytes": path.stat().st_size,
            }
            for path in files
        ],
    }
    write_json(legacy_dir / "manifest.json", manifest)
    checksum_files = [*files, legacy_dir / "manifest.json"]
    (legacy_dir / "SHA256SUMS").write_text(
        "".join(f"{sha256_file(path)}  {path.name}\n" for path in checksum_files),
        encoding="utf-8",
    )


def run_legacy_comparator(output: Path, *, workers: int, resume: bool) -> None:
    design = verify_frozen_inputs(output)
    record = _matrix_record(design, "luad_cas_n51")
    spec = matrix_spec("luad_cas_n51")
    matrix, _, _ = load_expression_matrix(spec["release"], spec["layer"])
    labels_path = output / "frozen_labels" / "luad_cas_n51.csv"
    labels = read_csv(labels_path)
    validate_labels(labels, sample_count=len(matrix.sample_ids), replicates=REPLICATES)

    legacy_dir = output / "legacy_gene_set_permutation_500x1000"
    if legacy_dir.exists() and any(legacy_dir.iterdir()) and not resume:
        raise RuntimeError(f"Refusing to overwrite {legacy_dir}; pass --resume.")
    legacy_dir.mkdir(parents=True, exist_ok=True)
    design_payload = {
        "schema_version": LEGACY_SCHEMA_VERSION,
        "status": "frozen in parent preregistered design before outcomes",
        "matrix_key": record["key"],
        "matrix_sha256": record["matrix_sha256"],
        "labels_sha256": sha256_file(labels_path),
        "outer_labels": REPLICATES,
        "inner_gene_set_permutations": LEGACY_INNER_PERMUTATIONS,
        "inner_seed": GSEA_SEED,
        "collection": workspace_path(DEFAULT_COLLECTION),
        "collection_sha256": sha256_file(DEFAULT_COLLECTION),
        "minimum_observed_genes": GSEA_MIN_SIZE,
        "maximum_observed_genes": GSEA_MAX_SIZE,
        "algorithm": (
            "Imported rank_expression_matrix and run_preranked_gsea; "
            "correlation-ignorant historical comparator, not production inference."
        ),
        "production_core_sha256": sha256_file(ROOT / "backend" / "app" / "gsea.py"),
    }
    legacy_design_path = legacy_dir / "design.json"
    if legacy_design_path.exists():
        if json.loads(legacy_design_path.read_text(encoding="utf-8")) != design_payload:
            raise RuntimeError("Legacy comparator design changed after checkpointing.")
    else:
        write_json(legacy_design_path, design_payload)

    checkpoint = legacy_dir / "checkpoint.csv"
    completed = _legacy_completed_replicates(checkpoint)
    pending = [
        (int(row["replicate"]), str(row["group_b_zero_based_positions"]))
        for row in labels
        if int(row["replicate"]) not in completed
    ]
    started = time.perf_counter()
    if pending:
        methods = multiprocessing.get_all_start_methods()
        context = multiprocessing.get_context("fork" if "fork" in methods else "spawn")
        with context.Pool(
            processes=workers,
            initializer=molecular._initialize_gsea_worker,
            initargs=(
                str(spec["release"]),
                spec["layer"],
                str(DEFAULT_COLLECTION),
                LEGACY_INNER_PERMUTATIONS,
                GSEA_SEED,
            ),
            maxtasksperchild=25,
        ) as pool:
            for index, result in enumerate(
                pool.imap_unordered(molecular._gsea_worker, pending), start=1
            ):
                row = {
                    "replicate": int(result["replicate"]),
                    "group_a_n": int(result["group_a_n"]),
                    "group_b_n": int(result["group_b_n"]),
                    **{
                        key: value
                        for key, value in result.items()
                        if key not in {"replicate", "group_a_n", "group_b_n"}
                    },
                }
                _append_legacy_checkpoint(
                    checkpoint, row, fieldnames=list(row)
                )
                if index % 10 == 0 or index == len(pending):
                    print(
                        f"Legacy comparator: {len(completed) + index}/{REPLICATES}",
                        flush=True,
                    )
    elapsed = time.perf_counter() - started
    rows = read_csv(checkpoint)
    if len(rows) != REPLICATES:
        raise RuntimeError(
            f"Legacy comparator is resumable but incomplete: {len(rows)}/{REPLICATES}."
        )
    rows.sort(key=lambda row: int(row["replicate"]))
    write_csv(legacy_dir / "raw_results.csv", rows)
    summary = {
        "schema_version": LEGACY_SCHEMA_VERSION,
        "generated_at": utc_now(),
        "replicates": REPLICATES,
        "inner_gene_set_permutations": LEGACY_INNER_PERMUTATIONS,
        "gsea": molecular.summarize_gsea(rows),
        "interval_interpretation": (
            "Wilson intervals quantify Monte Carlo uncertainty over frozen "
            "outer labels, not population sampling uncertainty."
        ),
        "runtime": {
            "completed_before_this_invocation": len(completed),
            "wall_seconds_this_invocation": elapsed,
            "workers": workers,
        },
        "environment": environment_metadata(),
    }
    write_json(legacy_dir / "summary.json", summary)
    _write_legacy_manifest(legacy_dir, output)
    print("Completed legacy comparator at 500 x 1,000.", flush=True)


def write_results_markdown(output: Path, aggregate: dict[str, Any]) -> None:
    lines = [
        "# Multi-matrix CAMERA null-calibration results",
        "",
        "Wilson intervals below describe Monte Carlo uncertainty across the 500 frozen label assignments.",
        "",
        "| Matrix | Mode | Any q<=0.05 | Mean rejected pathways | Median estimated rho |",
        "|---|---|---:|---:|---:|",
    ]
    for matrix in aggregate["matrices"]:
        for mode in ("estimated_per_set", "fixed_0_01"):
            method = matrix["methods"][mode]
            threshold = method["thresholds"]["q_le_0.05"]
            interval = threshold["monte_carlo_wilson_95_interval"]
            rho = "--"
            if mode == "estimated_per_set":
                rho_value = method["estimated_correlation_across_replicates"][
                    "camera_correlation_median"
                ]["median"]
                rho = f"{rho_value:.4f}"
            lines.append(
                f"| {matrix['matrix']['label']} | {mode} | "
                f"{100 * threshold['probability_any_rejection']:.1f}% "
                f"({100 * interval[0]:.1f}--{100 * interval[1]:.1f}) | "
                f"{threshold['mean_rejections']:.2f} | {rho} |"
            )
    legacy = aggregate.get("legacy_comparator")
    if legacy:
        threshold = legacy["gsea"]["thresholds"]["q_le_0.05"]
        interval = threshold["wilson_95_confidence_interval"]
        lines.extend(
            [
                "",
                "## Historical gene-set-permutation comparator",
                "",
                f"At 1,000 internal permutations, {threshold['replicates_with_any_rejection']}/{threshold['replicates']} outer labels contained at least one BH q<=0.05 rejection ({100 * threshold['probability_any_rejection']:.1f}%; Monte Carlo Wilson interval {100 * interval[0]:.1f}--{100 * interval[1]:.1f}%).",
            ]
        )
    lines.extend(
        [
            "",
            "These are three empirical contexts. Differences cannot be attributed to sample size alone because cohort and expression structure also vary.",
            "",
        ]
    )
    (output / "RESULTS.md").write_text("\n".join(lines), encoding="utf-8")


def finalize(output: Path) -> None:
    design = verify_frozen_inputs(output)
    matrix_summaries = []
    for record in design["matrices"]:
        phase_dir = output / "matrices" / record["key"]
        summary_path = phase_dir / "summary.json"
        manifest_path = phase_dir / "manifest.json"
        if not summary_path.is_file() or not manifest_path.is_file():
            raise RuntimeError(f"Matrix phase is incomplete: {record['key']}")
        matrix_summaries.append(json.loads(summary_path.read_text(encoding="utf-8")))
    legacy_path = output / "legacy_gene_set_permutation_500x1000" / "summary.json"
    aggregate: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": utc_now(),
        "matrices": matrix_summaries,
        "legacy_comparator": (
            json.loads(legacy_path.read_text(encoding="utf-8"))
            if legacy_path.is_file()
            else None
        ),
        "interpretive_boundary": design["scope_boundary"],
    }
    write_json(output / "aggregate_summary.json", aggregate)
    write_results_markdown(output, aggregate)

    excluded_names = {"artifact_manifest.json", "SHA256SUMS"}
    files = [
        path
        for path in sorted(output.rglob("*"))
        if path.is_file() and path.name not in excluded_names
    ]
    manifest = {
        "schema_version": "trace-camera-multimatrix-artifact-manifest-v1",
        "generated_at": utc_now(),
        "files": [
            {
                "path": str(path.relative_to(output)),
                "sha256": sha256_file(path),
                "bytes": path.stat().st_size,
            }
            for path in files
        ],
    }
    write_json(output / "artifact_manifest.json", manifest)
    checksum_files = [*files, output / "artifact_manifest.json"]
    (output / "SHA256SUMS").write_text(
        "".join(
            f"{sha256_file(path)}  {path.relative_to(output)}\n"
            for path in checksum_files
        ),
        encoding="utf-8",
    )
    verify_artifacts(output)
    print(f"Finalized multi-matrix artifact: {output}")


def verify_artifacts(output: Path) -> None:
    verify_frozen_inputs(output)
    manifest_path = output / "artifact_manifest.json"
    if not manifest_path.is_file():
        raise RuntimeError("Aggregate artifact manifest is missing.")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for item in manifest.get("files") or []:
        path = output / item["path"]
        if not path.is_file() or sha256_file(path) != item["sha256"]:
            raise RuntimeError(f"Artifact checksum mismatch: {path}")
    print(f"Verified multi-matrix artifact: {output}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("freeze")
    run_parser = subparsers.add_parser("run")
    run_parser.add_argument(
        "--matrix", choices=("all", *(spec["key"] for spec in MATRIX_SPECS)), default="all"
    )
    run_parser.add_argument("--workers", type=int, default=4)
    run_parser.add_argument("--resume", action="store_true")
    legacy_parser = subparsers.add_parser("legacy-run")
    legacy_parser.add_argument("--workers", type=int, default=4)
    legacy_parser.add_argument("--resume", action="store_true")
    subparsers.add_parser("finalize")
    subparsers.add_parser("verify")
    args = parser.parse_args()
    if getattr(args, "workers", 1) < 1:
        parser.error("--workers must be positive")
    return args


def main() -> int:
    args = parse_args()
    output = args.output_dir.resolve()
    if args.command == "freeze":
        freeze_protocol(output)
    elif args.command == "run":
        keys = (
            [spec["key"] for spec in MATRIX_SPECS]
            if args.matrix == "all"
            else [args.matrix]
        )
        for key in keys:
            run_matrix(output, key=key, workers=args.workers, resume=args.resume)
    elif args.command == "legacy-run":
        run_legacy_comparator(output, workers=args.workers, resume=args.resume)
    elif args.command == "finalize":
        finalize(output)
    elif args.command == "verify":
        verify_artifacts(output)
    else:  # pragma: no cover
        raise AssertionError(args.command)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
