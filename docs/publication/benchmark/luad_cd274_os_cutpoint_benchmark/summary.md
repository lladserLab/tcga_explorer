# TCGA-LUAD CD274 OS cutpoint benchmark

- Run started: 2026-07-25T17:51:24Z
- Run finished: 2026-07-25T17:51:38Z
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
- Cutpoint-independent continuous reference: n=505, events=182, HR per +1 SD=1.05 (0.91-1.21), linear p=0.489, linear suite BH q=0.530, events/parameter=182.0, nonlinearity p=0.572, nonlinearity suite BH q=0.749.

| Method | n | Events | Family p | Holm p | HR | Cox p | Adjusted HR | Adjusted p | Marker PH p | Global PH p | RMST delta @ tau | RMST p | Same-contrast HRs | Notes |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| maxstat | 505 | 182 | 1.000 | 1.000 | 1.42 (0.97-2.08) | 0.068 | 1.38 (0.94-2.02) | 0.104 | 0.643 | 0.444 | -85 @ 1130 | 0.081 | grouped 1.42 vs continuous-implied 1.11; absolute log-HR ratio 3.40 | Outcome-optimized cutpoint; grouped estimates are post-selection; Raw Lau94 approximation lay outside [0,1] and was clamped |
| median | 505 | 182 | 0.962 | 1.000 | 0.99 (0.74-1.33) | 0.962 | 0.94 (0.70-1.26) | 0.662 | 0.637 | 0.470 | -5 @ 1130 | 0.879 | grouped 0.99 vs continuous-implied 1.08; absolute log-HR ratio 0.09 | No model-diagnostic caution recorded |
| upper_quartile | 505 | 182 | 0.363 | 1.000 | 1.16 (0.84-1.61) | 0.364 | 1.12 (0.81-1.56) | 0.499 | 0.804 | 0.478 | -35 @ 1130 | 0.358 | grouped 1.16 vs continuous-implied 1.10; absolute log-HR ratio 1.66 | No model-diagnostic caution recorded |
| upper_lower_quartile | 254 | 103 | 0.771 | 1.000 | 1.06 (0.72-1.56) | 0.771 | 0.98 (0.67-1.45) | 0.930 | 0.919 | 0.970 | -9 @ 1130 | 0.844 | grouped 1.06 vs continuous-implied 1.13; absolute log-HR ratio 0.46 | Middle 50% excluded |

## Audit Hashes

| Method | Analysis ID | Reproducibility hash | Grouped records SHA-256 | Continuous records SHA-256 |
| --- | --- | --- | --- | --- |
| maxstat | `204eebf3c01a4a5bbf7cef4befe803f2` | `918d6ffa598c724cc53ec6ffe65dcd10ec9f1dd019fb5218c74bb49f3a28d8c5` | `9a4365305f92a18cbb4fee882bc75b9d89516bf1b7b5a4683daf2fd3205ab100` | `f13bb1725f6bd6989e06121e1d2e9f628a32db44961ca9721edd82877cb768f9` |
| median | `aaa1cceb5cd04ca59a9d59b694221062` | `1797b1e98a6dc61cc1ef8d955e3db12c39a925e3a21612742e341eed01896bc3` | `ac02621f429d7b9ebbc84c5ffcb402a8ef7cfe621cfa50d1d32e10d9d4c9d1d1` | `f13bb1725f6bd6989e06121e1d2e9f628a32db44961ca9721edd82877cb768f9` |
| upper_quartile | `5a5bd09a93b24a7999185c349b987e7b` | `ba36302288bb50bc563e3b493cb5d6c3d7c056e22dd57ff6613cf28ee0557e51` | `47f83d53c1b0e41c733ce12708c97b62b946cb3195777109c3c6f324af4c4def` | `f13bb1725f6bd6989e06121e1d2e9f628a32db44961ca9721edd82877cb768f9` |
| upper_lower_quartile | `714b96acf9f74135beaffc7dd91deb60` | `374a41e4040311cfdfa82b44d508672fa37319f7a98ee1b9803909d8044a5429` | `8471461c4f67464dee41221b4ece676806e65e090c5a28803f704012437c0c5a` | `f13bb1725f6bd6989e06121e1d2e9f628a32db44961ca9721edd82877cb768f9` |

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
