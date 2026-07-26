from __future__ import annotations

import importlib.util
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "verify_reproducibility_bundle.py"
SPEC = importlib.util.spec_from_file_location("verify_reproducibility_bundle", MODULE_PATH)
assert SPEC is not None
verifier = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(verifier)


def test_recompute_zscore_from_audited_components() -> None:
    provenance = {
        "method": "zscore",
        "weight_denominator": 2.0,
        "components": [
            {
                "resolved_symbol": "A",
                "weight": 1.0,
                "standardization": {
                    "center": 2.0,
                    "sample_standard_deviation": 1.0,
                },
                "selected_values": [
                    {"sample_barcode": "S1", "expression_value": 1.0},
                    {"sample_barcode": "S2", "expression_value": 3.0},
                ],
            },
            {
                "resolved_symbol": "B",
                "weight": 1.0,
                "standardization": {
                    "center": 5.0,
                    "sample_standard_deviation": 2.0,
                },
                "selected_values": [
                    {"sample_barcode": "S1", "expression_value": 3.0},
                    {"sample_barcode": "S2", "expression_value": 7.0},
                ],
            },
        ],
    }

    assert verifier.recompute_scores(provenance) == {
        "S1": -1.0,
        "S2": 1.0,
    }


def test_audit_v2_reproducibility_payload_binds_data_and_scoring() -> None:
    scoring = {"method": "single", "components": [{"resolved_symbol": "A"}]}
    report = {
        "schema_version": "tcga-trace-analysis-audit-v2",
        "data": {
            "data_dates": {"data_through_date": "2026-01-01"},
            "provenance": {"expression_sha256": "abc"},
        },
        "analysis_design": {"scoring_provenance": scoring},
        "results": {"n_patients": 10},
    }

    payload = verifier.reproducibility_payload_from_report(
        report,
        request_payload={"cohort": "TCGA-TEST"},
        patient_digest="records",
    )

    assert payload["data_provenance"] == {"expression_sha256": "abc"}
    assert payload["scoring_provenance_sha256"] == verifier.stable_hash(scoring)


def test_audit_v3_reproducibility_payload_matches_generator_contract() -> None:
    scoring = {"method": "single", "components": [{"resolved_symbol": "A"}]}
    continuous_records = [
        {
            "patient_id": "TCGA-00-0001",
            "time": 120,
            "event": 1,
            "expression_value": 2.5,
        }
    ]
    report = {
        "schema_version": "tcga-trace-analysis-audit-v3",
        "data": {
            "data_dates": {"data_through_date": "2026-01-01"},
            "provenance": {"expression_sha256": "abc"},
        },
        "analysis_design": {"scoring_provenance": scoring},
        "cohort_selection": {
            "continuous_patient_records": continuous_records,
        },
        "results": {"n_patients": 10},
    }

    payload = verifier.reproducibility_payload_from_report(
        report,
        request_payload={"cohort": "TCGA-TEST"},
        patient_digest="stratified-records",
    )

    assert payload == {
        "request": {"cohort": "TCGA-TEST"},
        "data_dates": {"data_through_date": "2026-01-01"},
        "data_provenance": {"expression_sha256": "abc"},
        "scoring_provenance_sha256": verifier.stable_hash(scoring),
        "record_digest": "stratified-records",
        "continuous_record_digest": verifier.stable_hash(
            {"records": continuous_records}
        ),
        "core_results": {"n_patients": 10},
    }


def test_quantity_aware_comparison_keeps_counts_exact() -> None:
    comparison = verifier.compare_values_detailed(
        {"n_patients": 10},
        {"n_patients": 10.000000001},
    )

    assert comparison["differences"]
    assert comparison["observed_errors"]["exact"]["comparisons"] == 1


def test_quantity_aware_comparison_uses_relative_effect_tolerance() -> None:
    comparison = verifier.compare_values_detailed(
        {"hazard_ratio": 2.0},
        {"hazard_ratio": 2.000000015},
    )

    assert comparison["differences"] == []
    effect = comparison["observed_errors"]["effect"]
    assert effect["comparisons"] == 1
    assert effect["max_absolute_error"] > 0
    assert effect["max_relative_path"] == "$.hazard_ratio"


def test_quantity_aware_comparison_classifies_p_values_separately() -> None:
    comparison = verifier.compare_values_detailed(
        {"p_value": 0.05},
        {"p_value": 0.05000001},
    )

    assert comparison["differences"] == []
    assert comparison["observed_errors"]["probability"]["comparisons"] == 1
    assert comparison["policy_version"].endswith("-v1")


def test_roundtrip_uses_bundle_frozen_engine_by_default(tmp_path: Path) -> None:
    bundle = tmp_path / "artifacts" / "case-a"

    assert verifier.select_roundtrip_r_script(bundle, None) == (
        bundle / "km_analysis.R"
    )
    assert verifier.select_container_roundtrip_r_script(
        Path("case-a"),
        container_artifact_dir="/app/artifacts",
        override="",
    ) == "/app/artifacts/case-a/km_analysis.R"


def test_roundtrip_engine_override_is_explicit(tmp_path: Path) -> None:
    override = tmp_path / "current-engine.R"

    assert verifier.select_roundtrip_r_script(tmp_path, override) == override
    assert verifier.select_container_roundtrip_r_script(
        Path("case-a"),
        container_artifact_dir="/app/artifacts",
        override="/app/scripts/km_analysis.R",
    ) == "/app/scripts/km_analysis.R"
