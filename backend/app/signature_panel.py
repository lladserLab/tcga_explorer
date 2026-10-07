from __future__ import annotations

import csv
import html
import json
import math
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.attestation import write_attestation_receipt
from app.config import Settings
from app.reproduction_capsule import (
    BASE_IMAGE,
    CRAN_SNAPSHOT,
    RENV_VERSION,
    file_sha256,
    reproduction_dockerfile_source,
)
from app.r_runner import json_safe_value, stable_hash
from app.survival import ClinicalOutcome, sample_os_outcome


SIGNATURE_PANEL_SCHEMA_VERSION = "tcga-trace-signature-panel-v1"
SIGNATURE_PANEL_AUDIT_SCHEMA_VERSION = "tcga-trace-signature-panel-audit-v1"
SIGNATURE_PANEL_REPRODUCTION_SCHEMA_VERSION = (
    "tcga-trace-signature-panel-reproduction-v1"
)
MIN_PANEL_PATIENTS = 10
MIN_PANEL_EVENTS = 5


def standardize_signature_scores(
    samples: list[Any],
    expression_by_signature: list[dict[str, float]],
    names: list[str],
) -> tuple[list[dict[str, float]], list[dict[str, Any]]]:
    """Standardize every final score on the same expression-complete population."""

    if len(expression_by_signature) != len(names):
        raise ValueError("Signature score and name counts do not match.")
    common_barcodes = {
        sample.barcode
        for sample in samples
        if all(
            sample.barcode in expression
            and math.isfinite(float(expression[sample.barcode]))
            for expression in expression_by_signature
        )
    }
    if len(common_barcodes) < MIN_PANEL_PATIENTS:
        raise ValueError(
            "The signature panel has fewer than 10 eligible patients with "
            "complete scores for every signature."
        )

    standardized: list[dict[str, float]] = []
    summaries: list[dict[str, Any]] = []
    for name, expression in zip(
        names,
        expression_by_signature,
        strict=True,
    ):
        values = [expression[barcode] for barcode in sorted(common_barcodes)]
        center = sum(values) / len(values)
        variance = sum((value - center) ** 2 for value in values) / max(
            len(values) - 1,
            1,
        )
        standard_deviation = math.sqrt(variance)
        has_variation = (
            math.isfinite(standard_deviation)
            and standard_deviation > 0
        )
        standardized.append(
            {
                barcode: (
                    (expression[barcode] - center) / standard_deviation
                    if has_variation
                    else 0.0
                )
                for barcode in sorted(common_barcodes)
            }
        )
        summaries.append(
            {
                "name": name,
                "n": len(values),
                "center": center,
                "sample_standard_deviation": (
                    standard_deviation if math.isfinite(standard_deviation) else None
                ),
                "has_variation": has_variation,
                "effect_unit": "+1 within-panel score SD",
            }
        )
    return standardized, summaries


def build_signature_panel_records(
    samples: list[Any],
    standardized_scores: list[dict[str, float]],
    *,
    endpoint_by_patient: dict[str, ClinicalOutcome] | None,
    endpoint: str,
    max_time_days: float | None,
    external_covariates_by_patient: (
        dict[str, dict[str, str | float | None]] | None
    ) = None,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for sample in samples:
        if not all(
            sample.barcode in expression
            for expression in standardized_scores
        ):
            continue
        outcome = (
            endpoint_by_patient.get(sample.patient_id)
            if endpoint_by_patient is not None
            else sample_os_outcome(sample)
        )
        if outcome is None:
            continue
        if max_time_days is not None and outcome.time_days > max_time_days:
            outcome = ClinicalOutcome(
                endpoint=outcome.endpoint,
                time_days=float(max_time_days),
                event=0,
                source=outcome.source,
                competing_risk_status=(
                    0 if outcome.competing_risk_status is not None else None
                ),
                competing_event=(
                    0 if outcome.competing_event is not None else None
                ),
                competing_risk_source=outcome.competing_risk_source,
            )
        record: dict[str, Any] = {
            "patient_id": sample.patient_id,
            "sample_barcode": sample.barcode,
            "endpoint": endpoint,
            "time_days": float(outcome.time_days),
            "event": int(outcome.event),
            "competing_risk_status": outcome.competing_risk_status,
            "competing_event": outcome.competing_event,
            "competing_risk_source": outcome.competing_risk_source,
            "sample_type": sample.sample_type,
            "stage": sample.stage,
            "grade": sample.grade,
            "gender": sample.gender,
            "race": sample.race,
            "age_at_index": sample.age_at_index,
        }
        for index, expression in enumerate(
            standardized_scores,
            start=1,
        ):
            record[f"signature_{index}"] = expression[sample.barcode]
        for name, value in sorted(
            (
                external_covariates_by_patient.get(sample.patient_id, {})
                if external_covariates_by_patient
                else {}
            ).items()
        ):
            record[f"external__{name}"] = value
        records.append(record)
    validate_signature_panel_records(records)
    return records


def validate_signature_panel_records(records: list[dict[str, Any]]) -> None:
    if len(records) < MIN_PANEL_PATIENTS:
        raise ValueError(
            "The signature panel requires at least 10 patients with usable "
            "endpoint data and every requested score."
        )
    events = sum(int(record.get("event") or 0) for record in records)
    if events < MIN_PANEL_EVENTS:
        raise ValueError(
            "The signature panel requires at least 5 survival events after "
            f"filters; {events} remain."
        )


def signature_gene_overlap(signatures: list[dict[str, Any]]) -> dict[str, Any]:
    gene_sets = [
        {
            str(gene.get("resolved_symbol") or "").upper()
            for gene in signature.get("genes") or []
            if gene.get("resolved_symbol")
        }
        for signature in signatures
    ]
    pairs = []
    for left_index in range(len(signatures)):
        for right_index in range(left_index + 1, len(signatures)):
            shared = sorted(gene_sets[left_index] & gene_sets[right_index])
            union = gene_sets[left_index] | gene_sets[right_index]
            pairs.append(
                {
                    "signature_a": signatures[left_index]["name"],
                    "signature_b": signatures[right_index]["name"],
                    "shared_gene_count": len(shared),
                    "union_gene_count": len(union),
                    "jaccard": len(shared) / len(union) if union else 0.0,
                    "shared_genes": shared,
                }
            )
    return {
        "status": "reported",
        "interpretation": (
            "Gene overlap is descriptive context. It is not itself a model "
            "warning or an exclusion criterion."
        ),
        "pairs": pairs,
    }


def run_signature_panel_r(
    *,
    settings: Settings,
    analysis_id: str,
    payload: dict[str, Any],
    records: list[dict[str, Any]],
) -> dict[str, Any]:
    analysis_dir = settings.artifact_dir / analysis_id
    analysis_dir.mkdir(parents=True, exist_ok=True)
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "signature_panel.R"
    if not script_path.is_file():
        raise FileNotFoundError("The signature-panel R engine is not available.")

    paths = signature_panel_artifact_paths(analysis_dir)
    for path in paths.values():
        if path.is_file():
            path.unlink()

    r_payload = {
        **payload,
        "schema_version": SIGNATURE_PANEL_SCHEMA_VERSION,
        "records": records,
        "output_path": str(paths["json"]),
        "plot_path": str(paths["png"]),
        "plot_svg_path": str(paths["svg"]),
        "cox_forest_path": str(paths["cox_forest_png"]),
        "cox_forest_svg_path": str(paths["cox_forest_svg"]),
        "univariable_plot_path": str(paths["cox_univariable_png"]),
        "univariable_plot_svg_path": str(paths["cox_univariable_svg"]),
        "joint_plot_path": str(paths["signature_panel_joint_png"]),
        "joint_plot_svg_path": str(paths["signature_panel_joint_svg"]),
        "adjusted_plot_path": str(paths["signature_panel_adjusted_png"]),
        "adjusted_plot_svg_path": str(paths["signature_panel_adjusted_svg"]),
        "multivariable_plot_path": str(paths["cox_multivariable_png"]),
        "multivariable_plot_svg_path": str(paths["cox_multivariable_svg"]),
        "model_results_path": str(paths["model_results_csv"]),
        "correlations_path": str(paths["correlations_csv"]),
    }
    paths["input"].write_text(
        json.dumps(r_payload, ensure_ascii=False, allow_nan=False),
        encoding="utf-8",
    )
    write_panel_records_csv(records, paths["csv"])

    result = subprocess.run(
        ["Rscript", str(script_path), str(paths["input"])],
        check=False,
        capture_output=True,
        text=True,
        timeout=240,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Rscript failed: {result.stderr or result.stdout}"
        )
    if not paths["json"].is_file():
        raise RuntimeError(
            "Signature-panel R execution completed without metrics."
        )

    metrics = json_safe_value(
        json.loads(paths["json"].read_text(encoding="utf-8"))
    )
    write_signature_panel_methodology(
        paths["methodology"],
        analysis_id=analysis_id,
        payload=payload,
        metrics=metrics,
    )
    reproduction = write_signature_panel_reproduction_capsule(
        analysis_dir,
        script_path=script_path,
        renv_lock_path=Path(__file__).resolve().parents[1] / "renv.lock",
    )
    metrics["artifact_paths"] = {
        key: str(path) if path.is_file() else None
        for key, path in paths.items()
        if key not in {"audit_json", "audit_html"}
    }
    metrics["artifact_paths"].update(reproduction)
    return metrics


def signature_panel_artifact_paths(
    analysis_dir: Path,
) -> dict[str, Path]:
    return {
        "input": analysis_dir / "input.json",
        "json": analysis_dir / "metrics.json",
        "png": analysis_dir / "plot.png",
        "svg": analysis_dir / "plot.svg",
        "cox_forest_png": analysis_dir / "cox_forest.png",
        "cox_forest_svg": analysis_dir / "cox_forest.svg",
        "cox_univariable_png": analysis_dir / "cox_univariable.png",
        "cox_univariable_svg": analysis_dir / "cox_univariable.svg",
        "cox_multivariable_png": analysis_dir / "cox_multivariable.png",
        "cox_multivariable_svg": analysis_dir / "cox_multivariable.svg",
        "signature_panel_joint_png": analysis_dir / "signature_panel_joint.png",
        "signature_panel_joint_svg": analysis_dir / "signature_panel_joint.svg",
        "signature_panel_adjusted_png": (
            analysis_dir / "signature_panel_adjusted.png"
        ),
        "signature_panel_adjusted_svg": (
            analysis_dir / "signature_panel_adjusted.svg"
        ),
        "csv": analysis_dir / "raw_data.csv",
        "model_results_csv": analysis_dir / "model_results.csv",
        "correlations_csv": analysis_dir / "score_correlations.csv",
        "methodology": analysis_dir / "methodology.txt",
        "reproduction_expected_results": (
            analysis_dir / "expected_results.json"
        ),
        "reproduction_signature_panel": (
            analysis_dir / "signature_panel.R"
        ),
        "reproduction_clinical_covariates": (
            analysis_dir / "clinical_covariates.R"
        ),
        "reproduction_cox_diagnostics": (
            analysis_dir / "cox_diagnostics.R"
        ),
        "reproduction_renv_lock": analysis_dir / "renv.lock",
        "reproduction_r_runner": analysis_dir / "rerun_analysis.R",
        "reproduction_dockerfile": (
            analysis_dir / "Dockerfile.reproduce"
        ),
        "reproduction_readme": analysis_dir / "REPRODUCE.md",
        "reproduction_manifest": (
            analysis_dir / "reproduction_manifest.json"
        ),
        "audit_json": analysis_dir / "audit_report.json",
        "audit_html": analysis_dir / "audit_report.html",
    }


def write_panel_records_csv(
    records: list[dict[str, Any]],
    path: Path,
) -> None:
    fields = sorted(
        {
            key
            for record in records
            for key in record
        },
        key=lambda key: (
            0
            if key
            in {
                "patient_id",
                "sample_barcode",
                "endpoint",
                "time_days",
                "event",
            }
            else 1,
            key,
        ),
    )
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(records)


def write_signature_panel_methodology(
    path: Path,
    *,
    analysis_id: str,
    payload: dict[str, Any],
    metrics: dict[str, Any],
) -> None:
    panel = payload.get("signatures") or []
    adjustment = payload.get("adjustment_covariates") or []
    external_adjustment = (
        payload.get("external_adjustment_covariates") or []
    )
    lines = [
        "TRACE Explorer Signature Panel Methodology",
        "",
        f"Analysis ID: {analysis_id}",
        f"Generated at: {datetime.now(timezone.utc).isoformat()}",
        f"Pipeline version: {payload.get('pipeline_version')}",
        f"Cohort: {payload.get('cohort')}",
        f"Endpoint: {payload.get('endpoint')}",
        f"Expression layer: {payload.get('expression_layer_id') or payload.get('expression_scale')}",
        "",
        "Panel contract",
        f"- Signatures: {len(panel)} (minimum 2, maximum 6).",
        "- Each final score was standardized on the same score-complete population.",
        "- Effect unit: hazard ratio per +1 within-panel score standard deviation.",
        "- Every univariable model and the joint unadjusted model used the same patients and events.",
        "- The joint adjusted model used its own complete-case population and reports that population explicitly.",
        "- Only continuous main effects were fitted. No interactions, cutpoints, Kaplan-Meier groups or RMST estimates were used.",
        "",
        "Models",
        "- One univariable cause-specific Cox model per signature.",
        "- One joint cause-specific Cox model containing every signature.",
        (
            "- One joint clinically adjusted Cox model containing every signature "
            f"plus: {', '.join([*adjustment, *external_adjustment])}."
            if adjustment or external_adjustment
            else "- No clinically adjusted model was requested."
        ),
        "- Ties used the Efron method.",
        "- Proportional-hazards diagnostics used cox.zph for each signature term and the complete model.",
        "- The existing events-per-parameter and Firth sensitivity thresholds were retained.",
        (
            "- Equivalent Fine-Gray main-effect families were fitted when the "
            "endpoint supplied evaluable competing-event coding."
        ),
        "",
        "Multiplicity",
        "- Benjamini-Hochberg and Bonferroni corrections were applied separately within the univariable, joint and adjusted signature-term families.",
        "- Clinical covariate p-values were not included in signature multiplicity families.",
        "",
        "Population",
        f"- Common score-complete patients: {metrics.get('n_patients')}.",
        f"- Endpoint events: {metrics.get('n_events')}.",
        "",
        "Interpretation",
        "- Results are retrospective exploratory associations and are not clinical advice.",
        "- Correlations and gene overlap describe panel redundancy but do not by themselves trigger warnings or exclusions.",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_signature_panel_audit(
    *,
    settings: Settings,
    analysis_id: str,
    request_payload: dict[str, Any],
    metrics: dict[str, Any],
    records: list[dict[str, Any]],
    scoring_provenance: dict[str, Any],
    data_provenance: dict[str, Any],
    data_dates: dict[str, Any],
    warnings: list[str],
) -> dict[str, Any]:
    analysis_dir = settings.artifact_dir / analysis_id
    paths = signature_panel_artifact_paths(analysis_dir)
    record_digest = stable_hash({"records": records})
    scoring_digest = stable_hash(scoring_provenance)
    core_results = {
        "n_patients": metrics.get("n_patients"),
        "n_events": metrics.get("n_events"),
        "signature_panel": metrics.get("signature_panel"),
        "signature_panel_cox_models": metrics.get(
            "signature_panel_cox_models"
        ),
        "multiplicity": metrics.get("multiplicity"),
        "competing_risks": metrics.get("competing_risks"),
    }
    reproducibility_payload = {
        "request": request_payload,
        "data_dates": data_dates,
        "data_provenance": data_provenance,
        "scoring_provenance_sha256": scoring_digest,
        "patient_records_sha256": record_digest,
        "core_results": core_results,
    }
    artifacts = {}
    for label, path in paths.items():
        if (
            label in {"audit_json", "audit_html", "json"}
            or not path.is_file()
        ):
            continue
        artifacts[label] = {
            "filename": path.name,
            "bytes": path.stat().st_size,
            "sha256": file_sha256(path),
        }
    report = json_safe_value(
        {
            "schema_version": SIGNATURE_PANEL_AUDIT_SCHEMA_VERSION,
            "report_type": "signature_panel_audit",
            "analysis_id": analysis_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "reproducibility_hash": stable_hash(
                reproducibility_payload
            ),
            "reproducibility_hash_definition": {
                "algorithm": "sha256 over canonical JSON",
                "payload_fields": list(reproducibility_payload),
            },
            "request": request_payload,
            "pipeline": {
                "version": request_payload.get("pipeline_version"),
                "software_versions": metrics.get("software_versions") or {},
            },
            "data": {
                "dates": data_dates,
                "provenance": data_provenance,
                "endpoint": {
                    "value": metrics.get("endpoint"),
                    "label": metrics.get("endpoint_label"),
                    "source": metrics.get("endpoint_source"),
                    "qc": metrics.get("endpoint_qc"),
                },
            },
            "analysis_design": {
                "signature_panel": metrics.get("signature_panel"),
                "scoring_provenance_sha256": scoring_digest,
                "scoring_provenance": scoring_provenance,
                "adjustment_covariates": request_payload.get(
                    "adjustment_covariates"
                )
                or [],
                "external_adjustment_covariates": request_payload.get(
                    "external_adjustment_covariates"
                )
                or [],
                "filters": request_payload.get("filters") or {},
                "plot_style": request_payload.get("plot_style") or {},
            },
            "cohort_selection": {
                "sample_selection": metrics.get("sample_selection"),
                "patient_record_count": len(records),
                "patient_records_sha256": record_digest,
                "patient_records": records,
            },
            "results": core_results,
            "quality": {
                "warnings": list(dict.fromkeys(warnings)),
                "limitations": [
                    "Retrospective exploratory analysis based on public cohort data.",
                    "Main-effect models do not test signature interactions.",
                    "Correlated signatures can produce unstable joint estimates.",
                    "Association does not establish causality or clinical utility.",
                ],
            },
            "artifacts": artifacts,
        }
    )
    paths["audit_json"].write_text(
        json.dumps(report, ensure_ascii=False, allow_nan=False, indent=2),
        encoding="utf-8",
    )
    paths["audit_html"].write_text(
        render_signature_panel_audit_html(report),
        encoding="utf-8",
    )
    receipt = write_attestation_receipt(
        settings,
        subject_type="signature_panel",
        subject_id=analysis_id,
        audit_path=paths["audit_json"],
        reproducibility_hash=report["reproducibility_hash"],
        report_schema_version=report["schema_version"],
    )
    return {
        "schema_version": report["schema_version"],
        "generated_at": report["generated_at"],
        "reproducibility_hash": report["reproducibility_hash"],
        "server_attestation": receipt,
        "patient_records_sha256": record_digest,
    }


def render_signature_panel_audit_html(
    report: dict[str, Any],
) -> str:
    panel = (report.get("analysis_design") or {}).get(
        "signature_panel"
    ) or {}
    rows = "".join(
        "<tr>"
        f"<td>{html.escape(str(item.get('name') or ''))}</td>"
        f"<td>{html.escape(str(item.get('method') or ''))}</td>"
        f"<td>{html.escape(', '.join(str(gene.get('resolved_symbol') or '') for gene in item.get('genes') or []))}</td>"
        "</tr>"
        for item in panel.get("signatures") or []
    )
    return f"""<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>TRACE Explorer signature panel audit</title></head>
<body>
  <h1>TRACE Explorer Signature Panel Audit</h1>
  <p>Analysis ID: <code>{html.escape(str(report.get("analysis_id") or ""))}</code></p>
  <p>Reproducibility hash: <code>{html.escape(str(report.get("reproducibility_hash") or ""))}</code></p>
  <h2>Panel</h2>
  <table>
    <thead><tr><th>Signature</th><th>Score method</th><th>Genes</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
  <h2>Boundary</h2>
  <p>Continuous main effects only. No interactions, cutpoints, Kaplan-Meier groups or RMST.</p>
</body>
</html>
"""


def write_signature_panel_reproduction_capsule(
    analysis_dir: Path,
    *,
    script_path: Path,
    renv_lock_path: Path,
) -> dict[str, str]:
    capsule_paths = {
        "reproduction_expected_results": (
            analysis_dir / "expected_results.json"
        ),
        "reproduction_signature_panel": (
            analysis_dir / "signature_panel.R"
        ),
        "reproduction_clinical_covariates": (
            analysis_dir / "clinical_covariates.R"
        ),
        "reproduction_cox_diagnostics": (
            analysis_dir / "cox_diagnostics.R"
        ),
        "reproduction_renv_lock": analysis_dir / "renv.lock",
        "reproduction_r_runner": analysis_dir / "rerun_analysis.R",
        "reproduction_dockerfile": (
            analysis_dir / "Dockerfile.reproduce"
        ),
        "reproduction_readme": analysis_dir / "REPRODUCE.md",
        "reproduction_manifest": (
            analysis_dir / "reproduction_manifest.json"
        ),
    }
    manifest_path = capsule_paths["reproduction_manifest"]
    if manifest_path.is_file():
        missing = [
            path
            for path in capsule_paths.values()
            if not path.is_file()
        ]
        if missing:
            raise FileNotFoundError(
                "The frozen signature-panel reproduction capsule is "
                "incomplete; missing: "
                + ", ".join(str(path) for path in missing)
            )
        return {
            label: str(path)
            for label, path in capsule_paths.items()
        }

    sources = {
        "signature_panel.R": script_path,
        "clinical_covariates.R": script_path.parent / "clinical_covariates.R",
        "cox_diagnostics.R": script_path.parent / "cox_diagnostics.R",
    }
    required = [
        analysis_dir / "input.json",
        analysis_dir / "metrics.json",
        renv_lock_path,
        *sources.values(),
    ]
    missing = [path for path in required if not path.is_file()]
    if missing:
        raise FileNotFoundError(
            "Cannot create the signature-panel reproduction capsule; missing: "
            + ", ".join(str(path) for path in missing)
        )

    expected_results = analysis_dir / "expected_results.json"
    if not expected_results.is_file():
        shutil.copyfile(
            analysis_dir / "metrics.json",
            expected_results,
        )

    copied: dict[str, Path] = {}
    for filename, source in sources.items():
        destination = analysis_dir / filename
        if source.resolve() != destination.resolve():
            shutil.copyfile(source, destination)
        copied[f"reproduction_{Path(filename).stem}"] = destination
    lock_destination = analysis_dir / "renv.lock"
    if renv_lock_path.resolve() != lock_destination.resolve():
        shutil.copyfile(renv_lock_path, lock_destination)
    copied["reproduction_renv_lock"] = lock_destination

    runner = analysis_dir / "rerun_analysis.R"
    runner.write_text(signature_panel_rerun_source(), encoding="utf-8")
    copied["reproduction_r_runner"] = runner
    dockerfile = analysis_dir / "Dockerfile.reproduce"
    dockerfile.write_text(
        reproduction_dockerfile_source(),
        encoding="utf-8",
    )
    copied["reproduction_dockerfile"] = dockerfile
    readme = analysis_dir / "REPRODUCE.md"
    readme.write_text(
        signature_panel_reproduction_readme(),
        encoding="utf-8",
    )
    copied["reproduction_readme"] = readme

    manifest = {
        "schema_version": SIGNATURE_PANEL_REPRODUCTION_SCHEMA_VERSION,
        "base_image": BASE_IMAGE,
        "cran_snapshot": CRAN_SNAPSHOT,
        "renv_version": RENV_VERSION,
        "entrypoint": "rerun_analysis.R",
        "input": "input.json",
        "expected_results": "expected_results.json",
        "core_result_keys": [
            "n_patients",
            "n_events",
            "signature_panel_cox_models",
            "multiplicity",
            "competing_risks",
        ],
        "files": {},
    }
    capsule_files = {
        "input": analysis_dir / "input.json",
        "expected_results": expected_results,
        **copied,
    }
    for label, path in sorted(capsule_files.items()):
        manifest["files"][label] = {
            "filename": path.name,
            "bytes": path.stat().st_size,
            "sha256": file_sha256(path),
        }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {
        label: str(path)
        for label, path in capsule_paths.items()
    }


def signature_panel_rerun_source() -> str:
    return """#!/usr/bin/env Rscript
suppressPackageStartupMessages(library(jsonlite))
args <- commandArgs(trailingOnly = TRUE)
script_arg <- grep("^--file=", commandArgs(trailingOnly = FALSE), value = TRUE)
script_path <- normalizePath(sub("^--file=", "", script_arg[[1]]))
capsule_dir <- dirname(script_path)
output_dir <- if (length(args)) normalizePath(args[[1]], mustWork = FALSE) else file.path(capsule_dir, "rerun_output")
dir.create(output_dir, recursive = TRUE, showWarnings = FALSE)
payload <- fromJSON(file.path(capsule_dir, "input.json"), simplifyVector = FALSE)
payload$output_path <- file.path(output_dir, "metrics.json")
payload$plot_path <- file.path(output_dir, "plot.png")
payload$plot_svg_path <- file.path(output_dir, "plot.svg")
payload$cox_forest_path <- file.path(output_dir, "cox_forest.png")
payload$cox_forest_svg_path <- file.path(output_dir, "cox_forest.svg")
payload$univariable_plot_path <- file.path(output_dir, "cox_univariable.png")
payload$univariable_plot_svg_path <- file.path(output_dir, "cox_univariable.svg")
payload$joint_plot_path <- file.path(output_dir, "signature_panel_joint.png")
payload$joint_plot_svg_path <- file.path(output_dir, "signature_panel_joint.svg")
payload$adjusted_plot_path <- file.path(output_dir, "signature_panel_adjusted.png")
payload$adjusted_plot_svg_path <- file.path(output_dir, "signature_panel_adjusted.svg")
payload$multivariable_plot_path <- file.path(output_dir, "cox_multivariable.png")
payload$multivariable_plot_svg_path <- file.path(output_dir, "cox_multivariable.svg")
payload$model_results_path <- file.path(output_dir, "model_results.csv")
payload$correlations_path <- file.path(output_dir, "score_correlations.csv")
rerun_input <- file.path(output_dir, "input.json")
write_json(payload, rerun_input, auto_unbox = TRUE, null = "null", digits = NA)
command <- file.path(R.home("bin"), "Rscript")
output <- system2(command, c(shQuote(file.path(capsule_dir, "signature_panel.R")), shQuote(rerun_input)), stdout = TRUE, stderr = TRUE)
status <- attr(output, "status")
if (is.null(status)) status <- 0L
writeLines(output, file.path(output_dir, "rscript.log"))
if (status != 0L || !file.exists(payload$output_path)) stop("Frozen signature-panel analysis failed.")
observed <- fromJSON(payload$output_path, simplifyVector = FALSE)
expected <- fromJSON(file.path(capsule_dir, "expected_results.json"), simplifyVector = FALSE)
keys <- c("n_patients", "n_events", "signature_panel_cox_models", "multiplicity", "competing_risks")
passed <- identical(toJSON(observed[keys], auto_unbox = TRUE, null = "null", digits = NA), toJSON(expected[keys], auto_unbox = TRUE, null = "null", digits = NA))
write_json(list(schema_version = "tcga-trace-signature-panel-rerun-v1", status = if (passed) "passed" else "failed", compared_keys = as.list(keys)), file.path(output_dir, "reproduction_result.json"), auto_unbox = TRUE, pretty = TRUE)
if (!passed) quit(status = 1L)
cat("Standalone signature-panel reproduction passed\\n")
"""


def signature_panel_reproduction_readme() -> str:
    return f"""# Reproduce this TRACE Explorer signature panel

The capsule contains the exact score-complete patient table, request, R engine,
model outputs and package lock used by the exported panel.

```sh
docker build -f Dockerfile.reproduce -t tcga-trace-panel-rerun .
mkdir -p rerun_output
docker run --rm --network none --read-only \\
  --tmpfs /tmp:rw,noexec,nosuid,size=512m \\
  -v "$PWD:/analysis:ro" \\
  -v "$PWD/rerun_output:/output" \\
  tcga-trace-panel-rerun
```

The image is pinned to `{BASE_IMAGE}` and packages are restored from
`{CRAN_SNAPSHOT}`. The rerun compares the model families, multiplicity results
and competing-risk outputs with the exported metrics.
"""
