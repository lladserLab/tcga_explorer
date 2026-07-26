# Feature Signature Definitions

All feature benchmark signatures use log2(TPM + 1) expression.
Weighted signatures use `sum(weight * expression_gene) / sum(abs(weight))`; z-score signatures standardize each gene among eligible patients before the same weighted combination.

| Role | Workflow | Cohort | Endpoint | Score method | Construction | Rationale | Genes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Main | ACC BUB1B-PINK1 contrast | TCGA-ACC | OS | weighted | (BUB1B - PINK1)/2 on log2(TPM + 1) expression; continuous Cox primary and median split sensitivity. | RNA-seq analogue of the published two-gene differential-expression predictor; not a replication of its qRT-PCR threshold. | BUB1B, PINK1 (w=-1) |
| Main | UVM BAP1 marker | TCGA-UVM | DSS | single | Gene-level BAP1 expression; median split for crossed grouping. | Gene-expression workflow analogue of established BAP1 prognostic biology; not a mutation or immunohistochemistry classifier. | BAP1 |
| Main | UVM PRAME marker | TCGA-UVM | DSS | single | Gene-level PRAME expression; median split for crossed grouping. | Paired with BAP1 to exercise literature-anchored four-group stratification; not a clinical PRAME assay. | PRAME |
| Main | BIRC5 pan-cancer primary + ordinal sensitivity | pan-cancer | OS | single | Primary continuous Cox with expression z-scored within each cohort; parallel ordinal stage, grade and stage+grade sensitivity models. | Published pan-cancer prognostic marker used to exercise FDR, family-specific adjustment and meta-analysis. | BIRC5 |
| Diagnostic | KIRC compact hypoxia signature | TCGA-KIRC | OS | zscore | Equal-weight mean of per-gene z-scores. | Compact Hallmark-aligned hypoxia example selected to exercise transparent multi-gene scoring without presenting a pathway model. | CA9, VEGFA, SLC2A1, LDHA, PGK1 |
| Diagnostic | SKCM effector signature | TCGA-SKCM | OS | zscore | Equal-weight mean of per-gene z-scores; crossed with the exhaustion signature after median splits. | Cytotoxic T-cell and interferon-chemokine example selected for an immune-active TCGA-SKCM workflow benchmark. | CD8A, GZMB, PRF1, IFNG, CXCL9, CXCL10 |
| Diagnostic | SKCM exhaustion signature | TCGA-SKCM | OS | zscore | Equal-weight mean of per-gene z-scores; crossed with the effector signature after median splits. | Checkpoint/exhaustion marker example paired with the effector score to exercise two-signature grouping and interaction Cox. | PDCD1, CTLA4, LAG3, HAVCR2, TIGIT |
| Diagnostic | CA9 pan-cancer primary + ordinal sensitivity | pan-cancer | OS | single | Primary single-gene continuous Cox with expression z-scored within each cohort; parallel ordinal stage, grade and stage+grade sensitivity models. | Single-gene hypoxia and kidney-cancer marker canary selected to expose attenuation and cross-cancer heterogeneity. | CA9 |
