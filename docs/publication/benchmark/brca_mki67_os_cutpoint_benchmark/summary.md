# TCGA-BRCA MKI67 OS cutpoint benchmark

- Run started: 2026-07-26T17:22:57Z
- Run finished: 2026-07-26T17:23:15Z
- Completed analyses: 4/4
- Cached analyses in this run: 4/4
- API base URL: `http://192.168.1.31:3000/tcga_explorer`
- Cohort: `TCGA-BRCA`
- Gene: `MKI67`
- Endpoint: `OS`
- Expression scale: `log2_tpm`
- Prespecified complete-case Cox adjustment: age_at_index.
- Grouped-test family: four prespecified two-group cutpoint sensitivities within this marker-endpoint scenario.
- Grouped multiplicity: Holm adjustment within this scenario. The maxstat member contributes its Lau94 selection-adjusted rank-statistic p-value; the other prespecified rules contribute their log-rank p-values.
- No composite retention rule is applied. Log-rank, Cox and RMST are related summaries of the same outcomes and are not counted as independent barriers.
- Marker-specific PH and global model PH are reported separately as interpretation diagnostics.
- Maxstat is outcome-optimized. Its corrected rank-statistic p-value is reported, while grouped HR, confidence intervals and RMST remain post-selection.
- Cutpoint-independent continuous reference: n=1080, events=151, HR per +1 SD=1.09 (0.94-1.27), linear p=0.262, linear suite BH q=0.320, events/parameter=151.0, nonlinearity p=0.613, nonlinearity suite BH q=0.766.

| Method | n | Events | Family p | Holm p | HR | Cox p | Adjusted HR | Adjusted p | Marker PH p | Global PH p | RMST delta @ tau | RMST p | Same-contrast HRs | Notes |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| maxstat | 1080 | 151 | 1.000 | 1.000 | 1.37 (0.97-1.91) | 0.071 | 1.59 (1.13-2.24) | 0.008 | 0.510 | 0.688 | -46 @ 1688 | 0.116 | grouped 1.37 vs continuous-implied 1.16; absolute log-HR ratio 2.15 | Outcome-optimized cutpoint; grouped estimates are post-selection; Raw Lau94 approximation lay outside [0,1] and was clamped |
| median | 1080 | 151 | 0.583 | 1.000 | 1.09 (0.79-1.51) | 0.583 | 1.27 (0.92-1.76) | 0.148 | 0.683 | 0.814 | -18 @ 1688 | 0.448 | grouped 1.09 vs continuous-implied 1.15; absolute log-HR ratio 0.65 | No model-diagnostic caution recorded |
| upper_quartile | 1080 | 151 | 0.112 | 0.447 | 1.32 (0.94-1.86) | 0.113 | 1.53 (1.08-2.16) | 0.017 | 0.203 | 0.334 | -51 @ 1688 | 0.086 | grouped 1.32 vs continuous-implied 1.16; absolute log-HR ratio 1.91 | No model-diagnostic caution recorded |
| upper_lower_quartile | 540 | 88 | 0.342 | 1.000 | 1.23 (0.81-1.86) | 0.343 | 1.47 (0.95-2.26) | 0.082 | 0.607 | 0.839 | -40 @ 1688 | 0.259 | grouped 1.23 vs continuous-implied 1.25; absolute log-HR ratio 0.92 | Middle 50% excluded |

## Audit Hashes

| Method | Analysis ID | Reproducibility hash | Grouped records SHA-256 | Continuous records SHA-256 |
| --- | --- | --- | --- | --- |
| maxstat | `a49de47d9368495da6a8126d3997400e` | `bca5b5baa85bc43a1cc50020e61f89942ad721609a796990d5772768c9ba590c` | `d221f53d45601540365c77a03595ca9e448a2ddafab2b9e3b6a3ebc4ca654078` | `030a82e9c3af33ee8cac435f397a36a96bedb5d3f00ea3315fb927f4ba7283ce` |
| median | `a059e21e415c4ce8a565a96db5b24673` | `ff25caa17208d52c928de0393d33a10ff28c6094ad9c45279cf545128599a6e6` | `d52483abb1b8ac131fad3908ba29696c35637ca2bcb14ca5067c8c36338bfcd6` | `030a82e9c3af33ee8cac435f397a36a96bedb5d3f00ea3315fb927f4ba7283ce` |
| upper_quartile | `195e0420654b437a8a428177007faa24` | `f4f680790ab1523534d5530fc49a33f5ab4ee64bf5c039424b15407473519176` | `3d3bb5f808026b070f3a4059fc766590c920c7495b7d9ddd2bf298611bbca6be` | `030a82e9c3af33ee8cac435f397a36a96bedb5d3f00ea3315fb927f4ba7283ce` |
| upper_lower_quartile | `8206064153c6481b83a6bd6ccefe1e5c` | `c3d1caf3f201c109f79ffb3f0d60b015435d4de33617dcdf40b7de825e912593` | `312cc55a21e3235d8caea28e43d44a4128bc8928645f677527a2f879d4f7a6c5` | `030a82e9c3af33ee8cac435f397a36a96bedb5d3f00ea3315fb927f4ba7283ce` |

## RMST Tau Sensitivity

| Method | Tau fraction | Tau days | RMST delta days | RMST p |
| --- | ---: | ---: | ---: | ---: |
| maxstat | 0.75 | 1266.0 | -26 | 0.130 |
| maxstat | 0.90 | 1519.2 | -37 | 0.122 |
| maxstat | 1.00 | 1688.0 | -46 | 0.116 |
| median | 0.75 | 1266.0 | -4 | 0.747 |
| median | 0.90 | 1519.2 | -11 | 0.579 |
| median | 1.00 | 1688.0 | -18 | 0.448 |
| upper_quartile | 0.75 | 1266.0 | -28 | 0.100 |
| upper_quartile | 0.90 | 1519.2 | -41 | 0.092 |
| upper_quartile | 1.00 | 1688.0 | -51 | 0.086 |
| upper_lower_quartile | 0.75 | 1266.0 | -16 | 0.451 |
| upper_lower_quartile | 0.90 | 1519.2 | -28 | 0.342 |
| upper_lower_quartile | 1.00 | 1688.0 | -40 | 0.259 |
