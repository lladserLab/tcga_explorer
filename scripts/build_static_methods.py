#!/usr/bin/env python3
"""Build the citable signature-scoring Methods page from one JSON contract."""

from __future__ import annotations

import argparse
import ast
import hashlib
import html
import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs" / "methods" / "signature_scoring.json"
MARKDOWN = ROOT / "docs" / "SIGNATURE_SCORING_METHODS.md"
PUBLIC_DIR = ROOT / "frontend" / "public" / "methods" / "signature-scoring"
HTML = PUBLIC_DIR / "index.html"
PUBLIC_MARKDOWN = PUBLIC_DIR / "methods.md"
PUBLIC_CONTRACT = PUBLIC_DIR / "contract.json"
PUBLIC_PARENT_MODE = 0o755
OUTPUT_MODE = 0o644
SCHEMAS = ROOT / "backend" / "app" / "schemas.py"
RENV_LOCK = ROOT / "backend" / "renv.lock"
SCORING_RUNTIME = ROOT / "backend" / "app" / "signature_scoring.py"
CAPABILITIES = ROOT / "backend" / "app" / "repository" / "capabilities.py"
R_ENGINE = ROOT / "backend" / "scripts" / "signature_scoring.R"


def esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def load_contract() -> tuple[dict[str, Any], bytes, str]:
    source_bytes = SOURCE.read_bytes()
    data = json.loads(source_bytes)
    digest = hashlib.sha256(source_bytes).hexdigest()
    validate_source(data)
    return data, source_bytes, digest


def validate_source(data: dict[str, Any]) -> None:
    required = {
        "schema_version",
        "title",
        "subtitle",
        "reviewed",
        "canonical_path",
        "app_help_path",
        "runtime",
        "implementation_contract",
        "summary",
        "workflow",
        "methods",
        "rules",
        "limitations",
        "references",
    }
    missing = sorted(required - set(data))
    if missing:
        raise ValueError(f"Methods contract is missing: {', '.join(missing)}")
    if data["canonical_path"] != "/tcga_explorer/methods/signature-scoring/":
        raise ValueError("The public Methods path is a stable contract.")
    if data["app_help_path"] != (
        "/tcga_explorer/?view=help#trace-guide-methods-signature-scoring"
    ):
        raise ValueError("The in-app help deep link must retain its view and fragment.")

    methods = data["methods"]
    identifiers = [method["id"] for method in methods]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("Method identifiers must be unique.")
    for method in methods:
        missing_method_fields = sorted(
            {
                "id",
                "label",
                "role",
                "status",
                "engine",
                "formula",
                "parameters",
                "direction",
                "universe",
                "cohort_dependence",
                "interpretation",
                "limits",
            }
            - set(method)
        )
        if missing_method_fields:
            raise ValueError(
                f"Method {method.get('id', '<unknown>')} is missing: "
                + ", ".join(missing_method_fields)
            )
        if method["status"] not in {"available", "boundary"}:
            raise ValueError(f"Unsupported status for {method['id']}.")

    implementation = data["implementation_contract"]
    documented_packages = {
        method["package"]["name"]: method["package"]["version"]
        for method in methods
        if method.get("package")
    }
    if documented_packages != implementation["packages"]:
        raise ValueError(
            "Package versions must have one value throughout the Methods source."
        )


def literal_assignments(path: Path) -> dict[str, Any]:
    """Read module-level literal constants without importing application code."""

    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    values: dict[str, Any] = {}
    for node in tree.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        if len(targets) != 1 or not isinstance(targets[0], ast.Name):
            continue
        try:
            values[targets[0].id] = ast.literal_eval(node.value)
        except (ValueError, TypeError):
            continue
    return values


def require_r_call_argument(
    script: str,
    function: str,
    argument: str,
    value: str,
) -> None:
    function_start = script.find(function)
    opening = script.find("(", function_start + len(function))
    arguments = None
    if function_start >= 0 and opening >= 0:
        depth = 0
        quote: str | None = None
        escaped = False
        for index in range(opening, len(script)):
            character = script[index]
            if quote:
                if escaped:
                    escaped = False
                elif character == "\\":
                    escaped = True
                elif character == quote:
                    quote = None
                continue
            if character in {'"', "'"}:
                quote = character
            elif character == "(":
                depth += 1
            elif character == ")":
                depth -= 1
                if depth == 0:
                    arguments = script[opening + 1 : index]
                    break
    if arguments is None or not re.search(
        rf"\b{re.escape(argument)}\s*=\s*{re.escape(value)}(?:\s*[,\n])",
        arguments + "\n",
    ):
        raise ValueError(
            f"R scoring drift: expected {function}(..., {argument} = {value})."
        )


def validate_runtime_contract(data: dict[str, Any]) -> None:
    schema_text = SCHEMAS.read_text(encoding="utf-8")
    match = re.search(r"SignatureMethod\s*=\s*Literal\[(.*?)\]", schema_text, re.S)
    if not match:
        raise ValueError("Could not read SignatureMethod from backend/app/schemas.py.")
    api_methods = set(re.findall(r'[\"\']([a-z0-9_]+)[\"\']', match.group(1)))
    documented = {
        method["id"] for method in data["methods"] if method["status"] == "available"
    }
    if api_methods != documented:
        raise ValueError(
            "Static Methods/API method drift: "
            f"documented={sorted(documented)}, API={sorted(api_methods)}"
        )

    lock = json.loads(RENV_LOCK.read_text(encoding="utf-8"))
    if lock.get("R", {}).get("Version") != data["runtime"]["r"]:
        raise ValueError("The documented R version differs from backend/renv.lock.")
    packages = lock.get("Packages", {})
    for method in data["methods"]:
        package = method.get("package")
        if not package:
            continue
        locked = packages.get(package["name"])
        if not locked:
            raise ValueError(f"{package['name']} is documented but absent from renv.lock.")
        if locked.get("Version") != package["version"]:
            raise ValueError(
                f"{package['name']} version drift: Methods={package['version']}, "
                f"renv.lock={locked.get('Version')}"
            )

    implementation = data["implementation_contract"]
    runtime = literal_assignments(SCORING_RUNTIME)
    capabilities = literal_assignments(CAPABILITIES)
    runtime_source = SCORING_RUNTIME.read_text(encoding="utf-8")
    if (
        runtime.get("MAX_MATRIX_ENTRIES") is None
        and "MAX_MATRIX_ENTRIES = RANK_SIGNATURE_MAXIMUM_MATRIX_ENTRIES"
        in runtime_source
    ):
        # The capability preflight and execution engine deliberately share one
        # limit. Resolve the imported alias instead of forcing a duplicate
        # numeric literal into the runtime module.
        runtime["MAX_MATRIX_ENTRIES"] = capabilities.get(
            "RANK_SIGNATURE_MAXIMUM_MATRIX_ENTRIES"
        )
    expected_runtime = {
        "SIGNATURE_SCORING_CONTRACT_VERSION": implementation[
            "backend_contract_version"
        ],
        "SIGNATURE_SCORING_ENGINE_SCHEMA": implementation["engine_schema"],
        "EXPECTED_PACKAGE_VERSIONS": {
            "singscore": implementation["packages"]["singscore"],
            "ssgsea": implementation["packages"]["GSVA"],
            "aucell": implementation["packages"]["AUCell"],
        },
        "MAX_MATRIX_ENTRIES": implementation["max_matrix_entries"],
        "SSGSEA_ALPHA": implementation["parameters"]["ssgsea"]["alpha"],
        "SSGSEA_MIN_SIZE": implementation["parameters"]["ssgsea"]["min_size"],
        "AUCELL_TOP_RANK_FRACTION": implementation["parameters"]["aucell"][
            "top_rank_fraction"
        ],
        "AUCELL_SEED": implementation["parameters"]["aucell"]["tie_seed_base"],
    }
    for name, expected in expected_runtime.items():
        if runtime.get(name) != expected:
            raise ValueError(
                f"Signature runtime drift for {name}: Methods={expected!r}, "
                f"backend={runtime.get(name)!r}."
            )
    if capabilities.get("RANK_SIGNATURE_MINIMUM_GENES") != implementation[
        "rank_minimum_genes"
    ]:
        raise ValueError("The documented broad-layer threshold differs from backend.")
    if capabilities.get(
        "RANK_SIGNATURE_MAXIMUM_MATRIX_ENTRIES"
    ) != implementation["max_matrix_entries"]:
        raise ValueError("The documented matrix-entry limit differs from backend.")

    r_script = R_ENGINE.read_text(encoding="utf-8")
    expected_schema = re.search(
        r'expected_schema\s*<-\s*"([^"]+)"',
        r_script,
    )
    if not expected_schema or expected_schema.group(1) != implementation["engine_schema"]:
        raise ValueError("The documented R engine schema differs from runtime.")

    sing = implementation["parameters"]["singscore"]
    require_r_call_argument(
        r_script, "singscore::rankGenes", "tiesMethod", f'"{sing["ties_method"]}"'
    )
    require_r_call_argument(
        r_script,
        "singscore::simpleScore",
        "centerScore",
        str(sing["center_score"]).upper(),
    )
    require_r_call_argument(
        r_script,
        "singscore::simpleScore",
        "knownDirection",
        str(sing["known_direction"]).upper(),
    )

    ssgsea = implementation["parameters"]["ssgsea"]
    for argument, value in {
        "minSize": str(ssgsea["min_size"]),
        "maxSize": str(ssgsea["max_size"]),
        "alpha": str(ssgsea["alpha"]),
        "normalize": str(ssgsea["normalize"]).upper(),
        "checkNA": f'"{ssgsea["check_na"]}"',
        "use": f'"{ssgsea["missing_value_policy"]}"',
    }.items():
        require_r_call_argument(r_script, "GSVA::ssgseaParam", argument, value)

    aucell = implementation["parameters"]["aucell"]
    for function, argument, value in [
        (
            "AUCell::AUCell_buildRankings",
            "splitByBlocks",
            str(aucell["split_by_blocks"]).upper(),
        ),
        (
            "AUCell::AUCell_buildRankings",
            "keepZeroesAsNA",
            str(aucell["keep_zeroes_as_na"]).upper(),
        ),
        (
            "AUCell::AUCell_calcAUC",
            "normAUC",
            str(aucell["normalize_auc"]).upper(),
        ),
    ]:
        require_r_call_argument(r_script, function, argument, value)


def render_markdown(data: dict[str, Any], digest: str) -> str:
    lines = [
        f"# {data['title']}",
        "",
        data["subtitle"],
        "",
        f"**Contract:** `{data['schema_version']}`  ",
        f"**Scoring engine contract:** `{data['implementation_contract']['backend_contract_version']}`  ",
        f"**Reviewed:** {data['reviewed']}  ",
        f"**Public HTML:** `https://apps.cienciavida.org{data['canonical_path']}`  ",
        f"**In-app explanation:** `https://apps.cienciavida.org{data['app_help_path']}`  ",
        f"**Source SHA-256:** `{digest}`",
        "",
    ]
    lines.extend(f"{paragraph}\n" for paragraph in data["summary"])
    lines.extend(
        [
            "## Recommended starting point",
            "",
            data["recommended"]["text"],
            "",
            "## What happens before a score is returned",
            "",
        ]
    )
    for index, step in enumerate(data["workflow"], start=1):
        lines.extend([f"{index}. **{step['title']}.** {step['text']}", ""])

    lines.extend(["## Notation", "", "| Symbol | Meaning |", "| --- | --- |"])
    lines.extend(
        f"| {item['term']} | {item['definition']} |" for item in data["notation"]
    )
    lines.extend(["", "## Scoring methods", ""])
    for method in data["methods"]:
        status = "Available" if method["status"] == "available" else "Not available"
        lines.extend(
            [
                f"### {method['label']} (`{method['id']}`)",
                "",
                f"**Status:** {status}  ",
                f"**Role:** {method['role']}  ",
                f"**Engine:** {method['engine']}  ",
                f"**Formula:** `{method['formula']}`  ",
                f"**Parameters:** {method['parameters']}  ",
                f"**Direction:** {method['direction']}  ",
                f"**Gene universe:** {method['universe']}  ",
                f"**Dependence on the run:** {method['cohort_dependence']}  ",
                f"**Interpretation:** {method['interpretation']}  ",
                f"**Limit:** {method['limits']}",
                "",
            ]
        )

    lines.extend(["## Rules shared by all methods", ""])
    for rule in data["rules"]:
        lines.extend([f"### {rule['title']}", "", rule["text"], ""])
    lines.extend(["## Limitations", ""])
    lines.extend(f"- {item}" for item in data["limitations"])
    lines.extend(["", "## References", ""])
    lines.extend(
        f"- [{reference['citation']}]({reference['url']})"
        for reference in data["references"]
    )
    return "\n".join(lines).rstrip() + "\n"


def method_html(method: dict[str, Any], recommended_id: str) -> str:
    status_label = "Available" if method["status"] == "available" else "Not available"
    package = method.get("package")
    package_html = ""
    if package:
        package_html = (
            "<span>"
            f"{esc(package['name'])} {esc(package['version'])}, "
            f"{esc(package['repository'])}"
            "</span>"
        )
    open_attribute = " open" if method["id"] == recommended_id else ""
    return f"""
      <details class="method" id="method-{esc(method['id'])}"{open_attribute}>
        <summary>
          <span class="method-title"><strong>{esc(method['label'])}</strong><code>{esc(method['id'])}</code></span>
          <span class="method-meta"><span class="status status-{esc(method['status'])}">{status_label}</span><span>{esc(method['role'])}</span></span>
        </summary>
        <div class="method-body">
          <div class="formula" aria-label="Score definition"><span>Score</span><code>{esc(method['formula'])}</code></div>
          <dl>
            <div><dt>Engine</dt><dd>{esc(method['engine'])}{package_html}</dd></div>
            <div><dt>Parameters</dt><dd>{esc(method['parameters'])}</dd></div>
            <div><dt>Direction</dt><dd>{esc(method['direction'])}</dd></div>
            <div><dt>Gene universe</dt><dd>{esc(method['universe'])}</dd></div>
            <div><dt>Dependence on the run</dt><dd>{esc(method['cohort_dependence'])}</dd></div>
            <div><dt>How to read it</dt><dd>{esc(method['interpretation'])}</dd></div>
            <div><dt>Important limit</dt><dd>{esc(method['limits'])}</dd></div>
          </dl>
        </div>
      </details>"""


def render_html(data: dict[str, Any], digest: str) -> str:
    workflow = "".join(
        f"<li><span>{index}</span><div><h3>{esc(step['title'])}</h3><p>{esc(step['text'])}</p></div></li>"
        for index, step in enumerate(data["workflow"], start=1)
    )
    notation = "".join(
        f"<tr><th scope=\"row\">{esc(item['term'])}</th><td>{esc(item['definition'])}</td></tr>"
        for item in data["notation"]
    )
    methods = "".join(
        method_html(method, data["recommended"]["method"])
        for method in data["methods"]
    )
    rules = "".join(
        f"<section class=\"rule\" id=\"rule-{slug(rule['title'])}\"><h3>{esc(rule['title'])}</h3><p>{esc(rule['text'])}</p></section>"
        for rule in data["rules"]
    )
    limits = "".join(f"<li>{esc(item)}</li>" for item in data["limitations"])
    references = "".join(
        f"<li id=\"ref-{esc(reference['id'])}\"><a href=\"{esc(reference['url'])}\">{esc(reference['citation'])}</a></li>"
        for reference in data["references"]
    )
    available_count = sum(
        method["status"] == "available" for method in data["methods"]
    )
    canonical = f"https://apps.cienciavida.org{data['canonical_path']}"
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="description" content="Citable TRACE Explorer methods for patient-level gene-signature scoring.">
  <meta name="trace-method-contract" content="{esc(data['schema_version'])}">
  <meta name="trace-source-sha256" content="{digest}">
  <link rel="canonical" href="{esc(canonical)}">
  <link rel="icon" href="../../favicon.ico" sizes="any">
  <title>{esc(data['title'])} | TRACE Explorer Methods</title>
  <style>
    :root {{
      color-scheme: light;
      --ink: oklch(24% .018 252);
      --ink-strong: oklch(17% .02 252);
      --muted: oklch(49% .018 245);
      --signal: oklch(43.5% .083 218);
      --signal-soft: oklch(94% .018 218);
      --canvas: oklch(96.5% .006 238);
      --paper: oklch(99% .003 245);
      --line: oklch(86% .011 240);
      --line-strong: oklch(71% .018 240);
      --warning: oklch(64% .13 70);
      --header: oklch(18% .022 252);
      --max: 1120px;
      font-family: "IBM Plex Sans", Aptos, ui-sans-serif, system-ui, sans-serif;
      font-synthesis: none;
    }}
    * {{ box-sizing: border-box; }}
    html {{ scroll-behavior: smooth; }}
    body {{
      margin: 0;
      color: var(--ink);
      background-color: var(--canvas);
      background-image: linear-gradient(var(--line) 1px, transparent 1px), linear-gradient(90deg, var(--line) 1px, transparent 1px);
      background-size: 28px 28px;
      font-size: 15px;
      line-height: 1.55;
    }}
    a {{ color: var(--signal); text-underline-offset: .18em; }}
    a:hover {{ text-decoration-thickness: 2px; }}
    :focus-visible {{ outline: 3px solid var(--warning); outline-offset: 3px; }}
    .skip-link {{ position: fixed; top: 10px; left: 10px; z-index: 10; transform: translateY(-160%); padding: 10px 14px; background: var(--paper); color: var(--ink-strong); border: 1px solid var(--line-strong); }}
    .skip-link:focus {{ transform: none; }}
    .topbar {{ background: var(--header); color: var(--paper); border-bottom: 1px solid oklch(32% .025 232); }}
    .topbar-inner {{ width: min(calc(100% - 32px), var(--max)); min-height: 68px; margin: auto; display: flex; align-items: center; justify-content: space-between; gap: 24px; }}
    .brand {{ display: flex; align-items: center; gap: 11px; color: inherit; text-decoration: none; font-weight: 680; }}
    .brand img {{ width: 30px; height: 30px; }}
    .topnav {{ display: flex; align-items: center; gap: 20px; }}
    .topnav a {{ color: oklch(88% .01 238); text-decoration: none; }}
    .topnav a:hover {{ color: var(--paper); text-decoration: underline; }}
    .hero {{ background: var(--paper); border-bottom: 1px solid var(--line); }}
    .hero-inner {{ width: min(calc(100% - 32px), var(--max)); margin: auto; padding: 64px 0 46px; }}
    .eyebrow {{ margin: 0 0 10px; color: var(--signal); font-size: 12px; font-weight: 780; }}
    h1 {{ max-width: 18ch; margin: 0; color: var(--ink-strong); font-size: 54px; line-height: 1.02; letter-spacing: -.035em; }}
    .lede {{ max-width: 67ch; margin: 22px 0 0; font-size: 18px; color: var(--muted); }}
    .contract-line {{ display: flex; flex-wrap: wrap; gap: 9px 24px; margin: 30px 0 0; padding-top: 18px; border-top: 1px solid var(--line); color: var(--muted); font-size: 13px; font-variant-numeric: tabular-nums; }}
    .contract-line strong {{ color: var(--ink); }}
    .layout {{ width: min(calc(100% - 32px), var(--max)); margin: 0 auto; display: grid; grid-template-columns: 218px minmax(0, 1fr); gap: 54px; padding: 42px 0 86px; align-items: start; }}
    .toc {{ position: sticky; top: 24px; padding: 4px 0; }}
    .toc h2 {{ margin: 0 0 12px; font-size: 13px; }}
    .toc ul {{ list-style: none; margin: 0; padding: 0; border-top: 1px solid var(--line-strong); }}
    .toc li {{ border-bottom: 1px solid var(--line); }}
    .toc a {{ display: block; padding: 10px 3px; color: var(--muted); text-decoration: none; }}
    .toc a:hover {{ color: var(--signal); }}
    main {{ min-width: 0; }}
    .section {{ scroll-margin-top: 20px; margin-bottom: 62px; }}
    .section > h2 {{ margin: 0 0 20px; color: var(--ink-strong); font-size: 24px; line-height: 1.18; }}
    .section-note {{ max-width: 68ch; margin: -7px 0 20px; color: var(--muted); }}
    .prose {{ max-width: 72ch; }}
    .prose p {{ margin: 0 0 14px; }}
    .recommendation {{ margin: 28px 0 0; padding: 20px; background: var(--signal-soft); border: 1px solid color-mix(in oklch, var(--signal) 34%, var(--line)); border-radius: 4px; }}
    .recommendation strong {{ display: block; margin-bottom: 5px; color: var(--ink-strong); }}
    .workflow {{ list-style: none; margin: 0; padding: 0; border-top: 1px solid var(--line-strong); }}
    .workflow li {{ display: grid; grid-template-columns: 34px minmax(0, 1fr); gap: 14px; padding: 19px 0; border-bottom: 1px solid var(--line); }}
    .workflow li > span {{ display: grid; place-items: center; width: 30px; height: 30px; border: 1px solid var(--signal); border-radius: 50%; color: var(--signal); font-weight: 720; font-variant-numeric: tabular-nums; }}
    .workflow h3, .rule h3 {{ margin: 0 0 5px; color: var(--ink-strong); font-size: 16px; }}
    .workflow p, .rule p {{ max-width: 72ch; margin: 0; }}
    .table-region {{ overflow-x: auto; border: 1px solid var(--line); background: var(--paper); }}
    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{ padding: 12px 14px; border-bottom: 1px solid var(--line); text-align: left; vertical-align: top; }}
    th {{ color: var(--ink-strong); font-weight: 700; }}
    tr:last-child > * {{ border-bottom: 0; }}
    .method-list {{ border-top: 1px solid var(--line-strong); }}
    .method {{ background: color-mix(in oklch, var(--paper) 92%, transparent); border-bottom: 1px solid var(--line-strong); }}
    .method summary {{ display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 18px; align-items: center; padding: 19px 4px; cursor: pointer; list-style-position: outside; }}
    .method summary::marker {{ color: var(--signal); }}
    .method-title, .method-meta {{ display: flex; align-items: center; flex-wrap: wrap; gap: 9px; }}
    .method-title strong {{ color: var(--ink-strong); font-size: 18px; }}
    code {{ font-family: ui-monospace, "SFMono-Regular", Consolas, monospace; font-size: .86em; }}
    .method-title code {{ padding: 3px 6px; color: var(--muted); background: var(--canvas); border: 1px solid var(--line); border-radius: 4px; }}
    .method-meta {{ justify-content: flex-end; color: var(--muted); font-size: 12px; }}
    .status {{ padding: 3px 7px; border: 1px solid var(--line-strong); border-radius: 999px; color: var(--ink); font-weight: 690; }}
    .status-available {{ border-color: color-mix(in oklch, var(--signal) 52%, var(--line)); color: var(--signal); }}
    .status-boundary {{ border-color: color-mix(in oklch, var(--warning) 55%, var(--line)); }}
    .method-body {{ padding: 2px 4px 26px; }}
    .formula {{ display: flex; align-items: baseline; gap: 13px; margin-bottom: 18px; padding: 13px 15px; background: var(--ink-strong); color: var(--paper); border-radius: 4px; overflow-x: auto; }}
    .formula span {{ flex: 0 0 auto; color: oklch(77% .055 218); font-size: 12px; font-weight: 750; }}
    .formula code {{ white-space: nowrap; font-size: 13px; }}
    dl {{ margin: 0; }}
    dl > div {{ display: grid; grid-template-columns: 154px minmax(0, 1fr); gap: 16px; padding: 10px 0; border-bottom: 1px solid var(--line); }}
    dl > div:last-child {{ border-bottom: 0; }}
    dt {{ color: var(--muted); font-size: 13px; font-weight: 700; }}
    dd {{ margin: 0; }}
    dd > span {{ display: block; margin-top: 3px; color: var(--muted); font-size: 13px; }}
    .rule {{ padding: 18px 0; border-top: 1px solid var(--line); }}
    .rule:first-of-type {{ border-top-color: var(--line-strong); }}
    .limitations {{ max-width: 72ch; padding-left: 21px; }}
    .limitations li {{ margin: 0 0 11px; padding-left: 5px; }}
    .references {{ max-width: 78ch; padding-left: 22px; }}
    .references li {{ margin: 0 0 13px; padding-left: 5px; }}
    .download-row {{ display: flex; flex-wrap: wrap; gap: 10px; margin-top: 25px; }}
    .download-row a {{ display: inline-flex; min-height: 44px; align-items: center; padding: 0 13px; border: 1px solid var(--line-strong); border-radius: 6px; background: var(--paper); text-decoration: none; font-weight: 650; }}
    footer {{ border-top: 1px solid var(--line); background: var(--paper); }}
    .footer-inner {{ width: min(calc(100% - 32px), var(--max)); margin: auto; padding: 28px 0 38px; color: var(--muted); font-size: 12px; }}
    .footer-inner code {{ overflow-wrap: anywhere; }}
    @media (max-width: 780px) {{
      .topbar-inner {{ min-height: 60px; }}
      .topnav a:first-child {{ display: none; }}
      .hero-inner {{ padding: 42px 0 34px; }}
      h1 {{ font-size: 40px; }}
      .layout {{ grid-template-columns: 1fr; gap: 36px; padding-top: 28px; }}
      .toc {{ position: static; }}
      .toc ul {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      .toc li:nth-child(odd) {{ border-right: 1px solid var(--line); }}
      .toc a {{ padding: 10px 8px; }}
      .method summary {{ grid-template-columns: 1fr; }}
      .method-meta {{ justify-content: flex-start; }}
      dl > div {{ grid-template-columns: 1fr; gap: 3px; }}
    }}
    @media (max-width: 430px) {{
      body {{ font-size: 14px; }}
      .topbar-inner, .hero-inner, .layout, .footer-inner {{ width: min(calc(100% - 24px), var(--max)); }}
      h1 {{ font-size: 34px; }}
      .brand span {{ max-width: 120px; line-height: 1.15; }}
      .topnav {{ gap: 11px; font-size: 13px; }}
      .toc ul {{ grid-template-columns: 1fr; }}
      .toc li:nth-child(odd) {{ border-right: 0; }}
      .method-title {{ align-items: flex-start; flex-direction: column; }}
    }}
    @media (prefers-reduced-motion: reduce) {{ html {{ scroll-behavior: auto; }} }}
    @media print {{
      body {{ background: var(--paper); color: var(--ink-strong); font-size: 10pt; }}
      .skip-link, .topnav, .toc, .download-row {{ display: none; }}
      .topbar {{ background: var(--paper); color: var(--ink-strong); }}
      .topbar-inner, .hero-inner, .layout, .footer-inner {{ width: 100%; }}
      .hero-inner {{ padding: 28px 0; }}
      .layout {{ display: block; padding: 24px 0; }}
      .section {{ break-inside: avoid; margin-bottom: 32px; }}
      details .method-body {{ display: block; }}
      a {{ color: inherit; text-decoration: none; }}
    }}
  </style>
</head>
<body>
  <a class="skip-link" href="#content">Skip to methods</a>
  <header class="topbar">
    <div class="topbar-inner">
      <a class="brand" href="../../" aria-label="TRACE Explorer home"><img src="../../brand/trace-mark.svg" alt=""><span>TRACE Explorer</span></a>
      <nav class="topnav" aria-label="Methods page links">
        <a href="../../?view=help#trace-guide-methods-signature-scoring">In-app explanation</a>
        <a href="methods.md">Markdown</a>
      </nav>
    </div>
  </header>
  <div class="hero">
    <div class="hero-inner">
      <p class="eyebrow">Methods · stable reference</p>
      <h1>{esc(data['title'])}</h1>
      <p class="lede">{esc(data['subtitle'])}</p>
      <div class="contract-line" aria-label="Method contract metadata">
        <span><strong>Contract</strong> {esc(data['schema_version'])}</span>
        <span><strong>Engine contract</strong> {esc(data['implementation_contract']['backend_contract_version'])}</span>
        <span><strong>Reviewed</strong> {esc(data['reviewed'])}</span>
        <span><strong>Runtime</strong> R {esc(data['runtime']['r'])} · Bioconductor {esc(data['runtime']['bioconductor'])}</span>
        <span><strong>Methods available</strong> {available_count}</span>
      </div>
    </div>
  </div>
  <div class="layout">
    <nav class="toc" aria-label="On this page">
      <h2>On this page</h2>
      <ul>
        <li><a href="#overview">Overview</a></li>
        <li><a href="#workflow">Before scoring</a></li>
        <li><a href="#methods">Methods</a></li>
        <li><a href="#rules">Shared rules</a></li>
        <li><a href="#limitations">Limitations</a></li>
        <li><a href="#references">References</a></li>
      </ul>
    </nav>
    <main id="content" tabindex="-1">
      <section class="section prose" id="overview">
        <h2>What this score means</h2>
        {''.join(f'<p>{esc(paragraph)}</p>' for paragraph in data['summary'])}
        <div class="recommendation"><strong>Recommended starting point</strong>{esc(data['recommended']['text'])}</div>
        <div class="download-row" aria-label="Download method definitions">
          <a href="methods.md" download>Download Markdown</a>
          <a href="contract.json" download>Download JSON contract</a>
        </div>
      </section>
      <section class="section" id="workflow">
        <h2>What happens before scoring</h2>
        <ol class="workflow">{workflow}</ol>
      </section>
      <section class="section" id="notation">
        <h2>Notation</h2>
        <div class="table-region" tabindex="0" role="region" aria-label="Score notation table">
          <table><thead><tr><th scope="col">Symbol</th><th scope="col">Meaning</th></tr></thead><tbody>{notation}</tbody></table>
        </div>
      </section>
      <section class="section" id="methods">
        <h2>Scoring methods</h2>
        <p class="section-note">Choose the method that matches how the score will be used. Expand a row for its exact calculation, population dependence and limits.</p>
        <div class="method-list">{methods}</div>
      </section>
      <section class="section" id="rules">
        <h2>Rules shared by all methods</h2>
        {rules}
      </section>
      <section class="section" id="limitations">
        <h2>What these scores cannot establish</h2>
        <ul class="limitations">{limits}</ul>
      </section>
      <section class="section" id="references">
        <h2>References</h2>
        <ol class="references">{references}</ol>
      </section>
    </main>
  </div>
  <footer><div class="footer-inner">Generated from <code>docs/methods/signature_scoring.json</code> · Source SHA-256 <code>{digest}</code></div></footer>
</body>
</html>
"""


def expected_outputs(data: dict[str, Any], source_bytes: bytes, digest: str) -> dict[Path, bytes]:
    markdown = render_markdown(data, digest).encode("utf-8")
    return {
        MARKDOWN: markdown,
        HTML: render_html(data, digest).encode("utf-8"),
        PUBLIC_MARKDOWN: markdown,
        PUBLIC_CONTRACT: source_bytes,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if generated files, API methods or package versions have drifted.",
    )
    args = parser.parse_args()
    data, source_bytes, digest = load_contract()
    outputs = expected_outputs(data, source_bytes, digest)

    if args.check:
        validate_runtime_contract(data)
        drift = [
            str(path.relative_to(ROOT))
            for path, content in outputs.items()
            if not path.exists()
            or path.read_bytes() != content
            or (path.stat().st_mode & 0o777) != OUTPUT_MODE
        ]
        drift.extend(
            f"{directory.relative_to(ROOT)}/"
            for directory in (PUBLIC_DIR.parent, PUBLIC_DIR)
            if not directory.is_dir()
            or (directory.stat().st_mode & 0o777) != PUBLIC_PARENT_MODE
        )
        if drift:
            raise SystemExit("Static Methods drift: " + ", ".join(drift))
        print(
            f"Static Methods verified: {data['schema_version']} "
            f"({sum(method['status'] == 'available' for method in data['methods'])} methods)."
        )
        return 0

    for directory in (PUBLIC_DIR.parent, PUBLIC_DIR):
        directory.mkdir(parents=True, exist_ok=True)
        directory.chmod(PUBLIC_PARENT_MODE)
    for path, content in outputs.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        path.chmod(OUTPUT_MODE)
    print(f"Generated {len(outputs)} files from {SOURCE.relative_to(ROOT)}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
