# Submission Artifact Manifest

Status date: 2026-07-22.

Current working branch:

```text
feature/bioinformatics-readiness-20260721-210041
```

Submission-package lineage at time of writing includes:

```text
53f837a Prepare Bioinformatics submission package
dc19150 Add publication benchmark suite and comparator matrix
c671ef0 Add publication cutpoint benchmark evidence
f3ad3f2 Add RMST reporting and Bioinformatics manuscript draft
```

## Manuscript Sources

| Artifact | Path | Purpose |
| --- | --- | --- |
| Main manuscript | `manuscript/bioinformatics_app_note/main.tex` | Bioinformatics Application Note draft. |
| References | `manuscript/bioinformatics_app_note/references.bib` | Bibliography for main manuscript. |
| Workflow figure source | `manuscript/bioinformatics_app_note/figures/workflow.tex` | Reproducible vector source for Figure 1. |
| Supplement | `manuscript/bioinformatics_app_note/supplementary.tex` | Supplementary comparator and benchmark details. |
| Main benchmark tables | `manuscript/bioinformatics_app_note/tables/` | Generated LaTeX tables used by manuscript and supplement. |
| Build instructions | `manuscript/bioinformatics_app_note/README.md` | Manuscript build and journal-constraint notes. |

Generated PDFs are intentionally ignored by git and rebuilt with:

```sh
make -C manuscript/bioinformatics_app_note clean all
```

## Submission Support Files

| Artifact | Path | Purpose |
| --- | --- | --- |
| Readiness checklist | `manuscript/bioinformatics_app_note/submission/submission_readiness_checklist.md` | Go/no-go checklist against Bioinformatics requirements. |
| Cover letter draft | `manuscript/bioinformatics_app_note/submission/cover_letter_draft.md` | Editable cover letter with explicit placeholders. |
| Reviewer guide | `manuscript/bioinformatics_app_note/submission/reviewer_reproduction_guide.md` | End-to-end reproduction instructions for reviewers. |
| Artifact manifest | `manuscript/bioinformatics_app_note/submission/artifact_manifest.md` | This file. |

## Benchmark Evidence

| Artifact | Path | Purpose |
| --- | --- | --- |
| Benchmark README | `docs/publication/benchmark/README.md` | Benchmark reproduction and interpretation. |
| Single-gene overview | `docs/publication/benchmark/single_gene_benchmark_overview.md` | Aggregate cutpoint robustness result. |
| Feature overview | `docs/publication/benchmark/feature_benchmarks/feature_benchmark_summary.md` | Weighted signature, two-signature and pan-cancer result. |
| Comparator matrix | `docs/publication/comparator_matrix.md` | Literature-backed positioning against existing tools. |
| Publication readiness | `docs/BIOINFORMATICS_PUBLICATION_READINESS.md` | Critical gap analysis and submission gates. |
| Strategy document | `docs/publication/bioinformatics_app_note_strategy.md` | Bioinformatics Application Note narrative and benchmark strategy. |

## Reproduction Scripts

| Script | Purpose |
| --- | --- |
| `scripts/publication/run_cutpoint_benchmark.py` | Runs one marker-endpoint cutpoint benchmark. |
| `scripts/publication/run_single_gene_benchmark_suite.py` | Runs six single-gene endpoint scenarios across five cutpoint methods. |
| `scripts/publication/run_feature_benchmarks.py` | Runs weighted signature, two-signature and pan-cancer workflow benchmarks. |

## Current Submission Blockers

These items require project-owner decisions before journal submission:

- Final author list, affiliations and corresponding-author email.
- Funding statement.
- Conflict-of-interest statement.
- Explicit software license.
- Reviewer-accessible or public repository URL.
- Public web-demo URL or Docker-only reviewer access statement.
- Stable archive DOI or release URL.
