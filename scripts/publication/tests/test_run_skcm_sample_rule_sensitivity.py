from __future__ import annotations

import csv
import importlib.util
import sys
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "run_skcm_sample_rule_sensitivity.py"
SPEC = importlib.util.spec_from_file_location("run_skcm_sample_rule_sensitivity", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_overview_rows_accepts_relative_output_directory(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    output_dir = Path("relative-output")
    for case in MODULE.CASES:
        summary_path = output_dir / case.label / "summary.csv"
        summary_path.parent.mkdir(parents=True)
        with summary_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=["analysis_id"])
            writer.writeheader()
            writer.writerow({"analysis_id": case.label})

    rows = MODULE.overview_rows(output_dir)

    assert [row["analysis_id"] for row in rows] == [case.label for case in MODULE.CASES]
    assert all(Path(row["summary_path"]).is_absolute() for row in rows)


def test_display_path_uses_project_relative_path_inside_repository() -> None:
    path = MODULE.ROOT / "docs" / "publication" / "benchmark" / "summary.csv"

    assert MODULE.display_path(path) == "docs/publication/benchmark/summary.csv"
