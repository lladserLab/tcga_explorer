# Cover Letter Draft

Dear Editors,

We are pleased to submit "TCGA Explorer: Auditable and Robust Survival Analysis
Workflows for TCGA Transcriptomic Biomarkers" for consideration as a
Bioinformatics Application Note.

TCGA Explorer is a Dockerized web application for endpoint-aware TCGA
transcriptomic survival analysis. The application supports TCGA-CDR OS, DSS,
DFI and PFI endpoints, one RNA-seq sample per participant, single-gene and
weighted signature scoring, two-signature stratification, Cox models,
pan-cancer Cox/FDR scans, proportional-hazards diagnostics, restricted mean
survival time and cutpoint robustness summaries.

The contribution is intentionally positioned as a reproducibility and
model-quality workflow rather than as a new Kaplan-Meier estimator or the first
two-biomarker survival tool. Existing resources such as GEPIA2, cSurvival,
DoSurvive and PESSA already provide important survival-analysis capabilities.
TCGA Explorer complements these resources by making the reproducibility object
the primary output: each completed analysis exports the request payload,
endpoint provenance, sample-selection rule, exact patient records, software
versions, artifact checksums and SHA-256 audit hashes together with PH, RMST and
cutpoint-robustness outputs.

The submitted package includes a main manuscript, supplementary material, a
literature-backed comparator matrix and reproducible benchmark scripts covering
single-gene cutpoint robustness, weighted signatures, two-signature interaction
and pan-cancer Cox/FDR workflows.

Before submission, replace the following placeholders:

- `[CORRESPONDING AUTHOR NAME AND EMAIL]`
- `[FINAL PUBLIC REPOSITORY URL]`
- `[SOFTWARE LICENSE]`
- `[ARCHIVAL DOI OR STABLE RELEASE URL]`
- `[PUBLIC DEMO URL OR REVIEWER ACCESS INSTRUCTIONS]`

Sincerely,

`[CORRESPONDING AUTHOR NAME]`
