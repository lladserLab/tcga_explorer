import { expect, test } from "@playwright/test";

const staticAssets = [
  ["/brand/trace-mark.svg", "image/svg+xml"],
  ["/favicon.ico", "image/"],
  ["/favicon-32x32.png", "image/png"],
  ["/apple-touch-icon.png", "image/png"],
  ["/icons/trace-icon-192.png", "image/png"],
  ["/icons/trace-icon-512.png", "image/png"],
  ["/icons/trace-maskable-512.png", "image/png"],
  ["/social/trace-explorer-card-v1.png", "image/png"],
];

test("the mark is shared by the browser and application shell", async ({ page }) => {
  await page.route("**/api/**", (route) => route.fulfill({
    status: 503,
    contentType: "application/json",
    body: JSON.stringify({ detail: "Scientific API intentionally offline for brand E2E." }),
  }));
  await page.goto("/?view=home");

  await expect(page.locator('link[rel="icon"][type="image/svg+xml"]')).toHaveAttribute(
    "href",
    "/brand/trace-mark.svg",
  );
  await expect(page.locator('.app-header .brand-mark img')).toHaveAttribute(
    "src",
    "/brand/trace-mark.svg",
  );
  await expect(page.locator('.home-title-lockup .brand-mark img')).toHaveAttribute(
    "src",
    "/brand/trace-mark.svg",
  );
  await expect(page.locator(".app-header .brand-mark")).toBeVisible();
  await expect(page.locator(".home-title-lockup .brand-mark")).toBeVisible();
});

test("brand, install and social assets resolve as files rather than SPA fallbacks", async ({ request }) => {
  for (const [url, expectedType] of staticAssets) {
    const response = await request.get(url);
    expect(response.ok(), url).toBe(true);
    const contentType = response.headers()["content-type"] || "";
    expect(contentType, url).toContain(expectedType);
    expect(contentType, url).not.toContain("text/html");
  }

  const manifestResponse = await request.get("/site.webmanifest");
  expect(manifestResponse.ok()).toBe(true);
  expect(manifestResponse.headers()["content-type"]).not.toContain("text/html");
  const manifest = await manifestResponse.json();
  expect(manifest).toMatchObject({
    name: "TRACE Explorer",
    id: "./",
    start_url: "./",
    scope: "./",
  });
});
