# External review triage, 2026-07-24

This file preserves the review-time diagnosis. Current implementation status is
authoritatively tracked in
`docs/publication/second_review_implementation_log_2026-07-25.md`; statements
below that describe missing features are historical and must not be used as the
current release checklist.

## Decision

The report supports a major revision. TCGA-TRACE is not submission-ready in its
current statistical framing. The most important issue is not missing interface
polish; it is that the binary retained flag combines dependent tests and treats
a global proportional-hazards diagnostic as an exclusion criterion.

The revision should preserve the audit/provenance foundation while replacing
the retained flag with an evidence profile and a prespecified multiverse.

## Revision status

The first four statistical-reporting and provenance blocks are implemented:

- removed the binary retained/not-retained field from new benchmark outputs,
  Compare Analyses and Paper Examples;
- separated marker-term and global `cox.zph` diagnostics;
- changed PH from an exclusion criterion to an interpretation modifier;
- exposed BH, univariable Cox, adjusted Cox and fixed-horizon RMST as related
  descriptive summaries rather than independent votes;
- labelled grouped HR, confidence interval and RMST outputs after maxstat as
  post-selection.
- made a cutpoint-independent Cox model per +1 expression-score SD the primary
  single-marker and single-signature estimate;
- added stage/grade-adjusted continuous sensitivities, a restricted
  cubic-spline effect profile and a spline-versus-linear nonlinearity test;
- constructed the continuous population before cutpoint-specific exclusions
  and stored a separate population hash in audit schema v3;
- moved KM, grouped Cox and RMST below an explicit cutpoint-sensitivity
  heading in Survival, Compare Analyses and Paper Examples;
- added fitted-parameter and events-per-parameter diagnostics to continuous,
  grouped and interaction Cox models, with caution below 10 and severe caution
  below 5;
- added automatic Firth profile-penalized-likelihood sensitivity for
  low-information, unstable, non-finite or extreme standard estimates while
  preserving the standard Efron-ties Cox result.
- added one exact user-selected complete-case adjustment across continuous,
  grouped and two-signature interaction Cox models using imported age, stage,
  grade, GDC gender and GDC race;
- encoded age per 10 years, retained explicit ordinal stage/grade and
  categorical treatment contrasts, and prevented unavailable requested models
  from being replaced by an auxiliary adjustment.
- added a prespecified endpoint x scoring x cutpoint workflow with separate
  continuous and grouped multiplicity families, a complete family ledger and
  a specification-curve export;
- retained failed and unavailable cells with request, child-analysis and audit
  hashes, without producing a binary evidence verdict.
- calibrated the revised evidence profile with 2,000 observed-cohort
  expression permutations and 2,000 simulations per null, linear PH, delayed
  non-PH and nonlinear scenario, retaining every replicate and Wilson
  interval.

Historical raw benchmark payloads remain immutable records of earlier runs.
The 11 continuous single-gene references and 44 grouped cutpoint sensitivities
have now been regenerated under pipeline v6.2 with an exact prespecified
age-adjusted model. Fixed stage/grade models remain in each raw result as
auxiliary sensitivities. Weighted- and crossed-signature examples were also
regenerated with exact age adjustment under the v6.2/v3.4 pipelines. The ACC
feature benchmark uses 77 evaluable ENSAT-stage records after the stage-data
repair. Multiverse export is implemented under
`prespecified-multiverse-family-v1.1`. Statistical calibration is implemented
under `tcga-trace-statistical-calibration-v1`. Standalone R capsules and
clean-container cross-architecture reproduction are implemented. A ledger
spanning unrelated ad hoc runs remains open.

## Verified critical findings

1. The retained flag requires BH-adjusted log-rank, univariable Cox, adjusted
   Cox and RMST significance, then rejects results when the adjusted model's
   global `cox.zph` test is below 0.05. This is statistically incoherent.
2. Marker-specific PH p-values are already computed, but the robustness view
   uses the global adjusted-model test. PH should modify interpretation, not
   erase an RMST association.
3. Maxstat stores a selection-adjusted p-value, but grouped HR confidence
   intervals and RMST inference remain post-selection.
4. **Implemented for imported generic fields:** single-marker analysis now has
   a flexible continuous primary model, EPV/separation diagnostics, Firth
   sensitivity and one exact user-selected adjustment. Age, stage, grade, GDC
   gender and GDC race are supported. Molecular subtype, purity and arbitrary
   uploaded covariates remain outside the current data model.
5. **Family-level multiverse implemented:** the application freezes and exports
   endpoint x scoring x cutpoint grids, with separate continuous/grouped
   families and every planned cell retained. It does not yet maintain one
   global ledger spanning unrelated ad hoc runs outside a declared family.
6. **Null calibration implemented:** observed-cohort and simulated null
   rejection was 3.2--5.8% for continuous Cox, spline, marker PH and the
   grouped BH family. Naive post-selection maxstat rejected 38.2--39.6%,
   whereas Lau94 rejected 1.8--2.4%. Marker PH detected 88.2% of delayed
   non-PH effects and the spline detected 100% of U-shaped effects. These are
   scenario-specific operating characteristics, not a new decision rule.
7. **Clean reconstruction implemented:** the three exported analysis classes
   pass 65/65 audit checks and 6/6 isolated capsule reruns on native arm64 and
   locally emulated amd64 at absolute tolerance 1e-8. The image is rebuilt from
   an immutable base digest and `renv.lock`; network, application source, TCGA
   matrices and the database are absent. All five record/input/snapshot
   negative controls are detected. A GitHub-hosted Linux/amd64 job independently
   repeats the contract after push.
8. The repository has a documented public API, queue and concurrency controls,
   generated standalone R scripts, `renv.lock` and an immutable reproduction
   base-image digest. An analysis CLI is absent; the OSI license, tagged release
   and archive DOI remain owner-controlled blockers.
9. The comparator matrix is not protocol-backed and omits important
   comparators. It should move out of the main paper unless every cell receives
   dated evidence and an operational definition.

## Findings already addressed or partly outdated

- The publication benchmark defines BH over 44 analyses: 11 scenarios crossed
  with four nonredundant cutpoint rules.
- Endpoint QC is numerically specified as at least 10 linked patients and five
  events.
- The biospecimen priority order is specified in the supplement.
- Cox models use Efron ties in code, although the manuscript must state this.
- RMST tau is already cutpoint-independent: the minimum of five years and the
  eligible cohort's 75th percentile of endpoint time. At least five patients
  must remain at risk per group. Tau and at-risk counts still need to appear in
  every result table and export.
- Main-text cases are described as illustrative/stress-test cases, but generated
  tables still contained the obsolete term "positive control".

## ACC audit

The reviewer was correct that the reported absence of ACC stage data was
implausible. The local source contains ENSAT stage for 77 of 79 patients. The
importer only searched AJCC, paper and FIGO fields.

Corrective work:

- added `ensat_pathologic_stage` to stage normalization and GDC synchronization;
- added `clinical_data.tsv` as a patient-level fallback when `col_data.tsv` is
  incomplete;
- backfilled the live database from 1/79 to 77/79 evaluable stages;
- added a regression test;
- version-invalidated affected analysis caches and included clinical metadata
  timestamps in future cache identity.

The earlier grouped recalculation gave stage-adjusted HR 3.54 (95% CI
1.47-8.51), p=0.0047, 77 complete patients and 27 events. In the regenerated
v6.1 feature benchmark, the continuous primary population contains 79 patients
and 28 events; the stage-adjusted continuous model is evaluable and has
p=0.000302. The frozen publication tables now reflect the repaired data.

## ACC signature interpretation

The omission of DLGAP5 is not itself an error. In the cited validation study,
DLGAP5-PINK1 was the recurrence/malignancy predictor, whereas BUB1B-PINK1 was
the overall-survival predictor. TCGA-TRACE uses an RNA-seq analogue of the
BUB1B-PINK1 expression contrast for OS and must state that distinction
explicitly. Dividing the contrast by two changes scale but not a median split.

## Required redesign

### Statistical core

1. **Implemented:** remove the binary retained/not-retained claim.
2. **Implemented:** make continuous expression the primary analysis:
   linear Cox plus a restricted cubic spline/nonlinearity test and an effect
   profile over expression percentiles.
3. **Implemented:** treat cutpoint analyses as secondary sensitivity views. Show group sizes,
   events and effect estimates rather than an unqualified x/5 score.
4. **Reporting layer implemented:** report marker-specific PH diagnostics. When
   PH is questionable, emphasize fixed-tau RMST and retain the global test as a
   model diagnostic only. A numerical time-varying HR profile remains open.
5. **Implemented:** report fitted parameters and events per parameter; caution
   below 10 and severe caution below 5. Automatically add a `coxphf` Firth
   sensitivity for low-information, unstable, non-finite or extreme standard
   Cox estimates. Keep standard Efron-ties Cox and Firth/Breslow outputs side
   by side rather than silently replacing one with the other.
6. **Implemented for imported fields:** add age and user-selectable clinical
   covariates with complete-case accounting. External or cohort-specific
   molecular covariates remain a documented limitation.
7. Add nested-reselection bootstrap uncertainty for maxstat, or label grouped
   HR/RMST estimates as descriptive and exclude them from confirmatory claims.
8. **Implemented:** calibrate operating properties with null permutation and
   simulations covering null, PH, non-PH and nonlinear effects. Replicate-level
   outputs, seeds, source audit hashes and Monte Carlo intervals are archived.

### Reproducibility core

1. **Implemented:** export a specification curve over endpoint, scoring and
   cutpoint choices, with a declared family and family-level multiplicity.
2. **Implemented within a declared multiverse; broader scope open:** persist
   every planned child run and failure in the parent family ledger. A global
   ledger of unrelated ad hoc browser runs is not implemented.
3. **Implemented:** generate a standalone executable R script, exact engine,
   input, lockfile and pinned Dockerfile with each audit bundle.
4. **Implemented locally across architectures and configured independently in CI:**
   reproduce the frozen suite in a clean pinned container on another machine or
   architecture; report numerical tolerances, exact matches and negative
   snapshot-mutation checks.
5. **Technical pinning implemented; owner actions pending:** R dependencies and
   the reproduction base image are pinned. Publish an OSI license, tagged
   release and version-specific archive DOI.

### Manuscript and benchmark

1. Remove the comparator matrix from the main four-page note or replace it with
   a dated, evidence-backed supplementary protocol.
2. **Application capability implemented:** include endpoints in the declared
   multiverse. The frozen publication benchmark must still document its own
   endpoint family.
3. Replace pooled pan-cancer claims under extreme heterogeneity with cohort
   effects and an explicitly descriptive aggregate, or suppress pooling above a
   prespecified heterogeneity threshold.
4. Expand external concordance beyond one KIRC marker.
5. Correct gene-level/transcript-level terminology and document GDC release,
   STAR-count workflow, annotation/symbol resolution and TCGA-CDR exclusions.
6. Add runtime, memory, concurrency and browser/reproduction results.

## Submission gate

Bioinformatics Application Notes allow up to four formatted pages, approximately
2,600 words or 2,000 words plus one figure. The main text should therefore carry
one claim: TCGA-TRACE makes the analytic multiverse and its consequences
inspectable and reproducible. Calibration, comparator evidence, cohort-specific
sensitivities and complete benchmark tables belong in the supplement.

Null calibration and clean-container reconstruction are now reported. Do not
submit until the release has a reviewer-accessible source, full license,
archived version and a passing independent CI run. The statistical redesign,
ACC repair and family-level multiverse are implemented.

## Primary sources checked

- Bioinformatics author guidelines:
  https://academic.oup.com/bioinformatics/pages/author-guidelines
- Fragoso et al. 2012, BUB1B/DLGAP5/PINK1 validation:
  https://pubmed.ncbi.nlm.nih.gov/22048964/
- Heinze and Schemper 2001, monotone likelihood in Cox regression:
  https://doi.org/10.1111/j.0006-341X.2001.00114.x
- `coxphf` 1.13.4 reference manual:
  https://cran.r-project.org/package=coxphf
