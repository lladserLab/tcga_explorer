# TCGA-LGG EMP3 OS cutpoint benchmark

- Run started: 2026-07-26T17:22:23Z
- Run finished: 2026-07-26T17:22:38Z
- Completed analyses: 4/4
- Cached analyses in this run: 4/4
- API base URL: `http://192.168.1.31:3000/tcga_explorer`
- Cohort: `TCGA-LGG`
- Gene: `EMP3`
- Endpoint: `OS`
- Expression scale: `log2_tpm`
- Prespecified complete-case Cox adjustment: age_at_index.
- Grouped-test family: four prespecified two-group cutpoint sensitivities within this marker-endpoint scenario.
- Grouped multiplicity: Holm adjustment within this scenario. The maxstat member contributes its Lau94 selection-adjusted rank-statistic p-value; the other prespecified rules contribute their log-rank p-values.
- No composite retention rule is applied. Log-rank, Cox and RMST are related summaries of the same outcomes and are not counted as independent barriers.
- Marker-specific PH and global model PH are reported separately as interpretation diagnostics.
- Maxstat is outcome-optimized. Its corrected rank-statistic p-value is reported, while grouped HR, confidence intervals and RMST remain post-selection.
- Cutpoint-independent continuous reference: n=511, events=125, HR per +1 SD=2.54 (2.15-3.00), linear p=3.09e-28, linear suite BH q=3.40e-27, events/parameter=125.0, nonlinearity p=0.400, nonlinearity suite BH q=0.739.

| Method | n | Events | Family p | Holm p | HR | Cox p | Adjusted HR | Adjusted p | Marker PH p | Global PH p | RMST delta @ tau | RMST p | Same-contrast HRs | Notes |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| maxstat | 511 | 125 | 3.48e-23 | 1.39e-22 | 11.07 (7.53-16.26) | 1.75e-34 | 8.92 (5.91-13.47) | 1.87e-25 | 0.103 | 0.082 | -514 @ 1224 | 2.65e-30 | grouped 11.07 vs continuous-implied 7.94; absolute log-HR ratio 1.16 | Outcome-optimized cutpoint; grouped estimates are post-selection |
| median | 511 | 125 | 2.95e-09 | 2.95e-09 | 2.98 (2.04-4.34) | 1.52e-08 | 2.55 (1.74-3.74) | 1.49e-06 | 0.003 | 1.94e-04 | -217 @ 1224 | 1.45e-13 | grouped 2.98 vs continuous-implied 3.94; absolute log-HR ratio 0.80 | Marker-specific PH caution; fixed 2-year diagnostic estimated |
| upper_quartile | 511 | 125 | 1.46e-19 | 4.38e-19 | 4.49 (3.15-6.40) | 1.09e-16 | 3.82 (2.66-5.48) | 4.27e-13 | 3.45e-04 | 1.01e-04 | -361 @ 1224 | 1.70e-17 | grouped 4.49 vs continuous-implied 6.44; absolute log-HR ratio 0.81 | Marker-specific PH caution; fixed 2-year diagnostic estimated |
| upper_lower_quartile | 256 | 77 | 5.61e-13 | 1.12e-12 | 6.50 (3.63-11.64) | 3.01e-10 | 5.37 (2.96-9.76) | 3.35e-08 | 0.006 | 0.005 | -390 @ 1224 | 1.31e-19 | grouped 6.50 vs continuous-implied 9.86; absolute log-HR ratio 0.82 | Marker-specific PH caution; fixed 2-year diagnostic estimated; Middle 50% excluded |

## Audit Hashes

| Method | Analysis ID | Reproducibility hash | Grouped records SHA-256 | Continuous records SHA-256 |
| --- | --- | --- | --- | --- |
| maxstat | `c0a2c18a93754c8ba116ba1131d8fa9a` | `dc2cc7bff3eb603a1ad822dafa32746b1857d16fcc38188c2fd455137c349401` | `924327ef395b8af90c3bfa73b5b92237f721263c1484f3a20b605565380be6f6` | `28dd953e96544fb5da47ae594e113b8cb9a92b80917df28f2dff5da734bcd7f3` |
| median | `ce6d6105174e4d4c8da9af1aee3cce80` | `d68560523f32ee9a97c5517b3fed1717cf672499277a5988ec83579649d1f58c` | `fa11d995c2ebd0746df30cf6e3d1159d4e76f29ac6f37e09f41b477d905da14e` | `28dd953e96544fb5da47ae594e113b8cb9a92b80917df28f2dff5da734bcd7f3` |
| upper_quartile | `49530f34215944a982612d1248e567fa` | `c5ec71746e77ad855cd40b2feccf705626fd24300eb27bcecdd473fdc992fa4b` | `17440a05988a9e05cb903e28fddd777529a3b14a4bc9e4a33253017fcd7063ce` | `28dd953e96544fb5da47ae594e113b8cb9a92b80917df28f2dff5da734bcd7f3` |
| upper_lower_quartile | `6c2eeef0412049fe8ffe7ab503a54d0b` | `4ae35ffdd38e0c60aa7c3656cc6be7210341dfb9839d63625c39dd8a15b22779` | `256ddb34ed9046b49a99b3b49cbcde884de27081ca09ac2de828035cb1bbbb29` | `28dd953e96544fb5da47ae594e113b8cb9a92b80917df28f2dff5da734bcd7f3` |

## RMST Tau Sensitivity

| Method | Tau fraction | Tau days | RMST delta days | RMST p |
| --- | ---: | ---: | ---: | ---: |
| maxstat | 0.75 | 918.4 | -302 | 1.64e-21 |
| maxstat | 0.90 | 1102.0 | -429 | 2.23e-27 |
| maxstat | 1.00 | 1224.5 | -514 | 2.65e-30 |
| median | 0.75 | 918.4 | -127 | 2.97e-12 |
| median | 0.90 | 1102.0 | -179 | 3.92e-13 |
| median | 1.00 | 1224.5 | -217 | 1.45e-13 |
| upper_quartile | 0.75 | 918.4 | -219 | 2.03e-15 |
| upper_quartile | 0.90 | 1102.0 | -305 | 3.92e-17 |
| upper_quartile | 1.00 | 1224.5 | -361 | 1.70e-17 |
| upper_lower_quartile | 0.75 | 918.4 | -232 | 6.16e-17 |
| upper_lower_quartile | 0.90 | 1102.0 | -325 | 6.55e-19 |
| upper_lower_quartile | 1.00 | 1224.5 | -390 | 1.31e-19 |
