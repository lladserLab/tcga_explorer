import json
import math
from pathlib import Path
import shutil
import subprocess

import pytest


def test_pancancer_r_script_recovers_exact_common_scale_coefficient(
    tmp_path: Path,
) -> None:
    rscript = shutil.which("Rscript")
    if rscript is None:
        pytest.skip("Rscript is not available in this test environment.")

    script_path = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "pancancer_cox_scan.R"
    )
    output_path = tmp_path / "output.json"
    records = [
        {
            "patient_id": f"P{index:03d}",
            "sample_barcode": f"P{index:03d}-01A",
            "expression_value": ((index * 7) % 17) / 3,
            "time_days": 100 + ((index * 137) % 1100),
            "event": 0 if index % 3 == 0 else 1,
            "sample_type": "Primary Tumor",
            "stage": ["Stage I", "Stage II", "Stage III", "Stage IV"][
                index % 4
            ],
            "grade": ["G1", "G2", "G3"][index % 3],
            "gender": "female" if index % 2 else "male",
            "race": "not reported",
            "age_at_index": 35 + index,
        }
        for index in range(40)
    ]
    payload = {
        "scan_id": "common-scale-integration-test",
        "min_patients": 10,
        "min_events": 5,
        "request": {},
        "cohorts": [
            {
                "cohort": "TCGA-TEST",
                "cohort_label": "Synthetic test cohort",
                "endpoint": "OS",
                "endpoint_label": "Overall survival",
                "endpoint_source": "synthetic",
                "records": records,
            }
        ],
        "output_path": str(output_path),
    }
    input_path = tmp_path / "input.json"
    input_path.write_text(json.dumps(payload), encoding="utf-8")

    completed = subprocess.run(
        [rscript, str(script_path), str(input_path)],
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert completed.returncode == 0, completed.stderr or completed.stdout
    row = json.loads(output_path.read_text(encoding="utf-8"))["results"][0]
    assert row["status"] == "completed"
    assert row["common_scale_log_hr"] == pytest.approx(
        row["log_hr"] / row["expression_sd"],
        rel=1e-12,
        abs=1e-12,
    )
    assert row["common_scale_standard_error"] == pytest.approx(
        row["standard_error"] / row["expression_sd"],
        rel=1e-12,
        abs=1e-12,
    )
    assert row["common_scale_hazard_ratio"] == pytest.approx(
        math.exp(row["common_scale_log_hr"]),
        rel=1e-12,
    )
    assert row["common_scale_p_value"] == pytest.approx(
        row["p_value"],
        rel=1e-12,
        abs=1e-12,
    )
    assert "ph_p_value" in row
    assert "ph_global_p_value" in row
    assert row["time_varying_effect"]["split_days"] == pytest.approx(730.5)
    assert row["time_varying_effect"]["status"] in {
        "completed",
        "not_triggered",
        "not_evaluable",
        "skipped",
    }
