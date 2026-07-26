# TCGA-LUAD BIRC5 OS cutpoint benchmark

- Run started: 2026-07-26T17:21:52Z
- Run finished: 2026-07-26T17:22:07Z
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
| maxstat | `bd7c1c832a884717ae80e8afd3ff4ba5` | `24228a1cc123659280ebc4c5f447b2440e11b76c81c323f7f48e90ab0fd00eef` | `4b63d0e531395c3598fd1703c03967ce8773c592d6fd9b82e89c857d627059b1` | `c1afda70940b24aaf6e1bbf735cb360ec40cd1d044b5b7f4981e564df00ad811` |
| median | `d98baf45611546b8aac4dc194dfcfc49` | `15cb91d899384b32f52a9adb3ae0ea7b4c3742b590ba9043b4e83d60e3eb6e78` | `31f35c313f095b0e2db6d630c1c09d326483759bd7df9bea168856560605487d` | `c1afda70940b24aaf6e1bbf735cb360ec40cd1d044b5b7f4981e564df00ad811` |
| upper_quartile | `3b949660f7384b3a941d6469bd080d3b` | `eef20eaca930e62aab9b1a3b091ad8a3d7e74638f2d4734962d7356aebd83a33` | `48d71803ac77b79dc10fab51973677755f7106b9b39cd7965ff3bf69591f38b6` | `c1afda70940b24aaf6e1bbf735cb360ec40cd1d044b5b7f4981e564df00ad811` |
| upper_lower_quartile | `b784569c8a8a45579e66b319dce67e7b` | `51e1b1ab345a7c959ea84dde9445197c6ed92623d96d295e64b39fd93b87a0d8` | `8f8b5e671a8bccdea4b3a48e145e0add00e5eb94ee48d937a21b7c99830efe82` | `c1afda70940b24aaf6e1bbf735cb360ec40cd1d044b5b7f4981e564df00ad811` |

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
