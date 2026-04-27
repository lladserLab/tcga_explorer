from __future__ import annotations

from dataclasses import dataclass
from statistics import median

from app.models import Sample
from app.schemas import AnalysisFilters


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
    "one eligible RNA-seq sample per TCGA participant; primary tumor or primary blood-derived cancer samples are "
    "preferred, followed by recurrent/additional/metastatic tumor samples, then normal/control samples only when no "
    "higher-priority sample remains after user filters; ties are resolved by RNA analyte/portion metadata and barcode."
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
    gender: str | None
    race: str | None
    age_at_index: float | None

    def as_dict(self) -> dict:
        return {
            "patient_id": self.patient_id,
            "sample_barcode": self.sample_barcode,
            "endpoint": self.endpoint,
            "expression_value": self.expression_value,
            "group": self.group,
            "time_days": self.time_days,
            "event": self.event,
            "sample_type": self.sample_type,
            "stage": self.stage,
            "gender": self.gender,
            "race": self.race,
            "age_at_index": self.age_at_index,
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


def filter_samples(
    samples: list[Sample],
    filters: AnalysisFilters,
    endpoint_by_patient: dict[str, ClinicalOutcome] | None = None,
    endpoint: str = "OS",
    endpoint_label: str = "overall survival",
) -> tuple[list[Sample], list[str], dict]:
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
    if filters.max_time_days is not None:
        selected = [
            sample
            for sample in selected
            if outcome(sample) is not None and outcome(sample).time_days <= filters.max_time_days
        ]

    with_endpoint = [sample for sample in selected if outcome(sample) is not None]
    dropped = len(selected) - len(with_endpoint)
    if dropped:
        warnings.append(f"{dropped} samples were excluded because {endpoint_label} was not usable.")

    deduplicated: dict[str, Sample] = {}
    removed_duplicates: list[Sample] = []
    for sample in sorted(with_endpoint, key=sample_selection_key):
        if sample.patient_id in deduplicated:
            removed_duplicates.append(sample)
            continue
        deduplicated[sample.patient_id] = sample
    retained = list(deduplicated.values())
    if removed_duplicates:
        warnings.append(
            f"{len(removed_duplicates)} extra sample records from patients with multiple eligible barcodes were removed; "
            "one sample per patient was retained using TCGA biospecimen priority."
        )

    retained_non_tumor = [
        sample
        for sample in retained
        if sample_priority(sample) >= 80
    ]
    if retained_non_tumor and not filters.sample_types:
        sample_word = "sample is" if len(retained_non_tumor) == 1 else "samples are"
        warnings.append(
            f"{len(retained_non_tumor)} retained patient-level {sample_word} normal/control/unknown sample type because no "
            "higher-priority tumor sample was available after user filters."
        )

    summary = {
        "rule": "tcga_biospecimen_priority_one_sample_per_patient",
        "rule_description": SAMPLE_SELECTION_RULE,
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
        "duplicate_samples_removed": len(removed_duplicates),
        "retained_patients": len(retained),
        "retained_sample_types": count_sample_types(retained),
        "removed_duplicate_sample_types": count_sample_types(removed_duplicates),
        "sample_type_filter_applied": bool(filters.sample_types),
    }

    return retained, warnings, summary


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
        labels = ["Low" if value < q1 else "High" if value > q3 else None for value in values]
        return labels, ["Low", "High"], details

    if method == "percentile":
        pct = 50.0 if custom_percentile is None else custom_percentile
        threshold = percentile(sorted_values, pct)
        details.update({"percentile": pct, "threshold": threshold})
        labels = ["Low" if value < threshold else "High" for value in values]
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


def build_survival_records(
    samples: list[Sample],
    expression_by_barcode: dict[str, float],
    method: str,
    custom_percentile: float | None,
    endpoint_by_patient: dict[str, ClinicalOutcome] | None = None,
    endpoint: str = "OS",
    precomputed_cutpoint: dict | None = None,
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
        records.append(
            SurvivalRecord(
                patient_id=sample.patient_id,
                sample_barcode=sample.barcode,
                endpoint=endpoint,
                expression_value=expression_by_barcode[sample.barcode],
                group=label,
                time_days=float(outcome.time_days),
                event=int(outcome.event),
                sample_type=sample.sample_type,
                stage=sample.stage,
                gender=sample.gender,
                race=sample.race,
                age_at_index=sample.age_at_index,
            )
        )
    return records, group_levels, cutpoint_details


def validate_records(records: list[SurvivalRecord], endpoint_label: str = "survival endpoint") -> None:
    if len(records) < 10:
        raise ValueError(f"The analysis requires at least 10 patients with usable {endpoint_label} and expression.")
    groups: dict[str, int] = {}
    for record in records:
        groups[record.group] = groups.get(record.group, 0) + 1
    if len(groups) < 2:
        raise ValueError("The selected cutpoint produced fewer than two groups.")
    small = {group: n for group, n in groups.items() if n < 5}
    if small:
        raise ValueError(f"Each group must contain at least 5 patients; undersized groups: {small}.")
    if sum(record.event for record in records) == 0:
        raise ValueError("No survival events remain after applying filters.")
