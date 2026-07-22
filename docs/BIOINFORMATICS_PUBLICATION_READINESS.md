# Bioinformatics Publication Readiness

This document defines the work needed to position TCGA Explorer as a
Bioinformatics Application Note rather than a general software note.

## Proposed Positioning

TCGA Explorer is an auditable TCGA survival web application for endpoint-aware,
clinically adjusted, signature-based and pan-cancer transcriptomic survival
analysis.

The contribution is not a new Kaplan-Meier implementation. The contribution is
the integration of:

- TCGA-CDR OS, DSS, DFI and PFI endpoint handling with fallback OS metadata;
- one RNA-seq sample per TCGA participant using an explicit biospecimen rule;
- gene and custom signature scoring, including weighted signatures;
- two-signature combined stratification;
- univariable and stage/grade-adjusted Cox models;
- proportional-hazards QC from `cox.zph` where estimable;
- continuous pan-cancer Cox scans with BH-FDR and meta-analysis;
- downloadable raw records, methods text and audit reports.

## Comparator Matrix

| Tool | Main scope | TCGA-CDR endpoints | Adjusted Cox | Custom signatures | Two-signature groups | Pan-cancer Cox/FDR | Audit export |
| --- | --- | --- | --- | --- | --- | --- | --- |
| GEPIA2 | TCGA/GTEx expression and survival | Partial/unclear in UI | No focused adjusted workflow | Yes | No | Limited | No |
| UALCAN | TCGA/CPTAC expression, subgroups, survival | Partial/unclear in UI | No focused adjusted workflow | Limited | No | No | No |
| OncoLnc | TCGA gene survival | No | No | No | No | Precomputed multi-cancer | Limited |
| KM Plotter | Survival biomarker screening | Dataset-dependent | Limited | Some gene-set modes | No | Yes, by modules | Limited |
| UCSC Xena | General multi-omics browser | Dataset-dependent | No focused adjusted workflow | Manual | Manual | No | Limited |
| cBioPortal | Cancer genomics exploration | Dataset-dependent | No focused adjusted workflow | Alteration groups | No | Across studies | Limited |
| DoSurvive | Survival database/web tool | Dataset-dependent | Yes, selected workflows | Yes | No | Database-dependent | Limited |
| PESSA | Gene-set activation survival | Dataset-dependent | Cox support | Yes, gene sets | No | Dataset database | Downloadable outputs |
| TCGAbiolinks | R package for TCGA workflows | Yes if configured | Programmable | Programmable | Programmable | Programmable | Script-level |
| TCGAplot | R package for pan-cancer analysis | Dataset-dependent | Programmable | Yes | No focused UI | Yes | Script-level |
| TCGA Explorer | TCGA survival webapp | Yes, endpoint QC exposed | Yes | Yes | Yes | Yes | Yes |

Sources used to frame the comparison:

- GEPIA2: https://academic.oup.com/nar/article/47/W1/W556/5494747
- OncoLnc: https://doaj.org/article/9733114d14464feebda2a410f09e148f
- PESSA: https://journals.plos.org/ploscompbiol/article?id=10.1371%2Fjournal.pcbi.1012024
- TCGAbiolinks: https://academic.oup.com/nar/article/44/8/e71/2465925
- TCGAplot: https://link.springer.com/article/10.1186/s12859-023-05615-3
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

## Go/No-Go Criteria

Proceed toward Bioinformatics if all are true:

- public repository with license, issue tracker, installation docs and Docker;
- stable web demo available without mandatory registration;
- audit report export available for every completed survival analysis;
- at least three comparator-visible differentiators remain after benchmark;
- benchmark scripts/tables are reproducible from a clean checkout;
- manuscript can state the contribution without relying on a single biological
  result.

Fallback to JOSS or SoftwareX if the benchmark shows that the main novelty is
software integration and reproducibility rather than a clearly distinct
bioinformatics analysis capability.
