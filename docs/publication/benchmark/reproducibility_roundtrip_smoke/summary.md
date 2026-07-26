# Reproducibility round-trip smoke test

- Run started: 2026-07-24T01:01:02Z
- Run finished: 2026-07-24T01:01:06Z
- Completed analyses: 1/1
- Cached analyses in this run: 0/1
- API base URL: `https://apps.cienciavida.org/tcga_explorer`
- Cohort: `TCGA-KIRC`
- Gene: `CA9`
- Endpoint: `OS`
- Expression scale: `log2_tpm`
- BH family: completed cutpoint methods in this scenario.
- No composite retention rule is applied. Log-rank, Cox and RMST are related summaries of the same outcomes and are not counted as independent barriers.
- Marker-specific PH and global model PH are reported separately as interpretation diagnostics.
- Maxstat is outcome-optimized. Its corrected rank-statistic p-value is reported, while grouped HR, confidence intervals and RMST remain post-selection.

| Method | n | Events | BH q | HR | Cox p | Adjusted HR | Adjusted p | Marker PH p | Global PH p | RMST delta @ tau | RMST p | Notes |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| median | 531 | 175 | 0.013 | 0.68 (0.51-0.92) | 0.013 | 0.83 (0.58-1.20) | 0.325 | 0.487 | 3.67e-04 | 427 @ 4074 | 0.011 | Global PH caution; marker term not flagged |

## Audit Hashes

| Method | Analysis ID | Reproducibility hash | Patient records SHA-256 |
| --- | --- | --- | --- |
| median | `a82a498f630041ae97f0a542e52ed72f` | `298f36961f30a5709d683bef83b44fb2358fc25d5319d6aa8048d9d3211d288b` | `bb669bb6df0671f8dee8b4eeacc068e56bd8c8de86363ea103e4ddfcc6c693a9` |

## RMST Tau Sensitivity

| Method | Tau fraction | Tau days | RMST delta days | RMST p |
| --- | ---: | ---: | ---: | ---: |
| median | 0.75 | 3055.5 | 248 | 0.022 |
| median | 0.90 | 3666.6 | 331 | 0.020 |
| median | 1.00 | 4074.0 | 427 | 0.011 |
