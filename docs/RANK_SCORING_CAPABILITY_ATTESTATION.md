# Rank-scoring availability

TRACE enables singscore, ssGSEA and AUCell only when the selected expression
layer satisfies all three conditions:

1. it contains at least 1,000 unique genes;
2. every value in the frozen gene-by-sample matrix is finite; and
3. the matrix contains at most 75,000,000 entries.

The dataset and expression-layer APIs report the selected layer, gene and
sample counts, total matrix entries, the current entry limit, missing-value
count and whether completeness was verified. A layer remains unavailable when
any of these facts is absent. TRACE never interprets missing legacy QC as zero.

## Historical releases

All 148 active public releases (149 expression layers) have a stored
finite-value count. Thirteen historical, inactive releases, comprising 14
expression layers, predate that field. They remain unavailable for
rank-based scoring when requested explicitly until their exact matrix is
attested. This does not affect their existing non-rank analyses.

An operator can inspect one historical release with a read-only dry run:

```bash
python -m app.repository.cli attest-rank-layer --release-id RELEASE_ID
```

Adding `--apply` records the result. Before writing, the command verifies the
release identity, matrix checksum, metadata dimensions, byte size and every
matrix value. It scans only the named release, does not overwrite existing
numerical QC, and aborts without a write if the release changes during the
scan.

No production release was modified while this safeguard was developed.

## Current size-limit impact

TCGA-BRCA contains 73,019,227 entries in its complete frozen matrix and
64,952,115 entries after its canonical primary-tumor, one-patient-one-sample
selection. Both fit under the 75,000,000-entry engine limit without changing
the release's gene universe. One active release, SCAN-B, contains 101,008,053
matrix entries and therefore exceeds that limit. TRACE keeps its other supported
analyses available but disables rank-based signature scoring for that layer
with the exact observed and permitted sizes. Mean, Z-score and Weighted remain
available alternatives where their own analysis requirements are met.
