# Publication Benchmarks

This directory stores compact benchmark outputs used to develop the
Bioinformatics Application Note narrative.

## KIRC CA9 Cutpoint Benchmark

Location:

```text
docs/publication/benchmark/kirc_ca9_cutpoint_benchmark/
```

Reproduce from a running local TCGA Explorer stack:

```sh
scripts/publication/run_cutpoint_benchmark.py
```

The benchmark calls the HTTP API at `http://localhost:3000/tcga_explorer` by
default, runs TCGA-KIRC CA9 overall survival analyses across the two-group
dichotomization methods, computes BH-adjusted log-rank p-values, applies the
downstream robustness rule and writes:

- `summary.csv`: compact machine-readable result table;
- `summary.md`: human-readable result table and audit hashes;
- `benchmark_metadata.json`: run metadata, endpoint status and health payload;
- `benchmark_results.raw.json`: full batch API response without raw patient rows;
- `manuscript/bioinformatics_app_note/tables/kirc_ca9_cutpoint_benchmark.tex`:
  manuscript-ready LaTeX table.

Full audit bundles remain in local `artifacts/` and are intentionally not
tracked in git.

## Single-Gene Benchmark Suite

Run all current single-gene benchmarks:

```sh
scripts/publication/run_single_gene_benchmark_suite.py
```

Cases:

- TCGA-KIRC CA9 OS;
- TCGA-BRCA MKI67 OS;
- TCGA-BRCA MKI67 PFI;
- TCGA-SKCM PDCD1 OS;
- TCGA-LUAD CD274 OS;
- TCGA-LUAD CD274 PFI.

Aggregate outputs:

- `single_gene_benchmark_overview.csv`;
- `single_gene_benchmark_overview.md`;
- `manuscript/bioinformatics_app_note/tables/single_gene_benchmark_overview.tex`.

The suite keeps full method-level summaries in each per-case directory and
stores only compact API responses, summaries and hashes in git.

## Feature Benchmark Suite

Run the current feature-level benchmarks:

```sh
scripts/publication/run_feature_benchmarks.py
```

Cases:

- TCGA-KIRC weighted hypoxia z-score signature, OS, median split;
- TCGA-SKCM effector x exhaustion two-signature workflow, OS, median split plus
  continuous interaction Cox;
- CA9 pan-cancer continuous Cox/FDR scan, OS, same endpoint across cohorts.

Aggregate outputs:

- `feature_benchmarks/feature_benchmark_summary.csv`;
- `feature_benchmarks/feature_benchmark_summary.md`;
- `manuscript/bioinformatics_app_note/tables/feature_benchmark_summary.tex`.

Current interpretation: the hypoxia signature shows nominal log-rank and RMST
evidence but fails adjusted Cox and PH criteria; the SKCM two-signature
interaction is not significant; and the CA9 pan-cancer scan finds cohort-level
FDR signals with a modest heterogeneous random-effects estimate. These are
software workflow benchmarks, not biomarker discovery claims.
