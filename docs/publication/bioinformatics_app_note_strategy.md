# TCGA Explorer Bioinformatics Application Note Strategy

Status: working strategy, July 22, 2026.

## Critical Diagnosis

TCGA Explorer is technically credible as an auditable TCGA survival web
application, but the manuscript cannot claim two-signature survival grouping or
two-biomarker interaction as the main novelty. cSurvival already provides joint
analysis with two genomic predictors and algorithms for optimal cutoffs across
two continuous predictors.

The defensible Bioinformatics Application Note contribution is instead the
combination of:

- verifiable audit reports with SHA-256 hashes, exact patient records, request
  payloads, artifact checksums and software versions;
- automatic Cox proportional-hazards diagnostics from `cox.zph`;
- endpoint-aware TCGA-CDR support for OS, DSS, DFI and PFI, with event QC;
- one-sample-per-patient TCGA biospecimen selection before survival modeling;
- cutpoint robustness across predefined dichotomization rules;
- RMST reporting for two-group comparisons, providing an interpretable
  time-scale effect estimate beside HR and log-rank p-values;
- continuous Cox models for single markers, pan-cancer scans and two-signature
  interactions.

This reframes two-signature analysis as a supported workflow, not as the unique
methodological gap.

## Claims That Survive Reviewer Scrutiny

1. **Auditable survival analyses.** Existing TCGA survival web tools usually
   expose plots, tables and downloads, but not a complete reproducibility bundle
   with exact patient rows, parameter hash, artifact checksums and package
   versions.
2. **Built-in proportional-hazards QC.** TCGA Explorer reports `cox.zph`
   diagnostics automatically for fitted Cox models and flags global PH
   violations.
3. **Cutpoint robustness as a first-class output.** The app lets users run the
   major grouping rules side by side and marks which signals survive downstream
   tests rather than presenting one selected p-value.
4. **Time-scale effect reporting with RMST.** RMST complements HRs and KM plots
   with an interpretable survival-time difference at a declared truncation time.
5. **Endpoint and sample-selection rigor.** TCGA-CDR endpoint choices and
   one-sample-per-patient rules are exposed in methods/audit artifacts.

## Comparator Matrix

| Tool | Main scope | Key overlap | Correct comparison point |
| --- | --- | --- | --- |
| GEPIA2 | TCGA/GTEx expression and survival | Web-based expression survival workflows | Does not expose a full audit bundle or PH diagnostics in the survival UI. |
| UALCAN | TCGA/CPTAC expression, subgroups and survival | TCGA biomarker exploration | Strong portal, but not designed around reproducible survival payloads and hashes. |
| OncoLnc | TCGA gene survival | TCGA survival associations | Primarily precomputed gene-level survival results; limited auditability. |
| KM Plotter | Survival biomarker screening | Marker survival plots across datasets | Strong screening tool; limited endpoint/sample audit and PH reporting in UI. |
| UCSC Xena | General multi-omics browser | Custom exploration of TCGA-like matrices | Powerful browser, but manual workflows are less reproducible by default. |
| cBioPortal | Cancer genomics exploration | Clinical-genomic subgroup survival | Broad portal; not focused on auditable transcriptomic survival workflows. |
| cSurvival | Biomarker interactions in cancer outcomes | Two-predictor joint survival, optimal two-predictor cutoffs, gene sets | Must be acknowledged as prior art for two-biomarker interaction; TCGA Explorer differs by audit, PH QC, CDR endpoint workflow and RMST/robustness reporting. |
| DoSurvive | Prognostic biomarker database/web tool | Multivariate survival with mRNA, miRNA, lncRNA, protein and methylation; OS/DSS/DFI/PFI | Strong overlap in multivariable survival; TCGA Explorer should not claim uniqueness there. |
| PESSA | Pathway enrichment score-based survival | ssGSEA gene-set scores, median/optimal cutoffs, Cox in 238 datasets | Stronger gene-set scoring framework; TCGA Explorer uses simpler weighted z-scores for interpretability and auditability. |
| TCGAbiolinks | R package for TCGA workflows | Programmable TCGA data acquisition/analysis | Reproducible by code, but not a ready web workflow with audit bundles. |
| TCGAplot | R package for pan-cancer analysis | Pan-cancer analysis | Programmable R workflow, not an auditable web application. |

## Journal Positioning

| Journal | Recommendation | Rationale |
| --- | --- | --- |
| Bioinformatics Application Note | Target after RMST, corrected comparator table and benchmark | Feasible if framed as auditable, robust TCGA survival software, not as novel two-biomarker interaction. |
| BMC Bioinformatics | Realistic fallback | More space for integration, benchmark and methodological care. |
| SoftwareX | High-probability fallback | Strong fit for Dockerized, reproducible research software. |
| JOSS | Safe software fallback | Requires public repo, license and concise software paper. |
| NAR Web Server | Not yet | Needs stable public HTTPS deployment and a stronger web-server novelty claim. |

## Bioinformatics Manuscript Narrative

Working title:

> TCGA Explorer: auditable and robust survival analysis workflows for TCGA transcriptomic biomarkers

Core argument:

> TCGA Explorer addresses a practical reproducibility gap in TCGA biomarker
> survival analysis. Instead of returning only Kaplan-Meier plots from a chosen
> cutoff, it records the full analysis payload, patient set, endpoint source,
> software versions and artifact checksums, while reporting Cox PH diagnostics,
> cutpoint robustness and RMST time-scale effects.

Do not use as primary novelty:

- two-signature groups;
- two-signature Cox interaction;
- custom gene signatures alone;
- pan-cancer Cox alone.

Use as supporting capabilities:

- two-signature analysis, including continuous interaction Cox;
- weighted z-score signatures;
- pan-cancer Cox/FDR and meta-analysis.

## Benchmark Cases

Minimum cases for the paper:

| Case | Cohort | Marker/signature | Endpoint | Output needed |
| --- | --- | --- | --- | --- |
| 1 | TCGA-KIRC | CA9 | OS | Audit report, PH diagnostics, RMST, cutpoint robustness. |
| 2 | TCGA-BRCA | MKI67 | OS and PFI | Endpoint sensitivity and clinical interpretability. |
| 3 | TCGA-SKCM | PDCD1 | OS | Immune checkpoint marker example. |
| 4 | TCGA-LUAD | CD274 | OS and PFI | Checkpoint ligand and endpoint sensitivity. |
| 5 | TCGA-KIRC | hypoxia signature | OS | Multi-gene weighted z-score signature example. |
| 6 | TCGA-SKCM | effector x exhaustion signatures | OS | Two-signature workflow as non-novel supported capability. |
| 7 | Pan-cancer | CA9 | OS | Continuous pan-cancer Cox/FDR workflow. |
| 8 | Low-event endpoint | Any feasible cohort/marker | DSS or DFI | Endpoint QC and not-reached median handling. |

## Current Benchmark Result

Case 1 has been run through the HTTP API:

```text
scripts/publication/run_cutpoint_benchmark.py
```

Output:

```text
docs/publication/benchmark/kirc_ca9_cutpoint_benchmark/
```

Result summary: CA9 in TCGA-KIRC shows nominal evidence for selected cutpoints
in log-rank, univariable Cox and RMST, but no dichotomization survives the full
downstream rule because adjusted Cox and/or PH diagnostics fail. This supports
the Application Note narrative: TCGA Explorer is not just another
Kaplan-Meier plotter, but a tool that makes cutoff-dependent exploratory
signals auditable and harder to overclaim.

## Sources

- Bioinformatics author guidelines: https://academic.oup.com/bioinformatics/pages/author-guidelines
- Bioinformatics submission limits: https://academic.oup.com/bioinformatics/pages/submission_online
- OUP General Template: https://www.overleaf.com/latex/templates/oup-general-template/ybpypwncdxyb
- cSurvival: https://academic.oup.com/bib/article/23/3/bbac090/6562683
- PESSA: https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1012024
- DoSurvive: https://pmc.ncbi.nlm.nih.gov/articles/PMC10440714/
- GEPIA2: https://academic.oup.com/nar/article/47/W1/W556/5494747
- TCGA-CDR: https://gdc.cancer.gov/about-data/publications/PanCan-Clinical-2018
- RMST biomarker paper: https://www.oncotarget.com/article/6121/text/
- Cutpoint methods comparison: https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0338425
