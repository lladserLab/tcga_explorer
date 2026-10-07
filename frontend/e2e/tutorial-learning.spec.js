import { expect, test } from "@playwright/test";

async function expectContainedGuideSpotlight(page) {
  const spotlight = page.locator('[data-guide-spotlight="active"]');
  await expect(spotlight).toHaveCount(1);
  const treatment = await spotlight.evaluate((element) => {
    const styles = getComputedStyle(element);
    return {
      boxShadow: styles.boxShadow,
      outlineStyle: styles.outlineStyle,
    };
  });

  expect(treatment.boxShadow).toContain("inset");
  expect(treatment.outlineStyle).toBe("none");
}

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    try {
      const resetMarker = "trace-e2e-storage-reset";
      if (window.sessionStorage.getItem(resetMarker) !== "done") {
        window.localStorage.clear();
        window.sessionStorage.setItem(resetMarker, "done");
      }
    } catch {
      // Individual tests may deliberately block browser storage.
    }
  });
  await page.route("**/api/**", (route) => route.fulfill({
    status: 503,
    contentType: "application/json",
    body: JSON.stringify({ detail: "Scientific API intentionally offline in tutorial UI E2E." }),
  }));
});

test("Survival guide walks through all five setup stages before interpretation", async ({ page }) => {
  await page.setViewportSize({ width: 1500, height: 900 });
  await page.goto("/?view=analysis");

  const trigger = page.locator(".tutorial-quick-start");
  await expect(trigger).toContainText(/6 steps/);
  const workspacePaddingBefore = await page.locator(".workspace").evaluate(
    (element) => getComputedStyle(element).paddingRight,
  );
  await trigger.click();

  const dock = page.locator("#trace-tutorial-dock");
  await expect(dock).toBeVisible();
  await expect(dock.getByRole("heading", { name: "Survival" })).toBeFocused();
  await expect(trigger).toHaveAttribute("aria-expanded", "true");
  await expect(dock.getByRole("button", { name: "Begin guide" })).toHaveCount(0);
  await expect(dock.getByRole("heading", { level: 3 })).toBeVisible();
  await expect(dock.locator('[aria-current="step"]')).toHaveCount(1);
  await expect(dock.getByRole("button", { name: "Previous" })).toBeDisabled();
  await expect(page).toHaveURL(/lesson=data/);
  await expect(page.locator("#analysis-step-panel-data")).toBeVisible();
  await expectContainedGuideSpotlight(page);

  await expect(dock.getByRole("button", { name: "Apply preset" })).toHaveCount(0);
  await expect(dock).toHaveCSS("position", "fixed");
  await expect(dock).toHaveCSS("bottom", "16px");
  const expandedDockBox = await dock.boundingBox();
  expect(expandedDockBox.y).toBeGreaterThan(32);
  expect(expandedDockBox.width).toBeLessThanOrEqual(410);
  await expect(page.locator(".workspace")).not.toHaveClass(/tutorial-open/);
  await expect.poll(() => page.locator(".workspace").evaluate(
    (element) => getComputedStyle(element).paddingRight,
  )).toBe(workspacePaddingBefore);
  await expect(dock.getByRole("button", { name: "Show me where" })).toHaveCount(0);

  const setupStages = [
    ["marker", "design"],
    ["outcome", "outcome"],
    ["clinical", "clinical"],
    ["review-run", "review"],
  ];
  for (const [lesson, panel] of setupStages) {
    await dock.getByRole("button", { name: "Next" }).click();
    await expect(dock).toHaveAttribute("data-lesson", lesson);
    await expect(page).toHaveURL(new RegExp(`lesson=${lesson}`));
    await expect(page.locator(`#analysis-step-panel-${panel}`)).toBeVisible();
    await expectContainedGuideSpotlight(page);
  }

  await dock.getByRole("button", { name: "Next" }).click();
  await expect(dock).toHaveAttribute("data-lesson", "interpret");
  await expect(page).toHaveURL(/lesson=interpret/);
  await expect(dock.getByText("6. How to read the result", { exact: true })).toBeVisible();
  await expect(dock.getByText("Question this analysis answers", { exact: true })).toBeVisible();
  await expect(dock.getByText("Limitations", { exact: true })).toBeVisible();
  await expect(dock.getByText("Bibliographic references", { exact: true })).toBeVisible();
  await expect(dock.getByText("Before you continue", { exact: true })).toHaveCount(0);
  await expect(dock.getByRole("button", { name: "Reviewed" })).toHaveCount(0);
  await expect(dock.getByRole("button", { name: "Finish" })).toBeEnabled();

  await page.keyboard.press("Escape");
  await expect(dock).toHaveCount(0);
  await expect(trigger).toBeFocused();
  await expect(trigger).toHaveAttribute("aria-expanded", "false");
});

test("Compare guide synchronizes all five setup panels before interpretation", async ({ page }) => {
  await page.setViewportSize({ width: 1500, height: 900 });
  await page.goto("/?view=compare");

  const trigger = page.locator(".tutorial-quick-start");
  await expect(trigger).toContainText(/6 steps/);
  await trigger.click();

  const dock = page.locator("#trace-tutorial-dock");
  await expect(dock.getByRole("button", { name: "Begin guide" })).toHaveCount(0);
  await expect(dock).toHaveAttribute("data-lesson", "dataset");
  await expect(dock.getByRole("button", { name: "Previous" })).toBeDisabled();
  await expect(dock.getByRole("button", { name: "Show me where" })).toHaveCount(0);
  await expect(page.locator("#compare-step-panel-dataset")).toBeVisible();

  for (const [lesson, panel] of [
    ["markers", "markers"],
    ["methods", "methods"],
    ["clinical", "filters"],
    ["review-run", "run"],
  ]) {
    await dock.getByRole("button", { name: "Next" }).click();
    await expect(dock).toHaveAttribute("data-lesson", lesson);
    await expect(page.locator(`#compare-step-panel-${panel}`)).toBeVisible();
  }

  await dock.getByRole("button", { name: "Next" }).click();
  await expect(dock).toHaveAttribute("data-lesson", "interpret");
  await expect(dock.getByRole("button", { name: "Reviewed" })).toHaveCount(0);
  await expect(dock.getByRole("button", { name: "Finish" })).toBeEnabled();
});

test("an open quick guide follows manual module navigation and browser history", async ({ page }) => {
  await page.setViewportSize({ width: 1500, height: 900 });
  await page.goto("/?view=analysis");

  const workspaceNavigation = page.getByRole("navigation", { name: "Workspace pages" });
  const dock = page.locator("#trace-tutorial-dock");

  await workspaceNavigation.getByRole("button", { name: /^GSEA:/ }).click();
  await expect(page).toHaveURL(/view=gsea/);
  await expect(page).not.toHaveURL(/[?&]guide=/);
  await expect(dock).toHaveCount(0);

  await workspaceNavigation.getByRole("button", { name: /^Survival:/ }).click();
  await page.locator(".tutorial-quick-start").click();
  await expect(dock.getByRole("heading", { name: "Survival" })).toBeVisible();
  await expect(dock).toHaveAttribute("data-lesson", "data");
  await expect(page).toHaveURL(/guide=quick-analysis/);

  await workspaceNavigation.getByRole("button", { name: /^GSEA:/ }).click();
  await expect(dock.getByRole("heading", { name: "GSEA, step by step" })).toBeVisible();
  await expect(dock).toHaveAttribute("data-lesson", "dataset");
  await expect(page).toHaveURL(/view=gsea/);
  await expect(page).toHaveURL(/guide=quick-gsea/);
  await expect(page).toHaveURL(/lesson=dataset/);

  await page.goBack();
  await expect(dock.getByRole("heading", { name: "Survival" })).toBeVisible();
  await expect(dock).toHaveAttribute("data-lesson", "data");
  await expect(page).toHaveURL(/view=analysis/);
  await expect(page).toHaveURL(/guide=quick-analysis/);

  await page.goForward();
  await expect(dock.getByRole("heading", { name: "GSEA, step by step" })).toBeVisible();
  await expect(dock).toHaveAttribute("data-lesson", "dataset");
  await expect(page).toHaveURL(/view=gsea/);
  await expect(page).toHaveURL(/guide=quick-gsea/);

  await workspaceNavigation.getByRole("button", { name: /^Dataset:/ }).click();
  await expect(page).toHaveURL(/view=summary/);
  await expect(page).not.toHaveURL(/[?&]guide=/);
  await expect(dock).toHaveCount(0);

  await page.goBack();
  await expect(dock.getByRole("heading", { name: "GSEA, step by step" })).toBeVisible();
  await expect(page).toHaveURL(/view=gsea/);
  await expect(page).toHaveURL(/guide=quick-gsea/);

  await page.goForward();
  await expect(page).toHaveURL(/view=summary/);
  await expect(page).not.toHaveURL(/[?&]guide=/);
  await expect(dock).toHaveCount(0);
});

test("route navigation changes modules without replacing the active route", async ({ page }) => {
  await page.setViewportSize({ width: 1500, height: 900 });
  await page.goto(
    "/?view=expression&guide=groups-to-pathways&lesson=primary-evidence&tab=tutorials",
  );

  const dock = page.locator("#trace-tutorial-dock");
  await expect(dock.getByRole("heading", { name: "From groups to pathways" })).toBeVisible();
  await expect(dock).toHaveAttribute("data-lesson", "primary-evidence");

  await dock.getByRole("button", { name: "Next" }).click();
  await expect(dock.getByRole("heading", { name: "From groups to pathways" })).toBeVisible();
  await expect(dock).toHaveAttribute("data-lesson", "diagnostics");
  await expect(page).toHaveURL(/view=gsea/);
  await expect(page).toHaveURL(/guide=groups-to-pathways/);
  await expect(page).not.toHaveURL(/guide=quick-gsea/);

  await page.goBack();
  await expect(dock).toHaveAttribute("data-lesson", "primary-evidence");
  await expect(page).toHaveURL(/view=expression/);
  await expect(page).toHaveURL(/guide=groups-to-pathways/);

  await page.goForward();
  await expect(dock).toHaveAttribute("data-lesson", "diagnostics");
  await expect(page).toHaveURL(/view=gsea/);
  await expect(page).toHaveURL(/guide=groups-to-pathways/);
});

test("informational pages have no contextual guide and keep only analytic quick guides", async ({ page }) => {
  await page.setViewportSize({ width: 1500, height: 900 });
  await page.goto("/?view=gsea");
  await page.getByRole("button", { name: /Learn this module/ }).click();

  const dock = page.locator("#trace-tutorial-dock");
  const workspaceNavigation = page.getByRole("navigation", { name: "Workspace pages" });
  await expect(dock).toBeVisible();

  for (const destination of [
    { label: /^Dataset:/, view: "summary" },
    { label: /^Guides:/, view: "examples" },
    { label: /^External cohorts:/, view: "repository" },
    { label: /^API & MCP:/, view: "api" },
    { label: /^Methods:/, view: "help" },
  ]) {
    await workspaceNavigation.getByRole("button", { name: destination.label }).click();
    await expect(page).toHaveURL(new RegExp(`view=${destination.view}`));
    await expect(page.locator(".tutorial-quick-start")).toHaveCount(0);
    await expect(dock).toHaveCount(0);
    await expect(page).not.toHaveURL(/[?&]guide=/);

    if (destination.view === "examples") {
      await expect(page.locator(
        '[data-guide-anchor="examples.quick-guides"] .trace-tutorial-row',
      )).toHaveCount(8);
    }
  }
});

test("mobile guide keeps explicit mini mode without a workspace-locating action", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/?view=gsea");

  await page.getByRole("button", { name: /Learn this module/ }).click();
  const dock = page.locator("#trace-tutorial-dock");
  await expect(dock).toHaveCSS("position", "fixed");
  await expect(dock).toHaveCSS("bottom", "8px");
  await expect(dock).toHaveCSS("border-radius", "8px");
  await expect(dock.getByRole("button", { name: "Begin guide" })).toHaveCount(0);
  await expect(dock.getByRole("button", { name: "Show me where" })).toHaveCount(0);
  await dock.getByRole("button", { name: "Minimize tutorial" }).click();

  await expect(dock).toHaveAttribute("data-presentation", "mini");
  await expect(dock.locator(".trace-tutorial-mini-main")).toBeVisible();
  await dock.locator(".trace-tutorial-mini-main").click();
  await expect(dock).toHaveAttribute("data-presentation", "auto");
  await expect(dock.getByRole("heading", {
    level: 2,
    name: "GSEA, step by step",
    exact: true,
  })).toBeFocused();

  await expect(dock.getByRole("combobox", { name: "Language" })).toHaveCount(0);
  await expect(dock.getByRole("button", { name: "Next" })).toBeVisible();
  await expect(dock.getByRole("button", { name: "Siguiente" })).toHaveCount(0);
});

test("Learning Center triggers transfer focus when navigation unmounts it", async ({ page }) => {
  await page.setViewportSize({ width: 1500, height: 900 });
  await page.goto("/?view=examples&tab=tutorials");
  await expect(page.locator(".tutorial-quick-start")).toHaveCount(0);
  const routeRow = page.locator(".trace-tutorial-row").filter({ hasText: "Analyze your own data" });
  await routeRow.getByRole("button", { name: "Start" }).click();
  const dock = page.locator("#trace-tutorial-dock");
  await expect(dock.getByRole("heading", { name: "Analyze your own data" })).toBeFocused();
  await expect(dock).toHaveAttribute("data-lesson", "overview");
  await expect(dock.getByRole("button", { name: "Begin guide" })).toBeVisible();
});

test("legacy Spanish links canonicalize to the English guide without gating completion", async ({ page }) => {
  await page.goto("/?view=gsea&guide=quick-gsea&lesson=complete&lang=es&tab=tutorials");
  const dock = page.locator("#trace-tutorial-dock");
  await expect(dock).toHaveAttribute("data-lesson", "complete");
  await expect(page).toHaveURL(/lesson=complete/);
  await expect(page).not.toHaveURL(/[?&]lang=/);
  await expect(dock.getByText(
    "You have finished this guide. You can reopen it from the first page at any time.",
    { exact: true },
  )).toBeVisible();
  await expect(dock.getByText("Completed", { exact: true })).toHaveCount(0);
  await expect(dock.getByRole("button", { name: "Review guide" })).toBeVisible();
  await expect(dock.getByRole("combobox", { name: "Language" })).toHaveCount(0);
  await expect(dock.getByText("Guía completada")).toHaveCount(0);
});

test("blocked browser storage falls back visibly without crashing", async ({ page }) => {
  await page.addInitScript(() => {
    Object.defineProperty(window, "localStorage", {
      configurable: true,
      get() {
        throw new DOMException("Storage blocked for test", "SecurityError");
      },
    });
  });
  await page.goto("/?view=gsea");
  await page.getByRole("button", { name: /Learn this module/ }).click();

  await expect(page.getByText(/Browser storage is unavailable/)).toBeVisible();
  await expect(page.locator("#trace-tutorial-dock")).toBeVisible();
});

test("live progress survives reload and browser Back/Forward navigation", async ({ page }) => {
  await page.goto("/?view=gsea");
  await page.getByRole("button", { name: /Learn this module/ }).click();

  const dock = page.locator("#trace-tutorial-dock");
  await expect(dock.getByRole("button", { name: "Begin guide" })).toHaveCount(0);
  await expect(dock.getByRole("button", { name: "Reviewed" })).toHaveCount(0);
  await dock.getByRole("button", { name: "Next" }).click();
  await expect(dock).toHaveAttribute("data-lesson", "groups");
  const savedProgress = await page.evaluate(() => (
    JSON.parse(window.localStorage.getItem("trace-learning-progress-v3"))
      ?.guides?.["quick-gsea"] || null
  ));
  expect(savedProgress).toMatchObject({
    lastStepId: "groups",
    status: "in_progress",
  });
  expect(savedProgress).not.toHaveProperty("completedCheckpointIds");

  await page.reload();
  await expect(dock).toHaveAttribute("data-lesson", "groups");

  await page.goBack();
  await expect(dock).toHaveAttribute("data-lesson", "dataset");
  const restoredProgress = await page.evaluate(() => (
    JSON.parse(window.localStorage.getItem("trace-learning-progress-v3"))
      ?.guides?.["quick-gsea"] || null
  ));
  expect(restoredProgress).not.toHaveProperty("completedCheckpointIds");
  await expect(dock.getByRole("button", { name: "Reviewed" })).toHaveCount(0);

  await page.goForward();
  await expect(dock).toHaveAttribute("data-lesson", "groups");
  await expect(dock.getByText("Completed", { exact: true })).toHaveCount(0);
});
