from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "finalize_submission_package.py"
SPEC = importlib.util.spec_from_file_location("finalize_submission_package", MODULE_PATH)
assert SPEC is not None
finalizer = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = finalizer
assert SPEC.loader is not None
SPEC.loader.exec_module(finalizer)


def test_command_steps_apply_metadata_then_strict_gate_archive_and_verify() -> None:
    steps = finalizer.command_steps(
        finalizer.ROOT / "owner.json",
        finalizer.ROOT / "build" / "review.tar.gz",
        license_source=finalizer.ROOT / "chosen_LICENSE",
        overwrite_license=True,
    )

    assert [step.label for step in steps] == [
        "apply owner metadata",
        "run strict pre-submission gate",
        "build final reviewer/source archive",
        "verify final archive",
    ]
    assert steps[0].argv == [
        "scripts/publication/apply_submission_metadata.py",
        "owner.json",
        "--license-source",
        "chosen_LICENSE",
        "--overwrite-license",
    ]
    assert steps[1].argv == ["scripts/publication/pre_submission_check.sh", "--strict-owner-metadata"]
    assert steps[2].argv == [
        "scripts/publication/build_submission_archive.py",
        "--strict-owner-metadata",
        "--output",
        "build/review.tar.gz",
    ]
    assert steps[3].argv == ["scripts/publication/verify_submission_archive.py", "build/review.tar.gz"]


def test_final_package_reports_archive_hash_and_required_pdfs(tmp_path: Path, monkeypatch) -> None:
    archive = tmp_path / "review.tar.gz"
    main_pdf = tmp_path / "main.pdf"
    oup_preview_pdf = tmp_path / "oup-preview.pdf"
    supplement_pdf = tmp_path / "supplement.pdf"
    archive.write_bytes(b"archive\n")
    main_pdf.write_bytes(b"main\n")
    oup_preview_pdf.write_bytes(b"oup\n")
    supplement_pdf.write_bytes(b"supplement\n")
    monkeypatch.setattr(finalizer, "ROOT", tmp_path)
    monkeypatch.setattr(finalizer, "MAIN_PDF", Path("main.pdf"))
    monkeypatch.setattr(finalizer, "OUP_PREVIEW_PDF", Path("oup-preview.pdf"))
    monkeypatch.setattr(finalizer, "SUPPLEMENT_PDF", Path("supplement.pdf"))

    package = finalizer.final_package(archive)

    assert package.archive == archive
    assert package.archive_bytes == len(b"archive\n")
    assert package.archive_sha256 == hashlib.sha256(b"archive\n").hexdigest()
    assert package.main_pdf == main_pdf
    assert package.oup_preview_pdf == oup_preview_pdf
    assert package.supplement_pdf == supplement_pdf


def test_final_package_reports_missing_outputs(tmp_path: Path, monkeypatch) -> None:
    archive = tmp_path / "review.tar.gz"
    archive.write_bytes(b"archive\n")
    monkeypatch.setattr(finalizer, "ROOT", tmp_path)
    monkeypatch.setattr(finalizer, "MAIN_PDF", Path("main.pdf"))
    monkeypatch.setattr(finalizer, "OUP_PREVIEW_PDF", Path("oup-preview.pdf"))
    monkeypatch.setattr(finalizer, "SUPPLEMENT_PDF", Path("supplement.pdf"))

    try:
        finalizer.final_package(archive)
    except finalizer.FinalizeError as exc:
        assert "missing final output" in str(exc)
        assert "main.pdf" in str(exc)
        assert "supplement.pdf" in str(exc)
    else:
        raise AssertionError("missing PDFs should fail final package report")


def test_validate_metadata_dry_run_appends_dry_run_flag(monkeypatch) -> None:
    calls = []

    def fake_run(argv, *, cwd, check):
        calls.append((argv, cwd, check))

    monkeypatch.setattr(finalizer.subprocess, "run", fake_run)
    step = finalizer.CommandStep(
        "apply owner metadata",
        ["scripts/publication/apply_submission_metadata.py", "owner.json"],
    )

    finalizer.validate_metadata_dry_run(step)

    assert calls == [
        (
            ["scripts/publication/apply_submission_metadata.py", "owner.json", "--dry-run"],
            finalizer.ROOT,
            True,
        )
    ]


def test_validate_metadata_dry_run_reports_failure(monkeypatch) -> None:
    def fake_run(argv, *, cwd, check):
        raise subprocess.CalledProcessError(1, argv)

    monkeypatch.setattr(finalizer.subprocess, "run", fake_run)
    step = finalizer.CommandStep(
        "apply owner metadata",
        ["scripts/publication/apply_submission_metadata.py", "owner.json"],
    )

    try:
        finalizer.validate_metadata_dry_run(step)
    except finalizer.FinalizeError as exc:
        assert "dry-run validation failed" in str(exc)
    else:
        raise AssertionError("failed metadata dry-run should fail finalizer dry-run")


def test_default_summary_path_replaces_tar_gz_suffix() -> None:
    path = Path("build") / "tcga-trace-review-package-final.tar.gz"

    assert finalizer.default_summary_path(path) == Path("build") / "tcga-trace-review-package-final.summary.json"


def test_write_summary_records_pdf_and_archive_hashes(tmp_path: Path, monkeypatch) -> None:
    archive = tmp_path / "review.tar.gz"
    main_pdf = tmp_path / "main.pdf"
    oup_preview_pdf = tmp_path / "oup-preview.pdf"
    supplement_pdf = tmp_path / "supplement.pdf"
    summary = tmp_path / "summary.json"
    archive.write_bytes(b"archive\n")
    main_pdf.write_bytes(b"main\n")
    oup_preview_pdf.write_bytes(b"oup\n")
    supplement_pdf.write_bytes(b"supplement\n")
    monkeypatch.setattr(finalizer, "ROOT", tmp_path)

    package = finalizer.FinalPackage(
        archive=archive,
        archive_bytes=archive.stat().st_size,
        archive_sha256=hashlib.sha256(b"archive\n").hexdigest(),
        main_pdf=main_pdf,
        oup_preview_pdf=oup_preview_pdf,
        supplement_pdf=supplement_pdf,
    )

    finalizer.write_summary(package, summary)
    payload = json.loads(summary.read_text(encoding="utf-8"))

    assert payload["schema_version"] == "tcga-trace-final-package-summary-v1"
    assert payload["archive"]["path"] == "review.tar.gz"
    assert payload["archive"]["sha256"] == hashlib.sha256(b"archive\n").hexdigest()
    assert payload["main_pdf"]["sha256"] == hashlib.sha256(b"main\n").hexdigest()
    assert payload["oup_preview_pdf"]["sha256"] == hashlib.sha256(b"oup\n").hexdigest()
    assert payload["supplement_pdf"]["sha256"] == hashlib.sha256(b"supplement\n").hexdigest()
