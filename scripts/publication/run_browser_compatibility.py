#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
import textwrap
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BASE_URL = "auto"
DEFAULT_OUTPUT_DIR = Path("docs/publication/benchmark/browser_compatibility")
DEFAULT_RECORD = Path(
    "manuscript/bioinformatics_app_note/submission/browser_compatibility_record.md"
)
DEFAULT_PLAYWRIGHT_IMAGE = "mcr.microsoft.com/playwright:v1.56.1-noble"
PLAYWRIGHT_VERSION = "1.56.1"
SCHEMA_VERSION = "tcga-trace-browser-compatibility-v1"
ENGINES = ("chromium", "firefox", "webkit")
RAW_FILENAME = "benchmark_results.raw.json"
SUMMARY_FILENAME = "summary.md"
MANIFEST_FILENAME = "manifest.json"
FINAL_RETEST_TOKEN = "FINAL_RELEASE_RETEST_REQUIRED"
REQUIRED_CHECKS = (
    "landing_and_keyboard",
    "survival_suggestions_analysis_and_download",
    "competing_risk_analysis",
    "compare_suggestions_preview_and_four_method_run",
    "exploratory_session_history",
    "paper_examples",
    "pancancer_and_dataset",
    "reduced_motion",
)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    output_dir = ROOT / args.output_dir
    record_path = ROOT / args.record

    if args.check_only:
        return check_frozen_output(output_dir, record_path, require_final=args.require_final)

    engines = parse_engines(args.engines)
    base_url = resolve_base_url(args.base_url, ROOT)
    release = git_release_state(ROOT)
    if args.final_release:
        validate_final_release(base_url, release)

    output_dir.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now(timezone.utc).isoformat()
    results: list[dict[str, Any]] = []

    with tempfile.TemporaryDirectory(prefix="tcga-trace-browser-compat-") as tmp:
        temp_root = Path(tmp)
        runner_path = temp_root / "browser_compatibility.js"
        result_dir = temp_root / "results"
        result_dir.mkdir()
        runner_path.write_text(playwright_runner_js(), encoding="utf-8")

        for engine in engines:
            command = build_docker_command(
                ROOT,
                runner_path,
                result_dir,
                engine=engine,
                base_url=base_url,
                playwright_image=args.playwright_image,
                expected_release_commit=(
                    release["commit"] if args.final_release else ""
                ),
                expected_release_ref=(
                    release["exact_tag"] if args.final_release else ""
                ),
            )
            print(
                f"Running {engine} compatibility smoke test against {base_url}",
                flush=True,
            )
            completed = subprocess.run(command, cwd=ROOT, check=False)
            result_path = result_dir / f"{engine}.json"
            if not result_path.is_file():
                raise SystemExit(
                    f"{engine} runner produced no result record (exit {completed.returncode})"
                )
            result = json.loads(result_path.read_text(encoding="utf-8"))
            results.append(result)
            if completed.returncode != 0 or result.get("status") != "passed":
                write_outputs(
                    output_dir=output_dir,
                    record_path=record_path,
                    base_url=base_url,
                    generated_at=generated_at,
                    release=release,
                    results=results,
                    final_release=args.final_release,
                    tester=args.tester,
                    playwright_image=args.playwright_image,
                )
                raise SystemExit(
                    f"{engine} browser compatibility failed; inspect {output_dir / RAW_FILENAME}"
                )

    write_outputs(
        output_dir=output_dir,
        record_path=record_path,
        base_url=base_url,
        generated_at=generated_at,
        release=release,
        results=results,
        final_release=args.final_release,
        tester=args.tester,
        playwright_image=args.playwright_image,
    )
    return check_frozen_output(
        output_dir,
        record_path,
        require_final=args.final_release,
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run the TCGA-TRACE browser compatibility contract in isolated "
            "Playwright containers for Chromium, Gecko/Firefox and WebKit."
        )
    )
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--record", type=Path, default=DEFAULT_RECORD)
    parser.add_argument("--engines", default=",".join(ENGINES))
    parser.add_argument("--playwright-image", default=DEFAULT_PLAYWRIGHT_IMAGE)
    parser.add_argument(
        "--tester",
        default="Automated Playwright compatibility contract",
        help="Name recorded as the tester.",
    )
    parser.add_argument(
        "--final-release",
        action="store_true",
        help=(
            "Generate final editorial evidence. Requires a clean exact-tag "
            "checkout and an HTTPS target."
        ),
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Validate existing JSON, summary, manifest and browser record.",
    )
    parser.add_argument(
        "--require-final",
        action="store_true",
        help="With --check-only, reject provisional pre-release evidence.",
    )
    args = parser.parse_args(argv)
    if args.require_final and not args.check_only:
        parser.error("--require-final is only valid with --check-only")
    if args.check_only and args.final_release:
        parser.error("--check-only and --final-release are mutually exclusive")
    return args


def parse_engines(value: str) -> tuple[str, ...]:
    requested = tuple(item.strip().lower() for item in value.split(",") if item.strip())
    unknown = [item for item in requested if item not in ENGINES]
    if unknown:
        raise ValueError(f"Unsupported browser engine(s): {', '.join(unknown)}")
    if not requested:
        raise ValueError("At least one browser engine is required")
    if len(set(requested)) != len(requested):
        raise ValueError("Browser engine names must not be repeated")
    return requested


def normalize_base_url(value: str) -> str:
    return value.rstrip("/") + "/"


def resolve_base_url(value: str, root: Path) -> str:
    if value != "auto":
        return normalize_base_url(value)
    completed = subprocess.run(
        ["docker", "compose", "port", "nginx", "80"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    binding = completed.stdout.strip().splitlines()[-1]
    if binding.startswith("["):
        host, port = binding.rsplit("]:", 1)
        host = host[1:]
    else:
        host, port = binding.rsplit(":", 1)
    if host in {"0.0.0.0", "127.0.0.1", "::", "localhost"}:
        host = "host.docker.internal"
    return f"http://{host}:{port}/tcga_explorer/"


def git_release_state(root: Path) -> dict[str, Any]:
    commit = run_git(root, "rev-parse", "HEAD")
    porcelain = run_git(root, "status", "--porcelain", "--untracked-files=all")
    tags_text = run_git(root, "tag", "--points-at", "HEAD")
    tags = [item for item in tags_text.splitlines() if item.strip()]
    return {
        "commit": commit,
        "dirty": bool(porcelain.strip()),
        "tags_at_head": tags,
        "exact_tag": tags[0] if len(tags) == 1 else None,
    }


def run_git(root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def validate_final_release(base_url: str, release: dict[str, Any]) -> None:
    problems: list[str] = []
    if urlparse(base_url).scheme.lower() != "https":
        problems.append("the final compatibility target must use HTTPS")
    if release.get("dirty"):
        problems.append("the final compatibility run requires a clean worktree")
    if not release.get("exact_tag"):
        problems.append("HEAD must have exactly one release tag")
    if problems:
        raise ValueError("; ".join(problems))


def build_docker_command(
    root: Path,
    runner_path: Path,
    result_dir: Path,
    *,
    engine: str,
    base_url: str,
    playwright_image: str,
    expected_release_commit: str = "",
    expected_release_ref: str = "",
) -> list[str]:
    install_and_run = textwrap.dedent(
        f"""
        set -euo pipefail
        cd /tmp
        npm init -y >/dev/null
        npm i playwright@{PLAYWRIGHT_VERSION} --no-save >/dev/null
        NODE_PATH=/tmp/node_modules node /runner/browser_compatibility.js
        """
    ).strip()
    return [
        "docker",
        "run",
        "--rm",
        "-e",
        f"BASE_URL={base_url}",
        "-e",
        f"ENGINE={engine}",
        "-e",
        f"RESULT_PATH=/results/{engine}.json",
        "-e",
        f"EXPECTED_RELEASE_COMMIT={expected_release_commit}",
        "-e",
        f"EXPECTED_RELEASE_REF={expected_release_ref}",
        "-v",
        f"{root.resolve()}:/work:ro",
        "-v",
        f"{runner_path.resolve()}:/runner/browser_compatibility.js:ro",
        "-v",
        f"{result_dir.resolve()}:/results",
        playwright_image,
        "bash",
        "-lc",
        install_and_run,
    ]


def write_outputs(
    *,
    output_dir: Path,
    record_path: Path,
    base_url: str,
    generated_at: str,
    release: dict[str, Any],
    results: list[dict[str, Any]],
    final_release: bool,
    tester: str,
    playwright_image: str,
) -> None:
    status = (
        "passed_final_release"
        if final_release and all(item.get("status") == "passed" for item in results)
        else "passed_provisional"
        if all(item.get("status") == "passed" for item in results)
        else "failed"
    )
    payload = {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "generated_at": generated_at,
        "base_url": base_url,
        "tester": tester,
        "playwright": {
            "version": PLAYWRIGHT_VERSION,
            "image": playwright_image,
        },
        "release": release,
        "required_engines": list(ENGINES),
        "required_checks": list(REQUIRED_CHECKS),
        "results": results,
        "scope": {
            "webkit_note": (
                "Playwright WebKit exercises the WebKit engine but is not an "
                "exact substitute for a manual Safari build/version check."
            ),
            "final_contract": (
                "Final evidence is generated only from a clean exact-tag "
                "checkout against an HTTPS deployment whose public health "
                "release commit and ref match that checkout."
            ),
        },
    }
    raw_path = output_dir / RAW_FILENAME
    raw_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    summary_path = output_dir / SUMMARY_FILENAME
    summary_path.write_text(render_summary(payload), encoding="utf-8")
    record_path.parent.mkdir(parents=True, exist_ok=True)
    record_path.write_text(render_browser_record(payload), encoding="utf-8")

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "status": status,
        "files": {
            RAW_FILENAME: file_record(raw_path),
            SUMMARY_FILENAME: file_record(summary_path),
        },
    }
    (output_dir / MANIFEST_FILENAME).write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def file_record(path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    return {
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def observed_deployment_commits(payload: dict[str, Any]) -> list[str]:
    commits = {
        str((check.get("details") or {}).get("release_commit") or "").strip()
        for result in payload.get("results", [])
        for check in result.get("checks", [])
        if check.get("id") == "landing_and_keyboard"
    }
    return sorted(commit for commit in commits if commit)


def render_summary(payload: dict[str, Any]) -> str:
    release = payload["release"]
    deployed_commits = observed_deployment_commits(payload)
    lines = [
        "# Browser Compatibility Benchmark",
        "",
        f"- Status: `{payload['status']}`",
        f"- Tested: `{payload['generated_at']}`",
        f"- Target: `{payload['base_url']}`",
        f"- Commit: `{release['commit']}`",
        f"- Exact tag: `{release.get('exact_tag') or 'none'}`",
        f"- Observed deployment commit(s): `{', '.join(deployed_commits) or 'not reported'}`",
        f"- Worktree dirty before run: `{str(bool(release['dirty'])).lower()}`",
        f"- Playwright: `{payload['playwright']['version']}`",
        f"- Container: `{payload['playwright']['image']}`",
        "",
        "| Engine | Browser version | Checks | Result | Duration (s) |",
        "| --- | --- | ---: | --- | ---: |",
    ]
    for result in payload["results"]:
        passed = sum(item.get("status") == "passed" for item in result.get("checks", []))
        total = len(result.get("checks", []))
        lines.append(
            "| {engine} | {version} | {passed}/{total} | {status} | {duration:.2f} |".format(
                engine=result.get("engine", "unknown"),
                version=result.get("browser_version", "unknown"),
                passed=passed,
                total=total,
                status=result.get("status", "unknown"),
                duration=float(result.get("duration_ms", 0)) / 1000,
            )
        )
    lines.extend(
        [
            "",
            "## Contract",
            "",
            "Each engine runs the following checks:",
            "",
            "- landing page, keyboard focus and navigation;",
            "- Survival gene suggestions, external-covariate CSV configuration, completed CDC20/LIHC analysis, audit download and signed-receipt download;",
            "- UVM/BAP1/DSS competing-risk output with CIF, Gray/Fine-Gray, square PNG download and desktop/mobile containment;",
            "- Compare gene suggestions, live preview and the four-method publication panel;",
            "- opt-in exploratory run history, export-defined multiplicity families, signed receipt and 390-pixel mobile containment;",
            "- final-release commit identity from the public health resource;",
            "- frozen Paper Examples rendering;",
            "- Pan-cancer and Dataset Summary visualizations; and",
            "- reduced-motion rendering and navigation.",
            "",
            "Playwright WebKit validates the engine contract but is not an exact substitute "
            "for a manual check in the final Safari release. Provisional evidence must be "
            "rerun against the exact tagged HTTPS deployment before submission.",
            "",
        ]
    )
    return "\n".join(lines)


def render_browser_record(payload: dict[str, Any]) -> str:
    is_final = payload["status"] == "passed_final_release"
    release = payload["release"]
    deployed_commits = observed_deployment_commits(payload)
    status_text = (
        "final tagged HTTPS release verified"
        if is_final
        else f"provisional pre-release validation; {FINAL_RETEST_TOKEN}"
    )
    lines = [
        "# Browser Compatibility Record",
        "",
        f"Status: {status_text}.",
        "",
        "Bioinformatics states that web servers should not be browser-specific. "
        "This record is generated by the versioned Playwright compatibility contract.",
        "",
        f"- Target: `{payload['base_url']}`",
        f"- Commit: `{release['commit']}`",
        f"- Exact tag: `{release.get('exact_tag') or 'none'}`",
        f"- Observed deployment commit(s): `{', '.join(deployed_commits) or 'not reported'}`",
        f"- Tested: `{payload['generated_at']}`",
        f"- Container: `{payload['playwright']['image']}`",
        "",
        "| Engine | Browser and version | Runtime OS | Date | Result | Tester |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for result in payload["results"]:
        passed = sum(item.get("status") == "passed" for item in result.get("checks", []))
        total = len(result.get("checks", []))
        lines.append(
            "| {engine} | Playwright {version} | {os} | {date} | {status} ({passed}/{total}) | {tester} |".format(
                engine=engine_label(result.get("engine", "")),
                version=result.get("browser_version", "unknown"),
                os=result.get("runtime_os", "unknown"),
                date=payload["generated_at"][:10],
                status="Passed" if result.get("status") == "passed" else "Failed",
                passed=passed,
                total=total,
                tester=payload["tester"],
            )
        )
    lines.extend(
        [
            "",
            "## Automated Scope",
            "",
            "- landing application, navigation and keyboard-visible focus;",
            "- gene suggestions in Survival and Compare;",
            "- external-covariate CSV upload, ordinal coding, explicit selection and removal;",
            "- completed Kaplan-Meier, continuous/grouped Cox, RMST and audit output;",
            "- completed UVM/BAP1/DSS cumulative-incidence and Fine-Gray output, including square-image download and mobile containment;",
            "- four-method Compare publication panel and live setup preview;",
            "- opt-in exploratory run history, export-defined multiplicity families, signed receipt and 390-pixel mobile containment;",
            "- final-release commit identity from the public health resource;",
            "- frozen Paper Examples;",
            "- Pan-cancer and Dataset Summary plots;",
            "- actual audit JSON and Ed25519 receipt downloads; and",
            "- reduced-motion media behavior.",
            "",
            "Machine-readable evidence and per-check timings are stored in "
            "`docs/publication/benchmark/browser_compatibility/`.",
            "",
            "## Interpretation",
            "",
            "Playwright WebKit exercises the WebKit engine but does not identify an exact "
            "Safari product build. Record a short manual Safari check if the final deployment "
            "depends on Safari-specific behavior. A provisional run does not satisfy the "
            "submission gate; rerun with `--final-release` from the clean tagged checkout "
            "against the public HTTPS URL.",
            "",
        ]
    )
    return "\n".join(lines)


def engine_label(engine: str) -> str:
    return {
        "chromium": "Chromium",
        "firefox": "Gecko",
        "webkit": "WebKit",
    }.get(engine, engine or "Unknown")


def check_frozen_output(
    output_dir: Path,
    record_path: Path,
    *,
    require_final: bool,
) -> int:
    raw_path = output_dir / RAW_FILENAME
    summary_path = output_dir / SUMMARY_FILENAME
    manifest_path = output_dir / MANIFEST_FILENAME
    missing = [
        path
        for path in (raw_path, summary_path, manifest_path, record_path)
        if not path.is_file()
    ]
    if missing:
        raise SystemExit("Missing browser evidence: " + ", ".join(str(path) for path in missing))

    payload = json.loads(raw_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    validate_payload(payload, require_final=require_final)
    for filename in (RAW_FILENAME, SUMMARY_FILENAME):
        expected = manifest.get("files", {}).get(filename)
        path = output_dir / filename
        if expected != file_record(path):
            raise SystemExit(f"Browser evidence checksum mismatch: {filename}")

    record_text = record_path.read_text(encoding="utf-8")
    if require_final and FINAL_RETEST_TOKEN in record_text:
        raise SystemExit("Browser record is provisional, not final-release evidence")
    if not require_final and payload["status"] == "passed_provisional":
        if FINAL_RETEST_TOKEN not in record_text:
            raise SystemExit("Provisional browser record does not preserve the final-release blocker")

    print(
        "Browser compatibility evidence OK: "
        f"{len(payload['results'])} engines, "
        f"{sum(len(item['checks']) for item in payload['results'])} checks, "
        f"status={payload['status']}"
    )
    return 0


def validate_payload(payload: dict[str, Any], *, require_final: bool) -> None:
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise SystemExit("Unexpected browser compatibility schema")
    expected_statuses = {"passed_final_release"} if require_final else {
        "passed_provisional",
        "passed_final_release",
    }
    if payload.get("status") not in expected_statuses:
        raise SystemExit(f"Browser compatibility status is not acceptable: {payload.get('status')}")
    results = payload.get("results", [])
    engines = [item.get("engine") for item in results]
    if engines != list(ENGINES):
        raise SystemExit(f"Browser evidence must cover {ENGINES}; found {engines}")
    for result in results:
        if result.get("status") != "passed":
            raise SystemExit(f"{result.get('engine')} browser result did not pass")
        checks = result.get("checks", [])
        check_ids = [item.get("id") for item in checks]
        if check_ids != list(REQUIRED_CHECKS):
            raise SystemExit(
                f"{result.get('engine')} check contract mismatch: {check_ids}"
            )
        if any(item.get("status") != "passed" for item in checks):
            raise SystemExit(f"{result.get('engine')} contains a failed check")
        if result.get("console_errors") or result.get("page_errors"):
            raise SystemExit(f"{result.get('engine')} contains browser runtime errors")
        if payload.get("status") == "passed_final_release":
            landing = next(
                (
                    item
                    for item in checks
                    if item.get("id") == "landing_and_keyboard"
                ),
                {},
            )
            observed_commit = (
                (landing.get("details") or {}).get("release_commit")
            )
            observed_ref = (
                (landing.get("details") or {}).get("release_ref")
            )
            expected_commit = (payload.get("release") or {}).get("commit")
            expected_ref = (payload.get("release") or {}).get("exact_tag")
            if observed_commit != expected_commit:
                raise SystemExit(
                    f"{result.get('engine')} tested deployment commit "
                    f"{observed_commit!r}, expected {expected_commit!r}"
                )
            if observed_ref != expected_ref:
                raise SystemExit(
                    f"{result.get('engine')} tested deployment ref "
                    f"{observed_ref!r}, expected {expected_ref!r}"
                )


def playwright_runner_js() -> str:
    return r"""
const { chromium, firefox, webkit } = require("playwright");
const fs = require("fs");
const os = require("os");

const baseUrl = process.env.BASE_URL;
const engine = process.env.ENGINE;
const resultPath = process.env.RESULT_PATH;
const expectedReleaseCommit = process.env.EXPECTED_RELEASE_COMMIT || "";
const expectedReleaseRef = process.env.EXPECTED_RELEASE_REF || "";
const browserType = { chromium, firefox, webkit }[engine];
const startedAt = Date.now();
const checks = [];
const consoleErrors = [];
const pageErrors = [];
const geneApiRequests = [];

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function requireText(text, snippet) {
  assert(text.includes(snippet), `Expected visible text to include: ${snippet}`);
}

async function recordCheck(id, callback) {
  const started = Date.now();
  try {
    const details = await callback();
    checks.push({
      id,
      status: "passed",
      duration_ms: Date.now() - started,
      details: details || {},
    });
  } catch (error) {
    checks.push({
      id,
      status: "failed",
      duration_ms: Date.now() - started,
      error: String(error && error.stack ? error.stack : error),
    });
    throw error;
  }
}

async function waitForImages(locator) {
  const count = await locator.count();
  assert(count > 0, "Expected at least one rendered image");
  for (let index = 0; index < count; index += 1) {
    await locator.nth(index).scrollIntoViewIfNeeded();
    await locator.nth(index).evaluate((image) => {
      if (image.complete && image.naturalWidth > 0) return;
      return new Promise((resolve, reject) => {
        const timer = window.setTimeout(
          () => reject(new Error(`Image timed out: ${image.src}`)),
          30000,
        );
        image.addEventListener("load", () => {
          window.clearTimeout(timer);
          resolve();
        }, { once: true });
        image.addEventListener("error", () => {
          window.clearTimeout(timer);
          reject(new Error(`Image failed: ${image.src}`));
        }, { once: true });
      });
    });
  }
}

async function assertVisual(locator, label) {
  await locator.waitFor({ state: "visible" });
  const box = await locator.boundingBox();
  assert(box && box.width >= 120 && box.height >= 80, `${label} has an invalid box`);
  const childMarks = await locator.locator("path, line, circle, rect, text, polyline").count();
  assert(childMarks >= 3, `${label} appears structurally blank`);
}

async function selectLihc(page) {
  const trigger = page.locator("button.cohort-trigger");
  await trigger.waitFor({ state: "visible" });
  const text = await trigger.innerText();
  if (!text.includes("Liver Hepatocellular")) {
    await trigger.click();
    await page.getByText("Liver Hepatocellular Carcinoma", { exact: true }).click();
  }
}

async function selectUvm(page) {
  const trigger = page.locator("button.cohort-trigger");
  await trigger.waitFor({ state: "visible" });
  const text = await trigger.innerText();
  if (!text.includes("Uveal Melanoma")) {
    await trigger.click();
    await page.getByText("Uveal Melanoma", { exact: true }).click();
  }
}

async function fillSuggestionQuery(input, suggestions, value) {
  await input.fill(value);
  try {
    await suggestions.waitFor({ state: "visible", timeout: 5000 });
  } catch {
    await input.focus();
    await input.press("End");
    await input.type("X");
    await input.press("Backspace");
    await suggestions.waitFor({ state: "visible", timeout: 15000 });
  }
}

async function addSuggestedGene(page, inputLabel) {
  const input = page.getByRole("textbox", { name: inputLabel });
  const suggestions = page.getByRole("listbox", { name: `${inputLabel} suggestions` });
  await fillSuggestionQuery(input, suggestions, "CDC");
  const option = suggestions.getByRole("option", { name: /CDC20/ }).first();
  try {
    await option.waitFor({ state: "visible", timeout: 10000 });
  } catch (error) {
    const diagnostic = {
      input_label: inputLabel,
      input_value: await input.inputValue(),
      suggestion_text: await suggestions.innerText().catch(() => "unavailable"),
      selected_chips: await page.locator(".gene-chip").allInnerTexts(),
      cohort_trigger: await page.locator("button.cohort-trigger").innerText().catch(() => "unavailable"),
      gene_api_requests: geneApiRequests.slice(-10),
    };
    throw new Error(`CDC20 suggestion unavailable: ${JSON.stringify(diagnostic)}; ${error}`);
  }
  const optionText = await option.innerText();
  requireText(optionText, "CDC20");
  await option.click();
  await page.locator(".gene-chip", { hasText: "CDC20" }).waitFor({ state: "visible" });
}

async function addSuggestedBap1(page, inputLabel) {
  const input = page.getByRole("textbox", { name: inputLabel });
  const suggestions = page.getByRole("listbox", { name: `${inputLabel} suggestions` });
  await fillSuggestionQuery(input, suggestions, "BAP");
  const option = suggestions.getByRole("option", { name: /BAP1/ }).first();
  await option.waitFor({ state: "visible", timeout: 10000 });
  await option.click();
  await page.locator(".gene-chip", { hasText: "BAP1" }).waitFor({ state: "visible" });
}

async function clickContinue(page, count) {
  for (let index = 0; index < count; index += 1) {
    const panel = page.locator(".analysis-step-panel").first();
    const previousPanelId = await panel.getAttribute("id");
    const button = page.getByRole("button", { name: /^Continue$/ });
    await button.waitFor({ state: "visible" });
    assert(!(await button.isDisabled()), `Continue is disabled at transition ${index + 1}`);
    await button.click();
    await page.waitForFunction(
      (previousId) => {
        const activePanel = document.querySelector(".analysis-step-panel");
        return activePanel && activePanel.id !== previousId;
      },
      previousPanelId,
    );
  }
}

async function navigate(page, label) {
  const button = page.getByRole("button", { name: new RegExp(`^${label}:`) }).first();
  await button.focus();
  assert(await button.evaluate((node) => node === document.activeElement), `${label} nav did not focus`);
  await button.press("Enter");
}

(async () => {
  if (!browserType) throw new Error(`Unknown engine: ${engine}`);
  let browser;
  let status = "passed";
  let fatalError = null;
  try {
    browser = await browserType.launch({ headless: true });
    const context = await browser.newContext({
      viewport: { width: 1440, height: 1100 },
      acceptDownloads: true,
    });
    const page = await context.newPage();
    page.setDefaultTimeout(60000);
    page.on("console", (message) => {
      if (message.type() === "error") consoleErrors.push(message.text());
    });
    page.on("pageerror", (error) => pageErrors.push(error.message));
    page.on("response", (response) => {
      if (response.url().includes("/genes?")) {
        geneApiRequests.push({ url: response.url(), status: response.status() });
      }
    });

    await recordCheck("landing_and_keyboard", async () => {
      const response = await page.goto(baseUrl, { waitUntil: "networkidle", timeout: 60000 });
      assert(response && response.ok(), `Landing response was ${response && response.status()}`);
      await page.getByText("TCGA-TRACE", { exact: true }).first().waitFor();
      const health = await page.evaluate(async () => {
        const response = await fetch("/tcga_explorer/api/v1/health");
        return { ok: response.ok, payload: await response.json() };
      });
      assert(health.ok && health.payload.status === "ok", "Health endpoint did not return ok");
      const releaseCommit = health.payload.release?.commit || "";
      const releaseRef = health.payload.release?.ref || "";
      if (expectedReleaseCommit) {
        assert(
          releaseCommit === expectedReleaseCommit,
          `Deployment commit ${releaseCommit || "missing"} does not match checked-out release ${expectedReleaseCommit}`,
        );
      }
      if (expectedReleaseRef) {
        assert(
          releaseRef === expectedReleaseRef,
          `Deployment ref ${releaseRef || "missing"} does not match checked-out tag ${expectedReleaseRef}`,
        );
      }
      await navigate(page, "Survival");
      await page.getByRole("heading", { name: "Survival analysis" }).waitFor();
      const nav = page.getByRole("button", { name: /^Survival:/ }).first();
      const outline = await nav.evaluate((node) => {
        const style = getComputedStyle(node);
        return { style: style.outlineStyle, width: style.outlineWidth };
      });
      assert(outline.style !== "none" && outline.width !== "0px", "Keyboard focus is not visible");
      await navigate(page, "Run history");
      await page.getByRole("heading", { name: "Exploratory run history", level: 1 }).waitFor();
      const recording = page.locator(".session-recording-switch input");
      assert(!(await recording.isChecked()), "Session recording is not opt-in");
      await recording.check({ force: true });
      await page.getByText("Recording on", { exact: true }).waitFor();
      await navigate(page, "Survival");
      return {
        app_version: health.payload.app_version,
        cohorts: health.payload.cohorts,
        release_commit: releaseCommit,
        release_ref: releaseRef,
      };
    });

    await recordCheck("survival_suggestions_analysis_and_download", async () => {
      await selectLihc(page);
      await clickContinue(page, 1);
      await addSuggestedGene(page, "Gene symbols");
      await clickContinue(page, 3);
      const externalEditor = page.locator("details.external-covariate-editor");
      await externalEditor.locator("summary").click();
      await externalEditor.locator('input[type="file"]').setInputFiles({
        name: "browser-contract.csv",
        mimeType: "text/csv",
        buffer: Buffer.from(
          "patient_id,smoke_group,smoke_measure\n"
          + "TCGA-AA-0001,Low,0.2\n"
          + "TCGA-AA-0002,High,0.4\n"
          + "TCGA-AA-0003,Low,0.6\n",
        ),
      });
      await externalEditor.getByText("3 patients · 2 variables · 0 selected").waitFor();
      requireText(await externalEditor.innerText(), "Use public TCGA participant barcodes only");
      const smokeGroup = externalEditor.locator(".external-covariate-definition", {
        hasText: "Smoke group",
      });
      await smokeGroup.getByLabel("Model type").selectOption("ordinal");
      requireText(await smokeGroup.innerText(), "Ordered levels, low to high");
      await smokeGroup.locator('input[type="checkbox"]').check({ force: true });
      await externalEditor.getByText("3 patients · 2 variables · 1 selected").waitFor();
      await externalEditor.getByRole("button", { name: "Remove" }).click();
      await externalEditor.getByText("Optional patient-level CSV").waitFor();
      await clickContinue(page, 1);
      const preview = page.getByRole("img", {
        name: "Illustrative Kaplan-Meier plot style preview",
      });
      await preview.waitFor({ state: "visible" });
      requireText(await preview.textContent(), "Time (days)");
      const runButton = page.getByRole("button", { name: /^Run analysis$/ });
      assert(!(await runButton.isDisabled()), "Run analysis is disabled after valid setup");
      await runButton.click();
      await page.locator(".continuous-analysis").waitFor({
        state: "visible",
        timeout: 240000,
      });
      await page.locator(".grouped-analysis-heading").waitFor({
        state: "visible",
        timeout: 240000,
      });
      await waitForImages(page.locator("img.km-plot, img.cox-forest-plot"));
      const resultText = await page.locator('[aria-label="Analysis result"]').innerText();
      for (const snippet of [
        "Continuous expression model",
        "Grouped Cox models",
        "Restricted mean survival time",
        "Events / parameter",
      ]) requireText(resultText, snippet);

      const exports = page.locator("details.result-downloads");
      await exports.locator("summary").click();
      const auditButton = exports.getByRole("button", { name: "Audit JSON" });
      const downloadPromise = page.waitForEvent("download", { timeout: 60000 });
      await auditButton.click();
      const download = await downloadPromise;
      const downloadPath = await download.path();
      assert(downloadPath, "Audit download has no local path");
      const bytes = fs.statSync(downloadPath).size;
      assert(bytes > 1000, `Audit download is unexpectedly small: ${bytes}`);

      const receiptButton = exports.getByRole("button", {
        name: "Signed receipt",
      });
      const receiptPromise = page.waitForEvent("download", {
        timeout: 60000,
      });
      await receiptButton.click();
      const receiptDownload = await receiptPromise;
      const receiptPath = await receiptDownload.path();
      assert(receiptPath, "Signed receipt download has no local path");
      const receiptBytes = fs.statSync(receiptPath).size;
      assert(
        receiptBytes > 500,
        `Signed receipt download is unexpectedly small: ${receiptBytes}`,
      );
      const receipt = JSON.parse(fs.readFileSync(receiptPath, "utf8"));
      assert(
        receipt.schema_version === "tcga-trace-server-attestation-v1",
        `Unexpected signed receipt schema: ${receipt.schema_version}`,
      );
      assert(
        receipt.signature?.algorithm === "Ed25519",
        `Unexpected signed receipt algorithm: ${receipt.signature?.algorithm}`,
      );
      return {
        audit_download_bytes: bytes,
        attestation_download_bytes: receiptBytes,
        attestation_schema: receipt.schema_version,
        attestation_algorithm: receipt.signature.algorithm,
        external_covariate_csv_ui: "passed",
      };
    });

    await recordCheck("competing_risk_analysis", async () => {
      await page.reload({ waitUntil: "networkidle", timeout: 60000 });
      await page.getByText("TCGA-TRACE", { exact: true }).first().waitFor();
      await navigate(page, "Survival");
      await selectUvm(page);
      await clickContinue(page, 1);
      await addSuggestedBap1(page, "Gene symbols");
      await clickContinue(page, 1);

      const dss = page.locator(".endpoint-grid button", {
        hasText: "Disease-specific survival",
      }).first();
      await dss.waitFor({ state: "visible" });
      assert(!(await dss.isDisabled()), "UVM DSS is disabled despite endpoint support");
      await dss.click();
      assert(
        await dss.evaluate((node) => node.classList.contains("selected")),
        "UVM DSS was not selected",
      );

      await clickContinue(page, 3);
      const square = page.locator(".plot-output-controls button", { hasText: /^Square$/ }).first();
      await square.click();
      const runButton = page.getByRole("button", { name: /^Run analysis$/ });
      assert(!(await runButton.isDisabled()), "Competing-risk run is disabled after valid setup");
      await runButton.click();

      const panel = page.locator(".competing-risk-analysis");
      await panel.waitFor({ state: "visible", timeout: 240000 });
      const panelText = (await panel.innerText()).replace(/\s+/g, " ");
      for (const snippet of [
        "Competing-risk analysis",
        "Subdistribution-based",
        "0 = censored",
        "1 = death from the index cancer",
        "2 = death from another cause",
        "Cumulative incidence at fixed horizons",
        "Grouped Fine-Gray models",
        "Continuous Fine-Gray models",
        "SHR (95% CI)",
        "not interchangeable",
      ]) requireText(panelText, snippet);

      const cifImage = panel.locator("img.cumulative-incidence-plot");
      await waitForImages(cifImage);
      const dimensions = await cifImage.evaluate((image) => ({
        width: image.naturalWidth,
        height: image.naturalHeight,
      }));
      assert(
        dimensions.width === dimensions.height && dimensions.width >= 1000,
        `Square CIF image has invalid dimensions: ${JSON.stringify(dimensions)}`,
      );

      const downloadPromise = page.waitForEvent("download", { timeout: 60000 });
      await panel.getByRole("button", { name: "PNG", exact: true }).click();
      const download = await downloadPromise;
      const downloadPath = await download.path();
      assert(downloadPath, "CIF PNG download has no local path");
      const bytes = fs.statSync(downloadPath).size;
      assert(bytes > 10000, `CIF PNG download is unexpectedly small: ${bytes}`);

      const overflow = await panel.evaluate((node) => ({
        scrollWidth: node.scrollWidth,
        clientWidth: node.clientWidth,
      }));
      assert(
        overflow.scrollWidth <= overflow.clientWidth + 2,
        `Competing-risk panel overflows horizontally: ${JSON.stringify(overflow)}`,
      );

      await page.setViewportSize({ width: 390, height: 844 });
      await panel.scrollIntoViewIfNeeded();
      const mobileLayout = await page.evaluate(() => {
        const panelNode = document.querySelector(".competing-risk-analysis");
        const image = panelNode?.querySelector("img.cumulative-incidence-plot");
        const panelBox = panelNode?.getBoundingClientRect();
        const imageBox = image?.getBoundingClientRect();
        return {
          viewportWidth: window.innerWidth,
          documentScrollWidth: document.documentElement.scrollWidth,
          panelWidth: panelBox?.width || 0,
          panelScrollWidth: panelNode?.scrollWidth || 0,
          imageWidth: imageBox?.width || 0,
        };
      });
      assert(
        mobileLayout.documentScrollWidth <= mobileLayout.viewportWidth + 2,
        `Mobile page overflows horizontally: ${JSON.stringify(mobileLayout)}`,
      );
      assert(
        mobileLayout.panelScrollWidth <= mobileLayout.panelWidth + 2,
        `Mobile competing-risk panel overflows: ${JSON.stringify(mobileLayout)}`,
      );
      assert(
        mobileLayout.imageWidth <= mobileLayout.panelWidth + 2,
        `Mobile CIF image escapes its panel: ${JSON.stringify(mobileLayout)}`,
      );
      await page.setViewportSize({ width: 1440, height: 1100 });

      return {
        endpoint: "DSS",
        cohort: "TCGA-UVM",
        cif_png_bytes: bytes,
        cif_natural_dimensions: dimensions,
        mobile_layout: mobileLayout,
      };
    });

    await recordCheck("compare_suggestions_preview_and_four_method_run", async () => {
      await navigate(page, "Compare");
      await page.getByRole("heading", { name: "Compare genes and cutpoints" }).waitFor();
      await selectLihc(page);
      await clickContinue(page, 1);
      await addSuggestedGene(page, "Genes to compare");
      await clickContinue(page, 1);
      for (const label of ["Maxstat", "Outer quartiles"]) {
        const button = page.locator(".compare-step-panel .method-grid button", {
          hasText: label,
        }).first();
        if (!(await button.evaluate((node) => node.classList.contains("selected")))) {
          await button.click();
        }
      }
      const selectedMethods = await page
        .locator(".compare-step-panel .method-grid button.selected")
        .allInnerTexts();
      assert(selectedMethods.length === 4, `Expected four selected methods: ${selectedMethods}`);
      assert(!selectedMethods.some((item) => item.includes("Percentile")), "Percentile entered publication panel");
      await clickContinue(page, 2);
      const previewText = await page.locator(".compare-preview-panel").innerText();
      assert(
        previewText.toLowerCase().includes("4 planned analyses"),
        `Compare preview did not expose four cells: ${previewText.slice(0, 1800)}`,
      );
      requireText(previewText, "Genes × cutpoint methods");
      const run = page.getByRole("button", { name: /^Run selected$/ });
      assert(!(await run.isDisabled()), "Compare run is disabled after valid setup");
      await run.click();
      await page.locator(".compare-continuous-reference").waitFor({
        state: "visible",
        timeout: 300000,
      });
      await page.locator(".robustness-summary").waitFor({
        state: "visible",
        timeout: 300000,
      });
      const cells = page.locator(".compare-plot-cell");
      await cells.nth(3).waitFor({ state: "visible", timeout: 300000 });
      assert(await cells.count() === 4, `Expected four completed Compare cells`);
      await waitForImages(cells.locator("img.compare-plot-thumb"));
      assert(
        (await page.locator(".robustness-summary").innerText())
          .toLowerCase()
          .includes("cutpoint analyses"),
        "Compare robustness summary is missing its cutpoint count",
      );
      return { selected_methods: selectedMethods, completed_cells: await cells.count() };
    });

    await recordCheck("exploratory_session_history", async () => {
      await navigate(page, "Run history");
      await page.getByRole("heading", { name: "Exploratory run history", level: 1 }).waitFor();
      const rows = page.locator(".session-run-table tbody tr");
      await rows.nth(2).waitFor({ state: "visible", timeout: 60000 });
      const recordedCount = await rows.count();
      assert(recordedCount >= 3, `Expected at least three recorded runs, observed ${recordedCount}`);
      const selected = page.locator(".session-run-table tbody input:checked");
      assert(await selected.count() === recordedCount, "Recorded runs were not selected by default");
      const exportButton = page.getByRole("button", { name: /^Export selected/ });
      assert(!(await exportButton.isDisabled()), "Session export is disabled after terminal runs");
      await exportButton.click();
      await page.getByRole("heading", { name: "Exploratory record completed" }).waitFor({
        state: "visible",
        timeout: 120000,
      });
      const result = page.locator(".session-export-result");
      const resultText = await result.innerText();
      for (const snippet of [
        "Continuous Cox hypotheses",
        "Grouped cutpoint sensitivities",
        "Two-signature interaction hypotheses",
        "BH + Bonferroni",
        "selected post hoc history",
      ]) requireText(resultText, snippet);

      const receiptPromise = page.waitForEvent("download", { timeout: 60000 });
      await result.getByRole("button", { name: "Signed receipt" }).click();
      const receiptDownload = await receiptPromise;
      const receiptPath = await receiptDownload.path();
      assert(receiptPath, "Session receipt download has no local path");
      const receipt = JSON.parse(fs.readFileSync(receiptPath, "utf8"));
      assert(
        receipt.payload?.subject?.type === "exploratory_session",
        `Unexpected session attestation subject: ${receipt.payload?.subject?.type}`,
      );

      await page.setViewportSize({ width: 390, height: 844 });
      const mobileLayout = await page.evaluate(() => ({
        viewportWidth: window.innerWidth,
        documentScrollWidth: document.documentElement.scrollWidth,
        sessionLabelHeight:
          document.querySelector(".session-label-field input")
            ?.getBoundingClientRect().height || 0,
      }));
      assert(
        mobileLayout.documentScrollWidth <= mobileLayout.viewportWidth + 2,
        `Session page overflows horizontally: ${JSON.stringify(mobileLayout)}`,
      );
      assert(
        mobileLayout.sessionLabelHeight > 0 && mobileLayout.sessionLabelHeight <= 56,
        `Session label input has invalid mobile height: ${JSON.stringify(mobileLayout)}`,
      );
      await page.setViewportSize({ width: 1440, height: 1100 });
      return {
        recorded_runs: recordedCount,
        report_id: await result.locator("code").first().innerText(),
        attestation_subject: receipt.payload.subject.type,
        mobile_layout: mobileLayout,
      };
    });

    await recordCheck("paper_examples", async () => {
      await navigate(page, "Examples");
      await page.getByRole("heading", { name: "Paper examples" }).waitFor();
      const evidenceSection = page.locator(".paper-example-section").first();
      await evidenceSection.waitFor({ state: "visible", timeout: 90000 });
      const text = await evidenceSection.innerText();
      const normalizedText = text.toLowerCase();
      requireText(normalizedText, "continuous marker profile");
      requireText(normalizedText, "cutpoint sensitivity");
      assert(!text.includes("Retained by reporting rule"), "Retired binary rule is visible");
      const images = evidenceSection.locator("img");
      if (await images.count()) await waitForImages(images);

      await page.locator(".paper-case-selector").getByRole("tab", {
        name: /EMP3/,
      }).click();
      await page.getByRole("heading", {
        name: "EMP3 in lower-grade glioma",
      }).waitFor();
      const continuousTemporal = page.locator(
        ".paper-continuous-reference .time-varying-effect-block",
      );
      await continuousTemporal.waitFor({ state: "visible" });
      const continuousTemporalText = await continuousTemporal.innerText();
      for (const snippet of [
        "Prespecified continuous effect over follow-up",
        "0-2 years HR",
        "After 2 years HR",
        "Late / early HR ratio",
        "56 / 69 events",
      ]) {
        requireText(continuousTemporalText, snippet);
      }

      await page.locator(".paper-method-tabs").getByRole("tab", {
        name: /^Median/,
      }).click();
      const groupedTemporal = page.locator(
        ".paper-case-explorer > .time-varying-effect-block",
      );
      await groupedTemporal.waitFor({ state: "visible" });
      requireText(
        await groupedTemporal.innerText(),
        "Prespecified follow-up-period diagnostic",
      );
      return {
        visible_case: "EMP3 in lower-grade glioma",
        temporal_diagnostics: await page.locator(
          ".paper-case-explorer .time-varying-effect-block",
        ).count(),
      };
    });

    await recordCheck("pancancer_and_dataset", async () => {
      await navigate(page, "Pan-cancer");
      const atlas = page.locator(".immune-atlas.analysis-result").first();
      await atlas.waitFor({ state: "visible", timeout: 90000 });
      requireText((await atlas.innerText()).toLowerCase(), "3,118");
      await assertVisual(
        atlas.getByRole("img", { name: "Immune gene recurrence by prognosis" }),
        "Pan-cancer recurrence plot",
      );
      await assertVisual(
        atlas.getByRole("img", { name: "Immune gene meta-analysis spectrum" }),
        "Pan-cancer spectrum plot",
      );

      await navigate(page, "Dataset");
      await page.getByRole("heading", { name: "TCGA data" }).waitFor();
      await page.getByRole("heading", { name: "Endpoint coverage" }).waitFor({
        timeout: 90000,
      });
      const datasetText = await page.locator(".summary-page").innerText();
      for (const snippet of [
        "Cohort landscape",
        "Metadata coverage",
        "Cohort table",
        "Summary CSV",
      ]) requireText(datasetText, snippet);
      const datasetVisuals = page.locator('.summary-page svg[role="img"]');
      assert(await datasetVisuals.count() >= 4, "Dataset Summary has too few rendered plots");
      for (let index = 0; index < Math.min(4, await datasetVisuals.count()); index += 1) {
        await assertVisual(datasetVisuals.nth(index), `Dataset plot ${index + 1}`);
      }
      const csvResponse = await context.request.get(
        new URL("api/v1/dataset/summary/download/csv", baseUrl).toString(),
      );
      assert(csvResponse.ok(), `Dataset CSV returned ${csvResponse.status()}`);
      assert((await csvResponse.body()).length > 1000, "Dataset CSV is unexpectedly small");
      return {
        dataset_svg_count: await datasetVisuals.count(),
        dataset_csv_bytes: (await csvResponse.body()).length,
      };
    });

    await recordCheck("reduced_motion", async () => {
      const reducedContext = await browser.newContext({
        viewport: { width: 1280, height: 900 },
        reducedMotion: "reduce",
      });
      const reducedPage = await reducedContext.newPage();
      await reducedPage.goto(baseUrl, { waitUntil: "networkidle", timeout: 60000 });
      const mediaMatches = await reducedPage.evaluate(
        () => matchMedia("(prefers-reduced-motion: reduce)").matches,
      );
      assert(mediaMatches, "Reduced-motion media query did not match");
      await reducedPage.getByRole("button", { name: /^Methods:/ }).first().click();
      await reducedPage.getByRole("heading", { name: "Methods", exact: true }).waitFor();
      const motion = await reducedPage.locator(".page-stage").evaluate((node) => {
        const style = getComputedStyle(node);
        return {
          animationDuration: style.animationDuration,
          transform: style.transform,
          scrollBehavior: getComputedStyle(document.documentElement).scrollBehavior,
        };
      });
      assert(motion.transform === "none", `Reduced-motion page transform is ${motion.transform}`);
      await reducedContext.close();
      return motion;
    });

    assert(consoleErrors.length === 0, `Console errors: ${consoleErrors.join(" | ")}`);
    assert(pageErrors.length === 0, `Page errors: ${pageErrors.join(" | ")}`);
    await context.close();
  } catch (error) {
    status = "failed";
    fatalError = String(error && error.stack ? error.stack : error);
  } finally {
    const result = {
      schema_version: "tcga-trace-browser-engine-v1",
      engine,
      browser_version: browser ? browser.version() : "unavailable",
      runtime_os: `${os.type()} ${os.release()} ${os.arch()}`,
      status,
      started_at: new Date(startedAt).toISOString(),
      duration_ms: Date.now() - startedAt,
      checks,
      console_errors: consoleErrors,
      page_errors: pageErrors,
      gene_api_requests: geneApiRequests,
      fatal_error: fatalError,
    };
    fs.writeFileSync(resultPath, JSON.stringify(result, null, 2) + "\n");
    if (browser) await browser.close();
    if (status !== "passed") process.exitCode = 1;
  }
})();
""".lstrip()


if __name__ == "__main__":
    sys.exit(main())
