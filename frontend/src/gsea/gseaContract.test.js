import { describe, expect, test } from "vitest";
import {
  buildGseaPayload,
  chooseSurvivalContrast,
  clinicalGroupingVariables,
  clinicalVariableLevelOptions,
  createDefaultGseaState,
  eligibleSurvivalAnalyses,
  parseSignatureGenes,
  toggleDisjointGroupValue,
  validateGseaState,
} from "./gseaContract";

describe("GSEA frontend contract", () => {
  test("discovers BRCA PAM50 from the dataset-aware clinical catalog", () => {
    const filters = {
      clinical_grouping_variables: [
        {
          id: "paper_BRCA_Subtype_PAM50",
          label: "PAM50 intrinsic subtype",
          value_type: "categorical",
          category: "tumor_specific",
          source: "TCGA marker-paper annotation",
          source_field: "paper_BRCA_Subtype_PAM50",
          analysis_eligible: true,
          non_missing_count: 1083,
          patient_count: 1095,
          coverage: 0.989041,
          levels: [
            { value: "LumA", label: "Luminal A", count: 562 },
            { value: "Basal", label: "Basal", count: 190 },
          ],
        },
      ],
    };

    expect(clinicalGroupingVariables(filters)[0]).toMatchObject({
      value: "paper_BRCA_Subtype_PAM50",
      category_label: "Published tumor annotations",
      analysis_eligible: true,
    });
    expect(
      clinicalVariableLevelOptions(filters, "paper_BRCA_Subtype_PAM50"),
    ).toEqual([
      {
        value: "LumA",
        label: "Luminal A",
        count: 562,
        analysis_eligible: true,
        unavailable_reason: null,
      },
      {
        value: "Basal",
        label: "Basal",
        count: 190,
        analysis_eligible: true,
        unavailable_reason: null,
      },
    ]);
  });

  test("retains per-level eligibility from the clinical catalog", () => {
    const options = clinicalVariableLevelOptions(
      {
        clinical_grouping_variables: [
          {
            id: "subtype",
            levels: [
              {
                value: "Rare",
                label: "Rare subtype",
                count: 3,
                analysis_eligible: false,
                unavailable_reason: "Fewer than 5 patients have this level.",
              },
            ],
          },
        ],
      },
      "subtype",
    );

    expect(options[0]).toMatchObject({
      value: "Rare",
      analysis_eligible: false,
      unavailable_reason: "Fewer than 5 patients have this level.",
    });
  });

  test("clinical levels remain disjoint when moved between groups", () => {
    let state = {
      ...createDefaultGseaState(),
      group_a_values: ["Stage I"],
      group_b_values: ["Stage II"],
    };
    state = toggleDisjointGroupValue(state, "b", "Stage I");
    expect(state.group_a_values).toEqual([]);
    expect(state.group_b_values).toEqual(["Stage II", "Stage I"]);
  });

  test("rejects using the same clinical variable as grouping and restriction", () => {
    const state = {
      ...createDefaultGseaState(),
      clinical_variable: "paper_BRCA_Subtype_PAM50",
      group_a_values: ["LumA"],
      group_b_values: ["Basal"],
    };
    const filters = {
      clinical_grouping_variables: [
        {
          id: "paper_BRCA_Subtype_PAM50",
          value_type: "categorical",
          analysis_eligible: true,
          levels: [
            { value: "LumA" },
            { value: "Basal" },
          ],
        },
      ],
    };
    const form = {
      cohort: "TCGA-BRCA",
      filters: {
        sample_population: "primary_solid",
        custom_filters: [
          {
            variable_id: "paper_BRCA_Subtype_PAM50",
            categorical_levels: ["LumA"],
          },
        ],
      },
    };

    expect(validateGseaState(state, filters, form).errors).toContain(
      "A clinical variable cannot define the groups and restrict eligibility at the same time.",
    );
  });

  test("weighted signature genes are normalized and deduplicated", () => {
    expect(
      parseSignatureGenes(
        " ca9:2;\nVEGFA:-1, CA9:4 ",
        "weighted",
      ),
    ).toEqual([
      { gene_symbol: "CA9", weight: 2 },
      { gene_symbol: "VEGFA", weight: -1 },
    ]);
  });

  test("single-gene grouping rejects silent truncation", () => {
    const state = {
      ...createDefaultGseaState(),
      grouping_source: "expression",
      signature_method: "single",
      signature_genes: "CA9, VEGFA",
      group_a_label: "Low",
      group_b_label: "High",
    };
    expect(validateGseaState(state)).toEqual({
      valid: false,
      errors: expect.arrayContaining([
        "Single-gene grouping requires exactly one gene.",
      ]),
    });
    expect(() => parseSignatureGenes("CA9, VEGFA", "single")).toThrow(
      "Single-gene scoring requires exactly one gene.",
    );
  });

  test("rank-based grouping sends explicit up and down directions", () => {
    expect(parseSignatureGenes("IFNG, GZMB, TGFB1:-1", "singscore")).toEqual([
      { gene_symbol: "IFNG", weight: 1, direction: "up" },
      { gene_symbol: "GZMB", weight: 1, direction: "up" },
      { gene_symbol: "TGFB1", weight: -1, direction: "down" },
    ]);
    expect(() => parseSignatureGenes("IFNG:2, GZMB", "aucell")).toThrow(
      /direction only/,
    );
  });

  test("mean grouping rejects weights instead of ignoring them", () => {
    expect(() => parseSignatureGenes("IFNG:2, GZMB", "mean")).toThrow(
      /does not use weights/,
    );
  });

  test("age, size and seed limits match the server contract", () => {
    const state = {
      ...createDefaultGseaState(),
      clinical_variable: "age_at_index",
      clinical_cutpoint_method: "value",
      clinical_cutpoint: "",
      min_gene_set_size: 501,
      max_gene_set_size: 5001,
      seed: -1,
    };
    const validation = validateGseaState(state);
    expect(validation.valid).toBe(false);
    expect(validation.errors).toEqual(expect.arrayContaining([
      "Enter a numeric cutpoint from 0 to 120.",
      "Minimum gene-set size must be an integer from 5 to 500.",
      "Maximum gene-set size must be an integer from 10 to 5000 and at least the minimum.",
      "Seed must be an integer from 0 to 2147483647.",
    ]));
  });

  test("validates any catalog-declared numeric clinical variable", () => {
    const filters = {
      clinical_grouping_variables: [
        {
          id: "pack_years_smoked",
          label: "Pack-years smoked",
          value_type: "numeric",
          category: "clinical",
          analysis_eligible: true,
          numeric_summary: { min: 0, max: 180, median: 40, unit: "pack-years" },
          levels: [],
        },
      ],
    };
    const state = {
      ...createDefaultGseaState(),
      clinical_variable: "pack_years_smoked",
      clinical_cutpoint_method: "value",
      clinical_cutpoint: "40",
    };

    expect(validateGseaState(state, filters).valid).toBe(true);
    expect(
      validateGseaState({ ...state, clinical_cutpoint: "200" }, filters).errors,
    ).toContain("Enter a numeric cutpoint from 0 to 180.");
  });

  test("completed two-group survival results are eligible", () => {
    const eligible = eligibleSurvivalAnalyses([
      {
        id: "a",
        status: "completed",
        cutpoint_method: "median",
        metrics: { group_counts: { Low: 10, High: 11 } },
      },
      {
        id: "b",
        status: "completed",
        cutpoint_method: "tertiles",
        metrics: { group_counts: { Low: 8, Mid: 8, High: 8 } },
      },
    ]);
    expect(eligible.map((item) => item.analysis.id)).toEqual(["a"]);
    expect(chooseSurvivalContrast(eligible[0].groups)).toEqual({
      groupA: "Low",
      groupB: "High",
    });
  });

  test("payload fixes the contrast as target minus reference", () => {
    const state = {
      ...createDefaultGseaState(),
      grouping_source: "clinical",
      clinical_variable: "gender",
      group_a_label: "Female",
      group_b_label: "Male",
      group_a_values: ["female"],
      group_b_values: ["male"],
    };
    expect(validateGseaState(state).valid).toBe(true);
    const payload = buildGseaPayload(state, {
      cohort: "TCGA-KIRC",
      dataset_id: null,
      dataset_release_id: null,
      expression_layer_id: null,
      expression_scale: "log2_tpm",
      filters: {},
    });
    expect(payload.grouping.group_a_label).toBe("Female");
    expect(payload.grouping.group_b_label).toBe("Male");
    expect(payload.ranking_metric).toBe("welch_t");
    expect(payload.permutations).toBe(1000);
  });

  test("keeps declared custom eligibility filters in the GSEA request", () => {
    const state = {
      ...createDefaultGseaState(),
      group_a_values: ["Stage I"],
      group_b_values: ["Stage IV"],
    };
    const payload = buildGseaPayload(state, {
      cohort: "TCGA-KIRC",
      expression_scale: "log2_tpm",
      filters: {
        custom_filters: [{
          variable_id: "immune_score",
          categorical_levels: [],
          numeric_min: 1.5,
          numeric_max: null,
        }],
      },
    });

    expect(payload.filters.custom_filters).toEqual([{
      variable_id: "immune_score",
      categorical_levels: [],
      numeric_min: 1.5,
      numeric_max: null,
    }]);
  });
});
