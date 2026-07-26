# TCGA-BRCA MKI67 PFI cutpoint benchmark

- Run started: 2026-07-25T17:50:35Z
- Run finished: 2026-07-25T17:50:52Z
- Completed analyses: 4/4
- Cached analyses in this run: 4/4
- API base URL: `http://192.168.1.31:3000/tcga_explorer`
- Cohort: `TCGA-BRCA`
- Gene: `MKI67`
- Endpoint: `PFI`
- Expression scale: `log2_tpm`
- Prespecified complete-case Cox adjustment: age_at_index.
- Grouped-test family: four prespecified two-group cutpoint sensitivities within this marker-endpoint scenario.
- Grouped multiplicity: Holm adjustment within this scenario. The maxstat member contributes its Lau94 selection-adjusted rank-statistic p-value; the other prespecified rules contribute their log-rank p-values.
- No composite retention rule is applied. Log-rank, Cox and RMST are related summaries of the same outcomes and are not counted as independent barriers.
- Marker-specific PH and global model PH are reported separately as interpretation diagnostics.
- Maxstat is outcome-optimized. Its corrected rank-statistic p-value is reported, while grouped HR, confidence intervals and RMST remain post-selection.
- Cutpoint-independent continuous reference: n=1080, events=145, HR per +1 SD=1.16 (0.99-1.35), linear p=0.074, linear suite BH q=0.117, events/parameter=145.0, nonlinearity p=0.029, nonlinearity suite BH q=0.106.

| Method | n | Events | Family p | Holm p | HR | Cox p | Adjusted HR | Adjusted p | Marker PH p | Global PH p | RMST delta @ tau | RMST p | Same-contrast HRs | Notes |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| maxstat | 1080 | 145 | 0.098 | 0.391 | 2.40 (1.33-4.34) | 0.004 | 2.45 (1.35-4.43) | 0.003 | 0.548 | 0.025 | -82 @ 1598 | 0.002 | grouped 2.40 vs continuous-implied 1.31; absolute log-HR ratio 3.21 | Global PH caution; marker term not flagged; Outcome-optimized cutpoint; grouped estimates are post-selection |
| median | 1080 | 145 | 0.215 | 0.430 | 1.23 (0.89-1.71) | 0.216 | 1.25 (0.90-1.74) | 0.188 | 0.790 | 0.013 | -32 @ 1598 | 0.203 | grouped 1.23 vs continuous-implied 1.26; absolute log-HR ratio 0.90 | Global PH caution; marker term not flagged |
| upper_quartile | 1080 | 145 | 0.384 | 0.430 | 1.17 (0.82-1.69) | 0.385 | 1.19 (0.82-1.71) | 0.356 | 0.292 | 0.005 | -31 @ 1598 | 0.302 | grouped 1.17 vs continuous-implied 1.27; absolute log-HR ratio 0.66 | Global PH caution; marker term not flagged |
| upper_lower_quartile | 540 | 71 | 0.131 | 0.394 | 1.43 (0.90-2.30) | 0.133 | 1.32 (0.81-2.13) | 0.261 | 0.726 | 0.085 | -39 @ 1598 | 0.264 | grouped 1.43 vs continuous-implied 1.44; absolute log-HR ratio 0.98 | Middle 50% excluded |

## Audit Hashes

| Method | Analysis ID | Reproducibility hash | Grouped records SHA-256 | Continuous records SHA-256 |
| --- | --- | --- | --- | --- |
| maxstat | `76b6c68bca5a446b80e22c758892f52b` | `a4ef39a50593f32d99065b53ceff0ea889f64368d220c85fbfb68bf828e7efdf` | `4bc795427b0fd96b5fc05ef46bf5ee7460babcae67ff6c4b11a7ca98790f9597` | `41e6daa2ab5fd051a496d0c2615849beff1c357cc28afb97fd7401a1f9b80ab1` |
| median | `1bfbf2f8505d4802b008c0a96e35871b` | `aec8eaebcc1a9657390d70edb35bca224fadacb8c80e567aea2f17e07767eafd` | `df443a60e7e9edc9f2375b0738d80330f00d992f399f94043ac2a6244ff8be2e` | `41e6daa2ab5fd051a496d0c2615849beff1c357cc28afb97fd7401a1f9b80ab1` |
| upper_quartile | `bd8a776c552b46a2a9d53ec69d979df7` | `300d5052a3e123ec25f2244240c8e76d1aeb9904cc042d5dc7dea27ea0c2a02c` | `b5a06e90191b065cc54679899881ed282ea0d40d7b24bb6252223f2873605a86` | `41e6daa2ab5fd051a496d0c2615849beff1c357cc28afb97fd7401a1f9b80ab1` |
| upper_lower_quartile | `0b0c2dd5fdc8463cae562622f9500c58` | `5e34151379c202e5b0537ea8fce7fc11d48a933f5a5a0e9048a00a9dbf4a52a9` | `654b99ccd91518d0224485dc63d3949608c8e78631e7e959d01a0a3dc9a78bad` | `41e6daa2ab5fd051a496d0c2615849beff1c357cc28afb97fd7401a1f9b80ab1` |

## RMST Tau Sensitivity

| Method | Tau fraction | Tau days | RMST delta days | RMST p |
| --- | ---: | ---: | ---: | ---: |
| maxstat | 0.75 | 1198.5 | -46 | 0.003 |
| maxstat | 0.90 | 1438.2 | -67 | 0.002 |
| maxstat | 1.00 | 1598.0 | -82 | 0.002 |
| median | 0.75 | 1198.5 | -14 | 0.351 |
| median | 0.90 | 1438.2 | -25 | 0.220 |
| median | 1.00 | 1598.0 | -32 | 0.203 |
| upper_quartile | 0.75 | 1198.5 | -12 | 0.505 |
| upper_quartile | 0.90 | 1438.2 | -22 | 0.365 |
| upper_quartile | 1.00 | 1598.0 | -31 | 0.302 |
| upper_lower_quartile | 0.75 | 1198.5 | -14 | 0.529 |
| upper_lower_quartile | 0.90 | 1438.2 | -28 | 0.337 |
| upper_lower_quartile | 1.00 | 1598.0 | -39 | 0.264 |
