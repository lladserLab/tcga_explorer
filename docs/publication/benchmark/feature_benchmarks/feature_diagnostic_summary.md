# Feature Benchmark Diagnostic Summary

- Started: 2026-07-26T01:31:54Z
- Finished: 2026-07-26T01:32:27Z
- API base URL: `http://192.168.1.31:3000/tcga_explorer`

| Mode | Inputs and construction | Cohort/n | Primary result | Diagnostics | Limitation |
| --- | --- | --- | --- | --- | --- |
| KIRC hypoxia signature | CA9, VEGFA, SLC2A1, LDHA, PGK1 | TCGA-KIRC OS; 531/175 | HR per SD 0.85 (0.74-0.98); nonlinearity p=4.51e-04 | continuous Cox p=0.024; adjusted p=0.016; nonlinearity p=4.51e-04; marker PH p=0.998; global PH p=0.652; grouped log-rank p=1.23e-04; RMST p=6.85e-04; 87.5 events/parameter | Continuous and grouped summaries are shown together; clinical adjustment, PH and nonlinearity remain separate diagnostics. |
| SKCM effector x exhaustion | Effector: CD8A, GZMB, PRF1, IFNG, CXCL9, CXCL10; Exhaustion: PDCD1, CTLA4, LAG3, HAVCR2, TIGIT | TCGA-SKCM OS; 453/213 | Global separation; 4 KM groups | four-group log-rank p=1.12e-06; interaction p=0.837; global PH p=0.056; 53.2 events/parameter | Four-group separation is significant, but the continuous interaction term is not. |
| CA9 pan-cancer primary + sensitivity | CA9 | pan-cancer OS; 10183/3149 | 8/32 cohorts FDR<0.10; common-scale REML HR 1.04 (1.00-1.08); 95% PI 0.93-1.16 | REML/HKSJ meta-analysis p=0.031; I2=60.7%; Ordinal sensitivity: 26/33 cohorts evaluable; 3 selected adjusted FDR hits; stage-adjusted common-scale REML HR 1.03 (HKSJ p=0.065; 95% PI 0.94-1.13). | Primary I2=60.7%; 95% prediction interval 0.93-1.16; ordinal sensitivity was evaluable in 26/33 cancers with 3 direction reversals; 3 selected adjusted FDR hits. |
