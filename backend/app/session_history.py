from __future__ import annotations

import csv
from datetime import datetime, timezone
from html import escape
import json
import math
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.attestation import attestation_metadata, write_attestation_receipt
from app.config import Settings
from app.models import ComputeJob
from app.multiverse import benjamini_hochberg
from app.r_runner import stable_hash
from app.schemas import ExploratorySessionExportRequest


SESSION_AUDIT_SCHEMA = "tcga-trace-exploratory-session-audit-v1"
SESSION_LEDGER_SCHEMA = "tcga-trace-exploratory-session-ledger-v1"
SESSION_FAMILIES = (
    "continuous_primary",
    "grouped_sensitivity",
    "signature_interaction",
)


def build_exploratory_session_report(
    *,
    request: ExploratorySessionExportRequest,
    db: Session,
    pipeline_version: str,
    generated_at: str | None = None,
) -> dict[str, Any]:
    generated_at = generated_at or datetime.now(timezone.utc).isoformat()
    request_snapshot = {
        "browser_session_id": request.browser_session_id,
        "session_label": request.session_label,
        "entries": [
            entry.model_dump(mode="json")
            for entry in request.entries
        ],
        "annotation_scope": (
            "Labels, source views and recorded times are browser-supplied "
            "annotations. Scientific requests and results are resolved from "
            "server compute jobs."
        ),
    }
    events_by_job: dict[str, list[str]] = {}
    for entry in request.entries:
        events_by_job.setdefault(entry.job_id, []).append(entry.event_id)

    source_jobs: dict[str, ComputeJob | None] = {
        job_id: db.get(ComputeJob, job_id)
        for job_id in events_by_job
    }
    runs: list[dict[str, Any]] = []
    source_job_records: list[dict[str, Any]] = []
    hypotheses_by_identity: dict[str, dict[str, Any]] = {}
    managed_family_references: list[dict[str, Any]] = []
    warnings = [
        (
            "This is a post hoc exploratory history of the selected browser "
            "events, not a prespecified analysis family."
        ),
        (
            "Benjamini-Hochberg and Bonferroni values depend on the selected "
            "export scope; adding, removing or clearing runs changes the family."
        ),
        (
            "The server receipt proves the integrity and origin of this export. "
            "It does not prove that no other analyses were run or omitted."
        ),
        (
            "Patient-level records and external-covariate row values are not "
            "embedded in the session report."
        ),
    ]

    for entry in request.entries:
        job = source_jobs.get(entry.job_id)
        run = {
            "event_id": entry.event_id,
            "recorded_at": entry.recorded_at.isoformat(),
            "label": entry.label,
            "source_view": entry.source_view,
            "source_job_id": entry.job_id,
            "source_job_kind": job.kind if job is not None else None,
            "source_job_status": job.status if job is not None else "missing",
            "result_id": job.result_id if job is not None else None,
            "server_created_at": _iso(job.created_at) if job is not None else None,
            "server_completed_at": _iso(job.completed_at) if job is not None else None,
            "captured": False,
            "exclusion_code": None,
            "exclusion_reason": None,
        }
        if job is None:
            run["exclusion_code"] = "SOURCE_JOB_NOT_FOUND"
            run["exclusion_reason"] = (
                "The supplied job ID does not resolve to a server compute job."
            )
        elif job.kind == "session":
            run["exclusion_code"] = "NESTED_SESSION_NOT_SUPPORTED"
            run["exclusion_reason"] = (
                "Exploratory session exports cannot include another session export."
            )
        elif job.status not in {"completed", "failed", "expired"}:
            run["exclusion_code"] = "SOURCE_JOB_NOT_TERMINAL"
            run["exclusion_reason"] = (
                f"The source job was {job.status} when the export was built."
            )
        else:
            run["captured"] = True
            if job.status == "failed":
                run["exclusion_code"] = "SOURCE_JOB_FAILED"
                run["exclusion_reason"] = str(
                    (job.error_json or {}).get("message")
                    or "The source compute job failed."
                )
        runs.append(run)

    for job_id, event_ids in events_by_job.items():
        job = source_jobs.get(job_id)
        if job is None or job.kind == "session":
            continue
        source_job_records.append(_source_job_record(job))
        if job.status not in {"completed", "expired"} or not job.result_json:
            continue
        if job.kind in {"multiverse", "pancancer"}:
            managed_family_references.append(
                _managed_family_reference(job, event_ids)
            )
            continue
        for child in _expand_analysis_children(job):
            if child["status"] != "completed" or not child.get("result"):
                continue
            result = child["result"]
            request_payload = child.get("request") or {}
            if child["kind"] == "combined":
                extracted = _combined_hypotheses(
                    request_payload=request_payload,
                    result=result,
                    source_job=job,
                    source_event_ids=event_ids,
                    child_index=child.get("index"),
                )
            else:
                extracted = _analysis_hypotheses(
                    request_payload=request_payload,
                    result=result,
                    source_job=job,
                    source_event_ids=event_ids,
                    child_index=child.get("index"),
                )
            for hypothesis in extracted:
                identity = hypothesis["identity_hash"]
                if identity in hypotheses_by_identity:
                    _merge_duplicate_hypothesis(
                        hypotheses_by_identity[identity],
                        hypothesis,
                    )
                else:
                    hypotheses_by_identity[identity] = hypothesis

    hypotheses = sorted(
        hypotheses_by_identity.values(),
        key=lambda row: (
            SESSION_FAMILIES.index(row["family"]),
            row.get("cohort") or "",
            row.get("endpoint") or "",
            row.get("marker") or "",
            row["identity_hash"],
        ),
    )
    analysis_families = _apply_family_multiplicity(hypotheses)
    family_prefix = {
        "continuous_primary": "C",
        "grouped_sensitivity": "G",
        "signature_interaction": "I",
    }
    counters = {family: 0 for family in SESSION_FAMILIES}
    for hypothesis in hypotheses:
        family = hypothesis["family"]
        counters[family] += 1
        hypothesis["hypothesis_id"] = (
            f"{family_prefix[family]}{counters[family]:03d}"
        )

    identity_core = {
        "pipeline_version": pipeline_version,
        "request_snapshot": request_snapshot,
        "source_jobs": source_job_records,
    }
    report_id = f"sh_{stable_hash(identity_core)[:24]}"
    excluded_events = sum(not run["captured"] for run in runs)
    failed_events = sum(
        run["captured"] and run["source_job_status"] == "failed"
        for run in runs
    )
    evaluable_hypotheses = sum(
        row.get("p_value") is not None for row in hypotheses
    )
    summary = {
        "selected_events": len(runs),
        "unique_source_jobs": len(source_job_records),
        "captured_events": sum(run["captured"] for run in runs),
        "excluded_events": excluded_events,
        "failed_events": failed_events,
        "unique_hypotheses": len(hypotheses),
        "evaluable_hypotheses": evaluable_hypotheses,
        "managed_family_references": len(managed_family_references),
        "duplicate_hypothesis_occurrences": sum(
            max(0, int(row["occurrence_count"]) - 1)
            for row in hypotheses
        ),
    }
    family_core = {
        **identity_core,
        "report_id": report_id,
        "analysis_families": analysis_families,
        "hypotheses": hypotheses,
        "managed_family_references": managed_family_references,
        "runs": runs,
    }
    reproducibility_hash = stable_hash(family_core)
    audit = {
        "schema_version": SESSION_AUDIT_SCHEMA,
        "report_type": "exploratory_session_audit",
        "report_id": report_id,
        "generated_at": generated_at,
        "pipeline_version": pipeline_version,
        "request_sha256": stable_hash(request_snapshot),
        "family_reproducibility_hash": reproducibility_hash,
        "source_job_count": len(source_job_records),
        "source_jobs": source_job_records,
        "selected_event_count": len(runs),
        "unique_hypothesis_count": len(hypotheses),
        "privacy_contract": {
            "patient_level_records_embedded": False,
            "external_covariate_rows_embedded": False,
            "source_request_hashes_recorded": True,
        },
        "scope_limit": (
            "This report covers only the browser events explicitly selected "
            "for export and cannot attest to analyses outside that selection."
        ),
    }
    if excluded_events or failed_events:
        warnings.append(
            f"{excluded_events + failed_events} selected event(s) were missing, "
            "non-terminal, nested or failed and therefore supplied no hypothesis."
        )
    return {
        "report_id": report_id,
        "status": (
            "completed"
            if excluded_events == 0 and failed_events == 0
            else "completed_with_exclusions"
        ),
        "pipeline_version": pipeline_version,
        "generated_at": generated_at,
        "request_snapshot": request_snapshot,
        "analysis_families": analysis_families,
        "summary": summary,
        "runs": runs,
        "hypotheses": hypotheses,
        "managed_family_references": managed_family_references,
        "warnings": warnings,
        "audit": audit,
        "downloads": exploratory_session_downloads(report_id),
    }


def exploratory_session_downloads(report_id: str) -> dict[str, str]:
    base = f"/api/v1/analyses/sessions/{report_id}/download"
    return {
        "json": f"{base}/json",
        "runs_csv": f"{base}/runs_csv",
        "hypotheses_csv": f"{base}/hypotheses_csv",
        "ledger": f"{base}/ledger",
        "audit_json": f"{base}/audit_json",
        "audit_html": f"{base}/audit_html",
        "methodology": f"{base}/methodology",
        "zip": f"{base}/zip",
    }


def write_exploratory_session_artifacts(
    artifact_root: Path,
    result: dict[str, Any],
    *,
    settings: Settings,
) -> dict[str, Path]:
    report_dir = artifact_root / "sessions" / result["report_id"]
    report_dir.mkdir(parents=True, exist_ok=True)
    result["audit"]["server_attestation"] = attestation_metadata(
        settings,
        subject_type="exploratory_session",
        subject_id=result["report_id"],
    )
    result["downloads"]["attestation"] = (
        f"/api/v1/analyses/sessions/{result['report_id']}"
        "/download/attestation"
    )
    paths = {
        "json": report_dir / "session_report.json",
        "runs_csv": report_dir / "runs.csv",
        "hypotheses_csv": report_dir / "hypotheses.csv",
        "ledger": report_dir / "execution_ledger.json",
        "audit_json": report_dir / "audit_report.json",
        "audit_html": report_dir / "audit_report.html",
        "methodology": report_dir / "methodology.txt",
        "attestation": report_dir / "attestation_receipt.json",
    }
    paths["runs_csv"].write_text(
        _rows_to_csv(result["runs"]),
        encoding="utf-8",
    )
    paths["hypotheses_csv"].write_text(
        _hypotheses_to_csv(result["hypotheses"]),
        encoding="utf-8",
    )
    paths["ledger"].write_text(
        json.dumps(
            {
                "schema_version": SESSION_LEDGER_SCHEMA,
                "report_id": result["report_id"],
                "analysis_families": result["analysis_families"],
                "runs": result["runs"],
                "managed_family_references": result[
                    "managed_family_references"
                ],
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
    write_attestation_receipt(
        settings,
        subject_type="exploratory_session",
        subject_id=result["report_id"],
        audit_path=paths["audit_json"],
        reproducibility_hash=result["audit"][
            "family_reproducibility_hash"
        ],
        report_schema_version=result["audit"]["schema_version"],
    )
    paths["methodology"].write_text(
        render_exploratory_session_methodology(result),
        encoding="utf-8",
    )
    paths["audit_html"].write_text(
        render_exploratory_session_audit_html(result),
        encoding="utf-8",
    )
    temporary = paths["json"].with_suffix(".json.tmp")
    try:
        temporary.write_text(
            json.dumps(
                result,
                ensure_ascii=False,
                allow_nan=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        temporary.replace(paths["json"])
    finally:
        temporary.unlink(missing_ok=True)
    return paths


def render_exploratory_session_methodology(
    result: dict[str, Any],
) -> str:
    lines = [
        "TCGA-TRACE exploratory session methodology",
        "",
        f"Report: {result['report_id']}",
        f"Pipeline: {result['pipeline_version']}",
        f"Generated: {result['generated_at']}",
        "",
        "Scope",
        (
            "- This is a post hoc record of browser events explicitly selected "
            "by the user; it is not a prespecified multiverse."
        ),
        (
            "- The server resolved every scientific request and result from its "
            "compute-job database. Browser labels and times remain annotations."
        ),
        (
            "- Exact duplicate hypotheses are counted once for multiplicity, "
            "while every run event remains in the execution ledger."
        ),
        "",
        "Multiplicity families",
    ]
    for family in SESSION_FAMILIES:
        detail = result["analysis_families"][family]
        lines.append(
            f"- {detail['label']}: {detail['evaluable_tests']} evaluable of "
            f"{detail['unique_hypotheses']} unique hypotheses; "
            "Benjamini-Hochberg and Bonferroni within this family."
        )
    lines.extend(
        [
            (
                "- Continuous Cox, grouped cutpoint and two-signature "
                "interaction tests are never pooled into one family."
            ),
            (
                "- Prespecified multiverse and pan-cancer scans retain their "
                "own internal correction and are listed only as managed-family "
                "references."
            ),
            "- No retained/not-retained verdict is calculated.",
            "",
            "Interpretation",
            (
                "- Family membership is exploratory and export-dependent. "
                "Adjusted p-values change if the selected history changes."
            ),
            (
                "- Maxstat contributes its Lau94-corrected p-value when "
                "available; grouped HR and RMST remain post-selection summaries."
            ),
            (
                "- PH diagnostics modify interpretation and never remove a "
                "hypothesis from the report."
            ),
            "",
            "Privacy and integrity",
            "- Patient-level records are not included.",
            "- External-covariate row values are not included.",
            (
                "- Source request and result hashes bind the report to the "
                "server records without exposing those row values."
            ),
            (
                "- A detached Ed25519 receipt signs the exact audit report and "
                "family reproducibility hash."
            ),
            "",
        ]
    )
    return "\n".join(lines)


def render_exploratory_session_audit_html(
    result: dict[str, Any],
) -> str:
    family_rows = "\n".join(
        (
            "<tr>"
            f"<td>{escape(detail['label'])}</td>"
            f"<td>{detail['unique_hypotheses']}</td>"
            f"<td>{detail['evaluable_tests']}</td>"
            f"<td>{escape(detail['p_value_contract'])}</td>"
            "</tr>"
        )
        for detail in (
            result["analysis_families"][family]
            for family in SESSION_FAMILIES
        )
    )
    run_rows = "\n".join(
        (
            "<tr>"
            f"<td><code>{escape(str(run['event_id']))}</code></td>"
            f"<td>{escape(str(run.get('source_job_kind') or ''))}</td>"
            f"<td>{escape(str(run.get('source_job_status') or ''))}</td>"
            f"<td><code>{escape(str(run.get('source_job_id') or ''))}</code></td>"
            f"<td>{escape(str(run.get('exclusion_code') or ''))}</td>"
            "</tr>"
        )
        for run in result["runs"]
    )
    warning_items = "\n".join(
        f"<li>{escape(message)}</li>"
        for message in result.get("warnings") or []
    )
    attestation = result["audit"].get("server_attestation") or {}
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>TCGA-TRACE exploratory session {escape(result['report_id'])}</title>
  <style>
    body {{ margin: 2rem auto; max-width: 76rem; padding: 0 1rem; color: #18262d; font: 14px/1.5 system-ui, sans-serif; }}
    h1, h2 {{ line-height: 1.2; }} code {{ font-size: 12px; overflow-wrap: anywhere; }}
    table {{ width: 100%; border-collapse: collapse; }} th, td {{ border: 1px solid #cad5d9; padding: .5rem; text-align: left; vertical-align: top; }}
    th {{ background: #f2f6f7; }} dl {{ display: grid; grid-template-columns: max-content 1fr; gap: .35rem 1rem; }}
  </style>
</head>
<body>
  <h1>Exploratory session audit</h1>
  <p>This is a post hoc record of selected runs, not a prespecified family and not proof that no other runs occurred.</p>
  <dl>
    <dt>Report</dt><dd><code>{escape(result['report_id'])}</code></dd>
    <dt>Pipeline</dt><dd>{escape(result['pipeline_version'])}</dd>
    <dt>Generated</dt><dd>{escape(result['generated_at'])}</dd>
    <dt>Family hash</dt><dd><code>{escape(result['audit']['family_reproducibility_hash'])}</code></dd>
    <dt>Attestation</dt><dd>{escape(str(attestation.get('status') or 'not configured'))}</dd>
    <dt>Signing key</dt><dd><code>{escape(str(attestation.get('key_id') or ''))}</code></dd>
    <dt>Selected events</dt><dd>{result['summary']['selected_events']}</dd>
    <dt>Unique hypotheses</dt><dd>{result['summary']['unique_hypotheses']}</dd>
  </dl>
  <h2>Exploratory multiplicity families</h2>
  <table>
    <thead><tr><th>Family</th><th>Unique</th><th>Evaluable</th><th>p-value contract</th></tr></thead>
    <tbody>{family_rows}</tbody>
  </table>
  <h2>Scope warnings</h2>
  <ul>{warning_items}</ul>
  <h2>Run ledger</h2>
  <table>
    <thead><tr><th>Event</th><th>Kind</th><th>Status</th><th>Server job</th><th>Exclusion</th></tr></thead>
    <tbody>{run_rows}</tbody>
  </table>
</body>
</html>
"""


def _source_job_record(job: ComputeJob) -> dict[str, Any]:
    return {
        "job_id": job.id,
        "kind": job.kind,
        "status": job.status,
        "params_hash": job.params_hash,
        "request_sha256": stable_hash(job.request_payload or {}),
        "result_id": job.result_id,
        "result_sha256": (
            stable_hash(job.result_json)
            if job.result_json is not None
            else None
        ),
        "created_at": _iso(job.created_at),
        "completed_at": _iso(job.completed_at),
    }


def _expand_analysis_children(
    job: ComputeJob,
) -> list[dict[str, Any]]:
    if job.kind in {"analysis", "combined"}:
        return [
            {
                "index": None,
                "kind": job.kind,
                "status": "completed",
                "request": job.request_payload,
                "result": job.result_json,
            }
        ]
    if job.kind != "batch":
        return []
    requests = list((job.request_payload or {}).get("analyses") or [])
    children = []
    for item in (job.result_json or {}).get("results") or []:
        index = int(item.get("index") or 0)
        children.append(
            {
                "index": index,
                "kind": "analysis",
                "status": item.get("status"),
                "request": requests[index] if index < len(requests) else {},
                "result": item.get("result"),
                "error": item.get("error"),
                "code": item.get("code"),
            }
        )
    return children


def _analysis_hypotheses(
    *,
    request_payload: dict[str, Any],
    result: dict[str, Any],
    source_job: ComputeJob,
    source_event_ids: list[str],
    child_index: int | None,
) -> list[dict[str, Any]]:
    metrics = result.get("metrics") or {}
    scientific = _scientific_request(request_payload)
    audit = metrics.get("audit_report") or {}
    clinical_adjustment = metrics.get("clinical_adjustment") or {}
    continuous_model_id = (
        clinical_adjustment.get("continuous_model")
        or "continuous_univariable"
    )
    grouped_model_id = (
        clinical_adjustment.get("grouped_model")
        or "univariable"
    )
    continuous_model = _find_model(
        (metrics.get("continuous_analysis") or {}).get("linear_models"),
        continuous_model_id,
    )
    grouped_model = _find_model(
        metrics.get("cox_models"),
        grouped_model_id,
    )
    marker = _analysis_marker(request_payload)
    base = {
        "cohort": request_payload.get("cohort"),
        "endpoint": request_payload.get("endpoint"),
        "marker": marker,
        "scoring_method": request_payload.get("signature_method"),
        "cutpoint_method": request_payload.get("cutpoint_method"),
        "adjustment": _adjustment_label(request_payload),
        "source_job_ids": [source_job.id],
        "source_event_ids": list(source_event_ids),
        "source_analysis_ids": [str(result.get("id") or "")],
        "source_child_indices": (
            [child_index] if child_index is not None else []
        ),
        "occurrence_count": len(source_event_ids),
        "exploratory_post_hoc": True,
    }
    continuous_spec = dict(scientific)
    continuous_spec.pop("cutpoint_method", None)
    continuous_spec.pop("custom_percentile", None)
    continuous_effect = _model_effect(continuous_model)
    continuous_identity = stable_hash(
        {
            "family": "continuous_primary",
            "specification": continuous_spec,
            "continuous_patient_records_sha256": audit.get(
                "continuous_patient_records_sha256"
            ),
            "effect": continuous_effect,
        }
    )
    inference_p, inference_test = _grouped_inference(metrics)
    grouped_effect = _model_effect(grouped_model)
    grouped_identity = stable_hash(
        {
            "family": "grouped_sensitivity",
            "specification": scientific,
            "patient_records_sha256": audit.get(
                "patient_records_sha256"
            ),
            "inference_test": inference_test,
            "p_value": inference_p,
            "effect": grouped_effect,
        }
    )
    return [
        {
            **base,
            "family": "continuous_primary",
            "identity_hash": continuous_identity,
            "model": continuous_model_id,
            "inference_test": "cox_wald",
            "p_value": _number(
                (continuous_model or {}).get("p_value")
            ),
            "effect": continuous_effect,
            "status": _model_status(continuous_model),
            "reason": (continuous_model or {}).get("reason"),
        },
        {
            **base,
            "family": "grouped_sensitivity",
            "identity_hash": grouped_identity,
            "model": grouped_model_id,
            "inference_test": inference_test,
            "p_value": inference_p,
            "effect": grouped_effect,
            "status": (
                "completed"
                if inference_p is not None
                else "not_evaluable"
            ),
            "reason": (
                None
                if inference_p is not None
                else "The grouped inference p-value was unavailable."
            ),
        },
    ]


def _combined_hypotheses(
    *,
    request_payload: dict[str, Any],
    result: dict[str, Any],
    source_job: ComputeJob,
    source_event_ids: list[str],
    child_index: int | None,
) -> list[dict[str, Any]]:
    metrics = result.get("metrics") or {}
    scientific = _scientific_request(request_payload)
    audit = metrics.get("audit_report") or {}
    clinical_adjustment = metrics.get("clinical_adjustment") or {}
    interaction_model_id = (
        clinical_adjustment.get("interaction_model")
        or "signature_interaction"
    )
    interaction_model = _find_model(
        metrics.get("signature_interaction_cox_models"),
        interaction_model_id,
    )
    interaction_term = (
        (interaction_model or {}).get("interaction_term") or {}
    )
    marker = _combined_marker(request_payload)
    base = {
        "cohort": request_payload.get("cohort"),
        "endpoint": request_payload.get("endpoint"),
        "marker": marker,
        "scoring_method": "two_signatures",
        "cutpoint_method": request_payload.get("combination_method"),
        "adjustment": _adjustment_label(request_payload),
        "source_job_ids": [source_job.id],
        "source_event_ids": list(source_event_ids),
        "source_analysis_ids": [str(result.get("id") or "")],
        "source_child_indices": (
            [child_index] if child_index is not None else []
        ),
        "occurrence_count": len(source_event_ids),
        "exploratory_post_hoc": True,
    }
    grouped_p = _number(metrics.get("logrank_p_value"))
    grouped_identity = stable_hash(
        {
            "family": "grouped_sensitivity",
            "specification": scientific,
            "patient_records_sha256": audit.get(
                "patient_records_sha256"
            ),
            "inference_test": "logrank_omnibus",
            "p_value": grouped_p,
        }
    )
    interaction_spec = dict(scientific)
    interaction_spec.pop("combination_method", None)
    interaction_effect = _interaction_effect(
        interaction_model,
        interaction_term,
    )
    interaction_identity = stable_hash(
        {
            "family": "signature_interaction",
            "specification": interaction_spec,
            "continuous_patient_records_sha256": audit.get(
                "continuous_patient_records_sha256"
            ),
            "effect": interaction_effect,
        }
    )
    return [
        {
            **base,
            "family": "grouped_sensitivity",
            "identity_hash": grouped_identity,
            "model": "combined_groups",
            "inference_test": "logrank_omnibus",
            "p_value": grouped_p,
            "effect": {
                "n_patients": metrics.get("n_patients"),
                "n_events": metrics.get("n_events"),
                "hazard_ratio": None,
                "hr_conf_low": None,
                "hr_conf_high": None,
                "ph_p_value": None,
                "ph_global_p_value": None,
            },
            "status": (
                "completed"
                if grouped_p is not None
                else "not_evaluable"
            ),
            "reason": (
                None
                if grouped_p is not None
                else "The combined-group log-rank p-value was unavailable."
            ),
        },
        {
            **base,
            "family": "signature_interaction",
            "identity_hash": interaction_identity,
            "model": interaction_model_id,
            "inference_test": "cox_interaction_wald",
            "p_value": _number(interaction_term.get("p_value")),
            "effect": interaction_effect,
            "status": (
                "completed"
                if (interaction_model or {}).get("status") == "completed"
                and _number(interaction_term.get("p_value")) is not None
                else "not_evaluable"
            ),
            "reason": (interaction_model or {}).get("reason"),
        },
    ]


def _managed_family_reference(
    job: ComputeJob,
    source_event_ids: list[str],
) -> dict[str, Any]:
    result = job.result_json or {}
    audit = result.get("audit") or {}
    if job.kind == "multiverse":
        contract = (
            "Prespecified continuous and grouped families with internal "
            "Benjamini-Hochberg and Bonferroni correction."
        )
        family = result.get("analysis_family") or {}
    else:
        contract = (
            "Pan-cancer cohort scan with its own across-cohort FDR family; "
            "it is not mixed with single-cohort session hypotheses."
        )
        family = {
            "fdr_threshold": result.get("fdr_threshold"),
            "effect_scale": result.get("effect_scale") or {},
        }
    return {
        "source_job_id": job.id,
        "source_event_ids": list(source_event_ids),
        "kind": job.kind,
        "result_id": job.result_id,
        "status": job.status,
        "summary": result.get("summary") or {},
        "internal_family": family,
        "internal_multiplicity_contract": contract,
        "audit_reproducibility_hash": (
            audit.get("family_reproducibility_hash")
            or audit.get("reproducibility_hash")
        ),
        "recounted_in_session_family": False,
    }


def _apply_family_multiplicity(
    hypotheses: list[dict[str, Any]],
) -> dict[str, Any]:
    definitions = {
        "continuous_primary": {
            "label": "Continuous Cox hypotheses",
            "unit": (
                "one unique cohort, endpoint, expression score, eligibility "
                "set and selected Cox adjustment"
            ),
            "p_value_contract": (
                "standard selected continuous Cox marker-term p-value"
            ),
            "cutpoint_independent": True,
        },
        "grouped_sensitivity": {
            "label": "Grouped cutpoint sensitivities",
            "unit": (
                "one unique cohort, endpoint, score and cutpoint "
                "specification"
            ),
            "p_value_contract": (
                "log-rank p-value, or Lau94-corrected maxstat p-value"
            ),
            "cutpoint_independent": False,
        },
        "signature_interaction": {
            "label": "Two-signature interaction hypotheses",
            "unit": (
                "one unique cohort, endpoint, signature pair and selected "
                "interaction Cox adjustment"
            ),
            "p_value_contract": (
                "selected Cox signature A x signature B interaction-term p-value"
            ),
            "cutpoint_independent": True,
        },
    }
    output: dict[str, Any] = {}
    for family in SESSION_FAMILIES:
        rows = [row for row in hypotheses if row["family"] == family]
        p_values = [row.get("p_value") for row in rows]
        q_values = benjamini_hochberg(p_values)
        evaluable = sum(value is not None for value in q_values)
        for row, q_value in zip(rows, q_values):
            row["bh_q_value"] = q_value
            row["bonferroni_p_value"] = (
                min(1.0, float(row["p_value"]) * evaluable)
                if row.get("p_value") is not None and evaluable
                else None
            )
        output[family] = {
            **definitions[family],
            "declared_before_execution": False,
            "scope": "selected exploratory session export",
            "unique_hypotheses": len(rows),
            "evaluable_tests": evaluable,
            "multiplicity": (
                "Benjamini-Hochberg and Bonferroni within this export-defined family"
            ),
            "binary_verdict": False,
        }
    output["managed_family_policy"] = {
        "multiverse": "reference only; retain internal declared-family correction",
        "pancancer": "reference only; retain internal across-cohort FDR",
    }
    output["session_scope_is_complete_claim"] = False
    return output


def _merge_duplicate_hypothesis(
    target: dict[str, Any],
    incoming: dict[str, Any],
) -> None:
    for key in (
        "source_job_ids",
        "source_event_ids",
        "source_analysis_ids",
        "source_child_indices",
    ):
        target[key] = list(
            dict.fromkeys([*target.get(key, []), *incoming.get(key, [])])
        )
    target["occurrence_count"] = int(
        target.get("occurrence_count") or 0
    ) + int(incoming.get("occurrence_count") or 0)


def _scientific_request(payload: dict[str, Any]) -> dict[str, Any]:
    external = payload.get("external_covariates")
    external_summary = None
    if external:
        external_summary = {
            "schema_version": external.get("schema_version"),
            "source_label": external.get("source_label"),
            "definitions": external.get("definitions") or [],
            "row_count": len(external.get("rows") or []),
            "dataset_sha256": stable_hash(external),
        }
    keys = (
        "cohort",
        "gene_symbol",
        "signature_method",
        "signature_genes",
        "signature_a",
        "signature_b",
        "endpoint",
        "expression_scale",
        "cutpoint_method",
        "custom_percentile",
        "combination_method",
        "filters",
        "adjustment_covariates",
        "external_adjustment_covariates",
    )
    result = {
        key: payload.get(key)
        for key in keys
        if key in payload
    }
    if external_summary:
        result["external_covariates"] = external_summary
    return result


def _analysis_marker(payload: dict[str, Any]) -> str:
    method = str(payload.get("signature_method") or "single")
    if method == "single":
        return str(payload.get("gene_symbol") or "")
    genes = [
        str(item.get("gene_symbol") or "")
        for item in payload.get("signature_genes") or []
    ]
    return f"{method}: {', '.join(filter(None, genes))}"


def _combined_marker(payload: dict[str, Any]) -> str:
    a = payload.get("signature_a") or {}
    b = payload.get("signature_b") or {}
    a_label = a.get("name") or a.get("gene_symbol") or "Signature A"
    b_label = b.get("name") or b.get("gene_symbol") or "Signature B"
    return f"{a_label} x {b_label}"


def _adjustment_label(payload: dict[str, Any]) -> str:
    clinical = list(payload.get("adjustment_covariates") or [])
    external = list(
        payload.get("external_adjustment_covariates") or []
    )
    selected = [*clinical, *external]
    return ", ".join(selected) if selected else "Univariable"


def _find_model(
    models: list[dict[str, Any]] | None,
    model_id: str,
) -> dict[str, Any] | None:
    return next(
        (
            model
            for model in (models or [])
            if model.get("model") == model_id
        ),
        None,
    )


def _model_effect(
    model: dict[str, Any] | None,
) -> dict[str, Any]:
    model = model or {}
    diagnostics = model.get("information_diagnostics") or {}
    return {
        "n_patients": model.get("n_patients"),
        "n_events": model.get("n_events"),
        "hazard_ratio": _number(model.get("hazard_ratio")),
        "hr_conf_low": _number(model.get("hr_conf_low")),
        "hr_conf_high": _number(model.get("hr_conf_high")),
        "standard_error": _number(model.get("standard_error")),
        "ph_p_value": _number(model.get("ph_p_value")),
        "ph_global_p_value": _number(model.get("ph_global_p_value")),
        "parameter_count": diagnostics.get("parameter_count"),
        "events_per_parameter": diagnostics.get(
            "events_per_parameter"
        ),
        "information_status": diagnostics.get("status"),
    }


def _interaction_effect(
    model: dict[str, Any] | None,
    interaction_term: dict[str, Any],
) -> dict[str, Any]:
    effect = _model_effect(model)
    effect.update(
        {
            "hazard_ratio": _number(
                interaction_term.get("hazard_ratio")
            ),
            "hr_conf_low": _number(
                interaction_term.get("hr_conf_low")
            ),
            "hr_conf_high": _number(
                interaction_term.get("hr_conf_high")
            ),
            "standard_error": _number(
                interaction_term.get("standard_error")
            ),
            "ph_p_value": _number(
                (model or {}).get("ph_p_value")
            ),
        }
    )
    return effect


def _model_status(model: dict[str, Any] | None) -> str:
    if model is None:
        return "not_evaluable"
    return (
        "completed"
        if model.get("status") == "completed"
        and _number(model.get("p_value")) is not None
        else "not_evaluable"
    )


def _grouped_inference(
    metrics: dict[str, Any],
) -> tuple[float | None, str]:
    cutpoint = metrics.get("cutpoint_details") or {}
    if cutpoint.get("method") == "maxstat":
        corrected = _number(cutpoint.get("corrected_p_value"))
        if (
            cutpoint.get("corrected_p_status") == "completed"
            and corrected is not None
        ):
            return corrected, "maxstat_lau94_corrected"
        return None, "maxstat_corrected_unavailable"
    return _number(metrics.get("logrank_p_value")), "logrank"


def _rows_to_csv(rows: list[dict[str, Any]]) -> str:
    fields = [
        "event_id",
        "recorded_at",
        "label",
        "source_view",
        "source_job_id",
        "source_job_kind",
        "source_job_status",
        "result_id",
        "server_created_at",
        "server_completed_at",
        "captured",
        "exclusion_code",
        "exclusion_reason",
    ]
    return _write_csv(fields, rows)


def _hypotheses_to_csv(rows: list[dict[str, Any]]) -> str:
    flattened = []
    for row in rows:
        effect = row.get("effect") or {}
        flattened.append(
            {
                "hypothesis_id": row.get("hypothesis_id"),
                "family": row.get("family"),
                "cohort": row.get("cohort"),
                "endpoint": row.get("endpoint"),
                "marker": row.get("marker"),
                "scoring_method": row.get("scoring_method"),
                "cutpoint_method": row.get("cutpoint_method"),
                "adjustment": row.get("adjustment"),
                "model": row.get("model"),
                "inference_test": row.get("inference_test"),
                "status": row.get("status"),
                "n_patients": effect.get("n_patients"),
                "n_events": effect.get("n_events"),
                "hazard_ratio": effect.get("hazard_ratio"),
                "hr_conf_low": effect.get("hr_conf_low"),
                "hr_conf_high": effect.get("hr_conf_high"),
                "p_value": row.get("p_value"),
                "bh_q_value": row.get("bh_q_value"),
                "bonferroni_p_value": row.get(
                    "bonferroni_p_value"
                ),
                "ph_p_value": effect.get("ph_p_value"),
                "ph_global_p_value": effect.get(
                    "ph_global_p_value"
                ),
                "occurrence_count": row.get("occurrence_count"),
                "source_job_ids": "|".join(
                    row.get("source_job_ids") or []
                ),
                "source_event_ids": "|".join(
                    row.get("source_event_ids") or []
                ),
                "source_analysis_ids": "|".join(
                    row.get("source_analysis_ids") or []
                ),
                "identity_hash": row.get("identity_hash"),
            }
        )
    fields = list(flattened[0]) if flattened else [
        "hypothesis_id",
        "family",
        "cohort",
        "endpoint",
        "marker",
        "p_value",
        "bh_q_value",
        "bonferroni_p_value",
    ]
    return _write_csv(fields, flattened)


def _write_csv(
    fields: list[str],
    rows: list[dict[str, Any]],
) -> str:
    from io import StringIO

    buffer = StringIO()
    writer = csv.DictWriter(
        buffer,
        fieldnames=fields,
        extrasaction="ignore",
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def _number(value: Any) -> float | None:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return numeric if math.isfinite(numeric) else None
