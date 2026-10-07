import { describe, expect, test } from "vitest";
import {
  compareResultsRequireRerun,
  plotStyleFingerprint,
} from "./plotRunContract";

describe("Compare plot run contract", () => {
  test("treats equivalent payloads as the same regardless of object key order", () => {
    expect(plotStyleFingerprint({ cox_forest: { model_layout: "combined", multivariable_display: "all" } }))
      .toBe(plotStyleFingerprint({ cox_forest: { multivariable_display: "all", model_layout: "combined" } }));
  });

  test("requires a new run after the selected multivariable rows change", () => {
    const recordedFingerprint = plotStyleFingerprint({
      cox_forest: { multivariable_display: "selected", multivariable_model_ids: ["stage_adjusted"] },
    });
    const currentFingerprint = plotStyleFingerprint({
      cox_forest: { multivariable_display: "selected", multivariable_model_ids: ["grade_adjusted"] },
    });
    expect(compareResultsRequireRerun({
      resultCount: 4,
      recordedFingerprint,
      currentFingerprint,
    })).toBe(true);
  });

  test("does not mark an empty result set as stale", () => {
    expect(compareResultsRequireRerun({
      resultCount: 0,
      recordedFingerprint: "previous",
      currentFingerprint: "current",
    })).toBe(false);
  });
});
