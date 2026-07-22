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
