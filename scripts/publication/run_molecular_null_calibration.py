#!/usr/bin/env python3
"""Calibrate Expression Comparison and GSEA under a sample-label null.

The outer randomization permutes artificial binary labels over one frozen,
patient-level bulk-RNA matrix.  It therefore preserves sample values, missing
values and the complete gene--gene correlation structure.  Expression
Comparison is evaluated with the same R tests and BH families as production.
GSEA imports and executes TRACE's production ranking and enrichment functions;
its internal gene-set permutations remain distinct from the outer label null.

This script is publication infrastructure.  It does not alter a production
endpoint or its statistical implementation.
"""

from __future__ import annotations

import argparse
from array import array
import csv
from datetime import datetime, timezone
from hashlib import sha256
import json
import math
import multiprocessing
import os
from pathlib import Path
import platform
import random
import statistics
import subprocess
import sys
import time
from typing import Any, Iterable, Sequence


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.gsea import (  # noqa: E402
    ExpressionMatrix,
    MatrixGene,
    rank_expression_matrix,
    read_gmt,
    run_preranked_gsea,
)
from app.pipeline_versions import (  # noqa: E402
    EXPRESSION_COMPARISON_PIPELINE_VERSION,
    GSEA_PIPELINE_VERSION,
)


SCHEMA_VERSION = "trace-molecular-null-calibration-v1"
DEFAULT_OUTPUT = (
    ROOT
    / "docs"
    / "publication"
    / "benchmark"
    / "major_revision_2026-08-26"
    / "expression_gsea_null_calibration"
)
DEFAULT_RELEASE = (
    ROOT
    / "external_repository"
    / "studies"
    / "cbioportal-luad-cas-2020"
    / "releases"
    / "cbioportal-luad-cas-2020-86690e1ed975-a398e2f4773e"
)
DEFAULT_LAYER = "log2_fpkm"
DEFAULT_COLLECTION = ROOT / "backend" / "gene_sets" / "go-bp-20260619.gmt"
DEFAULT_COLLECTION_MANIFEST = ROOT / "backend" / "gene_sets" / "collections.json"
DEFAULT_EXPRESSION_R = (
    ROOT / "scripts" / "publication" / "expression_comparison_null_calibration.R"
)
Q_THRESHOLDS = (0.05, 0.10, 0.25)
PANEL_SIZE = 25
MASTER_SEED = 20260826
GSEA_SEED = 17291
GSEA_MIN_SIZE = 15
GSEA_MAX_SIZE = 500
MINIMUM_EXPRESSION_GROUP_N = 5


_GSEA_CONTEXT: dict[str, Any] = {}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def write_csv(
    path: Path,
    rows: Sequence[dict[str, Any]],
    fields: Sequence[str] | None = None,
) -> None:
    if fields is None:
        if not rows:
            raise ValueError(f"Cannot infer fields for empty CSV: {path}.")
        fields = list(rows[0])
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fields), extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def workspace_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path.resolve())


def wilson_interval(
    successes: int,
    total: int,
    *,
    z: float = 1.959963984540054,
) -> tuple[float | None, float | None]:
    """Return a two-sided 95% Wilson interval for a binomial proportion."""

    if total < 1:
        return None, None
    if successes < 0 or successes > total:
        raise ValueError("successes must lie between zero and total.")
    estimate = successes / total
    denominator = 1 + z * z / total
    center = (estimate + z * z / (2 * total)) / denominator
    radius = (
        z
        * math.sqrt(
            estimate * (1 - estimate) / total
            + z * z / (4 * total * total)
        )
        / denominator
    )
    return max(0.0, center - radius), min(1.0, center + radius)


def build_permutations(
    *,
    sample_count: int,
    group_b_size: int,
    replicates: int,
    seed: int,
) -> list[dict[str, Any]]:
    """Freeze deterministic outer-label permutations.

    Zero-based positions are stored explicitly so reproducing the calibration
    never depends on the random-number implementation of a future runtime.
    """

    if not 0 < group_b_size < sample_count:
        raise ValueError("Both permuted groups must contain at least one sample.")
    if replicates < 1:
        raise ValueError("replicates must be positive.")
    rng = random.Random(seed)
    rows: list[dict[str, Any]] = []
    for replicate in range(1, replicates + 1):
        positions = sorted(rng.sample(range(sample_count), group_b_size))
        rows.append(
            {
                "replicate": replicate,
                "group_a_n": sample_count - group_b_size,
                "group_b_n": group_b_size,
                "group_b_zero_based_positions": ";".join(
                    str(position) for position in positions
                ),
            }
        )
    return rows


def parse_positions(value: str) -> tuple[int, ...]:
    if not value:
        return ()
    return tuple(int(item) for item in value.split(";") if item != "")


def load_expression_matrix(
    release_dir: Path,
    layer_id: str,
) -> tuple[ExpressionMatrix, dict[str, Any], dict[str, Path]]:
    derived = release_dir / "derived"
    metadata_path = derived / f"{layer_id}.metadata.json"
    genes_path = derived / "genes.tsv"
    manifest_path = release_dir / "manifest.json"
    if not metadata_path.is_file() or not genes_path.is_file():
        raise FileNotFoundError(
            f"Expression layer {layer_id} is incomplete under {release_dir}."
        )
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    with genes_path.open(newline="", encoding="utf-8") as handle:
        genes = [
            MatrixGene(
                symbol=str(row["gene_symbol"]).strip().upper(),
                row_number=int(row["row_number"]),
            )
            for row in csv.DictReader(handle, delimiter="\t")
        ]
    genes.sort(key=lambda row: (row.row_number, row.symbol))
    expected_rows = list(range(len(genes)))
    observed_rows = [row.row_number for row in genes]
    if observed_rows != expected_rows:
        raise ValueError("The expression index is not a contiguous row-major index.")
    matrix_file = None
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for layer in manifest.get("expression_layers") or []:
            if layer.get("layer_id") == layer_id:
                matrix_file = layer.get("matrix_file")
                break
    matrix_path = release_dir / str(matrix_file) if matrix_file else derived / f"{layer_id}.float32le.bin"
    if not matrix_path.is_file():
        raise FileNotFoundError(f"Expression matrix is unavailable: {matrix_path}.")
    sample_ids = [str(item) for item in metadata.get("sample_ids") or []]
    if len(sample_ids) != int(metadata.get("sample_count") or -1):
        raise ValueError("Expression metadata sample count is inconsistent.")
    if len(genes) != int(metadata.get("gene_count") or -1):
        raise ValueError("Expression metadata gene count is inconsistent.")
    expected_bytes = len(sample_ids) * len(genes) * array("f").itemsize
    if matrix_path.stat().st_size != expected_bytes:
        raise ValueError("Expression matrix byte count is inconsistent.")
    matrix = ExpressionMatrix(
        path=matrix_path,
        sample_ids=sample_ids,
        genes=genes,
        dtype="float32",
        byte_order="little",
        expression_scale=layer_id,
        expression_scale_label=str(metadata.get("analysis_unit") or layer_id),
        source_sha256=sha256_file(matrix_path),
    )
    return matrix, metadata, {
        "release_manifest": manifest_path,
        "matrix_metadata": metadata_path,
        "gene_index": genes_path,
        "matrix": matrix_path,
    }


def read_matrix_row(matrix: ExpressionMatrix, row_number: int) -> list[float]:
    sample_count = len(matrix.sample_ids)
    values = array("f")
    with matrix.path.open("rb") as handle:
        handle.seek(row_number * sample_count * values.itemsize)
        values.fromfile(handle, sample_count)
    if len(values) != sample_count:
        raise ValueError(f"Expression row {row_number} is truncated.")
    if matrix.byte_order == "little" and sys.byteorder != "little":
        values.byteswap()
    return [float(value) for value in values]


def select_expression_panel(
    matrix: ExpressionMatrix,
    *,
    panel_size: int = PANEL_SIZE,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Select a label-independent, high-variance 25-gene stress panel."""

    candidates: list[dict[str, Any]] = []
    values_by_row: dict[int, list[float]] = {}
    for gene in matrix.genes:
        values = read_matrix_row(matrix, gene.row_number)
        if not all(math.isfinite(value) for value in values):
            continue
        variance = statistics.variance(values)
        if not math.isfinite(variance) or variance <= 0:
            continue
        candidates.append(
            {
                "gene_symbol": gene.symbol,
                "row_number": gene.row_number,
                "variance_all_samples": variance,
            }
        )
        values_by_row[gene.row_number] = values
    candidates.sort(
        key=lambda row: (-float(row["variance_all_samples"]), row["gene_symbol"])
    )
    selected = candidates[:panel_size]
    if len(selected) != panel_size:
        raise ValueError(
            f"Only {len(selected)} complete, variable genes are available; "
            f"{panel_size} are required."
        )
    value_rows: list[dict[str, Any]] = []
    for gene in selected:
        values = values_by_row[int(gene["row_number"])]
        for sample_index, (sample_id, value) in enumerate(
            zip(matrix.sample_ids, values, strict=True)
        ):
            value_rows.append(
                {
                    "gene_symbol": gene["gene_symbol"],
                    "row_number": gene["row_number"],
                    "sample_index_zero_based": sample_index,
                    "sample_id": sample_id,
                    "expression_value": value,
                }
            )
    return selected, value_rows


def q_suffix(threshold: float) -> str:
    return f"{threshold:.2f}".replace(".", "_")


def gsea_metrics_from_assignments(
    matrix: ExpressionMatrix,
    pathways: list[dict[str, Any]],
    assignments: dict[str, str],
    *,
    permutations: int,
    seed: int,
    min_size: int = GSEA_MIN_SIZE,
    max_size: int = GSEA_MAX_SIZE,
) -> dict[str, Any]:
    """Run the exact production ranking and GSEA functions and retain metrics."""

    rank_started = time.perf_counter()
    ranked, ranking_metadata = rank_expression_matrix(
        matrix,
        assignments,
        ranking_metric="welch_t",
    )
    rank_seconds = time.perf_counter() - rank_started
    gsea_started = time.perf_counter()
    results, details = run_preranked_gsea(
        ranked,
        pathways,
        min_size=min_size,
        max_size=max_size,
        permutations=permutations,
        seed=seed,
    )
    gsea_seconds = time.perf_counter() - gsea_started
    q_values = [float(row["fdr"]) for row in results]
    minimum_index = min(range(len(results)), key=lambda index: q_values[index])
    output: dict[str, Any] = {
        "genes_ranked": ranking_metadata["genes_ranked"],
        "genes_excluded": ranking_metadata["genes_excluded"],
        "pathways_tested": details["pathways_tested"],
        "unique_overlap_sizes": details["unique_overlap_sizes"],
        "min_q": q_values[minimum_index],
        "min_q_pathway": results[minimum_index]["pathway"],
        "min_q_nominal_p": results[minimum_index]["p_value"],
        "min_q_nes": results[minimum_index]["nes"],
        "ranking_seconds": rank_seconds,
        "gsea_seconds": gsea_seconds,
    }
    for threshold in Q_THRESHOLDS:
        suffix = q_suffix(threshold)
        count = sum(value <= threshold for value in q_values)
        output[f"rejections_q_le_{suffix}"] = count
        output[f"any_q_le_{suffix}"] = count > 0
    return output


def _initialize_gsea_worker(
    release_dir: str,
    layer_id: str,
    collection_path: str,
    permutations: int,
    gsea_seed: int,
) -> None:
    matrix, _, _ = load_expression_matrix(Path(release_dir), layer_id)
    _GSEA_CONTEXT.clear()
    _GSEA_CONTEXT.update(
        {
            "matrix": matrix,
            "pathways": read_gmt(Path(collection_path)),
            "permutations": permutations,
            "gsea_seed": gsea_seed,
        }
    )


def _gsea_worker(task: tuple[int, str]) -> dict[str, Any]:
    replicate, encoded_positions = task
    matrix: ExpressionMatrix = _GSEA_CONTEXT["matrix"]
    group_b = set(parse_positions(encoded_positions))
    assignments = {
        sample_id: ("b" if index in group_b else "a")
        for index, sample_id in enumerate(matrix.sample_ids)
    }
    metrics = gsea_metrics_from_assignments(
        matrix,
        _GSEA_CONTEXT["pathways"],
        assignments,
        permutations=int(_GSEA_CONTEXT["permutations"]),
        seed=int(_GSEA_CONTEXT["gsea_seed"]),
    )
    return {
        "replicate": replicate,
        "group_a_n": len(matrix.sample_ids) - len(group_b),
        "group_b_n": len(group_b),
        **metrics,
    }


def run_gsea_calibration(
    permutation_rows: Sequence[dict[str, Any]],
    *,
    release_dir: Path,
    layer_id: str,
    collection_path: Path,
    permutations: int,
    gsea_seed: int,
    workers: int,
) -> tuple[list[dict[str, Any]], float]:
    tasks = [
        (
            int(row["replicate"]),
            str(row["group_b_zero_based_positions"]),
        )
        for row in permutation_rows
    ]
    started = time.perf_counter()
    results: list[dict[str, Any]] = []
    progress_every = max(1, min(10, len(tasks) // 10 or 1))
    if workers == 1:
        _initialize_gsea_worker(
            str(release_dir),
            layer_id,
            str(collection_path),
            permutations,
            gsea_seed,
        )
        iterator: Iterable[dict[str, Any]] = map(_gsea_worker, tasks)
        for index, result in enumerate(iterator, start=1):
            results.append(result)
            if index % progress_every == 0 or index == len(tasks):
                print(f"GSEA outer permutations: {index}/{len(tasks)}", flush=True)
    else:
        methods = multiprocessing.get_all_start_methods()
        context = multiprocessing.get_context("fork" if "fork" in methods else "spawn")
        with context.Pool(
            processes=workers,
            initializer=_initialize_gsea_worker,
            initargs=(
                str(release_dir),
                layer_id,
                str(collection_path),
                permutations,
                gsea_seed,
            ),
            maxtasksperchild=25,
        ) as pool:
            for index, result in enumerate(
                pool.imap_unordered(_gsea_worker, tasks),
                start=1,
            ):
                results.append(result)
                if index % progress_every == 0 or index == len(tasks):
                    print(f"GSEA outer permutations: {index}/{len(tasks)}", flush=True)
    results.sort(key=lambda row: int(row["replicate"]))
    return results, time.perf_counter() - started


def run_expression_calibration(
    *,
    phase_dir: Path,
    panel_values_path: Path,
    permutation_path: Path,
    r_script: Path,
) -> tuple[Path, Path, Path, float]:
    replicate_path = phase_dir / "expression_replicates.csv"
    gene_path = phase_dir / "expression_gene_statistics.csv"
    engine_path = phase_dir / "expression_engine.json"
    config_path = phase_dir / "expression_engine_input.json"
    config = {
        "schema_version": "trace-expression-null-calibration-engine-input-v1",
        "panel_values_csv": str(panel_values_path.resolve()),
        "permutations_csv": str(permutation_path.resolve()),
        "replicate_output_csv": str(replicate_path.resolve()),
        "gene_output_csv": str(gene_path.resolve()),
        "engine_output_json": str(engine_path.resolve()),
        "minimum_finite_samples_per_group": MINIMUM_EXPRESSION_GROUP_N,
        "q_thresholds": list(Q_THRESHOLDS),
        "contrast": "group_b_minus_group_a",
        "production_pipeline_version": EXPRESSION_COMPARISON_PIPELINE_VERSION,
        "production_reference_script": str(
            (ROOT / "backend" / "scripts" / "expression_comparison.R").resolve()
        ),
    }
    write_json(config_path, config)
    started = time.perf_counter()
    completed = subprocess.run(
        ["Rscript", str(r_script.resolve()), str(config_path.resolve())],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    elapsed = time.perf_counter() - started
    (phase_dir / "expression_engine.stdout.txt").write_text(
        completed.stdout,
        encoding="utf-8",
    )
    (phase_dir / "expression_engine.stderr.txt").write_text(
        completed.stderr,
        encoding="utf-8",
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "Expression null-calibration engine failed: "
            + (completed.stderr or completed.stdout or "unknown error")
        )
    for path in (replicate_path, gene_path, engine_path):
        if not path.is_file():
            raise RuntimeError(f"Expression engine omitted {path.name}.")
    return replicate_path, gene_path, engine_path, elapsed


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


def _numeric_distribution(values: Sequence[float]) -> dict[str, float | int | None]:
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


def summarize_threshold(
    rows: Sequence[dict[str, Any]],
    *,
    any_field: str,
    count_field: str,
) -> dict[str, Any]:
    evaluable = [row for row in rows if str(row.get(any_field, "")) != ""]
    successes = sum(_truth(row[any_field]) for row in evaluable)
    low, high = wilson_interval(successes, len(evaluable))
    counts = [
        float(row[count_field])
        for row in evaluable
        if _finite(row.get(count_field)) is not None
    ]
    return {
        "replicates": len(evaluable),
        "replicates_with_any_rejection": successes,
        "probability_any_rejection": (
            successes / len(evaluable) if evaluable else None
        ),
        "wilson_95_confidence_interval": [low, high],
        "rejections_per_replicate": _numeric_distribution(counts),
    }


def summarize_expression(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    output: dict[str, Any] = {
        "interpretation": (
            "Under the global label null, any BH rejection equals a false "
            "discovery event. Welch and Mann-Whitney are separate production "
            "families; their union is descriptive and is not a production "
            "decision rule."
        ),
        "families": {},
    }
    for family in ("welch", "mann_whitney", "either_family"):
        family_output: dict[str, Any] = {}
        for threshold in Q_THRESHOLDS:
            suffix = q_suffix(threshold)
            family_output[f"q_le_{threshold:.2f}"] = summarize_threshold(
                rows,
                any_field=f"{family}_any_q_le_{suffix}",
                count_field=f"{family}_rejections_q_le_{suffix}",
            )
        output["families"][family] = family_output
    output["minimum_q"] = {
        "welch": _numeric_distribution(
            [value for row in rows if (value := _finite(row.get("welch_min_q"))) is not None]
        ),
        "mann_whitney": _numeric_distribution(
            [
                value
                for row in rows
                if (value := _finite(row.get("mann_whitney_min_q"))) is not None
            ]
        ),
    }
    return output


def summarize_gsea(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    thresholds: dict[str, Any] = {}
    for threshold in Q_THRESHOLDS:
        suffix = q_suffix(threshold)
        thresholds[f"q_le_{threshold:.2f}"] = summarize_threshold(
            rows,
            any_field=f"any_q_le_{suffix}",
            count_field=f"rejections_q_le_{suffix}",
        )
    return {
        "interpretation": (
            "The outer null permutes sample labels and preserves the observed "
            "gene--gene correlation. Inside each outer replicate, TRACE's "
            "production GSEA instead constructs a gene-set-permutation null "
            "conditional on pathway overlap size. These are different null "
            "operations; the outer calibration assesses the complete fixed-seed "
            "algorithm under randomized labels."
        ),
        "thresholds": thresholds,
        "minimum_q": _numeric_distribution(
            [value for row in rows if (value := _finite(row.get("min_q"))) is not None]
        ),
        "genes_ranked": _numeric_distribution(
            [float(row["genes_ranked"]) for row in rows]
        ),
        "pathways_tested": _numeric_distribution(
            [float(row["pathways_tested"]) for row in rows]
        ),
    }


def environment_metadata() -> dict[str, Any]:
    def command_output(command: Sequence[str]) -> str | None:
        try:
            completed = subprocess.run(
                list(command),
                check=False,
                capture_output=True,
                text=True,
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
        "jsonlite": command_output(
            [
                "Rscript",
                "-e",
                'cat(as.character(utils::packageVersion("jsonlite")))',
            ]
        ),
        "container_image": os.environ.get("TRACE_CALIBRATION_CONTAINER_IMAGE"),
        "git_commit": command_output(["git", "rev-parse", "HEAD"]),
    }


def input_manifest(
    *,
    source_paths: dict[str, Path],
    collection_path: Path,
    collection_manifest: Path,
) -> list[dict[str, Any]]:
    paths = {
        **source_paths,
        "gene_set_collection": collection_path,
        "gene_set_collection_manifest": collection_manifest,
        "production_gsea_core": ROOT / "backend" / "app" / "gsea.py",
        "production_expression_engine": (
            ROOT / "backend" / "scripts" / "expression_comparison.R"
        ),
        "pipeline_versions": ROOT / "backend" / "app" / "pipeline_versions.py",
        "calibration_driver": Path(__file__).resolve(),
        "calibration_expression_engine": DEFAULT_EXPRESSION_R,
    }
    rows = []
    for role, path in sorted(paths.items()):
        if not path.is_file():
            raise FileNotFoundError(f"Manifest input is unavailable: {path}.")
        rows.append(
            {
                "role": role,
                "path": workspace_path(path),
                "sha256": sha256_file(path),
                "bytes": path.stat().st_size,
            }
        )
    return rows


def write_phase_manifest(
    phase_dir: Path,
    *,
    inputs: Sequence[dict[str, Any]],
    summary: dict[str, Any],
) -> None:
    excluded = {"manifest.json", "SHA256SUMS"}
    files = [
        path
        for path in sorted(phase_dir.iterdir())
        if path.is_file() and path.name not in excluded
    ]
    outputs = [
        {
            "file": path.name,
            "sha256": sha256_file(path),
            "bytes": path.stat().st_size,
        }
        for path in files
    ]
    manifest = {
        "schema_version": "trace-molecular-null-calibration-manifest-v1",
        "generated_at": utc_now(),
        "phase": summary["phase"],
        "inputs": list(inputs),
        "outputs": outputs,
        "summary_sha256": sha256_file(phase_dir / "summary.json"),
    }
    write_json(phase_dir / "manifest.json", manifest)
    checksum_files = files + [phase_dir / "manifest.json"]
    (phase_dir / "SHA256SUMS").write_text(
        "".join(f"{sha256_file(path)}  {path.name}\n" for path in checksum_files),
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
    if sha256_file(phase_dir / "summary.json") != manifest.get("summary_sha256"):
        raise RuntimeError("Summary checksum mismatch.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Calibrate TRACE Expression Comparison and GSEA by permuting "
            "sample labels over a frozen real bulk-RNA matrix."
        )
    )
    parser.add_argument(
        "--phase",
        choices=("pilot", "full", "default_sensitivity"),
        required=True,
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--release-dir", type=Path, default=DEFAULT_RELEASE)
    parser.add_argument("--layer-id", default=DEFAULT_LAYER)
    parser.add_argument("--collection", type=Path, default=DEFAULT_COLLECTION)
    parser.add_argument(
        "--collection-manifest",
        type=Path,
        default=DEFAULT_COLLECTION_MANIFEST,
    )
    parser.add_argument("--expression-r-script", type=Path, default=DEFAULT_EXPRESSION_R)
    parser.add_argument("--replicates", type=int)
    parser.add_argument("--gsea-permutations", type=int, default=1000)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--master-seed", type=int, default=MASTER_SEED)
    parser.add_argument("--gsea-seed", type=int, default=GSEA_SEED)
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    if args.replicates is None:
        args.replicates = {
            "pilot": 5,
            "full": 500,
            "default_sensitivity": 100,
        }[args.phase]
    if args.replicates < 1:
        parser.error("--replicates must be positive.")
    if not 100 <= args.gsea_permutations <= 5000:
        parser.error("--gsea-permutations must match the production range 100--5000.")
    if args.workers < 1:
        parser.error("--workers must be positive.")
    return args


def main() -> int:
    args = parse_args()
    output_root = args.output_dir.resolve()
    phase_dir = output_root / args.phase
    if args.check_only:
        verify_phase(phase_dir)
        print(f"Verified {phase_dir}")
        return 0
    if phase_dir.exists() and any(phase_dir.iterdir()):
        raise RuntimeError(
            f"Refusing to overwrite a non-empty calibration phase: {phase_dir}."
        )
    phase_dir.mkdir(parents=True, exist_ok=True)

    release_dir = args.release_dir.resolve()
    collection_path = args.collection.resolve()
    collection_manifest = args.collection_manifest.resolve()
    r_script = args.expression_r_script.resolve()
    matrix, metadata, source_paths = load_expression_matrix(
        release_dir,
        args.layer_id,
    )
    pathways = read_gmt(collection_path)
    group_b_size = len(matrix.sample_ids) // 2
    permutation_rows = build_permutations(
        sample_count=len(matrix.sample_ids),
        group_b_size=group_b_size,
        replicates=args.replicates,
        seed=args.master_seed,
    )
    permutation_path = phase_dir / "outer_label_permutations.csv"
    write_csv(permutation_path, permutation_rows)

    panel, panel_values = select_expression_panel(matrix)
    panel_path = phase_dir / "expression_panel.csv"
    panel_values_path = phase_dir / "expression_panel_values.csv"
    write_csv(panel_path, panel)
    write_csv(panel_values_path, panel_values)

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
        "outer_label_null": {
            "operation": (
                "Assign the fixed number of artificial group-B labels to a "
                "simple random sample of patient-level matrix columns; all other "
                "columns form group A. Expression values and sample columns are "
                "never permuted independently by gene."
            ),
            "replicates": args.replicates,
            "master_seed": args.master_seed,
            "group_a_n": len(matrix.sample_ids) - group_b_size,
            "group_b_n": group_b_size,
            "preserves": [
                "group sizes",
                "sample-level transcriptomes",
                "gene--gene correlation",
                "marginal expression distributions",
                "missing-value pattern",
            ],
        },
        "expression_comparison": {
            "panel_size": len(panel),
            "panel_selection": (
                "Before labels are assigned, select the 25 genes with the "
                "largest sample variance among genes finite in every source "
                "sample; break variance ties by HGNC symbol."
            ),
            "statistics": [
                "two-sided Welch unequal-variance t test",
                "two-sided continuity-corrected asymptotic Mann--Whitney--Wilcoxon test",
            ],
            "multiplicity": (
                "BH separately across all evaluable panel genes for Welch and "
                "Mann--Whitney, matching the production family definitions."
            ),
            "production_pipeline_version": EXPRESSION_COMPARISON_PIPELINE_VERSION,
        },
        "gsea": {
            "ranking": "production Welch B-minus-A ranking over the full matrix",
            "collection": workspace_path(collection_path),
            "collection_sets": len(pathways),
            "min_gene_set_size": GSEA_MIN_SIZE,
            "max_gene_set_size": GSEA_MAX_SIZE,
            "gene_set_permutations_per_outer_replicate": args.gsea_permutations,
            "fixed_inner_seed": args.gsea_seed,
            "algorithm": (
                "Exact imported production rank_expression_matrix and "
                "run_preranked_gsea functions. The inner gene-set permutations "
                "are not the outer sample-label null."
            ),
            "production_pipeline_version": GSEA_PIPELINE_VERSION,
        },
        "reported_q_thresholds": list(Q_THRESHOLDS),
        "workers": args.workers,
    }
    write_json(phase_dir / "design.json", design)

    expression_replicate_path, _, _, expression_seconds = run_expression_calibration(
        phase_dir=phase_dir,
        panel_values_path=panel_values_path,
        permutation_path=permutation_path,
        r_script=r_script,
    )
    expression_rows = read_csv(expression_replicate_path)
    if len(expression_rows) != args.replicates:
        raise RuntimeError("Expression engine returned the wrong replicate count.")

    gsea_rows, gsea_seconds = run_gsea_calibration(
        permutation_rows,
        release_dir=release_dir,
        layer_id=args.layer_id,
        collection_path=collection_path,
        permutations=args.gsea_permutations,
        gsea_seed=args.gsea_seed,
        workers=args.workers,
    )
    if len(gsea_rows) != args.replicates:
        raise RuntimeError("GSEA engine returned the wrong replicate count.")
    gsea_path = phase_dir / "gsea_replicates.csv"
    write_csv(gsea_path, gsea_rows)

    projected_full_seconds = None
    if args.phase == "pilot":
        projected_full_seconds = gsea_seconds * 500 / args.replicates
    summary = {
        "schema_version": SCHEMA_VERSION,
        "phase": args.phase,
        "generated_at": utc_now(),
        "replicates": args.replicates,
        "expression_comparison": summarize_expression(expression_rows),
        "gsea": summarize_gsea(gsea_rows),
        "runtime": {
            "expression_wall_seconds": expression_seconds,
            "gsea_wall_seconds": gsea_seconds,
            "gsea_seconds_per_outer_replicate_wall": (
                gsea_seconds / args.replicates
            ),
            "projected_500_replicate_wall_seconds_at_same_worker_count": (
                projected_full_seconds
            ),
            "workers": args.workers,
        },
        "precision": {
            "method": "two-sided 95% Wilson interval",
            "planned_replicates_for_this_phase": args.replicates,
            "planned_full_replicates": 500,
            "approximate_half_width_at_probability_0_05_for_500": (
                (
                    wilson_interval(25, 500)[1]
                    - wilson_interval(25, 500)[0]
                )
                / 2
            ),
        },
        "environment": environment_metadata(),
        "interpretive_boundary": (
            "This is a calibration of fixed analysis settings under randomized "
            "sample labels in one real cohort. It is not a claim of universal "
            "error control across every cohort, group imbalance, gene panel or "
            "gene-set collection."
        ),
    }
    write_json(phase_dir / "summary.json", summary)
    inputs = input_manifest(
        source_paths=source_paths,
        collection_path=collection_path,
        collection_manifest=collection_manifest,
    )
    write_phase_manifest(phase_dir, inputs=inputs, summary=summary)
    verify_phase(phase_dir)
    print(f"Completed {args.phase} calibration in {phase_dir}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
