# Curated external cohorts

TRACE stores each external study as a dataset with a versioned release. A release links expression layers, clinical variables, endpoint definitions, source identifiers and QC. Studies remain separate when a marker is examined across cohorts.

The source registry in `repository_registry/studies/` contains import specifications, not expression matrices. `cancer_types.json` supplies the taxonomy and `coverage.json` records curation status. A listed study is available for analysis only after a compatible release has been imported into the configured repository.

## Choose a study

In the cohort selector, choose an external study and inspect its available expression scales, endpoints and clinical metadata. A cohort may support molecular analysis without supporting survival. Multivariable models need compatible clinical columns and enough complete patient records; TRACE reports the population used by each model.

The study's expression layer determines which signature methods are available. TPM, counts, normalized expression and standardized scores have different interpretations. See [expression transformations](RNA_BULK_TRANSFORMATIONS.md), [signature scoring](SIGNATURE_SCORING_METHODS.md) and the [capability contract](EXTERNAL_REPOSITORY_CAPABILITY_CONTRACT_V2.md).

## Build and import a release

These are maintainer operations for a configured Python/R environment. Run them from the repository root with your own database and data-storage configuration:

```sh
PYTHONPATH=backend python -m app.repository.cli build-study \
  --spec repository_registry/studies/geo-brca-scanb-gse96058-2018.json \
  --output external_repository_staging/scanb

PYTHONPATH=backend python -m app.repository.cli validate \
  --bundle external_repository_staging/scanb

PYTHONPATH=backend python -m app.repository.cli promote \
  --bundle external_repository_staging/scanb
```

Building may download substantial source files. Review the specification, source license, population and endpoint mappings first. Validation checks the assembled bundle; promotion performs a further read-only eligibility gate before registering the release. Paths are examples and should be replaced with your own staging location.

To refresh catalog metadata or review active releases:

```sh
PYTHONPATH=backend python -m app.repository.cli sync-catalog
PYTHONPATH=backend python -m app.repository.cli revalidate-active
PYTHONPATH=backend python -m app.repository.cli coverage-report
```

The configured locations are `CANCER_REPOSITORY_DIR`, `CANCER_REPOSITORY_REGISTRY_DIR` and the database URL. Dataset licenses, citations and file manifests remain attached to their releases. The API guide documents [catalog and dataset endpoints](API.md).

## Compare studies

Cross-study analyses estimate an effect within each eligible study. Compatible effects can be summarized within a cancer and then across cancers. Study eligibility depends on the endpoint, expression scale, population and model requirements; a shared cancer label alone is insufficient.

The TCGA reference scan is a separate analysis. Its estimates and hierarchical cross-study summaries may use different effect units, so their combined estimates should not be treated as interchangeable. Check the eligibility preview and per-study details before interpreting a summary.

## Desktop packages

Desktop users import TRACE `.tar.gz` packages or connect a hosted package catalog through Manage data. They do not need to run the maintainer commands above. TCGA and external packages are selectable separately. See [desktop data management](DESKTOP.md#manage-data).
