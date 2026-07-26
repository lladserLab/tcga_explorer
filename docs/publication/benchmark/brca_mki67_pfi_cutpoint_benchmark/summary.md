# TCGA-BRCA MKI67 PFI cutpoint benchmark

- Run started: 2026-07-26T17:23:17Z
- Run finished: 2026-07-26T17:23:38Z
- Completed analyses: 4/4
- Cached analyses in this run: 4/4
- API base URL: `http://192.168.1.31:3000/tcga_explorer`
- Cohort: `TCGA-BRCA`
- Gene: `MKI67`
- Endpoint: `PFI`
- Expression scale: `log2_tpm`
- Prespecified complete-case Cox adjustment: age_at_index.
- Grouped-test family: four prespecified two-group cutpoint sensitivities within this marker-endpoint scenario.
- Grouped multiplicity: Holm adjustment within this scenario. The maxstat member contributes its Lau94 selection-adjusted rank-statistic p-value; the other prespecified rules contribute their log-rank p-values.
- No composite retention rule is applied. Log-rank, Cox and RMST are related summaries of the same outcomes and are not counted as independent barriers.
- Marker-specific PH and global model PH are reported separately as interpretation diagnostics.
- Maxstat is outcome-optimized. Its corrected rank-statistic p-value is reported, while grouped HR, confidence intervals and RMST remain post-selection.
- Cutpoint-independent continuous reference: n=1080, events=145, HR per +1 SD=1.16 (0.99-1.35), linear p=0.074, linear suite BH q=0.117, events/parameter=145.0, nonlinearity p=0.029, nonlinearity suite BH q=0.144.

| Method | n | Events | Family p | Holm p | HR | Cox p | Adjusted HR | Adjusted p | Marker PH p | Global PH p | RMST delta @ tau | RMST p | Same-contrast HRs | Notes |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| maxstat | 1080 | 145 | 0.098 | 0.391 | 2.40 (1.33-4.34) | 0.004 | 2.45 (1.35-4.43) | 0.003 | 0.548 | 0.025 | -82 @ 1598 | 0.002 | grouped 2.40 vs continuous-implied 1.31; absolute log-HR ratio 3.21 | Global PH caution; marker term not flagged; Outcome-optimized cutpoint; grouped estimates are post-selection |
| median | 1080 | 145 | 0.215 | 0.430 | 1.23 (0.89-1.71) | 0.216 | 1.25 (0.90-1.74) | 0.188 | 0.790 | 0.013 | -32 @ 1598 | 0.203 | grouped 1.23 vs continuous-implied 1.26; absolute log-HR ratio 0.90 | Global PH caution; marker term not flagged |
| upper_quartile | 1080 | 145 | 0.384 | 0.430 | 1.17 (0.82-1.69) | 0.385 | 1.19 (0.82-1.71) | 0.356 | 0.292 | 0.005 | -31 @ 1598 | 0.302 | grouped 1.17 vs continuous-implied 1.27; absolute log-HR ratio 0.66 | Global PH caution; marker term not flagged |
| upper_lower_quartile | 540 | 71 | 0.131 | 0.394 | 1.43 (0.90-2.30) | 0.133 | 1.32 (0.81-2.13) | 0.261 | 0.726 | 0.085 | -39 @ 1598 | 0.264 | grouped 1.43 vs continuous-implied 1.44; absolute log-HR ratio 0.98 | Middle 50% excluded |

## Audit Hashes

| Method | Analysis ID | Reproducibility hash | Grouped records SHA-256 | Continuous records SHA-256 |
| --- | --- | --- | --- | --- |
| maxstat | `1f3150636f7644d78e3f08e7d5cd2912` | `ad540188a75545c1fab55fd3ba38002fb94e3bf9a769f9170e60dae74517d3cf` | `a76183a1c098fa693c0448b6c8ab5d1c53d1f1fd425373a2d77c32a6c91f3890` | `00f9071ce0f20b5b9b56ec684c3e788fe9d32f067dfc1467b9ca1626b8286aaf` |
| median | `cc8c70ee05f34de984ee34e70e2765c5` | `a0d7d28ca675720a998e8293c73fee2cf89ac44faebf76635b75eca53ea0f164` | `5dd50bd7259f41ca9f04a054077e598058b6ed88401a99022cf088838bef396e` | `00f9071ce0f20b5b9b56ec684c3e788fe9d32f067dfc1467b9ca1626b8286aaf` |
| upper_quartile | `17e167ddad104d10a926e28b1b6cebf5` | `1e5dd0b08ee10dcaf22399144c0409649d3b14bef0f933e96056d51170c4f33a` | `2d4364b08978d11756781debd70a3ad7850727fa41a1436c8ae57fbc272f4e86` | `00f9071ce0f20b5b9b56ec684c3e788fe9d32f067dfc1467b9ca1626b8286aaf` |
| upper_lower_quartile | `3fd003c626584f7f8cf2d2b7886f4b97` | `23636c625fbc62ef49172d246881d733ae4aa688bf4843ae7d2faf95fc866669` | `0d56338e68bcd75f9b73ac93e946e0209fc2028b2a8a69279091b5cae671f3fc` | `00f9071ce0f20b5b9b56ec684c3e788fe9d32f067dfc1467b9ca1626b8286aaf` |

## RMST Tau Sensitivity

| Method | Tau fraction | Tau days | RMST delta days | RMST p |
| --- | ---: | ---: | ---: | ---: |
| maxstat | 0.75 | 1198.5 | -46 | 0.003 |
| maxstat | 0.90 | 1438.2 | -67 | 0.002 |
| maxstat | 1.00 | 1598.0 | -82 | 0.002 |
| median | 0.75 | 1198.5 | -14 | 0.351 |
| median | 0.90 | 1438.2 | -25 | 0.220 |
| median | 1.00 | 1598.0 | -32 | 0.203 |
| upper_quartile | 0.75 | 1198.5 | -12 | 0.505 |
| upper_quartile | 0.90 | 1438.2 | -22 | 0.365 |
| upper_quartile | 1.00 | 1598.0 | -31 | 0.302 |
| upper_lower_quartile | 0.75 | 1198.5 | -14 | 0.529 |
| upper_lower_quartile | 0.90 | 1438.2 | -28 | 0.337 |
| upper_lower_quartile | 1.00 | 1598.0 | -39 | 0.264 |
