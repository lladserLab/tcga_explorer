# TCGA-LIHC CDC20 OS cutpoint benchmark

- Run started: 2026-07-25T17:57:45Z
- Run finished: 2026-07-25T17:57:45Z
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
- Cutpoint-independent continuous reference: n=365, events=130, HR per +1 SD=1.65 (1.38-1.98), linear p=6.71e-08, linear suite BH q=3.69e-07, events/parameter=130.0, nonlinearity p=0.389, nonlinearity suite BH q=0.697.

| Method | n | Events | Family p | Holm p | HR | Cox p | Adjusted HR | Adjusted p | Marker PH p | Global PH p | RMST delta @ tau | RMST p | Same-contrast HRs | Notes |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| maxstat | 365 | 130 | 5.61e-06 | 2.24e-05 | 2.60 (1.83-3.71) | 1.19e-07 | 2.66 (1.86-3.79) | 6.75e-08 | 0.008 | 0.016 | -251 @ 1091 | 5.65e-10 | grouped 2.60 vs continuous-implied 2.29; absolute log-HR ratio 1.15 | Marker-specific PH caution; Outcome-optimized cutpoint; grouped estimates are post-selection |
| median | 365 | 130 | 4.42e-05 | 7.37e-05 | 2.07 (1.45-2.96) | 6.41e-05 | 2.12 (1.48-3.03) | 4.00e-05 | 0.003 | 0.005 | -207 @ 1091 | 1.56e-07 | grouped 2.07 vs continuous-implied 2.28; absolute log-HR ratio 0.88 | Marker-specific PH caution |
| upper_quartile | 365 | 130 | 1.99e-05 | 5.98e-05 | 2.15 (1.50-3.09) | 3.10e-05 | 2.22 (1.54-3.18) | 1.62e-05 | 0.022 | 0.045 | -229 @ 1091 | 7.02e-06 | grouped 2.15 vs continuous-implied 2.38; absolute log-HR ratio 0.89 | Marker-specific PH caution |
| upper_lower_quartile | 184 | 70 | 3.69e-05 | 7.37e-05 | 2.74 (1.66-4.50) | 7.29e-05 | 2.76 (1.67-4.53) | 6.61e-05 | 2.79e-04 | 5.79e-04 | -315 @ 1091 | 6.63e-09 | grouped 2.74 vs continuous-implied 3.61; absolute log-HR ratio 0.78 | Marker-specific PH caution; Middle 50% excluded |

## Audit Hashes

| Method | Analysis ID | Reproducibility hash | Grouped records SHA-256 | Continuous records SHA-256 |
| --- | --- | --- | --- | --- |
| maxstat | `bc330e791a5f40559a7054d360d10d53` | `f675b0a99526785b44a17e50272de6a8b108b941d8faf724dcefd18323c182ef` | `e9b5dd93c1b51fd49b4137e7140cd7d3b780436090466c52779cc5210ae91424` | `92699d577a954fcdb1a1d1fee76b1cc0c6885d622b16bc20c0f7c1b470cbbc68` |
| median | `d7a5cea9a427469885f6534cc03678b2` | `21d6130e1dd31fb8d7823ac121f5a42ee6e96f334652d20eb619dc169790e1b7` | `00c81834894ccf66c1c4f72d70fa74fb9855d447bd813f05dc031517ab1eb8dc` | `92699d577a954fcdb1a1d1fee76b1cc0c6885d622b16bc20c0f7c1b470cbbc68` |
| upper_quartile | `ad50a8298d2749bdb24d826927375633` | `614322b33ae8a8e69cda54e4d08dad2d66cfd8e9a8a8284487b66af4d7a3eeb5` | `9c0911ad2ae366d874b36fe86c0be0f9ee4b9dc5d505343b78976e376158aeda` | `92699d577a954fcdb1a1d1fee76b1cc0c6885d622b16bc20c0f7c1b470cbbc68` |
| upper_lower_quartile | `4e04d51cde934d35bfdef83a925c1f85` | `d11cb19e41f5bf405413bf09d74990136edd384d08f25ceaa92f145763ce06c3` | `25239e5854fa7ad977aea4af169f4a3b70c8fc4cf9cfe7063c03233dfe68e572` | `92699d577a954fcdb1a1d1fee76b1cc0c6885d622b16bc20c0f7c1b470cbbc68` |

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
