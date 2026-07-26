# TCGA-LUAD CD274 OS cutpoint benchmark

- Run started: 2026-07-26T17:24:13Z
- Run finished: 2026-07-26T17:24:28Z
- Completed analyses: 4/4
- Cached analyses in this run: 4/4
- API base URL: `http://192.168.1.31:3000/tcga_explorer`
- Cohort: `TCGA-LUAD`
- Gene: `CD274`
- Endpoint: `OS`
- Expression scale: `log2_tpm`
- Prespecified complete-case Cox adjustment: age_at_index.
- Grouped-test family: four prespecified two-group cutpoint sensitivities within this marker-endpoint scenario.
- Grouped multiplicity: Holm adjustment within this scenario. The maxstat member contributes its Lau94 selection-adjusted rank-statistic p-value; the other prespecified rules contribute their log-rank p-values.
- No composite retention rule is applied. Log-rank, Cox and RMST are related summaries of the same outcomes and are not counted as independent barriers.
- Marker-specific PH and global model PH are reported separately as interpretation diagnostics.
- Maxstat is outcome-optimized. Its corrected rank-statistic p-value is reported, while grouped HR, confidence intervals and RMST remain post-selection.
- Cutpoint-independent continuous reference: n=505, events=182, HR per +1 SD=1.05 (0.91-1.21), linear p=0.489, linear suite BH q=0.530, events/parameter=182.0, nonlinearity p=0.572, nonlinearity suite BH q=0.766.

| Method | n | Events | Family p | Holm p | HR | Cox p | Adjusted HR | Adjusted p | Marker PH p | Global PH p | RMST delta @ tau | RMST p | Same-contrast HRs | Notes |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| maxstat | 505 | 182 | 1.000 | 1.000 | 1.42 (0.97-2.08) | 0.068 | 1.38 (0.94-2.02) | 0.104 | 0.643 | 0.444 | -85 @ 1130 | 0.081 | grouped 1.42 vs continuous-implied 1.11; absolute log-HR ratio 3.40 | Outcome-optimized cutpoint; grouped estimates are post-selection; Raw Lau94 approximation lay outside [0,1] and was clamped |
| median | 505 | 182 | 0.962 | 1.000 | 0.99 (0.74-1.33) | 0.962 | 0.94 (0.70-1.26) | 0.662 | 0.637 | 0.470 | -5 @ 1130 | 0.879 | grouped 0.99 vs continuous-implied 1.08; absolute log-HR ratio 0.09 | No model-diagnostic caution recorded |
| upper_quartile | 505 | 182 | 0.363 | 1.000 | 1.16 (0.84-1.61) | 0.364 | 1.12 (0.81-1.56) | 0.499 | 0.804 | 0.478 | -35 @ 1130 | 0.358 | grouped 1.16 vs continuous-implied 1.10; absolute log-HR ratio 1.66 | No model-diagnostic caution recorded |
| upper_lower_quartile | 254 | 103 | 0.771 | 1.000 | 1.06 (0.72-1.56) | 0.771 | 0.98 (0.67-1.45) | 0.930 | 0.919 | 0.970 | -9 @ 1130 | 0.844 | grouped 1.06 vs continuous-implied 1.13; absolute log-HR ratio 0.46 | Middle 50% excluded |

## Audit Hashes

| Method | Analysis ID | Reproducibility hash | Grouped records SHA-256 | Continuous records SHA-256 |
| --- | --- | --- | --- | --- |
| maxstat | `047d0ecda3074545a5bfe1610dafecc6` | `43bffc6d98dc429af98761516852ee906bddd7e25f1a47d662587f318942139c` | `a384a4afb02fb19aab9e5a4747257883e3d8dd421ed2a9e1355f3299aa2847d4` | `de541631dca4170c7aba4c8f0c1b6e9b094d117fb878cb1864f84a32cd010ab1` |
| median | `477eff5db4574eb9976fa508c4bd2ace` | `0ebdfe5895a8000a8f40aed52a1fd687c9b8de218092cabf31fb75d855314fbc` | `16159691c1bd981d977d3c6c6ebebdb791b1afad1effe6bac3b000b48b24246a` | `de541631dca4170c7aba4c8f0c1b6e9b094d117fb878cb1864f84a32cd010ab1` |
| upper_quartile | `201d896fdcd949c0926b6766786eac01` | `ac8be22e87109fe13822d57d1a652192af80e9161364b3642069beb54139db9d` | `1b0002e40e197fb5d1fa7f6678b3bde8d974fe7d08688de2a8477662bacd5154` | `de541631dca4170c7aba4c8f0c1b6e9b094d117fb878cb1864f84a32cd010ab1` |
| upper_lower_quartile | `405f158f86fd4a1d9925f045bb624006` | `ac0177288854a1d90890b4da230227231334f93cf3cef5b79fc4bbe6a6f613a4` | `301bb7b275c9c061868132c54edd1af4150672252daafdabde90410bb012464f` | `de541631dca4170c7aba4c8f0c1b6e9b094d117fb878cb1864f84a32cd010ab1` |

## RMST Tau Sensitivity

| Method | Tau fraction | Tau days | RMST delta days | RMST p |
| --- | ---: | ---: | ---: | ---: |
| maxstat | 0.75 | 847.5 | -57 | 0.075 |
| maxstat | 0.90 | 1017.0 | -76 | 0.070 |
| maxstat | 1.00 | 1130.0 | -85 | 0.081 |
| median | 0.75 | 847.5 | -1 | 0.980 |
| median | 0.90 | 1017.0 | -3 | 0.911 |
| median | 1.00 | 1130.0 | -5 | 0.879 |
| upper_quartile | 0.75 | 847.5 | -26 | 0.308 |
| upper_quartile | 0.90 | 1017.0 | -31 | 0.349 |
| upper_quartile | 1.00 | 1130.0 | -35 | 0.358 |
| upper_lower_quartile | 0.75 | 847.5 | -10 | 0.747 |
| upper_lower_quartile | 0.90 | 1017.0 | -9 | 0.818 |
| upper_lower_quartile | 1.00 | 1130.0 | -9 | 0.844 |
