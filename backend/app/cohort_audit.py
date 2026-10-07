"""Selection evidence recorded alongside, never used to decide, eligibility."""
from __future__ import annotations

from copy import deepcopy


def start_selection_audit(samples: list) -> dict:
    return {
        "schema_version": "trace-cohort-selection-v1",
        "scope": "Loaded sample inventory through expression-complete one-sample-per-patient selection; before grouping and model-specific complete cases.",
        "stages": [],
        "records": [
            {"patient_id": sample.patient_id, "sample_barcode": sample.barcode,
             "sample_type": sample.sample_type, "status": "candidate", "excluded_at": None}
            for sample in sorted(samples, key=lambda item: (item.patient_id, item.barcode))
        ],
    }


def record_selection_step(audit: dict, stage: str, before: list, after: list) -> None:
    retained = {sample.barcode for sample in after}
    removed = {sample.barcode for sample in before} - retained
    before_patients = {sample.patient_id for sample in before}
    after_patients = {sample.patient_id for sample in after}
    audit["stages"].append({
        "stage": stage, "input_samples": len(before), "retained_samples": len(after),
        "removed_samples": len(before) - len(after),
        "input_patients": len(before_patients), "retained_patients": len(after_patients),
        "removed_patients": len(before_patients - after_patients),
    })
    for row in audit["records"]:
        if row["sample_barcode"] in removed and row["excluded_at"] is None:
            row.update(status="excluded", excluded_at=stage)


def finish_selection_audit(audit: dict, candidates: list, complete: list, retained: list) -> dict:
    # A summary can be reused across markers. Never mutate an earlier marker's evidence.
    result = deepcopy(audit)
    record_selection_step(result, "expression_completeness", candidates, complete)
    record_selection_step(result, "one_sample_per_patient", complete, retained)
    barcodes = {sample.barcode for sample in retained}
    patients = {sample.patient_id for sample in retained}
    for row in result["records"]:
        if row["sample_barcode"] in barcodes:
            row["status"] = "retained"
        row["patient_retained"] = row["patient_id"] in patients
    return result
