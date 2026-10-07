import { describe, expect, test } from "vitest";
import { resultSourceLabel } from "./resultSource";

const names = (code) => ({ "TCGA-LIHC": "Liver Hepatocellular Carcinoma" })[code] || code;

describe("resultSourceLabel", () => {
  test("TCGA results keep the cohort name and code", () => {
    expect(resultSourceLabel({ kind: "tcga", dataset_id: "TCGA-LIHC" }, "TCGA-LIHC", names)).toBe("Liver Hepatocellular Carcinoma (TCGA-LIHC)");
    expect(resultSourceLabel(undefined, "TCGA-LIHC", names)).toBe("Liver Hepatocellular Carcinoma (TCGA-LIHC)");
  });
  test("external and private results name the analyzed source, not the TCGA context", () => {
    expect(resultSourceLabel({ kind: "external", name: "Japanese primary liver cancer (ICGC LIRI-JP)" }, "TCGA-LIHC", names))
      .toBe("Japanese primary liver cancer (ICGC LIRI-JP) (external cohort)");
    expect(resultSourceLabel({ kind: "user", name: "KIRC synthetic quickstart" }, "TCGA-KIRC", names))
      .toBe("KIRC synthetic quickstart (private upload)");
  });
});
