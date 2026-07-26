# TCGA-UVM BAP1 DSS cutpoint benchmark

- Run started: 2026-07-26T17:22:09Z
- Run finished: 2026-07-26T17:22:21Z
- Completed analyses: 4/4
- Cached analyses in this run: 4/4
- API base URL: `http://192.168.1.31:3000/tcga_explorer`
- Cohort: `TCGA-UVM`
- Gene: `BAP1`
- Endpoint: `DSS`
- Expression scale: `log2_tpm`
- Prespecified complete-case Cox adjustment: age_at_index.
- Grouped-test family: four prespecified two-group cutpoint sensitivities within this marker-endpoint scenario.
- Grouped multiplicity: Holm adjustment within this scenario. The maxstat member contributes its Lau94 selection-adjusted rank-statistic p-value; the other prespecified rules contribute their log-rank p-values.
- No composite retention rule is applied. Log-rank, Cox and RMST are related summaries of the same outcomes and are not counted as independent barriers.
- Marker-specific PH and global model PH are reported separately as interpretation diagnostics.
- Maxstat is outcome-optimized. Its corrected rank-statistic p-value is reported, while grouped HR, confidence intervals and RMST remain post-selection.
- Cutpoint-independent continuous reference: n=80, events=21, HR per +1 SD=0.51 (0.35-0.74), linear p=3.73e-04, linear suite BH q=6.84e-04, events/parameter=21.0, nonlinearity p=, nonlinearity suite BH q=.

| Method | n | Events | Family p | Holm p | HR | Cox p | Adjusted HR | Adjusted p | Marker PH p | Global PH p | RMST delta @ tau | RMST p | Same-contrast HRs | Notes |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| maxstat | 80 | 21 | 7.65e-05 | 3.06e-04 |  |  |  |  |  |  | 299 @ 1180 | 7.79e-07 | not estimable | Standard adjusted Cox failed; Outcome-optimized cutpoint; grouped estimates are post-selection; Firth adjusted sensitivity HR 0.02 (0.00-0.17), p 8.91e-07 |
| median | 80 | 21 | 3.09e-04 | 6.17e-04 | 0.17 (0.06-0.50) | 0.001 | 0.18 (0.06-0.55) | 0.003 | 0.514 | 0.210 | 224 @ 1180 | 0.004 | grouped 0.17 vs continuous-implied 0.34; absolute log-HR ratio 1.64 | No model-diagnostic caution recorded |
| upper_quartile | 80 | 21 | 0.002 | 0.002 |  |  |  |  |  |  | 245 @ 1180 | 2.90e-06 | not estimable | Standard adjusted Cox failed; Firth adjusted sensitivity HR 0.05 (0.00-0.40), p 6.98e-04 |
| upper_lower_quartile | 40 | 10 | 1.82e-04 | 5.46e-04 |  |  |  |  |  |  | 262 @ 1180 | 0.004 | not estimable | Standard adjusted Cox failed; Middle 50% excluded; Adjusted Cox 5.0 events/parameter (caution); Firth adjusted sensitivity HR 0.03 (0.00-0.22), p 6.13e-05 |

## Audit Hashes

| Method | Analysis ID | Reproducibility hash | Grouped records SHA-256 | Continuous records SHA-256 |
| --- | --- | --- | --- | --- |
| maxstat | `83f8945bff354463b529e911c03416d2` | `f3d01334aa95c288efc5620f8f3923547873754e49ca5e55ceb1f3dd3b0f7783` | `b40a24f4d822c97a5dd4186097a5812429582ace4da59563750859fb79e29d91` | `0abcacbf745a623cca266a6d5332d9d3f3dfdf16860c1d30db64bc6b0b81f6f7` |
| median | `3695c8ead2134ecb9b2d10c72544c19e` | `6549cad343a51ba60d02e661f2b1d1e4afec7fc6593a9ec406eae0ebafbd9117` | `5658ae22404e8795fac4721f6d5a3335097a1ab8fd41243b111371e5466bff3b` | `0abcacbf745a623cca266a6d5332d9d3f3dfdf16860c1d30db64bc6b0b81f6f7` |
| upper_quartile | `148cee800ea544d6ace2b43aa45f1233` | `6df06fb2c0f4ae4818cf9f84e31cfb935e4a922ab710ca0e6c7a3a2dab797511` | `e184225550e6b7416f86cafc94ad43733f8dd603444ad71a37adea780efb5636` | `0abcacbf745a623cca266a6d5332d9d3f3dfdf16860c1d30db64bc6b0b81f6f7` |
| upper_lower_quartile | `135e413c6d0c46acaafaf55b65219349` | `d4f837a128509aad039b90a8383b3ef6ad1d52b72ff1b5ac83c545e072e68d41` | `48d97d6460b739e49fcf1b302d60cd7f6f37a9192440f959486a54f462a6c5f6` | `0abcacbf745a623cca266a6d5332d9d3f3dfdf16860c1d30db64bc6b0b81f6f7` |

## RMST Tau Sensitivity

| Method | Tau fraction | Tau days | RMST delta days | RMST p |
| --- | ---: | ---: | ---: | ---: |
| maxstat | 0.75 | 884.6 | 168 | 4.34e-05 |
| maxstat | 0.90 | 1061.5 | 244 | 3.52e-06 |
| maxstat | 1.00 | 1179.5 | 299 | 7.79e-07 |
| median | 0.75 | 884.6 | 122 | 0.019 |
| median | 0.90 | 1061.5 | 179 | 0.007 |
| median | 1.00 | 1179.5 | 224 | 0.004 |
| upper_quartile | 0.75 | 884.6 | 138 | 8.38e-05 |
| upper_quartile | 0.90 | 1061.5 | 200 | 9.75e-06 |
| upper_quartile | 1.00 | 1179.5 | 245 | 2.90e-06 |
| upper_lower_quartile | 0.75 | 884.6 | 142 | 0.023 |
| upper_lower_quartile | 0.90 | 1061.5 | 209 | 0.009 |
| upper_lower_quartile | 1.00 | 1179.5 | 262 | 0.004 |

## Low-information and Firth Sensitivities

| Method | Model family | Events / parameter | Information status | Firth HR (95% CI) | Firth p | Ties |
| --- | --- | ---: | --- | ---: | ---: | --- |
| maxstat | Grouped adjusted | 10.5 | adequate | 0.02 (0.00-0.17) | 8.91e-07 | breslow |
| upper_quartile | Grouped adjusted | 10.5 | adequate | 0.05 (0.00-0.40) | 6.98e-04 | breslow |
| upper_lower_quartile | Grouped adjusted | 5.0 | caution | 0.03 (0.00-0.22) | 6.13e-05 | breslow |
