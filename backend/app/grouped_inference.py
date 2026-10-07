"""Selection-aware grouped inference, shared by Compare and Robustness."""

import math
from typing import Any


def valid_p(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and 0 <= number <= 1 else None


def grouped_inference(metrics: dict[str, Any], method: str | None = None) -> tuple[float | None, str]:
    cutpoint = metrics.get("cutpoint_details") or {}
    if method == "maxstat" or cutpoint.get("method") == "maxstat" or metrics.get("cutpoint_method") == "maxstat":
        corrected = valid_p(cutpoint.get("corrected_p_value"))
        if cutpoint.get("corrected_p_status") == "completed" and corrected is not None:
            return corrected, "maxstat_lau94_corrected"
        return None, "maxstat_corrected_unavailable"
    return valid_p(metrics.get("logrank_p_value")), "logrank"


def batch_grouped_family(items: list[dict[str, Any]], methods: list[str]) -> dict[str, Any]:
    """Freeze the family of valid grouped tests; failed/unavailable tests stay visible.

    Continuous Cox, grouped Cox and RMST p-values are not members of this family.
    This preserves the existing evaluable-test scope; it is not a correction for
    selecting which analyses to run or report across sessions.
    """
    rows = []
    for item in items:
        metrics = (item.get("result") or {}).get("metrics") or {}
        index = item["index"]
        p, test = grouped_inference(metrics, methods[index])
        if item["status"] != "completed":
            p = None
        rows.append({"index": index, "p_value": p, "test": test, "bh_q_value": None, "bonferroni_p_value": None})
    ordered = sorted((row for row in rows if row["p_value"] is not None), key=lambda row: row["p_value"])
    count = len(ordered)
    running = 1.0
    for rank in range(count, 0, -1):
        row = ordered[rank - 1]
        running = min(running, row["p_value"] * count / rank)
        row["bh_q_value"] = running
        row["bonferroni_p_value"] = min(1.0, row["p_value"] * count)
    completed = sum(item["status"] == "completed" for item in items)
    return {
        "contract": "compare-grouped-family-v1",
        "scope": "valid_grouped_tests_in_submitted_batch",
        "requested": len(methods), "completed": completed,
        "failed": len(items) - completed, "evaluable": count,
        "unavailable": len(methods) - count, "tests": rows,
    }
