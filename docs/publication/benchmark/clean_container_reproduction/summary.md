# Clean-Container Reproduction Benchmark

Frozen patient-level inputs were re-executed without the TCGA-TRACE application, TCGA matrices, a database or network access.

- Base image: `rocker/r-ver@sha256:df26749182af64d5263bf64149d51a427b476ed28c4e046997143be3f97fdd7c`
- CRAN snapshot: `https://p3m.dev/cran/2026-07-25`
- Runtime: read-only container and capsule; only `/tmp` and `/output` writable.
- Numerical comparison: exact counts and categorical fields; quantity-aware absolute-plus-relative tolerances for probabilities, effects, times and other floating outputs.

| Environment | Architecture | Analysis | Runtime (s) | Numeric values | Max abs. error | Max rel. error | Differences | Status |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| native | arm64 | Single gene | 4.241 | 750 | 0 | 0 | 0 | passed |
| native | arm64 | Weighted signature | 3.202 | 155 | 0 | 0 | 0 | passed |
| native | arm64 | Two signatures | 2.931 | 902 | 4.06e-14 | 5.82e-14 | 0 | passed |
| linux/amd64 | amd64 | Single gene | 10.122 | 750 | 1.14e-13 | 5.53e-14 | 0 | passed |
| linux/amd64 | amd64 | Weighted signature | 6.072 | 155 | 2.84e-14 | 7.39e-15 | 0 | passed |
| linux/amd64 | amd64 | Two signatures | 5.571 | 902 | 6.48e-14 | 7.99e-14 | 0 | passed |

## Negative Controls

- Altered expression-snapshot SHA-256 detected: yes.
- Mutated patient input rejected in every environment: yes.

The local cross-architecture run uses Docker emulation and is not described as a second physical machine. The CI workflow repeats the same contract on an independent Linux/amd64 runner.
