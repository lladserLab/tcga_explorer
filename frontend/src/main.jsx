import React, { lazy, Suspense, useEffect, useId, useMemo, useRef, useState } from "react";
import AuthorizedImage from "./AuthorizedImage";
import DesktopDownloads from "./DesktopDownloads";
import { resultSourceLabel } from "./resultSource";
import { createRoot } from "react-dom/client";
import { scientificEstimate, scientificNumber } from "./scientificNumbers";
import { referenceCohortId, tcgaReferenceCohorts } from "./pancancer/referenceCohorts";
import "@fontsource-variable/ibm-plex-sans/wght.css";
import "@fontsource-variable/ibm-plex-sans/wght-italic.css";
import {
  IconButton,
  ModuleIcon,
  TraceIcon,
} from "./design/icons";
import {
  apiUrl,
  authorizedFetch,
  createAnalysis,
  createAnalysesBatch,
  createCombinedAnalysis,
  createUserDataset,
  deleteUserDataset,
  createSignaturePanelAnalysis,
  createExploratorySession,
  createHierarchicalPanCancerSurvival,
  createMultiverseAnalysis,
  createPanCancerSurvival,
  getCancerRepositoryCoverage,
  getCohortEndpoints,
  getCohorts,
  getDataSources,
  getDatasetSummary,
  getExpressionScales,
  getFilterOptions,
  getHealth,
  getImmunePanCancerScreen,
  getHierarchicalPanCancerPreflight,
  getRepositoryDatasetEndpoints,
  getRepositoryDatasetCandidates,
  getRepositoryDatasets,
  getRepositoryExpressionLayers,
  getRepositoryFilterOptions,
  getUserDataset,
  getUserDatasetTemplateUrl,
  searchGenes,
  searchRepositoryGenes,
} from "./api";
import { formatApiError } from "./apiError";
import { clearActiveJob } from "./activeJobs";
import { cohortMatchesQuery, cohortPickerCountLabel } from "./cohortSearch";
import ExpressionDataSelector from "./expression/ExpressionDataSelector";
import { endpointsForExpressionLayer } from "./expression/expressionDataContract";
import {
  PUBLIC_ANALYSIS_BATCH_MAX,
  ROBUSTNESS_GENE_MAX,
  analysisFilterState,
  batchCapacityState,
  hierarchicalThresholdState,
  panCancerInputsFromSurvivalForm,
  parseSignatureGenesStrict,
  percentileInputState,
  plotStyleInputState,
  referencePanCancerInputState,
  signatureInputState,
} from "./analysisRequestContract";
import {
  MAX_EXTERNAL_COVARIATE_FILE_BYTES,
  changeExternalCovariateType,
  externalCovariateTypeOptions,
  parseExternalCovariateCsv,
  reorderExternalCovariateLevel,
  updateExternalCovariateDefinition,
} from "./externalCovariates";
import {
  SESSION_JOB_EVENT,
  beginNewSession,
  buildSessionExportPayload,
  loadSessionHistory,
  persistSessionHistory,
  reduceSessionJobUpdate,
  terminalSessionEntry,
  updateSessionEntry,
} from "./sessionHistory";
import {
  MAX_SIGNATURE_PANEL_SIZE,
  buildSignaturePanelRequest,
  createPanelSignature,
  validateSignaturePanel,
} from "./survival/signaturePanel";
import {
  multiversePercentileState,
  multiverseSignatureProjection,
} from "./survival/multiverseContract";
import PlotStylePreview from "./survival/ScientificPlotPreview";
import { metadataContextKey, metadataReady, survivalRequestFingerprint, survivalResultsAreStale } from "./survival/setupState";
import {
  DEFAULT_COMBINED_PALETTE,
  DEFAULT_PLOT_STYLE,
  PLOT_ARTIFACT_OPTIONS,
} from "./survival/plotPreviewContract";
import { createDefaultExpressionComparisonState } from "./expression/expressionComparisonContract";
import { adjustCompareResults, compareRequestContext, comparisonFamilySummary, compareSummaryCsv, requestedAdjustedModel } from "./compare/resultContract";
import {
  isGeneListClipboardValue,
  mergeClipboardGeneList,
} from "./geneListClipboard";
import DatasetProvenance from "./dataset/DatasetProvenance";
import ClinicalFilterControls from "./clinical/ClinicalFilterControls";
import MolecularPopulationSelector from "./MolecularPopulationSelector";
import {
  clinicalVariableDefinition,
  createDefaultGseaState,
} from "./gsea/gseaContract";
import {
  APP_NAV_GROUPS,
  APP_NAV_HOME,
  PAGE_META,
  getAppModule,
} from "./moduleRegistry";
import {
  GUIDE_ANCHORS,
  GuideAnchor,
  TUTORIAL_DOCK_ID,
  TUTORIAL_CONCEPT_IDS,
  TutorialDock,
  TutorialLibrary,
  applyTutorialPresetWithAdapters,
  focusGuideAnchor,
  guideAnchorDomId,
  legacyStaticMethodsHref,
  readTutorialUrlState,
  useTutorialController,
} from "./tutorials";
import { GUIDE_VIDEO_COPY } from "./help/registry";
import { GuideVideo } from "./tutorials/GuideVideo";
import {
  FieldHelp,
  FieldWithHelp,
  HelpButton,
  DesignLedger,
  LabelWithHelp,
  PanelHeader,
  Term,
  compareDesignLedger,
  multiverseDesignLedger,
  survivalDesignLedger,
  getHelpEntry,
  useHelpText,
} from "./help";
import {
  createCustomClinicalVariable,
  customClinicalCandidates,
  defaultEventMapping,
  eventValuesForColumn,
  humanFileSize,
  inspectUserDatasetFiles,
  loadUserDatasetReference,
  persistUserDatasetReference,
  USER_CLINICAL_MAX_BYTES,
  USER_EXPRESSION_MAX_BYTES,
  isLocalDesktop,
  loadLocalProjects,
  forgetLocalProject,
  validateCustomClinicalVariables,
} from "./userDataset";
import { activeWorkflowPanelId } from "./workflowAccessibility";
import {
  ActiveJobRecovery,
  DraftRecoveryNotice,
  ElapsedTime,
  ModuleErrorBoundary,
  ModuleLoadFallback,
  ServiceStatusNotice,
} from "./resilience/Resilience";
import {
  clearWorkspaceDraft,
  createWorkspaceDraft,
  loadWorkspaceDraft,
  persistWorkspaceDraft,
} from "./workspaceDraft";
import {
  defaultSamplePopulation,
} from "./samplePopulation";
import {
  MULTI_GENE_SIGNATURE_METHOD_OPTIONS,
  SIGNATURE_METHOD_OPTIONS,
  normalizeSignatureInput,
  rankScoringAvailability,
  signatureMethodDefinition,
  signatureMethodUsesDirection,
  signatureMethodUsesNumericWeights,
} from "./signatureScoring";
import {
  SignatureInputSummary,
  SignatureScoringCollectionSummary,
  SignatureScoringSummary,
} from "./signatureScoringUi";
import PanCancerSignatureMethodPicker from "./pancancer/PanCancerSignatureMethodPicker";
import {
  aggregateCohortCoverage,
  aggregatePublicCatalogCoverage,
  publicCoverageState,
} from "./homeCoverage";
import {
  cohortSupportsModule,
  datasetCapability,
  datasetSupportsModule,
  filterDatasetsForModule,
  moduleAnalysisLabel,
  normalizeAnalysisModule,
} from "./datasetCapabilities";
import ResultTabs, { ResultSection } from "./ResultTabs";
import "./styles.css";
import "./home.css";
import "./readability.css";

const loadRepositoryCatalog = () => import("./repository/RepositoryCatalog");
const loadExpressionComparisonModule = () => import("./expression/ExpressionComparisonModule");
const loadGseaModule = () => import("./gsea/GseaModule");
const loadHierarchicalPanCancerModule = () => import("./pancancer/HierarchicalPanCancerModule");
const RepositoryCatalog = lazy(loadRepositoryCatalog);
const ExpressionComparisonModule = lazy(loadExpressionComparisonModule);
const GseaModule = lazy(loadGseaModule);
const HierarchicalPanCancerModule = lazy(loadHierarchicalPanCancerModule);

const PAGE_MODULE_PRELOADERS = Object.freeze({
  expression: loadExpressionComparisonModule,
  gsea: loadGseaModule,
  pancancer: loadHierarchicalPanCancerModule,
  repository: loadRepositoryCatalog,
});

function preloadPageModule(page) {
  PAGE_MODULE_PRELOADERS[page]?.();
}

const CUTPOINTS = [
  { value: "maxstat", label: "Maxstat" },
  { value: "median", label: "Median" },
  { value: "tertiles", label: "Tertiles" },
  { value: "upper_quartile", label: "Upper quartile" },
  { value: "upper_lower_quartile", label: "Outer quartiles" },
  { value: "percentile", label: "Percentile" },
];

const DICHOTOMIZATION_METHODS = [
  "maxstat",
  "median",
  "upper_quartile",
  "upper_lower_quartile",
  "percentile",
];
const COX_MULTIVARIABLE_MODEL_OPTIONS = [
  ["stage_adjusted", "Ordinal stage"],
  ["grade_adjusted", "Ordinal grade"],
  ["stage_grade_adjusted", "Ordinal stage + grade"],
  ["user_adjusted", "Selected clinical covariates"],
];
const ROBUSTNESS_ALPHA = 0.05;

const EXPRESSION_SCALE_FALLBACK = [
  {
    value: "log2_tpm",
    label: "log2(TPM + 1)",
    note: "Recommended normalized scale for TCGA survival analysis.",
  },
  {
    value: "log2_cpm",
    label: "log2(CPM + 1)",
    note: "Computed from raw STAR counts as a count-based fallback.",
  },
  {
    value: "log2_fpkm",
    label: "log2(FPKM + 1)",
    note: "Log-transformed FPKM from cached GDC files.",
  },
  {
    value: "log2_fpkm_uq",
    label: "log2(FPKM-UQ + 1)",
    note: "Log-transformed upper-quartile FPKM from cached GDC files.",
  },
];

const COHORT_NAMES = {
  "TCGA-ACC": "Adrenocortical Carcinoma",
  "TCGA-BLCA": "Bladder Urothelial Carcinoma",
  "TCGA-BRCA": "Breast Invasive Carcinoma",
  "TCGA-CESC": "Cervical Squamous Cell Carcinoma and Endocervical Adenocarcinoma",
  "TCGA-CHOL": "Cholangiocarcinoma",
  "TCGA-COAD": "Colon Adenocarcinoma",
  "TCGA-DLBC": "Lymphoid Neoplasm Diffuse Large B-cell Lymphoma",
  "TCGA-ESCA": "Esophageal Carcinoma",
  "TCGA-GBM": "Glioblastoma Multiforme",
  "TCGA-HNSC": "Head and Neck Squamous Cell Carcinoma",
  "TCGA-KICH": "Kidney Chromophobe",
  "TCGA-KIRC": "Kidney Renal Clear Cell Carcinoma",
  "TCGA-KIRP": "Kidney Renal Papillary Cell Carcinoma",
  "TCGA-LAML": "Acute Myeloid Leukemia",
  "TCGA-LGG": "Brain Lower Grade Glioma",
  "TCGA-LIHC": "Liver Hepatocellular Carcinoma",
  "TCGA-LUAD": "Lung Adenocarcinoma",
  "TCGA-LUSC": "Lung Squamous Cell Carcinoma",
  "TCGA-MESO": "Mesothelioma",
  "TCGA-OV": "Ovarian Serous Cystadenocarcinoma",
  "TCGA-PAAD": "Pancreatic Adenocarcinoma",
  "TCGA-PCPG": "Pheochromocytoma and Paraganglioma",
  "TCGA-PRAD": "Prostate Adenocarcinoma",
  "TCGA-READ": "Rectum Adenocarcinoma",
  "TCGA-SARC": "Sarcoma",
  "TCGA-SKCM": "Skin Cutaneous Melanoma",
  "TCGA-STAD": "Stomach Adenocarcinoma",
  "TCGA-TGCT": "Testicular Germ Cell Tumors",
  "TCGA-THCA": "Thyroid Carcinoma",
  "TCGA-THYM": "Thymoma",
  "TCGA-UCEC": "Uterine Corpus Endometrial Carcinoma",
  "TCGA-UCS": "Uterine Carcinosarcoma",
  "TCGA-UVM": "Uveal Melanoma",
  "FU-GBC": "Gallbladder Cancer",
  "EXT-CLL": "Chronic Lymphocytic Leukemia",
  "EXT-NBL": "Neuroblastoma",
  "EXT-PLGG": "Pediatric Low-Grade Glioma",
  "EXT-SCLC": "Small-Cell Lung Cancer",
};

const REPOSITORY_CANCER_CODES = {
  "FU-GBC": "GBC",
  "EXT-CLL": "CLL",
  "EXT-NBL": "NBL",
  "EXT-PLGG": "PLGG",
  "EXT-SCLC": "SCLC",
};

const EMPTY_FILTERS = {
  sample_population: null,
  sample_types: [],
  stages: [],
  grades: [],
  genders: [],
  races: [],
  age_min: "",
  age_max: "",
  max_time_days: "",
  custom_filters: [],
};

const DEFAULT_ADJUSTMENT_COVARIATES = ["age_at_index"];
const CLINICAL_ADJUSTMENT_OPTIONS = [
  {
    value: "age_at_index",
    label: "Age",
    detail: "Continuous · HR per 10 years",
    availabilityField: "age",
  },
  {
    value: "stage",
    label: "Stage",
    detail: "Ordinal major-stage trend",
    availabilityField: "stages",
  },
  {
    value: "grade",
    label: "Grade",
    detail: "Ordinal G1–G5 trend",
    availabilityField: "grades",
  },
  {
    value: "gender",
    label: "GDC gender",
    detail: "Categorical treatment contrasts",
    availabilityField: "genders",
  },
  {
    value: "race",
    label: "GDC race",
    detail: "Categorical treatment contrasts",
    availabilityField: "races",
  },
];

const ANALYSIS_BATCH_CONCURRENCY = 10;
const ANALYSIS_WORKFLOW_STEPS = [
  { id: "data", label: "Data", iconRole: "module.dataset", guideAnchor: GUIDE_ANCHORS.SURVIVAL_DATASET },
  { id: "design", label: "Marker design", iconRole: "module.geneAnalysis", guideAnchor: GUIDE_ANCHORS.SURVIVAL_MARKER },
  { id: "outcome", label: "Outcome", iconRole: "module.survivalEndpoint", guideAnchor: GUIDE_ANCHORS.SURVIVAL_OUTCOME },
  { id: "clinical", label: "Patient filters and adjustment", iconRole: "module.clinicalFilters", guideAnchor: GUIDE_ANCHORS.SURVIVAL_CLINICAL },
  { id: "review", label: "Review & run", iconRole: "module.plotOutput", guideAnchor: GUIDE_ANCHORS.SURVIVAL_REVIEW },
];
const COMPARE_WORKFLOW_STEPS = [
  { id: "dataset", label: "Dataset", iconRole: "module.dataset", guideAnchor: GUIDE_ANCHORS.COMPARE_DATASET },
  { id: "markers", label: "Markers", iconRole: "module.geneAnalysis", guideAnchor: GUIDE_ANCHORS.COMPARE_MARKERS },
  { id: "methods", label: "Methods", iconRole: "module.stratification", guideAnchor: GUIDE_ANCHORS.COMPARE_METHODS },
  { id: "filters", label: "Clinical", iconRole: "module.clinicalFilters", guideAnchor: GUIDE_ANCHORS.COMPARE_CLINICAL },
  { id: "run", label: "Review & run", iconRole: "module.plotOutput", guideAnchor: GUIDE_ANCHORS.COMPARE_REVIEW },
];
const MULTIVERSE_WORKFLOW_STEPS = [
  { id: "dataset", label: "Dataset", iconRole: "module.dataset", guideAnchor: GUIDE_ANCHORS.MULTIVERSE_DATASET },
  { id: "marker", label: "Marker", iconRole: "module.geneAnalysis", guideAnchor: GUIDE_ANCHORS.MULTIVERSE_MARKER },
  { id: "decisions", label: "Decisions", iconRole: "module.specificationCurve", guideAnchor: GUIDE_ANCHORS.MULTIVERSE_DESIGN },
  { id: "clinical", label: "Clinical", iconRole: "module.clinicalFilters", guideAnchor: GUIDE_ANCHORS.MULTIVERSE_CLINICAL },
  { id: "run", label: "Review & run", iconRole: "module.plotOutput", guideAnchor: GUIDE_ANCHORS.MULTIVERSE_REVIEW },
];

function workflowStepControlId(step, idPrefix) {
  return step.guideAnchor
    ? guideAnchorDomId(step.guideAnchor)
    : `${idPrefix}-${step.id}`;
}
const NO_SURVIVAL_ENDPOINT = {
  value: "",
  label: "No time-to-event outcome",
  available: false,
  patients: 0,
  events: 0,
  reason: "No usable survival outcome is reported for this source. Molecular analyses remain available when supported by its expression coverage.",
  source: "",
};

const PANCANCER_ENDPOINTS = [
  { value: "OS", label: "Overall survival" },
  { value: "DSS", label: "Disease-specific survival" },
  { value: "PFI", label: "Progression-free interval" },
  { value: "DFI", label: "Disease-free interval" },
];

const PANCANCER_ENDPOINT_MODES = [
  {
    value: "same_endpoint",
    label: "Same outcome",
    help: "Use only the survival outcome you selected.",
  },
  {
    value: "death_like",
    label: "Allow death outcomes",
    help: "Use the selected death outcome first, then DSS or OS if needed.",
  },
  {
    value: "progression_like",
    label: "Allow progression outcomes",
    help: "Use the selected progression outcome first, then PFI or DFI if needed.",
  },
  {
    value: "best_available",
    label: "Allow any available outcome",
    help: "Use your selected outcome first; otherwise try DSS, PFI, DFI, then OS.",
  },
];

const HELP_GUIDE_SECTION_CONTRACT = Object.freeze([
  Object.freeze({
    anchor: GUIDE_ANCHORS.METHODS_ANALYSIS_INPUTS,
    title: "Analysis inputs",
    entryIds: Object.freeze([
      "defaultAnalysis",
      "dataset",
      "repository",
      "survivalEndpoint",
      "expressionScale",
      "clinicalFilters",
      "clinicalAdjustment",
      "externalCovariates",
      "maxFollowup",
    ]),
  }),
  Object.freeze({
    anchor: GUIDE_ANCHORS.METHODS_SIGNATURE_SCORING,
    title: "Signature scoring",
    entryIds: Object.freeze([
      "score.single",
      "score.singscore",
      "score.ssgsea",
      "score.aucell",
      "score.mean",
      "score.zscore",
      "score.weighted",
    ]),
  }),
  Object.freeze({
    anchor: GUIDE_ANCHORS.METHODS_STRATIFICATION,
    title: "Stratification",
    entryIds: Object.freeze([
      "cutpoint.maxstat",
      "cutpoint.median",
      "cutpoint.tertiles",
      "cutpoint.upper_quartile",
      "cutpoint.upper_lower_quartile",
      "cutpoint.percentile",
    ]),
  }),
  Object.freeze({
    anchor: GUIDE_ANCHORS.METHODS_SURVIVAL_OUTPUTS,
    title: "Survival outputs",
    entryIds: Object.freeze([
      "continuousModel",
      "spline",
      "kaplanMeier",
      "groupedCox",
      "signaturePanel",
      "sparseEventDiagnostics",
      "firthSensitivity",
      "coxPH",
      "rmst",
      "competingRisk",
      "audit",
    ]),
  }),
  Object.freeze({
    anchor: GUIDE_ANCHORS.METHODS_CROSS_MODULE,
    title: "Comparison, GSEA and pan-cancer",
    entryIds: Object.freeze([
      "compareRunSelected",
      "compareRobustness",
      "gseaTwoGroup",
      "multiverse",
      "sessionHistory",
      "pancancer",
      "pancancerEndpointMode",
    ]),
  }),
]);

/**
 * The Methods page renders the same registry entries the workspace shows in
 * place, so a definition can never drift between the two surfaces.
 */
function buildHelpGuideSections(t) {
  const sections = HELP_GUIDE_SECTION_CONTRACT.map((section) => ({
    anchor: section.anchor,
    title: section.title,
    items: section.entryIds.map((entryId) => [t.term(entryId), t(entryId)]),
  }));
  sections.push({
    anchor: GUIDE_ANCHORS.METHODS_GLOSSARY,
    title: "Statistical glossary",
    items: TUTORIAL_CONCEPT_IDS.map((conceptId) => {
      const concept = t.glossary(conceptId);
      return [concept.term, concept.definition];
    }),
  });
  return sections;
}

const INPUT_OUTPUT_TREE_BRANCHES = [
  {
    group: "Computed paths",
    id: "survival-one-marker",
    route: "Survival",
    scope: "One marker",
    formula: "1 cohort × 1 endpoint × 1 score",
    inputs: [
      "One gene, several genes analyzed separately, or one planned signature scored with singscore, ssGSEA, AUCell, mean, z-score or numeric weights.",
      "Maxstat, median, tertiles, upper quartile, outer quartiles or a declared percentile.",
      "RNA layer, filters, follow-up censoring, exact clinical or uploaded adjustment and plot styling.",
    ],
    execution: [
      "Continuous Cox per +1 within-run SD and a 3-df restricted cubic spline with 5/35/65/95% knots when at least 30 events are available.",
      "Grouped Kaplan-Meier and log-rank; grouped Cox and RMST only when the selected rule yields exactly two groups.",
      "DSS, DFI and PFI add cumulative incidence, Gray and Fine-Gray outputs when competing-event coding is available.",
    ],
    outputs: [
      "Continuous-effect, survival and eligible competing-risk figures plus model, group and RMST tables.",
      "One combined grouped Cox forest, or extra univariable and adjusted forests in Separate mode.",
      "PNG, SVG, CSV, JSON, TXT, methods, audit, signed receipt and reconstruction ZIP.",
    ],
    boundary: "Tertiles produce three groups, so binary grouped Cox and RMST are not estimated.",
  },
  {
    group: "Computed paths",
    id: "survival-two-signatures",
    route: "Survival",
    scope: "Two signatures",
    formula: "score A × score B",
    inputs: [
      "Exactly two independently defined scores; each can use any documented signature scoring method.",
      "Median × median creates four groups; tertiles × tertiles creates nine groups.",
      "One cohort, one endpoint, one RNA layer, shared filters and the same clinical adjustment specification.",
    ],
    execution: [
      "Patients require complete values for both scores before cross-stratification.",
      "Crossed-group Kaplan-Meier and log-rank plus continuous Cox: score A + score B + A×B.",
      "Unadjusted, ordinal stage, ordinal grade, stage + grade and exact user-adjusted interaction models retain PH, information and Firth diagnostics.",
    ],
    outputs: [
      "Crossed survival figure, group counts and both score distributions.",
      "Cox table reporting signature A, signature B and interaction HRs for every evaluable model.",
      "Patient data, methodology, audit, signed receipt and reconstruction bundle.",
    ],
    boundary: "This tests exactly two-score interaction. It is not a three-or-more signature comparison, and its four or nine groups do not produce the binary grouped Cox/RMST forest.",
  },
  {
    group: "Computed paths",
    id: "compare",
    route: "Compare",
    scope: "Genes × cutpoints",
    formula: "G genes × C grouping rules",
    inputs: [
      "One cohort or curated release, one QC-eligible endpoint and one RNA layer.",
      "One or more individual genes and one or more grouping rules.",
      "Run all 5 selects maxstat, median, upper quartile, outer quartiles and the declared percentile; tertiles remain separately selectable.",
    ],
    execution: [
      "Each gene-rule cell is an independent Survival job with the same filters and adjustment.",
      "One cutpoint-independent continuous reference is deduplicated per gene.",
      "BH and Bonferroni are calculated across completed comparison cells.",
    ],
    outputs: [
      "Gene × cutpoint Kaplan-Meier matrix with per-cell plots and downloads.",
      "Continuous-reference table and grouped evidence table with HR, RMST, PH and time-varying diagnostics.",
      "Cell-level PNG, SVG, CSV, TXT, audit and ZIP artifacts.",
    ],
    boundary: "Compare currently accepts individual genes, not several separately named multi-gene signatures.",
  },
  {
    group: "Computed paths",
    id: "multiverse",
    route: "Robustness",
    scope: "Declared family",
    formula: "endpoints × scores × cutpoints ≤ 72",
    inputs: [
      "One gene with single-gene scoring, or one multi-gene definition evaluated with selected rank-based or numeric scoring methods.",
      "One or more QC-eligible endpoints and one or more cutpoint rules.",
      "One cohort or curated release, shared filters, adjustment and plot specification.",
    ],
    execution: [
      "Every combination of selected settings is fixed before running. The record retains every planned analysis.",
      "Continuous tests are deduplicated by endpoint × scoring method; grouped tests retain endpoint × scoring × cutpoint.",
      "BH and Bonferroni are calculated separately for continuous primary and grouped sensitivity families.",
    ],
    outputs: [
      "Continuous estimates, the grouped robustness curve and the complete analysis record.",
      "Completed, not-evaluable and failed specifications remain visible together.",
      "Curve SVG, specification and continuous CSVs, ledger JSON, audit, signed receipt and ZIP.",
    ],
    boundary: "Robustness varies scoring methods for one gene set; it does not compare several independently defined signatures.",
  },
  {
    group: "Computed paths",
    id: "gsea",
    route: "GSEA",
    scope: "Two-group pathways",
    formula: "group B − group A → ranked genes → gene sets",
    inputs: [
      "One broad normalized expression layer from TCGA, a curated release or a temporary private dataset.",
      "Two groups from standardized clinical fields, exact inherited survival assignments or one expression score.",
      "A frozen ImmPort or Gene Ontology BP/MF/CC collection, Welch t or signal-to-noise ranking, overlap limits, permutation count and seed.",
    ],
    execution: [
      "One sample per patient and complete-case variable genes enter both pathway layers.",
      "limma CAMERA estimates residual inter-gene correlation for every eligible set and tests a two-sided competitive B minus A contrast.",
      "BH-FDR is calculated from CAMERA p-values; deterministic gene-set permutations normalize descriptive ES to NES only.",
    ],
    outputs: [
      "NES DotPlot with point area mapped to min(−log10(CAMERA FDR), 10), a dark-blue–white–red NES scale centered at zero, right-side pathway labels and a table separating CAMERA evidence from descriptive ES, NES and leading edge.",
      "Ranked genes, exact group assignments and long-form leading-edge CSVs.",
      "SVG, JSON, methods, frozen collection manifest, audit and reconstruction ZIP.",
    ],
    boundary: "Expression-derived groups reuse the tested matrix; maxstat groups reuse an outcome-informed split. Both are labeled exploratory rather than independent validation.",
  },
  {
    group: "Computed paths",
    id: "pan-cancer",
    route: "Pan-cancer",
    scope: "Cross-cohort scan",
    formula: "1 marker × selected TCGA cancers",
    inputs: [
      "One gene or one defined multi-gene signature score through the web app, REST or MCP.",
      "Reference endpoint plus same-endpoint, death-like, progression-like or best-available matching.",
      "Index cohort, RNA scale, minimum patients/events and FDR threshold; REST and MCP can also restrict the cancer subset.",
    ],
    execution: [
      "One continuous Cox model per cancer reports HR per +1 within-cohort SD; stage and grade ordinal sensitivities remain separate model families.",
      "BH is applied within each model family. Eligible common-input effects are synthesized with REML, HKSJ inference and a 95% prediction interval.",
      "Only effects with a documented common score unit are pooled. Cohort-standardized or rank-based scores remain study-specific unless the synthesis contract declares a comparable scale.",
    ],
    outputs: [
      "Forest plot, concordance map, evidence landscape, power/precision map and cohort table.",
      "Primary-versus-adjusted sensitivity plot and model-family meta-analysis summaries.",
      "Cohort CSV, patient data, methodology, audit, signed receipt and ZIP.",
    ],
    boundary: "Each scan uses one gene or one signature. It does not compare several distinct signatures in the same scan.",
  },
  {
    group: "Catalog and evidence paths",
    id: "dataset-repository",
    route: "Dataset + Repository",
    scope: "Input discovery",
    formula: "catalog query → exact data release",
    inputs: [
      "Dataset inventory with an optional TCGA cohort filter.",
      "Repository search by cancer, release status and curated independent bulk RNA-seq dataset.",
      "Exact release, expression layer, endpoint inventory and immutable source manifest.",
    ],
    execution: [
      "Summarize cohort, patient, sample, endpoint and source-date coverage.",
      "Resolve repository QC, TCGA independence, license, patient linkage, endpoint events and checksums.",
      "Pass the selected release and layer into single-cohort Survival, Compare, GSEA or Robustness inputs.",
    ],
    outputs: [
      "Dataset metrics, distributions, endpoint coverage, provenance dates and summary CSV.",
      "Repository coverage, release metadata, source files, checksums and curation status.",
      "Analyze action with the selected independent release preloaded.",
    ],
  },
  {
    group: "Catalog and evidence paths",
    id: "immune-atlas",
    route: "Pan-cancer",
    scope: "Immune atlas",
    formula: "fixed genes × cancers × model families",
    inputs: [
      "A versioned immune-gene screen with results already computed; opening it does not run a new analysis.",
      "View family: primary, stage + grade, stage or grade.",
      "Pinned gene, cohort and pathway annotations from the screen manifest.",
    ],
    execution: [
      "Gene-cancer BH-FDR and gene-level random-effects meta-FDR are recomputed separately by model family.",
      "Availability-selected sensitivity classifies retained, attenuated, emerged and direction-changed signals.",
      "Mixed selected adjustment families are never meta-analyzed.",
    ],
    outputs: [
      "Recurrence, rare-versus-recurrent, meta-behavior, cancer burden, immune programs and context-specific extremes.",
      "Primary and ordinal-sensitivity model tables with not-evaluable results retained.",
      "Gene, cohort, term, sensitivity, audit, methodology and ZIP downloads.",
    ],
  },
  {
    group: "Catalog and evidence paths",
    id: "run-history",
    route: "Run history",
    scope: "Post hoc record",
    formula: "selected job events → unique hypotheses",
    inputs: [
      "Accepted Survival, Compare, GSEA, Robustness and Pan-cancer job references recorded locally in the browser.",
      "User-selected terminal events plus optional session label.",
      "No patient rows or uploaded covariate values are stored in local history.",
    ],
    execution: [
      "The server resolves authoritative requests and results, then deduplicates exact hypotheses.",
      "Continuous, grouped and two-signature interaction hypotheses receive separate BH and Bonferroni families.",
      "GSEA, Robustness and Pan-cancer jobs remain managed-family references and are not counted again.",
    ],
    outputs: [
      "Recorded runs and the testing families defined by your export.",
      "Runs CSV, hypotheses CSV and ledger JSON.",
      "Audit, methodology, signed receipt and ZIP for the selected post hoc scope.",
    ],
    boundary: "This record cannot prove that no other analyses occurred outside the selected browser history.",
  },
  {
    group: "Catalog and evidence paths",
    id: "examples",
    route: "Examples",
    scope: "Paper benchmark",
    formula: "fixed case × endpoint × method",
    inputs: [
      "Versioned manuscript benchmark with positive, unsupported, endpoint-sensitive and diagnostic cases.",
      "Selected marker-endpoint case, cutpoint method or advanced workflow example.",
      "Pinned data snapshot, pipeline versions and audit hashes.",
    ],
    execution: [
      "Read-only selection of already computed benchmark artifacts; no new analysis job is submitted.",
      "Continuous reference, grouped sensitivity and diagnostic counterexamples keep the manuscript analysis plan.",
      "Normal public-job retention does not remove the pinned benchmark.",
    ],
    outputs: [
      "Kaplan-Meier and Cox figures, continuous reference and cutpoint evidence matrix.",
      "Weighted-signature, two-marker and pan-cancer worked examples.",
      "Visible methods, diagnostics and benchmark provenance.",
    ],
  },
];

const METHOD_HISTORY = [
  {
    version: "server-attested-competing-risk-split-cox-contract-v6.22",
    title: "Declared primary Cox model",
    date: "2026-08",
    items: [
      "Without a declared clinical adjustment, the continuous univariable Cox model is primary and automatic stage or grade fits remain sensitivities.",
      "When covariates are selected before execution, the exact complete-case adjusted model becomes the declared primary result if evaluable.",
      "Choosing which fitted rows appear in a forest plot changes presentation only; changing covariates requires a new run.",
    ],
  },
  {
    version: "server-attested-competing-risk-split-cox-contract-v4.13",
    title: "Declared two-signature adjustment",
    date: "2026-08",
    items: [
      "The unadjusted signature-interaction model remains primary unless the request declares an exact clinical adjustment before execution.",
      "Automatic stage and grade interaction models remain visible sensitivity analyses and cannot become primary through availability alone.",
    ],
  },
  {
    version: "signature-panel-main-effects-cox-audit-v1.6",
    title: "Declared signature-panel adjustment",
    date: "2026-08",
    items: [
      "The joint unadjusted panel is primary unless an exact adjusted panel was requested and estimated on its declared complete-case population.",
      "Univariable terms and other available model families remain labelled context rather than interchangeable primary results.",
    ],
  },
  {
    version: "camera-estimated-correlation-bh-preranked-effect-contract-v2.1",
    title: "Explicit pathway direction semantics",
    date: "2026-08",
    items: [
      "Pathways meeting CAMERA FDR are summarized by CAMERA direction; descriptive NES direction never substitutes for the inferential direction.",
      "The result table names NES direction and CAMERA direction separately for every pathway and reports whether they agree.",
      "The competitive CAMERA test, per-set residual-correlation estimate, BH family, descriptive NES and DotPlot mappings are unchanged from v2.0.",
    ],
  },
  {
    version: "camera-estimated-correlation-bh-preranked-effect-contract-v2.0",
    title: "Correlation-aware pathway evidence",
    date: "2026-08",
    items: [
      "Primary pathway p-values now come from limma CAMERA with residual inter-gene correlation estimated separately for every eligible set, negative variance deflation disabled and a mean-variance trend in empirical-Bayes moderation.",
      "Benjamini-Hochberg FDR spans the complete eligible CAMERA family. Gene-set-permutation p-values are no longer reported or used as evidence.",
      "Weighted ES, NES and leading-edge genes remain descriptive effect summaries. The response records CAMERA and NES directions separately and flags disagreement.",
      "The DotPlot uses CAMERA FDR for point area and descriptive NES for horizontal position and color, making the two roles visible.",
      "Expression-derived groups retain conditional exploratory evidence and cannot be read as independent molecular confirmation.",
      "Completed v1 artifacts remain immutable; v2 uses a new response schema, cache identity, pinned limma 3.62.2 engine and audited R source.",
    ],
  },
  {
    version: "preranked-gene-set-permutation-bh-contract-v1.4",
    title: "Two-group preranked gene-set enrichment",
    date: "2026-07",
    items: [
      "Clinical groups now use a dataset-aware, versioned catalog with patient-level coverage and level counts, including curated TCGA-CDR fields and tumor-specific annotations such as BRCA PAM50, glioma IDH/1p19q and MSI.",
      "The catalog combines patient- and sample-level metadata for external releases, decodes bounded serialized source records and supports any declared numeric field; SCAN-B PAM50, receptor and nodal annotations are now available.",
      "Equivalent category spellings are canonicalized, diagnosis-level GDC fields require a primary-diagnosis row, and low-coverage or post-resection variables carry explicit cautions.",
      "Mirrored flat/JSON fields are coalesced, source missing sentinels are excluded, quantitative external fields use numeric cutpoints and levels with fewer than five patients remain visible but cannot form a group alone.",
      "Each requested field is validated against its selected cohort or release and its source field is retained in the result audit; stale levels are removed when the dataset changes.",
      "Expression-derived subtype annotations carry an explicit circularity warning. Identifiers, survival times, technical batches and undeclared marker-paper columns are not exposed as groupings.",
      "Groups can also use exact assignments inherited from a completed survival dichotomization, or one gene or multi-gene expression score.",
      "The ranking direction is fixed as group B minus group A; positive NES favors B and negative NES favors A.",
      "Weighted enrichment reuses one deterministic gene-set permutation null per overlap size and applies BH-FDR across every tested pathway.",
      "Frozen checksum-verified ImmPort and Gene Ontology BP/MF/CC collections plus pathway, ranking, assignment, leading-edge, methods and audit exports make each run inspectable.",
      "The pathway DotPlot maps point area to min(−log10(FDR), 10) and a dark-blue–white–red scale centered at zero to NES; legends sit above the clean panel, pathway labels sit at right and a dashed reference marks NES zero.",
      "Expression-derived and inherited maxstat groups carry explicit circularity notices.",
    ],
  },
  {
    version: "shared-plot-typography-frame-contract-v1.0",
    title: "Readable axes and explicit plot boundaries",
    date: "2026-07",
    items: [
      "Axis values and axis titles can independently use plain, bold, italic or bold italic text while retaining separate point-size controls.",
      "Every scientific plot can use an open panel, left-and-bottom L axes or a complete rectangular frame; the live preview mirrors the exported R figure.",
      "The shared settings apply to Kaplan-Meier, continuous Cox, grouped Cox and signature-panel forests, including separate univariable and multivariable files.",
      "The exact style remains in the request, methodology, audit and cache identity. It changes presentation only and does not refit or reinterpret a model.",
    ],
  },
  {
    version: "curated-external-rnaseq-repository-v1.49",
    title: "Dana-Farber clear-cell RCC atlas cohort",
    date: "2026-07",
    items: [
      "GSE309697 adds 22 clear-cell RCC patients with overall survival from diagnosis, including nine deaths and 13 censored observations.",
      "One local tumor is preferred per patient and a source-listed metastasis is used when local RNA is unavailable; one impossible interval and one irreconcilable composite linkage key are excluded.",
      "Twenty-three pinned Cufflinks files are aligned by symbol, and 109 rows belonging to 52 ambiguous symbols are excluded without aggregation, leaving 20,056 analyzable genes.",
      "The repository now contains 105 promoted releases and 13,612 expression-and-endpoint-complete patients across 30 of 33 TCGA cancer types.",
    ],
  },
  {
    version: "curated-external-rnaseq-repository-v1.48",
    title: "UROMOL early-stage bladder cancer cohort",
    date: "2026-07",
    items: [
      "E-MTAB-4321 adds 462 urothelial bladder tumors with positive progression-free follow-up, including 31 T2+/metastatic progression events and 431 censored observations.",
      "Fourteen zero-time censored source records are retained in the audit ledger and excluded before analysis; follow-up starts at surgery of the analyzed tumor.",
      "Pinned Cuffnorm FPKM values are transformed to log2(FPKM + 1). One truncated SRXN1 row and ambiguous multi-Ensembl symbols are excluded, leaving 37,909 analyzable symbols.",
      "At this release, the repository contained 104 promoted releases and 13,590 expression-and-endpoint-complete patients across 30 of 33 TCGA cancer types.",
    ],
  },
  {
    version: "curated-external-rnaseq-repository-v1.47",
    title: "MDX-BRCA tumor-enriched breast cancer cohort",
    date: "2026-07",
    items: [
      "GSE283522 adds 596 invasive breast tumors with exact overall-survival follow-up, including 193 deaths and 403 censored observations.",
      "The release starts from 1,013 source-designated invasive profiles and excludes 417 endpoint-incomplete cases, extra tumor regions, in situ lesions and experimental controls.",
      "Pinned featureCounts are converted to log2(CPM + 1); source-declared GRCh38 Ensembl release 104 mapping leaves 39,322 unambiguous gene symbols.",
      "The repository now contains 103 promoted releases and 13,140 expression-and-endpoint-complete patients across 30 of 33 TCGA cancer types.",
    ],
  },
  {
    version: "curated-external-rnaseq-repository-v1.46",
    title: "NKI breast and HMU stage I LUAD cohorts",
    date: "2026-07",
    items: [
      "GSE192341 adds 72 treatment-naive HER2-negative breast tumor biopsies with 14 source-coded recurrences and 58 censored RFS observations.",
      "GSE143486 adds 30 curative-intent resected stage I FFPE lung adenocarcinomas with 19 deaths and 11 censored OS observations; source selection used RIN greater than 2 rather than outcome.",
      "Pinned count processing retains 40,505 BRCA and 59,298 LUAD symbols. An all-NA LUAD row is excluded without imputation, while any partial count missingness remains a hard QC failure.",
      "The repository now contains 102 promoted releases and 12,544 expression-and-endpoint-complete patients across 30 of 33 TCGA cancer types.",
    ],
  },
  {
    version: "curated-external-rnaseq-repository-v1.45",
    title: "MSK resected PDAC disease-free survival cohort",
    date: "2026-07",
    items: [
      "GSE124231 adds 48 treatment-naive resected pancreatic ductal adenocarcinomas with 32 source-coded recurrences and 16 censored observations.",
      "A recorded linkage rule reconciles supplementary keys such as Pt 10 with GEO titles such as RNA-Seq PT10_1. Six clinical records without released RNA are excluded.",
      "Pinned HTSeq counts are converted to log2(CPM + 1); Ensembl release 75 mapping leaves 55,630 unambiguous gene symbols.",
      "The repository now contains 100 promoted releases and 12,442 expression-and-endpoint-complete patients across 30 of 33 TCGA cancer types.",
    ],
  },
  {
    version: "curated-external-rnaseq-repository-v1.44",
    title: "NYU stage I LUAD progression cohort",
    date: "2026-07",
    items: [
      "GSE229705 adds 123 treatment-naive stage I lung adenocarcinoma primary tumors with 45 source-coded progression events and 78 censored observations.",
      "Every tumor links one-to-one to the publication Source Data. PFS preserves second primary lung tumors, locoregional recurrence and systemic metastasis as the source event definition.",
      "Only the tumor member of each matched pair is analyzed. Raw featureCounts are converted to log2(CPM + 1), retaining 60,591 unique genes.",
      "The repository now contains 99 promoted releases and 12,394 expression-and-endpoint-complete patients across 30 of 33 TCGA cancer types.",
    ],
  },
  {
    version: "curated-external-rnaseq-repository-v1.43",
    title: "French PRAD-FR recurrence cohort",
    date: "2026-07",
    items: [
      "ICGC PRAD-FR adds 21 primary prostate adenocarcinomas with 14 recorded recurrence or progression events and 7 censored observations.",
      "An event requires both an exact recurrence interval and a recorded recurrence type. Censoring requires no recurrence record, complete remission at last follow-up and a positive follow-up interval.",
      "Four donors with a recurrence type but no exact interval are excluded. The source DESeq2 scale is preserved without a second logarithm, leaving 52,125 mapped genes.",
      "The repository now contains 98 promoted releases and 12,271 expression-and-endpoint-complete patients across 30 of 33 TCGA cancer types.",
    ],
  },
  {
    version: "private-user-dataset-contract-v2.0",
    title: "Temporary private expression and patient metadata",
    date: "2026-08",
    items: [
      "Expression Comparison and GSEA can use a de-identified CSV or TSV expression matrix linked by exact identifiers to patient metadata, including user-declared subtype annotations; a survival outcome is optional.",
      "When a time-to-event outcome is supplied, Survival, Compare and Robustness use only patients with complete time and event data. Missing outcomes do not remove otherwise valid patients from molecular analyses.",
      "Genes may be rows or columns. Declared TPM, FPKM, FPKM-UQ and CPM values receive one explicit log2(x + 1) transform; broad count matrices receive library-size CPM normalization; normalized scales remain unchanged.",
      "Imports require at least 10 expression-and-metadata-matched patients. Survival becomes available only with at least 10 complete outcomes, 5 events and 5 censored observations.",
      "Original uploads are discarded after validation. The normalized private release and its generated results are unlisted, deletable and expire after 24 hours.",
      "TRACE Explorer is the visible product, API and MCP name; /tcga_explorer and existing schema identifiers remain stable compatibility surfaces.",
    ],
  },
  {
    version: "signature-panel-main-effects-cox-audit-v1.0",
    title: "Multiple signatures on one common population",
    date: "2026-07",
    items: [
      "Survival Analysis now accepts two to six uniquely named signature definitions and estimates continuous main effects without searching cutpoints or interactions.",
      "Every final score is standardized per one within-panel SD after intersecting endpoint-complete patients with complete scores for every requested signature.",
      "The output separates one model per signature, a joint unadjusted model and an exact joint clinical-adjustment model when requested and evaluable.",
      "BH and Bonferroni corrections are applied to signature terms separately within the univariable, joint and adjusted families; score correlation and gene overlap remain descriptive.",
      "Decision-facing notices now distinguish the primary result, a requested adjustment, auxiliary sensitivities and provenance instead of presenting every diagnostic as an equivalent warning.",
    ],
  },
  {
    version: "curated-external-rnaseq-repository-v1.36",
    title: "Lap-NET1 pancreatic cancer trial cohort",
    date: "2026-07",
    items: [
      "GSE319924 adds 22 pretreatment laser-capture microdissected pancreatic tumor-cell profiles, with 11 overall-survival events, 11 censored observations and 27,769 unique genes.",
      "Stromal, post-treatment, surgical and technical-repeat libraries are excluded. S025T1R1 follows the source code's explicit low-depth QC exclusion at a pinned commit.",
      "Raw Entrez-level counts are normalized to log2(CPM + 1) and mapped through a pinned NCBI gene_info snapshot without online lookup.",
      "This first-line NP137 plus mFOLFIRINOX cohort is labelled as treatment-context specific. The repository now contains 85 promoted releases and 11,770 expression-and-endpoint-complete patients across 30 of 33 TCGA cancer types.",
    ],
  },
  {
    version: "curated-external-rnaseq-repository-v1.35",
    title: "Metastatic bladder cancer immunotherapy cohort",
    date: "2026-07",
    items: [
      "GSE176307 adds 78 bladder-primary patients treated with immune checkpoint blockade, with 48 overall-survival events, 30 censored observations and 58,387 unique genes.",
      "Eleven ureter or renal-pelvis primaries are excluded. BACI165_1 is retained for the only patient sequenced twice, using the pinned submitter key for deterministic linkage to the replacement Salmon matrix.",
      "GEO TPM is transformed to log2(TPM + 1). The endpoint keeps its source-defined OS label because the exact time origin is not stated.",
      "The repository now contains 84 promoted releases and 11,748 expression-and-endpoint-complete patients across 30 of 33 TCGA cancer types.",
    ],
  },
  {
    version: "curated-external-rnaseq-repository-v1.34",
    title: "Korean hepatocellular carcinoma cohort",
    date: "2026-07",
    items: [
      "GSE148355 adds 52 HCC tumors with 21 postoperative disease-free-survival events, 31 censored observations and 55,468 unambiguous genes.",
      "Commit-pinned clinical records map directly to GEO sample titles. One high-grade dysplastic nodule and one combined HCC-intrahepatic-cholangiocarcinoma tumor are excluded; two retained technical replicates use deterministic unsuffixed clinical identifiers.",
      "Source-provided quantile-normalized FPKM is transformed to log2(FPKM + 1), with every occurrence of a duplicated case-insensitive symbol excluded.",
      "The repository now contains 83 promoted releases and 11,670 expression-and-endpoint-complete patients across 30 of 33 TCGA cancer types.",
    ],
  },
  {
    version: "curated-external-rnaseq-repository-v1.33",
    title: "Two pretreatment cervical cancer cohorts",
    date: "2026-07",
    items: [
      "GSE151666 and GSE275914 add two non-overlapping WUSTL cervical cancer releases with 99 endpoint-complete patients, 39 deaths and 60 censored observations.",
      "Pinned Nature source data provide individual overall-survival records; library keys link one-to-one through GEO metadata to expression columns without reconstructing values from a survival curve.",
      "Both source FPKM matrices are transformed to log2(FPKM + 1). All occurrences of 302 ambiguous symbols are excluded, leaving 56,332 unique symbols per release.",
      "The two batches remain separate analysis options. The repository now contains 82 promoted releases and 11,618 expression-and-endpoint-complete patients across 30 of 33 TCGA cancer types.",
    ],
  },
  {
    version: "curated-external-rnaseq-repository-v1.32",
    title: "NIBIT-EPI-MESO mesothelioma cohort",
    date: "2026-07",
    items: [
      "The NIBIT-EPI-MESO release adds 82 malignant pleural mesothelioma patients with 69 overall-survival events, 13 censored observations and 22,896 usable genes.",
      "The pinned Zenodo expression and clinical sources retain their documented log2(TPM + 1) scale and remain separate from the existing NCI mesothelioma cohort.",
      "The repository reached 80 promoted releases and 11,519 expression-and-endpoint-complete patients across 30 of 33 TCGA cancer types.",
    ],
  },
  {
    version: "curated-external-rnaseq-repository-v1.31",
    title: "Primary pancreatic cancer cohort",
    date: "2026-07",
    items: [
      "GSE205154 adds 216 primary pancreatic ductal adenocarcinoma patients with 171 deaths and 45 censored observations.",
      "One profile per patient is selected before endpoint evaluation, and the source publication's figure-specific exclusion of deaths within 30 days is not applied.",
      "Pinned source TPM and matching GENCODE v24 annotation reproduce 58,375 unambiguous genes at log2(TPM + 1).",
      "The repository reached 79 promoted releases and 11,437 expression-and-endpoint-complete patients across 30 of 33 TCGA cancer types.",
    ],
  },
  {
    version: "curated-external-rnaseq-repository-v1.30",
    title: "Primary synovial sarcoma cohort",
    date: "2026-07",
    items: [
      "GSE271517 adds 49 primary synovial sarcoma patients with 20 deaths and 29 censored observations.",
      "Metastatic-only profiles and additional longitudinal tumors are excluded before endpoint QC, leaving one prespecified profile per patient.",
      "Pinned raw counts are normalized to log2(CPM + 1) and mapped through Ensembl 75, retaining 53,555 unambiguous symbols.",
      "The repository reached 78 promoted releases and 11,221 expression-and-endpoint-complete patients across 30 of 33 TCGA cancer types.",
    ],
  },
  {
    version: "curated-external-rnaseq-repository-v1.29",
    title: "Gastric cancer survival cohort",
    date: "2026-07",
    items: [
      "GSE236522 adds 33 gastric cancer patients with seven deaths, 26 censored observations and 36,134 HUGO-mapped genes.",
      "The source OS origin remains explicitly unspecified, and the small event count is retained as a visible caveat.",
      "Source FPKM is transformed once to log2(FPKM + 1); unmapped and repeated symbols are excluded rather than inferred or averaged.",
      "The repository reached 77 promoted releases and 11,172 expression-and-endpoint-complete patients across 30 of 33 TCGA cancer types.",
    ],
  },
  {
    version: "curated-external-rnaseq-repository-v1.28",
    title: "PLANet liver cancer recurrence cohort",
    date: "2026-07",
    items: [
      "The independent PLANet cohort adds 109 resected hepatocellular carcinoma patients with time-to-recurrence follow-up, including 56 recurrences and 53 censored observations.",
      "One of 393 mapped tumor regions is selected per patient by greatest total raw-count library size before endpoint evaluation; exact ties use sample ID.",
      "Pinned Zenodo and publisher files reproduce 60,587 usable symbols at log2(CPM + 1), while the endpoint remains labelled TTR rather than being silently equated with RFS.",
      "Matrix download is disabled under the combined CC BY 4.0 and CC BY-NC-ND 4.0 source boundary, although in-app analysis remains available.",
      "The repository now contains 76 promoted releases and 11,139 expression-and-endpoint-complete patients across 30 of 33 TCGA cancer types.",
    ],
  },
  {
    version: "curated-external-rnaseq-repository-v1.27",
    title: "Independent stage I lung adenocarcinoma cohorts",
    date: "2026-07",
    items: [
      "GSE273377 adds separate discovery and validation LUAD releases with 160 endpoint-complete patients, 24 seven-year RFS events and 136 censored observations.",
      "The cohorts remain separate because they differ by center, sequencing platform and batch; no cross-study pooling or expression harmonization is applied.",
      "One repeated validation patient is resolved by a prespecified transcript-integrity rank, while missing and non-positive follow-up remain explicit exclusions.",
      "Pinned ZIP/XLSX clinical evidence and fractional RSEM expected counts are now supported without relaxing integer validation for other count matrices.",
      "The repository now contains 75 promoted releases and 11,030 expression-and-endpoint-complete patients across 30 of 33 TCGA cancer types.",
    ],
  },
  {
    version: "curated-external-rnaseq-repository-v1.26",
    title: "Whole-transcriptome pancreatic cancer cohort",
    date: "2026-07",
    items: [
      "The Medical College of Wisconsin GSE313117 cohort adds 79 pancreatic ductal adenocarcinoma patients with whole-transcriptome bulk RNA-seq, 60 overall-survival events and 19 censored observations.",
      "All matched exome-capture profiles are excluded before analysis, so each patient contributes once and sequencing platforms are not mixed.",
      "The pinned GEO clinical CSV maps all 79 rnaseq libraries one-to-one; source TPM is transformed to log2(TPM + 1) across 24,416 unique symbols.",
      "The repository now contains 73 promoted releases and 10,870 expression-and-endpoint-complete patients across 30 of 33 TCGA cancer types; TGCT, THYM and UCS remain documented evidence gaps.",
    ],
  },
  {
    version: "curated-external-rnaseq-repository-v1.25",
    title: "Pretreatment rectal cancer DFS cohort",
    date: "2026-07",
    items: [
      "The Frankfurt GSE190826 cohort adds 86 pretreatment rectal-cancer biopsies with 29 source-provided DFS events and 57 censored observations.",
      "All 12 post-chemoradiotherapy profiles are excluded before endpoint QC, and GSE156281 is not counted separately after 95 exact count-vector duplicates were confirmed.",
      "Pinned per-sample featureCounts files are normalized to log2(CPM + 1), retaining 39,016 unambiguous mapped symbols and the exact clinical linkage from Supplementary Table S1.",
      "The repository reached 72 promoted releases and 10,791 expression-and-endpoint-complete patients across 30 of 33 TCGA cancer types.",
    ],
  },
  {
    version: "curated-external-rnaseq-repository-v1.24",
    title: "Postoperative EAC disease-free survival cohort",
    date: "2026-07",
    items: [
      "The Humanitas GSE273848 cohort adds 20 esophageal adenocarcinoma primary tumors with direct bulk total RNA-seq, 12 postoperative DFS events and eight censored observations.",
      "DFS records are transcribed from the CC BY 4.0 supplement after verifying that the article's local DFS curve uses the published relapse/progression follow-up months; two tumors without postoperative status are excluded.",
      "Pinned FeatureCounts libraries are normalized as log2(CPM + 1); the malformed final non-tumor source column is documented and never selected.",
      "Pathologic TNM strings remain in provenance but are not mislabelled as ordinal AJCC stage groups; grade and sex are the available clinical covariates.",
      "The repository now contains 71 promoted releases and 10,705 patients across 30 of 33 TCGA cancer types; TGCT, THYM and UCS remain documented evidence gaps.",
    ],
  },
  {
    version: "curated-external-rnaseq-repository-v1.23",
    title: "Pretreatment nivolumab melanoma cohort",
    date: "2026-07",
    items: [
      "The Riaz et al. cohort adds 51 advanced-melanoma patients with pretreatment bulk RNA-seq, 34 overall-survival events and 17 censored observations.",
      "All 56 source-labelled on-treatment biopsies are excluded before patient selection; the source-provided iAtlas log-TPM values are preserved without a second logarithm.",
      "The immutable release pins the DataHub repository-level ODbL statement as checksummed license evidence.",
      "The repository now contains 70 promoted releases and 10,685 patients across 30 of 33 TCGA cancer types; TGCT, THYM and UCS remain documented evidence gaps.",
    ],
  },
  {
    version: "curated-external-rnaseq-repository-v1.22",
    title: "Independent CGGA glioma validation cohorts",
    date: "2026-07",
    items: [
      "Four adult primary glioma releases from the independent CGGA mRNAseq_693 and mRNAseq_325 sequencing batches add 400 LGG and 216 GBM patients with individual overall-survival follow-up.",
      "Exact 2020-05-06 clinical and STAR+RSEM FPKM archives are pinned by byte size and SHA-256; the two batches share no identifiers or exact complete clinical fingerprints and remain separate analysis options.",
      "Ordinal clinical models now recognize numeric, G-prefixed and WHO Roman-numeral grades. CGGA matrix downloads remain disabled because the open-access source requests citation without granting a specific redistribution license.",
      "The repository now contains 69 promoted releases and 10,634 patients across 30 of 33 TCGA cancer types; TGCT, THYM and UCS remain documented evidence gaps.",
    ],
  },
  {
    version: "curated-external-rnaseq-repository-v1.21",
    title: "Independent renal cohorts and 10,000-patient milestone",
    date: "2026-07",
    items: [
      "Independent CPTAC and FUSCC clear-cell renal carcinoma releases add 188 expression-and-endpoint-complete patients across primary-tumor and sunitinib-treated settings.",
      "The FUSCC release exposes PFS with 83 events and OS with 71 deaths; its 94 RNA identifiers link exactly to the published clinical workbook.",
      "Pinned Europe PMC supplements are verified by byte size and SHA-256. Genes with any missing FPKM value are excluded without imputation, leaving 11,208 complete symbols transformed to log2(FPKM + 1).",
      "The repository now contains 65 promoted releases and 10,018 patients across 30 of 33 TCGA cancer types; TGCT, THYM and UCS remain documented evidence gaps.",
    ],
  },
  {
    version: "curated-external-rnaseq-repository-v1.4",
    title: "Independent primary uveal melanoma cohort",
    date: "2026-07",
    items: [
      "E-MTAB-4097 adds 74 primary uveal melanomas with public bulk RNA-seq counts, 40 overall-survival events and 34 censored observations.",
      "Published SDRF filenames link every count profile to one tumor and one clinical record; deaths from disease and other causes are retained as overall-survival events.",
      "Pinned BioStudies archives, the clinical supplement and Ensembl release 75 annotation reproduce a log2(CPM + 1) matrix with 55,494 usable gene symbols.",
      "Twenty-nine of 33 TCGA cancer types now have at least one promoted external cohort; TGCT, THCA, THYM and UCS remain documented evidence gaps.",
    ],
  },
  {
    version: "curated-external-rnaseq-repository-v1.3",
    title: "Independent chromophobe and papillary kidney cohorts",
    date: "2026-07",
    items: [
      "A public rare-kidney-cancer transcriptome atlas adds independent KICH and KIRP releases with patient-linked overall survival.",
      "KICH retains 27 patients with 17 events after deterministic one-sample-per-patient selection; KIRP retains 34 patients with 16 events.",
      "Pinned Figshare file IDs and MD5/SHA-256 checksums protect the source snapshot, and raw gene counts are converted reproducibly to log2(CPM + 1).",
      "Twenty-eight of 33 TCGA cancer types now have at least one promoted external cohort; TGCT, THCA, THYM, UCS and UVM remain under active review.",
    ],
  },
  {
    version: "curated-external-rnaseq-repository-v1.2",
    title: "Independent mesothelioma cohort",
    date: "2026-07",
    items: [
      "An independent NCI mesothelioma cohort adds 99 patients with biopsy-linked bulk RNA-seq and overall survival, including 56 events and 43 censored observations.",
      "The published TMM-normalized log2 CPM scale is preserved; explicit Excel-date repairs recover MARCH symbols and duplicate symbols remain excluded.",
      "The source license is retained as CC BY-NC-ND 4.0, so the cohort can be analyzed but its derived expression matrix is not offered for download.",
      "Twenty-six of 33 TCGA cancer types now have at least one promoted external cohort. The seven remaining gaps keep accession-level exclusion evidence.",
    ],
  },
  {
    version: "optional-split-cox-forest-v1.0",
    title: "Optional separate Cox model forests",
    date: "2026-07",
    items: [
      "The grouped Cox forest remains combined by default, preserving existing request semantics and combined download names.",
      "Separate mode adds one figure for the completed univariable model and one for all completed adjusted multivariable models; an empty model family is not rendered.",
      "Colors, axes and typography remain shared while combined, univariable and multivariable titles can be edited independently.",
      "The selected arrangement, completed model-family counts and generated files are retained in metrics, methods, audit artifacts and reconstruction exports without changing any Cox fit.",
    ],
  },
  {
    version: "curated-external-rnaseq-repository-v1.1",
    title: "Curated independent RNA-seq cohorts",
    date: "2026-07",
    items: [
      "Survival, Compare, GSEA and Robustness can use one immutable external bulk RNA-seq release with linked clinical outcomes; Pan-cancer remains TCGA-only.",
      "Twenty-five of 33 TCGA cancer types now have at least one promoted independent cohort from cBioPortal, GDC, GEO, Europe PMC or ICGC.",
      "Every promoted release passes explicit minimum patient, event, censored-observation and gene thresholds plus checksum, linkage, license and TCGA-independence review.",
      "Source units and transformations are dataset-specific and remain visible in the interface, provenance record and downloadable manifest.",
      "The coverage ledger records why KICH, KIRP, MESO, TGCT, THCA, THYM, UCS and UVM currently remain evidence gaps instead of silently counting ineligible arrays, controlled data or endpoint-free matrices.",
    ],
  },
  {
    version: "spline-temporal-information-contract-v6.2",
    title: "Information-aware nonlinear and temporal diagnostics",
    date: "2026-07",
    items: [
      "Restricted cubic splines now require at least 30 events, equivalent to 10 events per fitted spline parameter.",
      "Completed splines report fitted parameters, events per parameter and the same information-status vocabulary used by Cox models.",
      "Marker-specific PH cautions retain the fixed 2-year primary split and add fixed 1- and 5-year sensitivity splits.",
      "Temporal outputs identify the Wald marker-by-period contrast and state that a two-period model is a coarse approximation to smoothly varying effects.",
    ],
  },
  {
    version: "release-identity-ci-contract-v1.0",
    title: "Verifiable release identity",
    date: "2026-07",
    items: [
      "The public health endpoint reports the deployed source commit and release reference configured by the operator.",
      "Final browser evidence is accepted only when the clean tagged checkout matches the commit and release ref reported by the HTTPS deployment.",
      "A manual release-readiness workflow reruns backend, frontend, publication, browser, metadata and archive checks against one exact tag.",
      "Development deployments remain labeled as development and cannot satisfy the final-release evidence requirements.",
    ],
  },
  {
    version: "exploratory-session-family-v1.0",
    title: "Optional exploratory run history",
    date: "2026-07",
    items: [
      "Opt-in browser-local recording captures accepted Survival, Compare, GSEA, Robustness and Pan-cancer jobs without storing patient records or uploaded covariate rows.",
      "Selected exports resolve authoritative requests and results from server job IDs and retain repeated run events while deduplicating exact hypotheses.",
      "Continuous Cox, grouped cutpoint and two-signature interaction tests receive separate export-defined BH and Bonferroni families.",
      "Prespecified GSEA, Robustness and pan-cancer families retain their internal correction and are referenced without double counting.",
      "The audit and signed receipt state that the post hoc export covers only selected events and cannot attest that no other analyses occurred.",
    ],
  },
  {
    version: "server-attestation-contract-v1.0",
    title: "Server-signed audit receipts",
    date: "2026-07",
    items: [
      "Every new analysis, Robustness analysis, pan-cancer scan and exploratory session export receives a detached Ed25519 receipt for its exact audit report.",
      "The signed payload binds audit bytes, SHA-256, schema and the recorded reproducibility or family hash.",
      "Public keys are identified by their full SHA-256 fingerprint and retrieved from the declared HTTPS API.",
      "A valid receipt establishes server origin for one report; it does not establish scientific correctness or append-only time.",
    ],
  },
  {
    version: "competing-risk-estimand-contract-v1.0",
    title: "Competing deaths retained as competing events",
    date: "2026-07",
    items: [
      "DSS, DFI and PFI now use the explicit 0=censored, 1=event of interest and 2=competing death coding in TCGA-CDR ExtraEndpoints.",
      "Grouped outputs report nonparametric cumulative incidence, pointwise confidence intervals, support at 1, 3 and 5 years and Gray's K-sample test.",
      "Grouped and continuous Fine-Gray models report subdistribution hazard ratios with model-specific patients, target events, competing events, fitted parameters and low-information cautions.",
      "The competing-risk status, coding, results, plot and exact R implementation are retained in methodology, audit and reproduction exports.",
    ],
  },
  {
    version: "prespecified-time-varying-effect-v1.1",
    title: "Marker effects over prespecified follow-up splits",
    date: "2026-07",
    items: [
      "A marker-specific cox.zph p-value below 0.05 triggers a two-period Cox diagnostic rather than discarding the model.",
      "The primary split remains fixed at 730.5 days; one- and five-year splits are reported as prespecified sensitivities when support permits.",
      "Early and late HRs, their Wald interaction ratio, confidence intervals, period events and patients entering the late period are reported.",
      "At least five events per period and ten patients entering the late period are required; otherwise the reason remains visible.",
      "Every two-period result is labelled as a coarse diagnostic approximation to an effect that may vary smoothly over follow-up.",
    ],
  },
  {
    version: "external-covariate-adjustment-contract-v1.0",
    title: "User-supplied cohort covariates",
    date: "2026-07",
    items: [
      "Survival, Compare, GSEA and Robustness accept a patient-level CSV linked by exact public TCGA participant barcodes.",
      "Continuous, categorical and ordinal variables record their effect unit, reference category or declared level order before execution.",
      "No uploaded variable enters a model until it is selected explicitly; each adjusted fit reports complete-case patients, events, coding and information diagnostics.",
      "The normalized dataset, SHA-256, matching and missingness QC, patient-level values and selected specification are retained in methodology and audit exports.",
    ],
  },
  {
    version: "public-api-cli-v1.0",
    title: "Standalone public API command line",
    date: "2026-07",
    items: [
      "A dependency-free Python client checks the live OpenAPI schema before submitting public compute jobs.",
      "Single, combined-signature, batch, Robustness and pan-cancer requests can be submitted and polled outside the browser.",
      "Retained artifacts can be downloaded recursively with a local SHA-256 transfer manifest.",
      "Analysis, Robustness and pan-cancer ZIP bundles receive family-aware integrity verification without changing statistical results.",
    ],
  },
  {
    version: "browser-gene-suggestion-contract-v1.0",
    title: "Browser compatibility and reliable gene suggestions",
    date: "2026-07",
    items: [
      "Partial gene text is no longer committed when a workflow step moves focus before cohort suggestions arrive.",
      "Single-signature, crossed-signature, Compare, GSEA and Robustness searches cancel obsolete responses and expose accessible loading and error states.",
      "A versioned Playwright suite exercises Survival, Compare, Reference Analyses, Pan-cancer, Dataset Summary, downloads, keyboard focus and reduced motion.",
      "Provisional checks run in Chromium, Firefox/Gecko and WebKit; final evidence must target the exact tagged HTTPS release.",
    ],
  },
  {
    version: "runtime-identity-contract-v1.0",
    title: "Runtime evidence and canonical identity",
    date: "2026-07",
    items: [
      "TRACE Explorer is the canonical interface, API, MCP and manuscript name; the /tcga_explorer URL remains a compatibility route.",
      "Generated manuscript files and the review archive use the tcga-trace prefix and bind the canonical project name in the archive manifest.",
      "Existing tcga-trace schema, CLI and archive identifiers remain readable so previously exported records and integrations do not become ambiguous.",
      "A public-API benchmark records uncached and cached analyses, two-job concurrency, batch, a 72-cell Robustness analysis and 33-cohort pan-cancer execution.",
      "The benchmark reports wall, queue and compute time, observed Docker cgroup memory, hardware, pipeline versions, data snapshot and queue limits.",
    ],
  },
  {
    version: "endpoint-score-interpretation-contract-v1.0",
    title: "Endpoint and score interpretation",
    date: "2026-07",
    items: [
      "Z-score signatures now state that their reference population is defined by the expression-complete patients eligible in the current run.",
      "DSS, DFI and PFI notices distinguish Kaplan-Meier and cause-specific Cox from cumulative-incidence and subdistribution estimands.",
      "The same interpretation context is exposed in parameter help, result notices, methodology text and JSON/HTML audit exports.",
      "These notices are informational and do not change cohort eligibility, estimates or model status.",
    ],
  },
  {
    version: "common-scale-reml-hksj-integrity-contract-v2.8",
    title: "Comparable pan-cancer synthesis",
    date: "2026-07",
    items: [
      "Per-cohort Cox effects remain visible per within-cohort expression SD and are explicitly non-pooled.",
      "Single-gene and mean/weighted-signature effects are additionally recovered per +1 shared input-score unit for comparable synthesis.",
      "Pan-cancer synthesis now uses REML random effects, HKSJ inference and a 95% prediction interval.",
      "Mixed endpoints, mixed selected adjustment families and cohort-standardized z-score signatures do not receive a pooled estimate.",
      "The forest plot switches between common-unit synthesis and descriptive within-cohort-SD views without placing a pooled diamond on the latter scale.",
    ],
  },
  {
    version: "artifact-specific-cox-plot-style-v1.1",
    title: "Artifact-specific Cox plot styling",
    date: "2026-07",
    items: [
      "Kaplan-Meier, continuous spline and grouped Cox forest artifacts now have distinct color and title controls.",
      "Continuous-effect axis titles and the Cox forest hazard-ratio axis title can be customized without changing model labels, contrasts or estimates.",
      "Multivariable forests can show every evaluable adjusted model or a declared subset; changing the subset creates a new recorded analysis run.",
      "Typography and grid settings remain shared; aspect ratio applies to Kaplan-Meier and continuous-effect plots while Cox forest height follows its model count.",
      "The exact style specification is retained in the request, audit report, methodology export and artifact checksums; statistical results are unchanged.",
    ],
  },
  {
    version: "integrity-boundary-numeric-policy-v1.0",
    title: "Explicit integrity boundary",
    date: "2026-07",
    items: [
      "Audit reports now state that unsigned hashes detect accidental drift or corruption but do not establish authorship or resist adversarial recomputation.",
      "Request, participant, scoring, source-data and core-result fields are bound by the reproducibility hash; plots and methods text retain separate artifact checksums.",
      "Standalone reruns compare counts and categorical fields exactly and apply recorded absolute-plus-relative tolerances by numeric quantity.",
      "Reproduction results record the maximum absolute and relative error observed for each numeric class.",
    ],
  },
  {
    version: "standalone-reproduction-capsule-v1.0",
    title: "Standalone analysis reproduction",
    date: "2026-07",
    items: [
      "Every completed two-group analysis now exports its exact patient-level R input, statistical engine and helper scripts.",
      "The ZIP includes an executable R runner, renv.lock, a Dockerfile pinned to an immutable R base-image digest, instructions and a checksummed capsule manifest.",
      "The runner reconstructs core outputs without FastAPI, PostgreSQL or the original TCGA expression matrix and reports numerical differences under the quantity-aware policy recorded in the capsule.",
      "Clean-container tests disable network access, mount the capsule read-only and run on native arm64 plus amd64; an independent Linux/amd64 CI job repeats the verification.",
    ],
  },
  {
    version: "prespecified-multiverse-family-v1.1",
    title: "Prespecified multiverse and specification curve",
    date: "2026-07",
    items: [
      "A declared endpoint by scoring by cutpoint grid is frozen before execution and retained as a complete family ledger.",
      "Cutpoint-independent continuous Cox tests are counted once per endpoint and scoring method; grouped sensitivities form a separate multiplicity family.",
      "Maxstat contributes its Lau94 corrected rank-statistic p-value to multiplicity while its grouped effect estimates remain explicitly post-selection.",
      "The export includes a specification curve, compact result tables, child analysis IDs, audit hashes and failures without a binary evidence verdict.",
      "Specification columns use the available plot width for small families and preserve a fixed minimum spacing for larger scrollable families.",
    ],
  },
  {
    version: "continuous-user-adjustment-firth-v6.2",
    title: "User-selected clinical adjustment",
    date: "2026-07",
    items: [
      "Survival and Compare Analyses separate eligibility filters from one exact complete-case Cox adjustment specification.",
      "Users can select imported age, stage, grade, GDC gender and GDC race; age is modeled per 10 years and categorical fields use explicit treatment contrasts.",
      "The same specification is added to grouped, continuous and two-signature interaction model families.",
      "An unavailable requested model is marked not evaluable and is never replaced by an auxiliary stage/grade sensitivity.",
    ],
  },
  {
    version: "continuous-spline-firth-sensitivity-v6.1",
    title: "Sparse-event Cox diagnostics",
    date: "2026-07",
    items: [
      "Every grouped, continuous and two-signature interaction Cox model reports its fitted parameter count and observed events per parameter.",
      "Models below 10 events per parameter are marked as low-information; values below 5 receive a severe caution without suppressing the standard estimate.",
      "Low-information, unstable or extreme fits automatically add a Firth penalized partial-likelihood sensitivity with profile-likelihood confidence intervals and tests.",
      "The standard Efron-ties Cox estimate remains visible; the Firth sensitivity records its separate Breslow ties method, trigger and package version.",
    ],
  },
  {
    version: "continuous-spline-cutpoint-sensitivity-v6.0",
    title: "Continuous primary survival model",
    date: "2026-07",
    items: [
      "Single-gene and one-signature analyses now estimate the primary association per +1 within-analysis expression SD before assigning a cutpoint.",
      "A three-degree-of-freedom restricted cubic spline uses knots at the 5th, 35th, 65th and 95th percentiles and reports a likelihood-ratio test of nonlinearity.",
      "Spline estimation requires at least 30 events, equivalent to 10 events per spline parameter.",
      "The spline effect profile reports hazard ratios relative to median expression from the 5th through 95th percentile with 95% confidence intervals.",
      "Kaplan-Meier, grouped Cox and RMST outputs remain available as cutpoint sensitivity analyses.",
      "The audit bundle stores separate hashes and CSV files for the continuous expression-complete population and the cutpoint-specific grouped population.",
    ],
  },
  {
    version: "immune-pancancer-declared-primary-disease-ordinal-sensitivity-cox-audit-v2.2",
    title: "Immune atlas declared molecular populations",
    date: "2026-08",
    items: [
      "All 3,118 frozen ImmPort genes are recomputed across strict-OS TCGA cohorts with primary, ordinal-stage, ordinal-grade and stage+grade Cox families.",
      "Atlas-wide gene–cancer BH-FDR and gene-level random-effects meta-FDR are calculated independently inside every comparable model family.",
      "The availability-selected sensitivity hierarchy is stage+grade, then stage, then grade; mixed selected families support retained/attenuated summaries but are never meta-analyzed.",
      "Direction changes among all estimates remain available diagnostically, while headline flips are restricted to primary-FDR-supported associations to avoid magnifying null-effect noise.",
      "Every completed model carries cox.zph output, and the atlas audit pins ImmPort sources, patient records and expression matrices with SHA-256 hashes.",
      "Each TCGA cancer is restricted to its declared primary-disease molecular population before modeling; primary and metastatic melanoma are never pooled.",
    ],
  },
  {
    version: "decision-context-notices-ui-v1.0",
    title: "Decision-support interpretation layer",
    date: "2026-07",
    items: [
      "Cohort exclusions, censoring and one-sample-per-patient provenance are neutral information rather than statistical warnings.",
      "A missing clinical-adjusted model is labeled not evaluable; it is not treated as an execution failure.",
      "Only a diagnostic caution in the selected adjusted model changes the top-level status to amber; auxiliary-model cautions remain available without contaminating that status.",
      "Cutpoint comparisons show every result and keep BH, Cox, RMST, marker PH and global model PH as separate, descriptive outputs.",
      "The REST API and MCP preserve the legacy warnings array for compatibility and add structured notices plus a selected-model diagnostic summary.",
      "No p-value, effect estimate, patient grouping, endpoint rule or reproducibility hash definition changed in this interpretation-layer release.",
    ],
  },
  {
    version: "ordinal-clinical-adjusted-cox-audit-rmst-maxstat-v4.4",
    title: "Single-signature survival pipeline",
    date: "2026-07",
    items: [
      "Clinical adjustment now encodes major pathologic stage as 0/I/II/III/IV → 0/1/2/3/4 and histologic grade G1–G5 → 1–5.",
      "Stage substages collapse to their major stage; unrecognized Stage X/GX values remain missing and are reported in model provenance.",
      "The most complete evaluable adjustment uses both ordinal trends, with stage-only or grade-only models retained as explicit fallbacks.",
      "Each adjusted model records its encoding, mapped-patient count, observed scores and unmapped values.",
      "Diagnostic messages distinguish cohort-construction notes from model-specific convergence and proportional-hazards cautions.",
    ],
  },
  {
    version: "combined-signatures-ordinal-interaction-cox-audit-rmst-v2.4",
    title: "Two-signature combined groups",
    date: "2026-07",
    items: [
      "Continuous two-signature interaction models now use the same ordinal stage and grade encoding as single-signature analyses.",
      "Stage+grade, stage-only and grade-only interaction adjustments remain separately reported when evaluable.",
      "Score construction, crossed expression groups, audit hashes and plot exports are unchanged.",
    ],
  },
  {
    version: "clinical-adjusted-cox-audit-rmst-maxstat-v4.3",
    title: "Previous categorical clinical adjustment",
    date: "2026-07",
    items: [
      "TCGA-CDR endpoint selection with minimum patient and event QC.",
      "Kaplan-Meier, log-rank, univariable Cox and clinically adjusted Cox when covariates are evaluable.",
      "cox.zph proportional hazards diagnostics and RMST effect-size output for two-group comparisons.",
      "Maxstat cutpoints record the approximate maximally selected rank statistic p-value using maxstat::maxstat.test pmethod=Lau94.",
      "Reproducibility audit with payload hash, patient list, software versions and artifact checksums.",
    ],
  },
  {
    version: "combined-signatures-interaction-cox-audit-rmst-v2.3",
    title: "Previous categorical two-signature adjustment",
    date: "2026-07",
    items: [
      "Independent scoring for Signature A and Signature B using the documented direct, rank-based or numeric signature methods.",
      "Median x median or tertile x tertile grouping into crossed expression states.",
      "Interaction Cox model on continuous signature z-scores plus standard survival summaries for the combined groups.",
    ],
  },
  {
    version: "pancancer-primary-plus-ordinal-sensitivity-cox-audit-v2.1",
    title: "Pan-cancer primary + clinical sensitivity",
    date: "2026-07",
    items: [
      "The primary cross-cancer estimand remains one continuous Cox model per cancer with expression z-scored within cohort.",
      "Parallel sensitivity models add ordinal major stage, histologic grade or both when complete-case patient and event criteria remain satisfied.",
      "Sensitivity models are selected in this order: stage+grade, stage, then grade. Selection depends on model availability, not effect size or p-value.",
      "Each adjustment family has its own BH-FDR and random-effects meta-analysis. Mixed selected adjustment families are kept separate.",
      "Missing clinical adjustment is labeled not evaluable rather than failed or warned, while cox.zph findings remain model-level diagnostic cautions.",
      "Public-job reuse is keyed to both pipeline and data versions, so an older completed artifact cannot satisfy a request under a newer scientific context.",
      "Patient-level CSV, cohort CSV, parameter-specific methods, raw R output, audit report and a reproducibility bundle are exported for every scan.",
    ],
  },
  {
    version: "pancancer-cox-v1.0",
    title: "Pan-cancer continuous Cox",
    date: "2026-07",
    items: [
      "One Cox model per cancer using expression z-scored within each cohort.",
      "BH-FDR adjustment, direction concordance and random-effects meta-analysis.",
      "Endpoint-mode logic for strict, death-like, progression-like or best-available TCGA-CDR outcomes.",
    ],
  },
  {
    version: "cutpoint-evidence-profile-v1.1",
    title: "Cutpoint evidence profile",
    date: "2026-07",
    items: [
      "Batch comparison across maxstat, median, upper quartile, outer quartiles and selected percentile.",
      "BH, univariable Cox, adjusted Cox and fixed-horizon RMST remain separate descriptive summaries rather than independent votes.",
      "Marker-term and global cox.zph diagnostics are reported separately and modify interpretation without excluding an association.",
      "Maxstat grouped HR, confidence interval and RMST outputs are labelled post-selection.",
    ],
  },
  {
    version: "cutpoint-robustness-v1.0",
    title: "Previous dichotomization reporting panel",
    date: "2026-07",
    items: [
      "Introduced batch comparison across the five two-group cutpoint methods.",
      "Its composite downstream flag was retired in v1.1 because it combined correlated association summaries and treated PH as an exclusion rule.",
    ],
  },
  {
    version: "dataset-qc-v1.0",
    title: "Dataset inventory and biospecimen QC",
    date: "2026-07",
    items: [
      "One prioritized RNA sample per patient for patient-level survival modeling.",
      "Dataset summary page for endpoint coverage, sample types, event metadata and source dates.",
    ],
  },
];

function getCohortName(cohortId) {
  return COHORT_NAMES[cohortId] || cohortId || "Unknown cancer";
}

function repositoryCancerCodeForCohort(cohortId) {
  return REPOSITORY_CANCER_CODES[cohortId]
    || String(cohortId || "").replace(/^TCGA-/, "");
}

function getCohortLabel(cohortId) {
  return cohortId ? `${getCohortName(cohortId)} (${cohortId})` : "Select cancer";
}

function normalizeOptionalPlotLabel(value) {
  return String(value || "").trim() || null;
}

function buildPlotStylePayload(plotStyle, paletteOverride = null) {
  const style = { ...DEFAULT_PLOT_STYLE, ...(plotStyle || {}) };
  const continuous = {
    ...DEFAULT_PLOT_STYLE.continuous,
    ...(style.continuous || {}),
  };
  const coxForest = {
    ...DEFAULT_PLOT_STYLE.cox_forest,
    ...(style.cox_forest || {}),
  };
  const validatedNumbers = plotStyleInputState({
    ...style,
    continuous,
    cox_forest: coxForest,
  }).value;
  return {
    ...style,
    palette: paletteOverride || style.palette,
    plot_aspect: style.plot_aspect,
    base_font_size: validatedNumbers.base_font_size,
    axis_text_size: validatedNumbers.axis_text_size,
    axis_text_bold: Boolean(style.axis_text_bold),
    axis_text_italic: Boolean(style.axis_text_italic),
    axis_title_size: validatedNumbers.axis_title_size,
    axis_title_bold: Boolean(style.axis_title_bold),
    axis_title_italic: Boolean(style.axis_title_italic),
    plot_frame: ["axes", "box"].includes(style.plot_frame)
      ? style.plot_frame
      : "open",
    show_grid: Boolean(style.show_grid),
    show_title: Boolean(style.show_title),
    plot_title: style.show_title ? normalizeOptionalPlotLabel(style.plot_title) : null,
    continuous: {
      ...continuous,
      show_title: Boolean(continuous.show_title),
      plot_title: continuous.show_title
        ? normalizeOptionalPlotLabel(continuous.plot_title)
        : null,
      x_axis_title: normalizeOptionalPlotLabel(continuous.x_axis_title),
      y_axis_title: normalizeOptionalPlotLabel(continuous.y_axis_title),
    },
    cox_forest: {
      ...coxForest,
      model_layout: coxForest.model_layout === "separate" ? "separate" : "combined",
      multivariable_display:
        coxForest.multivariable_display === "selected" ? "selected" : "all",
      multivariable_model_ids: [
        ...new Set(
          Array.isArray(coxForest.multivariable_model_ids)
            ? coxForest.multivariable_model_ids
            : DEFAULT_PLOT_STYLE.cox_forest.multivariable_model_ids,
        ),
      ],
      show_title: Boolean(coxForest.show_title),
      plot_title: coxForest.show_title
        ? normalizeOptionalPlotLabel(coxForest.plot_title)
        : null,
      univariable_plot_title: coxForest.show_title
        ? normalizeOptionalPlotLabel(coxForest.univariable_plot_title)
        : null,
      multivariable_plot_title: coxForest.show_title
        ? normalizeOptionalPlotLabel(coxForest.multivariable_plot_title)
        : null,
      x_axis_title: normalizeOptionalPlotLabel(coxForest.x_axis_title),
    },
  };
}

function buildAnalysisPayload(form) {
  const signatureGenes = parseSignatureGenes(
    form.gene_symbol,
    form.signature_method,
  );
  const normalizedFilters = analysisFilterState(form.filters).value;
  return {
    ...form,
    gene_symbol: form.gene_symbol.trim().toUpperCase(),
    signature_genes: form.signature_method === "single" ? [] : signatureGenes,
    adjustment_covariates: [...new Set(form.adjustment_covariates || [])],
    external_covariates: form.external_covariates || null,
    external_adjustment_covariates: [
      ...new Set(form.external_adjustment_covariates || []),
    ],
    custom_percentile:
      percentileInputState(
        form.cutpoint_method === "percentile",
        form.custom_percentile,
      ).value,
    plot_style: buildPlotStylePayload(form.plot_style),
    filters: normalizedFilters,
  };
}

function buildCombinedAnalysisPayload(form, signatureAInput, signatureBInput) {
  const groupingMethod = form.combined_signature.grouping_method;
  const normalizedFilters = analysisFilterState(form.filters).value;
  return {
    cohort: form.cohort,
    dataset_id: form.dataset_id || null,
    dataset_release_id: form.dataset_release_id || null,
    expression_layer_id: form.expression_layer_id || null,
    signature_a: buildSignatureSpec(form.combined_signature.signature_a, signatureAInput, "Signature A"),
    signature_b: buildSignatureSpec(form.combined_signature.signature_b, signatureBInput, "Signature B"),
    endpoint: form.endpoint,
    expression_scale: form.expression_scale,
    combination_method: groupingMethod,
    time_unit: form.time_unit,
    show_confidence_interval: form.show_confidence_interval,
    show_risk_table: form.show_risk_table,
    adjustment_covariates: [...new Set(form.adjustment_covariates || [])],
    external_covariates: form.external_covariates || null,
    external_adjustment_covariates: [
      ...new Set(form.external_adjustment_covariates || []),
    ],
    plot_style: buildPlotStylePayload(
      form.plot_style,
      combinedPalette(form.plot_style.palette, groupingMethod),
    ),
    filters: normalizedFilters,
  };
}

function buildSurvivalRequests(form, geneInput, signatureAInput, signatureBInput, panelSignatures) {
  if (form.analysis_kind === "signature_panel") {
    return [buildSignaturePanelRequest({ form, signatures: panelSignatures, plotStyle: buildPlotStylePayload(form.plot_style) })];
  }
  if (form.analysis_kind === "combined_signatures") {
    return [buildCombinedAnalysisPayload(form, signatureAInput, signatureBInput)];
  }
  const inputs = form.signature_method === "single"
    ? uniqueGeneSymbols(geneInput)
    : [geneInputTokens(geneInput).join(", ")];
  return inputs.map((gene_symbol) => {
    const payload = buildAnalysisPayload({ ...form, gene_symbol });
    // These are editor state for other analysis modes, not this request.
    const { combined_signature, signature_panel, analysis_kind, ...request } = payload;
    return request;
  });
}

function buildSignatureSpec(signature, geneInput, fallbackName) {
  const normalizedInput = geneInputTokens(geneInput).join(", ");
  return {
    name: signature.name.trim() || fallbackName,
    gene_symbol: normalizedInput,
    signature_method: signature.signature_method,
    signature_genes: signature.signature_method === "single"
      ? []
      : parseSignatureGenes(normalizedInput, signature.signature_method),
  };
}

function combinedPalette(currentPalette, groupingMethod) {
  const required = groupingMethod === "tertiles" ? 9 : 4;
  const palette = Array.isArray(currentPalette) ? currentPalette.filter(Boolean) : [];
  if (palette.length >= required) {
    return palette.slice(0, required);
  }
  return DEFAULT_COMBINED_PALETTE.slice(0, required);
}

function parseSignatureGenes(text, method = null) {
  if (method) {
    const result = normalizeSignatureInput(text, method);
    if (!result.valid) throw new Error(result.errors[0]);
    return result.genes;
  }
  return parseSignatureGenesStrict(text).map(
    ({ has_explicit_weight: _ignored, ...gene }) => gene,
  );
}

function uniqueGeneSymbols(text) {
  const seen = new Set();
  return geneInputTokens(text)
    .map(geneSymbolFromToken)
    .filter((gene) => {
      if (!gene || seen.has(gene)) return false;
      seen.add(gene);
      return true;
    });
}

function currentGeneSearchTerm(text) {
  const token = text.split(/[,+;\n]/).pop()?.trim() || "";
  return token.split(":")[0]?.trim() || "";
}

function geneInputTokens(text) {
  const seen = new Set();
  return text
    .split(/[,+;\n]/)
    .map((item) => normalizeGeneToken(item))
    .filter(Boolean)
    .filter((token) => {
      const symbol = geneSymbolFromToken(token);
      if (seen.has(symbol)) return false;
      seen.add(symbol);
      return true;
    });
}

function normalizeGeneToken(item) {
  const parts = String(item || "").split(":");
  const symbol = String(parts[0] || "").trim().toUpperCase();
  if (!symbol) return "";
  if (parts.length === 1) return symbol;
  return `${symbol}:${parts.slice(1).map((part) => part.trim()).join(":")}`;
}

function geneSymbolFromToken(token) {
  return String(token || "").split(":")[0].trim().toUpperCase();
}

function addGeneToken(value, token) {
  const normalized = normalizeGeneToken(token);
  if (!normalized) return geneInputTokens(value).join(", ");
  const symbol = geneSymbolFromToken(normalized);
  const existing = geneInputTokens(value).filter((item) => geneSymbolFromToken(item) !== symbol);
  return [...existing, normalized].join(", ");
}

function removeGeneToken(value, symbol) {
  const normalizedSymbol = String(symbol || "").trim().toUpperCase();
  return geneInputTokens(value)
    .filter((item) => geneSymbolFromToken(item) !== normalizedSymbol)
    .join(", ");
}

function useGeneSuggestions(
  cohort,
  draft,
  datasetId = "",
  datasetReleaseId = "",
  expressionLayerId = "",
) {
  const searchTerm = currentGeneSearchTerm(draft);
  const [state, setState] = useState({
    genes: [],
    loading: false,
    error: "",
  });

  useEffect(() => {
    if (!cohort || searchTerm.length < 1) {
      setState({ genes: [], loading: false, error: "" });
      return undefined;
    }

    let cancelled = false;
    setState({ genes: [], loading: true, error: "" });
    const handle = window.setTimeout(() => {
      const lookup = datasetId
        ? searchRepositoryGenes(
            datasetId,
            searchTerm,
            datasetReleaseId,
            expressionLayerId,
          )
        : searchGenes(cohort, searchTerm);
      lookup
        .then((payload) => {
          if (!cancelled) {
            setState({ genes: payload.genes || [], loading: false, error: "" });
          }
        })
        .catch(() => {
          if (!cancelled) {
            setState({
              genes: [],
              loading: false,
              error: "Gene suggestions are temporarily unavailable.",
            });
          }
        });
    }, 220);

    return () => {
      cancelled = true;
      window.clearTimeout(handle);
    };
  }, [
    cohort,
    datasetId,
    datasetReleaseId,
    expressionLayerId,
    searchTerm,
  ]);

  return state;
}

function WorkspaceNavButton({ item, activePage, onNavigate }) {
  const selected = activePage === item.id;
  return (
    <button
      type="button"
      className={selected ? "selected" : ""}
      onClick={() => onNavigate(item.id)}
      onPointerEnter={() => preloadPageModule(item.id)}
      onFocus={() => preloadPageModule(item.id)}
      aria-current={selected ? "page" : undefined}
      aria-label={`${item.label}: ${item.kicker}`}
      title={`${item.label}: ${item.kicker}`}
    >
      <ModuleIcon role={item.iconRole} frame="navigation" />
      <span className="nav-copy">
        <strong>{item.label}</strong>
      </span>
    </button>
  );
}

function keepNavigationItemVisible(navigation, item) {
  if (!navigation || !item) return;
  const navigationBox = navigation.getBoundingClientRect();
  const itemBox = item.getBoundingClientRect();
  const edgeInset = 4;
  if (itemBox.left < navigationBox.left + edgeInset) {
    navigation.scrollLeft -= navigationBox.left + edgeInset - itemBox.left;
  } else if (itemBox.right > navigationBox.right - edgeInset) {
    navigation.scrollLeft += itemBox.right - navigationBox.right + edgeInset;
  }
}

function App() {
  const resultPanelRef = useRef(null);
  const analysisStepPanelRef = useRef(null);
  const tutorialTriggerRef = useRef(null);
  const workspaceNavRef = useRef(null);
  const hasNavigatedRef = useRef(false);
  const serviceLoadSequenceRef = useRef(0);
  const resourceLoadsRef = useRef(new Map());
  const repositoryDatasetsCompleteRef = useRef(false);
  const [health, setHealth] = useState(null);
  const [serviceState, setServiceState] = useState({
    status: "loading",
    failed: [],
  });
  const [pendingWorkspaceDraft, setPendingWorkspaceDraft] = useState(
    () => loadWorkspaceDraft(),
  );
  const [cohorts, setCohorts] = useState([]);
  const [repositoryCoverage, setRepositoryCoverage] = useState(null);
  const [repositoryDatasets, setRepositoryDatasets] = useState([]);
  const [repositoryCandidates, setRepositoryCandidates] = useState([]);
  const [repositoryCandidatesStatus, setRepositoryCandidatesStatus] = useState("idle");
  const [repositoryLayers, setRepositoryLayers] = useState([]);
  const [datasetSummary, setDatasetSummary] = useState(null);
  const [dataSources, setDataSources] = useState([]);
  const [endpointOptions, setEndpointOptions] = useState([]);
  const [expressionScales, setExpressionScales] = useState(EXPRESSION_SCALE_FALLBACK);
  const [filters, setFilters] = useState(null);
  const [analysisResults, storeAnalysisResults] = useState([]);
  const [analysisResultFingerprint, setAnalysisResultFingerprint] = useState(null);
  const analysisResultEpoch = useRef(0);
  function setAnalysisResults(results) {
    // Source changes, workspace restores and recovery invalidate pending writes.
    analysisResultEpoch.current += 1;
    setAnalysisResultFingerprint(null);
    storeAnalysisResults(results);
  }
  const [analysisMetadata, setAnalysisMetadata] = useState({ key: "", status: "idle", error: "" });
  const [metadataRetry, setMetadataRetry] = useState(0);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [geneQuery, setGeneQuery] = useState("");
  const [combinedGeneQueries, setCombinedGeneQueries] = useState({ a: "", b: "" });
  const [panelGeneQueries, setPanelGeneQueries] = useState(["", ""]);
  const [cohortQuery, setCohortQuery] = useState("");
  const [cohortPickerOpen, setCohortPickerOpen] = useState(false);
  const [dataSourceMode, setDataSourceMode] = useState("catalog");
  const [userDataset, setUserDataset] = useState(null);
  const [localProjects, setLocalProjects] = useState(loadLocalProjects);
  const [userDatasetUploadStep, setUserDatasetUploadStep] = useState(0);
  const [userDatasetUploadDirty, setUserDatasetUploadDirty] = useState(false);
  const [summaryCohort, setSummaryCohort] = useState("");
  const [activePage, setActivePage] = useState(() => (
    typeof window === "undefined"
      ? "home"
      : readTutorialUrlState(window.location).view
  ));
  const tutorialController = useTutorialController({
    onViewChange: setActivePage,
  });
  const t = useHelpText();
  const [analysisStep, setAnalysisStep] = useState(0);
  const [plotEditorTarget, setPlotEditorTarget] = useState("survival");
  const [survivalPlotEditorOpen, setSurvivalPlotEditorOpen] = useState(false);
  const [downloadNotices, setDownloadNotices] = useState([]);
  const [compare, setCompare] = useState({
    genes: "",
    methods: ["median", "upper_quartile"],
    running: false,
    results: [],
    result_context: null,
    grouped_family: null,
    active_run_id: null,
    error: "",
  });
  const [gsea, setGsea] = useState(() => createDefaultGseaState());
  useEffect(() => {
    // Acknowledge only results accepted by the run identity guard. Late
    // responses for a source that was left remain explicitly recoverable.
    if (compare.completed_event_id) clearActiveJob(compare.completed_event_id);
  }, [compare.completed_event_id]);
  const [expressionComparison, setExpressionComparison] = useState(
    () => createDefaultExpressionComparisonState(),
  );
  const [multiverse, setMultiverse] = useState({
    genes: "",
    endpoints: ["OS"],
    scoring_methods: ["single"],
    cutpoint_methods: [...DICHOTOMIZATION_METHODS],
    session_label: "",
    running: false,
    result: null,
    error: "",
  });
  const [sessionHistory, setSessionHistory] = useState(() => loadSessionHistory());
  const [sessionExport, setSessionExport] = useState({
    running: false,
    result: null,
    error: "",
  });
  const [panCancer, setPanCancer] = useState({
    analysis_mode: "tcga_reference",
    gene_symbol: "",
    signature_method: "single",
    geneQuery: "",
    geneSuggestions: [],
    index_cohort: "",
    endpoint: "OS",
    endpoint_mode: "same_endpoint",
    expression_scale: "log2_tpm",
    min_patients: 10,
    min_events: 5,
    fdr_threshold: 0.1,
    running: false,
    result: null,
    hierarchicalRequest: {
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
    },
    hierarchicalPreflight: null,
    hierarchicalPreflightStatus: "idle",
    hierarchicalPreflightError: "",
    hierarchicalResult: null,
    hierarchicalResultView: "all_studies",
    hierarchicalRunning: false,
    hierarchicalError: "",
    immuneScreen: null,
    immuneScreenLoading: false,
    immuneScreenError: "",
    error: "",
  });

  const [form, setForm] = useState({
    cohort: "",
    dataset_id: null,
    dataset_release_id: null,
    expression_layer_id: null,
    gene_symbol: "",
    analysis_kind: "single_signature",
    endpoint: "OS",
    signature_method: "single",
    signature_genes: [],
    combined_signature: {
      grouping_method: "median",
      signature_a: {
        name: "Signature A",
        gene_symbol: "",
        signature_method: "zscore",
      },
      signature_b: {
        name: "Signature B",
        gene_symbol: "",
        signature_method: "zscore",
      },
    },
    signature_panel: {
      name: "",
      signatures: [
        createPanelSignature(0),
        createPanelSignature(1),
      ],
    },
    expression_scale: "log2_tpm",
    cutpoint_method: "median",
    custom_percentile: 60,
    time_unit: "days",
    show_confidence_interval: true,
    show_risk_table: false,
    plot_style: DEFAULT_PLOT_STYLE,
    filters: EMPTY_FILTERS,
    adjustment_covariates: DEFAULT_ADJUSTMENT_COVARIATES,
    external_covariates: null,
    external_adjustment_covariates: [],
  });

  const geneSuggestionCohort = form.cohort || cohorts[0]?.id || "";
  const geneSuggestionState = useGeneSuggestions(
    geneSuggestionCohort,
    geneQuery,
    form.dataset_id,
    form.dataset_release_id,
    form.expression_layer_id,
  );
  const combinedSuggestionA = useGeneSuggestions(
    geneSuggestionCohort,
    combinedGeneQueries.a,
    form.dataset_id,
    form.dataset_release_id,
    form.expression_layer_id,
  );
  const combinedSuggestionB = useGeneSuggestions(
    geneSuggestionCohort,
    combinedGeneQueries.b,
    form.dataset_id,
    form.dataset_release_id,
    form.expression_layer_id,
  );
  const panelSuggestion0 = useGeneSuggestions(
    geneSuggestionCohort,
    panelGeneQueries[0] || "",
    form.dataset_id,
    form.dataset_release_id,
    form.expression_layer_id,
  );
  const panelSuggestion1 = useGeneSuggestions(
    geneSuggestionCohort,
    panelGeneQueries[1] || "",
    form.dataset_id,
    form.dataset_release_id,
    form.expression_layer_id,
  );
  const panelSuggestion2 = useGeneSuggestions(
    geneSuggestionCohort,
    panelGeneQueries[2] || "",
    form.dataset_id,
    form.dataset_release_id,
    form.expression_layer_id,
  );
  const panelSuggestion3 = useGeneSuggestions(
    geneSuggestionCohort,
    panelGeneQueries[3] || "",
    form.dataset_id,
    form.dataset_release_id,
    form.expression_layer_id,
  );
  const panelSuggestion4 = useGeneSuggestions(
    geneSuggestionCohort,
    panelGeneQueries[4] || "",
    form.dataset_id,
    form.dataset_release_id,
    form.expression_layer_id,
  );
  const panelSuggestion5 = useGeneSuggestions(
    geneSuggestionCohort,
    panelGeneQueries[5] || "",
    form.dataset_id,
    form.dataset_release_id,
    form.expression_layer_id,
  );
  const genes = geneSuggestionState.genes;
  const combinedGeneSuggestions = {
    a: combinedSuggestionA.genes,
    b: combinedSuggestionB.genes,
  };
  const combinedGeneSuggestionStates = {
    a: combinedSuggestionA,
    b: combinedSuggestionB,
  };
  const panelGeneSuggestionStates = [
    panelSuggestion0,
    panelSuggestion1,
    panelSuggestion2,
    panelSuggestion3,
    panelSuggestion4,
    panelSuggestion5,
  ];

  async function reloadApplicationData() {
    const sequence = serviceLoadSequenceRef.current + 1;
    serviceLoadSequenceRef.current = sequence;
    setServiceState((current) => ({ ...current, status: "loading" }));
    const resources = [
      {
        label: "Service status",
        request: getHealth(),
        apply: setHealth,
      },
      {
        label: "Cohort catalog",
        request: getCohorts(),
        apply: (payload) => {
          setCohorts(payload);
          if (
            form.cohort
            && !payload.find((item) => item.id === form.cohort)
          ) {
            setForm((current) => ({ ...current, cohort: "" }));
          }
        },
      },
      {
        label: "Expression scales",
        request: getExpressionScales(),
        apply: (payload) => {
          if (payload?.length) setExpressionScales(payload);
        },
      },
    ];
    const settled = await Promise.all(resources.map(async (resource) => {
      try {
        const payload = await resource.request;
        if (serviceLoadSequenceRef.current === sequence) resource.apply(payload);
        return { status: "fulfilled" };
      } catch (resourceError) {
        return { status: "rejected", reason: resourceError };
      }
    }));
    if (serviceLoadSequenceRef.current !== sequence) return;

    const failed = settled
      .map((result, index) => result.status === "rejected" ? resources[index].label : null)
      .filter(Boolean);
    setServiceState({
      status: failed.length
        ? (settled[0].status === "rejected" && settled[1].status === "rejected"
            ? "unavailable"
            : "degraded")
        : "ready",
      failed,
    });
  }

  useEffect(() => {
    reloadApplicationData();
  }, []);

  function loadResourceOnce(key, requestFactory, apply) {
    const existing = resourceLoadsRef.current.get(key);
    if (existing) return existing;
    const pending = requestFactory()
      .then((payload) => {
        apply(payload);
        return payload;
      })
      .catch((resourceError) => {
        resourceLoadsRef.current.delete(key);
        throw resourceError;
      });
    resourceLoadsRef.current.set(key, pending);
    return pending;
  }

  function ensureRepositoryCoverage() {
    return loadResourceOnce(
      "repository-coverage",
      () => getCancerRepositoryCoverage(),
      setRepositoryCoverage,
    );
  }

  function ensureRepositoryDatasets(cancerCode = "") {
    if (repositoryDatasetsCompleteRef.current && cancerCode) {
      return Promise.resolve({ datasets: repositoryDatasets });
    }
    const scope = cancerCode ? cancerCode.toUpperCase() : "all";
    return loadResourceOnce(
      `repository-datasets:${scope}`,
      () => getRepositoryDatasets(cancerCode, { includeMetadata: false }),
      (payload) => {
        const incoming = payload?.datasets || [];
        if (!cancerCode) {
          repositoryDatasetsCompleteRef.current = true;
          setRepositoryDatasets(incoming);
          return;
        }
        setRepositoryDatasets((current) => {
          const merged = new Map(current.map((dataset) => [dataset.id, dataset]));
          incoming.forEach((dataset) => merged.set(dataset.id, dataset));
          return [...merged.values()];
        });
      },
    );
  }

  function ensureRepositoryCandidates() {
    if (repositoryCandidatesStatus === "ready") {
      return Promise.resolve({ candidates: repositoryCandidates });
    }
    setRepositoryCandidatesStatus("loading");
    return loadResourceOnce(
      "repository-candidates:reviewable",
      () => getRepositoryDatasetCandidates(),
      (payload) => {
        setRepositoryCandidates((payload?.candidates || []).filter(
          (candidate) => candidate.status !== "promoted",
        ));
        setRepositoryCandidatesStatus("ready");
      },
    ).catch((candidateError) => {
      setRepositoryCandidatesStatus("unavailable");
      return { candidates: [], error: candidateError };
    });
  }

  useEffect(() => {
    if (activePage === "repository") {
      Promise.all([
        ensureRepositoryCoverage(),
        ensureRepositoryDatasets(),
        ensureRepositoryCandidates(),
      ])
        .catch((err) => setError(err.message));
    } else if (activePage === "pancancer" || normalizeAnalysisModule(activePage)) {
      // External-only cancers need their capabilities before the first cohort
      // choice. Loading only the selected cancer makes them undiscoverable.
      ensureRepositoryDatasets().catch((err) => setError(err.message));
      if (dataSourceMode === "upload") {
        ensureRepositoryCoverage().catch((err) => setError(err.message));
      }
    }
  }, [activePage, dataSourceMode]);

  useEffect(() => {
    if (
      !form.cohort
      || !["analysis", "compare", "expression", "gsea", "multiverse"].includes(activePage)
    ) return;
    const cancerCode = repositoryCancerCodeForCohort(form.cohort);
    ensureRepositoryDatasets(cancerCode).catch((err) => setError(err.message));
  }, [activePage, form.cohort, form.dataset_id]);

  useEffect(() => {
    const reference = loadUserDatasetReference();
    if (!reference?.id) return;
    let cancelled = false;
    getUserDataset(reference.id)
      .then((dataset) => {
        if (cancelled) return;
        setUserDataset({...dataset, access_token: reference.access_token});
        setDataSourceMode("upload");
        setForm((current) => ({
          ...current,
          cohort: dataset.tcga_cohort,
          dataset_id: dataset.id,
          dataset_release_id: dataset.active_release_id,
          expression_layer_id: dataset.expression_layer?.value || null,
          endpoint: dataset.endpoint?.value || "",
          filters: { ...EMPTY_FILTERS },
          external_covariates: null,
          external_adjustment_covariates: [],
        }));
      })
      .catch(() => persistUserDatasetReference(null));
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const navigation = workspaceNavRef.current;
    const activeItem = navigation?.querySelector('[aria-current="page"]');
    if (!navigation || !activeItem) return undefined;
    const alignActiveItem = () => keepNavigationItemVisible(navigation, activeItem);
    const frame = window.requestAnimationFrame(alignActiveItem);
    let cancelled = false;
    const resizeObserver = typeof ResizeObserver === "undefined"
      ? null
      : new ResizeObserver(alignActiveItem);
    resizeObserver?.observe(navigation);
    resizeObserver?.observe(activeItem);
    document.fonts?.ready?.then(() => {
      if (!cancelled) alignActiveItem();
    }).catch(() => {});
    return () => {
      cancelled = true;
      window.cancelAnimationFrame(frame);
      resizeObserver?.disconnect();
    };
  }, [activePage]);

  useEffect(() => {
    persistSessionHistory(sessionHistory);
  }, [sessionHistory]);

  useEffect(() => {
    if (pendingWorkspaceDraft) return undefined;
    const timer = window.setTimeout(() => {
      persistWorkspaceDraft(createWorkspaceDraft({
        activePage,
        form,
        compare,
        expressionComparison,
        gsea,
        multiverse,
        panCancer,
      }));
    }, 800);
    return () => window.clearTimeout(timer);
  }, [
    activePage,
    compare,
    expressionComparison,
    form,
    gsea,
    multiverse,
    panCancer,
    pendingWorkspaceDraft,
  ]);

  useEffect(() => {
    function captureJobUpdate(event) {
      setSessionHistory((current) =>
        reduceSessionJobUpdate(current, event.detail),
      );
    }
    window.addEventListener(SESSION_JOB_EVENT, captureJobUpdate);
    return () => window.removeEventListener(SESSION_JOB_EVENT, captureJobUpdate);
  }, []);

  const requiresDatasetSelection = !form.dataset_id && cohorts.some(
    (cohort) => cohort.id === form.cohort && cohort.status === "external_only",
  );
  const analysisMetadataKey = metadataContextKey(form);
  const analysisMetadataReady = metadataReady(analysisMetadata, analysisMetadataKey);
  useEffect(() => {
    if (!form.cohort || requiresDatasetSelection) {
      setFilters(null);
      setEndpointOptions([]);
      setRepositoryLayers([]);
      setAnalysisMetadata({ key: analysisMetadataKey, status: "idle", error: "" });
      return undefined;
    }
    let cancelled = false;
    setFilters(null);
    setEndpointOptions([]);
    setRepositoryLayers([]);
    setAnalysisMetadata({ key: analysisMetadataKey, status: "loading", error: "" });
    const inputPromise = form.dataset_id
      ? Promise.all([
          getRepositoryFilterOptions(
            form.dataset_id,
            form.dataset_release_id,
          ),
          getRepositoryDatasetEndpoints(
            form.dataset_id,
            form.dataset_release_id,
          ),
          getRepositoryExpressionLayers(
            form.dataset_id,
            form.dataset_release_id,
          ),
        ])
      : Promise.all([
          getFilterOptions(
            form.cohort,
            form.filters.sample_population || "",
          ),
          getCohortEndpoints(form.cohort),
          Promise.resolve({ expression_layers: [] }),
        ]);
    inputPromise
      .then(([payload, endpointPayload, layerPayload]) => {
        if (cancelled) return;
        setFilters(payload);
        const options = endpointPayload?.endpoints?.length
          ? endpointPayload.endpoints.map((item) => ({
              ...item,
              patients: item.patients ?? item.patient_count,
              events: item.events ?? item.event_count,
            }))
          : [NO_SURVIVAL_ENDPOINT];
        const layers = layerPayload?.expression_layers || [];
        const availableAdjustmentCovariates = new Set([
          ...(payload?.age_min != null || payload?.age_max != null
            ? ["age_at_index"]
            : []),
          ...(payload?.stages?.length ? ["stage"] : []),
          ...(payload?.grades?.length ? ["grade"] : []),
          ...(payload?.genders?.length ? ["gender"] : []),
          ...(payload?.races?.length ? ["race"] : []),
        ]);
        setRepositoryLayers(layers);
        setEndpointOptions(options);
        const fallbackEndpoint = options.find((item) => item.available) || options[0] || NO_SURVIVAL_ENDPOINT;
        const availableEndpoints = options
          .filter((item) => item.available)
          .map((item) => item.value);
        setMultiverse((current) => ({
          ...current,
          endpoints: availableEndpoints.length
            ? availableEndpoints
            : [],
          result: null,
          error: "",
        }));
        setForm((current) => ({
          ...current,
          endpoint: options.find((item) => item.value === current.endpoint && item.available)
            ? current.endpoint
            : fallbackEndpoint.value,
          expression_layer_id: form.dataset_id
            ? (
                layers.find((item) => item.value === current.expression_layer_id)
                  ?.value
                || layers.find((item) => item.is_default)?.value
                || layers[0]?.value
                || null
              )
            : null,
          adjustment_covariates: (
            current.adjustment_covariates || []
          ).filter((value) => availableAdjustmentCovariates.has(value)),
          // Selection handlers reset filters. A retry must retain the user's
          // restrictions instead of silently widening the population.
          filters: current.filters,
        }));
        setAnalysisMetadata({ key: analysisMetadataKey, status: "ready", error: "" });
      })
      .catch((err) => {
        if (!cancelled) setAnalysisMetadata({ key: analysisMetadataKey, status: "error", error: formatError(err) });
      });
    return () => {
      cancelled = true;
    };
  }, [
    form.cohort,
    form.dataset_id,
    form.dataset_release_id,
    form.filters.sample_population,
    requiresDatasetSelection,
    metadataRetry,
    analysisMetadataKey,
  ]);

  useEffect(() => {
    if (activePage !== "summary") return undefined;
    let cancelled = false;
    Promise.all([
      getDatasetSummary(summaryCohort, {
        includeDataSources: false,
        includeDataSync: false,
      }),
      loadResourceOnce(
        "data-sources",
        getDataSources,
        (payload) => setDataSources(payload?.sources || []),
      ),
    ])
      .then(([payload]) => {
        if (!cancelled) setDatasetSummary(payload);
      })
      .catch((err) => {
        if (!cancelled) setError(err.message);
      });
    return () => {
      cancelled = true;
    };
  }, [activePage, summaryCohort]);

  useEffect(() => {
    const searchTerm = currentGeneSearchTerm(panCancer.geneQuery);
    const cohort = referenceCohortId(cohorts, panCancer.index_cohort, form.cohort);
    if (!cohort || searchTerm.length < 1) {
      setPanCancer((current) => ({ ...current, geneSuggestions: [] }));
      return;
    }
    const handle = setTimeout(() => {
      searchGenes(cohort, searchTerm)
        .then((payload) => setPanCancer((current) => ({ ...current, geneSuggestions: payload.genes })))
        .catch(() => setPanCancer((current) => ({ ...current, geneSuggestions: [] })));
    }, 220);
    return () => clearTimeout(handle);
  }, [cohorts, form.cohort, panCancer.index_cohort, panCancer.geneQuery]);

  const selectedCohort = useMemo(
    () => cohorts.find((cohort) => cohort.id === form.cohort),
    [cohorts, form.cohort],
  );
  const selectedRepositoryDataset = useMemo(
    () => (
      userDataset?.id === form.dataset_id
        ? userDataset
        : repositoryDatasets.find((dataset) => dataset.id === form.dataset_id)
    ),
    [form.dataset_id, repositoryDatasets, userDataset],
  );
  const cohortRepositoryDatasets = useMemo(
    () => repositoryDatasets.filter(
      (dataset) => dataset.tcga_cohort === form.cohort,
    ),
    [form.cohort, repositoryDatasets],
  );
  const selectableCohortDatasets = useMemo(
    () => userDataset?.tcga_cohort === form.cohort
      ? [...cohortRepositoryDatasets, userDataset]
      : cohortRepositoryDatasets,
    [cohortRepositoryDatasets, form.cohort, userDataset],
  );
  const activeDatasetModule = normalizeAnalysisModule(activePage);
  const compatibleCohortRepositoryDatasets = useMemo(
    () => filterDatasetsForModule(
      cohortRepositoryDatasets,
      activeDatasetModule,
    ),
    [activeDatasetModule, cohortRepositoryDatasets],
  );
  useEffect(() => {
    if (
      selectedCohort?.status !== "external_only"
      || form.dataset_id
      || compatibleCohortRepositoryDatasets.length !== 1
    ) return;
    selectRepositoryDataset(compatibleCohortRepositoryDatasets[0].id);
  }, [
    activeDatasetModule,
    compatibleCohortRepositoryDatasets,
    form.dataset_id,
    selectedCohort?.status,
  ]);
  const uploadCancerTypes = useMemo(
    () => repositoryCoverage?.cancers?.length
      ? repositoryCoverage.cancers
      : cohorts.map((cohort) => ({
          code: cohort.id.replace(/^TCGA-/, ""),
          tcga_cohort: cohort.id,
          name: getCohortName(cohort.id),
          primary_site: cohort.primary_site,
        })),
    [cohorts, repositoryCoverage],
  );

  const visibleCohorts = useMemo(() => {
    return cohorts.filter((cohort) =>
      cohortMatchesQuery(cohort, cohortQuery, getCohortName(cohort.id)),
    );
  }, [cohorts, cohortQuery]);
  const moduleVisibleCohorts = useMemo(
    () => !activeDatasetModule
      ? visibleCohorts
      : visibleCohorts.filter((cohort) =>
        cohortSupportsModule(cohort, repositoryDatasets, activeDatasetModule)
        || cohort.id === form.cohort,
      ),
    [
      activeDatasetModule,
      form.cohort,
      repositoryDatasets,
      visibleCohorts,
    ],
  );

  const activeFilterCount = useMemo(() => {
    const listCount =
      form.filters.sample_types.length +
      form.filters.stages.length +
      form.filters.grades.length +
      form.filters.genders.length +
      form.filters.races.length;
    const rangeCount = ["age_min", "age_max", "max_time_days"].filter(
      (key) => form.filters[key] !== "",
    ).length;
    return listCount + rangeCount + (form.filters.custom_filters || []).length;
  }, [form.filters]);
  const selectedAdjustmentCovariates = form.adjustment_covariates || [];
  const selectedExternalAdjustmentCovariates =
    form.external_adjustment_covariates || [];

  const selectedCutpoint = CUTPOINTS.find((item) => item.value === form.cutpoint_method);
  const analysisExpressionScales = form.dataset_id
    ? repositoryLayers.map((layer) => ({
        ...layer,
        note: layer.scale_note
          || `${layer.source_unit} source values; ${layer.transform} transformation recorded in the release manifest.`,
      }))
    : expressionScales;
  const selectedExpressionScale =
    (
      form.dataset_id
        ? analysisExpressionScales.find(
            (item) => item.value === form.expression_layer_id,
          )
        : analysisExpressionScales.find(
            (item) => item.value === form.expression_scale,
          )
    )
    || analysisExpressionScales[0]
    || EXPRESSION_SCALE_FALLBACK[0];
  const analysisEndpointOptions = endpointsForExpressionLayer(endpointOptions, form.dataset_id ? selectedExpressionScale : null);
  const selectedEndpoint =
    (analysisMetadataReady && analysisEndpointOptions.find((item) => item.value === form.endpoint))
    || (analysisMetadataReady ? NO_SURVIVAL_ENDPOINT : {
      value: "", label: "Endpoint pending", available: false,
      reason: t.entry("survivalMetadata").does,
    });
  const effectiveGeneInput = geneQuery.trim() ? addGeneToken(form.gene_symbol, geneQuery) : form.gene_symbol;
  const selectedGenes = uniqueGeneSymbols(effectiveGeneInput);
  const effectiveSignatureAInput = combinedGeneQueries.a.trim()
    ? addGeneToken(form.combined_signature.signature_a.gene_symbol, combinedGeneQueries.a)
    : form.combined_signature.signature_a.gene_symbol;
  const effectiveSignatureBInput = combinedGeneQueries.b.trim()
    ? addGeneToken(form.combined_signature.signature_b.gene_symbol, combinedGeneQueries.b)
    : form.combined_signature.signature_b.gene_symbol;
  const selectedSignatureAGenes = uniqueGeneSymbols(effectiveSignatureAInput);
  const selectedSignatureBGenes = uniqueGeneSymbols(effectiveSignatureBInput);
  const isCombinedMode = form.analysis_kind === "combined_signatures";
  const isPanelMode = form.analysis_kind === "signature_panel";
  const effectivePanelSignatures = form.signature_panel.signatures.map(
    (signature, index) => ({
      ...signature,
      gene_symbol: panelGeneQueries[index]?.trim()
        ? addGeneToken(signature.gene_symbol, panelGeneQueries[index])
        : signature.gene_symbol,
    }),
  );
  const panelValidation = validateSignaturePanel(effectivePanelSignatures);
  const analysisFiltersValidation = analysisFilterState(form.filters);
  const plotStyleValidation = plotStyleInputState(form.plot_style);
  const percentileValidation = percentileInputState(
    !isCombinedMode && !isPanelMode && form.cutpoint_method === "percentile",
    form.custom_percentile,
  );
  const markerValidation = signatureInputState(effectiveGeneInput, {
    method: form.signature_method === "single" ? null : form.signature_method,
    allowWeights: form.signature_method !== "single",
    maximumGenes:
      form.signature_method === "single" ? PUBLIC_ANALYSIS_BATCH_MAX : null,
  });
  const signatureAValidation = signatureInputState(effectiveSignatureAInput, {
    method: form.combined_signature.signature_a.signature_method,
    label: "Signature A",
  });
  const signatureBValidation = signatureInputState(effectiveSignatureBInput, {
    method: form.combined_signature.signature_b.signature_method,
    label: "Signature B",
  });
  const rankScoring = rankScoringAvailability(
    selectedRepositoryDataset,
    selectedCohort,
    form.dataset_id ? selectedExpressionScale : null,
  );
  const activeSignatureMethods = isPanelMode
    ? effectivePanelSignatures.map((signature) => signature.signature_method)
    : isCombinedMode
      ? [
          form.combined_signature.signature_a.signature_method,
          form.combined_signature.signature_b.signature_method,
        ]
      : [form.signature_method];
  const rankMethodUnavailable = Boolean(
    !rankScoring.available
    && activeSignatureMethods.some(signatureMethodUsesDirection),
  );
  const singleAnalysisCapacity = batchCapacityState(selectedGenes.length, 1);
  const activeMarkerContractValid = isPanelMode
    ? panelValidation.valid && !rankMethodUnavailable
    : isCombinedMode
      ? signatureAValidation.valid && signatureBValidation.valid && !rankMethodUnavailable
      : markerValidation.valid && singleAnalysisCapacity.valid && !rankMethodUnavailable;
  const activeMarkerContractError = rankMethodUnavailable
    ? rankScoring.reason
    : isPanelMode
      ? panelValidation.errors[0]
      : isCombinedMode
        ? signatureAValidation.errors[0] || signatureBValidation.errors[0]
        : markerValidation.errors[0] || singleAnalysisCapacity.error;
  const requestContractValid = Boolean(
    analysisFiltersValidation.valid
    && plotStyleValidation.valid
    && percentileValidation.valid
    && activeMarkerContractValid,
  );
  let survivalRequests = [];
  if (requestContractValid) {
    survivalRequests = buildSurvivalRequests(form, effectiveGeneInput, effectiveSignatureAInput, effectiveSignatureBInput, effectivePanelSignatures);
  }
  const currentSurvivalFingerprint = survivalRequestFingerprint(survivalRequests);
  const survivalResultsStale = analysisResults.length > 0
    && survivalResultsAreStale(analysisResultFingerprint, currentSurvivalFingerprint);
  const runCount = isPanelMode
    ? panelValidation.valid ? effectivePanelSignatures.length : 0
    : isCombinedMode
      ? selectedSignatureAGenes.length && selectedSignatureBGenes.length ? 2 : 0
      : form.signature_method === "single"
        ? selectedGenes.length
        : Math.min(selectedGenes.length, 1);
  const molecularPopulationReady = Boolean(
    form.dataset_id || (form.filters.sample_population && (
      !filters?.sample_populations || filters.sample_populations.some((item) => item.available && item.id === form.filters.sample_population)
    )),
  );
  const expressionLayerReady = !form.dataset_id || repositoryLayers.some((item) => item.value === form.expression_layer_id);
  const survivalDatasetReady = !selectedRepositoryDataset
    || datasetSupportsModule(selectedRepositoryDataset, "analysis");
  const canRun = isPanelMode
    ? Boolean(form.cohort && molecularPopulationReady && expressionLayerReady && survivalDatasetReady && selectedEndpoint.available && panelValidation.valid && requestContractValid) && !loading
    : isCombinedMode
      ? Boolean(form.cohort && molecularPopulationReady && expressionLayerReady && survivalDatasetReady && selectedSignatureAGenes.length && selectedSignatureBGenes.length && selectedEndpoint.available && requestContractValid) && !loading
      : Boolean(form.cohort && molecularPopulationReady && expressionLayerReady && survivalDatasetReady && selectedGenes.length && selectedEndpoint.available && requestContractValid) && !loading;
  const previewCutpoint = isPanelMode
    ? { label: "Continuous main effects" }
    : isCombinedMode
    ? {
        label: form.combined_signature.grouping_method === "tertiles"
          ? "Tertiles x tertiles"
          : "Median x median",
      }
    : selectedCutpoint;
  const selectedCancerName = form.cohort ? getCohortName(form.cohort) : "Select cancer";
  const plotCancerName = form.cohort ? getCohortName(form.cohort) : "Cancer";
  const pageMeta = PAGE_META[activePage] || PAGE_META.analysis;
  const activeModule = getAppModule(activePage);
  const quickGuideId = `quick-${activePage}`;
  const quickGuide = tutorialController.curriculum.byId[quickGuideId] || null;
  const quickGuideProgress = tutorialController.getGuideProgress(quickGuideId);
  const quickGuideStepIndex = quickGuide
    ? Math.max(
      0,
      quickGuide.steps.findIndex((item) => item.id === quickGuideProgress?.lastStepId),
    )
    : 0;
  const quickGuideIsOpen = tutorialController.tutorial?.id === quickGuideId;
  const quickGuideActionLabel = quickGuideIsOpen
    ? "Close guide"
    : quickGuideProgress?.status === "completed"
      ? `Review guide · ${quickGuide?.steps.length || 0} steps`
      : quickGuideProgress
        ? `Resume guide · ${quickGuideStepIndex + 1}/${quickGuide?.steps.length || 0}`
        : `Learn this module · ${quickGuide?.steps.length || 0} steps${quickGuide?.estimatedMinutes ? ` · ${quickGuide.estimatedMinutes} min` : ""}`;
  const expressionClinicalDefinition = clinicalVariableDefinition(
    filters || {},
    expressionComparison.clinical_variable,
  );
  const expressionClinicalIsNumeric = expressionClinicalDefinition?.value_type === "numeric"
    || (!expressionClinicalDefinition && expressionComparison.clinical_variable === "age_at_index");
  const expressionGroupsAvailable = Boolean(
    expressionComparison.result
    || (
      expressionComparison.grouping_source === "clinical"
      && expressionComparison.clinical_variable
      && (
        (expressionClinicalIsNumeric && (
          expressionComparison.clinical_cutpoint_method === "median"
          || String(expressionComparison.clinical_cutpoint ?? "").trim()
        ))
        || (
          expressionComparison.group_a_values?.length
          && expressionComparison.group_b_values?.length
        )
      )
    )
    || (
      expressionComparison.grouping_source === "survival"
      && String(expressionComparison.survival_analysis_id || "").trim()
    )
    || (
      expressionComparison.grouping_source === "expression"
      && String(expressionComparison.signature_genes || "").trim()
    ),
  );
  const hasGeneSelection = isPanelMode
    ? panelValidation.valid
    : isCombinedMode
      ? Boolean(selectedSignatureAGenes.length && selectedSignatureBGenes.length)
      : Boolean(selectedGenes.length);
  const coreAnalysisReady = Boolean(form.cohort && hasGeneSelection && selectedEndpoint.available);
  const tutorialCapabilities = {
    "dataset.catalogAvailable": Boolean(cohorts.length || dataSources.length || userDataset),
    "survival.dataConfigured": Boolean(form.cohort),
    "survival.markerConfigured": Boolean(form.cohort && hasGeneSelection),
    "survival.outcomeConfigured": coreAnalysisReady,
    "survival.designReady": coreAnalysisReady,
    "survival.resultAvailable": analysisResults.some(
      (item) => item?.status === "completed" || item?.result,
    ),
    "compare.resultAvailable": compare.results.some((item) => Boolean(item?.result)),
    "expression.groupsAvailable": expressionGroupsAvailable,
    "expression.resultAvailable": Boolean(expressionComparison.result),
    "gsea.resultAvailable": Boolean(gsea.result),
    "multiverse.resultAvailable": Boolean(multiverse.result),
    "session.runsAvailable": Boolean(sessionHistory.entries?.length),
    "repository.catalogAvailable": Boolean(repositoryDatasets.length),
    "pancancer.tcgaResultAvailable": Boolean(
      panCancer.analysis_mode === "tcga_reference" && panCancer.result,
    ),
    "pancancer.resultAvailable": Boolean(
      panCancer.analysis_mode === "tcga_reference"
        ? panCancer.result
        : panCancer.hierarchicalResult,
    ),
    "pancancer.hierarchicalUniverseAvailable": Boolean(
      panCancer.analysis_mode === "hierarchical"
      && panCancer.hierarchicalPreflightStatus === "ready"
      && panCancer.hierarchicalPreflight,
    ),
    "pancancer.hierarchicalResultAvailable": Boolean(
      panCancer.analysis_mode === "hierarchical" && panCancer.hierarchicalResult,
    ),
    "api.publicAvailable": Boolean(health),
  };
  const analysisStepCompletion = [
    Boolean(form.cohort && molecularPopulationReady && expressionLayerReady && analysisMetadataReady && survivalDatasetReady),
    hasGeneSelection && activeMarkerContractValid,
    Boolean(form.cohort && selectedEndpoint.available),
    coreAnalysisReady && analysisFiltersValidation.valid,
    canRun,
  ];
  const analysisStepRequirements = [
    form.cohort && molecularPopulationReady && expressionLayerReady && analysisMetadataReady && survivalDatasetReady
      ? ""
      : requiresDatasetSelection
        ? "Choose an analysis source."
      : !survivalDatasetReady
        ? "This source does not support Survival. Choose another analysis source."
      : analysisMetadataReady && !expressionLayerReady
        ? "Choose an available expression layer, or another source if none is listed."
      : form.cohort && molecularPopulationReady
        ? analysisMetadata.status === "error" && analysisMetadata.key === analysisMetadataKey
          ? "Retry loading the cohort details before running."
          : "Wait for the cohort details to load."
      : form.cohort
        ? "Choose the molecular population that should represent each patient."
      : dataSourceMode === "upload"
        ? "Complete the private dataset upload to continue."
        : "Select a cancer cohort to continue.",
    !activeMarkerContractValid
      ? activeMarkerContractError
      : hasGeneSelection
        ? ""
      : isPanelMode
        ? panelValidation.errors[0] || "Define between 2 and 6 signatures."
        : isCombinedMode
          ? "Add at least one gene to both signatures."
          : "Add at least one gene or signature.",
    form.cohort && analysisMetadataReady
      ? selectedEndpoint.available ? "" : "Choose an endpoint that passes cohort QC."
      : "",
    !analysisFiltersValidation.valid
      ? analysisFiltersValidation.errors[0]
      : "",
    canRun
      ? ""
      : percentileValidation.error
        || plotStyleValidation.errors[0]
        || analysisFiltersValidation.errors[0]
        || singleAnalysisCapacity.error
        || "",
  ];
  const activeAnalysisStep = ANALYSIS_WORKFLOW_STEPS[analysisStep] || ANALYSIS_WORKFLOW_STEPS[0];
  const analysisGeneSummary = isPanelMode
    ? `${effectivePanelSignatures.length} signatures`
    : isCombinedMode
      ? `A ${selectedSignatureAGenes.length || 0} / B ${selectedSignatureBGenes.length || 0}`
      : selectedGenes.length
        ? `${selectedGenes.slice(0, 3).join(", ")}${selectedGenes.length > 3 ? ` +${selectedGenes.length - 3}` : ""}`
        : "Gene pending";
  const survivalLedger = survivalDesignLedger({
    datasetLabel: selectedRepositoryDataset?.name
      || (form.cohort ? selectedCancerName : ""),
    markerKind: form.analysis_kind,
    markerSummary: hasGeneSelection ? analysisGeneSummary : "",
    markerCount: runCount,
    endpointLabel: selectedEndpoint.available ? selectedEndpoint.label : "",
    patients: selectedEndpoint.available ? selectedEndpoint.patients : undefined,
    events: selectedEndpoint.available ? selectedEndpoint.events : undefined,
    expressionScaleLabel: selectedExpressionScale?.label,
    groupingLabel: previewCutpoint?.label,
    filterCount: activeFilterCount,
    populationLabel: form.dataset_id
      ? "Curated release population"
      : filters?.sample_populations?.find((item) => item.id === form.filters.sample_population)?.label || "",
    adjustmentSummary: formatAdjustmentSummary(
      selectedAdjustmentCovariates,
      selectedExternalAdjustmentCovariates,
      form.external_covariates,
    ),
    covariateCount:
      selectedAdjustmentCovariates.length
      + selectedExternalAdjustmentCovariates.length,
    requirements: [...new Set(analysisStepRequirements.filter(Boolean))],
  });
  function updateForm(key, value) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  function selectExpressionScale(value) {
    updateForm(
      form.dataset_id ? "expression_layer_id" : "expression_scale",
      value,
    );
    invalidateExpressionComparisonContext();
  }

  function navigateAnalysisStep(nextStep) {
    const boundedStep = Math.max(0, Math.min(ANALYSIS_WORKFLOW_STEPS.length - 1, nextStep));
    setAnalysisStep(boundedStep);
    if (boundedStep !== 4) setSurvivalPlotEditorOpen(false);
    window.requestAnimationFrame(() => {
      analysisStepPanelRef.current?.focus({ preventScroll: true });
      document
        .getElementById(workflowStepControlId(ANALYSIS_WORKFLOW_STEPS[boundedStep], "analysis-step"))
        ?.scrollIntoView({ behavior: "auto", block: "nearest", inline: "center" });
      analysisStepPanelRef.current
        ?.closest(".analysis-step-controls")
        ?.scrollIntoView({ behavior: "auto", block: "start" });
    });
  }

  function navigateToPage(page, { syncTutorial = true } = {}) {
    if (page === activePage) return;
    if (
      activePage === "analysis"
      && page !== "analysis"
      && dataSourceMode === "upload"
      && userDatasetUploadDirty
      && !window.confirm(
        "Leave this upload setup? Selected files cannot be restored automatically.",
      )
    ) {
      return;
    }
    hasNavigatedRef.current = true;
    setCohortPickerOpen(false);
    setActivePage(page);
    if (syncTutorial) tutorialController.setView?.(page);
    window.requestAnimationFrame(() => window.scrollTo({ top: 0, left: 0, behavior: "auto" }));
  }

  function applyTutorialPreset(presetId) {
    applyTutorialPresetWithAdapters(presetId, {
      setters: {
        analysisResults: setAnalysisResults,
        loading: setLoading,
        error: setError,
        compare: setCompare,
        expressionComparison: setExpressionComparison,
        gsea: setGsea,
        multiverse: setMultiverse,
        panCancer: setPanCancer,
        dataSourceMode: setDataSourceMode,
        userDatasetUploadStep: setUserDatasetUploadStep,
        analysisStep: setAnalysisStep,
        form: setForm,
      },
      navigate: navigateToPage,
    });
  }

  function resumeWorkspaceDraft() {
    const draft = pendingWorkspaceDraft;
    if (!draft) return;
    setForm((current) => ({
      ...current,
      ...(draft.form || {}),
      combined_signature: {
        ...current.combined_signature,
        ...(draft.form?.combined_signature || {}),
      },
      signature_panel: {
        ...current.signature_panel,
        ...(draft.form?.signature_panel || {}),
      },
      plot_style: {
        ...current.plot_style,
        ...(draft.form?.plot_style || {}),
        continuous: {
          ...current.plot_style.continuous,
          ...(draft.form?.plot_style?.continuous || {}),
        },
        cox_forest: {
          ...current.plot_style.cox_forest,
          ...(draft.form?.plot_style?.cox_forest || {}),
        },
      },
      filters: draft.form?.filters
        ? { ...EMPTY_FILTERS, ...draft.form.filters }
        : current.filters,
      external_covariates: null,
      external_adjustment_covariates: [],
    }));
    setCompare((current) => ({ ...current, ...(draft.compare || {}), running: false, results: [], result_context: null, grouped_family: null, active_run_id: null, error: "" }));
    setExpressionComparison((current) => ({
      ...current,
      ...(draft.expressionComparison || {}),
      running: false,
      result: null,
      error: "",
    }));
    setGsea((current) => ({ ...current, ...(draft.gsea || {}), running: false, result: null, error: "" }));
    setMultiverse((current) => ({ ...current, ...(draft.multiverse || {}), running: false, result: null, error: "" }));
    setPanCancer((current) => ({
      ...current,
      ...(draft.panCancer || {}),
      hierarchicalRequest: {
        ...current.hierarchicalRequest,
        ...(draft.panCancer?.hierarchicalRequest || {}),
      },
      running: false,
      result: null,
      error: "",
      hierarchicalRunning: false,
      hierarchicalResult: null,
      hierarchicalError: "",
    }));
    clearWorkspaceDraft();
    setPendingWorkspaceDraft(null);
    navigateToPage(draft.active_page || "analysis");
  }

  function discardWorkspaceDraft() {
    clearWorkspaceDraft();
    setPendingWorkspaceDraft(null);
  }

  function navigateTutorial(page, {
    anchor,
    tutorialStateCommitted = false,
    focusLearningCenter = false,
    workflowStepId = null,
    syncOnly = false,
  } = {}) {
    navigateToPage(page, { syncTutorial: !tutorialStateCommitted });
    if (page === "analysis" && workflowStepId) {
      const workflowStepIndex = ANALYSIS_WORKFLOW_STEPS.findIndex(
        (item) => item.id === workflowStepId,
      );
      if (workflowStepIndex >= 0) setAnalysisStep(workflowStepIndex);
    }
    if (page === "examples" && ["tutorials", "manuals"].includes(workflowStepId)) {
      tutorialController.setTab(workflowStepId);
    }
    if (syncOnly) return;
    if (focusLearningCenter) {
      window.requestAnimationFrame(() => {
        window.requestAnimationFrame(() => {
          document.querySelector('.trace-tutorial-tabs [aria-selected="true"]')?.focus({ preventScroll: true });
        });
      });
    }
    if (!anchor) return;
    window.requestAnimationFrame(() => {
      window.requestAnimationFrame(() => focusGuideAnchor(anchor));
    });
  }

  function updateCombinedSignature(key, patch) {
    setForm((current) => ({
      ...current,
      combined_signature: {
        ...current.combined_signature,
        [key]: {
          ...current.combined_signature[key],
          ...patch,
        },
      },
    }));
  }

  function updateCombinedGroupingMethod(value) {
    setForm((current) => ({
      ...current,
      combined_signature: {
        ...current.combined_signature,
        grouping_method: value,
      },
    }));
  }

  function updateCombinedGeneQuery(key, value) {
    setCombinedGeneQueries((current) => ({ ...current, [key]: value }));
  }

  function updatePanelSignature(signatureId, patch) {
    setForm((current) => ({
      ...current,
      signature_panel: {
        ...current.signature_panel,
        signatures: current.signature_panel.signatures.map((signature) =>
          signature.id === signatureId
            ? { ...signature, ...patch }
            : signature,
        ),
      },
    }));
  }

  function updatePanelGeneQuery(index, value) {
    setPanelGeneQueries((current) => {
      const next = [...current];
      next[index] = value;
      return next;
    });
  }

  function addPanelSignature() {
    if (form.signature_panel.signatures.length >= MAX_SIGNATURE_PANEL_SIZE) return;
    setForm((current) => {
      const signatures = current.signature_panel.signatures;
      if (signatures.length >= MAX_SIGNATURE_PANEL_SIZE) return current;
      const usedIds = new Set(signatures.map((signature) => signature.id));
      let seed = signatures.length;
      let signature = createPanelSignature(seed);
      while (usedIds.has(signature.id)) {
        seed += 1;
        signature = createPanelSignature(seed);
      }
      return {
        ...current,
        signature_panel: {
          ...current.signature_panel,
          signatures: [...signatures, signature],
        },
      };
    });
    setPanelGeneQueries((current) => [...current, ""]);
  }

  function removePanelSignature(signatureId) {
    const removedIndex = form.signature_panel.signatures.findIndex(
      (signature) => signature.id === signatureId,
    );
    setForm((current) => {
      if (current.signature_panel.signatures.length <= 2) return current;
      return {
        ...current,
        signature_panel: {
          ...current.signature_panel,
          signatures: current.signature_panel.signatures.filter(
            (signature) => signature.id !== signatureId,
          ),
        },
      };
    });
    if (removedIndex >= 0) {
      setPanelGeneQueries((current) =>
        current.filter((_value, index) => index !== removedIndex),
      );
    }
  }

  function movePanelSignature(signatureId, direction) {
    const currentIndex = form.signature_panel.signatures.findIndex(
      (signature) => signature.id === signatureId,
    );
    const queryTarget = currentIndex + direction;
    setForm((current) => {
      const signatures = [...current.signature_panel.signatures];
      const index = signatures.findIndex(
        (signature) => signature.id === signatureId,
      );
      const target = index + direction;
      if (index < 0 || target < 0 || target >= signatures.length) return current;
      [signatures[index], signatures[target]] = [
        signatures[target],
        signatures[index],
      ];
      return {
        ...current,
        signature_panel: {
          ...current.signature_panel,
          signatures,
        },
      };
    });
    if (
      currentIndex >= 0
      && queryTarget >= 0
      && queryTarget < form.signature_panel.signatures.length
    ) {
      setPanelGeneQueries((current) => {
        const next = [...current];
        [next[currentIndex], next[queryTarget]] = [
          next[queryTarget] || "",
          next[currentIndex] || "",
        ];
        return next;
      });
    }
  }

  function updateFilters(key, value) {
    setForm((current) => ({
      ...current,
      filters: { ...(key === "sample_population" ? EMPTY_FILTERS : current.filters), [key]: value },
    }));
    invalidateExpressionComparisonContext();
  }

  function invalidateExpressionComparisonContext({ resetGroups = false } = {}) {
    setExpressionComparison((current) => ({
      ...current,
      ...(resetGroups
        ? {
            group_a_values: [],
            group_b_values: [],
            survival_analysis_id: "",
            survival_group_a: "",
            survival_group_b: "",
          }
        : {}),
      context_epoch: current.context_epoch + 1,
      running: false,
      result: null,
      result_context_fingerprint: "",
      error: "",
    }));
  }

  function toggleAdjustmentCovariate(value) {
    setForm((current) => {
      const selected = current.adjustment_covariates || [];
      return {
        ...current,
        adjustment_covariates: selected.includes(value)
          ? selected.filter((item) => item !== value)
          : [...selected, value],
      };
    });
  }

  function updateExternalAdjustment(dataset, selected) {
    setForm((current) => ({
      ...current,
      external_covariates: dataset,
      external_adjustment_covariates: [
        ...new Set(selected || []),
      ],
    }));
  }

  function updatePlotStyle(key, value) {
    setForm((current) => ({
      ...current,
      plot_style: { ...current.plot_style, [key]: value },
    }));
  }

  function updateArtifactPlotStyle(artifact, key, value) {
    setForm((current) => ({
      ...current,
      plot_style: {
        ...current.plot_style,
        [artifact]: {
          ...(DEFAULT_PLOT_STYLE[artifact] || {}),
          ...(current.plot_style?.[artifact] || {}),
          [key]: value,
        },
      },
    }));
  }

  function updatePaletteColor(index, value) {
    setForm((current) => {
      const palette = [...current.plot_style.palette];
      palette[index] = value;
      return {
        ...current,
        plot_style: { ...current.plot_style, palette },
      };
    });
  }

  function selectCohort(value) {
    const externalOnly = cohorts.find(
      (cohort) => cohort.id === value,
    )?.status === "external_only";
    setDataSourceMode("catalog");
    setForm((current) => ({
      ...current,
      cohort: value,
      dataset_id: null,
      dataset_release_id: null,
      expression_layer_id: null,
      filters: {
        ...EMPTY_FILTERS,
        sample_population: externalOnly
          ? null
          : defaultSamplePopulation(value),
      },
      external_covariates: null,
      external_adjustment_covariates: [],
    }));
    setRepositoryLayers([]);
    setCohortPickerOpen(false);
    setCohortQuery("");
    setAnalysisResults([]);
    setCompare((current) => ({ ...current, results: [], result_context: null, grouped_family: null, active_run_id: null, running: false, error: "" }));
    invalidateExpressionComparisonContext({ resetGroups: true });
    setGsea((current) => ({
      ...current,
      group_a_values: [],
      group_b_values: [],
      survival_analysis_id: "",
      survival_group_a: "",
      survival_group_b: "",
      result: null,
      error: "",
    }));
    setMultiverse((current) => ({ ...current, result: null, error: "" }));
    setError("");
  }

  function changeDataSourceMode(mode) {
    setDataSourceMode(mode);
    const selectedIsUser = String(form.dataset_id || "").startsWith("user-");
    if (
      (mode === "upload" && !selectedIsUser)
      || (mode === "catalog" && selectedIsUser)
    ) {
      setForm((current) => ({
        ...current,
        cohort: "",
        dataset_id: null,
        dataset_release_id: null,
        expression_layer_id: null,
        endpoint: "OS",
        filters: { ...EMPTY_FILTERS },
        adjustment_covariates: DEFAULT_ADJUSTMENT_COVARIATES,
      }));
      setRepositoryLayers([]);
      setEndpointOptions([]);
      setAnalysisResults([]);
      invalidateExpressionComparisonContext({ resetGroups: true });
      setGsea((current) => ({
        ...current,
        group_a_values: [],
        group_b_values: [],
        survival_analysis_id: "",
        survival_group_a: "",
        survival_group_b: "",
        result: null,
        error: "",
      }));
    }
  }

  function openUserDataUpload() {
    changeDataSourceMode("upload");
    navigateToPage("analysis");
    navigateAnalysisStep(0);
  }

  function selectRepositoryDataset(datasetId) {
    const dataset =
      (userDataset?.id === datasetId ? userDataset : null)
      || repositoryDatasets.find((item) => item.id === datasetId);
    setDataSourceMode(dataset?.kind === "user" ? "upload" : "catalog");
    setForm((current) => ({
      ...current,
      cohort: dataset?.tcga_cohort || current.cohort,
      dataset_id: dataset?.id || null,
      dataset_release_id: dataset?.active_release_id || null,
      expression_layer_id: null,
      filters: { ...EMPTY_FILTERS },
      external_covariates: null,
      external_adjustment_covariates: [],
    }));
    setAnalysisResults([]);
    setCompare((current) => ({ ...current, results: [], result_context: null, grouped_family: null, active_run_id: null, running: false, error: "" }));
    invalidateExpressionComparisonContext({ resetGroups: true });
    setGsea((current) => ({
      ...current,
      group_a_values: [],
      group_b_values: [],
      survival_analysis_id: "",
      survival_group_a: "",
      survival_group_b: "",
      result: null,
      error: "",
    }));
    setMultiverse((current) => ({ ...current, result: null, error: "" }));
    setError("");
  }

  function selectUserDataset(dataset) {
    setUserDataset(dataset);
    persistUserDatasetReference(dataset);
    setLocalProjects(loadLocalProjects());
    setDataSourceMode("upload");
    setForm((current) => ({
      ...current,
      cohort: dataset.tcga_cohort,
      dataset_id: dataset.id,
      dataset_release_id: dataset.active_release_id,
      expression_layer_id: dataset.expression_layer?.value || null,
      endpoint: dataset.endpoint?.value || "",
      filters: { ...EMPTY_FILTERS },
      external_covariates: null,
      external_adjustment_covariates: [],
    }));
    setRepositoryLayers(
      dataset.expression_layer ? [dataset.expression_layer] : [],
    );
    setEndpointOptions(
      dataset.endpoint
        ? [{
            ...dataset.endpoint,
            patients: dataset.endpoint.patient_count,
            events: dataset.endpoint.event_count,
          }]
        : [NO_SURVIVAL_ENDPOINT],
    );
    setAnalysisResults([]);
    setCompare((current) => ({ ...current, results: [], result_context: null, grouped_family: null, active_run_id: null, running: false, error: "" }));
    invalidateExpressionComparisonContext({ resetGroups: true });
    setGsea((current) => ({
      ...current,
      group_a_values: [],
      group_b_values: [],
      survival_analysis_id: "",
      survival_group_a: "",
      survival_group_b: "",
      result: null,
      error: "",
    }));
    setMultiverse((current) => ({ ...current, result: null, error: "" }));
    setError("");
  }

  async function openLocalProject(id) {
    const previous = loadUserDatasetReference();
    const reference = localProjects.find(project => project.id === id);
    if (!reference) {
      persistUserDatasetReference(null);
      setUserDataset(null);
      setForm(current => ({...current, cohort: "", dataset_id: null, dataset_release_id: null, expression_layer_id: null}));
      return;
    }
    persistUserDatasetReference(reference);
    try {
      const dataset = await getUserDataset(reference.id);
      selectUserDataset({...dataset, access_token: reference.access_token});
    } catch (error) {
      persistUserDatasetReference(previous);
      setError(error.message);
    }
  }

  async function removeUserDataset() {
    if (!userDataset?.id) return;
    await deleteUserDataset(userDataset.id);
    forgetLocalProject(userDataset.id);
    setLocalProjects(loadLocalProjects());
    persistUserDatasetReference(null);
    setUserDataset(null);
    setDataSourceMode("catalog");
    setForm((current) => ({
      ...current,
      cohort: "",
      dataset_id: null,
      dataset_release_id: null,
      expression_layer_id: null,
      endpoint: "OS",
      filters: { ...EMPTY_FILTERS },
      adjustment_covariates: DEFAULT_ADJUSTMENT_COVARIATES,
    }));
    setRepositoryLayers([]);
    setEndpointOptions([]);
    setAnalysisResults([]);
    invalidateExpressionComparisonContext({ resetGroups: true });
    setGsea((current) => ({
      ...current,
      group_a_values: [],
      group_b_values: [],
      survival_analysis_id: "",
      survival_group_a: "",
      survival_group_b: "",
      result: null,
      error: "",
    }));
  }

  function openRepositoryDatasetModule(datasetId, moduleId = "analysis") {
    const dataset = repositoryDatasets.find((item) => item.id === datasetId);
    if (!dataset || !datasetSupportsModule(dataset, moduleId)) return;
    selectRepositoryDataset(datasetId);
    navigateToPage(moduleId);
    if (moduleId === "analysis") setAnalysisStep(0);
  }

  function toggleFilterValue(key, value) {
    const current = form.filters[key] || [];
    const next = current.includes(value)
      ? current.filter((item) => item !== value)
      : [...current, value];
    updateFilters(key, next);
  }

  function clearFilter(key) {
    updateFilters(key, []);
  }

  function updatePanCancer(key, value) {
    setPanCancer((current) => ({ ...current, [key]: value }));
  }

  function dismissDownloadNotice(id) {
    setDownloadNotices((current) => current.filter((notice) => notice.id !== id));
  }

  function updateDownloadNotice(id, patch) {
    setDownloadNotices((current) =>
      current.map((notice) => (notice.id === id ? { ...notice, ...patch } : notice)),
    );
  }

  async function startDownload(href, label) {
    if (!href) return;
    const id = `${Date.now()}-${Math.random().toString(16).slice(2)}`;
    setDownloadNotices((current) => [
      ...current,
      { id, label, status: "running", message: "Preparing download" },
    ]);
    try {
      const response = await authorizedFetch(apiUrl(href));
      if (!response.ok) {
        throw new Error(response.statusText || `HTTP ${response.status}`);
      }
      const blob = await response.blob();
      const filename =
        filenameFromDisposition(response.headers.get("Content-Disposition")) ||
        fallbackDownloadFilename(label, href);
      const objectUrl = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = objectUrl;
      anchor.download = filename;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
      updateDownloadNotice(id, { status: "done", message: "Download ready" });
      window.setTimeout(() => dismissDownloadNotice(id), 4500);
    } catch (err) {
      updateDownloadNotice(id, {
        status: "failed",
        message: err?.message || "Download failed",
      });
    }
  }

  async function startPlotDownload(svgSelector, filenameBase, format) {
    const id = `${Date.now()}-${Math.random().toString(16).slice(2)}`;
    const label = `${filenameBase}.${format}`;
    setDownloadNotices((current) => [
      ...current,
      { id, label, status: "running", message: "Rendering plot" },
    ]);
    try {
      await downloadSvgPlot(svgSelector, `${filenameBase}.${format}`, format);
      updateDownloadNotice(id, { status: "done", message: "Download ready" });
      window.setTimeout(() => dismissDownloadNotice(id), 4500);
    } catch (err) {
      updateDownloadNotice(id, {
        status: "failed",
        message: err?.message || "Plot download failed",
      });
    }
  }

  function scrollToResults() {
    window.requestAnimationFrame(() => {
      resultPanelRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  }

  async function runAnalysis() {
    if (!canRun) return;
    if (!requestContractValid) {
      setError(
        activeMarkerContractError
        || analysisFiltersValidation.errors[0]
        || percentileValidation.error
        || plotStyleValidation.errors[0]
        || "Review the analysis settings before running.",
      );
      return;
    }
    const submittedFingerprint = currentSurvivalFingerprint;
    const submittedEpoch = analysisResultEpoch.current;
    function commitResults(results) {
      if (submittedEpoch !== analysisResultEpoch.current) return;
      storeAnalysisResults(results);
      setAnalysisResultFingerprint(submittedFingerprint);
    }
    function reportRunError(message) {
      if (submittedEpoch === analysisResultEpoch.current) setError(message);
    }
    if (isPanelMode) {
      const validation = validateSignaturePanel(effectivePanelSignatures);
      if (!validation.valid) {
        setError(validation.errors[0] || "Complete the signature panel before running it.");
        return;
      }

      setLoading(true);
      setError("");
      scrollToResults();
      setPanelGeneQueries([]);
      setForm((current) => ({
        ...current,
        signature_panel: {
          ...current.signature_panel,
          signatures: current.signature_panel.signatures.map((signature, index) => ({
            ...signature,
            gene_symbol: validation.signatures[index].gene_symbol,
          })),
        },
      }));
      try {
        const payload = survivalRequests[0];
        const result = await createSignaturePanelAnalysis(payload);
        commitResults([result]);
      } catch (err) {
        reportRunError(formatError(err));
      } finally {
        setLoading(false);
      }
      return;
    }

    if (isCombinedMode) {
      const normalizedA = geneInputTokens(effectiveSignatureAInput).join(", ");
      const normalizedB = geneInputTokens(effectiveSignatureBInput).join(", ");
      if (!uniqueGeneSymbols(normalizedA).length || !uniqueGeneSymbols(normalizedB).length) {
        setError("Enter genes for both signatures before running the combined analysis.");
        return;
      }

      setLoading(true);
      setError("");
      scrollToResults();
      setCombinedGeneQueries({ a: "", b: "" });
      setForm((current) => ({
        ...current,
        combined_signature: {
          ...current.combined_signature,
          signature_a: { ...current.combined_signature.signature_a, gene_symbol: normalizedA },
          signature_b: { ...current.combined_signature.signature_b, gene_symbol: normalizedB },
        },
      }));
      try {
        const payload = survivalRequests[0];
        const result = await createCombinedAnalysis(payload);
        commitResults([result]);
      } catch (err) {
        reportRunError(formatError(err));
      } finally {
        setLoading(false);
      }
      return;
    }

    const sourceInput = geneQuery.trim() ? addGeneToken(form.gene_symbol, geneQuery) : form.gene_symbol;
    const normalizedGenes = uniqueGeneSymbols(sourceInput);
    if (!normalizedGenes.length) {
      setError("Enter at least one gene symbol before running the analysis.");
      return;
    }

    setLoading(true);
    setError("");
    scrollToResults();
    const normalizedInput =
      form.signature_method === "single"
        ? normalizedGenes.join(", ")
        : geneInputTokens(sourceInput).join(", ");
    setGeneQuery("");
    updateForm("gene_symbol", normalizedInput);

    try {
      if (form.signature_method === "single") {
        const payloads = survivalRequests;
        if (payloads.length === 1) {
          const result = await createAnalysis(payloads[0]);
          commitResults([result]);
        } else {
          const batch = await createAnalysesBatch(payloads, ANALYSIS_BATCH_CONCURRENCY);
          const successful = batch.results
            .filter((item) => item.status === "completed" && item.result)
            .map((item) => item.result);
          commitResults(successful);
          if (batch.failed) {
            const firstFailure = batch.results.find((item) => item.status === "failed");
            reportRunError(`${batch.failed} analysis${batch.failed === 1 ? "" : "es"} failed. ${formatBatchItemError(firstFailure)}`);
          }
        }
      } else {
        const payload = survivalRequests[0];
        const result = await createAnalysis(payload);
        commitResults([result]);
      }
    } catch (err) {
      reportRunError(formatError(err));
    } finally {
      setLoading(false);
    }
  }

  async function exportExploratorySession() {
    const selected = sessionHistory.entries.filter((entry) => entry.included);
    if (!selected.length) {
      setSessionExport((current) => ({
        ...current,
        error: "Select at least one recorded run.",
      }));
      return;
    }
    if (selected.some((entry) => !terminalSessionEntry(entry))) {
      setSessionExport((current) => ({
        ...current,
        error: "Wait for every selected run to reach a terminal status.",
      }));
      return;
    }
    const payload = buildSessionExportPayload(sessionHistory);
    setSessionExport((current) => ({ ...current, running: true, error: "" }));
    try {
      const result = await createExploratorySession(payload);
      setSessionExport({ running: false, result, error: "" });
    } catch (err) {
      setSessionExport((current) => ({
        ...current,
        running: false,
        error: formatError(err),
      }));
    }
  }

  return (
    <>
      <a className="skip-link" href="#main-content">Skip to main content</a>
      <div
        className="app-shell"
        data-page={activePage}
      >
      <header className="app-header">
        <div className="app-header-brand">
          <button
            type="button"
            className="brand"
            onClick={() => navigateToPage("home")}
            aria-label="Go to TRACE Explorer home"
            title="TRACE Explorer home"
          >
            <TraceLogo key={`brand-${activePage}`} animated={hasNavigatedRef.current} />
            <span className="brand-copy">
              <strong>TRACE</strong>
              <span>Explorer</span>
            </span>
          </button>
        </div>

        <nav
          ref={workspaceNavRef}
          className="top-nav"
          aria-label="Workspace pages"
          onFocusCapture={(event) => {
            if (!event.target.matches?.(":focus-visible")) return;
            keepNavigationItemVisible(
              event.currentTarget,
              event.target.closest?.("button"),
            );
          }}
        >
          <WorkspaceNavButton
            item={APP_NAV_HOME}
            activePage={activePage}
            onNavigate={navigateToPage}
          />
          {APP_NAV_GROUPS.map((group) => (
            <div
              className="top-nav-group"
              role="group"
              aria-labelledby={`top-nav-group-${group.id}`}
              key={group.id}
            >
              <span className="top-nav-group-label" id={`top-nav-group-${group.id}`}>
                {group.label}
              </span>
              <div className="top-nav-group-items">
                {group.items.map((item) => (
                  <WorkspaceNavButton
                    key={item.id}
                    item={item}
                    activePage={activePage}
                    onNavigate={navigateToPage}
                  />
                ))}
              </div>
            </div>
          ))}
        </nav>
        {isLocalDesktop() && window.traceDesktop && (
          <button type="button" className="desktop-data-button"
            onClick={() => window.traceDesktop.openDataManager()}
          >Manage data</button>
        )}
      </header>

      <ServiceStatusNotice state={serviceState} onRetry={reloadApplicationData} />

      <main id="main-content" className="workspace" tabIndex={-1}>
        {activePage !== "home" && (
          <header className="topbar">
            <div>
              <div className="page-title-line">
                <h1>{pageMeta.title}</h1>
                {activePage === "help" && (
                  <HelpButton label="Methods" helpId="methodsPage" />
                )}
              </div>
              <p className="page-summary">{pageMeta.summary}</p>
            </div>
            {activeModule?.showLearnAction && quickGuide && (
              <div className="tutorial-entry-actions">
              <button
                ref={tutorialTriggerRef}
                type="button"
                className="secondary-button tutorial-quick-start"
                aria-controls={quickGuideIsOpen ? TUTORIAL_DOCK_ID : undefined}
                aria-expanded={quickGuideIsOpen}
                data-progress={quickGuideProgress?.status || "not_started"}
                onClick={(event) => {
                  tutorialController.captureTrigger(event.currentTarget);
                  if (quickGuideIsOpen) {
                    tutorialController.close();
                  } else if (quickGuideProgress?.status === "completed") {
                    tutorialController.start(quickGuideId);
                  } else if (quickGuideProgress) {
                    tutorialController.resume(quickGuideId);
                  } else {
                    tutorialController.start(quickGuideId);
                  }
                }}
              >
                <TraceIcon role="document.guide" size="sm" />
                {quickGuideActionLabel}
              </button>
              <GuideVideo key={quickGuideId} guideId={quickGuideId} title={quickGuide.title} />
              </div>
            )}
          </header>
        )}

        <DraftRecoveryNotice
          draft={pendingWorkspaceDraft}
          onResume={resumeWorkspaceDraft}
          onDiscard={discardWorkspaceDraft}
        />

        <ModuleErrorBoundary resetKey={activePage} moduleName={pageMeta.title}>
          <Suspense fallback={<ModuleLoadFallback label={pageMeta.title} />}>
          <div
            key={`page-${activePage}`}
            className={`page-stage${hasNavigatedRef.current ? " is-entering" : ""}`}
          >
        {activePage === "home" ? (
          <HomePage
            health={health}
            summary={datasetSummary}
            cohorts={cohorts}
            repositoryCoverage={repositoryCoverage}
            serviceStatus={serviceState.status}
            onNavigate={navigateToPage}
            onUpload={openUserDataUpload}
            onBrowseGuides={() => {
              tutorialController.setTab("tutorials");
              navigateToPage("examples");
            }}
          />
        ) : activePage === "analysis" ? (
          <>
            <ActiveJobRecovery
              sourceView="analysis"
              busy={loading}
              onRecover={(result, job) => {
                const recovered = job?.kind === "batch"
                  ? (result?.results || [])
                    .filter((item) => item.status === "completed" && item.result)
                    .map((item) => item.result)
                  : [result].filter(Boolean);
                setAnalysisResults(recovered);
                setLoading(false);
                setError("");
              }}
            />
            <div className="layout analysis-workflow-layout">
              <section className="control-panel analysis-step-controls" aria-label="Analysis controls">
                <AnalysisWorkflowStepper
                  steps={ANALYSIS_WORKFLOW_STEPS}
                  activeStep={analysisStep}
                  completion={analysisStepCompletion}
                  summary=""
                  onSelect={navigateAnalysisStep}
                />
                {form.cohort && !requiresDatasetSelection && !analysisMetadataReady && (
                  <div className="survival-metadata-status" role="status" aria-live="polite">
                    <strong>{t.entry(analysisMetadata.status === "error" && analysisMetadata.key === analysisMetadataKey ? "survivalMetadataError" : "survivalMetadata").term}</strong>
                    <FieldHelp helpId={analysisMetadata.status === "error" && analysisMetadata.key === analysisMetadataKey ? "survivalMetadataError" : "survivalMetadata"} />
                    {analysisMetadata.status === "error" && analysisMetadata.key === analysisMetadataKey && (
                      <>
                        <button type="button" onClick={() => setMetadataRetry((value) => value + 1)}>Retry cohort details</button>
                        <details><summary>Technical details</summary><p>{analysisMetadata.error}</p></details>
                      </>
                    )}
                  </div>
                )}

                <section
                  ref={analysisStepPanelRef}
                  className="analysis-step-panel"
                  id={`analysis-step-panel-${activeAnalysisStep.id}`}
                  aria-labelledby={workflowStepControlId(activeAnalysisStep, "analysis-step")}
                  tabIndex={-1}
                >
                  {activeAnalysisStep.id === "data" && (
                    <>
                      <PanelHeader iconRole="module.dataset" title="Dataset" helpId="dataset" />
                      <div className="dataset-source-mode" aria-label="Dataset source">
                        <button
                          type="button"
                          className={dataSourceMode === "catalog" ? "selected" : ""}
                          aria-pressed={dataSourceMode === "catalog"}
                          onClick={() => changeDataSourceMode("catalog")}
                        >
                          <TraceIcon role="data.cohort" size="sm" />
                          Public cohorts
                        </button>
                        <GuideAnchor
                          as="button"
                          anchor={GUIDE_ANCHORS.SURVIVAL_UPLOAD}
                          label="Upload your own dataset"
                          tabIndex={0}
                          type="button"
                          className={dataSourceMode === "upload" ? "selected" : ""}
                          aria-pressed={dataSourceMode === "upload"}
                          onClick={() => changeDataSourceMode("upload")}
                        >
                          <TraceIcon role="file.csv" size="sm" />
                          Upload your data
                        </GuideAnchor>
                      </div>
                      {dataSourceMode === "catalog" ? (
                        <>
                          <CohortPicker
                            cohorts={cohorts}
                            visibleCohorts={moduleVisibleCohorts}
                            selectedCohort={selectedCohort}
                            selectedCohortId={form.cohort}
                            query={cohortQuery}
                            setQuery={setCohortQuery}
                            open={cohortPickerOpen}
                            setOpen={setCohortPickerOpen}
                            onSelect={selectCohort}
                          />
                          <RepositorySourceSelector
                            compact
                            key={form.cohort}
                            selectedCohort={selectedCohort}
                            datasets={cohortRepositoryDatasets}
                            selectedDataset={selectedRepositoryDataset}
                            onSelect={selectRepositoryDataset}
                            analysisType="analysis"
                          />
                        </>
                      ) : (
                        <>
                        {isLocalDesktop() && localProjects.length > 0 && <label>
                          <span>Saved project</span>
                          <select value={userDataset?.id || ""} onChange={event => openLocalProject(event.target.value)}>
                            <option value="">Create a new project</option>
                            {localProjects.map(project => <option key={project.id} value={project.id}>{project.name}</option>)}
                          </select>
                        </label>}
                        <UserDatasetUpload
                          key={userDataset?.id || "new-local-project"}
                          cancerTypes={uploadCancerTypes}
                          currentDataset={userDataset}
                          selected={userDataset?.id === form.dataset_id}
                          onStepChange={setUserDatasetUploadStep}
                          onDirtyChange={setUserDatasetUploadDirty}
                          onReady={selectUserDataset}
                          onSelect={() => userDataset && selectUserDataset(userDataset)}
                          onDelete={removeUserDataset}
                          onNavigate={navigateToPage}
                        />
                        </>
                      )}
                      <CohortAdjustmentNotice filters={analysisMetadataReady ? filters : null} />
                      {analysisMetadataReady && <MolecularPopulationSelector
                        form={form}
                        filters={filters}
                        onChange={(value) => updateFilters("sample_population", value)}
                      />}
                      {selectedCohort && (
                        <div className="cohort-summary">
                          <div className="cohort-title">
                            <strong>
                              {selectedRepositoryDataset?.name
                                || getCohortName(selectedCohort.id)}
                            </strong>
                            <span>
                              {selectedRepositoryDataset?.kind === "user"
                                ? "Private upload"
                                : selectedRepositoryDataset?.source_accession
                                || selectedCohort.id}
                            </span>
                          </div>
                          <SummaryStat
                            label="Cohort RNA samples"
                            value={
                              selectedRepositoryDataset?.sample_count
                                ?? selectedCohort.n_samples_paired
                            }
                          />
                          <SummaryStat
                            label="Cohort patients"
                            value={
                              selectedRepositoryDataset?.patient_count
                                ?? selectedCohort.n_patients_paired
                            }
                          />
                          <SummaryStat
                            label={selectedRepositoryDataset ? "Genes" : "Primary tumor RNA samples"}
                            value={
                              selectedRepositoryDataset?.gene_count
                                ?? selectedCohort.n_primary_tumor
                            }
                          />
                          <p>
                            {selectedRepositoryDataset?.kind === "user"
                              ? `${selectedRepositoryDataset.endpoint?.label || "Survival endpoint"} · ${selectedRepositoryDataset.expires_at ? `retained until ${formatDateTime(selectedRepositoryDataset.expires_at)}` : "saved on this computer"}`
                              : selectedRepositoryDataset?.cohort_context
                              || selectedCohort.primary_site}
                          </p>
                          <FieldHelp helpId="survivalCohortCounts" />
                        </div>
                      )}
                      {(dataSourceMode === "catalog" || selectedRepositoryDataset?.kind === "user") && (
                        <div className="analysis-step-subsection">
                          <ExpressionDataSelector options={analysisExpressionScales}
                            value={form.dataset_id ? form.expression_layer_id : form.expression_scale}
                            onChange={selectExpressionScale} />
                        </div>
                      )}
                    </>
                  )}

                  {activeAnalysisStep.id === "design" && (
                    <>
                      <PanelHeader iconRole="module.geneAnalysis" title="Gene analysis" helpId="analysisDesign" />
                      <div className="axis-control two-options">
                        <span>Analysis design</span>
                        <div>
                          {[
                            ["single_signature", "Genes or one signature"],
                            ["combined_signatures", "Two-signature interaction"],
                            ["signature_panel", "Signature panel"],
                          ].map(([value, label]) => (
                            <button
                              key={value}
                              type="button"
                              className={form.analysis_kind === value ? "selected" : ""}
                              onClick={() => updateForm("analysis_kind", value)}
                            >
                              {label}
                            </button>
                          ))}
                        </div>
                      </div>
                      {isPanelMode ? (
                        <SignaturePanelBuilder
                          panel={form.signature_panel}
                          onPanelNameChange={(name) => setForm((current) => ({
                            ...current,
                            signature_panel: {
                              ...current.signature_panel,
                              name,
                            },
                          }))}
                          onSignatureChange={updatePanelSignature}
                          onAdd={addPanelSignature}
                          onRemove={removePanelSignature}
                          onMove={movePanelSignature}
                          queries={panelGeneQueries}
                          onQueryChange={updatePanelGeneQuery}
                          suggestionStates={panelGeneSuggestionStates}
                          validation={panelValidation}
                          rankScoring={rankScoring}
                        />
                      ) : !isCombinedMode ? (
                        <GeneSelector
                          label={form.signature_method === "single" ? "Gene symbols" : "Signature genes"}
                          value={form.gene_symbol}
                          onChange={(value) => updateForm("gene_symbol", value)}
                          draft={geneQuery}
                          setDraft={setGeneQuery}
                          suggestions={genes}
                          suggestionsLoading={geneSuggestionState.loading}
                          suggestionsError={geneSuggestionState.error}
                          placeholder={signatureMethodUsesDirection(form.signature_method)
                            ? "Type IFNG, GZMB, TGFB1:-1..."
                            : form.signature_method === "single"
                              ? "Type TP53, KRAS, EGFR..."
                              : signatureMethodUsesNumericWeights(form.signature_method)
                                ? "Type TP53, KRAS or TP53:1"
                                : "Type TP53, KRAS..."}
                          helpId={form.signature_method === "single" ? "survivalSingleGenes" : "signatureGenesWeighted"}
                        />
                      ) : (
                        <CombinedSignatureBuilder
                          value={form.combined_signature}
                          onSignatureChange={updateCombinedSignature}
                          queries={combinedGeneQueries}
                          setQuery={updateCombinedGeneQuery}
                          suggestions={combinedGeneSuggestions}
                          suggestionStates={combinedGeneSuggestionStates}
                          rankScoring={rankScoring}
                        />
                      )}
                      {!isCombinedMode && !isPanelMode && (
                        <div className="axis-control">
                          <LabelWithHelp
                            label="Gene mode"
                            helpId={`score.${form.signature_method}`}
                          />
                          <div>
                            {SIGNATURE_METHOD_OPTIONS.map(({ value, label }) => {
                              const rankUnavailable = signatureMethodUsesDirection(value)
                                && !rankScoring.available;
                              return (
                              <button
                                key={value}
                                type="button"
                                aria-pressed={form.signature_method === value}
                                className={form.signature_method === value ? "selected" : ""}
                                onClick={() => updateForm("signature_method", value)}
                                disabled={rankUnavailable}
                                title={rankUnavailable ? rankScoring.reason : t.entry(`score.${value}`).does}
                              >
                                {label}
                              </button>
                              );
                            })}
                          </div>
                        </div>
                      )}
                      {!isCombinedMode && !isPanelMode && form.signature_method !== "single" && (
                        <SignatureInputSummary
                          method={form.signature_method}
                          value={effectiveGeneInput}
                        />
                      )}
                      {rankMethodUnavailable && (
                        <p className="signature-rank-unavailable" role="alert">
                          {rankScoring.reason}
                        </p>
                      )}
                    </>
                  )}

                  {activeAnalysisStep.id === "outcome" && (
                    <>
                      <PanelHeader iconRole="module.survivalEndpoint" title="Survival endpoint" helpId="survivalEndpoint" />
                      <EndpointSelector
                        endpoints={analysisEndpointOptions}
                        selected={form.endpoint}
                        onSelect={(value) => updateForm("endpoint", value)}
                      />
                      {analysisMetadataReady && <FieldHelp helpId="survivalEndpointCounts" />}
                    </>
                  )}

                  {activeAnalysisStep.id === "outcome" && (
                    <>
                      <PanelHeader
                        iconRole="module.stratification"
                        title="Expression & groups"
                        helpId={["expressionScale", "stratification"]}
                      />
                      <div className="analysis-step-subsection">
                        <LabelWithHelp
                          label={isPanelMode ? "Model boundary" : "Stratification"}
                          helpId={
                            isPanelMode
                              ? "panelModelBoundary"
                              : !isCombinedMode
                              ? ["stratification", `cutpoint.${form.cutpoint_method}`]
                              : form.combined_signature.grouping_method === "tertiles"
                                ? "combinedTertileCrossing"
                                : "combinedMedianCrossing"
                          }
                        />
                        {isPanelMode ? (
                          <div className="panel-model-boundary">
                            <TraceIcon role="data.trend" size="md" tone="accent" />
                            <div>
                              <strong>Continuous main effects only</strong>
                              <span>Estimate each signature on its own, then all signatures together. Add clinical adjustment when requested and supported by the data.</span>
                            </div>
                          </div>
                        ) : !isCombinedMode ? (
                          <div className="method-grid">
                            {CUTPOINTS.map((item) => (
                              <button
                                key={item.value}
                                type="button"
                                className={form.cutpoint_method === item.value ? "selected" : ""}
                                onClick={() => updateForm("cutpoint_method", item.value)}
                                title={t.entry(`cutpoint.${item.value}`).does}
                              >
                                <strong>{item.label}</strong>
                                <span>{t.caption(`cutpoint.${item.value}`)}</span>
                              </button>
                            ))}
                          </div>
                        ) : (
                          <div className="method-grid compact two">
                            {[
                              { value: "median", label: "Median x median", helpId: "combinedMedianCrossing" },
                              { value: "tertiles", label: "Tertiles x tertiles", helpId: "combinedTertileCrossing" },
                            ].map((item) => (
                              <button
                                key={item.value}
                                type="button"
                                className={form.combined_signature.grouping_method === item.value ? "selected" : ""}
                                onClick={() => updateCombinedGroupingMethod(item.value)}
                                title={t.entry(item.helpId).does}
                              >
                                <strong>{item.label}</strong>
                                <span>{t.caption(item.helpId)}</span>
                              </button>
                            ))}
                          </div>
                        )}
                        {!isCombinedMode && !isPanelMode && form.cutpoint_method === "percentile" && (
                          <label className="field">
                            <span>Percentile threshold</span>
                            <input
                              type="number"
                              min="1"
                              max="99"
                              value={form.custom_percentile}
                              onChange={(event) => updateForm("custom_percentile", event.target.value)}
                              aria-invalid={!percentileValidation.valid}
                              aria-describedby={!percentileValidation.valid ? "survival-percentile-error" : undefined}
                            />
                            <FieldHelp helpId="cutpoint.percentile" slot="all" />
                            {!percentileValidation.valid && (
                              <small id="survival-percentile-error" className="field-error" role="alert">
                                {percentileValidation.error}
                              </small>
                            )}
                          </label>
                        )}
                      </div>
                    </>
                  )}

                  {activeAnalysisStep.id === "clinical" && (
                    <>
                      <PanelHeader
                        iconRole="module.clinicalFilters"
                        title="Patient filters and adjustment"
                        description="Use filters to select patients. Use adjustment to account for clinical variables in an additional model."
                        helpId={["clinicalFilters", "clinicalAdjustment"]}
                      />
                      <details className="clinical-filter-disclosure">
                        <summary>
                          <span>
                            <strong>Eligibility filters</strong>
                            <small>Restrict who enters every model</small>
                          </span>
                          <b>{activeFilterCount ? `${activeFilterCount} active` : "Optional"}</b>
                        </summary>
                        <div className="clinical-filter-disclosure-body">
                          <div className="clinical-section-heading">
                            <strong>Patient and sample restrictions</strong>
                            <span>{activeFilterCount ? `${activeFilterCount} active` : "All eligible patients"}</span>
                          </div>
                      <FilterGroup
                        title="Sample type"
                        values={filters?.sample_types || []}
                        selected={form.filters.sample_types}
                        onToggle={(value) => toggleFilterValue("sample_types", value)}
                        onClear={() => clearFilter("sample_types")}
                      />
                      <FilterGroup
                        title="Stage"
                        values={filters?.stages || []}
                        selected={form.filters.stages}
                        onToggle={(value) => toggleFilterValue("stages", value)}
                        onClear={() => clearFilter("stages")}
                      />
                      <FilterGroup
                        title="Grade"
                        values={filters?.grades || []}
                        selected={form.filters.grades}
                        onToggle={(value) => toggleFilterValue("grades", value)}
                        onClear={() => clearFilter("grades")}
                        showWhenEmpty
                        emptyLabel="No grade metadata for this cohort"
                      />
                      <FilterGroup
                        title="Gender"
                        values={filters?.genders || []}
                        selected={form.filters.genders}
                        onToggle={(value) => toggleFilterValue("genders", value)}
                        onClear={() => clearFilter("genders")}
                      />
                      <FilterGroup
                        title="Race"
                        values={filters?.races || []}
                        selected={form.filters.races}
                        onToggle={(value) => toggleFilterValue("races", value)}
                        onClear={() => clearFilter("races")}
                      />
                      <div className="range-grid">
                        <label className="field">
                          <span>Min age</span>
                          <input
                            type="number"
                            min="0"
                            max="150"
                            step="any"
                            value={form.filters.age_min}
                            onChange={(event) => updateFilters("age_min", event.target.value)}
                            placeholder={filters?.age_min ? String(Math.floor(filters.age_min)) : ""}
                          />
                        </label>
                        <label className="field">
                          <span>Max age</span>
                          <input
                            type="number"
                            min="0"
                            max="150"
                            step="any"
                            value={form.filters.age_max}
                            onChange={(event) => updateFilters("age_max", event.target.value)}
                            placeholder={filters?.age_max ? String(Math.ceil(filters.age_max)) : ""}
                          />
                        </label>
                        <label className="field wide">
                          <span>Maximum follow-up days</span>
                          <input
                            type="number"
                            min="1"
                            step="any"
                            value={form.filters.max_time_days}
                            onChange={(event) => updateFilters("max_time_days", event.target.value)}
                            placeholder={filters?.os_time_max_days ? String(Math.ceil(filters.os_time_max_days)) : ""}
                          />
                          <FieldHelp helpId="maxFollowup" slot="all" />
                        </label>
                      </div>
                      {!analysisFiltersValidation.valid && (
                        <p className="field-error" role="alert">
                          {analysisFiltersValidation.errors[0]}
                        </p>
                      )}
                      <ClinicalFilterControls
                        variables={filters?.clinical_grouping_variables || []}
                        value={form.filters.custom_filters || []}
                        onChange={(value) => updateFilters("custom_filters", value)}
                        analysisContext="survival"
                      />
                        </div>
                      </details>
                      <ClinicalAdjustmentSelector
                        showDefaultAgeHint
                        selected={selectedAdjustmentCovariates}
                        filters={filters}
                        onToggle={toggleAdjustmentCovariate}
                        externalDataset={form.external_covariates}
                        externalSelected={selectedExternalAdjustmentCovariates}
                        onExternalChange={updateExternalAdjustment}
                      />
                    </>
                  )}

                  {activeAnalysisStep.id === "review" && (
                    <>
                      <PanelHeader
                        iconRole="module.plotOutput"
                        title="Review & run"
                        description="Confirm the analysis settings. Plot customization is optional."
                        helpId="plotOutput"
                      />
                      <details className="plot-editor-disclosure" open={survivalPlotEditorOpen} onToggle={(event) => setSurvivalPlotEditorOpen(event.currentTarget.open)}>
                        <summary>
                          <span>
                            <strong>Edit plots and exports</strong>
                            <small>Titles, colors, typography, axes and Cox layouts</small>
                          </span>
                          <TraceIcon role="action.configure" size="sm" />
                        </summary>
                        <PlotOutputControls
                          form={form}
                          updateForm={updateForm}
                          updatePlotStyle={updatePlotStyle}
                          updateArtifactPlotStyle={updateArtifactPlotStyle}
                          updatePaletteColor={updatePaletteColor}
                          plotEditorTarget={
                            isPanelMode
                              ? "cox_forest"
                              : isCombinedMode && plotEditorTarget === "continuous"
                                ? "cox_forest"
                                : plotEditorTarget
                          }
                          onPlotEditorTargetChange={setPlotEditorTarget}
                          supportsContinuous={!isCombinedMode && !isPanelMode}
                          supportsSurvival={!isPanelMode}
                          supportsCoxModelSelection={!isCombinedMode && !isPanelMode}
                          plotTitlePlaceholder={`${plotCancerName} overall survival`}
                        />
                      </details>
                    </>
                  )}
                </section>

                <DesignLedger
                  compact={activeAnalysisStep.id !== "review"}
                  key={activeAnalysisStep.id}
                  title="This analysis"
                  ledger={survivalLedger}
                  requirementsId="analysis-design-requirements"
                />

                <AnalysisStepActions
                  activeStep={analysisStep}
                  totalSteps={ANALYSIS_WORKFLOW_STEPS.length}
                  canContinue={analysisStepCompletion[analysisStep]}
                  requirement={analysisStepRequirements[analysisStep]}
                  loading={loading}
                  canRun={canRun}
                  onBack={() => navigateAnalysisStep(analysisStep - 1)}
                  onContinue={() => navigateAnalysisStep(analysisStep + 1)}
                  onRun={runAnalysis}
                />
              </section>

              <GuideAnchor
                anchor={GUIDE_ANCHORS.SURVIVAL_RESULTS}
                label="Survival analysis result"
                ref={resultPanelRef}
                className={`result-panel${!analysisResults.length && !loading ? " previewing" : ""}`}
              >
                {survivalResultsStale && (
                  <div className="survival-result-stale" role="status">
                    <strong>{t.entry(analysisResultFingerprint ? "survivalPreviousResult" : "survivalRecoveredResult").term}</strong>
                    <FieldHelp helpId={analysisResultFingerprint ? "survivalPreviousResult" : "survivalRecoveredResult"} />
                    <button type="button" onClick={() => navigateAnalysisStep(4)}>Review current settings</button>
                  </div>
                )}
                {error && (
                  <div className="error-box">
                    <TraceIcon role="status.error" size="md" tone="error" />
                    <div>
                      <strong>Analysis did not complete</strong>
                      <span>{error}</span>
                    </div>
                  </div>
                )}

                {!analysisResults.length && !loading && !error && (
                  <AnalysisSetupPreview
                    plotEditorOpen={survivalPlotEditorOpen}
                    activeStep={analysisStep}
                    step={activeAnalysisStep}
                    cohort={selectedCohort}
                    repositoryDataset={selectedRepositoryDataset}
                    dataSourceMode={dataSourceMode}
                    userDatasetUploadStep={userDatasetUploadStep}
                    form={form}
                    isCombinedMode={isCombinedMode}
                    isPanelMode={isPanelMode}
                    selectedGenes={selectedGenes}
                    signatureAGenes={selectedSignatureAGenes}
                    signatureBGenes={selectedSignatureBGenes}
                    panelSignatures={panelValidation.signatures}
                    endpoint={selectedEndpoint}
                    expressionScale={selectedExpressionScale}
                    cutpoint={previewCutpoint}
                    activeFilterCount={activeFilterCount}
                    plotEditorTarget={
                      isPanelMode
                        ? "cox_forest"
                        : isCombinedMode && plotEditorTarget === "continuous"
                          ? "cox_forest"
                          : plotEditorTarget
                    }
                    plotTitlePlaceholder={`${plotCancerName} overall survival`}
                  />
                )}

                {loading && (
                  <LoadingState
                    cohort={form.cohort}
                    gene={isPanelMode
                      ? form.signature_panel.name || `${effectivePanelSignatures.length} signatures`
                      : isCombinedMode
                        ? `${form.combined_signature.signature_a.name} x ${form.combined_signature.signature_b.name}`
                        : form.gene_symbol}
                    analysisKind={form.analysis_kind}
                    signatureMethod={form.signature_method}
                    geneCount={runCount}
                    completedCount={analysisResults.length}
                    endpoint={selectedEndpoint}
                    expressionScale={selectedExpressionScale}
                  />
                )}
                {!!analysisResults.length && <AnalysisResults analyses={analysisResults} onDownload={startDownload} />}
              </GuideAnchor>
            </div>
          </>
        ) : activePage === "compare" ? (
          <CompareAnalyses
            form={form}
            cohorts={cohorts}
            visibleCohorts={moduleVisibleCohorts}
            selectedCohort={selectedCohort}
            selectedCohortId={form.cohort}
            cohortQuery={cohortQuery}
            setCohortQuery={setCohortQuery}
            cohortPickerOpen={cohortPickerOpen}
            setCohortPickerOpen={setCohortPickerOpen}
            onSelectCohort={selectCohort}
            repositoryDatasets={selectableCohortDatasets}
            selectedRepositoryDataset={selectedRepositoryDataset}
            onSelectRepositoryDataset={selectRepositoryDataset}
            endpointOptions={analysisEndpointOptions}
            selectedEndpoint={selectedEndpoint}
            onSelectEndpoint={(value) => updateForm("endpoint", value)}
            updateForm={updateForm}
            updatePlotStyle={updatePlotStyle}
            updateArtifactPlotStyle={updateArtifactPlotStyle}
            updatePaletteColor={updatePaletteColor}
            plotEditorTarget={plotEditorTarget}
            onPlotEditorTargetChange={setPlotEditorTarget}
            expressionScales={analysisExpressionScales}
            expressionScaleValue={
              form.dataset_id
                ? form.expression_layer_id
                : form.expression_scale
            }
            onSelectExpressionScale={selectExpressionScale}
            filters={filters}
            activeFilterCount={activeFilterCount}
            updateFilters={updateFilters}
            toggleFilterValue={toggleFilterValue}
            clearFilter={clearFilter}
            compare={compare}
            setCompare={setCompare}
            cutpoints={CUTPOINTS}
            expressionScale={selectedExpressionScale}
            suggestionCohort={geneSuggestionCohort}
            canRun={Boolean(
              form.cohort
              && molecularPopulationReady && expressionLayerReady && analysisMetadataReady
              && selectedEndpoint.available
              && (!selectedRepositoryDataset
                || datasetSupportsModule(selectedRepositoryDataset, "compare"))
            )}
            metadataReady={analysisMetadataReady}
            metadataError={analysisMetadata.status === "error" && analysisMetadata.key === analysisMetadataKey ? analysisMetadata.error : ""}
            onRetryMetadata={() => setMetadataRetry((value) => value + 1)}
            dataRequirement={requiresDatasetSelection ? "Choose an analysis source."
              : selectedRepositoryDataset && !datasetSupportsModule(selectedRepositoryDataset, "compare")
                ? "This source does not support Compare. Choose another analysis source."
                : analysisStepRequirements[0]}
            onDownload={startDownload}
            tutorialStepId={
              tutorialController.tutorial?.module === "compare"
                && !["overview", "complete"].includes(tutorialController.state.lesson)
                ? tutorialController.step?.workspaceStepId
                : null
            }
          />
        ) : activePage === "expression" ? (
          <ExpressionComparisonModule
            state={expressionComparison}
            setState={setExpressionComparison}
            form={form}
            cohorts={cohorts}
            repositoryDatasets={repositoryDatasets}
            userDataset={userDataset}
            filters={filters}
            expressionScales={analysisExpressionScales}
            expressionScaleValue={
              form.dataset_id
                ? form.expression_layer_id
                : form.expression_scale
            }
            onSelectCohort={selectCohort}
            onSelectRepositoryDataset={selectRepositoryDataset}
            onSelectExpressionScale={selectExpressionScale}
            onSamplePopulationChange={(value) =>
              updateFilters("sample_population", value)
            }
            onClinicalFiltersChange={(value) => {
              updateFilters("custom_filters", value);
              invalidateExpressionComparisonContext();
            }}
            onClearEligibility={() => {
              setForm((current) => ({
                ...current,
                filters: {
                  ...EMPTY_FILTERS,
                  sample_population: current.filters.sample_population,
                },
              }));
              invalidateExpressionComparisonContext();
            }}
            recentAnalyses={[
              ...analysisResults,
              ...compare.results
                .map((item) => item.result)
                .filter(Boolean),
            ]}
            onDownload={startDownload}
          />
        ) : activePage === "gsea" ? (
          <GseaModule
            state={gsea}
            setState={setGsea}
            form={form}
            cohorts={cohorts}
            repositoryDatasets={repositoryDatasets}
            userDataset={userDataset}
            filters={filters}
            expressionScales={analysisExpressionScales}
            expressionScaleValue={
              form.dataset_id
                ? form.expression_layer_id
                : form.expression_scale
            }
            onSelectCohort={selectCohort}
            onSelectRepositoryDataset={selectRepositoryDataset}
            onSelectExpressionScale={selectExpressionScale}
            onSamplePopulationChange={(value) =>
              updateFilters("sample_population", value)
            }
            onClinicalFiltersChange={(value) =>
              updateFilters("custom_filters", value)
            }
            onClearEligibility={() =>
              setForm((current) => ({
                ...current,
                filters: {
                  ...EMPTY_FILTERS,
                  sample_population: current.filters.sample_population,
                },
              }))
            }
            recentAnalyses={[
              ...analysisResults,
              ...compare.results
                .map((item) => item.result)
                .filter(Boolean),
            ]}
            onDownload={startDownload}
          />
        ) : activePage === "multiverse" ? (
          <MultiverseAnalysis
            state={multiverse}
            setState={setMultiverse}
            form={form}
            cohorts={cohorts}
            visibleCohorts={moduleVisibleCohorts}
            selectedCohort={selectedCohort}
            cohortQuery={cohortQuery}
            setCohortQuery={setCohortQuery}
            cohortPickerOpen={cohortPickerOpen}
            setCohortPickerOpen={setCohortPickerOpen}
            onSelectCohort={selectCohort}
            repositoryDatasets={selectableCohortDatasets}
            selectedRepositoryDataset={selectedRepositoryDataset}
            onSelectRepositoryDataset={selectRepositoryDataset}
            endpointOptions={analysisEndpointOptions}
            expressionScales={analysisExpressionScales}
            expressionScaleValue={
              form.dataset_id
                ? form.expression_layer_id
                : form.expression_scale
            }
            onSelectExpressionScale={selectExpressionScale}
            filters={filters}
            activeFilterCount={activeFilterCount}
            updateForm={updateForm}
            updateFilters={updateFilters}
            toggleFilterValue={toggleFilterValue}
            clearFilter={clearFilter}
            suggestionCohort={geneSuggestionCohort}
            onDownload={startDownload}
            tutorialStepId={
              tutorialController.tutorial?.module === "multiverse"
                && !["overview", "complete"].includes(tutorialController.state.lesson)
                ? tutorialController.step?.workspaceStepId
                : null
            }
          />
        ) : activePage === "session" ? (
          <ExploratorySessionPage
            session={sessionHistory}
            exportState={sessionExport}
            setSession={setSessionHistory}
            setExportState={setSessionExport}
            onExport={exportExploratorySession}
            onDownload={startDownload}
          />
        ) : activePage === "pancancer" ? (
          <PanCancerSurvival
            state={panCancer}
            setState={setPanCancer}
            updateState={updatePanCancer}
            cohorts={cohorts}
            repositoryDatasets={repositoryDatasets}
            form={form}
            endpointOptions={endpointOptions}
            expressionScales={expressionScales}
            onDownload={startDownload}
            onPlotDownload={startPlotDownload}
          />
        ) : activePage === "examples" ? (
          <GuideAnchor anchor={GUIDE_ANCHORS.EXAMPLES_CATALOG} label="Guides and examples catalog">
            <TutorialLibrary
              controller={tutorialController}
            />
          </GuideAnchor>
        ) : activePage === "repository" ? (
          <RepositoryCatalog
            coverage={repositoryCoverage}
            datasets={repositoryDatasets}
            candidates={repositoryCandidates}
            candidatesStatus={repositoryCandidatesStatus}
            onOpenModule={openRepositoryDatasetModule}
            onDownload={startDownload}
          />
        ) : activePage === "summary" ? (
          <DatasetSummary
            summary={datasetSummary}
            health={health}
            dataSources={dataSources}
            repositoryDatasets={repositoryDatasets}
            cohorts={cohorts}
            summaryCohort={summaryCohort}
            setSummaryCohort={setSummaryCohort}
          />
        ) : activePage === "api" ? (
          <ApiMcpPage />
        ) : (
          <HelpMethodsPage />
        )}
          </div>
          </Suspense>
        </ModuleErrorBoundary>
        <TutorialDock
          controller={tutorialController}
          capabilities={tutorialCapabilities}
          triggerRef={tutorialTriggerRef}
          onNavigate={navigateTutorial}
          onApplyPreset={applyTutorialPreset}
        />
      </main>
      <DownloadNotifications notices={downloadNotices} onDismiss={dismissDownloadNotice} />
      </div>
    </>
  );
}

function HomePage({
  health,
  summary,
  cohorts,
  repositoryCoverage,
  serviceStatus,
  onNavigate,
  onUpload,
  onBrowseGuides,
}) {
  const totals = aggregateCohortCoverage(cohorts, {
    ...(summary?.totals || {}),
    cohorts: summary?.totals?.cohorts,
  });
  const externalCoverage = {
    ...(health?.external_repository || {}),
    ...(repositoryCoverage || {}),
  };
  const externalDatasetCount = externalCoverage.datasets;
  const publicCoverage = aggregatePublicCatalogCoverage(
    totals,
    externalCoverage,
  );
  const coverageState = publicCoverageState(publicCoverage, serviceStatus);
  const coverageValue = (key) => coverageState === "ready"
    ? formatInteger(publicCoverage[key])
    : coverageState === "unavailable" ? "Unavailable" : "...";
  const externalCoverageDescription = Number.isFinite(externalDatasetCount)
    ? `Browse ${formatInteger(externalDatasetCount)} curated bulk RNA-seq ${externalDatasetCount === 1 ? "release" : "releases"} and see which analyses each supports.`
    : "Browse curated bulk RNA-seq studies and see which analyses each supports.";
  const [homeQuestion, setHomeQuestion] = useState(null);
  const assetBase = import.meta.env.BASE_URL;
  const workspaceGroups = [
    {
      id: "analyze",
      label: "Analyze",
      modules: [
        {
          page: "analysis",
          iconRole: "navigation.analysis",
          title: "Analyze survival",
          description: "Relate a gene or signature to survival, with clinical adjustment and model checks.",
        },
        {
          page: "compare",
          iconRole: "navigation.compare",
          title: "Compare markers and cutpoints",
          description: "Compare survival results for different markers and ways of defining high and low expression.",
        },
        {
          page: "expression",
          iconRole: "navigation.expressionComparison",
          title: "Compare gene expression",
          description: "Compare up to 25 genes across patient groups, with statistical tests, violin plots, boxplots and a heatmap.",
        },
        {
          page: "gsea",
          iconRole: "navigation.gsea",
          title: "Compare pathways",
          description: "Compare biological pathways between two patient groups, with effect direction and statistical support.",
        },
        {
          page: "multiverse",
          iconRole: "navigation.multiverse",
          title: "Check analysis choices",
          description: "Check whether your findings change with different analysis choices.",
        },
        {
          page: "pancancer",
          iconRole: "navigation.panCancer",
          title: "Analyze across cancer types",
          description: "Follow a gene or signature across studies and cancer types, keeping differences between them visible.",
        },
      ],
    },
    {
      id: "evidence",
      label: "Evidence",
      description: "Review your analyses and the data behind them.",
      modules: [
        {
          page: "session",
          iconRole: "navigation.session",
          title: "Review past analyses",
          description: "Review analyses recorded in this browser and export selected runs together.",
        },
        {
          page: "repository",
          iconRole: "navigation.repository",
          title: "Find an external cohort",
          description: externalCoverageDescription,
        },
        {
          page: "summary",
          iconRole: "navigation.dataset",
          title: "Inspect the TCGA dataset",
          description: "See which patients, samples, survival outcomes and clinical information are available in TCGA.",
        },
      ],
    },
    {
      id: "learn",
      label: "Learn & connect",
      description: "Find guidance, methods and ways to connect.",
      modules: [
        {
          page: "examples",
          iconRole: "navigation.examples",
          title: "Follow a guide",
          description: "Follow each analysis step and learn how to interpret the results.",
        },
        {
          page: "api",
          iconRole: "navigation.api",
          title: "Use the API or MCP",
          description: "Explore TRACE data and run analyses from your code, Claude or ChatGPT.",
        },
        {
          page: "help",
          iconRole: "navigation.methods",
          title: "Read the methods",
          description: "Read how analyses work, their assumptions and limitations, with references and method versions.",
        },
      ],
    },
  ];

  return (
    <GuideAnchor
      as="div"
      anchor={GUIDE_ANCHORS.HOME_INTERPRETATION}
      label="How to interpret the TRACE Explorer home workspace"
      className="home-page home-reorganized"
    >
      <GuideAnchor
        anchor={GUIDE_ANCHORS.HOME_OVERVIEW}
        labelledBy="home-title"
        className="home-hero"
      >
        <div className="home-hero-inner">
          <div className="home-hero-trace" aria-hidden="true">
            <svg viewBox="0 0 600 300" preserveAspectRatio="xMidYMid meet" focusable="false">
              <path
                pathLength="1"
                d="M 14 48 H 112 V 96 H 220 V 135 H 324 V 195 H 432 V 230 H 586"
              />
            </svg>
          </div>
          <div className="home-hero-copy">
            <p className="home-kicker">Transcriptomic Research Across Cohorts and Endpoints</p>
            <div className="home-title-lockup"><TraceLogo animated /><h1 id="home-title">TRACE Explorer</h1></div>
            <p className="home-lede">Study survival, gene expression and pathways in public cohorts or your own data.</p>
          </div>
        </div>


      </GuideAnchor>

      <div className="home-start-layout">
        <GuideAnchor
          anchor={GUIDE_ANCHORS.HOME_WORKSPACE}
          labelledBy="home-workspace-title"
          className="home-workspace-index"
        >
          <header className="home-section-heading">
            <h2 id="home-workspace-title" tabIndex={-1}>What do you want to investigate?</h2>
          </header>
          <div className="home-question-choices" aria-label="Research question">
            {[
              ["survival", "Survival", "navigation.analysis", "How does expression relate to survival?"],
              ["molecular", "Molecular differences", "navigation.expressionComparison", "Compare genes or pathways between groups"],
              ["studies", "Across studies", "navigation.panCancer", "Does a finding hold in another cohort?"],
            ].map(([id, title, icon, description]) => <div key={id} className="home-question-item">
              <button type="button"
                aria-pressed={homeQuestion === id} aria-expanded={homeQuestion === id}
                aria-controls={homeQuestion === id ? "home-route-options" : undefined}
                onClick={() => setHomeQuestion(homeQuestion === id ? null : id)}>
                <ModuleIcon role={icon} frame="section" />
                <span><strong>{title}</strong><small>{description}</small></span>
                <TraceIcon role="action.next" size="sm" />
              </button>
              {homeQuestion === id && <section id="home-route-options" className="home-question-next" aria-label="Choose your analysis">
                <h3>{homeQuestion === "survival" ? "How do you want to study survival?" : homeQuestion === "molecular" ? "What do you want to compare?" : "Where do you want to look?"}</h3>
                <div className="home-next-options">
                {workspaceGroups[0].modules.filter((module) => (
                  homeQuestion === "survival" ? ["analysis", "compare", "multiverse"].includes(module.page)
                    : homeQuestion === "molecular" ? ["expression", "gsea"].includes(module.page)
                    : module.page === "pancancer"
                )).concat(homeQuestion === "studies" ? [workspaceGroups[1].modules[1]] : []).map((module) => (
                  <button type="button" key={module.page} onClick={() => onNavigate(module.page)}
                    aria-label={module.title} aria-describedby={`home-route-${module.page}-description`}
                    onPointerEnter={() => preloadPageModule(module.page)} onFocus={() => preloadPageModule(module.page)}>
                    <span><strong>{module.title}</strong><small id={`home-route-${module.page}-description`}>{module.description}</small></span><TraceIcon role="action.next" size="sm" />
                  </button>
                ))}
                </div>
              </section>}
            </div>)}
          </div>
        </GuideAnchor>
        <div className="home-assistance">
          <aside className="home-video-intro" aria-label={GUIDE_VIDEO_COPY.homeTitle}>
            <div>
              <ModuleIcon role="navigation.examples" frame="section" />
              <h2>{GUIDE_VIDEO_COPY.homeTitle}</h2>
              <p>{GUIDE_VIDEO_COPY.homeDescription}</p>
            </div>
            <div className="home-video-actions">
              <button type="button" onClick={onBrowseGuides}>{GUIDE_VIDEO_COPY.browse}<TraceIcon role="action.next" size="sm" /></button>
            </div>
          </aside>
          <div className="home-upload-entry">
            <button type="button" onClick={onUpload}>Use your own data<TraceIcon role="action.next" size="sm" /></button>
          </div>
          <nav className="home-secondary-links" aria-label="Other ways to use TRACE">
            {[workspaceGroups[1].modules[0], workspaceGroups[2].modules[1]].map((module) =>
              <button type="button" key={module.page} onClick={() => onNavigate(module.page)}>{module.title}<TraceIcon role="action.next" size="sm" /></button>)}
          </nav>
        </div>
      </div>


      <section className="home-coverage" aria-labelledby="home-coverage-title">
        <header className="home-coverage-heading">
          <h2 id="home-coverage-title">Available public data</h2>
          <p>TCGA and curated external cohorts</p>
        </header>
        <dl
          className="home-data-strip"
          aria-label="Current public data coverage"
          aria-busy={coverageState === "loading"}
          data-state={coverageState}
        >
          <div>
            <dt>Cancer types represented</dt>
            <dd>{coverageValue("cancerTypes")}</dd>
          </div>
          <div>
            <dt>Public cohort releases</dt>
            <dd>{coverageValue("cohortReleases")}</dd>
          </div>
          <div>
            <dt>Patient records across releases</dt>
            <dd>{coverageValue("patientRecords")}</dd>
          </div>
          <div>
            <dt>RNA profiles across releases</dt>
            <dd>{coverageValue("rnaProfiles")}</dd>
          </div>
        </dl>
      </section>

      <DesktopDownloads />

      <GuideAnchor
        anchor={GUIDE_ANCHORS.HOME_FOUNDATION}
        label="Analysis records and institutions"
        className="home-foundation"
      >
        <div className="home-institutions">
          <p className="eyebrow">Institutions</p>
          <div className="home-logo-row">
            <div className="home-combined-logo">
              <img
                src={`${assetBase}institutions/uss-cienciavida.png`}
                alt="Universidad San Sebastián and Fundación Ciencia & Vida"
                loading="lazy"
                decoding="async"
                width="720"
                height="180"
              />
              <a
                href="https://www.uss.cl/"
                target="_blank"
                rel="noopener noreferrer"
                className="home-logo-link is-uss"
              >
                <span className="sr-only">Universidad San Sebastián</span>
              </a>
              <a
                href="https://cienciavida.org/"
                target="_blank"
                rel="noopener noreferrer"
                className="home-logo-link is-cienciavida"
              >
                <span className="sr-only">Fundación Ciencia & Vida</span>
              </a>
            </div>
          </div>
        </div>
      </GuideAnchor>
    </GuideAnchor>
  );
}

const USER_EXPRESSION_UNIT_OPTIONS = [
  ["log2_tpm", "log2(TPM + 1)", "Already transformed"],
  ["tpm", "TPM", "Convert to log2(TPM + 1)"],
  ["log2_fpkm", "log2(FPKM + 1)", "Already transformed"],
  ["fpkm", "FPKM", "Convert to log2(FPKM + 1)"],
  ["log2_fpkm_uq", "log2(FPKM-UQ + 1)", "Already transformed"],
  ["fpkm_uq", "FPKM-UQ", "Convert to log2(FPKM-UQ + 1)"],
  ["log2_cpm", "log2(CPM + 1)", "Already transformed"],
  ["cpm", "CPM", "Convert to log2(CPM + 1)"],
  ["counts", "Raw counts", "Convert to log2(CPM + 1), 5,000+ genes"],
  ["normalized_log2", "Other normalized log scale", "Analyze as provided"],
  ["normalized_continuous", "Other normalized continuous scale", "Analyze as provided"],
];

const USER_ENDPOINT_OPTIONS = [
  ["OS", "Overall survival"],
  ["DSS", "Disease-specific survival"],
  ["PFI", "Progression-free interval"],
  ["DFI", "Disease-free interval"],
];

const USER_COVARIATE_FIELDS = [
  ["age_at_index", "Age"],
  ["stage", "Stage"],
  ["grade", "Grade"],
  ["gender", "Gender or sex"],
  ["race", "Race or ethnicity"],
];

function UserDatasetUpload({
  cancerTypes,
  currentDataset,
  selected,
  onStepChange,
  onDirtyChange,
  onReady,
  onSelect,
  onDelete,
  onNavigate,
}) {
  const t = useHelpText();
  const [step, setStep] = useState(0);
  const [files, setFiles] = useState({
    expression: null,
    clinical: null,
  });
  const [inspection, setInspection] = useState(null);
  const [mapping, setMapping] = useState({
    name: "",
    cancer_code: "",
    expression_orientation: "genes_by_rows",
    expression_id_column: "",
    clinical_id_column: "",
    has_survival_outcome: true,
    time_column: "",
    event_column: "",
    event_value: "",
    censored_value: "",
    time_unit: "days",
    endpoint: "OS",
    expression_unit: "",
    covariates: {
      stage: null,
      grade: null,
      age_at_index: null,
      gender: null,
      race: null,
    },
    custom_clinical_variables: [],
    confirm_deidentified: false,
  });
  const [busy, setBusy] = useState(false);
  const [busyPhase, setBusyPhase] = useState("");
  const [error, setError] = useState("");
  const [deleteState, setDeleteState] = useState("idle");

  useEffect(() => {
    if (currentDataset) {
      setStep(2);
      setDeleteState("idle");
    }
  }, [currentDataset?.id]);

  useEffect(() => {
    onStepChange(step);
  }, [onStepChange, step]);

  const dirty = Boolean(
    !currentDataset
    && (
      files.expression
      || files.clinical
      || mapping.name
      || mapping.cancer_code
      || step > 0
    )
  );

  useEffect(() => {
    onDirtyChange?.(dirty);
  }, [dirty, onDirtyChange]);

  useEffect(() => {
    if (!dirty || typeof window === "undefined") return undefined;
    const warnBeforeUnload = (event) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", warnBeforeUnload);
    return () => window.removeEventListener("beforeunload", warnBeforeUnload);
  }, [dirty]);

  function setFile(kind, file) {
    if (file) {
      const supported = /\.(csv|tsv|txt)$/i.test(file.name || "");
      const maximum = kind === "expression"
        ? USER_EXPRESSION_MAX_BYTES
        : USER_CLINICAL_MAX_BYTES;
      if (!supported) {
        setError(`${kind === "expression" ? "Expression" : "Patient metadata"} file must be CSV, TSV or TXT.`);
        return;
      }
      if (file.size > maximum) {
        setError(
          `${kind === "expression" ? "Expression" : "Patient metadata"} file is ${humanFileSize(file.size)}. The limit is ${humanFileSize(maximum)}.`,
        );
        return;
      }
    }
    setFiles((current) => ({ ...current, [kind]: file || null }));
    setInspection(null);
    setStep(0);
    setError("");
  }

  async function inspectFiles() {
    if (!files.expression || !files.clinical || !mapping.name || !mapping.cancer_code) {
      setError("Name the dataset, choose its cancer context and add both files.");
      return;
    }
    setBusy(true);
    setBusyPhase("reading");
    setError("");
    try {
      const nextInspection = await inspectUserDatasetFiles(
        files.expression,
        files.clinical,
      );
      const suggestions = nextInspection.suggestions;
      const eventPair = defaultEventMapping(suggestions.event_values);
      setInspection(nextInspection);
      setMapping((current) => ({
        ...current,
        ...suggestions,
        name: current.name,
        cancer_code: current.cancer_code,
        event_value: eventPair.event,
        censored_value: eventPair.censored,
        covariates: suggestions.covariates,
        custom_clinical_variables: [],
        confirm_deidentified: false,
      }));
      setStep(1);
    } catch (inspectionError) {
      setError(formatError(inspectionError));
    } finally {
      setBusy(false);
      setBusyPhase("");
    }
  }

  function updateMapping(key, value) {
    setMapping((current) => ({ ...current, [key]: value }));
    setError("");
  }

  function updateEventColumn(value) {
    const values = eventValuesForColumn(inspection, value);
    const pair = defaultEventMapping(values);
    setMapping((current) => ({
      ...current,
      event_column: value,
      event_value: pair.event,
      censored_value: pair.censored,
    }));
    setError("");
  }

  function updateCovariate(key, value) {
    setMapping((current) => ({
      ...current,
      covariates: {
        ...current.covariates,
        [key]: value || null,
      },
      custom_clinical_variables: (current.custom_clinical_variables || []).filter(
        (variable) => variable.source_column !== value,
      ),
    }));
  }

  function addCustomClinicalVariable() {
    setMapping((current) => {
      const candidates = customClinicalCandidates(inspection, current);
      const profile = candidates[0];
      if (!profile || (current.custom_clinical_variables || []).length >= 10) return current;
      const variable = createCustomClinicalVariable(profile.column, profile);
      const usedIds = new Set(
        (current.custom_clinical_variables || []).map((item) => item.id.toLowerCase()),
      );
      let id = variable.id;
      let suffix = 2;
      while (usedIds.has(id.toLowerCase())) {
        id = `${variable.id.slice(0, 60)}_${suffix}`;
        suffix += 1;
      }
      return {
        ...current,
        custom_clinical_variables: [
          ...(current.custom_clinical_variables || []),
          { ...variable, id },
        ],
      };
    });
    setError("");
  }

  function updateCustomClinicalVariable(index, key, value) {
    setMapping((current) => ({
      ...current,
      custom_clinical_variables: (current.custom_clinical_variables || []).map(
        (variable, variableIndex) => variableIndex === index
          ? { ...variable, [key]: value }
          : variable,
      ),
    }));
    setError("");
  }

  function removeCustomClinicalVariable(index) {
    setMapping((current) => ({
      ...current,
      custom_clinical_variables: (current.custom_clinical_variables || []).filter(
        (_, variableIndex) => variableIndex !== index,
      ),
    }));
    setError("");
  }

  const observedEventValues = eventValuesForColumn(
    inspection,
    mapping.event_column,
  );
  const customVariableCandidates = customClinicalCandidates(inspection, mapping);
  const customMappingErrors = validateCustomClinicalVariables(
    mapping.custom_clinical_variables || [],
    inspection,
    mapping,
  );
  const preliminaryMatches =
    mapping.expression_orientation === "genes_by_rows"
      ? inspection?.matching.genesByRowsMatches || 0
      : inspection?.matching.samplesByRowsMatches || 0;
  const requiredClinicalColumns = [
    mapping.clinical_id_column,
    ...(mapping.has_survival_outcome
      ? [mapping.time_column, mapping.event_column]
      : []),
  ].filter(Boolean).map((value) => String(value).trim().toLowerCase());
  const requiredClinicalColumnsDistinct =
    requiredClinicalColumns.length === (mapping.has_survival_outcome ? 3 : 1)
    && new Set(requiredClinicalColumns).size === requiredClinicalColumns.length;
  const eventMappingDistinct = !mapping.has_survival_outcome || Boolean(
      mapping.event_value
      && mapping.censored_value
      && String(mapping.event_value).trim().toLowerCase()
        !== String(mapping.censored_value).trim().toLowerCase()
    );
  const mappingReady = Boolean(
    mapping.expression_id_column
      && mapping.clinical_id_column
      && (!mapping.has_survival_outcome || (
        mapping.time_column
        && mapping.event_column
        && mapping.event_value
        && mapping.censored_value
      ))
      && requiredClinicalColumnsDistinct
      && eventMappingDistinct
      && mapping.expression_unit
      && (!mapping.has_survival_outcome || observedEventValues.length === 2)
      && customMappingErrors.length === 0
      && mapping.confirm_deidentified,
  );

  async function importDataset() {
    if (!mappingReady) {
      setError("Complete the required mappings and privacy confirmation.");
      return;
    }
    setBusy(true);
    setBusyPhase("validating");
    setError("");
    try {
      const dataset = await createUserDataset(
        files.expression,
        files.clinical,
        mapping,
      );
      onReady(dataset);
      setStep(2);
    } catch (uploadError) {
      const details = uploadError.details || {};
      const counts = details.thresholds
        ? ` Matched: ${details.matched_patients || 0} patients, ${details.events || 0} events and ${details.censored || 0} censored.`
        : "";
      setError(`${formatError(uploadError)}${counts}`);
    } finally {
      setBusy(false);
      setBusyPhase("");
    }
  }

  async function confirmDelete() {
    setDeleteState("deleting");
    setError("");
    try {
      await onDelete();
      setFiles({ expression: null, clinical: null });
      setInspection(null);
      setMapping((current) => ({
        ...current,
        name: "",
        cancer_code: "",
        custom_clinical_variables: [],
        confirm_deidentified: false,
      }));
      setStep(0);
      setDeleteState("idle");
    } catch (deleteError) {
      setDeleteState("idle");
      setError(formatError(deleteError));
    }
  }

  if (currentDataset && step === 2) {
    const notices = currentDataset.qc?.notices || [];
    const customClinicalVariables = currentDataset.qc?.custom_clinical?.variables || [];
    return (
      <section className="user-dataset-ready" aria-labelledby="user-dataset-ready-title">
        <div className="user-dataset-ready-heading">
          <TraceIcon role="status.success" size="md" tone="success" />
          <div>
            <span>Private dataset ready</span>
            <strong id="user-dataset-ready-title">{currentDataset.name}</strong>
          </div>
        </div>
        <dl>
          <div>
            <dt>Matched patients</dt>
            <dd>{formatInteger(currentDataset.patient_count)}</dd>
          </div>
          <div>
            <dt>Survival</dt>
            <dd>{currentDataset.capabilities?.survival?.available ? "Available" : "Not available"}</dd>
          </div>
          <div>
            <dt>Genes</dt>
            <dd>{formatInteger(currentDataset.gene_count)}</dd>
          </div>
          <div>
            <dt>Retention</dt>
            <dd>{currentDataset.expires_at ? formatDateTime(currentDataset.expires_at) : "Until you delete it"}</dd>
          </div>
        </dl>
        <div className="user-dataset-ready-meta">
          <span>{currentDataset.endpoint?.label || "No time-to-event outcome"}</span>
          <span>{currentDataset.expression_layer?.label}</span>
          <span>Original files deleted after validation</span>
        </div>
        <div className="user-dataset-capabilities" aria-label="Available analyses">
          <span><strong>Expression</strong> available</span>
          <span>
            <strong>GSEA</strong>{" "}
            {currentDataset.capabilities?.gsea?.available
              ? "available"
              : currentDataset.capabilities?.gsea?.reason || "not available"}
          </span>
          <span>
            <strong>Survival</strong>{" "}
            {currentDataset.capabilities?.survival?.available
              ? `${formatInteger(currentDataset.capabilities.survival.patient_count)} patients · ${formatInteger(currentDataset.capabilities.survival.event_count)} events`
              : currentDataset.capabilities?.survival?.reason || "No usable outcome"}
          </span>
        </div>
        {customClinicalVariables.length > 0 && (
          <section className="custom-clinical-ready" aria-labelledby="custom-clinical-ready-title">
            <header>
              <strong id="custom-clinical-ready-title">Custom clinical metadata</strong>
              <span>{customClinicalVariables.length} / 10 variables · no automatic Cox adjustment</span>
            </header>
            <div className="custom-clinical-ready-list">
              {customClinicalVariables.map((variable) => (
                <div key={variable.id}>
                  <span>
                    <strong>{variable.label}</strong>
                    <small>{variable.value_type} · {String(variable.timing || "unknown").replaceAll("_", " ")}</small>
                  </span>
                  <span>
                    {formatInteger(variable.non_missing_count)} observed
                    {variable.value_type === "categorical"
                      ? ` · ${formatInteger(variable.observed_levels?.length || 0)} levels`
                      : variable.min != null && variable.max != null
                        ? ` · ${formatCompactNumber(variable.min)}–${formatCompactNumber(variable.max)}`
                        : ""}
                  </span>
                  <span className={variable.analysis_eligible ? "is-eligible" : "is-ineligible"}>
                    {variable.analysis_eligible ? "Grouping eligible" : "Descriptive only"}
                  </span>
                </div>
              ))}
            </div>
          </section>
        )}
        {notices.length > 0 && (
          <div className="upload-notice-list">
            {notices.map((notice) => (
              <p key={notice.code}>
                <TraceIcon role="status.info" size="sm" tone="secondary" />
                {notice.message}
              </p>
            ))}
          </div>
        )}
        <div className="user-dataset-ready-actions">
          {!selected && (
            <button type="button" className="primary-button" onClick={onSelect}>
              <TraceIcon role="action.run" size="sm" />
              {currentDataset.capabilities?.survival?.available
                ? "Use in this analysis"
                : "Use for molecular analyses"}
            </button>
          )}
          {selected && (
            <span className="selected-dataset-indicator">
              <TraceIcon role="status.success" size="sm" tone="success" />
              Selected for analysis
            </span>
          )}
          {selected && (
            <>
              <button type="button" className="secondary-button" onClick={() => onNavigate?.("expression")}>
                Open Expression
              </button>
              {currentDataset.capabilities?.gsea?.available && (
                <button type="button" className="secondary-button" onClick={() => onNavigate?.("gsea")}>
                  Open GSEA
                </button>
              )}
            </>
          )}
          {deleteState === "confirm" ? (
            <span className="delete-confirmation">
              <span>Delete data and generated private results?</span>
              <button type="button" onClick={confirmDelete}>Delete</button>
              <button type="button" onClick={() => setDeleteState("idle")}>Keep</button>
            </span>
          ) : (
            <button
              type="button"
              className="text-button danger-action"
              disabled={deleteState === "deleting"}
              onClick={() => setDeleteState("confirm")}
            >
              {deleteState === "deleting" ? "Deleting…" : "Delete private data"}
            </button>
          )}
        </div>
        {error && <UploadError message={error} />}
      </section>
    );
  }

  return (
    <section
      className="user-dataset-upload"
      aria-labelledby="user-upload-title"
      aria-busy={busy}
      data-busy-phase={busyPhase || undefined}
    >
      <header className="user-upload-heading">
        <div>
          <span className="eyebrow">Private workspace</span>
          <h3 id="user-upload-title">Add expression and patient metadata</h3>
        </div>
        <a href={getUserDatasetTemplateUrl()} className="text-link">
          <TraceIcon role="action.download" size="sm" />
          Download template
        </a>
      </header>
      <ol className="upload-progress" aria-label="Upload progress">
        {[
          ["1", "Files"],
          ["2", "Map columns"],
          ["3", "Ready"],
        ].map(([number, label], index) => (
          <li
            key={number}
            data-state={index < step ? "complete" : index === step ? "current" : "pending"}
            aria-current={index === step ? "step" : undefined}
          >
            <span>{index < step ? "✓" : number}</span>
            {label}
          </li>
        ))}
      </ol>

      {step === 0 && (
        <div className="upload-files-step">
          <div className="upload-context-grid">
            <label>
              <span>Dataset name</span>
              <input
                value={mapping.name}
                maxLength={100}
                onChange={(event) => updateMapping("name", event.target.value)}
                placeholder="Example: Institutional lung cohort"
              />
            </label>
            <label>
              <span>Cancer context</span>
              <select
                value={mapping.cancer_code}
                onChange={(event) => updateMapping("cancer_code", event.target.value)}
              >
                <option value="">Choose cancer type</option>
                {cancerTypes.map((cancer) => (
                  <option key={cancer.code} value={cancer.code}>
                    {cancer.name} ({cancer.code})
                  </option>
                ))}
              </select>
            </label>
          </div>
          <div className="upload-file-grid">
            <UploadFileField
              id="user-expression-file"
              guideAnchor={GUIDE_ANCHORS.SURVIVAL_UPLOAD_EXPRESSION}
              guideLabel="Expression file upload"
              title="Expression table"
              description="CSV or TSV. Genes may be rows or columns."
              file={files.expression}
              onFile={(file) => setFile("expression", file)}
            />
            <UploadFileField
              id="user-clinical-file"
              guideAnchor={GUIDE_ANCHORS.SURVIVAL_UPLOAD_OUTCOME}
              guideLabel="Patient metadata file upload"
              title="Patient metadata"
              description="One row per patient. Survival columns are optional."
              file={files.clinical}
              onFile={(file) => setFile("clinical", file)}
            />
          </div>
          <div className="privacy-inline">
            <TraceIcon role="status.info" size="sm" tone="secondary" />
            <span>
              Upload de-identified research data only. Original files are discarded
              after validation. {isLocalDesktop() ? "Your data and results stay on this computer until you delete them." : "Normalized data and results expire after 24 hours."}
            </span>
            <HelpButton label="private dataset retention" helpId="userDataset" />
          </div>
          <div className="upload-step-actions">
            <span>Sample IDs must match exactly between both files.</span>
            <button
              type="button"
              className="primary-button"
              disabled={busy || !files.expression || !files.clinical}
              onClick={inspectFiles}
            >
              {busy ? (
                <TraceIcon role="status.loading" size="sm" />
              ) : (
                <TraceIcon role="action.next" size="sm" />
              )}
              {busyPhase === "reading" ? "Reading both files…" : "Map columns"}
            </button>
          </div>
        </div>
      )}

      {step === 1 && inspection && (
        <div className="upload-mapping-step">
          <div className="mapping-detection-summary">
            <TraceIcon role="status.success" size="sm" tone="success" />
            <span>
              Detected {inspection.expression.headers.length} expression columns,
              {" "}{inspection.clinical.rowCount} metadata rows and approximately
              {" "}{preliminaryMatches} matching identifiers.
            </span>
          </div>
          <GuideAnchor
            as="fieldset"
            anchor={GUIDE_ANCHORS.SURVIVAL_UPLOAD_EXPRESSION}
            label="Expression layout and identifier mapping"
            className="mapping-orientation"
          >
            <legend>Expression layout</legend>
            {[
              ["genes_by_rows", "Genes in rows", "Sample IDs are column headers"],
              ["samples_by_rows", "Samples in rows", "Gene symbols are column headers"],
            ].map(([value, label, detail]) => (
              <button
                key={value}
                type="button"
                className={mapping.expression_orientation === value ? "selected" : ""}
                aria-pressed={mapping.expression_orientation === value}
                onClick={() => updateMapping("expression_orientation", value)}
              >
                <strong>{label}</strong>
                <span>{detail}</span>
              </button>
            ))}
            <MappingSelect
              label={
                mapping.expression_orientation === "genes_by_rows"
                  ? "Gene symbol column"
                  : "Expression sample ID"
              }
              value={mapping.expression_id_column}
              options={inspection.expression.headers}
              onChange={(value) => updateMapping("expression_id_column", value)}
            />
            <FieldWithHelp label="Expression scale in the file" htmlFor="upload-expression-scale" helpId="expressionUploadScale">
              <select
                id="upload-expression-scale"
                value={mapping.expression_unit}
                onChange={(event) => updateMapping("expression_unit", event.target.value)}
              >
                <option value="" disabled>Choose the scale in your file</option>
                {USER_EXPRESSION_UNIT_OPTIONS.map(([value, label, detail]) => (
                  <option key={value} value={value}>{label}: {detail}</option>
                ))}
              </select>
            </FieldWithHelp>
          </GuideAnchor>
          <GuideAnchor
            as="fieldset"
            anchor={GUIDE_ANCHORS.SURVIVAL_UPLOAD_OUTCOME}
            label="Patient identifier and optional survival outcome mapping"
            className="mapping-grid mapping-outcome-contract"
          >
            <legend>Patient linkage and outcome</legend>
            <MappingSelect
              label="Patient ID"
              value={mapping.clinical_id_column}
              options={inspection.clinical.headers}
              onChange={(value) => updateMapping("clinical_id_column", value)}
            />
            <label className="mapping-wide custom-clinical-checkbox">
              <input
                type="checkbox"
                checked={Boolean(mapping.has_survival_outcome)}
                onChange={(event) => updateMapping("has_survival_outcome", event.target.checked)}
              />
              <span>This file includes a time-to-event outcome</span>
            </label>
            {mapping.has_survival_outcome ? (
              <>
                <MappingSelect
                  label="Survival time"
                  value={mapping.time_column}
                  options={inspection.clinical.headers}
                  onChange={(value) => updateMapping("time_column", value)}
                />
                <MappingSelect
                  label="Event status"
                  value={mapping.event_column}
                  options={inspection.clinical.headers}
                  onChange={updateEventColumn}
                />
                <MappingSelect
                  label="Value meaning event"
                  value={mapping.event_value}
                  options={observedEventValues}
                  onChange={(value) => updateMapping("event_value", value)}
                />
                <MappingSelect
                  label="Value meaning censored"
                  value={mapping.censored_value}
                  options={observedEventValues}
                  onChange={(value) => updateMapping("censored_value", value)}
                />
                <label>
                  <span>Survival time unit</span>
                  <select
                    value={mapping.time_unit}
                    onChange={(event) => updateMapping("time_unit", event.target.value)}
                  >
                    <option value="days">Days</option>
                    <option value="months">Months</option>
                    <option value="years">Years</option>
                  </select>
                </label>
                <label>
                  <span>Endpoint</span>
                  <select
                    value={mapping.endpoint}
                    onChange={(event) => updateMapping("endpoint", event.target.value)}
                  >
                    {USER_ENDPOINT_OPTIONS.map(([value, label]) => (
                      <option key={value} value={value}>{label}</option>
                    ))}
                  </select>
                </label>
              </>
            ) : (
              <p className="mapping-wide plot-control-note">
                Expression comparison remains available. GSEA is enabled for matrices with at least 100 genes and is checked again for rankable genes when run. Survival modules will stay unavailable for this upload.
              </p>
            )}
          </GuideAnchor>
          {mapping.has_survival_outcome && observedEventValues.length !== 2 && (
            <div className="mapping-blocker">
              <TraceIcon role="status.error" size="sm" tone="error" />
              The event column must contain exactly two non-missing values. Found
              {" "}{observedEventValues.length}: {observedEventValues.join(", ") || "none"}.
            </div>
          )}
          {mapping.has_survival_outcome && !requiredClinicalColumnsDistinct && (
            <div className="mapping-blocker">
              <TraceIcon role="status.error" size="sm" tone="error" />
              Clinical sample ID, survival time and event status must use three distinct columns.
            </div>
          )}
          <details className="optional-column-mapping">
            <summary>Standard patient variables</summary>
            <p>
              Mapping these columns enables patient filters and, when survival is
              available, clinically adjusted Cox models.
            </p>
            <div className="mapping-grid">
              {USER_COVARIATE_FIELDS.map(([key, label]) => (
                <MappingSelect
                  key={key}
                  label={label}
                  value={mapping.covariates[key] || ""}
                  options={inspection.clinical.headers}
                  allowEmpty
                  onChange={(value) => updateCovariate(key, value)}
                />
              ))}
            </div>
          </details>
          <GuideAnchor
            anchor={GUIDE_ANCHORS.SURVIVAL_UPLOAD_METADATA}
            labelledBy="custom-clinical-title"
            className="custom-clinical-mapping"
          >
            <header>
              <div>
                <span className="eyebrow">Dataset-specific metadata</span>
                <h4 id="custom-clinical-title">Custom clinical variables</h4>
                <p>
                  Map up to 10 additional categorical or numeric fields for filters,
                  Expression and GSEA. These fields are never added automatically to Cox models.
                </p>
              </div>
              <button
                type="button"
                className="secondary-button"
                disabled={
                  (mapping.custom_clinical_variables || []).length >= 10
                  || customVariableCandidates.length === 0
                }
                onClick={addCustomClinicalVariable}
              >
                <TraceIcon role="action.configure" size="sm" />
                Add variable
              </button>
            </header>
            {(mapping.custom_clinical_variables || []).length === 0 ? (
              <div className="custom-clinical-empty">
                <TraceIcon role="status.info" size="sm" tone="secondary" />
                <span>
                  Optional. Declare when each field was measured; only baseline or
                  pre-treatment fields are eligible for Survival filters.
                </span>
              </div>
            ) : (
              <div className="custom-clinical-list">
                {(mapping.custom_clinical_variables || []).map((variable, index) => {
                  const profile = inspection.clinical.columnProfiles?.find(
                    (item) => item.column === variable.source_column,
                  );
                  const sourceOptions = [
                    profile,
                    ...customVariableCandidates,
                  ].filter(Boolean).filter(
                    (item, itemIndex, items) => items.findIndex(
                      (candidate) => candidate.column === item.column,
                    ) === itemIndex,
                  );
                  const errorLabel = variable.label || `Custom variable ${index + 1}`;
                  const variableErrors = customMappingErrors.filter((message) =>
                    message.startsWith(`${errorLabel}:`)
                    || message.startsWith(`Custom variable ${index + 1}:`),
                  );
                  const variableErrorId = `custom-clinical-variable-${index}-errors`;
                  return (
                    <article className="custom-clinical-variable" key={index}>
                      <div className="custom-clinical-variable-heading">
                        <strong>{variable.label || `Variable ${index + 1}`}</strong>
                        <span>
                          {formatInteger(profile?.nonMissingCount || 0)} observed · {formatInteger(profile?.uniqueCount || 0)} unique
                        </span>
                        <button
                          type="button"
                          className="text-button"
                          onClick={() => removeCustomClinicalVariable(index)}
                        >
                          Remove
                        </button>
                      </div>
                      <div className="custom-clinical-grid">
                        <label>
                          <span>Source column</span>
                          <select
                            value={variable.source_column}
                            aria-invalid={variableErrors.length > 0 || undefined}
                            aria-describedby={variableErrors.length ? variableErrorId : undefined}
                            onChange={(event) => {
                              const source = event.target.value;
                              const nextProfile = inspection.clinical.columnProfiles?.find(
                                (item) => item.column === source,
                              );
                              updateCustomClinicalVariable(index, "source_column", source);
                              if (nextProfile) {
                                updateCustomClinicalVariable(index, "value_type", nextProfile.inferredValueType);
                              }
                            }}
                          >
                            {sourceOptions.map((item) => (
                              <option key={item.column} value={item.column}>{item.column}</option>
                            ))}
                          </select>
                        </label>
                        <label>
                          <span>Analysis ID</span>
                          <input
                            value={variable.id}
                            maxLength={64}
                            aria-invalid={variableErrors.length > 0 || undefined}
                            aria-describedby={variableErrors.length ? variableErrorId : undefined}
                            onChange={(event) => updateCustomClinicalVariable(index, "id", event.target.value)}
                          />
                        </label>
                        <label>
                          <span>Display label</span>
                          <input
                            value={variable.label}
                            maxLength={100}
                            aria-invalid={variableErrors.length > 0 || undefined}
                            aria-describedby={variableErrors.length ? variableErrorId : undefined}
                            onChange={(event) => updateCustomClinicalVariable(index, "label", event.target.value)}
                          />
                        </label>
                        <label>
                          <span>Value type</span>
                          <select
                            value={variable.value_type}
                            aria-invalid={variableErrors.length > 0 || undefined}
                            aria-describedby={variableErrors.length ? variableErrorId : undefined}
                            onChange={(event) => updateCustomClinicalVariable(index, "value_type", event.target.value)}
                          >
                            <option value="categorical">Categorical</option>
                            <option value="numeric">Numeric</option>
                          </select>
                        </label>
                        <label>
                          <span>Measurement timing</span>
                          <select
                            value={variable.timing}
                            aria-invalid={variableErrors.length > 0 || undefined}
                            aria-describedby={variableErrors.length ? variableErrorId : undefined}
                            onChange={(event) => updateCustomClinicalVariable(index, "timing", event.target.value)}
                          >
                            <option value="unknown">Choose timing</option>
                            <option value="baseline">Baseline</option>
                            <option value="pre_treatment">Pre-treatment</option>
                            <option value="on_treatment">On treatment</option>
                            <option value="post_treatment">Post-treatment</option>
                            <option value="post_baseline">Other post-baseline</option>
                            <option value="outcome">Outcome or response</option>
                          </select>
                        </label>
                        <label>
                          <span>Unit (optional)</span>
                          <input
                            value={variable.unit || ""}
                            maxLength={64}
                            aria-invalid={variableErrors.length > 0 || undefined}
                            aria-describedby={variableErrors.length ? variableErrorId : undefined}
                            placeholder={variable.value_type === "numeric" ? "Example: score units" : "Not required"}
                            onChange={(event) => updateCustomClinicalVariable(index, "unit", event.target.value)}
                          />
                        </label>
                        <label className="custom-clinical-description">
                          <span>Description (optional)</span>
                          <input
                            value={variable.description || ""}
                            maxLength={500}
                            aria-invalid={variableErrors.length > 0 || undefined}
                            aria-describedby={variableErrors.length ? variableErrorId : undefined}
                            onChange={(event) => updateCustomClinicalVariable(index, "description", event.target.value)}
                          />
                        </label>
                        <label className="custom-clinical-checkbox">
                          <input
                            type="checkbox"
                            checked={Boolean(variable.expression_derived)}
                            aria-describedby={variableErrors.length ? variableErrorId : undefined}
                            onChange={(event) => updateCustomClinicalVariable(index, "expression_derived", event.target.checked)}
                          />
                          <span>Derived from gene expression (exploratory/circular warning)</span>
                        </label>
                      </div>
                      {variableErrors.length > 0 && (
                        <span className="sr-only" id={variableErrorId}>
                          {variableErrors.join(" ")}
                        </span>
                      )}
                      {variable.value_type === "categorical" && profile?.categoricalLevelLimitExceeded && (
                        <p className="custom-clinical-variable-error">
                          This column has {formatInteger(profile.uniqueCount)} levels; categorical metadata is limited to 30.
                        </p>
                      )}
                      {["unknown", "on_treatment", "post_treatment", "post_baseline", "outcome"].includes(variable.timing) && (
                        <p className="custom-clinical-variable-caution">
                          {variable.timing === "unknown"
                            ? "Timing is unknown: retained for descriptive grouping, but not eligible for Survival filtering."
                            : "Retained for descriptive Expression/GSEA grouping, but not eligible for baseline Survival filtering."}
                        </p>
                      )}
                    </article>
                  );
                })}
              </div>
            )}
            {customMappingErrors.length > 0 && (
              <div className="custom-clinical-errors" role="alert">
                <TraceIcon role="status.caution" size="sm" tone="caution" />
                <ul>
                  {customMappingErrors.map((message) => <li key={message}>{message}</li>)}
                </ul>
              </div>
            )}
          </GuideAnchor>
          <label className="deidentified-confirmation">
            <input
              type="checkbox"
              checked={mapping.confirm_deidentified}
              onChange={(event) =>
                updateMapping("confirm_deidentified", event.target.checked)
              }
            />
            <span>
              I confirm these files contain de-identified research data and no
              names, emails, addresses or direct personal identifiers.
            </span>
          </label>
          <div className="upload-step-actions">
            <button
              type="button"
              className="secondary-button"
              disabled={busy}
              onClick={() => setStep(0)}
            >
              <TraceIcon role="action.back" size="sm" />
              Back
            </button>
            <button
              type="button"
              className="primary-button"
              disabled={busy || !mappingReady}
              onClick={importDataset}
            >
              {busy ? (
                <TraceIcon role="status.loading" size="sm" />
              ) : (
                <TraceIcon role="status.success" size="sm" />
              )}
              {busyPhase === "validating" ? "Validating and preparing…" : "Validate and use dataset"}
            </button>
          </div>
        </div>
      )}
      {error && <UploadError message={error} />}
    </section>
  );
}

function UploadFileField({
  id,
  guideAnchor,
  guideLabel,
  title,
  description,
  file,
  onFile,
}) {
  const inputRef = useRef(null);
  const [dragging, setDragging] = useState(false);

  function acceptFileList(fileList) {
    const nextFile = fileList?.[0] || null;
    if (nextFile) onFile(nextFile);
  }

  return (
    <GuideAnchor
      as="div"
      anchor={guideAnchor}
      label={guideLabel}
      className={`upload-file-field${dragging ? " is-dragging" : ""}${file ? " has-file" : ""}`}
      onDragEnter={(event) => {
        event.preventDefault();
        setDragging(true);
      }}
      onDragOver={(event) => event.preventDefault()}
      onDragLeave={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget)) setDragging(false);
      }}
      onDrop={(event) => {
        event.preventDefault();
        setDragging(false);
        acceptFileList(event.dataTransfer.files);
      }}
    >
      <input
        ref={inputRef}
        id={id}
        type="file"
        accept=".csv,.tsv,.txt,text/csv,text/tab-separated-values"
        onChange={(event) => acceptFileList(event.target.files)}
      />
      <TraceIcon role={file ? "status.success" : "file.csv"} size="lg" tone={file ? "success" : "accent"} />
      <div>
        <strong title={file ? file.name : title}>{file ? file.name : title}</strong>
        <span title={file ? humanFileSize(file.size) : description}>
          {file ? humanFileSize(file.size) : description}
        </span>
      </div>
      <button type="button" onClick={() => inputRef.current?.click()}>
        {file ? "Replace" : "Choose file"}
      </button>
    </GuideAnchor>
  );
}

function MappingSelect({
  label,
  value,
  options,
  onChange,
  allowEmpty = false,
}) {
  return (
    <label>
      <span>{label}</span>
      <select value={value} onChange={(event) => onChange(event.target.value)}>
        {(allowEmpty || !value) && <option value="">Not mapped</option>}
        {options.map((option) => (
          <option key={option} value={option}>{option}</option>
        ))}
      </select>
    </label>
  );
}

function UploadError({ message }) {
  return (
    <div className="upload-error" role="alert">
      <TraceIcon role="status.error" size="sm" tone="error" />
      <span>{message}</span>
    </div>
  );
}

function TraceLogo({ animated = false }) {
  return (
    <span className={`brand-mark${animated ? " is-acquiring" : ""}`} aria-hidden="true">
      <img
        src={`${import.meta.env.BASE_URL}brand/trace-mark.svg`}
        alt=""
        draggable="false"
      />
    </span>
  );
}

function SummaryStat({ label, value }) {
  return (
    <div>
      <span>{label}</span>
      <strong>{formatInteger(value)}</strong>
    </div>
  );
}

function CohortPicker({
  visibleCohorts,
  selectedCohort,
  selectedCohortId,
  query,
  setQuery,
  open,
  setOpen,
  onSelect,
}) {
  const pickerRef = useRef(null);
  const triggerRef = useRef(null);
  const searchInputRef = useRef(null);
  const selectedLabel = selectedCohort ? getCohortName(selectedCohort.id) : "Choose cancer cohort";
  const countLabel = cohortPickerCountLabel(visibleCohorts.length, query);

  useEffect(() => {
    if (!open) return;
    const frame = window.requestAnimationFrame(() => searchInputRef.current?.focus());
    return () => window.cancelAnimationFrame(frame);
  }, [open]);

  useEffect(() => {
    if (!open) return;
    function closeOnOutsidePointer(event) {
      if (!pickerRef.current?.contains(event.target)) setOpen(false);
    }
    document.addEventListener("pointerdown", closeOnOutsidePointer);
    return () => document.removeEventListener("pointerdown", closeOnOutsidePointer);
  }, [open, setOpen]);

  return (
    <div ref={pickerRef} className="cohort-picker">
      <button
        ref={triggerRef}
        type="button"
        className={`cohort-trigger${open ? " open" : ""}`}
        onClick={() => setOpen((current) => !current)}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls="cohort-picker-list"
      >
        <span>
          <strong>{selectedLabel}</strong>
          <small>
            {selectedCohort
              ? `${selectedCohort.id} / ${formatInteger(selectedCohort.n_patients_paired)} patients`
              : countLabel}
          </small>
        </span>
        <TraceIcon role="action.expand" size="md" />
      </button>

      <div
        className="cohort-menu"
        data-open={open ? "true" : "false"}
        aria-hidden={!open}
        inert={!open}
        onKeyDown={(event) => {
          if (event.key !== "Escape") return;
          setOpen(false);
          window.requestAnimationFrame(() => triggerRef.current?.focus());
        }}
      >
          <label className="cohort-search">
            <TraceIcon role="action.search" size="sm" />
            <input
              ref={searchInputRef}
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              aria-label="Search cancer cohorts"
              placeholder="Search cancer name, cohort code or site"
            />
          </label>
          <div className="cohort-count">
            {countLabel}
          </div>
          <div id="cohort-picker-list" className="cohort-browser" role="listbox" aria-label="Available cancer cohorts">
            {visibleCohorts.map((cohort) => (
              <button
                key={cohort.id}
                type="button"
                role="option"
                aria-selected={selectedCohortId === cohort.id}
                className={selectedCohortId === cohort.id ? "selected" : ""}
                onClick={() => onSelect(cohort.id)}
              >
                <strong>{getCohortName(cohort.id)}</strong>
                <span>{cohort.id} / {formatInteger(cohort.n_patients_paired)} patients</span>
              </button>
            ))}
            {!visibleCohorts.length && (
              <div className="no-cohorts">
                No cohorts match this search.
              </div>
            )}
          </div>
      </div>
    </div>
  );
}

function RepositorySourceSelector({
  selectedCohort,
  datasets,
  selectedDataset,
  onSelect,
  analysisType = "analysis",
  compact = false,
}) {
  const [expanded, setExpanded] = useState(false);
  const [query, setQuery] = useState("");
  const changeSourceRef = useRef(null);
  const optionsId = useId();
  if (!selectedCohort) return null;
  const externalOnly = selectedCohort.status === "external_only";
  const compatibleDatasets = filterDatasetsForModule(datasets, analysisType);
  const selectedCapability = selectedDataset
    ? datasetCapability(selectedDataset, analysisType)
    : null;
  const selectedIsIncompatible = Boolean(
    selectedDataset && !selectedCapability?.available,
  );
  const analysisLabel = moduleAnalysisLabel(analysisType);
  const showAlternatives = !compact || expanded || (externalOnly && !selectedDataset);
  const visibleDatasets = compatibleDatasets.filter((dataset) => (
    selectedDataset?.id === dataset.id
    || (showAlternatives && [dataset.name, dataset.source_accession, dataset.id, dataset.release_version]
      .join(" ").toLowerCase().includes(query.trim().toLowerCase()))
  ));
  function chooseSource(id) {
    if ((selectedDataset?.id || null) !== id) onSelect(id);
    if (compact) {
      setExpanded(false);
      setQuery("");
      window.requestAnimationFrame(() => changeSourceRef.current?.focus({ preventScroll: true }));
    }
  }
  return (
    <section className="repository-source-selector" aria-labelledby="analysis-source-label">
      <div className="repository-source-heading">
        <span id="analysis-source-label">Analysis source</span>
        <strong>
          {selectedIsIncompatible
            ? `Unavailable for ${analysisLabel}`
            : selectedDataset
            ? "Independent cohort"
            : externalOnly
              ? "External cohort"
              : "TCGA"}
        </strong>
      </div>
      {compact && (compatibleDatasets.length > 0 || selectedDataset) && (
        <button className="repository-source-toggle" type="button" ref={changeSourceRef}
          aria-expanded={showAlternatives} aria-controls={optionsId}
          onClick={() => { setExpanded(!expanded); setQuery(""); }}>
          {showAlternatives ? "Close source list" : "Change analysis source"}
        </button>
      )}
      {compact && showAlternatives && (
        <label className="field repository-source-search">
          <span>Find a source</span>
          <input type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Study name or accession" />
        </label>
      )}
      <div id={optionsId} className="repository-source-options" role="radiogroup" aria-label="Analysis dataset">
        {!externalOnly && (!selectedDataset || showAlternatives) && (
          <button
            type="button"
            role="radio"
            aria-checked={!selectedDataset}
            className={!selectedDataset ? "selected" : ""}
            onClick={() => chooseSource(null)}
          >
            <span className="repository-source-code">TCGA</span>
            <strong>{getCohortName(selectedCohort.id)}</strong>
            <small>
              {formatInteger(selectedCohort.n_patients_paired)} linked patients
            </small>
          </button>
        )}
        {selectedIsIncompatible && (
          <button
            type="button"
            role="radio"
            aria-checked="true"
            className="selected is-incompatible"
            disabled
          >
            <span className="repository-source-code">{selectedDataset.source_accession || "Selected source"}</span>
            <strong>{selectedDataset.name}</strong>
            <small>{selectedCapability.reason}</small>
          </button>
        )}
        {visibleDatasets.map((dataset) => (
          <button
            key={dataset.id}
            type="button"
            role="radio"
            aria-checked={selectedDataset?.id === dataset.id}
            className={selectedDataset?.id === dataset.id ? "selected" : ""}
            onClick={() => chooseSource(dataset.id)}
          >
            <span className="repository-source-code">
              {dataset.kind === "user"
                ? "Private dataset"
                : dataset.source_accession}
            </span>
            <strong>{dataset.name}</strong>
            <small>
              {formatInteger(dataset.patient_count)} patients
              {!compact && dataset.release_version ? ` · ${dataset.release_version}` : ""}
            </small>
            <small>
              {dataset.expression_layer?.label || "Expression layer documented in release"}
            </small>
          </button>
        ))}
      </div>
      {compact && showAlternatives && query && !visibleDatasets.some((dataset) => dataset.id !== selectedDataset?.id) && (
        <p role="status">No other sources match this search.</p>
      )}
      {compact && selectedDataset && (
        <details className="repository-source-details">
          <summary>Selected source details</summary>
          <dl>
            <dt>Dataset</dt><dd>{selectedDataset.id}</dd>
            <dt>Release</dt><dd>{selectedDataset.release_version || selectedDataset.active_release_id || "Not reported"}</dd>
            <dt>Source default expression</dt><dd>{selectedDataset.expression_layer?.label || "See Expression data below"}</dd>
          </dl>
        </details>
      )}
      {selectedIsIncompatible && (
        <p className="repository-source-compatibility" role="status">
          <TraceIcon role="status.info" size="sm" tone="secondary" />
          <span>
            {selectedDataset.name} remains selected, but cannot run {analysisLabel}.
            Choose another source below; your gene and model settings are unchanged.
          </span>
        </p>
      )}
      {!compatibleDatasets.length && !selectedIsIncompatible && (
        <p className="repository-source-gap">
          {externalOnly
            ? `No curated external cohort is ready for ${analysisLabel} in this cancer context.`
            : `No curated independent cohort is ready for ${analysisLabel} in this cancer yet.`}
        </p>
      )}
    </section>
  );
}

function FilterGroup({ title, values, selected, onToggle, onClear, showWhenEmpty = false, emptyLabel = "No values available" }) {
  if (!values.length && !showWhenEmpty) return null;
  return (
    <div className="filter-group">
      <div className="filter-title">
        <span>{title}</span>
        {!!selected.length && (
          <button type="button" onClick={onClear}>
            Clear
          </button>
        )}
      </div>
      <div>
        {values.length ? (
          values.slice(0, 14).map((value) => (
            <button
              key={value}
              type="button"
              className={selected.includes(value) ? "selected" : ""}
              onClick={() => onToggle(value)}
            >
              {value}
            </button>
          ))
        ) : (
          <span className="filter-empty">{emptyLabel}</span>
        )}
      </div>
    </div>
  );
}

function CohortAdjustmentNotice({ filters }) {
  const t = useHelpText();
  if (!filters || CLINICAL_ADJUSTMENT_OPTIONS.some((option) => clinicalCovariateAvailable(option, filters))) return null;
  return <div className="cohort-adjustment-notice" role="status">
    <strong>{t.entry("clinicalAdjustmentUnavailable").term}</strong>
    <p>{t.entry("clinicalAdjustmentUnavailable").does}</p>
  </div>;
}

function ClinicalAdjustmentSelector({
  selected,
  filters,
  onToggle,
  externalDataset = null,
  externalSelected = [],
  onExternalChange = () => {},
  showDefaultAgeHint = false,
}) {
  const totalSelected = selected.length + externalSelected.length;
  return (
    <section className="clinical-adjustment-selector" aria-label="Cox clinical adjustment">
      <div className="clinical-section-heading">
        <div>
          <LabelWithHelp label="Cox adjustment" helpId="clinicalAdjustment" />
          <small>
            An additional Cox model uses the checked fields and includes only patients with complete values.
          </small>
        </div>
        <strong>{totalSelected ? `${totalSelected} selected` : "Unadjusted only"}</strong>
      </div>
      <div className="clinical-adjustment-grid">
        {CLINICAL_ADJUSTMENT_OPTIONS.map((option) => {
          const available = clinicalCovariateAvailable(option, filters);
          const checked = selected.includes(option.value);
          return (
            <label
              key={option.value}
              className={checked ? "clinical-adjustment-option selected" : "clinical-adjustment-option"}
              data-unavailable={!available ? "true" : "false"}
            >
              <input
                type="checkbox"
                checked={checked}
                disabled={!available && !checked}
                onChange={() => onToggle(option.value)}
              />
              <span aria-hidden="true">
                {checked && <TraceIcon role="status.success" size="sm" />}
              </span>
              <strong>{option.label}</strong>
              <small>{available ? option.detail : "Not available in this cohort"}</small>
            </label>
          );
        })}
      </div>
      {showDefaultAgeHint && clinicalCovariateAvailable(CLINICAL_ADJUSTMENT_OPTIONS.find((item) => item.value === "age_at_index"), filters) && (
        <FieldHelp helpId="survivalAgeDefault" />
      )}
      <ExternalCovariateEditor
        dataset={externalDataset}
        selected={externalSelected}
        onChange={onExternalChange}
      />
      <p>
        Patients with missing covariates are excluded from the adjusted model. Each model reports its patient count, events, fitted parameters and events per parameter (EPV).
      </p>
    </section>
  );
}

function ExternalCovariateEditor({ dataset, selected, onChange }) {
  const inputId = useId();
  const [error, setError] = useState("");
  const [open, setOpen] = useState(Boolean(dataset));

  useEffect(() => {
    if (dataset) setOpen(true);
  }, [dataset]);

  async function handleFile(event) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    if (file.size > MAX_EXTERNAL_COVARIATE_FILE_BYTES) {
      setError("The CSV is larger than 2 MB.");
      return;
    }
    try {
      const parsed = parseExternalCovariateCsv(await file.text(), file.name);
      onChange(parsed, []);
      setError("");
      setOpen(true);
    } catch (uploadError) {
      setError(uploadError.message || "The CSV could not be read.");
    }
  }

  function updateDataset(nextDataset) {
    onChange(nextDataset, selected);
  }

  function toggleExternal(name) {
    onChange(dataset, toggleListValue(selected, name));
  }

  function updateDefinition(name, patch) {
    updateDataset(updateExternalCovariateDefinition(dataset, name, patch));
  }

  function changeType(name, valueType) {
    try {
      updateDataset(changeExternalCovariateType(dataset, name, valueType));
      setError("");
    } catch (typeError) {
      setError(typeError.message);
    }
  }

  return (
    <details
      className="external-covariate-editor"
      open={open}
      onToggle={(event) => setOpen(event.currentTarget.open)}
    >
      <summary>
        <span>
          <TraceIcon role="file.csv" size="sm" />
          <strong>External covariates</strong>
        </span>
        <small>
          {dataset
            ? `${dataset.rows.length} patients · ${dataset.definitions.length} variables · ${selected.length} selected`
            : "Optional patient-level CSV"}
        </small>
      </summary>
      <div className="external-covariate-body">
        <div className="external-covariate-privacy" role="note">
          <TraceIcon role="status.caution" size="sm" tone="caution" />
          <p>
            Use public TCGA participant barcodes only. Uploaded values become part of the analysis request and audit export. Do not upload names, local identifiers or protected clinical data.
          </p>
        </div>
        <div className="external-covariate-toolbar">
          <div>
            <strong>CSV requirements</strong>
            <span><code>patient_id</code> plus 1–10 covariate columns, maximum 2,000 rows.</span>
          </div>
          <label className="external-file-button" htmlFor={inputId}>
            <TraceIcon role="file.csv" size="sm" />
            <span>{dataset ? "Replace CSV" : "Choose CSV"}</span>
          </label>
          <input
            id={inputId}
            className="sr-only"
            type="file"
            accept=".csv,text/csv"
            onChange={handleFile}
          />
          {dataset && (
            <button
              type="button"
              className="external-remove-button"
              onClick={() => {
                onChange(null, []);
                setError("");
              }}
            >
              <TraceIcon role="action.close" size="sm" />
              <span>Remove</span>
            </button>
          )}
        </div>
        {error && (
          <div className="external-covariate-error" role="alert">
            <TraceIcon role="status.error" size="sm" tone="error" />
            <span>{error}</span>
          </div>
        )}
        {dataset && (
          <>
            <label className="field external-source-label">
              <span>Dataset label</span>
              <input
                value={dataset.source_label || ""}
                maxLength="120"
                onChange={(event) =>
                  updateDataset({
                    ...dataset,
                    source_label: event.target.value,
                  })
                }
              />
            </label>
            <div
              className="external-covariate-list"
              aria-label="External covariate definitions"
            >
              {dataset.definitions.map((definition) => (
                <ExternalCovariateDefinitionRow
                  key={definition.name}
                  definition={definition}
                  dataset={dataset}
                  selected={selected.includes(definition.name)}
                  onToggle={() => toggleExternal(definition.name)}
                  onDefinitionChange={(patch) =>
                    updateDefinition(definition.name, patch)
                  }
                  onTypeChange={(valueType) =>
                    changeType(definition.name, valueType)
                  }
                  onLevelOrderChange={(level, nextIndex) =>
                    updateDataset(
                      reorderExternalCovariateLevel(
                        dataset,
                        definition.name,
                        level,
                        nextIndex,
                      ),
                    )
                  }
                />
              ))}
            </div>
          </>
        )}
      </div>
    </details>
  );
}

function ExternalCovariateDefinitionRow({
  definition,
  dataset,
  selected,
  onToggle,
  onDefinitionChange,
  onTypeChange,
  onLevelOrderChange,
}) {
  const typeOptions = externalCovariateTypeOptions(dataset, definition.name);
  const nonMissing = dataset.rows.filter(
    (row) => row.values[definition.name] !== null
      && row.values[definition.name] !== undefined,
  ).length;
  const missing = dataset.rows.length - nonMissing;
  return (
    <section
      className={`external-covariate-definition${selected ? " selected" : ""}`}
      aria-label={definition.label}
    >
      <div className="external-definition-heading">
        <label className="external-variable-toggle">
          <input type="checkbox" checked={selected} onChange={onToggle} />
          <span aria-hidden="true">
            {selected && <TraceIcon role="status.success" size="sm" />}
          </span>
          <span>
            <strong>{definition.label}</strong>
            <code>{definition.name}</code>
          </span>
        </label>
        <small>{nonMissing} complete · {missing} missing</small>
      </div>
      <div className="external-definition-fields">
        <label className="field">
          <span>Display label</span>
          <input
            value={definition.label}
            maxLength="80"
            onChange={(event) => {
              if (event.target.value.trim()) {
                onDefinitionChange({ label: event.target.value });
              }
            }}
          />
        </label>
        <label className="field">
          <span>Model type</span>
          <select
            value={definition.value_type}
            onChange={(event) => onTypeChange(event.target.value)}
          >
            {typeOptions.map((value) => (
              <option key={value} value={value}>{formatLabel(value)}</option>
            ))}
          </select>
        </label>
        {definition.value_type === "continuous" && (
          <>
            <label className="field">
              <span>Effect unit</span>
              <input
                type="number"
                min="0.000000001"
                max="1000000000000"
                step="any"
                value={definition.effect_unit}
                onChange={(event) => {
                  const value = Number(event.target.value);
                  if (Number.isFinite(value) && value > 0 && value <= 1e12) {
                    onDefinitionChange({ effect_unit: value });
                  }
                }}
              />
            </label>
            <label className="field">
              <span>Unit label</span>
              <input
                value={definition.unit || ""}
                maxLength="80"
                placeholder="e.g. proportion"
                onChange={(event) =>
                  onDefinitionChange({ unit: event.target.value })
                }
              />
            </label>
          </>
        )}
        {definition.value_type === "categorical" && (
          <label className="field external-reference-field">
            <span>Reference level</span>
            <select
              value={definition.reference_level || ""}
              onChange={(event) =>
                onDefinitionChange({ reference_level: event.target.value })
              }
            >
              {definition.levels.map((level) => (
                <option key={level} value={level}>{level}</option>
              ))}
            </select>
          </label>
        )}
      </div>
      {definition.value_type === "ordinal" && (
        <div className="external-level-order">
          <span>Ordered levels, low to high</span>
          <div>
            {definition.levels.map((level, index) => (
              <label key={level}>
                <span>{level}</span>
                <select
                  aria-label={`Order for ${level}`}
                  value={index}
                  onChange={(event) =>
                    onLevelOrderChange(level, Number(event.target.value))
                  }
                >
                  {definition.levels.map((_, optionIndex) => (
                    <option key={optionIndex} value={optionIndex}>
                      {optionIndex + 1}
                    </option>
                  ))}
                </select>
              </label>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}

function SwitchField({ label, checked, onChange }) {
  return (
    <label className="switch-field">
      <input type="checkbox" checked={checked} onChange={(event) => onChange(event.target.checked)} />
      <span aria-hidden="true" />
      <strong>{label}</strong>
    </label>
  );
}

function PlotTextStyleField({
  label,
  description,
  size,
  minimum,
  maximum,
  bold,
  italic,
  onSizeChange,
  onBoldChange,
  onItalicChange,
}) {
  const labelId = useId();
  return (
    <div className="plot-text-style-field" role="group" aria-labelledby={labelId}>
      <div className="plot-text-style-copy">
        <strong id={labelId}>{label}</strong>
        <span>{description}</span>
      </div>
      <label className="plot-text-size">
        <span>Size</span>
        <input
          type="number"
          min={minimum}
          max={maximum}
          value={size}
          onChange={(event) => onSizeChange(event.target.value)}
        />
      </label>
      <div className="plot-text-style-buttons" aria-label={`${label} emphasis`}>
        <button
          type="button"
          className={bold ? "selected" : ""}
          aria-pressed={bold}
          aria-label={`Bold ${label.toLowerCase()}`}
          title="Bold"
          onClick={() => onBoldChange(!bold)}
        >
          <span aria-hidden="true" className="plot-style-bold">B</span>
        </button>
        <button
          type="button"
          className={italic ? "selected" : ""}
          aria-pressed={italic}
          aria-label={`Italic ${label.toLowerCase()}`}
          title="Italic"
          onClick={() => onItalicChange(!italic)}
        >
          <span aria-hidden="true" className="plot-style-italic">I</span>
        </button>
      </div>
    </div>
  );
}

function PlotFrameField({ value, onChange }) {
  const labelId = useId();
  const options = [
    {
      value: "open",
      label: "Open",
      description: "No boundary",
    },
    {
      value: "axes",
      label: "L axes",
      description: "Left and bottom",
    },
    {
      value: "box",
      label: "Box",
      description: "Full boundary",
    },
  ];
  return (
    <div className="plot-frame-field" role="group" aria-labelledby={labelId}>
      <div className="plot-frame-copy">
        <strong id={labelId}>Plot frame</strong>
        <span>Choose the boundary around the data panel.</span>
      </div>
      <div className="plot-frame-options">
        {options.map((option) => (
          <button
            key={option.value}
            type="button"
            className={value === option.value ? "selected" : ""}
            aria-pressed={value === option.value}
            aria-label={`${option.label}: ${option.description}`}
            onClick={() => onChange(option.value)}
          >
            <span
              aria-hidden="true"
              className={`plot-frame-swatch ${option.value}`}
            />
            <span>
              <strong>{option.label}</strong>
              <small>{option.description}</small>
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}

function ColorField({ label, value, onChange }) {
  return (
    <label className="color-field">
      <span>{label}</span>
      <div>
        <input type="color" value={value} onChange={(event) => onChange(event.target.value)} />
        <strong>{value.toUpperCase()}</strong>
      </div>
    </label>
  );
}

function EndpointSelector({ endpoints, selected, onSelect }) {
  const t = useHelpText();
  return (
    <div className="endpoint-grid" aria-label="Survival endpoint">
      {endpoints.map((item) => (
        <button
          key={item.value}
          type="button"
          className={selected === item.value ? "selected" : ""}
          onClick={() => item.available && onSelect(item.value)}
          disabled={!item.available}
          title={[
            item.reason,
            ["DSS", "DFI", "PFI"].includes(item.value)
              ? t("competingRisk")
              : null,
          ].filter(Boolean).join(" ")}
        >
          <strong>{item.label}</strong>
          <span>
            {item.available
              ? `${formatInteger(item.patients)} patients / ${formatInteger(item.events)} events`
              : item.reason}
          </span>
          <small>{formatSourceLabel(item.source)}</small>
        </button>
      ))}
    </div>
  );
}

function GeneSelector({
  id,
  label,
  value,
  onChange,
  draft,
  setDraft,
  suggestions,
  suggestionsLoading = false,
  suggestionsError = "",
  placeholder,
  helpId,
  help,
  disabled = false,
  required = false,
  ariaLabelledby,
  hideHeader = false,
  helpSlot = "all",
  showClipboardHint = true,
}) {
  const tokens = geneInputTokens(value);
  const selectedSymbols = tokens.map(geneSymbolFromToken);
  const searchTerm = currentGeneSearchTerm(draft);

  function commitToken(token = draft) {
    const nextValue = addGeneToken(value, token);
    onChange(nextValue);
    setDraft("");
  }

  function handleInputChange(event) {
    const nextDraft = event.target.value;
    if (/[,+;\n]/.test(nextDraft)) {
      const nextValue = nextDraft
        .split(/[,+;\n]/)
        .reduce((current, token) => addGeneToken(current, token), value);
      onChange(nextValue);
      setDraft("");
      return;
    }
    setDraft(nextDraft);
  }

  function handleKeyDown(event) {
    if ((event.key === "Enter" || event.key === "Tab") && draft.trim()) {
      event.preventDefault();
      commitToken(event.key === "Enter" && suggestions.length ? suggestions[0] : draft);
    }
    if (event.key === "Backspace" && !draft && tokens.length) {
      event.preventDefault();
      onChange(tokens.slice(0, -1).join(", "));
    }
  }

  function handlePaste(event) {
    const pasted = event.clipboardData?.getData("text") || "";
    if (!isGeneListClipboardValue(pasted)) return;
    event.preventDefault();
    onChange(mergeClipboardGeneList(value, pasted));
    setDraft("");
  }

  function handleCopy(event) {
    const target = event.target;
    const hasTextSelection =
      target instanceof HTMLInputElement &&
      target.selectionStart !== target.selectionEnd;
    if (hasTextSelection || !tokens.length) return;
    event.preventDefault();
    event.clipboardData?.setData("text/plain", tokens.join("\n"));
  }

  function handleBlur() {
    if (!draft.trim()) return;
    const symbol = geneSymbolFromToken(draft);
    if (suggestions.some((gene) => gene.toUpperCase() === symbol)) {
      commitToken(draft);
    }
  }

  return (
    <div className="gene-selector">
      {!hideHeader && (
        <div className="gene-selector-header">
          <span>{label}</span>
          {!!tokens.length && (
            <button type="button" onClick={() => onChange("")} disabled={disabled}>
              Clear all
            </button>
          )}
        </div>
      )}
      <div className="gene-autocomplete-wrap">
        <div className="gene-token-box" onCopy={handleCopy}>
          {tokens.map((token) => {
            const symbol = geneSymbolFromToken(token);
            return (
              <span key={symbol} className="gene-chip">
                {token}
                <IconButton
                  iconRole="action.close"
                  label={`Remove ${symbol}`}
                  tooltip={`Remove ${symbol}`}
                  iconSize="xsm"
                  size="sm"
                  disabled={disabled}
                  onMouseDown={(event) => event.preventDefault()}
                  onClick={() => onChange(removeGeneToken(value, symbol))}
                />
              </span>
            );
          })}
          <input
            id={id}
            value={draft}
            disabled={disabled}
            required={required}
            onChange={handleInputChange}
            onPaste={handlePaste}
            onKeyDown={handleKeyDown}
            onBlur={handleBlur}
            placeholder={tokens.length ? "Add gene..." : placeholder}
            aria-label={label}
            aria-labelledby={ariaLabelledby}
            autoComplete="off"
          />
        </div>
        {!!searchTerm && (
          <div
            className="gene-autocomplete"
            role="listbox"
            aria-label={`${label} suggestions`}
            aria-busy={suggestionsLoading}
          >
            <div className="gene-autocomplete-title">
              Suggestions for <strong>{searchTerm.toUpperCase()}</strong>
            </div>
            {suggestionsLoading ? (
              <div className="gene-autocomplete-empty" role="status">
                Searching cohort genes...
              </div>
            ) : suggestionsError ? (
              <div className="gene-autocomplete-empty" role="status">
                {suggestionsError}
              </div>
            ) : suggestions.length ? (
              suggestions.slice(0, 10).map((gene) => (
                <button
                  key={gene}
                  type="button"
                  disabled={disabled}
                  role="option"
                  aria-selected={selectedSymbols.includes(gene)}
                  className={selectedSymbols.includes(gene) ? "selected" : ""}
                  onMouseDown={(event) => event.preventDefault()}
                  onClick={() => commitToken(gene)}
                >
                  <strong>{gene}</strong>
                  {selectedSymbols.includes(gene) ? <span>Selected</span> : <span>Add gene</span>}
                </button>
              ))
            ) : (
              <div className="gene-autocomplete-empty">No matching gene symbols.</div>
            )}
          </div>
        )}
      </div>
      {showClipboardHint && <small className="gene-clipboard-hint">
        Paste a gene list with Ctrl/Cmd+V. With the empty field focused,
        Ctrl/Cmd+C copies the selected genes.
      </small>}
      {helpId ? <FieldHelp helpId={helpId} slot={helpSlot} /> : <small className="field-help">{help}</small>}
    </div>
  );
}

function CombinedSignatureBuilder({
  value,
  onSignatureChange,
  queries,
  setQuery,
  suggestions,
  suggestionStates,
  rankScoring,
}) {
  const t = useHelpText();
  return (
    <div className="combined-signature-builder">
      {[
        ["signature_a", "a", "Signature A"],
        ["signature_b", "b", "Signature B"],
      ].map(([signatureKey, queryKey, fallbackName]) => {
        const signature = value[signatureKey];
        return (
          <div className="combined-signature-card" key={signatureKey}>
            <label className="field">
              <span>{fallbackName} name</span>
              <input
                value={signature.name}
                onChange={(event) => onSignatureChange(signatureKey, { name: event.target.value })}
                placeholder={fallbackName}
              />
            </label>
            <GeneSelector
              label={`${signature.name || fallbackName} genes`}
              value={signature.gene_symbol}
              onChange={(gene_symbol) => onSignatureChange(signatureKey, { gene_symbol })}
              draft={queries[queryKey]}
              setDraft={(draft) => setQuery(queryKey, draft)}
              suggestions={suggestions[queryKey]}
              suggestionsLoading={suggestionStates[queryKey].loading}
              suggestionsError={suggestionStates[queryKey].error}
              placeholder={signatureMethodUsesDirection(signature.signature_method)
                ? "Type IFNG, GZMB, TGFB1:-1..."
                : "Type IFNG, CXCL9, GZMB..."}
              helpId="signatureGenesWeighted"
            />
              <div className="axis-control">
                <LabelWithHelp label="Score method" helpId={`score.${signature.signature_method}`} />
              <div>
                {SIGNATURE_METHOD_OPTIONS.map((method) => {
                  const rankUnavailable = signatureMethodUsesDirection(method.value)
                    && !rankScoring.available;
                  return (
                  <button
                    key={method.value}
                    type="button"
                    aria-pressed={signature.signature_method === method.value}
                    className={signature.signature_method === method.value ? "selected" : ""}
                    onClick={() => onSignatureChange(signatureKey, { signature_method: method.value })}
                    disabled={rankUnavailable}
                    title={rankUnavailable ? rankScoring.reason : t.entry(`score.${method.value}`).does}
                  >
                    {method.shortLabel}
                    </button>
                  );
                })}
                </div>
            </div>
            {signature.signature_method !== "single" && (
              <SignatureInputSummary
                method={signature.signature_method}
                value={signature.gene_symbol}
              />
            )}
          </div>
        );
      })}
    </div>
  );
}

function SignaturePanelBuilder({
  panel,
  onPanelNameChange,
  onSignatureChange,
  onAdd,
  onRemove,
  onMove,
  queries,
  onQueryChange,
  suggestionStates,
  validation,
  rankScoring,
}) {
  const signatures = panel.signatures || [];
  return (
    <div className="signature-panel-builder">
      <div className="signature-panel-contract">
        <div>
          <span>Panel comparison</span>
          <strong>2–6 continuous signature scores</strong>
        </div>
        <p>
          Every score is standardized on one common patient population. The
          model estimates main effects only; no cutpoint search or interaction
          is added.
        </p>
      </div>

      <label className="field signature-panel-name">
        <span>Panel name <small>(optional)</small></span>
        <input
          value={panel.name}
          onChange={(event) => onPanelNameChange(event.target.value)}
          placeholder="Immune program comparison"
        />
      </label>

      <div className="signature-panel-list">
        {signatures.map((signature, index) => {
          const suggestionState = suggestionStates[index] || {
            genes: [],
            loading: false,
            error: "",
          };
          return (
            <article className="signature-panel-card" key={signature.id}>
              <header>
                <span className="signature-panel-index">
                  {String(index + 1).padStart(2, "0")}
                </span>
                <strong>{signature.name || `Signature ${index + 1}`}</strong>
                <div className="signature-panel-actions">
                  <button
                    type="button"
                    onClick={() => onMove(signature.id, -1)}
                    disabled={index === 0}
                    aria-label={`Move ${signature.name || `signature ${index + 1}`} earlier`}
                    title="Move earlier"
                  >
                    <TraceIcon role="action.back" size="sm" />
                  </button>
                  <button
                    type="button"
                    onClick={() => onMove(signature.id, 1)}
                    disabled={index === signatures.length - 1}
                    aria-label={`Move ${signature.name || `signature ${index + 1}`} later`}
                    title="Move later"
                  >
                    <TraceIcon role="action.next" size="sm" />
                  </button>
                  <button
                    type="button"
                    onClick={() => onRemove(signature.id)}
                    disabled={signatures.length <= 2}
                    aria-label={`Remove ${signature.name || `signature ${index + 1}`}`}
                    title="Remove signature"
                  >
                    <TraceIcon role="action.close" size="sm" />
                  </button>
                </div>
              </header>

              <label className="field">
                <span>Signature name</span>
                <input
                  value={signature.name}
                  onChange={(event) =>
                    onSignatureChange(signature.id, {
                      name: event.target.value,
                    })
                  }
                  placeholder={`Signature ${index + 1}`}
                />
              </label>

              <GeneSelector
                label="Genes"
                value={signature.gene_symbol}
                onChange={(gene_symbol) =>
                  onSignatureChange(signature.id, { gene_symbol })
                }
                draft={queries[index] || ""}
                setDraft={(draft) => onQueryChange(index, draft)}
                suggestions={suggestionState.genes || []}
                suggestionsLoading={suggestionState.loading}
                suggestionsError={suggestionState.error}
                placeholder={signatureMethodUsesDirection(signature.signature_method)
                  ? "Type IFNG, GZMB, TGFB1:-1..."
                  : "Type IFNG, CXCL9, GZMB..."}
                helpId="signatureGenesWeighted"
              />

              <div className="axis-control signature-panel-method">
                <LabelWithHelp
                  label="Score method"
                  helpId={`score.${signature.signature_method}`}
                />
                <div>
                  {SIGNATURE_METHOD_OPTIONS.map((method) => {
                    const rankUnavailable = signatureMethodUsesDirection(method.value)
                      && !rankScoring.available;
                    return (
                    <button
                      key={method.value}
                      type="button"
                      aria-pressed={signature.signature_method === method.value}
                      className={
                        signature.signature_method === method.value ? "selected" : ""
                      }
                      onClick={() =>
                        onSignatureChange(signature.id, {
                          signature_method: method.value,
                        })
                      }
                      disabled={rankUnavailable}
                      title={rankUnavailable ? rankScoring.reason : undefined}
                    >
                      {method.shortLabel}
                    </button>
                    );
                  })}
                </div>
              </div>
              {signature.signature_method !== "single" && (
                <SignatureInputSummary
                  method={signature.signature_method}
                  value={signature.gene_symbol}
                />
              )}
            </article>
          );
        })}
      </div>

      <div className="signature-panel-footer">
        <button
          type="button"
          className="secondary-button"
          onClick={onAdd}
          disabled={signatures.length >= MAX_SIGNATURE_PANEL_SIZE}
        >
          Add signature
        </button>
        <span>{signatures.length} of {MAX_SIGNATURE_PANEL_SIZE}</span>
      </div>
      {!validation.valid && (
        <p className="signature-panel-validation" role="status">
          {validation.errors[0]}
        </p>
      )}
    </div>
  );
}

function PlotOutputControls({
  form,
  updateForm,
  updatePlotStyle,
  updateArtifactPlotStyle,
  updatePaletteColor,
  plotEditorTarget = "survival",
  onPlotEditorTargetChange = () => {},
  supportsContinuous = true,
  supportsSurvival = true,
  supportsCoxModelSelection = false,
  plotTitlePlaceholder,
  showOutputHeader = false,
}) {
  const plotStyle = {
    ...DEFAULT_PLOT_STYLE,
    ...(form.plot_style || {}),
  };
  const continuousStyle = {
    ...DEFAULT_PLOT_STYLE.continuous,
    ...(plotStyle.continuous || {}),
  };
  const coxForestStyle = {
    ...DEFAULT_PLOT_STYLE.cox_forest,
    ...(plotStyle.cox_forest || {}),
  };
  const plotValidation = plotStyleInputState(plotStyle);
  const artifactOptions = PLOT_ARTIFACT_OPTIONS.filter(
    (option) =>
      (supportsContinuous || option.value !== "continuous")
      && (supportsSurvival || option.value !== "survival"),
  );
  const activeArtifact =
    artifactOptions.some((option) => option.value === plotEditorTarget)
      ? plotEditorTarget
      : artifactOptions[0]?.value || "cox_forest";
  const artifactDescription = {
    survival: "Kaplan-Meier curves, confidence bands and risk table.",
    continuous: "Restricted cubic spline effect profile and confidence ribbon.",
    cox_forest: "Grouped Cox estimates in one forest or separate univariable and multivariable figures.",
  }[activeArtifact];

  return (
    <div className="plot-output-controls">
      {showOutputHeader && (
        <PanelHeader
          iconRole="module.plotOutput"
          title="Plot output"
          description="Edit each exported figure and preview the selected artifact."
          helpId="plotOutput"
        />
      )}

      <div className="plot-artifact-switch" aria-label="Plot to customize">
        <span>Plot to customize</span>
        <div>
          {artifactOptions.map((option) => (
            <button
              key={option.value}
              type="button"
              className={activeArtifact === option.value ? "selected" : ""}
              aria-pressed={activeArtifact === option.value}
              onClick={() => onPlotEditorTargetChange(option.value)}
            >
              {option.label}
            </button>
          ))}
        </div>
      </div>

      <div className="plot-artifact-intro">
        <strong>{PLOT_ARTIFACT_OPTIONS.find((option) => option.value === activeArtifact)?.label}</strong>
        <span>{artifactDescription}</span>
      </div>

      <div className="plot-artifact-fields">
        {activeArtifact === "survival" && (
          <>
            <div className="axis-control">
              <span>Time axis</span>
              <div>
                {["days", "months", "years"].map((unit) => (
                  <button
                    key={unit}
                    type="button"
                    className={form.time_unit === unit ? "selected" : ""}
                    onClick={() => updateForm("time_unit", unit)}
                  >
                    {unit}
                  </button>
                ))}
              </div>
            </div>

            <div className="switch-row">
              <SwitchField
                label="Confidence interval"
                checked={form.show_confidence_interval}
                onChange={(checked) => updateForm("show_confidence_interval", checked)}
              />
              <SwitchField
                label="Risk table"
                checked={form.show_risk_table}
                onChange={(checked) => updateForm("show_risk_table", checked)}
              />
            </div>

            <div className="color-grid">
              <ColorField
                label="Low / group 1"
                value={plotStyle.palette[0]}
                onChange={(value) => updatePaletteColor(0, value)}
              />
              <ColorField
                label="Mid / group 2"
                value={plotStyle.palette[1]}
                onChange={(value) => updatePaletteColor(1, value)}
              />
              <ColorField
                label="High / group 3"
                value={plotStyle.palette[2]}
                onChange={(value) => updatePaletteColor(2, value)}
              />
            </div>

            <SwitchField
              label="Plot title"
              checked={plotStyle.show_title}
              onChange={(checked) => updatePlotStyle("show_title", checked)}
            />
            {plotStyle.show_title && (
              <label className="field">
                <span>Plot title</span>
                <input
                  value={plotStyle.plot_title || ""}
                  maxLength={140}
                  onChange={(event) => updatePlotStyle("plot_title", event.target.value)}
                  placeholder={plotTitlePlaceholder}
                />
                <small className="field-help">Leave empty to use the cohort-derived title.</small>
              </label>
            )}
          </>
        )}

        {activeArtifact === "continuous" && (
          <>
            <div className="color-grid two">
              <ColorField
                label="Effect and 95% CI"
                value={continuousStyle.effect_color}
                onChange={(value) => updateArtifactPlotStyle("continuous", "effect_color", value)}
              />
              <ColorField
                label="Reference lines"
                value={continuousStyle.reference_color}
                onChange={(value) => updateArtifactPlotStyle("continuous", "reference_color", value)}
              />
            </div>
            <SwitchField
              label="Plot title"
              checked={continuousStyle.show_title}
              onChange={(checked) => updateArtifactPlotStyle("continuous", "show_title", checked)}
            />
            <div className="range-grid">
              {continuousStyle.show_title && (
                <label className="field wide">
                  <span>Plot title</span>
                  <input
                    value={continuousStyle.plot_title || ""}
                    maxLength={140}
                    onChange={(event) => updateArtifactPlotStyle("continuous", "plot_title", event.target.value)}
                    placeholder="Continuous expression effect"
                  />
                </label>
              )}
              <label className="field">
                <span>X-axis title</span>
                <input
                  value={continuousStyle.x_axis_title || ""}
                  maxLength={100}
                  onChange={(event) => updateArtifactPlotStyle("continuous", "x_axis_title", event.target.value)}
                  placeholder="Marker and expression scale"
                />
              </label>
              <label className="field">
                <span>Y-axis title</span>
                <input
                  value={continuousStyle.y_axis_title || ""}
                  maxLength={100}
                  onChange={(event) => updateArtifactPlotStyle("continuous", "y_axis_title", event.target.value)}
                  placeholder="Hazard ratio relative to median"
                />
              </label>
            </div>
            <p className="plot-control-note">
              The confidence ribbon follows the effect color. Spline method and nonlinearity remain automatically labeled from the result.
            </p>
          </>
        )}

        {activeArtifact === "cox_forest" && (
          <>
            <div className="axis-control two-options">
              <span>Figure arrangement</span>
              <div>
                {[
                  ["combined", "Combined"],
                  ["separate", "Separate"],
                ].map(([value, label]) => (
                  <button
                    key={value}
                    type="button"
                    className={coxForestStyle.model_layout === value ? "selected" : ""}
                    aria-pressed={coxForestStyle.model_layout === value}
                    onClick={() => updateArtifactPlotStyle("cox_forest", "model_layout", value)}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>
            {supportsCoxModelSelection && (
              <div className="cox-model-display-control">
                <div className="axis-control two-options">
                  <span>Multivariable rows</span>
                  <div>
                    {[
                      ["all", "Show all"],
                      ["selected", "Choose rows"],
                    ].map(([value, label]) => (
                      <button
                        key={value}
                        type="button"
                        className={coxForestStyle.multivariable_display === value ? "selected" : ""}
                        aria-pressed={coxForestStyle.multivariable_display === value}
                        onClick={() => updateArtifactPlotStyle("cox_forest", "multivariable_display", value)}
                      >
                        {label}
                      </button>
                    ))}
                  </div>
                </div>
                {coxForestStyle.multivariable_display === "selected" && (
                  <fieldset className="cox-model-choice-grid">
                    <legend>Rows included in the forest plot</legend>
                    {COX_MULTIVARIABLE_MODEL_OPTIONS.map(([value, label]) => {
                      const selected = coxForestStyle.multivariable_model_ids || [];
                      const checked = selected.includes(value);
                      return (
                        <label key={value}>
                          <input
                            type="checkbox"
                            checked={checked}
                            onChange={() => {
                              const next = checked
                                ? selected.filter((item) => item !== value)
                                : [...selected, value];
                              if (next.length) {
                                updateArtifactPlotStyle("cox_forest", "multivariable_model_ids", next);
                              }
                            }}
                          />
                          <span>{label}</span>
                        </label>
                      );
                    })}
                  </fieldset>
                )}
                <p className="plot-control-note">
                  Only evaluable rows are drawn. Run the analysis again to update the plot and its recorded downloads.
                </p>
              </div>
            )}
            <div className="color-grid">
              <ColorField
                label="Lower hazard"
                value={coxForestStyle.lower_hazard_color}
                onChange={(value) => updateArtifactPlotStyle("cox_forest", "lower_hazard_color", value)}
              />
              <ColorField
                label="Higher hazard"
                value={coxForestStyle.higher_hazard_color}
                onChange={(value) => updateArtifactPlotStyle("cox_forest", "higher_hazard_color", value)}
              />
              <ColorField
                label="Reference line"
                value={coxForestStyle.reference_color}
                onChange={(value) => updateArtifactPlotStyle("cox_forest", "reference_color", value)}
              />
            </div>
            <SwitchField
              label="Plot title"
              checked={coxForestStyle.show_title}
              onChange={(checked) => updateArtifactPlotStyle("cox_forest", "show_title", checked)}
            />
            <div className="range-grid">
              {coxForestStyle.show_title && coxForestStyle.model_layout !== "separate" && (
                <label className="field wide">
                  <span>Plot title</span>
                  <input
                    value={coxForestStyle.plot_title || ""}
                    maxLength={140}
                    onChange={(event) => updateArtifactPlotStyle("cox_forest", "plot_title", event.target.value)}
                    placeholder="Cox proportional hazards models"
                  />
                </label>
              )}
              {coxForestStyle.show_title && coxForestStyle.model_layout === "separate" && (
                <>
                  <label className="field">
                    <span>Univariable title</span>
                    <input
                      value={coxForestStyle.univariable_plot_title || ""}
                      maxLength={140}
                      onChange={(event) => updateArtifactPlotStyle(
                        "cox_forest",
                        "univariable_plot_title",
                        event.target.value,
                      )}
                      placeholder="Univariable Cox model"
                    />
                  </label>
                  <label className="field">
                    <span>Multivariable title</span>
                    <input
                      value={coxForestStyle.multivariable_plot_title || ""}
                      maxLength={140}
                      onChange={(event) => updateArtifactPlotStyle(
                        "cox_forest",
                        "multivariable_plot_title",
                        event.target.value,
                      )}
                      placeholder="Multivariable Cox models"
                    />
                  </label>
                </>
              )}
              <label className="field wide">
                <span>X-axis title</span>
                <input
                  value={coxForestStyle.x_axis_title || ""}
                  maxLength={100}
                  onChange={(event) => updateArtifactPlotStyle("cox_forest", "x_axis_title", event.target.value)}
                  placeholder="Hazard ratio (log scale)"
                />
              </label>
            </div>
            <p className="plot-control-note">
              {coxForestStyle.model_layout === "separate"
                ? "Separate mode creates one univariable figure and one multivariable figure containing the requested evaluable rows. Both use the same axis scale."
                : "Point and interval colors follow the estimated direction. Model names, group contrast, estimates, confidence intervals and p-values remain data-derived."}
            </p>
          </>
        )}
      </div>

      <div className="plot-style-shared">
        <div>
          <strong>Typography &amp; axes</strong>
          <span>Applied consistently to Survival, Continuous Cox and Cox model exports.</span>
        </div>
        <div className="range-grid">
          <label className="field">
            <span>Font family</span>
            <select
              value={plotStyle.font_family}
              onChange={(event) => updatePlotStyle("font_family", event.target.value)}
            >
              <option value="sans">Sans</option>
              <option value="serif">Serif</option>
              <option value="mono">Mono</option>
            </select>
          </label>
          {activeArtifact !== "cox_forest" && (
            <div className="axis-control two-options">
              <LabelWithHelp
                label="Plot shape"
                helpId="plotAspectRatio"
              />
              <div>
                {[
                  { value: "rectangular", label: "Rectangular" },
                  { value: "square", label: "Square" },
                ].map((shape) => (
                  <button
                    key={shape.value}
                    type="button"
                    className={plotStyle.plot_aspect === shape.value ? "selected" : ""}
                    onClick={() => updatePlotStyle("plot_aspect", shape.value)}
                  >
                    {shape.label}
                  </button>
                ))}
              </div>
            </div>
          )}
          <label className="field">
            <span>Base font size</span>
            <input
              type="number"
              min="8"
              max="20"
              value={plotStyle.base_font_size}
              onChange={(event) => updatePlotStyle("base_font_size", event.target.value)}
              aria-invalid={!plotValidation.valid}
            />
          </label>
        </div>
        <div className="plot-axis-style-stack">
          <PlotTextStyleField
            label="Axis values"
            description="Tick labels and categorical axis values"
            size={plotStyle.axis_text_size}
            minimum="6"
            maximum="24"
            bold={plotStyle.axis_text_bold}
            italic={plotStyle.axis_text_italic}
            onSizeChange={(value) => updatePlotStyle("axis_text_size", value)}
            onBoldChange={(value) => updatePlotStyle("axis_text_bold", value)}
            onItalicChange={(value) => updatePlotStyle("axis_text_italic", value)}
          />
          <PlotTextStyleField
            label="Axis titles"
            description="X and Y axis titles"
            size={plotStyle.axis_title_size}
            minimum="6"
            maximum="26"
            bold={plotStyle.axis_title_bold}
            italic={plotStyle.axis_title_italic}
            onSizeChange={(value) => updatePlotStyle("axis_title_size", value)}
            onBoldChange={(value) => updatePlotStyle("axis_title_bold", value)}
            onItalicChange={(value) => updatePlotStyle("axis_title_italic", value)}
          />
          <PlotFrameField
            value={plotStyle.plot_frame}
            onChange={(value) => updatePlotStyle("plot_frame", value)}
          />
          <div className="plot-grid-setting">
            <SwitchField
              label="Plot grid"
              checked={plotStyle.show_grid}
              onChange={(checked) => updatePlotStyle("show_grid", checked)}
            />
            <span>Grid lines stay behind the data and frame.</span>
          </div>
        </div>
        {!plotValidation.valid && (
          <p className="field-error" role="alert">{plotValidation.errors[0]}</p>
        )}
        {activeArtifact === "cox_forest" && (
          <p className="plot-control-note">
            Forest height adapts to the number of completed Cox models.
          </p>
        )}
      </div>
    </div>
  );
}

function CompareAnalyses({
  form,
  cohorts,
  visibleCohorts,
  selectedCohort,
  selectedCohortId,
  cohortQuery,
  setCohortQuery,
  cohortPickerOpen,
  setCohortPickerOpen,
  onSelectCohort,
  repositoryDatasets,
  selectedRepositoryDataset,
  onSelectRepositoryDataset,
  endpointOptions,
  selectedEndpoint,
  onSelectEndpoint,
  updateForm,
  updatePlotStyle,
  updateArtifactPlotStyle,
  updatePaletteColor,
  plotEditorTarget,
  onPlotEditorTargetChange,
  expressionScales,
  expressionScaleValue,
  onSelectExpressionScale,
  filters,
  activeFilterCount,
  updateFilters,
  toggleFilterValue,
  clearFilter,
  compare,
  setCompare,
  cutpoints,
  expressionScale,
  suggestionCohort,
  canRun,
  metadataReady,
  metadataError,
  onRetryMetadata,
  dataRequirement,
  onDownload,
  tutorialStepId = null,
}) {
  const t = useHelpText();
  const selectedMethods = compare.methods;
  const [compareStep, setCompareStep] = useState(0);
  const [compareGeneQuery, setCompareGeneQuery] = useState("");
  const [plotEditorOpen, setPlotEditorOpen] = useState(false);
  const compareGeneSuggestionState = useGeneSuggestions(
    suggestionCohort,
    compareGeneQuery,
    form.dataset_id,
    form.dataset_release_id,
    form.expression_layer_id,
  );
  const compareGeneSuggestions = compareGeneSuggestionState.genes;
  const compareStepPanelRef = useRef(null);

  useEffect(() => {
    if (!tutorialStepId) return;
    const nextStep = COMPARE_WORKFLOW_STEPS.findIndex(({ id }) => id === tutorialStepId);
    if (nextStep >= 0 && nextStep !== compareStep) setCompareStep(nextStep);
  }, [tutorialStepId]);
  const effectiveCompareInput = compareGeneQuery.trim() ? addGeneToken(compare.genes, compareGeneQuery) : compare.genes;
  const genes = uniqueGeneSymbols(effectiveCompareInput);
  const adjusted = useMemo(() => adjustCompareResults(compare.results, compare.grouped_family)
    .map((row) => ({ ...row, adjustmentRequested: compare.result_context?.adjustment_requested })),
  [compare.results, compare.grouped_family, compare.result_context]);
  const selectedCutpoints = cutpoints.filter((item) => selectedMethods.includes(item.value));
  const compareMarkerValidation = signatureInputState(effectiveCompareInput, {
    allowWeights: false,
    maximumGenes: PUBLIC_ANALYSIS_BATCH_MAX,
    label: "Compare genes",
  });
  const compareFiltersValidation = analysisFilterState(form.filters);
  const comparePlotValidation = plotStyleInputState(form.plot_style);
  const selectedPercentileValidation = percentileInputState(
    selectedMethods.includes("percentile"),
    form.custom_percentile,
  );
  const allPercentileValidation = percentileInputState(
    true,
    form.custom_percentile,
  );
  const selectedCapacity = batchCapacityState(genes.length, selectedMethods.length);
  const allCapacity = batchCapacityState(genes.length, DICHOTOMIZATION_METHODS.length);
  const compareCoreReady = Boolean(
    canRun && form.cohort
    && (form.dataset_id || form.filters.sample_population)
    && selectedEndpoint.available,
  );
  const missingRequirements = [];
  if (dataRequirement) missingRequirements.push(dataRequirement);
  if (!form.cohort) missingRequirements.push("select a cancer cohort");
  if (form.cohort && !form.dataset_id && !form.filters.sample_population) {
    missingRequirements.push("choose a molecular population");
  }
  if (form.cohort && !selectedEndpoint.available) missingRequirements.push("select an available survival endpoint");
  if (!genes.length) missingRequirements.push("add at least one gene");
  if (!selectedMethods.length) missingRequirements.push("select at least one method");
  const canRunSelectedMethods = Boolean(
    compareCoreReady
    && genes.length > 0
    && compareMarkerValidation.valid
    && selectedMethods.length > 0
    && selectedPercentileValidation.valid
    && selectedCapacity.valid
    && compareFiltersValidation.valid
    && comparePlotValidation.valid
    && !compare.running,
  );
  const canRunAllDichotomizations = Boolean(
    compareCoreReady
    && genes.length > 0
    && compareMarkerValidation.valid
    && allPercentileValidation.valid
    && allCapacity.valid
    && compareFiltersValidation.valid
    && comparePlotValidation.valid
    && !compare.running,
  );
  const selectedDichotomizationCount = selectedMethods.filter((method) => DICHOTOMIZATION_METHODS.includes(method)).length;
  function buildCompareJobs(methodsToRun) {
    return genes.flatMap((gene) => methodsToRun.map((method) => ({
      gene, method,
      payload: {
        ...buildAnalysisPayload({ ...form, gene_symbol: gene, signature_method: "single" }),
        gene_symbol: gene, signature_method: "single", signature_genes: [],
        cutpoint_method: method,
        custom_percentile: method === "percentile" ? Number(form.custom_percentile) : null,
      },
    })));
  }
  const currentContext = compareMarkerValidation.valid && selectedPercentileValidation.valid
    && compareFiltersValidation.valid && comparePlotValidation.valid
    ? compareRequestContext(buildCompareJobs(selectedMethods).map((job) => job.payload)) : null;
  const compareResultsNeedRerun = adjusted.length > 0
    && survivalResultsAreStale(compare.result_context?.fingerprint, currentContext?.fingerprint);
  const resultGenes = compare.result_context?.genes || [...new Set(adjusted.map((row) => row.gene))];
  const resultMethods = (compare.result_context?.methods || [...new Set(adjusted.map((row) => row.method))])
    .map((method) => cutpoints.find((item) => item.value === method) || { value: method, label: method });
  const familySummary = comparisonFamilySummary(adjusted);
  const compareStepCompletion = [
    compareCoreReady,
    genes.length > 0 && compareMarkerValidation.valid,
    selectedMethods.length > 0,
    compareCoreReady && genes.length > 0 && selectedMethods.length > 0,
    canRunSelectedMethods,
  ];
  const compareStepRequirements = [
    dataRequirement || (!form.cohort
      ? "Select a cancer cohort to continue."
      : !form.dataset_id && !form.filters.sample_population
        ? "Choose the molecular population that should represent each patient."
      : selectedEndpoint.available
        ? ""
        : "Choose an endpoint that passes cohort QC."),
    compareMarkerValidation.valid
      ? ""
      : compareMarkerValidation.errors[0] || "Add at least one gene.",
    selectedMethods.length ? "" : "Select at least one cutpoint method.",
    compareCoreReady && genes.length && selectedMethods.length
      ? ""
      : "Complete Dataset, Markers and Methods first.",
    canRunSelectedMethods
      ? ""
      : selectedPercentileValidation.error
        || selectedCapacity.error
        || compareFiltersValidation.errors[0]
        || comparePlotValidation.errors[0]
        || "Complete the required cohort, endpoint, gene and method selections.",
  ];
  const compareLedger = compareDesignLedger({
    datasetLabel: selectedRepositoryDataset?.name || (form.cohort ? getCohortName(form.cohort) : ""),
    geneCount: genes.length,
    methodLabels: selectedCutpoints.map((item) => item.label),
    endpointLabel: selectedEndpoint.available ? selectedEndpoint.label : "",
    expressionScaleLabel: expressionScale?.label,
    events: selectedEndpoint.available ? selectedEndpoint.events : undefined,
    filterCount: activeFilterCount,
    adjustmentSummary: formatAdjustmentSummary(
      form.adjustment_covariates,
      form.external_adjustment_covariates,
      form.external_covariates,
    ),
    covariateCount:
      (form.adjustment_covariates || []).length
      + (form.external_adjustment_covariates || []).length,
    requirements: compareStepRequirements.filter(Boolean),
  });
  const activeCompareStep = COMPARE_WORKFLOW_STEPS[compareStep] || COMPARE_WORKFLOW_STEPS[0];
  const compareSetupSummary = [
    selectedRepositoryDataset?.source_accession
      || form.cohort
      || "Cohort pending",
    genes.length ? `${genes.length} marker${genes.length === 1 ? "" : "s"}` : "Markers pending",
    selectedMethods.length ? `${selectedMethods.length} method${selectedMethods.length === 1 ? "" : "s"}` : "Methods pending",
    activeFilterCount ? `${activeFilterCount} filter${activeFilterCount === 1 ? "" : "s"}` : "No filters",
    formatAdjustmentSummary(
      form.adjustment_covariates,
      form.external_adjustment_covariates,
      form.external_covariates,
    ),
  ].join(" · ");

  function toggleMethod(method) {
    setCompare((current) => ({
      ...current,
      methods: current.methods.includes(method)
        ? current.methods.filter((item) => item !== method)
        : [...current.methods, method],
    }));
  }

  function navigateCompareStep(nextStep) {
    const boundedStep = Math.max(0, Math.min(COMPARE_WORKFLOW_STEPS.length - 1, nextStep));
    setCompareStep(boundedStep);
    window.requestAnimationFrame(() => {
      compareStepPanelRef.current?.focus({ preventScroll: true });
      document
        .getElementById(workflowStepControlId(COMPARE_WORKFLOW_STEPS[boundedStep], "compare-step"))
        ?.scrollIntoView({ behavior: "auto", block: "nearest", inline: "center" });
      compareStepPanelRef.current
        ?.closest(".compare-step-controls")
        ?.scrollIntoView({ behavior: "auto", block: "start" });
    });
  }

  async function runCompare(methodOverride = null) {
    const methodsToRun = methodOverride || selectedMethods;
    const percentile = percentileInputState(
      methodsToRun.includes("percentile"),
      form.custom_percentile,
    );
    const capacity = batchCapacityState(genes.length, methodsToRun.length);
    if (
      !compareCoreReady
      || !genes.length
      || !compareMarkerValidation.valid
      || !methodsToRun.length
      || !percentile.valid
      || !capacity.valid
      || !compareFiltersValidation.valid
      || !comparePlotValidation.valid
    ) {
      setCompare((current) => ({
        ...current,
        error: compareMarkerValidation.errors[0]
          || percentile.error
          || capacity.error
          || compareFiltersValidation.errors[0]
          || comparePlotValidation.errors[0]
          || `Cannot run comparison: ${missingRequirements.join(", ") || "check inputs"}.`,
      }));
      return;
    }
    const normalizedGenes = uniqueGeneSymbols(effectiveCompareInput);
    const jobs = buildCompareJobs(methodsToRun);
    const resultContext = compareRequestContext(jobs.map((job) => job.payload));
    const runId = {};
    setCompareGeneQuery("");
    setCompare((current) => ({
      ...current,
      methods: methodsToRun,
      genes: normalizedGenes.join(", "),
      running: true,
      active_run_id: runId,
      error: "",
    }));
    try {
      const batch = await createAnalysesBatch(jobs.map((job) => job.payload), ANALYSIS_BATCH_CONCURRENCY, { retainCompletedForRecovery: true });
      const results = batch.results.map((item) => {
        const job = jobs[item.index];
        return {
          index: item.index,
          gene: job.gene,
          method: job.method,
          result: item.status === "completed" ? item.result : null,
          error: item.status === "failed" ? formatBatchItemError(item) : null,
        };
      });
      setCompare((current) => current.active_run_id !== runId ? current : ({
        ...current,
        results,
        result_context: resultContext,
        grouped_family: batch.grouped_family || null,
        completed_event_id: batch.recovery_event_id,
        error: batch.failed ? `${batch.failed} comparison${batch.failed === 1 ? "" : "s"} failed; see matrix cells.` : "",
      }));
    } catch (err) {
      setCompare((current) => current.active_run_id !== runId ? current : ({ ...current, error: formatError(err) }));
    } finally {
      setCompare((current) => current.active_run_id !== runId ? current : ({ ...current, running: false, active_run_id: null }));
    }
  }

  return (
    <section className="compare-page">
      <ActiveJobRecovery
        sourceView="compare"
        busy={compare.running}
        onRecover={(result, _job, entry) => {
          const context = Array.isArray(entry?.recovery_context)
            ? entry.recovery_context
            : [];
          const recovered = (result?.results || []).map((item, index) => {
            const source = context[item.index ?? index] || {};
            return {
              index: item.index ?? index,
              gene: source.gene || item.result?.gene_symbol || "Gene",
              method: source.method || item.result?.cutpoint_method || item.result?.metrics?.cutpoint_method || "unknown",
              result: item.status === "completed" ? item.result : null,
              error: item.status === "failed" ? formatBatchItemError(item) : null,
            };
          });
          setCompare((current) => ({
            ...current,
            running: false,
            results: recovered,
            active_run_id: null,
            result_context: { ...context[0], fingerprint: null,
              cohort: context[0]?.cohort || recovered[0]?.result?.cohort,
              endpoint: context[0]?.endpoint || recovered[0]?.result?.metrics?.endpoint,
              genes: [...new Set(recovered.map((row) => row.gene))],
              methods: [...new Set(recovered.map((row) => row.method))] },
            grouped_family: result?.grouped_family || null,
            error: "",
          }));
        }}
      />
      <div className="layout analysis-workflow-layout compare-workflow-layout">
        <section className="control-panel analysis-step-controls compare-step-controls" aria-label="Comparison controls">
          <AnalysisWorkflowStepper
            steps={COMPARE_WORKFLOW_STEPS}
            activeStep={compareStep}
            completion={compareStepCompletion}
            summary={compareSetupSummary}
            onSelect={navigateCompareStep}
            idPrefix="compare-step"
            ariaLabel="Comparison analysis setup"
            summaryLabel="Current comparison"
          />

          {form.cohort && !metadataReady && (
            <div className="survival-metadata-status" role="status">
              <strong>{t.entry(metadataError ? "survivalMetadataError" : "survivalMetadata").term}</strong>
              <FieldHelp helpId={metadataError ? "survivalMetadataError" : "survivalMetadata"} />
              {metadataError && <>
                <button type="button" onClick={onRetryMetadata}>Retry cohort details</button>
                <details><summary>Technical details</summary><p>{metadataError}</p></details>
              </>}
            </div>
          )}

          <section
            ref={compareStepPanelRef}
            className="analysis-step-panel compare-step-panel"
            id={`compare-step-panel-${activeCompareStep.id}`}
            aria-labelledby={workflowStepControlId(activeCompareStep, "compare-step")}
            tabIndex={-1}
          >
          {activeCompareStep.id === "dataset" && (
            <>
            <PanelHeader
              iconRole="module.comparisonDataset"
              title="Dataset and endpoint"
              description="Use the same cohort, outcome and expression scale for all comparisons."
              helpId="compare"
            />
            <div className="compare-control-grid">
              <div className="compare-control-block">
                <div className="compare-control-label">
                  <span>Cohort</span>
                </div>
                <CohortPicker
                  cohorts={cohorts}
                  visibleCohorts={visibleCohorts}
                  selectedCohort={selectedCohort}
                  selectedCohortId={selectedCohortId}
                  query={cohortQuery}
                  setQuery={setCohortQuery}
                  open={cohortPickerOpen}
                  setOpen={setCohortPickerOpen}
                  onSelect={onSelectCohort}
                />
                <RepositorySourceSelector
                  selectedCohort={selectedCohort}
                  datasets={repositoryDatasets}
                  selectedDataset={selectedRepositoryDataset}
                  onSelect={onSelectRepositoryDataset}
                  analysisType="compare"
                  compact
                />
                <CohortAdjustmentNotice filters={metadataReady ? filters : null} />
                <MolecularPopulationSelector
                  form={form}
                  filters={filters}
                  compact
                  onChange={(value) => updateFilters("sample_population", value)}
                />
              </div>
              <div className="compare-control-block">
                <div className="compare-control-label">
                  <LabelWithHelp label="Survival endpoint" helpId="survivalEndpoint" />
                  <strong>{selectedEndpoint.available ? "Available" : "Unavailable"}</strong>
                </div>
                <EndpointSelector
                  endpoints={endpointOptions}
                  selected={form.endpoint}
                  onSelect={onSelectEndpoint}
                />
              </div>
              <div className="compare-control-block wide">
                <ExpressionDataSelector options={expressionScales} value={expressionScaleValue} onChange={onSelectExpressionScale} />
              </div>
            </div>
            </>
          )}

          {activeCompareStep.id === "markers" && (
            <>
            <PanelHeader
              iconRole="module.geneAnalysis"
              title="Markers"
              description="Each selected gene defines one row in the comparison matrix."
              helpId="compareRobustness"
            />
            <div className="compare-control-grid">
              <GeneSelector
                label="Genes to compare"
                value={compare.genes}
                onChange={(value) => setCompare((current) => ({ ...current, genes: value }))}
                draft={compareGeneQuery}
                setDraft={setCompareGeneQuery}
                suggestions={compareGeneSuggestions}
                suggestionsLoading={compareGeneSuggestionState.loading}
                suggestionsError={compareGeneSuggestionState.error}
                placeholder="Type TP53, KRAS, EGFR..."
                helpId="compareGenes"
              />
            </div>
            </>
          )}

          {activeCompareStep.id === "methods" && (
            <>
            <PanelHeader
              iconRole="module.markersCutpoints"
              title="Cutpoint methods"
              description="Each grouping method adds a column to the comparison."
              helpId="compareRobustness"
            />
            <div className="compare-method-panel">
              <div className="compare-control-label">
                <LabelWithHelp label="Cutpoint methods" helpId="compareRobustness" />
                <strong>{selectedMethods.length} selected / {selectedDichotomizationCount} dichotomizing</strong>
              </div>
              <div className="method-grid compact">
                {cutpoints.map((item) => (
                  <button
                    key={item.value}
                    type="button"
                    className={selectedMethods.includes(item.value) ? "selected" : ""}
                    aria-pressed={selectedMethods.includes(item.value)}
                    onClick={() => toggleMethod(item.value)}
                    title={t.entry(`cutpoint.${item.value}`).does}
                  >
                    <strong>{item.label}</strong>
                    <span>{t.caption(`cutpoint.${item.value}`)}</span>
                  </button>
                ))}
              </div>
              {selectedMethods.includes("percentile") && <FieldWithHelp className="compare-percentile-field" label="Percentile threshold" htmlFor="compare-percentile" helpId="cutpoint.percentile">
                <input
                  id="compare-percentile"
                  type="number"
                  min="1"
                  max="99"
                  value={form.custom_percentile}
                  onChange={(event) => updateForm("custom_percentile", event.target.value)}
                  aria-invalid={!selectedPercentileValidation.valid}
                  aria-describedby={!selectedPercentileValidation.valid ? "compare-percentile-error" : undefined}
                />
                {!selectedPercentileValidation.valid && (
                  <small id="compare-percentile-error" className="field-error" role="alert">
                    {selectedPercentileValidation.error}
                  </small>
                )}
              </FieldWithHelp>}
              {!selectedCapacity.valid && (
                <p className="field-error" role="alert">{selectedCapacity.error}</p>
              )}
              <div className="parameter-note">
                Run selected methods uses only checked columns. Run all 5 cutpoint methods runs every dichotomizing strategy downstream: maxstat, median, upper quartile, outer quartiles and percentile.
              </div>
            </div>
            </>
          )}

          {activeCompareStep.id === "filters" && (
            <>
              <PanelHeader
                iconRole="module.clinicalFilters"
                title="Patient filters and adjustment"
                description="Patient filters and clinical adjustment apply to every comparison in this batch."
                helpId={["clinicalFilters", "clinicalAdjustment"]}
              />
              <div className="compare-filter-grid">
                <div className="clinical-section-heading">
                  <strong>Eligibility filters</strong>
                  <span>{activeFilterCount ? `${activeFilterCount} active` : "All eligible patients"}</span>
                </div>
                <FilterGroup
                  title="Sample type"
                  values={filters?.sample_types || []}
                  selected={form.filters.sample_types}
                  onToggle={(value) => toggleFilterValue("sample_types", value)}
                  onClear={() => clearFilter("sample_types")}
                />
                <FilterGroup
                  title="Stage"
                  values={filters?.stages || []}
                  selected={form.filters.stages}
                  onToggle={(value) => toggleFilterValue("stages", value)}
                  onClear={() => clearFilter("stages")}
                />
                <FilterGroup
                  title="Grade"
                  values={filters?.grades || []}
                  selected={form.filters.grades}
                  onToggle={(value) => toggleFilterValue("grades", value)}
                  onClear={() => clearFilter("grades")}
                  showWhenEmpty
                  emptyLabel="No grade metadata for this cohort"
                />
                <FilterGroup
                  title="Gender"
                  values={filters?.genders || []}
                  selected={form.filters.genders}
                  onToggle={(value) => toggleFilterValue("genders", value)}
                  onClear={() => clearFilter("genders")}
                />
                <FilterGroup
                  title="Race"
                  values={filters?.races || []}
                  selected={form.filters.races}
                  onToggle={(value) => toggleFilterValue("races", value)}
                  onClear={() => clearFilter("races")}
                />
                <div className="range-grid">
                  <label className="field">
                    <span>Min age</span>
                    <input
                      type="number"
                      min="0"
                      max="150"
                      step="any"
                      value={form.filters.age_min}
                      onChange={(event) => updateFilters("age_min", event.target.value)}
                      placeholder={filters?.age_min ? String(Math.floor(filters.age_min)) : ""}
                    />
                  </label>
                  <label className="field">
                    <span>Max age</span>
                    <input
                      type="number"
                      min="0"
                      max="150"
                      step="any"
                      value={form.filters.age_max}
                      onChange={(event) => updateFilters("age_max", event.target.value)}
                      placeholder={filters?.age_max ? String(Math.ceil(filters.age_max)) : ""}
                    />
                  </label>
                  <label className="field wide">
                    <span>Maximum follow-up days</span>
                    <input
                      type="number"
                      min="1"
                      step="any"
                      value={form.filters.max_time_days}
                      onChange={(event) => updateFilters("max_time_days", event.target.value)}
                      placeholder={filters?.os_time_max_days ? String(Math.ceil(filters.os_time_max_days)) : ""}
                    />
                  </label>
                </div>
                {!compareFiltersValidation.valid && (
                  <p className="field-error" role="alert">
                    {compareFiltersValidation.errors[0]}
                  </p>
                )}
                <ClinicalFilterControls
                  variables={filters?.clinical_grouping_variables || []}
                  value={form.filters.custom_filters || []}
                  onChange={(value) => updateFilters("custom_filters", value)}
                  analysisContext="survival"
                />
                <ClinicalAdjustmentSelector
                  selected={form.adjustment_covariates || []}
                  filters={filters}
                  onToggle={(value) =>
                    updateForm(
                      "adjustment_covariates",
                      toggleListValue(form.adjustment_covariates || [], value),
                    )
                  }
                  externalDataset={form.external_covariates}
                  externalSelected={form.external_adjustment_covariates || []}
                  onExternalChange={(dataset, values) => {
                    updateForm("external_covariates", dataset);
                    updateForm("external_adjustment_covariates", values);
                  }}
                />
              </div>
            </>
          )}

          {activeCompareStep.id === "run" && (
            <>
              <PanelHeader
                iconRole="module.plotOutput"
                title="Plot output and execution"
                description={`${genes.length} genes × ${selectedMethods.length} methods = ${genes.length * selectedMethods.length} analyses`}
                helpId="plotOutput"
              />
              <details className="plot-editor-disclosure" open={plotEditorOpen} onToggle={(event) => setPlotEditorOpen(event.currentTarget.open)}>
                <summary><span><strong>Edit plots and exports</strong><small>Titles, colors, typography, axes and Cox layouts</small></span></summary>
                <PlotOutputControls
                form={form}
                updateForm={updateForm}
                updatePlotStyle={updatePlotStyle}
                updateArtifactPlotStyle={updateArtifactPlotStyle}
                updatePaletteColor={updatePaletteColor}
                plotEditorTarget={plotEditorTarget}
                onPlotEditorTargetChange={onPlotEditorTargetChange}
                supportsCoxModelSelection
                plotTitlePlaceholder={`${selectedCohort ? getCohortName(selectedCohort.id) : "Cancer"} comparison`}
              />
              </details>
              <div className="analysis-final-review">
                <strong>Multiple-testing scope</strong>
                <FieldHelp helpId="compareMultiplicity" />
              </div>
            </>
          )}
          </section>

          <DesignLedger
            compact={activeCompareStep.id !== "run"}
            title="This comparison"
            ledger={compareLedger}
            requirementsId="compare-design-requirements"
          />

          <CompareStepActions
            activeStep={compareStep}
            totalSteps={COMPARE_WORKFLOW_STEPS.length}
            canContinue={compareStepCompletion[compareStep]}
            requirement={compareStepRequirements[compareStep]}
            loading={compare.running}
            canRunSelected={canRunSelectedMethods}
            canRunAll={canRunAllDichotomizations}
            onBack={() => navigateCompareStep(compareStep - 1)}
            onContinue={() => navigateCompareStep(compareStep + 1)}
            onRunSelected={() => runCompare()}
            onRunAll={() => runCompare(DICHOTOMIZATION_METHODS)}
          />
        </section>

        <section className="result-panel previewing compare-preview-panel" aria-live="polite">
          <CompareSetupPreview
            activeStep={compareStep}
            step={activeCompareStep}
            cohort={selectedCohort}
            repositoryDataset={selectedRepositoryDataset}
            endpoint={selectedEndpoint}
            expressionScale={expressionScale}
            genes={genes}
            methods={selectedCutpoints}
            activeFilterCount={activeFilterCount}
            form={form}
            plotEditorTarget={plotEditorTarget}
            running={compare.running}
            plotEditorOpen={plotEditorOpen}
          />
        </section>
      </div>
      {compare.error && <div className="error-box"><TraceIcon role="status.error" size="md" tone="error" /><span>{compare.error}</span></div>}
      {compareResultsNeedRerun && (
        <div className="method-note caution" role="status">
          <strong>{compare.result_context?.fingerprint ? "Settings changed." : "Recovered result."}</strong> The results and downloads below retain their original analysis settings. Run again to use the current controls.
        </div>
      )}
      <GuideAnchor
        anchor={GUIDE_ANCHORS.COMPARE_RESULTS}
        label="Cutpoint comparison results"
        className="compare-results-slot"
      >
        {adjusted.length > 0 && <section className="analysis-final-review compare-run-summary" aria-label="Completed comparison settings">
          <strong>Results: {compare.result_context?.cohort || "Source not recorded"} · {compare.result_context?.endpoint || "Endpoint not recorded"}</strong>
          <span>{compare.result_context?.dataset_id || ""} {compare.result_context?.dataset_release_id || ""} {compare.result_context?.expression_layer_id || compare.result_context?.expression_scale || ""}</span>
          <span>{familySummary.requested} requested · {familySummary.completed} completed · {familySummary.failed} failed · {familySummary.evaluable} valid grouped tests</span>
          {compare.result_context?.fingerprint && <details>
            <summary>Submitted clinical settings</summary>
            <p>{analysisFilterLabels(compare.result_context.filters).join(" · ") || "No clinical restrictions"}</p>
            <p>Adjustment: {[...(compare.result_context.adjustment_covariates || []), ...(compare.result_context.external_adjustment_covariates || [])].map(formatLabel).join(", ") || "None requested"}</p>
            {compare.result_context.custom_percentile != null && <p>Custom percentile: {compare.result_context.custom_percentile}</p>}
          </details>}
          <FieldHelp helpId="compareMultiplicity" />
          <button type="button" className="secondary-button" onClick={() => downloadBlob(new Blob([compareSummaryCsv(adjusted, compare.result_context)], { type: "text/csv;charset=utf-8" }), "trace-compare-summary.csv")}>Download comparison summary CSV</button>
        </section>}
        <ResultTabs label="Comparison result sections">
        <ResultSection id="continuous" title="Continuous models" helpId="compareContinuousReference">
        <ContinuousReferenceSummary rows={adjusted} onDownload={onDownload} />
        </ResultSection>
        <ResultSection id="plots" title="Survival curves">
        <ComparePlotMatrix
          rows={adjusted}
          genes={adjusted.length ? resultGenes : genes}
          methods={adjusted.length ? resultMethods : selectedCutpoints}
          running={compare.running}
          onDownload={onDownload}
        />
        </ResultSection>
        <ResultSection id="cutpoints" title="Cutpoint comparison">
        <CutpointRobustnessSummary rows={adjusted} methods={cutpoints} />
        </ResultSection>
        </ResultTabs>
        <div className="method-note">
          These comparisons are exploratory. BH and Bonferroni cover the valid grouped tests in this submitted batch, not continuous Cox, grouped Cox, RMST or other runs.
        </div>
      </GuideAnchor>
    </section>
  );
}

function CompareStepActions({
  activeStep,
  totalSteps,
  canContinue,
  requirement,
  loading,
  canRunSelected,
  canRunAll,
  onBack,
  onContinue,
  onRunSelected,
  onRunAll,
}) {
  const isFirst = activeStep === 0;
  const isLast = activeStep === totalSteps - 1;
  return (
    <div className={`analysis-step-actions${isLast ? " compare-final-step-actions" : ""}`}>
      <button
        type="button"
        className="secondary-button"
        onClick={onBack}
        disabled={isFirst || loading}
      >
        <TraceIcon role="action.back" size="sm" />
        Back
      </button>
      <span className={requirement ? "analysis-step-requirement" : "analysis-step-position"} aria-live="polite">
        {requirement || `Step ${activeStep + 1} of ${totalSteps}`}
      </span>
      {isLast ? (
        <div className="compare-final-actions">
          <button
            type="button"
            className="secondary-button"
            onClick={onRunAll}
            disabled={!canRunAll || loading}
            title="Run maxstat, median, upper quartile, outer quartiles and the selected custom percentile."
          >
            {loading ? <TraceIcon role="status.loading" size="md" className="spin" /> : <TraceIcon role="action.configure" size="md" />}
            Run all 5
          </button>
          <button
            type="button"
            className="primary-button"
            onClick={onRunSelected}
            disabled={!canRunSelected || loading}
          >
            {loading ? <TraceIcon role="status.loading" size="md" className="spin" /> : <TraceIcon role="action.run" size="md" />}
            Run selected
          </button>
        </div>
      ) : (
        <button
          type="button"
          className="primary-button"
          onClick={onContinue}
          disabled={!canContinue || loading}
        >
          Continue
          <TraceIcon role="action.next" size="sm" />
        </button>
      )}
    </div>
  );
}

function CompareSetupPreview({
  activeStep,
  step,
  cohort,
  repositoryDataset,
  endpoint,
  expressionScale,
  genes,
  methods,
  activeFilterCount,
  form,
  plotEditorTarget,
  running,
  plotEditorOpen,
}) {
  const titles = {
    dataset: cohort ? "Shared analysis frame" : "Choose a cohort",
    markers: genes.length ? "Matrix rows" : "Add molecular markers",
    methods: methods.length ? "Comparison design" : "Choose matrix columns",
    filters: activeFilterCount ? "Restricted clinical design" : "Patient filters and adjustment",
    run: "Execution review",
  };
  const filterLabels = analysisFilterLabels(form.filters);
  const jobCount = genes.length * methods.length;

  if (running) {
    return (
      <div className="analysis-setup-preview compare-setup-preview is-running">
        <header className="analysis-preview-header">
          <ModuleIcon role="module.plotOutput" />
          <div>
            <span>Batch analysis</span>
            <h2>Computing comparison matrix</h2>
          </div>
          <TraceIcon role="status.loading" size="lg" className="spin" label="Running comparison analyses" />
        </header>
        <div className="compare-running-preview">
          <div className="analysis-loader" aria-hidden="true">
            {Array.from({ length: 5 }, (_, index) => <span key={index} />)}
          </div>
          <strong>{genes.length} genes × {methods.length} methods</strong>
          <p>The batch may wait in the compute queue. Results will appear when it finishes.</p>
          <ElapsedTime />
        </div>
        <footer className="analysis-preview-note">
          BH and Bonferroni adjustment are calculated after all successful cells return.
        </footer>
      </div>
    );
  }

  return (
    <div className={`analysis-setup-preview compare-setup-preview preview-${step.id}`}>
      <header className="analysis-preview-header">
        <ModuleIcon role={step.iconRole} />
        <div>
          <span>Step {activeStep + 1} of {COMPARE_WORKFLOW_STEPS.length}</span>
          <h2>{titles[step.id]}</h2>
        </div>
      </header>

      {step.id === "dataset" && (
        cohort ? (
          <div className="analysis-context-preview compare-dataset-preview">
            <div className="analysis-preview-lead">
              <span>{repositoryDataset?.source_accession || cohort.id}</span>
              <h3>{repositoryDataset?.name || getCohortName(cohort.id)}</h3>
              <p>
                {repositoryDataset?.cohort_context
                  || cohort.primary_site
                  || "Primary site not reported"}
              </p>
            </div>
            <div className="analysis-preview-metrics">
              <PreviewItem label="Endpoint" value={endpoint?.label || "Pending"} />
              <PreviewItem label="Events" value={formatInteger(endpoint?.events)} />
              <PreviewItem label="Expression data" value={expressionScale?.label || "Pending"} />
            </div>
          </div>
        ) : (
          <PreviewPrompt
            iconRole="module.dataset"
            title="Select a cancer and analysis source"
            text="Every cell in the comparison matrix uses the same cohort, endpoint and expression scale."
          />
        )
      )}

      {step.id === "markers" && (
        <div className="analysis-context-preview">
          <div className="analysis-preview-lead">
            <span>{genes.length ? `${genes.length} matrix row${genes.length === 1 ? "" : "s"}` : "Rows pending"}</span>
            <h3>Gene-by-gene analyses</h3>
            <p>Each marker is analyzed separately against every selected cutpoint method.</p>
          </div>
          <GenePreviewGroup
            label={genes.length ? "Selected markers" : "No markers selected"}
            genes={genes}
            method="single gene"
          />
        </div>
      )}

      {step.id === "methods" && (
        <CompareMatrixBlueprint genes={genes} methods={methods} />
      )}

      {step.id === "filters" && (
        <div className="analysis-context-preview">
          <div className="analysis-preview-lead">
            <span>{activeFilterCount ? `${activeFilterCount} active` : "No restrictions"}</span>
            <h3>{activeFilterCount ? "Shared filtered population" : "Default eligibility"}</h3>
            <p>
              The same eligibility criteria and {formatAdjustmentSummary(
                form.adjustment_covariates,
                form.external_adjustment_covariates,
                form.external_covariates,
              ).toLowerCase()} are applied to every matrix cell.
            </p>
          </div>
          <div className="clinical-preview-groups">
            <PreviewChipGroup
              label="Eligibility"
              values={filterLabels}
              empty="All available clinical values"
            />
            <PreviewChipGroup
              label="Cox adjustment"
              values={[
                ...adjustmentCovariateLabels(form.adjustment_covariates),
                ...externalAdjustmentCovariateLabels(
                  form.external_adjustment_covariates,
                  form.external_covariates,
                ),
              ]}
              empty="No additional adjustment"
            />
          </div>
        </div>
      )}

      {step.id === "run" && (
        <div className="compare-review-preview">
          {plotEditorOpen && <PlotStylePreview
            form={form}
            isCombinedMode={false}
            plotTitlePlaceholder={`${genes[0] || "Gene"} · ${methods[0]?.label || "Cutpoint method"}`}
            previewContext="compare"
            previewGene={genes[0] || "Gene"}
            previewMethod={methods[0]?.label || "Cutpoint method"}
            previewTarget={plotEditorTarget}
          />}
          <div className="compare-execution-facts">
            <PreviewItem label="Analyses" value={formatInteger(jobCount)} />
            <PreviewItem label="Multiplicity" value="BH + Bonferroni" />
            <PreviewItem
              label="Adjusted forest"
              value={formatMultivariableForestSelection(form.plot_style)}
            />
            <PreviewItem
              label="Plot aspect"
              value={plotEditorTarget === "cox_forest" ? "By model count" : formatLabel(form.plot_style.plot_aspect)}
            />
          </div>
          <CompareMatrixBlueprint genes={genes} methods={methods} compact />
          <div className="compare-run-modes">
            <div>
              <strong>Run selected</strong>
              <span>{methods.length} current columns · {jobCount} analyses</span>
            </div>
            <div>
              <strong>Run all 5</strong>
              <span>All two-group methods · {genes.length * DICHOTOMIZATION_METHODS.length} analyses</span>
            </div>
          </div>
        </div>
      )}

      <footer className="analysis-preview-note">
        {step.id === "run"
          ? "Illustrative plot preview only. Effect estimates and adjusted p-values are computed after execution."
          : "Configuration preview only. Curves, effect estimates and adjusted p-values are computed after execution."}
      </footer>
    </div>
  );
}

function CompareMatrixBlueprint({ genes, methods, compact = false }) {
  const previewGenes = genes.slice(0, compact ? 3 : 5);
  const previewMethods = methods.slice(0, compact ? 4 : 6);
  const hiddenGenes = Math.max(0, genes.length - previewGenes.length);
  const hiddenMethods = Math.max(0, methods.length - previewMethods.length);

  return (
    <div className={`compare-blueprint${compact ? " compact" : ""}`}>
      <div className="analysis-preview-lead">
        <span>{genes.length * methods.length} planned analyses</span>
        <h3>Genes × cutpoint methods</h3>
        <p>Each row is a gene; each column is a rule for dividing patients into expression groups.</p>
      </div>
      {genes.length && methods.length ? (
        <div
          className="compare-blueprint-grid"
          style={{ "--compare-column-count": previewMethods.length }}
          aria-label={`${genes.length} genes by ${methods.length} cutpoint methods`}
        >
          <span className="compare-blueprint-corner" aria-hidden="true">Gene</span>
          {previewMethods.map((method) => <strong key={method.value}>{method.label}</strong>)}
          {previewGenes.flatMap((gene) => [
            <strong className="compare-blueprint-gene" key={`${gene}-label`}>{gene}</strong>,
            ...previewMethods.map((method) => (
              <span key={`${gene}-${method.value}`} aria-label={`${gene}, ${method.label}`}>
                <i aria-hidden="true" />
              </span>
            )),
          ])}
        </div>
      ) : (
        <PreviewPrompt
          iconRole="module.cohortTable"
          title="Matrix structure pending"
          text="Add at least one gene and one cutpoint method to define the comparison grid."
        />
      )}
      {(hiddenGenes > 0 || hiddenMethods > 0) && (
        <span className="compare-blueprint-overflow">
          {hiddenGenes ? `+${hiddenGenes} rows` : ""}
          {hiddenGenes && hiddenMethods ? " · " : ""}
          {hiddenMethods ? `+${hiddenMethods} columns` : ""}
        </span>
      )}
    </div>
  );
}

function CompareAdjustedEstimate({ models = [], prefix = "", requested }) {
  const selected = requestedAdjustedModel(models, prefix, requested);
  const label = prefix ? formatContinuousModelLabel : formatCoxModelLabel;
  const alternatives = (models || []).filter((model) => model.model !== selected?.model
    && !["univariable", "continuous_univariable"].includes(model.model));
  return <>
    {selected?.status === "completed" ? formatHrValues(selected) : selected ? "Not estimable" : "Not requested"}
    <small className="table-secondary">{selected?.status === "completed"
      ? `${label(selected)} · p ${formatP(selected.p_value)}`
      : selected ? formatModelStatus(selected) : "No clinical adjustment requested"}</small>
    {alternatives.length > 0 && <details className="compare-model-alternatives">
      <summary>Other fitted models</summary>
      {alternatives.map((model) => <p key={model.model}>{label(model)}: {model.status === "completed"
        ? `${formatHrValues(model)} · p ${formatP(model.p_value)}` : formatModelStatus(model)}</p>)}
    </details>}
  </>;
}

function ContinuousReferenceSummary({ rows, onDownload }) {
  const byGene = new Map();
  rows.forEach((row) => {
    const continuous = row.result?.metrics?.continuous_analysis;
    if (continuous?.status !== "completed") return;
    const primary = findCoxModel(continuous.linear_models, "continuous_univariable");
    const requestedModel = requestedAdjustedModel(continuous.linear_models, "continuous_", row.adjustmentRequested);
    const adjusted = requestedModel?.status === "completed" ? requestedModel : null;
    const candidate = {
      gene: row.gene,
      continuous,
      primary,
      adjusted,
      adjustmentRequested: Boolean(requestedModel),
      spline: continuous.spline || {},
      downloads: row.result?.downloads || {},
      inconsistent: false,
    };
    const current = byGene.get(row.gene);
    if (!current) {
      byGene.set(row.gene, candidate);
      return;
    }
    const fields = [
      [current.continuous.n_patients, candidate.continuous.n_patients],
      [current.continuous.n_events, candidate.continuous.n_events],
      [current.primary?.hazard_ratio, candidate.primary?.hazard_ratio],
      [current.primary?.p_value, candidate.primary?.p_value],
      [current.spline?.nonlinearity_p_value, candidate.spline?.nonlinearity_p_value],
    ];
    if (fields.some(([left, right]) => !numbersEquivalent(left, right))) {
      current.inconsistent = true;
    }
  });
  const references = Array.from(byGene.values());
  if (!references.length) return null;

  return (
    <section className="detail-section compare-continuous-reference">
      <div className="table-scroll" role="region" aria-label="Scrollable continuous reference" tabIndex={0}>
      <table aria-label="Continuous survival reference by gene">
        <thead>
          <tr>
            <th scope="col">Gene</th>
            <th scope="col">n / events</th>
            <th scope="col">HR per +1 SD</th>
            <th scope="col">Linear p</th>
            <th scope="col">Adjusted HR</th>
            <th scope="col">Nonlinearity p</th>
            <th scope="col">Marker PH p</th>
            <th scope="col">Profile</th>
          </tr>
        </thead>
        <tbody>
          {references.map((item) => (
            <tr key={item.gene}>
              <th scope="row">{item.gene}</th>
              <td>{formatInteger(item.continuous.n_patients)} / {formatInteger(item.continuous.n_events)}</td>
              <td>{formatHrValues(item.primary)}</td>
              <td>{formatP(item.primary?.p_value)}</td>
              <td>
                <CompareAdjustedEstimate models={item.continuous.linear_models} prefix="continuous_" requested={item.adjustmentRequested} />
              </td>
              <td>{formatP(item.spline?.nonlinearity_p_value)}</td>
              <td>{formatP(item.adjustmentRequested ? item.adjusted?.ph_p_value : item.primary?.ph_p_value)}
                <small className="table-secondary">{item.adjustmentRequested ? "Requested adjustment" : "Unadjusted"}</small>
              </td>
              <td>
                {item.inconsistent ? (
                  <span className="evidence-badge caution">Population mismatch</span>
                ) : (
                  <div className="mini-downloads">
                    <MiniDownloadButton href={item.downloads.continuous_png} label="PNG" onDownload={onDownload} />
                    <MiniDownloadButton href={item.downloads.continuous_svg} label="SVG" onDownload={onDownload} />
                  </div>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      </div>
      <div className="method-note">
        Repeated cutpoint cells for the same gene must reproduce this reference. Outer quartiles may reduce grouped n, but cannot change the continuous population.
      </div>
    </section>
  );
}

function ComparePlotMatrix({ rows, genes, methods, running, onDownload }) {
  const t = useHelpText();
  if (!rows.length && !running) {
    return <div className="empty-plot"><ModuleIcon role="module.cohortTable" /><p>Comparison results will appear after running multiple genes or cutpoint methods.</p></div>;
  }
  const rowByKey = Object.fromEntries(rows.map((row) => [`${row.gene}::${row.method}`, row]));
  return (
    <div className="compare-matrix-scroll" role="region" aria-label="Scrollable gene and cutpoint comparison matrix" tabIndex={0}>
      <table className="compare-matrix-table" aria-label="Gene by cutpoint comparison matrix">
        <thead>
          <tr>
            <th scope="col">Gene</th>
            {methods.map((method) => (
              <th scope="col" key={method.value}>
                <strong>{method.label}</strong>
                <span>{method.value === "unknown" ? "Method not recorded" : t.caption(`cutpoint.${method.value}`)}</span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {genes.map((gene) => (
            <tr key={gene}>
              <th scope="row">{gene}</th>
              {methods.map((method) => (
                <td key={`${gene}-${method.value}`}>
                  <ComparePlotCell row={rowByKey[`${gene}::${method.value}`]} running={running} onDownload={onDownload} />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      <div className="method-note">
        Not reached means the Kaplan-Meier curve did not fall below 50% during follow-up.
      </div>
    </div>
  );
}

function ComparePlotCell({ row, running, onDownload }) {
  if (!row) {
    return (
      <div className="compare-cell-pending">
        {running ? <TraceIcon role="status.loading" size="md" className="spin" /> : <TraceIcon role="data.table" size="md" />}
        <span>{running ? "Waiting" : "Not run"}</span>
      </div>
    );
  }
  if (row.error) {
    return (
      <div className="compare-cell-error">
        <TraceIcon role="status.error" size="md" tone="error" />
        <span>{row.error}</span>
      </div>
    );
  }
  const metrics = row.result?.metrics || {};
  const downloads = row.result?.downloads || {};
  const continuousPrimary = findCoxModel(
    metrics.continuous_analysis?.linear_models,
    "continuous_univariable"
  );
  return (
    <div className="compare-plot-cell">
      <img
        className="compare-plot-thumb"
        src={apiUrl(downloads.png)}
        alt={`${row.gene} ${row.method} Kaplan-Meier plot`}
        loading="lazy"
      />
      <div className="compare-cell-metrics">
        <span>{row.method === "maxstat" ? "Maxstat corrected p" : "Log-rank p"} {formatP(row.p)}</span>
        <span>BH {formatP(row.bh)}</span>
        <span>Bonferroni {formatP(row.bonferroni)}</span>
        {row.method === "maxstat" && <span>Descriptive log-rank p {formatP(metrics.logrank_p_value)}</span>}
        <span>HR/SD {formatHrValues(continuousPrimary)}</span>
        <span>Grouped HR {formatHr(metrics)}</span>
        <span>RMST Δ {formatRmstDelta(metrics.rmst)}</span>
        <span>{formatInteger(metrics.n_patients)} pts / {formatInteger(metrics.n_events)} events</span>
      </div>
      <div className="mini-downloads">
        <MiniDownloadButton href={downloads.png} label="PNG" onDownload={onDownload} />
        <MiniDownloadButton href={downloads.svg} label="SVG" onDownload={onDownload} />
        <MiniDownloadButton href={downloads.csv} label="CSV" onDownload={onDownload} />
        <MiniDownloadButton href={downloads.txt} label="TXT" onDownload={onDownload} />
        <MiniDownloadButton href={downloads.zip} label="ZIP" onDownload={onDownload} />
      </div>
    </div>
  );
}

function CutpointRobustnessSummary({ rows, methods }) {
  const completed = rows.filter((row) => row.result?.metrics && DICHOTOMIZATION_METHODS.includes(row.method));
  if (!completed.length) return null;
  const methodLabels = Object.fromEntries(methods.map((method) => [method.value, method.label]));
  const summarized = completed.map((row) => ({
    ...row,
    evidenceProfile: cutpointEvidenceProfile(row),
  }));
  const lowBh = summarized.filter((row) => row.evidenceProfile.bhBelowAlpha);
  const markerPhCautions = summarized.filter((row) => row.evidenceProfile.markerPhFlagged);
  const rmstAvailable = summarized.filter((row) => row.evidenceProfile.rmstAvailable);
  const genes = Array.from(new Set(summarized.map((row) => row.gene)));
  return (
    <div className="detail-section robustness-summary">
      <h3>Cutpoint evidence profile</h3>
      <div className="robustness-headline">
        <div>
          <span>Cutpoint analyses</span>
          <strong>{summarized.length}</strong>
        </div>
        <div>
          <span>BH q ≤ {ROBUSTNESS_ALPHA}</span>
          <strong>{lowBh.length} / {summarized.length}</strong>
        </div>
        <div>
          <span>Marker PH cautions</span>
          <strong>{markerPhCautions.length} / {summarized.length}</strong>
        </div>
        <div>
          <span>RMST evaluable</span>
          <strong>{rmstAvailable.length} / {summarized.length}</strong>
        </div>
      </div>
      <div className="table-scroll" role="region" aria-label="Scrollable cutpoint evidence" tabIndex={0}>
      <table aria-label="Cutpoint robustness estimates">
        <thead>
          <tr>
            <th scope="col">Gene</th>
            <th scope="col">Method</th>
            <th scope="col">n / events</th>
            <th scope="col">Group sizes</th>
            <th scope="col">BH q</th>
            <th scope="col">Univariable HR</th>
            <th scope="col">Adjusted HR</th>
            <th scope="col">RMST Δ at tau</th>
            <th scope="col">Marker PH p</th>
            <th scope="col">Prespecified 2-year effect</th>
            <th scope="col">Model PH p</th>
            <th scope="col">Unadjusted association</th>
            <th scope="col">Interpretation notes</th>
          </tr>
        </thead>
        <tbody>
          {summarized.map((row) => {
            const metrics = row.result.metrics || {};
            const profile = row.evidenceProfile;
            const univariable = findCoxModel(metrics.cox_models, "univariable");
            const requestedModel = requestedAdjustedModel(metrics.cox_models, "", row.adjustmentRequested);
            const diagnosticModel = requestedModel ? (requestedModel.status === "completed" ? requestedModel : null) : univariable;
            return (
              <tr key={`${row.gene}-${row.method}`}>
                <td>{row.gene}</td>
                <td>{methodLabels[row.method] || formatLabel(row.method)}</td>
                <td>{formatInteger(metrics.n_patients)} / {formatInteger(metrics.n_events)}</td>
                <td>{formatGroupCounts(metrics.group_counts)}</td>
                <td className={profile.bhBelowAlpha ? "evidence-cell supporting" : "evidence-cell neutral"}>
                  {formatP(row.bh)}
                </td>
                <td>
                  {formatHrValues(univariable)}
                  <small className="table-secondary">p {formatP(univariable?.p_value)}</small>
                </td>
                <td>
                  <CompareAdjustedEstimate models={metrics.cox_models} requested={row.adjustmentRequested} />
                </td>
                <td>
                  {formatRmstDelta(metrics.rmst)}
                  <small className="table-secondary">
                    {profile.rmstAvailable
                      ? `tau ${formatCompactNumber(metrics.rmst?.tau_days)} d · p ${formatP(metrics.rmst?.difference?.p_value)}`
                      : metrics.rmst?.reason || "Not evaluable"}
                  </small>
                </td>
                <td className={profile.markerPhFlagged ? "evidence-cell caution" : "evidence-cell neutral"}>
                  {formatP(diagnosticModel?.ph_p_value)}
                </td>
                <td>
                  {profile.temporalStatus === "completed" ? (
                    <>
                      <strong>0-2 y: {formatHrValues(profile.temporalEffect?.periods?.early)}</strong>
                      <small className="table-secondary">
                        After 2 y: {formatHrValues(profile.temporalEffect?.periods?.late)}
                      </small>
                    </>
                  ) : profile.temporalTriggered
                    ? <span title={profile.temporalEffect?.reason}>{formatModelStatus(profile.temporalEffect)}</span>
                    : "..."}
                </td>
                <td className={profile.globalPhFlagged ? "evidence-cell caution" : "evidence-cell neutral"}>
                  {formatP(diagnosticModel?.ph_global_p_value)}
                </td>
                <td>{profile.direction}</td>
                <td>
                  <div className="evidence-stack">
                    <span className={`evidence-badge ${profile.bhTone}`}>
                      {profile.bhLabel}
                    </span>
                    {profile.interpretationNotes.length > 0 && (
                      <small>{profile.interpretationNotes.join("; ")}</small>
                    )}
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      </div>
      <div className="method-note">
        {`These grouped estimates are sensitivity analyses against the continuous reference above. BH q-values cover valid grouped tests in this batch. Log-rank, grouped Cox and RMST are related summaries of the same outcomes, not independent votes. PH diagnostics inform interpretation, not exclusion. Maxstat grouped HR, confidence intervals and RMST remain post-selection.`}
      </div>
    </div>
  );
}

function MultiverseAnalysis({
  state,
  setState,
  form,
  cohorts,
  visibleCohorts,
  selectedCohort,
  cohortQuery,
  setCohortQuery,
  cohortPickerOpen,
  setCohortPickerOpen,
  onSelectCohort,
  repositoryDatasets,
  selectedRepositoryDataset,
  onSelectRepositoryDataset,
  endpointOptions,
  expressionScales,
  expressionScaleValue,
  onSelectExpressionScale,
  filters,
  activeFilterCount,
  updateForm,
  updateFilters,
  toggleFilterValue,
  clearFilter,
  suggestionCohort,
  onDownload,
  tutorialStepId = null,
}) {
  const t = useHelpText();
  const [step, setStep] = useState(0);
  const [geneQuery, setGeneQuery] = useState("");
  const geneSuggestionState = useGeneSuggestions(
    suggestionCohort,
    geneQuery,
    form.dataset_id,
    form.dataset_release_id,
    form.expression_layer_id,
  );
  const geneSuggestions = geneSuggestionState.genes;
  const stepPanelRef = useRef(null);

  useEffect(() => {
    if (!tutorialStepId) return;
    const nextStep = MULTIVERSE_WORKFLOW_STEPS.findIndex(({ id }) => id === tutorialStepId);
    if (nextStep >= 0 && nextStep !== step) setStep(nextStep);
  }, [tutorialStepId]);
  const effectiveGeneInput = geneQuery.trim()
    ? addGeneToken(state.genes, geneQuery)
    : state.genes;
  const genes = uniqueGeneSymbols(effectiveGeneInput);
  const selectedEndpoints = state.endpoints || [];
  const allEndpointsAvailable = selectedEndpoints.every((value) => endpointOptions.some((endpoint) => endpoint.value === value && endpoint.available));
  const selectedScoring = state.scoring_methods || [];
  const selectedCutpoints = state.cutpoint_methods || [];
  const planned = selectedEndpoints.length * selectedScoring.length * selectedCutpoints.length;
  const robustnessMarkerValidation = signatureInputState(effectiveGeneInput, {
    methods: selectedScoring,
    maximumGenes: ROBUSTNESS_GENE_MAX,
    label: "Robustness marker",
  });
  const robustnessExpressionLayer = form.dataset_id
    ? expressionScales.find((item) => item.value === expressionScaleValue)
    : null;
  const robustnessRankScoring = rankScoringAvailability(
    selectedRepositoryDataset,
    selectedCohort,
    robustnessExpressionLayer,
  );
  const unavailableRankMethodSelected = Boolean(
    !robustnessRankScoring.available
    && selectedScoring.some(signatureMethodUsesDirection),
  );
  const robustnessFiltersValidation = analysisFilterState(form.filters);
  const robustnessPlotValidation = plotStyleInputState(form.plot_style);
  const percentile = multiversePercentileState(
    selectedCutpoints,
    form.custom_percentile,
  );
  const percentileValid = percentile.valid;
  const markerReady = genes.length === 1
    ? selectedScoring.length === 1 && selectedScoring[0] === "single"
    : genes.length > 1 && selectedScoring.length > 0 && !selectedScoring.includes("single");
  const datasetReady = !selectedRepositoryDataset
    || datasetSupportsModule(selectedRepositoryDataset, "multiverse");
  const canRun = Boolean(
    form.cohort
      && datasetReady
      && (form.dataset_id || form.filters.sample_population)
      && genes.length
      && selectedEndpoints.length
      && allEndpointsAvailable
      && selectedScoring.length
      && selectedCutpoints.length
      && markerReady
      && robustnessMarkerValidation.valid
      && !unavailableRankMethodSelected
      && planned <= 72
      && percentileValid
      && robustnessFiltersValidation.valid
      && robustnessPlotValidation.valid
      && !state.running,
  );
  const completion = [
    Boolean(
      form.cohort
      && datasetReady
      && (form.dataset_id || form.filters.sample_population)
      && selectedEndpoints.length
      && allEndpointsAvailable
    ),
    markerReady && robustnessMarkerValidation.valid && !unavailableRankMethodSelected,
    Boolean(
      selectedScoring.length
      && selectedCutpoints.length
      && planned <= 72
      && percentileValid
    ),
    Boolean(form.cohort && markerReady && selectedEndpoints.length && selectedCutpoints.length),
    canRun,
  ];
  const requirements = [
    !form.cohort
      ? "Select a cancer cohort."
      : selectedEndpoints.length && allEndpointsAvailable
        ? ""
        : "Select at least one endpoint that passes cohort QC.",
    !genes.length
      ? "Add one gene or a multi-gene signature."
      : !robustnessMarkerValidation.valid
        ? robustnessMarkerValidation.errors[0]
        : unavailableRankMethodSelected
          ? robustnessRankScoring.reason
        : markerReady
          ? ""
        : "Use single scoring for one gene or signature scoring for two or more genes.",
    !selectedScoring.length
      ? "Select at least one scoring method."
      : !selectedCutpoints.length
        ? "Select at least one cutpoint method."
        : planned > 72
          ? "Reduce the family to 72 specifications or fewer."
          : !percentileValid
            ? "Enter a percentile threshold from 1 to 99."
            : !robustnessFiltersValidation.valid
              ? robustnessFiltersValidation.errors[0]
              : !robustnessPlotValidation.valid
                ? robustnessPlotValidation.errors[0]
                : "",
    form.cohort && markerReady && selectedEndpoints.length && selectedCutpoints.length
      ? ""
      : "Complete Dataset, Marker and Decisions first.",
    canRun ? "" : "Complete the declared family before execution.",
  ];
  const multiverseLedger = multiverseDesignLedger({
    datasetLabel: form.cohort ? getCohortName(form.cohort) : "",
    markerSummary: genes.length === 1
      ? genes[0]
      : genes.length
        ? `${genes.length}-gene signature`
        : "",
    endpointLabels: selectedEndpoints,
    scoringLabels: selectedScoring.map((value) => t.term(`score.${value}`)),
    cutpointLabels: selectedCutpoints.map((value) => t.term(`cutpoint.${value}`)),
    filterCount: activeFilterCount,
    adjustmentSummary: formatAdjustmentSummary(
      form.adjustment_covariates,
      form.external_adjustment_covariates,
      form.external_covariates,
    ),
    requirements: requirements.filter(Boolean),
  });
  const activeStep = MULTIVERSE_WORKFLOW_STEPS[step] || MULTIVERSE_WORKFLOW_STEPS[0];
  const summary = [
    form.cohort || "Cohort pending",
    genes.length === 1 ? genes[0] : genes.length ? `${genes.length}-gene signature` : "Marker pending",
    selectedEndpoints.length ? `${selectedEndpoints.length} endpoint${selectedEndpoints.length === 1 ? "" : "s"}` : "Endpoints pending",
    selectedScoring.length ? `${selectedScoring.length} score${selectedScoring.length === 1 ? "" : "s"}` : "Scores pending",
    selectedCutpoints.length ? `${selectedCutpoints.length} cutpoint${selectedCutpoints.length === 1 ? "" : "s"}` : "Cutpoints pending",
    `${planned} planned`,
  ].join(" · ");

  useEffect(() => {
    const required = genes.length <= 1 ? ["single"] : ["singscore", "zscore"];
    const current = state.scoring_methods || [];
    const invalid = genes.length <= 1
      ? current.length !== 1 || current[0] !== "single"
      : !current.length || current.includes("single");
    if (invalid) {
      setState((value) => ({ ...value, scoring_methods: required, result: null }));
    }
  }, [genes.length]);

  function updateState(key, value) {
    setState((current) => ({ ...current, [key]: value, result: null, error: "" }));
  }

  function toggleEndpoint(value) {
    updateState("endpoints", toggleListValue(selectedEndpoints, value));
  }

  function toggleScoring(value) {
    updateState("scoring_methods", toggleListValue(selectedScoring, value));
  }

  function toggleCutpoint(value) {
    updateState("cutpoint_methods", toggleListValue(selectedCutpoints, value));
  }

  function navigateStep(nextStep) {
    const bounded = Math.max(0, Math.min(MULTIVERSE_WORKFLOW_STEPS.length - 1, nextStep));
    setStep(bounded);
    window.requestAnimationFrame(() => {
      stepPanelRef.current?.focus({ preventScroll: true });
      document
        .getElementById(workflowStepControlId(MULTIVERSE_WORKFLOW_STEPS[bounded], "multiverse-step"))
        ?.scrollIntoView({ behavior: "auto", block: "nearest", inline: "center" });
    });
  }

  async function runMultiverse() {
    if (!canRun) {
      setState((current) => ({
        ...current,
        error: requirements.find(Boolean) || "The Robustness design is incomplete.",
      }));
      return;
    }
    const normalizedInput = geneInputTokens(effectiveGeneInput).join(", ");
    const payload = {
      cohort: form.cohort,
      dataset_id: form.dataset_id || null,
      dataset_release_id: form.dataset_release_id || null,
      expression_layer_id: form.expression_layer_id || null,
      genes: multiverseSignatureProjection(normalizedInput, selectedScoring),
      signature_name: genes.length > 1 ? state.session_label.trim() : "",
      endpoints: selectedEndpoints,
      scoring_methods: selectedScoring,
      cutpoint_methods: selectedCutpoints,
      expression_scale: form.expression_scale,
      custom_percentile: percentile.requestValue,
      filters: analysisFilterState(form.filters).value,
      adjustment_covariates: [...new Set(form.adjustment_covariates || [])],
      external_covariates: form.external_covariates || null,
      external_adjustment_covariates: [
        ...new Set(form.external_adjustment_covariates || []),
      ],
      time_unit: form.time_unit,
      show_confidence_interval: form.show_confidence_interval,
      plot_style: buildPlotStylePayload(form.plot_style),
      session_label: state.session_label.trim(),
    };
    setGeneQuery("");
    setState((current) => ({
      ...current,
      genes: normalizedInput,
      running: true,
      error: "",
    }));
    try {
      const result = await createMultiverseAnalysis(payload);
      setState((current) => ({ ...current, result, error: "" }));
    } catch (error) {
      setState((current) => ({
        ...current,
        error: formatError(error, { context: "Robustness" }),
      }));
    } finally {
      setState((current) => ({ ...current, running: false }));
    }
  }

  return (
    <section className="multiverse-page">
      <ActiveJobRecovery
        sourceView="multiverse"
        busy={state.running}
        onRecover={(result) => setState((current) => ({
          ...current,
          running: false,
          result,
          error: "",
        }))}
      />
      <div className="layout analysis-workflow-layout multiverse-workflow-layout">
        <section className="control-panel analysis-step-controls multiverse-step-controls" aria-label="Robustness across analysis choices controls">
          <AnalysisWorkflowStepper
            steps={MULTIVERSE_WORKFLOW_STEPS}
            activeStep={step}
            completion={completion}
            summary={summary}
            onSelect={navigateStep}
            idPrefix="multiverse-step"
            ariaLabel="Robustness across analysis choices setup"
            summaryLabel="Declared family"
          />
          <section
            ref={stepPanelRef}
            className="analysis-step-panel multiverse-step-panel"
            id={`multiverse-step-panel-${activeStep.id}`}
            aria-labelledby={workflowStepControlId(activeStep, "multiverse-step")}
            tabIndex={-1}
          >
            {activeStep.id === "dataset" && (
              <>
                <PanelHeader
                  iconRole="module.comparisonDataset"
                  title="Cohort and endpoints"
                  description="Choose all outcomes to include before running."
                  helpId="multiverse"
                />
                <div className="compare-control-grid">
                  <div className="compare-control-block">
                    <div className="compare-control-label"><span>Cohort</span></div>
                    <CohortPicker
                      cohorts={cohorts}
                      visibleCohorts={visibleCohorts}
                      selectedCohort={selectedCohort}
                      selectedCohortId={form.cohort}
                      query={cohortQuery}
                      setQuery={setCohortQuery}
                      open={cohortPickerOpen}
                      setOpen={setCohortPickerOpen}
                      onSelect={onSelectCohort}
                    />
                    <RepositorySourceSelector
                      selectedCohort={selectedCohort}
                      datasets={repositoryDatasets}
                      selectedDataset={selectedRepositoryDataset}
                      onSelect={onSelectRepositoryDataset}
                      analysisType="multiverse"
                    />
                <CohortAdjustmentNotice filters={filters} />
                    <MolecularPopulationSelector
                      form={form}
                      filters={filters}
                      compact
                      onChange={(value) => updateFilters("sample_population", value)}
                    />
                  </div>
                  <div className="compare-control-block wide">
                    <div className="compare-control-label">
                      <LabelWithHelp label="Endpoint family" helpId="survivalEndpoint" />
                      <strong>{selectedEndpoints.length} selected</strong>
                    </div>
                    <div className="multiverse-option-grid endpoint-family" aria-label="Endpoint family">
                      {endpointOptions.map((endpoint) => (
                        <button
                          key={endpoint.value}
                          type="button"
                          aria-pressed={selectedEndpoints.includes(endpoint.value)}
                          className={selectedEndpoints.includes(endpoint.value) ? "selected" : ""}
                          disabled={!endpoint.available && !selectedEndpoints.includes(endpoint.value)}
                          onClick={() => toggleEndpoint(endpoint.value)}
                          title={endpoint.available ? endpoint.reason || endpoint.source : endpoint.reason}
                        >
                          <strong>{endpoint.value}</strong>
                          <span>{endpoint.label}</span>
                          <small>{endpoint.available ? `${formatInteger(endpoint.patients)} patients · ${formatInteger(endpoint.events)} events` : "Does not pass QC"}</small>
                        </button>
                      ))}
                    </div>
                  </div>
                </div>
              </>
            )}

            {activeStep.id === "marker" && (
              <>
                <PanelHeader
                  iconRole="module.geneAnalysis"
                  title="Gene or signature"
                  description="One gene uses its expression directly; two or more genes unlock alternative signature scores."
                  helpId="geneMode"
                />
                <div className="compare-control-grid">
                  <GeneSelector
                    label="Genes"
                    value={state.genes}
                    onChange={(value) => updateState("genes", value)}
                    draft={geneQuery}
                    setDraft={setGeneQuery}
                    suggestions={geneSuggestions}
                    suggestionsLoading={geneSuggestionState.loading}
                    suggestionsError={geneSuggestionState.error}
                    placeholder="Type CDC20 or IFNG, CXCL9, CXCL10..."
                    helpId="multiverseGeneList"
                  />
                  {genes.length > 1 && (
                    <label className="field">
                      <span>Signature label</span>
                      <input
                        value={state.session_label}
                        maxLength={80}
                        onChange={(event) => updateState("session_label", event.target.value)}
                        placeholder="Optional biological label"
                      />
                    </label>
                  )}
                </div>
              </>
            )}

            {activeStep.id === "decisions" && (
              <>
                <PanelHeader
                  iconRole="module.specificationCurve"
                  title="Choose analysis combinations"
                  description="Choose the scoring and grouping methods to combine with each selected outcome."
                  helpId="multiverse"
                />
                <div className="multiverse-decision-stack">
                  <div className="compare-method-panel">
                    <div className="compare-control-label">
                      <LabelWithHelp label="Scoring methods" helpId="geneMode" />
                      <strong>{selectedScoring.length} selected</strong>
                    </div>
                    <div className="multiverse-option-grid" aria-label="Signature scoring methods">
                      {(genes.length <= 1
                        ? [{ value: "single", label: "Single gene" }]
                        : MULTI_GENE_SIGNATURE_METHOD_OPTIONS).map((method) => {
                        const rankUnavailable = signatureMethodUsesDirection(method.value)
                          && !robustnessRankScoring.available;
                        return (
                        <button
                          key={method.value}
                          type="button"
                          aria-pressed={selectedScoring.includes(method.value)}
                          className={selectedScoring.includes(method.value) ? "selected" : ""}
                          disabled={rankUnavailable}
                          onClick={() => toggleScoring(method.value)}
                          title={rankUnavailable ? robustnessRankScoring.reason : t.entry(`score.${method.value}`).does}
                        >
                          <strong>{method.shortLabel || method.label}</strong>
                          <span>{t.caption(`score.${method.value}`)}</span>
                        </button>
                        );
                      })}
                    </div>
                    {selectedScoring.some(signatureMethodUsesDirection) && (
                      <SignatureInputSummary
                        method={selectedScoring.find(signatureMethodUsesDirection)}
                        value={effectiveGeneInput}
                      />
                    )}
                    {robustnessMarkerValidation.warnings.map((warning) => (
                      <p
                        className="signature-projection-warning"
                        role="note"
                        key={warning}
                      >
                        {warning}
                      </p>
                    ))}
                  </div>
                  <div className="compare-method-panel">
                    <div className="compare-control-label">
                      <LabelWithHelp label="Cutpoint methods" helpId="compareRobustness" />
                      <strong>{selectedCutpoints.length} selected</strong>
                    </div>
                    <div className="method-grid compact">
                      {CUTPOINTS.map((method) => (
                        <button
                          key={method.value}
                          type="button"
                          aria-pressed={selectedCutpoints.includes(method.value)}
                          className={selectedCutpoints.includes(method.value) ? "selected" : ""}
                          onClick={() => toggleCutpoint(method.value)}
                          title={t.entry(`cutpoint.${method.value}`).does}
                        >
                          <strong>{method.label}</strong>
                          <span>{t.caption(`cutpoint.${method.value}`)}</span>
                        </button>
                      ))}
                    </div>
                    {selectedCutpoints.includes("percentile") && (
                      <label className="field compare-percentile-field">
                        <span>Percentile threshold</span>
                        <input
                          type="number"
                          min="1"
                          max="99"
                          value={form.custom_percentile}
                          aria-invalid={!percentileValid || undefined}
                          aria-describedby={!percentileValid ? "multiverse-percentile-error" : undefined}
                          onChange={(event) => updateForm("custom_percentile", event.target.value)}
                        />
                        {!percentileValid && (
                          <small id="multiverse-percentile-error" className="field-error">
                            Enter a value from 1 to 99.
                          </small>
                        )}
                      </label>
                    )}
                  </div>
                  <div className="compare-control-block wide">
                    <ExpressionDataSelector options={expressionScales} value={expressionScaleValue} onChange={onSelectExpressionScale} />
                  </div>
                </div>
              </>
            )}

            {activeStep.id === "clinical" && (
              <>
                <PanelHeader
                  iconRole="module.clinicalFilters"
                  title="Patient filters and adjustment"
                  description="All analyses use the same patient eligibility rules and selected adjustment."
                  helpId={["clinicalFilters", "clinicalAdjustment"]}
                />
                <div className="compare-filter-grid">
                  <div className="clinical-section-heading">
                    <strong>Eligibility filters</strong>
                    <span>{activeFilterCount ? `${activeFilterCount} active` : "All eligible patients"}</span>
                  </div>
                  <FilterGroup
                    title="Sample type"
                    values={filters?.sample_types || []}
                    selected={form.filters.sample_types}
                    onToggle={(value) => toggleFilterValue("sample_types", value)}
                    onClear={() => clearFilter("sample_types")}
                  />
                  <FilterGroup
                    title="Stage"
                    values={filters?.stages || []}
                    selected={form.filters.stages}
                    onToggle={(value) => toggleFilterValue("stages", value)}
                    onClear={() => clearFilter("stages")}
                  />
                  <FilterGroup
                    title="Grade"
                    values={filters?.grades || []}
                    selected={form.filters.grades}
                    onToggle={(value) => toggleFilterValue("grades", value)}
                    onClear={() => clearFilter("grades")}
                    showWhenEmpty
                    emptyLabel="No grade metadata for this cohort"
                  />
                  <FilterGroup
                    title="Gender"
                    values={filters?.genders || []}
                    selected={form.filters.genders}
                    onToggle={(value) => toggleFilterValue("genders", value)}
                    onClear={() => clearFilter("genders")}
                  />
                  <FilterGroup
                    title="Race"
                    values={filters?.races || []}
                    selected={form.filters.races}
                    onToggle={(value) => toggleFilterValue("races", value)}
                    onClear={() => clearFilter("races")}
                  />
                  <div className="range-grid">
                    <label className="field">
                      <span>Min age</span>
                      <input type="number" min="0" max="150" step="any" value={form.filters.age_min} onChange={(event) => updateFilters("age_min", event.target.value)} />
                    </label>
                    <label className="field">
                      <span>Max age</span>
                      <input type="number" min="0" max="150" step="any" value={form.filters.age_max} onChange={(event) => updateFilters("age_max", event.target.value)} />
                    </label>
                    <label className="field wide">
                      <span>Maximum follow-up days</span>
                      <input type="number" min="1" step="any" value={form.filters.max_time_days} onChange={(event) => updateFilters("max_time_days", event.target.value)} />
                    </label>
                  </div>
                  {!robustnessFiltersValidation.valid && (
                    <p className="field-error" role="alert">
                      {robustnessFiltersValidation.errors[0]}
                    </p>
                  )}
                  <ClinicalFilterControls
                    variables={filters?.clinical_grouping_variables || []}
                    value={form.filters.custom_filters || []}
                    onChange={(value) => updateFilters("custom_filters", value)}
                    analysisContext="survival"
                  />
                  <ClinicalAdjustmentSelector
                    selected={form.adjustment_covariates || []}
                    filters={filters}
                    onToggle={(value) =>
                      updateForm(
                        "adjustment_covariates",
                        toggleListValue(form.adjustment_covariates || [], value),
                      )
                    }
                    externalDataset={form.external_covariates}
                    externalSelected={form.external_adjustment_covariates || []}
                    onExternalChange={(dataset, values) => {
                      updateForm("external_covariates", dataset);
                      updateForm("external_adjustment_covariates", values);
                    }}
                  />
                </div>
              </>
            )}

            {activeStep.id === "run" && (
              <>
                <PanelHeader
                  iconRole="module.plotOutput"
                  title="Freeze and execute"
                  description={`${planned} planned analyses. The record includes any that fail.`}
                  helpId="multiverse"
                />
                <div className="multiverse-family-review">
                  <div>
                    <span>Continuous primary family</span>
                    <strong>{selectedEndpoints.length * selectedScoring.length} tests</strong>
                    <p>One Cox model per endpoint and scoring method. Repeated cutpoints are deduplicated.</p>
                  </div>
                  <div>
                    <span>Grouped sensitivity family</span>
                    <strong>{planned} tests</strong>
                    <p>One endpoint by scoring by cutpoint specification. Maxstat uses its corrected p-value.</p>
                  </div>
                </div>
                <div className="analysis-final-review">
                  <strong>No binary verdict</strong>
                  <span>BH and Bonferroni are calculated separately inside the two declared families. PH remains an interpretation diagnostic.</span>
                </div>
              </>
            )}
          </section>
          <DesignLedger
            title="This Robustness analysis"
            ledger={multiverseLedger}
            requirementsId="multiverse-design-requirements"
          />

          <MultiverseStepActions
            activeStep={step}
            totalSteps={MULTIVERSE_WORKFLOW_STEPS.length}
            canContinue={completion[step]}
            requirement={requirements[step]}
            running={state.running}
            canRun={canRun}
            onBack={() => navigateStep(step - 1)}
            onContinue={() => navigateStep(step + 1)}
            onRun={runMultiverse}
          />
        </section>

        <section className="result-panel previewing multiverse-preview-panel" aria-live="polite">
          <MultiverseSetupPreview
            step={activeStep}
            cohort={selectedCohort}
            repositoryDataset={selectedRepositoryDataset}
            genes={genes}
            endpoints={selectedEndpoints}
            scoring={selectedScoring}
            cutpoints={selectedCutpoints}
            planned={planned}
            running={state.running}
            adjustment={form.adjustment_covariates || []}
            externalAdjustment={form.external_adjustment_covariates || []}
            externalDataset={form.external_covariates}
          />
        </section>
      </div>
      {state.error && (
        <div className="error-box">
          <TraceIcon role="status.error" size="md" tone="error" />
          <div>
            <strong>Robustness could not start</strong>
            <span>{state.error}</span>
          </div>
        </div>
      )}
      {state.result && <MultiverseResult result={state.result} onDownload={onDownload} />}
    </section>
  );
}

function MultiverseStepActions({
  activeStep,
  totalSteps,
  canContinue,
  requirement,
  running,
  canRun,
  onBack,
  onContinue,
  onRun,
}) {
  const isFirst = activeStep === 0;
  const isLast = activeStep === totalSteps - 1;
  return (
    <div className="analysis-step-actions">
      <button type="button" className="secondary-button" onClick={onBack} disabled={isFirst || running}>
        <TraceIcon role="action.back" size="sm" />
        Back
      </button>
      <span className={requirement ? "analysis-step-requirement" : "analysis-step-position"} aria-live="polite">
        {requirement || `Step ${activeStep + 1} of ${totalSteps}`}
      </span>
      {isLast ? (
        <button type="button" className="primary-button" onClick={onRun} disabled={!canRun || running}>
          {running ? <TraceIcon role="status.loading" size="md" className="spin" /> : <TraceIcon role="action.run" size="md" />}
          {running ? "Running family" : "Run Robustness"}
        </button>
      ) : (
        <button type="button" className="primary-button" onClick={onContinue} disabled={!canContinue || running}>
          Continue
          <TraceIcon role="action.next" size="sm" />
        </button>
      )}
    </div>
  );
}

function MultiverseSetupPreview({
  step,
  cohort,
  repositoryDataset,
  genes,
  endpoints,
  scoring,
  cutpoints,
  planned,
  running,
  adjustment,
  externalAdjustment,
  externalDataset,
}) {
  return (
    <div className={`analysis-setup-preview multiverse-setup-preview${running ? " is-running" : ""}`}>
      <header className="analysis-preview-header">
        <ModuleIcon role="module.specificationCurve" />
        <div>
          <span>{running ? "Running planned analyses" : "Declared analysis family"}</span>
          <h2>
            {cohort
              ? `${repositoryDataset?.source_accession || cohort.id} robustness analysis`
              : "Build a robustness analysis"}
          </h2>
        </div>
        {running && <TraceIcon role="status.loading" size="lg" className="spin" label="Running Robustness" />}
      </header>
      {running && <ElapsedTime />}
      <div className="multiverse-preview-count">
        <strong>{planned}</strong>
        <span>endpoint × score × cutpoint specifications</span>
      </div>
      <div className="multiverse-preview-equation" aria-label={`${endpoints.length} endpoints times ${scoring.length} scoring methods times ${cutpoints.length} cutpoints`}>
        <span><strong>{endpoints.length}</strong> endpoints</span>
        <i aria-hidden="true">×</i>
        <span><strong>{scoring.length}</strong> scores</span>
        <i aria-hidden="true">×</i>
        <span><strong>{cutpoints.length}</strong> cutpoints</span>
      </div>
      <div className="multiverse-preview-ledger" aria-hidden="true">
        {Array.from({ length: Math.min(24, Math.max(0, planned)) }, (_, index) => (
          <span key={index} style={{ "--ledger-index": index }} />
        ))}
      </div>
      <div className="analysis-preview-metrics">
        <PreviewItem label="Marker" value={genes.length === 1 ? genes[0] : genes.length ? `${genes.length} genes` : "Pending"} />
        <PreviewItem label="Endpoints" value={endpoints.join(", ") || "Pending"} />
        <PreviewItem
          label="Adjustment"
          value={formatAdjustmentSummary(
            adjustment,
            externalAdjustment,
            externalDataset,
          )}
        />
      </div>
      <div className="multiverse-preview-family">
        <div>
          <strong>{endpoints.length * scoring.length}</strong>
          <span>continuous tests</span>
        </div>
        <div>
          <strong>{planned}</strong>
          <span>grouped sensitivities</span>
        </div>
      </div>
      <footer className="analysis-preview-note">
        {step.id === "run"
          ? "The run keeps every planned combination and records whether it completed, lacked usable data or failed."
          : "The preview counts all selected combinations. Completed and failed analyses will remain in the results."}
      </footer>
    </div>
  );
}

function MultiverseResult({ result, onDownload }) {
  const summary = result.summary || {};
  const family = result.analysis_family || {};
  const downloads = result.downloads || {};
  const specifications = result.specifications || [];
  const references = result.continuous_references || [];
  const scoringContracts = (family.signature_scoring_contracts || [])
    .filter((item) => item.signature_scoring)
    .map((item) => ({
      id: item.reference_id,
      label: `${item.endpoint} · ${signatureMethodDefinition(item.scoring_method).shortLabel}`,
      signature: item.signature_scoring,
    }));
  return (
    <GuideAnchor
      anchor={GUIDE_ANCHORS.MULTIVERSE_RESULTS}
      label="Robustness analysis result"
      className="multiverse-results"
    >
      <header className="multiverse-result-header">
        <div>
          <span>Session <code>{result.session_id}</code></span>
          <h2>Analysis choices compared</h2>
          <p>{summary.completed} completed and {summary.failed} failed or unavailable of {summary.planned} planned specifications.</p>
        </div>
        <span className={`evidence-badge ${summary.failed ? "caution" : "informative"}`}>
          {summary.failed ? "Completed with gaps" : "All analyses recorded"}
        </span>
      </header>
      <div className="multiverse-result-actions" aria-label="Robustness downloads">
        <MiniDownloadButton href={downloads.svg} label="Curve SVG" onDownload={onDownload} />
        <MiniDownloadButton href={downloads.csv} label="Specs CSV" onDownload={onDownload} />
        <MiniDownloadButton href={downloads.continuous_csv} label="Continuous CSV" onDownload={onDownload} />
        <MiniDownloadButton href={downloads.ledger} label="Ledger JSON" onDownload={onDownload} />
        <MiniDownloadButton href={downloads.audit_html} label="Audit HTML" onDownload={onDownload} />
        <MiniDownloadButton href={downloads.attestation} label="Signed receipt" onDownload={onDownload} />
        <MiniDownloadButton href={downloads.zip} label="Bundle ZIP" onDownload={onDownload} />
      </div>
      <div className="multiverse-family-strip">
        <div>
          <span>Continuous analyses</span>
          <strong>{summary.continuous_tests} evaluable</strong>
          <small>{family.primary_continuous_family?.unit}</small>
        </div>
        <div>
          <span>Grouped sensitivities</span>
          <strong>{summary.grouped_tests} evaluable</strong>
          <small>{family.grouped_sensitivity_family?.unit}</small>
        </div>

      </div>
      <AnalysisNotices
        warnings={result.warnings}
        includeModelDiagnostics={false}
      />

      <ResultTabs label="Robustness result sections">
      <ResultSection id="continuous" title="Continuous models" helpId="multiverseLedger">
      <section className="detail-section multiverse-continuous">

        <div className="table-scroll" role="region" aria-label="Scrollable continuous Robustness results" tabIndex={0}>
          <table aria-label="Robustness reference estimates">
            <thead>
              <tr>
                <th scope="col">Endpoint</th>
                <th scope="col">Scoring</th>
                <th scope="col">n / events</th>
                <th scope="col">Model</th>
                <th scope="col">HR per +1 SD</th>
                <th scope="col">p</th>
                <th scope="col">BH q</th>
                <th scope="col">Marker PH p</th>
                <th scope="col">Information</th>
              </tr>
            </thead>
            <tbody>
              {references.map((reference) => {
                const effect = reference.effect || {};
                return (
                  <tr key={reference.reference_id}>
                    <th scope="row">{reference.endpoint}</th>
                    <td>{signatureMethodDefinition(reference.scoring_method).shortLabel}</td>
                    <td>{formatInteger(reference.n_patients)} / {formatInteger(reference.n_events)}</td>
                    <td>
                      {effect.label || formatLabel(effect.model)}
                      <small className="table-secondary">{formatEstimator(effect.display_estimator)}</small>
                    </td>
                    <td>{formatMultiverseEffect(effect)}</td>
                    <td>{formatP(effect.standard_p_value)}</td>
                    <td>{formatP(reference.continuous_bh_q_value)}</td>
                    <td>{formatP(effect.ph_p_value)}</td>
                    <td>{formatInformationStatus(effect)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>

      </ResultSection>
      <ResultSection id="curve" title="Grouped robustness" helpId="multiverseCurve">
      <section className="detail-section multiverse-curve-section">

        <div className="multiverse-curve-scroll" role="region" aria-label="Scrollable Robustness curve" tabIndex={0}>
          <img
            src={apiUrl(downloads.svg)}
            alt={`Robustness curve for ${summary.completed} completed of ${summary.planned} planned analyses`}
          />
        </div>
      </section>

      </ResultSection>
      <ResultSection id="ledger" title="All specifications" helpId="multiversePlannedCells">
        <div>
          <span>Family hash</span>
          <code>{result.audit?.family_reproducibility_hash?.slice(0, 18)}…</code>
          <small>No automatic selection of a preferred result</small>
        </div>
      <section className="detail-section multiverse-ledger-section">

        <div className="table-scroll" role="region" aria-label="Scrollable Robustness execution ledger" tabIndex={0}>
          <table aria-label="Robustness specification results">
            <thead>
              <tr>
                <th scope="col">Spec</th>
                <th scope="col">Endpoint</th>
                <th scope="col">Scoring</th>
                <th scope="col">Cutpoint</th>
                <th scope="col">n / events</th>
                <th scope="col">Inference p</th>
                <th scope="col">BH q</th>
                <th scope="col">Displayed effect</th>
                <th scope="col">RMST Δ / tau</th>
                <th scope="col">Marker / model PH</th>
                <th scope="col">Status</th>
                <th scope="col">Audit</th>
              </tr>
            </thead>
            <tbody>
              {specifications.map((row) => {
                const effect = row.grouped_effect || {};
                return (
                  <tr key={row.specification_id}>
                    <th scope="row"><code>{row.specification_id}</code></th>
                    <td>{row.endpoint}</td>
                    <td>{signatureMethodDefinition(row.scoring_method).shortLabel}</td>
                    <td>{formatLabel(row.cutpoint_method)}</td>
                    <td>{formatInteger(row.n_patients)} / {formatInteger(row.n_events)}</td>
                    <td>
                      {formatP(row.inference_p_value)}
                      <small className="table-secondary">{formatLabel(row.inference_test)}</small>
                    </td>
                    <td>{formatP(row.grouped_bh_q_value)}</td>
                    <td>
                      {formatMultiverseEffect(effect)}
                      <small className="table-secondary">{formatEstimator(effect.display_estimator)}</small>
                    </td>
                    <td>
                      {formatSignedNumber(row.rmst?.estimate_days, 0)} d
                      <small className="table-secondary">tau {formatCompactNumber(row.rmst?.tau_days)} d</small>
                    </td>
                    <td>{formatP(row.marker_ph_p_value)} / {formatP(row.global_ph_p_value)}</td>
                    <td>
                      <span className={`evidence-badge ${row.status === "completed" ? "neutral" : "caution"}`}>
                        {formatLabel(row.status)}
                      </span>
                      {row.error && <small className="table-secondary">{row.error}</small>}
                    </td>
                    <td>
                      {row.downloads?.audit_html ? (
                        <MiniDownloadButton href={row.downloads.audit_html} label="Audit" onDownload={onDownload} />
                      ) : "…"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>
      <SignatureScoringCollectionSummary
        items={scoringContracts}
        title="Score settings"
        description="Each endpoint and scoring method has its own settings. Cutpoint comparisons reuse that continuous score."
      />
      </ResultSection>
      </ResultTabs>
      <div className="method-note">
        Continuous and grouped p-values are related summaries of the same outcomes and are not votes. Maxstat grouped HR and RMST remain post-selection. PH tests modify interpretation and never remove a specification from this ledger.
      </div>
    </GuideAnchor>
  );
}

function ExploratorySessionPage({
  session,
  exportState,
  setSession,
  setExportState,
  onExport,
  onDownload,
}) {
  const selectedEntries = session.entries.filter((entry) => entry.included);
  const pendingSelected = selectedEntries.filter(
    (entry) => !terminalSessionEntry(entry),
  );
  const completedEntries = session.entries.filter(
    (entry) => entry.job_status === "completed",
  );
  const canExport =
    selectedEntries.length > 0 &&
    pendingSelected.length === 0 &&
    !exportState.running;

  function startNewHistory() {
    if (
      session.entries.length &&
      !window.confirm("Start a new local run history and clear the current entries?")
    ) {
      return;
    }
    setSession((current) => beginNewSession(current));
    setExportState({ running: false, result: null, error: "" });
  }

  return (
    <GuideAnchor
      anchor={GUIDE_ANCHORS.SESSION_INTERPRETATION}
      label="How to interpret exploratory run history"
      className="session-history-page"
    >
      <GuideAnchor
        anchor={GUIDE_ANCHORS.SESSION_SETUP}
        label="Run history controls"
        className="session-control-band"
      >
        <header className="session-title-row">
          <PanelHeader
            iconRole="module.sessionHistory"
            title="Exploratory run history"
            description="Review analysis requests saved in this browser and the testing families in your export."
            helpId="sessionScope"
          />
          <label className="switch-field session-recording-switch">
            <input
              type="checkbox"
              checked={session.recording_enabled}
              onChange={(event) =>
                setSession((current) => ({
                  ...current,
                  recording_enabled: event.target.checked,
                }))
              }
            />
            <span aria-hidden="true" />
            <strong>{session.recording_enabled ? "Recording on" : "Recording off"}</strong>
          </label>
        </header>

        <div className="session-toolbar">
          <label className="field session-label-field">
            <span>Session label</span>
            <input
              value={session.session_label}
              maxLength="120"
              placeholder="Optional analysis checkpoint"
              onChange={(event) =>
                setSession((current) => ({
                  ...current,
                  session_label: event.target.value,
                }))
              }
            />
          </label>
          <div className="session-toolbar-actions">
            <button
              type="button"
              className="secondary-button"
              onClick={startNewHistory}
            >
              New history
            </button>
            <button
              type="button"
              className="primary-button"
              disabled={!canExport}
              onClick={onExport}
            >
              {exportState.running ? (
                <TraceIcon role="status.loading" size="md" className="spin" />
              ) : (
                <TraceIcon role="file.audit" size="md" />
              )}
              {exportState.running
                ? "Building record"
                : `Export selected (${selectedEntries.length})`}
            </button>
          </div>
        </div>

        <div className="session-scope-strip" aria-label="Run history status">
          <div>
            <span>Recorded</span>
            <strong>{session.entries.length}</strong>
          </div>
          <div>
            <span>Completed</span>
            <strong>{completedEntries.length}</strong>
          </div>
          <div>
            <span>Selected</span>
            <strong>{selectedEntries.length}</strong>
          </div>
          <div>
            <span>Storage</span>
            <strong>Browser local</strong>
          </div>
        </div>
        <p className="session-privacy-note">
          This browser record stores job references, not patient records or uploaded covariate values. When you export, TRACE sends the selected job references to the server.
        </p>
      </GuideAnchor>

      {exportState.error && (
        <div className="error-box">
          <TraceIcon role="status.error" size="md" tone="error" />
          <span>{exportState.error}</span>
        </div>
      )}

      <GuideAnchor
        anchor={GUIDE_ANCHORS.SESSION_LEDGER}
        label="Recorded exploratory runs"
        className="detail-section session-run-ledger"
      >
        <DetailSectionTitle
          title="Recorded runs"
          helpId="sessionEvents"
        />
        {!session.entries.length ? (
          <div className="session-empty-state">
            <ModuleIcon role="module.sessionHistory" />
            <strong>
              {session.recording_enabled
                ? "No compute jobs recorded in this history"
                : "Local recording is off"}
            </strong>
            <span>
              {session.recording_enabled
                ? "Accepted Survival, Compare, GSEA, Robustness and Pan-cancer jobs will appear here."
                : "Enable recording when a session-level exploratory record is required."}
            </span>
          </div>
        ) : (
          <div className="table-scroll" role="region" aria-label="Scrollable recorded run history" tabIndex={0}>
            <table className="session-run-table" aria-label="Recorded analysis jobs selected for export">
              <thead>
                <tr>
                  <th scope="col" className="session-select-column">Export</th>
                  <th scope="col">Run</th>
                  <th scope="col">Design</th>
                  <th scope="col">Status</th>
                  <th scope="col">Recorded</th>
                  <th scope="col">Server job</th>
                </tr>
              </thead>
              <tbody>
                {session.entries.map((entry) => (
                  <tr key={entry.event_id}>
                    <td className="session-select-column">
                      <input
                        type="checkbox"
                        checked={entry.included}
                        aria-label={`Include ${entry.label} in session export`}
                        onChange={(event) =>
                          setSession((current) =>
                            updateSessionEntry(current, entry.event_id, {
                              included: event.target.checked,
                            }),
                          )
                        }
                      />
                    </td>
                    <th scope="row">
                      {entry.label}
                      <small className="table-secondary">
                        {formatLabel(entry.source_view)}
                      </small>
                    </th>
                    <td>{entry.design_summary || "Server-resolved request"}</td>
                    <td>
                      <span
                        className={`evidence-badge ${
                          entry.job_status === "failed"
                            ? "caution"
                            : entry.job_status === "completed"
                              ? "informative"
                              : "neutral"
                        }`}
                      >
                        {formatLabel(entry.job_status)}
                      </span>
                    </td>
                    <td>{formatDateTime(entry.recorded_at)}</td>
                    <td>
                      <code>{entry.job_id.slice(0, 12)}…</code>
                      {entry.cached && (
                        <small className="table-secondary">Reused result</small>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {pendingSelected.length > 0 && (
          <div className="method-note">
            {pendingSelected.length} selected run{pendingSelected.length === 1 ? " is" : "s are"} still queued or running.
          </div>
        )}
      </GuideAnchor>

      {exportState.result && (
        <ExploratorySessionResult
          result={exportState.result}
          onDownload={onDownload}
        />
      )}
    </GuideAnchor>
  );
}

function ExploratorySessionResult({ result, onDownload }) {
  const summary = result.summary || {};
  const families = result.analysis_families || {};
  const downloads = result.downloads || {};
  const familyOrder = [
    "continuous_primary",
    "grouped_sensitivity",
    "signature_interaction",
  ];
  return (
    <section className="session-export-result" aria-label="Exploratory session export">
      <header className="session-export-header">
        <div>
          <span>Report <code>{result.report_id}</code></span>
          <h2>Exploratory record completed</h2>
          <p>
            {summary.selected_events} events produced {summary.unique_hypotheses} unique hypotheses and {summary.managed_family_references} managed-family {summary.managed_family_references === 1 ? "reference" : "references"}.
          </p>
        </div>
        <span className={`evidence-badge ${summary.excluded_events || summary.failed_events ? "caution" : "informative"}`}>
          {summary.excluded_events || summary.failed_events
            ? "Completed with exclusions"
            : "Selected scope captured"}
        </span>
      </header>
      <div className="session-downloads download-row" aria-label="Exploratory session downloads">
        <MiniDownloadButton href={downloads.runs_csv} label="Runs CSV" onDownload={onDownload} />
        <MiniDownloadButton href={downloads.hypotheses_csv} label="Hypotheses CSV" onDownload={onDownload} />
        <MiniDownloadButton href={downloads.ledger} label="Ledger JSON" onDownload={onDownload} />
        <MiniDownloadButton href={downloads.audit_html} label="Audit HTML" onDownload={onDownload} />
        <MiniDownloadButton href={downloads.attestation} label="Signed receipt" onDownload={onDownload} />
        <MiniDownloadButton href={downloads.zip} label="Bundle ZIP" onDownload={onDownload} />
      </div>
      <div className="table-scroll" role="region" aria-label="Scrollable exported hypothesis families" tabIndex={0}>
        <table className="session-family-table" aria-label="Export-defined multiplicity families">
          <thead>
            <tr>
              <th scope="col">Export-defined family</th>
              <th scope="col">Unique</th>
              <th scope="col">Evaluable</th>
              <th scope="col">p-value definition</th>
              <th scope="col">Multiplicity</th>
            </tr>
          </thead>
          <tbody>
            {familyOrder.map((familyId) => {
              const family = families[familyId] || {};
              return (
                <tr key={familyId}>
                  <th scope="row">{family.label || formatLabel(familyId)}</th>
                  <td>{formatInteger(family.unique_hypotheses)}</td>
                  <td>{formatInteger(family.evaluable_tests)}</td>
                  <td>{family.p_value_contract}</td>
                  <td>BH + Bonferroni</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <AnalysisNotices
        warnings={result.warnings}
        includeModelDiagnostics={false}
      />
      <div className="method-note">
        This export describes only the selected post hoc history. GSEA,
        Robustness and Pan-cancer results retain their own internal families
        and are not counted again.
      </div>
    </section>
  );
}

function formatMultiverseEffect(effect) {
  const hazardRatio = scientificNumber(effect?.display_hazard_ratio);
  const low = scientificNumber(effect?.display_hr_conf_low);
  const high = scientificNumber(effect?.display_hr_conf_high);
  if ([hazardRatio, low, high].some((value) => value === null)) return "Not estimable";
  return `${hazardRatio.toFixed(2)} (${low.toFixed(2)}–${high.toFixed(2)})`;
}

function formatEstimator(value) {
  return {
    standard_cox: "Standard Cox",
    firth_sensitivity: "Firth sensitivity",
  }[value] || "Not evaluable";
}

function formatInformationStatus(effect) {
  const status = effect?.information_status;
  const epp = scientificNumber(effect?.events_per_parameter);
  if (!status && epp === null) return "Not evaluable";
  return `${formatLabel(status || "unknown")}${epp !== null ? ` · ${epp.toFixed(1)} EPP` : ""}`;
}

function PanCancerSurvival({ state, setState, updateState, cohorts, repositoryDatasets, form, expressionScales, onDownload, onPlotDownload }) {
  const t = useHelpText();
  const analysisMode = state.analysis_mode === "hierarchical" ? "hierarchical" : "tcga_reference";
  const effectiveGeneInput = state.geneQuery.trim() ? addGeneToken(state.gene_symbol, state.geneQuery) : state.gene_symbol;
  const referenceCohorts = tcgaReferenceCohorts(cohorts);
  const indexCohort = referenceCohortId(cohorts, state.index_cohort, form.cohort);
  const indexCohortRecord = cohorts.find((cohort) => cohort.id === indexCohort) || null;
  const rankScoring = rankScoringAvailability(null, indexCohortRecord);
  const selectedExpressionScale =
    expressionScales.find((item) => item.value === state.expression_scale) || EXPRESSION_SCALE_FALLBACK[0];
  const selectedEndpointMode =
    PANCANCER_ENDPOINT_MODES.find((item) => item.value === state.endpoint_mode) || PANCANCER_ENDPOINT_MODES[0];
  const referenceValidation = referencePanCancerInputState({
    ...state,
    gene_symbol: effectiveGeneInput,
  });
  const genes = referenceValidation.genes.map((gene) => gene.gene_symbol);
  const selectedSignatureMethod = signatureMethodDefinition(
    state.signature_method || "single",
  );
  const rankMethodUnavailable = signatureMethodUsesDirection(
    state.signature_method || "single",
  ) && !rankScoring.available;
  const canRun = Boolean(
    indexCohort
    && referenceValidation.valid
    && !rankMethodUnavailable
    && !state.running,
  );
  const hierarchicalRequest = state.hierarchicalRequest || {};
  // Most scans ask about one gene, so the score-method picker only appears
  // once a signature is being entered.
  const signatureInput = uniqueGeneSymbols(effectiveGeneInput).length > 1
    || (state.signature_method || "single") !== "single";
  const advancedSummary = [
    `Reference ${indexCohort || "cancer"}`,
    selectedEndpointMode.label,
    selectedExpressionScale.label,
    `≥${state.min_patients} patients, ≥${state.min_events} events`,
    `FDR ${state.fdr_threshold}`,
  ].join(" · ");

  // The precomputed atlas is secondary to the user's own scan, so it is only
  // requested once the reader opens its disclosure.
  function loadImmuneScreen() {
    if (state.immuneScreen || state.immuneScreenLoading) return;
    setState((current) => ({
      ...current,
      immuneScreenLoading: true,
      immuneScreenError: "",
    }));
    getImmunePanCancerScreen()
      .then((payload) => setState((current) => ({
        ...current,
        immuneScreen: payload,
        immuneScreenError: "",
      })))
      .catch((err) => setState((current) => ({
        ...current,
        immuneScreenError: formatError(err),
      })))
      .finally(() => setState((current) => ({
        ...current,
        immuneScreenLoading: false,
      })));
  }

  function updateReferenceInput(key, value) {
    setState((current) => ({
      ...current,
      [key]: value,
      result: null,
      error: "",
    }));
  }

  function useCurrentKmInputs() {
    const copiedSignature = panCancerInputsFromSurvivalForm(form);
    if (!copiedSignature.valid && !copiedSignature.value) {
      setState((current) => ({
        ...current,
        error: copiedSignature.errors[0],
      }));
      return;
    }
    setState((current) => ({
      ...current,
      gene_symbol: copiedSignature.value.gene_symbol,
      signature_method: copiedSignature.value.signature_method,
      signature_genes: copiedSignature.value.signature_genes,
      geneQuery: "",
      index_cohort: form.cohort || current.index_cohort,
      endpoint: form.endpoint || current.endpoint,
      expression_scale: form.expression_scale || current.expression_scale,
      result: null,
      error: copiedSignature.valid ? "" : copiedSignature.errors[0],
    }));
  }

  async function runScan() {
    if (!canRun) {
      setState((current) => ({
        ...current,
        error: rankMethodUnavailable
          ? rankScoring.reason
          : referenceValidation.errors[0] || "Choose a valid gene or signature.",
      }));
      return;
    }
    setState((current) => ({
      ...current,
      gene_symbol: referenceValidation.value.gene_symbol,
      signature_method: referenceValidation.value.signature_method,
      signature_genes: referenceValidation.value.signature_genes,
      geneQuery: "",
      running: true,
      error: "",
    }));
    try {
      const payload = {
        index_cohort: indexCohort,
        endpoint: state.endpoint,
        endpoint_mode: state.endpoint_mode,
        expression_scale: state.expression_scale,
        ...referenceValidation.value,
        filters: {
          sample_population: "primary_disease",
          sample_types: [],
          stages: [],
          grades: [],
          genders: [],
          races: [],
          age_min: null,
          age_max: null,
          max_time_days: null,
        },
      };
      const result = await createPanCancerSurvival(payload);
      setState((current) => ({ ...current, result, error: "" }));
    } catch (err) {
      setState((current) => ({ ...current, error: formatError(err) }));
    } finally {
      setState((current) => ({ ...current, running: false }));
    }
  }

  function hierarchicalPayload(requestState = hierarchicalRequest) {
    const selectedGenes = uniqueGeneSymbols(requestState.gene_symbol || "");
    const thresholds = hierarchicalThresholdState(requestState);
    if (selectedGenes.length !== 1 || !thresholds.valid) return null;
    return {
      gene_symbol: selectedGenes[0],
      scope: requestState.scope || "combined",
      cancers: requestState.cancers || [],
      study_ids: requestState.study_ids || [],
      endpoint: "OS",
      clinical_context: requestState.clinical_context || "primary_baseline",
      time_origin_policy: "strict_baseline",
      effect_scale: "within_study_iqr",
      overlap_policy: "independent_clusters",
      min_patients: thresholds.value.min_patients,
      min_events: thresholds.value.min_events,
      min_censored: thresholds.value.min_censored,
      include_exploratory: Boolean(requestState.include_exploratory),
      fdr_threshold: thresholds.value.fdr_threshold,
    };
  }

  function changeAnalysisMode(nextMode) {
    setState((current) => {
      const seedGene = uniqueGeneSymbols(
        current.hierarchicalRequest?.gene_symbol
          || current.gene_symbol
          || form.gene_symbol,
      ).slice(0, 1).join(", ");
      return {
        ...current,
        analysis_mode: nextMode,
        geneQuery: "",
        hierarchicalRequest: {
          ...(current.hierarchicalRequest || {}),
          gene_symbol: current.hierarchicalRequest?.gene_symbol || seedGene,
        },
        hierarchicalError: "",
        hierarchicalPreflightError: "",
      };
    });
  }

  function changeHierarchicalRequest(nextRequest) {
    const selectedGene = uniqueGeneSymbols(nextRequest.gene_symbol || "").slice(0, 1).join(", ");
    setState((current) => ({
      ...current,
      geneQuery: "",
      hierarchicalRequest: {
        ...nextRequest,
        gene_symbol: selectedGene,
      },
      hierarchicalPreflight: null,
      hierarchicalPreflightStatus: "idle",
      hierarchicalPreflightError: "",
      hierarchicalResult: null,
      hierarchicalError: "",
    }));
  }

  async function requestHierarchicalPreflight(requestState) {
    const payload = hierarchicalPayload(requestState);
    if (!payload) {
      const thresholdError = hierarchicalThresholdState(requestState).errors[0];
      setState((current) => ({
        ...current,
        hierarchicalPreflight: null,
        hierarchicalPreflightStatus: "error",
        hierarchicalPreflightError: thresholdError || "Select one gene before checking study eligibility.",
      }));
      return;
    }
    setState((current) => ({
      ...current,
      hierarchicalRequest: { ...requestState, gene_symbol: payload.gene_symbol },
      hierarchicalPreflight: null,
      hierarchicalPreflightStatus: "loading",
      hierarchicalPreflightError: "",
      hierarchicalError: "",
    }));
    try {
      const preflight = await getHierarchicalPanCancerPreflight(payload);
      setState((current) => ({
        ...current,
        hierarchicalPreflight: preflight,
        hierarchicalPreflightStatus: "ready",
        hierarchicalPreflightError: "",
      }));
    } catch (err) {
      setState((current) => ({
        ...current,
        hierarchicalPreflightStatus: "error",
        hierarchicalPreflightError: formatError(err),
      }));
    }
  }

  async function runHierarchicalScan(requestState) {
    const payload = hierarchicalPayload(requestState);
    if (!payload || !state.hierarchicalPreflight || state.hierarchicalRunning) return;
    setState((current) => ({
      ...current,
      hierarchicalRunning: true,
      hierarchicalError: "",
    }));
    try {
      const result = await createHierarchicalPanCancerSurvival(payload);
      setState((current) => ({
        ...current,
        hierarchicalResult: result,
        hierarchicalError: "",
      }));
    } catch (err) {
      setState((current) => ({
        ...current,
        hierarchicalError: formatError(err),
      }));
    } finally {
      setState((current) => ({ ...current, hierarchicalRunning: false }));
    }
  }

  return (
    <section className="pancancer-page">
      <ActiveJobRecovery
        sourceView="pancancer"
        busy={state.running || state.hierarchicalRunning}
        onRecover={(result, job) => setState((current) => (
          job?.kind === "pancancer_hierarchical"
            ? {
                ...current,
                analysis_mode: "hierarchical",
                hierarchicalRunning: false,
                hierarchicalResult: result,
                hierarchicalError: "",
              }
            : {
                ...current,
                analysis_mode: "tcga_reference",
                running: false,
                result,
                error: "",
              }
        ))}
      />
      <HierarchicalPanCancerModule
        mode={analysisMode}
        onModeChange={changeAnalysisMode}
        requestState={hierarchicalRequest}
        onRequestChange={changeHierarchicalRequest}
        geneSelector={({
          id,
          value,
          onChange,
          disabled,
          required,
          "aria-labelledby": ariaLabelledby,
        }) => (
          <GeneSelector
            id={id}
            label="Gene marker"
            value={value}
            onChange={(nextValue) =>
              onChange(uniqueGeneSymbols(nextValue).slice(0, 1).join(", "))
            }
            draft={state.geneQuery}
            setDraft={(nextValue) => updateState("geneQuery", nextValue)}
            suggestions={state.geneSuggestions}
            placeholder="Type TP53, ESR1, BAP1..."
            helpId="pancancerMarker"
            helpSlot="does"
            showClipboardHint={false}
            disabled={disabled}
            required={required}
            ariaLabelledby={ariaLabelledby}
            hideHeader
          />
        )}
        preflight={state.hierarchicalPreflight}
        preflightStatus={state.hierarchicalPreflightStatus}
        preflightError={state.hierarchicalPreflightError}
        onRequestPreflight={requestHierarchicalPreflight}
        onRun={runHierarchicalScan}
        isRunning={state.hierarchicalRunning}
        result={state.hierarchicalResult}
        resultView={state.hierarchicalResultView}
        onResultViewChange={(nextView) => updateState("hierarchicalResultView", nextView)}
        onDownload={onDownload}
      />

      {analysisMode === "hierarchical" && state.hierarchicalError && (
        <div className="error-box">
          <TraceIcon role="status.error" size="md" tone="error" />
          <span>{state.hierarchicalError}</span>
        </div>
      )}
      {analysisMode === "hierarchical" && state.hierarchicalRunning && (
        <div className="loading-state compact">
          <TraceIcon role="status.loading" size="lg" className="spin" label="Running hierarchical pan-cancer analysis" />
          <div>
            <p className="eyebrow">Fitting the evidence hierarchy</p>
            <h2>{hierarchicalRequest.gene_symbol || "Gene"}: study → cancer → global</h2>
            <span>Each release is fitted independently; only compatible IQR-scaled effects are synthesized.</span>
            <ElapsedTime />
          </div>
        </div>
      )}

      {analysisMode === "tcga_reference" && <>
      <div className="pancancer-controls">
        <GuideAnchor
          as="div"
          anchor={GUIDE_ANCHORS.PANCANCER_QUERY}
          label="Pan-cancer marker controls"
          className="pancancer-control-panel"
        >
          <PanelHeader
            iconRole="module.panCancerQuery"
            title="2. Choose a gene or signature"
            helpId="pancancer.query"
          />
          <GeneSelector
            label={state.signature_method === "single" ? "Gene or signature genes" : "Signature genes"}
            value={state.gene_symbol}
            onChange={(value) => updateReferenceInput("gene_symbol", value)}
            draft={state.geneQuery}
            setDraft={(value) => updateState("geneQuery", value)}
            suggestions={state.geneSuggestions}
            placeholder={signatureMethodUsesDirection(state.signature_method)
              ? "Type IFNG, GZMB, TGFB1:-1..."
              : state.signature_method === "single"
                ? "e.g. TP53"
                : signatureMethodUsesNumericWeights(state.signature_method)
                  ? "Type IFNG:1, CXCL9:0.5, TGFB1:-1..."
                  : "Type IFNG, CXCL9, GZMB..."}
            helpId="pancancerMarkerInput"
            helpSlot="does"
            showClipboardHint={false}
          />
          {signatureInput ? (
            <PanCancerSignatureMethodPicker
              method={state.signature_method || "single"}
              geneInput={effectiveGeneInput}
              rankScoring={rankScoring}
              onChange={(value) => updateReferenceInput("signature_method", value)}
            />
          ) : null}
          <div className="download-row">
            <button type="button" onClick={useCurrentKmInputs}>
              Copy from Survival
            </button>
          </div>
        </GuideAnchor>

        <GuideAnchor
          as="div"
          anchor={GUIDE_ANCHORS.PANCANCER_PREFLIGHT}
          label="Pan-cancer outcome and settings"
          className="pancancer-control-panel"
        >
          <PanelHeader
            iconRole="module.outcomeModel"
            title="3. Choose the outcome and run"
            helpId="pancancerEndpointMode"
          />
          <label className="field">
            <span>Survival outcome</span>
            <select value={state.endpoint} onChange={(event) => updateReferenceInput("endpoint", event.target.value)}>
              {PANCANCER_ENDPOINTS.map((endpoint) => (
                <option key={endpoint.value} value={endpoint.value}>
                  {endpoint.label}
                </option>
              ))}
            </select>
          </label>
          <details className="result-disclosure pancancer-advanced">
            <summary>
              <span>
                <strong>Advanced settings</strong>
                <small>Data settings and which cancers to include</small>
              </span>
              <b>Optional</b>
            </summary>
            <div className="pancancer-advanced-body">
              <p className="field-help">{advancedSummary}</p>
              <label className="field">
                <span>Reference cancer</span>
                <select value={indexCohort} onChange={(event) => updateReferenceInput("index_cohort", event.target.value)}>
                  {referenceCohorts.map((cohort) => (
                    <option key={cohort.id} value={cohort.id}>
                      {getCohortLabel(cohort.id)}
                    </option>
                  ))}
                </select>
                <small className="field-help">Other cancers are compared with this one in the concordance map. Every eligible cancer is still analysed.</small>
              </label>
              <label className="field">
                <span>Expression scale</span>
                <select value={state.expression_scale} onChange={(event) => updateReferenceInput("expression_scale", event.target.value)}>
                  {expressionScales.map((scale) => (
                    <option key={scale.value} value={scale.value}>
                      {scale.label}
                    </option>
                  ))}
                </select>
              </label>
              <div className="field">
                <span>Matching the outcome across cancers</span>
                <div className="method-grid compact">
                  {PANCANCER_ENDPOINT_MODES.map((item) => (
                    <button
                      key={item.value}
                      type="button"
                      className={state.endpoint_mode === item.value ? "selected" : ""}
                      onClick={() => updateReferenceInput("endpoint_mode", item.value)}
                    >
                      <strong>{item.label}</strong>
                      <span>{item.help}</span>
                    </button>
                  ))}
                </div>
                <FieldHelp helpId="pancancerEndpointMode" slot="does" />
              </div>
              <h3>Which cancers enter the scan?</h3>
              <FieldHelp helpId="pancancerInclusion" slot="does" />
              <div className="range-grid">
                <label className="field">
                  <span>Minimum patients per cancer</span>
                  <input
                    type="number"
                    min="10"
                    max="500"
                    step="1"
                    value={state.min_patients}
                    onChange={(event) => updateReferenceInput("min_patients", event.target.value)}
                  />
                  <FieldHelp helpId="pancancerPatients" />
                </label>
                <label className="field">
                  <span>Minimum outcome events per cancer</span>
                  <input
                    type="number"
                    min="5"
                    max="500"
                    step="1"
                    value={state.min_events}
                    onChange={(event) => updateReferenceInput("min_events", event.target.value)}
                  />
                  <FieldHelp helpId="pancancerEvents" />
                </label>
                <label className="field wide">
                  <span>Highlight associations at q ≤</span>
                  <input
                    type="number"
                    min="0.01"
                    max="1"
                    step="0.01"
                    value={state.fdr_threshold}
                    onChange={(event) => updateReferenceInput("fdr_threshold", event.target.value)}
                  />
                  <FieldHelp helpId="pancancerFdr" slot="all" />
                </label>
              </div>
            </div>
          </details>
          {!referenceValidation.valid && (effectiveGeneInput.trim() || referenceValidation.genes.length > 0) && (
            <p className="field-error" role="alert">
              {referenceValidation.errors[0]}
            </p>
          )}
          <div className="run-summary static">
            <div>
              <span>Your analysis</span>
              <strong>
                {referenceValidation.valid
                  ? state.signature_method === "single"
                    ? `${genes[0]} across ${formatInteger(referenceCohorts.length)} cancers`
                    : `${selectedSignatureMethod.shortLabel} · ${formatInteger(genes.length)}-gene signature across ${formatInteger(referenceCohorts.length)} cancers`
                  : "Add a gene to start"}
              </strong>
              {referenceValidation.valid && <small>One Cox model per eligible cancer. Standardized effects are per 1 SD within each cancer.</small>}
            </div>
            <button className="primary-button" onClick={runScan} disabled={!canRun}>
              {state.running ? <TraceIcon role="status.loading" size="md" className="spin" /> : <TraceIcon role="action.run" size="md" />}
              Run pan-cancer scan
            </button>
          </div>
        </GuideAnchor>
      </div>

      {state.error && <div className="error-box"><TraceIcon role="status.error" size="md" tone="error" /><span>{state.error}</span></div>}
      {state.running && (
        <div className="loading-state compact">
          <TraceIcon role="status.loading" size="lg" className="spin" label="Running pan-cancer scan" />
          <div>
            <p className="eyebrow">Running pan-cancer scan</p>
            <h2>
              {state.signature_method === "single"
                ? `${genes[0] || state.gene_symbol || "Gene"} across TCGA cohorts`
                : `${selectedSignatureMethod.shortLabel} signature across TCGA cohorts`}
            </h2>
            <span>Fitting one survival model per cancer, then correcting for multiple testing and summarizing agreement.</span>
            <ElapsedTime />
          </div>
        </div>
      )}
      {!state.running && !state.result && !state.error && (
        <div className="empty-plot">
          <ModuleIcon role="module.panCancerQuery" />
          <p>Results will appear here.</p>
        </div>
      )}
      {state.result && <PanCancerResults result={state.result} onDownload={onDownload} onPlotDownload={onPlotDownload} />}

      <details
        className="result-disclosure pancancer-atlas-disclosure"
        onToggle={(event) => {
          if (event.currentTarget.open) loadImmuneScreen();
        }}
      >
        <summary>
          <span>
            <strong>Immune pan-cancer atlas</strong>
            <small>A precomputed, versioned screen of immune genes across TCGA cancers. It is independent of your scan above.</small>
          </span>
          <b>Precomputed</b>
        </summary>
        <div className="pancancer-atlas-body">
          <ImmunePanCancerAtlas
            screen={state.immuneScreen}
            loading={state.immuneScreenLoading}
            error={state.immuneScreenError}
            onDownload={onDownload}
            onPlotDownload={onPlotDownload}
          />
        </div>
      </details>
      </>}
    </section>
  );
}

const PANCANCER_SECONDARY_VIEWS = [
  { value: "concordance", label: "Concordance map" },
  { value: "landscape", label: "Evidence landscape" },
  { value: "power", label: "Power and precision" },
  { value: "sensitivity", label: "Stage and grade sensitivity" },
];

function PanCancerResults({ result, onDownload, onPlotDownload }) {
  const summary = result.summary || {};
  const randomEffect = result.meta_analysis?.random_effect || {};
  const heterogeneity = result.meta_analysis?.heterogeneity || {};
  const predictionInterval = result.meta_analysis?.prediction_interval || {};
  const sensitivity = result.clinical_sensitivity || {};
  const secondaryViews = PANCANCER_SECONDARY_VIEWS.filter(
    (view) => view.value !== "sensitivity" || sensitivity.available,
  );
  const [secondaryView, setSecondaryView] = useState(secondaryViews[0].value);
  const activeSecondaryView = secondaryViews.some((view) => view.value === secondaryView)
    ? secondaryView
    : secondaryViews[0].value;
  const cohortScoringContracts = (result.results || [])
    .filter((row) => row.signature_scoring)
    .map((row) => ({
      id: row.cohort,
      label: `${row.cohort_label || row.cohort} · ${row.endpoint || result.endpoint}`,
      signature: row.signature_scoring,
    }));
  const cohortSpecificScoring = result.signature_scoring_scope?.scope
    === "cohort_specific";
  return (
    <GuideAnchor
      as="div"
      anchor={GUIDE_ANCHORS.PANCANCER_RESULTS}
      label="Pan-cancer concordance results"
      className="pancancer-results"
    >
      <div className="analysis-result">
        <div className="result-header">
          <div>
            <p className="eyebrow">{result.scan_id} {result.cached ? "/ cached" : ""}</p>
            <h2>{result.gene_symbol} across TCGA cancer types</h2>
          </div>
        </div>
        <div className="metric-strip pancancer-kpis">
          <Metric label="Cancers analysed" value={`${formatInteger(summary.completed)} / ${formatInteger(summary.total_cohorts)}`} />
          <Metric label="Significant after FDR correction" value={formatInteger(summary.significant)} />
          <Metric label="Pooled hazard ratio (95% CI)" value={randomEffect.hazard_ratio ? formatHrValues(randomEffect) : "Not pooled"} />
          <Metric label="Expected range in a new cancer (95% PI)" value={formatPredictionInterval(predictionInterval)} />
          <Metric label="Inconsistency between cancers (I²)" value={formatPercent(heterogeneity.i_squared)} />
        </div>
        {cohortSpecificScoring ? (
          <SignatureScoringCollectionSummary
            items={cohortScoringContracts}
            title="Cohort-specific signature scoring"
            description="TRACE calculates the signature separately in each cohort. Choose a cohort to inspect its matched genes, coverage, patients and scoring method."
          />
        ) : (
          <SignatureScoringSummary signature={result.signature} />
        )}
        <AnalysisNotices warnings={result.warnings} includeModelDiagnostics={false} />
        <div className="download-row pancancer-downloads">
          <span>Downloads</span>
          <DownloadLink href={result.downloads?.csv} iconRole="file.csv" label="CSV" onDownload={onDownload} />
          <DownloadLink href={result.downloads?.methodology} iconRole="file.text" label="Methods" onDownload={onDownload} />
          <DownloadLink href={result.downloads?.audit_html} iconRole="file.audit" label="Audit" onDownload={onDownload} />
          <DownloadLink href={result.downloads?.attestation} iconRole="file.audit" label="Signed receipt" onDownload={onDownload} />
          <DownloadLink href={result.downloads?.zip} iconRole="file.archive" label="Bundle" onDownload={onDownload} />
        </div>
      </div>

      <ResultTabs label="Cross-cancer result sections">
      <ResultSection id="effects" title="Effects by cancer" helpId="resultPanCancerEffects" descriptionHelpId="resultPanCancerEffects">
      <div className="pancancer-layout">
        <section className="summary-panel wide">

          <PlotDownloadButtons
            svgSelector=".pancancer-forest"
            filenameBase={`${result.scan_id}.forest`}
            onPlotDownload={onPlotDownload}
          />
          <PanCancerForestPlot
            rows={result.results || []}
            metaAnalysis={result.meta_analysis}
            effectScale={result.effect_scale}
          />
        </section>
      </div>
      </ResultSection>
      <ResultSection id="table" title="Cancer statistics" helpId="resultPanCancerTable" descriptionHelpId="resultPanCancerTable">
        <section className="summary-panel wide">

          <PanCancerTable rows={result.results || []} />
        </section>
      </ResultSection>
      <ResultSection id="more" title="Evidence & sensitivity">
      <div className="pancancer-layout">
        <section className="summary-panel wide pancancer-more-views">
          <div className="pancancer-view-switch" role="group" aria-label="Additional pan-cancer views">
            <strong>More views</strong>
            {secondaryViews.map((view) => (
              <button
                key={view.value}
                type="button"
                aria-pressed={activeSecondaryView === view.value}
                className={activeSecondaryView === view.value ? "selected" : ""}
                onClick={() => setSecondaryView(view.value)}
              >
                {view.label}
              </button>
            ))}
          </div>
          {activeSecondaryView === "concordance" && (
            <>
              <PanelHeader
                iconRole="module.concordance"
                title="Concordance map"
                description="Compare each cancer's effect with the reference cancer, including statistical evidence and model availability."
              />
              <PanCancerConcordanceMap
                rows={result.results || []}
                summary={summary}
                reference={result.reference}
                fdrThreshold={result.fdr_threshold}
              />
            </>
          )}
          {activeSecondaryView === "landscape" && (
            <>
              <PanelHeader
                iconRole="module.evidence"
                title="Evidence landscape"
                description="Each cancer is placed by effect size and FDR evidence; the horizontal line marks the selected FDR threshold."
              />
              <PlotDownloadButtons
                svgSelector=".pancancer-landscape"
                filenameBase={`${result.scan_id}.evidence_landscape`}
                onPlotDownload={onPlotDownload}
              />
              <PanCancerEvidenceLandscape rows={result.results || []} fdrThreshold={result.fdr_threshold} />
            </>
          )}
          {activeSecondaryView === "power" && (
            <>
              <PanelHeader
                iconRole="module.precision"
                title="Power and precision map"
                description="Compare event counts with estimate precision. More events usually support a more precise estimate."
              />
              <PlotDownloadButtons
                svgSelector=".pancancer-power"
                filenameBase={`${result.scan_id}.power_precision`}
                onPlotDownload={onPlotDownload}
              />
              <PanCancerPowerPrecision rows={result.results || []} />
            </>
          )}
          {activeSecondaryView === "sensitivity" && (
            <PanCancerSensitivityPanel
              sensitivity={sensitivity}
              rows={result.results || []}
              scanId={result.scan_id}
              onPlotDownload={onPlotDownload}
            />
          )}
        </section>
      </div>
      </ResultSection>
      </ResultTabs>
    </GuideAnchor>
  );
}

function PanCancerSensitivityPanel({ sensitivity, rows, scanId, onPlotDownload }) {
  const summary = sensitivity.summary || {};
  const comparisons = summary.comparison_counts || {};
  const families = [
    ["stage_grade_adjusted", "Stage + grade"],
    ["stage_adjusted", "Stage"],
    ["grade_adjusted", "Grade"],
  ];
  return (
    <section className="summary-panel wide pancancer-sensitivity">
      <PanelHeader
        iconRole="module.cohortEffects"
        title="Clinical sensitivity"
        description="Does the continuous association persist after adjustment for ordinal stage and grade?"
      />
      <div className="sensitivity-estimands">
        <div>
          <span>Cohort models</span>
          <strong>Marker or score z-value + covariates</strong>
          <small>Reported per within-cohort SD; descriptive, not pooled</small>
        </div>
        <TraceIcon role="action.next" size="md" />
        <div>
          <span>Comparable synthesis</span>
          <strong>Common input-score unit</strong>
          <small>REML + HKSJ within one endpoint and adjustment family</small>
        </div>
      </div>
      <div className="sensitivity-summary-line">
        <span><strong>{formatInteger(summary.evaluable)}</strong> adjusted</span>
        <span><strong>{formatInteger(summary.fdr_significant)}</strong> FDR hits</span>
        <span><strong>{formatInteger(comparisons.retained || 0)}</strong> retained</span>
        <span><strong>{formatInteger(comparisons.attenuated || 0)}</strong> attenuated</span>
        <span><strong>{formatInteger(summary.direction_reversed || 0)}</strong> reversed</span>
        <span className="quiet"><strong>{formatInteger(summary.not_evaluable)}</strong> no usable covariates</span>
      </div>
      <div className="sensitivity-family-table" role="table" aria-label="Meta-analysis by clinical adjustment family">
        <div className="sensitivity-family-row header" role="row">
          <span role="columnheader">Adjustment</span>
          <span role="columnheader">Cohorts</span>
          <span role="columnheader">FDR hits</span>
          <span role="columnheader">Common-scale REML HR</span>
          <span role="columnheader">95% prediction interval</span>
          <span role="columnheader">HKSJ p</span>
        </div>
        {families.map(([modelId, label]) => {
          const family = sensitivity.meta_analysis_by_model?.[modelId] || {};
          const meta = family.meta_analysis || {};
          const random = meta.random_effect || {};
          return (
            <div className="sensitivity-family-row" role="row" key={modelId}>
              <strong role="cell">{label}</strong>
              <span role="cell">{formatInteger(family.evaluable_cohorts)}</span>
              <span role="cell">{formatInteger(family.fdr_significant)}</span>
              <span role="cell">{meta.available ? formatHrValues(random) : "Not evaluable"}</span>
              <span role="cell">{meta.available ? formatPredictionInterval(meta.prediction_interval) : "..."}</span>
              <span role="cell">{formatP(random.p_value)}</span>
            </div>
          );
        })}
      </div>
      <div className="sensitivity-plot-header">
        <span>Each line connects the primary HR to the selected adjusted HR in the same cancer.</span>
        <PlotDownloadButtons
          svgSelector=".pancancer-sensitivity-svg"
          filenameBase={`${scanId}.clinical_sensitivity`}
          onPlotDownload={onPlotDownload}
        />
      </div>
      <PanCancerSensitivityPlot rows={rows} />
      <div className="method-note sensitivity-note">
        Selected adjusted models can differ by cancer, so mixed selected families are deliberately not pooled. Common-scale estimates stay separated by endpoint and adjustment family.
      </div>
    </section>
  );
}

function PanCancerSensitivityPlot({ rows }) {
  const points = (rows || [])
    .filter(
      (row) =>
        row.status === "completed"
        && row.adjusted_status === "completed"
        && finiteNumber(row.hazard_ratio) !== null
        && finiteNumber(row.adjusted_hazard_ratio) !== null,
    )
    .sort((a, b) => String(a.cohort).localeCompare(String(b.cohort)));
  if (!points.length) {
    return <div className="empty-inline">No ordinal-adjusted cohort model was evaluable.</div>;
  }

  const width = 920;
  const rowHeight = 27;
  const plot = { left: 126, right: 108, top: 38, bottom: 46 };
  const height = plot.top + plot.bottom + points.length * rowHeight;
  const logValues = points.flatMap((row) => [
    Math.log(Number(row.hazard_ratio)),
    Math.log(Number(row.adjusted_hazard_ratio)),
  ]);
  const extent = Math.max(0.25, ...logValues.map((value) => Math.abs(value))) * 1.12;
  const scaleX = (logHr) =>
    plot.left + ((logHr + extent) / (extent * 2)) * (width - plot.left - plot.right);
  const ticks = [-extent, -extent / 2, 0, extent / 2, extent];
  const modelCodes = {
    stage_grade_adjusted: "S + G",
    stage_adjusted: "S",
    grade_adjusted: "G",
  };
  return (
    <div className="pancancer-sensitivity-wrap" role="region" aria-label="Scrollable clinical sensitivity plot" tabIndex={0}>
      <svg
        className="pancancer-sensitivity-svg"
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label="Primary versus ordinal-adjusted hazard ratios by cancer"
      >
        <line
          className="sensitivity-null-line"
          x1={scaleX(0)}
          x2={scaleX(0)}
          y1={plot.top - 14}
          y2={height - plot.bottom + 4}
        />
        {ticks.map((tick, index) => (
          <g className="sensitivity-axis" key={index}>
            <line x1={scaleX(tick)} x2={scaleX(tick)} y1={height - plot.bottom} y2={height - plot.bottom + 6} />
            <text x={scaleX(tick)} y={height - 19}>{Math.exp(tick).toFixed(2)}</text>
          </g>
        ))}
        <text className="sensitivity-axis-title" x={(plot.left + width - plot.right) / 2} y={height - 3}>Hazard ratio per +1 SD of marker or score</text>
        {points.map((row, index) => {
          const y = plot.top + index * rowHeight;
          const primaryX = scaleX(Math.log(Number(row.hazard_ratio)));
          const adjustedX = scaleX(Math.log(Number(row.adjusted_hazard_ratio)));
          const tone = row.adjusted_direction || "neutral";
          return (
            <g className={`sensitivity-cohort-row ${tone}`} key={row.cohort}>
              <line className="sensitivity-row-guide" x1={plot.left} x2={width - plot.right} y1={y} y2={y} />
              <text className="sensitivity-cohort-label" x={plot.left - 10} y={y + 4}>{row.cohort.replace("TCGA-", "")}</text>
              <line className="sensitivity-connector" x1={primaryX} x2={adjustedX} y1={y} y2={y} />
              <circle className="sensitivity-primary-point" cx={primaryX} cy={y} r="4.5" />
              <rect className="sensitivity-adjusted-point" x={adjustedX - 4.5} y={y - 4.5} width="9" height="9" rx="1.5" />
              <text className="sensitivity-model-code" x={width - plot.right + 12} y={y + 4}>
                {modelCodes[row.selected_adjusted_model] || "..."}
              </text>
              <title>{`${row.cohort}: primary HR ${Number(row.hazard_ratio).toFixed(2)}; adjusted HR ${Number(row.adjusted_hazard_ratio).toFixed(2)}; ${formatClinicalSensitivity(row.clinical_sensitivity)}`}</title>
            </g>
          );
        })}
      </svg>
      <div className="sensitivity-legend">
        <span><i className="primary" /> Primary</span>
        <span><i className="adjusted" /> Selected adjusted</span>
        <span>S = stage · G = grade</span>
      </div>
    </div>
  );
}

function ImmunePanCancerAtlas({ screen, loading, error, onDownload, onPlotDownload }) {
  const [modelView, setModelView] = useState("primary");
  if (loading) {
    return (
      <div className="immune-atlas loading-state compact">
        <TraceIcon role="status.loading" size="lg" className="spin" label="Loading immune screen summary" />
        <div>
          <p className="eyebrow">Immune pan-cancer atlas</p>
          <h2>Loading immune screen summary</h2>
        </div>
      </div>
    );
  }
  if (error) {
    return <div className="error-box"><TraceIcon role="status.error" size="md" tone="error" /><span>{error}</span></div>;
  }
  if (!screen) return null;

  const atlasHeadline = screen.headline || {};
  const downloads = screen.downloads || {};
  const modelViews = screen.model_views || {};
  const activeView = modelViews[modelView] || {
    model: "primary",
    label: "Primary continuous expression",
    headline: atlasHeadline,
    direction_counts_global_fdr: screen.direction_counts_global_fdr || {},
    recurrence: screen.recurrence || {},
    top_genes: screen.top_genes || [],
    top_cohorts: screen.top_cohorts || [],
    top_terms: screen.top_terms || [],
  };
  const headline = activeView.headline || {};
  const directions = activeView.direction_counts_global_fdr || {};
  const recurrence = activeView.recurrence || {};
  const sensitivity = screen.clinical_sensitivity || {};
  const sensitivitySummary = sensitivity.summary || {};
  const viewOptions = [
    ["primary", "Primary", "Expression only"],
    ["stage_grade_adjusted", "Stage + grade", "Ordinal sensitivity"],
    ["stage_adjusted", "Stage", "Ordinal sensitivity"],
    ["grade_adjusted", "Grade", "Ordinal sensitivity"],
  ].filter(([id]) => modelViews[id]);
  const viewLabel = activeView.label || "Primary continuous expression";
  return (
    <div className="immune-atlas analysis-result">
      <div className="result-header immune-atlas-header">
        <div>
          <p className="eyebrow">{screen.screen_id}</p>
          <h2>Immune pan-cancer atlas</h2>
          {screen.pipeline_version && <code className="immune-atlas-version">{screen.pipeline_version}</code>}
        </div>
        <div className="download-row">
          <DownloadLink href={downloads.gene_models || downloads.genes} iconRole="file.csv" label="Gene models" onDownload={onDownload} />
          <DownloadLink href={downloads.results} iconRole="data.table" label="Model rows" onDownload={onDownload} />
          <DownloadLink href={downloads.sensitivity} iconRole="data.compare" label="Sensitivity" onDownload={onDownload} />
          <DownloadLink href={downloads.methodology} iconRole="file.text" label="Methods" onDownload={onDownload} />
          <DownloadLink href={downloads.audit} iconRole="file.audit" label="Audit" onDownload={onDownload} />
          <DownloadLink href={downloads.zip} iconRole="file.archive" label="Bundle" onDownload={onDownload} />
        </div>
      </div>

      {viewOptions.length > 0 && (
        <div className="immune-model-toolbar">
          <div>
            <span>Comparable model family</span>
            <small>FDR and random-effects meta-analysis are recomputed independently for every view.</small>
          </div>
          <div className="immune-model-switch" role="group" aria-label="Immune atlas model family">
            {viewOptions.map(([id, label, description]) => (
              <button
                key={id}
                type="button"
                className={modelView === id ? "selected" : ""}
                aria-pressed={modelView === id}
                onClick={() => setModelView(id)}
              >
                <strong>{label}</strong>
                <span>{description}</span>
              </button>
            ))}
          </div>
        </div>
      )}

      <div className="metric-strip immune-kpis">
        <Metric label="Immune genes" value={formatInteger(atlasHeadline.immune_genes)} />
        <Metric label="Cox models" value={formatInteger(headline.completed_gene_cohort_models)} />
        <Metric label="Global FDR hits" value={formatInteger(headline.global_fdr_hits)} />
        <Metric label="Meta-FDR genes" value={formatInteger(headline.meta_fdr_gene_hits)} />
        <Metric label="Harmful hits" value={formatInteger(directions.harmful || 0)} />
        <Metric label="Protective hits" value={formatInteger(directions.protective || 0)} />
      </div>

      {sensitivity.available && (
        <section className="immune-clinical-trace" aria-label="Atlas-wide selected clinical sensitivity">
          <div>
            <span>Availability-selected sensitivity</span>
            <strong>Stage + grade → stage → grade</strong>
            <small>Counts below are gene–cancer tests. Mixed adjustment families are not meta-analyzed.</small>
          </div>
          <dl>
            <div><dt>Evaluable</dt><dd>{formatInteger(sensitivitySummary.evaluable)}</dd></div>
            <div><dt>FDR hits</dt><dd>{formatInteger(sensitivitySummary.fdr_significant)}</dd></div>
            <div><dt>Retained</dt><dd>{formatInteger(sensitivitySummary.retained)}</dd></div>
            <div><dt>Attenuated</dt><dd>{formatInteger(sensitivitySummary.attenuated)}</dd></div>
            <div><dt>Emergent</dt><dd>{formatInteger(sensitivitySummary.emerged)}</dd></div>
            <div><dt>Primary-FDR flips</dt><dd>{formatInteger(sensitivitySummary.primary_fdr_direction_reversed)}</dd></div>
            <div><dt>FDR + PH caution</dt><dd>{formatInteger(sensitivitySummary.fdr_significant_ph_flagged)}</dd></div>
            <div><dt>Not evaluable</dt><dd>{formatInteger(sensitivitySummary.not_evaluable)}</dd></div>
          </dl>
        </section>
      )}

      <div className="immune-atlas-grid">
        <section className="immune-panel recurrence">
          <PanelHeader
            iconRole="module.recurrence"
            title="Recurrence by prognosis"
            description={`How often each immune gene is a ${viewLabel.toLowerCase()} global-FDR hit with HR > 1 or HR < 1 across cancers.`}
          />
          <PlotDownloadButtons
            svgSelector=".immune-recurrence-svg"
            filenameBase={`${screen.screen_id}.${modelView}.immune_recurrence`}
            onPlotDownload={onPlotDownload}
          />
          <ImmuneRecurrencePlot recurrence={recurrence} />
        </section>
        <section className="immune-panel frequency">
          <PanelHeader
            iconRole="module.frequency"
            title="Rare versus recurrent"
            description={`Context-specific versus recurrent evidence within the ${viewLabel.toLowerCase()} family.`}
          />
          <PlotDownloadButtons
            svgSelector=".immune-frequency-svg"
            filenameBase={`${screen.screen_id}.${modelView}.immune_frequency`}
            onPlotDownload={onPlotDownload}
          />
          <ImmuneFrequencyDistribution recurrence={recurrence} />
        </section>
        <section className="immune-panel spectrum">
          <PanelHeader
            iconRole="module.meta"
            title="Meta-behavior"
            description={`Family-specific random-effects signal for ${viewLabel.toLowerCase()}; point size follows cohort-level FDR hits.`}
          />
          <PlotDownloadButtons
            svgSelector=".immune-spectrum-svg"
            filenameBase={`${screen.screen_id}.${modelView}.immune_meta_spectrum`}
            onPlotDownload={onPlotDownload}
          />
          <ImmuneMetaSpectrum genes={activeView.top_genes || []} />
        </section>
        <section className="immune-panel burden">
          <PanelHeader
            iconRole="module.burden"
            title="Cancer burden"
            description={`Cancers with the densest ${viewLabel.toLowerCase()} immune-gene signal under global FDR control.`}
          />
          <ImmuneCohortBurden cohorts={activeView.top_cohorts || []} />
        </section>
        <section className="immune-panel terms">
          <PanelHeader
            iconRole="module.immunePrograms"
            title="Immune programs"
            description={`ImmPort GO/Reactome terms represented among the strongest ${viewLabel.toLowerCase()} signals.`}
          />
          <ImmuneTermList terms={activeView.top_terms || []} />
        </section>
        <section className="immune-panel rare">
          <PanelHeader
            iconRole="module.extremes"
            title="Context-specific extremes"
            description="The strongest signals in individual cancers. Use them for tissue-specific follow-up; they do not establish a pan-cancer effect."
          />
          <ImmuneRareSignals recurrence={recurrence} />
        </section>
      </div>
    </div>
  );
}

function ImmuneRecurrencePlot({ recurrence }) {
  const harmful = (recurrence.top_harmful || []).slice(0, 12);
  const protective = (recurrence.top_protective || []).slice(0, 12);
  const rowCount = Math.max(harmful.length, protective.length);
  if (!rowCount) return <div className="empty-inline">No recurrence summary available.</div>;

  const width = 900;
  const rowHeight = 29;
  const height = 76 + rowCount * rowHeight;
  const plot = { left: 170, right: 170, top: 46, bottom: 30 };
  const center = width / 2;
  const maxCount = Math.max(
    1,
    ...harmful.map((row) => Number(row.harmful_cancer_count || 0)),
    ...protective.map((row) => Number(row.protective_cancer_count || 0)),
  );
  const maxSpan = center - plot.left;
  const scale = (value) => (Number(value || 0) / maxCount) * maxSpan;
  const ticks = uniqueNumbers([0, Math.ceil(maxCount / 2), maxCount]);

  return (
    <div className="immune-recurrence-wrap" role="region" aria-label="Scrollable immune gene recurrence plot" tabIndex={0}>
      <svg className="immune-recurrence-svg" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Immune gene recurrence by prognosis">
        <line className="recurrence-center" x1={center} x2={center} y1={plot.top - 14} y2={height - plot.bottom + 4} />
        {ticks.map((tick) => (
          <g key={tick} className="recurrence-axis">
            <line x1={center - scale(tick)} x2={center - scale(tick)} y1={height - plot.bottom} y2={height - plot.bottom + 5} />
            <line x1={center + scale(tick)} x2={center + scale(tick)} y1={height - plot.bottom} y2={height - plot.bottom + 5} />
            <text x={center - scale(tick)} y={height - 8}>{tick}</text>
            {tick !== 0 && <text x={center + scale(tick)} y={height - 8}>{tick}</text>}
          </g>
        ))}
        <text className="recurrence-side-label protective" x={plot.left} y="18">More frequent better prognosis</text>
        <text className="recurrence-side-label harmful" x={width - plot.right} y="18">More frequent worse prognosis</text>
        {Array.from({ length: rowCount }).map((_, index) => {
          const y = plot.top + index * rowHeight;
          const better = protective[index];
          const worse = harmful[index];
          const betterCount = Number(better?.protective_cancer_count || 0);
          const worseCount = Number(worse?.harmful_cancer_count || 0);
          const betterX = center - scale(betterCount);
          const worseX = center + scale(worseCount);
          return (
            <g key={index} className="recurrence-row">
              <line className="recurrence-guide" x1={plot.left - 12} x2={width - plot.right + 12} y1={y} y2={y} />
              {better && (
                <g className="recurrence-lollipop protective">
                  <line x1={center} x2={betterX} y1={y} y2={y} />
                  <circle cx={betterX} cy={y} r={5.5} />
                  <text className="gene-label" x={betterX - 10} y={y + 4} textAnchor="end">{better.gene_symbol}</text>
                  <text className="count-label" x={betterX} y={y - 10} textAnchor="middle">{betterCount}</text>
                  <title>{`${better.gene_symbol}: protective in ${betterCount} cancers; best FDR ${formatP(better.min_protective_fdr)}; top cohort ${better.top_protective_cohort}`}</title>
                </g>
              )}
              {worse && (
                <g className="recurrence-lollipop harmful">
                  <line x1={center} x2={worseX} y1={y} y2={y} />
                  <circle cx={worseX} cy={y} r={5.5} />
                  <text className="gene-label" x={worseX + 10} y={y + 4}>{worse.gene_symbol}</text>
                  <text className="count-label" x={worseX} y={y - 10} textAnchor="middle">{worseCount}</text>
                  <title>{`${worse.gene_symbol}: harmful in ${worseCount} cancers; best FDR ${formatP(worse.min_harmful_fdr)}; top cohort ${worse.top_harmful_cohort}`}</title>
                </g>
              )}
            </g>
          );
        })}
      </svg>
      <div className="pancancer-figure-legend">
        <span><i className="protective" /> HR &lt; 1, better prognosis</span>
        <span><i className="harmful" /> HR &gt; 1, worse prognosis</span>
      </div>
    </div>
  );
}

function ImmuneFrequencyDistribution({ recurrence }) {
  const data = (recurrence.frequency_distribution || [])
    .map((row) => ({
      cancerCount: Number(row.cancer_count || 0),
      harmful: Number(row.harmful_genes || 0),
      protective: Number(row.protective_genes || 0),
    }))
    .filter((row) => row.cancerCount > 0);
  if (!data.length) return <div className="empty-inline">No frequency distribution available.</div>;

  const width = 560;
  const height = 210;
  const plot = { left: 48, right: 18, top: 16, bottom: 42 };
  const innerWidth = width - plot.left - plot.right;
  const innerHeight = height - plot.top - plot.bottom;
  const maxX = Math.max(...data.map((row) => row.cancerCount));
  const maxY = Math.max(1, ...data.flatMap((row) => [row.harmful, row.protective]));
  const scaleX = (value) => plot.left + ((value - 1) / Math.max(1, maxX - 1)) * innerWidth;
  const scaleY = (value) => plot.top + innerHeight - (value / maxY) * innerHeight;
  const linePoints = (key) => data.map((row) => `${scaleX(row.cancerCount)},${scaleY(row[key])}`).join(" ");
  const xTicks = uniqueNumbers([1, 2, 4, 6, 8, 10, maxX].filter((tick) => tick <= maxX));
  const yTicks = niceTicks(maxY, 4);
  const summary = recurrence.summary || {};

  return (
    <div
      className="immune-frequency-wrap"
      role="region"
      aria-label="Scrollable immune gene recurrence distribution"
      tabIndex={0}
    >
      <svg className="immune-frequency-svg" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Immune gene rare versus recurrent distribution">
        <rect className="chart-frame" x={plot.left} y={plot.top} width={innerWidth} height={innerHeight} />
        {xTicks.map((tick) => (
          <g key={`x-${tick}`} className="chart-axis-tick">
            <line x1={scaleX(tick)} x2={scaleX(tick)} y1={plot.top + innerHeight} y2={plot.top + innerHeight + 5} />
            <text x={scaleX(tick)} y={height - 14}>{tick}</text>
          </g>
        ))}
        {yTicks.map((tick) => (
          <g key={`y-${tick}`} className="chart-axis-tick">
            <line x1={plot.left - 5} x2={plot.left} y1={scaleY(tick)} y2={scaleY(tick)} />
            <text className="chart-y-tick-label" x={plot.left - 10} y={scaleY(tick) + 4}>{formatInteger(Math.round(tick))}</text>
          </g>
        ))}
        <polyline className="frequency-line harmful" points={linePoints("harmful")} />
        <polyline className="frequency-line protective" points={linePoints("protective")} />
        {data.map((row) => (
          <g key={row.cancerCount}>
            <circle className="frequency-point harmful" cx={scaleX(row.cancerCount)} cy={scaleY(row.harmful)} r={4.5}>
              <title>{`${formatInteger(row.harmful)} genes harmful in ${row.cancerCount} cancer(s)`}</title>
            </circle>
            <circle className="frequency-point protective" cx={scaleX(row.cancerCount)} cy={scaleY(row.protective)} r={4.5}>
              <title>{`${formatInteger(row.protective)} genes protective in ${row.cancerCount} cancer(s)`}</title>
            </circle>
          </g>
        ))}
        <text className="chart-axis-label" x={(plot.left + width - plot.right) / 2} y={height - 3}>Number of cancer types with FDR hit</text>
        <text className="chart-axis-label y" x={plot.left} y="12">Genes</text>
      </svg>
      <div className="immune-frequency-notes">
        <span><strong>{formatInteger(summary.recurrent_harmful_genes_ge5)}</strong> harmful genes recur in 5+ cancers</span>
        <span><strong>{formatInteger(summary.recurrent_protective_genes_ge5)}</strong> protective genes recur in 5+ cancers</span>
        <span><strong>{formatInteger(summary.one_cancer_protective_genes)}</strong> protective genes appear in one cancer</span>
      </div>
    </div>
  );
}

function ImmuneMetaSpectrum({ genes }) {
  const points = genes
    .map((gene) => {
      const hr = finiteNumber(gene.meta_hr);
      const fdr = finiteNumber(gene.meta_fdr);
      if (!hr || !fdr) return null;
      return {
        gene,
        x: Math.log2(hr),
        y: -Math.log10(Math.max(fdr, 1e-300)),
        hits: finiteNumber(gene.global_fdr_hits) || 0,
        i2: finiteNumber(gene.meta_i_squared) || 0,
        direction: hr >= 1 ? "harmful" : "protective",
      };
    })
    .filter(Boolean);
  if (!points.length) return <div className="empty-inline">No immune gene summary available.</div>;

  const width = 600;
  const height = 240;
  const plot = { left: 48, right: 28, top: 16, bottom: 44 };
  const innerWidth = width - plot.left - plot.right;
  const innerHeight = height - plot.top - plot.bottom;
  const absX = Math.max(0.25, ...points.map((point) => Math.abs(point.x))) * 1.15;
  const yMax = Math.max(2, ...points.map((point) => point.y)) * 1.08;
  const scaleX = (value) => plot.left + ((value + absX) / (2 * absX || 1)) * innerWidth;
  const scaleY = (value) => plot.top + innerHeight - (value / (yMax || 1)) * innerHeight;
  const labels = points.slice(0, 7);
  const xTicks = [-0.5, -0.25, 0, 0.25, 0.5].filter((tick) => Math.abs(tick) <= absX);
  const yTicks = niceTicks(yMax, 4);

  return (
    <div
      className="immune-spectrum-wrap"
      role="region"
      aria-label="Scrollable immune gene meta-analysis spectrum"
      tabIndex={0}
    >
      <svg className="immune-spectrum-svg" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Immune gene meta-analysis spectrum">
        <rect className="chart-frame" x={plot.left} y={plot.top} width={innerWidth} height={innerHeight} />
        <line className="chart-reference" x1={scaleX(0)} x2={scaleX(0)} y1={plot.top} y2={plot.top + innerHeight} />
        {xTicks.map((tick) => (
          <g key={`x-${tick}`} className="chart-axis-tick">
            <line x1={scaleX(tick)} x2={scaleX(tick)} y1={plot.top + innerHeight} y2={plot.top + innerHeight + 5} />
            <text x={scaleX(tick)} y={height - 14}>{tick}</text>
          </g>
        ))}
        {yTicks.map((tick) => (
          <g key={`y-${tick}`} className="chart-axis-tick">
            <line x1={plot.left - 5} x2={plot.left} y1={scaleY(tick)} y2={scaleY(tick)} />
            <text className="chart-y-tick-label" x={plot.left - 10} y={scaleY(tick) + 4}>{tick.toFixed(0)}</text>
          </g>
        ))}
        {points.map((point) => (
          <circle
            key={point.gene.gene_symbol}
            className={`immune-spectrum-dot ${point.direction}`}
            cx={scaleX(point.x)}
            cy={scaleY(point.y)}
            r={5 + Math.min(8, Math.sqrt(point.hits || 1) * 1.6)}
            opacity={0.72 + Math.min(0.24, point.i2 / 350)}
          >
            <title>{`${point.gene.gene_symbol}: meta HR ${formatCompactNumber(point.gene.meta_hr)}, meta FDR ${formatP(point.gene.meta_fdr)}, I2 ${formatPercent(point.gene.meta_i_squared)}`}</title>
          </circle>
        ))}
        {labels.map((point) => (
          <text key={`label-${point.gene.gene_symbol}`} className="chart-point-label" x={scaleX(point.x) + (point.x >= 0 ? 10 : -10)} y={scaleY(point.y) + 4} textAnchor={point.x >= 0 ? "start" : "end"}>
            {point.gene.gene_symbol}
          </text>
        ))}
        <text className="chart-axis-label" x={(plot.left + width - plot.right) / 2} y={height - 3}>log2(meta HR)</text>
        <text className="chart-axis-label y" x={plot.left} y="12">-log10(meta FDR)</text>
      </svg>
      <div className="pancancer-figure-legend">
        <span><i className="harmful" /> Higher expression worse</span>
        <span><i className="protective" /> Higher expression better</span>
      </div>
    </div>
  );
}

function ImmuneRareSignals({ recurrence }) {
  const harmful = (recurrence.rare_harmful || []).slice(0, 8);
  const protective = (recurrence.rare_protective || []).slice(0, 8);
  if (!harmful.length && !protective.length) return <div className="empty-inline">No rare signal summary available.</div>;
  return (
    <div className="immune-rare-grid">
      <div className="immune-rare-lane harmful">
        <span>Worse in one cancer</span>
        {harmful.map((row) => (
          <div key={row.gene_symbol}>
            <strong>{row.gene_symbol}</strong>
            <em>{row.top_harmful_cohort?.replace("TCGA-", "")}</em>
            <small>FDR {formatP(row.min_harmful_fdr)}</small>
          </div>
        ))}
      </div>
      <div className="immune-rare-lane protective">
        <span>Better in one cancer</span>
        {protective.map((row) => (
          <div key={row.gene_symbol}>
            <strong>{row.gene_symbol}</strong>
            <em>{row.top_protective_cohort?.replace("TCGA-", "")}</em>
            <small>FDR {formatP(row.min_protective_fdr)}</small>
          </div>
        ))}
      </div>
    </div>
  );
}

function ImmuneCohortBurden({ cohorts }) {
  const ordered = [...cohorts]
    .sort((a, b) => Number(b.global_fdr_hits || 0) - Number(a.global_fdr_hits || 0))
    .slice(0, 12);
  const maxHits = Math.max(1, ...ordered.map((cohort) => Number(cohort.global_fdr_hits || 0)));
  if (!ordered.length) return <div className="empty-inline">No cohort summary available.</div>;
  return (
    <div className="immune-burden-list">
      {ordered.map((cohort) => {
        const hits = Number(cohort.global_fdr_hits || 0);
        const harmful = Number(cohort.harmful_global_fdr_hits || 0);
        const protective = Number(cohort.protective_global_fdr_hits || 0);
        const harmfulWidth = hits ? (harmful / hits) * 100 : 0;
        const protectiveWidth = hits ? (protective / hits) * 100 : 0;
        return (
          <div key={cohort.cohort} className="immune-burden-row">
            <div>
              <strong>{cohort.cohort.replace("TCGA-", "")}</strong>
              <span>{cohort.top_gene || "..."}</span>
            </div>
            <div className="immune-burden-track" style={{ "--burden-width": `${(hits / maxHits) * 100}%` }}>
              <i className="harmful" style={{ width: `${harmfulWidth}%` }} />
              <i className="protective" style={{ width: `${protectiveWidth}%` }} />
            </div>
            <em>{formatInteger(hits)}</em>
          </div>
        );
      })}
    </div>
  );
}

function ImmuneTermList({ terms }) {
  const ordered = terms.slice(0, 10);
  const maxHits = Math.max(1, ...ordered.map((term) => Number(term.cohort_level_global_fdr_hits || 0)));
  if (!ordered.length) return <div className="empty-inline">No immune term summary available.</div>;
  return (
    <div className="immune-term-list">
      {ordered.map((term) => (
        <div key={term.term_id} className={`immune-term-row ${String(term.source || "").toLowerCase()}`}>
          <div>
            <strong>{term.term_name}</strong>
            <span>{term.source} / {formatInteger(term.panel_genes)} genes / best {term.best_gene || "..."}</span>
          </div>
          <b>{formatInteger(term.cohort_level_global_fdr_hits)}</b>
          <i style={{ width: `${(Number(term.cohort_level_global_fdr_hits || 0) / maxHits) * 100}%` }} />
        </div>
      ))}
    </div>
  );
}

function PanCancerForestPlot({ rows, metaAnalysis, effectScale }) {
  const synthesisEligible = effectScale?.synthesis?.eligible === true;
  const commonScaleRows = rows.filter(
    (row) =>
      row.status === "completed"
      && (scientificNumber(row.common_scale_hazard_ratio) ?? 0) > 0,
  );
  const commonScaleAvailable = synthesisEligible && commonScaleRows.length > 0;
  const [scaleMode, setScaleMode] = useState(
    commonScaleAvailable ? "common" : "standardized",
  );
  useEffect(() => {
    if (!commonScaleAvailable && scaleMode === "common") {
      setScaleMode("standardized");
    }
  }, [commonScaleAvailable, scaleMode]);
  const completed = rows
    .filter((row) => {
      const value = scaleMode === "common"
        ? row.common_scale_hazard_ratio
        : row.hazard_ratio;
      return row.status === "completed" && (scientificNumber(value) ?? 0) > 0;
    })
    .map((row) => (
      scaleMode === "common"
        ? {
          ...row,
          hazard_ratio: row.common_scale_hazard_ratio,
          hr_conf_low: row.common_scale_hr_conf_low,
          hr_conf_high: row.common_scale_hr_conf_high,
          log_hr: row.common_scale_log_hr,
          standard_error: row.common_scale_standard_error,
          p_value: row.common_scale_p_value,
        }
        : row
    ));
  if (!completed.length) return <div className="empty-inline">No completed Cox models available for the forest plot.</div>;
  const ordered = [...completed].sort((a, b) => Number(a.hazard_ratio) - Number(b.hazard_ratio));
  const pooled = scaleMode === "common" && metaAnalysis?.available
    ? metaAnalysis.random_effect
    : null;
  const predictionInterval = scaleMode === "common" && metaAnalysis?.available
    ? metaAnalysis.prediction_interval
    : null;
  const synthesisUnit = effectScale?.synthesis?.unit || "per +1 common input-score unit";
  const axisLabel = scaleMode === "common"
    ? `Hazard ratio ${synthesisUnit}`
    : "Hazard ratio per +1 within-cohort SD";
  const width = 900;
  const rowHeight = 28;
  const pooledHeight = pooled?.hazard_ratio ? 58 : 0;
  const height = 78 + ordered.length * rowHeight + pooledHeight;
  const plot = { left: 124, right: 184, top: 28, bottom: 46 };
  const values = ordered.flatMap((row) => [row.hr_conf_low, row.hazard_ratio, row.hr_conf_high].map((value) => Number(value)).filter(Number.isFinite));
  if (pooled?.hazard_ratio) {
    values.push(...[pooled.hr_conf_low, pooled.hazard_ratio, pooled.hr_conf_high].map((value) => Number(value)).filter(Number.isFinite));
  }
  const logMin = Math.min(Math.log(0.25), ...values.map((value) => Math.log(Math.max(value, 0.001))));
  const logMax = Math.max(Math.log(4), ...values.map((value) => Math.log(Math.max(value, 0.001))));
  const scaleX = (value) => {
    const logValue = Math.log(Math.max(Number(value), 0.001));
    return plot.left + ((logValue - logMin) / (logMax - logMin || 1)) * (width - plot.left - plot.right);
  };
  const axisTicks = [0.25, 0.5, 1, 2, 4].filter((tick) => Math.log(tick) >= logMin && Math.log(tick) <= logMax);
  return (
    <div className="pancancer-forest-block">
      <div className="forest-scale-toolbar">
        <div className="forest-scale-switch" role="group" aria-label="Forest plot effect scale">
          <button
            type="button"
            className={scaleMode === "common" ? "selected" : ""}
            aria-pressed={scaleMode === "common"}
            disabled={!commonScaleAvailable}
            onClick={() => setScaleMode("common")}
          >
            <strong>Common unit</strong>
            <span>Comparable synthesis</span>
          </button>
          <button
            type="button"
            className={scaleMode === "standardized" ? "selected" : ""}
            aria-pressed={scaleMode === "standardized"}
            onClick={() => setScaleMode("standardized")}
          >
            <strong>Within-cohort SD</strong>
            <span>Descriptive effects</span>
          </button>
        </div>
        <small>
          {scaleMode === "common"
            ? `${synthesisUnit}; pooled only within one endpoint and model family.`
            : "Each SD is cohort-specific; no pooled diamond is shown."}
        </small>
      </div>
      <div className="pancancer-forest-scroll" role="region" aria-label={`Scrollable pan-cancer Cox forest plot, ${axisLabel}`} tabIndex={0}>
        <svg className="pancancer-forest" viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`Pan-cancer Cox forest plot, ${axisLabel}`}>
          <line className="forest-reference" x1={scaleX(1)} x2={scaleX(1)} y1={plot.top - 8} y2={height - plot.bottom} />
          {axisTicks.map((tick) => (
            <g key={tick} className="forest-axis-tick">
              <line x1={scaleX(tick)} x2={scaleX(tick)} y1={height - plot.bottom} y2={height - plot.bottom + 5} />
              <text x={scaleX(tick)} y={height - 8}>{tick}</text>
            </g>
          ))}
          <text className="forest-axis-label" x={(plot.left + width - plot.right) / 2} y={height - 24}>{axisLabel}</text>
          {ordered.map((row, index) => {
            const y = plot.top + index * rowHeight;
            const effectClass = row.effect_category || "neutral";
            return (
              <g key={row.cohort} className={`forest-row ${effectClass}`}>
                <rect className="forest-row-band" x="0" y={y - 13} width={width} height={rowHeight} />
                <text x="8" y={y + 5}>{row.cohort}</text>
                <line x1={scaleX(row.hr_conf_low)} x2={scaleX(row.hr_conf_high)} y1={y} y2={y} />
                <circle cx={scaleX(row.hazard_ratio)} cy={y} r={row.significant ? 5 : 4} />
                <text className="forest-hr-label" x={width - plot.right + 18} y={y + 5}>{formatHrValues(row)}</text>
                <title>{`${row.cohort}: ${formatHrValues(row)}; ${axisLabel}.`}</title>
              </g>
            );
          })}
          {pooled?.hazard_ratio && (
            <g className="forest-pooled-row">
              <line x1="0" x2={width} y1={plot.top + ordered.length * rowHeight + 4} y2={plot.top + ordered.length * rowHeight + 4} />
              <text x="8" y={plot.top + ordered.length * rowHeight + 30}>REML + HKSJ</text>
              <polygon points={forestDiamondPoints(scaleX, pooled, plot.top + ordered.length * rowHeight + 25)} />
              <text x={width - plot.right + 18} y={plot.top + ordered.length * rowHeight + 30}>{formatHrValues(pooled)}</text>
              {predictionInterval && (
                <text className="forest-pi-label" x="8" y={plot.top + ordered.length * rowHeight + 49}>
                  95% prediction interval {formatPredictionInterval(predictionInterval)}
                </text>
              )}
              <title>{`REML random-effects HR with HKSJ inference: ${formatHrValues(pooled)}; 95% prediction interval ${formatPredictionInterval(predictionInterval)}.`}</title>
            </g>
          )}
        </svg>
      </div>
    </div>
  );
}

function PanCancerEvidenceLandscape({ rows, fdrThreshold }) {
  const completed = pancancerCompletedRows(rows)
    .map((row) => {
      const logHr = finiteNumber(row.log_hr) ?? Math.log(finiteNumber(row.hazard_ratio) || 1);
      const fdr = finiteNumber(row.fdr);
      const pValue = finiteNumber(row.p_value);
      const evidenceValue = fdr ?? pValue;
      return {
        row,
        x: logHr / Math.log(2),
        y: evidenceValue ? -Math.log10(Math.max(evidenceValue, 1e-300)) : 0,
        evidenceValue,
        events: finiteNumber(row.n_events) || 0,
      };
    })
    .filter((point) => Number.isFinite(point.x) && Number.isFinite(point.y));
  if (!completed.length) return <div className="empty-inline">No completed Cox models available for the evidence landscape.</div>;

  const width = 820;
  const height = 360;
  const plot = { left: 58, right: 34, top: 24, bottom: 58 };
  const innerWidth = width - plot.left - plot.right;
  const innerHeight = height - plot.top - plot.bottom;
  const fdrLine = fdrThreshold ? -Math.log10(Math.max(Number(fdrThreshold), 1e-12)) : null;
  const absX = Math.max(0.75, ...completed.map((point) => Math.abs(point.x))) * 1.08;
  const yMax = Math.max(1.4, fdrLine || 0, ...completed.map((point) => point.y)) * 1.08;
  const scaleX = (value) => plot.left + ((value + absX) / (2 * absX || 1)) * innerWidth;
  const scaleY = (value) => plot.top + innerHeight - (value / (yMax || 1)) * innerHeight;
  const xTicks = [-2, -1, -0.5, 0, 0.5, 1, 2].filter((tick) => Math.abs(tick) <= absX);
  const yTicks = uniqueNumbers([0, fdrLine, Math.ceil(yMax / 2), Math.floor(yMax)].filter((value) => value !== null && value <= yMax));
  const labeled = evidenceLabels(completed);

  return (
    <div className="pancancer-chart-wrap" role="region" aria-label="Scrollable pan-cancer evidence landscape" tabIndex={0}>
      <svg className="pancancer-landscape" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Pan-cancer evidence landscape">
        <rect className="chart-frame" x={plot.left} y={plot.top} width={innerWidth} height={innerHeight} />
        <line className="chart-reference" x1={scaleX(0)} x2={scaleX(0)} y1={plot.top} y2={plot.top + innerHeight} />
        {fdrLine !== null && (
          <g className="chart-threshold">
            <line x1={plot.left} x2={width - plot.right} y1={scaleY(fdrLine)} y2={scaleY(fdrLine)} />
            <text x={width - plot.right - 4} y={scaleY(fdrLine) - 7}>FDR {Number(fdrThreshold).toFixed(2)}</text>
          </g>
        )}
        {xTicks.map((tick) => (
          <g key={`x-${tick}`} className="chart-axis-tick">
            <line x1={scaleX(tick)} x2={scaleX(tick)} y1={plot.top + innerHeight} y2={plot.top + innerHeight + 5} />
            <text x={scaleX(tick)} y={height - 18}>{tick}</text>
          </g>
        ))}
        {yTicks.map((tick) => (
          <g key={`y-${tick}`} className="chart-axis-tick">
            <line x1={plot.left - 5} x2={plot.left} y1={scaleY(tick)} y2={scaleY(tick)} />
            <text className="chart-y-tick-label" x={plot.left - 10} y={scaleY(tick) + 4}>{tick.toFixed(tick < 1 ? 1 : 0)}</text>
          </g>
        ))}
        {completed.map((point) => {
          const radius = 4 + Math.min(5, Math.sqrt(point.events) / 7);
          return (
            <circle
              key={point.row.cohort}
              className={`landscape-dot ${point.row.effect_category || point.row.direction || "neutral"} ${point.row.significant ? "significant" : ""}`}
              cx={scaleX(point.x)}
              cy={scaleY(point.y)}
              r={radius}
            >
              <title>{`${point.row.cohort}: log2(HR) ${point.x.toFixed(2)}, FDR ${formatP(point.row.fdr)}, events ${formatInteger(point.row.n_events)}`}</title>
            </circle>
          );
        })}
        {labeled.map((point) => {
          const anchor = point.x >= 0 ? "start" : "end";
          const dx = point.x >= 0 ? 9 : -9;
          return (
            <text key={`label-${point.row.cohort}`} className="chart-point-label" x={scaleX(point.x) + dx} y={scaleY(point.y) + 4} textAnchor={anchor}>
              {point.row.cohort.replace("TCGA-", "")}
            </text>
          );
        })}
        <text className="chart-axis-label" x={(plot.left + width - plot.right) / 2} y={height - 4}>log2(HR): lower to higher hazard</text>
        <text className="chart-axis-label y" x="16" y={plot.top + 18}>-log10(FDR)</text>
      </svg>
      <PanCancerFigureLegend />
    </div>
  );
}

function PanCancerPowerPrecision({ rows }) {
  const points = pancancerCompletedRows(rows)
    .map((row) => ({
      row,
      events: finiteNumber(row.n_events),
      patients: finiteNumber(row.n_patients),
      precision: finiteNumber(row.standard_error) ? 1 / finiteNumber(row.standard_error) : null,
    }))
    .filter((point) => point.events !== null && point.patients !== null && point.precision !== null);
  if (!points.length) return <div className="empty-inline">No completed Cox models available for the power and precision map.</div>;

  const width = 820;
  const height = 350;
  const plot = { left: 60, right: 34, top: 24, bottom: 58 };
  const innerWidth = width - plot.left - plot.right;
  const innerHeight = height - plot.top - plot.bottom;
  const maxEvents = Math.max(10, ...points.map((point) => point.events)) * 1.05;
  const maxPrecision = Math.max(1, ...points.map((point) => point.precision)) * 1.08;
  const scaleX = (value) => plot.left + (value / maxEvents) * innerWidth;
  const scaleY = (value) => plot.top + innerHeight - (value / maxPrecision) * innerHeight;
  const xTicks = niceTicks(maxEvents, 4);
  const yTicks = niceTicks(maxPrecision, 4);
  const labeled = powerPrecisionLabels(points);

  return (
    <div className="pancancer-chart-wrap" role="region" aria-label="Scrollable pan-cancer power and precision map" tabIndex={0}>
      <svg className="pancancer-power" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Pan-cancer power and precision map">
        <rect className="chart-frame" x={plot.left} y={plot.top} width={innerWidth} height={innerHeight} />
        {xTicks.map((tick) => (
          <g key={`x-${tick}`} className="chart-axis-tick">
            <line x1={scaleX(tick)} x2={scaleX(tick)} y1={plot.top + innerHeight} y2={plot.top + innerHeight + 5} />
            <text x={scaleX(tick)} y={height - 18}>{formatInteger(Math.round(tick))}</text>
          </g>
        ))}
        {yTicks.map((tick) => (
          <g key={`y-${tick}`} className="chart-axis-tick">
            <line x1={plot.left - 5} x2={plot.left} y1={scaleY(tick)} y2={scaleY(tick)} />
            <text className="chart-y-tick-label" x={plot.left - 10} y={scaleY(tick) + 4}>{tick.toFixed(tick >= 10 ? 0 : 1)}</text>
          </g>
        ))}
        {points.map((point) => {
          const radius = 4 + Math.min(8, Math.sqrt(point.patients) / 9);
          return (
            <circle
              key={point.row.cohort}
              className={`power-dot ${point.row.effect_category || point.row.direction || "neutral"} ${point.row.significant ? "significant" : ""}`}
              cx={scaleX(point.events)}
              cy={scaleY(point.precision)}
              r={radius}
            >
              <title>{`${point.row.cohort}: ${formatInteger(point.events)} events, ${formatInteger(point.patients)} patients, Cox SE ${Number(point.row.standard_error).toFixed(3)}`}</title>
            </circle>
          );
        })}
        {labeled.map((point) => {
          const anchor = point.events > maxEvents * 0.78 ? "end" : "start";
          const dx = anchor === "start" ? 9 : -9;
          return (
            <text key={`label-${point.row.cohort}`} className="chart-point-label" x={scaleX(point.events) + dx} y={scaleY(point.precision) + 4} textAnchor={anchor}>
              {point.row.cohort.replace("TCGA-", "")}
            </text>
          );
        })}
        <text className="chart-axis-label" x={(plot.left + width - plot.right) / 2} y={height - 4}>Survival events</text>
        <text className="chart-axis-label y" x="14" y={plot.top + 18}>Precision: 1 / Cox SE</text>
      </svg>
      <PanCancerFigureLegend />
    </div>
  );
}

function PanCancerFigureLegend() {
  return (
    <div className="pancancer-figure-legend" aria-label="Pan-cancer figure legend">
      <span><i className="harmful" /> FDR hit, HR &gt; 1</span>
      <span><i className="protective" /> FDR hit, HR &lt; 1</span>
      <span><i className="neutral" /> Not FDR-significant</span>
    </div>
  );
}

function PanCancerConcordanceMap({ rows, summary, reference, fdrThreshold }) {
  const [filter, setFilter] = useState("all");
  const [sortMode, setSortMode] = useState("evidence");
  const [query, setQuery] = useState("");
  const [selectedCohort, setSelectedCohort] = useState(reference?.cohort || "");
  const enriched = useMemo(() => rows.map((row) => enrichConcordanceRow(row)), [rows]);
  const counts = useMemo(() => concordanceFilterCounts(enriched), [enriched]);
  const referenceRow = enriched.find((row) => row.cohort === reference?.cohort);
  const filtered = useMemo(
    () => sortConcordanceRows(filterConcordanceRows(enriched, filter, query), sortMode),
    [enriched, filter, query, sortMode],
  );
  const selected =
    enriched.find((row) => row.cohort === selectedCohort) ||
    filtered[0] ||
    referenceRow ||
    enriched.find((row) => row.status === "completed") ||
    enriched[0];

  if (!rows.length) return <div className="empty-inline">No cohorts to display.</div>;

  return (
    <div className="concordance-explorer">
      <div className="concordance-toolbar">
        <div className="concordance-filter-set" aria-label="Concordance filters">
          {[
            ["all", "All", counts.all],
            ["hits", "FDR hits", counts.hits],
            ["same", "Same direction", counts.same],
            ["opposite", "Opposite", counts.opposite],
            ["qc", "QC review", counts.qc],
          ].map(([value, label, count]) => (
            <button key={value} type="button" className={filter === value ? "selected" : ""} onClick={() => setFilter(value)}>
              <span>{label}</span>
              <strong>{formatInteger(count)}</strong>
            </button>
          ))}
        </div>
        <label className="concordance-search">
          <TraceIcon role="action.search" size="sm" />
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Find cohort or site" />
        </label>
        <label className="concordance-sort">
          <span>Order</span>
          <select value={sortMode} onChange={(event) => setSortMode(event.target.value)}>
            <option value="evidence">Evidence first</option>
            <option value="effect">Effect magnitude</option>
            <option value="precision">Precision</option>
            <option value="events">Events</option>
            <option value="cohort">Cohort code</option>
          </select>
        </label>
      </div>

      <div className="concordance-summary-strip">
        <div>
          <span>Index signal</span>
          <strong>{referenceRow ? `${referenceRow.shortCode} / ${formatDirectionToken(referenceRow)}` : "Unavailable"}</strong>
          <small>{referenceRow?.status === "completed" ? formatHrValues(referenceRow) : "No completed index model"}</small>
        </div>
        <div>
          <span>FDR threshold</span>
          <strong>{formatP(fdrThreshold)}</strong>
          <small>{formatInteger(summary?.significant || 0)} cohort-level hits</small>
        </div>
        <div>
          <span>Same vs opposite</span>
          <strong>{formatInteger(counts.same)} / {formatInteger(counts.opposite)}</strong>
          <ConcordanceBalance counts={counts} />
        </div>
        <div>
          <span>QC review</span>
          <strong>{formatInteger(counts.qc)}</strong>
          <small>Skipped, failed or PH flag</small>
        </div>
      </div>
      <div className="concordance-glyph-key" aria-label="Concordance glyph legend">
        <span><i className="key-axis" /> HR direction</span>
        <span><i className="key-ring" /> FDR evidence</span>
        <span><i className="key-halo" /> Event fraction</span>
        <span><i className="key-hit" /> FDR hit</span>
        <span><i className="key-qc" /> QC flag</span>
      </div>

      <div className="concordance-workspace">
        <div className="concordance-node-grid" role="list" aria-label="Interactive pan-cancer concordance cohorts">
          {filtered.map((row) => (
            <button
              key={row.cohort}
              type="button"
              role="listitem"
              className={`concordance-glyph-node ${row.effectClass} ${row.concordanceClass} ${row.status !== "completed" ? "not-completed" : ""} ${row.significant ? "fdr-hit" : ""} ${row.qcFlag ? "qc-flag" : ""} ${selected?.cohort === row.cohort ? "selected" : ""}`}
              onClick={() => setSelectedCohort(row.cohort)}
              title={`${row.cohort}: ${panCancerRowTooltip(row)}`}
              style={{
                "--glyph-x": `${row.glyphPosition}%`,
                "--glyph-size": `${row.glyphSize}px`,
                "--evidence-deg": `${row.evidenceDegrees}deg`,
                "--event-rate": row.eventRateRatio,
              }}
            >
              <span className="glyph-stage" aria-hidden="true">
                <span className="glyph-axis" />
                <span className="glyph-event-halo" />
                <span className="glyph-evidence-ring" />
                <span className="glyph-dot" />
                {row.concordance === "reference" && <span className="glyph-reference-mark" />}
                {row.significant && <span className="glyph-hit-mark" />}
                {row.qcFlag && <span className="glyph-qc-mark" />}
              </span>
              <span className="glyph-copy">
                <span className="glyph-topline">
                  <strong>{row.shortCode}</strong>
                  <i>{row.status === "completed" ? formatDirectionToken(row) : row.status}</i>
                </span>
                <span className="glyph-values">
                  <b>{row.status === "completed" ? `HR ${formatCompactNumber(row.hazardRatio)}` : row.code || "Not evaluable"}</b>
                  <em>FDR {formatP(row.fdr)}</em>
                </span>
                <span className="glyph-context">{formatInteger(row.nEvents)} / {formatInteger(row.nPatients)} events</span>
              </span>
            </button>
          ))}
          {!filtered.length && <div className="empty-inline">No cohorts match the active filter.</div>}
        </div>
        <PanCancerConcordanceDetail row={selected} referenceRow={referenceRow} fdrThreshold={fdrThreshold} />
      </div>
    </div>
  );
}

function ConcordanceBalance({ counts }) {
  const total = Math.max((counts.same || 0) + (counts.opposite || 0), 1);
  return (
    <span className="concordance-balance" aria-hidden="true">
      <i className="same" style={{ width: `${((counts.same || 0) / total) * 100}%` }} />
      <i className="opposite" style={{ width: `${((counts.opposite || 0) / total) * 100}%` }} />
    </span>
  );
}

function PanCancerConcordanceDetail({ row, referenceRow, fdrThreshold }) {
  if (!row) return <div className="concordance-detail empty-inline">Select a cohort to inspect concordance evidence.</div>;
  const interpretation = concordanceInterpretation(row, referenceRow, fdrThreshold);
  const temporal = row.time_varying_effect || {};
  const temporalCompleted = temporal.status === "completed";
  const temporalTriggered = ["completed", "skipped", "failed"].includes(temporal.status);
  return (
    <aside className="concordance-detail" aria-label={`${row.cohort} concordance details`}>
      <div className="concordance-detail-header">
        <div>
          <p className="eyebrow">{row.cohort}</p>
          <h3>{getCohortName(row.cohort)}</h3>
        </div>
        <span className={`detail-badge ${row.effectClass}`}>{row.status === "completed" ? formatEffectLabel(row.effect_category) : row.status}</span>
      </div>

      <div className="concordance-detail-grid">
        <div><span>Concordance</span><strong>{formatConcordance(row.concordance)}</strong></div>
        <div><span>Endpoint</span><strong>{row.endpoint || "..."}</strong><small>{formatSourceLabel(row.endpoint_source)}</small></div>
        <div><span>HR per SD</span><strong>{row.status === "completed" ? formatHrValues(row) : "..."}</strong></div>
        <div><span>Evidence</span><strong>p {formatP(row.p_value)} / FDR {formatP(row.fdr)}</strong></div>
        <div><span>Information</span><strong>{formatInteger(row.nEvents)} events</strong><small>{formatInteger(row.nPatients)} patients, {formatPercent((row.eventRate || 0) * 100)} event rate</small></div>
        <div><span>Model QC</span><strong>{row.phPValue === null ? "PH not available" : `PH p ${formatP(row.phPValue)}`}</strong><small>{row.standardError ? `SE ${row.standardError.toFixed(3)}, precision ${formatCompactNumber(row.precision)}` : "SE unavailable"}</small></div>
      </div>

      <div className="concordance-interpretation">
        <strong>{interpretation.title}</strong>
        <span>{interpretation.body}</span>
      </div>

      {temporalTriggered && (
        <div className={`pancancer-temporal-summary ${temporal.status}`}>
          <div>
            <span>Prespecified 2-year diagnostic</span>
            <strong>{temporalCompleted ? "Estimated" : formatModelStatus(temporal)}</strong>
          </div>
          {temporalCompleted && (
            <>
              <div>
                <span>0-2 years</span>
                <strong>{formatHrValues(temporal.periods?.early)}</strong>
              </div>
              <div>
                <span>After 2 years</span>
                <strong>{formatHrValues(temporal.periods?.late)}</strong>
              </div>
              <div>
                <span>Late / early</span>
                <strong>{formatTemporalHrRatio(temporal.change)}</strong>
              </div>
            </>
          )}
          {!temporalCompleted && <small>{temporal.reason}</small>}
        </div>
      )}

      {!!row.warnings?.length && (
        <div className="concordance-warning-list">
          {row.warnings.slice(0, 3).map((warning) => <span key={warning}>{warning}</span>)}
        </div>
      )}
    </aside>
  );
}

function PanCancerHeatmap({ rows }) {
  if (!rows.length) return <div className="empty-inline">No cohorts to display.</div>;
  return (
    <div className="pancancer-heatmap">
      {rows.map((row) => (
        <div key={row.cohort} className={`pancancer-tile ${row.effect_category || row.status}`} title={`${row.cohort}: ${panCancerRowTooltip(row)}`}>
          <strong>{row.cohort.replace("TCGA-", "")}</strong>
          <span>{shortEffectLabel(row)}</span>
        </div>
      ))}
    </div>
  );
}

function PanCancerSummaryCounts({ summary }) {
  const effects = summary.effect_counts || {};
  const concordance = summary.concordance_counts || {};
  return (
    <div className="pancancer-counts">
      <div><span>Harmful FDR hits</span><strong>{formatInteger(effects.harmful || 0)}</strong></div>
      <div><span>Protective FDR hits</span><strong>{formatInteger(effects.protective || 0)}</strong></div>
      <div><span>Same direction</span><strong>{formatInteger((concordance.same_direction_significant || 0) + (concordance.same_direction_not_significant || 0))}</strong></div>
      <div><span>Opposite direction</span><strong>{formatInteger((concordance.opposite_direction_significant || 0) + (concordance.opposite_direction_not_significant || 0))}</strong></div>
    </div>
  );
}

function PanCancerTable({ rows }) {
  const ordered = [...rows].sort((a, b) => {
    const aFdr = scientificNumber(a.fdr) ?? Number.POSITIVE_INFINITY;
    const bFdr = scientificNumber(b.fdr) ?? Number.POSITIVE_INFINITY;
    return aFdr - bFdr || String(a.cohort).localeCompare(String(b.cohort));
  });
  return (
    <div className="table-scroll pancancer-table-scroll" role="region" aria-label="Scrollable pan-cancer cohort results" tabIndex={0}>
      <table aria-label="Pan-cancer cohort estimates">
        <thead>
          <tr>
            <th scope="col">Cohort</th>
            <th scope="col">Endpoint</th>
            <th scope="col">Primary n / events</th>
            <th scope="col">RNA population</th>
            <th scope="col">Primary HR</th>
            <th scope="col">Primary FDR</th>
            <th scope="col">Ordinal model</th>
            <th scope="col">Adjusted n / events</th>
            <th scope="col">Adjusted HR</th>
            <th scope="col">Adjusted FDR</th>
            <th scope="col">Concordance</th>
            <th scope="col">Sensitivity readout</th>
          </tr>
        </thead>
        <tbody>
          {ordered.map((row) => (
            <tr key={row.cohort}>
              <td><strong>{row.cohort}</strong><br /><span>{getCohortName(row.cohort)}</span></td>
              <td>{row.endpoint || "..."}<br /><span>{formatSourceLabel(row.endpoint_source)}</span></td>
              <td>{row.status === "completed" ? `${formatInteger(row.n_patients)} / ${formatInteger(row.n_events)}` : "..."}</td>
              <td>
                {row.status === "completed"
                  ? <><strong>{row.sample_selection?.sample_population?.label || "Declared primary disease"}</strong><br /><span>{formatSampleTypeCounts(row.sample_selection?.retained_sample_types)}</span></>
                  : "..."}
              </td>
              <td>{row.status === "completed" ? formatHrValues(row) : "..."}</td>
              <td>{formatP(row.fdr)}</td>
              <td>{row.adjusted_status === "completed" ? formatAdjustmentModel(row.selected_adjusted_model) : "Not evaluable"}</td>
              <td>{row.adjusted_status === "completed" ? `${formatInteger(row.adjusted_n_patients)} / ${formatInteger(row.adjusted_n_events)}` : "..."}</td>
              <td>{row.adjusted_status === "completed" ? formatAdjustedHrValues(row) : "..."}</td>
              <td>{formatP(row.adjusted_fdr)}</td>
              <td>{formatConcordance(row.concordance)}</td>
              <td>
                {row.status !== "completed"
                  ? row.reason || row.code
                  : row.adjusted_status === "completed"
                    ? formatClinicalSensitivity(row.clinical_sensitivity)
                    : <span title={row.adjusted_reason || ""}>No usable stage / grade</span>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function BiologicalAnnotations({ annotations }) {
  const entries = Object.entries(annotations);
  if (!entries.length) return <div className="empty-inline">No subtype annotation fields detected for this scope.</div>;
  return (
    <div className="annotation-list">
      {entries.map(([cohort, payload]) => (
        <div key={cohort}>
          <strong>{cohort}</strong>
          {payload.fields?.map((field) => (
            <small key={field.name}>
              {field.label || field.name}
              {field.non_missing_patients != null && field.patient_count != null
                ? ` · ${field.non_missing_patients}/${field.patient_count} patients`
                : ""}
              {": "}
              {field.distribution?.slice(0, 3).map((item) => `${item.label} (${item.count})`).join(", ") || "present"}
            </small>
          ))}
        </div>
      ))}
    </div>
  );
}

function EndpointCoverageTable({ items }) {
  if (!items.length) return <div className="empty-inline">No endpoint coverage available.</div>;
  const visible = items
    .filter((item) => item.available || Number(item.patients || 0) > 0)
    .slice(0, 80);
  if (!visible.length) return <div className="empty-inline">No endpoint coverage available.</div>;
  return (
    <div
      className="table-scroll compact"
      role="region"
      aria-label="Scrollable endpoint coverage table"
      tabIndex={0}
    >
      <table aria-label="Survival endpoint coverage by cohort">
        <thead>
          <tr>
            <th scope="col">Cohort</th>
            <th scope="col">Endpoint</th>
            <th scope="col">Source</th>
            <th scope="col">Patients</th>
            <th scope="col">Events</th>
            <th scope="col">Status</th>
          </tr>
        </thead>
        <tbody>
          {visible.map((item) => (
            <tr key={`${item.cohort}-${item.value}`}>
              <td>{item.cohort}</td>
              <td>{item.label}</td>
              <td>{formatSourceLabel(item.source)}</td>
              <td>{formatInteger(item.patients)}</td>
              <td>{formatInteger(item.events)}</td>
              <td>{item.available ? "Available" : "QC limited"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function PaperExamplesPage({ catalog, loading, error, onRetry }) {
  const [selectedCaseId, setSelectedCaseId] = useState("");
  const [selectedMethodId, setSelectedMethodId] = useState("");
  const [selectedAdvancedId, setSelectedAdvancedId] = useState("");
  const [caseFilter, setCaseFilter] = useState("main");

  if (loading && !catalog) {
    return (
      <section className="paper-examples-page">
        <div className="loading-state compact">
          <TraceIcon role="status.loading" size="lg" className="spin" label="Loading reference analyses" />
          <div>
            <p className="eyebrow">Reproducible reference analyses</p>
            <h2>Loading benchmark figures and diagnostics</h2>
          </div>
        </div>
      </section>
    );
  }
  if (error) {
    return (
      <section className="paper-examples-page">
        <div className="error-box">
          <TraceIcon role="status.error" size="md" tone="error" />
          <span>{error}</span>
          <button type="button" className="tertiary-button" onClick={onRetry}>Retry</button>
        </div>
      </section>
    );
  }
  if (!catalog) return null;

  const allCases = catalog.single_gene_cases || [];
  const visibleCases = caseFilter === "all"
    ? allCases
    : allCases.filter((item) => item.section === caseFilter);
  const selectedCase =
    allCases.find((item) => item.id === selectedCaseId)
    || visibleCases[0]
    || allCases[0];
  const selectedMethod =
    selectedCase?.methods?.find((item) => item.method === selectedMethodId)
    || selectedCase?.methods?.find((item) => item.method === selectedCase.representative_method)
    || selectedCase?.methods?.[0];
  const advancedExamples = catalog.advanced_examples || [];
  const selectedAdvanced =
    advancedExamples.find((item) => item.result_id === selectedAdvancedId)
    || advancedExamples[0];
  const selectedDiagnostics = paperMethodDiagnostics(selectedMethod);

  function chooseCase(exampleCase, methodId = "") {
    setSelectedCaseId(exampleCase.id);
    setSelectedMethodId(methodId || exampleCase.representative_method || "median");
  }

  return (
    <section className="paper-examples-page">
      <section className="paper-example-section">
        <div className="paper-section-heading">
          <div>
            <p className="eyebrow">Figure atlas 01</p>
            <h2>Continuous marker profile</h2>
            <p>
              Each case starts with one cutpoint-independent Cox estimate over the complete eligible
              expression population, followed by a spline check for nonlinearity.
            </p>
          </div>
          <div className="example-filter" aria-label="Filter reference analyses">
            {[
              ["main", "Main paper"],
              ["supplementary", "Diagnostics"],
              ["all", "All 11"],
            ].map(([value, label]) => (
              <button
                key={value}
                type="button"
                className={caseFilter === value ? "selected" : ""}
                onClick={() => {
                  setCaseFilter(value);
                  const next = value === "all"
                    ? allCases[0]
                    : allCases.find((item) => item.section === value);
                  if (next) chooseCase(next);
                }}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
        <div className="paper-case-selector" role="tablist" aria-label="Benchmark marker">
          {visibleCases.map((exampleCase) => (
            <button
              key={exampleCase.id}
              type="button"
              role="tab"
              aria-selected={selectedCase?.id === exampleCase.id}
              className={selectedCase?.id === exampleCase.id ? "selected" : ""}
              onClick={() => chooseCase(exampleCase)}
            >
              <strong>{exampleCase.gene_symbol}</strong>
              <span>{exampleCase.cohort.replace("TCGA-", "")} · {exampleCase.endpoint}</span>
            </button>
          ))}
        </div>

        {selectedCase && selectedMethod && (
          <div className="paper-case-explorer">
          <div className="paper-case-header">
            <div>
              <span className={`example-purpose ${selectedCase.section}`}>{selectedCase.purpose}</span>
              <h2>{selectedCase.title}</h2>
              <p>{selectedCase.interpretation}</p>
            </div>
            <div className="paper-case-counts">
              <span><strong>{formatInteger(selectedCase.continuous?.n_patients)} / {formatInteger(selectedCase.continuous?.n_events)}</strong> continuous n / events</span>
              <span><strong>{formatHrValues(selectedCase.continuous)}</strong> HR per +1 SD</span>
            </div>
          </div>

          <PaperContinuousReference exampleCase={selectedCase} />

          <div className="paper-subanalysis-heading">
            <div>
              <p className="eyebrow">Grouped analysis</p>
              <h3>Cutpoint sensitivity</h3>
            </div>
            <p>
              Grouped KM, Cox and RMST estimates show how the presentation changes after applying
              each prespecified cutpoint.
            </p>
          </div>

          <div className="paper-method-tabs" role="tablist" aria-label="Cutpoint method">
            {selectedCase.methods.map((method) => (
              <button
                key={method.method}
                type="button"
                role="tab"
                aria-selected={selectedMethod.method === method.method}
                className={`${selectedMethod.method === method.method ? "selected " : ""}${exampleProfileClass(method)}`}
                onClick={() => setSelectedMethodId(method.method)}
              >
                <span>{method.label}</span>
                <small>{formatMethodProfileLabel(method)}</small>
              </button>
            ))}
          </div>

          <div className="paper-method-metrics">
            <Metric label="Patients / events" value={`${formatInteger(selectedMethod.n_patients)} / ${formatInteger(selectedMethod.n_events)}`} />
            <Metric label="Within-scenario Holm p" value={formatP(selectedMethod.grouped_holm_p_value)} />
            <Metric
              label="Univariable HR"
              value={selectedMethod.hazard_ratio
                ? `${formatCompactNumber(selectedMethod.hazard_ratio)} (${formatCompactNumber(selectedMethod.hr_conf_low)}–${formatCompactNumber(selectedMethod.hr_conf_high)})`
                : "Unavailable"}
            />
            <Metric
              label="Adjusted HR"
              value={selectedMethod.adjusted_hr
                ? `${formatCompactNumber(selectedMethod.adjusted_hr)} (${formatCompactNumber(selectedMethod.adjusted_hr_conf_low)}–${formatCompactNumber(selectedMethod.adjusted_hr_conf_high)}), p ${formatP(selectedMethod.adjusted_p_value)}`
                : "Unavailable"}
            />
            <Metric
              label="Events / parameter"
              value={formatSparseModelInformation(
                selectedDiagnostics.eventsPerParameter,
                selectedDiagnostics.informationStatus,
              )}
            />
            <Metric
              label="Firth sensitivity"
              value={formatPaperFirthSensitivity(selectedDiagnostics)}
            />
            <Metric
              label="RMST Δ at tau"
              value={selectedMethod.rmst_delta_days === null
                ? "Unavailable"
                : `${formatCompactNumber(selectedMethod.rmst_delta_days)} d at ${formatCompactNumber(selectedMethod.rmst_tau_days)} d`}
            />
            <Metric label="Marker PH p" value={formatP(selectedMethod.marker_ph_p_value)} />
            <Metric label="Model PH p" value={formatP(selectedMethod.global_ph_p_value)} />
            <Metric
              label="Continuous-implied HR"
              value={selectedMethod.continuous_implied_same_contrast_hr === null
                ? "Unavailable"
                : `${formatCompactNumber(selectedMethod.continuous_implied_same_contrast_hr)} for ${formatCompactNumber(selectedMethod.same_contrast_delta_sd)} SD`}
            />
            <Metric
              label="Grouped / implied |log HR|"
              value={selectedMethod.same_contrast_log_hr_amplification_ratio === null
                ? "Unavailable"
                : formatCompactNumber(selectedMethod.same_contrast_log_hr_amplification_ratio)}
            />
          </div>

          <TimeVaryingEffectTable
            title="Prespecified follow-up-period diagnostic"
            models={[{
              model: selectedMethod.adjusted_model || "univariable",
              label: selectedMethod.adjusted_model
                ? formatContinuousModelLabel(selectedMethod.adjusted_model)
                : "Univariable",
              ph_p_value: selectedMethod.marker_ph_p_value,
              time_varying_effect: selectedMethod.time_varying_effect,
            }]}
          />

          <div className="paper-figure-grid">
            <PaperAnalysisFigure
              title="Kaplan–Meier estimate"
              description={`${selectedCase.gene_symbol} · ${selectedCase.cohort} · ${selectedCase.endpoint} · ${selectedMethod.label}`}
              source={selectedMethod.figures?.km}
              alt={`Kaplan-Meier figure for ${selectedCase.gene_symbol} in ${selectedCase.cohort}, ${selectedCase.endpoint}, using ${selectedMethod.label}`}
            />
            <PaperAnalysisFigure
              title="Cox model summary"
              description="Univariable and eligible clinical-adjustment estimates with confidence intervals."
              source={selectedMethod.figures?.cox}
              alt={`Cox model figure for ${selectedCase.gene_symbol} in ${selectedCase.cohort} using ${selectedMethod.label}`}
            />
          </div>
          <div className={`paper-interpretation ${exampleProfileClass(selectedMethod)}${selectedMethod.marker_ph_flagged ? " has-ph-caution" : ""}`}>
            <strong>{formatMethodProfileSummary(selectedMethod)}</strong>
            <span>
              Benchmark audit <code>{shortHash(selectedMethod.audit_hash)}</code>. Log-rank, Cox and RMST are
              related views of the same outcomes, not independent votes. PH diagnostics modify interpretation
              and do not act as exclusion rules.
            </span>
          </div>
          </div>
        )}
      </section>

      <section className="paper-example-section">
        <div className="paper-section-heading">
          <div>
            <p className="eyebrow">Figure atlas 02</p>
            <h2>Cutpoint sensitivity map</h2>
            <p>
              Each cell reports the within-scenario Holm result for one of four prespecified
              grouped rules. Support across all four is the primary grouped summary. The PH marker
              identifies a biomarker-term caution; it does not discard the association.
            </p>
          </div>
        </div>
        <CutpointEvidenceMatrix
          cases={visibleCases}
          cutpoints={catalog.cutpoints || []}
          selectedCaseId={selectedCase?.id}
          selectedMethodId={selectedMethod?.method}
          onSelect={chooseCase}
        />
      </section>

      <section className="paper-example-section">
        <div className="paper-section-heading">
          <div>
            <p className="eyebrow">Figure atlas 03</p>
            <h2>Advanced workflow examples</h2>
            <p>
              Weighted signatures, two-marker grouping and continuous pan-cancer models are paired
              with diagnostic counterexamples using the same rendering and provenance rules.
            </p>
          </div>
        </div>
        <div className="advanced-example-tabs" role="tablist" aria-label="Advanced reference analyses">
          {advancedExamples.map((example) => (
            <button
              key={example.result_id}
              type="button"
              role="tab"
              aria-selected={selectedAdvanced?.result_id === example.result_id}
              className={selectedAdvanced?.result_id === example.result_id ? "selected" : ""}
              onClick={() => setSelectedAdvancedId(example.result_id)}
            >
              <span>{example.section === "main" ? "Main example" : "Diagnostic"}</span>
              <strong>{example.label}</strong>
              <small>{example.cohort} · {example.endpoint}</small>
            </button>
          ))}
        </div>
        {selectedAdvanced && <AdvancedPaperExample example={selectedAdvanced} />}
      </section>

      <section className="paper-provenance-note">
        <TraceIcon role="file.archive" size="md" />
        <div>
          <strong>{catalog.publication?.status}</strong>
          <span>
            Data snapshot <code>{shortHash(catalog.publication?.data_snapshot_hash)}</code>.
            Figures are pinned to the manuscript benchmark and are not removed by normal public-job retention.
          </span>
        </div>
      </section>
    </section>
  );
}

function PaperContinuousReference({ exampleCase }) {
  const continuous = exampleCase.continuous || {};
  const spline = continuous.spline || {};
  const completed = continuous.status === "completed";
  const splineCompleted = spline.status === "completed";
  const profile = spline.profile || [];
  const percentileRows = profile.filter((row) =>
    [5, 25, 50, 75, 95].includes(Number(row.percentile))
  );
  const eventsPerParameter = continuous.adjusted_model
    ? continuous.adjusted_events_per_parameter
    : continuous.events_per_parameter;
  const informationStatus = continuous.adjusted_model
    ? continuous.adjusted_information_status
    : continuous.information_status;
  const firthStatus = continuous.adjusted_model
    ? continuous.adjusted_firth_status
    : continuous.firth_status;
  const temporalIsAdjusted = Boolean(
    continuous.adjusted_time_varying_effect?.status
  );
  const temporalEffect = temporalIsAdjusted
    ? continuous.adjusted_time_varying_effect
    : continuous.univariable_time_varying_effect;
  const temporalModel = {
    model: temporalIsAdjusted
      ? continuous.adjusted_model
      : "continuous_univariable",
    label: temporalIsAdjusted
      ? formatContinuousModelLabel(continuous.adjusted_model)
      : "Continuous univariable",
    ph_p_value: temporalIsAdjusted
      ? continuous.adjusted_marker_ph_p_value
      : continuous.marker_ph_p_value,
    time_varying_effect: temporalEffect,
  };

  if (!completed) {
    return (
      <div className="paper-continuous-unavailable">
        Continuous reference unavailable in this frozen benchmark. The case must be regenerated
        under the current analysis pipeline.
      </div>
    );
  }

  return (
    <div className="paper-continuous-reference">
      <div className="paper-continuous-metrics">
        <Metric
          label="Linear HR per +1 SD"
          value={formatHrValues(continuous)}
        />
        <Metric
          label="Linear Cox p / BH q"
          value={`${formatP(continuous.p_value)} / ${formatP(continuous.bh_p_value)}`}
        />
        <Metric
          label={continuous.adjusted_model
            ? `Adjusted HR · ${formatContinuousModelLabel(continuous.adjusted_model)}`
            : "Adjusted HR"}
          value={continuous.adjusted_hr != null
            ? `${formatCompactNumber(continuous.adjusted_hr)} (${formatCompactNumber(continuous.adjusted_hr_conf_low)}–${formatCompactNumber(continuous.adjusted_hr_conf_high)}), p ${formatP(continuous.adjusted_p_value)}`
            : "Unavailable"}
        />
        <Metric
          label="Nonlinearity p / BH q"
          value={`${formatP(spline.nonlinearity_p_value)} / ${formatP(spline.nonlinearity_bh_p_value)}`}
        />
        <Metric
          label="Events / parameter"
          value={formatSparseModelInformation(eventsPerParameter, informationStatus)}
        />
        <Metric
          label="Firth sensitivity"
          value={firthStatus === "not_triggered" ? "Not triggered" : formatLabel(firthStatus || "Not evaluable")}
        />
        <Metric label="Marker PH p" value={formatP(continuous.adjusted_marker_ph_p_value)} />
        <Metric label="Population hash" value={shortHash(continuous.population_hash)} />
      </div>
      <TimeVaryingEffectTable
        title="Prespecified continuous effect over follow-up"
        models={[temporalModel]}
      />
      <div className="paper-continuous-body">
        <PaperAnalysisFigure
          title="Continuous effect profile"
          description={`${exampleCase.gene_symbol} · hazard ratio relative to median expression · 95% confidence interval`}
          source={continuous.figure}
          alt={`Continuous spline effect profile for ${exampleCase.gene_symbol} in ${exampleCase.cohort}, ${exampleCase.endpoint}`}
        />
        <div className="paper-continuous-reading">
          <span className="evidence-label">Model reading</span>
          <strong>
            {!splineCompleted
              ? "The spline profile was not estimable for this event count."
              : spline.nonlinearity_p_value < 0.05
              ? "The effect profile departs from a linear log-hazard trend."
              : "No strong departure from a linear log-hazard trend was detected."}
          </strong>
          <p>
            The continuous model uses all {formatInteger(continuous.n_patients)} eligible
            expression-complete patients and does not use the selected cutpoint.
          </p>
          {percentileRows.length > 0 && (
            <div className="paper-percentile-table" role="region" aria-label="Selected continuous effect percentiles" tabIndex={0}>
              <table aria-label="Continuous reference estimates">
                <thead>
                  <tr>
                    <th scope="col">Percentile</th>
                    <th scope="col">HR</th>
                    <th scope="col">95% CI</th>
                  </tr>
                </thead>
                <tbody>
                  {percentileRows.map((row) => (
                    <tr key={row.percentile}>
                      <td>{formatInteger(row.percentile)}</td>
                      <td>{formatCompactNumber(row.hazard_ratio)}</td>
                      <td>{formatCompactNumber(row.hr_conf_low)}–{formatCompactNumber(row.hr_conf_high)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function CutpointEvidenceMatrix({
  cases,
  cutpoints,
  selectedCaseId,
  selectedMethodId,
  onSelect,
}) {
  if (!cases.length) return <div className="empty-inline">No examples match this section.</div>;
  return (
    <div className="paper-matrix-scroll" role="region" aria-label="Scrollable cutpoint evidence matrix" tabIndex={0}>
      <div
        className="paper-evidence-matrix"
        style={{ "--method-count": Math.max(1, cutpoints.length) }}
      >
        <div className="matrix-corner">Marker · endpoint</div>
        {cutpoints.map((cutpoint) => <div className="matrix-method" key={cutpoint.id}>{cutpoint.label}</div>)}
        {cases.map((exampleCase) => (
          <React.Fragment key={exampleCase.id}>
            <button
              type="button"
              className={`matrix-case${selectedCaseId === exampleCase.id ? " selected" : ""}`}
              onClick={() => onSelect(exampleCase)}
            >
              <strong>{exampleCase.gene_symbol}</strong>
              <span>{exampleCase.cohort.replace("TCGA-", "")} · {exampleCase.endpoint}</span>
            </button>
            {cutpoints.map((cutpoint) => {
              const method = exampleCase.methods.find((item) => item.method === cutpoint.id);
              const selected = selectedCaseId === exampleCase.id && selectedMethodId === cutpoint.id;
              return (
                <button
                  key={`${exampleCase.id}-${cutpoint.id}`}
                  type="button"
                  className={`matrix-evidence ${exampleProfileClass(method)}${method?.marker_ph_flagged ? " has-ph-caution" : ""}${selected ? " selected" : ""}`}
                  onClick={() => onSelect(exampleCase, cutpoint.id)}
                  aria-label={`${exampleCase.gene_symbol}, ${cutpoint.label}: ${formatMethodProfileSummary(method)}`}
                  title={`${formatMethodProfileSummary(method)} · Holm p ${formatP(method?.grouped_holm_p_value)}`}
                >
                  <i aria-hidden="true" />
                  <span>{formatMatrixQLabel(method)}</span>
                  {method?.marker_ph_flagged && <b>PH</b>}
                </button>
              );
            })}
          </React.Fragment>
        ))}
      </div>
      <div className="paper-matrix-legend">
        <span><i className="q-below" /> Holm p ≤ .05</span>
        <span><i className="q-above" /> Holm p &gt; .05</span>
        <span><i className="ph-warning" /> Marker-specific PH caution</span>
      </div>
    </div>
  );
}

function PaperAnalysisFigure({ title, description, source, alt }) {
  if (!source) {
    return (
      <figure className="paper-analysis-figure unavailable">
        <div className="paper-figure-placeholder"><TraceIcon role="file.image" size="lg" /><span>Figure unavailable for this model</span></div>
        <figcaption><strong>{title}</strong><span>{description}</span></figcaption>
      </figure>
    );
  }
  const href = apiUrl(source);
  return (
    <figure className="paper-analysis-figure">
      <a href={href} target="_blank" rel="noreferrer" title={`Open ${title}`}>
        <img src={href} alt={alt} loading="lazy" />
      </a>
      <figcaption>
        <span><strong>{title}</strong><small>{description}</small></span>
        <a href={href} target="_blank" rel="noreferrer"><TraceIcon role="action.download" size="sm" /> Full size</a>
      </figcaption>
    </figure>
  );
}

function AdvancedPaperExample({ example }) {
  const isPancancer = example.figure_type === "pancancer";
  const isCombined = example.kind === "two_marker" || example.kind === "diagnostic_two_signature";
  return (
    <article className="advanced-example-detail">
      <div className="advanced-example-header">
        <div>
          <span className={`example-purpose ${example.section}`}>{example.section === "main" ? "Main paper" : "Diagnostic counterexample"}</span>
          <h2>{example.label}</h2>
          <p>{example.interpretation}</p>
        </div>
        <div className="advanced-example-result">
          <span>Primary result</span>
          <strong>{example.summary}</strong>
          {isPancancer && example.pancancer?.pipeline_version && (
            <code className="advanced-example-version">{example.pancancer.pipeline_version}</code>
          )}
        </div>
      </div>
      <div className="paper-method-metrics advanced">
        <Metric label="Cohort" value={example.cohort} />
        <Metric label="Patients / events" value={`${formatInteger(example.n_patients)} / ${formatInteger(example.n_events)}`} />
        <Metric label={example.primary_statistic || "Primary statistic"} value={formatP(example.primary_p_value)} />
        {isPancancer ? (
          <>
            <Metric
              label="Heterogeneity I²"
              value={example.heterogeneity_i2 === null ? "..." : formatPercent(example.heterogeneity_i2)}
            />
            <Metric label="Opposite FDR hits" value={formatInteger(example.opposite_significant)} />
          </>
        ) : isCombined ? (
          <>
            <Metric label="Interaction p" value={formatP(example.interaction_p_value)} />
            <Metric label="Global PH p" value={formatP(example.ph_global_p_value)} />
            <Metric
              label="Events / parameter"
              value={formatSparseModelInformation(example.events_per_parameter, example.information_status)}
            />
            <Metric
              label="Firth sensitivity"
              value={formatPaperFirthSensitivity({
                firthStatus: example.firth_status,
                firthHr: example.firth_hr,
                firthHrConfLow: example.firth_hr_conf_low,
                firthHrConfHigh: example.firth_hr_conf_high,
                firthPValue: example.firth_p_value,
              })}
            />
          </>
        ) : (
          <>
            <Metric label="Adjusted continuous p" value={formatP(example.adjusted_p_value)} />
            <Metric label="Nonlinearity p" value={formatP(example.nonlinearity_p_value)} />
            <Metric label="Marker PH p" value={formatP(example.ph_marker_p_value)} />
            <Metric label="Grouped log-rank p" value={formatP(example.grouped_logrank_p_value)} />
            <Metric
              label="Events / parameter"
              value={formatSparseModelInformation(example.events_per_parameter, example.information_status)}
            />
            <Metric
              label="Firth sensitivity"
              value={formatPaperFirthSensitivity({
                firthStatus: example.firth_status,
                firthHr: example.firth_hr,
                firthHrConfLow: example.firth_hr_conf_low,
                firthHrConfHigh: example.firth_hr_conf_high,
                firthPValue: example.firth_p_value,
              })}
            />
          </>
        )}
      </div>
      {isPancancer ? (
        <div className="paper-pancancer-figures">
          {example.pancancer?.clinical_sensitivity?.available && (
            <PanCancerSensitivityPanel
              sensitivity={example.pancancer.clinical_sensitivity}
              rows={example.pancancer.results || []}
              scanId={example.pancancer.scan_id || example.result_id}
            />
          )}
          <section>
            <PanelHeader
              iconRole="module.cohortEffects"
              title={`${example.marker} cohort effects`}
              description="Continuous Cox effects with common-scale REML synthesis and HKSJ inference when effects are comparable."
            />
            <PanCancerForestPlot
              rows={example.pancancer?.results || []}
              metaAnalysis={example.pancancer?.meta_analysis}
              effectScale={example.pancancer?.effect_scale}
            />
          </section>
          <section>
            <PanelHeader
              iconRole="module.evidence"
              title="Evidence landscape"
              description="Effect direction and FDR evidence across every evaluable cancer."
            />
            <PanCancerEvidenceLandscape
              rows={example.pancancer?.results || []}
              fdrThreshold={example.pancancer?.fdr_threshold || 0.1}
            />
          </section>
          <section>
            <PanelHeader
              iconRole="module.precision"
              title="Power and precision"
              description="Event counts and model precision expose where apparent differences are fragile."
            />
            <PanCancerPowerPrecision rows={example.pancancer?.results || []} />
          </section>
        </div>
      ) : (
        <div className="paper-figure-grid advanced">
          {example.figures?.continuous && (
            <PaperAnalysisFigure
              title="Continuous effect profile"
              description={`${example.marker} · cutpoint-independent spline profile`}
              source={example.figures.continuous}
              alt={`${example.label} continuous effect profile`}
            />
          )}
          <PaperAnalysisFigure
            title="Kaplan–Meier result"
            description={`${example.marker} · ${example.cohort} · ${example.endpoint}`}
            source={example.figures?.km}
            alt={`${example.label} Kaplan-Meier benchmark figure`}
          />
          <PaperAnalysisFigure
            title="Cox model summary"
            description={example.adjustment_status || "Eligible model estimates and diagnostics."}
            source={example.figures?.cox}
            alt={`${example.label} Cox model benchmark figure`}
          />
        </div>
      )}
      <div className="advanced-example-limitation">
        <TraceIcon role="status.caution" size="sm" tone="caution" />
        <span><strong>Interpretation boundary</strong>{example.limitation}</span>
      </div>
    </article>
  );
}

function exampleProfileClass(method) {
  if (!method) return "unavailable";
  if (method.grouped_holm_p_value === null || method.grouped_holm_p_value === undefined) return "q-unavailable";
  return method.grouped_holm_below_alpha ? "q-below" : "q-above";
}

function formatMethodProfileLabel(method) {
  if (!method) return "Unavailable";
  const holmLabel = method.grouped_holm_p_value === null || method.grouped_holm_p_value === undefined
    ? "Holm unavailable"
    : method.grouped_holm_below_alpha
      ? "Holm ≤ .05"
      : "Holm > .05";
  return method.marker_ph_flagged ? `${holmLabel} · marker PH` : holmLabel;
}

function formatMatrixQLabel(method) {
  if (!method || method.grouped_holm_p_value === null || method.grouped_holm_p_value === undefined) return "n/a";
  return method.grouped_holm_below_alpha ? "p≤.05" : "p>.05";
}

function formatMethodProfileSummary(method) {
  if (!method) return "Analysis unavailable";
  const holmLabel = method.grouped_holm_p_value === null || method.grouped_holm_p_value === undefined
    ? "Holm p unavailable"
    : `Holm p ${formatP(method.grouped_holm_p_value)}`;
  const notes = method.profile_notes || [];
  return notes.length ? `${holmLabel}. ${notes.join("; ")}.` : holmLabel;
}

function shortHash(value) {
  const normalized = String(value || "");
  return normalized ? `${normalized.slice(0, 12)}…` : "unavailable";
}

function ApiMcpPage() {
  const [copiedEndpoint, setCopiedEndpoint] = useState("");
  const restBaseUrl = absoluteAppUrl("/api/v1");
  const mcpUrl = absoluteAppUrl("/mcp");

  async function copyEndpoint(label, value) {
    try {
      await navigator.clipboard.writeText(value);
    } catch {
      const field = document.createElement("textarea");
      field.value = value;
      field.setAttribute("readonly", "");
      field.style.position = "fixed";
      field.style.opacity = "0";
      document.body.appendChild(field);
      field.select();
      document.execCommand("copy");
      field.remove();
    }
    setCopiedEndpoint(label);
    window.setTimeout(() => setCopiedEndpoint(""), 1800);
  }

  return (
    <GuideAnchor
      anchor={GUIDE_ANCHORS.API_INTERPRETATION}
      label="How to interpret API and MCP responses"
      className="access-page"
    >
      <div className="access-grid">
        <GuideAnchor
          as="article"
          anchor={GUIDE_ANCHORS.API_REST}
          label="REST API guide"
          className="access-card"
        >
          <PanelHeader
            iconRole="module.api"
            title="REST API v1"
            description="Query cohorts, datasets and genes; run analyses, check jobs and download results."
          />
          <EndpointClipboard
            label="Base URL"
            value={restBaseUrl}
            copied={copiedEndpoint === "rest"}
            onCopy={() => copyEndpoint("rest", restBaseUrl)}
          />
          <div className="access-links" aria-label="REST API documentation">
            <a href={apiUrl("/api/docs")} target="_blank" rel="noreferrer">
              <TraceIcon role="document.guide" size="sm" />
              <span>
                <strong>Swagger documentation</strong>
                <small>Browse the public endpoints and try requests</small>
              </span>
            </a>
            <a href={apiUrl("/api/openapi.json")} target="_blank" rel="noreferrer">
              <TraceIcon role="data.network" size="sm" />
              <span>
                <strong>OpenAPI 3.1 schema</strong>
                <small>Request and response definitions for your code</small>
              </span>
            </a>
          </div>
        </GuideAnchor>

        <GuideAnchor
          as="article"
          anchor={GUIDE_ANCHORS.API_CONNECTORS}
          label="MCP connector guide"
          className="access-card"
        >
          <PanelHeader
            iconRole="module.aiConnectors"
            title="Claude and ChatGPT"
            description="Connect an MCP client, such as Claude or ChatGPT, to query cohorts and run supported analyses. Use the web app or REST API for private uploads and Run history exports."
          />
          <EndpointClipboard
            label="MCP connector URL"
            value={mcpUrl}
            copied={copiedEndpoint === "mcp"}
            onCopy={() => copyEndpoint("mcp", mcpUrl)}
          />
          <ol className="connector-steps">
            <li>
              <span>01</span>
              <p><strong>Copy the MCP URL</strong><small>Use the button above; it is a connector endpoint, not a browser page.</small></p>
            </li>
            <li>
              <span>02</span>
              <p><strong>Add a remote connector</strong><small>Paste it in the custom MCP settings for Claude or ChatGPT.</small></p>
            </li>
            <li>
              <span>03</span>
              <p><strong>Start with a cohort query</strong><small>The public beta currently requires no API key.</small></p>
            </li>
          </ol>
        </GuideAnchor>
      </div>

      <GuideAnchor
        anchor={GUIDE_ANCHORS.API_EXECUTION}
        label="Shared API execution path"
        className="integration-map"
      >
        <div className="integration-map-heading">
          <div>
            <p className="eyebrow">How requests run</p>
            <h2>Web, REST and MCP use the same analysis engine</h2>
          </div>
          <a href={apiUrl("/api/v1/health")} target="_blank" rel="noreferrer">
            Check service status
          </a>
        </div>
        <div className="integration-flow">
          <div>
            <span>Inputs</span>
            <strong>Web · REST · MCP</strong>
          </div>
          <div>
            <span>Validation</span>
            <strong>API v1 validation</strong>
          </div>
          <div>
            <span>Compute</span>
            <strong>Shared job workers</strong>
          </div>
          <div>
            <span>Data</span>
            <strong>TCGA · curated · private</strong>
          </div>
        </div>
      </GuideAnchor>
      <p className="access-footnote">
        Public compute is rate-limited and asynchronous. Results are exploratory and must not be
        interpreted as clinical advice.
      </p>
    </GuideAnchor>
  );
}

function EndpointClipboard({ label, value, copied, onCopy }) {
  return (
    <div className="endpoint-clipboard">
      <span>{label}</span>
      <code>{value}</code>
      <button type="button" onClick={onCopy} aria-label={`Copy ${label}`}>
        {copied ? <TraceIcon role="status.success" size="sm" tone="success" /> : <TraceIcon role="action.copy" size="sm" />}
        {copied ? "Copied" : "Copy"}
      </button>
    </div>
  );
}

function absoluteAppUrl(path) {
  const value = apiUrl(path);
  try {
    return new URL(value, window.location.origin).toString();
  } catch {
    return value;
  }
}

function InputOutputTree() {
  const groups = [...new Set(INPUT_OUTPUT_TREE_BRANCHES.map((branch) => branch.group))];
  const accessPath = [
    {
      label: "Access",
      value: "Web interface · REST API v1 · MCP",
      detail: "The web app, REST API and MCP share the versioned public analysis settings.",
    },
    {
      label: "Validation",
      value: "Schema + cohort inventory + endpoint QC",
      detail: "TRACE checks the inputs before starting an analysis.",
    },
    {
      label: "Dispatch",
      value: "Catalog read or asynchronous compute job",
      detail: "Compute requests use the shared queue and analysis workers.",
    },
  ];

  return (
    <GuideAnchor
      anchor={GUIDE_ANCHORS.METHODS_INPUT_OUTPUT}
      labelledBy="input-output-title"
      className="help-section input-output-section"
    >
      <header className="input-output-heading">
        <div>
          <p className="eyebrow">Analysis overview</p>
          <h2 id="input-output-title">Analysis input-output tree</h2>
        </div>
        <p>
          Check the inputs, calculations and available outputs for each analysis.
        </p>
      </header>

      <figure className="input-output-tree" aria-describedby="input-output-caption">
        <div className="input-output-root" aria-label="Shared application entry path">
          {accessPath.map((step) => (
            <div key={step.label}>
              <span>{step.label}</span>
              <strong>{step.value}</strong>
              <small>{step.detail}</small>
            </div>
          ))}
        </div>

        <div className="input-output-column-heads" aria-hidden="true">
          <span>Application path</span>
          <span>Accepted input</span>
          <span>Execution</span>
          <span>Output</span>
        </div>

        <div className="input-output-groups">
          {groups.map((group) => (
            <section className="input-output-group" key={group} aria-labelledby={`input-output-${slugify(group)}`}>
              <h3 id={`input-output-${slugify(group)}`}>{group}</h3>
              <ol>
                {INPUT_OUTPUT_TREE_BRANCHES
                  .filter((branch) => branch.group === group)
                  .map((branch) => (
                    <li className="input-output-branch" key={branch.id}>
                      <div className="input-output-route">
                        <span>{branch.scope}</span>
                        <h4>{branch.route}</h4>
                        <code>{branch.formula}</code>
                      </div>
                      <InputOutputStage label="Accepted input" items={branch.inputs} />
                      <InputOutputStage label="Execution" items={branch.execution} />
                      <InputOutputStage label="Output" items={branch.outputs} />
                      {branch.boundary && (
                        <p className="input-output-boundary">
                          <strong>Analysis scope</strong>
                          <span>{branch.boundary}</span>
                        </p>
                      )}
                    </li>
                  ))}
              </ol>
            </section>
          ))}
        </div>

        <figcaption id="input-output-caption">
          Available outputs depend on the endpoint, samples, events and model requirements. Tables and run records retain failed analyses and explain which results could not be estimated.
        </figcaption>
      </figure>
    </GuideAnchor>
  );
}

function InputOutputStage({ label, items }) {
  return (
    <div className="input-output-stage">
      <span className="input-output-stage-label">{label}</span>
      <ul>
        {items.map((item) => <li key={item}>{item}</li>)}
      </ul>
    </div>
  );
}

function slugify(value) {
  return String(value || "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/(^-|-$)/g, "");
}

function focusPageSection(anchor, { updateHistory = false } = {}) {
  const id = guideAnchorDomId(anchor);
  const target = document.getElementById(id);
  if (!target) return false;
  if (target.tagName === "DETAILS") target.open = true;
  if (updateHistory) {
    window.history.pushState(null, "", `${window.location.pathname}${window.location.search}#${id}`);
  }
  target.scrollIntoView({ behavior: "auto", block: "start", inline: "nearest" });
  target.focus({ preventScroll: true });
  return true;
}

function PageContents({ label, items }) {
  const anchorKey = items.map(({ anchor }) => anchor).join("|");
  useEffect(() => {
    const requestedId = decodeURIComponent(window.location.hash.replace(/^#/, ""));
    const item = items.find(({ anchor }) => guideAnchorDomId(anchor) === requestedId);
    if (!item) return undefined;
    const frame = window.requestAnimationFrame(() => focusPageSection(item.anchor));
    return () => window.cancelAnimationFrame(frame);
  }, [anchorKey]);

  return (
    <nav className="page-contents" aria-label={label}>
      <strong>On this page</strong>
      <ul>
        {items.map((item) => (
          <li key={item.anchor}>
            <a
              href={`#${guideAnchorDomId(item.anchor)}`}
              onClick={(event) => {
                event.preventDefault();
                focusPageSection(item.anchor, { updateHistory: true });
              }}
            >
              {item.label}
            </a>
          </li>
        ))}
      </ul>
    </nav>
  );
}

function DatasetDisclosure({ anchor, label, className = "", iconRole, title, description, children }) {
  return (
    <GuideAnchor
      as="details"
      defaultOpen
      anchor={anchor}
      label={label}
      className={["summary-panel", "page-disclosure", className].filter(Boolean).join(" ")}
    >
      <summary>
        <PanelHeader iconRole={iconRole} title={title} description={description} />
        <TraceIcon role="action.expand" size="sm" className="page-disclosure-chevron" />
      </summary>
      <div className="page-disclosure-body">{children}</div>
    </GuideAnchor>
  );
}

function HelpMethodsPage() {
  const t = useHelpText();
  const helpGuideSections = buildHelpGuideSections(t);
  const methodContents = [
    { anchor: GUIDE_ANCHORS.METHODS_INPUT_OUTPUT, label: "Input-output map" },
    ...helpGuideSections.map((section) => ({ anchor: section.anchor, label: section.title })),
    { anchor: GUIDE_ANCHORS.METHODS_HISTORY, label: "Methods history" },
  ];

  return (
    <GuideAnchor
      anchor={GUIDE_ANCHORS.METHODS_INTERPRETATION}
      label="How to interpret the methods guide"
      className="help-page"
    >
      <PageContents label="Methods sections" items={methodContents} />

      <InputOutputTree />

      <div className="help-layout">
        <div className="help-section-stack">
          {helpGuideSections.map((section) => (
            <GuideAnchor
              as="details"
              defaultOpen
              anchor={section.anchor}
              label={section.title}
              className="help-section page-disclosure"
              key={section.title}
            >
              <summary>
                <h2>{section.title}</h2>
                <TraceIcon role="action.expand" size="sm" className="page-disclosure-chevron" />
              </summary>
              <div className="page-disclosure-body">
                <dl className="help-term-list">
                  {section.items.map(([term, body]) => (
                    <div className="help-term" key={term}>
                      <dt>{term}</dt>
                      <dd>{body}</dd>
                    </div>
                  ))}
                </dl>
              </div>
            </GuideAnchor>
          ))}
        </div>

        <GuideAnchor
          as="details"
          defaultOpen
          anchor={GUIDE_ANCHORS.METHODS_HISTORY}
          label="Methodological changelog"
          className="help-section method-history page-disclosure"
        >
          <summary>
            <h2>Methods history</h2>
            <TraceIcon role="action.expand" size="sm" className="page-disclosure-chevron" />
          </summary>
          <div className="page-disclosure-body">
            <p>
              These versions identify changes to scoring, grouping, endpoint checks, model outputs and reproducibility exports. They are method versions, separate from Git commits.
            </p>
            <div className="history-list">
              {METHOD_HISTORY.map((entry) => (
                <article key={entry.version} className="history-entry">
                  <div>
                    <span>{entry.date}</span>
                    <h3>{entry.title}</h3>
                    <code>{entry.version}</code>
                  </div>
                  <ul>
                    {entry.items.map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                </article>
              ))}
            </div>
          </div>
        </GuideAnchor>
      </div>
    </GuideAnchor>
  );
}

function DatasetSummary({
  summary,
  health,
  dataSources = [],
  repositoryDatasets = [],
  cohorts = [],
  summaryCohort,
  setSummaryCohort,
}) {
  if (!summary) {
    return (
      <section className="summary-page">
        <div className="loading-state compact">
          <TraceIcon role="status.loading" size="lg" className="spin" label="Loading dataset summary" />
          <div>
            <p className="eyebrow">Loading dataset summary</p>
            <h2>Reading cohort and sample metadata</h2>
          </div>
        </div>
      </section>
    );
  }

  const totals = summary.totals || {};
  const dates = summary.data_dates || health?.data_dates || {};
  const distributions = summary.distributions || {};
  const sources = dataSources.length ? dataSources : summary.data_sources || [];
  const endpointCoverage = summary.endpoint_coverage || [];
  const topCohorts = [...(summary.cohorts || [])]
    .sort((a, b) => Number(b.patient_count || 0) - Number(a.patient_count || 0))
    .slice(0, 12);
  const datasetContents = [
    { anchor: GUIDE_ANCHORS.DATASET_OVERVIEW, label: "Overview" },
    { anchor: GUIDE_ANCHORS.DATASET_PROVENANCE, label: "Provenance" },
    { anchor: GUIDE_ANCHORS.DATASET_COVERAGE, label: "Endpoint coverage" },
    { anchor: GUIDE_ANCHORS.DATASET_COHORT_LANDSCAPE, label: "Cohort landscape" },
    { anchor: GUIDE_ANCHORS.DATASET_SAMPLE_TYPES, label: "Sample types" },
    { anchor: GUIDE_ANCHORS.DATASET_VITAL_STATUS, label: "Vital status" },
    { anchor: GUIDE_ANCHORS.DATASET_PRIMARY_SITES, label: "Primary sites" },
    { anchor: GUIDE_ANCHORS.DATASET_AGE, label: "Age at index" },
    { anchor: GUIDE_ANCHORS.DATASET_METADATA, label: "Metadata coverage" },
    { anchor: GUIDE_ANCHORS.DATASET_ANNOTATIONS, label: "Biological annotations" },
    { anchor: GUIDE_ANCHORS.DATASET_COHORT_TABLE, label: "Cohort table" },
  ];

  return (
    <GuideAnchor
      anchor={GUIDE_ANCHORS.DATASET_INTERPRETATION}
      label="How to interpret the dataset inventory"
      className="summary-page"
    >
      <GuideAnchor
        as="div"
        anchor={GUIDE_ANCHORS.DATASET_OVERVIEW}
        label="Dataset overview and cohort filter"
        className="summary-overview"
      >
        <label className="field summary-overview-filter">
          <span>Cohort filter</span>
          <select value={summaryCohort} onChange={(event) => setSummaryCohort(event.target.value)}>
            <option value="">All cohorts</option>
            {tcgaReferenceCohorts(cohorts).map((cohort) => (
              <option key={cohort.id} value={cohort.id}>
                {getCohortLabel(cohort.id)}
              </option>
            ))}
          </select>
        </label>
        <a
          className="summary-csv-action"
          href={apiUrl(`/api/v1/dataset/summary/download/csv${summaryCohort ? `?cohort=${summaryCohort}` : ""}`)}
        >
          <TraceIcon role="file.csv" size="sm" />
          <span>Summary CSV</span>
        </a>
        <Metric label="Cohorts" value={formatInteger(totals.cohorts)} />
        <Metric label="Samples" value={formatInteger(totals.samples)} />
        <Metric label="Patients" value={formatInteger(totals.patients)} />
        <Metric label="Usable OS" value={formatInteger(totals.usable_os_samples)} />
        <Metric label="Events" value={formatInteger(totals.events)} />
      </GuideAnchor>

      <PageContents label="Dataset sections" items={datasetContents} />

      <DatasetProvenance
        dates={dates}
        sources={sources}
        repositoryDatasets={repositoryDatasets}
        repositoryDatasetCount={health?.external_repository?.datasets || 0}
      />

      <div className="summary-layout">
        <DatasetDisclosure
          anchor={GUIDE_ANCHORS.DATASET_COVERAGE}
          label="Dataset endpoint coverage"
          className="wide"
          iconRole="module.endpointCoverage"
          title="Endpoint coverage"
          description="An outcome becomes available after linked patient and event counts pass quality checks."
        >
          <EndpointCoverageTable items={endpointCoverage} />
        </DatasetDisclosure>

        <DatasetDisclosure
          anchor={GUIDE_ANCHORS.DATASET_COHORT_LANDSCAPE}
          label="Cohort landscape"
          className="wide"
          iconRole="module.cohortLandscape"
          title="Cohort landscape"
          description="Ranked dot plot: X-axis is patients, dot size is OS events, color is event rate."
        >
          <CohortRankPlot cohorts={topCohorts} />
        </DatasetDisclosure>

        <DatasetDisclosure
          anchor={GUIDE_ANCHORS.DATASET_SAMPLE_TYPES}
          label="Sample type distribution"
          iconRole="module.sampleTypes"
          title="Sample types"
          description="Top sample categories across all cohorts."
        >
          <DonutPlot items={distributions.sample_types || []} />
        </DatasetDisclosure>

        <DatasetDisclosure
          anchor={GUIDE_ANCHORS.DATASET_VITAL_STATUS}
          label="Vital status distribution"
          iconRole="module.vitalStatus"
          title="Vital status"
          description="Recorded alive or deceased status in the source data."
        >
          <DonutPlot items={distributions.vital_status || []} />
        </DatasetDisclosure>

        <DatasetDisclosure
          anchor={GUIDE_ANCHORS.DATASET_PRIMARY_SITES}
          label="Primary site distribution"
          iconRole="module.primarySites"
          title="Primary sites"
          description="Tissue sites counted by RNA samples, not by unique patients."
        >
          <PrimarySitePlot items={distributions.primary_site || []} />
        </DatasetDisclosure>

        <DatasetDisclosure
          anchor={GUIDE_ANCHORS.DATASET_AGE}
          label="Age at index distribution"
          iconRole="module.age"
          title="Age at index"
          description="Patient ages grouped into ranges."
        >
          <HistogramPlot items={distributions.age_bins || []} />
        </DatasetDisclosure>

        <DatasetDisclosure
          anchor={GUIDE_ANCHORS.DATASET_METADATA}
          label="Clinical metadata coverage"
          iconRole="module.metadata"
          title="Metadata coverage"
          description="How many samples have a recorded value for each field."
        >
          <CoverageMatrix items={summary.metadata_coverage || []} />
        </DatasetDisclosure>

        <DatasetDisclosure
          anchor={GUIDE_ANCHORS.DATASET_ANNOTATIONS}
          label="Biological annotation coverage"
          iconRole="module.biologicalAnnotations"
          title="Biological annotations"
          description="Reported tumor subtypes available for each TCGA cohort."
        >
          <BiologicalAnnotations annotations={summary.biological_annotations || {}} />
        </DatasetDisclosure>

        <DatasetDisclosure
          anchor={GUIDE_ANCHORS.DATASET_COHORT_TABLE}
          label="Dataset cohort table"
          className="wide"
          iconRole="module.cohortTable"
          title="Cohort table"
          description="Imported samples, patients, cancer name and source metadata."
        >
          <CohortSummaryTable cohorts={summary.cohorts || []} />
        </DatasetDisclosure>
      </div>
    </GuideAnchor>
  );
}

function CohortRankPlot({ cohorts }) {
  if (!cohorts.length) return <div className="empty-inline">No cohort data available.</div>;
  const width = 760;
  const rowHeight = 31;
  const topPad = 34;
  const bottomPad = 42;
  const height = topPad + cohorts.length * rowHeight + bottomPad;
  const labelX = 20;
  const plotLeft = 170;
  const plotRight = 610;
  const countX = 632;
  const maxPatients = Math.max(...cohorts.map((cohort) => Number(cohort.patient_count || 0)), 1);
  const maxEvents = Math.max(...cohorts.map((cohort) => Number(cohort.event_count ?? cohort.sample_count ?? 0)), 1);
  const ticks = [0, Math.round(maxPatients / 2), maxPatients];
  const eventRateColor = (rate) => {
    if (rate >= 0.35) return "#b94d48";
    if (rate >= 0.18) return "#c8842d";
    return "#1f6f8b";
  };
  return (
    <div className="cohort-rank-wrap">
      <svg className="cohort-rank-plot" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Ranked cohort dot plot by patients and events">
        {ticks.map((tick) => {
          const x = plotLeft + (tick / maxPatients) * (plotRight - plotLeft);
          return (
            <g key={tick} className="axis-tick">
              <line x1={x} y1="20" x2={x} y2={height - bottomPad + 9} />
              <text x={x} y={height - 14} textAnchor="middle">{formatInteger(tick)}</text>
            </g>
          );
        })}
        <text x={(plotLeft + plotRight) / 2} y={height - 1} textAnchor="middle">Patients</text>
        <text x={labelX} y="18">Cohort</text>
        <text x={countX} y="18">Patients / events</text>
      {cohorts.map((cohort, index) => {
        const patients = Number(cohort.patient_count || 0);
        const events = Number(cohort.event_count ?? 0);
        const eventRate = patients > 0 ? events / patients : 0;
        const x = plotLeft + (patients / maxPatients) * (plotRight - plotLeft);
        const y = topPad + index * rowHeight;
        const radius = 5 + Math.sqrt(events / maxEvents) * 10;
        return (
          <g key={cohort.id} className="cohort-rank-row">
            <title>{`${cohort.id} - ${getCohortName(cohort.id)}: ${formatInteger(patients)} patients, ${formatInteger(events)} events, ${Math.round(eventRate * 100)}% event rate`}</title>
            <line x1={plotLeft} y1={y} x2={plotRight} y2={y} />
            <text x={labelX} y={y + 4}>{cohort.id}</text>
            <circle cx={x} cy={y} r={radius} fill={eventRateColor(eventRate)} />
            <text x={countX} y={y + 4}>{formatInteger(patients)} / {formatInteger(events)}</text>
          </g>
        );
      })}
      </svg>
      <div className="cohort-rank-legend" aria-hidden="true">
        <span><i className="low" />Lower event rate</span>
        <span><i className="mid" />Moderate</span>
        <span><i className="high" />Higher</span>
        <span className="size-note">Larger dot = more OS events</span>
      </div>
    </div>
  );
}

function DonutPlot({ items }) {
  if (!items.length) return <div className="empty-inline">No metadata available.</div>;
  const total = items.reduce((sum, item) => sum + Number(item.count || 0), 0) || 1;
  let offset = 0;
  const radius = 64;
  const circumference = 2 * Math.PI * radius;
  return (
    <div className="donut-wrap">
      <svg className="donut-plot" viewBox="0 0 180 180" role="img" aria-label="Composition donut plot">
        <circle cx="90" cy="90" r={radius} className="donut-bg" />
        {items.slice(0, 6).map((item, index) => {
          const value = Number(item.count || 0);
          const dash = (value / total) * circumference;
          const segment = (
            <circle
              key={item.label}
              cx="90"
              cy="90"
              r={radius}
              className={`donut-segment segment-${index}`}
              strokeDasharray={`${dash} ${circumference - dash}`}
              strokeDashoffset={-offset}
            />
          );
          offset += dash;
          return segment;
        })}
        <text x="90" y="86" textAnchor="middle">{formatInteger(total)}</text>
        <text x="90" y="104" textAnchor="middle">samples</text>
      </svg>
      <div className="donut-legend">
        {items.slice(0, 6).map((item, index) => (
          <div key={item.label}>
            <i className={`segment-${index}`} />
            <span>{item.label}</span>
            <strong>{formatInteger(item.count)}</strong>
          </div>
        ))}
      </div>
    </div>
  );
}

function HistogramPlot({ items }) {
  if (!items.length) return <div className="empty-inline">No age metadata available.</div>;
  const maxValue = Math.max(...items.map((item) => Number(item.count || 0)), 1);
  const width = 420;
  const height = 220;
  const barGap = 8;
  const barWidth = (width - 48 - barGap * (items.length - 1)) / items.length;
  return (
    <svg className="histogram-plot" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Age distribution histogram">
      <line x1="32" y1="180" x2="408" y2="180" />
      <line x1="32" y1="24" x2="32" y2="180" />
      {items.map((item, index) => {
        const value = Number(item.count || 0);
        const barHeight = (value / maxValue) * 140;
        const x = 42 + index * (barWidth + barGap);
        const y = 180 - barHeight;
        return (
          <g key={item.label}>
            <rect x={x} y={y} width={barWidth} height={barHeight} rx="5" />
            <text x={x + barWidth / 2} y="202" textAnchor="middle">{item.label}</text>
            <text x={x + barWidth / 2} y={Math.max(18, y - 6)} textAnchor="middle">{formatInteger(value)}</text>
          </g>
        );
      })}
    </svg>
  );
}

function CoverageMatrix({ items }) {
  if (!items.length) return <div className="empty-inline">No coverage metadata available.</div>;
  return (
    <div className="coverage-matrix">
      {items.map((item) => (
        <div key={item.label}>
          <span>{item.label}</span>
          <div>
            {Array.from({ length: 10 }).map((_, index) => (
              <i key={index} className={index < Math.round((Number(item.percent) || 0) / 10) ? "filled" : ""} />
            ))}
          </div>
          <strong>{item.percent}%</strong>
        </div>
      ))}
    </div>
  );
}

function PrimarySitePlot({ items }) {
  const maxValue = Math.max(...items.map((item) => Number(item.count || 0)), 1);
  if (!items.length) return <div className="empty-inline">No primary-site metadata available.</div>;
  return (
    <div className="primary-site-list">
      {items.map((item) => {
        const count = Number(item.count || 0);
        const percent = maxValue > 0 ? (count / maxValue) * 100 : 0;
        return (
          <div key={item.label} className="primary-site-row" title={`${item.label}: ${formatInteger(count)} samples`}>
            <div>
              <span>{item.label}</span>
              <strong>{formatInteger(count)}</strong>
            </div>
            <i style={{ "--bar-width": `${percent}%` }} />
          </div>
        );
      })}
    </div>
  );
}

function DistributionBars({ items }) {
  const maxValue = Math.max(...items.map((item) => Number(item.count || 0)), 1);
  if (!items.length) return <div className="empty-inline">No metadata available.</div>;
  return (
    <div className="bar-list">
      {items.map((item) => (
        <div key={item.label} className="bar-row">
          <div>
            <span>{item.label}</span>
            <strong>{formatInteger(item.count)}</strong>
          </div>
          <i style={{ "--bar-width": `${(Number(item.count || 0) / maxValue) * 100}%` }} />
        </div>
      ))}
    </div>
  );
}

function CohortSummaryTable({ cohorts }) {
  const [sort, setSort] = useState({ key: "patient_count", direction: "desc" });
  const columns = [
    ["id", "Cohort", (cohort) => cohort.id || ""],
    ["cancer", "Cancer", (cohort) => getCohortName(cohort.id)],
    ["primary_site", "Primary site", (cohort) => cohort.primary_site || ""],
    ["sample_count", "Samples", (cohort) => Number(cohort.sample_count || 0)],
    ["patient_count", "Patients", (cohort) => Number(cohort.patient_count || 0)],
    ["event_count", "Events", (cohort) => Number(cohort.event_count || 0)],
    ["n_primary_tumor", "Primary tumor", (cohort) => Number(cohort.n_primary_tumor || 0)],
    ["n_solid_normal", "Solid normal", (cohort) => Number(cohort.n_solid_normal || 0)],
  ];
  const activeColumn = columns.find(([key]) => key === sort.key) || columns[0];
  const sortedCohorts = useMemo(() => [...cohorts].sort((left, right) => {
    const leftValue = activeColumn[2](left);
    const rightValue = activeColumn[2](right);
    const comparison = typeof leftValue === "number"
      ? leftValue - rightValue
      : String(leftValue).localeCompare(String(rightValue));
    return sort.direction === "asc" ? comparison : -comparison;
  }), [activeColumn, cohorts, sort.direction]);

  function changeSort(key) {
    setSort((current) => ({
      key,
      direction: current.key === key && current.direction === "asc" ? "desc" : "asc",
    }));
  }

  return (
    <div
      className="table-scroll"
      role="region"
      aria-label="Scrollable TCGA cohort summary table"
      tabIndex={0}
    >
      <table aria-label="Cohort sample and endpoint summary">
        <thead>
          <tr>
            {columns.map(([key, label]) => (
              <th
                scope="col"
                key={key}
                aria-sort={sort.key === key
                  ? sort.direction === "asc" ? "ascending" : "descending"
                  : "none"}
              >
                <button
                  type="button"
                  className="table-sort-button"
                  onClick={() => changeSort(key)}
                >
                  {label}
                  <span aria-hidden="true">
                    {sort.key === key ? sort.direction === "asc" ? "↑" : "↓" : "↕"}
                  </span>
                </button>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sortedCohorts.map((cohort) => (
            <tr key={cohort.id}>
              <th scope="row">{cohort.id}</th>
              <td>{getCohortName(cohort.id)}</td>
              <td>{cohort.primary_site || "..."}</td>
              <td>{formatInteger(cohort.sample_count)}</td>
              <td>{formatInteger(cohort.patient_count)}</td>
              <td>{formatInteger(cohort.event_count)}</td>
              <td>{formatInteger(cohort.n_primary_tumor)}</td>
              <td>{formatInteger(cohort.n_solid_normal)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function AnalysisWorkflowStepper({
  steps,
  activeStep,
  completion,
  summary,
  onSelect,
  idPrefix = "analysis-step",
  ariaLabel = "Survival analysis setup",
  summaryLabel = "Current setup",
}) {
  return (
    <div className="analysis-workflow-nav">
      <div
        className="analysis-stepper-scroll"
        role="region"
        tabIndex={0}
        aria-label={`${ariaLabel} steps`}
      >
        <nav aria-label={ariaLabel}>
          <ol className="analysis-stepper" style={{ "--workflow-step-count": steps.length }}>
            {steps.map((step, index) => {
              const isActive = index === activeStep;
              const isComplete = Boolean(completion[index]);
              const StepButton = step.guideAnchor ? GuideAnchor : "button";
              return (
                <li key={step.id}>
                  <StepButton
                    {...(step.guideAnchor
                      ? {
                          as: "button",
                          anchor: step.guideAnchor,
                          label: `${step.label} workflow step`,
                          tabIndex: 0,
                        }
                      : {})}
                    id={step.guideAnchor ? undefined : `${idPrefix}-${step.id}`}
                    type="button"
                    className={`${isActive ? "active" : ""}${isComplete ? " complete" : ""}`}
                    onClick={() => onSelect(index)}
                    aria-current={isActive ? "step" : undefined}
                    aria-controls={activeWorkflowPanelId(idPrefix, step.id, isActive)}
                  >
                    <span className="analysis-step-marker" aria-hidden="true">
                      {isComplete && !isActive ? <TraceIcon role="status.success" size="sm" /> : index + 1}
                    </span>
                    <span>{step.label}</span>
                    <span className="sr-only">
                      {isActive ? ", current step" : isComplete ? ", configured" : ""}
                    </span>
                  </StepButton>
                </li>
              );
            })}
          </ol>
        </nav>
      </div>
      {summary && <div className="analysis-step-summary" aria-label={summaryLabel}>
        <span>{summaryLabel}</span>
        <strong>{summary}</strong>
      </div>}
    </div>
  );
}

function AnalysisStepActions({
  activeStep,
  totalSteps,
  canContinue,
  requirement,
  loading,
  canRun,
  onBack,
  onContinue,
  onRun,
}) {
  const isFirst = activeStep === 0;
  const isLast = activeStep === totalSteps - 1;
  return (
    <div className="analysis-step-actions">
      <button
        type="button"
        className="secondary-button"
        onClick={onBack}
        disabled={isFirst || loading}
      >
        <TraceIcon role="action.back" size="sm" />
        Back
      </button>
      <span className={requirement ? "analysis-step-requirement" : "analysis-step-position"} aria-live="polite">
        {requirement || `Step ${activeStep + 1} of ${totalSteps}`}
      </span>
      {isLast ? (
        <button type="button" className="primary-button" onClick={onRun} disabled={!canRun || loading}>
          {loading ? <TraceIcon role="status.loading" size="md" className="spin" /> : <TraceIcon role="action.run" size="md" />}
          Run analysis
        </button>
      ) : (
        <button
          type="button"
          className="primary-button"
          onClick={onContinue}
          disabled={!canContinue || loading}
        >
          Continue
          <TraceIcon role="action.next" size="sm" />
        </button>
      )}
    </div>
  );
}

function AnalysisSetupPreview({
  plotEditorOpen = false,
  activeStep,
  step,
  cohort,
  repositoryDataset,
  dataSourceMode,
  userDatasetUploadStep,
  form,
  isCombinedMode,
  isPanelMode,
  selectedGenes,
  signatureAGenes,
  signatureBGenes,
  panelSignatures,
  endpoint,
  expressionScale,
  cutpoint,
  activeFilterCount,
  plotEditorTarget,
  plotTitlePlaceholder,
}) {
  const titles = {
    data: cohort
      ? "Cohort and RNA layer"
      : dataSourceMode === "upload"
        ? userDatasetUploadStep === 1
          ? "Finish dataset mapping"
          : "Prepare your dataset"
        : "Choose a cohort",
    design: isPanelMode
      ? "Signature panel"
      : isCombinedMode
        ? "Two-signature design"
        : "Molecular signal",
    outcome: isPanelMode ? "Outcome and estimand" : "Outcome and grouping",
    clinical: activeFilterCount ? "Restricted clinical design" : "Patient filters and adjustment",
    review: plotEditorOpen ? "Practical plot preview" : "Analysis results",
  };
  const filterLabels = analysisFilterLabels(form.filters);

  return (
    <div className={`analysis-setup-preview preview-${step.id}`}>
      <header className="analysis-preview-header">
        <ModuleIcon role={step.iconRole} />
        <div>
          <span>Step {activeStep + 1} of {ANALYSIS_WORKFLOW_STEPS.length}</span>
          <h2>{titles[step.id]}</h2>
        </div>
      </header>

      {step.id === "data" && (
        cohort ? (
          <div className="analysis-context-preview">
            <div className="analysis-preview-lead">
              <span>{repositoryDataset?.source_accession || cohort.id}</span>
              <h3>{repositoryDataset?.name || getCohortName(cohort.id)}</h3>
              <p>
                {repositoryDataset?.cohort_context
                  || cohort.primary_site
                  || "Primary site not reported"}
              </p>
            </div>
            <div className="analysis-preview-metrics">
              <PreviewItem
                label="Cohort RNA samples"
                value={formatInteger(
                  repositoryDataset?.sample_count ?? cohort.n_samples_paired,
                )}
              />
              <PreviewItem
                label="Cohort patients"
                value={formatInteger(
                  repositoryDataset?.patient_count ?? cohort.n_patients_paired,
                )}
              />
              <PreviewItem
                label={repositoryDataset ? "Genes" : "Primary tumor RNA samples"}
                value={formatInteger(
                  repositoryDataset?.gene_count ?? cohort.n_primary_tumor,
                )}
              />
              <PreviewItem
                label="Expression data"
                value={expressionScale?.label || "Select a layer"}
              />
            </div>
          </div>
        ) : (
          <PreviewPrompt
            iconRole="module.dataset"
            title={
              dataSourceMode === "upload"
                ? userDatasetUploadStep === 1
                  ? "Map and validate your files"
                  : "Add expression and metadata"
                : "Select one cancer cohort"
            }
            text={
              dataSourceMode === "upload"
                ? userDatasetUploadStep === 1
                  ? "Confirm identifiers, survival coding, time unit and expression scale, then validate the private dataset."
                  : "Name the dataset, choose a cancer context, then add expression and patient-metadata tables. Survival is optional."
                : "The cohort determines available genes, endpoints, clinical fields and patient counts."
            }
          />
        )
      )}

      {step.id === "design" && (
        <div className="analysis-context-preview">
          <div className="analysis-preview-lead">
            <span>{isPanelMode ? `${panelSignatures.length} signatures` : isCombinedMode ? "Two signatures" : signatureMethodDefinition(form.signature_method).label}</span>
            <h3>{isPanelMode ? "Common-population main effects" : isCombinedMode ? "Independent molecular scores" : "Expression signal"}</h3>
            <p>
              {isPanelMode
                ? "Every signature is scored independently, standardized on the same patients and entered together in a joint Cox model."
                : isCombinedMode
                ? "Each signature is scored separately before patient groups are crossed."
                : form.signature_method === "single"
                  ? "Each selected gene produces a separate survival analysis."
                  : "Selected genes contribute to one combined expression score."}
            </p>
          </div>
          {isPanelMode ? (
            <div className="signature-preview-grid panel">
              {panelSignatures.map((signature) => (
                <GenePreviewGroup
                  key={signature.name}
                  label={signature.name}
                  genes={uniqueGeneSymbols(signature.gene_symbol)}
                  method={signature.signature_method}
                />
              ))}
            </div>
          ) : isCombinedMode ? (
            <div className="signature-preview-grid">
              <GenePreviewGroup
                label={form.combined_signature.signature_a.name || "Signature A"}
                genes={signatureAGenes}
                method={form.combined_signature.signature_a.signature_method}
              />
              <GenePreviewGroup
                label={form.combined_signature.signature_b.name || "Signature B"}
                genes={signatureBGenes}
                method={form.combined_signature.signature_b.signature_method}
              />
            </div>
          ) : (
            <GenePreviewGroup
              label={selectedGenes.length ? `${selectedGenes.length} selected` : "No genes selected"}
              genes={selectedGenes}
              method={form.signature_method}
            />
          )}
        </div>
      )}

      {step.id === "outcome" && (
        cohort ? (
          <div className="analysis-context-preview endpoint-context-preview">
            <div className="analysis-endpoint-symbol" aria-hidden="true">
              <TraceIcon role="data.endpoint" size="lg" />
            </div>
            <div className="analysis-preview-lead">
              <span>{formatSourceLabel(endpoint?.source)}</span>
              <h3>{endpoint?.label || "Select an endpoint"}</h3>
              <p>
                {endpoint?.available
                  ? "This endpoint passes the displayed cohort-level patient and event QC."
                  : endpoint?.reason || "No evaluable endpoint is selected."}
              </p>
            </div>
            <div className="analysis-preview-metrics">
              <PreviewItem label="Patients with this endpoint" value={formatInteger(endpoint?.patients)} />
              <PreviewItem label="Events in source" value={formatInteger(endpoint?.events)} />
              <PreviewItem label="Status" value={endpoint?.available ? "Available" : "Not evaluable"} />
            </div>
            <FieldHelp helpId="survivalEndpointCounts" />
          </div>
        ) : (
          <PreviewPrompt
            iconRole="module.survivalEndpoint"
            title="Cohort required"
            text="Endpoint availability and event counts are evaluated after a cohort is selected."
          />
        )
      )}

      {step.id === "outcome" && (
        <GroupingPreview
          form={form}
          isCombinedMode={isCombinedMode}
          isPanelMode={isPanelMode}
          expressionScale={expressionScale}
          cutpoint={cutpoint}
        />
      )}

      {step.id === "clinical" && (
        <div className="analysis-context-preview">
          <div className="analysis-preview-lead">
            <span>{activeFilterCount ? `${activeFilterCount} active` : "No restrictions"}</span>
            <h3>{activeFilterCount ? "Filtered eligibility" : "Eligibility and adjustment"}</h3>
            <p>
              {activeFilterCount
                ? "Only patients matching every restriction enter scoring; adjustment then uses complete cases for the selected covariates."
                : "Eligibility retains all endpoint-complete patients; adjustment uses complete cases for the selected covariates."}
            </p>
          </div>
          <div className="clinical-preview-groups">
            <PreviewChipGroup
              label="Eligibility"
              values={filterLabels}
              empty="All available clinical values"
            />
            <PreviewChipGroup
              label="Cox adjustment"
              values={[
                ...adjustmentCovariateLabels(form.adjustment_covariates),
                ...externalAdjustmentCovariateLabels(
                  form.external_adjustment_covariates,
                  form.external_covariates,
                ),
              ]}
              empty="No additional adjustment"
            />
          </div>
        </div>
      )}

      {step.id === "review" && plotEditorOpen && (
        <PlotStylePreview
          form={form}
          isCombinedMode={isCombinedMode}
          isPanelMode={isPanelMode}
          plotTitlePlaceholder={plotTitlePlaceholder}
          previewTarget={plotEditorTarget}
        />
      )}
      {step.id === "review" && !plotEditorOpen && <FieldHelp helpId="survivalReviewPreview" />}

      {(step.id !== "review" || plotEditorOpen) && <footer className="analysis-preview-note">
        {step.id === "review"
          ? "Illustrative preview only. Colors and labels reflect the export settings; no effect estimate is implied."
          : "Configuration preview only. Patient grouping and models are computed after Run analysis."}
      </footer>}
    </div>
  );
}

function PreviewPrompt({ iconRole, title, text }) {
  return (
    <div className="analysis-preview-prompt">
      <ModuleIcon role={iconRole} />
      <h3>{title}</h3>
      <p>{text}</p>
    </div>
  );
}

function GenePreviewGroup({ label, genes, method }) {
  return (
    <div className="gene-preview-group">
      <div>
        <strong>{label}</strong>
        <span>{signatureMethodDefinition(method).shortLabel}</span>
      </div>
      <div>
        {genes.length ? genes.map((gene) => <span key={gene}>{gene}</span>) : <span className="empty">Add genes</span>}
      </div>
    </div>
  );
}

function PreviewChipGroup({ label, values, empty }) {
  return (
    <div className="clinical-preview-group">
      <strong>{label}</strong>
      <div className="analysis-filter-preview">
        {values.length
          ? values.map((value) => <span key={value}>{value}</span>)
          : <span className="empty">{empty}</span>}
      </div>
    </div>
  );
}

function GroupingPreview({
  form,
  isCombinedMode,
  isPanelMode,
  expressionScale,
  cutpoint,
}) {
  if (isPanelMode) {
    return (
      <div className="analysis-context-preview grouping-context-preview panel-boundary-preview">
        <div className="analysis-preview-lead">
          <span>{expressionScale?.label || "Expression scale"}</span>
          <h3>Continuous main effects</h3>
          <p>
            Hazard ratios represent a one-standard-deviation increase in each
            final score. Every signature uses the same endpoint-complete
            patient intersection.
          </p>
        </div>
        <div className="panel-boundary-flow" aria-label="Signature panel model sequence">
          <span>Separate scores</span>
          <TraceIcon role="action.next" size="sm" />
          <span>Common population</span>
          <TraceIcon role="action.next" size="sm" />
          <span>Joint Cox model</span>
        </div>
      </div>
    );
  }
  const groupLabels = isCombinedMode
    ? form.combined_signature.grouping_method === "tertiles"
      ? ["Low × Low", "Low × Mid", "Low × High", "Mid × Low", "Mid × Mid", "Mid × High", "High × Low", "High × Mid", "High × High"]
      : ["Low × Low", "Low × High", "High × Low", "High × High"]
    : form.cutpoint_method === "tertiles"
      ? ["Low", "Mid", "High"]
      : ["Low", "High"];
  const colors = isCombinedMode
    ? combinedPalette(form.plot_style.palette, form.combined_signature.grouping_method)
    : form.plot_style.palette;
  return (
    <div className="analysis-context-preview grouping-context-preview">
      <div className="analysis-preview-lead">
        <span>{expressionScale?.label || "Expression scale"}</span>
        <h3>{cutpoint?.label || "Patient groups"}</h3>
        <p>Group sizes and event counts are determined from eligible patients when the analysis runs.</p>
      </div>
      <div className={`analysis-group-preview${groupLabels.length > 4 ? " dense" : ""}`}>
        {groupLabels.map((label, index) => (
          <div key={label} style={{ "--group-color": colors[index % colors.length] }}>
            <i aria-hidden="true" />
            <span>{label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function analysisFilterLabels(filters = {}) {
  const labels = [];
  [
    ["Sample", filters.sample_types],
    ["Stage", filters.stages],
    ["Grade", filters.grades],
    ["Gender", filters.genders],
    ["Race", filters.races],
  ].forEach(([label, values]) => {
    if (values?.length) labels.push(`${label}: ${values.join(", ")}`);
  });
  if (filters.age_min !== "") labels.push(`Age ≥ ${filters.age_min}`);
  if (filters.age_max !== "") labels.push(`Age ≤ ${filters.age_max}`);
  if (filters.max_time_days !== "") labels.push(`Follow-up ≤ ${filters.max_time_days} days`);
  (filters.custom_filters || []).forEach((filter) => {
    if (filter.categorical_levels?.length) {
      labels.push(`${filter.variable_id}: ${filter.categorical_levels.join(", ")}`);
    } else {
      const lower = filter.numeric_min == null ? "−∞" : filter.numeric_min;
      const upper = filter.numeric_max == null ? "+∞" : filter.numeric_max;
      labels.push(`${filter.variable_id}: ${lower}–${upper}`);
    }
  });
  return labels;
}

function clinicalCovariateAvailable(option, filters) {
  if (!filters) return false;
  if (option.availabilityField === "age") {
    const minimum = toNullableNumber(filters.age_min);
    const maximum = toNullableNumber(filters.age_max);
    return minimum !== null && maximum !== null && maximum > minimum;
  }
  const values = (filters[option.availabilityField] || []).filter((value) => {
    const normalized = String(value || "").trim().toLowerCase();
    return normalized && !["unknown", "not reported", "n/a", "na"].includes(normalized);
  });
  return new Set(values.map((value) => String(value).trim().toLowerCase())).size >= 2;
}

function adjustmentCovariateLabels(values = []) {
  const selected = new Set(values || []);
  return CLINICAL_ADJUSTMENT_OPTIONS
    .filter((option) => selected.has(option.value))
    .map((option) => option.label);
}

function externalAdjustmentCovariateLabels(values = [], dataset = null) {
  const selected = new Set(values || []);
  return (dataset?.definitions || [])
    .filter((definition) => selected.has(definition.name))
    .map((definition) => definition.label || definition.name);
}

function formatAdjustmentSummary(
  values = [],
  externalValues = [],
  externalDataset = null,
) {
  const labels = [
    ...adjustmentCovariateLabels(values),
    ...externalAdjustmentCovariateLabels(
      externalValues,
      externalDataset,
    ),
  ];
  return labels.length ? `Adjusted for ${labels.join(" + ")}` : "No added adjustment";
}

function formatMultivariableForestSelection(plotStyle = {}) {
  const coxForest = {
    ...DEFAULT_PLOT_STYLE.cox_forest,
    ...(plotStyle?.cox_forest || {}),
  };
  if (coxForest.multivariable_display !== "selected") {
    return "All evaluable models";
  }
  const selected = new Set(coxForest.multivariable_model_ids || []);
  const labels = COX_MULTIVARIABLE_MODEL_OPTIONS
    .filter(([modelId]) => selected.has(modelId))
    .map(([, label]) => label);
  return labels.length === 1 ? labels[0] : `${labels.length} selected models`;
}

function toggleListValue(values, target) {
  const normalized = [...new Set(values || [])];
  return normalized.includes(target)
    ? normalized.filter((value) => value !== target)
    : [...normalized, target];
}

function PreviewItem({ label, value }) {
  return (
    <div className="preview-item">
      <span>{label}</span>
      <strong>{value ?? "..."}</strong>
    </div>
  );
}

function LoadingState({ cohort, gene, analysisKind, signatureMethod, geneCount, completedCount, endpoint, expressionScale }) {
  const isSingleMode = signatureMethod === "single";
  const isCombinedMode = analysisKind === "combined_signatures";
  const isPanelMode = analysisKind === "signature_panel";
  return (
    <div className="loading-state">
      <div className="analysis-loader" aria-hidden="true">
        <span />
        <span />
        <span />
        <span />
        <span />
      </div>
      <div>
        <p className="eyebrow">Running survival analysis</p>
        <h2>
          {getCohortName(cohort)} / {isPanelMode
            ? gene
            : isCombinedMode
              ? gene
              : isSingleMode
                ? `${completedCount} of ${geneCount} genes completed`
                : gene.trim().toUpperCase()}
        </h2>
        {cohort && <small>{cohort}</small>}
        <span>
          Reading {expressionScale?.label || "expression"}, {isPanelMode
            ? "standardizing every score on one common population, fitting the Cox model families"
            : `assigning groups, fitting ${endpoint?.label || "survival"} curves`} and rendering artifacts.
        </span>
        <ElapsedTime />
      </div>
      <div className="progress-rail">
        <i />
      </div>
    </div>
  );
}

function AnalysisResults({ analyses, onDownload }) {
  if (analyses.length === 1) {
    return <AnalysisResult analysis={analyses[0]} onDownload={onDownload} guideAnchors />;
  }
  return (
    <div className="analysis-stack">
      <div className="stack-header">
        <span>Separate Kaplan-Meier plots</span>
        <strong>{analyses.length} completed genes</strong>
      </div>
      {analyses.map((item, index) => (
        <AnalysisResult
          key={item.id}
          analysis={item}
          onDownload={onDownload}
          guideAnchors={index === 0}
        />
      ))}
    </div>
  );
}

function AnalysisResult({ analysis, onDownload, guideAnchors = false }) {
  const metrics = analysis.metrics || {};
  if (metrics.analysis_type === "signature_panel" || metrics.signature_panel) {
    return (
      <SignaturePanelResult
        analysis={analysis}
        metrics={metrics}
        onDownload={onDownload}
        guideAnchors={guideAnchors}
      />
    );
  }
  const downloads = analysis.downloads || {};
  const sampleSelection = metrics.sample_selection || {};
  const molecularPopulation = sampleSelection.sample_population || null;
  const endpointLabel = metrics.endpoint_label || "Overall survival";
  const combinedSignature = metrics.combined_signature;
  const continuous = metrics.continuous_analysis || {};
  const continuousPrimary =
    findCoxModel(
      continuous.linear_models,
      analysis.diagnostics?.primary_result_model,
    )
    || findCoxModel(continuous.linear_models, "continuous_univariable");
  const spline = continuous.spline || {};
  const hasContinuous = !combinedSignature && continuous.status === "completed";
  const separateCoxPlots = [
    {
      key: "univariable",
      label: "Univariable Cox model",
      png: downloads.cox_univariable_png,
      svg: downloads.cox_univariable_svg,
      alt: "Univariable grouped Cox model forest plot",
    },
    {
      key: "multivariable",
      label: "Multivariable Cox models",
      png: downloads.cox_multivariable_png,
      svg: downloads.cox_multivariable_svg,
      alt: "Adjusted multivariable grouped Cox model forest plot",
    },
  ].filter((plot) => plot.png);
  const hasSeparateCoxPlots = separateCoxPlots.length > 0;
  const DiagnosticsDisclosure = guideAnchors ? GuideAnchor : "section";
  return (
    <div className="analysis-result">
      <div className="result-header">
        <div>
          <h2>{analysis.gene_symbol} · {endpointLabel}</h2>
          <p className="result-context">
            {resultSourceLabel(metrics.dataset, analysis.cohort, getCohortName)} · {analysis.expression_scale_label || "Expression"}
            {analysis.cached ? " · cached" : ""}
          </p>
        </div>
        <ResultDownloads downloads={downloads} onDownload={onDownload} guideAnchor={guideAnchors} />
      </div>

      {molecularPopulation && (
        <details className="result-source-details">
          <summary>RNA population: {molecularPopulation.label} · {formatInteger(sampleSelection.retained_patients)} patients</summary>
          <div className="result-population-contract" role="note">
          <span>
            <strong>
              {formatInteger(sampleSelection.retained_patients)} patients · {formatInteger(retainedSampleCount(sampleSelection))} RNA samples
            </strong>
            <small>
              {formatSampleTypeCounts(sampleSelection.retained_sample_types)} · TCGA {molecularPopulation.allowed_tcga_sample_codes?.join("/")}
              {` · ${sampleSelection.population_excluded_samples || 0} other-tissue samples excluded`}
            </small>
          </span>
          </div>
        </details>
      )}

      <ResultTabs label="Survival result sections">
      {!combinedSignature && (
        <ResultSection id="continuous" title="Continuous model" helpId="continuousPrimaryModel" descriptionHelpId="resultContinuousView">
          <div className="metric-strip">
            <Metric label={continuousPrimary ? "Patients in this model" : "Eligible patients"} value={continuousPrimary?.n_patients ?? continuous.n_patients} />
            <Metric label="Events" value={continuousPrimary?.n_events ?? continuous.n_events} />
            <Metric label="HR / +1 SD" value={formatHrValues(continuousPrimary)} />
            <Metric label="Cox p" value={formatP(continuousPrimary?.p_value)} />
          </div>
          <p className="result-model-label">{continuousPrimary ? formatContinuousModelLabel(continuousPrimary) : "Model unavailable"}</p>
          {[continuousPrimary?.ph_p_value, continuousPrimary?.ph_global_p_value].some((value) => {
            const p = toNullableNumber(value);
            return p !== null && p < ROBUSTNESS_ALPHA;
          }) && <div className="method-note caution" role="note">{getHelpEntry("resultPhFlag").does}</div>}
          <ContinuousAnalysisSummary
            continuous={continuous}
            downloads={downloads}
            geneSymbol={analysis.gene_symbol}
            onDownload={onDownload}
          />
        </ResultSection>
      )}

      <ResultSection id="groups" title={combinedSignature ? "Combined groups" : "Survival groups"} descriptionHelpId={combinedSignature ? "resultCombinedView" : "resultGroupedView"}>
        <section className={combinedSignature ? "grouped-analysis" : "grouped-analysis cutpoint-sensitivity"}>
        <AuthorizedImage className="km-plot" src={downloads.png} alt="Kaplan-Meier cutpoint sensitivity plot" />
        <div className="result-details">
          <GroupTable metrics={metrics} />
          <CutpointSummary details={metrics.cutpoint_details} />
        </div>

        <details className="result-more-details">
          <summary>Hazard ratios and restricted mean survival</summary>
        <CoxModelTable models={metrics.cox_models} />
        <RmstTable rmst={metrics.rmst} />

        {hasSeparateCoxPlots ? (
          <div className="cox-split-plot-grid">
            {separateCoxPlots.map((plot) => (
              <figure className="cox-split-figure" key={plot.key}>
                <figcaption className="plot-download-row">
                  <span>{plot.label}</span>
                  <div className="download-row">
                    <DownloadLink href={plot.png} iconRole="file.image" label="PNG" onDownload={onDownload} />
                    <DownloadLink href={plot.svg} iconRole="action.download" label="SVG" onDownload={onDownload} />
                  </div>
                </figcaption>
                <AuthorizedImage className="cox-forest-plot" src={plot.png} alt={plot.alt} />
              </figure>
            ))}
          </div>
        ) : downloads.cox_png ? (
          <>
            <div className="plot-download-row">
              <span>Grouped Cox forest plot</span>
              <div className="download-row">
                <DownloadLink href={downloads.cox_png} iconRole="file.image" label="PNG" onDownload={onDownload} />
                <DownloadLink href={downloads.cox_svg} iconRole="action.download" label="SVG" onDownload={onDownload} />
              </div>
            </div>
            <AuthorizedImage className="cox-forest-plot" src={downloads.cox_png} alt="Grouped Cox model forest plot" />
          </>
        ) : null}
        </details>
        </section>
      </ResultSection>

      {metrics.competing_risks?.applicable && (
        <ResultSection id="competing" title="Competing risks" helpId="competingRisk" descriptionHelpId="resultCompetingView">
          <CompetingRiskPanel
            competing={metrics.competing_risks}
            downloads={downloads}
            endpointLabel={endpointLabel}
            onDownload={onDownload}
          />
        </ResultSection>
      )}

      {combinedSignature && (
        <ResultSection id="interaction" title="Signature effects" description="Main effects and the prespecified interaction.">
          <CombinedSignatureSummary combined={combinedSignature} />
          <div className="combined-signature-scoring">
            <SignatureScoringSummary
              signature={combinedSignature.signature_a}
              title={`${combinedSignature.signature_a?.name || "Signature A"} scoring`}
            />
            <SignatureScoringSummary
              signature={combinedSignature.signature_b}
              title={`${combinedSignature.signature_b?.name || "Signature B"} scoring`}
            />
          </div>
          <SignatureInteractionCoxTable models={metrics.signature_interaction_cox_models} />
        </ResultSection>
      )}

      <ResultSection id="diagnostics" title="Diagnostics & provenance">
      <DiagnosticsDisclosure
        {...(guideAnchors
          ? {
              as: "section",
              anchor: GUIDE_ANCHORS.SURVIVAL_DIAGNOSTICS,
              label: "Survival diagnostics and provenance",
            }
          : {})}
        className="result-disclosure"
      >

        {!combinedSignature && <SignatureScoringSummary signature={metrics.signature} title="Marker and score details" />}
        <AuditSummary audit={metrics.audit_report} />
        {combinedSignature ? (
          <div className="result-details">
            <ExpressionDistribution
              title={`${combinedSignature.signature_a?.name || "Signature A"} score distribution`}
              distribution={metrics.expression_distribution_a}
              cutpointDetails={signatureCutpointDetails(metrics.cutpoint_details, "signature_a")}
            />
            <ExpressionDistribution
              title={`${combinedSignature.signature_b?.name || "Signature B"} score distribution`}
              distribution={metrics.expression_distribution_b}
              cutpointDetails={signatureCutpointDetails(metrics.cutpoint_details, "signature_b")}
            />
          </div>
        ) : (
          <div className="result-details">
            <ExpressionDistribution distribution={metrics.expression_distribution} cutpointDetails={metrics.cutpoint_details} />
            <QualitySummary quality={metrics.quality} />
          </div>
        )}
        {combinedSignature && (
          <div className="result-details single">
            <QualitySummary quality={metrics.quality} />
          </div>
        )}
        <AnalysisNotices
          warnings={analysis.warnings}
          notices={analysis.notices}
          diagnostics={analysis.diagnostics}
          continuousModels={continuous.linear_models}
          models={metrics.cox_models}
          interactionModels={metrics.signature_interaction_cox_models}
        />
      </DiagnosticsDisclosure>
      </ResultSection>
      </ResultTabs>
    </div>
  );
}

function SignaturePanelResult({ analysis, metrics, onDownload, guideAnchors = false }) {
  const downloads = analysis.downloads || {};
  const panel = metrics.signature_panel || {};
  const families = metrics.model_families || {};
  const adjusted = families.adjusted || {};
  const joint = families.joint || {};
  const primary = adjusted.status === "completed" ? adjusted : joint;
  const primaryLabel =
    adjusted.status === "completed"
      ? "Joint clinically adjusted Cox"
      : "Joint unadjusted Cox";
  const univariable = Array.isArray(families.univariable)
    ? families.univariable
    : [];
  const correlations = (metrics.score_correlations?.pairs || []).filter(
    (pair) => pair.signature_a !== pair.signature_b,
  );
  const overlapPairs = panel.gene_overlap?.pairs || [];
  const scoringSignatures = metrics.signatures || panel.signatures || [];
  const primaryPlot =
    adjusted.status === "completed" && downloads.signature_panel_adjusted_png
      ? downloads.signature_panel_adjusted_png
      : downloads.signature_panel_joint_png || downloads.cox_png || downloads.png;
  const primaryPlotSvg =
    adjusted.status === "completed" && downloads.signature_panel_adjusted_svg
      ? downloads.signature_panel_adjusted_svg
      : downloads.signature_panel_joint_svg || downloads.cox_svg || downloads.svg;
  const DiagnosticsDisclosure = guideAnchors ? GuideAnchor : "section";
  const sampleSelection = metrics.sample_selection || {};
  const molecularPopulation = sampleSelection.sample_population || null;

  return (
    <div className="analysis-result signature-panel-result">
      <div className="result-header">
        <div>
          <span className="result-family-label">Signature panel · main effects</span>
          <h2>{panel.name || analysis.gene_symbol} · {metrics.endpoint_label || metrics.endpoint}</h2>
          <p className="result-context">
            {resultSourceLabel(metrics.dataset, analysis.cohort, getCohortName)} · {metrics.expression_scale_label || "Expression"}
            {analysis.cached ? " · cached" : ""}
          </p>
        </div>
        <ResultDownloads
          downloads={downloads}
          onDownload={onDownload}
          primaryPlotLabel="Panel Cox"
          guideAnchor={guideAnchors}
        />
      </div>

      {molecularPopulation && (
        <details className="result-source-details">
          <summary>RNA population: {molecularPopulation.label} · {formatInteger(sampleSelection.retained_patients)} patients</summary>
          <div className="result-population-contract" role="note">
          <span>
            <strong>
              {formatInteger(sampleSelection.retained_patients)} patients · {formatInteger(retainedSampleCount(sampleSelection))} RNA samples
            </strong>
            <small>
              {formatSampleTypeCounts(sampleSelection.retained_sample_types)} · TCGA {molecularPopulation.allowed_tcga_sample_codes?.join("/")}
              {` · ${sampleSelection.population_excluded_samples || 0} other-tissue samples excluded`}
            </small>
          </span>
          </div>
        </details>
      )}

      <div className="metric-strip signature-panel-metrics">
        <Metric label="Common patients" value={metrics.n_patients} />
        <Metric label="Events" value={metrics.n_events} />
        <Metric label="Signatures" value={panel.signatures?.length} />
        <Metric label="Effect unit" value="+1 panel SD" />
        <Metric label="Primary model" value={primary.status === "completed" ? primaryLabel : "Not evaluable"} />
      </div>

      <ResultTabs label="Signature panel result sections">
      <ResultSection id="joint" title="Joint model">
      <section className="panel-primary-evidence">
        <p className="result-model-label">{primaryLabel} · all signatures fitted together</p>
        <SignaturePanelModelTable models={[primary]} />
        {primaryPlot && (
          <>
            <div className="plot-download-row">
              <span>{primaryLabel} forest plot</span>
              <div className="download-row">
                <DownloadLink href={primaryPlot} iconRole="file.image" label="PNG" onDownload={onDownload} />
                <DownloadLink href={primaryPlotSvg} iconRole="action.download" label="SVG" onDownload={onDownload} />
              </div>
            </div>
            <img
              className="cox-forest-plot"
              src={apiUrl(primaryPlot)}
              alt={`${primaryLabel} signature-panel forest plot`}
            />
          </>
        )}
      </section>

      </ResultSection>
      <ResultSection id="univariable" title="Univariable context">
        <SignaturePanelModelTable models={univariable} />
        {downloads.cox_univariable_png && (
          <img
            className="cox-forest-plot"
            src={apiUrl(downloads.cox_univariable_png)}
            alt="Univariable signature-panel forest plot"
          />
        )}
      </ResultSection>

      {adjusted.status !== "completed" && adjusted.status !== "not_requested" && (
        <ResultSection id="adjustment" title="Requested clinical adjustment">
          <p className="method-note">{adjusted.reason || "The requested complete-case adjusted model could not be estimated."}</p>
        </ResultSection>
      )}

      <ResultSection id="relationships" title="Score relationships">
        <div className="panel-context-grid">
          <SignatureCorrelationTable pairs={correlations} />
          <SignatureOverlapTable pairs={overlapPairs} />
        </div>
      </ResultSection>

      {metrics.competing_risks?.applicable && (
        <ResultSection id="competing" title="Competing risks">
          <FineGrayModelTable
            title="Signature-panel Fine-Gray models"
            models={metrics.competing_risks.continuous_fine_gray_models}
          />
        </ResultSection>
      )}

      <ResultSection id="diagnostics" title="Diagnostics & provenance">
      <DiagnosticsDisclosure
        {...(guideAnchors
          ? {
              as: "section",
              anchor: GUIDE_ANCHORS.SURVIVAL_DIAGNOSTICS,
              label: "Signature panel diagnostics and provenance",
            }
          : {})}
        className="result-disclosure"
      >

        <AnalysisNotices
          warnings={analysis.warnings}
          notices={analysis.notices}
          diagnostics={analysis.diagnostics}
          models={metrics.signature_panel_cox_models}
        />
      {!!scoringSignatures.length && (
        <div className="signature-panel-scoring">
          {scoringSignatures.map((signature, index) => (
            <SignatureScoringSummary
              key={`${signature.name || "signature"}-${index}`}
              signature={signature}
              title={`${signature.name || `Signature ${index + 1}`} scoring`}
            />
          ))}
        </div>
      )}

        <AuditSummary audit={metrics.audit_report} />
        <QualitySummary quality={metrics.quality} />
      </DiagnosticsDisclosure>
      </ResultSection>
      </ResultTabs>
    </div>
  );
}

function SignaturePanelModelTable({ models = [] }) {
  const rows = models.flatMap((model) => {
    const terms = model?.marker_terms || [];
    return terms.length
      ? terms.map((term) => ({ model, term }))
      : model
        ? [{ model, term: null }]
        : [];
  });
  if (!rows.length) return <p className="method-note">No evaluable model rows were returned.</p>;
  return (
    <div className="signature-panel-model-table" role="region" aria-label="Scrollable signature panel model results" tabIndex={0}>
      <table aria-label="Signature panel Cox model estimates">
        <thead>
          <tr>
            <th scope="col">Signature</th>
            <th scope="col">Patients</th>
            <th scope="col">Events</th>
            <th scope="col"><Term id="hazard_ratio">HR</Term> / +1 SD (<Term id="confidence_interval">95% CI</Term>)</th>
            <th scope="col">p</th>
            <th scope="col"><Term id="fdr">BH q</Term></th>
            <th scope="col"><Term id="proportional_hazards">PH</Term> p</th>
            <th scope="col">Model</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(({ model, term }, index) => (
            <tr key={`${model.model || "model"}-${term?.signature || index}`}>
              <th scope="row">{term?.signature || "Not evaluable"}</th>
              <td>{formatInteger(model.n_patients)}</td>
              <td>{formatInteger(model.n_events)}</td>
              <td>{term ? formatHrValues(term) : "..."}</td>
              <td>{term ? formatP(term.p_value) : "..."}</td>
              <td>{term ? formatP(term.multiplicity?.bh_q_value) : "..."}</td>
              <td>{term ? formatP(term.ph_p_value) : "..."}</td>
              <td title={model.reason || formatCoxCovariates(model.covariates)}>
                {model.status === "completed" ? model.label : formatModelStatus(model)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function SignatureCorrelationTable({ pairs = [] }) {
  return (
    <div>
      <h4>Score correlation</h4>
      {pairs.length ? (
        <table aria-label="Pairwise signature correlations">
          <thead>
            <tr><th scope="col">Pair</th><th scope="col">Pearson</th><th scope="col">Spearman</th></tr>
          </thead>
          <tbody>
            {pairs.map((pair) => (
              <tr key={`${pair.signature_a}-${pair.signature_b}`}>
                <th scope="row">{pair.signature_a} / {pair.signature_b}</th>
                <td>{formatCompactNumber(pair.pearson)}</td>
                <td>{formatCompactNumber(pair.spearman)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : <p className="method-note">No pairwise correlations were returned.</p>}
    </div>
  );
}

function SignatureOverlapTable({ pairs = [] }) {
  return (
    <div>
      <h4>Gene overlap</h4>
      {pairs.length ? (
        <table aria-label="Pairwise signature gene overlap">
          <thead>
            <tr><th scope="col">Pair</th><th scope="col">Shared</th><th scope="col">Jaccard</th></tr>
          </thead>
          <tbody>
            {pairs.map((pair) => (
              <tr key={`${pair.signature_a}-${pair.signature_b}`}>
                <th scope="row">{pair.signature_a} / {pair.signature_b}</th>
                <td title={(pair.shared_genes || []).join(", ")}>
                  {formatInteger(pair.shared_gene_count)}
                </td>
                <td>{formatCompactNumber(pair.jaccard)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : <p className="method-note">No pairwise overlap rows were returned.</p>}
    </div>
  );
}

function ContinuousAnalysisSummary({ continuous, downloads, geneSymbol, onDownload }) {
  const models = continuous?.linear_models || [];
  const spline = continuous?.spline || {};
  const completed = continuous?.status === "completed";
  const splineCompleted = spline.status === "completed";
  const selectedPercentiles = (spline.profile || []).filter((point) =>
    [5, 25, 50, 75, 95].some((percentile) =>
      Math.abs(Number(point.percentile) - percentile) < 0.01
    )
  );

  return (
    <section className="detail-section continuous-analysis">
      {!completed ? (
        <div className="method-note">
          Continuous modeling was not estimable: {continuous?.reason || "No complete continuous population was available."}
        </div>
      ) : (
        <>
          <details className="result-more-details">
            <summary>All Cox models and model checks</summary>
          <div className="continuous-model-table" role="region" aria-label="Scrollable continuous Cox model results" tabIndex={0}>
            <table aria-label="Continuous Cox model estimates">
              <thead>
                <tr>
                  <th scope="col">Model</th>
                  <th scope="col">Patients</th>
                  <th scope="col">Events</th>
                  <th scope="col" title="Observed events divided by the number of fitted model coefficients">
                    Events / parameter
                  </th>
                  <th scope="col" title="Hazard ratio for a one-standard-deviation increase in expression, with 95% confidence interval">
                    <Term id="hazard_ratio">HR</Term> / +1 SD (
                    <Term id="confidence_interval">95% CI</Term>)
                  </th>
                  <th scope="col">p</th>
                  <th scope="col" title="Firth penalized sensitivity is run for low-information, unstable or extreme standard Cox fits">
                    Firth sensitivity
                  </th>
                  <th scope="col" title="Proportional-hazards diagnostic for the expression term">
                    <Term id="proportional_hazards">PH</Term> p (marker)
                  </th>
                  <th scope="col" title="Global proportional-hazards diagnostic for the complete model">PH p (global)</th>
                  <th scope="col">Issue</th>
                </tr>
              </thead>
              <tbody>
                {models.map((model) => {
                  const markerPh = toNullableNumber(model.ph_p_value);
                  const globalPh = toNullableNumber(model.ph_global_p_value);
                  const markerFlagged = markerPh !== null && markerPh < ROBUSTNESS_ALPHA;
                  const globalFlagged = globalPh !== null && globalPh < ROBUSTNESS_ALPHA;
                  const warnings = model.warnings || [];
                  return (
                    <tr key={model.model || model.label}>
                      <th scope="row" title={formatCoxCovariates(model.covariates)}>
                        {formatContinuousModelLabel(model)}
                      </th>
                      <td>{formatInteger(model.n_patients)}</td>
                      <td>{formatInteger(model.n_events)}</td>
                      <CoxInformationCell model={model} />
                      <td>{model.status === "completed" ? formatHrValues(model) : "..."}</td>
                      <td>{model.status === "completed" ? formatP(model.p_value) : "..."}</td>
                      <PenalizedSensitivityCell model={model} />
                      <td className={markerFlagged ? "model-diagnostic-caution" : ""}>
                        {model.status === "completed" ? formatP(markerPh) : "..."}
                      </td>
                      <td className={globalFlagged ? "model-diagnostic-caution" : ""}>
                        {model.status === "completed" ? formatP(globalPh) : "..."}
                      </td>
                      <td
                        className={warnings.length ? "model-status-cell caution" : "model-status-cell"}
                        title={warnings.length ? warnings.join(" · ") : model.reason || undefined}
                      >
                        {warnings.length
                          ? `${warnings.length} caution${warnings.length === 1 ? "" : "s"}`
                          : model.status === "completed"
                            ? "None"
                            : formatModelStatus(model)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          </details>
          <TimeVaryingEffectTable
            models={models}
            title="Expression effect over follow-up"
          />

          <div className="continuous-spline-summary">
            <div>
              <span>Spline overall p</span>
              <strong>{splineCompleted ? formatP(spline.overall_p_value) : "Not evaluable"}</strong>
            </div>
            <div>
              <span>Nonlinearity p</span>
              <strong>{splineCompleted ? formatP(spline.nonlinearity_p_value) : "Not evaluable"}</strong>
            </div>
          </div>

          {splineCompleted && downloads.continuous_png ? (
            <>
              <div className="plot-download-row">
                <span>Survival across the expression range</span>
                <div className="download-row">
                  <DownloadLink href={downloads.continuous_png} iconRole="file.image" label="PNG" onDownload={onDownload} />
                  <DownloadLink href={downloads.continuous_svg} iconRole="action.download" label="SVG" onDownload={onDownload} />
                  <DownloadLink href={downloads.continuous_csv} iconRole="file.csv" label="Data" onDownload={onDownload} />
                </div>
              </div>
              <img
                className="continuous-effect-plot"
                src={apiUrl(downloads.continuous_png)}
                alt={`${geneSymbol} restricted cubic spline hazard-ratio profile relative to median expression`}
              />
            </>
          ) : (
            <div className="method-note">
              Restricted cubic spline was not estimated: {spline.reason || "The event or expression requirements were not met."}
            </div>
          )}

          <details className="result-more-details">
            <summary>Curve settings</summary>
            <dl className="result-setting-list">
              <div><dt>Expression SD</dt><dd>{formatCompactNumber(continuous.predictor?.standard_deviation)}</dd></div>
              <div><dt>Reference</dt><dd>{splineCompleted ? `Median (${formatCompactNumber(spline.reference_expression)})` : "Not evaluable"}</dd></div>
              <div><dt>Knot percentiles</dt><dd>{splineCompleted ? "5 / 35 / 65 / 95" : "Not evaluable"}</dd></div>
            </dl>
          </details>
          {selectedPercentiles.length > 0 && (
            <details className="continuous-percentile-table">
              <summary>Effect estimates at selected percentiles</summary>
              <table aria-label="Spline expression profile estimates">
                <thead>
                  <tr>
                    <th scope="col">Expression percentile</th>
                    <th scope="col">Expression value</th>
                    <th scope="col">HR relative to median</th>
                    <th scope="col">95% CI</th>
                  </tr>
                </thead>
                <tbody>
                  {selectedPercentiles.map((point) => (
                    <tr key={point.percentile}>
                      <td>{formatPercent(point.percentile)}</td>
                      <td>{formatCompactNumber(point.expression_value)}</td>
                      <td>{formatCompactNumber(point.hazard_ratio)}</td>
                      <td>{formatCompactNumber(point.hr_conf_low)} to {formatCompactNumber(point.hr_conf_high)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </details>
          )}
        </>
      )}
    </section>
  );
}

function CompetingRiskPanel({
  competing,
  downloads,
  endpointLabel,
  onDownload,
}) {
  const t = useHelpText();
  if (!competing?.applicable) return null;

  const coding = competing.coding || {};
  const codes = coding.status_codes || {};
  const cumulative = competing.cumulative_incidence || {};
  const gray = cumulative.gray_test || {};
  const groupSummary = Array.isArray(cumulative.group_summary)
    ? cumulative.group_summary
    : Object.entries(cumulative.group_summary || {}).map(([group, values]) => ({
      group,
      ...(values || {}),
    }));
  const horizons = cumulative.horizons || [];
  const cumulativeCompleted = cumulative.status === "completed";

  return (
    <section className="detail-section competing-risk-analysis">
      <div className="competing-risk-estimands">
        <div>
          <span>Kaplan-Meier and Cox</span>
          <strong>Event-free and cause-specific</strong>
          <p>Competing deaths (code 2) end follow-up without counting as the event of interest.</p>
        </div>
        <div>
          <span>CIF, Gray and Fine-Gray</span>
          <strong>Subdistribution-based</strong>
          <p>Competing deaths (code 2) are accounted for when estimating the probability of the event of interest.</p>
        </div>
      </div>

      <div className="competing-risk-coding">
        <span>{coding.source || "TCGA-CDR competing-event coding"}</span>
        <code>0 = {codes["0"] || "censored"}</code>
        <code>1 = {codes["1"] || "event of interest"}</code>
        <code>2 = {codes["2"] || "competing event"}</code>
      </div>

      {competing.status !== "completed" && (
        <div className="method-note caution">
          Competing-risk estimates were not evaluable: {competing.reason || cumulative.reason || "The required event support was not available."}
        </div>
      )}

      {cumulativeCompleted ? (
        <>
          <div className="competing-risk-summary">
            <Metric label="Patients" value={formatInteger(cumulative.n_patients)} />
            <Metric label="Target events" value={formatInteger(cumulative.n_events_of_interest)} />
            <Metric label="Competing deaths" value={formatInteger(cumulative.n_competing_events)} />
            <Metric
              label="Gray p"
              value={gray.status === "completed" ? formatP(gray.p_value) : "Not evaluable"}
            />
          </div>

          <div className="competing-risk-subsection">
            <h4>Observed endpoint states by group</h4>
            <div className="competing-risk-table" role="region" aria-label="Scrollable observed competing-risk endpoint states" tabIndex={0}>
              <table aria-label="Competing-risk group counts">
                <caption className="sr-only">
                  Patient outcomes used for the {endpointLabel} competing-risk analysis
                </caption>
                <thead>
                  <tr>
                    <th scope="col">Group</th>
                    <th scope="col">Patients</th>
                    <th scope="col">Target events</th>
                    <th scope="col">Competing deaths</th>
                    <th scope="col">Censored</th>
                  </tr>
                </thead>
                <tbody>
                  {groupSummary.map((row) => (
                    <tr key={row.group}>
                      <th scope="row">{formatLabel(row.group)}</th>
                      <td>{formatInteger(row.patients)}</td>
                      <td>{formatInteger(row.events_of_interest)}</td>
                      <td>{formatInteger(row.competing_events)}</td>
                      <td>{formatInteger(row.censored)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div className="competing-risk-subsection">
            <h4>Cumulative incidence at fixed horizons</h4>
            <div className="competing-risk-table competing-risk-horizons" role="region" aria-label="Scrollable cumulative incidence estimates" tabIndex={0}>
              <table aria-label="Cumulative incidence estimates by horizon">
                <caption className="sr-only">
                  Pointwise cumulative-incidence estimates with 95 percent confidence intervals and patients at risk
                </caption>
                <thead>
                  <tr>
                    <th scope="col">Horizon</th>
                    <th scope="col">Group</th>
                    <th scope="col">CIF</th>
                    <th scope="col">95% CI</th>
                    <th scope="col">At risk</th>
                    <th scope="col">Support</th>
                  </tr>
                </thead>
                <tbody>
                  {horizons.flatMap((horizon) =>
                    Object.entries(horizon.groups || {}).map(([group, estimate]) => (
                      <tr key={`${horizon.time_days}-${group}`}>
                        <th scope="row">{formatHorizonYears(horizon)}</th>
                        <td>{formatLabel(group)}</td>
                        <td>{formatCif(estimate?.estimate)}</td>
                        <td>{formatCifInterval(estimate)}</td>
                        <td>{formatInteger(estimate?.n_at_risk)}</td>
                        <td className={estimate?.supported ? "support-adequate" : "support-caution"}>
                          {estimate?.supported ? "Adequate" : "Fewer than 5"}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
            <p className="competing-risk-note">
              Pointwise 95% intervals use Aalen variance. Estimates with fewer than five patients at risk in a group remain visible but are marked as low support.
            </p>
          </div>

          {downloads.cumulative_incidence_png && (
            <>
              <div className="plot-download-row">
                <span>Cumulative-incidence curves</span>
                <div className="download-row">
                  <DownloadLink
                    href={downloads.cumulative_incidence_png}
                    iconRole="file.image"
                    label="PNG"
                    onDownload={onDownload}
                  />
                  <DownloadLink
                    href={downloads.cumulative_incidence_svg}
                    iconRole="action.download"
                    label="SVG"
                    onDownload={onDownload}
                  />
                </div>
              </div>
              <img
                className="cumulative-incidence-plot"
                src={apiUrl(downloads.cumulative_incidence_png)}
                alt={`${endpointLabel} cumulative-incidence curves by expression group`}
              />
            </>
          )}
        </>
      ) : (
        <div className="method-note">
          Cumulative incidence was not estimated: {cumulative.reason || "The target or competing-event requirements were not met."}
        </div>
      )}

      <FineGrayModelTable
        title="Grouped Fine-Gray models"
        models={competing.grouped_fine_gray_models}
      />
      <FineGrayModelTable
        title="Continuous Fine-Gray models"
        models={competing.continuous_fine_gray_models}
      />

      <p className="competing-risk-note">
        Fine-Gray estimates are SHR values for the event-of-interest cumulative incidence. They are not interchangeable with the cause-specific HR values reported above.
      </p>
    </section>
  );
}

function FineGrayModelTable({ title, models = [] }) {
  if (!models.length) return null;
  const rows = models.flatMap((model) => {
    const markerTerms = model.status === "completed"
      ? model.marker_terms || []
      : [];
    return markerTerms.length
      ? markerTerms.map((term) => ({ model, term }))
      : [{ model, term: null }];
  });

  return (
    <div className="competing-risk-subsection fine-gray-models">
      <h4>{title}</h4>
      <div className="fine-gray-table" role="region" aria-label={`Scrollable ${title}`} tabIndex={0}>
        <table aria-label={title}>
          <caption className="sr-only">
            {title} with subdistribution hazard ratios and model-specific support
          </caption>
          <thead>
            <tr>
              <th scope="col">Model</th>
              <th scope="col">Contrast</th>
              <th scope="col">Patients</th>
              <th scope="col">Target events</th>
              <th scope="col">Competing</th>
              <th scope="col">Events / parameter</th>
              <th scope="col" title="Subdistribution hazard ratio with 95% confidence interval">
                SHR (95% CI)
              </th>
              <th scope="col">p</th>
              <th scope="col">Issue</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(({ model, term }, index) => {
              const warnings = model.warnings || [];
              const issue = warnings.length
                ? `${warnings.length} caution${warnings.length === 1 ? "" : "s"}`
                : model.status === "completed"
                  ? "None"
                  : formatModelStatus(model);
              return (
                <tr key={`${model.model || model.label}-${term?.term || index}`}>
                  <th scope="row" title={formatCoxCovariates(model.covariates)}>
                    {formatFineGrayModelLabel(model)}
                  </th>
                  <td>{term?.contrast || model.marker_effect_unit || "Not evaluable"}</td>
                  <td>{formatInteger(model.n_patients)}</td>
                  <td>{formatInteger(model.n_events_of_interest)}</td>
                  <td>{formatInteger(model.n_competing_events)}</td>
                  <td className={fineGrayInformationClass(model.events_per_parameter)}>
                    {formatFineGrayInformation(model)}
                  </td>
                  <td>{term ? formatShrValues(term) : "..."}</td>
                  <td>{term ? formatP(term.p_value) : "..."}</td>
                  <td
                    className={warnings.length ? "model-status-cell caution" : "model-status-cell"}
                    title={warnings.length ? warnings.join(" · ") : model.reason || undefined}
                  >
                    {issue}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function AnalysisNotices({
  warnings = [],
  notices = [],
  diagnostics,
  continuousModels = [],
  models = [],
  interactionModels = [],
  includeModelDiagnostics = true,
}) {
  const normalizedNotices = normalizeAnalysisNotices({
    notices,
    warnings,
    continuousModels,
    models,
    interactionModels,
    includeModelDiagnostics,
  });
  const groups = groupAnalysisNotices(normalizedNotices);
  if (!groups.length) return null;

  return (
    <section className="analysis-notices" aria-label="Evidence context and analysis diagnostics">
      <div className="analysis-notices-intro">
        <h3>{includeModelDiagnostics ? "Diagnostics" : "Context"}</h3>
        {diagnostics?.primary_result_model_label && (
          <span>Primary: {diagnostics.primary_result_model_label}</span>
        )}
      </div>
      {groups.length > 0 && (
        <div className="analysis-notice-groups">
          {groups.map((group) => (
            <details
              key={group.kind}
              className={`analysis-notice-group ${group.kind}`}
              open={group.open}
            >
              <summary>
                <span className="analysis-notice-mark" aria-hidden="true">
                  <TraceIcon
                    role={group.iconRole}
                    size="sm"
                    tone={group.tone}
                  />
                </span>
                <span>
                  <strong>{group.title}</strong>
                  <small>{group.subtitle}</small>
                </span>
                <b>{group.items.length}</b>
              </summary>
              <ul>
                {group.items.map((item, index) => (
                  <li
                    key={`${group.kind}-${index}`}
                    className={`notice-${item.severity || "info"}`}
                  >
                    {item.model_label && <strong>{item.model_label}: </strong>}
                    {item.message}
                  </li>
                ))}
              </ul>
            </details>
          ))}
        </div>
      )}
    </section>
  );
}

function normalizeAnalysisNotices({
  notices = [],
  warnings = [],
  continuousModels = [],
  models = [],
  interactionModels = [],
  includeModelDiagnostics = true,
}) {
  if (notices.length) return notices;
  const normalized = [];
  const selectedAdjustedModel =
    includeModelDiagnostics
      ? downstreamAdjustedContinuousModel(continuousModels)
        || downstreamAdjustedModel(models)
        || downstreamAdjustedInteractionModel(interactionModels)
      : null;
  const selectedModelId = selectedAdjustedModel?.model;
  const modelMessages = new Set();

  (includeModelDiagnostics ? [...continuousModels, ...models, ...interactionModels] : []).forEach((model) => {
    (model.warnings || []).forEach((message) => {
      const key = `${model.model}:${message}`;
      if (modelMessages.has(key)) return;
      modelMessages.add(key);
      normalized.push({
        category: "model",
        severity: "caution",
        scope: model.model === selectedModelId ? "primary" : "auxiliary",
        priority: model.model === selectedModelId ? "medium" : "low",
        message: String(message),
        model: model.model,
        model_label: model.label,
        selected_model: model.model === selectedModelId,
      });
    });
  });

  warnings.forEach((warning) => {
    const text = String(warning);
    const lower = text.toLowerCase();
    if (lower.startsWith("cox model warning:")) return;
    const isCohortInformation =
      /(samples? (?:were )?excluded|extra sample records|one sample per patient|retained patient-level|eligible barcodes|biospecimen priority|administratively censored|follow-up time exceeding|sample type)/.test(lower);
    normalized.push({
      category: isCohortInformation ? "cohort" : "method",
      severity: "info",
      scope: "context",
      priority: "low",
      message: text,
      selected_model: false,
    });
  });

  return normalized;
}

function groupAnalysisNotices(notices = []) {
  const definitions = {
    primary: {
      kind: "primary",
      title: "Primary result",
      subtitle: "Issues affecting the main estimate",
      iconRole: "status.caution",
      tone: "caution",
      items: [],
    },
    requested_adjustment: {
      kind: "requested-adjustment",
      title: "Requested clinical adjustment",
      subtitle: "Availability and assumptions of the model you requested",
      iconRole: "status.caution",
      tone: "caution",
      items: [],
    },
    auxiliary: {
      kind: "auxiliary",
      title: "Sensitivity and auxiliary models",
      subtitle: "Useful context that does not override the primary estimate",
      iconRole: "status.info",
      tone: "accent",
      items: [],
    },
    context: {
      kind: "context",
      title: "Cohort and method context",
      subtitle: "Provenance, exclusions and interpretation notes",
      iconRole: "status.info",
      tone: "accent",
      items: [],
    },
  };

  notices.forEach((notice) => {
    const kind = notice.scope === "requested_adjustment"
      ? "requested_adjustment"
      : notice.scope === "primary"
        ? "primary"
        : notice.scope === "auxiliary"
          ? "auxiliary"
          : "context";
    if (definitions[kind]) definitions[kind].items.push(notice);
  });

  const severityRank = { error: 0, caution: 1, not_evaluable: 2, info: 3 };
  const priorityRank = { high: 0, medium: 1, low: 2 };
  return ["primary", "requested_adjustment", "auxiliary", "context"]
    .map((kind) => definitions[kind])
    .filter((group) => group.items.length)
    .map((group) => {
      group.items.sort((left, right) =>
        (priorityRank[left.priority] ?? 3) - (priorityRank[right.priority] ?? 3)
        || (severityRank[left.severity] ?? 4) - (severityRank[right.severity] ?? 4)
      );
      const hasError = group.items.some((item) => item.severity === "error");
      const hasDecisionCaution = group.items.some(
        (item) =>
          item.priority === "high"
          || item.priority === "medium"
          || item.severity === "not_evaluable",
      );
      return {
        ...group,
        iconRole: hasError ? "status.error" : group.iconRole,
        tone: hasError ? "error" : group.tone,
        open:
          ["primary", "requested-adjustment"].includes(group.kind)
          && hasDecisionCaution,
      };
    });
}

function CoxInformationCell({ model }) {
  const information = model?.information_diagnostics;
  const eventsPerParameter = toNullableNumber(information?.events_per_parameter);
  const parameterCount = Number(information?.parameter_count);
  if (eventsPerParameter === null || !Number.isFinite(parameterCount)) {
    return <td className="cox-information-cell">...</td>;
  }
  const status = information?.status || "not-evaluable";
  const statusLabel = {
    adequate: "adequate",
    caution: "caution",
    severe: "severe caution",
  }[status] || "not evaluable";
  const threshold = Number(information?.caution_threshold || 10);
  const severeThreshold = Number(information?.severe_threshold || 5);
  return (
    <td
      className={`cox-information-cell ${status}`}
      title={`Events per fitted parameter. Caution below ${threshold}; severe caution below ${severeThreshold}.`}
    >
      <strong>{eventsPerParameter.toFixed(1)}</strong>
      <small>
        {parameterCount} parameter{parameterCount === 1 ? "" : "s"} · {statusLabel}
      </small>
    </td>
  );
}

function TimeVaryingEffectTable({ models, title = "Marker effect over follow-up" }) {
  const triggeredModels = (models || []).filter((model) => {
    const status = model?.time_varying_effect?.status;
    return ["completed", "skipped", "failed"].includes(status);
  });
  if (!triggeredModels.length) return null;
  const rows = triggeredModels.flatMap((model) => {
    const primary = model.time_varying_effect || {};
    return [
      {
        model,
        diagnostic: primary,
        role: "Primary",
      },
      ...(primary.sensitivity_analyses || []).map((diagnostic) => ({
        model,
        diagnostic,
        role: "Sensitivity",
      })),
    ];
  });

  return (
    <div className="time-varying-effect-block">
      <DetailSectionTitle
        title={title}
        helpId="phTwoPeriod"
      />
      <div className="table-scroll" role="region" aria-label="Scrollable time-varying effect diagnostics" tabIndex={0}>
        <table aria-label={title}>
          <thead>
            <tr>
              <th scope="col">Model</th>
              <th scope="col">Split</th>
              <th scope="col">Marker PH p</th>
              <th scope="col">Early HR (95% CI)</th>
              <th scope="col">Late HR (95% CI)</th>
              <th scope="col">Late / early HR ratio</th>
              <th scope="col">Support</th>
              <th scope="col">Status</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(({ model, diagnostic, role }) => {
              const early = diagnostic.periods?.early;
              const late = diagnostic.periods?.late;
              const change = diagnostic.change;
              const support = diagnostic.support || {};
              const completed = diagnostic.status === "completed";
              const splitYears = toNullableNumber(diagnostic.split_years);
              const splitLabel = splitYears === 1
                ? "1 year"
                : splitYears === null
                  ? "..."
                  : `${formatCompactNumber(splitYears)} years`;
              return (
                <tr key={`temporal-${model.model || model.label}-${role}-${splitLabel}`}>
                  <th scope="row">{model.label || formatLabel(model.model)}</th>
                  <td>
                    <strong>{splitLabel}</strong>
                    <small>{role}</small>
                  </td>
                  <td className="model-diagnostic-caution">{formatP(model.ph_p_value)}</td>
                  <td>{completed ? formatHrValues(early) : "..."}</td>
                  <td>{completed ? formatHrValues(late) : "..."}</td>
                  <td>
                    {completed ? (
                      <>
                        <strong>{formatTemporalHrRatio(change)}</strong>
                        <small>p {formatP(change?.p_value)}</small>
                      </>
                    ) : "..."}
                  </td>
                  <td>
                    <strong>
                      {formatInteger(support.early_events)} / {formatInteger(support.late_events)} events
                    </strong>
                    <small>{formatInteger(support.at_risk_at_split)} at risk at split</small>
                  </td>
                  <td
                    className={`temporal-model-status ${diagnostic.status}`}
                    title={diagnostic.reason || diagnostic.split_rule}
                  >
                    {completed ? "Estimated" : formatModelStatus(diagnostic)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="time-varying-method-note">
        Diagnostic summary, not additional primary tests. Ratios are Wald contrasts for marker-by-period interactions; the two-period model is a coarse approximation to a potentially smooth time-varying effect. HRs use Efron ties and participant-clustered robust variance.
      </p>
    </div>
  );
}

function PenalizedSensitivityCell({ model }) {
  const sensitivity = model?.penalized_sensitivity;
  if (!sensitivity) return <td className="penalized-sensitivity-cell">...</td>;
  const reasons = (sensitivity.trigger_reasons || []).join(" ");
  if (sensitivity.status === "completed") {
    return (
      <td
        className="penalized-sensitivity-cell completed"
        title={`${sensitivity.method || "Firth penalized Cox"}. ${reasons}`.trim()}
      >
        <strong>{formatHrValues(sensitivity)}</strong>
        <small>p {formatP(sensitivity.p_value)} · profile PL</small>
      </td>
    );
  }
  if (sensitivity.status === "not_triggered") {
    return (
      <td className="penalized-sensitivity-cell not-triggered" title={sensitivity.reason}>
        Not triggered
      </td>
    );
  }
  return (
    <td
      className="penalized-sensitivity-cell failed"
      title={[sensitivity.reason, reasons].filter(Boolean).join(" ")}
    >
      {formatModelStatus(sensitivity)}
    </td>
  );
}

function CoxModelTable({ models }) {
  if (!models?.length) return null;
  return (
    <div className="detail-section cox-model-table">
      <DetailSectionTitle
        title="Grouped Cox models"
        helpId="groupedCoxResults"
      />
      <table aria-label="Grouped Cox model estimates">
        <thead>
          <tr>
            <th scope="col">Model</th>
            <th scope="col">Patients</th>
            <th scope="col">Events</th>
            <th scope="col" title="Observed events divided by the number of fitted model coefficients">
              Events / parameter
            </th>
            <th scope="col">HR (95% CI)</th>
            <th scope="col">p</th>
            <th scope="col" title="Firth penalized sensitivity is run for low-information, unstable or extreme standard Cox fits">
              Firth sensitivity
            </th>
            <th scope="col" title="Proportional-hazards diagnostic for the grouped marker term">Marker PH p</th>
            <th scope="col" title="Global proportional-hazards diagnostic for the complete model">Global PH p</th>
            <th scope="col">Issue</th>
          </tr>
        </thead>
        <tbody>
          {models.map((model) => {
            const modelWarnings = model.warnings || [];
            const markerPh = toNullableNumber(model.ph_p_value);
            const globalPh = toNullableNumber(model.ph_global_p_value);
            const markerPhFlagged = markerPh !== null && markerPh < ROBUSTNESS_ALPHA;
            const globalPhFlagged = globalPh !== null && globalPh < ROBUSTNESS_ALPHA;
            const completedWithoutCaution = model.status === "completed" && !modelWarnings.length;
            return (
              <tr key={model.model || model.label}>
                <th
                  scope="row"
                  title={`${model.label || formatLabel(model.model)}; covariates: ${formatCoxCovariates(model.covariates)}`}
                >
                  {formatCoxModelLabel(model)}
                </th>
                <td>{formatInteger(model.n_patients)}</td>
                <td>{formatInteger(model.n_events)}</td>
                <CoxInformationCell model={model} />
                <td>{model.status === "completed" ? formatHrValues(model) : "..."}</td>
                <td>{model.status === "completed" ? formatP(model.p_value) : "..."}</td>
                <PenalizedSensitivityCell model={model} />
                <td className={markerPhFlagged ? "model-diagnostic-caution" : ""}>
                  {model.status === "completed" ? formatP(markerPh) : "..."}
                </td>
                <td className={globalPhFlagged ? "model-diagnostic-caution" : ""}>
                  {model.status === "completed" ? formatP(globalPh) : "..."}
                </td>
                <td
                  className={modelWarnings.length ? "model-status-cell caution" : "model-status-cell"}
                  title={modelWarnings.length ? modelWarnings.join(" · ") : model.reason || undefined}
                >
                  {completedWithoutCaution ? (
                    <span aria-label="No issue; model completed">—</span>
                  ) : modelWarnings.length ? (
                    <span>{modelWarnings.length} caution{modelWarnings.length === 1 ? "" : "s"}</span>
                  ) : (
                    <span>{formatModelStatus(model)}</span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <TimeVaryingEffectTable models={models} />
    </div>
  );
}

function RmstTable({ rmst }) {
  if (!rmst) return null;
  if (rmst.status === "skipped" && String(rmst.reason || "").includes("two expression groups")) {
    return null;
  }
  const completed = rmst.status === "completed";
  const groups = Object.entries(rmst.groups || {});
  return (
    <div className="detail-section rmst-table">
      <DetailSectionTitle
        title="Restricted mean survival time"
        helpId="rmstTau"
      />
      {completed ? (
        <>
          <div className="rmst-summary">
            <div>
              <span>Tau</span>
              <strong>{formatDays(rmst.tau_days)}</strong>
            </div>
            <div>
              <span>Comparison</span>
              <strong>{rmst.comparison_group} vs {rmst.reference_group}</strong>
            </div>
            <div>
              <span>RMST delta</span>
              <strong>{formatRmstDelta(rmst)}</strong>
            </div>
            <div>
              <span>RMST p</span>
              <strong>{formatP(rmst.difference?.p_value)}</strong>
            </div>
          </div>
          <table aria-label="Restricted mean survival time estimates">
            <thead>
              <tr>
                <th scope="col">Group</th>
                <th scope="col">RMST days</th>
                <th scope="col">95% CI</th>
              </tr>
            </thead>
            <tbody>
              {groups.map(([group, item]) => (
                <tr key={group}>
                  <td>{group}</td>
                  <td>{formatDays(item?.rmst_days)}</td>
                  <td>{formatRmstCi(item)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      ) : (
        <div className="method-note">RMST was not estimated: {rmst.reason || formatLabel(rmst.status)}.</div>
      )}
    </div>
  );
}

function SignatureInteractionCoxTable({ models }) {
  if (!models?.length) return null;
  return (
    <div className="detail-section interaction-cox-table">
      <DetailSectionTitle
        title="Two-signature interaction Cox"
        helpId="interactionModel"
      />
      <table aria-label="Two-signature interaction Cox models">
        <thead>
          <tr>
            <th scope="col">Model</th>
            <th scope="col">Covariates</th>
            <th scope="col">Patients</th>
            <th scope="col">Events</th>
            <th scope="col" title="Observed events divided by the number of fitted model coefficients">
              Events / parameter
            </th>
            <th scope="col">Signature A HR</th>
            <th scope="col">Signature B HR</th>
            <th scope="col">Interaction HR</th>
            <th scope="col">Interaction p</th>
            <th scope="col" title="Firth penalized sensitivity for the interaction term">
              Firth interaction
            </th>
            <th scope="col">PH interaction p</th>
            <th scope="col">PH global p</th>
            <th scope="col">Status</th>
          </tr>
        </thead>
        <tbody>
          {models.map((model) => {
            const terms = Object.fromEntries((model.terms || []).map((term) => [term.term, term]));
            const interaction = model.interaction_term || terms["score_a_z:score_b_z"];
            return (
              <tr key={model.model || model.label}>
                <td>{model.label || formatLabel(model.model)}</td>
                <td>{formatCoxCovariates(model.covariates)}</td>
                <td>{formatInteger(model.n_patients)}</td>
                <td>{formatInteger(model.n_events)}</td>
                <CoxInformationCell model={model} />
                <td>{model.status === "completed" ? formatHrValues(terms.score_a_z) : "..."}</td>
                <td>{model.status === "completed" ? formatHrValues(terms.score_b_z) : "..."}</td>
                <td>{model.status === "completed" ? formatHrValues(interaction) : "..."}</td>
                <td>{model.status === "completed" ? formatP(interaction?.p_value) : "..."}</td>
                <PenalizedSensitivityCell model={model} />
                <td
                  className={
                    toNullableNumber(model.ph_p_value) !== null
                    && toNullableNumber(model.ph_p_value) < ROBUSTNESS_ALPHA
                      ? "model-diagnostic-caution"
                      : ""
                  }
                >
                  {model.status === "completed" ? formatP(model.ph_p_value) : "..."}
                </td>
                <td>{model.status === "completed" ? formatP(model.ph_global_p_value) : "..."}</td>
                <td title={model.status === "completed" ? undefined : model.reason || formatLabel(model.status)}>
                  {formatModelStatus(model)}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <TimeVaryingEffectTable
        models={models}
        title="Signature interaction over follow-up"
      />
    </div>
  );
}

function AuditSummary({ audit }) {
  if (!audit?.reproducibility_hash) return null;
  const attestation = audit.server_attestation || {};
  return (
    <div className="detail-section audit-summary">
      <DetailSectionTitle
        title="Run record"
        helpId="auditCapture"
      />
      <dl>
        <div>
          <dt>Schema</dt>
          <dd>{audit.schema_version || "..."}</dd>
        </div>
        <div>
          <dt>Generated</dt>
          <dd>{formatDateTime(audit.generated_at)}</dd>
        </div>
        <div>
          <dt>Analysis hash</dt>
          <dd><code>{audit.reproducibility_hash}</code></dd>
        </div>
        <div>
          <dt>Patient records hash</dt>
          <dd><code>{audit.patient_records_sha256 || "..."}</code></dd>
        </div>
        <div>
          <dt>Server receipt</dt>
          <dd>{attestation.algorithm ? `${attestation.algorithm} signed` : "Not available"}</dd>
        </div>
        <div>
          <dt>Signing key</dt>
          <dd><code>{attestation.key_id || "..."}</code></dd>
        </div>
      </dl>
    </div>
  );
}

function DetailSectionTitle({ title, helpId, help }) {
  return (
    <div className="detail-section-title">
      <h3>{title}</h3>
      {(helpId || help) && (
        <HelpButton label={title} helpId={helpId}>{help}</HelpButton>
      )}
    </div>
  );
}

function Metric({ label, value }) {
  return (
    <div className="metric">
      <span>{label}</span>
      <strong>{value ?? "..."}</strong>
    </div>
  );
}

function CombinedSignatureSummary({ combined }) {
  const signatures = [
    ["Signature A", combined.signature_a],
    ["Signature B", combined.signature_b],
  ];
  const groupingHelp = combined.method === "tertiles"
    ? "Each signature is split into Low, Mid and High before crossing labels."
    : "Each signature is split into Low and High before crossing labels.";
  return (
    <div className="detail-section combined-signature-summary">
      <DetailSectionTitle title="Combined signatures" help={groupingHelp} />
      <table aria-label="Combined signature definitions">
        <thead>
          <tr>
            <th scope="col">Signature</th>
            <th scope="col">Score method</th>
            <th scope="col">Genes</th>
          </tr>
        </thead>
        <tbody>
          {signatures.map(([fallback, signature]) => (
            <tr key={fallback}>
              <td>
                <strong>{signature?.name || fallback}</strong>
                <br />
                <span>{signature?.label || "..."}</span>
              </td>
              <td>{formatLabel(signature?.method || "...")}</td>
              <td>{signatureGenesLabel(signature?.genes)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function signatureGenesLabel(genes) {
  if (!genes?.length) return "...";
  return genes
    .map((gene) => {
      const symbol = gene.resolved_symbol || gene.query;
      return gene.weight !== undefined && Number(gene.weight) !== 1 ? `${symbol}:${gene.weight}` : symbol;
    })
    .join(", ");
}

function GroupTable({ metrics }) {
  const groups = Object.keys(metrics.group_counts || {});
  if (!groups.length) return null;
  const notReachedGroups = groups.filter((group) => isMedianNotReached(metrics.median_survival_days?.[group]));
  return (
    <div className="detail-section">
      <DetailSectionTitle
        title="Survival groups"
        help={notReachedGroups.length ? "Not reached means the Kaplan-Meier curve stayed above 50% survival during follow-up." : undefined}
      />
      <table aria-label="Survival group summary">
        <thead>
          <tr>
            <th scope="col">Group</th>
            <th scope="col">Patients</th>
            <th scope="col">Events</th>
            <th scope="col">Median days</th>
          </tr>
        </thead>
        <tbody>
          {groups.map((group) => (
            <tr key={group}>
              <td>{group}</td>
              <td>{metrics.group_counts?.[group] ?? "..."}</td>
              <td>{metrics.event_counts?.[group] ?? "..."}</td>
              <td>{formatMedianSurvivalDays(metrics.median_survival_days?.[group])}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function CutpointSummary({ details }) {
  if (!details) return null;
  return (
    <div className="detail-section">
      <h3>Cutpoint</h3>
      <dl>
        {Object.entries(details).map(([key, value]) => (
          <div key={key}>
            <dt>{formatLabel(key)}</dt>
            <dd>{typeof value === "number" ? Number(value).toFixed(4) : String(value)}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

function ExpressionDistribution({ distribution, cutpointDetails, title = "Expression distribution before cutpoint" }) {
  if (!distribution?.bins?.length) return null;
  const bins = normalizeDistributionBins(distribution.bins);
  const markers = cutpointMarkers(cutpointDetails);
  const stats = [
    ["Patients", formatInteger(distribution.n)],
    ["Min", formatExpressionValue(distribution.min)],
    ["Q1", formatExpressionValue(distribution.q1)],
    ["Median", formatExpressionValue(distribution.median)],
    ["Q3", formatExpressionValue(distribution.q3)],
    ["Max", formatExpressionValue(distribution.max)],
  ];
  return (
    <div className="detail-section expression-section">
      <h3>{title}</h3>
      <div className="expression-summary">
        {stats.map(([label, value]) => (
          <div key={label}>
            <span>{label}</span>
            <strong>{value}</strong>
          </div>
        ))}
      </div>
      <ExpressionHistogram distribution={distribution} bins={bins} markers={markers} />
    </div>
  );
}

function ExpressionHistogram({ distribution, bins, markers }) {
  const width = 640;
  const height = 230;
  const plot = { top: 24, right: 18, bottom: 42, left: 46 };
  const innerWidth = width - plot.left - plot.right;
  const innerHeight = height - plot.top - plot.bottom;
  const maxCount = Math.max(...bins.map((item) => item.count), 1);
  const minValue = finiteNumber(distribution.min) ?? Math.min(...bins.map((item) => item.lower));
  const maxValue = finiteNumber(distribution.max) ?? Math.max(...bins.map((item) => item.upper));
  const span = maxValue - minValue || 1;
  const scaleX = (value) => plot.left + ((value - minValue) / span) * innerWidth;
  const scaleY = (count) => plot.top + innerHeight - (count / maxCount) * innerHeight;
  const axisTicks = uniqueNumbers([minValue, finiteNumber(distribution.median), maxValue]);
  const visibleMarkers = markers.filter((marker) => marker.value >= minValue && marker.value <= maxValue);

  return (
    <div className="expression-histogram-wrap">
      <svg className="expression-histogram" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Expression histogram with cutpoint markers">
        {[0, 0.5, 1].map((fraction) => {
          const y = plot.top + innerHeight - fraction * innerHeight;
          return <line key={fraction} className="histogram-grid-line" x1={plot.left} x2={width - plot.right} y1={y} y2={y} />;
        })}
        {bins.map((bin, index) => {
          const singleValue = bin.lower === bin.upper || minValue === maxValue;
          const x = singleValue ? plot.left + innerWidth * 0.16 : scaleX(bin.lower);
          const nextX = singleValue ? plot.left + innerWidth * 0.84 : scaleX(bin.upper);
          const barWidth = Math.max(3, nextX - x - 4);
          const y = scaleY(bin.count);
          const barHeight = plot.top + innerHeight - y;
          return (
            <rect
              key={`${bin.label}-${index}`}
              className="histogram-bar"
              x={x}
              y={y}
              width={barWidth}
              height={barHeight}
              rx="3"
            >
              <title>{`${bin.label}: ${formatInteger(bin.count)} patients`}</title>
            </rect>
          );
        })}
        {visibleMarkers.map((marker, index) => {
          const x = scaleX(marker.value);
          return (
            <g key={`${marker.label}-${marker.value}`} className={`cutpoint-marker marker-${index % 3}`}>
              <line x1={x} x2={x} y1={plot.top - 6} y2={plot.top + innerHeight} />
              <text x={x} y={index % 2 === 0 ? 14 : 28}>{marker.label}</text>
            </g>
          );
        })}
        <line className="histogram-axis" x1={plot.left} x2={width - plot.right} y1={plot.top + innerHeight} y2={plot.top + innerHeight} />
        {axisTicks.map((tick) => {
          const x = scaleX(tick);
          return (
            <g key={tick} className="histogram-tick">
              <line x1={x} x2={x} y1={plot.top + innerHeight} y2={plot.top + innerHeight + 5} />
              <text x={x} y={height - 16}>{formatExpressionValue(tick)}</text>
            </g>
          );
        })}
        <text className="histogram-y-label" x="12" y={plot.top + 10}>Patients</text>
      </svg>
      {!!visibleMarkers.length && (
        <div className="expression-marker-legend">
          {visibleMarkers.map((marker, index) => (
            <span key={`${marker.label}-${marker.value}`}>
              <i className={`marker-${index % 3}`} />
              {marker.label}: {formatExpressionValue(marker.value)}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

function normalizeDistributionBins(items) {
  return items.map((item, index) => {
    const label = String(item.label ?? "");
    const parsed = parseDistributionLabel(label);
    const lower = finiteNumber(item.lower) ?? parsed.lower ?? index;
    const upper = finiteNumber(item.upper) ?? parsed.upper ?? lower;
    return {
      label,
      count: Number(item.count || 0),
      lower,
      upper,
    };
  });
}

function parseDistributionLabel(label) {
  const range = label.match(/^\s*(-?\d+(?:\.\d+)?)\s*-\s*(-?\d+(?:\.\d+)?)\s*$/);
  if (range) {
    return { lower: Number(range[1]), upper: Number(range[2]) };
  }
  const single = label.match(/^\s*(-?\d+(?:\.\d+)?)\s*$/);
  if (single) {
    const value = Number(single[1]);
    return { lower: value, upper: value };
  }
  return {};
}

function cutpointMarkers(details) {
  if (!details) return [];
  return [
    ["threshold", "Cutpoint"],
    ["lower_quartile", "Lower quartile"],
    ["upper_quartile", "Upper quartile"],
    ["lower_tertile", "Lower tertile"],
    ["upper_tertile", "Upper tertile"],
  ]
    .map(([key, label]) => ({ label, value: finiteNumber(details[key]) }))
    .filter((marker) => marker.value !== null);
}

function signatureCutpointDetails(details, prefix) {
  if (!details || !prefix) return null;
  const scoped = {};
  [
    "threshold",
    "lower_tertile",
    "upper_tertile",
    "lower_quartile",
    "upper_quartile",
  ].forEach((key) => {
    const value = details[`${prefix}_${key}`];
    if (value !== undefined && value !== null) {
      scoped[key] = value;
    }
  });
  return Object.keys(scoped).length ? scoped : null;
}

function finiteNumber(value) {
  return scientificNumber(value);
}

function pancancerCompletedRows(rows) {
  return (rows || []).filter((row) => row.status === "completed" && finiteNumber(row.hazard_ratio) !== null);
}

function forestDiamondPoints(scaleX, row, y) {
  const low = finiteNumber(row.hr_conf_low);
  const mid = finiteNumber(row.hazard_ratio);
  const high = finiteNumber(row.hr_conf_high);
  if (low === null || mid === null || high === null) return "";
  return `${scaleX(low)},${y} ${scaleX(mid)},${y - 8} ${scaleX(high)},${y} ${scaleX(mid)},${y + 8}`;
}

function evidenceLabels(points) {
  const significant = points
    .filter((point) => point.row.significant)
    .sort((a, b) => b.y - a.y)
    .slice(0, 8);
  if (significant.length) return significant;
  return [...points].sort((a, b) => b.y - a.y).slice(0, 3);
}

function powerPrecisionLabels(points) {
  const significant = points
    .filter((point) => point.row.significant)
    .sort((a, b) => b.precision - a.precision)
    .slice(0, 8);
  if (significant.length) return significant;
  return [...points].sort((a, b) => b.events - a.events).slice(0, 3);
}

function niceTicks(maxValue, count = 4) {
  const number = Number(maxValue);
  if (!Number.isFinite(number) || number <= 0) return [0];
  const rawStep = number / Math.max(count, 1);
  const magnitude = 10 ** Math.floor(Math.log10(rawStep));
  const residual = rawStep / magnitude;
  const step =
    residual > 5
      ? 10 * magnitude
      : residual > 2
        ? 5 * magnitude
        : residual > 1
          ? 2 * magnitude
          : magnitude;
  const ticks = [];
  for (let tick = 0; tick <= number + step * 0.5; tick += step) {
    ticks.push(Number(tick.toFixed(6)));
  }
  return uniqueNumbers(ticks);
}

function enrichConcordanceRow(row) {
  const hazardRatio = finiteNumber(row.hazard_ratio);
  const logHr = finiteNumber(row.log_hr) ?? (hazardRatio ? Math.log(hazardRatio) : null);
  const fdr = finiteNumber(row.fdr);
  const pValue = finiteNumber(row.p_value);
  const evidenceValue = fdr ?? pValue;
  const evidenceScore = evidenceValue ? -Math.log10(Math.max(evidenceValue, 1e-300)) : 0;
  const nPatients = finiteNumber(row.n_patients);
  const nEvents = finiteNumber(row.n_events);
  const standardError = finiteNumber(row.standard_error);
  const precision = standardError ? 1 / standardError : null;
  const phPValue = finiteNumber(row.ph_p_value);
  const eventRate = nPatients ? nEvents / nPatients : null;
  const direction = row.direction || (hazardRatio > 1 ? "harmful" : hazardRatio < 1 ? "protective" : "neutral");
  const glyphPosition = logHr === null ? 50 : 50 + Math.max(-1, Math.min(1, logHr / Math.log(4))) * 42;
  const glyphSize = 12 + Math.min(12, Math.sqrt(Math.max(nEvents || 0, 0)) / 2.6);
  const qcFlag = row.status !== "completed" || (phPValue !== null && phPValue < 0.05);
  return {
    ...row,
    hazardRatio,
    logHr,
    log2Hr: logHr === null ? null : logHr / Math.log(2),
    fdr,
    pValue,
    evidenceScore,
    evidenceRatio: Math.min(1, evidenceScore / 3),
    evidenceDegrees: Math.min(1, evidenceScore / 3) * 360,
    nPatients,
    nEvents,
    standardError,
    precision,
    phPValue,
    qcFlag,
    eventRate,
    eventRateRatio: Math.min(1, eventRate || 0),
    glyphPosition,
    glyphSize,
    direction,
    shortCode: String(row.cohort || "").replace("TCGA-", ""),
    effectClass: row.status === "completed" ? row.effect_category || direction || "neutral" : "not_evaluable",
    concordanceClass: row.concordance || "not_evaluable",
  };
}

function concordanceFilterCounts(rows) {
  return {
    all: rows.length,
    hits: rows.filter((row) => row.significant).length,
    same: rows.filter((row) => row.concordance === "reference" || String(row.concordance || "").startsWith("same_direction")).length,
    opposite: rows.filter((row) => String(row.concordance || "").startsWith("opposite_direction")).length,
    qc: rows.filter((row) => row.status !== "completed" || (row.phPValue !== null && row.phPValue < 0.05)).length,
  };
}

function filterConcordanceRows(rows, filter, query) {
  const normalizedQuery = String(query || "").trim().toLowerCase();
  return rows.filter((row) => {
    const matchesFilter =
      filter === "hits"
        ? row.significant
        : filter === "same"
          ? row.concordance === "reference" || String(row.concordance || "").startsWith("same_direction")
          : filter === "opposite"
            ? String(row.concordance || "").startsWith("opposite_direction")
            : filter === "qc"
              ? row.status !== "completed" || (row.phPValue !== null && row.phPValue < 0.05)
              : true;
    if (!matchesFilter) return false;
    if (!normalizedQuery) return true;
    return [row.cohort, row.shortCode, getCohortName(row.cohort), row.primary_site, row.endpoint, row.endpoint_source]
      .filter(Boolean)
      .some((value) => String(value).toLowerCase().includes(normalizedQuery));
  });
}

function sortConcordanceRows(rows, sortMode) {
  const sorted = [...rows];
  const missingLast = (value) => (value === null || value === undefined ? Number.NEGATIVE_INFINITY : value);
  if (sortMode === "effect") {
    return sorted.sort((a, b) => Math.abs(missingLast(b.log2Hr)) - Math.abs(missingLast(a.log2Hr)) || String(a.cohort).localeCompare(String(b.cohort)));
  }
  if (sortMode === "precision") {
    return sorted.sort((a, b) => missingLast(b.precision) - missingLast(a.precision) || String(a.cohort).localeCompare(String(b.cohort)));
  }
  if (sortMode === "events") {
    return sorted.sort((a, b) => missingLast(b.nEvents) - missingLast(a.nEvents) || String(a.cohort).localeCompare(String(b.cohort)));
  }
  if (sortMode === "cohort") {
    return sorted.sort((a, b) => String(a.cohort).localeCompare(String(b.cohort)));
  }
  return sorted.sort((a, b) => {
    const aFdr = a.fdr ?? Number.POSITIVE_INFINITY;
    const bFdr = b.fdr ?? Number.POSITIVE_INFINITY;
    return aFdr - bFdr || Math.abs(missingLast(b.log2Hr)) - Math.abs(missingLast(a.log2Hr)) || String(a.cohort).localeCompare(String(b.cohort));
  });
}

function formatDirectionToken(row) {
  if (!row || row.status !== "completed") return "Not evaluable";
  if (row.hazardRatio > 1) return "HR > 1";
  if (row.hazardRatio < 1) return "HR < 1";
  return "HR = 1";
}

function formatCompactNumber(value) {
  const number = scientificNumber(value);
  if (number === null) return "...";
  if (Math.abs(number) < 0.01 && number !== 0) return number.toExponential(1);
  return number.toFixed(2);
}

function formatSignedNumber(value, digits = 1) {
  const number = scientificNumber(value);
  if (number === null) return "...";
  const absolute = Math.abs(number).toFixed(digits);
  if (number > 0) return `+${absolute}`;
  if (number < 0) return `-${absolute}`;
  return Number(absolute).toFixed(digits);
}

function concordanceInterpretation(row, referenceRow, fdrThreshold) {
  if (row.status !== "completed") {
    return {
      title: "Not evaluable in this scan",
      body: row.reason || row.code || "This cohort did not pass endpoint, gene, patient-count or event-count requirements.",
    };
  }
  const direction = row.hazardRatio > 1 ? "higher hazard" : row.hazardRatio < 1 ? "lower hazard" : "no directional effect";
  const fdrHit = row.fdr !== null && fdrThreshold !== null && row.fdr <= Number(fdrThreshold);
  const sameDirection = row.concordance === "reference" || String(row.concordance || "").startsWith("same_direction");
  const oppositeDirection = String(row.concordance || "").startsWith("opposite_direction");
  const caveats = [];
  if (row.phPValue !== null && row.phPValue < 0.05) caveats.push("PH test is flagged; inspect time-varying effects before treating the Cox HR as stable.");
  if (row.nEvents !== null && row.nEvents < 20) caveats.push("Event count is low, so the confidence interval may be unstable.");
  if (row.standardError !== null && row.standardError > 0.25) caveats.push("The Cox standard error is wide relative to stronger cohorts.");

  if (!referenceRow) {
    return {
      title: fdrHit ? "FDR-significant cohort effect" : "Direction without index concordance",
      body: `Expression is associated with ${direction}; the selected index cancer was not evaluable, so same/opposite-direction labels should not drive interpretation.${caveats.length ? ` ${caveats.join(" ")}` : ""}`,
    };
  }
  if (row.concordance === "reference") {
    return {
      title: "Index cancer reference",
      body: `This cohort defines the concordance direction for the scan. Expression is associated with ${direction}${fdrHit ? " and passes the selected FDR threshold" : " but does not pass the selected FDR threshold"}.${caveats.length ? ` ${caveats.join(" ")}` : ""}`,
    };
  }
  if (fdrHit && sameDirection) {
    return {
      title: "Concordant FDR hit",
      body: `This is the strongest cross-cancer support pattern: same direction as the index cancer and FDR <= ${formatP(fdrThreshold)}. Expression is associated with ${direction}.${caveats.length ? ` ${caveats.join(" ")}` : ""}`,
    };
  }
  if (fdrHit && oppositeDirection) {
    return {
      title: "Discordant FDR hit",
      body: `This cohort is statistically strong but directionally opposite to the index cancer. Treat it as biology worth follow-up, not noise. Expression is associated with ${direction}.${caveats.length ? ` ${caveats.join(" ")}` : ""}`,
    };
  }
  if (sameDirection) {
    return {
      title: "Directional concordance only",
      body: `The HR direction matches the index cancer, but this cohort is not an FDR hit. Use it as weak directional support, especially if events or precision are limited.${caveats.length ? ` ${caveats.join(" ")}` : ""}`,
    };
  }
  if (oppositeDirection) {
    return {
      title: "Opposite direction without FDR support",
      body: `The HR direction differs from the index cancer but does not pass FDR. This may reflect tissue context, endpoint noise or limited precision.${caveats.length ? ` ${caveats.join(" ")}` : ""}`,
    };
  }
  return {
    title: "No interpretable concordance label",
    body: `The cohort completed, but concordance is unavailable for this row.${caveats.length ? ` ${caveats.join(" ")}` : ""}`,
  };
}

function uniqueNumbers(values) {
  const seen = new Set();
  return values
    .filter((value) => value !== null && value !== undefined)
    .filter((value) => {
      const key = Number(value).toFixed(6);
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
}

function QualitySummary({ quality }) {
  if (!quality?.groups) return null;
  return (
    <div className="detail-section">
      <h3>Event quality</h3>
      <table aria-label="Input gene quality summary">
        <thead>
          <tr>
            <th scope="col">Group</th>
            <th scope="col">Patients</th>
            <th scope="col">Events</th>
          </tr>
        </thead>
        <tbody>
          {Object.entries(quality.groups).map(([group, item]) => (
            <tr key={group}>
              <td>{group}</td>
              <td>{item.patients}</td>
              <td>{item.events}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {!!quality.low_event_groups?.length && (
        <div className="method-note caution">Low event count in: {quality.low_event_groups.join(", ")}.</div>
      )}
    </div>
  );
}

function ResultDownloads({
  downloads = {},
  onDownload,
  primaryPlotLabel = "KM",
  guideAnchor = false,
}) {
  const hasSeparateCoxDownloads = Boolean(
    downloads.cox_univariable_png || downloads.cox_multivariable_png,
  );
  const coxDownloadUrls = hasSeparateCoxDownloads
    ? [
        downloads.cox_univariable_png,
        downloads.cox_univariable_svg,
        downloads.cox_multivariable_png,
        downloads.cox_multivariable_svg,
      ]
    : [downloads.cox_png, downloads.cox_svg];
  const downloadCount = [
    downloads.png,
    downloads.svg,
    ...coxDownloadUrls,
    downloads.continuous_png,
    downloads.continuous_svg,
    downloads.cumulative_incidence_png,
    downloads.cumulative_incidence_svg,
    downloads.signature_panel_joint_png,
    downloads.signature_panel_joint_svg,
    downloads.signature_panel_adjusted_png,
    downloads.signature_panel_adjusted_svg,
    downloads.continuous_csv,
    downloads.model_results_csv,
    downloads.score_correlations_csv,
    downloads.csv,
    downloads.json,
    downloads.txt,
    downloads.audit_json,
    downloads.audit_html,
    downloads.attestation,
    downloads.r_script,
    downloads.reproduction_manifest,
    downloads.zip,
  ].filter(Boolean).length;
  if (!downloadCount) return null;
  const DownloadsDisclosure = guideAnchor ? GuideAnchor : "details";

  return (
    <DownloadsDisclosure
      {...(guideAnchor
        ? {
            as: "details",
            anchor: GUIDE_ANCHORS.SURVIVAL_DOWNLOADS,
            label: "Survival result exports",
          }
        : {})}
      className="result-downloads"
    >
      <summary>
        <TraceIcon role="action.download" size="sm" />
        <span>Exports</span>
        <b>{downloadCount}</b>
        <TraceIcon role="action.expand" size="sm" className="result-download-chevron" />
      </summary>
      <div className="result-download-groups">
        <div>
          <strong>Plots</strong>
          <div className="download-row">
            <DownloadLink href={downloads.png} iconRole="file.image" label={`${primaryPlotLabel} PNG`} onDownload={onDownload} />
            <DownloadLink href={downloads.svg} iconRole="action.download" label={`${primaryPlotLabel} SVG`} onDownload={onDownload} />
            {hasSeparateCoxDownloads ? (
              <>
                <DownloadLink href={downloads.cox_univariable_png} iconRole="data.expression" label="Univariable Cox PNG" onDownload={onDownload} />
                <DownloadLink href={downloads.cox_univariable_svg} iconRole="action.download" label="Univariable Cox SVG" onDownload={onDownload} />
                <DownloadLink href={downloads.cox_multivariable_png} iconRole="data.expression" label="Multivariable Cox PNG" onDownload={onDownload} />
                <DownloadLink href={downloads.cox_multivariable_svg} iconRole="action.download" label="Multivariable Cox SVG" onDownload={onDownload} />
              </>
            ) : (
              <>
                <DownloadLink href={downloads.cox_png} iconRole="data.expression" label="Cox PNG" onDownload={onDownload} />
                <DownloadLink href={downloads.cox_svg} iconRole="action.download" label="Cox SVG" onDownload={onDownload} />
              </>
            )}
            <DownloadLink href={downloads.continuous_png} iconRole="data.expression" label="Continuous PNG" onDownload={onDownload} />
            <DownloadLink href={downloads.continuous_svg} iconRole="action.download" label="Continuous SVG" onDownload={onDownload} />
            <DownloadLink href={downloads.cumulative_incidence_png} iconRole="file.image" label="CIF PNG" onDownload={onDownload} />
            <DownloadLink href={downloads.cumulative_incidence_svg} iconRole="action.download" label="CIF SVG" onDownload={onDownload} />
            <DownloadLink href={downloads.signature_panel_joint_png} iconRole="data.expression" label="Joint Cox PNG" onDownload={onDownload} />
            <DownloadLink href={downloads.signature_panel_joint_svg} iconRole="action.download" label="Joint Cox SVG" onDownload={onDownload} />
            <DownloadLink href={downloads.signature_panel_adjusted_png} iconRole="data.expression" label="Adjusted panel PNG" onDownload={onDownload} />
            <DownloadLink href={downloads.signature_panel_adjusted_svg} iconRole="action.download" label="Adjusted panel SVG" onDownload={onDownload} />
          </div>
        </div>
        <div>
          <strong>Data</strong>
          <div className="download-row">
            <DownloadLink href={downloads.csv} iconRole="file.csv" label="Patient CSV" onDownload={onDownload} />
            <DownloadLink href={downloads.continuous_csv} iconRole="file.csv" label="Continuous CSV" onDownload={onDownload} />
            <DownloadLink href={downloads.model_results_csv} iconRole="file.csv" label="Model results CSV" onDownload={onDownload} />
            <DownloadLink href={downloads.score_correlations_csv} iconRole="file.csv" label="Correlations CSV" onDownload={onDownload} />
            <DownloadLink href={downloads.json} iconRole="file.text" label="Metrics JSON" onDownload={onDownload} />
          </div>
        </div>
        <div>
          <strong>Methods</strong>
          <div className="download-row">
            <DownloadLink href={downloads.txt} iconRole="file.text" label="Method TXT" onDownload={onDownload} />
          </div>
        </div>
        <div>
          <strong>Analysis report and reproduction</strong>
          <div className="download-row">
            <DownloadLink href={downloads.audit_json} iconRole="file.audit" label="Audit JSON" onDownload={onDownload} />
            <DownloadLink href={downloads.cohort_manifest} iconRole="file.csv" label="Cohort decisions CSV" onDownload={onDownload} />
            <DownloadLink href={downloads.source_files} iconRole="file.csv" label="Source files CSV" onDownload={onDownload} />
            <DownloadLink href={downloads.audit_html} iconRole="file.audit" label="Analysis report" onDownload={onDownload} />
            <DownloadLink href={downloads.attestation} iconRole="file.audit" label="Signed receipt" onDownload={onDownload} />
            <DownloadLink href={downloads.r_script} iconRole="file.text" label="R rerun" onDownload={onDownload} />
            <DownloadLink href={downloads.reproduction_manifest} iconRole="file.audit" label="R manifest" onDownload={onDownload} />
            <DownloadLink href={downloads.zip} iconRole="file.archive" label="Bundle ZIP" onDownload={onDownload} />
          </div>
        </div>
      </div>
    </DownloadsDisclosure>
  );
}

function DownloadLink({ href, iconRole, label, onDownload }) {
  if (!href) return null;
  return (
    <button type="button" onClick={() => onDownload?.(href, label)} title={`Download ${label}`}>
      <TraceIcon role={iconRole} size="sm" />
      {label}
    </button>
  );
}

function PlotDownloadButtons({ svgSelector, filenameBase, onPlotDownload }) {
  if (!onPlotDownload) return null;
  return (
    <div className="plot-download-row compact">
      <span>Download plot</span>
      <div className="download-row">
        <button type="button" onClick={() => onPlotDownload(svgSelector, filenameBase, "png")}>
          <TraceIcon role="file.image" size="sm" />
          PNG
        </button>
        <button type="button" onClick={() => onPlotDownload(svgSelector, filenameBase, "svg")}>
          <TraceIcon role="action.download" size="sm" />
          SVG
        </button>
      </div>
    </div>
  );
}

function MiniDownloadButton({ href, label, onDownload }) {
  if (!href) return null;
  return (
    <button type="button" onClick={() => onDownload?.(href, label)} title={`Download ${label}`}>
      {label}
    </button>
  );
}

function DownloadNotifications({ notices, onDismiss }) {
  if (!notices.length) return null;
  return (
    <div className="download-notifications" aria-live="polite" aria-label="Download status">
      {notices.map((notice) => (
        <div key={notice.id} className={`download-notice ${notice.status}`}>
          {notice.status === "running" && <TraceIcon role="status.loading" size="sm" className="spin" />}
          {notice.status === "done" && <TraceIcon role="status.success" size="sm" tone="success" />}
          {notice.status === "failed" && <TraceIcon role="status.error" size="sm" tone="error" />}
          <div>
            <strong>{notice.label}</strong>
            <span>{notice.message}</span>
          </div>
          <IconButton
            iconRole="action.close"
            label={`Dismiss ${notice.label} download status`}
            tooltip={`Dismiss ${notice.label} download status`}
            iconSize="xsm"
            size="sm"
            onClick={() => onDismiss(notice.id)}
          />
        </div>
      ))}
    </div>
  );
}

function formatP(value) {
  const number = scientificNumber(value);
  if (number === null || number < 0 || number > 1) return "...";
  if (number < 0.001) return number.toExponential(2);
  return number.toFixed(3);
}

function formatHr(metrics) {
  return scientificEstimate(metrics?.hazard_ratio, metrics?.hr_conf_low, metrics?.hr_conf_high);
}

function formatHrValues(row) {
  return scientificEstimate(row?.hazard_ratio, row?.hr_conf_low, row?.hr_conf_high);
}

function formatShrValues(row) {
  return scientificEstimate(row?.subdistribution_hazard_ratio, row?.shr_conf_low, row?.shr_conf_high);
}

function formatCif(value) {
  const number = scientificNumber(value);
  if (number === null || number < 0 || number > 1) return "...";
  return `${(100 * number).toFixed(1)}%`;
}

function formatCifInterval(estimate) {
  const low = scientificNumber(estimate?.conf_low);
  const high = scientificNumber(estimate?.conf_high);
  if (low === null || high === null) return "...";
  return `${formatCif(low)}-${formatCif(high)}`;
}

function formatHorizonYears(horizon) {
  const years = scientificNumber(horizon?.time_years);
  if (years === null) return "...";
  const digits = Math.abs(years - Math.round(years)) < 0.001 ? 0 : 1;
  return `${years.toFixed(digits)} y`;
}

function formatFineGrayModelLabel(model) {
  const labels = {
    fine_gray_grouped_univariable: "Unadjusted",
    fine_gray_grouped_user_adjusted: "User-adjusted",
    fine_gray_grouped_stage_adjusted: "Stage",
    fine_gray_grouped_grade_adjusted: "Grade",
    fine_gray_grouped_stage_grade_adjusted: "Stage + grade",
    fine_gray_continuous_univariable: "Unadjusted",
    fine_gray_continuous_user_adjusted: "User-adjusted",
    fine_gray_continuous_stage_adjusted: "Stage",
    fine_gray_continuous_grade_adjusted: "Grade",
    fine_gray_continuous_stage_grade_adjusted: "Stage + grade",
  };
  return labels[model?.model] || model?.label || formatLabel(model?.model);
}

function fineGrayInformationClass(value) {
  const number = scientificNumber(value);
  if (number === null) return "";
  if (number < 5) return "cox-information-cell severe";
  if (number < 10) return "cox-information-cell caution";
  return "cox-information-cell";
}

function formatFineGrayInformation(model) {
  const eventsPerParameter = scientificNumber(model?.events_per_parameter);
  const parameterCount = scientificNumber(model?.parameter_count);
  if (eventsPerParameter === null || parameterCount === null) {
    return "...";
  }
  const label = eventsPerParameter < 5
    ? "severe"
    : eventsPerParameter < 10
      ? "caution"
      : "adequate";
  return `${eventsPerParameter.toFixed(1)} · ${formatInteger(parameterCount)} parameter${parameterCount === 1 ? "" : "s"} · ${label}`;
}

function formatTemporalHrRatio(change) {
  return scientificEstimate(change?.hazard_ratio_ratio, change?.hr_ratio_conf_low, change?.hr_ratio_conf_high);
}

function formatPredictionInterval(interval) {
  const low = scientificNumber(interval?.hazard_ratio_low);
  const high = scientificNumber(interval?.hazard_ratio_high);
  if (low === null || high === null) return "Not available";
  return `${low.toFixed(2)}-${high.toFixed(2)}`;
}

function paperMethodDiagnostics(method) {
  const prefix = method?.adjusted_model ? "adjusted" : "univariable";
  return {
    eventsPerParameter: method?.[`${prefix}_events_per_parameter`],
    informationStatus: method?.[`${prefix}_information_status`],
    firthStatus: method?.[`${prefix}_firth_status`],
    firthHr: method?.[`${prefix}_firth_hr`],
    firthHrConfLow: method?.[`${prefix}_firth_hr_conf_low`],
    firthHrConfHigh: method?.[`${prefix}_firth_hr_conf_high`],
    firthPValue: method?.[`${prefix}_firth_p_value`],
  };
}

function formatSparseModelInformation(eventsPerParameter, status) {
  const value = toNullableNumber(eventsPerParameter);
  if (value === null) return "...";
  const label = {
    adequate: "adequate",
    caution: "caution",
    severe: "severe caution",
  }[status] || "not evaluable";
  return `${value.toFixed(1)} · ${label}`;
}

function formatPaperFirthSensitivity(diagnostic) {
  if (diagnostic?.firthStatus === "not_triggered") return "Not triggered";
  if (diagnostic?.firthStatus === "failed") return "Failed";
  if (diagnostic?.firthStatus !== "completed") return "...";
  const hr = toNullableNumber(diagnostic.firthHr);
  const low = toNullableNumber(diagnostic.firthHrConfLow);
  const high = toNullableNumber(diagnostic.firthHrConfHigh);
  const effect = [hr, low, high].every((value) => value !== null)
    ? `${formatCompactNumber(hr)} (${formatCompactNumber(low)}–${formatCompactNumber(high)})`
    : "Completed";
  return `${effect} · p ${formatP(diagnostic.firthPValue)}`;
}

function formatAdjustedHrValues(row) {
  return scientificEstimate(row?.adjusted_hazard_ratio, row?.adjusted_hr_conf_low, row?.adjusted_hr_conf_high);
}

function formatAdjustmentModel(value) {
  return {
    user_adjusted: "User-selected",
    stage_grade_adjusted: "Stage + grade",
    stage_adjusted: "Stage",
    grade_adjusted: "Grade",
  }[value] || "Not evaluable";
}

function formatClinicalSensitivity(value) {
  return {
    retained: "Retained after adjustment",
    attenuated: "Attenuated after adjustment",
    emerged: "Emerged after adjustment",
    direction_consistent: "Direction consistent",
    reversed: "Direction reversed",
    not_evaluable: "Adjustment not evaluable",
  }[value] || formatLabel(String(value || "Not evaluable"));
}

function formatCoxCovariates(value) {
  if (!value?.length) return "None";
  const labels = {
    age_at_index_per_10y: "Age / 10 years",
    stage_ordinal: "Stage (ordinal)",
    grade_ordinal: "Grade (ordinal)",
    gender_factor: "GDC gender",
    race_factor: "GDC race",
  };
  return value.map((item) => labels[item] || formatLabel(item)).join(", ");
}

function formatCoxModelLabel(model) {
  const labels = {
    univariable: "Unadjusted",
    user_adjusted: "User-adjusted",
    stage_adjusted: "Stage",
    grade_adjusted: "Grade",
    stage_grade_adjusted: "Stage + grade",
  };
  return labels[model?.model] || model?.label || formatLabel(model?.model);
}

function formatContinuousModelLabel(model) {
  const labels = {
    continuous_univariable: "Unadjusted",
    continuous_user_adjusted: "User-adjusted",
    continuous_stage_adjusted: "Stage",
    continuous_grade_adjusted: "Grade",
    continuous_stage_grade_adjusted: "Stage + grade",
  };
  return labels[model?.model] || model?.label || formatLabel(model?.model);
}

function formatModelStatus(model) {
  if (model?.status === "completed") return "Completed";
  const reason = String(model?.reason || "").toLowerCase();
  if (reason.includes("fewer than 10 complete patients")) return "Too few cases";
  if (reason.includes("no events")) return "No events";
  if (reason.includes("fewer than two levels") || reason.includes("fewer than two observed scores")) return "Covariate has one level";
  if (reason.includes("two expression groups")) return "Needs two groups";
  if (reason.includes("finite hr confidence intervals")) return "Non-finite CI";
  return model?.reason || formatLabel(model?.status);
}

function findCoxModel(models, modelId) {
  return (models || []).find((model) => model.model === modelId && model.status === "completed") || null;
}

function downstreamAdjustedModel(models) {
  return (
    findCoxModel(models, "user_adjusted") ||
    findCoxModel(models, "stage_grade_adjusted") ||
    findCoxModel(models, "stage_adjusted") ||
    findCoxModel(models, "grade_adjusted")
  );
}

function downstreamAdjustedContinuousModel(models) {
  return (
    findCoxModel(models, "continuous_user_adjusted") ||
    findCoxModel(models, "continuous_stage_grade_adjusted") ||
    findCoxModel(models, "continuous_stage_adjusted") ||
    findCoxModel(models, "continuous_grade_adjusted")
  );
}

function downstreamAdjustedInteractionModel(models) {
  return (
    findCoxModel(models, "signature_interaction_user_adjusted") ||
    findCoxModel(models, "signature_interaction_stage_grade_adjusted") ||
    findCoxModel(models, "signature_interaction_stage_adjusted") ||
    findCoxModel(models, "signature_interaction_grade_adjusted")
  );
}

function cutpointEvidenceProfile(row) {
  const metrics = row.result?.metrics || {};
  const univariable = findCoxModel(metrics.cox_models, "univariable");
  const requested = requestedAdjustedModel(metrics.cox_models, "", row.adjustmentRequested);
  const adjusted = requested?.status === "completed" ? requested : null;
  const diagnosticModel = requested ? adjusted : univariable;
  const bhValue = toNullableNumber(row.bh);
  const bhEvaluable = bhValue !== null;
  const bhBelowAlpha = bhEvaluable && bhValue <= ROBUSTNESS_ALPHA;
  const markerPhValue = toNullableNumber(diagnosticModel?.ph_p_value);
  const markerPhEvaluable = markerPhValue !== null;
  const markerPhFlagged = markerPhEvaluable && markerPhValue < ROBUSTNESS_ALPHA;
  const globalPhValue = toNullableNumber(diagnosticModel?.ph_global_p_value);
  const globalPhEvaluable = globalPhValue !== null;
  const globalPhFlagged = globalPhEvaluable && globalPhValue < ROBUSTNESS_ALPHA;
  const temporalEffect = diagnosticModel?.time_varying_effect || {};
  const temporalStatus = temporalEffect.status || null;
  const temporalTriggered = ["completed", "skipped", "failed"].includes(temporalStatus);
  const rmstAvailable = metrics.rmst?.status === "completed"
    && toNullableNumber(metrics.rmst?.difference?.estimate_days) !== null;
  const hr = toNullableNumber(univariable?.hazard_ratio);
  const direction = hr !== null ? (hr < 1 ? "Lower hazard" : hr > 1 ? "Higher hazard" : "HR = 1") : "...";
  const interpretationNotes = [];
  if (requested && !adjusted) interpretationNotes.push(`Requested adjustment not estimable: ${formatModelStatus(requested)}`);
  interpretationNotes.push(requested ? "Diagnostics refer to the requested adjustment" : "Diagnostics refer to the unadjusted model");
  if (!rmstAvailable) interpretationNotes.push("RMST not evaluable");
  if (markerPhFlagged) {
    interpretationNotes.push(
      temporalStatus === "completed"
        ? "Marker-specific PH caution; fixed 2-year diagnostic estimated"
        : temporalTriggered
          ? `Marker-specific PH caution; 2-year diagnostic ${formatLabel(temporalStatus)}`
          : "Marker-specific PH caution"
    );
  } else if (globalPhFlagged) {
    interpretationNotes.push("Global PH caution may arise from another model term");
  }
  if (row.method === "maxstat") {
    interpretationNotes.push("Outcome-optimized cutpoint; grouped estimates are post-selection");
  }
  if (row.method === "upper_lower_quartile") {
    interpretationNotes.push("Middle 50% excluded, reducing effective sample size");
  }
  const bhLabel = !bhEvaluable
    ? "BH q unavailable"
    : bhBelowAlpha
      ? `BH q ≤ ${ROBUSTNESS_ALPHA}`
      : `BH q > ${ROBUSTNESS_ALPHA}`;
  return {
    bhEvaluable,
    bhBelowAlpha,
    bhLabel,
    bhTone: bhBelowAlpha ? "informative" : "neutral",
    markerPhEvaluable,
    markerPhFlagged,
    globalPhEvaluable,
    globalPhFlagged,
    temporalEffect,
    temporalStatus,
    temporalTriggered,
    rmstAvailable,
    direction,
    interpretationNotes,
  };
}

function formatGroupCounts(groupCounts) {
  const entries = Object.entries(groupCounts || {});
  if (!entries.length) return "...";
  return entries
    .map(([group, count]) => `${formatLabel(group)} ${formatInteger(count)}`)
    .join(" · ");
}

function formatPercent(value) {
  const number = scientificNumber(value);
  if (number === null) return "...";
  return `${number.toFixed(0)}%`;
}

function formatEffectLabel(value) {
  return {
    harmful: "Higher expression worse",
    protective: "Higher expression better",
    neutral: "Not FDR-significant",
    not_evaluable: "Not evaluable",
  }[value] || formatLabel(String(value || "..."));
}

function formatConcordance(value) {
  return {
    reference: "Index cancer",
    same_direction_significant: "Same direction / FDR hit",
    same_direction_not_significant: "Same direction",
    opposite_direction_significant: "Opposite / FDR hit",
    opposite_direction_not_significant: "Opposite direction",
    reference_unavailable: "No index effect",
    not_evaluable: "Not evaluable",
  }[value] || formatLabel(String(value || "..."));
}

function shortEffectLabel(row) {
  if (row.status !== "completed") return row.status === "failed" ? "Fail" : "Skip";
  if (row.effect_category === "harmful") return "Worse";
  if (row.effect_category === "protective") return "Better";
  return row.direction === "harmful" ? "HR > 1" : row.direction === "protective" ? "HR < 1" : "Neutral";
}

function panCancerRowTooltip(row) {
  if (row.status !== "completed") return row.reason || row.code || row.status;
  return `${formatHrValues(row)}, FDR ${formatP(row.fdr)}, ${formatConcordance(row.concordance)}`;
}

async function downloadSvgPlot(svgSelector, filename, format) {
  const svg = document.querySelector(svgSelector);
  if (!svg) throw new Error("Plot is not available.");
  const serialized = serializeSvgForDownload(svg);
  if (format === "svg") {
    downloadBlob(new Blob([serialized], { type: "image/svg+xml;charset=utf-8" }), filename);
    return;
  }
  if (format !== "png") {
    throw new Error("Unsupported plot format.");
  }
  const { width, height } = svgDimensions(svg);
  const scale = 2;
  const blob = new Blob([serialized], { type: "image/svg+xml;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  try {
    const image = await loadImage(url);
    const canvas = document.createElement("canvas");
    canvas.width = Math.max(1, Math.round(width * scale));
    canvas.height = Math.max(1, Math.round(height * scale));
    const context = canvas.getContext("2d");
    context.fillStyle = "#ffffff";
    context.fillRect(0, 0, canvas.width, canvas.height);
    context.drawImage(image, 0, 0, canvas.width, canvas.height);
    const pngBlob = await new Promise((resolve, reject) => {
      canvas.toBlob((result) => (result ? resolve(result) : reject(new Error("PNG rendering failed."))), "image/png");
    });
    downloadBlob(pngBlob, filename);
  } finally {
    URL.revokeObjectURL(url);
  }
}

function serializeSvgForDownload(svg) {
  const clone = svg.cloneNode(true);
  const { width, height } = svgDimensions(svg);
  clone.setAttribute("xmlns", "http://www.w3.org/2000/svg");
  clone.setAttribute("xmlns:xlink", "http://www.w3.org/1999/xlink");
  clone.setAttribute("width", String(width));
  clone.setAttribute("height", String(height));
  const styleText = collectStylesheetText();
  if (styleText) {
    const style = document.createElementNS("http://www.w3.org/2000/svg", "style");
    style.textContent = styleText;
    clone.insertBefore(style, clone.firstChild);
  }
  return new XMLSerializer().serializeToString(clone);
}

function collectStylesheetText() {
  return Array.from(document.styleSheets)
    .map((sheet) => {
      try {
        return Array.from(sheet.cssRules || []).map((rule) => rule.cssText).join("\n");
      } catch {
        return "";
      }
    })
    .filter(Boolean)
    .join("\n");
}

function svgDimensions(svg) {
  const viewBox = svg.viewBox?.baseVal;
  if (viewBox && viewBox.width && viewBox.height) {
    return { width: viewBox.width, height: viewBox.height };
  }
  const rect = svg.getBoundingClientRect();
  return {
    width: rect.width || Number(svg.getAttribute("width")) || 900,
    height: rect.height || Number(svg.getAttribute("height")) || 500,
  };
}

function loadImage(url) {
  return new Promise((resolve, reject) => {
    const image = new window.Image();
    image.onload = () => resolve(image);
    image.onerror = () => reject(new Error("Could not render SVG as PNG."));
    image.src = url;
  });
}

function downloadBlob(blob, filename) {
  const objectUrl = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = objectUrl;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
}

function filenameFromDisposition(disposition) {
  if (!disposition) return "";
  const utf8Match = disposition.match(/filename\*=UTF-8''([^;]+)/i);
  if (utf8Match?.[1]) {
    return decodeURIComponent(utf8Match[1].replaceAll('"', ""));
  }
  const match = disposition.match(/filename="?([^";]+)"?/i);
  return match?.[1] || "";
}

function fallbackDownloadFilename(label, href) {
  const extension = String(label || "download").toLowerCase().replace("method txt", "txt");
  const analysisId = String(href || "").split("/").filter(Boolean).at(-3) || "analysis";
  return `${analysisId}.${extension}`;
}

function formatInteger(value) {
  const number = scientificNumber(value);
  return number === null ? "..." : number.toLocaleString();
}

function retainedSampleCount(sampleSelection = {}) {
  return Object.values(sampleSelection.retained_sample_types || {}).reduce(
    (sum, value) => sum + Number(value || 0),
    0,
  );
}

function formatSampleTypeCounts(counts = {}) {
  const values = Object.entries(counts)
    .map(([label, count]) => `${label} ${formatInteger(count)}`);
  return values.join(" · ") || "No retained sample types reported";
}

function formatMedianSurvivalDays(value) {
  if (value === undefined || value === "") return "...";
  if (value === null) return "Not reached";
  const number = Number(value);
  if (!Number.isFinite(number)) return "Not reached";
  return Math.round(number).toLocaleString();
}

function formatDays(value) {
  const number = scientificNumber(value);
  if (number === null) return "...";
  return Math.round(number).toLocaleString();
}

function formatRmstDelta(rmst) {
  if (rmst?.status !== "completed") return "...";
  const value = scientificNumber(rmst.difference?.estimate_days);
  if (value === null) return "...";
  const sign = value > 0 ? "+" : "";
  return `${sign}${Math.round(value).toLocaleString()} days`;
}

function formatRmstCi(item) {
  const low = scientificNumber(item?.conf_low);
  const high = scientificNumber(item?.conf_high);
  if (low === null || high === null) return "...";
  return `${Math.round(low).toLocaleString()}-${Math.round(high).toLocaleString()}`;
}

function isMedianNotReached(value) {
  if (value === undefined || value === "") return false;
  if (value === null) return true;
  return !Number.isFinite(Number(value));
}

function formatExpressionValue(value) {
  const number = scientificNumber(value);
  if (number === null) return "...";
  return number.toFixed(2);
}

function formatDate(value) {
  if (!value) return "...";
  return new Date(value).toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "2-digit",
  });
}

function formatDateTime(value) {
  if (!value) return "...";
  return new Date(value).toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatLabel(value) {
  return String(value || "...").replaceAll("_", " ");
}

function formatSourceLabel(value) {
  return {
    tcga_cdr: "TCGA-CDR",
    derived_sample_metadata: "TCGA metadata",
    tcga_rna: "TCGA RNA-seq",
  }[value] || value || "...";
}

function toNullableNumber(value) {
  return scientificNumber(value);
}

function numbersEquivalent(left, right, tolerance = 1e-10) {
  const leftNumber = toNullableNumber(left);
  const rightNumber = toNullableNumber(right);
  if (leftNumber === null || rightNumber === null) return leftNumber === rightNumber;
  return Math.abs(leftNumber - rightNumber) <= tolerance * Math.max(1, Math.abs(leftNumber), Math.abs(rightNumber));
}



function formatError(error, options = {}) {
  return formatApiError(error, options);
}

function formatBatchItemError(item) {
  if (!item) return "Analysis failed.";
  return formatError({ code: item.code, message: item.error || "Analysis failed." });
}

const legacyMethodsHref = typeof window === "undefined"
  ? null
  : legacyStaticMethodsHref(window.location, import.meta.env.BASE_URL);

if (legacyMethodsHref) {
  window.location.replace(legacyMethodsHref);
} else {
  createRoot(document.getElementById("root")).render(
    <ModuleErrorBoundary resetKey="application" moduleName="TRACE Explorer">
      <App />
    </ModuleErrorBoundary>,
  );
}
