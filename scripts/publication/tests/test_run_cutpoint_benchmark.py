from __future__ import annotations

import importlib.util
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "run_cutpoint_benchmark.py"
SPEC = importlib.util.spec_from_file_location("run_cutpoint_benchmark", MODULE_PATH)
assert SPEC is not None
benchmark = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(benchmark)


def test_analysis_payload_preserves_exact_adjustment_covariates() -> None:
    payload = benchmark.analysis_payload(
        cohort="TCGA-LGG",
        gene="EMP3",
        endpoint="OS",
        method="median",
        custom_percentile=60,
        expression_scale="log2_tpm",
        time_unit="months",
        sample_types=[],
        adjustment_covariates=["age_at_index", "grade"],
    )

    assert payload["adjustment_covariates"] == ["age_at_index", "grade"]


def test_custom_benchmark_does_not_overwrite_canonical_kirc_table(
    tmp_path,
) -> None:
    resolved = benchmark.resolve_latex_table(
        requested=None,
        benchmark_id="lgg_emp3_os_cutpoints",
        output_dir=tmp_path,
    )

    assert resolved == tmp_path / "lgg_emp3_os_cutpoints.tex"
    assert resolved != benchmark.DEFAULT_LATEX_TABLE


def test_explicit_latex_table_path_is_preserved(tmp_path) -> None:
    requested = tmp_path / "paper-table.tex"

    assert (
        benchmark.resolve_latex_table(
            requested=requested,
            benchmark_id="lgg_emp3_os_cutpoints",
            output_dir=tmp_path,
        )
        == requested
    )


def test_summarize_batch_preserves_rmst_tau_sensitivity() -> None:
    rows = benchmark.summarize_batch(
        {
            "results": [
                {
                    "index": 0,
                    "status": "completed",
                    "result": {
                        "id": "analysis-1",
                        "cutpoint_method": "median",
                        "metrics": {
                            "cox_models": [
                                {
                                    "model": "univariable",
                                    "status": "completed",
                                    "hazard_ratio": 0.8,
                                    "hr_conf_low": 0.6,
                                    "hr_conf_high": 1.0,
                                    "p_value": 0.03,
                                }
                            ],
                            "rmst": {
                                "status": "completed",
                                "tau_days": 100.0,
                                "difference": {"estimate_days": 12.0, "p_value": 0.04},
                                "tau_sensitivity": [
                                    {
                                        "status": "completed",
                                        "tau_fraction": 0.75,
                                        "tau_days": 75.0,
                                        "estimate_days": 8.0,
                                        "p_value": 0.05,
                                    }
                                ],
                            },
                        },
                    },
                }
            ]
        }
    )

    assert rows[0]["rmst_tau_sensitivity"]
    lines = benchmark.rmst_tau_sensitivity_lines(rows)
    assert "| median | 0.75 | 75.0 | 8 | 0.050 |" in lines


def test_latex_profile_label_reports_diagnostic_notes() -> None:
    label = benchmark.latex_profile_label(
        {"profile_notes": "Marker-specific PH caution"}
    )

    assert label == "Marker-specific PH caution"


def test_csv_roundtrip_preserves_rmst_status_for_suite_reannotation(tmp_path) -> None:
    row = {
        "method": "median",
        "status": "completed",
        "rmst_status": "completed",
        "rmst_p_value": 0.01,
        "adjusted_ph_p_value": 0.7,
        "marker_ph_flagged": False,
        "profile_notes": "No model-diagnostic caution recorded",
    }

    path = tmp_path / "summary.csv"
    benchmark.write_csv(path, [row])

    assert "rmst_status" in path.read_text(encoding="utf-8").splitlines()[0]
    assert "completed" in path.read_text(encoding="utf-8").splitlines()[1]


def test_evidence_profile_keeps_marker_and_global_ph_separate() -> None:
    row = {
        "method": "median",
        "grouped_holm_p_value": 0.01,
        "univariable_p_value": 0.01,
        "adjusted_model": "stage_adjusted",
        "adjusted_p_value": 0.02,
        "adjusted_ph_p_value": 0.6,
        "adjusted_ph_global_p_value": 0.01,
        "rmst_status": "completed",
        "rmst_delta_days": 100,
        "rmst_p_value": 0.03,
        "univariable_hr": 1.5,
    }

    benchmark.annotate_evidence_profile(row)

    assert row["bh_below_alpha"] is True
    assert row["marker_ph_flagged"] is False
    assert row["global_ph_flagged"] is True
    assert "Global PH caution" in row["profile_notes"]
    assert "retained" not in row


def test_grouped_holm_uses_corrected_maxstat_input() -> None:
    rows = [
        {
            "method": "maxstat",
            "logrank_p_value": 0.001,
            "maxstat_corrected_p_status": "completed",
            "maxstat_corrected_p_value": 0.04,
        },
        {"method": "median", "logrank_p_value": 0.02},
        {"method": "upper_quartile", "logrank_p_value": 0.03},
        {"method": "upper_lower_quartile", "logrank_p_value": 0.2},
    ]

    benchmark.assign_grouped_family_p_values(rows)
    benchmark.apply_holm(
        rows,
        "grouped_family_p_value",
        "grouped_holm_p_value",
    )

    assert rows[0]["grouped_family_p_value"] == 0.04
    assert rows[0]["grouped_family_input"] == "maxstat_lau94_corrected"
    assert rows[0]["grouped_holm_p_value"] == 0.09
    assert rows[1]["grouped_holm_p_value"] == 0.08
    assert rows[2]["grouped_holm_p_value"] == 0.09
    assert rows[3]["grouped_holm_p_value"] == 0.2


def test_same_contrast_projects_continuous_hr_onto_group_mean_difference() -> None:
    row = {
        "continuous_univariable_hr": 2.0,
        "univariable_hr": 4.0,
    }
    audit = {
        "cohort_selection": {
            "patient_records": [
                {"group": "Low", "expression_value": 0.0},
                {"group": "Low", "expression_value": 1.0},
                {"group": "High", "expression_value": 2.0},
                {"group": "High", "expression_value": 3.0},
            ],
            "continuous_patient_records": [
                {"expression_value": 0.0},
                {"expression_value": 1.0},
                {"expression_value": 2.0},
                {"expression_value": 3.0},
            ],
        },
        "results": {
            "cox_models": [
                {
                    "model": "univariable",
                    "status": "completed",
                    "contrast": "High vs Low",
                }
            ]
        },
    }

    benchmark.annotate_same_contrast_effect(row, audit)

    assert row["same_contrast_status"] == "completed"
    assert round(row["same_contrast_delta_sd"], 6) == 1.549193
    assert round(row["continuous_implied_same_contrast_hr"], 6) == 2.926535
    assert round(row["same_contrast_log_hr_amplification_ratio"], 6) == 1.290994


def test_summarize_batch_preserves_firth_when_standard_cox_fails() -> None:
    firth = {
        "status": "completed",
        "hazard_ratio": 0.04,
        "hr_conf_low": 0.001,
        "hr_conf_high": 0.3,
        "p_value": 0.001,
        "ties": "breslow",
        "trigger_reasons": ["The standard Cox fit was unstable."],
    }
    failed_model = {
        "model": "stage_adjusted",
        "status": "failed",
        "reason": "Model did not produce finite HR confidence intervals.",
        "information_diagnostics": {
            "parameter_count": 2,
            "events_per_parameter": 4.5,
            "status": "severe",
        },
        "penalized_sensitivity": firth,
    }

    rows = benchmark.summarize_batch(
        {
            "results": [
                {
                    "index": 0,
                    "status": "completed",
                    "result": {
                        "id": "analysis-firth",
                        "cutpoint_method": "upper_lower_quartile",
                        "metrics": {
                            "cox_models": [
                                {
                                    **failed_model,
                                    "model": "univariable",
                                },
                                failed_model,
                            ],
                        },
                    },
                }
            ]
        }
    )

    assert rows[0]["univariable_status"] == "failed"
    assert rows[0]["univariable_firth_status"] == "completed"
    assert rows[0]["adjusted_model"] == "stage_adjusted"
    assert rows[0]["adjusted_status"] == "failed"
    assert rows[0]["adjusted_events_per_parameter"] == 4.5
    assert rows[0]["adjusted_firth_hr"] == 0.04

    benchmark.annotate_evidence_profile(rows[0])
    assert "Standard adjusted Cox failed" in rows[0]["profile_notes"]
    assert "Firth adjusted sensitivity" in rows[0]["profile_notes"]


def test_summarize_batch_preserves_prespecified_temporal_effect() -> None:
    temporal = {
        "status": "completed",
        "split_days": 730.5,
        "support": {
            "early_events": 20,
            "late_events": 15,
            "at_risk_at_split": 80,
        },
        "periods": {
            "early": {
                "hazard_ratio": 2.2,
                "hr_conf_low": 1.4,
                "hr_conf_high": 3.4,
                "p_value": 0.001,
            },
            "late": {
                "hazard_ratio": 1.1,
                "hr_conf_low": 0.7,
                "hr_conf_high": 1.8,
                "p_value": 0.6,
            },
        },
        "change": {
            "hazard_ratio_ratio": 0.5,
            "hr_ratio_conf_low": 0.3,
            "hr_ratio_conf_high": 0.9,
            "p_value": 0.02,
        },
    }
    model = {
        "model": "user_adjusted",
        "status": "completed",
        "hazard_ratio": 1.7,
        "hr_conf_low": 1.2,
        "hr_conf_high": 2.4,
        "p_value": 0.01,
        "ph_p_value": 0.01,
        "time_varying_effect": temporal,
    }
    rows = benchmark.summarize_batch(
        {
            "results": [
                {
                    "index": 0,
                    "status": "completed",
                    "result": {
                        "id": "analysis-temporal",
                        "cutpoint_method": "median",
                        "metrics": {
                            "clinical_adjustment": {"status": "requested"},
                            "cox_models": [model],
                        },
                    },
                }
            ]
        }
    )

    row = rows[0]
    assert row["adjusted_temporal_status"] == "completed"
    assert row["adjusted_temporal_split_days"] == 730.5
    assert row["adjusted_temporal_early_hr"] == 2.2
    assert row["adjusted_temporal_late_hr"] == 1.1
    assert row["adjusted_temporal_late_to_early_hr_ratio"] == 0.5
    benchmark.annotate_evidence_profile(row)
    assert "fixed 2-year diagnostic estimated" in row["profile_notes"]


def test_summarize_batch_does_not_replace_requested_adjustment() -> None:
    rows = benchmark.summarize_batch(
        {
            "results": [
                {
                    "index": 0,
                    "status": "completed",
                    "result": {
                        "id": "analysis-user-adjusted",
                        "cutpoint_method": "median",
                        "metrics": {
                            "clinical_adjustment": {
                                "status": "requested",
                                "requested_covariates": ["age_at_index"],
                                "label": "Age",
                            },
                            "cox_models": [
                                {
                                    "model": "stage_grade_adjusted",
                                    "status": "completed",
                                    "hazard_ratio": 1.5,
                                },
                                {
                                    "model": "user_adjusted",
                                    "status": "skipped",
                                    "reason": "Fewer than 10 complete patients after clinical covariate filtering.",
                                },
                            ],
                            "continuous_analysis": {
                                "linear_models": [
                                    {
                                        "model": "continuous_stage_grade_adjusted",
                                        "status": "completed",
                                        "hazard_ratio": 1.3,
                                    },
                                    {
                                        "model": "continuous_user_adjusted",
                                        "status": "skipped",
                                        "reason": "Fewer than 10 complete patients after clinical covariate filtering.",
                                    },
                                ]
                            },
                        },
                    },
                }
            ]
        }
    )

    assert rows[0]["adjusted_model"] == "user_adjusted"
    assert rows[0]["adjusted_status"] == "skipped"
    assert rows[0]["continuous_adjusted_model"] == "continuous_user_adjusted"
    assert rows[0]["continuous_adjusted_status"] == "skipped"
    benchmark.annotate_evidence_profile(rows[0])
    assert "Requested adjusted Cox not evaluable" in rows[0]["profile_notes"]
