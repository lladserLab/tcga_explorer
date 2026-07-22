# TCGA-BRCA MKI67 OS cutpoint benchmark

- Run started: 2026-07-22T15:53:58Z
- Run finished: 2026-07-22T15:53:58Z
- Completed analyses: 5/5
- Cached analyses in this run: 5/5
- API base URL: `http://localhost:3000/tcga_explorer`
- Cohort: `TCGA-BRCA`
- Gene: `MKI67`
- Endpoint: `OS`
- Expression scale: `log2_tpm`
- Decision rule: BH log-rank, univariable Cox, adjusted Cox and RMST p <= 0.05; adjusted PH global p not flagged.

| Method | n | Events | BH log-rank | HR | Cox p | Adjusted p | PH global p | RMST delta days | RMST p | Survives |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| maxstat | 1080 | 151 | 0.186 | 1.37 (0.97-1.91) | 0.071 | 0.220 | 0.012 | -317 | 0.564 | no (Fails BH) |
| median | 1080 | 151 | 0.583 | 1.09 (0.79-1.51) | 0.583 | 0.692 | 0.014 | 128 | 0.810 | no (Fails BH) |
| upper_quartile | 1080 | 151 | 0.186 | 1.32 (0.94-1.86) | 0.113 | 0.100 | 0.009 | 52 | 0.925 | no (Fails BH) |
| upper_lower_quartile | 540 | 88 | 0.428 | 1.23 (0.81-1.86) | 0.343 | 0.356 | 0.019 | 70 | 0.920 | no (Fails BH) |
| percentile | 1080 | 151 | 0.186 | 1.32 (0.94-1.86) | 0.113 | 0.100 | 0.009 | 52 | 0.925 | no (Fails BH) |

## Audit Hashes

| Method | Analysis ID | Reproducibility hash | Patient records SHA-256 |
| --- | --- | --- | --- |
| maxstat | `4be6812717f94531a3b785844e1b736d` | `efb1dc2062249f204d99766a18e439dce961552f7634222956c20b0d6f380134` | `55a40b65054ac2fcdd3d04cb55cef33ae4270a612835b89f855950f94c6ff105` |
| median | `15db273fce1d42758984d277593477fe` | `d0b9cf1f667c14176cfa4403fa1dd1948d36bed8152cdb73f9a7fb478c593b16` | `ce86109f60a1eebb4eca6e0c0c9c1010aa64c7639023ea07edce5792b2b0de7c` |
| upper_quartile | `7e7ce12a6bfb411ea2636f5bc93f298e` | `3ba23f43b19b59879a3008379842a4d462bdb8648fdcf8025a8b146ad78c78e4` | `04a0aec756aa56dac56f214201ef07d052003564745cff2ffcad57873eb35792` |
| upper_lower_quartile | `8cf3592264f548cda786554592b3e5fa` | `a3ce6218262888ad48b302029b0b4c15b7c1d0fe056adaed103d8ff42ed40781` | `9bce461bb8413d5f551da57e74bcf263b5671d5b6eeb413d538cf22d226b9249` |
| percentile | `7a32bc94d041467c977d882599932026` | `c54171b8153581a707d3b48611a4d8ff21f811931d6ae343ccae4045f572485e` | `3a5b27c62e90d866ce5b6d732182a656183b5b1a132bdad5e49d3d99fc05f1a8` |
