# Comparator Matrix for Bioinformatics Application Note

Status: literature-backed working comparison, July 22, 2026.

## Interpretation

TCGA Explorer should not be positioned as the first web tool for TCGA survival
analysis, two-marker survival interaction or gene-set survival analysis. The
defensible gap is the combination of patient-level auditability, endpoint
provenance, PH diagnostics, RMST reporting and cutpoint robustness in one TCGA
transcriptomic survival workflow.

## Compact Comparator Table

| Tool | Confirmed strengths | Overlap with TCGA Explorer | Gap TCGA Explorer targets |
| --- | --- | --- | --- |
| GEPIA2 | TCGA/GTEx expression, survival maps, gene/isoform/signature analysis, API. | Web-based expression survival and signature scoring. | Does not present an analysis audit bundle with exact patient rows, artifact checksums, PH QC and RMST robustness reporting as the central workflow. |
| cSurvival | Two genomic predictors, two-continuous-predictor optimal cutoffs, gene-set survival and cell-line integration. | Strong overlap with two-predictor/grouped survival and gene sets. | TCGA Explorer must cite this as prior art; its different contribution is auditability, CDR endpoint workflow, PH diagnostics, RMST and cutpoint robustness panels. |
| DoSurvive | Multi-omic biomarker survival, log-rank, Cox, AFT, four survival endpoint types and combined effects. | Strong overlap with multivariable and combined biomarker survival. | TCGA Explorer should not claim uniqueness in multivariate survival; the gap is transparent patient-level provenance, hashable audit exports and RMST/cutpoint robustness. |
| PESSA | ssGSEA pathway activation scores, median/optimal cutoffs, Cox, 238 datasets, 51 cancer types and 13 survival outcomes. | Stronger pathway/gene-set survival framework than weighted z-scores. | TCGA Explorer uses simpler scores for transparent auditability and adds PH/RMST/robustness/audit outputs. |
| UALCAN | TCGA/CPTAC expression, subgroup expression and survival visualizations. | User-friendly TCGA biomarker exploration. | Publication graphics rather than complete survival provenance and model diagnostics. |
| KM Plotter | Large survival biomarker screening across mRNA, miRNA, protein and DNA with many samples. | Broad biomarker survival screening. | Screening-oriented; not centered on exact TCGA-CDR endpoint selection, audit hashes, RMST or PH diagnostics. |
| UCSC Xena | General cancer genomics browser, data hubs and Kaplan-Meier survival analysis. | Flexible TCGA-like exploration with genomic/phenotypic stratification. | Powerful manual browser, but reproducibility depends on user workflow rather than an exported audit object. |
| cBioPortal | Broad cancer genomics exploration, group comparison and survival analysis. | Clinical-genomic subgroup survival. | Broad portal; not specialized for RNA survival cutpoint robustness, RMST and audit bundles. |
| TCGAbiolinks | Programmable TCGA workflows. | Reproducible code-based data acquisition and analysis. | Requires coding; TCGA Explorer offers an interactive workflow with standardized audit artifacts. |
| TCGAplot | R package for TCGA pan-cancer analysis and visualization. | Pan-cancer TCGA analysis. | Programmable package rather than web audit workflow; does not define the same survival robustness/audit contract. |

## Manuscript-Safe Claim

> Existing resources provide strong interactive survival exploration,
> two-predictor interaction analysis, multi-omic survival modeling and ssGSEA
> gene-set survival. TCGA Explorer complements these tools by making the
> reproducibility object the primary output: exact patient rows, endpoint source,
> sample-selection rule, software versions, artifact hashes, PH diagnostics, RMST
> and cutpoint robustness are exported together for each analysis.

## Source Notes

- GEPIA2 reports TCGA/GTEx expression analysis, survival maps and
  gene/isoform/signature survival support, including a Python API.
  Source: https://academic.oup.com/nar/article/47/W1/W556/5494747
- cSurvival explicitly supports joint analysis with two genomic predictors,
  optimal cutoffs for two continuous predictors and gene-set survival.
  Source: https://academic.oup.com/bib/article/23/3/bbac090/6562683
- DoSurvive supports log-rank, Cox and AFT models over mRNA, miRNA, lncRNA,
  protein and methylation with OS/DSS/DFI/PFI.
  Source: https://pubmed.ncbi.nlm.nih.gov/37609633/
- PESSA uses ssGSEA pathway activation scores, median/optimal cutoffs and Cox
  analyses across TCGA/GEO/EGA/article datasets.
  Source: https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1012024
- UALCAN is positioned as a TCGA/CPTAC cancer omics, expression and survival
  analysis portal.
  Source: https://ualcan.path.uab.edu/
- KM Plotter is positioned as a biomarker survival screening tool across mRNA,
  miRNA, protein and DNA in more than 40,000 samples.
  Source: https://kmplot.com/
- UCSC Xena supports Kaplan-Meier survival analysis over genomic and phenotypic
  variables.
  Source: https://xena.ucsc.edu/kaplan-survival-analysis
- cBioPortal describes survival analysis and group comparisons over large cancer
  genomics datasets.
  Source: https://docs.cbioportal.org/user-guide/faq/
- TCGAplot is an R package for built-in multi-omic TCGA pan-cancer analysis and
  visualization.
  Source: https://pmc.ncbi.nlm.nih.gov/articles/PMC10726608/
