# Anticipated Reviewer Response Map

Status date: 2026-07-25.

This is a working response map for likely Bioinformatics Application Note
review concerns. It is not a submitted rebuttal. Use it to decide whether the
package is ready for first submission and to prepare a revision if reviewers
raise the issues below.

## Editorial Position

TCGA-TRACE should be presented as a reproducibility-oriented TCGA survival
application, not as a new survival method, a first Kaplan-Meier web tool, a
first two-biomarker survival tool or a pathway-inference method. The strongest
defensible claim is integration: endpoint provenance, one-sample-per-patient
rules, adjusted Cox, PH diagnostics, RMST, cutpoint sensitivity, patient-level
run exports, a prespecified specification-curve workflow and hashable
reproduction records in one Dockerized web workflow.

## Reviewer 1: Survival Methods

| Concern | Current response | Evidence |
| --- | --- | --- |
| Maxstat p-value optimism | Partly addressed. Maxstat is labelled exploratory and records the corrected maximally selected rank statistic p-value from `maxstat::maxstat.test`, LogRank, `pmethod=Lau94`. Grouped HR confidence intervals and RMST inference are explicitly labelled post-selection; nested-reselection uncertainty remains future work. | `backend/scripts/maxstat_cutpoint.R`; `scripts/publication/run_cutpoint_benchmark.py`; `docs/publication/benchmark/README.md`; `manuscript/bioinformatics_app_note/main.tex`. |
| Retention rule combines dependent tests and misuses PH | Addressed and calibrated. The binary rule was removed. BH, Cox, RMST, marker-term PH and global PH are reported separately; PH modifies interpretation and does not discard an association. Across 2,000 observed-cohort permutations and 2,000 simulations per known-truth scenario, null rejection was 3.2--5.8% for the revised summaries, naive maxstat rejected 38.2--39.6% and Lau94 rejected 1.8--2.4%. The delayed-effect PH diagnostic rejected 88.2%, while the nonlinear spline rejected 100% under the U-shaped mechanism. | `scripts/publication/statistical_calibration.R`; `scripts/publication/run_statistical_calibration.py`; `docs/publication/benchmark/statistical_calibration/`; `manuscript/bioinformatics_app_note/tables/statistical_calibration.tex`. |
| RMST tau sensitivity | Addressed. Each two-group run defines tau without group labels as the smaller of five years and the unstratified eligible-cohort 75th percentile, then reports 0.75, 0.90 and 1.00 sensitivity estimates when supported by both groups. | `backend/scripts/km_analysis.R`; `manuscript/bioinformatics_app_note/main.tex`. |
| Sparse events, separation and implausibly extreme Cox estimates | Addressed diagnostically. Every grouped, continuous and interaction Cox fit reports fitted parameters and events per parameter, with cautions below 10 and severe cautions below 5. A Firth profile-penalized-likelihood sensitivity fit is added automatically for low information, failed/non-finite standard fits or extreme marker estimates; it is displayed beside, and never substituted for, the standard Efron-ties Cox model. UVM BAP1 demonstrates recovery from non-finite standard grouped fits, while the adjusted BAP1--PRAME interaction records EPV 5 and a finite Firth sensitivity estimate. | `backend/scripts/cox_diagnostics.R`; `backend/scripts/km_analysis.R`; `docs/publication/benchmark/uvm_bap1_dss_cutpoint_benchmark/`; `docs/publication/benchmark/feature_benchmarks/two_signature.raw.json`; `manuscript/bioinformatics_app_note/main.tex`. |
| Pan-cancer Cox interpretation | Addressed. Per-SD cohort effects are retained descriptively and are never pooled. Same-endpoint, same-family coefficients are recovered per +1 shared input-score unit and synthesized by REML/HKSJ with a prediction interval. BIRC5 has HR 1.20 (1.06--1.37), I2=86.1% and PI 0.64--2.24; CA9 remains a small-effect diagnostic. Mixed endpoints/families and cohort-standardized z-score signatures are not pooled. | `backend/app/pancancer.py`; `docs/publication/benchmark/feature_benchmarks/feature_benchmark_summary.md`; `docs/publication/benchmark/feature_benchmarks/feature_diagnostic_summary.md`; `manuscript/bioinformatics_app_note/main.tex`. |

## Reviewer 2: Software and Reproducibility

| Concern | Current response | Evidence |
| --- | --- | --- |
| Software not available during review | The public source location is fixed at `https://github.com/lladserLab/tcga_explorer`, with Docker, CI, tests, reviewer quickstart and artifact checks. The final license, tagged release and version-specific Zenodo DOI remain pre-submission owner actions. | `REVIEWER_QUICKSTART.md`; `.github/workflows/ci.yml`; `manuscript/bioinformatics_app_note/submission/final_submission_decisions.md`; `scripts/publication/check_submission_metadata.py`. |
| Reproducibility hash and origin are not demonstrated | Addressed in two layers. Three frozen analyses and six network-disabled arm64/amd64 reruns demonstrate reconstruction under quantity-aware tolerances; internal check counts are dependent coverage checks, not independent replications. Boundary tests distinguish run-hash, artifact-checksum and intentionally unbound fields. Audit schema v4 additionally emits a detached Ed25519 receipt. A frozen BAP1/UVM DSS report verified against the archived public key; altering the report failed, and recomputing its SHA-256 plus canonical payload SHA-256 still failed the unchanged signature. This authenticates exact report bytes under a trusted key but does not claim scientific correctness, prespecification or append-only time. Hosted Linux/amd64 CI repeats the reconstruction contract independently after push. | `docs/publication/benchmark/reproducibility_benchmark/summary.md`; `docs/publication/benchmark/clean_container_reproduction/summary.md`; `docs/publication/benchmark/server_attestation/summary.md`; `scripts/publication/run_server_attestation_benchmark.py`; `.github/workflows/ci.yml`. |
| Provenance does not prevent endpoint/cutpoint/scoring cherry-picking | Addressed at two scopes without claiming prespecification. The Multiverse workflow freezes endpoint x scoring x cutpoint choices, separates continuous and grouped multiplicity families, and retains every planned cell and failure. An optional browser-local history records selected ad hoc run events and exports unique continuous, grouped and interaction families with BH and Bonferroni correction. It is disabled by default, excludes patient rows, preserves repeated executions, references managed multiverse and pan-cancer families without recounting them, and states explicitly that the selected post hoc export cannot prove that no other runs occurred. | `backend/app/multiverse.py`; `backend/app/session_history.py`; `backend/tests/test_multiverse.py`; `backend/tests/test_session_history.py`; `frontend/src/sessionHistory.js`; `manuscript/bioinformatics_app_note/supplementary.tex`. |
| TCGA data versioning is not pinned | Partly addressed. The final benchmark matrices are pinned by count-matrix SHA-256 hashes for 33 cohorts plus TCGA-CDR checksum. The GDC RNA sync manifest is still recorded as missing in this checkout and should be archived if the updater regenerates the final snapshot. | `docs/publication/benchmark/data_snapshot_manifest.json`; `docs/publication/benchmark/README.md`. |
| Missing dominant prior art | Addressed. The comparator matrix includes GEPIA2, cSurvival, DoSurvive, PESSA, UALCAN, KM Plotter, UCSC Xena, cBioPortal, TIMER2.0, SurvExpress, TCGAbiolinks and TCGAplot. | `docs/publication/comparator_matrix.md`; `manuscript/bioinformatics_app_note/tables/comparator_matrix.tex`; `manuscript/bioinformatics_app_note/supplementary.tex`. |
| Tests and CI not described | Addressed. Backend tests, publication-script syntax/tests, frontend Docker build and an independent clean-capsule reproduction job are tracked. The local gate also verifies manifests, recorded and clean round-trips, RMST tau, maxstat p-values, PDFs and submission artifacts. | `scripts/publication/pre_submission_check.sh`; `.github/workflows/ci.yml`; `REVIEWER_QUICKSTART.md`. |

## Reviewer 3: Cancer Genomics and Applied Use

| Concern | Current response | Evidence |
| --- | --- | --- |
| Novelty is incremental | Addressed by narrowing the claim. The manuscript does not claim a new method or first survival portal; it argues for an integrated, traceable workflow with model QC and exported run records. | `manuscript/bioinformatics_app_note/main.tex`; `docs/BIOINFORMATICS_PUBLICATION_READINESS.md`. |
| Concordance with existing tools is missing | Partly addressed. One KM Plotter KIRC CA9 OS comparison is recorded as directional concordance, not exact replication. Additional GEPIA2/KM Plotter/cSurvival cases would strengthen but are not required for the current minimum package. | `docs/publication/external_concordance_kmplotter_ca9_kirc.md`; `docs/publication/concordance_validation_plan.md`. |
| TCGA-SKCM sample composition can alter immune-marker survival analyses | Addressed. The median-split PDCD1 and TMEM176B BH, adjusted-Cox and diagnostic profiles differ across all-eligible, primary-only and metastatic-only sample rules. The supplement treats sample composition as a sensitivity setting for both SKCM immune examples. | `docs/publication/benchmark/skcm_sample_rule_sensitivity/README.md`; `docs/publication/benchmark/skcm_tmem176b_sample_rule_sensitivity/README.md`; `manuscript/bioinformatics_app_note/tables/skcm_sample_rule_sensitivity.tex`; `manuscript/bioinformatics_app_note/tables/skcm_tmem176b_sample_rule_sensitivity.tex`; `manuscript/bioinformatics_app_note/supplementary.tex`. |
| Signature scoring is weaker than ssGSEA | Addressed as limitation. The manuscript explicitly states that simple z-score and weighted scores are transparent but not a replacement for ssGSEA when pathway activity is the biological question. | `manuscript/bioinformatics_app_note/main.tex`. |
| GTEx/GEO validation absent | Addressed as limitation, not solved. The manuscript states that TCGA-TRACE currently covers bulk TCGA only and external validation remains required. | `manuscript/bioinformatics_app_note/main.tex`. |

## Editor-Level Minimums

| Requirement | Status before upload |
| --- | --- |
| Public or reviewer-accessible source | Owner decision still required. |
| OSI-compatible software license | Owner decision still required. |
| Dockerized review path | Prepared and tested. |
| Stable archive DOI or release URL | Owner decision still required. |
| Data snapshot manifest | Prepared with count-matrix hashes and stable manifest hash. |
| Round-trip reproducibility check | Recorded-environment and clean-container checks pass locally; independent hosted CI confirmation is pending push. |
| External concordance record | Prepared for KM Plotter KIRC CA9 OS, directional only. |
| Placeholder-free manuscript metadata | Not ready until authors, affiliation, email, funding and conflict-of-interest text are supplied. |

## Do Not Overclaim

- Do not describe the KM Plotter comparison as an exact replication.
- Do not present TCGA-SKCM PDCD1 or TMEM176B as general biological discoveries
  independent of sample composition.
- Do not combine BH, Cox, RMST and PH diagnostics into an informal validation
  score or claim that a PH caution negates an association.
- Do not present z-score or weighted signatures as a pathway-inference replacement
  for ssGSEA.
- Do not say the software is publicly available until the repository, license
  and archive URL are actually supplied.
