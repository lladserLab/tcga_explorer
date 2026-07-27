import React, { useEffect, useId, useLayoutEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import "@fontsource-variable/ibm-plex-sans/wght.css";
import "@fontsource-variable/ibm-plex-sans/wght-italic.css";
import {
  IconButton,
  ModuleIcon,
  TraceIcon,
} from "./design/icons";
import {
  apiUrl,
  createAnalysis,
  createAnalysesBatch,
  createCombinedAnalysis,
  createExploratorySession,
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
  getPaperExamples,
  getRepositoryDatasetEndpoints,
  getRepositoryDatasets,
  getRepositoryExpressionLayers,
  getRepositoryFilterOptions,
  searchGenes,
  searchRepositoryGenes,
} from "./api";
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
import "./styles.css";

const CUTPOINTS = [
  { value: "maxstat", label: "Maxstat", help: "Survival-optimized cutpoint, min 15% per group" },
  { value: "median", label: "Median", help: "Two balanced expression groups" },
  { value: "tertiles", label: "Tertiles", help: "Low, middle and high groups" },
  { value: "upper_quartile", label: "Upper quartile", help: "Top 25% against the rest" },
  { value: "upper_lower_quartile", label: "Outer quartiles", help: "Top 25% against bottom 25%" },
  { value: "percentile", label: "Percentile", help: "Custom high-expression threshold" },
];

const DICHOTOMIZATION_METHODS = [
  "maxstat",
  "median",
  "upper_quartile",
  "upper_lower_quartile",
  "percentile",
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
};

const DEFAULT_PLOT_STYLE = {
  palette: ["#1f6f8b", "#c8842d", "#b94d48"],
  font_family: "sans",
  plot_aspect: "rectangular",
  base_font_size: 12,
  axis_text_size: 11,
  axis_title_size: 12,
  show_grid: false,
  show_title: false,
  plot_title: "",
  continuous: {
    effect_color: "#1f6f8b",
    reference_color: "#75817e",
    show_title: true,
    plot_title: "",
    x_axis_title: "",
    y_axis_title: "",
  },
  cox_forest: {
    lower_hazard_color: "#1f6f8b",
    higher_hazard_color: "#b94d48",
    reference_color: "#7b8582",
    model_layout: "combined",
    show_title: true,
    plot_title: "",
    univariable_plot_title: "",
    multivariable_plot_title: "",
    x_axis_title: "",
  },
};

const PLOT_ARTIFACT_OPTIONS = [
  { value: "survival", label: "Survival" },
  { value: "continuous", label: "Continuous Cox" },
  { value: "cox_forest", label: "Cox models" },
];

const DEFAULT_COMBINED_PALETTE = [
  "#1f6f8b",
  "#c8842d",
  "#5a6f9f",
  "#b94d48",
  "#6c7a77",
  "#7b6aa8",
  "#3c8c5f",
  "#c46a42",
  "#4b5f5b",
];

const EMPTY_FILTERS = {
  sample_types: [],
  stages: [],
  grades: [],
  genders: [],
  races: [],
  age_min: "",
  age_max: "",
  max_time_days: "",
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
  { id: "dataset", label: "Dataset", iconRole: "module.dataset" },
  { id: "genes", label: "Genes", iconRole: "module.geneAnalysis" },
  { id: "endpoint", label: "Endpoint", iconRole: "module.survivalEndpoint" },
  { id: "groups", label: "Groups", iconRole: "module.stratification" },
  { id: "filters", label: "Clinical", iconRole: "module.clinicalFilters" },
  { id: "plot", label: "Plot & run", iconRole: "module.plotOutput" },
];
const COMPARE_WORKFLOW_STEPS = [
  { id: "dataset", label: "Dataset", iconRole: "module.dataset" },
  { id: "markers", label: "Markers", iconRole: "module.geneAnalysis" },
  { id: "methods", label: "Methods", iconRole: "module.stratification" },
  { id: "filters", label: "Clinical", iconRole: "module.clinicalFilters" },
  { id: "run", label: "Review & run", iconRole: "module.plotOutput" },
];
const MULTIVERSE_WORKFLOW_STEPS = [
  { id: "dataset", label: "Dataset", iconRole: "module.dataset" },
  { id: "marker", label: "Marker", iconRole: "module.geneAnalysis" },
  { id: "decisions", label: "Decisions", iconRole: "module.specificationCurve" },
  { id: "clinical", label: "Clinical", iconRole: "module.clinicalFilters" },
  { id: "run", label: "Review & run", iconRole: "module.plotOutput" },
];
const ENDPOINT_FALLBACK = [
  {
    value: "OS",
    label: "Overall survival",
    available: true,
    source: "derived_sample_metadata",
    reason: "Fallback OS derived from TCGA clinical/sample metadata.",
  },
];

const PANCANCER_ENDPOINTS = [
  { value: "OS", label: "Overall survival" },
  { value: "DSS", label: "Disease-specific survival" },
  { value: "PFI", label: "Progression-free interval" },
  { value: "DFI", label: "Disease-free interval" },
];

const PANCANCER_ENDPOINT_MODES = [
  {
    value: "same_endpoint",
    label: "Same endpoint",
    help: "Require each cancer to pass QC for the selected endpoint.",
  },
  {
    value: "death_like",
    label: "Death-like",
    help: "Use DSS when available, otherwise OS.",
  },
  {
    value: "progression_like",
    label: "Progression-like",
    help: "Use PFI or DFI depending on cohort availability.",
  },
  {
    value: "best_available",
    label: "Best available",
    help: "Use the selected endpoint first, then a TCGA-CDR fallback.",
  },
];

const ZSCORE_TRANSPORTABILITY_HELP =
  "Z-score signature genes are standardized among the expression-complete patients eligible in this run. Changing the endpoint or filters can change that reference population and the resulting score values; numerical z-score signature scores are not transportable across runs.";

const COMPETING_RISK_HELP =
  "For DSS, DFI and PFI, Kaplan-Meier and Cox treat a competing death as censoring and estimate event-free survival or a cause-specific hazard. When TCGA-CDR competing-event coding is available, the same result also reports cumulative incidence, Gray's test and Fine-Gray subdistribution hazard ratios. These are complementary estimands and should not be interpreted as interchangeable.";

const HELP_CONTENT = {
  dataset:
    "An analysis uses either one TCGA cohort or one exact release of a curated independent cohort. After clinical and endpoint eligibility, the app requires the requested gene or complete signature score and then retains one expression-complete sample per patient using the source-specific selection rule.",
  repository:
    "The repository contains public independent bulk RNA-seq cohorts with linked survival metadata. A detected candidate is not analyzable until its TCGA independence, license, expression scale, patient linkage, endpoint events and immutable checksums pass manual curation and automated QC. Releases are never pooled with TCGA or with each other.",
  defaultAnalysis:
    "The default Survival path uses one gene, OS, log2(TPM + 1), no clinical filters, age adjustment and a median split. It reports the cutpoint-independent continuous Cox model first, adds the spline when at least 30 events are available, and treats Kaplan-Meier, grouped Cox and RMST as median-split sensitivities. Every completed run creates audit and reconstruction downloads plus a signed server receipt; a declared multiverse remains an explicit separate action.",
  analysisDesign:
    "One signature runs standard single-gene or multi-gene survival analysis. Two signatures calculates two independent scores, stratifies each score and crosses the labels into combined groups.",
  survivalEndpoint:
    `TCGA endpoints come from TCGA-CDR when available: OS, DSS, PFI and DFI. External endpoints retain the release-specific time origin and event definition. Every endpoint is enabled only after patient and event count QC. ${COMPETING_RISK_HELP}`,
  geneMode:
    "Single genes are analyzed independently. Multi-gene modes collapse several genes into one signature score per patient before stratification.",
  expressionScale:
    "TCGA analyses offer the documented GDC-derived log-scale quantities and default to log2(TPM + 1). An external release exposes only its curated expression layer: its source unit, any applied transform and scale caveat are fixed in the manifest, shown in the interface and retained in the audit.",
  stratification:
    "Stratification converts a continuous expression or signature score into survival groups for secondary Kaplan-Meier, grouped Cox and RMST sensitivity analyses. Median is reproducible and balanced; maxstat is exploratory because it optimizes against survival.",
  clinicalFilters:
    "Filters restrict the eligible patient set before scoring, cutpoint selection and survival modeling. Empty filters include all available values.",
  clinicalAdjustment:
    "Clinical adjustment does not remove patients before grouping. It fits an additional complete-case Cox model using the exact imported and user-supplied covariates selected here. Age is continuous per 10 years; stage and grade are ordinal; GDC gender and race are categorical. External CSV variables are linked by exact TCGA participant barcode and use the type, effect unit, level order and reference recorded in the analysis.",
  externalCovariates:
    "Upload a patient-level CSV with a patient_id column and up to 10 variables. Use public TCGA participant barcodes only, for example TCGA-AB-1234. The browser validates and configures the data; selected values are included in the analysis request, patient CSV and audit bundle.",
  maxFollowup:
    "Maximum follow-up days censors records after the selected time horizon. Leave it empty to use the full endpoint follow-up.",
  plotOutput:
    "Choose Survival, Continuous Cox or Cox models to edit each exported PNG and SVG independently. The grouped Cox forest can remain combined or export univariable and multivariable model families as separate figures. Typography and grid are shared; colors, titles and applicable axes are artifact-specific. Scientific subtitles, model contrasts and estimates remain data-derived.",
  compare:
    "Compare analyses runs the same cohort, endpoint and expression scale across many gene by cutpoint combinations, then applies BH and Bonferroni correction across completed cells.",
  compareRobustness:
    "Run all 5 cutpoint methods means maxstat, median, upper quartile, outer quartiles and the selected percentile. Each gene also has one cutpoint-independent continuous reference. The grouped evidence profile reports BH, Cox, RMST, marker PH and model PH separately.",
  multiverse:
    "A prespecified multiverse runs every selected endpoint, signature-scoring and cutpoint combination as one declared family. Continuous Cox models and grouped sensitivities receive separate multiplicity correction, and every planned cell remains in the execution ledger.",
  continuousModel:
    "The primary single-gene or one-signature model uses all expression-complete eligible patients and reports a Cox hazard ratio per +1 within-analysis expression standard deviation.",
  spline:
    "A three-parameter restricted cubic spline with knots at the 5th, 35th, 65th and 95th percentiles estimates the shape of the expression-risk association when at least 30 events are available. The nonlinearity p-value compares the spline with a linear Cox effect.",
  pancancer:
    "Pan-cancer analysis reports each cohort per +1 within-cohort expression SD without pooling that scale. Eligible single-gene and mean/weighted-signature effects are also expressed per +1 common input-score unit and synthesized only within one endpoint and model family using REML, HKSJ inference and a 95% prediction interval.",
  pancancerEndpointMode:
    "Endpoint mode defines how strictly cohorts must match the requested endpoint. Same endpoint is strict; best available allows TCGA-CDR fallback endpoints when QC passes.",
  rmst:
    "RMST, restricted mean survival time, estimates average event-free time up to one fixed cohort-level horizon. It complements the hazard ratio, but the group comparison still depends on the selected cutpoint.",
  coxPH:
    "PH diagnostics use cox.zph for each marker term and the complete Cox model. When the marker-specific p-value is below 0.05, TCGA-TRACE reports separate marker HRs before and after a fixed 2-year primary split plus fixed 1- and 5-year sensitivities. These coarse two-period summaries are prespecified, never outcome-optimized, and require support on both sides.",
  audit:
    "Audit exports record the exact payload, selected patients, endpoint source, model outputs, package versions and artifact checksums. The ZIP also contains a standalone R runner, exact analysis engine, renv.lock and a pinned Dockerfile. SHA-256 values detect drift or corruption. A detached Ed25519 receipt additionally signs the exact audit report and run hash; verify it against the key published by the declared HTTPS server. The receipt proves origin for that report, not scientific correctness or immutable publication time.",
};

const SCORE_METHOD_GUIDE = {
  single:
    "Uses one gene expression vector directly. When several genes are entered in single-gene mode, each gene is run as a separate analysis.",
  mean:
    "Averages log-scale expression across genes. This is simple and interpretable, but genes with larger numeric ranges can dominate the score.",
  zscore:
    `Standardizes each gene across samples, then averages the standardized values. This is the default for signatures because it gives each gene comparable influence. ${ZSCORE_TRANSPORTABILITY_HELP}`,
  weighted:
    "Calculates a weighted score from genes entered as GENE:weight. This is useful for curated signatures where direction or effect size is known in advance.",
};

const CUTPOINT_GUIDE = {
  maxstat:
    "Chooses the threshold with strongest survival separation under a minimum group-size constraint. Use for discovery, then validate because it is outcome-optimized.",
  median:
    "Splits patients into two similarly sized groups. It is the safest default for reproducible Kaplan-Meier stratification.",
  tertiles:
    "Splits scores into low, middle and high groups. It adds resolution but needs enough patients and events in every group.",
  upper_quartile:
    "Compares the top 25% of expression against the remaining 75%. Useful for high-expression biology with sufficient events.",
  upper_lower_quartile:
    "Compares the top and bottom quartiles and excludes the middle half. It sharpens contrast but reduces sample size.",
  percentile:
    "Uses the selected percentile as the high-expression threshold. Document the percentile because changing it changes the tested hypothesis.",
};

const HELP_GUIDE_SECTIONS = [
  {
    title: "Analysis Inputs",
    items: [
      ["Default analysis path", HELP_CONTENT.defaultAnalysis],
      ["Cancer cohort", HELP_CONTENT.dataset],
      ["Independent cohort repository", HELP_CONTENT.repository],
      ["Survival endpoint", HELP_CONTENT.survivalEndpoint],
      ["Expression scale", HELP_CONTENT.expressionScale],
      ["Clinical filters", HELP_CONTENT.clinicalFilters],
      ["Cox adjustment", HELP_CONTENT.clinicalAdjustment],
      ["External covariates", HELP_CONTENT.externalCovariates],
      ["Maximum follow-up", HELP_CONTENT.maxFollowup],
    ],
  },
  {
    title: "Signature Scoring",
    items: [
      ["Single gene", SCORE_METHOD_GUIDE.single],
      ["Mean signature", SCORE_METHOD_GUIDE.mean],
      ["Z-score signature", SCORE_METHOD_GUIDE.zscore],
      ["Weighted signature", SCORE_METHOD_GUIDE.weighted],
    ],
  },
  {
    title: "Stratification",
    items: Object.entries(CUTPOINT_GUIDE).map(([key, body]) => [formatLabel(key), body]),
  },
  {
    title: "Survival Outputs",
    items: [
      ["Continuous Cox", HELP_CONTENT.continuousModel],
      ["Restricted cubic spline", HELP_CONTENT.spline],
      ["Kaplan-Meier", "Plots survival curves by expression group, reports log-rank p-values, patient counts, events and median survival when the curve reaches 50%."],
      ["Grouped Cox models", "Reports cutpoint-dependent hazard ratios for univariable, exact user-selected and auxiliary stage/grade models. Complete-case N, events and covariate encoding are model-specific."],
      ["Sparse-event diagnostics", "Reports fitted coefficients and events per parameter for every Cox model. Values below 10 are cautioned and values below 5 receive a severe caution."],
      ["Firth sensitivity", "Runs automatically when a Cox model has low events per parameter, convergence concerns or an extreme marker estimate. It uses Firth penalized partial likelihood with profile-likelihood confidence intervals and is shown beside, not substituted for, the standard Cox estimate."],
      ["PH diagnostics", HELP_CONTENT.coxPH],
      ["RMST", HELP_CONTENT.rmst],
      ["DSS, DFI and PFI competing events", COMPETING_RISK_HELP],
      ["Audit report", HELP_CONTENT.audit],
    ],
  },
  {
    title: "Comparison And Pan-Cancer",
    items: [
      ["Run selected methods", "Runs only the cutpoint methods currently selected in Compare analyses."],
      ["Run all 5 cutpoint methods", HELP_CONTENT.compareRobustness],
      ["Prespecified multiverse", HELP_CONTENT.multiverse],
      ["Exploratory run history", "Optionally records accepted browser compute jobs in local storage. A selected export deduplicates exact hypotheses, separates continuous, grouped and interaction families, and references multiverse or pan-cancer corrections without recounting them. The exported scope is post hoc and cannot prove that no other runs occurred."],
      ["Continuous pan-cancer Cox", HELP_CONTENT.pancancer],
      ["Endpoint mode", HELP_CONTENT.pancancerEndpointMode],
    ],
  },
];

const METHOD_HISTORY = [
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
      "Survival, Compare and Multiverse can use one immutable external bulk RNA-seq release with linked clinical outcomes; Pan-cancer remains TCGA-only.",
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
      "Development deployments remain labeled as development and cannot satisfy the final-release evidence contract.",
    ],
  },
  {
    version: "exploratory-session-family-v1.0",
    title: "Optional exploratory run history",
    date: "2026-07",
    items: [
      "Opt-in browser-local recording captures accepted Survival, Compare, Multiverse and Pan-cancer jobs without storing patient records or uploaded covariate rows.",
      "Selected exports resolve authoritative requests and results from server job IDs and retain repeated run events while deduplicating exact hypotheses.",
      "Continuous Cox, grouped cutpoint and two-signature interaction tests receive separate export-defined BH and Bonferroni families.",
      "Prespecified multiverse and pan-cancer scans retain their internal correction and are referenced without double counting.",
      "The audit and signed receipt state that the post hoc export covers only selected events and cannot attest that no other analyses occurred.",
    ],
  },
  {
    version: "server-attestation-contract-v1.0",
    title: "Server-signed audit receipts",
    date: "2026-07",
    items: [
      "Every new analysis, multiverse, pan-cancer scan and exploratory session export receives a detached Ed25519 receipt for its exact audit report.",
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
      "Survival, Compare and Multiverse accept a patient-level CSV linked by exact public TCGA participant barcodes.",
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
      "A dependency-free Python client checks the live OpenAPI contract before submitting public compute jobs.",
      "Single, combined-signature, batch, multiverse and pan-cancer requests can be submitted and polled outside the browser.",
      "Retained artifacts can be downloaded recursively with a local SHA-256 transfer manifest.",
      "Analysis, multiverse and pan-cancer ZIP bundles receive family-aware integrity verification without changing statistical results.",
    ],
  },
  {
    version: "browser-gene-suggestion-contract-v1.0",
    title: "Browser compatibility and reliable gene suggestions",
    date: "2026-07",
    items: [
      "Partial gene text is no longer committed when a workflow step moves focus before cohort suggestions arrive.",
      "Single-signature, crossed-signature, Compare and Multiverse searches cancel obsolete responses and expose accessible loading and error states.",
      "A versioned Playwright contract exercises Survival, Compare, Paper Examples, Pan-cancer, Dataset Summary, downloads, keyboard focus and reduced motion.",
      "Provisional checks run in Chromium, Firefox/Gecko and WebKit; final evidence must target the exact tagged HTTPS release.",
    ],
  },
  {
    version: "runtime-identity-contract-v1.0",
    title: "Runtime evidence and canonical identity",
    date: "2026-07",
    items: [
      "TCGA-TRACE is now the canonical interface, API, manuscript and release name; the /tcga_explorer URL remains a compatibility route.",
      "Generated manuscript files and the review archive use the tcga-trace prefix and bind the canonical project name in the archive manifest.",
      "A public-API benchmark records uncached and cached analyses, two-job concurrency, batch, 72-cell multiverse and 33-cohort pan-cancer execution.",
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
    version: "artifact-specific-cox-plot-style-v1.0",
    title: "Artifact-specific Cox plot styling",
    date: "2026-07",
    items: [
      "Kaplan-Meier, continuous spline and grouped Cox forest artifacts now have distinct color and title controls.",
      "Continuous-effect axis titles and the Cox forest hazard-ratio axis title can be customized without changing model labels, contrasts or estimates.",
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
      "Clean-container tests disable network access, mount the capsule read-only and run on native arm64 plus amd64; an independent Linux/amd64 CI job repeats the contract.",
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
    version: "immune-pancancer-primary-plus-ordinal-sensitivity-cox-audit-v2.1",
    title: "Immune atlas clinical-sensitivity refresh",
    date: "2026-07",
    items: [
      "All 3,118 frozen ImmPort genes are recomputed across strict-OS TCGA cohorts with primary, ordinal-stage, ordinal-grade and stage+grade Cox families.",
      "Atlas-wide gene–cancer BH-FDR and gene-level random-effects meta-FDR are calculated independently inside every comparable model family.",
      "The availability-selected sensitivity hierarchy is stage+grade, then stage, then grade; mixed selected families support retained/attenuated summaries but are never meta-analyzed.",
      "Direction changes among all estimates remain available diagnostically, while headline flips are restricted to primary-FDR-supported associations to avoid magnifying null-effect noise.",
      "Every completed model carries cox.zph output, and the atlas audit pins ImmPort sources, patient records and expression matrices with SHA-256 hashes.",
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
      "Independent scoring for Signature A and Signature B using single, mean, z-score or weighted methods.",
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
      "The selected sensitivity hierarchy is stage+grade, then stage, then grade; availability—not effect size or p-value—drives selection.",
      "BH-FDR and random-effects meta-analysis are reported separately for every adjustment family; mixed selected families are never silently pooled.",
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

const APP_NAV = [
  {
    id: "home",
    label: "Home",
    kicker: "About TCGA-TRACE",
    iconRole: "navigation.home",
  },
  {
    id: "analysis",
    label: "Survival",
    kicker: "Single gene or signature",
    iconRole: "navigation.analysis",
  },
  {
    id: "compare",
    label: "Compare",
    kicker: "Genes and cutpoints",
    iconRole: "navigation.compare",
  },
  {
    id: "multiverse",
    label: "Multiverse",
    kicker: "Specification curve",
    iconRole: "navigation.multiverse",
  },
  {
    id: "session",
    label: "Run history",
    kicker: "Exploratory record",
    iconRole: "navigation.session",
  },
  {
    id: "pancancer",
    label: "Pan-cancer",
    kicker: "Cox concordance",
    iconRole: "navigation.panCancer",
  },
  {
    id: "examples",
    label: "Examples",
    kicker: "Paper figures",
    iconRole: "navigation.examples",
  },
  {
    id: "repository",
    label: "Repository",
    kicker: "Independent cohorts",
    iconRole: "module.cohortResults",
  },
  {
    id: "summary",
    label: "Dataset",
    kicker: "Inventory",
    iconRole: "navigation.dataset",
  },
  {
    id: "api",
    label: "API & MCP",
    kicker: "Public access",
    iconRole: "navigation.api",
  },
  {
    id: "help",
    label: "Methods",
    kicker: "Versions and definitions",
    iconRole: "navigation.methods",
  },
];

const PAGE_META = {
  home: {
    title: "TCGA-TRACE",
    summary: "Traceable RNA survival analysis across TCGA cohorts.",
  },
  analysis: {
    title: "Survival analysis",
    summary: "Patient-level curves, adjusted models, diagnostics and audit exports.",
  },
  compare: {
    title: "Compare genes and cutpoints",
    summary: "One cohort and endpoint across genes and stratification rules.",
  },
  multiverse: {
    title: "Specification curve",
    summary: "Prespecify endpoint, scoring and cutpoint choices as one auditable family.",
  },
  session: {
    title: "Exploratory run history",
    summary: "Record selected browser runs and export explicit post hoc multiplicity families.",
  },
  pancancer: {
    title: "Pan-cancer concordance",
    summary: "Continuous Cox effects, FDR and heterogeneity across TCGA cohorts.",
  },
  examples: {
    title: "Paper examples",
    summary: "Literature-guided examples, unsupported results and diagnostic cases.",
  },
  repository: {
    title: "External RNA-seq repository",
    summary: "Curated independent cancer cohorts with survival-ready clinical data.",
  },
  summary: {
    title: "TCGA data",
    summary: "Cohort, endpoint, source and linked-sample coverage.",
  },
  api: {
    title: "API & MCP",
    summary: "Use the same data and methods from code, Claude or ChatGPT.",
  },
  help: {
    title: "Methods",
    summary: "Definitions, pipeline versions and reproducibility assumptions.",
  },
};

function getCohortName(cohortId) {
  return COHORT_NAMES[cohortId] || cohortId || "Unknown cancer";
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
  return {
    ...style,
    palette: paletteOverride || style.palette,
    plot_aspect: style.plot_aspect,
    base_font_size: Number(style.base_font_size),
    axis_text_size: Number(style.axis_text_size),
    axis_title_size: Number(style.axis_title_size),
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
  const signatureGenes = parseSignatureGenes(form.gene_symbol);
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
      form.cutpoint_method === "percentile" ? Number(form.custom_percentile) : null,
    plot_style: buildPlotStylePayload(form.plot_style),
    filters: {
      ...form.filters,
      age_min: toNullableNumber(form.filters.age_min),
      age_max: toNullableNumber(form.filters.age_max),
      max_time_days: toNullableNumber(form.filters.max_time_days),
    },
  };
}

function buildCombinedAnalysisPayload(form, signatureAInput, signatureBInput) {
  const groupingMethod = form.combined_signature.grouping_method;
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
    filters: {
      ...form.filters,
      age_min: toNullableNumber(form.filters.age_min),
      age_max: toNullableNumber(form.filters.age_max),
      max_time_days: toNullableNumber(form.filters.max_time_days),
    },
  };
}

function buildSignatureSpec(signature, geneInput, fallbackName) {
  const normalizedInput = geneInputTokens(geneInput).join(", ");
  return {
    name: signature.name.trim() || fallbackName,
    gene_symbol: normalizedInput,
    signature_method: signature.signature_method,
    signature_genes: signature.signature_method === "single" ? [] : parseSignatureGenes(normalizedInput),
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

function parseSignatureGenes(text) {
  return text
    .split(/[,+;\n]/)
    .map((item) => item.trim())
    .filter(Boolean)
    .map((item) => {
      const [gene, weight] = item.split(":").map((part) => part.trim());
      return { gene_symbol: gene.toUpperCase(), weight: Number(weight) || 1 };
    });
}

function uniqueGeneSymbols(text) {
  const seen = new Set();
  return parseSignatureGenes(text)
    .map((item) => item.gene_symbol)
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
  const [gene, weight] = String(item || "").split(":").map((part) => part.trim());
  const symbol = gene.toUpperCase();
  if (!symbol) return "";
  return weight ? `${symbol}:${weight}` : symbol;
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

function App() {
  const resultPanelRef = useRef(null);
  const analysisStepPanelRef = useRef(null);
  const hasNavigatedRef = useRef(false);
  const [health, setHealth] = useState(null);
  const [cohorts, setCohorts] = useState([]);
  const [repositoryCoverage, setRepositoryCoverage] = useState(null);
  const [repositoryDatasets, setRepositoryDatasets] = useState([]);
  const [repositoryLayers, setRepositoryLayers] = useState([]);
  const [datasetSummary, setDatasetSummary] = useState(null);
  const [dataSources, setDataSources] = useState([]);
  const [endpointOptions, setEndpointOptions] = useState(ENDPOINT_FALLBACK);
  const [expressionScales, setExpressionScales] = useState(EXPRESSION_SCALE_FALLBACK);
  const [filters, setFilters] = useState(null);
  const [analysisResults, setAnalysisResults] = useState([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [geneQuery, setGeneQuery] = useState("");
  const [combinedGeneQueries, setCombinedGeneQueries] = useState({ a: "", b: "" });
  const [cohortQuery, setCohortQuery] = useState("");
  const [cohortPickerOpen, setCohortPickerOpen] = useState(false);
  const [summaryCohort, setSummaryCohort] = useState("");
  const [activePage, setActivePage] = useState("home");
  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => {
    try {
      return window.localStorage.getItem("tcga-trace-sidebar-collapsed") === "true";
    } catch {
      return false;
    }
  });
  const [analysisStep, setAnalysisStep] = useState(0);
  const [plotEditorTarget, setPlotEditorTarget] = useState("survival");
  const [downloadNotices, setDownloadNotices] = useState([]);
  const [paperExamples, setPaperExamples] = useState({
    data: null,
    loading: false,
    error: "",
  });
  const [compare, setCompare] = useState({
    genes: "",
    methods: ["median", "upper_quartile"],
    running: false,
    results: [],
    error: "",
  });
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
    gene_symbol: "",
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
  const genes = geneSuggestionState.genes;
  const combinedGeneSuggestions = {
    a: combinedSuggestionA.genes,
    b: combinedSuggestionB.genes,
  };
  const combinedGeneSuggestionStates = {
    a: combinedSuggestionA,
    b: combinedSuggestionB,
  };

  useEffect(() => {
    Promise.all([
      getHealth(),
      getCohorts(),
      getExpressionScales(),
      getDatasetSummary(),
      getDataSources(),
      getCancerRepositoryCoverage().catch(() => null),
      getRepositoryDatasets().catch(() => ({ datasets: [] })),
    ])
      .then(([
        healthPayload,
        cohortPayload,
        scalePayload,
        summaryPayload,
        sourcePayload,
        repositoryCoveragePayload,
        repositoryDatasetPayload,
      ]) => {
        setHealth(healthPayload);
        setCohorts(cohortPayload);
        setRepositoryCoverage(repositoryCoveragePayload);
        setRepositoryDatasets(repositoryDatasetPayload?.datasets || []);
        setDatasetSummary(summaryPayload);
        setDataSources(sourcePayload?.sources || summaryPayload?.data_sources || []);
        if (scalePayload?.length) {
          setExpressionScales(scalePayload);
        }
        if (form.cohort && cohortPayload.length && !cohortPayload.find((item) => item.id === form.cohort)) {
          setForm((current) => ({ ...current, cohort: "" }));
        }
      })
      .catch((err) => setError(err.message));
  }, []);

  useEffect(() => {
    try {
      window.localStorage.setItem("tcga-trace-sidebar-collapsed", String(sidebarCollapsed));
    } catch {
      // Storage can be unavailable in privacy-restricted browser contexts.
    }
  }, [sidebarCollapsed]);

  useEffect(() => {
    persistSessionHistory(sessionHistory);
  }, [sessionHistory]);

  useEffect(() => {
    function captureJobUpdate(event) {
      setSessionHistory((current) =>
        reduceSessionJobUpdate(current, event.detail),
      );
    }
    window.addEventListener(SESSION_JOB_EVENT, captureJobUpdate);
    return () => window.removeEventListener(SESSION_JOB_EVENT, captureJobUpdate);
  }, []);

  useEffect(() => {
    if (!form.cohort) return undefined;
    let cancelled = false;
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
          getFilterOptions(form.cohort),
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
          : ENDPOINT_FALLBACK;
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
        const fallbackEndpoint = options.find((item) => item.available) || options[0] || ENDPOINT_FALLBACK[0];
        const availableEndpoints = options
          .filter((item) => item.available)
          .map((item) => item.value);
        setMultiverse((current) => ({
          ...current,
          endpoints: availableEndpoints.length
            ? availableEndpoints
            : [fallbackEndpoint.value],
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
          filters: { ...EMPTY_FILTERS },
        }));
      })
      .catch((err) => {
        if (!cancelled) setError(err.message);
      });
    return () => {
      cancelled = true;
    };
  }, [form.cohort, form.dataset_id, form.dataset_release_id]);

  useEffect(() => {
    getDatasetSummary(summaryCohort)
      .then((payload) => setDatasetSummary(payload))
      .catch((err) => setError(err.message));
  }, [summaryCohort]);

  useEffect(() => {
    const searchTerm = currentGeneSearchTerm(panCancer.geneQuery);
    const cohort = panCancer.index_cohort || form.cohort || cohorts[0]?.id || "";
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

  useEffect(() => {
    if (activePage !== "pancancer" || panCancer.immuneScreen || panCancer.immuneScreenLoading || panCancer.immuneScreenError) return;
    setPanCancer((current) => ({ ...current, immuneScreenLoading: true, immuneScreenError: "" }));
    getImmunePanCancerScreen()
      .then((payload) => setPanCancer((current) => ({ ...current, immuneScreen: payload, immuneScreenError: "" })))
      .catch((err) => setPanCancer((current) => ({ ...current, immuneScreenError: formatError(err) })))
      .finally(() => setPanCancer((current) => ({ ...current, immuneScreenLoading: false })));
  }, [activePage, panCancer.immuneScreen, panCancer.immuneScreenLoading, panCancer.immuneScreenError]);

  useEffect(() => {
    if (
      activePage !== "examples"
      || paperExamples.data
      || paperExamples.loading
      || paperExamples.error
    ) return;
    setPaperExamples((current) => ({ ...current, loading: true }));
    getPaperExamples()
      .then((payload) => setPaperExamples({ data: payload, loading: false, error: "" }))
      .catch((err) => setPaperExamples({ data: null, loading: false, error: formatError(err) }));
  }, [activePage, paperExamples.data, paperExamples.loading, paperExamples.error]);

  const selectedCohort = useMemo(
    () => cohorts.find((cohort) => cohort.id === form.cohort),
    [cohorts, form.cohort],
  );
  const selectedRepositoryDataset = useMemo(
    () => repositoryDatasets.find((dataset) => dataset.id === form.dataset_id),
    [form.dataset_id, repositoryDatasets],
  );
  const cohortRepositoryDatasets = useMemo(
    () => repositoryDatasets.filter(
      (dataset) => dataset.tcga_cohort === form.cohort,
    ),
    [form.cohort, repositoryDatasets],
  );

  const visibleCohorts = useMemo(() => {
    const query = cohortQuery.trim().toLowerCase();
    if (!query) return cohorts;
    return cohorts.filter((cohort) =>
      [cohort.id, getCohortName(cohort.id), cohort.primary_site, cohort.disease_type]
        .filter(Boolean)
        .some((value) => String(value).toLowerCase().includes(query)),
    );
  }, [cohorts, cohortQuery]);

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
    return listCount + rangeCount;
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
  const selectedEndpoint =
    endpointOptions.find((item) => item.value === form.endpoint) || ENDPOINT_FALLBACK[0];
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
  const runCount = isCombinedMode
    ? selectedSignatureAGenes.length && selectedSignatureBGenes.length ? 2 : 0
    : form.signature_method === "single"
      ? selectedGenes.length
      : Math.min(selectedGenes.length, 1);
  const canRun = isCombinedMode
    ? Boolean(form.cohort && selectedSignatureAGenes.length && selectedSignatureBGenes.length && selectedEndpoint.available) && !loading
    : Boolean(form.cohort && selectedGenes.length && selectedEndpoint.available) && !loading;
  const previewCutpoint = isCombinedMode
    ? {
        label: form.combined_signature.grouping_method === "tertiles"
          ? "Tertiles x tertiles"
          : "Median x median",
      }
    : selectedCutpoint;
  const selectedCancerName = form.cohort ? getCohortName(form.cohort) : "Select cancer";
  const plotCancerName = form.cohort ? getCohortName(form.cohort) : "Cancer";
  const pageMeta = PAGE_META[activePage] || PAGE_META.analysis;
  const hasGeneSelection = isCombinedMode
    ? Boolean(selectedSignatureAGenes.length && selectedSignatureBGenes.length)
    : Boolean(selectedGenes.length);
  const coreAnalysisReady = Boolean(form.cohort && hasGeneSelection && selectedEndpoint.available);
  const analysisStepCompletion = [
    Boolean(form.cohort),
    hasGeneSelection,
    Boolean(form.cohort && selectedEndpoint.available),
    coreAnalysisReady,
    coreAnalysisReady,
    canRun,
  ];
  const analysisStepRequirements = [
    form.cohort ? "" : "Select a cancer cohort to continue.",
    hasGeneSelection
      ? ""
      : isCombinedMode
        ? "Add at least one gene to both signatures."
        : "Add at least one gene or signature.",
    form.cohort
      ? selectedEndpoint.available ? "" : "Choose an endpoint that passes cohort QC."
      : "Select a cohort before choosing an endpoint.",
    coreAnalysisReady ? "" : "Complete Dataset, Genes and Endpoint first.",
    coreAnalysisReady ? "" : "Complete Dataset, Genes and Endpoint first.",
    canRun ? "" : "Complete the required cohort, gene and endpoint selections.",
  ];
  const activeAnalysisStep = ANALYSIS_WORKFLOW_STEPS[analysisStep] || ANALYSIS_WORKFLOW_STEPS[0];
  const analysisGeneSummary = isCombinedMode
    ? `A ${selectedSignatureAGenes.length || 0} / B ${selectedSignatureBGenes.length || 0}`
    : selectedGenes.length
      ? `${selectedGenes.slice(0, 3).join(", ")}${selectedGenes.length > 3 ? ` +${selectedGenes.length - 3}` : ""}`
      : "Gene pending";
  const analysisSetupSummary = [
    selectedRepositoryDataset?.source_accession
      || form.cohort
      || "Cohort pending",
    analysisGeneSummary,
    selectedEndpoint?.value || "Endpoint pending",
    previewCutpoint?.label || "Groups pending",
    activeFilterCount ? `${activeFilterCount} filter${activeFilterCount === 1 ? "" : "s"}` : "No filters",
    formatAdjustmentSummary(
      selectedAdjustmentCovariates,
      selectedExternalAdjustmentCovariates,
      form.external_covariates,
    ),
  ].join(" · ");

  function updateForm(key, value) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  function selectExpressionScale(value) {
    updateForm(
      form.dataset_id ? "expression_layer_id" : "expression_scale",
      value,
    );
  }

  function navigateAnalysisStep(nextStep) {
    const boundedStep = Math.max(0, Math.min(ANALYSIS_WORKFLOW_STEPS.length - 1, nextStep));
    setAnalysisStep(boundedStep);
    window.requestAnimationFrame(() => {
      analysisStepPanelRef.current?.focus({ preventScroll: true });
      document
        .getElementById(`analysis-step-${ANALYSIS_WORKFLOW_STEPS[boundedStep].id}`)
        ?.scrollIntoView({ behavior: "auto", block: "nearest", inline: "center" });
      analysisStepPanelRef.current
        ?.closest(".analysis-step-controls")
        ?.scrollIntoView({ behavior: "auto", block: "start" });
    });
  }

  function navigateToPage(page) {
    if (page === activePage) return;
    hasNavigatedRef.current = true;
    setCohortPickerOpen(false);
    setActivePage(page);
    window.requestAnimationFrame(() => window.scrollTo({ top: 0, left: 0, behavior: "auto" }));
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

  function updateFilters(key, value) {
    setForm((current) => ({
      ...current,
      filters: { ...current.filters, [key]: value },
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
    setForm((current) => ({
      ...current,
      cohort: value,
      dataset_id: null,
      dataset_release_id: null,
      expression_layer_id: null,
      filters: { ...EMPTY_FILTERS },
      external_covariates: null,
      external_adjustment_covariates: [],
    }));
    setRepositoryLayers([]);
    setCohortPickerOpen(false);
    setCohortQuery("");
    setAnalysisResults([]);
    setCompare((current) => ({ ...current, results: [], error: "" }));
    setMultiverse((current) => ({ ...current, result: null, error: "" }));
    setError("");
  }

  function selectRepositoryDataset(datasetId) {
    const dataset = repositoryDatasets.find((item) => item.id === datasetId);
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
    setCompare((current) => ({ ...current, results: [], error: "" }));
    setMultiverse((current) => ({ ...current, result: null, error: "" }));
    setError("");
  }

  function analyzeRepositoryDataset(datasetId) {
    selectRepositoryDataset(datasetId);
    navigateToPage("analysis");
    setAnalysisStep(0);
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
      const response = await fetch(apiUrl(href));
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
    if (isCombinedMode) {
      const normalizedA = geneInputTokens(effectiveSignatureAInput).join(", ");
      const normalizedB = geneInputTokens(effectiveSignatureBInput).join(", ");
      if (!uniqueGeneSymbols(normalizedA).length || !uniqueGeneSymbols(normalizedB).length) {
        setError("Enter genes for both signatures before running the combined analysis.");
        return;
      }

      setLoading(true);
      setError("");
      setAnalysisResults([]);
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
        const payload = buildCombinedAnalysisPayload(form, normalizedA, normalizedB);
        const result = await createCombinedAnalysis(payload);
        setAnalysisResults([result]);
      } catch (err) {
        setError(formatError(err));
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
    setAnalysisResults([]);
    scrollToResults();
    const normalizedInput =
      form.signature_method === "single"
        ? normalizedGenes.join(", ")
        : geneInputTokens(sourceInput).join(", ");
    setGeneQuery("");
    updateForm("gene_symbol", normalizedInput);

    try {
      if (form.signature_method === "single") {
        const payloads = normalizedGenes.map((gene) => ({
            ...buildAnalysisPayload({ ...form, gene_symbol: gene, signature_method: "single" }),
            gene_symbol: gene,
            signature_method: "single",
            signature_genes: [],
        }));
        if (payloads.length === 1) {
          const result = await createAnalysis(payloads[0]);
          setAnalysisResults([result]);
        } else {
          const batch = await createAnalysesBatch(payloads, ANALYSIS_BATCH_CONCURRENCY);
          const successful = batch.results
            .filter((item) => item.status === "completed" && item.result)
            .map((item) => item.result);
          setAnalysisResults(successful);
          if (batch.failed) {
            const firstFailure = batch.results.find((item) => item.status === "failed");
            setError(`${batch.failed} analysis${batch.failed === 1 ? "" : "es"} failed. ${formatBatchItemError(firstFailure)}`);
          }
        }
      } else {
        const payload = buildAnalysisPayload({ ...form, gene_symbol: normalizedInput });
        const result = await createAnalysis(payload);
        setAnalysisResults([result]);
      }
    } catch (err) {
      setError(formatError(err));
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
    setSessionExport({ running: true, result: null, error: "" });
    try {
      const result = await createExploratorySession(payload);
      setSessionExport({ running: false, result, error: "" });
    } catch (err) {
      setSessionExport({
        running: false,
        result: null,
        error: formatError(err),
      });
    }
  }

  return (
    <main
      className={`app-shell${sidebarCollapsed ? " sidebar-collapsed" : ""}`}
      data-page={activePage}
    >
      <aside className={`sidebar${sidebarCollapsed ? " is-collapsed" : ""}`}>
        <div className="sidebar-heading">
          <button
            type="button"
            className="brand"
            onClick={() => navigateToPage("home")}
            aria-label="Go to TCGA-TRACE home"
            title="TCGA-TRACE home"
          >
            <TraceLogo key={`brand-${activePage}`} animated={hasNavigatedRef.current} />
            <span className="brand-copy">
              <strong>TCGA-TRACE</strong>
              <span>Traceable RNA survival</span>
            </span>
          </button>
          <IconButton
            className="sidebar-toggle"
            iconRole={sidebarCollapsed ? "action.sidebarOpen" : "action.sidebarClose"}
            label={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}
            size="sm"
            aria-expanded={!sidebarCollapsed}
            onClick={() => setSidebarCollapsed((current) => !current)}
          />
        </div>

        <div className="status-block">
          <StatusItem iconRole="module.dataset" label="Cohorts" value={health?.cohorts ?? "..."} />
          <StatusItem iconRole="module.survivalEndpoint" label="Endpoint" value={selectedEndpoint.label} />
          <StatusItem iconRole="module.rnaScale" label="Expression" value={selectedExpressionScale.label} />
          <StatusItem
            iconRole="data.calendar"
            label="Data loaded"
            value={formatDate(health?.data_dates?.database_imported_at)}
          />
        </div>

        <nav className="side-nav" aria-label="Workspace pages">
          {APP_NAV.map(({ id, label, kicker, iconRole }) => (
            <button
              key={id}
              type="button"
              className={activePage === id ? "selected" : ""}
              onClick={() => navigateToPage(id)}
              aria-current={activePage === id ? "page" : undefined}
              aria-label={`${label}: ${kicker}`}
              title={`${label}: ${kicker}`}
            >
              <ModuleIcon role={iconRole} frame="navigation" />
              <span className="nav-copy">
                <strong>{label}</strong>
              </span>
            </button>
          ))}
        </nav>
      </aside>

      <section className="workspace">
        {activePage !== "home" && (
          <header className="topbar">
            <div>
              <h1>{pageMeta.title}</h1>
              <p className="page-summary">{pageMeta.summary}</p>
            </div>
          </header>
        )}

        <div
          key={`page-${activePage}`}
          className={`page-stage${hasNavigatedRef.current ? " is-entering" : ""}`}
        >
        {activePage === "home" ? (
          <HomePage
            health={health}
            summary={datasetSummary}
            repositoryCoverage={repositoryCoverage}
            onNavigate={navigateToPage}
          />
        ) : activePage === "analysis" ? (
          <>
            <div className="layout analysis-workflow-layout">
              <section className="control-panel analysis-step-controls" aria-label="Analysis controls">
                <AnalysisWorkflowStepper
                  steps={ANALYSIS_WORKFLOW_STEPS}
                  activeStep={analysisStep}
                  completion={analysisStepCompletion}
                  summary={analysisSetupSummary}
                  onSelect={navigateAnalysisStep}
                />

                <section
                  ref={analysisStepPanelRef}
                  className="analysis-step-panel"
                  id={`analysis-step-panel-${activeAnalysisStep.id}`}
                  aria-labelledby={`analysis-step-${activeAnalysisStep.id}`}
                  tabIndex={-1}
                >
                  {activeAnalysisStep.id === "dataset" && (
                    <>
                      <PanelHeader iconRole="module.dataset" title="Dataset" help={HELP_CONTENT.dataset} />
                      <CohortPicker
                        cohorts={cohorts}
                        visibleCohorts={visibleCohorts}
                        selectedCohort={selectedCohort}
                        selectedCohortId={form.cohort}
                        query={cohortQuery}
                        setQuery={setCohortQuery}
                        open={cohortPickerOpen}
                        setOpen={setCohortPickerOpen}
                        onSelect={selectCohort}
                      />
                      <RepositorySourceSelector
                        selectedCohort={selectedCohort}
                        datasets={cohortRepositoryDatasets}
                        selectedDataset={selectedRepositoryDataset}
                        onSelect={selectRepositoryDataset}
                      />
                      {selectedCohort && (
                        <div className="cohort-summary">
                          <div className="cohort-title">
                            <strong>
                              {selectedRepositoryDataset?.name
                                || getCohortName(selectedCohort.id)}
                            </strong>
                            <span>
                              {selectedRepositoryDataset?.source_accession
                                || selectedCohort.id}
                            </span>
                          </div>
                          <SummaryStat
                            label="RNA samples"
                            value={
                              selectedRepositoryDataset?.sample_count
                                ?? selectedCohort.n_samples_paired
                            }
                          />
                          <SummaryStat
                            label="Patients"
                            value={
                              selectedRepositoryDataset?.patient_count
                                ?? selectedCohort.n_patients_paired
                            }
                          />
                          <SummaryStat
                            label={selectedRepositoryDataset ? "Genes" : "Tumors"}
                            value={
                              selectedRepositoryDataset?.gene_count
                                ?? selectedCohort.n_primary_tumor
                            }
                          />
                          <p>
                            {selectedRepositoryDataset?.cohort_context
                              || selectedCohort.primary_site}
                          </p>
                        </div>
                      )}
                    </>
                  )}

                  {activeAnalysisStep.id === "genes" && (
                    <>
                      <PanelHeader iconRole="module.geneAnalysis" title="Gene analysis" help={HELP_CONTENT.analysisDesign} />
                      <div className="axis-control two-options">
                        <span>Analysis design</span>
                        <div>
                          {[
                            ["single_signature", "One signature"],
                            ["combined_signatures", "Two signatures"],
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
                      {!isCombinedMode ? (
                        <GeneSelector
                          label={form.signature_method === "single" ? "Gene symbols" : "Signature genes"}
                          value={form.gene_symbol}
                          onChange={(value) => updateForm("gene_symbol", value)}
                          draft={geneQuery}
                          setDraft={setGeneQuery}
                          suggestions={genes}
                          suggestionsLoading={geneSuggestionState.loading}
                          suggestionsError={geneSuggestionState.error}
                          placeholder={form.signature_method === "single" ? "Type TP53, KRAS, EGFR..." : "Type TP53, KRAS or TP53:1"}
                          help={
                            form.signature_method === "single"
                              ? "Select one or more genes. Each gene produces its own Kaplan-Meier plot."
                              : "Select genes for one combined expression signature. Weighted mode accepts GENE:weight."
                          }
                        />
                      ) : (
                        <CombinedSignatureBuilder
                          value={form.combined_signature}
                          onSignatureChange={updateCombinedSignature}
                          queries={combinedGeneQueries}
                          setQuery={updateCombinedGeneQuery}
                          suggestions={combinedGeneSuggestions}
                          suggestionStates={combinedGeneSuggestionStates}
                        />
                      )}
                      {!isCombinedMode && (
                        <div className="axis-control">
                          <LabelWithHelp
                            label="Gene mode"
                            help={`${SCORE_METHOD_GUIDE[form.signature_method]}${
                              form.signature_method === "zscore"
                                ? " This default is recommended for multi-gene signatures."
                                : ""
                            }`}
                          />
                          <div>
                            {[
                              ["single", "Single genes"],
                              ["mean", "Mean signature"],
                              ["zscore", "Z-score signature"],
                              ["weighted", "Weighted signature"],
                            ].map(([value, label]) => (
                              <button
                                key={value}
                                type="button"
                                className={form.signature_method === value ? "selected" : ""}
                                onClick={() => updateForm("signature_method", value)}
                                title={signatureHelp(value)}
                              >
                                {label}
                              </button>
                            ))}
                          </div>
                        </div>
                      )}
                    </>
                  )}

                  {activeAnalysisStep.id === "endpoint" && (
                    <>
                      <PanelHeader iconRole="module.survivalEndpoint" title="Survival endpoint" help={HELP_CONTENT.survivalEndpoint} />
                      <EndpointSelector
                        endpoints={endpointOptions}
                        selected={form.endpoint}
                        onSelect={(value) => updateForm("endpoint", value)}
                      />
                    </>
                  )}

                  {activeAnalysisStep.id === "groups" && (
                    <>
                      <PanelHeader
                        iconRole="module.stratification"
                        title="Expression & groups"
                        help={`${HELP_CONTENT.expressionScale} ${HELP_CONTENT.stratification}`}
                      />
                      <div className="analysis-step-subsection">
                        <LabelWithHelp label="RNA expression scale" help={HELP_CONTENT.expressionScale} />
                        <div className="scale-grid" aria-label="RNA expression scale">
                          {analysisExpressionScales.map((item) => (
                            <button
                              key={item.value}
                              type="button"
                              className={
                                (
                                  form.dataset_id
                                    ? form.expression_layer_id
                                    : form.expression_scale
                                ) === item.value
                                  ? "selected"
                                  : ""
                              }
                              onClick={() => selectExpressionScale(item.value)}
                            >
                              <strong>{item.label}</strong>
                            </button>
                          ))}
                        </div>
                      </div>
                      <div className="analysis-step-subsection">
                        <LabelWithHelp
                          label="Stratification"
                          help={
                            !isCombinedMode
                              ? `${HELP_CONTENT.stratification} ${CUTPOINT_GUIDE[form.cutpoint_method]}`
                              : form.combined_signature.grouping_method === "tertiles"
                                ? "Tertile crossing creates up to nine combined groups. Use it when the cohort has enough patients and events to avoid unstable strata."
                                : "Median crossing creates four balanced combined groups: Low_Low, Low_High, High_Low and High_High."
                          }
                        />
                        {!isCombinedMode ? (
                          <div className="method-grid">
                            {CUTPOINTS.map((item) => (
                              <button
                                key={item.value}
                                type="button"
                                className={form.cutpoint_method === item.value ? "selected" : ""}
                                onClick={() => updateForm("cutpoint_method", item.value)}
                                title={cutpointTooltip(item.value)}
                              >
                                <strong>{item.label}</strong>
                                <span>{item.help}</span>
                              </button>
                            ))}
                          </div>
                        ) : (
                          <div className="method-grid compact two">
                            {[
                              { value: "median", label: "Median x median", help: "Four combined groups: Low_Low through High_High" },
                              { value: "tertiles", label: "Tertiles x tertiles", help: "Up to nine combined Low/Mid/High groups" },
                            ].map((item) => (
                              <button
                                key={item.value}
                                type="button"
                                className={form.combined_signature.grouping_method === item.value ? "selected" : ""}
                                onClick={() => updateCombinedGroupingMethod(item.value)}
                              >
                                <strong>{item.label}</strong>
                                <span>{item.help}</span>
                              </button>
                            ))}
                          </div>
                        )}
                        {!isCombinedMode && form.cutpoint_method === "percentile" && (
                          <label className="field">
                            <span>Percentile threshold</span>
                            <input
                              type="number"
                              min="1"
                              max="99"
                              value={form.custom_percentile}
                              onChange={(event) => updateForm("custom_percentile", event.target.value)}
                            />
                            <small className="field-help">{CUTPOINT_GUIDE.percentile}</small>
                          </label>
                        )}
                      </div>
                    </>
                  )}

                  {activeAnalysisStep.id === "filters" && (
                    <>
                      <PanelHeader
                        iconRole="module.clinicalFilters"
                        title="Clinical design"
                        description="Define eligibility first, then choose the exact covariates for an additional Cox model."
                        help={`${HELP_CONTENT.clinicalFilters} ${HELP_CONTENT.clinicalAdjustment}`}
                      />
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
                            value={form.filters.age_min}
                            onChange={(event) => updateFilters("age_min", event.target.value)}
                            placeholder={filters?.age_min ? String(Math.floor(filters.age_min)) : ""}
                          />
                        </label>
                        <label className="field">
                          <span>Max age</span>
                          <input
                            value={form.filters.age_max}
                            onChange={(event) => updateFilters("age_max", event.target.value)}
                            placeholder={filters?.age_max ? String(Math.ceil(filters.age_max)) : ""}
                          />
                        </label>
                        <label className="field wide">
                          <span>Maximum follow-up days</span>
                          <input
                            value={form.filters.max_time_days}
                            onChange={(event) => updateFilters("max_time_days", event.target.value)}
                            placeholder={filters?.os_time_max_days ? String(Math.ceil(filters.os_time_max_days)) : ""}
                          />
                          <small className="field-help">{HELP_CONTENT.maxFollowup}</small>
                        </label>
                      </div>
                      <ClinicalAdjustmentSelector
                        selected={selectedAdjustmentCovariates}
                        filters={filters}
                        onToggle={toggleAdjustmentCovariate}
                        externalDataset={form.external_covariates}
                        externalSelected={selectedExternalAdjustmentCovariates}
                        onExternalChange={updateExternalAdjustment}
                      />
                    </>
                  )}

                  {activeAnalysisStep.id === "plot" && (
                    <>
                      <PanelHeader iconRole="module.plotOutput" title="Plot & run" help={HELP_CONTENT.plotOutput} />
                      <PlotOutputControls
                        form={form}
                        updateForm={updateForm}
                        updatePlotStyle={updatePlotStyle}
                        updateArtifactPlotStyle={updateArtifactPlotStyle}
                        updatePaletteColor={updatePaletteColor}
                        plotEditorTarget={isCombinedMode && plotEditorTarget === "continuous" ? "survival" : plotEditorTarget}
                        onPlotEditorTargetChange={setPlotEditorTarget}
                        supportsContinuous={!isCombinedMode}
                        plotTitlePlaceholder={`${plotCancerName} overall survival`}
                      />
                      <div className="analysis-final-review">
                        <strong>
                          {selectedCancerName} / {isCombinedMode ? "2 signatures" : runCount ? `${runCount} gene${runCount === 1 ? "" : "s"}` : "Gene pending"}
                        </strong>
                        <span>
                          {selectedEndpoint.label} · {selectedExpressionScale.label} · {previewCutpoint.label}
                          {activeFilterCount ? ` · ${activeFilterCount} filter${activeFilterCount === 1 ? "" : "s"}` : ""}
                          {` · ${formatAdjustmentSummary(
                            selectedAdjustmentCovariates,
                            selectedExternalAdjustmentCovariates,
                            form.external_covariates,
                          )}`}
                        </span>
                      </div>
                    </>
                  )}
                </section>

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

              <section
                ref={resultPanelRef}
                className={`result-panel${!analysisResults.length && !loading ? " previewing" : ""}`}
                aria-label="Analysis result"
              >
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
                    activeStep={analysisStep}
                    step={activeAnalysisStep}
                    cohort={selectedCohort}
                    repositoryDataset={selectedRepositoryDataset}
                    form={form}
                    isCombinedMode={isCombinedMode}
                    selectedGenes={selectedGenes}
                    signatureAGenes={selectedSignatureAGenes}
                    signatureBGenes={selectedSignatureBGenes}
                    endpoint={selectedEndpoint}
                    expressionScale={selectedExpressionScale}
                    cutpoint={previewCutpoint}
                    activeFilterCount={activeFilterCount}
                    plotEditorTarget={isCombinedMode && plotEditorTarget === "continuous" ? "survival" : plotEditorTarget}
                    plotTitlePlaceholder={`${plotCancerName} overall survival`}
                  />
                )}

                {loading && (
                  <LoadingState
                    cohort={form.cohort}
                    gene={isCombinedMode ? `${form.combined_signature.signature_a.name} x ${form.combined_signature.signature_b.name}` : form.gene_symbol}
                    analysisKind={form.analysis_kind}
                    signatureMethod={form.signature_method}
                    geneCount={runCount}
                    completedCount={analysisResults.length}
                    endpoint={selectedEndpoint}
                    expressionScale={selectedExpressionScale}
                  />
                )}
                {!!analysisResults.length && <AnalysisResults analyses={analysisResults} onDownload={startDownload} />}
              </section>
            </div>
          </>
        ) : activePage === "compare" ? (
          <CompareAnalyses
            form={form}
            cohorts={cohorts}
            visibleCohorts={visibleCohorts}
            selectedCohort={selectedCohort}
            selectedCohortId={form.cohort}
            cohortQuery={cohortQuery}
            setCohortQuery={setCohortQuery}
            cohortPickerOpen={cohortPickerOpen}
            setCohortPickerOpen={setCohortPickerOpen}
            onSelectCohort={selectCohort}
            repositoryDatasets={cohortRepositoryDatasets}
            selectedRepositoryDataset={selectedRepositoryDataset}
            onSelectRepositoryDataset={selectRepositoryDataset}
            endpointOptions={endpointOptions}
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
            canRun={Boolean(form.cohort && selectedEndpoint.available)}
            onDownload={startDownload}
          />
        ) : activePage === "multiverse" ? (
          <MultiverseAnalysis
            state={multiverse}
            setState={setMultiverse}
            form={form}
            cohorts={cohorts}
            visibleCohorts={visibleCohorts}
            selectedCohort={selectedCohort}
            cohortQuery={cohortQuery}
            setCohortQuery={setCohortQuery}
            cohortPickerOpen={cohortPickerOpen}
            setCohortPickerOpen={setCohortPickerOpen}
            onSelectCohort={selectCohort}
            repositoryDatasets={cohortRepositoryDatasets}
            selectedRepositoryDataset={selectedRepositoryDataset}
            onSelectRepositoryDataset={selectRepositoryDataset}
            endpointOptions={endpointOptions}
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
            form={form}
            endpointOptions={endpointOptions}
            expressionScales={expressionScales}
            onDownload={startDownload}
            onPlotDownload={startPlotDownload}
          />
        ) : activePage === "examples" ? (
          <PaperExamplesPage
            catalog={paperExamples.data}
            loading={paperExamples.loading}
            error={paperExamples.error}
            onRetry={() => setPaperExamples({ data: null, loading: false, error: "" })}
          />
        ) : activePage === "repository" ? (
          <RepositoryCatalog
            coverage={repositoryCoverage}
            datasets={repositoryDatasets}
            onAnalyze={analyzeRepositoryDataset}
            onDownload={startDownload}
          />
        ) : activePage === "summary" ? (
          <DatasetSummary
            summary={datasetSummary}
            health={health}
            dataSources={dataSources}
            cohorts={cohorts}
            summaryCohort={summaryCohort}
            setSummaryCohort={setSummaryCohort}
          />
        ) : activePage === "api" ? (
          <ApiMcpPage />
        ) : (
          <HelpMethodsPage health={health} />
        )}
        </div>
      </section>
      <DownloadNotifications notices={downloadNotices} onDismiss={dismissDownloadNotice} />
    </main>
  );
}

function HomePage({ health, summary, repositoryCoverage, onNavigate }) {
  const totals = summary?.totals || {};
  const assetBase = import.meta.env.BASE_URL;
  const workspaceModules = [
    {
      page: "analysis",
      iconRole: "navigation.analysis",
      title: "Survival by gene or signature",
      description: "Explore one or more genes, build signatures, and review Kaplan-Meier, Cox and RMST results.",
    },
    {
      page: "compare",
      iconRole: "navigation.compare",
      title: "Compare grouping methods",
      description: "Run the same marker with several cutpoints and see which findings remain consistent.",
    },
    {
      page: "pancancer",
      iconRole: "navigation.panCancer",
      title: "Look across cancer types",
      description: "Estimate the effect in each cohort and review FDR, heterogeneity and clinical adjustment.",
    },
    {
      page: "repository",
      iconRole: "module.cohortResults",
      title: "Validate in an independent cohort",
      description: `${formatInteger(repositoryCoverage?.datasets || 0)} curated bulk RNA-seq ${repositoryCoverage?.datasets === 1 ? "study" : "studies"} currently pass expression and survival QC.`,
    },
    {
      page: "methods",
      iconRole: "navigation.methods",
      title: "Read the methods",
      description: "See how scores, endpoints and models are defined, and what changed between releases.",
    },
  ];

  return (
    <div className="home-page">
      <section className="home-hero" aria-labelledby="home-title">
        <div className="home-hero-trace" aria-hidden="true">
          <span />
          <span />
          <span />
          <span />
          <span />
        </div>
        <div className="home-hero-copy">
          <p className="home-kicker">Explore survival patterns in TCGA</p>
          <div className="home-title-lockup">
            <TraceLogo animated />
            <h1 id="home-title">TCGA-TRACE</h1>
          </div>
          <p className="home-lede">
            Explore how gene expression relates to survival across 33 TCGA cancer cohorts.
            Build an analysis, compare grouping choices and keep a clear record of every result.
          </p>
          <div className="home-actions">
            <button type="button" className="primary-button home-primary-action" onClick={() => onNavigate("analysis")}>
              <TraceIcon role="action.run" size="sm" />
              Build an analysis
            </button>
            <button type="button" className="secondary-button home-secondary-action" onClick={() => onNavigate("examples")}>
              <TraceIcon role="document.reference" size="sm" />
              See worked examples
            </button>
          </div>
        </div>

        <dl className="home-data-strip" aria-label="Current TCGA-TRACE data coverage">
          <div>
            <dt>Cancer cohorts</dt>
            <dd>{formatInteger(totals.cohorts ?? health?.cohorts ?? 33)}</dd>
          </div>
          <div>
            <dt>Patients</dt>
            <dd>{formatInteger(totals.patients)}</dd>
          </div>
          <div>
            <dt>RNA samples</dt>
            <dd>{formatInteger(totals.samples)}</dd>
          </div>
          <div>
            <dt>Survival endpoints</dt>
            <dd>4</dd>
          </div>
        </dl>
      </section>

      <section className="home-workspace-index" aria-labelledby="home-workspace-title">
        <header className="home-section-heading">
          <div>
            <p className="eyebrow">Start here</p>
            <h2 id="home-workspace-title">What do you want to explore?</h2>
          </div>
          <p>
            Work with one cohort, compare cutpoints side by side or follow a marker across
            cancer types.
          </p>
        </header>
        <div className="home-module-grid">
          {workspaceModules.map((module) => (
            <button
              key={module.page}
              type="button"
              className="home-module"
              onClick={() => onNavigate(module.page === "methods" ? "help" : module.page)}
            >
              <ModuleIcon role={module.iconRole} frame="section" />
              <span>
                <strong>{module.title}</strong>
                <span>{module.description}</span>
              </span>
              <TraceIcon role="action.next" size="sm" />
            </button>
          ))}
        </div>
      </section>

      <section className="home-foundation" aria-labelledby="home-foundation-title">
        <div className="home-foundation-copy">
          <p className="eyebrow">Reproducibility</p>
          <h2 id="home-foundation-title">See what went into every result</h2>
          <p>
            TCGA-TRACE records the cohort, endpoint, expression scale, patient selection,
            model settings and software versions behind each analysis. You can download that
            record with the result.
          </p>
          <div className="home-method-trace" aria-label="Analysis record sequence">
            <span>Expression data</span>
            <i aria-hidden="true" />
            <span>One sample per patient</span>
            <i aria-hidden="true" />
            <span>Survival analysis</span>
            <i aria-hidden="true" />
            <span>Downloadable record</span>
          </div>
          <small>For research use only. Findings should be validated in independent data.</small>
        </div>

        <div className="home-institutions">
          <p className="eyebrow">Institutions</p>
          <div className="home-logo-row">
            <div className="home-combined-logo">
              <img
                src={`${assetBase}institutions/uss-cienciavida.png`}
                alt="Universidad San Sebastián and Fundación Ciencia & Vida"
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
      </section>
    </div>
  );
}

function RepositoryCatalog({ coverage, datasets, onAnalyze, onDownload }) {
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const cancers = coverage?.cancers || [];
  const normalizedQuery = query.trim().toLowerCase();
  const visibleCancers = cancers.filter((cancer) => {
    const matchesStatus = statusFilter === "all"
      || cancer.coverage_status === statusFilter;
    const matchesQuery = !normalizedQuery
      || [
        cancer.code,
        cancer.tcga_cohort,
        cancer.name,
        cancer.primary_site,
        cancer.search?.review_note,
        ...(cancer.search?.candidates || []).flatMap((candidate) => [
          candidate.accession,
          candidate.review_note,
        ]),
      ].some((value) => String(value || "").toLowerCase().includes(normalizedQuery));
    return matchesStatus && matchesQuery;
  });
  const datasetById = new Map(datasets.map((dataset) => [dataset.id, dataset]));

  return (
    <div className="repository-page">
      <section className="repository-overview" aria-labelledby="repository-overview-title">
        <div>
          <p className="eyebrow">Curated evidence</p>
          <h2 id="repository-overview-title">Independent bulk RNA-seq cohorts</h2>
          <p>
            Each published release fixes its expression matrix, endpoint definition,
            sample mapping, license and QC result.
          </p>
        </div>
        <dl className="repository-kpis">
          <div>
            <dt>Cancer types</dt>
            <dd>{formatInteger(coverage?.total_cancer_types || 33)}</dd>
          </div>
          <div>
            <dt>Available</dt>
            <dd>{formatInteger(coverage?.available_cancer_types || 0)}</dd>
          </div>
          <div>
            <dt>Studies</dt>
            <dd>{formatInteger(coverage?.datasets || 0)}</dd>
          </div>
          <div>
            <dt>Evidence gaps</dt>
            <dd>{formatInteger(coverage?.evidence_gaps || 0)}</dd>
          </div>
        </dl>
      </section>

      <section className="repository-releases" aria-labelledby="repository-releases-title">
        <header className="repository-section-heading">
          <div>
            <p className="eyebrow">Published releases</p>
            <h2 id="repository-releases-title">Survival-ready datasets</h2>
          </div>
        </header>
        <div className="repository-release-list">
          {datasets.map((dataset) => (
            <article key={dataset.id} className="repository-release">
              <header>
                <div>
                  <span>{dataset.cancer_code} · {dataset.source_accession}</span>
                  <h3>{dataset.name}</h3>
                </div>
                <span className="repository-qc-status">QC passed</span>
              </header>
              <p>{dataset.cohort_context || dataset.description}</p>
              <div className="repository-expression-note">
                <strong>
                  Expression: {dataset.expression_layer?.label || "Release-defined layer"}
                </strong>
                {dataset.expression_layer?.scale_note && (
                  <p>{dataset.expression_layer.scale_note}</p>
                )}
              </div>
              <dl>
                <div>
                  <dt>Patients</dt>
                  <dd>{formatInteger(dataset.patient_count)}</dd>
                </div>
                <div>
                  <dt>RNA samples</dt>
                  <dd>{formatInteger(dataset.sample_count)}</dd>
                </div>
                <div>
                  <dt>Genes</dt>
                  <dd>{formatInteger(dataset.gene_count)}</dd>
                </div>
                <div>
                  <dt>License</dt>
                  <dd>{dataset.license_id}</dd>
                </div>
              </dl>
              <div className="repository-release-meta">
                <span>{dataset.publication_citation}</span>
                <code title={dataset.manifest_hash}>
                  {dataset.manifest_hash?.slice(0, 14)}…
                </code>
              </div>
              <footer>
                <button
                  type="button"
                  className="primary-button"
                  onClick={() => onAnalyze(dataset.id)}
                >
                  <TraceIcon role="action.run" size="sm" />
                  Analyze
                </button>
                <details className="repository-download-menu">
                  <summary className="secondary-button">
                    <TraceIcon role="action.download" size="sm" />
                    Release files
                  </summary>
                  <div>
                    {[
                      ["manifest", "Manifest", "file.audit"],
                      ["qc", "QC report", "status.success"],
                      ["license", "License", "file.text"],
                      ...(dataset.redistribution_allowed
                        ? [
                            ["matrix", "Expression matrix", "data.expression"],
                            ["matrix-metadata", "Matrix metadata", "file.audit"],
                            ["genes", "Gene index", "data.table"],
                          ]
                        : []),
                    ].map(([kind, label, iconRole]) => (
                      <button
                        key={kind}
                        type="button"
                        onClick={(event) => {
                          event.currentTarget.closest("details")?.removeAttribute("open");
                          onDownload(
                            `/api/v1/datasets/${encodeURIComponent(dataset.id)}/download/${kind}?expression_layer_id=${encodeURIComponent(dataset.expression_layer?.layer_id || "")}`,
                            `${dataset.id} ${label}`,
                          );
                        }}
                      >
                        <TraceIcon role={iconRole} size="sm" />
                        {label}
                      </button>
                    ))}
                  </div>
                </details>
                <a
                  className="repository-source-link"
                  href={dataset.source_url}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  Source
                  <TraceIcon role="action.next" size="sm" />
                </a>
              </footer>
            </article>
          ))}
          {!datasets.length && (
            <div className="empty-inline">No external release currently passes repository QC.</div>
          )}
        </div>
      </section>

      <section className="repository-coverage" aria-labelledby="repository-coverage-title">
        <header className="repository-section-heading">
          <div>
            <p className="eyebrow">Coverage ledger</p>
            <h2 id="repository-coverage-title">All 33 TCGA cancer types</h2>
          </div>
          <div className="repository-catalog-controls">
            <label className="search-field">
              <TraceIcon role="action.search" size="sm" />
              <span className="sr-only">Search cancer types</span>
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Cancer, site or TCGA code"
              />
            </label>
            <div className="repository-status-filter" aria-label="Coverage status">
              {[
                ["all", "All"],
                ["available", "Available"],
                ["search_in_progress", "Reviewing"],
                ["evidence_gap", "Evidence gaps"],
              ].map(([value, label]) => (
                <button
                  key={value}
                  type="button"
                  aria-pressed={statusFilter === value}
                  className={statusFilter === value ? "selected" : ""}
                  onClick={() => setStatusFilter(value)}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>
        </header>
        <div className="repository-cancer-grid">
          {visibleCancers.map((cancer) => {
            const availableDatasets = (cancer.datasets || [])
              .map((id) => datasetById.get(id))
              .filter(Boolean);
            const status = cancer.coverage_status;
            const screenedCandidates = Number(
              cancer.search?.discovery?.candidate_count || 0,
            );
            const gapReason = status === "evidence_gap"
              ? cancer.search?.review_note
              : null;
            const gapLeads = status === "evidence_gap"
              ? (cancer.search?.candidates || [])
                .map((candidate) => candidate.accession)
                .filter(Boolean)
              : [];
            return (
              <article key={cancer.code} data-status={status}>
                <header>
                  <span>{cancer.code}</span>
                  <strong>{cancer.name}</strong>
                </header>
                <div className="repository-cancer-context">
                  <p>{cancer.primary_site}</p>
                  {gapReason && <small>{gapReason}</small>}
                  {gapLeads.length > 0 && (
                    <span className="repository-gap-leads">
                      Reviewed: {gapLeads.join(" · ")}
                    </span>
                  )}
                </div>
                <footer>
                  <span className={`repository-coverage-status ${status}`}>
                    {status === "available"
                      ? `${availableDatasets.length} available`
                      : status === "evidence_gap"
                        ? "Evidence gap"
                        : screenedCandidates
                          ? `${screenedCandidates} screened`
                          : "Search in progress"}
                  </span>
                  {availableDatasets[0] && (
                    <button
                      type="button"
                      onClick={() => onAnalyze(availableDatasets[0].id)}
                    >
                      Analyze
                      <TraceIcon role="action.next" size="sm" />
                    </button>
                  )}
                </footer>
              </article>
            );
          })}
        </div>
        {!visibleCancers.length && (
          <div className="empty-inline">No cancer types match the selected filter.</div>
        )}
      </section>
    </div>
  );
}

function TraceLogo({ animated = false }) {
  return (
    <span className={`brand-mark${animated ? " is-acquiring" : ""}`} aria-hidden="true">
      <TraceIcon role="data.gene" size="lg" className="brand-helix" />
      <span className="brand-survival-trace">
        <i />
        <i />
        <i />
        <i />
        <i />
      </span>
      <span className="brand-acquisition-node" />
    </span>
  );
}

function StatusItem({ iconRole, label, value }) {
  return (
    <div className="status-item">
      <ModuleIcon role={iconRole} frame="compact" />
      <span className="status-label">{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function HelpButton({ label, children }) {
  const id = useId();
  const rootRef = useRef(null);
  const triggerRef = useRef(null);
  const cardRef = useRef(null);
  const [open, setOpen] = useState(false);

  useLayoutEffect(() => {
    if (!open || !cardRef.current || !triggerRef.current) return;

    function positionCard() {
      const card = cardRef.current;
      const trigger = triggerRef.current;
      card.style.setProperty("--popover-left", "0px");
      const rootBox = rootRef.current.getBoundingClientRect();
      const triggerBox = trigger.getBoundingClientRect();
      const cardWidth = card.offsetWidth;
      const viewportMargin = 12;
      let shift = 0;
      if (rootBox.left + cardWidth > window.innerWidth - viewportMargin) {
        shift = window.innerWidth - viewportMargin - rootBox.left - cardWidth;
      }
      if (rootBox.left + shift < viewportMargin) {
        shift += viewportMargin - (rootBox.left + shift);
      }
      const finalLeft = rootBox.left + shift;
      const origin = Math.min(
        cardWidth - 12,
        Math.max(12, triggerBox.left + triggerBox.width / 2 - finalLeft),
      );
      card.style.setProperty("--popover-left", `${shift}px`);
      card.style.setProperty("--popover-origin-x", `${origin}px`);
    }

    positionCard();
    window.addEventListener("resize", positionCard);
    return () => window.removeEventListener("resize", positionCard);
  }, [open]);

  useEffect(() => {
    if (!open) return;
    function closeOnOutsidePointer(event) {
      if (!rootRef.current?.contains(event.target)) setOpen(false);
    }
    document.addEventListener("pointerdown", closeOnOutsidePointer);
    return () => document.removeEventListener("pointerdown", closeOnOutsidePointer);
  }, [open]);

  return (
    <span
      ref={rootRef}
      className="help-popover"
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => {
        if (!rootRef.current?.contains(document.activeElement)) setOpen(false);
      }}
    >
      <IconButton
        ref={triggerRef}
        iconRole="status.info"
        label={`Explain ${label}`}
        tooltip={`Explain ${label}`}
        iconSize="sm"
        size="md"
        className="help-trigger"
        aria-expanded={open}
        aria-controls={id}
        aria-describedby={open ? id : undefined}
        onFocus={() => setOpen(true)}
        onBlur={(event) => {
          if (!rootRef.current?.contains(event.relatedTarget)) setOpen(false);
        }}
        onClick={(event) => {
          event.stopPropagation();
          setOpen((current) =>
            window.matchMedia("(hover: none)").matches ? !current : true,
          );
        }}
        onKeyDown={(event) => {
          if (event.key === "Escape") {
            setOpen(false);
          }
        }}
      />
      <span
        ref={cardRef}
        id={id}
        role="tooltip"
        className="help-card"
        data-open={open ? "true" : "false"}
        aria-hidden={!open}
      >
        {children}
      </span>
    </span>
  );
}

function LabelWithHelp({ label, help }) {
  return (
    <span className="label-with-help">
      <span>{label}</span>
      <HelpButton label={label}>{help}</HelpButton>
    </span>
  );
}

function PanelHeader({ iconRole, title, description, help }) {
  return (
    <div className="panel-header">
      <ModuleIcon role={iconRole} />
      <div>
        <div className="panel-title-row">
          <h2>{title}</h2>
          {help && <HelpButton label={title}>{help}</HelpButton>}
        </div>
        {description && <p>{description}</p>}
      </div>
    </div>
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
  cohorts,
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
              : `${formatInteger(cohorts.length)} TCGA cohorts available`}
          </small>
        </span>
        <TraceIcon role="action.expand" size="md" />
      </button>

      <div
        className="cohort-menu"
        data-open={open ? "true" : "false"}
        aria-hidden={!open}
        inert={!open ? "" : undefined}
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
              placeholder="Search cancer name, TCGA code, site or disease"
            />
          </label>
          <div className="cohort-count">
            Showing {formatInteger(visibleCohorts.length)} of {formatInteger(cohorts.length)}
          </div>
          <div id="cohort-picker-list" className="cohort-browser" role="listbox" aria-label="Available TCGA cohorts">
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
}) {
  if (!selectedCohort) return null;
  return (
    <section className="repository-source-selector" aria-labelledby="analysis-source-label">
      <div className="repository-source-heading">
        <span id="analysis-source-label">Analysis source</span>
        <strong>
          {selectedDataset ? "Independent cohort" : "TCGA"}
        </strong>
      </div>
      <div className="repository-source-options" role="radiogroup" aria-label="Analysis dataset">
        <button
          type="button"
          role="radio"
          aria-checked={!selectedDataset}
          className={!selectedDataset ? "selected" : ""}
          onClick={() => onSelect(null)}
        >
          <span className="repository-source-code">TCGA</span>
          <strong>{getCohortName(selectedCohort.id)}</strong>
          <small>
            {formatInteger(selectedCohort.n_patients_paired)} linked patients
          </small>
        </button>
        {datasets.map((dataset) => (
          <button
            key={dataset.id}
            type="button"
            role="radio"
            aria-checked={selectedDataset?.id === dataset.id}
            className={selectedDataset?.id === dataset.id ? "selected" : ""}
            onClick={() => onSelect(dataset.id)}
          >
            <span className="repository-source-code">
              {dataset.source_accession}
            </span>
            <strong>{dataset.name}</strong>
            <small>
              {formatInteger(dataset.patient_count)} patients · {dataset.release_version}
            </small>
            <small>
              {dataset.expression_layer?.label || "Release-defined expression"}
            </small>
          </button>
        ))}
      </div>
      {!datasets.length && (
        <p className="repository-source-gap">
          No curated independent RNA-seq cohort is available for this cancer yet.
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

function ClinicalAdjustmentSelector({
  selected,
  filters,
  onToggle,
  externalDataset = null,
  externalSelected = [],
  onExternalChange = () => {},
}) {
  const totalSelected = selected.length + externalSelected.length;
  return (
    <section className="clinical-adjustment-selector" aria-label="Cox clinical adjustment">
      <div className="clinical-section-heading">
        <div>
          <LabelWithHelp label="Cox adjustment" help={HELP_CONTENT.clinicalAdjustment} />
          <small>
            One additional complete-case model uses exactly the checked fields.
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
      <ExternalCovariateEditor
        dataset={externalDataset}
        selected={externalSelected}
        onChange={onExternalChange}
      />
      <p>
        Complete-case adjustment can reduce patients and events. Each result reports model-specific N, events, fitted parameters and EPV.
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
            <strong>CSV contract</strong>
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
                step="any"
                value={definition.effect_unit}
                onChange={(event) => {
                  const value = Number(event.target.value);
                  if (Number.isFinite(value) && value > 0) {
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
              ? COMPETING_RISK_HELP
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
  label,
  value,
  onChange,
  draft,
  setDraft,
  suggestions,
  suggestionsLoading = false,
  suggestionsError = "",
  placeholder,
  help,
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

  function handleBlur() {
    if (!draft.trim()) return;
    const symbol = geneSymbolFromToken(draft);
    if (suggestions.some((gene) => gene.toUpperCase() === symbol)) {
      commitToken(draft);
    }
  }

  return (
    <div className="gene-selector">
      <div className="gene-selector-header">
        <span>{label}</span>
        {!!tokens.length && (
          <button type="button" onClick={() => onChange("")}>
            Clear all
          </button>
        )}
      </div>
      <div className="gene-autocomplete-wrap">
        <div className="gene-token-box">
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
                  onMouseDown={(event) => event.preventDefault()}
                  onClick={() => onChange(removeGeneToken(value, symbol))}
                />
              </span>
            );
          })}
          <input
            value={draft}
            onChange={handleInputChange}
            onKeyDown={handleKeyDown}
            onBlur={handleBlur}
            placeholder={tokens.length ? "Add gene..." : placeholder}
            aria-label={label}
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
      <small className="field-help">{help}</small>
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
}) {
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
              placeholder="Type IFNG, CXCL9, GZMB..."
              help="Select genes for this signature. Weighted mode accepts GENE:weight."
            />
              <div className="axis-control">
                <LabelWithHelp label="Score method" help={SCORE_METHOD_GUIDE[signature.signature_method]} />
              <div>
                {[
                  ["single", "Single"],
                  ["mean", "Mean"],
                  ["zscore", "Z-score"],
                  ["weighted", "Weighted"],
                ].map(([method, label]) => (
                  <button
                    key={method}
                    type="button"
                    className={signature.signature_method === method ? "selected" : ""}
                    onClick={() => onSignatureChange(signatureKey, { signature_method: method })}
                    title={signatureHelp(method)}
                  >
                    {label}
                    </button>
                  ))}
                </div>
            </div>
          </div>
        );
      })}
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
  const artifactOptions = PLOT_ARTIFACT_OPTIONS.filter(
    (option) => supportsContinuous || option.value !== "continuous",
  );
  const activeArtifact =
    artifactOptions.some((option) => option.value === plotEditorTarget)
      ? plotEditorTarget
      : "survival";
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
          help={HELP_CONTENT.plotOutput}
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
                ? "Separate mode creates one univariable figure and one figure containing every completed adjusted model. The combined file remains in the reproducibility bundle for compatibility."
                : "Point and interval colors follow the estimated direction. Model names, group contrast, estimates, confidence intervals and p-values remain data-derived."}
            </p>
          </>
        )}
      </div>

      <div className="plot-style-shared">
        <div>
          <strong>Shared typography</strong>
          <span>Applied consistently to all exported plots.</span>
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
                help="Aspect ratio is shared by the Survival and Continuous Cox plots."
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
            />
          </label>
          <label className="field">
            <span>Axis values size</span>
            <input
              type="number"
              min="6"
              max="24"
              value={plotStyle.axis_text_size}
              onChange={(event) => updatePlotStyle("axis_text_size", event.target.value)}
            />
          </label>
          <label className="field">
            <span>Axis titles size</span>
            <input
              type="number"
              min="6"
              max="26"
              value={plotStyle.axis_title_size}
              onChange={(event) => updatePlotStyle("axis_title_size", event.target.value)}
            />
          </label>
          <SwitchField
            label="Plot grid"
            checked={plotStyle.show_grid}
            onChange={(checked) => updatePlotStyle("show_grid", checked)}
          />
          {activeArtifact === "cox_forest" && (
            <p className="plot-control-note wide">
              Forest height adapts to the number of completed Cox models.
            </p>
          )}
        </div>
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
  onDownload,
}) {
  const selectedMethods = compare.methods;
  const [compareStep, setCompareStep] = useState(0);
  const [compareGeneQuery, setCompareGeneQuery] = useState("");
  const compareGeneSuggestionState = useGeneSuggestions(
    suggestionCohort,
    compareGeneQuery,
    form.dataset_id,
    form.dataset_release_id,
    form.expression_layer_id,
  );
  const compareGeneSuggestions = compareGeneSuggestionState.genes;
  const compareStepPanelRef = useRef(null);
  const effectiveCompareInput = compareGeneQuery.trim() ? addGeneToken(compare.genes, compareGeneQuery) : compare.genes;
  const genes = uniqueGeneSymbols(effectiveCompareInput);
  const adjusted = useMemo(() => adjustCompareResults(compare.results), [compare.results]);
  const selectedCutpoints = cutpoints.filter((item) => selectedMethods.includes(item.value));
  const missingRequirements = [];
  if (!form.cohort) missingRequirements.push("select a cancer cohort");
  if (form.cohort && !canRun) missingRequirements.push("select an available survival endpoint");
  if (!genes.length) missingRequirements.push("add at least one gene");
  if (!selectedMethods.length) missingRequirements.push("select at least one method");
  const canRunSelectedMethods = canRun && genes.length > 0 && selectedMethods.length > 0 && !compare.running;
  const canRunAllDichotomizations = canRun && genes.length > 0 && !compare.running;
  const selectedDichotomizationCount = selectedMethods.filter((method) => DICHOTOMIZATION_METHODS.includes(method)).length;
  const compareCoreReady = Boolean(form.cohort && selectedEndpoint.available);
  const compareStepCompletion = [
    compareCoreReady,
    genes.length > 0,
    selectedMethods.length > 0,
    compareCoreReady && genes.length > 0 && selectedMethods.length > 0,
    canRunSelectedMethods,
  ];
  const compareStepRequirements = [
    !form.cohort
      ? "Select a cancer cohort to continue."
      : selectedEndpoint.available
        ? ""
        : "Choose an endpoint that passes cohort QC.",
    genes.length ? "" : "Add at least one gene.",
    selectedMethods.length ? "" : "Select at least one cutpoint method.",
    compareCoreReady && genes.length && selectedMethods.length
      ? ""
      : "Complete Dataset, Markers and Methods first.",
    canRunSelectedMethods ? "" : "Complete the required cohort, endpoint, gene and method selections.",
  ];
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
        .getElementById(`compare-step-${COMPARE_WORKFLOW_STEPS[boundedStep].id}`)
        ?.scrollIntoView({ behavior: "auto", block: "nearest", inline: "center" });
      compareStepPanelRef.current
        ?.closest(".compare-step-controls")
        ?.scrollIntoView({ behavior: "auto", block: "start" });
    });
  }

  async function runCompare(methodOverride = null) {
    const methodsToRun = methodOverride || selectedMethods;
    if (!canRun || !genes.length || !methodsToRun.length) {
      setCompare((current) => ({
        ...current,
        error: `Cannot run comparison: ${missingRequirements.join(", ") || "check inputs"}.`,
      }));
      return;
    }
    const normalizedGenes = uniqueGeneSymbols(effectiveCompareInput);
    setCompareGeneQuery("");
    setCompare((current) => ({
      ...current,
      methods: methodsToRun,
      genes: normalizedGenes.join(", "),
      running: true,
      error: "",
      results: [],
    }));
    try {
      const jobs = normalizedGenes.flatMap((gene) =>
        methodsToRun.map((method) => {
          const basePayload = buildAnalysisPayload({ ...form, gene_symbol: gene, signature_method: "single" });
          return {
            gene,
            method,
            payload: {
              ...basePayload,
              gene_symbol: gene,
              signature_method: "single",
              signature_genes: [],
              cutpoint_method: method,
              custom_percentile: method === "percentile" ? Number(form.custom_percentile) : null,
            },
          };
        }),
      );
      const batch = await createAnalysesBatch(jobs.map((job) => job.payload), ANALYSIS_BATCH_CONCURRENCY);
      const results = batch.results.map((item) => {
        const job = jobs[item.index];
        return {
          gene: job.gene,
          method: job.method,
          result: item.status === "completed" ? item.result : null,
          error: item.status === "failed" ? formatBatchItemError(item) : null,
        };
      });
      setCompare((current) => ({
        ...current,
        results,
        error: batch.failed ? `${batch.failed} comparison${batch.failed === 1 ? "" : "s"} failed; see matrix cells.` : "",
      }));
    } catch (err) {
      setCompare((current) => ({ ...current, error: formatError(err) }));
    } finally {
      setCompare((current) => ({ ...current, running: false }));
    }
  }

  return (
    <section className="compare-page">
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

          <section
            ref={compareStepPanelRef}
            className="analysis-step-panel compare-step-panel"
            id={`compare-step-panel-${activeCompareStep.id}`}
            aria-labelledby={`compare-step-${activeCompareStep.id}`}
            tabIndex={-1}
          >
          {activeCompareStep.id === "dataset" && (
            <>
            <PanelHeader
              iconRole="module.comparisonDataset"
              title="Dataset and endpoint"
              description="Shared cohort, outcome and expression scale for every matrix cell."
              help={HELP_CONTENT.compare}
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
                />
              </div>
              <div className="compare-control-block">
                <div className="compare-control-label">
                  <LabelWithHelp label="Survival endpoint" help={HELP_CONTENT.survivalEndpoint} />
                  <strong>{selectedEndpoint.available ? "Available" : "Unavailable"}</strong>
                </div>
                <EndpointSelector
                  endpoints={endpointOptions}
                  selected={form.endpoint}
                  onSelect={onSelectEndpoint}
                />
              </div>
              <div className="compare-control-block wide">
                <div className="compare-control-label">
                  <LabelWithHelp label="RNA expression scale" help={HELP_CONTENT.expressionScale} />
                  <strong>{expressionScale.label}</strong>
                </div>
                <div className="scale-grid" aria-label="RNA expression scale">
                  {expressionScales.map((item) => (
                    <button
                      key={item.value}
                      type="button"
                      className={expressionScaleValue === item.value ? "selected" : ""}
                      onClick={() => onSelectExpressionScale(item.value)}
                    >
                      <strong>{item.label}</strong>
                    </button>
                  ))}
                </div>
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
              help={HELP_CONTENT.compareRobustness}
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
                help="Select genes for the comparison matrix. Each selected gene becomes one row."
              />
            </div>
            </>
          )}

          {activeCompareStep.id === "methods" && (
            <>
            <PanelHeader
              iconRole="module.markersCutpoints"
              title="Cutpoint methods"
              description="Each selected stratification method defines one matrix column."
              help={HELP_CONTENT.compareRobustness}
            />
            <div className="compare-method-panel">
              <div className="compare-control-label">
                <LabelWithHelp label="Cutpoint methods" help={HELP_CONTENT.compareRobustness} />
                <strong>{selectedMethods.length} selected / {selectedDichotomizationCount} dichotomizing</strong>
              </div>
              <div className="method-grid compact">
                {cutpoints.map((item) => (
                  <button
                    key={item.value}
                    type="button"
                    className={selectedMethods.includes(item.value) ? "selected" : ""}
                    onClick={() => toggleMethod(item.value)}
                    title={cutpointTooltip(item.value)}
                  >
                    <strong>{item.label}</strong>
                    <span>{item.help}</span>
                  </button>
                ))}
              </div>
              <label className="field compare-percentile-field">
                <span>Percentile threshold</span>
                <input
                  type="number"
                  min="1"
                  max="99"
                  value={form.custom_percentile}
                  onChange={(event) => updateForm("custom_percentile", event.target.value)}
                />
                <small className="field-help">{CUTPOINT_GUIDE.percentile}</small>
              </label>
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
                title="Clinical design"
                description="Apply one eligibility definition and one prespecified adjustment model to every matrix cell."
                help={`${HELP_CONTENT.clinicalFilters} ${HELP_CONTENT.clinicalAdjustment}`}
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
                      value={form.filters.age_min}
                      onChange={(event) => updateFilters("age_min", event.target.value)}
                      placeholder={filters?.age_min ? String(Math.floor(filters.age_min)) : ""}
                    />
                  </label>
                  <label className="field">
                    <span>Max age</span>
                    <input
                      value={form.filters.age_max}
                      onChange={(event) => updateFilters("age_max", event.target.value)}
                      placeholder={filters?.age_max ? String(Math.ceil(filters.age_max)) : ""}
                    />
                  </label>
                  <label className="field wide">
                    <span>Maximum follow-up days</span>
                    <input
                      value={form.filters.max_time_days}
                      onChange={(event) => updateFilters("max_time_days", event.target.value)}
                      placeholder={filters?.os_time_max_days ? String(Math.ceil(filters.os_time_max_days)) : ""}
                    />
                  </label>
                </div>
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
                help={HELP_CONTENT.plotOutput}
              />
              <PlotOutputControls
                form={form}
                updateForm={updateForm}
                updatePlotStyle={updatePlotStyle}
                updateArtifactPlotStyle={updateArtifactPlotStyle}
                updatePaletteColor={updatePaletteColor}
                plotEditorTarget={plotEditorTarget}
                onPlotEditorTargetChange={onPlotEditorTargetChange}
                plotTitlePlaceholder={`${selectedCohort ? getCohortName(selectedCohort.id) : "Cancer"} comparison`}
              />
              <div className="analysis-final-review">
                <strong>Multiple-testing scope</strong>
                <span>BH and Bonferroni correction are calculated across every successfully completed cell in this run.</span>
              </div>
            </>
          )}
          </section>

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
          />
        </section>
      </div>
      {compare.error && <div className="error-box"><TraceIcon role="status.error" size="md" tone="error" /><span>{compare.error}</span></div>}
      <ContinuousReferenceSummary rows={adjusted} onDownload={onDownload} />
      <ComparePlotMatrix
        rows={adjusted}
        genes={genes}
        methods={selectedCutpoints}
        running={compare.running}
        onDownload={onDownload}
      />
      <CutpointRobustnessSummary rows={adjusted} methods={cutpoints} />
      <div className="method-note">
        These comparisons are exploratory. Multiple-testing adjustment is applied to the displayed set only and does not replace external validation.
      </div>
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
}) {
  const titles = {
    dataset: cohort ? "Shared analysis frame" : "Choose a cohort",
    markers: genes.length ? "Matrix rows" : "Add molecular markers",
    methods: methods.length ? "Comparison design" : "Choose matrix columns",
    filters: activeFilterCount ? "Restricted clinical design" : "Clinical design",
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
          <p>Up to {ANALYSIS_BATCH_CONCURRENCY} analyses run in parallel. Completed cells will populate the evidence matrix below.</p>
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
              <PreviewItem label="RNA scale" value={expressionScale?.label || "Pending"} />
            </div>
          </div>
        ) : (
          <PreviewPrompt
            iconRole="module.dataset"
            title="Select one TCGA cancer"
            text="Every cell in the comparison matrix uses the same cohort, endpoint and expression scale."
          />
        )
      )}

      {step.id === "markers" && (
        <div className="analysis-context-preview">
          <div className="analysis-preview-lead">
            <span>{genes.length ? `${genes.length} matrix row${genes.length === 1 ? "" : "s"}` : "Rows pending"}</span>
            <h3>Independent gene analyses</h3>
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
          <PlotStylePreview
            form={form}
            isCombinedMode={false}
            plotTitlePlaceholder={`${genes[0] || "Gene"} · ${methods[0]?.label || "Cutpoint method"}`}
            previewContext="compare"
            previewGene={genes[0] || "Gene"}
            previewMethod={methods[0]?.label || "Cutpoint method"}
            previewTarget={plotEditorTarget}
          />
          <div className="compare-execution-facts">
            <PreviewItem label="Analyses" value={formatInteger(jobCount)} />
            <PreviewItem label="Parallel jobs" value={ANALYSIS_BATCH_CONCURRENCY} />
            <PreviewItem label="Multiplicity" value="BH + Bonferroni" />
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
        <p>Rows remain biologically independent; columns test sensitivity to patient stratification.</p>
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

function ContinuousReferenceSummary({ rows, onDownload }) {
  const byGene = new Map();
  rows.forEach((row) => {
    const continuous = row.result?.metrics?.continuous_analysis;
    if (continuous?.status !== "completed") return;
    const primary = findCoxModel(continuous.linear_models, "continuous_univariable");
    const adjusted = downstreamAdjustedContinuousModel(continuous.linear_models);
    const candidate = {
      gene: row.gene,
      continuous,
      primary,
      adjusted,
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
      <DetailSectionTitle
        title="Continuous reference"
        help="One cutpoint-independent model is shown per gene. It uses the full expression-complete eligible population and provides the reference against which grouped cutpoint results are compared."
      />
      <table>
        <thead>
          <tr>
            <th>Gene</th>
            <th>n / events</th>
            <th>HR per +1 SD</th>
            <th>Linear p</th>
            <th>Adjusted HR</th>
            <th>Nonlinearity p</th>
            <th>Marker PH p</th>
            <th>Profile</th>
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
                {formatHrValues(item.adjusted)}
                <small className="table-secondary">
                  {item.adjusted ? formatContinuousModelLabel(item.adjusted) : "Not evaluable"}
                </small>
              </td>
              <td>{formatP(item.spline?.nonlinearity_p_value)}</td>
              <td>{formatP(item.adjusted?.ph_p_value ?? item.primary?.ph_p_value)}</td>
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
      <div className="method-note">
        Repeated cutpoint cells for the same gene must reproduce this reference. Outer quartiles may reduce grouped n, but cannot change the continuous population.
      </div>
    </section>
  );
}

function ComparePlotMatrix({ rows, genes, methods, running, onDownload }) {
  if (!rows.length && !running) {
    return <div className="empty-plot"><ModuleIcon role="module.cohortTable" /><p>Comparison results will appear after running multiple genes or cutpoint methods.</p></div>;
  }
  const rowByKey = Object.fromEntries(rows.map((row) => [`${row.gene}::${row.method}`, row]));
  return (
    <div className="compare-matrix-scroll">
      <table className="compare-matrix-table">
        <thead>
          <tr>
            <th>Gene</th>
            {methods.map((method) => (
              <th key={method.value}>
                <strong>{method.label}</strong>
                <span>{method.help}</span>
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
        <span>p {formatP(metrics.logrank_p_value)}</span>
        <span>BH {formatP(row.bh)}</span>
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
      <table>
        <thead>
          <tr>
            <th>Gene</th>
            <th>Method</th>
            <th>n / events</th>
            <th>Group sizes</th>
            <th>BH q</th>
            <th>Univariable HR</th>
            <th>Adjusted HR</th>
            <th>RMST Δ at tau</th>
            <th>Marker PH p</th>
            <th>Prespecified 2-year effect</th>
            <th>Model PH p</th>
            <th>Direction</th>
            <th>Interpretation notes</th>
          </tr>
        </thead>
        <tbody>
          {summarized.map((row) => {
            const metrics = row.result.metrics || {};
            const profile = row.evidenceProfile;
            const univariable = findCoxModel(metrics.cox_models, "univariable");
            const adjustedModel = downstreamAdjustedModel(metrics.cox_models);
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
                  {formatHrValues(adjustedModel)}
                  <small className="table-secondary">
                    {adjustedModel ? `${formatCoxModelLabel(adjustedModel)} · p ${formatP(adjustedModel.p_value)}` : "Not evaluable"}
                  </small>
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
                  {formatP(adjustedModel?.ph_p_value)}
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
                  {formatP(adjustedModel?.ph_global_p_value)}
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
      <div className="method-note">
        {`These grouped estimates are sensitivity analyses against the continuous reference above. BH q-values describe the completed comparison family. Log-rank, grouped Cox and RMST are related summaries of the same outcomes and are not counted as independent votes. Marker-specific PH and global model PH are interpretation diagnostics, not exclusion rules. Maxstat is outcome-optimized; its grouped HR, confidence interval and RMST remain post-selection.`}
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
}) {
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
  const effectiveGeneInput = geneQuery.trim()
    ? addGeneToken(state.genes, geneQuery)
    : state.genes;
  const genes = uniqueGeneSymbols(effectiveGeneInput);
  const selectedEndpoints = state.endpoints || [];
  const selectedScoring = state.scoring_methods || [];
  const selectedCutpoints = state.cutpoint_methods || [];
  const planned = selectedEndpoints.length * selectedScoring.length * selectedCutpoints.length;
  const markerReady = genes.length === 1
    ? selectedScoring.length === 1 && selectedScoring[0] === "single"
    : genes.length > 1 && selectedScoring.length > 0 && !selectedScoring.includes("single");
  const canRun = Boolean(
    form.cohort
      && genes.length
      && selectedEndpoints.length
      && selectedScoring.length
      && selectedCutpoints.length
      && markerReady
      && planned <= 72
      && !state.running,
  );
  const completion = [
    Boolean(form.cohort && selectedEndpoints.length),
    markerReady,
    Boolean(selectedScoring.length && selectedCutpoints.length && planned <= 72),
    Boolean(form.cohort && markerReady && selectedEndpoints.length && selectedCutpoints.length),
    canRun,
  ];
  const requirements = [
    !form.cohort
      ? "Select a cancer cohort."
      : selectedEndpoints.length
        ? ""
        : "Select at least one endpoint that passes cohort QC.",
    !genes.length
      ? "Add one gene or a multi-gene signature."
      : markerReady
        ? ""
        : "Use single scoring for one gene or signature scoring for two or more genes.",
    !selectedScoring.length
      ? "Select at least one scoring method."
      : !selectedCutpoints.length
        ? "Select at least one cutpoint method."
        : planned > 72
          ? "Reduce the family to 72 specifications or fewer."
          : "",
    form.cohort && markerReady && selectedEndpoints.length && selectedCutpoints.length
      ? ""
      : "Complete Dataset, Marker and Decisions first.",
    canRun ? "" : "Complete the declared family before execution.",
  ];
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
    const required = genes.length <= 1 ? ["single"] : ["mean", "zscore"];
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
        .getElementById(`multiverse-step-${MULTIVERSE_WORKFLOW_STEPS[bounded].id}`)
        ?.scrollIntoView({ behavior: "auto", block: "nearest", inline: "center" });
    });
  }

  async function runMultiverse() {
    if (!canRun) {
      setState((current) => ({
        ...current,
        error: requirements.find(Boolean) || "The multiverse design is incomplete.",
      }));
      return;
    }
    const normalizedInput = geneInputTokens(effectiveGeneInput).join(", ");
    const base = buildAnalysisPayload({ ...form, gene_symbol: normalizedInput });
    const payload = {
      cohort: form.cohort,
      dataset_id: form.dataset_id || null,
      dataset_release_id: form.dataset_release_id || null,
      expression_layer_id: form.expression_layer_id || null,
      genes: parseSignatureGenes(normalizedInput),
      signature_name: genes.length > 1 ? state.session_label.trim() : "",
      endpoints: selectedEndpoints,
      scoring_methods: selectedScoring,
      cutpoint_methods: selectedCutpoints,
      expression_scale: form.expression_scale,
      custom_percentile: Number(form.custom_percentile),
      filters: base.filters,
      adjustment_covariates: [...new Set(form.adjustment_covariates || [])],
      external_covariates: form.external_covariates || null,
      external_adjustment_covariates: [
        ...new Set(form.external_adjustment_covariates || []),
      ],
      time_unit: form.time_unit,
      show_confidence_interval: form.show_confidence_interval,
      plot_style: base.plot_style,
      session_label: state.session_label.trim(),
    };
    setGeneQuery("");
    setState((current) => ({
      ...current,
      genes: normalizedInput,
      running: true,
      result: null,
      error: "",
    }));
    try {
      const result = await createMultiverseAnalysis(payload);
      setState((current) => ({ ...current, result, error: "" }));
    } catch (error) {
      setState((current) => ({ ...current, error: formatError(error) }));
    } finally {
      setState((current) => ({ ...current, running: false }));
    }
  }

  return (
    <section className="multiverse-page">
      <div className="layout analysis-workflow-layout multiverse-workflow-layout">
        <section className="control-panel analysis-step-controls multiverse-step-controls" aria-label="Prespecified multiverse controls">
          <AnalysisWorkflowStepper
            steps={MULTIVERSE_WORKFLOW_STEPS}
            activeStep={step}
            completion={completion}
            summary={summary}
            onSelect={navigateStep}
            idPrefix="multiverse-step"
            ariaLabel="Prespecified multiverse setup"
            summaryLabel="Declared family"
          />
          <section
            ref={stepPanelRef}
            className="analysis-step-panel multiverse-step-panel"
            id={`multiverse-step-panel-${activeStep.id}`}
            aria-labelledby={`multiverse-step-${activeStep.id}`}
            tabIndex={-1}
          >
            {activeStep.id === "dataset" && (
              <>
                <PanelHeader
                  iconRole="module.comparisonDataset"
                  title="Cohort and endpoints"
                  description="Select every outcome that belongs to this analysis family before execution."
                  help={HELP_CONTENT.multiverse}
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
                    />
                  </div>
                  <div className="compare-control-block wide">
                    <div className="compare-control-label">
                      <LabelWithHelp label="Endpoint family" help={HELP_CONTENT.survivalEndpoint} />
                      <strong>{selectedEndpoints.length} selected</strong>
                    </div>
                    <div className="multiverse-option-grid endpoint-family" aria-label="Endpoint family">
                      {endpointOptions.map((endpoint) => (
                        <button
                          key={endpoint.value}
                          type="button"
                          aria-pressed={selectedEndpoints.includes(endpoint.value)}
                          className={selectedEndpoints.includes(endpoint.value) ? "selected" : ""}
                          disabled={!endpoint.available}
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
                  help={HELP_CONTENT.geneMode}
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
                    help="Use GENE:weight syntax when weighted scoring is part of the family."
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
                  title="Analytical decisions"
                  description="The Cartesian product below is frozen as one family when execution starts."
                  help={HELP_CONTENT.multiverse}
                />
                <div className="multiverse-decision-stack">
                  <div className="compare-method-panel">
                    <div className="compare-control-label">
                      <LabelWithHelp label="Scoring methods" help={HELP_CONTENT.geneMode} />
                      <strong>{selectedScoring.length} selected</strong>
                    </div>
                    <div className="multiverse-option-grid" aria-label="Signature scoring methods">
                      {(genes.length <= 1
                        ? [{ value: "single", label: "Single gene", help: SCORE_METHOD_GUIDE.single }]
                        : [
                            { value: "mean", label: "Mean", help: SCORE_METHOD_GUIDE.mean },
                            { value: "zscore", label: "Z-score", help: SCORE_METHOD_GUIDE.zscore },
                            { value: "weighted", label: "Weighted", help: SCORE_METHOD_GUIDE.weighted },
                          ]).map((method) => (
                        <button
                          key={method.value}
                          type="button"
                          aria-pressed={selectedScoring.includes(method.value)}
                          className={selectedScoring.includes(method.value) ? "selected" : ""}
                          onClick={() => toggleScoring(method.value)}
                        >
                          <strong>{method.label}</strong>
                          <span>{method.help}</span>
                        </button>
                      ))}
                    </div>
                  </div>
                  <div className="compare-method-panel">
                    <div className="compare-control-label">
                      <LabelWithHelp label="Cutpoint methods" help={HELP_CONTENT.compareRobustness} />
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
                          title={cutpointTooltip(method.value)}
                        >
                          <strong>{method.label}</strong>
                          <span>{method.help}</span>
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
                          onChange={(event) => updateForm("custom_percentile", event.target.value)}
                        />
                      </label>
                    )}
                  </div>
                  <div className="compare-control-block wide">
                    <div className="compare-control-label">
                      <LabelWithHelp label="RNA expression scale" help={HELP_CONTENT.expressionScale} />
                      <strong>{expressionScales.find((item) => item.value === expressionScaleValue)?.label}</strong>
                    </div>
                    <div className="scale-grid" aria-label="RNA expression scale">
                      {expressionScales.map((item) => (
                        <button
                          key={item.value}
                          type="button"
                          aria-pressed={expressionScaleValue === item.value}
                          className={expressionScaleValue === item.value ? "selected" : ""}
                          onClick={() => onSelectExpressionScale(item.value)}
                        >
                          <strong>{item.label}</strong>
                        </button>
                      ))}
                    </div>
                  </div>
                </div>
              </>
            )}

            {activeStep.id === "clinical" && (
              <>
                <PanelHeader
                  iconRole="module.clinicalFilters"
                  title="Clinical design"
                  description="One eligibility rule and one exact adjustment specification apply to the complete family."
                  help={`${HELP_CONTENT.clinicalFilters} ${HELP_CONTENT.clinicalAdjustment}`}
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
                      <input value={form.filters.age_min} onChange={(event) => updateFilters("age_min", event.target.value)} />
                    </label>
                    <label className="field">
                      <span>Max age</span>
                      <input value={form.filters.age_max} onChange={(event) => updateFilters("age_max", event.target.value)} />
                    </label>
                    <label className="field wide">
                      <span>Maximum follow-up days</span>
                      <input value={form.filters.max_time_days} onChange={(event) => updateFilters("max_time_days", event.target.value)} />
                    </label>
                  </div>
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
                  description={`${planned} planned specifications, with all failures retained in the ledger.`}
                  help={HELP_CONTENT.multiverse}
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
          <span>{state.error}</span>
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
          {running ? "Running family" : "Run multiverse"}
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
          <span>{running ? "Executing frozen family" : "Declared analysis family"}</span>
          <h2>
            {cohort
              ? `${repositoryDataset?.source_accession || cohort.id} specification curve`
              : "Build a prespecified family"}
          </h2>
        </div>
        {running && <TraceIcon role="status.loading" size="lg" className="spin" label="Running multiverse" />}
      </header>
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
          ? "Execution freezes the full grid and records completed, unavailable and failed cells."
          : "This preview describes the planned family; no result is omitted after execution."}
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
  return (
    <section className="multiverse-results" aria-label="Prespecified multiverse result">
      <header className="multiverse-result-header">
        <div>
          <span>Session <code>{result.session_id}</code></span>
          <h2>Specification family completed</h2>
          <p>{summary.completed} completed and {summary.failed} failed or unavailable of {summary.planned} planned specifications.</p>
        </div>
        <span className={`evidence-badge ${summary.failed ? "caution" : "informative"}`}>
          {summary.failed ? "Completed with gaps" : "Complete ledger"}
        </span>
      </header>
      <div className="multiverse-result-actions" aria-label="Multiverse downloads">
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
          <span>Continuous primary family</span>
          <strong>{summary.continuous_tests} evaluable</strong>
          <small>{family.primary_continuous_family?.unit}</small>
        </div>
        <div>
          <span>Grouped sensitivity family</span>
          <strong>{summary.grouped_tests} evaluable</strong>
          <small>{family.grouped_sensitivity_family?.unit}</small>
        </div>
        <div>
          <span>Family hash</span>
          <code>{result.audit?.family_reproducibility_hash?.slice(0, 18)}…</code>
          <small>No retained/not-retained rule</small>
        </div>
      </div>
      <AnalysisNotices
        warnings={result.warnings}
        includeModelDiagnostics={false}
      />

      <section className="detail-section multiverse-continuous">
        <DetailSectionTitle
          title="Continuous primary family"
          help="Each endpoint and scoring method appears once. Repeated cutpoints must reproduce the same expression-complete continuous model and patient hash."
        />
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Endpoint</th>
                <th>Scoring</th>
                <th>n / events</th>
                <th>Model</th>
                <th>HR per +1 SD</th>
                <th>p</th>
                <th>BH q</th>
                <th>Marker PH p</th>
                <th>Information</th>
              </tr>
            </thead>
            <tbody>
              {references.map((reference) => {
                const effect = reference.effect || {};
                return (
                  <tr key={reference.reference_id}>
                    <th scope="row">{reference.endpoint}</th>
                    <td>{formatLabel(reference.scoring_method)}</td>
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

      <section className="detail-section multiverse-curve-section">
        <DetailSectionTitle
          title="Grouped specification curve"
          help="Specifications are sorted by displayed grouped log hazard ratio. Filled points have grouped-family BH q values at or below 0.05; crosses mark non-estimable effects."
        />
        <div className="multiverse-curve-scroll">
          <img
            src={apiUrl(downloads.svg)}
            alt={`Specification curve for ${summary.completed} completed of ${summary.planned} planned analyses`}
          />
        </div>
      </section>

      <section className="detail-section multiverse-ledger-section">
        <DetailSectionTitle
          title="Execution ledger"
          help="Every planned cell remains visible, including endpoint QC failures and models that were not evaluable."
        />
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Spec</th>
                <th>Endpoint</th>
                <th>Scoring</th>
                <th>Cutpoint</th>
                <th>n / events</th>
                <th>Inference p</th>
                <th>BH q</th>
                <th>Displayed effect</th>
                <th>RMST Δ / tau</th>
                <th>Marker / model PH</th>
                <th>Status</th>
                <th>Audit</th>
              </tr>
            </thead>
            <tbody>
              {specifications.map((row) => {
                const effect = row.grouped_effect || {};
                return (
                  <tr key={row.specification_id}>
                    <th scope="row"><code>{row.specification_id}</code></th>
                    <td>{row.endpoint}</td>
                    <td>{formatLabel(row.scoring_method)}</td>
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
      <div className="method-note">
        Continuous and grouped p-values are related summaries of the same outcomes and are not votes. Maxstat grouped HR and RMST remain post-selection. PH tests modify interpretation and never remove a specification from this ledger.
      </div>
    </section>
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
    <section className="session-history-page" aria-label="Exploratory run history">
      <section className="session-control-band">
        <header className="session-title-row">
          <PanelHeader
            iconRole="module.sessionHistory"
            title="Exploratory run history"
            description="Local record of accepted compute jobs and their export-defined statistical families."
            help="This history is post hoc. It does not replace the prespecified Multiverse module and cannot prove that unrecorded analyses did not occur."
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
          No patient records or uploaded covariate rows are stored here. The server receives only selected job references when an export is requested.
        </p>
      </section>

      {exportState.error && (
        <div className="error-box">
          <TraceIcon role="status.error" size="md" tone="error" />
          <span>{exportState.error}</span>
        </div>
      )}

      <section className="detail-section session-run-ledger">
        <DetailSectionTitle
          title="Recorded runs"
          help="Every accepted frontend compute request has one event. Repeated cached runs remain separate events; exact duplicate hypotheses are deduplicated only in the exported statistical family."
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
                ? "Accepted Survival, Compare, Multiverse and Pan-cancer jobs will appear here."
                : "Enable recording when a session-level exploratory record is required."}
            </span>
          </div>
        ) : (
          <div className="table-scroll">
            <table className="session-run-table">
              <thead>
                <tr>
                  <th className="session-select-column">Export</th>
                  <th>Run</th>
                  <th>Design</th>
                  <th>Status</th>
                  <th>Recorded</th>
                  <th>Server job</th>
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
      </section>

      {exportState.result && (
        <ExploratorySessionResult
          result={exportState.result}
          onDownload={onDownload}
        />
      )}
    </section>
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
      <div className="table-scroll">
        <table className="session-family-table">
          <thead>
            <tr>
              <th>Export-defined family</th>
              <th>Unique</th>
              <th>Evaluable</th>
              <th>p-value contract</th>
              <th>Multiplicity</th>
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
        This export describes only the selected post hoc history. Multiverse and Pan-cancer results retain their own internal families and are not counted again.
      </div>
    </section>
  );
}

function formatMultiverseEffect(effect) {
  const hazardRatio = Number(effect?.display_hazard_ratio);
  const low = Number(effect?.display_hr_conf_low);
  const high = Number(effect?.display_hr_conf_high);
  if (![hazardRatio, low, high].every(Number.isFinite)) return "Not estimable";
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
  const epp = Number(effect?.events_per_parameter);
  if (!status && !Number.isFinite(epp)) return "Not evaluable";
  return `${formatLabel(status || "unknown")}${Number.isFinite(epp) ? ` · ${epp.toFixed(1)} EPP` : ""}`;
}

function PanCancerSurvival({ state, setState, updateState, cohorts, form, expressionScales, onDownload, onPlotDownload }) {
  const effectiveGeneInput = state.geneQuery.trim() ? addGeneToken(state.gene_symbol, state.geneQuery) : state.gene_symbol;
  const genes = uniqueGeneSymbols(effectiveGeneInput);
  const indexCohort = state.index_cohort || form.cohort || cohorts[0]?.id || "";
  const selectedExpressionScale =
    expressionScales.find((item) => item.value === state.expression_scale) || EXPRESSION_SCALE_FALLBACK[0];
  const selectedEndpointMode =
    PANCANCER_ENDPOINT_MODES.find((item) => item.value === state.endpoint_mode) || PANCANCER_ENDPOINT_MODES[0];
  const canRun = Boolean(indexCohort && genes.length === 1 && !state.running);

  function useCurrentKmInputs() {
    setState((current) => ({
      ...current,
      gene_symbol: geneInputTokens(form.gene_symbol).slice(0, 1).join(", "),
      geneQuery: "",
      index_cohort: form.cohort || current.index_cohort,
      endpoint: form.endpoint || current.endpoint,
      expression_scale: form.expression_scale || current.expression_scale,
      result: null,
      error: "",
    }));
  }

  async function runScan() {
    if (!canRun) return;
    setState((current) => ({
      ...current,
      gene_symbol: genes[0],
      geneQuery: "",
      running: true,
      result: null,
      error: "",
    }));
    try {
      const payload = {
        gene_symbol: genes[0],
        index_cohort: indexCohort,
        endpoint: state.endpoint,
        endpoint_mode: state.endpoint_mode,
        expression_scale: state.expression_scale,
        min_patients: Number(state.min_patients) || 10,
        min_events: Number(state.min_events) || 5,
        fdr_threshold: Number(state.fdr_threshold) || 0.1,
        filters: {
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

  return (
    <section className="pancancer-page">
      <ImmunePanCancerAtlas
        screen={state.immuneScreen}
        loading={state.immuneScreenLoading}
        error={state.immuneScreenError}
        onDownload={onDownload}
        onPlotDownload={onPlotDownload}
      />

      <div className="pancancer-controls">
        <div className="pancancer-control-panel">
          <PanelHeader
            iconRole="module.panCancerQuery"
            title="Pan-cancer query"
            description="Run one continuous Cox model per TCGA cancer using expression z-scored inside each cohort."
            help={HELP_CONTENT.pancancer}
          />
          <div className="download-row">
            <button type="button" onClick={useCurrentKmInputs}>
              Use current KM inputs
            </button>
          </div>
          <label className="field">
            <span>Index cancer</span>
            <select value={indexCohort} onChange={(event) => updateState("index_cohort", event.target.value)}>
              {cohorts.map((cohort) => (
                <option key={cohort.id} value={cohort.id}>
                  {getCohortLabel(cohort.id)}
                </option>
              ))}
            </select>
          </label>
          <GeneSelector
            label="Gene symbol"
            value={state.gene_symbol}
            onChange={(value) => updateState("gene_symbol", value)}
            draft={state.geneQuery}
            setDraft={(value) => updateState("geneQuery", value)}
            suggestions={state.geneSuggestions}
            placeholder="Type TP53, KRAS, EGFR..."
            help="Use exactly one gene for a cross-cancer concordance scan."
          />
          {genes.length > 1 && (
            <div className="method-note">Pan-cancer concordance currently accepts one gene per scan.</div>
          )}
        </div>

        <div className="pancancer-control-panel">
          <PanelHeader
            iconRole="module.outcomeModel"
            title="Outcome model"
            description="Select the reference endpoint and how similar endpoints are allowed across cohorts."
            help={HELP_CONTENT.pancancerEndpointMode}
          />
          <div className="range-grid">
            <label className="field">
              <span>Reference endpoint</span>
              <select value={state.endpoint} onChange={(event) => updateState("endpoint", event.target.value)}>
                {PANCANCER_ENDPOINTS.map((endpoint) => (
                  <option key={endpoint.value} value={endpoint.value}>
                    {endpoint.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>Expression scale</span>
              <select value={state.expression_scale} onChange={(event) => updateState("expression_scale", event.target.value)}>
                {expressionScales.map((scale) => (
                  <option key={scale.value} value={scale.value}>
                    {scale.label}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <div className="method-grid compact">
            {PANCANCER_ENDPOINT_MODES.map((item) => (
              <button
                key={item.value}
                type="button"
                className={state.endpoint_mode === item.value ? "selected" : ""}
                onClick={() => updateState("endpoint_mode", item.value)}
              >
                <strong>{item.label}</strong>
                <span>{item.help}</span>
              </button>
            ))}
          </div>
          <div className="parameter-note">{HELP_CONTENT.pancancerEndpointMode}</div>
          <div className="range-grid">
            <label className="field">
              <span>Min patients</span>
              <input
                type="number"
                min="10"
                value={state.min_patients}
                onChange={(event) => updateState("min_patients", event.target.value)}
              />
              <small className="field-help">Minimum analyzable patients required for each cohort-specific Cox model.</small>
            </label>
            <label className="field">
              <span>Min events</span>
              <input
                type="number"
                min="5"
                value={state.min_events}
                onChange={(event) => updateState("min_events", event.target.value)}
              />
              <small className="field-help">Minimum observed endpoint events required before a cohort is modeled.</small>
            </label>
            <label className="field wide">
              <span>FDR threshold</span>
              <input
                type="number"
                min="0.01"
                max="1"
                step="0.01"
                value={state.fdr_threshold}
                onChange={(event) => updateState("fdr_threshold", event.target.value)}
              />
              <small className="field-help">Benjamini-Hochberg threshold used to flag significant pan-cancer Cox associations.</small>
            </label>
          </div>
          <div className="run-summary static">
            <div>
              <span>Scan scope</span>
              <strong>{genes.length === 1 ? `${genes[0]} across ${formatInteger(cohorts.length)} cancers` : "One gene required"}</strong>
              <small>{selectedEndpointMode.label}; {selectedExpressionScale.label}; Cox HR per +1 SD expression.</small>
            </div>
            <button className="primary-button" onClick={runScan} disabled={!canRun}>
              {state.running ? <TraceIcon role="status.loading" size="md" className="spin" /> : <TraceIcon role="action.run" size="md" />}
              Run pan-cancer scan
            </button>
          </div>
        </div>
      </div>

      {state.error && <div className="error-box"><TraceIcon role="status.error" size="md" tone="error" /><span>{state.error}</span></div>}
      {state.running && (
        <div className="loading-state compact">
          <TraceIcon role="status.loading" size="lg" className="spin" label="Running pan-cancer scan" />
          <div>
            <p className="eyebrow">Running pan-cancer Cox scan</p>
            <h2>{genes[0] || state.gene_symbol || "Gene"} across TCGA cohorts</h2>
            <span>Preparing one patient-level model per cancer, then adjusting p-values and summarizing concordance.</span>
          </div>
        </div>
      )}
      {!state.running && !state.result && !state.error && (
        <div className="empty-plot">
          <ModuleIcon role="module.panCancerQuery" />
          <p>Pan-cancer concordance results will appear here after running a single-gene scan.</p>
        </div>
      )}
      {state.result && <PanCancerResults result={state.result} onDownload={onDownload} onPlotDownload={onPlotDownload} />}
    </section>
  );
}

function PanCancerResults({ result, onDownload, onPlotDownload }) {
  const summary = result.summary || {};
  const randomEffect = result.meta_analysis?.random_effect || {};
  const heterogeneity = result.meta_analysis?.heterogeneity || {};
  const predictionInterval = result.meta_analysis?.prediction_interval || {};
  const sensitivity = result.clinical_sensitivity || {};
  return (
    <div className="pancancer-results">
      <div className="analysis-result">
        <div className="result-header">
          <div>
            <p className="eyebrow">{result.scan_id} {result.cached ? "/ cached" : ""}</p>
            <h2>{result.gene_symbol} pan-cancer survival concordance</h2>
          </div>
          <div className="download-row">
            <DownloadLink href={result.downloads?.csv} iconRole="file.csv" label="CSV" onDownload={onDownload} />
            <DownloadLink href={result.downloads?.methodology} iconRole="file.text" label="Methods" onDownload={onDownload} />
            <DownloadLink href={result.downloads?.audit_html} iconRole="file.audit" label="Audit" onDownload={onDownload} />
            <DownloadLink href={result.downloads?.attestation} iconRole="file.audit" label="Signed receipt" onDownload={onDownload} />
            <DownloadLink href={result.downloads?.zip} iconRole="file.archive" label="Bundle" onDownload={onDownload} />
          </div>
        </div>
        <div className="metric-strip pancancer-kpis">
          <Metric label="Primary models" value={`${formatInteger(summary.completed)} / ${formatInteger(summary.total_cohorts)}`} />
          <Metric label="Primary FDR hits" value={formatInteger(summary.significant)} />
          <Metric label="Common-scale meta HR" value={randomEffect.hazard_ratio ? formatHrValues(randomEffect) : "Not pooled"} />
          <Metric label="95% prediction interval" value={formatPredictionInterval(predictionInterval)} />
          <Metric label="Primary I2" value={formatPercent(heterogeneity.i_squared)} />
        </div>
        <AnalysisNotices warnings={result.warnings} includeModelDiagnostics={false} />
      </div>

      <div className="pancancer-layout">
        {sensitivity.available && (
          <PanCancerSensitivityPanel
            sensitivity={sensitivity}
            rows={result.results || []}
            scanId={result.scan_id}
            onPlotDownload={onPlotDownload}
          />
        )}
        <section className="summary-panel">
          <PanelHeader
            iconRole="module.forest"
            title="Forest plot"
            description="Inspect descriptive per-cohort effects or the transportable input-score scale used for cross-cancer synthesis."
          />
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
        <section className="summary-panel wide">
          <PanelHeader
            iconRole="module.concordance"
            title="Concordance map"
            description="Interactive cohort-level concordance, evidence strength and model-readiness relative to the selected index cancer."
          />
          <PanCancerConcordanceMap
            rows={result.results || []}
            summary={summary}
            reference={result.reference}
            fdrThreshold={result.fdr_threshold}
          />
        </section>
        <section className="summary-panel wide">
          <PanelHeader
            iconRole="module.evidence"
            title="Evidence landscape"
            description="Each cohort is positioned by effect size and FDR evidence; the horizontal line marks the selected FDR threshold."
          />
          <PlotDownloadButtons
            svgSelector=".pancancer-landscape"
            filenameBase={`${result.scan_id}.evidence_landscape`}
            onPlotDownload={onPlotDownload}
          />
          <PanCancerEvidenceLandscape rows={result.results || []} fdrThreshold={result.fdr_threshold} />
        </section>
        <section className="summary-panel wide">
          <PanelHeader
            iconRole="module.precision"
            title="Power and precision map"
            description="Cohorts farther right and higher have more survival events and tighter Cox estimates."
          />
          <PlotDownloadButtons
            svgSelector=".pancancer-power"
            filenameBase={`${result.scan_id}.power_precision`}
            onPlotDownload={onPlotDownload}
          />
          <PanCancerPowerPrecision rows={result.results || []} />
        </section>
        <section className="summary-panel wide">
          <PanelHeader
            iconRole="module.cohortResults"
            title="Cohort results"
            description="Primary and ordinal-adjusted estimates remain side by side; missing covariates are marked not evaluable, not failed."
          />
          <PanCancerTable rows={result.results || []} />
        </section>
      </div>
    </div>
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
        description="Does the continuous expression signal persist after ordinary ordinal adjustment for stage and grade?"
      />
      <div className="sensitivity-estimands">
        <div>
          <span>Cohort models</span>
          <strong>Expression z-score + covariates</strong>
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
    <div className="pancancer-sensitivity-wrap">
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
        <text className="sensitivity-axis-title" x={(plot.left + width - plot.right) / 2} y={height - 3}>Hazard ratio per +1 SD expression</text>
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
            description="Strongest one-cancer signals; useful for tissue-specific follow-up rather than pan-cancer claims."
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
    <div className="immune-recurrence-wrap">
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
      && Number.isFinite(Number(row.common_scale_hazard_ratio)),
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
      return row.status === "completed" && Number.isFinite(Number(value));
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
      <div className="pancancer-forest-scroll">
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
    <div className="pancancer-chart-wrap">
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
    <div className="pancancer-chart-wrap">
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
    const aFdr = Number.isFinite(Number(a.fdr)) ? Number(a.fdr) : Number.POSITIVE_INFINITY;
    const bFdr = Number.isFinite(Number(b.fdr)) ? Number(b.fdr) : Number.POSITIVE_INFINITY;
    return aFdr - bFdr || String(a.cohort).localeCompare(String(b.cohort));
  });
  return (
    <div className="table-scroll pancancer-table-scroll">
      <table>
        <thead>
          <tr>
            <th>Cohort</th>
            <th>Endpoint</th>
            <th>Primary n / events</th>
            <th>Primary HR</th>
            <th>Primary FDR</th>
            <th>Ordinal model</th>
            <th>Adjusted n / events</th>
            <th>Adjusted HR</th>
            <th>Adjusted FDR</th>
            <th>Concordance</th>
            <th>Sensitivity readout</th>
          </tr>
        </thead>
        <tbody>
          {ordered.map((row) => (
            <tr key={row.cohort}>
              <td><strong>{row.cohort}</strong><br /><span>{getCohortName(row.cohort)}</span></td>
              <td>{row.endpoint || "..."}<br /><span>{formatSourceLabel(row.endpoint_source)}</span></td>
              <td>{row.status === "completed" ? `${formatInteger(row.n_patients)} / ${formatInteger(row.n_events)}` : "..."}</td>
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
            <small key={field.name}>{field.name}: {field.distribution?.slice(0, 3).map((item) => `${item.label} (${item.count})`).join(", ") || "present"}</small>
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
      <table>
        <thead>
          <tr>
            <th>Cohort</th>
            <th>Endpoint</th>
            <th>Source</th>
            <th>Patients</th>
            <th>Events</th>
            <th>Status</th>
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
          <TraceIcon role="status.loading" size="lg" className="spin" label="Loading paper examples" />
          <div>
            <p className="eyebrow">Reproducible paper examples</p>
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
          <div className="example-filter" aria-label="Filter paper cases">
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
              <p className="eyebrow">Secondary analysis</p>
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
        <div className="advanced-example-tabs" role="tablist" aria-label="Advanced paper examples">
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
              <table>
                <thead>
                  <tr>
                    <th>Percentile</th>
                    <th>HR</th>
                    <th>95% CI</th>
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
    <section className="access-page">
      <div className="access-grid">
        <article className="access-card">
          <PanelHeader
            iconRole="module.api"
            title="REST API v1"
            description="Documented endpoints for cohorts, genes, analyses, jobs and downloadable artifacts."
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
                <small>Explore and execute every public endpoint</small>
              </span>
            </a>
            <a href={apiUrl("/api/guia")} target="_blank" rel="noreferrer">
              <TraceIcon role="document.reference" size="sm" />
              <span>
                <strong>Guía en español</strong>
                <small>Ejemplos, límites y flujo asíncrono</small>
              </span>
            </a>
            <a href={apiUrl("/api/openapi.json")} target="_blank" rel="noreferrer">
              <TraceIcon role="data.network" size="sm" />
              <span>
                <strong>OpenAPI 3.1 schema</strong>
                <small>Machine-readable integration contract</small>
              </span>
            </a>
          </div>
        </article>

        <article className="access-card">
          <PanelHeader
            iconRole="module.aiConnectors"
            title="Claude and ChatGPT"
            description="Remote Streamable HTTP MCP access to the same TCGA-TRACE capabilities."
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
        </article>
      </div>

      <section className="integration-map" aria-label="TCGA-TRACE service connection">
        <div className="integration-map-heading">
          <div>
            <p className="eyebrow">Shared execution path</p>
            <h2>Every request reaches the same scientific engine</h2>
          </div>
          <a href={apiUrl("/api/v1/health")} target="_blank" rel="noreferrer">
            View live health JSON
          </a>
        </div>
        <div className="integration-flow">
          <div>
            <span>Inputs</span>
            <strong>Web · REST · MCP</strong>
          </div>
          <div>
            <span>Contract</span>
            <strong>API v1 validation</strong>
          </div>
          <div>
            <span>Compute</span>
            <strong>Shared job workers</strong>
          </div>
          <div>
            <span>Data</span>
            <strong>33 TCGA cohorts</strong>
          </div>
        </div>
      </section>
      <p className="access-footnote">
        Public compute is rate-limited and asynchronous. Results are exploratory and must not be
        interpreted as clinical advice.
      </p>
    </section>
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

function HelpMethodsPage({ health }) {
  const pipelineVersions = health?.pipeline_versions || {};
  const versionItems = [
    ["App", health?.app_version || "0.1.0"],
    ["Survival analysis", pipelineVersions.analysis || "server-attested-competing-risk-split-cox-contract-v6.15"],
    ["Two signatures", pipelineVersions.combined_signatures || "server-attested-competing-risk-split-cox-contract-v4.7"],
    ["Pan-cancer", pipelineVersions.pancancer || "server-attested-common-scale-reml-hksj-contract-v3.2"],
    ["Immune atlas", pipelineVersions.immune_atlas || "immune-pancancer-primary-plus-ordinal-sensitivity-cox-audit-v2.1"],
    ["Data loaded", formatDate(health?.data_dates?.database_imported_at)],
  ];

  return (
    <section className="help-page">
      <section className="help-intro">
        <PanelHeader
          iconRole="module.methods"
          title="Methods guide"
          description="Operational definitions for every analysis parameter currently exposed in TCGA-TRACE."
          help="This page mirrors the active application behavior and is intended to support reproducible use and manuscript writing."
        />
        <div className="help-version-strip" aria-label="Application and pipeline versions">
          {versionItems.map(([label, value]) => (
            <div key={label}>
              <span>{label}</span>
              <strong>{value || "..."}</strong>
            </div>
          ))}
        </div>
      </section>

      <div className="help-layout">
        <div className="help-section-stack">
          {HELP_GUIDE_SECTIONS.map((section) => (
            <section className="help-section" key={section.title}>
              <h2>{section.title}</h2>
              <dl className="help-term-list">
                {section.items.map(([term, body]) => (
                  <div className="help-term" key={term}>
                    <dt>{term}</dt>
                    <dd>{body}</dd>
                  </div>
                ))}
              </dl>
            </section>
          ))}
        </div>

        <aside className="help-section method-history" aria-label="Methodological changelog">
          <h2>Methods History</h2>
          <p>
            Version names describe analysis behavior, not Git commits. Keep this list synchronized when a change affects scoring, grouping, endpoint QC, model outputs or reproducibility exports.
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
        </aside>
      </div>
    </section>
  );
}

function DatasetSummary({ summary, health, dataSources = [], cohorts = [], summaryCohort, setSummaryCohort }) {
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

  return (
    <section className="summary-page">
      <div className="summary-overview">
        <label className="field summary-overview-filter">
          <span>Cohort filter</span>
          <select value={summaryCohort} onChange={(event) => setSummaryCohort(event.target.value)}>
            <option value="">All cohorts</option>
            {cohorts.map((cohort) => (
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
      </div>

      <DatasetProvenance dates={dates} sources={sources} />

      <div className="summary-layout">
        <section className="summary-panel wide">
          <PanelHeader
            iconRole="module.endpointCoverage"
            title="Endpoint coverage"
            description="Clinical endpoints are enabled for analysis only when linked patient and event counts pass QC."
          />
          <EndpointCoverageTable items={endpointCoverage} />
        </section>

        <section className="summary-panel wide">
          <PanelHeader
            iconRole="module.cohortLandscape"
            title="Cohort landscape"
            description="Ranked dot plot: X-axis is patients, dot size is OS events, color is event rate."
          />
          <CohortRankPlot cohorts={topCohorts} />
        </section>

        <section className="summary-panel">
          <PanelHeader
            iconRole="module.sampleTypes"
            title="Sample types"
            description="Top sample categories across all cohorts."
          />
          <DonutPlot items={distributions.sample_types || []} />
        </section>

        <section className="summary-panel">
          <PanelHeader
            iconRole="module.vitalStatus"
            title="Vital status"
            description="Clinical survival event metadata."
          />
          <DonutPlot items={distributions.vital_status || []} />
        </section>

        <section className="summary-panel">
          <PanelHeader
            iconRole="module.primarySites"
            title="Primary sites"
            description="Sample-weighted primary site distribution."
          />
          <PrimarySitePlot items={distributions.primary_site || []} />
        </section>

        <section className="summary-panel">
          <PanelHeader
            iconRole="module.age"
            title="Age at index"
            description="Available patient age bins."
          />
          <HistogramPlot items={distributions.age_bins || []} />
        </section>

        <section className="summary-panel">
          <PanelHeader
            iconRole="module.metadata"
            title="Metadata coverage"
            description="Non-missing sample metadata fields."
          />
          <CoverageMatrix items={summary.metadata_coverage || []} />
        </section>

        <section className="summary-panel">
          <PanelHeader
            iconRole="module.biologicalAnnotations"
            title="Biological annotations"
            description="Cohort-specific subtype fields detected in TCGA metadata."
          />
          <BiologicalAnnotations annotations={summary.biological_annotations || {}} />
        </section>

        <section className="summary-panel wide">
          <PanelHeader
            iconRole="module.cohortTable"
            title="Cohort table"
            description="Imported samples, patients, cancer name and source metadata."
          />
          <CohortSummaryTable cohorts={summary.cohorts || []} />
        </section>
      </div>
    </section>
  );
}

function DatasetProvenance({ dates, sources }) {
  const snapshotDate =
    dates.data_through_date || dates.source_latest_metadata_file || dates.source_summary_file;
  const snapshotLabel = dates.data_through_date ? "Data through" : "Source snapshot";
  const preparedDate = dates.rna_cache_generated_at || dates.database_imported_at;
  const readyStatuses = new Set(["ready", "ready_cached", "configured_no_survival"]);

  return (
    <section className="dataset-provenance" aria-label="Dataset provenance and source status">
      <div className="dataset-provenance-heading">
        <TraceIcon role="data.cohort" size="md" />
        <strong>Data provenance</strong>
      </div>
      <div className="dataset-provenance-date">
        <span>{snapshotLabel}</span>
        <strong><time dateTime={snapshotDate || undefined}>{formatDate(snapshotDate)}</time></strong>
      </div>
      <div className="dataset-provenance-date">
        <span>Prepared for analysis</span>
        <strong><time dateTime={preparedDate || undefined}>{formatDate(preparedDate)}</time></strong>
      </div>
      <div className="dataset-provenance-sources">
        <span>Sources</span>
        <div>
          {sources.length ? sources.map((source) => {
            const ready = readyStatuses.has(source.status);
            const sourceName = formatSourceLabel(source.id);
            const statusLabel = formatSourceStatus(source.status);
            const details = [
              source.label || sourceName,
              statusLabel,
              source.imported_at ? `imported ${formatDateTime(source.imported_at)}` : null,
            ].filter(Boolean).join("; ");
            return (
              <span
                key={source.id}
                className={`dataset-source-state ${ready ? "ready" : "attention"}`}
                title={details}
              >
                {ready
                  ? <TraceIcon role="status.success" size="sm" tone="success" />
                  : <TraceIcon role="status.caution" size="sm" tone="caution" />}
                <strong>{sourceName}</strong>
                <small>{statusLabel}</small>
              </span>
            );
          }) : (
            <span className="dataset-source-state attention">
              <TraceIcon role="status.caution" size="sm" tone="caution" />
              <strong>Sources</strong>
              <small>unavailable</small>
            </span>
          )}
        </div>
      </div>
    </section>
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
  return (
    <div
      className="table-scroll"
      role="region"
      aria-label="Scrollable TCGA cohort summary table"
      tabIndex={0}
    >
      <table>
        <thead>
          <tr>
            <th>Cohort</th>
            <th>Cancer</th>
            <th>Primary site</th>
            <th>Samples</th>
            <th>Patients</th>
            <th>Events</th>
            <th>Primary tumor</th>
            <th>Solid normal</th>
          </tr>
        </thead>
        <tbody>
          {cohorts.map((cohort) => (
            <tr key={cohort.id}>
              <td>{cohort.id}</td>
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
      <div className="analysis-stepper-scroll">
        <nav aria-label={ariaLabel}>
          <ol className="analysis-stepper" style={{ "--workflow-step-count": steps.length }}>
            {steps.map((step, index) => {
              const isActive = index === activeStep;
              const isComplete = Boolean(completion[index]);
              return (
                <li key={step.id}>
                  <button
                    id={`${idPrefix}-${step.id}`}
                    type="button"
                    className={`${isActive ? "active" : ""}${isComplete ? " complete" : ""}`}
                    onClick={() => onSelect(index)}
                    aria-current={isActive ? "step" : undefined}
                    aria-controls={`${idPrefix}-panel-${step.id}`}
                  >
                    <span className="analysis-step-marker" aria-hidden="true">
                      {isComplete && !isActive ? <TraceIcon role="status.success" size="sm" /> : index + 1}
                    </span>
                    <span>{step.label}</span>
                    <span className="sr-only">
                      {isActive ? ", current step" : isComplete ? ", configured" : ""}
                    </span>
                  </button>
                </li>
              );
            })}
          </ol>
        </nav>
      </div>
      <div className="analysis-step-summary" aria-label={summaryLabel}>
        <span>{summaryLabel}</span>
        <strong>{summary}</strong>
      </div>
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
  activeStep,
  step,
  cohort,
  repositoryDataset,
  form,
  isCombinedMode,
  selectedGenes,
  signatureAGenes,
  signatureBGenes,
  endpoint,
  expressionScale,
  cutpoint,
  activeFilterCount,
  plotEditorTarget,
  plotTitlePlaceholder,
}) {
  const titles = {
    dataset: cohort ? "Cohort profile" : "Choose a cohort",
    genes: isCombinedMode ? "Two-signature design" : "Molecular signal",
    endpoint: "Outcome availability",
    groups: "Grouping scheme",
    filters: activeFilterCount ? "Restricted clinical design" : "Clinical design",
    plot: "Practical plot preview",
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

      {step.id === "dataset" && (
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
                label="RNA samples"
                value={formatInteger(
                  repositoryDataset?.sample_count ?? cohort.n_samples_paired,
                )}
              />
              <PreviewItem
                label="Patients"
                value={formatInteger(
                  repositoryDataset?.patient_count ?? cohort.n_patients_paired,
                )}
              />
              <PreviewItem
                label={repositoryDataset ? "Genes" : "Tumors"}
                value={formatInteger(
                  repositoryDataset?.gene_count ?? cohort.n_primary_tumor,
                )}
              />
            </div>
          </div>
        ) : (
          <PreviewPrompt
            iconRole="module.dataset"
            title="Select one TCGA cancer"
            text="The cohort determines available genes, endpoints, clinical fields and patient counts."
          />
        )
      )}

      {step.id === "genes" && (
        <div className="analysis-context-preview">
          <div className="analysis-preview-lead">
            <span>{isCombinedMode ? "Two signatures" : formatLabel(form.signature_method)}</span>
            <h3>{isCombinedMode ? "Independent molecular scores" : "Expression signal"}</h3>
            <p>
              {isCombinedMode
                ? "Each signature is scored separately before patient groups are crossed."
                : form.signature_method === "single"
                  ? "Each selected gene produces a separate survival analysis."
                  : "Selected genes contribute to one combined expression score."}
            </p>
          </div>
          {isCombinedMode ? (
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

      {step.id === "endpoint" && (
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
              <PreviewItem label="Patients" value={formatInteger(endpoint?.patients)} />
              <PreviewItem label="Events" value={formatInteger(endpoint?.events)} />
              <PreviewItem label="Status" value={endpoint?.available ? "Available" : "Not evaluable"} />
            </div>
          </div>
        ) : (
          <PreviewPrompt
            iconRole="module.survivalEndpoint"
            title="Cohort required"
            text="Endpoint availability and event counts are evaluated after a cohort is selected."
          />
        )
      )}

      {step.id === "groups" && (
        <GroupingPreview
          form={form}
          isCombinedMode={isCombinedMode}
          expressionScale={expressionScale}
          cutpoint={cutpoint}
        />
      )}

      {step.id === "filters" && (
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

      {step.id === "plot" && (
        <PlotStylePreview
          form={form}
          isCombinedMode={isCombinedMode}
          plotTitlePlaceholder={plotTitlePlaceholder}
          previewTarget={plotEditorTarget}
        />
      )}

      <footer className="analysis-preview-note">
        {step.id === "plot"
          ? "Illustrative preview only. Colors and labels reflect the export settings; no effect estimate is implied."
          : "Configuration preview only. Patient grouping and models are computed after Run analysis."}
      </footer>
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
        <span>{formatLabel(method)}</span>
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

function GroupingPreview({ form, isCombinedMode, expressionScale, cutpoint }) {
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

function PlotStylePreview({
  form,
  isCombinedMode,
  plotTitlePlaceholder,
  previewContext = "survival",
  previewGene = "",
  previewMethod = "",
  previewTarget = "survival",
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
  const activeTarget =
    isCombinedMode && previewTarget === "continuous" ? "survival" : previewTarget;
  const groupingMethod = form.combined_signature?.grouping_method || "median";
  const groupCount = isCombinedMode
    ? Math.min(groupingMethod === "tertiles" ? 9 : 4, 4)
    : form.cutpoint_method === "tertiles" ? 3 : 2;
  const colors = isCombinedMode
    ? combinedPalette(plotStyle.palette, groupingMethod).slice(0, groupCount)
    : groupCount === 2
      ? [plotStyle.palette[0], plotStyle.palette[2] || plotStyle.palette[1]]
      : plotStyle.palette.slice(0, groupCount);
  const labels = isCombinedMode
    ? ["Low × Low", "Low × High", "High × Low", "High × High"].slice(0, groupCount)
    : groupCount === 3 ? ["Low", "Mid", "High"] : ["Low", "High"];
  const fontFamily = {
    serif: 'Georgia, "Times New Roman", serif',
    mono: 'ui-monospace, "SFMono-Regular", Consolas, monospace',
    sans: '"IBM Plex Sans Variable", "IBM Plex Sans", Aptos, sans-serif',
  }[plotStyle.font_family] || '"IBM Plex Sans Variable", "IBM Plex Sans", Aptos, sans-serif';
  const baseFontSize = Math.max(10, Math.min(16, Number(plotStyle.base_font_size) || 12));
  const axisTextSize = Math.max(9, Math.min(16, Number(plotStyle.axis_text_size) || 11));
  const axisTitleSize = Math.max(10, Math.min(18, Number(plotStyle.axis_title_size) || 12));
  const markerLabel =
    previewGene || uniqueGeneSymbols(form.gene_symbol || "")[0] || "Marker";
  const artifactLabel =
    PLOT_ARTIFACT_OPTIONS.find((option) => option.value === activeTarget)?.label || "Survival";
  const previewClass =
    activeTarget === "cox_forest" ? "content-driven" : plotStyle.plot_aspect;
  const facts = {
    survival: [
      formatLabel(form.time_unit),
      `CI ${form.show_confidence_interval ? "on" : "off"}`,
      `Risk table ${form.show_risk_table ? "on" : "off"}`,
      formatLabel(plotStyle.plot_aspect),
    ],
    continuous: [
      "Effect + 95% CI",
      "Reference at HR 1",
      "Subtitle automatic",
      formatLabel(plotStyle.plot_aspect),
    ],
    cox_forest: [
      coxForestStyle.model_layout === "separate" ? "Separate forests" : "Combined forest",
      "Reference at HR 1",
      "Contrast automatic",
      "Height by model count",
    ],
  }[activeTarget];

  return (
    <div
      className={`plot-style-preview ${previewClass} artifact-${activeTarget}${previewContext === "compare" ? " compare-cell-style-preview" : ""}`}
      style={{ fontFamily }}
    >
      <div className="plot-style-preview-toolbar">
        <span>{previewContext === "compare" ? `Representative ${artifactLabel}` : `${artifactLabel} preview`}</span>
        <strong>
          {previewContext === "compare"
            ? `${previewGene} · ${previewMethod}`
            : "Illustrative data"}
        </strong>
      </div>

      {activeTarget === "survival" && (
        <SurvivalPlotPreview
          form={form}
          plotStyle={plotStyle}
          plotTitlePlaceholder={plotTitlePlaceholder}
          colors={colors}
          labels={labels}
          groupCount={groupCount}
          fontFamily={fontFamily}
          baseFontSize={baseFontSize}
          axisTextSize={axisTextSize}
          axisTitleSize={axisTitleSize}
        />
      )}
      {activeTarget === "continuous" && (
        <ContinuousCoxPlotPreview
          plotStyle={plotStyle}
          continuousStyle={continuousStyle}
          markerLabel={markerLabel}
          fontFamily={fontFamily}
          baseFontSize={baseFontSize}
          axisTextSize={axisTextSize}
          axisTitleSize={axisTitleSize}
        />
      )}
      {activeTarget === "cox_forest" && (
        <CoxForestPlotPreview
          plotStyle={plotStyle}
          coxForestStyle={coxForestStyle}
          isCombinedMode={isCombinedMode}
          fontFamily={fontFamily}
          baseFontSize={baseFontSize}
          axisTextSize={axisTextSize}
          axisTitleSize={axisTitleSize}
        />
      )}

      <div className="plot-style-preview-facts">
        {facts.map((fact) => <span key={fact}>{fact}</span>)}
      </div>
    </div>
  );
}

function SurvivalPlotPreview({
  form,
  plotStyle,
  plotTitlePlaceholder,
  colors,
  labels,
  groupCount,
  fontFamily,
  baseFontSize,
  axisTextSize,
  axisTitleSize,
}) {
  const svgHeight = form.show_risk_table ? 500 : 410;
  const xTicks = {
    days: ["0", "1,000", "2,000", "3,000", "4,000"],
    months: ["0", "12", "24", "36", "48"],
    years: ["0", "1", "2", "3", "4"],
  }[form.time_unit] || ["0", "1", "2", "3", "4"];
  const curvePaths = [
    "M 92 96 H 150 V 105 H 218 V 121 H 286 V 143 H 362 V 168 H 440 V 197 H 520 V 228 H 640 V 258",
    "M 92 96 H 155 V 101 H 226 V 111 H 300 V 126 H 380 V 145 H 464 V 170 H 548 V 196 H 640 V 218",
    "M 92 96 H 148 V 99 H 222 V 106 H 294 V 116 H 372 V 129 H 456 V 147 H 542 V 168 H 640 V 191",
    "M 92 96 H 162 V 103 H 236 V 118 H 312 V 136 H 394 V 159 H 476 V 186 H 558 V 218 H 640 V 246",
  ];

  return (
    <svg
      viewBox={`0 0 720 ${svgHeight}`}
      role="img"
      aria-label="Illustrative Kaplan-Meier plot style preview"
      style={{ fontFamily }}
    >
      <rect className="plot-preview-paper" x="1" y="1" width="718" height={svgHeight - 2} rx="4" />
      {plotStyle.show_title && (
        <text className="plot-preview-title" x="360" y="35" textAnchor="middle" fontSize={baseFontSize + 4}>
          {plotStyle.plot_title?.trim() || plotTitlePlaceholder}
        </text>
      )}
      <text className="plot-preview-watermark" x="680" y="35" textAnchor="end" fontSize="9">ILLUSTRATIVE</text>
      {plotStyle.show_grid && (
        <g className="plot-preview-grid">
          {[92, 229, 366, 503, 640].map((x) => <line key={`x-${x}`} x1={x} x2={x} y1="76" y2="330" />)}
          {[76, 139, 203, 266, 330].map((y) => <line key={`y-${y}`} x1="92" x2="640" y1={y} y2={y} />)}
        </g>
      )}
      <g className="plot-preview-axes">
        <line x1="92" x2="640" y1="330" y2="330" />
        <line x1="92" x2="92" y1="76" y2="330" />
      </g>
      <g className="plot-preview-y-labels" fontSize={axisTextSize}>
        {["1.00", "0.75", "0.50", "0.25", "0.00"].map((label, index) => (
          <text key={label} x="78" y={80 + index * 63.5} textAnchor="end">{label}</text>
        ))}
      </g>
      <g className="plot-preview-x-labels" fontSize={axisTextSize}>
        {xTicks.map((label, index) => (
          <text key={`${label}-${index}`} x={92 + index * 137} y="350" textAnchor="middle">{label}</text>
        ))}
      </g>
      <text className="plot-preview-axis-title" x="366" y="377" textAnchor="middle" fontSize={axisTitleSize}>
        Time ({form.time_unit})
      </text>
      <text
        className="plot-preview-axis-title"
        x="25"
        y="204"
        textAnchor="middle"
        fontSize={axisTitleSize}
        transform="rotate(-90 25 204)"
      >
        Survival probability
      </text>
      <g className="plot-preview-curves">
        {curvePaths.slice(0, groupCount).map((path, index) => (
          <g key={labels[index]}>
            {form.show_confidence_interval && (
              <path d={path} stroke={colors[index]} className="plot-preview-ci" />
            )}
            <path d={path} stroke={colors[index]} className="plot-preview-curve" />
          </g>
        ))}
      </g>
      <g className="plot-preview-legend" fontSize={baseFontSize}>
        {labels.map((label, index) => {
          const column = index % 2;
          const row = Math.floor(index / 2);
          const x = 452 + column * 100;
          const y = 64 + row * 17;
          return (
            <g key={label}>
              <line x1={x} x2={x + 18} y1={y} y2={y} stroke={colors[index]} />
              <text x={x + 24} y={y + 4}>{label}</text>
            </g>
          );
        })}
      </g>
      {form.show_risk_table && (
        <g className="plot-preview-risk-table" fontSize={axisTextSize}>
          <text x="92" y="410" fontWeight="700">Number at risk</text>
          {labels.map((label, row) => (
            <g key={label}>
              <text x="92" y={436 + row * 16} fill={colors[row]}>{label}</text>
              {[100, 78, 52, 31, 14].map((value, column) => (
                <text key={`${label}-${column}`} x={250 + column * 88} y={436 + row * 16} textAnchor="middle">
                  {Math.max(1, value - row * 8)}
                </text>
              ))}
            </g>
          ))}
        </g>
      )}
    </svg>
  );
}

function ContinuousCoxPlotPreview({
  plotStyle,
  continuousStyle,
  markerLabel,
  fontFamily,
  baseFontSize,
  axisTextSize,
  axisTitleSize,
}) {
  const title = continuousStyle.plot_title?.trim() || "Continuous expression effect";
  const xAxisTitle = continuousStyle.x_axis_title?.trim() || `${markerLabel} expression`;
  const yAxisTitle = continuousStyle.y_axis_title?.trim() || "Hazard ratio relative to median";
  return (
    <svg
      viewBox="0 0 720 410"
      role="img"
      aria-label="Illustrative continuous Cox spline plot style preview"
      style={{ fontFamily }}
    >
      <rect className="plot-preview-paper" x="1" y="1" width="718" height="408" rx="4" />
      {continuousStyle.show_title && (
        <text className="plot-preview-title" x="92" y="32" fontSize={baseFontSize + 4}>{title}</text>
      )}
      <text
        className="plot-preview-subtitle"
        x="92"
        y={continuousStyle.show_title ? 57 : 35}
        fontSize={baseFontSize}
      >
        Restricted cubic spline HR relative to median; spline vs linear p = 0.12
      </text>
      <text className="plot-preview-watermark" x="680" y="32" textAnchor="end" fontSize="9">ILLUSTRATIVE</text>
      {plotStyle.show_grid && (
        <g className="plot-preview-grid">
          {[92, 229, 366, 503, 640].map((x) => <line key={`x-${x}`} x1={x} x2={x} y1="86" y2="330" />)}
          {[86, 167, 248, 330].map((y) => <line key={`y-${y}`} x1="92" x2="640" y1={y} y2={y} />)}
        </g>
      )}
      <g className="plot-preview-axes">
        <line x1="92" x2="640" y1="330" y2="330" />
        <line x1="92" x2="92" y1="86" y2="330" />
      </g>
      <line
        className="plot-preview-reference dashed"
        x1="92"
        x2="640"
        y1="248"
        y2="248"
        stroke={continuousStyle.reference_color}
      />
      <line
        className="plot-preview-reference dotted"
        x1="366"
        x2="366"
        y1="86"
        y2="330"
        stroke={continuousStyle.reference_color}
      />
      <path
        className="plot-preview-effect-ribbon"
        fill={continuousStyle.effect_color}
        d="M 92 286 C 185 275, 286 238, 366 218 C 458 184, 555 116, 640 88 L 640 154 C 550 176, 458 229, 366 276 C 281 299, 184 326, 92 330 Z"
      />
      <path
        className="plot-preview-effect-line"
        stroke={continuousStyle.effect_color}
        d="M 92 309 C 188 293, 284 265, 366 248 C 456 218, 552 166, 640 120"
      />
      <g className="plot-preview-y-labels" fontSize={axisTextSize}>
        {["4.0", "2.0", "1.0", "0.5"].map((label, index) => (
          <text key={label} x="78" y={90 + index * 81} textAnchor="end">{label}</text>
        ))}
      </g>
      <g className="plot-preview-x-labels" fontSize={axisTextSize}>
        {["−2", "−1", "0", "+1", "+2"].map((label, index) => (
          <text key={label} x={92 + index * 137} y="350" textAnchor="middle">{label}</text>
        ))}
      </g>
      <text className="plot-preview-axis-title" x="366" y="378" textAnchor="middle" fontSize={axisTitleSize}>
        {xAxisTitle}
      </text>
      <text
        className="plot-preview-axis-title"
        x="25"
        y="208"
        textAnchor="middle"
        fontSize={axisTitleSize}
        transform="rotate(-90 25 208)"
      >
        {yAxisTitle}
      </text>
    </svg>
  );
}

function CoxForestPlotPreview({
  plotStyle,
  coxForestStyle,
  isCombinedMode,
  fontFamily,
  baseFontSize,
  axisTextSize,
  axisTitleSize,
}) {
  const rows = [
    { label: "Univariable", low: 286, point: 326, high: 361, estimate: "0.74 (0.52–1.06)", p: "p = 0.10", direction: "lower" },
    { label: "User-selected", low: 366, point: 405, high: 452, estimate: "1.38 (0.96–1.98)", p: "p = 0.08", direction: "higher" },
    { label: "Stage + grade", low: 348, point: 387, high: 430, estimate: "1.16 (0.84–1.61)", p: "p = 0.37", direction: "higher" },
  ];
  const commonProps = {
    plotStyle,
    coxForestStyle,
    isCombinedMode,
    fontFamily,
    baseFontSize,
    axisTextSize,
    axisTitleSize,
  };
  if (coxForestStyle.model_layout === "separate") {
    return (
      <div
        className="cox-preview-split"
        role="group"
        aria-label="Illustrative separate Cox forest plot previews"
      >
        <div>
          <span className="cox-preview-family-label">Univariable output</span>
          <CoxForestPreviewFigure
            {...commonProps}
            title={coxForestStyle.univariable_plot_title?.trim() || "Univariable Cox model"}
            rows={rows.slice(0, 1)}
            ariaLabel="Illustrative univariable Cox forest plot style preview"
          />
        </div>
        <div>
          <span className="cox-preview-family-label">Multivariable output</span>
          <CoxForestPreviewFigure
            {...commonProps}
            title={coxForestStyle.multivariable_plot_title?.trim() || "Multivariable Cox models"}
            rows={rows.slice(1)}
            ariaLabel="Illustrative multivariable Cox forest plot style preview"
          />
        </div>
      </div>
    );
  }

  return (
    <CoxForestPreviewFigure
      {...commonProps}
      title={coxForestStyle.plot_title?.trim() || "Cox proportional hazards models"}
      rows={rows}
      ariaLabel="Illustrative combined Cox proportional hazards forest plot style preview"
    />
  );
}

function CoxForestPreviewFigure({
  plotStyle,
  coxForestStyle,
  isCombinedMode,
  fontFamily,
  baseFontSize,
  axisTextSize,
  axisTitleSize,
  title,
  rows,
  ariaLabel,
}) {
  const xAxisTitle = coxForestStyle.x_axis_title?.trim() || "Hazard ratio (log scale)";
  const rowStart = 150;
  const rowGap = 58;
  const axisY = rowStart + Math.max(0, rows.length - 1) * rowGap + 38;
  const svgHeight = axisY + 106;
  return (
    <svg
      viewBox={`0 0 720 ${svgHeight}`}
      role="img"
      aria-label={ariaLabel}
      style={{ fontFamily }}
    >
      <rect className="plot-preview-paper" x="1" y="1" width="718" height={svgHeight - 2} rx="4" />
      {coxForestStyle.show_title && (
        <text className="plot-preview-title" x="40" y="32" fontSize={baseFontSize + 4}>{title}</text>
      )}
      <text
        className="plot-preview-subtitle"
        x="40"
        y={coxForestStyle.show_title ? 57 : 35}
        fontSize={baseFontSize}
      >
        {isCombinedMode ? "High × High vs Low × Low expression group" : "High vs Low expression group"}
      </text>
      <text className="plot-preview-watermark" x="680" y="32" textAnchor="end" fontSize="9">ILLUSTRATIVE</text>
      <g className="plot-preview-forest-header" fontSize={baseFontSize}>
        <text x="40" y="105">Model</text>
        <text x="518" y="105">Estimate (95% CI)</text>
        <text x="680" y="105" textAnchor="end">p-value</text>
      </g>
      {plotStyle.show_grid && (
        <g className="plot-preview-grid">
          {[260, 316, 372, 428, 484].map((x) => (
            <line key={x} x1={x} x2={x} y1="122" y2={axisY} />
          ))}
          {rows.map((row, index) => {
            const y = rowStart + index * rowGap;
            return <line key={row.label} x1="40" x2="680" y1={y} y2={y} />;
          })}
        </g>
      )}
      <line
        className="plot-preview-reference dashed"
        x1="372"
        x2="372"
        y1="122"
        y2={axisY}
        stroke={coxForestStyle.reference_color}
      />
      <g className="plot-preview-forest-rows" fontSize={axisTextSize}>
        {rows.map((row, index) => {
          const y = rowStart + index * rowGap;
          const color = row.direction === "lower"
            ? coxForestStyle.lower_hazard_color
            : coxForestStyle.higher_hazard_color;
          return (
            <g key={row.label}>
              <text x="40" y={y + 4}>{row.label}</text>
              <line className="plot-preview-forest-ci" x1={row.low} x2={row.high} y1={y} y2={y} stroke={color} />
              <circle className="plot-preview-forest-point" cx={row.point} cy={y} r="5" fill={color} />
              <text x="518" y={y + 4}>{row.estimate}</text>
              <text x="680" y={y + 4} textAnchor="end">{row.p}</text>
            </g>
          );
        })}
      </g>
      <g className="plot-preview-axes">
        <line x1="260" x2="484" y1={axisY} y2={axisY} />
      </g>
      <g className="plot-preview-x-labels" fontSize={axisTextSize}>
        {["0.25", "0.5", "1", "2", "4"].map((label, index) => (
          <text key={label} x={260 + index * 56} y={axisY + 22} textAnchor="middle">{label}</text>
        ))}
      </g>
      <text className="plot-preview-axis-title" x="372" y={axisY + 52} textAnchor="middle" fontSize={axisTitleSize}>
        {xAxisTitle}
      </text>
    </svg>
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
        <p className="eyebrow">Running R survival analysis</p>
        <h2>
          {getCohortName(cohort)} / {isCombinedMode ? gene : isSingleMode ? `${completedCount} of ${geneCount} genes completed` : gene.trim().toUpperCase()}
        </h2>
        {cohort && <small>{cohort}</small>}
        <span>
          Reading {expressionScale?.label || "expression"}, assigning groups, fitting {endpoint?.label || "survival"} curves and rendering artifacts.
        </span>
      </div>
      <div className="progress-rail">
        <i />
      </div>
    </div>
  );
}

function AnalysisResults({ analyses, onDownload }) {
  if (analyses.length === 1) {
    return <AnalysisResult analysis={analyses[0]} onDownload={onDownload} />;
  }
  return (
    <div className="analysis-stack">
      <div className="stack-header">
        <span>Separate Kaplan-Meier plots</span>
        <strong>{analyses.length} completed genes</strong>
      </div>
      {analyses.map((item) => (
        <AnalysisResult key={item.id} analysis={item} onDownload={onDownload} />
      ))}
    </div>
  );
}

function AnalysisResult({ analysis, onDownload }) {
  const metrics = analysis.metrics || {};
  const downloads = analysis.downloads || {};
  const endpointLabel = metrics.endpoint_label || "Overall survival";
  const combinedSignature = metrics.combined_signature;
  const continuous = metrics.continuous_analysis || {};
  const continuousPrimary = findCoxModel(continuous.linear_models, "continuous_univariable");
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
  return (
    <div className="analysis-result">
      <div className="result-header">
        <div>
          <h2>{analysis.gene_symbol} · {endpointLabel}</h2>
          <p className="result-context">
            {getCohortName(analysis.cohort)} ({analysis.cohort}) · {analysis.expression_scale_label || "Expression"}
            {analysis.cached ? " · cached" : ""}
          </p>
        </div>
        <ResultDownloads downloads={downloads} onDownload={onDownload} />
      </div>

      {hasContinuous ? (
        <div className="metric-strip">
          <Metric label="Continuous n" value={continuous.n_patients} />
          <Metric label="Events" value={continuous.n_events} />
          <Metric label="HR per +1 SD" value={formatHrValues(continuousPrimary)} />
          <Metric label="Linear Cox p" value={formatP(continuousPrimary?.p_value)} />
          <Metric label="Nonlinearity p" value={formatP(spline.nonlinearity_p_value)} />
        </div>
      ) : (
        <div className="metric-strip">
          <Metric label="Patients" value={metrics.n_patients} />
          <Metric label="Events" value={metrics.n_events} />
          <Metric label="Log-rank p" value={formatP(metrics.logrank_p_value)} />
          <Metric label="Hazard ratio" value={formatHr(metrics)} />
          <Metric label="RMST delta" value={formatRmstDelta(metrics.rmst)} />
        </div>
      )}

      {!combinedSignature && (
        <ContinuousAnalysisSummary
          continuous={continuous}
          downloads={downloads}
          geneSymbol={analysis.gene_symbol}
          onDownload={onDownload}
        />
      )}

      <section className={combinedSignature ? "grouped-analysis" : "grouped-analysis cutpoint-sensitivity"}>
        <div className="grouped-analysis-heading">
          <div>
            <span>{combinedSignature ? "Cross-stratified analysis" : "Cutpoint sensitivity"}</span>
            <h3>{combinedSignature ? "Combined expression groups" : "Grouped survival estimates"}</h3>
          </div>
          {!combinedSignature && (
            <p>Secondary estimates after applying the selected cutpoint to the continuous marker.</p>
          )}
        </div>

        <div className="result-details">
          <GroupTable metrics={metrics} />
          <CutpointSummary details={metrics.cutpoint_details} />
        </div>

        <CoxModelTable models={metrics.cox_models} />
        <RmstTable rmst={metrics.rmst} />

        <img className="km-plot" src={apiUrl(downloads.png)} alt="Kaplan-Meier cutpoint sensitivity plot" />
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
                <img className="cox-forest-plot" src={apiUrl(plot.png)} alt={plot.alt} />
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
            <img className="cox-forest-plot" src={apiUrl(downloads.cox_png)} alt="Grouped Cox model forest plot" />
          </>
        ) : null}
      </section>

      <CompetingRiskPanel
        competing={metrics.competing_risks}
        downloads={downloads}
        endpointLabel={endpointLabel}
        onDownload={onDownload}
      />

      <AuditSummary audit={metrics.audit_report} />

      {combinedSignature && <CombinedSignatureSummary combined={combinedSignature} />}
      <SignatureInteractionCoxTable models={metrics.signature_interaction_cox_models} />

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
      <DetailSectionTitle
        title="Continuous expression model"
        help="The primary model uses every expression-complete eligible patient before cutpoint assignment. Expression is standardized within that population, so each HR represents a one-standard-deviation increase."
      />
      {!completed ? (
        <div className="method-note">
          Continuous modeling was not estimable: {continuous?.reason || "No complete continuous population was available."}
        </div>
      ) : (
        <>
          <div className="continuous-model-context">
            <div>
              <span>Population</span>
              <strong>{formatInteger(continuous.n_patients)} patients / {formatInteger(continuous.n_events)} events</strong>
            </div>
            <div>
              <span>Effect unit</span>
              <strong>+1 SD expression</strong>
            </div>
            <div>
              <span>Expression SD</span>
              <strong>{formatCompactNumber(continuous.predictor?.standard_deviation)}</strong>
            </div>
            <div>
              <span>Cutpoint</span>
              <strong>Not used</strong>
            </div>
          </div>

          <div className="continuous-model-table">
            <table>
              <thead>
                <tr>
                  <th>Model</th>
                  <th>Patients</th>
                  <th>Events</th>
                  <th title="Observed events divided by the number of fitted model coefficients">
                    Events / parameter
                  </th>
                  <th title="Hazard ratio for a one-standard-deviation increase in expression, with 95% confidence interval">
                    HR / +1 SD (95% CI)
                  </th>
                  <th>p</th>
                  <th title="Firth penalized sensitivity is run for low-information, unstable or extreme standard Cox fits">
                    Firth sensitivity
                  </th>
                  <th title="Proportional-hazards diagnostic for the expression term">PH p (marker)</th>
                  <th title="Global proportional-hazards diagnostic for the complete model">PH p (global)</th>
                  <th>Issue</th>
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
            <div>
              <span>Reference</span>
              <strong>{splineCompleted ? `Median (${formatCompactNumber(spline.reference_expression)})` : "Not evaluable"}</strong>
            </div>
            <div>
              <span>Knots</span>
              <strong>{splineCompleted ? "5th / 35th / 65th / 95th" : "Not evaluable"}</strong>
            </div>
          </div>

          {splineCompleted && downloads.continuous_png ? (
            <>
              <div className="plot-download-row">
                <span>Restricted cubic spline effect profile</span>
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

          {selectedPercentiles.length > 0 && (
            <details className="continuous-percentile-table">
              <summary>Effect estimates at selected percentiles</summary>
              <table>
                <thead>
                  <tr>
                    <th>Expression percentile</th>
                    <th>Expression value</th>
                    <th>HR relative to median</th>
                    <th>95% CI</th>
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
      <DetailSectionTitle
        title="Competing-risk analysis"
        help={COMPETING_RISK_HELP}
      />

      <div className="competing-risk-estimands">
        <div>
          <span>Kaplan-Meier and Cox</span>
          <strong>Event-free and cause-specific</strong>
          <p>Code 2 is censored at its recorded time.</p>
        </div>
        <div>
          <span>CIF, Gray and Fine-Gray</span>
          <strong>Subdistribution-based</strong>
          <p>Code 2 remains a competing event.</p>
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
            <div className="competing-risk-table">
              <table>
                <caption className="sr-only">
                  Patient outcomes used for the {endpointLabel} competing-risk analysis
                </caption>
                <thead>
                  <tr>
                    <th>Group</th>
                    <th>Patients</th>
                    <th>Target events</th>
                    <th>Competing deaths</th>
                    <th>Censored</th>
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
            <div className="competing-risk-table competing-risk-horizons">
              <table>
                <caption className="sr-only">
                  Pointwise cumulative-incidence estimates with 95 percent confidence intervals and patients at risk
                </caption>
                <thead>
                  <tr>
                    <th>Horizon</th>
                    <th>Group</th>
                    <th>CIF</th>
                    <th>95% CI</th>
                    <th>At risk</th>
                    <th>Support</th>
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
      <div className="fine-gray-table">
        <table>
          <caption className="sr-only">
            {title} with subdistribution hazard ratios and model-specific support
          </caption>
          <thead>
            <tr>
              <th>Model</th>
              <th>Contrast</th>
              <th>Patients</th>
              <th>Target events</th>
              <th>Competing</th>
              <th>Events / parameter</th>
              <th title="Subdistribution hazard ratio with 95% confidence interval">
                SHR (95% CI)
              </th>
              <th>p</th>
              <th>Issue</th>
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
  const selectedAdjustedModel =
    includeModelDiagnostics
      ? downstreamAdjustedContinuousModel(continuousModels)
        || downstreamAdjustedModel(models)
        || downstreamAdjustedInteractionModel(interactionModels)
      : null;
  const selectedModelCautions = selectedAdjustedModel?.warnings || [];
  const selectedStatus =
    includeModelDiagnostics
      ? diagnostics?.selected_adjusted_status
        || (selectedAdjustedModel ? (selectedModelCautions.length ? "caution" : "clean") : "not_evaluable")
      : "information";
  const statusCopy = {
    clean: "",
    caution: "",
    not_evaluable: "Adjusted model: not evaluable",
    information: "Scan context",
  }[selectedStatus] ?? "Model diagnostics reported";
  if (!groups.length && (!selectedAdjustedModel || !statusCopy)) return null;

  return (
    <section className="analysis-notices" aria-label="Evidence context and analysis diagnostics">
      <div className="analysis-notices-intro">
        <h3>{includeModelDiagnostics ? "Diagnostics" : "Context"}</h3>
        {statusCopy && (
          <span className={`selected-model-verdict ${selectedStatus}`}>{statusCopy}</span>
        )}
      </div>
      {groups.length > 0 && (
        <div className="analysis-notice-groups">
          {groups.map((group) => (
            <details
              key={group.kind}
              className={`analysis-notice-group ${group.kind}`}
              open={group.kind === "selected-model"}
            >
              <summary>
                <span className="analysis-notice-mark" aria-hidden="true">
                  {group.kind === "selected-model"
                    ? <TraceIcon role="status.caution" size="sm" tone="caution" />
                    : <TraceIcon role="status.info" size="sm" tone="accent" />}
                </span>
                <span>
                  <strong>{group.title}</strong>
                </span>
                <b>{group.items.length}</b>
              </summary>
              <ul>
                {group.items.map((item, index) => (
                  <li key={`${group.kind}-${index}`}>
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
      message: text,
      selected_model: false,
    });
  });

  if (includeModelDiagnostics && !selectedAdjustedModel) {
    normalized.push({
      category: "availability",
      severity: "not_evaluable",
      message: "No clinical-adjusted Cox model was evaluable for this analysis. The remaining estimates and plots are still reported.",
      selected_model: false,
    });
  }
  return normalized;
}

function groupAnalysisNotices(notices = []) {
  const definitions = {
    "selected-model": {
      kind: "selected-model",
      title: "Selected model caution",
      items: [],
    },
    "other-model": {
      kind: "other-model",
      title: "Other model diagnostics",
      items: [],
    },
    availability: {
      kind: "availability",
      title: "Model availability",
      items: [],
    },
    cohort: {
      kind: "cohort",
      title: "Cohort notes",
      items: [],
    },
    method: {
      kind: "method",
      title: "Method context",
      items: [],
    },
  };

  notices.forEach((notice) => {
    const kind =
      notice.category === "model"
        ? notice.selected_model ? "selected-model" : "other-model"
        : notice.category;
    if (definitions[kind]) definitions[kind].items.push(notice);
  });

  return ["selected-model", "other-model", "availability", "cohort", "method"]
    .map((kind) => definitions[kind])
    .filter((group) => group.items.length);
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
        help="Shown only when the marker-specific cox.zph p-value is below 0.05. Two years is the fixed primary split; one and five years are prespecified sensitivities. No split is chosen from marker values, event times or effect estimates. At least 5 events per period and 10 patients entering the late period are required."
      />
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>Model</th>
              <th>Split</th>
              <th>Marker PH p</th>
              <th>Early HR (95% CI)</th>
              <th>Late HR (95% CI)</th>
              <th>Late / early HR ratio</th>
              <th>Support</th>
              <th>Status</th>
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
        help="These hazard ratios compare the expression groups created by the selected cutpoint. Adjusted models use complete cases, with stage and grade encoded as ordinal trends. Maxstat estimates remain post-selection."
      />
      <table>
        <thead>
          <tr>
            <th>Model</th>
            <th>Patients</th>
            <th>Events</th>
            <th title="Observed events divided by the number of fitted model coefficients">
              Events / parameter
            </th>
            <th>HR (95% CI)</th>
            <th>p</th>
            <th title="Firth penalized sensitivity is run for low-information, unstable or extreme standard Cox fits">
              Firth sensitivity
            </th>
            <th title="Proportional-hazards diagnostic for the grouped marker term">Marker PH p</th>
            <th title="Global proportional-hazards diagnostic for the complete model">Global PH p</th>
            <th>Issue</th>
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
        help="Tau is fixed before stratification as the smaller of five years and the eligible cohort's 75th percentile of endpoint time. RMST is reported only when at least five patients remain at risk in each group at tau."
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
          <table>
            <thead>
              <tr>
                <th>Group</th>
                <th>RMST days</th>
                <th>95% CI</th>
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
        help="Signature scores are z-scored within the analyzed patients. The interaction tests whether one signature's effect changes as the other increases."
      />
      <table>
        <thead>
          <tr>
            <th>Model</th>
            <th>Covariates</th>
            <th>Patients</th>
            <th>Events</th>
            <th title="Observed events divided by the number of fitted model coefficients">
              Events / parameter
            </th>
            <th>Signature A HR</th>
            <th>Signature B HR</th>
            <th>Interaction HR</th>
            <th>Interaction p</th>
            <th title="Firth penalized sensitivity for the interaction term">
              Firth interaction
            </th>
            <th>PH interaction p</th>
            <th>PH global p</th>
            <th>Status</th>
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
        help="Captures parameters, endpoint source, sample selection, patient records, Cox and QC outputs, software versions and artifact checksums."
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

function DetailSectionTitle({ title, help }) {
  return (
    <div className="detail-section-title">
      <h3>{title}</h3>
      {help && <HelpButton label={title}>{help}</HelpButton>}
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
      <table>
        <thead>
          <tr>
            <th>Signature</th>
            <th>Score method</th>
            <th>Genes</th>
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
      <table>
        <thead>
          <tr>
            <th>Group</th>
            <th>Patients</th>
            <th>Events</th>
            <th>Median days</th>
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
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
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
  const number = Number(value);
  if (!Number.isFinite(number)) return "...";
  if (Math.abs(number) < 0.01 && number !== 0) return number.toExponential(1);
  return number.toFixed(2);
}

function formatSignedNumber(value, digits = 1) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "...";
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
      <table>
        <thead>
          <tr>
            <th>Group</th>
            <th>Patients</th>
            <th>Events</th>
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

function ResultDownloads({ downloads = {}, onDownload }) {
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
    downloads.continuous_csv,
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

  return (
    <details className="result-downloads">
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
            <DownloadLink href={downloads.png} iconRole="file.image" label="KM PNG" onDownload={onDownload} />
            <DownloadLink href={downloads.svg} iconRole="action.download" label="KM SVG" onDownload={onDownload} />
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
          </div>
        </div>
        <div>
          <strong>Data</strong>
          <div className="download-row">
            <DownloadLink href={downloads.csv} iconRole="file.csv" label="Patient CSV" onDownload={onDownload} />
            <DownloadLink href={downloads.continuous_csv} iconRole="file.csv" label="Continuous CSV" onDownload={onDownload} />
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
          <strong>Audit</strong>
          <div className="download-row">
            <DownloadLink href={downloads.audit_json} iconRole="file.audit" label="Audit JSON" onDownload={onDownload} />
            <DownloadLink href={downloads.audit_html} iconRole="file.audit" label="Audit HTML" onDownload={onDownload} />
            <DownloadLink href={downloads.attestation} iconRole="file.audit" label="Signed receipt" onDownload={onDownload} />
            <DownloadLink href={downloads.r_script} iconRole="file.text" label="R rerun" onDownload={onDownload} />
            <DownloadLink href={downloads.reproduction_manifest} iconRole="file.audit" label="R manifest" onDownload={onDownload} />
            <DownloadLink href={downloads.zip} iconRole="file.archive" label="Bundle ZIP" onDownload={onDownload} />
          </div>
        </div>
      </div>
    </details>
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
  if (value === undefined || value === null) return "...";
  if (value < 0.001) return value.toExponential(2);
  return Number(value).toFixed(3);
}

function formatHr(metrics) {
  if (metrics.hazard_ratio === undefined || metrics.hazard_ratio === null) return "...";
  return `${Number(metrics.hazard_ratio).toFixed(2)} (${Number(metrics.hr_conf_low).toFixed(2)}-${Number(metrics.hr_conf_high).toFixed(2)})`;
}

function formatHrValues(row) {
  if (row?.hazard_ratio === undefined || row?.hazard_ratio === null) return "...";
  return `${Number(row.hazard_ratio).toFixed(2)} (${Number(row.hr_conf_low).toFixed(2)}-${Number(row.hr_conf_high).toFixed(2)})`;
}

function formatShrValues(row) {
  const estimate = Number(row?.subdistribution_hazard_ratio);
  const low = Number(row?.shr_conf_low);
  const high = Number(row?.shr_conf_high);
  if (![estimate, low, high].every(Number.isFinite)) return "...";
  return `${estimate.toFixed(2)} (${low.toFixed(2)}-${high.toFixed(2)})`;
}

function formatCif(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "...";
  return `${(100 * number).toFixed(1)}%`;
}

function formatCifInterval(estimate) {
  const low = Number(estimate?.conf_low);
  const high = Number(estimate?.conf_high);
  if (!Number.isFinite(low) || !Number.isFinite(high)) return "...";
  return `${formatCif(low)}-${formatCif(high)}`;
}

function formatHorizonYears(horizon) {
  const years = Number(horizon?.time_years);
  if (!Number.isFinite(years)) return "...";
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
  const number = Number(value);
  if (!Number.isFinite(number)) return "";
  if (number < 5) return "cox-information-cell severe";
  if (number < 10) return "cox-information-cell caution";
  return "cox-information-cell";
}

function formatFineGrayInformation(model) {
  const eventsPerParameter = Number(model?.events_per_parameter);
  const parameterCount = Number(model?.parameter_count);
  if (!Number.isFinite(eventsPerParameter) || !Number.isFinite(parameterCount)) {
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
  const ratio = Number(change?.hazard_ratio_ratio);
  const low = Number(change?.hr_ratio_conf_low);
  const high = Number(change?.hr_ratio_conf_high);
  if (![ratio, low, high].every(Number.isFinite)) return "...";
  return `${ratio.toFixed(2)} (${low.toFixed(2)}-${high.toFixed(2)})`;
}

function formatPredictionInterval(interval) {
  const low = Number(interval?.hazard_ratio_low);
  const high = Number(interval?.hazard_ratio_high);
  if (!Number.isFinite(low) || !Number.isFinite(high)) return "Not available";
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
  if (row?.adjusted_hazard_ratio === undefined || row?.adjusted_hazard_ratio === null) return "...";
  return `${Number(row.adjusted_hazard_ratio).toFixed(2)} (${Number(row.adjusted_hr_conf_low).toFixed(2)}-${Number(row.adjusted_hr_conf_high).toFixed(2)})`;
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
  const adjusted = downstreamAdjustedModel(metrics.cox_models);
  const bhValue = toNullableNumber(row.bh);
  const bhEvaluable = bhValue !== null;
  const bhBelowAlpha = bhEvaluable && bhValue <= ROBUSTNESS_ALPHA;
  const markerPhValue = toNullableNumber(adjusted?.ph_p_value);
  const markerPhEvaluable = markerPhValue !== null;
  const markerPhFlagged = markerPhEvaluable && markerPhValue < ROBUSTNESS_ALPHA;
  const globalPhValue = toNullableNumber(adjusted?.ph_global_p_value);
  const globalPhEvaluable = globalPhValue !== null;
  const globalPhFlagged = globalPhEvaluable && globalPhValue < ROBUSTNESS_ALPHA;
  const temporalEffect = adjusted?.time_varying_effect || {};
  const temporalStatus = temporalEffect.status || null;
  const temporalTriggered = ["completed", "skipped", "failed"].includes(temporalStatus);
  const rmstAvailable = metrics.rmst?.status === "completed"
    && toNullableNumber(metrics.rmst?.difference?.estimate_days) !== null;
  const hr = toNullableNumber(univariable?.hazard_ratio);
  const direction = hr !== null ? (hr < 1 ? "Protective" : hr > 1 ? "Harmful" : "Neutral") : "...";
  const interpretationNotes = [];
  if (!adjusted) interpretationNotes.push("Adjusted Cox not evaluable");
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
  const number = Number(value);
  if (!Number.isFinite(number)) return "...";
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
  if (value === undefined || value === null || value === "") return "...";
  return Number(value).toLocaleString();
}

function formatMedianSurvivalDays(value) {
  if (value === undefined || value === "") return "...";
  if (value === null) return "Not reached";
  const number = Number(value);
  if (!Number.isFinite(number)) return "Not reached";
  return Math.round(number).toLocaleString();
}

function formatDays(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "...";
  return Math.round(number).toLocaleString();
}

function formatRmstDelta(rmst) {
  if (rmst?.status !== "completed") return "...";
  const value = Number(rmst.difference?.estimate_days);
  if (!Number.isFinite(value)) return "...";
  const sign = value > 0 ? "+" : "";
  return `${sign}${Math.round(value).toLocaleString()} days`;
}

function formatRmstCi(item) {
  const low = Number(item?.conf_low);
  const high = Number(item?.conf_high);
  if (!Number.isFinite(low) || !Number.isFinite(high)) return "...";
  return `${Math.round(low).toLocaleString()}-${Math.round(high).toLocaleString()}`;
}

function isMedianNotReached(value) {
  if (value === undefined || value === "") return false;
  if (value === null) return true;
  return !Number.isFinite(Number(value));
}

function formatExpressionValue(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "...";
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

function formatSourceStatus(value) {
  return String(value || "unknown").replaceAll("_", " ");
}

function toNullableNumber(value) {
  if (value === "" || value === null || value === undefined) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function numbersEquivalent(left, right, tolerance = 1e-10) {
  const leftNumber = toNullableNumber(left);
  const rightNumber = toNullableNumber(right);
  if (leftNumber === null || rightNumber === null) return leftNumber === rightNumber;
  return Math.abs(leftNumber - rightNumber) <= tolerance * Math.max(1, Math.abs(leftNumber), Math.abs(rightNumber));
}

function cutpointTooltip(value) {
  return {
    maxstat: "Optimizes the expression threshold against survival separation; exploratory and prone to selection bias.",
    median: "Splits patients at the median expression value.",
    tertiles: "Creates low, middle and high expression groups.",
    upper_quartile: "Compares the highest 25% expression group against the remaining 75%.",
    upper_lower_quartile: "Compares upper and lower quartiles and excludes the middle 50%.",
    percentile: "Uses a user-selected percentile as the high-expression threshold.",
  }[value] || "";
}

function signatureHelp(value) {
  return {
    single: "Analyze one gene.",
    mean: "Average log-scale expression across all genes in the signature.",
    zscore: "Z-score each gene across samples, then average. Useful when genes have different scales.",
    weighted: "Weighted average of expression values. Use GENE:weight syntax.",
  }[value] || "";
}

function adjustCompareResults(rows) {
  const withP = rows.map((row, index) => ({
    ...row,
    index,
    p: row.result?.metrics?.logrank_p_value,
  }));
  const valid = withP.filter((row) => Number.isFinite(row.p)).sort((a, b) => a.p - b.p);
  const m = valid.length || 1;
  const bhByIndex = {};
  let runningMin = 1;
  for (let i = valid.length - 1; i >= 0; i -= 1) {
    const rank = i + 1;
    runningMin = Math.min(runningMin, (valid[i].p * m) / rank);
    bhByIndex[valid[i].index] = Math.min(runningMin, 1);
  }
  return withP.map((row) => ({
    ...row,
    bh: bhByIndex[row.index],
    bonferroni: Number.isFinite(row.p) ? Math.min(row.p * m, 1) : undefined,
  }));
}

function formatError(error) {
  if (!error) return "";
  const labels = {
    INVALID_GROUPS: "Invalid grouping",
    INSUFFICIENT_PATIENTS: "Not enough patients",
    NO_EVENTS: "No survival events",
    NO_GENE: "Gene not found",
    CACHE_INCOMPLETE: "Cache incomplete",
    R_FAILED: "R failed",
    ENDPOINT_UNAVAILABLE: "Endpoint unavailable",
    INVALID_ANALYSIS: "Invalid analysis",
  };
  return error.code ? `${labels[error.code] || error.code}: ${error.message}` : error.message;
}

function formatBatchItemError(item) {
  if (!item) return "Analysis failed.";
  return formatError({ code: item.code, message: item.error || "Analysis failed." });
}

createRoot(document.getElementById("root")).render(<App />);
