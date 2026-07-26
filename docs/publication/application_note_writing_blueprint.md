# TCGA-TRACE Application Note Writing Blueprint

Status date: 2026-07-24.

This document defines the editorial model for the TCGA-TRACE manuscript. It is
not a source of text to copy verbatim. The scientific authors must independently
rewrite and verify the final submission.

## Primary Published Example

Primary model:

- Pezoa-Soto et al. `GRNContext: An Interactive Web Platform for
  Contextualized Gene Regulatory Networks Visualization Across Human Cancers`.
  Bioinformatics, 2026, btag389.
  https://doi.org/10.1093/bioinformatics/btag389

GRNContext is a particularly close editorial analogue because it is a 2026
Bioinformatics Applications Note describing a React/FastAPI/Docker web platform
that exposes analyses across the same 33 TCGA cancer types.

Its accepted-manuscript structure is:

1. Short structured abstract with web availability, implementation, contacts
   and archived supplementary/source material.
2. Introduction that moves from biological context to limitations of existing
   resources and then to the target user's unmet need.
3. Methods divided into data, analytical method and web-server implementation.
4. Usage guide followed by descriptive, numbered cases: one recovers
   established relationships and one is presented as hypothesis generation.
5. Future plans, availability, funding, conflict statement and references.
6. One integrated main figure combining the computational workflow with
   platform use; detailed material is placed in the supplement.

## What TCGA-TRACE Should Borrow

- Start the title with the application name and state the scientific function.
- Present one concrete problem, not a catalogue of features.
- Move in the order `context -> gap -> implementation -> evidence -> limits`.
- Describe the audience and the decision the interface helps that audience make.
- Divide methods by reproducible scientific operations rather than frontend
  screens.
- Use a small set of cases to demonstrate different inferential outcomes.
- Keep one main figure that links inputs, analysis, diagnostics and visible
  outputs.
- Put detailed tables, parameter definitions and expanded benchmark results in
  one cited supplement.
- State the public HTTPS service and archived source release in the abstract.

## What TCGA-TRACE Should Not Copy

- The GRNContext accepted manuscript has six numbered manuscript pages. The
  current Bioinformatics limit is four pages, so it is a writing model rather
  than a page-count precedent.
- Its Summary is longer than the current one- or two-sentence instruction for
  Application Notes. TCGA-TRACE must retain exactly two sentences.
- GRNContext is an editorial structure model, not a scientific comparator for
  survival analysis. It should not be cited in the manuscript solely because
  its organization informed this draft.
- Recovering a literature-known association demonstrates a workflow; it does
  not validate a biomarker or establish clinical utility.
- Broad adjectives such as `comprehensive`, `powerful`, `novel` and
  `user-friendly` must be replaced by specific, checkable capabilities.
- Biological background should be limited to what is needed to understand the
  software contribution.

## Required TCGA-TRACE Narrative

### One-sentence problem

Interactive TCGA survival results are difficult to audit when the endpoint,
selected patients, expression transformation, cutpoint and model diagnostics
are not preserved with the reported curve.

### One-sentence response

TCGA-TRACE links endpoint-aware cohort construction to survival estimates,
sensitivity analyses and a server-signed run record that preserves the exact
inputs and outputs.

### Defensible contribution

The contribution is the integrated reporting contract:

- explicit TCGA-CDR endpoint provenance and endpoint QC;
- deterministic one-sample-per-patient construction;
- cutpoint sensitivity rather than a single optimized threshold;
- Cox PH diagnostics and RMST beside conventional KM/log-rank outputs, while
  acknowledging PH testing in PESSA as prior art;
- continuous pan-cancer models with family-specific correction;
- de-identified participant records, exact expression components, source
  identifiers, parameters, versions and checksums exported together;
- executable score reconstruction, statistical re-execution and mutation
  detection demonstrated across three analysis classes;
- a detached Ed25519 receipt that binds the exact audit report to a public key
  archived independently of the exporter.

Two-signature analysis, Kaplan-Meier estimation, Cox regression and gene-set
survival are prior art and must not be framed as first-of-kind methods.

## Target Main-Text Structure

### 1. Introduction

Use three short paragraphs:

1. TCGA survival portals are useful and established.
2. The unresolved gap is traceability and diagnostic context, with the risk of
   outcome-optimized cutpoints stated explicitly.
3. TCGA-TRACE addresses this gap and the paragraph states what the article
   demonstrates.

### 2. Materials and methods

Use three concise subsections:

- `Data and cohort construction`: TCGA RNA, TCGA-CDR endpoints, eligibility,
  sample selection and endpoint QC.
- `Survival analyses`: scores, cutpoints, Cox, PH, RMST, interaction and
  pan-cancer estimands.
- `Web server and run record`: implementation, outputs, versions and hashes.

Technical parameter definitions belong in the supplement and Help/Methods view.

### 3. Case Studies and Evaluation

Use cases should test the reporting contract rather than advertise significant
biomarkers:

- robust across cutpoints: CDC20/LIHC;
- associated but PH-flagged: EMP3/LGG;
- grouped separation without continuous interaction: BAP1/PRAME/UVM;
- pooled pan-cancer association constrained by heterogeneity: BIRC5;
- external direction agreement without exact statistical replication:
  CA9/KIRC.

Use concise declarative titles that identify the analysis or biological
context, following the function of GRNContext headings such as `Case 1: PTTG1
in Liver Hepatocellular Cancer (TCGA-LIHC)` without copying their wording.
TCGA-TRACE uses `Case 1: Analysis Record Reconstruction`, `Case 2: Cutpoint
and PH Sensitivity`, `Case 3: BAP1/PRAME in Uveal Melanoma` and `Case 4:
BIRC5 Across TCGA Cohorts`. Do not phrase subsection titles as questions.
Each case should follow `context -> result -> diagnostic qualification ->
interpretation`.

### 4. Future Plans

State the present scientific boundary before the roadmap: this is exploratory
bulk-TCGA analysis, not independent clinical validation. Distinguish
transparent z-score/weighted signatures from pathway-activity methods such as
ssGSEA, then name concrete next steps. End with the practical contribution,
not a generic claim of impact.

### Back matter

Include Data and Software Availability, CRediT contributions, Acknowledgements
and AI disclosure, Funding and Conflict of Interest. Keep owner-controlled
placeholders explicit until approved.

## Sentence-Level Writing Rules

These rules adapt Nature's readability guidance to the shorter Bioinformatics
format:

- Write for computational biologists outside survival analysis.
- Use one principal claim per sentence.
- Prefer concrete subjects and active verbs.
- Define uncommon abbreviations once and minimize them thereafter.
- Put the main result before implementation detail.
- Separate observations from interpretations.
- Quantify comparisons and report uncertainty or diagnostics with the estimate.
- Avoid causal or clinical language for retrospective observational analyses.
- Use `was not evaluable` for unavailable models and `was not supported` for
  null evidence; do not call either an execution failure.
- Avoid `validates`, `proves`, `superior`, `robust` or `replicates` unless the
  stated design directly supports that word.
- Keep headings short and informative.
- Make the figure legend understandable without reading the main text.

## Reporting Standard For Survival Examples

REMARK is used as a reporting aid, not as a claim that the paper is a clinical
biomarker validation study. The main text or supplement must make available:

- marker/signature definition and whether the hypothesis was prespecified;
- patient source, inclusion/exclusion and sample-selection rules;
- specimen/expression source and transformation;
- endpoint definition, events and follow-up;
- handling of missing data and clinical covariates;
- cutpoint rule and whether it uses the outcome;
- effect estimates, confidence intervals and p-values;
- adjusted analyses and proportional-hazards diagnostics;
- all tested examples, including null or discordant cases; and
- limitations, multiplicity and lack of independent validation.

## Editorial Model Boundary

The published GRNContext Application Note was inspected only as a recent
editorial example of Bioinformatics structure and density. It is not
survival-analysis prior art, a scientific comparator or a citation for the
TCGA-TRACE manuscript.

## Controlling Sources

- Bioinformatics author guidelines:
  https://academic.oup.com/bioinformatics/pages/author-guidelines
- Bioinformatics online submission:
  https://academic.oup.com/bioinformatics/pages/submission_online
- GRNContext published record:
  https://academic.oup.com/bioinformatics/advance-article/doi/10.1093/bioinformatics/btag389/8707839
- Nature Portfolio writing and readability guidance:
  https://www.nature.com/nature-portfolio/for-authors/write
- Nature reporting standards:
  https://www.nature.com/nature/editorial-policies/reporting-standards
- EQUATOR REMARK guidance:
  https://www.equator-network.org/reporting-guidelines/reporting-recommendations-for-tumour-marker-prognostic-studies-remark/
