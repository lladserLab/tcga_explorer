import { expect, test } from "@playwright/test";

const gbc = {
  id: "fu-gbc-cancer-cell-2026", kind: "external", tcga_cohort: "FU-GBC",
  name: "FU-GBC gallbladder cancer cohort (2026)", cancer_code: "GBC",
  status: "available", active_release_id: "fu-gbc-frozen-release",
  patient_count: 135, sample_count: 201, gene_count: 15926,
  available_modules: ["analysis", "compare", "expression", "gsea", "multiverse"],
  endpoints: [{ value: "OS", label: "Source-reported survival", available: true, patient_count: 135, event_count: 104 }],
};
const molecularOnly = {
  id: "nbl-expression-only", kind: "external", tcga_cohort: "EXT-NBL",
  name: "Neuroblastoma expression cohort", status: "available",
  active_release_id: "nbl-frozen-release", patient_count: 50, gene_count: 20000,
  available_modules: ["expression", "gsea"], endpoints: [],
};

async function mockCatalog(page) {
  const requestedScopes = [];
  requestedScopes.tcgaExternalLookups = [];
  await page.route("**/api/v1/**", async (route) => {
    const { pathname, searchParams } = new URL(route.request().url());
    if (/\/cohorts\/FU-GBC\/(endpoints|filters)/.test(pathname)) {
      requestedScopes.tcgaExternalLookups.push(pathname);
      await route.fulfill({ status: 422, contentType: "application/json", body: JSON.stringify({
        error: { code: "DATASET_REQUIRED", message: "Choose an external dataset first." },
      }) });
      return;
    }
    let payload = {};
    if (pathname.endsWith("/cohorts")) payload = [
      { id: "TCGA-BRCA", disease_type: "Breast cancer", n_patients_paired: 100, status: "available" },
      { id: "FU-GBC", disease_type: "Gallbladder cancer", primary_site: "Gallbladder", n_patients_paired: 135, status: "external_only" },
      { id: "EXT-NBL", disease_type: "Neuroblastoma", n_patients_paired: 50, status: "external_only" },
    ];
    else if (pathname.endsWith("/datasets")) {
      const scope = searchParams.get("cancer_code");
      requestedScopes.push(scope);
      payload = { datasets: scope ? (scope === "GBC" ? [gbc] : []) : [gbc, molecularOnly] };
    }
    else if (pathname.endsWith("/expression-scales")) payload = [];
    else if (pathname.endsWith("/endpoints")) payload = { endpoints: gbc.endpoints };
    else if (pathname.endsWith("/expression-layers")) payload = {
      expression_layers: [{ value: "fu_gbc_log2_tpm", label: "FU-GBC source log2(TPM + 1)" }],
    };
    else if (pathname.endsWith("/filters")) payload = { sample_types: [], stages: [], grades: [], genders: [], races: [] };
    else if (pathname.endsWith("/genes")) payload = { genes: [] };
    else if (pathname.endsWith("/health")) payload = { status: "ok", pipeline_versions: {} };
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(payload) });
  });
  return requestedScopes;
}

for (const width of [320, 390, 1280]) {
  test(`fresh Survival finds and selects gallbladder without visiting the repository (${width}px)`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    const scopes = await mockCatalog(page);
    await page.goto("/?view=analysis");
    await page.locator(".cohort-trigger").first().click();
    const search = page.getByRole("textbox", { name: "Search cancer cohorts" });
    const count = page.locator(".cohort-count");
    await expect(count).toHaveText("2 cancer types available for this analysis");
    for (const query of ["gallbladder", "gallblader", "vesícula", "GBC"]) {
      await search.fill(query);
      await expect(page.getByRole("option", { name: /Gallbladder Cancer/ })).toBeVisible();
      await expect(count).toHaveText("1 cancer type matches your search");
    }
    await search.fill("neuroblastoma");
    await expect(page.getByRole("option", { name: /Neuroblastoma/ })).toHaveCount(0);
    await expect(count).toHaveText("0 cancer types match your search");
    await search.fill("");
    await expect(count).toHaveText("2 cancer types available for this analysis");
    await search.fill("GBC");
    await page.getByRole("option", { name: /Gallbladder Cancer/ }).click();
    await expect(page.getByRole("radio", { name: /FU-GBC gallbladder cancer cohort/ })).toHaveAttribute("aria-checked", "true");
    expect(scopes).toContain(null);
    expect(scopes.tcgaExternalLookups).toEqual([]);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
  });
}

test("Home does not download the external catalogue before an analysis is opened", async ({ page }) => {
  const scopes = await mockCatalog(page);
  await page.goto("/?view=home");
  await expect(page.getByRole("navigation", { name: "Workspace pages" })).toBeVisible();
  expect(scopes).toHaveLength(0);
  await page.getByRole("button", { name: /^Survival:/ }).click();
  await expect.poll(() => scopes.includes(null)).toBe(true);
});
