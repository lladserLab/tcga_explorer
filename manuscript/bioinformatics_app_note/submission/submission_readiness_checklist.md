# Bioinformatics Application Note Submission Checklist

Status date: 2026-07-22.

Target article type: Bioinformatics Application Note.

Official constraints checked:

- Bioinformatics submission page: Application Notes should fit approximately
  2,600 words, or 2,000 words plus one figure.
  Source: https://academic.oup.com/bioinformatics/pages/submission_online
- Initial submissions may be PDF or LaTeX source, with line numbers, double
  spacing and at least 12-point font.
  Source: https://academic.oup.com/bioinformatics/pages/submission_online
- Software/data availability and implementation must be stated in the article;
  software or data must be freely available to non-commercial users.
  Source: https://academic.oup.com/bioinformatics/pages/author-guidelines

## Ready

- Main manuscript source: `manuscript/bioinformatics_app_note/main.tex`.
- Main manuscript PDF: `manuscript/bioinformatics_app_note/build/tcga_explorer_bioinformatics_app_note.pdf`.
- Supplement source: `manuscript/bioinformatics_app_note/supplementary.tex`.
- Supplement PDF: `manuscript/bioinformatics_app_note/build/tcga_explorer_bioinformatics_supplement.pdf`.
- One workflow figure is included as reproducible LaTeX/TikZ source:
  `manuscript/bioinformatics_app_note/figures/workflow.tex`.
- Line numbering, double spacing and 12-point manuscript font are enabled.
- Main manuscript is below the Application Note word budget.
- Literature-backed comparator matrix is available in
  `docs/publication/comparator_matrix.md`.
- Reproducible benchmark scripts are available:
  `scripts/publication/run_single_gene_benchmark_suite.py` and
  `scripts/publication/run_feature_benchmarks.py`.
- Benchmark outputs are stored in `docs/publication/benchmark/`.
- Narrative avoids unsupported novelty claims around two-biomarker survival
  interaction and gene-set survival.

## Blocking Before Submission

- Replace placeholder authors, affiliations and corresponding-author email in
  `main.tex`.
- Add funding statement.
- Add conflict-of-interest statement.
- Select and add an explicit open-source license file.
- Confirm repository visibility. Current remote is
  `git@github.com:lladserLab/tcga_explorer.git`; Bioinformatics needs reviewer
  access and post-publication non-commercial availability.
- Decide final public web-demo URL, or state that the Dockerized local app is
  the reviewer-accessible implementation.
- Archive a submission release in Zenodo, Figshare, Software Heritage or an
  equivalent stable repository, and insert the DOI/URL in Availability.
- Confirm whether TCGA source data redistribution restrictions require adding
  a data-availability note that benchmark raw patient exports are generated
  locally and not tracked in git.

## Optional But Strongly Recommended

- Add 2-3 screenshots or a short reviewer walkthrough as supplementary material
  if the journal submission system allows extra files.
- Run one manual comparator example in GEPIA2, cSurvival or DoSurvive and store
  the exact accessed date plus exported numbers, if available.
- Create a tagged release after final author/license edits.
- Run the full verification command before submission:

```sh
python3 -m py_compile scripts/publication/run_cutpoint_benchmark.py scripts/publication/run_single_gene_benchmark_suite.py scripts/publication/run_feature_benchmarks.py
docker compose run --rm --no-deps -v "$PWD/backend/tests:/app/tests:ro" backend pytest -q /app/tests
make -C manuscript/bioinformatics_app_note clean all
git diff --check
```
