# TRACE Explorer frontend rules

These instructions apply to every file under `frontend/`.

## Product character

TRACE Explorer is a traceable scientific instrument, not a generic SaaS dashboard.
Preserve the restrained evidence-cyan palette, technical paper canvas, compact
data hierarchy and visible methodological context described in `../PRODUCT.md`
and `../DESIGN.md`.

## Icon contract

- Read `../docs/ICON_SYSTEM.md` before changing or adding an icon.
- Import `TraceIcon`, `ModuleIcon` and `IconButton` only from
  `src/design/icons.jsx`.
- Do not import `lucide-react` outside `src/design/icons.jsx`.
- Pass an explicit semantic role. Never derive an icon or tone from visible
  copy, translated labels or regular expressions.
- Use `ModuleIcon` for navigation, workflow steps and analytical headings.
- Use `TraceIcon` for familiar actions, compact data glyphs and status.
- Use `IconButton` only when an icon-only action is universally recognizable.
  It requires a specific accessible label and tooltip.
- Use only named sizes and tones. Numeric icon sizes and hardcoded icon colors
  are prohibited.
- Plot marks remain in plot SVGs and are not added to the interface registry.

## Help contract

- Read `../docs/HELP_SYSTEM.md` before adding or changing any in-place help.
- All help copy lives in `src/help/registry.js`. Never inline it at a call site.
- Import `LabelWithHelp`, `FieldWithHelp`, `PanelHeader`, `SectionHelp`,
  `FieldHelp`, `HelpButton` and `Term` only from `src/help`.
- Pass `helpId`, not prose. Compose entries with `helpId={["a", "b"]}`.
- Statistical vocabulary lives in `src/tutorials/conceptRegistry.js` and reaches
  the workspace only through `<Term>`.
- Runtime help and guide copy is English only; internal stable identifiers may remain presentation-neutral.
- A help trigger is never a descendant of a `<label>`; use `FieldWithHelp`.
- A multi-step module renders `<DesignLedger>` in its setup column. Its copy
  comes from pure functions in `src/help/designLedgerContract.js`, never from
  JSX written per module.
- Module quick guides are reference help and are never gated on checkpoints.

## Synchronization

When the icon contract changes, update all of:

- `src/design/icons.jsx`
- `src/design/icons.test.jsx`
- `../docs/ICON_SYSTEM.md`
- `../DESIGN.md` when the visual language or behavior changes

Run `npm test` and `npm run build` in `frontend/` before considering the change
complete.
