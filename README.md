# TCGA-TRACE

TCGA-TRACE is a Dockerized web application for endpoint-aware TCGA
transcriptomic survival analysis. It combines cutpoint-independent continuous
Cox and spline models with secondary Kaplan-Meier, grouped Cox, RMST and
cutpoint-sensitivity views, a prespecified specification-curve workflow,
an optional exploratory session history, patient-level provenance and hashable
run exports.
Each newly generated analysis also receives a detached Ed25519 server receipt
for independent verification of the exact audit report.

TCGA-TRACE is the canonical product and release name. The deployed
`/tcga_explorer` path, current repository slug and selected internal identifiers
are retained as legacy compatibility surfaces, not as alternate product names;
see [Project Identity](docs/PROJECT_IDENTITY.md).
Source code is distributed under the [MIT License](LICENSE).
The archived trust anchor and rotation/revocation rules are documented in the
[attestation key policy](docs/ATTESTATION_KEY_POLICY.md).

## What It Uses

- Frontend: Vite + React
- Backend: FastAPI
- Database: PostgreSQL
- Plotting/statistics: R `survival` + `survminer`
- TCGA data snapshot mount: host `../TCGA` mounted into containers as `/data/tcga`
- Optional TCGA-CDR clinical endpoint file: `./clinical/TCGA-CDR-SupplementalTableS1.xlsx`
- Curated external RNA-seq repository: host
  `${CANCER_REPOSITORY_HOST_DIR:-./external_repository}` mounted read-only as
  `/data/cancer_repository`

The analysis surface uses TCGA RNA expression or one exact release of a
curated independent bulk RNA-seq cohort. TCGA-CDR can enable OS, PFI, DFI and
DSS per TCGA cohort when a configured CDR file is mounted and the endpoint
passes patient/event QC. For DSS, DFI and PFI, TCGA-TRACE also retains
TCGA-CDR competing-death coding to report cumulative incidence, Gray's test and
grouped/continuous Fine-Gray models beside the cause-specific Kaplan-Meier and
Cox outputs.

Methodological versions and user-facing analysis behavior are tracked in [CHANGELOG.md](CHANGELOG.md). The same information is exposed in the app under `Help & Methods`.

## Run

```bash
docker compose up -d --build
```

Then open:

- Frontend: http://localhost:3000/tcga_explorer/
- Public API health: http://localhost:3000/tcga_explorer/api/v1/health
- Attestation keys: http://localhost:3000/tcga_explorer/api/v1/attestation/keys
- Backend API docs: http://localhost:3000/tcga_explorer/api/docs
- Remote MCP: http://localhost:3000/tcga_explorer/mcp

Only the reverse-proxy container publishes a host port, bound to `127.0.0.1` by
default. PostgreSQL, backend, frontend, and the compute worker stay on the
internal Docker network. Nginx exposes the app on host port 3000 and proxies
the public API and MCP transport to FastAPI.

For deployment behind the Apache HTTPS virtual host at `apps.cienciavida.org`, Apache can proxy `/tcga_explorer/` to this app on port 3000. See `docs/APACHE_DEPLOYMENT.md`.
Production deployments must set `APP_RELEASE_COMMIT` to the full Git commit and
`APP_RELEASE_REF` to its exact release tag. The public health response exposes
both values so release evidence cannot silently test a different deployed
revision.

## Public API and MCP

The stable, anonymous beta API is available under `/api/v1`. Compute requests
return persistent `202 Accepted` jobs, run through a bounded PostgreSQL-backed
queue, and retain generated artifacts for 90 days. Swagger, ReDoc, and the
OpenAPI document are served under `/api/`.

The same scientific capabilities are exposed as a stateless Streamable HTTP
MCP server at `/mcp`, suitable for custom connectors in ChatGPT and Claude.
Start with the [English API/MCP guide](docs/API.md) or the
[Spanish guide](docs/API_ES.md).

The dependency-free command-line client checks the live OpenAPI contract and
can submit, poll, download, and verify every public compute family:

```bash
python3 scripts/tcga_trace_cli.py health
python3 scripts/tcga_trace_cli.py run analysis request.json --verify
```

See the [English CLI guide](docs/CLI.md) or the
[Spanish CLI guide](docs/CLI_ES.md).

## Curated External Cohorts

The **Repository** module tracks independent public bulk RNA-seq cohorts
against all 33 TCGA cancer types. A screening hit is not analyzable until its
TCGA independence, license, expression scale, patient linkage, endpoint event
and censoring counts, gene coverage and immutable checksums pass curation and
automated QC.

The current registry covers 25 cancer types through reviewed cBioPortal, GDC,
GEO, Europe PMC and ICGC releases. Eight types remain documented evidence gaps
because the best public leads are arrays, controlled-access, too small or lack
patient-level survival fields. Survival, Compare and Multiverse can use the
published releases; Pan-cancer remains TCGA-only and no cross-study pooling or
silent expression harmonization is performed. See the
[repository curation and deployment guide](docs/EXTERNAL_RNASEQ_REPOSITORY.md).

The web application's **Run history** module is opt-in and browser-local until
export. It can combine selected terminal jobs into one signed post hoc record
with separate continuous, grouped and interaction multiplicity families;
prespecified Multiverse and Pan-cancer families are referenced without being
counted again.

The web application's **Examples** module exposes the versioned manuscript
benchmark as an interactive figure atlas: 11 continuous single-gene profiles,
44 grouped cutpoint-sensitivity analyses and six advanced or diagnostic workflows.
These curated artifacts are pinned independently of normal public-job
retention.

The main **Pan-cancer** module also exposes the separately versioned
3,118-gene ImmPort atlas. Primary expression, ordinal stage+grade, stage and
grade families can be inspected without mixing their FDR or random-effects
summaries. REST and MCP clients read the same frozen screen
`immune_os_immport_all_v2_1`.

Production:

- API: https://apps.cienciavida.org/tcga_explorer/api/v1/
- Documentation: https://apps.cienciavida.org/tcga_explorer/api/docs
- MCP: https://apps.cienciavida.org/tcga_explorer/mcp

On first backend startup, the app imports cohort metadata and sample-level clinical fields into PostgreSQL. The Docker setup blocks the frontend until the backend cache warmup is complete. A fresh startup preloads cohort gene indexes, CPM library sizes, GDC barcode maps, and binary gene-by-sample matrices for the GDC-derived RNA scales before `http://localhost:3000/tcga_explorer/` is started.

To enable TCGA-CDR endpoints, place the official `TCGA-CDR-SupplementalTableS1.xlsx` file in `./clinical/` before startup. TSV/CSV equivalents with the same endpoint columns are also supported by configuring `TCGA_CDR_PATH`.

## Reviewer Reproduction

The reviewer quickstart is:

```text
REVIEWER_QUICKSTART.md
```

The full Bioinformatics Application Note reproduction guide is:

```text
manuscript/bioinformatics_app_note/submission/reviewer_reproduction_guide.md
```

It covers Docker startup, manuscript PDF builds, benchmark regeneration,
data-snapshot manifest export and reproducibility-bundle verification. Full TCGA
expression matrices and patient-level analysis exports are generated locally and
are not tracked in git; compact benchmark outputs and the publication manifest
are stored under `docs/publication/benchmark/`.

Continuous integration is defined in `.github/workflows/ci.yml` for checks that
do not require the local TCGA snapshot: backend tests, publication-script
syntax/tests, project-identity checks, pinned Gitleaks scanning, frontend Vitest
and the production frontend build. `.github/workflows/release-readiness.yml` is a manual exact-tag
gate: after that tag is deployed, it verifies the public deployment commit and
release ref in Chromium, Gecko and WebKit, enforces final metadata, rebuilds the
manuscript and produces a checksummed reviewer archive. The full local publication gate is
`scripts/publication/pre_submission_check.sh`.

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

- The default Survival interface uses one gene, OS, `log2(TPM + 1)`, no clinical filters, age adjustment and a median split. It presents the continuous Cox estimate first, adds the spline when at least 30 events are available, and treats Kaplan-Meier, grouped Cox and RMST as cutpoint sensitivities. Every completed analysis creates an audit report, reconstruction bundle and signed receipt; a prespecified multiverse is an explicit separate workflow.
- Expression grouping can use `log2(TPM + 1)`, `log2(CPM + 1)`, `log2(FPKM + 1)`, or `log2(FPKM-UQ + 1)`.
- Cancer cohorts are shown by full TCGA study name, with the TCGA code kept in parentheses.
- A Dataset Summary page shows the database creation date, the TCGA data-through date, cohort/sample totals, metadata coverage, ranked dot/donut/histogram/matrix plots, distributions, and a cohort table.
- Dataset Summary can be filtered by cohort and downloaded as CSV.
- Dataset Summary reports data-source status and endpoint coverage/QC.
- Compare Analyses can run several genes across several cutpoint methods and shows a plot matrix with genes as rows and methods as columns, including BH and Bonferroni adjusted p-values.
- Every single-marker or single-signature analysis starts with a Cox effect per +1 within-analysis expression-score SD and a restricted cubic-spline profile over the full eligible expression-complete population.
- Every continuous, grouped and two-signature interaction Cox result reports fitted parameters and events per parameter. Values below 10 are cautioned and values below 5 receive a severe caution.
- Low-information, unstable, non-finite or extreme standard Cox fits automatically add a `coxphf` Firth sensitivity with profile-likelihood inference. It is displayed beside, never substituted for, the Efron-ties standard estimate.
- Compare Analyses shows one cutpoint-independent continuous reference per gene, then evaluates maxstat, median, upper quartile, outer quartiles and the selected custom percentile as grouped sensitivities with BH, Cox, RMST and PH diagnostics. No composite retention rule is applied.
- A marker-specific `cox.zph` p-value below 0.05 triggers an adjacent two-period Cox diagnostic with a fixed 2-year primary split and fixed 1- and 5-year sensitivities. Each supported split reports early/late HRs, the Wald interaction ratio and period support; these coarse temporal summaries never replace the original model.
- Restricted cubic splines require at least 30 endpoint events for their three fitted parameters and report events per parameter with the same information-status contract as the Cox models.
- The Multiverse module freezes up to 72 endpoint-by-scoring-by-cutpoint
  specifications before execution. It deduplicates cutpoint-independent
  continuous tests, adjusts continuous and grouped families separately, and
  retains completed, unavailable and failed cells in one hashed family ledger.
  This ledger covers the declared family; unrelated ad hoc browser runs are not
  silently treated as prespecified.
- Analysis responses separate neutral cohort/method information, model availability, and statistical cautions. The top-level amber state is reserved for a caution in the selected adjusted model; `not_evaluable` is not treated as failure.
- Multi-gene and compare runs use the persistent public batch queue, with up to 25 analyses per batch.
- Pan-cancer survival concordance preserves descriptive per-cohort Cox effects per within-cohort expression SD and never pools that cohort-specific scale. Comparable single-gene and mean/weighted-signature coefficients are additionally expressed per +1 shared input-score unit and synthesized with REML, HKSJ inference and a 95% prediction interval. BH-FDR and synthesis remain separate by endpoint and model family; cohort-standardized z-score signatures, mixed endpoints and mixed selected adjustments are not pooled.
- The ImmPort atlas applies that contract to 3,118 genes across 32 strict-OS cohorts, exposes family-specific and availability-selected views, and pins its input matrices, checkpoints, patient records and outputs in a reproducibility audit.
- Each pan-cancer scan exports cohort and patient CSV files, parameter-specific methods, raw R results, JSON/HTML audit reports and a ZIP reproducibility bundle.
- Stratification supports maxstat, median, tertiles, quartiles, outer quartiles, and custom percentile cutpoints.
- Methodological tooltips explain cutpoint and expression-scale choices.
- Gene mode supports multiple single-gene KM plots plus mean, z-score, and weighted signature plots using `GENE:weight` syntax.
- Adjusted Cox models encode major stage and histologic grade as ordinal trends, use both when evaluable, and retain stage-only or grade-only variants as explicit fallbacks.
- Survival and Compare Analyses can request one exact complete-case Cox adjustment from imported age, stage, grade, GDC gender and GDC race. Age is reported per 10 years; categorical fields use explicit treatment contrasts. If the requested model is unavailable, it is marked not evaluable rather than replaced by an auxiliary stage/grade model.
- Survival, Compare and Multiverse can additionally link a bounded patient-level CSV by exact public TCGA participant barcode. User-supplied continuous, categorical and ordinal covariates use prespecified effect units, references and level order; no imported variable enters a model until selected explicitly. Dataset SHA-256, linkage/missingness QC, coding and patient-level values are retained in the audit bundle.
- Combined two-signature analyses report continuous Cox interaction models for `signature_A_z + signature_B_z + signature_A_z:signature_B_z`, including ordinal stage/grade-adjusted variants when evaluable.
- Gene selection uses removable chips with live autocomplete gene-symbol suggestions.
- Clinical filters start empty; users explicitly select sample type, stage, gender, race, age, or follow-up limits.
- Survival analyses apply user filters and endpoint QC, require complete expression for the requested gene or signature, and only then retain one RNA-seq sample per TCGA participant using biospecimen priority. A lower-priority expression-complete barcode is used when a higher-priority eligible sample lacks the requested score, and every fallback is recorded.
- A small HGNC-style alias map resolves common legacy symbols such as `P53` to `TP53` and reports the resolution as a warning.
- Plot export styling supports custom group colors, font family, base font size, axis tick/title font sizes, grid visibility, and optional plot title.
- PNG is generated immediately for display; SVG is generated on demand when downloaded to reduce initial plot-generation time.
- Result downloads show non-blocking background status notices, and each completed analysis can be downloaded as a ZIP bundle with continuous-effect PNG/SVG/CSV, grouped PNG/SVG/CSV, metrics JSON, methodology TXT, audit JSON, and audit HTML.
- Plot X-axis can be displayed in days, months, or years.
- OS is available as a fallback from `vital_status`, `days_to_death`, `days_to_last_follow_up`, and `days_to_last_known_disease_status` when TCGA-CDR is not configured.
- TCGA-CDR endpoints are exposed only when the selected cohort has sufficient linked patients and events.
- Analysis outputs are written under `./artifacts/<analysis_id>/`.
- Each analysis writes a parameter-specific REMARK-style `methodology.txt` with data source, endpoint, cohort selection, marker measurement, stratification, statistical methods, limitations, warnings, and software versions for manuscript methods drafting.
- Each analysis writes `audit_report.json` and `audit_report.html` with request parameters, endpoint source/QC, sample-selection details, separately hashed continuous and grouped patient records, group/event counts, Cox information/Firth, spline and prespecified time-varying outputs, proportional-hazards QC, software versions, artifact checksums, and reproducibility hashes. A detached `attestation_receipt.json` signs the exact audit bytes and recorded run hash with Ed25519; its key is published through the HTTPS API and can be checked with `scripts/verify_server_attestation.py`. The receipt establishes server origin for that report, not scientific correctness or append-only time.
- Bioinformatics Application Note readiness, comparator positioning and the benchmark protocol are documented in `docs/BIOINFORMATICS_PUBLICATION_READINESS.md`.
- Results are exploratory research outputs and are not intended for clinical decision-making.
- `TCGA-CHOL` is the available biliary tract/cholangiocarcinoma cohort. There is no explicit gallbladder cancer cohort in the current TCGA cohort summary table.
- RNA bulk expression availability is documented in `docs/RNA_BULK_TRANSFORMATIONS.md`; GDC cache-derived matrices are stored under `./derived/rna_bulk/matrices`.
- If `./derived` is empty, the first startup can take tens of minutes while all cohort caches are built. Later restarts reuse the generated cache.
- Public cache readiness is summarized at `http://localhost:3000/tcga_explorer/api/v1/health`; detailed cache operations remain internal to the backend container.
