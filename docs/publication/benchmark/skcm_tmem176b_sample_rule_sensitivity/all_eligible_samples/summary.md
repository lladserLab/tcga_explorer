# TCGA-SKCM TMEM176B OS sample-rule sensitivity (all eligible samples)

- Run started: 2026-07-25T02:41:11Z
- Run finished: 2026-07-25T02:41:12Z
- Completed analyses: 1/1
- Cached analyses in this run: 1/1
- API base URL: `http://192.168.1.31:3000/tcga_explorer`
- Cohort: `TCGA-SKCM`
- Gene: `TMEM176B`
- Endpoint: `OS`
- Expression scale: `log2_tpm`
- BH family: completed cutpoint methods within this marker-endpoint scenario.
- No composite retention rule is applied. Log-rank, Cox and RMST are related summaries of the same outcomes and are not counted as independent barriers.
- Marker-specific PH and global model PH are reported separately as interpretation diagnostics.
- Maxstat is outcome-optimized. Its corrected rank-statistic p-value is reported, while grouped HR, confidence intervals and RMST remain post-selection.
- Cutpoint-independent continuous reference: n=453, events=213, HR per +1 SD=0.77 (0.67-0.87), linear p=7.09e-05, linear BH q=, events/parameter=213.0, nonlinearity p=0.100, nonlinearity BH q=.

| Method | n | Events | BH q | HR | Cox p | Adjusted HR | Adjusted p | Marker PH p | Global PH p | RMST delta @ tau | RMST p | Notes |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| median | 453 | 213 | 1.32e-06 | 0.51 (0.39-0.68) | 2.00e-06 | 0.44 (0.33-0.59) | 6.16e-08 | 0.479 | 0.026 | 231 @ 1826 | 4.42e-05 | Global PH caution; marker term not flagged |

## Audit Hashes

| Method | Analysis ID | Reproducibility hash | Grouped records SHA-256 | Continuous records SHA-256 |
| --- | --- | --- | --- | --- |
| median | `0c604217ab5d4eac833778fac81bc9c8` | `85538694498f0cf83adf4ef2156f058f288cb6730280c515fcdf9806da9882d2` | `8124add9985c91adb36191eefb1bb00ab3103660c32f514fa1cc63b44447c98a` | `6cbbf87f2f6cb2c918e489d74a75f1c6d7d723ec51318202a929f67f242c7a64` |

## RMST Tau Sensitivity

| Method | Tau fraction | Tau days | RMST delta days | RMST p |
| --- | ---: | ---: | ---: | ---: |
| median | 0.75 | 1369.7 | 129 | 5.16e-04 |
| median | 0.90 | 1643.6 | 188 | 1.14e-04 |
| median | 1.00 | 1826.2 | 231 | 4.42e-05 |
