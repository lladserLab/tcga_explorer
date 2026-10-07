import {
  datasetSupportsModule,
  moduleCapabilityName,
} from "../datasetCapabilities";

export const REPOSITORY_PAGE_SIZE = 20;

const ENDPOINT_ORDER = ["OS", "DSS", "PFI", "DFI", "DFS", "PFS", "RFS"];

const SOURCE_LABELS = {
  biostudies_arrayexpress: "BioStudies / ArrayExpress",
  cbioportal_api: "cBioPortal",
  cbioportal_datahub: "cBioPortal DataHub",
  cbioportal_gdc_api: "cBioPortal / GDC",
  cgga_release: "CGGA",
  europe_pmc_geo_supplement: "Europe PMC / GEO",
  europe_pmc_supplement: "Europe PMC",
  figshare_publication: "Figshare",
  gdc_api: "GDC",
  geo: "GEO",
  icgc_release28: "ICGC",
  pdc_pancancer: "PDC",
  zenodo_publication: "Zenodo",
};

export function normalizeCatalogText(value) {
  return String(value || "")
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "")
    .toLowerCase()
    .trim();
}

export function sourceProviderLabel(value) {
  if (!value) return "Source";
  if (SOURCE_LABELS[value]) return SOURCE_LABELS[value];
  return String(value)
    .split(/[_-]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

export function endpointCode(endpoint) {
  return String(
    endpoint?.standard_code || endpoint?.value || "",
  ).toUpperCase();
}

export function sortedDatasetEndpoints(dataset) {
  return [...(dataset?.endpoints || [])].sort((left, right) => {
    const leftCode = endpointCode(left);
    const rightCode = endpointCode(right);
    const leftIndex = ENDPOINT_ORDER.indexOf(leftCode);
    const rightIndex = ENDPOINT_ORDER.indexOf(rightCode);
    if (leftIndex !== rightIndex) {
      return (leftIndex < 0 ? ENDPOINT_ORDER.length : leftIndex)
        - (rightIndex < 0 ? ENDPOINT_ORDER.length : rightIndex);
    }
    return leftCode.localeCompare(rightCode);
  });
}

export function maxDatasetEvents(dataset) {
  return Math.max(
    0,
    ...sortedDatasetEndpoints(dataset).map(
      (endpoint) => Number(endpoint.event_count || 0),
    ),
  );
}

export function datasetMatchesCatalogFilters(dataset, filters = {}) {
  const query = normalizeCatalogText(filters.query);
  if (query) {
    const endpointText = sortedDatasetEndpoints(dataset)
      .flatMap((endpoint) => [
        endpointCode(endpoint),
        endpoint.label,
        endpoint.time_origin,
        endpoint.event_definition,
      ])
      .join(" ");
    const searchable = normalizeCatalogText([
      dataset.id,
      dataset.name,
      dataset.cancer_code,
      dataset.cancer_name,
      dataset.tcga_cohort,
      dataset.source_accession,
      dataset.source_provider,
      sourceProviderLabel(dataset.source_provider),
      dataset.publication_citation,
      dataset.publication_id,
      dataset.cohort_context,
      dataset.description,
      ...(Object.values(dataset.capabilities || {}).flatMap((capability) => [
        capability?.reason,
      ])),
      endpointText,
    ].join(" "));
    if (!searchable.includes(query)) return false;
  }

  if (
    filters.cancerCode
    && filters.cancerCode !== "all"
    && dataset.cancer_code !== filters.cancerCode
  ) {
    return false;
  }

  if (
    filters.analysis
    && filters.analysis !== "all"
    && !datasetSupportsModule(dataset, filters.analysis)
  ) {
    return false;
  }

  if (
    filters.endpoint
    && filters.endpoint !== "all"
    && !sortedDatasetEndpoints(dataset).some(
      (endpoint) => endpointCode(endpoint) === filters.endpoint,
    )
  ) {
    return false;
  }

  if (
    filters.source
    && filters.source !== "all"
    && dataset.source_provider !== filters.source
  ) {
    return false;
  }

  if (
    filters.access === "downloadable"
    && !dataset.redistribution_allowed
  ) {
    return false;
  }
  if (
    filters.access === "server_only"
    && dataset.redistribution_allowed
  ) {
    return false;
  }

  const minimumEvents = Number(filters.minimumEvents || 0);
  if (
    minimumEvents > 0
    && !sortedDatasetEndpoints(dataset).some(
      (endpoint) => Number(endpoint.event_count || 0) >= minimumEvents,
    )
  ) {
    return false;
  }

  return true;
}

export function filterRepositoryDatasets(datasets, filters = {}) {
  const rows = (datasets || []).filter(
    (dataset) => datasetMatchesCatalogFilters(dataset, filters),
  );
  const sort = filters.sort || "catalog";
  return [...rows].sort((left, right) => {
    if (sort === "patients") {
      return Number(right.patient_count || 0) - Number(left.patient_count || 0)
        || left.name.localeCompare(right.name);
    }
    if (sort === "events") {
      return maxDatasetEvents(right) - maxDatasetEvents(left)
        || left.name.localeCompare(right.name);
    }
    return left.cancer_code.localeCompare(right.cancer_code)
      || left.name.localeCompare(right.name);
  });
}

export function activeRepositoryFilterCount(filters = {}) {
  return [
    filters.cancerCode && filters.cancerCode !== "all",
    filters.analysis && filters.analysis !== "all",
    filters.endpoint && filters.endpoint !== "all",
    filters.source && filters.source !== "all",
    filters.access && filters.access !== "all",
    Number(filters.minimumEvents || 0) > 0,
  ].filter(Boolean).length;
}

export function candidateMatchesCatalogFilters(candidate, filters = {}) {
  const query = normalizeCatalogText(filters.query);
  const disease = candidate?.disease || {};
  const source = candidate?.source || {};
  if (
    filters.coverage === "not_eligible"
    && candidate?.status !== "not_eligible"
  ) {
    return false;
  }
  if (
    filters.coverage === "under_review"
    && !["under_review", "access_required"].includes(candidate?.status)
  ) {
    return false;
  }
  if (query) {
    const searchable = normalizeCatalogText([
      candidate?.id,
      candidate?.label,
      disease.id,
      disease.label,
      source.repository,
      source.accession,
      candidate?.tier,
      candidate?.access_class,
      ...(candidate?.blockers || []).flatMap((blocker) => [
        typeof blocker === "string" ? blocker : blocker?.code,
        typeof blocker === "string" ? "" : blocker?.detail,
      ]),
      ...Object.values(candidate?.capabilities || {}).flatMap((capability) => [
        capability?.decision,
        capability?.reason,
      ]),
    ].join(" "));
    if (!searchable.includes(query)) return false;
  }

  if (
    filters.cancerCode
    && filters.cancerCode !== "all"
    && disease.id !== filters.cancerCode
  ) {
    return false;
  }

  if (filters.analysis && filters.analysis !== "all") {
    const capability = moduleCapabilityName(filters.analysis);
    const decision = candidate?.capabilities?.[capability]?.decision;
    if (!new Set(["enabled", "pending"]).has(decision)) return false;
  }

  if (
    filters.source
    && filters.source !== "all"
    && source.repository !== filters.source
  ) {
    return false;
  }

  return true;
}

export function filterRepositoryCandidates(candidates, filters = {}) {
  return (candidates || [])
    .filter((candidate) => candidate?.status !== "promoted")
    .filter((candidate) => candidateMatchesCatalogFilters(candidate, filters))
    .sort((left, right) =>
      String(left?.disease?.id || "").localeCompare(String(right?.disease?.id || ""))
      || String(left?.label || "").localeCompare(String(right?.label || "")),
    );
}

export function repositoryCatalogOptions(datasets) {
  const cancers = new Map();
  const endpoints = new Set();
  const sources = new Set();
  (datasets || []).forEach((dataset) => {
    cancers.set(dataset.cancer_code, dataset.cancer_name);
    sources.add(dataset.source_provider);
    sortedDatasetEndpoints(dataset).forEach((endpoint) => {
      const code = endpointCode(endpoint);
      if (code) endpoints.add(code);
    });
  });
  return {
    cancers: [...cancers]
      .map(([value, label]) => ({ value, label }))
      .sort((left, right) => left.value.localeCompare(right.value)),
    endpoints: [...endpoints].sort((left, right) => {
      const leftIndex = ENDPOINT_ORDER.indexOf(left);
      const rightIndex = ENDPOINT_ORDER.indexOf(right);
      return (leftIndex < 0 ? ENDPOINT_ORDER.length : leftIndex)
        - (rightIndex < 0 ? ENDPOINT_ORDER.length : rightIndex)
        || left.localeCompare(right);
    }),
    sources: [...sources]
      .filter(Boolean)
      .map((value) => ({ value, label: sourceProviderLabel(value) }))
      .sort((left, right) => left.label.localeCompare(right.label)),
  };
}

export function repositoryPage(rows, page, pageSize = REPOSITORY_PAGE_SIZE) {
  const pageCount = Math.max(1, Math.ceil((rows || []).length / pageSize));
  const selectedPage = Math.min(Math.max(1, Number(page || 1)), pageCount);
  const start = (selectedPage - 1) * pageSize;
  return {
    page: selectedPage,
    pageCount,
    start,
    end: Math.min(start + pageSize, (rows || []).length),
    rows: (rows || []).slice(start, start + pageSize),
  };
}
