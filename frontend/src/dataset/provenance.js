export const READY_SOURCE_STATUSES = new Set([
  "ready",
  "ready_cached",
  "configured_no_survival",
]);

const PROVIDER_METADATA = Object.freeze({
  tcga: Object.freeze({ label: "TCGA reference", shortLabel: "TCGA" }),
  biostudies: Object.freeze({ label: "BioStudies", shortLabel: "BioStudies" }),
  cbioportal: Object.freeze({ label: "cBioPortal", shortLabel: "cBioPortal" }),
  cgga: Object.freeze({ label: "Chinese Glioma Genome Atlas", shortLabel: "CGGA" }),
  dryad: Object.freeze({ label: "Dryad", shortLabel: "Dryad" }),
  figshare: Object.freeze({ label: "Figshare", shortLabel: "Figshare" }),
  gdc: Object.freeze({ label: "Genomic Data Commons", shortLabel: "GDC" }),
  geo: Object.freeze({ label: "Gene Expression Omnibus", shortLabel: "GEO" }),
  icgc: Object.freeze({ label: "International Cancer Genome Consortium", shortLabel: "ICGC" }),
  mendeley: Object.freeze({ label: "Mendeley Data", shortLabel: "Mendeley" }),
  metaprism: Object.freeze({ label: "MetaPRISM", shortLabel: "MetaPRISM" }),
  pdc: Object.freeze({ label: "Proteomic Data Commons", shortLabel: "PDC" }),
  pmc: Object.freeze({ label: "Published supplementary cohorts", shortLabel: "PMC" }),
  zenodo: Object.freeze({ label: "Zenodo", shortLabel: "Zenodo" }),
  other: Object.freeze({ label: "Other sources", shortLabel: "Other" }),
});

const PROVIDER_ALIASES = Object.freeze({
  biostudies_arrayexpress: "biostudies",
  cbioportal_api: "cbioportal",
  cbioportal_datahub: "cbioportal",
  cbioportal_gdc_api: "cbioportal",
  cgga_release: "cgga",
  dryad: "dryad",
  europe_pmc: "pmc",
  europe_pmc_geo_supplement: "pmc",
  europe_pmc_supplement: "pmc",
  figshare_publication: "figshare",
  gdc_api: "gdc",
  geo_expression_and_pmc_public_article_supplement: "pmc",
  icgc_release28: "icgc",
  mendeley_publication: "mendeley",
  metaprism_public: "metaprism",
  pdc_pancancer: "pdc",
  pmc_public_article_supplement: "pmc",
  pmc_public_article_supplements: "pmc",
  zenodo_publication: "zenodo",
});

function normalizeProviderKey(value) {
  const normalized = String(value || "")
    .trim()
    .toLocaleLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");
  return PROVIDER_ALIASES[normalized] || normalized;
}

export function sourceProviderKey(source = {}) {
  const id = String(source.id || "").trim();
  if (id.startsWith("external:")) {
    const idProvider = normalizeProviderKey(
      id.slice("external:".length).split("-", 1)[0],
    );
    if (idProvider && Object.hasOwn(PROVIDER_METADATA, idProvider) && idProvider !== "other") {
      return idProvider;
    }
  }
  const explicitProvider = normalizeProviderKey(
    source.source_provider || source.metadata?.source_provider || "",
  );
  if (explicitProvider) return explicitProvider;
  if (id.startsWith("external:")) {
    return id.slice("external:".length).split("-", 1)[0] || "other";
  }
  if (
    id.startsWith("tcga_")
    || id === "derived_sample_metadata"
    || id.toLowerCase().startsWith("tcga ")
    || id.toLowerCase().startsWith("tcga-")
  ) {
    return "tcga";
  }
  return "other";
}

export function resolveSourceProviders(sources = [], repositoryDatasets = []) {
  const providersByDataset = new Map(
    repositoryDatasets
      .filter((dataset) => dataset?.id && dataset?.source_provider)
      .map((dataset) => [String(dataset.id), String(dataset.source_provider)]),
  );
  return sources.map((source) => {
    if (source.source_provider || source.metadata?.source_provider) return source;
    const datasetId = source.metadata?.dataset_id;
    const sourceProvider = datasetId ? providersByDataset.get(String(datasetId)) : null;
    return sourceProvider
      ? {
          ...source,
          source_provider: sourceProvider,
          source_provider_canonical: normalizeProviderKey(sourceProvider),
        }
      : source;
  });
}

export function sourceProviderMetadata(key) {
  const fallback = String(key || "other").replaceAll("_", " ");
  return PROVIDER_METADATA[key] || {
    label: fallback.replace(/\b\w/g, (letter) => letter.toUpperCase()),
    shortLabel: fallback.toUpperCase(),
  };
}

export function sourceStatusLabel(value) {
  const normalized = String(value || "unknown").trim();
  return {
    ready: "Imported",
    ready_cached: "Cache available",
    configured_no_survival: "Expression available; survival unavailable",
    missing: "Source files unavailable",
    failed: "Import failed",
    unknown: "Status unavailable",
  }[normalized] || normalized.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

export function sourceIsReady(source = {}) {
  return READY_SOURCE_STATUSES.has(source.status);
}

export function sourceDisplayName(source = {}) {
  const known = {
    tcga_cdr: "TCGA Clinical Data Resource",
    derived_sample_metadata: "TCGA sample metadata",
    tcga_rna: "TCGA RNA-seq expression",
  };
  return source.label || known[source.id] || source.id || "Unnamed source";
}

export function sourceTechnicalId(source = {}) {
  return String(source.id || "unknown");
}

export function sourceSearchText(source = {}) {
  const metadata = source.metadata || {};
  return [
    source.id,
    source.label,
    source.kind,
    source.status,
    source.source_provider,
    source.source_accession,
    source.source_url,
    metadata.dataset_id,
    metadata.source_accession,
    metadata.release_id,
    metadata.license_id,
    metadata.description,
    metadata.citation,
    sourceProviderMetadata(sourceProviderKey(source)).label,
    sourceProviderMetadata(sourceProviderKey(source)).shortLabel,
  ]
    .filter(Boolean)
    .join(" ")
    .toLocaleLowerCase();
}

export function groupSources(sources = []) {
  const grouped = new Map();
  sources.forEach((source) => {
    const key = sourceProviderKey(source);
    if (!grouped.has(key)) grouped.set(key, []);
    grouped.get(key).push(source);
  });

  return [...grouped.entries()]
    .map(([key, items]) => {
      const provider = sourceProviderMetadata(key);
      const sortedItems = [...items].sort((left, right) => (
        sourceDisplayName(left).localeCompare(sourceDisplayName(right), undefined, { sensitivity: "base" })
      ));
      return {
        key,
        ...provider,
        items: sortedItems,
        total: sortedItems.length,
        ready: sortedItems.filter(sourceIsReady).length,
      };
    })
    .sort((left, right) => {
      if (left.key === "tcga") return -1;
      if (right.key === "tcga") return 1;
      return left.label.localeCompare(right.label, undefined, { sensitivity: "base" });
    });
}

export function summarizeSources(sources = []) {
  const groups = groupSources(sources);
  const ready = sources.filter(sourceIsReady).length;
  return {
    total: sources.length,
    ready,
    attention: sources.length - ready,
    providerCount: groups.length,
    groups,
  };
}

export function filterSources(
  sources = [],
  { query = "", provider = "all", status = "all" } = {},
) {
  const normalizedQuery = String(query).trim().toLocaleLowerCase();
  return sources.filter((source) => {
    if (provider !== "all" && sourceProviderKey(source) !== provider) return false;
    if (status === "ready" && !sourceIsReady(source)) return false;
    if (status === "attention" && sourceIsReady(source)) return false;
    return !normalizedQuery || sourceSearchText(source).includes(normalizedQuery);
  });
}
