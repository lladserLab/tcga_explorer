import json
from pathlib import Path
import shutil
import subprocess

import pytest
from pydantic import ValidationError

from app.schemas import AnalysisRequest, CombinedSignatureAnalysisRequest, SignatureSpec


RSCRIPT = shutil.which("Rscript")


def test_analysis_request_accepts_and_deduplicates_adjustment_covariates() -> None:
    request = AnalysisRequest(
        cohort="TCGA-LIHC",
        gene_symbol="CDC20",
        adjustment_covariates=[
            "age_at_index",
            "stage",
            "age_at_index",
            "gender",
        ],
    )

    assert request.adjustment_covariates == [
        "age_at_index",
        "stage",
        "gender",
    ]


def test_combined_request_preserves_user_selected_adjustment() -> None:
    request = CombinedSignatureAnalysisRequest(
        cohort="TCGA-UVM",
        signature_a=SignatureSpec(gene_symbol="BAP1", signature_method="single"),
        signature_b=SignatureSpec(gene_symbol="PRAME", signature_method="single"),
        adjustment_covariates=["age_at_index", "stage"],
    )

    assert request.adjustment_covariates == ["age_at_index", "stage"]


def test_analysis_request_rejects_unimported_adjustment_field() -> None:
    with pytest.raises(ValidationError, match="adjustment_covariates"):
        AnalysisRequest(
            cohort="TCGA-LGG",
            gene_symbol="EMP3",
            adjustment_covariates=["idh_status"],
        )


def test_analysis_request_preserves_artifact_specific_plot_styles() -> None:
    request = AnalysisRequest(
        cohort="TCGA-LIHC",
        gene_symbol="CDC20",
        plot_style={
            "continuous": {
                "effect_color": "#6A3D9A",
                "reference_color": "#FF7F00",
                "show_title": True,
                "plot_title": "  Continuous CDC20 effect  ",
                "x_axis_title": "  CDC20 expression  ",
                "y_axis_title": "  Relative hazard  ",
            },
            "cox_forest": {
                "lower_hazard_color": "#1B9E77",
                "higher_hazard_color": "#D95F02",
                "reference_color": "#7570B3",
                "model_layout": "separate",
                "show_title": False,
                "plot_title": "   ",
                "univariable_plot_title": "  Univariable only  ",
                "multivariable_plot_title": "  Adjusted models only  ",
                "x_axis_title": "  Adjusted hazard ratio  ",
            },
        },
    )

    style = request.model_dump()["plot_style"]
    assert style["continuous"] == {
        "effect_color": "#6A3D9A",
        "reference_color": "#FF7F00",
        "show_title": True,
        "plot_title": "Continuous CDC20 effect",
        "x_axis_title": "CDC20 expression",
        "y_axis_title": "Relative hazard",
    }
    assert style["cox_forest"] == {
        "lower_hazard_color": "#1B9E77",
        "higher_hazard_color": "#D95F02",
        "reference_color": "#7570B3",
        "model_layout": "separate",
        "show_title": False,
        "plot_title": None,
        "univariable_plot_title": "Univariable only",
        "multivariable_plot_title": "Adjusted models only",
        "x_axis_title": "Adjusted hazard ratio",
    }


def test_analysis_request_defaults_to_combined_cox_forest() -> None:
    request = AnalysisRequest(
        cohort="TCGA-LIHC",
        gene_symbol="CDC20",
    )

    assert request.plot_style.cox_forest.model_layout == "combined"


@pytest.mark.parametrize(
    ("artifact", "field"),
    [
        ("continuous", "effect_color"),
        ("cox_forest", "higher_hazard_color"),
    ],
)
def test_analysis_request_rejects_invalid_artifact_color(
    artifact: str,
    field: str,
) -> None:
    with pytest.raises(ValidationError, match=field):
        AnalysisRequest(
            cohort="TCGA-LIHC",
            gene_symbol="CDC20",
            plot_style={artifact: {field: "not-a-color"}},
        )


@pytest.mark.skipif(RSCRIPT is None, reason="Rscript is not installed")
def test_km_analysis_fits_exact_user_selected_covariates(tmp_path: Path) -> None:
    script = Path(__file__).resolve().parents[1] / "scripts" / "km_analysis.R"
    output_path = tmp_path / "metrics.json"
    survival_svg_path = tmp_path / "survival.svg"
    continuous_svg_path = tmp_path / "continuous.svg"
    cox_svg_path = tmp_path / "cox.svg"
    cox_univariable_svg_path = tmp_path / "cox_univariable.svg"
    cox_multivariable_svg_path = tmp_path / "cox_multivariable.svg"
    records = []
    for index in range(60):
        group = "Low" if index < 30 else "High"
        record = {
            "patient_id": f"TCGA-TEST-{index:04d}",
            "sample_barcode": f"TCGA-TEST-{index:04d}-01A",
            "endpoint": "OS",
            "expression_value": 2.0 + (index * 0.07) + ((index % 5) * 0.03),
            "group": group,
            "time_days": 280 + ((index * 47) % 900) - (55 if group == "High" else 0),
            "event": 0 if index % 3 == 0 else 1,
            "sample_type": "Primary Tumor",
            "stage": f"Stage {['I', 'II', 'III', 'IV'][index % 4]}",
            "grade": f"G{1 + (index % 3)}",
            "gender": "female" if index % 2 == 0 else "male",
            "race": "white" if index % 4 else "asian",
            "age_at_index": 40 + (index % 36),
        }
        records.append(record)

    payload = {
        "cohort": "TCGA-TEST",
        "gene_symbol": "TEST1",
        "endpoint": "OS",
        "endpoint_label": "Overall survival",
        "expression_scale": "tpm",
        "expression_scale_label": "log2(TPM + 1)",
        "records": records,
        "continuous_records": records,
        "group_levels": ["Low", "High"],
        "adjustment_covariates": ["age_at_index", "gender"],
        "cutpoint_details": {"method": "median"},
        "show_confidence_interval": False,
        "show_risk_table": False,
        "render_png": False,
        "render_svg": True,
        "svg_path": str(survival_svg_path),
        "continuous_effect_svg_path": str(continuous_svg_path),
        "cox_forest_svg_path": str(cox_svg_path),
        "cox_univariable_svg_path": str(cox_univariable_svg_path),
        "cox_multivariable_svg_path": str(cox_multivariable_svg_path),
        "plot_style": {
            "show_grid": False,
            "continuous": {
                "effect_color": "#6A3D9A",
                "reference_color": "#FF7F00",
                "plot_title": "Custom continuous Cox",
                "x_axis_title": "Custom expression axis",
                "y_axis_title": "Custom relative hazard",
            },
            "cox_forest": {
                "lower_hazard_color": "#1B9E77",
                "higher_hazard_color": "#D95F02",
                "reference_color": "#7570B3",
                "model_layout": "separate",
                "plot_title": "Custom Cox models",
                "univariable_plot_title": "Custom univariable Cox",
                "multivariable_plot_title": "Custom multivariable Cox",
                "x_axis_title": "Custom hazard ratio axis",
            },
        },
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
    assert metrics["clinical_adjustment"] == {
        "status": "requested",
        "requested_covariates": ["age_at_index", "gender"],
        "label": "Age + GDC gender",
        "grouped_model": "user_adjusted",
        "continuous_model": "continuous_user_adjusted",
        "interaction_model": "signature_interaction_user_adjusted",
    }

    grouped = next(
        model for model in metrics["cox_models"] if model["model"] == "user_adjusted"
    )
    continuous = next(
        model
        for model in metrics["continuous_analysis"]["linear_models"]
        if model["model"] == "continuous_user_adjusted"
    )
    for model in (grouped, continuous):
        assert model["status"] == "completed"
        assert model["covariates"] == ["age_at_index_per_10y", "gender_factor"]
        assert model["n_patients"] == 60
        assert model["n_events"] == 40
        assert model["information_diagnostics"]["parameter_count"] == 3
        assert model["information_diagnostics"]["events_per_parameter"] == pytest.approx(
            40 / 3
        )
        assert model["time_varying_effect"]["split_days"] == pytest.approx(730.5)
        assert model["time_varying_effect"]["status"] in {
            "completed",
            "not_triggered",
            "not_evaluable",
            "skipped",
        }

    spline = metrics["continuous_analysis"]["spline"]
    assert spline["status"] == "completed"
    assert spline["n_events"] == 40
    assert spline["degrees_freedom"] == 3
    assert spline["events_per_parameter"] == pytest.approx(40 / 3)
    assert spline["information_diagnostics"]["status"] == "adequate"

    assert survival_svg_path.exists()
    assert continuous_svg_path.exists()
    assert cox_svg_path.exists()
    assert cox_univariable_svg_path.exists()
    assert cox_multivariable_svg_path.exists()
    continuous_svg = continuous_svg_path.read_text(encoding="utf-8").lower()
    cox_svg = cox_svg_path.read_text(encoding="utf-8").lower()
    cox_univariable_svg = cox_univariable_svg_path.read_text(
        encoding="utf-8"
    ).lower()
    cox_multivariable_svg = cox_multivariable_svg_path.read_text(
        encoding="utf-8"
    ).lower()
    assert "custom continuous cox" in continuous_svg
    assert "custom expression axis" in continuous_svg
    assert "custom relative hazard" in continuous_svg
    assert "#6a3d9a" in continuous_svg
    assert "#ff7f00" in continuous_svg
    assert "custom cox models" in cox_svg
    assert "custom hazard ratio axis" in cox_svg
    assert "custom univariable cox" in cox_univariable_svg
    assert "custom multivariable cox" in cox_multivariable_svg
    assert "user-adjusted" not in cox_univariable_svg
    assert "user-adjusted" in cox_multivariable_svg
    assert metrics["cox_forest_output"]["model_layout"] == "separate"
    assert (
        metrics["cox_forest_output"]["completed_univariable_model_count"]
        == 1
    )
    assert (
        metrics["cox_forest_output"]["completed_multivariable_model_count"]
        >= 1
    )
    completed_grouped_models = [
        model for model in metrics["cox_models"] if model["status"] == "completed"
    ]
    if any(model["hazard_ratio"] < 1 for model in completed_grouped_models):
        assert "#1b9e77" in cox_svg
    if any(model["hazard_ratio"] >= 1 for model in completed_grouped_models):
        assert "#d95f02" in cox_svg
    assert "#7570b3" in cox_svg


@pytest.mark.skipif(RSCRIPT is None, reason="Rscript is not installed")
def test_km_analysis_requires_30_events_for_spline(tmp_path: Path) -> None:
    script = Path(__file__).resolve().parents[1] / "scripts" / "km_analysis.R"
    output_path = tmp_path / "metrics.json"
    records = []
    for index in range(60):
        records.append(
            {
                "patient_id": f"TCGA-TEST-{index:04d}",
                "sample_barcode": f"TCGA-TEST-{index:04d}-01A",
                "endpoint": "OS",
                "expression_value": 2.0 + (index * 0.07) + ((index % 5) * 0.03),
                "group": "Low" if index < 30 else "High",
                "time_days": 280 + ((index * 47) % 900),
                "event": 1 if index < 29 else 0,
                "sample_type": "Primary Tumor",
                "stage": f"Stage {['I', 'II', 'III', 'IV'][index % 4]}",
                "grade": f"G{1 + (index % 3)}",
                "gender": "female" if index % 2 == 0 else "male",
                "race": "white" if index % 4 else "asian",
                "age_at_index": 40 + (index % 36),
            }
        )

    payload = {
        "cohort": "TCGA-TEST",
        "gene_symbol": "TEST1",
        "endpoint": "OS",
        "endpoint_label": "Overall survival",
        "expression_scale": "tpm",
        "expression_scale_label": "log2(TPM + 1)",
        "records": records,
        "continuous_records": records,
        "group_levels": ["Low", "High"],
        "adjustment_covariates": ["age_at_index"],
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
    spline = metrics["continuous_analysis"]["spline"]
    assert spline["status"] == "skipped"
    assert spline["n_events"] == 29
    assert spline["reason"] == (
        "Fewer than 30 events were available for the three-degree-of-freedom "
        "spline model."
    )
