from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
RUNNER = (
    ROOT
    / "scripts"
    / "publication"
    / "run_camera_operating_characteristics.py"
)
ARTIFACT = (
    ROOT
    / "docs"
    / "publication"
    / "benchmark"
    / "major_revision_2026-08-26"
    / "camera_operating_characteristics"
)


def load_runner():
    spec = importlib.util.spec_from_file_location(
        "trace_camera_operating_characteristics", RUNNER
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fixture_pathways() -> list[dict[str, str]]:
    return [
        {
            "selection_id": "P01",
            "pathway": "PATH_A",
            "member_genes": "A;B;C;D;E;F;G;H",
        },
        {
            "selection_id": "P02",
            "pathway": "PATH_B",
            "member_genes": "J;K;L;M",
        },
    ]


def test_active_gene_selection_is_deterministic_and_label_independent() -> None:
    runner = load_runner()

    first = runner.freeze_injections(fixture_pathways())
    second = runner.freeze_injections(list(reversed(fixture_pathways())))

    by_key_first = {
        (row["pathway"], row["active_fraction"]): row for row in first
    }
    by_key_second = {
        (row["pathway"], row["active_fraction"]): row for row in second
    }
    assert by_key_first == by_key_second
    assert by_key_first[("PATH_A", "0.25")]["active_gene_count"] == 2
    assert by_key_first[("PATH_A", "1.00")]["active_gene_count"] == 8
    assert "label" not in " ".join(by_key_first[("PATH_A", "0.25")])


def test_power_tasks_cross_the_frozen_grid_exactly() -> None:
    runner = load_runner()
    tasks = runner.build_power_tasks(fixture_pathways(), replicates=7)

    assert len(tasks) == (
        len(fixture_pathways())
        * len(runner.POWER_EFFECT_SDS)
        * len(runner.POWER_ACTIVE_FRACTIONS)
        * 7
    )
    assert len({row["task_id"] for row in tasks}) == len(tasks)
    assert {float(row["effect_sd"]) for row in tasks} == set(
        runner.POWER_EFFECT_SDS
    )
    assert {float(row["active_fraction"]) for row in tasks} == set(
        runner.POWER_ACTIVE_FRACTIONS
    )
    assert {int(row["replicate"]) for row in tasks} == set(range(1, 8))


def test_fixed_null_tasks_are_an_ordered_complete_prefix() -> None:
    runner = load_runner()
    tasks = runner.build_fixed_null_tasks(replicates=4)

    assert tasks == [
        {
            "task_id": f"N{replicate:04d}",
            "replicate": replicate,
            "pathway": "",
            "effect_sd": "0.00",
            "active_fraction": "0.00",
        }
        for replicate in range(1, 5)
    ]


def test_checkpoint_merge_requires_every_task_mode_pair(tmp_path: Path) -> None:
    runner = load_runner()
    tasks = [
        {"task_id": "P000001"},
        {"task_id": "P000002"},
    ]
    modes = ("estimated_per_set", "fixed_0_01")
    rows = [
        {"task_id": task["task_id"], "correlation_mode": mode}
        for task in reversed(tasks)
        for mode in reversed(modes)
    ]
    runner.write_csv(tmp_path / "checkpoint_worker_01.csv", rows[:2])
    runner.write_csv(tmp_path / "checkpoint_worker_02.csv", rows[2:])

    merged = runner.merge_checkpoint_rows(tmp_path, tasks, modes)

    assert [(row["task_id"], row["correlation_mode"]) for row in merged] == [
        ("P000001", "estimated_per_set"),
        ("P000001", "fixed_0_01"),
        ("P000002", "estimated_per_set"),
        ("P000002", "fixed_0_01"),
    ]
    (tmp_path / "checkpoint_worker_02.csv").unlink()
    with pytest.raises(RuntimeError, match="Incomplete checkpoint"):
        runner.merge_checkpoint_rows(tmp_path, tasks, modes)


def test_candidate_correlation_summary_uses_strict_threshold() -> None:
    runner = load_runner()
    rows = [
        {"all_sample_residual_correlation": value}
        for value in ("0.005", "0.010", "0.020", "0.040")
    ]

    summary = runner.summarize_candidate_correlations(rows, fixed_rho=0.01)

    assert summary["pathways"] == 4
    assert summary["pathways_above_fixed_rho"] == 2
    assert summary["proportion_above_fixed_rho"] == 0.5
    assert summary["median_residual_correlation"] == pytest.approx(0.015)
    assert summary["comparison"] == "strictly greater than fixed_rho"


def test_fixed_null_summary_uses_probability_of_any_rejection() -> None:
    runner = load_runner()
    rows = []
    for replicate, counts in enumerate(((0, 0, 0), (2, 3, 4), (0, 1, 2)), 1):
        rows.append(
            {
                "replicate": str(replicate),
                "rejections_q_le_0_05": str(counts[0]),
                "rejections_q_le_0_10": str(counts[1]),
                "rejections_q_le_0_25": str(counts[2]),
                "min_fdr": "0.1",
                "pathways_tested": "100",
                "camera_seconds": "0.01",
            }
        )

    summary = runner.summarize_fixed_null(rows, phase="fixture")

    assert summary["thresholds"]["q_le_0.05"][
        "probability_any_rejection"
    ] == pytest.approx(1 / 3)
    assert summary["thresholds"]["q_le_0.10"][
        "probability_any_rejection"
    ] == pytest.approx(2 / 3)
    assert summary["thresholds"]["q_le_0.25"][
        "replicates_with_any_rejection"
    ] == 2
    assert summary["thresholds"]["q_le_0.05"]["mean_rejections"] == pytest.approx(
        2 / 3
    )
    assert summary["minimum_fdr"] == pytest.approx(
        {"mean": 0.1, "median": 0.1, "minimum": 0.1}
    )
    assert summary["pathway_counts"] == [100]
    assert summary["mean_camera_seconds"] == pytest.approx(0.01)


def test_power_summary_preserves_conditions_and_pairs_camera_decisions() -> None:
    runner = load_runner()
    rows = []
    decisions = {
        "P000001": {"estimated_per_set": True, "fixed_0_01": True},
        "P000002": {"estimated_per_set": True, "fixed_0_01": False},
        "P000003": {"estimated_per_set": False, "fixed_0_01": True},
        "P000004": {"estimated_per_set": False, "fixed_0_01": False},
    }
    for replicate, (task_id, modes) in enumerate(decisions.items(), start=1):
        for mode, detected in modes.items():
            rows.append(
                {
                    "task_id": task_id,
                    "replicate": str(replicate),
                    "pathway": "PATH_A",
                    "selection_id": "P01",
                    "size_stratum": "small_15_49",
                    "correlation_stratum": "high_q75",
                    "size_used": "40",
                    "effect_sd": "0.40",
                    "active_fraction": "1.00",
                    "active_gene_count": "40",
                    "correlation_mode": mode,
                    "target_detected_q_le_0_05": str(detected).lower(),
                    "direction_correct": "true",
                    "target_p_value": "0.02" if detected else "0.20",
                    "target_fdr": "0.04" if detected else "0.40",
                    "target_rank_by_p": "2" if detected else "20",
                    "camera_seconds": "0.25",
                    "estimated_target_correlation": (
                        "0.08" if mode == "estimated_per_set" else ""
                    ),
                    "residual_covariance_max_abs_delta": "2e-14",
                    "pathways_tested": "3166",
                }
            )

    summary = runner.summarize_power(rows, phase="power_formal")

    assert summary["paired_tasks"] == 4
    assert summary["result_rows"] == 8
    assert summary["paired_target_decisions"] == {
        "both_detect": 1,
        "estimated_only": 1,
        "fixed_0_01_only": 1,
        "neither": 1,
    }
    assert summary["maximum_residual_covariance_absolute_delta"] == pytest.approx(
        2e-14
    )
    assert summary["pathway_counts"] == [3166]
    assert len(summary["conditions"]) == 2
    by_mode = {row["correlation_mode"]: row for row in summary["conditions"]}
    assert by_mode["estimated_per_set"]["target_detection_probability"] == 0.5
    assert by_mode["fixed_0_01"]["target_detection_probability"] == 0.5
    assert by_mode["estimated_per_set"][
        "mean_estimated_target_correlation"
    ] == pytest.approx(0.08)
    assert by_mode["fixed_0_01"]["mean_estimated_target_correlation"] is None


def test_results_markdown_reproduces_fixed_rho_diagnostic_language(
    tmp_path: Path,
) -> None:
    runner = load_runner()
    fixed_dir = tmp_path / "fixed_null_formal"
    fixed_dir.mkdir()
    runner.write_json(
        fixed_dir / "summary.json",
        {
            "thresholds": {
                "q_le_0.05": {
                    "replicates_with_any_rejection": 453,
                    "replicates": 500,
                    "probability_any_rejection": 0.906,
                    "wilson_95_confidence_interval": [0.877, 0.929],
                }
            },
            "candidate_correlation_context": {
                "fixed_rho": 0.01,
                "pathways": 3166,
                "pathways_above_fixed_rho": 3043,
                "proportion_above_fixed_rho": 3043 / 3166,
                "median_residual_correlation": 0.046031102004760155,
            },
        },
    )

    runner.write_results_markdown(tmp_path)
    text = (tmp_path / "RESULTS.md").read_text(encoding="utf-8")

    assert "3,043 (96.1%) exceeded 0.01" in text
    assert "false-family rate" in text
    assert "invalidates its target-detection proportions" in text


def test_frozen_design_and_completed_artifacts_keep_methods_separate() -> None:
    design_path = ARTIFACT / "preregistered_design.json"
    if not design_path.is_file():
        pytest.skip("Frozen CAMERA operating-characteristic artifact not generated.")
    design = json.loads(design_path.read_text(encoding="utf-8"))

    assert design["status"] == "frozen before pilot outcomes"
    assert design["pathway_selection"]["uses_labels"] is False
    assert design["pathway_selection"]["uses_outcomes"] is False
    assert design["methods"]["primary"].startswith("estimated_per_set")
    assert design["methods"]["sensitivity"].startswith("fixed_0_01")
    assert design["run_rule"]["formal_counts_will_not_change_after_pilot"] is True

    fixed_summary = ARTIFACT / "fixed_null_formal" / "summary.json"
    if fixed_summary.is_file():
        fixed = json.loads(fixed_summary.read_text(encoding="utf-8"))
        assert fixed["replicates"] == 500
        assert fixed["pathway_counts"] == [3166]
        context = fixed.get("candidate_correlation_context")
        if context is not None:
            assert context["pathways"] == 3166
            assert context["pathways_above_fixed_rho"] == 3043
            assert context["median_residual_correlation"] == pytest.approx(
                0.046031102004760155
            )

    power_summary = ARTIFACT / "power_formal" / "summary.json"
    if power_summary.is_file():
        power = json.loads(power_summary.read_text(encoding="utf-8"))
        assert power["paired_tasks"] == 4800
        assert power["result_rows"] == 9600
        assert power["pathway_counts"] == [3166]
        assert power["maximum_residual_covariance_absolute_delta"] < 1e-10
