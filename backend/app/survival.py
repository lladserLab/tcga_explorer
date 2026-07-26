from __future__ import annotations

from dataclasses import dataclass, field
from statistics import median

from app.models import Sample
from app.schemas import AnalysisFilters


MIN_ANALYSIS_PATIENTS = 10
MIN_ANALYSIS_EVENTS = 5
RMST_TAU_QUANTILE = 75.0
RMST_TAU_CAP_DAYS = 5 * 365.25


SAMPLE_CODE_PRIORITY = {
    "01": 0,  # Primary Solid Tumor
    "03": 0,  # Primary Blood Derived Cancer - Peripheral Blood
    "09": 0,  # Primary Blood Derived Cancer - Bone Marrow
    "02": 10,  # Recurrent Solid Tumor
    "04": 10,  # Recurrent Blood Derived Cancer - Bone Marrow
    "40": 10,  # Recurrent Blood Derived Cancer - Peripheral Blood
    "05": 20,  # Additional - New Primary
    "06": 30,  # Metastatic
    "07": 30,  # Additional Metastatic
    "08": 40,  # Human Tumor Original Cells
    "10": 80,  # Blood Derived Normal
    "11": 80,  # Solid Tissue Normal
    "12": 80,  # Buccal Cell Normal
    "13": 80,  # EBV Immortalized Normal
    "14": 80,  # Bone Marrow Normal
    "20": 90,  # Control Analyte
    "50": 90,  # Cell Lines
    "60": 90,  # Primary Xenograft Tissue
    "61": 90,  # Cell Line Derived Xenograft Tissue
}

SAMPLE_TYPE_PRIORITY = {
    "primary tumor": 0,
    "primary solid tumor": 0,
    "primary blood derived cancer - peripheral blood": 0,
    "primary blood derived cancer - bone marrow": 0,
    "recurrent tumor": 10,
    "recurrent solid tumor": 10,
    "recurrent blood derived cancer - peripheral blood": 10,
    "recurrent blood derived cancer - bone marrow": 10,
    "additional - new primary": 20,
    "metastatic": 30,
    "additional metastatic": 30,
    "human tumor original cells": 40,
    "blood derived normal": 80,
    "solid tissue normal": 80,
    "buccal cell normal": 80,
    "ebv immortalized normal": 80,
    "bone marrow normal": 80,
    "control analyte": 90,
    "cell lines": 90,
    "primary xenograft tissue": 90,
    "cell line derived xenograft tissue": 90,
}

SAMPLE_SELECTION_RULE = (
    "one expression-complete eligible RNA-seq sample per TCGA participant; clinical filters and endpoint completeness "
    "are applied first, samples lacking the requested gene or complete signature score are removed second, and "
    "biospecimen priority is applied last. Primary tumor or primary blood-derived cancer samples are preferred, "
    "followed by recurrent/additional/metastatic tumor samples, then normal/control samples only when no "
    "higher-priority expression-complete sample remains; ties are resolved by RNA analyte/portion metadata and barcode."
)

SAMPLE_SELECTION_PRIORITY_ORDER = [
    "Primary tumor / primary blood-derived cancer",
    "Recurrent tumor",
    "Additional new primary",
    "Metastatic / additional metastatic",
    "Human tumor original cells",
    "Normal tissue / normal blood",
    "Control, cell line, xenograft or unknown",
]


@dataclass(frozen=True)
class ClinicalOutcome:
    endpoint: str
    time_days: float
    event: int
    source: str
    competing_risk_status: int | None = None
    competing_event: int | None = None
    competing_risk_source: str | None = None


@dataclass(frozen=True)
class SurvivalRecord:
    patient_id: str
    sample_barcode: str
    endpoint: str
    expression_value: float
    group: str
    time_days: float
    event: int
    sample_type: str | None
    stage: str | None
    grade: str | None
    gender: str | None
    race: str | None
    age_at_index: float | None
    competing_risk_status: int | None = None
    competing_event: int | None = None
    competing_risk_source: str | None = None
    expression_value_a: float | None = None
    expression_value_b: float | None = None
    group_a: str | None = None
    group_b: str | None = None
    external_covariates: dict[str, str | float | None] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "patient_id": self.patient_id,
            "sample_barcode": self.sample_barcode,
            "endpoint": self.endpoint,
            "expression_value": self.expression_value,
            "expression_value_a": self.expression_value_a,
            "expression_value_b": self.expression_value_b,
            "group": self.group,
            "group_a": self.group_a,
            "group_b": self.group_b,
            "time_days": self.time_days,
            "event": self.event,
            "competing_risk_status": self.competing_risk_status,
            "competing_event": self.competing_event,
            "competing_risk_source": self.competing_risk_source,
            "sample_type": self.sample_type,
            "stage": self.stage,
            "grade": self.grade,
            "gender": self.gender,
            "race": self.race,
            "age_at_index": self.age_at_index,
            "external_covariates": self.external_covariates,
        }


def sample_os_outcome(sample: Sample) -> ClinicalOutcome | None:
    if sample.os_time_days is None or sample.os_event is None:
        return None
    return ClinicalOutcome(
        endpoint="OS",
        time_days=float(sample.os_time_days),
        event=int(sample.os_event),
        source="derived_sample_metadata",
    )


def filter_sample_candidates(
    samples: list[Sample],
    filters: AnalysisFilters,
    endpoint_by_patient: dict[str, ClinicalOutcome] | None = None,
    endpoint: str = "OS",
    endpoint_label: str = "overall survival",
) -> tuple[list[Sample], list[str], dict]:
    """Apply user and endpoint eligibility without choosing a biospecimen."""

    warnings: list[str] = []
    selected = samples

    def outcome(sample: Sample) -> ClinicalOutcome | None:
        if endpoint_by_patient is not None:
            return endpoint_by_patient.get(sample.patient_id)
        return sample_os_outcome(sample)

    if filters.sample_types:
        allowed = set(filters.sample_types)
        selected = [sample for sample in selected if sample.sample_type in allowed]
    if filters.stages:
        allowed = set(filters.stages)
        selected = [sample for sample in selected if sample.stage in allowed]
    if filters.grades:
        allowed = set(filters.grades)
        selected = [sample for sample in selected if sample.grade in allowed]
    if filters.genders:
        allowed = {item.lower() for item in filters.genders}
        selected = [sample for sample in selected if sample.gender and sample.gender.lower() in allowed]
    if filters.races:
        allowed = {item.lower() for item in filters.races}
        selected = [sample for sample in selected if sample.race and sample.race.lower() in allowed]
    if filters.age_min is not None:
        selected = [sample for sample in selected if sample.age_at_index is not None and sample.age_at_index >= filters.age_min]
    if filters.age_max is not None:
        selected = [sample for sample in selected if sample.age_at_index is not None and sample.age_at_index <= filters.age_max]
    with_endpoint = [sample for sample in selected if outcome(sample) is not None]
    dropped = len(selected) - len(with_endpoint)
    if dropped:
        warnings.append(f"{dropped} samples were excluded because {endpoint_label} was not usable.")

    summary = {
        "rule": "tcga_expression_complete_biospecimen_priority_one_sample_per_patient",
        "rule_description": SAMPLE_SELECTION_RULE,
        "selection_order": [
            "user_filters",
            "endpoint_completeness",
            "requested_expression_or_score_completeness",
            "biospecimen_priority",
        ],
        "priority_order": SAMPLE_SELECTION_PRIORITY_ORDER,
        "endpoint": endpoint,
        "endpoint_label": endpoint_label,
        "endpoint_source": "tcga_cdr" if endpoint_by_patient is not None else "derived_sample_metadata",
        "input_samples": len(samples),
        "after_user_filters": len(selected),
        "complete_endpoint_samples": len(with_endpoint),
        "complete_os_samples": len(with_endpoint),
        "missing_endpoint_removed": dropped,
        "missing_os_removed": dropped,
        "candidate_patients": len({sample.patient_id for sample in with_endpoint}),
        "sample_type_filter_applied": bool(filters.sample_types),
    }
    return with_endpoint, warnings, summary


def select_expression_complete_samples(
    candidates: list[Sample],
    expression_barcodes: set[str] | None,
    *,
    warnings: list[str] | None = None,
    summary: dict | None = None,
) -> tuple[list[Sample], list[str], dict]:
    """Select one sample per patient after required-expression completeness."""

    warnings = list(warnings or [])
    summary = dict(summary or {})
    expression_requirement_applied = expression_barcodes is not None
    complete = (
        [sample for sample in candidates if sample.barcode in expression_barcodes]
        if expression_requirement_applied
        else list(candidates)
    )
    complete_barcodes = {sample.barcode for sample in complete}
    missing_expression = [
        sample for sample in candidates if sample.barcode not in complete_barcodes
    ]
    candidate_patients = {sample.patient_id for sample in candidates}
    complete_patients = {sample.patient_id for sample in complete}
    missing_expression_patients = candidate_patients - complete_patients
    if missing_expression:
        warnings.append(
            f"{len(missing_expression)} samples from "
            f"{len({sample.patient_id for sample in missing_expression})} participants "
            "were excluded because the requested gene or complete signature score "
            "was unavailable."
        )

    deduplicated: dict[str, Sample] = {}
    removed_duplicates: list[Sample] = []
    for sample in sorted(complete, key=sample_selection_key):
        if sample.patient_id in deduplicated:
            removed_duplicates.append(sample)
            continue
        deduplicated[sample.patient_id] = sample
    retained = list(deduplicated.values())

    candidates_by_patient: dict[str, list[Sample]] = {}
    for sample in candidates:
        candidates_by_patient.setdefault(sample.patient_id, []).append(sample)
    candidate_priority = {
        patient_id: min(candidates_by_patient[patient_id], key=sample_selection_key)
        for patient_id in complete_patients
    }
    expression_priority_fallbacks = [
        sample
        for patient_id, sample in deduplicated.items()
        if candidate_priority[patient_id].barcode != sample.barcode
    ]
    if expression_priority_fallbacks:
        warnings.append(
            f"{len(expression_priority_fallbacks)} participants used a lower-priority "
            "biospecimen because a higher-priority eligible candidate lacked complete "
            "required expression."
        )
    if removed_duplicates:
        warnings.append(
            f"{len(removed_duplicates)} extra expression-complete sample records from "
            "patients with multiple eligible barcodes were removed; one sample per "
            "patient was retained using TCGA biospecimen priority."
        )

    retained_non_tumor = [
        sample
        for sample in retained
        if sample_priority(sample) >= 80
    ]
    if retained_non_tumor and not summary.get("sample_type_filter_applied", False):
        sample_word = "sample is" if len(retained_non_tumor) == 1 else "samples are"
        warnings.append(
            f"{len(retained_non_tumor)} retained patient-level {sample_word} normal/control/unknown sample type because no "
            "higher-priority tumor sample was available after user filters."
        )

    summary.update({
        "expression_requirement_applied": expression_requirement_applied,
        "expression_complete_samples": len(complete),
        "expression_complete_patients": len(complete_patients),
        "missing_expression_samples_removed": len(missing_expression),
        "missing_expression_patients_removed": len(missing_expression_patients),
        "expression_priority_fallbacks": len(expression_priority_fallbacks),
        "expression_priority_fallback_barcodes": [
            sample.barcode for sample in expression_priority_fallbacks
        ],
        "duplicate_samples_removed": len(removed_duplicates),
        "retained_patients": len(retained),
        "retained_sample_types": count_sample_types(retained),
        "removed_duplicate_sample_types": count_sample_types(removed_duplicates),
    })

    return retained, warnings, summary


def filter_samples(
    samples: list[Sample],
    filters: AnalysisFilters,
    endpoint_by_patient: dict[str, ClinicalOutcome] | None = None,
    endpoint: str = "OS",
    endpoint_label: str = "overall survival",
) -> tuple[list[Sample], list[str], dict]:
    """Backward-compatible clinical/endpoint filtering and sample selection."""

    candidates, warnings, summary = filter_sample_candidates(
        samples,
        filters,
        endpoint_by_patient=endpoint_by_patient,
        endpoint=endpoint,
        endpoint_label=endpoint_label,
    )
    return select_expression_complete_samples(
        candidates,
        None,
        warnings=warnings,
        summary=summary,
    )


def sample_selection_key(sample: Sample) -> tuple[int, int, int, str]:
    return (
        sample_priority(sample),
        analyte_priority(sample.barcode),
        portion_priority(sample.barcode),
        sample.barcode or "",
    )


def sample_priority(sample: Sample) -> int:
    code = tcga_sample_code(sample.barcode)
    if code in SAMPLE_CODE_PRIORITY:
        return SAMPLE_CODE_PRIORITY[code]
    sample_type = (sample.sample_type or "").strip().lower()
    return SAMPLE_TYPE_PRIORITY.get(sample_type, 99)


def tcga_sample_code(barcode: str | None) -> str | None:
    if not barcode:
        return None
    parts = barcode.split("-")
    if len(parts) < 4:
        return None
    candidate = parts[3][:2]
    return candidate if len(candidate) == 2 and candidate.isdigit() else None


def analyte_priority(barcode: str | None) -> int:
    if not barcode:
        return 9
    parts = barcode.split("-")
    if len(parts) < 5 or not parts[4]:
        return 5
    analyte = parts[4][-1].upper()
    return {"R": 0, "T": 1, "H": 2}.get(analyte, 8)


def portion_priority(barcode: str | None) -> int:
    if not barcode:
        return 99
    parts = barcode.split("-")
    if len(parts) < 5:
        return 99
    portion = parts[4][:2]
    return int(portion) if portion.isdigit() else 99


def count_sample_types(samples: list[Sample]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for sample in samples:
        label = sample.sample_type or "Unknown"
        counts[label] = counts.get(label, 0) + 1
    return dict(sorted(counts.items()))


def assign_groups(values: list[float], method: str, custom_percentile: float | None = None) -> tuple[list[str | None], list[str], dict]:
    return assign_groups_with_cutpoint(values, method, custom_percentile)


def assign_groups_with_cutpoint(
    values: list[float],
    method: str,
    custom_percentile: float | None = None,
    precomputed_cutpoint: dict | None = None,
) -> tuple[list[str | None], list[str], dict]:
    if not values:
        return [], [], {}
    sorted_values = sorted(values)
    details: dict[str, float | str] = {"method": method}

    if method == "maxstat":
        if not precomputed_cutpoint or "threshold" not in precomputed_cutpoint:
            raise ValueError("Maxstat stratification requires a computed cutpoint.")
        threshold = float(precomputed_cutpoint["threshold"])
        details.update(precomputed_cutpoint)
        details["method"] = "maxstat"
        details["threshold"] = threshold
        labels = ["Low" if value <= threshold else "High" for value in values]
        return labels, ["Low", "High"], details

    if method == "median":
        threshold = median(sorted_values)
        details["threshold"] = threshold
        labels = ["Low" if value <= threshold else "High" for value in values]
        return labels, ["Low", "High"], details

    if method == "tertiles":
        q1 = percentile(sorted_values, 33.333333)
        q2 = percentile(sorted_values, 66.666667)
        details.update({"lower_tertile": q1, "upper_tertile": q2})
        labels = ["Low" if value <= q1 else "Mid" if value <= q2 else "High" for value in values]
        return labels, ["Low", "Mid", "High"], details

    if method == "upper_quartile":
        q3 = percentile(sorted_values, 75)
        details["upper_quartile"] = q3
        labels = ["High" if value >= q3 else "Low/Medium" for value in values]
        return labels, ["Low/Medium", "High"], details

    if method == "upper_lower_quartile":
        q1 = percentile(sorted_values, 25)
        q3 = percentile(sorted_values, 75)
        details.update({"lower_quartile": q1, "upper_quartile": q3})
        labels = ["Low" if value <= q1 else "High" if value >= q3 else None for value in values]
        return labels, ["Low", "High"], details

    if method == "percentile":
        pct = 50.0 if custom_percentile is None else custom_percentile
        threshold = percentile(sorted_values, pct)
        details.update({"percentile": pct, "threshold": threshold})
        labels = ["Low" if value <= threshold else "High" for value in values]
        return labels, ["Low", "High"], details

    raise ValueError(f"Unsupported cutpoint method: {method}")


def percentile(sorted_values: list[float], pct: float) -> float:
    if len(sorted_values) == 1:
        return sorted_values[0]
    rank = (pct / 100.0) * (len(sorted_values) - 1)
    lower = int(rank)
    upper = min(lower + 1, len(sorted_values) - 1)
    weight = rank - lower
    return sorted_values[lower] * (1 - weight) + sorted_values[upper] * weight


def _apply_time_ceiling(outcome: ClinicalOutcome, max_time_days: float) -> ClinicalOutcome:
    if outcome.time_days <= max_time_days:
        return outcome
    return ClinicalOutcome(
        endpoint=outcome.endpoint,
        time_days=max_time_days,
        event=0,
        source=outcome.source,
        competing_risk_status=(
            0 if outcome.competing_risk_status is not None else None
        ),
        competing_event=0 if outcome.competing_event is not None else None,
        competing_risk_source=outcome.competing_risk_source,
    )


def build_survival_records(
    samples: list[Sample],
    expression_by_barcode: dict[str, float],
    method: str,
    custom_percentile: float | None,
    endpoint_by_patient: dict[str, ClinicalOutcome] | None = None,
    endpoint: str = "OS",
    precomputed_cutpoint: dict | None = None,
    max_time_days: float | None = None,
    external_covariates_by_patient: (
        dict[str, dict[str, str | float | None]] | None
    ) = None,
) -> tuple[list[SurvivalRecord], list[str], dict]:
    samples_with_expression = [sample for sample in samples if sample.barcode in expression_by_barcode]
    values = [expression_by_barcode[sample.barcode] for sample in samples_with_expression]
    labels, group_levels, cutpoint_details = assign_groups_with_cutpoint(
        values,
        method,
        custom_percentile,
        precomputed_cutpoint,
    )

    records: list[SurvivalRecord] = []
    for sample, label in zip(samples_with_expression, labels, strict=False):
        if label is None:
            continue
        outcome = endpoint_by_patient.get(sample.patient_id) if endpoint_by_patient is not None else sample_os_outcome(sample)
        if outcome is None:
            continue
        if max_time_days is not None:
            outcome = _apply_time_ceiling(outcome, max_time_days)
        records.append(
            SurvivalRecord(
                patient_id=sample.patient_id,
                sample_barcode=sample.barcode,
                endpoint=endpoint,
                expression_value=expression_by_barcode[sample.barcode],
                group=label,
                time_days=float(outcome.time_days),
                event=int(outcome.event),
                competing_risk_status=outcome.competing_risk_status,
                competing_event=outcome.competing_event,
                competing_risk_source=outcome.competing_risk_source,
                sample_type=sample.sample_type,
                stage=sample.stage,
                grade=sample.grade,
                gender=sample.gender,
                race=sample.race,
                age_at_index=sample.age_at_index,
                external_covariates=(
                    external_covariates_by_patient.get(sample.patient_id, {})
                    if external_covariates_by_patient
                    else {}
                ),
            )
        )
    return records, group_levels, cutpoint_details


def build_continuous_survival_records(
    samples: list[Sample],
    expression_by_barcode: dict[str, float],
    endpoint_by_patient: dict[str, ClinicalOutcome] | None = None,
    endpoint: str = "OS",
    max_time_days: float | None = None,
    external_covariates_by_patient: (
        dict[str, dict[str, str | float | None]] | None
    ) = None,
) -> list[SurvivalRecord]:
    """Build the expression-complete population before any cutpoint exclusions."""
    records: list[SurvivalRecord] = []
    for sample in samples:
        if sample.barcode not in expression_by_barcode:
            continue
        outcome = endpoint_by_patient.get(sample.patient_id) if endpoint_by_patient is not None else sample_os_outcome(sample)
        if outcome is None:
            continue
        if max_time_days is not None:
            outcome = _apply_time_ceiling(outcome, max_time_days)
        records.append(
            SurvivalRecord(
                patient_id=sample.patient_id,
                sample_barcode=sample.barcode,
                endpoint=endpoint,
                expression_value=expression_by_barcode[sample.barcode],
                group="All eligible",
                time_days=float(outcome.time_days),
                event=int(outcome.event),
                competing_risk_status=outcome.competing_risk_status,
                competing_event=outcome.competing_event,
                competing_risk_source=outcome.competing_risk_source,
                sample_type=sample.sample_type,
                stage=sample.stage,
                grade=sample.grade,
                gender=sample.gender,
                race=sample.race,
                age_at_index=sample.age_at_index,
                external_covariates=(
                    external_covariates_by_patient.get(sample.patient_id, {})
                    if external_covariates_by_patient
                    else {}
                ),
            )
        )
    return records


def build_combined_survival_records(
    samples: list[Sample],
    expression_a_by_barcode: dict[str, float],
    expression_b_by_barcode: dict[str, float],
    method: str,
    endpoint_by_patient: dict[str, ClinicalOutcome] | None = None,
    endpoint: str = "OS",
    max_time_days: float | None = None,
    external_covariates_by_patient: (
        dict[str, dict[str, str | float | None]] | None
    ) = None,
) -> tuple[list[SurvivalRecord], list[str], dict]:
    samples_with_expression = [
        sample
        for sample in samples
        if sample.barcode in expression_a_by_barcode and sample.barcode in expression_b_by_barcode
    ]
    values_a = [expression_a_by_barcode[sample.barcode] for sample in samples_with_expression]
    values_b = [expression_b_by_barcode[sample.barcode] for sample in samples_with_expression]
    labels_a, levels_a, details_a = assign_groups_with_cutpoint(values_a, method)
    labels_b, levels_b, details_b = assign_groups_with_cutpoint(values_b, method)

    records: list[SurvivalRecord] = []
    for sample, label_a, label_b in zip(samples_with_expression, labels_a, labels_b, strict=False):
        if label_a is None or label_b is None:
            continue
        outcome = endpoint_by_patient.get(sample.patient_id) if endpoint_by_patient is not None else sample_os_outcome(sample)
        if outcome is None:
            continue
        if max_time_days is not None:
            outcome = _apply_time_ceiling(outcome, max_time_days)
        value_a = expression_a_by_barcode[sample.barcode]
        value_b = expression_b_by_barcode[sample.barcode]
        records.append(
            SurvivalRecord(
                patient_id=sample.patient_id,
                sample_barcode=sample.barcode,
                endpoint=endpoint,
                expression_value=(value_a + value_b) / 2,
                expression_value_a=value_a,
                expression_value_b=value_b,
                group=f"{label_a}_{label_b}",
                group_a=label_a,
                group_b=label_b,
                time_days=float(outcome.time_days),
                event=int(outcome.event),
                competing_risk_status=outcome.competing_risk_status,
                competing_event=outcome.competing_event,
                competing_risk_source=outcome.competing_risk_source,
                sample_type=sample.sample_type,
                stage=sample.stage,
                grade=sample.grade,
                gender=sample.gender,
                race=sample.race,
                age_at_index=sample.age_at_index,
                external_covariates=(
                    external_covariates_by_patient.get(sample.patient_id, {})
                    if external_covariates_by_patient
                    else {}
                ),
            )
        )

    present_groups = {record.group for record in records}
    group_levels = [
        f"{level_a}_{level_b}"
        for level_a in levels_a
        for level_b in levels_b
        if f"{level_a}_{level_b}" in present_groups
    ]
    cutpoint_details = combined_cutpoint_details(method, details_a, details_b, levels_a, levels_b)
    return records, group_levels, cutpoint_details


def select_rmst_tau(
    samples: list[Sample],
    expression_barcodes: set[str],
    endpoint_by_patient: dict[str, ClinicalOutcome] | None = None,
    max_time_days: float | None = None,
) -> dict:
    """Choose one cutpoint-independent RMST horizon from the eligible cohort."""
    times: list[float] = []
    for sample in samples:
        if sample.barcode not in expression_barcodes:
            continue
        outcome = endpoint_by_patient.get(sample.patient_id) if endpoint_by_patient is not None else sample_os_outcome(sample)
        if outcome is None or outcome.time_days <= 0:
            continue
        time_days = float(outcome.time_days)
        if max_time_days is not None:
            time_days = min(time_days, float(max_time_days))
        times.append(time_days)

    if len(times) < MIN_ANALYSIS_PATIENTS:
        return {
            "status": "unavailable",
            "reason": "Fewer than 10 eligible patients were available to define a fixed RMST horizon.",
            "source_n_patients": len(times),
        }

    tau_days = min(
        RMST_TAU_CAP_DAYS,
        percentile(sorted(times), RMST_TAU_QUANTILE),
    )
    return {
        "status": "available",
        "tau_days": tau_days,
        "source_n_patients": len(times),
        "rule": (
            "minimum of 5 years and the 75th percentile of observed endpoint times "
            "in the unstratified, expression-complete eligible cohort"
        ),
        "quantile": RMST_TAU_QUANTILE / 100.0,
        "cap_days": RMST_TAU_CAP_DAYS,
        "cutpoint_independent": True,
    }


def combined_cutpoint_details(
    method: str,
    details_a: dict,
    details_b: dict,
    levels_a: list[str],
    levels_b: list[str],
) -> dict:
    details = {
        "method": method,
        "combination": "signature_a_x_signature_b",
        "signature_a_levels": "/".join(levels_a),
        "signature_b_levels": "/".join(levels_b),
    }
    for key, value in details_a.items():
        if key != "method":
            details[f"signature_a_{key}"] = value
    for key, value in details_b.items():
        if key != "method":
            details[f"signature_b_{key}"] = value
    return details


def validate_records(records: list[SurvivalRecord], endpoint_label: str = "survival endpoint") -> None:
    if len(records) < MIN_ANALYSIS_PATIENTS:
        raise ValueError(f"The analysis requires at least 10 patients with usable {endpoint_label} and expression.")
    groups: dict[str, int] = {}
    for record in records:
        groups[record.group] = groups.get(record.group, 0) + 1
    if len(groups) < 2:
        raise ValueError("The selected cutpoint produced fewer than two groups.")
    small = {group: n for group, n in groups.items() if n < 5}
    if small:
        raise ValueError(f"Each group must contain at least 5 patients; undersized groups: {small}.")
    n_events = sum(record.event for record in records)
    if n_events < MIN_ANALYSIS_EVENTS:
        raise ValueError(
            f"The analysis requires at least {MIN_ANALYSIS_EVENTS} survival events after applying filters; "
            f"{n_events} remain."
        )
