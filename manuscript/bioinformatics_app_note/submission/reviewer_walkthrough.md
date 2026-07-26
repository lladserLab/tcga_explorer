# Reviewer Walkthrough

Status date: 2026-07-25.

This walkthrough maps the reviewer-visible web application to the manuscript
claims. It is intended as a short interface guide, complementary to the
command-oriented reproduction guide.

## Local App Status Checked

The public web instance is:

```text
https://apps.cienciavida.org/tcga_explorer/
```

The Docker stack was running locally at:

```text
http://localhost:3000/tcga_explorer/
```

Health endpoint checked:

```text
http://localhost:3000/tcga_explorer/api/v1/health
```

Observed status:

- app status: `ok`;
- cohorts: `33`;
- cache status: `ready`;
- cohorts ready: `33`;
- cohorts failed: `0`;
- active analysis pipeline:
  `continuous-user-adjustment-firth-v6.2`;
- active combined-signature pipeline:
  `eligible-score-user-adjustment-firth-v3.4`;
- active multiverse pipeline:
  `prespecified-multiverse-family-v1.1`;
- active pan-cancer pipeline:
  `eligible-score-primary-plus-ordinal-sensitivity-v2.3`.

## Walkthrough 1: Single-Gene Survival Run

Open the `Survival` view. A reviewer can reproduce the single-gene
reconstruction-benchmark scenario
with these visible choices:

| Field | Value |
| --- | --- |
| Cohort | `TCGA-LIHC` |
| Endpoint | `OS` |
| Gene mode | single gene |
| Gene | `CDC20` |
| Expression scale | `log2(TPM + 1)` |
| Stratification | median |
| Sample handling | one prioritized RNA-seq sample per patient |

Expected interface behavior:

- the endpoint selector exposes TCGA-CDR endpoints that pass patient/event QC;
- help popovers explain endpoint provenance, expression scale, stratification,
  RMST, PH diagnostics and audit exports;
- the run result shows a Kaplan-Meier plot, statistical summary, Cox output and
  download controls;
- export controls include patient rows, JSON, methods text, plot images,
  Cox-forest image and audit records.

The reviewer-facing reconstruction record and its selected artifact bundle are:

```text
docs/publication/benchmark/reproducibility_benchmark/summary.md
artifacts/a76ff00590a94be98b45ab97dbf6bfba
```

The verified reproducibility hash is:

```text
dc95801869a2a1263f8e63babe17f2c8e2556443d941fa1b24c981f550226610
```

## Walkthrough 2: Cutpoint Sensitivity

Open the `Compare` view. This view runs a selected cohort, endpoint and
expression scale across multiple genes and cutpoint methods.

Recommended reviewer check:

| Field | Value |
| --- | --- |
| Cohort | `TCGA-SKCM` |
| Endpoint | `OS` |
| Gene | `PDCD1` |
| Expression scale | `log2(TPM + 1)` |
| Cutpoint panel | maxstat, median, upper quartile, outer quartiles, percentile |

Expected interface behavior:

- maxstat is labelled as an optimized exploratory cutpoint;
- the cutpoint evidence map separates BH log-rank, Cox, adjusted Cox, RMST and
  PH checks instead of showing only the most favorable p-value;
- maxstat rows include the corrected maximally selected rank-statistic p-value
  when available;
- all rows remain visible, and marker-term PH cautions are distinguished from
  global model PH diagnostics without a composite pass/fail label.

The corresponding benchmark table is stored at:

```text
docs/publication/benchmark/skcm_pdcd1_os_cutpoint_benchmark/summary.md
manuscript/bioinformatics_app_note/tables/skcm_pdcd1_os_cutpoint_benchmark.tex
```

The SKCM primary/metastatic sensitivity check is stored at:

```text
docs/publication/benchmark/skcm_sample_rule_sensitivity/README.md
docs/publication/benchmark/skcm_tmem176b_sample_rule_sensitivity/README.md
manuscript/bioinformatics_app_note/tables/skcm_sample_rule_sensitivity.tex
manuscript/bioinformatics_app_note/tables/skcm_tmem176b_sample_rule_sensitivity.tex
```

## Walkthrough 3: Prespecified Multiverse

Open `Multiverse` and declare this compact software-contract check:

| Field | Value |
| --- | --- |
| Cohort | `TCGA-LIHC` |
| Endpoint family | `OS` |
| Gene | `CDC20` |
| Scoring | single gene |
| Cutpoint family | median, upper quartile |
| Exact Cox adjustment | age |

Before execution, the review step must report one continuous primary test and
two grouped sensitivities. After execution, every planned cell remains visible
in the ledger with its child analysis and audit links. The result must show
family-specific BH values, a grouped specification curve, RMST with tau,
marker/global PH fields and the explicit absence of a retained/not-retained
rule. The downloadable ZIP contains the result, continuous and grouped CSV
tables, SVG curve, ledger, audit and methodology.

This ledger covers the declared family. It does not claim that unrelated ad hoc
runs elsewhere in the browser were prespecified.

## Walkthrough 4: Pan-Cancer And Paper Examples

Open `Pan-cancer` and run BIRC5 with OS, strict same-endpoint mode and the
default minimums of 10 patients and five events. The reviewer should see two
explicit layers:

- the descriptive continuous Cox effect per within-cohort expression SD, with
  no pooled diamond on that cohort-specific scale;
- the exact effect per +1 common input-score unit and its REML/HKSJ synthesis
  with a 95% prediction interval when endpoint and model family are comparable;
- parallel ordinal stage+grade, stage-only and grade-only sensitivity results,
  with the availability-selected cohort model shown beside the primary effect.

The interface reports family-specific BH-FDR and common-scale REML/HKSJ
summaries. Mixed endpoints, cohort-standardized z-score signatures and
availability-selected mixed model families are never pooled. Missing clinical
covariates appear as neutral `not evaluable` states, whereas genuine model or
proportional-hazards diagnostics remain visible at model level.

Open `Paper examples` to inspect the frozen BIRC5 main example and CA9
diagnostic without rerunning R. BIRC5 demonstrates a positive mean with high
heterogeneity and a prediction interval crossing 1; CA9 demonstrates a small
mean, attenuation and three selected-model direction reversals. Both expose
methods, audit and reproducibility-bundle downloads.

## Walkthrough 5: Methods And Audit Trail

Open the `Methods` view. This page is the interface-level bridge between the
software and the manuscript methods.

Reviewer-visible items to check:

- endpoint source and endpoint QC are described before analysis;
- one-sample-per-patient behavior is documented;
- median, maxstat, quartile and percentile stratification are distinguished;
- RMST tau, PH diagnostics and adjusted Cox are explained as interpretation
  aids rather than novelty claims;
- the methods history records the active pipeline versions.

The same methodological version history is tracked in:

```text
CHANGELOG.md
```

An optional reviewer-facing interface screenshot can be regenerated from a
running local stack with:

```sh
scripts/publication/capture_reviewer_screenshots.py
```

## Walkthrough 6: Reviewer Evidence Files

For a fast review without re-running all benchmark analyses, inspect:

```text
REVIEWER_QUICKSTART.md
manuscript/bioinformatics_app_note/submission/reviewer_reproduction_guide.md
manuscript/bioinformatics_app_note/submission/anticipated_reviewer_response.md
docs/publication/benchmark/data_snapshot_manifest.json
docs/publication/external_concordance_kmplotter_ca9_kirc.md
```

These files connect the visible interface to the manuscript claims about
endpoint provenance, model diagnostics, cutpoint sensitivity, external
concordance and run-bundle reproducibility.
