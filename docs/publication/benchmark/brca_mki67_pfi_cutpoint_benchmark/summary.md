# TCGA-BRCA MKI67 PFI cutpoint benchmark

- Run started: 2026-07-22T15:53:58Z
- Run finished: 2026-07-22T15:53:58Z
- Completed analyses: 5/5
- Cached analyses in this run: 5/5
- API base URL: `http://localhost:3000/tcga_explorer`
- Cohort: `TCGA-BRCA`
- Gene: `MKI67`
- Endpoint: `PFI`
- Expression scale: `log2_tpm`
- Decision rule: BH log-rank, univariable Cox, adjusted Cox and RMST p <= 0.05; adjusted PH global p not flagged.

| Method | n | Events | BH log-rank | HR | Cox p | Adjusted p | PH global p | RMST delta days | RMST p | Survives |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| maxstat | 1080 | 145 | 0.014 | 2.40 (1.33-4.34) | 0.004 | 3.51e-04 | 0.836 | -2535 | 5.12e-07 | yes |
| median | 1080 | 145 | 0.359 | 1.23 (0.89-1.71) | 0.216 | 0.083 | 0.807 | -147 | 0.815 | no (Fails BH) |
| upper_quartile | 1080 | 145 | 0.384 | 1.17 (0.82-1.69) | 0.385 | 0.352 | 0.852 | 545 | 0.194 | no (Fails BH) |
| upper_lower_quartile | 540 | 71 | 0.328 | 1.43 (0.90-2.30) | 0.133 | 0.057 | 0.085 | -435 | 0.341 | no (Fails BH) |
| percentile | 1080 | 145 | 0.384 | 1.17 (0.82-1.69) | 0.385 | 0.352 | 0.852 | 545 | 0.194 | no (Fails BH) |

## Audit Hashes

| Method | Analysis ID | Reproducibility hash | Patient records SHA-256 |
| --- | --- | --- | --- |
| maxstat | `cb85a8ff38144efabdf9531ff6e3e50b` | `8b2eeeb6b3dbde3c35d3758f7d0340c8ea4d69ac58b5db60eb991faf3751320f` | `96efc88509def12fc58a464ec26b7d3b16c419e5e1e4d6841f366cc5c7515863` |
| median | `28a64f371b634c8e9144ddcc9b437777` | `d5c8719202e08cac7c29da92041b526a2044c34740472cea75019fc7ced88b6e` | `29fe82e6d51a813a7712c8d044b646a349bf2c90a7e0087ee2be0af10a4964e5` |
| upper_quartile | `296a38c3471b4b218158a8423679e72c` | `c72af5cf758ec7cb1c398186028422e8e498cb7a24b59d1002790c64940154f5` | `fc894070b18354a0d7ff9d78608bc8eff9f7ca72c819752288b7096794a3953d` |
| upper_lower_quartile | `027e58d9caa94786a09d08978b4a928d` | `b30adafbc3217d41fd1d25ca9267aa31c0e3cf194069ee2166cf6cfef8291ff0` | `162024bbb84b642e5e5157d0d69c617809461a8871c912c5f6274a1fee856114` |
| percentile | `7c201e6e6fa14009a2e524012d39fe92` | `130e9cc70ecab9a021629cb00b5322ccb5b18f9972cd405256b9ff86f7ed13c4` | `f63d419c825a006a4d137eb14c114a414bc6bc63f4e9da319e37603737d98314` |
