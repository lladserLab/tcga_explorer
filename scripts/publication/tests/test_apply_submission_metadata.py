from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "apply_submission_metadata.py"
SPEC = importlib.util.spec_from_file_location("apply_submission_metadata", MODULE_PATH)
assert SPEC is not None
applier = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = applier
assert SPEC.loader is not None
SPEC.loader.exec_module(applier)


def metadata() -> dict[str, str]:
    return {
        "schema_version": "tcga-trace-owner-metadata-v2",
        "author_latex": "Ada Lovelace$^{1}$ and Grace Hopper$^{2}$",
        "author_markdown": "Ada Lovelace; Grace Hopper",
        "affiliations_latex": "$^{1}$Analytical Engines Institute; $^{2}$Compiler Lab",
        "affiliations_markdown": "Analytical Engines Institute; Compiler Lab",
        "corresponding_author_name": "Ada Lovelace",
        "corresponding_email": "ada@example.org",
        "corresponding_author_orcid": "0000-0002-1825-0097",
        "submitting_author_name": "Grace Hopper",
        "submitting_author_orcid": "0000-0002-1694-233X",
        "author_contributions_statement": "Ada Lovelace: Software, Methodology; Grace Hopper: Validation",
        "funding_statement": "No external funding was received",
        "conflict_of_interest_statement": "None declared",
        "ai_use_disclosure": "The authors used ExampleAI version 1 for code review and language editing; the researchers independently rewrote and verified all final code, analyses and prose",
        "software_license": "MIT",
        "repository_url": "https://github.com/example/tcga-trace",
        "release_url_or_doi": "10.5281/zenodo.1234567",
        "demo_or_access_statement": "https://apps.cienciavida.org/tcga_explorer/",
        "maintenance_commitment": "The authors will keep the software and public web service available for at least two years after publication",
        "support_owner_name": "Grace Hopper",
        "support_email": "support@example.org",
        "author_review_confirmation": "Grace Hopper reviewed and verified the final code, analyses and prose on 2026-07-26",
    }


def license_text() -> str:
    return (
        "MIT License\n\n"
        "Copyright (c) 2026 Example Authors\n\n"
        "Permission is hereby granted, free of charge, to any person obtaining a copy "
        "of this software and associated documentation files, to deal in the Software "
        "without restriction, subject to the conditions of the selected final license.\n"
    )


def write_fixture(root: Path) -> None:
    manuscript = root / "manuscript" / "bioinformatics_app_note"
    submission = manuscript / "submission"
    submission.mkdir(parents=True)
    (manuscript / "main.tex").write_text(
        "\\title{TCGA-TRACE}\n"
        "\\author{\n"
        "  Author One$^{1}$, Author Two$^{1}$, and Author Three$^{1}$\\\\\n"
        "  $^{1}$Affiliation placeholder\\\\\n"
        "  Correspondence: email@example.org\n"
        "}\n"
        "\\begin{abstract}\n"
        "\\textbf{Availability and Implementation:}\n"
        "Repository and release pending.\n"
        "\\textbf{Contact:} email@example.org.\n"
        "\\end{abstract}\n"
        "\\section*{Data and Software Availability}\n\n"
        "The TCGA-TRACE source repository supplied for review includes Docker deployment instructions.\n\n"
        "\\section*{Author Contributions}\n\n"
        "CRediT contribution statement placeholder.\n\n"
        "\\section*{Funding}\n\n"
        "Funding placeholder.\n\n"
        "\\section*{Conflict of Interest}\n\n"
        "Conflict-of-interest statement placeholder.\n\n"
        "\\section*{Acknowledgements}\n\n"
        "AI-use disclosure pending independent author review.\n\n"
        "\\bibliographystyle{plainnat}\n",
        encoding="utf-8",
    )
    (manuscript / "supplementary.tex").write_text(
        "\\section*{AI Assistance Disclosure}\n\n"
        "Detailed AI-assistance disclosure pending independent author rewrite and verification.\n\n"
        "\\clearpage\n"
        "\\bibliographystyle{plainnat}\n",
        encoding="utf-8",
    )
    (submission / "final_submission_decisions.md").write_text(
        "| Field | Current placeholder | Final value |\n"
        "| --- | --- | --- |\n"
        "| Author list | `Author One, Author Two, Author Three` | TODO |\n"
        "| Affiliations | `Affiliation placeholder` | TODO |\n"
        "| Corresponding author | `email@example.org` | TODO |\n"
        "| Submitting author and ORCID | Required | TODO |\n"
        "| CRediT author contributions | Required | TODO |\n"
        "| Funding statement | `Funding placeholder` | TODO |\n"
        "| Conflict of interest | `Conflict-of-interest statement placeholder` | TODO |\n"
        "| AI-use disclosure | Required | TODO |\n"
        "| Software license | Required | TODO |\n"
        "| Public or reviewer-accessible repository URL | Required | TODO |\n"
        "| Stable release DOI or archive URL | Required | TODO |\n"
        "| Public demo URL or Docker-only access statement | Required | Prepared wording. |\n"
        "| Two-year software and web-service availability commitment | Required | TODO |\n"
        "| Support owner and contact | Required | TODO |\n"
        "| Author-led scientific review and verification | Required | TODO |\n"
        "| Open-access APC or waiver route | Operational | TODO |\n",
        encoding="utf-8",
    )
    (submission / "cover_letter_draft.md").write_text(
        "Dear Editors,\n\n"
        "Before submission, replace the following placeholders:\n\n"
        "- Corresponding author: [CORRESPONDING AUTHOR NAME AND EMAIL]\n"
        "- Submitting author and ORCID: [SUBMITTING AUTHOR ORCID]\n"
        "- Repository: [FINAL PUBLIC REPOSITORY URL]\n"
        "- Software license: [SOFTWARE LICENSE]\n"
        "- Release archive: [ARCHIVAL DOI OR STABLE RELEASE URL]\n"
        "- Reviewer access: [PUBLIC DEMO URL OR REVIEWER ACCESS INSTRUCTIONS]\n\n"
        "- AI-use disclosure: [FINAL PERMITTED AI-USE DISCLOSURE AFTER INDEPENDENT AUTHOR REVIEW]\n"
        "- Maintenance commitment: [TWO-YEAR WEB-SERVICE MAINTENANCE COMMITMENT]\n"
        "- Support contact: [SUPPORT OWNER AND CONTACT]\n"
        "- Author review: [AUTHOR REVIEW CONFIRMATION]\n\n"
        "Sincerely,\n\n"
        "[CORRESPONDING AUTHOR NAME]\n",
        encoding="utf-8",
    )
    (submission / "data_availability_statement.md").write_text(
        "# Data Availability Statement\n\n"
        "## Prepared Manuscript Wording\n\n"
        "Source and release details pending.\n\n"
        "## Notes For Final Submission\n\n"
        "Review before upload.\n",
        encoding="utf-8",
    )


def test_validate_metadata_rejects_placeholders() -> None:
    payload = metadata()
    payload["author_latex"] = "REPLACE_WITH_LATEX_AUTHOR_LINE"

    try:
        applier.validate_metadata(payload)
    except applier.MetadataError as exc:
        assert "author_latex" in str(exc)
    else:
        raise AssertionError("placeholder metadata should fail validation")


def test_validate_metadata_rejects_stale_schema() -> None:
    payload = metadata()
    payload["schema_version"] = "tcga-trace-owner-metadata-v1"

    try:
        applier.validate_metadata(payload)
    except applier.MetadataError as exc:
        assert "refresh the owner metadata template" in str(exc)
    else:
        raise AssertionError("a stale owner metadata schema should fail validation")


def test_validate_metadata_requires_two_year_software_availability() -> None:
    payload = metadata()
    payload["maintenance_commitment"] = (
        "The authors will maintain the public web service for one year after publication"
    )

    try:
        applier.validate_metadata(payload)
    except applier.MetadataError as exc:
        assert "at least two years" in str(exc)
    else:
        raise AssertionError("a one-year availability commitment should fail validation")


def test_validate_metadata_requires_dated_author_review_confirmation() -> None:
    payload = metadata()
    payload["author_review_confirmation"] = (
        "Grace Hopper accepts responsibility for the final submission"
    )

    try:
        applier.validate_metadata(payload)
    except applier.MetadataError as exc:
        assert "YYYY-MM-DD" in str(exc)
    else:
        raise AssertionError("an undated author-review statement should fail validation")


def test_apply_metadata_updates_manuscript_and_decision_rows(tmp_path: Path) -> None:
    write_fixture(tmp_path)
    (tmp_path / "LICENSE").write_text(license_text(), encoding="utf-8")

    result = applier.apply_metadata(tmp_path, metadata())

    assert applier.MAIN_TEX in result.changed_paths
    assert applier.SUPPLEMENT_TEX in result.changed_paths
    assert applier.FINAL_DECISIONS in result.changed_paths
    assert applier.COVER_LETTER in result.changed_paths
    assert applier.DATA_AVAILABILITY in result.changed_paths
    main_text = (tmp_path / applier.MAIN_TEX).read_text(encoding="utf-8")
    supplement_text = (tmp_path / applier.SUPPLEMENT_TEX).read_text(encoding="utf-8")
    decisions = (tmp_path / applier.FINAL_DECISIONS).read_text(encoding="utf-8")
    cover = (tmp_path / applier.COVER_LETTER).read_text(encoding="utf-8")
    data_availability = (tmp_path / applier.DATA_AVAILABILITY).read_text(
        encoding="utf-8"
    )
    assert "Ada Lovelace" in main_text
    assert "Correspondence: Ada Lovelace" in main_text
    assert "\\url{https://apps.cienciavida.org/tcga_explorer/}" in main_text
    assert "\\url{https://github.com/example/tcga-trace}" in main_text
    assert "\\url{https://doi.org/10.5281/zenodo.1234567}" in main_text
    assert "Source code and reproducibility materials are openly available" in main_text
    assert "hashed 33-cohort data-snapshot manifest" in main_text
    assert "archived together on Zenodo" in main_text
    assert "0000-0002-1825-0097" in main_text
    assert "Ada Lovelace: Software, Methodology" in main_text
    assert "independently rewrote and verified all final code" in main_text
    assert "ExampleAI version 1" in supplement_text
    assert "independently rewrote and verified" in supplement_text
    assert "Funding placeholder" not in main_text
    assert "| Author list | `Author One, Author Two, Author Three` | Ada Lovelace; Grace Hopper |" in decisions
    assert "| Software license | Required | MIT |" in decisions
    assert (
        "| Submitting author and ORCID | Required | "
        "Grace Hopper (0000-0002-1694-233X) |"
    ) in decisions
    assert "| Stable release DOI or archive URL | Required | 10.5281/zenodo.1234567 |" in decisions
    assert "| Public demo URL or Docker-only access statement | Required | https://apps.cienciavida.org/tcga_explorer/ |" in decisions
    assert (
        "| Two-year software and web-service availability commitment | Required | "
        "The authors will keep"
    ) in decisions
    assert "| Support owner and contact | Required | Grace Hopper (support@example.org) |" in decisions
    assert "| Author-led scientific review and verification | Required | Grace Hopper reviewed" in decisions
    assert "Ada Lovelace (ada@example.org)" in cover
    assert "- Repository: https://github.com/example/tcga-trace" in cover
    assert "- Submitting author and ORCID: Grace Hopper (0000-0002-1694-233X)" in cover
    assert "- Release archive: 10.5281/zenodo.1234567" in cover
    assert "- Reviewer access: https://apps.cienciavida.org/tcga_explorer/" in cover
    assert "- Maintenance commitment: The authors will keep" in cover
    assert "- Support contact: Grace Hopper (support@example.org)" in cover
    assert "- Author review: Grace Hopper reviewed and verified" in cover
    assert "[SOFTWARE LICENSE]" not in cover
    assert "under the MIT license" in data_availability
    assert "support@example.org" in data_availability
    assert "at least two years" in data_availability


def test_apply_metadata_rerun_updates_cover_letter_values(tmp_path: Path) -> None:
    write_fixture(tmp_path)
    (tmp_path / "LICENSE").write_text(license_text(), encoding="utf-8")

    applier.apply_metadata(tmp_path, metadata())
    changed = metadata()
    changed["release_url_or_doi"] = "https://zenodo.org/records/999"
    changed["demo_or_access_statement"] = "Public demo: https://example.org/tcga-trace"
    result = applier.apply_metadata(tmp_path, changed)

    assert applier.COVER_LETTER in result.changed_paths
    assert applier.MAIN_TEX in result.changed_paths
    assert applier.DATA_AVAILABILITY in result.changed_paths
    assert applier.SUPPLEMENT_TEX not in result.changed_paths
    main_text = (tmp_path / applier.MAIN_TEX).read_text(encoding="utf-8")
    cover = (tmp_path / applier.COVER_LETTER).read_text(encoding="utf-8")
    assert main_text.count("\\author{") == 1
    assert (
        "Correspondence: Ada Lovelace, \\href{mailto:ada@example.org}{ada@example.org}; "
        "ORCID: \\href{https://orcid.org/0000-0002-1825-0097}{0000-0002-1825-0097}\n"
        "}\n"
        "\\begin{abstract}"
    ) in main_text
    assert "\\url{https://zenodo.org/records/999}" in main_text
    assert "- Release archive: https://zenodo.org/records/999" in cover
    assert "- Reviewer access: Public demo: https://example.org/tcga-trace" in cover


def test_submitting_orcid_is_not_misattributed_to_corresponding_author(
    tmp_path: Path,
) -> None:
    write_fixture(tmp_path)
    (tmp_path / "LICENSE").write_text(license_text(), encoding="utf-8")
    payload = metadata()
    payload["corresponding_author_orcid"] = None

    applier.apply_metadata(tmp_path, payload)

    main_text = (tmp_path / applier.MAIN_TEX).read_text(encoding="utf-8")
    decisions = (tmp_path / applier.FINAL_DECISIONS).read_text(encoding="utf-8")
    assert "Correspondence: Ada Lovelace" in main_text
    assert "ORCID:" not in main_text
    assert "Grace Hopper (0000-0002-1694-233X)" in decisions


def test_apply_metadata_rerun_with_same_values_is_noop(tmp_path: Path) -> None:
    write_fixture(tmp_path)
    (tmp_path / "LICENSE").write_text(license_text(), encoding="utf-8")

    applier.apply_metadata(tmp_path, metadata())
    result = applier.apply_metadata(tmp_path, metadata())

    assert result.changed_paths == []


def test_replace_latex_command_block_handles_nested_href_braces() -> None:
    text = (
        "\\title{TCGA-TRACE}\n"
        "\\author{\n"
        "  Ada Lovelace$^{1}$\\\\\n"
        "  Correspondence: Ada Lovelace, \\href{mailto:ada@example.org}{ada@example.org}\n"
        "}\n"
        "\\begin{document}\n"
    )

    updated = applier.replace_latex_command_block(text, "author", "\\author{Grace Hopper}")

    assert updated == "\\title{TCGA-TRACE}\n\\author{Grace Hopper}\n\\begin{document}\n"


def test_apply_metadata_dry_run_does_not_write_or_require_license(tmp_path: Path) -> None:
    write_fixture(tmp_path)
    original = (tmp_path / applier.MAIN_TEX).read_text(encoding="utf-8")

    result = applier.apply_metadata(tmp_path, metadata(), dry_run=True)

    assert result.changed_paths
    assert (tmp_path / applier.MAIN_TEX).read_text(encoding="utf-8") == original


def test_apply_metadata_can_copy_license_source(tmp_path: Path) -> None:
    write_fixture(tmp_path)
    license_source = tmp_path / "chosen_license.txt"
    license_source.write_text(license_text(), encoding="utf-8")

    result = applier.apply_metadata(tmp_path, metadata(), license_source=license_source)

    assert result.license_path == Path("LICENSE")
    assert (tmp_path / "LICENSE").read_text(encoding="utf-8") == license_text()


def test_apply_metadata_rejects_placeholder_license_source(tmp_path: Path) -> None:
    write_fixture(tmp_path)
    license_source = tmp_path / "chosen_license.txt"
    license_source.write_text("Selected license\n", encoding="utf-8")

    try:
        applier.apply_metadata(tmp_path, metadata(), license_source=license_source)
    except applier.MetadataError as exc:
        assert "license file" in str(exc)
    else:
        raise AssertionError("placeholder license source should fail validation")
