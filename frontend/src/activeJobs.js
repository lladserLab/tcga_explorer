export const ACTIVE_JOB_STORAGE_KEY = "trace-explorer-active-jobs-v1";
export const ACTIVE_JOB_EVENT = "tcga-trace:active-job";
export const MAX_ACTIVE_JOBS = 12;

function safeStorage(storage) {
  if (storage !== undefined) return storage;
  try {
    return globalThis.localStorage || null;
  } catch {
    return null;
  }
}

function normalizeEntry(detail = {}) {
  const job = detail.job || {};
  const summary = detail.summary || {};
  if (!detail.event_id || !job.id) return null;
  return {
    event_id: String(detail.event_id),
    job_id: String(job.id),
    job_kind: String(job.kind || ""),
    job_status: String(job.status || "queued"),
    source_view: String(summary.source_view || "analysis"),
    label: String(summary.label || "Analysis"),
    design_summary: String(summary.design_summary || ""),
    recovery_context: summary.recovery_context || null,
    recorded_at: detail.recorded_at || new Date().toISOString(),
    updated_at: new Date().toISOString(),
  };
}

function notify(entry) {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new CustomEvent(ACTIVE_JOB_EVENT, { detail: entry }));
}

export function loadActiveJobs(storage) {
  const resolvedStorage = safeStorage(storage);
  try {
    const parsed = JSON.parse(
      resolvedStorage?.getItem?.(ACTIVE_JOB_STORAGE_KEY) || "[]",
    );
    if (!Array.isArray(parsed)) return [];
    return parsed
      .filter((entry) => entry?.event_id && entry?.job_id && entry?.source_view)
      .slice(-MAX_ACTIVE_JOBS);
  } catch {
    return [];
  }
}

function persist(entries, storage) {
  const resolvedStorage = safeStorage(storage);
  try {
    if (!resolvedStorage?.setItem) return false;
    resolvedStorage.setItem(
      ACTIVE_JOB_STORAGE_KEY,
      JSON.stringify(entries.slice(-MAX_ACTIVE_JOBS)),
    );
    return true;
  } catch {
    return false;
  }
}

export function recordActiveJobUpdate(detail, storage) {
  const entry = normalizeEntry(detail);
  if (!entry) return null;
  const entries = loadActiveJobs(storage);
  const priorIndex = entries.findIndex(
    (candidate) => candidate.event_id === entry.event_id,
  );
  if (priorIndex >= 0) {
    entry.recorded_at = entries[priorIndex].recorded_at || entry.recorded_at;
    entries[priorIndex] = entry;
  } else {
    entries.push(entry);
  }
  persist(entries, storage);
  notify(entry);
  return entry;
}

export function updateRecordedActiveJob(entry, job, storage) {
  if (!entry?.event_id || !job?.id) return null;
  return recordActiveJobUpdate(
    {
      event_id: entry.event_id,
      recorded_at: entry.recorded_at,
      summary: {
        source_view: entry.source_view,
        label: entry.label,
        design_summary: entry.design_summary,
        recovery_context: entry.recovery_context,
      },
      job,
    },
    storage,
  );
}

export function clearActiveJob(eventId, storage) {
  const normalized = String(eventId || "");
  if (!normalized) return false;
  const entries = loadActiveJobs(storage);
  const next = entries.filter((entry) => entry.event_id !== normalized);
  if (next.length === entries.length) return false;
  persist(next, storage);
  notify({ event_id: normalized, cleared: true });
  return true;
}

export function latestActiveJob(sourceView, storage) {
  const source = String(sourceView || "");
  return loadActiveJobs(storage)
    .filter((entry) => entry.source_view === source)
    .sort((left, right) => {
      const leftTime = Date.parse(left.updated_at || left.recorded_at || "") || 0;
      const rightTime = Date.parse(right.updated_at || right.recorded_at || "") || 0;
      return rightTime - leftTime;
    })[0] || null;
}
