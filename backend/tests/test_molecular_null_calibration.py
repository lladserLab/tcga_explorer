from __future__ import annotations

from array import array
import csv
import importlib.util
import json
import math
from pathlib import Path
import shutil
import subprocess
from types import SimpleNamespace

import pytest

from app.expression_comparison import run_expression_comparison_engine
from app.gsea import (
    ExpressionMatrix,
    MatrixGene,
    rank_expression_matrix,
    run_preranked_gsea,
)


ROOT = Path(__file__).resolve().parents[2]
CALIBRATION_PATH = (
    ROOT / "scripts" / "publication" / "run_molecular_null_calibration.py"
)
CAMERA_CALIBRATION_PATH = (
    ROOT / "scripts" / "publication" / "run_camera_null_calibration.py"
)
CROSS_PHASE_PATH = (
    ROOT / "scripts" / "publication" / "compare_molecular_null_phases.py"
)
EXPRESSION_R_PATH = (
    ROOT
    / "scripts"
    / "publication"
    / "expression_comparison_null_calibration.R"
)


def load_calibration_module():
    spec = importlib.util.spec_from_file_location(
        "trace_molecular_null_calibration",
        CALIBRATION_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_camera_calibration_module():
    spec = importlib.util.spec_from_file_location(
        "trace_camera_null_calibration",
        CAMERA_CALIBRATION_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_cross_phase_module():
    spec = importlib.util.spec_from_file_location(
        "trace_molecular_null_cross_phase",
        CROSS_PHASE_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_float_matrix(path: Path, rows: list[list[float]]) -> None:
    with path.open("wb") as handle:
        for row in rows:
            array("f", row).tofile(handle)


def test_outer_permutations_are_deterministic_and_preserve_group_sizes() -> None:
    calibration = load_calibration_module()
    first = calibration.build_permutations(
        sample_count=11,
        group_b_size=5,
        replicates=20,
        seed=17291,
    )
    second = calibration.build_permutations(
        sample_count=11,
        group_b_size=5,
        replicates=20,
        seed=17291,
    )

    assert first == second
    assert len(first) == 20
    for row in first:
        positions = calibration.parse_positions(
            row["group_b_zero_based_positions"]
        )
        assert len(positions) == 5
        assert len(set(positions)) == 5
        assert min(positions) >= 0
        assert max(positions) < 11
        assert row["group_a_n"] == 6
        assert row["group_b_n"] == 5


def test_wilson_and_threshold_summaries_include_zero_event_bounds() -> None:
    calibration = load_calibration_module()
    low, high = calibration.wilson_interval(0, 500)
    assert low == pytest.approx(0.0)
    assert high == pytest.approx(0.00762434, rel=1e-5)

    summary = calibration.summarize_threshold(
        [
            {"any": False, "count": 0},
            {"any": True, "count": 2},
            {"any": False, "count": 0},
        ],
        any_field="any",
        count_field="count",
    )
    assert summary["replicates"] == 3
    assert summary["replicates_with_any_rejection"] == 1
    assert summary["probability_any_rejection"] == pytest.approx(1 / 3)
    assert summary["rejections_per_replicate"]["maximum"] == 2


def test_camera_runner_consumes_frozen_permutation_prefix_without_rng(
    tmp_path: Path,
) -> None:
    calibration = load_camera_calibration_module()
    source = tmp_path / "outer_label_permutations.csv"
    rows = [
        {
            "replicate": 1,
            "group_a_n": 6,
            "group_b_n": 5,
            "group_b_zero_based_positions": "0;2;4;6;8",
        },
        {
            "replicate": 2,
            "group_a_n": 6,
            "group_b_n": 5,
            "group_b_zero_based_positions": "1;3;5;7;9",
        },
        {
            "replicate": 3,
            "group_a_n": 6,
            "group_b_n": 5,
            "group_b_zero_based_positions": "2;4;6;8;10",
        },
    ]
    calibration.write_csv(source, rows)

    observed = calibration.load_frozen_permutations(
        source,
        sample_count=11,
        replicates=2,
    )

    assert observed == rows[:2]
    assert not hasattr(calibration, "build_permutations")


def test_camera_runner_rejects_changed_or_invalid_frozen_labels(
    tmp_path: Path,
) -> None:
    calibration = load_camera_calibration_module()
    source = tmp_path / "invalid.csv"
    calibration.write_csv(
        source,
        [
            {
                "replicate": 1,
                "group_a_n": 6,
                "group_b_n": 5,
                "group_b_zero_based_positions": "0;2;2;6;12",
            }
        ],
    )

    with pytest.raises(ValueError, match="duplicate|out-of-range"):
        calibration.load_frozen_permutations(
            source,
            sample_count=11,
            replicates=1,
        )


def test_camera_summary_reports_familywise_null_rejection_probability() -> None:
    calibration = load_camera_calibration_module()
    rows = []
    for replicate, min_q in enumerate((0.01, 0.08, 0.60), start=1):
        row = {
            "replicate": replicate,
            "pathways_tested": 100,
            "min_q": min_q,
            "camera_correlation_mean": 0.02,
            "camera_correlation_median": 0.01,
            "camera_correlation_p05": 0.00,
            "camera_correlation_p95": 0.08,
            "camera_correlation_minimum": 0.00,
            "camera_correlation_maximum": 0.12,
            "camera_correlation_mean_absolute": 0.02,
            "camera_engine_seconds": 0.01,
            "camera_process_wall_seconds": 0.02,
            "replicate_wall_seconds": 0.03,
        }
        for threshold in calibration.Q_THRESHOLDS:
            suffix = calibration.q_suffix(threshold)
            count = int(min_q <= threshold)
            row[f"any_q_le_{suffix}"] = count > 0
            row[f"rejections_q_le_{suffix}"] = count
        rows.append(row)

    summary = calibration.summarize_camera(rows)

    assert summary["thresholds"]["q_le_0.05"][
        "probability_any_rejection"
    ] == pytest.approx(1 / 3)
    assert summary["thresholds"]["q_le_0.10"][
        "probability_any_rejection"
    ] == pytest.approx(2 / 3)
    assert summary["thresholds"]["q_le_0.25"][
        "replicates_with_any_rejection"
    ] == 2


def test_camera_worker_calls_production_preparation_and_inference(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calibration = load_camera_calibration_module()
    sample_ids = [f"S{index}" for index in range(10)]
    matrix = SimpleNamespace(sample_ids=sample_ids)
    observed: dict[str, object] = {}

    def fake_prepare(
        received_matrix,
        assignments,
        *,
        ranking_metric,
        camera_matrix_path,
    ):
        observed["matrix"] = received_matrix
        observed["assignments"] = assignments
        observed["ranking_metric"] = ranking_metric
        return [], {"genes_ranked": 100}, SimpleNamespace()

    def fake_camera(
        camera_matrix,
        *,
        gene_set_path,
        min_size,
        max_size,
        work_dir,
        r_script_path,
    ):
        observed["camera_matrix"] = camera_matrix
        observed["min_size"] = min_size
        observed["max_size"] = max_size
        return [
            {
                "pathway": "A",
                "p_value": 0.001,
                "fdr": 0.02,
                "camera_correlation": 0.10,
            },
            {
                "pathway": "B",
                "p_value": 0.4,
                "fdr": 0.4,
                "camera_correlation": 0.02,
            },
        ], {
            "complete_case_genes": 100,
            "pathways_tested": 2,
            "camera_engine_seconds": 0.01,
            "camera_process_wall_seconds": 0.02,
        }

    monkeypatch.setattr(calibration, "prepare_camera_expression_matrix", fake_prepare)
    monkeypatch.setattr(calibration, "run_camera_gene_set_test", fake_camera)
    calibration._CAMERA_CONTEXT.update(
        {
            "matrix": matrix,
            "gene_set_path": Path("go.gmt"),
            "camera_r_path": Path("camera.R"),
        }
    )

    result = calibration._camera_worker((1, "5;6;7;8;9"))

    assert observed["matrix"] is matrix
    assert observed["ranking_metric"] == "welch_t"
    assert observed["min_size"] == calibration.GSEA_MIN_SIZE
    assert observed["max_size"] == calibration.GSEA_MAX_SIZE
    assert observed["assignments"] == {
        sample_id: ("a" if index < 5 else "b")
        for index, sample_id in enumerate(sample_ids)
    }
    assert result["min_q"] == pytest.approx(0.02)
    assert result["rejections_q_le_0_05"] == 1


def test_cross_phase_comparison_requires_identical_frozen_prefix(
    tmp_path: Path,
) -> None:
    calibration = load_calibration_module()
    comparison = load_cross_phase_module()
    full_dir = tmp_path / "full"
    sensitivity_dir = tmp_path / "default_sensitivity"
    full_dir.mkdir()
    sensitivity_dir.mkdir()
    permutations = [
        {
            "replicate": index,
            "group_a_n": 6,
            "group_b_n": 5,
            "group_b_zero_based_positions": "0;2;4;6;8",
        }
        for index in (1, 2, 3)
    ]
    expression = [
        {"replicate": index, "welch_any_q_le_0_05": False}
        for index in (1, 2, 3)
    ]
    gsea = []
    for index, min_q in enumerate((0.01, 0.08, 0.5), start=1):
        row = {"replicate": index, "min_q": min_q}
        for threshold in comparison.Q_THRESHOLDS:
            row[f"any_q_le_{comparison.suffix(threshold)}"] = min_q <= threshold
        gsea.append(row)
    calibration.write_csv(full_dir / "outer_label_permutations.csv", permutations)
    calibration.write_csv(
        sensitivity_dir / "outer_label_permutations.csv", permutations[:2]
    )
    calibration.write_csv(full_dir / "expression_replicates.csv", expression)
    calibration.write_csv(
        sensitivity_dir / "expression_replicates.csv", expression[:2]
    )
    calibration.write_csv(full_dir / "gsea_replicates.csv", gsea)
    calibration.write_csv(
        sensitivity_dir / "gsea_replicates.csv", gsea[:2]
    )

    payload = comparison.compare(tmp_path)

    assert payload["paired_outer_replicates"] == 2
    assert payload["identity_checks"][
        "sensitivity_labels_equal_full_ordered_prefix"
    ] is True
    assert payload["comparison"]["threshold_event_agreement"]["q_le_0.05"][
        "paired_agreement"
    ] == 1.0


def test_gsea_calibration_wrapper_calls_exact_production_core(tmp_path: Path) -> None:
    calibration = load_calibration_module()
    sample_ids = [f"S{index}" for index in range(10)]
    rows = [
        [float((gene * 3 + sample) % 11) for sample in range(10)]
        for gene in range(60)
    ]
    matrix_path = tmp_path / "matrix.float32le.bin"
    write_float_matrix(matrix_path, rows)
    matrix = ExpressionMatrix(
        path=matrix_path,
        sample_ids=sample_ids,
        genes=[MatrixGene(f"G{index:03d}", index) for index in range(60)],
        dtype="float32",
        byte_order="little",
        expression_scale="fixture",
        expression_scale_label="fixture",
        source_sha256=None,
    )
    assignments = {
        sample_id: ("a" if index < 5 else "b")
        for index, sample_id in enumerate(sample_ids)
    }
    pathways = [
        {
            "name": "PATH_A",
            "description": "A",
            "genes": [f"G{index:03d}" for index in range(0, 20)],
        },
        {
            "name": "PATH_B",
            "description": "B",
            "genes": [f"G{index:03d}" for index in range(20, 40)],
        },
        {
            "name": "PATH_C",
            "description": "C",
            "genes": [f"G{index:03d}" for index in range(40, 60)],
        },
    ]

    ranked, _ = rank_expression_matrix(
        matrix,
        assignments,
        ranking_metric="welch_t",
    )
    direct, _ = run_preranked_gsea(
        ranked,
        pathways,
        min_size=15,
        max_size=500,
        permutations=100,
        seed=17291,
    )
    wrapped = calibration.gsea_metrics_from_assignments(
        matrix,
        pathways,
        assignments,
        permutations=100,
        seed=17291,
    )

    q_values = [float(row["fdr"]) for row in direct]
    assert wrapped["min_q"] == min(q_values)
    assert wrapped["pathways_tested"] == len(direct)
    for threshold in calibration.Q_THRESHOLDS:
        suffix = calibration.q_suffix(threshold)
        expected = sum(value <= threshold for value in q_values)
        assert wrapped[f"rejections_q_le_{suffix}"] == expected
        assert wrapped[f"any_q_le_{suffix}"] is (expected > 0)


@pytest.mark.skipif(shutil.which("Rscript") is None, reason="Rscript unavailable")
def test_expression_batch_engine_matches_production_p_and_q_values(
    tmp_path: Path,
) -> None:
    calibration = load_calibration_module()
    sample_ids = [f"S{index}" for index in range(10)]
    values_by_gene = {
        "UP": [1, 2, 2, 3, 4, 7, 8, 8, 9, 10],
        "DOWN": [10, 9, 9, 8, 7, 4, 3, 3, 2, 1],
        "MIXED": [1, 5, 2, 7, 3, 6, 4, 8, 5, 9],
        "CONSTANT": [2] * 10,
    }
    value_rows = []
    panel_rows = []
    for row_number, (gene, values) in enumerate(values_by_gene.items()):
        for sample_index, (sample_id, value) in enumerate(
            zip(sample_ids, values, strict=True)
        ):
            group_key = "a" if sample_index < 5 else "b"
            value_rows.append(
                {
                    "patient_id": f"P-{sample_id}",
                    "sample_barcode": sample_id,
                    "gene_symbol": gene,
                    "group_key": group_key,
                    "group_label": group_key.upper(),
                    "expression_value": value,
                }
            )
            panel_rows.append(
                {
                    "gene_symbol": gene,
                    "row_number": row_number,
                    "sample_index_zero_based": sample_index,
                    "sample_id": sample_id,
                    "expression_value": value,
                }
            )
    assignment_rows = [
        {
            "patient_id": f"P-{sample_id}",
            "sample_barcode": sample_id,
            "analysis_included": True,
            "exclusion_reason": "",
            "group_key": "a" if index < 5 else "b",
            "group_label": "A" if index < 5 else "B",
        }
        for index, sample_id in enumerate(sample_ids)
    ]
    resolved_genes = [
        {
            "requested_symbol": gene,
            "gene_symbol": gene,
            "row_number": index,
            "resolution": "exact",
        }
        for index, gene in enumerate(values_by_gene)
    ]
    policies = {
        gene: {
            "inferential_status": "inferential",
            "included_in_multiplicity": True,
        }
        for gene in values_by_gene
    }
    production = run_expression_comparison_engine(
        tmp_path / "production",
        request_payload={"request": "parity-fixture"},
        value_rows=value_rows,
        assignment_rows=assignment_rows,
        resolved_genes=resolved_genes,
        gene_policies=policies,
        group_a_label="A",
        group_b_label="B",
        fdr_threshold=0.05,
        heatmap_max_samples=20,
        pipeline_version="parity-fixture-v1",
    )

    panel_path = tmp_path / "panel.csv"
    permutation_path = tmp_path / "permutations.csv"
    gene_output = tmp_path / "gene_output.csv"
    replicate_output = tmp_path / "replicate_output.csv"
    engine_output = tmp_path / "engine.json"
    calibration.write_csv(panel_path, panel_rows)
    calibration.write_csv(
        permutation_path,
        [
            {
                "replicate": 1,
                "group_a_n": 5,
                "group_b_n": 5,
                "group_b_zero_based_positions": "5;6;7;8;9",
            }
        ],
    )
    config_path = tmp_path / "config.json"
    calibration.write_json(
        config_path,
        {
            "panel_values_csv": str(panel_path),
            "permutations_csv": str(permutation_path),
            "replicate_output_csv": str(replicate_output),
            "gene_output_csv": str(gene_output),
            "engine_output_json": str(engine_output),
            "minimum_finite_samples_per_group": 5,
            "q_thresholds": [0.05, 0.10, 0.25],
            "contrast": "group_b_minus_group_a",
            "production_pipeline_version": "parity-fixture-v1",
            "production_reference_script": str(
                ROOT / "backend" / "scripts" / "expression_comparison.R"
            ),
        },
    )
    subprocess.run(
        ["Rscript", str(EXPRESSION_R_PATH), str(config_path)],
        check=True,
        capture_output=True,
        text=True,
    )
    with gene_output.open(newline="", encoding="utf-8") as handle:
        calibration_rows = {
            row["gene_symbol"]: row for row in csv.DictReader(handle)
        }
    production_rows = {
        row["gene_symbol"]: row for row in production["statistics"]
    }

    def nullable_number(value):
        if value in (None, ""):
            return None
        number = float(value)
        return number if math.isfinite(number) else None

    field_pairs = (
        ("welch_p_value", ("welch_t", "p_value")),
        ("welch_fdr", ("welch_t", "fdr")),
        ("mann_whitney_p_value", ("mann_whitney", "p_value")),
        ("mann_whitney_fdr", ("mann_whitney", "fdr")),
    )
    assert set(calibration_rows) == set(production_rows)
    for gene in production_rows:
        for calibration_field, production_path in field_pairs:
            expected = nullable_number(
                production_rows[gene][production_path[0]][production_path[1]]
            )
            observed = nullable_number(calibration_rows[gene][calibration_field])
            if expected is None:
                assert observed is None
            else:
                assert observed == pytest.approx(expected, rel=1e-12, abs=1e-14)
