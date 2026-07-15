from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import subprocess
import sys
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCRIPT_PATH = Path(__file__).resolve()
for candidate in (SCRIPT_PATH.parents[1], Path("/app")):
    if (candidate / "app").exists():
        sys.path.insert(0, str(candidate))
        break

from sqlalchemy import select

from app.cache_warmup import load_cache_manifest
from app.config import get_settings
from app.database import SessionLocal, wait_for_database
from app.main import (
    ENDPOINT_LABELS,
    choose_pancancer_endpoint,
    current_data_version,
    dataset_dates,
    selected_endpoint_outcomes,
)
from app.models import Cohort, Sample
from app.pancancer import adjust_p_values_bh, meta_analysis_from_rows
from app.r_runner import stable_hash
from app.schemas import AnalysisFilters
from app.survival import filter_samples, sample_os_outcome


IMMPORT_JSON_URL = "https://s3.immport.org/release/genelists/current/all_gene_lists.json"
IMMPORT_GMT_URL = "https://s3.immport.org/release/genelists/current/all_gene_lists.gmt"
DEFAULT_R_SCRIPT = SCRIPT_PATH.with_name("immune_pancancer_cox_screen.R")

LONG_NUMERIC_FIELDS = {
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
    "cox_warning_count",
}
SUMMARY_NUMERIC_FIELDS = {
    "completed_cohorts",
    "tested_cohorts",
    "nominal_hits",
    "global_fdr_hits",
    "harmful_nominal_hits",
    "protective_nominal_hits",
    "harmful_global_fdr_hits",
    "protective_global_fdr_hits",
    "min_p_value",
    "min_global_fdr",
    "meta_hr",
    "meta_log_hr",
    "meta_standard_error",
    "meta_hr_conf_low",
    "meta_hr_conf_high",
    "meta_p_value",
    "meta_fdr",
    "meta_i_squared",
    "meta_tau_squared",
}


def main() -> None:
    args = parse_args()
    settings = get_settings()
    output_root = Path(args.output_root) if args.output_root else settings.artifact_dir / "immune_pancancer"
    output_root.mkdir(parents=True, exist_ok=True)

    panel_source_dir = output_root / "sources" / "immport_current"
    panel_terms, panel_rows, source_hashes = load_immport_panel(panel_source_dir)
    requested_genes = parse_gene_list(args.genes)
    if requested_genes:
        panel_rows = [row for row in panel_rows if row["gene_symbol"] in requested_genes]
        missing = sorted(set(requested_genes) - {row["gene_symbol"] for row in panel_rows})
        for gene in missing:
            panel_rows.append(
                {
                    "gene_symbol": gene,
                    "source_list_count": 0,
                    "go_term_count": 0,
                    "reactome_term_count": 0,
                    "term_ids": "",
                    "term_names": "",
                    "term_sources": "",
                    "term_links": "",
                    "panel_note": "user_requested_gene_not_in_immport_panel",
                }
            )
        panel_rows = sorted(panel_rows, key=lambda row: row["gene_symbol"])
    if args.max_genes:
        panel_rows = panel_rows[: args.max_genes]
    if not panel_rows:
        raise SystemExit("No genes were selected for the immune pan-cancer screen.")

    filters = AnalysisFilters.model_validate(json.loads(args.filters_json))
    requested_cohorts = parse_cohort_list(args.cohorts)
    payload_for_hash = {
        "pipeline": "immune-pancancer-cox-v1.0",
        "immune_panel": {
            "json_url": IMMPORT_JSON_URL,
            "gmt_url": IMMPORT_GMT_URL,
            "json_sha256": source_hashes["json_sha256"],
            "gmt_sha256": source_hashes["gmt_sha256"],
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
    screen_id = args.screen_id or f"immune_pc_{stable_hash(payload_for_hash)[:24]}"
    screen_dir = output_root / screen_id
    screen_dir.mkdir(parents=True, exist_ok=True)

    panel_path = screen_dir / "immune_gene_panel.tsv"
    write_table(panel_path, panel_rows)
    term_path = screen_dir / "immune_terms.tsv"
    write_table(term_path, panel_terms)

    wait_for_database()
    with SessionLocal() as db:
        data_dates = dataset_dates(db, load_cache_manifest(settings.derived_expression_dir))
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

    manifest = {
        "screen_id": screen_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "pipeline_version": "immune-pancancer-cox-v1.0",
        "data_version": data_version,
        "data_dates": data_dates,
        "immune_panel": {
            "source": "ImmPort gene lists current release",
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
        "cohorts": cohort_qc,
        "paths": {
            "immune_gene_panel_tsv": str(panel_path),
            "immune_terms_tsv": str(term_path),
        },
    }
    manifest_path = screen_dir / "manifest.json"
    write_json(manifest_path, manifest)

    raw_results_path = screen_dir / "results_long.raw.csv"
    r_input_path = screen_dir / "r_input.json"
    r_payload = {
        "screen_id": screen_id,
        "genes": [{"gene_symbol": row["gene_symbol"]} for row in panel_rows],
        "cohorts": cohort_payloads,
        "min_patients": args.min_patients,
        "min_events": args.min_events,
        "expression_scale": args.expression_scale,
        "output_csv_path": str(raw_results_path),
    }
    write_json(r_input_path, r_payload)

    if args.prepare_only:
        print(f"Prepared immune pan-cancer screen at {screen_dir}")
        return
    if args.force or not raw_results_path.exists():
        run_r_screen(args.r_script, r_input_path, timeout=args.timeout)

    results = read_long_results(raw_results_path)
    apply_global_statistics(results, args.fdr_threshold)

    long_results_path = screen_dir / "results_long.csv"
    write_table(long_results_path, results)

    gene_summary = build_gene_summary(panel_rows, results, args.fdr_threshold)
    apply_meta_fdr(gene_summary)
    gene_summary_path = screen_dir / "gene_summary.csv"
    write_table(gene_summary_path, gene_summary)

    cohort_summary = build_cohort_summary(results, cohort_qc, args.fdr_threshold)
    cohort_summary_path = screen_dir / "cohort_summary.csv"
    write_table(cohort_summary_path, cohort_summary)

    term_summary = build_term_summary(panel_terms, panel_rows, gene_summary, results, args.fdr_threshold)
    term_summary_path = screen_dir / "term_summary.csv"
    write_table(term_summary_path, term_summary)

    summary = build_screen_summary(
        screen_id=screen_id,
        manifest=manifest,
        results=results,
        gene_summary=gene_summary,
        cohort_summary=cohort_summary,
        term_summary=term_summary,
        paths={
            "manifest_json": manifest_path,
            "immune_gene_panel_tsv": panel_path,
            "immune_terms_tsv": term_path,
            "results_long_csv": long_results_path,
            "raw_results_long_csv": raw_results_path,
            "gene_summary_csv": gene_summary_path,
            "cohort_summary_csv": cohort_summary_path,
            "term_summary_csv": term_summary_path,
        },
    )
    summary_path = screen_dir / "screen_summary.json"
    write_json(summary_path, summary)
    write_methodology(screen_dir / "methodology.txt", summary, manifest)
    print(json.dumps(summary["headline"], indent=2, ensure_ascii=False))
    print(f"Artifacts: {screen_dir}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Screen immune genes across TCGA cancers with continuous Cox models.")
    parser.add_argument("--endpoint", choices=list(ENDPOINT_LABELS), default="OS")
    parser.add_argument(
        "--endpoint-mode",
        choices=["same_endpoint", "death_like", "progression_like", "best_available"],
        default="same_endpoint",
    )
    parser.add_argument("--expression-scale", choices=["log2_tpm", "log2_fpkm", "log2_fpkm_uq"], default="log2_tpm")
    parser.add_argument("--cohorts", default="", help="Comma-separated TCGA cohort IDs. Default: all cohorts.")
    parser.add_argument("--genes", default="", help="Comma-separated gene symbols. Default: all ImmPort immune genes.")
    parser.add_argument("--max-genes", type=int, default=0, help="Development limiter after panel sorting.")
    parser.add_argument("--filters-json", default="{}", help="AnalysisFilters JSON.")
    parser.add_argument("--min-patients", type=int, default=10)
    parser.add_argument("--min-events", type=int, default=5)
    parser.add_argument("--fdr-threshold", type=float, default=0.10)
    parser.add_argument("--screen-id", default="")
    parser.add_argument("--output-root", default="")
    parser.add_argument("--r-script", default=str(DEFAULT_R_SCRIPT))
    parser.add_argument("--timeout", type=int, default=0, help="R timeout in seconds; 0 disables timeout.")
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def parse_gene_list(raw: str) -> list[str]:
    return [item.strip().upper() for item in raw.split(",") if item.strip()]


def parse_cohort_list(raw: str) -> list[str]:
    return [item.strip().upper() for item in raw.split(",") if item.strip()]


def load_immport_panel(source_dir: Path) -> tuple[list[dict], list[dict], dict[str, str]]:
    source_dir.mkdir(parents=True, exist_ok=True)
    json_path = source_dir / "all_gene_lists.json"
    gmt_path = source_dir / "all_gene_lists.gmt"
    download_if_missing(IMMPORT_JSON_URL, json_path)
    download_if_missing(IMMPORT_GMT_URL, gmt_path)

    source_hashes = {
        "json_sha256": sha256_file(json_path),
        "gmt_sha256": sha256_file(gmt_path),
    }
    terms_json = json.loads(json_path.read_text(encoding="utf-8"))
    term_by_name_link = {
        (term["name"], term.get("link", "")): term
        for term in terms_json
    }
    term_by_name = {term["name"]: term for term in terms_json}
    term_rows: list[dict] = []
    genes_by_term: dict[str, set[str]] = {}
    terms_by_gene: dict[str, list[dict]] = defaultdict(list)

    for line in gmt_path.read_text(encoding="utf-8", errors="replace").splitlines():
        fields = line.rstrip("\n").split("\t")
        if len(fields) < 3:
            continue
        name, link, *genes = fields
        term = term_by_name_link.get((name, link)) or term_by_name.get(name) or {}
        term_id = term.get("id") or name
        source = term.get("source") or infer_term_source(term_id)
        normalized_genes = sorted({normalize_gene_symbol(gene) for gene in genes if normalize_gene_symbol(gene)})
        genes_by_term[term_id] = set(normalized_genes)
        term_row = {
            "term_id": term_id,
            "term_name": name,
            "source": source,
            "source_link": link,
            "source_count": term.get("count", len(normalized_genes)),
            "gene_count_in_gmt": len(normalized_genes),
        }
        term_rows.append(term_row)
        for gene in normalized_genes:
            terms_by_gene[gene].append(term_row)

    panel_rows = []
    for gene, gene_terms in terms_by_gene.items():
        unique_terms = sorted({term["term_id"]: term for term in gene_terms}.values(), key=lambda term: term["term_id"])
        source_counts = Counter(term["source"] for term in unique_terms)
        panel_rows.append(
            {
                "gene_symbol": gene,
                "source_list_count": len(unique_terms),
                "go_term_count": source_counts.get("GO", 0),
                "reactome_term_count": source_counts.get("Reactome", 0),
                "term_ids": "|".join(term["term_id"] for term in unique_terms),
                "term_names": "|".join(term["term_name"] for term in unique_terms),
                "term_sources": "|".join(term["source"] for term in unique_terms),
                "term_links": "|".join(term["source_link"] for term in unique_terms),
                "panel_note": "",
            }
        )
    return sorted(term_rows, key=lambda row: (row["source"], row["term_name"])), sorted(panel_rows, key=lambda row: row["gene_symbol"]), source_hashes


def download_if_missing(url: str, path: Path) -> None:
    if path.exists() and path.stat().st_size > 0:
        return
    with urllib.request.urlopen(url, timeout=120) as response:
        path.write_bytes(response.read())


def normalize_gene_symbol(value: str) -> str:
    return value.strip().upper()


def infer_term_source(term_id: str) -> str:
    if term_id.startswith("GO:"):
        return "GO"
    if term_id.startswith("R-HSA-"):
        return "Reactome"
    return "unknown"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def prepare_cohorts(
    db,
    settings,
    screen_dir: Path,
    requested_cohorts: list[str],
    endpoint: str,
    endpoint_mode: str,
    expression_scale: str,
    filters: AnalysisFilters,
) -> tuple[list[dict], list[dict]]:
    cohort_stmt = select(Cohort).order_by(Cohort.id)
    if requested_cohorts:
        cohort_stmt = cohort_stmt.where(Cohort.id.in_(requested_cohorts))
    cohorts = list(db.scalars(cohort_stmt).all())
    found = {cohort.id for cohort in cohorts}
    missing = [cohort_id for cohort_id in requested_cohorts if cohort_id not in found]
    if missing:
        raise SystemExit(f"Cohorts not found: {', '.join(missing)}")

    records_dir = screen_dir / "cohort_records"
    records_dir.mkdir(parents=True, exist_ok=True)
    cohort_payloads = []
    cohort_qc = []

    for cohort in cohorts:
        base = {
            "cohort": cohort.id,
            "cohort_label": cohort.id,
            "disease_type": cohort.disease_type,
            "primary_site": cohort.primary_site,
        }
        endpoint_option = choose_pancancer_endpoint(db, cohort.id, endpoint, endpoint_mode)
        if endpoint_option is None:
            cohort_qc.append({**base, "status": "skipped", "code": "ENDPOINT_UNAVAILABLE"})
            continue
        metadata_path = settings.derived_expression_dir / "matrices" / cohort.id / "metadata.json"
        if not metadata_path.exists():
            cohort_qc.append({**base, "status": "skipped", "code": "MATRIX_METADATA_MISSING", "endpoint": endpoint_option["value"]})
            continue
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        scale_info = metadata.get("scales", {}).get(expression_scale)
        if scale_info is None:
            cohort_qc.append({**base, "status": "skipped", "code": "EXPRESSION_SCALE_MISSING", "endpoint": endpoint_option["value"]})
            continue
        matrix_path = metadata_path.parent / scale_info["file"]
        if not matrix_path.exists():
            cohort_qc.append({**base, "status": "skipped", "code": "EXPRESSION_MATRIX_MISSING", "endpoint": endpoint_option["value"]})
            continue

        endpoint_by_patient, selected_option = selected_endpoint_outcomes(db, cohort.id, endpoint_option["value"])
        samples = list(db.scalars(select(Sample).where(Sample.cohort == cohort.id)).all())
        filtered, warnings, sample_selection = filter_samples(
            samples,
            filters,
            endpoint_by_patient=endpoint_by_patient,
            endpoint=selected_option["value"],
            endpoint_label=selected_option["label"],
        )
        records = survival_records_without_expression(filtered, endpoint_by_patient)
        records_path = records_dir / f"{cohort.id}.records.csv"
        write_table(records_path, records, fieldnames=[
            "patient_id",
            "sample_barcode",
            "time_days",
            "event",
            "sample_type",
            "stage",
            "gender",
            "race",
            "age_at_index",
        ])
        cohort_payloads.append(
            {
                **base,
                "endpoint": selected_option["value"],
                "endpoint_label": selected_option["label"],
                "endpoint_source": selected_option["source"],
                "records_csv_path": str(records_path),
                "metadata_path": str(metadata_path),
                "matrix_path": str(matrix_path),
                "sample_selection": sample_selection,
                "warnings": warnings,
            }
        )
        cohort_qc.append(
            {
                **base,
                "status": "prepared",
                "endpoint": selected_option["value"],
                "endpoint_label": selected_option["label"],
                "endpoint_source": selected_option["source"],
                "retained_patients": sample_selection["retained_patients"],
                "records": len(records),
                "warnings": warnings,
            }
        )
    return cohort_payloads, cohort_qc


def survival_records_without_expression(samples: list[Sample], endpoint_by_patient: dict | None) -> list[dict]:
    records = []
    for sample in samples:
        outcome = endpoint_by_patient.get(sample.patient_id) if endpoint_by_patient is not None else sample_os_outcome(sample)
        if outcome is None:
            continue
        records.append(
            {
                "patient_id": sample.patient_id,
                "sample_barcode": sample.barcode,
                "time_days": float(outcome.time_days),
                "event": int(outcome.event),
                "sample_type": sample.sample_type,
                "stage": sample.stage,
                "gender": sample.gender,
                "race": sample.race,
                "age_at_index": sample.age_at_index,
            }
        )
    return records


def run_r_screen(r_script: str, input_path: Path, timeout: int) -> None:
    result = subprocess.run(
        ["Rscript", r_script, str(input_path)],
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout or None,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Rscript failed: {result.stderr or result.stdout}")


def read_long_results(path: Path) -> list[dict]:
    rows = list(csv.DictReader(path.open(newline="", encoding="utf-8")))
    for row in rows:
        for field in LONG_NUMERIC_FIELDS:
            row[field] = parse_number(row.get(field))
    return rows


def apply_global_statistics(rows: list[dict], fdr_threshold: float) -> None:
    fdr_values = adjust_p_values_bh(
        [
            row.get("p_value")
            if row.get("status") == "completed"
            else None
            for row in rows
        ]
    )
    for row, fdr in zip(rows, fdr_values):
        row["global_fdr"] = fdr
        row["fdr"] = fdr
        hazard_ratio = parse_number(row.get("hazard_ratio"))
        if hazard_ratio is None:
            row["direction"] = "not_evaluable"
            row["effect_category"] = "not_evaluable"
            row["significant"] = False
            continue
        direction = "harmful" if hazard_ratio > 1 else "protective" if hazard_ratio < 1 else "neutral"
        significant = fdr is not None and fdr <= fdr_threshold
        row["direction"] = direction
        row["effect_category"] = direction if significant else "neutral"
        row["significant"] = significant


def build_gene_summary(panel_rows: list[dict], results: list[dict], fdr_threshold: float) -> list[dict]:
    by_gene: dict[str, list[dict]] = defaultdict(list)
    for row in results:
        by_gene[row["gene_symbol"]].append(row)
    panel_by_gene = {row["gene_symbol"]: row for row in panel_rows}
    summaries = []
    for gene in sorted(panel_by_gene):
        gene_rows = by_gene.get(gene, [])
        completed = [row for row in gene_rows if row.get("status") == "completed"]
        nominal = [row for row in completed if is_threshold(row.get("p_value"), 0.05)]
        fdr_hits = [row for row in completed if is_threshold(row.get("global_fdr"), fdr_threshold)]
        meta = meta_analysis_from_rows(completed)
        random = meta.get("random_effect") if meta.get("available") else {}
        heterogeneity = meta.get("heterogeneity") if meta.get("available") else {}
        best = top_significance_row(completed)
        strongest = top_effect_row(completed)
        row = {
            **panel_by_gene[gene],
            "tested_cohorts": len(gene_rows),
            "completed_cohorts": len(completed),
            "nominal_hits": len(nominal),
            "global_fdr_hits": len(fdr_hits),
            "harmful_nominal_hits": count_direction(nominal, "harmful"),
            "protective_nominal_hits": count_direction(nominal, "protective"),
            "harmful_global_fdr_hits": count_direction(fdr_hits, "harmful"),
            "protective_global_fdr_hits": count_direction(fdr_hits, "protective"),
            "min_p_value": min_finite(row.get("p_value") for row in completed),
            "min_global_fdr": min_finite(row.get("global_fdr") for row in completed),
            "top_cohort": best.get("cohort") if best else "",
            "top_cohort_direction": best.get("direction") if best else "",
            "top_cohort_hr": best.get("hazard_ratio") if best else None,
            "top_cohort_p_value": best.get("p_value") if best else None,
            "top_cohort_global_fdr": best.get("global_fdr") if best else None,
            "strongest_effect_cohort": strongest.get("cohort") if strongest else "",
            "strongest_effect_direction": strongest.get("direction") if strongest else "",
            "strongest_effect_hr": strongest.get("hazard_ratio") if strongest else None,
            "strongest_effect_p_value": strongest.get("p_value") if strongest else None,
            "meta_available": bool(meta.get("available")),
            "meta_model": meta.get("model", ""),
            "meta_log_hr": (random or {}).get("log_hr"),
            "meta_standard_error": (random or {}).get("standard_error"),
            "meta_hr": (random or {}).get("hazard_ratio"),
            "meta_hr_conf_low": (random or {}).get("hr_conf_low"),
            "meta_hr_conf_high": (random or {}).get("hr_conf_high"),
            "meta_p_value": (random or {}).get("p_value"),
            "meta_fdr": None,
            "meta_i_squared": (heterogeneity or {}).get("i_squared"),
            "meta_tau_squared": (heterogeneity or {}).get("tau_squared"),
        }
        summaries.append(row)
    return sorted(summaries, key=gene_sort_key)


def apply_meta_fdr(gene_summary: list[dict]) -> None:
    fdr_values = adjust_p_values_bh([row.get("meta_p_value") for row in gene_summary])
    for row, fdr in zip(gene_summary, fdr_values):
        row["meta_fdr"] = fdr
    gene_summary.sort(key=gene_sort_key)


def build_cohort_summary(results: list[dict], cohort_qc: list[dict], fdr_threshold: float) -> list[dict]:
    by_cohort: dict[str, list[dict]] = defaultdict(list)
    for row in results:
        by_cohort[row["cohort"]].append(row)
    qc_by_cohort = {row["cohort"]: row for row in cohort_qc}
    summaries = []
    for cohort, qc in sorted(qc_by_cohort.items()):
        rows = by_cohort.get(cohort, [])
        completed = [row for row in rows if row.get("status") == "completed"]
        nominal = [row for row in completed if is_threshold(row.get("p_value"), 0.05)]
        fdr_hits = [row for row in completed if is_threshold(row.get("global_fdr"), fdr_threshold)]
        best = top_significance_row(completed)
        summaries.append(
            {
                "cohort": cohort,
                "primary_site": qc.get("primary_site"),
                "disease_type": qc.get("disease_type"),
                "status": qc.get("status"),
                "endpoint": qc.get("endpoint"),
                "endpoint_label": qc.get("endpoint_label"),
                "endpoint_source": qc.get("endpoint_source"),
                "retained_patients": qc.get("retained_patients"),
                "tested_genes": len(rows),
                "completed_genes": len(completed),
                "nominal_hits": len(nominal),
                "global_fdr_hits": len(fdr_hits),
                "harmful_global_fdr_hits": count_direction(fdr_hits, "harmful"),
                "protective_global_fdr_hits": count_direction(fdr_hits, "protective"),
                "min_global_fdr": min_finite(row.get("global_fdr") for row in completed),
                "top_gene": best.get("gene_symbol") if best else "",
                "top_gene_direction": best.get("direction") if best else "",
                "top_gene_hr": best.get("hazard_ratio") if best else None,
                "top_gene_p_value": best.get("p_value") if best else None,
                "top_gene_global_fdr": best.get("global_fdr") if best else None,
            }
        )
    return summaries


def build_term_summary(
    panel_terms: list[dict],
    panel_rows: list[dict],
    gene_summary: list[dict],
    results: list[dict],
    fdr_threshold: float,
) -> list[dict]:
    gene_to_terms = {
        row["gene_symbol"]: [term for term in row["term_ids"].split("|") if term]
        for row in panel_rows
    }
    summary_by_gene = {row["gene_symbol"]: row for row in gene_summary}
    results_by_gene: dict[str, list[dict]] = defaultdict(list)
    for row in results:
        results_by_gene[row["gene_symbol"]].append(row)

    genes_by_term: dict[str, set[str]] = defaultdict(set)
    for gene, term_ids in gene_to_terms.items():
        for term_id in term_ids:
            genes_by_term[term_id].add(gene)

    term_meta = {row["term_id"]: row for row in panel_terms}
    term_rows = []
    for term_id, genes in sorted(genes_by_term.items()):
        summaries = [summary_by_gene[gene] for gene in genes if gene in summary_by_gene]
        completed_genes = [row for row in summaries if row.get("completed_cohorts", 0)]
        meta_hits = [row for row in completed_genes if is_threshold(row.get("meta_fdr"), fdr_threshold)]
        cohort_hits = []
        for gene in genes:
            cohort_hits.extend([row for row in results_by_gene.get(gene, []) if is_threshold(row.get("global_fdr"), fdr_threshold)])
        best_gene = top_gene_summary(completed_genes)
        meta = term_meta.get(term_id, {})
        term_rows.append(
            {
                "term_id": term_id,
                "term_name": meta.get("term_name", ""),
                "source": meta.get("source", ""),
                "source_link": meta.get("source_link", ""),
                "panel_genes": len(genes),
                "completed_genes": len(completed_genes),
                "meta_fdr_gene_hits": len(meta_hits),
                "cohort_level_global_fdr_hits": len(cohort_hits),
                "harmful_cohort_hits": count_direction(cohort_hits, "harmful"),
                "protective_cohort_hits": count_direction(cohort_hits, "protective"),
                "best_gene": best_gene.get("gene_symbol") if best_gene else "",
                "best_gene_meta_hr": best_gene.get("meta_hr") if best_gene else None,
                "best_gene_meta_fdr": best_gene.get("meta_fdr") if best_gene else None,
            }
        )
    return sorted(term_rows, key=lambda row: (nulls_last(row["best_gene_meta_fdr"]), -int(row["cohort_level_global_fdr_hits"]), row["term_name"]))


def build_screen_summary(
    screen_id: str,
    manifest: dict,
    results: list[dict],
    gene_summary: list[dict],
    cohort_summary: list[dict],
    term_summary: list[dict],
    paths: dict[str, Path],
) -> dict:
    completed = [row for row in results if row.get("status") == "completed"]
    global_hits = [row for row in completed if row.get("significant")]
    meta_hits = [row for row in gene_summary if is_threshold(row.get("meta_fdr"), manifest["request"]["fdr_threshold"])]
    top_gene_rows = sorted(gene_summary, key=gene_sort_key)[:25]
    top_cohort_rows = sorted(cohort_summary, key=lambda row: (nulls_last(row["min_global_fdr"]), row["cohort"]))[:15]
    top_term_rows = term_summary[:20]
    recurrence = build_recurrence_summary(results, gene_summary)
    return {
        "screen_id": screen_id,
        "headline": {
            "immune_genes": manifest["immune_panel"]["selected_gene_count"],
            "immune_terms": manifest["immune_panel"]["source_term_count"],
            "prepared_cohorts": sum(1 for row in manifest["cohorts"] if row.get("status") == "prepared"),
            "completed_gene_cohort_models": len(completed),
            "global_fdr_hits": len(global_hits),
            "meta_fdr_gene_hits": len(meta_hits),
            "fdr_threshold": manifest["request"]["fdr_threshold"],
        },
        "top_genes": top_gene_rows,
        "top_cohorts": top_cohort_rows,
        "top_terms": top_term_rows,
        "recurrence": recurrence,
        "status_counts": dict(Counter(row.get("status", "unknown") for row in results)),
        "direction_counts_global_fdr": dict(Counter(row.get("direction") for row in global_hits)),
        "paths": {key: str(value) for key, value in paths.items()},
        "method_notes": [
            "Each model is Cox proportional hazards with log2(TPM + 1) expression z-scored within cohort.",
            "Global FDR is Benjamini-Hochberg across completed gene-cohort tests.",
            "Gene-level meta-analysis uses DerSimonian-Laird random effects over completed cohort estimates.",
            "The screen is association analysis, not causal inference; tumor purity, immune infiltration and treatment are not adjusted here.",
        ],
    }


def build_recurrence_summary(results: list[dict], gene_summary: list[dict]) -> dict:
    gene_lookup = {row["gene_symbol"]: row for row in gene_summary}
    by_gene: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "harmful": [],
            "protective": [],
            "min_harmful_fdr": None,
            "min_protective_fdr": None,
        }
    )
    for row in results:
        if not row.get("significant"):
            continue
        direction = row.get("direction")
        if direction not in {"harmful", "protective"}:
            continue
        gene = row.get("gene_symbol")
        if not gene:
            continue
        fdr = parse_number(row.get("global_fdr"))
        entry = {
            "cohort": row.get("cohort"),
            "hazard_ratio": row.get("hazard_ratio"),
            "global_fdr": fdr,
            "p_value": row.get("p_value"),
        }
        by_gene[gene][direction].append(entry)
        key = f"min_{direction}_fdr"
        current = by_gene[gene][key]
        if fdr is not None and (current is None or fdr < current):
            by_gene[gene][key] = fdr

    recurrent_rows = []
    harmful_distribution = Counter()
    protective_distribution = Counter()
    for gene, entry in by_gene.items():
        harmful_count = len(entry["harmful"])
        protective_count = len(entry["protective"])
        if harmful_count:
            harmful_distribution[harmful_count] += 1
        if protective_count:
            protective_distribution[protective_count] += 1
        recurrent_rows.append(
            recurrence_gene_row(
                gene=gene,
                entry=entry,
                summary=gene_lookup.get(gene, {}),
            )
        )

    frequency_distribution = [
        {
            "cancer_count": cancer_count,
            "harmful_genes": harmful_distribution.get(cancer_count, 0),
            "protective_genes": protective_distribution.get(cancer_count, 0),
        }
        for cancer_count in range(1, max([0, *harmful_distribution, *protective_distribution]) + 1)
    ]
    top_harmful = sorted(
        [row for row in recurrent_rows if row["harmful_cancer_count"]],
        key=lambda row: (-row["harmful_cancer_count"], nulls_last(row["min_harmful_fdr"]), row["gene_symbol"]),
    )[:30]
    top_protective = sorted(
        [row for row in recurrent_rows if row["protective_cancer_count"]],
        key=lambda row: (-row["protective_cancer_count"], nulls_last(row["min_protective_fdr"]), row["gene_symbol"]),
    )[:30]
    rare_harmful = sorted(
        [
            row
            for row in recurrent_rows
            if row["harmful_cancer_count"] == 1 and row["protective_cancer_count"] == 0
        ],
        key=lambda row: (nulls_last(row["min_harmful_fdr"]), row["gene_symbol"]),
    )[:25]
    rare_protective = sorted(
        [
            row
            for row in recurrent_rows
            if row["protective_cancer_count"] == 1 and row["harmful_cancer_count"] == 0
        ],
        key=lambda row: (nulls_last(row["min_protective_fdr"]), row["gene_symbol"]),
    )[:25]
    mixed_direction = sorted(
        [
            row
            for row in recurrent_rows
            if row["harmful_cancer_count"] and row["protective_cancer_count"]
        ],
        key=lambda row: (-(row["harmful_cancer_count"] + row["protective_cancer_count"]), nulls_last(row["min_directional_fdr"]), row["gene_symbol"]),
    )[:25]

    return {
        "summary": {
            "genes_with_any_global_hit": len(recurrent_rows),
            "genes_with_harmful_hit": sum(1 for row in recurrent_rows if row["harmful_cancer_count"]),
            "genes_with_protective_hit": sum(1 for row in recurrent_rows if row["protective_cancer_count"]),
            "recurrent_harmful_genes_ge5": sum(1 for row in recurrent_rows if row["harmful_cancer_count"] >= 5),
            "recurrent_protective_genes_ge5": sum(1 for row in recurrent_rows if row["protective_cancer_count"] >= 5),
            "one_cancer_harmful_genes": sum(1 for row in recurrent_rows if row["harmful_cancer_count"] == 1),
            "one_cancer_protective_genes": sum(1 for row in recurrent_rows if row["protective_cancer_count"] == 1),
        },
        "frequency_distribution": frequency_distribution,
        "top_harmful": top_harmful,
        "top_protective": top_protective,
        "rare_harmful": rare_harmful,
        "rare_protective": rare_protective,
        "mixed_direction": mixed_direction,
    }


def recurrence_gene_row(gene: str, entry: dict[str, Any], summary: dict[str, Any]) -> dict:
    harmful = sorted(entry["harmful"], key=lambda row: (nulls_last(row.get("global_fdr")), row.get("cohort") or ""))
    protective = sorted(entry["protective"], key=lambda row: (nulls_last(row.get("global_fdr")), row.get("cohort") or ""))
    min_harmful = entry.get("min_harmful_fdr")
    min_protective = entry.get("min_protective_fdr")
    min_directional = min_finite([min_harmful, min_protective])
    return {
        "gene_symbol": gene,
        "harmful_cancer_count": len(harmful),
        "protective_cancer_count": len(protective),
        "total_directional_cancer_count": len(harmful) + len(protective),
        "min_harmful_fdr": min_harmful,
        "min_protective_fdr": min_protective,
        "min_directional_fdr": min_directional,
        "harmful_cohorts": [row["cohort"] for row in harmful if row.get("cohort")],
        "protective_cohorts": [row["cohort"] for row in protective if row.get("cohort")],
        "top_harmful_cohort": harmful[0]["cohort"] if harmful else "",
        "top_protective_cohort": protective[0]["cohort"] if protective else "",
        "top_harmful_hr": harmful[0].get("hazard_ratio") if harmful else None,
        "top_protective_hr": protective[0].get("hazard_ratio") if protective else None,
        "meta_hr": summary.get("meta_hr"),
        "meta_fdr": summary.get("meta_fdr"),
        "meta_i_squared": summary.get("meta_i_squared"),
        "source_list_count": summary.get("source_list_count"),
        "term_names": summary.get("term_names"),
    }


def write_methodology(path: Path, summary: dict, manifest: dict) -> None:
    lines = [
        "Immune pan-cancer Cox screen",
        "",
        f"Screen ID: {summary['screen_id']}",
        f"Created at: {manifest['created_at']}",
        f"ImmPort GMT: {manifest['immune_panel']['gmt_url']}",
        f"ImmPort JSON: {manifest['immune_panel']['json_url']}",
        f"Selected immune genes: {manifest['immune_panel']['selected_gene_count']}",
        f"Source immune terms: {manifest['immune_panel']['source_term_count']}",
        f"Endpoint request: {manifest['request']['endpoint']} ({manifest['request']['endpoint_mode']})",
        f"Expression scale: {manifest['request']['expression_scale']}",
        f"Minimum patients/events: {manifest['request']['min_patients']}/{manifest['request']['min_events']}",
        f"FDR threshold: {manifest['request']['fdr_threshold']}",
        "",
        "Statistics:",
        "For each gene and cohort, expression is z-scored among retained patients and modeled as a continuous covariate in Cox proportional hazards regression.",
        "FDR is controlled globally across all completed gene-cohort Cox tests using Benjamini-Hochberg.",
        "Gene summaries include random-effects meta-analysis across evaluable cohorts.",
        "",
        "Interpretation guardrails:",
        "These are univariable survival associations. They should be treated as hypothesis-generating until adjusted for clinical covariates, tumor purity, immune composition and treatment context.",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def top_effect_row(rows: list[dict]) -> dict:
    if not rows:
        return {}
    return max(rows, key=lambda row: abs(float(row.get("log_hr") or 0.0)))


def top_significance_row(rows: list[dict]) -> dict:
    finite = [row for row in rows if row.get("p_value") is not None]
    if not finite:
        return {}
    return min(finite, key=lambda row: float(row["p_value"]))


def top_gene_summary(rows: list[dict]) -> dict:
    finite = [row for row in rows if row.get("meta_fdr") is not None]
    if not finite:
        return {}
    return min(finite, key=lambda row: float(row["meta_fdr"]))


def gene_sort_key(row: dict) -> tuple:
    return (
        nulls_last(row.get("meta_fdr")),
        nulls_last(row.get("min_global_fdr")),
        -(int(row.get("global_fdr_hits") or 0)),
        row.get("gene_symbol", ""),
    )


def nulls_last(value: Any) -> float:
    number = parse_number(value)
    return number if number is not None else float("inf")


def count_direction(rows: list[dict], direction: str) -> int:
    return sum(1 for row in rows if row.get("direction") == direction)


def min_finite(values) -> float | None:
    finite = [float(value) for value in values if value is not None and math.isfinite(float(value))]
    return min(finite) if finite else None


def is_threshold(value: Any, threshold: float) -> bool:
    number = parse_number(value)
    return number is not None and number <= threshold


def parse_number(value: Any) -> float | int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value if math.isfinite(float(value)) else None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return int(number) if number.is_integer() else number


def write_table(path: Path, rows: list[dict], fieldnames: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fieldnames is None:
        fieldnames = []
        for row in rows:
            for key in row:
                if key not in fieldnames:
                    fieldnames.append(key)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore", delimiter="\t" if path.suffix == ".tsv" else ",")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: serialize_cell(row.get(field)) for field in fieldnames})


def serialize_cell(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float) and not math.isfinite(value):
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(json_safe(value), ensure_ascii=False, separators=(",", ":"))
    return value


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(json_safe(payload), ensure_ascii=False, allow_nan=False, indent=2), encoding="utf-8")


def json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [json_safe(item) for item in value]
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    return value


if __name__ == "__main__":
    main()
