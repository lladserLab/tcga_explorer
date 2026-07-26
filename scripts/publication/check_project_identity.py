#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
CANONICAL_NAME = "TCGA-TRACE"
CANONICAL_PDFS = (
    "tcga-trace-bioinformatics-application-note.pdf",
    "tcga-trace-bioinformatics-supplement.pdf",
    "tcga-trace-bioinformatics-oup-preview.pdf",
)
VISIBLE_SURFACES = (
    Path("README.md"),
    Path("CHANGELOG.md"),
    Path("frontend/src/main.jsx"),
    Path("frontend/index.html"),
    Path("docs/API.md"),
    Path("docs/API_ES.md"),
    Path("manuscript/bioinformatics_app_note/main.tex"),
    Path("manuscript/bioinformatics_app_note/supplementary.tex"),
)
PACKAGE_SURFACES = (
    Path("manuscript/bioinformatics_app_note/Makefile"),
    Path("scripts/publication/build_submission_archive.py"),
    Path("scripts/publication/check_submission_artifacts.py"),
    Path("scripts/publication/finalize_submission_package.py"),
    Path("scripts/publication/verify_submission_archive.py"),
)
LEGACY_DISPLAY_NAMES = ("TCGA Explorer", "TCGA KM Explorer")
LEGACY_PDF_PREFIX = "tcga_explorer_bioinformatics_"


def main() -> int:
    blockers = collect_blockers(ROOT)
    if blockers:
        print("TCGA-TRACE identity blockers:")
        for blocker in blockers:
            print(f"- {blocker}")
        return 1
    print(
        "TCGA-TRACE identity OK: canonical display/package names are in use; "
        "/tcga_explorer is documented as a legacy compatibility route."
    )
    return 0


def collect_blockers(root: Path) -> list[str]:
    blockers: list[str] = []
    identity_path = root / "docs/PROJECT_IDENTITY.md"
    identity_text = read_text(identity_path, blockers)
    required_identity_phrases = (
        CANONICAL_NAME,
        "/tcga_explorer",
        "legacy identifiers",
        "not the product name",
    )
    for phrase in required_identity_phrases:
        if phrase.lower() not in identity_text.lower():
            blockers.append(f"docs/PROJECT_IDENTITY.md does not define {phrase!r}")

    for relative in VISIBLE_SURFACES:
        text = read_text(root / relative, blockers)
        if CANONICAL_NAME not in text:
            blockers.append(f"{relative} does not contain the canonical name {CANONICAL_NAME}")
        for legacy_name in LEGACY_DISPLAY_NAMES:
            if legacy_name in text:
                blockers.append(f"{relative} exposes legacy display name {legacy_name!r}")

    package_text = "\n".join(
        read_text(root / relative, blockers) for relative in PACKAGE_SURFACES
    )
    for filename in CANONICAL_PDFS:
        if filename not in package_text:
            blockers.append(f"canonical package filename is not wired: {filename}")
    if LEGACY_PDF_PREFIX in package_text:
        blockers.append(f"package surfaces still use legacy PDF prefix {LEGACY_PDF_PREFIX}")
    if '"project_name": "TCGA-TRACE"' not in package_text:
        blockers.append("review archive manifest does not declare project_name TCGA-TRACE")

    try:
        frontend_package = json.loads(
            (root / "frontend/package.json").read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError) as exc:
        blockers.append(f"could not read frontend/package.json: {exc}")
    else:
        if frontend_package.get("name") != "tcga-trace-frontend":
            blockers.append("frontend package name is not tcga-trace-frontend")

    config_text = read_text(root / "backend/app/config.py", blockers)
    if 'app_name: str = "TCGA-TRACE"' not in config_text:
        blockers.append("backend default app_name is not TCGA-TRACE")
    return blockers


def read_text(path: Path, blockers: list[str]) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        blockers.append(f"could not read {path}: {exc}")
        return ""


if __name__ == "__main__":
    sys.exit(main())
