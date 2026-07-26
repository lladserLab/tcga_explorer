from __future__ import annotations

from collections import Counter
from typing import Any


ZSCORE_TRANSPORTABILITY_MESSAGE = (
    "Z-score signature genes are standardized among the expression-complete "
    "patients eligible in this run. Changing the endpoint or filters can change "
    "that reference population and the resulting score values; numerical z-score "
    "signature scores are not transportable across runs."
)

COMPETING_RISK_ENDPOINTS = {"DSS", "DFI", "PFI"}


def competing_risk_message(endpoint: str) -> str:
    normalized = str(endpoint or "").upper()
    label = {
        "DSS": "DSS",
        "DFI": "DFI",
        "PFI": "PFI",
    }.get(normalized, "This endpoint")
    return (
        f"{label} Kaplan-Meier and Cox outputs treat death before the event of "
        "interest as censoring and therefore estimate event-free survival and "
        "cause-specific hazards. The accompanying cumulative-incidence curves, "
        "Gray test and Fine-Gray models retain those deaths as competing events "
        "and estimate a different, subdistribution-based quantity."
    )


DSS_COMPETING_RISK_MESSAGE = competing_risk_message("DSS")


ADJUSTED_MODEL_PREFERENCE = (
    "stage_grade_adjusted",
    "stage_adjusted",
    "grade_adjusted",
)
USER_ADJUSTED_MODEL_PREFERENCE = ("user_adjusted",)
CONTINUOUS_ADJUSTED_MODEL_PREFERENCE = (
    "continuous_stage_grade_adjusted",
    "continuous_stage_adjusted",
    "continuous_grade_adjusted",
)
CONTINUOUS_USER_ADJUSTED_MODEL_PREFERENCE = ("continuous_user_adjusted",)
INTERACTION_ADJUSTED_MODEL_PREFERENCE = (
    "signature_interaction_stage_grade_adjusted",
    "signature_interaction_stage_adjusted",
    "signature_interaction_grade_adjusted",
)
INTERACTION_USER_ADJUSTED_MODEL_PREFERENCE = (
    "signature_interaction_user_adjusted",
)

COHORT_MESSAGE_MARKERS = (
    "samples were excluded",
    "sample was excluded",
    "extra sample records",
    "one sample per patient",
    "retained patient-level",
    "eligible barcodes",
    "biospecimen priority",
    "normal/control/unknown sample type",
    "administratively censored",
    "follow-up time exceeding",
    "sample type",
)
METHOD_MESSAGE_MARKERS = (
    "primary pan-cancer effect",
    "kaplan-meier cutpoints are not used",
    "endpoint mode can select",
    "expression z-scored",
    "exploratory research analysis",
    "resolved to current symbol",
    "resolved to",
    "duplicate gene",
)


def build_analysis_diagnostics(
    warnings: list[str] | None,
    metrics: dict[str, Any] | None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Return decision-support notices without changing the legacy warnings field."""

    metrics = metrics or {}
    legacy_warnings = [str(item) for item in (warnings or []) if str(item).strip()]
    cox_models = list(metrics.get("cox_models") or [])
    continuous_models = list(
        (metrics.get("continuous_analysis") or {}).get("linear_models") or []
    )
    interaction_models = list(metrics.get("signature_interaction_cox_models") or [])
    requested_adjustment = (
        (metrics.get("clinical_adjustment") or {}).get("status") == "requested"
    )
    selected_model, model_family = _selected_adjusted_model(
        continuous_models,
        cox_models,
        interaction_models,
        requested_adjustment=requested_adjustment,
    )

    notices: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str | None]] = set()

    def append_notice(
        *,
        category: str,
        severity: str,
        code: str,
        message: str,
        model: str | None = None,
        model_label: str | None = None,
        selected_model_notice: bool = False,
    ) -> None:
        normalized_message = " ".join(message.split())
        key = (category, normalized_message, model)
        if not normalized_message or key in seen:
            return
        seen.add(key)
        notices.append(
            {
                "category": category,
                "severity": severity,
                "code": code,
                "message": normalized_message,
                "model": model,
                "model_label": model_label,
                "selected_model": selected_model_notice,
            }
        )

    if uses_zscore_signature(metrics=metrics):
        append_notice(
            category="method",
            severity="info",
            code="zscore_run_specific_standardization",
            message=ZSCORE_TRANSPORTABILITY_MESSAGE,
        )

    endpoint = str(metrics.get("endpoint") or "").upper()
    if endpoint in COMPETING_RISK_ENDPOINTS:
        append_notice(
            category="method",
            severity="info",
            code="competing_risk_estimand_context",
            message=competing_risk_message(endpoint),
        )

    model_warning_count = 0
    for family, models in (
        ("continuous", continuous_models),
        ("cox", cox_models),
        ("interaction", interaction_models),
    ):
        for model in models:
            for message in model.get("warnings") or []:
                model_warning_count += 1
                append_notice(
                    category="model",
                    severity="caution",
                    code="model_diagnostic_caution",
                    message=str(message),
                    model=model.get("model"),
                    model_label=model.get("label"),
                    selected_model_notice=(
                        selected_model is not None
                        and model.get("model") == selected_model.get("model")
                        and family == model_family
                    ),
                )

    for message in legacy_warnings:
        normalized = message.lower()
        if normalized.startswith("cox model warning:"):
            if model_warning_count == 0:
                append_notice(
                    category="model",
                    severity="caution",
                    code="model_diagnostic_caution",
                    message=message.removeprefix("Cox model warning:").strip(),
                )
            continue
        if any(marker in normalized for marker in COHORT_MESSAGE_MARKERS):
            append_notice(
                category="cohort",
                severity="info",
                code="cohort_provenance",
                message=message,
            )
        else:
            code = (
                "method_context"
                if any(marker in normalized for marker in METHOD_MESSAGE_MARKERS)
                else "analysis_context"
            )
            append_notice(
                category="method",
                severity="info",
                code=code,
                message=message,
            )

    if selected_model is None:
        adjusted_model_ids = (
            CONTINUOUS_USER_ADJUSTED_MODEL_PREFERENCE
            + USER_ADJUSTED_MODEL_PREFERENCE
            + INTERACTION_USER_ADJUSTED_MODEL_PREFERENCE
            if requested_adjustment
            else CONTINUOUS_ADJUSTED_MODEL_PREFERENCE
            + ADJUSTED_MODEL_PREFERENCE
            + INTERACTION_ADJUSTED_MODEL_PREFERENCE
        )
        adjusted_models = [
            model
            for model in continuous_models + cox_models + interaction_models
            if model.get("model") in adjusted_model_ids
        ]
        reasons = _unique(
            str(model.get("reason")).strip()
            for model in adjusted_models
            if model.get("reason")
        )
        message = (
            "The user-requested clinical-adjusted Cox model was not evaluable for this analysis."
            if requested_adjustment
            else "No clinical-adjusted Cox model was evaluable for this analysis."
        )
        if reasons:
            message = f"{message} {' '.join(reasons[:2])}"
        append_notice(
            category="availability",
            severity="not_evaluable",
            code="adjusted_model_not_evaluable",
            message=message,
        )

    selected_cautions = [
        notice
        for notice in notices
        if notice["category"] == "model" and notice["selected_model"]
    ]
    selected_status = (
        "not_evaluable"
        if selected_model is None
        else "caution"
        if selected_cautions
        else "clean"
    )
    counts = Counter(notice["severity"] for notice in notices)
    category_counts = Counter(notice["category"] for notice in notices)
    diagnostics = {
        "selected_adjusted_model": selected_model.get("model") if selected_model else None,
        "selected_adjusted_model_label": selected_model.get("label") if selected_model else None,
        "selected_adjusted_model_family": model_family,
        "selected_adjusted_status": selected_status,
        "selected_model_caution_count": len(selected_cautions),
        "model_caution_count": counts["caution"],
        "information_count": counts["info"],
        "not_evaluable_count": counts["not_evaluable"],
        "cohort_information_count": category_counts["cohort"],
        "method_information_count": category_counts["method"],
        "legacy_warning_count": len(legacy_warnings),
    }
    return notices, diagnostics


def signature_methods(
    *,
    request_payload: dict[str, Any] | None = None,
    metrics: dict[str, Any] | None = None,
) -> list[str]:
    """Return signature score methods from either request or result payloads."""

    methods: list[str] = []
    request_payload = request_payload or {}
    metrics = metrics or {}

    signature_a = request_payload.get("signature_a") or {}
    signature_b = request_payload.get("signature_b") or {}
    if signature_a or signature_b:
        methods.extend(
            str(signature.get("signature_method") or "")
            for signature in (signature_a, signature_b)
        )
    else:
        methods.append(str(request_payload.get("signature_method") or ""))
    methods.extend(
        str(method or "")
        for method in request_payload.get("scoring_methods") or []
    )

    signature = metrics.get("signature") or {}
    methods.append(str(signature.get("method") or ""))
    methods.extend(
        str(item.get("method") or item.get("signature_method") or "")
        for item in signature.get("signatures") or []
    )

    combined = metrics.get("combined_signature") or {}
    methods.extend(
        str(item.get("method") or item.get("signature_method") or "")
        for item in (
            combined.get("signature_a") or {},
            combined.get("signature_b") or {},
        )
    )

    return list(
        dict.fromkeys(
            method.strip().lower()
            for method in methods
            if method and method.strip().lower() not in {"single", "combined"}
        )
    )


def uses_zscore_signature(
    *,
    request_payload: dict[str, Any] | None = None,
    metrics: dict[str, Any] | None = None,
) -> bool:
    return "zscore" in signature_methods(
        request_payload=request_payload,
        metrics=metrics,
    )


def _selected_adjusted_model(
    continuous_models: list[dict[str, Any]],
    cox_models: list[dict[str, Any]],
    interaction_models: list[dict[str, Any]],
    *,
    requested_adjustment: bool = False,
) -> tuple[dict[str, Any] | None, str | None]:
    if requested_adjustment:
        for model_id in CONTINUOUS_USER_ADJUSTED_MODEL_PREFERENCE:
            model = _completed_model(continuous_models, model_id)
            if model is not None:
                return model, "continuous"
        for model_id in USER_ADJUSTED_MODEL_PREFERENCE:
            model = _completed_model(cox_models, model_id)
            if model is not None:
                return model, "cox"
        for model_id in INTERACTION_USER_ADJUSTED_MODEL_PREFERENCE:
            model = _completed_model(interaction_models, model_id)
            if model is not None:
                return model, "interaction"
        return None, None
    for model_id in CONTINUOUS_ADJUSTED_MODEL_PREFERENCE:
        model = _completed_model(continuous_models, model_id)
        if model is not None:
            return model, "continuous"
    for model_id in ADJUSTED_MODEL_PREFERENCE:
        model = _completed_model(cox_models, model_id)
        if model is not None:
            return model, "cox"
    for model_id in INTERACTION_ADJUSTED_MODEL_PREFERENCE:
        model = _completed_model(interaction_models, model_id)
        if model is not None:
            return model, "interaction"
    return None, None


def _completed_model(
    models: list[dict[str, Any]],
    model_id: str,
) -> dict[str, Any] | None:
    return next(
        (
            model
            for model in models
            if model.get("model") == model_id and model.get("status") == "completed"
        ),
        None,
    )


def _unique(values) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))
