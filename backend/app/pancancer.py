from __future__ import annotations

import math
from collections import Counter, defaultdict
from typing import Any


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
    effects = []
    for row in rows:
        log_hr = _finite(row.get("log_hr"))
        se = _finite(row.get("standard_error"))
        if row.get("status") == "completed" and log_hr is not None and se is not None and se > 0:
            effects.append((log_hr, se))

    if not effects:
        return {"available": False, "reason": "No completed cohort-level Cox effects were available."}

    fixed = _weighted_meta(effects, tau_squared=0.0)
    weights = [1 / (se * se) for _, se in effects]
    fixed_log_hr = fixed["log_hr"]
    q_value = sum(weight * (log_hr - fixed_log_hr) ** 2 for (log_hr, _), weight in zip(effects, weights))
    df = max(len(effects) - 1, 0)
    weight_sum = sum(weights)
    weight_sq_sum = sum(weight * weight for weight in weights)
    c_value = weight_sum - (weight_sq_sum / weight_sum) if weight_sum else 0
    tau_squared = max(0.0, (q_value - df) / c_value) if c_value > 0 and q_value > df else 0.0
    random = _weighted_meta(effects, tau_squared=tau_squared)
    i_squared = max(0.0, ((q_value - df) / q_value) * 100.0) if q_value > 0 and q_value > df else 0.0
    q_p_value = chi2_sf(q_value, df) if df >= 1 else None

    return {
        "available": True,
        "model": "DerSimonian-Laird random-effects",
        "cohorts": len(effects),
        "fixed_effect": fixed,
        "random_effect": random,
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


def _finite(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None
