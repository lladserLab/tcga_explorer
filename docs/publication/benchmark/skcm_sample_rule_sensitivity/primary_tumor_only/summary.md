# TCGA-SKCM PDCD1 OS sample-rule sensitivity (primary tumor only)

- Run started: 2026-07-25T02:40:59Z
- Run finished: 2026-07-25T02:41:02Z
- Completed analyses: 1/1
- Cached analyses in this run: 0/1
- API base URL: `http://192.168.1.31:3000/tcga_explorer`
- Cohort: `TCGA-SKCM`
- Gene: `PDCD1`
- Endpoint: `OS`
- Expression scale: `log2_tpm`
- BH family: completed cutpoint methods within this marker-endpoint scenario.
- No composite retention rule is applied. Log-rank, Cox and RMST are related summaries of the same outcomes and are not counted as independent barriers.
- Marker-specific PH and global model PH are reported separately as interpretation diagnostics.
- Maxstat is outcome-optimized. Its corrected rank-statistic p-value is reported, while grouped HR, confidence intervals and RMST remain post-selection.
- Cutpoint-independent continuous reference: n=102, events=29, HR per +1 SD=0.69 (0.46-1.04), linear p=0.079, linear BH q=, events/parameter=29.0, nonlinearity p=0.558, nonlinearity BH q=.

| Method | n | Events | BH q | HR | Cox p | Adjusted HR | Adjusted p | Marker PH p | Global PH p | RMST delta @ tau | RMST p | Notes |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| median | 102 | 29 | 0.052 | 0.49 (0.23-1.02) | 0.057 | 0.48 (0.22-1.05) | 0.065 | 0.310 | 0.096 | 83 @ 698 | 0.012 | No model-diagnostic caution recorded |

## Audit Hashes

| Method | Analysis ID | Reproducibility hash | Grouped records SHA-256 | Continuous records SHA-256 |
| --- | --- | --- | --- | --- |
| median | `e83445cd7b6e48b2b66f0bf0188d72d2` | `fc08de00240388bfebb11e01b1042788ebea511c765a125210291fa0580db97a` | `3c551f79c8b145378bc6609fce9ed3e1968a4e9ceb948e87ba3bb7868cd4d99c` | `7d00f1c8072a937725e832ce2e579786945df7ee0b8b06a1fa526083da74f98a` |

## RMST Tau Sensitivity

| Method | Tau fraction | Tau days | RMST delta days | RMST p |
| --- | ---: | ---: | ---: | ---: |
| median | 0.75 | 523.9 | 43 | 0.012 |
| median | 0.90 | 628.6 | 66 | 0.013 |
| median | 1.00 | 698.5 | 83 | 0.012 |
