import pytest

from app.r_runner import validate_maxstat_records


def _record(expression: float, event: int = 1) -> dict:
    return {
        "patient_id": f"P{expression}-{event}",
        "expression_value": expression,
        "os_time_days": 100.0,
        "os_event": event,
    }


def test_validate_maxstat_records_accepts_valid_candidate_split() -> None:
    records = [_record(float(value), event=value % 2) for value in range(1, 11)]

    validate_maxstat_records(records, minprop=0.15)


def test_validate_maxstat_records_rejects_no_candidate_between_minprop() -> None:
    records = [_record(1.0) for _ in range(9)] + [_record(2.0)]

    with pytest.raises(ValueError, match="eligible cutpoint"):
        validate_maxstat_records(records, minprop=0.15)


def test_validate_maxstat_records_rejects_no_events() -> None:
    records = [_record(float(value), event=0) for value in range(1, 11)]

    with pytest.raises(ValueError, match="survival event"):
        validate_maxstat_records(records, minprop=0.15)
