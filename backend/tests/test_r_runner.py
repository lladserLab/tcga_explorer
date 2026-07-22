import math
from types import SimpleNamespace

import pytest

from app.r_runner import json_safe_value, validate_maxstat_records, write_audit_report
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
            "cox_models": [],
            "sample_selection": {"retained_patients": 1},
            "warnings": [],
        },
        records=[record],
        artifact_paths={"png": str(artifact)},
        analysis_warnings=[],
        data_dates={"data_through_date": "2026-07-21T00:00:00+00:00"},
    )

    assert audit["schema_version"] == "tcga-explorer-analysis-audit-v1"
    assert audit["median_survival_status"]["High"]["status"] == "not_reached"
    assert "rmst" in (tmp_path / "analysis-1" / "audit_report.json").read_text()
    assert (tmp_path / "analysis-1" / "audit_report.json").exists()
    assert (tmp_path / "analysis-1" / "audit_report.html").exists()
