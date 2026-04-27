# TCGA KM Explorer

Dockerized web application for Kaplan-Meier survival analysis using TCGA cancer cohort RNA-seq data.

## What It Uses

- Frontend: Vite + React
- Backend: FastAPI
- Database: PostgreSQL
- Plotting/statistics: R `survival` + `survminer`
- TCGA data snapshot mount: host `../TCGA` mounted into containers as `/data/tcga`
- Optional TCGA-CDR clinical endpoint file: `./clinical/TCGA-CDR-SupplementalTableS1.xlsx`

The analysis surface uses TCGA RNA expression. TCGA-CDR can enable OS, PFI, DFI and DSS per cohort when a configured CDR file is mounted and the endpoint passes basic patient/event QC.

## Run

```bash
docker compose up -d --build
```

Then open:

- Frontend: http://localhost/tcga_explorer/
- Backend health: http://localhost/api/health
- Backend API docs: http://localhost/api/docs

Only the reverse-proxy container publishes a host port. PostgreSQL, backend, and frontend stay on the internal Docker network, while Nginx exposes the app on port 80 and proxies `/api/` to FastAPI.

For deployment behind the Apache HTTPS virtual host at `apps.cienciavida.org`, bind the container Nginx to an internal host port such as `127.0.0.1:18080` and proxy `/tcga_explorer/` from Apache. See `docs/APACHE_DEPLOYMENT.md`.

On first backend startup, the app imports cohort metadata and sample-level clinical fields into PostgreSQL. The Docker setup blocks the frontend until the backend cache warmup is complete. A fresh startup preloads cohort gene indexes, CPM library sizes, GDC barcode maps, and binary gene-by-sample matrices for the GDC-derived RNA scales before `http://localhost/tcga_explorer/` is started.

To enable TCGA-CDR endpoints, place the official `TCGA-CDR-SupplementalTableS1.xlsx` file in `./clinical/` before startup. TSV/CSV equivalents with the same endpoint columns are also supported by configuring `TCGA_CDR_PATH`.

## Weekly Data Sync

The app can check and apply weekly updates for TCGA RNA-seq and TCGA-CDR without creating full duplicate snapshots. The default writable source is the sibling host folder:

```text
../TCGA
```

The updater writes manifests, staging files, run reports, and backups under:

```text
../TCGA/.sync
./clinical/.sync
```

Check for changes:

```bash
docker compose run --rm updater check --source all
```

Apply validated updates:

```bash
docker compose run --rm updater apply --source all --max-workers 10 --reimport
```

Weekly host script:

```bash
scripts/weekly_tcga_update.sh
```

Recommended cron, Monday 03:00 UTC:

```cron
0 3 * * 1 cd /path/to/tcga_explorer && scripts/weekly_tcga_update.sh >> logs/weekly_tcga_update.log 2>&1
```

Exit codes:

- `0`: no changes or successful no-op.
- `20`: data were updated and the script restarts backend/frontend.
- `1`: sync failed; current data remain in place.

The updater uses the GDC API to compare remote `file_id`, `md5sum`, `file_size`, `updated_datetime`, and `data_release` against the local manifest. Files are downloaded to staging, validated by checksum and expected STAR-count columns, then promoted atomically. Replaced files are copied into `.sync/backups/<run_id>/`. Derived RNA caches for affected cohorts are invalidated so backend startup rebuilds them before the frontend becomes available. TCGA-CDR is checked from the official GDC file id `1b5f413e-a8d1-4d10-92eb-7c4ae739ed81` and validated for OS/PFI/DFI/DSS columns.

## Notes

- Expression grouping can use `log2(TPM + 1)`, `log2(CPM + 1)`, `log2(FPKM + 1)`, or `log2(FPKM-UQ + 1)`.
- Cancer cohorts are shown by full TCGA study name, with the TCGA code kept in parentheses.
- A Dataset Summary page shows the database creation date, the TCGA data-through date, cohort/sample totals, metadata coverage, ranked dot/donut/histogram/matrix plots, distributions, and a cohort table.
- Dataset Summary can be filtered by cohort and downloaded as CSV.
- Dataset Summary reports data-source status and endpoint coverage/QC.
- Compare Analyses can run several genes across several cutpoint methods and shows a plot matrix with genes as rows and methods as columns, including BH and Bonferroni adjusted p-values.
- Multi-gene and compare runs use a bounded batch API that executes up to 10 analyses in parallel.
- Stratification supports maxstat, median, tertiles, quartiles, outer quartiles, and custom percentile cutpoints.
- Methodological tooltips explain cutpoint and expression-scale choices.
- Gene mode supports multiple single-gene KM plots plus mean, z-score, and weighted signature plots using `GENE:weight` syntax.
- Gene selection uses removable chips with live autocomplete gene-symbol suggestions.
- Clinical filters start empty; users explicitly select sample type, stage, gender, race, age, or follow-up limits.
- Survival analyses retain one RNA-seq sample per TCGA participant using a biospecimen priority rule: primary tumor or primary blood-derived cancer, recurrent/additional/metastatic tumor, then normal/control only if no higher-priority sample remains after filters.
- A small HGNC-style alias map resolves common legacy symbols such as `P53` to `TP53` and reports the resolution as a warning.
- Plot export styling supports custom group colors, font family, base font size, axis tick/title font sizes, grid visibility, and optional plot title.
- PNG is generated immediately for display; SVG is generated on demand when downloaded to reduce initial plot-generation time.
- Result downloads show non-blocking background status notices, and each completed analysis can be downloaded as a ZIP bundle with PNG, SVG, CSV, and methodology TXT.
- Plot X-axis can be displayed in days, months, or years.
- OS is available as a fallback from `vital_status`, `days_to_death`, `days_to_last_follow_up`, and `days_to_last_known_disease_status` when TCGA-CDR is not configured.
- TCGA-CDR endpoints are exposed only when the selected cohort has sufficient linked patients and events.
- Analysis outputs are written under `./artifacts/<analysis_id>/`.
- Each analysis writes a parameter-specific REMARK-style `methodology.txt` with data source, endpoint, cohort selection, marker measurement, stratification, statistical methods, limitations, warnings, and software versions for manuscript methods drafting.
- Results are exploratory research outputs and are not intended for clinical decision-making.
- `TCGA-CHOL` is the available biliary tract/cholangiocarcinoma cohort. There is no explicit gallbladder cancer cohort in the current TCGA cohort summary table.
- RNA bulk expression availability is documented in `docs/RNA_BULK_TRANSFORMATIONS.md`; GDC cache-derived matrices are stored under `./derived/rna_bulk/matrices`.
- If `./derived` is empty, the first startup can take tens of minutes while all cohort caches are built. Later restarts reuse the generated cache.
- Cache readiness is visible at `http://localhost/api/health` and detailed status is available at `http://localhost/api/cache/status`.
