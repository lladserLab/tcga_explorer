import React from "react";
import { TraceIcon } from "./design/icons";
import { HelpButton } from "./help";
import { DESKTOP_RELEASE, TRACE_GITHUB_URL } from "./desktopRelease";

export default function DesktopDownloads({ local = import.meta.env.VITE_TRACE_LOCAL_DESKTOP === "true" }) {
  const github = <a className="home-source-link" href={TRACE_GITHUB_URL} target="_blank" rel="noopener noreferrer"><TraceIcon role="resource.github" size="md" />GitHub<TraceIcon role="action.next" size="sm" /></a>;
  if (local) return null;

  return (
    <section className="home-desktop" aria-labelledby="home-desktop-title">
      <div className="home-desktop-copy">
        <h2 id="home-desktop-title">Run TRACE on your computer</h2>
        <p>Analyze your own files or selected public cohorts. Your data and results are stored locally.</p>
        <div className="home-desktop-meta">
          <HelpButton label="Desktop installation and data" helpId="desktopInstallation" />
          {github}
        </div>
      </div>
      <div className="home-desktop-downloads">
        <div className="home-installer-list" aria-label="Desktop installers">
          {DESKTOP_RELEASE.installers.map((installer) => (
            <a key={installer.id} className="home-installer" href={`${DESKTOP_RELEASE.baseUrl}${installer.filename}`} download={installer.filename} aria-label={`Download TRACE for ${installer.label}, ${installer.platform}`}>
              <TraceIcon role={installer.iconRole} size="lg" />
              <span><strong>{installer.label}</strong><small>{installer.platform}</small></span>
              <TraceIcon role="action.download" size="md" />
            </a>
          ))}
        </div>
      </div>
    </section>
  );
}
