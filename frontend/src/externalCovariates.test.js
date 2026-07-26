import { describe, expect, it } from "vitest";

import {
  changeExternalCovariateType,
  parseExternalCovariateCsv,
  reorderExternalCovariateLevel,
} from "./externalCovariates";

const VALID_CSV = `patient_id,idh_status,tumor_purity,molecular_risk
TCGA-AB-0001,Mutant,0.72,High
TCGA-AB-0002,Wild type,,Low
TCGA-AB-0003,Mutant,0.61,Intermediate
`;

describe("external covariate CSV", () => {
  it("parses exact TCGA barcodes and infers numeric and categorical variables", () => {
    const dataset = parseExternalCovariateCsv(
      VALID_CSV,
      "LGG annotations.csv",
    );

    expect(dataset.source_label).toBe("LGG annotations.csv");
    expect(dataset.rows).toHaveLength(3);
    expect(dataset.rows[0].patient_id).toBe("TCGA-AB-0001");
    expect(dataset.rows[0].values.tumor_purity).toBe(0.72);
    expect(dataset.rows[1].values.tumor_purity).toBeNull();
    expect(
      dataset.definitions.find((item) => item.name === "idh_status"),
    ).toMatchObject({
      value_type: "categorical",
      levels: ["Mutant", "Wild type"],
      reference_level: "Mutant",
    });
    expect(
      dataset.definitions.find((item) => item.name === "tumor_purity"),
    ).toMatchObject({
      value_type: "continuous",
      effect_unit: 1,
    });
  });

  it("rejects local identifiers and duplicate TCGA participant rows", () => {
    expect(() =>
      parseExternalCovariateCsv("patient_id,risk\nLOCAL-1,High\n"),
    ).toThrow("exact barcode");
    expect(() =>
      parseExternalCovariateCsv(
        "patient_id,risk\nTCGA-AB-0001,High\nTCGA-AB-0001,Low\n",
      ),
    ).toThrow("Duplicate patient_id");
  });

  it("supports explicit ordinal coding and level order", () => {
    const parsed = parseExternalCovariateCsv(VALID_CSV);
    const ordinal = changeExternalCovariateType(
      parsed,
      "molecular_risk",
      "ordinal",
    );
    const reordered = reorderExternalCovariateLevel(
      ordinal,
      "molecular_risk",
      "Low",
      0,
    );
    const definition = reordered.definitions.find(
      (item) => item.name === "molecular_risk",
    );

    expect(definition.value_type).toBe("ordinal");
    expect(definition.reference_level).toBeNull();
    expect(definition.levels).toEqual(["Low", "High", "Intermediate"]);
  });

  it("prevents non-numeric columns from being recoded as continuous", () => {
    const parsed = parseExternalCovariateCsv(VALID_CSV);

    expect(() =>
      changeExternalCovariateType(parsed, "idh_status", "continuous"),
    ).toThrow("non-numeric");
  });
});
