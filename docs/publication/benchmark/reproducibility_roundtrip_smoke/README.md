# Reproducibility Round-Trip Smoke Test

> Historical artifact, superseded on 2026-07-24. This record used the former
> group-dependent RMST horizon and is not evidence for the current manuscript.
> Use `docs/publication/benchmark/reproducibility_benchmark/summary.md` and
> `scripts/publication/run_reproducibility_benchmark.py` instead.

Status date: 2026-07-23.

This directory records a fresh reviewer-facing reproducibility smoke test run
against the current TCGA-TRACE Docker stack.

## Analysis

Command:

```sh
scripts/publication/run_cutpoint_benchmark.py \
  --benchmark-id reproducibility_roundtrip_smoke \
  --title "Reproducibility round-trip smoke test" \
  --cohort TCGA-KIRC \
  --gene CA9 \
  --endpoint OS \
  --methods median \
  --time-unit years \
  --output-dir docs/publication/benchmark/reproducibility_roundtrip_smoke \
  --latex-table docs/publication/benchmark/reproducibility_roundtrip_smoke/roundtrip_smoke.tex
```

Result:

- Analysis ID: `a82a498f630041ae97f0a542e52ed72f`
- Cached: `False`
- Reproducibility hash:
  `298f36961f30a5709d683bef83b44fb2358fc25d5319d6aa8048d9d3211d288b`
- Patient-record SHA-256:
  `bb669bb6df0671f8dee8b4eeacc068e56bd8c8de86363ea103e4ddfcc6c693a9`

## RMST Tau Sensitivity

The same analysis records RMST at the primary tau and two shorter tau values.
Tau is defined as the smaller maximum follow-up time across the two expression
groups. This smoke run stores the following sensitivity record in
`benchmark_results.raw.json`:

| Tau fraction | Tau days | Tau years | RMST delta days | 95% CI days | p-value |
| ---: | ---: | ---: | ---: | --- | ---: |
| 0.75 | 3055.5 | 8.37 | 248 | 36 to 460 | 0.0219 |
| 0.90 | 3666.6 | 10.04 | 331 | 52 to 610 | 0.0199 |
| 1.00 | 4074.0 | 11.15 | 427 | 100 to 755 | 0.0105 |

## Round-Trip Verification

Command:

```sh
scripts/publication/verify_reproducibility_bundle.py \
  --rerun \
  --docker-compose-service backend \
  artifacts/a82a498f630041ae97f0a542e52ed72f \
  --json
```

Result: `passed`.

Verified checks:

- patient-record SHA-256 recomputation;
- reproducibility hash recomputation from request, data dates, patient-record
  digest and core results;
- artifact byte counts and SHA-256 checksums;
- R round-trip from `input.json` inside the backend Docker service;
- core statistical outputs from the rerun match `audit_report.json`.
