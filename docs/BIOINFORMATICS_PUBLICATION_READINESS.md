# Bioinformatics Publication Readiness

This document defines the work needed to position TCGA Explorer as a
Bioinformatics Application Note rather than a general software note.

## Proposed Positioning

TCGA Explorer is an auditable TCGA survival web application for endpoint-aware,
clinically adjusted, robust and signature-capable transcriptomic survival
analysis.

The contribution is not a new Kaplan-Meier implementation. The contribution is
the integration of:

- TCGA-CDR OS, DSS, DFI and PFI endpoint handling with fallback OS metadata;
- one RNA-seq sample per TCGA participant using an explicit biospecimen rule;
- gene and custom signature scoring, including weighted signatures;
- two-signature combined stratification and continuous interaction Cox models
  as supported workflows, not as the primary novelty claim;
- univariable and stage/grade-adjusted Cox models;
- proportional-hazards QC from `cox.zph` where estimable;
- RMST reporting for two-group survival comparisons;
- cutpoint robustness summaries across dichotomization rules, including RMST;
- continuous pan-cancer Cox scans with BH-FDR and meta-analysis;
- downloadable raw records, methods text and audit reports.

The primary novelty claim should be auditability plus model-quality reporting:
every survival run can emit an exact patient-level analysis bundle, SHA-256
hashes, software versions, endpoint/sample-selection details, Cox PH diagnostics
and cutpoint/RMST robustness outputs. Two-biomarker interaction must be
presented carefully because cSurvival already implements joint analysis with two
genomic predictors and optimal cutoffs for two continuous predictors.

## Comparator Matrix

| Tool | Main scope | TCGA-CDR endpoints | Adjusted Cox | Custom signatures | Two-predictor survival | RMST | PH QC in UI | Cutpoint robustness | Audit export |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| GEPIA2 | TCGA/GTEx expression and survival | Partial/unclear in UI | No focused adjusted workflow | Yes | Limited | No | No | Limited | No |
| UALCAN | TCGA/CPTAC expression, subgroups, survival | Partial/unclear in UI | No focused adjusted workflow | Limited | Limited | No | No | Limited | No |
| OncoLnc | TCGA gene survival | No | No | No | No | No | No | Limited/precomputed | Limited |
| KM Plotter | Survival biomarker screening | Dataset-dependent | Limited | Some gene-set modes | Limited | No | No | Several cutpoint choices | Limited |
| UCSC Xena | General multi-omics browser | Dataset-dependent | Manual | Manual | Manual | No | Manual | Manual | Limited |
| cBioPortal | Cancer genomics exploration | Dataset-dependent | Limited | Alteration groups | Alteration/group comparisons | No | No focused workflow | Limited | Limited |
| cSurvival | Biomarker interactions in cancer outcomes | Dataset-dependent | Yes, selected workflows | Yes, gene and gene-set level | Yes, including optimal two-continuous-predictor cutoffs | No focused output | Not emphasized | Yes for optimal predictor cutoffs | Source/data downloadable, no per-run hash bundle |
| DoSurvive | Prognostic biomarker database/web tool | Dataset-dependent | Yes, including multivariable Cox workflows | Yes; mRNA, miRNA, lncRNA, protein and methylation | Yes for single or combined biomarkers | No focused output | Not emphasized | Selected workflows | Downloadable outputs, no per-run hash bundle |
| PESSA | Pathway enrichment score survival | Dataset-dependent | Cox support for dichotomous and continuous ssGSEA scores | Yes, MSigDB gene sets scored by ssGSEA | No primary interaction workflow | No focused output | Not emphasized | Median and optimal cutoffs | Downloadable outputs, no per-run hash bundle |
| TCGAbiolinks | R package for TCGA workflows | Yes if configured | Programmable | Programmable | Programmable | Programmable | Programmable | Programmable | Script-level |
| TCGAplot | R package for pan-cancer analysis | Dataset-dependent | Programmable | Yes | No focused UI | No focused output | Programmable | Programmable | Script-level |
| TCGA Explorer | TCGA survival webapp | Yes, endpoint QC exposed | Yes | Yes, including weighted z-scores | Yes, but not unique versus cSurvival/DoSurvive | Yes for two-group analyses | Yes | Yes | Yes, JSON/HTML with hashes and exact patient records |

Sources used to frame the comparison:

- GEPIA2: https://academic.oup.com/nar/article/47/W1/W556/5494747
- cSurvival: https://academic.oup.com/bib/article/23/3/bbac090/6562683
- DoSurvive: https://pmc.ncbi.nlm.nih.gov/articles/PMC10440714/
- OncoLnc: https://doaj.org/article/9733114d14464feebda2a410f09e148f
- PESSA: https://journals.plos.org/ploscompbiol/article?id=10.1371%2Fjournal.pcbi.1012024
- TCGAbiolinks: https://academic.oup.com/nar/article/44/8/e71/2465925
- TCGAplot: https://link.springer.com/article/10.1186/s12859-023-05615-3
- TCGA-CDR: https://gdc.cancer.gov/about-data/publications/PanCan-Clinical-2018
- RMST biomarker analysis: https://www.oncotarget.com/article/6121/text/
- Cutpoint methods comparison: https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0338425
- Bioinformatics author guidelines: https://academic.oup.com/bioinformatics/pages/author-guidelines

## Benchmark Protocol

Run each case in TCGA Explorer and, where possible, in at least three comparator
tools. Record patient counts, event counts, endpoint definition, cutoff,
hazard ratio, confidence interval, log-rank p-value, Cox p-value, downloads and
whether the exact analysis can be reproduced.

Minimum benchmark cases:

| Case | Cohort | Marker | Endpoint | Purpose |
| --- | --- | --- | --- | --- |
| 1 | TCGA-KIRC | CA9 | OS | Current canary and kidney cancer marker workflow |
| 2 | TCGA-BRCA | MKI67 | OS/PFI | Proliferation marker with common clinical context |
| 3 | TCGA-SKCM | PDCD1 | OS | Immune checkpoint marker |
| 4 | TCGA-LUAD | CD274 | OS/PFI | Checkpoint ligand and endpoint sensitivity |
| 5 | TCGA-KIRC | hypoxia signature | OS | Multi-gene signature scoring |
| 6 | TCGA-SKCM | effector signature x exhaustion signature | OS | Two-signature stratification |
| 7 | Pan-cancer | CA9 | OS | Continuous pan-cancer Cox/FDR workflow |
| 8 | Low-event cohort | any plausible marker | DSS/DFI | Endpoint QC and not-reached median behavior |

For cutpoint robustness, each single-marker case should run the dichotomization
panel: maxstat, median, upper quartile, outer quartiles and the selected custom
percentile. Tertiles remain available as a three-group stratification method but
are excluded from the dichotomization robustness rule. A cutpoint is considered
to survive downstream only when the BH-adjusted log-rank p-value, univariable
Cox p-value, adjusted Cox p-value and RMST p-value are all <= 0.05, with no
flagged adjusted proportional-hazards test.

Cases 1-4 have been run through
`scripts/publication/run_single_gene_benchmark_suite.py`. The aggregate table is
stored at `docs/publication/benchmark/single_gene_benchmark_overview.md`. Across
six single-gene endpoint scenarios, only BRCA/MKI67-PFI and SKCM/PDCD1-OS have
at least one cutpoint that survives the full downstream rule. CA9/KIRC-OS,
BRCA/MKI67-OS, LUAD/CD274-OS and LUAD/CD274-PFI should be presented as
robustness/audit demonstrations rather than positive biomarker claims.

Cases 5-7 have been run through
`scripts/publication/run_feature_benchmarks.py`. The aggregate table is stored
at `docs/publication/benchmark/feature_benchmarks/feature_benchmark_summary.md`.
The KIRC hypoxia signature shows nominal log-rank and RMST evidence but fails
adjusted Cox and PH criteria; the SKCM effector x exhaustion interaction is not
significant; and the CA9 pan-cancer scan finds 8/32 cohorts at FDR<0.10 with a
modest heterogeneous random-effects estimate. Treat these as workflow
benchmarks, not biological discovery claims.

For the two-signature case, report both the crossed KM groups and the continuous
Cox interaction term `signature_A_z:signature_B_z`, including adjusted models
when stage and grade complete-case data are sufficient.

## Submission Package Status

Generated files:

- main manuscript: `manuscript/bioinformatics_app_note/main.tex`;
- main workflow figure source:
  `manuscript/bioinformatics_app_note/figures/workflow.tex`;
- supplementary material:
  `manuscript/bioinformatics_app_note/supplementary.tex`;
- Bioinformatics readiness checklist:
  `manuscript/bioinformatics_app_note/submission/submission_readiness_checklist.md`;
- cover letter draft:
  `manuscript/bioinformatics_app_note/submission/cover_letter_draft.md`.
- reviewer reproduction guide:
  `manuscript/bioinformatics_app_note/submission/reviewer_reproduction_guide.md`;
- final submission decision tracker:
  `manuscript/bioinformatics_app_note/submission/final_submission_decisions.md`;
- user-facing Help & Methods page in the app and repository `CHANGELOG.md` with
  v0.1.0 functional baseline plus methodological version history.

External blockers before submission:

- author list, affiliations and corresponding-author email;
- funding and conflict-of-interest statements;
- explicit software license file;
- reviewer-accessible or public repository URL;
- stable public demo or clear Docker-only reviewer instructions;
- archival DOI or stable release URL.

## Go/No-Go Criteria

Proceed toward Bioinformatics if all are true:

- public repository with license, issue tracker, installation docs and Docker;
- stable web demo available without mandatory registration;
- audit report export available for every completed survival analysis;
- at least three comparator-visible differentiators remain after benchmark;
- cSurvival and PESSA are acknowledged directly in the comparator narrative;
- RMST is available for two-group analyses and appears in JSON, audit reports
  and the UI;
- benchmark scripts/tables are reproducible from a clean checkout;
- manuscript can state the contribution without relying on a single biological
  result.

Fallback to JOSS or SoftwareX if the benchmark shows that the main novelty is
software integration and reproducibility rather than a clearly distinct
bioinformatics analysis capability.
