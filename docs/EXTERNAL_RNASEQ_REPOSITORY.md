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

## Current releases

| Cancer | Dataset | Release | Patients | Events | Genes | Expression |
| --- | --- | --- | ---: | ---: | ---: | --- |
| SKCM | DFCI metastatic melanoma 2015 | `cbioportal-skcm-dfci-2015-86690e1ed975` | 40 | 27 OS | 21,623 | log2(RPKM + 1), transformed by TCGA-TRACE from source RPKM |
| BLCA | IMvigor210 metastatic bladder cancer | `cbioportal-blca-iatlas-imvigor210-2017-1da5c747e4fd` | 347 | 231 OS | 38,355 | iAtlas TPM profile preserved at the supplied scale |

The BLCA DataHub profile is named TPM, but its supplied values are bounded
near 22 and the exact upstream transform is not stated in the profile
metadata. The release therefore records `identity`, exposes a scale caveat and
does not claim that the analysis values are unlogged TPM.

Both current DataHub study directories include an ODbL 1.0 license. Matrix
downloads are exposed only when the release records redistribution as allowed.

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

Build a reviewed DataHub study specification:

```bash
docker compose run --rm \
  -v "$PWD/external_repository_staging:/staging" \
  backend python3 -m app.repository.cli build-cbioportal \
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

## Adding other sources

The bundle schema is source-independent. A new source adapter must produce the
same canonical bundle and pass `validate_bundle`; it must not write directly
to repository database tables. GEO, ArrayExpress or recount-derived adapters
can therefore be added later without changing the analysis contract.

Counts may be retained only when the adapter declares and implements the exact
analysis transform. Normalized matrices are retained at their documented
scale. If the source transform is uncertain, the values must be preserved
without an inferred second transformation and the uncertainty must be visible
as a release caveat.
