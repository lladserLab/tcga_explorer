# TCGA-SKCM TMEM176B OS sample-rule sensitivity (primary tumor only)

- Run started: 2026-07-25T02:41:12Z
- Run finished: 2026-07-25T02:41:15Z
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
- Cutpoint-independent continuous reference: n=102, events=29, HR per +1 SD=0.96 (0.67-1.38), linear p=0.841, linear BH q=, events/parameter=29.0, nonlinearity p=0.057, nonlinearity BH q=.

| Method | n | Events | BH q | HR | Cox p | Adjusted HR | Adjusted p | Marker PH p | Global PH p | RMST delta @ tau | RMST p | Notes |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| median | 102 | 29 | 0.630 | 0.84 (0.40-1.74) | 0.631 | 0.86 (0.40-1.88) | 0.711 | 0.710 | 0.245 | 6 @ 698 | 0.859 | No model-diagnostic caution recorded |

## Audit Hashes

| Method | Analysis ID | Reproducibility hash | Grouped records SHA-256 | Continuous records SHA-256 |
| --- | --- | --- | --- | --- |
| median | `9a3f83141e494474b1b74c401e9ee669` | `322d4f5007ff26b064be03f15e5502c68e6ce2b3d715f978661075ebc5193ac1` | `09ac1ed514f9d81350fd5ecb3e20ee8dae92c2f272d83bb1ee22b8d8e355d0e9` | `c6205f99b3fc80a3b3a3dbc39e94cda2022771005ed52316b53b2877069a8fae` |

## RMST Tau Sensitivity

| Method | Tau fraction | Tau days | RMST delta days | RMST p |
| --- | ---: | ---: | ---: | ---: |
| median | 0.75 | 523.9 | 2 | 0.920 |
| median | 0.90 | 628.6 | 4 | 0.873 |
| median | 1.00 | 698.5 | 6 | 0.859 |
