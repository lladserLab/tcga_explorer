export const SESSION_JOB_EVENT = "tcga-trace:job-update";
export const SESSION_HISTORY_STORAGE_KEY = "tcga-trace-exploratory-session-v1";
export const MAX_SESSION_EVENTS = 200;

function randomToken(prefix) {
  const token =
    globalThis.crypto?.randomUUID?.().replaceAll("-", "") ||
    `${Date.now().toString(36)}${Math.random().toString(36).slice(2)}`;
  return `${prefix}_${token}`;
}

export function createSessionHistory(enabled = false) {
  return {
    schema_version: "tcga-trace-browser-session-v1",
    browser_session_id: randomToken("browser"),
    session_label: "",
    recording_enabled: enabled,
    entries: [],
  };
}

export function loadSessionHistory(storage = globalThis.localStorage) {
  try {
    const parsed = JSON.parse(storage.getItem(SESSION_HISTORY_STORAGE_KEY) || "null");
    if (
      parsed?.schema_version === "tcga-trace-browser-session-v1" &&
      typeof parsed.browser_session_id === "string" &&
      Array.isArray(parsed.entries)
    ) {
      return {
        ...createSessionHistory(Boolean(parsed.recording_enabled)),
        ...parsed,
        entries: parsed.entries.slice(-MAX_SESSION_EVENTS),
      };
    }
  } catch {
    // Privacy-restricted storage falls back to an in-memory session.
  }
  return createSessionHistory(false);
}

export function persistSessionHistory(
  session,
  storage = globalThis.localStorage,
) {
  try {
    storage.setItem(SESSION_HISTORY_STORAGE_KEY, JSON.stringify(session));
    return true;
  } catch {
    return false;
  }
}

export function reduceSessionJobUpdate(session, detail) {
  if (!session.recording_enabled || !detail?.job?.id || !detail.event_id) {
    return session;
  }
  const existingIndex = session.entries.findIndex(
    (entry) => entry.event_id === detail.event_id,
  );
  const previous = existingIndex >= 0 ? session.entries[existingIndex] : null;
  const nextEntry = {
    event_id: detail.event_id,
    job_id: detail.job.id,
    recorded_at: previous?.recorded_at || detail.recorded_at || new Date().toISOString(),
    updated_at: new Date().toISOString(),
    label: detail.summary?.label || previous?.label || "Analysis run",
    source_view: detail.summary?.source_view || previous?.source_view || "",
    design_summary: detail.summary?.design_summary || previous?.design_summary || "",
    job_kind: detail.job.kind || previous?.job_kind || "",
    job_status: detail.job.status || previous?.job_status || "queued",
    result_id: detail.job.result_id || previous?.result_id || null,
    cached: Boolean(detail.job.cached),
    included: previous?.included ?? true,
  };
  const entries = [...session.entries];
  if (existingIndex >= 0) {
    entries[existingIndex] = nextEntry;
  } else {
    entries.push(nextEntry);
  }
  return {
    ...session,
    entries: entries.slice(-MAX_SESSION_EVENTS),
  };
}

export function updateSessionEntry(session, eventId, patch) {
  return {
    ...session,
    entries: session.entries.map((entry) =>
      entry.event_id === eventId ? { ...entry, ...patch } : entry,
    ),
  };
}

export function beginNewSession(session) {
  return {
    ...createSessionHistory(session.recording_enabled),
    session_label: "",
  };
}

export function buildSessionExportPayload(session) {
  const entries = session.entries
    .filter((entry) => entry.included && entry.job_id)
    .map((entry) => ({
      event_id: entry.event_id,
      job_id: entry.job_id,
      recorded_at: entry.recorded_at,
      label: entry.label,
      source_view: entry.source_view,
    }));
  return {
    browser_session_id: session.browser_session_id,
    session_label: session.session_label,
    entries,
  };
}

export function terminalSessionEntry(entry) {
  return ["completed", "failed", "expired"].includes(entry.job_status);
}
