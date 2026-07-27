import json
import math
from types import SimpleNamespace

import pytest

from app.analysis_notices import (
    DSS_COMPETING_RISK_MESSAGE,
    ZSCORE_TRANSPORTABILITY_MESSAGE,
)
from app.r_runner import (
    json_safe_value,
    normalize_maxstat_result,
    validate_maxstat_records,
    write_audit_report,
    write_methodology_txt,
    write_pancancer_artifacts,
)
from app.survival import SurvivalRecord


def _record(expression: float, event: int = 1) -> dict:
    return {
        "patient_id": f"P{expression}-{event}",
        "expression_value": expression,
        "os_time_days": 100.0,
        "os_event": event,
    }


def test_validate_maxstat_records_accepts_valid_candidate_split() -> None:
    records = [_record(float(value), event=value % 2) for value in range(1, 11)]

    validate_maxstat_records(records, minprop=0.15)


def test_validate_maxstat_records_rejects_no_candidate_between_minprop() -> None:
    records = [_record(1.0) for _ in range(9)] + [_record(2.0)]

    with pytest.raises(ValueError, match="eligible cutpoint"):
        validate_maxstat_records(records, minprop=0.15)


def test_validate_maxstat_records_rejects_no_events() -> None:
    records = [_record(float(value), event=0) for value in range(1, 11)]

    with pytest.raises(ValueError, match="survival event"):
        validate_maxstat_records(records, minprop=0.15)


def test_normalize_maxstat_result_preserves_raw_and_bounds_probability() -> None:
    normalized = normalize_maxstat_result(
        {
            "corrected_p_status": "completed",
            "corrected_p_value": 3.025,
        }
    )

    assert normalized["corrected_p_raw_value"] == 3.025
    assert normalized["corrected_p_value"] == 1.0
    assert normalized["corrected_p_clamped"] is True


def test_json_safe_value_replaces_non_finite_numbers() -> None:
    payload = {"median_survival_days": {"High_Low": math.nan, "Low_Low": 2601.0}}

    assert json_safe_value(payload) == {
        "median_survival_days": {"High_Low": None, "Low_Low": 2601.0}
    }


def test_write_audit_report_creates_json_html_and_not_reached_status(tmp_path) -> None:
    artifact = tmp_path / "plot.png"
    artifact.write_bytes(b"png")
    settings = SimpleNamespace(artifact_dir=tmp_path)
    record = SurvivalRecord(
        patient_id="TCGA-AA-0001",
        sample_barcode="TCGA-AA-0001-01A",
        endpoint="OS",
        expression_value=2.5,
        group="High",
        time_days=100.0,
        event=0,
        sample_type="Primary Tumor",
        stage="Stage II",
        grade="G2",
        gender="female",
        race="white",
        age_at_index=61.0,
    )

    audit = write_audit_report(
        settings=settings,
        analysis_id="analysis-1",
        request_payload={
            "cohort": "TCGA-KIRC",
            "gene_symbol": "CA9",
            "endpoint": "OS",
            "expression_scale": "log2_tpm",
            "cutpoint_method": "median",
            "pipeline_version": "test",
        },
        metrics={
            "n_patients": 1,
            "n_events": 0,
            "endpoint": "OS",
            "endpoint_label": "Overall survival",
            "endpoint_source": "tcga_cdr",
            "expression_scale": "log2_tpm",
            "expression_scale_label": "log2(TPM + 1)",
            "group_counts": {"High": 1},
            "event_counts": {"High": 0},
            "median_survival_days": {"High": None},
            "rmst": {
                "status": "completed",
                "method": "survRM2::rmst2",
                "tau_days": 100.0,
                "reference_group": "Low",
                "comparison_group": "High",
                "difference": {"estimate_days": 12.0, "p_value": 0.04},
            },
            "logrank_p_value": 1.0,
            "continuous_analysis": {
                "status": "completed",
                "linear_models": [
                    {
                        "model": "continuous_univariable",
                        "status": "completed",
                        "hazard_ratio": 1.1,
                    }
                ],
            },
            "cox_models": [],
            "cox_forest_output": {
                "model_layout": "separate",
                "completed_model_count": 1,
                "completed_univariable_model_count": 1,
                "completed_multivariable_model_count": 0,
            },
            "sample_selection": {"retained_patients": 1},
            "warnings": [],
        },
        records=[record],
        artifact_paths={"png": str(artifact)},
        continuous_records=[record],
        analysis_warnings=[],
        data_dates={"data_through_date": "2026-07-21T00:00:00+00:00"},
        scoring_provenance={
            "schema_version": "tcga-trace-scoring-provenance-v1",
            "method": "single",
            "components": [],
        },
        data_provenance={
            "schema_version": "tcga-trace-data-provenance-v1",
            "cohort": "TCGA-KIRC",
        },
    )

    assert audit["schema_version"] == "tcga-trace-analysis-audit-v4"
    assert audit["server_attestation"]["algorithm"] == "Ed25519"
    assert audit["continuous_patient_records_sha256"]
    assert audit["median_survival_status"]["High"]["status"] == "not_reached"
    report_text = (tmp_path / "analysis-1" / "audit_report.json").read_text()
    report = json.loads(report_text)
    assert "reproducibility_hash_definition" in report
    assert "integrity_scope" in report
    assert "Ed25519 server receipt" in report["integrity_scope"]["not_an_authenticity_proof"]
    assert report["server_attestation"]["status"] == "detached_receipt"
    assert "\"request\"" in report_text
    assert "scoring_provenance_sha256" in report_text
    assert "tcga-trace-data-provenance-v1" in report_text
    assert "rmst" in report_text
    assert "continuous_analysis" in report_text
    assert report["results"]["cox_forest_output"]["model_layout"] == "separate"
    assert "continuous_patient_records" in report["cohort_selection"]
    assert (tmp_path / "analysis-1" / "audit_report.json").exists()
    assert (tmp_path / "analysis-1" / "audit_report.html").exists()
    assert (tmp_path / "analysis-1" / "attestation_receipt.json").exists()


def test_zscore_dss_interpretation_is_in_audit_and_methodology(tmp_path) -> None:
    settings = SimpleNamespace(artifact_dir=tmp_path)
    artifact = tmp_path / "plot.png"
    artifact.write_bytes(b"png")
    record = SurvivalRecord(
        patient_id="TCGA-AA-0002",
        sample_barcode="TCGA-AA-0002-01A",
        endpoint="DSS",
        expression_value=0.25,
        group="High",
        time_days=250.0,
        event=1,
        sample_type="Primary Tumor",
        stage="Stage II",
        grade="G2",
        gender="female",
        race="white",
        age_at_index=61.0,
    )
    request = {
        "cohort": "TCGA-UVM",
        "gene_symbol": "BAP1, EZH2",
        "endpoint": "DSS",
        "expression_scale": "log2_tpm",
        "signature_method": "zscore",
        "signature_genes": [
            {"gene_symbol": "BAP1", "weight": 1.0},
            {"gene_symbol": "EZH2", "weight": 1.0},
        ],
        "cutpoint_method": "median",
        "pipeline_version": "test",
        "filters": {},
    }
    metrics = {
        "n_patients": 1,
        "n_events": 1,
        "endpoint": "DSS",
        "endpoint_label": "Disease-specific survival",
        "endpoint_source": "tcga_cdr",
        "expression_scale": "log2_tpm",
        "expression_scale_label": "log2(TPM + 1)",
        "signature": {"method": "zscore", "label": "BAP1 + EZH2"},
        "group_counts": {"High": 1},
        "event_counts": {"High": 1},
        "median_survival_days": {"High": 250.0},
        "cox_models": [],
        "warnings": [],
        "sample_selection": {"endpoint_source": "tcga_cdr"},
    }

    write_audit_report(
        settings=settings,
        analysis_id="zscore-dss",
        request_payload=request,
        metrics=metrics,
        records=[record],
        artifact_paths={"png": str(artifact)},
        analysis_warnings=[],
    )
    report = json.loads(
        (tmp_path / "zscore-dss" / "audit_report.json").read_text()
    )
    html = (tmp_path / "zscore-dss" / "audit_report.html").read_text()

    score_context = report["analysis_design"]["score_transportability"]
    endpoint_context = report["data"]["endpoint"]["estimand_context"]
    assert score_context["numerically_transportable_across_runs"] is False
    assert score_context["interpretation"] == ZSCORE_TRANSPORTABILITY_MESSAGE
    assert endpoint_context["fine_gray_provided"] is False
    assert endpoint_context["interpretation"] == DSS_COMPETING_RISK_MESSAGE
    assert ZSCORE_TRANSPORTABILITY_MESSAGE in report["quality"]["limitations"]
    assert DSS_COMPETING_RISK_MESSAGE in report["quality"]["limitations"]
    assert ZSCORE_TRANSPORTABILITY_MESSAGE in html
    assert "Fine-Gray" in html

    methodology_path = tmp_path / "zscore-dss-methodology.txt"
    write_methodology_txt(
        path=methodology_path,
        settings=settings,
        analysis_id="zscore-dss",
        cohort="TCGA-UVM",
        gene_symbol="BAP1, EZH2",
        endpoint="DSS",
        endpoint_label="Disease-specific survival",
        expression_scale="log2_tpm",
        expression_scale_label="log2(TPM + 1)",
        time_unit="days",
        cutpoint_method="median",
        cutpoint_details={"method": "median", "value": 0.0},
        group_levels=["Low", "High"],
        show_confidence_interval=False,
        show_risk_table=False,
        plot_style={},
        request_payload=request,
        metrics=metrics,
        analysis_warnings=[],
        data_dates={},
    )
    methodology = methodology_path.read_text()
    assert ZSCORE_TRANSPORTABILITY_MESSAGE in methodology
    assert DSS_COMPETING_RISK_MESSAGE in methodology


def test_completed_competing_risk_outputs_are_bound_into_audit_and_methods(
    tmp_path,
) -> None:
    settings = SimpleNamespace(artifact_dir=tmp_path)
    artifact = tmp_path / "cumulative_incidence.png"
    artifact.write_bytes(b"png")
    record = SurvivalRecord(
        patient_id="TCGA-AA-0003",
        sample_barcode="TCGA-AA-0003-01A",
        endpoint="DSS",
        expression_value=0.75,
        group="High",
        time_days=420.0,
        event=1,
        sample_type="Primary Tumor",
        stage="Stage III",
        grade="G3",
        gender="female",
        race="white",
        age_at_index=66.0,
        competing_risk_status=1,
        competing_event=0,
        competing_risk_source="TCGA-CDR ExtraEndpoints:DSS_cr",
    )
    request = {
        "cohort": "TCGA-UVM",
        "gene_symbol": "BAP1",
        "endpoint": "DSS",
        "expression_scale": "log2_tpm",
        "signature_method": "single",
        "cutpoint_method": "median",
        "pipeline_version": "test",
        "filters": {},
    }
    competing = {
        "applicable": True,
        "status": "completed",
        "coding": {
            "source": "TCGA-CDR Supplemental Table S1, ExtraEndpoints",
            "source_status_column": "DSS_cr",
            "status_codes": {
                "0": "censored",
                "1": "death from the index cancer",
                "2": "death from another cause",
            },
        },
        "cumulative_incidence": {
            "status": "completed",
            "gray_test": {"status": "completed", "p_value": 0.012},
        },
        "grouped_fine_gray_models": [
            {
                "model": "fine_gray_grouped_univariable",
                "status": "completed",
                "marker_terms": [
                    {
                        "contrast": "High vs Low",
                        "subdistribution_hazard_ratio": 1.8,
                    }
                ],
            }
        ],
        "continuous_fine_gray_models": [],
    }
    metrics = {
        "n_patients": 1,
        "n_events": 1,
        "endpoint": "DSS",
        "endpoint_label": "Disease-specific survival",
        "endpoint_source": "tcga_cdr",
        "expression_scale": "log2_tpm",
        "expression_scale_label": "log2(TPM + 1)",
        "signature": {"method": "single", "label": "BAP1"},
        "group_counts": {"High": 1},
        "event_counts": {"High": 1},
        "median_survival_days": {"High": 420.0},
        "cox_models": [],
        "warnings": [],
        "competing_risks": competing,
    }

    write_audit_report(
        settings=settings,
        analysis_id="completed-competing",
        request_payload=request,
        metrics=metrics,
        records=[record],
        artifact_paths={"cumulative_incidence_png": str(artifact)},
        analysis_warnings=[],
    )
    report = json.loads(
        (tmp_path / "completed-competing" / "audit_report.json").read_text()
    )
    context = report["data"]["endpoint"]["estimand_context"]
    assert context["cumulative_incidence_provided"] is True
    assert context["fine_gray_provided"] is True
    assert context["coding"]["source_status_column"] == "DSS_cr"
    assert report["results"]["competing_risks"]["status"] == "completed"

    methodology_path = tmp_path / "completed-competing-methodology.txt"
    write_methodology_txt(
        path=methodology_path,
        settings=settings,
        analysis_id="completed-competing",
        cohort="TCGA-UVM",
        gene_symbol="BAP1",
        endpoint="DSS",
        endpoint_label="Disease-specific survival",
        expression_scale="log2_tpm",
        expression_scale_label="log2(TPM + 1)",
        time_unit="days",
        cutpoint_method="median",
        cutpoint_details={"method": "median", "value": 0.0},
        group_levels=["Low", "High"],
        show_confidence_interval=False,
        show_risk_table=False,
        plot_style={},
        request_payload=request,
        metrics=metrics,
        analysis_warnings=[],
        data_dates={},
    )
    methodology = methodology_path.read_text()
    assert "cmprsk::cuminc" in methodology
    assert "completed Fine-Gray models: 1" in methodology
    assert "DSS_cr" in methodology


def test_write_pancancer_artifacts_exports_primary_and_sensitivity_rows(tmp_path) -> None:
    settings = SimpleNamespace(artifact_dir=tmp_path)
    request = {
        "gene_symbol": "BIRC5",
        "endpoint": "OS",
        "endpoint_mode": "same_endpoint",
        "expression_scale": "log2_tpm",
        "min_patients": 10,
        "min_events": 5,
        "fdr_threshold": 0.10,
        "filters": {},
        "pipeline_version": "pancancer-v2-test",
        "data_version": {"manifest": "test"},
    }
    prepared = [
        {
            "cohort": "TCGA-LUAD",
            "cohort_label": "Lung adenocarcinoma",
            "endpoint": "OS",
            "endpoint_label": "Overall survival",
            "endpoint_source": "tcga_cdr",
            "records": [
                {
                    "patient_id": "TCGA-AA-0001",
                    "sample_barcode": "TCGA-AA-0001-01A",
                    "expression_value": 2.5,
                    "time_days": 100.0,
                    "event": 1,
                    "sample_type": "Primary Tumor",
                    "stage": "Stage II",
                    "grade": "G2",
                    "gender": "female",
                    "race": "white",
                    "age_at_index": 61.0,
                }
            ],
        }
    ]
    cohort_result = {
        "cohort": "TCGA-LUAD",
        "status": "completed",
        "n_patients": 100,
        "n_events": 30,
        "expression_mean": 2.1,
        "expression_sd": 0.8,
        "hazard_ratio": 1.3,
        "common_scale_hazard_ratio": 1.39,
        "common_scale_hr_conf_low": 1.10,
        "common_scale_hr_conf_high": 1.76,
        "common_scale_log_hr": 0.329,
        "common_scale_standard_error": 0.12,
        "common_scale_p_value": 0.006,
        "common_scale_unit": "per +1 log2(TPM + 1)",
        "common_scale_eligible": True,
        "fdr": 0.03,
        "selected_adjusted_model": "stage_adjusted",
        "adjusted_status": "completed",
        "adjusted_n_patients": 80,
        "adjusted_n_events": 25,
        "adjusted_hazard_ratio": 1.2,
        "adjusted_common_scale_hazard_ratio": 1.26,
        "adjusted_common_scale_log_hr": 0.231,
        "adjusted_common_scale_standard_error": 0.11,
        "adjusted_fdr": 0.08,
        "clinical_sensitivity": "retained",
        "warnings": [],
        "cox_models": [],
    }
    result = {
        "pipeline_version": "pancancer-v2-test",
        "data_version": {"manifest": "test"},
        "gene_symbol": "BIRC5",
        "expression_scale_label": "log2(TPM + 1)",
        "effect_scale": {
            "cohort_display": {
                "unit": "per +1 within-cohort SD",
                "pooled": False,
            },
            "synthesis": {
                "unit": "per +1 log2(TPM + 1)",
                "eligible": True,
            },
        },
        "summary": {"completed": 1, "significant": 1},
        "meta_analysis": {"available": True},
        "clinical_sensitivity": {
            "available": True,
            "summary": {"evaluable": 1, "not_evaluable": 0},
            "notes": [],
        },
        "results": [cohort_result],
        "warnings": [],
    }

    audit = write_pancancer_artifacts(
        settings=settings,
        scan_id="pc_test",
        request_payload=request,
        prepared_cohorts=prepared,
        result_payload=result,
        r_software_versions={"R": "test", "survival": "test"},
    )

    scan_dir = tmp_path / "pancancer" / "pc_test"
    report = json.loads((scan_dir / "audit_report.json").read_text())
    assert audit["schema_version"] == "tcga-trace-pancancer-audit-v3"
    assert audit["server_attestation"]["algorithm"] == "Ed25519"
    assert report["data"]["patient_rows"] == 1
    assert report["results"]["cohort_results"][0]["adjusted_hazard_ratio"] == 1.2
    cohort_csv = (scan_dir / "cohort_results.csv").read_text()
    assert "selected_adjusted_model" in cohort_csv
    assert "common_scale_hazard_ratio" in cohort_csv
    assert "adjusted_common_scale_hazard_ratio" in cohort_csv
    assert "grade" in (scan_dir / "patient_records.csv").read_text()
    methodology = (scan_dir / "methodology.txt").read_text()
    assert "restricted maximum-likelihood" in methodology
    assert "Hartung-Knapp-Sidik-Jonkman" in methodology
    assert "DerSimonian" not in methodology
    assert report["results"]["effect_scale"]["synthesis"]["eligible"] is True
    assert "effect_scale" in report["analysis_design"]
    assert (scan_dir / "methodology.txt").exists()
    assert (scan_dir / "audit_report.html").exists()
    assert (scan_dir / "attestation_receipt.json").exists()


def test_pancancer_zscore_dss_context_reaches_all_exports(tmp_path) -> None:
    settings = SimpleNamespace(artifact_dir=tmp_path)
    request = {
        "gene_symbol": "BAP1, EZH2",
        "signature_method": "zscore",
        "endpoint": "DSS",
        "endpoint_mode": "same_endpoint",
        "expression_scale": "log2_tpm",
        "min_patients": 10,
        "min_events": 5,
        "fdr_threshold": 0.10,
        "filters": {},
    }
    prepared = [
        {
            "cohort": "TCGA-UVM",
            "endpoint": "DSS",
            "endpoint_label": "Disease-specific survival",
            "endpoint_source": "tcga_cdr",
            "records": [],
        }
    ]
    result = {
        "pipeline_version": "test",
        "data_version": {"manifest": "test"},
        "gene_symbol": "BAP1 + EZH2",
        "signature": {"method": "zscore"},
        "expression_scale_label": "log2(TPM + 1)",
        "effect_scale": {
            "cohort_display": {"unit": "per +1 within-cohort SD"},
            "synthesis": {"eligible": False},
        },
        "summary": {"completed": 1},
        "meta_analysis": {"available": False},
        "clinical_sensitivity": {"summary": {}},
        "results": [
            {
                "cohort": "TCGA-UVM",
                "endpoint": "DSS",
                "status": "completed",
            }
        ],
        "warnings": [
            ZSCORE_TRANSPORTABILITY_MESSAGE,
            DSS_COMPETING_RISK_MESSAGE,
        ],
    }

    write_pancancer_artifacts(
        settings=settings,
        scan_id="pc_context",
        request_payload=request,
        prepared_cohorts=prepared,
        result_payload=result,
    )

    scan_dir = tmp_path / "pancancer" / "pc_context"
    report = json.loads((scan_dir / "audit_report.json").read_text())
    methodology = (scan_dir / "methodology.txt").read_text()
    html = (scan_dir / "audit_report.html").read_text()
    assert report["data"]["actual_endpoints"] == ["DSS"]
    assert (
        report["analysis_design"]["score_transportability"][
            "numerically_transportable_across_runs"
        ]
        is False
    )
    assert (
        report["data"]["endpoint_estimand_contexts"]["DSS"][
            "fine_gray_provided"
        ]
        is False
    )
    assert ZSCORE_TRANSPORTABILITY_MESSAGE in methodology
    assert DSS_COMPETING_RISK_MESSAGE in methodology
    assert ZSCORE_TRANSPORTABILITY_MESSAGE in html
    assert DSS_COMPETING_RISK_MESSAGE in html
