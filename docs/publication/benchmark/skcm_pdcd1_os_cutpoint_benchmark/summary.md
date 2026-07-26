# TCGA-SKCM PDCD1 OS cutpoint benchmark

- Run started: 2026-07-26T17:23:40Z
- Run finished: 2026-07-26T17:23:55Z
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
| upper_lower_quartile | 228 | 110 | 2.24e-06 | 8.95e-06 | 0.40 (0.27-0.59) | 4.71e-06 | 0.41 (0.27-0.60) | 6.63e-06 | 0.044 | 0.127 | 412 @ 1826 | 3.11e-07 | grouped 0.40 vs continuous-implied 0.36; absolute log-HR ratio 0.90 | Marker-specific PH caution; fixed 2-year diagnostic estimated; Middle 50% excluded |

## Audit Hashes

| Method | Analysis ID | Reproducibility hash | Grouped records SHA-256 | Continuous records SHA-256 |
| --- | --- | --- | --- | --- |
| maxstat | `9a74dc9a4ed34034a49e80526010f041` | `bfe9514d56b21762cd65d0c326df3fd4776f7e36a42e0ec8e39744ea723365de` | `1c3a3423b0d191cfd025ce34198a6a3a8bc6a617960687733bb517b2c0d0a533` | `8de54e583e48968a8f86e7dc3bbf2a0e5a5532efb2d6605f1dd2d75595a9aef1` |
| median | `d328e03fed67419c95aa47cb21bc920f` | `f6e787e6ea6243ab3fa30cb3b58bd7d8a49d8b1b17046182e7c082b4db316994` | `6067197f80ccf38b41df194015e181370a1027bef07daafe5a22e048c21d3fd4` | `8de54e583e48968a8f86e7dc3bbf2a0e5a5532efb2d6605f1dd2d75595a9aef1` |
| upper_quartile | `51afabe0d7234bc188d2fd30a0868f38` | `b8e8c9ca82563b44e8600a9336ff94b4a7b9a4b2bd877d18401917d0fb7937dc` | `92e53da2827147051063f956ff5d9ebf7ae643c715bd98617a75d48cc0c058c7` | `8de54e583e48968a8f86e7dc3bbf2a0e5a5532efb2d6605f1dd2d75595a9aef1` |
| upper_lower_quartile | `c61437b0c49e4eb195194335e5abe42e` | `47f2843b5c6e7198b26452bc19cc50d30a277ee6f7ea34ddd79b9a5dcd785a14` | `0396e695b7105e8a053e3424bba8753c85c13591db5701aa69b9d2f22374adb2` | `8de54e583e48968a8f86e7dc3bbf2a0e5a5532efb2d6605f1dd2d75595a9aef1` |

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
