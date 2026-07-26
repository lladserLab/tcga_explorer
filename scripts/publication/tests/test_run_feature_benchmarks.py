from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "run_feature_benchmarks.py"
SPEC = importlib.util.spec_from_file_location("run_feature_benchmarks", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_latex_escape_preserves_inequality_symbols_in_text_mode() -> None:
    assert MODULE.latex_escape("FDR<0.10 and HR>1") == (
        "FDR\\textless{}0.10 and HR\\textgreater{}1"
    )


def test_feature_payloads_prespecify_age_adjustment() -> None:
    assert MODULE.signature_payload()["adjustment_covariates"] == ["age_at_index"]
    assert MODULE.combined_payload()["adjustment_covariates"] == ["age_at_index"]
    assert MODULE.diagnostic_signature_payload()["adjustment_covariates"] == [
        "age_at_index"
    ]
    assert MODULE.diagnostic_combined_payload()["adjustment_covariates"] == [
        "age_at_index"
    ]


def test_requested_interaction_adjustment_is_not_replaced_by_fixed_model() -> None:
    models = [
        {
            "model": "signature_interaction_user_adjusted",
            "status": "skipped",
            "reason": "Too few complete patients.",
        },
        {
            "model": "signature_interaction_stage_adjusted",
            "status": "completed",
        },
    ]

    assert MODULE.downstream_adjusted_interaction_model(models) == {}
    assert (
        MODULE.downstream_adjusted_interaction_reporting_model(models)["model"]
        == "signature_interaction_user_adjusted"
    )
    assert MODULE.interaction_adjustment_status(models) == "Too few complete patients."


def test_model_diagnostics_preserve_completed_firth_after_standard_failure() -> None:
    fields = MODULE.model_diagnostic_fields(
        {
            "model": "signature_interaction_stage_adjusted",
            "status": "failed",
            "information_diagnostics": {
                "parameter_count": 4,
                "events_per_parameter": 4.5,
                "status": "severe",
            },
            "penalized_sensitivity": {
                "status": "completed",
                "hazard_ratio": 0.2,
                "hr_conf_low": 0.03,
                "hr_conf_high": 0.9,
                "p_value": 0.04,
                "ties": "breslow",
                "trigger_reasons": ["Standard Cox failed."],
            },
        }
    )

    assert fields["standard_cox_status"] == "failed"
    assert fields["events_per_parameter"] == 4.5
    assert fields["information_status"] == "severe"
    assert fields["firth_status"] == "completed"
    assert fields["firth_hr"] == 0.2
    assert fields["firth_ties"] == "breslow"


def test_pancancer_summary_reports_common_scale_hksj_and_prediction_interval() -> None:
    result = {
        "status": "completed",
        "scan_id": "pc-test",
        "endpoint": "OS",
        "results": [
            {
                "status": "completed",
                "n_patients": 100,
                "n_events": 30,
                "significant": True,
            },
            {
                "status": "completed",
                "n_patients": 120,
                "n_events": 40,
                "significant": False,
            },
        ],
        "summary": {"concordance_counts": {}},
        "meta_analysis": {
            "random_effect": {
                "hazard_ratio": 1.2,
                "hr_conf_low": 1.05,
                "hr_conf_high": 1.37,
                "p_value": 0.006,
            },
            "prediction_interval": {
                "hazard_ratio_low": 0.64,
                "hazard_ratio_high": 2.24,
            },
            "heterogeneity": {"i_squared": 86.1},
        },
        "clinical_sensitivity": {
            "summary": {
                "total_cohorts": 2,
                "evaluable": 0,
                "fdr_significant": 0,
                "direction_reversed": 0,
            },
            "meta_analysis_by_model": {},
        },
        "audit": {},
    }

    summary = MODULE.summarize_pancancer(
        "pancancer",
        "Test",
        result,
        marker="BIRC5",
        interpretation="Test interpretation.",
    )

    assert summary["primary_statistic"] == (
        "common-scale REML/HKSJ meta-analysis"
    )
    assert "common-scale REML HR 1.20 (1.05-1.37)" in summary["effect_summary"]
    assert "95% PI 0.64-2.24" in summary["effect_summary"]
    assert "95% prediction interval 0.64-2.24" in summary["limitation"]
