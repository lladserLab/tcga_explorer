# TCGA-LUAD BIRC5 OS cutpoint benchmark

- Run started: 2026-07-25T17:49:17Z
- Run finished: 2026-07-25T17:49:31Z
- Completed analyses: 4/4
- Cached analyses in this run: 4/4
- API base URL: `http://192.168.1.31:3000/tcga_explorer`
- Cohort: `TCGA-LUAD`
- Gene: `BIRC5`
- Endpoint: `OS`
- Expression scale: `log2_tpm`
- Prespecified complete-case Cox adjustment: age_at_index.
- Grouped-test family: four prespecified two-group cutpoint sensitivities within this marker-endpoint scenario.
- Grouped multiplicity: Holm adjustment within this scenario. The maxstat member contributes its Lau94 selection-adjusted rank-statistic p-value; the other prespecified rules contribute their log-rank p-values.
- No composite retention rule is applied. Log-rank, Cox and RMST are related summaries of the same outcomes and are not counted as independent barriers.
- Marker-specific PH and global model PH are reported separately as interpretation diagnostics.
- Maxstat is outcome-optimized. Its corrected rank-statistic p-value is reported, while grouped HR, confidence intervals and RMST remain post-selection.
- Cutpoint-independent continuous reference: n=505, events=182, HR per +1 SD=1.34 (1.15-1.56), linear p=1.45e-04, linear suite BH q=3.18e-04, events/parameter=182.0, nonlinearity p=0.778, nonlinearity suite BH q=0.806.

| Method | n | Events | Family p | Holm p | HR | Cox p | Adjusted HR | Adjusted p | Marker PH p | Global PH p | RMST delta @ tau | RMST p | Same-contrast HRs | Notes |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| maxstat | 505 | 182 | 0.003 | 0.008 | 1.84 (1.37-2.47) | 4.97e-05 | 1.98 (1.46-2.67) | 9.09e-06 | 0.959 | 0.459 | -121 @ 1130 | 1.86e-04 | grouped 1.84 vs continuous-implied 1.61; absolute log-HR ratio 1.28 | Outcome-optimized cutpoint; grouped estimates are post-selection |
| median | 505 | 182 | 4.44e-04 | 0.002 | 1.70 (1.26-2.29) | 5.16e-04 | 1.80 (1.32-2.44) | 1.69e-04 | 0.678 | 0.434 | -107 @ 1130 | 7.69e-04 | grouped 1.70 vs continuous-implied 1.61; absolute log-HR ratio 1.11 | No model-diagnostic caution recorded |
| upper_quartile | 505 | 182 | 0.092 | 0.092 | 1.31 (0.96-1.80) | 0.093 | 1.39 (1.00-1.92) | 0.047 | 0.933 | 0.484 | -52 @ 1130 | 0.169 | grouped 1.31 vs continuous-implied 1.62; absolute log-HR ratio 0.56 | No model-diagnostic caution recorded |
| upper_lower_quartile | 254 | 89 | 0.004 | 0.008 | 1.88 (1.22-2.90) | 0.004 | 2.23 (1.42-3.50) | 5.11e-04 | 0.598 | 0.644 | -113 @ 1130 | 0.009 | grouped 1.88 vs continuous-implied 2.12; absolute log-HR ratio 0.84 | Middle 50% excluded |

## Audit Hashes

| Method | Analysis ID | Reproducibility hash | Grouped records SHA-256 | Continuous records SHA-256 |
| --- | --- | --- | --- | --- |
| maxstat | `916cac597df046bcb1374f03a1a28b5e` | `23b93be3e05aabd621c9348a7525ec5f5d5dcba957b3ee208069cb3b977dc4ad` | `abffbe9084b7670b472ae0e103ff8ae93b725ee152db50727e731b0e832e3a71` | `64f7bade8969c41af6bcf9618307d674c0218dd87be2f1b19d7b9c550fe44798` |
| median | `8e79747315f7438e9886ce171613f188` | `8117944da84aca2808ad43cd4fb149882fbd7fa3dc2c0e3be6fdcb4901a3df7d` | `68d540e9c910e99de28f922c4d2d5ec1fd60a1c95e476fa0edd40cd1467d7060` | `64f7bade8969c41af6bcf9618307d674c0218dd87be2f1b19d7b9c550fe44798` |
| upper_quartile | `29e0f29cd60042e88e2cee3eb8234372` | `35b4a6f374557f80e86a4b46bbec81f45adb4de05d13c39854b63b6185225023` | `7193610f00d9a7b27a081220e45fd2bc09a82dac0a16583b164c46ae60891ab7` | `64f7bade8969c41af6bcf9618307d674c0218dd87be2f1b19d7b9c550fe44798` |
| upper_lower_quartile | `165b12347d4b46d29485c464de05f7af` | `b918826a33d78f7cb6078903ffb8cba62ee781fd461d5469c2995b255009e434` | `88c0522a722c10e511ccaa6f819411b303f8164505bc6bffd406937c307a3dd3` | `64f7bade8969c41af6bcf9618307d674c0218dd87be2f1b19d7b9c550fe44798` |

## RMST Tau Sensitivity

| Method | Tau fraction | Tau days | RMST delta days | RMST p |
| --- | ---: | ---: | ---: | ---: |
| maxstat | 0.75 | 847.5 | -69 | 0.001 |
| maxstat | 0.90 | 1017.0 | -100 | 3.19e-04 |
| maxstat | 1.00 | 1130.0 | -121 | 1.86e-04 |
| median | 0.75 | 847.5 | -62 | 0.003 |
| median | 0.90 | 1017.0 | -88 | 0.001 |
| median | 1.00 | 1130.0 | -107 | 7.69e-04 |
| upper_quartile | 0.75 | 847.5 | -34 | 0.177 |
| upper_quartile | 0.90 | 1017.0 | -45 | 0.167 |
| upper_quartile | 1.00 | 1130.0 | -52 | 0.169 |
| upper_lower_quartile | 0.75 | 847.5 | -67 | 0.019 |
| upper_lower_quartile | 0.90 | 1017.0 | -94 | 0.011 |
| upper_lower_quartile | 1.00 | 1130.0 | -113 | 0.009 |
