import { TUTORIAL_CITATION_IDS } from "./citationRegistry";
import { TUTORIAL_CONCEPT_IDS } from "./conceptRegistry";

function defineContract(definition) {
  return Object.freeze({
    ...definition,
    conceptIds: Object.freeze([...(definition.conceptIds || [])]),
    citationIds: Object.freeze([...(definition.citationIds || [])]),
  });
}

export const SCIENTIFIC_CONTRACTS = Object.freeze({
  "orientation.question": defineContract({
    id: "orientation.question",
    module: "home",
    question: "Which TRACE analysis fits your research question?",
    unitOfAnalysis: "Your research question and the patients eligible to answer it.",
    decisionTarget: "Choose an analysis based on the patients, marker, outcome and purpose before viewing results.",
    reference: "The question declared before module selection.",
    scale: "Not applicable; this step helps choose an analysis rather than estimate an effect.",
    inferentialRole: "context",
    multiplicity: "No hypothesis family is tested at this stage.",
    assumptions: Object.freeze(["The question can be stated independently of statistical significance."]),
    diagnostics: Object.freeze(["Population, marker, endpoint and purpose are all explicit."]),
    cannotConclude: Object.freeze(["Module choice is not evidence for a biological effect."]),
    conceptIds: ["population", "endpoint", "estimand"],
    citationIds: [],
  }),
  "survival.continuous": defineContract({
    id: "survival.continuous",
    module: "analysis",
    question: "How does the selected marker relate to time until the selected event?",
    unitOfAnalysis: "One eligible patient with one prioritized expression profile and an unambiguous endpoint.",
    estimand: "Continuous Cox hazard ratio for a +1 within-analysis SD increase in marker expression or signature score; grouped analyses are cutpoint-based sensitivities.",
    reference: "A marker value one within-analysis SD lower in the same expression-complete eligible population, or the explicitly named reference group for grouped displays.",
    scale: "Expression or the signature score is standardized within the run's expression-complete eligible population; the reported continuous HR is per +1 SD, not per +1 raw log-expression unit.",
    inferentialRole: "primary_associational",
    multiplicity: "The primary continuous model is distinct from exploratory cutpoint and sensitivity families.",
    assumptions: Object.freeze(["Correct patient linkage and endpoint coding.", "A defensible functional form and proportional-hazards interpretation."]),
    diagnostics: Object.freeze(["Events per parameter.", "Marker and global proportional-hazards diagnostics.", "Penalized or RMST sensitivity when available."]),
    cannotConclude: Object.freeze(["The association is not a causal or treatment effect.", "A grouped curve cannot replace the primary continuous analysis."]),
    conceptIds: ["hazard_ratio", "continuous_primary", "proportional_hazards", "association_not_causation"],
    citationIds: ["cox-1972", "schoenfeld-1982"],
  }),
  "compare.cutpoint_sensitivity": defineContract({
    id: "compare.cutpoint_sensitivity",
    module: "compare",
    question: "How does a survival association change across the planned genes and cutpoints?",
    unitOfAnalysis: "One completed analysis cell using the same cohort, endpoint and expression data.",
    estimand: "Grouped Cox contrasts compared with the cutpoint-independent continuous reference.",
    reference: "The lower or named group specified before execution.",
    scale: "Hazard ratio on each declared grouping rule; continuous reference reported separately.",
    inferentialRole: "exploratory_sensitivity",
    multiplicity: "BH and Bonferroni are applied across the completed gene-by-cutpoint family.",
    assumptions: Object.freeze(["The family is declared before inspecting its cells.", "Cells retain comparable populations and endpoints."]),
    diagnostics: Object.freeze(["Family size and unavailable cells.", "Direction and population compatibility with the continuous model."]),
    cannotConclude: Object.freeze(["The smallest p value is not a validated optimal cutpoint."]),
    conceptIds: ["cutpoint", "multiplicity_family", "continuous_primary", "fdr"],
    citationIds: ["benjamini-hochberg-1995"],
  }),
  "expression.two_group": defineContract({
    id: "expression.two_group",
    module: "expression",
    question: "How does expression of the selected genes differ between the two groups?",
    unitOfAnalysis: "One eligible patient assigned to exactly one of two groups.",
    estimand: "Gene-wise B minus A location contrast, with Welch and Mann-Whitney evidence reported separately.",
    reference: "Group A is the reference; group B is the target.",
    scale: "Audited expression scale for estimates; within-gene z-scores only for heatmap display.",
    inferentialRole: "associational",
    multiplicity: "Welch and Mann-Whitney results form separate BH families across declared genes.",
    assumptions: Object.freeze(["Groups are disjoint and defined independently of target-gene outcomes.", "Patient counts and exclusions are visible."]),
    diagnostics: Object.freeze(["Distribution, dispersion and outliers.", "Agreement or disagreement between parametric and rank evidence."]),
    cannotConclude: Object.freeze(["A difference does not establish mechanism or causal regulation.", "Heatmap color is not comparable across genes."]),
    conceptIds: ["contrast_b_minus_a", "welch_test", "mann_whitney", "within_gene_zscore", "circularity"],
    citationIds: ["welch-1947", "mann-whitney-1947", "benjamini-hochberg-1995"],
  }),
  "gsea.preranked": defineContract({
    id: "gsea.preranked",
    module: "gsea",
    question: "Which declared gene sets concentrate toward either end of a B minus A ranking?",
    unitOfAnalysis: "A gene set evaluated against one complete ranked gene list.",
    estimand: "A two-sided CAMERA competitive test plus a descriptive preranked normalized enrichment score; positive NES favors B and negative NES favors A.",
    reference: "Group A in the B minus A ranking.",
    scale: "CAMERA p and BH FDR encode evidence after per-set residual correlation adjustment. NES encodes a separate directional running-sum effect. The DotPlot uses color and position for NES and point area proportional to min(-log10(CAMERA FDR), 10).",
    inferentialRole: "pathway_association",
    multiplicity: "BH is applied to two-sided CAMERA p-values across every eligible set in the selected collection.",
    assumptions: Object.freeze(["Group definition, collection and set-size bounds are declared before testing.", "Independent inference requires groups not to be constructed from the tested transcriptome.", "Only complete-case variable genes enter both layers."]),
    diagnostics: Object.freeze(["Per-set residual correlation.", "Agreement between CAMERA and NES direction.", "Leading-edge genes and redundancy among GO terms.", "Displayed top 30 versus the complete pathway table."]),
    cannotConclude: Object.freeze(["NES and leading edge are descriptive, not their own inferential test.", "Pathway association is not measured activation, causal mechanism or clinical actionability.", "Expression-derived groups provide conditional exploratory evidence rather than independent confirmation."]),
    conceptIds: ["contrast_b_minus_a", "nes", "fdr", "leading_edge", "circularity"],
    citationIds: ["wu-smyth-2012", "subramanian-2005", "go-consortium-2023", "benjamini-hochberg-1995"],
  }),
  "multiverse.specification_family": defineContract({
    id: "multiverse.specification_family",
    module: "multiverse",
    question: "How does the result change across the analysis choices planned before running?",
    unitOfAnalysis: "One planned analysis, including those that cannot be estimated.",
    estimand: "The range of compatible effects across the analysis choices fixed before running.",
    reference: "The shared reference encoded by the declared family.",
    scale: "Effect and uncertainty on each compatible specification's declared scale.",
    inferentialRole: "robustness",
    multiplicity: "The complete prospective specification family is the reporting boundary.",
    assumptions: Object.freeze(["Every decision has an a priori scientific rationale.", "The family is frozen before execution."]),
    diagnostics: Object.freeze(["Effect variation, precision and availability are separated.", "Unavailable and unfavorable specifications remain visible."]),
    cannotConclude: Object.freeze(["A visually favorable specification is not the new primary analysis."]),
    conceptIds: ["specification_curve", "prespecification", "multiplicity_family"],
    citationIds: ["simonsohn-2020"],
  }),
  "pancancer.mode_aware": defineContract({
    id: "pancancer.mode_aware",
    module: "pancancer",
    question: "Which pan-cancer approach matches the question, and how should its heterogeneity be interpreted?",
    unitOfAnalysis: "One TCGA cancer in reference mode, or one immutable study nested within a cancer in hierarchical mode; patient rows are never pooled across these units.",
    decisionTarget: "Identify what effect each mode estimates before reading cancer-, study- or global-level evidence.",
    reference: "The reference declared by the selected mode and effect view.",
    scale: "TCGA reference uses a declared common input-score unit when synthesis is eligible or a descriptive within-cancer SD view; hierarchical synthesis uses a within-study expression IQR. These scales are not interchangeable.",
    inferentialRole: "mode_selection_and_synthesis",
    multiplicity: "TCGA reference controls FDR across its eligible cancer family; hierarchical FDR applies only to replicated cancer effects, while study and singleton-cancer effects remain descriptive.",
    assumptions: Object.freeze(["Every cancer or study is fitted separately under its declared endpoint and scale.", "Eligibility, overlap and evidence level are resolved before synthesis."]),
    diagnostics: Object.freeze(["Effect scale and synthesis eligibility.", "Study and cancer intervals, heterogeneity, prediction interval, influence and unavailable reasons."]),
    cannotConclude: Object.freeze(["A global summary is not universal, and agreement between a precomputed atlas and a requested scan is not independent replication."]),
    conceptIds: ["tcga_reference_scale", "study_effect", "within_cancer_synthesis", "hierarchical_iqr_scale", "prediction_interval", "association_not_causation"],
    citationIds: ["cox-1972", "benjamini-hochberg-1995", "higgins-thompson-2002", "hartung-knapp-2001", "int-hout-2014", "riley-2011"],
  }),
  "session.exploration_ledger": defineContract({
    id: "session.exploration_ledger",
    module: "session",
    question: "Which analyses were run in this browser, with what settings and results?",
    unitOfAnalysis: "One recorded run with parameters, version, status and timing.",
    decisionTarget: "Reconstruct exploration and define any retrospective family explicitly.",
    reference: "The chronological record, not a rewritten analysis plan.",
    scale: "Run metadata; incompatible effect scales remain separate.",
    inferentialRole: "audit",
    multiplicity: "A selected set of historical runs is post hoc unless independently prespecified.",
    assumptions: Object.freeze(["Recording was enabled and the local record has not been mistaken for permanent storage."]),
    diagnostics: Object.freeze(["Statuses, failures, parameter compatibility and decision timing."]),
    cannotConclude: Object.freeze(["Run history is not preregistration and does not prove robustness by itself."]),
    conceptIds: ["prespecification", "multiplicity_family", "provenance"],
    citationIds: ["wilkinson-2016"],
  }),
  "pancancer.tcga_reference": defineContract({
    id: "pancancer.tcga_reference",
    module: "pancancer",
    question: "How consistent is a marker association across eligible TCGA cancers?",
    unitOfAnalysis: "One eligible TCGA cancer cohort; patients are never pooled across cancers.",
    estimand: "Separate cancer-specific Cox associations represented either per +1 common input-score unit or per +1 within-cancer expression SD.",
    reference: "A value one selected effect unit lower within the same TCGA cancer.",
    scale: "When a transportable common input-score unit is synthesis-eligible, the forest opens on that common scale and only that view may show the REML/HKSJ pooled estimate. The within-cancer SD view is descriptive and never pooled. Neither scale is the hierarchical within-study IQR.",
    inferentialRole: "cross_cancer_reference",
    multiplicity: "BH is applied across the declared eligible cancer family.",
    assumptions: Object.freeze(["Each cancer is analyzed separately with the same endpoint and information rules.", "Pooling is allowed only when the analysis explicitly reports a transportable common input-score unit and synthesis eligibility."]),
    diagnostics: Object.freeze(["Selected scale and synthesis eligibility.", "Patients, events, precision, FDR and concordance by cancer."]),
    cannotConclude: Object.freeze(["A cross-cancer summary is not a universal effect and does not validate external studies.", "A shared numerical unit does not by itself harmonize cancer biology."]),
    conceptIds: ["tcga_reference_scale", "hazard_ratio", "fdr", "association_not_causation"],
    citationIds: ["cox-1972", "benjamini-hochberg-1995", "higgins-thompson-2002", "hartung-knapp-2001", "int-hout-2014", "riley-2011"],
  }),
  "pancancer.hierarchical": defineContract({
    id: "pancancer.hierarchical",
    module: "pancancer",
    question: "Does a marker association hold across independent studies and cancers that estimate compatible effects?",
    unitOfAnalysis: "One fixed study release. Study estimates are combined within each cancer before synthesis across cancers.",
    estimand: "Cox HR per one expression IQR within each study. Study effects are combined within each cancer; compatible effects from the selected replicated cancers form the two-stage global summary.",
    reference: "A value one expression IQR lower in the same study.",
    scale: "HR per +1 within-study IQR; never substitute either TCGA reference view: the common input-score unit or the descriptive within-cancer SD.",
    inferentialRole: "hierarchical_transportability",
    multiplicity: "Benjamini-Hochberg FDR is calculated only across cancer effects supported by at least two independent studies. Study effects and singleton-cancer effects are descriptive; primary and exploratory sensitivity sets remain separate.",
    assumptions: Object.freeze(["Studies are analyzed separately and have compatible endpoints and effect units.", "Eligibility is fixed during the study check. Patient overlap is reviewed, and studies with unresolved dependence are excluded before synthesis.", "The deployed two-stage summary uses REML random effects, modified HKSJ intervals and a 95% prediction interval when estimable; its evidence threshold is not a calibration guarantee."]),
    diagnostics: Object.freeze(["Study and cancer heterogeneity.", "Modified-HKSJ floor status.", "Prediction interval and unavailable-study reasons.", "Leave-one-out influence and clearly labeled sensitivity analyses."]),
    cannotConclude: Object.freeze(["The two-stage summary is not a universal effect, and IQR scaling does not harmonize assay biology.", "Meeting the evidence threshold does not establish nominal interval coverage."]),
    conceptIds: ["study_effect", "within_cancer_synthesis", "hierarchical_iqr_scale", "reml", "modified_hksj", "prediction_interval"],
    citationIds: ["higgins-thompson-2002", "hartung-knapp-2001", "int-hout-2014", "riley-2011"],
  }),
  "examples.synthetic_case": defineContract({
    id: "examples.synthetic_case",
    module: "examples",
    question: "What can you conclude from this synthetic example?",
    unitOfAnalysis: "One immutable synthetic teaching case, not a computed analysis result.",
    decisionTarget: "Understand the interpretation supported by the case and where that interpretation stops.",
    reference: "The versioned evidence in the public teaching artifact.",
    scale: "The units stated in the synthetic example.",
    inferentialRole: "teaching",
    multiplicity: "No hypothesis family is tested by reading the teaching case.",
    assumptions: Object.freeze(["The case remains separate from the current analysis."]),
    diagnostics: Object.freeze(["The explanatory conclusion matches the versioned evidence and its stated limitations."]),
    cannotConclude: Object.freeze(["Synthetic values are not observations from TCGA, an external cohort or the user's data."]),
    conceptIds: ["estimand", "reference_group", "association_not_causation"],
    citationIds: [],
  }),
  "repository.independent_validation": defineContract({
    id: "repository.independent_validation",
    module: "repository",
    question: "Is an external cohort compatible with a validation hypothesis fixed before cohort search?",
    unitOfAnalysis: "One independent, versioned study release analyzed separately.",
    estimand: "The original effect reproduced as closely as the external endpoint, platform and metadata permit.",
    reference: "The reference fixed in the validation protocol.",
    scale: "The audited within-study scale; cross-study synthesis requires an explicitly compatible effect unit.",
    inferentialRole: "validation",
    multiplicity: "Marker, endpoint, direction and success criterion are fixed before catalog results are inspected.",
    assumptions: Object.freeze(["Independence, licensing, endpoint definition, patient linkage and provenance are reviewed."]),
    diagnostics: Object.freeze(["Patients, events, platform, scale, missingness and differences from the index cohort."]),
    cannotConclude: Object.freeze(["A same-name endpoint is not automatically equivalent, and cohort selection after seeing results is not independent validation."]),
    conceptIds: ["validation", "provenance", "study_effect", "estimand"],
    citationIds: ["wilkinson-2016"],
  }),
  "dataset.eligibility": defineContract({
    id: "dataset.eligibility",
    module: "summary",
    question: "Does the selected dataset contain enough eligible patient-level information for the planned analysis?",
    unitOfAnalysis: "Unique eligible patients, distinguished from RNA samples and files.",
    decisionTarget: "Decide whether the cohort and endpoint are suitable before fitting a model.",
    reference: "The declared eligibility and sample-prioritization rules.",
    scale: "Counts of patients, samples, events and nonmissing clinical fields.",
    inferentialRole: "eligibility",
    multiplicity: "No hypothesis family is tested by the coverage view.",
    assumptions: Object.freeze(["Patient identifiers, sample priorities and endpoint availability are correctly represented."]),
    diagnostics: Object.freeze(["Patient/sample denominator, event count, missingness and clinical-variable coverage."]),
    cannotConclude: Object.freeze(["A large sample count does not guarantee an informative or unbiased analysis."]),
    conceptIds: ["population", "endpoint", "provenance"],
    citationIds: ["wilkinson-2016"],
  }),
  "api.reproducible_query": defineContract({
    id: "api.reproducible_query",
    module: "api",
    question: "Can a public analysis be reconstructed from explicit machine-readable parameters and versions?",
    unitOfAnalysis: "One versioned API or MCP request and its returned audit artifacts.",
    decisionTarget: "Verify that the programmatic request and the interface describe the same public analysis.",
    reference: "The explicit request, returned parameters and pinned pipeline version.",
    scale: "Machine-readable parameters and result units declared by the endpoint.",
    inferentialRole: "reproducibility",
    multiplicity: "Batch failures and all requested analyses remain visible.",
    assumptions: Object.freeze(["No sensitive identifiers are sent and implicit defaults are not relied upon."]),
    diagnostics: Object.freeze(["Request, response status, returned parameters, versions and artifact hashes."]),
    cannotConclude: Object.freeze(["Assistant prose is not evidence until checked against returned artifacts."]),
    conceptIds: ["provenance", "estimand"],
    citationIds: ["wilkinson-2016"],
  }),
  "methods.reference": defineContract({
    id: "methods.reference",
    module: "help",
    question: "What effect does this method estimate, and which assumptions and checks affect its interpretation?",
    unitOfAnalysis: "One versioned method definition linked to an analytical decision.",
    decisionTarget: "Choose suitable settings and interpretation before running.",
    reference: "The method version reported with the analysis.",
    scale: "The units declared for the effect being interpreted.",
    inferentialRole: "reference",
    multiplicity: "The relevant family is defined by the selected analytical module, not by the Methods page.",
    assumptions: Object.freeze(["Definitions are consulted before interpreting unexpected results."]),
    diagnostics: Object.freeze(["Reference, scale, assumptions, version and interpretation boundary are recorded."]),
    cannotConclude: Object.freeze(["A method definition cannot validate a result whose data and diagnostics were not reviewed."]),
    conceptIds: ["estimand", "reference_group", "confidence_interval", "association_not_causation"],
    citationIds: [
      "cox-1972",
      "schoenfeld-1982",
      "welch-1947",
      "mann-whitney-1947",
      "subramanian-2005",
      "wu-smyth-2012",
      "go-consortium-2023",
      "simonsohn-2020",
      "benjamini-hochberg-1995",
      "higgins-thompson-2002",
      "hartung-knapp-2001",
      "int-hout-2014",
      "riley-2011",
      "wilkinson-2016",
    ],
  }),
});

export const SCIENTIFIC_CONTRACT_IDS = Object.freeze(Object.keys(SCIENTIFIC_CONTRACTS));

export const MODULE_SCIENTIFIC_CONTRACT_IDS = Object.freeze({
  home: "orientation.question",
  analysis: "survival.continuous",
  compare: "compare.cutpoint_sensitivity",
  expression: "expression.two_group",
  gsea: "gsea.preranked",
  multiverse: "multiverse.specification_family",
  session: "session.exploration_ledger",
  pancancer: "pancancer.tcga_reference",
  examples: "examples.synthetic_case",
  repository: "repository.independent_validation",
  summary: "dataset.eligibility",
  api: "api.reproducible_query",
  help: "methods.reference",
});

export function getScientificContract(contractId) {
  const record = SCIENTIFIC_CONTRACTS[contractId];
  if (!record) return null;
  return Object.freeze({
    id: record.id,
    module: record.module,
    question: record.question ?? null,
    unitOfAnalysis: record.unitOfAnalysis ?? null,
    estimand: record.estimand ?? null,
    decisionTarget: record.decisionTarget ?? null,
    reference: record.reference ?? null,
    scale: record.scale ?? null,
    inferentialRole: record.inferentialRole,
    multiplicity: record.multiplicity ?? null,
    assumptions: Object.freeze([...(record.assumptions || [])]),
    diagnostics: Object.freeze([...(record.diagnostics || [])]),
    cannotConclude: Object.freeze([...(record.cannotConclude || [])]),
    conceptIds: record.conceptIds,
    citationIds: record.citationIds,
  });
}

export function scientificContractIdForModule(module) {
  return MODULE_SCIENTIFIC_CONTRACT_IDS[module] || null;
}

export function scientificContractIdForStep(step) {
  if (step?.scientificContractId) return step.scientificContractId;
  if (
    step?.presetId === "pancancer-hierarchical-cdc20"
    || (step?.anchor === "pancancer.preflight" && step?.id !== "eligibility")
  ) {
    return "pancancer.hierarchical";
  }
  return scientificContractIdForModule(step?.module);
}

export const TUTORIAL_CAPABILITIES = Object.freeze({
  DATASET_CATALOG: "dataset.catalogAvailable",
  SURVIVAL_DATA_CONFIGURED: "survival.dataConfigured",
  SURVIVAL_MARKER_CONFIGURED: "survival.markerConfigured",
  SURVIVAL_OUTCOME_CONFIGURED: "survival.outcomeConfigured",
  SURVIVAL_DESIGN_READY: "survival.designReady",
  SURVIVAL_RESULT: "survival.resultAvailable",
  COMPARE_RESULT: "compare.resultAvailable",
  EXPRESSION_GROUPS: "expression.groupsAvailable",
  EXPRESSION_RESULT: "expression.resultAvailable",
  GSEA_RESULT: "gsea.resultAvailable",
  MULTIVERSE_RESULT: "multiverse.resultAvailable",
  SESSION_RUNS: "session.runsAvailable",
  REPOSITORY_CATALOG: "repository.catalogAvailable",
  PANCANCER_TCGA_RESULT: "pancancer.tcgaResultAvailable",
  PANCANCER_RESULT: "pancancer.resultAvailable",
  PANCANCER_HIERARCHICAL_UNIVERSE: "pancancer.hierarchicalUniverseAvailable",
  PANCANCER_HIERARCHICAL_RESULT: "pancancer.hierarchicalResultAvailable",
  API_PUBLIC: "api.publicAvailable",
});

export const TUTORIAL_CAPABILITY_LABELS = Object.freeze({
  [TUTORIAL_CAPABILITIES.DATASET_CATALOG]: "Dataset catalog loaded",
  [TUTORIAL_CAPABILITIES.SURVIVAL_DATA_CONFIGURED]: "Survival data selected",
  [TUTORIAL_CAPABILITIES.SURVIVAL_MARKER_CONFIGURED]: "Valid survival marker",
  [TUTORIAL_CAPABILITIES.SURVIVAL_OUTCOME_CONFIGURED]: "Eligible survival endpoint",
  [TUTORIAL_CAPABILITIES.SURVIVAL_DESIGN_READY]: "Survival design ready to review",
  [TUTORIAL_CAPABILITIES.SURVIVAL_RESULT]: "Survival result",
  [TUTORIAL_CAPABILITIES.COMPARE_RESULT]: "Comparison result",
  [TUTORIAL_CAPABILITIES.EXPRESSION_GROUPS]: "Eligible two-group contrast",
  [TUTORIAL_CAPABILITIES.EXPRESSION_RESULT]: "Expression comparison result",
  [TUTORIAL_CAPABILITIES.GSEA_RESULT]: "GSEA result",
  [TUTORIAL_CAPABILITIES.MULTIVERSE_RESULT]: "Robustness result",
  [TUTORIAL_CAPABILITIES.SESSION_RUNS]: "At least one recorded run",
  [TUTORIAL_CAPABILITIES.REPOSITORY_CATALOG]: "External-study catalog loaded",
  [TUTORIAL_CAPABILITIES.PANCANCER_TCGA_RESULT]: "TCGA reference result",
  [TUTORIAL_CAPABILITIES.PANCANCER_RESULT]: "Result in the selected pan-cancer mode",
  [TUTORIAL_CAPABILITIES.PANCANCER_HIERARCHICAL_UNIVERSE]: "Studies checked for hierarchical analysis",
  [TUTORIAL_CAPABILITIES.PANCANCER_HIERARCHICAL_RESULT]: "Hierarchical result",
  [TUTORIAL_CAPABILITIES.API_PUBLIC]: "Public API available",
});

export function getTutorialCapabilityLabel(capability) {
  return TUTORIAL_CAPABILITY_LABELS[capability] || capability;
}

export function tutorialRequirement(capability, options = {}) {
  return Object.freeze({
    id: options.id || capability,
    capability,
    blocking: options.blocking === true,
    jumpWhenAvailable: options.jumpWhenAvailable === true,
  });
}

export function requirementsForTutorialStep(step) {
  if (step?.requirements) return Object.freeze([...step.requirements]);
  if (step?.anchor === "pancancer.preflight" && step?.id === "eligibility") {
    return Object.freeze([]);
  }
  if (step?.anchor === "pancancer.results") {
    const capability = step.id === "interpret"
      ? TUTORIAL_CAPABILITIES.PANCANCER_RESULT
      : step.scientificContractId === "pancancer.hierarchical"
      ? TUTORIAL_CAPABILITIES.PANCANCER_HIERARCHICAL_RESULT
      : TUTORIAL_CAPABILITIES.PANCANCER_TCGA_RESULT;
    return Object.freeze([tutorialRequirement(capability, {
      blocking: true,
      jumpWhenAvailable: true,
    })]);
  }
  const anchorRequirements = {
    "survival.marker": TUTORIAL_CAPABILITIES.SURVIVAL_DATA_CONFIGURED,
    "survival.outcome": TUTORIAL_CAPABILITIES.SURVIVAL_MARKER_CONFIGURED,
    "survival.clinical": TUTORIAL_CAPABILITIES.SURVIVAL_OUTCOME_CONFIGURED,
    "survival.review": TUTORIAL_CAPABILITIES.SURVIVAL_DESIGN_READY,
    "survival.results": TUTORIAL_CAPABILITIES.SURVIVAL_RESULT,
    "survival.diagnostics": TUTORIAL_CAPABILITIES.SURVIVAL_RESULT,
    "survival.downloads": TUTORIAL_CAPABILITIES.SURVIVAL_RESULT,
    "compare.results": TUTORIAL_CAPABILITIES.COMPARE_RESULT,
    "expression.groups": TUTORIAL_CAPABILITIES.EXPRESSION_GROUPS,
    "expression.results": TUTORIAL_CAPABILITIES.EXPRESSION_RESULT,
    "gsea.results": TUTORIAL_CAPABILITIES.GSEA_RESULT,
    "multiverse.results": TUTORIAL_CAPABILITIES.MULTIVERSE_RESULT,
    "session.ledger": TUTORIAL_CAPABILITIES.SESSION_RUNS,
    "session.interpretation": TUTORIAL_CAPABILITIES.SESSION_RUNS,
    "repository.finder": TUTORIAL_CAPABILITIES.REPOSITORY_CATALOG,
    "repository.provenance": TUTORIAL_CAPABILITIES.REPOSITORY_CATALOG,
    "pancancer.preflight": TUTORIAL_CAPABILITIES.PANCANCER_HIERARCHICAL_UNIVERSE,
    "api.rest": TUTORIAL_CAPABILITIES.API_PUBLIC,
    "api.connectors": TUTORIAL_CAPABILITIES.API_PUBLIC,
  };
  const capability = anchorRequirements[step?.anchor];
  if (!capability) return Object.freeze([]);
  const blockingAnchors = new Set([
    "survival.marker",
    "survival.outcome",
    "survival.clinical",
    "survival.review",
    "survival.results",
    "survival.diagnostics",
    "survival.downloads",
    "compare.results",
    "expression.results",
    "gsea.results",
    "multiverse.results",
    "session.ledger",
    "session.interpretation",
    "repository.provenance",
  ]);
  const jumpWhenAvailableAnchors = new Set([
    "survival.results",
    "survival.diagnostics",
    "survival.downloads",
    "compare.results",
    "expression.results",
    "gsea.results",
    "multiverse.results",
    "session.ledger",
    "session.interpretation",
    "repository.provenance",
  ]);
  return Object.freeze([
    tutorialRequirement(capability, {
      blocking: blockingAnchors.has(step.anchor),
      jumpWhenAvailable: jumpWhenAvailableAnchors.has(step.anchor),
    }),
  ]);
}

export function evaluateTutorialRequirements(requirements, capabilities = {}) {
  const missing = (requirements || []).filter(
    (requirement) => capabilities[requirement.capability] !== true,
  );
  const missingBlocking = missing.filter((requirement) => requirement.blocking);
  return Object.freeze({
    available: missingBlocking.length === 0,
    missing: Object.freeze(missing),
    missingIds: Object.freeze(missing.map((requirement) => requirement.id)),
  });
}

export function scientificContractRegistryErrors() {
  const errors = [];
  for (const contract of Object.values(SCIENTIFIC_CONTRACTS)) {
    for (const conceptId of contract.conceptIds) {
      if (!TUTORIAL_CONCEPT_IDS.includes(conceptId)) {
        errors.push(`${contract.id} references unknown concept ${conceptId}.`);
      }
    }
    for (const citationId of contract.citationIds) {
      if (!TUTORIAL_CITATION_IDS.includes(citationId)) {
        errors.push(`${contract.id} references unknown citation ${citationId}.`);
      }
    }
  }
  return errors;
}
