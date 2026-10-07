#!/usr/bin/env python3
"""Freeze and run publication-only CAMERA operating-characteristic checks.

The experiment has two independent parts:

* a fixed-correlation (rho=0.01) null sensitivity using the exact 500 frozen
  LUAD label assignments from the production-CAMERA calibration; and
* a semi-synthetic power experiment.  It adds constant, standardized group-B
  shifts to genes in pathways chosen without labels or outcomes.  Constant
  within-group shifts leave the real-matrix residual covariance unchanged.

This script never edits or imports a different production CAMERA default.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import csv
from datetime import datetime, timezone
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import platform
import statistics
import subprocess
import sys
from typing import Any, Iterable, Sequence


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from scripts.publication.run_molecular_null_calibration import (  # noqa: E402
    DEFAULT_COLLECTION,
    DEFAULT_COLLECTION_MANIFEST,
    DEFAULT_LAYER,
    DEFAULT_OUTPUT as NULL_CALIBRATION_ROOT,
    DEFAULT_RELEASE,
    GSEA_MAX_SIZE,
    GSEA_MIN_SIZE,
    load_expression_matrix,
    parse_positions,
    read_csv,
    sha256_file,
    wilson_interval,
    workspace_path,
    write_csv,
    write_json,
)


SCHEMA_VERSION = "trace-camera-operating-characteristics-v1"
EXPECTED_LIMMA_VERSION = "3.62.2"
DEFAULT_OUTPUT = (
    ROOT
    / "docs"
    / "publication"
    / "benchmark"
    / "major_revision_2026-08-26"
    / "camera_operating_characteristics"
)
DEFAULT_LABELS = NULL_CALIBRATION_ROOT / "full" / "outer_label_permutations.csv"
DEFAULT_ESTIMATED_NULL = (
    NULL_CALIBRATION_ROOT / "camera_v2_full" / "camera_replicates.csv"
)
DEFAULT_R_ENGINE = ROOT / "scripts" / "publication" / "camera_operating_characteristics.R"

POWER_EFFECT_SDS = (0.20, 0.40)
POWER_ACTIVE_FRACTIONS = (0.25, 1.00)
POWER_FORMAL_REPLICATES = 200
POWER_PILOT_REPLICATES = 3
FIXED_NULL_FORMAL_REPLICATES = 500
FIXED_NULL_PILOT_REPLICATES = 5
ACTIVE_GENE_SEED = 2026082601
Q_THRESHOLDS = (0.05, 0.10, 0.25)


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


def stable_gene_order(pathway: str, genes: Iterable[str]) -> list[str]:
    """Order genes reproducibly without inspecting expression or labels."""

    return sorted(
        (str(gene) for gene in genes),
        key=lambda gene: (
            sha256(f"{ACTIVE_GENE_SEED}:{pathway}:{gene}".encode()).hexdigest(),
            gene,
        ),
    )


def active_gene_count(size: int, fraction: float) -> int:
    if size < 1 or not 0 < fraction <= 1:
        raise ValueError("Invalid active-gene design.")
    return max(1, min(size, int(math.floor(size * fraction + 0.5))))


def freeze_injections(selected: Sequence[dict[str, str]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for pathway_row in selected:
        pathway = pathway_row["pathway"]
        members = [gene for gene in pathway_row["member_genes"].split(";") if gene]
        ordered = stable_gene_order(pathway, members)
        for fraction in POWER_ACTIVE_FRACTIONS:
            count = active_gene_count(len(ordered), fraction)
            rows.append(
                {
                    "selection_id": pathway_row["selection_id"],
                    "pathway": pathway,
                    "active_fraction": f"{fraction:.2f}",
                    "active_gene_count": count,
                    "active_gene_selection": (
                        f"first {count} genes under SHA-256 order with seed "
                        f"{ACTIVE_GENE_SEED}"
                    ),
                    "active_genes": ";".join(ordered[:count]),
                }
            )
    return rows


def validate_labels(
    path: Path, *, sample_count: int, replicates: int
) -> list[dict[str, str]]:
    rows = read_csv(path)
    selected = rows[:replicates]
    if len(selected) != replicates:
        raise ValueError(f"Expected {replicates} frozen labels; observed {len(selected)}.")
    for expected, row in enumerate(selected, start=1):
        if int(row["replicate"]) != expected:
            raise ValueError("Frozen labels must be the ordered prefix starting at 1.")
        positions = parse_positions(row["group_b_zero_based_positions"])
        if int(row["group_a_n"]) + int(row["group_b_n"]) != sample_count:
            raise ValueError("A frozen label row has an incompatible sample count.")
        if len(positions) != int(row["group_b_n"]) or len(set(positions)) != len(
            positions
        ):
            raise ValueError("A frozen label row has invalid B positions.")
        if any(position < 0 or position >= sample_count for position in positions):
            raise ValueError("A frozen label position is out of range.")
    return selected


def build_power_tasks(
    selected_pathways: Sequence[dict[str, str]], *, replicates: int
) -> list[dict[str, Any]]:
    if replicates < 1:
        raise ValueError("replicates must be positive.")
    rows: list[dict[str, Any]] = []
    counter = 1
    for pathway in selected_pathways:
        for effect_sd in POWER_EFFECT_SDS:
            for active_fraction in POWER_ACTIVE_FRACTIONS:
                for replicate in range(1, replicates + 1):
                    rows.append(
                        {
                            "task_id": f"P{counter:06d}",
                            "replicate": replicate,
                            "pathway": pathway["pathway"],
                            "effect_sd": f"{effect_sd:.2f}",
                            "active_fraction": f"{active_fraction:.2f}",
                        }
                    )
                    counter += 1
    return rows


def build_fixed_null_tasks(*, replicates: int) -> list[dict[str, Any]]:
    return [
        {
            "task_id": f"N{replicate:04d}",
            "replicate": replicate,
            "pathway": "",
            "effect_sd": "0.00",
            "active_fraction": "0.00",
        }
        for replicate in range(1, replicates + 1)
    ]


def _input_payload(
    *,
    action: str,
    matrix: Any,
    collection_path: Path,
    extra: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "action": action,
        "matrix_path": str(matrix.path.resolve()),
        "gmt_path": str(collection_path.resolve()),
        "genes": [gene.symbol for gene in matrix.genes],
        "sample_ids": list(matrix.sample_ids),
        "min_gene_set_size": GSEA_MIN_SIZE,
        "max_gene_set_size": GSEA_MAX_SIZE,
        "expected_limma_version": EXPECTED_LIMMA_VERSION,
        **extra,
    }


def run_r(payload_path: Path, engine_path: Path) -> None:
    completed = subprocess.run(
        ["Rscript", str(engine_path), str(payload_path)],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode:
        detail = (completed.stderr or completed.stdout).strip()
        raise RuntimeError(
            f"CAMERA operating-characteristic engine failed for {payload_path.name}:\n"
            f"{detail[-5000:]}"
        )


def prepare(args: argparse.Namespace) -> None:
    output = args.output_dir.resolve()
    if output.exists() and any(output.iterdir()):
        raise RuntimeError(f"Refusing to overwrite prepared design: {output}")
    output.mkdir(parents=True, exist_ok=True)
    matrix, metadata, source_paths = load_expression_matrix(
        args.release_dir.resolve(), args.layer_id
    )
    collection_path = args.collection.resolve()
    selection_dir = output / "selection"
    selection_dir.mkdir()
    payload = _input_payload(
        action="prepare",
        matrix=matrix,
        collection_path=collection_path,
        extra={"output_dir": str(selection_dir)},
    )
    payload_path = selection_dir / "selection_input.json"
    write_json(payload_path, payload)
    run_r(payload_path, args.r_engine.resolve())

    selected_path = selection_dir / "selected_pathways.csv"
    selected = read_csv(selected_path)
    if len(selected) != 6:
        raise RuntimeError(f"Expected six frozen pathways; observed {len(selected)}.")
    if len({row["pathway"] for row in selected}) != 6:
        raise RuntimeError("Frozen pathways are not unique.")
    injections = freeze_injections(selected)
    injections_path = selection_dir / "frozen_injections.csv"
    write_csv(injections_path, injections)

    design = {
        "schema_version": SCHEMA_VERSION,
        "status": "frozen before pilot outcomes",
        "generated_at": utc_now(),
        "scientific_question": (
            "Compare strict per-set estimated correlation with limma's fixed "
            "rho=0.01 sensitivity under the same real-matrix null and planted "
            "competitive alternatives."
        ),
        "source": {
            "release": args.release_dir.resolve().name,
            "release_dir": workspace_path(args.release_dir),
            "layer": args.layer_id,
            "analysis_unit": metadata.get("analysis_unit"),
            "samples": len(matrix.sample_ids),
            "genes": len(matrix.genes),
            "matrix_sha256": sha256_file(matrix.path),
        },
        "gene_sets": {
            "collection": workspace_path(collection_path),
            "collection_sha256": sha256_file(collection_path),
            "min_observed_genes": GSEA_MIN_SIZE,
            "max_observed_genes": GSEA_MAX_SIZE,
        },
        "pathway_selection": {
            "uses_labels": False,
            "uses_outcomes": False,
            "size_strata": {
                "small_15_49": [15, 49],
                "medium_50_149": [50, 149],
                "large_150_500": [150, 500],
            },
            "correlation_strata": {
                "low_q25": 0.25,
                "high_q75": 0.75,
            },
            "correlation_basis": (
                "intercept-only residual correlation across all 51 source samples"
            ),
            "selected_pathways_sha256": sha256_file(selected_path),
            "candidate_pathways_sha256": sha256_file(
                selection_dir / "pathway_candidates.csv"
            ),
        },
        "injection": {
            "operation": (
                "For frozen group B, add effect_sd times each active gene's "
                "all-sample SD to every B sample."
            ),
            "residual_covariance": (
                "The constant group-specific shift is removed by the fitted "
                "B-minus-A design, leaving within-group residual covariance unchanged."
            ),
            "effect_sd": list(POWER_EFFECT_SDS),
            "active_fractions": list(POWER_ACTIVE_FRACTIONS),
            "active_gene_seed": ACTIVE_GENE_SEED,
            "active_genes_sha256": sha256_file(injections_path),
        },
        "methods": {
            "common": {
                "function": "limma::camera",
                "version": EXPECTED_LIMMA_VERSION,
                "design": "intercept plus B-minus-A",
                "use_ranks": False,
                "allow_negative_correlation": False,
                "trend_variance": True,
                "test": "two-sided directional competitive",
                "multiplicity": "BH across every eligible GO-BP pathway",
            },
            "primary": "estimated_per_set (inter.gene.cor=NA)",
            "sensitivity": "fixed_0_01 (inter.gene.cor=0.01)",
        },
        "frozen_labels": {
            "path": workspace_path(args.labels),
            "sha256": sha256_file(args.labels),
            "group_a_n": 26,
            "group_b_n": 25,
        },
        "run_rule": {
            "power_pilot_replicates": POWER_PILOT_REPLICATES,
            "power_formal_replicates_per_condition": POWER_FORMAL_REPLICATES,
            "fixed_null_pilot_replicates": FIXED_NULL_PILOT_REPLICATES,
            "fixed_null_formal_replicates": FIXED_NULL_FORMAL_REPLICATES,
            "formal_counts_will_not_change_after_pilot": True,
            "pilot_is_not_evidence": True,
        },
        "primary_power_outcome": (
            "probability that the injected target has BH q<=0.05"
        ),
        "secondary_outcomes": [
            "target CAMERA direction accuracy",
            "target raw p-value and BH q-value",
            "target rank among all eligible pathways",
            "probability of any rejection under the fixed-rho global null",
        ],
        "scope_boundary": (
            "The formal experiment characterizes this frozen LUAD matrix, balanced "
            "grouping and GO-BP family; it is not a universal power claim."
        ),
        "environment_at_freeze": environment_metadata(),
        "source_files": {
            role: {
                "path": workspace_path(path),
                "sha256": sha256_file(path),
            }
            for role, path in sorted(source_paths.items())
            if path.is_file()
        },
        "engine": {
            "path": workspace_path(args.r_engine),
            "sha256": sha256_file(args.r_engine),
            "runner_path": workspace_path(Path(__file__)),
            "runner_sha256": sha256_file(Path(__file__)),
        },
    }
    write_json(output / "preregistered_design.json", design)
    (output / "PREREGISTERED_DESIGN.md").write_text(
        "# CAMERA operating-characteristic design\n\n"
        "Status: frozen before the pilot and formal outcomes were generated.\n\n"
        "Six GO Biological Process terms were selected without labels or outcomes: "
        "one near the 25th and one near the 75th residual-correlation percentile "
        "within each of three overlap-size strata. Active genes were then fixed by "
        "a SHA-256 order.\n\n"
        "For each artificial group split, the power experiment adds a constant "
        "0.20 or 0.40 all-sample SD shift to 25% or 100% of the target genes in "
        "group B. Because the fitted model contains that group contrast, the "
        "within-group residual covariance remains unchanged.\n\n"
        "The strict production specification (`inter.gene.cor=NA`) and limma's "
        "fixed `0.01` sensitivity are run on the same injected matrices with BH "
        "over the same complete GO family. The primary outcome is detection of "
        "the planted target at q<=0.05. A separate fixed-0.01 null run consumes "
        "the exact 500 previously frozen labels.\n\n"
        "The pilot checks execution only. Formal replicate counts were fixed at "
        f"{POWER_FORMAL_REPLICATES} per planted condition and "
        f"{FIXED_NULL_FORMAL_REPLICATES} for the fixed-correlation null before "
        "pilot results were inspected.\n",
        encoding="utf-8",
    )
    write_base_manifest(output, args)


def _split_tasks(
    tasks: Sequence[dict[str, Any]], workers: int
) -> list[list[dict[str, Any]]]:
    chunks: list[list[dict[str, Any]]] = [[] for _ in range(workers)]
    for index, task in enumerate(tasks):
        chunks[index % workers].append(task)
    return [chunk for chunk in chunks if chunk]


def _phase_spec(phase: str) -> tuple[str, int, tuple[str, ...]]:
    if phase == "power_pilot":
        return "power", POWER_PILOT_REPLICATES, (
            "estimated_per_set",
            "fixed_0_01",
        )
    if phase == "power_formal":
        return "power", POWER_FORMAL_REPLICATES, (
            "estimated_per_set",
            "fixed_0_01",
        )
    if phase == "fixed_null_pilot":
        return "fixed_null", FIXED_NULL_PILOT_REPLICATES, ("fixed_0_01",)
    if phase == "fixed_null_formal":
        return "fixed_null", FIXED_NULL_FORMAL_REPLICATES, ("fixed_0_01",)
    raise ValueError(f"Unknown phase: {phase}.")


def merge_checkpoint_rows(
    phase_dir: Path,
    tasks: Sequence[dict[str, Any]],
    modes: Sequence[str],
) -> list[dict[str, str]]:
    """Merge complete worker checkpoints without rerunning the R engine."""

    checkpoint_paths = sorted(phase_dir.glob("checkpoint_worker_*.csv"))
    if not checkpoint_paths:
        raise RuntimeError(f"No worker checkpoints found in {phase_dir}.")
    rows: list[dict[str, str]] = []
    for path in checkpoint_paths:
        rows.extend(read_csv(path))
    expected_keys = {
        (str(task["task_id"]), mode) for task in tasks for mode in modes
    }
    observed_keys = {
        (row["task_id"], row["correlation_mode"]) for row in rows
    }
    if observed_keys != expected_keys or len(rows) != len(expected_keys):
        raise RuntimeError(
            f"Incomplete checkpoint: expected {len(expected_keys)} rows, "
            f"observed {len(rows)}."
        )
    rows.sort(key=lambda row: (row["task_id"], row["correlation_mode"]))
    return rows


def _pilot_pathways(selected: Sequence[dict[str, str]]) -> list[dict[str, str]]:
    wanted = {
        ("small_15_49", "low_q25"),
        ("large_150_500", "high_q75"),
    }
    result = [
        row
        for row in selected
        if (row["size_stratum"], row["correlation_stratum"]) in wanted
    ]
    if len(result) != 2:
        raise RuntimeError("Pilot pathway subset is incomplete.")
    return result


def run_phase(args: argparse.Namespace) -> None:
    output = args.output_dir.resolve()
    verify_prepared_design(output, args)
    run_type, replicates, modes = _phase_spec(args.phase)
    phase_dir = output / args.phase
    if phase_dir.exists() and any(phase_dir.iterdir()) and not args.resume:
        raise RuntimeError(
            f"Refusing to overwrite non-empty phase {phase_dir}; pass --resume."
        )
    phase_dir.mkdir(parents=True, exist_ok=True)

    matrix, metadata, _ = load_expression_matrix(
        args.release_dir.resolve(), args.layer_id
    )
    labels = validate_labels(
        args.labels.resolve(), sample_count=len(matrix.sample_ids), replicates=replicates
    )
    selected = read_csv(output / "selection" / "selected_pathways.csv")
    if run_type == "power":
        selected_for_run = (
            _pilot_pathways(selected) if args.phase == "power_pilot" else selected
        )
        tasks = build_power_tasks(selected_for_run, replicates=replicates)
    else:
        tasks = build_fixed_null_tasks(replicates=replicates)

    tasks_path = phase_dir / "tasks.csv"
    labels_path = phase_dir / "outer_label_permutations.csv"
    if not tasks_path.exists():
        write_csv(tasks_path, tasks)
    elif read_csv(tasks_path) != [
        {key: str(value) for key, value in row.items()} for row in tasks
    ]:
        raise RuntimeError("Existing checkpoint tasks do not match the frozen design.")
    if not labels_path.exists():
        write_csv(labels_path, labels)
    elif sha256_file(labels_path) != sha256_file(args.labels) and replicates == 500:
        raise RuntimeError("Formal fixed-null labels changed after checkpointing.")

    phase_design = {
        "schema_version": SCHEMA_VERSION,
        "phase": args.phase,
        "run_type": run_type,
        "formal": args.phase.endswith("formal"),
        "pilot_is_evidence": False if args.phase.endswith("pilot") else None,
        "replicates": replicates,
        "tasks": len(tasks),
        "correlation_modes": list(modes),
        "expected_result_rows": len(tasks) * len(modes),
        "workers": args.workers,
        "preregistered_design_sha256": sha256_file(
            output / "preregistered_design.json"
        ),
        "labels_sha256": sha256_file(labels_path),
        "tasks_sha256": sha256_file(tasks_path),
        "matrix_sha256": sha256_file(matrix.path),
        "collection_sha256": sha256_file(args.collection),
        "environment": environment_metadata(),
    }
    design_path = phase_dir / "design.json"
    if not design_path.exists():
        write_json(design_path, phase_design)

    chunks = _split_tasks(tasks, args.workers)
    payload_paths: list[Path] = []
    chunk_result_paths: list[Path] = []
    for index, chunk in enumerate(chunks, start=1):
        chunk_tasks_path = phase_dir / f"tasks_worker_{index:02d}.csv"
        if not chunk_tasks_path.exists():
            write_csv(chunk_tasks_path, chunk)
        result_path = phase_dir / f"checkpoint_worker_{index:02d}.csv"
        payload = _input_payload(
            action="run",
            matrix=matrix,
            collection_path=args.collection.resolve(),
            extra={
                "run_type": run_type,
                "tasks_path": str(chunk_tasks_path),
                "labels_path": str(labels_path),
                "selected_pathways_path": str(
                    output / "selection" / "selected_pathways.csv"
                ),
                "injections_path": str(
                    output / "selection" / "frozen_injections.csv"
                ),
                "correlation_modes": list(modes),
                "output_path": str(result_path),
            },
        )
        payload_path = phase_dir / f"input_worker_{index:02d}.json"
        write_json(payload_path, payload)
        payload_paths.append(payload_path)
        chunk_result_paths.append(result_path)

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(payload_paths)) as pool:
        futures = [
            pool.submit(run_r, payload_path, args.r_engine.resolve())
            for payload_path in payload_paths
        ]
        for future in concurrent.futures.as_completed(futures):
            future.result()

    result_rows = merge_checkpoint_rows(phase_dir, tasks, modes)
    merged_path = phase_dir / "results.csv"
    write_csv(merged_path, result_rows)
    summary = (
        summarize_power(result_rows, phase=args.phase)
        if run_type == "power"
        else summarize_fixed_null(result_rows, phase=args.phase)
    )
    if run_type == "fixed_null":
        summary["candidate_correlation_context"] = summarize_candidate_correlations(
            read_csv(output / "selection" / "pathway_candidates.csv")
        )
    summary.update(
        {
            "schema_version": SCHEMA_VERSION,
            "phase": args.phase,
            "formal": args.phase.endswith("formal"),
            "generated_at": utc_now(),
            "design_sha256": sha256_file(design_path),
            "results_sha256": sha256_file(merged_path),
        }
    )
    write_json(phase_dir / "summary.json", summary)
    write_phase_manifest(phase_dir, output, args)
    write_results_markdown(output)
    write_base_manifest(output, args)


def _mean(values: Iterable[float]) -> float:
    return statistics.fmean(list(values))


def _median(values: Iterable[float]) -> float:
    return statistics.median(list(values))


def summarize_candidate_correlations(
    rows: Sequence[dict[str, str]], *, fixed_rho: float = 0.01
) -> dict[str, Any]:
    """Describe the frozen pathway correlations using a real CSV parse."""

    if not rows:
        raise ValueError("Candidate pathway rows cannot be empty.")
    values = [float(row["all_sample_residual_correlation"]) for row in rows]
    if not all(math.isfinite(value) for value in values):
        raise ValueError("Candidate pathway correlations must be finite.")
    above = sum(value > fixed_rho for value in values)
    return {
        "fixed_rho": fixed_rho,
        "pathways": len(values),
        "pathways_above_fixed_rho": above,
        "proportion_above_fixed_rho": above / len(values),
        "median_residual_correlation": _median(values),
        "comparison": "strictly greater than fixed_rho",
        "source_field": "all_sample_residual_correlation",
    }


def summarize_power(rows: Sequence[dict[str, str]], *, phase: str) -> dict[str, Any]:
    groups: dict[tuple[str, str, str, str], list[dict[str, str]]] = {}
    for row in rows:
        key = (
            row["pathway"],
            row["effect_sd"],
            row["active_fraction"],
            row["correlation_mode"],
        )
        groups.setdefault(key, []).append(row)
    conditions: list[dict[str, Any]] = []
    for key, group in sorted(groups.items()):
        successes = sum(row["target_detected_q_le_0_05"].lower() == "true" for row in group)
        direction_correct = sum(row["direction_correct"].lower() == "true" for row in group)
        low, high = wilson_interval(successes, len(group))
        conditions.append(
            {
                "pathway": key[0],
                "selection_id": group[0]["selection_id"],
                "size_stratum": group[0]["size_stratum"],
                "correlation_stratum": group[0]["correlation_stratum"],
                "size_used": int(group[0]["size_used"]),
                "effect_sd": float(key[1]),
                "active_fraction": float(key[2]),
                "active_gene_count": int(group[0]["active_gene_count"]),
                "correlation_mode": key[3],
                "replicates": len(group),
                "target_detections_q_le_0_05": successes,
                "target_detection_probability": successes / len(group),
                "wilson_95_confidence_interval": [low, high],
                "direction_accuracy": direction_correct / len(group),
                "median_target_p": _median(float(row["target_p_value"]) for row in group),
                "median_target_fdr": _median(float(row["target_fdr"]) for row in group),
                "median_target_rank": _median(float(row["target_rank_by_p"]) for row in group),
                "mean_camera_seconds": _mean(float(row["camera_seconds"]) for row in group),
                "mean_estimated_target_correlation": (
                    _mean(
                        float(row["estimated_target_correlation"])
                        for row in group
                        if row["estimated_target_correlation"]
                    )
                    if key[3] == "estimated_per_set"
                    else None
                ),
            }
        )

    paired: dict[str, dict[str, dict[str, str]]] = {}
    for row in rows:
        paired.setdefault(row["task_id"], {})[row["correlation_mode"]] = row
    paired_decisions = {
        "both_detect": 0,
        "estimated_only": 0,
        "fixed_0_01_only": 0,
        "neither": 0,
    }
    for values in paired.values():
        if set(values) != {"estimated_per_set", "fixed_0_01"}:
            raise ValueError("Power results are not paired across CAMERA modes.")
        estimated = values["estimated_per_set"]["target_detected_q_le_0_05"].lower() == "true"
        fixed = values["fixed_0_01"]["target_detected_q_le_0_05"].lower() == "true"
        key = (
            "both_detect"
            if estimated and fixed
            else "estimated_only"
            if estimated
            else "fixed_0_01_only"
            if fixed
            else "neither"
        )
        paired_decisions[key] += 1

    return {
        "interpretation": (
            "Target detection is power for a known false competitive null. "
            "Other GO terms are not labelled false positives because GO overlap "
            "and the competitive complement make that classification ambiguous."
        ),
        "pilot_is_evidence": False if phase.endswith("pilot") else None,
        "result_rows": len(rows),
        "paired_tasks": len(paired),
        "conditions": conditions,
        "paired_target_decisions": paired_decisions,
        "maximum_residual_covariance_absolute_delta": max(
            float(row["residual_covariance_max_abs_delta"]) for row in rows
        ),
        "pathway_counts": sorted({int(row["pathways_tested"]) for row in rows}),
    }


def summarize_fixed_null(
    rows: Sequence[dict[str, str]], *, phase: str
) -> dict[str, Any]:
    thresholds: dict[str, Any] = {}
    for threshold in Q_THRESHOLDS:
        field = f"rejections_q_le_{threshold:.2f}".replace(".", "_")
        successes = sum(int(float(row[field])) > 0 for row in rows)
        low, high = wilson_interval(successes, len(rows))
        thresholds[f"q_le_{threshold:.2f}"] = {
            "replicates": len(rows),
            "replicates_with_any_rejection": successes,
            "probability_any_rejection": successes / len(rows),
            "wilson_95_confidence_interval": [low, high],
            "mean_rejections": _mean(float(row[field]) for row in rows),
        }
    comparison = None
    if phase == "fixed_null_formal" and DEFAULT_ESTIMATED_NULL.is_file():
        estimated = {row["replicate"]: row for row in read_csv(DEFAULT_ESTIMATED_NULL)}
        fixed = {row["replicate"]: row for row in rows}
        if set(estimated) == set(fixed):
            comparison = {}
            for threshold in Q_THRESHOLDS:
                suffix = f"{threshold:.2f}".replace(".", "_")
                est_field = f"any_q_le_{suffix}"
                fixed_field = f"rejections_q_le_{suffix}"
                counts = {"both": 0, "estimated_only": 0, "fixed_only": 0, "neither": 0}
                for replicate in sorted(fixed, key=int):
                    est_value = estimated[replicate][est_field].lower() == "true"
                    fixed_value = int(float(fixed[replicate][fixed_field])) > 0
                    key = (
                        "both"
                        if est_value and fixed_value
                        else "estimated_only"
                        if est_value
                        else "fixed_only"
                        if fixed_value
                        else "neither"
                    )
                    counts[key] += 1
                comparison[f"q_le_{threshold:.2f}"] = counts
    return {
        "interpretation": (
            "Under the complete label null every rejection is false; probability "
            "of any rejection is therefore the realized family FDR."
        ),
        "pilot_is_evidence": False if phase.endswith("pilot") else None,
        "replicates": len(rows),
        "thresholds": thresholds,
        "minimum_fdr": {
            "mean": _mean(float(row["min_fdr"]) for row in rows),
            "median": _median(float(row["min_fdr"]) for row in rows),
            "minimum": min(float(row["min_fdr"]) for row in rows),
        },
        "paired_with_estimated_per_set": comparison,
        "pathway_counts": sorted({int(row["pathways_tested"]) for row in rows}),
        "mean_camera_seconds": _mean(float(row["camera_seconds"]) for row in rows),
    }


def write_phase_manifest(
    phase_dir: Path, output_root: Path, args: argparse.Namespace
) -> None:
    excluded = {"manifest.json", "SHA256SUMS"}
    outputs = [
        path
        for path in sorted(phase_dir.iterdir())
        if path.is_file() and path.name not in excluded
    ]
    inputs = [
        output_root / "preregistered_design.json",
        output_root / "selection" / "selected_pathways.csv",
        output_root / "selection" / "frozen_injections.csv",
        args.labels.resolve(),
        args.collection.resolve(),
        args.r_engine.resolve(),
        Path(__file__).resolve(),
    ]
    manifest = {
        "schema_version": "trace-camera-operating-characteristics-manifest-v1",
        "generated_at": utc_now(),
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
    checksum_paths = outputs + [phase_dir / "manifest.json"]
    (phase_dir / "SHA256SUMS").write_text(
        "".join(f"{sha256_file(path)}  {path.name}\n" for path in checksum_paths),
        encoding="utf-8",
    )


def write_base_manifest(output: Path, args: argparse.Namespace) -> None:
    files = [
        path
        for path in sorted(output.rglob("*"))
        if path.is_file()
        and path.name not in {"artifact_manifest.json", "SHA256SUMS"}
    ]
    manifest = {
        "schema_version": "trace-camera-operating-characteristics-artifact-v1",
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
    checksum_files = files + [output / "artifact_manifest.json"]
    (output / "SHA256SUMS").write_text(
        "".join(
            f"{sha256_file(path)}  {path.relative_to(output)}\n"
            for path in checksum_files
        ),
        encoding="utf-8",
    )


def verify_prepared_design(output: Path, args: argparse.Namespace) -> None:
    design_path = output / "preregistered_design.json"
    selected_path = output / "selection" / "selected_pathways.csv"
    injections_path = output / "selection" / "frozen_injections.csv"
    if not all(path.is_file() for path in (design_path, selected_path, injections_path)):
        raise RuntimeError("Run --phase prepare before a pilot or formal phase.")
    design = json.loads(design_path.read_text(encoding="utf-8"))
    expected = design["pathway_selection"]["selected_pathways_sha256"]
    if sha256_file(selected_path) != expected:
        raise RuntimeError("Frozen pathway selection checksum changed.")
    if sha256_file(injections_path) != design["injection"]["active_genes_sha256"]:
        raise RuntimeError("Frozen active-gene checksum changed.")
    if sha256_file(args.labels) != design["frozen_labels"]["sha256"]:
        raise RuntimeError("Frozen outer labels changed.")
    if sha256_file(args.collection) != design["gene_sets"]["collection_sha256"]:
        raise RuntimeError("Frozen GO collection changed.")


def verify_manifest(path: Path, root: Path) -> None:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    for item in manifest.get("outputs") or []:
        candidate = path.parent / item["file"]
        if not candidate.is_file() or sha256_file(candidate) != item["sha256"]:
            raise RuntimeError(f"Artifact checksum mismatch: {candidate}")
    for item in manifest.get("inputs") or []:
        candidate = Path(item["path"])
        if not candidate.is_absolute():
            candidate = root / candidate
        if not candidate.is_file() or sha256_file(candidate) != item["sha256"]:
            raise RuntimeError(f"Input checksum mismatch: {candidate}")


def refresh_from_checkpoints(args: argparse.Namespace) -> None:
    """Regenerate summaries and manifests from complete frozen checkpoints only."""

    output = args.output_dir.resolve()
    verify_prepared_design(output, args)
    preregistered = json.loads(
        (output / "preregistered_design.json").read_text(encoding="utf-8")
    )
    phase_records: list[dict[str, Any]] = []
    for phase in (
        "power_pilot",
        "power_formal",
        "fixed_null_pilot",
        "fixed_null_formal",
    ):
        phase_dir = output / phase
        if not phase_dir.is_dir():
            continue
        design_path = phase_dir / "design.json"
        design = json.loads(design_path.read_text(encoding="utf-8"))
        tasks = read_csv(phase_dir / "tasks.csv")
        modes = tuple(str(mode) for mode in design["correlation_modes"])
        rows = merge_checkpoint_rows(phase_dir, tasks, modes)
        if len(rows) != int(design["expected_result_rows"]):
            raise RuntimeError(f"Unexpected checkpoint count for {phase}.")

        prior_summary_path = phase_dir / "summary.json"
        prior_results_sha256 = None
        if prior_summary_path.is_file():
            prior_summary = json.loads(prior_summary_path.read_text(encoding="utf-8"))
            prior_results_sha256 = prior_summary.get("results_sha256")
        results_path = phase_dir / "results.csv"
        write_csv(results_path, rows)
        refreshed_results_sha256 = sha256_file(results_path)
        if (
            prior_results_sha256
            and prior_results_sha256 != refreshed_results_sha256
        ):
            raise RuntimeError(
                f"Checkpoint refresh changed the recorded compute results for {phase}."
            )

        run_type = str(design["run_type"])
        summary = (
            summarize_power(rows, phase=phase)
            if run_type == "power"
            else summarize_fixed_null(rows, phase=phase)
        )
        if run_type == "fixed_null":
            summary["candidate_correlation_context"] = (
                summarize_candidate_correlations(
                    read_csv(output / "selection" / "pathway_candidates.csv")
                )
            )
        summary.update(
            {
                "schema_version": SCHEMA_VERSION,
                "phase": phase,
                "formal": phase.endswith("formal"),
                "generated_at": utc_now(),
                "design_sha256": sha256_file(design_path),
                "results_sha256": refreshed_results_sha256,
                "regenerated_from_complete_checkpoints": True,
            }
        )
        write_json(prior_summary_path, summary)
        write_phase_manifest(phase_dir, output, args)
        phase_records.append(
            {
                "phase": phase,
                "result_rows": len(rows),
                "results_sha256_before_refresh": prior_results_sha256,
                "results_sha256_after_refresh": refreshed_results_sha256,
                "compute_results_changed": False,
            }
        )

    if not phase_records:
        raise RuntimeError("No completed CAMERA phases were available to refresh.")
    correction = {
        "schema_version": "trace-camera-report-source-correction-v1",
        "generated_at": utc_now(),
        "scope": (
            "Reporting and validation source only; formal R computations were not rerun."
        ),
        "formal_compute_repeated": False,
        "frozen_runner_sha256": preregistered["engine"]["runner_sha256"],
        "current_runner_sha256": sha256_file(Path(__file__)),
        "frozen_r_engine_sha256": preregistered["engine"]["sha256"],
        "current_r_engine_sha256": sha256_file(args.r_engine.resolve()),
        "r_engine_changed": (
            preregistered["engine"]["sha256"]
            != sha256_file(args.r_engine.resolve())
        ),
        "corrections": [
            "parse quoted pathway CSV fields with csv.DictReader",
            "derive fixed-rho correlation context in code",
            "make the diagnostic-only fixed-rho interpretation reproducible",
            "rebuild summaries and manifests from complete worker checkpoints",
        ],
        "phases": phase_records,
    }
    write_json(output / "source_correction.json", correction)
    write_results_markdown(output)
    write_base_manifest(output, args)
    print(
        "Refreshed CAMERA summaries from complete checkpoints without rerunning R: "
        f"{output}"
    )


def check_only(args: argparse.Namespace) -> None:
    output = args.output_dir.resolve()
    verify_prepared_design(output, args)
    preregistered = json.loads(
        (output / "preregistered_design.json").read_text(encoding="utf-8")
    )
    for phase in (
        "power_pilot",
        "power_formal",
        "fixed_null_pilot",
        "fixed_null_formal",
    ):
        phase_dir = output / phase
        if not phase_dir.is_dir():
            continue
        verify_manifest(phase_dir / "manifest.json", ROOT)
        design = json.loads((phase_dir / "design.json").read_text(encoding="utf-8"))
        rows = read_csv(phase_dir / "results.csv")
        if len(rows) != int(design["expected_result_rows"]):
            raise RuntimeError(f"Unexpected result count for {phase}.")
        summary = json.loads((phase_dir / "summary.json").read_text(encoding="utf-8"))
        if summary["results_sha256"] != sha256_file(phase_dir / "results.csv"):
            raise RuntimeError(f"Summary/result checksum mismatch for {phase}.")
        checkpoint_rows = merge_checkpoint_rows(
            phase_dir,
            read_csv(phase_dir / "tasks.csv"),
            tuple(str(mode) for mode in design["correlation_modes"]),
        )
        if checkpoint_rows != rows:
            raise RuntimeError(f"Merged results differ from checkpoints for {phase}.")
        if design["run_type"] == "fixed_null":
            expected_context = summarize_candidate_correlations(
                read_csv(output / "selection" / "pathway_candidates.csv")
            )
            if summary.get("candidate_correlation_context") != expected_context:
                raise RuntimeError(
                    f"Candidate correlation context is stale for {phase}."
                )

    frozen_runner_sha256 = preregistered["engine"]["runner_sha256"]
    current_runner_sha256 = sha256_file(Path(__file__))
    if current_runner_sha256 != frozen_runner_sha256:
        correction_path = output / "source_correction.json"
        if not correction_path.is_file():
            raise RuntimeError("A post-run source correction record is required.")
        correction = json.loads(correction_path.read_text(encoding="utf-8"))
        if (
            correction.get("frozen_runner_sha256") != frozen_runner_sha256
            or correction.get("current_runner_sha256") != current_runner_sha256
            or correction.get("formal_compute_repeated") is not False
            or correction.get("r_engine_changed") is not False
        ):
            raise RuntimeError("The source correction record is inconsistent.")
    manifest = json.loads((output / "artifact_manifest.json").read_text(encoding="utf-8"))
    for item in manifest["files"]:
        path = output / item["path"]
        if not path.is_file() or sha256_file(path) != item["sha256"]:
            raise RuntimeError(f"Base artifact checksum mismatch: {path}")
    print(f"Verified CAMERA operating-characteristic artifact: {output}")


def _percent(value: float) -> str:
    return f"{100 * value:.1f}%"


def write_results_markdown(output: Path) -> None:
    lines = [
        "# CAMERA operating-characteristic results",
        "",
        "The production method was not changed by this experiment. Per-set estimated",
        "correlation remains the strict primary specification; fixed rho=0.01 is",
        "evaluated as a ranking-oriented limma sensitivity.",
        "",
    ]
    fixed_path = output / "fixed_null_formal" / "summary.json"
    if fixed_path.is_file():
        fixed = json.loads(fixed_path.read_text(encoding="utf-8"))
        lines.extend(["## Fixed rho=0.01 under the frozen global null", ""])
        for threshold, result in fixed["thresholds"].items():
            low, high = result["wilson_95_confidence_interval"]
            lines.append(
                f"- {threshold.replace('_', ' ')}: "
                f"{result['replicates_with_any_rejection']}/{result['replicates']} "
                f"({_percent(result['probability_any_rejection'])}; 95% Wilson CI "
                f"{_percent(low)}--{_percent(high)})."
            )
        lines.extend(
            [
                "",
                "Under the complete null, this probability is the realized family FDR.",
            ]
        )
        context = fixed["candidate_correlation_context"]
        lines.extend(
            [
                f"Across the {context['pathways']:,} eligible pathways, the median "
                f"frozen residual correlation was "
                f"{context['median_residual_correlation']:.7f} and "
                f"{context['pathways_above_fixed_rho']:,} "
                f"({_percent(context['proportion_above_fixed_rho'])}) exceeded "
                f"{context['fixed_rho']:.2f}.",
                "The fixed value therefore reduced the correlation correction for",
                "nearly the entire tested family. Its q<=0.05 false-family rate",
                "invalidates its target-detection proportions as estimates of power",
                "or as evidence of an advantage over per-set estimation.",
                "",
            ]
        )
    formal_path = output / "power_formal" / "summary.json"
    if formal_path.is_file():
        power = json.loads(formal_path.read_text(encoding="utf-8"))
        lines.extend(
            [
                "## Semi-synthetic pathway power",
                "",
                "Each cell below is the probability that the planted target passed BH",
                "q<=0.05. Every planted shift preserved the source residual covariance",
                f"to a maximum absolute numerical difference of {power['maximum_residual_covariance_absolute_delta']:.3g}.",
                "",
                "| Target | Size/rho stratum | Shift (SD) | Active | Estimated rho | Fixed 0.01 (diagnostic only) |",
                "|---|---|---:|---:|---:|---:|",
            ]
        )
        by_condition: dict[tuple[str, float, float], dict[str, Any]] = {}
        for row in power["conditions"]:
            key = (row["selection_id"], row["effect_sd"], row["active_fraction"])
            by_condition.setdefault(key, {})[row["correlation_mode"]] = row
        for key, modes in sorted(by_condition.items()):
            estimated = modes["estimated_per_set"]
            fixed = modes["fixed_0_01"]
            label = f"{estimated['size_stratum']} / {estimated['correlation_stratum']}"
            lines.append(
                f"| {key[0]} | {label} | {key[1]:.2f} | {_percent(key[2])} | "
                f"{_percent(estimated['target_detection_probability'])} | "
                f"{_percent(fixed['target_detection_probability'])} |"
            )
        paired = power["paired_target_decisions"]
        lines.extend(
            [
                "",
                "Paired decisions across all planted target-replicates: "
                f"both {paired['both_detect']}, estimated only {paired['estimated_only']}, "
                f"fixed only {paired['fixed_0_01_only']}, neither {paired['neither']}.",
                "",
                "The fixed-only count documents the consequence of the correlation",
                "assumption; it is not interpretable as additional valid power because",
                "that specification failed the matched complete-null experiment above.",
                "",
                "These curves characterize the frozen LUAD matrix and GO-BP family.",
                "GO overlap prevents treating every non-target rejection as a false",
                "positive under the planted alternative, so the formal power endpoint is",
                "detection of the known false target null.",
                "",
            ]
        )
    if not formal_path.is_file() and not fixed_path.is_file():
        lines.extend(
            [
                "Only preparation or pilot artifacts are currently present. Pilot outcomes",
                "validate execution and are not inferential evidence.",
                "",
            ]
        )
    (output / "RESULTS.md").write_text("\n".join(lines), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--phase",
        required=True,
        choices=(
            "prepare",
            "power_pilot",
            "power_formal",
            "fixed_null_pilot",
            "fixed_null_formal",
            "refresh",
            "check",
        ),
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--release-dir", type=Path, default=DEFAULT_RELEASE)
    parser.add_argument("--layer-id", default=DEFAULT_LAYER)
    parser.add_argument("--collection", type=Path, default=DEFAULT_COLLECTION)
    parser.add_argument(
        "--collection-manifest", type=Path, default=DEFAULT_COLLECTION_MANIFEST
    )
    parser.add_argument("--labels", type=Path, default=DEFAULT_LABELS)
    parser.add_argument("--r-engine", type=Path, default=DEFAULT_R_ENGINE)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    if args.workers < 1:
        parser.error("--workers must be positive.")
    return args


def main() -> int:
    args = parse_args()
    if args.phase == "prepare":
        prepare(args)
    elif args.phase == "refresh":
        refresh_from_checkpoints(args)
    elif args.phase == "check":
        check_only(args)
    else:
        run_phase(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
