# Feature Benchmark Summary

- Started: 2026-07-22T15:53:58Z
- Finished: 2026-07-22T15:53:58Z
- API base URL: `http://localhost:3000/tcga_explorer`

| Workflow | Cohort | Endpoint | n | Events | Statistic | p | Adjusted/FDR p | PH p | Summary |
| --- | --- | --- | ---: | ---: | --- | ---: | ---: | ---: | --- |
| KIRC hypoxia z-score signature | TCGA-KIRC | OS | 531 | 175 | log-rank | 2.16e-04 | 0.111 | 0.003 | HR 0.74 (0.51-1.07); RMST delta 569 days |
| SKCM effector x exhaustion signatures | TCGA-SKCM | OS | 453 | 213 | interaction Cox | 0.838 | 0.838 | 0.056 | Interaction HR 0.99; groups 4 |
| CA9 pan-cancer continuous Cox | pan-cancer | OS | 10183 | 3149 | continuous Cox/FDR | 0.168 | 0.384 |  | 8/32 cohorts FDR<0.10; random-effects HR 1.08 |
