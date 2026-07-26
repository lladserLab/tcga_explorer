# TCGA-TRACE Command-Line Client

`scripts/tcga_trace_cli.py` is a dependency-free Python client for the stable
TCGA-TRACE REST API v1. It checks the live OpenAPI contract, submits persistent
jobs, polls terminal status, downloads retained artifacts, and verifies local
bundles without importing the web application or backend.

Python 3.10 or newer is recommended. No third-party packages are required.

## Quick start

```bash
python3 scripts/tcga_trace_cli.py health
python3 scripts/tcga_trace_cli.py cohorts
python3 scripts/tcga_trace_cli.py genes TCGA-LIHC CDC --limit 10
python3 scripts/tcga_trace_cli.py contract-check
```

The production API is the default. Set another deployment root or API base
with `--base-url` or `TCGA_TRACE_API_URL`:

```bash
export TCGA_TRACE_API_URL=http://localhost:3000/tcga_explorer/
python3 scripts/tcga_trace_cli.py health
```

## Run an analysis

Store an API request in JSON:

```json
{
  "cohort": "TCGA-LIHC",
  "gene_symbol": "CDC20",
  "endpoint": "OS",
  "expression_scale": "log2_tpm",
  "cutpoint_method": "median",
  "adjustment_covariates": ["age_at_index"]
}
```

Submit and return immediately:

```bash
python3 scripts/tcga_trace_cli.py submit analysis request.json
```

Submit, poll, download the reproducibility bundle, and verify it:

```bash
python3 scripts/tcga_trace_cli.py run analysis request.json \
  --artifacts zip \
  --download-dir results/cdc20-lihc \
  --verify
```

`run` checks that the live OpenAPI document exposes the expected operation
IDs before submission. Use `--skip-contract-check` only for a known-compatible
development deployment.

## Compute families

The same command handles every public compute family:

| CLI family | REST operation | Request body |
| --- | --- | --- |
| `analysis` | `POST /analyses` | One gene or one signature |
| `combined` | `POST /analyses/combined` | Two independent signatures |
| `batch` | `POST /analyses/batch` | Up to 25 analysis requests |
| `multiverse` | `POST /analyses/multiverse` | Declared endpoint x scoring x cutpoint grid |
| `pancancer` | `POST /pancancer/survival` | Continuous cross-cohort scan |
| `session` | `POST /analyses/sessions/export` | Selected terminal job references and browser annotations |

Examples:

```bash
python3 scripts/tcga_trace_cli.py run combined combined.json --verify
python3 scripts/tcga_trace_cli.py run batch batch.json --verify
python3 scripts/tcga_trace_cli.py run multiverse multiverse.json --verify
python3 scripts/tcga_trace_cli.py run pancancer pancancer.json --verify
python3 scripts/tcga_trace_cli.py run session session-export.json --verify
```

When `--verify` is used without `--artifacts`, the CLI downloads each result
ZIP into `tcga-trace-JOB_ID/`. Batch results are traversed recursively, so each
completed child analysis bundle is retained and checked.

## Resume and download

Retrieve a persistent job:

```bash
python3 scripts/tcga_trace_cli.py job JOB_ID
python3 scripts/tcga_trace_cli.py job JOB_ID --wait
```

Download artifacts from an already completed job:

```bash
python3 scripts/tcga_trace_cli.py download JOB_ID \
  --download-dir results/JOB_ID \
  --artifacts zip \
  --verify
```

Use `--artifacts all` to retain every link exposed in the result. A
`tcga-trace-download-manifest.json` records URL, byte count, SHA-256, logical
result, and CLI version for every downloaded file.

## Local verification

Verify a prior download directory, ZIP, or unpacked audit package:

```bash
python3 scripts/tcga_trace_cli.py verify results/JOB_ID
python3 scripts/tcga_trace_cli.py verify analysis.zip
python3 scripts/tcga_trace_cli.py verify unpacked-analysis/
```

Verification is family-aware:

- Analysis and combined bundles: patient-record, continuous-record, scoring,
  reproducibility, artifact, and reproduction-capsule hashes.
- Multiverse bundles: request hash, declared-family hash, session identity,
  and child count.
- Pan-cancer bundles: reproducibility hash and artifact checksums.
- Exploratory session bundles: selected-request hash, export-defined family
  hash, report identity, and source-job count.
- All downloaded files: the local download-manifest byte counts and SHA-256
  values.

The checks detect accidental drift, corruption, incomplete transfer, and
unsafe ZIP members. Server origin is a separate check. Every newly generated
analysis, multiverse, pan-cancer, and exploratory-session bundle includes
`attestation_receipt.json`. Retrieve the receipt's exact public key through its
declared HTTPS URL, then verify both the Ed25519 signature and audit bytes:

```bash
curl -sS \
  https://apps.cienciavida.org/tcga_explorer/api/v1/attestation/keys/KEY_ID \
  > public-key.json

python3 scripts/verify_server_attestation.py \
  attestation_receipt.json audit_report.json \
  --key public-key.json
```

The receipt proves that the holder of the published server key signed that
exact audit report. It does not prove scientific correctness, prevent the
server from signing another report, or provide an append-only timestamp.

## Discovery commands

```text
index
health
cohorts
endpoints
expression-scales
cohort-endpoints COHORT
filters COHORT
genes COHORT [QUERY]
resolve COHORT QUERY
openapi
contract-check
```

Responses are JSON on stdout. Progress and structured errors use stderr.
Use `--output FILE` for an atomic analysis record and `--compact` for
single-line JSON.

## Exit codes

| Code | Meaning |
| --- | --- |
| `0` | Request or verification completed successfully |
| `2` | CLI arguments, input JSON, or local configuration failed |
| `3` | Network, HTTP, or API-contract failure |
| `4` | Compute job failed, expired, or was not complete |
| `5` | Local bundle verification failed |
| `6` | Job polling exceeded `--wait-timeout` |

The API remains the authoritative request schema. Inspect
`/api/openapi.json`, Swagger, or [the API guide](API.md) when constructing new
request JSON.
