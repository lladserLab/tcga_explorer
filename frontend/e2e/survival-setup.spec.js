import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

// Browser-only fixtures: every API request is intercepted. No public compute,
// patient upload or result artifact is used by these interaction tests.
const cohorts = ["TCGA-KIRC", "TCGA-BRCA"].map((id) => ({
  id, status: "available", n_patients_paired: 100, n_samples_paired: 115, n_primary_tumor: 110,
}));
const endpoints = [{ value: "OS", label: "Overall survival", available: true, patients: 90, events: 30 },
  { value: "DSS", label: "Disease-specific survival", available: true, patients: 85, events: 25 }];
const filters = {
  age_min: 35, age_max: 85, stages: ["Stage I", "Stage II"], grades: [], genders: [], races: [], sample_types: [],
  sample_populations: [{ id: "primary_solid", label: "Primary solid tumor", available: true,
    patient_count: 100, sample_count: 110, allowed_tcga_sample_codes: ["01"] }],
};
const datasets = ["Alpha", "Beta"].map((name) => ({
  id: `external-${name}`, name: `${name} kidney cohort`, kind: "external", status: "available", tcga_cohort: "TCGA-KIRC",
  active_release_id: `${name}-release`, release_version: `${name}-long-technical-release-id`,
  source_accession: `GSE-${name}`, patient_count: 100, sample_count: 110, gene_count: 20000,
  available_modules: ["analysis", "compare", "expression", "gsea"], endpoints,
}));

async function mockApi(page) {
  const state = { metadataFailure: "", requests: [], paths: [], analysisGate: null, endpointGate: null, delayedCohort: "", emptyEndpoints: false, emptyLayers: false };
  await page.addInitScript(() => Object.defineProperty(navigator, "onLine", { get: () => true, configurable: true }));
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    const send = (payload, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(payload) });
    if (route.request().method() !== "GET") {
      if (!/\/analyses(?:\/(combined|signature-panel))?$/.test(path)) return send({ detail: "Unmocked write blocked" }, 503);
      const request = route.request().postDataJSON();
      state.requests.push(request);
      state.paths.push(path);
      if (state.analysisGate) await state.analysisGate;
      return send({ id: "local-test-result", status: "completed", result: {
        id: "local-test-result", status: "completed", cohort: request.cohort,
        gene_symbol: request.gene_symbol || "Test signatures", cutpoint_method: request.cutpoint_method,
        metrics: { endpoint: request.endpoint, endpoint_label: endpoints.find((item) => item.value === request.endpoint)?.label,
          n_patients: 90, n_events: 30, cox_models: [], warnings: [], ...state.resultMetrics }, downloads: {}, diagnostics: state.resultDiagnostics || {},
      } });
    }
    if (state.metadataFailure && path.endsWith(`/${state.metadataFailure}`)) return send({ detail: "Simulated metadata failure" }, 503);
    if (path.endsWith("/endpoints") && state.endpointGate && path.includes(state.delayedCohort)) await state.endpointGate;
    if (path.endsWith("/cohorts")) return send(cohorts);
    if (path.endsWith("/datasets")) return send({ datasets });
    if (path.endsWith("/health")) return send({ status: "ok", pipeline_versions: {} });
    if (path.endsWith("/filters")) return send(state.filterOptions || filters);
    if (path.endsWith("/endpoints")) return send({ endpoints: state.emptyEndpoints ? [] : endpoints });
    if (path.endsWith("/expression-layers")) return send({ expression_layers: state.emptyLayers ? [] : state.expressionLayers || [{ value: "log2_tpm", label: "log2(TPM + 1)", is_default: true }] });
    if (path.endsWith("/expression-scales")) return send([]);
    if (path.endsWith("/genes")) return send({ genes: [] });
    return send({});
  });
  return state;
}

async function step(page, name) {
  await page.getByRole("button", { name: `${name} workflow step`, exact: true }).click();
}
async function chooseCohort(page, name = "KIRC") {
  await step(page, "Data");
  await page.locator(".cohort-trigger").first().click();
  await page.getByRole("textbox", { name: "Search cancer cohorts" }).fill(name);
  await page.getByRole("option", { name: new RegExp(name) }).click();
}
async function enterGene(page, gene = "CA9") {
  await step(page, "Marker design");
  const clear = page.getByRole("button", { name: "Clear all", exact: true });
  if (await clear.isVisible()) await clear.click();
  await page.getByRole("textbox", { name: "Gene symbols", exact: true }).fill(`${gene},`);
}
async function configure(page) {
  await page.goto("/?view=analysis");
  await chooseCohort(page);
  await expect(page.locator(".survival-metadata-status")).toHaveCount(0);
  await enterGene(page);
  await step(page, "Review & run");
}

for (const width of [320, 390, 1280]) {
  test(`expression layer explains paired change and updates outcome counts at ${width}px`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 900 });
    const state = await mockApi(page);
    state.expressionLayers = [
      { value: "source", label: "Source log2(TPM + 1)", is_default: true, transform: "identity",
        coverage: { patient_count: 135, sample_count: 201, observation_unit: "rna_profile",
          endpoints: { OS: { patients: 135, events: 104, available: true } } } },
      { value: "paired", label: "Paired Δ: tumor − adjacent log2(TPM + 1)", transform: "paired_difference", source_unit: "log2(TPM + 1)",
        coverage: { patient_count: 66, sample_count: 66, observation_unit: "paired_contrast",
          endpoints: { OS: { patients: 66, events: 40, available: true } } } },
    ];
    await page.goto("/?view=analysis");
    await chooseCohort(page);
    await page.getByRole("button", { name: "Change analysis source" }).click();
    await page.getByRole("radio", { name: /Alpha kidney/ }).click();
    const selector = page.locator(".expression-data-selector");
    await expect(selector).toContainText("135 patients · 201 RNA profiles");
    const paired = selector.getByRole("button", { name: /Paired Δ/ });
    await paired.click();
    await expect(paired).toHaveAttribute("aria-pressed", "true");
    await expect(selector).toContainText("66 patients · 66 paired contrasts");
    await expect(selector).toContainText("Positive values mean higher expression in the tumor");
    await expect(selector).toContainText("not an independent healthy-control cohort");
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true);
    const accessibility = await new AxeBuilder({ page }).include(".expression-data-selector").analyze();
    expect(accessibility.violations).toEqual([]);
    await page.screenshot({ path: testInfo.outputPath(`expression-data-${width}.png`), fullPage: true });
    await step(page, "Outcome");
    await expect(page.locator(".endpoint-grid")).toContainText("66");
    await expect(page.locator(".endpoint-grid")).toContainText("40");
    await expect(page.locator(".endpoint-grid")).not.toContainText("135");
    expect(state.requests).toHaveLength(0);
  });
}

for (const resource of ["endpoints", "filters", "expression-layers"]) {
  test(`a failed ${resource} check blocks Survival and has a specific retry`, async ({ page }) => {
    const state = await mockApi(page);
    state.metadataFailure = resource;
    await page.goto("/?view=analysis");
    await chooseCohort(page);
    if (resource === "expression-layers") {
      await page.getByRole("button", { name: "Change analysis source" }).click();
      await page.getByRole("radio", { name: /Alpha kidney/ }).click();
    }
    await enterGene(page);
    await step(page, "Review & run");
    await expect(page.getByRole("button", { name: "Run analysis", exact: true })).toBeDisabled();
    await expect(page.locator(".survival-metadata-status")).toContainText("Cohort details could not be loaded");
    await expect(page.locator(".error-box")).toHaveCount(0);
    await expect(page.locator(".design-ledger")).toHaveAttribute("data-ready", "false");
    state.metadataFailure = "";
    await page.getByRole("button", { name: "Retry cohort details" }).click();
    await expect(page.getByRole("button", { name: "Run analysis", exact: true })).toBeEnabled();
    await expect(page.locator(".survival-metadata-status")).toHaveCount(0);
    expect(state.requests).toHaveLength(0);
  });
}

test("an empty authoritative endpoint list never invents a runnable OS", async ({ page }) => {
  const state = await mockApi(page);
  state.emptyEndpoints = true;
  await configure(page);
  await expect(page.getByRole("button", { name: "Run analysis", exact: true })).toBeDisabled();
  await expect(page.locator(".design-ledger")).toHaveAttribute("data-ready", "false");
  expect(state.requests).toHaveLength(0);
});

test("a release without an expression layer is not ready to run", async ({ page }) => {
  const state = await mockApi(page);
  state.emptyLayers = true;
  await configure(page);
  await step(page, "Data");
  await page.getByRole("button", { name: "Change analysis source" }).click();
  await page.getByRole("radio", { name: /Alpha kidney/ }).click();
  await expect(page.locator(".survival-metadata-status")).toHaveCount(0);
  await step(page, "Review & run");
  await expect(page.getByRole("button", { name: "Run analysis", exact: true })).toBeDisabled();
  await expect(page.locator(".design-ledger")).toContainText("Choose an available expression layer");
});

test("retry preserves restrictions entered while metadata is unavailable", async ({ page }) => {
  const state = await mockApi(page);
  state.metadataFailure = "endpoints";
  await page.goto("/?view=analysis");
  await chooseCohort(page);
  await step(page, "Patient filters and adjustment");
  await page.getByText("Eligibility filters", { exact: true }).click();
  await page.getByRole("spinbutton", { name: "Min age", exact: true }).fill("50");
  state.metadataFailure = "";
  await page.getByRole("button", { name: "Retry cohort details" }).click();
  await expect(page.locator(".survival-metadata-status")).toHaveCount(0);
  await expect(page.getByRole("spinbutton", { name: "Min age", exact: true })).toHaveValue("50");
  await enterGene(page);
  await step(page, "Review & run");
  await page.getByRole("button", { name: "Run analysis", exact: true }).click();
  await expect.poll(() => state.requests.length).toBe(1);
  expect(state.requests[0].filters.age_min).toBe(50);
});

test("late cohort metadata cannot enable a different, failed source", async ({ page }) => {
  const state = await mockApi(page);
  let release;
  state.endpointGate = new Promise((resolve) => { release = resolve; });
  state.delayedCohort = "TCGA-KIRC";
  await page.goto("/?view=analysis");
  await chooseCohort(page);
  await expect(page.locator(".survival-metadata-status")).toContainText("Loading cohort details");
  await enterGene(page);
  await step(page, "Review & run");
  await expect(page.getByRole("button", { name: "Run analysis", exact: true })).toBeDisabled();
  state.metadataFailure = "endpoints";
  await chooseCohort(page, "BRCA");
  release();
  await step(page, "Review & run");
  await expect(page.locator(".survival-metadata-status")).toContainText("could not be loaded");
  await expect(page.getByRole("button", { name: "Run analysis", exact: true })).toBeDisabled();
});

test("previous results retain their identity after gene, endpoint, adjustment and plot changes", async ({ page }) => {
  const state = await mockApi(page);
  await configure(page);
  await page.getByRole("button", { name: "Run analysis", exact: true }).click();
  await expect(page.locator(".result-header h2")).toHaveText("CA9 · Overall survival");
  await expect(page.locator(".survival-result-stale")).toHaveCount(0);
  expect(state.requests[0].adjustment_covariates).toEqual(["age_at_index"]);
  expect(state.requests[0].cutpoint_method).toBe("median");
  await expect(page.locator('.design-ledger [data-fact="population"]')).toContainText("Primary solid tumor");
  await step(page, "Data");
  await page.getByRole("radiogroup", { name: "Analysis dataset", exact: true }).getByRole("radio").click();
  await expect(page.locator(".result-header h2")).toHaveText("CA9 · Overall survival");
  await enterGene(page, "MKI67");
  await expect(page.locator(".survival-result-stale")).toContainText("earlier configuration");
  await expect(page.locator(".result-header h2")).toHaveText("CA9 · Overall survival");
  await enterGene(page, "CA9");
  await expect(page.locator(".survival-result-stale")).toHaveCount(0);
  await step(page, "Outcome");
  await page.getByRole("button", { name: /Disease-specific survival/ }).click();
  await expect(page.locator(".survival-result-stale")).toBeVisible();
  await page.getByRole("button", { name: /Overall survival/ }).click();
  await expect(page.locator(".survival-result-stale")).toHaveCount(0);
  await step(page, "Patient filters and adjustment");
  await page.getByRole("checkbox", { name: /^Age/ }).uncheck();
  await expect(page.locator(".survival-result-stale")).toBeVisible();
  await page.getByRole("checkbox", { name: /^Age/ }).check();
  await expect(page.locator(".survival-result-stale")).toHaveCount(0);
  await step(page, "Review & run");
  await page.getByText("Edit plots and exports", { exact: true }).click();
  await page.getByRole("button", { name: "Cox models", exact: true }).click();
  await page.getByRole("button", { name: "Choose rows", exact: true }).click();
  await expect(page.locator(".survival-result-stale")).toBeVisible();
  expect(state.requests).toHaveLength(1);
  await page.getByRole("button", { name: "Run analysis", exact: true }).click();
  await expect.poll(() => state.requests.length).toBe(2);
  await expect(page.locator(".survival-result-stale")).toHaveCount(0);
});

for (const mode of ["combined", "signature-panel"]) {
  test(`${mode} keeps submitted signature identity after normalization`, async ({ page }) => {
    const state = await mockApi(page);
    await configure(page);
    await step(page, "Marker design");
    await page.getByRole("button", { name: mode === "combined" ? "Two-signature interaction" : "Signature panel", exact: true }).click();
    // Select the actual gene-entry controls, leaving score and name fields alone.
    const selectors = mode === "combined"
      ? [page.getByRole("textbox", { name: "Signature A genes", exact: true }), page.getByRole("textbox", { name: "Signature B genes", exact: true })]
      : [page.getByRole("textbox", { name: "Genes", exact: true }).nth(0), page.getByRole("textbox", { name: "Genes", exact: true }).nth(1)];
    await selectors[0].fill("ca9,vegfa,");
    await selectors[1].fill("mki67,pcna,");
    await step(page, "Review & run");
    await page.getByRole("button", { name: "Run analysis", exact: true }).click();
    await expect(page.locator(".analysis-result")).toHaveCount(1);
    await expect(page.locator(".survival-result-stale")).toHaveCount(0);
    expect(state.paths[0]).toBe(`/api/v1/analyses/${mode}`);
    expect(state.requests[0].adjustment_covariates).toEqual(["age_at_index"]);
    const signatures = mode === "combined" ? [state.requests[0].signature_a, state.requests[0].signature_b] : state.requests[0].signatures;
    expect(signatures.map((signature) => signature.gene_symbol)).toEqual(["CA9, VEGFA", "MKI67, PCNA"]);
    await step(page, "Marker design");
    const name = mode === "combined" ? page.getByRole("textbox", { name: "Signature A name", exact: true }) : page.getByRole("textbox", { name: /Panel name/ });
    await name.fill("Updated name");
    await expect(page.locator(".survival-result-stale")).toBeVisible();
    expect(state.requests).toHaveLength(1);
  });
}

for (const change of ["gene", "source"]) {
  test(`an in-flight result is not mistaken for a changed ${change}`, async ({ page }) => {
    const state = await mockApi(page);
    let release;
    state.analysisGate = new Promise((resolve) => { release = resolve; });
    await configure(page);
    await page.getByRole("button", { name: "Run analysis", exact: true }).click();
    await expect.poll(() => state.requests.length).toBe(1);
    if (change === "gene") await enterGene(page, "MKI67");
    else await chooseCohort(page, "BRCA");
    release();
    if (change === "gene") {
      await expect(page.locator(".result-header h2")).toHaveText("CA9 · Overall survival");
      await expect(page.locator(".survival-result-stale")).toBeVisible();
    } else {
      await step(page, "Review & run");
      await expect(page.getByRole("button", { name: "Run analysis", exact: true })).toBeEnabled();
      await expect(page.locator(".analysis-result")).toHaveCount(0);
    }
  });
}

for (const width of [320, 390, 1280]) {
  test(`Survival progressively reveals sources and plots at ${width}px`, async ({ page }, testInfo) => {
    const state = await mockApi(page);
    await page.setViewportSize({ width, height: 844 });
    await page.goto("/?view=analysis");
    await chooseCohort(page);
    await expect(page.getByRole("radio", { name: /Alpha kidney/ })).toHaveCount(0);
    await page.getByRole("button", { name: "Change analysis source" }).click();
    await page.getByRole("searchbox", { name: "Find a source" }).fill("Beta");
    await expect(page.getByRole("radio", { name: /Alpha kidney/ })).toHaveCount(0);
    const beta = page.getByRole("radio", { name: /Beta kidney/ });
    await beta.focus();
    await page.keyboard.press("Enter");
    await expect(beta).toHaveAttribute("aria-checked", "true");
    await expect(page.getByRole("button", { name: "Change analysis source" })).toBeFocused();
    await expect(page.getByText("Beta-long-technical-release-id", { exact: true })).not.toBeVisible();
    await page.getByText("Selected source details", { exact: true }).click();
    await expect(page.getByText("Beta-long-technical-release-id", { exact: true })).toBeVisible();
    await expect(page.getByText("Cohort RNA samples", { exact: true }).first()).toBeVisible();
    await page.evaluate(() => { document.activeElement?.blur(); window.scrollTo(0, 0); });
    await page.screenshot({ path: testInfo.outputPath(`survival-data-${width}.png`), fullPage: true });
    await enterGene(page);
    await expect(page.locator("#analysis-step-panel-design")).toContainText("not a combined score");
    await expect(page.locator(".design-ledger-compact")).toBeVisible();
    await step(page, "Outcome");
    const outcomePreview = page.locator(".endpoint-context-preview");
    const countsHelp = outcomePreview.locator(":scope > .field-help");
    await expect(countsHelp).toBeVisible();
    await expect.poll(async () => {
      const panel = await outcomePreview.boundingBox();
      const copy = await countsHelp.boundingBox();
      return copy.width / panel.width;
    }).toBeGreaterThan(0.75);
    await step(page, "Patient filters and adjustment");
    await expect(page.getByRole("checkbox", { name: /^Age/ })).toBeChecked();
    await expect(page.locator("#analysis-step-panel-clinical")).toContainText("Age is selected by default");
    await step(page, "Review & run");
    await expect(page.locator(".design-ledger-compact")).toHaveCount(0);
    await expect(page.getByText("Practical plot preview", { exact: true })).toHaveCount(0);
    await page.getByText("Edit plots and exports", { exact: true }).click();
    await expect(page.getByText("Practical plot preview", { exact: true })).toBeVisible();
    await page.getByText("Edit plots and exports", { exact: true }).click();
    await expect(page.getByText("Practical plot preview", { exact: true })).toHaveCount(0);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
    const axe = await new AxeBuilder({ page }).include(".analysis-workflow-layout").withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze();
    expect(axe.violations).toEqual([]);
    expect(state.requests).toHaveLength(0);
    await page.evaluate(() => { document.activeElement?.blur(); window.scrollTo(0, 0); });
    await page.screenshot({ path: testInfo.outputPath(`survival-review-${width}.png`), fullPage: true });
  });
}


test("cohort selection warns only after metadata confirms no usable adjustment fields", async ({ page }) => {
  const state = await mockApi(page);
  state.filterOptions = { ...filters, age_min: null, age_max: null, stages: [], grades: [], genders: ["Unknown"], races: [] };
  let release;
  state.endpointGate = new Promise((resolve) => { release = resolve; });
  state.delayedCohort = "TCGA-KIRC";
  await page.goto("/?view=analysis");
  await chooseCohort(page);
  await expect(page.locator(".survival-metadata-status")).toBeVisible();
  await expect(page.locator(".cohort-adjustment-notice")).toHaveCount(0);
  release();
  await expect(page.locator(".cohort-adjustment-notice")).toContainText("No usable clinical covariates");
  await expect(page.locator(".cohort-adjustment-notice")).toContainText("add patient-matched covariates");
  await expect(page.getByRole("button", { name: "Continue", exact: true })).toBeEnabled();
  state.filterOptions = filters;
  await chooseCohort(page, "BRCA");
  await expect(page.locator(".survival-metadata-status")).toHaveCount(0);
  await expect(page.locator(".cohort-adjustment-notice")).toHaveCount(0);
});

test("survival result tabs expose one view and retain grouped content and provenance", async ({ page }) => {
  await mockApi(page);
  await configure(page);
  await page.getByRole("button", { name: "Run analysis", exact: true }).click();
  const result = page.locator(".analysis-result");
  await expect(result.getByRole("tab", { name: "Continuous model", exact: true })).toHaveAttribute("aria-selected", "true");
  await expect(result.getByRole("tabpanel")).toHaveCount(1);
  await result.getByRole("tab", { name: "Survival groups", exact: true }).click();
  await expect(result.getByRole("tabpanel")).toContainText("Sensitivity analysis");
  await result.getByRole("tab", { name: "Diagnostics & provenance", exact: true }).click();
  await expect(result.getByRole("tabpanel")).toHaveCount(1);
  const axe = await new AxeBuilder({ page }).include(".result-tabs").withTags(["wcag2a", "wcag2aa"]).analyze();
  expect(axe.violations).toEqual([]);
});


for (const width of [320, 390, 1280]) {
  test(`wide model tables stay inside the result pane at ${width}px`, async ({ page }) => {
    const state = await mockApi(page);
    state.resultDiagnostics = { primary_result_model: "continuous_user_adjusted" };
    state.resultMetrics = { continuous_analysis: { status: "completed", n_patients: 90, n_events: 30,
      linear_models: [{ model: "continuous_univariable", status: "completed", n_patients: 90, n_events: 30,
        hazard_ratio: 1.2, hr_conf_low: 0.9, hr_conf_high: 1.6, p_value: 0.2 },
        { model: "continuous_user_adjusted", status: "completed", n_patients: 78, n_events: 24,
          hazard_ratio: 1.1, hr_conf_low: 0.8, hr_conf_high: 1.5, p_value: 0.4 }] } };
    await page.setViewportSize({ width, height: 1000 });
    await configure(page);
    await page.getByRole("button", { name: "Run analysis", exact: true }).click();
    await expect(page.locator(".result-tab-panel:not([hidden]) .metric-strip .metric").first()).toContainText("78");
    await page.getByText("All Cox models and model checks", { exact: true }).click();
    await expect(page.getByRole("table", { name: "Continuous Cox model estimates", exact: true })).toBeVisible();
    const tableRegion = page.getByRole("region", { name: "Scrollable continuous Cox model results", exact: true });
    expect(await tableRegion.evaluate((node) => node.scrollWidth > node.clientWidth)).toBe(true);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  });
}
