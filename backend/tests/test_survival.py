from dataclasses import dataclass

from app.survival import assign_groups, assign_groups_with_cutpoint, build_combined_survival_records, filter_samples


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
