# TCGA-TRACE Bioinformatics Application Note Strategy

Status: working strategy, July 24, 2026.

## Critical Diagnosis

TCGA-TRACE is technically credible as a transparent TCGA survival web
application, but the manuscript cannot claim two-signature survival grouping or
two-biomarker interaction as the main novelty. cSurvival already provides joint
analysis with two genomic predictors and algorithms for optimal cutoffs across
two continuous predictors.

The defensible Bioinformatics Application Note contribution is instead the
combination of:

- verifiable run reports with SHA-256 hashes, exact patient records, request
  payloads, artifact checksums and software versions;
- automatic Cox proportional-hazards diagnostics from `cox.zph`;
- endpoint-aware TCGA-CDR support for OS, DSS, DFI and PFI, with event QC;
- one-sample-per-patient TCGA biospecimen selection before survival modeling;
- cutpoint sensitivity across predefined dichotomization rules;
- RMST reporting for two-group comparisons, providing an interpretable
  time-scale effect estimate beside HR and log-rank p-values;
- continuous Cox models for single markers, pan-cancer scans and two-signature
  interactions, with parallel ordinal stage/grade sensitivity for pan-cancer
  effects.

This reframes two-signature analysis as a supported workflow, not as the unique
methodological gap.

## Claims That Survive Reviewer Scrutiny

1. **Traceable survival analyses.** Existing TCGA survival web tools usually
   expose plots, tables and downloads, but not a complete reproducibility bundle
   with exact patient rows, parameter hash, artifact checksums and package
   versions.
2. **PH diagnostics within the audited run.** TCGA-TRACE reports `cox.zph`
   diagnostics automatically for fitted Cox models and binds them to the run
   record. PH testing itself is prior art, including in PESSA.
3. **Cutpoint sensitivity as a first-class output.** The app lets users run the
   major grouping rules side by side and reports BH, Cox, adjusted Cox, RMST and
   PH diagnostics as an evidence map rather than presenting one selected
   p-value. Marker-term and global PH diagnostics remain separate, and no
   composite retention rule is applied.
4. **Time-scale effect reporting with RMST.** RMST complements HRs and KM plots
   with an interpretable survival-time difference at a declared truncation time.
5. **Endpoint and sample-selection rigor.** TCGA-CDR endpoint choices and
   one-sample-per-patient rules are exposed in methods and run records.

## Comparator Matrix

| Tool | Main scope | Key overlap | Correct comparison point |
| --- | --- | --- | --- |
| GEPIA2 | TCGA/GTEx expression and survival | Web-based expression survival workflows | Does not expose a standardized patient-level run bundle or PH diagnostics in the survival UI. |
| UALCAN | TCGA/CPTAC expression, subgroups and survival | TCGA biomarker exploration | Strong portal, but not designed around reproducible survival payloads and hashes. |
| OncoLnc | TCGA gene survival | TCGA survival associations | Primarily precomputed gene-level survival results; limited run-level provenance. |
| KM Plotter | Survival biomarker screening | Marker survival plots across datasets | Strong screening tool; limited endpoint/sample provenance and PH reporting in UI. |
| UCSC Xena | General multi-omics browser | Custom exploration of TCGA-like matrices | Powerful browser, but manual workflows are less reproducible by default. |
| cBioPortal | Cancer genomics exploration | Clinical-genomic subgroup survival | Broad portal; not focused on traceable transcriptomic survival workflows. |
| cSurvival | Biomarker interactions in cancer outcomes | Two-predictor joint survival, optimal two-predictor cutoffs, gene sets | Must be acknowledged as prior art for two-biomarker interaction; TCGA-TRACE differs by run traceability, PH QC, CDR endpoint workflow and RMST/sensitivity reporting. |
| DoSurvive | Prognostic biomarker database/web tool | Multivariate survival with mRNA, miRNA, lncRNA, protein and methylation; OS/DSS/DFI/PFI | Strong overlap in multivariable survival; TCGA-TRACE should not claim uniqueness there. |
| PESSA | Pathway enrichment score-based survival | ssGSEA scores, median/optimal cutoffs, grouped/continuous Cox and `cox.zph` in 238 datasets | Stronger gene-set scoring and PH prior art; TCGA-TRACE uses simpler scores and focuses on reconstructable cohort/scoring provenance plus RMST. |
| TCGAbiolinks | R package for TCGA workflows | Programmable TCGA data acquisition/analysis | Reproducible by code, but not a ready web workflow with standardized run records. |
| TCGAplot | R package for pan-cancer analysis | Pan-cancer analysis | Programmable R workflow, not an endpoint-aware web application with exported run records. |

## Journal Positioning

| Journal | Recommendation | Rationale |
| --- | --- | --- |
| Bioinformatics Application Note | Current target | Feasible if framed as a reconstructable TCGA survival run contract, not as novel two-biomarker interaction, PH testing or gene-set scoring. |
| BMC Bioinformatics | Realistic fallback | More space for integration, benchmark and methodological care. |
| SoftwareX | High-probability fallback | Strong fit for Dockerized, reproducible research software. |
| JOSS | Safe software fallback | Requires public repo, license and concise software paper. |
| NAR Web Server | Not yet | Needs stable public HTTPS deployment and a stronger web-server novelty claim. |

## Bioinformatics Manuscript Narrative

Working title:

> TCGA-TRACE: auditable survival analysis for TCGA transcriptomic biomarkers

Core argument:

> TCGA-TRACE
> addresses a practical reproducibility gap in TCGA biomarker
> survival analysis. Instead of returning only Kaplan-Meier plots from a chosen
> cutoff, it records the full analysis payload, patient set, endpoint source,
> source-expression and component values, selected GDC identifiers, software
> versions and result checksums, while providing a verifier that reconstructs
> scores and re-executes the frozen statistical input.

Do not use as primary novelty:

- two-signature groups;
- two-signature Cox interaction;
- custom gene signatures alone;
- pan-cancer Cox alone.

Use as supporting capabilities:

- two-signature analysis, including continuous interaction Cox;
- z-score and weighted signatures;
- pan-cancer primary Cox/FDR plus family-specific ordinal clinical sensitivity
  and meta-analysis.

## Benchmark Cases

Current manuscript-facing cases:

| Case | Cohort | Marker/signature | Endpoint | Output needed |
| --- | --- | --- | --- | --- |
| 1 | TCGA-LIHC | CDC20 | OS | Stable positive-control cutpoint panel. |
| 2 | TCGA-LUAD | BIRC5 | OS | Cutpoint-dependent positive-control panel. |
| 3 | TCGA-UVM | BAP1 | DSS | Transcript-level control with low event count reported. |
| 4 | TCGA-SKCM | TMEM176B | OS | Literature-prioritized exploratory marker. |
| 5 | TCGA-LGG | EMP3 | OS | PH-discordant diagnostic case. |
| 6 | TCGA-ACC | `(BUB1B - PINK1)/2` | OS | Signed weighted-score workflow. |
| 7 | TCGA-UVM | BAP1 x PRAME | DSS | Separate four-group separation from the continuous interaction term. |
| 8 | Pan-cancer | BIRC5 | OS | Continuous Cox/FDR and heterogeneous meta-analysis. |
| 9 | Supplementary diagnostics | CA9, MKI67, PDCD1, CD274, hypoxia and immune signatures | OS/PFI | Preserve null, endpoint-sensitive and discordant results. |

## Current Benchmark Results

The complete single-gene panel has been run through the HTTP API:

```text
scripts/publication/run_single_gene_benchmark_suite.py
```

Aggregate output:

```text
docs/publication/benchmark/single_gene_benchmark_overview.md
```

Result summary: the formal panel contains 11 single-gene endpoint scenarios
crossed with four nonredundant two-group methods (44 analyses). Suite-wide BH
correction applies to the 44 log-rank tests. LIHC/CDC20, LUAD/BIRC5, UVM/BAP1,
SKCM/TMEM176B and LGG/EMP3 illustrate stable, cutpoint-dependent, low-event and
PH-discordant outputs. The supplement preserves all scenarios, including null
results. The application shows BH, Cox, RMST, marker-term PH and global PH
separately because they do not form independent pass/fail barriers.

The two SKCM single-gene examples also have primary/metastatic sample-rule
sensitivity records. PDCD1 and TMEM176B produce different BH, adjusted-Cox and
diagnostic profiles in all-eligible, primary-only and metastatic-only samples.
The manuscript therefore treats SKCM sample composition as a reported
sensitivity setting.

The executable audit benchmark covers single-gene, weighted-signature and
crossed-signature runs. It passed 22/22, 23/23 and 20/20 checks, respectively,
including score reconstruction and deterministic R re-execution at absolute
tolerance \(10^{-8}\); all three targeted mutations were detected. This is the
primary empirical support for the manuscript's reporting-contract claim.

The statistical calibration benchmark separately evaluates the revised
evidence profile without defining a pass/fail score. In 2,000 observed-cohort
expression permutations and 2,000 simulations per known-truth scenario,
continuous Cox, spline, marker PH and grouped-family null rejection remained
between 3.2% and 5.8%. Naive post-selection maxstat rejected 38.2--39.6% under
null, whereas Lau94 rejected 1.8--2.4%. Delayed non-PH and U-shaped mechanisms
activated their intended PH and spline diagnostics. Replicate-level outputs
are stored in `docs/publication/benchmark/statistical_calibration/`.

The advanced main and diagnostic cases have also been run through the HTTP API:

```text
scripts/publication/run_feature_benchmarks.py
```

Aggregate output:

```text
docs/publication/benchmark/feature_benchmarks/feature_benchmark_summary.md
```

The supplementary feature benchmark tables report the exact ACC
`(BUB1B - PINK1)/2` score, UVM BAP1 x PRAME four-group separation and continuous
interaction as separate results, and the BIRC5 pan-cancer common-scale
REML/HKSJ estimate together with FDR counts, I2 and a 95% prediction interval.
Per-SD cohort effects are explicitly non-pooled. Stage+grade, stage-only and
grade-only sensitivity families remain separate, and availability-selected
mixed models are not synthesized. The earlier KIRC hypoxia and SKCM
effector-by-exhaustion examples, plus the CA9 attenuation and
direction-reversal result, are retained as supplementary diagnostics.

## Submission Package Status

Generated manuscript artifacts:

- main manuscript: `manuscript/bioinformatics_app_note/main.tex`;
- vector source and alt text for Figure 1:
  `manuscript/bioinformatics_app_note/figures/graphical_abstract.tex` and
  `manuscript/bioinformatics_app_note/figures/figure_alt_text.md`;
- supplementary material:
  `manuscript/bioinformatics_app_note/supplementary.tex`;
- readiness checklist:
  `manuscript/bioinformatics_app_note/submission/submission_readiness_checklist.md`;
- cover letter draft:
  `manuscript/bioinformatics_app_note/submission/cover_letter_draft.md`.
- reviewer reproduction guide:
  `manuscript/bioinformatics_app_note/submission/reviewer_reproduction_guide.md`;
- artifact manifest:
  `manuscript/bioinformatics_app_note/submission/artifact_manifest.md`.
- final submission decision tracker:
  `manuscript/bioinformatics_app_note/submission/final_submission_decisions.md`;
- SKCM sample-type sensitivity records:
  `docs/publication/benchmark/skcm_sample_rule_sensitivity/README.md`,
  `docs/publication/benchmark/skcm_tmem176b_sample_rule_sensitivity/README.md`;
- public web application:
  `https://apps.cienciavida.org/tcga_explorer/`;
- in-app Help & Methods page plus repository `CHANGELOG.md` for user-facing
  parameter explanations and methodological version history.

Current external blockers before journal submission:

- add corresponding-author name/email, submitting-author name/ORCID and final
  CRediT roles;
- choose and add an explicit software license;
- tag and deploy the exact submitted source state, then archive it and add a
  version-specific DOI or stable release URL;
- name a support owner and commit to at least two years of software and
  web-service availability;
- repeat the passing provisional cross-browser checks against the exact tagged
  HTTPS deployment and preserve the results;
- independently rewrite and scientifically verify all author-facing content;
- provide a detailed AI-use declaration in the manuscript, supplement and cover
  letter; contact the editorial office if any use falls outside the examples
  covered by the journal guidance.

Author order, affiliations, funding, conflict declaration, public repository
and public application URL are already supplied. The open-access APC,
institutional discount or waiver route remains an operational decision on the
journal timeline, not a blocker to assembling the reviewer package.

Template note: the current manuscript PDF is an initial-submission file, not an
OUP production-template rendering. Bioinformatics states that initial
submissions may be PDF or LaTeX source and do not need to follow the template;
the template matters for revised/production files if requested. The
synchronized page-limit preview uses the current OUP general class with the
Bioinformatics journal mapping: numbered sections, `modern,large` design,
author-date citations (`namedate` plus `abbrvnat`) and the `Applications Note`
article label.

## Sources

- Bioinformatics author guidelines: https://academic.oup.com/bioinformatics/pages/author-guidelines
- Bioinformatics submission limits: https://academic.oup.com/bioinformatics/pages/submission_online
- OUP manuscript preparation and supported-journals list: https://academic.oup.com/pages/for-authors/journals/preparing-and-submitting-your-manuscript
- OUP General Template: https://www.overleaf.com/latex/templates/oup-general-template/fqkhysbcbpwv
- cSurvival: https://academic.oup.com/bib/article/23/3/bbac090/6562683
- PESSA: https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1012024
- DoSurvive: https://pmc.ncbi.nlm.nih.gov/articles/PMC10440714/
- GEPIA2: https://academic.oup.com/nar/article/47/W1/W556/5494747
- TCGA-CDR: https://gdc.cancer.gov/about-data/publications/PanCan-Clinical-2018
- RMST biomarker paper: https://www.oncotarget.com/article/6121/text/
- Cutpoint methods comparison: https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0338425
