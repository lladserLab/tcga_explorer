import React, { useEffect, useId, useMemo, useState } from "react";

const FILTERABLE_CATEGORIES = new Set([
  "clinical",
  "tumor_specific",
  "dataset_specific",
]);

const CATEGORY_LABELS = {
  clinical: "Clinical variables",
  tumor_specific: "Published tumor annotations",
  dataset_specific: "Source-specific variables",
};

function formatInteger(value) {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric.toLocaleString("en-US") : "—";
}

function variableAvailable(variable, analysisContext) {
  if (variable.analysis_eligible === false) return false;
  return analysisContext !== "survival" || variable.survival_eligible !== false;
}

export function clinicalVariableProvenance(variable = {}) {
  if (variable.provenance) return variable.provenance;
  const expressionDerived = Boolean(variable.expression_derived);
  const category = variable.category || "clinical";
  if (category === "tumor_specific") {
    return {
      origin: expressionDerived
        ? "source_reported_molecular"
        : "source_reported_annotation",
      label: expressionDerived
        ? "Published molecular call"
        : "Published cohort annotation",
      reported_by: variable.source || "Source publication",
      method_summary: expressionDerived
        ? "The source reports this expression-derived classification; TRACE does not rerun it."
        : "The source reports this cohort annotation; TRACE does not reconstruct it.",
      reference: null,
      expression_derived: expressionDerived,
      recomputed_by_trace: false,
      comparability: expressionDerived
        ? "Confirm the classifier, normalization and assay platform before comparing this label across datasets."
        : "Confirm the source definition before comparing this label across datasets.",
    };
  }
  return {
    origin: category === "dataset_specific"
      ? "source_reported_metadata"
      : "harmonized_clinical",
    label: category === "dataset_specific"
      ? "Source-reported metadata"
      : "Harmonized clinical field",
    reported_by: variable.source || "Dataset metadata",
    method_summary: "TRACE preserves the reported value and does not infer a molecular subtype from it.",
    reference: null,
    expression_derived: expressionDerived,
    recomputed_by_trace: false,
    comparability: "Variables with the same name may have been measured or defined differently between studies.",
  };
}

export function ClinicalVariableProvenance({ variable, compact = false }) {
  if (!variable) return null;
  const provenance = clinicalVariableProvenance(variable);
  const reference = provenance.reference;
  const hasCoverage = variable.patient_count != null;
  return (
    <div
      className={`clinical-variable-provenance${compact ? " is-compact" : ""}`}
      aria-label={`${variable.label} provenance`}
    >
      <div className="clinical-provenance-status">
        <span className="clinical-origin-badge">{provenance.label}</span>
        {provenance.expression_derived && (
          <span className="clinical-origin-badge is-caution">Expression-derived</span>
        )}
        <span className="clinical-trace-state">
          {provenance.recomputed_by_trace
            ? "Computed by TRACE"
            : "Not recalculated by TRACE"}
        </span>
      </div>
      {!compact && provenance.method_summary && <p>{provenance.method_summary}</p>}
      <span>
        <strong>{provenance.reported_by || variable.source}</strong>
        {variable.source_field ? <> · source field <code>{variable.source_field}</code></> : null}
      </span>
      {hasCoverage && (
        <span>
          {formatInteger(variable.non_missing_count)} of {formatInteger(variable.patient_count)} patients annotated before eligibility filters
          {Number.isFinite(Number(variable.coverage))
            ? ` (${(Number(variable.coverage) * 100).toFixed(1)}%)`
            : ""}
        </span>
      )}
      {!compact && reference?.url && (
        <span>
          Reference: <a href={reference.url} target="_blank" rel="noreferrer">{reference.label || reference.doi}</a>
          {reference.doi ? ` · DOI ${reference.doi}` : ""}
        </span>
      )}
      {!compact && provenance.comparability && (
        <small className="clinical-comparability-note">{provenance.comparability}</small>
      )}
      {!compact && variable.analysis_note && <small>{variable.analysis_note}</small>}
      {!compact && !variable.analysis_eligible && variable.unavailable_reason && (
        <small>{variable.unavailable_reason}</small>
      )}
    </div>
  );
}

export function filterableClinicalVariables(
  variables = [],
  analysisContext = "survival",
) {
  return variables
    .filter((variable) => FILTERABLE_CATEGORIES.has(variable.category))
    .map((variable) => ({
      ...variable,
      available: variableAvailable(variable, analysisContext),
      categoryLabel:
        CATEGORY_LABELS[variable.category] || "Clinical variables",
    }));
}

export function clinicalFilterSummary(filters = [], variables = []) {
  const definitions = new Map(
    variables.map((variable) => [variable.id, variable]),
  );
  return filters.map((filter) => {
    const variable = definitions.get(filter.variable_id);
    const label = variable?.label || filter.variable_id;
    if (filter.categorical_levels?.length) {
      const levelLabels = new Map(
        (variable?.levels || []).map((level) => [
          level.value,
          level.label || level.value,
        ]),
      );
      return `${label}: ${filter.categorical_levels
        .map((level) => levelLabels.get(level) || level)
        .join(", ")}`;
    }
    return `${label}: ${filter.numeric_min ?? "−∞"}–${
      filter.numeric_max ?? "+∞"
    }`;
  });
}

export default function ClinicalFilterControls({
  variables = [],
  value = [],
  onChange,
  analysisContext = "survival",
  excludeVariableIds = [],
  title = "Additional patient restrictions",
}) {
  const selectorId = useId();
  const [pendingVariableId, setPendingVariableId] = useState("");
  const excluded = useMemo(
    () => new Set(excludeVariableIds.filter(Boolean)),
    [excludeVariableIds],
  );
  const catalog = useMemo(
    () => filterableClinicalVariables(variables, analysisContext),
    [variables, analysisContext],
  );
  const definitions = useMemo(
    () => new Map(catalog.map((variable) => [variable.id, variable])),
    [catalog],
  );
  const activeIds = new Set(value.map((filter) => filter.variable_id));
  const selectable = catalog.filter(
    (variable) => !activeIds.has(variable.id) && !excluded.has(variable.id),
  );
  const renderedIds = [
    ...value.map((filter) => filter.variable_id),
    ...(pendingVariableId && !activeIds.has(pendingVariableId)
      ? [pendingVariableId]
      : []),
  ];

  useEffect(() => {
    if (pendingVariableId && !definitions.has(pendingVariableId)) {
      setPendingVariableId("");
    }
  }, [definitions, pendingVariableId]);

  if (!catalog.length) return null;

  function replaceFilter(variableId, nextFilter, keepEditor = false) {
    const remaining = value.filter(
      (filter) => filter.variable_id !== variableId,
    );
    onChange(nextFilter ? [...remaining, nextFilter] : remaining);
    setPendingVariableId(keepEditor ? variableId : "");
  }

  function toggleLevel(variable, level) {
    const current = value.find(
      (filter) => filter.variable_id === variable.id,
    );
    const levels = current?.categorical_levels || [];
    const nextLevels = levels.includes(level)
      ? levels.filter((item) => item !== level)
      : [...levels, level];
    replaceFilter(
      variable.id,
      nextLevels.length
        ? {
            variable_id: variable.id,
            categorical_levels: nextLevels,
            numeric_min: null,
            numeric_max: null,
          }
        : null,
      !nextLevels.length,
    );
  }

  function updateNumericBound(variable, key, rawValue) {
    const current = value.find(
      (filter) => filter.variable_id === variable.id,
    );
    const numeric = rawValue === "" ? null : Number(rawValue);
    const next = {
      variable_id: variable.id,
      categorical_levels: [],
      numeric_min: current?.numeric_min ?? null,
      numeric_max: current?.numeric_max ?? null,
      [key]: Number.isFinite(numeric) ? numeric : null,
    };
    const empty = next.numeric_min == null && next.numeric_max == null;
    replaceFilter(variable.id, empty ? null : next, empty);
  }

  return (
    <section className="custom-clinical-filters" aria-labelledby={`${selectorId}-title`}>
      <div className="clinical-section-heading">
        <div>
          <strong id={`${selectorId}-title`}>{title}</strong>
          <small>
            Patients can match any selected value within a variable (OR), but must meet
            the filters for every selected variable (AND).
          </small>
        </div>
        <span>{value.length ? `${value.length} of 10 parameters` : "Optional"}</span>
      </div>

      {!!renderedIds.length && (
        <div className="custom-clinical-filter-list">
          {renderedIds.map((variableId) => {
            const variable = definitions.get(variableId);
            if (!variable) return null;
            const selected = value.find(
              (filter) => filter.variable_id === variable.id,
            );
            const conflict = excluded.has(variable.id);
            const disabled = !variable.available;
            const rangeInvalid = Boolean(
              selected?.numeric_min != null
              && selected?.numeric_max != null
              && selected.numeric_min > selected.numeric_max,
            );
            return (
              <div
                className={`custom-clinical-filter${
                  disabled || conflict ? " is-disabled" : ""
                }`}
                key={variable.id}
              >
                <div className="custom-clinical-filter-heading">
                  <span>
                    <strong>{variable.label}</strong>
                    <small>
                      {formatInteger(variable.non_missing_count)} /{" "}
                      {formatInteger(variable.patient_count)} observed
                    </small>
                  </span>
                  <button
                    type="button"
                    onClick={() => replaceFilter(variable.id, null)}
                    aria-label={`Remove ${variable.label} restriction`}
                  >
                    Remove
                  </button>
                </div>

                <ClinicalVariableProvenance variable={variable} compact />

                {conflict ? (
                  <p role="alert">
                    This variable already defines the comparison groups. Remove this
                    restriction or choose a different grouping variable.
                  </p>
                ) : disabled ? (
                  <p>
                    {variable.survival_unavailable_reason ||
                      variable.unavailable_reason ||
                      "This variable is not eligible in the current analysis."}
                  </p>
                ) : variable.value_type === "categorical" ? (
                  <div
                    className="custom-filter-levels"
                    aria-label={`${variable.label} levels`}
                  >
                    {variable.levels.map((level) => (
                      <button
                        key={level.value}
                        type="button"
                        aria-pressed={Boolean(
                          selected?.categorical_levels?.includes(level.value),
                        )}
                        className={
                          selected?.categorical_levels?.includes(level.value)
                            ? "selected"
                            : ""
                        }
                        disabled={level.analysis_eligible === false}
                        title={
                          level.unavailable_reason ||
                          `${formatInteger(level.count)} patients before other restrictions`
                        }
                        onClick={() => toggleLevel(variable, level.value)}
                      >
                        <span>{level.label || level.value}</span>
                        <small>{formatInteger(level.count)}</small>
                      </button>
                    ))}
                  </div>
                ) : (
                  <div className="custom-filter-range">
                    <label>
                      <span>
                        Minimum
                        {variable.numeric_summary?.unit
                          ? ` (${variable.numeric_summary.unit})`
                          : ""}
                      </span>
                      <input
                        type="number"
                        step="any"
                        value={selected?.numeric_min ?? ""}
                        aria-invalid={rangeInvalid}
                        aria-describedby={rangeInvalid ? `${selectorId}-${variable.id}-range-error` : undefined}
                        placeholder={variable.numeric_summary?.min ?? ""}
                        onChange={(event) =>
                          updateNumericBound(variable, "numeric_min", event.target.value)
                        }
                      />
                    </label>
                    <label>
                      <span>
                        Maximum
                        {variable.numeric_summary?.unit
                          ? ` (${variable.numeric_summary.unit})`
                          : ""}
                      </span>
                      <input
                        type="number"
                        step="any"
                        value={selected?.numeric_max ?? ""}
                        aria-invalid={rangeInvalid}
                        aria-describedby={rangeInvalid ? `${selectorId}-${variable.id}-range-error` : undefined}
                        placeholder={variable.numeric_summary?.max ?? ""}
                        onChange={(event) =>
                          updateNumericBound(variable, "numeric_max", event.target.value)
                        }
                      />
                    </label>
                    {rangeInvalid && (
                      <p id={`${selectorId}-${variable.id}-range-error`} className="field-error" role="alert">
                        Minimum cannot exceed maximum.
                      </p>
                    )}
                  </div>
                )}
                {variable.analysis_note && !conflict && <p>{variable.analysis_note}</p>}
              </div>
            );
          })}
        </div>
      )}

      <div className="clinical-filter-adder">
        <label htmlFor={selectorId}>
          {value.length ? "Add another parameter" : "Add a parameter"}
        </label>
        <select
          id={selectorId}
          value={pendingVariableId}
          disabled={!selectable.length || value.length >= 10}
          onChange={(event) => setPendingVariableId(event.target.value)}
        >
          <option value="">
            {value.length >= 10
              ? "Maximum of 10 parameters reached"
              : value.length
                ? "Choose another clinical variable"
                : "Choose a clinical variable"}
          </option>
          {[...new Set(selectable.map((variable) => variable.categoryLabel))].map(
            (categoryLabel) => (
              <optgroup key={categoryLabel} label={categoryLabel}>
                {selectable
                  .filter((variable) => variable.categoryLabel === categoryLabel)
                  .map((variable) => (
                    <option
                      key={variable.id}
                      value={variable.id}
                      disabled={!variable.available}
                    >
                      {variable.label}
                      {variable.non_missing_count != null
                        ? ` · n=${formatInteger(variable.non_missing_count)}`
                        : ""}
                      {!variable.available ? " · unavailable" : ""}
                    </option>
                  ))}
              </optgroup>
            ),
          )}
        </select>
      </div>
    </section>
  );
}
