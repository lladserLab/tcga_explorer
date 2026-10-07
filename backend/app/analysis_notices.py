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
    panel_models = list(metrics.get("signature_panel_cox_models") or [])
    structured_model_warning_messages = {
        " ".join(str(message).split())
        for model in (
            continuous_models
            + cox_models
            + interaction_models
            + panel_models
        )
        for message in (
            list(model.get("warnings") or [])
            + [
                term_message
                for term in model.get("marker_terms") or []
                for term_message in term.get("warnings") or []
            ]
        )
        if str(message).strip()
    }
    requested_adjustment = (
        (metrics.get("clinical_adjustment") or {}).get("status") == "requested"
    )
    selected_adjusted_model, selected_adjusted_family = _selected_adjusted_model(
        continuous_models,
        cox_models,
        interaction_models,
        panel_models,
        requested_adjustment=requested_adjustment,
    )
    primary_model, primary_family = _primary_result_model(
        metrics=metrics,
        continuous_models=continuous_models,
        cox_models=cox_models,
        interaction_models=interaction_models,
        panel_models=panel_models,
        selected_adjusted_model=selected_adjusted_model,
        selected_adjusted_family=selected_adjusted_family,
        requested_adjustment=requested_adjustment,
    )

    notices: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str | None, str]] = set()

    def append_notice(
        *,
        category: str,
        severity: str,
        scope: str,
        priority: str,
        code: str,
        message: str,
        model: str | None = None,
        model_label: str | None = None,
        selected_model_notice: bool = False,
    ) -> None:
        normalized_message = " ".join(message.split())
        key = (category, normalized_message, model, scope)
        if not normalized_message or key in seen:
            return
        seen.add(key)
        notices.append(
            {
                "category": category,
                "severity": severity,
                "scope": scope,
                "priority": priority,
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
            scope="context",
            priority="low",
            code="zscore_run_specific_standardization",
            message=ZSCORE_TRANSPORTABILITY_MESSAGE,
        )

    endpoint = str(metrics.get("endpoint") or "").upper()
    if endpoint in COMPETING_RISK_ENDPOINTS:
        append_notice(
            category="method",
            severity="info",
            scope="context",
            priority="low",
            code="competing_risk_estimand_context",
            message=competing_risk_message(endpoint),
        )

    model_warning_count = 0
    for family, models in (
        ("continuous", continuous_models),
        ("cox", cox_models),
        ("interaction", interaction_models),
        ("signature_panel", panel_models),
    ):
        for model in models:
            model_id = model.get("model")
            is_primary = (
                primary_model is not None
                and model_id == primary_model.get("model")
                and family == primary_family
            )
            is_requested_adjusted = (
                selected_adjusted_model is not None
                and model_id == selected_adjusted_model.get("model")
                and family == selected_adjusted_family
            )
            scope = (
                "primary"
                if is_primary
                else "requested_adjustment"
                if is_requested_adjusted
                else "auxiliary"
            )
            selected_notice = is_requested_adjusted
            information = model.get("information_diagnostics") or {}
            information_status = str(information.get("status") or "")
            if information_status in {"caution", "severe"}:
                events_per_parameter = information.get("events_per_parameter")
                threshold = (
                    information.get("severe_threshold")
                    if information_status == "severe"
                    else information.get("caution_threshold")
                )
                append_notice(
                    category="model",
                    severity="caution",
                    scope=scope,
                    priority=(
                        "high"
                        if is_primary and information_status == "severe"
                        else "medium"
                        if is_primary or is_requested_adjusted
                        else "low"
                    ),
                    code=(
                        "severe_low_information"
                        if information_status == "severe"
                        else "low_information"
                    ),
                    message=(
                        f"{events_per_parameter:.2f} events per fitted parameter "
                        f"is below the prespecified threshold of {threshold}."
                        if isinstance(events_per_parameter, (int, float))
                        and isinstance(threshold, (int, float))
                        else "The model has low events per fitted parameter."
                    ),
                    model=model_id,
                    model_label=model.get("label"),
                    selected_model_notice=selected_notice,
                )
            if information.get("standard_fit_instability"):
                append_notice(
                    category="model",
                    severity="error" if is_primary else "caution",
                    scope=scope,
                    priority="high" if is_primary else "medium",
                    code="standard_fit_instability",
                    message=(
                        "The standard Cox fit reported convergence, "
                        "singularity or non-finite coefficient instability."
                    ),
                    model=model_id,
                    model_label=model.get("label"),
                    selected_model_notice=selected_notice,
                )
            if _firth_failed(model.get("penalized_sensitivity")):
                append_notice(
                    category="model",
                    severity="caution",
                    scope=scope,
                    priority=(
                        "medium"
                        if is_primary or is_requested_adjusted
                        else "low"
                    ),
                    code="firth_sensitivity_failed",
                    message=(
                        "The prespecified Firth penalized sensitivity did "
                        "not produce an evaluable estimate."
                    ),
                    model=model_id,
                    model_label=model.get("label"),
                    selected_model_notice=selected_notice,
                )
            global_ph = _number(model.get("ph_global_p_value"))
            if global_ph is not None and global_ph < 0.05:
                append_notice(
                    category="model",
                    severity="caution",
                    scope=scope,
                    priority=(
                        "medium"
                        if is_primary or is_requested_adjusted
                        else "low"
                    ),
                    code="global_ph_diagnostic",
                    message=(
                        "The global proportional-hazards diagnostic is "
                        f"below 0.05 (p={global_ph:.3g})."
                    ),
                    model=model_id,
                    model_label=model.get("label"),
                    selected_model_notice=selected_notice,
                )

            term_messages: set[str] = set()
            for term in model.get("marker_terms") or []:
                term_label = str(term.get("signature") or term.get("term") or "")
                term_ph = _number(term.get("ph_p_value"))
                if term_ph is not None and term_ph < 0.05:
                    message = (
                        f"{term_label}: the signature-specific "
                        "proportional-hazards diagnostic is below 0.05 "
                        f"(p={term_ph:.3g})."
                    )
                    term_messages.add(message)
                    append_notice(
                        category="model",
                        severity="caution",
                        scope=scope,
                        priority=(
                            "medium"
                            if is_primary or is_requested_adjusted
                            else "low"
                        ),
                        code="marker_ph_diagnostic",
                        message=message,
                        model=model_id,
                        model_label=model.get("label"),
                        selected_model_notice=selected_notice,
                    )
                if _firth_failed(term.get("penalized_sensitivity")):
                    message = (
                        f"{term_label}: the prespecified Firth penalized "
                        "sensitivity did not produce an evaluable estimate."
                    )
                    term_messages.add(message)
                    append_notice(
                        category="model",
                        severity="caution",
                        scope=scope,
                        priority=(
                            "medium"
                            if is_primary or is_requested_adjusted
                            else "low"
                        ),
                        code="firth_sensitivity_failed",
                        message=message,
                        model=model_id,
                        model_label=model.get("label"),
                        selected_model_notice=selected_notice,
                    )
                for message in term.get("warnings") or []:
                    term_messages.add(str(message))

            structured_messages = {
                notice["message"]
                for notice in notices
                if notice.get("model") == model_id
            }
            structured_codes = {
                notice["code"]
                for notice in notices
                if notice.get("model") == model_id
            }
            for message in model.get("warnings") or []:
                model_warning_count += 1
                normalized_message = " ".join(str(message).split())
                if (
                    normalized_message in structured_messages
                    or normalized_message in term_messages
                ):
                    continue
                lowered_message = normalized_message.lower()
                if (
                    (
                        {"low_information", "severe_low_information"}
                        & structured_codes
                    )
                    and "low-information cox model" in lowered_message
                ):
                    continue
                if (
                    "global_ph_diagnostic" in structured_codes
                    and "global proportional-hazards" in lowered_message
                ):
                    continue
                append_notice(
                    category="model",
                    severity="caution",
                    scope=scope,
                    priority=(
                        "medium"
                        if is_primary or is_requested_adjusted
                        else "low"
                    ),
                    code="model_diagnostic_caution",
                    message=normalized_message,
                    model=model_id,
                    model_label=model.get("label"),
                    selected_model_notice=selected_notice,
                )

    for message in legacy_warnings:
        normalized_message = " ".join(message.split())
        if normalized_message in structured_model_warning_messages:
            continue
        normalized = message.lower()
        if normalized.startswith("cox model warning:"):
            if model_warning_count == 0:
                append_notice(
                    category="model",
                    severity="caution",
                    scope="auxiliary",
                    priority="low",
                    code="model_diagnostic_caution",
                    message=message.removeprefix("Cox model warning:").strip(),
                )
            continue
        if any(marker in normalized for marker in COHORT_MESSAGE_MARKERS):
            append_notice(
                category="cohort",
                severity="info",
                scope="context",
                priority="low",
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
                scope="context",
                priority="low",
                code=code,
                message=message,
            )

    if primary_model is None and (
        continuous_models
        or cox_models
        or interaction_models
        or panel_models
    ):
        if panel_models:
            expected_primary = [
                model
                for model in panel_models
                if model.get("model") == "panel_joint_unadjusted"
            ]
        elif metrics.get("combined_signature"):
            expected_primary = interaction_models
        else:
            expected_primary = [
                model
                for model in continuous_models
                if model.get("model") == "continuous_univariable"
            ] or [
                model
                for model in cox_models
                if model.get("model") == "univariable"
            ]
        reasons = _unique(
            str(model.get("reason")).strip()
            for model in expected_primary
            if model.get("reason")
        )
        message = (
            "The prespecified primary model was not evaluable; no "
            "decision-facing effect estimate is available."
        )
        if reasons:
            message = f"{message} {' '.join(reasons[:2])}"
        append_notice(
            category="availability",
            severity="error",
            scope="primary",
            priority="high",
            code="primary_model_not_evaluable",
            message=message,
        )

    if selected_adjusted_model is None and requested_adjustment:
        adjusted_model_ids = (
            CONTINUOUS_USER_ADJUSTED_MODEL_PREFERENCE
            + USER_ADJUSTED_MODEL_PREFERENCE
            + INTERACTION_USER_ADJUSTED_MODEL_PREFERENCE
            + ("panel_joint_adjusted",)
        )
        adjusted_models = [
            model
            for model in (
                continuous_models
                + cox_models
                + interaction_models
                + panel_models
            )
            if model.get("model") in adjusted_model_ids
        ]
        reasons = _unique(
            str(model.get("reason")).strip()
            for model in adjusted_models
            if model.get("reason")
        )
        message = (
            "The user-requested clinical-adjusted Cox model was not evaluable. "
            "The unadjusted primary estimate remains available when shown."
        )
        if reasons:
            message = f"{message} {' '.join(reasons[:2])}"
        append_notice(
            category="availability",
            severity="not_evaluable",
            scope="requested_adjustment",
            priority="medium",
            code="adjusted_model_not_evaluable",
            message=message,
        )
    elif selected_adjusted_model is None:
        automatic_adjusted_ids = (
            CONTINUOUS_ADJUSTED_MODEL_PREFERENCE
            + ADJUSTED_MODEL_PREFERENCE
            + INTERACTION_ADJUSTED_MODEL_PREFERENCE
        )
        automatic_adjusted = [
            model
            for model in (
                continuous_models
                + cox_models
                + interaction_models
            )
            if model.get("model") in automatic_adjusted_ids
        ]
        completed_automatic_adjusted = [
            model
            for model in automatic_adjusted
            if model.get("status") == "completed"
        ]
        if automatic_adjusted and not completed_automatic_adjusted:
            reasons = _unique(
                str(model.get("reason")).strip()
                for model in automatic_adjusted
                if model.get("reason")
            )
            message = (
                "The automatic clinical-adjusted sensitivity model was not "
                "evaluable. This does not invalidate the unadjusted primary "
                "estimate."
            )
            if reasons:
                message = f"{message} {' '.join(reasons[:2])}"
            append_notice(
                category="availability",
                severity="not_evaluable",
                scope="auxiliary",
                priority="low",
                code="automatic_adjusted_model_not_evaluable",
                message=message,
            )

    selected_adjusted_cautions = [
        notice
        for notice in notices
        if notice["category"] == "model"
        and notice["selected_model"]
    ]
    selected_adjusted_status = (
        "not_requested"
        if not requested_adjustment
        else "not_evaluable"
        if selected_adjusted_model is None
        else "caution"
        if selected_adjusted_cautions
        else "clean"
    )
    primary_cautions = [
        notice
        for notice in notices
        if notice["category"] == "model"
        and notice["scope"] == "primary"
        and notice["priority"] in {"high", "medium"}
    ]
    primary_status = (
        "not_evaluable"
        if primary_model is None
        else "caution"
        if primary_cautions
        else "clean"
    )
    counts = Counter(notice["severity"] for notice in notices)
    category_counts = Counter(notice["category"] for notice in notices)
    diagnostics = {
        "primary_result_model": (
            primary_model.get("model") if primary_model else None
        ),
        "primary_result_model_label": (
            primary_model.get("label") if primary_model else None
        ),
        "primary_result_model_family": primary_family,
        "primary_result_status": primary_status,
        "selected_adjusted_model": (
            selected_adjusted_model.get("model")
            if selected_adjusted_model
            else None
        ),
        "selected_adjusted_model_label": (
            selected_adjusted_model.get("label")
            if selected_adjusted_model
            else None
        ),
        "selected_adjusted_model_family": selected_adjusted_family,
        "selected_adjusted_status": selected_adjusted_status,
        "selected_model_caution_count": len(
            selected_adjusted_cautions
        ),
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
        str(signature.get("signature_method") or "")
        for signature in request_payload.get("signatures") or []
    )
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
    panel = metrics.get("signature_panel") or {}
    methods.extend(
        str(item.get("method") or item.get("signature_method") or "")
        for item in panel.get("signatures") or []
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
    panel_models: list[dict[str, Any]],
    *,
    requested_adjustment: bool = False,
) -> tuple[dict[str, Any] | None, str | None]:
    if panel_models and requested_adjustment:
        model = _completed_model(
            panel_models,
            "panel_joint_adjusted",
        )
        if model is not None:
            return model, "signature_panel"
        return None, None
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
    return None, None


def _primary_result_model(
    *,
    metrics: dict[str, Any],
    continuous_models: list[dict[str, Any]],
    cox_models: list[dict[str, Any]],
    interaction_models: list[dict[str, Any]],
    panel_models: list[dict[str, Any]],
    selected_adjusted_model: dict[str, Any] | None,
    selected_adjusted_family: str | None,
    requested_adjustment: bool,
) -> tuple[dict[str, Any] | None, str | None]:
    if panel_models:
        if (
            requested_adjustment
            and selected_adjusted_model is not None
            and selected_adjusted_family == "signature_panel"
        ):
            return selected_adjusted_model, "signature_panel"
        model = _completed_model(
            panel_models,
            "panel_joint_unadjusted",
        )
        return model, "signature_panel" if model else None

    if metrics.get("combined_signature"):
        if (
            requested_adjustment
            and selected_adjusted_model is not None
            and selected_adjusted_family == "interaction"
        ):
            return selected_adjusted_model, "interaction"
        model = _completed_model(interaction_models, "signature_interaction")
        return model, "interaction" if model else None

    if (
        requested_adjustment
        and selected_adjusted_model is not None
        and selected_adjusted_family == "continuous"
    ):
        return selected_adjusted_model, "continuous"
    model = _completed_model(
        continuous_models,
        "continuous_univariable",
    )
    if model is not None:
        return model, "continuous"
    if requested_adjustment and selected_adjusted_model is not None:
        return selected_adjusted_model, selected_adjusted_family
    model = _completed_model(cox_models, "univariable")
    return model, "cox" if model else None


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


def _firth_failed(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and value.get("status") == "failed"
    )


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number else None


def _unique(values) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))
