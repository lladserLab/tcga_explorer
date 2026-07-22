# TCGA-SKCM PDCD1 OS cutpoint benchmark

- Run started: 2026-07-22T15:53:59Z
- Run finished: 2026-07-22T15:53:59Z
- Completed analyses: 5/5
- Cached analyses in this run: 5/5
- API base URL: `http://localhost:3000/tcga_explorer`
- Cohort: `TCGA-SKCM`
- Gene: `PDCD1`
- Endpoint: `OS`
- Expression scale: `log2_tpm`
- Decision rule: BH log-rank, univariable Cox, adjusted Cox and RMST p <= 0.05; adjusted PH global p not flagged.

| Method | n | Events | BH log-rank | HR | Cox p | Adjusted p | PH global p | RMST delta days | RMST p | Survives |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| maxstat | 453 | 213 | 9.14e-07 | 0.49 (0.37-0.64) | 3.22e-07 | 0.011 | 0.281 | 2139 | 4.88e-05 | yes |
| median | 453 | 213 | 5.27e-06 | 0.53 (0.40-0.69) | 4.59e-06 | 0.094 | 0.492 | 2027 | 1.55e-04 | no (Fails adjusted) |
| upper_quartile | 453 | 213 | 0.003 | 0.60 (0.42-0.84) | 0.003 | 0.132 | 0.558 | 1129 | 0.003 | no (Fails adjusted) |
| upper_lower_quartile | 228 | 110 | 5.27e-06 | 0.40 (0.27-0.59) | 4.71e-06 | 7.12e-04 | 0.259 | 1858 | 3.51e-05 | yes |
| percentile | 453 | 213 | 0.002 | 0.58 (0.41-0.82) | 0.002 | 0.078 | 0.576 | 1175 | 0.002 | no (Fails adjusted) |

## Audit Hashes

| Method | Analysis ID | Reproducibility hash | Patient records SHA-256 |
| --- | --- | --- | --- |
| maxstat | `a6722eae34534123a2c0c5a7f4fa7b0d` | `e919531471394f6d589684e67049cb27e3c99a6265aa948a6e40ace1a0b99102` | `94272b1e2b8061832073d15d8ec4e3efaa4d96bd8721dafa17467eb93fcd2786` |
| median | `ec8919ffb9d94c308753736f44e17535` | `b13e0c116700794165e0cf08f7b41be2a2b047e9ce68a346248fd0154745aac6` | `fc9d634383f80f9023079f423877641e969fab44d578bc567bcedff9da6179c7` |
| upper_quartile | `9d60f4623d0f4bc6961c7129fc382424` | `0575c14cec851c865d9937dc043f13a2461bf01194d38ff2cfa5a87f9b32d6c9` | `678d8eb3452501271d47ed033bfde8d0f4151d9ea1ca90d64181eac24de132fb` |
| upper_lower_quartile | `7affe013a00d427eb90d5c236d6a5457` | `ab6fd31ed2bbc613c56b78cf483ecaf31849c200ea61c89fcdcb4018f6a75e33` | `7f17d00c55655bc2e6d37fb2c9b78d5724e859e457f6a7c90982138a8344fe79` |
| percentile | `1ec1d757d53d40809267164a358995d3` | `fc6cf218c4bd1e9ed12f49e1b3dbc9aee60a5f64ffc3e1d9428cba026ea32997` | `ca9f9562fffc37056210cb8af29321bd9e35b4b8c0c05fa78e6970292c18949f` |
