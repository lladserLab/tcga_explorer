from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCRIPT_PATH = Path(__file__).resolve()
for candidate in (SCRIPT_PATH.parents[1], Path("/app")):
    if (candidate / "app").exists():
        sys.path.insert(0, str(candidate))
        break

from app.cache_warmup import load_cache_manifest
from app.config import get_settings
from app.database import SessionLocal, wait_for_database
from app.main import ENDPOINT_LABELS, current_data_version, dataset_dates
from app.pancancer import adjust_p_values_bh
from app.pipeline_versions import IMMUNE_ATLAS_PIPELINE_VERSION
from app.r_runner import stable_hash
from app.schemas import AnalysisFilters
from immune_pancancer_screen import (
    IMMPORT_GMT_URL,
    IMMPORT_JSON_URL,
    apply_meta_fdr,
    build_cohort_summary,
    build_gene_summary,
    build_recurrence_summary,
    build_term_summary,
    is_threshold,
    load_immport_panel,
    nulls_last,
    parse_cohort_list,
    parse_gene_list,
    parse_number,
    prepare_cohorts,
    sha256_file,
    write_json,
    write_table,
)


DEFAULT_R_SCRIPT = SCRIPT_PATH.with_name("immune_pancancer_cox_atlas_v2.R")
MODEL_FAMILIES = (
    "primary",
    "stage_grade_adjusted",
    "stage_adjusted",
    "grade_adjusted",
)
ADJUSTED_MODEL_PREFERENCE = (
    "stage_grade_adjusted",
    "stage_adjusted",
    "grade_adjusted",
)
MODEL_LABELS = {
    "primary": "Primary continuous expression",
    "stage_grade_adjusted": "Ordinal stage + grade",
    "stage_adjusted": "Ordinal stage",
    "grade_adjusted": "Ordinal grade",
}
NUMERIC_FIELDS = {
    "n_patients",
    "n_events",
    "expression_mean",
    "expression_sd",
    "log_hr",
    "standard_error",
    "hazard_ratio",
    "hr_conf_low",
    "hr_conf_high",
    "p_value",
    "ph_p_value",
    "ph_global_p_value",
    "cox_warning_count",
}


def main() -> None:
    args = parse_args()
    settings = get_settings()
    output_root = (
        Path(args.output_root)
        if args.output_root
        else settings.artifact_dir / "immune_pancancer"
    )
    output_root.mkdir(parents=True, exist_ok=True)

    source_dir = output_root / "sources" / "immport_current"
    panel_terms, panel_rows, source_hashes = load_immport_panel(source_dir)
    panel_rows = select_panel_rows(panel_rows, parse_gene_list(args.genes), args.max_genes)
    if not panel_rows:
        raise SystemExit("No genes were selected for the immune pan-cancer atlas.")

    filters = AnalysisFilters.model_validate(json.loads(args.filters_json))
    requested_cohorts = parse_cohort_list(args.cohorts)
    identity = {
        "pipeline": IMMUNE_ATLAS_PIPELINE_VERSION,
        "immune_panel": {
            **source_hashes,
            "genes": [row["gene_symbol"] for row in panel_rows],
        },
        "cohorts": requested_cohorts,
        "endpoint": args.endpoint,
        "endpoint_mode": args.endpoint_mode,
        "expression_scale": args.expression_scale,
        "filters": filters.model_dump(mode="json"),
        "min_patients": args.min_patients,
        "min_events": args.min_events,
        "fdr_threshold": args.fdr_threshold,
    }
    screen_id = args.screen_id or f"immune_pc_{stable_hash(identity)[:24]}"
    screen_dir = output_root / screen_id
    screen_dir.mkdir(parents=True, exist_ok=True)

    panel_path = screen_dir / "immune_gene_panel.tsv"
    terms_path = screen_dir / "immune_terms.tsv"
    write_table(panel_path, panel_rows)
    write_table(terms_path, panel_terms)

    wait_for_database()
    with SessionLocal() as db:
        data_dates = dataset_dates(
            db,
            load_cache_manifest(settings.derived_expression_dir),
        )
        data_version = current_data_version(db)
        cohort_payloads, cohort_qc = prepare_cohorts(
            db=db,
            settings=settings,
            screen_dir=screen_dir,
            requested_cohorts=requested_cohorts,
            endpoint=args.endpoint,
            endpoint_mode=args.endpoint_mode,
            expression_scale=args.expression_scale,
            filters=filters,
        )

    print(
        f"Hashing {len(cohort_payloads)} expression matrices for the audit.",
        flush=True,
    )
    expression_matrix_manifest = build_expression_matrix_manifest(
        cohort_payloads
    )
    software_versions = collect_software_versions()
    existing_manifest_path = screen_dir / "manifest.json"
    existing_manifest = {}
    if args.postprocess_only and existing_manifest_path.exists():
        existing_manifest = json.loads(
            existing_manifest_path.read_text(encoding="utf-8")
        )
    created_at = (
        existing_manifest.get("created_at")
        or datetime.now(timezone.utc).isoformat()
    )
    manifest = {
        "screen_id": screen_id,
        "created_at": created_at,
        "pipeline_version": IMMUNE_ATLAS_PIPELINE_VERSION,
        "data_version": data_version,
        "data_dates": data_dates,
        "expression_matrix_manifest": expression_matrix_manifest,
        "software_versions": software_versions,
        "immune_panel": {
            "source": "ImmPort gene lists current release, frozen by SHA-256",
            "json_url": IMMPORT_JSON_URL,
            "gmt_url": IMMPORT_GMT_URL,
            **source_hashes,
            "source_term_count": len(panel_terms),
            "selected_gene_count": len(panel_rows),
        },
        "request": {
            "endpoint": args.endpoint,
            "endpoint_mode": args.endpoint_mode,
            "expression_scale": args.expression_scale,
            "filters": filters.model_dump(mode="json"),
            "min_patients": args.min_patients,
            "min_events": args.min_events,
            "fdr_threshold": args.fdr_threshold,
            "requested_cohorts": requested_cohorts,
        },
        "model_contract": {
            "primary_estimand": "Cox HR per +1 within-cohort SD expression",
            "families": list(MODEL_FAMILIES),
            "selection_hierarchy": list(ADJUSTED_MODEL_PREFERENCE),
            "covariate_encoding": {
                "stage": "0/I/II/III/IV -> 0/1/2/3/4; substages collapse",
                "grade": "G1-G5 -> 1-5",
            },
            "fdr_scopes": {
                "cohort_level": (
                    "BH globally across completed gene-cancer tests, "
                    "calculated separately for each model family"
                ),
                "selected_sensitivity": (
                    "BH globally across one availability-selected adjusted "
                    "test per evaluable gene-cancer pair"
                ),
                "meta_level": (
                    "BH across gene-level random-effects meta-analysis tests, "
                    "calculated separately for each model family"
                ),
            },
        },
        "cohorts": cohort_qc,
    }
    manifest_path = existing_manifest_path
    write_json(manifest_path, manifest)

    checkpoint_dir = screen_dir / "model_checkpoints"
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    r_input_path = screen_dir / "r_input.json"
    r_payload = {
        "screen_id": screen_id,
        "pipeline_version": IMMUNE_ATLAS_PIPELINE_VERSION,
        "genes": [{"gene_symbol": row["gene_symbol"]} for row in panel_rows],
        "cohorts": cohort_payloads,
        "min_patients": args.min_patients,
        "min_events": args.min_events,
        "expression_scale": args.expression_scale,
        "output_dir": str(checkpoint_dir),
        "workers": args.workers,
        "force": args.force,
    }
    write_json(r_input_path, r_payload)

    if args.prepare_only:
        print(f"Prepared immune pan-cancer atlas at {screen_dir}", flush=True)
        return
    if not args.postprocess_only:
        run_r_atlas(args.r_script, r_input_path, timeout=args.timeout)

    checkpoint_paths = [
        checkpoint_dir / f"{safe_cohort_name(cohort['cohort'])}.raw.csv"
        for cohort in cohort_payloads
    ]
    missing_checkpoints = [path for path in checkpoint_paths if not path.exists()]
    if missing_checkpoints:
        raise RuntimeError(
            "Missing cohort model checkpoints: "
            + ", ".join(path.name for path in missing_checkpoints)
        )

    raw_results_path = screen_dir / "model_results.raw.csv"
    raw_row_count = combine_checkpoints(checkpoint_paths, raw_results_path)
    expected_rows = (
        len(panel_rows)
        * len(cohort_payloads)
        * len(MODEL_FAMILIES)
    )
    if raw_row_count != expected_rows:
        raise RuntimeError(
            f"Expected {expected_rows} raw model rows; found {raw_row_count}."
        )

    print(f"Reading {raw_row_count:,} model rows for post-processing.", flush=True)
    model_rows = read_model_results(raw_results_path)
    validate_model_rows(
        model_rows,
        expected_genes=len(panel_rows),
        expected_cohorts=len(cohort_payloads),
    )
    apply_family_statistics(model_rows, args.fdr_threshold)

    results_path = screen_dir / "model_results.csv"
    write_table(results_path, model_rows)

    rows_by_model = {
        model: [row for row in model_rows if row.get("model") == model]
        for model in MODEL_FAMILIES
    }
    model_views: dict[str, dict[str, Any]] = {}
    all_gene_summaries: list[dict] = []
    all_cohort_summaries: list[dict] = []
    all_term_summaries: list[dict] = []

    for model in MODEL_FAMILIES:
        print(f"Summarizing {MODEL_LABELS[model]}.", flush=True)
        view, gene_summary, cohort_summary, term_summary = build_model_view(
            model=model,
            panel_rows=panel_rows,
            panel_terms=panel_terms,
            results=rows_by_model[model],
            cohort_qc=cohort_qc,
            fdr_threshold=args.fdr_threshold,
        )
        model_views[model] = view
        all_gene_summaries.extend(
            [{"model": model, "model_label": MODEL_LABELS[model], **row}
             for row in gene_summary]
        )
        all_cohort_summaries.extend(
            [{"model": model, "model_label": MODEL_LABELS[model], **row}
             for row in cohort_summary]
        )
        all_term_summaries.extend(
            [{"model": model, "model_label": MODEL_LABELS[model], **row}
             for row in term_summary]
        )

    primary_gene_summary = [
        row for row in all_gene_summaries if row["model"] == "primary"
    ]
    primary_cohort_summary = [
        row for row in all_cohort_summaries if row["model"] == "primary"
    ]
    primary_term_summary = [
        row for row in all_term_summaries if row["model"] == "primary"
    ]

    gene_models_path = screen_dir / "gene_model_summary.csv"
    cohort_models_path = screen_dir / "cohort_model_summary.csv"
    term_models_path = screen_dir / "term_model_summary.csv"
    write_table(gene_models_path, all_gene_summaries)
    write_table(cohort_models_path, all_cohort_summaries)
    write_table(term_models_path, all_term_summaries)

    gene_summary_path = screen_dir / "gene_summary.csv"
    cohort_summary_path = screen_dir / "cohort_summary.csv"
    term_summary_path = screen_dir / "term_summary.csv"
    write_table(gene_summary_path, primary_gene_summary)
    write_table(cohort_summary_path, primary_cohort_summary)
    write_table(term_summary_path, primary_term_summary)

    selected_rows, clinical_sensitivity = build_selected_sensitivity(
        model_rows=model_rows,
        primary_gene_summary=primary_gene_summary,
        panel_rows=panel_rows,
        fdr_threshold=args.fdr_threshold,
    )
    selected_path = screen_dir / "selected_sensitivity.csv"
    write_table(selected_path, selected_rows)

    model_family_summary = build_model_family_summary(
        model_views=model_views,
        clinical_sensitivity=clinical_sensitivity,
    )
    model_family_summary_path = screen_dir / "model_family_summary.csv"
    write_table(model_family_summary_path, model_family_summary)

    methodology_path = screen_dir / "methodology.txt"
    write_methodology_v2(
        methodology_path,
        manifest=manifest,
        clinical_sensitivity=clinical_sensitivity,
    )

    checkpoint_manifest = {
        path.name: {
            "sha256": sha256_file(path),
            "bytes": path.stat().st_size,
        }
        for path in checkpoint_paths
    }
    patient_record_paths = sorted((screen_dir / "cohort_records").glob("*.csv"))
    patient_record_manifest = {
        path.name: {
            "sha256": sha256_file(path),
            "bytes": path.stat().st_size,
        }
        for path in patient_record_paths
    }
    artifact_paths = {
        "manifest": manifest_path,
        "panel": panel_path,
        "terms": terms_path,
        "model_results_raw": raw_results_path,
        "model_results": results_path,
        "selected_sensitivity": selected_path,
        "model_family_summary": model_family_summary_path,
        "gene_model_summary": gene_models_path,
        "cohort_model_summary": cohort_models_path,
        "term_model_summary": term_models_path,
        "gene_summary_primary": gene_summary_path,
        "cohort_summary_primary": cohort_summary_path,
        "term_summary_primary": term_summary_path,
        "methodology": methodology_path,
    }
    artifact_manifest = {
        name: {
            "path": str(path),
            "sha256": sha256_file(path),
            "bytes": path.stat().st_size,
        }
        for name, path in artifact_paths.items()
    }
    audit_core = {
        "pipeline_version": IMMUNE_ATLAS_PIPELINE_VERSION,
        "data_version": data_version,
        "data_dates": data_dates,
        "expression_matrix_manifest": expression_matrix_manifest,
        "software_versions": software_versions,
        "request": manifest["request"],
        "model_contract": manifest["model_contract"],
        "immune_panel": manifest["immune_panel"],
        "checkpoint_manifest": checkpoint_manifest,
        "patient_record_manifest": patient_record_manifest,
        "artifacts": artifact_manifest,
    }
    audit = {
        "schema_version": "tcga-trace-immune-pancancer-atlas-audit-v2",
        "report_type": "immune_pancancer_atlas_audit",
        "screen_id": screen_id,
        "created_at": created_at,
        "reproducibility_hash": stable_hash(audit_core),
        **audit_core,
    }
    audit_path = screen_dir / "audit_report.json"
    write_json(audit_path, audit)

    primary_view = model_views["primary"]
    summary = {
        "screen_id": screen_id,
        "created_at": created_at,
        "pipeline_version": IMMUNE_ATLAS_PIPELINE_VERSION,
        "data_version": data_version,
        "headline": {
            "immune_genes": len(panel_rows),
            "immune_terms": len(panel_terms),
            "prepared_cohorts": len(cohort_payloads),
            "completed_gene_cohort_models": primary_view["headline"][
                "completed_gene_cohort_models"
            ],
            "global_fdr_hits": primary_view["headline"]["global_fdr_hits"],
            "meta_fdr_gene_hits": primary_view["headline"][
                "meta_fdr_gene_hits"
            ],
            "adjusted_gene_cohort_models": clinical_sensitivity["summary"][
                "evaluable"
            ],
            "adjusted_global_fdr_hits": clinical_sensitivity["summary"][
                "fdr_significant"
            ],
            "retained_global_fdr_hits": clinical_sensitivity["summary"][
                "retained"
            ],
            "attenuated_global_fdr_hits": clinical_sensitivity["summary"][
                "attenuated"
            ],
            "direction_reversed": clinical_sensitivity["summary"][
                "primary_fdr_direction_reversed"
            ],
            "direction_reversed_all": clinical_sensitivity["summary"][
                "direction_reversed_all"
            ],
            "fdr_threshold": args.fdr_threshold,
        },
        "model_views": model_views,
        "clinical_sensitivity": clinical_sensitivity,
        "top_genes": primary_view["top_genes"],
        "top_cohorts": primary_view["top_cohorts"],
        "top_terms": primary_view["top_terms"],
        "recurrence": primary_view["recurrence"],
        "status_counts": primary_view["status_counts"],
        "direction_counts_global_fdr": primary_view[
            "direction_counts_global_fdr"
        ],
        "audit": {
            "schema_version": audit["schema_version"],
            "reproducibility_hash": audit["reproducibility_hash"],
            "path": str(audit_path),
        },
        "paths": {
            **{name: str(path) for name, path in artifact_paths.items()},
            "audit_json": str(audit_path),
        },
        "method_notes": [
            (
                "Primary and ordinal-adjusted Cox models use expression "
                "z-scored within each cancer."
            ),
            (
                "Stage 0/I/II/III/IV maps to 0/1/2/3/4 and grade G1-G5 "
                "maps to 1-5; unknown values remain missing."
            ),
            (
                "Gene-cancer BH-FDR and gene-level random-effects "
                "meta-analysis are calculated separately by model family."
            ),
            (
                "The availability-selected sensitivity hierarchy is "
                "stage+grade, stage, then grade; mixed selected families "
                "are never meta-analyzed."
            ),
            (
                "The atlas is association analysis, not causal inference; "
                "tumor purity, immune composition and treatment are not "
                "included as covariates."
            ),
        ],
    }
    summary_path = screen_dir / "screen_summary.json"
    write_json(summary_path, summary)

    print(
        json.dumps(summary["headline"], indent=2, ensure_ascii=False),
        flush=True,
    )
    print(
        f"Reproducibility hash: {audit['reproducibility_hash']}",
        flush=True,
    )
    print(f"Artifacts: {screen_dir}", flush=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build the versioned ImmPort immune pan-cancer atlas with "
            "primary and ordinal clinical-sensitivity Cox models."
        )
    )
    parser.add_argument("--endpoint", choices=list(ENDPOINT_LABELS), default="OS")
    parser.add_argument(
        "--endpoint-mode",
        choices=[
            "same_endpoint",
            "death_like",
            "progression_like",
            "best_available",
        ],
        default="same_endpoint",
    )
    parser.add_argument(
        "--expression-scale",
        choices=["log2_tpm", "log2_fpkm", "log2_fpkm_uq"],
        default="log2_tpm",
    )
    parser.add_argument("--cohorts", default="")
    parser.add_argument("--genes", default="")
    parser.add_argument("--max-genes", type=int, default=0)
    parser.add_argument("--filters-json", default="{}")
    parser.add_argument("--min-patients", type=int, default=10)
    parser.add_argument("--min-events", type=int, default=5)
    parser.add_argument("--fdr-threshold", type=float, default=0.10)
    parser.add_argument("--screen-id", default="")
    parser.add_argument("--output-root", default="")
    parser.add_argument("--r-script", default=str(DEFAULT_R_SCRIPT))
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument(
        "--timeout",
        type=int,
        default=0,
        help="R timeout in seconds; zero disables the timeout.",
    )
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--postprocess-only", action="store_true")
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def select_panel_rows(
    panel_rows: list[dict],
    requested_genes: list[str],
    max_genes: int,
) -> list[dict]:
    if requested_genes:
        lookup = {row["gene_symbol"]: row for row in panel_rows}
        selected = []
        for gene in requested_genes:
            selected.append(
                lookup.get(
                    gene,
                    {
                        "gene_symbol": gene,
                        "source_list_count": 0,
                        "go_term_count": 0,
                        "reactome_term_count": 0,
                        "term_ids": "",
                        "term_names": "",
                        "term_sources": "",
                        "term_links": "",
                        "panel_note": (
                            "user_requested_gene_not_in_immport_panel"
                        ),
                    },
                )
            )
        panel_rows = sorted(
            {row["gene_symbol"]: row for row in selected}.values(),
            key=lambda row: row["gene_symbol"],
        )
    if max_genes:
        panel_rows = panel_rows[:max_genes]
    return panel_rows


def safe_cohort_name(cohort: str) -> str:
    return "".join(
        character
        if character.isalnum() or character in "_.-"
        else "_"
        for character in cohort
    )


def build_expression_matrix_manifest(
    cohort_payloads: list[dict],
) -> dict[str, dict[str, Any]]:
    output = {}
    for cohort in cohort_payloads:
        metadata_path = Path(cohort["metadata_path"])
        matrix_path = Path(cohort["matrix_path"])
        output[str(cohort["cohort"])] = {
            "metadata_file": metadata_path.name,
            "metadata_sha256": sha256_file(metadata_path),
            "metadata_bytes": metadata_path.stat().st_size,
            "matrix_file": matrix_path.name,
            "matrix_sha256": sha256_file(matrix_path),
            "matrix_bytes": matrix_path.stat().st_size,
        }
    return output


def collect_software_versions() -> dict[str, Any]:
    r_code = (
        "cat(jsonlite::toJSON(list("
        "R=R.version.string,"
        "survival=as.character(packageVersion('survival')),"
        "jsonlite=as.character(packageVersion('jsonlite'))"
        "),auto_unbox=TRUE))"
    )
    result = subprocess.run(
        ["Rscript", "-e", r_code],
        check=True,
        capture_output=True,
        text=True,
    )
    return {
        "python": sys.version.split()[0],
        **json.loads(result.stdout),
    }


def run_r_atlas(r_script: str, input_path: Path, timeout: int) -> None:
    command = ["Rscript", r_script, str(input_path)]
    print("Running " + " ".join(command), flush=True)
    subprocess.run(command, check=True, timeout=timeout or None)


def combine_checkpoints(paths: list[Path], output_path: Path) -> int:
    header: str | None = None
    row_count = 0
    with output_path.open("w", newline="", encoding="utf-8") as output:
        for path in paths:
            with path.open(newline="", encoding="utf-8") as source:
                current_header = source.readline()
                if not current_header:
                    raise RuntimeError(f"Empty model checkpoint: {path}")
                if header is None:
                    header = current_header
                    output.write(header)
                elif current_header != header:
                    raise RuntimeError(
                        f"Model checkpoint header mismatch: {path}"
                    )
                for line in source:
                    output.write(line)
                    row_count += 1
    return row_count


def read_model_results(path: Path) -> list[dict]:
    rows = list(csv.DictReader(path.open(newline="", encoding="utf-8")))
    for row in rows:
        for field in NUMERIC_FIELDS:
            row[field] = parse_number(row.get(field))
    return rows


def validate_model_rows(
    rows: list[dict],
    *,
    expected_genes: int,
    expected_cohorts: int,
) -> None:
    expected_per_family = expected_genes * expected_cohorts
    counts = Counter(row.get("model") for row in rows)
    unexpected = sorted(set(counts) - set(MODEL_FAMILIES))
    if unexpected:
        raise RuntimeError(
            "Unexpected model families: " + ", ".join(unexpected)
        )
    for model in MODEL_FAMILIES:
        if counts[model] != expected_per_family:
            raise RuntimeError(
                f"{model} has {counts[model]} rows; expected "
                f"{expected_per_family}."
            )
    identities = {
        (row.get("gene_symbol"), row.get("cohort"), row.get("model"))
        for row in rows
    }
    if len(identities) != len(rows):
        raise RuntimeError("Duplicate gene-cohort-model rows were detected.")


def apply_family_statistics(rows: list[dict], fdr_threshold: float) -> None:
    by_model: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_model[str(row.get("model"))].append(row)
    for model in MODEL_FAMILIES:
        family = by_model[model]
        adjusted = adjust_p_values_bh(
            [
                row.get("p_value")
                if row.get("status") == "completed"
                else None
                for row in family
            ]
        )
        for row, fdr in zip(family, adjusted):
            row["global_fdr"] = fdr
            row["fdr"] = fdr
            hazard_ratio = parse_number(row.get("hazard_ratio"))
            if hazard_ratio is None:
                direction = "not_evaluable"
            elif hazard_ratio > 1:
                direction = "harmful"
            elif hazard_ratio < 1:
                direction = "protective"
            else:
                direction = "neutral"
            significant = (
                fdr is not None
                and float(fdr) <= fdr_threshold
                and direction in {"harmful", "protective"}
            )
            row["direction"] = direction
            row["significant"] = significant
            row["effect_category"] = (
                direction
                if significant
                else "not_evaluable"
                if direction == "not_evaluable"
                else "neutral"
            )
            ph_global = parse_number(row.get("ph_global_p_value"))
            row["ph_flagged"] = (
                ph_global is not None and ph_global < 0.05
            )


def build_model_view(
    *,
    model: str,
    panel_rows: list[dict],
    panel_terms: list[dict],
    results: list[dict],
    cohort_qc: list[dict],
    fdr_threshold: float,
) -> tuple[dict, list[dict], list[dict], list[dict]]:
    gene_summary = build_gene_summary(panel_rows, results, fdr_threshold)
    apply_meta_fdr(gene_summary)
    cohort_summary = build_cohort_summary(
        results,
        cohort_qc,
        fdr_threshold,
    )
    term_summary = build_term_summary(
        panel_terms,
        panel_rows,
        gene_summary,
        results,
        fdr_threshold,
    )
    completed = [
        row for row in results if row.get("status") == "completed"
    ]
    hits = [row for row in completed if row.get("significant")]
    meta_hits = [
        row
        for row in gene_summary
        if is_threshold(row.get("meta_fdr"), fdr_threshold)
    ]
    ph_flagged = [
        row for row in completed if bool(row.get("ph_flagged"))
    ]
    top_genes = sorted(gene_summary, key=model_gene_sort_key)[:25]
    top_cohorts = sorted(
        cohort_summary,
        key=lambda row: (
            nulls_last(row.get("min_global_fdr")),
            row.get("cohort") or "",
        ),
    )[:15]
    view = {
        "model": model,
        "label": MODEL_LABELS[model],
        "role": (
            "primary_estimand"
            if model == "primary"
            else "clinical_sensitivity"
        ),
        "headline": {
            "completed_gene_cohort_models": len(completed),
            "global_fdr_hits": len(hits),
            "meta_fdr_gene_hits": len(meta_hits),
            "ph_flagged_models": len(ph_flagged),
            "global_fdr_ph_flagged": sum(
                bool(row.get("ph_flagged")) for row in hits
            ),
            "fdr_threshold": fdr_threshold,
        },
        "top_genes": top_genes,
        "top_cohorts": top_cohorts,
        "top_terms": term_summary[:20],
        "recurrence": build_recurrence_summary(results, gene_summary),
        "status_counts": dict(
            Counter(row.get("status", "unknown") for row in results)
        ),
        "direction_counts_global_fdr": dict(
            Counter(row.get("direction") for row in hits)
        ),
    }
    return view, gene_summary, cohort_summary, term_summary


def model_gene_sort_key(row: dict) -> tuple:
    return (
        nulls_last(row.get("meta_fdr")),
        nulls_last(row.get("min_global_fdr")),
        -(int(row.get("global_fdr_hits") or 0)),
        row.get("gene_symbol") or "",
    )


def build_selected_sensitivity(
    *,
    model_rows: list[dict],
    primary_gene_summary: list[dict],
    panel_rows: list[dict],
    fdr_threshold: float,
) -> tuple[list[dict], dict]:
    by_identity: dict[tuple[str, str], dict[str, dict]] = defaultdict(dict)
    for row in model_rows:
        identity = (str(row.get("gene_symbol")), str(row.get("cohort")))
        by_identity[identity][str(row.get("model"))] = row

    selected_rows: list[dict] = []
    selected_models: list[dict | None] = []
    for identity in sorted(by_identity):
        models = by_identity[identity]
        primary = models.get("primary")
        if not primary or primary.get("status") != "completed":
            continue
        selected = next(
            (
                models.get(model)
                for model in ADJUSTED_MODEL_PREFERENCE
                if models.get(model)
                and models[model].get("status") == "completed"
            ),
            None,
        )
        selected_models.append(selected)
        reasons = list(
            dict.fromkeys(
                str(models[model].get("reason")).strip()
                for model in ADJUSTED_MODEL_PREFERENCE
                if models.get(model) and models[model].get("reason")
            )
        )
        selected_rows.append(
            {
                "gene_symbol": identity[0],
                "cohort": identity[1],
                "primary_n_patients": primary.get("n_patients"),
                "primary_n_events": primary.get("n_events"),
                "primary_hazard_ratio": primary.get("hazard_ratio"),
                "primary_p_value": primary.get("p_value"),
                "primary_global_fdr": primary.get("global_fdr"),
                "primary_direction": primary.get("direction"),
                "primary_significant": bool(primary.get("significant")),
                "selected_model": (
                    selected.get("model") if selected else None
                ),
                "selected_model_label": (
                    MODEL_LABELS.get(str(selected.get("model")))
                    if selected
                    else None
                ),
                "adjusted_status": (
                    "completed" if selected else "not_evaluable"
                ),
                "adjusted_reason": (
                    None
                    if selected
                    else " ".join(reasons[:2])
                    or "No ordinal stage- or grade-adjusted model was evaluable."
                ),
                "adjusted_n_patients": (
                    selected.get("n_patients") if selected else None
                ),
                "adjusted_n_events": (
                    selected.get("n_events") if selected else None
                ),
                "adjusted_log_hr": (
                    selected.get("log_hr") if selected else None
                ),
                "adjusted_standard_error": (
                    selected.get("standard_error") if selected else None
                ),
                "adjusted_hazard_ratio": (
                    selected.get("hazard_ratio") if selected else None
                ),
                "adjusted_hr_conf_low": (
                    selected.get("hr_conf_low") if selected else None
                ),
                "adjusted_hr_conf_high": (
                    selected.get("hr_conf_high") if selected else None
                ),
                "adjusted_p_value": (
                    selected.get("p_value") if selected else None
                ),
                "adjusted_ph_p_value": (
                    selected.get("ph_p_value") if selected else None
                ),
                "adjusted_ph_global_p_value": (
                    selected.get("ph_global_p_value")
                    if selected
                    else None
                ),
                "adjusted_ph_flagged": (
                    bool(selected.get("ph_flagged"))
                    if selected
                    else False
                ),
            }
        )

    selected_fdr = adjust_p_values_bh(
        [
            model.get("p_value")
            if model and model.get("status") == "completed"
            else None
            for model in selected_models
        ]
    )
    comparison_counts: Counter[str] = Counter()
    model_counts: Counter[str] = Counter()
    for row, fdr in zip(selected_rows, selected_fdr):
        row["adjusted_global_fdr"] = fdr
        adjusted_hr = parse_number(row.get("adjusted_hazard_ratio"))
        if adjusted_hr is None:
            adjusted_direction = "not_evaluable"
        elif adjusted_hr > 1:
            adjusted_direction = "harmful"
        elif adjusted_hr < 1:
            adjusted_direction = "protective"
        else:
            adjusted_direction = "neutral"
        row["adjusted_direction"] = adjusted_direction
        row["adjusted_significant"] = bool(
            fdr is not None
            and fdr <= fdr_threshold
            and adjusted_direction in {"harmful", "protective"}
        )
        comparison = clinical_comparison_label(row)
        row["clinical_sensitivity"] = comparison
        comparison_counts[comparison] += 1
        model_counts[str(row.get("selected_model") or "not_evaluable")] += 1

    primary_gene_lookup = {
        row["gene_symbol"]: row for row in primary_gene_summary
    }
    panel_lookup = {row["gene_symbol"]: row for row in panel_rows}
    by_gene: dict[str, Counter[str]] = defaultdict(Counter)
    selected_for_recurrence: list[dict] = []
    for row in selected_rows:
        gene = row["gene_symbol"]
        by_gene[gene][str(row["clinical_sensitivity"])] += 1
        directions_reversed = (
            row.get("adjusted_status") == "completed"
            and row.get("primary_direction") in {"harmful", "protective"}
            and row.get("adjusted_direction") in {"harmful", "protective"}
            and row.get("primary_direction") != row.get("adjusted_direction")
        )
        if directions_reversed:
            by_gene[gene]["direction_reversed_all"] += 1
            if row.get("primary_significant"):
                by_gene[gene]["primary_fdr_direction_reversed"] += 1
            if (
                row.get("primary_significant")
                and row.get("adjusted_significant")
            ):
                by_gene[gene]["both_fdr_direction_reversed"] += 1
        if row["adjusted_status"] == "completed":
            selected_for_recurrence.append(
                {
                    "gene_symbol": gene,
                    "cohort": row["cohort"],
                    "status": "completed",
                    "hazard_ratio": row["adjusted_hazard_ratio"],
                    "p_value": row["adjusted_p_value"],
                    "global_fdr": row["adjusted_global_fdr"],
                    "direction": row["adjusted_direction"],
                    "significant": row["adjusted_significant"],
                }
            )
    sensitivity_by_gene = []
    recurrence_gene_context = []
    for gene in sorted(panel_lookup):
        counts = by_gene[gene]
        primary_summary = primary_gene_lookup.get(gene, {})
        sensitivity_by_gene.append(
            {
                "gene_symbol": gene,
                "evaluable": (
                    sum(counts.values()) - counts["not_evaluable"]
                ),
                "not_evaluable": counts["not_evaluable"],
                "retained": counts["retained"],
                "attenuated": counts["attenuated"],
                "emerged": counts["emerged"],
                "direction_reversed_all": counts[
                    "direction_reversed_all"
                ],
                "primary_fdr_direction_reversed": counts[
                    "primary_fdr_direction_reversed"
                ],
                "both_fdr_direction_reversed": counts[
                    "both_fdr_direction_reversed"
                ],
                "direction_consistent": counts["direction_consistent"],
                "primary_global_fdr_hits": primary_summary.get(
                    "global_fdr_hits"
                ),
            }
        )
        recurrence_gene_context.append(
            {
                **panel_lookup[gene],
                "meta_hr": None,
                "meta_fdr": None,
                "meta_i_squared": None,
            }
        )
    sensitivity_by_gene.sort(
        key=lambda row: (
            -int(row["retained"]),
            int(row["primary_fdr_direction_reversed"]),
            -int(row["primary_global_fdr_hits"] or 0),
            row["gene_symbol"],
        )
    )
    selected_recurrence = build_recurrence_summary(
        selected_for_recurrence,
        recurrence_gene_context,
    )

    evaluable = sum(
        row["adjusted_status"] == "completed" for row in selected_rows
    )
    primary_fdr_direction_reversed = sum(
        row.get("primary_significant")
        and row.get("adjusted_status") == "completed"
        and row.get("primary_direction") in {"harmful", "protective"}
        and row.get("adjusted_direction") in {"harmful", "protective"}
        and row.get("primary_direction") != row.get("adjusted_direction")
        for row in selected_rows
    )
    both_fdr_direction_reversed = sum(
        row.get("primary_significant")
        and row.get("adjusted_significant")
        and row.get("adjusted_status") == "completed"
        and row.get("primary_direction") in {"harmful", "protective"}
        and row.get("adjusted_direction") in {"harmful", "protective"}
        and row.get("primary_direction") != row.get("adjusted_direction")
        for row in selected_rows
    )
    summary = {
        "total_primary_gene_cohort_pairs": len(selected_rows),
        "evaluable": evaluable,
        "not_evaluable": len(selected_rows) - evaluable,
        "fdr_significant": sum(
            bool(row.get("adjusted_significant")) for row in selected_rows
        ),
        "primary_fdr_not_evaluable": sum(
            bool(row.get("primary_significant"))
            and row.get("adjusted_status") != "completed"
            for row in selected_rows
        ),
        "retained": comparison_counts["retained"],
        "attenuated": comparison_counts["attenuated"],
        "emerged": comparison_counts["emerged"],
        "direction_reversed_all": comparison_counts["reversed"],
        "primary_fdr_direction_reversed": (
            primary_fdr_direction_reversed
        ),
        "both_fdr_direction_reversed": both_fdr_direction_reversed,
        "direction_consistent": comparison_counts[
            "direction_consistent"
        ],
        "ph_flagged": sum(
            bool(row.get("adjusted_ph_flagged")) for row in selected_rows
        ),
        "fdr_significant_ph_flagged": sum(
            bool(row.get("adjusted_significant"))
            and bool(row.get("adjusted_ph_flagged"))
            for row in selected_rows
        ),
        "selected_model_counts": dict(model_counts),
        "comparison_counts": dict(comparison_counts),
    }
    return selected_rows, {
        "available": bool(evaluable),
        "role": "atlas_scale_clinical_sensitivity",
        "primary_estimand_unchanged": True,
        "selection_hierarchy": list(ADJUSTED_MODEL_PREFERENCE),
        "fdr_scope": (
            "BH globally across availability-selected adjusted gene-cancer "
            "tests; family-specific FDR remains available in model_views"
        ),
        "mixed_selected_meta_analysis": {
            "available": False,
            "reason": (
                "Availability-selected effects use mixed clinical-adjustment "
                "families; a pooled meta-analysis is intentionally not "
                "reported."
            ),
        },
        "summary": summary,
        "top_genes": sensitivity_by_gene[:30],
        "recurrence": selected_recurrence,
        "notes": [
            (
                "Selection depends only on complete-case model availability, "
                "never on effect size or p-value."
            ),
            (
                "Retained and attenuated refer to atlas-wide FDR support, not "
                "clinical validity or causality."
            ),
        ],
    }


def clinical_comparison_label(row: dict) -> str:
    if row.get("adjusted_status") != "completed":
        return "not_evaluable"
    primary_direction = row.get("primary_direction")
    adjusted_direction = row.get("adjusted_direction")
    if (
        primary_direction in {"harmful", "protective"}
        and adjusted_direction in {"harmful", "protective"}
        and primary_direction != adjusted_direction
    ):
        return "reversed"
    primary_significant = bool(row.get("primary_significant"))
    adjusted_significant = bool(row.get("adjusted_significant"))
    if primary_significant and adjusted_significant:
        return "retained"
    if primary_significant and not adjusted_significant:
        return "attenuated"
    if not primary_significant and adjusted_significant:
        return "emerged"
    return "direction_consistent"


def build_model_family_summary(
    *,
    model_views: dict[str, dict[str, Any]],
    clinical_sensitivity: dict,
) -> list[dict[str, Any]]:
    rows = []
    for model in MODEL_FAMILIES:
        view = model_views[model]
        headline = view["headline"]
        recurrence = (view.get("recurrence") or {}).get("summary") or {}
        rows.append(
            {
                "model": model,
                "model_label": MODEL_LABELS[model],
                "role": view.get("role"),
                "completed_gene_cohort_models": headline.get(
                    "completed_gene_cohort_models"
                ),
                "global_fdr_hits": headline.get("global_fdr_hits"),
                "meta_fdr_gene_hits": headline.get("meta_fdr_gene_hits"),
                "ph_flagged_models": headline.get("ph_flagged_models"),
                "global_fdr_ph_flagged": headline.get(
                    "global_fdr_ph_flagged"
                ),
                "recurrent_harmful_genes_ge5": recurrence.get(
                    "recurrent_harmful_genes_ge5"
                ),
                "recurrent_protective_genes_ge5": recurrence.get(
                    "recurrent_protective_genes_ge5"
                ),
            }
        )
    sensitivity_summary = clinical_sensitivity["summary"]
    sensitivity_recurrence = (
        clinical_sensitivity.get("recurrence") or {}
    ).get("summary") or {}
    rows.append(
        {
            "model": "availability_selected",
            "model_label": "Availability-selected sensitivity",
            "role": "descriptive_sensitivity_no_mixed_meta",
            "completed_gene_cohort_models": sensitivity_summary.get(
                "evaluable"
            ),
            "global_fdr_hits": sensitivity_summary.get("fdr_significant"),
            "meta_fdr_gene_hits": None,
            "ph_flagged_models": sensitivity_summary.get("ph_flagged"),
            "global_fdr_ph_flagged": sensitivity_summary.get(
                "fdr_significant_ph_flagged"
            ),
            "recurrent_harmful_genes_ge5": sensitivity_recurrence.get(
                "recurrent_harmful_genes_ge5"
            ),
            "recurrent_protective_genes_ge5": sensitivity_recurrence.get(
                "recurrent_protective_genes_ge5"
            ),
        }
    )
    return rows


def write_methodology_v2(
    path: Path,
    *,
    manifest: dict,
    clinical_sensitivity: dict,
) -> None:
    request = manifest["request"]
    lines = [
        "Immune pan-cancer Cox atlas",
        "",
        f"Screen ID: {manifest['screen_id']}",
        f"Created at: {manifest['created_at']}",
        f"Pipeline: {manifest['pipeline_version']}",
        f"ImmPort GMT: {manifest['immune_panel']['gmt_url']}",
        f"ImmPort JSON: {manifest['immune_panel']['json_url']}",
        (
            "ImmPort GMT SHA-256: "
            f"{manifest['immune_panel']['gmt_sha256']}"
        ),
        (
            "ImmPort JSON SHA-256: "
            f"{manifest['immune_panel']['json_sha256']}"
        ),
        (
            "Selected immune genes: "
            f"{manifest['immune_panel']['selected_gene_count']}"
        ),
        (
            "Source immune terms: "
            f"{manifest['immune_panel']['source_term_count']}"
        ),
        (
            f"Endpoint request: {request['endpoint']} "
            f"({request['endpoint_mode']})"
        ),
        f"Expression scale: {request['expression_scale']}",
        (
            "Minimum patients/events: "
            f"{request['min_patients']}/{request['min_events']}"
        ),
        f"FDR threshold: {request['fdr_threshold']}",
        "",
        "Model families:",
        (
            "Primary: Surv(time, event) ~ expression_z, where expression is "
            "z-scored within cancer."
        ),
        (
            "Clinical sensitivity: expression_z plus ordinal stage, ordinal "
            "grade, or both."
        ),
        (
            "Major stage 0/I/II/III/IV maps to 0/1/2/3/4 and substages "
            "collapse; histologic grade G1-G5 maps to 1-5."
        ),
        (
            "Unknown clinical values remain missing and adjusted models use "
            "complete cases."
        ),
        (
            "The selected sensitivity hierarchy is stage+grade, stage, then "
            "grade, based only on availability."
        ),
        "",
        "Multiplicity and pooling:",
        (
            "BH-FDR is controlled globally across completed gene-cancer tests "
            "separately for primary, stage+grade, stage and grade families."
        ),
        (
            "Gene-level DerSimonian-Laird random-effects meta-analysis and "
            "meta-FDR are calculated separately for every model family."
        ),
        (
            "Availability-selected sensitivity tests receive an additional "
            "global BH-FDR for retained/attenuated summaries, but mixed "
            "selected families are not meta-analyzed."
        ),
        "",
        "Diagnostics and interpretation:",
        (
            "Each completed Cox model includes expression-specific and global "
            "proportional-hazards diagnostics from cox.zph when estimable."
        ),
        (
            "Missing clinical adjustment is not evaluable, not a failed "
            "primary association."
        ),
        (
            "This is association analysis, not causal inference. Tumor purity, "
            "immune composition and treatment are not included as covariates."
        ),
        "",
        "Selected sensitivity counts:",
        json.dumps(
            clinical_sensitivity["summary"],
            ensure_ascii=False,
            sort_keys=True,
        ),
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
