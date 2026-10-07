import { analysisFilterState } from "../analysisRequestContract";
import { normalizeSignatureInput } from "../signatureScoring";

export const GSEA_GROUP_SOURCES = [
  {
    value: "clinical",
    label: "Clinical variable",
    note: "Choose clinical categories for each group. The same category cannot belong to both groups.",
  },
  {
    value: "survival",
    label: "Survival groups",
    note: "Reuse the exact patient assignments from a completed two-group survival analysis.",
  },
  {
    value: "expression",
    label: "Gene expression",
    note: "Define high and low groups from one gene or a signature score. Survival data are not required.",
  },
];

export const GSEA_CLINICAL_VARIABLES = [
  { value: "stage", label: "Stage", optionsKey: "stages" },
  { value: "grade", label: "Grade", optionsKey: "grades" },
  { value: "gender", label: "Gender", optionsKey: "genders" },
  { value: "race", label: "Race", optionsKey: "races" },
  { value: "age_at_index", label: "Age at diagnosis", optionsKey: null },
];

const CLINICAL_CATEGORY_LABELS = {
  standardized: "Standardized variables",
  clinical: "Clinical variables",
  tumor_specific: "Published tumor annotations",
  dataset_specific: "Source-specific variables",
};

export function clinicalGroupingVariables(filters = {}) {
  const catalog = filters?.clinical_grouping_variables;
  if (Array.isArray(catalog) && catalog.length) {
    return catalog.map((item) => ({
      ...item,
      id: item.id || item.value,
      value: item.id || item.value,
      label: item.label || item.id || item.value,
      value_type: item.value_type || "categorical",
      category: item.category || "clinical",
      category_label:
        CLINICAL_CATEGORY_LABELS[item.category] || "Clinical variables",
      levels: Array.isArray(item.levels) ? item.levels : [],
      analysis_eligible: item.analysis_eligible !== false,
    }));
  }
  return GSEA_CLINICAL_VARIABLES.map((item) => {
    const levels = item.optionsKey
      ? [...new Set(filters?.[item.optionsKey] || [])]
      : [];
    const numericAvailable =
      item.value === "age_at_index" &&
      (filters?.age_min != null || filters?.age_max != null);
    return {
      ...item,
      id: item.value,
      value_type: item.value === "age_at_index" ? "numeric" : "categorical",
      category: "standardized",
      category_label: CLINICAL_CATEGORY_LABELS.standardized,
      source: "Standardized dataset metadata",
      source_field: item.value,
      levels: levels.map((value) => ({
        value,
        label: value,
        count: null,
        analysis_eligible: true,
        unavailable_reason: null,
      })),
      analysis_eligible: item.optionsKey ? levels.length > 1 : numericAvailable,
      non_missing_count: null,
      patient_count: null,
      coverage: null,
    };
  });
}

export function clinicalVariableDefinition(filters, variable) {
  return clinicalGroupingVariables(filters).find(
    (item) => item.value === variable,
  );
}

export function clinicalVariableLevelOptions(filters, variable) {
  const definition = clinicalVariableDefinition(filters, variable);
  return (definition?.levels || []).map((level) =>
    typeof level === "string"
      ? {
          value: level,
          label: level,
          count: null,
          analysis_eligible: true,
          unavailable_reason: null,
        }
      : {
          value: level.value,
          label: level.label || level.value,
          count: level.count ?? null,
          analysis_eligible: level.analysis_eligible !== false,
          unavailable_reason: level.unavailable_reason || null,
        },
  );
}

export const GSEA_EXPRESSION_CUTPOINTS = [
  { value: "median", label: "Median", note: "Uses all eligible samples." },
  {
    value: "upper_quartile",
    label: "Upper quartile",
    note: "Compares the top 25% with the remaining 75%.",
  },
  {
    value: "upper_lower_quartile",
    label: "Outer quartiles",
    note: "Compares the top and bottom quartiles; the middle half is excluded.",
  },
  {
    value: "percentile",
    label: "Percentile",
    note: "Uses a declared score percentile as the threshold.",
  },
];

export const ELIGIBLE_SURVIVAL_CUTPOINTS = new Set([
  "maxstat",
  "median",
  "upper_quartile",
  "upper_lower_quartile",
  "percentile",
]);

export function createDefaultGseaState() {
  return {
    grouping_source: "clinical",
    clinical_variable: "stage",
    group_a_label: "Reference",
    group_b_label: "Target",
    group_a_values: [],
    group_b_values: [],
    clinical_cutpoint_method: "median",
    clinical_cutpoint: "",
    survival_analysis_id: "",
    survival_group_a: "",
    survival_group_b: "",
    signature_name: "",
    signature_genes: "",
    signature_method: "single",
    cutpoint_method: "median",
    custom_percentile: 75,
    gene_set_collection: "immport",
    ranking_metric: "welch_t",
    min_gene_set_size: 15,
    max_gene_set_size: 500,
    permutations: 1000,
    seed: 17291,
    fdr_threshold: 0.25,
    running: false,
    result: null,
    error: "",
  };
}

export function clinicalVariableLevels(filters, variable) {
  return clinicalVariableLevelOptions(filters, variable).map(
    (item) => item.value,
  );
}

export function eligibleSurvivalAnalyses(analyses = []) {
  return analyses
    .map((analysis) => {
      const groups = Object.keys(analysis?.metrics?.group_counts || {});
      return {
        analysis,
        groups,
        eligible:
          analysis?.status === "completed" &&
          ELIGIBLE_SURVIVAL_CUTPOINTS.has(analysis?.cutpoint_method) &&
          groups.length === 2,
      };
    })
    .filter((item) => item.eligible);
}

export function chooseSurvivalContrast(groups = []) {
  if (groups.length !== 2) {
    return { groupA: "", groupB: "" };
  }
  const high = groups.find((value) => value.toLowerCase() === "high");
  if (high) {
    return {
      groupA: groups.find((value) => value !== high) || "",
      groupB: high,
    };
  }
  return { groupA: groups[0], groupB: groups[1] };
}

export function toggleDisjointGroupValue(state, groupKey, value) {
  const ownKey = groupKey === "a" ? "group_a_values" : "group_b_values";
  const otherKey = groupKey === "a" ? "group_b_values" : "group_a_values";
  const selected = state[ownKey].includes(value);
  return {
    ...state,
    [ownKey]: selected
      ? state[ownKey].filter((item) => item !== value)
      : [...state[ownKey], value],
    [otherKey]: selected
      ? state[otherKey]
      : state[otherKey].filter((item) => item !== value),
    result: null,
    error: "",
  };
}

export function parseSignatureGenes(rawValue, method) {
  const result = normalizeSignatureInput(rawValue, method);
  if (!result.valid) throw new Error(result.errors[0]);
  return result.genes;
}

function normalizeFilters(filters = {}) {
  const normalized = analysisFilterState(filters, { includeFollowup: false }).value;
  return {
    sample_population: normalized.sample_population || null,
    sample_types: normalized.sample_types || [],
    stages: normalized.stages || [],
    grades: normalized.grades || [],
    genders: normalized.genders || [],
    races: normalized.races || [],
    age_min: normalized.age_min,
    age_max: normalized.age_max,
    max_time_days: null,
    custom_filters: normalized.custom_filters || [],
  };
}

export function validateGseaState(state, filters = {}, form = {}) {
  const errors = [];
  errors.push(...analysisFilterState(form.filters || {}, { includeFollowup: false }).errors);
  if (form.cohort && !form.dataset_id && !form.filters?.sample_population) {
    errors.push("Choose the molecular population that should represent each patient.");
  }
  if (!state.group_a_label.trim() || !state.group_b_label.trim()) {
    errors.push("Name both groups.");
  } else if (
    state.group_a_label.trim().toLowerCase() ===
    state.group_b_label.trim().toLowerCase()
  ) {
    errors.push("Group labels must be different.");
  }

  if (state.grouping_source === "clinical") {
    const definition = clinicalVariableDefinition(
      filters,
      state.clinical_variable,
    );
    const numericVariable =
      definition?.value_type === "numeric" ||
      (!definition && state.clinical_variable === "age_at_index");
    if (!state.clinical_variable) {
      errors.push("Choose a clinical variable.");
    } else if (
      (form.filters?.custom_filters || []).some(
        (filter) => filter.variable_id === state.clinical_variable,
      )
    ) {
      errors.push(
        "A clinical variable cannot define the groups and restrict eligibility at the same time.",
      );
    } else if (numericVariable) {
      const cutpoint = Number(state.clinical_cutpoint);
      const minimum = Number(
        definition?.numeric_summary?.min ??
          (state.clinical_variable === "age_at_index" ? 0 : Number.NaN),
      );
      const maximum = Number(
        definition?.numeric_summary?.max ??
          (state.clinical_variable === "age_at_index" ? 120 : Number.NaN),
      );
      if (
        state.clinical_cutpoint_method === "value" &&
        (
          String(state.clinical_cutpoint).trim() === "" ||
          !Number.isFinite(cutpoint) ||
          (Number.isFinite(minimum) && cutpoint < minimum) ||
          (Number.isFinite(maximum) && cutpoint > maximum)
        )
      ) {
        const range =
          Number.isFinite(minimum) && Number.isFinite(maximum)
            ? ` from ${minimum} to ${maximum}`
            : "";
        errors.push(`Enter a numeric cutpoint${range}.`);
      }
    } else if (
      !state.group_a_values.length ||
      !state.group_b_values.length
    ) {
      errors.push("Select at least one clinical level for each group.");
    }
  }

  if (state.grouping_source === "survival") {
    if (!state.survival_analysis_id.trim()) {
      errors.push("Choose or enter a completed survival analysis ID.");
    }
    if (
      Boolean(state.survival_group_a) !== Boolean(state.survival_group_b)
    ) {
      errors.push("Select both source survival groups.");
    }
  }

  if (state.grouping_source === "expression") {
    try {
      const signatureGenes = parseSignatureGenes(
        state.signature_genes,
        state.signature_method,
      );
      if (!signatureGenes.length) {
        errors.push("Enter at least one gene for expression grouping.");
      }
    } catch (error) {
      errors.push(
        error.message === "Single-gene scoring requires exactly one gene."
          ? "Single-gene grouping requires exactly one gene."
          : error.message,
      );
    }
    if (
      state.cutpoint_method === "percentile" &&
      (!Number.isFinite(Number(state.custom_percentile)) ||
        Number(state.custom_percentile) < 1 ||
        Number(state.custom_percentile) > 99)
    ) {
      errors.push("Expression percentile must be between 1 and 99.");
    }
  }

  const minSize = Number(state.min_gene_set_size);
  const maxSize = Number(state.max_gene_set_size);
  if (!Number.isInteger(minSize) || minSize < 5 || minSize > 500) {
    errors.push("Minimum gene-set size must be an integer from 5 to 500.");
  }
  if (
    !Number.isInteger(maxSize) ||
    maxSize < 10 ||
    maxSize > 5000 ||
    maxSize < minSize
  ) {
    errors.push(
      "Maximum gene-set size must be an integer from 10 to 5000 and at least the minimum.",
    );
  }
  const permutations = Number(state.permutations);
  if (
    !Number.isInteger(permutations) ||
    permutations < 100 ||
    permutations > 5000
  ) {
    errors.push("Permutations must be an integer from 100 to 5000.");
  }
  const seed = Number(state.seed);
  if (
    !Number.isInteger(seed) ||
    seed < 0 ||
    seed > 2147483647
  ) {
    errors.push("Seed must be an integer from 0 to 2147483647.");
  }
  return { valid: errors.length === 0, errors };
}

export function buildGseaPayload(state, form) {
  const signatureGenes =
    state.grouping_source === "expression"
      ? parseSignatureGenes(state.signature_genes, state.signature_method)
      : [];
  const grouping = {
    source: state.grouping_source,
    group_a_label: state.group_a_label.trim(),
    group_b_label: state.group_b_label.trim(),
    clinical_variable:
      state.grouping_source === "clinical"
        ? state.clinical_variable
        : null,
    group_a_values:
      state.grouping_source === "clinical"
        ? state.group_a_values
        : state.grouping_source === "survival" && state.survival_group_a
          ? [state.survival_group_a]
          : [],
    group_b_values:
      state.grouping_source === "clinical"
        ? state.group_b_values
        : state.grouping_source === "survival" && state.survival_group_b
          ? [state.survival_group_b]
          : [],
    clinical_cutpoint_method: state.clinical_cutpoint_method,
    clinical_cutpoint:
      state.clinical_cutpoint_method === "value" &&
      state.clinical_cutpoint !== ""
        ? Number(state.clinical_cutpoint)
        : null,
    survival_analysis_id:
      state.grouping_source === "survival"
        ? state.survival_analysis_id.trim()
        : null,
    signature:
      state.grouping_source === "expression"
        ? {
            name: state.signature_name.trim(),
            gene_symbol: signatureGenes
              .map((item) => item.gene_symbol)
              .join(","),
            signature_method: state.signature_method,
            signature_genes: signatureGenes,
          }
        : null,
    cutpoint_method: state.cutpoint_method,
    custom_percentile:
      state.cutpoint_method === "percentile"
        ? Number(state.custom_percentile)
        : null,
  };
  return {
    cohort: form.cohort,
    dataset_id: form.dataset_id || null,
    dataset_release_id: form.dataset_release_id || null,
    expression_layer_id: form.expression_layer_id || null,
    expression_scale: form.expression_scale || "log2_tpm",
    filters: normalizeFilters(form.filters),
    grouping,
    gene_set_collection: state.gene_set_collection,
    ranking_metric: state.ranking_metric,
    min_gene_set_size: Number(state.min_gene_set_size),
    max_gene_set_size: Number(state.max_gene_set_size),
    permutations: Number(state.permutations),
    seed: Number(state.seed),
    fdr_threshold: Number(state.fdr_threshold),
  };
}
