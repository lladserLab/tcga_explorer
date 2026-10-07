import { describe, expect, test, vi } from "vitest";

import {
  WORKSPACE_DRAFT_STORAGE_KEY,
  clearWorkspaceDraft,
  createWorkspaceDraft,
  loadWorkspaceDraft,
  persistWorkspaceDraft,
  sanitizeWorkspaceDraft,
} from "./workspaceDraft";

function memoryStorage() {
  const values = new Map();
  return {
    getItem: (key) => values.get(key) || null,
    setItem: (key, value) => values.set(key, value),
    removeItem: (key) => values.delete(key),
  };
}

test("does not create empty workspace drafts", () => {
  expect(createWorkspaceDraft({ form: {} })).toBeNull();
});

test("removes private tables, identifiers and runtime results", () => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date("2026-08-08T12:00:00Z"));
  const draft = createWorkspaceDraft({
    activePage: "expression",
    form: {
      cohort: "TCGA-BRCA",
      dataset_id: "user-secret",
      gene_symbol: "ESR1",
      endpoint: "OS",
      filters: { custom_filters: [{ variable_id: "response" }] },
      external_covariates: { rows: [{ patient_id: "P001" }] },
    },
    compare: { results: [{ private: true }], running: true, active_run_id: {},
      result_context: { fingerprint: "P001", dataset_id: "user-secret" }, grouped_family: { private: true } },
    expressionComparison: {
      genes: ["ESR1"],
      clinical_variable: "private_subtype",
      group_a_values: ["secret"],
      group_a_label: "secret responders",
      result: { private: true },
    },
    gsea: { signature_genes: "ESR1", clinical_variable: "private_subtype" },
    multiverse: {},
    panCancer: {},
  });

  const serialized = JSON.stringify(draft);
  expect(draft.form.dataset_id).toBeNull();
  expect(draft.expressionComparison.clinical_variable).toBeUndefined();
  expect(serialized).not.toContain("P001");
  expect(serialized).not.toContain("secret");
  expect(serialized).not.toContain("private_subtype");
  expect(draft.compare).toEqual({ genes: "", methods: [] });
});

describe("workspace draft storage", () => {
  test("persists, loads and clears a versioned draft", () => {
    const storage = memoryStorage();
    const draft = {
      schema_version: "trace-workspace-draft-v1",
      summary: "TCGA-BRCA · ESR1 · OS",
    };
    expect(persistWorkspaceDraft(draft, storage)).toBe(true);
    expect(loadWorkspaceDraft(storage)).toMatchObject(draft);
    expect(clearWorkspaceDraft(storage)).toBe(true);
    expect(storage.getItem(WORKSPACE_DRAFT_STORAGE_KEY)).toBeNull();
  });

  test("repairs obsolete numeric state and caps saved gene lists", () => {
    const draft = sanitizeWorkspaceDraft({
      schema_version: "trace-workspace-draft-v1",
      active_page: "compare",
      form: {
        custom_percentile: 0,
        gene_symbol: Array.from({ length: 30 }, (_, index) => `G${index}`).join(","),
        filters: { age_min: 80, age_max: 40, max_time_days: -1 },
        plot_style: { base_font_size: "", axis_text_size: 0, axis_title_size: 99 },
      },
      compare: {
        genes: Array.from({ length: 30 }, (_, index) => `C${index}`).join(","),
        methods: ["median", "obsolete"],
      },
      panCancer: {
        min_patients: 0,
        min_events: 999,
        fdr_threshold: 2,
        hierarchicalRequest: { min_patients: "" },
      },
    });

    expect(draft.form.custom_percentile).toBe(60);
    expect(draft.form.gene_symbol.split(",")).toHaveLength(25);
    expect(draft.form.filters).toMatchObject({ age_min: "", age_max: "", max_time_days: "" });
    expect(draft.form.plot_style).toMatchObject({ base_font_size: 12, axis_text_size: 11, axis_title_size: 12 });
    expect(draft.compare.methods).toEqual(["median"]);
    expect(draft.panCancer).toMatchObject({ min_patients: 10, min_events: 5, fdr_threshold: 0.1 });
    expect(draft.panCancer.hierarchicalRequest.min_patients).toBe(20);
  });
});
