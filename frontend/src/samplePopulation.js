export const SAMPLE_POPULATION_CONTRACT_VERSION = "tcga-molecular-population-v1.1";

export function defaultSamplePopulation(cohort, datasetId = null) {
  if (!cohort || datasetId) return null;
  if (cohort === "TCGA-SKCM") return null;
  if (cohort === "TCGA-LAML") return "primary_blood";
  return "primary_solid";
}

export function samplePopulationLabel(value, options = []) {
  if (!value) return "Choose a molecular population";
  if (value === "primary_disease") return "Primary disease tissue";
  return options.find((option) => option.id === value)?.label
    || value.replaceAll("_", " ");
}

export function availableSamplePopulations(filters = {}) {
  return (filters.sample_populations || []).filter(
    (population) => population.available,
  );
}

export function requiresSamplePopulation(form = {}, filters = {}) {
  return Boolean(
    form.cohort
    && !form.dataset_id
    && filters.population_selection_required
    && !form.filters?.sample_population,
  );
}

export function molecularPopulationSummary(form = {}, filters = {}) {
  if (form.dataset_id) {
    return {
      label: "Curated release population",
      detail: "Patients and samples follow the eligibility rules of this release.",
      blocking: false,
    };
  }
  const selected = (filters.sample_populations || []).find(
    (population) => population.id === form.filters?.sample_population,
  );
  if (!selected) {
    return {
      label: "Population required",
      detail: "Choose which tissue should represent each patient.",
      blocking: true,
    };
  }
  return {
    label: selected.label,
    detail: `${selected.patient_count.toLocaleString("en-US")} patients · TCGA ${selected.allowed_tcga_sample_codes.join("/")}`,
    blocking: false,
  };
}
