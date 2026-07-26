# TCGA-LIHC CDC20 OS cutpoint benchmark

- Run started: 2026-07-26T17:21:35Z
- Run finished: 2026-07-26T17:21:50Z
- Completed analyses: 4/4
- Cached analyses in this run: 4/4
- API base URL: `http://192.168.1.31:3000/tcga_explorer`
- Cohort: `TCGA-LIHC`
- Gene: `CDC20`
- Endpoint: `OS`
- Expression scale: `log2_tpm`
- Prespecified complete-case Cox adjustment: age_at_index.
- Grouped-test family: four prespecified two-group cutpoint sensitivities within this marker-endpoint scenario.
- Grouped multiplicity: Holm adjustment within this scenario. The maxstat member contributes its Lau94 selection-adjusted rank-statistic p-value; the other prespecified rules contribute their log-rank p-values.
- No composite retention rule is applied. Log-rank, Cox and RMST are related summaries of the same outcomes and are not counted as independent barriers.
- Marker-specific PH and global model PH are reported separately as interpretation diagnostics.
- Maxstat is outcome-optimized. Its corrected rank-statistic p-value is reported, while grouped HR, confidence intervals and RMST remain post-selection.
- Cutpoint-independent continuous reference: n=365, events=130, HR per +1 SD=1.65 (1.38-1.98), linear p=6.71e-08, linear suite BH q=3.69e-07, events/parameter=130.0, nonlinearity p=0.389, nonlinearity suite BH q=0.739.

| Method | n | Events | Family p | Holm p | HR | Cox p | Adjusted HR | Adjusted p | Marker PH p | Global PH p | RMST delta @ tau | RMST p | Same-contrast HRs | Notes |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| maxstat | 365 | 130 | 5.61e-06 | 2.24e-05 | 2.60 (1.83-3.71) | 1.19e-07 | 2.66 (1.86-3.79) | 6.75e-08 | 0.008 | 0.016 | -251 @ 1091 | 5.65e-10 | grouped 2.60 vs continuous-implied 2.29; absolute log-HR ratio 1.15 | Marker-specific PH caution; fixed 2-year diagnostic estimated; Outcome-optimized cutpoint; grouped estimates are post-selection |
| median | 365 | 130 | 4.42e-05 | 7.37e-05 | 2.07 (1.45-2.96) | 6.41e-05 | 2.12 (1.48-3.03) | 4.00e-05 | 0.003 | 0.005 | -207 @ 1091 | 1.56e-07 | grouped 2.07 vs continuous-implied 2.28; absolute log-HR ratio 0.88 | Marker-specific PH caution; fixed 2-year diagnostic estimated |
| upper_quartile | 365 | 130 | 1.99e-05 | 5.98e-05 | 2.15 (1.50-3.09) | 3.10e-05 | 2.22 (1.54-3.18) | 1.62e-05 | 0.022 | 0.045 | -229 @ 1091 | 7.02e-06 | grouped 2.15 vs continuous-implied 2.38; absolute log-HR ratio 0.89 | Marker-specific PH caution; fixed 2-year diagnostic estimated |
| upper_lower_quartile | 184 | 70 | 3.69e-05 | 7.37e-05 | 2.74 (1.66-4.50) | 7.29e-05 | 2.76 (1.67-4.53) | 6.61e-05 | 2.79e-04 | 5.79e-04 | -315 @ 1091 | 6.63e-09 | grouped 2.74 vs continuous-implied 3.61; absolute log-HR ratio 0.78 | Marker-specific PH caution; fixed 2-year diagnostic estimated; Middle 50% excluded |

## Audit Hashes

| Method | Analysis ID | Reproducibility hash | Grouped records SHA-256 | Continuous records SHA-256 |
| --- | --- | --- | --- | --- |
| maxstat | `abc80569c2f845fa8e0c312f872e097b` | `3aa8771ec332bd3691b153b84205b63e3d9d8380e09cf3abc20e7e474d25cef6` | `a5603a6366f160024536d7e081544c4a53edc63a0532c456d1bb57d76e186d2f` | `e84887dd6900726a93270b21394036677d5cfdeb822da5a1ed6f5beb4ccaf7ec` |
| median | `5bc89f4c26934a34a9c6238898436b4b` | `d5a8381b32f22e23600927c0ad679efbe9af283d009431a6c39e394b0a5a685d` | `2949504726de52ea346d244a8e8a04a4b9cb7724c131df7509043d09faba015c` | `e84887dd6900726a93270b21394036677d5cfdeb822da5a1ed6f5beb4ccaf7ec` |
| upper_quartile | `222caadc15d141deab95f8fa72072c16` | `6e4429684b272c0f75f397d5c9b19ec6a62af2e9ad91de20893d9079c8bdc8a8` | `862006efd2b6653eeeae44fe0b02dce601d938ecf03d1628b1348ecc0cc1d74f` | `e84887dd6900726a93270b21394036677d5cfdeb822da5a1ed6f5beb4ccaf7ec` |
| upper_lower_quartile | `0e7210e46f6742b08632288f4e20a563` | `1d986674fdc93e26441abbb7c9a3c9d6fcdb7d7a7aa1a35ca37bcd596535f972` | `7616ee32a4ac7f22571c1dea692b682701d19788afd00a0e1a46008d7455f273` | `e84887dd6900726a93270b21394036677d5cfdeb822da5a1ed6f5beb4ccaf7ec` |

## RMST Tau Sensitivity

| Method | Tau fraction | Tau days | RMST delta days | RMST p |
| --- | ---: | ---: | ---: | ---: |
| maxstat | 0.75 | 818.2 | -170 | 6.73e-10 |
| maxstat | 0.90 | 981.9 | -219 | 4.86e-10 |
| maxstat | 1.00 | 1091.0 | -251 | 5.65e-10 |
| median | 0.75 | 818.2 | -142 | 1.09e-07 |
| median | 0.90 | 981.9 | -181 | 1.15e-07 |
| median | 1.00 | 1091.0 | -207 | 1.56e-07 |
| upper_quartile | 0.75 | 818.2 | -155 | 1.31e-05 |
| upper_quartile | 0.90 | 981.9 | -198 | 9.18e-06 |
| upper_quartile | 1.00 | 1091.0 | -229 | 7.02e-06 |
| upper_lower_quartile | 0.75 | 818.2 | -208 | 3.11e-08 |
| upper_lower_quartile | 0.90 | 981.9 | -271 | 1.14e-08 |
| upper_lower_quartile | 1.00 | 1091.0 | -315 | 6.63e-09 |
