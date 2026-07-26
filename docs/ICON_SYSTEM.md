# TCGA-TRACE Icon System

## Purpose

TCGA-TRACE uses icons to reinforce analytical meaning, not to decorate the
interface. The system keeps domain-specific scientific concepts distinct from
familiar interface actions and makes accessibility behavior predictable.

The authoritative implementation is
`frontend/src/design/icons.jsx`. Application code must request a semantic role
from that module instead of importing an SVG library directly.

## Four icon families

### Module icons

Module icons are original TCGA-TRACE drawings. Use them for navigation,
workflow steps and analytical section headings.

Examples:

- `module.dataset`
- `module.geneAnalysis`
- `module.survivalEndpoint`
- `module.rnaScale`
- `module.stratification`
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
<ModuleIcon role="navigation.home" frame="navigation" />
<ModuleIcon role="navigation.panCancer" frame="navigation" />
<ModuleIcon role="navigation.session" frame="navigation" />
```

Scientific frames are limited to:

| Frame | Container | Use |
| --- | ---: | --- |
| `compact` | 28 px | Sidebar status metadata |
| `section` | 36 px | Panel and workflow headings |
| `navigation` | 38 px | Main navigation |

Do not place every inline action or status inside a scientific frame.

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

The five primary workflow icons have stable meanings:

- **Dataset:** A patient-by-variable acquisition matrix. A database cylinder is
  reserved for storage or infrastructure.
- **Gene analysis:** A transcript helix with an analytical acquisition node.
  It must remain distinct from the TCGA-TRACE brand mark.
- **Survival endpoint:** A descending survival step curve with an event mark.
- **RNA expression scale:** A calibrated axis, expression bars and a continuous
  trace. It must not collapse into a generic bar chart.
- **Stratification:** One eligible population branching into analysis groups.
  It must remain distinct from the clinical-filter funnel.
- **Session history:** A chronological acquisition rail connected to separate
  inferential families. It denotes a post hoc run record, not a prespecified
  specification curve.

All custom drawings use a 24 by 24 view box, `currentColor`, round caps and
joins, a 1.65 stroke and a safe area of approximately 3 CSS units.

## Placement rules

- Use one module icon per navigation item, workflow step or major panel header.
- Pair domain icons with visible text.
- Use unframed action icons inside buttons, links, toolbars and dense tables.
- Reserve filled marks for status or plot evidence. Do not mix unrelated filled
  and outline icon styles in one control group.
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
