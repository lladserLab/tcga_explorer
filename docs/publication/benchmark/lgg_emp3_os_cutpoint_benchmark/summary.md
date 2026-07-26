# TCGA-LGG EMP3 OS cutpoint benchmark

- Run started: 2026-07-25T23:06:04Z
- Run finished: 2026-07-25T23:06:04Z
- Completed analyses: 4/4
- Cached analyses in this run: 4/4
- API base URL: `http://backend:8000`
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
- Cutpoint-independent continuous reference: n=511, events=125, HR per +1 SD=2.54 (2.15-3.00), linear p=3.09e-28, linear suite BH q=3.40e-27, events/parameter=125.0, nonlinearity p=0.400, nonlinearity suite BH q=0.697.

| Method | n | Events | Family p | Holm p | HR | Cox p | Adjusted HR | Adjusted p | Marker PH p | Global PH p | RMST delta @ tau | RMST p | Same-contrast HRs | Notes |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| maxstat | 511 | 125 | 3.48e-23 | 1.39e-22 | 11.07 (7.53-16.26) | 1.75e-34 | 8.92 (5.91-13.47) | 1.87e-25 | 0.103 | 0.082 | -514 @ 1224 | 2.65e-30 | grouped 11.07 vs continuous-implied 7.94; absolute log-HR ratio 1.16 | Outcome-optimized cutpoint; grouped estimates are post-selection |
| median | 511 | 125 | 2.95e-09 | 2.95e-09 | 2.98 (2.04-4.34) | 1.52e-08 | 2.55 (1.74-3.74) | 1.49e-06 | 0.003 | 1.94e-04 | -217 @ 1224 | 1.45e-13 | grouped 2.98 vs continuous-implied 3.94; absolute log-HR ratio 0.80 | Marker-specific PH caution; fixed 2-year diagnostic estimated |
| upper_quartile | 511 | 125 | 1.46e-19 | 4.38e-19 | 4.49 (3.15-6.40) | 1.09e-16 | 3.82 (2.66-5.48) | 4.27e-13 | 3.45e-04 | 1.01e-04 | -361 @ 1224 | 1.70e-17 | grouped 4.49 vs continuous-implied 6.44; absolute log-HR ratio 0.81 | Marker-specific PH caution; fixed 2-year diagnostic estimated |
| upper_lower_quartile | 256 | 77 | 5.61e-13 | 1.12e-12 | 6.50 (3.63-11.64) | 3.01e-10 | 5.37 (2.96-9.76) | 3.35e-08 | 0.006 | 0.005 | -390 @ 1224 | 1.31e-19 | grouped 6.50 vs continuous-implied 9.86; absolute log-HR ratio 0.82 | Marker-specific PH caution; fixed 2-year diagnostic estimated; Middle 50% excluded |

## Audit Hashes

| Method | Analysis ID | Reproducibility hash | Grouped records SHA-256 | Continuous records SHA-256 |
| --- | --- | --- | --- | --- |
| maxstat | `66347acbabaf491a8c6a81cb16685c02` | `4835cb9d3f82a6593b131f1ca6bd7f523427175c00426bb437f8b6cdabb71eea` | `5bd88b6ca2636ac11d5b55b1c0a016be75fe9c7805a070f9db12fa341b5d01b9` | `3e77f1b8e5e52ba81e0044ae53aad96a740bfe0f115b7fc102433275059bba5c` |
| median | `bcfb57edcb024261a6d654e9de77daa1` | `5eda31dbd0c70812a118ab50ee48d0f08206e05aee33cdb5d98aed3241d671ac` | `69aa49322719127a5d7c4459795ec234669b3d402b71793179670033fdffaf91` | `3e77f1b8e5e52ba81e0044ae53aad96a740bfe0f115b7fc102433275059bba5c` |
| upper_quartile | `bbb2ebb5ff6049569f3e9c70c11f8e63` | `872afb72204d70b1fc99282b321d62d7d27cee1f79e0d29489d734054270f1cc` | `3afd4df092241d0e0065a1eb8590d40871a92f0ca33b33febafc8a5f762e68f4` | `3e77f1b8e5e52ba81e0044ae53aad96a740bfe0f115b7fc102433275059bba5c` |
| upper_lower_quartile | `3086f6911ad54610871ee22e967fba72` | `bb5faa477b71f9b25dc5e6b3c6a4021c1515d4d02e30d9276f7abf222df9b74e` | `fa095347382256fa873693c9fbe39c1931c0633820333b3343608dc251da8e2f` | `3e77f1b8e5e52ba81e0044ae53aad96a740bfe0f115b7fc102433275059bba5c` |

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
