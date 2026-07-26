# TCGA-KIRC CA9 OS cutpoint benchmark

- Run started: 2026-07-26T17:22:40Z
- Run finished: 2026-07-26T17:22:55Z
- Completed analyses: 4/4
- Cached analyses in this run: 4/4
- API base URL: `http://192.168.1.31:3000/tcga_explorer`
- Cohort: `TCGA-KIRC`
- Gene: `CA9`
- Endpoint: `OS`
- Expression scale: `log2_tpm`
- Prespecified complete-case Cox adjustment: age_at_index.
- Grouped-test family: four prespecified two-group cutpoint sensitivities within this marker-endpoint scenario.
- Grouped multiplicity: Holm adjustment within this scenario. The maxstat member contributes its Lau94 selection-adjusted rank-statistic p-value; the other prespecified rules contribute their log-rank p-values.
- No composite retention rule is applied. Log-rank, Cox and RMST are related summaries of the same outcomes and are not counted as independent barriers.
- Marker-specific PH and global model PH are reported separately as interpretation diagnostics.
- Maxstat is outcome-optimized. Its corrected rank-statistic p-value is reported, while grouped HR, confidence intervals and RMST remain post-selection.
- Cutpoint-independent continuous reference: n=531, events=175, HR per +1 SD=0.91 (0.79-1.04), linear p=0.168, linear suite BH q=0.231, events/parameter=175.0, nonlinearity p=0.002, nonlinearity suite BH q=0.022.

| Method | n | Events | Family p | Holm p | HR | Cox p | Adjusted HR | Adjusted p | Marker PH p | Global PH p | RMST delta @ tau | RMST p | Same-contrast HRs | Notes |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| maxstat | 531 | 175 | 0.032 | 0.096 | 0.59 (0.44-0.80) | 5.69e-04 | 0.63 (0.46-0.85) | 0.003 | 0.756 | 0.676 | 158 @ 1826 | 0.008 | grouped 0.59 vs continuous-implied 0.88; absolute log-HR ratio 4.14 | Outcome-optimized cutpoint; grouped estimates are post-selection |
| median | 531 | 175 | 0.013 | 0.050 | 0.68 (0.51-0.92) | 0.013 | 0.70 (0.52-0.95) | 0.023 | 0.579 | 0.595 | 107 @ 1826 | 0.044 | grouped 0.68 vs continuous-implied 0.90; absolute log-HR ratio 3.81 | No model-diagnostic caution recorded |
| upper_quartile | 531 | 175 | 0.355 | 0.355 | 0.84 (0.59-1.21) | 0.355 | 0.89 (0.62-1.28) | 0.527 | 0.102 | 0.198 | 1 @ 1826 | 0.986 | grouped 0.84 vs continuous-implied 0.92; absolute log-HR ratio 1.94 | No model-diagnostic caution recorded |
| upper_lower_quartile | 266 | 93 | 0.043 | 0.096 | 0.65 (0.43-0.99) | 0.044 | 0.69 (0.45-1.05) | 0.083 | 0.398 | 0.416 | 112 @ 1826 | 0.163 | grouped 0.65 vs continuous-implied 0.84; absolute log-HR ratio 2.43 | Middle 50% excluded |

## Audit Hashes

| Method | Analysis ID | Reproducibility hash | Grouped records SHA-256 | Continuous records SHA-256 |
| --- | --- | --- | --- | --- |
| maxstat | `b9d5801d53914285b0698f1df69be9f1` | `66587e48026372e803dab88c79e22d787119ce89b513a56ee7f1a9240ffb860b` | `e508a0cf7f9307e6220e065e0d6dad7e5e29cfee7f3fedcbfd08116bd1baa100` | `7ed858c95e5fb900604cb9245212d63f059f6e569e47f7a38ee5febceb855a0e` |
| median | `686d9253ed1b4d4fa12fea884926c6c9` | `7420be3fffcaaf88ad02f4b9e63932b4a4a70b1c463a3730f5aa6029caf1c3be` | `a002128fcf3ecc630e4f5e9338e0760d40bde05bc1accf9570ff0cc95773fea2` | `7ed858c95e5fb900604cb9245212d63f059f6e569e47f7a38ee5febceb855a0e` |
| upper_quartile | `b3bd175b500c4bb0b81a0ce7290214e7` | `2d04cf6c1cad92c24c429ae8378534bf62983004221dfae4e7fe50eb67006788` | `eeb009f4baa04e85fd42a29621b7034ad966b0e4a817bfa9820e6da1255dcd96` | `7ed858c95e5fb900604cb9245212d63f059f6e569e47f7a38ee5febceb855a0e` |
| upper_lower_quartile | `db5c1e98a33540cab1fd7a28a46f6c8d` | `433a2bd2c06fe4517144cd329ec769581fbf31ac6ea1cb64965a0c6f5d0881b5` | `c6e3d8d40a38820df003389a4e345149b76e3b2d13e6e1f04ba3128b0b4c77c9` | `7ed858c95e5fb900604cb9245212d63f059f6e569e47f7a38ee5febceb855a0e` |

## RMST Tau Sensitivity

| Method | Tau fraction | Tau days | RMST delta days | RMST p |
| --- | ---: | ---: | ---: | ---: |
| maxstat | 0.75 | 1369.7 | 97 | 0.018 |
| maxstat | 0.90 | 1643.6 | 127 | 0.015 |
| maxstat | 1.00 | 1826.2 | 158 | 0.008 |
| median | 0.75 | 1369.7 | 59 | 0.102 |
| median | 0.90 | 1643.6 | 85 | 0.067 |
| median | 1.00 | 1826.2 | 107 | 0.044 |
| upper_quartile | 0.75 | 1369.7 | -7 | 0.874 |
| upper_quartile | 0.90 | 1643.6 | -4 | 0.942 |
| upper_quartile | 1.00 | 1826.2 | 1 | 0.986 |
| upper_lower_quartile | 0.75 | 1369.7 | 65 | 0.239 |
| upper_lower_quartile | 0.90 | 1643.6 | 89 | 0.204 |
| upper_lower_quartile | 1.00 | 1826.2 | 112 | 0.163 |
