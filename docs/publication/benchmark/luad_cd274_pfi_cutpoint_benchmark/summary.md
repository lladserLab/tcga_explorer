# TCGA-LUAD CD274 PFI cutpoint benchmark

- Run started: 2026-07-22T15:53:59Z
- Run finished: 2026-07-22T15:53:59Z
- Completed analyses: 5/5
- Cached analyses in this run: 5/5
- API base URL: `http://localhost:3000/tcga_explorer`
- Cohort: `TCGA-LUAD`
- Gene: `CD274`
- Endpoint: `PFI`
- Expression scale: `log2_tpm`
- Decision rule: BH log-rank, univariable Cox, adjusted Cox and RMST p <= 0.05; adjusted PH global p not flagged.

| Method | n | Events | BH log-rank | HR | Cox p | Adjusted p | PH global p | RMST delta days | RMST p | Survives |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| maxstat | 505 | 208 | 0.110 | 1.38 (1.05-1.83) | 0.023 | 0.042 | 0.205 | -294 | 0.040 | no (Fails BH) |
| median | 505 | 208 | 0.695 | 1.06 (0.80-1.39) | 0.695 | 0.454 | 0.188 | 84 | 0.860 | no (Fails BH) |
| upper_quartile | 505 | 208 | 0.454 | 1.21 (0.89-1.63) | 0.228 | 0.678 | 0.211 | -184 | 0.232 | no (Fails BH) |
| upper_lower_quartile | 254 | 117 | 0.695 | 1.11 (0.77-1.60) | 0.580 | 0.904 | 0.289 | -124 | 0.498 | no (Fails BH) |
| percentile | 505 | 208 | 0.454 | 1.19 (0.87-1.61) | 0.273 | 0.786 | 0.206 | -171 | 0.270 | no (Fails BH) |

## Audit Hashes

| Method | Analysis ID | Reproducibility hash | Patient records SHA-256 |
| --- | --- | --- | --- |
| maxstat | `9d1c0d34f1e54561a5496019e38d67a9` | `5491e2d32b20931fca902d76423ed35333068e5d2a5e72a1b0a7fc337aa9bb8d` | `f48eb9f26decb1b6e547cd054d5154b4bdc5ffce79af11a00e6e15d7d6bc2c22` |
| median | `5fb9eeecac664832bcd10ae5e680d080` | `4b2ca5852b9d920b12e40d9ec27ee360063ef764534e8de8cd83578c0d1c568e` | `d6b7eb198dafbf3ef25b899ae978411429ec5490e51c86f0c5f14595ed677a3c` |
| upper_quartile | `f224959d1fff4cdebc39b1d17bae0876` | `fc3b64f18b20d4c9bbb90e21f7b4f28d7cd8b322baadbdade2aae80ea4085ed7` | `db24fa30ae48df01b1645789d194bab3600a2c1eed9c3a8990ba20179795cd70` |
| upper_lower_quartile | `e6ecf235c58444c1bdc6b56447d9c25b` | `3d6aec3c04070e6f07893eb9a7fff728b5937de0abfc7bac6ae7a2d50d70ce98` | `fceccdadebbf2ee1ad67e05b3b4832b42d9fa9efad8fd28513116cf6310d3b9c` |
| percentile | `9bfd9fc0f7a440009257034a82b8967c` | `522c53efd2869e3fc354c5d3208f1aef8883d470b2b109be78a57cee6f96266c` | `98d0ae9fa3d7852d52c06ea0622c305ed8d6cdf82e14e6177fe5b09d49a9d4ce` |
