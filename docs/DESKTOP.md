# TRACE on your computer

The desktop app contains the frontend, local API, compute worker, Python, R and scientific libraries. Cohort data are added separately. Local analysis works without an internet connection once the required data are installed; downloading packages requires a connection.

## Install

Download the installer for your processor from the [README](../README.md#use-trace-on-your-computer).

- **Windows x64:** run the `.exe` installer and choose the installation folder. The installer preserves user data when the app is uninstalled.
- **macOS, Apple Silicon:** open the `.dmg`, drag TRACE Explorer into Applications, eject the disk image and launch the app. This build does not support Intel Macs.
- **Linux x64:** allow the AppImage to run as a program in your file manager, then open it. Alternatively, use `chmod +x` followed by the AppImage filename. The current runtime requires glibc 2.39 or later, such as Ubuntu 24.04, and a desktop session with GTK3 and NSS. Run it as your regular user.

Windows signing and Apple Developer ID signing/notarization are pending. The current Windows executable is unsigned; the Mac app is ad-hoc signed. A security warning about an unknown publisher is different from an explicit antivirus detection. If installation is blocked, report the exact message and installer name in a GitHub issue. Do not disable antivirus protection.

## Manage data

Choose **Manage data** in the desktop app:

1. **From this computer:** choose a folder containing TRACE `.tar.gz` packages, search by cancer or filename and add a package. You can also choose a single file. TRACE searches the chosen folder without traversing subfolders or following symlinks; the original archive stays in place.
2. **Download:** set a hosted catalog URL under **Download source**, then choose TCGA or external studies. The catalog lists package sizes and whether a source is installed or has an update. No public catalog is configured by default.
3. **Ready to use:** inspect installed sources or choose **Save a copy** to export a package for another installation.

TCGA and external studies remain separate sources. Downloads are checked against the catalog's size and SHA-256, and imports validate archive paths and contents. An unavailable remote catalog does not prevent local imports.

To analyze your own measurements, choose **Use your own data** in TRACE rather than importing an arbitrary archive into Manage data. Upload the expression and clinical files, map their columns and select the applicable expression scale.

## Storage and updates

Projects, reference data and results live outside the application installation:

| System | Default workspace |
| --- | --- |
| Windows | `%APPDATA%\TRACE Explorer\workspace` |
| macOS | `~/Library/Application Support/trace-explorer-desktop-macos/workspace` |
| Linux | `~/.config/trace-explorer-desktop-linux/workspace` |

The local database uses SQLite and one compute worker. Saved projects retain their access information across restarts. Replacing an installer preserves the workspace; back it up before updating. Installing a newer app and downloading newer cohort packages are separate actions.

On Windows, the engine uses the loopback port 3100. macOS and Linux save the port selected on first launch. If another service occupies the required port, close that service before starting TRACE again. Quit the application to stop its local services; on macOS, closing the window alone hides the app.

## Verify downloads

SHA-256 values for the currently hosted 0.1.7 installers:

```text
4178fdb89224253e6730be3f3cfff292debe64dfe785a4bbc974c97d1f5518aa  TRACE-Explorer-Setup-0.1.7-windows-x64.exe
fa8e76582cea64cf45523e68c183422a540ad9ce55acc87f827316d7364ff748  TRACE-Explorer-0.1.7-macOS-arm64.dmg
b7a1b94b2990132f3be0f100d572654342b4e211d7981a09b7c70b7b1c57a1f6  TRACE-Explorer-0.1.7-Linux-x64.AppImage
```

Use `Get-FileHash -Algorithm SHA256` in PowerShell, `shasum -a 256` on macOS or `sha256sum` on Linux. Matching a checksum verifies the downloaded file against this record; it does not replace publisher signing or a malware assessment.

## Build from source

See [desktop source](../desktop/README.md). The Windows, macOS and Linux packaging directories contain their launcher, runtime preparation scripts and dependency locks. The platform documentation records build requirements and the scope of verification. A source update does not automatically rebuild the hosted installers.
