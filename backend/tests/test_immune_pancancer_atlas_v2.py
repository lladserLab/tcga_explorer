from __future__ import annotations

import sys
from pathlib import Path

import pytest


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from immune_pancancer_atlas_v2 import (  # noqa: E402
    apply_family_statistics,
    build_selected_sensitivity,
    clinical_comparison_label,
)
from immune_pancancer_screen import top_gene_summary  # noqa: E402


def model_row(
    gene: str,
    cohort: str,
    model: str,
    *,
    p_value: float | None,
    hazard_ratio: float | None,
    status: str = "completed",
    reason: str | None = None,
) -> dict:
    log_hr = None
    if hazard_ratio is not None:
        import math

        log_hr = math.log(hazard_ratio)
    return {
        "gene_symbol": gene,
        "cohort": cohort,
        "model": model,
        "status": status,
        "reason": reason,
        "n_patients": 100,
        "n_events": 30,
        "log_hr": log_hr,
        "standard_error": 0.1 if log_hr is not None else None,
        "hazard_ratio": hazard_ratio,
        "hr_conf_low": (
            hazard_ratio * 0.8 if hazard_ratio is not None else None
        ),
        "hr_conf_high": (
            hazard_ratio * 1.2 if hazard_ratio is not None else None
        ),
        "p_value": p_value,
        "ph_p_value": 0.5,
        "ph_global_p_value": 0.4,
    }


def test_atlas_fdr_is_calculated_separately_by_model_family() -> None:
    rows = [
        model_row("A", "TCGA-X", "primary", p_value=0.01, hazard_ratio=1.2),
        model_row("B", "TCGA-X", "primary", p_value=0.04, hazard_ratio=0.8),
        model_row(
            "A",
            "TCGA-X",
            "stage_adjusted",
            p_value=0.50,
            hazard_ratio=1.1,
        ),
        model_row(
            "B",
            "TCGA-X",
            "stage_adjusted",
            p_value=0.60,
            hazard_ratio=0.9,
        ),
    ]

    apply_family_statistics(rows, 0.10)

    primary = [row for row in rows if row["model"] == "primary"]
    stage = [row for row in rows if row["model"] == "stage_adjusted"]
    assert [row["global_fdr"] for row in primary] == pytest.approx([0.02, 0.04])
    assert [row["global_fdr"] for row in stage] == pytest.approx([0.6, 0.6])
    assert [row["significant"] for row in primary] == [True, True]
    assert [row["significant"] for row in stage] == [False, False]


def test_selected_atlas_sensitivity_uses_availability_not_p_value() -> None:
    rows = [
        model_row("A", "TCGA-X", "primary", p_value=0.001, hazard_ratio=1.5),
        model_row(
            "A",
            "TCGA-X",
            "stage_grade_adjusted",
            p_value=0.04,
            hazard_ratio=1.3,
        ),
        model_row(
            "A",
            "TCGA-X",
            "stage_adjusted",
            p_value=0.00001,
            hazard_ratio=1.8,
        ),
        model_row(
            "A",
            "TCGA-X",
            "grade_adjusted",
            p_value=0.02,
            hazard_ratio=1.2,
        ),
        model_row("B", "TCGA-Y", "primary", p_value=0.01, hazard_ratio=0.7),
        model_row(
            "B",
            "TCGA-Y",
            "stage_grade_adjusted",
            p_value=None,
            hazard_ratio=None,
            status="skipped",
            reason="Grade unavailable.",
        ),
        model_row(
            "B",
            "TCGA-Y",
            "stage_adjusted",
            p_value=0.03,
            hazard_ratio=0.8,
        ),
        model_row(
            "B",
            "TCGA-Y",
            "grade_adjusted",
            p_value=None,
            hazard_ratio=None,
            status="skipped",
            reason="Grade unavailable.",
        ),
    ]
    apply_family_statistics(rows, 0.10)
    panel_rows = [
        {"gene_symbol": "A", "source_list_count": 1, "term_names": "Term A"},
        {"gene_symbol": "B", "source_list_count": 1, "term_names": "Term B"},
    ]
    primary_gene_summary = [
        {"gene_symbol": "A", "global_fdr_hits": 1},
        {"gene_symbol": "B", "global_fdr_hits": 1},
    ]

    selected, sensitivity = build_selected_sensitivity(
        model_rows=rows,
        primary_gene_summary=primary_gene_summary,
        panel_rows=panel_rows,
        fdr_threshold=0.10,
    )

    assert selected[0]["selected_model"] == "stage_grade_adjusted"
    assert selected[1]["selected_model"] == "stage_adjusted"
    assert sensitivity["summary"]["selected_model_counts"] == {
        "stage_grade_adjusted": 1,
        "stage_adjusted": 1,
    }
    assert sensitivity["mixed_selected_meta_analysis"]["available"] is False


def test_atlas_comparison_keeps_reversal_and_not_evaluable_distinct() -> None:
    reversed_row = {
        "adjusted_status": "completed",
        "primary_direction": "harmful",
        "adjusted_direction": "protective",
        "primary_significant": True,
        "adjusted_significant": False,
    }
    unavailable_row = {
        "adjusted_status": "not_evaluable",
        "primary_direction": "harmful",
        "adjusted_direction": "not_evaluable",
        "primary_significant": True,
        "adjusted_significant": False,
    }

    assert clinical_comparison_label(reversed_row) == "reversed"
    assert clinical_comparison_label(unavailable_row) == "not_evaluable"


def test_term_best_gene_ties_are_deterministic() -> None:
    rows = [
        {"gene_symbol": "ZETA", "meta_fdr": 0.04, "meta_p_value": 0.02},
        {"gene_symbol": "ALPHA", "meta_fdr": 0.04, "meta_p_value": 0.01},
        {"gene_symbol": "BETA", "meta_fdr": 0.04, "meta_p_value": 0.01},
    ]

    assert top_gene_summary(rows)["gene_symbol"] == "ALPHA"
    assert top_gene_summary(list(reversed(rows)))["gene_symbol"] == "ALPHA"
