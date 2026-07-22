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
BENCHMARK_ROOT = ROOT / "docs" / "publication" / "benchmark"
TABLE_ROOT = ROOT / "manuscript" / "bioinformatics_app_note" / "tables"
ROBUSTNESS_ALPHA = 0.05


@dataclass(frozen=True)
class BenchmarkCase:
    benchmark_id: str
    cohort: str
    gene: str
    endpoint: str
    title: str
    output_name: str
    table_name: str


CASES = [
    BenchmarkCase(
        "kirc_ca9_cutpoints",
        "TCGA-KIRC",
        "CA9",
        "OS",
        "TCGA-KIRC CA9 OS cutpoint benchmark",
        "kirc_ca9_cutpoint_benchmark",
        "kirc_ca9_cutpoint_benchmark.tex",
    ),
    BenchmarkCase(
        "brca_mki67_os_cutpoints",
        "TCGA-BRCA",
        "MKI67",
        "OS",
        "TCGA-BRCA MKI67 OS cutpoint benchmark",
        "brca_mki67_os_cutpoint_benchmark",
        "brca_mki67_os_cutpoint_benchmark.tex",
    ),
    BenchmarkCase(
        "brca_mki67_pfi_cutpoints",
        "TCGA-BRCA",
        "MKI67",
        "PFI",
        "TCGA-BRCA MKI67 PFI cutpoint benchmark",
        "brca_mki67_pfi_cutpoint_benchmark",
        "brca_mki67_pfi_cutpoint_benchmark.tex",
    ),
    BenchmarkCase(
        "skcm_pdcd1_os_cutpoints",
        "TCGA-SKCM",
        "PDCD1",
        "OS",
        "TCGA-SKCM PDCD1 OS cutpoint benchmark",
        "skcm_pdcd1_os_cutpoint_benchmark",
        "skcm_pdcd1_os_cutpoint_benchmark.tex",
    ),
    BenchmarkCase(
        "luad_cd274_os_cutpoints",
        "TCGA-LUAD",
        "CD274",
        "OS",
        "TCGA-LUAD CD274 OS cutpoint benchmark",
        "luad_cd274_os_cutpoint_benchmark",
        "luad_cd274_os_cutpoint_benchmark.tex",
    ),
    BenchmarkCase(
        "luad_cd274_pfi_cutpoints",
        "TCGA-LUAD",
        "CD274",
        "PFI",
        "TCGA-LUAD CD274 PFI cutpoint benchmark",
        "luad_cd274_pfi_cutpoint_benchmark",
        "luad_cd274_pfi_cutpoint_benchmark.tex",
    ),
]


def main() -> int:
    args = parse_args()
    selected = [case for case in CASES if not args.only or case.benchmark_id in args.only]
    if not selected:
        raise ValueError(f"No benchmark cases matched --only: {args.only}")

    for case in selected:
        run_case(case, args)
    rows = [summarize_case(case) for case in CASES if summary_path(case).exists()]
    write_overview_csv(BENCHMARK_ROOT / "single_gene_benchmark_overview.csv", rows)
    write_overview_markdown(BENCHMARK_ROOT / "single_gene_benchmark_overview.md", rows)
    write_overview_latex(TABLE_ROOT / "single_gene_benchmark_overview.tex", rows)
    print(f"Wrote {BENCHMARK_ROOT / 'single_gene_benchmark_overview.csv'}")
    print(f"Wrote {TABLE_ROOT / 'single_gene_benchmark_overview.tex'}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the single-gene publication benchmark suite.")
    parser.add_argument("--api-base-url", default="http://localhost:3000/tcga_explorer")
    parser.add_argument("--max-concurrency", type=int, default=1)
    parser.add_argument("--only", action="append", default=[], help="Benchmark id to run. Can be repeated.")
    return parser.parse_args()


def run_case(case: BenchmarkCase, args: argparse.Namespace) -> None:
    command = [
        sys.executable,
        str(RUNNER),
        "--api-base-url",
        args.api_base_url,
        "--benchmark-id",
        case.benchmark_id,
        "--title",
        case.title,
        "--cohort",
        case.cohort,
        "--gene",
        case.gene,
        "--endpoint",
        case.endpoint,
        "--output-dir",
        str(BENCHMARK_ROOT / case.output_name),
        "--latex-table",
        str(TABLE_ROOT / case.table_name),
        "--max-concurrency",
        str(args.max_concurrency),
    ]
    subprocess.run(command, cwd=ROOT, check=True)


def summarize_case(case: BenchmarkCase) -> dict[str, Any]:
    rows = read_csv(summary_path(case))
    completed = [row for row in rows if row.get("status") == "completed"]
    survived = [row for row in completed if row.get("survives") == "True"]
    nominal = [row for row in completed if is_significant(row.get("logrank_p_value"))]
    bh = [row for row in completed if is_significant(row.get("bh_logrank_p_value"))]
    adjusted = [row for row in completed if is_significant(row.get("adjusted_p_value"))]
    rmst = [row for row in completed if is_significant(row.get("rmst_p_value"))]
    ph_flagged = [
        row
        for row in completed
        if is_number(row.get("adjusted_ph_global_p_value")) and float(row["adjusted_ph_global_p_value"]) < ROBUSTNESS_ALPHA
    ]
    return {
        "benchmark_id": case.benchmark_id,
        "cohort": case.cohort,
        "gene": case.gene,
        "endpoint": case.endpoint,
        "methods_completed": len(completed),
        "nominal_logrank_methods": len(nominal),
        "bh_methods": len(bh),
        "adjusted_methods": len(adjusted),
        "rmst_methods": len(rmst),
        "ph_flagged_methods": len(ph_flagged),
        "surviving_methods": len(survived),
        "best_bh_logrank_p": min_number(row.get("bh_logrank_p_value") for row in completed),
        "best_adjusted_p": min_number(row.get("adjusted_p_value") for row in completed),
        "best_rmst_p": min_number(row.get("rmst_p_value") for row in completed),
        "decision": "At least one survives" if survived else "No method survives",
        "summary_path": str(summary_path(case).relative_to(ROOT)),
    }


def summary_path(case: BenchmarkCase) -> Path:
    return BENCHMARK_ROOT / case.output_name / "summary.csv"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_overview_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = [
        "benchmark_id",
        "cohort",
        "gene",
        "endpoint",
        "methods_completed",
        "nominal_logrank_methods",
        "bh_methods",
        "adjusted_methods",
        "rmst_methods",
        "ph_flagged_methods",
        "surviving_methods",
        "best_bh_logrank_p",
        "best_adjusted_p",
        "best_rmst_p",
        "decision",
        "summary_path",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def write_overview_markdown(path: Path, rows: list[dict[str, Any]]) -> None:
    lines = [
        "# Single-Gene Cutpoint Benchmark Overview",
        "",
        "| Cohort | Gene | Endpoint | Completed | BH methods | Adjusted methods | RMST methods | PH flagged | Surviving | Decision |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in rows:
        lines.append(
            "| {cohort} | {gene} | {endpoint} | {completed} | {bh} | {adjusted} | {rmst} | {ph} | {surviving} | {decision} |".format(
                cohort=row["cohort"],
                gene=row["gene"],
                endpoint=row["endpoint"],
                completed=row["methods_completed"],
                bh=row["bh_methods"],
                adjusted=row["adjusted_methods"],
                rmst=row["rmst_methods"],
                ph=row["ph_flagged_methods"],
                surviving=row["surviving_methods"],
                decision=row["decision"],
            )
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_overview_latex(path: Path, rows: list[dict[str, Any]]) -> None:
    lines = [
        "\\begin{table}[t]",
        "\\centering",
        "\\caption{Single-gene cutpoint robustness benchmark overview.}",
        "\\label{tab:single-gene-benchmark-overview}",
        "\\begin{tabular}{lllrrrrl}",
        "\\toprule",
        "Cohort & Gene & Endpoint & BH & Adj. & RMST & Surv. & Decision \\\\",
        "\\midrule",
    ]
    for row in rows:
        lines.append(
            " & ".join(
                [
                    row["cohort"].replace("TCGA-", ""),
                    row["gene"],
                    row["endpoint"],
                    str(row["bh_methods"]),
                    str(row["adjusted_methods"]),
                    str(row["rmst_methods"]),
                    str(row["surviving_methods"]),
                    row["decision"],
                ]
            )
            + " \\\\"
        )
    lines.extend(["\\bottomrule", "\\end{tabular}", "\\end{table}", ""])
    path.write_text("\n".join(lines), encoding="utf-8")


def is_significant(value: Any) -> bool:
    return is_number(value) and float(value) <= ROBUSTNESS_ALPHA


def is_number(value: Any) -> bool:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return number == number and abs(number) != float("inf")


def min_number(values: Any) -> float | None:
    numbers = [float(value) for value in values if is_number(value)]
    return min(numbers) if numbers else None


if __name__ == "__main__":
    sys.exit(main())
