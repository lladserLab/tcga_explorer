import React from "react";
import { readFileSync } from "node:fs";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, test } from "vitest";

import GseaModule, { GseaResult } from "./GseaModule";
import { createDefaultGseaState } from "./gseaContract";

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
    schema_version: "tcga-trace-camera-preranked-gsea-result-v2",
    gsea_id: "gsea-accessibility-test",
    pipeline_version: "camera-estimated-correlation-bh-preranked-effect-contract-v2.0",
    cohort: "TCGA-KIRC",
    grouping: {
      group_counts: { Low: 12, High: 13 },
    },
    gene_set_collection: {
      label: "ImmPort",
      version: "frozen-test",
    },
    ranking: {
      genes_ranked: 1200,
      permutations: 1000,
      seed: 17291,
    },
    inference: {
      primary_method: "limma_camera",
      inter_gene_correlation: "estimated_per_gene_set",
      inferential_role: "associational",
      camera_engine_seconds: 0.2,
    },
    summary: {
      group_a_label: "Low",
      group_b_label: "High",
      pathways_tested: 1,
      pathways_at_fdr: 1,
      enriched_in_group_b: 1,
      enriched_in_group_a: 0,
      fdr_threshold: 0.25,
    },
    pathways: [
      {
        pathway: "INTERFERON_SIGNALING",
        description: "Interferon response",
        size_used: 8,
        es: 0.63,
        nes: 1.74,
        p_value: 0.002,
        fdr: 0.04,
        camera_correlation: 0.08,
        camera_direction: "group_b",
        nes_direction: "group_b",
        direction_concordant: true,
        inference_method: "limma_camera",
        effect_method: "weighted_preranked_gsea",
        effect_inferential_role: "descriptive",
        leading_edge: [
          "STAT1",
          "IRF1",
          "CXCL10",
          "GBP1",
          "ISG15",
          "OAS1",
        ],
      },
    ],
    downloads: {
      csv: "/api/v1/gsea.csv",
      dotplot_svg: "/api/v1/gsea.dotplot.svg",
      svg: "/api/v1/gsea.landscape.svg",
      audit_json: "/api/v1/gsea.audit.json",
    },
    audit: {
      result_core_sha256: "0123456789abcdef0123456789abcdef",
    },
    warnings: [],
  };
}

describe("GSEA module accessibility contract", () => {
  test("renders BRCA PAM50 levels, patient counts and provenance", () => {
    const clinicalFilters = {
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
          analysis_note: "Expression-derived grouping; exploratory circularity.",
        },
      ],
    };
    const markup = renderToStaticMarkup(
      <GseaModule
        state={{
          ...createDefaultGseaState(),
          clinical_variable: "paper_BRCA_Subtype_PAM50",
          group_a_values: ["LumA"],
          group_b_values: ["Basal"],
        }}
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
        filters={clinicalFilters}
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
    expect(markup).toContain("Luminal A<small>n=562</small>");
    expect(markup).toContain("Basal<small>n=190</small>");
    expect(markup).toContain("Rare subtype<small>n=3 · unavailable for an individual group</small>");
    expect(markup).toContain("gsea-level-row is-unavailable");
    expect(markup).toContain('disabled=""');
    expect(markup).toContain(
      "1,083 of 1,095 patients annotated before eligibility filters (98.9%)",
    );
    expect(markup).toContain("Do not assume equivalence across platforms.");
    expect(markup).toContain("paper_BRCA_Subtype_PAM50");
  });

  test("the result exposes a named keyboard-scrollable table and complete data", () => {
    const markup = renderToStaticMarkup(
      <GseaResult result={resultFixture()} onDownload={() => {}} />,
    );

    expect(markup).toContain(
      'class="table-scroll gsea-table-region" role="region" tabindex="0"',
    );
    expect(markup).toContain(
      'aria-labelledby="gsea-result-table-heading-gsea-accessibility-test"',
    );
    expect(markup).toContain("<caption");
    expect(markup).toContain('scope="col"');
    expect(markup).toContain('scope="row"');
    expect(markup).toContain(
      "Leading-edge genes: STAT1, IRF1, CXCL10, GBP1, ISG15, OAS1",
    );
    expect(markup).toContain(
      'aria-label="Download pathway results as CSV"',
    );
    expect(markup).toContain(
      'aria-label="Download GSEA DotPlot as SVG"',
    );
    expect(markup).toContain(
      'aria-label="Download bidirectional NES landscape as SVG"',
    );
    expect(markup).toContain(
      '<figure class="gsea-dotplot" aria-labelledby=',
    );
    expect(markup).toContain(
      'role="img" tabindex="0" aria-label="Dot plot of 1 pathways.',
    );
    expect(markup).toContain(
      "Point area is min(−log10(CAMERA FDR), 10); horizontal position and blue–white–red color are NES.",
    );
    expect(markup).toContain("CAMERA inference · preranked effect");
    expect(markup).toContain("NES direction");
    expect(markup).toContain("CAMERA direction");
    expect(markup).toContain("Same direction");
    expect(markup).toContain("1 toward target · 0 toward reference · CAMERA direction");
    expect(markup).toContain("Residual ρ");
    expect(markup).toContain(
      'class="gsea-dotplot-legends" data-position="top"',
    );
    expect(markup).toContain(
      'data-role="nes-axis" data-position="bottom"',
    );
    expect(markup).toContain('data-role="nes-zero-reference"');
    expect(markup).toContain(
      'data-role="pathway-label" data-axis-side="right"',
    );
    expect(markup).toContain('fill="#ff0000"');
    expect(markup.indexOf("gsea-dotplot-legends")).toBeLessThan(
      markup.indexOf("gsea-dotplot-canvas"),
    );
    expect(markup).toContain('data-negative-log10-fdr="1.3979400086720375"');
    expect(markup).toContain(
      "The pathway CSV contains the complete result.",
    );
  });

  test("renders archived v1 p-values without relabeling them as CAMERA", () => {
    const legacy = resultFixture();
    legacy.schema_version = "tcga-trace-preranked-gsea-result-v1";
    legacy.pipeline_version = "preranked-gene-set-permutation-bh-contract-v1.6";
    delete legacy.inference;
    for (const pathway of legacy.pathways) {
      delete pathway.camera_correlation;
      delete pathway.camera_direction;
      delete pathway.nes_direction;
      delete pathway.direction_concordant;
      delete pathway.inference_method;
    }

    const markup = renderToStaticMarkup(
      <GseaResult result={legacy} onDownload={() => {}} />,
    );

    expect(markup).toContain("Archived preranked GSEA · v1 method");
    expect(markup).toContain("Legacy permutation p");
    expect(markup).toContain("legacy permutation FDR");
    expect(markup).toContain("preranked-gene-set-permutation-bh-contract-v1.6");
    expect(markup).toContain("are not CAMERA results");
    expect(markup).not.toContain("CAMERA p</th>");
    expect(markup).not.toContain("Residual ρ");
    expect(markup).not.toContain("Same direction");
  });

  test("invalid setup remains operable and exposes its requirements", () => {
    const state = createDefaultGseaState();
    const markup = renderToStaticMarkup(
      <GseaModule
        state={state}
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
        expressionScales={[
          { value: "log2_tpm", label: "log2(TPM + 1)" },
        ]}
        expressionScaleValue="log2_tpm"
        onSelectCohort={() => {}}
        onSelectRepositoryDataset={() => {}}
        onSelectExpressionScale={() => {}}
        onClearEligibility={() => {}}
        recentAnalyses={[]}
        onDownload={() => {}}
      />,
    );

    expect(markup).toContain(
      '<legend class="sr-only">GSEA setup parameters</legend>',
    );
    expect(markup).toContain(
      'role="status" aria-live="polite" aria-atomic="true"',
    );
    expect(markup).toContain('id="gsea-run-requirements"');
    expect(markup).toContain('aria-describedby="gsea-run-requirements"');

    const runTextPosition = markup.indexOf("Run GSEA");
    const runButtonStart = markup.lastIndexOf("<button", runTextPosition);
    const runButtonEnd = markup.indexOf(">", runButtonStart);
    const runButtonTag = markup.slice(runButtonStart, runButtonEnd + 1);
    expect(runButtonTag).toContain('aria-disabled="true"');
    expect(runButtonTag).not.toContain(" disabled");
  });

  test("offers an endpointless transcriptome while blocking inherited survival groups", () => {
    const molecularDataset = {
      id: "external-gbc-gsea",
      kind: "external",
      name: "GBC transcriptome cohort",
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
      <GseaModule
        state={createDefaultGseaState()}
        setState={() => {}}
        form={{
          cohort: "EXT-GBC",
          dataset_id: molecularDataset.id,
          dataset_release_id: "release-1",
          expression_layer_id: "rna",
          expression_scale: "log2_tpm",
          filters: EMPTY_FILTERS,
        }}
        cohorts={[{ id: "EXT-GBC", status: "external_only", disease_type: "Gallbladder cancer" }]}
        repositoryDatasets={[molecularDataset]}
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

    expect(markup).toContain("External · GBC transcriptome cohort");
    expect(markup).toMatch(/<button[^>]*disabled=""[^>]*>Survival groups<\/button>/);
    expect(markup).not.toContain("GSEA is not available for this release");
  });

  test("completion focus and selected-source styling remain explicit", () => {
    const componentSource = readFileSync(
      new URL("./GseaModule.jsx", import.meta.url),
      "utf8",
    );
    const styles = readFileSync(
      new URL("../styles.css", import.meta.url),
      "utf8",
    );

    expect(componentSource).toContain(
      "resultHeadingRef.current?.focus({ preventScroll: false })",
    );
    expect(styles).toContain(
      '.gsea-source-tabs button[aria-pressed="true"]',
    );
    expect(styles).toContain(".gsea-table-region:focus-visible");
  });

  test("expression grouping exposes a dataset-aware combobox without replacing the signature field", () => {
    const state = {
      ...createDefaultGseaState(),
      grouping_source: "expression",
      signature_method: "weighted",
      signature_genes: "CA9:1.5, VE:-2",
      group_a_label: "Low",
      group_b_label: "High",
    };
    const markup = renderToStaticMarkup(
      <GseaModule
        state={state}
        setState={() => {}}
        form={{
          cohort: "TCGA-KIRC",
          dataset_id: null,
          dataset_release_id: null,
          expression_layer_id: null,
          expression_scale: "log2_tpm",
          filters: EMPTY_FILTERS,
        }}
        cohorts={[{ id: "TCGA-KIRC", disease_type: "Kidney cancer" }]}
        repositoryDatasets={[]}
        userDataset={null}
        filters={{}}
        expressionScales={[
          { value: "log2_tpm", label: "log2(TPM + 1)" },
        ]}
        expressionScaleValue="log2_tpm"
        onSelectCohort={() => {}}
        onSelectRepositoryDataset={() => {}}
        onSelectExpressionScale={() => {}}
        onClearEligibility={() => {}}
        recentAnalyses={[]}
        onDownload={() => {}}
      />,
    );

    expect(markup).toContain('id="gsea-signature-genes"');
    expect(markup).toContain('role="combobox"');
    expect(markup).toContain('aria-autocomplete="list"');
    expect(markup).toContain("CA9:1.5, VE:-2");
    expect(markup).toContain(
      "Weighted mode preserves GENE:weight values when completing a symbol.",
    );
  });

  test("large pathway families render one table page and disclose the complete CSV", () => {
    const result = resultFixture();
    result.pathways = Array.from({ length: 75 }, (_, index) => ({
      ...result.pathways[0],
      pathway: `PATHWAY_${String(index).padStart(3, "0")}`,
      nes: index % 2 ? -1.2 : 1.2,
      fdr: (index + 1) / 100,
    }));
    const markup = renderToStaticMarkup(
      <GseaResult result={result} onDownload={() => {}} />,
    );
    const tableBody = markup.match(/<tbody>(.*?)<\/tbody>/s)?.[1] || "";

    expect((tableBody.match(/<tr>/g) || [])).toHaveLength(50);
    expect(markup).toContain("Showing 1–50 of 75 pathways.");
    expect(markup).toContain("Page 1 of 2");
    expect(markup).toContain(
      "The pathway CSV contains the complete result.",
    );
  });
});
