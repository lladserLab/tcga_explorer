#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
METADATA_SCHEMA_VERSION = "tcga-trace-owner-metadata-v2"
MAIN_TEX = Path("manuscript/bioinformatics_app_note/main.tex")
SUPPLEMENT_TEX = Path("manuscript/bioinformatics_app_note/supplementary.tex")
FINAL_DECISIONS = Path("manuscript/bioinformatics_app_note/submission/final_submission_decisions.md")
COVER_LETTER = Path("manuscript/bioinformatics_app_note/submission/cover_letter_draft.md")
DATA_AVAILABILITY = Path(
    "manuscript/bioinformatics_app_note/submission/data_availability_statement.md"
)

REQUIRED_FIELDS = [
    "author_latex",
    "author_markdown",
    "affiliations_latex",
    "affiliations_markdown",
    "corresponding_author_name",
    "corresponding_email",
    "submitting_author_name",
    "submitting_author_orcid",
    "author_contributions_statement",
    "funding_statement",
    "conflict_of_interest_statement",
    "ai_use_disclosure",
    "software_license",
    "repository_url",
    "release_url_or_doi",
    "demo_or_access_statement",
    "maintenance_commitment",
    "support_owner_name",
    "support_email",
    "author_review_confirmation",
]

OPTIONAL_ROW_FIELDS = {
    "data_availability_note": "Data availability note",
    "apc_route": "Open-access APC or waiver route",
}
OPTIONAL_FIELDS = {*OPTIONAL_ROW_FIELDS, "corresponding_author_orcid"}

PLACEHOLDER_MARKERS = [
    "REPLACE_WITH",
    "TODO",
    "Author One",
    "Author Two",
    "Author Three",
    "Affiliation placeholder",
    "email@example.org",
    "Funding placeholder",
    "Conflict-of-interest statement placeholder",
    "CRediT contribution statement placeholder",
    "AI-use disclosure pending independent author review",
    "REPOSITORY-URL-PENDING",
    "ARCHIVE-DOI-PENDING",
    "TWO-YEAR-MAINTENANCE-COMMITMENT-PENDING",
    "LICENSE-PENDING",
    "placeholder",
    "[CORRESPONDING AUTHOR NAME AND EMAIL]",
    "[FINAL PUBLIC REPOSITORY URL]",
    "[SOFTWARE LICENSE]",
    "[ARCHIVAL DOI OR STABLE RELEASE URL]",
    "[PUBLIC DEMO URL OR REVIEWER ACCESS INSTRUCTIONS]",
    "[CORRESPONDING AUTHOR NAME]",
    "[SUBMITTING AUTHOR ORCID]",
    "[FINAL PERMITTED AI-USE DISCLOSURE AFTER INDEPENDENT AUTHOR REVIEW]",
    "[TWO-YEAR WEB-SERVICE MAINTENANCE COMMITMENT]",
    "[SUPPORT OWNER AND CONTACT]",
    "[AUTHOR REVIEW CONFIRMATION]",
]
MIN_LICENSE_CHARS = 100
LICENSE_PLACEHOLDER_MARKERS = PLACEHOLDER_MARKERS + [
    "Selected license",
    "Choose license",
    "License placeholder",
    "REPLACE_WITH_LICENSE",
]

CONTACT_RE = re.compile(r"^\\textbf\{Contact:\}.*$", re.MULTILINE)
ABSTRACT_AVAILABILITY_RE = re.compile(
    r"(\\textbf\{Availability and Implementation:\}\n)(.*?)(\n\\textbf\{Contact:\})",
    re.DOTALL,
)
AVAILABILITY_RE = re.compile(
    r"(\\section\*\{Data and Software Availability\}\n\n)(.*?)(\n\n\\section\*\{Author Contributions\})",
    re.DOTALL,
)
AUTHOR_CONTRIBUTIONS_RE = re.compile(
    r"(\\section\*\{Author Contributions\}\n\n)(.*?)(\n\n\\section\*\{Funding\})",
    re.DOTALL,
)
FUNDING_RE = re.compile(
    r"(\\section\*\{Funding\}\n\n)(.*?)(\n\n\\section\*\{Conflict of Interest\})",
    re.DOTALL,
)
CONFLICT_RE = re.compile(
    r"(\\section\*\{Conflict of Interest\}\n\n)(.*?)(\n\n\\section\*\{Acknowledgements\})",
    re.DOTALL,
)
ACKNOWLEDGEMENTS_RE = re.compile(
    r"(\\section\*\{Acknowledgements\}\n\n)(.*?)(\n\n\\bibliographystyle)",
    re.DOTALL,
)
SUPPLEMENT_AI_DISCLOSURE_RE = re.compile(
    r"(\\section\*\{AI Assistance Disclosure\}\n\n)(.*?)(\n\n\\clearpage)",
    re.DOTALL,
)
DATA_AVAILABILITY_STATEMENT_RE = re.compile(
    r"(## Prepared Manuscript Wording\n\n)(.*?)(\n\n## Notes For Final Submission)",
    re.DOTALL,
)
COVER_LETTER_SIGNATURE_RE = re.compile(r"(Sincerely,\n\n)(.*?)(\n?)\Z", re.DOTALL)
EXTERNAL_REFERENCE_RE = re.compile(r"^https?://|^doi:|^10\.\d{4,9}/", re.IGNORECASE)
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
ORCID_RE = re.compile(r"^\d{4}-\d{4}-\d{4}-\d{3}[\dX]$")
DATE_RE = re.compile(r"\b20\d{2}-\d{2}-\d{2}\b")


@dataclass(frozen=True)
class ApplyResult:
    changed_paths: list[Path]
    license_path: Path | None


def main() -> int:
    args = parse_args()
    root = ROOT
    metadata_path = Path(args.metadata)
    metadata_path = metadata_path if metadata_path.is_absolute() else root / metadata_path
    license_source = Path(args.license_source) if args.license_source else None
    try:
        metadata = load_metadata(metadata_path)
        result = apply_metadata(
            root,
            metadata,
            license_source=license_source,
            dry_run=args.dry_run,
            overwrite_license=args.overwrite_license,
        )
    except MetadataError as exc:
        print(f"Submission metadata application failed: {exc}", file=sys.stderr)
        return 1

    verb = "Would update" if args.dry_run else "Updated"
    for path in result.changed_paths:
        print(f"{verb} {path}")
    if result.license_path:
        license_verb = "Would copy" if args.dry_run else "Copied"
        print(f"{license_verb} license file to {result.license_path}")
    if not result.changed_paths and not result.license_path:
        print("Submission metadata already applied.")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Apply final owner-supplied submission metadata to the TCGA-TRACE "
            "Bioinformatics manuscript and decision tracker. The script does "
            "not choose authors, license or archive URL; it only validates and "
            "inserts values supplied in the metadata JSON."
        )
    )
    parser.add_argument("metadata", help="Path to an owner metadata JSON file.")
    parser.add_argument(
        "--license-source",
        help=(
            "Optional path to the final LICENSE text. If supplied, it is copied "
            "to the repository root as LICENSE."
        ),
    )
    parser.add_argument(
        "--overwrite-license",
        action="store_true",
        help="Allow --license-source to replace an existing different LICENSE file.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Validate and report changes without writing files.")
    return parser.parse_args()


def load_metadata(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise MetadataError(f"{path} does not exist")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise MetadataError(f"{path} is not valid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise MetadataError("metadata JSON must contain an object")
    return payload


def apply_metadata(
    root: Path,
    metadata: dict[str, Any],
    *,
    license_source: Path | None = None,
    dry_run: bool = False,
    overwrite_license: bool = False,
) -> ApplyResult:
    validated = validate_metadata(metadata)
    license_target = prepare_license(root, license_source, dry_run=dry_run, overwrite=overwrite_license)

    main_path = root / MAIN_TEX
    supplement_path = root / SUPPLEMENT_TEX
    decisions_path = root / FINAL_DECISIONS
    cover_path = root / COVER_LETTER
    data_availability_path = root / DATA_AVAILABILITY
    main_text = read_required_text(main_path)
    supplement_text = read_required_text(supplement_path)
    decisions_text = read_required_text(decisions_path)
    cover_text = read_required_text(cover_path)
    data_availability_text = read_required_text(data_availability_path)

    updated_main = update_main_tex(main_text, validated)
    updated_supplement = update_supplement_tex(supplement_text, validated)
    updated_decisions = update_final_decisions(decisions_text, validated)
    updated_cover = update_cover_letter(cover_text, validated)
    updated_data_availability = update_data_availability_statement(
        data_availability_text,
        validated,
    )

    changed_paths: list[Path] = []
    writes = [
        (main_path, updated_main),
        (supplement_path, updated_supplement),
        (decisions_path, updated_decisions),
        (cover_path, updated_cover),
        (data_availability_path, updated_data_availability),
    ]
    for path, new_text in writes:
        old_text = path.read_text(encoding="utf-8")
        if old_text != new_text:
            changed_paths.append(path.relative_to(root))
            if not dry_run:
                path.write_text(new_text, encoding="utf-8")

    return ApplyResult(changed_paths=changed_paths, license_path=license_target)


def validate_metadata(metadata: dict[str, Any]) -> dict[str, str]:
    if metadata.get("schema_version") != METADATA_SCHEMA_VERSION:
        raise MetadataError(
            "schema_version must be "
            f"{METADATA_SCHEMA_VERSION}; refresh the owner metadata template"
        )
    missing = [field for field in REQUIRED_FIELDS if field not in metadata]
    if missing:
        raise MetadataError("missing required field(s): " + ", ".join(missing))

    validated: dict[str, str] = {}
    for field in REQUIRED_FIELDS:
        value = metadata[field]
        if not isinstance(value, str):
            raise MetadataError(f"{field} must be a string")
        cleaned = value.strip()
        if not cleaned:
            raise MetadataError(f"{field} must not be empty")
        for marker in PLACEHOLDER_MARKERS:
            if marker.lower() in cleaned.lower():
                raise MetadataError(f"{field} still looks like a placeholder: {marker}")
        validated[field] = cleaned

    for field in OPTIONAL_FIELDS:
        value = metadata.get(field)
        if value is None:
            continue
        if not isinstance(value, str):
            raise MetadataError(f"{field} must be a string when supplied")
        cleaned = value.strip()
        if cleaned:
            for marker in PLACEHOLDER_MARKERS:
                if marker.lower() in cleaned.lower():
                    raise MetadataError(f"{field} still looks like a placeholder: {marker}")
            validated[field] = cleaned

    if not EMAIL_RE.match(validated["corresponding_email"]):
        raise MetadataError("corresponding_email must look like an email address")
    if not valid_orcid(validated["submitting_author_orcid"]):
        raise MetadataError("submitting_author_orcid must be a valid ORCID identifier")
    corresponding_orcid = validated.get("corresponding_author_orcid")
    if corresponding_orcid and not valid_orcid(corresponding_orcid):
        raise MetadataError(
            "corresponding_author_orcid must be empty or a valid ORCID identifier"
        )
    if not EMAIL_RE.match(validated["support_email"]):
        raise MetadataError("support_email must look like an email address")
    if not validated["repository_url"].startswith(("http://", "https://")):
        raise MetadataError("repository_url must be an HTTP(S) URL visible to reviewers")
    if not EXTERNAL_REFERENCE_RE.search(validated["release_url_or_doi"]):
        raise MetadataError("release_url_or_doi must be an HTTP(S) URL or DOI")
    if not re.search(
        r"(?:\b2\b|\btwo\b).{0,30}\byears?\b|\byears?\b.{0,30}(?:\b2\b|\btwo\b)",
        validated["maintenance_commitment"],
        re.IGNORECASE,
    ):
        raise MetadataError(
            "maintenance_commitment must explicitly state availability for at least two years"
        )
    review_confirmation = validated["author_review_confirmation"]
    if not DATE_RE.search(review_confirmation) or not re.search(
        r"\b(reviewed|rewrote|verified)\b",
        review_confirmation,
        re.IGNORECASE,
    ):
        raise MetadataError(
            "author_review_confirmation must name a completed review or rewrite "
            "and include its YYYY-MM-DD date"
        )

    return validated


def prepare_license(
    root: Path,
    license_source: Path | None,
    *,
    dry_run: bool,
    overwrite: bool,
) -> Path | None:
    target = root / "LICENSE"
    if license_source is None:
        if target.is_file():
            validate_license_file(target)
            return None
        if dry_run:
            return None
        raise MetadataError("root LICENSE file is missing; supply --license-source or add LICENSE first")

    source = license_source if license_source.is_absolute() else root / license_source
    if not source.is_file():
        raise MetadataError(f"license source {source} does not exist")
    validate_license_file(source)
    if target.exists() and source.resolve() != target.resolve():
        same_content = target.read_bytes() == source.read_bytes()
        if not same_content and not overwrite:
            raise MetadataError("LICENSE already exists and differs; use --overwrite-license to replace it")
        if same_content:
            return None
    if not dry_run and source.resolve() != target.resolve():
        shutil.copyfile(source, target)
    return target.relative_to(root)


def validate_license_file(path: Path) -> None:
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise MetadataError(f"license file {path} is not valid UTF-8") from exc
    if len(text.strip()) < MIN_LICENSE_CHARS:
        raise MetadataError(f"license file {path} is too short to be final license text")
    lowered = text.lower()
    for marker in LICENSE_PLACEHOLDER_MARKERS:
        if marker.lower() in lowered:
            raise MetadataError(f"license file {path} still contains placeholder marker: {marker}")


def read_required_text(path: Path) -> str:
    if not path.is_file():
        raise MetadataError(f"required file is missing: {path}")
    return path.read_text(encoding="utf-8")


def update_main_tex(text: str, metadata: dict[str, str]) -> str:
    author_block = render_author_block(metadata)
    text = replace_latex_command_block(text, "author", author_block)
    text = replace_section(
        ABSTRACT_AVAILABILITY_RE,
        text,
        render_abstract_availability(metadata),
        "abstract Availability and Implementation",
    )
    text = replace_once(
        CONTACT_RE,
        text,
        rf"\textbf{{Contact:}} \href{{mailto:{metadata['corresponding_email']}}}{{{metadata['corresponding_email']}}}.",
        "abstract contact line",
    )
    text = replace_section(
        AVAILABILITY_RE,
        text,
        render_availability(metadata),
        "Data and Software Availability",
    )
    text = replace_section(
        AUTHOR_CONTRIBUTIONS_RE,
        text,
        latex_sentence(metadata["author_contributions_statement"]),
        "Author Contributions",
    )
    text = replace_section(FUNDING_RE, text, latex_sentence(metadata["funding_statement"]), "Funding")
    text = replace_section(
        CONFLICT_RE,
        text,
        latex_sentence(metadata["conflict_of_interest_statement"]),
        "Conflict of Interest",
    )
    text = replace_section(
        ACKNOWLEDGEMENTS_RE,
        text,
        latex_sentence(metadata["ai_use_disclosure"]),
        "Acknowledgements",
    )
    return text


def update_supplement_tex(text: str, metadata: dict[str, str]) -> str:
    return replace_section(
        SUPPLEMENT_AI_DISCLOSURE_RE,
        text,
        latex_sentence(metadata["ai_use_disclosure"]),
        "supplementary AI Assistance Disclosure",
    )


def render_author_block(metadata: dict[str, str]) -> str:
    email = metadata["corresponding_email"]
    name = latex_escape(metadata["corresponding_author_name"])
    correspondence = (
        f"  Correspondence: {name}, "
        f"\\href{{mailto:{email}}}{{{email}}}"
    )
    orcid = metadata.get("corresponding_author_orcid")
    if orcid:
        correspondence += (
            f"; ORCID: \\href{{https://orcid.org/{orcid}}}{{{orcid}}}"
        )
    return (
        "\\author{\n"
        f"  {metadata['author_latex']}\\\\\n"
        f"  {metadata['affiliations_latex']}\\\\\n"
        f"{correspondence}\n"
        "}"
    )


def render_abstract_availability(metadata: dict[str, str]) -> str:
    repository = latex_url(metadata["repository_url"])
    release = latex_url(normalize_reference(metadata["release_url_or_doi"]))
    access = latex_url_or_text(metadata["demo_or_access_statement"])
    return (
        f"The registration-free HTTPS service is available at {access}. Source code "
        f"and reproducibility materials are openly available at {repository}; the "
        f"exact submitted release, compact benchmark outputs and hashed 33-cohort "
        f"data-snapshot manifest are archived on Zenodo at {release}. TCGA-TRACE is "
        "implemented in Python/FastAPI, React and R and containerized with Docker."
    )


def render_availability(metadata: dict[str, str]) -> str:
    repository = latex_url(metadata["repository_url"])
    release = latex_url(normalize_reference(metadata["release_url_or_doi"]))
    access = latex_url_or_text(metadata["demo_or_access_statement"])
    license_name = latex_escape(metadata["software_license"])
    return (
        f"A registration-free TCGA-TRACE instance is available at {access}, and the "
        f"source code is openly available at {repository} under the {license_name} "
        f"license. The exact submitted source release, Docker and test materials, "
        f"documentation, compact benchmark outputs, reconstruction bundles and hashed "
        f"33-cohort data-snapshot manifest are archived together on Zenodo at "
        f"{release}. Full TCGA expression matrices and participant exports are not "
        "redistributed through GitHub or Zenodo; they are regenerated from public "
        "GDC/TCGA and TCGA-CDR inputs by the documented Docker and "
        "reproducibility-bundle workflows. "
        f"{latex_sentence(metadata['maintenance_commitment'])} "
        f"Support is coordinated by {latex_escape(metadata['support_owner_name'])} "
        f"(\\href{{mailto:{metadata['support_email']}}}"
        f"{{{latex_escape(metadata['support_email'])}}})."
    )


def update_final_decisions(text: str, metadata: dict[str, str]) -> str:
    rows = {
        "Author list": metadata["author_markdown"],
        "Affiliations": metadata["affiliations_markdown"],
        "Corresponding author": (
            f"{metadata['corresponding_author_name']} "
            f"({metadata['corresponding_email']})"
        ),
        "Submitting author and ORCID": (
            f"{metadata['submitting_author_name']} "
            f"({metadata['submitting_author_orcid']})"
        ),
        "CRediT author contributions": metadata["author_contributions_statement"],
        "Funding statement": metadata["funding_statement"],
        "Conflict of interest": metadata["conflict_of_interest_statement"],
        "AI-use disclosure": metadata["ai_use_disclosure"],
        "Software license": metadata["software_license"],
        "Public or reviewer-accessible repository URL": metadata["repository_url"],
        "Stable release DOI or archive URL": metadata["release_url_or_doi"],
        "Public demo URL or Docker-only access statement": metadata["demo_or_access_statement"],
        "Two-year software and web-service availability commitment": metadata[
            "maintenance_commitment"
        ],
        "Support owner and contact": (
            f"{metadata['support_owner_name']} ({metadata['support_email']})"
        ),
        "Author-led scientific review and verification": metadata[
            "author_review_confirmation"
        ],
    }
    for field, row_name in OPTIONAL_ROW_FIELDS.items():
        if field in metadata:
            rows[row_name] = metadata[field]

    for field, value in rows.items():
        text = replace_markdown_row(text, field, value)
    return text


def update_cover_letter(text: str, metadata: dict[str, str]) -> str:
    rows = {
        "Corresponding author": f"{metadata['corresponding_author_name']} ({metadata['corresponding_email']})",
        "Submitting author and ORCID": (
            f"{metadata['submitting_author_name']} "
            f"({metadata['submitting_author_orcid']})"
        ),
        "Repository": metadata["repository_url"],
        "Software license": metadata["software_license"],
        "Release archive": metadata["release_url_or_doi"],
        "Reviewer access": metadata["demo_or_access_statement"],
        "AI-use disclosure": metadata["ai_use_disclosure"],
        "Maintenance commitment": metadata["maintenance_commitment"],
        "Support contact": (
            f"{metadata['support_owner_name']} ({metadata['support_email']})"
        ),
        "Author review": metadata["author_review_confirmation"],
    }
    for label, value in rows.items():
        text = replace_cover_letter_row(text, label, value)
    return replace_cover_letter_signature(text, metadata["corresponding_author_name"])


def update_data_availability_statement(
    text: str,
    metadata: dict[str, str],
) -> str:
    return replace_section(
        DATA_AVAILABILITY_STATEMENT_RE,
        text,
        render_data_availability_statement(metadata),
        "prepared Data Availability wording",
    )


def render_data_availability_statement(metadata: dict[str, str]) -> str:
    supplied = metadata.get("data_availability_note")
    if supplied:
        return supplied

    release = normalize_reference(metadata["release_url_or_doi"])
    return (
        "A registration-free HTTPS TCGA-TRACE instance is available at "
        f"`{metadata['demo_or_access_statement']}`. Source code is openly "
        f"available at `{metadata['repository_url']}` under the "
        f"{metadata['software_license']} license. The exact submitted source "
        "release, Docker and test materials, documentation, compact benchmark "
        "outputs, reconstruction bundles and "
        "`docs/publication/benchmark/data_snapshot_manifest.json` are archived "
        f"together at `{release}`. The manifest records the local TCGA/CDR/cache "
        "snapshot used for the benchmark claims, including count-matrix hashes "
        "for 33 cohorts and the TCGA-CDR checksum. Full TCGA expression matrices "
        "and participant exports are not redistributed through GitHub or the "
        "release archive; they are regenerated from public Genomic Data "
        "Commons/TCGA and TCGA-CDR inputs by the documented Docker and "
        "reproducibility-bundle workflows. "
        f"{metadata['maintenance_commitment'].rstrip('.')}. Support is coordinated "
        f"by {metadata['support_owner_name']} ({metadata['support_email']})."
    )


def replace_cover_letter_row(text: str, label: str, value: str) -> str:
    pattern = re.compile(rf"^- {re.escape(label)}: .*$", re.MULTILINE)
    matches = list(pattern.finditer(text))
    if len(matches) != 1:
        raise MetadataError(f"expected exactly one cover letter row for {label}, found {len(matches)}")
    match = matches[0]
    return text[: match.start()] + f"- {label}: {value}" + text[match.end() :]


def replace_cover_letter_signature(text: str, name: str) -> str:
    matches = list(COVER_LETTER_SIGNATURE_RE.finditer(text))
    if len(matches) != 1:
        raise MetadataError(f"expected exactly one cover letter signature, found {len(matches)}")
    match = matches[0]
    return text[: match.start(2)] + name + text[match.end(2) :]


def replace_markdown_row(text: str, field: str, value: str) -> str:
    pattern = re.compile(rf"^\| {re.escape(field)} \| (?P<middle>.*?) \| .*? \|$", re.MULTILINE)
    match = pattern.search(text)
    if not match:
        raise MetadataError(f"final_submission_decisions.md is missing row: {field}")
    replacement = f"| {field} | {match.group('middle')} | {markdown_cell(value)} |"
    return text[: match.start()] + replacement + text[match.end() :]


def replace_once(pattern: re.Pattern[str], text: str, replacement: str, label: str) -> str:
    matches = list(pattern.finditer(text))
    if len(matches) != 1:
        raise MetadataError(f"expected exactly one {label}, found {len(matches)}")
    match = matches[0]
    return text[: match.start()] + replacement + text[match.end() :]


def replace_latex_command_block(text: str, command: str, replacement: str) -> str:
    pattern = re.compile(rf"\\{re.escape(command)}\s*\{{")
    matches = list(pattern.finditer(text))
    if len(matches) != 1:
        raise MetadataError(f"expected exactly one \\{command}{{...}} block, found {len(matches)}")
    match = matches[0]
    open_brace = match.end() - 1
    close_brace = find_matching_brace(text, open_brace)
    return text[: match.start()] + replacement + text[close_brace + 1 :]


def find_matching_brace(text: str, open_brace: int) -> int:
    if open_brace >= len(text) or text[open_brace] != "{":
        raise MetadataError("internal error: expected opening brace")
    depth = 0
    for index in range(open_brace, len(text)):
        char = text[index]
        if char not in "{}" or is_escaped(text, index):
            continue
        if char == "{":
            depth += 1
        else:
            depth -= 1
            if depth == 0:
                return index
    raise MetadataError("unterminated LaTeX command block")


def is_escaped(text: str, index: int) -> bool:
    backslashes = 0
    cursor = index - 1
    while cursor >= 0 and text[cursor] == "\\":
        backslashes += 1
        cursor -= 1
    return backslashes % 2 == 1


def replace_section(pattern: re.Pattern[str], text: str, content: str, label: str) -> str:
    matches = list(pattern.finditer(text))
    if len(matches) != 1:
        raise MetadataError(f"expected exactly one {label} section, found {len(matches)}")
    match = matches[0]
    return text[: match.start(2)] + content + text[match.end(2) :]


def normalize_reference(value: str) -> str:
    cleaned = value.strip()
    if cleaned.lower().startswith("doi:"):
        return "https://doi.org/" + cleaned[4:].strip()
    if re.match(r"^10\.\d{4,9}/", cleaned):
        return "https://doi.org/" + cleaned
    return cleaned


def valid_orcid(value: str) -> bool:
    if not ORCID_RE.fullmatch(value):
        return False
    compact = value.replace("-", "")
    total = 0
    for char in compact[:15]:
        total = (total + int(char)) * 2
    remainder = total % 11
    result = (12 - remainder) % 11
    expected = "X" if result == 10 else str(result)
    return compact[-1] == expected


def latex_url(value: str) -> str:
    return "\\url{" + value.replace("}", "%7D").replace("{", "%7B") + "}"


def latex_url_or_text(value: str) -> str:
    cleaned = value.strip()
    if re.match(r"^https?://", cleaned, re.IGNORECASE):
        return latex_url(cleaned)
    return latex_escape(cleaned)


def latex_escape(value: str) -> str:
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    return "".join(replacements.get(char, char) for char in value)


def latex_sentence(value: str) -> str:
    escaped = latex_escape(value.strip())
    return escaped if escaped.endswith((".", "!", "?")) else escaped + "."


def markdown_cell(value: str) -> str:
    return " ".join(value.split()).replace("|", r"\|")


class MetadataError(Exception):
    pass


if __name__ == "__main__":
    sys.exit(main())
