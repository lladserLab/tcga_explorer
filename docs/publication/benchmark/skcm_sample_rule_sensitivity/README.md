# TCGA-SKCM PDCD1 OS Sample-Type Sensitivity

Status date: 2026-07-24.

This record checks whether the TCGA-SKCM PDCD1 continuous and median-split results are
sensitive to including all eligible RNA-seq samples versus restricting
to primary or metastatic samples. The goal is not to select the most
favorable subset; it is to expose a sample-composition choice that can
change the downstream conclusion.

Continuous Cox and grouped log-rank p-values use separate BH families across the three sample rules.

| Sample rule | Continuous n/events | HR per SD | Continuous q | Adjusted p | Nonlinearity p | Grouped n/events | Grouped q | RMST delta @ tau | Notes |
| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| All eligible | 453/213 | 0.67 (0.58-0.78) | 3.82e-07 | 5.66e-09 | 0.806 | 453/213 | 9.48e-06 | 218 @ 1826 | Global PH caution; marker term not flagged |
| Primary only | 102/29 | 0.69 (0.46-1.04) | 0.079 | 0.113 | 0.558 | 102/29 | 0.052 | 83 @ 698 | No model-diagnostic caution recorded |
| Metastatic only | 353/186 | 0.69 (0.59-0.81) | 5.81e-06 | 1.61e-07 | 0.988 | 353/186 | 1.65e-04 | 173 @ 1826 | Global PH caution; marker term not flagged |

Interpretation: continuous-model BH q <= 0.05 for All eligible, Metastatic only; grouped log-rank BH q <= 0.05 for All eligible, Metastatic only; marker-specific grouped PH caution for none. TCGA-SKCM sample composition should therefore be reported as a sensitivity setting.

Per-case summaries and run hashes are stored under the three
subdirectories in this folder.
