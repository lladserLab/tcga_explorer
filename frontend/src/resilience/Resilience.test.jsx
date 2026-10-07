// @vitest-environment jsdom

import React from "react";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import { getComputeJob } from "../api";
import { loadActiveJobs, recordActiveJobUpdate } from "../activeJobs";
import { ActiveJobRecovery, ModuleErrorBoundary, ServiceStatusNotice } from "./Resilience";

vi.mock("../api", () => ({
  getComputeJob: vi.fn(),
}));

afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllEnvs(); });

function BrokenModule() {
  throw new Error("render failed");
}

describe("release resilience surfaces", () => {
  beforeEach(() => {
    window.localStorage.clear();
    vi.mocked(getComputeJob).mockReset();
  });

  test("local analyses remain usable without internet but engine failures stay visible", () => {
    vi.stubEnv("VITE_TRACE_LOCAL_DESKTOP", "true");
    vi.spyOn(window.navigator, "onLine", "get").mockReturnValue(false);
    const { rerender } = render(<ServiceStatusNotice state={{ status: "ready" }} />);
    expect(screen.queryByText("You are offline")).toBeNull();
    rerender(<ServiceStatusNotice state={{ status: "unavailable" }} onRetry={vi.fn()} />);
    expect(screen.getByText("TRACE services are unavailable")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Retry" })).toBeTruthy();
  });

  test("the web still explains that new analyses need a connection", () => {
    vi.stubEnv("VITE_TRACE_LOCAL_DESKTOP", "false");
    vi.spyOn(window.navigator, "onLine", "get").mockReturnValue(false);
    render(<ServiceStatusNotice state={{ status: "ready" }} />);
    expect(screen.getByRole("alert").textContent).toContain("You are offline");
  });

  test("keeps navigation context alive when a module render fails", () => {
    const error = vi.spyOn(console, "error").mockImplementation(() => {});
    render(
      <ModuleErrorBoundary resetKey="gsea" moduleName="GSEA">
        <BrokenModule />
      </ModuleErrorBoundary>,
    );
    expect(screen.getByRole("heading", { name: "GSEA could not be displayed" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Try this module again" })).toBeTruthy();
    error.mockRestore();
  });

  test("recovers a completed server job and clears its local pointer", async () => {
    const user = userEvent.setup();
    const onRecover = vi.fn();
    recordActiveJobUpdate({
      event_id: "event-gsea",
      recorded_at: "2026-08-08T12:00:00Z",
      summary: {
        source_view: "gsea",
        label: "Luminal A vs Basal",
        design_summary: "TCGA-BRCA · GO:BP",
      },
      job: { id: "job-gsea", kind: "gsea", status: "running" },
    });
    vi.mocked(getComputeJob).mockResolvedValue({
      id: "job-gsea",
      kind: "gsea",
      status: "completed",
      result: { gsea_id: "gsea-result" },
    });

    render(<ActiveJobRecovery sourceView="gsea" onRecover={onRecover} />);
    const open = await screen.findByRole("button", { name: "Open result" });
    await user.click(open);

    expect(onRecover).toHaveBeenCalledWith(
      { gsea_id: "gsea-result" },
      expect.objectContaining({ id: "job-gsea" }),
      expect.objectContaining({ event_id: "event-gsea" }),
    );
    await waitFor(() => expect(loadActiveJobs()).toEqual([]));
  });
});
