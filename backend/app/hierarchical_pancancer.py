"""Statistical core for the hierarchical pan-cancer analysis.

The module deliberately operates on release-level Cox effects rather than raw
expression matrices.  Expression values are put on a robust, study-specific
IQR scale by ``hierarchical_pancancer_cox.R`` before they reach this module.
Pooling then happens in two explicit stages: studies within cancer, followed
by cancer summaries across cancers.

This file has no API or database dependencies.  Keeping the statistical core
pure makes it possible to test the estimand and all pooling guards without
changing the historical TCGA pan-cancer workflow.
"""

from __future__ import annotations

import json
import math
import subprocess
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Sequence

from app.pancancer import common_scale_meta_analysis_from_rows


HIERARCHICAL_EFFECT_SCALE = "within_study_iqr"
HIERARCHICAL_EFFECT_SCALE_LABEL = (
    "Cox hazard ratio per +1 within-study expression IQR"
)
HIERARCHICAL_MODEL = (
    "two-stage REML random-effects with modified HKSJ inference"
)

COMPARABILITY_FIELDS: tuple[tuple[str, str, str], ...] = (
    ("endpoint", "mixed_endpoints", "survival endpoints"),
    ("time_origin", "mixed_time_origins", "survival time origins"),
    ("clinical_context", "mixed_clinical_contexts", "clinical contexts"),
    ("model_family", "mixed_model_families", "Cox model families"),
)


def validate_hierarchical_effects(
    rows: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    """Validate that release effects form a defensible pooling set.

    Only completed rows with ``pooling_eligible`` (default ``True``) enter the
    synthesis.  Descriptive or failed rows remain in the audit trail.  The
    function intentionally blocks unverifiable and mixed endpoint, time-origin,
    clinical-context, model-family, and effect-scale sets.
    """

    included: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    for position, row in enumerate(rows):
        normalized = dict(row)
        normalized["_input_position"] = position
        if row.get("status") != "completed":
            excluded.append(
                _exclusion_record(row, "effect_not_completed")
            )
            continue
        if row.get("pooling_eligible") is False:
            excluded.append(
                _exclusion_record(
                    row,
                    str(row.get("pooling_exclusion_reason") or "not_pooling_eligible"),
                )
            )
            continue
        included.append(normalized)

    base = {
        "included_count": len(included),
        "excluded_count": len(excluded),
        "included_release_ids": sorted(
            str(row.get("release_id"))
            for row in included
            if row.get("release_id")
        ),
        "excluded": sorted(
            excluded,
            key=lambda row: (
                str(row.get("cancer_id") or ""),
                str(row.get("study_id") or ""),
                str(row.get("release_id") or ""),
            ),
        ),
    }
    if not included:
        return {
            **base,
            "eligible": False,
            "code": "no_completed_effects",
            "reason": "No completed, pooling-eligible release effects were available.",
        }

    missing_identifiers: list[dict[str, Any]] = []
    invalid_effects: list[str] = []
    for row in included:
        release_id = _clean(row.get("release_id"))
        missing = [
            field
            for field in ("release_id", "study_id", "cancer_id")
            if not _clean(row.get(field))
        ]
        if missing:
            missing_identifiers.append(
                {"release_id": release_id, "missing_fields": missing}
            )
        log_hr, standard_error = _effect_pair(row)
        if log_hr is None or standard_error is None or standard_error <= 0:
            invalid_effects.append(release_id or f"row-{row['_input_position']}")
    if missing_identifiers:
        return {
            **base,
            "eligible": False,
            "code": "missing_universe_identifiers",
            "reason": (
                "Every pooled effect must identify its release, study, and cancer."
            ),
            "details": missing_identifiers,
        }
    if invalid_effects:
        return {
            **base,
            "eligible": False,
            "code": "invalid_effect_estimates",
            "reason": (
                "Every pooled release requires a finite log hazard ratio and a "
                "strictly positive standard error."
            ),
            "release_ids": sorted(invalid_effects),
        }

    release_counts = Counter(_clean(row.get("release_id")) for row in included)
    duplicate_releases = sorted(
        release_id for release_id, count in release_counts.items() if count > 1
    )
    if duplicate_releases:
        return {
            **base,
            "eligible": False,
            "code": "duplicate_release_effects",
            "reason": "A release may contribute at most one effect to a synthesis.",
            "release_ids": duplicate_releases,
        }

    missing_comparability: dict[str, list[str]] = {}
    comparability: dict[str, str] = {}
    for field, mixed_code, label in COMPARABILITY_FIELDS:
        values_by_release = {
            _clean(row.get("release_id")): _normalized_category(row.get(field))
            for row in included
        }
        missing = sorted(
            release_id
            for release_id, value in values_by_release.items()
            if not value
        )
        if missing:
            missing_comparability[field] = missing
            continue
        values = sorted(set(values_by_release.values()))
        if len(values) > 1:
            return {
                **base,
                "eligible": False,
                "code": mixed_code,
                "comparability": mixed_code,
                "reason": (
                    f"Completed release effects use mixed {label}; pooling is "
                    "intentionally blocked."
                ),
                "field": field,
                "values": values,
            }
        comparability[field] = values[0]
    if missing_comparability:
        return {
            **base,
            "eligible": False,
            "code": "comparability_metadata_unavailable",
            "comparability": "metadata_unavailable",
            "reason": (
                "Endpoint, time origin, clinical context, and model family must "
                "be recorded for every pooled effect."
            ),
            "missing": missing_comparability,
        }

    scales_by_release = {
        _clean(row.get("release_id")): _effect_scale(row)
        for row in included
    }
    missing_scales = sorted(
        release_id
        for release_id, scale in scales_by_release.items()
        if scale is None
    )
    if missing_scales:
        return {
            **base,
            "eligible": False,
            "code": "effect_scale_unavailable",
            "comparability": "effect_scale_unavailable",
            "reason": (
                "The within-study IQR effect scale must be recorded for every "
                "pooled release."
            ),
            "release_ids": missing_scales,
        }
    observed_scales = sorted(set(scales_by_release.values()))
    if observed_scales != [HIERARCHICAL_EFFECT_SCALE]:
        return {
            **base,
            "eligible": False,
            "code": "mixed_or_unsupported_effect_scales",
            "comparability": "mixed_effect_scales",
            "reason": (
                "Hierarchical synthesis accepts only Cox effects expressed per "
                "+1 within-study expression IQR."
            ),
            "effect_scales": observed_scales,
        }

    clusters: dict[str, list[str]] = defaultdict(list)
    for row in included:
        independence_unit = _clean(
            row.get("study_cluster_id") or row.get("study_id")
        )
        clusters[independence_unit].append(_clean(row.get("release_id")))
    dependent = {
        cluster_id: sorted(release_ids)
        for cluster_id, release_ids in clusters.items()
        if len(release_ids) > 1
    }
    if dependent:
        return {
            **base,
            "eligible": False,
            "code": "dependent_releases",
            "comparability": "non_independent_study_units",
            "reason": (
                "More than one release belongs to the same study cluster. "
                "Select one primary release or mark the others as descriptive."
            ),
            "study_clusters": dependent,
        }

    return {
        **base,
        "eligible": True,
        "code": "eligible",
        "reason": None,
        "comparability": {
            **comparability,
            "effect_scale": HIERARCHICAL_EFFECT_SCALE,
            "effect_scale_label": HIERARCHICAL_EFFECT_SCALE_LABEL,
        },
    }


def hierarchical_meta_analysis(
    rows: Sequence[dict[str, Any]],
    *,
    alpha: float = 0.05,
    formal_min_cancers: int = 5,
    formal_min_events: int = 100,
) -> dict[str, Any]:
    """Pool release effects within cancer and cancer effects globally.

    The result always contains the validation ledger.  Invalid mixtures return
    an unavailable result instead of silently dropping an incompatible study.
    Leave-one-out analyses rerun the complete two-stage synthesis so a study
    omission can change both its cancer summary and the global estimate.
    """

    validation = validate_hierarchical_effects(rows)
    if not validation["eligible"]:
        return {
            "available": False,
            "model": HIERARCHICAL_MODEL,
            "reason": validation["reason"],
            "code": validation["code"],
            "validation": validation,
            "classification": "insufficient_support",
            "study_effects": [],
            "cancer_effects": [],
            "global_effect": None,
            "leave_one_study_out": [],
            "leave_one_cancer_out": [],
        }

    included_ids = set(validation["included_release_ids"])
    included = [
        _canonical_effect(row)
        for row in rows
        if _clean(row.get("release_id")) in included_ids
        and row.get("status") == "completed"
        and row.get("pooling_eligible") is not False
    ]
    included.sort(key=_effect_sort_key)
    core = _synthesize_core(included)

    leave_one_study_out = []
    if len(included) > 1:
        for omitted in included:
            sensitivity = _synthesize_core(
                [
                    row
                    for row in included
                    if row["release_id"] != omitted["release_id"]
                ]
            )
            leave_one_study_out.append(
                _sensitivity_record(
                    sensitivity,
                    omitted,
                    omitted_kind="study",
                )
            )

    cancers = sorted({row["cancer_id"] for row in included})
    leave_one_cancer_out = []
    if len(cancers) > 1:
        for cancer_id in cancers:
            sensitivity = _synthesize_core(
                [row for row in included if row["cancer_id"] != cancer_id]
            )
            leave_one_cancer_out.append(
                _sensitivity_record(
                    sensitivity,
                    {"cancer_id": cancer_id},
                    omitted_kind="cancer",
                )
            )

    replicated_cancer_effects = [
        row
        for row in core.get("cancer_effects", [])
        if int(row.get("n_studies") or 0) >= 2
    ]
    replicated_cancers = {
        str(row["cancer_id"]) for row in replicated_cancer_effects
    }
    replicated_rows = [
        row for row in included if row["cancer_id"] in replicated_cancers
    ]
    all_events = sum(
        int(row["n_events"])
        for row in included
        if row.get("n_events") is not None
    )
    all_event_counts_recorded = bool(included) and all(
        row.get("n_events") is not None for row in included
    )
    replicated_patients = sum(
        int(row["n_patients"])
        for row in replicated_rows
        if row.get("n_patients") is not None
    )
    all_replicated_patient_counts_recorded = all(
        row.get("n_patients") is not None for row in replicated_rows
    )
    total_events = sum(
        int(row["n_events"])
        for row in replicated_rows
        if row.get("n_events") is not None
    )
    all_events_recorded = all(
        row.get("n_events") is not None for row in replicated_rows
    )
    formal_support_reasons: list[str] = []
    if len(replicated_cancers) < formal_min_cancers:
        formal_support_reasons.append(
            "requires at least "
            f"{formal_min_cancers} cancers with two independent study clusters; "
            f"found {len(replicated_cancers)}"
        )
    if not all_events_recorded:
        formal_support_reasons.append(
            "event counts are unavailable for one or more studies"
        )
    elif total_events < formal_min_events:
        formal_support_reasons.append(
            f"requires at least {formal_min_events} events; found {total_events}"
        )
    formal_support = not formal_support_reasons
    classification = _classify_global_result(
        core.get("global_effect"),
        replicated_cancer_effects,
        leave_one_cancer_out,
        formal_support=formal_support,
        alpha=alpha,
    )

    return {
        "available": bool(
            core.get("global_effect")
            and core["global_effect"].get("available")
        ),
        "model": HIERARCHICAL_MODEL,
        "reason": (
            None
            if core.get("global_effect")
            and core["global_effect"].get("available")
            else (core.get("global_effect") or {}).get("reason")
        ),
        "validation": validation,
        "comparability": validation["comparability"],
        "effect_scale": {
            "id": HIERARCHICAL_EFFECT_SCALE,
            "label": HIERARCHICAL_EFFECT_SCALE_LABEL,
            "normalization_scope": "independently within each release",
        },
        "study_effects": included,
        "cancer_effects": core["cancer_effects"],
        "global_effect": core["global_effect"],
        "leave_one_study_out": leave_one_study_out,
        "leave_one_cancer_out": leave_one_cancer_out,
        "formal_pan_cancer_support": {
            "supported": formal_support,
            "minimum_cancers": formal_min_cancers,
            "observed_cancers": len(replicated_cancers),
            "minimum_events": formal_min_events,
            "observed_events": total_events if all_events_recorded else None,
            "reasons": formal_support_reasons,
        },
        "within_cancer_replication": {
            "minimum_independent_studies": 2,
            "replicated_cancers": sorted(replicated_cancers),
            "replicated_cancer_count": len(replicated_cancers),
            "single_study_cancers": sorted(
                row["cancer_id"]
                for row in core.get("cancer_effects", [])
                if int(row.get("n_studies") or 0) == 1
            ),
            "single_study_effects_are_descriptive_only": True,
        },
        "classification": classification,
        "summary": {
            "studies": len(included),
            "cancers": len(cancers),
            "patients": sum(
                int(row["n_patients"])
                for row in included
                if row.get("n_patients") is not None
            ),
            "events": all_events if all_event_counts_recorded else None,
            "replicated_events": (
                total_events if all_events_recorded else None
            ),
            "replicated_patients": (
                replicated_patients
                if all_replicated_patient_counts_recorded
                else None
            ),
        },
    }


def run_hierarchical_release_cox(
    *,
    scan_id: str,
    releases: Sequence[dict[str, Any]],
    input_path: Path,
    output_path: Path,
    script_path: Path | None = None,
    min_patients: int = 20,
    min_events: int = 10,
    min_censored: int = 5,
    timeout_seconds: int = 240,
) -> dict[str, Any]:
    """Run the isolated release-level IQR-scaled Cox implementation."""

    if script_path is None:
        script_path = (
            Path(__file__).resolve().parents[1]
            / "scripts"
            / "hierarchical_pancancer_cox.R"
        )
    input_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "scan_id": scan_id,
        "min_patients": min_patients,
        "min_events": min_events,
        "min_censored": min_censored,
        "releases": list(releases),
        "output_path": str(output_path),
    }
    input_path.write_text(
        json.dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )
    completed = subprocess.run(
        ["Rscript", str(script_path), str(input_path)],
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"Hierarchical pan-cancer Rscript failed: "
            f"{completed.stderr or completed.stdout}"
        )
    return json.loads(output_path.read_text(encoding="utf-8"))


def _synthesize_core(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    by_cancer: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_cancer[row["cancer_id"]].append(row)

    cancer_effects: list[dict[str, Any]] = []
    for cancer_id in sorted(by_cancer):
        studies = sorted(by_cancer[cancer_id], key=_effect_sort_key)
        cancer_effects.append(_pool_within_cancer(cancer_id, studies))

    completed_cancers = [
        row
        for row in cancer_effects
        if row.get("status") == "completed"
        and int(row.get("n_studies") or 0) >= 2
        and _finite(row.get("log_hr")) is not None
        and (_finite(row.get("standard_error")) or 0) > 0
    ]
    if len(completed_cancers) < 2:
        global_effect: dict[str, Any] = {
            "available": False,
            "reason": (
                "At least two cancer-level effects, each replicated in two "
                "independent study clusters, are required for the global "
                "pan-cancer synthesis. Single-study cancer estimates remain "
                "descriptive."
            ),
            "cancers": len(completed_cancers),
            "replication_required": True,
        }
    else:
        global_effect = _meta(
            completed_cancers,
            log_hr_key="log_hr",
            standard_error_key="standard_error",
        )
        global_effect["cancers"] = len(completed_cancers)
        global_effect["studies"] = sum(
            int(row.get("n_studies") or 0) for row in completed_cancers
        )
        global_effect["level"] = "across_cancers"
        global_effect["unit"] = "cancer-level effects"
    return {"cancer_effects": cancer_effects, "global_effect": global_effect}


def _pool_within_cancer(
    cancer_id: str,
    studies: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    patients = _optional_sum(studies, "n_patients")
    events = _optional_sum(studies, "n_events")
    base = {
        "cancer_id": cancer_id,
        "status": "completed",
        "endpoint": studies[0].get("endpoint"),
        "time_origin": studies[0].get("time_origin"),
        "clinical_context": studies[0].get("clinical_context"),
        "model_family": studies[0].get("model_family"),
        "effect_scale": HIERARCHICAL_EFFECT_SCALE,
        "n_studies": len(studies),
        "n_patients": patients,
        "n_events": events,
        "study_ids": sorted(str(row["study_id"]) for row in studies),
        "release_ids": sorted(str(row["release_id"]) for row in studies),
    }
    if len(studies) == 1:
        study = studies[0]
        log_hr = float(study["log_hr"])
        standard_error = float(study["standard_error"])
        return {
            **base,
            "model": "single-study cancer estimate (no within-cancer pooling)",
            "log_hr": log_hr,
            "standard_error": standard_error,
            "hazard_ratio": math.exp(log_hr),
            "hr_conf_low": math.exp(log_hr - 1.96 * standard_error),
            "hr_conf_high": math.exp(log_hr + 1.96 * standard_error),
            "meta_analysis": {
                "available": False,
                "reason": (
                    "Only one independent study is available; within-cancer "
                    "heterogeneity and prediction intervals are not estimable."
                ),
                "studies": 1,
            },
            "heterogeneity": None,
            "prediction_interval": None,
            "propagation_standard_error": "study_standard_error",
        }

    meta = _meta(studies)
    random = meta["random_effect"]
    standard_error = _finite(random.get("standard_error"))
    propagation = "modified_HKSJ_standard_error"
    if standard_error is None or standard_error <= 0:
        standard_error = float(random["conventional_standard_error"])
        propagation = "conventional_random_effect_standard_error_fallback"
    return {
        **base,
        "model": meta["model"],
        "log_hr": random["log_hr"],
        "standard_error": standard_error,
        "hazard_ratio": random["hazard_ratio"],
        "hr_conf_low": random["hr_conf_low"],
        "hr_conf_high": random["hr_conf_high"],
        "meta_analysis": meta,
        "heterogeneity": meta["heterogeneity"],
        "prediction_interval": meta["prediction_interval"],
        "propagation_standard_error": propagation,
    }


def _meta(
    rows: Sequence[dict[str, Any]],
    *,
    log_hr_key: str = "log_hr",
    standard_error_key: str = "standard_error",
) -> dict[str, Any]:
    endpoint = str(rows[0].get("endpoint") or "OS")
    prepared = [
        {
            "status": "completed",
            "endpoint": endpoint,
            "common_scale_log_hr": row.get(log_hr_key),
            "common_scale_standard_error": row.get(standard_error_key),
        }
        for row in rows
    ]
    result = common_scale_meta_analysis_from_rows(
        prepared,
        effect_scale={
            "id": HIERARCHICAL_EFFECT_SCALE,
            "label": HIERARCHICAL_EFFECT_SCALE_LABEL,
        },
        modified_hksj=True,
    )
    if "cohorts" in result:
        result["units"] = result.pop("cohorts")
    return result


def _canonical_effect(row: dict[str, Any]) -> dict[str, Any]:
    log_hr, standard_error = _effect_pair(row)
    result = {
        key: value
        for key, value in row.items()
        if key != "_input_position"
    }
    result.update(
        {
            "release_id": _clean(row.get("release_id")),
            "study_id": _clean(row.get("study_id")),
            "study_cluster_id": _clean(
                row.get("study_cluster_id") or row.get("study_id")
            ),
            "cancer_id": _clean(row.get("cancer_id")),
            "endpoint": _normalized_category(row.get("endpoint")),
            "time_origin": _normalized_category(row.get("time_origin")),
            "clinical_context": _normalized_category(
                row.get("clinical_context")
            ),
            "model_family": _normalized_category(row.get("model_family")),
            "effect_scale": HIERARCHICAL_EFFECT_SCALE,
            "log_hr": log_hr,
            "standard_error": standard_error,
            "hazard_ratio": math.exp(float(log_hr)),
        }
    )
    return result


def _sensitivity_record(
    synthesis: dict[str, Any],
    omitted: dict[str, Any],
    *,
    omitted_kind: str,
) -> dict[str, Any]:
    global_effect = synthesis.get("global_effect") or {}
    random = global_effect.get("random_effect") or {}
    record = {
        "omitted_kind": omitted_kind,
        "omitted_cancer_id": omitted.get("cancer_id"),
        "available": bool(global_effect.get("available")),
        "reason": global_effect.get("reason"),
        "remaining_cancers": global_effect.get("cancers", 0),
        "remaining_studies": global_effect.get("studies", 0),
        "log_hr": random.get("log_hr"),
        "hazard_ratio": random.get("hazard_ratio"),
        "hr_conf_low": random.get("hr_conf_low"),
        "hr_conf_high": random.get("hr_conf_high"),
        "p_value": random.get("p_value"),
    }
    if omitted_kind == "study":
        record.update(
            {
                "omitted_release_id": omitted.get("release_id"),
                "omitted_study_id": omitted.get("study_id"),
            }
        )
    return record


def _classify_global_result(
    global_effect: dict[str, Any] | None,
    cancer_effects: Sequence[dict[str, Any]],
    leave_one_cancer_out: Sequence[dict[str, Any]],
    *,
    formal_support: bool,
    alpha: float,
) -> str:
    if not formal_support or not global_effect or not global_effect.get("available"):
        return "insufficient_support"
    random = global_effect.get("random_effect") or {}
    p_value = _finite(random.get("p_value"))
    if p_value is None or p_value > alpha:
        return "no_average_association"
    log_hr = _finite(random.get("log_hr"))
    if log_hr is None or log_hr == 0:
        return "no_average_association"

    direction = 1 if log_hr > 0 else -1
    completed = [
        row for row in cancer_effects if _finite(row.get("log_hr")) is not None
    ]
    concordant = sum(
        (1 if float(row["log_hr"]) > 0 else -1) == direction
        for row in completed
        if float(row["log_hr"]) != 0
    )
    direction_fraction = concordant / len(completed) if completed else 0.0
    stable_loo = all(
        not row.get("available")
        or row.get("log_hr") is None
        or ((float(row["log_hr"]) > 0) == (direction > 0))
        for row in leave_one_cancer_out
    )
    prediction = global_effect.get("prediction_interval") or {}
    prediction_low = _finite(prediction.get("log_hr_low"))
    prediction_high = _finite(prediction.get("log_hr_high"))
    prediction_excludes_zero = bool(
        prediction_low is not None
        and prediction_high is not None
        and (prediction_low > 0 or prediction_high < 0)
    )
    i_squared = _finite(
        (global_effect.get("heterogeneity") or {}).get("i_squared")
    )
    if prediction_excludes_zero and direction_fraction >= 0.8 and stable_loo:
        return "broadly_consistent"
    if not prediction_excludes_zero or (i_squared is not None and i_squared >= 50):
        return "heterogeneous_or_context_dependent"
    return "average_pan_cancer_association"


def _effect_pair(row: dict[str, Any]) -> tuple[float | None, float | None]:
    log_hr = _finite(
        row.get("iqr_log_hr")
        if row.get("iqr_log_hr") is not None
        else row.get("log_hr")
    )
    standard_error = _finite(
        row.get("iqr_standard_error")
        if row.get("iqr_standard_error") is not None
        else row.get("standard_error")
    )
    return log_hr, standard_error


def _effect_scale(row: dict[str, Any]) -> str | None:
    value = row.get("effect_scale")
    if isinstance(value, dict):
        value = value.get("id") or value.get("scale")
    normalized = _normalized_category(value)
    aliases = {
        "within_study_iqr": HIERARCHICAL_EFFECT_SCALE,
        "per_1_within_study_iqr": HIERARCHICAL_EFFECT_SCALE,
        "per +1 within-study iqr": HIERARCHICAL_EFFECT_SCALE,
        "hr per +1 within-study expression iqr": HIERARCHICAL_EFFECT_SCALE,
    }
    return aliases.get(normalized, normalized or None)


def _effect_sort_key(row: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(row.get("cancer_id") or ""),
        str(row.get("study_id") or ""),
        str(row.get("release_id") or ""),
    )


def _optional_sum(rows: Iterable[dict[str, Any]], field: str) -> int | None:
    values = [row.get(field) for row in rows]
    if any(value is None for value in values):
        return None
    try:
        return sum(int(value) for value in values)
    except (TypeError, ValueError):
        return None


def _exclusion_record(row: dict[str, Any], reason: str) -> dict[str, Any]:
    return {
        "release_id": row.get("release_id"),
        "study_id": row.get("study_id"),
        "cancer_id": row.get("cancer_id"),
        "status": row.get("status"),
        "reason": reason,
    }


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _normalized_category(value: Any) -> str:
    return " ".join(_clean(value).casefold().split())


def _finite(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None
