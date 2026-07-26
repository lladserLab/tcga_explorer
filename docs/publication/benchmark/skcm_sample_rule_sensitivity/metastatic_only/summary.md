# TCGA-SKCM PDCD1 OS sample-rule sensitivity (metastatic only)

- Run started: 2026-07-25T02:41:03Z
- Run finished: 2026-07-25T02:41:07Z
- Completed analyses: 1/1
- Cached analyses in this run: 0/1
- API base URL: `http://192.168.1.31:3000/tcga_explorer`
- Cohort: `TCGA-SKCM`
- Gene: `PDCD1`
- Endpoint: `OS`
- Expression scale: `log2_tpm`
- BH family: completed cutpoint methods within this marker-endpoint scenario.
- No composite retention rule is applied. Log-rank, Cox and RMST are related summaries of the same outcomes and are not counted as independent barriers.
- Marker-specific PH and global model PH are reported separately as interpretation diagnostics.
- Maxstat is outcome-optimized. Its corrected rank-statistic p-value is reported, while grouped HR, confidence intervals and RMST remain post-selection.
- Cutpoint-independent continuous reference: n=353, events=186, HR per +1 SD=0.69 (0.59-0.81), linear p=3.88e-06, linear BH q=, events/parameter=186.0, nonlinearity p=0.988, nonlinearity BH q=.

| Method | n | Events | BH q | HR | Cox p | Adjusted HR | Adjusted p | Marker PH p | Global PH p | RMST delta @ tau | RMST p | Notes |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| median | 353 | 186 | 1.10e-04 | 0.56 (0.41-0.75) | 1.38e-04 | 0.48 (0.35-0.66) | 7.12e-06 | 0.871 | 0.016 | 173 @ 1826 | 0.003 | Global PH caution; marker term not flagged |

## Audit Hashes

| Method | Analysis ID | Reproducibility hash | Grouped records SHA-256 | Continuous records SHA-256 |
| --- | --- | --- | --- | --- |
| median | `f1c9b07e361c4619bbdc38a108e34038` | `8ee06669acd37d6bf0746fdb3eef96808b9401b475aba493d9f976434f6647b0` | `bb9c091c2e2045ecc492eb7dc9fe16d8f2d2f9b1ac85eb218ea9f6d6f04aa97e` | `7361081f6e1b5daea3ae55e706833c50de278f8d66bd2a9e4cdcda891dae9e65` |

## RMST Tau Sensitivity

| Method | Tau fraction | Tau days | RMST delta days | RMST p |
| --- | ---: | ---: | ---: | ---: |
| median | 0.75 | 1369.7 | 97 | 0.011 |
| median | 0.90 | 1643.6 | 138 | 0.006 |
| median | 1.00 | 1826.2 | 173 | 0.003 |
