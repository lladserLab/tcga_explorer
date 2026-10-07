from types import SimpleNamespace

import pytest

from app.clinical_grouping import clinical_grouping_context
from app.repository.service import (
    IMMOTION150_DATASET_ID,
    RepositoryAnalysisSample,
    repository_requires_independent_arm,
    repository_study_arm,
)
from app.schemas import AnalysisFilters
from app.survival import ClinicalOutcome, filter_sample_candidates


def _context(dataset_id: str = IMMOTION150_DATASET_ID):
    return SimpleNamespace(dataset=SimpleNamespace(id=dataset_id))


def _samples() -> list[RepositoryAnalysisSample]:
    samples = []
    for arm_index, arm in enumerate(
        (
            "Atezolizumab",
            "Atezolizumab + Bevacizumab",
            "Sunitinib",
        )
    ):
        for index in range(6):
            patient_id = f"arm-{arm_index}-{index}"
            samples.append(
                RepositoryAnalysisSample(
                    patient_id=patient_id,
                    barcode=patient_id,
                    sample_type="Metastasis",
                    stage="IV",
                    grade=None,
                    gender=None,
                    race=None,
                    age_at_index=None,
                    selection_rank=0,
                    sample_role="Pretreatment biopsy",
                    raw_metadata=None,
                    study_arm=arm,
                )
            )
    return samples


def test_immotion_arm_is_derived_only_from_treatment_assignment() -> None:
    context = _context()
    assert repository_study_arm(
        context,
        {"ICI_RX": "Atezolizumab", "PFS_STATUS": "1:Progressed"},
        {"NON_ICI_RX": "Bevacizumab", "RESPONSE": "Partial Response"},
    ) == "Atezolizumab + Bevacizumab"
    assert repository_study_arm(
        context,
        {"ICI_RX": "None"},
        {"NON_ICI_RX": "Sunitinib"},
    ) == "Sunitinib"


def test_single_arm_policy_is_specific_to_immotion_pfs() -> None:
    assert repository_requires_independent_arm(_context(), "PFS") is True
    assert repository_requires_independent_arm(_context(), "OS") is False
    assert repository_requires_independent_arm(_context("another-study"), "PFS") is False


def test_immotion_catalog_exposes_three_randomized_arms() -> None:
    catalog, values = clinical_grouping_context(
        _samples(), cohort="TCGA-KIRC", repository=True
    )
    definition = next(item for item in catalog if item["id"] == "study_arm")
    assert definition["label"] == "Treatment arm"
    assert definition["declared_source_column"] == (
        "patient.ICI_RX + sample.NON_ICI_RX"
    )
    assert [level["value"] for level in definition["levels"]] == [
        "Atezolizumab",
        "Atezolizumab + Bevacizumab",
        "Sunitinib",
    ]
    assert set(values["study_arm"].values()) == {
        "Atezolizumab",
        "Atezolizumab + Bevacizumab",
        "Sunitinib",
    }


def test_immotion_pfs_rejects_pooled_arms_and_accepts_one_arm() -> None:
    samples = _samples()
    outcomes = {
        sample.patient_id: ClinicalOutcome(
            endpoint="PFS", time_days=100.0, event=1, source="external:test"
        )
        for sample in samples
    }
    with pytest.raises(ValueError, match="exactly one randomized treatment arm"):
        filter_sample_candidates(
            samples,
            AnalysisFilters(),
            endpoint_by_patient=outcomes,
            endpoint="PFS",
            selection_rule="external",
            required_single_study_arm=True,
        )

    selected, _, summary = filter_sample_candidates(
        samples,
        AnalysisFilters(
            custom_filters=[
                {
                    "variable_id": "study_arm",
                    "categorical_levels": ["Sunitinib"],
                }
            ]
        ),
        endpoint_by_patient=outcomes,
        endpoint="PFS",
        selection_rule="external",
        required_single_study_arm=True,
    )
    assert len(selected) == 6
    assert {sample.study_arm for sample in selected} == {"Sunitinib"}
    assert summary["study_arm_policy"] == "single_randomized_arm_required"
    assert summary["retained_study_arms"] == ["Sunitinib"]
