# Second Review Implementation Log

Status date: 2026-07-25.

This is the authoritative checklist for the second external statistical and
reproducibility review. An item is `complete` only when implementation,
generated evidence and manuscript wording agree. Historical review notes remain
useful context but do not override this ledger.

## Status Vocabulary

- `complete`: implementation and acceptance evidence verified.
- `in_progress`: implementation is being changed or regenerated.
- `pending`: confirmed gap with an agreed acceptance criterion.
- `verify`: likely implemented, but current evidence has not yet been rerun.
- `owner`: requires an author or repository-owner decision.
- `deferred`: explicitly outside the Application Note release and stated as a
  limitation; it remains open in the long-term backlog.

## Submission-Critical Ledger

| ID | Status | Requirement | Acceptance evidence |
| --- | --- | --- | --- |
| R2-01 | complete | Fixed, group-label-independent RMST horizon | Every two-group export reports the cohort-level tau rule, tau value, at-risk support and 0.75/0.90 sensitivities; tests cover cutpoint invariance. |
| R2-02 | complete | Numeric endpoint and adjusted-model QC | API and manuscript state >=10 patients and >=5 events as operational thresholds; adjusted models repeat complete-case QC. |
| R2-03 | complete | Age and exact user-selected clinical adjustment | Continuous, grouped and interaction Cox models accept age, stage, grade, gender and race; age is the UI default; model-specific N/events/parameters are exported. |
| R2-04 | complete | Continuous single-marker analysis | Every single-gene or one-signature analysis reports cutpoint-independent linear Cox and restricted cubic spline outputs before grouped sensitivities. |
| R2-05 | complete | Marker-specific PH without binary exclusion | Marker-term and global `cox.zph` results are separate; neither removes an association; no retained/not-retained field is produced by current benchmarks or multiverse exports. |
| R2-06 | complete | Sparse-data diagnostics and Firth sensitivity | Every Cox family reports fitted parameters and events per parameter; Firth is triggered for low-information, unstable or extreme estimates. |
| R2-07 | complete | ACC stage mapping audit | ENSAT stage is normalized and patient-level clinical fallback restores 77/79 evaluable ACC stages; regression tests cover the mapping. |
| R2-08 | complete | Prespecified multiverse export | One request freezes endpoint x scoring x cutpoint cells, separates continuous/grouped families and exports all successes, failures, child hashes and a specification curve. |
| R2-09 | complete | Expression-complete biospecimen selection | Clinical/endpoint eligibility now precedes requested-score completeness and biospecimen priority. Audit fields record missing-expression removals and lower-priority fallbacks; unit tests cover single, multi-gene and crossed signatures, and all six feature benchmarks completed under the revised pipelines. |
| R2-10 | complete | Accurate integrity claim and threat model | Manuscript and evidence lead with three frozen analyses and six isolated reruns, identify internal checks as dependent coverage, and restrict the unsigned-hash threat model to accidental drift, corruption or incomplete transfer rather than adversarial forgery. |
| R2-11 | complete | Integrity-boundary coverage test | Eleven controls prove that request, patient, score and source mutations change the reproducibility hash; plot/method mutations preserve that hash but fail artifact checksums; generated-at/quality fields and recomputed unsigned hashes are explicitly outside scope. |
| R2-12 | complete | Quantity-aware reproduction tolerances | Exact fields compare exactly; probabilities, effects, times and generic floats use versioned absolute-plus-relative policies. Six arm64/amd64 isolated reruns passed and publish per-case comparison counts plus maximum observed absolute and relative errors. |
| R2-13 | complete | Multiplicity aligned to hypotheses | BH remains over 11 prespecified continuous marker hypotheses and 11 nonlinearity hypotheses. The four grouped rules use Holm within each marker-endpoint scenario, with corrected maxstat inference and no suite-dependent verdict. Calibration uses the same four-rule Holm family. |
| R2-14 | complete | Quantified maxstat selection diagnostic | All 11 scenarios report continuous, median and maxstat effects on a common observed group-mean contrast, amplification or an explicit non-estimable reason, Lau94 inference and post-selection cautions. Raw out-of-range Lau94 approximations are preserved while reported probabilities are bounded to [0,1]. |
| R2-15 | complete | Common-scale pan-cancer synthesis | Per-SD cohort effects are descriptive and non-pooled. Eligible same-endpoint, same-family effects are recovered per +1 shared input-score unit and synthesized with REML/HKSJ plus a 95% prediction interval; mixed endpoints/families and cohort-standardized z-score signatures are not pooled. |
| R2-16 | complete | Main-text empirical evidence | One integrated vector figure summarizes the auditable workflow, while Supplementary Table S4 retains the complete 11-scenario x four-rule evidence matrix with continuous/nonlinear evidence, Holm p-values, direction, maxstat amplification, PH, low-information and Firth cautions. The main article contains no table, and the OUP preview passes at four pages. |
| R2-17 | complete | Prespecified scenario and endpoint registry | Registry v1.0.0 freezes all 11 scenarios, literature anchors, endpoint roles and change control. Every generated scenario metadata file carries the registry SHA-256; tests reject code/registry endpoint drift. |
| R2-18 | complete | External concordance panel | Three cases prespecified on 2026-07-23 were rerun against frozen cBioPortal PanCancer Atlas API snapshots: supported PDCD1/SKCM, direction-only CA9/KIRC and unsupported CD274/LUAD. Access date, source hashes, patient inputs, model outputs and cross-pipeline limits are retained. |
| R2-19 | complete | Supplement order and cutpoint rationale | Tables and first citations now proceed S1--S8. Main text, supplement and benchmark guide define the four-rule Holm family and explain that tertiles are three-group while a custom percentile is user-defined. |
| R2-20 | complete | Z-score transportability warning | Parameter help, completed-result notices, methodology and structured JSON/HTML audit exports state that the expression-complete endpoint/filter population defines within-run standardization and that numerical z-score signature scores are not transportable across runs. |
| R2-21 | complete | Competing-risk interpretation contract | UI, methodology, JSON/HTML audit and manuscript distinguish KM/cause-specific Cox estimands from cumulative-incidence and Fine--Gray estimands, disclose endpoint-specific 0/1/2 event coding and preserve the non-informative censoring assumption where competing deaths are censored. |
| R2-22 | complete | Runtime and concurrency evidence | A public-API benchmark reports uncached/cached single analysis, two-job overlap, 10-analysis batch, 72-cell multiverse and 33-cohort pan-cancer wall/queue/compute times, observed Docker cgroup memory, hardware and queue limits. Raw JSON, CSV, manifest and Table S8 pass the frozen-output gate. |
| R2-23 | complete | Canonical project identity | UI, API/MCP metadata, manuscript outputs and review archive use TCGA-TRACE or `tcga-trace`; the archive manifest declares the project name. `/tcga_explorer`, the repository slug and historical internal identifiers are documented only as compatibility surfaces, with an automated identity gate. |
| R2-24 | owner | Final owner and release handoff | Authorship, four affiliations, funding and the no-conflict declaration were supplied on 2026-07-25. CI now includes a manual exact-tag release gate that requires the HTTPS deployment to report the checked-out commit and tag before rerunning browsers, tests, metadata, manuscript and archive checks. Owners must still confirm corresponding author/email/ORCID, CRediT, AI disclosure, APC route and support ownership; approve a top-level OSI license; tag, push and deploy the exact release with its commit and ref identity; archive it under an immutable Zenodo DOI; and replace every remaining placeholder consistently. |

## Long-Term Scientific and Product Backlog

| ID | Status | Requirement | Completion criterion |
| --- | --- | --- | --- |
| L-01 | complete | Cohort-specific or uploaded covariates | Schema v1 accepts an explicitly selected patient-level CSV with exact TCGA participant linkage, continuous/categorical/ordinal coding, reference levels, units, bounded size and privacy warnings. Single, combined, Compare and multiverse requests propagate the frozen dataset into complete-case grouped, continuous and interaction Cox models; exports record source, SHA-256, coding, matching, missingness and model diagnostics. |
| L-02 | complete | Time-varying marker effects | PH-flagged models provide a prespecified time-varying effect summary or early/late contrast without data-driven interval shopping. |
| L-03 | complete | Competing-risk models | DSS, DFI and PFI workflows expose cumulative incidence with pointwise confidence intervals, Gray tests and grouped/continuous Fine--Gray models beside distinct cause-specific estimands; endpoint-specific competing-event coding is retained in UI, exports, audits and standalone reproduction. |
| L-04 | complete | Standalone analysis CLI | The dependency-free CLI checks the live OpenAPI contract; discovers public resources; submits and polls single, combined, batch, multiverse, pan-cancer and exploratory-session jobs; recursively downloads retained artifacts; and verifies analysis, multiverse, pan-cancer and session bundles with stable machine-readable exit behavior. |
| L-05 | complete | Third-party attestation | Persistent server-side Ed25519 keys sign the exact audit bytes, schema and recorded run hash for analysis, multiverse, pan-cancer and exploratory-session families. The public-key API, standalone verifier, frozen positive and adversarial mutation controls, browser receipt downloads and review-archive gate verify the signed boundary while excluding private key material. |
| L-06 | complete | Session-wide exploratory history | Recording is browser-local, optional and disabled by default. A selected export resolves up to 200 terminal run events server-side, preserves repeated executions, deduplicates exact hypotheses, separates continuous Cox, grouped-cutpoint and two-signature-interaction BH/Bonferroni families, and references managed multiverse/pan-cancer families without recounting them. Patient records and uploaded covariate rows are excluded; the signed report states that its post hoc selected scope cannot prove that no other runs occurred. |

## Verification Gates

- Backend unit and integration tests pass.
- Publication-script tests pass.
- Frontend production build passes.
- All publication benchmarks regenerate from the declared snapshot.
- Clean-container reproduction passes on native and hosted amd64.
- Main OUP preview remains within four pages.
- Supplementary citations and table numbering are sequential.
- Submission artifact and archive verifiers pass.
- Runtime smoke tests confirm the deployed UI and public API expose the revised
  contracts.

## Work Log

### 2026-07-25

- Created this authoritative ledger from the second external review and the
  current implementation audit.
- Confirmed that age/user adjustment, continuous single-marker Cox/spline,
  marker-specific PH, Firth, ACC stage repair, OpenAPI and the prespecified
  multiverse already exist.
- Confirmed that expression completeness is currently checked after
  one-sample-per-participant selection; R2-09 is the first implementation block.
- Reordered cohort construction to apply user filters and endpoint completeness,
  require the requested gene or complete signature score, and only then choose
  the highest-priority expression-complete biospecimen.
- Added audited counts for expression-complete candidates, patients removed for
  missing expression and lower-priority biospecimen fallbacks. Pan-cancer rows
  now retain the same cohort-level selection record after the R model fit.
- Added regression coverage for single-gene fallback, multi-gene score
  completeness, crossed-signature intersection, warning normalization and
  pan-cancer preparation metadata.
- Verified 28 focused tests and 86 backend tests, then rebuilt backend/worker and
  regenerated six feature benchmarks. Both pan-cancer scans completed across 32
  evaluable cohorts with pipeline
  `expression-complete-sample-selection-audit-v2.5`.
- Replaced the grouped 44-test suite-wide BH interpretation with two declared
  multiplicity layers: BH across the 11 continuous linear and 11 spline
  hypotheses, and Holm across four grouped rules within each marker-endpoint
  scenario. Maxstat contributes its Lau94 selection-adjusted p-value.
- Regenerated 44 single-gene analyses under analysis pipeline
  `expression-complete-integrity-contract-v6.5`. Five of 11 scenarios support
  all four grouped rules, one supports three of four and five support none;
  23/44 supported cells are retained only as a secondary count.
- Added a same-contrast diagnostic that projects the continuous Cox coefficient
  onto each split's observed group-mean expression difference. Among 10
  scenarios with finite standard median and maxstat grouped HRs, maxstat had a
  larger absolute log-HR in 10/10 (median ratio 1.80). UVM BAP1 is explicitly
  non-estimable because its standard maxstat Cox estimate is non-finite.
- Bounded Lau94 approximations to [0,1], retained the raw approximation and a
  clamping flag, and added regression coverage. Two null-like scenarios had raw
  approximations above 1.
- Recalibrated 2,000 observed-cohort permutations and 2,000 simulations per
  mechanism with the four-rule Holm family. Null family rejection was 3.2% in
  observed permutations and 3.5% in simulated null data.
- Updated the paper-example API and frontend to display within-scenario Holm
  inference and the same-contrast amplification diagnostic. Frontend production
  build passed and the local containers expose the revised catalog.
- Manuscript and supplement now describe the declared families and maxstat
  diagnostic. The interim editorial gate correctly reports two remaining
  R2-16 issues: eight supplementary tables and a five-page OUP preview.
- Replaced pan-cancer DerSimonian--Laird synthesis with REML random effects,
  HKSJ inference and a 95% prediction interval on an exact common input-score
  scale. Per-SD cohort effects remain available descriptively and never carry a
  pooled diamond. Same-endpoint and same-adjustment-family checks are enforced;
  z-score signatures and mixed endpoints/families return an explicit
  non-pooling reason.
- Added self-describing `effect_scale`, `common_scale_*`,
  `common_scale_unit` and `common_scale_eligible` fields to API, CSV, audit and
  paper-example outputs. The pan-cancer marker-term and global PH fields are now
  distinct, and full-precision JSON prevents four-digit coefficient rounding.
- Added reference-value tests for Student-t inference, mixed-endpoint refusal,
  row-level scale metadata and an R integration test proving that the common
  coefficient and standard error equal the standardized values divided by the
  cohort score SD. The directed backend suite passes 25/25 tests and both
  backend and frontend production images build.
- Regenerated BIRC5 and CA9 under
  `common-scale-reml-hksj-integrity-contract-v2.8`. BIRC5 reports HR 1.20
  (HKSJ 95% CI 1.06--1.37), PI 0.64--2.24 and I2=86.1%; CA9 reports HR 1.04
  (1.00--1.08), PI 0.93--1.16 and I2=60.7%. Manuscript, supplement, API guides,
  UI help and reviewer materials use the same estimands and numbers.
- All LaTeX targets compile. The editorial gate still fails only the already
  declared R2-16 constraints: eight supplementary tables and a five-page OUP
  preview.
- Replaced the workflow figure in the article body with a generated
  11-scenario x four-cutpoint empirical matrix. The vector workflow remains a
  separate graphical-abstract artifact. The table exposes continuous BH
  results, spline nonlinearity, grouped direction and within-scenario Holm
  p-values, Firth fallbacks, maxstat/median amplification and PH/information
  diagnostics without hiding null or mixed-direction cases.
- Merged the separate maxstat table into the main empirical matrix and retained
  its complete machine-readable CSV, reducing the supplement from eight to
  seven tables. Added a render-only benchmark mode and regression coverage so
  the table is regenerated from frozen summary CSVs without resubmitting jobs.
- Recompiled the review manuscript, supplement and Bioinformatics OUP preview.
  The technical editorial gate now passes: one generated main table, seven
  supplementary tables, all 17 Paper Examples mapped and a legible four-page
  OUP preview. Main text was edited for information density rather than by
  shrinking journal typography.
- Frozen the 11-scenario publication panel in
  `docs/publication/benchmark/scenario_registry_v1.json` (registry v1.0.0,
  SHA-256
  `393cbc06edfae73843641af77aac17873c49ab91984a207e2ee5155319300f4c`).
  The registry states that the initial panel arose from retrospective
  exploratory triage and prohibits result-driven in-place changes during future
  regeneration.
- Registered OS as the default primary endpoint, UVM BAP1 DSS as the sole
  literature-motivated exception, and BRCA MKI67 PFI plus LUAD CD274 PFI as
  endpoint sensitivities that cannot replace their OS parents based on observed
  results.
- Bound registry version, file hash, role, rationale and literature anchors to
  every per-scenario benchmark metadata file and aggregate overview. Five
  focused tests verify exact suite coverage, parent relationships, metadata
  binding and rejection of endpoint drift. The publication compliance gate
  continues to pass with a four-page OUP preview.
- Re-executed the single-gene, weighted-signature and crossed-signature
  capsules on native arm64 and emulated Linux/amd64 after detecting that the
  previous frozen evidence predated the quantity-aware policy metadata. All
  six isolated reruns passed under
  `tcga-trace-numeric-comparison-v1`; maximum absolute error was
  `1.1369e-13` and maximum relative error was `5.8193e-14`.
- Verified 11/11 integrity-boundary controls and both negative controls.
  Bound request, patient, expression-component and source mutations changed the
  run hash; plot and method-text mutations remained outside that hash and
  failed their artifact checksums. The report states that unsigned hashes
  detect accidental drift rather than adversarial rewriting.
- Removed the misleading `R rerun = no` column from the supplementary
  reconstruction table. It now reports the six isolated reruns, numeric values
  compared and worst observed errors. Fourteen focused reproducibility tests
  and the frozen-output verifier pass.
- Built a reproducible three-case external concordance panel from the official
  cBioPortal API using the cases prespecified on 2026-07-23. Frozen PanCancer
  Atlas source snapshots were accessed on 2026-07-25, reduced to one
  OS/expression-complete sample per patient under an explicit sample-code rule,
  and analyzed with median-split log-rank and Efron Cox models.
- PDCD1/SKCM agreed in direction and nominal support (external HR 0.57 versus
  TCGA-TRACE 0.53); CA9/KIRC agreed in direction but not nominal support (0.81
  versus 0.68); CD274/LUAD was unsupported in both, with null point estimates
  on opposite sides of one (1.08 versus 0.99). The panel explicitly states that
  shared TCGA origin, RSEM versus GDC TPM, endpoint curation and sample release
  differences preclude independent validation or exact replication.
- Added source-snapshot hashes, a panel manifest, offline `--render-existing`
  and `--check-only` paths, four focused tests and manuscript/supplement
  reporting. The historical KM Plotter CA9 record was refreshed against the
  current TCGA-TRACE run without issuing new automated queries. Editorial
  compliance remains green with seven supplementary tables and a four-page OUP
  preview.
- Reordered the first three supplementary tables so comparator positioning,
  signature definitions and reconstruction evidence are Tables S1, S2 and S3,
  respectively. Main-text first citations now proceed sequentially through
  S1--S7; the generated supplement confirms the same caption order.
- Removed stale calibration wording for five grouped methods, a 60th-percentile
  split and grouped BH. The paper and benchmark guide now consistently define
  maxstat, median, upper quartile and outer quartiles as a four-rule
  within-replicate Holm family, excluding tertiles because they create three
  groups and custom percentiles because they are user-defined.
- Extended the editorial compliance gate to reject out-of-order first
  citations and stale cutpoint-family wording. Eight focused editorial tests
  pass, and the gate reports seven tables plus a four-page OUP preview.
- Added one shared interpretation contract for z-score signatures and DSS.
  Z-score signatures now disclose their endpoint/filter-dependent
  expression-complete reference population and lack of numerical
  transportability across runs. DSS now discloses other-cause censoring, the
  non-informative censoring assumption and the absence of cumulative-incidence
  or Fine-Gray estimation.
- Propagated the exact statements through contextual parameter help,
  completed-result notices, single/combined analysis methodology, multiverse
  methodology, pan-cancer methodology and structured JSON/HTML audit fields.
  The notices are informational and do not alter eligibility, estimates or
  model status.
- Incremented analysis, combined-signature, multiverse and pan-cancer pipeline
  versions to invalidate stale cached reporting contracts. Rebuilt the running
  backend, worker and frontend, regenerated all six advanced feature examples
  and verified the new structured contexts in frozen z-score and DSS audit
  reports.
- Verification passed with 40 focused backend tests, 103 full backend tests,
  six frontend tests and a production frontend build.
- Added a reproducible public-API runtime and concurrency benchmark covering an
  uncached single run, exact cached repeat, two concurrent jobs, a 10-analysis
  batch, the 72-cell multiverse limit and all 33 requested pan-cancer cohorts.
  The record distinguishes analysis-result cache misses from operating-system
  or import cold starts and binds hardware, Docker resources, service limits,
  pipelines and data snapshot.
- On the declared Apple M1 Ultra/Docker host, wall times were 5.121 s for an
  uncached single run, 0.037 s for its exact cached repeat, 5.231 s for two
  overlapping jobs, 32.47 s for the batch, 218.8 s for the multiverse and
  7.180 s for pan-cancer. The two-job probe observed 2.53 s overlap under
  global concurrency two; peak backend-plus-worker cgroup memory ranged from
  224.7 to 775.7 MiB.
- Integrated the protocol and generated results as Supplementary Table S8,
  extended editorial numbering and archive gates, and kept the OUP preview at
  4/4 pages. Twenty focused tests, the six-workload frozen-output check,
  82/82 artifact check and a 362-entry review archive verification passed.
- Established TCGA-TRACE as the canonical display, manuscript and release
  identity. Replaced the final two visible `TCGA Explorer` labels, renamed all
  generated PDFs with a `tcga-trace` prefix and added `project_name:
  TCGA-TRACE` to the checksummed review archive manifest.
- Documented `/tcga_explorer`, the current repository slug, database names,
  deployment variables and historical schema versions as stable legacy
  compatibility identifiers rather than alternate product names. Added a
  repository identity gate and test to prevent display/package regressions.
- Regenerated the manuscript from a clean build directory. The canonical
  package passed 104 backend tests, 105 publication-script tests, six frontend
  tests, the 4/4-page editorial gate, 84/84 artifact checks and verification of
  a 365-entry TCGA-TRACE review archive.
- Synchronized the final-decision tracker, artifact manifest, submission
  checklist and reviewer reproduction guide with that canonical validation
  snapshot. The non-strict metadata gate now isolates 30 placeholder detections
  that collapse to the single R2-24 owner/release handoff; no scientific or
  engineering gate remains open.
- Added a generated compatibility contract that runs Survival, Compare, Paper
  Examples, Pan-cancer, Dataset Summary, downloads, keyboard focus and reduced
  motion in isolated Chromium, Firefox/Gecko and WebKit containers. The
  provisional development build passed 18/18 checks; strict finalization
  requires a clean exact-tag checkout and the public HTTPS deployment.
- The compatibility run exposed and verified a real Compare autocomplete race:
  step focus could commit partial text before suggestions arrived. Gene search
  is now cancellable, stale responses are ignored, partial blur commits are
  rejected and accessible loading/error states are shared by Survival,
  crossed signatures, Compare and Multiverse.
- After integration, 112 publication-script tests and six frontend tests pass,
  the production frontend was rebuilt, 88/88 submission artifacts are
  available and the reviewer archive verifies 370 entries.
- Audited the six long-term backlog items against the current implementation.
  Existing exact adjustment is limited to imported age, stage, grade, gender
  and race; marker/global PH diagnostics do not yet estimate time-varying
  effects; DSS currently documents but does not model competing events; audit
  hashes remain unsigned; and the multiverse ledger does not capture unrelated
  ad hoc browser runs. The public API and retained artifact contract provided a
  complete foundation for the standalone CLI.
- Added `scripts/tcga_trace_cli.py`, a Python-standard-library client for the
  public REST v1 contract. It supports service/cohort/gene discovery, live
  OpenAPI operation checks, request-file submission, persistent polling and
  recursive downloads for single, combined-signature, batch, multiverse and
  pan-cancer workflows. Every download receives a local URL/bytes/SHA-256
  manifest.
- Added family-aware local verification. Analysis bundles verify participant,
  continuous-population, score, core-result, artifact and reproduction-capsule
  hashes; multiverse bundles verify request and declared-family hashes;
  pan-cancer bundles verify the audit reproducibility hash and artifact
  checksums. ZIP traversal, duplicate-member and symlink controls fail closed.
  The documentation preserves the unsigned-hash threat model.
- Added English and Spanish CLI guides, stable JSON errors and exit codes,
  changelog/help entries, CI coverage and reviewer-archive integration.
  Twelve CLI tests cover all five compute families plus mutation and unsafe-ZIP
  controls. A real cached CDC20/LIHC request passed OpenAPI validation,
  submission, retained-ZIP download and verification against the running local
  Docker deployment.
- Fixed the non-strict pre-submission path for macOS Bash 3.2, where expanding
  an empty strict-browser argument array under `set -u` aborted before the
  frozen browser check. The gate now branches explicitly for provisional and
  strict final-release validation.
- Final L-04 validation passed 104 backend tests, 112 publication-script tests,
  12 CLI tests, six frontend tests and the production frontend build. The full
  pre-submission gate rebuilt the 4/4-page OUP preview, verified provisional
  browser evidence across 18/18 checks, found 92/92 artifacts and verified a
  374-entry review archive. The only submission-critical blockers remain the
  30 owner-controlled metadata/license/release placeholders under R2-24.
- Replaced the manuscript's placeholder authors with Sergio Hernández-Galaz,
  Andrés Hernández-Oliveras, Ignacio Pezoa-Soto, Javiera Reyes-Alvarez,
  Vincenzo Benedetti, Alberto J. M. Martin and Alvaro Lladser; added the four
  supplied affiliations and the declaration that the authors have no conflicts
  of interest. R2-24 remains owner-controlled for correspondence, ORCID, CRediT,
  AI disclosure, APC, support, license, release and DOI decisions.
- Added the owner-supplied funding statement for Centro Basal Ciencia \& Vida
  FB210008, ANID Fondecyt grants 1251312 and 1231629, ANID postdoctoral
  fellowship 3260791 and NLHPC CCSS210001. The MVG/MVJ project and the IPS PhD
  fellowship were intentionally excluded as requested.
- Completed L-01 with external-covariate schema v1. CSV uploads require an
  exact `patient_id` column, reject duplicates and malformed identifiers, and
  are bounded to 10 covariates, 2,000 participant rows and a 2 MiB source file.
  Variables may be continuous, categorical or ordinal; users explicitly select
  which variables enter Cox models and define effect units, reference levels or
  ordered levels before submission.
- Added a progressive, keyboard-accessible editor to Survival, Compare and
  Multiverse. It previews matching and coding, selects no uploaded variable by
  default, warns that participant-level clinical data leave the browser, and
  supports replacement or removal without retaining a hidden adjustment.
- Propagated the frozen external dataset through single-marker/signature,
  crossed-signature, comparison-batch and multiverse requests. Grouped,
  continuous and interaction Cox families apply deterministic complete-case
  coding and report model-specific patients, events, parameters, events per
  parameter, PH diagnostics and sparse-data cautions.
- Extended methodology and JSON/HTML audit exports with the external source
  label, dataset SHA-256, selected coding, units, references, level order,
  cohort matching, missingness and exact retained values. Analysis, combined
  and multiverse pipelines advanced to versions 6.7, 3.9 and 1.6.
- Raised the reverse-proxy request-body allowance to 64 MiB for bounded API and
  MCP batch envelopes; documented the matching Apache
  `LimitRequestBody 67108864` requirement. Application-level schema limits
  remain authoritative.
- A real local EMP3/LGG smoke run matched 180/180 synthetic smoke-only records
  and completed categorical, continuous and ordinal external adjustment in
  grouped and continuous models. Its raw CSV, methodology and audit exports
  preserved all three covariates and their declared coding; the synthetic run
  is implementation evidence, not scientific evidence.
- Final L-01 validation passed 115 backend tests, 112 publication-script tests,
  12 CLI tests, 10 frontend tests, the production frontend build and
  `git diff --check`. The OUP preview remains 4/4 pages. An isolated browser
  contract exercised upload, privacy disclosure, recoding, explicit selection
  and removal across Chromium, Firefox/Gecko and WebKit and passed 18/18 checks;
  exact-tag public HTTPS validation remains part of owner-controlled R2-24.
- Completed L-02 with a prespecified two-period marker-effect diagnostic. It is
  triggered only when the marker-term `cox.zph` p-value is below 0.05, uses a
  fixed two-year (730.5-day) split for every analysis, Efron ties and
  participant-clustered robust sandwich variance, and requires at least five
  events in each period and 10 participants entering the late period. The split
  is never selected from expression, event times, cutpoints or effect estimates.
- Added early and late marker HRs, confidence intervals and p-values, the
  late/early HR ratio, marker-PH trigger, support counts and explicit
  completed/skipped/failed/not-triggered status to continuous, grouped,
  crossed-signature interaction and pan-cancer Cox families. The diagnostic is
  an interpretation aid only: it does not replace the primary estimand, enter a
  multiplicity family, exclude a result or create a composite verdict.
- Propagated the contract through public JSON schemas, multiverse and pan-cancer
  CSVs, methodology, JSON/HTML audit reports, the analysis UI and frozen Paper
  Examples. The catalog now selects the exact registered
  `continuous_user_adjusted` model rather than silently substituting a
  stage/grade model, and retains primary and adjusted pan-cancer temporal
  diagnostics.
- Regenerated the canonical EMP3/LGG benchmark and all six advanced feature
  examples under analysis pipeline 6.8, combined-signature pipeline 4.0,
  multiverse pipeline 1.7 and pan-cancer pipeline 3.0. The EMP3 age-adjusted
  continuous model used 511 participants/125 events and reported marker PH
  p=0.0115, HR 2.78 (2.20--3.51) at 0--2 years, HR 1.82 (1.39--2.39) after two
  years and late/early ratio 0.66 (0.46--0.94; p=0.023). Median, upper-quartile
  and outer-quartile grouped models completed the same diagnostic; maxstat was
  correctly `not_triggered` because its adjusted marker PH p=0.103.
- Updated main and supplementary Methods and Results with the fixed split,
  support rule, variance, diagnostic-only interpretation and EMP3 result. The
  editorial compiler reports no technical blocker and the OUP preview remains
  4/4 pages.
- Final L-02 validation passed 120 backend tests, 115 publication-script tests,
  12 CLI tests, 10 frontend tests, the production Vite/Docker builds,
  `git diff --check` and the live API contract. Chromium, Firefox/Gecko and
  WebKit passed 18/18 browser checks, including continuous and median-grouped
  EMP3 temporal tables. The local multi-engine run temporarily raised the batch
  quota only to avoid two pre-existing hourly test jobs; the deployed stack was
  immediately restored and verified at the public default of two batches/hour.
  Exact-tag public HTTPS validation remains owner-controlled under R2-24.
- Restructured the Application Note against the accepted GRNContext editorial
  pattern and Nature-style readability guidance. The main narrative now uses
  concise descriptive case headings, separates calibration/runtime from the
  biological cases and closes with `Future Plans` while retaining explicit
  scientific boundaries.
- Replaced the 11-scenario main-text table with the integrated vector Figure 1.
  The article now contains exactly one figure with inline alt text and no
  empirical tables; the full evidence matrix remains in Supplementary Table S4.
  The synchronized OUP preview remains 4/4 pages, the review manuscript is 11
  pages, and the focused editorial tests pass 10/10.
- Rechecked the narrative against the accepted GRNContext Application Note and
  Nature readability guidance. The main results section is now `Case Studies
  and Evaluation`, with four declarative headings of at most 40 characters:
  analysis-record reconstruction, cutpoint/PH sensitivity, BAP1/PRAME in uveal
  melanoma and BIRC5 across TCGA cohorts. The grouped signature and pan-cancer
  examples are separate cases rather than one mixed software-feature section.
  `Future Plans` retains the current scientific boundary before the roadmap.
  Automated compliance now rejects question-form case headings, extra main-text
  tables or any main-figure count other than one; 11/11 focused tests pass and
  the visually inspected OUP preview remains 4/4 pages.
- Completed L-03 with the endpoint-specific TCGA-CDR competing-risk contract:
  status 0 is censored, status 1 is the target event and status 2 is the
  competing death for DSS, DFI and PFI. The imported source contains 2,499/623
  target/competing DSS events, 1,118/351 DFI events and 3,996/839 PFI events.
- Added cumulative-incidence curves, Gray tests, fixed one-, three- and
  five-year CIF estimates with pointwise Aalen confidence intervals and
  at-risk support, plus grouped and continuous Fine--Gray subdistribution
  models. Cause-specific HRs and subdistribution HRs remain visibly labelled as
  different estimands and are never substituted for one another.
- Propagated competing-risk inputs and outputs through public schemas,
  methodology, JSON/HTML audit, PNG/SVG downloads, retained ZIP capsules,
  standalone R reconstruction and the Survival result interface. Square CIF
  plots retain square dimensions without clipping their endpoint/coding
  subtitle; analysis, combined and multiverse pipelines advanced to 6.10, 4.2
  and 1.9.
- Real local smoke analyses completed for BAP1/UVM DSS, CDC20/LIHC DFI and
  MKI67/BRCA PFI. The BAP1/UVM run contained 80 participants, 21 target events
  and two competing deaths; Gray p=0.000457, grouped SHR=0.174 and continuous
  SHR=0.504. Its retained capsule passed CLI integrity verification and an
  offline, read-only, network-disabled standalone rerun, including numeric
  comparison of every competing-risk output.
- Final L-03 validation passed 64 directed backend tests, 19 publication-script
  tests, 11 frontend tests, `git diff --check`, all LaTeX targets and the
  four-page editorial gate. Chromium, Firefox/Gecko and WebKit passed 21/21
  browser checks, including desktop/mobile CIF rendering, Fine--Gray tables and
  CIF download. The main article and supplement now cite and define the Gray
  and Fine--Gray estimands without adding another main-text display item.
- Completed L-05 with detached Ed25519 server receipts for analysis,
  crossed-signature, multiverse and pan-cancer audit reports. A Docker named
  volume persists the private key outside application images, while the HTTPS
  API publishes the stable key identifier, raw public key, issuer and creation
  time.
- Verified a fresh BAP1/UVM DSS analysis from computation through public audit,
  receipt and retained ZIP. The standalone verifier passed all 13 checks against
  the exact audit bytes. Browser contracts in Chromium, Firefox/Gecko and WebKit
  downloaded and parsed the 1,475-byte signed receipt.
- Frozen three attestation acceptance controls: the exact report verifies, an
  altered report is rejected, and an altered report with recomputed SHA-256 and
  canonical payload hash still fails under the unchanged signature. The stated
  trust boundary is server origin under the archived public key, not scientific
  correctness, prespecification, adversarial server compromise or append-only
  publication time.
- Added source, tests, frozen evidence and the standalone verifier to the review
  archive. The archive builder excludes key-volume contents; the verifier
  rejects every `.pem` file, with an explicit private-key regression test. The
  focused archive suite passes 13/13 and a generated 385-entry package verifies
  all 103 submission artifacts.
- Recompiled the review manuscript, supplement and OUP preview after replacing
  the main evidence table with the single integrated vector figure. Automated
  editorial compliance confirms four declarative case headings, `Future Plans`,
  one main figure, no main tables, eight supplementary tables and a 4/4-page
  OUP preview; all four pages were visually inspected.
- Completed L-06 with an opt-in browser-local exploratory run history. Accepted
  compute jobs emit compact lifecycle events without patient records or
  uploaded covariate-row values. Users may retain repeated executions, select
  up to 200 terminal events and export a server-resolved report.
- The report deduplicates exact hypotheses, applies BH and Bonferroni
  separately to continuous Cox, grouped cutpoint and two-signature interaction
  families, and lists multiverse or pan-cancer jobs as managed-family
  references without recounting their internal tests. It contains no
  retained/not-retained verdict and states that the selected post hoc scope
  cannot prove no other runs occurred.
- Session exports include JSON, run/hypothesis CSVs, an execution ledger,
  methodology, audit HTML/JSON, a ZIP and an Ed25519 server receipt. A live
  two-event smoke export yielded five unique hypotheses plus one managed
  pan-cancer reference; the standalone CLI verified its request hash, family
  hash, report identity and source-job count.
- Final L-06 validation passed 138 backend tests, 125 publication-script tests,
  14 CLI tests plus one standalone attestation-verifier test, 15 frontend tests
  and the production frontend build. Chromium, Firefox/Gecko and WebKit passed
  24/24 functional checks, including the signed session export and a 390-pixel
  mobile layout. The manuscript remains one figure, zero main tables and 4/4
  OUP pages; the artifact gate reports 109/109 and a generated 480-entry review
  archive verifies successfully.
- Added explicit `release.commit` and `release.ref` fields to legacy and public
  health responses. Development instances report `development`; production
  operators must set both fields from the exact deployed tag and full commit.
- Strengthened the browser release contract so final evidence requires a clean
  exact-tag checkout, HTTPS and an exact match between the checked-out commit
  and the commit reported independently by every tested browser through the
  public health endpoint.
- Expanded continuous integration to run backend, publication, CLI and frontend
  tests, project-identity checks and a production frontend build. Added a
  manual release-readiness workflow that repeats all three browser engines,
  strict owner metadata, manuscript compliance and archive generation for one
  exact pushed tag.
- Validated both workflows with `actionlint` 1.7.7. The rebuilt local service
  reports its provisional development identity; Chromium, Firefox/Gecko and
  WebKit pass 24/24 checks and record that identity. The normal session-export
  limit was restored to five requests per client-hour after the smoke run.
- Final automated gates pass with 138 backend tests, 125 publication tests, 15
  standalone CLI/attestation tests, 15 frontend tests, one main figure, no main
  tables, eight supplementary tables and a 4/4-page OUP preview. The artifact
  checker reports 109/109 and the 480-entry review archive verifies. R2-24
  remains owner-controlled because the strict metadata check still reports 18
  release and authorship placeholders.
- Audited the checkpoint candidate before publication: local point-in-time
  archives under `release_backups/` are now ignored and remain workstation-only;
  no environment file, private key or runtime data is included in the staged
  source tree.
- Added a narrow Gitleaks policy for one typed Ed25519 annotation and
  bibliography identifiers, pinned Gitleaks 8.24.3 by image digest in both
  workflows, and scanned 15.25 MB of staged content with no secret findings.
- The full pre-submission gate exposed that frozen reproduction bundles were
  being rerun against the current `km_analysis.R`. The verifier now defaults to
  each bundle's checksummed R engine, while explicit overrides remain available
  only as compatibility diagnostics. All three frozen analyses reproduced
  successfully with 125/125 publication tests passing.
- Rebuilt all manuscript targets and the review package after the correction.
  Editorial compliance remains one main vector figure, no main table, eight
  supplementary tables and a 4/4-page OUP preview; 109/109 required artifacts
  and the 480-entry archive verify successfully. R2-24 remains the sole
  owner-controlled closeout item.
- Preserved the validated implementation in checkpoint commit
  `039a91201b363de8fce586f18ff993fe5646762e` and pushed it without rewriting
  history to
  `origin/feature/bioinformatics-readiness-20260721-210041`. This is a recovery
  checkpoint, not the final citable release or publication tag.
- Audited GitHub Actions run `30186431670` after the checkpoint push rather
  than treating local gates as sufficient. Both jobs failed in the clean
  runner: frozen capsules could be silently refreshed from local artifacts,
  while two public-contract tests depended on a locally installed immune-atlas
  screen.
- Made checked-in clean-reproduction capsules immutable by default. Validation
  now follows each capsule's versioned manifest and `renv.lock`, compares R
  package versions semantically, copies the manifest-defined inventory for
  tamper controls and requires explicit `--refresh-capsules` for a maintainer
  update. `--check-only` now validates capsule completeness as well as derived
  evidence.
- Replaced the immune-atlas test dependency with a synthetic temporary fixture
  and recursively strips nested `path`, `paths` and `/app/...` values from the
  public screen payload while preserving `/api/...` downloads. A clean
  worktree with no ignored data or artifacts passes 138/138 backend tests,
  129/129 publication tests and the exact independent capsule command.
- Updated `actions/checkout` and `actions/upload-artifact` to their official
  Node 24 `v7.0.1` commits
  (`3d3c42e5aac5ba805825da76410c181273ba90b1` and
  `043fb46d1a93c77aae656e7c1c64a875d1fc6a0a`) and revalidated both workflows
  with Actionlint 1.7.7.
- The complete local pre-submission gate passes after these corrections:
  138 backend, 129 publication and 15 standalone tests; one main figure, no
  main tables, eight supplementary tables, a 4/4-page OUP preview, 109/109
  artifacts and the 480-entry archive. R2-24 remains owner-controlled with the
  same 18 metadata and release placeholders.
- Published the CI correction as commit
  `ba50e507ac857c36c753bc712345c7c36f4846e8` without rewriting branch
  history. GitHub Actions run `30187314505` completed successfully on the
  hosted runner: `docker-checks` passed backend, publication, standalone,
  identity, frontend-test and production-build gates
  (`https://github.com/lladserLab/tcga_explorer/actions/runs/30187314505/job/89754175751`);
  `Independent clean-capsule reproduction` rebuilt the pinned R environment,
  reran all frozen capsules, verified checksummed results and uploaded the
  independent evidence
  (`https://github.com/lladserLab/tcga_explorer/actions/runs/30187314505/job/89754175720`).
