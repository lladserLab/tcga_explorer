# Final Submission Decisions

Status date: 2026-07-22.

This file collects the project-owner decisions that must be filled before TCGA
Explorer can be submitted as a Bioinformatics Application Note. The technical
manuscript, comparison narrative, benchmark tables and PDF build are ready for
these values to be inserted.

## Required Manuscript Metadata

| Field | Current placeholder | Final value |
| --- | --- | --- |
| Author list | `Author One, Author Two, Author Three` | TODO |
| Affiliations | `Affiliation placeholder` | TODO |
| Corresponding author | `email@example.org` | TODO |
| Funding statement | `Funding placeholder` | TODO |
| Conflict of interest | `Conflict-of-interest statement placeholder` | TODO |

## Availability And Legal Decisions

| Field | Why it matters | Final value |
| --- | --- | --- |
| Software license | Bioinformatics requires software/data availability for non-commercial users. | TODO |
| Public or reviewer-accessible repository URL | Required for reviewer access and post-publication availability. | TODO |
| Stable release DOI or archive URL | Needed for a citable submitted version. | TODO |
| Public demo URL or Docker-only access statement | Needed to tell reviewers how to evaluate the web application. | TODO |
| Data availability note | Needed because full TCGA patient-level exports are generated locally and not tracked in git. | TODO |

## Recommended Defaults To Confirm

- Repository: `git@github.com:lladserLab/tcga_explorer.git`.
- Article type: Bioinformatics Application Note.
- Target title: `TCGA Explorer: Auditable and Robust Survival Analysis Workflows for TCGA Transcriptomic Biomarkers`.
- Contribution claim: auditable, endpoint-aware and model-QC-rich TCGA survival workflows with PH diagnostics, RMST and cutpoint robustness.
- Claims to avoid as primary novelty: first Kaplan-Meier tool, first two-biomarker survival tool, first gene-set survival tool.

## Current Technical Validation Snapshot

Validated on 2026-07-22:

- `make -C manuscript/bioinformatics_app_note clean all` completed.
- Main PDF: `manuscript/bioinformatics_app_note/build/tcga_explorer_bioinformatics_app_note.pdf`.
- Supplement PDF: `manuscript/bioinformatics_app_note/build/tcga_explorer_bioinformatics_supplement.pdf`.
- `texcount -inc -brief main.tex supplementary.tex` reports 853 main-text words for `main.tex`, below the Bioinformatics Application Note target budget.
- `python3 -m py_compile scripts/publication/run_cutpoint_benchmark.py scripts/publication/run_single_gene_benchmark_suite.py scripts/publication/run_feature_benchmarks.py` completed.
- Latest backend validation in this branch: `21 passed`.

## Final Pre-Submission Command

Run this after replacing the values above:

```sh
python3 -m py_compile \
  scripts/publication/run_cutpoint_benchmark.py \
  scripts/publication/run_single_gene_benchmark_suite.py \
  scripts/publication/run_feature_benchmarks.py

docker compose run --rm --no-deps \
  -v "$PWD/backend/tests:/app/tests:ro" \
  backend pytest -q /app/tests

make -C manuscript/bioinformatics_app_note clean all
git diff --check
```

