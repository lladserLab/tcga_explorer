# TCGA Explorer Methods History

This changelog tracks methodological behavior exposed to users. It is not a Git commit log. Update it when a change affects scoring, endpoint QC, patient selection, model outputs, robustness criteria, audit exports or manuscript-facing interpretation.

## TCGA KM Explorer v0.1.0 - Functional Baseline

### Added

#### Platform And Navigation

- Dockerized web application with React/Vite frontend, FastAPI backend, PostgreSQL database and Nginx reverse proxy.
- Main workspace navigation with KM Analysis, Compare Analyses, Pan-cancer, Dataset Summary and Help & Methods modules.
- Backend healthcheck with cache status, data dates, application version and pipeline versions.
- Warm startup RNA cache loading for all configured TCGA cohorts.
- Apache/Nginx and Docker Compose deployment documentation.

#### Cohort, Gene And Patient Inputs

- TCGA cohort selector with search by TCGA code, cancer name, primary site or disease description.
- Full cancer-name display alongside TCGA cohort codes.
- Cohort quick summary with RNA samples, patients, tumors and primary site.
- Per-cohort gene search with autocomplete.
- Gene selection through removable chips.
- Multiple genes in single-gene mode, producing one Kaplan-Meier analysis per gene.
- Common gene alias resolution, including legacy symbols mapped to current gene symbols.
- One RNA sample per TCGA participant using explicit biospecimen priority.

#### Expression And Signature Scoring

- Selectable RNA scales: log2(TPM + 1), log2(CPM + 1), log2(FPKM + 1) and log2(FPKM-UQ + 1).
- Single-signature analysis with mean, z-score and weighted scoring.
- Weighted signature syntax using `GENE:weight`.
- Combined analysis of two independent signatures.
- Crossed two-signature stratification by median x median or tertiles x tertiles.
- Continuous z-scored signature scores for two-signature interaction modeling.

#### Endpoints, Cutpoints And Clinical QC

- TCGA-CDR survival endpoints OS, PFI, DFI and DSS when available.
- OS fallback from TCGA clinical metadata when TCGA-CDR is not configured.
- Per-cohort endpoint availability checks with minimum patient and event QC.
- Cutpoint methods: maxstat, median, tertiles, upper quartile, outer quartiles and custom percentile.
- Clinical filters by sample type, stage, grade, gender, race, minimum age, maximum age and maximum follow-up.
- Administrative censoring when maximum follow-up is defined.

#### KM Analysis Outputs

- Kaplan-Meier plots generated in R with `survival`, `survminer` and `ggplot2`.
- Plot options for confidence interval, risk table, colors, font family, font sizes, grid, title, aspect ratio and X-axis units in days, months or years.
- Analysis metrics including patients, events, log-rank p-value, hazard ratio, median survival, group counts and group event counts.
- Univariable Cox and adjusted Cox models for stage, grade and stage plus grade when evaluable.
- Proportional hazards diagnostics using `cox.zph`.
- Cox forest plot.
- RMST for two-group comparisons, including tau, difference, confidence interval and p-value.
- Expression distribution before cutpoint selection and per-analysis quality summary.
- REMARK-style methodology report per analysis.

#### Two-Signature Outputs

- Cox interaction models for two signatures using `signature_A_z + signature_B_z + interaction`.
- Combined-group Kaplan-Meier outputs for median x median and tertile x tertile grouping.
- Shared plot export, audit and methodology outputs for combined-signature analyses.

#### Compare Analyses And Robustness

- Gene x cutpoint comparison page.
- Batch execution with up to 10 parallel analyses.
- Visual comparison matrix with Kaplan-Meier thumbnails per cell.
- Multiple-testing correction using Benjamini-Hochberg and Bonferroni adjustment across completed comparisons.
- Cutpoint robustness summary using BH, Cox, adjusted Cox, RMST and PH diagnostics.
- Explicit "Run all 5 cutpoint methods" control for dichotomization robustness.

#### Pan-Cancer Analysis

- Pan-cancer scan with continuous Cox per cohort and within-cohort expression z-scoring.
- Pan-cancer endpoint modes: same endpoint, death-like, progression-like and best available.
- Pan-cancer outputs with FDR, effect direction, index-cohort concordance and random-effects meta-analysis.
- Pan-cancer visualizations: forest plot, concordance map, evidence landscape, power/precision map and cohort table.
- Precomputed immune pan-cancer atlas with gene, cohort, term and recurrent-signal summaries.
- Immune atlas downloads for genes, cohorts, terms, results, panel, manifest and methodology.

#### Dataset Summary

- Dataset Summary page with global KPIs, data dates, source status, endpoint coverage and cohort table.
- Dataset visualizations including cohort dot plot, donut charts, age histogram, metadata coverage matrix and primary-site distribution.
- Cohort filter in Dataset Summary.
- CSV export for dataset summary.

#### Downloads, Caching And Data Operations

- Per-analysis downloads: PNG, SVG, CSV, Cox PNG/SVG, metrics JSON, methodology TXT, audit JSON, audit HTML and ZIP bundle.
- On-demand SVG generation to reduce initial latency.
- Non-blocking download notifications.
- Analysis cache keyed by parameter hash and data version.
- Reproducible audit report with parameters, endpoint, sample selection, patient records, hashes, software versions and artifact checksums.
- Incremental TCGA RNA and TCGA-CDR synchronization through the GDC API.
- `check` and `apply` commands for data updates.
- Download validation by checksum, file size and expected columns.
- Atomic promotion of updated files, backups and derived-cache invalidation.
- Weekly TCGA update script.
- RNA bulk transformation documentation.

#### Publication Materials

- Comparative tool matrix for publication positioning.
- Benchmark protocol and benchmark scripts.
- Manuscript-ready tables and publication-readiness documentation.

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
