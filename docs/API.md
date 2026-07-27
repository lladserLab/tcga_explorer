# TCGA-TRACE Public API and MCP

TCGA-TRACE exposes the current scientific workflows through a public REST API
and a remote Model Context Protocol (MCP) server. Both interfaces use the same
validation, persistent compute queue, cache, and artifact retention policy.

These outputs are for exploratory research. They are not intended for clinical
decision-making, diagnosis, prognosis, or treatment selection.

## Production addresses

| Interface | Address |
| --- | --- |
| Web application | `https://apps.cienciavida.org/tcga_explorer/` |
| REST API v1 | `https://apps.cienciavida.org/tcga_explorer/api/v1/` |
| Swagger UI | `https://apps.cienciavida.org/tcga_explorer/api/docs` |
| ReDoc | `https://apps.cienciavida.org/tcga_explorer/api/redoc` |
| OpenAPI 3 document | `https://apps.cienciavida.org/tcga_explorer/api/openapi.json` |
| Remote MCP | `https://apps.cienciavida.org/tcga_explorer/mcp` |
| Spanish guide | `https://apps.cienciavida.org/tcga_explorer/api/guia` |

`/tcga_explorer` is the stable legacy deployment path for TCGA-TRACE, retained
for existing bookmarks and API clients. It is not an alternate product name.

The public beta does not require an API key. Limits are applied to an anonymous
client identity derived from the proxy-verified IP address or MCP session.

## Data and scientific scope

The API exposes the same public-data capabilities as the web application:

- TCGA cohort, sample, patient, gene, endpoint, and data-source summaries.
- Curated independent bulk RNA-seq releases with source-specific expression
  layers, endpoint definitions, license metadata and immutable manifests.
- OS, PFI, DFI, and DSS endpoint availability and cohort-level QC.
- Single-gene, mean, z-score, and weighted RNA signature survival analyses.
- Cutpoint-independent continuous Cox models, restricted cubic-spline effect
  profiles, proportional-hazards diagnostics, and reproducibility artifacts.
- Secondary Kaplan-Meier, grouped Cox, RMST, and cutpoint-sensitivity outputs.
- For DSS, DFI, and PFI, explicit TCGA-CDR competing-event coding,
  cumulative-incidence functions, Gray tests, and grouped and continuous
  Fine-Gray models alongside the cause-specific outputs.
- Prespecified endpoint-by-scoring-by-cutpoint multiverses with family-specific
  multiplicity correction, complete execution ledgers, and specification
  curves.
- Two-signature grouping and continuous Cox interaction models.
- Bounded comparison batches.
- Continuous pan-cancer Cox scans, BH-FDR, concordance, and meta-analysis.
- Precomputed immune pan-cancer screens.

Public scope contains open TCGA/GDC, TCGA-CDR-derived data and explicitly
licensed external releases. Internal filesystem paths, cache manifests,
synchronization controls and database operations are not part of API v1.
External matrices are downloadable only when the release records redistribution
as allowed.

Patient-level audit artifacts retain exact TCGA participant and sample barcodes
for scientific traceability. These are public research identifiers, but users
must not attempt re-identification or combine them with restricted data.

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
| `GET` | `/cohorts/{cohort_id}/genes` | Search valid genes |
| `GET` | `/cohorts/{cohort_id}/genes/resolve` | Resolve a symbol or supported alias |

### Curated external RNA-seq repository

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/cancer-types` | Coverage ledger for all 33 TCGA cancer types |
| `GET` | `/datasets` | Published independent bulk RNA-seq releases |
| `GET` | `/datasets/{dataset_id}` | Release, source, license, QC, endpoint and expression-layer detail |
| `GET` | `/datasets/{dataset_id}/endpoints` | Release-specific endpoint definitions and QC |
| `GET` | `/datasets/{dataset_id}/expression-layers` | Source units, transforms and scale caveats |
| `GET` | `/datasets/{dataset_id}/filters` | Available curated clinical filters |
| `GET` | `/datasets/{dataset_id}/genes` | Search genes in one pinned expression layer |
| `GET` | `/datasets/{dataset_id}/genes/resolve` | Resolve a gene against one pinned layer |
| `GET` | `/datasets/{dataset_id}/download/{kind}` | Download manifest, QC, license, or licensed matrix/metadata/gene index |

To analyze an external release, retain the matching TCGA code as cancer
taxonomy and pin the dataset, release and expression layer:

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
present. External releases are supported by Survival, Compare and Multiverse;
Pan-cancer remains TCGA-only.

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
| `POST` | `/analyses/batch` | Submit up to 25 analyses |
| `POST` | `/analyses/multiverse` | Submit one declared specification family |
| `POST` | `/analyses/sessions/export` | Export selected browser jobs as one exploratory record |
| `GET` | `/jobs/{job_id}` | Poll any compute job |
| `GET` | `/analyses/{analysis_id}` | Retrieve a completed analysis |
| `GET` | `/analyses/batches/{batch_id}` | Retrieve a completed batch |
| `GET` | `/analyses/multiverses/{session_id}` | Retrieve a completed specification family |
| `GET` | `/analyses/multiverses/{session_id}/download/{kind}` | Download a family artifact |
| `GET` | `/analyses/sessions/{report_id}` | Retrieve an exploratory session record |
| `GET` | `/analyses/sessions/{report_id}/download/{kind}` | Download a session artifact |
| `GET` | `/analyses/{analysis_id}/download/{kind}` | Download an analysis artifact |

Analysis download kinds are `zip`, `continuous_png`, `continuous_svg`,
`continuous_csv`, `png`, `svg`, `cox_png`, `cox_svg`,
`cox_univariable_png`, `cox_univariable_svg`, `cox_multivariable_png`,
`cox_multivariable_svg`,
`cumulative_incidence_png`, `cumulative_incidence_svg`, `csv`, `json`,
`audit_json`, `audit_html`, `attestation`, `txt`, and `methodology`.

Analysis pipeline v6.15 adds
`plot_style.cox_forest.model_layout: "combined" | "separate"`. `combined`
remains the default. `separate` creates an extra univariable forest and an
extra forest containing every completed adjusted multivariable model; a file
is omitted when its model family is not evaluable. Optional
`univariable_plot_title` and `multivariable_plot_title` fields customize those
titles. The original `cox_png` and `cox_svg` remain available for backward
compatibility.

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
Multiverse continuous and grouped CSV exports retain the same fields.

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

Completed analysis responses also include two decision-support fields:

- `notices`: structured messages with `category` (`cohort`, `method`, `model`,
  or `availability`) and `severity` (`info`, `caution`, or `not_evaluable`).
- `diagnostics`: the selected clinical-adjusted model, its family and its
  top-level status (`clean`, `caution`, or `not_evaluable`), together with
  message counts.

Only a diagnostic caution attached to the selected adjusted model produces a
top-level `caution` status. Cohort construction is neutral information, an
unavailable adjusted model is `not_evaluable`, and cautions from auxiliary
models do not contaminate the selected-model status. The original `warnings`
array remains present for backward compatibility; new clients should prefer
`notices` and `diagnostics`.

### Prespecified multiverse

`POST /analyses/multiverse` accepts one cohort, one gene or multi-gene
signature, one or more QC-eligible endpoints, compatible scoring methods, and
one or more cutpoint methods. The full Cartesian grid is frozen before
execution and is limited to 72 specifications.

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

Multiverse download kinds are `svg`, `csv`, `continuous_csv`, `ledger`,
`json`, `audit_json`, `audit_html`, `attestation`, `methodology`, and `zip`.

### Exploratory session history

`POST /analyses/sessions/export` accepts up to 200 selected run events that
reference terminal `job_id` values, plus browser-supplied labels and
timestamps. The server resolves the authoritative requests and results from
its compute-job records. Patient-level records and external-covariate row
values are not embedded.

The report applies BH and Bonferroni separately to unique continuous Cox,
grouped cutpoint, and two-signature interaction hypotheses. Exact duplicate
hypotheses are counted once while repeated run events remain in the ledger.
Prespecified multiverses and pan-cancer scans retain their internal correction
and appear only as managed-family references. This is explicitly a post hoc,
export-defined scope: it does not claim that no other runs occurred and
produces no retained/not-retained verdict.

Session download kinds are `json`, `runs_csv`, `hypotheses_csv`, `ledger`,
`audit_json`, `audit_html`, `attestation`, `methodology`, and `zip`.

### Pan-cancer

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/pancancer/survival` | Submit a pan-cancer scan |
| `GET` | `/pancancer/survival/{scan_id}` | Retrieve a scan |
| `GET` | `/pancancer/survival/{scan_id}/download/csv` | Download scan results |
| `GET` | `/pancancer/survival/{scan_id}/download/{kind}` | Download a reproducibility artifact |
| `GET` | `/pancancer/immune-screens` | List precomputed screens |
| `GET` | `/pancancer/immune-screens/{screen_id}` | Retrieve one screen |
| `GET` | `/pancancer/immune-screens/{screen_id}/download/{kind}` | Download screen data |

Pan-cancer artifact kinds are `patients`, `methodology`, `audit_json`,
`audit_html`, `attestation`, `raw_r_json`, `result_json`, and `zip`. The
dedicated `csv` route returns the cohort-level table.

Pipeline v2.8 reports each cohort's continuous Cox effect per one
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
same v1 and OpenAPI contract. It supports discovery, all six asynchronous
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
    "message": "The request did not match the documented API contract.",
    "details": {},
    "request_id": "4ea1..."
  }
}
```

Send `X-Request-ID` to correlate a request with your logs; otherwise the server
generates one. Respect `Retry-After` on `429` and `503` responses.

## Public beta limits and retention

- Two analyses execute concurrently across the deployment.
- At most 50 jobs can be active in the bounded queue.
- At most five jobs can be active per anonymous client.
- Single and combined jobs: 10 submissions per kind and client per hour.
- Batch jobs: two submissions per client per hour, up to 25 analyses each.
- Multiverse jobs: one submission per client per hour, up to 72
  specifications.
- Pan-cancer jobs: two submissions per client per hour.
- Exploratory session exports: five submissions per client per hour, with up
  to 200 selected events each.
- Generated artifacts are retained for 90 days.
- Re-submitting an expired request regenerates its artifacts.

The reverse proxy also applies a short-burst request limit. Poll every two
seconds or more slowly; aggressive polling does not make a job finish sooner.

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
5. Enable TCGA-TRACE in the conversation and ask Claude to list cohorts before
   starting an analysis.

Availability of custom connectors depends on the Claude plan and organization
policy.

## MCP tool catalog

Discovery tools:

- `tcga_list_cohorts`
- `tcga_get_dataset_summary`
- `tcga_list_survival_endpoints`
- `tcga_get_cohort_endpoints`
- `tcga_list_expression_scales`
- `tcga_get_filter_options`
- `tcga_search_genes`
- `tcga_resolve_gene`

Compute and result tools:

- `tcga_run_survival_analysis`
- `tcga_run_combined_analysis`
- `tcga_run_batch_analysis`
- `tcga_run_pancancer_analysis`
- `tcga_get_job`
- `tcga_get_analysis`
- `tcga_list_immune_screens`
- `tcga_get_immune_screen`

Compute tools return a job. The model should call `tcga_get_job` until the job
finishes and preserve warnings, endpoint provenance, patient/event counts,
diagnostics, and multiple-testing context when explaining a result. MCP
responses are compact and link to complete REST results and downloadable
artifacts.

Two read-only resources are also exposed:

- `tcga-trace://dataset/version`
- `tcga-trace://methods`

## Citation and responsible use

When using TCGA clinical endpoints, cite the TCGA Pan-Cancer Clinical Data
Resource:

> Liu J, et al. An Integrated TCGA Pan-Cancer Clinical Data Resource to Drive
> High-Quality Survival Outcome Analytics. *Cell*. 2018;173:400-416.e11.
> doi:10.1016/j.cell.2018.02.052.

Also cite the relevant GDC/TCGA data release and record the pipeline version,
data dates, request payload, analysis ID, warnings, and audit checksum supplied
by TCGA-TRACE.

The legacy `/api/*` routes remain temporarily available to preserve the web
application's historical contract. New integrations must use `/api/v1/*`.
