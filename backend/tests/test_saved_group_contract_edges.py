"""Focused regression checks for the manuscript's saved-group contract."""
from types import SimpleNamespace

import pytest

from app.gsea import survival_group_assignments
from app.schemas import GseaGroupingDefinition


@pytest.fixture
def saved_groups(tmp_path):
    source = tmp_path / "assignments.csv"
    source.write_text(
        "patient_id,sample_barcode,group,expression_value\n"
        "P1,S1,Low,4\nP2,S2,Low,4\nP3,S3,High,9\nP4,S4,High,10\n"
    )
    job = SimpleNamespace(
        id="frozen-analysis", status="completed", cohort="external",
        dataset_id="dataset-a", dataset_release_id="release-1",
        cutpoint_method="median", csv_path=str(source), request_payload={},
    )
    session = SimpleNamespace(get=lambda model, key: job)
    return session, job, source


def definition(reverse=False):
    return GseaGroupingDefinition(
        source="survival", survival_analysis_id="frozen-analysis",
        group_a_label="High" if reverse else "Low",
        group_b_label="Low" if reverse else "High",
        group_a_values=["High" if reverse else "Low"],
        group_b_values=["Low" if reverse else "High"],
    )


def test_explicit_reversal_preserves_membership_and_reverses_only_contrast(saved_groups):
    session, job, _ = saved_groups
    kwargs = dict(cohort=job.cohort, dataset_id=job.dataset_id,
                  dataset_release_id=job.dataset_release_id)
    forward, details, rows = survival_group_assignments(session, grouping=definition(), **kwargs)
    reverse, reversed_details, reversed_rows = survival_group_assignments(
        session, grouping=definition(True), **kwargs)
    assert forward == {"S1": "a", "S2": "a", "S3": "b", "S4": "b"}
    assert reverse == {key: "b" if value == "a" else "a" for key, value in forward.items()}
    assert rows == reversed_rows
    assert details["source_group_a"] == "Low"
    assert reversed_details["source_group_a"] == "High"
    assert details["contrast"] == reversed_details["contrast"] == "group_b_minus_group_a"


@pytest.mark.parametrize("field", ["dataset_id", "dataset_release_id"])
def test_saved_groups_reject_incompatible_dataset_or_release(saved_groups, field):
    session, job, _ = saved_groups
    kwargs = dict(cohort=job.cohort, dataset_id=job.dataset_id,
                  dataset_release_id=job.dataset_release_id)
    kwargs[field] = "incompatible"
    with pytest.raises(ValueError, match="different dataset release"):
        survival_group_assignments(session, grouping=definition(), **kwargs)


def test_unavailable_assignments_fail_without_recomputing_a_cutpoint(saved_groups):
    session, job, source = saved_groups
    job.csv_path = str(source.with_name("not-available.csv"))
    with pytest.raises(ValueError, match="expired or are unavailable"):
        survival_group_assignments(
            session, cohort=job.cohort, dataset_id=job.dataset_id,
            dataset_release_id=job.dataset_release_id, grouping=definition())
