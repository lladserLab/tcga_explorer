import { describe, expect, test } from "vitest";

import {
  colorForNes,
  dotPlotSizeValue,
  dotRadiusForSignificance,
  geneCompletionContext,
  negativeLog10Fdr,
  replaceGeneCompletion,
  signatureGeneSymbols,
  topDotPlotPathways,
} from "./gseaUi";

describe("GSEA gene completion", () => {
  test("replaces only the active gene and preserves every weight", () => {
    const source = "CA9:1.5, veg:-2; SLC2A1:0.25";
    const caret = source.indexOf("veg") + 2;
    const completed = replaceGeneCompletion(source, caret, "VEGFA");

    expect(completed.value).toBe("CA9:1.5, VEGFA:-2; SLC2A1:0.25");
    expect(completed.cursor).toBe(completed.value.indexOf(":-2") + 3);
    expect(signatureGeneSymbols(completed.value)).toEqual([
      "CA9",
      "VEGFA",
      "SLC2A1",
    ]);
  });

  test("derives the search query from the token at the caret", () => {
    const source = "TP53, BR";
    expect(geneCompletionContext(source, source.length)).toMatchObject({
      query: "BR",
      weightSuffix: "",
      start: 5,
      end: 8,
    });
  });

  test("reads pasted spreadsheet rows and tabs as signature genes", () => {
    expect(signatureGeneSymbols("tp53\tKRAS\nEGFR pik3ca")).toEqual([
      "TP53",
      "KRAS",
      "EGFR",
      "PIK3CA",
    ]);
  });
});

describe("GSEA dot-plot encodings", () => {
  test("never ranks missing FDR or NES as a significant measured pathway", () => {
    const pathways = [
      { pathway: "VALID", nes: 1.2, fdr: 0.04 },
      { pathway: "NO_FDR", nes: 1.2, fdr: null },
      { pathway: "NO_NES", nes: null, fdr: 0.01 },
      { pathway: "BLANK_FDR", nes: 1.2, fdr: "" },
      { pathway: "ZERO_NES", nes: 0, fdr: 0.05 },
    ];
    expect(negativeLog10Fdr(null)).toBeNull();
    expect(dotPlotSizeValue("")).toBeNull();
    expect(topDotPlotPathways(pathways).map((row) => row.pathway)).toEqual(["VALID", "ZERO_NES"]);
  });

  test("maps circle area, rather than radius, to negative log10 FDR", () => {
    const one = negativeLog10Fdr(0.1);
    const four = negativeLog10Fdr(0.0001);
    const radiusOne = dotRadiusForSignificance(one, four);
    const radiusFour = dotRadiusForSignificance(four, four);

    expect(one).toBeCloseTo(1);
    expect(four).toBeCloseTo(4);
    expect((radiusFour ** 2) / (radiusOne ** 2)).toBeCloseTo(4);
    expect(dotPlotSizeValue(1e-12)).toBe(10);
    expect(dotPlotSizeValue(1)).toBe(0);
  });

  test("uses a continuous signed NES color and keeps the top 30 by FDR", () => {
    const pathways = Array.from({ length: 35 }, (_, index) => ({
      pathway: `PATH_${index}`,
      nes: index % 2 ? -1 - index / 100 : 1 + index / 100,
      fdr: (35 - index) / 100,
    }));
    const rows = topDotPlotPathways(pathways);

    expect(rows).toHaveLength(30);
    expect(rows[0].pathway).toBe("PATH_34");
    expect(rows.at(-1).pathway).toBe("PATH_5");
    expect(colorForNes(-2, 2)).toBe("#00008b");
    expect(colorForNes(0, 2)).toBe("#ffffff");
    expect(colorForNes(2, 2)).toBe("#ff0000");
    expect(colorForNes(-1, 2)).not.toBe(colorForNes(1, 2));
    expect(colorForNes(0.5, 2)).not.toBe(colorForNes(1, 2));
  });
});
