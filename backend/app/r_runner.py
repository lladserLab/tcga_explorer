import csv
import hashlib
import html
import importlib.metadata
import json
import math
import platform
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from app.config import Settings
from app.survival import SurvivalRecord


def stable_hash(payload: dict) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def json_safe_value(value):
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {key: json_safe_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_safe_value(item) for item in value]
    return value


def write_records_csv(records: list[SurvivalRecord], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(records[0].as_dict().keys())
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for record in records:
            writer.writerow(record.as_dict())


def run_r_km(
    settings: Settings,
    analysis_id: str,
    cohort: str,
    gene_symbol: str,
    endpoint: str,
    endpoint_label: str,
    cutpoint_method: str,
    records: list[SurvivalRecord],
    group_levels: list[str],
    cutpoint_details: dict,
    show_confidence_interval: bool,
    show_risk_table: bool,
    plot_style: dict,
    expression_scale: str,
    expression_scale_label: str,
    time_unit: str = "days",
    request_payload: dict | None = None,
    analysis_warnings: list[str] | None = None,
    data_dates: dict | None = None,
    sample_selection: dict | None = None,
) -> dict:
    analysis_dir = settings.artifact_dir / analysis_id
    analysis_dir.mkdir(parents=True, exist_ok=True)

    input_path = analysis_dir / "input.json"
    output_path = analysis_dir / "metrics.json"
    png_path = analysis_dir / "plot.png"
    svg_path = analysis_dir / "plot.svg"
    cox_forest_png_path = analysis_dir / "cox_forest.png"
    cox_forest_svg_path = analysis_dir / "cox_forest.svg"
    csv_path = analysis_dir / "raw_data.csv"
    methodology_path = analysis_dir / "methodology.txt"
    clear_stale_analysis_artifacts(
        [
            output_path,
            png_path,
            svg_path,
            cox_forest_png_path,
            cox_forest_svg_path,
            csv_path,
            methodology_path,
            analysis_dir / "audit_report.json",
            analysis_dir / "audit_report.html",
            analysis_dir / "svg_input.json",
            analysis_dir / "svg_metrics.json",
        ]
    )

    write_records_csv(records, csv_path)
    payload = {
        "analysis_id": analysis_id,
        "cohort": cohort,
        "gene_symbol": gene_symbol,
        "endpoint": endpoint,
        "endpoint_label": endpoint_label,
        "expression_scale": expression_scale,
        "expression_scale_label": expression_scale_label,
        "time_unit": time_unit,
        "cutpoint_method": cutpoint_method,
        "group_levels": group_levels,
        "cutpoint_details": cutpoint_details,
        "records": [record.as_dict() for record in records],
        "show_confidence_interval": show_confidence_interval,
        "show_risk_table": show_risk_table,
        "plot_style": plot_style,
        "png_path": str(png_path),
        "svg_path": str(svg_path),
        "cox_forest_png_path": str(cox_forest_png_path),
        "cox_forest_svg_path": str(cox_forest_svg_path),
        "render_png": True,
        "render_svg": False,
        "output_path": str(output_path),
    }
    input_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    result = subprocess.run(
        ["Rscript", str(settings.r_script_path), str(input_path)],
        check=False,
        capture_output=True,
        text=True,
        timeout=180,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Rscript failed: {result.stderr or result.stdout}")

    metrics = json_safe_value(json.loads(output_path.read_text(encoding="utf-8")))
    if sample_selection is not None:
        metrics["sample_selection"] = sample_selection
    write_methodology_txt(
        path=methodology_path,
        settings=settings,
        analysis_id=analysis_id,
        cohort=cohort,
        gene_symbol=gene_symbol,
        endpoint=endpoint,
        endpoint_label=endpoint_label,
        expression_scale=expression_scale,
        expression_scale_label=expression_scale_label,
        time_unit=time_unit,
        cutpoint_method=cutpoint_method,
        cutpoint_details=cutpoint_details,
        group_levels=group_levels,
        show_confidence_interval=show_confidence_interval,
        show_risk_table=show_risk_table,
        plot_style=plot_style,
        request_payload=request_payload or {},
        metrics=metrics,
        analysis_warnings=analysis_warnings or [],
        data_dates=data_dates or {},
    )
    metrics["artifact_paths"] = {
        "png": str(png_path),
        "svg": str(svg_path),
        "cox_forest_png": str(cox_forest_png_path) if cox_forest_png_path.exists() else None,
        "cox_forest_svg": str(cox_forest_svg_path),
        "csv": str(csv_path),
        "json": str(output_path),
        "txt": str(methodology_path),
    }
    return metrics


def clear_stale_analysis_artifacts(paths: list[Path]) -> None:
    for path in paths:
        try:
            if path.exists() and path.is_file():
                path.unlink()
        except OSError:
            continue


def write_audit_report(
    settings: Settings,
    analysis_id: str,
    request_payload: dict,
    metrics: dict,
    records: list[SurvivalRecord],
    artifact_paths: dict,
    analysis_warnings: list[str] | None = None,
    data_dates: dict | None = None,
) -> dict:
    analysis_dir = settings.artifact_dir / analysis_id
    analysis_dir.mkdir(parents=True, exist_ok=True)
    json_path = analysis_dir / "audit_report.json"
    html_path = analysis_dir / "audit_report.html"
    generated_at = datetime.now(timezone.utc).isoformat()
    record_payload = [record.as_dict() for record in records]
    record_digest = stable_hash({"records": record_payload})
    median_status = median_survival_status(metrics)
    core_results = audit_core_results(metrics, median_status)
    reproducibility_payload = {
        "request": request_payload,
        "data_dates": data_dates or {},
        "record_digest": record_digest,
        "core_results": core_results,
    }
    report = {
        "schema_version": "tcga-explorer-analysis-audit-v1",
        "report_type": "survival_analysis_audit",
        "analysis_id": analysis_id,
        "generated_at": generated_at,
        "reproducibility_hash": stable_hash(reproducibility_payload),
        "pipeline": {
            "version": request_payload.get("pipeline_version"),
            "software_versions": software_versions(metrics),
        },
        "data": {
            "cohort": request_payload.get("cohort"),
            "data_dates": data_dates or {},
            "endpoint": {
                "value": metrics.get("endpoint") or request_payload.get("endpoint"),
                "label": metrics.get("endpoint_label"),
                "source": metrics.get("endpoint_source"),
                "qc": metrics.get("endpoint_qc"),
            },
            "expression_scale": {
                "value": metrics.get("expression_scale") or request_payload.get("expression_scale"),
                "label": metrics.get("expression_scale_label"),
            },
        },
        "analysis_design": {
            "gene_symbol": request_payload.get("gene_symbol"),
            "reported_marker": metrics.get("signature", {}).get("label") or request_payload.get("gene_symbol"),
            "signature": metrics.get("signature"),
            "combined_signature": metrics.get("combined_signature"),
            "cutpoint_method": request_payload.get("cutpoint_method") or request_payload.get("combination_method"),
            "cutpoint_details": metrics.get("cutpoint_details"),
            "filters": request_payload.get("filters") or {},
            "time_unit": metrics.get("time_unit") or request_payload.get("time_unit"),
            "plot_style": request_payload.get("plot_style") or {},
        },
        "cohort_selection": {
            "sample_selection": metrics.get("sample_selection"),
            "patient_record_count": len(record_payload),
            "patient_records_sha256": record_digest,
            "patient_records": record_payload,
        },
        "results": core_results,
        "quality": {
            "summary": metrics.get("quality"),
            "warnings": list(dict.fromkeys((analysis_warnings or []) + (metrics.get("warnings") or []))),
            "limitations": [
                "Retrospective exploratory analysis based on public TCGA cohort data.",
                "Kaplan-Meier grouping does not establish causality and is sensitive to cutpoint choice.",
                "Optimized cutpoints such as maxstat can overestimate apparent significance unless externally validated.",
                "Clinical adjustment is limited to imported covariates and does not include treatment or tumor purity.",
            ],
        },
        "artifacts": audit_artifact_manifest(artifact_paths),
    }
    report = json_safe_value(report)
    json_path.write_text(json.dumps(report, ensure_ascii=False, allow_nan=False, indent=2), encoding="utf-8")
    html_path.write_text(render_audit_html(report), encoding="utf-8")
    return {
        "json": str(json_path),
        "html": str(html_path),
        "schema_version": report["schema_version"],
        "generated_at": generated_at,
        "reproducibility_hash": report["reproducibility_hash"],
        "patient_records_sha256": record_digest,
        "median_survival_status": median_status,
    }


def audit_core_results(metrics: dict, median_status: dict) -> dict:
    return {
        "n_patients": metrics.get("n_patients"),
        "n_events": metrics.get("n_events"),
        "group_counts": metrics.get("group_counts") or {},
        "event_counts": metrics.get("event_counts") or {},
        "median_survival_days": metrics.get("median_survival_days") or {},
        "median_survival_status": median_status,
        "rmst": metrics.get("rmst"),
        "logrank_p_value": metrics.get("logrank_p_value"),
        "hazard_ratio": metrics.get("hazard_ratio"),
        "hr_conf_low": metrics.get("hr_conf_low"),
        "hr_conf_high": metrics.get("hr_conf_high"),
        "hr_p_value": metrics.get("hr_p_value"),
        "cox_models": metrics.get("cox_models") or [],
        "signature_interaction_cox_models": metrics.get("signature_interaction_cox_models") or [],
        "expression_distribution": metrics.get("expression_distribution"),
        "expression_distribution_a": metrics.get("expression_distribution_a"),
        "expression_distribution_b": metrics.get("expression_distribution_b"),
    }


def median_survival_status(metrics: dict) -> dict:
    medians = metrics.get("median_survival_days") or {}
    status = {}
    for group, value in medians.items():
        if value is None:
            status[group] = {
                "status": "not_reached",
                "explanation": "The Kaplan-Meier curve did not fall to or below 50% survival in this group, so median survival was not reached.",
            }
        else:
            status[group] = {
                "status": "estimated",
                "explanation": "Median survival was reached and estimated from the Kaplan-Meier curve.",
            }
    return status


def audit_artifact_manifest(paths: dict) -> dict:
    manifest = {}
    for label, raw_path in sorted(paths.items()):
        if not raw_path:
            continue
        path = Path(raw_path)
        if not path.exists() or not path.is_file():
            continue
        manifest[label] = {
            "filename": path.name,
            "bytes": path.stat().st_size,
            "sha256": file_sha256(path),
        }
    return manifest


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def render_audit_html(report: dict) -> str:
    def esc(value) -> str:
        if value is None:
            return ""
        return html.escape(str(value), quote=True)

    def rows(items: list[tuple[str, object]]) -> str:
        return "\n".join(f"<tr><th>{esc(label)}</th><td>{esc(value)}</td></tr>" for label, value in items)

    results = report.get("results") or {}
    data = report.get("data") or {}
    endpoint = data.get("endpoint") or {}
    analysis = report.get("analysis_design") or {}
    quality = report.get("quality") or {}
    group_counts = results.get("group_counts") or {}
    event_counts = results.get("event_counts") or {}
    medians = results.get("median_survival_days") or {}
    median_status = results.get("median_survival_status") or {}
    rmst = results.get("rmst") or {}
    cox_models = results.get("cox_models") or []
    interaction_models = results.get("signature_interaction_cox_models") or []
    artifacts = report.get("artifacts") or {}
    warnings = quality.get("warnings") or []

    group_rows = "\n".join(
        "<tr>"
        f"<td>{esc(group)}</td>"
        f"<td>{esc(group_counts.get(group))}</td>"
        f"<td>{esc(event_counts.get(group))}</td>"
        f"<td>{esc('not reached' if medians.get(group) is None else medians.get(group))}</td>"
        f"<td>{esc((median_status.get(group) or {}).get('status'))}</td>"
        "</tr>"
        for group in group_counts
    )
    cox_rows = "\n".join(
        "<tr>"
        f"<td>{esc(model.get('label') or model.get('model'))}</td>"
        f"<td>{esc(', '.join(model.get('covariates') or []) or 'none')}</td>"
        f"<td>{esc(model.get('n_patients'))}</td>"
        f"<td>{esc(model.get('n_events'))}</td>"
        f"<td>{esc(model.get('hazard_ratio'))}</td>"
        f"<td>{esc(model.get('p_value'))}</td>"
        f"<td>{esc(model.get('ph_global_p_value'))}</td>"
        f"<td>{esc(model.get('status'))}</td>"
        f"<td>{esc(model.get('reason'))}</td>"
        "</tr>"
        for model in cox_models
    )
    rmst_rows = ""
    if rmst.get("status") == "completed":
        rmst_groups = rmst.get("groups") or {}
        rmst_rows = "\n".join(
            "<tr>"
            f"<td>{esc(group)}</td>"
            f"<td>{esc((item or {}).get('rmst_days'))}</td>"
            f"<td>{esc((item or {}).get('conf_low'))}</td>"
            f"<td>{esc((item or {}).get('conf_high'))}</td>"
            "</tr>"
            for group, item in rmst_groups.items()
        )
    else:
        rmst_rows = (
            "<tr>"
            f"<td colspan=\"4\">{esc(rmst.get('reason') or 'RMST was not estimated for this analysis.')}</td>"
            "</tr>"
        )
    interaction_rows = "\n".join(
        "<tr>"
        f"<td>{esc(model.get('label') or model.get('model'))}</td>"
        f"<td>{esc(', '.join(model.get('covariates') or []) or 'none')}</td>"
        f"<td>{esc(model.get('n_patients'))}</td>"
        f"<td>{esc(model.get('n_events'))}</td>"
        f"<td>{esc((model.get('interaction_term') or {}).get('hazard_ratio'))}</td>"
        f"<td>{esc((model.get('interaction_term') or {}).get('p_value'))}</td>"
        f"<td>{esc(model.get('ph_global_p_value'))}</td>"
        f"<td>{esc(model.get('status'))}</td>"
        f"<td>{esc(model.get('reason'))}</td>"
        "</tr>"
        for model in interaction_models
    )
    artifact_rows = "\n".join(
        "<tr>"
        f"<td>{esc(label)}</td>"
        f"<td>{esc(item.get('filename'))}</td>"
        f"<td>{esc(item.get('bytes'))}</td>"
        f"<td><code>{esc(item.get('sha256'))}</code></td>"
        "</tr>"
        for label, item in artifacts.items()
    )
    warning_items = "\n".join(f"<li>{esc(warning)}</li>" for warning in warnings) or "<li>None reported.</li>"
    json_payload = html.escape(json.dumps(report, ensure_ascii=False, indent=2), quote=False)

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>TCGA Explorer audit report {esc(report.get('analysis_id'))}</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 32px; color: #17211f; background: #fbfcfb; }}
    h1 {{ font-size: 28px; margin-bottom: 4px; }}
    h2 {{ font-size: 18px; margin-top: 28px; }}
    table {{ border-collapse: collapse; width: 100%; margin: 12px 0; background: #ffffff; }}
    th, td {{ border: 1px solid #d9e1de; padding: 8px 10px; text-align: left; vertical-align: top; }}
    th {{ background: #eef3f1; }}
    code, pre {{ font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }}
    pre {{ overflow: auto; padding: 16px; background: #111816; color: #edf5f2; border-radius: 6px; }}
    .hash {{ color: #41524e; word-break: break-all; }}
  </style>
</head>
<body>
  <h1>TCGA Explorer Survival Analysis Audit Report</h1>
  <p class="hash">Analysis ID: <code>{esc(report.get('analysis_id'))}</code></p>
  <p class="hash">Reproducibility hash: <code>{esc(report.get('reproducibility_hash'))}</code></p>

  <h2>Analysis Summary</h2>
  <table>
    {rows([
        ("Generated at", report.get("generated_at")),
        ("Cohort", data.get("cohort")),
        ("Marker", analysis.get("reported_marker")),
        ("Endpoint", f"{endpoint.get('label')} ({endpoint.get('value')})"),
        ("Endpoint source", endpoint.get("source")),
        ("Expression scale", (data.get("expression_scale") or {}).get("label")),
        ("Cutpoint method", analysis.get("cutpoint_method")),
        ("Patients", results.get("n_patients")),
        ("Events", results.get("n_events")),
        ("Log-rank p-value", results.get("logrank_p_value")),
        ("Hazard ratio", results.get("hazard_ratio")),
    ])}
  </table>

  <h2>Survival Groups</h2>
  <table>
    <thead><tr><th>Group</th><th>Patients</th><th>Events</th><th>Median days</th><th>Median status</th></tr></thead>
    <tbody>{group_rows}</tbody>
  </table>

  <h2>Cox Models</h2>
  <table>
    <thead><tr><th>Model</th><th>Covariates</th><th>Patients</th><th>Events</th><th>HR</th><th>p</th><th>PH global p</th><th>Status</th><th>Reason</th></tr></thead>
    <tbody>{cox_rows}</tbody>
  </table>

  <h2>Restricted Mean Survival Time</h2>
  <table>
    {rows([
        ("Status", rmst.get("status")),
        ("Method", rmst.get("method")),
        ("Tau days", rmst.get("tau_days")),
        ("Tau rule", rmst.get("tau_rule")),
        ("Comparison", f"{rmst.get('comparison_group')} vs {rmst.get('reference_group')}" if rmst.get("comparison_group") else None),
        ("RMST difference days", (rmst.get("difference") or {}).get("estimate_days")),
        ("RMST difference p-value", (rmst.get("difference") or {}).get("p_value")),
    ])}
  </table>
  <table>
    <thead><tr><th>Group</th><th>RMST days</th><th>Lower 95%</th><th>Upper 95%</th></tr></thead>
    <tbody>{rmst_rows}</tbody>
  </table>

  <h2>Two-Signature Interaction Cox Models</h2>
  <table>
    <thead><tr><th>Model</th><th>Covariates</th><th>Patients</th><th>Events</th><th>Interaction HR</th><th>Interaction p</th><th>PH global p</th><th>Status</th><th>Reason</th></tr></thead>
    <tbody>{interaction_rows}</tbody>
  </table>

  <h2>Warnings And Limitations</h2>
  <ul>{warning_items}</ul>

  <h2>Artifacts</h2>
  <table>
    <thead><tr><th>Artifact</th><th>Filename</th><th>Bytes</th><th>SHA-256</th></tr></thead>
    <tbody>{artifact_rows}</tbody>
  </table>

  <h2>Full Audit JSON</h2>
  <pre>{json_payload}</pre>
</body>
</html>
"""


def run_r_pancancer_cox(
    settings: Settings,
    scan_id: str,
    cohorts: list[dict],
    min_patients: int,
    min_events: int,
    request_payload: dict,
) -> dict:
    scan_dir = settings.artifact_dir / "pancancer" / scan_id
    scan_dir.mkdir(parents=True, exist_ok=True)
    input_path = scan_dir / "input.json"
    output_path = scan_dir / "cox_results.json"
    payload = {
        "scan_id": scan_id,
        "min_patients": min_patients,
        "min_events": min_events,
        "request": request_payload,
        "cohorts": cohorts,
        "output_path": str(output_path),
    }
    input_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    result = subprocess.run(
        ["Rscript", str(settings.pancancer_script_path), str(input_path)],
        check=False,
        capture_output=True,
        text=True,
        timeout=240,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Rscript failed: {result.stderr or result.stdout}")
    return json.loads(output_path.read_text(encoding="utf-8"))


def ensure_svg_artifact(settings: Settings, analysis_id: str) -> Path:
    analysis_dir = settings.artifact_dir / analysis_id
    input_path = analysis_dir / "input.json"
    svg_path = analysis_dir / "plot.svg"
    if svg_path.exists():
        return svg_path
    if not input_path.exists():
        raise FileNotFoundError("Analysis input payload is not available.")

    payload = json.loads(input_path.read_text(encoding="utf-8"))
    payload["render_png"] = False
    payload["render_svg"] = True
    payload["svg_path"] = str(svg_path)
    payload["cox_forest_svg_path"] = str(analysis_dir / "cox_forest.svg")
    payload["output_path"] = str(analysis_dir / "svg_metrics.json")
    svg_input_path = analysis_dir / "svg_input.json"
    svg_input_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    result = subprocess.run(
        ["Rscript", str(settings.r_script_path), str(svg_input_path)],
        check=False,
        capture_output=True,
        text=True,
        timeout=180,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Rscript failed while generating SVG: {result.stderr or result.stdout}")
    if not svg_path.exists():
        raise FileNotFoundError("SVG generation completed but no SVG file was produced.")
    return svg_path


def write_methodology_txt(
    path: Path,
    settings: Settings,
    analysis_id: str,
    cohort: str,
    gene_symbol: str,
    endpoint: str,
    endpoint_label: str,
    expression_scale: str,
    expression_scale_label: str,
    time_unit: str,
    cutpoint_method: str,
    cutpoint_details: dict,
    group_levels: list[str],
    show_confidence_interval: bool,
    show_risk_table: bool,
    plot_style: dict,
    request_payload: dict,
    metrics: dict,
    analysis_warnings: list[str],
    data_dates: dict,
) -> None:
    filters = request_payload.get("filters") or {}
    sample_selection = metrics.get("sample_selection") or {}
    database_created_at = data_dates.get("database_imported_at") or "not available"
    data_through = data_dates.get("source_latest_metadata_file") or data_dates.get("source_summary_file") or "not available"
    lines = [
        "REMARK-Style Kaplan-Meier Survival Analysis Methodology",
        "",
        f"Analysis ID: {analysis_id}",
        f"Generated at: {datetime.now(timezone.utc).isoformat()}",
        "",
        "Study Objective",
        "- Objective: exploratory evaluation of the association between RNA expression or an RNA expression signature and a TCGA survival endpoint.",
        "- Intended use: research hypothesis generation and manuscript methods reporting; results are not intended for clinical decision-making.",
        "",
        "Data Source",
        f"- Cohort: {cohort}",
        f"- Gene: {gene_symbol}",
        f"- Endpoint: {endpoint_label} ({endpoint})",
        "- Data source: TCGA cancer cohort RNA-seq and clinical/sample metadata.",
        "- Clinical endpoint source: TCGA-CDR when configured and available; otherwise OS falls back to TCGA clinical/sample metadata.",
        "- TCGA-CDR citation: Liu et al., Cell 2018, doi:10.1016/j.cell.2018.02.052.",
        "- Reporting framework: REMARK-style structure for transparent prognostic marker reporting.",
        f"- TCGA cohort data through: {data_through}",
        f"- Database created at: {database_created_at}",
        f"- Source summary snapshot: {data_dates.get('source_summary_file') or 'not available'}",
        f"- TCGA-CDR source timestamp: {data_dates.get('tcga_cdr_source_file') or 'not available'}",
        f"- TCGA-CDR import timestamp: {data_dates.get('tcga_cdr_imported_at') or 'not available'}",
        f"- RNA cache timestamp: {data_dates.get('rna_cache_generated_at') or 'not available'}",
        f"- Analysis pipeline version: {request_payload.get('pipeline_version') or 'not available'}",
        "",
        "Cohort And Sample Selection",
        "- Samples were restricted according to the user-selected clinical filters below.",
        f"- Sample type filter: {format_filter(filters.get('sample_types'))}",
        f"- Stage filter: {format_filter(filters.get('stages'))}",
        f"- Grade filter: {format_filter(filters.get('grades'))}",
        f"- Gender filter: {format_filter(filters.get('genders'))}",
        f"- Race filter: {format_filter(filters.get('races'))}",
        f"- Minimum age at index: {format_optional(filters.get('age_min'))}",
        f"- Maximum age at index: {format_optional(filters.get('age_max'))}",
        f"- Maximum follow-up time in days: {format_optional(filters.get('max_time_days'))} (patients with longer follow-up are administratively censored at this time; event set to 0).",
        f"- Final analyzable patients: {metrics.get('n_patients', 'not available')}",
        f"- Observed events: {metrics.get('n_events', 'not available')}",
        "",
        "Patient-Level Sample Selection",
        "- Survival analyses were fitted with one observation per TCGA participant to avoid weighting a patient more than once.",
        f"- Duplicate-sample rule: {sample_selection.get('rule_description') or 'one eligible RNA-seq sample was retained per participant using TCGA barcode order.'}",
        f"- Input samples before filters: {format_optional(sample_selection.get('input_samples'))}",
        f"- Samples after user filters: {format_optional(sample_selection.get('after_user_filters'))}",
        f"- Samples with complete endpoint data after filters: {format_optional(sample_selection.get('complete_endpoint_samples', sample_selection.get('complete_os_samples')))}",
        f"- Samples removed for missing endpoint data: {format_optional(sample_selection.get('missing_endpoint_removed', sample_selection.get('missing_os_removed')))}",
        f"- Extra same-patient sample records removed: {format_optional(sample_selection.get('duplicate_samples_removed'))}",
        f"- Retained patient-level sample types: {format_count_dict(sample_selection.get('retained_sample_types'))}",
        f"- Removed duplicate sample types: {format_count_dict(sample_selection.get('removed_duplicate_sample_types'))}",
        "",
        "Survival Endpoint",
        f"- Endpoint analyzed: {endpoint_label} ({endpoint}).",
        endpoint_method_text(endpoint, sample_selection.get("endpoint_source")),
        "- Samples with missing or non-positive endpoint time were excluded before fitting survival models.",
        f"- Survival statistics used time in days; the plot X-axis was displayed in {time_unit}.",
        "",
        "Marker Measurement / RNA Expression Transformation",
        expression_method_text(expression_scale, expression_scale_label),
        *signature_methodology_lines(request_payload),
        "",
        "Patient Stratification",
        stratification_method_text(cutpoint_method, cutpoint_details),
        f"- Final expression groups: {', '.join(group_levels)}",
        f"- Cutpoint details: {json.dumps(cutpoint_details, sort_keys=True)}",
        "",
        "Statistical Analysis",
        f"- Kaplan-Meier curves were fitted with survival::survfit using {endpoint_label.lower()} time and event status.",
        "- Group differences were tested with the log-rank test using survival::survdiff.",
        "- When exactly two expression groups were present, Cox proportional hazards models were fitted with survival::coxph to estimate hazard ratios and 95% confidence intervals.",
        "- Cox models attempted: univariable expression group; expression group adjusted for pathologic stage; expression group adjusted for tumor grade; expression group adjusted for both stage and grade. Adjusted models were reported only when complete covariate data and model rank were sufficient.",
        rmst_method_text(metrics),
        interaction_method_text(metrics),
        f"- Log-rank p-value: {format_optional(metrics.get('logrank_p_value'))}",
        f"- Hazard ratio: {format_optional(metrics.get('hazard_ratio'))}",
        f"- Hazard ratio 95% CI: {format_optional(metrics.get('hr_conf_low'))} to {format_optional(metrics.get('hr_conf_high'))}",
        f"- Cox model p-value: {format_optional(metrics.get('hr_p_value'))}",
        f"- RMST status: {format_optional((metrics.get('rmst') or {}).get('status'))}",
        f"- RMST tau in days: {format_optional((metrics.get('rmst') or {}).get('tau_days'))}",
        f"- RMST difference in days: {format_optional(((metrics.get('rmst') or {}).get('difference') or {}).get('estimate_days'))}",
        f"- RMST difference p-value: {format_optional(((metrics.get('rmst') or {}).get('difference') or {}).get('p_value'))}",
        f"- Cox adjustment models available: {format_cox_models(metrics.get('cox_models'))}",
        f"- Signature interaction Cox models available: {format_cox_models(metrics.get('signature_interaction_cox_models'))}",
        "",
        "Plot Generation",
        "- Kaplan-Meier plots were generated in R with survminer::ggsurvplot and ggplot2.",
        f"- Confidence interval shown: {'yes' if show_confidence_interval else 'no'}",
        f"- Risk table shown: {'yes' if show_risk_table else 'no'}",
        f"- Plot title shown: {'yes' if plot_style.get('show_title') else 'no'}",
        f"- Plot title text: {plot_style.get('plot_title') or 'not used'}",
        f"- Palette: {', '.join(plot_style.get('palette') or [])}",
        f"- Font family: {plot_style.get('font_family') or 'sans'}",
        f"- Plot aspect: {plot_style.get('plot_aspect') or 'rectangular'}",
        f"- Base font size: {plot_style.get('base_font_size') or 12}",
        f"- Axis tick-label font size: {plot_style.get('axis_text_size') or 11}",
        f"- Axis title font size: {plot_style.get('axis_title_size') or 12}",
        f"- Plot grid shown: {'yes' if plot_style.get('show_grid', True) else 'no'}",
        "",
        "Output Files",
        "- PNG contains the rendered Kaplan-Meier plot generated at analysis time.",
        "- SVG contains the rendered Kaplan-Meier plot and is generated on demand when requested for download.",
        csv_methodology_text(request_payload),
        "- This TXT file contains the parameter-specific methods text.",
        "",
        "Warnings And Exclusions",
        *[f"- {warning}" for warning in analysis_warnings],
        *[f"- {warning}" for warning in metrics.get("warnings", [])],
        "" if analysis_warnings or metrics.get("warnings") else "- None reported.",
        "",
        "Limitations",
        "- This is a retrospective exploratory analysis based on public TCGA cohort data.",
        "- Kaplan-Meier grouping does not establish causality and can be sensitive to cutpoint choice.",
        "- Optimized cutpoints such as maxstat can overestimate apparent significance unless validated externally.",
        "- Clinical covariate adjustment is limited to imported stage and grade fields and does not account for treatment, tumor purity, immune composition or other prognostic variables.",
        "",
        "Software Versions",
    ]
    versions = software_versions(metrics)
    lines.extend(f"- {name}: {value}" for name, value in versions.items())
    lines.extend(
        [
            "",
            "Suggested citation wording",
            f"Kaplan-Meier survival analyses were performed using TCGA cancer cohort RNA-seq and clinical metadata from a database created at {database_created_at}, with data through {data_through}. The analyzed endpoint was {endpoint_label} ({endpoint}). When multiple eligible RNA-seq barcodes were available for the same TCGA participant, one sample was retained using a TCGA biospecimen priority rule before expression stratification. Gene expression was transformed as described above, patients were stratified according to the selected cutpoint rule, and survival differences were assessed with log-rank tests. For two-group comparisons, hazard ratios were estimated with Cox proportional hazards models, including univariable and stage/grade-adjusted models when covariate data were available; restricted mean survival time was estimated with survRM2 when available. Plots were generated in R using survival, survminer and ggplot2.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def rmst_method_text(metrics: dict) -> str:
    rmst = metrics.get("rmst") or {}
    if rmst.get("status") == "completed":
        return (
            "- Restricted mean survival time was estimated with survRM2::rmst2 for two-group comparisons. "
            f"The truncation time tau was {format_optional(rmst.get('tau_days'))} days, defined as the {rmst.get('tau_rule') or 'analysis-specific follow-up limit'}."
        )
    reason = rmst.get("reason") or "not applicable"
    return f"- Restricted mean survival time was not estimated: {reason}"


def expression_method_text(expression_scale: str, expression_scale_label: str) -> str:
    if expression_scale == "log2_tpm":
        return f"- Expression scale: {expression_scale_label}. TPM values were read from cached GDC STAR-count files and transformed as log2(TPM + 1)."
    if expression_scale == "log2_fpkm":
        return f"- Expression scale: {expression_scale_label}. FPKM values were read from cached GDC STAR-count files and transformed as log2(FPKM + 1)."
    if expression_scale == "log2_fpkm_uq":
        return f"- Expression scale: {expression_scale_label}. Upper-quartile normalized FPKM values were read from cached GDC STAR-count files and transformed as log2(FPKM-UQ + 1)."
    if expression_scale == "log2_cpm":
        return f"- Expression scale: {expression_scale_label}. CPM was computed from unstranded STAR counts in count_matrix.tsv using sample library sizes, then transformed as log2(CPM + 1)."
    return f"- Expression scale: {expression_scale_label}."


def signature_methodology_lines(request_payload: dict) -> list[str]:
    signature_a = request_payload.get("signature_a")
    signature_b = request_payload.get("signature_b")
    if signature_a and signature_b:
        return [
            f"- Signature A: {format_signature_name(signature_a, 'Signature A')}; score method: {signature_a.get('signature_method') or 'not available'}; genes: {format_signature_genes(signature_a)}.",
            f"- Signature B: {format_signature_name(signature_b, 'Signature B')}; score method: {signature_b.get('signature_method') or 'not available'}; genes: {format_signature_genes(signature_b)}.",
        ]
    method = request_payload.get("signature_method")
    if method and method != "single":
        return [
            f"- RNA signature score method: {method}; genes: {format_signature_genes(request_payload)}.",
        ]
    return []


def format_signature_name(signature: dict, fallback: str) -> str:
    return str(signature.get("name") or fallback)


def format_signature_genes(signature: dict) -> str:
    entries = signature.get("signature_genes") or []
    if entries:
        formatted = []
        for entry in entries:
            gene = entry.get("gene_symbol") or entry.get("query") or ""
            weight = entry.get("weight")
            formatted.append(f"{gene}:{weight}" if weight not in (None, 1, 1.0) else str(gene))
        return ", ".join(item for item in formatted if item) or "not available"
    return str(signature.get("gene_symbol") or "not available")


def csv_methodology_text(request_payload: dict) -> str:
    if request_payload.get("signature_a") and request_payload.get("signature_b"):
        return (
            "- CSV contains the exact patient-level records used for the analysis, including combined score, "
            "signature A score, signature B score, combined group, per-signature groups, survival time, event status "
            "and selected metadata."
        )
    return "- CSV contains the exact patient-level records used for the analysis, including expression value, survival time, event status, assigned group and selected metadata."


def interaction_method_text(metrics: dict) -> str:
    models = metrics.get("signature_interaction_cox_models") or []
    if not models:
        return "- Two-signature interaction Cox models were not applicable for this analysis."
    return (
        "- For two-signature analyses, continuous Cox interaction models were fitted as "
        "Surv(time, event) ~ signature_A_z + signature_B_z + signature_A_z:signature_B_z, "
        "with additional stage/grade-adjusted variants when complete covariate data and model rank were sufficient. "
        "Signature scores were z-scored within the analyzed patient set before fitting."
    )


def endpoint_method_text(endpoint: str, source: str | None) -> str:
    if source == "tcga_cdr":
        return (
            "- Endpoint data were obtained from the TCGA Clinical Data Resource (TCGA-CDR), "
            "which standardizes OS, PFI, DFI and DSS outcomes across TCGA cancer cohorts."
        )
    if endpoint == "OS":
        return (
            "- Overall survival was derived from TCGA clinical/sample metadata. Event status was coded as 1 for "
            "vital_status = Dead and 0 for vital_status = Alive; time used days_to_death for deceased patients and "
            "days_to_last_follow_up or days_to_last_known_disease_status for censored patients."
        )
    return "- Endpoint data source was recorded in the exported patient-level CSV."


def stratification_method_text(cutpoint_method: str, cutpoint_details: dict) -> str:
    if cutpoint_details.get("combination") == "signature_a_x_signature_b":
        method = cutpoint_details.get("method", cutpoint_method)
        if method == "median":
            return "- Cutpoint method: each signature was independently split at its median score, then patient labels were crossed to produce combined groups such as Low_High and High_High."
        if method == "tertiles":
            return "- Cutpoint method: each signature was independently split into low, middle and high tertiles, then patient labels were crossed to produce up to nine combined groups."
        return f"- Cutpoint method: each signature was independently stratified by {method}, then labels were crossed to produce combined groups."
    if cutpoint_method == "maxstat":
        return "- Cutpoint method: maximally selected rank statistic via survminer::surv_cutpoint with minprop = 0.15. This is exploratory and can inflate apparent significance if not externally validated."
    if cutpoint_method == "median":
        return "- Cutpoint method: median expression threshold, producing low and high expression groups of approximately equal size."
    if cutpoint_method == "tertiles":
        return "- Cutpoint method: tertiles, producing low, middle and high expression groups."
    if cutpoint_method == "upper_quartile":
        return "- Cutpoint method: upper quartile versus the remaining samples, comparing the top 25% expression group against all others."
    if cutpoint_method == "upper_lower_quartile":
        return "- Cutpoint method: outer quartiles, comparing the top 25% expression group against the bottom 25% while excluding the middle 50%."
    if cutpoint_method == "percentile":
        percentile = cutpoint_details.get("percentile", cutpoint_details.get("method", "custom"))
        return f"- Cutpoint method: user-selected percentile threshold ({percentile})."
    return f"- Cutpoint method: {cutpoint_method}."


def format_filter(values) -> str:
    if not values:
        return "all available values"
    return ", ".join(str(value) for value in values)


def format_optional(value) -> str:
    if value is None or value == "":
        return "not applied"
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value)


def format_count_dict(value) -> str:
    if not value:
        return "none"
    if not isinstance(value, dict):
        return str(value)
    return ", ".join(f"{key}: {count}" for key, count in value.items())


def format_cox_models(value) -> str:
    if not value:
        return "none"
    if not isinstance(value, list):
        return str(value)
    completed = [item.get("label") or item.get("model") for item in value if item.get("status") == "completed"]
    return ", ".join(str(item) for item in completed if item) or "none"


def software_versions(metrics: dict) -> dict[str, str]:
    versions = {
        "Python": platform.python_version(),
        "FastAPI": installed_version("fastapi"),
        "SQLAlchemy": installed_version("SQLAlchemy"),
        "psycopg": installed_version("psycopg"),
        "pydantic-settings": installed_version("pydantic-settings"),
    }
    r_versions = metrics.get("software_versions") or {}
    for name, value in r_versions.items():
        key = "R" if name == "R" else f"R/{name}"
        versions[key] = str(value)
    return versions


def installed_version(package_name: str) -> str:
    try:
        return importlib.metadata.version(package_name)
    except importlib.metadata.PackageNotFoundError:
        return "not available"


def compute_maxstat_cutpoint(settings: Settings, analysis_id: str, records: list[dict]) -> dict:
    analysis_dir = settings.artifact_dir / analysis_id
    analysis_dir.mkdir(parents=True, exist_ok=True)
    minprop = 0.15
    validate_maxstat_records(records, minprop=minprop)

    input_path = analysis_dir / "maxstat_input.json"
    output_path = analysis_dir / "maxstat_cutpoint.json"
    payload = {
        "records": records,
        "minprop": minprop,
        "output_path": str(output_path),
    }
    input_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    result = subprocess.run(
        ["Rscript", str(settings.maxstat_script_path), str(input_path)],
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        raise ValueError(maxstat_error_message(result.stderr or result.stdout))

    return json.loads(output_path.read_text(encoding="utf-8"))


def validate_maxstat_records(records: list[dict], minprop: float = 0.15) -> None:
    complete: list[tuple[float, float, int]] = []
    for record in records:
        try:
            expression_value = float(record["expression_value"])
            time_days = float(record.get("time_days", record.get("os_time_days")))
            event = int(record.get("event", record.get("os_event")))
        except (KeyError, TypeError, ValueError):
            continue
        if math.isfinite(expression_value) and math.isfinite(time_days):
            complete.append((expression_value, time_days, event))

    n_records = len(complete)
    if n_records < 10:
        raise ValueError("Maxstat requires at least 10 complete patients with usable endpoint data and expression.")
    if sum(event for _, _, event in complete) == 0:
        raise ValueError("Maxstat requires at least one survival event after filters.")

    values = [expression for expression, _, _ in complete]
    unique_values = sorted(set(values))
    if len(unique_values) < 2:
        raise ValueError("Maxstat requires expression variation after filters; use median/quartiles or choose another gene.")

    has_candidate = False
    for threshold in unique_values[:-1]:
        low = sum(1 for value in values if value <= threshold)
        high = n_records - low
        if low / n_records >= minprop and high / n_records >= minprop:
            has_candidate = True
            break
    if not has_candidate:
        min_group = math.ceil(n_records * minprop)
        raise ValueError(
            "Maxstat cannot find an eligible cutpoint after filters. "
            f"It requires at least {min_group} patients in each expression group (minprop={minprop}), "
            "but expression ties or the current distribution leave no valid split. "
            "Use median/quartiles, choose another gene, or relax filters."
        )


def maxstat_error_message(raw_message: str) -> str:
    text = raw_message or ""
    lower = text.lower()
    if "no data between minprop" in lower:
        return (
            "Maxstat cannot find an eligible cutpoint after filters. "
            "Expression ties or the current distribution leave no valid split with at least 15% of patients per group. "
            "Use median/quartiles, choose another gene, or relax filters."
        )
    if "requires at least 10" in lower:
        return "Maxstat requires at least 10 complete patients with usable endpoint data and expression."
    if "requires expression variation" in lower:
        return "Maxstat requires expression variation after filters; use median/quartiles or choose another gene."
    if "requires at least one survival event" in lower:
        return "Maxstat requires at least one survival event after filters."
    if "did not produce a finite cutpoint" in lower:
        return "Maxstat did not produce a finite cutpoint; use median/quartiles, choose another gene, or relax filters."
    return "Maxstat failed in R; use median/quartiles, choose another gene, or relax filters."
