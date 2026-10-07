# TRACE Explorer learning guide

This guide is the written companion to the in-application **Guides & examples**
workspace. It teaches a defensible analysis sequence; it is not a substitute for
the Methods page, the audit report attached to a result, or domain expertise.

## How guided learning works

TRACE Explorer keeps learning state separate from scientific state. Module help
explains the controls and results already in the workspace; it never loads a
preset, changes a scientific control or submits an analysis. Optional full
learning routes may contain explicit reproducible exercises, but they remain
separate from **Learn this module**.

Module quick guides open directly on page 1 and use a short, predictable
sequence:

1. **Question this analysis answers:** keeps the scientific purpose visible in
   plain language.
2. **What to do and why:** explains the matching workspace subsection without
   changing a control or running an analysis.
3. **Limitations:** states the boundaries that matter for that page, next to the
   instruction rather than behind a self-review task.
4. **Bibliographic references:** lists the supporting methods once, without
   repeating the same citations in evidence and completion blocks.
5. **Interpretation:** the final page explains how to read the result as a whole
   and what it cannot establish.

Contextual quick guides are available for Home and the analytic workspaces:
Survival, Compare, Expression, GSEA, Robustness, Run history and Pan-cancer.
Guides & examples, External cohorts, Dataset, API & MCP and Methods do not show
**Learn this module**. Guides & examples remains the library for full learning
routes, practical manuals and reproducible paper examples.

There are no checkpoints, **Reviewed** buttons, scored answers or completion
gates. The guide is reference help for working scientists, not a course that
asks them to certify that they read each screen.

Closing a guide does not erase live progress. In a quick guide, **Review guide**
returns to page 1 without changing the underlying scientific result.

The floating help also follows manual module navigation. If a module quick guide
is open and the user moves to another application page, the dock replaces it
with that page's quick guide and starts on page 1. This keeps the explanation
aligned with the analysis now on screen. A closed guide stays closed when pages
change; navigation never opens help on the user's behalf.

Full learning routes behave differently because their steps may intentionally
cross modules. When one of their own steps opens another module, the dock keeps
the same route instead of replacing it with a module quick guide.

Every module quick guide follows the visible interface: one help page for each
subsection, in the same order, plus one final interpretation page. This keeps a
short module short and gives a dense module enough room without collapsing
several scientific decisions into generic prose.

| Module | Subsection pages | Interpretation | Total pages |
| --- | ---: | ---: | ---: |
| Home | 3 | 1 | 4 |
| Survival | 5 | 1 | 6 |
| Compare | 5 | 1 | 6 |
| Expression | 4 | 1 | 5 |
| GSEA | 3 | 1 | 4 |
| Robustness | 5 | 1 | 6 |
| Run history | 2 | 1 | 3 |
| Pan-cancer | 3 | 1 | 4 |

For workflow modules, advancing the guide opens the matching workspace panel.
For example, Survival moves through Data, Marker design, Outcome, Clinical
design and Review & run before the result page; Compare and Robustness follow
their own five setup panels in the same way. If a result-dependent page has no
result yet, the guide explains what evidence is missing but remains navigable.
A tutorial never presses **Run analysis** for the learner.

### Know the evidence source

The source badge identifies where the evidence comes from:

- **Current analysis (`live`):** instructions refer to the dataset, controls and
  result currently open. Running remains an explicit user action.
- **Computed benchmark (`computed_benchmark`):** an immutable result actually
  produced by a declared pipeline, with result ID, inputs, version and hash.
  Paper examples use this class; never treat a hand-authored scenario as one.

### Progress and presentation

Only guides in live mode persist progress. The browser stores, per guide, the
content version, last stable step ID and `in_progress`/`completed` status.
Computed examples do not write progress. Dataset values,
result payloads, private identifiers and timestamps are never stored.

Every quick guide reaches `lesson=complete` after the user advances through its
final page. If browser storage is unavailable, live progress continues only in
memory and the dock warns that a reload will discard it.

Guides are available in English only. There is no language selector, language
preference or `lang` parameter in canonical guide URLs. Existing links that
contain `lang=en` or `lang=es` are opened in English and rewritten without that
parameter while preserving the rest of the URL.

`auto`/`mini` controls the dock only; it does not change guide completion or any
analysis. The dock is always a floating overlay and never reserves workspace
width.
Quick-guide deep links use a stable step ID or `lesson=complete`; an existing
quick-guide link with `lesson=overview` resolves to page 1. Full learning routes
may retain `lesson=overview` for their introduction. Legacy numeric step links
remain readable.

### Requirements and the analysis-reading specification

A step may state that a result, eligible grouping, preflight universe or catalog
must exist before its evidence can be inspected. These notices come from a
privacy-safe map of boolean capabilities. They never inspect or persist patient
records and never invent a missing result. Requirements are informational: they
explain what is available or missing without blocking reading, navigation or
completion.

Every guide and page links internally to a scientific specification that
declares the question, unit of analysis, estimand or decision target, reference,
scale, inferential role, multiplicity boundary, assumptions, diagnostics and
claims that cannot be made. The interface translates that internal model into
three direct, human labels: **Question this analysis answers**, **Limitations**
and **Bibliographic references**. “Scientific contract” remains an internal code
name. References resolve from one registry and appear once in the page.

Pan-cancer has two non-interchangeable specifications:

- **TCGA reference:** cancer-specific Cox associations with two explicit views:
  **+1 common input-score unit** when transportable and synthesis-eligible, and
  descriptive **+1 within-cancer expression SD**. Patients remain within their
  TCGA cancer; only the common-unit view may show a pooled estimate.
- **Hierarchical studies:** a study-specific Cox HR per **+1 within-study
  expression IQR**, followed by study → cancer → global synthesis using REML,
  modified HKSJ inference and a 95% prediction interval when estimable.

Do not send either TCGA reference scale into the hierarchical +1 IQR synthesis.
A pooled estimate summarizes compatible evidence; it does not establish a
universal effect.

## Recommended routes

### 1. Understand Survival analysis

Question: how is the marker currently shown in the workspace associated with
time to the selected event in the eligible patients?

The **Learn this module** guide walks through the interface one stage at a time:

1. **Data:** explains which patients can enter, how RNA samples are prioritized
   and what the selected expression scale represents.
2. **Marker design:** explains single genes, signatures, interactions and panels,
   including the +1 SD unit of the primary continuous effect.
3. **Outcome:** explains event definition, time origin and why grouping belongs
   to cutpoint-based KM, grouped Cox and RMST views.
4. **Clinical design:** separates eligibility filters from complete-case
   adjustment and states what adjustment cannot prove.
5. **Review & run:** brings population, marker, endpoint, estimand, grouping,
   filters and adjustment together before the user decides whether to run.
6. **Interpret:** reads patients and events first, then the continuous HR and
   95% CI, diagnostics, supporting grouped views, warnings and downloads.

Do not use a data-driven cutpoint as if it had been prespecified. A small p value
does not establish predictive utility, causality or clinical usefulness. A
hazard ratio is an instantaneous-hazard association, not an absolute survival
difference, death probability or treatment effect.

### 2. Analyze your own data

Start with the `private-quickstart-kirc-log2-v1` synthetic pack from
**Guides & examples → Downloads**.

1. Confirm that the files contain de-identified research data only.
2. Map exact sample identifiers, time, event state, time unit and expression
   scale. A structurally valid mapping can still be semantically wrong.
3. Map fixed covariates and, when present, up to ten custom categorical or
   numeric baseline variables. Inspect coverage and level counts.
4. Variables measured after baseline must not filter a survival risk set.
   Response/outcome variables are descriptive grouping candidates only and carry
   a contextual warning. Expression-derived groups are exploratory because reuse
   of the same signal can create circular inference.
5. Check linked patients, events, censored observations, genes and QC notices.
6. Use the quickstart matrix for Survival, Expression, Compare and Robustness.
   Its 32 genes are not a valid transcriptome background for GSEA.
7. For GSEA, use `private-transcriptome-kirc-gsea-v1` instead.

Private normalized data and generated results expire after 24 hours. Original
uploaded files are discarded after validation.

The `private-upload-validation-lab-v1` pack contains one isolated error per
folder plus semantic traps. Work on one folder at a time. The goal is to explain
the diagnostic, not to force the file through validation. Every case includes a
machine-readable `case.json`, and `cases/index.json` records whether the real
importer must reject it, accept it with a named QC notice, or accept it only
after an analyst has reviewed a semantic trap.

### 3. From groups to genes and pathways

Question: how do expression distributions and coordinated pathways differ
between two traceable patient groups?

1. Define groups from a clinical variable, a saved survival dichotomization or
   one/more genes. Confirm that every sample has one unambiguous assignment.
2. Use **Expression** for selected genes. Inspect violin and box plots, the
   patient-level heatmap and both Welch and Mann-Whitney results with adjusted
   p values.
3. Use **GSEA** only with a broad expression matrix. The ranked statistic is
   Welch group B minus group A; therefore positive NES favors B and negative NES
   favors A.
4. Run GO Biological Process and ImmPort separately. Review tested set sizes,
   permutations, seed, FDR and leading-edge genes.
5. In the GSEA DotPlot, color is NES and point area is proportional to
   `min(-log10(FDR), 10)`. It displays at most the 30 lowest-FDR pathways, so
   inspect the complete table; values below FDR `1e-10` share the visual cap.
6. Do not define groups with a gene and then present that gene or a directly
   derived signature as independent evidence. Label this exploratory/circular.

For the fixed BRCA lesson, stage I+II versus III+IV is the main clinical
contrast. PAM50 subtype is an exploratory multi-level context and is not silently
collapsed into an arbitrary binary comparison.

### 4. Robustness and multiplicity

Question: does the interpretation depend on a particular analytical choice?

1. In **Compare**, examine PDCD1 in TCGA-SKCM across prespecified grouping rules.
2. Treat estimates from the same patients and outcomes as correlated views, not
   independent votes.
3. In **Robustness**, prespecify the CDC20 TCGA-LIHC endpoint, score and cutpoint
   family before running it.
4. Read the robustness curve together with the decision matrix, denominators,
   diagnostics and multiplicity adjustment.
5. Use **Run history** to select the runs that form one exploratory family and
   export that family explicitly.

Robustness is not “how many p values are below 0.05.” Look for effect direction,
uncertainty, support across reasonable specifications and the assumptions that
change between them.

### 5. Validation and generalization

Question: does an association transport beyond one study and cancer context?

1. Use **External cohorts** for a genuinely independent RNA-seq study with a
   compatible endpoint and expression layer.
2. Analyze each study as its own universe; do not pool patient rows from studies
   with different recruitment, measurement and follow-up processes.
3. Use **Pan-cancer → TCGA reference** for the existing cancer-by-cancer TCGA
   analysis. Verify whether the forest is on the synthesis-eligible common unit
   or the descriptive within-cancer SD view.
4. Use **Pan-cancer → Hierarchical studies** for study → cancer → global synthesis.
   Run a current preflight, review eligible and excluded study universes, then
   execute the exact fingerprinted specification.
5. Interpret hierarchical cancer-level and global random-effects summaries with
   modified-HKSJ status, the prediction interval, leave-one-out influence,
   labeled sensitivity contracts and unavailable-study reasons. A global
   estimate does not erase meaningful study or cancer differences.
6. Export source-level effects, exclusions, model diagnostics, data versions and
   audit artifacts. The API exposes the same contracts for scripted reproduction.

## Statistical reading checklist

Before interpreting any figure, answer:

1. What is the estimand and which group/direction is the reference?
2. How many patients and events contributed to this exact model?
3. Was the choice prespecified, descriptive or data-driven?
4. Is uncertainty shown with a confidence interval and an appropriate adjusted
   p value/FDR where multiple hypotheses were tested?
5. Which assumptions or diagnostics limit the interpretation?
6. Is the evidence internal, externally validated or synthesized across studies?
7. Can another analyst reproduce the result from the exported record?

## Tutorial dataset API

The catalog is read-only:

```text
GET /api/v1/tutorial-assets
GET /api/v1/tutorial-assets/{asset_id}
```

Archives are deterministic and include a manifest, recipes, expected QC,
synthetic truth where applicable, and `SHA256SUMS.txt`. They contain no patient
data and tutorial progress is never sent to the server. Archive documentation is
separate from the English-only Guides interface.

## Authoring and scientific QA

This section is for contributors. A tutorial change is a scientific-interface
change and requires the same review discipline as an analysis label.

### Add or change a guide

1. Classify it as a learning route, quick guide, synthetic case, manual or
   computed benchmark. For a quick guide, inventory every visible subsection,
   create one ordered page per subsection and append one interpretation page.
   Register the exact IDs, anchors and optional workspace-panel IDs in
   `QUICK_GUIDE_STEP_CONTRACTS`. Keep existing stable IDs unchanged.
2. If it introduces a workspace module, register the module once in
   `frontend/src/moduleRegistry.js` and explicitly decide whether the module
   shows **Learn this module**. A module with `showLearnAction: false` remains in
   navigation but has no contextual quick guide or quick-guide catalog entry.
3. Register stable anchors, provenance and acyclic recommended continuations in
   `frontend/src/tutorials/catalog.js`. Continuation IDs never belong in locale
   copy.
4. Add or reuse the internal scientific specification in
   `scientificContracts.js`. The interface exposes its scientific question,
   relevant limitations and references with human labels; it never exposes
   “scientific contract” as a heading. Add bibliographic records to
   `citationRegistry.js` before referencing their IDs.
5. Author the guide in English. Keep tutorial IDs, step IDs, anchors,
   specification IDs, citation IDs and capability requirements language-neutral
   and stable. Do not add a language selector or translated runtime copy.
6. Give each quick-guide page one idea, a short action and one reason it matters.
   Show **Question this analysis answers**, page-specific **Limitations** and one
   **Bibliographic references** list. Do not add checkpoints, review
   confirmations, answer reveals or completion gates.
7. Declare requirements as serializable capability IDs, never functions or
   result payloads. Presets must change local controls only, clear stale derived
   results and never call an API. Attach a destructive/resetting preset only to
   the lesson where it belongs; in Survival that is `data`, never the later
   review or interpretation lessons.
8. For a synthetic case, create the public JSON and answer key first; declare
   `source_kind: synthetic_case` and
   `status: not_a_computed_analysis_result`, calculate SHA-256 and register the
   digest. Synthetic numbers stay in the artifact, not duplicated locale prose.
9. Use `computed_benchmark` only when the artifact was actually generated by a
   documented pipeline and its inputs, result ID, version and hash are auditable.
10. Increase `TUTORIAL_CONTENT_VERSION` when step identity, estimand, scale or
    interpretation boundaries change.

### Release gate

Each change needs:

- a method-owner review of estimand, reference, scale, multiplicity, assumptions,
  diagnostics and interpretation limits;
- an editorial review for plain English, biological relevance and consistency
  with the visible workspace;
- provenance and digest verification for every synthetic or computed artifact;
- keyboard, focus restoration, `Escape`, reduced-motion, 200% zoom and
  screen-reader review;
- representative checks at 320, 390, 1280 and 1600 px;
- automated curriculum, scientific-specification, URL, progress, anchor and component
  tests.

Run from `frontend/`:

```bash
npm test -- --run src/tutorials
npm run build
npm run test:e2e
```

`validateAllCurricula()` must return no errors. The automated checks verify
the English curriculum shape, resolvable concepts and citations, registered
presets, acyclic continuations, public artifact hashes and the separation
between the two pan-cancer scales. Tests must also reject checkpoint fields and
legacy language controls in rendered Guides.
