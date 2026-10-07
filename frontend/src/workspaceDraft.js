import {
  PUBLIC_ANALYSIS_BATCH_MAX,
  ROBUSTNESS_GENE_MAX,
  analysisFilterState,
  hierarchicalThresholdState,
  referencePanCancerInputState,
} from "./analysisRequestContract";

export const WORKSPACE_DRAFT_STORAGE_KEY = "trace-explorer-workspace-draft-v1";
const ANALYSIS_PAGES = new Set([
  "analysis",
  "compare",
  "expression",
  "gsea",
  "multiverse",
  "pancancer",
]);

function safeStorage(storage) {
  if (storage !== undefined) return storage;
  try {
    return globalThis.localStorage || null;
  } catch {
    return null;
  }
}

function withoutRuntime(state = {}, extra = []) {
  const omitted = new Set([
    "running",
    "result",
    "error",
    "hierarchicalRunning",
    "hierarchicalResult",
    "hierarchicalError",
    "hierarchicalPreflight",
    "hierarchicalPreflightStatus",
    "hierarchicalPreflightError",
    "immuneScreen",
    "immuneScreenLoading",
    "immuneScreenError",
    "geneSuggestions",
    "result_context_fingerprint",
    ...extra,
  ]);
  return Object.fromEntries(
    Object.entries(state).filter(([key]) => !omitted.has(key)),
  );
}

function publicForm(form = {}) {
  const privateDataset = String(form.dataset_id || "").startsWith("user-");
  return {
    cohort: form.cohort || "",
    dataset_id: privateDataset ? null : form.dataset_id || null,
    dataset_release_id: privateDataset ? null : form.dataset_release_id || null,
    expression_layer_id: privateDataset ? null : form.expression_layer_id || null,
    gene_symbol: form.gene_symbol || "",
    analysis_kind: form.analysis_kind,
    endpoint: form.endpoint,
    signature_method: form.signature_method,
    signature_genes: form.signature_genes || [],
    combined_signature: form.combined_signature,
    signature_panel: form.signature_panel,
    expression_scale: form.expression_scale,
    cutpoint_method: form.cutpoint_method,
    custom_percentile: form.custom_percentile,
    time_unit: form.time_unit,
    show_confidence_interval: form.show_confidence_interval,
    show_risk_table: form.show_risk_table,
    plot_style: form.plot_style,
    filters: privateDataset ? undefined : form.filters,
    adjustment_covariates: privateDataset ? [] : form.adjustment_covariates,
    external_covariates: null,
    external_adjustment_covariates: [],
  };
}

function meaningful({ form, compare, expressionComparison, gsea, multiverse, panCancer }) {
  return Boolean(
    form?.cohort
    || form?.gene_symbol
    || compare?.genes
    || expressionComparison?.genes?.length
    || gsea?.signature_genes
    || multiverse?.genes
    || panCancer?.gene_symbol
  );
}

function boundedGeneText(value, maximum) {
  return String(value || "")
    .split(/[,+;\n]/)
    .map((item) => item.trim())
    .filter(Boolean)
    .slice(0, maximum)
    .join(", ");
}

function validNumber(value, minimum, maximum, fallback) {
  const numeric = Number(value);
  return Number.isFinite(numeric) && numeric >= minimum && numeric <= maximum
    ? numeric
    : fallback;
}

function sanitizedPlotStyle(style = {}) {
  const forest = style.cox_forest || {};
  const modelIds = (forest.multivariable_model_ids || []).filter((value) => [
    "stage_adjusted",
    "grade_adjusted",
    "stage_grade_adjusted",
    "user_adjusted",
  ].includes(value));
  return {
    ...style,
    base_font_size: validNumber(style.base_font_size, 8, 20, 12),
    axis_text_size: validNumber(style.axis_text_size, 6, 24, 11),
    axis_title_size: validNumber(style.axis_title_size, 6, 26, 12),
    cox_forest: {
      ...forest,
      multivariable_display:
        forest.multivariable_display === "selected" ? "selected" : "all",
      multivariable_model_ids: modelIds.length
        ? [...new Set(modelIds)]
        : [
            "stage_adjusted",
            "grade_adjusted",
            "stage_grade_adjusted",
            "user_adjusted",
          ],
    },
  };
}

export function sanitizeWorkspaceDraft(draft) {
  if (!draft || draft.schema_version !== "trace-workspace-draft-v1") return null;
  const form = draft.form || {};
  const normalizedFilters = analysisFilterState(form.filters || {});
  const filters = normalizedFilters.valid
    ? normalizedFilters.value
    : {
        ...(form.filters || {}),
        age_min: "",
        age_max: "",
        max_time_days: "",
        custom_filters: (form.filters?.custom_filters || []).filter((filter) => {
          if (filter.categorical_levels?.length) return true;
          if (filter.numeric_min == null && filter.numeric_max == null) return false;
          return !(
            filter.numeric_min != null
            && filter.numeric_max != null
            && Number(filter.numeric_min) > Number(filter.numeric_max)
          );
        }),
      };
  const panCancer = draft.panCancer || {};
  const reference = referencePanCancerInputState(panCancer);
  const hierarchy = hierarchicalThresholdState(panCancer.hierarchicalRequest || {});
  return {
    ...draft,
    active_page: ANALYSIS_PAGES.has(draft.active_page)
      ? draft.active_page
      : "analysis",
    form: {
      ...form,
      gene_symbol: boundedGeneText(form.gene_symbol, PUBLIC_ANALYSIS_BATCH_MAX),
      custom_percentile: validNumber(form.custom_percentile, 1, 99, 60),
      filters,
      plot_style: sanitizedPlotStyle(form.plot_style),
    },
    compare: {
      genes: boundedGeneText(draft.compare?.genes, PUBLIC_ANALYSIS_BATCH_MAX),
      methods: [...new Set(draft.compare?.methods || [])].filter((value) => [
        "maxstat",
        "median",
        "upper_quartile",
        "upper_lower_quartile",
        "percentile",
      ].includes(value)),
    },
    expressionComparison: {
      ...(draft.expressionComparison || {}),
      genes: (draft.expressionComparison?.genes || []).slice(0, 25),
    },
    multiverse: {
      ...(draft.multiverse || {}),
      genes: boundedGeneText(draft.multiverse?.genes, ROBUSTNESS_GENE_MAX),
    },
    panCancer: {
      ...panCancer,
      ...(reference.valid
        ? reference.value
        : { min_patients: 10, min_events: 5, fdr_threshold: 0.1 }),
      hierarchicalRequest: {
        ...(panCancer.hierarchicalRequest || {}),
        ...(hierarchy.valid
          ? hierarchy.value
          : {
              min_patients: 20,
              min_events: 10,
              min_censored: 5,
              fdr_threshold: 0.05,
            }),
      },
    },
  };
}

export function createWorkspaceDraft({
  activePage,
  form,
  compare,
  expressionComparison,
  gsea,
  multiverse,
  panCancer,
}) {
  if (!meaningful({ form, compare, expressionComparison, gsea, multiverse, panCancer })) {
    return null;
  }
  const page = ANALYSIS_PAGES.has(activePage) ? activePage : "analysis";
  const sanitizedForm = publicForm(form);
  const privateDataset = String(form?.dataset_id || "").startsWith("user-");
  return {
    schema_version: "trace-workspace-draft-v1",
    saved_at: new Date().toISOString(),
    active_page: page,
    summary: [
      sanitizedForm.cohort,
      sanitizedForm.gene_symbol,
      sanitizedForm.endpoint,
    ].filter(Boolean).join(" · ") || "Configured analysis",
    form: sanitizedForm,
    // Result identity can contain private clinical input. Persist controls only.
    compare: { genes: compare?.genes || "", methods: compare?.methods || [] },
    expressionComparison: privateDataset
      ? withoutRuntime(expressionComparison, [
          "clinical_variable",
          "group_a_values",
          "group_b_values",
          "group_a_label",
          "group_b_label",
        ])
      : withoutRuntime(expressionComparison),
    gsea: privateDataset
      ? withoutRuntime(gsea, [
          "clinical_variable",
          "group_a_values",
          "group_b_values",
          "group_a_label",
          "group_b_label",
        ])
      : withoutRuntime(gsea),
    multiverse: withoutRuntime(multiverse),
    panCancer: withoutRuntime(panCancer),
  };
}

export function loadWorkspaceDraft(storage) {
  const resolvedStorage = safeStorage(storage);
  try {
    const parsed = JSON.parse(
      resolvedStorage?.getItem?.(WORKSPACE_DRAFT_STORAGE_KEY) || "null",
    );
    return sanitizeWorkspaceDraft(parsed);
  } catch {
    return null;
  }
}

export function persistWorkspaceDraft(draft, storage) {
  const resolvedStorage = safeStorage(storage);
  try {
    if (!resolvedStorage) return false;
    if (!draft) {
      resolvedStorage.removeItem?.(WORKSPACE_DRAFT_STORAGE_KEY);
      return true;
    }
    resolvedStorage.setItem(WORKSPACE_DRAFT_STORAGE_KEY, JSON.stringify(draft));
    return true;
  } catch {
    return false;
  }
}

export function clearWorkspaceDraft(storage) {
  return persistWorkspaceDraft(null, storage);
}
