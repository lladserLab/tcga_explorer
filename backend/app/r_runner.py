import csv
import hashlib
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
    csv_path = analysis_dir / "raw_data.csv"
    methodology_path = analysis_dir / "methodology.txt"

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

    metrics = json.loads(output_path.read_text(encoding="utf-8"))
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
        "csv": str(csv_path),
        "json": str(output_path),
        "txt": str(methodology_path),
    }
    return metrics


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
        f"- Gender filter: {format_filter(filters.get('genders'))}",
        f"- Race filter: {format_filter(filters.get('races'))}",
        f"- Minimum age at index: {format_optional(filters.get('age_min'))}",
        f"- Maximum age at index: {format_optional(filters.get('age_max'))}",
        f"- Maximum follow-up time in days: {format_optional(filters.get('max_time_days'))}",
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
        "",
        "Patient Stratification",
        stratification_method_text(cutpoint_method, cutpoint_details),
        f"- Final expression groups: {', '.join(group_levels)}",
        f"- Cutpoint details: {json.dumps(cutpoint_details, sort_keys=True)}",
        "",
        "Statistical Analysis",
        f"- Kaplan-Meier curves were fitted with survival::survfit using {endpoint_label.lower()} time and event status.",
        "- Group differences were tested with the log-rank test using survival::survdiff.",
        "- When exactly two expression groups were present, a univariable Cox proportional hazards model was fitted with survival::coxph to estimate the hazard ratio and 95% confidence interval.",
        f"- Log-rank p-value: {format_optional(metrics.get('logrank_p_value'))}",
        f"- Hazard ratio: {format_optional(metrics.get('hazard_ratio'))}",
        f"- Hazard ratio 95% CI: {format_optional(metrics.get('hr_conf_low'))} to {format_optional(metrics.get('hr_conf_high'))}",
        f"- Cox model p-value: {format_optional(metrics.get('hr_p_value'))}",
        "",
        "Plot Generation",
        "- Kaplan-Meier plots were generated in R with survminer::ggsurvplot and ggplot2.",
        f"- Confidence interval shown: {'yes' if show_confidence_interval else 'no'}",
        f"- Risk table shown: {'yes' if show_risk_table else 'no'}",
        f"- Plot title shown: {'yes' if plot_style.get('show_title') else 'no'}",
        f"- Plot title text: {plot_style.get('plot_title') or 'not used'}",
        f"- Palette: {', '.join(plot_style.get('palette') or [])}",
        f"- Font family: {plot_style.get('font_family') or 'sans'}",
        f"- Base font size: {plot_style.get('base_font_size') or 12}",
        f"- Axis tick-label font size: {plot_style.get('axis_text_size') or 11}",
        f"- Axis title font size: {plot_style.get('axis_title_size') or 12}",
        f"- Plot grid shown: {'yes' if plot_style.get('show_grid', True) else 'no'}",
        "",
        "Output Files",
        "- PNG contains the rendered Kaplan-Meier plot generated at analysis time.",
        "- SVG contains the rendered Kaplan-Meier plot and is generated on demand when requested for download.",
        "- CSV contains the exact patient-level records used for the analysis, including expression value, survival time, event status, assigned group and selected metadata.",
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
        "- Multivariable clinical adjustment and independent validation are recommended before drawing biological or translational conclusions.",
        "",
        "Software Versions",
    ]
    versions = software_versions(metrics)
    lines.extend(f"- {name}: {value}" for name, value in versions.items())
    lines.extend(
        [
            "",
            "Suggested citation wording",
            f"Kaplan-Meier survival analyses were performed using TCGA cancer cohort RNA-seq and clinical metadata from a database created at {database_created_at}, with data through {data_through}. The analyzed endpoint was {endpoint_label} ({endpoint}). When multiple eligible RNA-seq barcodes were available for the same TCGA participant, one sample was retained using a TCGA biospecimen priority rule before expression stratification. Gene expression was transformed as described above, patients were stratified according to the selected cutpoint rule, and survival differences were assessed with log-rank tests. For two-group comparisons, hazard ratios were estimated with univariable Cox proportional hazards models. Plots were generated in R using survival and survminer.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


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
