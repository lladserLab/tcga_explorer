# Historical TCGA-TRACE Exploratory Candidate Register

Status date: 2026-07-23.

This is a historical triage record. It is superseded for publication
regeneration by
`docs/publication/benchmark/scenario_registry_v1.json` and
`docs/publication/scenario_endpoint_registry.md`. The versioned registry
explicitly records that initial selection followed exploratory triage, freezes
endpoint roles and prohibits result-driven in-place changes.

This register records literature-prioritized genes and compact gene sets that
can be used to validate TCGA-TRACE or to motivate exploratory examples. It is
not a discovery claim. Local TCGA-TRACE screens below were run as exploratory
triage; they should be followed by full cutpoint evidence maps, audit-bundle
verification and external concordance before any manuscript claim is made.

## Source Basis

- TCGA-SKCM: the TCGA melanoma publication reported that an immune-expression
  transcriptomic subclass, lymphocyte infiltrate and high LCK protein were
  associated with improved survival.
  Source: https://gdc.cancer.gov/about-data/publications/skcm_2015
- TCGA-KIRC: the TCGA clear-cell renal carcinoma publication highlights the
  VHL/oxygen-sensing axis and metabolic remodeling.
  Source: https://gdc.cancer.gov/about-data/publications/kirc_2013
- TCGA-LGG: the TCGA lower-grade glioma publication defines prognostically
  significant molecular classes more accurately captured by IDH, 1p/19q and TP53
  status than by histology alone. This makes LGG useful for showing confounding
  and PH/adjusted-model diagnostics.
  Source: https://gdc.cancer.gov/about-data/publications/lgg_2015
- TCGA-LIHC and TCGA-PAAD have disease-defining TCGA publications that include
  RNA-level molecular characterization.
  Source: https://www.cancer.gov/ccg/research/genome-sequencing/tcga/publications
- The 18-gene T-cell-inflamed profile was derived for pembrolizumab response
  biology across tumor types and captures antigen presentation, chemokine,
  cytotoxic and adaptive immune-resistance programs.
  Source: https://www.jci.org/articles/view/91190
- MSigDB Hallmark sets provide curated pathway anchors for hypoxia and EMT
  examples.
  Sources:
  https://www.gsea-msigdb.org/gsea/msigdb/human/geneset/HALLMARK_HYPOXIA.html,
  https://www.gsea-msigdb.org/gsea/msigdb/cards/HALLMARK_EPITHELIAL_MESENCHYMAL_TRANSITION.html
- Exploratory single-gene candidates have supporting but non-definitive
  literature/database anchors. TMEM176B is linked to antitumor immunity and has
  reported SKCM prognostic associations; ITGA2 has pancreatic-cancer prognostic
  evidence in Human Protein Atlas/TCGA-derived summaries; CXCL13 is linked to
  tertiary lymphoid structure biology in HNSC.
  Sources:
  https://pubmed.ncbi.nlm.nih.gov/31085177/,
  https://pubmed.ncbi.nlm.nih.gov/35399535/,
  https://www.proteinatlas.org/ENSG00000164171-ITGA2/cancer/pancreatic+cancer,
  https://pmc.ncbi.nlm.nih.gov/articles/PMC10807398/

## Historically Promoted Publication Examples

The final manuscript-facing examples were selected from the exploratory screen
and then rerun through the complete benchmark scripts on 2026-07-23. Selection
favored recognizable literature anchors and distinct diagnostic behavior, not
only the smallest p-values. This was retrospective selection and must not be
described as prospective validation. The complete registered panel remains in
the manuscript evidence matrix and supplement.

| Historical role | Workflow | Case | Triage rationale |
| --- | --- | --- | --- |
| Literature-guided stress test | Single gene | TCGA-LIHC CDC20 OS | Agreement across continuous and grouped reporting layers. |
| Literature-guided stress test | Single gene | TCGA-LUAD BIRC5 OS | Visible cutpoint dependence. |
| Low-event diagnostic | Single gene | TCGA-UVM BAP1 DSS | Disease-specific marker with only 21 DSS events explicitly reported. |
| Exploratory immune case | Single gene | TCGA-SKCM TMEM176B OS | Literature-prioritized immune-regulatory candidate. |
| PH diagnostic | Single gene | TCGA-LGG EMP3 OS | Marker-specific PH caution remains visible beside association and RMST. |
| Published score analogue | Weighted signature | TCGA-ACC `(BUB1B - PINK1)/2` OS | Exercises signed weighting; explicitly not an exact qRT-PCR threshold replication. |
| Crossed markers | Two-marker | TCGA-UVM BAP1 x PRAME DSS | Four-group separation is reported separately from the nonsignificant interaction term. |
| Heterogeneous evidence | Pan-cancer | BIRC5 continuous OS | Common-scale mean is accompanied by high heterogeneity, a prediction interval and non-pooled opposite-direction cohorts. |

Definitive generated results are stored in
`docs/publication/benchmark/single_gene_benchmark_overview.md` and
`docs/publication/benchmark/feature_benchmarks/feature_benchmark_summary.md`.

## Best Immediate Candidates

| Priority | Use | Cohort | Marker/signature | Why it is useful |
| --- | --- | --- | --- | --- |
| 1 | Validation | TCGA-SKCM | T-cell-inflamed GEP, HLA-DRA, CD8A, GZMB, LCK | Directly aligned with the TCGA-SKCM immune-survival finding and exercises single-gene and signature modes. |
| 2 | Validation plus exploratory | TCGA-SKCM | TMEM176B | Less saturated than PDCD1/CD274 but biologically connected to antigen-presenting/myeloid immune regulation; local evidence is strong. |
| 3 | Validation | TCGA-HNSC | TLS/B-cell axis, CXCL13 | Exercises an immune/TLS program in a second squamous cancer with adjusted Cox and PH diagnostics behaving cleanly. |
| 4 | Exploratory validation | TCGA-PAAD | ITGA2, KRT19, MUC1 | Small cohort but strong local ITGA2/KRT19 signal; useful for exploratory surface-antigen/adhesion examples if externally checked. |
| 5 | Validation of cautionary reporting | TCGA-LGG | CD44 or proliferation signature | Strong survival separation, but LGG biology is confounded by molecular class/grade; useful to show adjusted and PH diagnostics. |
| 6 | Cautionary known-biology case | TCGA-KIRC | Hypoxia compact set, CA9/SLC16A3/EGLN3 | Known VHL/HIF biology; local association is directionally strong but adjusted/PH checks often warn against overinterpretation. |
| 7 | Secondary exploratory | TCGA-LIHC | BIRC5 | Strong local proliferation-associated signal; needs external validation and careful framing. |

## Signature Definitions

| Signature | Genes used in this screen |
| --- | --- |
| T_CELL_INFLAMED_GEP | CCL5, CD27, CD274, CD276, CD8A, CMKLR1, CXCL9, CXCR6, HLA-DQA1, HLA-DRB1, HLA-E, IDO1, LAG3, NKG7, PDCD1LG2, PSMB10, STAT1, TIGIT |
| CYTOLYTIC_ACTIVITY | GZMA, PRF1 |
| PROLIFERATION_CELL_CYCLE | MKI67, TOP2A, AURKA, BIRC5, CCNB1, CDC20, UBE2C |
| PDAC_BASAL_DUCTAL | KRT5, KRT6A, KRT14, KRT17, S100A2, LAMC2, LAMB3, SLC2A1 |
| EMT_STROMA_COMPACT | VIM, FN1, COL1A1, COL1A2, ACTA2, TAGLN, POSTN, SPARC, LOXL2, TGFB1 |
| HCC_PROGENITOR | KRT19, EPCAM, PROM1, SOX9, CD24, TACSTD2 |
| HALLMARK_HYPOXIA_COMPACT | CA9, SLC2A1, VEGFA, LDHA, PDK1, EGLN3, NDRG1, BNIP3, ENO1, PGK1 |
| TLS_BCELL_AXIS | CXCL13, MS4A1, CD79A, CCL19, CCR7, LTB, LTA |

## Median OS Single-Gene Screen

Screen: median split, OS, log2(TPM + 1), no clinical filters. These p-values
are triage only and are not adjusted across all screened genes.

| Cohort | Gene | n/events | HR | Cox p | Adjusted p | RMST delta, days | RMST p | PH p | Direction | Analysis ID |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| TCGA-LGG | CHI3L1 | 511/125 | 3.11 | 1.45e-08 | 6.23e-06 | -1090 | 9.67e-05 | 2.26e-05 | harmful | 53e9fd83b0f54a558d6ef16282ebd8e0 |
| TCGA-SKCM | HLA-DRA | 453/213 | 0.488 | 3.66e-07 | 0.00149 | 2360 | 2.48e-06 | 0.132 | protective | bdc29bf712c247898620022686a30aeb |
| TCGA-SKCM | CD8A | 453/213 | 0.501 | 7.91e-07 | 0.0128 | 1990 | 1.71e-04 | 0.526 | protective | cb849ff86ebe43d5840bc42e97e7832f |
| TCGA-LGG | TOP2A | 511/125 | 2.62 | 1.45e-06 | 0.00248 | -891 | 0.00192 | 0.00182 | harmful | fbeb564d19094db095077d0ee613b6f8 |
| TCGA-SKCM | TMEM176B | 453/213 | 0.514 | 2.00e-06 | 4.15e-04 | 2050 | 3.11e-05 | 0.540 | protective | 1ad39b1838694e6eac83f293cda0ba05 |
| TCGA-SKCM | GZMB | 453/213 | 0.519 | 3.10e-06 | 0.00839 | 2160 | 9.83e-06 | 0.439 | protective | 968d238fdb404e39845e0f70ac5a0e11 |
| TCGA-LGG | CD44 | 511/125 | 2.01 | 2.53e-04 | 0.0134 | -601 | 0.0117 | 0.151 | harmful | 9b82d898554848f6b05ecf83fc57a9db |
| TCGA-LIHC | BIRC5 | 365/130 | 1.94 | 2.63e-04 | 0.00880 | -485 | 0.0137 | 0.667 | harmful | 71e167f9c0b040988ede454e25c44be5 |
| TCGA-PAAD | ITGA2 | 177/93 | 1.96 | 0.00188 | 0.0380 | -450 | 6.98e-04 | 0.376 | harmful | 1d765c2f5fde49509b088d0207013b85 |
| TCGA-PAAD | KRT19 | 177/93 | 1.92 | 0.00212 | 0.0311 | -333 | 0.0329 | 0.0856 | harmful | a324890e1c8a4c9dac4533be8b40ea77 |
| TCGA-HNSC | CXCL13 | 520/220 | 0.725 | 0.0183 | 0.00414 | 455 | 0.108 | 0.134 | protective | 1fd6ee64a18d4276aaeb6e6e4a5b87cd |

## Compact Signature Screen

Screen: median split, OS, z-score signature score, log2(TPM + 1), no clinical
filters.

| Cohort | Signature | Genes | n/events | HR | Cox p | Adjusted p | RMST delta, days | RMST p | PH p | Direction | Analysis ID |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| TCGA-SKCM | T_CELL_INFLAMED_GEP | 18 | 453/213 | 0.459 | 3.57e-08 | 0.0138 | 2390 | 1.48e-06 | 0.308 | protective | 69d4d78830e149b78edb0cdeb7cc1d9e |
| TCGA-SKCM | CYTOLYTIC_ACTIVITY | 2 | 453/213 | 0.508 | 1.40e-06 | 0.00331 | 2100 | 8.77e-05 | 0.158 | protective | 431e1dbce3eb4457a3b4134da7ecbd05 |
| TCGA-LGG | PROLIFERATION_CELL_CYCLE | 7 | 511/125 | 2.67 | 6.69e-07 | 0.00536 | -944 | 0.00251 | 0.00689 | harmful | bd1c0715161f4377b6e36c54ce998d37 |
| TCGA-KIRC | HALLMARK_HYPOXIA_COMPACT | 10 | 531/175 | 0.500 | 1.43e-05 | 0.100 | 773 | 1.88e-06 | 0.00105 | protective | ed4086b85b844e15bb7e9bc19a891c27 |
| TCGA-HNSC | TLS_BCELL_AXIS | 7 | 520/220 | 0.605 | 2.61e-04 | 0.00179 | 755 | 0.00989 | 0.155 | protective | ec84a403786547b7bdd94d04020a24cf |
| TCGA-PAAD | PDAC_BASAL_DUCTAL | 8 | 177/93 | 1.65 | 0.0176 | 0.465 | -230 | 0.0957 | 0.229 | harmful | fae208a2c314455f9634d464190fa220 |
| TCGA-PAAD | EMT_STROMA_COMPACT | 10 | 177/93 | 1.28 | 0.233 | 0.897 | -260 | 0.0739 | 0.251 | harmful | 41d287f71b724b028e2cf2bc6718450a |
| TCGA-LIHC | HCC_PROGENITOR | 6 | 365/130 | 1.05 | 0.787 | 0.836 | 115 | 0.567 | 0.887 | harmful | e7188498edb44c06bc7d86c764924e36 |

## Legacy Five-Cutpoint Triage (Superseded)

This table preserves the exploratory screen that preceded the frozen
publication registry. Its five-method BH/composite convention is not the
current TCGA-TRACE evidence contract and must not be used as a retention rule.
The current benchmark uses four nonredundant two-group rules with
within-scenario Holm and reports continuous, grouped, RMST and PH quantities
separately.

Screen: maxstat, median, upper quartile, outer quartiles and 75th percentile.
BH counts are within each five-method case. The conservative method count uses
the TCGA-TRACE evidence-map convention: BH log-rank, univariable Cox, adjusted
Cox and RMST p <= 0.05, no adjusted PH flag, and corrected maxstat p when
applicable.

| Cohort | Gene | Completed | BH | Cox | Adjusted | RMST | PH flagged | Conservative methods | Best method | Best HR | Best Cox p | Best adjusted p | Best RMST p |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | ---: | ---: | ---: | ---: |
| TCGA-SKCM | TMEM176B | 5 | 5 | 5 | 3 | 5 | 0 | 3 | maxstat | 0.502 | 1.02e-06 | 8.11e-04 | 1.90e-05 |
| TCGA-SKCM | HLA-DRA | 5 | 5 | 5 | 3 | 5 | 0 | 3 | maxstat | 0.412 | 2.10e-08 | 0.0130 | 1.87e-08 |
| TCGA-HNSC | CXCL13 | 5 | 5 | 5 | 5 | 1 | 0 | 1 | maxstat | 0.483 | 6.18e-04 | 0.00562 | 0.0179 |
| TCGA-PAAD | ITGA2 | 5 | 5 | 5 | 4 | 5 | 0 | 4 | maxstat | 3.10 | 2.91e-05 | 8.80e-04 | 9.09e-06 |
| TCGA-LIHC | BIRC5 | 5 | 5 | 5 | 3 | 5 | 0 | 3 | maxstat | 2.32 | 2.89e-06 | 4.03e-04 | 6.73e-04 |
| TCGA-LGG | CD44 | 5 | 5 | 5 | 5 | 5 | 0 | 5 | maxstat | 2.91 | 1.67e-08 | 7.13e-07 | 1.95e-04 |

## Recommended Use

1. `TCGA-SKCM TMEM176B OS` has been promoted to the formal single-gene
   cutpoint benchmark suite. Use it as a literature-prioritized exploratory
   association, not as a claim of novel biomarker discovery.
2. Consider `TCGA-SKCM HLA-DRA OS` only if an additional immune-validation
   case is needed; it is closer to the known antigen-presentation biology and
   therefore less exploratory than TMEM176B.
3. Add one second-tissue immune benchmark: `TCGA-HNSC CXCL13 OS` or
   `TCGA-HNSC TLS_BCELL_AXIS OS`. Keep this as validation/exploration unless
   external concordance is recorded.
4. Add one non-immune exploratory case: `TCGA-PAAD ITGA2 OS` or
   `TCGA-LIHC BIRC5 OS`. These have strong local evidence, but they require
   extra caution because cohort size, disease stage composition and external
   validation are important.
5. Keep `TCGA-LGG CD44` or the LGG proliferation signature as a cautionary
   diagnostics example. It is statistically strong, but LGG molecular class is a
   major confounder unavailable to the current TCGA-TRACE clinical-adjusted
   model.

## Do Not Overstate

- Do not describe any candidate as novel based only on this screen.
- Do not report the median-screen p-values as discovery-level evidence; they
  were used to prioritize cases.
- Prefer "literature-prioritized exploratory association" for TMEM176B, ITGA2,
  BIRC5 and CXCL13 until external validation is recorded.
- For LGG, emphasize that transcriptomic survival separation may proxy IDH,
  1p/19q, TP53 or grade-related biology.
- For KIRC hypoxia, emphasize that strong KM/RMST separation can coexist with
  adjusted-model or PH warnings.
