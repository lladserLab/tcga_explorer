import React from "react";
import { readFileSync } from "node:fs";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, test } from "vitest";

import HierarchicalPanCancerModule, {
  HierarchicalPanCancerJobRecovery,
  HierarchicalPanCancerModeSelector,
  HierarchicalPanCancerPreflight,
  HierarchicalPanCancerRequestControls,
  HierarchicalPanCancerResults,
  HierarchicalPanCancerForest,
  HierarchicalPanCancerDiagnostics,
  canonicalHierarchicalRequest,
  fetchRecordedHierarchicalJob,
  hierarchicalPreflightIsCurrent,
  hierarchicalRequestFingerprint,
} from "./HierarchicalPanCancerModule";
import {
  forestDomain,
  forestEstimate,
  hierarchicalViewPayload,
  preflightCancerGroups,
  summarizePreflight,
  heterogeneityBand,
} from "./HierarchicalPanCancerContract";

function preflightFixture() {
  const brcaStudies = [
    {
      universe_id: "tcga-brca-r38",
      release_id: "TCGA-BRCA-r38",
      study_cluster_id: "TCGA-BRCA",
      cancer_code: "BRCA",
      source_kind: "tcga",
      evidence_tier: "primary",
      included: true,
      analysis_eligible: true,
      selected_for_cluster: true,
      n_patients: 1095,
      n_events: 152,
      n_censored: 943,
      endpoint: "OS",
      time_origin_class: "primary_diagnosis",
      clinical_context: "primary_baseline",
      reasons: [],
    },
    {
      universe_id: "metabric-2024",
      release_id: "METABRIC-2024.1",
      study_cluster_id: "METABRIC",
      cancer_code: "BRCA",
      source_kind: "external",
      source_provider: "cBioPortal curated",
      evidence_tier: "primary",
      included: true,
      analysis_eligible: true,
      selected_for_cluster: true,
      n_patients: 1904,
      n_events: 622,
      n_censored: 1282,
      endpoint: "OS",
      time_origin_class: "primary_diagnosis",
      clinical_context: "primary_baseline",
      reasons: [],
    },
    {
      universe_id: "brca-small-series",
      release_id: "BRCA-SMALL-1",
      study_cluster_id: "BRCA-SMALL",
      cancer_code: "BRCA",
      source_kind: "external",
      evidence_tier: "exploratory",
      included: false,
      analysis_eligible: false,
      selected_for_cluster: true,
      n_patients: 31,
      n_events: 11,
      n_censored: 20,
      reasons: ["exploratory_evidence_only"],
    },
  ];
  const luadStudies = [
    {
      universe_id: "tcga-luad-r38",
      release_id: "TCGA-LUAD-r38",
      study_cluster_id: "TCGA-LUAD",
      cancer_code: "LUAD",
      source_kind: "tcga",
      evidence_tier: "primary",
      included: true,
      analysis_eligible: true,
      selected_for_cluster: true,
      n_patients: 585,
      n_events: 214,
      n_censored: 371,
      endpoint: "OS",
      time_origin_class: "primary_diagnosis",
      clinical_context: "primary_baseline",
      reasons: [],
    },
    {
      universe_id: "luad-treatment-series",
      release_id: "LUAD-TX-2",
      study_cluster_id: "LUAD-TX",
      cancer_code: "LUAD",
      source_kind: "external",
      evidence_tier: "excluded",
      included: false,
      analysis_eligible: false,
      selected_for_cluster: false,
      n_patients: 144,
      n_events: 88,
      n_censored: 56,
      endpoint: "OS",
      time_origin_class: "treatment_start",
      clinical_context: "advanced_treatment",
      reasons: [
        "clinical_context_mismatch:advanced_treatment",
        "time_origin_mismatch:treatment_start",
      ],
    },
  ];
  return {
    schema_version: "tcga-trace-hierarchical-pancancer-preflight-v1",
    pipeline_version: "hierarchical-pancancer-v1.0",
    registry_version: "study-universes-2026-08-04",
    request: {
      gene_symbol: "ESR1",
      endpoint: "OS",
      include_exploratory: false,
      effect_scale: "within_study_iqr",
    },
    summary: {
      cancers: 2,
      total_universes: 5,
      primary: 3,
      exploratory: 1,
      excluded: 1,
      patients: 3584,
      events: 988,
      endpoint: "OS",
      effect_unit: "HR per +1 within-study expression IQR",
    },
    universes: [...brcaStudies, ...luadStudies],
    cancer_groups: [
      { cancer_code: "BRCA", cancer_label: "Breast invasive carcinoma", studies: brcaStudies },
      { cancer_code: "LUAD", cancer_label: "Lung adenocarcinoma", studies: luadStudies },
    ],
    warnings: [
      "External releases are kept independent; patient-level matrices are never concatenated.",
    ],
  };
}

function resultFixture() {
  return {
    schema_version: "tcga-trace-hierarchical-pancancer-result-v1",
    scan_id: "hpc-ESR1-001",
    status: "completed",
    pipeline_version: "hierarchical-pancancer-v1.0",
    registry_version: "study-universes-2026-08-04",
    analysis_mode: "hierarchical",
    gene_symbol: "ESR1",
    endpoint: "OS",
    effect_scale: {
      id: "within_study_iqr",
      label: "Cox hazard ratio per +1 within-study expression IQR",
    },
    request_snapshot: { gene_symbol: "ESR1", include_exploratory: false },
    preflight: preflightFixture(),
    summary: {
      studies: 4,
      completed_studies: 3,
      compatible_studies: 3,
      completed_primary_studies: 3,
      cancers: 2,
      patients: 3584,
      events: 988,
    },
    study_results: [
      {
        release_id: "TCGA-BRCA-r38",
        study_id: "TCGA-BRCA",
        name: "TCGA BRCA",
        cancer_id: "BRCA",
        source_kind: "tcga",
        status: "completed",
        pooling_eligible: true,
        n_patients: 1095,
        n_events: 152,
        log_hr: -0.2231,
        standard_error: 0.071,
        weight_percent: 31.2,
      },
      {
        release_id: "METABRIC-2024.1",
        study_id: "METABRIC",
        study_label: "METABRIC 2024",
        cancer_id: "BRCA",
        source_kind: "external",
        source_provider: "cBioPortal curated",
        status: "completed",
        pooling_eligible: true,
        n_patients: 1904,
        n_events: 622,
        hazard_ratio: 0.91,
        hr_conf_low: 0.83,
        hr_conf_high: 1.00,
        weight_percent: 34.8,
      },
      {
        release_id: "TCGA-LUAD-r38",
        study_id: "TCGA-LUAD",
        study_label: "TCGA LUAD",
        cancer_id: "LUAD",
        source_kind: "tcga",
        status: "completed",
        pooling_eligible: true,
        n_patients: 585,
        n_events: 214,
        hazard_ratio: 1.18,
        hr_conf_low: 1.02,
        hr_conf_high: 1.37,
        weight_percent: 34.0,
      },
      {
        release_id: "LUAD-TX-2",
        study_id: "LUAD-TX",
        study_label: "LUAD treatment-start series",
        cancer_id: "LUAD",
        source_kind: "external",
        status: "excluded",
        pooling_eligible: false,
        pooling_exclusion_reason: "mixed_time_origins",
        n_patients: 144,
        n_events: 88,
      },
    ],
    cancer_results: [
      {
        cancer_id: "BRCA",
        cancer_label: "BRCA synthesis",
        status: "completed",
        n_studies: 2,
        n_patients: 2999,
        n_events: 774,
        hazard_ratio: 0.87,
        hr_conf_low: 0.75,
        hr_conf_high: 1.00,
        p_value: 0.012,
        fdr: 0.024,
        weight_percent: 52.6,
      },
      {
        cancer_id: "LUAD",
        cancer_label: "LUAD synthesis",
        status: "completed",
        n_studies: 1,
        n_patients: 585,
        n_events: 214,
        hazard_ratio: 1.18,
        hr_conf_low: 1.02,
        hr_conf_high: 1.37,
        p_value: 0.031,
        fdr: null,
        weight_percent: 47.4,
      },
    ],
    global_result: {
      available: true,
      model: "REML random-effects with modified HKSJ inference",
      units: 2,
      cancers: 2,
      studies: 3,
      random_effect: {
        hazard_ratio: 1.01,
        hr_conf_low: 0.65,
        hr_conf_high: 1.57,
        p_value: 0.94,
      },
      heterogeneity: {
        i_squared: 71.4,
        tau_squared: 0.031,
        q_p_value: 0.028,
        df: 1,
      },
      prediction_interval: {
        hazard_ratio_low: 0.49,
        hazard_ratio_high: 2.08,
      },
      classification: "heterogeneous_or_context_dependent",
      formal_pan_cancer_support: {
        supported: false,
        reasons: ["requires at least 5 cancers; found 2"],
      },
      within_cancer_replication: {
        replicated_cancer_count: 1,
      },
    },
    leave_one_out: {
      cancers: [
        {
          omitted_kind: "cancer",
          omitted_cancer_id: "BRCA",
          available: true,
          hazard_ratio: 1.18,
        },
        {
          omitted_kind: "cancer",
          omitted_cancer_id: "LUAD",
          available: true,
          hazard_ratio: 0.87,
        },
      ],
      studies: [
        {
          omitted_kind: "study",
          omitted_cancer_id: "BRCA",
          omitted_release_id: "METABRIC-2024.1",
          omitted_study_id: "METABRIC",
          available: true,
          hazard_ratio: 1.12,
        },
      ],
    },
    warnings: ["Global inference is exploratory because fewer than five cancers contribute."],
    sensitivities: {
      primary_plus_exploratory: {
        description: "Adds studies meeting the labeled exploratory thresholds",
        summary: { studies: 2 },
        global_effect: {
          random_effect: {
            hazard_ratio: 1.08,
            hr_conf_low: 0.74,
            hr_conf_high: 1.58,
          },
        },
        classification: "heterogeneous_or_context_dependent",
      },
    },
    downloads: {
      studies: "/api/pancancer/hierarchical-survival/hpc-ESR1-001/download/studies",
      cancers: "/api/pancancer/hierarchical-survival/hpc-ESR1-001/download/cancers",
      ledger: "/api/pancancer/hierarchical-survival/hpc-ESR1-001/download/ledger",
      audit_json: "/api/v1/pancancer/hierarchical-survival/hpc-ESR1-001/audit.json",
    },
  };
}

describe("Hierarchical pan-cancer frontend contract", () => {
  test("unavailable cancer FDR and weight remain absent in the exact estimates table", () => {
    const markup = renderToStaticMarkup(<HierarchicalPanCancerForest rows={[{
      id: "singleton", label: "Singleton cancer", kind: "cancer",
      hazard_ratio: 1.2, hr_conf_low: 0.8, hr_conf_high: 1.6,
      p_value: 0.12, fdr: null, weight_percent: null,
      patients: 30, events: 8,
    }]} />);
    expect(markup).toContain("<td>0.120</td><td>—</td><td>—</td>");
    expect(markup).not.toContain("0.0e+0");
  });

  test("unavailable heterogeneity is not displayed as zero or classified as low", () => {
    const markup = renderToStaticMarkup(<HierarchicalPanCancerDiagnostics
      heterogeneity={{ units: 5, i_squared: null, tau_squared: null, q_p_value: null }}
    />);
    expect(markup).toContain("<dt>I²</dt><dd>—</dd>");
    expect(markup).toContain("<dt>τ²</dt><dd>—</dd>");
    expect(markup).toContain("<dt>Q p</dt><dd>—</dd>");
    expect(heterogeneityBand(null)).toBe("Not estimable");
    expect(heterogeneityBand(0)).toBe("Low");
    expect(markup).not.toContain("Low heterogeneity");
  });

  test("frames the two pan-cancer modes by the questions they answer", () => {
    const markup = renderToStaticMarkup(
      <HierarchicalPanCancerModeSelector
        value="hierarchical"
        onChange={() => {}}
      />,
    );

    expect(markup).toContain("1. Choose where to look");
    expect(markup).toContain("Across TCGA cancer types");
    expect(markup).toContain("Across independent studies");
    expect(markup).toContain("Test one gene or signature separately in each TCGA cancer type.");
    expect(markup).toContain("Uses overall survival.");
    expect(markup).toContain('checked="" value="hierarchical"');
    expect(markup).toContain("matching outcome definitions, time origins, clinical contexts");
    expect(markup).not.toMatch(/\d+ TCGA cancers/);
    expect(markup).not.toContain("external studies / 9 cancers");
  });

  test("renders an auditable preflight grouped by cancer and universe with reasons", () => {
    const preflight = preflightFixture();
    const markup = renderToStaticMarkup(
      <HierarchicalPanCancerPreflight
        preflight={preflight}
        onRefresh={() => {}}
        onRun={() => {}}
      />,
    );

    expect(markup).toContain("Breast invasive carcinoma");
    expect(markup).toContain("Lung adenocarcinoma");
    expect(markup).toContain("METABRIC-2024.1");
    expect(markup).toContain("Exploratory held out");
    expect(markup).toContain("clinical_context_mismatch");
    expect(markup).toContain("Clinical context mismatch: advanced treatment");
    expect(markup).toContain("time_origin_mismatch");
    expect(markup).toContain("3 / 5 studies pass");
    expect(markup).toContain('role="region" tabindex="0"');
    expect(markup).toContain('aria-describedby=');
    expect(markup).toContain("patient-level matrices are never concatenated");

    const groups = preflightCancerGroups(preflight);
    expect(groups).toHaveLength(2);
    expect(groups[0].studies).toHaveLength(3);
    expect(summarizePreflight(preflight)).toMatchObject({
      cancers: 2,
      totalStudies: 5,
      includedStudies: 3,
      excludedStudies: 2,
      replicatedCancers: 1,
      replicatedEvents: 774,
      preliminaryGlobalReady: false,
      effectUnit: "HR per +1 within-study expression IQR",
    });

    const expanded = preflightFixture();
    expanded.request.include_exploratory = true;
    const exploratory = expanded.cancer_groups[0].studies.find(
      (study) => study.evidence_tier === "exploratory",
    );
    exploratory.analysis_eligible = true;
    expect(
      preflightCancerGroups(expanded)[0].studies.find(
        (study) => study.evidence_tier === "exploratory",
      ).included,
    ).toBe(true);
  });

  test("exposes controlled request fields and an optional gene-selector render prop", () => {
    const markup = renderToStaticMarkup(
      <HierarchicalPanCancerRequestControls
        state={{
          gene_symbol: "ESR1",
          scope: "combined",
          clinical_context: "primary_baseline",
          min_patients: 20,
          min_events: 10,
          min_censored: 5,
          include_exploratory: true,
        }}
        onChange={() => {}}
        geneSelector={(props) => (
          <input {...props} role="combobox" aria-autocomplete="list" />
        )}
      />,
    );

    expect(markup).toContain("Choose a gene and cohorts");
    expect(markup).toContain('role="combobox"');
    expect(markup).toContain('aria-autocomplete="list"');
    expect(markup).toContain('value="combined" selected=""');
    expect(markup).toContain('value="primary_baseline" selected=""');
    expect(markup).toContain('value="20"');
    expect(markup).toContain('value="10"');
    expect(markup).toContain('value="5"');
    expect(markup).toContain('type="checkbox" checked=""');
    expect(markup).toContain("Within-study IQR");
    expect(markup).toContain("Independent clusters");
  });

  test("fingerprints every scientific input with canonical selection ordering", () => {
    const request = {
      gene_symbol: " esr1 ",
      scope: "combined",
      cancers: ["LUAD", "brca", "LUAD"],
      study_ids: ["study-b", "study-a", "study-b"],
      endpoint: "OS",
      clinical_context: "primary_baseline",
      time_origin_policy: "strict_baseline",
      effect_scale: "within_study_iqr",
      overlap_policy: "independent_clusters",
      min_patients: "20",
      min_events: 10,
      min_censored: 5,
      include_exploratory: false,
      fdr_threshold: "0.05",
    };
    const equivalent = {
      ...request,
      gene_symbol: "ESR1",
      cancers: ["BRCA", "LUAD"],
      study_ids: ["study-a", "study-b"],
      min_patients: 20,
      fdr_threshold: 0.05,
    };
    const canonical = canonicalHierarchicalRequest(request);

    expect(canonical).toMatchObject({
      gene_symbol: "ESR1",
      cancers: ["BRCA", "LUAD"],
      study_ids: ["study-a", "study-b"],
      min_patients: 20,
      fdr_threshold: 0.05,
    });
    expect(hierarchicalRequestFingerprint(request)).toBe(
      hierarchicalRequestFingerprint(equivalent),
    );

    const mutations = [
      { gene_symbol: "TP53" },
      { scope: "tcga_only" },
      { cancers: ["BRCA"] },
      { study_ids: ["study-a"] },
      { endpoint: "PFS" },
      { clinical_context: "advanced_treatment" },
      { time_origin_policy: "changed_policy" },
      { effect_scale: "changed_scale" },
      { overlap_policy: "changed_overlap" },
      { min_patients: 21 },
      { min_events: 11 },
      { min_censored: 6 },
      { include_exploratory: true },
      { fdr_threshold: 0.1 },
    ];
    for (const mutation of mutations) {
      expect(
        hierarchicalRequestFingerprint({ ...equivalent, ...mutation }),
      ).not.toBe(hierarchicalRequestFingerprint(equivalent));
    }
  });

  test("invalidates and hides a preflight resolved for obsolete inputs", () => {
    const preflight = preflightFixture();
    expect(
      hierarchicalPreflightIsCurrent(preflight, {
        gene_symbol: "ESR1",
      }),
    ).toBe(true);
    expect(
      hierarchicalPreflightIsCurrent(preflight, {
        gene_symbol: "TP53",
      }),
    ).toBe(false);

    const markup = renderToStaticMarkup(
      <HierarchicalPanCancerModule
        mode="hierarchical"
        requestState={{ gene_symbol: "TP53" }}
        preflight={preflight}
        preflightStatus="ready"
        onRequestPreflight={() => {}}
        onRun={() => {}}
      />,
    );

    expect(markup).toContain("Inputs changed after the last eligibility check");
    expect(markup).toContain("Check eligibility again");
    expect(markup).not.toContain("METABRIC-2024.1");
    expect(markup).not.toContain("Run hierarchical analysis");
  });

  test("offers an explicit retry after a failed preflight", () => {
    const markup = renderToStaticMarkup(
      <HierarchicalPanCancerPreflight
        status="error"
        error="Repository temporarily unavailable"
        onRefresh={() => {}}
      />,
    );

    expect(markup).toContain("Preflight could not be completed");
    expect(markup).toContain("Repository temporarily unavailable");
    expect(markup).toContain("Retry eligibility check");
  });

  test("exposes recorded-job refresh and explicit form-result recovery", () => {
    const markup = renderToStaticMarkup(
      <HierarchicalPanCancerJobRecovery
        recovery={{
          status: "ready",
          error: "",
          entry: {
            event_id: "event-hpc",
            job_id: "a".repeat(32),
            job_status: "running",
            label: "ESR1 hierarchy",
          },
          job: {
            id: "a".repeat(32),
            kind: "pancancer_hierarchical",
            status: "completed",
            result: resultFixture(),
          },
        }}
        onRefresh={() => {}}
        onRecover={() => {}}
      />,
    );

    expect(markup).toContain("Resume the latest hierarchical run");
    expect(markup).toContain("Refresh job");
    expect(markup).toContain("Recover form and result");
    expect(markup).toContain("never runs the analysis automatically");
  });

  test("refreshes only hierarchical jobs through the public job contract", async () => {
    const fetchImpl = async () => ({
      ok: true,
      status: 200,
      json: async () => ({
        id: "a".repeat(32),
        kind: "pancancer_hierarchical",
        status: "completed",
        result: resultFixture(),
      }),
    });
    await expect(
      fetchRecordedHierarchicalJob("a".repeat(32), fetchImpl),
    ).resolves.toMatchObject({
      kind: "pancancer_hierarchical",
      status: "completed",
    });
    await expect(
      fetchRecordedHierarchicalJob("b".repeat(32), async () => ({
        ok: true,
        status: 200,
        json: async () => ({
          id: "b".repeat(32),
          kind: "pancancer",
          status: "completed",
        }),
      })),
    ).rejects.toThrow("not a hierarchical pan-cancer run");
  });

  test("adapts the backend result into all, compatible and sensitivity hierarchies", () => {
    const result = resultFixture();
    const all = hierarchicalViewPayload(result, "all_studies");
    const compatible = hierarchicalViewPayload(result, "compatible");
    const sensitivities = hierarchicalViewPayload(result, "sensitivities");

    expect(all.rows).toHaveLength(7);
    expect(compatible.rows).toHaveLength(6);
    expect(sensitivities.rows).toHaveLength(3);
    expect(sensitivities.leaveOneOut).toHaveLength(3);
    expect(sensitivities.leaveOneOut[0]).toMatchObject({
      omitted_id: "BRCA",
      hazard_ratio: 1.18,
    });

    const estimateFromLogScale = forestEstimate(result.study_results[0]);
    expect(estimateFromLogScale.estimable).toBe(true);
    expect(estimateFromLogScale.hazardRatio).toBeCloseTo(0.8, 2);
    const domain = forestDomain(all.rows);
    expect(domain.min).toBeLessThan(1);
    expect(domain.max).toBeGreaterThan(1);
    expect(domain.min * domain.max).toBeCloseTo(1, 8);
  });

  test("renders an accessible hierarchical forest and heterogeneity audit", () => {
    const markup = renderToStaticMarkup(
      <HierarchicalPanCancerResults
        result={resultFixture()}
        activeView="all_studies"
        onViewChange={() => {}}
      />,
    );

    expect(markup).toContain('role="tablist"');
    expect(markup).toContain("All studies");
    expect(markup).toContain("Compatible");
    expect(markup).toContain("Sensitivities");
    expect(markup).toContain('role="img" tabindex="0"');
    expect(markup).toContain("Study, cancer and global estimates");
    expect(markup).toContain("TCGA BRCA");
    expect(markup).toContain("METABRIC 2024");
    expect(markup).toContain("BRCA synthesis");
    expect(markup).toContain("Combined estimate across compatible cancers");
    expect(markup).toContain("hierarchical-pc-study-point is-tcga");
    expect(markup).toContain("hierarchical-pc-study-point is-external");
    expect(markup).toContain("hierarchical-pc-summary-point is-universe");
    expect(markup).toContain("Exact estimates and support");
    expect(markup).toContain("<th scope=\"col\">FDR</th>");
    expect(markup).toContain("0.024");
    expect(markup).toContain("I²");
    expect(markup).toContain("Not summarized");
    expect(markup).toContain("Fewer than five evidence units");
    expect(markup).not.toContain("71.4%");
    expect(markup).not.toContain("0.49–2.08");
    expect(markup).toContain("3 refits");
    expect(markup).toContain("fewer than five cancers contribute");
    expect(markup).toContain("Study effects · CSV");
    expect(markup).toContain("Cancer effects · CSV");
    expect(markup).toContain("Inclusion ledger · CSV");
    expect(markup).toContain("Audit record · JSON");
    expect(markup).toContain("Heterogeneous or context dependent");
    expect(markup).toContain("Deployed two-stage summary");
    expect(markup).toContain("Two-stage result label");
    expect(markup).not.toContain("Formal support met");
    expect(markup).not.toContain("Pan-cancer interpretation");
    expect(markup).toContain("requires at least 5 cancers; found 2");

    const supportedResult = resultFixture();
    supportedResult.global_result.formal_pan_cancer_support = {
      supported: true,
      reasons: [],
    };
    supportedResult.global_result.classification = "no_average_association";
    const supportedMarkup = renderToStaticMarkup(
      <HierarchicalPanCancerResults
        result={supportedResult}
        activeView="all_studies"
        onViewChange={() => {}}
      />,
    );
    expect(supportedMarkup).toContain("Evidence threshold met");
    expect(supportedMarkup).toContain("does not establish calibrated intervals or an effect that applies to every cancer");
    expect(supportedMarkup).toContain("Two-stage CI includes HR 1");
    expect(supportedMarkup).not.toContain("No average association");
  });

  test("compatible and sensitivity views preserve their declared evidence level", () => {
    const compatibleMarkup = renderToStaticMarkup(
      <HierarchicalPanCancerResults
        result={resultFixture()}
        activeView="compatible"
        onViewChange={() => {}}
      />,
    );
    expect(compatibleMarkup).not.toContain("LUAD treatment-start series");
    expect(compatibleMarkup).toContain("METABRIC 2024");

    const sensitivityMarkup = renderToStaticMarkup(
      <HierarchicalPanCancerResults
        result={resultFixture()}
        activeView="sensitivities"
        onViewChange={() => {}}
      />,
    );
    expect(sensitivityMarkup).not.toContain("TCGA BRCA");
    expect(sensitivityMarkup).toContain("BRCA synthesis");
    expect(sensitivityMarkup).toContain("METABRIC");
    expect(sensitivityMarkup).toContain("Leave-one-out");
    expect(sensitivityMarkup).toContain("Primary plus exploratory");
    expect(sensitivityMarkup).toContain("Adds studies meeting the labeled exploratory thresholds");
  });

  test("the wrapper hides hierarchical evidence in TCGA reference mode", () => {
    const markup = renderToStaticMarkup(
      <HierarchicalPanCancerModule
        mode="tcga_reference"
        preflight={preflightFixture()}
        result={resultFixture()}
      />,
    );
    expect(markup).toContain("1. Choose where to look");
    expect(markup).not.toContain("Check which studies qualify");
    expect(markup).not.toContain("Hierarchical forest");
  });

  test("keeps responsive overflow, focus and reduced-motion behavior explicit", () => {
    const styles = readFileSync(
      new URL("./HierarchicalPanCancer.css", import.meta.url),
      "utf8",
    );
    const source = readFileSync(
      new URL("./HierarchicalPanCancerModule.jsx", import.meta.url),
      "utf8",
    );

    expect(styles).toContain(".hierarchical-pc-table-scroll");
    expect(styles).toContain("overflow: auto");
    expect(styles).toContain(":focus-visible");
    expect(styles).toContain("@media (max-width: 760px)");
    expect(styles).toContain("@media (prefers-reduced-motion: reduce)");
    expect(source).toContain('event.key === "ArrowRight"');
    expect(source).not.toContain("lucide-react");
  });
});
