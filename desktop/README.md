# Desktop source

TRACE desktop bundles the existing scientific engine with a local API, worker, SQLite database and Electron interface. Python and R are bundled for the target platform. Data packages are managed separately; user projects live outside the application and persist across upgrades.

For installation and data management, see [the desktop guide](../docs/DESKTOP.md).

| Target | Source and build notes | Output |
| --- | --- | --- |
| Windows x64 | [native/](native/README.md) | NSIS `.exe` |
| macOS Apple Silicon | [macos/](macos/README.md) | `.dmg` |
| Linux x64 | [linux/](linux/README.md) | `.AppImage` |

`native/` also contains shared cohort-package, download and HTTP-serving code used by the other platforms. Each platform has its own engine launcher and runtime assembly. Generated runtimes and build outputs belong under `desktop/build/`; test workspaces belong under `desktop/runtime/`. Both are ignored by Git.

## Build sequence

1. Prepare the target's Python and R runtime from the pinned archives and locks.
2. Restore the scientific libraries and run `native/verify_r.R` with bundled R.
3. Install frontend dependencies, fetch the seven guide videos, run frontend tests and build with `VITE_TRACE_LOCAL_DESKTOP=true`, `VITE_BASE_PATH=/tcga_explorer/` and `VITE_API_BASE_URL=/tcga_explorer`.
4. Run the platform's assembly scripts and install its launcher dependencies with `npm ci`. Package using the platform's `dist` command.
5. Test the packaged app from a clean user profile: startup, upload, cohort import, scientific jobs, exports, saved-project recovery and shutdown.
6. Sign the Windows installer, or sign and notarize the Mac app, before a publisher-verified distribution. Keep the final installer hash with the release.

Build tooling may use containers; the installed app does not require Docker. Current hosted Windows and Mac builds still need publisher signing/notarization.

## Data packages

`native/data_packages.py` validates imports, `native/tcga_packages.py` builds TCGA archives, and `native/publish_packages.py` prepares the separate package catalog. These tools require a configured local source repository; they do not download or publish research data merely by being installed. Host the resulting archives and catalog separately, then configure their URL in Manage data.

Keep runtime credentials, private project capabilities and source patient data out of installer resources and Git commits. Platform probes use their own test profiles; synthetic fixtures are included for repeatable checks.
