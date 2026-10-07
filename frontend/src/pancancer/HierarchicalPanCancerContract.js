import { scientificNumber } from "../scientificNumbers";

export const PAN_CANCER_ANALYSIS_MODES = [
  {
    value: "tcga_reference",
    label: "Across TCGA cancer types",
    shortLabel: "TCGA only",
    description:
      "Test one gene or signature separately in each TCGA cancer type.",
    question: "Which cancer types show an association with survival?",
  },
  {
    value: "hierarchical",
    label: "Across independent studies",
    shortLabel: "TCGA + external",
    description:
      "Test one gene in TCGA cohorts, external studies, or both. Uses overall survival.",
    question: "Does this gene's association with survival hold across cohorts?",
  },
];

export const HIERARCHICAL_RESULT_VIEWS = [
  {
    value: "all_studies",
    label: "All studies",
    description: "Every analyzed study, grouped by cancer.",
  },
  {
    value: "compatible",
    label: "Compatible",
    description: "Only studies with matching outcome, timing, context and scale.",
  },
  {
    value: "sensitivities",
    label: "Sensitivities",
    description: "Prespecified alternative inclusion rules and scales.",
  },
];

export const HIERARCHICAL_REQUEST_DEFAULTS = Object.freeze({
  gene_symbol: "",
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
});

export const HIERARCHICAL_SCOPE_OPTIONS = [
  { value: "combined", label: "TCGA + curated external" },
  { value: "tcga_only", label: "TCGA only" },
  { value: "external_only", label: "Curated external only" },
];

export const HIERARCHICAL_CONTEXT_OPTIONS = [
  { value: "primary_baseline", label: "Primary disease · baseline" },
  { value: "advanced_treatment", label: "Advanced disease · treatment start" },
  { value: "hematologic_diagnostic", label: "Hematologic disease · diagnosis" },
];

const VIEW_ALIASES = {
  all: "all_studies",
  all_studies: "all_studies",
  compatible: "compatible",
  sensitivity: "sensitivities",
  sensitivities: "sensitivities",
};

export function normalizeAnalysisMode(value) {
  return value === "hierarchical" ? "hierarchical" : "tcga_reference";
}

export function normalizeResultView(value) {
  return VIEW_ALIASES[value] || "all_studies";
}

export function normalizeHierarchicalRequestState(state = {}) {
  return { ...HIERARCHICAL_REQUEST_DEFAULTS, ...state };
}

export function preflightCancerGroups(preflight = {}) {
  const includeExploratory = Boolean(
    preflight.request?.include_exploratory ?? preflight.include_exploratory,
  );
  let groups = preflight.cancer_groups || preflight.cancers || [];
  if (!groups.length && Array.isArray(preflight.universes)) {
    const grouped = new Map();
    for (const universe of preflight.universes) {
      const cancer = String(
        universe.cancer || universe.cancer_code || universe.cancer_id || "Unmapped",
      );
      if (!grouped.has(cancer)) {
        grouped.set(cancer, { cancer, label: cancer, studies: [] });
      }
      grouped.get(cancer).studies.push(universe);
    }
    groups = [...grouped.values()];
  }
  return [...groups]
    .map((group) => ({
      ...group,
      cancer: String(group.cancer || group.cancer_code || "Unmapped"),
      label: String(
        group.label || group.cancer_label || group.cancer || "Unmapped cancer",
      ),
      studies: [...(group.studies || group.universes || [])]
        .map((study) => normalizePreflightStudy(study, includeExploratory))
        .sort(compareStudies),
    }))
    .sort((left, right) => left.cancer.localeCompare(right.cancer));
}

export function studyIsIncluded(study = {}) {
  if (study.selected_for_cluster === false) return false;
  if (typeof study.selected_for_analysis === "boolean") {
    return study.selected_for_analysis;
  }
  if (typeof study.analysis_eligible === "boolean") {
    return study.analysis_eligible;
  }
  if (typeof study.included === "boolean") return study.included;
  if (typeof study.eligible === "boolean") return study.eligible;
  if (["primary", "exploratory"].includes(String(study.evidence_tier || "").toLowerCase())) {
    return true;
  }
  return ["included", "eligible", "compatible", "reference"].includes(
    String(study.status || study.compatibility || "").toLowerCase(),
  );
}

export function studyReasons(study = {}) {
  const reasons = study.reasons || study.exclusion_reasons || [];
  return reasons
    .map((reason) => {
      if (typeof reason === "string") {
        const [code] = reason.split(":", 1);
        return { code: code || "NOT_ELIGIBLE", label: humanizeReason(reason) };
      }
      return {
        code: String(reason?.code || "NOT_ELIGIBLE"),
        label: String(reason?.label || reason?.message || reason?.code || "Not eligible"),
      };
    })
    .filter((reason) => reason.label);
}

export function summarizePreflight(preflight = {}) {
  const groups = preflightCancerGroups(preflight);
  const studies = groups.flatMap((group) => group.studies);
  const included = studies.filter(studyIsIncluded);
  const replicatedGroups = groups.filter((group) => {
    const clusters = new Set(
      group.studies
        .filter(studyIsIncluded)
        .map((study) => study.study_cluster_id || study.study_id || study.universe_id)
        .filter(Boolean),
    );
    return clusters.size >= 2;
  });
  const replicatedCancerIds = new Set(
    replicatedGroups.map((group) => String(group.cancer)),
  );
  const replicatedStudies = included.filter((study) =>
    replicatedCancerIds.has(String(study.cancer || study.cancer_code || "")),
  );
  const explicit = preflight.universe || preflight.summary || {};
  const explicitIncluded =
    explicit.included_studies ??
    explicit.eligible_studies ??
    explicit.included ??
    (Number.isFinite(Number(explicit.primary))
      ? Number(explicit.primary) +
        (preflight.request?.include_exploratory
          ? finiteOrFallback(explicit.exploratory, 0)
          : 0)
      : undefined);
  return {
    cancers: finiteOrFallback(
      explicit.cancers ?? explicit.cancer_groups,
      groups.length,
    ),
    replicatedCancers: finiteOrFallback(
      explicit.replicated_cancers,
      replicatedGroups.length,
    ),
    replicatedEvents: finiteOrFallback(
      explicit.replicated_events,
      replicatedStudies.reduce(
        (total, study) => total + finiteOrFallback(study.events, 0),
        0,
      ),
    ),
    preliminaryGlobalReady:
      typeof explicit.preliminary_global_ready === "boolean"
        ? explicit.preliminary_global_ready
        : replicatedGroups.length >= 2,
    formalGlobalReady:
      typeof explicit.formal_global_ready === "boolean"
        ? explicit.formal_global_ready
        : replicatedGroups.length >= 5 && replicatedStudies.reduce(
          (total, study) => total + finiteOrFallback(study.events, 0),
          0,
        ) >= 100,
    totalStudies: finiteOrFallback(
      explicit.total_studies ?? explicit.total_universes,
      studies.length,
    ),
    includedStudies: finiteOrFallback(
      explicitIncluded,
      included.length,
    ),
    excludedStudies: finiteOrFallback(
      explicit.excluded_studies,
      studies.length - included.length,
    ),
    patients: finiteOrFallback(
      explicit.patients,
      included.reduce((total, study) => total + finiteOrFallback(study.patients, 0), 0),
    ),
    events: finiteOrFallback(
      explicit.events,
      included.reduce((total, study) => total + finiteOrFallback(study.events, 0), 0),
    ),
    endpoint:
      explicit.endpoint ||
      preflight.endpoint ||
      preflight.request?.endpoint ||
      "Not specified",
    effectUnit:
      explicit.effect_unit ||
      preflight.effect_unit ||
      preflight.effect_scale?.label ||
      "HR per +1 within-study expression IQR",
  };
}

export function hierarchicalViewPayload(result = {}, view = "all_studies") {
  const normalizedView = normalizeResultView(view);
  const views = result.views || {};
  const explicit = views[normalizedView] || views[view];
  if (explicit) {
    const explicitMetaAnalysis = explicit.meta_analysis || {};
    const explicitSensitivities = explicit.sensitivities || {};
    return {
      ...explicit,
      rows: explicit.rows || explicit.forest_rows || [],
      heterogeneity:
        explicit.heterogeneity || explicit.meta_analysis?.heterogeneity || {},
      leaveOneOut: normalizedLeaveOneOut(
        hasLeaveOneOutRows(explicit.leave_one_out)
          ? explicit.leave_one_out
          : explicitSensitivities.leave_one_out || explicitSensitivities,
        explicitMetaAnalysis.random_effect?.hazard_ratio,
      ),
      sensitivity_sets: hierarchicalSensitivitySets(
        explicit.sensitivity_sets || explicit.sensitivities,
      ),
    };
  }

  if (
    Array.isArray(result.study_results) ||
    Array.isArray(result.cancer_results) ||
    result.global_result
  ) {
    const rows = hierarchicalResultRows(result, normalizedView);
    const globalEffect = resolvedGlobalEffect(result.global_result);
    const sensitivities = result.sensitivities || {};
    const leaveOneOutSource = hasLeaveOneOutRows(result.leave_one_out)
      ? result.leave_one_out
      : sensitivities.leave_one_out || sensitivities;
    return {
      rows,
      summary: result.summary || {},
      meta_analysis: globalEffect,
      heterogeneity: globalEffect.heterogeneity || {},
      leaveOneOut: normalizedLeaveOneOut(
        leaveOneOutSource,
        globalEffect.random_effect?.hazard_ratio,
      ),
      sensitivity_sets: hierarchicalSensitivitySets(
        result.sensitivity_sets || sensitivities,
      ),
      effect_unit:
        result.effect_scale?.label || result.effect_scale?.unit || result.effect_scale,
      endpoint: result.endpoint,
      description: hierarchicalViewDescription(normalizedView),
    };
  }

  const rows = result.rows || result.forest_rows || result.results || [];
  return {
    rows: rows.filter((row) => rowSupportsView(row, normalizedView)),
    meta_analysis: result.meta_analysis || {},
    heterogeneity:
      result.heterogeneity || result.meta_analysis?.heterogeneity || {},
    leaveOneOut: result.leave_one_out || [],
    description: result.description || "",
  };
}

export function hierarchicalSensitivitySets(value) {
  if (!value) return [];
  if (Array.isArray(value)) {
    return value.map((row, index) => normalizeSensitivitySet(row, `set-${index + 1}`));
  }
  if (typeof value !== "object") return [];
  const nested =
    value.sets ||
    value.analysis_sets ||
    value.alternative_universes ||
    value.results;
  if (Array.isArray(nested)) {
    return nested.map((row, index) =>
      normalizeSensitivitySet(row, row?.id || `set-${index + 1}`),
    );
  }
  const reserved = new Set([
    "leave_one_out",
    "leave_one_study_out",
    "leave_one_cancer_out",
    "warnings",
    "summary",
  ]);
  return Object.entries(value)
    .filter(([id, row]) =>
      !reserved.has(id) && row && typeof row === "object" && !Array.isArray(row),
    )
    .map(([id, row]) => normalizeSensitivitySet(row, id));
}

export function hierarchicalResultRows(result = {}, view = "all_studies") {
  const normalizedView = normalizeResultView(view);
  const studies = (result.study_results || []).map((row) => ({
    ...row,
    id: row.id || row.release_id || row.study_id,
    label:
      row.label || row.study_label || row.name || row.study_id || row.release_id,
    kind: "study",
    cancer: row.cancer || row.cancer_id || row.cancer_code,
    patients: row.patients ?? row.n_patients,
    events: row.events ?? row.n_events,
  }));
  const cancers = (result.cancer_results || []).map((row) => ({
    ...row,
    id: row.id || `cancer-${row.cancer_id || row.cancer_code}`,
    label:
      row.label || row.cancer_label || `${row.cancer_id || row.cancer_code} synthesis`,
    kind: "cancer",
    cancer: row.cancer || row.cancer_id || row.cancer_code,
    studies: row.studies ?? row.n_studies,
    patients: row.patients ?? row.n_patients,
    events: row.events ?? row.n_events,
  }));
  const globalEffect = resolvedGlobalEffect(result.global_result);
  const randomEffect = globalEffect.random_effect || {};
  const globalRows = globalEffect && Object.keys(globalEffect).length
    ? [{
        ...globalEffect,
        ...randomEffect,
        id: "hierarchical-universe",
        label: globalEffect.label || "Combined estimate across compatible cancers",
        kind: "universe",
        cancers:
          globalEffect.cancers ?? result.summary?.cancers ?? result.summary?.evaluable_cancers,
        studies:
          globalEffect.studies ?? result.summary?.studies ?? result.summary?.completed_studies,
        patients:
          result.summary?.replicated_patients ?? result.summary?.patients,
        events:
          result.summary?.replicated_events ?? result.summary?.events,
      }]
    : [];

  const visibleStudies = normalizedView === "compatible"
    ? studies.filter((row) =>
        row.status === "completed" &&
        row.pooling_eligible !== false &&
        row.compatible !== false,
      )
    : normalizedView === "sensitivities"
      ? []
      : studies;

  const cancerIds = new Set([
    ...visibleStudies.map((row) => String(row.cancer || "")),
    ...cancers.map((row) => String(row.cancer || "")),
  ]);
  const ordered = [];
  for (const cancer of [...cancerIds].filter(Boolean).sort()) {
    ordered.push(
      ...visibleStudies
        .filter((row) => String(row.cancer || "") === cancer)
        .sort((left, right) => String(left.label || "").localeCompare(String(right.label || ""))),
    );
    ordered.push(...cancers.filter((row) => String(row.cancer || "") === cancer));
  }
  ordered.push(...globalRows);
  return ordered;
}

export function rowSupportsView(row = {}, view = "all_studies") {
  const normalizedView = normalizeResultView(view);
  const declaredViews = row.views || row.result_views;
  if (Array.isArray(declaredViews)) {
    return declaredViews.map(normalizeResultView).includes(normalizedView);
  }
  if (normalizedView === "all_studies") return true;
  if (normalizedView === "compatible") {
    return row.compatible === true || ["compatible", "reference"].includes(
      String(row.compatibility || "").toLowerCase(),
    );
  }
  return Boolean(row.sensitivity_id || row.sensitivity);
}

export function forestEstimate(row = {}) {
  const randomEffect = row.random_effect || {};
  const logHazardRatio = finiteOrNull(
    row.iqr_log_hr ?? row.log_hr ?? randomEffect.log_hr,
  );
  const standardError = positiveFinite(
    row.iqr_standard_error ?? row.standard_error ?? randomEffect.standard_error,
  );
  const hazardRatio = positiveFinite(
    row.iqr_hazard_ratio ??
      row.hazard_ratio ??
      row.hr ??
      randomEffect.hazard_ratio ??
      (logHazardRatio == null ? null : Math.exp(logHazardRatio)),
  );
  const confLow = positiveFinite(
    row.iqr_hr_conf_low ??
      row.hr_conf_low ??
      row.conf_low ??
      row.ci_low ??
      randomEffect.hr_conf_low ??
      (logHazardRatio == null || standardError == null
        ? null
        : Math.exp(logHazardRatio - 1.96 * standardError)),
  );
  const confHigh = positiveFinite(
    row.iqr_hr_conf_high ??
      row.hr_conf_high ??
      row.conf_high ??
      row.ci_high ??
      randomEffect.hr_conf_high ??
      (logHazardRatio == null || standardError == null
        ? null
        : Math.exp(logHazardRatio + 1.96 * standardError)),
  );
  return {
    hazardRatio,
    confLow,
    confHigh,
    estimable: Boolean(
      hazardRatio && confLow && confHigh && confLow <= hazardRatio && hazardRatio <= confHigh,
    ),
  };
}

export function forestRowKind(row = {}) {
  const value = String(row.kind || row.row_type || row.level || "study").toLowerCase();
  if (value.includes("universe") || value.includes("overall")) return "universe";
  if (value.includes("cancer")) return "cancer";
  return "study";
}

export function forestDomain(rows = []) {
  const estimates = rows.flatMap((row) => {
    const estimate = forestEstimate(row);
    return estimate.estimable
      ? [estimate.confLow, estimate.hazardRatio, estimate.confHigh]
      : [];
  });
  if (!estimates.length) return { min: 0.5, max: 2 };
  const minimum = Math.min(1, ...estimates);
  const maximum = Math.max(1, ...estimates);
  const logExtent = Math.max(
    Math.abs(Math.log(minimum)),
    Math.abs(Math.log(maximum)),
    Math.log(1.25),
  );
  const paddedExtent = logExtent * 1.08;
  return {
    min: Math.exp(-paddedExtent),
    max: Math.exp(paddedExtent),
  };
}

export function forestTicks(domain) {
  const preferred = [0.125, 0.25, 0.5, 1, 2, 4, 8];
  const visible = preferred.filter(
    (value) => value >= domain.min * 0.98 && value <= domain.max * 1.02,
  );
  if (visible.length >= 3) return visible;
  const minimumLog = Math.log(domain.min);
  const maximumLog = Math.log(domain.max);
  return [0, 0.5, 1].map((fraction) =>
    Math.exp(minimumLog + fraction * (maximumLog - minimumLog)),
  );
}

export function forestX(value, domain, left, width) {
  const numeric = positiveFinite(value) || 1;
  const minimumLog = Math.log(domain.min);
  const maximumLog = Math.log(domain.max);
  const bounded = Math.max(domain.min, Math.min(domain.max, numeric));
  return left + ((Math.log(bounded) - minimumLog) / (maximumLog - minimumLog)) * width;
}

export function heterogeneityBand(iSquared) {
  const value = scientificNumber(iSquared);
  if (value === null) return "Not estimable";
  if (value < 25) return "Low";
  if (value < 50) return "Moderate";
  if (value < 75) return "Substantial";
  return "Considerable";
}

export function leaveOneOutIsInfluential(row = {}) {
  if (typeof row.influential === "boolean") return row.influential;
  const change = Math.abs(Number(row.relative_change ?? row.delta_percent));
  return Number.isFinite(change) && change >= 10;
}

function compareStudies(left, right) {
  const includedDelta = Number(studyIsIncluded(right)) - Number(studyIsIncluded(left));
  if (includedDelta) return includedDelta;
  const sourceDelta = sourceOrder(left.source_kind) - sourceOrder(right.source_kind);
  if (sourceDelta) return sourceDelta;
  return String(left.label || left.id || "").localeCompare(
    String(right.label || right.id || ""),
  );
}

function normalizePreflightStudy(study, includeExploratory) {
  const evidenceTier = String(study.evidence_tier || study.tier || "").toLowerCase();
  const explicitIncluded =
    typeof study.selected_for_analysis === "boolean"
        ? study.selected_for_analysis
        : typeof study.analysis_eligible === "boolean"
          ? study.analysis_eligible
          : typeof study.included === "boolean"
            ? study.included
            : null;
  const included = study.selected_for_cluster === false
    ? false
    : explicitIncluded ?? Boolean(
        evidenceTier === "primary" ||
        (evidenceTier === "exploratory" && includeExploratory) ||
        (!evidenceTier && (study.eligible || study.analysis_eligible)),
      );
  const reasons = [...(study.reasons || study.exclusion_reasons || [])];
  if (evidenceTier === "exploratory" && !includeExploratory && !included) {
    reasons.push("exploratory_not_requested");
  }
  return {
    ...study,
    id: study.id || study.universe_id || study.release_id || study.study_id,
    label:
      study.label || study.name || study.study_label || study.study_id || study.universe_id,
    included,
    status: study.status || evidenceTier,
    compatibility: study.compatibility || evidenceTier,
    patients: study.patients ?? study.n_patients,
    events: study.events ?? study.n_events,
    censored: study.censored ?? study.n_censored,
    endpoint: study.endpoint || study.endpoint_class || study.endpoint_id,
    time_origin: study.time_origin || study.time_origin_class,
    tumor_context:
      study.tumor_context || study.sample_context || study.clinical_context,
    expression_unit:
      study.expression_unit ||
      study.analysis_unit ||
      study.expression_scale?.analysis_unit ||
      study.expression_scale?.source_unit ||
      "Within-study IQR score",
    reasons,
  };
}

function resolvedGlobalEffect(globalResult) {
  if (!globalResult || typeof globalResult !== "object") return {};
  return globalResult.global_effect || globalResult;
}

function normalizedLeaveOneOut(leaveOneOut, referenceHazardRatio) {
  if (Array.isArray(leaveOneOut)) return leaveOneOut;
  if (!leaveOneOut || typeof leaveOneOut !== "object") return [];
  if (leaveOneOut.leave_one_out) {
    return normalizedLeaveOneOut(
      leaveOneOut.leave_one_out,
      referenceHazardRatio,
    );
  }
  const rows = [
    ...(leaveOneOut.leave_one_cancer_out || leaveOneOut.cancers || []),
    ...(leaveOneOut.leave_one_study_out || leaveOneOut.studies || []),
  ];
  return rows.map((row) => {
    const hazardRatio = Number(row.hazard_ratio ?? row.hr);
    const reference = Number(referenceHazardRatio);
    const omittedKind = String(row.omitted_kind || "").toLowerCase();
    const studyOmission = omittedKind === "study" || Boolean(
      row.omitted_release_id || row.omitted_study_id,
    );
    const delta = Number.isFinite(hazardRatio) && hazardRatio > 0 && Number.isFinite(reference) && reference > 0
      ? ((hazardRatio / reference) - 1) * 100
      : null;
    return {
      ...row,
      omitted_id:
        row.omitted_id ||
        (studyOmission
          ? row.omitted_release_id || row.omitted_study_id
          : row.omitted_cancer_id),
      omitted_label:
        row.omitted_label ||
        (studyOmission
          ? row.omitted_study_id || row.omitted_release_id
          : row.omitted_cancer_id),
      delta_percent: row.delta_percent ?? row.relative_change ?? delta,
    };
  });
}

function hasLeaveOneOutRows(value) {
  if (Array.isArray(value)) return value.length > 0;
  if (!value || typeof value !== "object") return false;
  if (value.leave_one_out) return hasLeaveOneOutRows(value.leave_one_out);
  return [
    value.leave_one_cancer_out,
    value.cancers,
    value.leave_one_study_out,
    value.studies,
  ].some((rows) => Array.isArray(rows) && rows.length > 0);
}

function normalizeSensitivitySet(row = {}, fallbackId) {
  const globalEffect = resolvedGlobalEffect(
    row.global_result || row.result || row.meta_analysis || row,
  );
  const randomEffect = globalEffect.random_effect || row.random_effect || {};
  const id = String(row.id || row.contract_id || fallbackId);
  return {
    ...row,
    id,
    label: row.label || row.name || humanizeReason(id),
    change:
      row.change ||
      row.change_from_primary ||
      row.description ||
      "Planned alternative settings",
    units:
      row.units ??
      row.studies ??
      row.summary?.studies ??
      globalEffect.studies ??
      globalEffect.units,
    hazard_ratio:
      row.hazard_ratio ?? randomEffect.hazard_ratio,
    hr_conf_low:
      row.hr_conf_low ?? randomEffect.hr_conf_low,
    hr_conf_high:
      row.hr_conf_high ?? randomEffect.hr_conf_high,
    interpretation:
      row.interpretation || row.classification || row.status || "Not reported",
  };
}

function hierarchicalViewDescription(view) {
  if (view === "compatible") {
    return "Only completed, pooling-eligible study effects contribute to the strict hierarchical synthesis.";
  }
  if (view === "sensitivities") {
    return "Compare cancer and global estimates with refits that omit one study or one cancer at a time.";
  }
  return "All attempted study effects remain visible; excluded or non-estimable rows carry no synthesis weight.";
}

function humanizeReason(reason) {
  return String(reason || "")
    .replace(/:/g, ": ")
    .replace(/_/g, " ")
    .replace(/^./, (character) => character.toUpperCase());
}

function sourceOrder(value) {
  return String(value || "").toLowerCase() === "tcga" ? 0 : 1;
}

function finiteOrFallback(value, fallback) {
  return scientificNumber(value) ?? fallback;
}

function positiveFinite(value) {
  const numeric = Number(value);
  return Number.isFinite(numeric) && numeric > 0 ? numeric : null;
}

function finiteOrNull(value) {
  return scientificNumber(value);
}
