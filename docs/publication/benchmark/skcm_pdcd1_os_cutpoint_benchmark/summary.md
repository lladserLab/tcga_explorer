# TCGA-SKCM PDCD1 OS cutpoint benchmark

- Run started: 2026-07-25T17:50:54Z
- Run finished: 2026-07-25T17:51:08Z
- Completed analyses: 4/4
- Cached analyses in this run: 4/4
- API base URL: `http://192.168.1.31:3000/tcga_explorer`
- Cohort: `TCGA-SKCM`
- Gene: `PDCD1`
- Endpoint: `OS`
- Expression scale: `log2_tpm`
- Prespecified complete-case Cox adjustment: age_at_index.
- Grouped-test family: four prespecified two-group cutpoint sensitivities within this marker-endpoint scenario.
- Grouped multiplicity: Holm adjustment within this scenario. The maxstat member contributes its Lau94 selection-adjusted rank-statistic p-value; the other prespecified rules contribute their log-rank p-values.
- No composite retention rule is applied. Log-rank, Cox and RMST are related summaries of the same outcomes and are not counted as independent barriers.
- Marker-specific PH and global model PH are reported separately as interpretation diagnostics.
- Maxstat is outcome-optimized. Its corrected rank-statistic p-value is reported, while grouped HR, confidence intervals and RMST remain post-selection.
- Cutpoint-independent continuous reference: n=453, events=213, HR per +1 SD=0.67 (0.58-0.78), linear p=1.27e-07, linear suite BH q=4.67e-07, events/parameter=213.0, nonlinearity p=0.806, nonlinearity suite BH q=0.806.

| Method | n | Events | Family p | Holm p | HR | Cox p | Adjusted HR | Adjusted p | Marker PH p | Global PH p | RMST delta @ tau | RMST p | Same-contrast HRs | Notes |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| maxstat | 453 | 213 | 1.98e-05 | 3.97e-05 | 0.49 (0.37-0.64) | 3.22e-07 | 0.51 (0.39-0.67) | 1.50e-06 | 0.561 | 0.812 | 253 @ 1826 | 9.93e-06 | grouped 0.49 vs continuous-implied 0.51; absolute log-HR ratio 1.06 | Outcome-optimized cutpoint; grouped estimates are post-selection |
| median | 453 | 213 | 3.16e-06 | 9.48e-06 | 0.53 (0.40-0.69) | 4.59e-06 | 0.55 (0.42-0.72) | 2.02e-05 | 0.795 | 0.925 | 218 @ 1826 | 1.20e-04 | grouped 0.53 vs continuous-implied 0.51; absolute log-HR ratio 0.95 | No model-diagnostic caution recorded |
| upper_quartile | 453 | 213 | 0.003 | 0.003 | 0.60 (0.42-0.84) | 0.003 | 0.60 (0.43-0.85) | 0.003 | 0.280 | 0.524 | 182 @ 1826 | 0.002 | grouped 0.60 vs continuous-implied 0.48; absolute log-HR ratio 0.71 | No model-diagnostic caution recorded |
| upper_lower_quartile | 228 | 110 | 2.24e-06 | 8.95e-06 | 0.40 (0.27-0.59) | 4.71e-06 | 0.41 (0.27-0.60) | 6.63e-06 | 0.044 | 0.127 | 412 @ 1826 | 3.11e-07 | grouped 0.40 vs continuous-implied 0.36; absolute log-HR ratio 0.90 | Marker-specific PH caution; Middle 50% excluded |

## Audit Hashes

| Method | Analysis ID | Reproducibility hash | Grouped records SHA-256 | Continuous records SHA-256 |
| --- | --- | --- | --- | --- |
| maxstat | `83b425379674497daf7c9f792584c156` | `190d8cf04e42ed6bd616533cfa6682dfc8366ddc3d0858cfb24c31b364f6f93f` | `28e6cd05e0632ff26314c578df961fe5608b5751f48df782cd41f6250d64b423` | `8927efdcba6c46f1a92af1d4c6a8b5f84c8cf64767ee5fa374329c0c95ba5fe4` |
| median | `50587193715341759cf0b4b765583abb` | `c41dcfa4afe2ccdfb33dcf884018e3a4078ec4085cc6861d86b94e73d2d2f185` | `8dab9305760c2f2c0afa6c671ddba73a73391ddbcef59e866749bf4efe7faa7a` | `8927efdcba6c46f1a92af1d4c6a8b5f84c8cf64767ee5fa374329c0c95ba5fe4` |
| upper_quartile | `b1d67a9458ce424d9c15144cc3ffa2e9` | `73af1b32aae200ecea1a0f6a8b4e64a2f69b901b40a68bac0bfc4f6cbb25a0c5` | `1785225745d6c4518918b9a8d221e27364cc1b9ebe0e5ef6ad91774cc5af358f` | `8927efdcba6c46f1a92af1d4c6a8b5f84c8cf64767ee5fa374329c0c95ba5fe4` |
| upper_lower_quartile | `05b621f857b848c68f396208cf332785` | `b26f36da8d6fb5f7aca8ee012cf2d9a625532d2e5359f1e83cdd776369227d75` | `9c078ea9d2532bce09a8ab9322ccd36e5d1e9da440aec60c2d439a4c41eedbc6` | `8927efdcba6c46f1a92af1d4c6a8b5f84c8cf64767ee5fa374329c0c95ba5fe4` |

## RMST Tau Sensitivity

| Method | Tau fraction | Tau days | RMST delta days | RMST p |
| --- | ---: | ---: | ---: | ---: |
| maxstat | 0.75 | 1369.7 | 150 | 7.61e-05 |
| maxstat | 0.90 | 1643.6 | 208 | 2.62e-05 |
| maxstat | 1.00 | 1826.2 | 253 | 9.93e-06 |
| median | 0.75 | 1369.7 | 130 | 4.72e-04 |
| median | 0.90 | 1643.6 | 178 | 2.67e-04 |
| median | 1.00 | 1826.2 | 218 | 1.20e-04 |
| upper_quartile | 0.75 | 1369.7 | 112 | 0.003 |
| upper_quartile | 0.90 | 1643.6 | 149 | 0.003 |
| upper_quartile | 1.00 | 1826.2 | 182 | 0.002 |
| upper_lower_quartile | 0.75 | 1369.7 | 260 | 1.37e-06 |
| upper_lower_quartile | 0.90 | 1643.6 | 345 | 7.56e-07 |
| upper_lower_quartile | 1.00 | 1826.2 | 412 | 3.11e-07 |
