#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
import re
import shutil
import struct
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


COHORT = "TCGA-KIRC"
MISSING = {"", "NA", "N/A", "NULL", "null", "None", "not reported", "Not Reported", "--"}

SAMPLE_CODE_PRIORITY = {
    "01": 0,
    "03": 0,
    "09": 0,
    "02": 10,
    "04": 10,
    "40": 10,
    "05": 20,
    "06": 30,
    "07": 30,
    "08": 40,
    "10": 80,
    "11": 80,
    "12": 80,
    "13": 80,
    "14": 80,
    "20": 90,
    "50": 90,
    "60": 90,
    "61": 90,
}
SAMPLE_TYPE_PRIORITY = {
    "primary tumor": 0,
    "primary solid tumor": 0,
    "primary blood derived cancer - peripheral blood": 0,
    "primary blood derived cancer - bone marrow": 0,
    "recurrent tumor": 10,
    "recurrent solid tumor": 10,
    "recurrent blood derived cancer - peripheral blood": 10,
    "recurrent blood derived cancer - bone marrow": 10,
    "additional - new primary": 20,
    "metastatic": 30,
    "additional metastatic": 30,
    "human tumor original cells": 40,
    "blood derived normal": 80,
    "solid tissue normal": 80,
    "buccal cell normal": 80,
    "ebv immortalized normal": 80,
    "bone marrow normal": 80,
    "control analyte": 90,
    "cell lines": 90,
    "primary xenograft tissue": 90,
    "cell line derived xenograft": 90,
    "cell line derived xenograft tissue": 90,
}

SIGNATURES: list[tuple[str, str, list[str]]] = [
    ("Trm", "CD4 Trm signature", ["CD4", "CD69", "CXCR6", "ITGA1", "CXCL13"]),
    ("Tcirc", "CD4 Tcirc signature", ["CD4", "GZMB", "CX3CR1"]),
    (
        "HLA-DR",
        "HLA-DR signature",
        ["HLA-DRA", "HLA-DRB1", "HLA-DRB5", "HLA-DRB6", "HLA-DRB9"],
    ),
    ("HLA-DP", "HLA-DP signature", ["HLA-DPA1", "HLA-DPA2", "HLA-DPA3", "HLA-DPB1", "HLA-DPB2"]),
    ("HLA-DQ", "HLA-DQ signature", ["HLA-DQA1", "HLA-DQA2", "HLA-DQB1", "HLA-DQB2", "HLA-DQB3"]),
    ("CXCL10_CXCR3", "CXCL10/CXCR3 axis", ["CXCL10", "CXCR3"]),
    ("CCL3_CCL4_CCR5", "CCL3-CCL4/CCR5 axis", ["CCL3", "CCL4", "CCR5"]),
    ("CX3CL1_CX3CR1", "CX3CL1/CX3CR1 axis", ["CX3CL1", "CX3CR1"]),
]


@dataclass(frozen=True)
class Sample:
    patient_id: str
    barcode: str
    sample_type: str | None
    stage: str | None
    grade: str | None
    gender: str | None
    race: str | None
    age_at_index: float | None
    vital_status: str | None
    time_days: float
    event: int


@dataclass(frozen=True)
class AnalysisSpec:
    analysis_id: str
    analysis_type: str
    label: str
    genes: list[str]


def clean(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return None if text in MISSING else text


def parse_float(value: Any) -> float | None:
    text = clean(value)
    if text is None:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def normalize_stage(row: dict[str, str]) -> str | None:
    stage = clean(row.get("ajcc_pathologic_stage")) or clean(row.get("paper_pathologic_stage")) or clean(row.get("figo_stage"))
    return stage.replace("_", " ") if stage else None


def normalize_grade(row: dict[str, str]) -> str | None:
    grade = (
        clean(row.get("tumor_grade"))
        or clean(row.get("paper_Tumor_Grade"))
        or clean(row.get("paper_Grade"))
        or clean(row.get("paper_Histologic.grade"))
        or clean(row.get("paper_FNCLCC.grade"))
        or clean(row.get("paper_histology_grade"))
        or clean(row.get("tumor_grade_category"))
        or clean(row.get("gleason_grade_group"))
        or clean(row.get("primary_gleason_grade"))
    )
    return grade.replace("_", " ") if grade else None


def derive_os(row: dict[str, str]) -> tuple[float | None, int | None]:
    vital = (clean(row.get("vital_status")) or "").lower()
    days_to_death = parse_float(row.get("days_to_death"))
    days_to_follow_up = parse_float(row.get("days_to_last_follow_up"))
    days_to_last_known = parse_float(row.get("days_to_last_known_disease_status"))

    if vital == "dead":
        event = 1
        time_days = days_to_death or days_to_follow_up or days_to_last_known
    elif vital == "alive":
        event = 0
        time_days = days_to_follow_up or days_to_last_known
    else:
        event = None
        time_days = days_to_death or days_to_follow_up or days_to_last_known

    if time_days is None or time_days <= 0:
        return None, None
    return time_days, event


def read_samples(col_data_path: Path) -> list[Sample]:
    samples: list[Sample] = []
    with col_data_path.open(newline="", encoding="utf-8", errors="replace") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        for row in reader:
            barcode = clean(row.get("")) or clean(row.get("barcode"))
            patient_id = clean(row.get("patient_id")) or clean(row.get("patient")) or (barcode[:12] if barcode else None)
            if barcode is None or patient_id is None:
                continue
            time_days, event = derive_os(row)
            if time_days is None or event is None:
                continue
            samples.append(
                Sample(
                    patient_id=patient_id,
                    barcode=barcode,
                    sample_type=clean(row.get("sample_type")),
                    stage=normalize_stage(row),
                    grade=normalize_grade(row),
                    gender=clean(row.get("gender")) or clean(row.get("sex_at_birth")),
                    race=clean(row.get("race")),
                    age_at_index=parse_float(row.get("age_at_index")),
                    vital_status=clean(row.get("vital_status")),
                    time_days=float(time_days),
                    event=int(event),
                )
            )
    return samples


def select_one_sample_per_patient(samples: list[Sample]) -> tuple[list[Sample], dict[str, Any]]:
    selected: dict[str, Sample] = {}
    duplicates = 0
    for sample in sorted(samples, key=sample_selection_key):
        if sample.patient_id in selected:
            duplicates += 1
            continue
        selected[sample.patient_id] = sample
    retained = list(selected.values())
    return retained, {
        "input_samples_with_os": len(samples),
        "retained_patients": len(retained),
        "duplicate_samples_removed": duplicates,
        "retained_sample_types": count_by(lambda sample: sample.sample_type or "Unknown", retained),
    }


def sample_selection_key(sample: Sample) -> tuple[int, int, int, str]:
    return (sample_priority(sample), analyte_priority(sample.barcode), portion_priority(sample.barcode), sample.barcode)


def sample_priority(sample: Sample) -> int:
    code = tcga_sample_code(sample.barcode)
    if code in SAMPLE_CODE_PRIORITY:
        return SAMPLE_CODE_PRIORITY[code]
    return SAMPLE_TYPE_PRIORITY.get((sample.sample_type or "").strip().lower(), 99)


def tcga_sample_code(barcode: str | None) -> str | None:
    if not barcode:
        return None
    parts = barcode.split("-")
    if len(parts) < 4:
        return None
    candidate = parts[3][:2]
    return candidate if len(candidate) == 2 and candidate.isdigit() else None


def analyte_priority(barcode: str | None) -> int:
    if not barcode:
        return 9
    parts = barcode.split("-")
    if len(parts) < 5 or not parts[4]:
        return 5
    return {"R": 0, "T": 1, "H": 2}.get(parts[4][-1].upper(), 8)


def portion_priority(barcode: str | None) -> int:
    if not barcode:
        return 99
    parts = barcode.split("-")
    if len(parts) < 5:
        return 99
    portion = parts[4][:2]
    return int(portion) if portion.isdigit() else 99


def count_by(get_key, samples: list[Sample]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for sample in samples:
        key = get_key(sample)
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def load_matrix_metadata(derived_expression_dir: Path, cohort: str) -> dict[str, Any]:
    path = derived_expression_dir / "matrices" / cohort / "metadata.json"
    if not path.exists():
        raise FileNotFoundError(f"Derived expression metadata not found: {path}")
    metadata = json.loads(path.read_text(encoding="utf-8"))
    if metadata.get("status") != "ready":
        raise ValueError(f"Derived expression metadata is not ready: {path}")
    return metadata


def read_gene_expression(derived_expression_dir: Path, metadata: dict[str, Any], gene: str, scale: str) -> dict[str, float] | None:
    row_index = (metadata.get("gene_to_row") or {}).get(gene.upper())
    if row_index is None:
        return None
    scale_info = (metadata.get("scales") or {}).get(scale)
    if scale_info is None:
        raise ValueError(f"Expression scale {scale} not present in derived matrix metadata.")

    barcodes = metadata["barcodes"]
    sample_count = int(metadata["sample_count"])
    matrix_path = derived_expression_dir / "matrices" / metadata["cohort"] / scale_info["file"]
    with matrix_path.open("rb") as handle:
        handle.seek(int(row_index) * sample_count * 4)
        raw = handle.read(sample_count * 4)
    values = struct.unpack(f"<{sample_count}f", raw)
    return {barcode: float(value) for barcode, value in zip(barcodes, values, strict=False)}


def build_analysis_specs() -> list[AnalysisSpec]:
    specs = [
        AnalysisSpec(analysis_id=safe_name(name), analysis_type="signature", label=label, genes=genes)
        for name, label, genes in SIGNATURES
    ]
    seen: set[str] = set()
    individual_genes: list[str] = []
    for _, _, genes in SIGNATURES:
        for gene in genes:
            if gene not in seen:
                seen.add(gene)
                individual_genes.append(gene)
    specs.extend(
        AnalysisSpec(analysis_id=safe_name(gene), analysis_type="individual_gene", label=gene, genes=[gene])
        for gene in individual_genes
    )
    return specs


def safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._") or "analysis"


def build_records(samples: list[Sample], gene_values: list[dict[str, float]], spec: AnalysisSpec) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for sample in samples:
        values = [expression[sample.barcode] for expression in gene_values if sample.barcode in expression]
        if len(values) != len(gene_values):
            continue
        expression_value = sum(values) / len(values)
        if not math.isfinite(expression_value):
            continue
        records.append(
            {
                "patient_id": sample.patient_id,
                "sample_barcode": sample.barcode,
                "endpoint": "OS",
                "expression_value": expression_value,
                "group": None,
                "time_days": sample.time_days,
                "event": sample.event,
                "os_time_days": sample.time_days,
                "os_event": sample.event,
                "sample_type": sample.sample_type,
                "stage": sample.stage,
                "grade": sample.grade,
                "gender": sample.gender,
                "race": sample.race,
                "age_at_index": sample.age_at_index,
                "analysis_id": spec.analysis_id,
                "analysis_type": spec.analysis_type,
                "analysis_label": spec.label,
            }
        )
    return records


def compute_maxstat(
    records: list[dict[str, Any]],
    spec: AnalysisSpec,
    args: argparse.Namespace,
    paths: dict[str, Path],
) -> dict[str, Any]:
    input_path = paths["inputs"] / f"{spec.analysis_id}.maxstat_input.json"
    output_path = paths["inputs"] / f"{spec.analysis_id}.maxstat_output.json"
    payload = {
        "records": [
            {
                "patient_id": record["patient_id"],
                "expression_value": record["expression_value"],
                "time_days": record["time_days"],
                "event": record["event"],
                "os_time_days": record["os_time_days"],
                "os_event": record["os_event"],
            }
            for record in records
        ],
        "output_path": str(output_path),
        "minprop": args.maxstat_minprop,
    }
    write_json(input_path, payload)
    run_command([args.rscript_bin, str(args.maxstat_script_path), str(input_path)], paths["logs"] / f"{spec.analysis_id}.log")
    return json.loads(output_path.read_text(encoding="utf-8"))


def run_km(
    records: list[dict[str, Any]],
    cutpoint: dict[str, Any],
    spec: AnalysisSpec,
    args: argparse.Namespace,
    paths: dict[str, Path],
) -> dict[str, Any]:
    threshold = float(cutpoint["threshold"])
    grouped = []
    for record in records:
        updated = dict(record)
        updated["group"] = "Low" if float(record["expression_value"]) <= threshold else "High"
        grouped.append(updated)

    analysis_dir = paths["signatures" if spec.analysis_type == "signature" else "individual_genes"] / spec.analysis_id
    analysis_dir.mkdir(parents=True, exist_ok=True)
    records_csv_path = paths["inputs"] / f"{spec.analysis_id}.records.csv"
    write_records_csv(records_csv_path, grouped)

    payload_path = paths["inputs"] / f"{spec.analysis_id}.km_input.json"
    metrics_path = analysis_dir / f"{spec.analysis_id}.metrics.json"
    payload = {
        "cohort": COHORT,
        "gene_symbol": spec.label,
        "endpoint": "OS",
        "endpoint_label": "Overall survival",
        "expression_scale": args.expression_scale,
        "expression_scale_label": "Mean log2(TPM + 1)" if len(spec.genes) > 1 else "log2(TPM + 1)",
        "records": grouped,
        "group_levels": ["Low", "High"],
        "cutpoint_details": cutpoint,
        "time_unit": args.time_unit,
        "show_confidence_interval": args.show_confidence_interval,
        "show_risk_table": args.show_risk_table,
        "render_png": True,
        "render_svg": True,
        "plot_style": {
            "palette": ["#1f77b4", "#d62728"],
            "font_family": "sans",
            "base_font_size": 12,
            "axis_text_size": 11,
            "axis_title_size": 12,
            "show_grid": False,
            "show_title": True,
            "plot_aspect": "square",
            "plot_title": f"{COHORT} {spec.label} OS",
        },
        "png_path": str(analysis_dir / f"{spec.analysis_id}.km.png"),
        "svg_path": str(analysis_dir / f"{spec.analysis_id}.km.svg"),
        "cox_forest_png_path": str(analysis_dir / f"{spec.analysis_id}.cox_forest.png"),
        "cox_forest_svg_path": str(analysis_dir / f"{spec.analysis_id}.cox_forest.svg"),
        "output_path": str(metrics_path),
    }
    write_json(payload_path, payload)
    run_command([args.rscript_bin, str(args.km_script_path), str(payload_path)], paths["logs"] / f"{spec.analysis_id}.log")
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    methods_path = analysis_dir / f"{spec.analysis_id}.methods.json"
    write_json(
        methods_path,
        {
            "analysis_id": spec.analysis_id,
            "analysis_type": spec.analysis_type,
            "label": spec.label,
            "genes": spec.genes,
            "expression_score": "mean log2(TPM + 1)" if len(spec.genes) > 1 else "log2(TPM + 1)",
            "cutpoint": cutpoint,
            "records_csv": str(records_csv_path),
            "metrics_json": str(metrics_path),
        },
    )
    return metrics


def run_command(command: list[str], log_path: Path) -> None:
    with log_path.open("a", encoding="utf-8") as log:
        log.write("\n$ " + " ".join(command) + "\n")
        started = time.time()
        result = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        log.write(result.stdout)
        log.write(f"\nexit_code={result.returncode} elapsed_seconds={time.time() - started:.3f}\n")
    if result.returncode != 0:
        raise RuntimeError(f"Command failed with exit code {result.returncode}: {' '.join(command)}")


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def write_records_csv(path: Path, records: list[dict[str, Any]]) -> None:
    if not records:
        return
    fields = [
        "patient_id",
        "sample_barcode",
        "endpoint",
        "expression_value",
        "group",
        "time_days",
        "event",
        "sample_type",
        "stage",
        "grade",
        "gender",
        "race",
        "age_at_index",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for record in records:
            writer.writerow({field: record.get(field) for field in fields})


def write_tables(paths: dict[str, Path], summary_rows: list[dict[str, Any]], cox_rows: list[dict[str, Any]], km_rows: list[dict[str, Any]], skipped_rows: list[dict[str, Any]]) -> None:
    write_csv(paths["tables"] / "summary_all_results.csv", summary_rows)
    write_csv(paths["tables"] / "cox_models_all.csv", cox_rows)
    write_csv(paths["tables"] / "km_logrank_all.csv", km_rows)
    write_csv(paths["tables"] / "missing_or_skipped.csv", skipped_rows)


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: serialize_cell(row.get(field)) for field in fields})


def serialize_cell(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True)
    return value


def summarize_metrics(spec: AnalysisSpec, metrics: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    base = {
        "analysis_id": spec.analysis_id,
        "analysis_type": spec.analysis_type,
        "label": spec.label,
        "genes": ";".join(spec.genes),
        "n_genes": len(spec.genes),
        "n_patients": metrics.get("n_patients"),
        "n_events": metrics.get("n_events"),
        "logrank_p_value": metrics.get("logrank_p_value"),
        "threshold": (metrics.get("cutpoint_details") or {}).get("threshold"),
        "group_counts": metrics.get("group_counts"),
        "event_counts": metrics.get("event_counts"),
        "median_survival_days": metrics.get("median_survival_days"),
    }
    cox_rows: list[dict[str, Any]] = []
    for model in metrics.get("cox_models") or []:
        cox_rows.append(
            {
                "analysis_id": spec.analysis_id,
                "analysis_type": spec.analysis_type,
                "label": spec.label,
                "model": model.get("model"),
                "model_label": model.get("label"),
                "status": model.get("status"),
                "reason": model.get("reason"),
                "covariates": model.get("covariates"),
                "contrast": model.get("contrast"),
                "n_patients": model.get("n_patients"),
                "n_events": model.get("n_events"),
                "hazard_ratio": model.get("hazard_ratio"),
                "hr_conf_low": model.get("hr_conf_low"),
                "hr_conf_high": model.get("hr_conf_high"),
                "p_value": model.get("p_value"),
                "warnings": model.get("warnings"),
            }
        )
        if model.get("status") == "completed":
            suffix = model.get("model")
            base[f"{suffix}_hr"] = model.get("hazard_ratio")
            base[f"{suffix}_p_value"] = model.get("p_value")
    km_row = {
        "analysis_id": spec.analysis_id,
        "analysis_type": spec.analysis_type,
        "label": spec.label,
        "genes": ";".join(spec.genes),
        "n_patients": metrics.get("n_patients"),
        "n_events": metrics.get("n_events"),
        "logrank_p_value": metrics.get("logrank_p_value"),
        "threshold": (metrics.get("cutpoint_details") or {}).get("threshold"),
        "group_counts": metrics.get("group_counts"),
        "event_counts": metrics.get("event_counts"),
    }
    return base, cox_rows, km_row


def write_methods(paths: dict[str, Path], args: argparse.Namespace, sample_summary: dict[str, Any], specs: list[AnalysisSpec], skipped_rows: list[dict[str, Any]]) -> None:
    methods = {
        "title": "TCGA-KIRC headless survival analyses",
        "cohort": COHORT,
        "endpoint": "Overall survival",
        "expression_scale": "log2(TPM + 1)",
        "signature_score": "Mean of member genes on log2(TPM + 1) scale",
        "km_cutpoint": f"survminer::surv_cutpoint maxstat, minprop={args.maxstat_minprop}",
        "cox_models": [
            "Surv(OS days, event) ~ expression_group",
            "Surv(OS days, event) ~ expression_group + stage",
            "Surv(OS days, event) ~ expression_group + grade",
            "Surv(OS days, event) ~ expression_group + stage + grade",
        ],
        "sample_selection": "One RNA-seq sample per TCGA participant using TCGA biospecimen priority; all KIRC stages retained.",
        "document_gene_note": "Document text listed HLA-BQB2 for HLA-DQ; this run uses HLA-DQB2 because HLA-BQB2 is absent and HLA-DQB2 is present in TCGA-KIRC.",
        "sample_summary": sample_summary,
        "analysis_count": len(specs),
        "skipped_count": len(skipped_rows),
        "output_dir": str(args.output_dir),
    }
    write_json(paths["methods"] / "methods.json", methods)
    lines = [
        "# TCGA-KIRC headless survival analyses",
        "",
        f"- Cohort: {COHORT}",
        "- Endpoint: overall survival (Dead = 1, Alive = 0)",
        "- Expression: log2(TPM + 1) from derived GDC STAR-count cache",
        "- Signature score: mean log2(TPM + 1) across member genes",
        f"- KM cutpoint: maxstat with minprop={args.maxstat_minprop}",
        "- Cox models: univariable, stage-adjusted, grade-adjusted, and stage+grade-adjusted",
        "- Sample rule: one RNA-seq sample per participant using TCGA biospecimen priority; all KIRC stages retained",
        "- Gene note: HLA-BQB2 in the document was treated as HLA-DQB2 because HLA-BQB2 is absent from the matrix",
        "",
        "## Analyses",
        "",
    ]
    for spec in specs:
        lines.append(f"- {spec.analysis_type}: {spec.label} ({', '.join(spec.genes)})")
    if skipped_rows:
        lines.extend(["", "## Skipped", ""])
        for row in skipped_rows:
            lines.append(f"- {row.get('analysis_id')}: {row.get('reason')}")
    (paths["methods"] / "methods.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def prepare_paths(output_dir: Path) -> dict[str, Path]:
    paths = {
        "root": output_dir,
        "signatures": output_dir / "signatures",
        "individual_genes": output_dir / "individual_genes",
        "tables": output_dir / "tables",
        "inputs": output_dir / "inputs",
        "logs": output_dir / "logs",
        "methods": output_dir / "methods",
    }
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)
    return paths


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run TCGA-KIRC KM and Cox analyses headlessly for thesis signatures and genes.")
    parser.add_argument("--tcga-data-dir", type=Path, default=Path("/data/tcga"))
    parser.add_argument("--derived-expression-dir", type=Path, default=Path("/app/derived/rna_bulk"))
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--km-script-path", type=Path, default=Path("/app/scripts/km_analysis.R"))
    parser.add_argument("--maxstat-script-path", type=Path, default=Path("/app/scripts/maxstat_cutpoint.R"))
    parser.add_argument("--rscript-bin", default="Rscript")
    parser.add_argument("--expression-scale", default="log2_tpm")
    parser.add_argument("--maxstat-minprop", type=float, default=0.15)
    parser.add_argument("--time-unit", choices=["days", "months", "years"], default="months")
    parser.add_argument("--show-confidence-interval", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--show-risk-table", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--only", action="append", default=[], help="Run only analyses matching this analysis id or label. Can be passed multiple times.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    paths = prepare_paths(args.output_dir)
    main_log = paths["logs"] / "run.log"
    main_log.write_text(f"TCGA-KIRC survival run started at {time.strftime('%Y-%m-%d %H:%M:%S')}\n", encoding="utf-8")

    if shutil.which(args.rscript_bin) is None:
        raise FileNotFoundError(f"{args.rscript_bin} was not found in PATH. Run this script inside the backend Docker image.")

    col_data_path = args.tcga_data_dir / COHORT / "col_data.tsv"
    samples, sample_summary = select_one_sample_per_patient(read_samples(col_data_path))
    metadata = load_matrix_metadata(args.derived_expression_dir, COHORT)
    expression_cache: dict[str, dict[str, float]] = {}

    specs = build_analysis_specs()
    if args.only:
        wanted = {item.lower() for item in args.only}
        specs = [
            spec
            for spec in specs
            if spec.analysis_id.lower() in wanted or spec.label.lower() in wanted
        ]
        if not specs:
            raise ValueError(f"No analyses matched --only values: {args.only}")

    summary_rows: list[dict[str, Any]] = []
    cox_rows: list[dict[str, Any]] = []
    km_rows: list[dict[str, Any]] = []
    skipped_rows: list[dict[str, Any]] = []

    for index, spec in enumerate(specs, start=1):
        with main_log.open("a", encoding="utf-8") as log:
            log.write(f"[{index}/{len(specs)}] {spec.analysis_type} {spec.label}\n")
        try:
            missing_genes: list[str] = []
            gene_values: list[dict[str, float]] = []
            for gene in spec.genes:
                if gene not in expression_cache:
                    expression = read_gene_expression(args.derived_expression_dir, metadata, gene, args.expression_scale)
                    if expression is None:
                        missing_genes.append(gene)
                        continue
                    expression_cache[gene] = expression
                gene_values.append(expression_cache[gene])
            if missing_genes:
                skipped_rows.append(
                    {
                        "analysis_id": spec.analysis_id,
                        "analysis_type": spec.analysis_type,
                        "label": spec.label,
                        "genes": ";".join(spec.genes),
                        "reason": "missing_genes",
                        "missing_genes": ";".join(missing_genes),
                    }
                )
                continue
            records = build_records(samples, gene_values, spec)
            if len(records) < 10:
                skipped_rows.append(
                    {
                        "analysis_id": spec.analysis_id,
                        "analysis_type": spec.analysis_type,
                        "label": spec.label,
                        "genes": ";".join(spec.genes),
                        "reason": "fewer_than_10_records",
                        "n_records": len(records),
                    }
                )
                continue
            cutpoint = compute_maxstat(records, spec, args, paths)
            metrics = run_km(records, cutpoint, spec, args, paths)
            summary, spec_cox_rows, km_row = summarize_metrics(spec, metrics)
            summary_rows.append(summary)
            cox_rows.extend(spec_cox_rows)
            km_rows.append(km_row)
        except Exception as error:
            message = str(error)
            reason = "maxstat_failed" if "maxstat_cutpoint" in message else type(error).__name__
            skipped_rows.append(
                {
                    "analysis_id": spec.analysis_id,
                    "analysis_type": spec.analysis_type,
                    "label": spec.label,
                    "genes": ";".join(spec.genes),
                    "reason": reason,
                    "message": message,
                }
            )
            with (paths["logs"] / f"{spec.analysis_id}.log").open("a", encoding="utf-8") as log:
                log.write(f"\nERROR {type(error).__name__}: {error}\n")

    write_tables(paths, summary_rows, cox_rows, km_rows, skipped_rows)
    write_methods(paths, args, sample_summary, specs, skipped_rows)
    write_json(
        paths["root"] / "analysis_manifest.json",
        {
            "cohort": COHORT,
            "output_dir": str(args.output_dir),
            "sample_summary": sample_summary,
            "completed": len(summary_rows),
            "skipped": len(skipped_rows),
            "summary_table": str(paths["tables"] / "summary_all_results.csv"),
            "cox_table": str(paths["tables"] / "cox_models_all.csv"),
            "km_table": str(paths["tables"] / "km_logrank_all.csv"),
            "skipped_table": str(paths["tables"] / "missing_or_skipped.csv"),
        },
    )
    with main_log.open("a", encoding="utf-8") as log:
        log.write(f"completed={len(summary_rows)} skipped={len(skipped_rows)}\n")
        log.write(f"TCGA-KIRC survival run finished at {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
    return 0 if summary_rows else 1


if __name__ == "__main__":
    sys.exit(main())
