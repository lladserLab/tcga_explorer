# TCGA-TRACE Project Identity

The canonical product, manuscript and release name is **TCGA-TRACE**.
New user-facing text, package metadata, manuscript files and release archives
must use that name or the lowercase file prefix `tcga-trace`.

## Compatibility Identifiers

The following legacy identifiers remain stable compatibility surfaces. They
are locators or implementation names, not the product name:

- `/tcga_explorer` is the historical public deployment path retained for
  bookmarks, API clients and published reviewer links.
- `lladserLab/tcga_explorer` is the current repository slug until the repository
  owner decides whether to rename it.
- `tcga_explorer` database names, `TCGA_EXPLORER_*` deployment variables and
  historical `tcga-explorer-*` audit schema versions remain accepted to avoid
  breaking deployments or previously exported records.

Documentation may show these identifiers only when referring to their exact
technical role. Display names, page titles, OpenAPI/MCP metadata, manuscript
prose and newly generated release artifacts use TCGA-TRACE.
