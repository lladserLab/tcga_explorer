#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


DEFAULT_API_BASE_URL = "http://localhost:3000/tcga_explorer"
DEFAULT_OUTPUT_DIR = Path("docs/publication/benchmark/kirc_ca9_cutpoint_benchmark")
DEFAULT_LATEX_TABLE = Path("manuscript/bioinformatics_app_note/tables/kirc_ca9_cutpoint_benchmark.tex")
DEFAULT_BENCHMARK_ID = "kirc_ca9_cutpoints"
DEFAULT_METHODS = ["maxstat", "median", "upper_quartile", "upper_lower_quartile"]
EVIDENCE_ALPHA = 0.05


def main() -> int:
    args = parse_args()
    benchmark_id = args.benchmark_id or slugify(f"{args.cohort}_{args.gene}_{args.endpoint}_cutpoint_benchmark")
    title = args.title or f"{args.cohort} {args.gene} {args.endpoint} cutpoint benchmark"
    output_dir = args.output_dir
    latex_table = resolve_latex_table(
        requested=args.latex_table,
        benchmark_id=benchmark_id,
        output_dir=output_dir,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    latex_table.parent.mkdir(parents=True, exist_ok=True)

    client = ApiClient(args.api_base_url)
    health = client.get("/api/health")
    endpoints = client.get(f"/api/cohorts/{urllib.parse.quote(args.cohort)}/endpoints")
    resolved = client.get(
        f"/api/cohorts/{urllib.parse.quote(args.cohort)}/genes/resolve?"
        f"{urllib.parse.urlencode({'query': args.gene})}"
    )
    if resolved.get("status") == "not_found":
        raise RuntimeError(f"Gene {args.gene} was not found in {args.cohort}.")

    analyses = [
        analysis_payload(
            cohort=args.cohort,
            gene=resolved.get("resolved") or args.gene,
            endpoint=args.endpoint,
            method=method,
            custom_percentile=args.custom_percentile,
            expression_scale=args.expression_scale,
            time_unit=args.time_unit,
            sample_types=args.sample_type,
            adjustment_covariates=args.adjustment_covariate,
        )
        for method in args.methods
    ]
    started_at = utc_now()
    batch = client.post("/api/analyses/batch", {"analyses": analyses, "max_concurrency": args.max_concurrency})
    finished_at = utc_now()

    rows = summarize_batch(batch)
    assign_grouped_family_p_values(rows)
    apply_holm(rows, "grouped_family_p_value", "grouped_holm_p_value")
    for row in rows:
        set_legacy_grouped_multiplicity_aliases(row)
        annotate_evidence_profile(row)
    annotate_same_contrast_effects(rows, client)

    metadata = {
        "benchmark_id": benchmark_id,
        "title": title,
        "started_at": started_at,
        "finished_at": finished_at,
        "api_base_url": args.api_base_url,
        "cohort": args.cohort,
        "gene": args.gene,
        "resolved_gene": resolved.get("resolved") or args.gene,
        "gene_resolution": resolved,
        "endpoint": args.endpoint,
        "expression_scale": args.expression_scale,
        "time_unit": args.time_unit,
        "sample_types": args.sample_type,
        "adjustment_covariates": args.adjustment_covariate,
        "methods": args.methods,
        "custom_percentile": args.custom_percentile,
        "evidence_alpha": EVIDENCE_ALPHA,
        "multiple_testing": {
            "grouped_method": "Holm",
            "grouped_family": (
                "four prespecified two-group cutpoint sensitivities within this "
                "marker-endpoint scenario"
            ),
            "grouped_scope": "within_scenario",
            "grouped_tests": len(
                [
                    row
                    for row in rows
                    if is_finite_number(row.get("grouped_family_p_value"))
                ]
            ),
            "maxstat_input": (
                "Lau94 selection-adjusted rank-statistic p-value; naive "
                "post-selection log-rank p is descriptive only"
            ),
            "continuous_linear_method": (
                "Benjamini-Hochberg across one prespecified linear Cox "
                "hypothesis per scenario, assigned by the suite"
            ),
            "continuous_nonlinearity_method": (
                "Benjamini-Hochberg across one prespecified spline "
                "nonlinearity hypothesis per scenario, assigned by the suite"
            ),
            "legacy_aliases": {
                "bh_logrank_p_value": "grouped_holm_p_value",
                "bh_within_scenario_logrank_p_value": "grouped_holm_p_value",
            },
        },
        "health": health,
        "endpoint_options": endpoints,
        "batch": {
            "total": batch.get("total"),
            "completed": batch.get("completed"),
            "failed": batch.get("failed"),
            "max_concurrency": batch.get("max_concurrency"),
        },
    }

    write_json(output_dir / "benchmark_metadata.json", metadata)
    write_json(output_dir / "benchmark_results.raw.json", batch)
    write_csv(output_dir / "summary.csv", rows)
    write_markdown(output_dir / "summary.md", metadata, rows)
    write_latex_table(latex_table, metadata, rows)

    print(f"Completed {metadata['batch']['completed']}/{metadata['batch']['total']} analyses")
    print(f"Wrote {output_dir / 'summary.csv'}")
    print(f"Wrote {output_dir / 'summary.md'}")
    print(f"Wrote {latex_table}")
    return 0 if metadata["batch"]["completed"] else 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the publication cutpoint benchmark through the TCGA-TRACE HTTP API."
    )
    parser.add_argument("--api-base-url", default=DEFAULT_API_BASE_URL)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--latex-table",
        type=Path,
        default=None,
        help=(
            "LaTeX output path. Defaults to the canonical KIRC table only for "
            "the default benchmark; custom benchmark IDs write inside "
            "--output-dir."
        ),
    )
    parser.add_argument("--benchmark-id", default=DEFAULT_BENCHMARK_ID)
    parser.add_argument("--title", default="")
    parser.add_argument("--cohort", default="TCGA-KIRC")
    parser.add_argument("--gene", default="CA9")
    parser.add_argument("--endpoint", default="OS", choices=["OS", "DSS", "DFI", "PFI"])
    parser.add_argument("--expression-scale", default="log2_tpm")
    parser.add_argument("--time-unit", default="months", choices=["days", "months", "years"])
    parser.add_argument("--methods", nargs="+", default=DEFAULT_METHODS)
    parser.add_argument("--sample-type", action="append", default=[], help="Restrict analysis to a TCGA sample_type value. Can be repeated.")
    parser.add_argument(
        "--adjustment-covariate",
        action="append",
        default=[],
        choices=["age_at_index", "stage", "grade", "gender", "race"],
        help=(
            "Clinical field for the exact complete-case user-adjusted Cox model. "
            "Can be repeated; omitted means no user-adjusted model."
        ),
    )
    parser.add_argument("--custom-percentile", type=float, default=60.0)
    parser.add_argument("--max-concurrency", type=int, default=1)
    return parser.parse_args()


def resolve_latex_table(
    *,
    requested: Path | None,
    benchmark_id: str,
    output_dir: Path,
) -> Path:
    if requested is not None:
        return requested
    if benchmark_id == DEFAULT_BENCHMARK_ID:
        return DEFAULT_LATEX_TABLE
    return output_dir / f"{benchmark_id}.tex"


class ApiClient:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    def get(self, path: str) -> dict[str, Any]:
        return self._request("GET", path)

    def post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", path, payload)

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=body,
            method=method,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=900) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"HTTP {exc.code} for {method} {path}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Could not reach {self.base_url}: {exc}") from exc


def analysis_payload(
    *,
    cohort: str,
    gene: str,
    endpoint: str,
    method: str,
    custom_percentile: float,
    expression_scale: str,
    time_unit: str,
    sample_types: list[str],
    adjustment_covariates: list[str],
) -> dict[str, Any]:
    return {
        "cohort": cohort,
        "gene_symbol": gene,
        "signature_method": "single",
        "signature_genes": [],
        "endpoint": endpoint,
        "expression_scale": expression_scale,
        "cutpoint_method": method,
        "custom_percentile": custom_percentile if method == "percentile" else None,
        "adjustment_covariates": adjustment_covariates,
        "filters": {
            "sample_types": sample_types,
            "stages": [],
            "grades": [],
            "genders": [],
            "races": [],
            "age_min": None,
            "age_max": None,
            "max_time_days": None,
        },
        "time_unit": time_unit,
        "show_confidence_interval": True,
        "show_risk_table": False,
        "plot_style": {
            "palette": ["#1f6f8b", "#c8842d", "#b94d48"],
            "font_family": "sans",
            "plot_aspect": "rectangular",
            "base_font_size": 12,
            "axis_text_size": 11,
            "axis_title_size": 12,
            "show_grid": False,
            "show_title": False,
            "plot_title": "",
        },
    }


def summarize_batch(batch: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in batch.get("results") or []:
        result = item.get("result") or {}
        metrics = result.get("metrics") or {}
        request_index = int(item.get("index") or 0)
        method = result.get("cutpoint_method") or ""
        univariable = find_model(
            metrics.get("cox_models"),
            "univariable",
            statuses=("completed", "failed"),
        )
        clinical_adjustment = metrics.get("clinical_adjustment") or {}
        user_adjustment_requested = clinical_adjustment.get("status") == "requested"
        adjusted = downstream_adjusted_reporting_model(
            metrics.get("cox_models"),
            user_requested=user_adjustment_requested,
        )
        continuous = metrics.get("continuous_analysis") or {}
        continuous_univariable = find_model(
            continuous.get("linear_models"),
            "continuous_univariable",
            statuses=("completed", "failed"),
        )
        continuous_adjusted = downstream_continuous_adjusted_reporting_model(
            continuous.get("linear_models"),
            user_requested=user_adjustment_requested,
        )
        continuous_spline = continuous.get("spline") or {}
        rmst = metrics.get("rmst") or {}
        audit = metrics.get("audit_report") or {}
        cutpoint = metrics.get("cutpoint_details") or {}
        row = {
            "index": request_index,
            "status": item.get("status"),
            "cached": result.get("cached"),
            "error": item.get("error"),
            "code": item.get("code"),
            "analysis_id": result.get("id"),
            "method": method,
            "cohort": result.get("cohort"),
            "gene_symbol": result.get("gene_symbol"),
            "endpoint": metrics.get("endpoint"),
            "endpoint_source": metrics.get("endpoint_source"),
            "adjustment_status": clinical_adjustment.get("status"),
            "adjustment_covariates": stable_json(
                clinical_adjustment.get("requested_covariates")
            ),
            "adjustment_label": clinical_adjustment.get("label"),
            "n_patients": metrics.get("n_patients"),
            "n_events": metrics.get("n_events"),
            "continuous_n_patients": continuous.get("n_patients"),
            "continuous_n_events": continuous.get("n_events"),
            "continuous_univariable_status": continuous_univariable.get("status"),
            "continuous_univariable_reason": continuous_univariable.get("reason"),
            "continuous_univariable_hr": continuous_univariable.get("hazard_ratio"),
            "continuous_univariable_hr_conf_low": continuous_univariable.get("hr_conf_low"),
            "continuous_univariable_hr_conf_high": continuous_univariable.get("hr_conf_high"),
            "continuous_univariable_p_value": continuous_univariable.get("p_value"),
            "continuous_bh_p_value": None,
            "continuous_univariable_ph_p_value": continuous_univariable.get("ph_p_value"),
            "continuous_univariable_ph_global_p_value": continuous_univariable.get(
                "ph_global_p_value"
            ),
            **model_information_fields(
                "continuous_univariable",
                continuous_univariable,
            ),
            **time_varying_effect_fields(
                "continuous_univariable",
                continuous_univariable,
            ),
            "continuous_adjusted_status": continuous_adjusted.get("status"),
            "continuous_adjusted_reason": continuous_adjusted.get("reason"),
            "continuous_adjusted_model": continuous_adjusted.get("model"),
            "continuous_adjusted_hr": continuous_adjusted.get("hazard_ratio"),
            "continuous_adjusted_hr_conf_low": continuous_adjusted.get("hr_conf_low"),
            "continuous_adjusted_hr_conf_high": continuous_adjusted.get("hr_conf_high"),
            "continuous_adjusted_p_value": continuous_adjusted.get("p_value"),
            "continuous_adjusted_ph_p_value": continuous_adjusted.get("ph_p_value"),
            "continuous_adjusted_ph_global_p_value": continuous_adjusted.get(
                "ph_global_p_value"
            ),
            **model_information_fields(
                "continuous_adjusted",
                continuous_adjusted,
            ),
            **time_varying_effect_fields(
                "continuous_adjusted",
                continuous_adjusted,
            ),
            "spline_status": continuous_spline.get("status"),
            "spline_overall_p_value": continuous_spline.get("overall_p_value"),
            "spline_nonlinearity_p_value": continuous_spline.get(
                "nonlinearity_p_value"
            ),
            "spline_nonlinearity_bh_p_value": None,
            "spline_reference_expression": continuous_spline.get(
                "reference_expression"
            ),
            "spline_knot_percentiles": stable_json(
                continuous_spline.get("knot_percentiles")
            ),
            "threshold": cutpoint.get("threshold"),
            "maxstat_corrected_p_value": cutpoint.get("corrected_p_value"),
            "maxstat_corrected_p_raw_value": cutpoint.get(
                "corrected_p_raw_value"
            ),
            "maxstat_corrected_p_clamped": cutpoint.get(
                "corrected_p_clamped"
            ),
            "maxstat_corrected_p_method": cutpoint.get("corrected_p_method"),
            "maxstat_corrected_p_status": cutpoint.get("corrected_p_status"),
            "custom_percentile": cutpoint.get("percentile"),
            "group_counts": stable_json(metrics.get("group_counts")),
            "event_counts": stable_json(metrics.get("event_counts")),
            "median_survival_days": stable_json(metrics.get("median_survival_days")),
            "logrank_p_value": metrics.get("logrank_p_value"),
            "univariable_status": univariable.get("status"),
            "univariable_reason": univariable.get("reason"),
            "univariable_hr": univariable.get("hazard_ratio"),
            "univariable_hr_conf_low": univariable.get("hr_conf_low"),
            "univariable_hr_conf_high": univariable.get("hr_conf_high"),
            "univariable_p_value": univariable.get("p_value"),
            **model_information_fields("univariable", univariable),
            **time_varying_effect_fields("univariable", univariable),
            "adjusted_status": adjusted.get("status"),
            "adjusted_reason": adjusted.get("reason"),
            "adjusted_model": adjusted.get("model"),
            "adjusted_hr": adjusted.get("hazard_ratio"),
            "adjusted_hr_conf_low": adjusted.get("hr_conf_low"),
            "adjusted_hr_conf_high": adjusted.get("hr_conf_high"),
            "adjusted_p_value": adjusted.get("p_value"),
            "adjusted_ph_p_value": adjusted.get("ph_p_value"),
            "adjusted_ph_global_p_value": adjusted.get("ph_global_p_value"),
            **model_information_fields("adjusted", adjusted),
            **time_varying_effect_fields("adjusted", adjusted),
            "rmst_status": rmst.get("status"),
            "rmst_tau_days": rmst.get("tau_days"),
            "rmst_tau_sensitivity": stable_json(rmst.get("tau_sensitivity")),
            "rmst_delta_days": (rmst.get("difference") or {}).get("estimate_days"),
            "rmst_delta_conf_low": (rmst.get("difference") or {}).get("conf_low"),
            "rmst_delta_conf_high": (rmst.get("difference") or {}).get("conf_high"),
            "rmst_p_value": (rmst.get("difference") or {}).get("p_value"),
            "audit_reproducibility_hash": audit.get("reproducibility_hash"),
            "patient_records_sha256": audit.get("patient_records_sha256"),
            "continuous_patient_records_sha256": audit.get(
                "continuous_patient_records_sha256"
            ),
            "downloads": stable_json(result.get("downloads")),
        }
        rows.append(row)
    return sorted(rows, key=lambda row: int(row.get("index") or 0))


def find_model(
    models: list[dict[str, Any]] | None,
    model_id: str,
    *,
    statuses: tuple[str, ...] = ("completed",),
) -> dict[str, Any]:
    for model in models or []:
        if model.get("model") == model_id and model.get("status") in statuses:
            return model
    return {}


def downstream_adjusted_model(
    models: list[dict[str, Any]] | None,
    *,
    user_requested: bool = False,
) -> dict[str, Any]:
    if user_requested:
        return find_model(models, "user_adjusted")
    return (
        find_model(models, "stage_grade_adjusted")
        or find_model(models, "stage_adjusted")
        or find_model(models, "grade_adjusted")
    )


def downstream_adjusted_reporting_model(
    models: list[dict[str, Any]] | None,
    *,
    user_requested: bool = False,
) -> dict[str, Any]:
    if user_requested:
        return find_model(
            models,
            "user_adjusted",
            statuses=("completed", "failed", "skipped"),
        )
    return downstream_adjusted_model(models) or (
        find_model(models, "stage_grade_adjusted", statuses=("failed",))
        or find_model(models, "stage_adjusted", statuses=("failed",))
        or find_model(models, "grade_adjusted", statuses=("failed",))
    )


def downstream_continuous_adjusted_model(
    models: list[dict[str, Any]] | None,
    *,
    user_requested: bool = False,
) -> dict[str, Any]:
    if user_requested:
        return find_model(models, "continuous_user_adjusted")
    return (
        find_model(models, "continuous_stage_grade_adjusted")
        or find_model(models, "continuous_stage_adjusted")
        or find_model(models, "continuous_grade_adjusted")
    )


def downstream_continuous_adjusted_reporting_model(
    models: list[dict[str, Any]] | None,
    *,
    user_requested: bool = False,
) -> dict[str, Any]:
    if user_requested:
        return find_model(
            models,
            "continuous_user_adjusted",
            statuses=("completed", "failed", "skipped"),
        )
    return downstream_continuous_adjusted_model(models) or (
        find_model(models, "continuous_stage_grade_adjusted", statuses=("failed",))
        or find_model(models, "continuous_stage_adjusted", statuses=("failed",))
        or find_model(models, "continuous_grade_adjusted", statuses=("failed",))
    )


def model_information_fields(prefix: str, model: dict[str, Any]) -> dict[str, Any]:
    information = model.get("information_diagnostics") or {}
    firth = model.get("penalized_sensitivity") or {}
    return {
        f"{prefix}_parameter_count": information.get("parameter_count"),
        f"{prefix}_events_per_parameter": information.get("events_per_parameter"),
        f"{prefix}_information_status": information.get("status"),
        f"{prefix}_firth_status": firth.get("status"),
        f"{prefix}_firth_hr": firth.get("hazard_ratio"),
        f"{prefix}_firth_hr_conf_low": firth.get("hr_conf_low"),
        f"{prefix}_firth_hr_conf_high": firth.get("hr_conf_high"),
        f"{prefix}_firth_p_value": firth.get("p_value"),
        f"{prefix}_firth_ties": firth.get("ties"),
        f"{prefix}_firth_trigger_reasons": stable_json(
            firth.get("trigger_reasons")
        ),
    }


def time_varying_effect_fields(
    prefix: str,
    model: dict[str, Any],
) -> dict[str, Any]:
    diagnostic = model.get("time_varying_effect") or {}
    periods = diagnostic.get("periods") or {}
    early = periods.get("early") or {}
    late = periods.get("late") or {}
    change = diagnostic.get("change") or {}
    support = diagnostic.get("support") or {}
    return {
        f"{prefix}_temporal_status": diagnostic.get("status"),
        f"{prefix}_temporal_reason": diagnostic.get("reason"),
        f"{prefix}_temporal_split_days": diagnostic.get("split_days"),
        f"{prefix}_temporal_early_events": support.get("early_events"),
        f"{prefix}_temporal_early_hr": early.get("hazard_ratio"),
        f"{prefix}_temporal_early_hr_conf_low": early.get("hr_conf_low"),
        f"{prefix}_temporal_early_hr_conf_high": early.get("hr_conf_high"),
        f"{prefix}_temporal_early_p_value": early.get("p_value"),
        f"{prefix}_temporal_late_events": support.get("late_events"),
        f"{prefix}_temporal_at_risk_at_split": support.get(
            "at_risk_at_split"
        ),
        f"{prefix}_temporal_late_hr": late.get("hazard_ratio"),
        f"{prefix}_temporal_late_hr_conf_low": late.get("hr_conf_low"),
        f"{prefix}_temporal_late_hr_conf_high": late.get("hr_conf_high"),
        f"{prefix}_temporal_late_p_value": late.get("p_value"),
        f"{prefix}_temporal_late_to_early_hr_ratio": change.get(
            "hazard_ratio_ratio"
        ),
        f"{prefix}_temporal_late_to_early_hr_ratio_conf_low": change.get(
            "hr_ratio_conf_low"
        ),
        f"{prefix}_temporal_late_to_early_hr_ratio_conf_high": change.get(
            "hr_ratio_conf_high"
        ),
        f"{prefix}_temporal_late_to_early_p_value": change.get("p_value"),
    }


def apply_bh(rows: list[dict[str, Any]], p_key: str, out_key: str) -> None:
    indexed = [
        (index, float(row[p_key]))
        for index, row in enumerate(rows)
        if is_finite_number(row.get(p_key))
    ]
    m = len(indexed)
    previous = 1.0
    adjusted_by_index: dict[int, float] = {}
    for rank_from_end, (index, p_value) in enumerate(sorted(indexed, key=lambda item: item[1], reverse=True), start=1):
        rank = m - rank_from_end + 1
        adjusted = min(previous, p_value * m / rank)
        previous = adjusted
        adjusted_by_index[index] = min(adjusted, 1.0)
    for index, row in enumerate(rows):
        row[out_key] = adjusted_by_index.get(index)


def assign_grouped_family_p_values(rows: list[dict[str, Any]]) -> None:
    for row in rows:
        method = str(row.get("method") or "")
        if method == "maxstat":
            corrected = row.get("maxstat_corrected_p_value")
            corrected_status = row.get("maxstat_corrected_p_status")
            if corrected_status == "completed" and is_finite_number(corrected):
                row["grouped_family_p_value"] = float(corrected)
                row["grouped_family_input"] = "maxstat_lau94_corrected"
            else:
                row["grouped_family_p_value"] = None
                row["grouped_family_input"] = "maxstat_corrected_unavailable"
        else:
            logrank = row.get("logrank_p_value")
            row["grouped_family_p_value"] = (
                float(logrank) if is_finite_number(logrank) else None
            )
            row["grouped_family_input"] = "prespecified_logrank"
        row["multiplicity_scope"] = "within_scenario_holm"


def apply_holm(rows: list[dict[str, Any]], p_key: str, out_key: str) -> None:
    indexed = [
        (index, float(row[p_key]))
        for index, row in enumerate(rows)
        if is_finite_number(row.get(p_key))
    ]
    adjusted_by_index: dict[int, float] = {}
    running_max = 0.0
    total = len(indexed)
    for rank, (index, p_value) in enumerate(
        sorted(indexed, key=lambda item: item[1]),
        start=1,
    ):
        adjusted = min(1.0, (total - rank + 1) * p_value)
        running_max = max(running_max, adjusted)
        adjusted_by_index[index] = running_max
    for index, row in enumerate(rows):
        row[out_key] = adjusted_by_index.get(index)


def set_legacy_grouped_multiplicity_aliases(row: dict[str, Any]) -> None:
    holm_p = row.get("grouped_holm_p_value")
    row["grouped_holm_below_alpha"] = is_significant(holm_p)
    # Kept only so older frozen frontend/catalog readers do not fail. New
    # manuscript and UI code must use the grouped_holm_* fields.
    row["bh_logrank_p_value"] = holm_p
    row["bh_within_scenario_logrank_p_value"] = holm_p


def annotate_same_contrast_effects(
    rows: list[dict[str, Any]],
    client: ApiClient,
) -> None:
    for row in rows:
        analysis_id = str(row.get("analysis_id") or "")
        if not analysis_id:
            set_same_contrast_unavailable(row, "Analysis ID is unavailable.")
            continue
        try:
            audit = client.get(
                f"/api/v1/analyses/{urllib.parse.quote(analysis_id)}/download/audit_json"
            )
            annotate_same_contrast_effect(row, audit)
        except (RuntimeError, TypeError, ValueError, statistics.StatisticsError) as exc:
            set_same_contrast_unavailable(row, str(exc))


def annotate_same_contrast_effect(
    row: dict[str, Any],
    audit: dict[str, Any],
) -> None:
    cohort_selection = audit.get("cohort_selection") or {}
    grouped_records = cohort_selection.get("patient_records") or []
    continuous_records = cohort_selection.get("continuous_patient_records") or []
    univariable = find_model(
        (audit.get("results") or {}).get("cox_models"),
        "univariable",
    )
    contrast = str(univariable.get("contrast") or "")
    if " vs " not in contrast:
        raise ValueError("Grouped Cox contrast is unavailable.")
    comparison_group, reference_group = [
        part.strip() for part in contrast.split(" vs ", maxsplit=1)
    ]
    grouped_values: dict[str, list[float]] = {}
    for record in grouped_records:
        group = str(record.get("group") or "")
        expression = record.get("expression_value")
        if group and is_finite_number(expression):
            grouped_values.setdefault(group, []).append(float(expression))
    comparison_values = grouped_values.get(comparison_group) or []
    reference_values = grouped_values.get(reference_group) or []
    all_values = [
        float(record["expression_value"])
        for record in continuous_records
        if is_finite_number(record.get("expression_value"))
    ]
    if not comparison_values or not reference_values:
        raise ValueError(
            f"Expression values are unavailable for contrast {contrast}."
        )
    if len(all_values) < 2:
        raise ValueError("Continuous expression SD is not estimable.")
    expression_sd = statistics.stdev(all_values)
    if not is_finite_number(expression_sd) or expression_sd <= 0:
        raise ValueError("Continuous expression SD is zero or non-finite.")
    continuous_hr = row.get("continuous_univariable_hr")
    grouped_hr = row.get("univariable_hr")
    if (
        not is_finite_number(continuous_hr)
        or float(continuous_hr) <= 0
        or not is_finite_number(grouped_hr)
        or float(grouped_hr) <= 0
    ):
        raise ValueError("A positive grouped and continuous HR is required.")

    comparison_mean = statistics.fmean(comparison_values)
    reference_mean = statistics.fmean(reference_values)
    delta_expression = comparison_mean - reference_mean
    delta_sd = delta_expression / expression_sd
    continuous_log_hr_same_contrast = math.log(float(continuous_hr)) * delta_sd
    grouped_log_hr = math.log(float(grouped_hr))
    implied_hr = math.exp(continuous_log_hr_same_contrast)
    direction_concordant = (
        grouped_log_hr == 0
        and continuous_log_hr_same_contrast == 0
    ) or grouped_log_hr * continuous_log_hr_same_contrast > 0
    amplification_ratio = (
        abs(grouped_log_hr) / abs(continuous_log_hr_same_contrast)
        if continuous_log_hr_same_contrast != 0
        else None
    )

    row.update(
        {
            "same_contrast_status": "completed",
            "same_contrast_reason": None,
            "same_contrast_label": contrast,
            "same_contrast_comparison_group": comparison_group,
            "same_contrast_reference_group": reference_group,
            "same_contrast_comparison_n": len(comparison_values),
            "same_contrast_reference_n": len(reference_values),
            "same_contrast_comparison_mean": comparison_mean,
            "same_contrast_reference_mean": reference_mean,
            "same_contrast_expression_sd": expression_sd,
            "same_contrast_delta_expression": delta_expression,
            "same_contrast_delta_sd": delta_sd,
            "continuous_implied_same_contrast_hr": implied_hr,
            "continuous_implied_same_contrast_log_hr": (
                continuous_log_hr_same_contrast
            ),
            "grouped_same_contrast_hr": float(grouped_hr),
            "grouped_same_contrast_log_hr": grouped_log_hr,
            "same_contrast_direction_concordant": direction_concordant,
            "same_contrast_log_hr_amplification_ratio": amplification_ratio,
            "same_contrast_absolute_log_hr_excess": (
                abs(grouped_log_hr) - abs(continuous_log_hr_same_contrast)
            ),
        }
    )


def set_same_contrast_unavailable(row: dict[str, Any], reason: str) -> None:
    row.update(
        {
            "same_contrast_status": "unavailable",
            "same_contrast_reason": reason,
            "same_contrast_label": None,
            "same_contrast_comparison_group": None,
            "same_contrast_reference_group": None,
            "same_contrast_comparison_n": None,
            "same_contrast_reference_n": None,
            "same_contrast_comparison_mean": None,
            "same_contrast_reference_mean": None,
            "same_contrast_expression_sd": None,
            "same_contrast_delta_expression": None,
            "same_contrast_delta_sd": None,
            "continuous_implied_same_contrast_hr": None,
            "continuous_implied_same_contrast_log_hr": None,
            "grouped_same_contrast_hr": None,
            "grouped_same_contrast_log_hr": None,
            "same_contrast_direction_concordant": None,
            "same_contrast_log_hr_amplification_ratio": None,
            "same_contrast_absolute_log_hr_excess": None,
        }
    )


def annotate_evidence_profile(
    row: dict[str, Any],
    *,
    grouped_key: str = "grouped_holm_p_value",
) -> None:
    grouped_value = row.get(grouped_key)
    if grouped_value is None:
        grouped_value = row.get("bh_logrank_p_value")
    grouped_holm_below_alpha = is_significant(grouped_value)
    cox_below_alpha = is_significant(row.get("univariable_p_value"))
    adjusted_below_alpha = is_significant(row.get("adjusted_p_value"))
    rmst_available = row.get("rmst_status") == "completed" and is_finite_number(
        row.get("rmst_delta_days")
    )
    rmst_below_alpha = rmst_available and is_significant(row.get("rmst_p_value"))
    marker_ph_value = row.get("adjusted_ph_p_value")
    marker_ph_evaluable = is_finite_number(marker_ph_value)
    marker_ph_flagged = marker_ph_evaluable and float(marker_ph_value) < EVIDENCE_ALPHA
    global_ph_value = row.get("adjusted_ph_global_p_value")
    global_ph_evaluable = is_finite_number(global_ph_value)
    global_ph_flagged = global_ph_evaluable and float(global_ph_value) < EVIDENCE_ALPHA
    maxstat_p_available = row.get("method") != "maxstat" or (
        row.get("maxstat_corrected_p_status") == "completed"
        and is_finite_number(row.get("maxstat_corrected_p_value"))
    )
    maxstat_corrected_p_below_alpha = row.get("method") != "maxstat" or is_significant(
        row.get("maxstat_corrected_p_value")
    )
    hr = row.get("univariable_hr")
    row["direction"] = (
        "Protective"
        if is_finite_number(hr) and float(hr) < 1
        else "Harmful"
        if is_finite_number(hr) and float(hr) > 1
        else ""
    )
    notes = []
    if not row.get("adjusted_model"):
        notes.append("Adjusted Cox not evaluable")
    elif row.get("adjusted_status") == "skipped":
        notes.append("Requested adjusted Cox not evaluable")
    elif row.get("adjusted_status") == "failed":
        notes.append("Standard adjusted Cox failed")
    if not rmst_available:
        notes.append("RMST not evaluable")
    if marker_ph_flagged:
        temporal_status = row.get("adjusted_temporal_status")
        if temporal_status == "completed":
            notes.append(
                "Marker-specific PH caution; fixed 2-year diagnostic estimated"
            )
        elif temporal_status in {"skipped", "failed"}:
            notes.append(
                "Marker-specific PH caution; fixed 2-year diagnostic "
                f"{temporal_status}"
            )
        else:
            notes.append("Marker-specific PH caution")
    elif global_ph_flagged:
        notes.append("Global PH caution; marker term not flagged")
    if row.get("method") == "maxstat":
        notes.append("Outcome-optimized cutpoint; grouped estimates are post-selection")
        if str(row.get("maxstat_corrected_p_clamped")).lower() == "true":
            notes.append(
                "Raw Lau94 approximation lay outside [0,1] and was clamped"
            )
    if row.get("method") == "upper_lower_quartile":
        notes.append("Middle 50% excluded")
    adjusted_information_status = row.get("adjusted_information_status")
    if adjusted_information_status in {"caution", "severe"}:
        notes.append(
            "Adjusted Cox "
            f"{format_number(row.get('adjusted_events_per_parameter'), digits=1)} "
            f"events/parameter ({adjusted_information_status})"
        )
    if row.get("adjusted_firth_status") == "completed":
        notes.append(
            "Firth adjusted sensitivity "
            f"HR {format_prefixed_hr(row, 'adjusted_firth')}, "
            f"p {format_p(row.get('adjusted_firth_p_value'))}"
        )
    if not notes:
        notes.append("No model-diagnostic caution recorded")
    row["grouped_holm_below_alpha"] = grouped_holm_below_alpha
    row["bh_below_alpha"] = grouped_holm_below_alpha
    row["univariable_p_below_alpha"] = cox_below_alpha
    row["adjusted_p_below_alpha"] = adjusted_below_alpha
    row["rmst_available"] = rmst_available
    row["rmst_p_below_alpha"] = rmst_below_alpha
    row["marker_ph_evaluable"] = marker_ph_evaluable
    row["marker_ph_flagged"] = marker_ph_flagged
    row["global_ph_evaluable"] = global_ph_evaluable
    row["global_ph_flagged"] = global_ph_flagged
    row["maxstat_p_available"] = maxstat_p_available
    row["maxstat_corrected_p_below_alpha"] = maxstat_corrected_p_below_alpha
    row["profile_notes"] = "; ".join(notes)


def is_significant(value: Any) -> bool:
    return is_finite_number(value) and float(value) <= EVIDENCE_ALPHA


def is_finite_number(value: Any) -> bool:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(number)


def time_varying_fieldnames(prefix: str) -> list[str]:
    suffixes = [
        "status",
        "reason",
        "split_days",
        "early_events",
        "early_hr",
        "early_hr_conf_low",
        "early_hr_conf_high",
        "early_p_value",
        "late_events",
        "at_risk_at_split",
        "late_hr",
        "late_hr_conf_low",
        "late_hr_conf_high",
        "late_p_value",
        "late_to_early_hr_ratio",
        "late_to_early_hr_ratio_conf_low",
        "late_to_early_hr_ratio_conf_high",
        "late_to_early_p_value",
    ]
    return [f"{prefix}_temporal_{suffix}" for suffix in suffixes]


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = [
        "method",
        "status",
        "cached",
        "analysis_id",
        "cohort",
        "gene_symbol",
        "endpoint",
        "endpoint_source",
        "adjustment_status",
        "adjustment_covariates",
        "adjustment_label",
        "n_patients",
        "n_events",
        "continuous_n_patients",
        "continuous_n_events",
        "continuous_univariable_status",
        "continuous_univariable_reason",
        "continuous_univariable_hr",
        "continuous_univariable_hr_conf_low",
        "continuous_univariable_hr_conf_high",
        "continuous_univariable_p_value",
        "continuous_bh_p_value",
        "continuous_univariable_ph_p_value",
        "continuous_univariable_ph_global_p_value",
        "continuous_univariable_parameter_count",
        "continuous_univariable_events_per_parameter",
        "continuous_univariable_information_status",
        "continuous_univariable_firth_status",
        "continuous_univariable_firth_hr",
        "continuous_univariable_firth_hr_conf_low",
        "continuous_univariable_firth_hr_conf_high",
        "continuous_univariable_firth_p_value",
        "continuous_univariable_firth_ties",
        "continuous_univariable_firth_trigger_reasons",
        *time_varying_fieldnames("continuous_univariable"),
        "continuous_adjusted_status",
        "continuous_adjusted_reason",
        "continuous_adjusted_model",
        "continuous_adjusted_hr",
        "continuous_adjusted_hr_conf_low",
        "continuous_adjusted_hr_conf_high",
        "continuous_adjusted_p_value",
        "continuous_adjusted_ph_p_value",
        "continuous_adjusted_ph_global_p_value",
        "continuous_adjusted_parameter_count",
        "continuous_adjusted_events_per_parameter",
        "continuous_adjusted_information_status",
        "continuous_adjusted_firth_status",
        "continuous_adjusted_firth_hr",
        "continuous_adjusted_firth_hr_conf_low",
        "continuous_adjusted_firth_hr_conf_high",
        "continuous_adjusted_firth_p_value",
        "continuous_adjusted_firth_ties",
        "continuous_adjusted_firth_trigger_reasons",
        *time_varying_fieldnames("continuous_adjusted"),
        "spline_status",
        "spline_overall_p_value",
        "spline_nonlinearity_p_value",
        "spline_nonlinearity_bh_p_value",
        "spline_reference_expression",
        "spline_knot_percentiles",
        "threshold",
        "maxstat_corrected_p_value",
        "maxstat_corrected_p_raw_value",
        "maxstat_corrected_p_clamped",
        "maxstat_corrected_p_method",
        "maxstat_corrected_p_status",
        "custom_percentile",
        "logrank_p_value",
        "grouped_family_p_value",
        "grouped_family_input",
        "grouped_holm_p_value",
        "grouped_holm_below_alpha",
        "bh_within_scenario_logrank_p_value",
        "bh_logrank_p_value",
        "multiplicity_scope",
        "univariable_status",
        "univariable_reason",
        "univariable_hr",
        "univariable_hr_conf_low",
        "univariable_hr_conf_high",
        "univariable_p_value",
        "univariable_parameter_count",
        "univariable_events_per_parameter",
        "univariable_information_status",
        "univariable_firth_status",
        "univariable_firth_hr",
        "univariable_firth_hr_conf_low",
        "univariable_firth_hr_conf_high",
        "univariable_firth_p_value",
        "univariable_firth_ties",
        "univariable_firth_trigger_reasons",
        *time_varying_fieldnames("univariable"),
        "adjusted_status",
        "adjusted_reason",
        "adjusted_model",
        "adjusted_hr",
        "adjusted_hr_conf_low",
        "adjusted_hr_conf_high",
        "adjusted_p_value",
        "adjusted_ph_p_value",
        "adjusted_ph_global_p_value",
        "adjusted_parameter_count",
        "adjusted_events_per_parameter",
        "adjusted_information_status",
        "adjusted_firth_status",
        "adjusted_firth_hr",
        "adjusted_firth_hr_conf_low",
        "adjusted_firth_hr_conf_high",
        "adjusted_firth_p_value",
        "adjusted_firth_ties",
        "adjusted_firth_trigger_reasons",
        *time_varying_fieldnames("adjusted"),
        "rmst_status",
        "rmst_tau_days",
        "rmst_tau_sensitivity",
        "rmst_delta_days",
        "rmst_delta_conf_low",
        "rmst_delta_conf_high",
        "rmst_p_value",
        "direction",
        "bh_below_alpha",
        "univariable_p_below_alpha",
        "adjusted_p_below_alpha",
        "rmst_available",
        "rmst_p_below_alpha",
        "marker_ph_evaluable",
        "marker_ph_flagged",
        "global_ph_evaluable",
        "global_ph_flagged",
        "maxstat_p_available",
        "maxstat_corrected_p_below_alpha",
        "same_contrast_status",
        "same_contrast_reason",
        "same_contrast_label",
        "same_contrast_comparison_group",
        "same_contrast_reference_group",
        "same_contrast_comparison_n",
        "same_contrast_reference_n",
        "same_contrast_comparison_mean",
        "same_contrast_reference_mean",
        "same_contrast_expression_sd",
        "same_contrast_delta_expression",
        "same_contrast_delta_sd",
        "continuous_implied_same_contrast_hr",
        "continuous_implied_same_contrast_log_hr",
        "grouped_same_contrast_hr",
        "grouped_same_contrast_log_hr",
        "same_contrast_direction_concordant",
        "same_contrast_log_hr_amplification_ratio",
        "same_contrast_absolute_log_hr_excess",
        "profile_notes",
        "audit_reproducibility_hash",
        "patient_records_sha256",
        "continuous_patient_records_sha256",
        "group_counts",
        "event_counts",
        "median_survival_days",
        "downloads",
        "error",
        "code",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def write_markdown(path: Path, metadata: dict[str, Any], rows: list[dict[str, Any]]) -> None:
    cached_count = sum(1 for row in rows if row.get("cached"))
    multiple_testing = metadata.get("multiple_testing") or {}
    multiplicity_family = multiple_testing.get("grouped_family") or (
        "completed cutpoint methods in this scenario"
    )
    continuous_reference = next(
        (
            row
            for row in rows
            if is_finite_number(row.get("continuous_univariable_hr"))
        ),
        {},
    )
    lines = [
        f"# {metadata['title']}",
        "",
        f"- Run started: {metadata['started_at']}",
        f"- Run finished: {metadata['finished_at']}",
        f"- Completed analyses: {metadata['batch']['completed']}/{metadata['batch']['total']}",
        f"- Cached analyses in this run: {cached_count}/{len(rows)}",
        f"- API base URL: `{metadata['api_base_url']}`",
        f"- Cohort: `{metadata['cohort']}`",
        f"- Gene: `{metadata['resolved_gene']}`",
        f"- Endpoint: `{metadata['endpoint']}`",
        f"- Expression scale: `{metadata['expression_scale']}`",
        (
            "- Prespecified complete-case Cox adjustment: "
            + (
                ", ".join(metadata.get("adjustment_covariates") or [])
                if metadata.get("adjustment_covariates")
                else "none"
            )
            + "."
        ),
        f"- Grouped-test family: {multiplicity_family}.",
        (
            "- Grouped multiplicity: Holm adjustment within this scenario. "
            "The maxstat member contributes its Lau94 selection-adjusted "
            "rank-statistic p-value; the other prespecified rules contribute "
            "their log-rank p-values."
        ),
        "- No composite retention rule is applied. Log-rank, Cox and RMST are related summaries of the same outcomes and are not counted as independent barriers.",
        "- Marker-specific PH and global model PH are reported separately as interpretation diagnostics.",
        "- Maxstat is outcome-optimized. Its corrected rank-statistic p-value is reported, while grouped HR, confidence intervals and RMST remain post-selection.",
        (
            "- Cutpoint-independent continuous reference: "
            f"n={format_int(continuous_reference.get('continuous_n_patients'))}, "
            f"events={format_int(continuous_reference.get('continuous_n_events'))}, "
            f"HR per +1 SD={format_continuous_hr(continuous_reference)}, "
            f"linear p={format_p(continuous_reference.get('continuous_univariable_p_value'))}, "
            f"linear suite BH q={format_p(continuous_reference.get('continuous_bh_p_value'))}, "
            f"events/parameter={format_number(continuous_reference.get('continuous_univariable_events_per_parameter'), digits=1)}, "
            f"nonlinearity p={format_p(continuous_reference.get('spline_nonlinearity_p_value'))}, "
            f"nonlinearity suite BH q={format_p(continuous_reference.get('spline_nonlinearity_bh_p_value'))}."
            if continuous_reference
            else "- Cutpoint-independent continuous reference was not evaluable."
        ),
        "",
        "| Method | n | Events | Family p | Holm p | HR | Cox p | Adjusted HR | Adjusted p | Marker PH p | Global PH p | RMST delta @ tau | RMST p | Same-contrast HRs | Notes |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |",
    ]
    for row in rows:
        lines.append(
            "| {method} | {n} | {events} | {family_p} | {holm} | {hr} | {cox} | {adjusted_hr} | {adj} | {marker_ph} | {global_ph} | {rmst_delta} @ {tau} | {rmst_p} | {same_contrast} | {notes} |".format(
                method=row.get("method") or "",
                n=format_int(row.get("n_patients")),
                events=format_int(row.get("n_events")),
                family_p=format_p(row.get("grouped_family_p_value")),
                holm=format_p(row.get("grouped_holm_p_value")),
                hr=format_hr(row),
                cox=format_p(row.get("univariable_p_value")),
                adjusted_hr=format_adjusted_hr(row),
                adj=format_p(row.get("adjusted_p_value")),
                marker_ph=format_p(row.get("adjusted_ph_p_value")),
                global_ph=format_p(row.get("adjusted_ph_global_p_value")),
                rmst_delta=format_number(row.get("rmst_delta_days"), digits=0),
                tau=format_number(row.get("rmst_tau_days"), digits=0),
                rmst_p=format_p(row.get("rmst_p_value")),
                same_contrast=format_same_contrast(row),
                notes=row.get("profile_notes") or "",
            )
        )
    lines.extend(
        [
            "",
            "## Audit Hashes",
            "",
            "| Method | Analysis ID | Reproducibility hash | Grouped records SHA-256 | Continuous records SHA-256 |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for row in rows:
        lines.append(
            f"| {row.get('method') or ''} | `{row.get('analysis_id') or ''}` | "
            f"`{row.get('audit_reproducibility_hash') or ''}` | `{row.get('patient_records_sha256') or ''}` | "
            f"`{row.get('continuous_patient_records_sha256') or ''}` |"
        )
    tau_lines = rmst_tau_sensitivity_lines(rows)
    if tau_lines:
        lines.extend(["", "## RMST Tau Sensitivity", ""])
        lines.extend(tau_lines)
    firth_lines = firth_sensitivity_lines(rows)
    if firth_lines:
        lines.extend(["", "## Low-information and Firth Sensitivities", ""])
        lines.extend(firth_lines)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_latex_table(path: Path, metadata: dict[str, Any], rows: list[dict[str, Any]]) -> None:
    latex_id = latex_escape(str(metadata["benchmark_id"]).replace("_", "-"))
    caption = latex_escape(str(metadata["title"]).replace("cutpoint benchmark", "cutpoint-sensitivity benchmark"))
    lines = [
        "\\begin{table}[t]",
        "\\centering",
        f"\\caption{{{caption}.}}",
        f"\\label{{tab:{latex_id}}}",
        "\\begin{tabular}{lrrrrrrl}",
        "\\toprule",
        "Method & n & Events & Holm $p$ & Adj. $p$ & Marker PH $p$ & RMST $\\Delta$ & Notes \\\\",
        "\\midrule",
    ]
    for row in rows:
        profile = latex_profile_label(row)
        lines.append(
            " & ".join(
                [
                    latex_escape(method_label(str(row.get("method") or ""))),
                    format_int(row.get("n_patients")),
                    format_int(row.get("n_events")),
                    format_p(row.get("grouped_holm_p_value")),
                    format_p(row.get("adjusted_p_value")),
                    format_p(row.get("adjusted_ph_p_value")),
                    format_number(row.get("rmst_delta_days"), digits=0),
                    latex_escape(profile),
                ]
            )
            + " \\\\"
        )
    lines.extend(["\\bottomrule", "\\end{tabular}", "\\end{table}", ""])
    path.write_text("\n".join(lines), encoding="utf-8")


def latex_profile_label(row: dict[str, Any]) -> str:
    return str(row.get("profile_notes") or "No model-diagnostic caution")


def stable_json(value: Any) -> str:
    if value is None:
        return ""
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def rmst_tau_sensitivity_lines(rows: list[dict[str, Any]]) -> list[str]:
    lines = [
        "| Method | Tau fraction | Tau days | RMST delta days | RMST p |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    count = 0
    for row in rows:
        try:
            tau_values = json.loads(row.get("rmst_tau_sensitivity") or "[]")
        except json.JSONDecodeError:
            tau_values = []
        for item in tau_values:
            if item.get("status") != "completed":
                continue
            lines.append(
                "| {method} | {fraction} | {tau_days} | {delta} | {p_value} |".format(
                    method=row.get("method") or "",
                    fraction=format_number(item.get("tau_fraction"), digits=2),
                    tau_days=format_number(item.get("tau_days"), digits=1),
                    delta=format_number(item.get("estimate_days"), digits=0),
                    p_value=format_p(item.get("p_value")),
                )
            )
            count += 1
    return lines if count else []


def firth_sensitivity_lines(rows: list[dict[str, Any]]) -> list[str]:
    lines = [
        "| Method | Model family | Events / parameter | Information status | Firth HR (95% CI) | Firth p | Ties |",
        "| --- | --- | ---: | --- | ---: | ---: | --- |",
    ]
    count = 0
    for row in rows:
        for family, label in (
            ("continuous_adjusted", "Continuous adjusted"),
            ("adjusted", "Grouped adjusted"),
        ):
            if row.get(f"{family}_firth_status") != "completed":
                continue
            lines.append(
                "| {method} | {label} | {events_per_parameter} | {status} | {hr} | {p_value} | {ties} |".format(
                    method=row.get("method") or "",
                    label=label,
                    events_per_parameter=format_number(
                        row.get(f"{family}_events_per_parameter"),
                        digits=1,
                    ),
                    status=row.get(f"{family}_information_status") or "",
                    hr=format_prefixed_hr(row, f"{family}_firth"),
                    p_value=format_p(row.get(f"{family}_firth_p_value")),
                    ties=row.get(f"{family}_firth_ties") or "",
                )
            )
            count += 1
    return lines if count else []


def method_label(method: str) -> str:
    return {
        "maxstat": "Maxstat",
        "median": "Median",
        "upper_quartile": "Upper Q",
        "upper_lower_quartile": "Outer Q",
        "percentile": "Custom pct.",
    }.get(method, method)


def slugify(value: str) -> str:
    slug = "".join(char.lower() if char.isalnum() else "_" for char in value)
    while "__" in slug:
        slug = slug.replace("__", "_")
    return slug.strip("_")


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def format_p(value: Any) -> str:
    if not is_finite_number(value):
        return ""
    number = float(value)
    if number < 0.001:
        return f"{number:.2e}"
    return f"{number:.3f}"


def format_hr(row: dict[str, Any]) -> str:
    hr = row.get("univariable_hr")
    low = row.get("univariable_hr_conf_low")
    high = row.get("univariable_hr_conf_high")
    if not (is_finite_number(hr) and is_finite_number(low) and is_finite_number(high)):
        return ""
    return f"{float(hr):.2f} ({float(low):.2f}-{float(high):.2f})"


def format_adjusted_hr(row: dict[str, Any]) -> str:
    hr = row.get("adjusted_hr")
    low = row.get("adjusted_hr_conf_low")
    high = row.get("adjusted_hr_conf_high")
    if not (is_finite_number(hr) and is_finite_number(low) and is_finite_number(high)):
        return ""
    return f"{float(hr):.2f} ({float(low):.2f}-{float(high):.2f})"


def format_continuous_hr(row: dict[str, Any]) -> str:
    hr = row.get("continuous_univariable_hr")
    low = row.get("continuous_univariable_hr_conf_low")
    high = row.get("continuous_univariable_hr_conf_high")
    if not (is_finite_number(hr) and is_finite_number(low) and is_finite_number(high)):
        return ""
    return f"{float(hr):.2f} ({float(low):.2f}-{float(high):.2f})"


def format_same_contrast(row: dict[str, Any]) -> str:
    if row.get("same_contrast_status") != "completed":
        return "not estimable"
    grouped = row.get("grouped_same_contrast_hr")
    implied = row.get("continuous_implied_same_contrast_hr")
    amplification = row.get("same_contrast_log_hr_amplification_ratio")
    if not (is_finite_number(grouped) and is_finite_number(implied)):
        return "not estimable"
    amplification_text = (
        f"; absolute log-HR ratio {float(amplification):.2f}"
        if is_finite_number(amplification)
        else ""
    )
    return (
        f"grouped {float(grouped):.2f} vs continuous-implied "
        f"{float(implied):.2f}{amplification_text}"
    )


def format_prefixed_hr(row: dict[str, Any], prefix: str) -> str:
    hr = row.get(f"{prefix}_hr")
    low = row.get(f"{prefix}_hr_conf_low")
    high = row.get(f"{prefix}_hr_conf_high")
    if not (is_finite_number(hr) and is_finite_number(low) and is_finite_number(high)):
        return ""
    return f"{float(hr):.2f} ({float(low):.2f}-{float(high):.2f})"


def format_int(value: Any) -> str:
    if not is_finite_number(value):
        return ""
    return str(int(round(float(value))))


def format_number(value: Any, *, digits: int) -> str:
    if not is_finite_number(value):
        return ""
    return f"{float(value):.{digits}f}"


def latex_escape(value: str) -> str:
    replacements = {
        "\\": "\\textbackslash{}",
        "&": "\\&",
        "%": "\\%",
        "$": "\\$",
        "#": "\\#",
        "_": "\\_",
        "{": "\\{",
        "}": "\\}",
        "~": "\\textasciitilde{}",
        "^": "\\textasciicircum{}",
    }
    return "".join(replacements.get(char, char) for char in value)


def utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


if __name__ == "__main__":
    sys.exit(main())
