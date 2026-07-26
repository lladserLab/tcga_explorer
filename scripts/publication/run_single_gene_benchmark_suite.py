#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import run_cutpoint_benchmark as cutpoint_benchmark


ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "scripts" / "publication" / "run_cutpoint_benchmark.py"
BENCHMARK_ROOT = ROOT / "docs" / "publication" / "benchmark"
TABLE_ROOT = ROOT / "manuscript" / "bioinformatics_app_note" / "tables"
SCENARIO_REGISTRY_PATH = BENCHMARK_ROOT / "scenario_registry_v1.json"
EVIDENCE_ALPHA = 0.05
MAXSTAT_DIAGNOSTIC_STEM = "maxstat_selection_diagnostic"
MAIN_EVIDENCE_TABLE = "main_evidence_matrix.tex"
CUTPOINT_METHODS = [
    ("maxstat", "Max"),
    ("median", "Med"),
    ("upper_quartile", "UQ"),
    ("upper_lower_quartile", "OQ"),
]

PRIMARY_CASE_IDS = [
    "lihc_cdc20_os_cutpoints",
    "luad_birc5_os_cutpoints",
    "uvm_bap1_dss_cutpoints",
    "skcm_tmem176b_os_cutpoints",
    "lgg_emp3_os_cutpoints",
]

CASE_PRESENTATION = {
    "lihc_cdc20_os_cutpoints": {
        "purpose": "Illustrative case",
        "interpretation": "Literature-guided case showing agreement across nonredundant cutpoint rules.",
    },
    "luad_birc5_os_cutpoints": {
        "purpose": "Illustrative case",
        "interpretation": "Literature-guided case showing cutpoint-dependent estimates.",
    },
    "uvm_bap1_dss_cutpoints": {
        "purpose": "Low-event diagnostic",
        "interpretation": "Low-event scenario used to expose model-support and PH limitations.",
    },
    "skcm_tmem176b_os_cutpoints": {
        "purpose": "Exploratory",
        "interpretation": "Exploratory scenario; biological interpretation remains outside the software benchmark.",
    },
    "lgg_emp3_os_cutpoints": {
        "purpose": "PH diagnostic",
        "interpretation": "Diagnostic scenario used to expose proportional-hazards discordance.",
    },
}


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
        "lihc_cdc20_os_cutpoints",
        "TCGA-LIHC",
        "CDC20",
        "OS",
        "TCGA-LIHC CDC20 OS cutpoint benchmark",
        "lihc_cdc20_os_cutpoint_benchmark",
        "lihc_cdc20_os_cutpoint_benchmark.tex",
    ),
    BenchmarkCase(
        "luad_birc5_os_cutpoints",
        "TCGA-LUAD",
        "BIRC5",
        "OS",
        "TCGA-LUAD BIRC5 OS cutpoint benchmark",
        "luad_birc5_os_cutpoint_benchmark",
        "luad_birc5_os_cutpoint_benchmark.tex",
    ),
    BenchmarkCase(
        "uvm_bap1_dss_cutpoints",
        "TCGA-UVM",
        "BAP1",
        "DSS",
        "TCGA-UVM BAP1 DSS cutpoint benchmark",
        "uvm_bap1_dss_cutpoint_benchmark",
        "uvm_bap1_dss_cutpoint_benchmark.tex",
    ),
    BenchmarkCase(
        "lgg_emp3_os_cutpoints",
        "TCGA-LGG",
        "EMP3",
        "OS",
        "TCGA-LGG EMP3 OS cutpoint benchmark",
        "lgg_emp3_os_cutpoint_benchmark",
        "lgg_emp3_os_cutpoint_benchmark.tex",
    ),
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
        "skcm_tmem176b_os_cutpoints",
        "TCGA-SKCM",
        "TMEM176B",
        "OS",
        "TCGA-SKCM TMEM176B OS cutpoint benchmark",
        "skcm_tmem176b_os_cutpoint_benchmark",
        "skcm_tmem176b_os_cutpoint_benchmark.tex",
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
    registry = load_scenario_registry()
    validate_scenario_registry(registry, CASES)
    args.adjustment_covariates = (
        []
        if args.no_clinical_adjustment
        else args.adjustment_covariate or ["age_at_index"]
    )
    selected = [case for case in CASES if not args.only or case.benchmark_id in args.only]
    if not selected:
        raise ValueError(f"No benchmark cases matched --only: {args.only}")

    if not args.render_existing:
        for case in selected:
            run_case(case, args)
        apply_declared_multiplicity(CASES, registry)
    else:
        missing = [str(summary_path(case)) for case in CASES if not summary_path(case).exists()]
        if missing:
            raise FileNotFoundError(
                "Cannot render existing benchmark artifacts; missing: "
                + ", ".join(missing)
            )
        attach_scenario_registry_metadata(CASES, registry)
    rows = [
        summarize_case(case, registry)
        for case in CASES
        if summary_path(case).exists()
    ]
    rows_by_id = {row["benchmark_id"]: row for row in rows}
    primary_rows = [rows_by_id[case_id] for case_id in PRIMARY_CASE_IDS if case_id in rows_by_id]
    rows = primary_rows + [
        row for row in rows if row["benchmark_id"] not in PRIMARY_CASE_IDS
    ]
    write_overview_csv(BENCHMARK_ROOT / "single_gene_benchmark_overview.csv", rows)
    write_overview_markdown(BENCHMARK_ROOT / "single_gene_benchmark_overview.md", rows)
    write_main_overview_latex(TABLE_ROOT / "single_gene_benchmark_overview.tex", primary_rows)
    write_full_overview_latex(TABLE_ROOT / "single_gene_benchmark_full_overview.tex", rows)
    diagnostic_rows = build_maxstat_selection_diagnostic(CASES)
    write_maxstat_diagnostic_csv(
        BENCHMARK_ROOT / f"{MAXSTAT_DIAGNOSTIC_STEM}.csv",
        diagnostic_rows,
    )
    write_maxstat_diagnostic_markdown(
        BENCHMARK_ROOT / f"{MAXSTAT_DIAGNOSTIC_STEM}.md",
        diagnostic_rows,
    )
    write_maxstat_diagnostic_latex(
        TABLE_ROOT / f"{MAXSTAT_DIAGNOSTIC_STEM}.tex",
        diagnostic_rows,
    )
    write_main_evidence_latex(
        TABLE_ROOT / MAIN_EVIDENCE_TABLE,
        rows,
        diagnostic_rows,
    )
    print(f"Wrote {BENCHMARK_ROOT / 'single_gene_benchmark_overview.csv'}")
    print(f"Wrote {TABLE_ROOT / 'single_gene_benchmark_overview.tex'}")
    print(f"Wrote {TABLE_ROOT / 'single_gene_benchmark_full_overview.tex'}")
    print(f"Wrote {BENCHMARK_ROOT / f'{MAXSTAT_DIAGNOSTIC_STEM}.csv'}")
    print(f"Wrote {TABLE_ROOT / MAIN_EVIDENCE_TABLE}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the single-gene publication benchmark suite.")
    parser.add_argument("--api-base-url", default="http://localhost:3000/tcga_explorer")
    parser.add_argument("--max-concurrency", type=int, default=1)
    parser.add_argument("--only", action="append", default=[], help="Benchmark id to run. Can be repeated.")
    parser.add_argument(
        "--adjustment-covariate",
        action="append",
        choices=["age_at_index", "stage", "grade", "gender", "race"],
        help=(
            "Clinical field for the exact complete-case adjusted model. "
            "Can be repeated; the suite default is age_at_index."
        ),
    )
    parser.add_argument(
        "--no-clinical-adjustment",
        action="store_true",
        help="Run without the suite's default age-adjusted model.",
    )
    parser.add_argument(
        "--render-existing",
        action="store_true",
        help=(
            "Regenerate overview and LaTeX artifacts from the frozen summary "
            "CSVs without submitting analyses or changing multiplicity fields."
        ),
    )
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
    for covariate in args.adjustment_covariates:
        command.extend(["--adjustment-covariate", covariate])
    subprocess.run(command, cwd=ROOT, check=True)


def load_scenario_registry(
    path: Path = SCENARIO_REGISTRY_PATH,
) -> dict[str, Any]:
    try:
        registry = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise FileNotFoundError(
            f"Publication scenario registry is required: {path}"
        ) from error
    except json.JSONDecodeError as error:
        raise ValueError(
            f"Publication scenario registry is not valid JSON: {path}: {error}"
        ) from error
    if not isinstance(registry, dict):
        raise ValueError("Publication scenario registry must be a JSON object.")
    return registry


def validate_scenario_registry(
    registry: dict[str, Any],
    cases: list[BenchmarkCase],
) -> None:
    if registry.get("schema_version") != "tcga-trace-publication-scenario-registry-v1":
        raise ValueError("Unsupported or missing publication scenario registry schema.")
    if not str(registry.get("registry_version") or "").strip():
        raise ValueError("Publication scenario registry version is required.")
    scenarios = registry.get("scenarios")
    if not isinstance(scenarios, list) or not scenarios:
        raise ValueError("Publication scenario registry must contain scenarios.")
    scenario_count = (registry.get("scope") or {}).get("scenario_count")
    if scenario_count != len(scenarios):
        raise ValueError(
            "Publication scenario registry scope.scenario_count does not match "
            f"the {len(scenarios)} scenario entries."
        )

    registry_ids = [str(entry.get("benchmark_id") or "") for entry in scenarios]
    if len(set(registry_ids)) != len(registry_ids):
        raise ValueError("Publication scenario registry contains duplicate benchmark IDs.")
    case_ids = [case.benchmark_id for case in cases]
    if registry_ids != case_ids:
        raise ValueError(
            "Publication benchmark cases do not exactly match the frozen "
            f"scenario registry. Registry={registry_ids}; code={case_ids}."
        )

    entries = {entry["benchmark_id"]: entry for entry in scenarios}
    for case in cases:
        entry = entries[case.benchmark_id]
        expected = (case.cohort, case.gene, case.endpoint)
        observed = (
            entry.get("cohort"),
            entry.get("marker"),
            entry.get("endpoint"),
        )
        if observed != expected:
            raise ValueError(
                f"Scenario {case.benchmark_id} differs from the frozen registry: "
                f"registry={observed}; code={expected}."
            )
        endpoint_role = entry.get("endpoint_role")
        if endpoint_role not in {"primary", "sensitivity"}:
            raise ValueError(
                f"Scenario {case.benchmark_id} has invalid endpoint_role "
                f"{endpoint_role!r}."
            )
        parent_id = entry.get("parent_benchmark_id")
        if endpoint_role == "primary" and parent_id is not None:
            raise ValueError(
                f"Primary scenario {case.benchmark_id} cannot have a parent."
            )
        if endpoint_role == "sensitivity":
            parent = entries.get(parent_id)
            if parent is None:
                raise ValueError(
                    f"Sensitivity scenario {case.benchmark_id} has no valid "
                    f"primary parent {parent_id!r}."
                )
            if parent.get("endpoint_role") != "primary":
                raise ValueError(
                    f"Sensitivity parent {parent_id} must be a primary scenario."
                )
            if (
                parent.get("cohort"),
                parent.get("marker"),
            ) != (
                entry.get("cohort"),
                entry.get("marker"),
            ):
                raise ValueError(
                    f"Sensitivity scenario {case.benchmark_id} must share its "
                    "cohort and marker with its primary parent."
                )
        anchors = entry.get("literature_anchors")
        if not isinstance(anchors, list) or not anchors:
            raise ValueError(
                f"Scenario {case.benchmark_id} requires at least one literature anchor."
            )
        if any(
            not str(anchor.get("citation_key") or "").strip()
            or not str(anchor.get("doi") or "").strip()
            for anchor in anchors
        ):
            raise ValueError(
                f"Scenario {case.benchmark_id} has an incomplete literature anchor."
            )

    registered_sensitivities = (
        registry.get("endpoint_policy") or {}
    ).get("registered_endpoint_sensitivities")
    observed_sensitivities = [
        entry["benchmark_id"]
        for entry in scenarios
        if entry.get("endpoint_role") == "sensitivity"
    ]
    if registered_sensitivities != observed_sensitivities:
        raise ValueError(
            "endpoint_policy.registered_endpoint_sensitivities must exactly "
            "match sensitivity scenario entries."
        )


def scenario_registry_sha256(
    path: Path = SCENARIO_REGISTRY_PATH,
) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def scenario_registry_entry(
    registry: dict[str, Any],
    benchmark_id: str,
) -> dict[str, Any]:
    for entry in registry["scenarios"]:
        if entry["benchmark_id"] == benchmark_id:
            return entry
    raise KeyError(f"Scenario {benchmark_id} is absent from the frozen registry.")


def scenario_registry_metadata(
    registry: dict[str, Any],
    entry: dict[str, Any],
    path: Path = SCENARIO_REGISTRY_PATH,
) -> dict[str, Any]:
    try:
        relative_path = path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        relative_path = path.resolve().as_posix()
    return {
        "schema_version": registry["schema_version"],
        "registry_version": registry["registry_version"],
        "registry_sha256": scenario_registry_sha256(path),
        "registry_path": relative_path,
        "status": registry.get("status"),
        "selection_history": registry.get("selection_history"),
        "endpoint_policy": registry.get("endpoint_policy"),
        "scenario": entry,
    }


def attach_scenario_registry_metadata(
    cases: list[BenchmarkCase],
    registry: dict[str, Any],
    path: Path = SCENARIO_REGISTRY_PATH,
) -> None:
    validate_scenario_registry(registry, cases)
    for case in cases:
        metadata_path = BENCHMARK_ROOT / case.output_name / "benchmark_metadata.json"
        if not metadata_path.exists():
            raise FileNotFoundError(
                f"Cannot attach scenario registry; missing {metadata_path}."
            )
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        metadata["scenario_registry"] = scenario_registry_metadata(
            registry,
            scenario_registry_entry(registry, case.benchmark_id),
            path,
        )
        cutpoint_benchmark.write_json(metadata_path, metadata)


def apply_declared_multiplicity(
    cases: list[BenchmarkCase],
    registry: dict[str, Any],
) -> None:
    validate_scenario_registry(registry, cases)
    rows_by_case: dict[str, list[dict[str, Any]]] = {}
    combined_rows: list[dict[str, Any]] = []
    for case in cases:
        path = summary_path(case)
        if not path.exists():
            continue
        rows = read_csv(path)
        for row in rows:
            row["benchmark_id"] = case.benchmark_id
        cutpoint_benchmark.assign_grouped_family_p_values(rows)
        cutpoint_benchmark.apply_holm(
            rows,
            "grouped_family_p_value",
            "grouped_holm_p_value",
        )
        for row in rows:
            cutpoint_benchmark.set_legacy_grouped_multiplicity_aliases(row)
        rows_by_case[case.benchmark_id] = rows
        combined_rows.extend(rows)

    continuous_representatives = [
        next(
            (
                row
                for row in rows
                if row.get("method") == "median"
            ),
            rows[0],
        )
        for rows in rows_by_case.values()
        if rows
    ]
    cutpoint_benchmark.apply_bh(
        continuous_representatives,
        "continuous_univariable_p_value",
        "continuous_bh_p_value",
    )
    cutpoint_benchmark.apply_bh(
        continuous_representatives,
        "spline_nonlinearity_p_value",
        "spline_nonlinearity_bh_p_value",
    )
    continuous_q_by_case = {
        row["benchmark_id"]: row.get("continuous_bh_p_value")
        for row in continuous_representatives
    }
    nonlinearity_q_by_case = {
        row["benchmark_id"]: row.get("spline_nonlinearity_bh_p_value")
        for row in continuous_representatives
    }
    for row in combined_rows:
        row["continuous_bh_p_value"] = continuous_q_by_case.get(
            row["benchmark_id"]
        )
        row["spline_nonlinearity_bh_p_value"] = nonlinearity_q_by_case.get(
            row["benchmark_id"]
        )
        cutpoint_benchmark.annotate_evidence_profile(row)
        row["multiplicity_scope"] = (
            "within_scenario_holm_grouped;"
            "across_scenarios_bh_continuous"
        )

    for case in cases:
        rows = rows_by_case.get(case.benchmark_id)
        if rows is None:
            continue
        metadata_path = BENCHMARK_ROOT / case.output_name / "benchmark_metadata.json"
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        metadata["multiple_testing"] = {
            "grouped_method": "Holm",
            "grouped_family": (
                "four prespecified two-group cutpoint sensitivities within "
                "this marker-endpoint scenario"
            ),
            "grouped_scope": "within_scenario",
            "grouped_tests": len(
                [
                    row for row in rows
                    if cutpoint_benchmark.is_finite_number(
                        row.get("grouped_family_p_value")
                    )
                ]
            ),
            "maxstat_input": (
                "Lau94 selection-adjusted rank-statistic p-value; naive "
                "post-selection log-rank p is descriptive only"
            ),
            "continuous_linear_family": (
                "one continuous univariable Cox test per completed "
                "single-gene benchmark scenario"
            ),
            "continuous_linear_method": "Benjamini-Hochberg",
            "continuous_linear_scope": "across_prespecified_scenarios",
            "continuous_linear_tests": len(
                [
                    row
                    for row in continuous_representatives
                    if cutpoint_benchmark.is_finite_number(
                        row.get("continuous_univariable_p_value")
                    )
                ]
            ),
            "continuous_nonlinearity_family": (
                "one spline-versus-linear likelihood-ratio test per "
                "completed single-gene benchmark scenario"
            ),
            "continuous_nonlinearity_method": "Benjamini-Hochberg",
            "continuous_nonlinearity_scope": "across_prespecified_scenarios",
            "continuous_nonlinearity_tests": len(
                [
                    row
                    for row in continuous_representatives
                    if cutpoint_benchmark.is_finite_number(
                        row.get("spline_nonlinearity_p_value")
                    )
                ]
            ),
            "legacy_aliases": {
                "bh_logrank_p_value": "grouped_holm_p_value",
                "bh_within_scenario_logrank_p_value": (
                    "grouped_holm_p_value"
                ),
            },
        }
        metadata["scenario_registry"] = scenario_registry_metadata(
            registry,
            scenario_registry_entry(registry, case.benchmark_id),
        )
        cutpoint_benchmark.write_json(metadata_path, metadata)
        cutpoint_benchmark.write_csv(summary_path(case), rows)
        cutpoint_benchmark.write_markdown(
            BENCHMARK_ROOT / case.output_name / "summary.md",
            metadata,
            rows,
        )
        cutpoint_benchmark.write_latex_table(
            TABLE_ROOT / case.table_name,
            metadata,
            rows,
        )


def summarize_case(
    case: BenchmarkCase,
    registry: dict[str, Any],
) -> dict[str, Any]:
    rows = read_csv(summary_path(case))
    entry = scenario_registry_entry(registry, case.benchmark_id)
    anchors = entry["literature_anchors"]
    completed = [row for row in rows if row.get("status") == "completed"]
    median = next((row for row in completed if row.get("method") == "median"), {})
    nominal = [row for row in completed if is_significant(row.get("logrank_p_value"))]
    grouped_holm = [
        row
        for row in completed
        if is_significant(row.get("grouped_holm_p_value"))
    ]
    adjusted = [row for row in completed if is_significant(row.get("adjusted_p_value"))]
    rmst = [row for row in completed if is_significant(row.get("rmst_p_value"))]
    marker_ph_flagged = [
        row
        for row in completed
        if is_number(row.get("adjusted_ph_p_value"))
        and float(row["adjusted_ph_p_value"]) < EVIDENCE_ALPHA
    ]
    global_ph_flagged = [
        row
        for row in completed
        if is_number(row.get("adjusted_ph_global_p_value"))
        and float(row["adjusted_ph_global_p_value"]) < EVIDENCE_ALPHA
    ]
    low_information = [
        row
        for row in completed
        if row.get("univariable_information_status") in {"caution", "severe"}
        or row.get("adjusted_information_status") in {"caution", "severe"}
    ]
    firth_completed = [
        row
        for row in completed
        if row.get("univariable_firth_status") == "completed"
        or row.get("adjusted_firth_status") == "completed"
    ]
    return {
        "benchmark_id": case.benchmark_id,
        "purpose": CASE_PRESENTATION.get(case.benchmark_id, {}).get("purpose", "Supplementary"),
        "interpretation": CASE_PRESENTATION.get(case.benchmark_id, {}).get(
            "interpretation", "Complete result preserved in the supplementary diagnostic panel."
        ),
        "cohort": case.cohort,
        "gene": case.gene,
        "endpoint": case.endpoint,
        "registry_version": registry["registry_version"],
        "registry_sha256": scenario_registry_sha256(),
        "endpoint_role": entry["endpoint_role"],
        "parent_benchmark_id": entry.get("parent_benchmark_id"),
        "benchmark_role": entry["benchmark_role"],
        "inclusion_rationale": entry["inclusion_rationale"],
        "endpoint_rationale": entry["endpoint_rationale"],
        "literature_citation_keys": ";".join(
            anchor["citation_key"] for anchor in anchors
        ),
        "literature_dois": ";".join(anchor["doi"] for anchor in anchors),
        "adjustment_status": median.get("adjustment_status"),
        "adjustment_covariates": median.get("adjustment_covariates"),
        "adjustment_label": median.get("adjustment_label"),
        "n_patients": median.get("n_patients"),
        "n_events": median.get("n_events"),
        "continuous_n_patients": median.get("continuous_n_patients"),
        "continuous_n_events": median.get("continuous_n_events"),
        "continuous_univariable_hr": median.get("continuous_univariable_hr"),
        "continuous_univariable_hr_conf_low": median.get(
            "continuous_univariable_hr_conf_low"
        ),
        "continuous_univariable_hr_conf_high": median.get(
            "continuous_univariable_hr_conf_high"
        ),
        "continuous_univariable_p": median.get("continuous_univariable_p_value"),
        "continuous_bh_p": median.get("continuous_bh_p_value"),
        "continuous_adjusted_model": median.get("continuous_adjusted_model"),
        "continuous_adjusted_hr": median.get("continuous_adjusted_hr"),
        "continuous_adjusted_hr_conf_low": median.get(
            "continuous_adjusted_hr_conf_low"
        ),
        "continuous_adjusted_hr_conf_high": median.get(
            "continuous_adjusted_hr_conf_high"
        ),
        "continuous_adjusted_p": median.get("continuous_adjusted_p_value"),
        "continuous_marker_ph_p": median.get("continuous_adjusted_ph_p_value"),
        "continuous_global_ph_p": median.get(
            "continuous_adjusted_ph_global_p_value"
        ),
        "continuous_adjusted_parameter_count": median.get(
            "continuous_adjusted_parameter_count"
        ),
        "continuous_adjusted_events_per_parameter": median.get(
            "continuous_adjusted_events_per_parameter"
        ),
        "continuous_adjusted_information_status": median.get(
            "continuous_adjusted_information_status"
        ),
        "continuous_adjusted_firth_status": median.get(
            "continuous_adjusted_firth_status"
        ),
        "continuous_adjusted_firth_hr": median.get(
            "continuous_adjusted_firth_hr"
        ),
        "continuous_adjusted_firth_hr_conf_low": median.get(
            "continuous_adjusted_firth_hr_conf_low"
        ),
        "continuous_adjusted_firth_hr_conf_high": median.get(
            "continuous_adjusted_firth_hr_conf_high"
        ),
        "continuous_adjusted_firth_p": median.get(
            "continuous_adjusted_firth_p_value"
        ),
        "spline_status": median.get("spline_status"),
        "spline_overall_p": median.get("spline_overall_p_value"),
        "spline_nonlinearity_p": median.get("spline_nonlinearity_p_value"),
        "spline_nonlinearity_bh_p": median.get(
            "spline_nonlinearity_bh_p_value"
        ),
        "methods_completed": len(completed),
        "nominal_logrank_methods": len(nominal),
        "grouped_holm_methods": len(grouped_holm),
        "all_grouped_methods_supported": (
            len(completed) == 4 and len(grouped_holm) == 4
        ),
        "any_grouped_method_supported": bool(grouped_holm),
        "grouped_support_profile": (
            "all four"
            if len(completed) == 4 and len(grouped_holm) == 4
            else "none"
            if not grouped_holm
            else f"partial ({len(grouped_holm)}/{len(completed)})"
        ),
        # Deprecated export alias retained for old notebooks.
        "bh_methods": len(grouped_holm),
        "adjusted_methods": len(adjusted),
        "rmst_methods": len(rmst),
        "marker_ph_flagged_methods": len(marker_ph_flagged),
        "global_ph_flagged_methods": len(global_ph_flagged),
        "low_information_methods": len(low_information),
        "firth_methods": len(firth_completed),
        "best_grouped_holm_p": min_number(
            row.get("grouped_holm_p_value") for row in completed
        ),
        "best_bh_logrank_p": min_number(
            row.get("grouped_holm_p_value") for row in completed
        ),
        "best_adjusted_p": min_number(row.get("adjusted_p_value") for row in completed),
        "best_rmst_p": min_number(row.get("rmst_p_value") for row in completed),
        "median_adjusted_model": median.get("adjusted_model"),
        "median_adjusted_hr": median.get("adjusted_hr"),
        "median_adjusted_hr_conf_low": median.get("adjusted_hr_conf_low"),
        "median_adjusted_hr_conf_high": median.get("adjusted_hr_conf_high"),
        "median_adjusted_p": median.get("adjusted_p_value"),
        "median_marker_ph_p": median.get("adjusted_ph_p_value"),
        "median_global_ph_p": median.get("adjusted_ph_global_p_value"),
        "median_rmst_tau_days": median.get("rmst_tau_days"),
        "median_rmst_delta_days": median.get("rmst_delta_days"),
        "median_rmst_p": median.get("rmst_p_value"),
        "profile": (
            f"within-scenario Holm p <= {EVIDENCE_ALPHA:g} in "
            f"{len(grouped_holm)}/{len(completed)}; "
            f"marker PH caution in {len(marker_ph_flagged)}/{len(completed)}"
        ),
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
        "purpose",
        "interpretation",
        "cohort",
        "gene",
        "endpoint",
        "registry_version",
        "registry_sha256",
        "endpoint_role",
        "parent_benchmark_id",
        "benchmark_role",
        "inclusion_rationale",
        "endpoint_rationale",
        "literature_citation_keys",
        "literature_dois",
        "adjustment_status",
        "adjustment_covariates",
        "adjustment_label",
        "n_patients",
        "n_events",
        "continuous_n_patients",
        "continuous_n_events",
        "continuous_univariable_hr",
        "continuous_univariable_hr_conf_low",
        "continuous_univariable_hr_conf_high",
        "continuous_univariable_p",
        "continuous_bh_p",
        "continuous_adjusted_model",
        "continuous_adjusted_hr",
        "continuous_adjusted_hr_conf_low",
        "continuous_adjusted_hr_conf_high",
        "continuous_adjusted_p",
        "continuous_marker_ph_p",
        "continuous_global_ph_p",
        "continuous_adjusted_parameter_count",
        "continuous_adjusted_events_per_parameter",
        "continuous_adjusted_information_status",
        "continuous_adjusted_firth_status",
        "continuous_adjusted_firth_hr",
        "continuous_adjusted_firth_hr_conf_low",
        "continuous_adjusted_firth_hr_conf_high",
        "continuous_adjusted_firth_p",
        "spline_status",
        "spline_overall_p",
        "spline_nonlinearity_p",
        "spline_nonlinearity_bh_p",
        "methods_completed",
        "nominal_logrank_methods",
        "grouped_holm_methods",
        "all_grouped_methods_supported",
        "any_grouped_method_supported",
        "grouped_support_profile",
        "bh_methods",
        "adjusted_methods",
        "rmst_methods",
        "marker_ph_flagged_methods",
        "global_ph_flagged_methods",
        "low_information_methods",
        "firth_methods",
        "best_grouped_holm_p",
        "best_bh_logrank_p",
        "best_adjusted_p",
        "best_rmst_p",
        "median_adjusted_model",
        "median_adjusted_hr",
        "median_adjusted_hr_conf_low",
        "median_adjusted_hr_conf_high",
        "median_adjusted_p",
        "median_marker_ph_p",
        "median_global_ph_p",
        "median_rmst_tau_days",
        "median_rmst_delta_days",
        "median_rmst_p",
        "profile",
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
        (
            "The 11 marker-endpoint scenarios are frozen by "
            "`docs/publication/benchmark/scenario_registry_v1.json`. The panel "
            "was assembled after exploratory triage and is a software stress "
            "test, not a prospectively selected biomarker-validation sample."
        ),
        (
            "OS is primary except for the registered UVM BAP1 DSS case. BRCA "
            "MKI67 PFI and LUAD CD274 PFI are endpoint sensitivities and cannot "
            "supersede their OS parent because of observed results."
        ),
        (
            "The main manuscript emphasizes five literature-anchored scenarios. "
            "All rows, including unsupported and endpoint-sensitivity cases, "
            "remain visible."
        ),
        "The selected adjusted estimate in this frozen suite is the exact prespecified age-adjusted complete-case model; fixed stage/grade models remain auxiliary sensitivities in each raw result.",
        "",
        "| Purpose | Cohort | Gene | Endpoint | Endpoint role | Continuous n/events | HR per SD | Linear q | Nonlinearity q | Cutpoints | Grouped Holm p<=.05 | Primary grouped profile | Age-adjusted p<=.05 | RMST p<=.05 | Marker PH | Low information | Firth | Profile |",
        "| --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in rows:
        lines.append(
            "| {purpose} | {cohort} | {gene} | {endpoint} | {endpoint_role} | {continuous_n_events} | {continuous_hr} | {continuous_p} | {nonlinearity_p} | {completed} | {holm} | {grouped_profile} | {adjusted} | {rmst} | {marker_ph} | {low_information} | {firth} | {profile} |".format(
                purpose=row["purpose"],
                cohort=row["cohort"],
                gene=row["gene"],
                endpoint=row["endpoint"],
                endpoint_role=row["endpoint_role"],
                continuous_n_events=f"{row['continuous_n_patients']}/{row['continuous_n_events']}",
                continuous_hr=format_effect(row["continuous_univariable_hr"]),
                continuous_p=format_p(row["continuous_bh_p"]),
                nonlinearity_p=format_p(row["spline_nonlinearity_bh_p"]),
                completed=row["methods_completed"],
                holm=row["grouped_holm_methods"],
                grouped_profile=row["grouped_support_profile"],
                adjusted=row["adjusted_methods"],
                rmst=row["rmst_methods"],
                marker_ph=row["marker_ph_flagged_methods"],
                low_information=row["low_information_methods"],
                firth=row["firth_methods"],
                profile=row["profile"],
            )
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_main_overview_latex(path: Path, rows: list[dict[str, Any]]) -> None:
    lines = [
        "\\begin{table}[t]",
        "\\centering",
        "\\begingroup",
        "\\footnotesize",
        "\\setlength{\\tabcolsep}{3pt}",
        "\\renewcommand{\\arraystretch}{1.08}",
        "\\newcolumntype{Y}{>{\\raggedright\\arraybackslash}X}",
        "\\newcolumntype{P}[1]{>{\\raggedright\\arraybackslash}p{#1}}",
        "\\caption{Literature-anchored single-gene software stress tests spanning concordant, cutpoint-dependent and proportional-hazards-discordant outputs. The cutpoint-independent continuous Cox estimate is primary. Grouped sensitivity reports the number of four prespecified rules supported after within-scenario Holm adjustment, with support across all four as the primary grouped summary. Age-adjusted Cox, RMST and marker-specific PH are reported separately and are not combined into a decision rule.}",
        "\\label{tab:single-gene-benchmark-overview}",
        "\\begin{tabularx}{\\linewidth}{P{1.55cm}P{1.65cm}P{1.3cm}YP{1.55cm}Y}",
        "\\toprule",
        "Purpose & Cohort--gene & Endpoint, n/events & Continuous primary result & Cutpoint sensitivity & Diagnostic reading \\\\",
        "\\midrule",
    ]
    for row in rows:
        lines.append(
            " & ".join(
                [
                    latex_escape(str(row["purpose"])),
                    latex_escape(f"{row['cohort'].replace('TCGA-', '')}--{row['gene']}"),
                    latex_escape(
                        f"{row['endpoint']}, {row['continuous_n_patients']}/"
                        f"{row['continuous_n_events']}"
                    ),
                    latex_escape(continuous_result(row)),
                    latex_escape(
                        f"{row['grouped_holm_methods']}/"
                        f"{row['adjusted_methods']}/"
                        f"{row['rmst_methods']}/{row['marker_ph_flagged_methods']}"
                    ),
                    latex_escape(str(row["interpretation"])),
                ]
            )
            + " \\\\"
        )
    lines.extend(["\\bottomrule", "\\end{tabularx}", "\\endgroup", "\\end{table}", ""])
    path.write_text("\n".join(lines), encoding="utf-8")


def write_full_overview_latex(path: Path, rows: list[dict[str, Any]]) -> None:
    lines = [
        "\\begin{table}[H]",
        "\\centering",
        "\\scriptsize",
        "\\caption{Complete registered single-gene cutpoint-sensitivity panel. P denotes a primary endpoint and S a linked endpoint sensitivity. Holm counts the four prespecified grouped rules supported after within-scenario adjustment; support across all four is the primary grouped summary. Age-adj. and RMST count nominal p-values at or below 0.05. Marker PH and Global PH count diagnostics below 0.05 for the biomarker term and complete age-adjusted model, respectively. Low-info counts methods whose grouped univariable or selected adjusted Cox fit was below 10 events per parameter; Firth counts methods with at least one completed grouped penalized sensitivity. These correlated summaries are not combined into a decision rule.}",
        "\\label{tab:single-gene-benchmark-full-overview}",
        "\\begin{tabular}{llllrrrrrrr}",
        "\\toprule",
        "Cohort & Gene & Endpoint & Role & Holm & Age-adj. & RMST & Marker PH & Global PH & Low-info & Firth \\\\",
        "\\midrule",
    ]
    for row in rows:
        lines.append(
            " & ".join(
                [
                    row["cohort"].replace("TCGA-", ""),
                    row["gene"],
                    row["endpoint"],
                    "P" if row["endpoint_role"] == "primary" else "S",
                    str(row["grouped_holm_methods"]),
                    str(row["adjusted_methods"]),
                    str(row["rmst_methods"]),
                    str(row["marker_ph_flagged_methods"]),
                    str(row["global_ph_flagged_methods"]),
                    str(row["low_information_methods"]),
                    str(row["firth_methods"]),
                ]
            )
            + " \\\\"
        )
    lines.extend(["\\bottomrule", "\\end{tabular}", "\\end{table}", ""])
    path.write_text("\n".join(lines), encoding="utf-8")


def build_maxstat_selection_diagnostic(
    cases: list[BenchmarkCase],
) -> list[dict[str, Any]]:
    diagnostic_rows: list[dict[str, Any]] = []
    for case in cases:
        path = summary_path(case)
        if not path.exists():
            continue
        methods = {
            row.get("method"): row
            for row in read_csv(path)
            if row.get("status") == "completed"
        }
        median = methods.get("median") or {}
        maxstat = methods.get("maxstat") or {}
        median_grouped_hr = numeric(median.get("grouped_same_contrast_hr"))
        maxstat_grouped_hr = numeric(maxstat.get("grouped_same_contrast_hr"))
        median_log_hr = safe_abs_log(median_grouped_hr)
        maxstat_log_hr = safe_abs_log(maxstat_grouped_hr)
        median_amplification = numeric(
            median.get("same_contrast_log_hr_amplification_ratio")
        )
        maxstat_amplification = numeric(
            maxstat.get("same_contrast_log_hr_amplification_ratio")
        )
        diagnostic_rows.append(
            {
                "benchmark_id": case.benchmark_id,
                "cohort": case.cohort,
                "gene": case.gene,
                "endpoint": case.endpoint,
                "continuous_hr_per_sd": numeric(
                    median.get("continuous_univariable_hr")
                ),
                "continuous_bh_q": numeric(
                    median.get("continuous_bh_p_value")
                ),
                "median_delta_sd": numeric(
                    median.get("same_contrast_delta_sd")
                ),
                "median_continuous_implied_hr": numeric(
                    median.get("continuous_implied_same_contrast_hr")
                ),
                "median_grouped_hr": median_grouped_hr,
                "median_log_hr_amplification_ratio": median_amplification,
                "median_direction_concordant": boolean_value(
                    median.get("same_contrast_direction_concordant")
                ),
                "median_holm_p": numeric(
                    median.get("grouped_holm_p_value")
                ),
                "maxstat_delta_sd": numeric(
                    maxstat.get("same_contrast_delta_sd")
                ),
                "maxstat_continuous_implied_hr": numeric(
                    maxstat.get("continuous_implied_same_contrast_hr")
                ),
                "maxstat_grouped_hr": maxstat_grouped_hr,
                "maxstat_log_hr_amplification_ratio": maxstat_amplification,
                "maxstat_direction_concordant": boolean_value(
                    maxstat.get("same_contrast_direction_concordant")
                ),
                "maxstat_lau94_p": numeric(
                    maxstat.get("maxstat_corrected_p_value")
                ),
                "maxstat_lau94_raw_p": numeric(
                    maxstat.get("maxstat_corrected_p_raw_value")
                ),
                "maxstat_lau94_clamped": boolean_value(
                    maxstat.get("maxstat_corrected_p_clamped")
                ),
                "maxstat_holm_p": numeric(
                    maxstat.get("grouped_holm_p_value")
                ),
                "maxstat_to_median_abs_log_hr_ratio": (
                    maxstat_log_hr / median_log_hr
                    if maxstat_log_hr is not None
                    and median_log_hr is not None
                    and median_log_hr > 0
                    else None
                ),
                "maxstat_minus_median_abs_log_hr": (
                    maxstat_log_hr - median_log_hr
                    if maxstat_log_hr is not None and median_log_hr is not None
                    else None
                ),
                "maxstat_minus_median_amplification": (
                    maxstat_amplification - median_amplification
                    if maxstat_amplification is not None
                    and median_amplification is not None
                    else None
                ),
                "status": (
                    "completed"
                    if median.get("same_contrast_status") == "completed"
                    and maxstat.get("same_contrast_status") == "completed"
                    else "incomplete"
                ),
            }
        )
    return diagnostic_rows


def write_maxstat_diagnostic_csv(
    path: Path,
    rows: list[dict[str, Any]],
) -> None:
    fields = [
        "benchmark_id",
        "cohort",
        "gene",
        "endpoint",
        "continuous_hr_per_sd",
        "continuous_bh_q",
        "median_delta_sd",
        "median_continuous_implied_hr",
        "median_grouped_hr",
        "median_log_hr_amplification_ratio",
        "median_direction_concordant",
        "median_holm_p",
        "maxstat_delta_sd",
        "maxstat_continuous_implied_hr",
        "maxstat_grouped_hr",
        "maxstat_log_hr_amplification_ratio",
        "maxstat_direction_concordant",
        "maxstat_lau94_p",
        "maxstat_lau94_raw_p",
        "maxstat_lau94_clamped",
        "maxstat_holm_p",
        "maxstat_to_median_abs_log_hr_ratio",
        "maxstat_minus_median_abs_log_hr",
        "maxstat_minus_median_amplification",
        "status",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def write_maxstat_diagnostic_markdown(
    path: Path,
    rows: list[dict[str, Any]],
) -> None:
    lines = [
        "# Maxstat Selection Diagnostic",
        "",
        (
            "For each scenario, the continuous Cox coefficient is projected "
            "onto the observed expression-mean difference between the two "
            "groups. This places the continuous-implied and grouped HRs on "
            "the same contrast before comparing their absolute log-HR."
        ),
        (
            "The ratio is descriptive evidence of contrast amplification, "
            "not a selection-corrected confidence interval for the maxstat HR."
        ),
        (
            "Lau94 approximations are bounded to [0,1] for inference; the "
            "machine-readable table preserves the raw approximation and a "
            "clamping flag."
        ),
        "",
        "| Cohort | Gene | Endpoint | Continuous HR/SD | Median: delta SD | Median implied/grouped HR | Median amplification | Maxstat: delta SD | Maxstat implied/grouped HR | Maxstat amplification | Maxstat/median | Lau94 p | Holm p |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in rows:
        lines.append(
            "| {cohort} | {gene} | {endpoint} | {continuous} | {median_delta} | {median_hrs} | {median_amp} | {maxstat_delta} | {maxstat_hrs} | {maxstat_amp} | {ratio} | {lau94} | {holm} |".format(
                cohort=row["cohort"],
                gene=row["gene"],
                endpoint=row["endpoint"],
                continuous=format_effect(row["continuous_hr_per_sd"]),
                median_delta=format_effect(row["median_delta_sd"]),
                median_hrs=format_hr_pair(
                    row["median_continuous_implied_hr"],
                    row["median_grouped_hr"],
                ),
                median_amp=format_effect(
                    row["median_log_hr_amplification_ratio"]
                ),
                maxstat_delta=format_effect(row["maxstat_delta_sd"]),
                maxstat_hrs=format_hr_pair(
                    row["maxstat_continuous_implied_hr"],
                    row["maxstat_grouped_hr"],
                ),
                maxstat_amp=format_effect(
                    row["maxstat_log_hr_amplification_ratio"]
                ),
                ratio=format_effect(
                    row["maxstat_to_median_abs_log_hr_ratio"]
                ),
                lau94=format_p(row["maxstat_lau94_p"]),
                holm=format_p(row["maxstat_holm_p"]),
            )
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_maxstat_diagnostic_latex(
    path: Path,
    rows: list[dict[str, Any]],
) -> None:
    lines = [
        "\\begin{table}[H]",
        "\\centering",
        "\\scriptsize",
        "\\caption{Descriptive maxstat selection diagnostic after placing grouped and continuous Cox estimates on the same observed group-mean contrast. Amplification is the ratio of absolute grouped to continuous-implied log-HR and is not a selection-corrected interval.}",
        "\\label{tab:maxstat-selection-diagnostic}",
        "\\begin{tabular}{lllrrrrr}",
        "\\toprule",
        "Cohort & Gene & Endpoint & Continuous HR/SD & Median amp. & Maxstat amp. & Max./median & Lau94 $p$ \\\\",
        "\\midrule",
    ]
    for row in rows:
        lines.append(
            " & ".join(
                [
                    row["cohort"].replace("TCGA-", ""),
                    row["gene"],
                    row["endpoint"],
                    format_effect(row["continuous_hr_per_sd"]),
                    format_effect(row["median_log_hr_amplification_ratio"]),
                    format_effect(row["maxstat_log_hr_amplification_ratio"]),
                    format_effect(row["maxstat_to_median_abs_log_hr_ratio"]),
                    format_p(row["maxstat_lau94_p"]),
                ]
            )
            + " \\\\"
        )
    lines.extend(["\\bottomrule", "\\end{tabular}", "\\end{table}", ""])
    path.write_text("\n".join(lines), encoding="utf-8")


def write_main_evidence_latex(
    path: Path,
    overview_rows: list[dict[str, Any]],
    diagnostic_rows: list[dict[str, Any]],
) -> None:
    diagnostics_by_id = {
        str(row["benchmark_id"]): row for row in diagnostic_rows
    }
    lines = [
        "\\begin{table*}[t]",
        "\\centering",
        "\\begingroup",
        "\\scriptsize",
        "\\setlength{\\tabcolsep}{2.2pt}",
        "\\renewcommand{\\arraystretch}{0.94}",
        "\\caption{Continuous primary estimates and four grouped sensitivities "
        "across the 11 prespecified marker--endpoint scenarios. HR/SD is the "
        "linear Cox estimate with its across-scenario BH $q$ in brackets; "
        "$q_{\\mathrm{NL}}$ tests spline nonlinearity. Grouped cells show "
        "harmful (H) or protective (P) direction and within-scenario Holm "
        "$p$; bold denotes $p\\leq0.05$, and F denotes a Firth direction when "
        "the standard estimate was non-finite. Amp. is the descriptive ratio "
        "$|\\log(\\mathrm{HR})|_{\\mathrm{maxstat}}/"
        "|\\log(\\mathrm{HR})|_{\\mathrm{median}}$; it is not a "
        "selection-corrected interval.}",
        "\\label{tab:main-evidence-matrix}",
        "\\resizebox{\\textwidth}{!}{%",
        "\\begin{tabular}{lrrrccccrl}",
        "\\toprule",
        "Scenario & $n/e$ & \\shortstack{HR/SD\\\\BH $q$} & "
        "$q_{\\mathrm{NL}}$ & Max & Med & UQ & OQ & Amp. & Diagnostics \\\\",
        "\\midrule",
    ]
    for overview in overview_rows:
        benchmark_id = str(overview["benchmark_id"])
        case = next(
            case for case in CASES if case.benchmark_id == benchmark_id
        )
        method_rows = {
            str(row.get("method")): row
            for row in read_csv(summary_path(case))
            if row.get("status") == "completed"
        }
        cutpoint_cells = [
            format_cutpoint_evidence_cell(method_rows.get(method, {}))
            for method, _ in CUTPOINT_METHODS
        ]
        diagnostic = diagnostics_by_id.get(benchmark_id, {})
        scenario = (
            f"{case.cohort.replace('TCGA-', '')} "
            f"{case.gene} ({case.endpoint})"
        )
        continuous = (
            f"{format_effect(overview.get('continuous_univariable_hr'))}"
            f" [{format_matrix_p(overview.get('continuous_bh_p'))}]"
        )
        amplification = format_amplification(
            diagnostic.get("maxstat_to_median_abs_log_hr_ratio")
        )
        lines.append(
            " & ".join(
                [
                    latex_escape(scenario),
                    (
                        f"{overview.get('continuous_n_patients', 'NA')}/"
                        f"{overview.get('continuous_n_events', 'NA')}"
                    ),
                    continuous,
                    format_matrix_p(overview.get("spline_nonlinearity_bh_p")),
                    *cutpoint_cells,
                    amplification,
                    format_evidence_diagnostics(overview, method_rows),
                ]
            )
            + " \\\\"
        )
    lines.extend(
        [
            "\\bottomrule",
            "\\end{tabular}",
            "}%",
            "\\endgroup",
            "\\end{table*}",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def format_cutpoint_evidence_cell(row: dict[str, Any]) -> str:
    grouped_hr = numeric(row.get("univariable_hr"))
    firth_direction = False
    if grouped_hr is None:
        grouped_hr = numeric(row.get("univariable_firth_hr"))
        firth_direction = grouped_hr is not None
    if grouped_hr is None:
        direction = "NA"
    elif grouped_hr > 1:
        direction = "H"
    elif grouped_hr < 1:
        direction = "P"
    else:
        direction = "N"
    firth_marker = "\\textsuperscript{F}" if firth_direction else ""
    p_value = numeric(row.get("grouped_holm_p_value"))
    cell = f"{direction}{firth_marker} {format_matrix_p(p_value)}"
    return f"\\textbf{{{cell}}}" if is_significant(p_value) else cell


def format_evidence_diagnostics(
    overview: dict[str, Any],
    method_rows: dict[str, dict[str, Any]],
) -> str:
    notes: list[str] = []
    if is_significant(overview.get("spline_nonlinearity_bh_p")):
        notes.append("NL")
    marker_ph = int(overview.get("marker_ph_flagged_methods") or 0)
    global_ph = int(overview.get("global_ph_flagged_methods") or 0)
    low_information = int(overview.get("low_information_methods") or 0)
    firth = int(overview.get("firth_methods") or 0)
    if marker_ph:
        notes.append(f"mPH {marker_ph}")
    if global_ph:
        notes.append(f"gPH {global_ph}")
    if low_information:
        notes.append(f"low {low_information}")
    if firth:
        notes.append(f"Firth {firth}")

    directions = {
        direction
        for direction in (
            cutpoint_direction(method_rows.get(method, {}))
            for method, _ in CUTPOINT_METHODS
        )
        if direction is not None
    }
    if len(directions) > 1:
        notes.append("mixed dir.")
    return latex_escape(", ".join(notes)) if notes else "--"


def cutpoint_direction(row: dict[str, Any]) -> str | None:
    grouped_hr = numeric(row.get("univariable_hr"))
    if grouped_hr is None:
        grouped_hr = numeric(row.get("univariable_firth_hr"))
    if grouped_hr is None or grouped_hr == 1:
        return None
    return "harmful" if grouped_hr > 1 else "protective"


def format_matrix_p(value: Any) -> str:
    if not is_number(value):
        return "NA"
    number = float(value)
    if number < 0.001:
        return "$<$.001"
    if number >= 0.995:
        return "1.00"
    rendered = f"{number:.3g}"
    return rendered[1:] if rendered.startswith("0.") else rendered


def format_amplification(value: Any) -> str:
    if not is_number(value):
        return "--"
    number = float(value)
    return f"{number:.1f}" if number >= 10 else f"{number:.2f}"


def numeric(value: Any) -> float | None:
    return float(value) if is_number(value) else None


def boolean_value(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    normalized = str(value or "").strip().lower()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    return None


def safe_abs_log(value: float | None) -> float | None:
    if value is None or value <= 0:
        return None
    import math

    return abs(math.log(value))


def format_hr_pair(implied: Any, grouped: Any) -> str:
    return f"{format_effect(implied)}/{format_effect(grouped)}"


def median_result(row: dict[str, Any]) -> str:
    hr = format_effect(row.get("median_adjusted_hr"))
    low = format_effect(row.get("median_adjusted_hr_conf_low"))
    high = format_effect(row.get("median_adjusted_hr_conf_high"))
    adjusted_p = format_p(row.get("median_adjusted_p"))
    rmst = format_signed_days(row.get("median_rmst_delta_days"))
    rmst_p = format_p(row.get("median_rmst_p"))
    tau = format_signed_days(row.get("median_rmst_tau_days")).lstrip("+")
    return f"aHR {hr} ({low}-{high}), p={adjusted_p}; RMST {rmst} d at tau={tau} d, p={rmst_p}"


def continuous_result(row: dict[str, Any]) -> str:
    hr = format_effect(row.get("continuous_univariable_hr"))
    low = format_effect(row.get("continuous_univariable_hr_conf_low"))
    high = format_effect(row.get("continuous_univariable_hr_conf_high"))
    linear_p = format_p(row.get("continuous_univariable_p"))
    linear_q = format_p(row.get("continuous_bh_p"))
    nonlinearity_p = format_p(row.get("spline_nonlinearity_p"))
    nonlinearity_q = format_p(row.get("spline_nonlinearity_bh_p"))
    return (
        f"HR/SD {hr} ({low}-{high}), p={linear_p}, q={linear_q}; "
        f"nonlinearity p={nonlinearity_p}, q={nonlinearity_q}"
    )


def format_effect(value: Any) -> str:
    if not is_number(value):
        return "NA"
    number = float(value)
    return f"{number:.3f}" if abs(number) < 0.1 else f"{number:.2f}"


def format_signed_days(value: Any) -> str:
    if not is_number(value):
        return "NA"
    return f"{float(value):+.0f}"


def format_p(value: Any) -> str:
    if not is_number(value):
        return "NA"
    number = float(value)
    return f"{number:.2e}" if number < 0.001 else f"{number:.3f}"


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


def is_significant(value: Any) -> bool:
    return is_number(value) and float(value) <= EVIDENCE_ALPHA


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
