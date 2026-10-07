import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    window.localStorage.clear();
    window.sessionStorage.clear();
  });
  await page.route("**/api/**", (route) => route.fulfill({
    status: 503,
    contentType: "application/json",
    body: JSON.stringify({ detail: "Scientific API intentionally offline in accessibility E2E." }),
  }));
});

test("the 320 px top navigation keeps the active destination visible without page overflow", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 800 });
  await page.goto("/?view=pancancer");

  const rail = page.getByRole("navigation", { name: "Workspace pages" });
  const destinations = rail.getByRole("button");
  await expect(destinations).toHaveCount(12);
  await expect(rail.getByRole("button", { name: /^Run history:/ })).toHaveCount(0);
  const activeDestination = rail.getByRole("button", { name: /^Pan-cancer:/ });
  await expect(activeDestination).toHaveAttribute("aria-current", "page");
  await expect(activeDestination).toBeVisible();

  await expect.poll(() => activeDestination.evaluate((element) => {
    const item = element.getBoundingClientRect();
    const viewport = element.closest(".top-nav").getBoundingClientRect();
    return item.left >= viewport.left - 1 && item.right <= viewport.right + 1;
  })).toBe(true);

  const navigationFrame = await page.locator(".app-header").evaluate((element) => {
    const box = element.getBoundingClientRect();
    return { top: Math.round(box.top), left: Math.round(box.left), width: Math.round(box.width) };
  });
  expect(navigationFrame).toEqual({ top: 0, left: 0, width: 320 });
  await expect(page.locator(".sidebar, .sidebar-toggle")).toHaveCount(0);

  const selectedTreatment = await activeDestination.evaluate((element) => ({
    background: getComputedStyle(element).backgroundColor,
    trailingLine: getComputedStyle(element, "::after").display,
  }));
  expect(selectedTreatment.background).not.toBe("rgba(0, 0, 0, 0)");
  expect(selectedTreatment.trailingLine).toBe("none");

  await destinations.first().focus();
  for (let index = 0; index < 12; index += 1) {
    if (index > 0) await page.keyboard.press("Tab");
    const focusedDestination = destinations.nth(index);
    await expect(focusedDestination).toBeFocused();
    await expect.poll(() => focusedDestination.evaluate((element) => {
      const item = element.getBoundingClientRect();
      const viewport = element.closest(".top-nav").getBoundingClientRect();
      return item.left >= viewport.left - 1 && item.right <= viewport.right + 1;
    })).toBe(true);
  }

  await expect.poll(() => page.evaluate(
    () => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1,
  )).toBe(true);
});

test("run history remains reachable from Home without a global navigation item", async ({ page }) => {
  await page.goto("/?view=home");

  const rail = page.getByRole("navigation", { name: "Workspace pages" });
  await expect(rail.getByRole("button", { name: /^Run history:/ })).toHaveCount(0);

  await page.getByRole("button", { name: /Review past analyses/ }).click();
  await expect(page).toHaveURL(/(?:\?|&)view=session(?:&|$)/);
  await expect(page.getByRole("heading", { name: "Exploratory run history", level: 1 })).toBeVisible();

  await page.goto("/?view=session");
  await expect(page.getByRole("heading", { name: "Exploratory run history", level: 1 })).toBeVisible();
});

test("home coverage metrics stay on one line at 320 px", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 800 });
  await page.goto("/?view=home");

  const metrics = page.locator(".home-data-strip dd");
  const labels = page.locator(".home-data-strip dt");
  await expect(metrics).toHaveCount(4);
  await expect(labels).toHaveText([
    "Cancer types represented",
    "Public cohort releases",
    "Patient records across releases",
    "RNA profiles across releases",
  ]);
  const layout = await metrics.evaluateAll(async (elements, values) => {
    elements.forEach((element, index) => {
      element.textContent = values[index];
    });
    await new Promise((resolve) => requestAnimationFrame(resolve));
    return elements.map((element) => {
      const range = document.createRange();
      range.selectNodeContents(element);
      const lineTops = [...range.getClientRects()].map((rect) => Math.round(rect.top));
      const cell = element.closest("div").getBoundingClientRect();
      const value = element.getBoundingClientRect();
      return {
        lines: new Set(lineTops).size,
        contained: value.left >= cell.left && value.right <= cell.right,
      };
    });
  }, ["38", "181", "28,410", "29,743"]);

  expect(layout).toEqual([
    { lines: 1, contained: true },
    { lines: 1, contained: true },
    { lines: 1, contained: true },
    { lines: 1, contained: true },
  ]);
  expect(await page.evaluate(
    () => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1,
  )).toBe(true);
  expect(await labels.evaluateAll((elements) => elements.every((element) => {
    const label = element.getBoundingClientRect();
    const cell = element.closest("div").getBoundingClientRect();
    return label.left >= cell.left && label.right <= cell.right;
  }))).toBe(true);
});

test("home coverage does not wait for the detailed dataset summary", async ({ page }) => {
  await page.unroute("**/api/**");
  let releaseSummary;
  const summaryGate = new Promise((resolve) => {
    releaseSummary = resolve;
  });
  const cohorts = [
    { id: "TCGA-A", n_patients_paired: 79, n_samples_paired: 81 },
    { id: "TCGA-B", n_patients_paired: 120, n_samples_paired: 132 },
  ];

  await page.route("**/api/v1/**", async (route) => {
    const { pathname } = new URL(route.request().url());
    if (pathname === "/api/v1/dataset/summary") {
      await summaryGate;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ totals: { cohorts: 99, patients: 999, samples: 999 } }),
      });
      return;
    }
    const payloads = {
      "/api/v1/health": {
        cohorts: 2,
        external_repository: {
          datasets: 7,
          represented_cancer_types: 3,
          patient_records_across_active_releases: 41,
          rna_samples_across_active_releases: 48,
        },
      },
      "/api/v1/cohorts": cohorts,
      "/api/v1/expression-scales": [],
      "/api/v1/data-sources": { sources: [] },
      "/api/v1/cancer-types": { cancers: [], datasets: 0 },
      "/api/v1/datasets": { datasets: [] },
    };
    await route.fulfill({
      status: Object.hasOwn(payloads, pathname) ? 200 : 503,
      contentType: "application/json",
      body: JSON.stringify(payloads[pathname] || { detail: "Unexpected request" }),
    });
  });

  await page.goto("/?view=home");
  const metrics = page.locator(".home-data-strip dd");
  await expect(metrics.nth(0)).toHaveText("3");
  await expect(metrics.nth(1)).toHaveText("9");
  await expect(metrics.nth(2)).toHaveText("240");
  await expect(metrics.nth(3)).toHaveText("261");

  const decorativeBackgrounds = await page.locator(
    ".brand-mark, .top-nav .scientific-icon",
  ).evaluateAll((elements) => elements.map(
    (element) => getComputedStyle(element).backgroundImage,
  ));
  expect(decorativeBackgrounds.every((value) => value === "none")).toBe(true);
  releaseSummary();
});

test("the skip link moves keyboard focus directly to the workspace", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto("/?view=home");

  const skipLink = page.getByRole("link", { name: "Skip to main content" });
  await page.keyboard.press("Tab");
  await expect(skipLink).toBeFocused();
  await expect(skipLink).toBeVisible();
  await page.keyboard.press("Enter");
  await expect(page.locator("#main-content")).toBeFocused();
});

test("the floating guide keeps a newly focused analysis control unobscured", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/?view=analysis");
  await page.locator(".tutorial-quick-start").click();

  const dock = page.locator("#trace-tutorial-dock");
  await expect(dock).toBeVisible();
  const target = page.locator(
    ".analysis-step-panel :is(button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled))",
  ).last();
  await expect(target).toBeVisible();
  await target.evaluate((element) => element.scrollIntoView({ block: "end" }));
  await target.focus();

  await expect.poll(async () => {
    const targetBox = await target.boundingBox();
    const dockBox = await dock.boundingBox();
    if (!targetBox || !dockBox) return false;
    const overlapsHorizontally = targetBox.right > dockBox.x - 12
      && targetBox.x < dockBox.x + dockBox.width + 12;
    return !overlapsHorizontally || targetBox.y + targetBox.height <= dockBox.y - 12;
  }).toBe(true);
  await expect(target).toBeFocused();
});

test("workflow steps are a named keyboard-scrollable region", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 800 });
  await page.goto("/?view=analysis");

  const stepRegion = page.getByRole("region", { name: "Survival analysis setup steps" });
  await expect(stepRegion).toBeVisible();
  expect(await stepRegion.evaluate((element) => element.scrollWidth > element.clientWidth)).toBe(true);
  await stepRegion.focus();
  await expect(stepRegion).toBeFocused();
  await page.keyboard.press("ArrowRight");
  await page.keyboard.press("ArrowRight");
  await expect.poll(() => stepRegion.evaluate((element) => element.scrollLeft)).toBeGreaterThan(0);
});

test("Compare exposes multivariable forest selection on mobile", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/?view=compare&guide=quick-compare&lesson=review-run");

  await expect(page.locator("#compare-step-panel-run")).toBeVisible();
  await page.locator("#compare-step-panel-run summary").filter({ hasText: "Edit plots and exports" }).click();
  await page.getByRole("button", { name: "Cox models", exact: true }).click();

  const modelDisplay = page.locator(".cox-model-display-control");
  await expect(modelDisplay.getByText("Multivariable rows", { exact: true })).toBeVisible();
  await modelDisplay.getByRole("button", { name: "Choose rows" }).click();
  await expect(modelDisplay.getByRole("group", { name: "Rows included in the forest plot" })).toBeVisible();
  await expect(modelDisplay.getByText("Ordinal stage + grade", { exact: true })).toBeVisible();
  await expect(modelDisplay.getByText("Selected clinical covariates", { exact: true })).toBeVisible();
  await expect.poll(() => page.evaluate(
    () => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1,
  )).toBe(true);
});

test("a metadata-only breast cohort exposes its three-level subtype on mobile", async ({ page }) => {
  await page.unroute("**/api/**");
  await page.route("**/api/**", async (route) => {
    const { pathname } = new URL(route.request().url());
    const payloads = {
      "/api/v1/health": { status: "ok" },
      "/api/v1/cohorts": [
        {
          id: "TCGA-BRCA",
          disease_type: "Breast Invasive Carcinoma",
          primary_site: "Breast",
          n_patients_paired: 100,
          n_samples_paired: 100,
          n_genes: 20000,
        },
      ],
      "/api/v1/expression-scales": [],
      "/api/v1/data-sources": { sources: [] },
    };
    await route.fulfill({
      status: Object.hasOwn(payloads, pathname) ? 200 : 503,
      contentType: "application/json",
      body: JSON.stringify(payloads[pathname] || { detail: "Not required by this test" }),
    });
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/?view=analysis");

  await page.getByRole("button", { name: "Upload your own dataset" }).click();
  await page.getByLabel("Dataset name").fill("Private breast cohort");
  await page.getByLabel("Cancer context").selectOption("BRCA");
  const sampleIds = Array.from({ length: 18 }, (_, index) => `S${String(index + 1).padStart(2, "0")}`);
  const expression = [
    ["gene_symbol", ...sampleIds].join(","),
    ["ESR1", ...sampleIds.map((_, index) => (2 + index / 10).toFixed(1))].join(","),
  ].join("\n");
  const metadata = [
    "sample_id,subtype",
    ...sampleIds.map((sampleId, index) => {
      const subtype = index < 6 ? "Luminal A" : index < 12 ? "Luminal B" : "Basal-like";
      return `${sampleId},${subtype}`;
    }),
  ].join("\n");
  await page.locator("#user-expression-file").setInputFiles({
    name: "expression.csv",
    mimeType: "text/csv",
    buffer: Buffer.from(expression),
  });
  await page.locator("#user-clinical-file").setInputFiles({
    name: "metadata.csv",
    mimeType: "text/csv",
    buffer: Buffer.from(metadata),
  });
  await page.getByRole("button", { name: "Map columns" }).click();

  const outcomeToggle = page.getByRole("checkbox", {
    name: "This file includes a time-to-event outcome",
  });
  await expect(outcomeToggle).not.toBeChecked();
  await expect(page.getByText(/Expression comparison remains available/)).toBeVisible();
  await page.getByRole("button", { name: "Add variable" }).click();
  const customVariable = page.locator(".custom-clinical-variable");
  await expect(customVariable.getByLabel("Source column")).toHaveValue("subtype");
  await expect(customVariable.getByLabel("Value type")).toHaveValue("categorical");
  await expect(customVariable.getByText("18 observed · 3 unique")).toBeVisible();
  await page.getByLabel("Expression scale in the file", { exact: true }).selectOption("log2_tpm");
  await page.getByRole("checkbox", { name: /I confirm these files contain/ }).check();
  let uploadResponse = {
    status: 422,
    code: "INVALID_EXPRESSION_VALUE",
    message: "Expression table, row 2, column 2 ('S01'): use a finite number with a dot as the decimal separator (for example, 2.5), or leave the value blank or NA.",
    details: { row: 2, column: 2, column_name: "S01" },
  };
  await page.route("**/api/v1/user-datasets", async (route) => {
    await route.fulfill({
      status: uploadResponse.status,
      contentType: "application/json",
      body: JSON.stringify({ detail: uploadResponse }),
    });
  });
  await page.getByRole("button", { name: "Validate and use dataset" }).click();
  const uploadError = page.locator(".upload-error");
  await expect(uploadError).toContainText("row 2, column 2");
  await expect(uploadError).toContainText("dot as the decimal separator");
  await expect(customVariable.getByLabel("Source column")).toHaveValue("subtype");
  uploadResponse = {
    status: 429,
    code: "USER_DATASET_LIMIT",
    message: "Delete an existing private dataset before uploading another.",
    details: { maximum_active: 3 },
  };
  await page.getByRole("button", { name: "Validate and use dataset" }).click();
  await expect(uploadError).toContainText("3 active private datasets");
  await expect(uploadError).toContainText("Delete a private dataset you can access");
  await expect(uploadError).not.toContainText("compute requests");
  await expect.poll(() => page.evaluate(
    () => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1,
  )).toBe(true);
});

test("methods remains usable with WCAG text-spacing overrides at 320 px", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 800 });
  await page.goto("/?view=help");
  await page.addStyleTag({ content: `
    * {
      line-height: 1.5 !important;
      letter-spacing: 0.12em !important;
      word-spacing: 0.16em !important;
    }
    p { margin-block-end: 2em !important; }
  ` });

  await expect(page.getByRole("heading", { name: "Methods", level: 1 })).toBeVisible();
  await expect(page.getByRole("button", { name: "Explain Methods" })).toBeVisible();
  await expect(page.locator(".help-version-strip")).toHaveCount(0);
  await expect(page.getByRole("navigation", { name: "Methods sections" })).toBeVisible();
  await expect.poll(() => page.evaluate(
    () => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1,
  )).toBe(true);

  const criticalBlocks = page.locator(".topbar, .page-contents, .page-disclosure > summary");
  const blockCount = await criticalBlocks.count();
  for (let index = 0; index < blockCount; index += 1) {
    const block = criticalBlocks.nth(index);
    expect(await block.evaluate((element) => (
      element.scrollWidth <= element.clientWidth + 1
      && element.scrollHeight <= element.clientHeight + 1
    ))).toBe(true);
  }
});

for (const destination of [
  { label: "Home", query: "home" },
  { label: "Survival", query: "analysis" },
  { label: "Methods", query: "help" },
]) {
  test(`${destination.label} has no automated WCAG A/AA violations`, async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.goto(`/?view=${destination.query}`);

    const results = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
      .analyze();

    expect(results.violations).toEqual([]);
  });
}
