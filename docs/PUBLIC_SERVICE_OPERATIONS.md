# TRACE Explorer public-service operations

This document separates enforced limits from measured observations. It is an
operational record for the paper release, not a service-level agreement.

## Private-upload limits

The upload validator applies all of the following ceilings independently:

| Boundary | Enforced value |
| --- | ---: |
| Expression file | 100 MiB |
| Patient-metadata file | 10 MiB |
| Samples | 5,000 |
| Genes | 60,000 |
| Matrix cells | 50,000,000 |
| Active private datasets per network | 3 |

The sample and gene ceilings are not jointly attainable. After identifiers are
parsed, the validator computes `genes × samples`, including cells represented
as missing, and rejects the upload when that product exceeds 50 million. A
5,000-sample matrix can therefore contain at most 10,000 genes, whereas a
60,000-gene matrix can contain at most 833 samples. A 5,000 × 60,000 matrix
contains 300 million cells and is rejected.

Original uploaded files are deleted after successful normalization. The
normalized private dataset has an initial 24-hour lifetime. Submitting an
accepted queued or running job extends the input lease by one additional
24-hour window. Private results expire with the private-data window; public
analysis artifacts are retained for 90 days. A user can delete a private
dataset and its associated jobs and artifacts before expiry.

Code authority: `backend/app/config.py`, `backend/app/user_datasets.py` and
`backend/app/jobs.py`.

## Queue states and admission

`queued` and `running` are distinct server states:

- `queued` means that the request has been accepted and is waiting for a
  worker;
- `running` means that a worker has claimed the job and recorded
  `started_at`; and
- `completed`, `failed` and `expired` are terminal states.

The configured global concurrency is two jobs. The configured capacity of 50
counts `queued` and `running` jobs together; it is not 50 waiting jobs plus two
running jobs. When both worker slots are occupied, no more than 48 additional
jobs can be waiting. The per-network active limit of five also counts both
states. Accepted jobs are claimed in `created_at`, then job-ID order.

The public API reports `created_at`, `started_at` and `completed_at`, allowing
queue wait and execution time to be calculated separately. It does not predict
an expected queue wait. A `Retry-After` header accompanies a rejected
rate-limited or full-queue request; it must not be interpreted as the expected
wait of an already accepted job. Clients should poll every two seconds or more
slowly.

The module-level browser busy state spans submission, queueing and execution.
Only the returned job `status` establishes whether server-side computation has
started.

## Current public quotas

The limits below are per proxy-resolved network address and use a rolling
one-hour window:

| Job family | Submissions per hour |
| --- | ---: |
| Single survival, two-signature, signature-panel or GSEA, per kind | 25 |
| Expression Comparison | 1,000 |
| Batch | 2 |
| Robustness | 1 |
| TCGA or hierarchical Pan-cancer | 2 |
| Session/report export | 5 |

A batch contains at most 25 analyses and a Robustness request at most 72
specifications. These hourly limits do not override the global or per-network
active-job limits.

## GSEA computation limit

Correlation-aware pathway testing passes a complete-case `genes × patients` matrix to the
pinned limma CAMERA engine. The enforced ceiling is 100,000,000 entries
(`CAMERA_MAX_MATRIX_ENTRIES`, `backend/app/gsea.py`); it was raised from 50,000,000 on
6 October 2026 because a whole-transcriptome TCGA-BRCA contrast (~60,000 genes × ~1,100
patients) exceeded the previous value. This limit is independent of the private-upload
matrix-cell ceiling above.

## Measured observations

The frozen CAMERA-v2 connected-case GSEA job
`f6301377ac444dd8bd0c82535c2e308c` was created on 26 August 2026. For that
single 4,315-pathway workload, queue wait was 0.23 s, analysis compute time was
216.94 s and server-job wall time was 218.51 s. Matrix preparation took 15.89 s,
descriptive preranked effects 183.42 s and the CAMERA subprocess 17.40 s
(6.672 s in the R engine); these components are nested in the total. The 5,000
gene-set permutations normalize descriptive NES and do not generate inferential
pathway p-values. This is one observation, not a median, tail percentile,
maximum or promise for other cohorts or traffic levels.

TRACE Explorer exposes health checks but has no audited historical uptime
series and no clinical or research-compute SLA.
