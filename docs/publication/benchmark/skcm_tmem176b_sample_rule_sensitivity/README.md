# TCGA-SKCM TMEM176B OS Sample-Type Sensitivity

Status date: 2026-07-24.

This record checks whether the TCGA-SKCM TMEM176B continuous and median-split results are
sensitive to including all eligible RNA-seq samples versus restricting
to primary or metastatic samples. The goal is not to select the most
favorable subset; it is to expose a sample-composition choice that can
change the downstream conclusion.

Continuous Cox and grouped log-rank p-values use separate BH families across the three sample rules.

| Sample rule | Continuous n/events | HR per SD | Continuous q | Adjusted p | Nonlinearity p | Grouped n/events | Grouped q | RMST delta @ tau | Notes |
| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| All eligible | 453/213 | 0.77 (0.67-0.87) | 2.13e-04 | 7.62e-07 | 0.100 | 453/213 | 3.95e-06 | 231 @ 1826 | Global PH caution; marker term not flagged |
| Primary only | 102/29 | 0.96 (0.67-1.38) | 0.841 | 0.990 | 0.057 | 102/29 | 0.630 | 6 @ 698 | No model-diagnostic caution recorded |
| Metastatic only | 353/186 | 0.77 (0.67-0.89) | 4.27e-04 | 2.71e-06 | 0.259 | 353/186 | 3.62e-04 | 156 @ 1826 | Global PH caution; marker term not flagged |

Interpretation: continuous-model BH q <= 0.05 for All eligible, Metastatic only; grouped log-rank BH q <= 0.05 for All eligible, Metastatic only; marker-specific grouped PH caution for none. TCGA-SKCM sample composition should therefore be reported as a sensitivity setting.

Per-case summaries and run hashes are stored under the three
subdirectories in this folder.
