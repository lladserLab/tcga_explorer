import pytest

from app.pancancer import (
    add_clinical_sensitivity,
    add_concordance_labels,
    adjust_p_values_bh,
    attach_effect_scale_metadata,
    attach_preparation_metadata,
    common_scale_meta_analysis_from_rows,
    meta_analysis_from_rows,
    student_t_quantile,
    student_t_two_sided_p,
)


def test_adjust_p_values_bh_preserves_input_order() -> None:
    adjusted = adjust_p_values_bh([0.01, None, 0.04, 0.03])

    assert adjusted[0] == pytest.approx(0.03)
    assert adjusted[1] is None
    assert adjusted[2] == pytest.approx(0.04)
    assert adjusted[3] == pytest.approx(0.04)


def test_attach_preparation_metadata_restores_sample_selection_and_warnings() -> None:
    rows = [
        {
            "cohort": "TCGA-A",
            "endpoint": "OS",
            "status": "completed",
            "warnings": "R warning",
        }
    ]
    prepared = [
        {
            "cohort": "TCGA-A",
            "sample_selection": {
                "selection_order": [
                    "user_filters",
                    "endpoint_completeness",
                    "requested_expression_or_score_completeness",
                    "biospecimen_priority",
                ],
                "expression_priority_fallbacks": 1,
            },
            "warnings": ["Preparation warning", "R warning"],
        }
    ]

    attached = attach_preparation_metadata(rows, prepared)

    assert attached[0]["sample_selection"]["expression_priority_fallbacks"] == 1
    assert attached[0]["warnings"] == ["Preparation warning", "R warning"]


def test_attach_effect_scale_metadata_makes_each_row_self_describing() -> None:
    rows = [
        {
            "cohort": "TCGA-A",
            "cox_models": [{"model": "univariable", "status": "completed"}],
        }
    ]
    effect_scale = {
        "synthesis": {
            "unit": "per +1 log2(TPM + 1)",
            "eligible": True,
        }
    }

    attached = attach_effect_scale_metadata(rows, effect_scale, True)

    assert attached[0]["common_scale_unit"] == "per +1 log2(TPM + 1)"
    assert attached[0]["common_scale_eligible"] is True
    assert attached[0]["cox_models"][0]["common_scale_unit"] == (
        "per +1 log2(TPM + 1)"
    )
    assert attached[0]["cox_models"][0]["common_scale_eligible"] is True


def test_meta_analysis_uses_common_scale_reml_hksj() -> None:
    result = meta_analysis_from_rows(
        [
            {
                "status": "completed",
                "endpoint": "OS",
                "common_scale_log_hr": 0.2,
                "common_scale_standard_error": 0.1,
            },
            {
                "status": "completed",
                "endpoint": "OS",
                "common_scale_log_hr": 0.4,
                "common_scale_standard_error": 0.2,
            },
            {
                "status": "completed",
                "endpoint": "OS",
                "common_scale_log_hr": 0.1,
                "common_scale_standard_error": 0.15,
            },
        ]
    )

    assert result["available"] is True
    assert result["cohorts"] == 3
    assert result["model"] == "REML random-effects with HKSJ inference"
    assert result["tau_estimator"] == "restricted maximum likelihood"
    assert result["inference"] == "Hartung-Knapp-Sidik-Jonkman"
    assert result["random_effect"]["hazard_ratio"] > 1
    assert result["heterogeneity"]["i_squared"] >= 0
    assert result["prediction_interval"]["hazard_ratio_low"] > 0
    assert result["prediction_interval"]["hazard_ratio_high"] > 0


@pytest.mark.parametrize(
    ("degrees_of_freedom", "expected"),
    [
        (1, 12.7062047364),
        (10, 2.2281388520),
        (30, 2.0422724563),
    ],
)
def test_student_t_quantile_matches_reference_values(
    degrees_of_freedom: int,
    expected: float,
) -> None:
    assert student_t_quantile(0.975, degrees_of_freedom) == pytest.approx(
        expected,
        rel=1e-9,
    )


def test_student_t_two_sided_p_matches_reference_value() -> None:
    assert student_t_two_sided_p(2.228138852, 10) == pytest.approx(
        0.05,
        rel=1e-9,
    )


def test_common_scale_meta_analysis_refuses_mixed_endpoints() -> None:
    result = common_scale_meta_analysis_from_rows(
        [
            {
                "status": "completed",
                "endpoint": "OS",
                "common_scale_log_hr": 0.2,
                "common_scale_standard_error": 0.1,
            },
            {
                "status": "completed",
                "endpoint": "DSS",
                "common_scale_log_hr": 0.3,
                "common_scale_standard_error": 0.1,
            },
        ]
    )

    assert result["available"] is False
    assert result["comparability"] == "mixed_endpoints"
    assert result["endpoints"] == ["DSS", "OS"]


def test_add_concordance_labels_uses_index_direction() -> None:
    rows = [
        {"cohort": "TCGA-A", "status": "completed", "direction": "harmful", "significant": True},
        {"cohort": "TCGA-B", "status": "completed", "direction": "harmful", "significant": False},
        {"cohort": "TCGA-C", "status": "completed", "direction": "protective", "significant": True},
    ]

    reference = add_concordance_labels(rows, "TCGA-A")

    assert reference["cohort"] == "TCGA-A"
    assert rows[0]["concordance"] == "reference"
    assert rows[1]["concordance"] == "same_direction_not_significant"
    assert rows[2]["concordance"] == "opposite_direction_significant"


def test_clinical_sensitivity_selects_most_complete_evaluable_model() -> None:
    rows = [
        {
            "cohort": "TCGA-A",
            "endpoint": "OS",
            "status": "completed",
            "direction": "harmful",
            "significant": True,
            "cox_models": [
                {
                    "model": "stage_adjusted",
                    "label": "Adjusted for ordinal stage",
                    "status": "completed",
                    "n_patients": 80,
                    "n_events": 20,
                    "log_hr": 0.2,
                    "standard_error": 0.08,
                    "common_scale_log_hr": 0.1,
                    "common_scale_standard_error": 0.04,
                    "hazard_ratio": 1.22,
                    "hr_conf_low": 1.04,
                    "hr_conf_high": 1.43,
                    "p_value": 0.01,
                    "ph_p_value": 0.4,
                    "ph_global_p_value": 0.3,
                },
                {
                    "model": "stage_grade_adjusted",
                    "label": "Adjusted for ordinal stage and grade",
                    "status": "completed",
                    "n_patients": 70,
                    "n_events": 18,
                    "log_hr": 0.18,
                    "standard_error": 0.07,
                    "common_scale_log_hr": 0.09,
                    "common_scale_standard_error": 0.035,
                    "hazard_ratio": 1.20,
                    "hr_conf_low": 1.05,
                    "hr_conf_high": 1.37,
                    "p_value": 0.008,
                    "ph_p_value": 0.5,
                    "ph_global_p_value": 0.2,
                },
            ],
        }
    ]

    sensitivity = add_clinical_sensitivity(rows, 0.10)

    assert rows[0]["selected_adjusted_model"] == "stage_grade_adjusted"
    assert rows[0]["adjusted_hazard_ratio"] == pytest.approx(1.20)
    assert rows[0]["adjusted_significant"] is True
    assert rows[0]["clinical_sensitivity"] == "retained"
    assert sensitivity["summary"]["evaluable"] == 1
    assert sensitivity["selected_model_meta_analysis"]["available"] is False
    assert "At least two" in sensitivity["selected_model_meta_analysis"]["reason"]


def test_clinical_sensitivity_does_not_pool_mixed_selected_models() -> None:
    rows = [
        {
            "cohort": "TCGA-A",
            "endpoint": "OS",
            "status": "completed",
            "direction": "harmful",
            "significant": True,
            "cox_models": [
                {
                    "model": "stage_grade_adjusted",
                    "label": "Stage and grade",
                    "status": "completed",
                    "n_patients": 70,
                    "n_events": 18,
                    "log_hr": 0.18,
                    "standard_error": 0.07,
                    "hazard_ratio": 1.20,
                    "p_value": 0.008,
                }
            ],
        },
        {
            "cohort": "TCGA-B",
            "endpoint": "OS",
            "status": "completed",
            "direction": "protective",
            "significant": False,
            "cox_models": [
                {
                    "model": "stage_grade_adjusted",
                    "label": "Stage and grade",
                    "status": "skipped",
                    "reason": "Grade unavailable.",
                },
                {
                    "model": "stage_adjusted",
                    "label": "Stage",
                    "status": "completed",
                    "n_patients": 90,
                    "n_events": 30,
                    "log_hr": -0.12,
                    "standard_error": 0.09,
                    "hazard_ratio": 0.89,
                    "p_value": 0.18,
                },
            ],
        },
    ]

    sensitivity = add_clinical_sensitivity(rows, 0.10)

    selected_meta = sensitivity["selected_model_meta_analysis"]
    assert selected_meta["available"] is False
    assert selected_meta["comparability"] == "mixed_adjustment_families"
    assert sensitivity["summary"]["selected_model_counts"] == {
        "stage_grade_adjusted": 1,
        "stage_adjusted": 1,
    }


def test_clinical_sensitivity_preserves_reversal_and_not_evaluable_states() -> None:
    rows = [
        {
            "cohort": "TCGA-A",
            "endpoint": "OS",
            "status": "completed",
            "direction": "harmful",
            "significant": True,
            "cox_models": [
                {
                    "model": "stage_adjusted",
                    "label": "Stage",
                    "status": "completed",
                    "n_patients": 50,
                    "n_events": 12,
                    "log_hr": -0.4,
                    "standard_error": 0.15,
                    "hazard_ratio": 0.67,
                    "p_value": 0.01,
                }
            ],
        },
        {
            "cohort": "TCGA-B",
            "endpoint": "OS",
            "status": "completed",
            "direction": "protective",
            "significant": False,
            "cox_models": [
                {
                    "model": "stage_adjusted",
                    "label": "Stage",
                    "status": "skipped",
                    "reason": "Fewer than 10 complete patients.",
                }
            ],
        },
    ]

    sensitivity = add_clinical_sensitivity(rows, 0.10)

    assert rows[0]["clinical_sensitivity"] == "reversed"
    assert rows[1]["clinical_sensitivity"] == "not_evaluable"
    assert "Fewer than 10" in rows[1]["adjusted_reason"]
    assert sensitivity["summary"]["direction_reversed"] == 1
    assert sensitivity["summary"]["not_evaluable"] == 1
