# Feature Benchmark Summary

- Started: 2026-07-26T01:31:54Z
- Finished: 2026-07-26T01:32:27Z
- API base URL: `http://192.168.1.31:3000/tcga_explorer`

| Mode | Inputs and construction | Cohort/n | Primary result | Diagnostics | Limitation |
| --- | --- | --- | --- | --- | --- |
| Weighted signature | BUB1B, PINK1 (w=-1) | TCGA-ACC OS; 79/28 | HR per SD 2.85 (1.90-4.26); nonlinearity p=0.470 | continuous Cox p=3.66e-07; adjusted p=5.58e-07; nonlinearity p=0.470; marker PH p=0.265; global PH p=0.521; grouped log-rank p=4.59e-04; RMST p=1.90e-04; 14.0 events/parameter | RNA-seq analogue of a published expression contrast; the original qRT-PCR threshold is not replicated. |
| Two-marker grouping | BAP1 x PRAME; independent median splits | TCGA-UVM DSS; 80/21 | Global separation; BAP1-low/PRAME-high 10/21 events; BAP1-high/PRAME-low 1/21 | four-group log-rank p=0.002; interaction p=0.637; global PH p=0.431; 5.2 events/parameter; Firth HR=1.38, p=0.126 | Continuous interaction p=0.637; signature interaction user-adjusted for age completed without a model warning. |
| Pan-cancer primary + sensitivity | BIRC5 | pan-cancer OS; 10183/3149 | 18/32 cohorts FDR<0.10; common-scale REML HR 1.20 (1.06-1.37); 95% PI 0.64-2.24 | REML/HKSJ meta-analysis p=0.006; I2=86.1%; Ordinal sensitivity: 26/33 cohorts evaluable; 11 selected adjusted FDR hits; stage-adjusted common-scale REML HR 1.20 (HKSJ p=0.005; 95% PI 0.73-1.98). | Primary I2=86.1%; 95% prediction interval 0.64-2.24; selected ordinal sensitivity was evaluable in 26/33 cancers and mixed adjustment families were not pooled. |
