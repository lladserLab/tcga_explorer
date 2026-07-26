# Bioinformatics Publication Readiness

This document defines the work needed to position TCGA-TRACE as a
Bioinformatics Application Note rather than a general software note.

## Proposed Positioning

TCGA-TRACE is a transparent TCGA survival web application for endpoint-aware,
clinically adjusted and signature-capable transcriptomic survival analysis.

The contribution is not a new Kaplan-Meier implementation. The contribution is
the integration of:

- TCGA-CDR OS, DSS, DFI and PFI endpoint handling with fallback OS metadata;
- one RNA-seq sample per TCGA participant using an explicit biospecimen rule;
- gene and custom signature scoring, including weighted signatures;
- two-signature combined stratification and continuous interaction Cox models
  as supported workflows, not as the primary novelty claim;
- univariable and ordinal stage/grade-adjusted Cox models;
- proportional-hazards QC from `cox.zph` where estimable;
- RMST reporting for two-group survival comparisons;
- cutpoint sensitivity summaries across dichotomization rules, including RMST;
- a prespecified endpoint-by-scoring-by-cutpoint workflow with separate
  continuous/grouped multiplicity families and a complete family ledger;
- continuous pan-cancer Cox scans with BH-FDR and meta-analysis;
- downloadable raw records, methods text, structured run reports and local
  reproducibility-bundle verification;
- a standalone R capsule containing exact patient input, statistical engine,
  `renv.lock` and an immutable-base Dockerfile.

The primary claim should be executable reconstruction plus model-quality
reporting: every survival run can emit exact patient and expression-component
records, GDC identifiers, SHA-256 hashes, software versions,
endpoint/sample-selection details, Cox PH diagnostics and cutpoint/RMST
sensitivity outputs. A specification family additionally binds every planned
cell, child-analysis ID and child audit hash without treating unrelated ad hoc
runs as prespecified. Three saved bundles now reconstruct scores and reproduce
the frozen R results for single-gene, weighted-signature and crossed-signature
analyses. The two-biomarker interaction workflow must be presented carefully because
cSurvival already implements joint analysis with two genomic predictors and
optimal cutoffs for two continuous predictors.

## Comparator Matrix

| Tool | Main scope | TCGA-CDR endpoints | Adjusted Cox | Custom signatures | Two-predictor survival | RMST | PH QC in UI | Cutpoint sensitivity | Run export |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| GEPIA2 | TCGA/GTEx expression and survival | Partial/unclear in UI | No focused adjusted workflow | Yes | Limited | No | No | Limited | No |
| UALCAN | TCGA/CPTAC expression, subgroups, survival | Partial/unclear in UI | No focused adjusted workflow | Limited | Limited | No | No | Limited | No |
| OncoLnc | TCGA gene survival | No | No | No | No | No | No | Limited/precomputed | Limited |
| KM Plotter | Survival biomarker screening | Dataset-dependent | Limited | Some gene-set modes | Limited | No | No | Several cutpoint choices | Limited |
| UCSC Xena | General multi-omics browser | Dataset-dependent | Manual | Manual | Manual | No | Manual | Manual | Limited |
| cBioPortal | Cancer genomics exploration | Dataset-dependent | Limited | Alteration groups | Alteration/group comparisons | No | No focused workflow | Limited | Limited |
| cSurvival | Biomarker interactions in cancer outcomes | Dataset-dependent | Yes, selected workflows | Yes, gene and gene-set level | Yes, including two-predictor grouped survival, interaction analysis and optimal two-continuous-predictor cutoffs | No focused output | Not emphasized | Yes for optimal predictor cutoffs | Source/data downloadable, no per-run hash bundle |
| DoSurvive | Prognostic biomarker database/web tool | Dataset-dependent | Yes, including multivariable Cox workflows | Yes; mRNA, miRNA, lncRNA, protein and methylation | Yes for single or combined biomarkers | No focused output | Not emphasized | Selected workflows | Downloadable outputs, no per-run hash bundle |
| PESSA | Pathway enrichment score survival | Dataset-dependent | Cox support for dichotomous and continuous ssGSEA scores | Yes, MSigDB gene sets scored by ssGSEA | No primary interaction workflow | No focused output reported | Yes, `cox.zph` for continuous Cox | Median and optimal cutoffs | Downloadable outputs; no comparable per-run reconstruction bundle reported |
| TCGAbiolinks | R package for TCGA workflows | Yes if configured | Programmable | Programmable | Programmable | Programmable | Programmable | Programmable | Script-level |
| TCGAplot | R package for pan-cancer analysis | Dataset-dependent | Programmable | Yes | No focused UI | No focused output | Programmable | Programmable | Script-level |
| TCGA-TRACE | TCGA survival webapp | Yes, endpoint QC exposed | Yes | Yes, including z-score and weighted scores | Yes, but not unique versus cSurvival/DoSurvive | Yes for two-group analyses | Yes | Yes | Yes, JSON/HTML with hashes and exact patient records |

Sources used to frame the comparison:

- GEPIA2: https://academic.oup.com/nar/article/47/W1/W556/5494747
- cSurvival: https://academic.oup.com/bib/article/23/3/bbac090/6562683
- DoSurvive: https://pmc.ncbi.nlm.nih.gov/articles/PMC10440714/
- UALCAN: https://ualcan.path.uab.edu/
- OncoLnc: https://doaj.org/article/9733114d14464feebda2a410f09e148f
- KM Plotter: https://kmplot.com/
- UCSC Xena: https://xena.ucsc.edu/kaplan-survival-analysis
- cBioPortal: https://docs.cbioportal.org/user-guide/faq/
- PESSA: https://journals.plos.org/ploscompbiol/article?id=10.1371%2Fjournal.pcbi.1012024
- TCGAbiolinks: https://academic.oup.com/nar/article/44/8/e71/2465925
- TCGAplot: https://link.springer.com/article/10.1186/s12859-023-05615-3
- TCGA-CDR: https://gdc.cancer.gov/about-data/publications/PanCan-Clinical-2018
- RMST biomarker analysis: https://www.oncotarget.com/article/6121/text/
- Cutpoint methods comparison: https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0338425
- Bioinformatics author guidelines: https://academic.oup.com/bioinformatics/pages/author-guidelines

The source-by-source evidence register is maintained in
`docs/publication/comparator_matrix.md`.

## Benchmark Protocol

Run each case in TCGA-TRACE and, where possible, in at least three comparator
tools. Record patient counts, event counts, endpoint definition, cutoff,
hazard ratio, confidence interval, log-rank p-value, Cox p-value, downloads and
whether the exact analysis can be reproduced.

Minimum benchmark cases:

| Case | Cohort | Marker | Endpoint | Purpose |
| --- | --- | --- | --- | --- |
| 1 | TCGA-KIRC | CA9 | OS | Current canary and kidney cancer marker workflow |
| 2 | TCGA-BRCA | MKI67 | OS/PFI | Proliferation marker with common clinical context |
| 3 | TCGA-SKCM | PDCD1 | OS | Immune checkpoint marker |
| 4 | TCGA-SKCM | TMEM176B | OS | Literature-prioritized exploratory immune-regulatory marker |
| 5 | TCGA-LUAD | CD274 | OS/PFI | Checkpoint ligand and endpoint sensitivity |
| 6 | TCGA-KIRC | hypoxia signature | OS | Multi-gene signature scoring |
| 7 | TCGA-SKCM | effector signature x exhaustion signature | OS | Two-signature stratification |
| 8 | Pan-cancer | BIRC5 and CA9 | OS | Primary continuous Cox/FDR plus ordinal clinical sensitivity |
| 9 | Low-event cohort | any plausible marker | DSS/DFI | Endpoint QC and not-reached median behavior |

For the frozen publication sensitivity panel, each single-marker case runs four
nonredundant two-group rules: maxstat, median, upper quartile and outer
quartiles. Custom percentile remains user-configurable and therefore lacks one
prespecified publication value; tertiles remain a three-group method. The
interface and benchmark summaries show suite-wide BH q, univariable and adjusted
Cox, fixed-horizon RMST, marker-term PH and global PH separately. They are not
combined into a retention score because the association summaries are
correlated and PH is an assumption diagnostic. Maxstat remains exploratory: its
selection-adjusted rank-test p-value is shown when available, while grouped HR,
confidence interval and RMST outputs remain post-selection.

The single-gene panel has been run through
`scripts/publication/run_single_gene_benchmark_suite.py`. The aggregate table is
stored at `docs/publication/benchmark/single_gene_benchmark_overview.md`. The
suite now contains 11 scenarios. The main manuscript reports literature-anchored
LIHC/CDC20, LUAD/BIRC5, UVM/BAP1, SKCM/TMEM176B and LGG/EMP3 examples; the full
supplementary overview preserves all earlier positive, null and discordant
cases. The descriptive rule is a benchmark reporting convention, not an
application gate.

The feature workflows have been run through
`scripts/publication/run_feature_benchmarks.py`. The aggregate table is stored
at `docs/publication/benchmark/feature_benchmarks/feature_benchmark_summary.md`.
The main examples are the ACC BUB1B-PINK1 weighted contrast, UVM BAP1 x PRAME
four-group workflow and a BIRC5 pan-cancer primary Cox/FDR scan with parallel
ordinal clinical sensitivity. The UVM global
separation is reported separately from its nonsignificant interaction, and the
BIRC5 estimate is reported with high heterogeneity and opposite-direction
cohorts. Its adjustment families are summarized separately and mixed selected
families are not pooled. Earlier KIRC hypoxia and SKCM effector x exhaustion
examples, plus the CA9 attenuation and direction-reversal result, remain
supplementary diagnostics. Treat all as workflow benchmarks, not independent
biological validation.

The complete ImmPort atlas was subsequently recomputed as
`immune_os_immport_all_v2_1` using the same final model contract. It contains
3,118 genes across 32 strict-OS cohorts and preserves primary, stage+grade,
stage and grade FDR/meta-FDR families separately. The compact publication
record at `docs/publication/benchmark/immune_pancancer_atlas_v2_1/` includes
the exact primary-to-selected-adjustment decomposition and audit hash; full
model rows remain local versioned artifacts. Raw hit counts across adjusted
families must not be ranked as if denominators were equal.

For the two-signature case, report both the crossed KM groups and the continuous
Cox interaction term `signature_A_z:signature_B_z`, including adjusted models
when ordinal major-stage and histologic-grade scores have sufficient
complete-case data. Stage 0/I/II/III/IV map to 0/1/2/3/4 with substages
collapsed, G1--G5 map to 1--5, and unrecognized values remain missing.

## Submission Package Status

Generated files:

- main manuscript: `manuscript/bioinformatics_app_note/main.tex`;
- vector source and alt text for Figure 1:
  `manuscript/bioinformatics_app_note/figures/graphical_abstract.tex` and
  `manuscript/bioinformatics_app_note/figures/figure_alt_text.md`;
- optional reviewer-facing interface screenshots:
  `manuscript/bioinformatics_app_note/figures/tcga_trace_ui_analysis.png` and
  `manuscript/bioinformatics_app_note/figures/tcga_trace_ui_multiverse.png`;
- supplementary material:
  `manuscript/bioinformatics_app_note/supplementary.tex`;
- Bioinformatics readiness checklist:
  `manuscript/bioinformatics_app_note/submission/submission_readiness_checklist.md`;
- cover letter draft:
  `manuscript/bioinformatics_app_note/submission/cover_letter_draft.md`.
- reviewer reproduction guide:
  `manuscript/bioinformatics_app_note/submission/reviewer_reproduction_guide.md`;
- reviewer interface walkthrough:
  `manuscript/bioinformatics_app_note/submission/reviewer_walkthrough.md`;
- root reviewer quickstart:
  `REVIEWER_QUICKSTART.md`;
- prepared public-web and Docker-fallback reviewer access statement:
  `manuscript/bioinformatics_app_note/submission/reviewer_access_statement.md`;
- public web application verified on 2026-07-24:
  `https://apps.cienciavida.org/tcga_explorer/`;
- prepared data availability statement:
  `manuscript/bioinformatics_app_note/submission/data_availability_statement.md`;
- release and license checklist:
  `manuscript/bioinformatics_app_note/submission/release_and_license_checklist.md`;
- final submission decision tracker:
  `manuscript/bioinformatics_app_note/submission/final_submission_decisions.md`;
- external concordance validation plan:
  `docs/publication/concordance_validation_plan.md`;
- external KM Plotter concordance record:
  `docs/publication/external_concordance_kmplotter_ca9_kirc.md`;
- user-facing Help & Methods page in the app and repository `CHANGELOG.md` with
  v0.1.0 functional baseline plus methodological version history.
- CI workflow:
  `.github/workflows/ci.yml`;
- local data snapshot manifest:
  `docs/publication/benchmark/data_snapshot_manifest.json`;
- compact full ImmPort atlas record and generated table:
  `docs/publication/benchmark/immune_pancancer_atlas_v2_1/` and
  `manuscript/bioinformatics_app_note/tables/immune_pancancer_atlas_model_summary.tex`;
- ImmPort atlas publication exporter:
  `scripts/publication/export_immune_atlas_benchmark.py`;
- three-class executable audit-reconstruction benchmark:
  `docs/publication/benchmark/reproducibility_benchmark/summary.md`;
- SKCM sample-type sensitivity record:
  `docs/publication/benchmark/skcm_sample_rule_sensitivity/README.md`;
- SKCM TMEM176B sample-type sensitivity record:
  `docs/publication/benchmark/skcm_tmem176b_sample_rule_sensitivity/README.md`;
- reproducibility-bundle verifier:
  `scripts/publication/verify_reproducibility_bundle.py`;
- compact reviewer/source archive builder:
  `scripts/publication/build_submission_archive.py`;
- reviewer screenshot capture script:
  `scripts/publication/capture_reviewer_screenshots.py`;
- compact reviewer/source archive verifier:
  `scripts/publication/verify_submission_archive.py`;
- owner metadata application path:
  `scripts/publication/apply_submission_metadata.py` with
  `manuscript/bioinformatics_app_note/submission/owner_metadata.template.json`;
- owner-selected permissive license text helper:
  `scripts/publication/write_license_template.py`;
- final owner-metadata, strict-gate and archive handoff runner:
  `scripts/publication/finalize_submission_package.py`;
- submission artifact and owner metadata checkers:
  `scripts/publication/check_submission_artifacts.py`,
  `scripts/publication/check_submission_metadata.py` and
  `scripts/publication/pre_submission_check.sh --strict-owner-metadata`;
- SKCM primary-versus-metastatic sample-rule sensitivity wrapper:
  `scripts/publication/run_skcm_sample_rule_sensitivity.py`.

Current local reproducibility evidence:

- `docs/publication/benchmark/data_snapshot_manifest.json` was generated with
  `--hash-count-matrices` and records 33 cohorts with zero missing
  count-matrix hashes; this pins the final benchmark matrices by SHA-256, while
  a GDC RNA sync manifest should also be archived if the final snapshot is
  regenerated by the updater;
- the single-gene, weighted-signature and crossed-signature bundles pass 22/22,
  23/23 and 20/20 checks, respectively, including score reconstruction and
  deterministic R re-execution;
- the same three standalone capsules pass 6/6 clean-container reruns across
  native arm64 and locally emulated amd64 with zero core-result differences at
  absolute tolerance 1e-8. The runtime has no network, application source, TCGA
  matrix or database; altered patient input and expression-snapshot hashes are
  detected. The independent Linux/amd64 CI job is configured and must pass
  after the final branch is pushed;
- the full ImmPort atlas pins 32 expression matrices and reproduces audit hash
  `4d942e93715ec953f0501b13a818d2f19e34f21d851367057924f0af3c2d0252`
  in consecutive post-processing runs;
- the executable audit record is stored in
  `docs/publication/benchmark/reproducibility_benchmark/summary.md`.
- the statistical calibration record stores 10,000 replicate-level analyses,
  source audit hashes and Wilson intervals; observed and simulated null
  rejection is 3.2--5.8% for the revised summaries, while naive maxstat
  rejection is 38.2--39.6% versus 1.8--2.4% with Lau94;
- the SKCM sample-type sensitivity records show that median-split immune-marker
  BH, adjusted-Cox and diagnostic profiles can change across all-eligible,
  primary-only and metastatic-only sample rules for PDCD1 and TMEM176B.
- KM Plotter CA9/KIRC OS directional concordance is recorded in
  `docs/publication/external_concordance_kmplotter_ca9_kirc.md`.

External blockers before submission:

- author list, affiliations and corresponding-author email;
- funding and conflict-of-interest statements;
- complete final software license text as a top-level `LICENSE`/`COPYING` file;
- reviewer-accessible or public repository URL;
- archival DOI or stable release URL.
- CI run confirmation after the final reviewer-accessible repository is pushed.
- author-led substantive review and resolution of the OUP disclosure
  requirement for AI-assisted drafting before submission.

## Go/No-Go Criteria

Proceed toward Bioinformatics if all are true:

- public or reviewer-accessible repository with complete license text, issue tracker,
  installation docs and Docker;
- stable web demo available without mandatory registration, with Docker
  reproduction instructions stated clearly;
- structured run report export available for every completed survival analysis;
- at least one saved analysis bundle passes local round-trip verification;
- TCGA/CDR data snapshot is pinned by manifest and archived with the submitted
  release;
- at least one external concordance case is recorded with accessed date,
  endpoint, cutoff and available summary statistics;
- at least three comparator-visible differentiators remain after benchmark;
- KM Plotter, cSurvival and PESSA are acknowledged directly in the comparator
  narrative;
- RMST is available for two-group analyses and appears in JSON, run reports
  and the UI;
- benchmark scripts/tables are reproducible from a clean checkout;
- manuscript can state the contribution without relying on a single biological
  result.

Fallback to JOSS or SoftwareX if the benchmark shows that the main novelty is
software integration and reproducibility rather than a clearly distinct
bioinformatics analysis capability.
