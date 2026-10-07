from types import SimpleNamespace

import pytest

from app.gsea import select_gsea_samples
from app.sample_population import (
    SAMPLE_POPULATION_CONTRACT_VERSION,
    resolve_tcga_sample_population,
    tcga_population_options,
)
from app.schemas import AnalysisFilters, AnalysisRequest
from app.survival import filter_sample_candidates, select_expression_complete_samples


def sample(cohort: str, patient: str, code: str, sample_type: str):
    return SimpleNamespace(
        cohort=cohort,
        patient_id=patient,
        barcode=f"{patient}-{code}A",
        sample_type=sample_type,
        stage=None,
        grade=None,
        gender=None,
        race=None,
        age_at_index=None,
        os_time_days=365.0,
        os_event=1,
    )


def test_primary_population_excludes_normal_without_fallback():
    rows = [
        sample("TCGA-BRCA", "TCGA-AA-0001", "01", "Primary Tumor"),
        sample("TCGA-BRCA", "TCGA-AA-0001", "11", "Solid Tissue Normal"),
        sample("TCGA-BRCA", "TCGA-AA-0002", "11", "Solid Tissue Normal"),
    ]

    candidates, warnings, summary = filter_sample_candidates(
        rows,
        AnalysisFilters(sample_population="primary_solid"),
    )
    retained, warnings, summary = select_expression_complete_samples(
        candidates,
        {row.barcode for row in rows},
        warnings=warnings,
        summary=summary,
    )

    assert [row.patient_id for row in retained] == ["TCGA-AA-0001"]
    assert summary["sample_population"]["contract_version"] == (
        SAMPLE_POPULATION_CONTRACT_VERSION
    )
    assert summary["sample_population"]["fallback_across_populations"] is False
    assert summary["population_excluded_samples"] == 2
    assert summary["retained_sample_types"] == {"Primary Tumor": 1}
    assert not any("normal/control" in warning for warning in warnings)


def test_skcm_requires_primary_or_metastatic_population():
    rows = [
        sample("TCGA-SKCM", "TCGA-BB-0001", "01", "Primary Tumor"),
        sample("TCGA-SKCM", "TCGA-BB-0002", "06", "Metastatic"),
    ]

    with pytest.raises(ValueError, match="does not mix"):
        filter_sample_candidates(rows, AnalysisFilters())

    primary, _, primary_summary = filter_sample_candidates(
        rows,
        AnalysisFilters(sample_population="primary_solid"),
    )
    metastatic, _, metastatic_summary = filter_sample_candidates(
        rows,
        AnalysisFilters(sample_population="metastatic"),
    )

    assert [row.sample_type for row in primary] == ["Primary Tumor"]
    assert [row.sample_type for row in metastatic] == ["Metastatic"]
    assert primary_summary["sample_population"]["id"] == "primary_solid"
    assert metastatic_summary["sample_population"]["id"] == "metastatic"


def test_laml_defaults_to_primary_blood_and_rejects_primary_solid():
    policy, payload = resolve_tcga_sample_population("TCGA-LAML", None)
    assert policy.id == "primary_blood"
    assert payload["allowed_tcga_sample_codes"] == ["03", "09"]

    with pytest.raises(ValueError, match="hematologic"):
        resolve_tcga_sample_population("TCGA-LAML", "primary_solid")


def test_grouped_expression_uses_the_same_population_contract():
    rows = [
        sample("TCGA-SKCM", "TCGA-CC-0001", "01", "Primary Tumor"),
        sample("TCGA-SKCM", "TCGA-CC-0002", "06", "Metastatic"),
    ]
    retained, audit, _ = select_gsea_samples(
        rows,
        AnalysisFilters(sample_population="metastatic"),
        [row.barcode for row in rows],
    )

    assert [row.sample_type for row in retained] == ["Metastatic"]
    assert audit["sample_population"]["id"] == "metastatic"
    assert audit["retained_sample_types"] == {"Metastatic": 1}


def test_population_catalog_reports_patient_and_sample_counts():
    rows = [
        sample("TCGA-SKCM", "TCGA-DD-0001", "01", "Primary Tumor"),
        sample("TCGA-SKCM", "TCGA-DD-0002", "06", "Metastatic"),
        sample("TCGA-SKCM", "TCGA-DD-0002", "07", "Additional Metastatic"),
    ]
    options = {row["id"]: row for row in tcga_population_options("TCGA-SKCM", rows)}

    assert options["primary_solid"]["patient_count"] == 1
    assert options["metastatic"]["sample_count"] == 2
    assert options["metastatic"]["patient_count"] == 1
    assert options["metastatic"]["requires_explicit_selection"] is True


def test_conflicting_barcode_and_sample_type_are_excluded():
    rows = [
        sample("TCGA-OV", "TCGA-EE-0001", "01", "Primary Tumor"),
        sample("TCGA-OV", "TCGA-EE-0002", "01", "Recurrent Tumor"),
    ]

    candidates, _, summary = filter_sample_candidates(
        rows,
        AnalysisFilters(sample_population="primary_solid"),
    )

    assert [row.patient_id for row in candidates] == ["TCGA-EE-0001"]
    assert summary["population_metadata_conflicts_excluded"] == 1
    options = {
        row["id"]: row for row in tcga_population_options("TCGA-OV", rows)
    }
    assert options["primary_solid"]["sample_count"] == 1
    assert options["recurrent"]["sample_count"] == 0


def test_compute_requests_persist_defaults_and_block_implicit_skcm():
    brca = AnalysisRequest(cohort="TCGA-BRCA", gene_symbol="ESR1")
    assert brca.filters.sample_population == "primary_disease"

    with pytest.raises(ValueError, match="explicit sample_population"):
        AnalysisRequest(cohort="TCGA-SKCM", gene_symbol="PDCD1")

    skcm = AnalysisRequest(
        cohort="TCGA-SKCM",
        gene_symbol="PDCD1",
        filters=AnalysisFilters(sample_population="metastatic"),
    )
    assert skcm.filters.sample_population == "metastatic"
