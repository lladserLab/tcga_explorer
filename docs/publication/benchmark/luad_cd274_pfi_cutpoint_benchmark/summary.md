# TCGA-LUAD CD274 PFI cutpoint benchmark

- Run started: 2026-07-25T17:51:40Z
- Run finished: 2026-07-25T17:51:54Z
- Completed analyses: 4/4
- Cached analyses in this run: 4/4
- API base URL: `http://192.168.1.31:3000/tcga_explorer`
- Cohort: `TCGA-LUAD`
- Gene: `CD274`
- Endpoint: `PFI`
- Expression scale: `log2_tpm`
- Prespecified complete-case Cox adjustment: age_at_index.
- Grouped-test family: four prespecified two-group cutpoint sensitivities within this marker-endpoint scenario.
- Grouped multiplicity: Holm adjustment within this scenario. The maxstat member contributes its Lau94 selection-adjusted rank-statistic p-value; the other prespecified rules contribute their log-rank p-values.
- No composite retention rule is applied. Log-rank, Cox and RMST are related summaries of the same outcomes and are not counted as independent barriers.
- Marker-specific PH and global model PH are reported separately as interpretation diagnostics.
- Maxstat is outcome-optimized. Its corrected rank-statistic p-value is reported, while grouped HR, confidence intervals and RMST remain post-selection.
- Cutpoint-independent continuous reference: n=505, events=208, HR per +1 SD=1.04 (0.91-1.19), linear p=0.530, linear suite BH q=0.530, events/parameter=208.0, nonlinearity p=0.444, nonlinearity suite BH q=0.697.

| Method | n | Events | Family p | Holm p | HR | Cox p | Adjusted HR | Adjusted p | Marker PH p | Global PH p | RMST delta @ tau | RMST p | Same-contrast HRs | Notes |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| maxstat | 505 | 208 | 0.958 | 1.000 | 1.38 (1.05-1.83) | 0.023 | 1.35 (1.02-1.79) | 0.036 | 0.813 | 0.393 | -60 @ 896 | 0.034 | grouped 1.38 vs continuous-implied 1.07; absolute log-HR ratio 4.62 | Outcome-optimized cutpoint; grouped estimates are post-selection |
| median | 505 | 208 | 0.695 | 1.000 | 1.06 (0.80-1.39) | 0.695 | 1.03 (0.78-1.35) | 0.852 | 0.907 | 0.384 | -15 @ 896 | 0.580 | grouped 1.06 vs continuous-implied 1.07; absolute log-HR ratio 0.83 | No model-diagnostic caution recorded |
| upper_quartile | 505 | 208 | 0.228 | 0.911 | 1.21 (0.89-1.63) | 0.228 | 1.18 (0.87-1.60) | 0.289 | 0.805 | 0.388 | -33 @ 896 | 0.290 | grouped 1.21 vs continuous-implied 1.08; absolute log-HR ratio 2.41 | No model-diagnostic caution recorded |
| upper_lower_quartile | 254 | 117 | 0.580 | 1.000 | 1.11 (0.77-1.60) | 0.580 | 1.08 (0.74-1.56) | 0.692 | 0.604 | 0.833 | -19 @ 896 | 0.624 | grouped 1.11 vs continuous-implied 1.11; absolute log-HR ratio 0.97 | Middle 50% excluded |

## Audit Hashes

| Method | Analysis ID | Reproducibility hash | Grouped records SHA-256 | Continuous records SHA-256 |
| --- | --- | --- | --- | --- |
| maxstat | `3ef9f4ad4e8445cc9fb87f35ea07604a` | `42e56eb7981a82dcc69b2dd20b8da5326e7856d0640be5904a19bbd6a9874c61` | `755e18eb96d8482775ca62357ac70edc8b2513987d54780a62c98d11ddd3d9f1` | `b436e2c5d973b365c6b4f86792ba19233bf5510a7c94700f898de2299db095ec` |
| median | `17fd9170df814b2081a045faeba24f99` | `f122ad52a6db97be51493c909e153813a4ae88d733534b9bba99c516e640990b` | `6612a6f24b1c9fbd144e67939efa7400f0e1154e62634591ac41664c1c8657d5` | `b436e2c5d973b365c6b4f86792ba19233bf5510a7c94700f898de2299db095ec` |
| upper_quartile | `c3ee68ab925a4df2a5175ab46d7cb945` | `62797a689d0f354c1407c784f157d26bd245ba4b8e32b6070b4ab5950e879210` | `186bd366d7530128319e528b63a285ce8a00e1c9b38499c914a214ecd7eedac1` | `b436e2c5d973b365c6b4f86792ba19233bf5510a7c94700f898de2299db095ec` |
| upper_lower_quartile | `fbbeba99a65f4109bffeb0119373e081` | `c642b23ff3c1ae471b888c5fe6428cb3e1378a591820a0b7ddb80f41f0fe921b` | `a406b54c846adb96a4abd396dcda7d06a73523b8d559cbfc60c35822d9401920` | `b436e2c5d973b365c6b4f86792ba19233bf5510a7c94700f898de2299db095ec` |

## RMST Tau Sensitivity

| Method | Tau fraction | Tau days | RMST delta days | RMST p |
| --- | ---: | ---: | ---: | ---: |
| maxstat | 0.75 | 672.0 | -34 | 0.068 |
| maxstat | 0.90 | 806.4 | -50 | 0.039 |
| maxstat | 1.00 | 896.0 | -60 | 0.034 |
| median | 0.75 | 672.0 | -8 | 0.643 |
| median | 0.90 | 806.4 | -13 | 0.559 |
| median | 1.00 | 896.0 | -15 | 0.580 |
| upper_quartile | 0.75 | 672.0 | -21 | 0.310 |
| upper_quartile | 0.90 | 806.4 | -30 | 0.262 |
| upper_quartile | 1.00 | 896.0 | -33 | 0.290 |
| upper_lower_quartile | 0.75 | 672.0 | -8 | 0.755 |
| upper_lower_quartile | 0.90 | 806.4 | -16 | 0.623 |
| upper_lower_quartile | 1.00 | 896.0 | -19 | 0.624 |
