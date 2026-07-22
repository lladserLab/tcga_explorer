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


def main() -> int:
    args = parse_args()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    TABLE_PATH.parent.mkdir(parents=True, exist_ok=True)
    client = ApiClient(args.api_base_url)

    started_at = utc_now()
    signature_result = client.post("/api/analyses", signature_payload())
    combined_result = client.post("/api/analyses/combined", combined_payload())
    pancancer_result = client.post("/api/pancancer/survival", pancancer_payload())
    finished_at = utc_now()

    feature_rows = [
        summarize_analysis("weighted_signature", "KIRC hypoxia z-score signature", signature_result),
        summarize_combined("two_signature", "SKCM effector x exhaustion signatures", combined_result),
        summarize_pancancer("pancancer", "CA9 pan-cancer continuous Cox", pancancer_result),
    ]
    metadata = {
        "started_at": started_at,
        "finished_at": finished_at,
        "api_base_url": args.api_base_url,
        "feature_rows": feature_rows,
    }
    write_json(OUTPUT_DIR / "feature_benchmark_metadata.json", metadata)
    write_json(OUTPUT_DIR / "weighted_signature.raw.json", signature_result)
    write_json(OUTPUT_DIR / "two_signature.raw.json", combined_result)
    write_json(OUTPUT_DIR / "pancancer.raw.json", pancancer_result)
    write_csv(OUTPUT_DIR / "feature_benchmark_summary.csv", feature_rows)
    write_markdown(OUTPUT_DIR / "feature_benchmark_summary.md", metadata, feature_rows)
    write_latex(TABLE_PATH, feature_rows)
    print(f"Wrote {OUTPUT_DIR / 'feature_benchmark_summary.md'}")
    print(f"Wrote {TABLE_PATH}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run feature benchmarks for the TCGA Explorer Application Note.")
    parser.add_argument("--api-base-url", default="http://localhost:3000/tcga_explorer")
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
        "cohort": "TCGA-KIRC",
        "gene_symbol": "HYPOXIA_SIGNATURE",
        "signature_method": "zscore",
        "signature_genes": HYPOXIA_SIGNATURE,
        "endpoint": "OS",
        "expression_scale": "log2_tpm",
        "cutpoint_method": "median",
        "custom_percentile": None,
        "filters": empty_filters(),
        "time_unit": "months",
        "show_confidence_interval": True,
        "show_risk_table": True,
        "plot_style": plot_style(),
    }


def combined_payload() -> dict[str, Any]:
    return {
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
        "expression_scale": "log2_tpm",
        "combination_method": "median",
        "filters": empty_filters(),
        "time_unit": "months",
        "show_confidence_interval": True,
        "show_risk_table": True,
        "plot_style": {
            **plot_style(),
            "palette": ["#2f756f", "#d7953f", "#5a6f9f", "#b44b3f"],
        },
    }


def pancancer_payload() -> dict[str, Any]:
    return {
        "gene_symbol": "CA9",
        "signature_method": "single",
        "signature_genes": [],
        "index_cohort": "TCGA-KIRC",
        "cohorts": [],
        "endpoint": "OS",
        "endpoint_mode": "same_endpoint",
        "expression_scale": "log2_tpm",
        "filters": empty_filters(),
        "min_patients": 10,
        "min_events": 5,
        "fdr_threshold": 0.10,
    }


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
        "palette": ["#2f756f", "#d7953f", "#b44b3f"],
        "font_family": "sans",
        "plot_aspect": "square",
        "base_font_size": 12,
        "axis_text_size": 11,
        "axis_title_size": 12,
        "show_grid": True,
        "show_title": False,
        "plot_title": "",
    }


def summarize_analysis(kind: str, label: str, result: dict[str, Any]) -> dict[str, Any]:
    metrics = result.get("metrics") or {}
    adjusted = downstream_adjusted_model(metrics.get("cox_models"))
    rmst = metrics.get("rmst") or {}
    audit = metrics.get("audit_report") or {}
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
        "primary_statistic": "log-rank",
        "primary_p_value": metrics.get("logrank_p_value"),
        "adjusted_p_value": adjusted.get("p_value"),
        "ph_global_p_value": adjusted.get("ph_global_p_value"),
        "rmst_p_value": (rmst.get("difference") or {}).get("p_value"),
        "summary": f"HR {format_hr(adjusted)}; RMST delta {format_number((rmst.get('difference') or {}).get('estimate_days'), 0)} days",
        "audit_hash": audit.get("reproducibility_hash"),
    }


def summarize_combined(kind: str, label: str, result: dict[str, Any]) -> dict[str, Any]:
    metrics = result.get("metrics") or {}
    interaction = first_completed(metrics.get("signature_interaction_cox_models"))
    interaction_term = interaction.get("interaction_term") or {}
    audit = metrics.get("audit_report") or {}
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
        "primary_statistic": "interaction Cox",
        "primary_p_value": interaction_term.get("p_value"),
        "adjusted_p_value": interaction_term.get("p_value"),
        "ph_global_p_value": interaction.get("ph_global_p_value"),
        "rmst_p_value": None,
        "summary": f"Interaction HR {format_number(interaction_term.get('hazard_ratio'), 2)}; groups {len(metrics.get('group_counts') or {})}",
        "audit_hash": audit.get("reproducibility_hash"),
    }


def summarize_pancancer(kind: str, label: str, result: dict[str, Any]) -> dict[str, Any]:
    completed = [row for row in result.get("results") or [] if row.get("status") == "completed"]
    significant = [row for row in completed if row.get("significant")]
    reference = result.get("reference") or {}
    meta = result.get("meta_analysis") or {}
    random_effect = meta.get("random_effect") or {}
    return {
        "kind": kind,
        "label": label,
        "status": result.get("status"),
        "id": result.get("scan_id"),
        "cohort": "pan-cancer",
        "marker": result.get("gene_symbol"),
        "endpoint": result.get("endpoint"),
        "n_patients": sum(int(row.get("n_patients") or 0) for row in completed),
        "n_events": sum(int(row.get("n_events") or 0) for row in completed),
        "primary_statistic": "continuous Cox/FDR",
        "primary_p_value": reference.get("p_value"),
        "adjusted_p_value": reference.get("fdr"),
        "ph_global_p_value": reference.get("ph_p_value"),
        "rmst_p_value": None,
        "summary": f"{len(significant)}/{len(completed)} cohorts FDR<0.10; random-effects HR {format_number(random_effect.get('hazard_ratio'), 2)}",
        "audit_hash": result.get("scan_id"),
    }


def downstream_adjusted_model(models: list[dict[str, Any]] | None) -> dict[str, Any]:
    return (
        find_model(models, "stage_grade_adjusted")
        or find_model(models, "stage_adjusted")
        or find_model(models, "grade_adjusted")
    )


def find_model(models: list[dict[str, Any]] | None, model_id: str) -> dict[str, Any]:
    for model in models or []:
        if model.get("model") == model_id and model.get("status") == "completed":
            return model
    return {}


def first_completed(models: list[dict[str, Any]] | None) -> dict[str, Any]:
    for model in models or []:
        if model.get("status") == "completed":
            return model
    return {}


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
        "adjusted_p_value",
        "ph_global_p_value",
        "rmst_p_value",
        "summary",
        "audit_hash",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def write_markdown(path: Path, metadata: dict[str, Any], rows: list[dict[str, Any]]) -> None:
    lines = [
        "# Feature Benchmark Summary",
        "",
        f"- Started: {metadata['started_at']}",
        f"- Finished: {metadata['finished_at']}",
        f"- API base URL: `{metadata['api_base_url']}`",
        "",
        "| Workflow | Cohort | Endpoint | n | Events | Statistic | p | Adjusted/FDR p | PH p | Summary |",
        "| --- | --- | --- | ---: | ---: | --- | ---: | ---: | ---: | --- |",
    ]
    for row in rows:
        lines.append(
            "| {label} | {cohort} | {endpoint} | {n} | {events} | {stat} | {p} | {adj} | {ph} | {summary} |".format(
                label=row["label"],
                cohort=row["cohort"],
                endpoint=row["endpoint"],
                n=format_int(row["n_patients"]),
                events=format_int(row["n_events"]),
                stat=row["primary_statistic"],
                p=format_p(row["primary_p_value"]),
                adj=format_p(row["adjusted_p_value"]),
                ph=format_p(row["ph_global_p_value"]),
                summary=row["summary"],
            )
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_latex(path: Path, rows: list[dict[str, Any]]) -> None:
    lines = [
        "\\begin{table}[t]",
        "\\centering",
        "\\small",
        "\\caption{Feature benchmark summary for signatures, two-signature interaction and pan-cancer Cox.}",
        "\\label{tab:feature-benchmark-summary}",
        "\\begin{tabularx}{\\linewidth}{llrrX}",
        "\\toprule",
        "Workflow & Endpoint & n & Events & Summary \\\\",
        "\\midrule",
    ]
    for row in rows:
        lines.append(
            " & ".join(
                [
                    latex_escape(latex_label(row)),
                    row["endpoint"] or "",
                    format_int(row["n_patients"]),
                    format_int(row["n_events"]),
                    latex_escape(latex_summary(row)),
                ]
            )
            + " \\\\"
        )
    lines.extend(["\\bottomrule", "\\end{tabularx}", "\\end{table}", ""])
    path.write_text("\n".join(lines), encoding="utf-8")


def latex_label(row: dict[str, Any]) -> str:
    labels = {
        "weighted_signature": "KIRC hypoxia signature",
        "two_signature": "SKCM effector x exhaustion",
        "pancancer": "CA9 pan-cancer Cox",
    }
    return labels.get(str(row.get("kind")), str(row.get("label") or ""))


def latex_summary(row: dict[str, Any]) -> str:
    primary = format_p(row["primary_p_value"])
    adjusted = format_p(row["adjusted_p_value"])
    ph = format_p(row["ph_global_p_value"])
    summary = str(row.get("summary") or "")
    summary = summary.replace("RMST delta ", "RMST +")
    summary = summary.replace(" days", " d")
    summary = summary.replace("Interaction HR", "HRint")
    summary = summary.replace("random-effects", "RE")
    summary = summary.replace("FDR<0.10", "q below 0.10")
    if row.get("kind") == "weighted_signature":
        return f"log-rank p={primary}; adj={adjusted}; PH={ph}; {summary}"
    if row.get("kind") == "two_signature":
        return f"interaction p={primary}; adj={adjusted}; PH={ph}; {summary}"
    if row.get("kind") == "pancancer":
        return f"Cox p={primary}; FDR={adjusted}; {summary}"
    return f"{row['primary_statistic']} p={primary}; {summary}"


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def format_hr(model: dict[str, Any]) -> str:
    hr = format_number(model.get("hazard_ratio"), 2)
    low = format_number(model.get("hr_conf_low"), 2)
    high = format_number(model.get("hr_conf_high"), 2)
    return f"{hr} ({low}-{high})" if hr and low and high else ""


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
    }
    return "".join(replacements.get(char, char) for char in str(value))


def utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


if __name__ == "__main__":
    sys.exit(main())
