import { describe, expect, it } from "vitest";

import {
  activeRepositoryFilterCount,
  filterRepositoryCandidates,
  filterRepositoryDatasets,
  repositoryCatalogOptions,
  repositoryPage,
  sourceProviderLabel,
  sortedDatasetEndpoints,
} from "./catalog";

const DATASETS = [
  {
    id: "luad-large",
    cancer_code: "LUAD",
    cancer_name: "Lung adenocarcinoma",
    name: "Large lung cohort",
    source_provider: "geo",
    source_accession: "GSE-LARGE",
    patient_count: 300,
    redistribution_allowed: true,
    endpoints: [
      { value: "PFI", event_count: 40 },
      { value: "OS", event_count: 90 },
    ],
    capabilities: {
      survival: { available: true },
      expression_comparison: { available: true },
      gsea: { available: true },
    },
    available_modules: ["analysis", "compare", "expression", "gsea", "multiverse"],
  },
  {
    id: "skcm-trial",
    cancer_code: "SKCM",
    cancer_name: "Skin cutaneous melanoma",
    name: "Checkpoint treatment cohort",
    source_provider: "cbioportal_datahub",
    source_accession: "TRIAL-1",
    patient_count: 120,
    redistribution_allowed: false,
    cohort_context: "Pretreatment biopsies before checkpoint therapy",
    endpoints: [{ value: "OS", event_count: 70 }],
    capabilities: {
      survival: { available: true },
      expression_comparison: { available: true },
      gsea: { available: false, reason: "Insufficient gene coverage." },
    },
    available_modules: ["analysis", "compare", "expression", "multiverse"],
  },
  {
    id: "luad-small",
    cancer_code: "LUAD",
    cancer_name: "Lung adenocarcinoma",
    name: "Small lung cohort",
    source_provider: "gdc_api",
    source_accession: "GDC-SMALL",
    patient_count: 80,
    redistribution_allowed: false,
    endpoints: [{ value: "DSS", event_count: 12 }],
    capabilities: {
      survival: { available: true },
      expression_comparison: { available: true },
      gsea: { available: true },
    },
    available_modules: ["analysis", "compare", "expression", "gsea", "multiverse"],
  },
];

describe("repository catalog decisions", () => {
  it("searches scientific context and applies endpoint and access filters", () => {
    expect(filterRepositoryDatasets(DATASETS, {
      query: "checkpoint",
      endpoint: "OS",
      access: "server_only",
    }).map((dataset) => dataset.id)).toEqual(["skcm-trial"]);
  });

  it("filters by minimum endpoint events and sorts without a hidden score", () => {
    expect(filterRepositoryDatasets(DATASETS, {
      minimumEvents: "50",
      sort: "patients",
    }).map((dataset) => dataset.id)).toEqual([
      "luad-large",
      "skcm-trial",
    ]);
  });

  it("orders familiar survival endpoints and builds compact filter options", () => {
    expect(sortedDatasetEndpoints(DATASETS[0]).map((endpoint) => endpoint.value))
      .toEqual(["OS", "PFI"]);
    expect(repositoryCatalogOptions(DATASETS).endpoints).toEqual([
      "OS",
      "DSS",
      "PFI",
    ]);
    expect(sourceProviderLabel("cbioportal_datahub")).toBe(
      "cBioPortal DataHub",
    );
  });

  it("counts only filters that change the result set", () => {
    expect(activeRepositoryFilterCount({
      cancerCode: "LUAD",
      analysis: "gsea",
      endpoint: "all",
      source: "geo",
      access: "all",
      minimumEvents: "25",
    })).toBe(4);
  });

  it("filters released cohorts by the exact available module", () => {
    expect(filterRepositoryDatasets(DATASETS, { analysis: "gsea" })
      .map((dataset) => dataset.id)).toEqual(["luad-large", "luad-small"]);
  });

  it("keeps under-review candidates separate and filters pending capabilities", () => {
    const candidates = [
      {
        id: "candidate-a",
        label: "GBC discovery cohort",
        status: "under_review",
        disease: { id: "GBC", label: "Gallbladder cancer" },
        source: { repository: "geo", accession: "GSE-A" },
        capabilities: {
          survival: { decision: "disabled", reason: "No endpoint." },
          expression_comparison: { decision: "pending", reason: "Matrix audit pending." },
          gsea: { decision: "pending", reason: "Gene coverage audit pending." },
        },
        blockers: [{ code: "linkage", detail: "Sample linkage audit" }],
      },
    ];

    expect(filterRepositoryCandidates(candidates, { analysis: "gsea" }))
      .toHaveLength(1);
    expect(filterRepositoryCandidates(candidates, { analysis: "analysis" }))
      .toHaveLength(0);
    expect(filterRepositoryCandidates(candidates, { query: "linkage" }))
      .toHaveLength(1);
    expect(filterRepositoryCandidates([
      { ...candidates[0], id: "promoted-a", status: "promoted" },
    ], {})).toHaveLength(0);
    expect(filterRepositoryCandidates([
      ...candidates,
      { ...candidates[0], id: "excluded-a", status: "not_eligible" },
    ], { coverage: "under_review" }).map((row) => row.id)).toEqual([
      "candidate-a",
    ]);
    expect(filterRepositoryCandidates([
      ...candidates,
      { ...candidates[0], id: "excluded-a", status: "not_eligible" },
    ], { coverage: "not_eligible" }).map((row) => row.id)).toEqual([
      "excluded-a",
    ]);
  });

  it("paginates and clamps requested pages", () => {
    const result = repositoryPage(
      Array.from({ length: 41 }, (_, index) => index),
      9,
      20,
    );
    expect(result.page).toBe(3);
    expect(result.pageCount).toBe(3);
    expect(result.rows).toEqual([40]);
  });
});
