from __future__ import annotations

from array import array
from collections import Counter
import csv
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import secrets
import shutil
import sys
from typing import Any, BinaryIO

from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.retention import persistent_local_dataset
from app.models import (
    AnalysisJob,
    CancerType,
    ComputeJob,
    RepositoryDataset,
    RepositoryEndpointDefinition,
    RepositoryEndpointValue,
    RepositoryExpressionLayer,
    RepositoryGene,
    RepositoryPatient,
    RepositoryRelease,
    RepositorySample,
)
from app.repository.storage import canonical_json_sha256, sha256_file
from app.repository.capabilities import (
    rank_signature_capability,
    rank_signature_capability_from_qc,
)
from app.schemas import UserDatasetMapping


USER_DATASET_SCHEMA_VERSION = "trace-user-dataset-v2"
USER_CUSTOM_CLINICAL_SCHEMA_VERSION = "trace-user-custom-clinical-v1"
USER_CUSTOM_CLINICAL_METADATA_KEY = "user_custom_clinical"
MIN_PATIENTS = 10
MIN_EVENTS = 5
MIN_CENSORED = 5
MAX_CUSTOM_CLINICAL_VARIABLES = 10
MAX_CUSTOM_CATEGORICAL_LEVELS = 30
MIN_CUSTOM_LEVEL_PATIENTS = 5
MIN_GENES_FOR_COUNT_NORMALIZATION = 5_000
MIN_GENES_FOR_GSEA = 100
FLOAT32_MAX = float.fromhex("0x1.fffffep+127")
FLOAT32_MIN_SUBNORMAL = float.fromhex("0x1p-149")
MISSING_TOKENS = {
    "",
    "na",
    "n/a",
    "nan",
    "null",
    "none",
    "not available",
    "not reported",
    "unknown",
    ".",
}
ENDPOINT_METADATA = {
    "OS": {
        "label": "Overall survival",
        "time_origin": "Diagnosis or study baseline, as supplied by the user",
        "event_definition": "Death from any cause",
    },
    "DSS": {
        "label": "Disease-specific survival",
        "time_origin": "Diagnosis or study baseline, as supplied by the user",
        "event_definition": "Death attributed to the indexed cancer",
    },
    "PFI": {
        "label": "Progression-free interval",
        "time_origin": "Diagnosis or study baseline, as supplied by the user",
        "event_definition": "Progression, recurrence, new tumor event or death",
    },
    "DFI": {
        "label": "Disease-free interval",
        "time_origin": "Disease-free landmark, as supplied by the user",
        "event_definition": "Recurrence, progression, new tumor event or death",
    },
}
EXPRESSION_UNITS = {
    "counts": {
        "source_unit": "raw counts",
        "analysis_unit": "log2(CPM + 1)",
        "label": "log2(CPM + 1), derived from uploaded counts",
        "transform": "library_size_cpm_log2p",
        "requires_nonnegative": True,
    },
    "tpm": {
        "source_unit": "TPM",
        "analysis_unit": "log2(TPM + 1)",
        "label": "log2(TPM + 1), derived from uploaded TPM",
        "transform": "log2p",
        "requires_nonnegative": True,
    },
    "fpkm": {
        "source_unit": "FPKM",
        "analysis_unit": "log2(FPKM + 1)",
        "label": "log2(FPKM + 1), derived from uploaded FPKM",
        "transform": "log2p",
        "requires_nonnegative": True,
    },
    "fpkm_uq": {
        "source_unit": "FPKM-UQ",
        "analysis_unit": "log2(FPKM-UQ + 1)",
        "label": "log2(FPKM-UQ + 1), derived from uploaded FPKM-UQ",
        "transform": "log2p",
        "requires_nonnegative": True,
    },
    "cpm": {
        "source_unit": "CPM",
        "analysis_unit": "log2(CPM + 1)",
        "label": "log2(CPM + 1), derived from uploaded CPM",
        "transform": "log2p",
        "requires_nonnegative": True,
    },
    "log2_tpm": {
        "source_unit": "log2(TPM + 1)",
        "analysis_unit": "log2(TPM + 1)",
        "label": "log2(TPM + 1), as uploaded",
        "transform": "none",
        "requires_nonnegative": True,
    },
    "log2_fpkm": {
        "source_unit": "log2(FPKM + 1)",
        "analysis_unit": "log2(FPKM + 1)",
        "label": "log2(FPKM + 1), as uploaded",
        "transform": "none",
        "requires_nonnegative": True,
    },
    "log2_fpkm_uq": {
        "source_unit": "log2(FPKM-UQ + 1)",
        "analysis_unit": "log2(FPKM-UQ + 1)",
        "label": "log2(FPKM-UQ + 1), as uploaded",
        "transform": "none",
        "requires_nonnegative": True,
    },
    "log2_cpm": {
        "source_unit": "log2(CPM + 1)",
        "analysis_unit": "log2(CPM + 1)",
        "label": "log2(CPM + 1), as uploaded",
        "transform": "none",
        "requires_nonnegative": True,
    },
    "normalized_log2": {
        "source_unit": "normalized log-scale expression",
        "analysis_unit": "normalized log-scale expression",
        "label": "Normalized log-scale expression, as uploaded",
        "transform": "none",
        "requires_nonnegative": False,
    },
    "normalized_continuous": {
        "source_unit": "normalized continuous expression",
        "analysis_unit": "normalized continuous expression",
        "label": "Normalized continuous expression, as uploaded",
        "transform": "none",
        "requires_nonnegative": False,
    },
}


class UserDatasetError(ValueError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        field: str | None = None,
        details: dict[str, Any] | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.message = message
        self.field = field
        self.details = details or {}

    def as_details(self) -> dict[str, Any]:
        return {
            **self.details,
            **({"field": self.field} if self.field else {}),
        }


@dataclass
class ClinicalRecord:
    patient_id: str
    time_days: float | None
    event: int | None
    raw_time: float | None
    raw_event: str | None
    stage: str | None
    grade: str | None
    age_at_index: float | None
    gender: str | None
    race: str | None
    custom_values: dict[str, str | float | None]
    outcome_exclusion_reason: str | None = None


@dataclass
class ExpressionBuild:
    raw_path: Path
    raw_layout: str
    sample_ids: list[str]
    gene_symbols: list[str]
    original_gene_ids: list[str]
    library_sizes: list[float]
    nonmissing_cells: int
    missing_cells: int
    source_min: float | None
    source_max: float | None
    expression_sample_count: int


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _optional_text(value: Any) -> str | None:
    normalized = _clean_text(value)
    return None if normalized.casefold() in MISSING_TOKENS else normalized


def _custom_categorical_value(value: Any) -> str | None:
    normalized = _optional_text(value)
    return " ".join(normalized.split()) if normalized is not None else None


def _normalized_value(value: Any) -> str:
    return _clean_text(value).casefold()


def _finite_float(value: Any) -> float | None:
    normalized = _clean_text(value)
    if normalized.casefold() in MISSING_TOKENS:
        return None
    try:
        parsed = float(normalized)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _normalized_gene(value: Any) -> str:
    return _clean_text(value).upper()


def _detect_delimiter(path: Path) -> str:
    with path.open("r", encoding="utf-8-sig", errors="strict", newline="") as handle:
        sample = handle.read(32_768)
    if not sample.strip():
        raise UserDatasetError(
            "EMPTY_FILE",
            f"{path.name} is empty.",
        )
    try:
        return csv.Sniffer().sniff(sample, delimiters=",\t;").delimiter
    except csv.Error:
        first_line = sample.splitlines()[0]
        return "\t" if first_line.count("\t") > first_line.count(",") else ","


def _reader(path: Path) -> tuple[Any, csv.DictReader]:
    handle = path.open("r", encoding="utf-8-sig", errors="strict", newline="")
    reader = csv.DictReader(handle, delimiter=_detect_delimiter(path))
    if not reader.fieldnames:
        handle.close()
        raise UserDatasetError(
            "MISSING_HEADER",
            f"{path.name} does not contain a header row.",
        )
    reader.fieldnames = [_clean_text(value) for value in reader.fieldnames]
    if any(not value for value in reader.fieldnames):
        handle.close()
        raise UserDatasetError(
            "EMPTY_COLUMN_NAME",
            f"{path.name} contains an empty column name.",
        )
    if len(reader.fieldnames) != len(set(reader.fieldnames)):
        handle.close()
        raise UserDatasetError(
            "DUPLICATE_COLUMN",
            f"{path.name} contains duplicate column names.",
        )
    return handle, reader


def save_uploaded_file(
    source: BinaryIO,
    destination: Path,
    *,
    maximum_bytes: int,
) -> dict[str, Any]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    size = 0
    with destination.open("wb") as output:
        while True:
            chunk = source.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > maximum_bytes:
                raise UserDatasetError(
                    "FILE_TOO_LARGE",
                    f"{destination.name} exceeds the configured upload limit.",
                    details={"maximum_bytes": maximum_bytes},
                )
            digest.update(chunk)
            output.write(chunk)
    if size == 0:
        raise UserDatasetError(
            "EMPTY_FILE",
            f"{destination.name} is empty.",
        )
    return {"bytes": size, "sha256": digest.hexdigest()}


def _require_columns(
    fieldnames: list[str],
    required: dict[str, str],
    *,
    filename: str,
) -> None:
    missing = [
        {"field": field, "column": column}
        for field, column in required.items()
        if column not in fieldnames
    ]
    if missing:
        raise UserDatasetError(
            "MISSING_COLUMN",
            f"{filename} is missing one or more selected columns.",
            details={"missing": missing, "available_columns": fieldnames},
        )


def _time_to_days(value: float, unit: str) -> float:
    if unit == "months":
        return value * 30.4375
    if unit == "years":
        return value * 365.25
    return value


def _parse_clinical(
    path: Path,
    mapping: UserDatasetMapping,
) -> tuple[dict[str, ClinicalRecord], dict[str, Any]]:
    handle, reader = _reader(path)
    try:
        selected_covariates = {
            key: value
            for key, value in mapping.covariates.model_dump().items()
            if value
        }
        custom_variables = list(mapping.custom_variables)
        required_columns = {
            "clinical_id_column": mapping.clinical_id_column,
            **selected_covariates,
            **{
                f"custom_clinical_variables.{variable.id}": (
                    variable.source_column
                )
                for variable in custom_variables
            },
        }
        if mapping.has_survival_outcome:
            required_columns.update(
                {
                    "time_column": mapping.time_column,
                    "event_column": mapping.event_column,
                }
            )
        _require_columns(
            list(reader.fieldnames or []),
            required_columns,
            filename=path.name,
        )
        records: dict[str, ClinicalRecord] = {}
        seen_ids: set[str] = set()
        duplicate_ids: list[str] = []
        unassigned_event_values: set[str] = set()
        excluded_missing_id = 0
        excluded_incomplete_outcome = 0
        excluded_nonpositive_time = 0
        invalid_age = 0
        invalid_custom_numeric: dict[str, dict[str, Any]] = {}
        total_rows = 0
        event_token = (mapping.event_value or "").casefold()
        censor_token = (mapping.censored_value or "").casefold()

        for row in reader:
            total_rows += 1
            patient_id = _clean_text(row.get(mapping.clinical_id_column))
            if not patient_id:
                excluded_missing_id += 1
                continue
            if len(patient_id) > 128:
                raise UserDatasetError(
                    "IDENTIFIER_TOO_LONG",
                    "A clinical identifier exceeds 128 characters.",
                    field="clinical_id_column",
                )
            if patient_id in seen_ids:
                duplicate_ids.append(patient_id)
                continue
            seen_ids.add(patient_id)

            raw_time: float | None = None
            raw_event: str | None = None
            event: int | None = None
            time_days: float | None = None
            outcome_exclusion_reason: str | None = None
            if mapping.has_survival_outcome:
                raw_time = _finite_float(row.get(mapping.time_column))
                raw_event = _clean_text(row.get(mapping.event_column))
                normalized_event = raw_event.casefold()
                if raw_time is None or normalized_event in MISSING_TOKENS:
                    excluded_incomplete_outcome += 1
                    outcome_exclusion_reason = "incomplete"
                elif normalized_event == event_token:
                    event = 1
                elif normalized_event == censor_token:
                    event = 0
                else:
                    unassigned_event_values.add(raw_event)
                if event is not None and raw_time is not None:
                    candidate_time_days = _time_to_days(
                        raw_time, mapping.time_unit
                    )
                    if not math.isfinite(candidate_time_days):
                        excluded_incomplete_outcome += 1
                        outcome_exclusion_reason = "incomplete"
                        event = None
                    elif candidate_time_days <= 0:
                        excluded_nonpositive_time += 1
                        outcome_exclusion_reason = "nonpositive_time"
                        event = None
                    else:
                        time_days = candidate_time_days

            age = None
            if mapping.covariates.age_at_index:
                raw_age = row.get(mapping.covariates.age_at_index)
                age = _finite_float(raw_age)
                if _optional_text(raw_age) is not None and age is None:
                    invalid_age += 1
            custom_values: dict[str, str | float | None] = {}
            for variable in custom_variables:
                raw_custom = row.get(variable.source_column)
                if variable.value_type == "numeric":
                    custom_value = _finite_float(raw_custom)
                    if (
                        _optional_text(raw_custom) is not None
                        and custom_value is None
                    ):
                        invalid = invalid_custom_numeric.setdefault(
                            variable.id,
                            {
                                "source_column": variable.source_column,
                                "count": 0,
                                "examples": [],
                            },
                        )
                        invalid["count"] += 1
                        raw_example = _clean_text(raw_custom)
                        if (
                            raw_example
                            and raw_example not in invalid["examples"]
                            and len(invalid["examples"]) < 10
                        ):
                            invalid["examples"].append(raw_example)
                else:
                    custom_value = _custom_categorical_value(raw_custom)
                custom_values[variable.id] = custom_value
            records[patient_id] = ClinicalRecord(
                patient_id=patient_id,
                time_days=time_days,
                event=event,
                raw_time=raw_time,
                raw_event=raw_event,
                stage=_optional_text(
                    row.get(mapping.covariates.stage)
                    if mapping.covariates.stage
                    else None
                ),
                grade=_optional_text(
                    row.get(mapping.covariates.grade)
                    if mapping.covariates.grade
                    else None
                ),
                age_at_index=age,
                gender=_optional_text(
                    row.get(mapping.covariates.gender)
                    if mapping.covariates.gender
                    else None
                ),
                race=_optional_text(
                    row.get(mapping.covariates.race)
                    if mapping.covariates.race
                    else None
                ),
                custom_values=custom_values,
                outcome_exclusion_reason=outcome_exclusion_reason,
            )
    finally:
        handle.close()

    if duplicate_ids:
        raise UserDatasetError(
            "DUPLICATE_CLINICAL_ID",
            "The selected clinical ID column must contain one row per patient.",
            field="clinical_id_column",
            details={
                "examples": sorted(set(duplicate_ids))[:10],
                "duplicate_count": len(set(duplicate_ids)),
            },
        )
    if unassigned_event_values:
        raise UserDatasetError(
            "UNMAPPED_EVENT_VALUE",
            "Every non-missing event value must be assigned as event or censored.",
            field="event_column",
            details={"unmapped_values": sorted(unassigned_event_values)[:20]},
        )
    if invalid_custom_numeric:
        raise UserDatasetError(
            "INVALID_CUSTOM_NUMERIC_VALUE",
            "Custom numeric clinical variables must contain finite numbers or missing values.",
            field="custom_clinical_variables",
            details={"variables": invalid_custom_numeric},
        )
    custom_summaries = _summarize_custom_clinical(records, mapping)
    return records, {
        "summary_population": "uploaded_metadata",
        "rows": total_rows,
        "metadata_records": len(records),
        "complete_outcomes": sum(
            record.time_days is not None and record.event is not None
            for record in records.values()
        ),
        "excluded_missing_id": excluded_missing_id,
        "excluded_incomplete_outcome": excluded_incomplete_outcome,
        "excluded_nonpositive_time": excluded_nonpositive_time,
        "invalid_optional_age": invalid_age,
        "custom_clinical_variables": custom_summaries,
    }


def _summarize_custom_clinical(
    records: dict[str, ClinicalRecord], mapping: UserDatasetMapping,
) -> list[dict[str, Any]]:
    """Summarize the supplied population, not patients absent from its matrix."""
    custom_summaries: list[dict[str, Any]] = []
    for variable in mapping.custom_variables:
        observed = [
            record.custom_values.get(variable.id)
            for record in records.values()
        ]
        non_missing = [value for value in observed if value is not None]
        if variable.value_type == "categorical":
            variants: dict[str, Counter[str]] = {}
            for value in non_missing:
                text = str(value)
                variants.setdefault(text.casefold(), Counter())[text] += 1
            canonical_by_key = {
                key: sorted(
                    counts.items(),
                    key=lambda item: (-item[1], item[0]),
                )[0][0]
                for key, counts in variants.items()
            }
            for record in records.values():
                value = record.custom_values.get(variable.id)
                if isinstance(value, str):
                    record.custom_values[variable.id] = canonical_by_key[
                        value.casefold()
                    ]
            counts = Counter(
                str(record.custom_values[variable.id])
                for record in records.values()
                if record.custom_values.get(variable.id) is not None
            )
            if len(counts) > MAX_CUSTOM_CATEGORICAL_LEVELS:
                raise UserDatasetError(
                    "CUSTOM_CATEGORICAL_HIGH_CARDINALITY",
                    (
                        f"Custom categorical variable {variable.label!r} has "
                        f"more than {MAX_CUSTOM_CATEGORICAL_LEVELS} observed levels."
                    ),
                    field="custom_clinical_variables",
                    details={
                        "variable_id": variable.id,
                        "source_column": variable.source_column,
                        "observed_levels": len(counts),
                        "maximum_levels": MAX_CUSTOM_CATEGORICAL_LEVELS,
                        "examples": sorted(counts)[:20],
                    },
                )
            eligible_levels = sum(
                count >= MIN_CUSTOM_LEVEL_PATIENTS
                for count in counts.values()
            )
            custom_summaries.append(
                {
                    **variable.model_dump(mode="json"),
                    "non_missing_count": len(non_missing),
                    "missing_count": max(0, len(records) - len(non_missing)),
                    "observed_levels": [
                        {"value": value, "count": count}
                        for value, count in sorted(
                            counts.items(),
                            key=lambda item: (-item[1], item[0].casefold()),
                        )
                    ],
                    "analysis_eligible": (
                        len(non_missing) >= MIN_PATIENTS
                        and eligible_levels >= 2
                    ),
                    "eligibility_rule": (
                        "at least two levels with at least five patients each"
                    ),
                }
            )
        else:
            finite = [float(value) for value in non_missing]
            custom_summaries.append(
                {
                    **variable.model_dump(mode="json"),
                    "non_missing_count": len(finite),
                    "missing_count": max(0, len(records) - len(finite)),
                    "min": min(finite) if finite else None,
                    "max": max(finite) if finite else None,
                    "analysis_eligible": (
                        len(finite) >= MIN_PATIENTS
                        and bool(finite)
                        and min(finite) < max(finite)
                    ),
                    "eligibility_rule": (
                        "at least ten finite values with observed variation"
                    ),
                }
            )
    return custom_summaries


def _custom_clinical_definitions(
    mapping: UserDatasetMapping,
) -> list[dict[str, Any]]:
    return [
        variable.model_dump(mode="json")
        for variable in mapping.custom_variables
    ]


def _custom_clinical_patient_metadata(
    record: ClinicalRecord,
    mapping: UserDatasetMapping,
) -> dict[str, Any] | None:
    definitions = _custom_clinical_definitions(mapping)
    if not definitions:
        return None
    return {
        USER_CUSTOM_CLINICAL_METADATA_KEY: {
            "schema_version": USER_CUSTOM_CLINICAL_SCHEMA_VERSION,
            "definitions": definitions,
            "values": {
                variable.id: record.custom_values.get(variable.id)
                for variable in mapping.custom_variables
            },
        }
    }


def _custom_clinical_notices(
    summaries: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    notices: list[dict[str, Any]] = []
    for summary in summaries:
        variable_id = str(summary["id"])
        label = str(summary["label"])
        if not summary.get("analysis_eligible"):
            notices.append(
                {
                    "level": "information",
                    "code": f"CUSTOM_CLINICAL_VARIABLE_INELIGIBLE:{variable_id}",
                    "message": (
                        f"Custom clinical variable {label!r} was retained but "
                        f"is not eligible for two-group analysis: "
                        f"{summary['eligibility_rule']}."
                    ),
                }
            )
        timing = str(summary.get("timing") or "unknown")
        if timing == "outcome":
            notices.append(
                {
                    "level": "warning",
                    "code": f"CUSTOM_CLINICAL_OUTCOME_TIMING:{variable_id}",
                    "message": (
                        f"Custom variable {label!r} is outcome-defined. It is "
                        "retained for descriptive grouping but must not be used "
                        "as a baseline survival filter or Cox covariate."
                    ),
                }
            )
        elif timing in {"on_treatment", "post_treatment", "post_baseline"}:
            notices.append(
                {
                    "level": "warning",
                    "code": f"CUSTOM_CLINICAL_POST_BASELINE_TIMING:{variable_id}",
                    "message": (
                        f"Custom variable {label!r} is measured {timing.replace('_', ' ')}. "
                        "It is not eligible for baseline survival filtering or "
                        "Cox adjustment."
                    ),
                }
            )
        elif timing == "unknown":
            notices.append(
                {
                    "level": "information",
                    "code": f"CUSTOM_CLINICAL_UNKNOWN_TIMING:{variable_id}",
                    "message": (
                        f"Custom variable {label!r} has unknown timing and is "
                        "not eligible for survival modeling until timing is declared."
                    ),
                }
            )
        if summary.get("expression_derived"):
            notices.append(
                {
                    "level": "warning",
                    "code": f"CUSTOM_CLINICAL_EXPRESSION_DERIVED:{variable_id}",
                    "message": (
                        f"Custom variable {label!r} was derived from expression. "
                        "Expression comparisons and GSEA using it are exploratory "
                        "and potentially circular."
                    ),
                }
            )
    return notices


def _update_range(
    value: float | None,
    current_min: float | None,
    current_max: float | None,
) -> tuple[float | None, float | None]:
    if value is None:
        return current_min, current_max
    return (
        value if current_min is None else min(current_min, value),
        value if current_max is None else max(current_max, value),
    )


def _parse_expression_value(
    raw_value: Any,
    *,
    unit: dict[str, Any],
    row_number: int,
    column_number: int,
    column_name: str,
) -> float | None:
    normalized = _clean_text(raw_value)
    if normalized.casefold() in MISSING_TOKENS:
        return None
    value = _finite_float(normalized)
    code = "INVALID_EXPRESSION_VALUE"
    reason = None
    if value is None:
        reason = (
            "use a finite number with a dot as the decimal separator "
            "(for example, 2.5), or leave the value blank or NA."
        )
    elif unit["requires_nonnegative"] and value < 0:
        code = "NEGATIVE_EXPRESSION"
        reason = f"{unit['source_unit']} values cannot be negative."
    elif abs(value) > FLOAT32_MAX or 0 < abs(value) < FLOAT32_MIN_SUBNORMAL:
        code = "EXPRESSION_VALUE_OUT_OF_RANGE"
        reason = (
            "this number is outside the supported storage range. "
            "Check its exponent and the expression scale before uploading again."
        )
    if reason is not None:
        raise UserDatasetError(
            code,
            f"Expression table, row {row_number}, column {column_number} "
            f"({column_name[:128]!r}): {reason}",
            field="expression_file",
            details={
                "row": row_number,
                "column": column_number,
                "column_name": column_name,
            },
        )
    return value


def _validate_gene_symbols(gene_symbols: list[str]) -> None:
    if not gene_symbols:
        raise UserDatasetError(
            "NO_GENES",
            "No gene rows or columns were found after applying the mapping.",
            field="expression_id_column",
        )
    duplicates: list[str] = []
    seen: set[str] = set()
    for symbol in gene_symbols:
        if symbol in seen:
            duplicates.append(symbol)
        seen.add(symbol)
    if duplicates:
        raise UserDatasetError(
            "DUPLICATE_GENE",
            "Gene identifiers must be unique after upper-case normalization.",
            field="expression_id_column",
            details={
                "examples": sorted(set(duplicates))[:10],
                "duplicate_count": len(set(duplicates)),
            },
        )
    ensembl_count = sum(symbol.startswith("ENSG") for symbol in gene_symbols)
    if ensembl_count > len(gene_symbols) / 2:
        raise UserDatasetError(
            "ENSEMBL_IDS_REQUIRE_SYMBOLS",
            "Most gene identifiers are Ensembl IDs. Select an HGNC gene-symbol column before importing.",
            field="expression_id_column",
            details={"ensembl_like_genes": ensembl_count},
        )


def _build_genes_by_rows(
    path: Path,
    mapping: UserDatasetMapping,
    clinical: dict[str, ClinicalRecord],
    raw_path: Path,
    settings: Settings,
) -> ExpressionBuild:
    handle, reader = _reader(path)
    try:
        fieldnames = list(reader.fieldnames or [])
        _require_columns(
            fieldnames,
            {"expression_id_column": mapping.expression_id_column},
            filename=path.name,
        )
        sample_columns = [
            column
            for column in fieldnames
            if column != mapping.expression_id_column and column in clinical
        ]
        column_numbers = {column: index + 1 for index, column in enumerate(fieldnames)}
        if len(sample_columns) > settings.user_dataset_max_samples:
            raise UserDatasetError(
                "TOO_MANY_SAMPLES",
                "The matched expression matrix exceeds the configured sample limit.",
                details={"maximum_samples": settings.user_dataset_max_samples},
            )
        gene_symbols: list[str] = []
        original_gene_ids: list[str] = []
        library_sizes = [0.0] * len(sample_columns)
        source_min: float | None = None
        source_max: float | None = None
        nonmissing = 0
        missing = 0
        expression_rows = 0
        unit = EXPRESSION_UNITS[mapping.expression_unit]
        with raw_path.open("wb") as raw:
            for row in reader:
                expression_rows += 1
                original = _clean_text(row.get(mapping.expression_id_column))
                symbol = _normalized_gene(original)
                if not symbol:
                    continue
                if len(symbol) > 128:
                    raise UserDatasetError(
                        "GENE_IDENTIFIER_TOO_LONG",
                        "A gene identifier exceeds 128 characters.",
                        field="expression_id_column",
                    )
                values = array("f")
                for index, column in enumerate(sample_columns):
                    value = _parse_expression_value(
                        row.get(column),
                        unit=unit,
                        row_number=expression_rows + 1,
                        column_number=column_numbers[column],
                        column_name=column,
                    )
                    source_min, source_max = _update_range(
                        value, source_min, source_max
                    )
                    if value is None:
                        missing += 1
                        values.append(float("nan"))
                    else:
                        nonmissing += 1
                        values.append(value)
                        if mapping.expression_unit == "counts":
                            library_sizes[index] += value
                if sys.byteorder != "little":
                    values.byteswap()
                values.tofile(raw)
                gene_symbols.append(symbol)
                original_gene_ids.append(original)
                if len(gene_symbols) > settings.user_dataset_max_genes:
                    raise UserDatasetError(
                        "TOO_MANY_GENES",
                        "The expression matrix exceeds the configured gene limit.",
                        details={"maximum_genes": settings.user_dataset_max_genes},
                    )
        _validate_gene_symbols(gene_symbols)
        cell_count = len(gene_symbols) * len(sample_columns)
        if cell_count > settings.user_dataset_max_cells:
            raise UserDatasetError(
                "MATRIX_TOO_LARGE",
                "The matched expression matrix exceeds the configured cell limit.",
                details={"maximum_cells": settings.user_dataset_max_cells},
            )
        return ExpressionBuild(
            raw_path=raw_path,
            raw_layout="row_major_gene_by_sample",
            sample_ids=sample_columns,
            gene_symbols=gene_symbols,
            original_gene_ids=original_gene_ids,
            library_sizes=library_sizes,
            nonmissing_cells=nonmissing,
            missing_cells=missing,
            source_min=source_min,
            source_max=source_max,
            expression_sample_count=len(fieldnames) - 1,
        )
    finally:
        handle.close()


def _build_samples_by_rows(
    path: Path,
    mapping: UserDatasetMapping,
    clinical: dict[str, ClinicalRecord],
    raw_path: Path,
    settings: Settings,
) -> ExpressionBuild:
    handle, reader = _reader(path)
    try:
        fieldnames = list(reader.fieldnames or [])
        _require_columns(
            fieldnames,
            {"expression_id_column": mapping.expression_id_column},
            filename=path.name,
        )
        original_gene_ids = [
            column
            for column in fieldnames
            if column != mapping.expression_id_column
        ]
        column_numbers = {column: index + 1 for index, column in enumerate(fieldnames)}
        gene_symbols = [_normalized_gene(value) for value in original_gene_ids]
        _validate_gene_symbols(gene_symbols)
        if len(gene_symbols) > settings.user_dataset_max_genes:
            raise UserDatasetError(
                "TOO_MANY_GENES",
                "The expression matrix exceeds the configured gene limit.",
                details={"maximum_genes": settings.user_dataset_max_genes},
            )
        sample_ids: list[str] = []
        library_sizes: list[float] = []
        seen_expression_ids: set[str] = set()
        source_min: float | None = None
        source_max: float | None = None
        nonmissing = 0
        missing = 0
        expression_rows = 0
        unit = EXPRESSION_UNITS[mapping.expression_unit]
        with raw_path.open("wb") as raw:
            for row in reader:
                expression_rows += 1
                sample_id = _clean_text(row.get(mapping.expression_id_column))
                if not sample_id:
                    continue
                if sample_id in seen_expression_ids:
                    raise UserDatasetError(
                        "DUPLICATE_EXPRESSION_ID",
                        "The selected expression sample ID must be unique.",
                        field="expression_id_column",
                        details={"sample_id": sample_id},
                    )
                seen_expression_ids.add(sample_id)
                if sample_id not in clinical:
                    continue
                values = array("f")
                library_size = 0.0
                for column in original_gene_ids:
                    value = _parse_expression_value(
                        row.get(column),
                        unit=unit,
                        row_number=expression_rows + 1,
                        column_number=column_numbers[column],
                        column_name=column,
                    )
                    source_min, source_max = _update_range(
                        value, source_min, source_max
                    )
                    if value is None:
                        missing += 1
                        values.append(float("nan"))
                    else:
                        nonmissing += 1
                        values.append(value)
                        if mapping.expression_unit == "counts":
                            library_size += value
                if sys.byteorder != "little":
                    values.byteswap()
                values.tofile(raw)
                sample_ids.append(sample_id)
                library_sizes.append(library_size)
                if len(sample_ids) > settings.user_dataset_max_samples:
                    raise UserDatasetError(
                        "TOO_MANY_SAMPLES",
                        "The matched expression matrix exceeds the configured sample limit.",
                        details={"maximum_samples": settings.user_dataset_max_samples},
                    )
        cell_count = len(gene_symbols) * len(sample_ids)
        if cell_count > settings.user_dataset_max_cells:
            raise UserDatasetError(
                "MATRIX_TOO_LARGE",
                "The matched expression matrix exceeds the configured cell limit.",
                details={"maximum_cells": settings.user_dataset_max_cells},
            )
        return ExpressionBuild(
            raw_path=raw_path,
            raw_layout="row_major_sample_by_gene",
            sample_ids=sample_ids,
            gene_symbols=gene_symbols,
            original_gene_ids=original_gene_ids,
            library_sizes=library_sizes,
            nonmissing_cells=nonmissing,
            missing_cells=missing,
            source_min=source_min,
            source_max=source_max,
            expression_sample_count=expression_rows,
        )
    finally:
        handle.close()


def _transform_value(
    value: float,
    *,
    expression_unit: str,
    library_size: float,
) -> float:
    if not math.isfinite(value):
        return float("nan")
    if expression_unit == "counts":
        if library_size <= 0:
            return float("nan")
        return math.log2((value / library_size) * 1_000_000.0 + 1.0)
    if expression_unit in {"tpm", "fpkm", "fpkm_uq", "cpm"}:
        return math.log2(value + 1.0)
    return value


def _read_float_array(path: Path, count: int) -> array:
    values = array("f")
    with path.open("rb") as handle:
        values.fromfile(handle, count)
    if sys.byteorder != "little":
        values.byteswap()
    if len(values) != count:
        raise UserDatasetError(
            "TRUNCATED_MATRIX",
            "The uploaded expression matrix could not be normalized completely.",
        )
    return values


def _write_analysis_matrix(
    build: ExpressionBuild,
    destination: Path,
    expression_unit: str,
) -> dict[str, Any]:
    sample_count = len(build.sample_ids)
    gene_count = len(build.gene_symbols)
    if expression_unit == "counts":
        if gene_count < MIN_GENES_FOR_COUNT_NORMALIZATION:
            raise UserDatasetError(
                "COUNT_MATRIX_TOO_NARROW",
                "Raw-count CPM normalization requires a broad matrix with at least 5,000 genes. Upload normalized expression for targeted panels.",
                field="expression_unit",
                details={
                    "gene_count": gene_count,
                    "minimum_genes": MIN_GENES_FOR_COUNT_NORMALIZATION,
                },
            )
        if any(size <= 0 for size in build.library_sizes):
            raise UserDatasetError(
                "ZERO_LIBRARY_SIZE",
                "At least one matched sample has a zero count library size.",
                field="expression_file",
            )

    total = sample_count * gene_count
    raw = _read_float_array(build.raw_path, total)
    analysis_min: float | None = None
    analysis_max: float | None = None
    analysis_nonmissing = 0
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("wb") as output:
        for gene_index in range(gene_count):
            row = array("f")
            for sample_index in range(sample_count):
                if build.raw_layout == "row_major_gene_by_sample":
                    source_index = gene_index * sample_count + sample_index
                else:
                    source_index = sample_index * gene_count + gene_index
                value = _transform_value(
                    float(raw[source_index]),
                    expression_unit=expression_unit,
                    library_size=build.library_sizes[sample_index],
                )
                if math.isfinite(value):
                    analysis_nonmissing += 1
                    analysis_min, analysis_max = _update_range(
                        value, analysis_min, analysis_max
                    )
                row.append(value)
            if sys.byteorder != "little":
                row.byteswap()
            row.tofile(output)
    return {
        "nonmissing_cells": analysis_nonmissing,
        "analysis_min": analysis_min,
        "analysis_max": analysis_max,
    }


def _write_tsv(
    path: Path,
    fieldnames: list[str],
    rows: list[dict[str, Any]],
) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fieldnames,
            delimiter="\t",
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(rows)


def _user_dataset_response(
    dataset: RepositoryDataset,
    release: RepositoryRelease,
    cancer: CancerType,
    endpoint: RepositoryEndpointDefinition | None,
    layer: RepositoryExpressionLayer,
) -> dict[str, Any]:
    endpoint_payload = (
        {
            "value": endpoint.endpoint_id,
            "label": endpoint.label,
            "patient_count": endpoint.patient_count,
            "event_count": endpoint.event_count,
            "available": endpoint.available,
            "reason": endpoint.reason,
            "time_origin": endpoint.time_origin,
            "event_definition": endpoint.event_definition,
            "source_time_unit": endpoint.source_time_unit,
        }
        if endpoint is not None
        else None
    )
    capabilities = dict(
        (dataset.metadata_json or {}).get("capabilities") or {}
    )
    if not capabilities:
        capabilities = {
            "expression_comparison": {
                "available": True,
                "patient_count": release.patient_count,
            },
            "gsea": {
                "available": layer.gene_count >= MIN_GENES_FOR_GSEA,
                "patient_count": release.patient_count,
                "gene_count": layer.gene_count,
                "reason": (
                    None
                    if layer.gene_count >= MIN_GENES_FOR_GSEA
                    else "GSEA requires at least 100 genes before run-specific variance and missingness checks."
                ),
            },
            "survival": {
                "available": bool(endpoint and endpoint.available),
                "patient_count": endpoint.patient_count if endpoint else 0,
                "event_count": endpoint.event_count if endpoint else 0,
                "reason": endpoint.reason if endpoint else "No time-to-event outcome was supplied.",
            },
        }
    capabilities["rank_based_signature_scoring"] = {
        **rank_signature_capability_from_qc(
            release.qc_json,
            expression_layer_id=layer.layer_id,
        ),
        "patient_count": release.patient_count,
    }
    return {
        "id": dataset.id,
        "kind": "user",
        "name": dataset.name,
        "cancer_code": cancer.code,
        "tcga_cohort": cancer.tcga_cohort,
        "cancer_name": cancer.name,
        "active_release_id": release.id,
        "patient_count": release.patient_count,
        "sample_count": release.sample_count,
        "gene_count": release.gene_count,
        "event_count": endpoint.event_count if endpoint else 0,
        "endpoint": endpoint_payload,
        "capabilities": capabilities,
        "expression_layer": {
            "value": layer.layer_id,
            "layer_id": layer.layer_id,
            "label": layer.label,
            "source_unit": layer.source_unit,
            "analysis_unit": layer.analysis_unit,
            "transform": layer.transform,
            "is_default": layer.is_default,
            "gene_count": layer.gene_count,
            "sample_count": layer.sample_count,
            "scale_note": (layer.metadata_json or {}).get("scale_note"),
        },
        "qc": release.qc_json or {},
        "created_at": dataset.created_at,
        "expires_at": dataset.expires_at,
        "privacy": {
            "visibility": "private",
            "enumerated": False,
            "original_files_retained": False,
            "retention_hours": (dataset.metadata_json or {}).get(
                "retention_hours"
            ),
            "delete_supported": True,
            "retention_policy": (dataset.metadata_json or {}).get("retention_policy", "temporary"),
        },
    }


def get_user_dataset(
    db: Session,
    dataset_id: str,
) -> dict[str, Any]:
    dataset = db.get(RepositoryDataset, dataset_id)
    if (
        dataset is None
        or dataset.visibility != "private"
        or dataset.status != "available"
        or not dataset.id.startswith("user-")
    ):
        raise UserDatasetError(
            "USER_DATASET_NOT_FOUND",
            "The private dataset was not found.",
        )
    if not persistent_local_dataset(dataset) and (dataset.expires_at is None or dataset.expires_at <= _now()):
        raise UserDatasetError(
            "USER_DATASET_EXPIRED",
            "The private dataset has expired. Upload it again to continue.",
        )
    release = db.get(RepositoryRelease, dataset.active_release_id)
    cancer = db.get(CancerType, dataset.cancer_code)
    if release is None or cancer is None:
        raise UserDatasetError(
            "USER_DATASET_INCOMPLETE",
            "The private dataset metadata is incomplete.",
        )
    endpoint = db.scalar(
        select(RepositoryEndpointDefinition)
        .where(RepositoryEndpointDefinition.release_id == release.id)
        .limit(1)
    )
    layer = db.scalar(
        select(RepositoryExpressionLayer)
        .where(RepositoryExpressionLayer.release_id == release.id)
        .where(RepositoryExpressionLayer.is_default.is_(True))
        .limit(1)
    )
    if layer is None:
        raise UserDatasetError(
            "USER_DATASET_INCOMPLETE",
            "The private dataset does not contain a usable expression layer.",
        )
    return _user_dataset_response(dataset, release, cancer, endpoint, layer)


def user_dataset_access_token_hash(access_token: str) -> str:
    return hashlib.sha256(access_token.encode("utf-8")).hexdigest()


def authorize_user_dataset(
    db: Session,
    dataset_id: str,
    access_token: str | None,
) -> RepositoryDataset:
    dataset = db.get(RepositoryDataset, dataset_id)
    supplied_hash = user_dataset_access_token_hash(access_token or "")
    if (
        dataset is None
        or dataset.visibility != "private"
        or not dataset.id.startswith("user-")
        or not dataset.access_token_hash
        or not secrets.compare_digest(
            dataset.access_token_hash,
            supplied_hash,
        )
    ):
        raise UserDatasetError(
            "USER_DATASET_NOT_FOUND",
            "The private dataset was not found or its access token is invalid.",
        )
    if not persistent_local_dataset(dataset) and (dataset.expires_at is None or dataset.expires_at <= _now()):
        raise UserDatasetError(
            "USER_DATASET_EXPIRED",
            "The private dataset has expired. Upload it again to continue.",
        )
    return dataset


def private_dataset_ids(value: Any) -> set[str]:
    if isinstance(value, dict):
        values = {
            item
            for key, item in value.items()
            if key == "dataset_id"
            and isinstance(item, str)
            and item.startswith("user-")
        }
        declared_ids = value.get("private_dataset_ids")
        if isinstance(declared_ids, list):
            values.update(
                item
                for item in declared_ids
                if isinstance(item, str) and item.startswith("user-")
            )
        for item in value.values():
            values.update(private_dataset_ids(item))
        return values
    if isinstance(value, list):
        values: set[str] = set()
        for item in value:
            values.update(private_dataset_ids(item))
        return values
    return set()


def authorize_user_datasets_in_payload(
    db: Session,
    payload: Any,
    access_token: str | None,
) -> None:
    dataset_ids = private_dataset_ids(payload)
    if len(dataset_ids) > 1:
        raise UserDatasetError(
            "MULTIPLE_PRIVATE_DATASETS",
            "One request cannot combine multiple private datasets.",
        )
    for dataset_id in dataset_ids:
        authorize_user_dataset(db, dataset_id, access_token)


def create_user_dataset(
    db: Session,
    settings: Settings,
    *,
    expression_source: BinaryIO,
    clinical_source: BinaryIO,
    mapping: UserDatasetMapping,
    owner_key_hash: str,
    access_token_hash: str | None = None,
) -> dict[str, Any]:
    cancer = db.get(CancerType, mapping.cancer_code)
    if cancer is None:
        raise UserDatasetError(
            "UNKNOWN_CANCER_CONTEXT",
            f"Cancer context {mapping.cancer_code!r} is not registered.",
            field="cancer_code",
        )
    active_count = int(
        db.scalar(
            select(func.count())
            .select_from(RepositoryDataset)
            .where(RepositoryDataset.visibility == "private")
            .where(RepositoryDataset.owner_key_hash == owner_key_hash)
            .where(RepositoryDataset.status == "available")
            .where(or_(RepositoryDataset.expires_at > _now(), RepositoryDataset.expires_at.is_(None)))
        )
        or 0
    )
    if active_count >= settings.user_dataset_max_active_per_client:
        raise UserDatasetError(
            "USER_DATASET_LIMIT",
            (
                "Delete an existing private dataset before uploading another. "
                f"At most {settings.user_dataset_max_active_per_client} active uploads are retained per network client."
            ),
            details={
                "maximum_active": settings.user_dataset_max_active_per_client
            },
        )
    dataset_id = f"user-{secrets.token_hex(24)}"
    release_id = f"{dataset_id}-v1"
    root = settings.user_dataset_dir
    root.mkdir(parents=True, exist_ok=True)
    root.chmod(0o700)
    staging = root / f".staging-{secrets.token_hex(16)}"
    destination = root / dataset_id
    staging.mkdir(mode=0o700, parents=False, exist_ok=False)
    try:
        expression_path = staging / "expression-upload"
        clinical_path = staging / "clinical-upload"
        expression_upload = save_uploaded_file(
            expression_source,
            expression_path,
            maximum_bytes=settings.user_dataset_expression_max_bytes,
        )
        clinical_upload = save_uploaded_file(
            clinical_source,
            clinical_path,
            maximum_bytes=settings.user_dataset_clinical_max_bytes,
        )
        clinical, clinical_qc = _parse_clinical(clinical_path, mapping)
        raw_matrix_path = staging / "expression.raw.float32le.bin"
        if mapping.expression_orientation == "genes_by_rows":
            build = _build_genes_by_rows(
                expression_path,
                mapping,
                clinical,
                raw_matrix_path,
                settings,
            )
        else:
            build = _build_samples_by_rows(
                expression_path,
                mapping,
                clinical,
                raw_matrix_path,
                settings,
            )
        matched_ids = build.sample_ids
        matched_clinical = [clinical[sample_id] for sample_id in matched_ids]
        patient_count = len(matched_ids)
        if patient_count < MIN_PATIENTS:
            raise UserDatasetError(
                "INSUFFICIENT_MATCHED_PATIENTS",
                "The matched expression and patient-metadata dataset needs at least 10 patients.",
                details={
                    "matched_patients": patient_count,
                    "thresholds": {
                        "patients": MIN_PATIENTS,
                    },
                },
            )
        matched_custom_summaries = _summarize_custom_clinical(
            {sample_id: clinical[sample_id] for sample_id in matched_ids}, mapping,
        )
        matched_outcome_exclusions = Counter(
            record.outcome_exclusion_reason
            for record in matched_clinical
            if record.outcome_exclusion_reason
        )
        matched_outcomes = [
            record
            for record in matched_clinical
            if record.time_days is not None and record.event is not None
        ]
        endpoint_patient_count = len(matched_outcomes)
        event_count = sum(int(record.event or 0) for record in matched_outcomes)
        censored_count = endpoint_patient_count - event_count
        survival_available = bool(
            mapping.has_survival_outcome
            and endpoint_patient_count >= MIN_PATIENTS
            and event_count >= MIN_EVENTS
            and censored_count >= MIN_CENSORED
        )
        survival_reason = None
        if not mapping.has_survival_outcome:
            survival_reason = "No time-to-event outcome was supplied."
        elif not survival_available:
            survival_reason = (
                "The matched outcome subset needs at least 10 patients, "
                "5 events and 5 censored observations."
            )
        matrix_path = staging / "expression.float32le.bin"
        transformed = _write_analysis_matrix(
            build,
            matrix_path,
            mapping.expression_unit,
        )
        matrix_cell_count = len(build.gene_symbols) * patient_count
        rank_missing_value_count = max(
            0,
            matrix_cell_count - int(transformed["nonmissing_cells"]),
        )
        rank_capability = {
            **rank_signature_capability(
                gene_count=len(build.gene_symbols),
                sample_count=patient_count,
                missing_value_count=rank_missing_value_count,
                expression_layer_id="uploaded_expression",
            ),
            "patient_count": patient_count,
        }
        unit = EXPRESSION_UNITS[mapping.expression_unit]
        metadata_path = staging / "expression.metadata.json"
        metadata = {
            "schema_version": USER_DATASET_SCHEMA_VERSION,
            "dtype": "float32_le",
            "layout": "row_major_gene_by_sample",
            "gene_count": len(build.gene_symbols),
            "sample_count": patient_count,
            "sample_ids": matched_ids,
            "source_unit": unit["source_unit"],
            "analysis_unit": unit["analysis_unit"],
            "transform": unit["transform"],
        }
        metadata_path.write_text(
            json.dumps(metadata, ensure_ascii=True, allow_nan=False, indent=2),
            encoding="utf-8",
        )
        genes_path = staging / "genes.tsv"
        _write_tsv(
            genes_path,
            [
                "gene_symbol",
                "original_gene_id",
                "row_number",
                "mapping_source",
            ],
            [
                {
                    "gene_symbol": symbol,
                    "original_gene_id": original,
                    "row_number": index,
                    "mapping_source": "user_supplied_hgnc_symbol",
                }
                for index, (symbol, original) in enumerate(
                    zip(
                        build.gene_symbols,
                        build.original_gene_ids,
                        strict=True,
                    )
                )
            ],
        )
        clinical_normalized_path = staging / "clinical.normalized.tsv"
        custom_fieldnames = [
            f"custom.{variable.id}" for variable in mapping.custom_variables
        ]
        _write_tsv(
            clinical_normalized_path,
            [
                "patient_id",
                "time_days",
                "event",
                "stage",
                "grade",
                "age_at_index",
                "gender",
                "race",
                *custom_fieldnames,
            ],
            [
                {
                    "patient_id": record.patient_id,
                    "time_days": (
                        f"{record.time_days:.12g}"
                        if record.time_days is not None
                        else ""
                    ),
                    "event": record.event if record.event is not None else "",
                    "stage": record.stage or "",
                    "grade": record.grade or "",
                    "age_at_index": (
                        f"{record.age_at_index:.12g}"
                        if record.age_at_index is not None
                        else ""
                    ),
                    "gender": record.gender or "",
                    "race": record.race or "",
                    **{
                        f"custom.{variable.id}": (
                            f"{value:.12g}"
                            if isinstance(
                                (value := record.custom_values.get(variable.id)),
                                float,
                            )
                            else value or ""
                        )
                        for variable in mapping.custom_variables
                    },
                }
                for record in matched_clinical
            ],
        )
        notices: list[dict[str, Any]] = []
        unmatched_expression = max(
            0, build.expression_sample_count - patient_count
        )
        unmatched_clinical = max(0, len(clinical) - patient_count)
        if unmatched_expression or unmatched_clinical:
            notices.append(
                {
                    "level": "information",
                    "code": "UNMATCHED_IDENTIFIERS_EXCLUDED",
                    "message": (
                        f"{unmatched_expression} expression identifiers and "
                        f"{unmatched_clinical} patient-metadata identifiers did not match and were excluded."
                    ),
                }
            )
        if build.missing_cells:
            notices.append(
                {
                    "level": "information",
                    "code": "MISSING_EXPRESSION_RETAINED",
                    "message": (
                        f"{build.missing_cells} missing expression cells were retained as unavailable; "
                        "each analysis uses its expression-complete patients."
                    ),
                }
            )
        if matched_outcome_exclusions["incomplete"]:
            count = matched_outcome_exclusions["incomplete"]
            notices.append(
                {
                    "level": "information",
                    "code": "INCOMPLETE_OUTCOMES_EXCLUDED_FROM_SURVIVAL",
                    "message": (
                        f"{count} matched patient{'s' if count != 1 else ''} "
                        "without a complete, finite time and event pair "
                        f"{'remain' if count != 1 else 'remains'} available to molecular analyses "
                        f"and {'are' if count != 1 else 'is'} excluded only from survival."
                    ),
                }
            )
        if matched_outcome_exclusions["nonpositive_time"]:
            count = matched_outcome_exclusions["nonpositive_time"]
            notices.append(
                {
                    "level": "warning",
                    "code": "NONPOSITIVE_TIMES_EXCLUDED_FROM_SURVIVAL",
                    "message": (
                        f"{count} matched patient{'s' if count != 1 else ''} "
                        f"{'have' if count != 1 else 'has'} a survival time of zero or less "
                        f"and {'are' if count != 1 else 'is'} excluded only from survival. "
                        "Expression data remain available to molecular analyses. Check the time values "
                        "and their starting point in your metadata file."
                    ),
                }
            )
        if not survival_available:
            notices.append(
                {
                    "level": "information",
                    "code": "SURVIVAL_NOT_AVAILABLE",
                    "message": survival_reason,
                }
            )
        notices.extend(
            _custom_clinical_notices(
                matched_custom_summaries
            )
        )
        qc = {
            "schema_version": USER_DATASET_SCHEMA_VERSION,
            "status": "passed",
            "matching": {
                "clinical_rows": clinical_qc["rows"],
                "metadata_records": len(clinical),
                "complete_clinical_outcomes": clinical_qc["complete_outcomes"],
                "expression_identifiers": build.expression_sample_count,
                "matched_patients": patient_count,
                "unmatched_expression_identifiers": unmatched_expression,
                "unmatched_clinical_identifiers": unmatched_clinical,
            },
            "endpoint": {
                "declared": bool(mapping.has_survival_outcome),
                "available": survival_available,
                "reason": survival_reason,
                "endpoint_id": mapping.endpoint if mapping.has_survival_outcome else None,
                "patients": endpoint_patient_count,
                "events": event_count,
                "censored": censored_count,
                "excluded_incomplete_outcome": matched_outcome_exclusions["incomplete"],
                "excluded_nonpositive_time": matched_outcome_exclusions["nonpositive_time"],
                "source_time_unit": mapping.time_unit if mapping.has_survival_outcome else None,
                "analysis_time_unit": "days",
                "event_value": mapping.event_value if mapping.has_survival_outcome else None,
                "censored_value": mapping.censored_value if mapping.has_survival_outcome else None,
            },
            "expression": {
                "orientation": mapping.expression_orientation,
                "genes": len(build.gene_symbols),
                "samples": patient_count,
                "source_unit": unit["source_unit"],
                "analysis_unit": unit["analysis_unit"],
                "transform": unit["transform"],
                "source_min": build.source_min,
                "source_max": build.source_max,
                "analysis_min": transformed["analysis_min"],
                "analysis_max": transformed["analysis_max"],
                "nonmissing_cells": transformed["nonmissing_cells"],
                "missing_cells": build.missing_cells,
            },
            "default_expression_layer_id": "uploaded_expression",
            "layers": {
                "uploaded_expression": {
                    "genes": len(build.gene_symbols),
                    "samples": patient_count,
                    "is_default": True,
                    "nonfinite_values": rank_missing_value_count,
                    "missing_value_policy": "retain_for_complete-case_analyses",
                }
            },
            "clinical": clinical_qc,
            "custom_clinical": {
                "schema_version": USER_CUSTOM_CLINICAL_SCHEMA_VERSION,
                "summary_population": "expression_matched_patients",
                "patient_count": patient_count,
                "maximum_variables": MAX_CUSTOM_CLINICAL_VARIABLES,
                "maximum_categorical_levels": (
                    MAX_CUSTOM_CATEGORICAL_LEVELS
                ),
                "minimum_patients_per_eligible_level": (
                    MIN_CUSTOM_LEVEL_PATIENTS
                ),
                "variables": matched_custom_summaries,
                "automatic_cox_adjustment": False,
            },
            "thresholds": {
                "minimum_patients": MIN_PATIENTS,
                "minimum_events": MIN_EVENTS,
                "minimum_censored": MIN_CENSORED,
                "maximum_samples": settings.user_dataset_max_samples,
                "maximum_genes": settings.user_dataset_max_genes,
                "maximum_cells": settings.user_dataset_max_cells,
            },
            "notices": notices,
        }
        qc_path = staging / "qc.json"
        qc_path.write_text(
            json.dumps(qc, ensure_ascii=False, allow_nan=False, indent=2),
            encoding="utf-8",
        )
        checksums = {
            "expression": sha256_file(matrix_path),
            "expression_metadata": sha256_file(metadata_path),
            "genes": sha256_file(genes_path),
            "clinical": sha256_file(clinical_normalized_path),
            "qc": sha256_file(qc_path),
        }
        created_at = _now()
        expires_at = None if settings.local_desktop_mode else created_at + timedelta(
            hours=settings.user_dataset_retention_hours
        )
        manifest = {
            "schema_version": USER_DATASET_SCHEMA_VERSION,
            "dataset_id": dataset_id,
            "release_id": release_id,
            "name": mapping.name,
            "cancer_code": cancer.code,
            "created_at": created_at.isoformat() + "Z",
            "expires_at": expires_at.isoformat() + "Z" if expires_at else None,
            "privacy": {
                "visibility": "private",
                "enumerated": False,
                "original_files_retained": False,
            },
            "mapping": {
                **mapping.model_dump(mode="json"),
                "confirm_deidentified": True,
            },
            "normalized_files": {
                "expression": "expression.float32le.bin",
                "expression_metadata": "expression.metadata.json",
                "genes": "genes.tsv",
                "clinical": "clinical.normalized.tsv",
                "qc": "qc.json",
            },
            "source_checksums": {
                "expression_upload_sha256": expression_upload["sha256"],
                "clinical_upload_sha256": clinical_upload["sha256"],
            },
            "checksums": checksums,
        }
        manifest_path = staging / "manifest.json"
        manifest_path.write_text(
            json.dumps(
                manifest,
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                indent=2,
            ),
            encoding="utf-8",
        )
        manifest_hash = canonical_json_sha256(manifest)
        raw_matrix_path.unlink(missing_ok=True)
        expression_path.unlink(missing_ok=True)
        clinical_path.unlink(missing_ok=True)
        for private_file in staging.iterdir():
            if private_file.is_file():
                private_file.chmod(0o600)
        os.replace(staging, destination)

        dataset = RepositoryDataset(
            id=dataset_id,
            cancer_code=cancer.code,
            name=mapping.name,
            description="Private user-supplied expression and patient-metadata dataset.",
            cohort_context=f"User-supplied {cancer.name} cohort",
            source_provider="user_upload",
            source_accession=f"private:{dataset_id[5:17]}",
            source_url="",
            publication_citation=None,
            publication_id=None,
            organism="Homo sapiens",
            assay="bulk_rna_expression",
            independence_status="user_supplied",
            license_id="private-user-supplied",
            license_url=None,
            redistribution_allowed=False,
            status="available",
            visibility="private",
            owner_key_hash=owner_key_hash,
            access_token_hash=(
                access_token_hash
                or user_dataset_access_token_hash(secrets.token_urlsafe(32))
            ),
            active_release_id=release_id,
            expires_at=expires_at,
            metadata_json={
                "schema_version": USER_DATASET_SCHEMA_VERSION,
                "retention_hours": None if settings.local_desktop_mode else settings.user_dataset_retention_hours,
                "retention_policy": "local_until_deleted" if settings.local_desktop_mode else "temporary",
                "original_files_retained": False,
                "custom_clinical_schema_version": (
                    USER_CUSTOM_CLINICAL_SCHEMA_VERSION
                    if mapping.custom_variables
                    else None
                ),
                "custom_clinical_variables": _custom_clinical_definitions(
                    mapping
                ),
                "custom_clinical_automatic_cox_adjustment": False,
                "capabilities": {
                    "expression_comparison": {
                        "available": True,
                        "patient_count": patient_count,
                    },
                    "gsea": {
                        "available": len(build.gene_symbols) >= MIN_GENES_FOR_GSEA,
                        "patient_count": patient_count,
                        "gene_count": len(build.gene_symbols),
                        "reason": (
                            None
                            if len(build.gene_symbols) >= MIN_GENES_FOR_GSEA
                            else "GSEA requires at least 100 genes before run-specific variance and missingness checks."
                        ),
                    },
                    "rank_based_signature_scoring": rank_capability,
                    "survival": {
                        "available": survival_available,
                        "patient_count": endpoint_patient_count,
                        "event_count": event_count,
                        "reason": survival_reason,
                    },
                },
            },
            created_at=created_at,
            updated_at=created_at,
        )
        release = RepositoryRelease(
            id=release_id,
            dataset_id=dataset_id,
            version="v1",
            status="published",
            manifest_hash=manifest_hash,
            manifest_path=str(destination / "manifest.json"),
            repository_path=str(destination),
            source_snapshot=(
                f"expression:{expression_upload['sha256']};"
                f"clinical:{clinical_upload['sha256']}"
            ),
            source_retrieved_at=created_at,
            patient_count=patient_count,
            sample_count=patient_count,
            gene_count=len(build.gene_symbols),
            qc_status="passed",
            qc_json=qc,
            published_at=created_at,
            created_at=created_at,
        )
        db.add(dataset)
        db.add(release)
        db.flush()
        patients = [
            RepositoryPatient(
                release_id=release_id,
                patient_id=record.patient_id,
                stage=record.stage,
                grade=record.grade,
                gender=record.gender,
                race=record.race,
                age_at_index=record.age_at_index,
                raw_metadata=_custom_clinical_patient_metadata(
                    record,
                    mapping,
                ),
            )
            for record in matched_clinical
        ]
        samples = [
            RepositorySample(
                release_id=release_id,
                sample_id=record.patient_id,
                patient_id=record.patient_id,
                sample_type="User supplied",
                sample_role="analysis",
                selection_rank=0,
                raw_metadata=None,
            )
            for record in matched_clinical
        ]
        db.add_all(patients)
        db.add_all(samples)
        endpoint = None
        if mapping.has_survival_outcome:
            endpoint_meta = ENDPOINT_METADATA[mapping.endpoint]
            endpoint = RepositoryEndpointDefinition(
                release_id=release_id,
                endpoint_id=mapping.endpoint,
                standard_code=mapping.endpoint,
                label=endpoint_meta["label"],
                time_origin=endpoint_meta["time_origin"],
                event_definition=endpoint_meta["event_definition"],
                source_time_column=mapping.time_column,
                source_event_column=mapping.event_column,
                source_time_unit=mapping.time_unit,
                patient_count=endpoint_patient_count,
                event_count=event_count,
                available=survival_available,
                reason=survival_reason,
                metadata_json={
                    "event_value": mapping.event_value,
                    "censored_value": mapping.censored_value,
                    "user_supplied": True,
                },
            )
            db.add(endpoint)
            db.add_all(
                [
                    RepositoryEndpointValue(
                        release_id=release_id,
                        endpoint_id=mapping.endpoint,
                        patient_id=record.patient_id,
                        time_days=record.time_days,
                        event=record.event,
                        raw_time=record.raw_time,
                        raw_event=record.raw_event,
                        raw_metadata=None,
                    )
                    for record in matched_outcomes
                ]
            )
        layer = RepositoryExpressionLayer(
            release_id=release_id,
            layer_id="uploaded_expression",
            label=unit["label"],
            source_unit=unit["source_unit"],
            analysis_unit=unit["analysis_unit"],
            transform=unit["transform"],
            matrix_path=str(destination / "expression.float32le.bin"),
            matrix_sha256=checksums["expression"],
            metadata_path=str(destination / "expression.metadata.json"),
            gene_count=len(build.gene_symbols),
            sample_count=patient_count,
            is_default=True,
            downloadable=False,
            metadata_json={
                "mapping_source": "user_supplied_hgnc_symbol",
                "scale_note": (
                    f"User declared {unit['source_unit']}; "
                    f"{unit['transform']} was applied before analysis."
                    if unit["transform"] != "none"
                    else f"User declared {unit['analysis_unit']}; values are analyzed as provided."
                ),
                "user_supplied": True,
            },
        )
        db.add(layer)
        db.flush()
        db.add_all(
            [
                RepositoryGene(
                    expression_layer_id=layer.id,
                    gene_symbol=symbol,
                    original_gene_id=original,
                    row_number=index,
                    mapping_source="user_supplied_hgnc_symbol",
                )
                for index, (symbol, original) in enumerate(
                    zip(
                        build.gene_symbols,
                        build.original_gene_ids,
                        strict=True,
                    )
                )
            ]
        )
        db.commit()
        db.refresh(dataset)
        db.refresh(release)
        if endpoint is not None:
            db.refresh(endpoint)
        db.refresh(layer)
        return _user_dataset_response(
            dataset,
            release,
            cancer,
            endpoint,
            layer,
        )
    except Exception:
        db.rollback()
        shutil.rmtree(staging, ignore_errors=True)
        shutil.rmtree(destination, ignore_errors=True)
        raise


def delete_user_dataset(
    db: Session,
    settings: Settings,
    dataset_id: str,
) -> dict[str, Any]:
    # Serialize explicit deletion with compute submission. Once this lock is
    # acquired, every job accepted before it is visible to the cleanup below;
    # later submitters cannot validate a dataset that this transaction removes.
    dataset = db.scalar(
        select(RepositoryDataset)
        .where(RepositoryDataset.id == dataset_id)
        .with_for_update()
    )
    if (
        dataset is None
        or dataset.visibility != "private"
        or not dataset.id.startswith("user-")
    ):
        raise UserDatasetError(
            "USER_DATASET_NOT_FOUND",
            "The private dataset was not found.",
        )
    related_compute_jobs = [
        job
        for job in db.scalars(select(ComputeJob)).all()
        if _payload_contains_dataset(job.request_payload, dataset_id)
    ]
    active_compute_jobs = [
        job
        for job in related_compute_jobs
        if job.status in {"queued", "running"}
    ]
    if active_compute_jobs:
        raise UserDatasetError(
            "USER_DATASET_IN_USE",
            (
                "The private dataset cannot be deleted while a compute job is "
                "queued or running. Wait for the job to finish and retry."
            ),
            details={
                "active_job_count": len(active_compute_jobs),
                "active_job_statuses": sorted(
                    {job.status for job in active_compute_jobs}
                ),
            },
        )
    analysis_ids = list(
        db.scalars(
            select(AnalysisJob.id).where(AnalysisJob.dataset_id == dataset_id)
        ).all()
    )
    for analysis_id in analysis_ids:
        shutil.rmtree(settings.artifact_dir / analysis_id, ignore_errors=True)
    for compute_job in related_compute_jobs:
        artifact_family = {
            "session": "sessions",
            "multiverse": "multiverse",
            "gsea": "gsea",
            "expression_comparison": "expression_comparisons",
        }.get(compute_job.kind)
        if artifact_family and compute_job.result_id:
            shutil.rmtree(
                settings.artifact_dir
                / artifact_family
                / compute_job.result_id,
                ignore_errors=True,
            )
        db.delete(compute_job)
    if analysis_ids:
        db.execute(
            delete(AnalysisJob).where(AnalysisJob.id.in_(analysis_ids))
        )
    repository_path = (
        Path(dataset.metadata_json.get("repository_path"))
        if (dataset.metadata_json or {}).get("repository_path")
        else settings.user_dataset_dir / dataset.id
    )
    db.delete(dataset)
    db.commit()
    shutil.rmtree(repository_path, ignore_errors=True)
    return {
        "id": dataset_id,
        "status": "deleted",
        "analysis_artifacts_deleted": len(analysis_ids),
        "compute_jobs_deleted": len(related_compute_jobs),
    }


def _payload_contains_dataset(value: Any, dataset_id: str) -> bool:
    return dataset_id in private_dataset_ids(value)


def user_dataset_ids_in_payload(value: Any) -> set[str]:
    # Use the same references for authorization, leases, retention and deletion.
    return private_dataset_ids(value)


def lock_user_datasets_for_compute(
    db: Session,
    payload: dict[str, Any],
) -> list[RepositoryDataset]:
    datasets: list[RepositoryDataset] = []
    for dataset_id in sorted(user_dataset_ids_in_payload(payload)):
        dataset = db.scalar(
            select(RepositoryDataset)
            .where(RepositoryDataset.id == dataset_id)
            .with_for_update()
        )
        # Validate the complete capability-addressed dataset while its metadata
        # row is locked against the expiry sweep.
        get_user_dataset(db, dataset_id)
        if dataset is not None:
            datasets.append(dataset)
    return datasets


def extend_user_dataset_compute_leases(
    datasets: list[RepositoryDataset],
    settings: Settings,
) -> None:
    lease_until = _now() + timedelta(
        hours=settings.user_dataset_retention_hours
    )
    for dataset in datasets:
        if persistent_local_dataset(dataset):
            continue
        if (
            dataset.expires_at is None
            or dataset.expires_at < lease_until
        ):
            dataset.expires_at = lease_until


def expire_user_datasets(
    db: Session,
    settings: Settings,
    *,
    now: datetime | None = None,
) -> int:
    cutoff = now or _now()
    dataset_ids = list(
        db.scalars(
            select(RepositoryDataset.id)
            .where(RepositoryDataset.visibility == "private")
            .where(RepositoryDataset.expires_at.is_not(None))
            .where(RepositoryDataset.expires_at <= cutoff)
            .order_by(RepositoryDataset.id)
        ).all()
    )
    expired = 0
    for dataset_id in dataset_ids:
        # Re-resolve and lock one candidate per transaction. A submitter that
        # already holds the row lock wins and this sweep skips the row; a
        # submitter arriving later cannot enqueue until this decision commits.
        dataset = db.scalar(
            select(RepositoryDataset)
            .where(RepositoryDataset.id == dataset_id)
            .where(RepositoryDataset.visibility == "private")
            .where(RepositoryDataset.expires_at.is_not(None))
            .where(RepositoryDataset.expires_at <= cutoff)
            .with_for_update(skip_locked=True)
        )
        if dataset is None:
            db.rollback()
            continue
        active_jobs = list(
            db.scalars(
                select(ComputeJob).where(
                    ComputeJob.status.in_({"queued", "running"})
                )
            ).all()
        )
        if any(
            _payload_contains_dataset(job.request_payload, dataset.id)
            for job in active_jobs
        ):
            dataset.expires_at = cutoff + timedelta(
                hours=settings.user_dataset_retention_hours
            )
            db.commit()
            continue
        try:
            delete_user_dataset(db, settings, dataset.id)
            expired += 1
        except Exception:
            db.rollback()
    return expired
