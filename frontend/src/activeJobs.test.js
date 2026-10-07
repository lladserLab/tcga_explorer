import { beforeEach, describe, expect, test, vi } from "vitest";

import {
  ACTIVE_JOB_STORAGE_KEY,
  clearActiveJob,
  latestActiveJob,
  loadActiveJobs,
  recordActiveJobUpdate,
  updateRecordedActiveJob,
} from "./activeJobs";

function memoryStorage() {
  const values = new Map();
  return {
    getItem: (key) => values.get(key) || null,
    setItem: (key, value) => values.set(key, value),
  };
}

describe("active analysis recovery ledger", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-08-08T12:00:00Z"));
  });

  test("stores only operational metadata and updates one event in place", () => {
    const storage = memoryStorage();
    const detail = {
      event_id: "event-1",
      recorded_at: "2026-08-08T11:59:00Z",
      summary: {
        source_view: "gsea",
        label: "Luminal A vs Basal",
        design_summary: "TCGA-BRCA · clinical · GO:BP",
      },
      job: { id: "job-1", kind: "gsea", status: "queued", result: { private: true } },
    };
    recordActiveJobUpdate(detail, storage);
    updateRecordedActiveJob(
      latestActiveJob("gsea", storage),
      { id: "job-1", kind: "gsea", status: "running", result: { private: true } },
      storage,
    );

    expect(loadActiveJobs(storage)).toEqual([
      expect.objectContaining({
        event_id: "event-1",
        job_id: "job-1",
        job_status: "running",
        source_view: "gsea",
      }),
    ]);
    expect(storage.getItem(ACTIVE_JOB_STORAGE_KEY)).not.toContain("private");
  });

  test("clears a recovered job without affecting another module", () => {
    const storage = memoryStorage();
    [
      ["event-gsea", "job-gsea", "gsea"],
      ["event-expression", "job-expression", "expression"],
    ].forEach(([eventId, jobId, sourceView]) => {
      recordActiveJobUpdate({
        event_id: eventId,
        summary: { source_view: sourceView },
        job: { id: jobId, status: "running" },
      }, storage);
    });

    expect(clearActiveJob("event-gsea", storage)).toBe(true);
    expect(latestActiveJob("gsea", storage)).toBeNull();
    expect(latestActiveJob("expression", storage)?.job_id).toBe("job-expression");
  });
});
