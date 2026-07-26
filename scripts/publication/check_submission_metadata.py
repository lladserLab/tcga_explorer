#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]

SCAN_FILES = [
    Path("manuscript/bioinformatics_app_note/main.tex"),
    Path("manuscript/bioinformatics_app_note/supplementary.tex"),
    Path("manuscript/bioinformatics_app_note/submission/browser_compatibility_record.md"),
    Path("manuscript/bioinformatics_app_note/submission/final_submission_decisions.md"),
    Path("manuscript/bioinformatics_app_note/submission/cover_letter_draft.md"),
    Path("manuscript/bioinformatics_app_note/submission/data_availability_statement.md"),
]

DECISION_LABELS = {
    "authorship": "Author list and affiliations",
    "correspondence": "Corresponding author and institutional email",
    "submitting_author": "Submitting author and ORCID",
    "contributions": "CRediT author contributions",
    "funding": "Funding statement",
    "conflicts": "Conflict-of-interest statement",
    "ai_disclosure": "Detailed AI-use disclosure",
    "author_review": "Independent author review and verification",
    "repository": "Public source repository",
    "license": "Complete software license",
    "release_archive": "Version-specific archive DOI or URL",
    "demo_access": "Public service or reviewer access",
    "maintenance": "Two-year software and service availability",
    "support": "Named support owner and contact",
    "browser_release": "Exact-tag HTTPS browser retest",
    "submission_files": "Required submission files",
    "availability": "Data and software availability statement",
}

PLACEHOLDER_RULES = [
    ("authorship", "Author One"),
    ("authorship", "Author Two"),
    ("authorship", "Author Three"),
    ("authorship", "Affiliation placeholder"),
    ("correspondence", "email@example.org"),
    ("funding", "Funding placeholder"),
    ("conflicts", "Conflict-of-interest statement placeholder"),
    ("contributions", "CRediT contribution statement placeholder"),
    ("ai_disclosure", "AI-use disclosure pending independent author review"),
    (
        "ai_disclosure",
        "Detailed AI-assistance disclosure pending independent author rewrite and verification",
    ),
    ("repository", "REPOSITORY-URL-PENDING"),
    ("release_archive", "ARCHIVE-DOI-PENDING"),
    ("maintenance", "TWO-YEAR-MAINTENANCE-COMMITMENT-PENDING"),
    ("license", "LICENSE-PENDING"),
    ("correspondence", "[CORRESPONDING AUTHOR NAME AND EMAIL]"),
    ("repository", "[FINAL PUBLIC REPOSITORY URL]"),
    ("license", "[SOFTWARE LICENSE]"),
    ("release_archive", "[ARCHIVAL DOI OR STABLE RELEASE URL]"),
    ("demo_access", "[PUBLIC DEMO URL OR REVIEWER ACCESS INSTRUCTIONS]"),
    ("correspondence", "[CORRESPONDING AUTHOR NAME]"),
    ("submitting_author", "[SUBMITTING AUTHOR ORCID]"),
    (
        "ai_disclosure",
        "[FINAL PERMITTED AI-USE DISCLOSURE AFTER INDEPENDENT AUTHOR REVIEW]",
    ),
    ("maintenance", "[TWO-YEAR WEB-SERVICE MAINTENANCE COMMITMENT]"),
    ("support", "[SUPPORT OWNER AND CONTACT]"),
    ("author_review", "[AUTHOR REVIEW CONFIRMATION]"),
    ("browser_release", "FINAL_RELEASE_RETEST_REQUIRED"),
]
PLACEHOLDER_PATTERNS = [pattern for _, pattern in PLACEHOLDER_RULES]

REQUIRED_DECISION_ROWS = {
    "Author list": "authorship",
    "Affiliations": "authorship",
    "Corresponding author": "correspondence",
    "Submitting author and ORCID": "submitting_author",
    "CRediT author contributions": "contributions",
    "Funding statement": "funding",
    "Conflict of interest": "conflicts",
    "AI-use disclosure": "ai_disclosure",
    "Software license": "license",
    "Public or reviewer-accessible repository URL": "repository",
    "Stable release DOI or archive URL": "release_archive",
    "Public demo URL or Docker-only access statement": "demo_access",
    "Two-year software and web-service availability commitment": "maintenance",
    "Support owner and contact": "support",
    "Author-led scientific review and verification": "author_review",
}
UNRESOLVED_ROW_RE = re.compile(
    r"(?:\bTODO\b|REPLACE_WITH|PENDING|placeholder)",
    re.IGNORECASE,
)

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


class MetadataBlocker:
    __slots__ = ("decision", "detail")

    def __init__(self, decision: str, detail: str) -> None:
        object.__setattr__(self, "decision", decision)
        object.__setattr__(self, "detail", detail)

    def __setattr__(self, name: str, value: str) -> None:
        raise AttributeError("MetadataBlocker is immutable")

    @property
    def label(self) -> str:
        return DECISION_LABELS[self.decision]


def main() -> int:
    args = parse_args()
    records = collect_blocker_records(ROOT)
    decisions = summarize_decisions(records)
    if args.json:
        print(
            json.dumps(
                {
                    "schema_version": "tcga-trace-owner-readiness-v2",
                    "decision_count": len(decisions),
                    "occurrence_count": len(records),
                    "decisions": decisions,
                },
                indent=2,
                sort_keys=True,
            )
        )
    elif records:
        print(
            "Submission metadata blockers: "
            f"{len(decisions)} unresolved decision(s), "
            f"{len(records)} occurrence(s)."
        )
        for decision in decisions:
            print(
                f"- {decision['label']} "
                f"({decision['occurrence_count']} occurrence(s))"
            )
            for occurrence in decision["occurrences"]:
                print(f"  - {occurrence}")
        print(
            "Use manuscript/bioinformatics_app_note/submission/"
            "final_submission_decisions.md as the handoff checklist."
        )
    else:
        print(
            "Submission metadata OK: no owner placeholders, license file "
            "found and availability has an external reference."
        )
    if records:
        return 1 if args.strict else 0
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
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit grouped owner decisions and their source occurrences as JSON.",
    )
    return parser.parse_args()


def collect_blockers(root: Path) -> list[str]:
    return [record.detail for record in collect_blocker_records(root)]


def collect_blocker_records(root: Path) -> list[MetadataBlocker]:
    blockers: list[MetadataBlocker] = []
    for relative_path in SCAN_FILES:
        path = root / relative_path
        if not path.exists():
            blockers.append(
                MetadataBlocker(
                    "submission_files",
                    f"{relative_path}: missing required submission file",
                )
            )
            continue
        text = path.read_text(encoding="utf-8")
        blockers.extend(text_placeholder_records(relative_path, text))
        if relative_path.name == "final_submission_decisions.md":
            blockers.extend(decision_row_blocker_records(relative_path, text))

    main_path = root / "manuscript/bioinformatics_app_note/main.tex"
    if main_path.exists():
        main_text = main_path.read_text(encoding="utf-8")
        availability = data_software_availability_section(main_text)
        if not availability:
            blockers.append(
                MetadataBlocker(
                    "availability",
                    "main.tex: missing Data and Software Availability section",
                )
            )
        elif not EXTERNAL_AVAILABILITY_RE.search(availability):
            blockers.append(
                MetadataBlocker(
                    "availability",
                    "main.tex: Data and Software Availability lacks "
                    "repository/archive URL or DOI",
                )
            )

    license_blocker = license_file_blocker(root)
    if license_blocker:
        blockers.append(MetadataBlocker("license", license_blocker))

    return blockers


def text_placeholder_blockers(relative_path: Path, text: str) -> list[str]:
    return [
        record.detail
        for record in text_placeholder_records(relative_path, text)
    ]


def text_placeholder_records(
    relative_path: Path,
    text: str,
) -> list[MetadataBlocker]:
    blockers: list[MetadataBlocker] = []
    for decision, pattern in PLACEHOLDER_RULES:
        if pattern in text:
            blockers.append(
                MetadataBlocker(
                    decision,
                    f"{relative_path}: unresolved placeholder `{pattern}`",
                )
            )
    return blockers


def decision_row_blocker_records(
    relative_path: Path,
    text: str,
) -> list[MetadataBlocker]:
    blockers: list[MetadataBlocker] = []
    rows = markdown_table_rows(text)
    for field, decision in REQUIRED_DECISION_ROWS.items():
        value = rows.get(field)
        if value is None:
            blockers.append(
                MetadataBlocker(
                    decision,
                    f"{relative_path}: missing required decision row `{field}`",
                )
            )
        elif UNRESOLVED_ROW_RE.search(value):
            blockers.append(
                MetadataBlocker(
                    decision,
                    f"{relative_path}: unresolved decision `{field}`",
                )
            )
    return blockers


def markdown_table_rows(text: str) -> dict[str, str]:
    rows: dict[str, str] = {}
    for line in text.splitlines():
        if not line.startswith("| ") or line.startswith("| ---"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) == 3 and cells[0] != "Field":
            rows[cells[0]] = cells[2]
    return rows


def summarize_decisions(
    records: list[MetadataBlocker],
) -> list[dict[str, Any]]:
    grouped: dict[str, list[str]] = {}
    for record in records:
        grouped.setdefault(record.decision, []).append(record.detail)
    return [
        {
            "decision": decision,
            "label": DECISION_LABELS[decision],
            "occurrence_count": len(grouped[decision]),
            "occurrences": grouped[decision],
        }
        for decision in sorted(grouped, key=lambda key: DECISION_LABELS[key])
    ]


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
