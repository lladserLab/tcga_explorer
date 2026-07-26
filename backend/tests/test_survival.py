from dataclasses import dataclass

import pytest

from app.survival import (
    ClinicalOutcome,
    SurvivalRecord,
    assign_groups,
    assign_groups_with_cutpoint,
    build_combined_survival_records,
    build_continuous_survival_records,
    build_survival_records,
    filter_sample_candidates,
    filter_samples,
    select_expression_complete_samples,
    select_rmst_tau,
    validate_records,
)


@dataclass
class MockSample:
    patient_id: str
    barcode: str
    sample_type: str | None
    os_time_days: float | None = 100.0
    os_event: int | None = 1
    stage: str | None = None
    grade: str | None = None
    gender: str | None = None
    race: str | None = None
    age_at_index: float | None = None


class EmptyFilters:
    sample_types: list[str] = []
    stages: list[str] = []
    grades: list[str] = []
    genders: list[str] = []
    races: list[str] = []
    age_min = None
    age_max = None
    max_time_days = None


def test_assign_groups_median() -> None:
    labels, levels, details = assign_groups([1, 2, 3, 4], "median")
    assert labels == ["Low", "Low", "High", "High"]
    assert levels == ["Low", "High"]
    assert details["threshold"] == 2.5


def test_assign_groups_upper_lower_quartile_discards_middle() -> None:
    labels, levels, details = assign_groups([1, 2, 3, 4, 5, 6, 7, 8], "upper_lower_quartile")
    assert levels == ["Low", "High"]
    assert labels.count(None) == 4
    assert details["lower_quartile"] == 2.75
    assert details["upper_quartile"] == 6.25


def test_continuous_population_retains_patients_excluded_by_outer_quartiles() -> None:
    samples = [
        MockSample(f"P{index}", f"S{index}", "Primary Tumor")
        for index in range(1, 21)
    ]
    expression = {sample.barcode: float(index) for index, sample in enumerate(samples, start=1)}

    grouped, _, _ = build_survival_records(
        samples,
        expression,
        "upper_lower_quartile",
        None,
    )
    continuous = build_continuous_survival_records(samples, expression)

    assert len(grouped) == 10
    assert len(continuous) == 20
    assert {record.group for record in continuous} == {"All eligible"}
    assert {record.patient_id for record in grouped} < {
        record.patient_id for record in continuous
    }


def test_assign_groups_maxstat_uses_precomputed_threshold() -> None:
    labels, levels, details = assign_groups_with_cutpoint(
        [1, 2, 3, 4, 5],
        "maxstat",
        precomputed_cutpoint={"threshold": 3.0, "statistic": 4.2},
    )
    assert labels == ["Low", "Low", "Low", "High", "High"]
    assert levels == ["Low", "High"]
    assert details["threshold"] == 3.0
    assert details["statistic"] == 4.2


def test_build_combined_survival_records_crosses_signature_groups() -> None:
    samples = [
        MockSample("P1", "S1", "Primary Tumor"),
        MockSample("P2", "S2", "Primary Tumor"),
        MockSample("P3", "S3", "Primary Tumor"),
        MockSample("P4", "S4", "Primary Tumor"),
    ]
    expression_a = {"S1": 1.0, "S2": 2.0, "S3": 3.0, "S4": 4.0}
    expression_b = {"S1": 1.0, "S2": 4.0, "S3": 2.0, "S4": 3.0}

    records, levels, details = build_combined_survival_records(samples, expression_a, expression_b, "median")

    assert levels == ["Low_Low", "Low_High", "High_Low", "High_High"]
    assert [record.group for record in records] == ["Low_Low", "Low_High", "High_Low", "High_High"]
    assert records[0].expression_value_a == 1.0
    assert records[0].expression_value_b == 1.0
    assert records[0].as_dict()["group_a"] == "Low"
    assert details["signature_a_threshold"] == 2.5
    assert details["signature_b_threshold"] == 2.5


def test_filter_samples_keeps_primary_tumor_over_alphabetic_normal() -> None:
    samples = [
        MockSample("TCGA-AA-0001", "LOCAL-A", "Solid Tissue Normal"),
        MockSample("TCGA-AA-0001", "LOCAL-Z", "Primary Tumor"),
        MockSample("TCGA-AA-0002", "LOCAL-B", "Primary Tumor"),
    ]

    retained, warnings, summary = filter_samples(samples, EmptyFilters())

    retained_by_patient = {sample.patient_id: sample.barcode for sample in retained}
    assert retained_by_patient == {"TCGA-AA-0001": "LOCAL-Z", "TCGA-AA-0002": "LOCAL-B"}
    assert summary["duplicate_samples_removed"] == 1
    assert summary["retained_sample_types"] == {"Primary Tumor": 2}
    assert any("TCGA biospecimen priority" in warning for warning in warnings)


def test_filter_samples_uses_tcga_sample_code_priority() -> None:
    samples = [
        MockSample("TCGA-AA-0001", "TCGA-AA-0001-11A-01R-0000-01", "Solid Tissue Normal"),
        MockSample("TCGA-AA-0001", "TCGA-AA-0001-01A-01R-0000-01", "Primary Tumor"),
    ]

    retained, _, summary = filter_samples(samples, EmptyFilters())

    assert len(retained) == 1
    assert retained[0].barcode == "TCGA-AA-0001-01A-01R-0000-01"
    assert summary["removed_duplicate_sample_types"] == {"Solid Tissue Normal": 1}


def test_filter_samples_prefers_primary_over_metastatic_when_both_exist() -> None:
    samples = [
        MockSample("TCGA-SKCM-0001", "TCGA-SKCM-0001-06A-01R-0000-07", "Metastatic"),
        MockSample("TCGA-SKCM-0001", "TCGA-SKCM-0001-01A-01R-0000-07", "Primary Tumor"),
    ]

    retained, _, summary = filter_samples(samples, EmptyFilters())

    assert len(retained) == 1
    assert retained[0].barcode == "TCGA-SKCM-0001-01A-01R-0000-07"
    assert summary["retained_sample_types"] == {"Primary Tumor": 1}
    assert summary["removed_duplicate_sample_types"] == {"Metastatic": 1}


def test_filter_samples_can_filter_by_grade() -> None:
    class GradeFilters(EmptyFilters):
        grades = ["G2"]

    samples = [
        MockSample("TCGA-AA-0001", "TCGA-AA-0001-01A-01R-0000-01", "Primary Tumor", grade="G1"),
        MockSample("TCGA-AA-0002", "TCGA-AA-0002-01A-01R-0000-01", "Primary Tumor", grade="G2"),
    ]

    retained, _, summary = filter_samples(samples, GradeFilters())

    assert [sample.patient_id for sample in retained] == ["TCGA-AA-0002"]
    assert summary["after_user_filters"] == 1


def test_expression_complete_selection_falls_back_to_lower_priority_sample() -> None:
    primary = MockSample(
        "TCGA-AA-0001",
        "TCGA-AA-0001-01A-01R-0000-01",
        "Primary Tumor",
    )
    metastatic = MockSample(
        "TCGA-AA-0001",
        "TCGA-AA-0001-06A-01R-0000-01",
        "Metastatic",
    )
    second_patient = MockSample(
        "TCGA-AA-0002",
        "TCGA-AA-0002-01A-01R-0000-01",
        "Primary Tumor",
    )
    candidates, warnings, summary = filter_sample_candidates(
        [primary, metastatic, second_patient],
        EmptyFilters(),
    )

    retained, warnings, summary = select_expression_complete_samples(
        candidates,
        {metastatic.barcode, second_patient.barcode},
        warnings=warnings,
        summary=summary,
    )

    assert {sample.patient_id: sample.barcode for sample in retained} == {
        "TCGA-AA-0001": metastatic.barcode,
        "TCGA-AA-0002": second_patient.barcode,
    }
    assert summary["selection_order"] == [
        "user_filters",
        "endpoint_completeness",
        "requested_expression_or_score_completeness",
        "biospecimen_priority",
    ]
    assert summary["missing_expression_samples_removed"] == 1
    assert summary["missing_expression_patients_removed"] == 0
    assert summary["expression_priority_fallbacks"] == 1
    assert summary["expression_priority_fallback_barcodes"] == [metastatic.barcode]
    assert any("lower-priority biospecimen" in warning for warning in warnings)


def test_expression_complete_selection_uses_summary_for_sample_type_warning() -> None:
    normal = MockSample(
        "TCGA-AA-0001",
        "TCGA-AA-0001-11A-01R-0000-01",
        "Solid Tissue Normal",
    )

    retained, warnings, summary = select_expression_complete_samples(
        [normal],
        {normal.barcode},
        summary={"sample_type_filter_applied": False},
    )

    assert retained == [normal]
    assert summary["retained_patients"] == 1
    assert any("normal/control/unknown" in warning for warning in warnings)


def test_expression_complete_selection_uses_full_multigene_score_overlap() -> None:
    samples = [
        MockSample(
            "TCGA-AA-0001",
            "TCGA-AA-0001-01A-01R-0000-01",
            "Primary Tumor",
        ),
        MockSample(
            "TCGA-AA-0001",
            "TCGA-AA-0001-06A-01R-0000-01",
            "Metastatic",
        ),
        MockSample(
            "TCGA-AA-0002",
            "TCGA-AA-0002-01A-01R-0000-01",
            "Primary Tumor",
        ),
    ]
    candidates, warnings, summary = filter_sample_candidates(
        samples,
        EmptyFilters(),
    )
    gene_a = {samples[0].barcode, samples[1].barcode, samples[2].barcode}
    gene_b = {samples[1].barcode, samples[2].barcode}

    retained, _, summary = select_expression_complete_samples(
        candidates,
        gene_a & gene_b,
        warnings=warnings,
        summary=summary,
    )

    assert {sample.patient_id: sample.barcode for sample in retained} == {
        "TCGA-AA-0001": samples[1].barcode,
        "TCGA-AA-0002": samples[2].barcode,
    }
    assert summary["expression_complete_patients"] == 2
    assert summary["expression_priority_fallbacks"] == 1


def test_crossed_signatures_drop_patient_without_both_complete_scores() -> None:
    samples = [
        MockSample("P1", "P1-PRIMARY", "Primary Tumor"),
        MockSample("P1", "P1-METASTATIC", "Metastatic"),
        MockSample("P2", "P2-PRIMARY", "Primary Tumor"),
    ]
    candidates, warnings, summary = filter_sample_candidates(
        samples,
        EmptyFilters(),
    )
    signature_a = {"P1-PRIMARY", "P1-METASTATIC", "P2-PRIMARY"}
    signature_b = {"P1-METASTATIC"}

    retained, _, summary = select_expression_complete_samples(
        candidates,
        signature_a & signature_b,
        warnings=warnings,
        summary=summary,
    )

    assert [sample.barcode for sample in retained] == ["P1-METASTATIC"]
    assert summary["missing_expression_patients_removed"] == 1
    assert summary["retained_patients"] == 1


def test_select_rmst_tau_is_independent_of_expression_groups() -> None:
    samples = [
        MockSample(f"P{index}", f"S{index}", "Primary Tumor")
        for index in range(1, 13)
    ]
    outcomes = {
        sample.patient_id: ClinicalOutcome(
            endpoint="OS",
            time_days=float(index * 100),
            event=index % 2,
            source="test",
        )
        for index, sample in enumerate(samples, start=1)
    }

    tau = select_rmst_tau(
        samples,
        {sample.barcode for sample in samples},
        endpoint_by_patient=outcomes,
    )

    assert tau["status"] == "available"
    assert tau["cutpoint_independent"] is True
    assert tau["source_n_patients"] == 12
    assert tau["tau_days"] == pytest.approx(925.0)


def test_validate_records_requires_five_events_after_grouping() -> None:
    records = [
        SurvivalRecord(
            patient_id=f"P{index}",
            sample_barcode=f"S{index}",
            endpoint="OS",
            expression_value=float(index),
            group="Low" if index <= 5 else "High",
            time_days=100.0 + index,
            event=1 if index <= 4 else 0,
            sample_type="Primary Tumor",
            stage=None,
            grade=None,
            gender=None,
            race=None,
            age_at_index=None,
        )
        for index in range(1, 11)
    ]

    with pytest.raises(ValueError, match="at least 5 survival events"):
        validate_records(records, "overall survival")
