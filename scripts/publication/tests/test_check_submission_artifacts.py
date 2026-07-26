from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "check_submission_artifacts.py"
SPEC = importlib.util.spec_from_file_location("check_submission_artifacts", MODULE_PATH)
assert SPEC is not None
checker = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = checker
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


def write_owner_ready_fixture(root: Path) -> None:
    manuscript = root / "manuscript" / "bioinformatics_app_note"
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
        "| Software license | Required | MIT |\n",
        encoding="utf-8",
    )
    (submission / "cover_letter_draft.md").write_text(
        "Dear Editors,\n\nSincerely,\nFinal Author\n",
        encoding="utf-8",
    )
    (root / "LICENSE").write_text(license_text(), encoding="utf-8")


def test_build_manifest_records_available_artifact(tmp_path: Path) -> None:
    write_owner_ready_fixture(tmp_path)
    artifact_path = Path("artifact.txt")
    (tmp_path / artifact_path).write_text("content\n", encoding="utf-8")

    manifest = checker.build_manifest(
        tmp_path,
        [checker.Artifact(artifact_path, "test", "Test artifact.")],
    )

    assert manifest["missing_required_artifacts"] == []
    assert manifest["owner_metadata_blockers"] == []
    assert manifest["artifacts"][0]["status"] == "available"
    assert manifest["artifacts"][0]["sha256"]


def test_build_manifest_reports_missing_required_artifact(tmp_path: Path) -> None:
    write_owner_ready_fixture(tmp_path)

    manifest = checker.build_manifest(
        tmp_path,
        [checker.Artifact(Path("missing.txt"), "test", "Missing artifact.")],
    )

    assert manifest["missing_required_artifacts"] == ["missing.txt"]
    assert manifest["artifacts"][0]["status"] == "missing"


def test_build_manifest_includes_owner_metadata_blockers(tmp_path: Path) -> None:
    manifest = checker.build_manifest(
        tmp_path,
        [checker.Artifact(Path("missing.txt"), "test", "Missing artifact.", required=False)],
    )

    assert manifest["missing_required_artifacts"] == []
    assert manifest["owner_metadata_blockers"]
