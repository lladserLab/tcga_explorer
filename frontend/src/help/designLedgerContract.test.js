import { describe, expect, test } from "vitest";

import {
  compareDesignLedger,
  multiverseDesignLedger,
  survivalDesignLedger,
} from "./designLedgerContract";

describe("survival design ledger", () => {
  const complete = {
    datasetLabel: "Kidney renal clear cell carcinoma",
    markerKind: "single",
    markerSummary: "CA9",
    markerCount: 1,
    endpointLabel: "Overall survival",
    patients: 512,
    events: 168,
    expressionScaleLabel: "log2(TPM + 1)",
    groupingLabel: "Median",
    filterCount: 0,
    adjustmentSummary: "Age",
    covariateCount: 1,
    requirements: [],
  };

  test("an incomplete design is not ready and says exactly what blocks it", () => {
    const ledger = survivalDesignLedger({
      ...complete,
      markerSummary: "",
      requirements: ["Add at least one gene or signature."],
    });
    expect(ledger.ready).toBe(false);
    expect(ledger.missing).toEqual(["Add at least one gene or signature."]);
    const marker = ledger.decided.find((item) => item.id === "marker");
    expect(marker.pending).toBe(true);
    expect(marker.value).toBe("Pending");
  });

  test("a complete design reports patients and events beside the dataset", () => {
    const ledger = survivalDesignLedger(complete);
    expect(ledger.ready).toBe(true);
    expect(ledger.missing).toEqual([]);
    const dataset = ledger.decided.find((item) => item.id === "dataset");
    expect(dataset.value).toContain("512 patients");
    expect(dataset.value).toContain("168 events");
    expect(dataset.value).toContain("before tissue selection, filters and adjustment");
  });

  test("the estimand describes the primary continuous result, not the groups", () => {
    const ledger = survivalDesignLedger(complete);
    expect(ledger.estimand).toMatch(/one-standard-deviation increase/);
    expect(ledger.estimand).toMatch(/selected groups as sensitivity analyses/);
  });
  test("review keeps the tissue population distinct from clinical restrictions", () => {
    const ledger = survivalDesignLedger({ ...complete, populationLabel: "Metastatic tumor", filterCount: 2 });
    expect(ledger.decided.find((item) => item.id === "population").value).toBe("Metastatic tumor · 2 clinical filters");
    const unrestricted = survivalDesignLedger({ ...complete, populationLabel: "Primary solid tumor" });
    expect(unrestricted.decided.find((item) => item.id === "population").value).toBe("Primary solid tumor · No clinical restrictions");
  });

  test("the panel estimand states that no cutpoint is searched", () => {
    const ledger = survivalDesignLedger({
      ...complete,
      markerKind: "signature_panel",
      markerCount: 3,
    });
    expect(ledger.estimand).toContain("3 signatures");
    expect(ledger.estimand).toMatch(/without cutpoint searches/);
  });

  test("the interaction estimand refuses a mechanistic reading", () => {
    const ledger = survivalDesignLedger({
      ...complete,
      markerKind: "combined_signatures",
      markerCount: 2,
      groupingLabel: "Median x median",
    });
    expect(ledger.estimand).toMatch(/does not establish a biological mechanism/);
  });

  test("several genes are named as separate uncorrected analyses", () => {
    const ledger = survivalDesignLedger({ ...complete, markerCount: 4 });
    expect(ledger.estimand).toContain("4 separate analyses");
    expect(ledger.estimand).toMatch(/do not share a multiple-testing correction/);
    expect(ledger.cautions.join(" ")).toMatch(/Compare or Robustness/);
  });

  test("sparse events are flagged against the number of selected covariates", () => {
    const sparse = survivalDesignLedger({
      ...complete,
      events: 12,
      covariateCount: 3,
    });
    expect(sparse.cautions.join(" ")).toContain("12 events");
    expect(sparse.cautions.join(" ")).toMatch(/events per parameter/);
  });

  test("no events-per-parameter figure is invented", () => {
    const ledger = survivalDesignLedger({ ...complete, events: 12, covariateCount: 3 });
    expect(ledger.cautions.join(" ")).not.toMatch(/\b\d+(\.\d+)? events per parameter\b/);
  });

  test("an ample event count raises no caution", () => {
    expect(survivalDesignLedger(complete).cautions).toEqual([]);
  });
});

describe("compare design ledger", () => {
  const complete = {
    datasetLabel: "KIRC",
    geneCount: 3,
    methodLabels: ["Median", "Maxstat"],
    endpointLabel: "Overall survival",
    expressionScaleLabel: "log2(TPM + 1)",
    events: 168,
    filterCount: 2,
    adjustmentSummary: "Age",
    covariateCount: 1,
    requirements: [],
  };

  test("the declared family is the product of rows and columns", () => {
    const ledger = compareDesignLedger(complete);
    const family = ledger.decided.find((item) => item.id === "family");
    expect(family.value).toBe("6 planned cells");
    expect(ledger.estimand).toContain("6 grouped comparisons");
    expect(ledger.estimand).toMatch(/BH and Bonferroni/);
    expect(ledger.estimand).toContain("valid grouped tests");
    expect(ledger.estimand).toContain("selection-corrected");
    expect(ledger.compactEstimand).toContain("same source and endpoint");
  });

  test("active filters are reported as the analyzed population", () => {
    const ledger = compareDesignLedger(complete);
    expect(ledger.decided.find((item) => item.id === "population").value)
      .toBe("2 clinical filters");
    expect(compareDesignLedger({ ...complete, filterCount: 0 })
      .decided.find((item) => item.id === "population").value)
      .toBe("All eligible patients");
  });

  test("several cutpoints warn against reading the most favorable cell", () => {
    expect(compareDesignLedger(complete).cautions.join(" "))
      .toMatch(/Include all comparisons/);
    expect(compareDesignLedger({ ...complete, methodLabels: ["Median"] }).cautions)
      .toEqual([]);
  });

  test("an empty design still explains what a cell is", () => {
    const ledger = compareDesignLedger({ requirements: ["Add at least one gene."] });
    expect(ledger.ready).toBe(false);
    expect(ledger.estimand).toMatch(/one grouped comparison under one cutpoint rule/);
  });
});

describe("multiverse design ledger", () => {
  const complete = {
    datasetLabel: "KIRC",
    markerSummary: "CA9",
    endpointLabels: ["OS", "DSS"],
    scoringLabels: ["Single gene"],
    cutpointLabels: ["Median", "Maxstat", "Tertiles"],
    filterCount: 0,
    adjustmentSummary: "Unadjusted",
    requirements: [],
  };

  test("the decision universe is the product of every declared axis", () => {
    const ledger = multiverseDesignLedger(complete);
    expect(ledger.decided.find((item) => item.id === "family").value)
      .toBe("6 specifications");
    expect(ledger.estimand).toContain("6 planned analyses");
    expect(ledger.estimand).toMatch(/record includes every combination/);
  });

  test("prespecification is stated whatever the size of the universe", () => {
    expect(multiverseDesignLedger(complete).cautions.join(" "))
      .toMatch(/Choose all combinations before running/);
  });

  test("a tiny universe is called out as describing choices, not robustness", () => {
    const ledger = multiverseDesignLedger({
      ...complete,
      endpointLabels: ["OS"],
      cutpointLabels: ["Median"],
    });
    expect(ledger.cautions.join(" ")).toMatch(/covers only a few choices/);
  });

  test("an empty universe raises no size caution", () => {
    const ledger = multiverseDesignLedger({ requirements: ["Select a cancer cohort."] });
    expect(ledger.cautions.join(" ")).not.toMatch(/covers only a few choices/);
    expect(ledger.ready).toBe(false);
  });
});
