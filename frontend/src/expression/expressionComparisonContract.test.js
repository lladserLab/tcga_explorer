import { describe, expect, test } from "vitest";

import {
  EXPRESSION_COMPARISON_FDR_THRESHOLD,
  EXPRESSION_COMPARISON_HEATMAP_MAX_SAMPLES,
  EXPRESSION_COMPARISON_MAX_GENES,
  buildExpressionComparisonPayload,
  circularTargetGenes,
  createDefaultExpressionComparisonState,
  normalizeExpressionGenes,
  validateExpressionComparisonState,
} from "./expressionComparisonContract";

const FORM = {
  cohort: "TCGA-KIRC",
  dataset_id: null,
  dataset_release_id: null,
  expression_layer_id: null,
  expression_scale: "log2_tpm",
  filters: {
    sample_population: "primary_solid",
    sample_types: ["Primary Tumor"],
    stages: [],
    grades: [],
    genders: [],
    races: [],
    age_min: "40",
    age_max: "",
    max_time_days: "3650",
    custom_filters: [{
      variable_id: "immune_class",
      categorical_levels: ["inflamed"],
      numeric_min: null,
      numeric_max: null,
    }],
  },
};

describe("expression comparison request contract", () => {
  test("normalizes and deduplicates target genes without reordering", () => {
    expect(normalizeExpressionGenes([" ca9 ", "VEGFA", "CA9", ""])).toEqual([
      "CA9",
      "VEGFA",
    ]);
  });

  test("builds the exact binary clinical request", () => {
    const state = {
      ...createDefaultExpressionComparisonState(),
      genes: ["CA9", "VEGFA"],
      group_a_label: "Early",
      group_b_label: "Advanced",
      group_a_values: ["Stage I"],
      group_b_values: ["Stage III", "Stage IV"],
    };

    expect(validateExpressionComparisonState(state, FORM).valid).toBe(true);
    expect(buildExpressionComparisonPayload(state, FORM)).toEqual({
      cohort: "TCGA-KIRC",
      dataset_id: null,
      dataset_release_id: null,
      expression_layer_id: null,
      expression_scale: "log2_tpm",
      filters: {
        sample_population: "primary_solid",
        sample_types: ["Primary Tumor"],
        stages: [],
        grades: [],
        genders: [],
        races: [],
        age_min: 40,
        age_max: null,
        max_time_days: null,
        custom_filters: [{
          variable_id: "immune_class",
          categorical_levels: ["inflamed"],
          numeric_min: null,
          numeric_max: null,
        }],
      },
      genes: ["CA9", "VEGFA"],
      grouping: {
        source: "clinical",
        group_a_label: "Early",
        group_b_label: "Advanced",
        clinical_variable: "stage",
        group_a_values: ["Stage I"],
        group_b_values: ["Stage III", "Stage IV"],
        clinical_cutpoint_method: "median",
        clinical_cutpoint: null,
        survival_analysis_id: null,
        signature: null,
        cutpoint_method: "median",
        custom_percentile: null,
      },
      fdr_threshold: EXPRESSION_COMPARISON_FDR_THRESHOLD,
      heatmap_max_samples: EXPRESSION_COMPARISON_HEATMAP_MAX_SAMPLES,
    });
  });

  test("detects circular targets in an expression-derived contrast", () => {
    const state = {
      ...createDefaultExpressionComparisonState(),
      genes: ["CA9", "VEGFA", "SLC2A1"],
      grouping_source: "expression",
      group_a_label: "Low",
      group_b_label: "High",
      signature_method: "weighted",
      signature_genes: "CA9:1.5, EGLN3:-0.5",
    };

    expect(circularTargetGenes(state)).toEqual(["CA9"]);
    expect(validateExpressionComparisonState(state, FORM)).toMatchObject({
      valid: true,
      circular_genes: ["CA9"],
    });
    expect(buildExpressionComparisonPayload(state, FORM).grouping.signature).toEqual({
      name: "",
      gene_symbol: "CA9,EGLN3",
      signature_method: "weighted",
      signature_genes: [
        { gene_symbol: "CA9", weight: 1.5 },
        { gene_symbol: "EGLN3", weight: -0.5 },
      ],
    });
  });

  test("rejects using the same clinical variable as grouping and restriction", () => {
    const state = {
      ...createDefaultExpressionComparisonState(),
      genes: ["MKI67"],
      clinical_variable: "paper_BRCA_Subtype_PAM50",
      group_a_values: ["LumA"],
      group_b_values: ["Basal"],
    };
    const form = {
      ...FORM,
      filters: {
        ...FORM.filters,
        custom_filters: [
          {
            variable_id: "paper_BRCA_Subtype_PAM50",
            categorical_levels: ["LumA"],
          },
        ],
      },
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

    expect(validateExpressionComparisonState(state, form, filters).errors).toContain(
      "A clinical variable cannot define the groups and restrict eligibility at the same time.",
    );
  });

  test("enforces one to twenty-five target genes", () => {
    const missing = createDefaultExpressionComparisonState();
    expect(validateExpressionComparisonState(missing, FORM).errors).toContain(
      "Add at least one target gene.",
    );

    const excessive = {
      ...createDefaultExpressionComparisonState(),
      genes: Array.from(
        { length: EXPRESSION_COMPARISON_MAX_GENES + 1 },
        (_, index) => `GENE${index}`,
      ),
      group_a_values: ["Stage I"],
      group_b_values: ["Stage II"],
    };
    expect(validateExpressionComparisonState(excessive, FORM).errors).toContain(
      `Select no more than ${EXPRESSION_COMPARISON_MAX_GENES} target genes.`,
    );
  });

  test("accepts a dataset-declared numeric grouping beyond age", () => {
    const state = {
      ...createDefaultExpressionComparisonState(),
      genes: ["CA9"],
      clinical_variable: "pack_years_smoked",
      clinical_cutpoint_method: "value",
      clinical_cutpoint: "35",
    };
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

    expect(
      validateExpressionComparisonState(state, FORM, filters).valid,
    ).toBe(true);
  });
});
