import { describe, expect, test } from "vitest";

import {
  SAMPLE_POPULATION_CONTRACT_VERSION,
  defaultSamplePopulation,
  molecularPopulationSummary,
  requiresSamplePopulation,
} from "./samplePopulation";

describe("TCGA molecular-population contract", () => {
  test("uses disease-specific defaults without treating SKCM as homogeneous", () => {
    expect(defaultSamplePopulation("TCGA-BRCA")).toBe("primary_solid");
    expect(defaultSamplePopulation("TCGA-LAML")).toBe("primary_blood");
    expect(defaultSamplePopulation("TCGA-SKCM")).toBeNull();
    expect(defaultSamplePopulation("TCGA-SKCM", "external-release")).toBeNull();
  });

  test("blocks an explicit-population cohort until the user chooses", () => {
    const filters = {
      population_selection_required: true,
      sample_populations: [],
    };
    const form = {
      cohort: "TCGA-SKCM",
      dataset_id: null,
      filters: { sample_population: null },
    };

    expect(requiresSamplePopulation(form, filters)).toBe(true);
    expect(molecularPopulationSummary(form, filters)).toMatchObject({
      label: "Population required",
      blocking: true,
    });
  });

  test("reports the selected population using server-attested counts", () => {
    const population = {
      id: "metastatic",
      label: "Metastatic tumor",
      patient_count: 366,
      allowed_tcga_sample_codes: ["06", "07"],
      contract_version: SAMPLE_POPULATION_CONTRACT_VERSION,
    };
    const summary = molecularPopulationSummary(
      {
        cohort: "TCGA-SKCM",
        dataset_id: null,
        filters: { sample_population: "metastatic" },
      },
      { sample_populations: [population] },
    );

    expect(summary.label).toBe("Metastatic tumor");
    expect(summary.detail).toContain("366 patients");
    expect(summary.detail).toContain("06/07");
    expect(summary.blocking).toBe(false);
  });
});
