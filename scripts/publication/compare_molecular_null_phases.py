#!/usr/bin/env python3
"""Verify frozen-label identity and compare 250 vs 1,000 GSEA permutations."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import statistics
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ROOT = (
    ROOT
    / "docs"
    / "publication"
    / "benchmark"
    / "major_revision_2026-08-26"
    / "expression_gsea_null_calibration"
)
Q_THRESHOLDS = (0.05, 0.10, 0.25)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def truth(value: Any) -> bool:
    return str(value).strip().casefold() in {"true", "1", "yes"}


def suffix(threshold: float) -> str:
    return f"{threshold:.2f}".replace(".", "_")


def numeric_summary(values: Sequence[float]) -> dict[str, float]:
    ordered = sorted(float(value) for value in values)
    return {
        "mean": statistics.fmean(ordered),
        "median": statistics.median(ordered),
        "minimum": ordered[0],
        "maximum": ordered[-1],
    }


def pearson(x: Sequence[float], y: Sequence[float]) -> float | None:
    if len(x) != len(y) or len(x) < 2:
        return None
    mean_x = statistics.fmean(x)
    mean_y = statistics.fmean(y)
    numerator = sum((a - mean_x) * (b - mean_y) for a, b in zip(x, y, strict=True))
    denominator = math.sqrt(
        sum((a - mean_x) ** 2 for a in x) * sum((b - mean_y) ** 2 for b in y)
    )
    return numerator / denominator if denominator > 0 else None


def compare(root: Path) -> dict[str, Any]:
    full_dir = root / "full"
    sensitivity_dir = root / "default_sensitivity"
    full_permutations = read_csv(full_dir / "outer_label_permutations.csv")
    sensitivity_permutations = read_csv(
        sensitivity_dir / "outer_label_permutations.csv"
    )
    if full_permutations[: len(sensitivity_permutations)] != sensitivity_permutations:
        raise RuntimeError(
            "The sensitivity labels are not the exact ordered prefix of the full run."
        )

    full_expression = read_csv(full_dir / "expression_replicates.csv")
    sensitivity_expression = read_csv(
        sensitivity_dir / "expression_replicates.csv"
    )
    if full_expression[: len(sensitivity_expression)] != sensitivity_expression:
        raise RuntimeError(
            "Expression results changed despite identical labels and method."
        )

    full_gsea = {
        int(row["replicate"]): row
        for row in read_csv(full_dir / "gsea_replicates.csv")
    }
    sensitivity_gsea = read_csv(sensitivity_dir / "gsea_replicates.csv")
    paired = [(full_gsea[int(row["replicate"])], row) for row in sensitivity_gsea]
    if len(paired) != len(sensitivity_permutations):
        raise RuntimeError("The paired GSEA result count is inconsistent.")
    thresholds: dict[str, Any] = {}
    for threshold in Q_THRESHOLDS:
        field = f"any_q_le_{suffix(threshold)}"
        pairs = [(truth(full[field]), truth(sensitive[field])) for full, sensitive in paired]
        both = sum(a and b for a, b in pairs)
        only_250 = sum(a and not b for a, b in pairs)
        only_1000 = sum(not a and b for a, b in pairs)
        neither = sum(not a and not b for a, b in pairs)
        thresholds[f"q_le_{threshold:.2f}"] = {
            "both_reject": both,
            "only_250_internal_permutations_reject": only_250,
            "only_1000_internal_permutations_reject": only_1000,
            "neither_reject": neither,
            "paired_agreement": (both + neither) / len(pairs),
        }
    full_min_q = [float(full["min_q"]) for full, _ in paired]
    sensitivity_min_q = [float(sensitive["min_q"]) for _, sensitive in paired]
    differences = [
        sensitive - full
        for full, sensitive in zip(full_min_q, sensitivity_min_q, strict=True)
    ]
    return {
        "schema_version": "trace-molecular-null-cross-phase-comparison-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "paired_outer_replicates": len(paired),
        "identity_checks": {
            "sensitivity_labels_equal_full_ordered_prefix": True,
            "expression_results_equal_full_ordered_prefix": True,
            "matrix_and_pathway_family": "verified by phase input manifests",
        },
        "comparison": {
            "full_internal_gene_set_permutations": 250,
            "sensitivity_internal_gene_set_permutations": 1000,
            "threshold_event_agreement": thresholds,
            "minimum_q_pearson_correlation": pearson(full_min_q, sensitivity_min_q),
            "minimum_q_sensitivity_minus_full": numeric_summary(differences),
        },
        "interpretation": (
            "This paired comparison isolates the numerical effect of increasing "
            "the internal gene-set permutations because outer sample labels and "
            "Expression Comparison results are identical. It does not validate "
            "the legacy gene-set-permutation null against gene correlation."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    output = (args.output or root / "cross_phase_comparison.json").resolve()
    payload = compare(root)
    output.write_text(
        json.dumps(payload, ensure_ascii=False, allow_nan=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
