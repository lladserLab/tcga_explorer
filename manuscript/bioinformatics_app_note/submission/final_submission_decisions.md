# Final Submission Decisions

Status date: 2026-07-26.

This file collects the project-owner decisions that must be filled before
TCGA-TRACE can be submitted as a Bioinformatics Application Note. The technical
manuscript, comparison narrative, benchmark tables and PDF build are ready for
these values to be inserted.

## Required Manuscript Metadata

| Field | Current placeholder | Final value |
| --- | --- | --- |
| Author list | `Sergio Hernández-Galaz; Andrés Hernández-Oliveras; Ignacio Pezoa-Soto; Javiera Reyes-Alvarez; Vincenzo Benedetti; Alberto J. M. Martin; Alvaro Lladser` | Confirmed 2026-07-25 |
| Affiliations | Four numbered affiliations supplied in `main.tex` and `owner_metadata.template.json` | Confirmed 2026-07-25 |
| Corresponding author | `email@example.org` | TODO |
| Submitting author and ORCID | Required in the submission system | TODO |
| CRediT author contributions | `CRediT contribution statement placeholder` | TODO |
| Funding statement | Centro Basal Ciencia & Vida FB210008; ANID Fondecyt 1251312 to A.L. and 1231629 to A.J.M.M.; ANID postdoctoral fellowship 3260791 to S.H.-G.; NLHPC CCSS210001 | Confirmed 2026-07-25 |
| Conflict of interest | `The authors declare no conflicts of interest.` | Confirmed 2026-07-25 |
| AI-use disclosure | Required after independent author review of the assisted draft | TODO |

## Availability And Legal Decisions

| Field | Why it matters | Final value |
| --- | --- | --- |
| Software license | Bioinformatics requires free availability to non-commercial users and encourages an open-source license; TCGA-TRACE release policy requires complete OSI-compatible license text. | MIT; complete top-level `LICENSE` added 2026-07-26. |
| Public or reviewer-accessible repository URL | Required for reviewer access and post-publication availability. | `https://github.com/lladserLab/tcga_explorer` |
| Stable release DOI or archive URL | Needed for a citable submitted version. | Zenodo selected; version-specific DOI pending reservation/publication. |
| Public demo URL or Docker-only access statement | Needed to tell reviewers how to evaluate the web application. | Public URL supplied: `https://apps.cienciavida.org/tcga_explorer/`; health endpoint verified `ok` on 2026-07-24. Docker instructions remain as a reproducibility fallback. |
| Two-year software and web-service availability commitment | Bioinformatics requires the software to remain available for a full two years after publication. | TODO |
| Data availability note | Needed because full TCGA patient-level exports are generated locally and not tracked in git. | Prepared wording in `manuscript/bioinformatics_app_note/submission/data_availability_statement.md`; owner/legal review before upload. |
| Final TCGA data manifest | Needed to pin the RNA/CDR snapshot used by benchmark claims. | `docs/publication/benchmark/data_snapshot_manifest.json`; stable manifest hash `f424cf0ce18199ca291b9a396dd89660c654d049cc9bdeff1bbdcf1b8a0ba094`. |
| Reviewer concordance record | Needed to show at least one comparison against an established external tool. | `docs/publication/external_concordance_kmplotter_ca9_kirc.md`; KM Plotter direction concordant for TCGA-KIRC CA9 OS median split, nominal significance not concordant. |

## Submission Logistics

| Field | Why it matters | Final value |
| --- | --- | --- |
| Open-access APC or waiver route | Bioinformatics is fully open access; payment, institutional agreement, discount or waiver handling must be resolved on the journal timeline. This operational decision does not block assembly of the submission package. | TODO |
| Author-led scientific review and verification | Authors must independently review the code, analyses and prose, remain accountable for the final work and disclose AI assistance in the cover letter and manuscript. Contact the editorial office if any use falls outside the journal's stated examples. | TODO |
| Support owner and contact | A named maintainer and support contact are needed to uphold the two-year availability commitment. | TODO |
| Cross-browser compatibility record | Bioinformatics states that web servers should not be browser-specific; complete `submission/browser_compatibility_record.md` for Chromium, Gecko and WebKit engines. | Provisional local build passed 24/24 automated checks on 2026-07-25; rerun the contract against the exact tagged HTTPS release. |

## Policy Basis

The Bioinformatics author guidelines were rechecked on 2026-07-26:
`https://academic.oup.com/bioinformatics/pages/author-guidelines`. For an
Application Note they specify up to four journal-template pages, approximately
2,600 words or 2,000 words plus one figure; free availability to
non-commercial users; a full two years of software availability; no mandatory
registration; browser-independent web services; stable source and archived
submitted-version URLs; reproduction information; and AI-use disclosure in
the cover letter plus Methods or Acknowledgements. Open-source licensing is
encouraged rather than stated as a journal requirement. TCGA-TRACE deliberately
keeps a complete OSI-compatible license as a stricter project release gate.

## Recommended Defaults To Confirm

- Repository: `https://github.com/lladserLab/tcga_explorer`.
- Release archive: Zenodo, using the version-specific DOI for the exact
  submitted GitHub release.
- Article type: Bioinformatics Application Note.
- Target title: `TCGA-TRACE: auditable survival analysis for TCGA transcriptomic biomarkers`.
- Contribution claim: a machine-verifiable TCGA survival run record that integrates endpoint/sample provenance, score reconstruction, PH diagnostics, RMST and cutpoint sensitivity.
- Claims to avoid as primary novelty: first Kaplan-Meier tool, first two-biomarker survival tool, first gene-set survival tool.

## Current Technical Validation Snapshot

Validated on 2026-07-26:

- `make -C manuscript/bioinformatics_app_note clean all` completed.
- The 12-point, double-spaced review PDF is 12 pages; this is not the journal
  page-count metric.
- The synchronized Bioinformatics OUP `modern,large`, author-date preview is
  4/4 template pages; OUP notes that this is not an exact production-page
  guarantee.
- The 23-page supplementary PDF contains 8 tables and no figures.
- `texcount -inc -sum` reports a sum count of 1,841 for `main.tex`, including
  1,660 text words and one integrated figure.
- The technical editorial gate confirms the structured abstract, one integrated
  vector Figure 1 with inline alt text, no main-text tables and sequential
  Supplementary Tables S1--S8.
- All 17 frozen Paper Examples cases are explicitly mapped in the manuscript
  package.
- `python3 -m py_compile` covers the benchmark, data-manifest,
  reproducibility-bundle, owner-metadata, license-template, finalizer,
  screenshot-capture, identity, runtime, OUP-preview, editorial-check and
  submission-archive scripts, plus the standalone public API CLI.
- Backend tests pass in Docker: `140 passed`.
- Publication-script tests pass: `136 passed`.
- Standalone tests pass: `15 passed`: 14 CLI tests covering all six public
  compute families and negative integrity controls, plus one attestation
  verifier test.
- Frontend tests pass: `15 passed`; the production Docker build also passes.
- Submission artifact checker reports `109/109` artifacts available, including
  the cover-letter draft, Data Availability statement and three current
  reconstruction bundles, the statistical-calibration benchmark and the
  runtime/concurrency benchmark, CLI and bilingual CLI guides.
- The generated TCGA-TRACE review archive passes verification with 485 entries.
- Provisional browser compatibility passes 24/24 functional checks across
  Chromium, Firefox/Gecko and WebKit; strict finalization still requires the
  exact tagged HTTPS release run.
- The CLI passed a real local-Docker smoke test for CDC20/LIHC: OpenAPI
  compatibility, cached submission, completed-job retrieval, retained ZIP
  download and family-aware verification all passed.
- Public web application `https://apps.cienciavida.org/tcga_explorer/` returned
  HTTP 200, and `https://apps.cienciavida.org/tcga_explorer/api/v1/health`
  returned app status `ok` and 33 cohorts.
- CI workflow prepared at `.github/workflows/ci.yml` for backend Docker
  build/tests, publication-script syntax/tests, standalone CLI tests, frontend
  Docker build and independent clean-capsule reproduction without local TCGA
  data.
- Data manifest generated with count-matrix hashes: 33 cohorts, zero missing
  count-matrix hashes.
- The RNA updater sync manifest is recorded as missing in this checkout; the
  current publication manifest pins benchmark matrices by final SHA-256 hashes.
- The audit-reconstruction benchmark covers three frozen analyses:
  single-gene, weighted-signature and crossed-signature. Internal check counts
  measure coverage within those runs, not independent replications.
- The standalone capsules pass 6/6 clean, network-disabled reruns on native
  arm64 and locally emulated amd64 under the recorded quantity-aware
  absolute-plus-relative numeric policy.
- Integrity-boundary controls distinguish fields bound by the reproducibility
  hash, separately checksummed artifacts and intentionally unbound metadata.
- External concordance record completed against KM Plotter pan-cancer RNA-seq:
  TCGA-KIRC CA9 OS median split is direction concordant but not an exact
  statistical replication.

## Final Pre-Submission Command

Run this after replacing the submission-blocking values above. The APC route
may remain operationally pending until the journal timeline requires it. The
low-friction path is to copy
`manuscript/bioinformatics_app_note/submission/owner_metadata.template.json`,
fill it outside git if desired, then run the finalizer command below.

The repository now contains the complete MIT license text. If a separate
license source is supplied to the finalizer, it must contain the complete text,
not a short stub such as `MIT` or `Selected license`.

For common permissive options already listed in the release checklist, the
license text can be regenerated if the owner changes the year or copyright
holder:

```sh
scripts/publication/write_license_template.py --list
scripts/publication/write_license_template.py --license MIT --year 2026 --holder "FINAL COPYRIGHT HOLDER" --output path/to/LICENSE
```

Then run the final packaging command:

```sh
scripts/publication/finalize_submission_package.py \
  path/to/owner_metadata.json \
  --license-source LICENSE \
  --dry-run

scripts/publication/finalize_submission_package.py \
  path/to/owner_metadata.json \
  --license-source LICENSE
```

The dry run prints the exact command plan and validates owner metadata plus the
supplied license without editing files. The second command applies the owner
metadata, runs `pre_submission_check.sh
--strict-owner-metadata`, builds the final compact archive, verifies the
archive manifest and writes a neighboring `*.summary.json` file with the final
PDF and archive SHA-256 values. Use the expanded command below only when
debugging a failed step manually.

Strict gate alone:

```sh
scripts/publication/pre_submission_check.sh --strict-owner-metadata
```

Equivalent expanded command:

```sh
python3 -m py_compile \
  scripts/publication/apply_submission_metadata.py \
  scripts/publication/build_oup_preview.py \
  scripts/publication/build_submission_archive.py \
  scripts/publication/capture_reviewer_screenshots.py \
  scripts/publication/check_editorial_compliance.py \
  scripts/publication/check_submission_artifacts.py \
  scripts/publication/check_submission_metadata.py \
  scripts/publication/finalize_submission_package.py \
  scripts/publication/run_cutpoint_benchmark.py \
  scripts/publication/run_single_gene_benchmark_suite.py \
  scripts/publication/run_feature_benchmarks.py \
  scripts/publication/run_reproducibility_benchmark.py \
  scripts/publication/run_clean_reproduction_benchmark.py \
  scripts/publication/run_statistical_calibration.py \
  scripts/publication/run_skcm_sample_rule_sensitivity.py \
  scripts/publication/export_data_snapshot_manifest.py \
  scripts/publication/verify_submission_archive.py \
  scripts/publication/verify_reproducibility_bundle.py \
  scripts/publication/write_license_template.py

scripts/publication/check_submission_metadata.py --strict

docker compose run --rm --no-deps \
  -v "$PWD/backend/tests:/app/tests:ro" \
  backend pytest -q /app/tests

docker compose run --rm --no-deps \
  -v "$PWD/scripts/publication:/app/publication:ro" \
  backend pytest -q /app/publication/tests

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
scripts/publication/run_clean_reproduction_benchmark.py --check-only
make -C manuscript/bioinformatics_app_note clean all
scripts/publication/check_editorial_compliance.py
docker run --rm \
  -e LC_ALL=C \
  -e LANG=C \
  -v "$PWD/manuscript/bioinformatics_app_note":/work \
  -w /work \
  texlive/texlive@sha256:1a1b8588cd73ac33fe1d7722c4065b3e6eaa3f3a20fb54d2934e42310264d134 \
  texcount -inc -brief main.tex supplementary.tex
scripts/publication/check_submission_artifacts.py
archive_tmp="$(mktemp)"
scripts/publication/build_submission_archive.py --strict-owner-metadata --output "$archive_tmp" >/dev/null
scripts/publication/verify_submission_archive.py "$archive_tmp"
git diff --check
```
