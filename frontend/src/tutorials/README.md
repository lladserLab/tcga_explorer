# TRACE tutorial system v3.2

The tutorial package is a data-driven learning layer. It can navigate the
workspace and focus registered controls, but it has no API dependency and never
starts an analysis. Module quick guides are explanatory: they never apply a
preset or change scientific controls. Scientific results remain owned by the
application.

All public exports are available from `./tutorials`.

## Video walkthroughs

Only seven module quick guides have reviewed silent recordings in English.
Quick guides appear before learning routes, which remain text-only. Home has a written guide only. `videoRegistry.js` maps
stable guide IDs to versioned files in `public/tutorial-videos/`. `manifest.json`
records source checksums, duration, size and stream metadata. Recordings retain
1080p resolution; JPEG posters are extracted at one second.

Home links to the video guide library without an embedded video. The library,
module entry actions and guide headers expose a shared Watch video button.
It opens a native modal dialog at up to 1120px wide with keyboard focus trapping,
Escape/Close dismissal, focus restoration, native fullscreen and a direct link.
The player mounts only while open, uses `preload="none"`, never autoplays and
unmounts on close. There is no language selector. Written guides remain available
if media fails. Playback does not change analytical controls or guide progress.
Resume opens the saved lesson in the expanded dock, including when the previous
presentation was minimized. Escape in the video dialog closes only the video.

The seven current cuts add approximately 315 MiB to the application, not to its JavaScript
bundle or initial page transfer. Production Nginx serves versioned media with
immutable caching, byte-range support and a real 404 for missing assets.
Keep these files in deployment build contexts. When replacing a recording,
use a new versioned filename and update its registry entry and manifest.

## User journey

Module quick guides open directly on page 1 and use a deliberately simple
presentation:

1. stable step IDs — one page per visible subsection, showing **What to do** and
   **Why this matters**;
2. **Question this analysis answers** — the scientific purpose in plain English;
3. **Limitations** — boundaries relevant to the current page, not a generic
   warning repeated at the end;
4. **Bibliographic references** — one resolved citation list, never duplicated
   in evidence or completion blocks;
5. final interpretation page — explains how to read the module's evidence as a
   whole and what it cannot establish;
6. `complete` — reached by advancing from the final page.

Guides do not render checkpoints, **Reviewed** confirmations, answer choices,
reveal controls or self-certification prompts. Scientific context is visible at
the point of use instead of being hidden behind an additional onboarding step.

Full learning routes and fixed synthetic cases may retain a contextual
introduction and immutable teaching evidence. A fixed case states the supported
conclusion as prose; it does not turn interpretation into a quiz.

Completion means that the user reached the end of the guide. It never depends on
statistical significance, a favorable direction, a result capability or a
confirmation action.
For a completed quick guide, **Review guide** returns directly to page 1.

Quick guides mirror the guide-enabled analytic modules instead of forcing every
workspace page into the same generic sequence. Each represented subsection has
exactly one help page, in the same order as the workspace, followed by exactly
one final interpretation page. The final page explains how to combine the
module's evidence and limits; it is not an extra control subsection.

Guides, External cohorts, Dataset, API & MCP and Methods are
reference or library pages and intentionally have no contextual quick guide.
Guides hosts the cross-module routes and practical manuals.
Legacy fixed-case records remain in the runtime only so saved versioned links
and their checksums continue to resolve; they are not listed in the interface.

| Module | Visible subsections represented by help pages | Final page | Total |
| --- | --- | --- | ---: |
| Home | Orientation · Workspace · Reproducibility foundation | Interpretation | 4 |
| Survival | Data · Marker design · Outcome · Clinical design · Review & run | Interpretation | 6 |
| Compare | Dataset · Markers · Methods · Clinical · Review & run | Interpretation | 6 |
| Expression | Dataset · Genes · Groups · Test family | Interpretation | 5 |
| GSEA | Dataset · Groups · Gene sets and ranking | Interpretation | 4 |
| Robustness | Dataset · Marker · Decisions · Clinical · Review & run | Interpretation | 6 |
| Run history | Setup · Recorded-run ledger | Interpretation | 3 |
| Pan-cancer | Analysis mode · Design · Eligibility preflight | Interpretation | 4 |

The structural mapping lives in `QUICK_GUIDE_STEP_CONTRACTS`; counts are derived
from it through `QUICK_GUIDE_STEP_COUNTS`. This is an internal implementation
contract for IDs, anchors and optional `workspaceStepId` values, not a label
shown to users.
For example, `quick-analysis` has six lessons: five visible Survival workflow
stages and the completed-result interpretation. Its stable lesson IDs and
targets are:

| Lesson ID | Visible Survival stage or evidence | Anchor | `workspaceStepId` |
| --- | --- | --- | --- |
| `data` | Data | `survival.dataset` | `data` |
| `marker` | Marker design | `survival.marker` | `design` |
| `outcome` | Outcome and secondary grouping | `survival.outcome` | `outcome` |
| `clinical` | Clinical design | `survival.clinical` | `clinical` |
| `review-run` | Review & run | `survival.review` | `review` |
| `interpret` | Completed result and its interpretation | `survival.results` | — |

Moving among the first five lessons activates the matching workspace stage.
The interpretation page has the blocking `survival.resultAvailable` requirement, so
the page explains that result evidence is missing when no run is available. The
requirement does not block reading, navigation or completion.

Canonical URLs use stable lesson IDs:

```text
?view=gsea&guide=groups-to-pathways&lesson=primary-evidence&tab=tutorials
```

Quick guides use a step ID or `complete`. An existing quick-guide URL with
`lesson=overview` resolves to page 1. Full learning routes and fixed cases may
retain `overview` for their introduction. Legacy `step=<number>` links remain
readable, but new links are written with `lesson` so editorial reordering does
not silently change their meaning. `lang` is not part of canonical state.
Legacy URLs containing `lang=en` or `lang=es` load the English guide and are
rewritten without `lang`, preserving unrelated query parameters and the hash.

## Evidence source and tutorial mode

`sourceKind` is a scientific provenance statement and is independent from the
visible localized label:

| `sourceKind` | Meaning | Required provenance |
| --- | --- | --- |
| `live` | The user interprets the current workspace and may run a new analysis. | Current dataset, parameters, versions and exported audit artifacts. |
| `synthetic_case` | Immutable invented values for teaching. It is not a computed cohort result. | Public JSON with `source_kind`, `status: not_a_computed_analysis_result`, answer key, version and verified SHA-256. |
| `computed_benchmark` | An immutable result actually produced by a declared pipeline. | Result ID, pipeline version, snapshot, inputs and verified SHA-256. Never label a hand-authored case this way. |

The current fixed practice cases use `synthetic_case`. Computed paper examples
remain distinct. Fixed content cannot apply a live preset or enter Run history.

`mode` controls behavior:

- `live`: last-page and guide-completion progress may be persisted;
- `fixed`: the case is explanatory and does not write tutorial progress.

## Controller and navigation

Create one controller for the application lifetime:

```jsx
const tutorials = useTutorialController({
  onViewChange: setActivePage,
});
```

Normal application navigation must update the tutorial URL without closing the
guide:

```jsx
function navigateToPage(page) {
  setActivePage(page);
  tutorials.setView(page);
}
```

`setView(page)` applies contextual synchronization:

- if a module quick guide is open and `page` changes, it replaces the active
  guide with the registered `quick-<page>` guide and opens its first page;
- if the dock is closed, it updates the application view but does not open a
  guide;
- full learning routes and fixed teaching cases keep their guide identity when
  their own lesson navigation changes `view`, because cross-module movement can
  be part of their intended teaching sequence.

This synchronization changes tutorial navigation only. It does not restore a
saved destination lesson, mutate a scientific control or submit an analysis.

Render the Learning center where the Guides workspace lives:

```jsx
<TutorialLibrary
  controller={tutorials}
  onPrint={() => window.print()}
/>
```

Render one non-modal dock near the application root. It is always a floating
overlay, never a rail or an embedded workspace column. It does not trap focus
and does not use dialog semantics:

```jsx
<TutorialDock
  controller={tutorials}
  capabilities={tutorialCapabilities}
  onNavigate={navigateToPage}
  onApplyPreset={applyTutorialPreset}
/>
```

Opening from a Learn trigger moves focus to the dock heading. `Escape` closes
the dock and restores the trigger when possible. The explicit `auto`/`mini`
choice is a preference. Both states remain fixed overlays and never resize the
workspace.

## Requirements and capabilities

Curriculum data never closes over application state. A step declares a
serializable requirement:

```js
{
  id: "survival.resultAvailable",
  capability: "survival.resultAvailable",
  blocking: true,
}
```

The integration reduces current application state to privacy-safe booleans and
passes that map to the dock:

```js
const tutorialCapabilities = {
  "dataset.catalogAvailable": Boolean(cohorts.length),
  "survival.resultAvailable": Boolean(analysisResults),
  "expression.groupsAvailable": Boolean(expressionGroupsReady),
  "expression.resultAvailable": Boolean(expressionComparisonResult),
  "gsea.resultAvailable": Boolean(gseaResult),
  "session.runsAvailable": sessionRuns.length > 0,
  "repository.catalogAvailable": Boolean(repositoryDatasets),
  "pancancer.tcgaResultAvailable": Boolean(panCancerResult),
  "pancancer.hierarchicalUniverseAvailable": Boolean(hierarchicalPreflight),
  "pancancer.hierarchicalResultAvailable": Boolean(hierarchicalResult),
  "api.publicAvailable": Boolean(health),
};
```

`evaluateTutorialRequirements(requirements, capabilities)` returns
`{ available, missing, missingIds }`. Capability maps must never contain result
payloads, patient identifiers or functions. Missing requirements explain what
the workspace needs; they do not fabricate evidence. Requirements are
informational even if a legacy declaration contains `blocking: true`: the page
remains readable, navigable and completable.

## Internal scientific specifications, concepts and citations

Every guide and step resolves a stable internal `scientificContractId`. In the
quick-guide interface, the relevant content is presented with three direct
labels: **Question this analysis answers**, **Limitations** and **Bibliographic
references**. The phrase “scientific contract” is not used as a visible label.
The internal specification declares:

- scientific question and unit of analysis;
- estimand or decision target;
- reference and effect scale;
- inferential role and multiplicity boundary;
- assumptions, diagnostics and claims that cannot be made;
- stable concept and citation IDs.

`scientificContracts.js` is the only specification registry in code.
`conceptRegistry.js` owns stable terms and definitions.
`citationRegistry.js` owns bibliographic records and DOI metadata. Curriculum
copy references these IDs; it must not duplicate identifiers. References render
once in the active guide page, not again in evidence, notes or completion.

Pan-cancer specifications are intentionally separate:

- `pancancer.mode_aware`: the floating quick guide shared by both Pan-cancer
  modes; it keeps TCGA reference, hierarchical synthesis and the precomputed
  immune-atlas output on their own units and inferential levels;
- `pancancer.tcga_reference`: cancer-specific Cox associations shown on two
  explicit views: **+1 common input-score unit** when transportable and
  synthesis-eligible, and descriptive **+1 within-cancer expression SD**;
  patients remain stratified by TCGA cancer and only the common-unit view may
  show a pooled estimate;
- `pancancer.hierarchical`: study-specific Cox HR per **+1 within-study
  expression IQR**, followed by study → cancer → global synthesis using REML,
  modified HKSJ inference and a 95% prediction interval when estimable.

Never transfer either TCGA reference scale into the hierarchical +1 IQR
synthesis or describe a pooled estimate as universal.

## Informational flow and completion

Steps are informational records. The final curriculum model must not contain a
`checkpoint`, answer option, review ID or reveal payload. Completion is a normal
navigation transition after the final page; the controller does not inspect a
set of confirmations or an answer state.

Synthetic cases still render their versioned `scenario` as readable evidence.
The supported conclusion, assumptions and limits are prose derived from that
artifact. The public JSON and SHA-256 remain available for independent
verification.

Internal objectives may remain linked through `objectiveIds` for curriculum QA,
but they are not completion requirements and are not surfaced as an extra
**Begin guide** or prerequisite page.

## Persistence and preferences

Progress and preferences are separate privacy boundaries.

`trace-learning-progress-v3` stores only live guides:

```js
{
  schemaVersion: 3,
  activeGuideId,
  guides: {
    [guideId]: {
      contentVersion,
      lastStepId,
      status: "in_progress" | "completed",
    },
  },
}
```

It never stores language, presentation, answers, dataset values, result
payloads, private identifiers or timestamps. Valid live progress from v1/v2 is
migrated to v3 using stable guide and step IDs; fixed cases are not migrated.

`trace-learning-preferences-v2` stores only:

```js
{ schemaVersion: 2, presentation: "auto" | "mini" }
```

Guides are English-only. There is no language preference or selector. A legacy
v1 preference migrates only its valid presentation value. Presentation does not
alter scientific state or progress.
If browser storage is blocked or a write fails, progress continues ephemerally
in memory and the dock warns that a reload will discard it.

## Presets and anchors

Quick guides never have a guide-level or lesson-level preset. They explain the
controls and results already present in the current workspace. Optional full
learning routes may attach a local preset to a lesson when a reproducible
exercise requires it; that capability remains separate from module help and
never runs an analysis automatically.

Every target panel uses a registered semantic anchor:

```jsx
<GuideAnchor anchor={GUIDE_ANCHORS.GSEA_RESULTS} label="GSEA results">
  <GseaResult />
</GuideAnchor>
```

Anchor IDs are language-neutral contracts in `catalog.js`. Unknown or unnamed
anchors must fail tests.

## Adding or changing a guide without drift

1. Decide whether the work is a route, quick guide, synthetic case, manual or
   computed benchmark. For a quick guide, inventory the module's visible
   subsections and create one ordered page for each, followed by one
   interpretation page. Register that exact shape in
   `QUICK_GUIDE_STEP_CONTRACTS`. Do not repurpose an existing stable ID.
2. If a workspace module is new, add it once to `src/moduleRegistry.js` and make
   an explicit `showLearnAction` decision. A false value means no trigger, no
   quick-guide catalog entry and no contextual guide when the page is entered.
   Navigation still includes the page.
3. Register new anchors, source provenance and acyclic continuations in
   `catalog.js`; continuation IDs do not belong in visible copy.
4. Add or reuse an internal scientific specification in
   `scientificContracts.js`. Surface its question, relevant limitations and
   citations under the human labels documented above. Register concepts and
   citations centrally before referencing their IDs.
5. Author one English definition. Keep tutorial IDs, step IDs, anchors,
   specification IDs, concepts, citations and capability requirements stable and
   language-neutral. Do not add locale state or a language selector.
6. Keep each quick page to one idea: a short action and why it matters. Include
   the scientific question, page-specific limitations and one reference list.
   Never add a checkpoint, review prompt, answer reveal or completion gate.
7. For a synthetic case, create the public JSON and answer key first, compute its
   SHA-256, then register provenance. Keep synthetic numbers out of locale prose
   so the artifact remains the single source of truth.
8. Register any preset in `presets.js`, keep it local-only and verify that all
   changed result scopes are cleared. If applying it after the first lesson
   would erase evidence, attach it to that lesson rather than to the tutorial.
9. Bump `TUTORIAL_CONTENT_VERSION` when meaning, step identity or interpretation
   boundaries change. Copy-only punctuation fixes do not require invalidating
   progress.

## Review and QA gate

Every release requires:

- scientific review by a method owner for estimand, scale, reference,
  multiplicity, assumptions and interpretation limits;
- editorial review for plain English and relevance to a biological analyst;
- provenance review for every synthetic or computed artifact and hash;
- keyboard, focus, reduced-motion, 200% zoom and screen-reader checks;
- representative viewport checks at 320, 390, 1280 and 1600 px;
- automated specification, URL, progress, component and anchor tests;
- contextual navigation tests proving that an open quick guide switches to the
  destination page on page 1, a closed dock remains closed, and cross-module
  routes and fixed cases keep their identity.

Run from `frontend/`:

```bash
npm test -- --run src/tutorials
npm run build
npm run test:e2e
```

`validateAllCurricula()` must return an empty array. Tests must also prove
English-only URL and preference behavior, absence of checkpoint UI, resolvable
references, acyclic continuations, registered presets, verified artifact hashes
and separation of the two pan-cancer effect scales. The curriculum specification
compares all eight quick guides against their complete ordered ID/anchor/workspace
shape and rejects count drift. Component tests verify that the scientific
question and limitations are visible and that references are not duplicated.
Integration tests also verify that workflow help pages activate the matching
Survival, Compare and Robustness panels without executing an analysis. They also
verify contextual manual page changes without replacing intentional
cross-module route or fixed-case navigation.
