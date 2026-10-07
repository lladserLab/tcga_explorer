#!/usr/bin/env python3
"""Calibrate TRACE's CAMERA v2 pathway inference under frozen label nulls.

This runner deliberately does not generate random labels.  It consumes the
explicit outer-label permutations frozen by ``run_molecular_null_calibration``
and calls the production matrix-preparation and CAMERA inference functions.
Consequently a CAMERA v2 result can be paired replicate-for-replicate with the
legacy preranked calibration without changing the cohort, matrix, group sizes,
or group assignments.

The script is publication infrastructure only.  It does not alter TRACE's
production implementation or its defaults.
"""

from __future__ import annotations

import argparse
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
import tempfile
import time
from typing import Any, Iterable, Sequence


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.gsea import (  # noqa: E402
    prepare_camera_expression_matrix,
    run_camera_gene_set_test,
)
from app.pipeline_versions import GSEA_PIPELINE_VERSION  # noqa: E402
from scripts.publication.run_molecular_null_calibration import (  # noqa: E402
    DEFAULT_COLLECTION,
    DEFAULT_COLLECTION_MANIFEST,
    DEFAULT_LAYER,
    DEFAULT_OUTPUT as LEGACY_OUTPUT,
    DEFAULT_RELEASE,
    GSEA_MAX_SIZE,
    GSEA_MIN_SIZE,
    Q_THRESHOLDS,
    load_expression_matrix,
    parse_positions,
    read_csv,
    sha256_file,
    wilson_interval,
    workspace_path,
    write_csv,
    write_json,
)


SCHEMA_VERSION = "trace-camera-null-calibration-v2"
DEFAULT_OUTPUT = LEGACY_OUTPUT
DEFAULT_FROZEN_PERMUTATIONS = LEGACY_OUTPUT / "full" / "outer_label_permutations.csv"
DEFAULT_CAMERA_R = ROOT / "backend" / "scripts" / "camera_gsea.R"


_CAMERA_CONTEXT: dict[str, Any] = {}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def q_suffix(threshold: float) -> str:
    return f"{threshold:.2f}".replace(".", "_")


def _truth(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().casefold() in {"true", "1", "yes"}


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _numeric_distribution(values: Iterable[float]) -> dict[str, float | int | None]:
    finite = sorted(float(value) for value in values if math.isfinite(float(value)))
    if not finite:
        return {
            "evaluable": 0,
            "mean": None,
            "median": None,
            "p95": None,
            "maximum": None,
        }
    p95_index = max(0, math.ceil(0.95 * len(finite)) - 1)
    return {
        "evaluable": len(finite),
        "mean": statistics.fmean(finite),
        "median": statistics.median(finite),
        "p95": finite[p95_index],
        "maximum": finite[-1],
    }


def _quantile(values: Sequence[float], probability: float) -> float:
    if not values:
        raise ValueError("Cannot compute a quantile of an empty sequence.")
    ordered = sorted(float(value) for value in values)
    position = probability * (len(ordered) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def load_frozen_permutations(
    path: Path,
    *,
    sample_count: int,
    replicates: int | None,
) -> list[dict[str, Any]]:
    """Read and validate explicit, zero-based B-group positions.

    No seed or random-number generator is accepted here.  This is intentional:
    CAMERA must consume the exact outer labels used by the frozen v1 run.
    """

    rows = read_csv(path)
    if not rows:
        raise ValueError("The frozen permutation file is empty.")
    selected = rows if replicates is None else rows[:replicates]
    if replicates is not None and len(selected) != replicates:
        raise ValueError(
            f"Requested {replicates} frozen permutations but only {len(rows)} exist."
        )
    expected_replicates = list(range(1, len(selected) + 1))
    observed_replicates = [int(row["replicate"]) for row in selected]
    if observed_replicates != expected_replicates:
        raise ValueError(
            "Frozen permutations must be the ordered prefix beginning at replicate 1."
        )
    validated: list[dict[str, Any]] = []
    for row in selected:
        group_a_n = int(row["group_a_n"])
        group_b_n = int(row["group_b_n"])
        positions = parse_positions(row["group_b_zero_based_positions"])
        if group_a_n + group_b_n != sample_count:
            raise ValueError("A frozen permutation has an incompatible sample count.")
        if len(positions) != group_b_n or len(set(positions)) != group_b_n:
            raise ValueError("A frozen permutation has duplicate or missing B positions.")
        if any(position < 0 or position >= sample_count for position in positions):
            raise ValueError("A frozen permutation contains an out-of-range position.")
        if tuple(sorted(positions)) != positions:
            raise ValueError("Frozen B positions must be sorted.")
        validated.append(
            {
                "replicate": int(row["replicate"]),
                "group_a_n": group_a_n,
                "group_b_n": group_b_n,
                "group_b_zero_based_positions": ";".join(
                    str(position) for position in positions
                ),
            }
        )
    return validated


def _initialize_camera_worker(
    release_dir: str,
    layer_id: str,
    gene_set_path: str,
    camera_r_path: str,
) -> None:
    matrix, _, _ = load_expression_matrix(Path(release_dir), layer_id)
    _CAMERA_CONTEXT.clear()
    _CAMERA_CONTEXT.update(
        {
            "matrix": matrix,
            "gene_set_path": Path(gene_set_path),
            "camera_r_path": Path(camera_r_path),
        }
    )


def _camera_worker(task: tuple[int, str]) -> dict[str, Any]:
    replicate, encoded_positions = task
    matrix = _CAMERA_CONTEXT["matrix"]
    group_b = set(parse_positions(encoded_positions))
    assignments = {
        sample_id: ("b" if index in group_b else "a")
        for index, sample_id in enumerate(matrix.sample_ids)
    }
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix=f"trace-camera-null-{replicate:04d}-") as temp:
        work_dir = Path(temp)
        ranked, ranking_metadata, camera_matrix = prepare_camera_expression_matrix(
            matrix,
            assignments,
            ranking_metric="welch_t",
            camera_matrix_path=work_dir / "camera_expression.float32le.bin",
        )
        camera_rows, details = run_camera_gene_set_test(
            camera_matrix,
            gene_set_path=_CAMERA_CONTEXT["gene_set_path"],
            min_size=GSEA_MIN_SIZE,
            max_size=GSEA_MAX_SIZE,
            work_dir=work_dir / "engine",
            r_script_path=_CAMERA_CONTEXT["camera_r_path"],
        )
    if not camera_rows:
        raise RuntimeError("CAMERA returned no eligible pathways.")
    minimum = min(
        camera_rows,
        key=lambda row: (float(row["fdr"]), float(row["p_value"]), row["pathway"]),
    )
    correlations = [float(row["camera_correlation"]) for row in camera_rows]
    result: dict[str, Any] = {
        "replicate": replicate,
        "group_a_n": len(matrix.sample_ids) - len(group_b),
        "group_b_n": len(group_b),
        "genes_ranked": int(ranking_metadata["genes_ranked"]),
        "complete_case_genes": int(details["complete_case_genes"]),
        "pathways_tested": int(details["pathways_tested"]),
        "min_q": float(minimum["fdr"]),
        "min_q_pathway": str(minimum["pathway"]),
        "min_q_p_value": float(minimum["p_value"]),
        "min_q_camera_correlation": float(minimum["camera_correlation"]),
        "camera_correlation_mean": statistics.fmean(correlations),
        "camera_correlation_median": statistics.median(correlations),
        "camera_correlation_p05": _quantile(correlations, 0.05),
        "camera_correlation_p95": _quantile(correlations, 0.95),
        "camera_correlation_minimum": min(correlations),
        "camera_correlation_maximum": max(correlations),
        "camera_correlation_mean_absolute": statistics.fmean(
            abs(value) for value in correlations
        ),
        "camera_engine_seconds": float(details["camera_engine_seconds"]),
        "camera_process_wall_seconds": float(
            details["camera_process_wall_seconds"]
        ),
        "replicate_wall_seconds": time.perf_counter() - started,
    }
    for threshold in Q_THRESHOLDS:
        suffix = q_suffix(threshold)
        count = sum(float(row["fdr"]) <= threshold for row in camera_rows)
        result[f"rejections_q_le_{suffix}"] = count
        result[f"any_q_le_{suffix}"] = count > 0
    return result


def run_camera_calibration(
    permutation_rows: Sequence[dict[str, Any]],
    *,
    release_dir: Path,
    layer_id: str,
    gene_set_path: Path,
    camera_r_path: Path,
    workers: int,
) -> tuple[list[dict[str, Any]], float]:
    tasks = [
        (int(row["replicate"]), str(row["group_b_zero_based_positions"]))
        for row in permutation_rows
    ]
    started = time.perf_counter()
    results: list[dict[str, Any]] = []
    progress_every = max(1, min(10, len(tasks) // 10 or 1))
    if workers == 1:
        _initialize_camera_worker(
            str(release_dir), layer_id, str(gene_set_path), str(camera_r_path)
        )
        iterator: Iterable[dict[str, Any]] = map(_camera_worker, tasks)
        for index, result in enumerate(iterator, start=1):
            results.append(result)
            if index % progress_every == 0 or index == len(tasks):
                print(f"CAMERA outer permutations: {index}/{len(tasks)}", flush=True)
    else:
        methods = multiprocessing.get_all_start_methods()
        context = multiprocessing.get_context("fork" if "fork" in methods else "spawn")
        with context.Pool(
            processes=workers,
            initializer=_initialize_camera_worker,
            initargs=(
                str(release_dir),
                layer_id,
                str(gene_set_path),
                str(camera_r_path),
            ),
            maxtasksperchild=10,
        ) as pool:
            for index, result in enumerate(
                pool.imap_unordered(_camera_worker, tasks), start=1
            ):
                results.append(result)
                if index % progress_every == 0 or index == len(tasks):
                    print(f"CAMERA outer permutations: {index}/{len(tasks)}", flush=True)
    results.sort(key=lambda row: int(row["replicate"]))
    return results, time.perf_counter() - started


def summarize_camera(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    thresholds: dict[str, Any] = {}
    for threshold in Q_THRESHOLDS:
        suffix = q_suffix(threshold)
        evaluable = [row for row in rows if str(row.get(f"any_q_le_{suffix}", ""))]
        successes = sum(_truth(row[f"any_q_le_{suffix}"]) for row in evaluable)
        low, high = wilson_interval(successes, len(evaluable))
        counts = [float(row[f"rejections_q_le_{suffix}"]) for row in evaluable]
        thresholds[f"q_le_{threshold:.2f}"] = {
            "replicates": len(evaluable),
            "replicates_with_any_rejection": successes,
            "probability_any_rejection": successes / len(evaluable),
            "wilson_95_confidence_interval": [low, high],
            "rejections_per_replicate": _numeric_distribution(counts),
        }
    return {
        "interpretation": (
            "Under the global outer label null, every CAMERA rejection is false. "
            "For a BH-controlled pathway family, the probability of at least one "
            "rejection is therefore the realized false-discovery rate."
        ),
        "thresholds": thresholds,
        "minimum_q": _numeric_distribution(
            value
            for row in rows
            if (value := _finite(row.get("min_q"))) is not None
        ),
        "pathways_tested": _numeric_distribution(
            float(row["pathways_tested"]) for row in rows
        ),
        "runtime_per_replicate_seconds": {
            field: _numeric_distribution(float(row[field]) for row in rows)
            for field in (
                "camera_engine_seconds",
                "camera_process_wall_seconds",
                "replicate_wall_seconds",
            )
        },
        "inter_gene_correlation_across_replicates": {
            field: _numeric_distribution(float(row[field]) for row in rows)
            for field in (
                "camera_correlation_mean",
                "camera_correlation_median",
                "camera_correlation_p05",
                "camera_correlation_p95",
                "camera_correlation_minimum",
                "camera_correlation_maximum",
                "camera_correlation_mean_absolute",
            )
        },
    }


def environment_metadata() -> dict[str, Any]:
    def command_output(command: Sequence[str]) -> str | None:
        try:
            completed = subprocess.run(
                list(command), check=False, capture_output=True, text=True
            )
        except OSError:
            return None
        if completed.returncode != 0:
            return None
        return (completed.stdout or completed.stderr).strip() or None

    return {
        "python": sys.version.replace("\n", " "),
        "platform": platform.platform(),
        "r": command_output(["Rscript", "-e", "cat(R.version.string)"]),
        "limma": command_output(
            ["Rscript", "-e", 'cat(as.character(packageVersion("limma")))']
        ),
        "container_image": os.environ.get("TRACE_CALIBRATION_CONTAINER_IMAGE"),
        "git_commit": command_output(["git", "rev-parse", "HEAD"]),
    }


def write_manifest(
    phase_dir: Path,
    *,
    input_paths: dict[str, Path],
) -> None:
    excluded = {"manifest.json", "SHA256SUMS"}
    outputs = [
        path
        for path in sorted(phase_dir.iterdir())
        if path.is_file() and path.name not in excluded
    ]
    manifest = {
        "schema_version": "trace-camera-null-calibration-manifest-v2",
        "generated_at": utc_now(),
        "inputs": [
            {
                "role": role,
                "path": workspace_path(path),
                "sha256": sha256_file(path),
                "bytes": path.stat().st_size,
            }
            for role, path in sorted(input_paths.items())
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


def verify_phase(phase_dir: Path) -> None:
    manifest_path = phase_dir / "manifest.json"
    if not manifest_path.is_file():
        raise RuntimeError(f"Missing manifest: {manifest_path}.")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for item in manifest.get("outputs") or []:
        path = phase_dir / item["file"]
        if not path.is_file() or sha256_file(path) != item["sha256"]:
            raise RuntimeError(f"Checksum mismatch: {path}.")
    for item in manifest.get("inputs") or []:
        raw_path = Path(item["path"])
        path = raw_path if raw_path.is_absolute() else ROOT / raw_path
        if not path.is_file() or sha256_file(path) != item["sha256"]:
            raise RuntimeError(f"Frozen input checksum mismatch: {path}.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Calibrate production CAMERA inference using explicitly frozen "
            "outer-label permutations from the molecular null experiment."
        )
    )
    parser.add_argument(
        "--phase",
        choices=("camera_v2_pilot", "camera_v2_full"),
        required=True,
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--frozen-permutations", type=Path, default=DEFAULT_FROZEN_PERMUTATIONS
    )
    parser.add_argument("--release-dir", type=Path, default=DEFAULT_RELEASE)
    parser.add_argument("--layer-id", default=DEFAULT_LAYER)
    parser.add_argument("--collection", type=Path, default=DEFAULT_COLLECTION)
    parser.add_argument(
        "--collection-manifest", type=Path, default=DEFAULT_COLLECTION_MANIFEST
    )
    parser.add_argument("--camera-r-script", type=Path, default=DEFAULT_CAMERA_R)
    parser.add_argument("--replicates", type=int)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    if args.replicates is None:
        args.replicates = {
            "camera_v2_pilot": 5,
            "camera_v2_full": 500,
        }[args.phase]
    if args.replicates < 1:
        parser.error("--replicates must be positive.")
    if args.workers < 1:
        parser.error("--workers must be positive.")
    return args


def main() -> int:
    args = parse_args()
    phase_dir = args.output_dir.resolve() / args.phase
    if args.check_only:
        verify_phase(phase_dir)
        print(f"Verified {phase_dir}")
        return 0
    if phase_dir.exists() and any(phase_dir.iterdir()):
        raise RuntimeError(f"Refusing to overwrite a non-empty phase: {phase_dir}.")
    phase_dir.mkdir(parents=True, exist_ok=True)

    release_dir = args.release_dir.resolve()
    collection_path = args.collection.resolve()
    collection_manifest = args.collection_manifest.resolve()
    camera_r_path = args.camera_r_script.resolve()
    frozen_source = args.frozen_permutations.resolve()
    matrix, metadata, source_paths = load_expression_matrix(release_dir, args.layer_id)
    permutation_rows = load_frozen_permutations(
        frozen_source,
        sample_count=len(matrix.sample_ids),
        replicates=args.replicates,
    )
    frozen_copy = phase_dir / "outer_label_permutations.csv"
    write_csv(frozen_copy, permutation_rows)

    design = {
        "schema_version": SCHEMA_VERSION,
        "phase": args.phase,
        "generated_at": utc_now(),
        "source": {
            "release_dir": workspace_path(release_dir),
            "release_id": release_dir.name,
            "expression_layer": args.layer_id,
            "expression_scale": metadata.get("analysis_unit"),
            "samples": len(matrix.sample_ids),
            "genes": len(matrix.genes),
            "matrix_sha256": matrix.source_sha256,
        },
        "frozen_outer_label_null": {
            "source_path": workspace_path(frozen_source),
            "source_sha256": sha256_file(frozen_source),
            "selection": f"ordered prefix of {args.replicates} replicates",
            "copied_permutations_sha256": sha256_file(frozen_copy),
            "index_convention": "zero-based positions in the frozen matrix sample order",
            "group_a_n": int(permutation_rows[0]["group_a_n"]),
            "group_b_n": int(permutation_rows[0]["group_b_n"]),
            "regenerated": False,
        },
        "camera": {
            "inference": "limma CAMERA two-sided competitive test",
            "design": "intercept plus group B-minus-A",
            "use_ranks": False,
            "trend_variance": True,
            "inter_gene_correlation": "estimated separately for each gene set",
            "allow_negative_correlation": False,
            "multiplicity": "BH across all eligible pathways",
            "collection": workspace_path(collection_path),
            "min_gene_set_size": GSEA_MIN_SIZE,
            "max_gene_set_size": GSEA_MAX_SIZE,
            "production_pipeline_version": GSEA_PIPELINE_VERSION,
            "production_python_functions": [
                "app.gsea.prepare_camera_expression_matrix",
                "app.gsea.run_camera_gene_set_test",
            ],
            "production_r_engine": workspace_path(camera_r_path),
        },
        "reported_q_thresholds": list(Q_THRESHOLDS),
        "workers": args.workers,
    }
    write_json(phase_dir / "design.json", design)

    rows, elapsed = run_camera_calibration(
        permutation_rows,
        release_dir=release_dir,
        layer_id=args.layer_id,
        gene_set_path=collection_path,
        camera_r_path=camera_r_path,
        workers=args.workers,
    )
    if len(rows) != args.replicates:
        raise RuntimeError("CAMERA returned the wrong number of outer replicates.")
    results_path = phase_dir / "camera_replicates.csv"
    write_csv(results_path, rows)
    summary = {
        "schema_version": SCHEMA_VERSION,
        "phase": args.phase,
        "generated_at": utc_now(),
        "replicates": args.replicates,
        "camera": summarize_camera(rows),
        "runtime": {
            "wall_seconds": elapsed,
            "seconds_per_outer_replicate_wall": elapsed / args.replicates,
            "projected_500_replicate_wall_seconds_at_same_worker_count": (
                elapsed * 500 / args.replicates
                if args.phase == "camera_v2_pilot"
                else elapsed
            ),
            "workers": args.workers,
        },
        "precision": {
            "method": "two-sided 95% Wilson interval",
            "planned_full_replicates": 500,
            "approximate_half_width_at_probability_0_05_for_500": (
                wilson_interval(25, 500)[1] - wilson_interval(25, 500)[0]
            )
            / 2,
        },
        "environment": environment_metadata(),
        "interpretive_boundary": (
            "This calibrates one frozen real cohort, group balance, collection, "
            "and production CAMERA contract. It is not universal error-control "
            "evidence for every cohort or grouping design."
        ),
    }
    write_json(phase_dir / "summary.json", summary)
    input_paths = {
        **source_paths,
        "frozen_outer_permutations_source": frozen_source,
        "gene_set_collection": collection_path,
        "gene_set_collection_manifest": collection_manifest,
        "production_gsea_core": ROOT / "backend" / "app" / "gsea.py",
        "production_camera_engine": camera_r_path,
        "pipeline_versions": ROOT / "backend" / "app" / "pipeline_versions.py",
        "calibration_driver": Path(__file__).resolve(),
    }
    write_manifest(phase_dir, input_paths=input_paths)
    verify_phase(phase_dir)
    print(f"Completed CAMERA {args.phase} calibration in {phase_dir}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
