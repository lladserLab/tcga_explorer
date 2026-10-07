import { expect, test } from "@playwright/test";

test("Home discovers videos without fetching MP4s until playback", async ({ page }) => {
  const mediaRequests = [];
  page.on("request", (request) => {
    if (request.url().endsWith(".mp4")) mediaRequests.push(request.url());
  });
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto("/?view=home");
  await expect(page.getByText("New to TRACE?", { exact: true })).toBeVisible();
  await expect(page.getByText("Watch a walkthrough before you start. 7 quick guides", { exact: true })).toBeVisible();
  await expect(page.getByText("Download each result with its data sources, patient selection and analysis settings.", { exact: true })).toHaveCount(0);
  await expect(page.locator("video")).toHaveCount(0);
  expect(mediaRequests).toEqual([]);
  await page.screenshot({ path: "test-results/video-home-desktop.png", fullPage: true });
  await expect(page.locator(".home-video-intro .trace-guide-video")).toHaveCount(0);
  await page.getByRole("button", { name: "Browse video guides", exact: true }).click();
  await expect(page).toHaveURL(/view=examples/);
  await expect(page.locator(".trace-tutorial-row .trace-guide-video")).toHaveCount(7);
  const headings = await page.locator(".trace-tutorial-tab-panel > section > h3").allTextContents();
  expect(headings).toEqual(["Quick guides", "Learning routes"]);
  await expect(page.locator(".trace-tutorial-route-list .trace-guide-video")).toHaveCount(0);
  await page.locator(".trace-tutorial-row button.trace-guide-video").first().click();
  const video = page.locator(".trace-video-dialog video");
  await expect(video).toBeVisible();
  await expect(video).toHaveAttribute("src", /_en\.mp4$/);
  await expect(page.getByLabel("Video language")).toHaveCount(0);
  expect(mediaRequests).toEqual([]);
});

test("Resume expands the saved guide and video Escape preserves its step", async ({ page }) => {
  await page.goto("/?view=examples");
  const row = page.getByRole("heading", { name: "Survival analysis, step by step", exact: true }).locator("xpath=ancestor::li");
  await row.getByRole("button", { name: "Start", exact: true }).click();
  const dock = page.locator("#trace-tutorial-dock");
  await dock.getByRole("button", { name: "Next", exact: true }).click();
  const savedStep = await dock.getAttribute("data-lesson");
  await dock.getByRole("button", { name: "Minimize tutorial", exact: true }).click();
  await dock.getByRole("button", { name: "Close tutorial", exact: true }).click();
  await page.getByRole("button", { name: /^Resume guide/ }).click();
  await expect(dock).toHaveAttribute("data-presentation", "auto");
  await expect(dock).toHaveAttribute("data-lesson", savedStep);
  const trigger = dock.getByRole("button", { name: "Watch video", exact: true });
  await trigger.click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  await expect(dialog.getByRole("button", { name: "Close video", exact: true })).toBeFocused();
  for (let index = 0; index < 5; index += 1) {
    await page.keyboard.press("Tab");
    expect(await dialog.evaluate((element) => element.contains(document.activeElement))).toBe(true);
  }
  await page.keyboard.press("Escape");
  await expect(dialog).toHaveCount(0);
  await expect(dock).toHaveAttribute("data-lesson", savedStep);
  await expect(trigger).toBeFocused();
  await page.setViewportSize({ width: 390, height: 844 });
  await trigger.click();
  await expect(dialog).toBeVisible();
  const bounds = await dialog.boundingBox();
  expect(bounds.width).toBeLessThanOrEqual(390);
  await page.screenshot({ path: "test-results/guide-video-dialog-mobile.png" });
  await dialog.getByRole("button", { name: "Close video", exact: true }).click();
  await expect(dialog).toHaveCount(0);
  await expect(dock).toHaveAttribute("data-lesson", savedStep);
});

const health = {
  status: "ok",
  cohorts: 1,
  external_repository: {
    datasets: 2,
    represented_cancer_types: 2,
    patient_records_across_active_releases: 40,
    rna_samples_across_active_releases: 45,
  },
};
const cohorts = [{
  id: "TCGA-BRCA",
  disease_type: "Breast Invasive Carcinoma",
  primary_site: "Breast",
  n_patients_paired: 100,
  n_samples_paired: 110,
  n_genes: 20000,
}];

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    // Network-isolated test containers still serve Vite and mocked APIs.
    Object.defineProperty(navigator, "onLine", { get: () => true, configurable: true });
  });
  await page.route("**/api/**", (route) => {
    const path = new URL(route.request().url()).pathname;
    const payloads = {
      "/api/v1/health": health,
      "/api/v1/cohorts": cohorts,
      "/api/v1/expression-scales": [],
      "/api/v1/datasets": { datasets: [] },
      "/api/v1/cancer-types": { cancers: [] },
    };
    return route.fulfill({
      status: Object.hasOwn(payloads, path) ? 200 : 503,
      contentType: "application/json",
      body: JSON.stringify(payloads[path] || { detail: "API isolated for Home tests." }),
    });
  });
});

for (const reducedMotion of ["no-preference", "reduce"]) {
  test(`question-led entry works with keyboard (${reducedMotion})`, async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.emulateMedia({ reducedMotion });
    await page.goto("/?view=home");
    await expect(page.getByRole("heading", { name: "What do you want to investigate?" })).toBeVisible();
    await expect(page.locator(".home-kicker")).toHaveText("Transcriptomic Research Across Cohorts and Endpoints");
    await expect(page.getByRole("button", { name: /Analyze survival/ })).toHaveCount(0);
    const start = page.getByRole("button", { name: /^Survival How does expression/ });
    await start.focus();
    await page.keyboard.press("Enter");
    await expect(start).toHaveAttribute("aria-pressed", "true");
    await expect(page.getByRole("heading", { name: "How do you want to study survival?" })).toBeVisible();
    await expect(page).toHaveURL(/view=home(?:&|$)/);
    await page.getByRole("button", { name: "Analyze survival", exact: true }).click();
    await expect(page).toHaveURL(/view=analysis(?:&|$)/);
    await expect(page.locator("#analysis-step-panel-data")).toBeVisible();
    await expect(page.locator("#trace-tutorial-dock")).toHaveCount(0);
  });
}

test("molecular and cross-study questions reveal only relevant routes", async ({ page }) => {
  await page.goto("/?view=home");
  await page.getByRole("button", { name: /^Molecular differences/ }).click();
  await expect(page.getByRole("button", { name: "Compare gene expression", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Compare pathways", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Analyze survival", exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: /^Across studies/ }).click();
  await expect(page.getByRole("button", { name: "Analyze across cancer types", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Find an external cohort", exact: true })).toBeVisible();
});

test("homepage trace keeps its proportions in the compact banner", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto("/?view=home");
  const trace = page.locator(".home-hero-trace");
  await expect(trace).toBeVisible();
  const bounds = await trace.boundingBox();
  expect(bounds.height).toBeGreaterThan(100);
  expect((await page.locator(".home-hero").boundingBox()).height).toBeLessThanOrEqual(200);
  expect(bounds.width / bounds.height).toBeCloseTo(2, 1);
  await expect(trace.locator("svg")).toHaveAttribute("preserveAspectRatio", "xMidYMid meet");
  const copy = await page.locator(".home-hero-copy").boundingBox();
  expect(bounds.x).toBeGreaterThanOrEqual(copy.x + copy.width);
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(trace).toBeHidden();
});

test("pan-cancer setup keeps technical details optional and supports genes or signatures", async ({ page }) => {
  await page.goto("/?view=pancancer");
  await expect(page.getByRole("heading", { name: "Survival across cancers and studies", exact: true })).toBeVisible();
  const mode = page.getByRole("group", { name: "Pan-cancer analysis mode" });
  await expect(mode.getByRole("radio", { name: /^Across TCGA cancer types/ })).toBeChecked();
  const detail = page.locator(".hierarchical-pc-synthesis-help");
  await expect(detail).not.toHaveAttribute("open");
  await expect(page.locator(".gene-clipboard-hint")).toHaveCount(0);
  const genes = page.getByRole("textbox", { name: "Gene or signature genes", exact: true });
  await genes.fill("TP53,");
  await expect(page.getByRole("button", { name: "Run pan-cancer scan", exact: true })).toBeEnabled();
  await genes.fill("KRAS,");
  await expect(page.getByRole("group", { name: "Pan-cancer score method" })).toBeVisible();
  await page.getByRole("group", { name: "Pan-cancer score method" }).getByRole("button", { name: "Mean", exact: true }).click();
  await expect(page.getByRole("button", { name: "Run pan-cancer scan", exact: true })).toBeEnabled();
  await detail.getByText("How results are combined", { exact: true }).click();
  await expect(detail.getByText(/cross-study per-IQR effects use different increments/)).toBeVisible();
  const advanced = page.locator(".pancancer-advanced");
  await advanced.getByText("Advanced settings", { exact: true }).click();
  await expect(advanced.getByRole("heading", { name: "Which cancers enter the scan?" })).toBeVisible();
  await expect(advanced.getByLabel(/^Minimum patients per cancer/)).toBeVisible();
  await expect(advanced.getByLabel(/^Minimum outcome events per cancer/)).toBeVisible();
  await expect(advanced.getByLabel(/^Highlight associations at q ≤/)).toBeVisible();
  await expect(advanced.getByText(/This does not remove cancers, change the fitted models/)).toBeVisible();
  await mode.getByRole("radio", { name: /^Across independent studies/ }).check();
  await expect(page.getByRole("heading", { name: "Choose a gene and cohorts", exact: true })).toBeVisible();
  await expect(page.locator(".pancancer-controls")).toHaveCount(0);
});

test("Home opens the existing private upload at the data step, without a POST", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const writes = [];
  page.on("request", (request) => {
    if (request.method() !== "GET") writes.push(request.url());
  });
  // A previous visit to a later Survival step must not hide the upload.
  await page.goto("/?view=analysis");
  await page.getByRole("button", { name: "Marker design workflow step", exact: true }).click();
  await page.getByRole("navigation", { name: "Workspace pages" })
    .getByRole("button", { name: /^Home:/ }).click();
  await page.getByRole("button", { name: "Use your own data", exact: true }).click();
  await expect(page).toHaveURL(/view=analysis(?:&|$)/);
  await expect(page.locator("#analysis-step-panel-data")).toBeVisible();
  await expect(page.getByRole("button", { name: "Upload your own dataset", exact: true })).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByRole("heading", { name: "Add expression and patient metadata" })).toBeVisible();
  await expect(page.getByLabel("Dataset name")).toBeVisible();
  await expect(page.locator("#user-expression-file")).toBeAttached();
  expect(writes).toEqual([]);
  await expect(page.locator("#trace-tutorial-dock")).toHaveCount(0);
});

for (const resource of ["health", "cohorts"]) {
  test(`coverage finishes in an unavailable state after ${resource} fails and recovers on Retry`, async ({ page }) => {
    await page.setViewportSize({ width: 320, height: 800 });
    let fail = true;
    await page.route(`**/api/v1/${resource}`, (route) => route.fulfill({
      status: fail ? 503 : 200,
      contentType: "application/json",
      body: JSON.stringify(fail ? { detail: "Simulated request failure." } : resource === "health" ? health : cohorts),
    }));
    await page.goto("/?view=home");
    const strip = page.locator(".home-data-strip");
    await expect(strip).toHaveAttribute("aria-busy", "false");
    await expect(strip.locator("dd")).toHaveText(Array(4).fill("Unavailable"));
    await expect(page.locator(".service-status-notice")).toBeVisible();
    await page.getByRole("button", { name: /^Across studies/ }).click();
    await expect(page.getByRole("button", { name: /Find an external cohort/ })).not.toContainText("...");
    expect(await strip.locator("dd").evaluateAll((nodes) => nodes.every((node) => {
      const value = node.getBoundingClientRect();
      const cell = node.closest("div").getBoundingClientRect();
      return value.left >= cell.left && value.right <= cell.right;
    }))).toBe(true);
    fail = false;
    await page.getByRole("button", { name: "Retry", exact: true }).click();
    await expect(strip.locator("dd")).toHaveText(["2", "3", "140", "155"]);
    await expect(strip).toHaveAttribute("aria-busy", "false");
    await expect(page.locator(".service-status-notice")).toHaveCount(0);
  });
}

test("pending coverage does not show a partial population or an unavailable state", async ({ page }) => {
  let releaseHealth;
  const gate = new Promise((resolve) => { releaseHealth = resolve; });
  await page.route("**/api/v1/health", async (route) => {
    await gate;
    await route.fulfill({ contentType: "application/json", body: JSON.stringify(health) });
  });
  await page.goto("/?view=home");
  const strip = page.locator(".home-data-strip");
  try {
    await expect(strip).toHaveAttribute("aria-busy", "true");
    await expect(strip.locator("dd")).toHaveText(Array(4).fill("..."));
  } finally {
    releaseHealth();
  }
  await expect(strip.locator("dd")).toHaveText(["2", "3", "140", "155"]);
  await expect(strip).toHaveAttribute("aria-busy", "false");
});

for (const width of [320, 390, 800, 1280, 1440]) {
  test(`Home stays readable at ${width} px`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: width === 390 ? 844 : 900 });
    // Exercise the full-width counts, not only the small fixtures above.
    await page.route("**/api/v1/health", (route) => route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({ ...health, external_repository: {
        datasets: 148,
        represented_cancer_types: 38,
        patient_records_across_active_releases: 17893,
        rna_samples_across_active_releases: 18238,
      } }),
    }));
    await page.route("**/api/v1/cohorts", (route) => route.fulfill({
      contentType: "application/json",
      body: JSON.stringify(Array.from({ length: 33 }, (_, index) => ({
        ...cohorts[0],
        id: `TCGA-TEST-${index}`,
        n_patients_paired: index === 0 ? 341 : 318,
        n_samples_paired: index === 0 ? 369 : 348,
      }))),
    }));
    await page.goto("/?view=home");
    await expect(page.locator(".home-data-strip")).toHaveAttribute("data-state", "ready");
    await expect(page.locator(".home-data-strip dd")).toHaveText(["38", "181", "28,410", "29,743"]);
    await page.evaluate(() => document.fonts.ready);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    for (const name of ["Use your own data"]) {
      expect((await page.getByRole("button", { name, exact: true }).boundingBox()).height).toBeGreaterThanOrEqual(44);
    }
    if (width === 390) {
      const firstChoice = await page.locator(".home-question-choices button").first().boundingBox();
      expect(firstChoice.y + firstChoice.height).toBeLessThanOrEqual(844);
    }
    await expect(page.locator(".home-foundation")).toContainText("Institutions");
    await expect(page.getByRole("heading", { name: "Available public data", exact: true })).toBeVisible();
    const guideBounds = await page.locator(".home-video-intro").boundingBox();
    const workspaceBounds = await page.locator(".home-workspace-index").boundingBox();
    if (width >= 800) {
      expect(guideBounds.x).toBeGreaterThanOrEqual(workspaceBounds.x + workspaceBounds.width);
    } else {
      expect(guideBounds.y).toBeGreaterThanOrEqual(workspaceBounds.y + workspaceBounds.height);
    }
    await page.screenshot({ path: testInfo.outputPath(`home-${width}.png`), fullPage: true });
  });
}

for (const width of [320, 390, 800, 1280]) {
  test(`Expression copy keeps readable width at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/?view=expression");
    const copy = page.locator(".expression-run-row p");
    await expect(copy).toBeVisible();
    await expect.poll(async () => (await copy.boundingBox()).width).toBeGreaterThan(150);
    const summary = page.locator(".page-summary");
    await expect(summary).toBeVisible();
    await expect.poll(async () => (await summary.boundingBox()).width).toBeGreaterThan(200);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
  });
}

for (const width of [320, 800, 1440]) {
  test(`expanded research choices remain readable and can collapse at ${width}px`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 1000 });
    await page.goto("/?view=home");
    for (const [question, count] of [["Survival", 3], ["Molecular differences", 2], ["Across studies", 2]]) {
      const trigger = page.getByRole("button", { name: new RegExp(`^${question} `) });
      await trigger.click();
      await expect(trigger).toHaveAttribute("aria-expanded", "true");
      const panel = page.getByRole("region", { name: "Choose your analysis" });
      await expect(panel).toHaveCount(1);
      await expect(panel.getByRole("button")).toHaveCount(count);
      const panelBounds = await panel.boundingBox();
      const triggerBounds = await trigger.boundingBox();
      expect(panelBounds.y).toBeCloseTo(triggerBounds.y + triggerBounds.height, 0);
      for (const description of await panel.locator("small").all()) {
        expect((await description.boundingBox()).width).toBeGreaterThan(180);
      }
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    }
    await page.screenshot({ path: testInfo.outputPath(`home-expanded-${width}.png`), fullPage: true });
    const trigger = page.getByRole("button", { name: /^Across studies / });
    await trigger.focus();
    await page.keyboard.press("Space");
    await expect(trigger).toHaveAttribute("aria-expanded", "false");
    await expect(trigger).toBeFocused();
    await expect(page.getByRole("region", { name: "Choose your analysis" })).toHaveCount(0);
  });
}
