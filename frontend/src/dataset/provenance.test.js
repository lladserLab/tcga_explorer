import { describe, expect, test } from "vitest";

import {
  filterSources,
  groupSources,
  resolveSourceProviders,
  sourceProviderKey,
  sourceStatusLabel,
  summarizeSources,
} from "./provenance";

const SOURCES = [
  {
    id: "external:geo-brca-scanb-gse96058-2018",
    label: "SCAN-B breast cancer cohort",
    status: "ready",
    metadata: { dataset_id: "geo-brca-scanb-gse96058-2018", license_id: "CC-BY-4.0" },
  },
  {
    id: "external:cbioportal-skcm-gide-2019",
    label: "Melanoma immunotherapy cohort",
    status: "ready_cached",
    metadata: { dataset_id: "cbioportal-skcm-gide-2019", license_id: "ODbL-1.0" },
  },
  {
    id: "tcga_cdr",
    label: "TCGA Clinical Data Resource",
    status: "ready",
    metadata: {},
  },
  {
    id: "external:future-study",
    label: "Future validation cohort",
    status: "missing",
    metadata: { dataset_id: "future-study" },
  },
];

describe("dataset provenance contract", () => {
  test("uses catalog providers before the documented legacy ID fallback", () => {
    const resolved = resolveSourceProviders(SOURCES, [
      { id: "geo-brca-scanb-gse96058-2018", source_provider: "geo" },
      { id: "cbioportal-skcm-gide-2019", source_provider: "cbioportal" },
      { id: "future-study", source_provider: "zenodo" },
    ]);

    expect(sourceProviderKey(resolved[0])).toBe("geo");
    expect(sourceProviderKey(resolved[1])).toBe("cbioportal");
    expect(sourceProviderKey(resolved[2])).toBe("tcga");
    expect(sourceProviderKey(resolved[3])).toBe("zenodo");
  });

  test("groups technical import adapters under their scientific source systems", () => {
    expect(sourceProviderKey({ source_provider: "cbioportal_datahub" })).toBe("cbioportal");
    expect(sourceProviderKey({ source_provider: "cbioportal_gdc_api" })).toBe("cbioportal");
    expect(sourceProviderKey({ source_provider: "europe_pmc_geo_supplement" })).toBe("pmc");
    expect(sourceProviderKey({ source_provider: "PMC public article supplements" })).toBe("pmc");
    expect(sourceProviderKey({ source_provider: "GEO expression and PMC public article supplement" })).toBe("pmc");
    expect(sourceProviderKey({ source_provider: "ICGC release28" })).toBe("icgc");
    expect(sourceProviderKey({ id: "derived_sample_metadata" })).toBe("tcga");
    expect(sourceStatusLabel("configured_no_survival")).toBe(
      "Expression available; survival unavailable",
    );
  });

  test("summarizes readiness and groups every source exactly once", () => {
    const summary = summarizeSources(SOURCES);
    const flattened = summary.groups.flatMap((group) => group.items.map((source) => source.id));

    expect(summary).toMatchObject({ total: 4, ready: 3, attention: 1, providerCount: 4 });
    expect(summary.groups[0].key).toBe("tcga");
    expect(new Set(flattened)).toEqual(new Set(SOURCES.map((source) => source.id)));
    expect(flattened).toHaveLength(SOURCES.length);
  });

  test("filters by human label, accession, provider, status and licence", () => {
    expect(filterSources(SOURCES, { query: "GSE96058" })).toHaveLength(1);
    expect(filterSources(SOURCES, { query: "melanoma" })[0].id).toContain("gide");
    expect(filterSources(SOURCES, { query: "odbl" })[0].id).toContain("cbioportal");
    expect(filterSources(SOURCES, { provider: "geo" })[0].id).toContain("gse96058");
    expect(filterSources(SOURCES, { status: "attention" })).toEqual([SOURCES[3]]);
  });

  test("keeps source and group ordering stable without mutating inputs", () => {
    const before = JSON.stringify(SOURCES);
    const first = groupSources(SOURCES).map((group) => group.key);
    const second = groupSources(SOURCES).map((group) => group.key);

    expect(first).toEqual(second);
    expect(JSON.stringify(SOURCES)).toBe(before);
  });
});
