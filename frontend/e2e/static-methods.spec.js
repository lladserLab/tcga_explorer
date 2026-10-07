import { expect, test } from "@playwright/test";


test("the signature-scoring reference is complete without JavaScript", async ({ browser }) => {
  const context = await browser.newContext({ javaScriptEnabled: false });
  const page = await context.newPage();
  await page.goto("/methods/signature-scoring?source=e2e#methods");

  await expect(page).toHaveURL(/\/methods\/signature-scoring\/\?source=e2e#methods$/);
  await expect(page).toHaveTitle("Signature scoring | TRACE Explorer Methods");
  await expect(page.getByRole("heading", { name: "Signature scoring", level: 1 })).toBeVisible();
  await expect(page.getByText("Recommended starting point", { exact: true })).toBeVisible();
  await expect(page.locator("details.method")).toHaveCount(8);
  await expect(page.locator("#method-singscore")).toContainText(
    "Recommended rank-based bulk score",
  );
  await expect(page.locator("#method-gsva")).toContainText("Not available");
  await expect(page.locator('link[rel="canonical"]')).toHaveAttribute(
    "href",
    "https://apps.cienciavida.org/tcga_explorer/methods/signature-scoring/",
  );
  await expect(page.getByRole("link", { name: "In-app explanation" })).toHaveAttribute(
    "href",
    "../../?view=help#trace-guide-methods-signature-scoring",
  );

  await context.close();
});


test("the static Methods page remains readable at 320 CSS pixels", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 800 });
  await page.goto("/methods/signature-scoring/");

  await expect(page.locator("#method-aucell summary")).toBeVisible();
  expect(await page.evaluate(
    () => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1,
  )).toBe(true);

  const summary = page.locator("#method-aucell summary");
  await expect(page.locator("#method-aucell")).not.toHaveAttribute("open", "");
  await summary.focus();
  await expect(summary).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.locator("#method-aucell")).toHaveAttribute("open", "");
});
