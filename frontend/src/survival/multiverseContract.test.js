import { describe, expect, test } from "vitest";
import {
  multiversePercentileState,
  multiverseSignatureProjection,
} from "./multiverseContract";

describe("Robustness percentile contract", () => {
  test("blocks an empty percentile when that cutpoint is selected", () => {
    expect(multiversePercentileState(["median", "percentile"], "")).toEqual({
      selected: true,
      value: 0,
      valid: false,
      requestValue: 60,
    });
  });

  test("retains a valid declared percentile", () => {
    expect(multiversePercentileState(["percentile"], "75")).toEqual({
      selected: true,
      value: 75,
      valid: true,
      requestValue: 75,
    });
  });

  test("sends a valid neutral value when percentile is outside the family", () => {
    expect(multiversePercentileState(["median"], "")).toEqual({
      selected: false,
      value: 0,
      valid: true,
      requestValue: 60,
    });
  });
});

describe("Robustness signature projection", () => {
  test("retains rank direction for every downstream scoring projection", () => {
    expect(multiverseSignatureProjection("IFNG, GZMB:-1", [
      "mean",
      "zscore",
      "weighted",
      "singscore",
    ])).toEqual([
      { gene_symbol: "IFNG", weight: 1, direction: "up" },
      { gene_symbol: "GZMB", weight: -1, direction: "down" },
    ]);
  });

  test("retains coefficients for weighted families without a rank method", () => {
    expect(multiverseSignatureProjection("IFNG:2, GZMB:-0.5", [
      "mean",
      "weighted",
    ])).toEqual([
      { gene_symbol: "IFNG", weight: 2 },
      { gene_symbol: "GZMB", weight: -0.5 },
    ]);
  });

  test("fails closed for non-unit rank magnitudes and mean-only qualifiers", () => {
    expect(() => multiverseSignatureProjection("IFNG:2, GZMB", [
      "weighted",
      "singscore",
    ])).toThrow(/direction only/);
    expect(() => multiverseSignatureProjection("IFNG:-1, GZMB", ["mean"]))
      .toThrow(/does not use weights/);
  });
});
