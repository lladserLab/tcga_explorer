#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
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
DEFAULT_METHODS = ["maxstat", "median", "upper_quartile", "upper_lower_quartile", "percentile"]
ROBUSTNESS_ALPHA = 0.05


def main() -> int:
    args = parse_args()
    benchmark_id = args.benchmark_id or slugify(f"{args.cohort}_{args.gene}_{args.endpoint}_cutpoint_benchmark")
    title = args.title or f"{args.cohort} {args.gene} {args.endpoint} cutpoint benchmark"
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    args.latex_table.parent.mkdir(parents=True, exist_ok=True)

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
        )
        for method in args.methods
    ]
    started_at = utc_now()
    batch = client.post("/api/analyses/batch", {"analyses": analyses, "max_concurrency": args.max_concurrency})
    finished_at = utc_now()

    rows = summarize_batch(batch)
    apply_bh(rows, "logrank_p_value", "bh_logrank_p_value")
    for row in rows:
        annotate_robustness(row)

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
        "methods": args.methods,
        "custom_percentile": args.custom_percentile,
        "robustness_alpha": ROBUSTNESS_ALPHA,
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
    write_latex_table(args.latex_table, metadata, rows)

    print(f"Completed {metadata['batch']['completed']}/{metadata['batch']['total']} analyses")
    print(f"Wrote {output_dir / 'summary.csv'}")
    print(f"Wrote {output_dir / 'summary.md'}")
    print(f"Wrote {args.latex_table}")
    return 0 if metadata["batch"]["completed"] else 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the publication cutpoint benchmark through the TCGA Explorer HTTP API."
    )
    parser.add_argument("--api-base-url", default=DEFAULT_API_BASE_URL)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--latex-table", type=Path, default=DEFAULT_LATEX_TABLE)
    parser.add_argument("--benchmark-id", default=DEFAULT_BENCHMARK_ID)
    parser.add_argument("--title", default="")
    parser.add_argument("--cohort", default="TCGA-KIRC")
    parser.add_argument("--gene", default="CA9")
    parser.add_argument("--endpoint", default="OS", choices=["OS", "DSS", "DFI", "PFI"])
    parser.add_argument("--expression-scale", default="log2_tpm")
    parser.add_argument("--time-unit", default="months", choices=["days", "months", "years"])
    parser.add_argument("--methods", nargs="+", default=DEFAULT_METHODS)
    parser.add_argument("--custom-percentile", type=float, default=75.0)
    parser.add_argument("--max-concurrency", type=int, default=1)
    return parser.parse_args()


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
        "filters": {
            "sample_types": [],
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
        "show_risk_table": True,
        "plot_style": {
            "palette": ["#2f756f", "#d7953f", "#b44b3f"],
            "font_family": "sans",
            "plot_aspect": "square",
            "base_font_size": 12,
            "axis_text_size": 11,
            "axis_title_size": 12,
            "show_grid": True,
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
        univariable = find_model(metrics.get("cox_models"), "univariable")
        adjusted = downstream_adjusted_model(metrics.get("cox_models"))
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
            "n_patients": metrics.get("n_patients"),
            "n_events": metrics.get("n_events"),
            "threshold": cutpoint.get("threshold"),
            "custom_percentile": cutpoint.get("percentile"),
            "group_counts": stable_json(metrics.get("group_counts")),
            "event_counts": stable_json(metrics.get("event_counts")),
            "median_survival_days": stable_json(metrics.get("median_survival_days")),
            "logrank_p_value": metrics.get("logrank_p_value"),
            "univariable_hr": univariable.get("hazard_ratio"),
            "univariable_hr_conf_low": univariable.get("hr_conf_low"),
            "univariable_hr_conf_high": univariable.get("hr_conf_high"),
            "univariable_p_value": univariable.get("p_value"),
            "adjusted_model": adjusted.get("model"),
            "adjusted_hr": adjusted.get("hazard_ratio"),
            "adjusted_hr_conf_low": adjusted.get("hr_conf_low"),
            "adjusted_hr_conf_high": adjusted.get("hr_conf_high"),
            "adjusted_p_value": adjusted.get("p_value"),
            "adjusted_ph_p_value": adjusted.get("ph_p_value"),
            "adjusted_ph_global_p_value": adjusted.get("ph_global_p_value"),
            "rmst_status": rmst.get("status"),
            "rmst_tau_days": rmst.get("tau_days"),
            "rmst_delta_days": (rmst.get("difference") or {}).get("estimate_days"),
            "rmst_delta_conf_low": (rmst.get("difference") or {}).get("conf_low"),
            "rmst_delta_conf_high": (rmst.get("difference") or {}).get("conf_high"),
            "rmst_p_value": (rmst.get("difference") or {}).get("p_value"),
            "audit_reproducibility_hash": audit.get("reproducibility_hash"),
            "patient_records_sha256": audit.get("patient_records_sha256"),
            "downloads": stable_json(result.get("downloads")),
        }
        rows.append(row)
    return sorted(rows, key=lambda row: int(row.get("index") or 0))


def find_model(models: list[dict[str, Any]] | None, model_id: str) -> dict[str, Any]:
    for model in models or []:
        if model.get("model") == model_id and model.get("status") == "completed":
            return model
    return {}


def downstream_adjusted_model(models: list[dict[str, Any]] | None) -> dict[str, Any]:
    return (
        find_model(models, "stage_grade_adjusted")
        or find_model(models, "stage_adjusted")
        or find_model(models, "grade_adjusted")
    )


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


def annotate_robustness(row: dict[str, Any]) -> None:
    bh_pass = is_significant(row.get("bh_logrank_p_value"))
    cox_pass = is_significant(row.get("univariable_p_value"))
    adjusted_pass = is_significant(row.get("adjusted_p_value"))
    rmst_pass = row.get("rmst_status") == "completed" and is_significant(row.get("rmst_p_value"))
    ph_value = row.get("adjusted_ph_global_p_value")
    ph_ok = not is_finite_number(ph_value) or float(ph_value) >= ROBUSTNESS_ALPHA
    if not bh_pass:
        reason = "Fails BH"
    elif not cox_pass:
        reason = "Fails Cox"
    elif not adjusted_pass:
        reason = "Fails adjusted"
    elif not rmst_pass:
        reason = "Fails RMST"
    elif not ph_ok:
        reason = "PH flagged"
    else:
        reason = "Survives"
    hr = row.get("univariable_hr")
    row["direction"] = "Protective" if is_finite_number(hr) and float(hr) < 1 else "Harmful" if is_finite_number(hr) and float(hr) > 1 else ""
    row["bh_pass"] = bh_pass
    row["cox_pass"] = cox_pass
    row["adjusted_pass"] = adjusted_pass
    row["rmst_pass"] = rmst_pass
    row["ph_ok"] = ph_ok
    row["survives"] = bh_pass and cox_pass and adjusted_pass and rmst_pass and ph_ok
    row["robustness_reason"] = reason


def is_significant(value: Any) -> bool:
    return is_finite_number(value) and float(value) <= ROBUSTNESS_ALPHA


def is_finite_number(value: Any) -> bool:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(number)


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
        "n_patients",
        "n_events",
        "threshold",
        "custom_percentile",
        "logrank_p_value",
        "bh_logrank_p_value",
        "univariable_hr",
        "univariable_hr_conf_low",
        "univariable_hr_conf_high",
        "univariable_p_value",
        "adjusted_model",
        "adjusted_hr",
        "adjusted_hr_conf_low",
        "adjusted_hr_conf_high",
        "adjusted_p_value",
        "adjusted_ph_global_p_value",
        "rmst_tau_days",
        "rmst_delta_days",
        "rmst_delta_conf_low",
        "rmst_delta_conf_high",
        "rmst_p_value",
        "direction",
        "survives",
        "robustness_reason",
        "audit_reproducibility_hash",
        "patient_records_sha256",
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
        f"- Decision rule: BH log-rank, univariable Cox, adjusted Cox and RMST p <= {ROBUSTNESS_ALPHA}; adjusted PH global p not flagged.",
        "",
        "| Method | n | Events | BH log-rank | HR | Cox p | Adjusted p | PH global p | RMST delta days | RMST p | Survives |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in rows:
        lines.append(
            "| {method} | {n} | {events} | {bh} | {hr} | {cox} | {adj} | {ph} | {rmst_delta} | {rmst_p} | {survives} |".format(
                method=row.get("method") or "",
                n=format_int(row.get("n_patients")),
                events=format_int(row.get("n_events")),
                bh=format_p(row.get("bh_logrank_p_value")),
                hr=format_hr(row),
                cox=format_p(row.get("univariable_p_value")),
                adj=format_p(row.get("adjusted_p_value")),
                ph=format_p(row.get("adjusted_ph_global_p_value")),
                rmst_delta=format_number(row.get("rmst_delta_days"), digits=0),
                rmst_p=format_p(row.get("rmst_p_value")),
                survives="yes" if row.get("survives") else f"no ({row.get('robustness_reason')})",
            )
        )
    lines.extend(
        [
            "",
            "## Audit Hashes",
            "",
            "| Method | Analysis ID | Reproducibility hash | Patient records SHA-256 |",
            "| --- | --- | --- | --- |",
        ]
    )
    for row in rows:
        lines.append(
            f"| {row.get('method') or ''} | `{row.get('analysis_id') or ''}` | "
            f"`{row.get('audit_reproducibility_hash') or ''}` | `{row.get('patient_records_sha256') or ''}` |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_latex_table(path: Path, metadata: dict[str, Any], rows: list[dict[str, Any]]) -> None:
    latex_id = latex_escape(str(metadata["benchmark_id"]).replace("_", "-"))
    caption = latex_escape(str(metadata["title"]).replace("cutpoint benchmark", "cutpoint robustness benchmark"))
    lines = [
        "\\begin{table}[t]",
        "\\centering",
        f"\\caption{{{caption}.}}",
        f"\\label{{tab:{latex_id}}}",
        "\\begin{tabular}{lrrrrrrl}",
        "\\toprule",
        "Method & n & Events & BH $p$ & Cox $p$ & Adj. $p$ & RMST $\\Delta$ & Decision \\\\",
        "\\midrule",
    ]
    for row in rows:
        decision = "Yes" if row.get("survives") else str(row.get("robustness_reason") or "No")
        lines.append(
            " & ".join(
                [
                    latex_escape(method_label(str(row.get("method") or ""))),
                    format_int(row.get("n_patients")),
                    format_int(row.get("n_events")),
                    format_p(row.get("bh_logrank_p_value")),
                    format_p(row.get("univariable_p_value")),
                    format_p(row.get("adjusted_p_value")),
                    format_number(row.get("rmst_delta_days"), digits=0),
                    latex_escape(decision),
                ]
            )
            + " \\\\"
        )
    lines.extend(["\\bottomrule", "\\end{tabular}", "\\end{table}", ""])
    path.write_text("\n".join(lines), encoding="utf-8")


def stable_json(value: Any) -> str:
    if value is None:
        return ""
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def method_label(method: str) -> str:
    return {
        "maxstat": "Maxstat",
        "median": "Median",
        "upper_quartile": "Upper Q",
        "upper_lower_quartile": "Outer Q",
        "percentile": "75th pct.",
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
