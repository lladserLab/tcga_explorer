# Immune Pan-Cancer Atlas v2.1

This directory contains the compact publication record for
`immune_os_immport_all_v2_1`. The full model-level artifacts remain in the
versioned application artifact bundle.

## Frozen contract

- Pipeline: `immune-pancancer-primary-plus-ordinal-sensitivity-cox-audit-v2.1`
- ImmPort genes: 3,118
- Strict-OS cohorts prepared: 32
- Primary completed gene-cancer models: 96,779
- Primary global-FDR hits: 12,234
- Primary meta-FDR genes: 881
- Selected adjusted models evaluable: 72,633
- Selected adjusted global-FDR hits: 2,379
- Primary global-FDR hits retained: 2,212
- Primary global-FDR hits attenuated: 7,432
- Primary global-FDR direction flips: 169
- Primary global-FDR hits without evaluable adjustment: 2,421

The last quantity is the subset of primary global-FDR hits without an
availability-selected adjusted model, not all clinically non-evaluable
gene-cancer pairs. It is reported in the manuscript decomposition.

## Interpretation

The primary atlas remains the comparable cross-cancer estimand. Adjustment
families use different complete-case populations and therefore should not be
ranked by raw hit counts alone. Loss of global-FDR support can reflect clinical
confounding, reduced sample size, or both. Mixed availability-selected families
are never meta-analyzed.

## Reproducibility

- Audit schema: `tcga-trace-immune-pancancer-atlas-audit-v2`
- Audit reproducibility hash: `4d942e93715ec953f0501b13a818d2f19e34f21d851367057924f0af3c2d0252`
- Expression matrices pinned by SHA-256: 32
- Software: `{"R": "R version 4.4.2 (2024-10-31)", "jsonlite": "2.0.0", "python": "3.12.3", "survival": "3.8.9"}`
