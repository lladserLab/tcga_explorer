# TCGA-TRACE frontend rules

These instructions apply to every file under `frontend/`.

## Product character

TCGA-TRACE is a traceable scientific instrument, not a generic SaaS dashboard.
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

## Synchronization

When the icon contract changes, update all of:

- `src/design/icons.jsx`
- `src/design/icons.test.jsx`
- `../docs/ICON_SYSTEM.md`
- `../DESIGN.md` when the visual language or behavior changes

Run `npm test` and `npm run build` in `frontend/` before considering the change
complete.
