# Comparator Matrix for Bioinformatics Application Note

Status: literature-backed working comparison, July 24, 2026.

## Interpretation

TCGA-TRACE should not be positioned as the first web tool for TCGA survival
analysis, two-marker survival interaction, gene-set survival analysis or PH
testing. The defensible gap is not any one survival method. It is the executable
combination of exact participant and expression-component provenance,
score/result reconstruction, endpoint-aware cohort construction, RMST and
cutpoint sensitivity in one TCGA transcriptomic survival workflow.

Source claims below were rechecked on 2026-07-22. Peer-reviewed papers are used
where available; official project pages are used for current web-only feature
claims.

## Compact Comparator Table

The supplement uses a compact evidence table so the reader can see the
TCGA-TRACE comparison point before reading the detailed source-by-source
register. Negative entries below mean that a capability was not reported in the
cited paper, not that every current interface state was exhaustively audited.

| Tool | Signature or two-marker analysis | PH test described | RMST described | Multiple cutpoints | Reconstructable audited score/cohort |
| --- | --- | --- | --- | --- | --- |
| GEPIA2 | Yes | Not reported in cited paper | Not reported | Limited | Not reported |
| KM Plotter | Limited | Not reported in cited paper | Not reported | Limited | Not reported |
| cSurvival | Yes | Not reported in cited paper | Not reported | Yes | Not reported |
| DoSurvive | Yes | Not reported in cited paper | Not reported | Limited | Not reported |
| PESSA | Yes, ssGSEA | Yes, for continuous Cox | Not reported | Median and optimal | Not reported |
| TCGA-TRACE | Yes | Yes | Yes | Yes | Yes |

The longer evidence register below keeps the qualitative interpretation for
additional comparators that do not fit in the short Application Note table.

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
