import { describe, expect, test } from "vitest";
import { scientificEstimate, scientificNumber } from "./scientificNumbers";

describe("scientific numbers", () => {
  test.each([null, undefined, "", " ", NaN, Infinity, false, [], {}])(
    "keeps an unavailable value (%s) distinct from zero",
    (value) => expect(scientificNumber(value)).toBeNull(),
  );
  test.each([0, "0", "0.00"])("preserves a reported zero (%s)", (value) => {
    expect(scientificNumber(value)).toBe(0);
  });
  test("preserves signed effects and numeric strings", () => {
    expect(scientificNumber(-0.7)).toBe(-0.7);
    expect(scientificNumber("1e-8")).toBe(1e-8);
  });
  test.each([[null, null, null], [1.2, null, 1.5], [1.2, 0.9, ""], [1.2, undefined, 1.5]])(
    "keeps a missing estimate or confidence limit unavailable: %s, %s, %s",
    (estimate, low, high) => expect(scientificEstimate(estimate, low, high)).toBe("..."),
  );
  test("formats complete estimates without treating measured zero as missing", () => {
    expect(scientificEstimate(1.2, 0.9, 1.5)).toBe("1.20 (0.90-1.50)");
    expect(scientificEstimate(0, -0.2, 0.2)).toBe("0.00 (-0.20-0.20)");
  });
});
