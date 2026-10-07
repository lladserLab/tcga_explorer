/**
 * Tutorial presets are declarative local-state plans. They never fetch data or
 * execute an analysis. Every plan lists the derived result scopes it invalidates.
 */

const DERIVED_RESULT_RESETS = Object.freeze({
  survival: Object.freeze({
    analysisResults: [],
    loading: false,
    error: "",
  }),
  compare: Object.freeze({
    compare: { running: false, results: [], error: "", active_run_id: null, result_context: null, grouped_family: null },
  }),
  expression: Object.freeze({
    expressionComparison: {
      running: false,
      result: null,
      result_context_fingerprint: "",
      error: "",
    },
  }),
  gsea: Object.freeze({
    gsea: { running: false, result: null, error: "" },
  }),
  multiverse: Object.freeze({
    multiverse: { running: false, result: null, error: "" },
  }),
  pancancer: Object.freeze({
    panCancer: {
      running: false,
      result: null,
      error: "",
      hierarchicalPreflight: null,
      hierarchicalPreflightStatus: "idle",
      hierarchicalPreflightError: "",
      hierarchicalResult: null,
      hierarchicalRunning: false,
      hierarchicalError: "",
    },
  }),
});

const SHARED_CONTEXT_SCOPES = Object.freeze([
  "survival",
  "compare",
  "expression",
  "gsea",
  "multiverse",
  "pancancer",
]);

export const TUTORIAL_PRESETS = Object.freeze({
  "included-lihc-cdc20-os": Object.freeze({
    id: "included-lihc-cdc20-os",
    targetView: "analysis",
    patches: {
      activePage: "analysis",
      dataSourceMode: "catalog",
      analysisStep: 0,
      form: {
        cohort: "TCGA-LIHC",
        dataset_id: null,
        dataset_release_id: null,
        expression_layer_id: null,
        gene_symbol: "CDC20",
        analysis_kind: "single_signature",
        endpoint: "OS",
        signature_method: "single",
        signature_genes: [],
        expression_scale: "log2_tpm",
        cutpoint_method: "median",
        time_unit: "days",
        filters: {
          sample_types: [],
          stages: [],
          grades: [],
          genders: [],
          races: [],
          age_min: "",
          age_max: "",
          max_time_days: "",
          custom_filters: [],
        },
        adjustment_covariates: ["age_at_index"],
        external_covariates: null,
        external_adjustment_covariates: [],
        show_confidence_interval: true,
        show_risk_table: true,
      },
    },
    invalidateScopes: SHARED_CONTEXT_SCOPES,
  }),
  "own-data-upload-start": Object.freeze({
    id: "own-data-upload-start",
    targetView: "analysis",
    patches: {
      activePage: "analysis",
      dataSourceMode: "upload",
      userDatasetUploadStep: 0,
      analysisStep: 0,
    },
    invalidateScopes: ["survival"],
  }),
  "own-data-clinical-groups": Object.freeze({
    id: "own-data-clinical-groups",
    targetView: "expression",
    patches: {
      activePage: "expression",
      expressionComparison: {
        grouping_source: "clinical",
        clinical_variable: "",
        group_a_label: "Reference",
        group_b_label: "Target",
        group_a_values: [],
        group_b_values: [],
      },
    },
    invalidateScopes: ["expression"],
  }),
  "own-data-gsea-go": Object.freeze({
    id: "own-data-gsea-go",
    targetView: "gsea",
    patches: {
      activePage: "gsea",
      gsea: {
        grouping_source: "clinical",
        clinical_variable: "",
        group_a_label: "Reference",
        group_b_label: "Target",
        group_a_values: [],
        group_b_values: [],
        gene_set_collection: "go_bp",
        ranking_metric: "welch_t",
        permutations: 1000,
        seed: 17291,
        fdr_threshold: 0.25,
      },
    },
    invalidateScopes: ["gsea"],
  }),
  "groups-brca-stage": Object.freeze({
    id: "groups-brca-stage",
    targetView: "expression",
    patches: {
      activePage: "expression",
      form: {
        cohort: "TCGA-BRCA",
        dataset_id: null,
        dataset_release_id: null,
        expression_layer_id: null,
        expression_scale: "log2_tpm",
      },
      expressionComparison: {
        grouping_source: "clinical",
        clinical_variable: "stage",
        group_a_label: "Earlier stage",
        group_b_label: "Later stage",
        group_a_values: [],
        group_b_values: [],
      },
    },
    invalidateScopes: SHARED_CONTEXT_SCOPES,
  }),
  "groups-expression-panel": Object.freeze({
    id: "groups-expression-panel",
    targetView: "expression",
    patches: {
      activePage: "expression",
      expressionComparison: {
        genes: ["ESR1", "PGR", "ERBB2"],
      },
    },
    invalidateScopes: ["expression"],
  }),
  "groups-gsea-go": Object.freeze({
    id: "groups-gsea-go",
    targetView: "gsea",
    patches: {
      activePage: "gsea",
      gsea: {
        grouping_source: "clinical",
        clinical_variable: "stage",
        group_a_label: "Earlier stage",
        group_b_label: "Later stage",
        group_a_values: [],
        group_b_values: [],
        gene_set_collection: "go_bp",
        ranking_metric: "welch_t",
        min_gene_set_size: 15,
        max_gene_set_size: 500,
        permutations: 1000,
        seed: 17291,
        fdr_threshold: 0.25,
      },
    },
    invalidateScopes: ["gsea"],
  }),
  "groups-brca-pam50-exploratory": Object.freeze({
    id: "groups-brca-pam50-exploratory",
    targetView: "gsea",
    patches: {
      activePage: "gsea",
      form: {
        cohort: "TCGA-BRCA",
        dataset_id: null,
        dataset_release_id: null,
        expression_layer_id: null,
        expression_scale: "log2_tpm",
      },
      gsea: {
        grouping_source: "clinical",
        clinical_variable: "paper_BRCA_Subtype_PAM50",
        group_a_label: "Luminal A",
        group_b_label: "Basal-like",
        group_a_values: [],
        group_b_values: [],
        gene_set_collection: "go_bp",
        ranking_metric: "welch_t",
        permutations: 1000,
        seed: 17291,
        fdr_threshold: 0.25,
      },
    },
    invalidateScopes: SHARED_CONTEXT_SCOPES,
  }),
  "compare-skcm-pdcd1-cutpoints": Object.freeze({
    id: "compare-skcm-pdcd1-cutpoints",
    targetView: "compare",
    patches: {
      activePage: "compare",
      form: {
        cohort: "TCGA-SKCM",
        dataset_id: null,
        dataset_release_id: null,
        expression_layer_id: null,
        endpoint: "OS",
        expression_scale: "log2_tpm",
      },
      compare: {
        genes: "PDCD1",
        methods: ["median", "upper_quartile", "upper_lower_quartile"],
      },
    },
    invalidateScopes: SHARED_CONTEXT_SCOPES,
  }),
  "multiverse-lihc-cdc20": Object.freeze({
    id: "multiverse-lihc-cdc20",
    targetView: "multiverse",
    patches: {
      activePage: "multiverse",
      form: {
        cohort: "TCGA-LIHC",
        dataset_id: null,
        dataset_release_id: null,
        expression_layer_id: null,
        expression_scale: "log2_tpm",
      },
      multiverse: {
        genes: "CDC20",
        endpoints: ["OS", "DSS"],
        scoring_methods: ["single"],
        cutpoint_methods: ["median", "upper_quartile"],
        session_label: "Tutorial: CDC20 TCGA-LIHC robustness",
      },
    },
    invalidateScopes: SHARED_CONTEXT_SCOPES,
  }),
  "pancancer-cdc20-tcga": Object.freeze({
    id: "pancancer-cdc20-tcga",
    targetView: "pancancer",
    patches: {
      activePage: "pancancer",
      panCancer: {
        analysis_mode: "tcga_reference",
        gene_symbol: "CDC20",
        geneQuery: "CDC20",
        index_cohort: "TCGA-LIHC",
        endpoint: "OS",
        endpoint_mode: "same_endpoint",
        expression_scale: "log2_tpm",
        min_patients: 20,
        min_events: 10,
        fdr_threshold: 0.1,
      },
    },
    invalidateScopes: ["pancancer"],
  }),
  "pancancer-hierarchical-cdc20": Object.freeze({
    id: "pancancer-hierarchical-cdc20",
    targetView: "pancancer",
    patches: {
      activePage: "pancancer",
      panCancer: {
        analysis_mode: "hierarchical",
        hierarchicalRequest: {
          gene_symbol: "CDC20",
          scope: "combined",
          cancers: [],
          study_ids: [],
          endpoint: "OS",
          clinical_context: "primary_baseline",
          time_origin_policy: "strict_baseline",
          effect_scale: "within_study_iqr",
          overlap_policy: "independent_clusters",
          min_patients: 20,
          min_events: 10,
          min_censored: 5,
          include_exploratory: false,
          fdr_threshold: 0.05,
        },
      },
    },
    invalidateScopes: ["pancancer"],
  }),
});

function isPlainObject(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function cloneValue(value) {
  if (Array.isArray(value)) return value.map(cloneValue);
  if (!isPlainObject(value)) return value;
  return Object.fromEntries(
    Object.entries(value).map(([key, item]) => [key, cloneValue(item)]),
  );
}

export function mergeTutorialState(base, patch) {
  if (!isPlainObject(patch)) return cloneValue(patch);
  const result = isPlainObject(base) ? cloneValue(base) : {};
  for (const [key, value] of Object.entries(patch)) {
    result[key] = isPlainObject(value)
      ? mergeTutorialState(result[key], value)
      : cloneValue(value);
  }
  return result;
}

function presetMutation(preset) {
  let mutation = cloneValue(preset.patches);
  for (const scope of preset.invalidateScopes) {
    mutation = mergeTutorialState(mutation, DERIVED_RESULT_RESETS[scope]);
  }
  return mutation;
}

export function getTutorialPreset(presetId) {
  return TUTORIAL_PRESETS[presetId] || null;
}

export function applyTutorialPreset(workspace, presetId) {
  const preset = getTutorialPreset(presetId);
  if (!preset) throw new Error(`Unknown TRACE Explorer tutorial preset: ${presetId}`);
  return mergeTutorialState(workspace, presetMutation(preset));
}

export function createTutorialPresetReducers(presetId) {
  const preset = getTutorialPreset(presetId);
  if (!preset) throw new Error(`Unknown TRACE Explorer tutorial preset: ${presetId}`);
  const mutation = presetMutation(preset);
  const reducers = {};
  for (const [key, value] of Object.entries(mutation)) {
    if (key === "activePage") continue;
    reducers[key] = (previous) => mergeTutorialState(previous, value);
  }
  return {
    presetId,
    targetView: preset.targetView,
    activePage: mutation.activePage || preset.targetView,
    reducers,
  };
}

/**
 * Optional integration adapter for React setters. The caller owns every setter
 * and navigation callback; no network or analysis action is reachable here.
 */
export function applyTutorialPresetWithAdapters(presetId, adapters = {}) {
  const application = createTutorialPresetReducers(presetId);
  for (const [stateKey, reducer] of Object.entries(application.reducers)) {
    const setter = adapters.setters?.[stateKey];
    if (typeof setter === "function") setter(reducer);
  }
  if (typeof adapters.navigate === "function") {
    adapters.navigate(application.activePage);
  }
  return application;
}
