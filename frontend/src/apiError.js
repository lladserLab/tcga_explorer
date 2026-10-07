import { RANK_SCORING_UNAVAILABLE_MESSAGE } from "./signatureScoring";

const FIELD_LABELS = Object.freeze({
  adjustment_covariates: "Clinical adjustment",
  age_max: "Maximum age",
  age_min: "Minimum age",
  cohort: "Cancer cohort",
  custom_filters: "Additional patient restrictions",
  custom_percentile: "Percentile threshold",
  cutpoint_methods: "Cutpoint methods",
  dataset_id: "Dataset",
  dataset_release_id: "Dataset release",
  endpoints: "Survival endpoints",
  event_column: "Event status",
  expression_layer_id: "Expression layer",
  expression_scale: "Expression scale",
  external_adjustment_covariates: "Uploaded adjustment variables",
  filters: "Patient filters",
  genes: "Genes",
  levels: "Selected levels",
  max_time_days: "Maximum follow-up",
  multivariable_model_ids: "Multivariable rows",
  sample_population: "Molecular population",
  scoring_methods: "Scoring methods",
  time_unit: "Time unit",
});

function sentence(value) {
  const normalized = String(value || "")
    .replace(/^Value error,\s*/i, "")
    .replace(/^Input should be\s*/i, "Must be ")
    .trim();
  if (!normalized) return "Check this value.";
  const capitalized = normalized[0].toUpperCase() + normalized.slice(1);
  return /[.!?]$/.test(capitalized) ? capitalized : `${capitalized}.`;
}

function fieldLabel(location = []) {
  const parts = location
    .filter((part) => !["body", "query", "path", "request"].includes(String(part)))
    .filter((part) => !["__root__", "root"].includes(String(part)));
  const named = [...parts].reverse().find((part) => typeof part === "string");
  if (!named) return "Analysis design";
  return FIELD_LABELS[named]
    || String(named).replaceAll("_", " ").replace(/^./, (character) => character.toUpperCase());
}

export function validationErrorItems(error) {
  const errors = error?.details?.errors;
  if (!Array.isArray(errors)) return [];
  return errors.map((item) => ({
    field: fieldLabel(item?.loc),
    message: sentence(item?.msg),
  }));
}

export function formatApiError(error, { context = "" } = {}) {
  if (!error) return "";
  if (error.code === "DATASET_CAPABILITY_UNAVAILABLE") {
    return error.message || "The selected dataset does not support this analysis.";
  }
  if (/transcriptome[- ]wide|broad expression layer|gene universe.*unavailable/i.test(
    String(error.message || ""),
  )) {
    return RANK_SCORING_UNAVAILABLE_MESSAGE;
  }
  if ([
    "HOURLY_LIMIT",
    "CLIENT_ACTIVE_LIMIT",
    "QUEUE_FULL",
    "HTTP_429",
  ].includes(error.code)) {
    return error.message || "The analysis service is busy. Try again later.";
  }
  if (error.code === "VALIDATION_ERROR") {
    const items = validationErrorItems(error);
    if (items.length) {
      const visible = items
        .slice(0, 3)
        .map(({ field, message }) => `${field}: ${message}`)
        .join(" ");
      const remaining = items.length - 3;
      return `${visible}${remaining > 0 ? ` ${remaining} more setting${remaining === 1 ? " needs" : "s need"} review.` : ""}`;
    }
    return `${context || "The analysis"} settings could not be validated. Review the current selections and try again.`;
  }
  const labels = {
    INVALID_GROUPS: "Invalid grouping",
    INSUFFICIENT_PATIENTS: "Not enough patients",
    NO_EVENTS: "No survival events",
    NO_GENE: "Gene not found",
    CACHE_INCOMPLETE: "Saved result incomplete",
    R_FAILED: "Analysis engine failed",
    ENDPOINT_UNAVAILABLE: "Endpoint unavailable",
    INVALID_ANALYSIS: "Invalid analysis",
  };
  if (!error.code) return error.message || "The request could not be completed.";
  return `${labels[error.code] || error.code}: ${error.message || "The request could not be completed."}`;
}
