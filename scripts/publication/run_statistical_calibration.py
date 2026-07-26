#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = (
    ROOT / "docs" / "publication" / "benchmark" / "statistical_calibration"
)
DEFAULT_LATEX_TABLE = (
    ROOT
    / "manuscript"
    / "bioinformatics_app_note"
    / "tables"
    / "statistical_calibration.tex"
)
DEFAULT_SOURCE_BENCHMARK = (
    ROOT
    / "docs"
    / "publication"
    / "benchmark"
    / "lihc_cdc20_os_cutpoint_benchmark"
    / "benchmark_results.raw.json"
)
DEFAULT_R_SCRIPT = ROOT / "scripts" / "publication" / "statistical_calibration.R"
METHODS = [
    "maxstat",
    "median",
    "upper_quartile",
    "upper_lower_quartile",
]
SCENARIO_LABELS = {
    "observed_null_permutation": "LIHC expression permutation",
    "null": "Simulated null",
    "linear_ph": "Linear PH",
    "delayed_non_ph": "Delayed non-PH",
    "u_shaped_nonlinear": "U-shaped nonlinear",
}
METRIC_LABELS = {
    "continuous_linear": "Linear Cox",
    "spline_nonlinearity": "Spline nonlinearity",
    "marker_ph": "Marker PH diagnostic",
    "grouped_family_holm": "Grouped-family Holm",
    "maxstat_naive": "Maxstat naive",
    "maxstat_lau94": "Maxstat Lau94",
    "median_logrank": "Median log-rank",
    "median_cox": "Median Cox",
    "median_rmst": "Median RMST",
}


def main() -> int:
    args = parse_args()
    output_dir = args.output_dir.resolve()
    latex_table = args.latex_table.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    latex_table.parent.mkdir(parents=True, exist_ok=True)

    design_path = output_dir / "calibration_design.json"
    result_path = output_dir / "calibration_results.raw.json"
    permutation_path = output_dir / "permutation_replicates.csv"
    simulation_path = output_dir / "simulation_replicates.csv"
    if args.check_only:
        check_existing_outputs(
            design_path=design_path,
            result_path=result_path,
            manifest_path=output_dir / "manifest.json",
        )
        print("Statistical calibration outputs verified.")
        return 0

    audit_report = resolve_audit_report(args.audit_report, args.source_benchmark)
    design = {
        "schema_version": "tcga-trace-statistical-calibration-design-v2",
        "alpha": args.alpha,
        "seed": args.seed,
        "permutation_replicates": args.permutation_replicates,
        "simulation_replicates": args.simulation_replicates,
        "simulation_n": args.simulation_n,
        "workers": args.workers,
        "methods": METHODS,
        "observed_max_tau": 1826.25,
        "simulation_max_tau": 5,
        "audit_report": workspace_path(audit_report),
        "output_json": workspace_path(result_path),
        "permutation_csv": workspace_path(permutation_path),
        "simulation_csv": workspace_path(simulation_path),
    }
    write_json(design_path, design)

    if not args.summarize_only:
        run_calibration(
            service=args.docker_compose_service,
            r_script=args.r_script,
            design_path=design_path,
        )

    result = read_json(result_path)
    validate_result(result, design)
    rows = result_rows(result)
    write_summary_csv(output_dir / "summary.csv", rows)
    write_markdown(output_dir / "summary.md", result, rows)
    write_latex(latex_table, result)
    write_manifest(
        output_dir / "manifest.json",
        files=[
            design_path,
            result_path,
            permutation_path,
            simulation_path,
            output_dir / "summary.csv",
            output_dir / "summary.md",
            latex_table,
        ],
        result=result,
    )

    print(f"Wrote {output_dir / 'summary.md'}")
    print(f"Wrote {latex_table}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Calibrate TCGA-TRACE survival evidence profiles by observed-cohort "
            "expression permutation and known-truth simulation."
        )
    )
    parser.add_argument("--audit-report", type=Path)
    parser.add_argument(
        "--source-benchmark",
        type=Path,
        default=DEFAULT_SOURCE_BENCHMARK,
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--latex-table", type=Path, default=DEFAULT_LATEX_TABLE)
    parser.add_argument("--r-script", type=Path, default=DEFAULT_R_SCRIPT)
    parser.add_argument("--docker-compose-service", default="backend")
    parser.add_argument("--permutation-replicates", type=int, default=2000)
    parser.add_argument("--simulation-replicates", type=int, default=2000)
    parser.add_argument("--simulation-n", type=int, default=300)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--seed", type=int, default=20260725)
    parser.add_argument("--alpha", type=float, default=0.05)
    parser.add_argument(
        "--summarize-only",
        action="store_true",
        help="Regenerate summaries from existing raw calibration outputs.",
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Verify the frozen design, result schema and output checksums without rerunning R.",
    )
    args = parser.parse_args()
    if args.permutation_replicates < 1 or args.simulation_replicates < 1:
        parser.error("Replicate counts must be positive.")
    if args.simulation_n < 50:
        parser.error("--simulation-n must be at least 50.")
    if not 0 < args.alpha < 1:
        parser.error("--alpha must be between zero and one.")
    if args.summarize_only and args.check_only:
        parser.error("--summarize-only and --check-only are mutually exclusive.")
    return args


def resolve_audit_report(
    explicit: Path | None,
    source_benchmark: Path,
) -> Path:
    if explicit is not None:
        audit_report = explicit.resolve()
    else:
        payload = read_json(source_benchmark)
        analysis_id = None
        for item in payload.get("results") or []:
            result = item.get("result") or {}
            if result.get("cutpoint_method") == "median":
                analysis_id = result.get("id")
                break
        if not analysis_id:
            raise RuntimeError(
                f"No median analysis ID was found in {source_benchmark}."
            )
        audit_report = ROOT / "artifacts" / analysis_id / "audit_report.json"
    if not audit_report.exists():
        raise RuntimeError(
            f"Calibration audit report is unavailable: {audit_report}"
        )
    try:
        audit_report.relative_to(ROOT)
    except ValueError as exc:
        raise RuntimeError(
            "The calibration audit report must be inside the repository root "
            "so the Docker benchmark can mount it reproducibly."
        ) from exc
    return audit_report


def run_calibration(
    *,
    service: str,
    r_script: Path,
    design_path: Path,
) -> None:
    command = [
        "docker",
        "compose",
        "run",
        "--rm",
        "--no-deps",
        "-v",
        f"{ROOT}:/workspace",
        "-w",
        "/workspace",
        service,
        "Rscript",
        workspace_path(r_script),
        workspace_path(design_path),
    ]
    subprocess.run(command, cwd=ROOT, check=True)


def validate_result(result: dict[str, Any], design: dict[str, Any]) -> None:
    if result.get("schema_version") != "tcga-trace-statistical-calibration-v2":
        raise RuntimeError("Unexpected statistical calibration schema.")
    result_design = result.get("design") or {}
    expected = {
        "alpha": float(design["alpha"]),
        "seed": int(design["seed"]),
        "permutation_replicates": int(design["permutation_replicates"]),
        "simulation_replicates_per_scenario": int(
            design["simulation_replicates"]
        ),
        "simulation_n": int(design["simulation_n"]),
    }
    for key, value in expected.items():
        if result_design.get(key) != value:
            raise RuntimeError(
                f"Calibration result design mismatch for {key}: "
                f"{result_design.get(key)!r} != {value!r}"
            )
    source = result.get("source") or {}
    if not source.get("audit_reproducibility_hash"):
        raise RuntimeError("Calibration result is not bound to an audit hash.")
    expected_scenarios = {
        "observed_null_permutation",
        "null",
        "linear_ph",
        "delayed_non_ph",
        "u_shaped_nonlinear",
    }
    observed_scenarios = {
        row.get("scenario")
        for row in (result.get("permutation_summary") or [])
        + (result.get("simulation_summary") or [])
    }
    if observed_scenarios != expected_scenarios:
        raise RuntimeError(
            "Calibration scenarios are incomplete: "
            f"{sorted(observed_scenarios)}"
        )


def check_existing_outputs(
    *,
    design_path: Path,
    result_path: Path,
    manifest_path: Path,
) -> None:
    for path in (design_path, result_path, manifest_path):
        if not path.exists():
            raise RuntimeError(f"Missing calibration output: {path}")
    design = read_json(design_path)
    result = read_json(result_path)
    validate_result(result, design)
    manifest = read_json(manifest_path)
    if (
        manifest.get("schema_version")
        != "tcga-trace-statistical-calibration-manifest-v2"
    ):
        raise RuntimeError("Unexpected statistical calibration manifest schema.")
    for item in manifest.get("files") or []:
        path = ROOT / str(item.get("path") or "")
        if not path.is_file():
            raise RuntimeError(f"Missing calibration manifest file: {path}")
        observed_bytes = path.stat().st_size
        if observed_bytes != item.get("bytes"):
            raise RuntimeError(
                f"Calibration file size mismatch for {path}: "
                f"{observed_bytes} != {item.get('bytes')}"
            )
        observed_hash = file_sha256(path)
        if observed_hash != item.get("sha256"):
            raise RuntimeError(
                f"Calibration checksum mismatch for {path}: "
                f"{observed_hash} != {item.get('sha256')}"
            )


def result_rows(result: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for analysis_type, key in (
        ("permutation", "permutation_summary"),
        ("simulation", "simulation_summary"),
    ):
        for item in result.get(key) or []:
            rows.append(
                {
                    "analysis_type": analysis_type,
                    "scenario": item.get("scenario"),
                    "scenario_label": SCENARIO_LABELS.get(
                        str(item.get("scenario")),
                        str(item.get("scenario")),
                    ),
                    "metric": item.get("metric"),
                    "metric_label": METRIC_LABELS.get(
                        str(item.get("metric")),
                        str(item.get("metric")),
                    ),
                    "rejected": item.get("rejected"),
                    "evaluable": item.get("evaluable"),
                    "rate": item.get("rate"),
                    "confidence_low": item.get("confidence_low"),
                    "confidence_high": item.get("confidence_high"),
                }
            )
    return rows


def write_summary_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = [
        "analysis_type",
        "scenario",
        "scenario_label",
        "metric",
        "metric_label",
        "rejected",
        "evaluable",
        "rate",
        "confidence_low",
        "confidence_high",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fields,
            extrasaction="ignore",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def write_markdown(
    path: Path,
    result: dict[str, Any],
    rows: list[dict[str, Any]],
) -> None:
    design = result["design"]
    source = result["source"]
    dependence = result["dependence"]
    selected_metrics = [
        "continuous_linear",
        "spline_nonlinearity",
        "marker_ph",
        "grouped_family_holm",
        "maxstat_naive",
        "maxstat_lau94",
    ]
    lines = [
        "# Statistical Calibration",
        "",
        "This benchmark evaluates the revised evidence profile; it does not "
        "calibrate or reinstate the removed retained/not-retained rule.",
        "",
        "## Design",
        "",
        f"- Alpha: `{format_number(design['alpha'], 3)}`.",
        f"- Seed: `{design['seed']}`.",
        f"- Observed-cohort permutations: `{design['permutation_replicates']}`.",
        "- Known-truth simulations: "
        f"`{design['simulation_replicates_per_scenario']}` per scenario, "
        f"`n={design['simulation_n']}`.",
        "- Grouped family: maxstat, median, upper quartile and outer "
        "quartiles, with Holm adjustment within each replicate.",
        "- Maxstat: Lau94 corrected p-value enters multiplicity; the selected "
        "group log-rank p-value is retained only to quantify selection bias.",
        "- Rejection intervals: Wilson 95% Monte Carlo intervals.",
        "",
        "## Source Cohort",
        "",
        f"- Analysis: `{source['analysis_id']}`.",
        f"- Patients/events: `{source['patients']}/{source['events']}`.",
        f"- Fixed tau: `{format_number(source['tau'], 2)}` days.",
        "- Audit reproducibility hash: "
        f"`{source['audit_reproducibility_hash']}`.",
        "- Continuous records hash: "
        f"`{source['continuous_patient_records_sha256']}`.",
        "",
        "## Rejection Proportions",
        "",
        "| Scenario | Linear Cox | Spline nonlinear | Marker PH | Grouped Holm | "
        "Maxstat naive | Maxstat Lau94 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    by_key = {
        (str(row["scenario"]), str(row["metric"])): row
        for row in rows
    }
    scenario_order = [
        "observed_null_permutation",
        "null",
        "linear_ph",
        "delayed_non_ph",
        "u_shaped_nonlinear",
    ]
    for scenario in scenario_order:
        values = [
            format_rate(by_key.get((scenario, metric)))
            for metric in selected_metrics
        ]
        lines.append(
            f"| {SCENARIO_LABELS[scenario]} | " + " | ".join(values) + " |"
        )
    lines.extend(
        [
            "",
            "Rates are operating characteristics of different estimands. In "
            "particular, the PH column measures diagnostic sensitivity rather "
            "than biomarker association power.",
            "",
            "## Dependence of Grouped Summaries",
            "",
            "Under observed-cohort expression permutation with a median split:",
            "",
            "- Spearman correlation of -log10 p, log-rank versus Cox: "
            f"`{format_number(dependence['spearman_logrank_vs_cox'], 3)}`.",
            "- Spearman correlation of -log10 p, log-rank versus RMST: "
            f"`{format_number(dependence['spearman_logrank_vs_rmst'], 3)}`.",
            "- Spearman correlation of -log10 p, Cox versus RMST: "
            f"`{format_number(dependence['spearman_cox_vs_rmst'], 3)}`.",
            "- All three nominally below alpha: "
            f"`{format_interval(dependence['all_three_nominal'])}`.",
            "",
            "These correlations are why TCGA-TRACE reports log-rank, grouped "
            "Cox and RMST side by side rather than treating them as independent "
            "barriers. Marker-specific PH modifies interpretation and never "
            "removes an RMST or association result.",
            "",
            "## Machine-readable Outputs",
            "",
            "- `calibration_results.raw.json`: design, source hashes, scenario "
            "truth, summaries and software versions.",
            "- `permutation_replicates.csv`: all observed-null replicate metrics.",
            "- `simulation_replicates.csv`: all known-truth replicate metrics.",
            "- `manifest.json`: SHA-256 checksums for the benchmark outputs.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def write_latex(path: Path, result: dict[str, Any]) -> None:
    summaries = (
        result.get("permutation_summary") or []
    ) + (result.get("simulation_summary") or [])
    by_key = {
        (str(row.get("scenario")), str(row.get("metric"))): row
        for row in summaries
    }
    scenario_order = [
        "observed_null_permutation",
        "null",
        "linear_ph",
        "delayed_non_ph",
        "u_shaped_nonlinear",
    ]
    lines = [
        r"\begin{table}[H]",
        r"\centering",
        r"\begingroup",
        r"\setstretch{1.0}",
        r"\scriptsize",
        r"\renewcommand{\arraystretch}{1.05}",
        (
            r"\caption{Permutation and known-truth simulation calibration. "
            r"Entries are rejection percentages at $\alpha=0.05$; Wilson "
            r"intervals and replicate-level results are supplied in the "
            r"machine-readable benchmark. Grouped Holm uses four cutpoint "
            r"methods and the Lau94 maxstat p-value. The naive maxstat column "
            r"uses the post-selection log-rank p-value only to expose bias.}"
        ),
        r"\label{tab:statistical-calibration}",
        r"\begin{tabular}{lrrrrrr}",
        r"\toprule",
        (
            r"Scenario & Linear & Nonlinear & Marker PH & Grouped Holm & "
            r"\multicolumn{2}{c}{Maxstat} \\"
        ),
        r"\cmidrule(lr){6-7}",
        r" & Cox & spline & diagnostic & family & naive & Lau94 \\",
        r"\midrule",
    ]
    latex_labels = {
        "observed_null_permutation": "LIHC permutation",
        "null": "Simulated null",
        "linear_ph": "Linear PH",
        "delayed_non_ph": "Delayed non-PH",
        "u_shaped_nonlinear": "U-shaped nonlinear",
    }
    metric_order = [
        "continuous_linear",
        "spline_nonlinearity",
        "marker_ph",
        "grouped_family_holm",
        "maxstat_naive",
        "maxstat_lau94",
    ]
    for scenario in scenario_order:
        values = [
            percent_value(by_key.get((scenario, metric)))
            for metric in metric_order
        ]
        lines.append(
            latex_labels[scenario]
            + " & "
            + " & ".join(values)
            + r" \\"
        )
    lines.extend(
        [
            r"\bottomrule",
            r"\end{tabular}",
            r"\endgroup",
            r"\end{table}",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def write_manifest(
    path: Path,
    *,
    files: list[Path],
    result: dict[str, Any],
) -> None:
    payload = {
        "schema_version": "tcga-trace-statistical-calibration-manifest-v2",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_analysis_id": (result.get("source") or {}).get("analysis_id"),
        "source_audit_reproducibility_hash": (
            result.get("source") or {}
        ).get("audit_reproducibility_hash"),
        "files": [
            {
                "path": str(file.relative_to(ROOT)),
                "bytes": file.stat().st_size,
                "sha256": file_sha256(file),
            }
            for file in files
        ],
    }
    write_json(path, payload)


def workspace_path(path: Path) -> str:
    return "/workspace/" + path.resolve().relative_to(ROOT).as_posix()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def format_number(value: Any, digits: int) -> str:
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return "NA"


def format_rate(row: dict[str, Any] | None) -> str:
    if not row:
        return "NA"
    return (
        f"{100 * float(row['rate']):.1f}% "
        f"({100 * float(row['confidence_low']):.1f}-"
        f"{100 * float(row['confidence_high']):.1f})"
    )


def format_interval(item: dict[str, Any]) -> str:
    return (
        f"{item['rejected']}/{item['evaluable']} "
        f"({100 * float(item['rate']):.1f}%, "
        f"95% CI {100 * float(item['confidence_low']):.1f}-"
        f"{100 * float(item['confidence_high']):.1f}%)"
    )


def percent_value(row: dict[str, Any] | None) -> str:
    if not row or row.get("rate") is None:
        return "--"
    return f"{100 * float(row['rate']):.1f}"


if __name__ == "__main__":
    raise SystemExit(main())
