# TRACE Explorer brand system

## Concept

The T-Trace mark turns the initial **T** into a stepped analytical path ending
in a square evidence node. It represents carrying one research question across
cohorts, endpoints and analyses. It deliberately avoids a DNA helix, cancer
ribbon, medical cross or a single statistical plot because TRACE Explorer is a
multi-analysis research instrument.

## Canonical assets

- `frontend/public/brand/trace-mark.svg` — master full-colour square mark.
- `frontend/public/brand/trace-mark-maskable.svg` — safe-zone-padded app icon source.
- `frontend/public/brand/trace-mark-monochrome.svg` — transparent one-colour mark.
- `frontend/public/brand/trace-explorer-lockup.svg` — horizontal logo lockup.
- `frontend/public/brand/trace-thumbnail.png` — 512 px square thumbnail.
- `frontend/public/social/trace-explorer-card-v1.png` — 1200×630 social preview.
- `frontend/public/favicon.ico` — 16/32/48 px browser fallback.
- `frontend/public/apple-touch-icon.png` — 180 px Apple touch icon.
- `frontend/public/icons/` — 192, 512 and maskable app icons.

The SVG master is authoritative. Regenerate every raster derivative with:

```bash
cd frontend
npm run brand:build
```

## Usage rules

- Use the square mark alone below 96 px or whenever the product name is already visible.
- Use the horizontal lockup in documents with enough horizontal space.
- Preserve the dark ink field, cyan trace and paper evidence node in colour use.
- Use only the monochrome asset for one-colour printing.
- Do not redraw, rotate, outline, recolour individual segments or place another glyph inside the mark.
- Keep clear space around the mark equal to at least one quarter of its width.
- Never use the product mark as an analysis-module, action or status icon.

The social image is a dedicated composition, not a stretched favicon. The web
manifest identifies the installed application but does not claim offline
support; TRACE Explorer currently has no service worker.
