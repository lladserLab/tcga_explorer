# Benchmark and Figure Revision Log

Date: 2026-07-25

## Current Manuscript State

This section supersedes the numerical values and confidence-grade terminology
in the historical July 23 record below.

- The frozen single-gene panel now contains 11 marker--endpoint scenarios and
  four nonredundant two-group rules, for 44 analyses.
- Each scenario has one cutpoint-independent continuous Cox model and one
  restricted cubic-spline nonlinearity test over the full expression-complete
  population. BH is applied separately to the 11 linear and 11 nonlinearity
  tests. The four grouped rules form a scenario-specific Holm family using
  Lau94 for maxstat and log-rank for the other three rules.
- Six continuous linear effects and two nonlinear profiles have family-specific
  BH q-values below 0.05. The nonlinear cases are UVM BAP1 and KIRC CA9.
- Grouped Cox, adjusted Cox and fixed-horizon RMST are related descriptive
  sensitivities; marker-term and global PH diagnostics are reported separately.
- The former retained/not-retained rule has been removed. The benchmark no
  longer combines association summaries and PH diagnostics into a pass/fail
  label.
- The LIHC/CDC20 primary HR per expression SD is 1.65 (95% CI 1.38--1.98)
  and its nonlinearity q-value is 0.697. Its median sensitivity reports RMST
  difference -207 days at tau 1,091 days. The LGG/EMP3 primary HR per SD is
  2.54 (2.15--3.00), while the adjusted marker-term PH p-value is
  7.56e-05.
- Across 44 analyses, 27 have suite-wide BH q<=0.05 and eight have a
  marker-term PH caution. The counts describe different outputs and are not
  interpreted as independent votes.
- The executable audit benchmark covers one single-gene, one weighted-signature
  and one crossed-signature run. It passes 22/22, 23/23 and 20/20 checks,
  respectively, and detects 3/3 targeted record mutations.
- The statistical calibration benchmark contains 2,000 observed-cohort
  permutations and 2,000 simulations per null, linear PH, delayed non-PH and
  nonlinear scenario. Null rejection is 3.2--5.8% for the revised summaries;
  naive maxstat rejects 38.2--39.6% versus 1.8--2.4% with Lau94.
- Pan-cancer pipeline v2.8 retains non-pooled per-SD cohort effects and
  synthesizes only same-endpoint, same-family coefficients per one shared
  input-score unit using REML/HKSJ plus a 95% prediction interval. BIRC5 has
  common-scale HR 1.20 (1.06--1.37), PI 0.64--2.24 and I2=86.1%; CA9 has HR
  1.04 (1.00--1.08), PI 0.93--1.16 and I2=60.7%. Z-score signatures and mixed
  endpoints/families are not pooled.
- The manuscript supplement now contains seven compact tables and no figures.
  Full method-level records remain in machine-readable benchmark files.

The remaining sections document superseded decisions and are preserved as
change history; they must not be used as the source of current manuscript
values or reporting semantics.

## Scope

This record documents the revision of manuscript Tables 2 and 3 and Figure 1,
the July 23 ordinal clinical-adjustment refresh and the July 24 full ImmPort
atlas recomputation. Changes that affect analysis behavior are versioned in
Methods History.

## Pan-Cancer Primary And Ordinal Sensitivity Refresh

- `pancancer-primary-plus-ordinal-sensitivity-cox-audit-v2.1` preserves the
  original continuous within-cohort expression z-score Cox model as the
  primary estimand.
- Parallel sensitivity models use ordinal major stage and histologic grade.
  Availability selects stage+grade, then stage, then grade; effect size and
  p-value never influence that choice.
- BH-FDR and DerSimonian--Laird summaries remain separate for the primary,
  stage+grade, stage-only and grade-only families. Availability-selected mixed
  families are shown cohort by cohort and deliberately not pooled.
- In the real BIRC5 pilot, 18/32 primary cohort effects survive FDR and the
  primary random-effects HR is 1.24 (95% CI 1.12--1.39). Sensitivity is
  evaluable in 24/33 cancers; five selected effects survive FDR, none reverse,
  and the stage-only family attenuates to HR 1.13 (p=0.016).
- In the real CA9 diagnostic, 8/32 primary effects survive FDR and the primary
  random-effects HR is 1.08 (95% CI 1.02--1.14). No selected sensitivity effect
  survives FDR, four directions reverse and the stage-only family attenuates
  to HR 1.06 (p=0.051).
- Public compute-job identity now includes both pipeline and data versions.
  This prevents an old completed job from satisfying a request under a newer
  scientific context while preserving same-version deduplication.
- The earlier 3,118-gene atlas was first preserved unchanged while BIRC5, CA9
  and immune-marker pilots established v2.1 behavior. It was then recomputed as
  the separate versioned screen `immune_os_immport_all_v2_1`; v1 remains
  archived for rollback rather than being overwritten.

## Full ImmPort Atlas v2.1

- The atlas contains 3,118 unique genes from frozen ImmPort JSON/GMT sources,
  153 immune terms and 32 prepared strict-OS cohorts.
- Four prespecified families produce 399,104 attempted rows. The primary
  family completes 96,779 gene-cancer models, with 12,234 global-FDR hits and
  881 gene-level meta-FDR hits.
- Availability-selected ordinal adjustment is evaluable for 72,633 primary
  results. The 12,234 primary FDR hits decompose into 2,212 retained, 7,432
  attenuated, 169 direction-reversed and 2,421 not evaluable results.
- No direction reversal survives FDR in both primary and selected adjusted
  layers. Of 2,379 adjusted FDR hits, 899 have a global PH caution.
- Primary recurrence includes 508 harmful and 73 protective genes appearing as
  FDR hits in at least five cancers. No availability-selected adjusted gene
  reaches the same threshold.
- These counts are descriptive, not causal. Adjustment-family denominators
  differ because of clinical complete cases, and attenuation can reflect
  clinical covariation, reduced information or both.
- Input sources, 32 expression matrices, patient records, cohort checkpoints,
  software versions and final artifacts are pinned by SHA-256. Consecutive
  post-processing runs produce the same audit hash:
  `4d942e93715ec953f0501b13a818d2f19e34f21d851367057924f0af3c2d0252`.
- The compact publication record is stored at
  `docs/publication/benchmark/immune_pancancer_atlas_v2_1/`; full model-level
  files remain versioned application artifacts.

## Ordinal Adjustment And Diagnostic Audit

- Major stage is modeled as `0/I/II/III/IV -> 0/1/2/3/4`; grade is modeled as
  `G1-G5 -> 1-5`. Substages collapse to their major stage and unknown values
  remain missing.
- The selected adjustment uses stage plus grade when evaluable, then stage-only
  or grade-only as explicit fallbacks. Every export records the actual mapping
  and complete-case count.
- Across the 55 refreshed cutpoint analyses, 30 selected adjusted models are
  diagnostically clean, 21 retain a genuine proportional-hazards caution and
  four have no evaluable adjusted model. No selected adjusted model retains a
  convergence caution.
- All 13 results meeting the high-confidence evidence screen have a clean
  selected adjusted model. Cohort exclusions and one-sample-per-patient notes
  remain visible as neutral provenance, not model cautions or failures.

## Table 2 Decision

The formal suite contains 11 marker-endpoint scenarios and 55 cutpoint runs.
The main table shows five cases selected to span different workflow outcomes:

| Case | Median-split result | Five-method reading |
| --- | --- | --- |
| LIHC CDC20 OS | aHR 1.99; RMST -487 days | High confidence in 5/5 |
| LUAD BIRC5 OS | aHR 1.53; RMST -1303 days | High confidence in 2/5 |
| UVM BAP1 DSS | aHR 0.056; RMST +599 days | No high-confidence method; ordinal-stage PH caution; 21 DSS events |
| SKCM TMEM176B OS | aHR 0.35; RMST +2051 days | High confidence in 3/5; biology remains exploratory |
| LGG EMP3 OS | aHR 2.19; RMST -1091 days | No high-confidence method because PH was flagged 5/5 |

The complete 11-case overview and every method-level table remain in the
supplement. The high-confidence label is used only for compact benchmark
reporting; it does not hide or suppress web-application results.

## Table 3 Decision

- ACC uses `(BUB1B - PINK1)/2` on log2(TPM + 1) expression. It is described as
  an RNA-seq analogue of published work, not a replication of its qRT-PCR
  threshold.
- UVM crosses independent median splits of BAP1 and PRAME. The global log-rank
  result and continuous interaction Cox result are reported separately.
- The BIRC5 pan-cancer row reports FDR counts, random-effects HR, I2 and the
  number of significant opposite-direction cohorts in the same row.
- Exact genes and constructions are retained in Supplementary Table S1.
- The previous KIRC hypoxia, SKCM effector x exhaustion and CA9 pan-cancer
  workflows remain as diagnostic counterexamples in Supplementary Table S17.

## Figure 1 Decision

The image-generated background was removed. Figure 1 is now a pure TikZ vector
diagram with a white background and five stages:

1. Versioned RNA, TCGA-CDR endpoints and analysis request.
2. Deterministic patient-level cohort construction.
3. Single-feature, crossed-feature and pan-cancer branches.
4. Cutpoint, RMST, PH, completeness and event-count diagnostics.
5. Plots, selected patient rows, methods, versions, JSON and checksums.

A provenance rail connects the data snapshot hash, request JSON,
selected-patient hash, analysis version and artifact SHA-256. Accessibility text
is stored in `manuscript/bioinformatics_app_note/figures/figure_alt_text.md`.

## Literature Anchors

- CDC20/HCC: `10.1155/2022/9117205`
- BIRC5/LUAD: `10.1155/2019/5451290`
- BAP1/UVM: `10.1136/bjophthalmol-2014-305047`
- BUB1B-PINK1/ACC: `10.1530/EJE-11-0806`
- BAP1-PRAME/UVM: `10.1016/j.modpat.2022.100081`
- BIRC5 pan-cancer: `10.1186/s12885-022-09371-0`
- EMP3/LGG: `10.7150/jca.41123`

## Final Validation

The non-strict pre-submission gate completed on 2026-07-25:

- Backend tests: 80 passed.
- Publication-script tests: 78 passed.
- Frontend production image: built successfully.
- Editorial compliance: 4/4 OUP pages, 7 supplementary tables, no
  supplementary figures and all 17 web examples mapped.
- Data snapshot manifest:
  `f424cf0ce18199ca291b9a396dd89660c654d049cc9bdeff1bbdcf1b8a0ba094`.
- Reproducibility round-trip: patient rows, core results and exported artifact
  hashes matched in 65/65 checks; 3/3 deliberate record mutations were detected.
- Added standalone R capsules with exact patient input, statistical engine,
  `renv.lock` and immutable-base Dockerfile. The three representative analyses
  matched in 6/6 isolated arm64/amd64 reruns at tolerance 1e-8; altered frozen
  input and expression-snapshot controls were detected.
- Statistical calibration: 2,000 observed-cohort permutations and four
  2,000-replicate known-truth scenarios verified against the checksummed
  frozen manifest.
- RMST tau sensitivity: 0.75, 0.90 and 1.00 completed.
- Maxstat post-selection p-values: present for every formal cutpoint case.
- Main PDF SHA-256:
  `53cbea5fcfaddacb7b2932a2bbcfa378354c7985402fc88e1924d9069a4406af`.
- Supplement PDF SHA-256:
  `aacdd65d8758c48ba6e9d9a0e428c9cad9a2ccb19af507889e5d6db8779dd600`.
- OUP preview SHA-256:
  `cb3cb2d6362b1f12e3242d26b6a95c7747dda085c72f35eeb18d159847723269`.
- Submission artifact check: 76/76 available.
- Draft reviewer archive: 287 entries and 286 manifest files verified.
- Full ImmPort atlas audit:
  `4d942e93715ec953f0501b13a818d2f19e34f21d851367057924f0af3c2d0252`.
- Public application health last verified on 2026-07-24: `status=ok`, 33 cohorts at
  `https://apps.cienciavida.org/tcga_explorer/api/v1/health`.
- `git diff --check`: clean.

The strict submission gate remains intentionally blocked by owner-controlled
authorship, affiliation, funding, conflict-of-interest, license, public
repository and archival DOI fields. An author-led review and resolution of the
current OUP AI-assistance policy are also required before upload.
