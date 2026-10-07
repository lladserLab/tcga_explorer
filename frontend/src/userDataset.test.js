import { afterEach, describe, expect, it, vi } from "vitest";

import {
  USER_CLINICAL_MAX_BYTES,
  createCustomClinicalVariable,
  customClinicalCandidates,
  defaultEventMapping,
  eventValuesForColumn,
  humanFileSize,
  inspectUserDatasetFiles,
  loadUserDatasetReference,
  persistUserDatasetReference,
  loadLocalProjects,
  forgetLocalProject,
  validateCustomClinicalVariables,
} from "./userDataset";

function memoryStorage() {
  const values = new Map();
  return {
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, String(value)),
    removeItem: (key) => values.delete(key),
  };
}

afterEach(() => {
  vi.unstubAllEnvs();
  delete globalThis.window;
});


function tableFile(name, text, reportedSize = null) {
  const bytes = new TextEncoder().encode(text).byteLength;
  return {
    name,
    size: reportedSize ?? bytes,
    text: async () => text,
    slice: () => ({ text: async () => text }),
  };
}


const clinical = [
  "sample_id,os_months,os_status,age,stage",
  "S01,12,0,45,Stage I",
  "S02,18,1,51,Stage II",
  "S03,24,0,62,Stage III",
].join("\n");


describe("user dataset inspection", () => {
  it("infers genes in rows, outcomes and optional covariates", async () => {
    const expression = [
      "gene_symbol,S01,S02,S03",
      "TP53,2.1,2.4,2.8",
      "MKI67,4.2,4.5,4.7",
    ].join("\n");

    const result = await inspectUserDatasetFiles(
      tableFile("expression.csv", expression),
      tableFile("clinical.csv", clinical),
    );

    expect(result.suggestions.expression_orientation).toBe("genes_by_rows");
    expect(result.suggestions.expression_id_column).toBe("gene_symbol");
    expect(result.suggestions.clinical_id_column).toBe("sample_id");
    expect(result.suggestions.time_column).toBe("os_months");
    expect(result.suggestions.event_column).toBe("os_status");
    expect(result.suggestions.time_unit).toBe("months");
    expect(result.suggestions.expression_unit).toBe("");
    expect(result.suggestions.covariates.age_at_index).toBe("age");
    expect(result.suggestions.covariates.stage).toBe("stage");
    expect(result.matching.genesByRowsMatches).toBe(3);
    expect(eventValuesForColumn(result, "os_status")).toEqual(["0", "1"]);
  });

  it("infers samples in rows from matching identifiers", async () => {
    const expression = [
      "sample_id,TP53,MKI67",
      "S01,2.1,4.2",
      "S02,2.4,4.5",
      "S03,2.8,4.7",
    ].join("\n");

    const result = await inspectUserDatasetFiles(
      tableFile("expression.tsv", expression),
      tableFile("clinical.tsv", clinical),
    );

    expect(result.suggestions.expression_orientation).toBe("samples_by_rows");
    expect(result.suggestions.expression_id_column).toBe("sample_id");
    expect(result.matching.samplesByRowsMatches).toBe(3);
  });

  it("blocks an oversized patient-metadata file before reading it", async () => {
    const expression = tableFile(
      "expression.csv",
      "gene_symbol,S01\nTP53,2.1\n",
    );
    const oversizedClinical = tableFile(
      "clinical.csv",
      clinical,
      USER_CLINICAL_MAX_BYTES + 1,
    );

    await expect(
      inspectUserDatasetFiles(expression, oversizedClinical),
    ).rejects.toThrow("patient-metadata table exceeds the 10 MB upload limit");
  });

  it("accepts three subtype levels without inventing a survival outcome", async () => {
    const expression = [
      "gene_symbol,S01,S02,S03,S04,S05,S06",
      "ESR1,4.1,4.4,2.1,2.0,3.2,3.4",
    ].join("\n");
    const metadata = [
      "patient_id,subtype",
      "S01,Luminal A",
      "S02,Luminal A",
      "S03,Basal-like",
      "S04,Basal-like",
      "S05,HER2-enriched",
      "S06,HER2-enriched",
    ].join("\n");

    const result = await inspectUserDatasetFiles(
      tableFile("expression.csv", expression),
      tableFile("metadata.csv", metadata),
    );

    expect(result.suggestions.has_survival_outcome).toBe(false);
    expect(result.suggestions.time_column).toBe("");
    expect(result.suggestions.event_column).toBe("");
    expect(customClinicalCandidates(result, result.suggestions).map(
      (item) => item.column,
    )).toEqual(["subtype"]);
    expect(result.clinical.observedValuesByColumn.subtype).toEqual([
      "Luminal A",
      "Basal-like",
      "HER2-enriched",
    ]);
  });

  it("maps common event and censor labels by meaning, not row order", () => {
    expect(defaultEventMapping(["0", "1"])).toEqual({
      event: "1",
      censored: "0",
    });
    expect(defaultEventMapping(["Alive", "Dead"])).toEqual({
      event: "Dead",
      censored: "Alive",
    });
    expect(defaultEventMapping(["Group A", "Group B"])).toEqual({
      event: "",
      censored: "",
    });
  });

  it("profiles candidate custom clinical variables without reusing endpoint columns", async () => {
    const expression = [
      "gene_symbol,S01,S02,S03",
      "TP53,2.1,2.4,2.8",
    ].join("\n");
    const enrichedClinical = [
      "sample_id,os_months,os_status,age,stage,pam50,immune_score",
      "S01,12,0,45,Stage I,LumA,1.2",
      "S02,18,1,51,Stage II,Basal,2.4",
      "S03,24,0,62,Stage III,LumA,3.1",
    ].join("\n");
    const result = await inspectUserDatasetFiles(
      tableFile("expression.csv", expression),
      tableFile("clinical.csv", enrichedClinical),
    );
    const candidates = customClinicalCandidates(result, result.suggestions);

    expect(candidates.map((item) => item.column)).toEqual(["pam50", "immune_score"]);
    expect(candidates.find((item) => item.column === "pam50").inferredValueType).toBe("categorical");
    expect(candidates.find((item) => item.column === "immune_score").inferredValueType).toBe("numeric");
  });

  it("keeps unknown timing valid but detects unsupported timing", () => {
    const inspection = {
      clinical: {
        columnProfiles: [{
          column: "subtype",
          categoricalLevelLimitExceeded: false,
        }],
      },
    };
    const variable = createCustomClinicalVariable("subtype", {
      inferredValueType: "categorical",
    });

    expect(variable.id).toBe("subtype");
    expect(validateCustomClinicalVariables([variable], inspection)).toEqual([]);
    expect(validateCustomClinicalVariables([
      { ...variable, timing: "after_magic" },
    ], inspection)).toContain("subtype: measurement timing is not supported.");
  });

  it("mirrors backend safeguards for reserved IDs and protected source columns", () => {
    const inspection = {
      clinical: {
        columnProfiles: [
          { column: "os_months", categoricalLevelLimitExceeded: false },
          { column: "pam50", categoricalLevelLimitExceeded: false },
        ],
      },
    };
    const mapping = {
      clinical_id_column: "sample_id",
      time_column: "os_months",
      event_column: "os_status",
      covariates: { stage: "stage" },
    };

    expect(validateCustomClinicalVariables([{
      ...createCustomClinicalVariable("os_months"),
      id: "os_event",
    }], inspection, mapping)).toEqual(expect.arrayContaining([
      "os months: analysis ID is reserved.",
      "os months: source column is already assigned to the endpoint or a standard covariate.",
    ]));
  });

  it("rejects empty labels, PHI-like columns and case-insensitive duplicates", () => {
    const inspection = {
      clinical: {
        columnProfiles: [
          { column: "patient_identifier", categoricalLevelLimitExceeded: false },
          { column: "PAM50", categoricalLevelLimitExceeded: false },
          { column: "pam50", categoricalLevelLimitExceeded: false },
        ],
      },
    };
    const phi = {
      ...createCustomClinicalVariable("patient_identifier"),
      label: "",
    };
    const first = createCustomClinicalVariable("PAM50");
    const duplicate = {
      ...createCustomClinicalVariable("pam50"),
      id: "PAM50_COPY",
    };
    const errors = validateCustomClinicalVariables([phi, first, duplicate], inspection);

    expect(errors).toEqual(expect.arrayContaining([
      "Custom variable 1: display label is required.",
      "Custom variable 1: source column appears to contain direct identifiers.",
      "pam50: each source column can be mapped once.",
    ]));
  });
});


describe("humanFileSize", () => {
  it("formats upload sizes compactly", () => {
    expect(humanFileSize(512)).toBe("512 B");
    expect(humanFileSize(2048)).toBe("2.0 KB");
    expect(humanFileSize(2 * 1024 * 1024)).toBe("2.0 MB");
  });
});

describe("private dataset session boundary", () => {
  it("keeps access to earlier local projects and deletes only the selected reference", () => {
    vi.stubEnv("VITE_TRACE_LOCAL_DESKTOP", "true");
    globalThis.window = {localStorage: memoryStorage(), sessionStorage: memoryStorage()};
    for (const id of ["user-one", "user-two"]) {
      persistUserDatasetReference({id, name: id, expires_at: null,
        privacy: {retention_policy: "local_until_deleted"}, access_token: id + "-token"});
    }
    persistUserDatasetReference(null);
    expect(loadLocalProjects().map(project => project.id)).toEqual(["user-one", "user-two"]);
    forgetLocalProject("user-two");
    expect(loadLocalProjects().map(project => project.id)).toEqual(["user-one"]);
    persistUserDatasetReference(loadLocalProjects()[0]);
    expect(loadUserDatasetReference().id).toBe("user-one");
  });
  it("recovers a local project after closing the browser session", () => {
    vi.stubEnv("VITE_TRACE_LOCAL_DESKTOP", "true");
    const localStorage = memoryStorage();
    globalThis.window = {localStorage, sessionStorage: memoryStorage()};
    const dataset = {id: "user-local-fixture", name: "Local project", expires_at: null,
      privacy: {retention_policy: "local_until_deleted"}, access_token: "local-capability"};
    persistUserDatasetReference(dataset);
    globalThis.window.sessionStorage = memoryStorage();
    expect(loadUserDatasetReference()).toEqual(dataset);
    persistUserDatasetReference(null);
    expect(loadUserDatasetReference()).toBeNull();
    expect(localStorage.getItem("trace-explorer-user-dataset-token")).toBeNull();
  });
  it("keeps the access token out of persistent local storage", () => {
    const localStorage = memoryStorage();
    const sessionStorage = memoryStorage();
    globalThis.window = { localStorage, sessionStorage };
    const dataset = {
      id: "user-private-fixture",
      name: "Private fixture",
      expires_at: "2099-01-01T00:00:00Z",
      access_token: "private-access-token",
    };

    persistUserDatasetReference(dataset);

    expect(localStorage.getItem("trace-explorer-user-dataset")).not.toContain(
      "private-access-token",
    );
    expect(sessionStorage.getItem("trace-explorer-user-dataset-token")).toBe(
      "private-access-token",
    );
    expect(loadUserDatasetReference()).toEqual(dataset);
  });

  it("forgets the dataset reference when the browser session token is gone", () => {
    const localStorage = memoryStorage();
    globalThis.window = {
      localStorage,
      sessionStorage: memoryStorage(),
    };
    localStorage.setItem(
      "trace-explorer-user-dataset",
      JSON.stringify({
        id: "user-private-fixture",
        name: "Private fixture",
        expires_at: "2099-01-01T00:00:00Z",
      }),
    );

    expect(loadUserDatasetReference()).toBeNull();
    expect(localStorage.getItem("trace-explorer-user-dataset")).toBeNull();
  });
});
