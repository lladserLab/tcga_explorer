---
name: TRACE Explorer
description: A traceable transcriptomic survival workspace across cohorts and endpoints
colors:
  evidence-cyan: "oklch(43.5% 0.083 218)"
  evidence-ink: "oklch(24% 0.018 252)"
  evidence-ink-strong: "oklch(17% 0.02 252)"
  grid-canvas: "oklch(96.5% 0.006 238)"
  paper-surface: "oklch(99% 0.003 245)"
  instrument-line: "oklch(86% 0.011 240)"
  warning-amber: "oklch(64% 0.13 70)"
  danger-rust: "oklch(49% 0.12 32)"
typography:
  display:
    fontFamily: '"IBM Plex Sans Variable", "IBM Plex Sans", Aptos, ui-sans-serif, system-ui, sans-serif'
    fontSize: "40px"
    fontWeight: 650
    lineHeight: 1.04
    letterSpacing: "0"
  headline:
    fontFamily: '"IBM Plex Sans Variable", "IBM Plex Sans", Aptos, ui-sans-serif, system-ui, sans-serif'
    fontSize: "19px"
    fontWeight: 780
    lineHeight: 1.18
    letterSpacing: "0"
  body:
    fontFamily: '"IBM Plex Sans Variable", "IBM Plex Sans", Aptos, ui-sans-serif, system-ui, sans-serif'
    fontSize: "16px"
    fontWeight: 400
    lineHeight: 1.45
    letterSpacing: "0"
  label:
    fontFamily: '"IBM Plex Sans Variable", "IBM Plex Sans", Aptos, ui-sans-serif, system-ui, sans-serif'
    fontSize: "15px"
    fontWeight: 800
    lineHeight: 1.2
    letterSpacing: "0"
  identifier:
    fontFamily: 'ui-monospace, "SFMono-Regular", Consolas, "Liberation Mono", monospace'
    fontSize: "13px"
    fontWeight: 800
    lineHeight: 1.2
    letterSpacing: "0"
rounded:
  instrument: "4px"
  control: "6px"
  popover: "8px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "12px"
  lg: "16px"
  xl: "20px"
  xxl: "24px"
components:
  button-primary:
    backgroundColor: "{colors.evidence-cyan}"
    textColor: "{colors.paper-surface}"
    typography: "{typography.body}"
    rounded: "{rounded.control}"
    padding: "0 12px"
    height: "44px"
  input:
    backgroundColor: "{colors.paper-surface}"
    textColor: "{colors.evidence-ink-strong}"
    typography: "{typography.body}"
    rounded: "{rounded.control}"
    padding: "9px 11px"
    height: "44px"
  instrument-panel:
    backgroundColor: "{colors.paper-surface}"
    textColor: "{colors.evidence-ink}"
    rounded: "{rounded.instrument}"
    padding: "20px"
---

# Design System: TRACE Explorer

### Home composition

The web-only desktop download section pairs a monochrome GitHub mark with its
source link, using the same central icon registry as the three system marks.
Keep the visible GitHub label and the existing evidence color.

Use a compact TRACE banner with the acronym expansion, a restrained proportional
trace and a short product description. Desktop pairs the primary question-led
analysis chooser with a smaller guide entry at its side. Question choices form
three contiguous disclosure rows; selecting one reveals module names and
explanatory descriptions directly below that question. Module destinations use
flat divided rows within the selected question. Private upload, history and
API/MCP form a quieter action list below the guide entry.

Available public data has a named section with four flat, readable counts and
complete population units. Counts represent releases, patient records and RNA
profiles, never implied unique patients. Keep the institutional footer compact.
At mobile widths, the guide entry and secondary actions follow the analysis choices;
coverage uses two columns. Preserve loading/unavailable states and keyboard
navigation. Home-specific layout lives in `frontend/src/home.css`.

### Optional video guides

Home gives silent video walkthroughs a compact entry below the research-question
choices. Keep the question heading and choices together. Home links to the library
without an embedded video. The library places Quick guides before Learning routes. Only the seven
module quick guides have English videos; routes remain text-only. Every contextual guide uses the
same Watch video dialog with playback controls and a direct link. Video access
appears beside Start/Resume and in the guide header, including mini mode.
Do not autoplay or preload MP4s. Closing releases the player and restores focus;
Escape closes only the video. Resume expands the dock at the saved lesson.
Written guide navigation and analytical settings remain independent of playback.

## Overview

**Creative North Star: "The Traceable Research Instrument"**

TRACE Explorer should feel like a calibrated scientific instrument placed on a
quiet laboratory bench. The gridded paper canvas, journal-like headings,
compact controls and patient-level metrics communicate rigor before decoration.
The interface is dense because the work is dense, but every screen preserves a
clear sequence from setup to evidence to provenance.

Personality comes from a restrained analytical trace: small calibration
corners, one evidence signal color, tabular numerals, scientific icon frames
and brief acquisition motion. The system explicitly rejects generic SaaS dashboards, marketing
composition and theatrical biotechnology imagery.

The T-Trace product mark is the only brand symbol: a T becomes a stepped
analytical path and terminates in a square evidence node. Its geometry remains
unchanged across the interface, favicon, app icon and social thumbnail. The
mark is deliberately simpler than module icons and does not depict a specific
assay, endpoint or cancer type.

**Key Characteristics:**

- Evidence remains the visual foreground.
- One muted evidence color connects every analytical module.
- Structural icons use calibrated frames, acquisition nodes and microtraces.
- Major surfaces are square, quiet and calibrated.
- Motion explains acquisition, location, loading or completion.
- Methodological context stays beside the parameter it affects.

## Colors

The palette combines cool paper neutrals with one low-chroma analytical
channel. Semantic warning and danger colors remain independent.

### Primary

- **Evidence Signal Cyan:** Navigation, selected parameters, focus and
  analytical progress throughout the application.

### Tertiary

- **Warning Amber:** Exploratory-method caveats and incomplete requirements.
- **Danger Rust:** Failed analyses, invalid state and blocking errors.

### Neutral

- **Evidence Ink:** Primary text and data labels.
- **Strong Evidence Ink:** Headings and high-priority values.
- **Grid Canvas:** The technical-paper workspace background.
- **Paper Surface:** Controls, panels and result surfaces.
- **Instrument Line:** Dividers, table rules and input outlines.

### Named Rules

**The One Channel Rule.** One evidence signal color controls navigation,
selection and focus throughout the product. Modules never change the interface
accent.

**The Evidence Rule.** Color may classify state or analytical context. It may
not imply biological significance that is absent from the statistics.

## Typography

**Interface Font:** Self-hosted IBM Plex Sans Variable with Aptos and system UI fallbacks
**Label/Mono Font:** System monospace for compact identifiers only

**Character:** One technical sans carries page titles, controls and dense
tables without splitting the workspace between editorial and application
voices. Monospace is reserved for version strings, cohort codes and pipeline
identifiers.

### Hierarchy

- **Display** (720, 40px, 1.04): Page titles only.
- **Headline** (780, 19px, 1.18): Major panel and workflow headings.
- **Title** (780, 15px, 1.2): Compact result sections and table groups.
- **Body** (400, 16px, 1.55): Descriptions and methodological context, capped
  near 70 characters when prose is continuous.
- **Label** (800, 15px, 1.4): Status and parameter labels. Letter spacing is
  always zero.

### Named Rules

**The Instrument Heading Rule.** Page titles and the product name use the same
sans family as the interface, distinguished by scale and a restrained weight
rather than a separate display face.

**The Stable Number Rule.** Dynamic metrics and numeric table cells always use
tabular numerals.

## Elevation

The system uses structural elevation, not floating decoration. A transparent
one-pixel ring defines the surface, a small near shadow separates adjacent
controls, and a broad low-opacity shadow is reserved for popovers. Dividers
remain real hairline borders because they communicate table and section
structure.

### Shadow Vocabulary

- **Instrument Surface:** A one-pixel translucent ring plus two low-opacity
  depth layers. Use for panels, controls and buttons at rest.
- **Instrument Hover:** A slightly stronger ring and ambient layer. Use only
  under a fine pointer.
- **Anchored Popover:** A stronger ring with broad downward depth. Use only for
  cohort and help popovers.

### Named Rules

**The Calibrated Surface Rule.** Major panels use a restrained 4px corner and
one small calibration corner. Rounded floating cards are forbidden.

**The Flat Data Rule.** Tables, metric strips and evidence matrices stay flat.
Depth is reserved for interaction and layering.

## Components

### Buttons

- **Shape:** Compact instrument control with a 6px radius and a minimum 44px
  height.
- **Primary:** Uses the evidence signal color with high-contrast paper
  text.
- **Hover / Focus:** Hover lift is one pixel and only available to a fine
  pointer. Focus uses a visible two-pixel outline. Press feedback uses
  `scale(0.96)`.
- **Secondary / Tertiary:** Paper surface with a translucent structural shadow
  and signal-colored text.

### Chips

- **Style:** Pale signal tint, compact sans label and a distinct remove icon.
- **State:** Selected parameter controls gain a six-pixel square acquisition
  marker. The marker transitions through opacity, blur and scale without moving
  layout.

### Cards / Containers

- **Corner Style:** Calibrated and nearly square (4px for major panels, 6px for
  compact controls).
- **Background:** Paper surface over the gridded canvas.
- **Shadow Strategy:** Structural surface shadow only.
- **Border:** Hairlines remain for dividers and tables; full borders remain on
  inputs for accessibility.
- **Internal Padding:** 20px on major panels, 12px to 16px on compact groups.

### Inputs / Fields

- **Style:** Paper background, strong instrument-line outline, 6px radius and a
  44px minimum height.
- **Focus:** Evidence-colored outline plus a low-opacity focus ring.
- **Error / Disabled:** Danger remains rust; disabled controls reduce contrast
  and never acquire hover motion.

### Navigation

- **Style:** Dark technical top rail with a subtle coordinate grid. The active
  module uses a contained surface and evidence-colored icon, never an overlapping
  underline or vertical side stripe.
- **Typography:** A 14px technical sans label; descriptions remain available
  through accessible names and tooltips.
- **Desktop:** Home stays adjacent to the product mark. Analytical, evidence and
  reference destinations are grouped in one horizontally scanable rail.
- **Mobile:** Status duplication is removed and navigation becomes a compact
  horizontally scrollable module rail. The active module remains visible with
  its icon and label, while analytical summaries remain keyboard-scrollable.

### Resilience and Continuity

- **Module failure:** A render failure replaces only the current page stage.
  Navigation and the application frame remain usable, with retry and reload
  actions in plain language.
- **Service failure:** Offline, unavailable and partially degraded states are
  distinct. A failed catalog must not erase data that already loaded correctly.
- **Active computation:** Queued and running jobs expose their real server state,
  job identifier and elapsed time. TRACE never invents a percentage. After a
  reload, the result is recovered only when the researcher chooses to open it.
- **Drafts:** Local drafts contain analytical controls only. Results, uploaded
  files, patient identifiers, private clinical levels and external covariate
  tables are excluded.
- **Uploads:** Browser navigation warns when selected local files would be lost.
  File type and size are checked before column mapping begins.

### Scientific Tables

- Every table has an accessible name, column scopes and row scopes where a row
  has a semantic label.
- Scrollable evidence tables retain sticky column headers and, when present, a
  sticky row-label column. The surrounding region is keyboard focusable.
- Sorting is opt-in. It is appropriate for inventories such as the cohort table,
  but prespecified model, sensitivity and evidence-family order remains fixed.
- Small screens may scroll the table, but patient counts, events, effect sizes,
  confidence intervals and multiplicity measures are never hidden.

### External Cohort Catalog

The catalog starts from the researcher decision rather than the storage model.
Cancer types form a compact disclosure list, each expanded cancer reveals only
its matching studies, and technical release provenance remains behind an
explicit detail control. The alternate all-studies view uses 20-row pagination
instead of an unbounded card stream.

Study rows foreground cohort context, patient and event counts, usable
endpoints and the exact expression layer. License terms, manifest hashes,
download controls and full endpoint definitions remain available in the
expanded detail. The catalog never chooses the first study for a cancer
implicitly and does not rank cohorts with an undeclared quality score.

### Scientific Plot Previews

Plot editing uses deterministic simulated data rendered on the same physical
canvas proportions as the R exports. Kaplan-Meier previews include step
functions, censoring marks, confidence bands, p-value placement and an aligned
number-at-risk table. Continuous Cox previews preserve the logarithmic hazard
ratio scale, spline confidence ribbon and median reference. Cox previews mirror
the actual grouped-model table or the multi-signature model-family forest,
including the separate-output arrangement.

Shared plot typography exposes axis values and titles as two compact rows, each
with one point-size field and familiar bold/italic toggles. Plot boundaries use
three visual choices: open, left-and-bottom L axes and a complete box. The
preview must update those choices immediately and the R renderer must consume
the same request fields; a decorative approximation that diverges from the
export is not acceptable.

Font sizes are converted from points into export coordinates, and plot
geometry follows the PNG and SVG dimensions declared by the corresponding R
renderer. Simulation is identified in the interface outside the figure, never
as a watermark inside the scientific canvas. Editing changes presentation
only; the fixed simulated values do not move between style selections.

### Scientific Icons

Structural icons combine familiar scientific glyphs with a quiet tonal frame,
acquisition node and three-bar microtrace. Brand and icon frames do not use
decorative corner brackets. Survival
uses a descending outcome curve; endpoints use a target. Navigation selection
and fine-pointer hover animate only the glyph and microtrace using transform,
opacity and blur.

A structural icon is read at roughly 22 CSS pixels, so the drawing is what has
to survive, not the frame. The glyph is sized as a proportion of its container
rather than a fixed pixel value, so every breakpoint keeps the same optical
weight. Each navigation drawing stays inside a primitive budget and reaches a
single conventional idea: a step curve for survival, two step curves for a
gene-and-cutpoint comparison, box plots for a two-group expression contrast,
an enrichment curve over a hit barcode for gene sets, converging analysis paths
for robustness, a field of cohorts with one in focus for pan-cancer work. The
three-bar microtrace reports navigation selection, so it appears only in
navigation frames where that state exists.

The implementation has four explicit semantic families:

- **Module icons:** Custom TRACE Explorer drawings for datasets, genes, endpoints,
  expression, stratification, model outputs and reproducibility surfaces. Each
  one answers to the panel it sits above rather than to its role name.
  Expression comparison uses two box plots and remains visually distinct from
  both heatmaps and pathway tests. Gene-set enrichment uses a running
  enrichment curve above a hit barcode. Session history uses a clock with a
  return arrow and remains distinct from the prespecified multiverse, which
  shows several analysis paths converging on one estimate. Forest estimates
  carry square markers against a null line, and the pooled diamond belongs to
  the random-effects panel alone.
- **Action icons:** Familiar command glyphs such as download, copy, search,
  previous, next and close. They are never placed in a scientific frame.
- **Status icons:** Success, caution, error, information and loading. Status
  always remains understandable from adjacent text and never relies on color.
- **Plot marks:** Cohort points, confidence intervals, FDR markers and censoring
  symbols belong to the visualization and are not interface icons.

Components request an explicit semantic role from
`frontend/src/design/icons.jsx`. Titles, labels and translated copy must never
select an icon or its tone. Direct `lucide-react` imports outside that registry
are prohibited.

Command glyphs use only `xsm`, `sm`, `md` and `lg`, corresponding to exactly
12, 16, 20 and 24 CSS pixels. Scientific frames use `compact`,
`section` and `navigation`, corresponding to the existing 28, 36 and 38 pixel
containers, each drawing its glyph at 58 percent of that container. Decorative icons are hidden from assistive technology. Meaningful
standalone icons require a label, while icon-only buttons require both an
accessible label and a visible tooltip.

The complete role inventory and contribution rules live in
`docs/ICON_SYSTEM.md`.

### Anchored Popovers

Cohort and help popovers originate from their trigger at `scale(0.97)` and
translate by only four pixels. Their 130ms to 190ms transitions are
interruptible. Cohort menus close on outside pointer input or Escape and return
focus to the trigger.

### Acquisition Motion

Page content enters at 220ms after navigation. Loading signals may loop because
they communicate active computation.
Autocomplete suggestions never animate because they are keyboard-driven and
high frequency. Reduced-motion mode removes positional movement and retains
only gentle opacity feedback.

## Do's and Don'ts

### Do:

- **Do** keep evidence, uncertainty and model diagnostics visible.
- **Do** use exactly one evidence signal color for selection and focus.
- **Do** preserve visible keyboard focus, 40px to 44px targets and WCAG 2.2 AA
  contrast.
- **Do** use tabular numerals in metrics and numeric tables.
- **Do** animate only state, location, acquisition, loading or completion.
- **Do** keep mobile pages free of horizontal overflow at 320px and wider.

### Don't:

- **Don't** turn the app into a generic SaaS dashboard.
- **Don't** use marketing-style hero layouts or landing-page composition.
- **Don't** imitate hospital or electronic-health-record visual language.
- **Don't** use neon genomics aesthetics, decorative gradients or glowing
  biological imagery.
- **Don't** create decorative card grids or cards inside cards.
- **Don't** add gratuitous motion, bounce, elastic easing or animations over
  300ms for ordinary UI state changes.
- **Don't** hide statistical assumptions behind simplified scores.
- **Don't** use color as the only signal of significance, availability or
  failure.
- **Don't** use colored side-stripe borders, gradient text or decorative
  glassmorphism.

### Question-led entry and result navigation (October 2026)

Home starts with three research goals: survival, molecular differences and
cross-study evidence. Selecting a goal reveals relevant module routes; direct
navigation, uploads, history and API/MCP access remain available. The compact
brand banner must leave the research question visible in the first viewport.
Coverage appears below the chooser, with explicit population units.

Results use equal-weight, keyboard-accessible tabs with a named heading per pane.
Continuous, grouped and competing-risk estimands retain their analytical roles
in concise descriptions. Inactive panes stay mounted to preserve controls;
printing includes every pane. Guides reveal the relevant pane before focusing
its evidence. Interpretation notices remain available; tab changes do not alter
requests, estimates, assignments or exports.

At cohort selection, survival workflows report when loaded metadata contains no
standard clinical covariates with usable variation. Loading or failed metadata
must not be mistaken for confirmed absence. The notice explains unadjusted
analysis and patient-matched covariate upload without disabling marker-only
models or claiming the cohort lacks survival outcomes.

### Result copy and progressive detail (October 2026)

Retain the TRACE acronym expansion above the homepage title. Use short questions
and concrete actions in the chooser; scientific copy stays neutral and precise.
A result pane has one heading with its help trigger. View-specific effects and
model counts belong inside that pane, not in a shared header that could be
misread after switching estimands. A selected adjusted model reports its own
complete-case patient and event counts.

The default survival view shows its primary effect and curve. Full fitted-model
tables, curve parameters and grouped Cox/RMST results remain in named native
disclosures. PH flags on the selected model stay visible. RNA source coverage,
scoring records and export choices appear once, without repeating a second
headline. Expression opens with a compact effect table; full descriptive and
inferential statistics remain available in the same pane.

### Cross-cancer setup clarity

Show three TCGA setup decisions: where to look, which gene or signature, and
which outcome. Mode options contain one label and one short explanation.
Synthesis rules and effect-scale distinctions stay in named optional details.
Marker instructions show one short sentence; full scoring help stays available
beside the field. Guide progress explicitly names the guide to distinguish it
from the form's steps.

### Explanations beside decisions

Workspace copy starts with the choice and its consequence for patients or
results. Method details retain named tests and effect units. Descriptions must
match available controls: Expression reports both fixed tests, crossed median
groups need not be balanced, and GSEA distinguishes CAMERA evidence from NES.
Guides use the same visible step names as the workspace.

### Readable copy in action rows and preview grids

Expression action rows reserve width for their paragraph and wrap the run
button when necessary. The desktop button must not inherit 100% width.
Endpoint count notes span the full preview grid rather than the icon column.
Regression checks measure text width at phone, tablet and desktop sizes;
absence of page overflow alone does not establish readable wrapping.

### Comfortable reading on scaled desktop displays

Reading roles live in `frontend/src/readability.css`: instructions and input
values use 16px, controls use 15px, secondary context uses 14px and dense
tables use 13px. Keep plot typography independent. Continuous prose remains
below 72ch. The setup column gains width on large desktops; at smaller widths
the existing stacked layouts remain available. Browser zoom remains supported.

### Anchored help reading

Help uses a 420px maximum reading width with 16px body text and 14px sentence-case
labels above each paragraph. Panels render outside form grids and clipping
containers, remain inside the viewport, and scroll internally when necessary.
Click holds a panel open; Escape and outside clicks dismiss it. The hover close
delay allows moving into the explanation without losing it. Glossary terms use
the same positioning and dismissal behavior.

### Local desktop access on Home

Keep the question-led workspace first. A flat section after public data coverage
explains that local analysis stores datasets and results on the researcher's
computer, with platform-specific downloads. Match the existing
cyan, typography and control sizes. Use monochrome operating-system icons beside platform and architecture labels.
Keep version and file sizes out of this section. Installation details use the shared help registry.
GitHub is a text link; do not turn source access into a second product pitch.
The whole section is absent from native builds, including the GitHub link.

Versioned installers are served from a separate read-only download mount with
range requests and no large proxy buffers. They are not bundled in the web
frontend image. Missing files return 404 rather than the SPA homepage.
