import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

// All API calls are intercepted. No public compute or patient data is used.
const endpoints = [{ value: "OS", label: "Overall survival", available: true, patients: 90, events: 30 },
  { value: "DSS", label: "Disease-specific survival", available: true, patients: 85, events: 25 }];
const cohorts = ["TCGA-KIRC", "TCGA-BRCA"].map((id) => ({ id, status: "available", n_patients_paired: 100, n_samples_paired: 115 }));
const datasets = ["Alpha", "Beta"].map((name) => ({
  id: `external-${name}`, name: `${name} kidney cohort`, kind: "external", status: "available", tcga_cohort: "TCGA-KIRC",
  active_release_id: `${name}-release`, source_accession: `GSE-${name}`, patient_count: 100, sample_count: 110,
  gene_count: 20000, available_modules: ["analysis", "compare", "expression", "gsea"], endpoints,
}));
const model = (id, status = "completed") => ({ model: id, status, hazard_ratio: 1.5, hr_conf_low: 1.1,
  hr_conf_high: 1.9, p_value: 0.01, ph_p_value: 0.4, ph_global_p_value: 0.5,
  ...(status !== "completed" ? { reason: "Too few complete cases for requested adjustment" } : {}) });

async function mockApi(page) {
  const state = { requests: [], gate: null, metadataFailure: "", emptyLayers: false, failedAdjustment: false };
  await page.addInitScript(() => Object.defineProperty(navigator, "onLine", { get: () => true, configurable: true }));
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    const send = (payload, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(payload) });
    if (route.request().method() !== "GET") {
      if (!path.endsWith("/analyses/batch")) return send({ detail: "Unmocked write blocked" }, 503);
      const request = route.request().postDataJSON();
      state.requests.push(request);
      if (state.gate) await state.gate;
      const results = request.analyses.map((item, index) => ({ index, status: "completed", result: {
        id: `fixture-${index}`, status: "completed", cohort: item.cohort, gene_symbol: item.gene_symbol,
        downloads: { png: "/api/fixture-plot" }, metrics: {
          endpoint: item.endpoint, n_patients: 90, n_events: 30, logrank_p_value: 0.001,
          cutpoint_details: { method: item.cutpoint_method, corrected_p_value: 0.3, corrected_p_status: "completed" },
          cox_models: [model("univariable"), model("user_adjusted", state.failedAdjustment ? "skipped" : "completed"), model("stage_adjusted")],
          continuous_analysis: { status: "completed", n_patients: 90, n_events: 30,
            linear_models: [model("continuous_univariable"), model("continuous_user_adjusted", state.failedAdjustment ? "skipped" : "completed"), model("continuous_stage_adjusted")] },
        },
      } }));
      state.lastResult = { total: results.length, completed: results.length, failed: 0, results };
      return send({ id: "fixture-job", status: "completed", result: state.lastResult });
    }
    if (path.endsWith("/jobs/fixture-job")) return send({ id: "fixture-job", status: "completed", result: state.lastResult });
    if (path.endsWith("fixture-plot")) return route.fulfill({ contentType: "image/svg+xml", body: '<svg xmlns="http://www.w3.org/2000/svg" width="400" height="240"><rect width="400" height="240" fill="#f7fafb"/><path d="M30 30 H100 V80 H220 V150 H370" fill="none" stroke="#087e8b"/></svg>' });
    if (state.metadataFailure && path.endsWith(`/${state.metadataFailure}`)) return send({ detail: "Simulated metadata failure" }, 503);
    if (path.endsWith("/cohorts")) return send(cohorts);
    if (path.endsWith("/datasets")) return send({ datasets });
    if (path.endsWith("/health")) return send({ status: "ok", pipeline_versions: {} });
    if (path.endsWith("/filters")) return send({ stages: ["Stage I", "Stage II"], grades: [], genders: [], races: [], sample_types: [],
      sample_populations: [{ id: "primary_solid", label: "Primary solid tumor", available: true, patient_count: 100, sample_count: 110, allowed_tcga_sample_codes: ["01"] }] });
    if (path.endsWith("/endpoints")) return send({ endpoints });
    if (path.endsWith("/expression-layers")) return send({ expression_layers: state.emptyLayers ? [] : [
      { value: "source", label: "Source log2(TPM + 1)", is_default: true },
      { value: "paired", label: "Paired change" },
    ] });
    if (path.endsWith("/expression-scales")) return send([]);
    if (path.endsWith("/genes")) return send({ genes: [] });
    return send({});
  });
  return state;
}

const step = (page, name) => page.getByRole("button", { name: `${name} workflow step`, exact: true }).click();
async function chooseCohort(page, name = "KIRC") {
  await step(page, "Dataset");
  await page.locator(".cohort-trigger").first().click();
  await page.getByRole("textbox", { name: "Search cancer cohorts" }).fill(name);
  await page.getByRole("option", { name: new RegExp(name) }).click();
}
async function genes(page, value = "CA9") {
  await step(page, "Markers");
  const clear = page.getByRole("button", { name: "Clear all", exact: true });
  if (await clear.isVisible()) await clear.click();
  await page.getByRole("textbox", { name: "Genes to compare", exact: true }).fill(`${value},`);
}
async function configure(page) {
  await page.goto("/?view=compare");
  await chooseCohort(page);
  await genes(page);
  await step(page, "Review & run");
  await expect(page.getByRole("button", { name: "Run selected", exact: true })).toBeEnabled();
}
async function run(page) {
  await step(page, "Review & run");
  await page.getByRole("button", { name: "Run selected", exact: true }).click();
  await expect(page.locator(".compare-run-summary")).toBeVisible();
}

for (const width of [320, 390, 1280]) {
  test(`Compare keeps accessible controls and submitted results at ${width}px`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 900 });
    await mockApi(page);
    await configure(page);
    await expect(page.locator("#compare-step-panel-run .plot-editor-disclosure")).not.toHaveAttribute("open", "");
    await step(page, "Methods");
    const panel = page.locator("#compare-step-panel-methods");
    await expect(panel.getByLabel("Percentile threshold", { exact: true })).toHaveCount(0);
    await panel.getByRole("button", { name: /Maxstat/ }).click();
    await expect(panel.getByRole("button", { name: /Maxstat/ })).toHaveAttribute("aria-pressed", "true");
    await panel.getByRole("button", { name: /^Percentile/ }).click();
    await panel.getByLabel("Percentile threshold", { exact: true }).fill("65");
    expect((await new AxeBuilder({ page }).include("#compare-step-panel-methods").analyze()).violations).toEqual([]);
    await run(page);
    const cell = page.locator(".compare-plot-cell").filter({ hasText: "Maxstat corrected p" });
    await expect(cell).toContainText("0.300");
    await expect(cell).toContainText("Bonferroni");
    await expect(page.locator(".compare-run-summary")).toContainText("4 valid grouped tests");
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
    const download = page.waitForEvent("download");
    await page.getByRole("button", { name: "Download comparison summary CSV" }).click();
    expect((await download).suggestedFilename()).toBe("trace-compare-summary.csv");
    await page.screenshot({ path: testInfo.outputPath(`compare-${width}.png`), fullPage: true });
  });
}

test("endpoint and gene changes never relabel old results", async ({ page }) => {
  const state = await mockApi(page);
  await configure(page);
  await run(page);
  await step(page, "Dataset");
  await page.getByRole("button", { name: /Disease-specific survival/ }).click();
  await expect(page.locator(".method-note.caution")).toContainText("Settings changed.");
  await genes(page, "TP53");
  await page.getByRole("tab", { name: "Cutpoint comparison", exact: true }).click();
  await expect(page.locator(".compare-matrix-table")).toContainText("CA9");
  await page.getByRole("tab", { name: "Cutpoint comparison", exact: true }).click();
  await expect(page.locator(".compare-matrix-table")).not.toContainText("TP53");
  await expect(page.locator(".compare-continuous-reference")).toContainText("CA9");
  await expect(page.locator(".compare-run-summary")).toContainText("OS");
  expect(state.requests).toHaveLength(1);
  await run(page);
  await expect(page.locator(".compare-run-summary")).toContainText("DSS");
  await page.getByRole("tab", { name: "Cutpoint comparison", exact: true }).click();
  await expect(page.locator(".compare-matrix-table")).toContainText("TP53");
  await expect(page.locator(".method-note.caution")).toHaveCount(0);
});

test("an old response cannot repopulate results after a cohort round trip", async ({ page }) => {
  const state = await mockApi(page);
  await configure(page);
  let release;
  state.gate = new Promise((resolve) => { release = resolve; });
  await page.getByRole("button", { name: "Run selected", exact: true }).click();
  await expect.poll(() => state.requests.length).toBe(1);
  await chooseCohort(page, "BRCA");
  await chooseCohort(page, "KIRC");
  release();
  await expect(page.getByRole("button", { name: "Open result", exact: true })).toBeVisible();
  await expect(page.getByText("Computing comparison matrix", { exact: true })).toHaveCount(0);
  await step(page, "Review & run");
  await expect(page.getByRole("button", { name: "Run selected", exact: true })).toBeEnabled();
  // Start another batch after the old one settles; only its responses may render.
  state.gate = null;
  await expect(page.locator(".compare-run-summary")).toHaveCount(0);
  await run(page);
  expect(state.requests).toHaveLength(2);
});

for (const resource of ["endpoints", "filters", "expression-layers"]) {
  test(`Compare blocks failed ${resource} metadata and supports retry`, async ({ page }) => {
    const state = await mockApi(page);
    state.metadataFailure = resource;
    await page.goto("/?view=compare");
    await chooseCohort(page);
    if (resource === "expression-layers") {
      await page.getByRole("button", { name: "Change analysis source" }).click();
      await page.getByRole("radio", { name: /Alpha kidney/ }).click();
    }
    await genes(page);
    await step(page, "Review & run");
    await expect(page.getByRole("button", { name: "Run selected", exact: true })).toBeDisabled();
    await expect(page.locator(".survival-metadata-status")).toContainText("Cohort details could not be loaded");
    state.metadataFailure = "";
    await page.getByRole("button", { name: "Retry cohort details" }).click();
    await expect(page.getByRole("button", { name: "Run selected", exact: true })).toBeEnabled();
    expect(state.requests).toHaveLength(0);
  });
}

test("empty external expression layers block both batch buttons", async ({ page }) => {
  const state = await mockApi(page);
  state.emptyLayers = true;
  await configure(page);
  await step(page, "Dataset");
  await page.getByRole("button", { name: "Change analysis source" }).click();
  await page.getByRole("radio", { name: /Alpha kidney/ }).click();
  await step(page, "Review & run");
  await expect(page.getByRole("button", { name: "Run selected", exact: true })).toBeDisabled();
  await expect(page.getByRole("button", { name: "Run all 5", exact: true })).toBeDisabled();
  await expect(page.locator(".design-ledger")).toContainText("Choose an available expression layer");
  expect(state.requests).toHaveLength(0);
});

test("a failed requested model is not replaced with a stage-adjusted estimate", async ({ page }) => {
  const state = await mockApi(page);
  state.failedAdjustment = true;
  await configure(page);
  await step(page, "Clinical");
  await page.getByRole("checkbox", { name: /^Stage/ }).check();
  await run(page);
  const continuous = page.locator(".compare-continuous-reference");
  await expect(continuous).toContainText("Not estimable");
  await expect(continuous).toContainText("Too few complete cases for requested adjustment");
  await continuous.locator("summary").filter({ hasText: "Other fitted models" }).click();
  await expect(continuous).toContainText("Stage: 1.50");
  await expect(page.locator(".robustness-summary")).toContainText("Higher hazard");
  await expect(page.locator(".robustness-summary")).not.toContainText("Harmful");
});

test("recovery after reload preserves original labels and marks unknown request identity", async ({ page }) => {
  await mockApi(page);
  await configure(page);
  await run(page);
  // Simulate a tab that closed after submission, before consuming completion.
  await page.evaluate(() => localStorage.setItem("trace-explorer-active-jobs-v1", JSON.stringify([{
    event_id: "interrupted-comparison", job_id: "fixture-job", job_kind: "batch", job_status: "queued", source_view: "compare",
    label: "CA9", design_summary: "TCGA-KIRC · OS",
    recovery_context: [{ gene: "CA9", method: "median", cohort: "TCGA-KIRC", endpoint: "OS" },
      { gene: "CA9", method: "upper_quartile", cohort: "TCGA-KIRC", endpoint: "OS" }],
    recorded_at: new Date().toISOString(),
  }])));
  await page.reload();
  await page.getByRole("button", { name: "Open result", exact: true }).click();
  await expect(page.locator(".method-note.caution")).toContainText("Recovered result.");
  await expect(page.locator(".compare-run-summary")).toContainText("TCGA-KIRC · OS");
  await page.getByRole("tab", { name: "Cutpoint comparison", exact: true }).click();
  await expect(page.locator(".compare-matrix-table")).toContainText("CA9");
  const draft = await page.evaluate(() => localStorage.getItem("trace-explorer-workspace-draft-v1"));
  expect(draft || "").not.toContain("fingerprint");
});

test("changing an exported forest setting requires a rerun", async ({ page }) => {
  const state = await mockApi(page);
  await configure(page);
  await run(page);
  await page.locator("#compare-step-panel-run summary").filter({ hasText: "Edit plots and exports" }).click();
  await page.getByRole("button", { name: "Cox models", exact: true }).click();
  await page.locator(".cox-model-display-control").getByRole("button", { name: "Choose rows" }).click();
  await expect(page.locator(".method-note.caution")).toContainText("Settings changed.");
  expect(state.requests).toHaveLength(1);
});
