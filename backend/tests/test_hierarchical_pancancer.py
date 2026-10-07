from __future__ import annotations

import random

import pytest

from app.hierarchical_pancancer import (
    HIERARCHICAL_EFFECT_SCALE,
    hierarchical_meta_analysis,
    validate_hierarchical_effects,
)


def effect(
    cancer: str,
    study: str,
    log_hr: float,
    standard_error: float = 0.12,
    *,
    events: int = 24,
    **updates,
) -> dict:
    row = {
        "release_id": f"{study}-v1",
        "study_id": study,
        "study_cluster_id": study,
        "cancer_id": cancer,
        "endpoint": "OS",
        "time_origin": "diagnosis",
        "clinical_context": "primary untreated baseline",
        "model_family": "univariable_cox",
        "effect_scale": HIERARCHICAL_EFFECT_SCALE,
        "status": "completed",
        "n_patients": 80,
        "n_events": events,
        "log_hr": log_hr,
        "standard_error": standard_error,
    }
    row.update(updates)
    return row


def test_hierarchical_meta_pools_studies_then_cancers_and_runs_leave_one_out() -> None:
    rows = [
        effect("BRCA", "TCGA-BRCA", 0.22, 0.10),
        effect("BRCA", "SCAN-B", 0.31, 0.13),
        effect("LUAD", "TCGA-LUAD", 0.15, 0.09),
        effect("LUAD", "CPTAC-LUAD", 0.08, 0.15),
        effect("KIRC", "TCGA-KIRC", 0.27, 0.11),
        effect("KIRC", "CHECKMATE-KIRC", 0.42, 0.16),
    ]

    result = hierarchical_meta_analysis(
        rows,
        formal_min_cancers=3,
        formal_min_events=100,
    )

    assert result["available"] is True
    assert result["validation"]["eligible"] is True
    assert result["summary"] == {
        "studies": 6,
        "cancers": 3,
        "patients": 480,
        "events": 144,
        "replicated_events": 144,
        "replicated_patients": 480,
    }
    assert [row["cancer_id"] for row in result["cancer_effects"]] == [
        "BRCA",
        "KIRC",
        "LUAD",
    ]
    assert all(row["n_studies"] == 2 for row in result["cancer_effects"])
    assert result["global_effect"]["model"] == (
        "REML random-effects with modified HKSJ inference"
    )
    assert result["global_effect"]["heterogeneity"]["q"] >= 0
    assert result["global_effect"]["heterogeneity"]["i_squared"] >= 0
    assert result["global_effect"]["heterogeneity"]["tau_squared"] >= 0
    assert result["global_effect"]["prediction_interval"] is not None
    assert len(result["leave_one_study_out"]) == 6
    assert len(result["leave_one_cancer_out"]) == 3
    assert result["formal_pan_cancer_support"]["supported"] is True
    assert result["classification"] in {
        "broadly_consistent",
        "heterogeneous_or_context_dependent",
        "average_pan_cancer_association",
        "no_average_association",
    }


def test_hierarchical_meta_uses_modified_hksj_at_both_pooling_levels() -> None:
    rows = [
        effect("BRCA", "brca-a", 0.2, 0.1),
        effect("BRCA", "brca-b", 0.2, 0.1),
        effect("LUAD", "luad-a", 0.2, 0.1),
        effect("LUAD", "luad-b", 0.2, 0.1),
    ]

    result = hierarchical_meta_analysis(rows)

    assert result["model"] == (
        "two-stage REML random-effects with modified HKSJ inference"
    )
    for cancer in result["cancer_effects"]:
        random_effect = cancer["meta_analysis"]["random_effect"]
        assert cancer["propagation_standard_error"] == (
            "modified_HKSJ_standard_error"
        )
        assert random_effect["hksj_scale_unmodified"] == pytest.approx(0.0)
        assert random_effect["hksj_scale"] == pytest.approx(1.0)
        assert random_effect["hksj_scale_floor_applied"] is True
        assert cancer["standard_error"] == pytest.approx(
            random_effect["conventional_standard_error"]
        )

    global_effect = result["global_effect"]
    random_effect = global_effect["random_effect"]
    assert global_effect["inference"] == (
        "modified Hartung-Knapp-Sidik-Jonkman"
    )
    assert random_effect["hksj_scale_unmodified"] == pytest.approx(0.0)
    assert random_effect["hksj_scale"] == pytest.approx(1.0)
    assert random_effect["hksj_scale_floor_applied"] is True
    assert random_effect["standard_error"] == pytest.approx(
        random_effect["conventional_standard_error"]
    )
    assert random_effect["p_value"] > 0.05
    assert random_effect["hr_conf_low"] < random_effect["hazard_ratio"]
    assert random_effect["hr_conf_high"] > random_effect["hazard_ratio"]


@pytest.mark.parametrize(
    ("field", "replacement", "code"),
    [
        ("endpoint", "DSS", "mixed_endpoints"),
        ("time_origin", "therapy start", "mixed_time_origins"),
        (
            "clinical_context",
            "metastatic post-treatment",
            "mixed_clinical_contexts",
        ),
        ("model_family", "stage_adjusted_cox", "mixed_model_families"),
    ],
)
def test_hierarchical_meta_blocks_mixed_estimands(
    field: str,
    replacement: str,
    code: str,
) -> None:
    rows = [
        effect("BRCA", "study-a", 0.2),
        effect("LUAD", "study-b", 0.1, **{field: replacement}),
    ]

    result = hierarchical_meta_analysis(rows)

    assert result["available"] is False
    assert result["code"] == code
    assert result["validation"]["comparability"] == code
    assert result["global_effect"] is None


def test_hierarchical_meta_requires_explicit_comparability_metadata() -> None:
    rows = [
        effect("BRCA", "study-a", 0.2),
        effect("LUAD", "study-b", 0.1, time_origin=None),
    ]

    validation = validate_hierarchical_effects(rows)

    assert validation["eligible"] is False
    assert validation["code"] == "comparability_metadata_unavailable"
    assert validation["missing"]["time_origin"] == ["study-b-v1"]


def test_hierarchical_meta_blocks_correlated_releases_in_same_study_cluster() -> None:
    rows = [
        effect("BRCA", "scan-b-release-a", 0.2, study_cluster_id="scan-b"),
        effect("BRCA", "scan-b-release-b", 0.3, study_cluster_id="scan-b"),
        effect("LUAD", "study-c", 0.1),
    ]

    validation = validate_hierarchical_effects(rows)

    assert validation["eligible"] is False
    assert validation["code"] == "dependent_releases"
    assert validation["study_clusters"]["scan-b"] == [
        "scan-b-release-a-v1",
        "scan-b-release-b-v1",
    ]


def test_descriptive_dependent_release_is_audited_but_not_pooled() -> None:
    rows = [
        effect("BRCA", "scan-b-primary", 0.2, study_cluster_id="scan-b"),
        effect(
            "BRCA",
            "scan-b-secondary",
            0.3,
            study_cluster_id="scan-b",
            pooling_eligible=False,
            pooling_exclusion_reason="overlapping_secondary_release",
        ),
        effect("LUAD", "study-c", 0.1),
    ]

    result = hierarchical_meta_analysis(rows)

    assert result["available"] is False
    assert result["summary"]["studies"] == 2
    assert result["validation"]["excluded"] == [
        {
            "release_id": "scan-b-secondary-v1",
            "study_id": "scan-b-secondary",
            "cancer_id": "BRCA",
            "status": "completed",
            "reason": "overlapping_secondary_release",
        }
    ]


def test_single_cancer_is_reported_but_global_synthesis_is_insufficient() -> None:
    result = hierarchical_meta_analysis(
        [
            effect("BRCA", "study-a", 0.2),
            effect("BRCA", "study-b", 0.3),
        ]
    )

    assert result["available"] is False
    assert len(result["cancer_effects"]) == 1
    assert result["cancer_effects"][0]["meta_analysis"]["available"] is True
    assert result["global_effect"]["available"] is False
    assert result["global_effect"]["cancers"] == 1
    assert result["classification"] == "insufficient_support"


def test_single_study_cancers_keep_original_uncertainty() -> None:
    result = hierarchical_meta_analysis(
        [
            effect("BRCA", "study-a", 0.2, 0.1),
            effect("LUAD", "study-b", -0.1, 0.2),
        ]
    )

    assert result["available"] is False
    assert result["cancer_effects"][0]["standard_error"] == pytest.approx(0.1)
    assert result["cancer_effects"][0]["heterogeneity"] is None
    assert result["cancer_effects"][1]["standard_error"] == pytest.approx(0.2)
    assert result["summary"]["events"] == 48
    assert result["summary"]["replicated_events"] == 0
    assert result["summary"]["replicated_patients"] == 0
    assert result["formal_pan_cancer_support"]["supported"] is False
    assert result["within_cancer_replication"] == {
        "minimum_independent_studies": 2,
        "replicated_cancers": [],
        "replicated_cancer_count": 0,
        "single_study_cancers": ["BRCA", "LUAD"],
        "single_study_effects_are_descriptive_only": True,
    }
    assert result["classification"] == "insufficient_support"


def test_hierarchical_result_is_deterministic_under_input_reordering() -> None:
    rows = [
        effect("BRCA", "study-a", 0.2),
        effect("BRCA", "study-b", 0.3),
        effect("LUAD", "study-c", 0.1),
        effect("LUAD", "study-d", 0.25),
        effect("KIRC", "study-e", -0.05),
    ]
    shuffled = list(rows)
    random.Random(173).shuffle(shuffled)

    ordered_result = hierarchical_meta_analysis(rows)
    shuffled_result = hierarchical_meta_analysis(shuffled)

    assert shuffled_result == ordered_result


def test_mixed_effect_scales_are_blocked() -> None:
    validation = validate_hierarchical_effects(
        [
            effect("BRCA", "study-a", 0.2),
            effect("LUAD", "study-b", 0.1, effect_scale="within_study_sd"),
        ]
    )

    assert validation["eligible"] is False
    assert validation["code"] == "mixed_or_unsupported_effect_scales"
