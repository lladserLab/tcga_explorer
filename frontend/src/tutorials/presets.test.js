import { describe, expect, test, vi } from "vitest";
import {
  applyTutorialPreset,
  applyTutorialPresetWithAdapters,
  createTutorialPresetReducers,
} from "./presets";

describe("pure tutorial presets", () => {
  test("applies the included-data preset without mutating input and clears derived results", () => {
    const workspace = {
      activePage: "home",
      form: {
        cohort: "TCGA-BRCA",
        gene_symbol: "ESR1",
        time_unit: "months",
        show_confidence_interval: false,
        show_risk_table: false,
        filters: {
          sample_types: ["Primary Tumor"],
          stages: ["Stage I"],
          grades: ["G1"],
          genders: ["female"],
          races: ["white"],
          age_min: "40",
          age_max: "70",
          max_time_days: "1825",
          custom_filters: [{ variable: "paper_BRCA_Subtype_PAM50", values: ["LumA"] }],
        },
        adjustment_covariates: ["ajcc_pathologic_stage", "age_at_index"],
        external_covariates: { filename: "clinical.csv", columns: [{ name: "smoking" }] },
        external_adjustment_covariates: ["smoking"],
      },
      analysisResults: [{ id: "old" }],
      compare: { genes: "ESR1", methods: ["median"], results: [{ id: "old" }], error: "old" },
      gsea: { grouping_source: "clinical", result: { id: "old" }, error: "old" },
      expressionComparison: { genes: ["ESR1"], result: { id: "old" } },
      multiverse: { result: { id: "old" } },
      panCancer: { result: { id: "old" }, hierarchicalResult: { id: "old" } },
    };
    const next = applyTutorialPreset(workspace, "included-lihc-cdc20-os");
    expect(next).not.toBe(workspace);
    expect(workspace.form.cohort).toBe("TCGA-BRCA");
    expect(next.form).toMatchObject({ cohort: "TCGA-LIHC", gene_symbol: "CDC20", endpoint: "OS" });
    expect(next.form.filters).toEqual({
      sample_types: [],
      stages: [],
      grades: [],
      genders: [],
      races: [],
      age_min: "",
      age_max: "",
      max_time_days: "",
      custom_filters: [],
    });
    expect(next.form.adjustment_covariates).toEqual(["age_at_index"]);
    expect(next.form.external_covariates).toBeNull();
    expect(next.form.external_adjustment_covariates).toEqual([]);
    expect(next.form.time_unit).toBe("days");
    expect(next.form.show_confidence_interval).toBe(true);
    expect(next.form.show_risk_table).toBe(true);
    expect(next.analysisResults).toEqual([]);
    expect(next.compare).toMatchObject({ genes: "ESR1", results: [], error: "" });
    expect(next.gsea.result).toBeNull();
    expect(next.expressionComparison.result).toBeNull();
    expect(next.multiverse.result).toBeNull();
    expect(next.panCancer.result).toBeNull();
    expect(next.panCancer.hierarchicalResult).toBeNull();
  });

  test("PAM50 preset is explicitly expression-derived and does not invent live levels", () => {
    const next = applyTutorialPreset({}, "groups-brca-pam50-exploratory");
    expect(next.form.cohort).toBe("TCGA-BRCA");
    expect(next.gsea).toMatchObject({
      clinical_variable: "paper_BRCA_Subtype_PAM50",
      group_a_values: [],
      group_b_values: [],
      gene_set_collection: "go_bp",
      result: null,
    });
  });

  test("builds setter reducers and a navigation target without any API surface", () => {
    const application = createTutorialPresetReducers("compare-skcm-pdcd1-cutpoints");
    expect(application.activePage).toBe("compare");
    expect(Object.keys(application.reducers)).toContain("form");
    expect(JSON.stringify(application)).not.toContain("fetch");

    const setForm = vi.fn((reducer) => reducer({ endpoint: "OS" }));
    const navigate = vi.fn();
    applyTutorialPresetWithAdapters("compare-skcm-pdcd1-cutpoints", {
      setters: { form: setForm },
      navigate,
    });
    expect(setForm).toHaveBeenCalledOnce();
    expect(navigate).toHaveBeenCalledWith("compare");
  });
});
