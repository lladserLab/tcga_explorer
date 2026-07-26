#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = ROOT / "docs" / "publication" / "benchmark" / "feature_benchmarks"
TABLE_PATH = ROOT / "manuscript" / "bioinformatics_app_note" / "tables" / "feature_benchmark_summary.tex"
DIAGNOSTIC_TABLE_PATH = (
    ROOT / "manuscript" / "bioinformatics_app_note" / "tables" / "feature_benchmark_diagnostic_summary.tex"
)
SIGNATURE_TABLE_PATH = (
    ROOT / "manuscript" / "bioinformatics_app_note" / "tables" / "feature_signature_definitions.tex"
)

ACC_BUB1B_PINK1_SIGNATURE = [
    {"gene_symbol": "BUB1B", "weight": 1.0},
    {"gene_symbol": "PINK1", "weight": -1.0},
]

UVM_BAP1_MARKER = [{"gene_symbol": "BAP1", "weight": 1.0}]
UVM_PRAME_MARKER = [{"gene_symbol": "PRAME", "weight": 1.0}]
BIRC5_MARKER = [{"gene_symbol": "BIRC5", "weight": 1.0}]

HYPOXIA_SIGNATURE = [
    {"gene_symbol": "CA9", "weight": 1.0},
    {"gene_symbol": "VEGFA", "weight": 1.0},
    {"gene_symbol": "SLC2A1", "weight": 1.0},
    {"gene_symbol": "LDHA", "weight": 1.0},
    {"gene_symbol": "PGK1", "weight": 1.0},
]

EFFECTOR_SIGNATURE = [
    {"gene_symbol": "CD8A", "weight": 1.0},
    {"gene_symbol": "GZMB", "weight": 1.0},
    {"gene_symbol": "PRF1", "weight": 1.0},
    {"gene_symbol": "IFNG", "weight": 1.0},
    {"gene_symbol": "CXCL9", "weight": 1.0},
    {"gene_symbol": "CXCL10", "weight": 1.0},
]

EXHAUSTION_SIGNATURE = [
    {"gene_symbol": "PDCD1", "weight": 1.0},
    {"gene_symbol": "CTLA4", "weight": 1.0},
    {"gene_symbol": "LAG3", "weight": 1.0},
    {"gene_symbol": "HAVCR2", "weight": 1.0},
    {"gene_symbol": "TIGIT", "weight": 1.0},
]

PRESPECIFIED_ADJUSTMENT = ["age_at_index"]


def main() -> int:
    args = parse_args()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    TABLE_PATH.parent.mkdir(parents=True, exist_ok=True)

    started_at = utc_now()
    if args.reuse_raw:
        signature_result = read_json(OUTPUT_DIR / "weighted_signature.raw.json")
        combined_result = read_json(OUTPUT_DIR / "two_signature.raw.json")
        pancancer_result = read_json(OUTPUT_DIR / "pancancer.raw.json")
        diagnostic_signature_result = read_json(
            OUTPUT_DIR / "diagnostic_hypoxia.raw.json"
        )
        diagnostic_combined_result = read_json(
            OUTPUT_DIR / "diagnostic_two_signature.raw.json"
        )
        diagnostic_pancancer_result = read_json(
            OUTPUT_DIR / "diagnostic_pancancer.raw.json"
        )
    else:
        client = ApiClient(args.api_base_url)
        signature_result = client.post("/api/analyses", signature_payload())
        combined_result = client.post("/api/analyses/combined", combined_payload())
        pancancer_result = client.post("/api/pancancer/survival", pancancer_payload())
        diagnostic_signature_result = client.post(
            "/api/analyses",
            diagnostic_signature_payload(),
        )
        diagnostic_combined_result = client.post(
            "/api/analyses/combined",
            diagnostic_combined_payload(),
        )
        diagnostic_pancancer_result = client.post(
            "/api/pancancer/survival",
            diagnostic_pancancer_payload(),
        )
    finished_at = utc_now()

    signature_rows = feature_signature_definitions()
    feature_rows = [
        summarize_analysis(
            "weighted_signature",
            "ACC BUB1B-PINK1 expression contrast",
            signature_result,
            signature_inputs=format_signature_entries(ACC_BUB1B_PINK1_SIGNATURE),
            interpretation=(
                "RNA-seq analogue of a published expression contrast; the original "
                "qRT-PCR threshold is not replicated."
            ),
        ),
        summarize_combined(
            "two_marker",
            "UVM BAP1 x PRAME grouping",
            combined_result,
            signature_inputs="BAP1 x PRAME; independent median splits",
            interpretation=(
                "Four-group stratification is supported; the continuous interaction "
                "term is not significant."
            ),
        ),
        summarize_pancancer(
            "pancancer",
            "BIRC5 pan-cancer primary + ordinal sensitivity",
            pancancer_result,
            marker="BIRC5",
            interpretation=(
                "The broad primary association is attenuated but directionally "
                "consistent in the stage-adjusted family."
            ),
        ),
    ]
    diagnostic_rows = [
        summarize_analysis(
            "diagnostic_hypoxia",
            "KIRC compact hypoxia z-score signature",
            diagnostic_signature_result,
            signature_inputs=format_signature_entries(HYPOXIA_SIGNATURE),
            interpretation=(
                "Continuous and grouped summaries are shown together; clinical "
                "adjustment, PH and nonlinearity remain separate diagnostics."
            ),
        ),
        summarize_combined(
            "diagnostic_two_signature",
            "SKCM effector x exhaustion signatures",
            diagnostic_combined_result,
            signature_inputs=(
                f"Effector: {format_signature_entries(EFFECTOR_SIGNATURE)}; "
                f"Exhaustion: {format_signature_entries(EXHAUSTION_SIGNATURE)}"
            ),
            interpretation=(
                "Four-group separation is significant, but the continuous interaction "
                "term is not."
            ),
        ),
        summarize_pancancer(
            "diagnostic_pancancer",
            "CA9 pan-cancer primary + ordinal sensitivity",
            diagnostic_pancancer_result,
            marker="CA9",
            interpretation=(
                "The modest primary estimate attenuates under ordinal clinical "
                "sensitivity."
            ),
        ),
    ]
    metadata = {
        "started_at": started_at,
        "finished_at": finished_at,
        "api_base_url": args.api_base_url,
        "reused_frozen_raw_results": bool(args.reuse_raw),
        "prespecified_adjustment_covariates": PRESPECIFIED_ADJUSTMENT,
        "feature_rows": feature_rows,
        "diagnostic_rows": diagnostic_rows,
        "signature_definitions": signature_rows,
    }
    write_json(OUTPUT_DIR / "feature_benchmark_metadata.json", metadata)
    write_json(OUTPUT_DIR / "weighted_signature.raw.json", signature_result)
    write_json(OUTPUT_DIR / "two_signature.raw.json", combined_result)
    write_json(OUTPUT_DIR / "pancancer.raw.json", pancancer_result)
    write_json(OUTPUT_DIR / "diagnostic_hypoxia.raw.json", diagnostic_signature_result)
    write_json(OUTPUT_DIR / "diagnostic_two_signature.raw.json", diagnostic_combined_result)
    write_json(OUTPUT_DIR / "diagnostic_pancancer.raw.json", diagnostic_pancancer_result)
    write_csv(OUTPUT_DIR / "feature_benchmark_summary.csv", feature_rows)
    write_markdown(OUTPUT_DIR / "feature_benchmark_summary.md", metadata, feature_rows)
    write_csv(OUTPUT_DIR / "feature_diagnostic_summary.csv", diagnostic_rows)
    write_markdown(OUTPUT_DIR / "feature_diagnostic_summary.md", metadata, diagnostic_rows)
    write_signature_markdown(OUTPUT_DIR / "signature_definitions.md", signature_rows)
    write_latex(TABLE_PATH, feature_rows)
    write_diagnostic_latex(DIAGNOSTIC_TABLE_PATH, diagnostic_rows)
    write_signature_latex(SIGNATURE_TABLE_PATH, signature_rows)
    print(f"Wrote {OUTPUT_DIR / 'feature_benchmark_summary.md'}")
    print(f"Wrote {OUTPUT_DIR / 'signature_definitions.md'}")
    print(f"Wrote {TABLE_PATH}")
    print(f"Wrote {DIAGNOSTIC_TABLE_PATH}")
    print(f"Wrote {SIGNATURE_TABLE_PATH}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run feature benchmarks for the TCGA-TRACE Application Note.")
    parser.add_argument("--api-base-url", default="http://localhost:3000/tcga_explorer")
    parser.add_argument(
        "--reuse-raw",
        action="store_true",
        help="Regenerate summaries and tables from the six frozen raw JSON files.",
    )
    return parser.parse_args()


class ApiClient:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    def post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=1200) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"HTTP {exc.code} for {path}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Could not reach {self.base_url}: {exc}") from exc


def signature_payload() -> dict[str, Any]:
    return {
        "cohort": "TCGA-ACC",
        "gene_symbol": "BUB1B_PINK1",
        "signature_method": "weighted",
        "signature_genes": ACC_BUB1B_PINK1_SIGNATURE,
        "endpoint": "OS",
        "expression_scale": "log2_tpm",
        "cutpoint_method": "median",
        "custom_percentile": None,
        "adjustment_covariates": PRESPECIFIED_ADJUSTMENT,
        "filters": empty_filters(),
        "time_unit": "months",
        "show_confidence_interval": True,
        "show_risk_table": False,
        "plot_style": plot_style(),
    }


def combined_payload() -> dict[str, Any]:
    return {
        "cohort": "TCGA-UVM",
        "signature_a": {
            "name": "BAP1",
            "gene_symbol": "BAP1",
            "signature_method": "single",
            "signature_genes": [],
        },
        "signature_b": {
            "name": "PRAME",
            "gene_symbol": "PRAME",
            "signature_method": "single",
            "signature_genes": [],
        },
        "endpoint": "DSS",
        "expression_scale": "log2_tpm",
        "combination_method": "median",
        "adjustment_covariates": PRESPECIFIED_ADJUSTMENT,
        "filters": empty_filters(),
        "time_unit": "months",
        "show_confidence_interval": True,
        "show_risk_table": False,
        "plot_style": {
            **plot_style(),
            "palette": ["#1f6f8b", "#c8842d", "#5a6f9f", "#b94d48"],
        },
    }


def pancancer_payload() -> dict[str, Any]:
    return {
        "gene_symbol": "BIRC5",
        "signature_method": "single",
        "signature_genes": [],
        "index_cohort": "TCGA-LUAD",
        "cohorts": [],
        "endpoint": "OS",
        "endpoint_mode": "same_endpoint",
        "expression_scale": "log2_tpm",
        "filters": empty_filters(),
        "min_patients": 10,
        "min_events": 5,
        "fdr_threshold": 0.10,
    }


def diagnostic_signature_payload() -> dict[str, Any]:
    payload = signature_payload()
    payload.update(
        {
            "cohort": "TCGA-KIRC",
            "gene_symbol": "HYPOXIA_SIGNATURE",
            "signature_method": "zscore",
            "signature_genes": HYPOXIA_SIGNATURE,
        }
    )
    return payload


def diagnostic_combined_payload() -> dict[str, Any]:
    payload = combined_payload()
    payload.update(
        {
            "cohort": "TCGA-SKCM",
            "signature_a": {
                "name": "Effector",
                "gene_symbol": "EFFECTOR_SIGNATURE",
                "signature_method": "zscore",
                "signature_genes": EFFECTOR_SIGNATURE,
            },
            "signature_b": {
                "name": "Exhaustion",
                "gene_symbol": "EXHAUSTION_SIGNATURE",
                "signature_method": "zscore",
                "signature_genes": EXHAUSTION_SIGNATURE,
            },
            "endpoint": "OS",
        }
    )
    return payload


def diagnostic_pancancer_payload() -> dict[str, Any]:
    payload = pancancer_payload()
    payload.update({"gene_symbol": "CA9", "index_cohort": "TCGA-KIRC"})
    return payload


def feature_signature_definitions() -> list[dict[str, Any]]:
    return [
        {
            "role": "Main",
            "workflow": "ACC BUB1B-PINK1 contrast",
            "cohort": "TCGA-ACC",
            "endpoint": "OS",
            "score_method": "weighted",
            "construction": (
                "(BUB1B - PINK1)/2 on log2(TPM + 1) expression; continuous Cox "
                "primary and median split sensitivity."
            ),
            "rationale": (
                "RNA-seq analogue of the published two-gene differential-expression "
                "predictor; not a replication of its qRT-PCR threshold."
            ),
            "genes": ACC_BUB1B_PINK1_SIGNATURE,
        },
        {
            "role": "Main",
            "workflow": "UVM BAP1 marker",
            "cohort": "TCGA-UVM",
            "endpoint": "DSS",
            "score_method": "single",
            "construction": "Gene-level BAP1 expression; median split for crossed grouping.",
            "rationale": (
                "Gene-expression workflow analogue of established BAP1 prognostic "
                "biology; not a mutation or immunohistochemistry classifier."
            ),
            "genes": UVM_BAP1_MARKER,
        },
        {
            "role": "Main",
            "workflow": "UVM PRAME marker",
            "cohort": "TCGA-UVM",
            "endpoint": "DSS",
            "score_method": "single",
            "construction": "Gene-level PRAME expression; median split for crossed grouping.",
            "rationale": (
                "Paired with BAP1 to exercise literature-anchored four-group "
                "stratification; not a clinical PRAME assay."
            ),
            "genes": UVM_PRAME_MARKER,
        },
        {
            "role": "Main",
            "workflow": "BIRC5 pan-cancer primary + ordinal sensitivity",
            "cohort": "pan-cancer",
            "endpoint": "OS",
            "score_method": "single",
            "construction": (
                "Primary continuous Cox with expression z-scored within each cohort; "
                "parallel ordinal stage, grade and stage+grade sensitivity models."
            ),
            "rationale": (
                "Published pan-cancer prognostic marker used to exercise FDR, "
                "family-specific adjustment and meta-analysis."
            ),
            "genes": BIRC5_MARKER,
        },
        {
            "role": "Diagnostic",
            "workflow": "KIRC compact hypoxia signature",
            "cohort": "TCGA-KIRC",
            "endpoint": "OS",
            "score_method": "zscore",
            "construction": "Equal-weight mean of per-gene z-scores.",
            "rationale": (
                "Compact Hallmark-aligned hypoxia example selected to exercise "
                "transparent multi-gene scoring without presenting a pathway model."
            ),
            "genes": HYPOXIA_SIGNATURE,
        },
        {
            "role": "Diagnostic",
            "workflow": "SKCM effector signature",
            "cohort": "TCGA-SKCM",
            "endpoint": "OS",
            "score_method": "zscore",
            "construction": "Equal-weight mean of per-gene z-scores; crossed with the exhaustion signature after median splits.",
            "rationale": (
                "Cytotoxic T-cell and interferon-chemokine example selected for "
                "an immune-active TCGA-SKCM workflow benchmark."
            ),
            "genes": EFFECTOR_SIGNATURE,
        },
        {
            "role": "Diagnostic",
            "workflow": "SKCM exhaustion signature",
            "cohort": "TCGA-SKCM",
            "endpoint": "OS",
            "score_method": "zscore",
            "construction": "Equal-weight mean of per-gene z-scores; crossed with the effector signature after median splits.",
            "rationale": (
                "Checkpoint/exhaustion marker example paired with the effector "
                "score to exercise two-signature grouping and interaction Cox."
            ),
            "genes": EXHAUSTION_SIGNATURE,
        },
        {
            "role": "Diagnostic",
            "workflow": "CA9 pan-cancer primary + ordinal sensitivity",
            "cohort": "pan-cancer",
            "endpoint": "OS",
            "score_method": "single",
            "construction": (
                "Primary single-gene continuous Cox with expression z-scored within "
                "each cohort; parallel ordinal stage, grade and stage+grade sensitivity models."
            ),
            "rationale": (
                "Single-gene hypoxia and kidney-cancer marker canary selected "
                "to expose attenuation and cross-cancer heterogeneity."
            ),
            "genes": [{"gene_symbol": "CA9", "weight": 1.0}],
        },
    ]


def empty_filters() -> dict[str, Any]:
    return {
        "sample_types": [],
        "stages": [],
        "grades": [],
        "genders": [],
        "races": [],
        "age_min": None,
        "age_max": None,
        "max_time_days": None,
    }


def plot_style() -> dict[str, Any]:
    return {
        "palette": ["#1f6f8b", "#c8842d", "#b94d48"],
        "font_family": "sans",
        "plot_aspect": "rectangular",
        "base_font_size": 12,
        "axis_text_size": 11,
        "axis_title_size": 12,
        "show_grid": False,
        "show_title": False,
        "plot_title": "",
    }


def summarize_analysis(
    kind: str,
    label: str,
    result: dict[str, Any],
    *,
    signature_inputs: str,
    interpretation: str,
) -> dict[str, Any]:
    metrics = result.get("metrics") or {}
    continuous = metrics.get("continuous_analysis") or {}
    univariable = find_model(
        continuous.get("linear_models"),
        "continuous_univariable",
    )
    adjusted = downstream_continuous_adjusted_model(
        continuous.get("linear_models")
    )
    adjusted_reporting = (
        adjusted
        or downstream_continuous_adjusted_reporting_model(
            continuous.get("linear_models")
        )
    )
    diagnostic_model = adjusted_reporting or univariable
    spline = continuous.get("spline") or {}
    rmst = metrics.get("rmst") or {}
    rmst_delta = (rmst.get("difference") or {}).get("estimate_days")
    audit = metrics.get("audit_report") or {}
    adjustment_status = continuous_adjustment_status(
        continuous.get("linear_models")
    )
    return {
        "kind": kind,
        "label": label,
        "status": result.get("status"),
        "id": result.get("id"),
        "cohort": result.get("cohort"),
        "marker": result.get("gene_symbol"),
        "endpoint": metrics.get("endpoint"),
        "n_patients": continuous.get("n_patients"),
        "n_events": continuous.get("n_events"),
        "primary_statistic": "continuous Cox per +1 SD",
        "primary_p_value": univariable.get("p_value"),
        "cox_p_value": None,
        "adjusted_p_value": adjusted.get("p_value"),
        "ph_marker_p_value": diagnostic_model.get("ph_p_value"),
        "ph_global_p_value": diagnostic_model.get("ph_global_p_value"),
        "nonlinearity_p_value": spline.get("nonlinearity_p_value"),
        "grouped_logrank_p_value": metrics.get("logrank_p_value"),
        "rmst_p_value": (rmst.get("difference") or {}).get("p_value"),
        "interaction_p_value": None,
        "meta_p_value": None,
        "heterogeneity_i2": None,
        "opposite_significant": None,
        "adjustment_status": adjustment_status,
        **model_diagnostic_fields(diagnostic_model),
        "signature_inputs": signature_inputs,
        "effect_summary": (
            f"HR per SD {format_hr(univariable)}; "
            f"nonlinearity p={format_p(spline.get('nonlinearity_p_value'))}"
        ),
        "interpretation": interpretation,
        "limitation": interpretation,
        "summary": (
            f"HR per SD {format_hr(univariable)}; grouped log-rank "
            f"p={format_p(metrics.get('logrank_p_value'))}; RMST delta "
            f"{format_number(rmst_delta, 0)} days"
        ),
        "audit_hash": audit.get("reproducibility_hash"),
    }


def summarize_combined(
    kind: str,
    label: str,
    result: dict[str, Any],
    *,
    signature_inputs: str,
    interpretation: str,
) -> dict[str, Any]:
    metrics = result.get("metrics") or {}
    interaction = first_reporting(metrics.get("signature_interaction_cox_models"))
    adjusted_interaction = downstream_adjusted_interaction_model(
        metrics.get("signature_interaction_cox_models")
    )
    adjusted_interaction_reporting = (
        adjusted_interaction
        or downstream_adjusted_interaction_reporting_model(
            metrics.get("signature_interaction_cox_models")
        )
    )
    diagnostic_model = adjusted_interaction_reporting or interaction
    interaction_term = interaction.get("interaction_term") or {}
    audit = metrics.get("audit_report") or {}
    event_counts = metrics.get("event_counts") or {}
    group_counts = metrics.get("group_counts") or {}
    if kind == "two_marker":
        event_summary = (
            f"BAP1-low/PRAME-high {event_counts.get('Low_High')}/{group_counts.get('Low_High')} events; "
            f"BAP1-high/PRAME-low {event_counts.get('High_Low')}/{group_counts.get('High_Low')}"
        )
    else:
        event_summary = f"{len(group_counts)} KM groups"
    return {
        "kind": kind,
        "label": label,
        "status": result.get("status"),
        "id": result.get("id"),
        "cohort": result.get("cohort"),
        "marker": result.get("gene_symbol"),
        "endpoint": metrics.get("endpoint"),
        "n_patients": metrics.get("n_patients"),
        "n_events": metrics.get("n_events"),
        "primary_statistic": "four-group log-rank",
        "primary_p_value": metrics.get("logrank_p_value"),
        "cox_p_value": None,
        "adjusted_p_value": None,
        "ph_global_p_value": interaction.get("ph_global_p_value"),
        "rmst_p_value": None,
        "interaction_p_value": interaction_term.get("p_value"),
        "meta_p_value": None,
        "heterogeneity_i2": None,
        "opposite_significant": None,
        "adjustment_status": interaction_adjustment_status(
            metrics.get("signature_interaction_cox_models")
        ),
        **model_diagnostic_fields(diagnostic_model),
        "signature_inputs": signature_inputs,
        "effect_summary": f"Global separation; {event_summary}",
        "interpretation": interpretation,
        "limitation": (
            interaction_limitation(interaction_term, adjusted_interaction_reporting)
            if kind == "two_marker"
            else interpretation
        ),
        "summary": (
            f"Global log-rank p={format_p(metrics.get('logrank_p_value'))}; "
            f"interaction HR {format_number(interaction_term.get('hazard_ratio'), 2)}"
        ),
        "audit_hash": audit.get("reproducibility_hash"),
    }


def summarize_pancancer(
    kind: str,
    label: str,
    result: dict[str, Any],
    *,
    marker: str,
    interpretation: str,
) -> dict[str, Any]:
    completed = [row for row in result.get("results") or [] if row.get("status") == "completed"]
    significant = [row for row in completed if row.get("significant")]
    meta = result.get("meta_analysis") or {}
    random_effect = meta.get("random_effect") or {}
    prediction_interval = meta.get("prediction_interval") or {}
    heterogeneity = meta.get("heterogeneity") or {}
    concordance = (result.get("summary") or {}).get("concordance_counts") or {}
    opposite_significant = int(concordance.get("opposite_direction_significant") or 0)
    sensitivity = result.get("clinical_sensitivity") or {}
    sensitivity_summary = sensitivity.get("summary") or {}
    sensitivity_total = int(sensitivity_summary.get("total_cohorts") or 0)
    sensitivity_evaluable = int(sensitivity_summary.get("evaluable") or 0)
    sensitivity_hits = int(sensitivity_summary.get("fdr_significant") or 0)
    sensitivity_reversals = int(sensitivity_summary.get("direction_reversed") or 0)
    stage_family = (
        (sensitivity.get("meta_analysis_by_model") or {}).get("stage_adjusted") or {}
    )
    stage_random_effect = (
        (stage_family.get("meta_analysis") or {}).get("random_effect") or {}
    )
    stage_prediction_interval = (
        (stage_family.get("meta_analysis") or {}).get("prediction_interval")
        or {}
    )
    stage_summary = (
        "stage-adjusted common-scale REML HR "
        f"{format_number(stage_random_effect.get('hazard_ratio'), 2)} "
        f"(HKSJ p={format_p(stage_random_effect.get('p_value'))}; "
        f"95% PI {format_prediction_interval(stage_prediction_interval)})"
        if stage_random_effect
        else "stage-adjusted meta-analysis not evaluable"
    )
    hit_summary = (
        f"{sensitivity_hits} selected adjusted FDR hits"
        if sensitivity_hits
        else "no selected adjusted cohort survived FDR<0.10"
    )
    adjustment_status = (
        f"Ordinal sensitivity: {sensitivity_evaluable}/{sensitivity_total} cohorts "
        f"evaluable; {hit_summary}; {stage_summary}."
    )
    if kind == "pancancer":
        limitation = (
            f"Primary I2={format_number(heterogeneity.get('i_squared'), 1)}%; "
            f"95% prediction interval "
            f"{format_prediction_interval(prediction_interval)}; "
            f"selected ordinal sensitivity was evaluable in "
            f"{sensitivity_evaluable}/{sensitivity_total} cancers and mixed "
            "adjustment families were not pooled."
        )
    else:
        limitation = (
            f"Primary I2={format_number(heterogeneity.get('i_squared'), 1)}%; "
            f"95% prediction interval "
            f"{format_prediction_interval(prediction_interval)}; "
            f"ordinal sensitivity was evaluable in {sensitivity_evaluable}/"
            f"{sensitivity_total} cancers with {sensitivity_reversals} direction "
            f"reversals; {hit_summary}."
        )
    audit = result.get("audit") or {}
    return {
        "kind": kind,
        "label": label,
        "status": result.get("status"),
        "id": result.get("scan_id"),
        "cohort": "pan-cancer",
        "marker": marker,
        "endpoint": result.get("endpoint"),
        "n_patients": sum(int(row.get("n_patients") or 0) for row in completed),
        "n_events": sum(int(row.get("n_events") or 0) for row in completed),
        "primary_statistic": "common-scale REML/HKSJ meta-analysis",
        "primary_p_value": random_effect.get("p_value"),
        "cox_p_value": None,
        "adjusted_p_value": None,
        "ph_global_p_value": None,
        "rmst_p_value": None,
        "interaction_p_value": None,
        "meta_p_value": random_effect.get("p_value"),
        "heterogeneity_i2": heterogeneity.get("i_squared"),
        "opposite_significant": opposite_significant,
        "adjustment_status": adjustment_status,
        "signature_inputs": marker,
        "effect_summary": (
            f"{len(significant)}/{len(completed)} cohorts FDR<0.10; "
            f"common-scale REML HR {format_hr(random_effect)}; "
            f"95% PI {format_prediction_interval(prediction_interval)}"
        ),
        "interpretation": interpretation,
        "limitation": limitation,
        "summary": (
            f"Primary {len(significant)}/{len(completed)} FDR hits; {stage_summary}"
        ),
        "audit_hash": audit.get("reproducibility_hash"),
    }


def downstream_adjusted_model(models: list[dict[str, Any]] | None) -> dict[str, Any]:
    if model_present(models, "user_adjusted"):
        return find_model(models, "user_adjusted")
    return (
        find_model(models, "stage_grade_adjusted")
        or find_model(models, "stage_adjusted")
        or find_model(models, "grade_adjusted")
    )


def downstream_continuous_adjusted_model(
    models: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    if model_present(models, "continuous_user_adjusted"):
        return find_model(models, "continuous_user_adjusted")
    return (
        find_model(models, "continuous_stage_grade_adjusted")
        or find_model(models, "continuous_stage_adjusted")
        or find_model(models, "continuous_grade_adjusted")
    )


def downstream_continuous_adjusted_reporting_model(
    models: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    if model_present(models, "continuous_user_adjusted"):
        return find_reporting_model(models, "continuous_user_adjusted")
    completed = downstream_continuous_adjusted_model(models)
    if completed:
        return completed
    for model_id in (
        "continuous_stage_grade_adjusted",
        "continuous_stage_adjusted",
        "continuous_grade_adjusted",
    ):
        model = find_reporting_model(models, model_id)
        if model:
            return model
    return {}


def model_present(
    models: list[dict[str, Any]] | None,
    model_id: str,
) -> bool:
    return any(model.get("model") == model_id for model in models or [])


def find_model(models: list[dict[str, Any]] | None, model_id: str) -> dict[str, Any]:
    for model in models or []:
        if model.get("model") == model_id and model.get("status") == "completed":
            return model
    return {}


def find_reporting_model(
    models: list[dict[str, Any]] | None,
    model_id: str,
) -> dict[str, Any]:
    completed = find_model(models, model_id)
    if completed:
        return completed
    for model in models or []:
        if (
            model.get("model") == model_id
            and model.get("status") in {"failed", "skipped"}
        ):
            return model
    return {}


def first_completed(models: list[dict[str, Any]] | None) -> dict[str, Any]:
    for model in models or []:
        if model.get("status") == "completed":
            return model
    return {}


def first_reporting(models: list[dict[str, Any]] | None) -> dict[str, Any]:
    completed = first_completed(models)
    if completed:
        return completed
    for model in models or []:
        if model.get("status") == "failed":
            return model
    return {}


def downstream_adjusted_interaction_model(
    models: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    if model_present(models, "signature_interaction_user_adjusted"):
        return find_model(models, "signature_interaction_user_adjusted")
    for model_id in (
        "signature_interaction_stage_grade_adjusted",
        "signature_interaction_stage_adjusted",
        "signature_interaction_grade_adjusted",
    ):
        model = find_model(models, model_id)
        if model:
            return model
    return {}


def downstream_adjusted_interaction_reporting_model(
    models: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    if model_present(models, "signature_interaction_user_adjusted"):
        return find_reporting_model(
            models,
            "signature_interaction_user_adjusted",
        )
    completed = downstream_adjusted_interaction_model(models)
    if completed:
        return completed
    for model_id in (
        "signature_interaction_stage_grade_adjusted",
        "signature_interaction_stage_adjusted",
        "signature_interaction_grade_adjusted",
    ):
        model = find_reporting_model(models, model_id)
        if model:
            return model
    return {}


def model_diagnostic_fields(model: dict[str, Any]) -> dict[str, Any]:
    information = model.get("information_diagnostics") or {}
    firth = model.get("penalized_sensitivity") or {}
    return {
        "diagnostic_model": model.get("model"),
        "standard_cox_status": model.get("status"),
        "parameter_count": information.get("parameter_count"),
        "events_per_parameter": information.get("events_per_parameter"),
        "information_status": information.get("status"),
        "firth_status": firth.get("status"),
        "firth_hr": firth.get("hazard_ratio"),
        "firth_hr_conf_low": firth.get("hr_conf_low"),
        "firth_hr_conf_high": firth.get("hr_conf_high"),
        "firth_p_value": firth.get("p_value"),
        "firth_ties": firth.get("ties"),
        "firth_trigger_reasons": json.dumps(
            firth.get("trigger_reasons") or [],
            sort_keys=True,
        ),
    }


def interaction_limitation(
    interaction_term: dict[str, Any],
    adjusted: dict[str, Any],
) -> str:
    prefix = f"Continuous interaction p={format_p(interaction_term.get('p_value'))}; "
    if not adjusted:
        return prefix + "no clinically adjusted ordinal interaction model was evaluable."
    if adjusted.get("status") == "failed":
        firth = adjusted.get("penalized_sensitivity") or {}
        if firth.get("status") == "completed":
            return (
                prefix
                + "the standard adjusted interaction failed, while Firth sensitivity "
                + f"gave HR={format_hr(firth)}, p={format_p(firth.get('p_value'))}."
            )
        return prefix + "the standard adjusted interaction failed without a completed Firth sensitivity."
    label = str(adjusted.get("label") or "Clinically adjusted ordinal interaction")
    ph_p = adjusted.get("ph_global_p_value")
    if is_number(ph_p) and float(ph_p) < 0.05:
        return prefix + f"{label.lower()} completed with a PH caution (global p={format_p(ph_p)})."
    return prefix + f"{label.lower()} completed without a model warning."


def clinical_adjustment_status(models: list[dict[str, Any]] | None) -> str:
    adjusted = downstream_adjusted_model(models)
    if adjusted:
        return f"Completed: {adjusted.get('label') or adjusted.get('model')}."
    if model_present(models, "user_adjusted"):
        requested = find_reporting_model(models, "user_adjusted")
        return str(
            requested.get("reason")
            or "The requested clinical adjustment was not evaluable."
        )
    skipped = [
        model
        for model in models or []
        if model.get("model") != "univariable" and model.get("status") == "skipped"
    ]
    return str(skipped[0].get("reason") or "Clinical adjustment unavailable.") if skipped else ""


def continuous_adjustment_status(
    models: list[dict[str, Any]] | None,
) -> str:
    adjusted = downstream_continuous_adjusted_model(models)
    if adjusted:
        return f"Completed: {adjusted.get('label') or adjusted.get('model')}."
    if model_present(models, "continuous_user_adjusted"):
        requested = find_reporting_model(models, "continuous_user_adjusted")
        return str(
            requested.get("reason")
            or "The requested clinical adjustment was not evaluable."
        )
    skipped = [
        model
        for model in models or []
        if model.get("model") != "continuous_univariable"
        and model.get("status") == "skipped"
    ]
    return (
        str(skipped[0].get("reason") or "Clinical adjustment unavailable.")
        if skipped
        else ""
    )


def interaction_adjustment_status(models: list[dict[str, Any]] | None) -> str:
    if model_present(models, "signature_interaction_user_adjusted"):
        requested = find_reporting_model(
            models,
            "signature_interaction_user_adjusted",
        )
        if requested.get("status") == "completed":
            warnings = requested.get("warnings") or []
            return (
                "; ".join(warnings)
                if warnings
                else "User-selected interaction adjustment completed."
            )
        firth = requested.get("penalized_sensitivity") or {}
        if firth.get("status") == "completed":
            return (
                "Standard user-selected interaction failed; Firth sensitivity "
                f"completed at {format_number((requested.get('information_diagnostics') or {}).get('events_per_parameter'), 1)} "
                "events per parameter."
            )
        return str(
            requested.get("reason")
            or "The user-selected interaction adjustment was not evaluable."
        )
    adjusted = [
        model
        for model in models or []
        if model.get("model") != "signature_interaction" and model.get("status") == "completed"
    ]
    if not adjusted:
        failed = downstream_adjusted_interaction_reporting_model(models)
        if failed:
            firth = failed.get("penalized_sensitivity") or {}
            if firth.get("status") == "completed":
                return (
                    "Standard adjusted interaction failed; Firth sensitivity completed "
                    f"at {format_number((failed.get('information_diagnostics') or {}).get('events_per_parameter'), 1)} "
                    "events per parameter."
                )
            return "The clinically adjusted interaction failed and Firth sensitivity did not complete."
        return "No completed clinically adjusted interaction model."
    warnings = [warning for model in adjusted for warning in model.get("warnings") or []]
    return "; ".join(warnings) if warnings else "Clinically adjusted interaction model completed."


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = [
        "kind",
        "label",
        "status",
        "id",
        "cohort",
        "marker",
        "endpoint",
        "n_patients",
        "n_events",
        "primary_statistic",
        "primary_p_value",
        "cox_p_value",
        "adjusted_p_value",
        "ph_marker_p_value",
        "ph_global_p_value",
        "nonlinearity_p_value",
        "grouped_logrank_p_value",
        "rmst_p_value",
        "interaction_p_value",
        "meta_p_value",
        "heterogeneity_i2",
        "opposite_significant",
        "adjustment_status",
        "diagnostic_model",
        "standard_cox_status",
        "parameter_count",
        "events_per_parameter",
        "information_status",
        "firth_status",
        "firth_hr",
        "firth_hr_conf_low",
        "firth_hr_conf_high",
        "firth_p_value",
        "firth_ties",
        "firth_trigger_reasons",
        "signature_inputs",
        "effect_summary",
        "interpretation",
        "limitation",
        "summary",
        "audit_hash",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def write_markdown(path: Path, metadata: dict[str, Any], rows: list[dict[str, Any]]) -> None:
    title = (
        "Feature Benchmark Diagnostic Summary"
        if any(str(row.get("kind", "")).startswith("diagnostic_") for row in rows)
        else "Feature Benchmark Summary"
    )
    lines = [
        f"# {title}",
        "",
        f"- Started: {metadata['started_at']}",
        f"- Finished: {metadata['finished_at']}",
        f"- API base URL: `{metadata['api_base_url']}`",
        "",
        "| Mode | Inputs and construction | Cohort/n | Primary result | Diagnostics | Limitation |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        lines.append(
            "| {label} | {inputs} | {cohort_n} | {effect} | {checks} | {interpretation} |".format(
                label=display_mode(row),
                inputs=row["signature_inputs"],
                cohort_n=format_cohort_n(row),
                effect=row["effect_summary"],
                checks=markdown_statistical_checks(row),
                interpretation=row["limitation"],
            )
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_signature_markdown(path: Path, rows: list[dict[str, Any]]) -> None:
    lines = [
        "# Feature Signature Definitions",
        "",
        "All feature benchmark signatures use log2(TPM + 1) expression.",
        "Weighted signatures use `sum(weight * expression_gene) / sum(abs(weight))`; z-score signatures standardize each gene among eligible patients before the same weighted combination.",
        "",
        "| Role | Workflow | Cohort | Endpoint | Score method | Construction | Rationale | Genes |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        lines.append(
            "| {role} | {workflow} | {cohort} | {endpoint} | {method} | {construction} | {rationale} | {genes} |".format(
                role=row["role"],
                workflow=row["workflow"],
                cohort=row["cohort"],
                endpoint=row["endpoint"],
                method=row["score_method"],
                construction=row["construction"],
                rationale=row["rationale"],
                genes=format_signature_entries(row["genes"]),
            )
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_latex(path: Path, rows: list[dict[str, Any]]) -> None:
    lines = [
        "\\begin{table}[H]",
        "\\centering",
        "\\begingroup",
        "\\scriptsize",
        "\\setlength{\\tabcolsep}{3pt}",
        "\\renewcommand{\\arraystretch}{1.05}",
        "\\newcolumntype{Y}{>{\\raggedright\\arraybackslash}X}",
        "\\newcolumntype{P}[1]{>{\\raggedright\\arraybackslash}p{#1}}",
        "\\caption{Literature-anchored demonstrations of weighted-signature, two-marker and pan-cancer workflows. These are workflow examples rather than biomarker validation claims.}",
        "\\label{tab:feature-benchmark-summary}",
        "\\begin{tabularx}{\\linewidth}{P{1.45cm}YP{1.55cm}YY}",
        "\\toprule",
        "Mode & Inputs and construction & Cohort, n/events & Primary result & Limitation \\\\",
        "\\midrule",
    ]
    for row in rows:
        lines.append(
            " & ".join(
                [
                    latex_escape(display_mode(row)),
                    latex_escape(latex_feature_inputs(row)),
                    latex_escape(latex_cohort_n(row)),
                    latex_escape(
                        f"{latex_effect_summary(row)}; {latex_statistical_checks(row)}"
                    ),
                    latex_escape(str(row.get("limitation") or "")),
                ]
            )
            + " \\\\"
        )
    lines.extend(["\\bottomrule", "\\end{tabularx}", "\\endgroup", "\\end{table}", ""])
    path.write_text("\n".join(lines), encoding="utf-8")


def write_diagnostic_latex(path: Path, rows: list[dict[str, Any]]) -> None:
    lines = [
        "\\begin{table}[H]",
        "\\centering",
        "\\begingroup",
        "\\scriptsize",
        "\\setlength{\\tabcolsep}{3pt}",
        "\\renewcommand{\\arraystretch}{1.05}",
        "\\newcolumntype{Y}{>{\\raggedright\\arraybackslash}X}",
        "\\newcolumntype{P}[1]{>{\\raggedright\\arraybackslash}p{#1}}",
        "\\caption{Diagnostic feature-workflow cases carried forward from the original benchmark panel. They show adjusted-model, interaction and pan-cancer meta-analysis discordance rather than selected positive results.}",
        "\\label{tab:feature-benchmark-diagnostic-summary}",
        "\\begin{tabularx}{\\linewidth}{P{1.55cm}YP{1.55cm}YY}",
        "\\toprule",
        "Workflow & Inputs & Cohort, n/events & Readout & Diagnostic interpretation \\\\",
        "\\midrule",
    ]
    for row in rows:
        lines.append(
            " & ".join(
                [
                    latex_escape(display_mode(row)),
                    latex_escape(latex_feature_inputs(row)),
                    latex_escape(latex_cohort_n(row)),
                    latex_escape(
                        f"{latex_effect_summary(row)}; {latex_statistical_checks(row)}"
                    ),
                    latex_escape(str(row.get("interpretation") or "")),
                ]
            )
            + " \\\\"
        )
    lines.extend(
        ["\\bottomrule", "\\end{tabularx}", "\\endgroup", "\\end{table}", ""]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def write_signature_latex(path: Path, rows: list[dict[str, Any]]) -> None:
    lines = [
        "\\begin{table}[H]",
        "\\centering",
        "\\begingroup",
        "\\footnotesize",
        "\\setlength{\\tabcolsep}{4pt}",
        "\\renewcommand{\\arraystretch}{1.08}",
        "\\newcolumntype{Y}{>{\\raggedright\\arraybackslash}X}",
        "\\newcolumntype{P}[1]{>{\\raggedright\\arraybackslash}p{#1}}",
        "\\caption{Exact feature definitions used in the main and diagnostic workflow benchmarks.}",
        "\\label{tab:feature-signature-definitions}",
        "\\begin{tabularx}{\\linewidth}{P{1.1cm}P{2.65cm}P{1.45cm}YY}",
        "\\toprule",
        "Role & Workflow & Score & Construction & Genes \\\\",
        "\\midrule",
    ]
    for row in rows:
        lines.append(
            " & ".join(
                [
                    "Diag." if row["role"] == "Diagnostic" else latex_escape(row["role"]),
                    latex_escape(row["workflow"]),
                    latex_escape(row["score_method"]),
                    latex_escape(latex_signature_construction(row)),
                    latex_escape(format_signature_entries(row["genes"])),
                ]
            )
            + " \\\\"
        )
    lines.extend(
        ["\\bottomrule", "\\end{tabularx}", "\\endgroup", "\\end{table}", ""]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def latex_signature_construction(row: dict[str, Any]) -> str:
    workflow = row.get("workflow")
    if workflow in {"SKCM effector signature", "SKCM exhaustion signature"}:
        return "Mean z-score; crossed after median splits."
    if workflow in {
        "CA9 pan-cancer primary + ordinal sensitivity",
        "BIRC5 pan-cancer primary + ordinal sensitivity",
    }:
        return "Primary continuous Cox; parallel ordinal stage/grade sensitivity."
    return str(row.get("construction") or "")


def latex_signature_rationale(row: dict[str, Any]) -> str:
    labels = {
        "KIRC compact hypoxia signature": "Compact Hallmark-aligned hypoxia example.",
        "SKCM effector signature": "Cytotoxic and interferon-chemokine immune example.",
        "SKCM exhaustion signature": "Checkpoint marker example paired with effector score.",
        "CA9 pan-cancer primary + ordinal sensitivity": "Hypoxia/kidney marker pan-cancer canary.",
        "ACC BUB1B-PINK1 contrast": "Published ACC two-gene contrast, adapted to RNA-seq.",
        "UVM BAP1 marker": "Transcript-level BAP1 prognostic example.",
        "UVM PRAME marker": "Transcript-level PRAME prognostic example.",
        "BIRC5 pan-cancer primary + ordinal sensitivity": "Published pan-cancer prognostic example.",
    }
    return labels.get(str(row.get("workflow")), str(row.get("rationale") or ""))


def display_mode(row: dict[str, Any]) -> str:
    labels = {
        "weighted_signature": "Weighted signature",
        "two_marker": "Two-marker grouping",
        "pancancer": "Pan-cancer primary + sensitivity",
        "diagnostic_hypoxia": "KIRC hypoxia signature",
        "diagnostic_two_signature": "SKCM effector x exhaustion",
        "diagnostic_pancancer": "CA9 pan-cancer primary + sensitivity",
    }
    return labels.get(str(row.get("kind")), str(row.get("label") or ""))


def latex_summary(row: dict[str, Any]) -> str:
    primary = format_p(row["primary_p_value"])
    adjusted = format_p(row["adjusted_p_value"])
    ph = format_p(row["ph_global_p_value"])
    summary = str(row.get("summary") or "")
    summary = summary.replace("RMST delta ", "RMST ")
    summary = summary.replace(" days", " d")
    summary = summary.replace("Interaction HR", "HRint")
    summary = summary.replace("random-effects", "RE")
    summary = summary.replace("FDR<0.10", "q below 0.10")
    if row.get("kind") == "hypoxia_signature":
        return f"log-rank p={primary}; adj={adjusted}; PH={ph}; {summary}"
    if row.get("kind") == "two_signature":
        return f"interaction p={primary}; adj={adjusted}; PH={ph}; {summary}"
    if row.get("kind") == "pancancer":
        return f"Cox p={primary}; FDR={adjusted}; {summary}"
    return f"{row['primary_statistic']} p={primary}; {summary}"


def latex_feature_inputs(row: dict[str, Any]) -> str:
    if row.get("kind") == "weighted_signature":
        return (
            "(BUB1B - PINK1)/2 on log2(TPM + 1); continuous Cox primary "
            "plus median sensitivity"
        )
    if row.get("kind") == "two_marker":
        return "BAP1 x PRAME; independent median splits"
    if row.get("kind") == "pancancer":
        return "BIRC5; primary continuous within-cohort z-score plus ordinal sensitivity"
    if row.get("kind") == "diagnostic_pancancer":
        return "CA9; primary continuous within-cohort z-score plus ordinal sensitivity"
    if row.get("kind") == "diagnostic_two_signature":
        return (
            "Effector: CD8A, GZMB, PRF1, IFNG, CXCL9, CXCL10; "
            "Exhaustion: PDCD1, CTLA4, LAG3, HAVCR2, TIGIT"
        )
    return str(row.get("signature_inputs") or "")


def markdown_statistical_checks(row: dict[str, Any]) -> str:
    return statistical_checks(row, latex=False)


def latex_statistical_checks(row: dict[str, Any]) -> str:
    return statistical_checks(row, latex=True)


def statistical_checks(row: dict[str, Any], latex: bool = False) -> str:
    kind = str(row.get("kind"))
    primary_labels = {
        "weighted_signature": "continuous Cox",
        "two_marker": "four-group log-rank",
        "pancancer": "REML/HKSJ meta-analysis",
        "diagnostic_hypoxia": "continuous Cox",
        "diagnostic_two_signature": "four-group log-rank",
        "diagnostic_pancancer": "REML/HKSJ meta-analysis",
    }
    parts = []
    primary = format_p(row["primary_p_value"])
    if primary:
        parts.append(f"{primary_labels.get(kind, row['primary_statistic'])} p={primary}")
    cox = format_p(row.get("cox_p_value"))
    if cox:
        parts.append(f"{'adjusted Cox' if kind == 'diagnostic_hypoxia' else 'Cox'} p={cox}")
    adjusted = format_p(row["adjusted_p_value"])
    if adjusted:
        parts.append(f"adjusted p={adjusted}")
    interaction = format_p(row.get("interaction_p_value"))
    if interaction:
        parts.append(f"interaction p={interaction}")
    nonlinearity = format_p(row.get("nonlinearity_p_value"))
    if nonlinearity:
        parts.append(f"nonlinearity p={nonlinearity}")
    ph_marker = format_p(row.get("ph_marker_p_value"))
    if ph_marker:
        parts.append(f"marker PH p={ph_marker}")
    ph = format_p(row["ph_global_p_value"])
    if ph:
        parts.append(f"global PH p={ph}")
    grouped_logrank = format_p(row.get("grouped_logrank_p_value"))
    if grouped_logrank:
        parts.append(f"grouped log-rank p={grouped_logrank}")
    rmst = format_p(row["rmst_p_value"])
    if rmst:
        parts.append(f"RMST p={rmst}")
    i_squared = format_number(row.get("heterogeneity_i2"), 1)
    if i_squared:
        parts.append(f"I2={i_squared}%")
    if kind in {"pancancer", "diagnostic_pancancer"} and row.get("adjustment_status"):
        parts.append(str(row["adjustment_status"]))
    if kind not in {"pancancer", "diagnostic_pancancer"}:
        events_per_parameter = format_number(row.get("events_per_parameter"), 1)
        if events_per_parameter:
            parts.append(f"{events_per_parameter} events/parameter")
        if row.get("firth_status") == "completed":
            parts.append(
                "Firth "
                f"HR={format_number(row.get('firth_hr'), 2)}, "
                f"p={format_p(row.get('firth_p_value'))}"
            )
    return "; ".join(parts)


def format_cohort_endpoint(row: dict[str, Any]) -> str:
    return f"{row['cohort']} {row['endpoint']}"


def latex_cohort_endpoint(row: dict[str, Any]) -> str:
    return format_cohort_endpoint(row).replace("TCGA-", "")


def format_cohort_n(row: dict[str, Any]) -> str:
    return f"{format_cohort_endpoint(row)}; {format_n_events(row)}"


def latex_cohort_n(row: dict[str, Any]) -> str:
    return f"{latex_cohort_endpoint(row)}; {format_n_events(row)}"


def format_n_events(row: dict[str, Any]) -> str:
    return f"{format_int(row['n_patients'])}/{format_int(row['n_events'])}"


def latex_effect_summary(row: dict[str, Any]) -> str:
    effect = str(row.get("effect_summary") or "")
    return (
        effect.replace("RMST delta ", "RMST ")
        .replace(" days", " d")
        .replace("Interaction HR", "HRint")
        .replace("random-effects", "RE")
        .replace("FDR<0.10", "q below 0.10")
    )


def latex_interpretation(row: dict[str, Any]) -> str:
    if row.get("kind") == "hypoxia_signature":
        return "Nominal evidence; fails adjusted Cox and PH."
    if row.get("kind") == "two_signature":
        return "No significant interaction."
    if row.get("kind") == "pancancer":
        return "Cohort-specific FDR signals; modest heterogeneous meta-effect."
    return str(row.get("interpretation") or "")


def format_signature_entries(entries: list[dict[str, Any]]) -> str:
    formatted = []
    for entry in entries:
        gene = str(entry.get("gene_symbol") or "")
        weight = entry.get("weight")
        formatted.append(
            f"{gene} (w={weight:g})"
            if is_number(weight) and float(weight) != 1.0
            else gene
        )
    return ", ".join(item for item in formatted if item)


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def format_hr(model: dict[str, Any]) -> str:
    hr = format_number(model.get("hazard_ratio"), 2)
    low = format_number(model.get("hr_conf_low"), 2)
    high = format_number(model.get("hr_conf_high"), 2)
    return f"{hr} ({low}-{high})" if hr and low and high else ""


def format_prediction_interval(interval: dict[str, Any]) -> str:
    low = format_number(interval.get("hazard_ratio_low"), 2)
    high = format_number(interval.get("hazard_ratio_high"), 2)
    return f"{low}-{high}" if low and high else "not available"


def format_p(value: Any) -> str:
    if not is_number(value):
        return ""
    number = float(value)
    if number < 0.001:
        return f"{number:.2e}"
    return f"{number:.3f}"


def format_number(value: Any, digits: int) -> str:
    if not is_number(value):
        return ""
    return f"{float(value):.{digits}f}"


def format_int(value: Any) -> str:
    if not is_number(value):
        return ""
    return str(int(round(float(value))))


def is_number(value: Any) -> bool:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(number)


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
        "<": "\\textless{}",
        ">": "\\textgreater{}",
    }
    return "".join(replacements.get(char, char) for char in str(value))


def utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


if __name__ == "__main__":
    sys.exit(main())
