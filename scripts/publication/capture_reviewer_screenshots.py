#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BASE_URL = "http://host.docker.internal:3000/tcga_explorer/"
DEFAULT_OUTPUT_DIR = Path("manuscript/bioinformatics_app_note/figures")
DEFAULT_PLAYWRIGHT_IMAGE = "mcr.microsoft.com/playwright:v1.56.1-noble"
PLAYWRIGHT_VERSION = "1.56.1"
ANALYSIS_SCREENSHOT = "tcga_trace_ui_analysis.png"
MULTIVERSE_SCREENSHOT = "tcga_trace_ui_multiverse.png"
PANCANCER_SCREENSHOT = "tcga_trace_ui_pancancer.png"
METHODS_SCREENSHOT = "tcga_trace_ui_methods.png"


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    output_dir = ROOT / args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="tcga-trace-screenshots-") as tmp:
        runner_dir = Path(tmp)
        runner = runner_dir / "capture_screenshots.js"
        runner.write_text(playwright_runner_js(), encoding="utf-8")
        command = build_docker_command(ROOT, runner_dir, args)
        print("Capturing reviewer screenshots from", normalize_base_url(args.base_url))
        subprocess.run(command, cwd=ROOT, check=True)

    missing = missing_or_empty_outputs(output_dir)
    if missing:
        for path in missing:
            print(f"Missing or empty screenshot: {path}", file=sys.stderr)
        return 1

    for path in output_paths(output_dir):
        print(f"Wrote {path.relative_to(ROOT)} ({path.stat().st_size} bytes)")
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Regenerate reviewer-facing TCGA-TRACE interface screenshots. "
            "Run this after the Docker app stack is available. The default "
            "base URL targets a host app from inside the Playwright container."
        )
    )
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help=(
            "TCGA-TRACE app URL visible from the Playwright container. "
            f"Default: {DEFAULT_BASE_URL}"
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Repository-relative directory for screenshot PNGs. Default: {DEFAULT_OUTPUT_DIR}",
    )
    parser.add_argument(
        "--playwright-image",
        default=DEFAULT_PLAYWRIGHT_IMAGE,
        help=f"Docker image used to run Chromium/Playwright. Default: {DEFAULT_PLAYWRIGHT_IMAGE}",
    )
    return parser.parse_args(argv)


def normalize_base_url(value: str) -> str:
    return value.rstrip("/") + "/"


def build_docker_command(root: Path, runner_dir: Path, args: argparse.Namespace) -> list[str]:
    output_dir = args.output_dir.as_posix()
    install_and_run = textwrap.dedent(
        f"""
        set -euo pipefail
        cd /tmp
        npm init -y >/dev/null
        npm i playwright@{PLAYWRIGHT_VERSION} --no-save >/dev/null
        NODE_PATH=/tmp/node_modules node /runner/capture_screenshots.js
        """
    ).strip()
    return [
        "docker",
        "run",
        "--rm",
        "-e",
        f"BASE_URL={normalize_base_url(args.base_url)}",
        "-e",
        f"OUTPUT_DIR=/work/{output_dir}",
        "-e",
        f"ANALYSIS_SCREENSHOT={ANALYSIS_SCREENSHOT}",
        "-e",
        f"MULTIVERSE_SCREENSHOT={MULTIVERSE_SCREENSHOT}",
        "-e",
        f"PANCANCER_SCREENSHOT={PANCANCER_SCREENSHOT}",
        "-e",
        f"METHODS_SCREENSHOT={METHODS_SCREENSHOT}",
        "-v",
        f"{root.resolve()}:/work",
        "-v",
        f"{runner_dir.resolve()}:/runner:ro",
        "-w",
        "/work",
        args.playwright_image,
        "bash",
        "-lc",
        install_and_run,
    ]


def missing_or_empty_outputs(output_dir: Path) -> list[Path]:
    return [path for path in output_paths(output_dir) if not path.is_file() or path.stat().st_size == 0]


def output_paths(output_dir: Path) -> list[Path]:
    return [
        output_dir / ANALYSIS_SCREENSHOT,
        output_dir / MULTIVERSE_SCREENSHOT,
        output_dir / PANCANCER_SCREENSHOT,
        output_dir / METHODS_SCREENSHOT,
    ]


def playwright_runner_js() -> str:
    return r"""
const { chromium } = require("playwright");
const fs = require("fs");
const path = require("path");

const baseUrl = process.env.BASE_URL;
const outputDir = process.env.OUTPUT_DIR;
const analysisScreenshot = process.env.ANALYSIS_SCREENSHOT;
const multiverseScreenshot = process.env.MULTIVERSE_SCREENSHOT;
const pancancerScreenshot = process.env.PANCANCER_SCREENSHOT;
const methodsScreenshot = process.env.METHODS_SCREENSHOT;

function requireText(text, snippet) {
  if (!text.includes(snippet)) {
    throw new Error(`Expected page text to include: ${snippet}`);
  }
}

(async () => {
  fs.mkdirSync(outputDir, { recursive: true });
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({
    viewport: { width: 1440, height: 1200 },
    deviceScaleFactor: 3
  });
  page.setDefaultTimeout(60000);

  const browserErrors = [];
  page.on("console", (msg) => {
    if (msg.type() === "error") browserErrors.push(msg.text());
  });
  page.on("pageerror", (err) => browserErrors.push(err.message));

  await page.goto(baseUrl, { waitUntil: "networkidle", timeout: 60000 });
  await page.waitForSelector("text=TCGA-TRACE", { timeout: 60000 });

  await page.getByRole("button", { name: /^Survival:/ }).first().click();
  await page.locator("button.cohort-trigger").waitFor({ state: "visible" });
  await page.locator("button.cohort-trigger").click();
  await page.getByText("Liver Hepatocellular Carcinoma", { exact: true }).click();
  await page.getByRole("button", { name: /^Continue$/ }).click();
  const geneInput = page.getByRole("textbox", { name: "Gene symbols" });
  await geneInput.fill("CDC20");
  await geneInput.press("Enter");
  await page.locator(".gene-chip", { hasText: "CDC20" }).waitFor({ state: "visible" });
  await page.getByRole("button", { name: /^Continue$/ }).click();
  await page.getByRole("button", { name: /^Continue$/ }).click();
  await page.getByRole("button", { name: /^Continue$/ }).click();
  await page.getByRole("button", { name: /^Continue$/ }).click();
  const plotPreview = page.getByRole("img", {
    name: "Illustrative Kaplan-Meier plot style preview"
  });
  await plotPreview.waitFor({ state: "visible" });
  const riskTableSwitch = page.getByLabel("Risk table", { exact: true });
  await riskTableSwitch.setChecked(false, { force: true });
  if (await page.locator(".plot-preview-risk-table").count()) {
    throw new Error("The practical plot preview did not hide its risk table");
  }
  await riskTableSwitch.setChecked(true, { force: true });
  await page.locator(".plot-preview-risk-table").waitFor({ state: "visible" });
  await riskTableSwitch.setChecked(false, { force: true });
  await page.getByRole("button", { name: /^months$/i }).click();
  requireText(await plotPreview.textContent(), "Time (months)");
  await page.getByRole("button", { name: /^days$/i }).click();
  await page.getByRole("button", { name: /^Back$/ }).click();
  const clinicalStepText = await page.locator(".analysis-step-panel").innerText();
  requireText(clinicalStepText, "Clinical design");
  requireText(clinicalStepText, "ELIGIBILITY FILTERS");
  requireText(clinicalStepText, "Cox adjustment");
  requireText(clinicalStepText, "Age");
  requireText(clinicalStepText, "1 SELECTED");
  const desktopAdjustmentBoxes = await page
    .locator(".clinical-adjustment-option")
    .evaluateAll((items) => items.map((item) => {
      const box = item.getBoundingClientRect();
      return { x: box.x, y: box.y, width: box.width, height: box.height };
    }));
  const desktopColumns = new Set(desktopAdjustmentBoxes.map((box) => Math.round(box.x)));
  if (
    desktopAdjustmentBoxes.length !== 5 ||
    desktopColumns.size < 2 ||
    desktopAdjustmentBoxes.some((box) => box.width < 190 || box.height < 64)
  ) {
    throw new Error(
      `Desktop clinical adjustment layout is invalid: ${JSON.stringify(desktopAdjustmentBoxes)}`
    );
  }
  await page.getByRole("button", { name: /^Continue$/ }).click();
  await page.getByRole("button", { name: /^Run analysis$/ }).click();
  await page.waitForSelector("img.km-plot", { state: "visible", timeout: 180000 });
  await page.locator(".continuous-analysis").waitFor({ state: "visible", timeout: 180000 });
  const groupedHeading = page.locator(".grouped-analysis-heading");
  await groupedHeading.waitFor({ state: "visible", timeout: 180000 });
  requireText(await groupedHeading.innerText(), "CUTPOINT SENSITIVITY");
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.waitForTimeout(1000);

  const analysisText = await page.locator("body").innerText();
  requireText(analysisText, "Liver Hepatocellular Carcinoma");
  requireText(analysisText, "CDC20");
  requireText(analysisText, "Continuous expression model");
  requireText(analysisText, "Grouped Cox models");
  requireText(analysisText, "Events / parameter");
  requireText(analysisText, "Firth sensitivity");
  requireText(analysisText, "Restricted mean survival time");
  await page.screenshot({
    path: path.join(outputDir, analysisScreenshot),
    fullPage: false
  });

  await page.getByRole("button", { name: /^Multiverse:/ }).first().click();
  await page.locator("button.cohort-trigger").waitFor({ state: "visible" });
  await page.locator("button.cohort-trigger").click();
  await page.getByRole("option", { name: /Liver Hepatocellular/ }).click();
  const endpointButtons = page.locator(".multiverse-option-grid.endpoint-family button");
  for (const endpoint of ["DSS", "PFI", "DFI"]) {
    const button = endpointButtons.filter({ hasText: endpoint }).first();
    if ((await button.count()) && (await button.getAttribute("aria-pressed")) === "true") {
      await button.click();
    }
  }
  await page.getByRole("button", { name: /^Continue$/ }).click();
  const multiverseGeneInput = page.getByRole("textbox", { name: "Genes" });
  await multiverseGeneInput.fill("CDC20");
  await multiverseGeneInput.press("Enter");
  await page.locator(".gene-chip", { hasText: "CDC20" }).waitFor({ state: "visible" });
  await page.getByRole("button", { name: /^Continue$/ }).click();
  const cutpointButtons = page.locator(".multiverse-step-panel .method-grid.compact button");
  for (const cutpoint of ["Maxstat", "Outer quartiles", "Percentile"]) {
    const button = cutpointButtons.filter({ hasText: cutpoint }).first();
    if ((await button.getAttribute("aria-pressed")) === "true") {
      await button.click();
    }
  }
  await page.getByRole("button", { name: /^Continue$/ }).click();
  const multiverseClinicalText = await page.locator(".multiverse-step-panel").innerText();
  requireText(multiverseClinicalText, "Clinical design");
  requireText(multiverseClinicalText, "Age");
  await page.getByRole("button", { name: /^Continue$/ }).click();
  const frozenFamilyText = await page.locator(".multiverse-step-panel").innerText();
  requireText(frozenFamilyText, "2 planned specifications");
  requireText(frozenFamilyText, "1 tests");
  requireText(frozenFamilyText, "2 tests");
  requireText(frozenFamilyText, "No binary verdict");
  await page.getByRole("button", { name: /^Run multiverse$/ }).click();
  const multiverseResults = page.locator(".multiverse-results");
  await multiverseResults.waitFor({ state: "visible", timeout: 180000 });
  const multiverseText = await multiverseResults.innerText();
  requireText(multiverseText, "Specification family completed");
  requireText(multiverseText, "Continuous primary family");
  requireText(multiverseText, "Grouped sensitivity family");
  requireText(multiverseText, "Grouped specification curve");
  requireText(multiverseText, "Execution ledger");
  requireText(multiverseText, "No retained/not-retained rule");
  requireText(multiverseText, "Maxstat grouped HR and RMST remain post-selection");
  const curveImage = multiverseResults.getByRole("img", {
    name: /Specification curve for 2 completed of 2 planned analyses/
  });
  await curveImage.waitFor({ state: "visible", timeout: 60000 });
  await multiverseResults.scrollIntoViewIfNeeded();
  await page.waitForTimeout(1000);
  await page.screenshot({
    path: path.join(outputDir, multiverseScreenshot),
    fullPage: false
  });

  await page.getByRole("button", { name: /^Methods:/ }).first().click();
  await page.waitForSelector("text=Methods guide", { timeout: 60000 });
  await page.waitForTimeout(1000);
  const methodsText = await page.locator("body").innerText();
  requireText(methodsText, "Methods History");
  requireText(methodsText, "immune-pancancer-primary-plus-ordinal-sensitivity-cox-audit-v2.1");
  requireText(methodsText, "continuous-user-adjustment-firth-v6.2");
  requireText(methodsText, "pancancer-cox-v1.0");
  await page.screenshot({
    path: path.join(outputDir, methodsScreenshot),
    fullPage: false
  });

  await page.getByRole("button", { name: /^Examples:/ }).first().click();
  await page.waitForTimeout(1500);
  const examplesText = await page.locator("body").innerText();
  if (!examplesText.includes("Advanced workflow examples")) {
    throw new Error(
      `Paper Examples did not render. Console: ${browserErrors.join(" | ")}. ` +
      `Visible text: ${examplesText.slice(-2000)}`
    );
  }
  const evidenceSection = page.locator(".paper-example-section").first();
  const evidenceText = await evidenceSection.innerText();
  requireText(evidenceText, "Continuous marker profile");
  if (evidenceText.includes("Retained by reporting rule")) {
    throw new Error("Paper Examples still exposes the retired binary retention rule");
  }
  await evidenceSection.getByRole("tab", { name: /EMP3/i }).click();
  const emp3Panel = page.locator(".paper-case-explorer");
  await emp3Panel.waitFor({ state: "visible" });
  await emp3Panel.getByRole("heading", { name: "EMP3 in lower-grade glioma" }).waitFor();
  const emp3Text = await emp3Panel.innerText();
  requireText(emp3Text, "LINEAR COX P / BH Q");
  requireText(emp3Text, "NONLINEARITY P / BH Q");
  requireText(emp3Text, "Cutpoint sensitivity");
  requireText(emp3Text, "EVENTS / PARAMETER");
  requireText(emp3Text, "FIRTH SENSITIVITY");
  requireText(emp3Text, "MARKER PH P");
  requireText(emp3Text, "MODEL PH P");
  const continuousCount = emp3Panel.locator(".paper-case-counts span", {
    hasText: "continuous n / events"
  });
  requireText(await continuousCount.innerText(), "continuous n / events");
  await evidenceSection.getByRole("tab", { name: /BAP1/i }).click();
  const uvmPanel = page.locator(".paper-case-explorer");
  await uvmPanel.getByRole("heading", { name: "BAP1 in uveal melanoma" }).waitFor();
  await uvmPanel.getByRole("tab", { name: /Maxstat/i }).click();
  const uvmMaxstatText = await uvmPanel.innerText();
  requireText(uvmMaxstatText, "FIRTH SENSITIVITY");
  requireText(uvmMaxstatText, "0.02");
  requireText(uvmMaxstatText, "Standard adjusted Cox failed");
  await uvmPanel.getByRole("tab", { name: /Outer quartiles/i }).click();
  requireText(await uvmPanel.innerText(), "5.0 · caution");
  await page.getByRole("tab", { name: /BIRC5 pan-cancer primary/i }).click();
  const sensitivityPanel = page.locator(".pancancer-sensitivity").first();
  await sensitivityPanel.waitFor({ state: "visible", timeout: 60000 });
  await sensitivityPanel.scrollIntoViewIfNeeded();
  await page.waitForTimeout(1000);
  const sensitivityText = await sensitivityPanel.innerText();
  requireText(sensitivityText, "PRIMARY ESTIMAND");
  requireText(sensitivityText, "PARALLEL SENSITIVITY");
  requireText(sensitivityText, "mixed selected families are deliberately not pooled");
  await sensitivityPanel.screenshot({
    path: path.join(outputDir, pancancerScreenshot)
  });

  await page.getByRole("button", { name: /^Pan-cancer:/ }).first().click();
  const immuneAtlas = page.locator(".immune-atlas.analysis-result").first();
  await immuneAtlas.waitFor({ state: "visible", timeout: 60000 });
  const atlasText = await immuneAtlas.innerText();
  const normalizedAtlasText = atlasText.toLowerCase();
  requireText(normalizedAtlasText, "immune_os_immport_all_v2_1");
  requireText(normalizedAtlasText, "immune genes");
  requireText(normalizedAtlasText, "3,118");
  requireText(normalizedAtlasText, "fdr + ph caution");
  requireText(normalizedAtlasText, "899");

  const frequencyPanel = immuneAtlas.locator(".immune-panel.frequency");
  const spectrumPanel = immuneAtlas.locator(".immune-panel.spectrum");
  await frequencyPanel.waitFor({ state: "visible" });
  const frequencyBox = await frequencyPanel.boundingBox();
  const spectrumBox = await spectrumPanel.boundingBox();
  if (
    !frequencyBox ||
    !spectrumBox ||
    Math.abs(frequencyBox.y - spectrumBox.y) > 4 ||
    frequencyBox.width > 650 ||
    spectrumBox.width > 650
  ) {
    throw new Error(
      `Immune frequency and meta plots are not in the intended compact row: ` +
      `${JSON.stringify({ frequencyBox, spectrumBox })}`
    );
  }

  const atlasFdrMetric = immuneAtlas
    .locator(".immune-kpis .metric")
    .filter({ hasText: "Global FDR hits" });
  await immuneAtlas.getByRole("button", { name: /Stage \+ grade/ }).click();
  requireText(await atlasFdrMetric.innerText(), "178");
  await immuneAtlas.getByRole("button", { name: /^Primary/ }).click();
  requireText(await atlasFdrMetric.innerText(), "12,234");

  const mobilePage = await browser.newPage({
    viewport: { width: 390, height: 844 },
    deviceScaleFactor: 2
  });
  mobilePage.setDefaultTimeout(60000);
  mobilePage.on("console", (msg) => {
    if (msg.type() === "error") browserErrors.push(msg.text());
  });
  mobilePage.on("pageerror", (err) => browserErrors.push(err.message));
  await mobilePage.goto(baseUrl, { waitUntil: "networkidle", timeout: 60000 });
  await mobilePage.getByRole("button", { name: /^Survival:/ }).first().click();
  await mobilePage.locator("button.cohort-trigger").waitFor({ state: "visible" });
  await mobilePage.locator("button.cohort-trigger").click();
  await mobilePage.getByText("Liver Hepatocellular Carcinoma", { exact: true }).click();
  await mobilePage.getByRole("button", { name: /^Continue$/ }).click();
  requireText(await mobilePage.locator(".analysis-step-panel").innerText(), "Gene analysis");
  const mobileGeneInput = mobilePage.getByRole("textbox", { name: "Gene symbols" });
  await mobileGeneInput.fill("CDC20");
  await mobileGeneInput.press("Enter");
  await mobilePage.locator(".gene-chip", { hasText: "CDC20" }).waitFor({ state: "visible" });
  await mobilePage.getByRole("button", { name: /^Continue$/ }).click();
  await mobilePage.getByRole("button", { name: /^Continue$/ }).click();
  await mobilePage.getByRole("button", { name: /^Continue$/ }).click();
  const mobileClinicalText = await mobilePage.locator(".analysis-step-panel").innerText();
  requireText(mobileClinicalText, "Clinical design");
  requireText(mobileClinicalText, "Cox adjustment");
  const mobileAgeAdjustment = mobilePage
    .locator(".clinical-adjustment-option")
    .filter({ hasText: "Age" })
    .first()
    .locator("input");
  if (!(await mobileAgeAdjustment.isChecked())) {
    throw new Error("Age adjustment is not selected by default on mobile");
  }
  const mobileAdjustmentBoxes = await mobilePage
    .locator(".clinical-adjustment-option")
    .evaluateAll((items) => items.map((item) => {
      const box = item.getBoundingClientRect();
      return { x: box.x, y: box.y, width: box.width, height: box.height };
    }));
  const mobileColumns = new Set(mobileAdjustmentBoxes.map((box) => Math.round(box.x)));
  if (
    mobileAdjustmentBoxes.length !== 5 ||
    mobileColumns.size !== 1 ||
    mobileAdjustmentBoxes.some((box) => box.width < 190 || box.height < 64)
  ) {
    throw new Error(
      `Mobile clinical adjustment layout is invalid: ${JSON.stringify(mobileAdjustmentBoxes)}`
    );
  }
  const mobileLayout = await mobilePage.evaluate(() => ({
    innerWidth: window.innerWidth,
    scrollWidth: document.documentElement.scrollWidth,
  }));
  if (mobileLayout.scrollWidth !== mobileLayout.innerWidth) {
    throw new Error(`Mobile page overflow: ${JSON.stringify(mobileLayout)}`);
  }
  const mobilePanelBox = await mobilePage.locator(".analysis-step-panel").boundingBox();
  if (!mobilePanelBox || mobilePanelBox.y < 0 || mobilePanelBox.y >= 844) {
    throw new Error(`Next step is outside the mobile viewport: ${JSON.stringify(mobilePanelBox)}`);
  }
  await mobilePage.close();

  const multiverseMobilePage = await browser.newPage({
    viewport: { width: 390, height: 844 },
    deviceScaleFactor: 2
  });
  multiverseMobilePage.setDefaultTimeout(60000);
  await multiverseMobilePage.goto(baseUrl, { waitUntil: "networkidle", timeout: 60000 });
  await multiverseMobilePage.getByRole("button", { name: /^Multiverse:/ }).first().click();
  await multiverseMobilePage.locator("button.cohort-trigger").waitFor({ state: "visible" });
  await multiverseMobilePage.locator("button.cohort-trigger").click();
  await multiverseMobilePage.getByRole("option", { name: /Liver Hepatocellular/ }).click();
  await multiverseMobilePage.waitForFunction(() => (
    document.querySelectorAll(".multiverse-option-grid.endpoint-family button").length === 4
  ));
  const multiverseMobileLayout = await multiverseMobilePage.evaluate(() => ({
    innerWidth: window.innerWidth,
    scrollWidth: document.documentElement.scrollWidth,
  }));
  if (multiverseMobileLayout.scrollWidth !== multiverseMobileLayout.innerWidth) {
    throw new Error(`Mobile multiverse overflow: ${JSON.stringify(multiverseMobileLayout)}`);
  }
  const mobileEndpointBoxes = await multiverseMobilePage
    .locator(".multiverse-option-grid.endpoint-family button")
    .evaluateAll((items) => items.map((item) => {
      const box = item.getBoundingClientRect();
      return { x: box.x, width: box.width, height: box.height };
    }));
  const mobileEndpointColumns = new Set(mobileEndpointBoxes.map((box) => Math.round(box.x)));
  if (
    mobileEndpointBoxes.length !== 4 ||
    mobileEndpointColumns.size !== 1 ||
    mobileEndpointBoxes.some((box) => box.width < 250 || box.height < 72)
  ) {
    throw new Error(
      `Mobile endpoint family layout is invalid: ${JSON.stringify(mobileEndpointBoxes)}`
    );
  }
  await multiverseMobilePage.close();

  await browser.close();
  if (browserErrors.length) {
    console.warn(`Browser console errors observed: ${browserErrors.join(" | ")}`);
  }
})();
""".lstrip()


if __name__ == "__main__":
    sys.exit(main())
