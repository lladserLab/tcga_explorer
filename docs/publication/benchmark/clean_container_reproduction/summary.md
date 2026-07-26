# Clean-Container Reproduction Benchmark

Frozen patient-level inputs were re-executed without the TCGA-TRACE application, TCGA matrices, a database or network access.

- Base image: `rocker/r-ver@sha256:df26749182af64d5263bf64149d51a427b476ed28c4e046997143be3f97fdd7c`
- CRAN snapshot: `https://p3m.dev/cran/2026-07-25`
- Runtime: read-only container and capsule; only `/tmp` and `/output` writable.
- Numerical comparison: exact counts and categorical fields; quantity-aware absolute-plus-relative tolerances for probabilities, effects, times and other floating outputs.

| Environment | Architecture | Analysis | Runtime (s) | Numeric values | Max abs. error | Max rel. error | Differences | Status |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| native | arm64 | Single gene | 3.679 | 170 | 0 | 0 | 0 | passed |
| native | arm64 | Weighted signature | 3.126 | 131 | 0 | 0 | 0 | passed |
| native | arm64 | Two signatures | 2.446 | 159 | 4.06e-14 | 5.82e-14 | 0 | passed |
| linux/amd64 | amd64 | Single gene | 6.551 | 170 | 1.14e-13 | 4e-14 | 0 | passed |
| linux/amd64 | amd64 | Weighted signature | 5.714 | 131 | 2.84e-14 | 7.39e-15 | 0 | passed |
| linux/amd64 | amd64 | Two signatures | 4.613 | 159 | 4.33e-15 | 3.43e-14 | 0 | passed |

## Negative Controls

- Altered expression-snapshot SHA-256 detected: yes.
- Mutated patient input rejected in every environment: yes.

The local cross-architecture run uses Docker emulation and is not described as a second physical machine. The CI workflow repeats the same contract on an independent Linux/amd64 runner.
