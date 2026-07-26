# Maxstat Selection Diagnostic

For each scenario, the continuous Cox coefficient is projected onto the observed expression-mean difference between the two groups. This places the continuous-implied and grouped HRs on the same contrast before comparing their absolute log-HR.
The ratio is descriptive evidence of contrast amplification, not a selection-corrected confidence interval for the maxstat HR.
Lau94 approximations are bounded to [0,1] for inference; the machine-readable table preserves the raw approximation and a clamping flag.

| Cohort | Gene | Endpoint | Continuous HR/SD | Median: delta SD | Median implied/grouped HR | Median amplification | Maxstat: delta SD | Maxstat implied/grouped HR | Maxstat amplification | Maxstat/median | Lau94 p | Holm p |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| TCGA-LIHC | CDC20 | OS | 1.65 | 1.64 | 2.28/2.07 | 0.88 | 1.66 | 2.29/2.60 | 1.15 | 1.31 | 5.61e-06 | 2.24e-05 |
| TCGA-LUAD | BIRC5 | OS | 1.34 | 1.64 | 1.61/1.70 | 1.11 | 1.63 | 1.61/1.84 | 1.28 | 1.15 | 0.003 | 0.008 |
| TCGA-UVM | BAP1 | DSS | 0.51 | 1.60 | 0.34/0.17 | 1.64 | NA | NA/NA | NA | NA | 7.65e-05 | 3.06e-04 |
| TCGA-LGG | EMP3 | OS | 2.54 | 1.47 | 3.94/2.98 | 0.80 | 2.22 | 7.94/11.07 | 1.16 | 2.20 | 3.48e-23 | 1.39e-22 |
| TCGA-KIRC | CA9 | OS | 0.91 | 1.05 | 0.90/0.68 | 3.81 | 1.34 | 0.88/0.59 | 4.14 | 1.39 | 0.032 | 0.096 |
| TCGA-BRCA | MKI67 | OS | 1.09 | 1.59 | 1.15/1.09 | 0.65 | 1.66 | 1.16/1.37 | 2.15 | 3.48 | 1.000 | 1.000 |
| TCGA-BRCA | MKI67 | PFI | 1.16 | 1.59 | 1.26/1.23 | 0.90 | 1.89 | 1.31/2.40 | 3.21 | 4.24 | 0.098 | 0.391 |
| TCGA-SKCM | PDCD1 | OS | 0.67 | 1.69 | 0.51/0.53 | 0.95 | 1.68 | 0.51/0.49 | 1.06 | 1.11 | 1.98e-05 | 3.97e-05 |
| TCGA-SKCM | TMEM176B | OS | 0.77 | 1.63 | 0.65/0.51 | 1.54 | 1.63 | 0.65/0.50 | 1.60 | 1.04 | 5.66e-05 | 1.70e-04 |
| TCGA-LUAD | CD274 | OS | 1.05 | 1.55 | 1.08/0.99 | 0.092 | 2.07 | 1.11/1.42 | 3.40 | 49.16 | 1.000 | 1.000 |
| TCGA-LUAD | CD274 | PFI | 1.04 | 1.55 | 1.07/1.06 | 0.83 | 1.65 | 1.07/1.38 | 4.62 | 5.95 | 0.958 | 1.000 |
