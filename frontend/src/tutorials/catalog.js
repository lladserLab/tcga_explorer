/**
 * Stable tutorial identifiers shared by curriculum, URL state and integrations.
 * These values are data contracts. Visible copy belongs to the English curriculum.
 */

import { APP_MODULES } from "../moduleRegistry";

export const TUTORIAL_CONTENT_VERSION = "3.2.0";
export const TUTORIAL_HUB_TABS = Object.freeze(["tutorials", "manuals"]);

export const SEVEN_LESSON_PATTERN = Object.freeze([
  "question",
  "eligibility",
  "design",
  "primary-evidence",
  "diagnostics",
  "error-lab",
  "handoff",
]);

export const APPROVED_ROUTE_IDS = Object.freeze([
  "included-data-first-analysis",
  "own-data",
  "groups-to-pathways",
  "robustness-multiplicity",
  "validation-generalization",
]);

export const TEACHING_EXAMPLE_PROVENANCE = Object.freeze({
  "example-continuous-before-cutpoint": Object.freeze({
    result_id: "TRACE-TEACH-CONTINUOUS-V1",
    pipeline_version: "teaching-contract-only",
    snapshot_date: "2026-08-05",
    sha256: "45acda6ebb5062501250a318f86ecb98cf7eb976521259ab532d9cf5178e5556",
    artifact_path: "tutorial-examples/continuous-before-cutpoint.json",
  }),
  "example-private-data-error-lab": Object.freeze({
    result_id: "TRACE-TEACH-UPLOAD-ERRORS-V1",
    pipeline_version: "teaching-contract-only",
    snapshot_date: "2026-08-05",
    sha256: "b056f6cc095697d241dc27966371162e6544844af7224869fc350ca6d0d5f817",
    artifact_path: "tutorial-examples/private-data-error-lab.json",
  }),
  "example-gsea-direction": Object.freeze({
    result_id: "TRACE-TEACH-GSEA-DIRECTION-V1",
    pipeline_version: "teaching-contract-only",
    snapshot_date: "2026-08-05",
    sha256: "8cc4eed344d0df08c047a0b2f71fed59addbd1242859cc5598cde815a379d002",
    artifact_path: "tutorial-examples/gsea-direction.json",
  }),
  "example-multiplicity-boundaries": Object.freeze({
    result_id: "TRACE-TEACH-MULTIPLICITY-V1",
    pipeline_version: "teaching-contract-only",
    snapshot_date: "2026-08-05",
    sha256: "7f236c3ae71e62556d3feb02daeb9f35eadaacb613f52e283ba64f759c40067b",
    artifact_path: "tutorial-examples/multiplicity-boundaries.json",
  }),
  "example-pancancer-heterogeneity": Object.freeze({
    result_id: "TRACE-TEACH-PANCANCER-V1",
    pipeline_version: "teaching-contract-only",
    snapshot_date: "2026-08-05",
    sha256: "2dc66946a539bcf36941d01f2fea8b5bee167d0c4210e6af4d72c9d13433c4ec",
    artifact_path: "tutorial-examples/pancancer-heterogeneity.json",
  }),
});

export const TUTORIAL_MODULE_ORDER = Object.freeze(APP_MODULES.map(({ id }) => id));
export const QUICK_GUIDE_MODULE_ORDER = Object.freeze(
  APP_MODULES.filter(({ showLearnAction }) => showLearnAction).map(({ id }) => id),
);

export const TUTORIAL_SOURCE_KINDS = Object.freeze([
  "live",
  "synthetic_case",
  "computed_benchmark",
]);

/**
 * Recommended continuations enter one of the approved learning routes. Keeping
 * these edges out of visible copy prevents the learning graph from drifting or
 * creating cycles such as Repository -> Pan-cancer -> Repository.
 */
export const QUICK_GUIDE_CONTINUATIONS = Object.freeze({
  home: "included-data-first-analysis",
  analysis: "robustness-multiplicity",
  compare: "robustness-multiplicity",
  expression: "groups-to-pathways",
  gsea: "groups-to-pathways",
  multiverse: "robustness-multiplicity",
  session: "robustness-multiplicity",
  pancancer: "validation-generalization",
});

export const FIXED_EXAMPLE_CONTINUATIONS = Object.freeze({
  "example-continuous-before-cutpoint": "included-data-first-analysis",
  "example-private-data-error-lab": "own-data",
  "example-gsea-direction": "groups-to-pathways",
  "example-multiplicity-boundaries": "robustness-multiplicity",
  "example-pancancer-heterogeneity": "validation-generalization",
});

export const TUTORIAL_MODULES = Object.freeze(Object.fromEntries(
  APP_MODULES.map(({ id, iconRole }) => [
    id,
    Object.freeze({ page: id, iconRole }),
  ]),
));

export const GUIDE_ANCHORS = Object.freeze({
  HOME_OVERVIEW: "home.overview",
  HOME_WORKSPACE: "home.workspace",
  HOME_FOUNDATION: "home.foundation",
  HOME_INTERPRETATION: "home.interpretation",
  DATASET_COVERAGE: "dataset.coverage",
  DATASET_OVERVIEW: "dataset.overview",
  DATASET_PROVENANCE: "dataset.provenance",
  DATASET_COHORT_LANDSCAPE: "dataset.cohort-landscape",
  DATASET_SAMPLE_TYPES: "dataset.sample-types",
  DATASET_VITAL_STATUS: "dataset.vital-status",
  DATASET_PRIMARY_SITES: "dataset.primary-sites",
  DATASET_AGE: "dataset.age",
  DATASET_METADATA: "dataset.metadata",
  DATASET_ANNOTATIONS: "dataset.annotations",
  DATASET_COHORT_TABLE: "dataset.cohort-table",
  DATASET_INTERPRETATION: "dataset.interpretation",
  METHODS_INPUT_OUTPUT: "methods.input-output",
  METHODS_ANALYSIS_INPUTS: "methods.analysis-inputs",
  METHODS_SIGNATURE_SCORING: "methods.signature-scoring",
  METHODS_STRATIFICATION: "methods.stratification",
  METHODS_SURVIVAL_OUTPUTS: "methods.survival-outputs",
  METHODS_CROSS_MODULE: "methods.cross-module",
  METHODS_GLOSSARY: "methods.glossary",
  METHODS_HISTORY: "methods.history",
  METHODS_INTERPRETATION: "methods.interpretation",
  EXAMPLES_CATALOG: "examples.catalog",
  EXAMPLES_ROUTES: "examples.routes",
  EXAMPLES_QUICK: "examples.quick-guides",
  EXAMPLES_MANUALS: "examples.manuals",

  SURVIVAL_DATASET: "survival.dataset",
  SURVIVAL_UPLOAD: "survival.upload",
  SURVIVAL_UPLOAD_EXPRESSION: "survival.upload.expression",
  SURVIVAL_UPLOAD_OUTCOME: "survival.upload.outcome",
  SURVIVAL_UPLOAD_METADATA: "survival.upload.metadata",
  SURVIVAL_MARKER: "survival.marker",
  SURVIVAL_OUTCOME: "survival.outcome",
  SURVIVAL_CLINICAL: "survival.clinical",
  SURVIVAL_REVIEW: "survival.review",
  SURVIVAL_RESULTS: "survival.results",
  SURVIVAL_DIAGNOSTICS: "survival.diagnostics",
  SURVIVAL_DOWNLOADS: "survival.downloads",

  COMPARE_DATASET: "compare.dataset",
  COMPARE_MARKERS: "compare.markers",
  COMPARE_METHODS: "compare.methods",
  COMPARE_CLINICAL: "compare.clinical",
  COMPARE_REVIEW: "compare.review",
  COMPARE_RESULTS: "compare.results",
  EXPRESSION_DATASET: "expression.dataset",
  EXPRESSION_GENES: "expression.genes",
  EXPRESSION_GROUPS: "expression.groups",
  EXPRESSION_TEST_FAMILY: "expression.test-family",
  EXPRESSION_RESULTS: "expression.results",
  GSEA_DATASET: "gsea.dataset",
  GSEA_GROUPS: "gsea.groups",
  GSEA_COLLECTION: "gsea.collection",
  GSEA_RESULTS: "gsea.results",

  MULTIVERSE_DATASET: "multiverse.dataset",
  MULTIVERSE_MARKER: "multiverse.marker",
  MULTIVERSE_DESIGN: "multiverse.design",
  MULTIVERSE_CLINICAL: "multiverse.clinical",
  MULTIVERSE_REVIEW: "multiverse.review",
  MULTIVERSE_RESULTS: "multiverse.results",
  SESSION_SETUP: "session.setup",
  SESSION_LEDGER: "session.ledger",
  SESSION_INTERPRETATION: "session.interpretation",

  REPOSITORY_INTERPRETATION: "repository.interpretation",
  REPOSITORY_FINDER: "repository.finder",
  REPOSITORY_PROVENANCE: "repository.provenance",
  PANCANCER_MODE: "pancancer.mode",
  PANCANCER_QUERY: "pancancer.query",
  PANCANCER_PREFLIGHT: "pancancer.preflight",
  PANCANCER_RESULTS: "pancancer.results",
  API_INTERPRETATION: "api.interpretation",
  API_REST: "api.rest",
  API_CONNECTORS: "api.connectors",
  API_EXECUTION: "api.execution",
});

const quickStep = (id, anchor, workspaceStepId = null) => Object.freeze({
  id,
  anchor,
  workspaceStepId,
});

export const QUICK_GUIDE_STEP_CONTRACTS = Object.freeze({
  home: Object.freeze([
    quickStep("orientation", GUIDE_ANCHORS.HOME_OVERVIEW),
    quickStep("workspace", GUIDE_ANCHORS.HOME_WORKSPACE),
    quickStep("foundation", GUIDE_ANCHORS.HOME_FOUNDATION),
    quickStep("interpret", GUIDE_ANCHORS.HOME_INTERPRETATION),
  ]),
  analysis: Object.freeze([
    quickStep("data", GUIDE_ANCHORS.SURVIVAL_DATASET, "data"),
    quickStep("marker", GUIDE_ANCHORS.SURVIVAL_MARKER, "design"),
    quickStep("outcome", GUIDE_ANCHORS.SURVIVAL_OUTCOME, "outcome"),
    quickStep("clinical", GUIDE_ANCHORS.SURVIVAL_CLINICAL, "clinical"),
    quickStep("review-run", GUIDE_ANCHORS.SURVIVAL_REVIEW, "review"),
    quickStep("interpret", GUIDE_ANCHORS.SURVIVAL_RESULTS),
  ]),
  compare: Object.freeze([
    quickStep("dataset", GUIDE_ANCHORS.COMPARE_DATASET, "dataset"),
    quickStep("markers", GUIDE_ANCHORS.COMPARE_MARKERS, "markers"),
    quickStep("methods", GUIDE_ANCHORS.COMPARE_METHODS, "methods"),
    quickStep("clinical", GUIDE_ANCHORS.COMPARE_CLINICAL, "filters"),
    quickStep("review-run", GUIDE_ANCHORS.COMPARE_REVIEW, "run"),
    quickStep("interpret", GUIDE_ANCHORS.COMPARE_RESULTS),
  ]),
  expression: Object.freeze([
    quickStep("dataset", GUIDE_ANCHORS.EXPRESSION_DATASET),
    quickStep("genes", GUIDE_ANCHORS.EXPRESSION_GENES),
    quickStep("groups", GUIDE_ANCHORS.EXPRESSION_GROUPS),
    quickStep("test-family", GUIDE_ANCHORS.EXPRESSION_TEST_FAMILY),
    quickStep("interpret", GUIDE_ANCHORS.EXPRESSION_RESULTS),
  ]),
  gsea: Object.freeze([
    quickStep("dataset", GUIDE_ANCHORS.GSEA_DATASET),
    quickStep("groups", GUIDE_ANCHORS.GSEA_GROUPS),
    quickStep("collection", GUIDE_ANCHORS.GSEA_COLLECTION),
    quickStep("interpret", GUIDE_ANCHORS.GSEA_RESULTS),
  ]),
  multiverse: Object.freeze([
    quickStep("dataset", GUIDE_ANCHORS.MULTIVERSE_DATASET, "dataset"),
    quickStep("marker", GUIDE_ANCHORS.MULTIVERSE_MARKER, "marker"),
    quickStep("decisions", GUIDE_ANCHORS.MULTIVERSE_DESIGN, "decisions"),
    quickStep("clinical", GUIDE_ANCHORS.MULTIVERSE_CLINICAL, "clinical"),
    quickStep("review-run", GUIDE_ANCHORS.MULTIVERSE_REVIEW, "run"),
    quickStep("interpret", GUIDE_ANCHORS.MULTIVERSE_RESULTS),
  ]),
  session: Object.freeze([
    quickStep("setup", GUIDE_ANCHORS.SESSION_SETUP),
    quickStep("ledger", GUIDE_ANCHORS.SESSION_LEDGER),
    quickStep("interpret", GUIDE_ANCHORS.SESSION_INTERPRETATION),
  ]),
  pancancer: Object.freeze([
    quickStep("mode", GUIDE_ANCHORS.PANCANCER_MODE),
    quickStep("design", GUIDE_ANCHORS.PANCANCER_QUERY),
    quickStep("eligibility", GUIDE_ANCHORS.PANCANCER_PREFLIGHT),
    quickStep("interpret", GUIDE_ANCHORS.PANCANCER_RESULTS),
  ]),
});

export const QUICK_GUIDE_STEP_COUNTS = Object.freeze(Object.fromEntries(
  QUICK_GUIDE_MODULE_ORDER.map((id) => [id, QUICK_GUIDE_STEP_CONTRACTS[id].length]),
));

export const SURVIVAL_QUICK_GUIDE_STEP_CONTRACT = QUICK_GUIDE_STEP_CONTRACTS.analysis;

export const KNOWN_GUIDE_ANCHORS = Object.freeze(
  Object.values(GUIDE_ANCHORS),
);

export function isKnownGuideAnchor(anchor) {
  return KNOWN_GUIDE_ANCHORS.includes(anchor);
}

export function guideAnchorDomId(anchor) {
  if (!isKnownGuideAnchor(anchor)) {
    throw new Error(`Unknown TRACE Explorer guide anchor: ${anchor}`);
  }
  return `trace-guide-${anchor.replaceAll(".", "-")}`;
}
