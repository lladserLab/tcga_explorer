import { describe, expect, test } from "vitest";
import {
  MAX_SESSION_EVENTS,
  beginNewSession,
  buildSessionExportPayload,
  createSessionHistory,
  loadSessionHistory,
  persistSessionHistory,
  reduceSessionJobUpdate,
  updateSessionEntry,
} from "./sessionHistory";

function memoryStorage() {
  const values = new Map();
  return {
    getItem: (key) => values.get(key) || null,
    setItem: (key, value) => values.set(key, value),
  };
}

describe("exploratory browser session history", () => {
  test("recording is opt-in and job updates are upserted", () => {
    const disabled = createSessionHistory(false);
    const detail = {
      event_id: "event-001",
      recorded_at: "2026-07-25T12:00:00Z",
      summary: {
        label: "CDC20",
        source_view: "analysis",
        design_summary: "TCGA-LIHC · OS · median",
      },
      job: {
        id: "a".repeat(32),
        kind: "analysis",
        status: "queued",
      },
    };

    expect(reduceSessionJobUpdate(disabled, detail).entries).toEqual([]);
    const enabled = { ...disabled, recording_enabled: true };
    const queued = reduceSessionJobUpdate(enabled, detail);
    const completed = reduceSessionJobUpdate(queued, {
      ...detail,
      job: {
        ...detail.job,
        status: "completed",
        result_id: "analysis-1",
      },
    });

    expect(completed.entries).toHaveLength(1);
    expect(completed.entries[0]).toMatchObject({
      event_id: "event-001",
      job_status: "completed",
      result_id: "analysis-1",
      included: true,
    });
  });

  test("storage roundtrip retains at most the public export limit", () => {
    const storage = memoryStorage();
    const session = {
      ...createSessionHistory(true),
      entries: Array.from({ length: MAX_SESSION_EVENTS + 4 }, (_, index) => ({
        event_id: `event-${index}`,
      })),
    };

    expect(persistSessionHistory(session, storage)).toBe(true);
    expect(loadSessionHistory(storage).entries).toHaveLength(MAX_SESSION_EVENTS);
  });

  test("export contains selected server references but no display-only state", () => {
    let session = {
      ...createSessionHistory(true),
      session_label: "Checkpoint",
      entries: [
        {
          event_id: "event-001",
          job_id: "a".repeat(32),
          recorded_at: "2026-07-25T12:00:00Z",
          label: "CDC20",
          source_view: "analysis",
          design_summary: "not exported",
          included: true,
        },
        {
          event_id: "event-002",
          job_id: "b".repeat(32),
          recorded_at: "2026-07-25T12:01:00Z",
          label: "BIRC5",
          source_view: "pancancer",
          included: false,
        },
      ],
    };
    session = updateSessionEntry(session, "event-001", { label: "CDC20 OS" });
    const payload = buildSessionExportPayload(session);

    expect(payload.entries).toEqual([
      {
        event_id: "event-001",
        job_id: "a".repeat(32),
        recorded_at: "2026-07-25T12:00:00Z",
        label: "CDC20 OS",
        source_view: "analysis",
      },
    ]);
    expect(JSON.stringify(payload)).not.toContain("not exported");
    expect(beginNewSession(session).entries).toEqual([]);
    expect(beginNewSession(session).browser_session_id).not.toBe(
      session.browser_session_id,
    );
  });
});
