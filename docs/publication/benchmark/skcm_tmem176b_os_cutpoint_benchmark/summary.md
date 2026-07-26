# TCGA-SKCM TMEM176B OS cutpoint benchmark

- Run started: 2026-07-25T17:51:09Z
- Run finished: 2026-07-25T17:51:23Z
- Completed analyses: 4/4
- Cached analyses in this run: 4/4
- API base URL: `http://192.168.1.31:3000/tcga_explorer`
- Cohort: `TCGA-SKCM`
- Gene: `TMEM176B`
- Endpoint: `OS`
- Expression scale: `log2_tpm`
- Prespecified complete-case Cox adjustment: age_at_index.
- Grouped-test family: four prespecified two-group cutpoint sensitivities within this marker-endpoint scenario.
- Grouped multiplicity: Holm adjustment within this scenario. The maxstat member contributes its Lau94 selection-adjusted rank-statistic p-value; the other prespecified rules contribute their log-rank p-values.
- No composite retention rule is applied. Log-rank, Cox and RMST are related summaries of the same outcomes and are not counted as independent barriers.
- Marker-specific PH and global model PH are reported separately as interpretation diagnostics.
- Maxstat is outcome-optimized. Its corrected rank-statistic p-value is reported, while grouped HR, confidence intervals and RMST remain post-selection.
- Cutpoint-independent continuous reference: n=453, events=213, HR per +1 SD=0.77 (0.67-0.87), linear p=7.09e-05, linear suite BH q=1.95e-04, events/parameter=213.0, nonlinearity p=0.100, nonlinearity suite BH q=0.275.

| Method | n | Events | Family p | Holm p | HR | Cox p | Adjusted HR | Adjusted p | Marker PH p | Global PH p | RMST delta @ tau | RMST p | Same-contrast HRs | Notes |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| maxstat | 453 | 213 | 5.66e-05 | 1.70e-04 | 0.50 (0.38-0.66) | 1.02e-06 | 0.52 (0.39-0.68) | 3.41e-06 | 0.837 | 0.965 | 235 @ 1826 | 2.91e-05 | grouped 0.50 vs continuous-implied 0.65; absolute log-HR ratio 1.60 | Outcome-optimized cutpoint; grouped estimates are post-selection |
| median | 453 | 213 | 1.32e-06 | 5.27e-06 | 0.51 (0.39-0.68) | 2.00e-06 | 0.54 (0.41-0.71) | 9.67e-06 | 0.913 | 0.983 | 231 @ 1826 | 4.42e-05 | grouped 0.51 vs continuous-implied 0.65; absolute log-HR ratio 1.54 | No model-diagnostic caution recorded |
| upper_quartile | 453 | 213 | 9.72e-04 | 9.72e-04 | 0.58 (0.42-0.81) | 0.001 | 0.60 (0.43-0.83) | 0.002 | 0.919 | 0.975 | 170 @ 1826 | 0.004 | grouped 0.58 vs continuous-implied 0.64; absolute log-HR ratio 1.20 | No model-diagnostic caution recorded |
| upper_lower_quartile | 228 | 111 | 1.91e-04 | 3.83e-04 | 0.49 (0.34-0.72) | 2.56e-04 | 0.50 (0.34-0.73) | 3.22e-04 | 0.539 | 0.815 | 282 @ 1826 | 4.70e-04 | grouped 0.49 vs continuous-implied 0.51; absolute log-HR ratio 1.04 | Middle 50% excluded |

## Audit Hashes

| Method | Analysis ID | Reproducibility hash | Grouped records SHA-256 | Continuous records SHA-256 |
| --- | --- | --- | --- | --- |
| maxstat | `77d496c6a35f4fa181c6b99c091b02e6` | `528431831f83c6f1f6515bb4f011f0aee0153239110e71e04f45692be13d9362` | `b68afe39c1d81f31b4dcc493fd9d499ddac1b189a8ae15c8d6cf0bbae4b94b7e` | `6cbbf87f2f6cb2c918e489d74a75f1c6d7d723ec51318202a929f67f242c7a64` |
| median | `404f1ec8aa2546efa5431fd6c2f35a1e` | `be863e44ecec5a6f3f25c11e30e314e4277eef554cd0d9afab0c9f3cbde86b54` | `8124add9985c91adb36191eefb1bb00ab3103660c32f514fa1cc63b44447c98a` | `6cbbf87f2f6cb2c918e489d74a75f1c6d7d723ec51318202a929f67f242c7a64` |
| upper_quartile | `16f14fc539834f69bcdd058af0e2d6ed` | `bec3306ee2f6423a0f5cbd355b794dad28ecdd0073b6a54c6598f670b21827e8` | `93d103c04dd318d0db042b1e7307713230cd33845ebe4a8d81d00b79080b87cc` | `6cbbf87f2f6cb2c918e489d74a75f1c6d7d723ec51318202a929f67f242c7a64` |
| upper_lower_quartile | `5fc367d42aca4710ab527f28c3874d0c` | `de25bc6db30443e4cc45e29f9b5ede77fc0936e5671c0350ff64fd5ab01802c9` | `e34d45664011eb863e83fcd45bab77e506278500e883c3006add72f897009f5e` | `6cbbf87f2f6cb2c918e489d74a75f1c6d7d723ec51318202a929f67f242c7a64` |

## RMST Tau Sensitivity

| Method | Tau fraction | Tau days | RMST delta days | RMST p |
| --- | ---: | ---: | ---: | ---: |
| maxstat | 0.75 | 1369.7 | 132 | 3.69e-04 |
| maxstat | 0.90 | 1643.6 | 189 | 8.84e-05 |
| maxstat | 1.00 | 1826.2 | 235 | 2.91e-05 |
| median | 0.75 | 1369.7 | 129 | 5.16e-04 |
| median | 0.90 | 1643.6 | 188 | 1.14e-04 |
| median | 1.00 | 1826.2 | 231 | 4.42e-05 |
| upper_quartile | 0.75 | 1369.7 | 99 | 0.010 |
| upper_quartile | 0.90 | 1643.6 | 138 | 0.007 |
| upper_quartile | 1.00 | 1826.2 | 170 | 0.004 |
| upper_lower_quartile | 0.75 | 1369.7 | 178 | 7.38e-04 |
| upper_lower_quartile | 0.90 | 1643.6 | 239 | 5.47e-04 |
| upper_lower_quartile | 1.00 | 1826.2 | 282 | 4.70e-04 |
