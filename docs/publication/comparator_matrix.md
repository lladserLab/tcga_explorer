# Comparator Matrix for Bioinformatics Application Note

Status: literature-backed working comparison, July 26, 2026.

## Interpretation

TCGA-TRACE should not be positioned as the first web tool for TCGA survival
analysis, two-marker survival interaction, gene-set survival analysis or PH
testing. The defensible gap is not any one survival method. It is the executable
combination of exact participant and expression-component provenance,
score/result reconstruction, endpoint-aware cohort construction, RMST and
cutpoint sensitivity in one TCGA transcriptomic survival workflow.

Source claims below were rechecked on 2026-07-26. Peer-reviewed papers are used
where available; official project pages are used for current web-only feature
claims.

## Compact Comparator Table

The supplement uses a strength-first positioning table rather than a binary
feature scorecard. “Residual point” identifies the narrower function evaluated
for TCGA-TRACE; it is not evidence that a capability is absent from every
version of another resource.

| Tool | Established strength | Residual point for this paper |
| --- | --- | --- |
| GEPIA2 | Gene, isoform, subtype and signature survival; API | One standardized score/cohort/diagnostic/result bundle |
| KM Plotter | Broad RNA, protein and DNA survival screening | Exact TCGA endpoint/sample provenance and rerun artifact |
| UALCAN | Broad TCGA/CPTAC cancer-omics portal and survival plots | Run-level endpoint provenance and diagnostics |
| cSurvival | Two-predictor interaction, optimized cutoffs and gene sets | Declared multiverse and signed reconstructable run |
| DoSurvive | Combined multi-omic biomarkers and four endpoints | TCGA-TRACE is narrower; it tests run provenance |
| PESSA | ssGSEA, continuous/grouped Cox and Schoenfeld tests | Simpler scores, but bound components, RMST and source identifiers |
| PrognoScan | Multi-cohort microarray survival with corrected minimum-p cutpoints | TCGA RNA/CDR scope plus declared cutpoint multiverse |
| OncoLnc | Downloadable TCGA survival linked to mRNA, miRNA and lncRNA | Current source/sample/diagnostic reconstruction contract |
| ESurv | Continuous analysis, user data and penalized multi-omic signatures | Explicit endpoint/sample provenance and fixed rerun bundle |
| GSCA | GSVA gene-set analysis across genomic, immune and drug modules | TCGA-TRACE is methodologically narrower; it binds one survival run |
| TCGEx | Broad expression analysis, enrichment, clustering, ML and user data | Survival-specific endpoint/sample/run reconstruction |
| Survival Genie 2 | 132 datasets and single-cell-derived target workflows | Narrower TCGA scope with durable signed analysis records |
| UCSC Xena | Flexible multi-omic browsing and custom survival | Standardized survival-specific export |
| cBioPortal | Broad genomics, APIs, survival and shareable sessions | Cross-pipeline comparator plus exact run artifact |
| TIMER2.0 | Immune estimation and outcome exploration | No immune-method claim; narrower reporting contract |
| SurvExpress | Signature risk groups across cancer datasets | TCGA-CDR/sample-selection and executable provenance |
| TCGAbiolinks | Flexible, code-based GDC/TCGA workflows | Interactive standardization plus standalone R export |
| TCGAplot | Programmable TCGA pan-cancer analyses | Endpoint-aware survival record and fixed verifier |
| CaPSSA | Mutation/CNV/expression-defined patient stratification | TCGA-TRACE focuses on transcriptomic estimands and run reconstruction |
| SurvBoard | Standardized multi-omic survival-prediction benchmarking | Different target: marker-association records rather than predictive leaderboards |

The manuscript supplement keeps the closest 12 resources in its compact table
and discusses eight further direct or adjacent systems in prose. No independent
feature audit of all comparator versions was performed.

## Manuscript-Safe Claim

> Existing resources provide strong interactive survival exploration,
> two-predictor interaction analysis, multi-omic survival modeling, ssGSEA
> gene-set survival and, in PESSA, Schoenfeld PH testing. TCGA-TRACE complements
> these tools by making reconstruction a standard output: exact participant
> records, source-expression hashes, component values, GDC identifiers, endpoint
> source, sample-selection rule, software versions and result hashes are exported
> together and verified by an executable round trip.

## Source Evidence Register

| Tool | Evidence checked | Primary source | Safe interpretation for TCGA-TRACE |
| --- | --- | --- | --- |
| GEPIA2 | TCGA/GTEx expression analysis, survival maps, gene/isoform/signature survival support and API. | https://academic.oup.com/nar/article/47/W1/W556/5494747 | Cite as established expression-survival and signature prior art; do not claim basic KM/survival-map novelty. |
| cSurvival | Joint survival analysis with two genomic predictors, optimal cutoffs for two continuous predictors, gene-set survival and cell-line integration. | https://academic.oup.com/bib/article/23/3/bbac090/6562683 | Treat two-predictor survival and gene-set survival as prior art; position TCGA-TRACE on reconstructable run records, endpoint provenance, RMST and sensitivity outputs rather than PH alone. |
| DoSurvive | Log-rank, Cox and AFT survival over mRNA, miRNA, lncRNA, protein and methylation with OS, DSS, DFI and PFI. | https://pmc.ncbi.nlm.nih.gov/articles/PMC10440714/ | Do not claim uniqueness in multi-omic or combined-biomarker survival; emphasize patient-level provenance and model-QC exports. |
| PESSA | ssGSEA pathway activation scores, median/optimal cutoffs, grouped and continuous Cox models, and `cox.zph` Schoenfeld tests across 238 datasets, 51 cancer types and 13 outcome types. | https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1012024 | Acknowledge stronger pathway-survival scope and PH testing; frame TCGA-TRACE signatures as simpler and focus the comparison on auditable score/cohort reconstruction, RMST and endpoint/sample provenance. |
| UALCAN | TCGA/MET500/CPTAC/CBTTC cancer omics access, biomarker validation, expression profiles and patient-survival plots. | https://ualcan.path.uab.edu/ | Use as portal/context comparator; avoid suggesting it lacks survival visualization. The gap is exported survival provenance and diagnostics. |
| KM Plotter | Current site states screening across mRNA, miRNA, protein and DNA assays in 40k+ samples; pan-cancer RNA-seq work is also published. | https://kmplot.com/ and https://www.nature.com/articles/s41598-021-84787-5 | Use as strong screening prior art; TCGA-TRACE should claim traceable endpoint/sample/run outputs rather than screening breadth. |
| UCSC Xena | General cancer genomics visualization platform; survival documentation describes stratification by genomic or phenotypic variables. | https://www.nature.com/articles/s41587-020-0546-8 and https://xena.ucsc.edu/kaplan-survival-analysis | Treat as flexible manual browser; the differentiator is a standardized exported run record per survival run. |
| cBioPortal | Large-scale cancer genomics exploration with survival analysis, group comparisons, APIs and shareable sessions. | https://docs.cbioportal.org/user-guide/faq/ and https://aacrjournals.org/cancerdiscovery/article/2/5/401/3246/The-cBio-Cancer-Genomics-Portal-An-Open-Platform | Use as broad clinical-genomics portal prior art; do not overstate absence of survival or sharing features. |
| TIMER2.0 | Immune, exploration, estimation and outcome modules for TCGA/user-provided data. | https://pmc.ncbi.nlm.nih.gov/articles/PMC7319575/ | Use as immune/outcome portal prior art; TCGA-TRACE should not claim broad TCGA outcome exploration novelty. |
| SurvExpress | Gene-expression biomarker validation, risk groups and survival analysis across cancer datasets. | https://pmc.ncbi.nlm.nih.gov/articles/PMC3774754/ | Use as gene-signature survival/risk prior art; TCGA-TRACE differs by TCGA-CDR endpoint provenance and run-record export. |
| TCGAbiolinks | R/Bioconductor workflow to query, download and perform integrative analyses of GDC/TCGA data. | https://academic.oup.com/nar/article/44/8/e71/2465925 and https://gdc.cancer.gov/content/tcgabiolinks | Code-based reproducibility is established prior art; TCGA-TRACE's gap is an interactive workflow with standardized run artifacts. |
| TCGAplot | R package with built-in TCGA multi-omic pan-cancer data, expression/correlation/survival/user-defined analyses and visualization outputs. | https://link.springer.com/article/10.1186/s12859-023-05615-3 | Use as programmable pan-cancer analysis prior art; keep TCGA-TRACE's claim focused on transparent survival workflow behavior. |
| OncoLnc | Links TCGA survival data to mRNA, miRNA and lncRNA expression levels, with downloadable clinical/expression coupling. | https://www.oncolnc.org/ and https://doaj.org/article/9733114d14464feebda2a410f09e148f | Historical single-marker TCGA survival prior art; not part of the main manuscript comparator table unless more space is needed. |
| PrognoScan | Curated public microarray cohorts, multiple endpoints and a corrected minimum-p cutpoint search; its paper explicitly discusses cohort, care, platform and random-error heterogeneity. | https://link.springer.com/article/10.1186/1755-8794-2-18 | Treat cross-dataset survival screening and within-search cutpoint correction as prior art; distinguish the TCGA-CDR run record rather than optimized grouping itself. |
| ESurv | Single-gene continuous/grouped analyses, user-supplied data, and lasso/elastic-net/network-regularized multi-omic signatures. | https://www.jmir.org/2020/5/e16084 | Do not claim continuous survival analysis, uploaded data or signature modeling as unique; compare exact cohort and endpoint reconstruction. |
| GSCA | GSVA-based gene-set expression plus mutation, immune, clinical and drug modules across 33 cancers. | https://academic.oup.com/bib/article/24/1/bbac558/6957252 | Acknowledge substantially broader pathway and multi-omic analysis; TCGA-TRACE uses simpler scores and tests a narrower provenance contract. |
| TCGEx | TCGA/user-data survival modeling together with enrichment, clustering and machine learning; Docker image available. | https://doi.org/10.1038/s44319-025-00407-7 | Treat broad transcriptomic exploration and deployability as prior art; compare survival-specific endpoint/sample artifacts only. |
| Survival Genie 2 | 132 adult/pediatric datasets, multiple partitioning rules and survival analysis for single-cell-derived markers, modules and ligand-receptor pairs. | https://doi.org/10.1186/s13073-026-01651-9 | Recognize stronger dataset and single-cell-derived input breadth; the residual question is durable, executable run provenance rather than a 24-hour analysis identifier. |
| CaPSSA | Interactive patient stratification by mutation, copy number and expression on TCGA or uploaded data with immediate survival analysis. | https://academic.oup.com/bioinformatics/article/35/24/5341/5522011 | Prior art for flexible subgroup construction; TCGA-TRACE does not claim broader genomic stratification. |
| SurvBoard | Standardized multi-omic survival-prediction benchmark across TCGA, ICGC, TARGET and METABRIC with discrimination/calibration metrics and a leaderboard. | https://academic.oup.com/bib/article/26/5/bbaf521/8269886 | Adjacent rather than direct: predictive-model benchmarking is a different task from preserving one exploratory marker-association run. |

## Cross-Tool Limitations

The literature supports scope boundaries rather than a claim that competing
software is defective:

- Optimized grouping remains a selection and multiplicity problem even when
  the within-search p-value is corrected. PrognoScan addresses the cutpoint
  search itself; cSurvival identifies outer multiplicity as user-managed; ESurv
  recommends accompanying grouped output with a continuous analysis.
- PESSA, GSCA, TCGEx and Survival Genie 2 are broader than TCGA-TRACE for
  pathways, datasets, machine learning or single-cell-derived hypotheses. Their
  breadth is not a weakness and cannot be recast as one.
- TCGAbiolinks and TCGAplot can support fully reproducible code-first analyses.
  Their trade-off is that the analyst, rather than a fixed interface contract,
  defines endpoint harmonization, sample selection and report contents.
- SurvBoard evaluates prediction models and calibration; TCGA-TRACE evaluates
  marker associations and run reconstruction. Neither substitutes for the
  other.
- No portal, including TCGA-TRACE, converts retrospective TCGA association into
  independent biomarker validation or removes residual biological confounding.
