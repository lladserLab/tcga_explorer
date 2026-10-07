# macOS Apple Silicon

The DMG contains the current TRACE desktop interface, its seven offline guide videos and a bundled Python/R engine. Docker, Homebrew and a separate XQuartz installation are not end-user requirements. Install by dragging TRACE Explorer into Applications. Storage and data management are described in [the desktop guide](../../docs/DESKTOP.md).

## Build

Use a native arm64 Node 22 or later. Runtime source URLs, sizes and SHA-256 values are recorded in `runtime-archives.json`.

1. Prepare standalone Python 3.13.16 and the R 4.4.2 arm64 framework in `desktop/build/runtime/macos-arm64`. Install the Python dependencies from `requirements.lock`.
2. Retrieve R packages using `prepare-r-packages.py`; install source fallbacks using `install-source-r.py`. Configure R's launcher and bundle the XQuartz graphics client libraries used by Cairo. No X11 server is needed. Omit unused TclTk GUI support while retaining R's X11 graphics module.
3. Run `relocate-r.py` to rewrite Mach-O dependencies to loader-relative paths and ad-hoc sign modified files. Reject unresolved non-system dependencies. Check the result using `desktop/native/verify_r.R` with bundled Rscript.
4. Fetch guide videos, run frontend tests and build with `VITE_TRACE_LOCAL_DESKTOP=true`, `VITE_BASE_PATH=/tcga_explorer/` and `VITE_API_BASE_URL=/tcga_explorer`. Run `python3 desktop/macos/assemble.py`.
5. In `desktop/macos`, run `npm ci`, generate icons with `build-icons.cjs` if needed, and run `npm run dist:mac`. Output belongs under `desktop/build/macos/installers/`.
6. Test the packaged app after copying it into a path containing spaces. Verify Finder startup, uploads, jobs, exports, cohort import, offline videos, saved-project recovery and Command-Q shutdown.

The current build is ad-hoc signed and is not Apple-notarized. Public publisher verification requires a Developer ID certificate, signing the nested runtime and app, notarization and stapling the ticket to the distributed package. The package configuration currently disables automatic Developer ID signing.

## Runtime behavior

The app targets Apple Silicon. The loopback port selected on first launch is saved, so projects remain accessible after restart. Closing the window hides it; the Dock restores it. Command-Q stops the API and worker. Upgrades preserve the separate workspace.

Checks on the build host covered local analysis, source import/export, offline videos and restart behavior. They do not establish Intel compatibility. Runtime dependency locks and relocation scripts are included; machine-specific test profiles and generated verification artifacts are maintained separately.
