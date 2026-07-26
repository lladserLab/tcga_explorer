from __future__ import annotations

import csv
from datetime import datetime, timezone
from html import escape
from itertools import product
import json
import math
from pathlib import Path
from typing import Any

from app.attestation import (
    attestation_metadata,
    write_attestation_receipt,
)
from app.config import Settings
from app.r_runner import (
    endpoint_estimand_context,
    interpretation_limitations,
    score_transportability_context,
    stable_hash,
)
from app.schemas import AnalysisRequest, MultiverseAnalysisRequest


MULTIVERSE_AUDIT_SCHEMA = "tcga-trace-multiverse-audit-v2"


def expand_multiverse_request(
    request: MultiverseAnalysisRequest,
) -> list[dict[str, Any]]:
    gene_label = ", ".join(gene.gene_symbol for gene in request.genes)
    specifications: list[dict[str, Any]] = []
    for index, (endpoint, scoring_method, cutpoint_method) in enumerate(
        product(
            request.endpoints,
            request.scoring_methods,
            request.cutpoint_methods,
        ),
        start=1,
    ):
        analysis_request = AnalysisRequest(
            cohort=request.cohort,
            gene_symbol=gene_label,
            signature_method=scoring_method,
            signature_genes=[] if scoring_method == "single" else request.genes,
            endpoint=endpoint,
            expression_scale=request.expression_scale,
            cutpoint_method=cutpoint_method,
            custom_percentile=(
                request.custom_percentile
                if cutpoint_method == "percentile"
                else None
            ),
            filters=request.filters,
            adjustment_covariates=request.adjustment_covariates,
            external_covariates=request.external_covariates,
            external_adjustment_covariates=(
                request.external_adjustment_covariates
            ),
            time_unit=request.time_unit,
            show_confidence_interval=request.show_confidence_interval,
            show_risk_table=False,
            plot_style=request.plot_style,
        )
        payload = analysis_request.model_dump(mode="json")
        specifications.append(
            {
                "index": index - 1,
                "specification_id": f"S{index:03d}",
                "endpoint": endpoint,
                "scoring_method": scoring_method,
                "cutpoint_method": cutpoint_method,
                "custom_percentile": (
                    request.custom_percentile
                    if cutpoint_method == "percentile"
                    else None
                ),
                "analysis_request_hash": stable_hash(payload),
                "analysis_request": analysis_request,
            }
        )
    return specifications


def benjamini_hochberg(values: list[float | None]) -> list[float | None]:
    valid = [
        (index, float(value))
        for index, value in enumerate(values)
        if _number(value) is not None
    ]
    result: list[float | None] = [None] * len(values)
    if not valid:
        return result
    ordered = sorted(valid, key=lambda item: item[1])
    running_min = 1.0
    total = len(ordered)
    for reverse_index in range(total - 1, -1, -1):
        original_index, value = ordered[reverse_index]
        rank = reverse_index + 1
        running_min = min(running_min, value * total / rank)
        result[original_index] = min(1.0, running_min)
    return result


def summarize_multiverse(
    *,
    session_id: str,
    request: MultiverseAnalysisRequest,
    specifications: list[dict[str, Any]],
    completed_items: list[dict[str, Any]],
    pipeline_version: str,
    data_version: dict[str, Any],
    generated_at: str | None = None,
) -> dict[str, Any]:
    generated_at = generated_at or datetime.now(timezone.utc).isoformat()
    request_snapshot = request.model_dump(mode="json")
    score_context = score_transportability_context(
        request_payload=request_snapshot,
    )
    endpoint_contexts = {
        endpoint: endpoint_estimand_context(endpoint)
        for endpoint in request.endpoints
    }
    interpretation_messages = interpretation_limitations(
        request_payload=request_snapshot,
        endpoints=request.endpoints,
    )
    requested_adjustment = bool(
        request.adjustment_covariates
        or request.external_adjustment_covariates
    )
    grouped_model_id = "user_adjusted" if requested_adjustment else "univariable"
    continuous_model_id = (
        "continuous_user_adjusted"
        if requested_adjustment
        else "continuous_univariable"
    )
    items_by_index = {
        int(item["index"]): item
        for item in completed_items
    }

    rows: list[dict[str, Any]] = []
    ledger: list[dict[str, Any]] = []
    warnings: list[str] = list(interpretation_messages)
    reference_candidates: dict[tuple[str, str], list[dict[str, Any]]] = {}

    for specification in specifications:
        item = items_by_index.get(specification["index"]) or {
            "index": specification["index"],
            "status": "failed",
            "code": "SPECIFICATION_NOT_EXECUTED",
            "error": "The planned specification did not return an execution record.",
        }
        result = item.get("result") or {}
        metrics = result.get("metrics") or {}
        status = "completed" if item.get("status") == "completed" and metrics else "failed"
        grouped_effect = _extract_model_effect(
            metrics.get("cox_models"),
            grouped_model_id,
        )
        continuous_effect = _extract_model_effect(
            (metrics.get("continuous_analysis") or {}).get("linear_models"),
            continuous_model_id,
        )
        inference_p_value, inference_test = _grouped_inference(metrics)
        audit = metrics.get("audit_report") or {}
        reference_key = (
            specification["endpoint"],
            specification["scoring_method"],
        )
        if status == "completed":
            reference_candidates.setdefault(reference_key, []).append(
                {
                    "effect": continuous_effect,
                    "n_patients": (metrics.get("continuous_analysis") or {}).get(
                        "n_patients"
                    ),
                    "n_events": (metrics.get("continuous_analysis") or {}).get(
                        "n_events"
                    ),
                    "patient_records_sha256": audit.get(
                        "continuous_patient_records_sha256"
                    ),
                    "analysis_id": result.get("id"),
                }
            )

        row = {
            "specification_id": specification["specification_id"],
            "index": specification["index"],
            "endpoint": specification["endpoint"],
            "scoring_method": specification["scoring_method"],
            "cutpoint_method": specification["cutpoint_method"],
            "custom_percentile": specification["custom_percentile"],
            "status": status,
            "analysis_id": result.get("id"),
            "analysis_request_hash": specification["analysis_request_hash"],
            "n_patients": metrics.get("n_patients"),
            "n_events": metrics.get("n_events"),
            "group_counts": metrics.get("group_counts") or {},
            "event_counts": metrics.get("event_counts") or {},
            "inference_test": inference_test,
            "inference_p_value": inference_p_value,
            "grouped_bh_q_value": None,
            "grouped_bonferroni_p_value": None,
            "grouped_effect": grouped_effect,
            "continuous_reference_id": (
                f"{specification['endpoint']}::{specification['scoring_method']}"
            ),
            "rmst": _compact_rmst(metrics.get("rmst")),
            "marker_ph_p_value": grouped_effect.get("ph_p_value"),
            "global_ph_p_value": grouped_effect.get("ph_global_p_value"),
            "audit_reproducibility_hash": audit.get("reproducibility_hash"),
            "patient_records_sha256": audit.get("patient_records_sha256"),
            "error_code": item.get("code") if status == "failed" else None,
            "error": item.get("error") if status == "failed" else None,
            "downloads": result.get("downloads") or {},
        }
        rows.append(row)
        ledger.append(
            {
                "specification_id": specification["specification_id"],
                "analysis_request_hash": specification["analysis_request_hash"],
                "status": status,
                "analysis_id": result.get("id"),
                "audit_reproducibility_hash": audit.get("reproducibility_hash"),
                "error_code": row["error_code"],
                "error": row["error"],
            }
        )

    grouped_q_values = benjamini_hochberg(
        [row["inference_p_value"] for row in rows]
    )
    grouped_test_count = sum(value is not None for value in grouped_q_values)
    for row, q_value in zip(rows, grouped_q_values):
        row["grouped_bh_q_value"] = q_value
        if row["inference_p_value"] is not None:
            row["grouped_bonferroni_p_value"] = min(
                1.0,
                row["inference_p_value"] * grouped_test_count,
            )

    continuous_references: list[dict[str, Any]] = []
    for endpoint, scoring_method in product(
        request.endpoints,
        request.scoring_methods,
    ):
        reference_id = f"{endpoint}::{scoring_method}"
        candidates = reference_candidates.get((endpoint, scoring_method), [])
        if not candidates:
            continuous_references.append(
                {
                    "reference_id": reference_id,
                    "endpoint": endpoint,
                    "scoring_method": scoring_method,
                    "status": "not_evaluable",
                    "reason": "No completed specification supplied a continuous reference.",
                    "effect": _missing_effect(continuous_model_id),
                    "continuous_bh_q_value": None,
                    "continuous_bonferroni_p_value": None,
                }
            )
            continue
        first = candidates[0]
        consistent = all(_references_match(first, candidate) for candidate in candidates[1:])
        if not consistent:
            warnings.append(
                f"{reference_id}: repeated cutpoint cells produced inconsistent continuous references."
            )
        continuous_references.append(
            {
                "reference_id": reference_id,
                "endpoint": endpoint,
                "scoring_method": scoring_method,
                "status": "completed" if consistent else "inconsistent",
                "n_patients": first.get("n_patients"),
                "n_events": first.get("n_events"),
                "patient_records_sha256": first.get("patient_records_sha256"),
                "source_analysis_id": first.get("analysis_id"),
                "effect": first["effect"],
                "continuous_bh_q_value": None,
                "continuous_bonferroni_p_value": None,
            }
        )

    continuous_p_values = [
        (
            reference["effect"].get("standard_p_value")
            if reference["status"] == "completed"
            else None
        )
        for reference in continuous_references
    ]
    continuous_q_values = benjamini_hochberg(continuous_p_values)
    continuous_test_count = sum(
        value is not None for value in continuous_q_values
    )
    for reference, p_value, q_value in zip(
        continuous_references,
        continuous_p_values,
        continuous_q_values,
    ):
        reference["continuous_bh_q_value"] = q_value
        if p_value is not None:
            reference["continuous_bonferroni_p_value"] = min(
                1.0,
                p_value * continuous_test_count,
            )

    completed_count = sum(row["status"] == "completed" for row in rows)
    failed_count = len(rows) - completed_count
    if failed_count:
        warnings.append(
            f"{failed_count} of {len(rows)} prespecified analyses were not evaluable or failed."
        )
    if "maxstat" in request.cutpoint_methods:
        warnings.append(
            "Maxstat multiplicity uses its Lau94 corrected rank-statistic p-value; grouped HR and RMST remain post-selection summaries."
        )

    family_core = {
        "pipeline_version": pipeline_version,
        "data_version": data_version,
        "request": request_snapshot,
        "specifications": [
            {
                "specification_id": row["specification_id"],
                "analysis_request_hash": row["analysis_request_hash"],
                "analysis_id": row["analysis_id"],
                "audit_reproducibility_hash": row[
                    "audit_reproducibility_hash"
                ],
                "status": row["status"],
            }
            for row in rows
        ],
    }
    reproducibility_hash = stable_hash(family_core)
    analysis_family = {
        "session_id": session_id,
        "declared_before_execution": True,
        "dimensions": {
            "endpoints": request.endpoints,
            "scoring_methods": request.scoring_methods,
            "cutpoint_methods": request.cutpoint_methods,
        },
        "planned_specifications": len(rows),
        "primary_continuous_family": {
            "unit": "one unique endpoint x scoring combination",
            "planned_tests": len(request.endpoints) * len(request.scoring_methods),
            "evaluable_tests": continuous_test_count,
            "p_value": (
                "standard Cox p-value from the exact user-selected model"
                if requested_adjustment
                else "standard univariable continuous Cox p-value"
            ),
            "multiplicity": "Benjamini-Hochberg and Bonferroni within this declared family",
            "cutpoint_independent": True,
        },
        "grouped_sensitivity_family": {
            "unit": "one endpoint x scoring x cutpoint specification",
            "planned_tests": len(rows),
            "evaluable_tests": grouped_test_count,
            "p_value": "log-rank p-value, except Lau94-corrected maxstat p-value",
            "multiplicity": "Benjamini-Hochberg and Bonferroni within this declared family",
            "cutpoint_independent": False,
        },
        "interpretation_context": {
            "score_transportability": score_context,
            "endpoint_estimands": endpoint_contexts,
            "messages": interpretation_messages,
        },
        "binary_verdict": False,
    }
    summary = {
        "planned": len(rows),
        "completed": completed_count,
        "failed": failed_count,
        "continuous_tests": continuous_test_count,
        "grouped_tests": grouped_test_count,
        "continuous_bh_below_0_05": sum(
            reference.get("continuous_bh_q_value") is not None
            and reference["continuous_bh_q_value"] <= 0.05
            for reference in continuous_references
        ),
        "grouped_bh_below_0_05": sum(
            row.get("grouped_bh_q_value") is not None
            and row["grouped_bh_q_value"] <= 0.05
            for row in rows
        ),
    }
    audit = {
        "schema_version": MULTIVERSE_AUDIT_SCHEMA,
        "report_type": "prespecified_multiverse_audit",
        "session_id": session_id,
        "generated_at": generated_at,
        "pipeline_version": pipeline_version,
        "data_version": data_version,
        "request_sha256": stable_hash(request_snapshot),
        "family_reproducibility_hash": reproducibility_hash,
        "child_analysis_count": len(rows),
        "completed_child_analysis_count": completed_count,
        "child_analyses": ledger,
        "interpretation_context": analysis_family["interpretation_context"],
    }
    return {
        "session_id": session_id,
        "status": "completed" if failed_count == 0 else "completed_with_failures",
        "pipeline_version": pipeline_version,
        "generated_at": generated_at,
        "request_snapshot": request_snapshot,
        "analysis_family": analysis_family,
        "summary": summary,
        "continuous_references": continuous_references,
        "specifications": rows,
        "execution_ledger": ledger,
        "warnings": warnings,
        "audit": audit,
        "downloads": multiverse_downloads(session_id),
    }


def multiverse_downloads(session_id: str) -> dict[str, str]:
    base = f"/api/v1/analyses/multiverses/{session_id}/download"
    return {
        "svg": f"{base}/svg",
        "csv": f"{base}/csv",
        "continuous_csv": f"{base}/continuous_csv",
        "json": f"{base}/json",
        "ledger": f"{base}/ledger",
        "audit_json": f"{base}/audit_json",
        "audit_html": f"{base}/audit_html",
        "methodology": f"{base}/methodology",
        "zip": f"{base}/zip",
    }


def write_multiverse_artifacts(
    artifact_root: Path,
    result: dict[str, Any],
    settings: Settings | None = None,
) -> dict[str, Path]:
    session_dir = artifact_root / "multiverse" / result["session_id"]
    session_dir.mkdir(parents=True, exist_ok=True)
    if settings is not None:
        result["audit"]["server_attestation"] = attestation_metadata(
            settings,
            subject_type="prespecified_multiverse",
            subject_id=result["session_id"],
        )
        result["downloads"]["attestation"] = (
            f"/api/v1/analyses/multiverses/{result['session_id']}"
            "/download/attestation"
        )
    paths = {
        "json": session_dir / "multiverse_result.json",
        "csv": session_dir / "specifications.csv",
        "continuous_csv": session_dir / "continuous_references.csv",
        "ledger": session_dir / "execution_ledger.json",
        "audit_json": session_dir / "audit_report.json",
        "audit_html": session_dir / "audit_report.html",
        "methodology": session_dir / "methodology.txt",
        "svg": session_dir / "specification_curve.svg",
    }
    if settings is not None:
        paths["attestation"] = (
            session_dir / "attestation_receipt.json"
        )
    paths["ledger"].write_text(
        json.dumps(
            {
                "schema_version": "tcga-trace-multiverse-ledger-v1",
                "session_id": result["session_id"],
                "analysis_family": result["analysis_family"],
                "entries": result["execution_ledger"],
            },
            ensure_ascii=False,
            allow_nan=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    paths["audit_json"].write_text(
        json.dumps(
            result["audit"],
            ensure_ascii=False,
            allow_nan=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    if settings is not None:
        write_attestation_receipt(
            settings,
            subject_type="prespecified_multiverse",
            subject_id=result["session_id"],
            audit_path=paths["audit_json"],
            reproducibility_hash=result["audit"][
                "family_reproducibility_hash"
            ],
            report_schema_version=result["audit"]["schema_version"],
        )
    _write_specification_csv(paths["csv"], result["specifications"])
    _write_continuous_csv(paths["continuous_csv"], result["continuous_references"])
    paths["methodology"].write_text(
        render_multiverse_methodology(result),
        encoding="utf-8",
    )
    paths["audit_html"].write_text(
        render_multiverse_audit_html(result),
        encoding="utf-8",
    )
    paths["svg"].write_text(
        render_specification_curve_svg(result),
        encoding="utf-8",
    )
    result_temp = paths["json"].with_suffix(".json.tmp")
    try:
        result_temp.write_text(
            json.dumps(result, ensure_ascii=False, allow_nan=False, indent=2),
            encoding="utf-8",
        )
        result_temp.replace(paths["json"])
    finally:
        result_temp.unlink(missing_ok=True)
    return paths


def render_multiverse_methodology(result: dict[str, Any]) -> str:
    family = result["analysis_family"]
    continuous = family["primary_continuous_family"]
    grouped = family["grouped_sensitivity_family"]
    dimensions = family["dimensions"]
    interpretation_messages = (
        family.get("interpretation_context") or {}
    ).get("messages") or []
    return "\n".join(
        [
            "TCGA-TRACE prespecified multiverse methodology",
            "",
            f"Session: {result['session_id']}",
            f"Pipeline: {result['pipeline_version']}",
            f"Generated: {result['generated_at']}",
            "",
            "Declared dimensions",
            f"- Endpoints: {', '.join(dimensions['endpoints'])}",
            f"- Scoring methods: {', '.join(dimensions['scoring_methods'])}",
            f"- Cutpoint methods: {', '.join(dimensions['cutpoint_methods'])}",
            f"- Planned specifications: {family['planned_specifications']}",
            "",
            "Multiplicity families",
            f"- Continuous primary family: {continuous['unit']}; {continuous['evaluable_tests']} evaluable tests; {continuous['multiplicity']}.",
            f"- Grouped sensitivity family: {grouped['unit']}; {grouped['evaluable_tests']} evaluable tests; {grouped['multiplicity']}.",
            "- Continuous models are counted once per endpoint and scoring method, not once per repeated cutpoint.",
            "- Maxstat uses the Lau94 corrected maximally selected rank-statistic p-value for multiplicity.",
            "- Grouped maxstat hazard ratios, confidence intervals and RMST estimates remain post-selection summaries.",
            "- Marker-specific and global proportional-hazards tests modify interpretation and never exclude a result.",
            "- Marker-specific cox.zph p-values below 0.05 trigger a fixed two-year early/late Cox diagnostic; the split is not selected from the multiverse results, and its status, support and estimates are retained in both continuous and grouped CSV exports.",
            "- The multiverse produces no retained/not-retained verdict.",
            *(
                [
                    "",
                    "Endpoint and score interpretation",
                    *[f"- {message}" for message in interpretation_messages],
                ]
                if interpretation_messages
                else []
            ),
            "",
            "Reproducibility",
            f"- Family hash: {result['audit']['family_reproducibility_hash']}",
            "- The execution ledger records every planned child request hash, analysis ID, audit hash and failure.",
            "- Each completed child analysis retains its own patient-level audit bundle.",
            *(
                [
                    (
                        "- A detached Ed25519 receipt signs the exact multiverse "
                        "audit report and family hash; verify it against key "
                        f"{(result['audit'].get('server_attestation') or {}).get('key_id')} "
                        "from the declared HTTPS issuer."
                    )
                ]
                if result["audit"].get("server_attestation")
                else []
            ),
            "",
        ]
    )


def render_multiverse_audit_html(result: dict[str, Any]) -> str:
    family = result["analysis_family"]
    summary = result["summary"]
    interpretation_messages = (
        family.get("interpretation_context") or {}
    ).get("messages") or []
    interpretation_items = "\n".join(
        f"<li>{escape(message)}</li>" for message in interpretation_messages
    ) or "<li>No endpoint- or score-specific interpretation context applies.</li>"
    warning_items = "\n".join(
        f"<li>{escape(message)}</li>" for message in result.get("warnings") or []
    ) or "<li>None reported.</li>"
    server_attestation = result["audit"].get("server_attestation") or {}
    rows = "\n".join(
        (
            "<tr>"
            f"<td>{escape(row['specification_id'])}</td>"
            f"<td>{escape(row['endpoint'])}</td>"
            f"<td>{escape(row['scoring_method'])}</td>"
            f"<td>{escape(row['cutpoint_method'])}</td>"
            f"<td>{escape(row['status'])}</td>"
            f"<td><code>{escape(str(row.get('analysis_id') or ''))}</code></td>"
            f"<td><code>{escape(str(row.get('audit_reproducibility_hash') or ''))}</code></td>"
            "</tr>"
        )
        for row in result["specifications"]
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>TCGA-TRACE multiverse audit {escape(result['session_id'])}</title>
  <style>
    body {{ margin: 2rem auto; max-width: 76rem; padding: 0 1rem; color: #18262d; font: 14px/1.5 system-ui, sans-serif; }}
    h1, h2 {{ line-height: 1.2; }} code {{ font-size: 12px; overflow-wrap: anywhere; }}
    table {{ width: 100%; border-collapse: collapse; }} th, td {{ border: 1px solid #cad5d9; padding: .5rem; text-align: left; vertical-align: top; }}
    th {{ background: #f2f6f7; }} dl {{ display: grid; grid-template-columns: max-content 1fr; gap: .35rem 1rem; }}
  </style>
</head>
<body>
  <h1>Prespecified multiverse audit</h1>
  <dl>
    <dt>Session</dt><dd><code>{escape(result['session_id'])}</code></dd>
    <dt>Pipeline</dt><dd>{escape(result['pipeline_version'])}</dd>
    <dt>Generated</dt><dd>{escape(result['generated_at'])}</dd>
    <dt>Family hash</dt><dd><code>{escape(result['audit']['family_reproducibility_hash'])}</code></dd>
    <dt>Attestation</dt><dd>{escape(str(server_attestation.get('status') or 'not configured'))}</dd>
    <dt>Signing key</dt><dd><code>{escape(str(server_attestation.get('key_id') or ''))}</code></dd>
    <dt>Public key</dt><dd>{escape(str(server_attestation.get('public_key_url') or ''))}</dd>
    <dt>Detached receipt</dt><dd>{escape(str(server_attestation.get('receipt_url') or ''))}</dd>
    <dt>Planned</dt><dd>{summary['planned']}</dd>
    <dt>Completed</dt><dd>{summary['completed']}</dd>
    <dt>Failed</dt><dd>{summary['failed']}</dd>
  </dl>
  <h2>Declared family</h2>
  <p>Endpoints: {escape(', '.join(family['dimensions']['endpoints']))}<br>
     Scoring: {escape(', '.join(family['dimensions']['scoring_methods']))}<br>
     Cutpoints: {escape(', '.join(family['dimensions']['cutpoint_methods']))}</p>
  <p>Continuous Cox tests and grouped cutpoint sensitivities form separate multiplicity families. No binary evidence verdict is calculated.</p>
  <h2>Endpoint and score interpretation</h2>
  <ul>{interpretation_items}</ul>
  <h2>Warnings</h2>
  <ul>{warning_items}</ul>
  <h2>Execution ledger</h2>
  <table>
    <thead><tr><th>Spec</th><th>Endpoint</th><th>Scoring</th><th>Cutpoint</th><th>Status</th><th>Analysis ID</th><th>Audit hash</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
</body>
</html>
"""


def render_specification_curve_svg(result: dict[str, Any]) -> str:
    ordered = sorted(
        result["specifications"],
        key=lambda row: (
            _effect_log_hr(row.get("grouped_effect")) is None,
            _effect_log_hr(row.get("grouped_effect")) or 0,
            row["specification_id"],
        ),
    )
    count = max(1, len(ordered))
    left = 86
    right = 28
    column_width = 28
    width = max(960, left + right + count * column_width)
    plot_width = width - left - right
    column_spacing = plot_width / count
    track_width = min(column_width - 2, column_spacing - 2)
    plot_top = 48
    plot_bottom = 298
    track_top = 338
    height = 468
    finite_logs = []
    for row in ordered:
        effect = row.get("grouped_effect") or {}
        for key in ("display_log_hr",):
            value = _number(effect.get(key))
            if value is not None:
                finite_logs.append(abs(value))
        for key in ("display_hr_conf_low", "display_hr_conf_high"):
            value = _number(effect.get(key))
            if value is not None and value > 0:
                finite_logs.append(abs(math.log(value)))
    limit = min(4.5, max(1.5, max(finite_logs, default=1.5)))

    def y_position(log_hr: float) -> float:
        bounded = max(-limit, min(limit, log_hr))
        return plot_bottom - ((bounded + limit) / (2 * limit)) * (
            plot_bottom - plot_top
        )

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" role="img" viewBox="0 0 {width} {height}" width="{width}" height="{height}">',
        "<title>TCGA-TRACE prespecified specification curve</title>",
        (
            "<desc>Grouped hazard-ratio estimates across all declared endpoint, "
            "scoring and cutpoint specifications. Filled points have grouped "
            "family BH q values at or below 0.05. Open points do not.</desc>"
        ),
        """<style>
          text { font-family: IBM Plex Sans, system-ui, sans-serif; fill: #20313a; }
          .axis { stroke: #9dafb6; stroke-width: 1; }
          .reference { stroke: #4f646d; stroke-width: 1.4; stroke-dasharray: 4 4; }
          .ci { stroke: #1f6f8b; stroke-width: 1.4; }
          .point { stroke: #1f6f8b; stroke-width: 1.5; }
          .track { fill: #eef4f5; stroke: #cad6da; stroke-width: .7; }
          .label { font-size: 11px; font-weight: 650; }
          .small { font-size: 8px; }
        </style>""",
        f'<rect width="{width}" height="{height}" fill="#fbfcfc"/>',
        '<text x="18" y="24" class="label">Grouped effect specification curve</text>',
        f'<line x1="{left}" x2="{width-right}" y1="{y_position(0):.2f}" y2="{y_position(0):.2f}" class="reference"/>',
    ]
    for hr_tick in (0.25, 0.5, 1, 2, 4):
        log_tick = math.log(hr_tick)
        if abs(log_tick) > limit:
            continue
        y = y_position(log_tick)
        parts.extend(
            [
                f'<line x1="{left-5}" x2="{left}" y1="{y:.2f}" y2="{y:.2f}" class="axis"/>',
                f'<text x="{left-9}" y="{y+3:.2f}" text-anchor="end" class="small">HR {hr_tick:g}</text>',
            ]
        )
    parts.append(
        f'<line x1="{left}" x2="{left}" y1="{plot_top}" y2="{plot_bottom}" class="axis"/>'
    )

    endpoint_abbrev = {"OS": "OS", "DSS": "DSS", "PFI": "PFI", "DFI": "DFI"}
    score_abbrev = {"single": "S", "mean": "M", "zscore": "Z", "weighted": "W"}
    cutpoint_abbrev = {
        "maxstat": "Max",
        "median": "Med",
        "tertiles": "Ter",
        "upper_quartile": "UQ",
        "upper_lower_quartile": "OQ",
        "percentile": "Pct",
    }
    track_rows = [
        ("Endpoint", endpoint_abbrev),
        ("Score", score_abbrev),
        ("Cutpoint", cutpoint_abbrev),
    ]
    for index, row in enumerate(ordered):
        x = left + column_spacing * (index + 0.5)
        effect = row.get("grouped_effect") or {}
        log_hr = _number(effect.get("display_log_hr"))
        low = _number(effect.get("display_hr_conf_low"))
        high = _number(effect.get("display_hr_conf_high"))
        if log_hr is not None and low is not None and high is not None and low > 0 and high > 0:
            y_low = y_position(math.log(low))
            y_high = y_position(math.log(high))
            y = y_position(log_hr)
            parts.append(
                f'<line x1="{x:.2f}" x2="{x:.2f}" y1="{y_high:.2f}" y2="{y_low:.2f}" class="ci"/>'
            )
            q_value = _number(row.get("grouped_bh_q_value"))
            fill = "#1f6f8b" if q_value is not None and q_value <= 0.05 else "#fbfcfc"
            parts.append(
                f'<circle cx="{x:.2f}" cy="{y:.2f}" r="3.6" fill="{fill}" class="point"/>'
            )
        else:
            y = y_position(0)
            parts.append(
                f'<path d="M {x-3:.2f} {y-3:.2f} L {x+3:.2f} {y+3:.2f} M {x+3:.2f} {y-3:.2f} L {x-3:.2f} {y+3:.2f}" stroke="#8a5a35" stroke-width="1.3"/>'
            )
        for track_index, (label, abbreviations) in enumerate(track_rows):
            track_y = track_top + track_index * 32
            value_key = (
                "endpoint"
                if track_index == 0
                else "scoring_method"
                if track_index == 1
                else "cutpoint_method"
            )
            abbreviation = abbreviations.get(
                row.get(value_key),
                str(row.get(value_key) or "")[:3],
            )
            parts.extend(
                [
                    f'<rect x="{x-track_width/2:.2f}" y="{track_y}" width="{track_width:.2f}" height="24" class="track"/>',
                    f'<text x="{x:.2f}" y="{track_y+15}" text-anchor="middle" class="small">{escape(abbreviation)}</text>',
                ]
            )
    for track_index, (label, _) in enumerate(track_rows):
        parts.append(
            f'<text x="{left-9}" y="{track_top+track_index*32+15}" text-anchor="end" class="small">{escape(label)}</text>'
        )
    parts.extend(
        [
            f'<text x="{left}" y="{height-18}" class="small">Specifications sorted by displayed grouped log(HR). Filled point: grouped-family BH q at or below 0.05. Cross: effect not estimable.</text>',
            "</svg>",
        ]
    )
    return "\n".join(parts)


def _grouped_inference(metrics: dict[str, Any]) -> tuple[float | None, str]:
    cutpoint = metrics.get("cutpoint_details") or {}
    if cutpoint.get("method") == "maxstat":
        corrected = _number(cutpoint.get("corrected_p_value"))
        if cutpoint.get("corrected_p_status") == "completed" and corrected is not None:
            return corrected, "maxstat_lau94_corrected"
        return None, "maxstat_corrected_unavailable"
    return _number(metrics.get("logrank_p_value")), "logrank"


def _compact_time_varying_effect(
    value: dict[str, Any] | None,
) -> dict[str, Any]:
    value = value or {}
    periods = value.get("periods") or {}
    early = periods.get("early") or {}
    late = periods.get("late") or {}
    change = value.get("change") or {}
    return {
        "status": value.get("status"),
        "reason": value.get("reason"),
        "split_days": _number(value.get("split_days")),
        "early_hazard_ratio": _number(early.get("hazard_ratio")),
        "early_hr_conf_low": _number(early.get("hr_conf_low")),
        "early_hr_conf_high": _number(early.get("hr_conf_high")),
        "late_hazard_ratio": _number(late.get("hazard_ratio")),
        "late_hr_conf_low": _number(late.get("hr_conf_low")),
        "late_hr_conf_high": _number(late.get("hr_conf_high")),
        "late_to_early_hr_ratio": _number(change.get("hazard_ratio_ratio")),
        "late_to_early_p_value": _number(change.get("p_value")),
        "support": value.get("support") or {},
    }


def _extract_model_effect(
    models: list[dict[str, Any]] | None,
    model_id: str,
) -> dict[str, Any]:
    model = next(
        (
            candidate
            for candidate in (models or [])
            if candidate.get("model") == model_id
        ),
        None,
    )
    if model is None:
        return _missing_effect(model_id)
    standard_completed = (
        model.get("status") == "completed"
        and _number(model.get("hazard_ratio")) is not None
        and _number(model.get("hr_conf_low")) is not None
        and _number(model.get("hr_conf_high")) is not None
    )
    firth = model.get("penalized_sensitivity") or {}
    firth_completed = (
        firth.get("status") == "completed"
        and _number(firth.get("hazard_ratio")) is not None
        and _number(firth.get("hr_conf_low")) is not None
        and _number(firth.get("hr_conf_high")) is not None
    )
    display = model if standard_completed else firth if firth_completed else {}
    estimator = (
        "standard_cox"
        if standard_completed
        else "firth_sensitivity"
        if firth_completed
        else None
    )
    display_hr = _number(display.get("hazard_ratio"))
    return {
        "model": model_id,
        "label": model.get("label"),
        "status": model.get("status"),
        "reason": model.get("reason"),
        "n_patients": model.get("n_patients"),
        "n_events": model.get("n_events"),
        "parameter_count": (
            model.get("information_diagnostics") or {}
        ).get("parameter_count"),
        "events_per_parameter": (
            model.get("information_diagnostics") or {}
        ).get("events_per_parameter"),
        "information_status": (
            model.get("information_diagnostics") or {}
        ).get("status"),
        "standard_hazard_ratio": _number(model.get("hazard_ratio")),
        "standard_hr_conf_low": _number(model.get("hr_conf_low")),
        "standard_hr_conf_high": _number(model.get("hr_conf_high")),
        "standard_p_value": _number(model.get("p_value")),
        "ph_p_value": _number(model.get("ph_p_value")),
        "ph_global_p_value": _number(model.get("ph_global_p_value")),
        "time_varying_effect": _compact_time_varying_effect(
            model.get("time_varying_effect")
        ),
        "firth_status": firth.get("status"),
        "firth_hazard_ratio": _number(firth.get("hazard_ratio")),
        "firth_hr_conf_low": _number(firth.get("hr_conf_low")),
        "firth_hr_conf_high": _number(firth.get("hr_conf_high")),
        "firth_p_value": _number(firth.get("p_value")),
        "display_estimator": estimator,
        "display_hazard_ratio": display_hr,
        "display_log_hr": math.log(display_hr) if display_hr and display_hr > 0 else None,
        "display_hr_conf_low": _number(display.get("hr_conf_low")),
        "display_hr_conf_high": _number(display.get("hr_conf_high")),
        "display_p_value": _number(display.get("p_value")),
    }


def _missing_effect(model_id: str) -> dict[str, Any]:
    return {
        "model": model_id,
        "label": None,
        "status": "not_evaluable",
        "reason": "The requested model was not returned.",
        "display_estimator": None,
        "display_hazard_ratio": None,
        "display_log_hr": None,
        "display_hr_conf_low": None,
        "display_hr_conf_high": None,
        "display_p_value": None,
        "standard_p_value": None,
        "ph_p_value": None,
        "ph_global_p_value": None,
        "time_varying_effect": _compact_time_varying_effect(None),
        "firth_status": None,
    }


def _compact_rmst(rmst: dict[str, Any] | None) -> dict[str, Any]:
    rmst = rmst or {}
    difference = rmst.get("difference") or {}
    at_risk = rmst.get("at_risk_at_tau") or {}
    return {
        "status": rmst.get("status"),
        "reason": rmst.get("reason"),
        "tau_days": _number(rmst.get("tau_days")),
        "at_risk_at_tau": at_risk,
        "estimate_days": _number(difference.get("estimate_days")),
        "conf_low": _number(difference.get("conf_low")),
        "conf_high": _number(difference.get("conf_high")),
        "p_value": _number(difference.get("p_value")),
    }


def _references_match(left: dict[str, Any], right: dict[str, Any]) -> bool:
    if left.get("patient_records_sha256") != right.get("patient_records_sha256"):
        return False
    if left.get("n_patients") != right.get("n_patients"):
        return False
    if left.get("n_events") != right.get("n_events"):
        return False
    for key in (
        "standard_hazard_ratio",
        "standard_p_value",
        "ph_p_value",
    ):
        left_value = _number((left.get("effect") or {}).get(key))
        right_value = _number((right.get("effect") or {}).get(key))
        if left_value is None or right_value is None:
            if left_value != right_value:
                return False
        elif not math.isclose(left_value, right_value, rel_tol=1e-10, abs_tol=1e-12):
            return False
    return True


def _write_specification_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = [
        "specification_id",
        "endpoint",
        "scoring_method",
        "cutpoint_method",
        "custom_percentile",
        "status",
        "analysis_id",
        "n_patients",
        "n_events",
        "inference_test",
        "inference_p_value",
        "grouped_bh_q_value",
        "grouped_bonferroni_p_value",
        "effect_model",
        "effect_estimator",
        "hazard_ratio",
        "hr_conf_low",
        "hr_conf_high",
        "effect_p_value",
        "marker_ph_p_value",
        "global_ph_p_value",
        "temporal_status",
        "temporal_split_days",
        "early_hazard_ratio",
        "early_hr_conf_low",
        "early_hr_conf_high",
        "late_hazard_ratio",
        "late_hr_conf_low",
        "late_hr_conf_high",
        "late_to_early_hr_ratio",
        "late_to_early_p_value",
        "temporal_support",
        "events_per_parameter",
        "information_status",
        "rmst_tau_days",
        "rmst_at_risk",
        "rmst_difference_days",
        "rmst_conf_low",
        "rmst_conf_high",
        "rmst_p_value",
        "group_counts",
        "event_counts",
        "analysis_request_hash",
        "audit_reproducibility_hash",
        "patient_records_sha256",
        "error_code",
        "error",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            effect = row.get("grouped_effect") or {}
            rmst = row.get("rmst") or {}
            temporal = effect.get("time_varying_effect") or {}
            writer.writerow(
                {
                    "specification_id": row.get("specification_id"),
                    "endpoint": row.get("endpoint"),
                    "scoring_method": row.get("scoring_method"),
                    "cutpoint_method": row.get("cutpoint_method"),
                    "custom_percentile": row.get("custom_percentile"),
                    "status": row.get("status"),
                    "analysis_id": row.get("analysis_id"),
                    "n_patients": row.get("n_patients"),
                    "n_events": row.get("n_events"),
                    "inference_test": row.get("inference_test"),
                    "inference_p_value": row.get("inference_p_value"),
                    "grouped_bh_q_value": row.get("grouped_bh_q_value"),
                    "grouped_bonferroni_p_value": row.get(
                        "grouped_bonferroni_p_value"
                    ),
                    "effect_model": effect.get("model"),
                    "effect_estimator": effect.get("display_estimator"),
                    "hazard_ratio": effect.get("display_hazard_ratio"),
                    "hr_conf_low": effect.get("display_hr_conf_low"),
                    "hr_conf_high": effect.get("display_hr_conf_high"),
                    "effect_p_value": effect.get("display_p_value"),
                    "marker_ph_p_value": row.get("marker_ph_p_value"),
                    "global_ph_p_value": row.get("global_ph_p_value"),
                    "temporal_status": temporal.get("status"),
                    "temporal_split_days": temporal.get("split_days"),
                    "early_hazard_ratio": temporal.get("early_hazard_ratio"),
                    "early_hr_conf_low": temporal.get("early_hr_conf_low"),
                    "early_hr_conf_high": temporal.get("early_hr_conf_high"),
                    "late_hazard_ratio": temporal.get("late_hazard_ratio"),
                    "late_hr_conf_low": temporal.get("late_hr_conf_low"),
                    "late_hr_conf_high": temporal.get("late_hr_conf_high"),
                    "late_to_early_hr_ratio": temporal.get(
                        "late_to_early_hr_ratio"
                    ),
                    "late_to_early_p_value": temporal.get(
                        "late_to_early_p_value"
                    ),
                    "temporal_support": json.dumps(
                        temporal.get("support") or {},
                        sort_keys=True,
                    ),
                    "events_per_parameter": effect.get("events_per_parameter"),
                    "information_status": effect.get("information_status"),
                    "rmst_tau_days": rmst.get("tau_days"),
                    "rmst_at_risk": json.dumps(
                        rmst.get("at_risk_at_tau") or {},
                        sort_keys=True,
                    ),
                    "rmst_difference_days": rmst.get("estimate_days"),
                    "rmst_conf_low": rmst.get("conf_low"),
                    "rmst_conf_high": rmst.get("conf_high"),
                    "rmst_p_value": rmst.get("p_value"),
                    "group_counts": json.dumps(
                        row.get("group_counts") or {},
                        sort_keys=True,
                    ),
                    "event_counts": json.dumps(
                        row.get("event_counts") or {},
                        sort_keys=True,
                    ),
                    "analysis_request_hash": row.get("analysis_request_hash"),
                    "audit_reproducibility_hash": row.get(
                        "audit_reproducibility_hash"
                    ),
                    "patient_records_sha256": row.get(
                        "patient_records_sha256"
                    ),
                    "error_code": row.get("error_code"),
                    "error": row.get("error"),
                }
            )


def _write_continuous_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = [
        "reference_id",
        "endpoint",
        "scoring_method",
        "status",
        "n_patients",
        "n_events",
        "model",
        "estimator",
        "hazard_ratio",
        "hr_conf_low",
        "hr_conf_high",
        "p_value",
        "bh_q_value",
        "bonferroni_p_value",
        "marker_ph_p_value",
        "global_ph_p_value",
        "temporal_status",
        "temporal_split_days",
        "early_hazard_ratio",
        "early_hr_conf_low",
        "early_hr_conf_high",
        "late_hazard_ratio",
        "late_hr_conf_low",
        "late_hr_conf_high",
        "late_to_early_hr_ratio",
        "late_to_early_p_value",
        "temporal_support",
        "events_per_parameter",
        "information_status",
        "patient_records_sha256",
        "source_analysis_id",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            effect = row.get("effect") or {}
            temporal = effect.get("time_varying_effect") or {}
            writer.writerow(
                {
                    "reference_id": row.get("reference_id"),
                    "endpoint": row.get("endpoint"),
                    "scoring_method": row.get("scoring_method"),
                    "status": row.get("status"),
                    "n_patients": row.get("n_patients"),
                    "n_events": row.get("n_events"),
                    "model": effect.get("model"),
                    "estimator": effect.get("display_estimator"),
                    "hazard_ratio": effect.get("display_hazard_ratio"),
                    "hr_conf_low": effect.get("display_hr_conf_low"),
                    "hr_conf_high": effect.get("display_hr_conf_high"),
                    "p_value": effect.get("standard_p_value"),
                    "bh_q_value": row.get("continuous_bh_q_value"),
                    "bonferroni_p_value": row.get(
                        "continuous_bonferroni_p_value"
                    ),
                    "marker_ph_p_value": effect.get("ph_p_value"),
                    "global_ph_p_value": effect.get("ph_global_p_value"),
                    "temporal_status": temporal.get("status"),
                    "temporal_split_days": temporal.get("split_days"),
                    "early_hazard_ratio": temporal.get("early_hazard_ratio"),
                    "early_hr_conf_low": temporal.get("early_hr_conf_low"),
                    "early_hr_conf_high": temporal.get("early_hr_conf_high"),
                    "late_hazard_ratio": temporal.get("late_hazard_ratio"),
                    "late_hr_conf_low": temporal.get("late_hr_conf_low"),
                    "late_hr_conf_high": temporal.get("late_hr_conf_high"),
                    "late_to_early_hr_ratio": temporal.get(
                        "late_to_early_hr_ratio"
                    ),
                    "late_to_early_p_value": temporal.get(
                        "late_to_early_p_value"
                    ),
                    "temporal_support": json.dumps(
                        temporal.get("support") or {},
                        sort_keys=True,
                    ),
                    "events_per_parameter": effect.get("events_per_parameter"),
                    "information_status": effect.get("information_status"),
                    "patient_records_sha256": row.get(
                        "patient_records_sha256"
                    ),
                    "source_analysis_id": row.get("source_analysis_id"),
                }
            )


def _effect_log_hr(effect: dict[str, Any] | None) -> float | None:
    return _number((effect or {}).get("display_log_hr"))


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None
