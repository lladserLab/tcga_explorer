from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


MODULE_PATH = (
    Path(__file__).resolve().parents[1] / "run_statistical_calibration.py"
)
SPEC = importlib.util.spec_from_file_location(
    "run_statistical_calibration",
    MODULE_PATH,
)
assert SPEC is not None
calibration = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(calibration)


def calibration_result() -> dict:
    summary = []
    for scenario in (
        "observed_null_permutation",
        "null",
        "linear_ph",
        "delayed_non_ph",
        "u_shaped_nonlinear",
    ):
        for metric in (
            "continuous_linear",
            "spline_nonlinearity",
            "marker_ph",
            "grouped_family_holm",
            "maxstat_naive",
            "maxstat_lau94",
            "median_logrank",
            "upper_quartile_logrank",
            "outer_quartiles_logrank",
            "median_cox",
            "median_rmst",
        ):
            summary.append(
                {
                    "scenario": scenario,
                    "metric": metric,
                    "rejected": 5,
                    "evaluable": 100,
                    "rate": 0.05,
                    "confidence_low": 0.02,
                    "confidence_high": 0.11,
                }
            )
    return {
        "schema_version": "tcga-trace-statistical-calibration-v2",
        "design": {
            "alpha": 0.05,
            "seed": 20260725,
            "permutation_replicates": 100,
            "simulation_replicates_per_scenario": 100,
            "simulation_n": 300,
        },
        "source": {
            "analysis_id": "analysis",
            "audit_reproducibility_hash": "audit-hash",
            "continuous_patient_records_sha256": "records-hash",
            "patients": 300,
            "events": 100,
            "tau": 1000,
        },
        "permutation_summary": [
            row
            for row in summary
            if row["scenario"] == "observed_null_permutation"
        ],
        "simulation_summary": [
            row
            for row in summary
            if row["scenario"] != "observed_null_permutation"
        ],
        "dependence": {
            "spearman_logrank_vs_cox": 0.99,
            "spearman_logrank_vs_rmst": 0.6,
            "spearman_cox_vs_rmst": 0.6,
            "all_three_nominal": {
                "rejected": 4,
                "evaluable": 100,
                "rate": 0.04,
                "confidence_low": 0.02,
                "confidence_high": 0.10,
            },
        },
    }


def test_validate_result_requires_complete_known_truth_design() -> None:
    result = calibration_result()
    design = {
        "alpha": 0.05,
        "seed": 20260725,
        "permutation_replicates": 100,
        "simulation_replicates": 100,
        "simulation_n": 300,
    }

    calibration.validate_result(result, design)

    result["simulation_summary"] = [
        row
        for row in result["simulation_summary"]
        if row["scenario"] != "delayed_non_ph"
    ]
    with pytest.raises(RuntimeError, match="scenarios are incomplete"):
        calibration.validate_result(result, design)


def test_latex_labels_naive_maxstat_as_selection_diagnostic(
    tmp_path: Path,
) -> None:
    path = tmp_path / "calibration.tex"

    calibration.write_latex(path, calibration_result())

    text = path.read_text(encoding="utf-8")
    assert "naive maxstat column" in text
    assert "only to expose bias" in text
    assert "Grouped Holm" in text
    assert "Linear-PH power" in text


def test_markdown_reports_power_and_null_interval_interpretation(
    tmp_path: Path,
) -> None:
    path = tmp_path / "summary.md"
    result = calibration_result()

    calibration.write_markdown(
        path,
        result,
        calibration.result_rows(result),
    )

    text = path.read_text(encoding="utf-8")
    assert "Linear-PH Association Power" in text
    assert "Outer quartiles" in text
    assert "Null Calibration Interpretation" in text
    assert "lack of grouped support is not evidence" in text


def test_result_rows_preserve_analysis_family() -> None:
    rows = calibration.result_rows(calibration_result())

    permutation = [
        row for row in rows if row["scenario"] == "observed_null_permutation"
    ]
    simulated = [row for row in rows if row["scenario"] == "linear_ph"]

    assert permutation
    assert all(row["analysis_type"] == "permutation" for row in permutation)
    assert simulated
    assert all(row["analysis_type"] == "simulation" for row in simulated)


def test_check_existing_outputs_detects_tampered_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(calibration, "ROOT", tmp_path)
    output = tmp_path / "calibration"
    output.mkdir()
    design_path = output / "calibration_design.json"
    result_path = output / "calibration_results.raw.json"
    summary_path = output / "summary.md"
    manifest_path = output / "manifest.json"
    design = {
        "alpha": 0.05,
        "seed": 20260725,
        "permutation_replicates": 100,
        "simulation_replicates": 100,
        "simulation_n": 300,
    }
    calibration.write_json(design_path, design)
    calibration.write_json(result_path, calibration_result())
    summary_path.write_text("calibrated\n", encoding="utf-8")
    calibration.write_manifest(
        manifest_path,
        files=[design_path, result_path, summary_path],
        result=calibration_result(),
    )

    calibration.check_existing_outputs(
        design_path=design_path,
        result_path=result_path,
        manifest_path=manifest_path,
    )

    summary_path.write_text("tampered!!\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="checksum mismatch"):
        calibration.check_existing_outputs(
            design_path=design_path,
            result_path=result_path,
            manifest_path=manifest_path,
        )
