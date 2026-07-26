from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest


SCRIPTS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_DIR))
MODULE_PATH = SCRIPTS_DIR / "run_single_gene_benchmark_suite.py"
SPEC = importlib.util.spec_from_file_location(
    "run_single_gene_benchmark_suite",
    MODULE_PATH,
)
assert SPEC is not None
suite = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = suite
SPEC.loader.exec_module(suite)


def test_frozen_scenario_registry_exactly_covers_suite_and_endpoint_parents() -> None:
    registry = suite.load_scenario_registry()

    suite.validate_scenario_registry(registry, suite.CASES)

    assert [entry["benchmark_id"] for entry in registry["scenarios"]] == [
        case.benchmark_id for case in suite.CASES
    ]
    sensitivities = [
        entry
        for entry in registry["scenarios"]
        if entry["endpoint_role"] == "sensitivity"
    ]
    assert [entry["benchmark_id"] for entry in sensitivities] == [
        "brca_mki67_pfi_cutpoints",
        "luad_cd274_pfi_cutpoints",
    ]
    assert all(entry["parent_benchmark_id"].endswith("_os_cutpoints") for entry in sensitivities)
    assert all(entry["literature_anchors"] for entry in registry["scenarios"])


def test_registry_validation_rejects_code_or_endpoint_drift() -> None:
    registry = suite.load_scenario_registry()
    changed = [
        suite.BenchmarkCase(
            case.benchmark_id,
            case.cohort,
            case.gene,
            "PFI" if case.benchmark_id == "lihc_cdc20_os_cutpoints" else case.endpoint,
            case.title,
            case.output_name,
            case.table_name,
        )
        for case in suite.CASES
    ]

    with pytest.raises(ValueError, match="differs from the frozen registry"):
        suite.validate_scenario_registry(registry, changed)


def test_registry_metadata_binds_exact_file_hash(
    tmp_path: Path,
    monkeypatch,
) -> None:
    case = suite.BenchmarkCase(
        "test_case",
        "TCGA-TEST",
        "GENE1",
        "OS",
        "Test",
        "test_output",
        "test.tex",
    )
    registry = {
        "schema_version": "tcga-trace-publication-scenario-registry-v1",
        "registry_version": "test-1",
        "status": "frozen_for_test",
        "selection_history": {"initial_panel_origin": "test"},
        "scope": {"scenario_count": 1},
        "endpoint_policy": {"registered_endpoint_sensitivities": []},
        "scenarios": [
            {
                "benchmark_id": "test_case",
                "cohort": "TCGA-TEST",
                "marker": "GENE1",
                "endpoint": "OS",
                "endpoint_role": "primary",
                "parent_benchmark_id": None,
                "benchmark_role": "test",
                "inclusion_rationale": "Test scenario.",
                "endpoint_rationale": "Test endpoint.",
                "literature_anchors": [
                    {
                        "citation_key": "test2026",
                        "doi": "10.0000/test",
                        "scope": "Test.",
                    }
                ],
            }
        ],
    }
    registry_path = tmp_path / "registry.json"
    registry_path.write_text(
        json.dumps(registry, sort_keys=True),
        encoding="utf-8",
    )
    benchmark_root = tmp_path / "benchmarks"
    metadata_path = benchmark_root / case.output_name / "benchmark_metadata.json"
    metadata_path.parent.mkdir(parents=True)
    metadata_path.write_text('{"benchmark_id": "test_case"}', encoding="utf-8")
    monkeypatch.setattr(suite, "BENCHMARK_ROOT", benchmark_root)

    suite.attach_scenario_registry_metadata(
        [case],
        registry,
        registry_path,
    )

    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    bound = metadata["scenario_registry"]
    assert bound["registry_version"] == "test-1"
    assert bound["scenario"]["benchmark_id"] == "test_case"
    assert bound["registry_sha256"] == hashlib.sha256(
        registry_path.read_bytes()
    ).hexdigest()


def test_maxstat_diagnostic_compares_like_for_like_contrasts(
    tmp_path: Path,
    monkeypatch,
) -> None:
    case = suite.BenchmarkCase(
        "test_case",
        "TCGA-TEST",
        "GENE1",
        "OS",
        "Test",
        "test_output",
        "test.tex",
    )
    monkeypatch.setattr(suite, "BENCHMARK_ROOT", tmp_path)
    output = tmp_path / case.output_name
    output.mkdir()
    fields = [
        "method",
        "status",
        "continuous_univariable_hr",
        "continuous_bh_p_value",
        "grouped_same_contrast_hr",
        "same_contrast_delta_sd",
        "continuous_implied_same_contrast_hr",
        "same_contrast_log_hr_amplification_ratio",
        "same_contrast_direction_concordant",
        "grouped_holm_p_value",
        "maxstat_corrected_p_value",
        "maxstat_corrected_p_raw_value",
        "maxstat_corrected_p_clamped",
        "same_contrast_status",
    ]
    rows = [
        {
            "method": "median",
            "status": "completed",
            "continuous_univariable_hr": 1.5,
            "continuous_bh_p_value": 0.01,
            "grouped_same_contrast_hr": 2.0,
            "same_contrast_delta_sd": 1.5,
            "continuous_implied_same_contrast_hr": 1.84,
            "same_contrast_log_hr_amplification_ratio": 1.14,
            "same_contrast_direction_concordant": True,
            "grouped_holm_p_value": 0.02,
            "same_contrast_status": "completed",
        },
        {
            "method": "maxstat",
            "status": "completed",
            "continuous_univariable_hr": 1.5,
            "continuous_bh_p_value": 0.01,
            "grouped_same_contrast_hr": 3.0,
            "same_contrast_delta_sd": 1.6,
            "continuous_implied_same_contrast_hr": 1.91,
            "same_contrast_log_hr_amplification_ratio": 1.70,
            "same_contrast_direction_concordant": True,
            "grouped_holm_p_value": 1.0,
            "maxstat_corrected_p_value": 1.0,
            "maxstat_corrected_p_raw_value": 2.4,
            "maxstat_corrected_p_clamped": True,
            "same_contrast_status": "completed",
        },
    ]
    with (output / "summary.csv").open(
        "w",
        newline="",
        encoding="utf-8",
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    diagnostic = suite.build_maxstat_selection_diagnostic([case])

    assert len(diagnostic) == 1
    assert diagnostic[0]["maxstat_lau94_p"] == 1.0
    assert diagnostic[0]["maxstat_lau94_raw_p"] == 2.4
    assert diagnostic[0]["maxstat_lau94_clamped"] is True
    assert diagnostic[0]["maxstat_to_median_abs_log_hr_ratio"] > 1


def test_main_evidence_matrix_preserves_all_four_grouped_rules(
    tmp_path: Path,
    monkeypatch,
) -> None:
    case = suite.BenchmarkCase(
        "test_case",
        "TCGA-TEST",
        "GENE1",
        "OS",
        "Test",
        "test_output",
        "test.tex",
    )
    monkeypatch.setattr(suite, "BENCHMARK_ROOT", tmp_path)
    monkeypatch.setattr(suite, "CASES", [case])
    output = tmp_path / case.output_name
    output.mkdir()
    fields = [
        "method",
        "status",
        "univariable_hr",
        "univariable_firth_hr",
        "grouped_holm_p_value",
    ]
    rows = [
        {
            "method": "maxstat",
            "status": "completed",
            "univariable_hr": "",
            "univariable_firth_hr": 0.20,
            "grouped_holm_p_value": 0.01,
        },
        {
            "method": "median",
            "status": "completed",
            "univariable_hr": 1.20,
            "univariable_firth_hr": "",
            "grouped_holm_p_value": 0.20,
        },
        {
            "method": "upper_quartile",
            "status": "completed",
            "univariable_hr": 1.40,
            "univariable_firth_hr": "",
            "grouped_holm_p_value": 0.03,
        },
        {
            "method": "upper_lower_quartile",
            "status": "completed",
            "univariable_hr": 0.80,
            "univariable_firth_hr": "",
            "grouped_holm_p_value": 1.0,
        },
    ]
    with (output / "summary.csv").open(
        "w",
        newline="",
        encoding="utf-8",
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    table_path = tmp_path / "main_evidence_matrix.tex"
    suite.write_main_evidence_latex(
        table_path,
        [
            {
                "benchmark_id": "test_case",
                "continuous_n_patients": 100,
                "continuous_n_events": 25,
                "continuous_univariable_hr": 1.1,
                "continuous_bh_p": 0.2,
                "spline_nonlinearity_bh_p": 0.01,
                "marker_ph_flagged_methods": 1,
                "global_ph_flagged_methods": 0,
                "low_information_methods": 1,
                "firth_methods": 1,
            }
        ],
        [
            {
                "benchmark_id": "test_case",
                "maxstat_to_median_abs_log_hr_ratio": 2.5,
            }
        ],
    )

    rendered = table_path.read_text(encoding="utf-8")
    assert "Max & Med & UQ & OQ" in rendered
    assert "P\\textsuperscript{F}" in rendered
    assert "\\textbf{H .03}" in rendered
    assert "NL, mPH 1, low 1, Firth 1, mixed dir." in rendered
    assert rendered.count("TEST GENE1 (OS)") == 1
