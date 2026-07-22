# TCGA Explorer Methods History

This changelog tracks methodological behavior exposed to users. It is not a Git commit log. Update it when a change affects scoring, endpoint QC, patient selection, model outputs, robustness criteria, audit exports or manuscript-facing interpretation.

## Current Application State - July 2026

### clinical-adjusted-cox-audit-rmst-v4.2

Single-signature survival pipeline.

- Uses TCGA-CDR endpoints when available: OS, DSS, PFI and DFI.
- Enables endpoints only after minimum patient and event QC.
- Keeps one prioritized RNA biospecimen per patient for patient-level survival analysis.
- Supports single gene, mean signature, z-score signature and weighted signature scoring.
- Fits Kaplan-Meier, log-rank, univariable Cox and clinically adjusted Cox models when covariates are evaluable.
- Reports cox.zph proportional hazards diagnostics.
- Reports RMST for two-group comparisons.
- Exports reproducibility audit reports with payload hash, patient records, model outputs, software versions and artifact checksums.

### combined-signatures-interaction-cox-audit-rmst-v2.3

Two-signature combined group pipeline.

- Scores Signature A and Signature B independently.
- Supports single, mean, z-score and weighted scoring for each signature.
- Defaults multi-gene signatures to z-score scoring because each gene contributes on a comparable scale.
- Creates median x median four-group comparisons or tertile x tertile multi-group comparisons.
- Fits interaction Cox models on continuous signature z-scores.
- Preserves the same audit and plot export behavior used by the single-signature pipeline.

### pancancer-cox-v1.0

Pan-cancer continuous Cox pipeline.

- Fits one Cox model per cancer using expression z-scored within each cohort.
- Reports HR per +1 SD expression.
- Applies BH-FDR adjustment across modeled cohorts.
- Summarizes effect direction concordance and random-effects meta-analysis.
- Supports endpoint modes: same endpoint, death-like, progression-like and best available.

### cutpoint-robustness-v1.0

Dichotomization robustness panel.

- Runs maxstat, median, upper quartile, outer quartiles and selected percentile cutpoints.
- Applies BH and Bonferroni adjustment across completed comparison cells.
- Flags downstream robustness using log-rank, Cox, adjusted Cox, RMST direction and PH diagnostics.
- Clarifies that maxstat is exploratory because the cutpoint is optimized against survival separation.

### dataset-qc-v1.0

Dataset inventory and sample QC.

- Summarizes cohort, sample, patient and endpoint coverage.
- Tracks data source dates, RNA cache generation and database import time.
- Documents TCGA source status and endpoint availability for analysis decisions.

