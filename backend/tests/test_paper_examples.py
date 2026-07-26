from pathlib import Path

from app.paper_examples import (
    _compact_time_varying_effect,
    _figure_artifact_path,
    _versioned_figure_url,
    build_paper_examples,
)
from app.pipeline_versions import PANCANCER_PIPELINE_VERSION


def test_figure_urls_change_when_artifact_changes(tmp_path):
    figure = tmp_path / "cox_forest.png"
    figure.write_bytes(b"first")
    first = _versioned_figure_url("analysis-id", "cox", figure)

    figure.write_bytes(b"second-version")
    second = _versioned_figure_url("analysis-id", "cox", figure)

    assert first.startswith(
        "/api/v1/examples/paper/figures/analysis-id/cox?v="
    )
    assert first != second


def test_example_km_prefers_presentation_artifact(tmp_path):
    analysis_dir = tmp_path / "analysis-id"
    analysis_dir.mkdir()
    audited_plot = analysis_dir / "plot.png"
    audited_plot.write_bytes(b"audited")

    assert (
        _figure_artifact_path(tmp_path, "analysis-id", "km")
        == audited_plot
    )

    presentation_plot = analysis_dir / "example_plot.png"
    presentation_plot.write_bytes(b"presentation")

    assert (
        _figure_artifact_path(tmp_path, "analysis-id", "km")
        == presentation_plot
    )


def test_example_continuous_uses_effect_profile_artifact(tmp_path):
    analysis_dir = tmp_path / "analysis-id"
    analysis_dir.mkdir()
    continuous_plot = analysis_dir / "continuous_effect.png"
    continuous_plot.write_bytes(b"profile")

    assert (
        _figure_artifact_path(tmp_path, "analysis-id", "continuous")
        == continuous_plot
    )


def test_time_varying_effect_compacts_raw_model_contract():
    model = {
        "ph_p_value": 0.01,
        "time_varying_effect": {
            "status": "completed",
            "split_days": 730.5,
            "periods": {
                "early": {
                    "hazard_ratio": 2.8,
                    "hr_conf_low": 2.2,
                    "hr_conf_high": 3.5,
                    "p_value": 1e-8,
                },
                "late": {
                    "hazard_ratio": 1.8,
                    "hr_conf_low": 1.4,
                    "hr_conf_high": 2.4,
                    "p_value": 1e-4,
                },
            },
            "change": {
                "hazard_ratio_ratio": 0.65,
                "hr_ratio_conf_low": 0.46,
                "hr_ratio_conf_high": 0.94,
                "p_value": 0.02,
            },
            "support": {
                "early_events": 56,
                "late_events": 69,
                "at_risk_at_split": 241,
            },
            "ties": "efron",
            "variance": "participant-clustered robust sandwich",
        },
    }

    compact = _compact_time_varying_effect(model, {}, "adjusted")

    assert compact["status"] == "completed"
    assert compact["split_days"] == 730.5
    assert compact["trigger_ph_p_value"] == 0.01
    assert compact["periods"]["early"]["hazard_ratio"] == 2.8
    assert compact["periods"]["late"]["hazard_ratio"] == 1.8
    assert compact["change"]["hazard_ratio_ratio"] == 0.65
    assert compact["support"] == {
        "early_events": 56,
        "late_events": 69,
        "at_risk_at_split": 241,
    }


def test_time_varying_effect_compacts_csv_fallback():
    compact = _compact_time_varying_effect(
        {},
        {
            "adjusted_temporal_status": "completed",
            "adjusted_temporal_split_days": "730.5",
            "adjusted_temporal_early_events": "8",
            "adjusted_temporal_early_hr": "2.4",
            "adjusted_temporal_late_events": "7",
            "adjusted_temporal_at_risk_at_split": "30",
            "adjusted_temporal_late_hr": "1.1",
            "adjusted_temporal_late_to_early_hr_ratio": "0.458",
            "adjusted_temporal_late_to_early_p_value": "0.03",
        },
        "adjusted",
    )

    assert compact["status"] == "completed"
    assert compact["periods"]["early"]["hazard_ratio"] == 2.4
    assert compact["periods"]["late"]["hazard_ratio"] == 1.1
    assert compact["change"]["hazard_ratio_ratio"] == 0.458
    assert compact["support"]["early_events"] == 8
    assert compact["support"]["late_events"] == 7
    assert compact["support"]["at_risk_at_split"] == 30


def test_publication_catalog_covers_main_and_diagnostic_benchmarks():
    packaged = Path("/app/publication/benchmark")
    if packaged.exists():
        benchmark_dir = packaged
        artifact_dir = Path("/app/artifacts")
    else:
        repository = Path(__file__).resolve().parents[2]
        benchmark_dir = repository / "docs" / "publication" / "benchmark"
        artifact_dir = repository / "artifacts"

    catalog = build_paper_examples(benchmark_dir, artifact_dir)

    assert catalog["summary"]["single_gene_scenarios"] == 11
    assert catalog["summary"]["continuous_references"] == 11
    assert catalog["summary"]["cutpoint_analyses"] == 44
    assert catalog["summary"]["advanced_examples"] == 6
    assert "retained_cutpoint_results" not in catalog["summary"]
    assert "grouped_holm_below_alpha_cutpoint_results" in catalog["summary"]
    assert "marker_ph_caution_results" in catalog["summary"]
    assert catalog["summary"]["low_information_cutpoint_results"] >= 1
    assert catalog["summary"]["firth_sensitivity_cutpoint_results"] >= 4
    assert len(catalog["cutpoints"]) == 4
    assert {case["section"] for case in catalog["single_gene_cases"]} == {
        "main",
        "supplementary",
    }
    assert {
        example["kind"] for example in catalog["advanced_examples"]
    } == {
        "weighted_signature",
        "two_marker",
        "pancancer",
        "diagnostic_hypoxia",
        "diagnostic_two_signature",
        "diagnostic_pancancer",
    }
    pancancer = next(
        example
        for example in catalog["advanced_examples"]
        if example["kind"] == "pancancer"
    )
    assert pancancer["pancancer"]["gene_symbol"] == "BIRC5"
    assert pancancer["pancancer"]["pipeline_version"] == PANCANCER_PIPELINE_VERSION
    assert len(pancancer["pancancer"]["results"]) == 33
    assert pancancer["pancancer"]["clinical_sensitivity"]["available"] is True
    assert (
        pancancer["pancancer"]["clinical_sensitivity"]["summary"]["evaluable"]
        == 26
    )
    assert any(
        row["selected_adjusted_model"]
        for row in pancancer["pancancer"]["results"]
    )
    assert any(
        (row["time_varying_effect"] or {}).get("status") == "completed"
        for row in pancancer["pancancer"]["results"]
    )
    assert any(
        (row["adjusted_time_varying_effect"] or {}).get("status") == "completed"
        for row in pancancer["pancancer"]["results"]
    )

    methods = [
        method
        for case in catalog["single_gene_cases"]
        for method in case["methods"]
    ]
    assert methods
    assert all("retained" not in method for method in methods)
    assert all("grouped_holm_p_value" in method for method in methods)
    assert all("grouped_holm_below_alpha" in method for method in methods)
    assert all("marker_ph_flagged" in method for method in methods)
    assert all("global_ph_flagged" in method for method in methods)
    assert any(method["marker_ph_p_value"] is not None for method in methods)
    assert any(
        method["adjusted_information_status"] in {"caution", "severe"}
        for method in methods
    )
    assert any(
        method["adjusted_firth_status"] == "completed"
        for method in methods
    )
    continuous = [
        case["continuous"]
        for case in catalog["single_gene_cases"]
    ]
    assert all(reference["status"] == "completed" for reference in continuous)
    assert all(reference["cutpoint_independent"] is True for reference in continuous)
    assert all(reference["n_patients"] for reference in continuous)
    assert all(reference["hazard_ratio"] is not None for reference in continuous)
    assert all(reference["bh_p_value"] is not None for reference in continuous)
    assert all(reference["events_per_parameter"] is not None for reference in continuous)
    assert all(
        reference["adjusted_model"] == "continuous_user_adjusted"
        for reference in continuous
    )
    emp3 = next(
        case
        for case in catalog["single_gene_cases"]
        if case["id"] == "lgg-emp3-os"
    )
    assert emp3["continuous"]["adjusted_time_varying_effect"]["status"] == "completed"
    assert (
        emp3["continuous"]["adjusted_time_varying_effect"]["split_days"]
        == 730.5
    )
    assert sum(
        method["adjusted_time_varying_effect"].get("status") == "completed"
        for method in emp3["methods"]
    ) == 3
    assert all(
        reference["spline"]["nonlinearity_bh_p_value"] is not None
        for reference in continuous
    )
