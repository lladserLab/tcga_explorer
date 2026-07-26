#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import shutil
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ATLAS_DIR = (
    PROJECT_ROOT
    / "artifacts"
    / "immune_pancancer"
    / "immune_os_immport_all_v2_1"
)
DEFAULT_OUTPUT_DIR = (
    PROJECT_ROOT
    / "docs"
    / "publication"
    / "benchmark"
    / "immune_pancancer_atlas_v2_1"
)
DEFAULT_TABLE_PATH = (
    PROJECT_ROOT
    / "manuscript"
    / "bioinformatics_app_note"
    / "tables"
    / "immune_pancancer_atlas_model_summary.tex"
)
EXPECTED_PIPELINE = (
    "immune-pancancer-primary-plus-ordinal-sensitivity-cox-audit-v2.1"
)


def main() -> None:
    args = parse_args()
    atlas_dir = Path(args.atlas_dir).resolve()
    output_dir = Path(args.output_dir).resolve()
    table_path = Path(args.table_path).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    table_path.parent.mkdir(parents=True, exist_ok=True)

    summary = read_json(atlas_dir / "screen_summary.json")
    audit = read_json(atlas_dir / "audit_report.json")
    validate(summary, audit)
    family_rows = read_csv(atlas_dir / "model_family_summary.csv")

    compact = {
        "screen_id": summary["screen_id"],
        "created_at": summary["created_at"],
        "pipeline_version": summary["pipeline_version"],
        "data_version": summary.get("data_version") or {},
        "headline": summary["headline"],
        "model_family_summary": family_rows,
        "clinical_sensitivity": {
            "selection_hierarchy": summary["clinical_sensitivity"][
                "selection_hierarchy"
            ],
            "summary": summary["clinical_sensitivity"]["summary"],
            "recurrence_summary": summary["clinical_sensitivity"][
                "recurrence"
            ]["summary"],
            "notes": summary["clinical_sensitivity"]["notes"],
        },
        "audit": {
            "schema_version": audit["schema_version"],
            "reproducibility_hash": audit["reproducibility_hash"],
            "software_versions": audit["software_versions"],
            "expression_matrix_count": len(
                audit["expression_matrix_manifest"]
            ),
        },
        "method_notes": summary.get("method_notes") or [],
    }
    (output_dir / "atlas_summary.json").write_text(
        json.dumps(compact, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    shutil.copyfile(
        atlas_dir / "model_family_summary.csv",
        output_dir / "model_family_summary.csv",
    )
    write_clinical_summary_csv(
        output_dir / "clinical_sensitivity_summary.csv",
        summary["clinical_sensitivity"]["summary"],
    )
    (output_dir / "README.md").write_text(
        render_readme(compact),
        encoding="utf-8",
    )
    table_path.write_text(
        render_latex_table(family_rows),
        encoding="utf-8",
    )
    print(
        f"Exported immune atlas benchmark summary to {output_dir}",
        flush=True,
    )
    print(f"Wrote manuscript table {table_path}", flush=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Export compact publication records from the versioned immune "
            "pan-cancer atlas."
        )
    )
    parser.add_argument("--atlas-dir", default=str(DEFAULT_ATLAS_DIR))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--table-path", default=str(DEFAULT_TABLE_PATH))
    return parser.parse_args()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def validate(summary: dict[str, Any], audit: dict[str, Any]) -> None:
    if summary.get("pipeline_version") != EXPECTED_PIPELINE:
        raise SystemExit(
            "Unexpected immune atlas pipeline: "
            f"{summary.get('pipeline_version')}"
        )
    if summary.get("headline", {}).get("immune_genes") != 3118:
        raise SystemExit("The publication atlas must contain 3,118 genes.")
    if not audit.get("reproducibility_hash"):
        raise SystemExit("The immune atlas audit lacks a reproducibility hash.")
    if len(audit.get("expression_matrix_manifest") or {}) != 32:
        raise SystemExit("The immune atlas audit must pin 32 expression matrices.")


def write_clinical_summary_csv(
    path: Path,
    summary: dict[str, Any],
) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["metric", "value"])
        writer.writeheader()
        for key, value in summary.items():
            if isinstance(value, (dict, list)):
                value = json.dumps(value, ensure_ascii=False, sort_keys=True)
            writer.writerow({"metric": key, "value": value})


def integer(row: dict[str, str], key: str) -> str:
    value = row.get(key)
    if value in (None, ""):
        return "--"
    return f"{int(float(value)):,}"


def render_latex_table(rows: list[dict[str, str]]) -> str:
    labels = {
        "primary": "Primary expression",
        "stage_grade_adjusted": "Stage + grade",
        "stage_adjusted": "Stage",
        "grade_adjusted": "Grade",
        "availability_selected": "Availability-selected",
    }
    body = []
    for row in rows:
        body.append(
            " & ".join(
                [
                    labels.get(row["model"], row["model_label"]),
                    integer(row, "completed_gene_cohort_models"),
                    integer(row, "global_fdr_hits"),
                    integer(row, "meta_fdr_gene_hits"),
                    integer(row, "global_fdr_ph_flagged"),
                    (
                        integer(row, "recurrent_harmful_genes_ge5")
                        + " / "
                        + integer(row, "recurrent_protective_genes_ge5")
                    ),
                ]
            )
            + r" \\"
        )
    return (
        "\\begin{table}[p]\n"
        "\\centering\n"
        "\\caption{Versioned 3,118-gene ImmPort pan-cancer atlas. "
        "Gene--cancer BH-FDR and gene-level meta-FDR are calculated "
        "separately within each comparable model family. PH cautions count "
        "global-FDR hits whose model-level global "
        "\\texttt{cox.zph} $p<0.05$. H/P is the number of harmful/protective "
        "genes recurring as global-FDR hits in at least five cancers. The "
        "availability-selected row has no mixed-family meta-analysis.}\n"
        "\\label{tab:immune-atlas-model-summary}\n"
        "\\scriptsize\n"
        "\\setlength{\\tabcolsep}{3pt}\n"
        "\\begin{tabular}{lrrrrr}\n"
        "\\toprule\n"
        "Model family & Completed & FDR hits & Meta-FDR genes & "
        "FDR + PH caution & Recurrent H/P $\\geq 5$ \\\\\n"
        "\\midrule\n"
        + "\n".join(body)
        + "\n\\bottomrule\n"
        "\\end{tabular}\n"
        "\\end{table}\n"
    )


def render_readme(compact: dict[str, Any]) -> str:
    headline = compact["headline"]
    sensitivity = compact["clinical_sensitivity"]["summary"]
    audit = compact["audit"]
    return f"""# Immune Pan-Cancer Atlas v2.1

This directory contains the compact publication record for
`{compact["screen_id"]}`. The full model-level artifacts remain in the
versioned application artifact bundle.

## Frozen contract

- Pipeline: `{compact["pipeline_version"]}`
- ImmPort genes: {headline["immune_genes"]:,}
- Strict-OS cohorts prepared: {headline["prepared_cohorts"]:,}
- Primary completed gene-cancer models: {headline["completed_gene_cohort_models"]:,}
- Primary global-FDR hits: {headline["global_fdr_hits"]:,}
- Primary meta-FDR genes: {headline["meta_fdr_gene_hits"]:,}
- Selected adjusted models evaluable: {sensitivity["evaluable"]:,}
- Selected adjusted global-FDR hits: {sensitivity["fdr_significant"]:,}
- Primary global-FDR hits retained: {sensitivity["retained"]:,}
- Primary global-FDR hits attenuated: {sensitivity["attenuated"]:,}
- Primary global-FDR direction flips: {sensitivity["primary_fdr_direction_reversed"]:,}
- Primary global-FDR hits without evaluable adjustment: {sensitivity["primary_fdr_not_evaluable"]:,}

The last quantity is the subset of primary global-FDR hits without an
availability-selected adjusted model, not all clinically non-evaluable
gene-cancer pairs. It is reported in the manuscript decomposition.

## Interpretation

The primary atlas remains the comparable cross-cancer estimand. Adjustment
families use different complete-case populations and therefore should not be
ranked by raw hit counts alone. Loss of global-FDR support can reflect clinical
confounding, reduced sample size, or both. Mixed availability-selected families
are never meta-analyzed.

## Reproducibility

- Audit schema: `{audit["schema_version"]}`
- Audit reproducibility hash: `{audit["reproducibility_hash"]}`
- Expression matrices pinned by SHA-256: {audit["expression_matrix_count"]}
- Software: `{json.dumps(audit["software_versions"], sort_keys=True)}`
"""


if __name__ == "__main__":
    main()
