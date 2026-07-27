# TCGA-TRACE Methods History

This changelog tracks methodological behavior exposed to users. It is not a Git commit log. Update it when a change affects scoring, endpoint QC, patient selection, model outputs, robustness criteria, audit exports or manuscript-facing interpretation.

## Optional Separate Cox Forests v1.0 - 2026-07-27

This release changes plot output only; it does not change any fitted Cox
model or estimate.

- Kept the existing combined grouped-Cox forest as the default.
- Added an optional layout with one forest for the univariable model and one
  for all evaluable adjusted multivariable models.
- Added independent titles, live previews, PNG/SVG downloads and ZIP entries
  for both model families.
- Omitted a separate figure when its model family is not estimable rather than
  rendering an empty panel.
- Recorded the requested layout and completed model-family counts in metrics,
  methodology, audit and reconstruction exports.

## Curated External RNA-seq Repository v1.1 - 2026-07-27

This release adds independently sourced bulk RNA-seq cohorts without combining
their measurements or clinical definitions with TCGA.

- Added an explicit 33-cancer coverage ledger that distinguishes published
  releases, screening candidates, searches in progress and evidence gaps.
- Added immutable dataset releases with source snapshots, SHA-256 file
  checksums, license metadata, expression-layer semantics, patient/sample
  linkage, endpoint definitions and automated QC.
- Required at least 10 expression-and-endpoint-complete patients, 5 events, 5
  censored observations and 10,000 unique mapped gene symbols before a release
  can be promoted.
- Added repository-backed gene search, endpoint/filter discovery and
  patient-level analysis to Survival, Compare and Multiverse. Pan-cancer
  remains TCGA-only; cohorts are never pooled or silently harmonized.
- Published 25 independent, survival-ready cohorts covering 25 of the 33 TCGA
  cancer types through reviewed cBioPortal, GDC, GEO, Europe PMC and ICGC
  sources.
- Recorded KICH, KIRP, MESO, TGCT, THCA, THYM, UCS and UVM as evidence gaps,
  with the best public lead and its exact rejection reason retained in the
  machine-readable coverage ledger and shown in the interface.
- Preserved each release's documented expression scale. The IMvigor210 profile
  is retained exactly as supplied because DataHub labels it TPM while the exact
  upstream transform is not stated; TCGA-TRACE does not apply a second log
  transform or describe it as unlogged TPM.
- Added a reproducible cBioPortal discovery scan. Detection of RNA and survival
  columns creates a screening candidate only; TCGA independence, event counts,
  scale semantics, license and linkage still require review.
- Added deterministic adapters for non-TCGA GDC projects, GEO matrices,
  publication/clinical supplements and open ICGC Release 28 objects.
- Rebuilt the 3,273-patient SCAN-B release without download-time metadata in
  its source snapshot so identical source responses reproduce the same recipe.
- Kept external release hashes separate from the primary TCGA data-manifest
  hash in health and dataset-summary responses.

## Release Identity and CI Contract v1.0 - 2026-07-25

This release strengthens deployment verification without changing a scientific
estimate.

- Added public `release.commit` and `release.ref` fields to health responses;
  development defaults are explicit rather than silently resembling a tagged
  deployment.
- Required final browser evidence to compare the full commit and tag reported
  by the HTTPS deployment with the clean exact-tag checkout under test.
- Extended continuous integration to run frontend Vitest, full-context
  publication tests, project-identity checks, pinned Gitleaks secret scanning
  and the production frontend build.
- Added a manual exact-tag release workflow that runs Chromium, Gecko and
  WebKit against the deployed tag, enforces owner metadata and editorial gates,
  rebuilds all PDFs and emits a verified archive plus `SHA256SUMS`.

## Exploratory Session Family Contract v1.0 - 2026-07-25

This release adds an optional post hoc run record without changing any
scientific estimate.

- Added opt-in browser-local recording for accepted Survival, Compare,
  Multiverse and Pan-cancer compute jobs.
- Added selection and export of up to 200 run events as one server-resolved
  report; local history does not retain patient records or uploaded
  covariate-row values.
- Deduplicated exact hypotheses while retaining repeated execution events, and
  separated continuous Cox, grouped cutpoint and two-signature interaction
  tests into distinct export-defined BH and Bonferroni families.
- Kept prespecified multiverse and pan-cancer scans under their own internal
  multiplicity contracts and referenced them without double counting.
- Added run and hypothesis CSVs, execution ledger, methodology, JSON/HTML
  audit, ZIP bundle and detached Ed25519 receipt.
- Stated the scope boundary in every export: the selected history is post hoc,
  changes when runs are added or removed, and cannot prove that no other
  analyses occurred.

## Server Attestation Contract v1.0 - 2026-07-25

This release adds a verifiable server-origin layer without changing any
scientific estimate.

- Added a persistent Ed25519 signing key stored outside application images and
  analysis bundles; only public keys are exposed through API v1.
- Added a detached `attestation_receipt.json` for every completed analysis,
  multiverse, pan-cancer scan and exploratory session export. The signed
  payload binds the exact audit byte
  count, SHA-256, schema and recorded reproducibility hash.
- Added active/retired public-key discovery by full SHA-256 fingerprint and a
  standalone verifier that requires a key obtained from the declared HTTPS
  issuer or an independently archived release.
- Included receipts in direct downloads and ZIP bundles and surfaced them in
  the Survival, Multiverse and Pan-cancer interfaces.
- Kept the trust boundary explicit: a valid receipt establishes server origin
  for one exact audit report, but does not establish scientific correctness,
  prevent the server from signing another report or provide append-only time.

## Competing-Risk Estimand Contract v1.0 - 2026-07-25

This release adds explicit competing-risk estimation for TCGA-CDR DSS, DFI and
PFI while preserving the existing cause-specific outputs.

- Imported endpoint-specific `ExtraEndpoints` status/time columns with
  `0 = censored`, `1 = event of interest` and `2 = competing death`.
- Kept Kaplan-Meier and Cox as event-free/cause-specific estimands that censor
  code 2 at its recorded time.
- Added nonparametric cumulative-incidence curves, Gray's K-sample test and
  fixed 1-, 3- and 5-year CIF estimates with pointwise Aalen-variance 95%
  intervals, patients at risk and low-support flags.
- Added grouped and continuous Fine-Gray models, including exact user-selected
  and available auxiliary clinical adjustments, with model-specific patients,
  target/competing events, information diagnostics, contrasts and SHR
  inference.
- Added CIF PNG/SVG downloads and bound the coding, results and exact
  `competing_risks.R` source into methodology, patient data, JSON/HTML audit,
  integrity checks and standalone reproduction capsules.
- Added an estimand comparison panel that states cause-specific HRs and
  Fine-Gray SHRs are not interchangeable.
- Extended the browser contract to 21 checks across Chromium, Firefox/Gecko
  and WebKit, including a real UVM/BAP1/DSS run, square CIF download and
  desktop/mobile overflow checks.

## Prespecified Time-Varying Marker Effects v1.0 - 2026-07-25

This release adds an interpretable follow-up diagnostic when a marker does not
support one constant Cox hazard ratio.

- Triggered the diagnostic only when the marker-specific `cox.zph` p-value is
  below 0.05; a global-model PH flag alone does not trigger it.
- Fixed the follow-up split at 2 years (730.5 days) for every analysis before
  inspecting expression, event times or estimated effects.
- Added marker HRs for 0-2 years and after 2 years, their late-to-early ratio,
  95% confidence intervals and p-values using participant-clustered robust
  variance and Efron ties.
- Required at least 5 events in each period and 10 patients entering the late
  period; unsupported diagnostics remain visible with their reason.
- Applied the contract to grouped, continuous, two-signature interaction and
  pan-cancer Cox models.
- Added the temporal specification and results to the interface, methodology,
  JSON/HTML audit, pan-cancer CSV and multiverse continuous/grouped CSV exports.
- Kept the temporal output diagnostic: it does not replace RMST, remove a model
  or become another component of a composite significance rule.

## User-Supplied External Covariates v1.0 - 2026-07-25

This release extends the exact complete-case adjustment model to cohort-specific
variables without changing unadjusted or auxiliary stage/grade estimates.

- Added a client-side CSV workflow shared by Survival, Compare and Multiverse.
- Required exact public TCGA participant barcodes in `patient_id`, unique rows,
  1 to 10 covariates and at most 2,000 participants.
- Added explicit continuous, categorical and ordinal encoding with effect
  units, treatment-reference levels and ordered levels.
- Kept imported variables out of every model until the user selects them
  explicitly.
- Linked selected values after expression-complete patient construction and
  reported unmatched cohort rows, missingness, variation and complete-case
  model size.
- Applied the same selected external specification to grouped, continuous and
  two-signature interaction Cox families.
- Added external values to patient-level CSV and R inputs, and added dataset
  SHA-256, definitions, coding and QC to methodology and JSON/HTML audit
  exports.
- Incremented single/signature, crossed-signature and multiverse pipeline
  versions to prevent reuse of artifacts from the previous contract.

## Standalone Public API CLI v1.0 - 2026-07-25

This release adds a dependency-free command-line interface without changing
scientific estimates.

- Added OpenAPI compatibility checks and discovery commands for the public v1
  service.
- Added request-file submission and persistent-job polling for single,
  combined-signature, batch, multiverse and pan-cancer analyses.
- Added recursive artifact download with a local SHA-256 download manifest.
- Added family-aware verification for analysis, multiverse and pan-cancer
  reproducibility bundles, including unsafe-ZIP rejection.
- Added English and Spanish CLI guides, structured errors and stable exit
  codes for pipeline integration.

## Browser Compatibility and Gene Suggestions v1.0 - 2026-07-25

This release hardens gene selection and adds executable browser evidence
without changing statistical estimates.

- Prevented a step-transition focus race from committing a partial gene token
  before cohort suggestions arrived.
- Centralized cancellable gene searches for single signatures, crossed
  signatures, Compare and Multiverse inputs.
- Added accessible searching, empty and API-error states to the gene
  suggestion list.
- Added an isolated Playwright contract for Chromium, Firefox/Gecko and WebKit
  covering 21 functional checks across Survival, competing-risk results,
  Compare, Paper Examples,
  Pan-cancer, Dataset Summary, downloads, keyboard focus and reduced motion.
- Added a strict final mode that requires a clean exact-tag checkout and an
  HTTPS deployment, while preserving provisional development evidence
  separately.

## Runtime Evidence and Canonical Identity v1.0 - 2026-07-25

This release adds reviewer-facing operational evidence and fixes the public
software identity without changing statistical estimates.

- Established TCGA-TRACE as the canonical UI, API/MCP, manuscript and release
  name; `/tcga_explorer` remains a documented legacy compatibility route.
- Renamed generated manuscript PDFs and the review package with a
  `tcga-trace` prefix and bound `project_name: TCGA-TRACE` into the archive
  manifest.
- Added an automated identity gate that rejects legacy display names and
  package filenames.
- Added a reproducible public-API benchmark for uncached/cached single runs,
  two-job concurrency, a 10-analysis batch, a 72-cell multiverse and a
  33-cohort pan-cancer request.
- Recorded wall, queue and compute intervals, observed backend-plus-worker
  Docker cgroup memory, host/container resources, pipeline versions, data
  snapshot and public queue limits.

## Endpoint and Score Interpretation Contract v1.0 - 2026-07-25

This release makes two estimand limitations explicit without changing cohort
selection, estimates or model status.

- Added an informational notice for z-score signatures stating that genes are
  standardized among the expression-complete patients eligible in the current
  run and that numerical scores are not transportable across endpoint or
  filter-defined runs.
- Added an informational DSS notice stating that other-cause deaths are
  censored under a non-informative censoring assumption and that Kaplan-Meier
  and Cox outputs are not cumulative-incidence or Fine-Gray estimates.
- Exposed both statements consistently in parameter help, completed-result
  context, methodology text and structured JSON/HTML audit reports.
- Propagated the contract to single/signature, two-signature, prespecified
  multiverse and pan-cancer workflows.
- Incremented analysis, combined-signature, multiverse and pan-cancer pipeline
  versions so cached exports cannot silently retain the prior reporting
  contract.

## Standalone Reproduction Capsules v1.0 - 2026-07-25

This release makes a completed two-group analysis reproducible without the
TCGA-TRACE service, database or original TCGA expression matrix.

- Added the exact patient-level `input.json`, R statistical engine and helper
  scripts, executable `rerun_analysis.R`, `renv.lock`, pinned
  `Dockerfile.reproduce`, instructions and capsule manifest to every analysis
  export and ZIP bundle.
- Fixed the R 4.4.2 base image by immutable multi-architecture digest and
  restored 90 exact package versions from a dated CRAN snapshot.
- Added direct R-runner and capsule-manifest downloads to the interface.
- Added a clean-container benchmark using a read-only root and capsule,
  disabled network and no application source, TCGA matrix or database.
- Reproduced single-gene, weighted-signature and crossed-signature outputs in
  native arm64 and emulated amd64 environments: 6/6 runs matched under
  versioned quantity-specific absolute-plus-relative tolerances.
- Added frozen-input and expression-snapshot mutation controls and an
  independent GitHub-hosted Linux/amd64 CI job.

## Statistical Calibration Benchmark v1.0 - 2026-07-25

This release calibrates the revised evidence profile without reinstating the
removed retained/not-retained rule.

- Added 2,000 expression permutations in a frozen 365-patient, 130-event
  TCGA-LIHC cohort while preserving event times and censoring.
- Added four known-truth scenarios with 2,000 datasets each at `n=300`: null,
  linear PH, delayed non-PH and U-shaped nonlinear effects.
- Refit continuous Cox, spline nonlinearity, marker-specific `cox.zph`, fixed
  tau RMST and four two-group rules in every replicate: maxstat, median, upper
  quartile and outer quartiles.
- Applied Holm within each four-rule grouped family, using Lau94 for maxstat
  and retaining its naive selected-group log-rank p-value only to quantify
  post-selection bias.
- Added Wilson 95% Monte Carlo intervals and replicate-level CSV outputs bound
  to the source audit hash.
- Observed null rejection was 3.2-5.8% for the revised primary and grouped
  summaries, while naive maxstat rejected 39.6% versus 1.8% with Lau94.
- Confirmed diagnostic sensitivity of marker PH for delayed effects (88.2%)
  and spline nonlinearity for the U-shaped scenario (100%).

## Prespecified Multiverse and Specification Curve v1.1 - 2026-07-25

This release adds an explicit analysis-family workflow for endpoint, signature
scoring and cutpoint choices. It does not reinterpret unrelated ad hoc runs as
prespecified.

- Added a five-step Multiverse module that freezes a Cartesian
  endpoint-by-scoring-by-cutpoint grid before execution, with a public limit of
  72 specifications.
- Defined a cutpoint-independent primary family containing one continuous Cox
  test per unique endpoint and scoring method, deduplicated across repeated
  cutpoints.
- Defined a separate grouped-sensitivity family containing every declared
  endpoint, scoring and cutpoint combination.
- Applied BH and Bonferroni correction separately within the continuous and
  grouped families; maxstat contributes its Lau94 corrected rank-test p-value
  to grouped multiplicity.
- Preserved standard Cox as primary and exposed Firth only as a named
  sensitivity when the standard estimate is not evaluable.
- Kept marker-term and global PH diagnostics as interpretation fields rather
  than filters, and did not calculate a retained/not-retained verdict.
- Added a parent execution ledger with every planned specification, request
  hash, child analysis ID, child audit hash, status and error.
- Added result JSON, grouped and continuous CSV, SVG specification curve,
  ledger JSON, audit JSON/HTML, methodology text and a complete ZIP bundle.
- Distributed small specification families across the available SVG width
  while retaining fixed minimum spacing and horizontal scrolling for large
  families.

## User-Selected Clinical Adjustment v6.2 - 2026-07-24

This release separates cohort eligibility filters from model adjustment and
adds one exact, auditable complete-case adjustment specification.

- Added `adjustment_covariates` to single/signature, two-signature and batch
  analysis requests.
- Added imported age, stage, grade, GDC gender and GDC race as selectable Cox
  covariates in Survival and Compare Analyses.
- Modeled age continuously per 10 years, stage and grade as ordinal trends, and
  gender/race as deterministic treatment contrasts.
- Added `user_adjusted`, `continuous_user_adjusted` and
  `signature_interaction_user_adjusted` model outputs without removing the
  fixed stage/grade sensitivity families.
- Prevented unavailable requested models from being silently replaced by an
  auxiliary adjustment.
- Added model-specific complete-case N, events, parameter count, EPV,
  covariate encoding and Firth sensitivity to the exact requested model.
- Recorded the requested fields and adjustment design in methodology and audit
  exports.
- Prespecified age adjustment for the publication single-gene benchmark suite.

## Sparse-Event Cox Diagnostics v6.1 - 2026-07-24

This release makes model information and monotone-likelihood sensitivity
explicit without replacing the standard Cox estimate.

- Added fitted-parameter counts and observed events per fitted parameter to
  continuous, grouped and two-signature interaction Cox models.
- Marked values below 10 events per parameter as `caution` and values below 5
  as `severe`; these are interpretation warnings rather than exclusion rules.
- Added automatic Firth penalized partial-likelihood sensitivity when a
  standard Cox fit has low events per parameter, convergence or non-finite
  coefficient concerns, or an extreme marker estimate or confidence interval.
- Kept standard `survival::coxph` results with Efron ties visible. Firth
  sensitivities use `coxphf` 1.13.4 with penalty 0.5, Breslow ties,
  profile-penalized-likelihood confidence intervals and penalized likelihood
  ratio tests.
- Added trigger reasons, iterations, package version and both tie methods to
  result JSON, audit exports, methodology text, Survival tables, Paper
  Examples and benchmark CSV files.
- Regenerated all 11 single-gene scenarios, 44 grouped sensitivities and six
  advanced examples under pipeline v6.1. UVM BAP1 produced three grouped
  Firth sensitivities after non-finite standard Cox intervals; its
  outer-quartile stage-adjusted model had 4.5 events per parameter.

## Continuous Primary Model v6.0 - 2026-07-24

This release makes cutpoint-independent expression modelling the primary
single-marker and single-signature result. Dichotomized outputs remain
available as secondary sensitivity analyses.

- Added an unadjusted Cox model per +1 within-analysis expression-score
  standard deviation over the full eligible expression-complete population.
- Added stage, grade and stage+grade ordinal sensitivity models using the same
  standardized predictor and explicit availability fallback.
- Added a three-degree-of-freedom restricted cubic-spline profile with knots at
  the 5th, 35th, 65th and 95th percentiles, a spline-versus-linear
  nonlinearity test and a 5th-to-95th-percentile effect profile relative to the
  median.
- Kept the continuous population independent of cutpoint exclusions. For
  example, outer-quartile grouping may discard the middle 50% for KM/RMST but
  cannot change the continuous Cox estimate.
- Moved Kaplan-Meier, grouped Cox and RMST outputs under an explicit
  `Cutpoint sensitivity` section in Survival, Compare Analyses and Paper
  Examples.
- Added continuous PNG, SVG and CSV downloads and included them in the ZIP
  bundle.
- Upgraded the audit record to schema v3 with separate hashes and patient
  records for the continuous and grouped populations.
- Kept marker-term and global PH tests separate. Neither PH nor spline
  nonlinearity is converted into a binary retention decision.
- Regenerated 11 continuous single-gene references, 44 grouped
  cutpoint-sensitivity runs, both three-rule TCGA-SKCM sample-composition
  panels and all six advanced paper examples under pipeline v6.0.

## Cutpoint Evidence Profile v1.1 - 2026-07-24

This release replaces the earlier composite cutpoint reporting flag. It changes
interpretation and benchmark presentation, not patient grouping or statistical
estimation.

- Removed `retained` and `reporting_decision` from newly generated cutpoint
  summaries and from the Paper Examples API.
- Reported suite/run-level BH q-values, univariable Cox, adjusted Cox and
  fixed-horizon RMST as related descriptive summaries rather than independent
  pass/fail barriers.
- Separated the biomarker-term `cox.zph` p-value from the complete-model global
  PH test. PH cautions modify HR interpretation and do not discard an
  association.
- Labelled maxstat-grouped HRs, confidence intervals and RMST comparisons as
  post-selection; the corrected maximally selected rank-test p-value remains a
  separate output.
- Added group sizes, event counts, RMST tau and interpretation notes to the
  Compare Analyses evidence profile.
- Regenerated the 44-analysis single-gene panel and six TCGA-SKCM sample-rule
  sensitivity runs under analysis pipeline v5.1.

## Audit Reconstruction and Reporting Semantics - 2026-07-24

- Replaced confidence-grade wording in cutpoint comparisons with neutral
  retention-by-reporting-rule language; this intermediate presentation was
  subsequently replaced by the v1.1 evidence profile above.
- Defined the two-group RMST horizon without group labels as the smaller of
  five years and the 75th percentile of observed endpoint times in the
  unstratified expression-complete eligible cohort.
- Restricted the frozen publication panel to four nonredundant two-group rules:
  maxstat, median, upper quartile and outer quartiles. The application retains
  custom-percentile and three-group tertile options.
- Applied one suite-wide Benjamini--Hochberg correction to the 44 frozen
  single-gene log-rank tests; downstream Cox, RMST and PH checks remain
  explicitly descriptive.
- Added audit schema v2 provenance for the exact expression artifact, matched
  GDC file identifiers, gene-level expression components, weights and
  standardization parameters.
- Added deterministic score reconstruction and R re-execution for single-gene,
  weighted-signature and crossed-signature bundles, plus targeted mutation
  detection.

## Immune Pan-Cancer Atlas v2.1 - 2026-07-24

This release recomputes the full ImmPort atlas under the same final pan-cancer
logic used by the interactive BIRC5 and CA9 examples.

- Frozen 3,118 unique ImmPort genes from JSON/GMT sources and prepared 32
  strict-OS TCGA cohorts.
- Attempted 399,104 gene-cancer-family rows across primary expression,
  stage+grade, stage and grade Cox families.
- Preserved the within-cohort expression z-score Cox model as the primary
  cross-cancer estimand.
- Encoded major stage and histologic grade as ordinal trends and selected
  stage+grade, then stage, then grade by availability only.
- Applied global gene-cancer BH-FDR and gene-level random-effects meta-FDR
  independently within each comparable model family.
- Kept the availability-selected adjusted layer descriptive and cohort-level;
  mixed selected families are never meta-analyzed.
- Reported retained, attenuated, emergent, direction-reversed, not-evaluable
  and PH-caution counts without treating any single diagnostic as an automatic
  validity gate.
- Restricted the headline direction-change count to primary-FDR-supported
  results; all model-level direction changes remain available in the export.
- Pinned ImmPort inputs, 32 expression matrices, patient records, cohort
  checkpoints, software versions and final artifacts by SHA-256.
- Added model-family, selected-sensitivity, raw-model, audit and ZIP downloads
  to the public API; REST, MCP and the web interface read the same versioned
  atlas.
- Verified deterministic post-processing in consecutive runs. The frozen
  atlas audit hash is
  `4d942e93715ec953f0501b13a818d2f19e34f21d851367057924f0af3c2d0252`.

## Decision-Support Evidence Semantics - 2026-07-23

This release changes interpretation metadata and presentation without changing
patient grouping, statistical estimates, endpoints or reproducibility hashes.

- Reclassified cohort exclusions, administrative censoring and deterministic
  sample selection as neutral provenance information.
- Added a distinct `not_evaluable` state when no clinical-adjusted Cox model
  can be fitted.
- Reserved the top-level amber status for a diagnostic caution in the selected
  adjusted model. Cautions from auxiliary models remain inspectable but no
  longer contaminate the selected-model status.
- Reframed the conservative robustness rule as a high-confidence evidence
  screen rather than a validity gate.
- Added high-confidence, convergent, exploratory, limited and no-current-
  evidence labels to cutpoint comparisons while preserving every result.
- Added structured `notices` and `diagnostics` to REST/MCP analysis responses.
  The legacy `warnings` array remains unchanged for client compatibility.

## Public API and MCP - 2026-07-23

This release adds integration and operational controls without changing the
statistical pipelines.

- Added a documented public REST API under `/api/v1`, with stable error
  envelopes, request IDs, Swagger, ReDoc, and OpenAPI 3 metadata.
- Added persistent asynchronous compute jobs, deduplication, anonymous quotas,
  two global worker slots, stale-job recovery, and 90-day artifact retention.
- Added a stateless Streamable HTTP MCP server for ChatGPT, Claude, and other
  compatible clients, with 16 scientific tools and two read-only resources.
- Migrated the web frontend to the queued v1 contract while preserving its
  existing completed-result interface.
- Removed internal filesystem paths from public metadata and kept cache/sync
  operations outside the public reverse proxy.
- Added English and Spanish API/MCP guides.

## Publication Evidence Revision - 2026-07-23

This revision changes manuscript-facing examples and documentation. It does not
change the statistical behavior of the web application.

### Benchmark Panel

- Expanded the formal single-gene panel from 7 to 11 marker-endpoint scenarios
  and regenerated all five dichotomization methods through the HTTP API.
- Selected five literature-anchored cases for the main summary table:
  LIHC/CDC20 OS, LUAD/BIRC5 OS, UVM/BAP1 DSS, SKCM/TMEM176B OS and LGG/EMP3 OS.
- Preserved all 11 scenarios in the supplementary overview. Null and discordant
  CA9, MKI67, PDCD1 and CD274 examples were not removed.
- Reframed the conservative retained flag as a benchmark reporting convention,
  not an application gate. The interface continues to display and export every
  estimate and diagnostic.

### Advanced Workflow Examples

- Replaced the main feature examples with a weighted ACC BUB1B-PINK1 contrast,
  UVM BAP1 x PRAME four-group analysis and continuous BIRC5 pan-cancer scan.
- Added the exact score construction and complete gene membership to the
  manuscript and supplement.
- Reported global four-group separation and the continuous interaction test as
  distinct UVM results; no interaction claim is made.
- Reported the BIRC5 random-effects estimate together with I2 and
  opposite-direction significant cohorts.
- Retained the previous KIRC hypoxia, SKCM effector x exhaustion and CA9
  pan-cancer cases as supplementary diagnostic counterexamples.

### Figure 1

- Replaced the image-generated background with a white-background TikZ vector
  diagram covering inputs, deterministic cohort construction, three analysis
  branches, diagnostics, exported run records and the provenance hash chain.
- Added a separate accessibility description for Figure 1.

## TCGA-TRACE v0.1.0 - Functional Baseline

### Added

#### Platform And Navigation

- Dockerized web application with React/Vite frontend, FastAPI backend, PostgreSQL database and Nginx reverse proxy.
- Main workspace navigation with KM Analysis, Compare Analyses, Pan-cancer, Dataset Summary and Help & Methods modules.
- Backend healthcheck with cache status, data dates, application version and pipeline versions.
- Warm startup RNA cache loading for all configured TCGA cohorts.
- Apache/Nginx and Docker Compose deployment documentation.

#### Cohort, Gene And Patient Inputs

- TCGA cohort selector with search by TCGA code, cancer name, primary site or disease description.
- Full cancer-name display alongside TCGA cohort codes.
- Cohort quick summary with RNA samples, patients, tumors and primary site.
- Per-cohort gene search with autocomplete.
- Gene selection through removable chips.
- Multiple genes in single-gene mode, producing one Kaplan-Meier analysis per gene.
- Common gene alias resolution, including legacy symbols mapped to current gene symbols.
- One RNA sample per TCGA participant using explicit biospecimen priority.

#### Expression And Signature Scoring

- Selectable RNA scales: log2(TPM + 1), log2(CPM + 1), log2(FPKM + 1) and log2(FPKM-UQ + 1).
- Single-signature analysis with mean, z-score and weighted scoring.
- Weighted signature syntax using `GENE:weight`.
- Combined analysis of two independent signatures.
- Crossed two-signature stratification by median x median or tertiles x tertiles.
- Continuous z-scored signature scores for two-signature interaction modeling.

#### Endpoints, Cutpoints And Clinical QC

- TCGA-CDR survival endpoints OS, PFI, DFI and DSS when available.
- OS fallback from TCGA clinical metadata when TCGA-CDR is not configured.
- Per-cohort endpoint availability checks with minimum patient and event QC.
- Cutpoint methods: maxstat, median, tertiles, upper quartile, outer quartiles and custom percentile.
- Clinical filters by sample type, stage, grade, gender, race, minimum age, maximum age and maximum follow-up.
- Administrative censoring when maximum follow-up is defined.

#### KM Analysis Outputs

- Kaplan-Meier plots generated in R with `survival`, `survminer` and `ggplot2`.
- Plot options for confidence interval, risk table, colors, font family, font sizes, grid, title, aspect ratio and X-axis units in days, months or years.
- Analysis metrics including patients, events, log-rank p-value, hazard ratio, median survival, group counts and group event counts.
- Univariable Cox and adjusted Cox models for stage, grade and stage plus grade when evaluable.
- Proportional hazards diagnostics using `cox.zph`.
- Cox forest plot.
- RMST for two-group comparisons, including tau, difference, confidence interval and p-value.
- Expression distribution before cutpoint selection and per-analysis quality summary.
- REMARK-style methodology report per analysis.

#### Two-Signature Outputs

- Cox interaction models for two signatures using `signature_A_z + signature_B_z + interaction`.
- Combined-group Kaplan-Meier outputs for median x median and tertile x tertile grouping.
- Shared plot export, audit and methodology outputs for combined-signature analyses.

#### Compare Analyses And Robustness

- Gene x cutpoint comparison page.
- Batch execution with up to 10 parallel analyses.
- Visual comparison matrix with Kaplan-Meier thumbnails per cell.
- Multiple-testing correction using Benjamini-Hochberg and Bonferroni adjustment across completed comparisons.
- Cutpoint robustness summary using BH, Cox, adjusted Cox, RMST and PH diagnostics.
- Explicit "Run all 5 cutpoint methods" control for dichotomization robustness.

#### Pan-Cancer Analysis

- Pan-cancer scan with continuous Cox per cohort and within-cohort expression z-scoring.
- Pan-cancer endpoint modes: same endpoint, death-like, progression-like and best available.
- Pan-cancer outputs with FDR, effect direction, index-cohort concordance and random-effects meta-analysis.
- Pan-cancer visualizations: forest plot, concordance map, evidence landscape, power/precision map and cohort table.
- Precomputed immune pan-cancer atlas with gene, cohort, term and recurrent-signal summaries.
- Immune atlas downloads for genes, cohorts, terms, results, panel, manifest and methodology.

#### Dataset Summary

- Dataset Summary page with global KPIs, data dates, source status, endpoint coverage and cohort table.
- Dataset visualizations including cohort dot plot, donut charts, age histogram, metadata coverage matrix and primary-site distribution.
- Cohort filter in Dataset Summary.
- CSV export for dataset summary.

#### Downloads, Caching And Data Operations

- Per-analysis downloads: PNG, SVG, CSV, Cox PNG/SVG, metrics JSON, methodology TXT, audit JSON, audit HTML and ZIP bundle.
- On-demand SVG generation to reduce initial latency.
- Non-blocking download notifications.
- Analysis cache keyed by parameter hash and data version.
- Reproducible audit report with parameters, endpoint, sample selection, patient records, hashes, software versions and artifact checksums.
- Incremental TCGA RNA and TCGA-CDR synchronization through the GDC API.
- `check` and `apply` commands for data updates.
- Download validation by checksum, file size and expected columns.
- Atomic promotion of updated files, backups and derived-cache invalidation.
- Weekly TCGA update script.
- RNA bulk transformation documentation.

#### Publication Materials

- Comparative tool matrix for publication positioning.
- Benchmark protocol and benchmark scripts.
- Manuscript-ready tables and publication-readiness documentation.

## Current Application State - July 2026

### ordinal-clinical-adjusted-cox-audit-rmst-maxstat-v4.4

Single-signature survival pipeline.

- Replaces categorical stage/grade terms in adjusted Cox models with explicit
  ordinal trends to reduce sparse-level separation and improve ordinary
  clinical adjustment.
- Maps Stage 0/I/II/III/IV to 0/1/2/3/4, collapsing A/B/C substages to their
  major stage; maps G1-G5 to 1-5.
- Treats unrecognized values such as Stage X and GX as missing rather than
  assigning an artificial order.
- Fits stage+grade when both ordinal covariates are evaluable and preserves
  stage-only and grade-only models as explicit fallbacks.
- Records encoding type, unit, mapped-patient count, observed scores and
  unmapped values with each adjusted model.
- Interprets adjusted coefficients under a linear log-hazard trend per
  one-category increase; this assumption is reported as a model limitation.
- Separates cohort-construction provenance from model-specific convergence and
  proportional-hazards cautions in the web interface without removing either
  from reproducibility exports.

### combined-signatures-ordinal-interaction-cox-audit-rmst-v2.4

Two-signature combined group pipeline.

- Applies the same ordinal stage and grade encoding to continuous
  two-signature interaction Cox models.
- Reports stage+grade, stage-only and grade-only adjusted interaction variants
  separately when evaluable.
- Leaves signature scoring, crossed grouping, interaction definition, audit
  hashing and artifact exports unchanged.

### clinical-adjusted-cox-audit-rmst-maxstat-v4.3

Single-signature survival pipeline.

- Uses TCGA-CDR endpoints when available: OS, DSS, PFI and DFI.
- Enables endpoints only after minimum patient and event QC.
- Keeps one prioritized RNA biospecimen per patient for patient-level survival analysis.
- Supports single gene, mean signature, z-score signature and weighted signature scoring.
- Fits Kaplan-Meier, log-rank, univariable Cox and clinically adjusted Cox models when covariates are evaluable.
- Reports cox.zph proportional hazards diagnostics.
- Reports RMST for two-group comparisons, including tau sensitivity in raw outputs.
- Records maxstat cutpoints as optimized exploratory cutpoints and stores the approximate maximally selected rank statistic p-value from `maxstat::maxstat.test` with `pmethod=Lau94`.
- Exports reproducibility audit reports with payload hash, patient records, model outputs, software versions and artifact checksums.

### clinical-adjusted-cox-audit-rmst-v4.2

Single-signature survival pipeline.

- Uses TCGA-CDR endpoints when available: OS, DSS, PFI and DFI.
- Enables endpoints only after minimum patient and event QC.
- Keeps one prioritized RNA biospecimen per patient for patient-level survival analysis.
- Supports single gene, mean signature, z-score signature and weighted signature scoring.
- Fits Kaplan-Meier, log-rank, univariable Cox and clinically adjusted Cox models when covariates are evaluable.
- Reports cox.zph proportional hazards diagnostics.
- Reports RMST for two-group comparisons.
- Exports reproducibility audit reports with payload hash, patient records, model outputs, software versions and artifact checksums.

### combined-signatures-interaction-cox-audit-rmst-v2.3

Two-signature combined group pipeline.

- Scores Signature A and Signature B independently.
- Supports single, mean, z-score and weighted scoring for each signature.
- Defaults multi-gene signatures to z-score scoring because each gene contributes on a comparable scale.
- Creates median x median four-group comparisons or tertile x tertile multi-group comparisons.
- Fits interaction Cox models on continuous signature z-scores.
- Preserves the same audit and plot export behavior used by the single-signature pipeline.

### pancancer-primary-plus-ordinal-sensitivity-cox-audit-v2.1

Pan-cancer primary plus clinical-sensitivity pipeline.

- Preserves the original continuous within-cohort z-score Cox model as the primary cross-cancer estimand.
- Adds parallel ordinal stage, grade and stage+grade sensitivity models when complete-case sample and event criteria are met.
- Selects the displayed adjusted model by covariate availability only: stage+grade, then stage, then grade.
- Applies BH-FDR within every adjustment family and to the availability-selected sensitivity tests.
- Reports DerSimonian-Laird meta-analysis separately by adjustment family and deliberately refuses to pool mixed selected families.
- Treats unavailable clinical covariates as not evaluable rather than as execution warnings.
- Keys public-job reuse to both pipeline and data versions so completed jobs cannot return artifacts from an older scientific context.
- Exports cohort and patient CSV files, parameter-specific methods, raw R results, JSON/HTML audit reports and a ZIP bundle.

### pancancer-cox-v1.0

Pan-cancer continuous Cox pipeline.

- Fits one Cox model per cancer using expression z-scored within each cohort.
- Reports HR per +1 SD expression.
- Applies BH-FDR adjustment across modeled cohorts.
- Summarizes effect direction concordance and random-effects meta-analysis.
- Supports endpoint modes: same endpoint, death-like, progression-like and best available.

### cutpoint-robustness-v1.0

Dichotomization robustness panel.

- Runs maxstat, median, upper quartile, outer quartiles and selected percentile cutpoints.
- Applies BH and Bonferroni adjustment across completed comparison cells.
- Flags downstream robustness using log-rank, Cox, adjusted Cox, RMST direction and PH diagnostics.
- Clarifies that maxstat is exploratory because the cutpoint is optimized against survival separation.

### dataset-qc-v1.0

Dataset inventory and sample QC.

- Summarizes cohort, sample, patient and endpoint coverage.
- Tracks data source dates, RNA cache generation and database import time.
- Documents TCGA source status and endpoint availability for analysis decisions.
