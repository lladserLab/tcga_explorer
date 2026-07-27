# Curated External Bulk RNA-seq Repository

TCGA-TRACE can analyze public bulk RNA-seq cancer cohorts that are independent
of TCGA and have patient-linked clinical outcomes. This repository is a
curated validation surface. It is not an upload service, a study-integration
engine or a claim that an external cohort is population-matched to TCGA.

## Scope and invariants

A published release must satisfy all of the following:

- human bulk RNA-seq;
- no TCGA-derived patients or expression matrix;
- public source with an explicit license;
- documented source expression unit or an explicit provided-scale caveat;
- deterministic sample-to-patient linkage;
- at least 10 patients with both expression and one usable endpoint;
- at least 5 events for one endpoint;
- at least 5 censored observations for the same endpoint;
- at least 10,000 unique mapped gene symbols;
- immutable source snapshot, file checksums and derived-matrix checksum;
- one prespecified sample-selection rank per source sample.

TCGA-TRACE does not pool external cohorts with TCGA, batch-correct across
studies or convert different expression units onto a purported common scale.
Each analysis uses one exact dataset release. Pan-cancer analysis remains
TCGA-only in repository version 1.

## Curation states

The 33-cancer ledger uses distinct states:

| State | Meaning |
| --- | --- |
| `screening_candidate` | Public API screening found RNA-seq plus recognizable survival columns. No scientific or legal validation is implied. |
| `registered_spec` | A human-reviewed study specification exists, but its bundle has not necessarily been promoted. |
| `available` / `promoted` | The immutable bundle passed automated QC and the reviewed release is analyzable. |
| `search_in_progress` | No release has passed review; searching continues. |
| `evidence_gap` | A documented search found no eligible public cohort under the current policy. |

Candidate detection never changes a cancer type to `available`.

## Current coverage

As of 27 July 2026, 26 of the 33 TCGA cancer types have at least one
independent release that passes the complete policy. Counts below refer to the
default usable endpoint; additional endpoints remain available where listed
in each release manifest.

| Cancer | Dataset ID | Patients | Endpoint events | Genes | Expression |
| --- | --- | ---: | ---: | ---: | --- |
| ACC | `pmc-acc-jouinot-2022` | 85 | 33 OS | 39,736 | log2(count + 1) |
| BLCA | `cbioportal-blca-iatlas-imvigor210-2017` | 347 | 231 OS | 38,355 | supplied iAtlas TPM profile |
| BRCA | `geo-brca-scanb-gse96058-2018` | 3,273 | 336 OS | 30,861 | log2(FPKM + 0.1) |
| CESC | `gdc-cesc-htmcp-cc-2020` | 118 | 74 OS | 59,317 | log2(TPM + 1) |
| CHOL | `pmc-chol-ahn-2019` | 22 | 13 OS | 55,531 | log2(RPKM + 1) |
| COAD | `cbioportal-coad-cptac-2019` | 100 | 8 OS | 12,720 | supplied log2 RSEM-UQ |
| DLBC | `gdc-dlbc-nciccr-2018` | 234 | 98 OS | 59,317 | log2(TPM + 1) |
| ESCA | `pmc-esca-vanderzalm-2024` | 85 | 43 OS | 52,031 | supplied DESeq2 VST / RUVg |
| GBM | `gdc-gbm-cptac-2021` | 188 | 141 OS | 59,317 | log2(TPM + 1) |
| HNSC | `cbioportal-hnsc-cptac-gdc-2025` | 104 | 39 OS | 40,636 | log2(TPM + 1) |
| KIRC | `cbioportal-kirc-iatlas-choueiri-2016` | 16 | 5 OS | 38,355 | supplied log2 UQ counts |
| LAML | `cbioportal-laml-ohsu-2022` | 440 | 243 OS | 16,823 | supplied log2 RPKM |
| LGG | `cbioportal-lgg-glass-2022` | 23 | 14 OS | 24,617 | log2(TPM + 1) |
| LIHC | `icgc-lihc-liri-jp-2019` | 231 | 42 OS | 13,405 | log2(FPKM + 1) |
| LUAD | `cbioportal-luad-cas-2020` | 51 | 15 OS | 10,611 | log2(FPKM + 1) |
| LUSC | `cbioportal-lusc-cptac-gdc-2025` | 103 | 32 OS | 40,636 | log2(TPM + 1) |
| MESO | `pmc-meso-nci-2023` | 99 | 56 OS | 15,076 | supplied TMM log2 CPM |
| OV | `cbioportal-ov-pog570-2020` | 12 | 6 OS | 38,168 | log2(RPKM + 1) |
| PAAD | `cbioportal-paad-iatlas-prince-2022` | 63 | 15 OS | 38,355 | supplied log2 UQ counts |
| PCPG | `cbioportal-pcpg-a5-2025` | 68 | 19 OS | 28,475 | supplied TMM log2 CPM |
| PRAD | `cbioportal-prad-su2c-2019` | 65 | 39 OS | 18,374 | log2(FPKM + 1) |
| READ | `cbioportal-read-msk-2022` | 97 | 13 OS | 19,100 | supplied RNA-seq scale |
| SARC | `cbioportal-sarc-pog570-2020` | 31 | 23 OS | 38,168 | log2(RPKM + 1) |
| SKCM | `cbioportal-skcm-dfci-2015` | 40 | 27 OS | 21,623 | log2(RPKM + 1) |
| STAD | `gdc-stad-cptac-2026` | 138 | 18 OS | 59,317 | log2(TPM + 1) |
| UCEC | `cbioportal-ucec-cptac-gdc-2025` | 225 | 34 OS | 40,636 | log2(TPM + 1) |

The precise release ID, source snapshot, checksums, endpoint definitions,
scale caveat and license are authoritative in each manifest and API response.
A profile name such as TPM is not interpreted as an untransformed unit when
the source does not document that property. Matrix downloads are exposed only
when the release records redistribution as allowed.

## Documented evidence gaps

Seven cancer types currently lack an eligible open cohort. These are
evidence gaps under the stated policy, not claims that no relevant biological
data exist.

| Cancer | Best public lead reviewed | Why it is not a release |
| --- | --- | --- |
| KICH | CPTAC-3; GSE312695 | Two endpoint-complete CPTAC-3 cases; the newer ten-tumor GEO subset omits patient-level outcomes. |
| KIRP | CPTAC-3; GSE312695 | Nine usable CPTAC-3 cases with one event; the 27-tumor GEO subset omits patient-level outcomes. |
| TGCT | GSE99420 | The relapse-linked cohort is an expression array, not RNA-seq. |
| THCA | GSE310793; GSE288945 | The large matrix lacks patient-level survival; the smaller cohort provides recurrence class without event time. |
| THYM | GSE181815 | Nine RNA profiles are available and individual survival time is absent. |
| UCS | GSE128630; UTCA-FR | The GEO matrix lacks individual survival; the ICGC project has no open RNA-seq expression object. |
| UVM | GSE317536; GSE202687 | The former is a roughly 2,570-feature targeted panel; the latter has only nine patients. |

The reviewed accessions, rejection reason and review date are machine-readable
in `repository_registry/coverage.json`. A cancer can move from
`evidence_gap` to `available` without changing the policy when a suitable
public release appears.

## Tracked registry and untracked data

Human-reviewed metadata is tracked in Git:

```text
repository_registry/
  cancer_types.json
  coverage.json
  discovery/
  studies/
```

Downloaded source files, binary matrices and promoted releases are local data
and are ignored by Git:

```text
external_repository_staging/
external_repository/
```

Production should use a persistent host directory:

```text
/mnt/data2/tcga_trace_repository
```

mounted read-only into the running backend and worker as:

```text
/data/cancer_repository
```

Promotion requires a short-lived curator process with a writable repository
mount. Normal web and worker containers do not write the repository.

## Reproducible workflow

Generate the current cBioPortal screening report:

```bash
docker compose run --rm \
  -v "$PWD/repository_registry:/app/repository_registry" \
  backend \
  python3 -m app.repository.cli discover-cbioportal \
  --output /app/repository_registry/discovery/cbioportal-YYYY-MM-DD.json
```

This screen excludes obvious TCGA, TARGET, PCAWG and cell-line accessions,
requires at least 10 reported RNA-seq samples, and looks for paired patient
survival status/time fields. Every hit still requires manual review.

Build any reviewed study specification using its declared adapter:

```bash
docker compose run --rm \
  -v "$PWD/external_repository_staging:/staging" \
  backend python3 -m app.repository.cli build-study \
  --spec /app/repository_registry/studies/STUDY.json \
  --output /staging/DATASET_ID
```

Validate without touching the database or published repository:

```bash
docker compose run --rm \
  -v "$PWD/external_repository_staging:/staging:ro" \
  backend python3 -m app.repository.cli validate \
  --bundle /staging/DATASET_ID
```

Promote only after reviewing the generated manifest, QC, source scale,
license, endpoint semantics and independence evidence:

```bash
docker run --rm \
  --network tcga_explorer_default \
  -e DATABASE_URL='postgresql+psycopg://tcga:tcga@postgres:5432/tcga_explorer' \
  -e CANCER_REPOSITORY_DIR=/data/cancer_repository \
  -e CANCER_REPOSITORY_REGISTRY_DIR=/app/repository_registry \
  -v "$PWD/external_repository_staging:/staging:ro" \
  -v "/mnt/data2/tcga_trace_repository:/data/cancer_repository:rw" \
  tcga_explorer-backend \
  python3 -m app.repository.cli promote \
  --bundle /staging/DATASET_ID
```

Promotion copies into:

```text
studies/<dataset_id>/releases/<release_id>/
```

Existing release directories are immutable. A repeated release ID with a
different canonical manifest hash is rejected.

## Bundle contents

Each bundle contains:

- original source files and their SHA-256 values;
- source-to-canonical gene mapping snapshot;
- one row-major little-endian float32 matrix per expression layer;
- matrix metadata with exact sample order;
- canonical gene symbols and matrix row numbers;
- patient and sample tables;
- endpoint values in days with raw source values retained;
- one canonical `manifest.json`.

The database stores catalog and row indexes. Expression values remain in the
immutable matrix file and are read by gene row on demand.

## Analysis behavior

Repository releases are available in:

- Survival;
- Compare Analyses;
- Multiverse.

The request pins:

```json
{
  "cohort": "TCGA-BLCA",
  "dataset_id": "cbioportal-blca-iatlas-imvigor210-2017",
  "dataset_release_id": "cbioportal-blca-iatlas-imvigor210-2017-1da5c747e4fd",
  "expression_layer_id": "provided_tpm_profile"
}
```

The TCGA cohort code supplies the cancer taxonomy only. Data, patients,
clinical fields, endpoints and expression all come from the pinned external
release.

Audit outputs record the dataset, release, manifest hash, source snapshot,
license, expression layer, matrix hash, mapping source and selected sample
identifiers. TCGA data-version fields remain separate.

## API

Stable repository discovery is available under `/api/v1`:

```text
GET /cancer-types
GET /datasets
GET /datasets/{dataset_id}
GET /datasets/{dataset_id}/endpoints
GET /datasets/{dataset_id}/expression-layers
GET /datasets/{dataset_id}/filters
GET /datasets/{dataset_id}/genes
GET /datasets/{dataset_id}/genes/resolve
GET /datasets/{dataset_id}/download/{manifest|qc|license|matrix|matrix-metadata|genes}
```

Every dataset response exposes the active release, QC counts, license,
publication, context and default expression-layer semantics.

## Source adapters

The current adapters ingest reviewed releases from:

- cBioPortal API and DataHub snapshots;
- NCI GDC projects independent of TCGA;
- NCBI GEO family metadata and supplementary matrices;
- Europe PMC clinical supplements paired with publication or GEO expression;
- open ICGC 25K Release 28 objects.

The bundle schema remains source-independent. A new adapter must produce the
same canonical bundle and pass `validate_bundle`; it must not write directly
to repository database tables.

Counts may be retained only when the adapter declares and implements the exact
analysis transform. Normalized matrices are retained at their documented
scale. If the source transform is uncertain, the values must be preserved
without an inferred second transformation and the uncertainty must be visible
as a release caveat.
