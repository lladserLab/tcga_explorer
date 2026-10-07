import { describe, expect, test } from "vitest";

import {
  analysisFilterState,
  batchCapacityState,
  hierarchicalThresholdState,
  panCancerInputsFromSurvivalForm,
  panCancerSignatureInputState,
  parseSignatureGenesStrict,
  percentileInputState,
  plotStyleInputState,
  referencePanCancerInputState,
  signatureInputState,
} from "./analysisRequestContract";

describe("shared analysis request validation", () => {
  test("distinguishes an optional blank from an invalid written filter", () => {
    expect(analysisFilterState({ age_min: "" }).valid).toBe(true);
    expect(analysisFilterState({ age_min: "abc" }).errors[0]).toContain("must be a number");
  });

  test("rejects reversed ages, nonpositive follow-up and reversed custom ranges", () => {
    expect(analysisFilterState({ age_min: 80, age_max: 40 }).valid).toBe(false);
    expect(analysisFilterState({ max_time_days: 0 }).valid).toBe(false);
    expect(analysisFilterState({
      custom_filters: [{ variable_id: "score", numeric_min: 8, numeric_max: 2 }],
    }).valid).toBe(false);
  });

  test("validates only an active percentile", () => {
    expect(percentileInputState(false, "")).toEqual({ valid: true, value: null, error: "" });
    expect(percentileInputState(true, "").valid).toBe(false);
    expect(percentileInputState(true, 75).value).toBe(75);
  });

  test("rejects zero or malformed weights", () => {
    expect(() => parseSignatureGenesStrict("CA9:0, VEGFA:-1")).toThrow("weight 0");
    expect(() => parseSignatureGenesStrict("CA9:nope")).toThrow("Invalid weight");
    expect(() => parseSignatureGenesStrict("CA9:1:2")).toThrow("more than one");
    expect(signatureInputState("CA9:2", { allowWeights: false }).valid).toBe(false);
  });

  test("validates rank direction against every selected scoring method", () => {
    expect(signatureInputState("IFNG, TGFB1:-1", {
      method: "singscore",
    })).toMatchObject({
      valid: true,
      direction_counts: { up: 1, down: 1 },
    });
    expect(signatureInputState("IFNG:2, GZMB", {
      methods: ["weighted", "aucell"],
    }).errors).toEqual(expect.arrayContaining([
      expect.stringMatching(/AUCell uses direction only/),
    ]));
  });

  test("projects signed genes across mixed Robustness scoring methods", () => {
    const result = signatureInputState("IFNG, GZMB:-1", {
      methods: ["mean", "zscore", "weighted", "singscore"],
    });
    expect(result.valid).toBe(true);
    expect(result.genes).toEqual([
      { gene_symbol: "IFNG", weight: 1, direction: "up" },
      { gene_symbol: "GZMB", weight: -1, direction: "down" },
    ]);
    expect(result.warnings).toContain(
      "Mean ignores declared directions or coefficients; the other selected methods retain their signed input.",
    );
  });

  test("keeps mixed rank inputs directional while rejecting ambiguous magnitudes", () => {
    expect(signatureInputState("IFNG:2, GZMB:-1", {
      methods: ["mean", "weighted", "singscore"],
    }).errors).toEqual(expect.arrayContaining([
      expect.stringMatching(/singscore uses direction only/),
    ]));
    expect(signatureInputState("IFNG:-1, GZMB", {
      method: "mean",
    }).errors[0]).toMatch(/does not use weights/);
  });

  test("matches public batch capacity", () => {
    expect(batchCapacityState(5, 5).valid).toBe(true);
    expect(batchCapacityState(6, 5)).toMatchObject({ valid: false, analyses: 30 });
  });

  test("rejects blank or out-of-range plot and pan-cancer controls", () => {
    expect(plotStyleInputState({
      base_font_size: "",
      axis_text_size: 11,
      axis_title_size: 12,
    }).valid).toBe(false);
    expect(referencePanCancerInputState({
      min_patients: 10,
      min_events: 5,
      fdr_threshold: 1.1,
    }).valid).toBe(false);
    expect(hierarchicalThresholdState({
      min_patients: "",
      min_events: 10,
      min_censored: 5,
      fdr_threshold: 0.05,
    }).valid).toBe(false);
  });

  test.each([
    ["mean", "IFNG, CXCL9", [{ gene_symbol: "IFNG", weight: 1 }, { gene_symbol: "CXCL9", weight: 1 }]],
    ["zscore", "IFNG:2, TGFB1:-1", [{ gene_symbol: "IFNG", weight: 2 }, { gene_symbol: "TGFB1", weight: -1 }]],
    ["weighted", "IFNG:0.5, TGFB1:-2", [{ gene_symbol: "IFNG", weight: 0.5 }, { gene_symbol: "TGFB1", weight: -2 }]],
    ["singscore", "IFNG, TGFB1:-1", [{ gene_symbol: "IFNG", weight: 1, direction: "up" }, { gene_symbol: "TGFB1", weight: -1, direction: "down" }]],
    ["ssgsea", "IFNG, GZMB, IL10:-1, TGFB1:-1", [
      { gene_symbol: "IFNG", weight: 1, direction: "up" },
      { gene_symbol: "GZMB", weight: 1, direction: "up" },
      { gene_symbol: "IL10", weight: -1, direction: "down" },
      { gene_symbol: "TGFB1", weight: -1, direction: "down" },
    ]],
    ["aucell", "IFNG, TGFB1:-1", [{ gene_symbol: "IFNG", weight: 1, direction: "up" }, { gene_symbol: "TGFB1", weight: -1, direction: "down" }]],
  ])("builds the %s TCGA reference signature contract", (method, input, genes) => {
    const result = panCancerSignatureInputState(input, method);
    expect(result.valid).toBe(true);
    expect(result.value).toMatchObject({
      signature_method: method,
      signature_genes: genes,
    });
  });

  test("keeps TCGA reference directions and weights but leaves single-gene mode narrow", () => {
    expect(panCancerSignatureInputState("IFNG:2, TGFB1:-1", "weighted").value)
      .toMatchObject({ gene_symbol: "IFNG:2, TGFB1:-1" });
    expect(panCancerSignatureInputState("IFNG, TGFB1:-1", "singscore").value)
      .toMatchObject({ gene_symbol: "IFNG:1, TGFB1:-1" });
    expect(panCancerSignatureInputState("IFNG, GZMB", "single").errors[0])
      .toMatch(/exactly one gene/);
  });

  test("adds the scoring contract to a valid TCGA reference request", () => {
    const result = referencePanCancerInputState({
      gene_symbol: "IFNG, TGFB1:-1",
      signature_method: "singscore",
      min_patients: 10,
      min_events: 5,
      fdr_threshold: 0.1,
    });
    expect(result.valid).toBe(true);
    expect(result.value.signature_method).toBe("singscore");
    expect(result.value.signature_genes).toHaveLength(2);
  });

  test("copies the complete current survival signature without losing weights or directions", () => {
    expect(panCancerInputsFromSurvivalForm({
      analysis_kind: "single_signature",
      gene_symbol: "IFNG, TGFB1:-1",
      signature_method: "singscore",
    }).value).toMatchObject({
      gene_symbol: "IFNG:1, TGFB1:-1",
      signature_method: "singscore",
      signature_genes: [
        { gene_symbol: "IFNG", weight: 1, direction: "up" },
        { gene_symbol: "TGFB1", weight: -1, direction: "down" },
      ],
    });
    expect(panCancerInputsFromSurvivalForm({
      analysis_kind: "combined_signatures",
    }).errors[0]).toMatch(/not a two-signature interaction/);
  });
});
