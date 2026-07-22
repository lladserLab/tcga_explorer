# TCGA-LUAD CD274 OS cutpoint benchmark

- Run started: 2026-07-22T15:53:59Z
- Run finished: 2026-07-22T15:53:59Z
- Completed analyses: 5/5
- Cached analyses in this run: 5/5
- API base URL: `http://localhost:3000/tcga_explorer`
- Cohort: `TCGA-LUAD`
- Gene: `CD274`
- Endpoint: `OS`
- Expression scale: `log2_tpm`
- Decision rule: BH log-rank, univariable Cox, adjusted Cox and RMST p <= 0.05; adjusted PH global p not flagged.

| Method | n | Events | BH log-rank | HR | Cox p | Adjusted p | PH global p | RMST delta days | RMST p | Survives |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| maxstat | 505 | 182 | 0.334 | 1.42 (0.97-2.08) | 0.068 | 0.251 | 0.168 | -282 | 0.094 | no (Fails BH) |
| median | 505 | 182 | 0.962 | 0.99 (0.74-1.33) | 0.962 | 0.651 | 0.164 | -9 | 0.985 | no (Fails BH) |
| upper_quartile | 505 | 182 | 0.605 | 1.16 (0.84-1.61) | 0.364 | 0.495 | 0.162 | -230 | 0.252 | no (Fails BH) |
| upper_lower_quartile | 254 | 103 | 0.962 | 1.06 (0.72-1.56) | 0.771 | 0.978 | 0.125 | -155 | 0.514 | no (Fails BH) |
| percentile | 505 | 182 | 0.605 | 1.17 (0.85-1.63) | 0.336 | 0.431 | 0.165 | -237 | 0.237 | no (Fails BH) |

## Audit Hashes

| Method | Analysis ID | Reproducibility hash | Patient records SHA-256 |
| --- | --- | --- | --- |
| maxstat | `18e136960cc24ce8b275cb5a3a67d899` | `c282368859ee26f7da026d39c39f403902b3d94012039dbfb074be2625cd18c4` | `b317f077ef8118f3718058e593e868bdd88eddc98559fc3dbad6e70f9d4888ba` |
| median | `366571f2fb17476a986e0b70b552cd1b` | `ca8eb394563f5049399a4a0d73207e2783b00f52a3fd9e426f73a5ed8d3faeb2` | `9c7181bd82f70168fd3598ed668b6b1ffaa166092ee55b62e3d5cb8c8aa6950d` |
| upper_quartile | `cd4d4dec5bde4e10b96cd0dfdaeca19a` | `5e296e67a14dcf5e13e4582814e57d6bc59c00ae182b47ab78645fa3bb784231` | `9a0ddb70ea9724445b2a5055d01ede8cfe43dc9628a6abced6c1895db986ab15` |
| upper_lower_quartile | `04f3ee3bc856426889d21ab9e94290fa` | `3d421a63f74c74bfad5db261b35e4915790c4c9a31d5b34970c4e22bf884aaf5` | `521788826642aa8c9faf97fb65e6d52bedc90edbc278e509572521e743a6f58b` |
| percentile | `b0cf6d5b8a5e410b995d0d933726dc2f` | `10b5a35cc60b1b0de72050c3a1d9b1b5eec7d2efa4a0841f0bcaaaac148b0ccf` | `f5215bdc220ddfcf16294ee1e7f51e9d458841eeaaba939b37ed59f0e7e73621` |
