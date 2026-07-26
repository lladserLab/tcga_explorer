---
name: TCGA-TRACE
description: A traceable TCGA RNA survival research workspace
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
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.45
    letterSpacing: "0"
  label:
    fontFamily: '"IBM Plex Sans Variable", "IBM Plex Sans", Aptos, ui-sans-serif, system-ui, sans-serif'
    fontSize: "12px"
    fontWeight: 800
    lineHeight: 1.2
    letterSpacing: "0"
  identifier:
    fontFamily: 'ui-monospace, "SFMono-Regular", Consolas, "Liberation Mono", monospace'
    fontSize: "10px"
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

# Design System: TCGA-TRACE

## Overview

**Creative North Star: "The Traceable Research Instrument"**

TCGA-TRACE should feel like a calibrated scientific instrument placed on a
quiet laboratory bench. The gridded paper canvas, journal-like headings,
compact controls and patient-level metrics communicate rigor before decoration.
The interface is dense because the work is dense, but every screen preserves a
clear sequence from setup to evidence to provenance.

Personality comes from a restrained analytical trace: small calibration
corners, one evidence signal color, tabular numerals, scientific icon frames
and brief acquisition motion. The system explicitly rejects generic SaaS dashboards, marketing
composition and theatrical biotechnology imagery.

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
- **Body** (400, 14px, 1.45): Descriptions and methodological context, capped
  near 70 characters when prose is continuous.
- **Label** (800, 12px, 1.2): Status and parameter labels. Letter spacing is
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

- **Style:** Dark technical rail with a subtle coordinate grid. The active
  module uses the evidence signal for its icon and a one-pixel horizontal trace.
- **Typography:** A 14px technical sans label; descriptions remain available
  through accessible names and tooltips.
- **Desktop:** The 280px rail may collapse to an 88px icon rail. The preference
  persists locally, while Home remains reachable from both the product mark and
  the first navigation item.
- **Mobile:** Status duplication is removed, navigation becomes a three-column
  grid with vertically centered icons and analytical summaries remain
  keyboard-scrollable.

### Scientific Icons

Structural icons combine familiar scientific glyphs with an original calibrated
frame, corner reference, acquisition node and three-bar microtrace. Survival
uses a descending outcome curve; endpoints use a target. Navigation selection
and fine-pointer hover animate only the glyph and microtrace using transform,
opacity and blur.

The implementation has four explicit semantic families:

- **Module icons:** Custom TCGA-TRACE drawings for datasets, genes, endpoints,
  expression, stratification, model outputs and reproducibility surfaces.
  Session history uses a chronological acquisition rail feeding separate
  inferential tracks and remains distinct from the prespecified multiverse
  specification curve.
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
containers. Decorative icons are hidden from assistive technology. Meaningful
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
