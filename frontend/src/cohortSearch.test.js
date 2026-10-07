import { describe, expect, it } from "vitest";
import { cohortMatchesQuery, cohortPickerCountLabel } from "./cohortSearch";

const gallbladder = { id: "FU-GBC", disease_type: "Gallbladder cancer", primary_site: "Gallbladder" };
const chol = { id: "TCGA-CHOL", disease_type: "Cholangiocarcinoma", primary_site: "Bile duct" };

describe("cohort discovery", () => {
  it.each([
    [38, "", "38 cancer types available for this analysis"],
    [38, "  ", "38 cancer types available for this analysis"],
    [1, "", "1 cancer type available for this analysis"],
    [1, "GBC", "1 cancer type matches your search"],
    [2, "cancer", "2 cancer types match your search"],
    [0, "unmatched", "0 cancer types match your search"],
  ])("labels %i visible types for query %s", (count, query, expected) => {
    expect(cohortPickerCountLabel(count, query)).toBe(expected);
  });

  it.each(["gallbladder", "gallblader", "gall bladder", "GBC", "FU-GBC", "vesícula", "vesicula biliar"])(
    "finds the external gallbladder cohort for %s without relabelling CHOL",
    (query) => {
      expect(cohortMatchesQuery(gallbladder, query)).toBe(true);
      expect(cohortMatchesQuery(chol, query)).toBe(false);
    },
  );

  it("matches words across fields regardless of case and order", () => {
    expect(cohortMatchesQuery(gallbladder, "  cancer   GBC  ")).toBe(true);
    expect(cohortMatchesQuery(chol, "cholangiocarcinoma TCGA")).toBe(true);
    expect(cohortMatchesQuery(gallbladder, "breast")).toBe(false);
    expect(cohortMatchesQuery(gallbladder, "")).toBe(true);
  });
});
