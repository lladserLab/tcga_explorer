# TRACE Explorer Icon System

## Purpose

TRACE Explorer uses icons to reinforce analytical meaning, not to decorate the
interface. The system keeps domain-specific scientific concepts distinct from
familiar interface actions and makes accessibility behavior predictable.

The product mark is not an interface icon. Its canonical source is
`frontend/public/brand/trace-mark.svg`: a T continuing into a stepped
analytical trace and ending in an evidence node. Favicons, app icons and social
thumbnails are generated from that source with `npm run brand:build`; the mark
must never be substituted for a module, action or status role.

The authoritative implementation is
`frontend/src/design/icons.jsx`. Application code must request a semantic role
from that module instead of importing an SVG library directly.

## Four icon families

### Module icons

Module icons are original TRACE Explorer drawings. Use them for navigation,
workflow steps and analytical section headings.

Examples:

- `module.dataset`
- `module.geneAnalysis`
- `module.survivalEndpoint`
- `module.rnaScale`
- `module.stratification`
- `module.expressionComparison`
- `module.geneSetEnrichment`
- `module.sessionHistory`
- `module.clinicalFilters`
- `module.plotOutput`
- `module.panCancerQuery`
- `module.cohortEffects`
- `module.api`
- `module.aiConnectors`
- `module.methods`

Render them with `ModuleIcon`:

```jsx
<ModuleIcon role="module.survivalEndpoint" />
<ModuleIcon role="module.expressionComparison" />
<ModuleIcon role="module.geneSetEnrichment" />
<ModuleIcon role="navigation.home" frame="navigation" />
<ModuleIcon role="navigation.expressionComparison" frame="navigation" />
<ModuleIcon role="navigation.gsea" frame="navigation" />
<ModuleIcon role="navigation.panCancer" frame="navigation" />
<ModuleIcon role="navigation.session" frame="navigation" />
<ModuleIcon role="navigation.repository" frame="navigation" />
```

Scientific frames are limited to:

| Frame | Container | Drawing | Use |
| --- | ---: | ---: | --- |
| `compact` | 28 px | 16 px | Sidebar status metadata |
| `section` | 36 px | 21 px | Panel and workflow headings |
| `navigation` | 38 px | 22 px | Main navigation |

The drawing is sized as 58 percent of its container, so the responsive
navigation and top-bar frames keep the same optical weight instead of shrinking
the drawing into texture. Never set the drawing to a fixed pixel size.

Do not place every inline action or status inside a scientific frame.
Frames use a quiet tonal field and border. They do not add corner brackets or
calibration marks around the scientific drawing. The three signal bars report
navigation selection, so they render only in the `navigation` frame.

### Drawing budget

A framed drawing is read at 16 to 22 CSS pixels. Past roughly ten primitives —
counting every move command in every path plus every shape element — the
strokes stop resolving and the icon reads as texture rather than meaning.

`icons.test.jsx` enforces the budget for every module and navigation role, and
also asserts that no two navigation destinations share a drawing. A drawing that
needs more than ten primitives is describing more than one idea; split the idea
or drop the detail, and do not raise the ceiling.

### Action and data glyphs

Familiar actions and compact data objects use the centralized Lucide registry.
They remain visually quiet and unframed.

Common roles:

- `action.back`, `action.next`, `action.expand`
- `action.run`, `action.configure`
- `action.download`, `action.copy`
- `action.search`, `action.close`
- `action.sidebarOpen`, `action.sidebarClose`
- `data.cohort`, `data.endpoint`, `data.expression`, `data.gene`
- `data.table`, `data.compare`, `data.network`
- `file.csv`, `file.text`, `file.image`, `file.audit`, `file.archive`

Render them with `TraceIcon`:

```jsx
<TraceIcon role="action.download" size="sm" />
<TraceIcon role="data.table" size="md" tone="secondary" />
```

Allowed glyph sizes:

| Size | CSS size | Typical use |
| --- | ---: | --- |
| `xsm` | 12 px | Dense removable tokens |
| `sm` | 16 px | Inline controls and metadata |
| `md` | 20 px | Buttons and compact feedback |
| `lg` | 24 px | Loading and empty-state emphasis |

Numeric icon sizes are not permitted in application JSX.

### Status icons

Status roles are `status.success`, `status.caution`, `status.error`,
`status.info` and `status.loading`.

Use semantic tones only:

- `success` for completed or ready states
- `caution` for a diagnostic limitation that needs review
- `error` for failed execution or unavailable required data
- `accent` or `secondary` for neutral information

Status text remains visible next to the icon. A warning color must not be used
for provenance, ordinary exclusions or an unevaluable auxiliary model unless
the state genuinely requires attention.

### Plot marks

Plot marks are not interface icons. Hazard-ratio points, confidence intervals,
FDR thresholds, cohort nodes, censoring marks and Kaplan-Meier traces stay
inside their chart SVG and retain chart-specific legends and accessible names.

## Accessibility contract

`TraceIcon` and `ModuleIcon` are decorative by default and emit
`aria-hidden="true"`.

Give a standalone meaningful icon a label:

```jsx
<TraceIcon
  role="status.caution"
  tone="caution"
  label="Diagnostic caution"
/>
```

If the parent button or link already has an accessible name, leave the child
icon decorative. Do not label both.

Icon-only actions use `IconButton`:

```jsx
<IconButton
  iconRole="action.close"
  label="Dismiss download status"
/>
```

`IconButton` requires a specific label and exposes the same text as a tooltip by
default. If the action is not obvious without explanation, use a text button
instead.

## Domain icon semantics

Every navigation drawing commits to one conventional idea a reader already
knows from the literature, so the icon carries meaning before the label is read:

| Destination | Drawing | Must not become |
| --- | --- | --- |
| Survival | Axes, a descending Kaplan-Meier step curve, one censoring tick | A transcript helix; survival is an outcome, not a molecule |
| Compare | Two step curves at different levels, no axes | A single curve, which is the Survival mark |
| Expression | Two box plots with visible medians | Violins, which collapse into blobs at 22 px |
| GSEA | A running enrichment curve above a hit barcode | A generic ranked list or a bar chart |
| Robustness | Several analysis paths converging on one estimate | A forest of horizontal whiskers, which reads as sliders |
| Pan-cancer | A field of cohorts with one in focus | A wheel, which reads as a life preserver |
| Run history | A clock with a return arrow | A rail or ladder, which reads as a helix |
| External cohorts | A stored dataset with an inbound arrow | Sliders, which read as settings |
| Dataset | A table with a header row | An abacus |
| Guides | An open book | Two book spines |
| Methods | A document with a folded corner | An open book, which is Guides |

The section drawings answer to the panel they sit above, not to their role name.
Read the panel copy before changing one:

- **Dataset:** A stack of cohorts with one chosen, because the panel asks the
  reader to select one TCGA cancer. A database cylinder is reserved for stored
  or external dataset repositories.
- **Cohort table:** Shares the dataset-inventory table with `navigation.dataset`;
  both name one table of what is loaded.
- **Gene analysis:** A transcript helix with an analytical acquisition node.
  It must remain distinct from the TRACE Explorer brand mark.
- **Survival endpoint:** A descending survival step curve with an event mark.
- **Stratification:** One population cut into a high and a low group. It must
  remain distinct from the clinical-filter funnel, from the cutpoint mark, which
  shows the rule rather than the result, and from the Robustness mark, which
  converges rather than splits.
- **Cutpoint methods:** A threshold standing on a distribution.
- **Specification curve:** Ranked estimates above the decision matrix that
  produced them. Robustness navigation uses the converging-paths mark instead.
- **Forest:** Estimates and intervals against a null line, with square markers,
  so it is a forest and not a row of sliders.
- **Meta-behavior:** The pooled random-effects diamond, which is what separates
  it from the forest.
- **Recurrence:** Counts either side of the null, oriented vertically so the
  direction of effect is the subject.
- **Cohort results:** Primary and adjusted estimates paired on each row. Finding
  an outside cohort is `navigation.repository`, a different idea and drawing.
- **Endpoint coverage:** Filled tracks, because the panel reports how much of
  each endpoint passes QC.
- **Evidence landscape:** Cohorts scattered against the FDR threshold line.
- **Concordance:** Points along the identity line.
- **Age at index:** An hourglass. A clock belongs to run history.
- **AI connectors:** An assistant plugged into the engine. A cross reads as a
  failure, never as a connection.

All custom drawings use a 24 by 24 view box, `currentColor`, round caps and
joins, a 1.65 stroke and a safe area of approximately 3 CSS units.

## Placement rules

- Use one module icon per navigation item, workflow step or major panel header.
- Pair domain icons with visible text.
- Use unframed action icons inside buttons, links, toolbars and dense tables.
- Reserve filled marks for status, plot evidence and recognizable platform
  silhouettes. Platform links pair their system mark with the shared download
  action. Do not mix unrelated icon styles within other control groups.
- Use semantic color tokens. Do not add hex colors to icon JSX.
- Do not infer icon roles from English labels, titles or regular expressions.
- Do not introduce decorative badges or frames around ordinary actions.

## Adding or changing an icon

1. Add or update the role in `frontend/src/design/icons.jsx`.
2. Keep the role semantic. Name what the icon means, not what it resembles.
3. Update the appropriate registry and, for module icons, the workflow drawing.
4. Add the role to this document if it expands the public vocabulary.
5. Update `frontend/src/design/icons.test.jsx`.
6. Run the frontend tests and production build.
7. Inspect navigation, a section heading, compact metadata and reduced-motion
   behavior at desktop and mobile widths.

The registry, tests, this document and `DESIGN.md` must remain synchronized.

## Platform downloads

`platform.windows`, `platform.macos` and `platform.linux` use recognizable,
monochrome silhouettes from Simple Icons 11.15.0 (CC0), stored in the central
registry. They are decorative beside explicit system and architecture labels;
the separate download action remains visible. No platform color is introduced.

`resource.github` uses the monochrome GitHub mark from the same Simple Icons
release beside the visible GitHub link. Its accessible name comes from the link;
the mark is decorative and follows the surrounding text color.
