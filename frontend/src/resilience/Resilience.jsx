import React, { Component, useEffect, useMemo, useState } from "react";

import { getComputeJob } from "../api";
import {
  ACTIVE_JOB_EVENT,
  clearActiveJob,
  latestActiveJob,
  updateRecordedActiveJob,
} from "../activeJobs";
import { TraceIcon } from "../design/icons";
import { isLocalDesktop } from "../userDataset";
import "./resilience.css";

const TERMINAL_JOB_STATES = new Set(["completed", "failed", "expired"]);

export class ModuleErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, details) {
    globalThis.console?.error?.("TRACE module render failed", error, details);
  }

  componentDidUpdate(previousProps) {
    if (
      this.state.error
      && previousProps.resetKey !== this.props.resetKey
    ) {
      this.setState({ error: null });
    }
  }

  render() {
    if (!this.state.error) return this.props.children;
    const moduleName = this.props.moduleName || "This module";
    return (
      <section className="module-failure" role="alert" aria-labelledby="module-failure-title">
        <TraceIcon role="status.error" size="lg" tone="error" />
        <div>
          <p className="eyebrow">Interface recovery</p>
          <h1 id="module-failure-title">{moduleName} could not be displayed</h1>
          <p>
            Your analyses and private dataset remain on the server. Try opening this
            module again.
          </p>
          <div className="module-failure-actions">
            <button
              type="button"
              className="primary-button"
              onClick={() => this.setState({ error: null })}
            >
              Try this module again
            </button>
            <button
              type="button"
              className="tertiary-button"
              onClick={() => globalThis.location?.reload?.()}
            >
              Reload application
            </button>
          </div>
        </div>
      </section>
    );
  }
}

export function ServiceStatusNotice({ state, onRetry }) {
  const [online, setOnline] = useState(() => (
    typeof navigator === "undefined" ? true : navigator.onLine
  ));

  useEffect(() => {
    if (typeof window === "undefined") return undefined;
    const markOnline = () => setOnline(true);
    const markOffline = () => setOnline(false);
    window.addEventListener("online", markOnline);
    window.addEventListener("offline", markOffline);
    return () => {
      window.removeEventListener("online", markOnline);
      window.removeEventListener("offline", markOffline);
    };
  }, []);

  const offline = !online && !isLocalDesktop();
  if (!offline && !["degraded", "unavailable"].includes(state?.status)) {
    return null;
  }

  const failed = Array.isArray(state?.failed) ? state.failed : [];
  const title = offline
    ? "You are offline"
    : state?.status === "unavailable"
      ? "TRACE services are unavailable"
      : "Some data could not be refreshed";
  const detail = offline
    ? "The current page remains visible. New searches, analyses and downloads need a connection."
    : failed.length
      ? `${failed.join(", ")} could not be loaded. Available modules remain usable.`
      : "The application could not reach the analysis service.";

  return (
    <div className="service-status-notice" role={offline ? "alert" : "status"}>
      <TraceIcon
        role={offline || state?.status === "unavailable" ? "status.error" : "status.caution"}
        size="sm"
        tone={offline || state?.status === "unavailable" ? "error" : "caution"}
      />
      <div>
        <strong>{title}</strong>
        <span>{detail}</span>
      </div>
      {!offline && typeof onRetry === "function" && (
        <button
          type="button"
          className="tertiary-button"
          disabled={state?.status === "loading"}
          onClick={onRetry}
        >
          Retry
        </button>
      )}
    </div>
  );
}

export function DraftRecoveryNotice({ draft, onResume, onDiscard }) {
  if (!draft) return null;
  const savedAt = Date.parse(draft.saved_at || "");
  const savedLabel = Number.isFinite(savedAt)
    ? new Intl.DateTimeFormat("en", {
        dateStyle: "medium",
        timeStyle: "short",
      }).format(savedAt)
    : "an earlier session";
  return (
    <section className="draft-recovery-notice" aria-labelledby="draft-recovery-title">
      <TraceIcon role="status.info" size="md" tone="accent" />
      <div>
        <span>Saved setup</span>
        <strong id="draft-recovery-title">Resume your previous analysis?</strong>
        <p>{draft.summary || "Configured analysis"}</p>
        <small>Saved {savedLabel}. Results and private files are not stored in this draft.</small>
      </div>
      <div className="draft-recovery-actions">
        <button type="button" className="primary-button" onClick={onResume}>
          Resume setup
        </button>
        <button type="button" className="tertiary-button" onClick={onDiscard}>
          Discard
        </button>
      </div>
    </section>
  );
}

export function ModuleLoadFallback({ label = "module" }) {
  return (
    <div className="module-load-fallback" role="status" aria-live="polite">
      <TraceIcon role="status.loading" size="lg" tone="accent" className="spin" />
      <div>
        <span>Opening {label}</span>
        <strong>Loading the workspace</strong>
      </div>
    </div>
  );
}

function elapsedLabel(recordedAt, now) {
  const start = Date.parse(recordedAt || "");
  if (!Number.isFinite(start)) return "Started recently";
  const seconds = Math.max(0, Math.floor((now - start) / 1000));
  if (seconds < 60) return `${seconds}s elapsed`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m elapsed`;
  const hours = Math.floor(minutes / 60);
  return `${hours}h ${minutes % 60}m elapsed`;
}

export function ElapsedTime({ label = "Elapsed" }) {
  const [startedAt] = useState(() => Date.now());
  const [now, setNow] = useState(startedAt);
  useEffect(() => {
    if (typeof window === "undefined") return undefined;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);
  const value = elapsedLabel(new Date(startedAt).toISOString(), now)
    .replace(" elapsed", "");
  return <small className="job-elapsed-time">{label} {value}</small>;
}

function jobPresentation(job) {
  const status = job?.status || job?.job_status || "queued";
  if (status === "completed") {
    return {
      icon: "status.success",
      tone: "success",
      eyebrow: "Recovered analysis",
      title: "Result ready",
    };
  }
  if (status === "failed" || status === "expired") {
    return {
      icon: "status.error",
      tone: "error",
      eyebrow: "Recovery stopped",
      title: status === "expired" ? "Result expired" : "Analysis failed",
    };
  }
  return {
    icon: "status.loading",
    tone: "accent",
    eyebrow: status === "queued" ? "Queued analysis" : "Analysis in progress",
    title: status === "queued" ? "Waiting for a compute worker" : "Server-side computation continues",
  };
}

export function ActiveJobRecovery({
  sourceView,
  busy = false,
  onRecover,
}) {
  const [entry, setEntry] = useState(() => latestActiveJob(sourceView));
  const [job, setJob] = useState(null);
  const [refreshError, setRefreshError] = useState("");
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    setEntry(latestActiveJob(sourceView));
    setJob(null);
    setRefreshError("");
  }, [sourceView]);

  useEffect(() => {
    if (typeof window === "undefined") return undefined;
    const refreshEntry = (event) => {
      if (
        event?.detail?.source_view === sourceView
        || event?.detail?.cleared
      ) {
        setEntry(latestActiveJob(sourceView));
      }
    };
    const refreshFromStorage = () => setEntry(latestActiveJob(sourceView));
    window.addEventListener(ACTIVE_JOB_EVENT, refreshEntry);
    window.addEventListener("storage", refreshFromStorage);
    return () => {
      window.removeEventListener(ACTIVE_JOB_EVENT, refreshEntry);
      window.removeEventListener("storage", refreshFromStorage);
    };
  }, [sourceView]);

  useEffect(() => {
    if (!entry || busy || typeof window === "undefined") return undefined;
    let cancelled = false;
    let timer = 0;
    async function refresh() {
      try {
        const payload = await getComputeJob(entry.job_id);
        if (cancelled) return;
        setJob(payload);
        setRefreshError("");
        updateRecordedActiveJob(entry, payload);
        if (!TERMINAL_JOB_STATES.has(payload.status)) {
          timer = window.setTimeout(refresh, 2000);
        }
      } catch (error) {
        if (cancelled) return;
        setRefreshError(
          error?.message || "The job status could not be refreshed.",
        );
        timer = window.setTimeout(refresh, 5000);
      }
    }
    timer = window.setTimeout(refresh, 0);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [busy, entry?.event_id, entry?.job_id]);

  const activeStatus = job?.status || entry?.job_status;
  useEffect(() => {
    if (!entry || TERMINAL_JOB_STATES.has(activeStatus) || typeof window === "undefined") {
      return undefined;
    }
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [activeStatus, entry]);

  const presentation = useMemo(
    () => jobPresentation(job || entry),
    [entry, job],
  );

  if (!entry || busy) return null;
  const canRecover = activeStatus === "completed" && job?.result;
  const terminal = TERMINAL_JOB_STATES.has(activeStatus);

  return (
    <section
      className={`active-job-recovery is-${activeStatus || "queued"}`}
      aria-live="polite"
      aria-atomic="true"
    >
      <TraceIcon
        role={presentation.icon}
        size="md"
        tone={presentation.tone}
        className={!terminal ? "spin" : ""}
      />
      <div className="active-job-recovery-copy">
        <span>{presentation.eyebrow}</span>
        <strong>{presentation.title}</strong>
        <p>{entry.label}{entry.design_summary ? ` · ${entry.design_summary}` : ""}</p>
        <small>
          Job {entry.job_id.slice(0, 12)}… · {elapsedLabel(entry.recorded_at, now)}
          {refreshError ? ` · ${refreshError}` : ""}
        </small>
      </div>
      <div className="active-job-recovery-actions">
        {canRecover && (
          <button
            type="button"
            className="primary-button"
            onClick={() => {
              onRecover?.(job.result, job, entry);
              clearActiveJob(entry.event_id);
            }}
          >
            Open result
          </button>
        )}
        {terminal && !canRecover && (
          <button
            type="button"
            className="tertiary-button"
            onClick={() => clearActiveJob(entry.event_id)}
          >
            Dismiss
          </button>
        )}
      </div>
    </section>
  );
}
