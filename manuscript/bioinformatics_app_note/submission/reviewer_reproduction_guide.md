# Reviewer Reproduction Guide

Status date: 2026-07-22.

This guide describes how to reproduce the TCGA Explorer Application Note
artifacts from a reviewer-accessible checkout.

## 1. Required Local Inputs

TCGA Explorer is Dockerized, but it expects a local TCGA RNA-seq data snapshot
mounted from the sibling directory:

```text
../TCGA
```

TCGA-CDR endpoints are enabled when the official clinical file is available at:

```text
clinical/TCGA-CDR-SupplementalTableS1.xlsx
```

The repository tracks compact benchmark summaries and API responses. Full
patient-level audit exports are generated locally by the app and are not tracked
in git.

## 2. Start the Application

From the repository root:

```sh
docker compose up -d --build
```

Open:

```text
http://localhost:3000/tcga_explorer/
```

Health and API documentation:

```text
http://localhost:3000/tcga_explorer/api/health
http://localhost:3000/tcga_explorer/api/docs
```

The first startup may take tens of minutes if expression caches under
`derived/` must be rebuilt.

## 3. Reproduce Manuscript PDFs

The host does not need a local LaTeX installation:

```sh
make -C manuscript/bioinformatics_app_note clean all
```

Expected outputs:

```text
manuscript/bioinformatics_app_note/build/tcga_explorer_bioinformatics_app_note.pdf
manuscript/bioinformatics_app_note/build/tcga_explorer_bioinformatics_supplement.pdf
```

## 4. Reproduce Benchmark Tables

With the app running at `http://localhost:3000/tcga_explorer`, run:

```sh
scripts/publication/run_single_gene_benchmark_suite.py
scripts/publication/run_feature_benchmarks.py
```

Expected aggregate outputs:

```text
docs/publication/benchmark/single_gene_benchmark_overview.md
docs/publication/benchmark/feature_benchmarks/feature_benchmark_summary.md
manuscript/bioinformatics_app_note/tables/single_gene_benchmark_overview.tex
manuscript/bioinformatics_app_note/tables/feature_benchmark_summary.tex
```

The single-gene suite runs 30 analyses: six marker-endpoint scenarios crossed
with five two-group cutpoint methods. The feature suite runs a weighted
signature example, a two-signature interaction example and a pan-cancer Cox/FDR
example.

## 5. Reproduce Validation Checks

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

Current expected backend test result:

```text
21 passed
```

## 6. Reviewer-Facing Claims to Check

- TCGA Explorer does not claim novelty for Kaplan-Meier estimation,
  two-predictor survival interaction or gene-set survival.
- The stated gap is the combined audit workflow: endpoint provenance,
  sample-selection rule, exact patient rows, software versions, artifact hashes,
  PH diagnostics, RMST and cutpoint robustness.
- The main comparator prior art explicitly includes GEPIA2, cSurvival,
  DoSurvive and PESSA.
- Benchmark summaries distinguish exploratory associations from robust signals
  after downstream Cox, PH and RMST checks.
