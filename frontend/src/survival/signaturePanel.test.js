import { describe, expect, it } from "vitest";

import {
  buildSignaturePanelRequest,
  createPanelSignature,
  normalizePanelSignature,
  validateSignaturePanel,
} from "./signaturePanel";


describe("signature panel request", () => {
  it("normalizes weighted genes and removes duplicates", () => {
    const signature = normalizePanelSignature({
      name: "Effector",
      gene_symbol: "ifng:2, GZMB:-1, IFNG:4",
      signature_method: "weighted",
    });

    expect(signature.signature_genes).toEqual([
      { gene_symbol: "IFNG", weight: 2 },
      { gene_symbol: "GZMB", weight: -1 },
    ]);
    expect(signature.gene_symbol).toBe("IFNG:2, GZMB:-1");
  });

  it("requires 2 to 6 uniquely named and defined signatures", () => {
    expect(validateSignaturePanel([createPanelSignature(0)]).valid).toBe(false);
    const result = validateSignaturePanel([
      {
        ...createPanelSignature(0),
        name: "A",
        gene_symbol: "IFNG, GZMB",
      },
      {
        ...createPanelSignature(1),
        name: "a",
        gene_symbol: "PDCD1",
      },
    ]);
    expect(result.valid).toBe(false);
    expect(result.errors).toContain("Signature names must be unique.");

    const ambiguousSingle = validateSignaturePanel([
      { name: "A", gene_symbol: "IFNG, GZMB", signature_method: "single" },
      { name: "B", gene_symbol: "PDCD1", signature_method: "single" },
    ]);
    expect(ambiguousSingle.valid).toBe(false);
    expect(ambiguousSingle.errors[0]).toContain("requires exactly one gene");

    const invalidWeight = validateSignaturePanel([
      { name: "A", gene_symbol: "IFNG:not-a-number", signature_method: "weighted" },
      { name: "B", gene_symbol: "PDCD1", signature_method: "single" },
    ]);
    expect(invalidWeight.valid).toBe(false);
    expect(invalidWeight.errors[0]).toContain("Invalid weight");
  });

  it("serializes directional rank signatures explicitly", () => {
    const signature = normalizePanelSignature({
      name: "Immune balance",
      gene_symbol: "IFNG, GZMB:1, TGFB1:-1",
      signature_method: "singscore",
    });

    expect(signature.gene_symbol).toBe("IFNG, GZMB, TGFB1:-1");
    expect(signature.signature_genes).toEqual([
      { gene_symbol: "IFNG", weight: 1, direction: "up" },
      { gene_symbol: "GZMB", weight: 1, direction: "up" },
      { gene_symbol: "TGFB1", weight: -1, direction: "down" },
    ]);
  });

  it("builds one common design request without grouping fields", () => {
    const form = {
      cohort: "TCGA-SKCM",
      dataset_id: null,
      dataset_release_id: null,
      expression_layer_id: null,
      signature_panel: { name: "Immune panel" },
      endpoint: "OS",
      expression_scale: "log2_tpm",
      filters: {
        sample_types: [],
        stages: [],
        grades: [],
        genders: [],
        races: [],
        age_min: "",
        age_max: "80",
        max_time_days: "",
      },
      adjustment_covariates: ["age_at_index", "stage", "stage"],
      external_covariates: null,
      external_adjustment_covariates: [],
      time_unit: "days",
    };
    const request = buildSignaturePanelRequest({
      form,
      signatures: [
        { name: "A", gene_symbol: "IFNG", signature_method: "single" },
        { name: "B", gene_symbol: "PDCD1, LAG3", signature_method: "zscore" },
      ],
      plotStyle: { cox_forest: { model_layout: "combined" } },
    });

    expect(request.signatures).toHaveLength(2);
    expect(request.adjustment_covariates).toEqual(["age_at_index", "stage"]);
    expect(request.filters.age_max).toBe(80);
    expect(request).not.toHaveProperty("cutpoint_method");
    expect(request).not.toHaveProperty("combination_method");
  });
});
