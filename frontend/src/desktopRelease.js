// Update from the verified installer manifests when publishing a new version.
export const TRACE_GITHUB_URL = "https://github.com/lladserLab/tcga_explorer";
export const DESKTOP_RELEASE = Object.freeze({
  version: "0.1.7",
  baseUrl: "https://apps.cienciavida.org/tcga_explorer/downloads/desktop/0.1.7/",
  installers: [
    {
      id: "windows",
      label: "Windows",
      platform: "64-bit (x64)",
      filename: "TRACE-Explorer-Setup-0.1.7-windows-x64.exe",
      iconRole: "platform.windows",
      sha256: "4178fdb89224253e6730be3f3cfff292debe64dfe785a4bbc974c97d1f5518aa",
    },
    {
      id: "macos",
      label: "macOS",
      platform: "Apple Silicon (M1 or later)",
      filename: "TRACE-Explorer-0.1.7-macOS-arm64.dmg",
      iconRole: "platform.macos",
      sha256: "fa8e76582cea64cf45523e68c183422a540ad9ce55acc87f827316d7364ff748",
    },
    {
      id: "linux",
      label: "Linux",
      platform: "64-bit (x64) · AppImage",
      filename: "TRACE-Explorer-0.1.7-Linux-x64.AppImage",
      iconRole: "platform.linux",
      sha256: "b7a1b94b2990132f3be0f100d572654342b4e211d7981a09b7c70b7b1c57a1f6",
    },
  ],
});
