from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
RUNNER = (
    ROOT
    / "scripts"
    / "publication"
    / "run_camera_multimatrix_null_calibration.py"
)


def load_runner():
    spec = importlib.util.spec_from_file_location(
        "trace_camera_multimatrix_null_calibration", RUNNER
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_matrix_selection_is_fixed_and_spans_three_sample_size_strata() -> None:
    runner = load_runner()

    assert [row["key"] for row in runner.MATRIX_SPECS] == [
        "luad_cas_n51",
        "luad_cptac_n208",
        "blca_uromol_n462",
    ]
    assert [row["expected_samples"] for row in runner.MATRIX_SPECS] == [51, 208, 462]
    assert [row["selection_stratum"] for row in runner.MATRIX_SPECS] == [
        "small",
        "medium",
        "large",
    ]
    assert len({row["master_seed"] for row in runner.MATRIX_SPECS}) == 3


def test_fixed_null_tasks_are_complete_and_ordered() -> None:
    runner = load_runner()

    tasks = runner.build_fixed_null_tasks(500)

    assert len(tasks) == 500
    assert tasks[0] == {"task_id": "N0001", "replicate": 1}
    assert tasks[-1] == {"task_id": "N0500", "replicate": 500}
    assert len({row["task_id"] for row in tasks}) == 500


def test_label_validation_requires_balanced_unique_in_range_positions() -> None:
    runner = load_runner()
    valid = [
        {
            "replicate": 1,
            "group_a_n": 6,
            "group_b_n": 5,
            "group_b_zero_based_positions": "0;2;4;6;8",
        }
    ]
    runner.validate_labels(valid, sample_count=11, replicates=1)

    duplicated = [{**valid[0], "group_b_zero_based_positions": "0;2;2;6;8"}]
    with pytest.raises(ValueError, match="missing or duplicate"):
        runner.validate_labels(duplicated, sample_count=11, replicates=1)

    out_of_range = [{**valid[0], "group_b_zero_based_positions": "0;2;4;6;11"}]
    with pytest.raises(ValueError, match="out-of-range"):
        runner.validate_labels(out_of_range, sample_count=11, replicates=1)


def _paired_rows() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    patterns = [
        ("N0001", 1, 0, 1),
        ("N0002", 2, 1, 1),
        ("N0003", 3, 0, 0),
    ]
    for task_id, replicate, estimated_rejections, fixed_rejections in patterns:
        for mode, rejections in (
            ("estimated_per_set", estimated_rejections),
            ("fixed_0_01", fixed_rejections),
        ):
            estimated = mode == "estimated_per_set"
            rows.append(
                {
                    "task_id": task_id,
                    "replicate": str(replicate),
                    "correlation_mode": mode,
                    "configured_correlation": "" if estimated else "0.01",
                    "group_a_n": "6",
                    "group_b_n": "5",
                    "pathways_tested": "100",
                    "min_fdr": "0.01" if rejections else "0.50",
                    "rejections_q_le_0_05": str(rejections),
                    "rejections_q_le_0_10": str(rejections),
                    "rejections_q_le_0_25": str(rejections),
                    "camera_correlation_mean": "0.03" if estimated else "",
                    "camera_correlation_median": "0.02" if estimated else "",
                    "camera_correlation_p05": "0.00" if estimated else "",
                    "camera_correlation_p95": "0.10" if estimated else "",
                    "camera_correlation_minimum": "-0.01" if estimated else "",
                    "camera_correlation_maximum": "0.20" if estimated else "",
                    "camera_correlation_mean_absolute": "0.04" if estimated else "",
                    "camera_correlation_above_0_01": "70" if estimated else "",
                    "camera_correlation_proportion_above_0_01": "0.70" if estimated else "",
                    "camera_seconds": "0.2",
                }
            )
    return rows


def test_summary_preserves_paired_decisions_and_monte_carlo_label(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = load_runner()
    monkeypatch.setattr(runner, "REPLICATES", 3)

    summary = runner.summarize_matrix_results(
        _paired_rows(),
        matrix_record={"key": "fixture", "label": "Fixture"},
    )

    estimated = summary["methods"]["estimated_per_set"]["thresholds"]["q_le_0.05"]
    fixed = summary["methods"]["fixed_0_01"]["thresholds"]["q_le_0.05"]
    assert estimated["probability_any_rejection"] == pytest.approx(1 / 3)
    assert fixed["probability_any_rejection"] == pytest.approx(2 / 3)
    assert "monte_carlo_wilson_95_interval" in estimated
    assert summary["paired_any_rejection_decisions"]["q_le_0.05"] == {
        "both": 1,
        "estimated_only": 0,
        "fixed_only": 1,
        "neither": 1,
    }
    correlation = summary["methods"]["estimated_per_set"][
        "estimated_correlation_across_replicates"
    ]
    assert correlation["camera_correlation_median"]["median"] == pytest.approx(0.02)


def test_checkpoint_merge_requires_both_modes_for_every_task(tmp_path: Path) -> None:
    runner = load_runner()
    tasks = runner.build_fixed_null_tasks(2)
    rows = [
        {"task_id": task["task_id"], "replicate": task["replicate"], "correlation_mode": mode}
        for task in tasks
        for mode in ("estimated_per_set", "fixed_0_01")
    ]
    runner.write_csv(tmp_path / "checkpoint_worker_01.csv", rows[:2])
    runner.write_csv(tmp_path / "checkpoint_worker_02.csv", rows[2:])

    merged = runner.merge_checkpoints(tmp_path, tasks)

    assert len(merged) == 4
    (tmp_path / "checkpoint_worker_02.csv").unlink()
    with pytest.raises(RuntimeError, match="Incomplete checkpoints"):
        runner.merge_checkpoints(tmp_path, tasks)


def test_legacy_checkpoint_is_incremental_and_rejects_duplicates(tmp_path: Path) -> None:
    runner = load_runner()
    checkpoint = tmp_path / "checkpoint.csv"
    fields = ("replicate", "min_q")
    runner._append_legacy_checkpoint(
        checkpoint, {"replicate": 2, "min_q": 0.3}, fieldnames=fields
    )
    runner._append_legacy_checkpoint(
        checkpoint, {"replicate": 1, "min_q": 0.2}, fieldnames=fields
    )
    assert runner._legacy_completed_replicates(checkpoint) == {1, 2}

    runner._append_legacy_checkpoint(
        checkpoint, {"replicate": 1, "min_q": 0.1}, fieldnames=fields
    )
    with pytest.raises(RuntimeError, match="duplicate"):
        runner._legacy_completed_replicates(checkpoint)
