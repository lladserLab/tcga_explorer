# Release And License Checklist

Status date: 2026-07-24.

This checklist records the remaining project-owner release steps. GitHub and
Zenodo are the selected source and archive locations; the checklist does not
select authors, a license or an APC route.

## 1. Complete Owner Metadata

Copy `owner_metadata.template.json` and supply:

- final author names, order and affiliations;
- corresponding-author name and email;
- submitting-author ORCID;
- CRediT contribution statement;
- funding and conflict-of-interest statements;
- accurate disclosure of permitted AI assistance;
- the prefilled public repository and application URLs;
- the version-specific Zenodo DOI/archive URL;
- license identifier;
- explicit three-year service-maintenance commitment; and
- named support owner/contact.

The author team must independently rewrite and scientifically verify the final
author-facing text. Manuscript drafting is not among the common acceptable uses
listed in the current Bioinformatics AI policy, so the assistance must be
disclosed and its acceptability confirmed with the editorial office.

## 2. Choose The Software License

Bioinformatics requires software/data availability. The final repository must
contain a complete top-level `LICENSE` or `COPYING` file before reviewer access.

Common choices for owner/institutional review:

- MIT: permissive, minimal conditions.
- BSD-3-Clause: permissive with non-endorsement language.
- Apache-2.0: permissive with an explicit patent grant.
- GPL-3.0-or-later: copyleft.

For supported permissive choices, generate complete text after the owner has
selected the license, year and copyright holder:

```sh
scripts/publication/write_license_template.py --list
scripts/publication/write_license_template.py \
  --license MIT \
  --year 2026 \
  --holder "FINAL COPYRIGHT HOLDER" \
  --output path/to/LICENSE
```

Use institution-approved full text for any other license. Short values such as
`MIT` or `Selected license` are not valid license files and fail the strict
gate.

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
- a named maintainer accepts responsibility for at least three years after
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
be addressed on the journal timeline, not after an invoice is issued.

## 8. Final Upload Set

Prepare:

- main review manuscript PDF;
- single supplementary PDF;
- mandatory cover letter;
- complete source repository or compact verified source archive;
- final package summary JSON;
- selected license;
- archived release DOI/URL;
- Data Availability statement;
- data snapshot manifest; and
- reviewer reproduction/access instructions.

The OUP two-column preview is an internal four-page compliance artifact. Include
it in the source/reviewer archive, but do not upload it as a second manuscript
unless the editorial office requests it.
