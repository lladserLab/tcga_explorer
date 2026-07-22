# TCGA-KIRC CA9 Cutpoint Benchmark

- Run started: 2026-07-22T12:38:56Z
- Run finished: 2026-07-22T12:38:56Z
- API base URL: `http://localhost:3000/tcga_explorer`
- Cohort: `TCGA-KIRC`
- Gene: `CA9`
- Endpoint: `OS`
- Expression scale: `log2_tpm`
- Decision rule: BH log-rank, univariable Cox, adjusted Cox and RMST p <= 0.05; adjusted PH global p not flagged.

| Method | n | Events | BH log-rank | HR | Cox p | Adjusted p | PH global p | RMST delta days | RMST p | Survives |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| maxstat | 531 | 175 | 0.002 | 0.59 (0.44-0.80) | 5.69e-04 | 0.058 | 0.005 | 607 | 6.17e-04 | no (Fails adjusted) |
| median | 531 | 175 | 0.031 | 0.68 (0.51-0.92) | 0.013 | 0.362 | 0.004 | 427 | 0.011 | no (Fails adjusted) |
| upper_quartile | 531 | 175 | 0.355 | 0.84 (0.59-1.21) | 0.355 | 0.348 | 0.002 | 268 | 0.169 | no (Fails BH) |
| upper_lower_quartile | 266 | 93 | 0.071 | 0.65 (0.43-0.99) | 0.044 | 0.487 | 0.093 | 555 | 0.019 | no (Fails BH) |
| percentile | 531 | 175 | 0.355 | 0.84 (0.59-1.21) | 0.355 | 0.348 | 0.002 | 268 | 0.169 | no (Fails BH) |

## Audit Hashes

| Method | Analysis ID | Reproducibility hash | Patient records SHA-256 |
| --- | --- | --- | --- |
| maxstat | `fbe678227f944a1fab649d344bf4f124` | `188d8bd6eae334683ee941c3187b477456b8506d77bdf6f4faf5a57ff1255a43` | `7857b6416321e581c7bf4712032419f099f3c2afbbbbf81b244d7be6e5574ae9` |
| median | `ede0234860d74ce3b8d36006aff5e4d6` | `b823976b65099ddde1fbf46d0a74e724c9d6399fcc7422b0751471a36d651dd6` | `bb669bb6df0671f8dee8b4eeacc068e56bd8c8de86363ea103e4ddfcc6c693a9` |
| upper_quartile | `b22a7ab7a4d94b0fab864726a7335433` | `bf132d15867f273ea2a7ab8af2a511ab2212e866993c5784ae9ab3ff1e69ff9a` | `6dcab00c7975f2013240269fcd5a1d7bfc37811187fe7aad3d318fc669c71ead` |
| upper_lower_quartile | `d4b761863dcf4eef9877d4e9d6c37f62` | `3a11010be3acca984c36269025e038c3729ced9fc97413f557c01463af91adf5` | `d441459b9efcf2eb0d0d77cd83eb491b92060d294c07ef0fad69f13c17f814fd` |
| percentile | `62531792f36546868725d70913d4c3e3` | `516bd794208c68059febe283ed85ca098466bcdd735e8dd683b4e2377a19e1b1` | `43de205c7d3b146b7e8972c9697524f3d3f7b1f79e03d213a6eb89ef4d2ab105` |
