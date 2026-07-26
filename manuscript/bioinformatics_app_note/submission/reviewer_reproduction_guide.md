# Reviewer Reproduction Guide

Status date: 2026-07-25.

This guide describes how to reproduce the TCGA-TRACE Application Note
artifacts from a reviewer-accessible checkout.

For a shorter interface-oriented tour of the running web app, see
`manuscript/bioinformatics_app_note/submission/reviewer_walkthrough.md`.

The public web instance is available at:

```text
https://apps.cienciavida.org/tcga_explorer/
https://apps.cienciavida.org/tcga_explorer/api/v1/health
```

## 1. Required Local Inputs

TCGA-TRACE is Dockerized, but it expects a local TCGA RNA-seq data snapshot
mounted from the sibling directory:

```text
../TCGA
```

TCGA-CDR endpoints are enabled when the official clinical file is available at:

```text
clinical/TCGA-CDR-SupplementalTableS1.xlsx
```

The repository tracks compact benchmark summaries and API responses. Full
patient-level run exports are generated locally by the app and are not tracked
in git.

If the reviewer starts from an empty machine, the application updater can
materialize public GDC STAR-count files into the mounted `../TCGA` directory:

```sh
mkdir -p ../TCGA
docker compose run --rm updater apply --source tcga_rna --max-workers 10
docker compose run --rm updater apply --source tcga_cdr
```

This is a large download. For exact review of the submitted benchmark snapshot,
compare the resulting files with
`docs/publication/benchmark/data_snapshot_manifest.json`; the submitted
repository tracks compact benchmark outputs but does not redistribute full TCGA
expression matrices.

## 2. Start the Application

From the repository root:

```sh
docker compose up -d --build
```

Open:

```text
http://localhost:3000/tcga_explorer/
```

Health and API documentation:

```text
http://localhost:3000/tcga_explorer/api/v1/health
http://localhost:3000/tcga_explorer/api/docs
```

The first startup may take tens of minutes if expression caches under
`derived/` must be rebuilt.

## 3. Reproduce Manuscript PDFs

The host does not need a local LaTeX installation:

```sh
make -C manuscript/bioinformatics_app_note clean all
```

Expected outputs:

```text
manuscript/bioinformatics_app_note/build/tcga-trace-bioinformatics-application-note.pdf
manuscript/bioinformatics_app_note/build/tcga-trace-bioinformatics-supplement.pdf
```

## 4. Reproduce Benchmark Tables

With the app running at `http://localhost:3000/tcga_explorer`, run:

```sh
scripts/publication/run_single_gene_benchmark_suite.py
scripts/publication/run_feature_benchmarks.py
scripts/publication/run_reproducibility_benchmark.py
scripts/publication/run_clean_reproduction_benchmark.py --check-only
```

Expected aggregate outputs:

```text
docs/publication/benchmark/single_gene_benchmark_overview.md
docs/publication/benchmark/feature_benchmarks/feature_benchmark_summary.md
docs/publication/benchmark/feature_benchmarks/feature_diagnostic_summary.md
docs/publication/benchmark/feature_benchmarks/signature_definitions.md
manuscript/bioinformatics_app_note/tables/single_gene_benchmark_overview.tex
manuscript/bioinformatics_app_note/tables/single_gene_benchmark_full_overview.tex
manuscript/bioinformatics_app_note/tables/feature_benchmark_summary.tex
manuscript/bioinformatics_app_note/tables/feature_benchmark_diagnostic_summary.tex
manuscript/bioinformatics_app_note/tables/feature_signature_definitions.tex
docs/publication/benchmark/reproducibility_benchmark/summary.md
manuscript/bioinformatics_app_note/tables/reproducibility_benchmark.tex
```

The single-gene suite runs 44 analyses: 11 marker-endpoint scenarios crossed
with four nonredundant two-group cutpoint methods. The feature suite runs three
literature-anchored main examples and preserves three earlier diagnostic
examples.

Maxstat is treated as an optimized exploratory cutpoint. Its corrected
maximally selected rank statistic p-value is reported when available. The
downstream grouped HR, confidence interval and RMST comparison remain
post-selection summaries, not unqualified confirmatory inference.

To reproduce the SKCM primary/metastatic sample-rule sensitivity checks:

```sh
scripts/publication/run_skcm_sample_rule_sensitivity.py
scripts/publication/run_skcm_sample_rule_sensitivity.py --gene TMEM176B
```

Expected sample-rule outputs:

```text
docs/publication/benchmark/skcm_sample_rule_sensitivity/README.md
docs/publication/benchmark/skcm_tmem176b_sample_rule_sensitivity/README.md
manuscript/bioinformatics_app_note/tables/skcm_sample_rule_sensitivity.tex
manuscript/bioinformatics_app_note/tables/skcm_tmem176b_sample_rule_sensitivity.tex
```

To export the local data snapshot manifest used by the app:

```sh
scripts/publication/export_data_snapshot_manifest.py --hash-count-matrices
```

The current manifest records 33 cohorts with zero missing count-matrix hashes.
If the RNA snapshot was created by the application updater, also preserve
`../TCGA/.sync/manifests/tcga_rna_current.json` with the submitted release.

Completed local analysis bundles can be verified with:

```sh
scripts/publication/verify_reproducibility_bundle.py artifacts/<analysis_id>
scripts/publication/verify_reproducibility_bundle.py \
  --rerun \
  --docker-compose-service backend \
  artifacts/<analysis_id>
```

The three-class executable reconstruction benchmark is in
`docs/publication/benchmark/reproducibility_benchmark/`. It verifies one
single-gene, one weighted-signature and one crossed-signature bundle, including
score reconstruction, deterministic re-execution with each bundle's
checksummed frozen R engine and three targeted mutation checks.

Each frozen bundle also contains a standalone R capsule. To rebuild its pinned
environment and reproduce all three representative analyses without network,
application source, TCGA matrices or a database:

```sh
scripts/publication/run_clean_reproduction_benchmark.py \
  --build \
  --platform native
```

Expected evidence:

```text
docs/publication/benchmark/clean_container_reproduction/summary.md
docs/publication/benchmark/clean_container_reproduction/benchmark_results.raw.json
docs/publication/benchmark/clean_container_reproduction/manifest.json
```

The checked-in record contains native arm64 and locally emulated amd64 results.
The CI workflow repeats the native contract on a GitHub-hosted Linux/amd64
runner and uploads its evidence as a workflow artifact.

The statistical calibration benchmark is in
`docs/publication/benchmark/statistical_calibration/`. It stores the
prespecified design, 2,000 observed-cohort permutations, 2,000 known-truth
simulations per scenario, replicate-level metrics and source/output hashes.
Verify the frozen result without rerunning the 10,000 datasets:

```sh
scripts/publication/run_statistical_calibration.py --check-only
```

The repository also includes `.github/workflows/ci.yml` for checks that do not
require local TCGA data: backend Docker build plus unit tests,
publication-script syntax/tests, frontend Docker build and independent
clean-capsule reproduction. The full publication gate below remains local
because it verifies the submitted data snapshot and full run bundle.

## 5. Reproduce Validation Checks

Run the full check. The default form reports owner metadata blockers without
failing the technical checks; after final owner edits, use
`--strict-owner-metadata`.

```sh
scripts/publication/pre_submission_check.sh
```

Equivalent expanded commands:

```sh
python3 -m py_compile \
  scripts/publication/apply_submission_metadata.py \
  scripts/publication/build_submission_archive.py \
  scripts/publication/capture_reviewer_screenshots.py \
  scripts/publication/check_submission_artifacts.py \
  scripts/publication/check_submission_metadata.py \
  scripts/publication/finalize_submission_package.py \
  scripts/publication/run_cutpoint_benchmark.py \
  scripts/publication/run_single_gene_benchmark_suite.py \
  scripts/publication/run_feature_benchmarks.py \
  scripts/publication/run_reproducibility_benchmark.py \
  scripts/publication/run_statistical_calibration.py \
  scripts/publication/run_skcm_sample_rule_sensitivity.py \
  scripts/publication/export_data_snapshot_manifest.py \
  scripts/publication/verify_submission_archive.py \
  scripts/publication/verify_reproducibility_bundle.py \
  scripts/publication/write_license_template.py

scripts/publication/check_submission_metadata.py

docker compose run --rm --no-deps \
  -v "$PWD/backend/tests:/app/tests:ro" \
  backend pytest -q /app/tests

docker compose run --rm --no-deps \
  -v "$PWD/scripts/publication:/app/publication:ro" \
  backend pytest -q /app/publication/tests

python3 -m py_compile scripts/tcga_trace_cli.py
docker compose run --rm --no-deps \
  -v "$PWD:/workspace:ro" \
  -w /workspace \
  backend pytest -q -p no:cacheprovider scripts/tests

docker build -f frontend/Dockerfile -t tcga-trace-frontend-check .
manifest_tmp="$(mktemp)"
trap 'rm -f "$manifest_tmp"' EXIT
scripts/publication/export_data_snapshot_manifest.py --hash-count-matrices --output "$manifest_tmp"
python3 - "$manifest_tmp" docs/publication/benchmark/data_snapshot_manifest.json <<'PY'
import json
import sys
from pathlib import Path

generated = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
tracked = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
assert generated["manifest_hash"] == tracked["manifest_hash"]
print(f"Data snapshot manifest hash OK: {tracked['manifest_hash']}")
PY
scripts/publication/run_reproducibility_benchmark.py
scripts/publication/run_statistical_calibration.py --check-only

python3 - docs/publication/benchmark <<'PY'
import csv
import math
import sys
from pathlib import Path

root = Path(sys.argv[1])
missing = []
for path in sorted(root.glob("*_cutpoint_benchmark/summary.csv")):
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row.get("method") != "maxstat":
                continue
            try:
                value = float(row.get("maxstat_corrected_p_value") or "nan")
            except ValueError:
                value = math.nan
            if not math.isfinite(value) or row.get("maxstat_corrected_p_status") != "completed":
                missing.append(str(path))
if missing:
    raise SystemExit("Missing completed maxstat corrected p-values in: " + ", ".join(missing))
print("Maxstat corrected p-values OK")
PY

make -C manuscript/bioinformatics_app_note clean all
docker run --rm \
  -e LC_ALL=C \
  -e LANG=C \
  -v "$PWD/manuscript/bioinformatics_app_note":/work \
  -w /work \
  texlive/texlive@sha256:1a1b8588cd73ac33fe1d7722c4065b3e6eaa3f3a20fb54d2934e42310264d134 \
  texcount -inc -brief main.tex supplementary.tex
scripts/publication/check_submission_artifacts.py
archive_tmp="$(mktemp)"
scripts/publication/build_submission_archive.py --output "$archive_tmp" >/dev/null
scripts/publication/verify_submission_archive.py "$archive_tmp"
git diff --check
```

Current expected backend test result:

```text
138 passed
```

Current expected publication-script test result:

```text
125 passed
```

Current expected standalone-script test result:

```text
15 passed
```

This comprises 14 CLI tests across six compute families and one independent
server-attestation verifier test.

The CLI can also verify a retained public analysis without importing the
backend:

```sh
python3 scripts/tcga_trace_cli.py run analysis request.json \
  --artifacts zip --download-dir reviewer-cli-run --verify
```

## 6. Reviewer-Facing Claims to Check

- TCGA-TRACE does not claim novelty for Kaplan-Meier estimation,
  two-predictor survival interaction, gene-set survival or PH testing.
- The stated gap is the executable reconstruction workflow: endpoint and
  sample-selection provenance, exact de-identified participant records,
  expression components and source identifiers, score reconstruction, software
  versions, result hashes, RMST and cutpoint sensitivity.
- The main comparator prior art explicitly includes GEPIA2, KM Plotter,
  cSurvival, DoSurvive, PESSA, UALCAN, TIMER2.0 and SurvExpress.
- Benchmark summaries keep BH, Cox, RMST, marker-term PH and global PH separate;
  they do not convert correlated summaries and assumption diagnostics into a
  pass/fail score.
