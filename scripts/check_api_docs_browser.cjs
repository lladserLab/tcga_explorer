/* Read-only browser check: never runs API examples or analysis jobs. */
const { chromium } = require("@playwright/test");
const assert = require("node:assert/strict");
(async () => {
  const base = (process.env.TRACE_DOCS_URL || "http://host.docker.internal:18123/tcga_explorer/").replace(/\/?$/, "/");
  const browser = await chromium.launch({ headless: true });
  try {
    for (const viewer of ["docs", "redoc"]) {
      const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
      const errors = [], external = [];
      page.on("pageerror", error => errors.push(error.message));
      page.on("console", message => {
        if (message.type() === "error" && /Content Security Policy|Refused to/.test(message.text())) errors.push(message.text());
      });
      page.on("request", request => {
        if (new URL(request.url()).origin !== new URL(base).origin) external.push(request.url());
      });
      await page.goto(base + "api/" + viewer);
      await page.locator("#docs-status").waitFor({ state: "hidden", timeout: 60000 });
      const text = await page.locator("#api-reference").innerText();
      assert(text.includes("/api/v1/"), "Reference must render actual endpoints");
      assert.equal(errors.length, 0, errors.join("\n"));
      assert.equal(external.length, 0, "Documentation contacted an external service: " + external.join(", "));
      console.log(viewer + ": visible endpoints, no CSP errors, no third-party requests");
      await page.setViewportSize({ width: 390, height: 844 });
      assert(await page.getByRole("link", { name: "Integration guide", exact: true }).isVisible());
      await page.route("**/api/openapi.json", route => route.fulfill({ status: 503, body: "unavailable" }));
      await page.reload();
      await page.getByRole("status").filter({ hasText: "could not load" }).waitFor();
      console.log(viewer + ": schema failure keeps actionable fallback visible");
      await page.close();
    }
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
