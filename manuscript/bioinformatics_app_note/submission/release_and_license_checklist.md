# Release And License Checklist

Status date: 2026-07-26.

This checklist records the remaining project-owner release steps. GitHub and
Zenodo are the selected source and archive locations, and the software license
is MIT; the checklist does not select authors or an APC route.

## 1. Complete Owner Metadata

Copy `owner_metadata.template.json`. It already contains the confirmed author
order, four affiliations, funding statement, conflict declaration, public
repository and application URL. Review those prefilled values, then supply:

- corresponding-author name and email;
- submitting-author name and ORCID, independently of the corresponding author;
- CRediT contribution statement;
- accurate disclosure of permitted AI assistance;
- the version-specific Zenodo DOI/archive URL;
- explicit software and service availability commitment for at least two years;
- named support owner/contact; and
- dated confirmation of independent author review and scientific verification.

The author team must independently review, rewrite where necessary and
scientifically verify the final author-facing text. Bioinformatics explicitly
requires AI used to generate content, write code or process data to be
disclosed in both the cover letter and Methods or Acknowledgements. Contact the
editorial office if the authors determine that any use falls outside the
journal's stated examples.

Policy source rechecked 2026-07-26:
`https://academic.oup.com/bioinformatics/pages/author-guidelines`.

## 2. Verify The Software License

Bioinformatics requires free software/data availability to non-commercial
users and encourages an open-source license. TCGA-TRACE adopts a complete
top-level OSI-compatible `LICENSE` or `COPYING` file as a stronger project
release requirement before reviewer access. The complete MIT text is present
at repository root and `owner_metadata.template.json` records `MIT`.

If the owner changes the year or copyright holder, regenerate the full text:

```sh
scripts/publication/write_license_template.py --list
scripts/publication/write_license_template.py \
  --license MIT \
  --year 2026 \
  --holder "FINAL COPYRIGHT HOLDER" \
  --output LICENSE
```

Short values such as `MIT` or `Selected license` are not valid license files
and fail the strict gate.

## 3. Confirm Repository And Service Access

The public repository corresponding to the current git remote is:

```text
https://github.com/lladserLab/tcga_explorer
```

Before submission, confirm that the public repository points to the exact
submitted tagged source state. The released source must include Docker files, benchmark
scripts, compact outputs, the data snapshot manifest, reviewer instructions
and the final license.

Also confirm:

- the HTTPS application works without an account;
- the documented reviewer example can be executed;
- Help/Methods and support contact are visible;
- a named maintainer accepts responsibility for at least two years after
  publication; and
- the Docker reproduction path remains available if the hosted service is
  temporarily unavailable.

## 4. Reserve The Archive Identifier

The manuscript abstract must contain a stable URL for the submitted software
version. Zenodo is the selected archive.

Connect `lladserLab/tcga_explorer` to Zenodo, reserve the version-specific DOI,
insert it in `owner_metadata.json`, build and review the final package, then
publish the Zenodo record against the exact tagged GitHub source state.

## 5. Run Finalization

Validate owner metadata and license without editing files:

```sh
scripts/publication/finalize_submission_package.py \
  path/to/owner_metadata.json \
  --license-source path/to/LICENSE \
  --dry-run
```

Then apply metadata, copy the license, run the strict gate, build the compact
source/reviewer archive and write final SHA-256 values:

```sh
scripts/publication/finalize_submission_package.py \
  path/to/owner_metadata.json \
  --license-source path/to/LICENSE
```

Filled `owner_metadata*.json` files are ignored by git except for the template.
Review the generated manuscript, supplement, cover letter and package summary
before release.

## 6. Commit, Tag, Push And Archive

This worktree contains unrelated and untracked files. Do not use an unreviewed
`git add .`. Inspect the tree and stage only the final submission paths:

```sh
git status --short
git add <reviewed-submission-paths>
git diff --cached --check
git commit -m "Prepare TCGA-TRACE Bioinformatics submission package"
git tag -a v0.1.0-bioinformatics-submission \
  -m "TCGA-TRACE Bioinformatics submission"
git push origin HEAD
git push origin v0.1.0-bioinformatics-submission
```

Publish the archive from that exact tag and verify that its DOI/URL matches the
manuscript. If the final DOI differs from the reserved value, update metadata,
rerun the finalizer and create a corrected release tag rather than silently
changing the submitted source.

Deploy that exact tag with `APP_RELEASE_COMMIT` set to its full commit and
`APP_RELEASE_REF` set to the tag. Then run the GitHub Actions
`Release readiness` workflow manually with the same tag and public HTTPS URL.
The workflow rejects a dirty/non-tagged checkout, a deployment reporting a
different commit or release ref, unresolved owner metadata, an editorial
violation or an invalid reviewer archive. Retain its `SHA256SUMS` and uploaded
submission artifact with the release record.

## 7. Open-Access Logistics

Bioinformatics is fully open access. Before acceptance, the owner/institution
must determine:

- who pays the APC;
- whether an ISCB member discount applies; or
- whether a waiver or discount request must be submitted.

Record this decision in `final_submission_decisions.md`. Waiver handling should
be addressed on the journal timeline, not after an invoice is issued. This
operational item does not block creation of the reviewer package.

## 8. Final Upload Set

Prepare:

- main review manuscript PDF;
- single supplementary PDF;
- mandatory cover letter;
- complete source repository or compact verified source archive;
- final package summary JSON;
- complete MIT license;
- archived release DOI/URL;
- Data Availability statement;
- data snapshot manifest; and
- reviewer reproduction/access instructions.

The OUP two-column preview is an internal four-page compliance artifact. Include
it in the source/reviewer archive, but do not upload it as a second manuscript
unless the editorial office requests it.
