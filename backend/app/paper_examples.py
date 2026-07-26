from __future__ import annotations

import csv
import json
from functools import lru_cache
from pathlib import Path
from typing import Any


CUTPOINTS = [
    {"id": "maxstat", "label": "Maxstat"},
    {"id": "median", "label": "Median"},
    {"id": "upper_quartile", "label": "Upper quartile"},
    {"id": "upper_lower_quartile", "label": "Outer quartiles"},
]

SINGLE_GENE_CASES = [
    {
        "id": "lihc-cdc20-os",
        "source": "lihc_cdc20_os_cutpoint_benchmark",
        "section": "main",
        "purpose": "Illustrative case",
        "title": "CDC20 in liver cancer",
        "interpretation": "Adverse estimates remain directionally similar across four nonredundant cutpoint rules.",
    },
    {
        "id": "luad-birc5-os",
        "source": "luad_birc5_os_cutpoint_benchmark",
        "section": "main",
        "purpose": "Illustrative case",
        "title": "BIRC5 in lung adenocarcinoma",
        "interpretation": "Cutpoint-dependent grouped evidence and adjusted estimates remain visible without a composite verdict.",
    },
    {
        "id": "uvm-bap1-dss",
        "source": "uvm_bap1_dss_cutpoint_benchmark",
        "section": "main",
        "purpose": "Low-event diagnostic",
        "title": "BAP1 in uveal melanoma",
        "interpretation": "A strong low-event association whose ordinal-stage model exposes an assumption and precision caution.",
    },
    {
        "id": "skcm-tmem176b-os",
        "source": "skcm_tmem176b_os_cutpoint_benchmark",
        "section": "main",
        "purpose": "Exploratory",
        "title": "TMEM176B in melanoma",
        "interpretation": "A literature-prioritized marker with estimates that vary across cutpoint rules.",
    },
    {
        "id": "lgg-emp3-os",
        "source": "lgg_emp3_os_cutpoint_benchmark",
        "section": "main",
        "purpose": "PH diagnostic",
        "title": "EMP3 in lower-grade glioma",
        "interpretation": (
            "Strong association and RMST differences coexist with marker-specific "
            "PH cautions; a fixed two-year diagnostic separates early and later effects."
        ),
    },
    {
        "id": "kirc-ca9-os",
        "source": "kirc_ca9_cutpoint_benchmark",
        "section": "supplementary",
        "purpose": "External concordance",
        "title": "CA9 in clear-cell kidney cancer",
        "interpretation": "Directionally concordant externally, with internally cutpoint-dependent evidence.",
    },
    {
        "id": "brca-mki67-os",
        "source": "brca_mki67_os_cutpoint_benchmark",
        "section": "supplementary",
        "purpose": "Unsupported case",
        "title": "MKI67 in breast cancer · OS",
        "interpretation": "A preserved null and PH-sensitive result rather than a selected positive example.",
    },
    {
        "id": "brca-mki67-pfi",
        "source": "brca_mki67_pfi_cutpoint_benchmark",
        "section": "supplementary",
        "purpose": "Endpoint sensitivity",
        "title": "MKI67 in breast cancer · PFI",
        "interpretation": "Changing the endpoint changes nominal evidence and uncertainty.",
    },
    {
        "id": "skcm-pdcd1-os",
        "source": "skcm_pdcd1_os_cutpoint_benchmark",
        "section": "supplementary",
        "purpose": "Immune marker",
        "title": "PDCD1 in melanoma",
        "interpretation": "An immune marker with cutpoint and sample-selection sensitivity.",
    },
    {
        "id": "luad-cd274-os",
        "source": "luad_cd274_os_cutpoint_benchmark",
        "section": "supplementary",
        "purpose": "Unsupported case",
        "title": "CD274 in lung adenocarcinoma · OS",
        "interpretation": "The frozen OS benchmark preserves estimates without supported within-scenario Holm results.",
    },
    {
        "id": "luad-cd274-pfi",
        "source": "luad_cd274_pfi_cutpoint_benchmark",
        "section": "supplementary",
        "purpose": "Endpoint sensitivity",
        "title": "CD274 in lung adenocarcinoma · PFI",
        "interpretation": "Endpoint-sensitive estimates remain visible without collapsing them into a claim.",
    },
]

PAN_CANCER_RAW_FILES = {
    "pancancer": "pancancer.raw.json",
    "diagnostic_pancancer": "diagnostic_pancancer.raw.json",
}

FIGURE_FILENAMES = {
    "km": ("example_plot.png", "plot.png"),
    "cox": ("cox_forest.png",),
    "continuous": ("continuous_effect.png",),
}


def build_paper_examples(benchmark_dir: Path, artifact_dir: Path) -> dict[str, Any]:
    if not benchmark_dir.exists():
        raise FileNotFoundError(f"Publication benchmark directory not found: {benchmark_dir}")

    single_gene_cases = [
        _single_gene_case(benchmark_dir, artifact_dir, definition)
        for definition in SINGLE_GENE_CASES
    ]
    feature_metadata = _read_json(
        benchmark_dir / "feature_benchmarks" / "feature_benchmark_metadata.json"
    )
    advanced_examples = []
    for section, rows in (
        ("main", feature_metadata.get("feature_rows", [])),
        ("diagnostic", feature_metadata.get("diagnostic_rows", [])),
    ):
        for row in rows:
            advanced_examples.append(
                _advanced_example(benchmark_dir, artifact_dir, section, row)
            )

    snapshot = _read_json(benchmark_dir / "data_snapshot_manifest.json")
    method_count = sum(len(case["methods"]) for case in single_gene_cases)
    grouped_holm_below_alpha_count = sum(
        int(method["grouped_holm_below_alpha"])
        for case in single_gene_cases
        for method in case["methods"]
    )
    marker_ph_caution_count = sum(
        int(method["marker_ph_flagged"])
        for case in single_gene_cases
        for method in case["methods"]
    )
    low_information_count = sum(
        int(
            method.get("univariable_information_status") in {"caution", "severe"}
            or method.get("adjusted_information_status") in {"caution", "severe"}
        )
        for case in single_gene_cases
        for method in case["methods"]
    )
    firth_sensitivity_count = sum(
        int(
            method.get("univariable_firth_status") == "completed"
            or method.get("adjusted_firth_status") == "completed"
        )
        for case in single_gene_cases
        for method in case["methods"]
    )
    return {
        "publication": {
            "title": "TCGA-TRACE: auditable survival analysis for TCGA transcriptomic biomarkers",
            "benchmark_generated_at": feature_metadata.get("finished_at"),
            "data_snapshot_generated_at": snapshot.get("generated_at"),
            "data_snapshot_hash": snapshot.get("manifest_hash"),
            "schema_version": snapshot.get("schema_version"),
            "status": "Reproducible manuscript benchmark snapshot",
            "disclaimer": (
                "These examples demonstrate workflow behavior. They are exploratory research "
                "outputs, not validated biomarkers or clinical recommendations."
            ),
        },
        "summary": {
            "single_gene_scenarios": len(single_gene_cases),
            "continuous_references": sum(
                case["continuous"]["status"] == "completed"
                for case in single_gene_cases
            ),
            "cutpoint_analyses": method_count,
            "grouped_holm_below_alpha_cutpoint_results": (
                grouped_holm_below_alpha_count
            ),
            # Deprecated alias for clients pinned to the first catalog schema.
            "bh_below_alpha_cutpoint_results": grouped_holm_below_alpha_count,
            "marker_ph_caution_results": marker_ph_caution_count,
            "low_information_cutpoint_results": low_information_count,
            "firth_sensitivity_cutpoint_results": firth_sensitivity_count,
            "advanced_examples": len(advanced_examples),
            "main_examples": sum(
                case["section"] == "main" for case in single_gene_cases
            )
            + sum(example["section"] == "main" for example in advanced_examples),
            "diagnostic_examples": sum(
                case["section"] != "main" for case in single_gene_cases
            )
            + sum(example["section"] != "main" for example in advanced_examples),
        },
        "cutpoints": CUTPOINTS,
        "single_gene_cases": single_gene_cases,
        "advanced_examples": advanced_examples,
    }


@lru_cache(maxsize=8)
def publication_example_result_ids(benchmark_dir: Path) -> frozenset[str]:
    if not benchmark_dir.exists():
        return frozenset()
    result_ids: set[str] = set()
    for summary_path in benchmark_dir.glob("*_benchmark/summary.csv"):
        for row in _read_csv(summary_path):
            analysis_id = str(row.get("analysis_id") or "").strip()
            if analysis_id:
                result_ids.add(analysis_id)
    feature_path = (
        benchmark_dir / "feature_benchmarks" / "feature_benchmark_metadata.json"
    )
    if feature_path.exists():
        feature_metadata = _read_json(feature_path)
        for key in ("feature_rows", "diagnostic_rows"):
            for row in feature_metadata.get(key, []):
                result_id = str(row.get("id") or "").strip()
                if result_id:
                    result_ids.add(result_id)
    return frozenset(result_ids)


def publication_figure_path(
    benchmark_dir: Path,
    artifact_dir: Path,
    analysis_id: str,
    kind: str,
) -> Path | None:
    if kind not in FIGURE_FILENAMES:
        return None
    if analysis_id not in publication_example_result_ids(benchmark_dir):
        return None
    candidate = _figure_artifact_path(artifact_dir, analysis_id, kind)
    if candidate is None:
        return None
    try:
        candidate.resolve().relative_to(artifact_dir.resolve())
    except ValueError:
        return None
    return candidate


def _single_gene_case(
    benchmark_dir: Path,
    artifact_dir: Path,
    definition: dict[str, str],
) -> dict[str, Any]:
    rows = _read_csv(benchmark_dir / definition["source"] / "summary.csv")
    raw_results = _raw_results_by_analysis_id(
        benchmark_dir / definition["source"] / "benchmark_results.raw.json"
    )
    methods = [
        _compact_method(
            row,
            artifact_dir,
            raw_results.get(str(row.get("analysis_id") or "")),
        )
        for row in rows
    ]
    representative = next(
        (method for method in methods if method["method"] == "median"),
        methods[0],
    )
    representative_row = next(
        (row for row in rows if row.get("method") == representative["method"]),
        rows[0],
    )
    representative_raw = raw_results.get(
        str(representative_row.get("analysis_id") or "")
    )
    first = methods[0]
    return {
        **{key: value for key, value in definition.items() if key != "source"},
        "cohort": first["cohort"],
        "gene_symbol": first["gene_symbol"],
        "endpoint": first["endpoint"],
        "endpoint_source": first["endpoint_source"],
        "n_patients": first["n_patients"],
        "n_events": first["n_events"],
        "completed_methods": sum(method["status"] == "completed" for method in methods),
        "grouped_holm_below_alpha_methods": sum(
            method["grouped_holm_below_alpha"] for method in methods
        ),
        "all_grouped_methods_supported": (
            len(methods) == 4
            and all(method["grouped_holm_below_alpha"] for method in methods)
        ),
        "any_grouped_method_supported": any(
            method["grouped_holm_below_alpha"] for method in methods
        ),
        # Deprecated alias for clients pinned to the first catalog schema.
        "bh_below_alpha_methods": sum(
            method["grouped_holm_below_alpha"] for method in methods
        ),
        "marker_ph_flagged_methods": sum(method["marker_ph_flagged"] for method in methods),
        "global_ph_flagged_methods": sum(method["global_ph_flagged"] for method in methods),
        "representative_method": representative["method"],
        "continuous": _compact_continuous_reference(
            representative_row,
            artifact_dir,
            representative_raw,
        ),
        "methods": methods,
    }


def _compact_method(
    row: dict[str, str],
    artifact_dir: Path,
    raw_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    analysis_id = str(row.get("analysis_id") or "")
    figures = {}
    km_path = _figure_artifact_path(artifact_dir, analysis_id, "km")
    cox_path = _figure_artifact_path(artifact_dir, analysis_id, "cox")
    if km_path is not None:
        figures["km"] = _versioned_figure_url(analysis_id, "km", km_path)
    if cox_path is not None:
        figures["cox"] = _versioned_figure_url(analysis_id, "cox", cox_path)
    cox_models = ((raw_result or {}).get("metrics") or {}).get("cox_models") or []
    univariable_model = _selected_model(cox_models, "univariable")
    adjusted_model = _selected_adjusted_model(raw_result, row.get("adjusted_model"))
    univariable_temporal = _compact_time_varying_effect(
        univariable_model,
        row,
        "univariable",
    )
    adjusted_temporal = _compact_time_varying_effect(
        adjusted_model,
        row,
        "adjusted",
    )
    selected_temporal = adjusted_temporal or univariable_temporal
    marker_ph_p = _number(row.get("adjusted_ph_p_value"))
    if marker_ph_p is None:
        marker_ph_p = _number(adjusted_model.get("ph_p_value"))
    global_ph_p = _number(row.get("adjusted_ph_global_p_value"))
    if global_ph_p is None:
        global_ph_p = _number(adjusted_model.get("ph_global_p_value"))
    grouped_holm_p = _number(row.get("grouped_holm_p_value"))
    if grouped_holm_p is None:
        grouped_holm_p = _number(row.get("bh_logrank_p_value"))
    grouped_holm_below_alpha = (
        grouped_holm_p is not None and grouped_holm_p <= 0.05
    )
    marker_ph_flagged = marker_ph_p is not None and marker_ph_p < 0.05
    global_ph_flagged = global_ph_p is not None and global_ph_p < 0.05
    method = row.get("method")
    profile_notes = []
    if marker_ph_flagged:
        profile_notes.append("Marker-specific PH caution")
        if selected_temporal.get("status") == "completed":
            profile_notes.append("Prespecified two-year effect diagnostic completed")
        elif selected_temporal.get("status") == "skipped":
            profile_notes.append(
                "Prespecified two-year effect diagnostic skipped for insufficient support"
            )
    elif global_ph_flagged:
        profile_notes.append("Global PH caution; marker term is not flagged")
    if method == "maxstat":
        profile_notes.append("Outcome-optimized cutpoint; grouped estimates are post-selection")
    if not row.get("adjusted_model"):
        profile_notes.append("Adjusted Cox not evaluable")
    elif row.get("adjusted_status") == "failed":
        profile_notes.append("Standard adjusted Cox failed")
    if row.get("adjusted_information_status") in {"caution", "severe"}:
        profile_notes.append(
            f"Adjusted Cox {row.get('adjusted_events_per_parameter')} events/parameter "
            f"({row.get('adjusted_information_status')})"
        )
    if row.get("adjusted_firth_status") == "completed":
        profile_notes.append("Firth adjusted sensitivity completed")
    elif row.get("univariable_firth_status") == "completed":
        profile_notes.append("Firth univariable sensitivity completed")
    if row.get("rmst_status") != "completed":
        profile_notes.append("RMST not evaluable")
    if not profile_notes:
        profile_notes.append("No model-diagnostic caution recorded")
    return {
        "method": method,
        "label": next(
            (
                cutpoint["label"]
                for cutpoint in CUTPOINTS
                if cutpoint["id"] == row.get("method")
            ),
            row.get("method"),
        ),
        "status": row.get("status"),
        "analysis_id": analysis_id,
        "cohort": row.get("cohort"),
        "gene_symbol": row.get("gene_symbol"),
        "endpoint": row.get("endpoint"),
        "endpoint_source": row.get("endpoint_source"),
        "n_patients": _integer(row.get("n_patients")),
        "n_events": _integer(row.get("n_events")),
        "threshold": _number(row.get("threshold")),
        "logrank_p_value": _number(row.get("logrank_p_value")),
        "grouped_family_p_value": _number(row.get("grouped_family_p_value")),
        "grouped_family_input": row.get("grouped_family_input") or None,
        "grouped_holm_p_value": grouped_holm_p,
        "grouped_holm_below_alpha": grouped_holm_below_alpha,
        # Deprecated aliases for clients pinned to the first catalog schema.
        "bh_logrank_p_value": grouped_holm_p,
        "bh_below_alpha": grouped_holm_below_alpha,
        "hazard_ratio": _number(row.get("univariable_hr")),
        "hr_conf_low": _number(row.get("univariable_hr_conf_low")),
        "hr_conf_high": _number(row.get("univariable_hr_conf_high")),
        "cox_p_value": _number(row.get("univariable_p_value")),
        "univariable_status": row.get("univariable_status") or None,
        "univariable_parameter_count": _integer(
            row.get("univariable_parameter_count")
        ),
        "univariable_events_per_parameter": _number(
            row.get("univariable_events_per_parameter")
        ),
        "univariable_information_status": row.get(
            "univariable_information_status"
        )
        or None,
        "univariable_firth_status": row.get("univariable_firth_status") or None,
        "univariable_firth_hr": _number(row.get("univariable_firth_hr")),
        "univariable_firth_hr_conf_low": _number(
            row.get("univariable_firth_hr_conf_low")
        ),
        "univariable_firth_hr_conf_high": _number(
            row.get("univariable_firth_hr_conf_high")
        ),
        "univariable_firth_p_value": _number(
            row.get("univariable_firth_p_value")
        ),
        "univariable_firth_ties": row.get("univariable_firth_ties") or None,
        "adjusted_model": row.get("adjusted_model") or None,
        "adjusted_status": row.get("adjusted_status") or None,
        "adjusted_hr": _number(row.get("adjusted_hr")),
        "adjusted_hr_conf_low": _number(row.get("adjusted_hr_conf_low")),
        "adjusted_hr_conf_high": _number(row.get("adjusted_hr_conf_high")),
        "adjusted_p_value": _number(row.get("adjusted_p_value")),
        "adjusted_parameter_count": _integer(row.get("adjusted_parameter_count")),
        "adjusted_events_per_parameter": _number(
            row.get("adjusted_events_per_parameter")
        ),
        "adjusted_information_status": row.get("adjusted_information_status")
        or None,
        "adjusted_firth_status": row.get("adjusted_firth_status") or None,
        "adjusted_firth_hr": _number(row.get("adjusted_firth_hr")),
        "adjusted_firth_hr_conf_low": _number(
            row.get("adjusted_firth_hr_conf_low")
        ),
        "adjusted_firth_hr_conf_high": _number(
            row.get("adjusted_firth_hr_conf_high")
        ),
        "adjusted_firth_p_value": _number(row.get("adjusted_firth_p_value")),
        "adjusted_firth_ties": row.get("adjusted_firth_ties") or None,
        "marker_ph_p_value": marker_ph_p,
        "marker_ph_flagged": marker_ph_flagged,
        "global_ph_p_value": global_ph_p,
        "global_ph_flagged": global_ph_flagged,
        "time_varying_effect": selected_temporal,
        "univariable_time_varying_effect": univariable_temporal,
        "adjusted_time_varying_effect": adjusted_temporal,
        "rmst_tau_days": _number(row.get("rmst_tau_days")),
        "rmst_delta_days": _number(row.get("rmst_delta_days")),
        "rmst_p_value": _number(row.get("rmst_p_value")),
        "direction": row.get("direction") or None,
        "selection_caution": method == "maxstat",
        "same_contrast_status": row.get("same_contrast_status") or None,
        "same_contrast_delta_sd": _number(row.get("same_contrast_delta_sd")),
        "continuous_implied_same_contrast_hr": _number(
            row.get("continuous_implied_same_contrast_hr")
        ),
        "same_contrast_log_hr_amplification_ratio": _number(
            row.get("same_contrast_log_hr_amplification_ratio")
        ),
        "same_contrast_direction_concordant": _boolean(
            row.get("same_contrast_direction_concordant")
        ),
        "profile_notes": profile_notes,
        "audit_hash": row.get("audit_reproducibility_hash") or None,
        "figures": figures,
    }


def _raw_results_by_analysis_id(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    raw = _read_json(path)
    results: dict[str, dict[str, Any]] = {}
    for item in raw.get("results", []):
        result = item.get("result") or {}
        analysis_id = str(result.get("id") or "")
        if analysis_id:
            results[analysis_id] = result
    return results


def _compact_continuous_reference(
    row: dict[str, str],
    artifact_dir: Path,
    raw_result: dict[str, Any] | None,
) -> dict[str, Any]:
    analysis_id = str(row.get("analysis_id") or "")
    continuous = ((raw_result or {}).get("metrics") or {}).get(
        "continuous_analysis"
    ) or {}
    linear_models = continuous.get("linear_models") or []
    univariable = _selected_model(linear_models, "continuous_univariable")
    adjusted = _selected_continuous_adjusted_model(
        linear_models,
        row.get("continuous_adjusted_model"),
    )
    univariable_temporal = _compact_time_varying_effect(
        univariable,
        row,
        "continuous_univariable",
    )
    adjusted_temporal = _compact_time_varying_effect(
        adjusted,
        row,
        "continuous_adjusted",
    )
    spline = continuous.get("spline") or {}
    figure_path = _figure_artifact_path(
        artifact_dir,
        analysis_id,
        "continuous",
    )
    figure = (
        _versioned_figure_url(
            analysis_id,
            "continuous",
            figure_path,
        )
        if figure_path is not None
        else None
    )
    return {
        "status": continuous.get("status") or row.get("spline_status") or "unavailable",
        "reason": continuous.get("reason"),
        "analysis_id": analysis_id,
        "cutpoint_independent": continuous.get("cutpoint_independent", True),
        "population": continuous.get(
            "population",
            "unstratified expression-complete eligible cohort",
        ),
        "n_patients": _first_integer(
            continuous.get("n_patients"),
            row.get("continuous_n_patients"),
        ),
        "n_events": _first_integer(
            continuous.get("n_events"),
            row.get("continuous_n_events"),
        ),
        "effect_unit": (continuous.get("predictor") or {}).get(
            "effect_unit",
            "hazard ratio per +1 SD expression",
        ),
        "standard_deviation": _number(
            (continuous.get("predictor") or {}).get("standard_deviation")
        ),
        "hazard_ratio": _first_number(
            univariable.get("hazard_ratio"),
            row.get("continuous_univariable_hr"),
        ),
        "hr_conf_low": _first_number(
            univariable.get("hr_conf_low"),
            row.get("continuous_univariable_hr_conf_low"),
        ),
        "hr_conf_high": _first_number(
            univariable.get("hr_conf_high"),
            row.get("continuous_univariable_hr_conf_high"),
        ),
        "p_value": _first_number(
            univariable.get("p_value"),
            row.get("continuous_univariable_p_value"),
        ),
        "information_status": (
            univariable.get("information_diagnostics") or {}
        ).get("status")
        or row.get("continuous_univariable_information_status")
        or None,
        "events_per_parameter": _first_number(
            (univariable.get("information_diagnostics") or {}).get(
                "events_per_parameter"
            ),
            row.get("continuous_univariable_events_per_parameter"),
        ),
        "firth_status": (univariable.get("penalized_sensitivity") or {}).get(
            "status"
        )
        or row.get("continuous_univariable_firth_status")
        or None,
        "bh_p_value": _number(row.get("continuous_bh_p_value")),
        "marker_ph_p_value": _first_number(
            univariable.get("ph_p_value"),
            row.get("continuous_univariable_ph_p_value"),
        ),
        "global_ph_p_value": _first_number(
            univariable.get("ph_global_p_value"),
            row.get("continuous_univariable_ph_global_p_value"),
        ),
        "adjusted_model": adjusted.get("model")
        or row.get("continuous_adjusted_model")
        or None,
        "adjusted_hr": _first_number(
            adjusted.get("hazard_ratio"),
            row.get("continuous_adjusted_hr"),
        ),
        "adjusted_hr_conf_low": _first_number(
            adjusted.get("hr_conf_low"),
            row.get("continuous_adjusted_hr_conf_low"),
        ),
        "adjusted_hr_conf_high": _first_number(
            adjusted.get("hr_conf_high"),
            row.get("continuous_adjusted_hr_conf_high"),
        ),
        "adjusted_p_value": _first_number(
            adjusted.get("p_value"),
            row.get("continuous_adjusted_p_value"),
        ),
        "adjusted_information_status": (
            adjusted.get("information_diagnostics") or {}
        ).get("status")
        or row.get("continuous_adjusted_information_status")
        or None,
        "adjusted_events_per_parameter": _first_number(
            (adjusted.get("information_diagnostics") or {}).get(
                "events_per_parameter"
            ),
            row.get("continuous_adjusted_events_per_parameter"),
        ),
        "adjusted_firth_status": (
            adjusted.get("penalized_sensitivity") or {}
        ).get("status")
        or row.get("continuous_adjusted_firth_status")
        or None,
        "adjusted_marker_ph_p_value": _first_number(
            adjusted.get("ph_p_value"),
            row.get("continuous_adjusted_ph_p_value"),
        ),
        "adjusted_global_ph_p_value": _first_number(
            adjusted.get("ph_global_p_value"),
            row.get("continuous_adjusted_ph_global_p_value"),
        ),
        "time_varying_effect": adjusted_temporal or univariable_temporal,
        "univariable_time_varying_effect": univariable_temporal,
        "adjusted_time_varying_effect": adjusted_temporal,
        "spline": {
            "status": spline.get("status") or row.get("spline_status"),
            "reason": spline.get("reason"),
            "overall_p_value": _first_number(
                spline.get("overall_p_value"),
                row.get("spline_overall_p_value"),
            ),
            "nonlinearity_p_value": _first_number(
                spline.get("nonlinearity_p_value"),
                row.get("spline_nonlinearity_p_value"),
            ),
            "nonlinearity_bh_p_value": _number(
                row.get("spline_nonlinearity_bh_p_value")
            ),
            "reference_expression": _first_number(
                spline.get("reference_expression"),
                row.get("spline_reference_expression"),
            ),
            "knot_percentiles": spline.get("knot_percentiles")
            or _json_list(row.get("spline_knot_percentiles")),
            "profile": spline.get("profile") or [],
        },
        "figure": figure,
        "population_hash": row.get("continuous_patient_records_sha256") or None,
    }


def _selected_adjusted_model(
    raw_result: dict[str, Any] | None,
    model_id: str | None,
) -> dict[str, Any]:
    models = ((raw_result or {}).get("metrics") or {}).get("cox_models") or []
    if model_id:
        selected = next(
            (
                model
                for model in models
                if model.get("model") == model_id and model.get("status") == "completed"
            ),
            None,
        )
        if selected:
            return selected
    for candidate in ("stage_grade_adjusted", "stage_adjusted", "grade_adjusted"):
        selected = next(
            (
                model
                for model in models
                if model.get("model") == candidate and model.get("status") == "completed"
            ),
            None,
        )
        if selected:
            return selected
    return {}


def _selected_continuous_adjusted_model(
    models: list[dict[str, Any]],
    model_id: str | None = None,
) -> dict[str, Any]:
    if model_id:
        selected = _selected_model(models, model_id)
        if selected:
            return selected
    for candidate in (
        "continuous_user_adjusted",
        "continuous_stage_grade_adjusted",
        "continuous_stage_adjusted",
        "continuous_grade_adjusted",
    ):
        selected = _selected_model(models, candidate)
        if selected:
            return selected
    return {}


def _compact_time_varying_effect(
    model: dict[str, Any],
    row: dict[str, str],
    prefix: str,
) -> dict[str, Any]:
    diagnostic = model.get("time_varying_effect") or {}
    status = diagnostic.get("status") or row.get(f"{prefix}_temporal_status")
    if not status:
        return {}

    periods = diagnostic.get("periods") or {}
    early = periods.get("early") or {}
    late = periods.get("late") or {}
    change = diagnostic.get("change") or {}
    support = diagnostic.get("support") or {}
    return {
        "status": status,
        "reason": diagnostic.get("reason")
        or row.get(f"{prefix}_temporal_reason")
        or None,
        "method": diagnostic.get("method")
        or "Prespecified two-period Cox marker effect",
        "trigger": diagnostic.get("trigger")
        or "Marker-specific cox.zph p < 0.05",
        "trigger_ph_p_value": _first_number(
            diagnostic.get("trigger_ph_p_value"),
            model.get("ph_p_value"),
        ),
        "split_days": _first_number(
            diagnostic.get("split_days"),
            row.get(f"{prefix}_temporal_split_days"),
        ),
        "split_rule": diagnostic.get("split_rule"),
        "effect_label": diagnostic.get("effect_label"),
        "periods": {
            "early": {
                "label": early.get("label") or "0 to 2 years",
                "hazard_ratio": _first_number(
                    early.get("hazard_ratio"),
                    row.get(f"{prefix}_temporal_early_hr"),
                ),
                "hr_conf_low": _first_number(
                    early.get("hr_conf_low"),
                    row.get(f"{prefix}_temporal_early_hr_conf_low"),
                ),
                "hr_conf_high": _first_number(
                    early.get("hr_conf_high"),
                    row.get(f"{prefix}_temporal_early_hr_conf_high"),
                ),
                "p_value": _first_number(
                    early.get("p_value"),
                    row.get(f"{prefix}_temporal_early_p_value"),
                ),
            },
            "late": {
                "label": late.get("label") or "After 2 years",
                "hazard_ratio": _first_number(
                    late.get("hazard_ratio"),
                    row.get(f"{prefix}_temporal_late_hr"),
                ),
                "hr_conf_low": _first_number(
                    late.get("hr_conf_low"),
                    row.get(f"{prefix}_temporal_late_hr_conf_low"),
                ),
                "hr_conf_high": _first_number(
                    late.get("hr_conf_high"),
                    row.get(f"{prefix}_temporal_late_hr_conf_high"),
                ),
                "p_value": _first_number(
                    late.get("p_value"),
                    row.get(f"{prefix}_temporal_late_p_value"),
                ),
            },
        },
        "change": {
            "label": change.get("label") or "Late HR / early HR",
            "hazard_ratio_ratio": _first_number(
                change.get("hazard_ratio_ratio"),
                row.get(f"{prefix}_temporal_late_to_early_hr_ratio"),
            ),
            "hr_ratio_conf_low": _first_number(
                change.get("hr_ratio_conf_low"),
                row.get(
                    f"{prefix}_temporal_late_to_early_hr_ratio_conf_low"
                ),
            ),
            "hr_ratio_conf_high": _first_number(
                change.get("hr_ratio_conf_high"),
                row.get(
                    f"{prefix}_temporal_late_to_early_hr_ratio_conf_high"
                ),
            ),
            "p_value": _first_number(
                change.get("p_value"),
                row.get(f"{prefix}_temporal_late_to_early_p_value"),
            ),
        },
        "support": {
            "early_events": _first_integer(
                support.get("early_events"),
                row.get(f"{prefix}_temporal_early_events"),
            ),
            "late_events": _first_integer(
                support.get("late_events"),
                row.get(f"{prefix}_temporal_late_events"),
            ),
            "at_risk_at_split": _first_integer(
                support.get("at_risk_at_split"),
                row.get(f"{prefix}_temporal_at_risk_at_split"),
            ),
        },
        "ties": diagnostic.get("ties") or "efron",
        "variance": diagnostic.get("variance"),
    }


def _selected_model(
    models: list[dict[str, Any]],
    model_id: str,
) -> dict[str, Any]:
    return next(
        (
            model
            for model in models
            if model.get("model") == model_id and model.get("status") == "completed"
        ),
        {},
    )


def _versioned_figure_url(analysis_id: str, kind: str, path: Path) -> str:
    stat = path.stat()
    version = f"{stat.st_mtime_ns:x}-{stat.st_size:x}"
    return f"/api/v1/examples/paper/figures/{analysis_id}/{kind}?v={version}"


def _figure_artifact_path(
    artifact_dir: Path,
    analysis_id: str,
    kind: str,
) -> Path | None:
    for filename in FIGURE_FILENAMES.get(kind, ()):
        candidate = artifact_dir / analysis_id / filename
        if candidate.is_file():
            return candidate
    return None


def _advanced_example(
    benchmark_dir: Path,
    artifact_dir: Path,
    section: str,
    row: dict[str, Any],
) -> dict[str, Any]:
    result_id = str(row.get("id") or "")
    kind = str(row.get("kind") or "")
    output = {
        **row,
        "section": section,
        "result_id": result_id,
        "figure_type": "pancancer" if kind in PAN_CANCER_RAW_FILES else "analysis",
        "figures": {},
    }
    if output["figure_type"] == "analysis":
        continuous_path = _figure_artifact_path(
            artifact_dir,
            result_id,
            "continuous",
        )
        km_path = _figure_artifact_path(artifact_dir, result_id, "km")
        cox_path = _figure_artifact_path(artifact_dir, result_id, "cox")
        if continuous_path is not None:
            output["figures"]["continuous"] = _versioned_figure_url(
                result_id,
                "continuous",
                continuous_path,
            )
        if km_path is not None:
            output["figures"]["km"] = _versioned_figure_url(
                result_id,
                "km",
                km_path,
            )
        if cox_path is not None:
            output["figures"]["cox"] = _versioned_figure_url(
                result_id,
                "cox",
                cox_path,
            )
    else:
        raw = _read_json(
            benchmark_dir
            / "feature_benchmarks"
            / PAN_CANCER_RAW_FILES[kind]
        )
        output["pancancer"] = _compact_pancancer(raw)
    return output


def _compact_pancancer(raw: dict[str, Any]) -> dict[str, Any]:
    row_fields = (
        "code",
        "cohort",
        "cohort_label",
        "concordance",
        "direction",
        "effect_category",
        "endpoint",
        "endpoint_label",
        "endpoint_source",
        "fdr",
        "hazard_ratio",
        "hr_conf_high",
        "hr_conf_low",
        "log_hr",
        "common_scale_hazard_ratio",
        "common_scale_hr_conf_high",
        "common_scale_hr_conf_low",
        "common_scale_log_hr",
        "common_scale_standard_error",
        "common_scale_p_value",
        "common_scale_unit",
        "common_scale_eligible",
        "n_events",
        "n_patients",
        "p_value",
        "ph_p_value",
        "ph_global_p_value",
        "time_varying_effect",
        "primary_site",
        "reason",
        "selected_adjusted_model",
        "selected_adjusted_model_label",
        "adjusted_status",
        "adjusted_reason",
        "adjusted_n_patients",
        "adjusted_n_events",
        "adjusted_log_hr",
        "adjusted_standard_error",
        "adjusted_hazard_ratio",
        "adjusted_hr_conf_low",
        "adjusted_hr_conf_high",
        "adjusted_p_value",
        "adjusted_common_scale_hazard_ratio",
        "adjusted_common_scale_hr_conf_low",
        "adjusted_common_scale_hr_conf_high",
        "adjusted_common_scale_log_hr",
        "adjusted_common_scale_standard_error",
        "adjusted_common_scale_p_value",
        "adjusted_fdr",
        "adjusted_ph_p_value",
        "adjusted_ph_global_p_value",
        "adjusted_time_varying_effect",
        "adjusted_direction",
        "adjusted_effect_category",
        "adjusted_significant",
        "clinical_sensitivity",
        "significant",
        "standard_error",
        "status",
    )
    return {
        "scan_id": raw.get("scan_id"),
        "gene_symbol": raw.get("gene_symbol"),
        "endpoint": raw.get("endpoint"),
        "pipeline_version": raw.get("pipeline_version"),
        "data_version": raw.get("data_version") or {},
        "fdr_threshold": raw.get("fdr_threshold"),
        "effect_scale": raw.get("effect_scale") or {},
        "summary": raw.get("summary") or {},
        "meta_analysis": raw.get("meta_analysis") or {},
        "clinical_sensitivity": raw.get("clinical_sensitivity") or {},
        "audit": raw.get("audit") or {},
        "reference": raw.get("reference") or {},
        "results": [
            {key: row.get(key) for key in row_fields}
            for row in raw.get("results", [])
        ],
    }


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _number(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number else None


def _integer(value: Any) -> int | None:
    number = _number(value)
    return int(number) if number is not None else None


def _boolean(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    normalized = str(value or "").strip().lower()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    return None


def _first_number(*values: Any) -> float | None:
    for value in values:
        number = _number(value)
        if number is not None:
            return number
    return None


def _first_integer(*values: Any) -> int | None:
    number = _first_number(*values)
    return int(number) if number is not None else None


def _json_list(value: Any) -> list[Any]:
    if not value:
        return []
    if isinstance(value, list):
        return value
    try:
        parsed = json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    return parsed if isinstance(parsed, list) else []
