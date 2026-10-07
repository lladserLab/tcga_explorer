import React from "react";
import { readFileSync } from "node:fs";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, test } from "vitest";

import ExpressionComparisonModule, {
  ExpressionComparisonResult,
} from "./ExpressionComparisonModule";
import { createDefaultExpressionComparisonState } from "./expressionComparisonContract";
import { APP_MODULE_ORDER } from "../moduleRegistry";

const EMPTY_FILTERS = {
  sample_types: [],
  stages: [],
  grades: [],
  genders: [],
  races: [],
  age_min: "",
  age_max: "",
  max_time_days: "",
};

function resultFixture() {
  return {
    comparison_id: "expression-test",
    cohort: "TCGA-KIRC",
    pipeline_version: "expression-comparison-v1.0",
    grouping: {
      source: "expression",
      group_a_label: "Low",
      group_b_label: "High",
    },
    summary: {
      genes_requested: 2,
      genes_analyzed: 2,
      genes_at_fdr_welch: 1,
      genes_at_fdr_mann_whitney: 1,
      patients: 25,
      group_counts: { Low: 12, High: 13 },
      fdr_threshold: 0.05,
      heatmap_samples: 25,
    },
    statistics: [
      {
        gene_symbol: "VEGFA",
        status: "analyzed",
        inferential_status: "inferential",
        group_a: { label: "Low", n: 12, mean: 3, sd: 1, median: 3, q1: 2, q3: 4 },
        group_b: { label: "High", n: 13, mean: 5, sd: 1, median: 5, q1: 4, q3: 6 },
        mean_difference_b_minus_a: 2,
        mean_difference_ci_low: 1.2,
        mean_difference_ci_high: 2.8,
        median_difference_b_minus_a: 2,
        hedges_g: 1.9,
        rank_biserial: 0.7,
        welch_t: { statistic: 5, df: 22, p_value: 0.00003, fdr: 0.00006 },
        mann_whitney: { u_statistic: 140, p_value: 0.0002, fdr: 0.0004 },
        significant_at_fdr: true,
      },
      {
        gene_symbol: "CA9",
        status: "analyzed",
        inferential_status: "descriptive_only",
        group_a: { label: "Low", n: 12, mean: 2, sd: 1, median: 2, q1: 1, q3: 3 },
        group_b: { label: "High", n: 13, mean: 7, sd: 1, median: 7, q1: 6, q3: 8 },
        mean_difference_b_minus_a: 5,
        mean_difference_ci_low: null,
        mean_difference_ci_high: null,
        median_difference_b_minus_a: 5,
        hedges_g: null,
        rank_biserial: null,
        welch_t: { statistic: null, df: null, p_value: null, fdr: null },
        mann_whitney: { u_statistic: null, p_value: null, fdr: null },
        significant_at_fdr: false,
      },
    ],
    warnings: ["CA9 defines the grouping signature and is descriptive only."],
    downloads: {
      statistics_csv: "/api/v1/expression/statistics.csv",
      violin_svg: "/api/v1/expression/violin.svg",
      boxplot_svg: "/api/v1/expression/boxplot.svg",
      heatmap_svg: "/api/v1/expression/heatmap.svg",
      audit_json: "/api/v1/expression/audit.json",
    },
    audit: { result_core_sha256: "0123456789abcdef0123456789abcdef" },
  };
}

describe("Expression comparison module", () => {
  test("uses the same dataset-aware PAM50 clinical selector", () => {
    const state = {
      ...createDefaultExpressionComparisonState(),
      genes: ["ESR1"],
      clinical_variable: "paper_BRCA_Subtype_PAM50",
      group_a_values: ["LumA"],
      group_b_values: ["Basal"],
    };
    const filters = {
      ...EMPTY_FILTERS,
      clinical_grouping_variables: [
        {
          id: "paper_BRCA_Subtype_PAM50",
          label: "PAM50 intrinsic subtype",
          value_type: "categorical",
          category: "tumor_specific",
          source: "TCGA marker-paper annotation",
          source_field: "paper_BRCA_Subtype_PAM50",
          expression_derived: true,
          provenance: {
            origin: "source_reported_molecular",
            label: "Published molecular call",
            reported_by: "TCGA marker-paper annotation",
            method_summary: "Author-provided PAM50 call; TRACE does not rerun it.",
            reference: {
              label: "TCGA Breast Cancer, Nature 2012",
              doi: "10.1038/nature11412",
              url: "https://doi.org/10.1038/nature11412",
            },
            expression_derived: true,
            recomputed_by_trace: false,
            comparability: "Do not assume equivalence across platforms.",
          },
          analysis_eligible: true,
          non_missing_count: 1083,
          patient_count: 1095,
          coverage: 0.989041,
          levels: [
            { value: "LumA", label: "Luminal A", count: 562 },
            { value: "Basal", label: "Basal", count: 190 },
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
    };
    const markup = renderToStaticMarkup(
      <ExpressionComparisonModule
        state={state}
        setState={() => {}}
        form={{
          cohort: "TCGA-BRCA",
          dataset_id: null,
          dataset_release_id: null,
          expression_layer_id: null,
          expression_scale: "log2_tpm",
          filters: EMPTY_FILTERS,
        }}
        cohorts={[{ id: "TCGA-BRCA" }]}
        repositoryDatasets={[]}
        userDataset={null}
        filters={filters}
        expressionScales={[{ value: "log2_tpm", label: "log2(TPM + 1)" }]}
        expressionScaleValue="log2_tpm"
        onSelectCohort={() => {}}
        onSelectRepositoryDataset={() => {}}
        onSelectExpressionScale={() => {}}
        onClearEligibility={() => {}}
        recentAnalyses={[]}
        onDownload={() => {}}
      />,
    );

    expect(markup).toContain("PAM50 intrinsic subtype · n=1083");
    expect(markup).toContain("Published molecular call");
    expect(markup).toContain("Not recalculated by TRACE");
    expect(markup).toContain("Do not assume equivalence across platforms.");
    expect(markup).toContain("Luminal A<small>n=562</small>");
    expect(markup).toContain("expression-level-row is-unavailable");
    expect(markup).toContain("unavailable for an individual group");
    expect(markup).toContain("Clinical field</dt><dd>PAM50 intrinsic subtype");
  });

  test("renders the statistics table before responsive backend SVG figures", () => {
    const markup = renderToStaticMarkup(
      <ExpressionComparisonResult result={resultFixture()} onDownload={() => {}} />,
    );

    expect(markup).toContain('<caption class="sr-only">');
    expect(markup).toContain('scope="colgroup"');
    expect(markup).toContain('scope="row"');
    expect(markup).toContain('role="region" tabindex="0"');
    expect(markup.indexOf("Full gene-level statistics")).toBeGreaterThan(0);
    expect(markup.indexOf("Full gene-level statistics")).toBeLessThan(
      markup.indexOf('class="expression-distribution-region"'),
    );
    // Figures load through authorizedFetch (private datasets need the token header), so the
    // first render shows a placeholder instead of a bare <img src> to the artifact URL.
    expect(markup.match(/Loading plot…/g)).toHaveLength(3);
    expect(markup).not.toContain('<img src="/api/v1/expression/heatmap.svg"');
    expect(markup).toContain("descriptive only");
    expect(markup).not.toContain("<1e−300</strong></td><td><strong><1e−300");
    expect(markup).toContain("—");
    expect(markup).not.toContain("<small>inferential</small>");
  });

  test("invalid setup remains operable and exposes an accessible gene combobox", () => {
    const markup = renderToStaticMarkup(
      <ExpressionComparisonModule
        state={createDefaultExpressionComparisonState()}
        setState={() => {}}
        form={{
          cohort: "",
          dataset_id: null,
          dataset_release_id: null,
          expression_layer_id: null,
          expression_scale: "log2_tpm",
          filters: EMPTY_FILTERS,
        }}
        cohorts={[]}
        repositoryDatasets={[]}
        userDataset={null}
        filters={{}}
        expressionScales={[{ value: "log2_tpm", label: "log2(TPM + 1)" }]}
        expressionScaleValue="log2_tpm"
        onSelectCohort={() => {}}
        onSelectRepositoryDataset={() => {}}
        onSelectExpressionScale={() => {}}
        onClearEligibility={() => {}}
        recentAnalyses={[]}
        onDownload={() => {}}
      />,
    );

    expect(markup).toContain("Expression comparison setup parameters");
    expect(markup).toContain('id="expression-comparison-gene-input"');
    expect(markup).toContain('role="combobox"');
    expect(markup).toContain('aria-autocomplete="list"');
    expect(markup).toContain('id="expression-comparison-run-requirements"');
    expect(markup).toContain('aria-describedby="expression-comparison-run-requirements"');
  });

  test("keeps molecular-only cohorts available and disables survival-derived groups", () => {
    const molecularDataset = {
      id: "external-gbc-expression",
      kind: "external",
      name: "GBC expression cohort",
      tcga_cohort: "EXT-GBC",
      expression_layer: { label: "log2 normalized expression" },
      gene_count: 18000,
      capabilities: {
        survival: { available: false, reason: "No time-to-event endpoint." },
        expression_comparison: { available: true },
        gsea: { available: true },
      },
      available_modules: ["expression", "gsea"],
    };
    const markup = renderToStaticMarkup(
      <ExpressionComparisonModule
        state={createDefaultExpressionComparisonState()}
        setState={() => {}}
        form={{
          cohort: "EXT-GBC",
          dataset_id: molecularDataset.id,
          dataset_release_id: "release-1",
          expression_layer_id: "rna",
          expression_scale: "log2_tpm",
          filters: EMPTY_FILTERS,
        }}
        cohorts={[
          { id: "EXT-GBC", status: "external_only", disease_type: "Gallbladder cancer" },
          { id: "EXT-MM", status: "external_only", disease_type: "Multiple myeloma" },
        ]}
        repositoryDatasets={[
          molecularDataset,
          {
            ...molecularDataset,
            id: "external-mm-survival",
            name: "MM survival cohort",
            tcga_cohort: "EXT-MM",
            capabilities: { survival: { available: true } },
            available_modules: ["analysis", "compare", "multiverse"],
          },
        ]}
        userDataset={null}
        filters={{}}
        expressionScales={[{ value: "rna", label: "Release expression" }]}
        expressionScaleValue="rna"
        onSelectCohort={() => {}}
        onSelectRepositoryDataset={() => {}}
        onSelectExpressionScale={() => {}}
        onClearEligibility={() => {}}
        recentAnalyses={[]}
        onDownload={() => {}}
      />,
    );

    expect(markup).toContain("EXT-GBC · Gallbladder cancer");
    expect(markup).not.toContain("EXT-MM · Multiple myeloma");
    expect(markup).toMatch(/<button[^>]*disabled=""[^>]*>Survival groups<\/button>/);
    expect(markup).not.toContain("Expression comparison is not available for this release");
  });

  test("navigation order, static autocomplete and responsive plot constraints are explicit", () => {
    const styles = readFileSync(new URL("../styles.css", import.meta.url), "utf8");
    const comparePosition = APP_MODULE_ORDER.indexOf("compare");
    const expressionPosition = APP_MODULE_ORDER.indexOf("expression");
    const gseaPosition = APP_MODULE_ORDER.indexOf("gsea");

    expect(comparePosition).toBeLessThan(expressionPosition);
    expect(expressionPosition).toBeLessThan(gseaPosition);
    expect(styles).toContain(".expression-gene-autocomplete");
    expect(styles).toContain("animation: none");
    expect(styles).toContain(".expression-svg-scroll:focus-visible");
    expect(styles).toContain("overflow: auto");
    expect(styles).toContain("@media (max-width: 760px)");
  });
});
