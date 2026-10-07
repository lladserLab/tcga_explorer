/** Stable English concepts used by Guides. IDs remain presentation-neutral. */

function concept(id, term, definition) {
  return Object.freeze({ id, term, definition });
}

export const TUTORIAL_CONCEPTS = Object.freeze({
  population: concept(
    "population",
    "Population",
    "The patients who meet the eligibility rules and are actually included in the analysis.",
  ),
  endpoint: concept(
    "endpoint",
    "Endpoint",
    "The outcome being studied, including when follow-up starts, what counts as an event, how censoring works and the time unit.",
  ),
  estimand: concept(
    "estimand",
    "Estimand",
    "What the analysis estimates: for which patients, which comparison and which effect unit.",
  ),
  reference_group: concept(
    "reference_group",
    "Reference",
    "The group or value used as the baseline for a comparison.",
  ),
  hazard_ratio: concept(
    "hazard_ratio",
    "Hazard ratio",
    "The ratio of instantaneous event rates in a Cox model, for the stated groups or marker increase.",
  ),
  confidence_interval: concept(
    "confidence_interval",
    "Confidence interval",
    "An interval describing sampling uncertainty under the fitted model. It does not give the probability that the fixed true effect lies inside this particular interval.",
  ),
  continuous_primary: concept(
    "continuous_primary",
    "Continuous primary effect",
    "The primary marker effect estimated without dividing expression into groups. Grouped plots provide supporting sensitivity analyses.",
  ),
  cutpoint: concept(
    "cutpoint",
    "Cutpoint",
    "A threshold or rule for dividing a continuous marker into groups. The rule changes the comparison and how much information it retains.",
  ),
  proportional_hazards: concept(
    "proportional_hazards",
    "Proportional hazards",
    "The assumption that the hazard ratio stays constant over follow-up. The event rates themselves can still change over time.",
  ),
  multiplicity_family: concept(
    "multiplicity_family",
    "Multiplicity family",
    "The tests or analysis choices covered by one multiple-testing correction and report.",
  ),
  fdr: concept(
    "fdr",
    "False discovery rate",
    "The expected proportion of false discoveries among discoveries within the declared testing family under the procedure's assumptions.",
  ),
  contrast_b_minus_a: concept(
    "contrast_b_minus_a",
    "B minus A contrast",
    "Group A is the reference. A positive difference means the reported measure is higher in Group B.",
  ),
  welch_test: concept(
    "welch_test",
    "Welch test",
    "A two-group mean comparison that does not require equal variances.",
  ),
  mann_whitney: concept(
    "mann_whitney",
    "Mann-Whitney test",
    "A comparison of ranked values between two groups. It can detect distributional differences and is not generally a test of medians alone.",
  ),
  within_gene_zscore: concept(
    "within_gene_zscore",
    "Within-gene z-score",
    "For plotting, each gene is scaled relative to its own values across the included samples. Colors show which patients have higher or lower values for that gene, not which gene is more abundant.",
  ),
  nes: concept(
    "nes",
    "Normalized enrichment score",
    "A gene-set enrichment score normalized for gene-set properties; its sign follows the declared ranking direction.",
  ),
  leading_edge: concept(
    "leading_edge",
    "Leading edge",
    "The subset of genes contributing to the enrichment peak for that set in the observed ranking.",
  ),
  circularity: concept(
    "circularity",
    "Circular analysis",
    "Using the same signal to create groups or choose genes and then presenting its test as independent evidence.",
  ),
  specification_curve: concept(
    "specification_curve",
    "Specification curve",
    "A plot of results across planned analysis choices. It also identifies analyses that could not be estimated.",
  ),
  prespecification: concept(
    "prespecification",
    "Prespecification",
    "A decision recorded before inspecting the outcomes it can influence.",
  ),
  validation: concept(
    "validation",
    "Independent validation",
    "Evaluation of a fixed hypothesis and compatible estimand in data not used to generate that hypothesis.",
  ),
  provenance: concept(
    "provenance",
    "Provenance",
    "A record of where the data came from, which version was used and how it was prepared before analysis.",
  ),
  study_effect: concept(
    "study_effect",
    "Study-specific effect",
    "An effect estimated in one study, before combining results across studies or cancers.",
  ),
  within_cancer_synthesis: concept(
    "within_cancer_synthesis",
    "Within-cancer synthesis",
    "A combined estimate from independent studies of the same cancer that estimate a compatible effect. This step comes before synthesis across cancers.",
  ),
  reml: concept(
    "reml",
    "REML random effects",
    "A random-effects method that uses restricted maximum likelihood to estimate variation in true effects between studies or cancers.",
  ),
  modified_hksj: concept(
    "modified_hksj",
    "Modified HKSJ inference",
    "Hartung-Knapp-Sidik-Jonkman inference for random-effects estimates. The variance scale has a minimum of one to prevent an adjustment that could make intervals too narrow.",
  ),
  prediction_interval: concept(
    "prediction_interval",
    "Prediction interval",
    "A random-effects interval describing the range expected for a compatible future unit, conditional on the synthesis model and estimated heterogeneity.",
  ),
  tcga_reference_scale: concept(
    "tcga_reference_scale",
    "TCGA reference effect scales",
    "Cancer-specific effects can be viewed per one common input-score unit when transportable, or descriptively per one within-cancer expression SD. Only the eligible common-unit view may be pooled.",
  ),
  hierarchical_iqr_scale: concept(
    "hierarchical_iqr_scale",
    "Within-study IQR scale",
    "The hierarchical hazard ratio describes an expression increase from the 25th to the 75th percentile within each study. Studies are analyzed separately.",
  ),
  association_not_causation: concept(
    "association_not_causation",
    "Association is not causation",
    "An observational association does not by itself establish a causal or mechanistic effect.",
  ),
});

export const TUTORIAL_CONCEPT_IDS = Object.freeze(Object.keys(TUTORIAL_CONCEPTS));

export function getTutorialConcept(conceptId) {
  return TUTORIAL_CONCEPTS[conceptId] || null;
}

export function resolveTutorialConcepts(conceptIds) {
  return Object.freeze(
    (conceptIds || []).map((conceptId) => getTutorialConcept(conceptId)).filter(Boolean),
  );
}
