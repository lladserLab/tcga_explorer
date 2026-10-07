import React from "react";
import { afterEach, describe, expect, test, vi } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";

import RepositoryCatalog from "./RepositoryCatalog";

function installCatalogState(state) {
  vi.stubGlobal("window", {
    sessionStorage: {
      getItem: () => JSON.stringify(state),
      setItem: () => {},
    },
  });
}

const MOLECULAR_RELEASE = {
  id: "geo-gbc-expression",
  name: "Gallbladder expression cohort",
  cancer_code: "GBC",
  cancer_name: "Gallbladder cancer",
  tcga_cohort: "EXT-GBC",
  source_provider: "geo",
  source_accession: "GSE-GBC",
  patient_count: 84,
  sample_count: 84,
  gene_count: 18000,
  endpoints: [],
  expression_layer: { layer_id: "rna", label: "log2 normalized expression" },
  capabilities: {
    survival: {
      available: false,
      reason: "No documented time-to-event endpoint was released.",
    },
    expression_comparison: { available: true, reason: "Expression QC passed." },
    gsea: { available: true, reason: "Gene coverage QC passed." },
  },
  available_modules: ["expression", "gsea"],
};

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("capability-aware external cohort catalog", () => {
  test("routes an endpointless ready release only to supported modules", () => {
    installCatalogState({
      coverage: "available",
      view: "cancers",
      expandedCancer: "GBC",
      expandedDataset: "geo-gbc-expression",
    });
    const markup = renderToStaticMarkup(
      <RepositoryCatalog
        coverage={{
          datasets: 1,
          available_cancer_types: 1,
          cancers: [{
            code: "GBC",
            name: "Gallbladder cancer",
            primary_site: "Gallbladder",
            coverage_status: "available",
          }],
        }}
        datasets={[MOLECULAR_RELEASE]}
        candidates={[]}
        candidatesStatus="ready"
        onOpenModule={() => {}}
        onDownload={() => {}}
      />,
    );

    expect(markup).toContain("No time-to-event endpoint");
    expect(markup).toContain("Open Expression with Gallbladder expression cohort");
    expect(markup).toContain("Open GSEA with Gallbladder expression cohort");
    expect(markup).not.toContain("Open Survival with Gallbladder expression cohort");
    expect(markup).toContain("No documented time-to-event endpoint was released.");
  });

  test("keeps under-review candidates visibly non-executable", () => {
    installCatalogState({
      coverage: "under_review",
      view: "cancers",
      expandedCancer: "GBC",
    });
    const markup = renderToStaticMarkup(
      <RepositoryCatalog
        coverage={{ cancers: [] }}
        datasets={[]}
        candidates={[{
          id: "gbc-candidate",
          label: "Candidate GBC cohort",
          status: "under_review",
          tier: "S2",
          access_class: "public",
          disease: { id: "GBC", label: "Gallbladder cancer" },
          source: { repository: "geo", accession: "GSE-CANDIDATE" },
          blockers: [{ code: "linkage", detail: "Patient linkage audit" }],
          links: [],
          capabilities: {
            survival: { available: false, decision: "disabled", reason: "No endpoint." },
            expression_comparison: { available: false, decision: "pending", reason: "Matrix review pending." },
            gsea: { available: false, decision: "pending", reason: "Gene coverage review pending." },
          },
        }]}
        candidatesStatus="ready"
        onOpenModule={() => {}}
        onDownload={() => {}}
      />,
    );

    expect(markup).toContain("Under review");
    expect(markup).toContain("Not available for analysis");
    expect(markup).toContain("Patient linkage audit");
    expect(markup).not.toContain("Open Survival with Candidate GBC cohort");
  });

  test("shows reviewed exclusions separately from cohorts still under review", () => {
    installCatalogState({
      coverage: "not_eligible",
      view: "cancers",
      expandedCancer: "GBC",
    });
    const markup = renderToStaticMarkup(
      <RepositoryCatalog
        coverage={{ cancers: [] }}
        datasets={[]}
        candidates={[{
          id: "gbc-excluded",
          label: "Ineligible GBC evidence",
          status: "not_eligible",
          tier: "X",
          access_class: "public",
          disease: { id: "GBC", label: "Gallbladder cancer" },
          source: { repository: "geo", accession: "GSE-X" },
          blockers: [{ code: "not_bulk", detail: "Single-cell data only." }],
          links: [],
          capabilities: {
            survival: { available: false, decision: "disabled", reason: "Not eligible." },
            expression_comparison: { available: false, decision: "disabled", reason: "Not eligible." },
            gsea: { available: false, decision: "disabled", reason: "Not eligible." },
          },
        }]}
        candidatesStatus="ready"
        onOpenModule={() => {}}
        onDownload={() => {}}
      />,
    );

    expect(markup).toContain("Reviewed exclusions");
    expect(markup).toContain("Reviewed cohort excluded from TRACE");
    expect(markup).toContain("Not eligible for TRACE");
    expect(markup).not.toContain("not yet a TRACE release");
  });
});
