import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

const DATA_DATES = Object.freeze({
  source_latest_metadata_file: "2026-04-22T00:00:00Z",
  rna_cache_generated_at: "2026-08-05T14:30:00Z",
  database_imported_at: "2026-08-05T15:00:00Z",
});

const EXTERNAL_SYSTEMS = Object.freeze([
  { key: "biostudies", label: "BioStudies", count: 4 },
  { key: "cbioportal", label: "cBioPortal", count: 34 },
  { key: "cgga", label: "Chinese Glioma Genome Atlas", count: 4 },
  { key: "dryad", label: "Dryad", count: 1 },
  { key: "figshare", label: "Figshare", count: 2 },
  { key: "gdc", label: "Genomic Data Commons", count: 7 },
  { key: "geo", label: "Gene Expression Omnibus", count: 60 },
  { key: "icgc", label: "International Cancer Genome Consortium", count: 9 },
  { key: "mendeley", label: "Mendeley Data", count: 1 },
  { key: "metaprism", label: "MetaPRISM", count: 1 },
  { key: "pdc", label: "Proteomic Data Commons", count: 2 },
  { key: "pmc", label: "Published supplementary cohorts", count: 14 },
  { key: "zenodo", label: "Zenodo", count: 3 },
]);

function buildExternalCatalog() {
  let recordIndex = 0;
  return EXTERNAL_SYSTEMS.flatMap((system) => (
    Array.from({ length: system.count }, (_, systemIndex) => {
      recordIndex += 1;
      const isScanB = system.key === "geo" && systemIndex === 0;
      const sequence = String(systemIndex + 1).padStart(3, "0");
      const id = isScanB
        ? "geo-brca-scanb-gse96058-2018"
        : `${system.key}-validation-cohort-${sequence}-2026`;
      return {
        id,
        name: isScanB
          ? "SCAN-B breast cancer cohort"
          : `${system.label} validation cohort ${sequence}`,
        source_provider: system.key,
        source_accession: isScanB ? "GSE96058" : `${system.key.toUpperCase()}-${sequence}`,
        source_url: `https://example.org/${system.key}/${id}`,
        status: "active",
        active_release_id: `${id}-release-v1`,
        patient_count: 80 + recordIndex,
      };
    })
  ));
}

function buildDataSources(externalCatalog) {
  const external = externalCatalog.map((dataset, index) => ({
    id: `external:${dataset.id}`,
    label: dataset.name,
    kind: "external_bulk_rna_seq",
    status: "ready",
    source_url: dataset.source_url,
    source_file_modified_at: "2026-04-20T10:00:00Z",
    imported_at: `2026-08-05T${String(10 + (index % 10)).padStart(2, "0")}:15:00Z`,
    metadata: {
      dataset_id: dataset.id,
      release_id: dataset.active_release_id,
      manifest_sha256: String(index + 1).padStart(64, "0"),
      license_id: dataset.source_provider === "geo" ? "CC-BY-4.0" : "Source terms",
      redistribution_allowed: dataset.source_provider === "geo",
    },
  }));

  return [
    {
      id: "tcga_cdr",
      label: "TCGA Clinical Data Resource",
      kind: "clinical_endpoints",
      status: "ready",
      source_url: "https://gdc.cancer.gov/about-data/publications/pancanatlas",
      imported_at: "2026-08-05T09:00:00Z",
      metadata: { release_id: "TCGA-CDR-2018", license_id: "GDC data use policy" },
    },
    {
      id: "tcga_rna",
      label: "TCGA RNA-seq expression",
      kind: "gene_expression",
      status: "ready_cached",
      source_url: "https://portal.gdc.cancer.gov/",
      imported_at: "2026-08-05T09:30:00Z",
      metadata: { release_id: "GDC-2026-04", license_id: "GDC data use policy" },
    },
    ...external,
  ];
}

const EXTERNAL_CATALOG = buildExternalCatalog();
const DATA_SOURCES = buildDataSources(EXTERNAL_CATALOG);

const DATASET_SUMMARY = Object.freeze({
  totals: {
    cohorts: 33,
    samples: 11_505,
    patients: 10_517,
    usable_os_samples: 10_214,
    events: 4_186,
  },
  data_dates: DATA_DATES,
  data_sources: DATA_SOURCES,
  endpoint_coverage: [],
  distributions: {
    sample_types: [],
    vital_status: [],
    primary_site: [],
    age_bins: [],
  },
  metadata_coverage: [],
  biological_annotations: {},
  cohorts: [],
});

async function mockDatasetApis(page) {
  await page.route("**/api/v1/**", async (route) => {
    const { pathname } = new URL(route.request().url());
    const payloads = {
      "/api/v1/health": {
        app_version: "1.0.0",
        data_dates: DATA_DATES,
        pipeline_versions: {},
      },
      "/api/v1/cohorts": [],
      "/api/v1/expression-scales": [],
      "/api/v1/dataset/summary": DATASET_SUMMARY,
      "/api/v1/data-sources": { sources: DATA_SOURCES },
      "/api/v1/cancer-types": {
        datasets: EXTERNAL_CATALOG.length,
        available_cancer_types: 30,
        evidence_gaps: 3,
        cancers: [],
      },
      "/api/v1/datasets": { datasets: EXTERNAL_CATALOG },
    };

    if (Object.hasOwn(payloads, pathname)) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(payloads[pathname]),
      });
      return;
    }

    await route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({ detail: `Unexpected test request: ${pathname}` }),
    });
  });
}

async function openDatasetPage(page) {
  await mockDatasetApis(page);
  await page.goto("/?view=summary");
  const provenance = page.getByRole("region", {
    name: "Dataset provenance and source status",
  });
  await expect(provenance.getByRole("heading", { name: "Data provenance" })).toBeVisible();
  return provenance;
}

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    window.localStorage.clear();
    window.sessionStorage.clear();
  });
});

test("shows a compact 144-record summary with the source ledger closed", async ({ page }) => {
  const provenance = await openDatasetPage(page);
  const ledger = provenance.locator("details.source-ledger");

  await expect(provenance.getByText("144 of 144 records imported", { exact: true })).toBeVisible();
  await expect(provenance.getByText("2 TCGA references · 142 external records", { exact: true })).toBeVisible();
  await expect(provenance.getByText("144 sources grouped by 14 systems", { exact: true })).toBeVisible();
  await expect(provenance.getByRole("list", { name: "Dataset preparation timeline" })).toBeVisible();
  await expect(provenance.locator('time[datetime="2026-04-22T00:00:00Z"]')).toBeVisible();
  await expect(provenance.locator('time[datetime="2026-08-05T14:30:00Z"]')).toBeVisible();
  await expect(ledger).not.toHaveAttribute("open", "");
  await expect(provenance.getByRole("searchbox", { name: "Search sources" })).not.toBeVisible();
});

test("finds a cohort by name or accession and opens its technical record", async ({ page }) => {
  const provenance = await openDatasetPage(page);
  await provenance.getByText("Browse data sources", { exact: true }).click();

  const search = provenance.getByRole("searchbox", { name: "Search sources" });
  const resultStatus = provenance.getByRole("status");

  await search.fill("SCAN-B breast cancer cohort");
  await expect(resultStatus).toContainText("1 of 144 sources");
  await expect(provenance.getByText("SCAN-B breast cancer cohort", { exact: true })).toBeVisible();

  await search.fill("GSE96058");
  await expect(resultStatus).toContainText("1 of 144 sources");
  const sourceRow = provenance.getByRole("row", { name: /SCAN-B breast cancer cohort/ });
  await expect(sourceRow).toBeVisible();

  const technicalRecord = sourceRow.locator("details.source-record-details");
  await technicalRecord.locator(":scope > summary").click();
  await expect(technicalRecord).toHaveJSProperty("open", true);
  await expect(sourceRow.getByText("Technical source ID", { exact: true })).toBeVisible();
  await expect(sourceRow.getByText("external:geo-brca-scanb-gse96058-2018", { exact: true })).toBeVisible();
  await expect(sourceRow.getByText("geo-brca-scanb-gse96058-2018-release-v1", { exact: true })).toBeVisible();
  await expect(sourceRow.getByRole("link", { name: /Open original source for SCAN-B/ })).toBeVisible();
});

test("the expanded provenance workflow has no automated WCAG A or AA violations", async ({ page }) => {
  const provenance = await openDatasetPage(page);
  await provenance.getByText("Browse data sources", { exact: true }).click();
  await provenance.getByRole("searchbox", { name: "Search sources" }).fill("GSE96058");

  const sourceRow = provenance.getByRole("row", { name: /SCAN-B breast cancer cohort/ });
  await sourceRow.locator("details.source-record-details > summary").click();

  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
    .analyze();

  expect(results.violations).toEqual([]);
});

test("keeps every provenance control reachable without page overflow at 320 px", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 800 });
  const provenance = await openDatasetPage(page);
  await provenance.getByText("Browse data sources", { exact: true }).click();

  const controls = [
    provenance.getByRole("searchbox", { name: "Search sources" }),
    provenance.getByRole("combobox", { name: "Source system" }),
    provenance.getByRole("combobox", { name: "Status" }),
  ];
  for (const control of controls) {
    await control.scrollIntoViewIfNeeded();
    await expect(control).toBeVisible();
    const box = await control.boundingBox();
    expect(box).not.toBeNull();
    expect(box.x).toBeGreaterThanOrEqual(0);
    expect(box.x + box.width).toBeLessThanOrEqual(320);
    expect(box.height).toBeGreaterThanOrEqual(40);
  }

  await controls[0].fill("GSE96058");
  const sourceRecords = provenance.getByRole("region", {
    name: "Gene Expression Omnibus source records",
  });
  await expect(sourceRecords).toBeVisible();
  await expect(sourceRecords.getByText("SCAN-B breast cancer cohort", { exact: true })).toBeVisible();
  await sourceRecords.getByText("Technical record", { exact: true }).click();

  expect(await sourceRecords.evaluate(
    (element) => element.scrollWidth <= element.clientWidth + 1,
  )).toBe(true);
  expect(await page.evaluate(
    () => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1,
  )).toBe(true);
});
