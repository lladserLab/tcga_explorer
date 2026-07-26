# Bioinformatics Application Note Submission Checklist

Status date: 2026-07-26.

Target article type: Bioinformatics Application Note.

Official sources last checked on 2026-07-26:

- Author guidelines:
  https://academic.oup.com/bioinformatics/pages/author-guidelines
- Online submission:
  https://academic.oup.com/bioinformatics/pages/submission_online
- OUP supported-journals list and LaTeX template:
  https://academic.oup.com/pages/for-authors/journals/preparing-and-submitting-your-manuscript
- Open access:
  https://academic.oup.com/bioinformatics/pages/open-access

Journal policies can change. Recheck these pages immediately before upload.

## Editorial Limits

| Requirement | Current state | Status |
| --- | --- | --- |
| Maximum length | Four journal pages. Five pages is 25% over the limit and is liable to immediate return. | OUP `modern,large` preview is 4/4 pages. |
| Approximate content budget | About 2,600 words without a figure or 2,000 words plus one figure. | Main sum count is 1,998, including 1,840 text words and one figure; OUP preview remains 4/4 pages. |
| Initial review format | At least 12-point type, double spacing and line numbers. | Enabled in `main.tex`; review PDF is 12 pages. |
| Revised/final format | OUP authoring template. | Preview uses the Bioinformatics mapping: numbered sections, `modern,large`, author-date citations and `Applications Note` article label. |
| Abstract | Headings must be `Summary`, `Availability and Implementation`, `Contact` and `Supplementary Information`; Summary is one or two sentences. | Four headings are in order; Summary has two sentences. |
| Main display items | Must fit within the four-page article. | One integrated full-width vector figure and no main-text tables. |
| Accessibility | Figure alt text must follow the legend. | Figure 1 includes inline alt text after its legend; the standalone accessibility source is also retained. |
| Supplement | Submit as one separate file, with items cited from the manuscript. | One supplementary PDF with 8 essential tables and no figures; all tables precede the references. |
| Cover letter | Required at submission. | Draft exists; author-led rewrite and final sign-off are pending. |
| Data Availability | Required statement. | Prepared with the public GitHub URL and Zenodo as the archive; final license and version-specific DOI are pending. |

The current instructions do not state a separate numerical maximum for
supplementary tables or figures. The supplement retains eight essential, cited
tables, including the complete 11-scenario evidence matrix in Table S4. The
main manuscript uses one integrated vector figure and no empirical tables
while remaining within the four-page limit. The 12-page review PDF is not
the journal page-count metric: its length results from the required 12-point,
double-spaced submission format. The synchronized OUP preview is the page-limit
estimate and currently occupies four pages. OUP states that author templates
do not exactly reproduce final typesetting, so this is a conservative local
gate rather than a production-page guarantee.

## Technical Package Ready

- Canonical manuscript:
  `manuscript/bioinformatics_app_note/main.tex`.
- Review PDF:
  `manuscript/bioinformatics_app_note/build/tcga-trace-bioinformatics-application-note.pdf`.
- OUP page-limit preview:
  `manuscript/bioinformatics_app_note/build/tcga-trace-bioinformatics-oup-preview.pdf`.
- Single supplementary PDF:
  `manuscript/bioinformatics_app_note/build/tcga-trace-bioinformatics-supplement.pdf`.
- Main vector figure and accessibility source:
  `figures/graphical_abstract.tex` and `figures/figure_alt_text.md`.
- The supplement orders Tables S1-S8 before the reference list and contains no
  figures.
- All 17 frozen Paper Examples cases are explicitly mapped between the main
  manuscript and supplement.
- The comparator table correctly treats cSurvival two-predictor analysis and
  PESSA ssGSEA as prior art.
- The narrative centers the defensible contribution: a machine-verifiable run
  record that integrates endpoint/sample provenance, score reconstruction,
  automatic PH diagnostics, RMST and cutpoint-sensitivity reporting.
- Public HTTPS application:
  `https://apps.cienciavida.org/tcga_explorer/`.
- Public health endpoint returned status `ok` with 33 cohorts on 2026-07-24:
  `https://apps.cienciavida.org/tcga_explorer/api/v1/health`.
- Reviewer quickstart, walkthrough, reproduction guide and Docker fallback are
  included.
- Compact benchmark records, the 33-cohort data snapshot manifest, three
  audit-reconstruction bundles and their standalone pinned R capsules are
  included.
- `check_editorial_compliance.py` enforces page count, abstract structure,
  main/supplement float counts and inline alt text.
- `application_note_writing_blueprint.md` records the internal editorial
  structure review; it is not a scientific comparator or manuscript citation.
- `check_submission_artifacts.py` verifies the complete technical handoff.
- Backend, publication-script, standalone-script and frontend tests pass:
  `138 + 133 + 15 + 15`. The standalone suite comprises 14 CLI tests across
  all six public compute families plus one server-attestation verifier test.
- The artifact checker reports `109/109`; the compact review archive verifies
  480 entries.
- Frozen capsules pass 6/6 network-disabled clean-container reruns across
  native arm64 and locally emulated amd64. Hosted amd64 CI independently passed
  both jobs for commit `00c3aaeb18ce5871b69122641db0bf3810b2d1d1` in run
  `30188150881`; the exact tagged release must repeat the gate after deployment.

## Remaining Submission Blockers

The technical editorial gate passes, but journal submission must not proceed
until every item below is resolved:

- Corresponding-author name and institutional email.
- Submitting-author name and ORCID.
- CRediT contribution statement.
- Complete top-level software license.
- Exact submitted code state tagged and pushed to the public GitHub repository.
- Passing independent clean-reproduction CI run for that exact commit.
- Tagged release archived on Zenodo with its stable version-specific DOI/URL.
- Software and public web-service availability commitment for at least two
  years after publication.
- Named support owner and support contact for those two years.
- Provisional automated smoke tests pass 24/24 checks across Chromium,
  Firefox/Gecko and WebKit. Regenerate the record against the exact tagged
  HTTPS release; add a short manual Safari-product check if deployment behavior
  depends on Safari-specific integration.
- Owner/legal approval of the Data Availability wording.
- Final cover letter and submission-system metadata.
- Independent author rewrite and scientific verification of all author-facing
  prose, tables, captions and references.
- Accurate disclosure of permitted AI assistance in the cover letter and
  manuscript and detailed supplementary disclosure, following the current OUP
  AI policy.

Author order, affiliations, funding, conflict declaration, public repository
and public demo URL are already supplied. The APC, ISCB discount or waiver
route remains an operational owner decision on the journal timeline, but it
does not block construction of the reviewer package.

The last two points are submission blockers. Bioinformatics requires AI used
to generate content, write code or process data to be disclosed in both the
cover letter and Methods or Acknowledgements. The current package remains an
engineering and editorial working draft: the author team must independently
review, rewrite where necessary and verify the final text, and contact the
editorial office if any use falls outside the examples covered by the journal
guidance.

## Finalization Workflow

1. Copy and complete
   `submission/owner_metadata.template.json`.
2. Select the full license text and save it outside the repository until the
   owner/institution approves it.
3. Validate without editing:

```sh
scripts/publication/finalize_submission_package.py \
  path/to/owner_metadata.json \
  --license-source path/to/LICENSE \
  --dry-run
```

4. Apply owner metadata, run the strict gate and generate the final archive:

```sh
scripts/publication/finalize_submission_package.py \
  path/to/owner_metadata.json \
  --license-source path/to/LICENSE
```

5. Commit and push only the reviewed submission files, create a release tag,
   archive that exact release, insert the resulting DOI and rerun the
   finalizer. Deploy it with `APP_RELEASE_COMMIT` and `APP_RELEASE_REF`, then
   run `.github/workflows/release-readiness.yml` against that exact tag and
   HTTPS URL.

## Verification Commands

Current technical check:

```sh
make -C manuscript/bioinformatics_app_note compliance
python3 -m pytest -q scripts/publication/tests
python3 -m pytest -q scripts/tests
scripts/publication/check_submission_artifacts.py
scripts/publication/check_submission_metadata.py
git diff --check
```

The metadata checker is expected to report owner blockers until the fields above
are resolved. The strict upload gate must pass after owner finalization:

```sh
scripts/publication/pre_submission_check.sh --strict-owner-metadata
```

The finalizer additionally builds and verifies the compact source/reviewer
archive and writes SHA-256 values for the main PDF, supplement, OUP preview and
archive.
