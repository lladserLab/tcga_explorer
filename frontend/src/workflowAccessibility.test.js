import { describe, expect, test } from "vitest";
import { activeWorkflowPanelId } from "./workflowAccessibility";

describe("workflow step accessibility", () => {
  test("references only the panel currently rendered", () => {
    expect(activeWorkflowPanelId("analysis-step", "data", true)).toBe(
      "analysis-step-panel-data",
    );
    expect(activeWorkflowPanelId("analysis-step", "outcome", false)).toBeUndefined();
  });

  test("does not emit incomplete ID references", () => {
    expect(activeWorkflowPanelId("", "data", true)).toBeUndefined();
    expect(activeWorkflowPanelId("analysis-step", "", true)).toBeUndefined();
  });
});
