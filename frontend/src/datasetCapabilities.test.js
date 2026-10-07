import { describe, expect, test } from "vitest";

import {
  availableDatasetModules,
  cohortSupportsModule,
  datasetCapability,
  datasetSupportsModule,
  filterDatasetsForModule,
} from "./datasetCapabilities";

const MOLECULAR_ONLY = {
  id: "molecular-only",
  tcga_cohort: "EXT-GBC",
  gene_count: 18000,
  endpoints: [],
  capabilities: {
    survival: {
      available: false,
      reason: "No documented time-to-event endpoint was released.",
    },
    expression_comparison: { available: true },
    gsea: { available: true },
  },
  available_modules: ["expression", "gsea"],
};

describe("dataset capability contract", () => {
  test("keeps molecular-only cohorts available without inventing survival", () => {
    expect(datasetSupportsModule(MOLECULAR_ONLY, "analysis")).toBe(false);
    expect(datasetSupportsModule(MOLECULAR_ONLY, "compare")).toBe(false);
    expect(datasetSupportsModule(MOLECULAR_ONLY, "multiverse")).toBe(false);
    expect(datasetSupportsModule(MOLECULAR_ONLY, "expression")).toBe(true);
    expect(datasetSupportsModule(MOLECULAR_ONLY, "gsea")).toBe(true);
    expect(datasetCapability(MOLECULAR_ONLY, "analysis").reason).toBe(
      "No documented time-to-event endpoint was released.",
    );
  });

  test("treats available_modules as the module-level authority", () => {
    const dataset = {
      ...MOLECULAR_ONLY,
      capabilities: { survival: { available: true } },
      available_modules: ["analysis", "compare"],
    };
    expect(datasetSupportsModule(dataset, "analysis")).toBe(true);
    expect(datasetSupportsModule(dataset, "compare")).toBe(true);
    expect(datasetSupportsModule(dataset, "multiverse")).toBe(false);
  });

  test("supports older release payloads through conservative evidence fallbacks", () => {
    const legacy = {
      expression_layer: { layer_id: "rna" },
      gene_count: 12000,
      endpoints: [{ value: "OS", available: true }],
    };
    expect(availableDatasetModules(legacy).map((item) => item.id)).toEqual([
      "analysis",
      "compare",
      "expression",
      "gsea",
      "multiverse",
    ]);
  });

  test("filters external-only cancer contexts by the active module", () => {
    const cohort = { id: "EXT-GBC", status: "external_only" };
    expect(cohortSupportsModule(cohort, [MOLECULAR_ONLY], "gsea")).toBe(true);
    expect(cohortSupportsModule(cohort, [MOLECULAR_ONLY], "analysis")).toBe(false);
    expect(filterDatasetsForModule([MOLECULAR_ONLY], "expression")).toHaveLength(1);
    expect(filterDatasetsForModule([MOLECULAR_ONLY], "compare")).toHaveLength(0);
  });
});
