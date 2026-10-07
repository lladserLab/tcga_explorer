import { describe, expect, test } from "vitest";
import { metadataContextKey, metadataReady, survivalRequestFingerprint, survivalResultsAreStale } from "./setupState";

const form = { cohort: "TCGA-BRCA", filters: { sample_population: "primary_solid" } };
const request = { cohort: "TCGA-BRCA", gene_symbol: "CA9", endpoint: "OS", filters: form.filters, adjustment_covariates: ["age_at_index"] };

describe("Survival data readiness", () => {
  test.each(["idle", "loading", "error"])("%s metadata cannot authorize a run", (status) => {
    const key = metadataContextKey(form);
    expect(metadataReady({ key, status }, key)).toBe(false);
  });
  test("only a successful check for the current context is ready", () => {
    const key = metadataContextKey(form);
    expect(metadataReady({ key, status: "ready" }, key)).toBe(true);
    for (const change of [{ cohort: "TCGA-KIRC" }, { dataset_id: "external-brca" }, { dataset_release_id: "v2" }, { filters: { sample_population: "metastatic" } }]) {
      expect(metadataReady({ key, status: "ready" }, metadataContextKey({ ...form, ...change }))).toBe(false);
    }
  });
  test("clinical restrictions do not trigger a cohort reload", () => {
    expect(metadataContextKey({ ...form, filters: { ...form.filters, stages: ["II"] } })).toBe(metadataContextKey(form));
  });
});

describe("Survival result identity", () => {
  const original = survivalRequestFingerprint([request]);
  test("object key order does not change identity", () => {
    expect(survivalRequestFingerprint([{ adjustment_covariates: ["age_at_index"], filters: form.filters, endpoint: "OS", gene_symbol: "CA9", cohort: "TCGA-BRCA" }])).toBe(original);
    expect(survivalResultsAreStale(original, original)).toBe(false);
  });
  test.each([
    { gene_symbol: "MKI67" }, { endpoint: "DSS" }, { filters: { sample_population: "metastatic" } },
    { filters: { ...form.filters, custom_filters: [{ variable: "PAM50", values: ["LumA"] }] } },
    { adjustment_covariates: [] }, { cutpoint_method: "maxstat" }, { expression_scale: "tpm" },
    { expression_layer_id: "v2" }, { dataset_release_id: "release-2" },
    { plot_style: { cox_forest: { selected_model_keys: ["adjusted"] } } },
    { external_covariates: { rows: [{ patient_id: "patient-1", age: 50 }] } },
  ])("changed request %j is stale, reverting restores identity", (change) => {
    expect(survivalResultsAreStale(original, survivalRequestFingerprint([{ ...request, ...change }]))).toBe(true);
    expect(survivalResultsAreStale(original, survivalRequestFingerprint([request]))).toBe(false);
  });
  test("all batch members contribute to identity", () => {
    expect(survivalResultsAreStale(original, survivalRequestFingerprint([request, { ...request, gene_symbol: "MKI67" }]))).toBe(true);
  });
  test("recovered and invalid requests never assert a match", () => {
    expect(survivalResultsAreStale(null, original)).toBe(true);
    expect(survivalResultsAreStale(original, survivalRequestFingerprint([]))).toBe(true);
  });
});
