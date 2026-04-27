from dataclasses import dataclass

from app.survival import assign_groups, assign_groups_with_cutpoint, filter_samples


@dataclass
class MockSample:
    patient_id: str
    barcode: str
    sample_type: str | None
    os_time_days: float | None = 100.0
    os_event: int | None = 1
    stage: str | None = None
    gender: str | None = None
    race: str | None = None
    age_at_index: float | None = None


class EmptyFilters:
    sample_types: list[str] = []
    stages: list[str] = []
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
