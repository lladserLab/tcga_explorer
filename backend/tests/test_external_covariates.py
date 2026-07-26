from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.external_covariates import prepare_external_covariates
from app.r_runner import write_audit_report, write_methodology_txt
from app.schemas import AnalysisRequest, ExternalCovariateDataset
from app.survival import SurvivalRecord


RSCRIPT = shutil.which("Rscript")


def external_dataset_payload() -> dict:
    return {
        "schema_version": "tcga-trace-external-covariates-v1",
        "source_label": "Curated LGG annotations",
        "definitions": [
            {
                "name": "idh_status",
                "label": "IDH status",
                "value_type": "categorical",
                "levels": ["Wild type", "Mutant"],
                "reference_level": "Wild type",
            },
            {
                "name": "tumor_purity",
                "label": "Tumor purity",
                "value_type": "continuous",
                "unit": "proportion",
                "effect_unit": 0.1,
            },
            {
                "name": "molecular_risk",
                "label": "Molecular risk",
                "value_type": "ordinal",
                "levels": ["Low", "Intermediate", "High"],
            },
        ],
        "rows": [
            {
                "patient_id": "tcga-ab-0001",
                "values": {
                    "idh_status": "mutant",
                    "tumor_purity": "0.72",
                    "molecular_risk": "high",
                },
            },
            {
                "patient_id": "TCGA-AB-0002",
                "values": {
                    "idh_status": "Wild type",
                    "tumor_purity": None,
                    "molecular_risk": "Low",
                },
            },
            {
                "patient_id": "TCGA-ZZ-9999",
                "values": {
                    "idh_status": "N/A",
                    "tumor_purity": 0.55,
                    "molecular_risk": "Intermediate",
                },
            },
        ],
    }


def test_external_covariate_schema_canonicalizes_values_and_selection() -> None:
    request = AnalysisRequest(
        cohort="TCGA-LGG",
        gene_symbol="EMP3",
        external_covariates=external_dataset_payload(),
        external_adjustment_covariates=[
            "IDH_STATUS",
            "tumor_purity",
            "idh_status",
        ],
    )

    assert request.external_adjustment_covariates == [
        "idh_status",
        "tumor_purity",
    ]
    assert request.external_covariates is not None
    assert request.external_covariates.rows[0].patient_id == "TCGA-AB-0001"
    assert request.external_covariates.rows[0].values == {
        "idh_status": "Mutant",
        "tumor_purity": 0.72,
        "molecular_risk": "High",
    }
    assert request.external_covariates.rows[2].values["idh_status"] is None


@pytest.mark.parametrize(
    ("mutator", "message"),
    [
        (
            lambda payload: payload["rows"][0].update(
                {"patient_id": "LOCAL-PATIENT-1"}
            ),
            "exact TCGA participant",
        ),
        (
            lambda payload: payload["definitions"][0].update(
                {"reference_level": "Unknown"}
            ),
            "reference_level",
        ),
        (
            lambda payload: payload["rows"][0]["values"].update(
                {"idh_status": "Not declared"}
            ),
            "undeclared level",
        ),
        (
            lambda payload: payload["definitions"][0].update(
                {"name": "patient_id"}
            ),
            "reserved",
        ),
        (
            lambda payload: payload["definitions"][0].update(
                {
                    "levels": ["Wild type", "M" * 65],
                    "reference_level": "Wild type",
                }
            ),
            "64 characters",
        ),
    ],
)
def test_external_covariate_schema_rejects_ambiguous_inputs(
    mutator,
    message: str,
) -> None:
    payload = external_dataset_payload()
    mutator(payload)

    with pytest.raises(ValidationError, match=message):
        ExternalCovariateDataset(**payload)


def test_external_covariate_schema_rejects_duplicate_patients() -> None:
    payload = external_dataset_payload()
    payload["rows"].append(payload["rows"][0])

    with pytest.raises(ValidationError, match="unique patient_id"):
        ExternalCovariateDataset(**payload)


def test_external_selection_requires_a_matching_definition() -> None:
    with pytest.raises(ValidationError, match="not defined"):
        AnalysisRequest(
            cohort="TCGA-LGG",
            gene_symbol="EMP3",
            external_covariates=external_dataset_payload(),
            external_adjustment_covariates=["one_p_19_q"],
        )


def test_external_covariate_context_reports_matching_and_missingness() -> None:
    dataset = ExternalCovariateDataset(**external_dataset_payload())
    context = prepare_external_covariates(
        dataset,
        ["idh_status", "tumor_purity"],
        cohort_patient_ids={"TCGA-AB-0001", "TCGA-AB-0002", "TCGA-AB-0003"},
        analysis_patient_ids={"TCGA-AB-0001", "TCGA-AB-0002", "TCGA-AB-0003"},
    )

    assert context.qc["status"] == "selected"
    assert context.qc["cohort_matched_rows"] == 2
    assert context.qc["unmatched_rows"] == 1
    assert context.qc["unmatched_patient_ids"] == ["TCGA-ZZ-9999"]
    assert context.values_by_patient["TCGA-AB-0001"] == {
        "idh_status": "Mutant",
        "tumor_purity": 0.72,
    }
    assert context.values_by_patient["TCGA-AB-0003"] == {
        "idh_status": None,
        "tumor_purity": None,
    }
    purity_qc = next(
        item
        for item in context.qc["variables"]
        if item["name"] == "tumor_purity"
    )
    assert purity_qc["analysis_population_non_missing"] == 1
    assert purity_qc["analysis_population_missing"] == 2
    assert any("absent from the selected cohort" in item for item in context.warnings)


def test_external_covariates_are_explicit_in_audit_and_methodology(
    tmp_path: Path,
) -> None:
    request = AnalysisRequest(
        cohort="TCGA-LGG",
        gene_symbol="EMP3",
        adjustment_covariates=["age_at_index"],
        external_covariates=external_dataset_payload(),
        external_adjustment_covariates=["idh_status", "tumor_purity"],
    ).model_dump(mode="json")
    context = prepare_external_covariates(
        ExternalCovariateDataset(**external_dataset_payload()),
        ["idh_status", "tumor_purity"],
        cohort_patient_ids={"TCGA-AB-0001", "TCGA-AB-0002"},
        analysis_patient_ids={"TCGA-AB-0001", "TCGA-AB-0002"},
    )
    record = SurvivalRecord(
        patient_id="TCGA-AB-0001",
        sample_barcode="TCGA-AB-0001-01A",
        endpoint="OS",
        expression_value=2.0,
        group="High",
        time_days=500.0,
        event=1,
        sample_type="Primary Tumor",
        stage="Stage II",
        grade="G2",
        gender="female",
        race="white",
        age_at_index=60.0,
        external_covariates=context.values_by_patient["TCGA-AB-0001"],
    )
    metrics = {
        "n_patients": 2,
        "n_events": 1,
        "endpoint": "OS",
        "endpoint_label": "Overall survival",
        "endpoint_source": "tcga_cdr",
        "expression_scale": "log2_tpm",
        "expression_scale_label": "log2(TPM + 1)",
        "group_counts": {"High": 1, "Low": 1},
        "event_counts": {"High": 1, "Low": 0},
        "median_survival_days": {"High": 500.0, "Low": None},
        "cox_models": [],
        "warnings": [],
        "sample_selection": {"endpoint_source": "tcga_cdr"},
        "external_covariates": context.qc,
        "clinical_adjustment": {
            "status": "requested",
            "requested_covariates": ["age_at_index"],
            "requested_external_covariates": [
                "idh_status",
                "tumor_purity",
            ],
            "external_covariate_definitions": context.definitions,
        },
    }
    artifact = tmp_path / "plot.png"
    artifact.write_bytes(b"png")
    settings = SimpleNamespace(artifact_dir=tmp_path)

    write_audit_report(
        settings=settings,
        analysis_id="external-audit",
        request_payload=request,
        metrics=metrics,
        records=[record],
        artifact_paths={"png": str(artifact)},
    )
    report = json.loads(
        (tmp_path / "external-audit" / "audit_report.json").read_text()
    )
    external = report["analysis_design"]["external_covariates"]
    assert external["selected_covariates"] == ["idh_status", "tumor_purity"]
    assert external["quality_control"]["dataset_sha256"] == (
        context.qc["dataset_sha256"]
    )
    assert external["selected_definitions"][0]["reference_level"] == "Wild type"
    assert "user-supplied external covariates" in (
        report["quality"]["limitations"][-1]
    )
    audit_html = (
        tmp_path / "external-audit" / "audit_report.html"
    ).read_text()
    assert "External Covariates" in audit_html
    assert "per 0.1 proportion" in audit_html

    methodology_path = tmp_path / "external-methodology.txt"
    write_methodology_txt(
        path=methodology_path,
        settings=settings,
        analysis_id="external-audit",
        cohort="TCGA-LGG",
        gene_symbol="EMP3",
        endpoint="OS",
        endpoint_label="Overall survival",
        expression_scale="log2_tpm",
        expression_scale_label="log2(TPM + 1)",
        time_unit="days",
        cutpoint_method="median",
        cutpoint_details={"method": "median", "value": 2.0},
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
    assert "IDH status (idh_status)" in methodology
    assert "reference Wild type" in methodology
    assert "Tumor purity (tumor_purity)" in methodology
    assert "per 0.1 proportion" in methodology
    assert "does not account for treatment, tumor purity" not in methodology


@pytest.mark.skipif(RSCRIPT is None, reason="Rscript is not installed")
def test_external_covariates_fit_grouped_continuous_and_interaction_cox(
    tmp_path: Path,
) -> None:
    script = Path(__file__).resolve().parents[1] / "scripts" / "km_analysis.R"
    output_path = tmp_path / "metrics.json"
    definitions = [
        {
            "name": "idh_status",
            "label": "IDH status",
            "value_type": "categorical",
            "levels": ["Wild type", "Mutant"],
            "reference_level": "Wild type",
            "unit": "",
            "effect_unit": 1,
            "description": "",
        },
        {
            "name": "tumor_purity",
            "label": "Tumor purity",
            "value_type": "continuous",
            "levels": [],
            "reference_level": None,
            "unit": "proportion",
            "effect_unit": 0.1,
            "description": "",
        },
        {
            "name": "molecular_risk",
            "label": "Molecular risk",
            "value_type": "ordinal",
            "levels": ["Low", "Intermediate", "High"],
            "reference_level": None,
            "unit": "",
            "effect_unit": 1,
            "description": "",
        },
    ]
    records = []
    for index in range(72):
        group = "Low" if index < 36 else "High"
        purity = None if index % 10 == 0 else 0.45 + ((index % 20) * 0.02)
        records.append(
            {
                "patient_id": f"TCGA-AB-{index:04d}",
                "sample_barcode": f"TCGA-AB-{index:04d}-01A",
                "endpoint": "OS",
                "expression_value": 1.5 + index * 0.06 + (index % 4) * 0.04,
                "expression_value_a": 2.0 + index * 0.05 + (index % 5) * 0.03,
                "expression_value_b": 3.0 + (index % 13) * 0.11 + index * 0.01,
                "group": group,
                "group_a": group,
                "group_b": "Low" if index % 3 == 0 else "High",
                "time_days": 250 + ((index * 41) % 1_100) - (
                    45 if group == "High" else 0
                ),
                "event": 0 if index % 3 == 0 else 1,
                "sample_type": "Primary Tumor",
                "stage": f"Stage {['I', 'II', 'III', 'IV'][index % 4]}",
                "grade": f"G{1 + (index % 3)}",
                "gender": "female" if index % 2 == 0 else "male",
                "race": "white" if index % 4 else "asian",
                "age_at_index": 35 + (index % 45),
                "external_covariates": {
                    "idh_status": "Wild type" if index % 2 == 0 else "Mutant",
                    "tumor_purity": purity,
                    "molecular_risk": [
                        "Low",
                        "Intermediate",
                        "High",
                    ][index % 3],
                },
            }
        )

    payload = {
        "cohort": "TCGA-TEST",
        "gene_symbol": "TEST1",
        "endpoint": "OS",
        "endpoint_label": "Overall survival",
        "expression_scale": "log2_tpm",
        "expression_scale_label": "log2(TPM + 1)",
        "records": records,
        "continuous_records": records,
        "group_levels": ["Low", "High"],
        "adjustment_covariates": ["age_at_index"],
        "external_adjustment_covariates": [
            "idh_status",
            "tumor_purity",
            "molecular_risk",
        ],
        "external_covariate_definitions": definitions,
        "external_covariate_qc": {
            "status": "selected",
            "analysis_population_count": 72,
        },
        "cutpoint_details": {"method": "median"},
        "show_confidence_interval": False,
        "show_risk_table": False,
        "render_png": False,
        "render_svg": False,
        "output_path": str(output_path),
    }
    input_path = tmp_path / "input.json"
    input_path.write_text(json.dumps(payload), encoding="utf-8")

    completed = subprocess.run(
        [RSCRIPT, str(script), str(input_path)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    metrics = json.loads(output_path.read_text(encoding="utf-8"))
    adjustment = metrics["clinical_adjustment"]
    assert adjustment["status"] == "requested"
    assert adjustment["requested_covariates"] == ["age_at_index"]
    assert adjustment["requested_external_covariates"] == [
        "idh_status",
        "tumor_purity",
        "molecular_risk",
    ]
    assert adjustment["label"] == (
        "Age + IDH status + Tumor purity + Molecular risk"
    )
    expected_covariates = [
        "age_at_index_per_10y",
        "external_idh_status_factor",
        "external_tumor_purity_per_unit",
        "external_molecular_risk_ordinal",
    ]
    model_families = [
        metrics["cox_models"],
        metrics["continuous_analysis"]["linear_models"],
        metrics["signature_interaction_cox_models"],
    ]
    model_ids = [
        "user_adjusted",
        "continuous_user_adjusted",
        "signature_interaction_user_adjusted",
    ]
    for models, model_id in zip(model_families, model_ids, strict=True):
        model = next(item for item in models if item["model"] == model_id)
        assert model["status"] == "completed"
        assert model["covariates"] == expected_covariates
        assert model["n_patients"] == 64
        assert model["n_events"] > 5
        assert model["time_varying_effect"]["split_days"] == pytest.approx(730.5)
        assert model["time_varying_effect"]["status"] in {
            "completed",
            "not_triggered",
            "not_evaluable",
            "skipped",
        }
        assert (
            model["covariate_encoding"][
                "external_idh_status_factor"
            ]["reference_level"]
            == "Wild type"
        )
        assert (
            model["covariate_encoding"][
                "external_tumor_purity_per_unit"
            ]["effect_unit"]
            == pytest.approx(0.1)
        )
