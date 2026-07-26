# Cover Letter Draft

Dear Editors,

We are submitting "TCGA-TRACE: auditable survival analysis for TCGA
transcriptomic biomarkers" for consideration as a Bioinformatics Application
Note.

TCGA-TRACE (Transparent and Reproducible Analysis of Cancer Endpoints) is a
Dockerized web application for TCGA transcriptomic survival analysis. The
specific problem addressed is that endpoint choice, sample selection, cutpoint
and model diagnostics are often separated from the reported Kaplan-Meier
curve, making exploratory results difficult to audit.

The contribution is intentionally positioned as a reproducibility and
model-quality workflow rather than as a new Kaplan-Meier estimator or the first
two-biomarker survival tool. Existing resources such as GEPIA2, cSurvival,
DoSurvive and PESSA already provide important survival-analysis capabilities.
TCGA-TRACE instead makes the reproducibility record a standard output: each
analysis exports endpoint and sample provenance, exact patient records,
parameters, software versions and checksums together with PH, RMST and cutpoint
sensitivity.

The submitted package includes a main manuscript, supplementary material, a
literature-backed comparator matrix and reproducible benchmark scripts covering
44 single-gene/cutpoint analyses, weighted and crossed-signature examples,
continuous pan-cancer sensitivity, an executable three-class reconstruction
benchmark.
The cases deliberately retain PH violations, heterogeneous pooled effects and
external statistical disagreement to demonstrate qualified reporting rather
than selected significance. The repository also includes Dockerized tests, CI
checks and reviewer reproduction instructions.

Before submission, replace the following placeholders:

- Corresponding author: `[CORRESPONDING AUTHOR NAME AND EMAIL]`
- Submitting author ORCID: `[SUBMITTING AUTHOR ORCID]`
- Repository: `https://github.com/lladserLab/tcga_explorer`
- Software license: `[SOFTWARE LICENSE]`
- Release archive: `[ARCHIVAL DOI OR STABLE RELEASE URL]` (Zenodo)
- Reviewer access: `https://apps.cienciavida.org/tcga_explorer/`
- AI-use disclosure: `[FINAL PERMITTED AI-USE DISCLOSURE AFTER INDEPENDENT AUTHOR REVIEW]`
- Maintenance commitment: `[THREE-YEAR WEB-SERVICE MAINTENANCE COMMITMENT]`

AI-assisted drafting is broader than the common acceptable uses enumerated in
the current Bioinformatics policy. The corresponding author must independently
rewrite and verify this letter and the manuscript, disclose the assistance, and
confirm acceptability with the editorial office before submission.

Sincerely,

`[CORRESPONDING AUTHOR NAME]`
