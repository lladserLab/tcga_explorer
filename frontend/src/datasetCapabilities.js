/**
 * One frontend interpretation of the dataset capability contract.
 *
 * New repository releases expose both `capabilities` and `available_modules`.
 * The fallbacks keep older cached releases and temporary private datasets
 * usable while those payloads age out; they do not manufacture survival when
 * no time-to-event endpoint exists.
 */

export const DATASET_ANALYSIS_MODULES = Object.freeze([
  Object.freeze({ id: "analysis", label: "Survival", capability: "survival" }),
  Object.freeze({ id: "compare", label: "Compare", capability: "survival" }),
  Object.freeze({ id: "expression", label: "Expression", capability: "expression_comparison" }),
  Object.freeze({ id: "gsea", label: "GSEA", capability: "gsea" }),
  Object.freeze({ id: "multiverse", label: "Robustness", capability: "survival" }),
]);

export const DATASET_ANALYSIS_FILTERS = Object.freeze([
  Object.freeze({ value: "all", label: "Any available analysis" }),
  ...DATASET_ANALYSIS_MODULES.map(({ id, label }) => Object.freeze({
    value: id,
    label,
  })),
]);

const MODULE_ALIASES = Object.freeze({
  survival: "analysis",
  analysis: "analysis",
  compare: "compare",
  expression: "expression",
  expression_comparison: "expression",
  gsea: "gsea",
  robustness: "multiverse",
  multiverse: "multiverse",
});

const DEFAULT_UNAVAILABLE_REASONS = Object.freeze({
  survival: "No time-to-event endpoint passed release QC.",
  expression_comparison: "No patient-level expression layer passed release QC.",
  gsea: "The expression matrix does not meet transcriptome-wide gene coverage.",
});

export function normalizeAnalysisModule(moduleId) {
  return MODULE_ALIASES[String(moduleId || "").trim().toLowerCase()] || "";
}

export function moduleCapabilityName(moduleId) {
  const normalized = normalizeAnalysisModule(moduleId);
  return DATASET_ANALYSIS_MODULES.find((item) => item.id === normalized)?.capability || "";
}

export function moduleAnalysisLabel(moduleId) {
  const normalized = normalizeAnalysisModule(moduleId);
  return DATASET_ANALYSIS_MODULES.find((item) => item.id === normalized)?.label || "Analysis";
}

function capabilityEntry(dataset, capability) {
  const capabilities = dataset?.capabilities || {};
  if (capability === "expression_comparison") {
    return capabilities.expression_comparison || capabilities.expression || null;
  }
  return capabilities[capability] || null;
}

function legacyCapabilityAvailable(dataset, capability) {
  if (capability === "survival") {
    return (dataset?.endpoints || []).some((endpoint) => endpoint?.available !== false);
  }
  if (capability === "expression_comparison") {
    return Boolean(
      dataset?.expression_layer
      || dataset?.expression_layers?.length
      || Number(dataset?.gene_count || 0) > 0,
    );
  }
  if (capability === "gsea") {
    const geneCount = Number(dataset?.gene_count);
    return (Number.isFinite(geneCount) && geneCount > 0
      ? geneCount >= 100
      : Boolean(dataset?.expression_layer || dataset?.expression_layers?.length))
      || dataset?.capabilities?.gsea?.available === true;
  }
  return false;
}

export function datasetCapability(dataset, moduleId) {
  const module = normalizeAnalysisModule(moduleId);
  const capability = moduleCapabilityName(module);
  if (!dataset || !module || !capability) {
    return {
      module,
      capability,
      available: false,
      reason: "This analysis is not available for the selected dataset.",
    };
  }

  const availableModules = Array.isArray(dataset.available_modules)
    ? dataset.available_modules.map(normalizeAnalysisModule).filter(Boolean)
    : null;
  const entry = capabilityEntry(dataset, capability);
  const available = availableModules
    ? availableModules.includes(module)
    : typeof entry?.available === "boolean"
      ? entry.available
      : legacyCapabilityAvailable(dataset, capability);

  return {
    ...(entry || {}),
    module,
    capability,
    available,
    reason: available
      ? String(entry?.reason || "Available for this release.")
      : String(entry?.reason || DEFAULT_UNAVAILABLE_REASONS[capability]),
  };
}

export function datasetSupportsModule(dataset, moduleId) {
  return datasetCapability(dataset, moduleId).available;
}

export function availableDatasetModules(dataset) {
  return DATASET_ANALYSIS_MODULES.filter(({ id }) =>
    datasetSupportsModule(dataset, id),
  );
}

export function filterDatasetsForModule(datasets, moduleId) {
  const normalized = normalizeAnalysisModule(moduleId);
  if (!normalized) return [...(datasets || [])];
  return (datasets || []).filter((dataset) =>
    datasetSupportsModule(dataset, normalized),
  );
}

export function cohortSupportsModule(cohort, datasets, moduleId) {
  if (!cohort) return false;
  if (cohort.status !== "external_only") return true;
  return (datasets || []).some(
    (dataset) => dataset.tcga_cohort === cohort.id
      && datasetSupportsModule(dataset, moduleId),
  );
}
