# TCGA-LUAD CD274 PFI cutpoint benchmark

- Run started: 2026-07-26T17:24:30Z
- Run finished: 2026-07-26T17:24:47Z
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
- Cutpoint-independent continuous reference: n=505, events=208, HR per +1 SD=1.04 (0.91-1.19), linear p=0.530, linear suite BH q=0.530, events/parameter=208.0, nonlinearity p=0.444, nonlinearity suite BH q=0.739.

| Method | n | Events | Family p | Holm p | HR | Cox p | Adjusted HR | Adjusted p | Marker PH p | Global PH p | RMST delta @ tau | RMST p | Same-contrast HRs | Notes |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| maxstat | 505 | 208 | 0.958 | 1.000 | 1.38 (1.05-1.83) | 0.023 | 1.35 (1.02-1.79) | 0.036 | 0.813 | 0.393 | -60 @ 896 | 0.034 | grouped 1.38 vs continuous-implied 1.07; absolute log-HR ratio 4.62 | Outcome-optimized cutpoint; grouped estimates are post-selection |
| median | 505 | 208 | 0.695 | 1.000 | 1.06 (0.80-1.39) | 0.695 | 1.03 (0.78-1.35) | 0.852 | 0.907 | 0.384 | -15 @ 896 | 0.580 | grouped 1.06 vs continuous-implied 1.07; absolute log-HR ratio 0.83 | No model-diagnostic caution recorded |
| upper_quartile | 505 | 208 | 0.228 | 0.911 | 1.21 (0.89-1.63) | 0.228 | 1.18 (0.87-1.60) | 0.289 | 0.805 | 0.388 | -33 @ 896 | 0.290 | grouped 1.21 vs continuous-implied 1.08; absolute log-HR ratio 2.41 | No model-diagnostic caution recorded |
| upper_lower_quartile | 254 | 117 | 0.580 | 1.000 | 1.11 (0.77-1.60) | 0.580 | 1.08 (0.74-1.56) | 0.692 | 0.604 | 0.833 | -19 @ 896 | 0.624 | grouped 1.11 vs continuous-implied 1.11; absolute log-HR ratio 0.97 | Middle 50% excluded |

## Audit Hashes

| Method | Analysis ID | Reproducibility hash | Grouped records SHA-256 | Continuous records SHA-256 |
| --- | --- | --- | --- | --- |
| maxstat | `be21def70f354c20b628986ed324661c` | `838e21cde51b03c1304919463f515444b0e10dcb222fe4b32853b1d2b6ac96fd` | `d80de0d7d64a14cea813d74e9d33db592fc8fb2f0e4a637bf6f71e4e0afa8a0b` | `42ec1741534bc4d3a942242e91bbb957773a0fe2c5ebd63fca387e5dcf371aeb` |
| median | `1cfb2ab03e5c4c15ad753375c3ebc67f` | `869ceae86254d194c65f9f500ee4a836497ca2e94c2180e4cfac57d8e9e0b177` | `c9a89879603a278f9de7c931a115aeb08593ca587ad147894aa7c0bda8a5c383` | `42ec1741534bc4d3a942242e91bbb957773a0fe2c5ebd63fca387e5dcf371aeb` |
| upper_quartile | `fb0b9aa68aab435face5fceece7ebf80` | `a1258d8a87b0b752741f170ff6e588e7ef04a3ee73bb5156e19a560dcea054d9` | `0ac1239bb3c128fe4102a362c5517292813d8eefcf72a0bcd6b281a84609e1a5` | `42ec1741534bc4d3a942242e91bbb957773a0fe2c5ebd63fca387e5dcf371aeb` |
| upper_lower_quartile | `f821fee6c516495c97e98071128be847` | `b7411b3b7bb90da816445bd263174699db2109ee44cb5859f858559b4669f44c` | `e9faccd5821137f95cdf3e21624a89897bf19d0a83e0d5c0319446abe7a9f3cc` | `42ec1741534bc4d3a942242e91bbb957773a0fe2c5ebd63fca387e5dcf371aeb` |

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
