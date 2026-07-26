# TCGA-KIRC CA9 OS cutpoint benchmark

- Run started: 2026-07-25T17:50:00Z
- Run finished: 2026-07-25T17:50:15Z
- Completed analyses: 4/4
- Cached analyses in this run: 4/4
- API base URL: `http://192.168.1.31:3000/tcga_explorer`
- Cohort: `TCGA-KIRC`
- Gene: `CA9`
- Endpoint: `OS`
- Expression scale: `log2_tpm`
- Prespecified complete-case Cox adjustment: age_at_index.
- Grouped-test family: four prespecified two-group cutpoint sensitivities within this marker-endpoint scenario.
- Grouped multiplicity: Holm adjustment within this scenario. The maxstat member contributes its Lau94 selection-adjusted rank-statistic p-value; the other prespecified rules contribute their log-rank p-values.
- No composite retention rule is applied. Log-rank, Cox and RMST are related summaries of the same outcomes and are not counted as independent barriers.
- Marker-specific PH and global model PH are reported separately as interpretation diagnostics.
- Maxstat is outcome-optimized. Its corrected rank-statistic p-value is reported, while grouped HR, confidence intervals and RMST remain post-selection.
- Cutpoint-independent continuous reference: n=531, events=175, HR per +1 SD=0.91 (0.79-1.04), linear p=0.168, linear suite BH q=0.231, events/parameter=175.0, nonlinearity p=0.002, nonlinearity suite BH q=0.012.

| Method | n | Events | Family p | Holm p | HR | Cox p | Adjusted HR | Adjusted p | Marker PH p | Global PH p | RMST delta @ tau | RMST p | Same-contrast HRs | Notes |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| maxstat | 531 | 175 | 0.032 | 0.096 | 0.59 (0.44-0.80) | 5.69e-04 | 0.63 (0.46-0.85) | 0.003 | 0.756 | 0.676 | 158 @ 1826 | 0.008 | grouped 0.59 vs continuous-implied 0.88; absolute log-HR ratio 4.14 | Outcome-optimized cutpoint; grouped estimates are post-selection |
| median | 531 | 175 | 0.013 | 0.050 | 0.68 (0.51-0.92) | 0.013 | 0.70 (0.52-0.95) | 0.023 | 0.579 | 0.595 | 107 @ 1826 | 0.044 | grouped 0.68 vs continuous-implied 0.90; absolute log-HR ratio 3.81 | No model-diagnostic caution recorded |
| upper_quartile | 531 | 175 | 0.355 | 0.355 | 0.84 (0.59-1.21) | 0.355 | 0.89 (0.62-1.28) | 0.527 | 0.102 | 0.198 | 1 @ 1826 | 0.986 | grouped 0.84 vs continuous-implied 0.92; absolute log-HR ratio 1.94 | No model-diagnostic caution recorded |
| upper_lower_quartile | 266 | 93 | 0.043 | 0.096 | 0.65 (0.43-0.99) | 0.044 | 0.69 (0.45-1.05) | 0.083 | 0.398 | 0.416 | 112 @ 1826 | 0.163 | grouped 0.65 vs continuous-implied 0.84; absolute log-HR ratio 2.43 | Middle 50% excluded |

## Audit Hashes

| Method | Analysis ID | Reproducibility hash | Grouped records SHA-256 | Continuous records SHA-256 |
| --- | --- | --- | --- | --- |
| maxstat | `053fb6c068114e84bedb441888354156` | `449d5d0031c6e521edb2d70129d96c9af1384b9974cc088ad2f39a9d3ce8364b` | `0da5fb68c5a7e856ba3aa7a18bc28409839b0513a72ba29e09eb526732b457c8` | `1ed8fa5ba2d6766798c853a1ff6b07c6e2f5e1afad90161d10cf978bcb14e645` |
| median | `9281f0877ce24ce79d683a0c0a19f07c` | `7d3ca49db684f5331b52b132c5bcf064a3240e877dc05094e041a236e4c83585` | `a9b9a351f99ebd870c6a006a8bacc5eb6441ca1887dac24e3bbf0358dad9e2c3` | `1ed8fa5ba2d6766798c853a1ff6b07c6e2f5e1afad90161d10cf978bcb14e645` |
| upper_quartile | `bbf9d53e9aeb4f3791d7f9cbdf15ff18` | `2ed2d90a7cc778317c1b91d3cbfffdb9deef1f696c0d8c9abaf0678bf7bed771` | `0a2c44bc407d3eff84b0af36df0f7d2f69d1b71f0455f6f0639ecc61dd91671a` | `1ed8fa5ba2d6766798c853a1ff6b07c6e2f5e1afad90161d10cf978bcb14e645` |
| upper_lower_quartile | `32edc41140c94990b365778df554981c` | `676e5f375e2db092763130f890ce0f1c818d5cdce05c6e9fcc26a164f062f1b5` | `461ab898759ce9fe1cca5b5be07b5d551e5d5aba2c2fe70089444d28ab0dc8b0` | `1ed8fa5ba2d6766798c853a1ff6b07c6e2f5e1afad90161d10cf978bcb14e645` |

## RMST Tau Sensitivity

| Method | Tau fraction | Tau days | RMST delta days | RMST p |
| --- | ---: | ---: | ---: | ---: |
| maxstat | 0.75 | 1369.7 | 97 | 0.018 |
| maxstat | 0.90 | 1643.6 | 127 | 0.015 |
| maxstat | 1.00 | 1826.2 | 158 | 0.008 |
| median | 0.75 | 1369.7 | 59 | 0.102 |
| median | 0.90 | 1643.6 | 85 | 0.067 |
| median | 1.00 | 1826.2 | 107 | 0.044 |
| upper_quartile | 0.75 | 1369.7 | -7 | 0.874 |
| upper_quartile | 0.90 | 1643.6 | -4 | 0.942 |
| upper_quartile | 1.00 | 1826.2 | 1 | 0.986 |
| upper_lower_quartile | 0.75 | 1369.7 | 65 | 0.239 |
| upper_lower_quartile | 0.90 | 1643.6 | 89 | 0.204 |
| upper_lower_quartile | 1.00 | 1826.2 | 112 | 0.163 |
