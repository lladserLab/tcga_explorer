# Submission Artifact Manifest

Status date: 2026-07-25.

Current working branch:

```text
feature/bioinformatics-readiness-20260721-210041
```

Submission-package lineage at time of writing includes:

```text
ac32eb6 Add final Bioinformatics submission decision tracker
d1c0064 Document v0.1.0 functional baseline
e62446c Add methods help and changelog
1b319c2 Improve comparison accessibility affordances
1970a25 Refine comparison workflow layout
ea3ef0e Reorganize comparison controls layout
58386f4 Add plot editing controls to comparison view
16423f2 Make cohort picker menu floating
33dc699 Improve comparison controls and reviewer docs
53f837a Prepare Bioinformatics submission package
dc19150 Add publication benchmark suite and comparator matrix
c671ef0 Add publication cutpoint benchmark evidence
f3ad3f2 Add RMST reporting and Bioinformatics manuscript draft
```

## Manuscript Sources

| Artifact | Path | Purpose |
| --- | --- | --- |
| Main manuscript | `manuscript/bioinformatics_app_note/main.tex` | Bioinformatics Application Note draft. |
| References | `manuscript/bioinformatics_app_note/references.bib` | Bibliography for main manuscript. |
| Review PDF | `manuscript/bioinformatics_app_note/build/tcga-trace-bioinformatics-application-note.pdf` | Required 12-point, double-spaced and line-numbered review rendering. |
| OUP preview PDF | `manuscript/bioinformatics_app_note/build/tcga-trace-bioinformatics-oup-preview.pdf` | Synchronized Bioinformatics `modern,large`, author-date rendering used as a conservative four-page estimate; OUP states that templates do not exactly reproduce final typesetting. |
| Supplement PDF | `manuscript/bioinformatics_app_note/build/tcga-trace-bioinformatics-supplement.pdf` | Single supplementary upload containing Tables S1-S8 and no figures. |
| Figure 1 vector source | `manuscript/bioinformatics_app_note/figures/graphical_abstract.tex` | Complete reproducible TikZ source for Figure 1. |
| Figure 1 alt text | `manuscript/bioinformatics_app_note/figures/figure_alt_text.md` | Accessibility description for Figure 1. |
| Interface analysis screenshot | `manuscript/bioinformatics_app_note/figures/tcga_trace_ui_analysis.png` | Optional reviewer aid showing a completed LIHC/CDC20 analysis; not included as a supplementary figure. |
| Interface multiverse screenshot | `manuscript/bioinformatics_app_note/figures/tcga_trace_ui_multiverse.png` | Optional reviewer aid showing the declared family, separate multiplicity families, specification curve and ledger; not included as a supplementary figure. |
| Supplement | `manuscript/bioinformatics_app_note/supplementary.tex` | Supplementary comparator and benchmark details. |
| Main benchmark tables | `manuscript/bioinformatics_app_note/tables/` | Generated LaTeX tables used by manuscript and supplement. |
| Build instructions | `manuscript/bioinformatics_app_note/README.md` | Manuscript build and journal-constraint notes. |
| Methods changelog | `CHANGELOG.md` | Functional and methodological version history for the application. |

Generated PDFs are intentionally ignored by git. Rebuild all three and run the
technical editorial gate with:

```sh
make -C manuscript/bioinformatics_app_note clean compliance
```

## Submission Support Files

| Artifact | Path | Purpose |
| --- | --- | --- |
| Readiness checklist | `manuscript/bioinformatics_app_note/submission/submission_readiness_checklist.md` | Go/no-go checklist against Bioinformatics requirements. |
| Reviewer quickstart | `REVIEWER_QUICKSTART.md` | Short root-level entry point for reviewers. |
| Cover letter draft | `manuscript/bioinformatics_app_note/submission/cover_letter_draft.md` | Editable cover letter whose owner placeholders are filled by `apply_submission_metadata.py`. |
| Anticipated reviewer response map | `manuscript/bioinformatics_app_note/submission/anticipated_reviewer_response.md` | Draft response map for likely method/software/genomics reviewer objections. |
| Reviewer guide | `manuscript/bioinformatics_app_note/submission/reviewer_reproduction_guide.md` | End-to-end reproduction instructions for reviewers. |
| Reviewer walkthrough | `manuscript/bioinformatics_app_note/submission/reviewer_walkthrough.md` | Short reviewer-facing guide to the visible web interface and expected outputs. |
| Reviewer access statement | `manuscript/bioinformatics_app_note/submission/reviewer_access_statement.md` | Public web instance plus Docker fallback reviewer access wording. |
| Data availability statement | `manuscript/bioinformatics_app_note/submission/data_availability_statement.md` | Prepared data availability wording for manuscript and submission forms. |
| Release and license checklist | `manuscript/bioinformatics_app_note/submission/release_and_license_checklist.md` | Owner-controlled license, repository, release-tag and DOI steps. |
| Browser compatibility record | `manuscript/bioinformatics_app_note/submission/browser_compatibility_record.md` | Generated Chromium, Gecko and WebKit smoke-test evidence; provisional results pass and final tagged-HTTPS repetition remains required. |
| CLI guide | `docs/CLI.md` | English submit, poll, download and bundle-verification workflow for the public REST v1 contract. |
| CLI guide (Spanish) | `docs/CLI_ES.md` | Spanish command-line workflow and integrity-scope explanation. |
| CI workflow | `.github/workflows/ci.yml` | Backend, publication, CLI and frontend tests plus identity and production-build checks without local TCGA data. |
| Secret-scanning policy | `.gitleaks.toml` | Default Gitleaks rules with two line-specific false-positive exclusions and no excluded source paths. |
| Release-readiness workflow | `.github/workflows/release-readiness.yml` | Exact-tag gate that binds the deployed commit to browser evidence, owner metadata, manuscript compliance and the verified archive. |
| Artifact manifest | `manuscript/bioinformatics_app_note/submission/artifact_manifest.md` | This file. |
| Final decision tracker | `manuscript/bioinformatics_app_note/submission/final_submission_decisions.md` | Owner-provided metadata and availability decisions required before submission. |
| Owner metadata template | `manuscript/bioinformatics_app_note/submission/owner_metadata.template.json` | Fillable JSON for final authorship, availability, funding and COI values. |

## Benchmark Evidence

| Artifact | Path | Purpose |
| --- | --- | --- |
| Benchmark README | `docs/publication/benchmark/README.md` | Benchmark reproduction and interpretation. |
| Single-gene overview | `docs/publication/benchmark/single_gene_benchmark_overview.md` | Aggregate cutpoint-sensitivity result. |
| Benchmark revision log | `docs/publication/benchmark_revision_log.md` | Decision record for benchmark selection and manuscript evidence. |
| SKCM TMEM176B benchmark | `docs/publication/benchmark/skcm_tmem176b_os_cutpoint_benchmark/summary.md` | Literature-prioritized exploratory SKCM immune-regulatory cutpoint benchmark. |
| Feature overview | `docs/publication/benchmark/feature_benchmarks/feature_benchmark_summary.md` | ACC weighted, UVM crossed-marker and BIRC5 pan-cancer primary plus ordinal-sensitivity result. |
| Feature diagnostics | `docs/publication/benchmark/feature_benchmarks/feature_diagnostic_summary.md` | Preserved hypoxia, immune-interaction and CA9 pan-cancer attenuation cases. |
| Feature signature definitions | `docs/publication/benchmark/feature_benchmarks/signature_definitions.md` | Gene membership, score construction and rationale for feature benchmarks. |
| ImmPort atlas v2.1 | `docs/publication/benchmark/immune_pancancer_atlas_v2_1/` | Compact 3,118-gene model-family, selected-sensitivity and audit record. |
| ImmPort atlas table | `manuscript/bioinformatics_app_note/tables/immune_pancancer_atlas_model_summary.tex` | Archived scale-test table with family-specific FDR, meta-FDR, PH and recurrence counts; not included in the submitted supplement. |
| Data snapshot manifest | `docs/publication/benchmark/data_snapshot_manifest.json` | Local TCGA/CDR/cache input manifest with count-matrix hashes. |
| Audit reconstruction benchmark | `docs/publication/benchmark/reproducibility_benchmark/summary.md` | Three-class integrity, score-reconstruction, deterministic R re-execution and tamper-detection record. |
| Clean-container reconstruction | `docs/publication/benchmark/clean_container_reproduction/` | Three standalone R capsules, 6/6 cross-architecture reruns, two clean negative controls and checksum manifest. |
| Statistical calibration | `docs/publication/benchmark/statistical_calibration/` | Prespecified design, 10,000 replicate-level permutation/simulation records, source hashes, rejection summaries and checksum manifest. |
| Runtime and concurrency | `docs/publication/benchmark/runtime_concurrency/` | Public-API timings, queue/compute intervals, observed Docker cgroup memory, hardware, service limits and checksum manifest. |
| Browser compatibility | `docs/publication/benchmark/browser_compatibility/` | Per-engine checks, versions, timings and checksums for the generated UI compatibility contract. |
| SKCM sample-type sensitivity | `docs/publication/benchmark/skcm_sample_rule_sensitivity/README.md` | PDCD1/SKCM primary-versus-metastatic sensitivity record. |
| SKCM TMEM176B sample-type sensitivity | `docs/publication/benchmark/skcm_tmem176b_sample_rule_sensitivity/README.md` | TMEM176B/SKCM primary-versus-metastatic sensitivity record. |
| Validation candidate register | `docs/publication/validation_candidate_register.md` | Literature-prioritized validation and exploratory candidate screen. |
| Comparator matrix | `docs/publication/comparator_matrix.md` | Literature-backed positioning against existing tools. |
| Concordance validation plan | `docs/publication/concordance_validation_plan.md` | Manual external-tool comparison template required before submission. |
| External concordance record | `docs/publication/external_concordance_kmplotter_ca9_kirc.md` | KM Plotter CA9/KIRC OS directional concordance record. |
| Publication readiness | `docs/BIOINFORMATICS_PUBLICATION_READINESS.md` | Critical gap analysis and submission gates. |
| Strategy document | `docs/publication/bioinformatics_app_note_strategy.md` | Bioinformatics Application Note narrative and benchmark strategy. |
| Writing blueprint | `docs/publication/application_note_writing_blueprint.md` | Structural model derived from the published GRNContext Application Note, current Bioinformatics rules, Nature readability guidance and REMARK. |

## Reproduction Scripts

| Script | Purpose |
| --- | --- |
| `scripts/publication/run_cutpoint_benchmark.py` | Runs one marker-endpoint cutpoint benchmark. |
| `scripts/publication/run_single_gene_benchmark_suite.py` | Runs 11 single-gene endpoint scenarios across four nonredundant cutpoint methods. |
| `scripts/publication/run_feature_benchmarks.py` | Runs three main and three diagnostic advanced-workflow benchmarks. |
| `scripts/publication/run_skcm_sample_rule_sensitivity.py` | Runs gene-configurable SKCM primary-versus-metastatic sample-rule sensitivity checks. |
| `scripts/publication/export_immune_atlas_benchmark.py` | Validates the frozen atlas and exports its compact publication record and LaTeX table. |
| `scripts/publication/export_data_snapshot_manifest.py` | Exports local TCGA/CDR/cache manifest for the benchmark data snapshot. |
| `scripts/publication/verify_reproducibility_bundle.py` | Verifies local run-record hashes, artifact checksums and optional R round-trip. |
| `scripts/verify_server_attestation.py` | Verifies a detached Ed25519 receipt against exact audit bytes and a trusted public-key document. |
| `scripts/publication/run_server_attestation_benchmark.py` | Freezes the signed-report evidence and tests report replacement plus unsigned-digest recomputation. |
| `backend/app/session_history.py` | Resolves selected run events, separates post hoc testing families and builds the signed session bundle. |
| `backend/tests/test_session_history.py` | Covers event deduplication, family isolation, privacy and signed session artifacts. |
| `frontend/src/sessionHistory.js` | Implements opt-in browser-local event recording and the bounded export payload. |
| `frontend/src/sessionHistory.test.js` | Covers lifecycle updates, the 200-event limit and payload privacy. |
| `scripts/tcga_trace_cli.py` | Checks OpenAPI; submits, polls and downloads every public compute family; verifies retained bundles. |
| `scripts/tests/test_tcga_trace_cli.py` | Covers all six compute families, URL/root-path behavior, mutation detection and unsafe ZIP controls. |
| `scripts/publication/run_clean_reproduction_benchmark.py` | Rebuilds the pinned R environment and runs frozen capsules without network or application data. |
| `scripts/publication/run_statistical_calibration.py` | Runs, summarizes and verifies the statistical calibration benchmark. |
| `scripts/publication/run_browser_compatibility.py` | Runs and verifies the Chromium, Firefox/Gecko and WebKit functional contract. |
| `scripts/publication/statistical_calibration.R` | Fits the permutation and known-truth simulation models. |
| `scripts/publication/apply_submission_metadata.py` | Applies final owner metadata to the manuscript, supplement, cover letter and decision tracker. |
| `scripts/publication/write_license_template.py` | Writes complete text for an owner-selected common license option. |
| `scripts/publication/finalize_submission_package.py` | Applies owner metadata, runs the strict gate, builds the final archive and verifies it. |
| `scripts/publication/build_submission_archive.py` | Builds a compact source/reviewer archive excluding full TCGA matrices and derived caches. |
| `scripts/publication/build_oup_preview.py` | Generates the synchronized OUP two-column preview from the canonical manuscript source. |
| `scripts/publication/capture_reviewer_screenshots.py` | Regenerates reviewer-facing interface screenshots from a running TCGA-TRACE stack. |
| `scripts/publication/check_editorial_compliance.py` | Enforces the technical page, abstract, float and alt-text requirements. |
| `scripts/publication/check_submission_artifacts.py` | Verifies the reviewer/submission artifact set and reports file SHA-256 values. |
| `scripts/publication/check_submission_metadata.py` | Reports unresolved owner-controlled submission metadata and can fail in strict mode before upload. |
| `scripts/publication/verify_submission_archive.py` | Verifies required archive contents and rejects local runtime data/caches. |
| `scripts/publication/pre_submission_check.sh` | Runs the full local pre-submission validation gate. |

## Current Submission Blockers

These items require project-owner decisions before journal submission:

- Final author list, affiliations and corresponding-author email.
- Submitting-author ORCID and CRediT contribution statement.
- Funding statement.
- Conflict-of-interest statement.
- Accurate AI-use disclosure after independent author rewrite and scientific
  verification of the assisted draft.
- Complete final software license text as a top-level `LICENSE`/`COPYING` file;
  short stubs and placeholders fail the strict owner-metadata gate.
- Reviewer-accessible or public repository URL.
- Stable archive DOI or release URL.
- Three-year web-service maintenance commitment, named support owner and
  support contact.
- Open-access APC, discount or waiver route.

After these owner-controlled blockers are resolved,
`scripts/publication/finalize_submission_package.py` writes the final compact
archive plus a neighboring `*.summary.json` file containing final PDF/archive
SHA-256 values for upload checks.

## Current Validation Snapshot

Validated on 2026-07-25:

- `make -C manuscript/bioinformatics_app_note clean all` completed.
- Main PDF output:
  `manuscript/bioinformatics_app_note/build/tcga-trace-bioinformatics-application-note.pdf`.
- Supplement PDF output:
  `manuscript/bioinformatics_app_note/build/tcga-trace-bioinformatics-supplement.pdf`.
- Synchronized OUP preview output:
  `manuscript/bioinformatics_app_note/build/tcga-trace-bioinformatics-oup-preview.pdf`.
- The review, supplement and OUP PDFs are 12, 17 and 4 pages, respectively; the
  OUP rendering is within the four-page Application Note limit.
- `texcount -inc -sum` reports sum counts of 1,998 for `main.tex` and 3,283
  across `supplementary.tex` and its included tables; the corresponding
  text-word counts are 1,840 and 2,925.
- The main article contains one integrated vector figure with inline alt text
  and no empirical tables. The supplement contains eight tables and no figures,
  with the complete evidence matrix in Table S4 and all tables preceding the
  bibliography.
- All 17 frozen Paper Examples cases are explicitly identified in the
  manuscript package and linked to their supporting supplementary tables.
- `make -C manuscript/bioinformatics_app_note clean compliance` regenerates all
  three PDFs and runs the technical editorial gate.
- Benchmark, verification, owner-metadata and submission-archive scripts compile with
  `python3 -m py_compile`.
- Owner metadata checker is available; it reports current owner-controlled
  blockers and is intended to pass in strict mode after final metadata,
  complete license text, repository URL and archive DOI edits.
- Backend tests pass in Docker: `138 passed`.
- Publication-script tests pass: `125 passed`.
- Standalone tests pass: `15 passed` (14 CLI plus one attestation verifier).
- Frontend tests pass: `15 passed`; the production Docker build also passes.
- Submission artifact checker reports `109/109` artifacts available.
- The generated TCGA-TRACE review archive passes verification with 480 entries.
- The provisional browser contract passes 24/24 checks across Chromium,
  Firefox/Gecko and WebKit; final tagged-HTTPS repetition remains enforced.
- Data manifest generated with `--hash-count-matrices`: 33 cohorts, zero
  missing count-matrix hashes, stable manifest hash
  `f424cf0ce18199ca291b9a396dd89660c654d049cc9bdeff1bbdcf1b8a0ba094`.
  The stable hash excludes export timestamps, file mtimes and cache timing
  fields.
- The RNA updater sync manifest is recorded as missing in this checkout; the
  publication manifest therefore pins the benchmark matrices by final SHA-256
  hashes.
- Public web application `https://apps.cienciavida.org/tcga_explorer/` returned
  HTTP 200, and `https://apps.cienciavida.org/tcga_explorer/api/v1/health`
  returned app status `ok` and 33 cohorts.
- The current audit-reconstruction benchmark covers three frozen analyses:
  single-gene, weighted-signature and crossed-signature. Internal check counts
  measure coverage within those runs, not independent replications.
- The same exports pass 6/6 clean-capsule reruns on native arm64 and locally
  emulated amd64 under the recorded quantity-aware numeric policy. Integrity
  boundary controls distinguish reproducibility-hash fields, separately
  checksummed artifacts and intentionally unbound report metadata.
- The frozen server-attestation benchmark verifies the exact BAP1/UVM DSS
  audit against an archived Ed25519 public key. Report replacement is rejected,
  and recomputing every unsigned digest in the receipt payload still fails the
  unchanged signature.
- The frozen statistical-calibration benchmark verifies 2,000 observed-cohort
  permutations and four 2,000-replicate known-truth simulations, with
  replicate-level outputs and a checksummed manifest.
- SKCM PDCD1 sample-type sensitivity is recorded under
  `docs/publication/benchmark/skcm_sample_rule_sensitivity/`; its median-split
  BH, adjusted-Cox and diagnostic profile differs by sample rule.
- SKCM TMEM176B sample-type sensitivity is recorded under
  `docs/publication/benchmark/skcm_tmem176b_sample_rule_sensitivity/`; its
  median-split profile likewise differs across all-eligible, primary-only and
  metastatic-only samples.
- SKCM TMEM176B OS is recorded under
  `docs/publication/benchmark/skcm_tmem176b_os_cutpoint_benchmark/`; all four
  method-level BH, Cox, RMST and PH outputs remain available without a composite
  reporting decision.
- External KM Plotter CA9/KIRC OS record is available at
  `docs/publication/external_concordance_kmplotter_ca9_kirc.md`; direction is
  concordant, but the record is not described as an exact replication.
