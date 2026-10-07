# In-place help contract

Video player and Home discovery copy lives in `GUIDE_VIDEO_COPY` in the help
registry. The interface and reviewed silent recordings are English only.
Home has a written guide and a link to the video library, without a video. `tutorials/videoRegistry.js` owns asset mappings,
not explanatory copy. Optional Watch video dialogs accompany written guides and
never gate navigation or modify analysis controls.

TRACE Explorer has one source of in-place help: `frontend/src/help/registry.js`.
Nothing else in the interface may declare help copy.

Before this contract existed the same concept was written three to five times —
once in a workspace constant, once in the tutorial curriculum, once on the
Methods page and again in ad-hoc `title` tooltips — and four modules with their
own file (Expression, GSEA, Repository, Pan-cancer) had no in-place help at all,
because the workspace constant was module-local and unreachable from them.

## Layers

| Layer | Component | Answers |
| --- | --- | --- |
| Term | `<Term id="...">` | What does this word mean? |
| Control | `<LabelWithHelp>`, `<FieldWithHelp>`, `<PanelHeader>`, `<SectionHelp>`, `<FieldHelp>` | What does this control do, what changes, what is safe? |
| Section | Module setup headings carrying `helpId`, and `<DesignLedger>` | What is this step for, and what have I decided so far? |
| Result | `<DetailSectionTitle helpId="...">` | How do I read this output? |

Layers nest. They never restate each other: a control entry explains the
control, and any statistical vocabulary inside it is a `Term`.

## The design ledger

`<DesignLedger>` is the section layer for a multi-step module. It reads the
live design and answers three questions at every step, not only at the end:
what is decided, what still blocks a run, and what the result will estimate.

- It sits in the setup column. It is not a dock, never overlays a control, has
  no steps, no progress and nothing to complete.
- Its sentences come from pure functions in `designLedgerContract.js`, so every
  claim a user reads about their own design is unit-tested.
- It reports what the app knows and never invents a derived statistic. Events
  per parameter, for example, is stated as a threshold the fitted model checks,
  because categorical covariates expand into several coefficients.
- Requirement strings are the module's own, reused verbatim; the ledger does
  not paraphrase them.
- Survival uses a compact ledger during setup, with the marker, endpoint,
  adjustment, a short statement of the question and visible blockers. A native
  disclosure retains all other settings and the full estimand. Review shows the
  complete ledger without a second duplicate summary. Both descriptions come
  from the same pure contract. Source endpoint counts are not fitted model N.
- Compare also uses the compact ledger during setup and the full ledger in
  Review. Plot controls are an optional disclosure. Completed results retain
  their submitted source, endpoint, genes and methods; changed or unknown
  recovered settings receive an explicit notice. `compareMultiplicity` explains
  the evaluable grouped-test family, maxstat selection correction, excluded
  unavailable tests and the separate scope of continuous Cox/Cox/RMST.

## Language

Help uses direct English instructions and states what a choice changes for the
patient population, effect or output. Prefer user actions to internal terms:
"study eligibility check", "analysis choices", "analysis record" and "scoring
details". Preserve named methods, effect units, testing families, diagnostics
and source-reported terminology. The October 2026 Humanizer editorial record is
in `docs/publication/experiments/humanizer_full_interface_2026-10-06/`.

`ExpressionDataSelector` shares the **Expression data** control across Survival,
Compare, Robustness, Expression and GSEA. It exposes the selected source note
and verified matrix population beside the control. When a paired-difference
layer is available, the choices distinguish tissue expression from within-patient
change; the selected contrast shows its formula, direction and paired-only
population. Shared explanations live in `expressionDataSource`,
`expressionDataPaired` and `expressionDataCoverage`. Counts never imply fitted
model N, and TCGA scales do not acquire invented layer counts.

In-place help and Guides are **English only**. `<Term>` reads the English
concept registry. Do not reintroduce a language parameter into the help
resolver or guide state; if a second language is added in a future release, it
must be implemented coherently across the whole help system rather than per
call site.

## Entry shape

Every entry fills three slots:

```js
Object.freeze({ term, caption?, does, changes?, safeDefault? })
```

- `does` — what the control does. Required.
- `changes` — what changes in the result when the value changes.
- `safeDefault` — what to choose when unsure.
- `caption` — compact one-line label for dense option grids only.

Slots are rendered as labelled sections, so help is answerable rather than
narrative. Do not concatenate the slots into one paragraph at a call site.

## Rules

- Help identifiers are a contract, like guide anchors and icon roles. An unknown
  identifier throws; it never renders empty.
- Never inline help copy at a call site. `helpId` is the supported prop; the
  `help` child remains only for a value-dependent sentence that cannot be
  precomputed.
- Compose several entries with `helpId={["a", "b"]}` instead of joining strings.
- Statistical vocabulary lives once, in `frontend/src/tutorials/conceptRegistry.js`,
  and reaches the workspace only through `<Term>`. Do not restate a definition
  in a help entry.
- Help copy is English. `useHelpText()` returns a stable resolver with no
  language argument.
- A help trigger is a button, and a button is a labelable element. Never nest it
  inside a `<label>`; use `<FieldWithHelp>`, which renders the trigger as a
  sibling of the label and wires `htmlFor`.
- The interactive Methods page is generated from the same registry entries the
  workspace shows in place. Citable static method contracts are generated from
  their versioned scientific source and checked against the runtime API.

## Guides are not gated

A module quick guide is reference help: it can be closed at any point and has
no checkpoint, acknowledgement or scored interaction. Routes and fixed
examples remain separate teaching experiences. Do not add completion gates at
a quick-guide call site.

## Stable method citations

The interactive Methods view and the citable reference have different URLs:

- In-app explanation:
  `https://apps.cienciavida.org/tcga_explorer/?view=help#trace-guide-methods-signature-scoring`
- Static reference:
  `https://apps.cienciavida.org/tcga_explorer/methods/signature-scoring/`

The query must select `view=help` before the fragment identifies the section.
Use the static URL in manuscripts and external documentation because it is
rendered without JavaScript. `docs/methods/signature_scoring.json` is the
authoritative source for its HTML, Markdown and public JSON forms. Regenerate
them with `python3 scripts/build_static_methods.py` and verify drift with
`python3 scripts/build_static_methods.py --check`.

## Synchronization

When the help contract changes, update all of:

- `frontend/src/help/registry.js`
- `frontend/src/help/designLedgerContract.js`
- `frontend/src/help/registry.test.js`
- `frontend/src/help/HelpSurface.test.jsx`
- `frontend/src/help/designLedgerContract.test.js`
- this document

Run `npm test` and `npm run build` in `frontend/` before considering the change
complete.

Pan-cancer inclusion help separates usable patient and outcome-event counts
from the FDR highlighting threshold. The latter does not select cancers or
refit models. Outcome fallback options describe their actual candidate order;
cross-study minimum counts explain deaths and censored follow-up separately.

The full-interface clarity audit in
`docs/publication/experiments/interface_clarity_audit_2026-10-06/` separates
fixed test settings from selectable controls, median crossing from balanced
marginal splits, CAMERA evidence from ranked enrichment, patient filters from
adjustment, and recorded requests from survival events. Formal method names,
units, correction scopes and model requirements remain explicit.

## October 7 help comfort revision

Help and glossary panels share a portaled, fixed-position surface. They stay
inside the viewport, switch above or below their trigger when space permits,
and scroll internally when needed. A short close delay bridges the hover gap.
Click pins the explanation; dismissal suppresses hover reopening until the pointer leaves or the user clicks or focuses again. Another click, Escape or a click outside dismisses
it. Keyboard focus opens help; arrow and Page keys scroll a long explanation.
The reading text is 16px and slot headings are 14px, stacked above their text.
The third slot is labeled “How to use it” so recommendations and interpretation
notes have an honest heading. Humanizer was reapplied to dense entries. Upload
scale conversion help lives beside the file-scale control, separately from
public expression-layer selection. Scientific method names and units remain.

`desktopInstallation` explains local processing, public packages, offline use
after import, platform selection and the signing status of preview installers.
Home displays the concise purpose and download choices; technical installation
context stays in the shared anchored help.
