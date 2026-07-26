# Browser Compatibility Benchmark

- Status: `passed_provisional`
- Tested: `2026-07-26T03:10:13.454134+00:00`
- Target: `http://192.168.1.31:3000/tcga_explorer/`
- Commit: `ac32eb643e6c60b0281881cd879ce0d6e88b2843`
- Exact tag: `none`
- Observed deployment commit(s): `development`
- Worktree dirty before run: `true`
- Playwright: `1.56.1`
- Container: `mcr.microsoft.com/playwright:v1.56.1-noble`

| Engine | Browser version | Checks | Result | Duration (s) |
| --- | --- | ---: | --- | ---: |
| chromium | 141.0.7390.37 | 8/8 | passed | 20.99 |
| firefox | 142.0.1 | 8/8 | passed | 25.25 |
| webkit | 26.0 | 8/8 | passed | 47.92 |

## Contract

Each engine runs the following checks:

- landing page, keyboard focus and navigation;
- Survival gene suggestions, external-covariate CSV configuration, completed CDC20/LIHC analysis, audit download and signed-receipt download;
- UVM/BAP1/DSS competing-risk output with CIF, Gray/Fine-Gray, square PNG download and desktop/mobile containment;
- Compare gene suggestions, live preview and the four-method publication panel;
- opt-in exploratory run history, export-defined multiplicity families, signed receipt and 390-pixel mobile containment;
- final-release commit identity from the public health resource;
- frozen Paper Examples rendering;
- Pan-cancer and Dataset Summary visualizations; and
- reduced-motion rendering and navigation.

Playwright WebKit validates the engine contract but is not an exact substitute for a manual check in the final Safari release. Provisional evidence must be rerun against the exact tagged HTTPS deployment before submission.
