# RNA Bulk Transformations Inventory

Generated: 2026-04-26

## Scope

This note records what RNA bulk expression values are present in the TCGA cohort data snapshot:

```text
/mnt/data1/Andres/TCGA
```

The goal is to avoid exposing transformation choices in the webapp unless they are backed by the TCGA cohort data snapshot or by a clearly labeled deterministic calculation from those files.

## Files Reviewed

All 33 TCGA cohort directories contain:

- `count_matrix.tsv`
- `dds.rds`
- `col_data.tsv`
- `clinical_data.tsv`

The repository also contains the original GDC download cache:

```text
/mnt/data1/Andres/TCGA/gdc_cache
```

The cache contains 11,505 files matching:

```text
*.rna_seq.augmented_star_gene_counts.tsv
```

For every TCGA cohort, the number of cached STAR-count TSV files matches the number of samples in `count_matrix.tsv`.

## Aggregated Matrix Currently Used By The App

`count_matrix.tsv` is an aggregated matrix with:

- rows = deduplicated gene symbols;
- columns = TCGA sample barcodes;
- values = integer `STAR - Counts` `unstranded` counts;
- 59,427 genes per cohort in the current summary table.

The download pipeline states:

```text
count_matrix.tsv - integer STAR-unstranded counts
dds.rds          - DESeqDataSet (DESeq() NOT called)
```

The pipeline code confirms:

- it selects the `unstranded` assay first;
- rounds the matrix;
- stores it as integer;
- deduplicates gene symbols by highest mean count;
- writes only that count matrix to `count_matrix.tsv`;
- builds `dds.rds` with `DESeqDataSetFromMatrix`;
- does not run `DESeq()`.

Therefore, `dds.rds` is a DESeq2 container around raw counts and sample metadata, not a stored normalized-expression artifact.

## Original GDC STAR-Counts Files

The cached GDC files have a uniform header across all inspected files:

```text
gene_id
gene_name
gene_type
unstranded
stranded_first
stranded_second
tpm_unstranded
fpkm_unstranded
fpkm_uq_unstranded
```

These are the RNA bulk expression value columns present in the original GDC cache.

## Backed Expression Choices

The expression choices backed by the TCGA cohort data snapshot are:

- `unstranded` raw counts: already materialized in `count_matrix.tsv` and `dds.rds`.
- `stranded_first` raw counts: present in individual cached GDC STAR-count TSV files.
- `stranded_second` raw counts: present in individual cached GDC STAR-count TSV files.
- `tpm_unstranded`: present in individual cached GDC STAR-count TSV files.
- `fpkm_unstranded`: present in individual cached GDC STAR-count TSV files.
- `fpkm_uq_unstranded`: present in individual cached GDC STAR-count TSV files.

The webapp currently computes `log2(CPM + 1)` from `count_matrix.tsv`. That is a deterministic calculation from the stored `unstranded` raw counts, but it is not a separate expression matrix on disk.

## Not Present As RNA Bulk Data In This Snapshot

Do not expose these as data-backed options unless a new, explicit processing step creates them and documents the method:

- DESeq2 normalized counts;
- DESeq2 VST;
- DESeq2 rlog;
- edgeR TMM;
- z-score expression;
- rank or percentile expression;
- arbitrary log transforms not tied to a source matrix in this snapshot.

## Implementation In The Webapp

The webapp now exposes survival-oriented log-scale expression choices backed by the TCGA cohort data snapshot:

- `log2(TPM + 1)`: computed from cached GDC `tpm_unstranded` values;
- `log2(CPM + 1)`: computed from `count_matrix.tsv` unstranded counts;
- `log2(FPKM + 1)`: computed from cached GDC `fpkm_unstranded` values;
- `log2(FPKM-UQ + 1)`: computed from cached GDC `fpkm_uq_unstranded` values.

For the GDC cached columns, the backend builds derived binary gene-by-sample matrix caches under:

```text
/app/derived/rna_bulk/matrices
```

In Docker this is mounted from:

```text
./derived/rna_bulk/matrices
```

The derived cache does two things:

- maps cached GDC STAR-count files to TCGA sample barcodes using count fingerprints against `count_matrix.tsv`;
- materializes `log2(TPM + 1)`, `log2(FPKM + 1)`, and `log2(FPKM-UQ + 1)` as binary float32 matrices before the frontend starts.

This avoids modifying `/mnt/data1/Andres/TCGA` and avoids slow first-analysis scans across sample-level GDC files. The first startup after clearing `./derived` can take tens of minutes because all cohort matrix caches are built up front.

Raw count, raw TPM, raw FPKM, z-score, VST, and rlog are not exposed in the first survival UI. Z-score is better reserved for future multi-gene signatures or penalized models. VST/rlog would require an explicit DESeq2 processing step because the current `dds.rds` files were created without running `DESeq()`.

Stranded count modes should only be exposed if we decide they are analytically useful for this survival workflow and materialize them with the same barcode alignment checks.
