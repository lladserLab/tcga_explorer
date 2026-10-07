from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest


def _release(study: str, multiplier: float, offset: float = 0.0) -> dict:
    records = []
    for index in range(60):
        expression = (((index * 11) % 29) / 4.0) * multiplier + offset
        records.append(
            {
                "patient_id": f"{study}-P{index:03d}",
                "sample_id": f"{study}-S{index:03d}",
                "expression_value": expression,
                "time_days": 90 + ((index * 137) % 1600),
                "event": 0 if index % 4 == 0 else 1,
            }
        )
    return {
        "release_id": f"{study}-v1",
        "study_id": study,
        "study_cluster_id": study,
        "cancer_id": "BRCA",
        "endpoint": "OS",
        "time_origin": "diagnosis",
        "clinical_context": "primary untreated baseline",
        "model_family": "univariable_cox",
        "records": records,
    }


def _run(tmp_path: Path, releases: list[dict]) -> dict:
    rscript = shutil.which("Rscript")
    if rscript is None:
        pytest.skip("Rscript is not available in this test environment.")
    script_path = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "hierarchical_pancancer_cox.R"
    )
    output_path = tmp_path / "output.json"
    input_path = tmp_path / "input.json"
    input_path.write_text(
        json.dumps(
            {
                "scan_id": "hierarchical-iqr-test",
                "min_patients": 20,
                "min_events": 10,
                "min_censored": 5,
                "releases": releases,
                "output_path": str(output_path),
            }
        ),
        encoding="utf-8",
    )
    completed = subprocess.run(
        [rscript, str(script_path), str(input_path)],
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout
    return json.loads(output_path.read_text(encoding="utf-8"))


def test_release_cox_is_invariant_to_affine_expression_rescaling(
    tmp_path: Path,
) -> None:
    output = _run(
        tmp_path,
        [
            _release("study-a", 1.0),
            _release("study-b", 10.0, 37.0),
        ],
    )

    first, second = output["results"]
    assert first["status"] == "completed"
    assert second["status"] == "completed"
    assert first["effect_scale"] == "within_study_iqr"
    assert second["effect_scale"] == "within_study_iqr"
    assert second["expression_iqr"] == pytest.approx(
        10 * first["expression_iqr"], rel=1e-12
    )
    assert second["log_hr"] == pytest.approx(first["log_hr"], rel=1e-10)
    assert second["standard_error"] == pytest.approx(
        first["standard_error"], rel=1e-10
    )
    assert second["hazard_ratio"] == pytest.approx(
        first["hazard_ratio"], rel=1e-10
    )
    assert first["n_patients"] == 60
    assert first["n_events"] == 45
    assert first["n_censored"] == 15


def test_release_cox_refuses_duplicate_patient_records(tmp_path: Path) -> None:
    release = _release("study-a", 1.0)
    release["records"].append(dict(release["records"][0]))

    row = _run(tmp_path, [release])["results"][0]

    assert row["status"] == "skipped"
    assert row["code"] == "DUPLICATE_PATIENTS"
    assert "upstream sample selection" in row["reason"]


def test_release_cox_enforces_censoring_and_expression_information(
    tmp_path: Path,
) -> None:
    no_censoring = _release("all-events", 1.0)
    for record in no_censoring["records"]:
        record["event"] = 1
    no_iqr = _release("constant-expression", 1.0)
    for record in no_iqr["records"]:
        record["expression_value"] = 4.25

    censoring_row, iqr_row = _run(
        tmp_path,
        [no_censoring, no_iqr],
    )["results"]

    assert censoring_row["status"] == "skipped"
    assert censoring_row["code"] == "INSUFFICIENT_CENSORED"
    assert censoring_row["n_censored"] == 0
    assert iqr_row["status"] == "skipped"
    assert iqr_row["code"] == "NO_EXPRESSION_IQR"
