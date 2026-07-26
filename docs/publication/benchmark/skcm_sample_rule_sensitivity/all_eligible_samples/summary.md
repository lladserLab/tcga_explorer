# TCGA-SKCM PDCD1 OS sample-rule sensitivity (all eligible samples)

- Run started: 2026-07-25T02:40:58Z
- Run finished: 2026-07-25T02:40:59Z
- Completed analyses: 1/1
- Cached analyses in this run: 1/1
- API base URL: `http://192.168.1.31:3000/tcga_explorer`
- Cohort: `TCGA-SKCM`
- Gene: `PDCD1`
- Endpoint: `OS`
- Expression scale: `log2_tpm`
- BH family: completed cutpoint methods within this marker-endpoint scenario.
- No composite retention rule is applied. Log-rank, Cox and RMST are related summaries of the same outcomes and are not counted as independent barriers.
- Marker-specific PH and global model PH are reported separately as interpretation diagnostics.
- Maxstat is outcome-optimized. Its corrected rank-statistic p-value is reported, while grouped HR, confidence intervals and RMST remain post-selection.
- Cutpoint-independent continuous reference: n=453, events=213, HR per +1 SD=0.67 (0.58-0.78), linear p=1.27e-07, linear BH q=, events/parameter=213.0, nonlinearity p=0.806, nonlinearity BH q=.

| Method | n | Events | BH q | HR | Cox p | Adjusted HR | Adjusted p | Marker PH p | Global PH p | RMST delta @ tau | RMST p | Notes |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| median | 453 | 213 | 3.16e-06 | 0.53 (0.40-0.69) | 4.59e-06 | 0.49 (0.36-0.66) | 1.98e-06 | 0.631 | 0.012 | 218 @ 1826 | 1.20e-04 | Global PH caution; marker term not flagged |

## Audit Hashes

| Method | Analysis ID | Reproducibility hash | Grouped records SHA-256 | Continuous records SHA-256 |
| --- | --- | --- | --- | --- |
| median | `f1786d8204ec400199eb3d648302e056` | `8ff183ea2f8b0fcee0e19f0d5d11dd305ba08ce473cbcba0da51b76b7d31a232` | `8dab9305760c2f2c0afa6c671ddba73a73391ddbcef59e866749bf4efe7faa7a` | `8927efdcba6c46f1a92af1d4c6a8b5f84c8cf64767ee5fa374329c0c95ba5fe4` |

## RMST Tau Sensitivity

| Method | Tau fraction | Tau days | RMST delta days | RMST p |
| --- | ---: | ---: | ---: | ---: |
| median | 0.75 | 1369.7 | 130 | 4.72e-04 |
| median | 0.90 | 1643.6 | 178 | 2.67e-04 |
| median | 1.00 | 1826.2 | 218 | 1.20e-04 |
