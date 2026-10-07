import {
  clinicalVariableDefinition,
  parseSignatureGenes,
} from "../gsea/gseaContract";
import { analysisFilterState } from "../analysisRequestContract";

export const EXPRESSION_COMPARISON_MAX_GENES = 25;
export const EXPRESSION_COMPARISON_FDR_THRESHOLD = 0.05;
export const EXPRESSION_COMPARISON_HEATMAP_MAX_SAMPLES = 300;

export function createDefaultExpressionComparisonState() {
  return {
    genes: [],
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
    fdr_threshold: EXPRESSION_COMPARISON_FDR_THRESHOLD,
    heatmap_max_samples: EXPRESSION_COMPARISON_HEATMAP_MAX_SAMPLES,
    context_epoch: 0,
    running: false,
    result: null,
    result_context_fingerprint: "",
    error: "",
  };
}

export function normalizeExpressionGenes(values = []) {
  const seen = new Set();
  const normalized = [];
  for (const value of values) {
    const symbol = String(value || "").trim().toUpperCase();
    if (!symbol || seen.has(symbol)) continue;
    seen.add(symbol);
    normalized.push(symbol);
  }
  return normalized;
}

export function expressionComparisonContextFingerprint(form = {}) {
  return JSON.stringify({
    cohort: form.cohort || "",
    dataset_id: form.dataset_id || null,
    dataset_release_id: form.dataset_release_id || null,
    expression_layer_id: form.expression_layer_id || null,
    expression_scale: form.expression_scale || "log2_tpm",
    filters: normalizeFilters(form.filters),
  });
}

export function expressionGroupingGeneSymbols(state) {
  if (state.grouping_source !== "expression") return [];
  try {
    return parseSignatureGenes(
      state.signature_genes,
      state.signature_method,
    ).map((entry) => entry.gene_symbol);
  } catch {
    return [];
  }
}

export function circularTargetGenes(state) {
  const groupingGenes = new Set(expressionGroupingGeneSymbols(state));
  return normalizeExpressionGenes(state.genes).filter((gene) =>
    groupingGenes.has(gene),
  );
}

export function validateExpressionComparisonState(
  state,
  form = {},
  filters = {},
) {
  const errors = [];
  errors.push(...analysisFilterState(form.filters || {}, { includeFollowup: false }).errors);
  const genes = normalizeExpressionGenes(state.genes);
  if (!form.cohort) {
    errors.push("Select a dataset.");
  }
  if (form.cohort && !form.dataset_id && !form.filters?.sample_population) {
    errors.push("Choose the molecular population that should represent each patient.");
  }
  if (!genes.length) {
    errors.push("Add at least one target gene.");
  }
  if (genes.length > EXPRESSION_COMPARISON_MAX_GENES) {
    errors.push(
      `Select no more than ${EXPRESSION_COMPARISON_MAX_GENES} target genes.`,
    );
  }

  const groupALabel = String(state.group_a_label || "").trim();
  const groupBLabel = String(state.group_b_label || "").trim();
  if (!groupALabel || !groupBLabel) {
    errors.push("Name both groups.");
  } else if (groupALabel.toLowerCase() === groupBLabel.toLowerCase()) {
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
        (String(state.clinical_cutpoint).trim() === "" ||
          !Number.isFinite(cutpoint) ||
          (Number.isFinite(minimum) && cutpoint < minimum) ||
          (Number.isFinite(maximum) && cutpoint > maximum))
      ) {
        const range =
          Number.isFinite(minimum) && Number.isFinite(maximum)
            ? ` from ${minimum} to ${maximum}`
            : "";
        errors.push(`Enter a numeric cutpoint${range}.`);
      }
    } else if (!state.group_a_values.length || !state.group_b_values.length) {
      errors.push("Select at least one clinical level for each group.");
    }
  } else if (state.grouping_source === "survival") {
    if (!String(state.survival_analysis_id || "").trim()) {
      errors.push("Choose or enter a completed survival analysis ID.");
    }
    if (Boolean(state.survival_group_a) !== Boolean(state.survival_group_b)) {
      errors.push("Select both source survival groups.");
    }
  } else if (state.grouping_source === "expression") {
    try {
      const signatureGenes = parseSignatureGenes(
        state.signature_genes,
        state.signature_method,
      );
      if (!signatureGenes.length) {
        errors.push("Enter at least one gene for expression grouping.");
      }
      if (state.signature_method === "single" && signatureGenes.length !== 1) {
        errors.push("Single-gene grouping requires exactly one gene.");
      }
    } catch (error) {
      errors.push(error.message);
    }
    if (
      state.cutpoint_method === "percentile" &&
      (!Number.isFinite(Number(state.custom_percentile)) ||
        Number(state.custom_percentile) < 1 ||
        Number(state.custom_percentile) > 99)
    ) {
      errors.push("Expression percentile must be between 1 and 99.");
    }
  } else {
    errors.push("Choose a supported group source.");
  }

  return {
    valid: errors.length === 0,
    errors,
    circular_genes: circularTargetGenes(state),
  };
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

export function buildExpressionComparisonGrouping(state) {
  const signatureGenes =
    state.grouping_source === "expression"
      ? parseSignatureGenes(state.signature_genes, state.signature_method)
      : [];
  return {
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
              .map((entry) => entry.gene_symbol)
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
}

export function buildExpressionComparisonPayload(state, form) {
  return {
    cohort: form.cohort,
    dataset_id: form.dataset_id || null,
    dataset_release_id: form.dataset_release_id || null,
    expression_layer_id: form.expression_layer_id || null,
    expression_scale: form.expression_scale || "log2_tpm",
    filters: normalizeFilters(form.filters),
    genes: normalizeExpressionGenes(state.genes),
    grouping: buildExpressionComparisonGrouping(state),
    fdr_threshold: EXPRESSION_COMPARISON_FDR_THRESHOLD,
    heatmap_max_samples: EXPRESSION_COMPARISON_HEATMAP_MAX_SAMPLES,
  };
}
