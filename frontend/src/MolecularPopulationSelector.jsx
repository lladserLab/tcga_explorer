import React from "react";

import { TraceIcon } from "./design/icons";
import {
  availableSamplePopulations,
  molecularPopulationSummary,
  requiresSamplePopulation,
} from "./samplePopulation";

export default function MolecularPopulationSelector({
  form,
  filters,
  onChange,
  compact = false,
}) {
  if (!form.cohort) return null;
  const summary = molecularPopulationSummary(form, filters || {});
  if (form.dataset_id) {
    return (
      <div className="molecular-population-release" role="note">
        <TraceIcon role="data.cohort" size="sm" />
        <span>
          <strong>{summary.label}</strong>
          <small>{summary.detail}</small>
        </span>
      </div>
    );
  }

  const options = availableSamplePopulations(filters || {});
  const required = requiresSamplePopulation(form, filters || {});
  return (
    <section
      className={`molecular-population-selector${compact ? " compact" : ""}${required ? " needs-selection" : ""}`}
      aria-labelledby="molecular-population-title"
    >
      <div className="molecular-population-heading">
        <span>
          <strong id="molecular-population-title">Molecular population</strong>
          <small>Choose which tissue samples to analyze.</small>
        </span>
        <b>{required ? "Selection required" : summary.label}</b>
      </div>
      {required && (
        <p className="molecular-population-notice" role="status">
          TCGA-SKCM contains primary and metastatic RNA samples. TRACE analyzes
          them as separate biological populations.
        </p>
      )}
      <div
        className="molecular-population-options"
        role="radiogroup"
        aria-label="Molecular population"
      >
        {options.map((population) => {
          const selected = form.filters.sample_population === population.id;
          return (
            <button
              key={population.id}
              type="button"
              role="radio"
              aria-checked={selected}
              className={selected ? "selected" : ""}
              onClick={() => onChange(population.id)}
            >
              <span>
                <strong>{population.label}</strong>
                <small>{population.rationale}</small>
              </span>
              <span className="molecular-population-count">
                {population.patient_count.toLocaleString("en-US")} patients
                <small>
                  {population.sample_count.toLocaleString("en-US")} RNA samples
                </small>
                <small>TCGA {population.allowed_tcga_sample_codes.join("/")}</small>
              </span>
            </button>
          );
        })}
      </div>
      {Number(filters?.sample_population_metadata_conflicts || 0) > 0 && (
        <p className="molecular-population-quality" role="note">
          {filters.sample_population_metadata_conflicts.toLocaleString("en-US")}
          {" "}sample metadata conflict
          {filters.sample_population_metadata_conflicts === 1 ? "" : "s"} excluded:
          {" "}barcode code and recorded
          sample type do not agree.
        </p>
      )}
      <p className="molecular-population-footnote">
        Use separate clinical filters for stage and prior treatment. TRACE uses
        only the selected tissue population; it does not substitute another tumor class or normal tissue.
      </p>
    </section>
  );
}
