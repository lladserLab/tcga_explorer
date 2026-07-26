#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

SCAN_FILES = [
    Path("manuscript/bioinformatics_app_note/main.tex"),
    Path("manuscript/bioinformatics_app_note/supplementary.tex"),
    Path("manuscript/bioinformatics_app_note/submission/browser_compatibility_record.md"),
    Path("manuscript/bioinformatics_app_note/submission/final_submission_decisions.md"),
    Path("manuscript/bioinformatics_app_note/submission/cover_letter_draft.md"),
]

PLACEHOLDER_PATTERNS = [
    "Author One",
    "Author Two",
    "Author Three",
    "Affiliation placeholder",
    "email@example.org",
    "Funding placeholder",
    "Conflict-of-interest statement placeholder",
    "CRediT contribution statement placeholder",
    "AI-use disclosure pending independent author review",
    "Detailed AI-assistance disclosure pending independent author rewrite and verification",
    "REPOSITORY-URL-PENDING",
    "ARCHIVE-DOI-PENDING",
    "THREE-YEAR-MAINTENANCE-COMMITMENT-PENDING",
    "| TODO",
    "[CORRESPONDING AUTHOR NAME AND EMAIL]",
    "[FINAL PUBLIC REPOSITORY URL]",
    "[SOFTWARE LICENSE]",
    "[ARCHIVAL DOI OR STABLE RELEASE URL]",
    "[PUBLIC DEMO URL OR REVIEWER ACCESS INSTRUCTIONS]",
    "[CORRESPONDING AUTHOR NAME]",
    "[SUBMITTING AUTHOR ORCID]",
    "[FINAL PERMITTED AI-USE DISCLOSURE AFTER INDEPENDENT AUTHOR REVIEW]",
    "[THREE-YEAR WEB-SERVICE MAINTENANCE COMMITMENT]",
    "FINAL_RELEASE_RETEST_REQUIRED",
]

LICENSE_FILES = [
    "LICENSE",
    "LICENSE.md",
    "LICENSE.txt",
    "COPYING",
    "COPYING.md",
    "COPYING.txt",
]
MIN_LICENSE_CHARS = 100
LICENSE_PLACEHOLDER_PATTERNS = PLACEHOLDER_PATTERNS + [
    "Selected license",
    "Choose license",
    "License placeholder",
    "REPLACE_WITH_LICENSE",
]

AVAILABILITY_SECTION_RE = re.compile(
    r"\\section\*\{Data and Software Availability\}(.*?)(?:\\section\*|\Z)",
    re.DOTALL,
)
EXTERNAL_AVAILABILITY_RE = re.compile(
    r"https?://|doi\.org|github\.com|zenodo|figshare|software\s+heritage",
    re.IGNORECASE,
)


def main() -> int:
    args = parse_args()
    blockers = collect_blockers(ROOT)
    if blockers:
        print("Submission metadata blockers:")
        for blocker in blockers:
            print(f"- {blocker}")
        print(
            "Owner-controlled fields remain unresolved. "
            "Use manuscript/bioinformatics_app_note/submission/final_submission_decisions.md "
            "as the handoff checklist."
        )
        return 1 if args.strict else 0
    print("Submission metadata OK: no owner placeholders, license file found and availability has an external reference.")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Check journal-submission metadata that cannot be inferred from tests: "
            "authors, affiliations, contact email, funding, conflicts, license and "
            "software availability references, AI disclosure and browser evidence."
        )
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero when any owner-controlled submission field remains unresolved.",
    )
    return parser.parse_args()


def collect_blockers(root: Path) -> list[str]:
    blockers: list[str] = []
    for relative_path in SCAN_FILES:
        path = root / relative_path
        if not path.exists():
            blockers.append(f"{relative_path}: missing required submission file")
            continue
        text = path.read_text(encoding="utf-8")
        blockers.extend(text_placeholder_blockers(relative_path, text))

    main_path = root / "manuscript/bioinformatics_app_note/main.tex"
    if main_path.exists():
        main_text = main_path.read_text(encoding="utf-8")
        availability = data_software_availability_section(main_text)
        if not availability:
            blockers.append("main.tex: missing Data and Software Availability section")
        elif not EXTERNAL_AVAILABILITY_RE.search(availability):
            blockers.append("main.tex: Data and Software Availability lacks repository/archive URL or DOI")

    license_blocker = license_file_blocker(root)
    if license_blocker:
        blockers.append(license_blocker)

    return blockers


def text_placeholder_blockers(relative_path: Path, text: str) -> list[str]:
    blockers: list[str] = []
    for pattern in PLACEHOLDER_PATTERNS:
        if pattern in text:
            blockers.append(f"{relative_path}: unresolved placeholder `{pattern}`")
    return blockers


def data_software_availability_section(text: str) -> str:
    match = AVAILABILITY_SECTION_RE.search(text)
    return match.group(1) if match else ""


def license_file_blocker(root: Path) -> str | None:
    paths = [root / name for name in LICENSE_FILES if (root / name).is_file()]
    if not paths:
        return "repository root: missing explicit LICENSE/COPYING file"

    path = paths[0]
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return f"{path.relative_to(root)}: license text is not valid UTF-8"

    if len(text.strip()) < MIN_LICENSE_CHARS:
        return f"{path.relative_to(root)}: license text is too short to be a final license file"

    lowered = text.lower()
    for pattern in LICENSE_PLACEHOLDER_PATTERNS:
        if pattern.lower() in lowered:
            return f"{path.relative_to(root)}: unresolved license placeholder `{pattern}`"

    return None


if __name__ == "__main__":
    sys.exit(main())
