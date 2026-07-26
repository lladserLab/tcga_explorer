# TCGA-TRACE Reviewer Quickstart

Status date: 2026-07-25.

This file is the short entry point for reviewers. The complete reproduction
guide is:

```text
manuscript/bioinformatics_app_note/submission/reviewer_reproduction_guide.md
```

## Fast Checks Without TCGA Data

The repository includes a GitHub Actions workflow at `.github/workflows/ci.yml`
for checks that do not require the local TCGA data snapshot:

```sh
docker compose build backend
docker compose run --rm --no-deps \
  -v "$PWD/backend/tests:/app/tests:ro" \
  backend pytest -q /app/tests
docker compose run --rm --no-deps \
  -v "$PWD/scripts/publication:/app/publication:ro" \
  backend python3 - <<'PY'
from pathlib import Path

count = 0
for path in sorted(Path("/app/publication").glob("*.py")):
    compile(path.read_text(encoding="utf-8"), str(path), "exec")
    count += 1
print(f"Publication script syntax OK: {count} files")
PY
docker compose run --rm --no-deps \
  -v "$PWD/scripts/publication:/app/publication:ro" \
  backend pytest -q /app/publication/tests
python3 -m py_compile scripts/tcga_trace_cli.py
docker compose run --rm --no-deps \
  -v "$PWD:/workspace:ro" \
  -w /workspace \
  backend pytest -q -p no:cacheprovider scripts/tests
docker build -f frontend/Dockerfile -t tcga-trace-frontend-check .
```

Expected test results:

```text
138 passed
Publication script syntax OK: 25 files
125 passed
15 passed
```

## Run The Web Application

The public TCGA-TRACE instance is available at:

```text
https://apps.cienciavida.org/tcga_explorer/
https://apps.cienciavida.org/tcga_explorer/api/v1/health
```

For local reproduction, TCGA-TRACE can also be run with Docker Compose.
TCGA-TRACE expects a TCGA RNA-seq snapshot mounted at `../TCGA`. TCGA-CDR
endpoints are enabled when the official clinical file is present at:

```text
clinical/TCGA-CDR-SupplementalTableS1.xlsx
```

Start the Dockerized app:

```sh
docker compose up -d --build
```

Open:

```text
http://localhost:3000/tcga_explorer/
http://localhost:3000/tcga_explorer/api/v1/health
http://localhost:3000/tcga_explorer/api/docs
```

If no local TCGA snapshot is available, public GDC STAR-count files can be
materialized with the updater. This is a large download:

```sh
mkdir -p ../TCGA
docker compose run --rm updater apply --source tcga_rna --max-workers 10
docker compose run --rm updater apply --source tcga_cdr
```

## Full Local Publication Gate

The full local pre-submission gate is:

```sh
scripts/publication/pre_submission_check.sh
```

It compiles publication scripts, runs Dockerized backend and publication-script
tests, builds the frontend image, reports unresolved owner metadata, verifies
the tracked data-snapshot manifest hash, re-runs the three-class executable
audit reconstruction benchmark, rebuilds manuscript PDFs,
checks the frozen 10,000-run statistical calibration, reports `texcount`,
verifies the submission artifact set with SHA-256
checksums, checks the compact archive builder, and runs `git diff --check`.

For the final journal-upload pass, after authors, license and the
version-specific Zenodo DOI have been inserted, run:

```sh
scripts/publication/finalize_submission_package.py path/to/owner_metadata.json --license-source path/to/LICENSE
```

The finalizer writes the final archive and a neighboring `*.summary.json` file
with the final archive and PDF SHA-256 values. In `--dry-run` mode it validates
the owner metadata and supplied license without editing files.

Current data-snapshot manifest:

```text
docs/publication/benchmark/data_snapshot_manifest.json
```

Stable manifest hash:

```text
f424cf0ce18199ca291b9a396dd89660c654d049cc9bdeff1bbdcf1b8a0ba094
```

The manifest records 33 cohorts, zero missing count-matrix hashes and a missing
RNA updater sync manifest in this checkout. The benchmark matrices are pinned by
final SHA-256 hashes.

## Key Submission Artifacts

```text
manuscript/bioinformatics_app_note/build/tcga-trace-bioinformatics-application-note.pdf
manuscript/bioinformatics_app_note/build/tcga-trace-bioinformatics-supplement.pdf
manuscript/bioinformatics_app_note/figures/graphical_abstract.tex
manuscript/bioinformatics_app_note/figures/tcga_trace_graphical_abstract_background.png
manuscript/bioinformatics_app_note/submission/artifact_manifest.md
manuscript/bioinformatics_app_note/submission/reviewer_walkthrough.md
docs/publication/external_concordance_kmplotter_ca9_kirc.md
docs/publication/benchmark/reproducibility_benchmark/summary.md
docs/publication/benchmark/clean_container_reproduction/summary.md
docs/publication/benchmark/statistical_calibration/summary.md
docs/publication/benchmark/feature_benchmarks/signature_definitions.md
docs/publication/benchmark/skcm_sample_rule_sensitivity/README.md
docs/publication/benchmark/skcm_tmem176b_sample_rule_sensitivity/README.md
```

The compact reviewer/source archive can be rebuilt alone after final owner
metadata is inserted with:

```sh
scripts/publication/build_submission_archive.py --strict-owner-metadata
```

Full TCGA expression matrices and full patient-level analysis exports are not
redistributed in git. They are generated locally by the Dockerized application
and reproducibility-bundle workflow.

## Known Submission Placeholders

The technical package is prepared, but journal upload still requires
project-owner values for author metadata, funding, conflict of interest,
software license and the version-specific Zenodo DOI/archive.
To insert them without editing LaTeX directly, copy and fill
`manuscript/bioinformatics_app_note/submission/owner_metadata.template.json`,
then run the finalizer:

```sh
scripts/publication/finalize_submission_package.py path/to/owner_metadata.json --license-source path/to/LICENSE --dry-run
scripts/publication/finalize_submission_package.py path/to/owner_metadata.json --license-source path/to/LICENSE
```

Filled `owner_metadata*.json` files are ignored by git except for the template,
so private reviewer URLs or contact details do not get staged accidentally.

The finalizer runs the strict owner-metadata check and is expected to fail until
those values and the selected license file are inserted.
