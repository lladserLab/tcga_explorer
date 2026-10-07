# Windows x64 and shared desktop code

The Windows NSIS installer contains Electron, Python 3.13.16, R 4.4.2 and the TRACE scientific libraries. End users do not need Docker, PostgreSQL, Python or R. Data packages are imported separately. For installation, storage locations and downloads, see [the desktop guide](../../docs/DESKTOP.md).

## Build

Use Node 22 or later. Generated assets belong under `desktop/build/`, outside Git.

1. Extract the official Windows x64 Python embeddable archive into `desktop/build/runtime/windows/python`. In `python313._pth`, enable `import site` and include `Lib/site-packages` and `../backend`.
2. Install Windows cp313 x64 wheels using `requirements-windows.lock`. Include pywin32 explicitly when assembling on a non-Windows host, whose pip does not evaluate Windows markers.
3. Extract the R 4.4.2 Windows installer into the runtime's `R` directory. `prepare_r_packages.py` retrieves pinned Windows ZIPs and records hashes. Use `install_r_sources.R` with bundled Rscript for the pure-R source fallbacks, then run `verify_r.R`.
4. Fetch guide videos and build the frontend with `VITE_TRACE_LOCAL_DESKTOP=true`, `VITE_BASE_PATH=/tcga_explorer/` and `VITE_API_BASE_URL=/tcga_explorer`. Run `python3 desktop/native/assemble.py` from the repository root.
5. In `desktop/native`, run `npm ci` and `npm run dist:windows`. Packaging produces `desktop/build/installers/TRACE-Explorer-Setup-0.1.7-windows-x64.exe`.

Electron and electron-builder versions are pinned in `package-lock.json`. The Windows package lock differs from the server lock where platform dependencies require it. BiocParallel uses the available Bioconductor 3.20 Windows binary 1.40.0 instead of Linux 1.40.2; the tested scoring runs serially. The Unix-only littler CLI is excluded. Statistical formulas remain in the shared backend scripts.

The portable engine and scientific scripts have been exercised through cross-build checks, and a user reported successful Windows startup. A complete test on native Windows should cover uploads, cohort updates, analysis exports, restart and uninstall/reinstall. The hosted installer is unsigned; publisher signing is still required for distribution without an unknown-publisher identity.

## Shared modules

- `serving.py` routes frontend assets and API/MCP requests to their respective handlers.
- `cohorts.py`, `tcga_packages.py` and `data_packages.py` handle cohort archives and validation.
- `reference_updates.py` installs reference updates while preserving their release identity.
- `publish_packages.py` prepares standalone package files and their catalog.
- `data-actions.cjs` and `downloads.cjs` provide native file selection and checked downloads.

The local engine uses SQLite, WAL, a 30-second lock timeout and one compute worker. User data are separate from installer resources and survive uninstall. Manage data searches only a user-selected folder and grants access through native-dialog selections. See the shared unit tests for import, archive-path, download and HTTP-routing checks.
