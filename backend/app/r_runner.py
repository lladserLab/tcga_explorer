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

from app.analysis_notices import (
    COMPETING_RISK_ENDPOINTS,
    ZSCORE_TRANSPORTABILITY_MESSAGE,
    competing_risk_message,
    signature_methods,
    uses_zscore_signature,
)
from app.attestation import (
    attestation_metadata,
    write_attestation_receipt,
)
from app.config import Settings
from app.external_covariates import ExternalCovariateContext
from app.reproduction_capsule import write_reproduction_capsule
from app.survival import SurvivalRecord


PANCANCER_COHORT_CSV_FIELDS = [
    "cohort",
    "cohort_label",
    "primary_site",
    "disease_type",
    "endpoint",
    "endpoint_label",
    "endpoint_source",
    "status",
    "code",
    "reason",
    "n_patients",
    "n_events",
    "expression_mean",
    "expression_sd",
    "hazard_ratio",
    "hr_conf_low",
    "hr_conf_high",
    "log_hr",
    "standard_error",
    "p_value",
    "common_scale_hazard_ratio",
    "common_scale_hr_conf_low",
    "common_scale_hr_conf_high",
    "common_scale_log_hr",
    "common_scale_standard_error",
    "common_scale_p_value",
    "common_scale_unit",
    "common_scale_eligible",
    "fdr",
    "ph_p_value",
    "ph_global_p_value",
    "time_varying_effect",
    "direction",
    "effect_category",
    "significant",
    "concordance",
    "selected_adjusted_model",
    "adjusted_status",
    "adjusted_reason",
    "adjusted_n_patients",
    "adjusted_n_events",
    "adjusted_hazard_ratio",
    "adjusted_hr_conf_low",
    "adjusted_hr_conf_high",
    "adjusted_log_hr",
    "adjusted_standard_error",
    "adjusted_p_value",
    "adjusted_common_scale_hazard_ratio",
    "adjusted_common_scale_hr_conf_low",
    "adjusted_common_scale_hr_conf_high",
    "adjusted_common_scale_log_hr",
    "adjusted_common_scale_standard_error",
    "adjusted_common_scale_p_value",
    "adjusted_fdr",
    "adjusted_ph_p_value",
    "adjusted_ph_global_p_value",
    "adjusted_time_varying_effect",
    "adjusted_direction",
    "adjusted_effect_category",
    "adjusted_significant",
    "clinical_sensitivity",
    "sample_selection",
    "warnings",
    "cox_models",
]

PANCANCER_PATIENT_CSV_FIELDS = [
    "cohort",
    "cohort_label",
    "endpoint",
    "endpoint_label",
    "endpoint_source",
    "patient_id",
    "sample_barcode",
    "expression_value",
    "time_days",
    "event",
    "sample_type",
    "stage",
    "grade",
    "gender",
    "race",
    "age_at_index",
]
INTEGRITY_SCOPE = {
    "threat_model": (
        "Detect accidental analysis drift, file corruption and incomplete transfer "
        "relative to the values recorded in this export."
    ),
    "not_an_authenticity_proof": (
        "SHA-256 digests alone do not prove origin. When present, the detached "
        "Ed25519 server receipt binds the exact audit report to the public key "
        "published by the declared HTTPS issuer; it does not establish scientific "
        "correctness or an append-only publication time."
    ),
    "reproducibility_hash_boundary": (
        "The reproducibility hash binds the fields named in "
        "reproducibility_hash_definition.payload_fields."
    ),
    "artifact_boundary": (
        "Rendered plots and methodology files are outside the reproducibility hash "
        "and are protected separately by artifact byte counts and SHA-256 checksums."
    ),
}


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


def score_transportability_context(
    request_payload: dict | None = None,
    metrics: dict | None = None,
) -> dict:
    methods = signature_methods(
        request_payload=request_payload,
        metrics=metrics,
    )
    applies = "zscore" in methods
    context = {
        "applicable": applies,
        "score_methods": methods,
    }
    if applies:
        context.update(
            {
                "status": "run_specific",
                "standardization_population": (
                    "Expression-complete patients eligible after the endpoint and "
                    "filter rules in this run."
                ),
                "numerically_transportable_across_runs": False,
                "interpretation": ZSCORE_TRANSPORTABILITY_MESSAGE,
            }
        )
    else:
        context.update(
            {
                "status": "not_applicable",
                "reason": "No z-score signature method was requested.",
            }
        )
    return context


def endpoint_estimand_context(
    endpoint: str | None,
    competing_risks: dict | None = None,
) -> dict:
    normalized = str(endpoint or "").upper()
    competing_risks = competing_risks or {}
    cumulative_incidence = competing_risks.get("cumulative_incidence") or {}
    models = [
        *(competing_risks.get("grouped_fine_gray_models") or []),
        *(competing_risks.get("continuous_fine_gray_models") or []),
    ]
    context = {
        "endpoint": normalized or None,
        "competing_risk_context_applicable": (
            normalized in COMPETING_RISK_ENDPOINTS
        ),
    }
    if normalized in COMPETING_RISK_ENDPOINTS:
        context.update(
            {
                "cause_specific_estimand": (
                    "Kaplan-Meier event-free survival and cause-specific Cox "
                    "hazard with competing deaths censored at their recorded time."
                ),
                "subdistribution_estimand": (
                    "Nonparametric cumulative incidence and Fine-Gray "
                    "subdistribution hazard for the event of interest."
                ),
                "competing_event_handling": (
                    "Status 2 is censored only for Kaplan-Meier/cause-specific "
                    "Cox and retained as a competing event for cumulative "
                    "incidence/Fine-Gray."
                ),
                "cumulative_incidence_provided": (
                    cumulative_incidence.get("status") == "completed"
                ),
                "fine_gray_provided": any(
                    model.get("status") == "completed"
                    for model in models
                ),
                "competing_risk_status": competing_risks.get("status"),
                "coding": competing_risks.get("coding") or {},
                "interpretation": competing_risk_message(normalized),
            }
        )
    return context


def interpretation_limitations(
    request_payload: dict | None = None,
    metrics: dict | None = None,
    *,
    endpoints: list[str] | None = None,
) -> list[str]:
    limitations: list[str] = []
    if uses_zscore_signature(
        request_payload=request_payload,
        metrics=metrics,
    ):
        limitations.append(ZSCORE_TRANSPORTABILITY_MESSAGE)

    endpoint_values = {
        str(value or "").upper()
        for value in (
            endpoints
            or [
                (metrics or {}).get("endpoint")
                or (request_payload or {}).get("endpoint")
            ]
        )
        if value
    }
    for endpoint in sorted(endpoint_values & COMPETING_RISK_ENDPOINTS):
        limitations.append(competing_risk_message(endpoint))
    return limitations


def write_records_csv(records: list[SurvivalRecord], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    external_names: set[str] = set()
    for record in records:
        row = record.as_dict()
        external = row.pop("external_covariates", {}) or {}
        external_names.update(external)
        rows.append((row, external))
    fieldnames = list(rows[0][0].keys()) + [
        f"external__{name}" for name in sorted(external_names)
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row, external in rows:
            writer.writerow(
                {
                    **row,
                    **{
                        f"external__{name}": external.get(name)
                        for name in sorted(external_names)
                    },
                }
            )


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
    rmst_tau: dict | None = None,
    continuous_records: list[SurvivalRecord] | None = None,
    external_covariates: ExternalCovariateContext | None = None,
) -> dict:
    analysis_dir = settings.artifact_dir / analysis_id
    analysis_dir.mkdir(parents=True, exist_ok=True)

    input_path = analysis_dir / "input.json"
    output_path = analysis_dir / "metrics.json"
    png_path = analysis_dir / "plot.png"
    svg_path = analysis_dir / "plot.svg"
    cox_forest_png_path = analysis_dir / "cox_forest.png"
    cox_forest_svg_path = analysis_dir / "cox_forest.svg"
    continuous_effect_png_path = analysis_dir / "continuous_effect.png"
    continuous_effect_svg_path = analysis_dir / "continuous_effect.svg"
    cumulative_incidence_png_path = analysis_dir / "cumulative_incidence.png"
    cumulative_incidence_svg_path = analysis_dir / "cumulative_incidence.svg"
    csv_path = analysis_dir / "raw_data.csv"
    continuous_csv_path = analysis_dir / "continuous_data.csv"
    methodology_path = analysis_dir / "methodology.txt"
    clear_stale_analysis_artifacts(
        [
            output_path,
            png_path,
            svg_path,
            cox_forest_png_path,
            cox_forest_svg_path,
            continuous_effect_png_path,
            continuous_effect_svg_path,
            cumulative_incidence_png_path,
            cumulative_incidence_svg_path,
            csv_path,
            continuous_csv_path,
            methodology_path,
            analysis_dir / "audit_report.json",
            analysis_dir / "audit_report.html",
            analysis_dir / "svg_input.json",
            analysis_dir / "svg_metrics.json",
            analysis_dir / "rerun_analysis.R",
            analysis_dir / "km_analysis.R",
            analysis_dir / "clinical_covariates.R",
            analysis_dir / "cox_diagnostics.R",
            analysis_dir / "competing_risks.R",
            analysis_dir / "renv.lock",
            analysis_dir / "Dockerfile.reproduce",
            analysis_dir / "REPRODUCE.md",
            analysis_dir / "reproduction_manifest.json",
        ]
    )

    write_records_csv(records, csv_path)
    if continuous_records:
        write_records_csv(continuous_records, continuous_csv_path)
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
        "rmst_tau": rmst_tau or {},
        "adjustment_covariates": (
            (request_payload or {}).get("adjustment_covariates") or []
        ),
        "external_adjustment_covariates": (
            external_covariates.selected_names if external_covariates else []
        ),
        "external_covariate_definitions": (
            external_covariates.definitions if external_covariates else []
        ),
        "external_covariate_qc": (
            external_covariates.qc if external_covariates else {}
        ),
        "records": [record.as_dict() for record in records],
        "continuous_records": [
            record.as_dict() for record in (continuous_records or [])
        ],
        "show_confidence_interval": show_confidence_interval,
        "show_risk_table": show_risk_table,
        "plot_style": plot_style,
        "png_path": str(png_path),
        "svg_path": str(svg_path),
        "cox_forest_png_path": str(cox_forest_png_path),
        "cox_forest_svg_path": str(cox_forest_svg_path),
        "continuous_effect_png_path": str(continuous_effect_png_path),
        "continuous_effect_svg_path": str(continuous_effect_svg_path),
        "cumulative_incidence_png_path": str(cumulative_incidence_png_path),
        "cumulative_incidence_svg_path": str(cumulative_incidence_svg_path),
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
    if external_covariates is not None:
        metrics["external_covariates"] = external_covariates.qc
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
    reproduction_paths = write_reproduction_capsule(
        analysis_dir,
        r_script_path=settings.r_script_path,
        renv_lock_path=Path(__file__).resolve().parents[1] / "renv.lock",
    )
    metrics["artifact_paths"] = {
        "png": str(png_path),
        "svg": str(svg_path),
        "cox_forest_png": str(cox_forest_png_path) if cox_forest_png_path.exists() else None,
        "cox_forest_svg": str(cox_forest_svg_path),
        "continuous_effect_png": str(continuous_effect_png_path) if continuous_effect_png_path.exists() else None,
        "continuous_effect_svg": str(continuous_effect_svg_path),
        "cumulative_incidence_png": str(cumulative_incidence_png_path) if cumulative_incidence_png_path.exists() else None,
        "cumulative_incidence_svg": str(cumulative_incidence_svg_path),
        "csv": str(csv_path),
        "continuous_csv": str(continuous_csv_path) if continuous_csv_path.exists() else None,
        "json": str(output_path),
        "txt": str(methodology_path),
        "input": str(input_path),
        **reproduction_paths,
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
    continuous_records: list[SurvivalRecord] | None = None,
    analysis_warnings: list[str] | None = None,
    data_dates: dict | None = None,
    scoring_provenance: dict | None = None,
    data_provenance: dict | None = None,
) -> dict:
    analysis_dir = settings.artifact_dir / analysis_id
    analysis_dir.mkdir(parents=True, exist_ok=True)
    json_path = analysis_dir / "audit_report.json"
    html_path = analysis_dir / "audit_report.html"
    generated_at = datetime.now(timezone.utc).isoformat()
    record_payload = [record.as_dict() for record in records]
    record_digest = stable_hash({"records": record_payload})
    continuous_record_payload = [
        record.as_dict() for record in (continuous_records or [])
    ]
    continuous_record_digest = (
        stable_hash({"records": continuous_record_payload})
        if continuous_record_payload
        else None
    )
    median_status = median_survival_status(metrics)
    core_results = audit_core_results(metrics, median_status)
    endpoint_value = metrics.get("endpoint") or request_payload.get("endpoint")
    score_context = score_transportability_context(request_payload, metrics)
    endpoint_context = endpoint_estimand_context(
        endpoint_value,
        metrics.get("competing_risks") or {},
    )
    method_limitations = interpretation_limitations(request_payload, metrics)
    server_attestation = attestation_metadata(
        settings,
        subject_type="survival_analysis",
        subject_id=analysis_id,
    )
    reproducibility_payload = {
        "request": request_payload,
        "data_dates": data_dates or {},
        "data_provenance": data_provenance or {},
        "scoring_provenance_sha256": stable_hash(scoring_provenance or {}),
        "record_digest": record_digest,
        "continuous_record_digest": continuous_record_digest,
        "core_results": core_results,
    }
    report = {
        "schema_version": "tcga-trace-analysis-audit-v4",
        "report_type": "survival_analysis_audit",
        "analysis_id": analysis_id,
        "generated_at": generated_at,
        "reproducibility_hash": stable_hash(reproducibility_payload),
        "integrity_scope": INTEGRITY_SCOPE,
        "server_attestation": server_attestation,
        "reproducibility_hash_definition": {
            "algorithm": "sha256 over canonical JSON with sorted keys and compact separators",
            "payload_fields": [
                "request",
                "data_dates",
                "data_provenance",
                "scoring_provenance_sha256",
                "record_digest",
                "continuous_record_digest",
                "core_results",
            ],
            "artifact_checksums": "Artifact files are not included in reproducibility_hash; their SHA-256 values are reported separately under artifacts.",
        },
        "request": request_payload,
        "pipeline": {
            "version": request_payload.get("pipeline_version"),
            "software_versions": software_versions(metrics),
        },
        "data": {
            "cohort": request_payload.get("cohort"),
            "data_dates": data_dates or {},
            "endpoint": {
                "value": endpoint_value,
                "label": metrics.get("endpoint_label"),
                "source": metrics.get("endpoint_source"),
                "qc": metrics.get("endpoint_qc"),
                "estimand_context": endpoint_context,
            },
            "expression_scale": {
                "value": metrics.get("expression_scale") or request_payload.get("expression_scale"),
                "label": metrics.get("expression_scale_label"),
            },
            "provenance": data_provenance or {},
        },
        "analysis_design": {
            "gene_symbol": request_payload.get("gene_symbol"),
            "reported_marker": metrics.get("signature", {}).get("label") or request_payload.get("gene_symbol"),
            "signature": metrics.get("signature"),
            "combined_signature": metrics.get("combined_signature"),
            "scoring_provenance_sha256": stable_hash(scoring_provenance or {}),
            "scoring_provenance": scoring_provenance or {},
            "cutpoint_method": request_payload.get("cutpoint_method") or request_payload.get("combination_method"),
            "cutpoint_details": metrics.get("cutpoint_details"),
            "filters": request_payload.get("filters") or {},
            "adjustment_covariates": (
                request_payload.get("adjustment_covariates") or []
            ),
            "external_adjustment_covariates": (
                request_payload.get("external_adjustment_covariates") or []
            ),
            "external_covariates": external_covariate_audit_context(
                request_payload,
                metrics,
            ),
            "clinical_adjustment": metrics.get("clinical_adjustment") or {},
            "score_transportability": score_context,
            "time_unit": metrics.get("time_unit") or request_payload.get("time_unit"),
            "plot_style": request_payload.get("plot_style") or {},
        },
        "cohort_selection": {
            "sample_selection": metrics.get("sample_selection"),
            "patient_record_count": len(record_payload),
            "patient_records_sha256": record_digest,
            "patient_records": record_payload,
            "stratified_patient_record_count": len(record_payload),
            "stratified_patient_records_sha256": record_digest,
            "continuous_patient_record_count": len(continuous_record_payload),
            "continuous_patient_records_sha256": continuous_record_digest,
            "continuous_patient_records": continuous_record_payload,
        },
        "results": core_results,
        "quality": {
            "summary": metrics.get("quality"),
            "warnings": list(dict.fromkeys((analysis_warnings or []) + (metrics.get("warnings") or []))),
            "limitations": [
                "Retrospective exploratory analysis based on public TCGA cohort data.",
                "Continuous Cox and spline estimates describe association, not causality, and can remain confounded by unmeasured clinical or biological factors.",
                "Kaplan-Meier grouping does not establish causality and is sensitive to cutpoint choice.",
                "Optimized cutpoints such as maxstat can overestimate apparent significance unless externally validated.",
                adjustment_limitation_text(request_payload),
                *method_limitations,
            ],
        },
        "artifacts": audit_artifact_manifest(artifact_paths),
    }
    report = json_safe_value(report)
    json_path.write_text(json.dumps(report, ensure_ascii=False, allow_nan=False, indent=2), encoding="utf-8")
    html_path.write_text(render_audit_html(report), encoding="utf-8")
    receipt = write_attestation_receipt(
        settings,
        subject_type="survival_analysis",
        subject_id=analysis_id,
        audit_path=json_path,
        reproducibility_hash=report["reproducibility_hash"],
        report_schema_version=report["schema_version"],
    )
    return {
        "json": str(json_path),
        "html": str(html_path),
        "schema_version": report["schema_version"],
        "generated_at": generated_at,
        "reproducibility_hash": report["reproducibility_hash"],
        "server_attestation": receipt,
        "patient_records_sha256": record_digest,
        "continuous_patient_records_sha256": continuous_record_digest,
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
        "competing_risks": metrics.get("competing_risks"),
        "continuous_analysis": metrics.get("continuous_analysis"),
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


def external_covariate_audit_context(
    request_payload: dict,
    metrics: dict,
) -> dict:
    dataset = request_payload.get("external_covariates") or {}
    selected = request_payload.get("external_adjustment_covariates") or []
    definitions = {
        item.get("name"): item
        for item in dataset.get("definitions") or []
        if item.get("name")
    }
    return {
        "status": (
            (metrics.get("external_covariates") or {}).get("status")
            or ("selected" if selected else "not_provided")
        ),
        "schema_version": dataset.get("schema_version"),
        "source_label": dataset.get("source_label"),
        "selected_covariates": selected,
        "selected_definitions": [
            definitions[name]
            for name in selected
            if name in definitions
        ],
        "quality_control": metrics.get("external_covariates") or {},
        "coding": (
            (metrics.get("clinical_adjustment") or {}).get(
                "external_covariate_definitions"
            )
            or []
        ),
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
    endpoint_context = endpoint.get("estimand_context") or {}
    analysis = report.get("analysis_design") or {}
    score_context = analysis.get("score_transportability") or {}
    external_context = analysis.get("external_covariates") or {}
    external_qc = external_context.get("quality_control") or {}
    data_provenance = data.get("provenance") or {}
    scoring_provenance = analysis.get("scoring_provenance") or {}
    quality = report.get("quality") or {}
    group_counts = results.get("group_counts") or {}
    event_counts = results.get("event_counts") or {}
    medians = results.get("median_survival_days") or {}
    median_status = results.get("median_survival_status") or {}
    rmst = results.get("rmst") or {}
    continuous_models = (
        (results.get("continuous_analysis") or {}).get("linear_models") or []
    )
    cox_models = results.get("cox_models") or []
    interaction_models = results.get("signature_interaction_cox_models") or []
    artifacts = report.get("artifacts") or {}
    server_attestation = report.get("server_attestation") or {}
    warnings = quality.get("warnings") or []
    limitations = quality.get("limitations") or []

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
    def temporal_cell(model: dict, period: str, field: str) -> object:
        return (
            (((model.get("time_varying_effect") or {}).get("periods") or {}).get(period) or {}).get(field)
        )

    def cox_row(model: dict, effect: dict | None = None) -> str:
        effect = effect or model
        temporal = model.get("time_varying_effect") or {}
        return (
        "<tr>"
        f"<td>{esc(model.get('label') or model.get('model'))}</td>"
        f"<td>{esc(', '.join(model.get('covariates') or []) or 'none')}</td>"
        f"<td>{esc(model.get('n_patients'))}</td>"
        f"<td>{esc(model.get('n_events'))}</td>"
        f"<td>{esc(effect.get('hazard_ratio'))}</td>"
        f"<td>{esc(effect.get('p_value'))}</td>"
        f"<td>{esc(model.get('ph_p_value'))}</td>"
        f"<td>{esc(model.get('ph_global_p_value'))}</td>"
        f"<td>{esc(temporal.get('status'))}</td>"
        f"<td>{esc(temporal_cell(model, 'early', 'hazard_ratio'))}</td>"
        f"<td>{esc(temporal_cell(model, 'late', 'hazard_ratio'))}</td>"
        f"<td>{esc(model.get('status'))}</td>"
        f"<td>{esc(model.get('reason'))}</td>"
        "</tr>"
        )

    continuous_cox_rows = "\n".join(
        cox_row(model) for model in continuous_models
    )
    cox_rows = "\n".join(
        cox_row(model) for model in cox_models
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
        cox_row(model, model.get("interaction_term") or {})
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
    expression_file_rows = "\n".join(
        "<tr>"
        f"<td>{esc(item.get('logical_name'))}</td>"
        f"<td>{esc(item.get('filename'))}</td>"
        f"<td>{esc(item.get('bytes'))}</td>"
        f"<td><code>{esc(item.get('sha256'))}</code></td>"
        "</tr>"
        for item in data_provenance.get("expression_files") or []
    )
    external_definitions = {
        item.get("name"): item
        for item in external_context.get("selected_definitions") or []
        if item.get("name")
    }
    external_variable_rows = "\n".join(
        "<tr>"
        f"<td>{esc(item.get('label') or item.get('name'))}</td>"
        f"<td><code>{esc(item.get('name'))}</code></td>"
        f"<td>{esc(item.get('value_type'))}</td>"
        f"<td>{esc(external_covariate_definition_text(external_definitions.get(item.get('name')) or item))}</td>"
        f"<td>{esc(item.get('analysis_population_non_missing'))}</td>"
        f"<td>{esc(item.get('analysis_population_missing'))}</td>"
        f"<td>{esc(item.get('analysis_population_missing_fraction'))}</td>"
        "</tr>"
        for item in external_qc.get("variables") or []
        if item.get("selected")
    ) or (
        "<tr><td colspan=\"7\">No external adjustment covariates were selected.</td></tr>"
    )
    scoring_population = (
        scoring_provenance
        if scoring_provenance.get("analysis_type") != "combined_signatures"
        else {
            "complete_case_barcode_count": min(
                (scoring_provenance.get("signature_a") or {}).get("complete_case_barcode_count") or 0,
                (scoring_provenance.get("signature_b") or {}).get("complete_case_barcode_count") or 0,
            ),
            "population_rule": "Both audited signature-specific eligible populations were intersected.",
        }
    )
    warning_items = "\n".join(f"<li>{esc(warning)}</li>" for warning in warnings) or "<li>None reported.</li>"
    limitation_items = (
        "\n".join(f"<li>{esc(item)}</li>" for item in limitations)
        or "<li>None reported.</li>"
    )
    interpretation_items = [
        context.get("interpretation")
        for context in (score_context, endpoint_context)
        if context.get("applicable", context.get("competing_risk_context_applicable"))
        and context.get("interpretation")
    ]
    interpretation_list = (
        "\n".join(f"<li>{esc(item)}</li>" for item in interpretation_items)
        or "<li>No endpoint- or score-specific interpretation context applies.</li>"
    )
    json_payload = html.escape(json.dumps(report, ensure_ascii=False, indent=2), quote=False)

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>TCGA-TRACE audit report {esc(report.get('analysis_id'))}</title>
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
  <h1>TCGA-TRACE Survival Analysis Audit Report</h1>
  <p class="hash">Analysis ID: <code>{esc(report.get('analysis_id'))}</code></p>
  <p class="hash">Reproducibility hash: <code>{esc(report.get('reproducibility_hash'))}</code></p>
  <p><strong>Integrity scope:</strong> {esc((report.get("integrity_scope") or {}).get("threat_model"))}
  {esc((report.get("integrity_scope") or {}).get("not_an_authenticity_proof"))}</p>

  <h2>Server Attestation</h2>
  <table>
    {rows([
        ("Status", server_attestation.get("status")),
        ("Algorithm", server_attestation.get("algorithm")),
        ("Issuer", server_attestation.get("issuer")),
        ("Key ID", server_attestation.get("key_id")),
        ("Public key", server_attestation.get("public_key_url")),
        ("Detached receipt", server_attestation.get("receipt_url")),
        ("Scope", server_attestation.get("scope")),
        ("Trust model", server_attestation.get("trust_model")),
    ])}
  </table>

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

	  <h2>Data And Scoring Provenance</h2>
  <table>
    {rows([
        ("Audit schema", report.get("schema_version")),
        ("Publication snapshot hash", (data_provenance.get("publication_snapshot") or {}).get("manifest_hash")),
        ("Expression source", data_provenance.get("expression_source")),
        ("Selected GDC files", data_provenance.get("selected_gdc_file_count")),
        ("Scoring provenance SHA-256", analysis.get("scoring_provenance_sha256")),
	        ("Scoring population", scoring_population.get("complete_case_barcode_count")),
	        ("Scoring population rule", scoring_population.get("population_rule")),
	        ("Score transportability", score_context.get("status")),
	    ])}
	  </table>
  <table>
    <thead><tr><th>Expression artifact</th><th>Filename</th><th>Bytes</th><th>SHA-256</th></tr></thead>
    <tbody>{expression_file_rows}</tbody>
	  </table>

	  <h2>Endpoint And Score Interpretation</h2>
	  <ul>{interpretation_list}</ul>

  <h2>External Covariates</h2>
  <table>
    {rows([
        ("Status", external_context.get("status")),
        ("Source label", external_context.get("source_label")),
        ("Dataset SHA-256", external_qc.get("dataset_sha256")),
        ("Rows supplied", external_qc.get("n_rows")),
        ("Rows matched to cohort", external_qc.get("cohort_matched_rows")),
        ("Rows unmatched to cohort", external_qc.get("unmatched_rows")),
    ])}
  </table>
  <table>
    <thead><tr><th>Variable</th><th>Name</th><th>Type</th><th>Coding</th><th>Complete</th><th>Missing</th><th>Missing fraction</th></tr></thead>
    <tbody>{external_variable_rows}</tbody>
  </table>

  <h2>Survival Groups</h2>
  <table>
    <thead><tr><th>Group</th><th>Patients</th><th>Events</th><th>Median days</th><th>Median status</th></tr></thead>
    <tbody>{group_rows}</tbody>
  </table>

  <h2>Continuous Cox Models</h2>
  <table>
    <thead><tr><th>Model</th><th>Covariates</th><th>Patients</th><th>Events</th><th>HR</th><th>p</th><th>PH marker p</th><th>PH global p</th><th>Temporal status</th><th>HR 0-2 y</th><th>HR &gt;2 y</th><th>Status</th><th>Reason</th></tr></thead>
    <tbody>{continuous_cox_rows}</tbody>
  </table>

  <h2>Grouped Cox Models</h2>
  <table>
    <thead><tr><th>Model</th><th>Covariates</th><th>Patients</th><th>Events</th><th>HR</th><th>p</th><th>PH marker p</th><th>PH global p</th><th>Temporal status</th><th>HR 0-2 y</th><th>HR &gt;2 y</th><th>Status</th><th>Reason</th></tr></thead>
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
    <thead><tr><th>Model</th><th>Covariates</th><th>Patients</th><th>Events</th><th>Interaction HR</th><th>Interaction p</th><th>PH interaction p</th><th>PH global p</th><th>Temporal status</th><th>HR 0-2 y</th><th>HR &gt;2 y</th><th>Status</th><th>Reason</th></tr></thead>
    <tbody>{interaction_rows}</tbody>
  </table>

	  <h2>Warnings And Limitations</h2>
	  <h3>Warnings</h3>
	  <ul>{warning_items}</ul>
	  <h3>Limitations</h3>
	  <ul>{limitation_items}</ul>

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
    return normalize_maxstat_result(
        json.loads(output_path.read_text(encoding="utf-8"))
    )


def normalize_maxstat_result(result: dict) -> dict:
    normalized = dict(result)
    try:
        corrected = float(normalized.get("corrected_p_value"))
    except (TypeError, ValueError):
        return normalized
    if not math.isfinite(corrected):
        return normalized
    raw_value = normalized.get("corrected_p_raw_value")
    try:
        raw = float(raw_value)
    except (TypeError, ValueError):
        raw = corrected
    bounded = min(1.0, max(0.0, corrected))
    normalized["corrected_p_raw_value"] = raw
    normalized["corrected_p_value"] = bounded
    normalized["corrected_p_clamped"] = bool(
        normalized.get("corrected_p_clamped")
        or not math.isclose(corrected, bounded, rel_tol=0.0, abs_tol=0.0)
        or not math.isclose(raw, bounded, rel_tol=0.0, abs_tol=0.0)
    )
    return normalized


def write_pancancer_artifacts(
    settings: Settings,
    scan_id: str,
    request_payload: dict,
    prepared_cohorts: list[dict],
    result_payload: dict,
    r_software_versions: dict | None = None,
) -> dict:
    """Write a self-describing pan-cancer export without changing its estimand."""

    scan_dir = settings.artifact_dir / "pancancer" / scan_id
    scan_dir.mkdir(parents=True, exist_ok=True)
    cohort_csv_path = scan_dir / "cohort_results.csv"
    patient_csv_path = scan_dir / "patient_records.csv"
    methodology_path = scan_dir / "methodology.txt"
    audit_json_path = scan_dir / "audit_report.json"
    audit_html_path = scan_dir / "audit_report.html"

    cohort_rows = result_payload.get("results") or []
    patient_rows = pancancer_patient_rows(prepared_cohorts)
    actual_endpoints = sorted(
        {
            str(row.get("endpoint") or "").upper()
            for row in cohort_rows
            if row.get("endpoint")
        }
        | {
            str(cohort.get("endpoint") or "").upper()
            for cohort in prepared_cohorts
            if cohort.get("endpoint")
        }
    )
    score_context = score_transportability_context(
        request_payload=request_payload,
        metrics=result_payload,
    )
    endpoint_contexts = {
        endpoint: endpoint_estimand_context(endpoint)
        for endpoint in actual_endpoints
    }
    method_limitations = interpretation_limitations(
        request_payload=request_payload,
        metrics=result_payload,
        endpoints=actual_endpoints,
    )
    server_attestation = attestation_metadata(
        settings,
        subject_type="pancancer_survival",
        subject_id=scan_id,
    )
    write_dict_rows_csv(cohort_csv_path, cohort_rows, PANCANCER_COHORT_CSV_FIELDS)
    write_dict_rows_csv(patient_csv_path, patient_rows, PANCANCER_PATIENT_CSV_FIELDS)

    versions = software_versions({"software_versions": r_software_versions or {}})
    methodology_path.write_text(
        pancancer_methodology_text(
            scan_id=scan_id,
            request_payload=request_payload,
            result_payload=result_payload,
            patient_count=len(patient_rows),
            versions=versions,
        ),
        encoding="utf-8",
    )

    patient_digest = stable_hash({"records": patient_rows})
    core_results = {
        "summary": result_payload.get("summary"),
        "reference": result_payload.get("reference"),
        "effect_scale": result_payload.get("effect_scale"),
        "primary_meta_analysis": result_payload.get("meta_analysis"),
        "clinical_sensitivity": result_payload.get("clinical_sensitivity"),
        "cohort_results": cohort_rows,
    }
    reproducibility_payload = {
        "request": request_payload,
        "pipeline_version": result_payload.get("pipeline_version"),
        "data_version": result_payload.get("data_version"),
        "patient_records_sha256": patient_digest,
        "core_results": core_results,
    }
    artifact_paths = {
        "cohort_results": cohort_csv_path,
        "patient_records": patient_csv_path,
        "methodology": methodology_path,
        "raw_r_results": scan_dir / "cox_results.json",
    }
    report = {
        "schema_version": "tcga-trace-pancancer-audit-v3",
        "report_type": "pancancer_survival_audit",
        "scan_id": scan_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "reproducibility_hash": stable_hash(reproducibility_payload),
        "integrity_scope": INTEGRITY_SCOPE,
        "server_attestation": server_attestation,
        "reproducibility_hash_definition": {
            "algorithm": "sha256 over canonical JSON with sorted keys and compact separators",
            "payload_fields": [
                "request",
                "pipeline_version",
                "data_version",
                "patient_records_sha256",
                "core_results",
            ],
            "artifact_checksums": (
                "Artifact files are excluded from the reproducibility hash; "
                "their SHA-256 values are reported separately."
            ),
        },
        "request": request_payload,
        "pipeline": {
            "version": result_payload.get("pipeline_version"),
            "software_versions": versions,
        },
        "data": {
            "version": result_payload.get("data_version") or {},
            "patient_rows": len(patient_rows),
            "patient_records_sha256": patient_digest,
            "cohorts_requested": len(cohort_rows),
            "actual_endpoints": actual_endpoints,
            "endpoint_estimand_contexts": endpoint_contexts,
        },
        "analysis_design": {
            "cohort_estimand": (
                "Within-cohort hazard ratio per one standard-deviation increase "
                "in continuous expression, fitted as Surv(time, event) ~ expression_z. "
                "These descriptive effects are not pooled."
            ),
            "synthesis_estimand": (
                "Cross-cancer synthesis uses the algebraically equivalent "
                "unstandardized coefficient per +1 common input-score unit when "
                "that unit is transportable across cohorts."
            ),
            "sensitivity_estimands": [
                "Surv(time, event) ~ expression_z + stage_ordinal",
                "Surv(time, event) ~ expression_z + grade_ordinal",
                "Surv(time, event) ~ expression_z + stage_ordinal + grade_ordinal",
            ],
            "adjusted_model_selection": (
                "Availability-based hierarchy: stage+grade, then stage, then grade. "
                "The selected model never replaces the primary effect."
            ),
            "meta_analysis_policy": (
                "Eligible common-scale coefficients are synthesized with REML "
                "random effects, Hartung-Knapp-Sidik-Jonkman inference and a "
                "95% prediction interval when at least three cohorts are available. "
                "Mixed endpoints, mixed selected adjustment families and "
                "cohort-standardized z-score signatures are not pooled."
            ),
            "effect_scale": result_payload.get("effect_scale") or {},
            "score_transportability": score_context,
            "multiple_testing": {
                "primary": "Benjamini-Hochberg across completed primary cohort tests.",
                "adjusted_family": "Benjamini-Hochberg separately within each adjusted model family.",
                "selected_sensitivity": (
                    "Benjamini-Hochberg across the availability-selected adjusted "
                    "cohort tests; model selection does not use effect size or p-value."
                ),
            },
        },
        "results": core_results,
        "quality": {
            "warnings": list(
                dict.fromkeys(
                    (result_payload.get("warnings") or [])
                    + ((result_payload.get("clinical_sensitivity") or {}).get("notes") or [])
                )
            ),
            "limitations": [
                "Retrospective exploratory analysis based on public TCGA data.",
                "Ordinal adjustment assumes a linear log-hazard trend across major stage or grade scores.",
                "Adjusted models can use fewer patients because stage and grade are incompletely observed.",
                "Treatment, molecular subtype, tumor purity and immune composition are not modeled.",
                "Association does not establish causality or clinical utility.",
                *method_limitations,
            ],
        },
        "artifacts": audit_artifact_manifest(artifact_paths),
    }
    report = json_safe_value(report)
    audit_json_path.write_text(
        json.dumps(report, ensure_ascii=False, allow_nan=False, indent=2),
        encoding="utf-8",
    )
    audit_html_path.write_text(render_pancancer_audit_html(report), encoding="utf-8")
    receipt = write_attestation_receipt(
        settings,
        subject_type="pancancer_survival",
        subject_id=scan_id,
        audit_path=audit_json_path,
        reproducibility_hash=report["reproducibility_hash"],
        report_schema_version=report["schema_version"],
    )
    return {
        "schema_version": report["schema_version"],
        "generated_at": report["generated_at"],
        "reproducibility_hash": report["reproducibility_hash"],
        "server_attestation": receipt,
        "patient_records_sha256": patient_digest,
        "artifacts": report["artifacts"],
    }


def pancancer_patient_rows(prepared_cohorts: list[dict]) -> list[dict]:
    rows: list[dict] = []
    for cohort in prepared_cohorts:
        context = {
            "cohort": cohort.get("cohort"),
            "cohort_label": cohort.get("cohort_label"),
            "endpoint": cohort.get("endpoint"),
            "endpoint_label": cohort.get("endpoint_label"),
            "endpoint_source": cohort.get("endpoint_source"),
        }
        for record in cohort.get("records") or []:
            rows.append({**context, **record})
    return sorted(
        rows,
        key=lambda row: (
            str(row.get("cohort") or ""),
            str(row.get("patient_id") or ""),
            str(row.get("sample_barcode") or ""),
        ),
    )


def write_dict_rows_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    field: (
                        json.dumps(value, ensure_ascii=False, sort_keys=True)
                        if isinstance(value := row.get(field), (dict, list))
                        else value
                    )
                    for field in fieldnames
                }
            )


def pancancer_methodology_text(
    scan_id: str,
    request_payload: dict,
    result_payload: dict,
    patient_count: int,
    versions: dict[str, str],
) -> str:
    filters = request_payload.get("filters") or {}
    sensitivity = result_payload.get("clinical_sensitivity") or {}
    sensitivity_summary = sensitivity.get("summary") or {}
    effect_scale = result_payload.get("effect_scale") or {}
    cohort_scale = effect_scale.get("cohort_display") or {}
    synthesis_scale = effect_scale.get("synthesis") or {}
    actual_endpoints = sorted(
        {
            str(row.get("endpoint") or "").upper()
            for row in result_payload.get("results") or []
            if row.get("endpoint")
        }
    )
    interpretation_lines = interpretation_limitations(
        request_payload=request_payload,
        metrics=result_payload,
        endpoints=actual_endpoints,
    )
    lines = [
        "TCGA-TRACE Pan-Cancer Survival Analysis Methods",
        "",
        f"Scan ID: {scan_id}",
        f"Pipeline version: {result_payload.get('pipeline_version') or 'not available'}",
        f"Marker or signature: {result_payload.get('gene_symbol') or request_payload.get('gene_symbol')}",
        f"Requested endpoint: {request_payload.get('endpoint')}",
        f"Endpoint mode: {request_payload.get('endpoint_mode')}",
        f"Expression scale: {result_payload.get('expression_scale_label')}",
        f"Cohort effect unit: {cohort_scale.get('unit') or 'not available'}",
        f"Synthesis effect unit: {synthesis_scale.get('unit') or 'not available'}",
        f"Synthesis eligible: {bool(synthesis_scale.get('eligible'))}",
        f"Minimum patients per fitted model: {request_payload.get('min_patients')}",
        f"Minimum events per fitted model: {request_payload.get('min_events')}",
        f"FDR threshold: {request_payload.get('fdr_threshold')}",
        f"Filters: {json.dumps(filters, ensure_ascii=False, sort_keys=True)}",
        f"Exported patient-level rows: {patient_count}",
        "",
        "Primary analysis",
        "- Expression was transformed using the requested RNA scale and z-scored independently within each cancer cohort.",
        "- The primary model was a continuous Cox proportional hazards model: Surv(time_days, event) ~ expression_z.",
        "- Its hazard ratio is interpreted per one within-cohort standard-deviation increase in expression.",
        "- Per-SD cohort effects are descriptive and are not pooled because one SD represents a different expression increment in each cohort.",
        "- For eligible single-gene, mean-signature and weighted-signature analyses, the standardized coefficient and standard error were divided by the cohort expression-score SD to recover the exact coefficient per +1 common input-score unit.",
        "- Benjamini-Hochberg FDR was computed across completed primary cohort tests.",
        "- Eligible common-scale coefficients were synthesized with restricted maximum-likelihood random effects and Hartung-Knapp-Sidik-Jonkman inference.",
        "- A 95% prediction interval was reported when at least three comparable cohort effects were available.",
        "- Mixed endpoints were not pooled. Cohort-standardized z-score signatures were not pooled because they lack a transportable raw score unit.",
        "",
        "Clinical sensitivity analysis",
        "- Stage and grade were treated as ordinal numeric trends, not categorical dummy variables.",
        "- Major stage 0/I/II/III/IV was encoded 0/1/2/3/4; substages were collapsed to their major stage.",
        "- Histologic grade G1-G5 was encoded 1-5.",
        "- Three sensitivity families were attempted: stage-adjusted, grade-adjusted and stage+grade-adjusted continuous Cox models.",
        "- The displayed selected sensitivity model followed an availability-only hierarchy: stage+grade, then stage, then grade.",
        "- Complete-case minimum patient and event rules were re-applied separately after covariate filtering.",
        "- FDR was computed separately within every adjusted family and across the availability-selected adjusted tests.",
        "- Common-scale random-effects synthesis was computed separately by adjustment family. Effects from mixed selected families were intentionally not pooled.",
        f"- Evaluable selected sensitivity models: {sensitivity_summary.get('evaluable', 0)}.",
        f"- Not evaluable after ordinal covariate requirements: {sensitivity_summary.get('not_evaluable', 0)}.",
        "",
        "Endpoint and sample handling",
        "- One eligible RNA-seq sample was retained per TCGA participant according to the application sample-selection rule.",
        "- Non-positive or missing endpoint times and missing expression values were excluded.",
        "- When a follow-up cap was requested, later observations were administratively censored at that time.",
        "- Endpoint substitution, when enabled, followed the requested biologic endpoint family and remains explicit in every cohort row.",
        *(
            [
                "",
                "Endpoint and score interpretation",
                *[f"- {item}" for item in interpretation_lines],
            ]
            if interpretation_lines
            else []
        ),
        "",
        "Proportional hazards checks",
        "- survival::cox.zph was evaluated for the expression term and globally for every completed model.",
        "- A PH p-value below 0.05 is a diagnostic signal for interpretation, not an automatic deletion of an otherwise estimable result.",
        "- An expression-specific cox.zph p-value below 0.05 triggered separate expression HRs from 0 to 2 years and after 2 years in a prespecified piecewise Cox model with participant-clustered robust variance.",
        "- The 730.5-day split was fixed for every cohort before analysis and was not selected from expression, event times or effect estimates; at least 5 events per period and 10 patients entering the late period were required.",
        "",
        "Interpretation",
        "- Primary and adjusted results are shown together because either can be informative; adjusted non-evaluability is not labeled as model failure.",
        "- These retrospective associations are hypothesis-generating and are not evidence of causality or clinical utility.",
        "",
        "Software versions",
    ]
    lines.extend(f"- {name}: {value}" for name, value in versions.items())
    return "\n".join(lines) + "\n"


def render_pancancer_audit_html(report: dict) -> str:
    def esc(value) -> str:
        return html.escape("" if value is None else str(value), quote=True)

    results = report.get("results") or {}
    summary = results.get("summary") or {}
    meta_analysis = results.get("primary_meta_analysis") or {}
    random_effect = meta_analysis.get("random_effect") or {}
    prediction_interval = meta_analysis.get("prediction_interval") or {}
    effect_scale = results.get("effect_scale") or {}
    sensitivity = results.get("clinical_sensitivity") or {}
    sensitivity_summary = sensitivity.get("summary") or {}
    rows = results.get("cohort_results") or []
    data = report.get("data") or {}
    analysis_design = report.get("analysis_design") or {}
    score_context = analysis_design.get("score_transportability") or {}
    endpoint_contexts = data.get("endpoint_estimand_contexts") or {}
    quality = report.get("quality") or {}
    server_attestation = report.get("server_attestation") or {}
    def temporal_status(value: object) -> object:
        return value.get("status") if isinstance(value, dict) else None

    cohort_rows = "\n".join(
        "<tr>"
        f"<td>{esc(row.get('cohort'))}</td>"
        f"<td>{esc(row.get('endpoint'))}</td>"
        f"<td>{esc(row.get('n_patients'))}</td>"
        f"<td>{esc(row.get('hazard_ratio'))}</td>"
        f"<td>{esc(row.get('common_scale_hazard_ratio'))}</td>"
        f"<td>{esc(row.get('fdr'))}</td>"
        f"<td>{esc(temporal_status(row.get('time_varying_effect')))}</td>"
        f"<td>{esc(row.get('selected_adjusted_model'))}</td>"
        f"<td>{esc(row.get('adjusted_hazard_ratio'))}</td>"
        f"<td>{esc(row.get('adjusted_common_scale_hazard_ratio'))}</td>"
        f"<td>{esc(row.get('adjusted_fdr'))}</td>"
        f"<td>{esc(temporal_status(row.get('adjusted_time_varying_effect')))}</td>"
        f"<td>{esc(row.get('clinical_sensitivity'))}</td>"
        "</tr>"
        for row in rows
    )
    warning_items = "\n".join(
        f"<li>{esc(item)}</li>" for item in quality.get("warnings") or []
    ) or "<li>None reported.</li>"
    limitation_items = "\n".join(
        f"<li>{esc(item)}</li>" for item in quality.get("limitations") or []
    ) or "<li>None reported.</li>"
    interpretation_items = []
    if score_context.get("applicable") and score_context.get("interpretation"):
        interpretation_items.append(score_context["interpretation"])
    interpretation_items.extend(
        context.get("interpretation")
        for context in endpoint_contexts.values()
        if context.get("competing_risk_context_applicable")
        and context.get("interpretation")
    )
    interpretation_list = "\n".join(
        f"<li>{esc(item)}</li>" for item in dict.fromkeys(interpretation_items)
    ) or "<li>No endpoint- or score-specific interpretation context applies.</li>"
    artifact_rows = "\n".join(
        "<tr>"
        f"<td>{esc(label)}</td>"
        f"<td>{esc(item.get('filename'))}</td>"
        f"<td>{esc(item.get('bytes'))}</td>"
        f"<td><code>{esc(item.get('sha256'))}</code></td>"
        "</tr>"
        for label, item in (report.get("artifacts") or {}).items()
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>TCGA-TRACE pan-cancer audit {esc(report.get('scan_id'))}</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 32px; color: #17211f; background: #fbfcfb; }}
    h1 {{ font-size: 28px; margin-bottom: 4px; }}
    h2 {{ font-size: 18px; margin-top: 28px; }}
    table {{ border-collapse: collapse; width: 100%; margin: 12px 0; background: #fff; }}
    th, td {{ border: 1px solid #d9e1de; padding: 8px 10px; text-align: left; vertical-align: top; }}
    th {{ background: #eef3f1; }}
    code {{ font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; word-break: break-all; }}
  </style>
</head>
<body>
  <h1>TCGA-TRACE Pan-Cancer Audit</h1>
  <p>Scan ID: <code>{esc(report.get('scan_id'))}</code></p>
  <p>Reproducibility hash: <code>{esc(report.get('reproducibility_hash'))}</code></p>
  <p><strong>Integrity scope:</strong> {esc((report.get("integrity_scope") or {}).get("threat_model"))}
  {esc((report.get("integrity_scope") or {}).get("not_an_authenticity_proof"))}</p>
  <h2>Server attestation</h2>
  <table>
    <tr><th>Status</th><td>{esc(server_attestation.get('status'))}</td></tr>
    <tr><th>Algorithm</th><td>{esc(server_attestation.get('algorithm'))}</td></tr>
    <tr><th>Issuer</th><td>{esc(server_attestation.get('issuer'))}</td></tr>
    <tr><th>Key ID</th><td><code>{esc(server_attestation.get('key_id'))}</code></td></tr>
    <tr><th>Public key</th><td>{esc(server_attestation.get('public_key_url'))}</td></tr>
    <tr><th>Detached receipt</th><td>{esc(server_attestation.get('receipt_url'))}</td></tr>
    <tr><th>Trust model</th><td>{esc(server_attestation.get('trust_model'))}</td></tr>
  </table>
  <h2>Analysis summary</h2>
  <table>
    <tr><th>Pipeline</th><td>{esc((report.get('pipeline') or {}).get('version'))}</td></tr>
    <tr><th>Cohort effect unit</th><td>{esc(((effect_scale.get('cohort_display') or {}).get('unit')))}</td></tr>
    <tr><th>Synthesis effect unit</th><td>{esc(((effect_scale.get('synthesis') or {}).get('unit')))}</td></tr>
    <tr><th>Completed primary cohorts</th><td>{esc(summary.get('completed'))}</td></tr>
    <tr><th>Primary FDR hits</th><td>{esc(summary.get('significant'))}</td></tr>
    <tr><th>Cross-cancer synthesis</th><td>{esc(meta_analysis.get('model') if meta_analysis.get('available') else meta_analysis.get('reason'))}</td></tr>
    <tr><th>Common-scale meta HR</th><td>{esc(random_effect.get('hazard_ratio'))} ({esc(random_effect.get('hr_conf_low'))}-{esc(random_effect.get('hr_conf_high'))})</td></tr>
    <tr><th>95% prediction interval</th><td>{esc(prediction_interval.get('hazard_ratio_low'))}-{esc(prediction_interval.get('hazard_ratio_high'))}</td></tr>
    <tr><th>Adjusted sensitivity evaluable</th><td>{esc(sensitivity_summary.get('evaluable'))}</td></tr>
    <tr><th>Adjusted sensitivity not evaluable</th><td>{esc(sensitivity_summary.get('not_evaluable'))}</td></tr>
    <tr><th>Direction reversals</th><td>{esc(sensitivity_summary.get('direction_reversed'))}</td></tr>
  </table>
  <h2>Cohort effects</h2>
  <table>
    <thead><tr><th>Cohort</th><th>Endpoint</th><th>Primary n</th><th>Primary HR / SD</th><th>Primary HR / common unit</th><th>Primary FDR</th><th>Primary temporal diagnostic</th><th>Adjusted family</th><th>Adjusted HR / SD</th><th>Adjusted HR / common unit</th><th>Adjusted FDR</th><th>Adjusted temporal diagnostic</th><th>Comparison</th></tr></thead>
    <tbody>{cohort_rows}</tbody>
  </table>
  <h2>Endpoint and score interpretation</h2>
  <ul>{interpretation_list}</ul>
  <h2>Warnings</h2>
  <ul>{warning_items}</ul>
  <h2>Limitations</h2>
  <ul>{limitation_items}</ul>
  <h2>Artifacts</h2>
  <table>
    <thead><tr><th>Artifact</th><th>Filename</th><th>Bytes</th><th>SHA-256</th></tr></thead>
    <tbody>{artifact_rows}</tbody>
  </table>
</body>
</html>
"""


def ensure_svg_artifact(settings: Settings, analysis_id: str) -> Path:
    analysis_dir = settings.artifact_dir / analysis_id
    input_path = analysis_dir / "input.json"
    svg_path = analysis_dir / "plot.svg"
    cox_svg_path = analysis_dir / "cox_forest.svg"
    continuous_svg_path = analysis_dir / "continuous_effect.svg"
    cumulative_incidence_svg_path = analysis_dir / "cumulative_incidence.svg"
    cox_svg_required = (analysis_dir / "cox_forest.png").exists()
    continuous_svg_required = (analysis_dir / "continuous_effect.png").exists()
    cumulative_incidence_svg_required = (
        analysis_dir / "cumulative_incidence.png"
    ).exists()
    if (
        svg_path.exists()
        and (not cox_svg_required or cox_svg_path.exists())
        and (not continuous_svg_required or continuous_svg_path.exists())
        and (
            not cumulative_incidence_svg_required
            or cumulative_incidence_svg_path.exists()
        )
    ):
        return svg_path
    if not input_path.exists():
        raise FileNotFoundError("Analysis input payload is not available.")

    payload = json.loads(input_path.read_text(encoding="utf-8"))
    payload["render_png"] = False
    payload["render_svg"] = True
    payload["svg_path"] = str(svg_path)
    payload["cox_forest_svg_path"] = str(cox_svg_path)
    payload["continuous_effect_svg_path"] = str(continuous_svg_path)
    payload["cumulative_incidence_svg_path"] = str(
        cumulative_incidence_svg_path
    )
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
    continuous_plot_style = plot_style.get("continuous") or {}
    cox_forest_style = plot_style.get("cox_forest") or {}
    interpretation_lines = interpretation_limitations(
        request_payload=request_payload,
        metrics=metrics,
        endpoints=[endpoint],
    )
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
        f"- Samples with complete requested expression or signature score: {format_optional(sample_selection.get('expression_complete_samples'))}",
        f"- Participants removed because no expression-complete candidate remained: {format_optional(sample_selection.get('missing_expression_patients_removed'))}",
        f"- Participants using a lower-priority expression-complete biospecimen: {format_optional(sample_selection.get('expression_priority_fallbacks'))}",
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
        *(
            [
                "",
                "Endpoint And Score Interpretation",
                *[f"- {item}" for item in interpretation_lines],
            ]
            if interpretation_lines
            else []
        ),
        "",
        "Patient Stratification",
        stratification_method_text(cutpoint_method, cutpoint_details),
        f"- Final expression groups: {', '.join(group_levels)}",
        f"- Cutpoint details: {json.dumps(cutpoint_details, sort_keys=True)}",
        "",
        "Statistical Analysis",
        continuous_method_text(metrics),
        f"- Kaplan-Meier curves were fitted with survival::survfit using {endpoint_label.lower()} time and event status.",
        "- Group differences were tested with the log-rank test using survival::survdiff.",
        "- When exactly two expression groups were present, Cox proportional hazards models were fitted with survival::coxph using Efron ties to estimate hazard ratios and 95% confidence intervals.",
        "- Fixed sensitivity models attempted: univariable expression; ordinal major stage; ordinal histologic grade; and both ordinal trends. Stage 0/I/II/III/IV map to 0/1/2/3/4 with substages collapsed, and G1-G5 map to 1-5.",
        clinical_adjustment_method_text(request_payload, metrics),
        *external_covariate_methodology_lines(request_payload, metrics),
        "- Adjusted models were reported only when complete covariate data, covariate variation, event count and model rank were sufficient. Each model reports its own complete-case patient and event counts.",
        cox_information_method_text(metrics),
        time_varying_effect_method_text(metrics),
        rmst_method_text(metrics),
        competing_risk_method_text(metrics),
        interaction_method_text(metrics),
        f"- Log-rank p-value: {format_optional(metrics.get('logrank_p_value'))}",
        f"- Primary continuous HR per +1 SD: {format_optional(((metrics.get('continuous_analysis') or {}).get('linear_models') or [{}])[0].get('hazard_ratio'))}",
        f"- Primary continuous Cox p-value: {format_optional(((metrics.get('continuous_analysis') or {}).get('linear_models') or [{}])[0].get('p_value'))}",
        f"- Spline nonlinearity p-value: {format_optional(((metrics.get('continuous_analysis') or {}).get('spline') or {}).get('nonlinearity_p_value'))}",
        f"- Hazard ratio: {format_optional(metrics.get('hazard_ratio'))}",
        f"- Hazard ratio 95% CI: {format_optional(metrics.get('hr_conf_low'))} to {format_optional(metrics.get('hr_conf_high'))}",
        f"- Cox model p-value: {format_optional(metrics.get('hr_p_value'))}",
        f"- RMST status: {format_optional((metrics.get('rmst') or {}).get('status'))}",
        f"- RMST tau in days: {format_optional((metrics.get('rmst') or {}).get('tau_days'))}",
        f"- RMST difference in days: {format_optional(((metrics.get('rmst') or {}).get('difference') or {}).get('estimate_days'))}",
        f"- RMST difference p-value: {format_optional(((metrics.get('rmst') or {}).get('difference') or {}).get('p_value'))}",
        f"- Competing-risk analysis status: {format_optional((metrics.get('competing_risks') or {}).get('status'))}",
        f"- Gray-test p-value: {format_optional((((metrics.get('competing_risks') or {}).get('cumulative_incidence') or {}).get('gray_test') or {}).get('p_value'))}",
        f"- Cox adjustment models available: {format_cox_models(metrics.get('cox_models'))}",
        f"- Signature interaction Cox models available: {format_cox_models(metrics.get('signature_interaction_cox_models'))}",
        "",
        "Plot Generation",
        "- Kaplan-Meier plots were generated in R with survminer::ggsurvplot and ggplot2.",
        f"- Confidence interval shown: {'yes' if show_confidence_interval else 'no'}",
        f"- Risk table shown: {'yes' if show_risk_table else 'no'}",
        f"- Kaplan-Meier title shown: {'yes' if plot_style.get('show_title') else 'no'}",
        f"- Kaplan-Meier title text: {plot_style.get('plot_title') or 'automatic or not used'}",
        f"- Kaplan-Meier palette: {', '.join(plot_style.get('palette') or [])}",
        f"- Continuous-effect color: {continuous_plot_style.get('effect_color') or '#1f6f8b'}",
        f"- Continuous-effect reference color: {continuous_plot_style.get('reference_color') or '#75817e'}",
        f"- Continuous-effect title shown: {'yes' if continuous_plot_style.get('show_title', True) else 'no'}",
        f"- Continuous-effect title text: {continuous_plot_style.get('plot_title') or 'Continuous expression effect'}",
        f"- Continuous-effect X-axis title: {continuous_plot_style.get('x_axis_title') or 'automatic from marker and expression scale'}",
        f"- Continuous-effect Y-axis title: {continuous_plot_style.get('y_axis_title') or 'Hazard ratio relative to median'}",
        f"- Cox forest lower-hazard color: {cox_forest_style.get('lower_hazard_color') or '#1f6f8b'}",
        f"- Cox forest higher-hazard color: {cox_forest_style.get('higher_hazard_color') or '#b94d48'}",
        f"- Cox forest reference color: {cox_forest_style.get('reference_color') or '#7b8582'}",
        f"- Cox forest title shown: {'yes' if cox_forest_style.get('show_title', True) else 'no'}",
        f"- Cox forest title text: {cox_forest_style.get('plot_title') or 'Cox proportional hazards models'}",
        f"- Cox forest X-axis title: {cox_forest_style.get('x_axis_title') or 'Hazard ratio (log scale)'}",
        f"- Font family: {plot_style.get('font_family') or 'sans'}",
        f"- Plot aspect: {plot_style.get('plot_aspect') or 'rectangular'}",
        f"- Base font size: {plot_style.get('base_font_size') or 12}",
        f"- Axis tick-label font size: {plot_style.get('axis_text_size') or 11}",
        f"- Axis title font size: {plot_style.get('axis_title_size') or 12}",
        f"- Plot grid shown: {'yes' if plot_style.get('show_grid', False) else 'no'}",
        "",
        "Output Files",
        "- PNG contains the rendered Kaplan-Meier plot generated at analysis time.",
        "- SVG contains the rendered Kaplan-Meier plot and is generated on demand when requested for download.",
        "- Cox PNG/SVG contains the grouped proportional-hazards model forest plot when at least one model is evaluable.",
        "- Continuous PNG/SVG contains the restricted cubic spline effect profile when the spline model is evaluable.",
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
        "- The continuous Cox and restricted cubic spline models are associative and can remain confounded by covariates not represented in TCGA-TRACE.",
        "- Kaplan-Meier grouping does not establish causality and can be sensitive to cutpoint choice.",
        "- Optimized cutpoints such as maxstat can overestimate apparent significance unless validated externally.",
        "- Events-per-parameter thresholds are pragmatic information diagnostics rather than guarantees against overfitting. Firth sensitivity reduces monotone-likelihood bias but does not correct outcome-driven cutpoint selection or unmeasured confounding.",
        f"- {adjustment_limitation_text(request_payload)}",
        "",
        "Software Versions",
    ]
    versions = software_versions(metrics)
    lines.extend(f"- {name}: {value}" for name, value in versions.items())
    lines.extend(
        [
            "",
            "Suggested citation wording",
            f"Survival analyses were performed using TCGA cancer cohort RNA-seq and clinical metadata from a database created at {database_created_at}, with data through {data_through}. The analyzed endpoint was {endpoint_label} ({endpoint}). Clinical and endpoint eligibility were applied before requiring the requested gene or complete signature score; when multiple expression-complete RNA-seq barcodes remained for one TCGA participant, one sample was retained using TCGA biospecimen priority. The primary association was estimated continuously per one within-analysis standard deviation using Cox regression, with a three-degree-of-freedom restricted cubic spline used to assess nonlinearity. The prespecified user-adjustment fields were {format_all_adjustment_covariates(request_payload)}. Kaplan-Meier, grouped Cox and restricted mean survival time estimates were reported as cutpoint sensitivity analyses. Every Cox fit reported events per fitted parameter; low-information, unstable or extreme fits additionally reported a Firth penalized partial-likelihood sensitivity without replacing the standard estimate. Marker-specific cox.zph p-values below 0.05 triggered a prespecified piecewise Cox diagnostic reporting separate marker HRs before and after a fixed two-year follow-up split; the split was not optimized from the data. Plots were generated in R using survival, survminer and ggplot2.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def continuous_method_text(metrics: dict) -> str:
    continuous = metrics.get("continuous_analysis") or {}
    if continuous.get("status") != "completed":
        return (
            "- A cutpoint-independent continuous model was not estimated: "
            f"{continuous.get('reason') or 'not applicable'}"
        )
    spline = continuous.get("spline") or {}
    spline_text = (
        "A three-degree-of-freedom restricted cubic spline with knots at the "
        "5th, 35th, 65th and 95th expression percentiles was compared with the "
        "linear model by likelihood-ratio test."
        if spline.get("status") == "completed"
        else f"The spline was not estimable: {spline.get('reason') or 'not available'}"
    )
    return (
        "- The primary association used the unstratified expression-complete population. "
        "Expression was standardized within that population and modeled continuously with "
        "survival::coxph using Efron ties; HRs represent a +1 SD increase. "
        f"{spline_text}"
    )


def clinical_adjustment_method_text(request_payload: dict, metrics: dict) -> str:
    requested = request_payload.get("adjustment_covariates") or []
    external_requested = (
        request_payload.get("external_adjustment_covariates") or []
    )
    if not requested and not external_requested:
        return (
            "- No additional user-selected clinical adjustment was requested; "
            "the fixed stage/grade sensitivity models remain available."
        )
    continuous_models = (metrics.get("continuous_analysis") or {}).get("linear_models") or []
    grouped_models = metrics.get("cox_models") or []
    interaction_models = metrics.get("signature_interaction_cox_models") or []
    user_models = [
        model
        for model in [*continuous_models, *grouped_models, *interaction_models]
        if model.get("model")
        in {
            "continuous_user_adjusted",
            "user_adjusted",
            "signature_interaction_user_adjusted",
        }
    ]
    completed = sum(model.get("status") == "completed" for model in user_models)
    details = []
    if requested:
        details.append(
            "Imported TCGA age was modeled continuously per 10-year increase; "
            "stage and grade as ordinal trends; and GDC gender and race as "
            "categorical treatment contrasts after unknown/non-standard values "
            "were set missing."
        )
    if external_requested:
        details.append(
            "User-supplied variables were linked by exact TCGA participant "
            "barcode and encoded from their prespecified type, level order, "
            "reference level and effect unit."
        )
    return (
        "- User-selected adjustment: "
        f"{format_all_adjustment_covariates(request_payload)}. "
        f"{' '.join(details)} "
        f"{completed}/{len(user_models)} applicable user-adjusted model(s) were estimable."
    )


def external_covariate_methodology_lines(
    request_payload: dict,
    metrics: dict,
) -> list[str]:
    selected = request_payload.get("external_adjustment_covariates") or []
    if not selected:
        return []
    dataset = request_payload.get("external_covariates") or {}
    qc = metrics.get("external_covariates") or {}
    definitions = {
        item.get("name"): item
        for item in dataset.get("definitions") or []
        if item.get("name")
    }
    variable_qc = {
        item.get("name"): item
        for item in qc.get("variables") or []
        if item.get("name")
    }
    lines = [
        (
            "- External covariate dataset: "
            f"{dataset.get('source_label') or 'unlabeled user-supplied dataset'}; "
            f"schema {dataset.get('schema_version') or 'not available'}; "
            f"SHA-256 {qc.get('dataset_sha256') or 'not available'}; "
            f"{qc.get('cohort_matched_rows', 'not available')} of "
            f"{qc.get('n_rows', 'not available')} supplied TCGA participant rows "
            "matched the selected cohort."
        )
    ]
    for name in selected:
        definition = definitions.get(name) or {"name": name, "label": name}
        quality = variable_qc.get(name) or {}
        lines.append(
            "- External covariate "
            f"{definition.get('label') or name} ({name}): "
            f"{external_covariate_definition_text(definition)}; "
            f"{quality.get('analysis_population_non_missing', 'not available')} "
            "non-missing and "
            f"{quality.get('analysis_population_missing', 'not available')} missing "
            "in the expression-complete analysis population."
        )
    return lines


def cox_information_method_text(metrics: dict) -> str:
    continuous_models = (metrics.get("continuous_analysis") or {}).get("linear_models") or []
    grouped_models = metrics.get("cox_models") or []
    interaction_models = metrics.get("signature_interaction_cox_models") or []
    models = [*continuous_models, *grouped_models, *interaction_models]
    evaluated = [
        model
        for model in models
        if (model.get("information_diagnostics") or {}).get("status")
        not in (None, "not_evaluable")
    ]
    low_information = [
        model
        for model in evaluated
        if (model.get("information_diagnostics") or {}).get("status")
        in {"caution", "severe"}
    ]
    firth_completed = [
        model
        for model in models
        if (model.get("penalized_sensitivity") or {}).get("status") == "completed"
    ]
    return (
        "- Model information was summarized as observed events per fitted regression "
        "parameter. Values below 10 were flagged as low-information and values below "
        "5 as severe; these are interpretation warnings, not exclusion rules. A "
        "coxphf Firth penalized partial-likelihood sensitivity (penalty 0.5, profile "
        "penalized-likelihood confidence interval and test, Breslow ties) was run "
        "automatically for low-information, unstable or extreme standard estimates "
        "and was reported alongside rather than substituted for the Efron-ties Cox "
        f"estimate. This analysis had {len(low_information)}/{len(evaluated)} "
        f"evaluable low-information model(s) and {len(firth_completed)} completed "
        "Firth sensitivity fit(s)."
    )


def time_varying_effect_method_text(metrics: dict) -> str:
    continuous_models = (
        (metrics.get("continuous_analysis") or {}).get("linear_models") or []
    )
    grouped_models = metrics.get("cox_models") or []
    interaction_models = metrics.get("signature_interaction_cox_models") or []
    models = [*continuous_models, *grouped_models, *interaction_models]
    diagnostics = [
        model.get("time_varying_effect") or {}
        for model in models
        if model.get("status") == "completed"
    ]
    triggered = [
        item
        for item in diagnostics
        if item.get("status") in {"completed", "skipped", "failed"}
    ]
    completed = [item for item in triggered if item.get("status") == "completed"]
    return (
        "- Marker-specific survival::cox.zph p-values below 0.05 triggered a "
        "prespecified two-period Cox diagnostic. The marker coefficient was "
        "estimated separately from 0 to 2 years and after 2 years using a fixed "
        "730.5-day split, Efron ties and participant-clustered robust sandwich "
        "variance; the late-to-early HR ratio was also reported. The split was "
        "never selected from marker values, event times or effect estimates. "
        "Estimation required at least 5 events in each period and 10 patients "
        f"entering the late period. This analysis triggered {len(triggered)} "
        f"diagnostic(s), of which {len(completed)} were estimable."
    )


def rmst_method_text(metrics: dict) -> str:
    rmst = metrics.get("rmst") or {}
    if rmst.get("status") == "completed":
        return (
            "- Restricted mean survival time was estimated with survRM2::rmst2 for two-group comparisons. "
            f"The truncation time tau was {format_optional(rmst.get('tau_days'))} days, defined as the {rmst.get('tau_rule') or 'analysis-specific follow-up limit'}."
        )
    reason = rmst.get("reason") or "not applicable"
    return f"- Restricted mean survival time was not estimated: {reason}"


def competing_risk_method_text(metrics: dict) -> str:
    competing = metrics.get("competing_risks") or {}
    if not competing.get("applicable"):
        return (
            "- Competing-risk analysis was not applicable to the selected endpoint."
        )
    coding = competing.get("coding") or {}
    cumulative = competing.get("cumulative_incidence") or {}
    grouped_models = competing.get("grouped_fine_gray_models") or []
    continuous_models = competing.get("continuous_fine_gray_models") or []
    completed_models = sum(
        model.get("status") == "completed"
        for model in [*grouped_models, *continuous_models]
    )
    return (
        "- Competing events were coded from TCGA-CDR ExtraEndpoints as "
        f"0=censored, 1=event of interest and 2=competing death "
        f"({coding.get('source_status_column') or 'source status column unavailable'}). "
        "Kaplan-Meier/Cox outputs censored code 2 and estimate cause-specific "
        "quantities; cmprsk::cuminc retained code 2 for cumulative incidence and "
        "Gray's test, while cmprsk::crr estimated proportional subdistribution "
        f"hazards. Cumulative-incidence status: "
        f"{cumulative.get('status') or 'not available'}; completed Fine-Gray "
        f"models: {completed_models}."
    )


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
    external_text = (
        " and the selected user-supplied external covariates"
        if request_payload.get("external_adjustment_covariates")
        else ""
    )
    if request_payload.get("signature_a") and request_payload.get("signature_b"):
        return (
            "- CSV contains the exact patient-level records used for the analysis, including combined score, "
            "signature A score, signature B score, combined group, per-signature groups, survival time, event status "
            f"and selected metadata{external_text}."
        )
    return (
        "- CSV contains the exact patient-level records used for the analysis, "
        "including expression value, survival time, event status, assigned group "
        f"and selected metadata{external_text}."
    )


def interaction_method_text(metrics: dict) -> str:
    models = metrics.get("signature_interaction_cox_models") or []
    if not models:
        return "- Two-signature interaction Cox models were not applicable for this analysis."
    return (
        "- For two-signature analyses, continuous Cox interaction models were fitted as "
        "Surv(time, event) ~ signature_A_z + signature_B_z + signature_A_z:signature_B_z, "
        "with additional ordinal major-stage and histologic-grade adjusted variants when at least two recognized "
        "scores, complete covariate data and model rank were sufficient. "
        "Signature scores were z-scored within the analyzed patient set before fitting."
    )


def endpoint_method_text(endpoint: str, source: str | None) -> str:
    if source == "tcga_cdr":
        base = (
            "- Endpoint data were obtained from the TCGA Clinical Data Resource (TCGA-CDR), "
            "which standardizes OS, PFI, DFI and DSS outcomes across TCGA cancer cohorts."
        )
        if endpoint in COMPETING_RISK_ENDPOINTS:
            return (
                base
                + " Competing-event status was read from the matched "
                "ExtraEndpoints status/time columns."
            )
        return base
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


def format_adjustment_covariates(values) -> str:
    labels = {
        "age_at_index": "age at index (per 10 years)",
        "stage": "ordinal stage",
        "grade": "ordinal grade",
        "gender": "GDC gender",
        "race": "GDC race",
    }
    requested = list(dict.fromkeys(values or []))
    if not requested:
        return "none"
    return ", ".join(labels.get(value, str(value)) for value in requested)


def format_all_adjustment_covariates(request_payload: dict) -> str:
    values: list[str] = []
    built_in = format_adjustment_covariates(
        request_payload.get("adjustment_covariates")
    )
    if built_in != "none":
        values.append(built_in)
    definitions = {
        item.get("name"): item
        for item in (
            (request_payload.get("external_covariates") or {}).get(
                "definitions"
            )
            or []
        )
        if item.get("name")
    }
    for name in request_payload.get("external_adjustment_covariates") or []:
        definition = definitions.get(name) or {}
        values.append(str(definition.get("label") or name))
    return ", ".join(values) if values else "none"


def external_covariate_definition_text(definition: dict) -> str:
    value_type = str(definition.get("value_type") or "unspecified")
    label = str(definition.get("label") or definition.get("name") or "variable")
    if value_type == "continuous":
        effect_unit = definition.get("effect_unit", 1)
        unit = str(definition.get("unit") or "").strip()
        unit_text = f" {unit}" if unit else ""
        return (
            f"continuous; model coefficient per {effect_unit}{unit_text} "
            f"increase in {label}"
        )
    levels = [str(value) for value in definition.get("levels") or []]
    if value_type == "categorical":
        reference = definition.get("reference_level") or "not specified"
        return (
            "categorical treatment contrasts; "
            f"reference {reference}; declared levels {', '.join(levels) or 'not available'}"
        )
    if value_type == "ordinal":
        return (
            "ordinal one-level trend following the declared order "
            f"{' < '.join(levels) or 'not available'}"
        )
    return value_type


def adjustment_limitation_text(request_payload: dict) -> str:
    if request_payload.get("external_adjustment_covariates"):
        return (
            "Clinical adjustment is limited to the selected imported TCGA fields "
            "and user-supplied external covariates; treatment and any prognostic "
            "variables not supplied remain unmodeled."
        )
    return (
        "Clinical adjustment is limited to selected imported TCGA fields; "
        "treatment, tumor purity, immune composition, molecular subtype and other "
        "cohort-specific prognostic variables remain unmodeled unless supplied as "
        "external covariates."
    )


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
