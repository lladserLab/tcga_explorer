# TCGA Explorer Bioinformatics Application Note

This folder contains the working Bioinformatics Application Note draft.

The manuscript is intentionally framed around the reproducibility and model-QC
gap: audit reports, exact patient records, endpoint provenance, proportional
hazards diagnostics, RMST and cutpoint robustness. Two-signature analysis is
included as a supported workflow, not as the primary novelty claim, because
cSurvival is prior art for two-predictor survival interaction.

## Build

The host does not need a local LaTeX installation. Build with Docker:

```sh
make pdf
```

The output is written to:

```text
build/tcga_explorer_bioinformatics_app_note.pdf
```

Build the supplement:

```sh
make supplement
```

Build both PDFs:

```sh
make all
```

Supplement output:

```text
build/tcga_explorer_bioinformatics_supplement.pdf
```

The default image can be overridden:

```sh
TEX_IMAGE=texlive/texlive:latest make pdf
```

## Journal Constraints

The draft targets Bioinformatics Application Notes, which are short reports of
software or database resources. The manuscript should remain near the official
Application Note budget, approximately 2600 words or approximately 2000 words
with one figure.

Before submission, replace placeholders for authors, affiliation, repository,
license and public web demo.

## Submission Files

- `submission/submission_readiness_checklist.md`: current go/no-go checklist
  against Bioinformatics Application Note requirements.
- `submission/cover_letter_draft.md`: reviewer-facing cover letter draft.
- `figures/workflow.tex`: reproducible vector source for Figure 1.
- `supplementary.tex`: supplementary comparator and benchmark tables.
