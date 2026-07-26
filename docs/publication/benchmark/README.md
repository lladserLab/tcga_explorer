# Publication Benchmarks

This directory stores compact benchmark outputs used to develop the
Bioinformatics Application Note narrative.

## KIRC CA9 Cutpoint Benchmark

Location:

```text
docs/publication/benchmark/kirc_ca9_cutpoint_benchmark/
```

Reproduce from a running local TCGA-TRACE stack:

```sh
scripts/publication/run_cutpoint_benchmark.py
```

The benchmark calls the HTTP API at `http://localhost:3000/tcga_explorer` by
default, runs TCGA-KIRC CA9 overall survival analyses across the two-group
dichotomization methods, computes BH-adjusted log-rank p-values, assembles a
descriptive evidence profile and writes:

- `summary.csv`: compact machine-readable result table;
- `summary.md`: human-readable result table and run hashes;
- `benchmark_metadata.json`: run metadata, endpoint status and health payload;
- `benchmark_results.raw.json`: full batch API response without raw patient rows;
- `manuscript/bioinformatics_app_note/tables/kirc_ca9_cutpoint_benchmark.tex`:
  manuscript-ready LaTeX table.

Full patient-level run bundles remain in local `artifacts/` and are intentionally not
tracked in git.

Maxstat is included as an optimized exploratory cutpoint. The pipeline records
its corrected maximally selected rank statistic p-value with
`maxstat::maxstat.test`, `smethod="LogRank"` and `pmethod="Lau94"`. Grouped HRs,
confidence intervals and RMST comparisons remain post-selection summaries.

## Single-Gene Benchmark Suite

The immutable scenario and endpoint contract is:

```text
docs/publication/benchmark/scenario_registry_v1.json
```

Its human-readable companion is
`docs/publication/scenario_endpoint_registry.md`. The suite validates its exact
IDs, cohorts, markers, endpoints and primary/sensitivity links before running
or rendering. Every per-scenario metadata file records the registry version and
SHA-256.

Run all current single-gene benchmarks:

```sh
scripts/publication/run_single_gene_benchmark_suite.py
```

Cases:

- TCGA-LIHC CDC20 OS;
- TCGA-LUAD BIRC5 OS;
- TCGA-UVM BAP1 DSS;
- TCGA-SKCM TMEM176B OS;
- TCGA-LGG EMP3 OS;
- TCGA-KIRC CA9 OS;
- TCGA-BRCA MKI67 OS;
- TCGA-BRCA MKI67 PFI;
- TCGA-SKCM PDCD1 OS;
- TCGA-LUAD CD274 OS;
- TCGA-LUAD CD274 PFI.

Aggregate outputs:

- `single_gene_benchmark_overview.csv`;
- `single_gene_benchmark_overview.md`;
- `manuscript/bioinformatics_app_note/tables/single_gene_benchmark_overview.tex`;
- `manuscript/bioinformatics_app_note/tables/single_gene_benchmark_full_overview.tex`.

The suite keeps full method-level summaries in each per-case directory and
stores only compact API responses, summaries and hashes in git.
The panel was assembled after exploratory triage and is frozen as a software
stress test, not a prospective biomarker-validation sample. OS is primary
except for UVM BAP1 DSS; BRCA MKI67 PFI and LUAD CD274 PFI are linked endpoint
sensitivities.

The publication suite uses four nonredundant two-group rules per scenario:
maxstat, median, upper quartile and outer quartiles. Every method reports
suite-wide BH q, univariable and prespecified age-adjusted Cox, fixed-horizon
RMST, marker-term PH and global PH separately. Age is modeled continuously per
10 years in the exact complete-case user model; fixed stage, grade and
stage-plus-grade fits remain available as auxiliary sensitivities in each raw
result. These correlated quantities are not combined into a retention rule.
LGG/EMP3 illustrates why: association and RMST summaries are below 0.05 under
all four methods while the marker-term PH diagnostic cautions against
interpreting the HR as constant over time. The remaining scenarios are kept as
sensitivity and provenance demonstrations.

## Reproducibility Bundle Verification

Completed analyses write local bundle directories under `artifacts/<analysis_id>/`.
Verify an existing bundle without rerunning R:

```sh
scripts/publication/verify_reproducibility_bundle.py artifacts/<analysis_id>
```

To perform the reviewer-facing round-trip check from `input.json`:

```sh
scripts/publication/verify_reproducibility_bundle.py --rerun artifacts/<analysis_id>
```

When using the Dockerized backend R environment, run:

```sh
scripts/publication/verify_reproducibility_bundle.py \
  --rerun \
  --docker-compose-service backend \
  artifacts/<analysis_id>
```

This recomputes participant-record, expression-component, score, artifact and
reproducibility hashes. It also reconstructs the analyzed score from the audited
components. With `--rerun`, it re-executes the checksummed `km_analysis.R`
stored in that bundle and compares core
statistical outputs against `audit_report.json`. `--r-script` and
`--container-r-script` are explicit compatibility overrides, not the
reproduction default.

The current audit-reconstruction benchmark is stored in
`docs/publication/benchmark/reproducibility_benchmark/`. It verifies one
single-gene, one weighted-signature and one crossed-signature bundle, including
score reconstruction, deterministic R re-execution and targeted mutation
detection. Regenerate it with:

```sh
scripts/publication/run_reproducibility_benchmark.py
```

Every new two-group analysis export also contains `input.json`, the exact R
engine and helpers, `rerun_analysis.R`, `renv.lock`,
`Dockerfile.reproduce`, instructions and a checksummed capsule manifest. The
runner does not require FastAPI, PostgreSQL or TCGA matrices.

The frozen clean-container benchmark is in
`clean_container_reproduction/`. It rebuilds the pinned environment and runs
all three capsules with no network, a read-only root and capsule, and only
temporary/output storage writable:

```sh
scripts/publication/run_clean_reproduction_benchmark.py \
  --build \
  --platform native

# Verify the checked-in evidence without rebuilding Docker.
scripts/publication/run_clean_reproduction_benchmark.py --check-only
```

Existing checked-in capsules are immutable by default. Both commands validate
each capsule against its own checksummed engine manifest and compare the
reported R package versions semantically with that capsule's `renv.lock`;
local analysis artifacts cannot silently replace frozen inputs or code.
Maintainers may deliberately regenerate all three capsules from matching local
artifacts and the current engine with `--refresh-capsules`, but that operation
also requires review and refreezing of every derived benchmark artifact.

The publication record additionally includes a locally emulated
`linux/amd64` run. GitHub Actions repeats the native contract on an independent
hosted Linux/amd64 runner.

## Server Attestation

Every new analysis, multiverse and pan-cancer audit receives a detached
`attestation_receipt.json`. Its Ed25519 signature binds the exact
`audit_report.json` byte count, SHA-256, schema and recorded reproducibility
hash. Public keys are exposed by the HTTPS API and retained across application
image rebuilds in a separate server volume.

The frozen evidence is stored in:

```text
docs/publication/benchmark/server_attestation/
```

It contains one exact BAP1/UVM DSS audit, its detached receipt, the public key
only, full verification results and a compact summary. Regenerate it from
downloaded artifacts in an environment containing the backend dependencies:

```sh
python3 scripts/publication/run_server_attestation_benchmark.py \
  --audit audit_report.json \
  --receipt attestation_receipt.json \
  --key public_key.json
```

Verify the checked-in evidence without contacting the service:

```sh
scripts/publication/run_server_attestation_benchmark.py --check-only
```

The positive control verifies the exact report. One negative control alters the
report while retaining the original receipt. A second recomputes the altered
report SHA-256 and canonical payload SHA-256 but cannot recompute the Ed25519
signature; verification therefore fails at the cryptographic boundary. This
establishes server origin only when the HTTPS key or archived fingerprint is
trusted. It does not establish scientific correctness, prespecification,
append-only time or protection against server-key compromise.

## Statistical Calibration

The revised evidence profile is calibrated with observed-cohort expression
permutation and known-truth simulation:

```sh
scripts/publication/run_statistical_calibration.py
```

The default publication design uses 2,000 permutations of the frozen
TCGA-LIHC CDC20 continuous population and 2,000 simulated datasets per
scenario at `n=300`. Scenarios are null, linear proportional hazards, delayed
non-proportional hazards and U-shaped nonlinear effects. Every replicate refits
continuous Cox, the spline comparison, marker-term `cox.zph`, fixed-horizon
RMST and four grouped rules: maxstat, median, upper quartile and outer
quartiles. The within-replicate grouped family uses Holm and enters the Lau94
maxstat p-value rather than its selected-group log-rank p-value. Tertiles are
three-group comparisons and a custom percentile would add an arbitrary,
user-defined rule, so neither belongs to the frozen four-rule publication
family.

Outputs are stored in:

```text
docs/publication/benchmark/statistical_calibration/
```

`permutation_replicates.csv` and `simulation_replicates.csv` preserve every
replicate. The raw JSON records source audit hashes, seeds, scenario truth,
software versions and Wilson Monte Carlo intervals. Verify the frozen files
without rerunning the 10,000 datasets:

```sh
scripts/publication/run_statistical_calibration.py --check-only
```

The benchmark calibrates p-value behavior in the stated scenarios. It is not a
biomarker validation and does not define a composite pass/fail rule.

## Runtime and Concurrency

Measure representative workflows through the public asynchronous API:

```sh
scripts/publication/run_runtime_benchmark.py
```

The frozen publication run measures an uncached single analysis, its exact
cached repeat, two concurrent single analyses, a 10-analysis public batch, the
maximum 72-cell multiverse and a 33-cohort pan-cancer request. It records
client wall time, server queue and compute intervals, observed aggregate
backend-plus-worker Docker cgroup memory, hardware, container images, pipeline
versions, data-manifest hash and public queue limits. “Uncached” means an
analysis-result cache miss; it does not mean a fresh operating-system page
cache or data import.

Outputs are stored in:

```text
docs/publication/benchmark/runtime_concurrency/
```

Regenerate summaries from the frozen raw response or validate the complete
record without submitting work:

```sh
scripts/publication/run_runtime_benchmark.py --reuse-raw
scripts/publication/run_runtime_benchmark.py --check-only
```

The one-second memory sampler reports observed cgroup peaks rather than
allocator maxima. Timing values characterize the declared host and snapshot;
they are not cross-platform performance guarantees.

## Browser Compatibility

Run the same functional contract in isolated Chromium, Firefox/Gecko and
WebKit containers:

```sh
scripts/publication/run_browser_compatibility.py
```

The contract checks keyboard-visible focus, reduced-motion behavior, gene
suggestions in Survival and Compare, a completed CDC20/LIHC analysis and audit
download, the four-method Compare publication panel, frozen Paper Examples,
Pan-cancer plots and Dataset Summary outputs. Each engine runs in a separate
container so public batch-rate limits are not shared across browser clients.

Provisional development evidence is stored in:

```text
docs/publication/benchmark/browser_compatibility/
```

Validate the frozen evidence without opening browsers:

```sh
scripts/publication/run_browser_compatibility.py --check-only
```

The submission record must be regenerated from a clean exact-tag checkout
against the deployed HTTPS URL:

```sh
scripts/publication/run_browser_compatibility.py \
  --base-url https://apps.cienciavida.org/tcga_explorer/ \
  --final-release
```

Final mode rejects a dirty worktree, an untagged `HEAD` or a non-HTTPS target.
Playwright WebKit validates the engine contract but remains distinct from a
manual check in an exact Safari product version.

## Data Snapshot Manifest

Export the current local data snapshot manifest:

```sh
scripts/publication/export_data_snapshot_manifest.py
```

The manifest is written to:

```text
docs/publication/benchmark/data_snapshot_manifest.json
```

The current manifest was generated with count-matrix hashes:

```sh
scripts/publication/export_data_snapshot_manifest.py --hash-count-matrices
```

It records 33 cohorts, zero missing count-matrix hashes and stable manifest
hash `f424cf0ce18199ca291b9a396dd89660c654d049cc9bdeff1bbdcf1b8a0ba094`.
The stable hash excludes export timestamps, file mtimes and cache timing fields,
so repeated exports of the same content keep the same hash.
Archive this manifest with the software release. If the RNA snapshot is created
by the application updater, also archive the GDC RNA sync manifest from
`../TCGA/.sync/manifests/tcga_rna_current.json`; this checkout currently pins
the benchmark matrices by final count-matrix hashes and records the RNA updater
sync manifest as missing.

## External Concordance Panel

Run the three marker-cohort comparisons prespecified in
`docs/publication/concordance_validation_plan.md` with:

```sh
python3 scripts/publication/run_external_concordance_panel.py \
  --access-date 2026-07-25
```

The runner downloads official cBioPortal TCGA PanCancer Atlas API responses,
freezes them as gzipped source snapshots, selects one expression- and
OS-complete sample per patient under an explicit TCGA sample-code rule, and
fits a median-split univariable Cox/log-rank comparison in R. Re-render without
network access using `--render-existing`. The panel is a cross-pipeline
software check rather than independent validation because both resources use
TCGA. The earlier manually documented KM Plotter CA9 record remains a
secondary comparison.

## SKCM Sample-Rule Sensitivity

TCGA-SKCM contains both primary and metastatic RNA-seq samples. Run the PDCD1 OS
sample-rule sensitivity checks with:

```sh
scripts/publication/run_skcm_sample_rule_sensitivity.py
```

Run the same sensitivity wrapper for the TMEM176B exploratory SKCM case with:

```sh
scripts/publication/run_skcm_sample_rule_sensitivity.py --gene TMEM176B
```

The wrapper compares all eligible samples, primary tumors only and metastatic
samples only using the same HTTP benchmark machinery.

Current overviews:

```text
docs/publication/benchmark/skcm_sample_rule_sensitivity/README.md
docs/publication/benchmark/skcm_tmem176b_sample_rule_sensitivity/README.md
```

The median-split PDCD1 profile differs across metastatic-only, primary-only and
all-eligible subsets, including loss of adjusted-Cox support in the all-eligible
set. The median-split TMEM176B BH and adjusted-Cox summaries also vary by sample
rule. Treat TCGA-SKCM sample composition as a sensitivity setting rather than a
minor implementation detail.

## Feature Benchmark Suite

Run the current feature-level benchmarks:

```sh
scripts/publication/run_feature_benchmarks.py
```

Cases:

- Main: TCGA-ACC weighted `(BUB1B - PINK1)/2` score, OS, median split;
- Main: TCGA-UVM BAP1 x PRAME marker grouping, DSS, independent median splits
  plus continuous interaction Cox;
- Main: BIRC5 pan-cancer primary continuous Cox/FDR scan plus parallel ordinal
  stage/grade sensitivity, OS;
- Diagnostic: TCGA-KIRC compact hypoxia z-score signature, OS;
- Diagnostic: TCGA-SKCM effector x exhaustion signatures, OS;
- Diagnostic: CA9 pan-cancer primary continuous Cox/FDR scan plus parallel
  ordinal stage/grade sensitivity, OS.

Aggregate outputs:

- `feature_benchmarks/feature_benchmark_summary.csv`;
- `feature_benchmarks/feature_benchmark_summary.md`;
- `feature_benchmarks/feature_diagnostic_summary.csv`;
- `feature_benchmarks/feature_diagnostic_summary.md`;
- `feature_benchmarks/signature_definitions.md`;
- `manuscript/bioinformatics_app_note/tables/feature_benchmark_summary.tex`;
- `manuscript/bioinformatics_app_note/tables/feature_benchmark_diagnostic_summary.tex`;
- `manuscript/bioinformatics_app_note/tables/feature_signature_definitions.tex`.

Current interpretation: the ACC score has a continuous HR per SD of 2.85 and
an age-adjusted p-value of \(5.58\times10^{-7}\), with 14 events per fitted
parameter; it remains an RNA-seq analogue rather than a replication of the
published qRT-PCR threshold. UVM shows global four-group separation without a
significant continuous interaction. Its age-adjusted interaction has 5.2
events per parameter and an unsupported Firth sensitivity (p=0.126). BIRC5 has
18/32 FDR-significant cohort effects and a common-scale REML/HKSJ HR of 1.20
(1.06--1.37), but high heterogeneity (I2=86.1%) and a 95% prediction interval
of 0.64--2.24. CA9 is deliberately included as the counterexample: its
common-scale HR is 1.04 (1.00--1.08), its prediction interval is 0.93--1.16,
and its stage-adjusted family attenuates. Per-SD cohort effects remain
descriptive; mixed endpoints, mixed selected adjustment families and
cohort-standardized z-score signatures are never pooled. These are
literature-anchored workflow examples, not independent biomarker validations.

Run the three-class executable benchmark with:

```sh
scripts/publication/run_reproducibility_benchmark.py
```

It verifies representative single-gene, weighted-signature and
crossed-signature bundles and performs participant, request and expression
mutation checks. The same generated table incorporates the clean-capsule
results and their input/snapshot negative controls, avoiding an additional
supplementary table. Compact results are in `reproducibility_benchmark/` and
`clean_container_reproduction/`.

## ImmPort Pan-Cancer Atlas v2.1

The full immune atlas is a separate versioned scale test using the same primary
and ordinal-sensitivity model definitions as the BIRC5 and CA9 examples. It is
not part of the three-bundle executable reconstruction benchmark. Its compact
publication record is stored in:

```text
docs/publication/benchmark/immune_pancancer_atlas_v2_1/
```

Regenerate the compact JSON, CSV and LaTeX table from the frozen local atlas:

```sh
scripts/publication/export_immune_atlas_benchmark.py
```

The atlas freezes 3,118 unique ImmPort genes, 153 immune terms and 32
strict-OS expression matrices. It attempted 399,104 model rows and completed
96,779 primary gene-cancer models. Global gene-cancer FDR and gene-level
meta-FDR are recomputed independently for primary, stage+grade, stage and grade
families. An availability-selected adjusted summary uses stage+grade, then
stage, then grade based only on evaluability and is never meta-analyzed across
mixed families.

The compact record preserves the exact 12,234-primary-hit decomposition,
model-family counts, selected-adjustment counts, interpretation notes, software
versions and audit hash. The full 626 MB model-level output remains under local
versioned artifacts and is not copied into the review archive. Consecutive
post-processing runs produced audit hash
`4d942e93715ec953f0501b13a818d2f19e34f21d851367057924f0af3c2d0252`.

## RMST Tau Sensitivity Evidence

Two-group analyses store RMST at a cutpoint-independent primary tau and at 0.75
and 0.90 of that tau in the raw benchmark JSON. Tau is defined without group
labels as the smaller of five years and the 75th percentile of observed
endpoint times in the unstratified, expression-complete eligible cohort. Both
groups must support that horizon and retain at least five participants at risk.
