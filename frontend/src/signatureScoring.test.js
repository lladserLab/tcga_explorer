import { describe, expect, test } from "vitest";

import {
  MULTI_GENE_SIGNATURE_METHOD_OPTIONS,
  RANK_SCORING_UNAVAILABLE_MESSAGE,
  inspectSignatureGeneInput,
  normalizeSignatureInput,
  rankScoringAvailability,
  signatureMethodDefinition,
  signatureMethodInputHint,
} from "./signatureScoring";

describe("signature scoring contract", () => {
  test("publishes the rank methods in their intended order", () => {
    expect(MULTI_GENE_SIGNATURE_METHOD_OPTIONS.map((item) => item.value)).toEqual([
      "singscore",
      "ssgsea",
      "aucell",
      "mean",
      "zscore",
      "weighted",
    ]);
    expect(MULTI_GENE_SIGNATURE_METHOD_OPTIONS.find((item) => item.value === "singscore"))
      .toMatchObject({ recommended: true });
    expect(MULTI_GENE_SIGNATURE_METHOD_OPTIONS.find((item) => item.value === "aucell"))
      .toMatchObject({ sensitivity: true });
  });

  test("rejects zero weights before a method can silently ignore them", () => {
    expect(() => inspectSignatureGeneInput("IFNG:0, GZMB")).toThrow(/weight 0/);
  });

  test("keeps the first duplicate and reports it", () => {
    const result = normalizeSignatureInput("ifng, GZMB, IFNG", "singscore");
    expect(result.valid).toBe(true);
    expect(result.genes.map((gene) => gene.gene_symbol)).toEqual(["IFNG", "GZMB"]);
    expect(result.duplicate_queries).toEqual(["IFNG"]);
    expect(result.warnings[0]).toMatch(/first occurrence/);
  });

  test("turns unit signs into explicit up and down directions", () => {
    const result = normalizeSignatureInput(
      "IFNG, GZMB:1, TGFB1:-1",
      "singscore",
    );
    expect(result.valid).toBe(true);
    expect(result.genes).toEqual([
      { gene_symbol: "IFNG", weight: 1, direction: "up" },
      { gene_symbol: "GZMB", weight: 1, direction: "up" },
      { gene_symbol: "TGFB1", weight: -1, direction: "down" },
    ]);
    expect(result.direction_counts).toEqual({ up: 2, down: 1 });
  });

  test("rank methods reject non-unit magnitudes", () => {
    const result = normalizeSignatureInput("IFNG:2, GZMB", "ssgsea");
    expect(result.valid).toBe(false);
    expect(result.errors[0]).toMatch(/direction only/);
  });

  test("ssGSEA requires two genes in every declared direction", () => {
    expect(normalizeSignatureInput("IFNG, GZMB", "ssgsea").valid).toBe(true);
    expect(normalizeSignatureInput("IFNG, GZMB, TGFB1:-1", "ssgsea").errors)
      .toContain("ssGSEA requires at least 2 down genes when that component is present.");
  });

  test("plain methods reject qualifiers and weighted methods retain magnitude", () => {
    expect(normalizeSignatureInput("IFNG:1, GZMB", "mean").errors[0])
      .toMatch(/does not use weights/);
    expect(normalizeSignatureInput("IFNG:2, GZMB:-0.5", "weighted").genes)
      .toEqual([
        { gene_symbol: "IFNG", weight: 2 },
        { gene_symbol: "GZMB", weight: -0.5 },
      ]);
  });

  test("the inline guidance distinguishes direction from magnitude", () => {
    expect(signatureMethodInputHint("singscore")).toMatch(/GENE:-1 marks down/);
    expect(signatureMethodInputHint("weighted")).toMatch(/GENE:weight/);
    expect(signatureMethodInputHint("mean")).toBe("Enter gene symbols without weights.");
  });

  test("blocks rank scoring for a targeted expression layer with a human reason", () => {
    const availability = rankScoringAvailability({ gene_count: 420 });
    expect(availability.available).toBe(false);
    expect(availability.reason).toMatch(/complete expression matrix/);
    const unattestedBroad = rankScoringAvailability({ gene_count: 18000 });
    expect(unattestedBroad.available).toBe(false);
    expect(unattestedBroad.reason).toMatch(/could not verify/);
  });

  test("honors the canonical rank-scoring capability for targeted uploads", () => {
    const unavailable = rankScoringAvailability({
      capabilities: {
        rank_based_signature_scoring: {
          available: false,
          gene_count: 420,
          minimum_genes: 1000,
          reason: "Targeted upload has 420 genes.",
        },
      },
    });
    expect(unavailable).toEqual({
      available: false,
      reason: "Targeted upload has 420 genes.",
      detail: "Targeted upload has 420 genes.",
      missingValueCount: null,
      matrixEntryCount: null,
      maximumMatrixEntries: null,
    });
    expect(rankScoringAvailability({
      capabilities: {
        rank_based_signature_scoring: {
          available: true,
          gene_count: 18000,
          missing_value_count: 0,
          complete_matrix_verified: true,
        },
      },
    }).available).toBe(true);
  });

  test("uses the selected layer capability instead of a dataset-wide maximum", () => {
    const dataset = {
      capabilities: {
        rank_based_signature_scoring: {
          available: true,
          gene_count: 18000,
          missing_value_count: 0,
          complete_matrix_verified: true,
        },
      },
    };
    const narrow = {
      value: "targeted",
      gene_count: 420,
      capabilities: {
        rank_based_signature_scoring: {
          available: false,
          gene_count: 420,
          missing_value_count: 0,
          complete_matrix_verified: true,
          reason: "The selected layer contains 420 genes.",
        },
      },
    };
    const broad = {
      value: "transcriptome",
      gene_count: 18000,
      capabilities: {
        rank_based_signature_scoring: {
          available: true,
          gene_count: 18000,
          missing_value_count: 0,
          complete_matrix_verified: true,
        },
      },
    };

    expect(rankScoringAvailability(dataset, null, narrow)).toMatchObject({
      available: false,
      reason: "The selected layer contains 420 genes.",
    });
    expect(rankScoringAvailability(dataset, null, broad)).toMatchObject({
      available: true,
      missingValueCount: 0,
    });
  });

  test("fails closed when a broad selected layer has missing values", () => {
    const availability = rankScoringAvailability(
      { capabilities: {} },
      null,
      {
        value: "broad-with-missing",
        gene_count: 18000,
        capabilities: {
          rank_based_signature_scoring: {
            available: true,
            gene_count: 18000,
            missing_value_count: 7,
            complete_matrix_verified: false,
            reason: "The selected expression layer contains 7 missing or non-finite values.",
          },
        },
      },
    );

    expect(availability).toMatchObject({
      available: false,
      missingValueCount: 7,
    });
    expect(availability.reason).toMatch(/7 missing or non-finite values/);
  });

  test("blocks a selected layer that exceeds the engine matrix limit", () => {
    const availability = rankScoringAvailability(
      { capabilities: {} },
      null,
      {
        value: "scan-b",
        capabilities: {
          rank_based_signature_scoring: {
            available: true,
            gene_count: 20_001,
            sample_count: 5_050,
            matrix_entry_count: 101_005_050,
            maximum_matrix_entries: 50_000_000,
            missing_value_count: 0,
            complete_matrix_verified: true,
            reason: null,
          },
        },
      },
    );

    expect(availability).toMatchObject({
      available: false,
      matrixEntryCount: 101_005_050,
      maximumMatrixEntries: 50_000_000,
    });
    expect(availability.reason).toMatch(/101,005,050 matrix entries/);
  });

  test("labels ssGSEA in biological rather than implementation language", () => {
    expect(signatureMethodDefinition("ssgsea").optionLabel)
      .toBe("ssGSEA · sample-wise enrichment");
  });
});
