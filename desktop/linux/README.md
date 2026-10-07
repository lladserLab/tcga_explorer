# Linux x64

The AppImage contains TRACE, Python 3.13.16, R 4.4.2, the locked scientific libraries and seven offline guide videos. End users do not need Docker or a system Python/R installation. Choose data through Manage data or upload your own expression and clinical files. See [the desktop guide](../../docs/DESKTOP.md).

## Install

```sh
chmod +x TRACE-Explorer-0.1.7-Linux-x64.AppImage
./TRACE-Explorer-0.1.7-Linux-x64.AppImage
```

The current build requires x86-64 Linux with glibc 2.39 or later, such as Ubuntu 24.04, and a desktop session with GTK3 and NSS. It is not an ARM64 build. The modern static AppImage runtime does not require the legacy libfuse2 package. Run TRACE as your regular user. Closing the last window stops its local services; upgrading the AppImage preserves the separate workspace.

## Build

Use an x86-64 Ubuntu 24.04 build environment with R 4.4.2, patchelf, fonts-dejavu-core and Node 22 or later. The R bundling scripts expect the source checkout at `/project` and R under `/usr/local/lib/R`.

1. Retrieve and verify the standalone Python archive in `runtime-archives.json`; restore `backend/requirements.lock` with pip's `--require-hashes` option.
2. Run `restore-r.R` to install the R library, then `bundle-r.py` to copy R and its non-glibc ELF dependencies into `desktop/build/runtime/linux-x64`. Retain license/source notices using `notices.py`.
3. Run `assemble.py` to copy scientific source and registry metadata. Fetch guide videos and build the frontend with `VITE_TRACE_LOCAL_DESKTOP=true`, `VITE_BASE_PATH=/tcga_explorer/` and `VITE_API_BASE_URL=/tcga_explorer`. Run `prepare-frontend.py` to verify and copy the seven offline videos.
4. In `desktop/linux`, run `npm ci` and `npm run dist:linux`. Electron, electron-builder and the AppImage toolset are pinned in the package lock/configuration. Output belongs under `desktop/build/linux/installers/`.
5. Test the actual packaged app from a clean user profile, including startup, scientific jobs, data packages, exports, restart and shutdown.

## Verification scope

The packaged payload passed core workflows on Ubuntu 24.04 and Debian 13 using virtual X11 sessions. Tests included private uploads, survival and molecular jobs, all six signature methods, cohort import/export, checked catalog downloads, offline videos and saved-project recovery. A non-root launch from a path containing spaces was checked.

These checks used virtual display environments and test-only Electron flags. FUSE-mounted startup on a physical Linux desktop and Wayland have not been verified. The launcher checks glibc compatibility and reports unsupported environments explicitly.
