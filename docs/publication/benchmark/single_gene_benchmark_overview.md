# Single-Gene Cutpoint Benchmark Overview

The 11 marker-endpoint scenarios are frozen by `docs/publication/benchmark/scenario_registry_v1.json`. The panel was assembled after exploratory triage and is a software stress test, not a prospectively selected biomarker-validation sample.
OS is primary except for the registered UVM BAP1 DSS case. BRCA MKI67 PFI and LUAD CD274 PFI are endpoint sensitivities and cannot supersede their OS parent because of observed results.
The main manuscript emphasizes five literature-anchored scenarios. All rows, including unsupported and endpoint-sensitivity cases, remain visible.
The selected adjusted estimate in this frozen suite is the exact prespecified age-adjusted complete-case model; fixed stage/grade models remain auxiliary sensitivities in each raw result.

| Purpose | Cohort | Gene | Endpoint | Endpoint role | Continuous n/events | HR per SD | Linear q | Nonlinearity q | Cutpoints | Grouped Holm p<=.05 | Primary grouped profile | Age-adjusted p<=.05 | RMST p<=.05 | Marker PH | Low information | Firth | Profile |
| --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: | --- |
| Illustrative case | TCGA-LIHC | CDC20 | OS | primary | 365/130 | 1.65 | 3.69e-07 | 0.739 | 4 | 4 | all four | 4 | 4 | 4 | 0 | 0 | within-scenario Holm p <= 0.05 in 4/4; marker PH caution in 4/4 |
| Illustrative case | TCGA-LUAD | BIRC5 | OS | primary | 505/182 | 1.34 | 3.18e-04 | 0.806 | 4 | 3 | partial (3/4) | 4 | 3 | 0 | 0 | 0 | within-scenario Holm p <= 0.05 in 3/4; marker PH caution in 0/4 |
| Low-event diagnostic | TCGA-UVM | BAP1 | DSS | primary | 80/21 | 0.51 | 6.84e-04 | NA | 4 | 4 | all four | 1 | 4 | 0 | 1 | 3 | within-scenario Holm p <= 0.05 in 4/4; marker PH caution in 0/4 |
| Exploratory | TCGA-SKCM | TMEM176B | OS | primary | 453/213 | 0.77 | 1.95e-04 | 0.333 | 4 | 4 | all four | 4 | 4 | 0 | 0 | 0 | within-scenario Holm p <= 0.05 in 4/4; marker PH caution in 0/4 |
| PH diagnostic | TCGA-LGG | EMP3 | OS | primary | 511/125 | 2.54 | 3.40e-27 | 0.739 | 4 | 4 | all four | 4 | 4 | 3 | 0 | 1 | within-scenario Holm p <= 0.05 in 4/4; marker PH caution in 3/4 |
| Supplementary | TCGA-KIRC | CA9 | OS | primary | 531/175 | 0.91 | 0.231 | 0.022 | 4 | 0 | none | 2 | 2 | 0 | 0 | 0 | within-scenario Holm p <= 0.05 in 0/4; marker PH caution in 0/4 |
| Supplementary | TCGA-BRCA | MKI67 | OS | primary | 1080/151 | 1.09 | 0.320 | 0.766 | 4 | 0 | none | 2 | 0 | 0 | 0 | 0 | within-scenario Holm p <= 0.05 in 0/4; marker PH caution in 0/4 |
| Supplementary | TCGA-BRCA | MKI67 | PFI | sensitivity | 1080/145 | 1.16 | 0.117 | 0.144 | 4 | 0 | none | 1 | 1 | 0 | 0 | 0 | within-scenario Holm p <= 0.05 in 0/4; marker PH caution in 0/4 |
| Supplementary | TCGA-SKCM | PDCD1 | OS | primary | 453/213 | 0.67 | 4.67e-07 | 0.806 | 4 | 4 | all four | 4 | 4 | 1 | 0 | 0 | within-scenario Holm p <= 0.05 in 4/4; marker PH caution in 1/4 |
| Supplementary | TCGA-LUAD | CD274 | OS | primary | 505/182 | 1.05 | 0.530 | 0.766 | 4 | 0 | none | 0 | 0 | 0 | 0 | 0 | within-scenario Holm p <= 0.05 in 0/4; marker PH caution in 0/4 |
| Supplementary | TCGA-LUAD | CD274 | PFI | sensitivity | 505/208 | 1.04 | 0.530 | 0.739 | 4 | 0 | none | 1 | 1 | 0 | 0 | 0 | within-scenario Holm p <= 0.05 in 0/4; marker PH caution in 0/4 |
