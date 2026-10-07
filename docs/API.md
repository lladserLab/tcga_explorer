# TRACE Explorer Public API and MCP

TRACE Explorer exposes its scientific workflows through a public REST
API and a remote Model Context Protocol (MCP) server. Both interfaces use the
same validation, persistent compute queue, cache, and artifact retention
policy.

REST is the complete public integration contract. MCP is a bounded,
analysis-oriented surface over the same scientific engine: it supports TCGA,
curated external and already-uploaded private dataset discovery, including
dataset-specific clinical filters; the main survival and grouped-expression
workflows; Robustness; and both TCGA-reference and hierarchical pan-cancer
analysis. Creating or deleting a private upload and exporting browser Run
history remain explicit web/REST operations.

These outputs are for exploratory research. They are not intended for clinical
decision-making, diagnosis, prognosis, or treatment selection.

## Production addresses

| Interface | Address |
| --- | --- |
| Web application | `https://apps.cienciavida.org/tcga_explorer/` |
| Static signature-scoring Methods | `https://apps.cienciavida.org/tcga_explorer/methods/signature-scoring/` |
| REST API v1 | `https://apps.cienciavida.org/tcga_explorer/api/v1/` |
| Swagger UI | `https://apps.cienciavida.org/tcga_explorer/api/docs` |
| ReDoc | `https://apps.cienciavida.org/tcga_explorer/api/redoc` |
| OpenAPI 3 document | `https://apps.cienciavida.org/tcga_explorer/api/openapi.json` |
| Remote MCP | `https://apps.cienciavida.org/tcga_explorer/mcp` |
| Spanish guide | `https://apps.cienciavida.org/tcga_explorer/api/guia` |

`/tcga_explorer` is the stable compatibility path for TRACE Explorer,
retained for existing bookmarks, Apache deployments and API clients. It is not
an alternate product name.

The public beta does not require an API key. Limits are applied to an anonymous
client identity derived from the proxy-verified IP address or MCP session.

## Data and scientific scope

The API exposes the same public-data capabilities as the web application:

- TCGA cohort, sample, patient, gene, endpoint, and data-source summaries.
- Curated independent bulk RNA-seq releases with source-specific expression
  layers, endpoint definitions, license metadata and immutable manifests.
- Explicit per-dataset capabilities for survival, expression comparison, GSEA
  and hierarchical pan-cancer analysis. A dataset being visible does not imply
  that every workflow is scientifically eligible.
- A separate read-only registry of reviewed candidates. Candidate records
  document promotion decisions and blockers but are never accepted as compute
  dataset IDs until they become a versioned release.
- Temporary private user datasets created from de-identified expression and
  patient-metadata CSV/TSV files. Survival outcomes are optional, and private
  releases are never enumerated in the public repository.
- OS, PFI, DFI, and DSS endpoint availability and cohort-level QC.
- Single-gene, mean, z-score, weighted, singscore, ssGSEA and AUCell RNA
  signature survival analyses.
- Cutpoint-independent continuous Cox models, restricted cubic-spline effect
  profiles, proportional-hazards diagnostics, and reproducibility artifacts.
- Cutpoint-based Kaplan-Meier, grouped Cox, RMST, and sensitivity outputs.
- For DSS, DFI, and PFI, explicit TCGA-CDR competing-event coding,
  cumulative-incidence functions, Gray tests, and grouped and continuous
  Fine-Gray models alongside the cause-specific outputs.
- **Robustness across analysis choices**, implemented as prespecified
  endpoint-by-scoring-by-cutpoint multiverse and specification-curve analysis,
  with family-specific multiplicity correction and complete execution ledgers.
- Two-signature grouping and continuous Cox interaction models.
- Bounded panels of 2--6 signatures with common-population standardization,
  univariable and joint main-effects Cox models, and family-specific
  multiplicity correction.
- Bounded comparison batches.
- Preranked GSEA between two groups defined by standardized clinical fields,
  inherited survival dichotomizations, or one gene/multi-gene expression
  score.
- Targeted expression comparison for 1--25 genes across the same traceable
  clinical, inherited-survival or expression-derived groups, with separate
  across-gene FDR for Welch and Mann--Whitney tests.
- Continuous pan-cancer Cox scans, BH-FDR, concordance, and meta-analysis.
- Opt-in hierarchical pan-cancer synthesis of one-gene, strict-OS Cox effects
  across compatible TCGA and curated external study universes.
- Precomputed immune pan-cancer screens.
- A read-only catalog of deterministic, bilingual synthetic tutorial datasets;
  tutorial progress is browser-local and is not an API resource.

Public scope contains open TCGA/GDC, TCGA-CDR-derived data and explicitly
licensed external releases. Internal filesystem paths, cache manifests,
synchronization controls and database operations are not part of API v1.
External matrices are downloadable only when the release records redistribution
as allowed.

Private uploads are capability-addressed by an unguessable `user-*` ID. Original
files are discarded after validation; normalized data and generated private
results are deletable and expire after 24 hours. An accepted queued or running
analysis leases its private inputs for one additional retention window; a
completed cached response does not extend that lease. The service is not a
repository for protected health information. Upload only de-identified research
data.

Upload ceilings are 100 MiB for the expression file, 10 MiB for patient
metadata, 5,000 samples, 60,000 genes and 50 million matrix cells. These are
independent checks: the validator also requires `genes × samples ≤ 50,000,000`.
Thus 5,000 samples permit at most 10,000 genes, and 60,000 genes permit at most
833 samples; a 5,000 × 60,000 matrix is not accepted.

Patient-level audit artifacts retain exact TCGA participant and sample barcodes
for scientific traceability. These are public research identifiers, but users
must not attempt re-identification or combine them with restricted data.

### Shared request validation

The web application, REST API and MCP server enforce the same input boundaries.
Single-gene survival requests require exactly one gene; mean, z-score,
weighted, singscore, ssGSEA and AUCell signatures require at least two.
Selecting a percentile cutpoint also requires `custom_percentile` from 1
through 99.

### Signature-scoring contract

`signature_method` accepts `single`, `mean`, `zscore`, `weighted`, `singscore`,
`ssgsea` or `aucell`. Mean, weighted and z-score operate on the resolved
signature components. Z-score centres and scales each gene among the eligible,
expression-complete patients in that run, so its numerical values are not
transportable across separately scored populations.

The three rank methods require a frozen broad expression layer with at least
1,000 unique usable genes, no more than 75 million gene-by-sample entries and
complete mapping of the requested signature.
Plain genes and weight `+1` define the positive component; weight `-1` defines
the negative component. REST clients may instead use
`signature_genes[].direction` with `up` or `down` and should omit `weight` in
that representation. Explicit direction is authoritative if both fields are
sent; zero and non-unit rank weights are rejected. `singscore` uses
within-sample centred ranks and is the recommended bulk-RNA starting point.
ssGSEA uses `GSVA::ssgseaParam(alpha=0.25, normalize=FALSE, minSize=2,
maxSize=Inf)`; each non-empty direction must retain at least two genes. AUCell
uses a deterministic sample-specific tie seed,
`aucMaxRank=ceiling(0.05 * universe_n)` and normalized AUC, and is labelled a
top-ranked activity sensitivity. GSVA itself is not an exposed method.

Rank scores are computed once on the release's canonical molecular population
before endpoint and clinical filters, then subset for the requested analysis.
Changing those downstream filters therefore does not recalculate a retained
patient's rank score. Arithmetic methods follow the analysis-eligible
population; z-score is recalculated on its complete cases. Cross-study
workflows fit effects within each study; they do not pool raw patient-level
rank scores as if they shared one numerical scale.

The stable [Signature scoring Methods](https://apps.cienciavida.org/tcga_explorer/methods/signature-scoring/)
page gives the formulas, pinned package versions, feature-universe and
missing-gene rules, direction semantics and interpretation limits without
requiring JavaScript. Its machine-readable contract is available beside it as
`contract.json`.

Age bounds must be finite and between 0 and 150, with the minimum no greater
than the maximum. `max_time_days`, when supplied, must be positive and no more
than 3,652,500 days. A numeric custom clinical restriction needs at least one
bound and its minimum cannot exceed its maximum. The same clinical variable
cannot be restricted twice. Public comparison batches accept at most 25
analysis requests; clients should count genes multiplied by requested methods
before submission.

Audit SHA-256 values remain integrity checks for accidental drift, corruption
and incomplete transfer. Completed analyses also receive a detached Ed25519
server receipt that signs the exact `audit_report.json` byte count, SHA-256,
schema and recorded reproducibility hash. Verify it against the public key
retrieved from the declared HTTPS issuer, not a key supplied only inside the
export. This establishes server origin for that exact report; it does not
establish scientific correctness or append-only publication time. Plots and
methodology files remain outside the reproducibility hash and have separate
checksums recorded by the signed report.

## REST quick start

Discover the API and its canonical service links:

```bash
curl -sS \
  https://apps.cienciavida.org/tcga_explorer/api/v1/
```

Inspect service and dataset readiness:

```bash
curl -sS \
  https://apps.cienciavida.org/tcga_explorer/api/v1/health

curl -sS \
  https://apps.cienciavida.org/tcga_explorer/api/v1/cohorts
```

The health payload includes `release.commit` and `release.ref`. Development
stacks report `development`; a citable deployment should expose the full Git
commit and exact tag supplied through `APP_RELEASE_COMMIT` and
`APP_RELEASE_REF`.

## Upload your own expression and patient metadata

Download a synthetic two-file example:

```bash
curl -sS -o trace-user-dataset-template.zip \
  https://apps.cienciavida.org/tcga_explorer/api/v1/user-datasets/template
```

That archive contains 18 synthetic patients, three genes and three subtypes
with six patients each. It supports testing the upload and two-group comparison
workflow, not biological inference or GSEA. Map `breast_subtype` as a categorical
custom variable with baseline timing to use it. List the versioned teaching datasets, including the 48-sample
quickstart, transcriptome-scale GSEA example and validation lab, with:

```bash
curl -sS \
  https://apps.cienciavida.org/tcga_explorer/api/v1/tutorial-assets

curl -sS -o trace-private-quickstart-kirc-log2-v1.zip \
  https://apps.cienciavida.org/tcga_explorer/api/v1/tutorial-assets/private-quickstart-kirc-log2-v1
```

Every archive is synthetic and includes bilingual READMEs, a versioned
manifest, expected QC, recipes and SHA-256 checksums. See the full written
learning guide in `docs/TUTORIALS.md`.

Create a temporary private dataset with multipart form data. The metadata table
may contain subtype or other categorical and numeric patient variables. A
time-to-event outcome is optional. Do not set the
multipart `Content-Type` manually; `curl` adds the required boundary.

```bash
curl -sS \
  -F 'expression_file=@expression.csv' \
  -F 'clinical_file=@clinical.csv' \
  --form-string 'mapping={
    "name": "Institutional LUAD cohort",
    "cancer_code": "LUAD",
    "expression_orientation": "genes_by_rows",
    "expression_id_column": "gene_symbol",
    "clinical_id_column": "sample_id",
    "has_survival_outcome": true,
    "time_column": "os_months",
    "event_column": "os_status",
    "event_value": "event",
    "censored_value": "censored",
    "time_unit": "months",
    "endpoint": "OS",
    "expression_unit": "log2_tpm",
    "covariates": {
      "age_at_index": "age",
      "stage": "stage",
      "grade": "grade"
    },
    "confirm_deidentified": true
  }' \
  https://apps.cienciavida.org/tcga_explorer/api/v1/user-datasets
```

The response supplies `id`, `active_release_id`, a one-time `access_token`,
`expression_layer.value`, analysis `capabilities`, an optional `endpoint`, QC
notices and `expires_at`. A dataset without a usable outcome can still be used
for Expression Comparison and, with at least 100 genes before run-specific
ranking checks, GSEA. Patients with missing outcome fields remain
in molecular analyses and are excluded only from survival. Zero or negative
survival times are also excluded only from survival, with an explicit notice.
`qc.endpoint` reports exclusions among expression-matched patients;
`qc.custom_clinical` reports their metadata coverage and grouping eligibility.
`qc.clinical` retains the source-table counts, including unmatched records.

Expression values must be finite numbers with a dot as the decimal separator,
or declared missing values such as a blank cell or `NA`. Invalid text, infinity
and values outside the float32 storage range reject the upload with HTTP 422,
an explanation and the row and column in `details`. They are not silently
converted to missing values. These checks apply to new uploads; existing
private releases and their recorded QC are not rewritten.

Use
the dataset values in the ordinary analysis request and send the token in
every private-data request:

```bash
curl -H 'X-TRACE-Dataset-Token: RETURNED-ACCESS-TOKEN' \
  https://apps.cienciavida.org/tcga_explorer/api/v1/user-datasets/user-RETURNED-ID
```

The browser keeps this token only in session storage; closing the browser tab
ends local access. TRACE stores only its SHA-256 digest. The dataset ID alone
does not grant access.

```json
{
  "cohort": "TCGA-LUAD",
  "dataset_id": "user-RETURNED-ID",
  "dataset_release_id": "user-RETURNED-ID-v1",
  "expression_layer_id": "uploaded_expression",
  "gene_symbol": "TP53",
  "endpoint": "OS",
  "cutpoint_method": "median"
}
```

Inspect it with `GET /api/v1/user-datasets/{dataset_id}` or delete it with
`DELETE /api/v1/user-datasets/{dataset_id}`. Gene search, endpoint,
expression-layer and filter resources are available below that same URL. Raw
counts require at
least 5,000 genes and are converted to `log2(CPM + 1)`; non-log TPM, FPKM,
FPKM-UQ and CPM receive one declared `log2(x + 1)` transform. Other normalized
scales are analyzed as provided. Import requires at least 10 matched patients.
Survival capability additionally requires 10 complete outcomes, 5 events and
5 censored observations. `DELETE` returns HTTP 409 with
`USER_DATASET_IN_USE` while a referencing compute job is queued or running;
wait for the job to finish and retry.

HTTP 429 with `USER_DATASET_LIMIT` means the network has reached its active
upload limit (three by default). Delete a private dataset you can access or
wait for a retained upload to expire. This is separate from compute quotas;
retrying an analysis or waiting a few seconds does not free an upload slot.

Submit a survival analysis:

```bash
curl -i -sS \
  -H 'Content-Type: application/json' \
  -d '{
    "cohort": "TCGA-BRCA",
    "gene_symbol": "TP53",
    "endpoint": "OS",
    "expression_scale": "log2_tpm",
    "cutpoint_method": "median",
    "adjustment_covariates": ["age_at_index"]
  }' \
  https://apps.cienciavida.org/tcga_explorer/api/v1/analyses
```

The compute endpoint returns `202 Accepted`. Its body is a persistent job and
the `Location` header points to the same status resource:

```json
{
  "id": "2f6a...",
  "kind": "analysis",
  "status": "queued",
  "status_url": "https://apps.cienciavida.org/tcga_explorer/api/v1/jobs/2f6a...",
  "result": null,
  "error": null
}
```

Poll the job until `status` is `completed`, `failed`, or `expired`:

```bash
curl -sS \
  https://apps.cienciavida.org/tcga_explorer/api/v1/jobs/JOB_ID
```

On completion, `result` contains the full response and `result_url` provides
its durable resource URL. Identical active or retained requests are
deduplicated and can return a cached job. Job identity includes the request,
analysis-pipeline version, and data version, so a newer scientific context
cannot reuse a completed artifact from an older one.

Submit a multiple-signature main-effects panel:

```bash
curl -i -sS \
  -H 'Content-Type: application/json' \
  -d '{
    "cohort": "TCGA-SKCM",
    "panel_name": "Immune program comparison",
    "endpoint": "OS",
    "expression_scale": "log2_tpm",
    "signatures": [
      {
        "name": "Effector",
        "gene_symbol": "IFNG, CXCL9, GZMB",
        "signature_method": "zscore",
        "signature_genes": [
          {"gene_symbol": "IFNG", "weight": 1},
          {"gene_symbol": "CXCL9", "weight": 1},
          {"gene_symbol": "GZMB", "weight": 1}
        ]
      },
      {
        "name": "Checkpoint",
        "gene_symbol": "PDCD1, LAG3, HAVCR2",
        "signature_method": "zscore",
        "signature_genes": [
          {"gene_symbol": "PDCD1", "weight": 1},
          {"gene_symbol": "LAG3", "weight": 1},
          {"gene_symbol": "HAVCR2", "weight": 1}
        ]
      }
    ],
    "adjustment_covariates": ["age_at_index", "stage"]
  }' \
  https://apps.cienciavida.org/tcga_explorer/api/v1/analyses/signature-panel
```

The panel accepts 2--6 uniquely named and uniquely defined signatures. It
intersects patients with complete endpoint data and every final score, then
standardizes each score on that common population. It fits continuous main
effects only: one univariable Cox model per signature, one joint unadjusted
model, and one exact joint clinical-adjustment model when requested and
evaluable. It does not search cutpoints, draw Kaplan--Meier groups, or infer
interactions.

## Endpoint catalog

### Service and dataset

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/health` | API, pipeline, data, cache, and queue readiness |
| `GET` | `/dataset/summary` | Dataset summary, optionally filtered by `cohort` |
| `GET` | `/dataset/summary/download/csv` | Summary CSV |
| `GET` | `/data-sources` | Sanitized source provenance |
| `GET` | `/endpoints` | Global survival endpoint availability |
| `GET` | `/expression-scales` | Supported RNA expression scales |
| `GET` | `/attestation/keys` | Active and retained Ed25519 public keys |
| `GET` | `/attestation/keys/{key_id}` | One exact public-key document |

### Cohort discovery

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/cohorts` | List cohorts |
| `GET` | `/cohorts/{cohort_id}/endpoints` | Endpoint coverage and QC |
| `GET` | `/cohorts/{cohort_id}/filters` | Available clinical filters |
| `GET` | `/cohorts/{cohort_id}/genes` | Search valid TCGA reference genes |
| `GET` | `/cohorts/{cohort_id}/genes/resolve` | Resolve a TCGA symbol or supported alias |

For external-only cancers such as `FU-GBC`, select the external `dataset_id`
and use `/datasets/{dataset_id}/genes` or `/datasets/{dataset_id}/genes/resolve`.
The TCGA gene routes return `422 DATASET_REQUIRED` for these cancers rather
than attempting to load a TCGA matrix. MCP follows the same distinction:
`trace_search_dataset_genes` and `trace_resolve_dataset_gene` handle external data.
The same boundary applies to `/cohorts/{cohort_id}/endpoints` and `/filters`:
external-only cohorts return `422 DATASET_REQUIRED`, not a zero-patient TCGA
response. Use `/datasets/{dataset_id}/endpoints` and `/filters`, or MCP
`trace_get_dataset_endpoints` and `trace_get_dataset_filter_options`.

Swagger UI and ReDoc serve pinned local assets without a CDN or an external
schema validator. Their integration-guide and OpenAPI links remain usable
when JavaScript is disabled or the schema cannot be loaded.

Filter responses include `clinical_grouping_variables`, a versioned catalog
shared by GSEA and grouped expression comparison. Each variable reports its
stable `id`, label, type, category, source field, patient coverage, missingness,
availability and categorical
`levels[{value,label,count,analysis_eligible,unavailable_reason}]` (or a numeric
summary). Every entry also returns a `provenance` object with `origin`,
`reported_by`, `method_summary`, optional publication `reference`,
`expression_derived`, `recomputed_by_trace` and a cross-study `comparability`
statement. TRACE distinguishes harmonized clinical fields, source-reported
annotations, source-reported molecular calls and user declarations. It never
silently converts one class into another. Levels with fewer than five patients remain auditable but cannot be
selected as an individual group. The server validates the requested ID and
levels against the active
cohort or release. TCGA entries are deliberately curated from standardized
metadata, primary-diagnosis GDC rows, TCGA-CDR fields and selected marker-paper
annotations; identifiers, survival times and undeclared technical columns are
not accepted. External catalogs combine namespaced patient/sample metadata,
decode bounded serialized source objects, canonicalize equivalent category
spellings and suppress duplicate standardized fields. Low-coverage and
post-resection variables retain explicit interpretation notes.

### Curated external RNA-seq repository

Expression-layer responses include `coverage`: unique linked `patient_count`,
matrix-column `sample_count`, `observation_unit`, and linked `endpoints` with
patient/event counts. These describe the selected expression data **before**
tissue selection, patient filters and model exclusions—not the final model N.
The `/endpoints` discovery route retains release-wide counts. Use the selected
layer's coverage when describing who can contribute to an analysis.

For FU-GBC, the source layer contains 201 RNA profiles from 135 patients
(135 tumors and 66 matched adjacent tissues). The `paired_difference` layer
contains 66 patient-level contrasts, calculated as
`log2(TPM_tumor + 1) - log2(TPM_adjacent + 1)`. Positive values mean higher
expression in tumor. This is a different measurement and population, not
another normalization or 66 additional patients. Adjacent tissue is not an
independent healthy-control cohort. API and MCP layer discovery use the same
coverage calculation; existing source matrices and frozen release QC are not
rewritten. Future imports also record per-layer patient/endpoint coverage in QC.

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/cancer-types` | Coverage ledger for TCGA and registered external-only disease types |
| `GET` | `/datasets` | Compute-ready releases, optionally filtered by `analysis_type` |
| `GET` | `/dataset-candidates` | Reviewed candidates, decisions and blockers; discovery only |
| `GET` | `/datasets/{dataset_id}` | Release, source, license, QC, endpoint and expression-layer detail |
| `GET` | `/datasets/{dataset_id}/endpoints` | Release-specific endpoint definitions and QC |
| `GET` | `/datasets/{dataset_id}/expression-layers` | Source units, transforms and scale caveats |
| `GET` | `/datasets/{dataset_id}/filters` | Available curated clinical filters |
| `GET` | `/datasets/{dataset_id}/genes` | Search genes in one pinned expression layer |
| `GET` | `/datasets/{dataset_id}/genes/resolve` | Resolve a gene against one pinned layer |
| `GET` | `/datasets/{dataset_id}/download/{kind}` | Download manifest, QC, license, or licensed matrix/metadata/gene index |

Each `/datasets` item includes explicit `capabilities`, `available_modules` and
an `endpoints` array with the usable endpoint code, label, patient count, event
count, time origin and event definition. Use, for example,
`/datasets?analysis_type=gsea` or
`/datasets?analysis_type=expression_comparison` to request only compatible
releases. The release-specific endpoint route remains the authoritative detail
surface.

`/dataset-candidates` is deliberately separate. It can be filtered by
`disease_id`, `status`, `analysis_type` and `query`, but a candidate ID cannot
be sent to a compute endpoint until its versioned release has passed QC and
appears in `/datasets`.

To analyze an external release, use the cohort identifier returned by the
dataset catalog and pin the dataset, release and expression layer. Releases for
a TCGA-covered disease retain that TCGA cohort identifier; external-only
diseases use their registered `EXT-*` identifier (for example `EXT-CLL`):

```json
{
  "cohort": "TCGA-BLCA",
  "dataset_id": "cbioportal-blca-iatlas-imvigor210-2017",
  "dataset_release_id": "cbioportal-blca-iatlas-imvigor210-2017-1da5c747e4fd",
  "expression_layer_id": "provided_tpm_profile",
  "gene_symbol": "MKI67",
  "endpoint": "OS",
  "cutpoint_method": "median",
  "adjustment_covariates": []
}
```

The analysis uses no TCGA patients or expression values when `dataset_id` is
present. Each external release supports only the workflows declared by its
frozen capability block; a molecular release may correctly support expression
comparison and GSEA without supporting survival. Unsupported requests are
rejected before queueing with a reason and the compatible analyses. Within Pan-cancer, the **TCGA
reference** mode remains TCGA-only; the separate, opt-in **TCGA + external
hierarchical** mode can include eligible external releases as distinct study
universes. It never appends their expression columns to a TCGA matrix.

### Reproducible paper examples

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/examples/paper` | Curated manuscript benchmark, diagnostics, and figure catalog |
| `GET` | `/examples/paper/figures/{analysis_id}/{kind}` | Pinned benchmark figure (`continuous`, `km`, or `cox`) |

Paper-example figures are pinned to the versioned manuscript benchmark and are
not removed by the normal 90-day public-job retention process. The catalog
includes positive, unsupported, endpoint-sensitive, and diagnostic results,
including the BIRC5 and CA9 primary-versus-ordinal-sensitivity pan-cancer cases.

### Analyses and jobs

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/analyses` | Submit one gene/signature analysis |
| `POST` | `/analyses/combined` | Submit a two-signature analysis |
| `POST` | `/analyses/signature-panel` | Submit a 2--6 signature main-effects panel |
| `POST` | `/analyses/batch` | Submit up to 25 analyses |
| `POST` | `/analyses/multiverse` | Submit one Robustness analysis (declared specification family) |
| `GET` | `/gsea/collections` | List frozen gene-set collections and ranking metrics |
| `POST` | `/analyses/gsea` | Submit one correlation-aware two-group pathway analysis with descriptive preranked effects |
| `POST` | `/analyses/expression-comparisons` | Submit a targeted two-group expression comparison |
| `POST` | `/analyses/sessions/export` | Export selected browser jobs as one exploratory record |
| `GET` | `/jobs/{job_id}` | Poll any compute job |
| `GET` | `/analyses/{analysis_id}` | Retrieve a completed analysis |
| `GET` | `/analyses/batches/{batch_id}` | Retrieve a completed batch |
| `GET` | `/analyses/multiverses/{session_id}` | Retrieve a completed Robustness analysis |
| `GET` | `/analyses/multiverses/{session_id}/download/{kind}` | Download a Robustness artifact |
| `GET` | `/analyses/gsea/{gsea_id}` | Retrieve a completed GSEA |
| `GET` | `/analyses/gsea/{gsea_id}/download/{kind}` | Download a GSEA artifact |
| `GET` | `/analyses/expression-comparisons/{comparison_id}` | Retrieve a completed expression comparison |
| `GET` | `/analyses/expression-comparisons/{comparison_id}/download/{kind}` | Download an expression-comparison artifact |
| `GET` | `/analyses/sessions/{report_id}` | Retrieve an exploratory session record |
| `GET` | `/analyses/sessions/{report_id}/download/{kind}` | Download a session artifact |
| `GET` | `/analyses/{analysis_id}/download/{kind}` | Download an analysis artifact |

Completed comparison batches include `grouped_family` (contract
`compare-grouped-family-v1`). REST and MCP return the same summary:
`requested`, `completed`, `failed`, `evaluable`, `unavailable`, and an indexed
`tests` list with `test`, `p_value`, `bh_q_value` and `bonferroni_p_value`.
Maxstat uses its Lau94 selection-corrected p-value before between-test correction;
it never falls back to the descriptive grouped log-rank p-value. Fixed cutpoints
use log-rank. BH and Bonferroni use the number of valid grouped tests in the
submitted batch. Failed tests and missing corrected p-values remain counted and
visible, with null adjusted values, but do not enter that denominator. This is
the evaluable-test family, not a correction for choosing successful analyses or
selecting between runs. Continuous Cox, grouped Cox and RMST remain separate.
Compare's summary CSV records this family; per-analysis downloads retain their
individual scope. Existing batches may lack `grouped_family`; new batch cache
keys include this contract to avoid reusing those legacy responses.

Analysis download kinds are `zip`, `continuous_png`, `continuous_svg`,
`continuous_csv`, `png`, `svg`, `cox_png`, `cox_svg`,
`cox_univariable_png`, `cox_univariable_svg`, `cox_multivariable_png`,
`cox_multivariable_svg`,
`signature_panel_joint_png`, `signature_panel_joint_svg`,
`signature_panel_adjusted_png`, `signature_panel_adjusted_svg`,
`model_results_csv`, `score_correlations_csv`,
`cumulative_incidence_png`, `cumulative_incidence_svg`, `csv`, `json`,
`audit_json`, `audit_html`, `attestation`, `txt`, and `methodology`.

Analysis pipeline v6.15 added
`plot_style.cox_forest.model_layout: "combined" | "separate"`. `combined`
remains the default. `separate` creates an extra univariable forest and an
extra forest containing the requested evaluable adjusted multivariable models; a file
is omitted when its model family is not evaluable. Optional
`univariable_plot_title` and `multivariable_plot_title` fields customize those
titles. The original `cox_png` and `cox_svg` remain available for backward
compatibility.

Plot-style contract v1.1 adds
`plot_style.cox_forest.multivariable_display: "all" | "selected"` and
`multivariable_model_ids`. Supported row IDs are `stage_adjusted`,
`grade_adjusted`, `stage_grade_adjusted`, and `user_adjusted`. The default is
`all`. A selected subset is part of the request and cache identity, so updating
it requires a new run and is recorded in the metrics, audit and downloads. The
forest retains the axis limits derived from every completed Cox model so that
spacing and scale remain comparable when rows are hidden.

Analysis pipeline v6.17 adds shared axis typography and panel-boundary fields:
`axis_text_bold`, `axis_text_italic`, `axis_title_bold`,
`axis_title_italic`, and `plot_frame: "open" | "axes" | "box"`. The default
remains plain text with an open panel. These fields affect the Kaplan-Meier,
continuous Cox, grouped Cox, competing-risk and signature-panel figures
without changing any fitted model. The complete specification is retained in
the request, cache identity, audit and methodology exports.

Analysis pipeline v6.18 makes randomized-arm separation mandatory for
IMmotion150 PFS. The dataset filter catalog exposes `study_arm` with the three
source assignments: `Atezolizumab`, `Atezolizumab + Bevacizumab`, and
`Sunitinib`. Requests must include one, and only one, of these levels in
`filters.custom_filters`; pooled PFS requests are rejected by every survival
entry point, including batch, Robustness and MCP submissions.

Analysis pipeline v6.19 preserves that rule and gives separately rendered
univariable and multivariable forest plots one shared log-HR scale, physical
width and row-spacing contract. Combined-signature v4.10, signature-panel
v1.3 and Robustness v2.5 carry the same visual comparability contract.

Signature-panel pipeline v1.0 applies BH and Bonferroni separately to the
signature terms in its univariable, joint and adjusted model families.
Clinical covariate terms are not part of those multiplicity families.
Pairwise Pearson/Spearman score correlations and gene-overlap/Jaccard values
are exported as descriptive context and do not trigger a warning threshold.
For DSS, DFI and PFI, matching Fine-Gray main-effects families are reported
alongside the cause-specific Cox results when event coding is evaluable.

Starting with analysis pipeline v6.0, every single-gene or single-signature
analysis first fits one Cox model per +1 within-analysis expression-score
standard deviation using the full eligible expression-complete population.
The same population is used for a three-degree-of-freedom restricted
cubic-spline profile with knots at the 5th, 35th, 65th, and 95th percentiles.
The spline-versus-linear likelihood-ratio test is reported as a nonlinearity
diagnostic, not a pass/fail rule. `metrics.continuous_analysis` contains the
linear models, spline profile, predictor scaling, population size, and event
count. It remains identical when only the requested cutpoint changes.

Analysis pipeline v6.2 accepts an optional `adjustment_covariates` list for one
exact, complete-case user-adjusted model. Supported imported fields are
`age_at_index`, `stage`, `grade`, `gender`, and `race`. Age is continuous per
10-year increase; major pathologic stage (`0`, `I`, `II`, `III`, `IV`) and
histologic grade (`G1`–`G5`) are ordinal trends; GDC gender and race are
categorical treatment contrasts. Missing, unknown, and nonstandard categories
are excluded from that model.

Analysis pipeline v6.7 additionally accepts an inline, versioned
`external_covariates` dataset and an explicit
`external_adjustment_covariates` selection. The dataset is linked by exact TCGA
participant barcode after the expression-complete population is constructed.
It is limited to 10 variables and 2,000 unique participant rows. Only public
TCGA identifiers are permitted; names, local identifiers and protected
clinical data must not be submitted.

```json
{
  "external_covariates": {
    "schema_version": "tcga-trace-external-covariates-v1",
    "source_label": "Curated LGG annotations",
    "definitions": [
      {
        "name": "idh_status",
        "label": "IDH status",
        "value_type": "categorical",
        "levels": ["Wild type", "Mutant"],
        "reference_level": "Wild type"
      },
      {
        "name": "tumor_purity",
        "label": "Tumor purity",
        "value_type": "continuous",
        "unit": "proportion",
        "effect_unit": 0.1
      },
      {
        "name": "molecular_risk",
        "label": "Molecular risk",
        "value_type": "ordinal",
        "levels": ["Low", "Intermediate", "High"]
      }
    ],
    "rows": [
      {
        "patient_id": "TCGA-AB-0001",
        "values": {
          "idh_status": "Mutant",
          "tumor_purity": 0.72,
          "molecular_risk": "High"
        }
      }
    ]
  },
  "external_adjustment_covariates": [
    "idh_status",
    "tumor_purity",
    "molecular_risk"
  ]
}
```

Continuous coefficients use the declared `effect_unit`; categorical variables
use treatment contrasts against the declared `reference_level`; ordinal
variables use a one-level trend in the declared `levels` order. Missing values
are handled by model-specific complete-case analysis. The normalized dataset
participates in request identity and the reproducibility hash. Audit exports
record its SHA-256, matching and missingness QC, definitions, selected
variables and patient-level values.

The exact user model is added to continuous, grouped, and two-signature
interaction families. Fixed stage, grade, and stage-plus-grade models remain
available as auxiliary sensitivities. When a user model is requested but is
not evaluable, the response reports `not_evaluable`; it never substitutes a
different auxiliary model as the requested estimate. Every Cox model records
model-specific complete-case patients, events, fitted parameters, events per
parameter, and `covariate_encoding` metadata.

Starting with analysis pipeline v6.1, every continuous, grouped, and
two-signature interaction Cox model also contains:

- `information_diagnostics`: fitted parameter count, observed events, events
  per parameter, `adequate`/`caution`/`severe` status, thresholds, standard-fit
  instability, extreme-estimate status, and trigger reasons.
- `penalized_sensitivity`: `not_triggered`, `completed`, or `failed`. Completed
  results use `coxphf` Firth penalized partial likelihood (penalty 0.5),
  profile penalized-likelihood confidence intervals and tests, and record
  Breslow ties, iterations, package version, effect estimate, and trigger.

The caution threshold is below 10 events per fitted parameter and the severe
threshold is below 5. These are interpretation diagnostics, not model
exclusion rules. Standard `survival::coxph` estimates retain Efron ties and
remain the primary reported fit; Firth is an adjacent sensitivity.

Kaplan-Meier, grouped Cox, and RMST outputs are cutpoint-sensitivity views.
Maxstat is outcome-optimized; its grouped effect estimates and RMST remain
post-selection summaries. Marker-term and global `cox.zph` results are reported
separately and modify interpretation rather than excluding an association.
When the marker-term `cox.zph` p-value is below 0.05, completed grouped,
continuous, interaction and pan-cancer Cox models also return
`time_varying_effect`. The diagnostic uses a fixed primary split at 730.5 days
and fixed 1- and 5-year sensitivity splits:

- `status`: `completed`, `skipped`, `failed`, `not_triggered`, or
  `not_evaluable`;
- `periods.early` and `periods.late`: interval support, HR, 95% CI and p-value;
- `change`: the late-to-early HR ratio, 95% CI and p-value;
- `support`: events on each side and patients entering the late period; and
- `sensitivity_analyses`: the same contract for the 1- and 5-year splits; and
- the trigger, fixed split rule, minimum support, tie handling and robust
  variance specification.

The split is never selected from expression, event times, cutpoints or effect
estimates. Estimation requires at least 5 events per period and 10 patients
entering the late period. The ratio is the Wald contrast for the
marker-by-period interaction, and each two-period model is a coarse
approximation to a potentially smooth time-varying effect. This is a PH
interpretation diagnostic, not another primary test or an exclusion rule.
Robustness continuous and grouped CSV exports retain the same fields.

### Maximally selected cutpoint implementation

The production maxstat threshold is selected by
`survminer::surv_cutpoint` from complete endpoint-eligible records. The default
eligible split range is 15%–85%; at least 10 complete patients, one event,
expression variation and one eligible candidate split are required. The
selection-adjusted probability is calculated separately with
`maxstat::maxstat.test`, `smethod="LogRank"`, `pmethod="Lau94"`,
`minprop=0.15` and `maxprop=0.85` (`maxstat` 0.7-26). The raw approximation is
retained and the API probability is bounded to [0,1]. `Lau94` is the improved
Bonferroni approximation of Lausen, Sauerbrei and Schumacher (1994), not the
Brownian-bridge `Lau92` approximation or the later Hothorn–Lausen
exact/conditional procedure.

The threshold and maximally selected-rank probability are distinct from the
downstream grouped log-rank, Cox and RMST summaries. Those grouped summaries
reuse the outcome-selected split and remain post-selection descriptions. In a
Robustness multiplicity family, maxstat contributes the Lau94-adjusted
maximally selected-rank probability when available; it does not contribute the
naive grouped log-rank probability.

### Competing-risk estimands

Analysis pipeline v6.10 uses the TCGA-CDR `ExtraEndpoints` status and time
columns for DSS, DFI, and PFI. The structured coding is:

- `0`: censored;
- `1`: event of interest; and
- `2`: endpoint-specific competing death.

For DSS, the event of interest is death from the index cancer and code 2 is
death from another cause. For DFI, code 1 is recurrence after a disease-free
interval and code 2 is death before documented recurrence. For PFI, code 1 is
progression or death with tumour and code 2 is death without a preceding
progression event.

Kaplan-Meier and Cox outputs continue to treat code 2 as censored at its
recorded time. They therefore describe event-free survival and the
cause-specific hazard under the corresponding censoring assumption.
`metrics.competing_risks` retains code 2 as a competing event and reports a
different estimand:

- `coding`: exact source columns, status labels, and both estimand contracts;
- `cumulative_incidence`: nonparametric group curves, event-state counts,
  Gray's K-sample test, and pointwise estimates at 1, 3, and 5 years;
- each fixed-horizon estimate includes an Aalen-variance 95% interval,
  patients at risk, and a low-support flag below 5 at risk;
- `grouped_fine_gray_models`: subdistribution hazard ratios for the requested
  expression groups; and
- `continuous_fine_gray_models`: subdistribution hazard ratios per +1
  within-analysis expression SD.

Fine-Gray families include univariable, exact user-adjusted, and available
auxiliary stage/grade models. Every model reports its own complete-case
patients, target events, competing events, fitted parameters, events per
parameter, covariate encoding, contrast, SHR, 95% interval, and p-value.
Unavailable or unsupported models remain present with a reason. OS returns
`applicable: false`; a competing-risk endpoint without a code-2 event keeps
the contract visible but skips estimation.

Cause-specific HRs and Fine-Gray SHRs answer different questions and are never
labelled as interchangeable. The CIF PNG/SVG, structured result, methodology,
JSON/HTML audit, patient CSV, exact R helper, and reproduction capsule preserve
the same coding and result.

These calculations use `cmprsk` 2.2-12. Grouped cumulative incidence and
Gray's test use `cmprsk::cuminc` with `rho=0` and censor code 0. Fine-Gray
models use `cmprsk::crr` with event code 1, censor code 0 and at most 50 Newton
iterations; grouped models estimate the censoring distribution separately by
expression group. Estimation requires at least 10 complete patients, five
events of interest, one competing event, predictor variation and a full-rank
design. Non-convergence and low events per fitted parameter remain visible.
The signature-panel DSS/DFI/PFI main-effects families also use
`cmprsk::crr` under their common-population design.

The competing-risk contract applies only to TCGA DSS, DFI and PFI when the
TCGA-CDR code-2 event is present. It is not run for OS and is not synthesized
in either Pan-cancer mode.

Completed analysis responses also include two decision-support fields:

- `notices`: structured messages with `category` (`cohort`, `method`, `model`,
  or `availability`), `severity` (`info`, `caution`, `not_evaluable`, or
  `error`), decision `scope` (`primary`, `requested_adjustment`, `auxiliary`,
  or `context`), and `priority` (`high`, `medium`, or `low`).
- `diagnostics`: the decision-facing primary model and, when declared in the
  request, the exact clinical-adjusted model, including each model identifier, label, family and
  top-level status. Primary status is `clean`, `caution`, or `not_evaluable`;
  adjusted status additionally uses `not_requested` when no adjustment was
  declared. Message counts are reported separately.

Primary-result failures and cautions are never hidden. Without a declared
clinical adjustment, the unadjusted model remains primary; stage, grade and
stage-plus-grade models are auxiliary sensitivities. With an adjustment
request, its exact covariate set is selected before fitting and the adjusted
model becomes decision-facing while the unadjusted result remains visible. An
unevaluable requested adjustment remains visible without invalidating an
available unadjusted result. Auxiliary-model diagnostics and cohort/method
provenance remain available at lower priority and do not contaminate primary
status. The original `warnings` array remains present for backward
compatibility; new clients should prefer `notices` and `diagnostics`.

### Robustness across analysis choices

The API route remains `POST /analyses/multiverse` for compatibility. It powers
the **Robustness** interface through prespecified multiverse and
specification-curve analysis, and accepts one cohort, one gene or multi-gene
signature, one or more QC-eligible endpoints, compatible scoring methods, and
one or more cutpoint methods. The full Cartesian grid is frozen before
execution and is limited to 72 specifications.
When `percentile` is selected, `custom_percentile` must be numeric and between
1 and 99. Clients should validate this before submission.

The response separates two multiplicity families:

- `continuous_references`: one cutpoint-independent Cox test per unique
  endpoint and scoring method. Repeated cutpoints do not repeat this test.
- `specifications`: every endpoint-by-scoring-by-cutpoint sensitivity. Maxstat
  uses its Lau94 corrected p-value for grouped-family multiplicity; its grouped
  HR and RMST remain labelled post-selection.

BH and Bonferroni values are calculated independently within each family. PH
diagnostics remain interpretation fields and no retained/not-retained verdict
is generated. The execution ledger preserves every planned cell, including
endpoint-QC failures and non-evaluable models, together with request hashes,
child analysis IDs and child audit hashes. It covers this declared family, not
unrelated ad hoc runs made elsewhere in a browser session.

Robustness download kinds are `svg`, `csv`, `continuous_csv`, `ledger`,
`json`, `audit_json`, `audit_html`, `attestation`, `methodology`, and `zip`.

### Correlation-aware two-group pathway analysis

`POST /analyses/gsea` tests the server-pinned gene-set collection with limma
CAMERA and ranks genes by an explicit group B minus group A contrast for
descriptive ES, NES and leading-edge summaries. Positive NES favors group B
and negative NES favors group A. Group definitions support:

- `clinical`: disjoint levels from a variable declared by the selected
  dataset's `clinical_grouping_variables` catalog, or a median/fixed threshold
  for any catalog-declared numeric field. Examples include standardized stage,
  age, pack-years, BRCA PAM50, glioma IDH/1p19q and available histologic or MSI
  annotations;
- `survival`: the exact sample assignments retained by a completed two-group
  survival analysis, identified by `survival_analysis_id`;
- `expression`: a single-gene, mean, z-score, weighted, singscore, ssGSEA or
  AUCell signature split by median, upper quartile, outer quartiles or a
  declared percentile.

Primary pathway p-values use limma CAMERA 3.62.2 with a B-minus-A design,
empirical-Bayes variance moderation with a mean--variance trend, and residual
inter-gene correlation estimated separately for every eligible set
(`inter.gene.cor=NA`, `allow.neg.cor=FALSE`). The two-sided competitive
p-values are adjusted by Benjamini--Hochberg across the complete eligible
collection. The response records CAMERA direction, estimated correlation, NES
direction and whether the directions agree. Summary counts among pathways that
meet CAMERA FDR use CAMERA direction; NES direction remains a separate
descriptive field.

The descriptive ranking uses an unmoderated Welch t statistic or
signal-to-noise score. Weighted enrichment uses exponent 1 and deterministic
gene-set permutations only to normalize ES to NES; gene-set-permutation
p-values are neither returned nor used as evidence. Only complete-case
variable genes enter both layers. Expression-derived groups, including PAM50
and groups inherited from expression-based survival analyses, are marked
`conditional_exploratory`: CAMERA p-values and FDR describe the observed
contrast but are not independent confirmation. Inherited maxstat groups also
receive an outcome-informed circularity warning.

Completed schema-v1 GSEA records remain readable and downloadable for
reproducibility. Their original gene-set-permutation p-values and FDR are
labelled as a legacy method and are never presented as CAMERA evidence. New
compute requests always use schema v2; TRACE does not rewrite or reinterpret
v1 artifacts.

The sample-group export includes every patient considered after eligibility
and matrix matching. It records the resolved clinical value, variable ID and
source field; patients outside the binary contrast remain auditable with
`missing_clinical_value` or `unselected_clinical_level` instead of disappearing
from the CSV.

All Survival, Compare, Robustness, Expression comparison and GSEA requests can
add up to ten catalog-declared patient restrictions through
`filters.custom_filters`. Obtain each stable `variable_id` and its observed
levels from the selected dataset's `clinical_grouping_variables` response.
Selected levels within one variable use OR; different variables use AND.
Numeric variables accept a minimum, a maximum or both. These restrictions
change cohort eligibility and are audited, but never become automatic Cox
covariates.

For example, an AJCC N comparison restricted to PAM50 Luminal A in TCGA-BRCA
includes:

```json
{
  "filters": {
    "sample_population": "primary_solid",
    "custom_filters": [
      {
        "variable_id": "paper_BRCA_Subtype_PAM50",
        "categorical_levels": ["LumA"]
      }
    ]
  },
  "grouping": {
    "source": "clinical",
    "clinical_variable": "ajcc_pathologic_n",
    "group_a_values": ["N0"],
    "group_b_values": ["N1", "N1a", "N1b", "N1c", "N2", "N3"]
  }
}
```

The exact N levels must be selected from the live catalog. A variable cannot
both define the groups and appear in `custom_filters`. PAM50 is
an author-provided, expression-derived TCGA-BRCA call; TRACE does not rerun the
classifier. It carries circularity and method-dependent cross-study
comparability warnings. Basal-like PAM50 is not
silently labeled TNBC; TNBC requires observed ER-negative, PR-negative and
HER2-negative status.

Each completed run retains the NES landscape and adds a reproducible DotPlot
for up to 30 pathways with lowest CAMERA FDR. Dot position and divergent color
encode descriptive NES using a dark-blue-to-white-to-red scale centered at
zero; circle area is proportional to `min(-log10(CAMERA FDR), 10)`. Legends are above the clean
panel, pathway labels are on the right and a dashed vertical reference marks
NES 0. The cap and both group directions are printed in the accessible SVG.
The DotPlot is checksummed in the audit report and included in the signed ZIP.

The bundled, checksum-verified catalog contains a frozen ImmPort GMT with 153
immune lists and three separate human Gene Ontology collections: Biological
Process (8,195 sets), Molecular Function (2,202) and Cellular Component
(1,287). GO uses the official 2026-06-19 release
(DOI:10.5281/zenodo.20943148, CC BY 4.0); direct annotations are propagated
over exactly `is_a` and `part_of`, while `NOT`-qualified annotations and
obsolete terms are excluded. `GET /gsea/collections` exposes release,
attribution, source and output checksums. Runtime jobs never download gene
sets. Full generation provenance and the attribution notice are documented in
`backend/gene_sets/README.md`. GSEA download kinds are `csv`, `ranking_csv`,
`groups_csv`, `leading_edges_csv`, `svg` (NES landscape), `dotplot_svg`,
`json`, `input`, `gene_set_manifest`, `audit_json`, `methodology`,
`camera_r_script`, and `zip`.
New runs also include `attestation` for the detached Ed25519 audit receipt.

### Grouped expression comparison

`POST /analyses/expression-comparisons` compares 1--25 requested genes across
one binary grouping. It accepts the same `clinical`, `survival` and
`expression` grouping definitions documented for GSEA. The analysis therefore
can use standardized clinical variables, reuse the exact assignments from an
unexpired two-group survival result, or split a single-gene/multi-gene score.
The normalized expression layer and cohort filters are declared in the request.

For every usable target gene the result reports group sizes, means, medians and
dispersion, plus the expression difference as group B minus group A. It
calculates an unequal-variance Welch test and a Mann--Whitney rank-sum
sensitivity where inference is eligible. A target that overlaps the signature
used to construct an expression-derived group is retained as
`descriptive_only`, with null p/FDR values and `significant_at_fdr: false`.
Benjamini--Hochberg FDR is applied separately across the remaining requested,
inferentially evaluable genes for the Welch and Mann--Whitney families; the
service does not claim correction across the full matrix. Non-overlapping
targets under expression-derived grouping remain exploratory, and inherited
maxstat groups carry the outcome-informed circularity warning.
If the selected clinical grouping itself was derived from transcriptomic
expression (for example PAM50), every requested target is `descriptive_only`,
its p/FDR values are null and it is excluded from both BH families.

Example request:

```json
{
  "cohort": "TCGA-LIHC",
  "expression_scale": "log2_tpm",
  "genes": ["CDC20", "BIRC5", "MKI67"],
  "grouping": {
    "source": "clinical",
    "clinical_variable": "stage",
    "group_a_values": ["Stage I", "Stage II"],
    "group_b_values": ["Stage III", "Stage IV"],
    "group_a_label": "Early",
    "group_b_label": "Advanced"
  },
  "fdr_threshold": 0.05
}
```

Download kinds are `values_csv`, `groups_csv`, `statistics_csv`,
`violin_svg`, `boxplot_svg`, `heatmap_svg`, `json`, `input`, `methodology`,
`audit_json`, `attestation`, and `zip`. The complete on-demand ZIP contains
`input.json`, `expression_values.csv`, `sample_groups.csv`,
`gene_statistics.csv`, all three SVGs, `methodology.txt`, `result.json`,
`audit_report.json` and `attestation_receipt.json`. The audit binds the request,
group assignments, expression values, gene statistics and bounded result core
with SHA-256 records for every rendered artifact.
The cache/audit contract is versioned as
`grouped-expression-comparison-welch-wilcoxon-bh-contract-v1.4`.

### Exploratory session history

`POST /analyses/sessions/export` accepts up to 200 selected run events that
reference terminal `job_id` values, plus browser-supplied labels and
timestamps. The server resolves the authoritative requests and results from
its compute-job records. Patient-level records and external-covariate row
values are not embedded.

The report applies BH and Bonferroni separately to unique continuous Cox,
grouped cutpoint, and two-signature interaction hypotheses. Exact duplicate
hypotheses are counted once while repeated run events remain in the ledger.
Prespecified Robustness analyses, pan-cancer scans, signature panels, GSEA results and
grouped expression comparisons retain their internal correction and appear
only as managed-family references.
This is explicitly a post hoc, export-defined scope: it does not claim that no
other runs occurred and produces no retained/not-retained verdict.

Session download kinds are `json`, `runs_csv`, `hypotheses_csv`, `ledger`,
`audit_json`, `audit_html`, `attestation`, `methodology`, and `zip`.

### Pan-cancer

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/pancancer/survival` | Submit a TCGA reference scan |
| `GET` | `/pancancer/survival/{scan_id}` | Retrieve a TCGA reference scan |
| `GET` | `/pancancer/survival/{scan_id}/download/csv` | Download TCGA reference results |
| `GET` | `/pancancer/survival/{scan_id}/download/{kind}` | Download a TCGA reference artifact |
| `POST` | `/pancancer/hierarchical/preflight` | Inspect hierarchical eligibility before computation |
| `POST` | `/pancancer/hierarchical-survival` | Submit a hierarchical TCGA + external synthesis |
| `GET` | `/pancancer/hierarchical-survival/{scan_id}` | Retrieve a completed hierarchical synthesis |
| `GET` | `/pancancer/hierarchical-survival/{scan_id}/download/{kind}` | Download a hierarchical reproducibility artifact |
| `GET` | `/pancancer/immune-screens` | List precomputed screens |
| `GET` | `/pancancer/immune-screens/{screen_id}` | Retrieve one screen |
| `GET` | `/pancancer/immune-screens/{screen_id}/download/{kind}` | Download screen data |

#### TCGA reference mode

The existing `/pancancer/survival` contract is the **TCGA reference** mode.
Its pipeline and cache identity remain
`server-attested-common-scale-reml-hksj-contract-v3.3`; adding hierarchical
analysis does not reinterpret, invalidate, or silently recompute its results.
It remains limited to TCGA cohorts and continues to accept the established
single-gene and signature request schema.

`signature_method` accepts `single`, `mean`, `zscore`, `weighted`,
`singscore`, `ssgsea`, or `aucell`. Multi-gene requests send their normalized
`signature_genes` explicitly. Each cohort result carries its own compact
`signature_scoring` contract (resolved coverage, scoring population, method
parameters, engine, hashes, and the feature universe when applicable); the
top-level `signature` is only the shared request definition and never a copy
of the first cohort's scoring contract.

TCGA reference artifact kinds are `patients`, `methodology`, `audit_json`,
`audit_html`, `attestation`, `raw_r_json`, `result_json`, and `zip`. The
dedicated `csv` route returns the cohort-level table.

The TCGA reference pipeline reports each cohort's continuous Cox effect per one
within-cohort expression SD as a descriptive, non-pooled estimate. For a
single gene or a mean/weighted signature, it also recovers the exact
coefficient per +1 common input-score unit and synthesizes comparable effects
with REML random effects, HKSJ inference, and a 95% prediction interval.
Synthesis requires one endpoint and one model family. Cohort-standardized
z-score signatures, mixed endpoints, and selected effects from different
adjustment families are deliberately not pooled. Ordinal stage, grade, and
stage-plus-grade sensitivities and BH-FDR remain separated by model family.
Missing clinical covariates produce `not_evaluable`, not a failed primary
model. The response and cohort CSV expose both the descriptive `hazard_ratio`
fields and the `common_scale_*` synthesis fields together with `effect_scale`.

#### Hierarchical TCGA + external mode

The hierarchical mode is an additional workflow inside Pan-cancer, not a new
application section and not a replacement for the TCGA reference scan. It is
versioned independently as
`hierarchical-study-cancer-iqr-reml-mhksj-contract-v1.3`.

`POST /pancancer/hierarchical/preflight` is synchronous and does not create a
compute job. It applies the versioned study-universe registry and returns the
normalized request, registry version, eligible and excluded universes,
cancer-level support, warnings, and explicit reason codes. Submit the same
request to `POST /pancancer/hierarchical-survival`; that route creates an
asynchronous `pancancer_hierarchical` job. Poll `/jobs/{job_id}`, then follow
its `result_url` or use the hierarchical result and download routes above.
The response `schema_version` values are
`tcga-trace-hierarchical-pancancer-preflight-v1` and
`tcga-trace-hierarchical-pancancer-result-v1`, respectively.

The preflight summary distinguishes all represented cancers from cancers with
at least two independent primary study clusters. It exposes
`replicated_cancers`, `replicated_events`, `preliminary_global_ready`, and
`formal_global_ready`; `can_run` may still be true when only descriptive
study- or cancer-level estimates are possible.

The request deliberately has a narrow primary estimand:

```json
{
  "gene_symbol": "MKI67",
  "scope": "combined",
  "cancers": [],
  "study_ids": [],
  "endpoint": "OS",
  "clinical_context": "primary_baseline",
  "time_origin_policy": "strict_baseline",
  "effect_scale": "within_study_iqr",
  "overlap_policy": "independent_clusters",
  "min_patients": 20,
  "min_events": 10,
  "min_censored": 5,
  "include_exploratory": false,
  "fdr_threshold": 0.05
}
```

`gene_symbol` is normalized to uppercase and only one gene is accepted. Known
legacy aliases are resolved once before either TCGA or external universes are
selected (for example, `P53` to `TP53` and `HER2` to `ERBB2`). Preflight and
completed results retain `requested_gene_symbol` and `resolved_gene_symbol`.
Equivalent alias/canonical requests select the same canonical estimand and
study universes but receive separate artifact identities, preventing one
query's audit provenance from overwriting the other's. Each study record also
exposes the resolved symbol, source feature identifier,
mapping source and release-specific expression-row index under `gene_mapping`.
The endpoint is strict overall survival (`OS`). `scope` may be `combined`,
`tcga_only`, or `external_only`; empty `cancers` and `study_ids` selections
mean all registry-compatible universes in that scope. Clinical context is
prespecified as `primary_baseline`, `advanced_treatment`, or
`hematologic_diagnostic`. Endpoint, time-origin class, clinical context, and
model family must be compatible before effects can enter the same synthesis.

Each TCGA cohort or external release remains its own analytical universe. The
server selects one eligible expression-complete sample per patient, fits a
separate continuous Cox model, and reports the hazard ratio for a +1 IQR
increase calculated within that universe. This makes the coefficient unit
explicit without claiming that source expression values were harmonized.
Expression matrices and patient rows are never concatenated across studies.

The registry records source, cancer mapping, clinical context, time origin,
study/dependency cluster, and known exact or partial overlap. Releases in one
dependency cluster are not counted as independent replication; unresolved
dependence or incompatible context remains visible in the preflight exclusion
ledger rather than being silently pooled.

The hierarchical cache identity includes a canonical SHA-256 of the universe
registry, cancer taxonomy, every study manifest (including inactive entries),
registry/schema versions and all published release-manifest identities. Thus a
change that can alter grouping, context, time origin or source data cannot
silently reuse an older completed job. Preflight itself is synchronous and is
recomputed on every request.

Eligible log hazard ratios are synthesized with random effects in a declared
hierarchy: study evidence within cancer, then cancer estimates in the global
pan-cancer estimate. REML estimates heterogeneity and modified HKSJ supplies
interval inference using the rule `max(1, q)`, which prevents its standard
error from falling below the conventional random-effects standard error.
Both the unmodified scale and whether the floor was applied remain in the
result for audit. Results expose study-, cancer-, and global-level effects, 95%
prediction intervals where estimable, heterogeneity statistics, and
leave-one-study/cancer-out sensitivity analyses. Study-level p-values are
descriptive. A cancer supported by only one independent study remains
descriptive and receives no BH-FDR value. BH-FDR is applied only to the family
of cancer effects replicated by at least two independent study clusters,
while the global estimate is one declared synthesis. At least two such
replicated cancers are required to estimate the global effect. Formal
pan-cancer support additionally requires at least five replicated cancers and
100 OS events across their contributing primary studies.

Primary support requires at least 20 patients, 10 OS events, and 5 censored
patients in a universe. When `include_exploratory` is enabled, universes with
at least 10 patients, 5 events, and 5 censored patients may be shown in a
separately labelled exploratory tier; they do not silently become primary
replication. Preflight exclusions, fitted failures, and insufficient
independent support remain in the returned ledger.

There is no global Kaplan--Meier curve for this mode. Such a curve would mix
study-specific baselines and time origins and imply a pooled patient cohort
that the analysis intentionally does not create. Hierarchical download kinds
are `studies`, `cancers`, `ledger`, `methodology`, `audit_json`, `audit_html`,
`attestation`, `result_json`, and `zip`; the completed response enumerates the
available links in `downloads`.

The versioned immune atlas applies the same primary-plus-ordinal-sensitivity
contract at atlas scale. Gene-cancer BH-FDR and gene-level random-effects
meta-FDR are calculated separately for primary, stage-plus-grade, stage, and
grade families. The availability-selected hierarchy supports retained,
attenuated, emerged, and direction-change summaries, but mixed selected
families are never meta-analyzed.

Immune-screen download kinds are `genes`, `cohorts`, `terms`, `results`,
`panel`, `manifest`, and `methodology`. Atlas v2 additionally exposes
`gene_models`, `cohort_models`, `term_models`, `sensitivity`, `audit`,
`family_summary`, `raw_results`, and `zip`.

All paths in these tables are relative to the REST v1 base address. The live
OpenAPI document is authoritative for request and response schemas.

## Command-line client

The dependency-free Python client at `scripts/tcga_trace_cli.py` consumes this
same v1 and OpenAPI contract. It supports discovery, established asynchronous
compute families, persistent-job polling, recursive batch downloads, and
family-aware verification of retained ZIP bundles.

```bash
python3 scripts/tcga_trace_cli.py contract-check
python3 scripts/tcga_trace_cli.py run analysis request.json \
  --artifacts zip --download-dir results/run-1 --verify
```

See [the complete CLI guide](CLI.md). The integrity verifier checks each
hash-based audit contract. To verify server origin, download the receipt and
its declared HTTPS public key and run:

```bash
python3 scripts/verify_server_attestation.py \
  attestation_receipt.json audit_report.json \
  --key public-key.json
```

## Errors

API v1 errors have one stable envelope:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Check the following request settings: custom percentile: Input should be greater than or equal to 1.",
    "details": {
      "errors": [
        {
          "loc": ["body", "custom_percentile"],
          "msg": "Input should be greater than or equal to 1"
        }
      ]
    },
    "request_id": "4ea1..."
  }
}
```

Validation messages identify the affected setting without echoing its submitted
value. Machine clients should use `details.errors` for field-level handling.
Send `X-Request-ID` to correlate a request with your logs; otherwise the server
generates one. Respect `Retry-After` on `429` and `503` responses. Rate limits
are bound to the proxy-verified network address, so researchers sharing an
institutional network may share the same quota. `HOURLY_LIMIT` means that the
rolling one-hour quota for that analysis family was reached; its
`Retry-After` value is the calculated time until a submission ages out of the
window, not a new full-hour delay. `CLIENT_ACTIVE_LIMIT` means that the network
already has five jobs queued or running, and `QUEUE_FULL` means global service
capacity is temporarily full. Their fixed `Retry-After` values are resubmission
hints, not predictions of when a particular accepted or active job will
finish.

## Public beta limits and retention

- Two analyses execute concurrently across the deployment.
- At most 50 jobs can be active across `queued` and `running` states together;
  this is not 50 waiting jobs plus the two running slots.
- At most five jobs can be active per network address.
- Single, combined, signature-panel and GSEA jobs: 25 submissions per kind and
  network address per rolling hour.
- Expression Comparison: 1,000 submissions per network address per rolling
  hour. The separate limit of five active jobs per network still applies.
- Batch jobs: two submissions per network address per rolling hour, up to 25 analyses each.
- Robustness jobs (`multiverse` API family): one submission per network address per rolling hour, up to 72
  specifications.
- Pan-cancer jobs: two submissions per network address per rolling hour.
- Exploratory session exports: five submissions per network address per rolling hour, with up
  to 200 selected events each.
- Public generated artifacts are retained for 90 days. Private results,
  including exploratory session reports, use the 24-hour private retention
  window and are deleted with their source dataset. Active jobs protect their
  private inputs from expiry until they finish.
- Re-submitting an expired request regenerates its artifacts.

Each accepted submission that requires execution counts towards its rolling
hourly limit, including retries of failed jobs. Returning an identical queued,
running or retained completed job does not consume another submission. These
rules apply equally to REST and MCP. A superseded worker attempt cannot change
the current job's status, result or heartbeat.

The reverse proxy also applies a short-burst request limit. Poll every two
seconds or more slowly; aggressive polling does not make a job finish sooner.
The API exposes `queued` and `running` separately and records `started_at` only
after a worker claims the job. It does not publish an expected wait-time
estimate for accepted jobs.

## Connect ChatGPT

The MCP endpoint uses Streamable HTTP and does not require OAuth in the public
beta.

1. Enable Developer mode in ChatGPT's connector/app settings.
2. Create a custom app or connector from a remote MCP server.
3. Enter `https://apps.cienciavida.org/tcga_explorer/mcp`.
4. Select no authentication.
5. Review the discovered tools, then enable the connector for a conversation.

Workspace administrators can restrict custom connectors, so the exact controls
available depend on the ChatGPT plan and workspace policy.

## Connect Claude

1. Open Claude's connector settings.
2. Add a custom remote connector.
3. Enter `https://apps.cienciavida.org/tcga_explorer/mcp`.
4. Complete the connection with no authentication.
5. Enable TRACE Explorer in the conversation and ask Claude to list
   cohorts or curated datasets before starting an analysis.

Availability of custom connectors depends on the Claude plan and organization
policy.

## MCP tool catalog

Discovery tools:

- `trace_list_tcga_cohorts`
- `trace_list_cancer_types`
- `trace_list_datasets`
- `trace_list_dataset_candidates`
- `trace_get_dataset`
- `trace_get_dataset_endpoints`
- `trace_list_dataset_expression_layers`
- `trace_resolve_dataset_gene`
- `trace_search_dataset_genes`
- `trace_get_tcga_dataset_summary`
- `trace_list_survival_endpoints`
- `trace_get_tcga_cohort_endpoints`
- `trace_list_expression_scales`
- `trace_list_gsea_collections`
- `trace_get_tcga_filter_options`
- `trace_get_dataset_filter_options`
- `trace_search_tcga_genes`
- `trace_resolve_tcga_gene`

`trace_list_tcga_cohorts` is retained as a backwards-compatible tool name. Its
response now includes TCGA cohorts and registered external-only cohorts; clients
must read each row's `status` and must not infer TCGA membership from this tool
name. Dataset-specific tools remain authoritative for external releases.

Compute and result tools:

- `trace_run_survival_analysis`
- `trace_run_combined_analysis`
- `trace_run_signature_panel`
- `trace_run_gsea_analysis`
- `trace_run_expression_comparison`
- `trace_run_batch_analysis`
- `trace_run_robustness_analysis`
- `trace_run_pancancer_analysis`
- `trace_preflight_hierarchical_pancancer`
- `trace_run_hierarchical_pancancer_analysis`
- `trace_get_job`
- `trace_get_analysis`
- `trace_list_immune_screens`
- `trace_get_immune_screen`

`trace_preflight_hierarchical_pancancer` returns a synchronous, bounded
eligibility ledger with explicit `total`, `returned` and `truncated` fields.
When it is truncated, review the complete REST preflight before hierarchical
synthesis. Other compute tools return a job; the model should call
`trace_get_job` until it finishes and
preserve warnings, endpoint provenance, patient/event counts, diagnostics,
heterogeneity and multiple-testing context when explaining a result.
For curated external and authorized private `user-*` datasets, use
`trace_get_dataset_endpoints`, `trace_list_dataset_expression_layers`,
`trace_get_dataset_filter_options` and `trace_resolve_dataset_gene` before
constructing a compute request. Together they expose the release-specific
endpoint, expression-layer, grouping/filter and gene-resolution contracts used
by the analysis tools.

For TCGA, call `trace_get_tcga_filter_options` before compute. Its
`sample_populations` field reports the allowed tissue populations, TCGA sample
codes, patient/sample counts and the current population-contract version. Pass
the selected ID as `filters.sample_population` in every compute request.
`TCGA-SKCM` requires an explicit choice between `primary_solid` and
`metastatic`; TRACE does not pool them or fall back to normal/control tissue.
`TCGA-LAML` defaults to `primary_blood`. Tissue origin, stage/metastatic status
and prior-treatment metadata remain independent clinical dimensions, and an
unknown treatment value must not be interpreted as treatment-naive. Clinical
filter levels and ranges are calculated inside the selected molecular
population. If barcode sample code and recorded sample type disagree, the
sample is excluded and `sample_population_metadata_conflicts` reports it.

A private dataset must first be uploaded through the web app or multipart REST
endpoint. Configure `X-TRACE-Dataset-Token` (or a Bearer token) on the MCP
transport before passing its dataset ID to
`trace_get_dataset`, `trace_get_dataset_endpoints`,
`trace_list_dataset_expression_layers`, `trace_get_dataset_filter_options`,
`trace_search_dataset_genes`, `trace_resolve_dataset_gene` and supported
compute requests. Upload creation,
manual deletion and exploratory-session export are deliberately not MCP tools;
use web/REST for those stateful operations. MCP responses are compact and link
to complete REST results and downloadable artifacts.

Two read-only resources are also exposed:

- `trace-explorer://dataset/version`
- `trace-explorer://methods`

## Citation and responsible use

When using TCGA clinical endpoints, cite the TCGA Pan-Cancer Clinical Data
Resource:

> Liu J, et al. An Integrated TCGA Pan-Cancer Clinical Data Resource to Drive
> High-Quality Survival Outcome Analytics. *Cell*. 2018;173:400-416.e11.
> doi:10.1016/j.cell.2018.02.052.

Also cite the relevant GDC/TCGA data release and record the pipeline version,
data dates, request payload, analysis ID, warnings, and audit checksum supplied
by TRACE Explorer.

Only the documentation resources remain reachable below the legacy `/api/*`
prefix. Integrations must use `/api/v1/*`.
