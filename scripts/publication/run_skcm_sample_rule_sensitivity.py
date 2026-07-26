#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "scripts" / "publication" / "run_cutpoint_benchmark.py"
BENCHMARK_PARENT = ROOT / "docs" / "publication" / "benchmark"
MANUSCRIPT_TABLE_PARENT = ROOT / "manuscript" / "bioinformatics_app_note" / "tables"


@dataclass(frozen=True)
class SensitivityCase:
    label: str
    sample_types: tuple[str, ...]


CASES = [
    SensitivityCase("all_eligible_samples", ()),
    SensitivityCase("primary_tumor_only", ("Primary Tumor",)),
    SensitivityCase("metastatic_only", ("Metastatic", "Additional Metastatic")),
]


def main() -> int:
    args = parse_args()
    output_dir = resolve_cli_path(args.output_dir or default_output_dir(args.gene))
    latex_table = resolve_cli_path(args.latex_table or default_latex_table(args.gene))
    for case in CASES:
        run_case(case, args, output_dir)
    rows = overview_rows(output_dir)
    write_overview_csv(rows, output_dir)
    write_overview_markdown(rows, output_dir, args.gene)
    write_overview_latex(rows, latex_table, args.gene)
    print(f"Wrote SKCM {args.gene.upper()} sample-rule sensitivity outputs under {output_dir}")
    print(f"Wrote {latex_table}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run TCGA-SKCM survival sensitivity checks by TCGA sample type."
    )
    parser.add_argument("--api-base-url", default="http://localhost:3000/tcga_explorer")
    parser.add_argument("--gene", default="PDCD1", help="Gene symbol to analyze in TCGA-SKCM.")
    parser.add_argument("--output-dir", type=Path, default=None, help="Output directory for the sensitivity record.")
    parser.add_argument("--latex-table", type=Path, default=None, help="Manuscript-ready LaTeX overview table path.")
    parser.add_argument("--max-concurrency", type=int, default=1)
    parser.add_argument("--method", default="median", choices=["maxstat", "median", "upper_quartile", "upper_lower_quartile", "percentile"])
    return parser.parse_args()


def default_output_dir(gene: str) -> Path:
    normalized = gene.strip().lower()
    if normalized == "pdcd1":
        return BENCHMARK_PARENT / "skcm_sample_rule_sensitivity"
    return BENCHMARK_PARENT / f"skcm_{normalized}_sample_rule_sensitivity"


def default_latex_table(gene: str) -> Path:
    normalized = gene.strip().lower()
    if normalized == "pdcd1":
        return MANUSCRIPT_TABLE_PARENT / "skcm_sample_rule_sensitivity.tex"
    return MANUSCRIPT_TABLE_PARENT / f"skcm_{normalized}_sample_rule_sensitivity.tex"


def resolve_cli_path(path: Path) -> Path:
    return path.resolve()


def display_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(ROOT))
    except ValueError:
        return str(resolved)


def run_case(case: SensitivityCase, args: argparse.Namespace, output_dir: Path) -> None:
    gene = args.gene.strip().upper()
    command = [
        sys.executable,
        str(RUNNER),
        "--api-base-url",
        args.api_base_url,
        "--benchmark-id",
        f"skcm_{gene.lower()}_os_{case.label}",
        "--title",
        f"TCGA-SKCM {gene} OS sample-rule sensitivity ({case.label.replace('_', ' ')})",
        "--cohort",
        "TCGA-SKCM",
        "--gene",
        gene,
        "--endpoint",
        "OS",
        "--methods",
        args.method,
        "--output-dir",
        str(output_dir / case.label),
        "--latex-table",
        str(output_dir / f"{case.label}.tex"),
        "--max-concurrency",
        str(args.max_concurrency),
    ]
    for sample_type in case.sample_types:
        command.extend(["--sample-type", sample_type])
    subprocess.run(command, cwd=ROOT, check=True)


def overview_rows(output_dir: Path) -> list[dict[str, Any]]:
    rows = []
    for case in CASES:
        summary_path = output_dir / case.label / "summary.csv"
        with summary_path.open(newline="", encoding="utf-8") as handle:
            row = next(csv.DictReader(handle))
        row["sample_rule"] = sample_rule_label(case)
        row["summary_path"] = display_path(summary_path)
        rows.append(row)
    apply_bh(
        rows,
        "continuous_univariable_p_value",
        "continuous_sample_rule_bh_p_value",
    )
    apply_bh(
        rows,
        "logrank_p_value",
        "grouped_sample_rule_bh_p_value",
    )
    return rows


def sample_rule_label(case: SensitivityCase) -> str:
    return {
        "all_eligible_samples": "All eligible",
        "primary_tumor_only": "Primary only",
        "metastatic_only": "Metastatic only",
    }.get(case.label, case.label.replace("_", " "))


def write_overview_csv(rows: list[dict[str, Any]], output_dir: Path) -> None:
    path = output_dir / "overview.csv"
    fields = [
        "sample_rule",
        "analysis_id",
        "continuous_n_patients",
        "continuous_n_events",
        "continuous_univariable_hr",
        "continuous_univariable_hr_conf_low",
        "continuous_univariable_hr_conf_high",
        "continuous_univariable_p_value",
        "continuous_sample_rule_bh_p_value",
        "continuous_adjusted_model",
        "continuous_adjusted_hr",
        "continuous_adjusted_p_value",
        "continuous_adjusted_ph_p_value",
        "continuous_adjusted_ph_global_p_value",
        "spline_nonlinearity_p_value",
        "n_patients",
        "n_events",
        "logrank_p_value",
        "grouped_sample_rule_bh_p_value",
        "univariable_hr",
        "univariable_p_value",
        "adjusted_model",
        "adjusted_p_value",
        "adjusted_ph_p_value",
        "adjusted_ph_global_p_value",
        "rmst_tau_days",
        "rmst_delta_days",
        "rmst_p_value",
        "bh_below_alpha",
        "marker_ph_flagged",
        "global_ph_flagged",
        "profile_notes",
        "patient_records_sha256",
        "continuous_patient_records_sha256",
        "audit_reproducibility_hash",
        "summary_path",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def write_overview_markdown(rows: list[dict[str, Any]], output_dir: Path, gene: str) -> None:
    path = output_dir / "README.md"
    gene = gene.strip().upper()
    lines = [
        f"# TCGA-SKCM {gene} OS Sample-Type Sensitivity",
        "",
        "Status date: 2026-07-24.",
        "",
        f"This record checks whether the TCGA-SKCM {gene} continuous and median-split results are",
        "sensitive to including all eligible RNA-seq samples versus restricting",
        "to primary or metastatic samples. The goal is not to select the most",
        "favorable subset; it is to expose a sample-composition choice that can",
        "change the downstream conclusion.",
        "",
        "Continuous Cox and grouped log-rank p-values use separate BH families across the three sample rules.",
        "",
        "| Sample rule | Continuous n/events | HR per SD | Continuous q | Adjusted p | Nonlinearity p | Grouped n/events | Grouped q | RMST delta @ tau | Notes |",
        "| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in rows:
        lines.append(
            "| {sample_rule} | {continuous_n}/{continuous_events} | {continuous_hr} | {continuous_q} | {continuous_adj} | {nonlinearity} | {n}/{events} | {grouped_q} | {rmst_delta} @ {tau} | {notes} |".format(
                sample_rule=row["sample_rule"],
                continuous_n=format_int(row.get("continuous_n_patients")),
                continuous_events=format_int(row.get("continuous_n_events")),
                continuous_hr=format_continuous_hr(row),
                continuous_q=format_p(row.get("continuous_sample_rule_bh_p_value")),
                continuous_adj=format_p(row.get("continuous_adjusted_p_value")),
                nonlinearity=format_p(row.get("spline_nonlinearity_p_value")),
                n=format_int(row.get("n_patients")),
                events=format_int(row.get("n_events")),
                grouped_q=format_p(row.get("grouped_sample_rule_bh_p_value")),
                rmst_delta=format_int(row.get("rmst_delta_days")),
                tau=format_int(row.get("rmst_tau_days")),
                notes=row.get("profile_notes") or "",
            )
        )
    lines.extend(
        [
            "",
            interpretation(rows),
            "",
            "Per-case summaries and run hashes are stored under the three",
            "subdirectories in this folder.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def interpretation(rows: list[dict[str, Any]]) -> str:
    continuous_low_q = [
        row["sample_rule"]
        for row in rows
        if is_number(row.get("continuous_sample_rule_bh_p_value"))
        and float(row["continuous_sample_rule_bh_p_value"]) <= 0.05
    ]
    grouped_low_q = [
        row["sample_rule"]
        for row in rows
        if is_number(row.get("grouped_sample_rule_bh_p_value"))
        and float(row["grouped_sample_rule_bh_p_value"]) <= 0.05
    ]
    marker_ph = [row["sample_rule"] for row in rows if row.get("marker_ph_flagged") == "True"]
    continuous_text = ", ".join(continuous_low_q) if continuous_low_q else "none"
    grouped_text = ", ".join(grouped_low_q) if grouped_low_q else "none"
    marker_ph_text = ", ".join(marker_ph) if marker_ph else "none"
    return (
        f"Interpretation: continuous-model BH q <= 0.05 for {continuous_text}; "
        f"grouped log-rank BH q <= 0.05 for {grouped_text}; marker-specific grouped PH caution for {marker_ph_text}. "
        "TCGA-SKCM sample composition should therefore be reported as a sensitivity setting."
    )


def write_overview_latex(rows: list[dict[str, Any]], latex_table: Path, gene: str) -> None:
    gene = gene.strip().upper()
    label_gene = gene.lower()
    lines = [
        "\\begin{table}[t]",
        "\\centering",
        "\\footnotesize",
        f"\\caption{{TCGA-SKCM {gene} OS sample-type sensitivity. Continuous Cox and grouped median-split log-rank tests use separate BH families across the three sample rules.}}",
        f"\\label{{tab:skcm-{label_gene}-sample-rule-sensitivity}}",
        "\\begin{tabular}{lrrrrrrr}",
        "\\toprule",
        "Rule & Continuous n/events & HR/SD & q & Nonlin. p & Grouped n/events & q & RMST d \\\\",
        "\\midrule",
    ]
    for row in rows:
        lines.append(
            "{sample_rule} & {continuous_n}/{continuous_events} & {continuous_hr} & {continuous_q} & {nonlinearity} & {n}/{events} & {grouped_q} & {rmst_delta} \\\\".format(
                sample_rule=latex_escape(latex_sample_rule(row["sample_rule"])),
                continuous_n=format_int(row.get("continuous_n_patients")),
                continuous_events=format_int(row.get("continuous_n_events")),
                continuous_hr=format_continuous_hr(row),
                continuous_q=format_p(row.get("continuous_sample_rule_bh_p_value")),
                nonlinearity=format_p(row.get("spline_nonlinearity_p_value")),
                n=format_int(row.get("n_patients")),
                events=format_int(row.get("n_events")),
                grouped_q=format_p(row.get("grouped_sample_rule_bh_p_value")),
                rmst_delta=format_int(row.get("rmst_delta_days")),
            )
        )
    lines.extend(["\\bottomrule", "\\end{tabular}", "\\end{table}", ""])
    latex_table.parent.mkdir(parents=True, exist_ok=True)
    latex_table.write_text("\n".join(lines), encoding="utf-8")


def latex_sample_rule(label: str) -> str:
    return {
        "All eligible": "All",
        "Primary only": "Primary",
        "Metastatic only": "Metastatic",
    }.get(label, label)


def format_p(value: Any) -> str:
    if not is_number(value):
        return ""
    number = float(value)
    if number < 0.001:
        return f"{number:.2e}"
    return f"{number:.3f}"


def format_hr(row: dict[str, Any]) -> str:
    hr = row.get("univariable_hr")
    low = row.get("univariable_hr_conf_low")
    high = row.get("univariable_hr_conf_high")
    if not (is_number(hr) and is_number(low) and is_number(high)):
        return ""
    return f"{float(hr):.2f} ({float(low):.2f}-{float(high):.2f})"


def format_continuous_hr(row: dict[str, Any]) -> str:
    hr = row.get("continuous_univariable_hr")
    low = row.get("continuous_univariable_hr_conf_low")
    high = row.get("continuous_univariable_hr_conf_high")
    if not (is_number(hr) and is_number(low) and is_number(high)):
        return ""
    return f"{float(hr):.2f} ({float(low):.2f}-{float(high):.2f})"


def apply_bh(
    rows: list[dict[str, Any]],
    p_key: str,
    out_key: str,
) -> None:
    indexed = [
        (index, float(row[p_key]))
        for index, row in enumerate(rows)
        if is_number(row.get(p_key))
    ]
    total = len(indexed)
    previous = 1.0
    adjusted_by_index: dict[int, float] = {}
    for reverse_rank, (index, p_value) in enumerate(
        sorted(indexed, key=lambda item: item[1], reverse=True),
        start=1,
    ):
        rank = total - reverse_rank + 1
        adjusted = min(previous, p_value * total / rank)
        previous = adjusted
        adjusted_by_index[index] = min(adjusted, 1.0)
    for index, row in enumerate(rows):
        row[out_key] = adjusted_by_index.get(index)


def format_int(value: Any) -> str:
    if not is_number(value):
        return ""
    return str(int(round(float(value))))


def is_number(value: Any) -> bool:
    try:
        float(value)
    except (TypeError, ValueError):
        return False
    return True


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
    }
    return "".join(replacements.get(char, char) for char in value)


if __name__ == "__main__":
    sys.exit(main())
