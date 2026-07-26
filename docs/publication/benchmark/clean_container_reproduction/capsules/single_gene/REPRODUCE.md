# Reproduce this TCGA-TRACE analysis

This directory contains the exact patient-level R input and statistical source
used for the exported analysis. It does not require TCGA matrices, PostgreSQL,
FastAPI or the TCGA-TRACE web application.

## Docker

```sh
docker build -f Dockerfile.reproduce -t tcga-trace-rerun .
mkdir -p rerun_output
docker run --rm --network none --read-only \
  --tmpfs /tmp:rw,noexec,nosuid,size=512m \
  -v "$PWD:/analysis:ro" \
  -v "$PWD/rerun_output:/output" \
  tcga-trace-rerun
```

The base image is fixed to `rocker/r-ver@sha256:df26749182af64d5263bf64149d51a427b476ed28c4e046997143be3f97fdd7c` and R packages are restored from
`renv.lock` using `https://p3m.dev/cran/2026-07-25`.

## Existing R installation

With the package versions in `renv.lock` available:

```sh
Rscript rerun_analysis.R rerun_output
```

`rerun_output/reproduction_result.json` reports package versions and whether
the core outputs match `metrics.json`. Counts and categorical fields must match
exactly; floating-point outputs use the quantity-aware absolute-plus-relative
policy recorded in both `reproduction_manifest.json` and the result, including
the maximum observed error for every metric class.
