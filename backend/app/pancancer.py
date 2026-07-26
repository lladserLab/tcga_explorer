from __future__ import annotations

import math
from collections import Counter, defaultdict
from typing import Any


PANCANCER_ADJUSTED_MODEL_PREFERENCE = (
    "stage_grade_adjusted",
    "stage_adjusted",
    "grade_adjusted",
)


def chi2_sf(q: float, df: int) -> float | None:
    """Upper-tail p-value for the chi-squared distribution (Cochran Q heterogeneity test).

    Uses exact formulas for df=1 and df=2; Wilson-Hilferty normal approximation for df>=3
    (error < 0.2% for df >= 10, suitable for pan-cancer Q tests with many cohorts).
    """
    if not math.isfinite(q) or df <= 0 or q < 0.0:
        return None
    if q == 0.0:
        return 1.0
    if df == 1:
        return float(math.erfc(math.sqrt(q / 2.0)))
    if df == 2:
        return float(math.exp(-q / 2.0))
    h = 1.0 - 2.0 / (9.0 * df)
    s = math.sqrt(2.0 / (9.0 * df))
    z = ((q / df) ** (1.0 / 3.0) - h) / s
    return float(math.erfc(z / math.sqrt(2.0)) / 2.0)


def normal_two_sided_p(z_value: float) -> float | None:
    if not math.isfinite(z_value):
        return None
    return math.erfc(abs(z_value) / math.sqrt(2.0))


def adjust_p_values_bh(p_values: list[float | None]) -> list[float | None]:
    indexed = [
        (index, float(value))
        for index, value in enumerate(p_values)
        if value is not None and math.isfinite(float(value))
    ]
    if not indexed:
        return [None for _ in p_values]

    indexed.sort(key=lambda item: item[1])
    adjusted: dict[int, float] = {}
    running_min = 1.0
    total = len(indexed)
    for rank_index in range(total - 1, -1, -1):
        original_index, p_value = indexed[rank_index]
        rank = rank_index + 1
        running_min = min(running_min, p_value * total / rank)
        adjusted[original_index] = min(running_min, 1.0)
    return [adjusted.get(index) for index in range(len(p_values))]


def attach_preparation_metadata(
    rows: list[dict[str, Any]],
    prepared_cohorts: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Restore Python-side cohort preparation metadata after the R model fit."""

    prepared_by_cohort = {
        str(cohort.get("cohort")): cohort
        for cohort in prepared_cohorts
        if cohort.get("cohort")
    }
    for row in rows:
        prepared = prepared_by_cohort.get(str(row.get("cohort")))
        if not prepared:
            continue
        row["sample_selection"] = prepared.get("sample_selection")
        row["warnings"] = list(
            dict.fromkeys(
                _warning_list(prepared.get("warnings"))
                + _warning_list(row.get("warnings"))
            )
        )
    return rows


def attach_effect_scale_metadata(
    rows: list[dict[str, Any]],
    effect_scale: dict[str, Any],
    pooling_eligible: bool,
) -> list[dict[str, Any]]:
    synthesis = effect_scale.get("synthesis") or {}
    unit = synthesis.get("unit")
    for row in rows:
        row["common_scale_unit"] = unit
        row["common_scale_eligible"] = bool(pooling_eligible)
        for model in row.get("cox_models") or []:
            model["common_scale_unit"] = unit
            model["common_scale_eligible"] = bool(pooling_eligible)
    return rows


def _warning_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value]
    return [str(value)]


def add_effect_labels(rows: list[dict[str, Any]], fdr_threshold: float) -> list[dict[str, Any]]:
    for row in rows:
        hazard_ratio = _finite(row.get("hazard_ratio"))
        fdr = _finite(row.get("fdr"))
        if hazard_ratio is None:
            row["direction"] = "not_evaluable"
            row["effect_category"] = "not_evaluable"
            row["significant"] = False
            continue

        direction = "harmful" if hazard_ratio > 1 else "protective" if hazard_ratio < 1 else "neutral"
        significant = fdr is not None and fdr <= fdr_threshold
        row["direction"] = direction
        row["effect_category"] = direction if significant else "neutral"
        row["significant"] = significant
    return rows


def add_clinical_sensitivity(
    rows: list[dict[str, Any]],
    fdr_threshold: float,
    *,
    effect_scale: dict[str, Any] | None = None,
    pooling_eligible: bool = True,
    pooling_reason: str | None = None,
) -> dict[str, Any]:
    """Annotate ordinal-adjusted Cox models without replacing primary effects."""

    for model_id in PANCANCER_ADJUSTED_MODEL_PREFERENCE:
        models = [
            _model_by_id(row.get("cox_models"), model_id)
            for row in rows
        ]
        fdr_values = adjust_p_values_bh(
            [
                model.get("p_value")
                if model and model.get("status") == "completed"
                else None
                for model in models
            ]
        )
        for model, fdr in zip(models, fdr_values):
            if not model:
                continue
            model["fdr"] = fdr
            _annotate_effect(model, fdr_threshold)

    selected_models: list[dict[str, Any] | None] = []
    for row in rows:
        selected = _selected_adjusted_model(row.get("cox_models"))
        selected_models.append(selected)
        row["selected_adjusted_model"] = selected.get("model") if selected else None
        row["selected_adjusted_model_label"] = selected.get("label") if selected else None
        row["adjusted_status"] = "completed" if selected else "not_evaluable"
        for source, target in (
            ("n_patients", "adjusted_n_patients"),
            ("n_events", "adjusted_n_events"),
            ("log_hr", "adjusted_log_hr"),
            ("standard_error", "adjusted_standard_error"),
            ("hazard_ratio", "adjusted_hazard_ratio"),
            ("hr_conf_low", "adjusted_hr_conf_low"),
            ("hr_conf_high", "adjusted_hr_conf_high"),
            ("p_value", "adjusted_p_value"),
            ("ph_p_value", "adjusted_ph_p_value"),
            ("ph_global_p_value", "adjusted_ph_global_p_value"),
            ("time_varying_effect", "adjusted_time_varying_effect"),
            ("common_scale_log_hr", "adjusted_common_scale_log_hr"),
            (
                "common_scale_standard_error",
                "adjusted_common_scale_standard_error",
            ),
            (
                "common_scale_hazard_ratio",
                "adjusted_common_scale_hazard_ratio",
            ),
            (
                "common_scale_hr_conf_low",
                "adjusted_common_scale_hr_conf_low",
            ),
            (
                "common_scale_hr_conf_high",
                "adjusted_common_scale_hr_conf_high",
            ),
            (
                "common_scale_p_value",
                "adjusted_common_scale_p_value",
            ),
        ):
            row[target] = selected.get(source) if selected else None
        row["adjusted_reason"] = (
            None
            if selected
            else _adjusted_unavailable_reason(row.get("cox_models"))
        )

    selected_fdr_values = adjust_p_values_bh(
        [
            model.get("p_value")
            if model and model.get("status") == "completed"
            else None
            for model in selected_models
        ]
    )
    for row, model, fdr in zip(rows, selected_models, selected_fdr_values):
        row["adjusted_fdr"] = fdr
        adjusted_hr = _finite(row.get("adjusted_hazard_ratio"))
        adjusted_direction = _direction(adjusted_hr)
        row["adjusted_direction"] = adjusted_direction
        row["adjusted_significant"] = bool(
            fdr is not None and fdr <= fdr_threshold
        )
        row["adjusted_effect_category"] = (
            adjusted_direction
            if row["adjusted_significant"]
            and adjusted_direction in {"harmful", "protective"}
            else "not_evaluable"
            if adjusted_direction == "not_evaluable"
            else "neutral"
        )
        row["clinical_sensitivity"] = _clinical_comparison_label(row)
        if model is not None:
            model["selected"] = True
            model["selected_fdr"] = fdr

    completed_rows = [
        row for row in rows if row.get("adjusted_status") == "completed"
    ]
    selected_model_counts = Counter(
        row.get("selected_adjusted_model") or "not_evaluable"
        for row in rows
    )
    comparison_counts = Counter(
        row.get("clinical_sensitivity") or "not_evaluable"
        for row in rows
    )
    by_model = {
        model_id: _model_family_summary(
            rows,
            model_id,
            fdr_threshold,
            effect_scale=effect_scale,
            pooling_eligible=pooling_eligible,
            pooling_reason=pooling_reason,
        )
        for model_id in PANCANCER_ADJUSTED_MODEL_PREFERENCE
    }
    selected_model_ids = {
        row.get("selected_adjusted_model")
        for row in completed_rows
        if row.get("selected_adjusted_model")
    }
    if not pooling_eligible:
        selected_meta = {
            "available": False,
            "reason": pooling_reason
            or "The requested score is not transportable on a common scale.",
            "comparability": "common_scale_unavailable",
            "effect_scale": effect_scale or {},
        }
    elif len(selected_model_ids) == 1:
        selected_meta = common_scale_meta_analysis_from_rows(
            [
                {
                    "status": "completed",
                    "endpoint": row.get("endpoint"),
                    "common_scale_log_hr": row.get(
                        "adjusted_common_scale_log_hr"
                    ),
                    "common_scale_standard_error": row.get(
                        "adjusted_common_scale_standard_error"
                    ),
                }
                for row in completed_rows
            ],
            effect_scale=effect_scale,
        )
        selected_meta["adjustment_model"] = next(iter(selected_model_ids))
        selected_meta["comparability"] = "single_adjustment_family"
    else:
        selected_meta = {
            "available": False,
            "reason": (
                "Selected sensitivity effects use mixed clinical-adjustment "
                "families; a pooled estimate is intentionally not reported."
            ),
            "model_families": sorted(selected_model_ids),
            "comparability": "mixed_adjustment_families",
        }

    return {
        "available": bool(completed_rows),
        "role": "sensitivity_analysis",
        "primary_estimand_unchanged": True,
        "covariate_encoding": "ordinal_stage_and_grade",
        "selection_hierarchy": list(PANCANCER_ADJUSTED_MODEL_PREFERENCE),
        "fdr_scope": "BH across selected cohort-level sensitivity tests",
        "summary": {
            "total_cohorts": len(rows),
            "evaluable": len(completed_rows),
            "not_evaluable": len(rows) - len(completed_rows),
            "fdr_significant": sum(
                bool(row.get("adjusted_significant")) for row in completed_rows
            ),
            "direction_concordant": sum(
                row.get("clinical_sensitivity")
                in {"retained", "attenuated", "emerged", "direction_consistent"}
                for row in completed_rows
            ),
            "direction_reversed": comparison_counts["reversed"],
            "selected_model_counts": dict(selected_model_counts),
            "comparison_counts": dict(comparison_counts),
        },
        "meta_analysis_by_model": by_model,
        "selected_model_meta_analysis": selected_meta,
        "notes": [
            (
                "Clinical sensitivity models use ordinal major stage and "
                "histologic grade when evaluable; missing covariates change "
                "the analyzed patient subset."
            ),
            (
                "Primary univariable effects remain the cross-cancer "
                "estimand. Adjusted effects are reported in parallel and "
                "mixed adjustment families are not pooled."
            ),
        ],
    }


def add_concordance_labels(rows: list[dict[str, Any]], index_cohort: str | None) -> dict[str, Any] | None:
    reference = None
    if index_cohort:
        reference = next(
            (
                row
                for row in rows
                if row.get("cohort") == index_cohort
                and row.get("status") == "completed"
                and row.get("direction") in {"harmful", "protective"}
            ),
            None,
        )
    reference_direction = reference.get("direction") if reference else None

    for row in rows:
        if row.get("status") != "completed" or row.get("direction") not in {"harmful", "protective"}:
            row["concordance"] = "not_evaluable"
            continue
        if not reference_direction:
            row["concordance"] = "reference_unavailable"
            continue
        if row.get("cohort") == index_cohort:
            row["concordance"] = "reference"
            continue
        same_direction = row["direction"] == reference_direction
        if same_direction and row.get("significant"):
            row["concordance"] = "same_direction_significant"
        elif same_direction:
            row["concordance"] = "same_direction_not_significant"
        elif row.get("significant"):
            row["concordance"] = "opposite_direction_significant"
        else:
            row["concordance"] = "opposite_direction_not_significant"

    if not reference:
        return None
    return {
        "cohort": reference.get("cohort"),
        "endpoint": reference.get("endpoint"),
        "direction": reference.get("direction"),
        "hazard_ratio": reference.get("hazard_ratio"),
        "p_value": reference.get("p_value"),
        "fdr": reference.get("fdr"),
    }


def meta_analysis_from_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return common_scale_meta_analysis_from_rows(rows)


def common_scale_meta_analysis_from_rows(
    rows: list[dict[str, Any]],
    *,
    log_hr_key: str = "common_scale_log_hr",
    standard_error_key: str = "common_scale_standard_error",
    effect_scale: dict[str, Any] | None = None,
) -> dict[str, Any]:
    effects = []
    endpoints: set[str] = set()
    for row in rows:
        log_hr = _finite(row.get(log_hr_key))
        se = _finite(row.get(standard_error_key))
        if row.get("status") == "completed" and log_hr is not None and se is not None and se > 0:
            effects.append((log_hr, se))
            endpoint = str(row.get("endpoint") or "").strip()
            if endpoint:
                endpoints.add(endpoint)

    if not effects:
        return {
            "available": False,
            "reason": (
                "No completed common-scale cohort-level Cox effects were "
                "available."
            ),
            "effect_scale": effect_scale or {},
        }
    if len(endpoints) > 1:
        return {
            "available": False,
            "reason": (
                "Completed cohort effects use mixed survival endpoints; a "
                "pooled estimate is intentionally not reported."
            ),
            "endpoints": sorted(endpoints),
            "comparability": "mixed_endpoints",
            "effect_scale": effect_scale or {},
        }
    if not endpoints:
        return {
            "available": False,
            "reason": (
                "The endpoint was not recorded for the completed common-scale "
                "effects, so comparability cannot be verified."
            ),
            "comparability": "endpoint_unavailable",
            "effect_scale": effect_scale or {},
        }
    if len(effects) < 2:
        return {
            "available": False,
            "reason": "At least two common-scale cohort effects are required.",
            "cohorts": len(effects),
            "effect_scale": effect_scale or {},
        }

    fixed = _weighted_meta(effects, tau_squared=0.0)
    weights = [1 / (se * se) for _, se in effects]
    fixed_log_hr = fixed["log_hr"]
    q_value = sum(weight * (log_hr - fixed_log_hr) ** 2 for (log_hr, _), weight in zip(effects, weights))
    df = max(len(effects) - 1, 0)
    tau_squared = _reml_tau_squared(effects)
    random = _hksj_random_effect(effects, tau_squared)
    i_squared = max(0.0, ((q_value - df) / q_value) * 100.0) if q_value > 0 and q_value > df else 0.0
    q_p_value = chi2_sf(q_value, df) if df >= 1 else None

    return {
        "available": True,
        "model": "REML random-effects with HKSJ inference",
        "tau_estimator": "restricted maximum likelihood",
        "inference": "Hartung-Knapp-Sidik-Jonkman",
        "cohorts": len(effects),
        "endpoint": next(iter(endpoints)) if len(endpoints) == 1 else None,
        "effect_scale": effect_scale or {},
        "fixed_effect": fixed,
        "random_effect": random,
        "prediction_interval": _prediction_interval(
            random,
            tau_squared,
            len(effects),
        ),
        "heterogeneity": {
            "q": q_value,
            "df": df,
            "q_p_value": q_p_value,
            "i_squared": i_squared,
            "tau_squared": tau_squared,
        },
    }


def summarize_pancancer_results(
    rows: list[dict[str, Any]],
    index_cohort: str | None,
    fdr_threshold: float,
) -> dict[str, Any]:
    status_counts = Counter(row.get("status", "unknown") for row in rows)
    effect_counts = Counter(row.get("effect_category", "not_evaluable") for row in rows)
    concordance_counts = Counter(row.get("concordance", "not_evaluable") for row in rows)
    completed = [row for row in rows if row.get("status") == "completed"]
    significant = [row for row in completed if row.get("significant")]

    by_primary_site: dict[str, Counter] = defaultdict(Counter)
    for row in completed:
        site = row.get("primary_site") or "Unknown"
        by_primary_site[site][row.get("effect_category", "neutral")] += 1

    primary_site_patterns = [
        {"primary_site": site, **dict(counts)}
        for site, counts in sorted(
            by_primary_site.items(),
            key=lambda item: sum(item[1].values()),
            reverse=True,
        )
    ]

    return {
        "total_cohorts": len(rows),
        "completed": len(completed),
        "failed_or_skipped": len(rows) - len(completed),
        "significant": len(significant),
        "fdr_threshold": fdr_threshold,
        "index_cohort": index_cohort,
        "status_counts": dict(status_counts),
        "effect_counts": dict(effect_counts),
        "concordance_counts": dict(concordance_counts),
        "primary_site_patterns": primary_site_patterns,
    }


def _weighted_meta(effects: list[tuple[float, float]], tau_squared: float) -> dict[str, float | None]:
    weights = [1 / ((se * se) + tau_squared) for _, se in effects]
    weight_sum = sum(weights)
    log_hr = sum(weight * effect[0] for weight, effect in zip(weights, effects)) / weight_sum
    se = math.sqrt(1 / weight_sum)
    z_value = log_hr / se if se else float("nan")
    p_value = normal_two_sided_p(z_value)
    return {
        "log_hr": log_hr,
        "standard_error": se,
        "hazard_ratio": math.exp(log_hr),
        "hr_conf_low": math.exp(log_hr - 1.96 * se),
        "hr_conf_high": math.exp(log_hr + 1.96 * se),
        "p_value": p_value,
    }


def _reml_tau_squared(effects: list[tuple[float, float]]) -> float:
    if len(effects) < 2:
        return 0.0
    effect_values = [effect for effect, _ in effects]
    mean_effect = sum(effect_values) / len(effect_values)
    sample_variance = sum(
        (effect - mean_effect) ** 2 for effect in effect_values
    ) / max(len(effect_values) - 1, 1)
    max_variance = max(se * se for _, se in effects)
    upper = max(1e-6, sample_variance * 10.0, max_variance * 10.0)
    best = 0.0
    for _ in range(8):
        best = _golden_section_minimize(
            lambda tau: _negative_reml_log_likelihood(effects, tau),
            0.0,
            upper,
        )
        if best < upper * 0.98:
            break
        upper *= 10.0
    if _negative_reml_log_likelihood(
        effects,
        0.0,
    ) <= _negative_reml_log_likelihood(effects, best):
        return 0.0
    return max(0.0, best)


def _negative_reml_log_likelihood(
    effects: list[tuple[float, float]],
    tau_squared: float,
) -> float:
    variances = [(se * se) + tau_squared for _, se in effects]
    if any(variance <= 0 or not math.isfinite(variance) for variance in variances):
        return float("inf")
    weights = [1.0 / variance for variance in variances]
    weight_sum = sum(weights)
    if weight_sum <= 0 or not math.isfinite(weight_sum):
        return float("inf")
    pooled = sum(
        weight * effect[0] for weight, effect in zip(weights, effects)
    ) / weight_sum
    residual = sum(
        weight * (effect[0] - pooled) ** 2
        for weight, effect in zip(weights, effects)
    )
    return 0.5 * (
        sum(math.log(variance) for variance in variances)
        + math.log(weight_sum)
        + residual
    )


def _golden_section_minimize(
    function,
    lower: float,
    upper: float,
    *,
    iterations: int = 160,
) -> float:
    ratio = (math.sqrt(5.0) - 1.0) / 2.0
    left = upper - ratio * (upper - lower)
    right = lower + ratio * (upper - lower)
    left_value = function(left)
    right_value = function(right)
    for _ in range(iterations):
        if left_value <= right_value:
            upper = right
            right = left
            right_value = left_value
            left = upper - ratio * (upper - lower)
            left_value = function(left)
        else:
            lower = left
            left = right
            left_value = right_value
            right = lower + ratio * (upper - lower)
            right_value = function(right)
    return (lower + upper) / 2.0


def _hksj_random_effect(
    effects: list[tuple[float, float]],
    tau_squared: float,
) -> dict[str, float | int | str | None]:
    weights = [1 / ((se * se) + tau_squared) for _, se in effects]
    weight_sum = sum(weights)
    log_hr = sum(
        weight * effect[0] for weight, effect in zip(weights, effects)
    ) / weight_sum
    degrees_of_freedom = len(effects) - 1
    hk_scale = sum(
        weight * (effect[0] - log_hr) ** 2
        for weight, effect in zip(weights, effects)
    ) / degrees_of_freedom
    variance = hk_scale / weight_sum
    standard_error = math.sqrt(max(variance, 0.0))
    conventional_standard_error = math.sqrt(1.0 / weight_sum)
    t_value = (
        log_hr / standard_error
        if standard_error > 0
        else math.copysign(float("inf"), log_hr)
        if log_hr != 0
        else 0.0
    )
    p_value = student_t_two_sided_p(t_value, degrees_of_freedom)
    critical = student_t_quantile(0.975, degrees_of_freedom)
    margin = critical * standard_error
    return {
        "log_hr": log_hr,
        "standard_error": standard_error,
        "conventional_standard_error": conventional_standard_error,
        "hksj_scale": hk_scale,
        "degrees_of_freedom": degrees_of_freedom,
        "test_statistic": t_value,
        "hazard_ratio": math.exp(log_hr),
        "hr_conf_low": math.exp(log_hr - margin),
        "hr_conf_high": math.exp(log_hr + margin),
        "p_value": p_value,
        "confidence_distribution": "Student t",
    }


def _prediction_interval(
    random_effect: dict[str, Any],
    tau_squared: float,
    cohort_count: int,
) -> dict[str, float | int | str] | None:
    if cohort_count < 3:
        return None
    degrees_of_freedom = cohort_count - 2
    critical = student_t_quantile(0.975, degrees_of_freedom)
    standard_error = float(random_effect["standard_error"])
    prediction_standard_error = math.sqrt(
        max(0.0, tau_squared + standard_error * standard_error)
    )
    margin = critical * prediction_standard_error
    log_hr = float(random_effect["log_hr"])
    return {
        "log_hr_low": log_hr - margin,
        "log_hr_high": log_hr + margin,
        "hazard_ratio_low": math.exp(log_hr - margin),
        "hazard_ratio_high": math.exp(log_hr + margin),
        "standard_error": prediction_standard_error,
        "degrees_of_freedom": degrees_of_freedom,
        "distribution": "Student t",
    }


def student_t_two_sided_p(
    t_value: float,
    degrees_of_freedom: int,
) -> float | None:
    if degrees_of_freedom <= 0 or math.isnan(t_value):
        return None
    if math.isinf(t_value):
        return 0.0
    x_value = degrees_of_freedom / (
        degrees_of_freedom + t_value * t_value
    )
    return _regularized_incomplete_beta(
        x_value,
        degrees_of_freedom / 2.0,
        0.5,
    )


def student_t_quantile(probability: float, degrees_of_freedom: int) -> float:
    if not 0.5 < probability < 1.0 or degrees_of_freedom <= 0:
        raise ValueError("Student t quantile requires p in (0.5,1) and df > 0.")
    lower = 0.0
    upper = 1.0
    while _student_t_cdf(upper, degrees_of_freedom) < probability:
        upper *= 2.0
    for _ in range(120):
        midpoint = (lower + upper) / 2.0
        if _student_t_cdf(midpoint, degrees_of_freedom) < probability:
            lower = midpoint
        else:
            upper = midpoint
    return (lower + upper) / 2.0


def _student_t_cdf(t_value: float, degrees_of_freedom: int) -> float:
    if t_value == 0:
        return 0.5
    x_value = degrees_of_freedom / (
        degrees_of_freedom + t_value * t_value
    )
    tail = 0.5 * _regularized_incomplete_beta(
        x_value,
        degrees_of_freedom / 2.0,
        0.5,
    )
    return 1.0 - tail if t_value > 0 else tail


def _regularized_incomplete_beta(x_value: float, a_value: float, b_value: float) -> float:
    if x_value <= 0:
        return 0.0
    if x_value >= 1:
        return 1.0
    log_term = (
        math.lgamma(a_value + b_value)
        - math.lgamma(a_value)
        - math.lgamma(b_value)
        + a_value * math.log(x_value)
        + b_value * math.log1p(-x_value)
    )
    front = math.exp(log_term)
    if x_value < (a_value + 1.0) / (a_value + b_value + 2.0):
        return front * _beta_continued_fraction(
            a_value,
            b_value,
            x_value,
        ) / a_value
    return 1.0 - front * _beta_continued_fraction(
        b_value,
        a_value,
        1.0 - x_value,
    ) / b_value


def _beta_continued_fraction(
    a_value: float,
    b_value: float,
    x_value: float,
) -> float:
    max_iterations = 300
    epsilon = 3e-14
    floor = 1e-300
    qab = a_value + b_value
    qap = a_value + 1.0
    qam = a_value - 1.0
    c_value = 1.0
    d_value = 1.0 - qab * x_value / qap
    if abs(d_value) < floor:
        d_value = floor
    d_value = 1.0 / d_value
    result = d_value
    for iteration in range(1, max_iterations + 1):
        even = 2 * iteration
        numerator = (
            iteration
            * (b_value - iteration)
            * x_value
            / ((qam + even) * (a_value + even))
        )
        d_value = 1.0 + numerator * d_value
        if abs(d_value) < floor:
            d_value = floor
        c_value = 1.0 + numerator / c_value
        if abs(c_value) < floor:
            c_value = floor
        d_value = 1.0 / d_value
        result *= d_value * c_value
        numerator = -(
            (a_value + iteration)
            * (qab + iteration)
            * x_value
            / ((a_value + even) * (qap + even))
        )
        d_value = 1.0 + numerator * d_value
        if abs(d_value) < floor:
            d_value = floor
        c_value = 1.0 + numerator / c_value
        if abs(c_value) < floor:
            c_value = floor
        d_value = 1.0 / d_value
        delta = d_value * c_value
        result *= delta
        if abs(delta - 1.0) < epsilon:
            break
    return result


def _finite(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _model_by_id(
    models: list[dict[str, Any]] | None,
    model_id: str,
) -> dict[str, Any] | None:
    return next(
        (model for model in models or [] if model.get("model") == model_id),
        None,
    )


def _selected_adjusted_model(
    models: list[dict[str, Any]] | None,
) -> dict[str, Any] | None:
    for model_id in PANCANCER_ADJUSTED_MODEL_PREFERENCE:
        model = _model_by_id(models, model_id)
        if model and model.get("status") == "completed":
            return model
    return None


def _adjusted_unavailable_reason(
    models: list[dict[str, Any]] | None,
) -> str:
    reasons = [
        str(model.get("reason")).strip()
        for model in models or []
        if model.get("model") in PANCANCER_ADJUSTED_MODEL_PREFERENCE
        and model.get("reason")
    ]
    unique_reasons = list(dict.fromkeys(reason for reason in reasons if reason))
    if unique_reasons:
        return " ".join(unique_reasons[:2])
    return "No ordinal stage- or grade-adjusted Cox model was evaluable."


def _annotate_effect(model: dict[str, Any], fdr_threshold: float) -> None:
    direction = _direction(_finite(model.get("hazard_ratio")))
    fdr = _finite(model.get("fdr"))
    significant = bool(fdr is not None and fdr <= fdr_threshold)
    model["direction"] = direction
    model["significant"] = significant
    model["effect_category"] = (
        direction
        if significant and direction in {"harmful", "protective"}
        else "not_evaluable"
        if direction == "not_evaluable"
        else "neutral"
    )


def _direction(hazard_ratio: float | None) -> str:
    if hazard_ratio is None:
        return "not_evaluable"
    if hazard_ratio > 1:
        return "harmful"
    if hazard_ratio < 1:
        return "protective"
    return "neutral"


def _clinical_comparison_label(row: dict[str, Any]) -> str:
    if row.get("adjusted_status") != "completed":
        return "not_evaluable"
    primary_direction = row.get("direction")
    adjusted_direction = row.get("adjusted_direction")
    if (
        primary_direction in {"harmful", "protective"}
        and adjusted_direction in {"harmful", "protective"}
        and primary_direction != adjusted_direction
    ):
        return "reversed"
    primary_significant = bool(row.get("significant"))
    adjusted_significant = bool(row.get("adjusted_significant"))
    if primary_significant and adjusted_significant:
        return "retained"
    if primary_significant and not adjusted_significant:
        return "attenuated"
    if not primary_significant and adjusted_significant:
        return "emerged"
    return "direction_consistent"


def _model_family_summary(
    rows: list[dict[str, Any]],
    model_id: str,
    fdr_threshold: float,
    *,
    effect_scale: dict[str, Any] | None = None,
    pooling_eligible: bool = True,
    pooling_reason: str | None = None,
) -> dict[str, Any]:
    row_models = [
        (row, _model_by_id(row.get("cox_models"), model_id))
        for row in rows
    ]
    completed = [
        model
        for _, model in row_models
        if model and model.get("status") == "completed"
    ]
    comparable_effects = [
        {**model, "endpoint": row.get("endpoint")}
        for row, model in row_models
        if model and model.get("status") == "completed"
    ]
    meta = (
        common_scale_meta_analysis_from_rows(
            comparable_effects,
            effect_scale=effect_scale,
        )
        if pooling_eligible
        else {
            "available": False,
            "reason": pooling_reason
            or "The requested score is not transportable on a common scale.",
            "comparability": "common_scale_unavailable",
            "effect_scale": effect_scale or {},
        }
    )
    return {
        "model": model_id,
        "evaluable_cohorts": len(completed),
        "fdr_significant": sum(
            _finite(model.get("fdr")) is not None
            and float(model["fdr"]) <= fdr_threshold
            for model in completed
        ),
        "meta_analysis": meta,
    }
