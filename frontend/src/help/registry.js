/**
 * Single source of in-place help for every TRACE Explorer control.
 *
 * One entry per control, split into three fixed slots so help is answerable
 * rather than narrative:
 *
 *   does        - what this control does.
 *   changes     - what changes in the result when the value changes.
 *   safeDefault - what to choose when the user is unsure.
 *
 * Statistical vocabulary is NOT duplicated here. Terms live once in
 * `tutorials/conceptRegistry` and are surfaced in place through `<Term>`, so a
 * definition never drifts between the workspace, the tutorials and Methods.
 *
 * Help and guide copy is English only. Stable identifiers remain
 * presentation-neutral so a future language change must be made centrally.
 */

import {
  TUTORIAL_CONCEPT_IDS,
  getTutorialConcept,
} from "../tutorials/conceptRegistry";

/** The language every help entry and glossary lookup is written in. */
export const HELP_LANGUAGE = "en";

// Reviewed video walkthroughs are available in English.
export const GUIDE_VIDEO_COPY = Object.freeze({
  watch: "Watch video",
  close: "Close video",
  silent: "No audio · instructions on screen",
  open: "Open video in a new tab",
  error: "The video could not be loaded. Try the direct link or continue with the written guide.",
  homeTitle: "New to TRACE?",
  homeDescription: "Watch a walkthrough before you start. 7 quick guides",
  browse: "Browse video guides",
});

export const HELP_SLOTS = Object.freeze(["does", "changes", "safeDefault"]);

const ZSCORE_TRANSPORTABILITY =
  "Z-score signature genes are standardized among the expression-complete patients eligible in this run. Changing the endpoint or filters can change the patients used for standardization and their scores. Do not compare numerical z-score signature values across runs.";

const COMPETING_RISK =
  "For DSS, DFI and PFI, Kaplan-Meier and Cox treat a competing death as censoring and estimate event-free survival or a cause-specific hazard. When TCGA-CDR competing-event coding is available, the same result also reports cumulative incidence, Gray's test and Fine-Gray subdistribution hazard ratios. Cause-specific hazard and cumulative incidence answer different questions; interpret each on its own scale.";

export const HELP_ENTRIES = Object.freeze({
  desktopInstallation: {
    term: "Desktop installation and data",
    does: "The desktop app runs analyses on your computer and keeps uploaded datasets and results there. Python and R are included; you do not need Docker.",
    changes: "Cohorts are added separately through Manage data. Import a TRACE .tar.gz package from your computer, or download one when a catalog link is configured. You can work offline once the data are installed.",
    safeDefault: "Choose the download for your system and processor. Linux x64 requires glibc 2.39 or later, as in Ubuntu 24.04: allow the AppImage to run as a program in file Properties, then open it. Windows is unsigned; macOS is not notarized and requires Apple Silicon. The macOS build was tested on macOS 14.",
  },
  resultPhFlag: {
    term: "Model check flagged",
    does: "A proportional hazards check flagged this model. Review the model checks before interpreting a constant hazard ratio.",
    changes: "A marker-specific flag can lead to a two-period effect estimate when follow-up supports it. A global flag may concern another model term.",
    safeDefault: "Inspect the flagged terms and any time-varying estimates.",
  },
  resultPanCancerEffects: {
    term: "Effects by cancer",
    does: "Each row shows one cancer's estimate and confidence interval.",
    changes: "A hazard ratio below 1 indicates a lower event hazard with higher expression; above 1 indicates a higher hazard. Intervals crossing 1 include the null effect.",
    safeDefault: "Read cancer-specific intervals before interpreting a pooled estimate.",
  },
  resultPanCancerTable: {
    term: "Cancer statistics",
    does: "Compare unadjusted estimates with the stage- and grade-adjusted models.",
    changes: "Adjusted models may use fewer patients with complete data. Missing clinical fields are marked not evaluable.",
    safeDefault: "Check patient counts and model availability before comparing estimates.",
  },
  resultExpressionView: {
    term: "Expression effects",
    does: "Differences are target minus reference. Welch and Mann–Whitney tests have separate BH corrections.",
    changes: "The summary shows how large the difference is, its uncertainty and the group sizes. Full statistics include Hedges g, distributions, raw p-values and rank effects.",
    safeDefault: "Read effect size and uncertainty together with corrected p values.",
  },
  resultContinuousView: {
    term: "Continuous analysis",
    does: "Primary analysis. Uses expression as a continuous measure.",
    changes: "The hazard ratio describes a one-standard-deviation increase. The spline curve shows how the association varies across the expression range.",
    safeDefault: "Read the effect and its confidence interval, then inspect the model checks.",
  },
  resultGroupedView: {
    term: "Survival groups",
    does: "Sensitivity analysis. Compares the groups defined by your cutpoint.",
    changes: "Group sizes and effects depend on the selected cutpoint. Adjusted models may use fewer patients with complete clinical data.",
    safeDefault: "Use the continuous model as the primary analysis and the grouped result as a sensitivity analysis.",
  },
  resultCombinedView: {
    term: "Combined groups",
    does: "Compares survival across the combined expression groups.",
    changes: "The signature effects tab reports each score and their interaction.",
    safeDefault: "Read group sizes before interpreting their survival curves.",
  },
  resultCompetingView: {
    term: "Competing risks",
    does: "Estimates event probability while accounting for competing deaths.",
    changes: "Fine-Gray effects describe the subdistribution hazard; they differ from cause-specific Cox effects.",
    safeDefault: "Read cumulative incidence and event counts alongside the effect estimates.",
  },
  clinicalAdjustmentUnavailable: {
    term: "No usable clinical covariates in this cohort",
    does: "This cohort has no clinical fields suitable for adjustment. Continue without adjustment, or add patient-matched covariates in the Clinical step.",
    changes: "This cohort has no standard clinical covariates with usable variation. Survival outcomes and marker-only models can still be available.",
    safeDefault: "Continue unadjusted, or add covariates before requesting clinical adjustment.",
  },
  // ---------------------------------------------------------------- Dataset
  dataset: Object.freeze({
    term: "Dataset",
    does: "Choose one TCGA cohort, one release of an external study or one private upload.",
    changes: "Changing the source changes the patients and expression measurements. TRACE checks outcome eligibility and selects one expression-complete sample per patient using that source's rule.",
    safeDefault: "Choose the cohort that matches your question. Releases are analyzed separately.",
  }),
  repository: Object.freeze({
    term: "Independent cohort repository",
    does: "Find public bulk RNA-seq cohorts and check which analyses each release supports.",
    changes: "TRACE checks eligibility separately for expression, GSEA and survival. A cohort without survival data may still support molecular analyses. Each release stays separate.",
    safeDefault: "Choose the analysis first, then select a ready release with the clinical context your question requires.",
  }),
  userDataset: Object.freeze({
    term: "Private upload",
    does: "Upload one de-identified expression table and one patient-metadata table. A time-to-event outcome is optional, and patient identifiers must match exactly.",
    changes: "TRACE keeps the normalized expression matrix, selected metadata and any mapped outcome for 24 hours. It discards the original files after validation. Patients with incomplete outcomes can still enter molecular analyses, but not survival models. GSEA also needs enough measured genes.",
    safeDefault: "Map your patient variables, confirm the expression scale and check that patient IDs match before running.",
  }),
  defaultAnalysis: Object.freeze({
    term: "Default analysis path",
    does: "For a TCGA cohort, the default Survival path uses one gene, OS, log2(TPM + 1), no clinical filters, age adjustment and a median split; private uploads require an explicit source-scale choice.",
    changes: "It reports the cutpoint-independent continuous Cox model first, adds the spline when at least 30 events are available, and treats Kaplan-Meier, grouped Cox and RMST as median-split sensitivities.",
    safeDefault: "Start with these settings for a single-gene TCGA question. Use Robustness to examine a planned set of alternative choices.",
  }),

  // ---------------------------------------------------------------- Marker
  analysisDesign: Object.freeze({
    term: "Gene analysis",
    does: "Analyze genes separately, combine a gene set into one score, or test a prespecified interaction between two signatures. The first two options include continuous and grouped survival analyses.",
    changes: "Signature panel compares 2 to 6 continuous scores through common-population univariable, joint and clinically adjusted Cox main-effects models, without interactions or Kaplan-Meier grouping.",
    safeDefault: "Use separate genes for individual markers, one signature for a gene program, or an interaction or panel when your question needs it.",
  }),
  geneMode: Object.freeze({
    term: "Gene mode",
    does: "Single genes are analyzed independently. Multi-gene modes calculate one signature score per patient before creating groups.",
    changes: "Switching from single to multi-gene replaces several independent results with one score whose meaning depends on the scoring method.",
    safeDefault: "Single gene keeps each result interpretable on its own.",
  }),
  survivalSingleGenes: Object.freeze({
    term: "Genes analyzed separately",
    does: "Enter or paste one or more gene symbols. Each gene gets its own survival analysis, not a combined score.",
    changes: "To study a gene set as one marker, choose a signature scoring method below.",
    safeDefault: "Choose the genes before viewing results. Use Compare or Robustness to assess a declared family of comparisons.",
  }),
  survivalMetadata: Object.freeze({
    term: "Loading cohort details",
    does: "Checking available outcomes, clinical fields and expression layers. You can explore the steps while these load; running requires a successful check.",
  }),
  survivalMetadataError: Object.freeze({
    term: "Cohort details could not be loaded",
    does: "These details are needed before starting a new analysis. Retry to check outcomes, clinical fields and expression layers for the selected source.",
  }),
  survivalPreviousResult: Object.freeze({
    term: "Results from an earlier configuration",
    does: "Your settings have changed. These results and downloads still describe the submitted analysis. Run again from Review & run to update them.",
  }),
  survivalRecoveredResult: Object.freeze({
    term: "Recovered results",
    does: "These results retain their original analysis settings. They have not been matched to the current controls. Review their recorded settings, or run again to use your current setup.",
  }),
  survivalAgeDefault: Object.freeze({
    term: "Age adjustment",
    does: "Age is selected by default when available. Uncheck Age if it is not part of your planned adjustment. The unadjusted model remains available.",
  }),
  survivalCohortCounts: Object.freeze({
    term: "Cohort totals",
    does: "These are source totals, before selecting a tissue population or applying clinical restrictions. The fitted results report the patients and events used by each model.",
  }),
  survivalEndpointCounts: Object.freeze({
    term: "Endpoint coverage",
    does: "Counts describe patients with this outcome in the source, before your tissue selection, clinical restrictions and complete-case adjustment. Final counts are reported separately for each fitted model.",
  }),
  survivalReviewPreview: Object.freeze({
    term: "Your results will appear here",
    does: "Review the settings and run the analysis. To preview the appearance of your plots first, open Edit plots and exports.",
  }),
  signatureGenes: Object.freeze({
    term: "Signature genes",
    does: "Select the genes that form this signature. Numeric score methods may use weights; rank methods may declare up and down directions.",
    changes: "Adding or removing a gene changes the score of every patient and therefore every downstream cutpoint and model.",
    safeDefault: "Declare the gene list before running; changing it after seeing a result makes the analysis exploratory.",
  }),
  signatureGenesWeighted: Object.freeze({
    term: "Signature gene list",
    does: "Z-score and Weighted accept GENE:weight. For singscore, ssGSEA and AUCell, plain genes or GENE:1 are up and GENE:-1 is down. The first duplicate is retained and zero weights are rejected.",
    changes: "Weights change numeric contribution; up and down labels change the direction of a rank score. Every requested signature gene must resolve in the selected expression layer.",
    safeDefault: "Use an unweighted list unless weights or directions were defined before analysis.",
  }),

  // ------------------------------------------------------- Scoring methods
  "score.single": Object.freeze({
    term: "Single gene",
    caption: "Analyze one gene",
    does: "Uses the expression of one gene as the marker.",
    changes: "When several genes are entered in single-gene mode, each gene is run as a separate analysis.",
    safeDefault: "Start here for a question about one gene.",
  }),
  "score.mean": Object.freeze({
    term: "Mean signature",
    caption: "Average log-scale expression across genes",
    does: "Averages log-scale expression across genes.",
    changes: "Genes with larger numeric ranges can dominate the average.",
    safeDefault: "Use only when averaging the reported expression scale has a clear biological meaning.",
  }),
  "score.zscore": Object.freeze({
    term: "Z-score signature",
    caption: "Standardize each gene, then average",
    does: "Standardizes each gene across samples, then averages the standardized values. Optional GENE:weight values weight those standardized components; otherwise every weight is 1.",
    changes: ZSCORE_TRANSPORTABILITY,
    safeDefault: "Use this to standardize a score within one run. Choose singscore if your question calls for ranks within each sample.",
  }),
  "score.weighted": Object.freeze({
    term: "Weighted signature",
    caption: "Weighted average using GENE:weight",
    does: "Calculates a weighted score from genes entered as GENE:weight.",
    changes: "Weights apply to log-scale components, so a gene's numeric range still affects its contribution.",
    safeDefault: "Use weights defined in the source signature or your analysis plan.",
  }),
  "score.singscore": Object.freeze({
    term: "singscore",
    caption: "Recommended per-sample rank score for bulk RNA",
    does: "Ranks the full measured gene universe within each sample, then scores the declared up and down signature components with singscore.",
    changes: "The score does not use means or standard deviations from other samples. It still depends on the expression layer, measured gene universe and complete resolution of the signature.",
    safeDefault: "The recommended rank-based option for a prespecified bulk-RNA signature.",
  }),
  "score.ssgsea": Object.freeze({
    term: "ssGSEA",
    caption: "Sample-wise enrichment",
    does: "Calculates a single-sample enrichment score from within-sample gene ranks. TRACE disables normalization across the returned sample scores.",
    changes: "The result still depends on the measured gene universe, expression layer and signature coverage; it is not automatically comparable across assays or studies.",
    safeDefault: "Use when ssGSEA is required by the analysis plan; otherwise start with singscore.",
  }),
  "score.aucell": Object.freeze({
    term: "AUCell",
    caption: "Check signature genes near the top of the ranking",
    does: "Measures whether signature genes occur near the top of each sample's ranked expression profile using a fixed, recorded AUC rank threshold.",
    changes: "Sensitivity depends on signature size, the measured gene universe, ties and the fixed top-rank threshold. Use it as a sensitivity analysis; its values are not a universal activity scale.",
    safeDefault: "Choose AUCell before running and compare it with your primary signature score.",
  }),

  // ------------------------------------------------------------ Endpoint
  survivalEndpoint: Object.freeze({
    term: "Survival endpoint",
    does: "TCGA endpoints come from TCGA-CDR when available: OS, DSS, PFI and DFI. External endpoints retain the release-specific time origin and event definition.",
    changes: "Changing the outcome changes which patients and events enter the analysis. For DSS, DFI and PFI, check the competing-risk results when available.",
    safeDefault: "Choose OS to study death from any cause. Choose another outcome when progression, recurrence or cancer-specific death is the question.",
  }),
  competingRisk: Object.freeze({
    term: "DSS, DFI and PFI competing events",
    does: COMPETING_RISK,
    safeDefault: "Report the estimand you declared; do not switch between cause-specific and subdistribution results after seeing them.",
  }),
  maxFollowup: Object.freeze({
    term: "Maximum follow-up",
    does: "Set a follow-up limit in days. Patients followed longer remain in the analysis, but follow-up stops at this limit and later events are not counted.",
    changes: "A shorter horizon removes late events and can change both the effect estimate and the proportional-hazards diagnostic.",
    safeDefault: "Leave it empty to use the full endpoint follow-up.",
  }),

  // ------------------------------------------------------------ Expression
  expressionScale: Object.freeze({
    term: "Expression data",
    does: "Choose the expression values used in this analysis. TCGA offers normalized scales; external studies offer the layers prepared for their release.",
    changes: "The scale changes the marker values and can change groups or effects. Results from different scales need not agree.",
    safeDefault: "For TCGA tissue expression, start with log2(TPM + 1). For another source, use the prepared layer that matches your question.",
  }),
  expressionUploadScale: Object.freeze({
    term: "Expression scale in your file",
    does: "Choose the scale already present in the file. Do not select a scale you want TRACE to convert it into.",
    changes: "Non-log TPM, FPKM, FPKM-UQ and CPM become log2(x + 1). Broad raw-count matrices become log2(CPM + 1). Declared normalized scales are used as supplied.",
    safeDefault: "Check the file's preparation method. An incorrect scale declaration changes the analysis.",
  }),
  expressionDataSource: Object.freeze({
    term: "Source expression",
    caption: "Expression in the sampled tissue",
    does: "The source layer may contain several tissue types. The tissue selection determines which are analyzed; survival uses one eligible sample per patient.",
  }),
  expressionDataPaired: Object.freeze({
    term: "Paired tumor–adjacent difference",
    caption: "Tumor–adjacent change within each patient",
    does: "Positive values mean higher expression in the tumor; negative values mean higher expression in the matched adjacent tissue.",
    changes: "Only patients with both tissues are included. These are not additional patients, and adjacent tissue is not an independent healthy-control cohort.",
  }),
  expressionDataCoverage: Object.freeze({
    term: "Patients in this expression layer",
    does: "These are source counts, before tissue selection, patient filters and model exclusions. Each fitted model reports its own patient count.",
  }),

  // -------------------------------------------------------- Stratification
  stratification: Object.freeze({
    term: "Stratification",
    does: "Choose how to divide expression or a signature score into groups for Kaplan-Meier, grouped Cox and RMST sensitivity analyses.",
    changes: "The grouped result depends on the rule; the continuous primary result does not.",
    safeDefault: "Start with the median for a reproducible split. Maxstat chooses the cutpoint using survival outcomes and remains exploratory.",
  }),
  panelModelBoundary: Object.freeze({
    term: "Model scope",
    does: "The panel fits the continuous Cox main effects of all selected signatures in the same patients.",
    changes: "It does not search cutpoints, create Kaplan-Meier groups or fit interactions.",
    safeDefault: "Choose the one-signature analysis if you need survival groups.",
  }),
  combinedTertileCrossing: Object.freeze({
    term: "Tertile crossing",
    caption: "Up to nine combined Low/Mid/High groups",
    does: "Tertile crossing creates up to nine combined groups.",
    changes: "Each added stratum reduces the patients and events available per group.",
    safeDefault: "Start with median crossing. Use tertiles only when the extra middle group is needed and patient and event counts support it.",
  }),
  combinedMedianCrossing: Object.freeze({
    term: "Median crossing",
    caption: "Four combined groups: Low_Low through High_High",
    does: "Split each signature at its own median, then combine the labels into four groups: Low_Low, Low_High, High_Low and High_High.",
    changes: "The four groups can have very different sizes, especially when the signatures are correlated. Some combinations may be empty.",
    safeDefault: "Start with median crossing and check the patient and event counts in each combined group.",
  }),
  "cutpoint.maxstat": Object.freeze({
    term: "Maxstat",
    caption: "Survival-optimized cutpoint, min 15% per group",
    does: "Chooses the threshold with strongest survival separation under a minimum group-size constraint.",
    changes: "The reported maxstat p-value accounts for searching cutpoints. The selected groups and their hazard ratio still depend on the outcomes used to choose the split.",
    safeDefault: "Use for discovery, then validate; it is outcome-optimized.",
  }),
  "cutpoint.median": Object.freeze({
    term: "Median",
    caption: "Two balanced expression groups",
    does: "Splits patients into two similarly sized groups.",
    changes: "Group sizes stay balanced regardless of the survival pattern.",
    safeDefault: "The safest default for reproducible Kaplan-Meier stratification.",
  }),
  "cutpoint.tertiles": Object.freeze({
    term: "Tertiles",
    caption: "Low, middle and high groups",
    does: "Splits scores into low, middle and high groups.",
    changes: "Three groups mean binary grouped Cox and RMST are not estimated.",
    safeDefault: "Adds resolution but needs enough patients and events in every group.",
  }),
  "cutpoint.upper_quartile": Object.freeze({
    term: "Upper quartile",
    caption: "Top 25% against the rest",
    does: "Compares the top 25% of expression against the remaining 75%.",
    changes: "The high group is small, so its confidence interval widens.",
    safeDefault: "Useful for high-expression biology with sufficient events.",
  }),
  "cutpoint.upper_lower_quartile": Object.freeze({
    term: "Outer quartiles",
    caption: "Top 25% against bottom 25%",
    does: "Compares the top and bottom quartiles and excludes the middle half.",
    changes: "It sharpens contrast but reduces sample size and changes the analyzed population.",
    safeDefault: "Report the excluded half explicitly when using this rule.",
  }),
  "cutpoint.percentile": Object.freeze({
    term: "Percentile",
    caption: "Custom high-expression threshold",
    does: "Uses the selected percentile as the high-expression threshold.",
    changes: "Changing the percentile changes the tested hypothesis.",
    safeDefault: "Document the percentile you declared before running.",
  }),

  // ------------------------------------------------------- Clinical design
  clinicalFilters: Object.freeze({
    term: "Clinical filters",
    does: "Filters choose who enters the analysis. Selecting stages I and II includes either stage; adding a grade filter requires patients to match that too. Each field shows where its values came from.",
    changes: "Filters can change patient counts, expression scores, cutpoints and events. Select Cox covariates separately. TRACE keeps reported molecular subtypes as supplied.",
    safeDefault: "Add only the subgroup required by the biological question. For a molecular subtype, verify its method and cross-study comparability note first.",
  }),
  clinicalAdjustment: Object.freeze({
    term: "Cox adjustment",
    does: "Add clinical variables to estimate the marker association while accounting for them. Only patients with complete values for all selected variables enter the adjusted model.",
    changes: "Age is continuous per 10 years; stage and grade are ordinal; GDC gender and race are categorical. External CSV variables are linked by exact TCGA participant barcode and use the type, effect unit, level order and reference recorded in the analysis. Missing covariate values reduce only the adjusted model.",
    safeDefault: "Choose the covariates your question requires before running. Compare adjusted and unadjusted estimates and their patient counts.",
  }),
  externalCovariates: Object.freeze({
    term: "External covariates",
    does: "Upload a patient-level CSV with a patient_id column and up to 10 variables. Use public TCGA participant barcodes only, for example TCGA-AB-1234.",
    changes: "The browser validates and configures the data; selected values are included in the analysis request, patient CSV and audit bundle.",
    safeDefault: "Use patient IDs that match the cohort and check how each variable is coded before running. Avoid variables recorded after the outcome.",
  }),

  // --------------------------------------------------------------- Outputs
  continuousModel: Object.freeze({
    term: "Continuous Cox",
    does: "The primary model uses all eligible patients with a complete gene or signature value. Its Cox hazard ratio describes a one-standard-deviation increase within this analysis.",
    changes: "Changing the grouping rule leaves this continuous estimate unchanged.",
    safeDefault: "Report this as the primary result and treat grouped views as supporting evidence.",
  }),
  spline: Object.freeze({
    term: "Restricted cubic spline",
    does: "The spline shows whether the survival association changes across the expression range instead of following one straight-line effect. It is available with at least 30 events and uses three parameters with knots at the 5th, 35th, 65th and 95th percentiles.",
    changes: "The nonlinearity p-value compares the spline with a linear Cox effect.",
    safeDefault: "Compare the curve and its uncertainty with the linear estimate. The nonlinearity test asks about the shape, not whether the marker has any association at all.",
  }),
  rmst: Object.freeze({
    term: "RMST",
    does: "RMST estimates average time alive (for OS), or free of the selected event, up to a fixed follow-up limit. It is reported in days or months.",
    changes: "It complements the hazard ratio, but the group comparison still depends on the selected cutpoint.",
    safeDefault: "Report it on the time scale, in months or days, alongside the hazard ratio.",
  }),
  coxPH: Object.freeze({
    term: "PH diagnostics",
    does: "Checks whether the hazard ratio stays constant over follow-up, using cox.zph for the marker and the full model.",
    changes: "When the marker-specific p-value is below 0.05, TRACE Explorer reports separate marker HRs before and after a fixed 2-year primary split plus fixed 1- and 5-year sensitivities.",
    safeDefault: "These coarse two-period summaries are prespecified, never outcome-optimized, and require support on both sides.",
  }),
  audit: Object.freeze({
    term: "Audit report",
    does: "Download the audit bundle to recover the analysis settings, included patients, outcome source, results and software versions. It also includes file checksums and the R code, renv.lock and Dockerfile needed to rerun the analysis.",
    changes: "SHA-256 values detect drift or corruption. A detached Ed25519 receipt additionally signs the exact audit report and run hash; verify it against the key published by the declared HTTPS server.",
    safeDefault: "Keep the bundle with any result you report. Verify the receipt to check its source, not its scientific validity or publication date.",
  }),
  kaplanMeier: Object.freeze({
    term: "Kaplan-Meier",
    does: "Plots survival curves by expression group and reports log-rank p-values, patient counts, events and median survival when the curve reaches 50%.",
    changes: "The curves depend entirely on the selected cutpoint rule.",
    safeDefault: "Use these curves to show survival in the selected groups. Use the continuous model to assess the marker without a cutpoint.",
  }),
  groupedCox: Object.freeze({
    term: "Grouped Cox models",
    does: "Compares the expression groups without adjustment, with your selected clinical variables, and with stage or grade when available.",
    changes: "Check the patient and event counts for each model. Adjustment can exclude patients with missing clinical values, so a change in HR can reflect both the adjustment and the change in patients.",
    safeDefault: "Read the grouped HR alongside the continuous estimate.",
  }),
  signaturePanel: Object.freeze({
    term: "Signature panel",
    does: "Compare 2-6 signature scores in the same patients. Separate models show each signature on its own; the joint model estimates each association while accounting for the other signatures. Scores are standardized in the shared analysis population.",
    changes: "Outputs include separate univariable models, one joint model and one exact clinically adjusted joint model when requested and evaluable. BH and Bonferroni are reported separately within each model family.",
    safeDefault: "Use this to ask whether signatures carry distinct survival associations. Choose the two-signature interaction mode to test whether one association depends on another score.",
  }),
  sparseEventDiagnostics: Object.freeze({
    term: "Sparse-event diagnostics",
    does: "Reports fitted coefficients and events per parameter for every Cox model.",
    changes: "Fewer than 10 events per fitted coefficient triggers a caution; fewer than 5 triggers a severe caution. A categorical variable can require several coefficients.",
    safeDefault: "Reduce the number of covariates before trusting a model with few events per parameter.",
  }),
  firthSensitivity: Object.freeze({
    term: "Firth sensitivity",
    does: "Runs automatically when a Cox model has low events per parameter, convergence concerns or an extreme marker estimate.",
    changes: "It uses Firth penalized partial likelihood with profile-likelihood confidence intervals.",
    safeDefault: "Compare the Firth estimate with the standard Cox estimate; both remain available.",
  }),
  compareRunSelected: Object.freeze({
    term: "Run selected methods",
    does: "Runs only the cutpoint methods currently selected in Compare analyses.",
    changes: "All requested cells remain visible. The correction covers their valid grouped tests, with missing and failed tests counted separately.",
    safeDefault: "Choose all methods before running so the correction covers the comparisons you planned.",
  }),
  gseaTwoGroup: Object.freeze({
    term: "Two-group GSEA",
    does: "Compare gene sets between groups A and B. CAMERA tests each set while accounting for gene correlation; the ranked enrichment score (NES) describes its direction. Collections use recorded versions of ImmPort and Gene Ontology BP/MF/CC.",
    changes: "Positive NES points toward group B; negative NES points toward group A. Statistical evidence comes from CAMERA p-values with BH correction across the tested sets.",
    safeDefault: "Read the corrected p-value with NES direction. Treat expression-derived or inherited maxstat groups as exploratory.",
  }),
  sessionHistory: Object.freeze({
    term: "Exploratory run history",
    does: "Turn on recording to save accepted analysis requests in this browser.",
    changes: "A selected export deduplicates exact hypotheses, separates continuous, grouped and interaction families, and references Robustness or pan-cancer corrections without recounting them.",
    safeDefault: "Save the complete set of runs relevant to your question. This browser history cannot record analyses performed elsewhere.",
  }),
  plotOutput: Object.freeze({
    term: "Plot output",
    does: "Choose Survival, Continuous Cox or Cox models to edit each exported PNG and SVG independently. The grouped Cox forest can remain combined or export univariable and multivariable model families as separate figures.",
    changes: "In Survival and Compare, the multivariable forest can include every evaluable adjusted model or a declared subset. Changing that subset requires a new run and new downloads.",
    safeDefault: "Titles, contrasts and estimates come from the fitted results. Selecting plots changes which models appear in the figures; it does not change their estimates.",
  }),
  plotAspectRatio: Object.freeze({
    term: "Aspect ratio",
    does: "Aspect ratio is shared by the Survival and Continuous Cox plots.",
    changes: "It affects exported figure geometry only.",
    safeDefault: "Match the aspect ratio to the target journal column width.",
  }),

  // --------------------------------------------------------------- Compare
  compare: Object.freeze({
    term: "Compare analyses",
    does: "Compare analyses runs the same cohort, endpoint and expression scale across many gene by cutpoint combinations.",
    changes: "It then applies BH and Bonferroni correction across valid grouped tests in that batch. Maxstat uses its selection-corrected p-value first.",
    safeDefault: "Choose all genes and cutpoints before running so Compare can correct the planned testing family.",
  }),
  compareMultiplicity: Object.freeze({
    term: "Multiple-testing scope",
    does: "BH and Bonferroni cover the valid grouped tests in the submitted batch. Maxstat uses its selection-corrected p-value; fixed cutpoints use log-rank.",
    changes: "Failed tests and missing corrected p-values are counted but excluded from the correction. Editing controls does not change a completed batch or its summary CSV.",
    safeDefault: "Choose genes, methods and clinical adjustment before viewing results. Continuous Cox, grouped Cox, RMST and other runs are separate evidence, not covered by this family.",
  }),
  compareGenes: Object.freeze({
    term: "Comparison genes",
    does: "Select genes for the comparison matrix. Each selected gene becomes one row.",
    changes: "Adding genes adds tests to the batch and can change the corrected p-values for all genes.",
    safeDefault: "Each gene is analyzed separately; columns test sensitivity to patient stratification. Genes from the same patients need not be statistically independent.",
  }),
  compareRobustness: Object.freeze({
    term: "Cutpoint methods",
    does: "Run all 5 cutpoint methods means maxstat, median, upper quartile, outer quartiles and the selected percentile. Each gene also has one cutpoint-independent continuous reference.",
    changes: "The grouped evidence profile reports BH, Cox, RMST, marker PH and model PH separately.",
    safeDefault: "Check direction and uncertainty across all cutpoints, including unfavorable results.",
  }),
  compareMethodSelection: Object.freeze({
    term: "Method selection",
    does: "Run selected methods uses only checked columns. Run all 5 cutpoint methods runs every dichotomizing strategy downstream: maxstat, median, upper quartile, outer quartiles and percentile.",
    changes: "Each grouping method adds a column and a comparison for each gene to the testing family.",
    safeDefault: "Choose the column set before running so the multiplicity family is prospective.",
  }),
  compareContinuousReference: Object.freeze({
    term: "Continuous reference",
    does: "One cutpoint-independent model is shown per gene. It uses the full expression-complete eligible population.",
    changes: "It provides the reference against which grouped cutpoint results are compared.",
    safeDefault: "Continuous and grouped models answer different questions. If they disagree, inspect the functional form, uncertainty and populations before interpreting the contrast.",
  }),

  // ------------------------------------------------------------ Robustness (technical multiverse contract)
  multiverse: Object.freeze({
    term: "Robustness across analysis choices",
    does: "Robustness runs every combination of your selected endpoints, scoring methods and cutpoints as one planned analysis family.",
    changes: "Continuous Cox tests and grouped sensitivity tests receive separate multiple-testing corrections. The record keeps every planned combination.",
    safeDefault: "Choose the analysis combinations before running. The record includes failed and unfavorable results.",
  }),
  multiverseGeneList: Object.freeze({
    term: "Robustness marker",
    does: "Use GENE:weight syntax when weighted scoring is part of the family.",
    changes: "The same gene list is scored under every selected scoring method.",
    safeDefault: "Keep the marker fixed; Robustness varies analysis choices, not the hypothesis.",
  }),
  multiverseLedger: Object.freeze({
    term: "Analysis record",
    does: "Each endpoint and scoring method appears once.",
    changes: "Repeated cutpoints must reproduce the same expression-complete continuous model and patient hash.",
    safeDefault: "Check that repeated cutpoints retain the same patient hash. Investigate any mismatch before comparing the results.",
  }),
  multiverseCurve: Object.freeze({
    term: "Robustness curve",
    does: "Specifications are sorted by displayed grouped log hazard ratio.",
    changes: "Filled points have grouped-family BH q values at or below 0.05; crosses mark non-estimable effects.",
    safeDefault: "Read the spread of the curve, not its extremes.",
  }),
  multiversePlannedCells: Object.freeze({
    term: "Planned cells",
    does: "Each planned combination stays in the record, including outcomes without usable data and models that could not be estimated.",
    changes: "Removing failures from the report would turn a declared family into a selected one.",
    safeDefault: "Report the complete analysis record, including failures.",
  }),

  // ------------------------------------------------- Expression comparison
  "expression.dataset": Object.freeze({
    term: "Expression dataset",
    does: "Compare both groups using the same expression data. TRACE selects one sample per patient according to the source rules.",
    changes: "The expression scale determines the units of the difference. Differences from other releases or assays may use different units and need not be directly comparable.",
    safeDefault: "Use the same dataset and expression scale for both groups.",
  }),
  "expression.genes": Object.freeze({
    term: "Target genes",
    does: "Each selected gene is tested separately between the two groups.",
    changes: "Every added gene enlarges the multiple-testing family reported with the result.",
    safeDefault: "Declare the gene list before defining the groups.",
  }),
  "expression.groups": Object.freeze({
    term: "Comparison groups",
    does: "Group A is the reference. Reported differences are Group B minus Group A.",
    changes: "Groups can come from clinical levels, from inherited survival groups or from expression itself. Expression-derived groups reuse the tested matrix and are explicitly exploratory, not independent evidence.",
    safeDefault: "For independent group definitions, use clinical information measured independently of the expression being tested. A molecular subtype inferred from these expression data still requires caution.",
  }),
  "expression.testFamily": Object.freeze({
    term: "Test family",
    does: "TRACE runs both Welch and Mann-Whitney tests for each eligible gene. Each test has its own BH correction across the selected genes; this section describes those fixed settings.",
    changes: "Welch compares means without assuming equal variance; Mann-Whitney compares distributions without assuming normality. The correction is applied over the full gene family, not over the genes you report.",
    safeDefault: "Read Welch for differences in means and Mann-Whitney for differences in ranked distributions. Neither test alone explains why the groups differ.",
  }),
  "expression.results": Object.freeze({
    term: "Expression results",
    does: "Read the per-gene effect, its interval and the corrected p-value together with the group sizes.",
    changes: "The difference describes these groups. It does not establish regulation or causality.",
    safeDefault: "Read the corrected p-value from the full selected gene family, along with effect size and group counts.",
  }),

  // -------------------------------------------------------------- GSEA
  "gsea.dataset": Object.freeze({
    term: "GSEA dataset",
    does: "One normalized bulk RNA-seq matrix and one sample per patient supply the ranking.",
    changes: "The cohort, release and expression scale determine the gene ranking and therefore every enrichment score.",
    safeDefault: "Use the same patient eligibility rules as the analysis these pathways will help interpret.",
  }),
  "gsea.groups": Object.freeze({
    term: "GSEA groups",
    does: "Group A is the reference; genes are ranked by group B minus group A, so positive enrichment favors group B.",
    changes: "Swapping A and B flips the sign of every NES without changing the underlying evidence. Expression-derived and inherited maxstat groups reuse outcome- or expression-informed splits and stay explicitly exploratory.",
    safeDefault: "Define groups from clinical variables declared before the analysis whenever possible.",
  }),
  "gsea.collection": Object.freeze({
    term: "Gene-set collection",
    does: "TRACE uses fixed versions of ImmPort and Gene Ontology BP/MF/CC collections and verifies their checksums.",
    changes: "BH correction covers all tested sets in the selected collection. Changing the collection changes both the biological questions and the multiple-testing correction.",
    safeDefault: "Choose the collection before running and report its version and DOI with the result.",
  }),
  "gsea.results": Object.freeze({
    term: "GSEA results",
    does: "Use CAMERA FDR to assess statistical evidence, NES to read the ranked direction and the leading edge to inspect contributing genes. The plot shows up to 30 sets; larger dots indicate smaller CAMERA FDR values (-log10 FDR, capped at 10). The table includes every tested set.",
    changes: "Positive NES points toward group B and negative NES toward group A under B minus A.",
    safeDefault: "Use CAMERA/BH values to assess statistical evidence and NES to read direction. Similar GO terms may describe the same genes.",
  }),

  // -------------------------------------------------------------- Repository
  "repository.finder": Object.freeze({
    term: "Cohort finder",
    does: "Search curated public RNA-seq releases by cancer, available analysis, endpoint, patient count and source.",
    changes: "Filters narrow the catalog only; they never change an analysis already run.",
    safeDefault: "Match the cancer, clinical context and required analysis before comparing sample or event counts.",
  }),
  "repository.eligibility": Object.freeze({
    term: "Release eligibility",
    does: "A release is ready for an analysis once its required data pass curation and quality checks. Readiness is checked separately for expression, GSEA and survival.",
    changes: "Missing survival data disables survival-based modules without hiding a valid expression release. Candidates under review remain separate and cannot be opened for analysis.",
    safeDefault: "A candidate under review can guide your search but is not ready for validation.",
  }),
  "repository.provenance": Object.freeze({
    term: "Release provenance",
    does: "Each release records its source accession, version, license, expression layer and immutable checksums.",
    changes: "Use the recorded source and version to reconstruct the result. A validation claim needs this information.",
    safeDefault: "Cite the exact release version, not the repository name.",
  }),

  // ------------------------------------------------------------- Pan-cancer
  pancancer: Object.freeze({
    term: "Choosing a pan-cancer analysis",
    does: "Compare cancer types in TCGA, or check whether one gene's survival association holds across cohorts.",
    changes: "TCGA supports a gene or fixed signature. Cross-study analysis supports one gene and overall survival. Each source is fitted separately; compatible results may be combined.",
    safeDefault: "Use the TCGA scan for a cross-cancer question. Use cross-study analysis for replication across cohorts, and check eligibility before running.",
  }),
  pancancerSynthesis: Object.freeze({
    term: "How results are combined",
    does: "Across TCGA cancers: each cancer gets its own result. A combined result is available only when the effects use a common input-score scale; the per-SD view is never combined.",
    changes: "Across independent studies: each study gets its own result. Studies with matching outcome definitions, time origins, clinical contexts and compatible expression measurements can be combined within a cancer, then across cancers. Patient records are never merged.",
    safeDefault: "Read individual results first. TCGA per-SD and cross-study per-IQR effects use different increments and cannot be compared directly.",
  }),
  pancancerInclusion: Object.freeze({
    term: "Which cancers enter the scan?",
    does: "A cancer needs usable data for your marker and survival outcome, and must meet both minimum counts below. Counts refer to patients who can enter the model, not everyone in the source dataset.",
    changes: "Raising either minimum leaves more cancers out. Lowering it allows smaller analyses, whose estimates may be less precise. Skipped cancers and their reasons remain in the results.",
    safeDefault: "These rules decide which cancers are analyzed. The FDR threshold below only decides which results are highlighted.",
  }),
  pancancerPatients: Object.freeze({
    term: "Minimum patients",
    does: "At least this many patients must have usable marker, survival time and outcome-status data in each cancer.",
  }),
  pancancerEvents: Object.freeze({
    term: "Minimum outcome events",
    does: "At least this many patients must have experienced the selected outcome: death for overall survival, or the corresponding event for another outcome.",
  }),
  pancancerFdr: Object.freeze({
    term: "Highlighting associations",
    does: "Highlight results whose Benjamini–Hochberg adjusted p-value (q) meets this threshold. A value of 0.10 is less strict than 0.05.",
    changes: "This does not remove cancers, change the fitted models or measure an individual result's probability of being false.",
  }),
  pancancerStudyCounts: Object.freeze({
    term: "Minimum patients per study",
    does: "Each study must meet all three counts: patients with usable data, deaths, and patients whose follow-up ended without an observed death (censored).",
    changes: "Raising a minimum excludes more studies. Meeting the counts does not override the outcome, timing or clinical-context checks.",
    safeDefault: "Check eligible studies to see which pass and why others are excluded.",
  }),
  pancancerMarkerInput: Object.freeze({
    term: "Gene or signature",
    does: "Enter one gene, or add at least two genes and choose a signature scoring method.",
    changes: "TRACE calculates the signature separately in each cancer. Rank methods use GENE:-1 for down genes; Z-score and Weighted accept GENE:weight.",
    safeDefault: "Choose the genes and scoring method before running. Check signature coverage in the results for each cancer.",
  }),
  pancancerHierarchicalQuery: Object.freeze({
    term: "Gene across studies",
    does: "Choose one HGNC gene and select TCGA, external cohorts or both. This mode uses overall survival.",
    changes: "Each study has its own Cox model. Effects describe an increase of one expression IQR within that study; compatible effects can then be combined.",
    safeDefault: "Check eligible studies and exclusion reasons before running. Review clinical context and study-size requirements in Advanced settings.",
  }),
  pancancerEndpointMode: Object.freeze({
    term: "Matching the survival outcome",
    does: "Same outcome uses only the outcome you selected. For example, an overall-survival scan skips cancers without usable overall-survival data.",
    changes: "The other options allow a different outcome when the selected one is unavailable or fails quality checks. This can mix deaths, progression or recurrence across cancer results; inspect the outcome listed for each cancer.",
    safeDefault: "Keep Same outcome for a directly comparable scan.",
  }),
  "pancancer.query": Object.freeze({
    term: "Pan-cancer query",
    does: "TCGA reference applies the same marker or signature definition and endpoint rule to every eligible TCGA cancer.",
    changes: "Each cohort is scored and fitted separately. Coverage and the exact scoring population remain visible for every multi-gene signature.",
    safeDefault: "Fix the genes, directions or weights, and scoring method before comparing cancers.",
  }),
  "pancancer.preflight": Object.freeze({
    term: "Study eligibility check",
    does: "Check which cohorts or studies qualify before running. TRACE lists those excluded and their reasons.",
    changes: "Excluding a cohort after seeing its effect would turn the synthesis into a selected set.",
    safeDefault: "Decide which studies to include before fitting the models, and keep the exclusion reasons in your report.",
  }),
  "pancancer.results": Object.freeze({
    term: "Pan-cancer results",
    does: "Read study effects, their intervals, heterogeneity and the prediction interval together.",
    changes: "The global estimate combines study effects within cancers, then compatible cancer effects. Its evidence threshold records replicated cancers and events; passing that threshold does not guarantee calibration.",
    safeDefault: "Read cancer-specific intervals, heterogeneity and the prediction interval before the global estimate. The average may not apply to every cancer.",
  }),
  // ------------------------------------------------- Result-panel readings
  continuousPrimaryModel: Object.freeze({
    term: "Primary continuous model",
    does: "The primary model uses every expression-complete eligible patient before cutpoint assignment.",
    changes: "Expression is standardized within that population, so each HR represents a one-standard-deviation increase.",
    safeDefault: "This is the estimate to report; grouped views are sensitivities.",
  }),
  phTwoPeriod: Object.freeze({
    term: "Two-period marker effect",
    does: "Shown only when the marker-specific cox.zph p-value is below 0.05. Two years is the fixed primary split; one and five years are prespecified sensitivities.",
    changes: "No split is chosen from marker values, event times or effect estimates.",
    safeDefault: "At least 5 events per period and 10 patients entering the late period are required.",
  }),
  groupedCoxResults: Object.freeze({
    term: "Grouped hazard ratios",
    does: "These hazard ratios compare the expression groups created by the selected cutpoint.",
    changes: "Adjusted models use complete cases, with stage and grade encoded as ordinal trends.",
    safeDefault: "Maxstat estimates remain post-selection and are optimistic.",
  }),
  rmstTau: Object.freeze({
    term: "RMST horizon",
    does: "Tau is fixed before stratification as the smaller of five years and the eligible cohort's 75th percentile of endpoint time.",
    changes: "RMST is reported only when at least five patients remain at risk in each group at tau.",
    safeDefault: "Report tau with the RMST difference so the reader knows the follow-up horizon.",
  }),
  interactionModel: Object.freeze({
    term: "Signature interaction",
    does: "Signature scores are z-scored within the analyzed patients.",
    changes: "The interaction tests whether one signature's effect changes as the other increases.",
    safeDefault: "An interaction term is not evidence of a biological mechanism.",
  }),
  auditCapture: Object.freeze({
    term: "Audit capture",
    does: "Captures parameters, endpoint source, sample selection, patient records, Cox and QC outputs, software versions and artifact checksums.",
    changes: "Anything not captured here cannot be reconstructed from the export.",
    safeDefault: "Download the audit bundle with every result you intend to publish.",
  }),
  sessionScope: Object.freeze({
    term: "Run history scope",
    does: "The history contains requests recorded in this browser while recording was enabled. It is a record of exploration, not a plan made before the results.",
    changes: "It does not replace the prespecified Robustness module.",
    safeDefault: "It cannot prove that unrecorded analyses did not occur.",
  }),
  sessionEvents: Object.freeze({
    term: "Recorded requests",
    does: "Each accepted analysis request creates one history entry while recording is enabled.",
    changes: "Repeating a request creates another entry even when a cached result is returned. The export counts identical hypotheses once when constructing its testing families.",
    safeDefault: "Use the export to see which distinct tests receive each correction. The number of history entries is not the number of distinct tests.",
  }),
  pancancerMarker: Object.freeze({
    term: "Hierarchical pan-cancer marker",
    does: "Enter one HGNC gene symbol. Suggestions use the selected TCGA reference cohort.",
    changes: "The same symbol is looked up independently in every cohort or study.",
    safeDefault: "A symbol missing from a cohort excludes that cohort rather than failing the scan.",
  }),
  pancancerSingleGene: Object.freeze({
    term: "TCGA marker or signature",
    does: "Use one gene directly, or enter two or more genes and choose Mean, Z-score, Weighted, singscore, ssGSEA or AUCell.",
    changes: "Every signature is recalculated inside each cohort. Use GENE:-1 for down genes in rank methods and GENE:weight for Z-score or Weighted scoring.",
    safeDefault: "Use Single gene for a marker question; for a signature, keep one declared method and inspect gene coverage by cohort.",
  }),
  methodsPage: Object.freeze({
    term: "Methods",
    does: "Read how TRACE selects patients, fits models and produces results.",
    changes: "The Methods page and in-place help use the same definitions.",
    safeDefault: "Use these definitions when documenting or reproducing an analysis.",
  }),
});

export const HELP_ENTRY_IDS = Object.freeze(Object.keys(HELP_ENTRIES));

export function hasHelpEntry(entryId) {
  return Object.hasOwn(HELP_ENTRIES, entryId);
}

/**
 * Resolve one entry. Unknown identifiers throw because help identifiers are a
 * contract, exactly like guide anchors and icon roles.
 */
export function getHelpEntry(entryId) {
  const record = HELP_ENTRIES[entryId];
  if (!record) {
    throw new Error(`Unknown TRACE Explorer help entry: ${entryId}`);
  }
  return record;
}

/** Flatten one or more entries into a single prose string. */
export function helpProse(entryIds) {
  const ids = Array.isArray(entryIds) ? entryIds : [entryIds];
  return ids
    .map((entryId) => {
      const resolved = getHelpEntry(entryId);
      return HELP_SLOTS.map((slot) => resolved[slot]).filter(Boolean).join(" ");
    })
    .filter(Boolean)
    .join(" ");
}

/**
 * Statistical vocabulary, resolved from the single tutorial concept registry.
 * The registry exposes the single English concept source used by Guides and
 * in-place help.
 */
export function getGlossaryTerm(conceptId) {
  return getTutorialConcept(conceptId, HELP_LANGUAGE);
}

export const GLOSSARY_TERM_IDS = TUTORIAL_CONCEPT_IDS;

export function hasGlossaryTerm(conceptId) {
  return TUTORIAL_CONCEPT_IDS.includes(conceptId);
}

/** Contract validation surfaced by the test suite. */
export function helpRegistryErrors() {
  const errors = [];
  const allowed = ["term", "caption", ...HELP_SLOTS];
  for (const [entryId, entry] of Object.entries(HELP_ENTRIES)) {
    if (!String(entry.term || "").trim()) {
      errors.push(`${entryId}: entry needs a term.`);
    }
    if (!String(entry.does || "").trim()) {
      errors.push(`${entryId}: entry needs a "does" slot.`);
    }
    for (const key of Object.keys(entry)) {
      if (!allowed.includes(key)) {
        errors.push(`${entryId}: entry has unknown slot "${key}".`);
      }
    }
  }
  return errors;
}
