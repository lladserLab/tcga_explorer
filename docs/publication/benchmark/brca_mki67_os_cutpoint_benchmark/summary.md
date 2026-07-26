# TCGA-BRCA MKI67 OS cutpoint benchmark

- Run started: 2026-07-25T17:50:16Z
- Run finished: 2026-07-25T17:50:34Z
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
- Cutpoint-independent continuous reference: n=1080, events=151, HR per +1 SD=1.09 (0.94-1.27), linear p=0.262, linear suite BH q=0.320, events/parameter=151.0, nonlinearity p=0.613, nonlinearity suite BH q=0.749.

| Method | n | Events | Family p | Holm p | HR | Cox p | Adjusted HR | Adjusted p | Marker PH p | Global PH p | RMST delta @ tau | RMST p | Same-contrast HRs | Notes |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| maxstat | 1080 | 151 | 1.000 | 1.000 | 1.37 (0.97-1.91) | 0.071 | 1.59 (1.13-2.24) | 0.008 | 0.510 | 0.688 | -46 @ 1688 | 0.116 | grouped 1.37 vs continuous-implied 1.16; absolute log-HR ratio 2.15 | Outcome-optimized cutpoint; grouped estimates are post-selection; Raw Lau94 approximation lay outside [0,1] and was clamped |
| median | 1080 | 151 | 0.583 | 1.000 | 1.09 (0.79-1.51) | 0.583 | 1.27 (0.92-1.76) | 0.148 | 0.683 | 0.814 | -18 @ 1688 | 0.448 | grouped 1.09 vs continuous-implied 1.15; absolute log-HR ratio 0.65 | No model-diagnostic caution recorded |
| upper_quartile | 1080 | 151 | 0.112 | 0.447 | 1.32 (0.94-1.86) | 0.113 | 1.53 (1.08-2.16) | 0.017 | 0.203 | 0.334 | -51 @ 1688 | 0.086 | grouped 1.32 vs continuous-implied 1.16; absolute log-HR ratio 1.91 | No model-diagnostic caution recorded |
| upper_lower_quartile | 540 | 88 | 0.342 | 1.000 | 1.23 (0.81-1.86) | 0.343 | 1.47 (0.95-2.26) | 0.082 | 0.607 | 0.839 | -40 @ 1688 | 0.259 | grouped 1.23 vs continuous-implied 1.25; absolute log-HR ratio 0.92 | Middle 50% excluded |

## Audit Hashes

| Method | Analysis ID | Reproducibility hash | Grouped records SHA-256 | Continuous records SHA-256 |
| --- | --- | --- | --- | --- |
| maxstat | `59f69ed8d40744fbb90dc562f4ec945f` | `bb4a1e14101278a481bf6ee6a273560b93c958154dd6850762ba4cb28c5d170e` | `dabb394045ca03dc609d4f17f1a927b2b4fcc8d0dcdf4dc37a90839b02b13825` | `ead97d58ce1313d5ca4cbe5783729ec5c004b232b6b7daf2873c7b640fbdf006` |
| median | `346dcba7cbdd4565a9134c7c02b1677a` | `8da40c425769cd57f8d075b14285d8a7203f98ca15997e629dc7f0075d4e70a2` | `7e6edea974b7a69b2838422db6950464e194b8ad3884cde311adc9655504937d` | `ead97d58ce1313d5ca4cbe5783729ec5c004b232b6b7daf2873c7b640fbdf006` |
| upper_quartile | `f0d7a58b8eb24f24904651b45fc70a5c` | `2905b7e9d2a67398b8db68a6c60c0302eb9f26644a61e9df03318c64159e1764` | `0d750237382956d1e95f805178355bccc08bc7b3d731848839c9bcc1ef9bce77` | `ead97d58ce1313d5ca4cbe5783729ec5c004b232b6b7daf2873c7b640fbdf006` |
| upper_lower_quartile | `1f0853cbbc82423d896e18bc59253b50` | `4321dd3d9109894e644a569fdd4f8ffda9e6f84765e937818c2f01ac0ce06a3f` | `c2ec3a5e573a2dfa9ddfb5d6866a1cd57d9d40bcc1ad0683549c6772b0b11e47` | `ead97d58ce1313d5ca4cbe5783729ec5c004b232b6b7daf2873c7b640fbdf006` |

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
