# TCGA-SKCM TMEM176B OS sample-rule sensitivity (metastatic only)

- Run started: 2026-07-25T02:41:15Z
- Run finished: 2026-07-25T02:41:19Z
- Completed analyses: 1/1
- Cached analyses in this run: 0/1
- API base URL: `http://192.168.1.31:3000/tcga_explorer`
- Cohort: `TCGA-SKCM`
- Gene: `TMEM176B`
- Endpoint: `OS`
- Expression scale: `log2_tpm`
- BH family: completed cutpoint methods within this marker-endpoint scenario.
- No composite retention rule is applied. Log-rank, Cox and RMST are related summaries of the same outcomes and are not counted as independent barriers.
- Marker-specific PH and global model PH are reported separately as interpretation diagnostics.
- Maxstat is outcome-optimized. Its corrected rank-statistic p-value is reported, while grouped HR, confidence intervals and RMST remain post-selection.
- Cutpoint-independent continuous reference: n=353, events=186, HR per +1 SD=0.77 (0.67-0.89), linear p=2.85e-04, linear BH q=, events/parameter=186.0, nonlinearity p=0.259, nonlinearity BH q=.

| Method | n | Events | BH q | HR | Cox p | Adjusted HR | Adjusted p | Marker PH p | Global PH p | RMST delta @ tau | RMST p | Notes |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| median | 353 | 186 | 2.42e-04 | 0.58 (0.43-0.78) | 2.87e-04 | 0.46 (0.33-0.64) | 2.82e-06 | 0.459 | 0.038 | 156 @ 1826 | 0.008 | Global PH caution; marker term not flagged |

## Audit Hashes

| Method | Analysis ID | Reproducibility hash | Grouped records SHA-256 | Continuous records SHA-256 |
| --- | --- | --- | --- | --- |
| median | `b103f569e61945f893e01fc8ceefce7f` | `328dde291d20a2027c61fc8b96f995d88f84dabc50f9314bbb45aeac458a79ba` | `d41e97b8e698664b5958ed0a8af5537f229583a5c8f6b7641b7b8bfb7076f157` | `703b2d2808f01fccd043ee58a16721166ff015cea4aee5bf716436e40d94b6f7` |

## RMST Tau Sensitivity

| Method | Tau fraction | Tau days | RMST delta days | RMST p |
| --- | ---: | ---: | ---: | ---: |
| median | 0.75 | 1369.7 | 76 | 0.049 |
| median | 0.90 | 1643.6 | 119 | 0.018 |
| median | 1.00 | 1826.2 | 156 | 0.008 |
