export const PUBLIC_ANALYSIS_BATCH_MAX = 25;
export const ROBUSTNESS_GENE_MAX = 50;

import {
  inspectSignatureGeneInput,
  normalizeSignatureInput,
  signatureMethodUsesDirection,
  signatureMethodUsesNumericWeights,
} from "./signatureScoring";

function numericInput(value, {
  label,
  optional = false,
  integer = false,
  minimum = null,
  maximum = null,
  strictMinimum = false,
} = {}) {
  const empty = value === "" || value === null || value === undefined;
  if (empty) {
    return optional
      ? { valid: true, value: null, error: "" }
      : { valid: false, value: null, error: `${label} is required.` };
  }
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) {
    return { valid: false, value: null, error: `${label} must be a number.` };
  }
  if (integer && !Number.isInteger(parsed)) {
    return { valid: false, value: null, error: `${label} must be a whole number.` };
  }
  if (
    minimum !== null
    && (strictMinimum ? parsed <= minimum : parsed < minimum)
  ) {
    return {
      valid: false,
      value: null,
      error: strictMinimum
        ? `${label} must be greater than ${minimum}.`
        : `${label} must be at least ${minimum}.`,
    };
  }
  if (maximum !== null && parsed > maximum) {
    return {
      valid: false,
      value: null,
      error: `${label} must not exceed ${maximum}.`,
    };
  }
  return { valid: true, value: parsed, error: "" };
}

export function percentileInputState(active, value, label = "Percentile threshold") {
  if (!active) return { valid: true, value: null, error: "" };
  return numericInput(value, {
    label,
    minimum: 1,
    maximum: 99,
  });
}

export function analysisFilterState(filters = {}, { includeFollowup = true } = {}) {
  const ageMin = numericInput(filters.age_min, {
    label: "Minimum age",
    optional: true,
    minimum: 0,
    maximum: 150,
  });
  const ageMax = numericInput(filters.age_max, {
    label: "Maximum age",
    optional: true,
    minimum: 0,
    maximum: 150,
  });
  const followup = includeFollowup
    ? numericInput(filters.max_time_days, {
        label: "Maximum follow-up",
        optional: true,
        minimum: 0,
        strictMinimum: true,
        maximum: 3_652_500,
      })
    : { valid: true, value: null, error: "" };
  const errors = [ageMin.error, ageMax.error, followup.error].filter(Boolean);
  if (
    ageMin.valid
    && ageMax.valid
    && ageMin.value !== null
    && ageMax.value !== null
    && ageMin.value > ageMax.value
  ) {
    errors.push("Minimum age cannot exceed maximum age.");
  }

  const customIds = new Set();
  const customFilters = (filters.custom_filters || []).map((filter, index) => {
    const variableId = String(filter.variable_id || "").trim();
    if (!variableId) errors.push(`Restriction ${index + 1} is missing its clinical variable.`);
    if (customIds.has(variableId.toLowerCase())) {
      errors.push("Each clinical variable can be restricted only once.");
    }
    customIds.add(variableId.toLowerCase());
    if (filter.categorical_levels?.length) {
      if (filter.numeric_min != null || filter.numeric_max != null) {
        errors.push(`Restriction ${index + 1} cannot combine levels and a numeric range.`);
      }
      return { ...filter, numeric_min: null, numeric_max: null };
    }
    const label = `Restriction ${index + 1}`;
    const minimum = numericInput(filter.numeric_min, {
      label: `${label} minimum`,
      optional: true,
    });
    const maximum = numericInput(filter.numeric_max, {
      label: `${label} maximum`,
      optional: true,
    });
    if (!minimum.valid) errors.push(minimum.error);
    if (!maximum.valid) errors.push(maximum.error);
    if (minimum.value === null && maximum.value === null) {
      errors.push(`${label} requires at least one level or numeric bound.`);
    }
    if (
      minimum.valid
      && maximum.valid
      && minimum.value !== null
      && maximum.value !== null
      && minimum.value > maximum.value
    ) {
      errors.push(`${label} minimum cannot exceed its maximum.`);
    }
    return {
      ...filter,
      categorical_levels: [],
      numeric_min: minimum.value,
      numeric_max: maximum.value,
    };
  });

  return {
    valid: errors.length === 0,
    errors,
    value: {
      ...filters,
      age_min: ageMin.value,
      age_max: ageMax.value,
      max_time_days: followup.value,
      custom_filters: customFilters,
    },
  };
}

export function plotStyleInputState(style = {}) {
  const base = numericInput(style.base_font_size, {
    label: "Base font size",
    integer: true,
    minimum: 8,
    maximum: 20,
  });
  const axis = numericInput(style.axis_text_size, {
    label: "Axis value size",
    integer: true,
    minimum: 6,
    maximum: 24,
  });
  const title = numericInput(style.axis_title_size, {
    label: "Axis title size",
    integer: true,
    minimum: 6,
    maximum: 26,
  });
  const errors = [base.error, axis.error, title.error].filter(Boolean);
  const palette = style.palette || [];
  const validColor = (value) => /^#[0-9a-f]{6}$/i.test(String(value || ""));
  if (palette.length < 2 || palette.length > 9 || !palette.every(validColor)) {
    errors.push("Plot palette must contain 2 to 9 valid colors.");
  }
  if (!["sans", "serif", "mono"].includes(style.font_family)) {
    errors.push("Choose a supported plot font family.");
  }
  if (!["rectangular", "square"].includes(style.plot_aspect)) {
    errors.push("Choose a supported plot shape.");
  }
  for (const [label, color] of [
    ["Continuous effect color", style.continuous?.effect_color],
    ["Continuous reference color", style.continuous?.reference_color],
    ["Lower hazard color", style.cox_forest?.lower_hazard_color],
    ["Higher hazard color", style.cox_forest?.higher_hazard_color],
    ["Cox reference color", style.cox_forest?.reference_color],
  ]) {
    if (!validColor(color)) errors.push(`${label} is invalid.`);
  }
  const forest = style.cox_forest || {};
  if (
    forest.multivariable_display === "selected"
    && !(forest.multivariable_model_ids || []).length
  ) {
    errors.push("Select at least one multivariable row for the Cox plot.");
  }
  return {
    valid: errors.length === 0,
    errors,
    value: {
      base_font_size: base.value,
      axis_text_size: axis.value,
      axis_title_size: title.value,
    },
  };
}

export function parseSignatureGenesStrict(rawValue) {
  return inspectSignatureGeneInput(rawValue).genes;
}

export function signatureInputState(rawValue, {
  allowWeights = true,
  maximumGenes = null,
  label = "Gene selection",
  method = null,
  methods = null,
} = {}) {
  try {
    const selectedMethods = Array.isArray(methods) && methods.length
      ? [...new Set(methods)]
      : method
        ? [method]
        : [];
    const inspected = inspectSignatureGeneInput(rawValue);
    const hasRankMethod = selectedMethods.some(signatureMethodUsesDirection);
    const meanUsesSharedProjection = selectedMethods.includes("mean")
      && selectedMethods.some((value) =>
        signatureMethodUsesDirection(value)
        || signatureMethodUsesNumericWeights(value),
      );
    const unsignedInput = inspected.genes
      .map((gene) => gene.gene_symbol)
      .join(", ");
    const methodStates = selectedMethods.map((value) =>
      normalizeSignatureInput(
        value === "mean" && meanUsesSharedProjection
          ? unsignedInput
          : rawValue,
        value,
      ),
    );
    const errors = methodStates.flatMap((state) => state.errors);
    const meanIgnoresSignedInput = meanUsesSharedProjection
      && inspected.genes.some((gene) => gene.has_explicit_weight);
    const warnings = [...new Set([
      ...methodStates.flatMap((state) => state.warnings),
      ...(meanIgnoresSignedInput
        ? ["Mean ignores declared directions or coefficients; the other selected methods retain their signed input."]
        : []),
      ...(inspected.duplicates.length && !methodStates.length
        ? [`Duplicate ${inspected.duplicates.join(", ")} ${inspected.duplicates.length === 1 ? "entry was" : "entries were"} ignored; the first occurrence is retained.`]
        : []),
    ])];
    if (!inspected.genes.length && !methodStates.length) {
      errors.push(`${label} requires at least one gene.`);
    }
    if (
      !selectedMethods.length
      && !allowWeights
      && inspected.genes.some((item) => item.has_explicit_weight)
    ) {
      errors.push(`${label} does not use weights. Remove the :weight values.`);
    }
    if (maximumGenes !== null && inspected.genes.length > maximumGenes) {
      errors.push(`${label} accepts at most ${maximumGenes} genes.`);
    }
    const rankMethodIndex = hasRankMethod
      ? selectedMethods.findIndex(signatureMethodUsesDirection)
      : -1;
    const weightedMethodIndex = selectedMethods.findIndex(
      signatureMethodUsesNumericWeights,
    );
    const preservingMethodIndex = rankMethodIndex >= 0
      ? rankMethodIndex
      : weightedMethodIndex >= 0
        ? weightedMethodIndex
        : 0;
    const normalized = methodStates[preservingMethodIndex];
    return {
      valid: errors.length === 0,
      errors: [...new Set(errors.map((error) =>
        error === "Enter at least one gene."
          ? `${label} requires at least one gene.`
          : error,
      ))],
      warnings,
      genes: normalized?.genes
        || inspected.genes.map(({ has_explicit_weight: _ignored, ...gene }) => gene),
      duplicate_queries: inspected.duplicates,
      direction_counts: normalized?.direction_counts || { up: 0, down: 0 },
    };
  } catch (error) {
    return {
      valid: false,
      errors: [error.message],
      warnings: [],
      genes: [],
      duplicate_queries: [],
      direction_counts: { up: 0, down: 0 },
    };
  }
}

export function batchCapacityState(geneCount, methodCount = 1) {
  const analyses = geneCount * methodCount;
  return {
    valid: analyses <= PUBLIC_ANALYSIS_BATCH_MAX,
    analyses,
    maximum: PUBLIC_ANALYSIS_BATCH_MAX,
    maximumGenes: methodCount > 0
      ? Math.floor(PUBLIC_ANALYSIS_BATCH_MAX / methodCount)
      : PUBLIC_ANALYSIS_BATCH_MAX,
    error: analyses <= PUBLIC_ANALYSIS_BATCH_MAX
      ? ""
      : `${analyses} analyses are requested, but one public batch can contain at most ${PUBLIC_ANALYSIS_BATCH_MAX}. Reduce the genes or methods.`,
  };
}

export function panCancerSignatureInputState(rawValue, method = "single") {
  const signatureMethod = method || "single";
  const signature = normalizeSignatureInput(rawValue || "", signatureMethod);
  const canonicalGeneInput = signature.genes.map((gene) => {
    if (signatureMethodUsesDirection(signatureMethod)) {
      return `${gene.gene_symbol}:${gene.direction === "down" ? -1 : 1}`;
    }
    if (signatureMethodUsesNumericWeights(signatureMethod)) {
      return `${gene.gene_symbol}:${gene.weight}`;
    }
    return gene.gene_symbol;
  }).join(", ");
  return {
    ...signature,
    value: {
      gene_symbol: canonicalGeneInput,
      signature_method: signatureMethod,
      signature_genes: signatureMethod === "single" ? [] : signature.genes,
    },
  };
}

export function panCancerInputsFromSurvivalForm(form = {}) {
  if (form.analysis_kind && form.analysis_kind !== "single_signature") {
    return {
      valid: false,
      errors: [
        "Pan-cancer TCGA reference accepts one marker or one signature, not a two-signature interaction or signature panel.",
      ],
      warnings: [],
      genes: [],
      value: null,
    };
  }
  return panCancerSignatureInputState(
    form.gene_symbol || "",
    form.signature_method || "single",
  );
}

export function referencePanCancerInputState(state = {}) {
  const signature = panCancerSignatureInputState(
    state.gene_symbol || "",
    state.signature_method || "single",
  );
  const patients = numericInput(state.min_patients, {
    label: "Minimum patients",
    integer: true,
    minimum: 10,
    maximum: 500,
  });
  const events = numericInput(state.min_events, {
    label: "Minimum events",
    integer: true,
    minimum: 5,
    maximum: 500,
  });
  const fdr = numericInput(state.fdr_threshold, {
    label: "FDR threshold",
    minimum: 0,
    strictMinimum: true,
    maximum: 1,
  });
  const errors = [
    ...signature.errors,
    patients.error,
    events.error,
    fdr.error,
  ].filter(Boolean);
  return {
    valid: errors.length === 0,
    errors,
    warnings: signature.warnings,
    genes: signature.genes,
    direction_counts: signature.direction_counts,
    value: {
      ...signature.value,
      min_patients: patients.value,
      min_events: events.value,
      fdr_threshold: fdr.value,
    },
  };
}

export function hierarchicalThresholdState(state = {}) {
  const rules = [
    ["min_patients", "Minimum patients", 20],
    ["min_events", "Minimum events", 10],
    ["min_censored", "Minimum censored patients", 5],
  ];
  const value = {};
  const errors = [];
  for (const [key, label, minimum] of rules) {
    const checked = numericInput(state[key], {
      label,
      integer: true,
      minimum,
      maximum: 500,
    });
    value[key] = checked.value;
    if (!checked.valid) errors.push(checked.error);
  }
  const fdr = numericInput(state.fdr_threshold, {
    label: "FDR threshold",
    minimum: 0,
    strictMinimum: true,
    maximum: 1,
  });
  value.fdr_threshold = fdr.value;
  if (!fdr.valid) errors.push(fdr.error);
  return { valid: errors.length === 0, errors, value };
}
