import { describe, expect, test } from "vitest";

import {
  isGeneListClipboardValue,
  mergeClipboardGeneList,
  normalizeClipboardGeneList,
  parseClipboardGeneList,
} from "./geneListClipboard";

describe("gene-list clipboard handling", () => {
  test("accepts spreadsheet rows, tabs, spaces, commas and semicolons", () => {
    expect(
      parseClipboardGeneList("tp53\tKRAS\nEGFR, pik3ca; PTEN BRCA1"),
    ).toEqual(["TP53", "KRAS", "EGFR", "PIK3CA", "PTEN", "BRCA1"]);
  });

  test("deduplicates symbols and preserves the last pasted weight", () => {
    expect(
      mergeClipboardGeneList("CA9:1, VEGFA", "ca9:2\nSLC2A1:0.5"),
    ).toBe("CA9:2, VEGFA, SLC2A1:0.5");
  });

  test("can remove weights and enforce a selection limit", () => {
    expect(
      mergeClipboardGeneList("TP53", "KRAS:2 EGFR", {
        allowWeights: false,
        maximum: 2,
      }),
    ).toBe("TP53, KRAS");
    expect(normalizeClipboardGeneList("'ca9'\n\"vegfa\"")).toBe("CA9, VEGFA");
  });

  test("distinguishes one symbol from a pasted list", () => {
    expect(isGeneListClipboardValue("TP53")).toBe(false);
    expect(isGeneListClipboardValue("TP53\nKRAS")).toBe(true);
  });
});
