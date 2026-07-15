import pytest

from app.pancancer import adjust_p_values_bh, add_concordance_labels, meta_analysis_from_rows


def test_adjust_p_values_bh_preserves_input_order() -> None:
    adjusted = adjust_p_values_bh([0.01, None, 0.04, 0.03])

    assert adjusted[0] == pytest.approx(0.03)
    assert adjusted[1] is None
    assert adjusted[2] == pytest.approx(0.04)
    assert adjusted[3] == pytest.approx(0.04)


def test_meta_analysis_random_effects_returns_pooled_hr() -> None:
    result = meta_analysis_from_rows(
        [
            {"status": "completed", "log_hr": 0.2, "standard_error": 0.1},
            {"status": "completed", "log_hr": 0.4, "standard_error": 0.2},
        ]
    )

    assert result["available"] is True
    assert result["cohorts"] == 2
    assert result["random_effect"]["hazard_ratio"] > 1
    assert result["heterogeneity"]["i_squared"] >= 0


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
