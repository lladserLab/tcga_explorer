from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any

from app.schemas import ExternalCovariateDataset


@dataclass(frozen=True)
class ExternalCovariateContext:
    definitions: list[dict[str, Any]]
    selected_names: list[str]
    values_by_patient: dict[str, dict[str, str | float | None]]
    qc: dict[str, Any]
    warnings: list[str]


def empty_external_covariate_context() -> ExternalCovariateContext:
    return ExternalCovariateContext(
        definitions=[],
        selected_names=[],
        values_by_patient={},
        qc={
            "status": "not_provided",
            "schema_version": None,
            "selected_covariates": [],
        },
        warnings=[],
    )


def prepare_external_covariates(
    dataset: ExternalCovariateDataset | None,
    selected_names: list[str],
    *,
    cohort_patient_ids: set[str],
    analysis_patient_ids: set[str],
) -> ExternalCovariateContext:
    if dataset is None:
        return empty_external_covariate_context()

    selected = list(dict.fromkeys(selected_names))
    definition_by_name = {
        definition.name: definition for definition in dataset.definitions
    }
    selected_definitions = [
        definition_by_name[name].model_dump(mode="json")
        for name in selected
    ]
    row_by_patient = {row.patient_id: row.values for row in dataset.rows}
    dataset_patient_ids = set(row_by_patient)
    matched_patient_ids = dataset_patient_ids & cohort_patient_ids
    unmatched_patient_ids = sorted(dataset_patient_ids - cohort_patient_ids)

    values_by_patient: dict[str, dict[str, str | float | None]] = {}
    for patient_id in analysis_patient_ids:
        source_values = row_by_patient.get(patient_id, {})
        values_by_patient[patient_id] = {
            name: source_values.get(name)
            for name in selected
        }

    variable_qc: list[dict[str, Any]] = []
    for definition in dataset.definitions:
        name = definition.name
        supplied_values = [
            values[name]
            for values in row_by_patient.values()
            if name in values and values[name] is not None
        ]
        cohort_values = [
            row_by_patient[patient_id].get(name)
            for patient_id in matched_patient_ids
            if row_by_patient[patient_id].get(name) is not None
        ]
        analysis_values = [
            row_by_patient.get(patient_id, {}).get(name)
            for patient_id in analysis_patient_ids
            if row_by_patient.get(patient_id, {}).get(name) is not None
        ]
        observed_values = sorted(
            {str(value) for value in analysis_values},
            key=str.casefold,
        )
        variable_qc.append(
            {
                "name": name,
                "label": definition.label,
                "value_type": definition.value_type,
                "selected": name in selected,
                "supplied_non_missing": len(supplied_values),
                "cohort_matched_non_missing": len(cohort_values),
                "analysis_population_non_missing": len(analysis_values),
                "analysis_population_missing": (
                    len(analysis_patient_ids) - len(analysis_values)
                ),
                "analysis_population_missing_fraction": (
                    (len(analysis_patient_ids) - len(analysis_values))
                    / len(analysis_patient_ids)
                    if analysis_patient_ids
                    else None
                ),
                "analysis_population_unique_values": len(observed_values),
                "observed_values": observed_values[:20],
            }
        )

    dataset_payload = dataset.model_dump(mode="json")
    dataset_sha256 = hashlib.sha256(
        json.dumps(
            dataset_payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()
    status = "selected" if selected else "provided_not_selected"
    qc = {
        "status": status,
        "schema_version": dataset.schema_version,
        "source_label": dataset.source_label or None,
        "dataset_sha256": dataset_sha256,
        "n_definitions": len(dataset.definitions),
        "n_rows": len(dataset.rows),
        "cohort_patient_count": len(cohort_patient_ids),
        "analysis_population_count": len(analysis_patient_ids),
        "cohort_matched_rows": len(matched_patient_ids),
        "unmatched_rows": len(unmatched_patient_ids),
        "unmatched_patient_ids": unmatched_patient_ids,
        "selected_covariates": selected,
        "variables": variable_qc,
    }

    warnings: list[str] = []
    if unmatched_patient_ids:
        warnings.append(
            f"External covariate data include {len(unmatched_patient_ids)} TCGA "
            "participant barcode(s) absent from the selected cohort; they were "
            "ignored for modeling and retained in the audited request."
        )
    for variable in variable_qc:
        if not variable["selected"]:
            continue
        if variable["analysis_population_non_missing"] == 0:
            warnings.append(
                f"External covariate {variable['label']} has no non-missing "
                "values in the expression-complete analysis population."
            )
        elif variable["analysis_population_unique_values"] < 2:
            warnings.append(
                f"External covariate {variable['label']} has fewer than two "
                "observed values in the expression-complete analysis population."
            )

    return ExternalCovariateContext(
        definitions=selected_definitions,
        selected_names=selected,
        values_by_patient=values_by_patient,
        qc=qc,
        warnings=warnings,
    )
