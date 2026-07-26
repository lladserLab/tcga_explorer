# TCGA-TRACE Bioinformatics Application Note

This folder contains the working Bioinformatics Application Note draft.

The manuscript is intentionally framed around the reproducibility and model-QC
gap: run reports, exact patient records, endpoint provenance, proportional
hazards diagnostics, RMST and cutpoint sensitivity. Two-signature analysis is
included as a supported workflow, not as the primary novelty claim, because
cSurvival is prior art for two-predictor survival interaction.

## Build

The host does not need a local LaTeX installation. The Makefile produces three
different review artifacts:

```sh
make all
```

Outputs:

```text
build/tcga-trace-bioinformatics-application-note.pdf  12-point, double-spaced and line-numbered review manuscript
build/tcga-trace-bioinformatics-supplement.pdf        single supplementary PDF
build/tcga-trace-bioinformatics-oup-preview.pdf       synchronized OUP two-column page-limit preview
```

Individual targets are also available:

```sh
make pdf
make supplement
make oup-preview
```

Build all outputs and run the technical editorial gate:

```sh
make compliance
```

The default TeX image is pinned by digest to the validated build containing
`oup-authoring-template` 1.5. It can be overridden deliberately, for example:

```sh
TEX_IMAGE=texlive/texlive:latest make compliance
```

## Journal Constraints

The draft targets a Bioinformatics Application Note. The current official
limit is four journal pages, with an approximate content budget of 2,600 words
without a figure or 2,000 words plus one figure. A five-page manuscript is 25%
over the limit and is liable to immediate return. Initial submissions must use
at least 12-point type, double spacing and line numbers; revised/final files use
the OUP template.

The format-free review source is the canonical manuscript. The OUP preview is
generated from that source by `build_oup_preview.py`, so it does not maintain a
second copy of the scientific narrative. Its class settings follow the
Bioinformatics row in OUP's supported-journals list: numbered sections,
`modern,large` design, and author-date citations via `namedate` and `abbrvnat`.
The list calls the heading mode `numsec`; `oup-authoring-template` 1.5 does not
declare that option and instead numbers sections by default, so the generated
class line deliberately omits both `numsec` and `unnumsec`.
OUP states that author templates do not exactly reproduce final typesetting;
the preview is therefore a conservative page estimate, not a guarantee of the
production page count.
On 2026-07-26:

- the OUP `modern,large` preview is 4/4 pages;
- the main source contains one integrated vector Figure 1 with inline alt text
  and no empirical tables;
- `texcount -inc -sum` reports sum counts of 1,841 for the main source and
  4,277 across the supplementary source and its included tables; text-word
  counts are 1,660 and 3,916;
- the single supplementary PDF contains 8 tables and no figures;
  and the complete 11-scenario evidence matrix remains in Supplementary
  Table S4.

No separate numerical limit for supplementary tables or figures was identified
in the current instructions. The eight essential tables are kept in one cited
supplementary PDF,
while the main manuscript remains within the four-page limit. Recheck the
official instructions immediately before upload because journal policies can
change.

Before submission, copy and fill
`submission/owner_metadata.template.json`, then apply the final owner metadata
with `../../scripts/publication/apply_submission_metadata.py`. This updates the
manuscript, cover letter, Data Availability statement and decision tracker
without direct LaTeX edits. Author order, affiliations, funding, conflict
statement, MIT license, repository and demo URL are already supplied.
Corresponding and submitting-author details, CRediT roles, AI-use disclosure,
release DOI/archive and two-year support commitment still require owner
confirmation. The exact tagged HTTPS cross-browser run also remains. The author
team must independently review, rewrite
where necessary and verify all author-facing prose, disclose AI assistance in
the manuscript, supplement and cover letter, and contact the editorial office
if any use falls outside the examples covered by the journal guidance.

## Submission Files

- `submission/submission_readiness_checklist.md`: current go/no-go checklist
  against Bioinformatics Application Note requirements.
- `submission/cover_letter_draft.md`: reviewer-facing cover letter draft.
- `submission/anticipated_reviewer_response.md`: working response map for
  likely method, software and genomics reviewer objections.
- `submission/reviewer_reproduction_guide.md`: end-to-end local reproduction
  guide for reviewers.
- `submission/reviewer_walkthrough.md`: short guide to the visible web
  interface and expected outputs.
- `submission/reviewer_access_statement.md`: public web instance plus Docker
  fallback reviewer access text.
- `submission/data_availability_statement.md`: prepared data-availability text
  for the final manuscript and submission form.
- `submission/release_and_license_checklist.md`: final license, repository,
  release-tag and DOI steps that require owner decisions.
- `submission/browser_compatibility_record.md`: final Chromium, Gecko and
  WebKit smoke-test record for the tagged public release.
- `submission/artifact_manifest.md`: map of manuscript, benchmark and
  submission support files.
- `submission/final_submission_decisions.md`: grouped owner decisions,
  operational follow-ups and exact-release gates.
- `submission/owner_metadata.template.json`: JSON template consumed by the
  metadata application script; schema v2 keeps corresponding and submitting
  author identities distinct.
- `../../docs/publication/application_note_writing_blueprint.md`: writing and
  structure model derived from the published GRNContext Application Note,
  current Bioinformatics rules, Nature readability guidance and REMARK.
- `../../scripts/publication/apply_submission_metadata.py`: validates and
  applies final owner metadata to `main.tex`, the supplement, cover letter,
  Data Availability statement and decision tracker.
- `../../scripts/publication/build_submission_archive.py`: compact
  reviewer/source archive builder for the final release package.
- `../../scripts/publication/build_oup_preview.py`: generates the synchronized
  OUP two-column page-limit preview from `main.tex`.
- `../../scripts/publication/capture_reviewer_screenshots.py`: regenerates the
  optional reviewer-facing interface screenshot from a running local stack.
- `../../scripts/publication/check_editorial_compliance.py`: enforces the
  technical page, abstract, float and alt-text gates.
- `../../scripts/publication/check_submission_artifacts.py`: verifies the
  required upload, reviewer, evidence and software artifact set.
- `../../scripts/publication/export_immune_atlas_benchmark.py`: validates the
  frozen 3,118-gene ImmPort atlas and regenerates its archived scale-test
  record; the atlas is not part of the submitted supplement.
- `../../scripts/publication/verify_submission_archive.py`: verifies that a
  reviewer/source archive contains the required files and excludes local runtime
  data.
- `figures/graphical_abstract.tex`: complete vector TikZ source for Figure 1.
- `figures/figure_alt_text.md`: accessibility description for Figure 1.
- `figures/tcga_trace_ui_analysis.png`: reviewer-facing screenshot of a
  completed LIHC/CDC20 single-gene analysis; retained as an optional review aid
  rather than a supplementary figure.
- `figures/tcga_trace_ui_multiverse.png`: reviewer-facing screenshot of the
  completed LIHC/CDC20 two-cell specification family and its execution ledger;
  also retained as an optional review aid.
- `supplementary.tex`: supplementary comparator and benchmark tables.
- `tables/immune_pancancer_atlas_model_summary.tex`: archived family-specific
  primary and ordinal-sensitivity summary for the full immune atlas; not
  included in the submitted supplement.
