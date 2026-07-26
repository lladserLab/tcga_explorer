# TCGA-SKCM TMEM176B OS cutpoint benchmark

- Run started: 2026-07-26T17:23:57Z
- Run finished: 2026-07-26T17:24:11Z
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
- Cutpoint-independent continuous reference: n=453, events=213, HR per +1 SD=0.77 (0.67-0.87), linear p=7.09e-05, linear suite BH q=1.95e-04, events/parameter=213.0, nonlinearity p=0.100, nonlinearity suite BH q=0.333.

| Method | n | Events | Family p | Holm p | HR | Cox p | Adjusted HR | Adjusted p | Marker PH p | Global PH p | RMST delta @ tau | RMST p | Same-contrast HRs | Notes |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| maxstat | 453 | 213 | 5.66e-05 | 1.70e-04 | 0.50 (0.38-0.66) | 1.02e-06 | 0.52 (0.39-0.68) | 3.41e-06 | 0.837 | 0.965 | 235 @ 1826 | 2.91e-05 | grouped 0.50 vs continuous-implied 0.65; absolute log-HR ratio 1.60 | Outcome-optimized cutpoint; grouped estimates are post-selection |
| median | 453 | 213 | 1.32e-06 | 5.27e-06 | 0.51 (0.39-0.68) | 2.00e-06 | 0.54 (0.41-0.71) | 9.67e-06 | 0.913 | 0.983 | 231 @ 1826 | 4.42e-05 | grouped 0.51 vs continuous-implied 0.65; absolute log-HR ratio 1.54 | No model-diagnostic caution recorded |
| upper_quartile | 453 | 213 | 9.72e-04 | 9.72e-04 | 0.58 (0.42-0.81) | 0.001 | 0.60 (0.43-0.83) | 0.002 | 0.919 | 0.975 | 170 @ 1826 | 0.004 | grouped 0.58 vs continuous-implied 0.64; absolute log-HR ratio 1.20 | No model-diagnostic caution recorded |
| upper_lower_quartile | 228 | 111 | 1.91e-04 | 3.83e-04 | 0.49 (0.34-0.72) | 2.56e-04 | 0.50 (0.34-0.73) | 3.22e-04 | 0.539 | 0.815 | 282 @ 1826 | 4.70e-04 | grouped 0.49 vs continuous-implied 0.51; absolute log-HR ratio 1.04 | Middle 50% excluded |

## Audit Hashes

| Method | Analysis ID | Reproducibility hash | Grouped records SHA-256 | Continuous records SHA-256 |
| --- | --- | --- | --- | --- |
| maxstat | `24bd253e2de245d89ed1c6be215a2a69` | `70a5250cab743839a9530ea20fbabc5a7512ea0aa431da0ecae2d3891951ba16` | `5cf6c8d46e3ffa923661bfbd15b4b27df855606c8224ac996f6dbd4ce7b35e84` | `1623741dfec1f7f9c53ee2be9ae9e5a2afddf1b947187f120b39acf9cba7f5b0` |
| median | `15c679d8b41b4e7485b683a77838b757` | `191809395137b92fba2e5ec865d6f86df13d3b90fdb78d6503aeb68e8ad4e8d9` | `d91c403810bcd89d1f7c0388003ea2be2b56c057566542e8733ce2533e427bc1` | `1623741dfec1f7f9c53ee2be9ae9e5a2afddf1b947187f120b39acf9cba7f5b0` |
| upper_quartile | `fb3d3fc8ab2c4b94b4e48f11767beda0` | `9bf46c64b196373b13fbb7294d0daafa1583aa9e62290781a3ec3d4c41d41e59` | `4949184a1afbf7a88e8a19140cf71f03c24782fd4e68f88cfe4c68c8b587063f` | `1623741dfec1f7f9c53ee2be9ae9e5a2afddf1b947187f120b39acf9cba7f5b0` |
| upper_lower_quartile | `a790be15d4b4418e9eb5d90031d2fd2c` | `b22c013cad78a71f7bb0743eb54f33d98bc72c1169e4198362988bfe774a524b` | `08d94951c9845bcfe8672e13c14aa0d145ee0caf4b28ffff4583acf1c9facad3` | `1623741dfec1f7f9c53ee2be9ae9e5a2afddf1b947187f120b39acf9cba7f5b0` |

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
