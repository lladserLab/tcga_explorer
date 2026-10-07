from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any, Iterable


SAMPLE_POPULATION_CONTRACT_VERSION = "tcga-molecular-population-v1.1"

PRIMARY_BLOOD_COHORTS = {"TCGA-LAML"}
EXPLICIT_POPULATION_COHORTS = {"TCGA-SKCM"}


@dataclass(frozen=True)
class SamplePopulationPolicy:
    id: str
    label: str
    allowed_codes: tuple[str, ...]
    allowed_sample_types: tuple[str, ...]
    rationale: str

    def as_dict(self, *, requested: str | None, explicit: bool) -> dict[str, Any]:
        return {
            "contract_version": SAMPLE_POPULATION_CONTRACT_VERSION,
            "id": self.id,
            "label": self.label,
            "requested": requested,
            "explicit": explicit,
            "allowed_tcga_sample_codes": list(self.allowed_codes),
            "allowed_sample_types": list(self.allowed_sample_types),
            "rationale": self.rationale,
            "fallback_across_populations": False,
        }


POPULATIONS: dict[str, SamplePopulationPolicy] = {
    "primary_solid": SamplePopulationPolicy(
        id="primary_solid",
        label="Primary solid tumor",
        allowed_codes=("01",),
        allowed_sample_types=("Primary Tumor", "Primary Solid Tumor"),
        rationale="RNA was measured in a primary solid-tumor specimen.",
    ),
    "primary_blood": SamplePopulationPolicy(
        id="primary_blood",
        label="Primary blood-derived cancer",
        allowed_codes=("03", "09"),
        allowed_sample_types=(
            "Primary Blood Derived Cancer - Peripheral Blood",
            "Primary Blood Derived Cancer - Bone Marrow",
        ),
        rationale="RNA was measured in primary blood or bone-marrow disease material.",
    ),
    "metastatic": SamplePopulationPolicy(
        id="metastatic",
        label="Metastatic tumor",
        allowed_codes=("06", "07"),
        allowed_sample_types=("Metastatic", "Additional Metastatic"),
        rationale="RNA was measured in a metastatic specimen.",
    ),
    "recurrent": SamplePopulationPolicy(
        id="recurrent",
        label="Recurrent tumor",
        allowed_codes=("02", "04", "40"),
        allowed_sample_types=(
            "Recurrent Tumor",
            "Recurrent Solid Tumor",
            "Recurrent Blood Derived Cancer - Bone Marrow",
            "Recurrent Blood Derived Cancer - Peripheral Blood",
        ),
        rationale="RNA was measured in recurrent disease material.",
    ),
    "additional_primary": SamplePopulationPolicy(
        id="additional_primary",
        label="Additional new primary",
        allowed_codes=("05",),
        allowed_sample_types=("Additional - New Primary",),
        rationale="RNA was measured in an additional new primary tumor.",
    ),
    "other_tumor": SamplePopulationPolicy(
        id="other_tumor",
        label="Other tumor material",
        allowed_codes=("08",),
        allowed_sample_types=("Human Tumor Original Cells",),
        rationale="RNA was measured in source-coded tumor material outside the main disease classes.",
    ),
}


def tcga_sample_code(barcode: str | None) -> str | None:
    if not barcode:
        return None
    parts = barcode.split("-")
    if len(parts) < 4:
        return None
    candidate = parts[3][:2]
    return candidate if len(candidate) == 2 and candidate.isdigit() else None


def default_population_id(cohort: str) -> str:
    return "primary_blood" if cohort in PRIMARY_BLOOD_COHORTS else "primary_solid"


def _population_for_legacy_sample_types(
    sample_types: Iterable[str],
) -> str | None:
    normalized = {str(value).strip().casefold() for value in sample_types if str(value).strip()}
    if not normalized:
        return None
    matches = []
    for population_id, policy in POPULATIONS.items():
        allowed = {value.casefold() for value in policy.allowed_sample_types}
        if normalized.issubset(allowed):
            matches.append(population_id)
    if len(matches) == 1:
        return matches[0]
    raise ValueError(
        "Sample type filters must belong to one declared tumor population. "
        "Normal, control and mixed tissue populations are not eligible for this analysis."
    )


def resolve_tcga_sample_population(
    cohort: str,
    requested: str | None,
    legacy_sample_types: Iterable[str] = (),
    *,
    require_explicit_skcm: bool = True,
) -> tuple[SamplePopulationPolicy, dict[str, Any]]:
    explicit = bool(requested)
    population_id = requested
    if population_id == "primary_disease":
        population_id = default_population_id(cohort)
    if population_id is None:
        population_id = _population_for_legacy_sample_types(legacy_sample_types)
        explicit = population_id is not None
    if population_id is None:
        if require_explicit_skcm and cohort in EXPLICIT_POPULATION_COHORTS:
            raise ValueError(
                "TCGA-SKCM contains both primary and metastatic RNA samples. "
                "Choose primary_solid or metastatic explicitly; TRACE does not mix them."
            )
        population_id = default_population_id(cohort)
    policy = POPULATIONS.get(population_id)
    if policy is None:
        raise ValueError(f"Unsupported TCGA sample population: {population_id}.")
    if cohort in PRIMARY_BLOOD_COHORTS and population_id == "primary_solid":
        raise ValueError(
            f"{cohort} is a hematologic cohort; use primary_blood rather than primary_solid."
        )
    return policy, policy.as_dict(requested=requested, explicit=explicit)


def sample_matches_population(sample: Any, policy: SamplePopulationPolicy) -> bool:
    code = tcga_sample_code(getattr(sample, "barcode", None))
    sample_type = str(getattr(sample, "sample_type", "") or "").strip().casefold()
    known_sample_types = {
        value.casefold()
        for candidate in POPULATIONS.values()
        for value in candidate.allowed_sample_types
    }
    code_is_known = code is not None and any(
        code in candidate.allowed_codes for candidate in POPULATIONS.values()
    )
    type_is_known = sample_type in known_sample_types
    code_matches = code in policy.allowed_codes if code_is_known else None
    type_matches = (
        sample_type in {value.casefold() for value in policy.allowed_sample_types}
        if type_is_known
        else None
    )
    if code_matches is not None and type_matches is not None:
        return code_matches and type_matches
    if code_matches is not None:
        return code_matches
    if type_matches is not None:
        return type_matches
    return False


def sample_population_metadata_conflict(sample: Any) -> bool:
    code = tcga_sample_code(getattr(sample, "barcode", None))
    sample_type = str(getattr(sample, "sample_type", "") or "").strip().casefold()
    code_populations = {
        population_id
        for population_id, policy in POPULATIONS.items()
        if code in policy.allowed_codes
    }
    type_populations = {
        population_id
        for population_id, policy in POPULATIONS.items()
        if sample_type in {value.casefold() for value in policy.allowed_sample_types}
    }
    return bool(
        code_populations
        and type_populations
        and code_populations.isdisjoint(type_populations)
    )


def count_sample_types(samples: Iterable[Any]) -> dict[str, int]:
    counts = Counter(
        str(getattr(sample, "sample_type", None) or "Unknown")
        for sample in samples
    )
    return dict(sorted(counts.items(), key=lambda item: item[0].casefold()))


def tcga_population_options(
    cohort: str,
    samples: Iterable[Any],
) -> list[dict[str, Any]]:
    rows = list(samples)
    options = []
    for policy in POPULATIONS.values():
        matching = [sample for sample in rows if sample_matches_population(sample, policy)]
        patients = {getattr(sample, "patient_id", None) for sample in matching}
        patients.discard(None)
        options.append(
            {
                **policy.as_dict(requested=policy.id, explicit=True),
                "sample_count": len(matching),
                "patient_count": len(patients),
                "available": bool(matching),
                "recommended": policy.id == default_population_id(cohort),
                "requires_explicit_selection": cohort in EXPLICIT_POPULATION_COHORTS,
            }
        )
    return options
