from __future__ import annotations

import importlib.util
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "check_submission_metadata.py"
SPEC = importlib.util.spec_from_file_location("check_submission_metadata", MODULE_PATH)
assert SPEC is not None
checker = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(checker)


def license_text() -> str:
    return (
        "MIT License\n\n"
        "Copyright (c) 2026 Example Authors\n\n"
        "Permission is hereby granted, free of charge, to any person obtaining a copy "
        "of this software and associated documentation files, to deal in the Software "
        "without restriction, subject to the conditions of the selected final license.\n"
    )


def test_text_placeholder_blockers_reports_owner_placeholders() -> None:
    blockers = checker.text_placeholder_blockers(
        Path("main.tex"),
        "Author One\nAffiliation placeholder\nCorrespondence: email@example.org",
    )

    assert "main.tex: unresolved placeholder `Author One`" in blockers
    assert "main.tex: unresolved placeholder `Affiliation placeholder`" in blockers
    assert "main.tex: unresolved placeholder `email@example.org`" in blockers


def test_text_placeholder_blockers_preserves_final_browser_retest() -> None:
    blockers = checker.text_placeholder_blockers(
        Path("browser_compatibility_record.md"),
        "Status: provisional; FINAL_RELEASE_RETEST_REQUIRED.",
    )

    assert blockers == [
        "browser_compatibility_record.md: unresolved placeholder "
        "`FINAL_RELEASE_RETEST_REQUIRED`"
    ]


def test_decision_summary_groups_duplicate_occurrences() -> None:
    records = [
        checker.MetadataBlocker("release_archive", "main.tex: DOI pending"),
        checker.MetadataBlocker("release_archive", "cover.md: DOI pending"),
        checker.MetadataBlocker("license", "LICENSE missing"),
    ]

    summary = checker.summarize_decisions(records)

    assert len(summary) == 2
    release = next(item for item in summary if item["decision"] == "release_archive")
    assert release["occurrence_count"] == 2
    assert release["occurrences"] == [
        "main.tex: DOI pending",
        "cover.md: DOI pending",
    ]


def test_availability_section_requires_external_reference() -> None:
    text = (
        "\\section*{Data and Software Availability}\n"
        "The source repository is supplied for review.\n"
        "\\section*{Funding}\n"
    )

    availability = checker.data_software_availability_section(text)

    assert availability.strip() == "The source repository is supplied for review."
    assert not checker.EXTERNAL_AVAILABILITY_RE.search(availability)


def test_collect_blockers_passes_complete_minimal_fixture(tmp_path: Path) -> None:
    manuscript = tmp_path / "manuscript" / "bioinformatics_app_note"
    submission = manuscript / "submission"
    submission.mkdir(parents=True)
    (manuscript / "main.tex").write_text(
        "\\section*{Data and Software Availability}\n"
        "Source code is archived at https://example.org/release and licensed under MIT.\n"
        "\\section*{Funding}\n"
        "No external funding.\n"
        "\\section*{Conflict of Interest}\n"
        "None declared.\n",
        encoding="utf-8",
    )
    (manuscript / "supplementary.tex").write_text(
        "\\section*{AI Assistance Disclosure}\n"
        "The authors used ExampleAI for language editing and independently verified the final text.\n",
        encoding="utf-8",
    )
    (submission / "browser_compatibility_record.md").write_text(
        "| Engine | Browser | Result |\n"
        "| --- | --- | --- |\n"
        "| Chromium | Chrome 130 | passed |\n"
        "| Gecko | Firefox 132 | passed |\n"
        "| WebKit | Safari 18 | passed |\n",
        encoding="utf-8",
    )
    (submission / "final_submission_decisions.md").write_text(
        "| Field | Current placeholder | Final value |\n"
        "| --- | --- | --- |\n"
        "| Author list | Required | Final authors |\n"
        "| Affiliations | Required | Final affiliations |\n"
        "| Corresponding author | Required | Ada Lovelace (ada@example.org) |\n"
        "| Submitting author and ORCID | Required | Grace Hopper (0000-0002-1694-233X) |\n"
        "| CRediT author contributions | Required | Final CRediT statement |\n"
        "| Funding statement | Required | No external funding |\n"
        "| Conflict of interest | Required | None declared |\n"
        "| AI-use disclosure | Required | Final disclosure reviewed by the authors |\n"
        "| Software license | Required | MIT |\n"
        "| Public or reviewer-accessible repository URL | Required | https://example.org/source |\n"
        "| Stable release DOI or archive URL | Required | https://doi.org/10.5281/zenodo.1 |\n"
        "| Public demo URL or Docker-only access statement | Required | https://example.org/demo |\n"
        "| Two-year software and web-service availability commitment | Required | Available for two years |\n"
        "| Support owner and contact | Required | Grace Hopper (support@example.org) |\n"
        "| Author-led scientific review and verification | Required | Grace Hopper reviewed and verified the submission on 2026-07-26 |\n"
        "| Open-access APC or waiver route | Operational | TODO |\n",
        encoding="utf-8",
    )
    (submission / "cover_letter_draft.md").write_text(
        "Dear Editors,\n\nSincerely,\nFinal Author\n",
        encoding="utf-8",
    )
    (submission / "data_availability_statement.md").write_text(
        "Source and release are archived at https://example.org/release under MIT.\n",
        encoding="utf-8",
    )
    (tmp_path / "LICENSE").write_text(license_text(), encoding="utf-8")

    assert checker.collect_blockers(tmp_path) == []


def test_collect_blockers_reports_short_license_stub(tmp_path: Path) -> None:
    manuscript = tmp_path / "manuscript" / "bioinformatics_app_note"
    submission = manuscript / "submission"
    submission.mkdir(parents=True)
    (manuscript / "main.tex").write_text(
        "\\section*{Data and Software Availability}\n"
        "Source code is archived at https://example.org/release and licensed under MIT.\n",
        encoding="utf-8",
    )
    (manuscript / "supplementary.tex").write_text(
        "\\section*{AI Assistance Disclosure}\n"
        "The authors used ExampleAI for language editing and independently verified the final text.\n",
        encoding="utf-8",
    )
    (submission / "browser_compatibility_record.md").write_text(
        "| Engine | Browser | Result |\n"
        "| --- | --- | --- |\n"
        "| Chromium | Chrome 130 | passed |\n"
        "| Gecko | Firefox 132 | passed |\n"
        "| WebKit | Safari 18 | passed |\n",
        encoding="utf-8",
    )
    (submission / "final_submission_decisions.md").write_text("No owner placeholders.\n", encoding="utf-8")
    (submission / "cover_letter_draft.md").write_text("Dear Editors.\n", encoding="utf-8")
    (submission / "data_availability_statement.md").write_text(
        "Available at https://example.org/release.\n",
        encoding="utf-8",
    )
    (tmp_path / "LICENSE").write_text("MIT\n", encoding="utf-8")

    blockers = checker.collect_blockers(tmp_path)

    assert "LICENSE: license text is too short to be a final license file" in blockers


def test_collect_blockers_reports_missing_required_files(tmp_path: Path) -> None:
    blockers = checker.collect_blockers(tmp_path)

    assert "manuscript/bioinformatics_app_note/main.tex: missing required submission file" in blockers
    assert (
        "manuscript/bioinformatics_app_note/supplementary.tex: missing required submission file"
        in blockers
    )
    assert (
        "manuscript/bioinformatics_app_note/submission/browser_compatibility_record.md: missing required submission file"
        in blockers
    )
    assert (
        "manuscript/bioinformatics_app_note/submission/final_submission_decisions.md: missing required submission file"
        in blockers
    )
    assert (
        "manuscript/bioinformatics_app_note/submission/cover_letter_draft.md: missing required submission file"
        in blockers
    )
    assert (
        "manuscript/bioinformatics_app_note/submission/data_availability_statement.md: missing required submission file"
        in blockers
    )
