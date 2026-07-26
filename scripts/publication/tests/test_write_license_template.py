from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "write_license_template.py"
SPEC = importlib.util.spec_from_file_location("write_license_template", MODULE_PATH)
assert SPEC is not None
writer = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = writer
assert SPEC.loader is not None
SPEC.loader.exec_module(writer)

APPLIER_PATH = Path(__file__).resolve().parents[1] / "apply_submission_metadata.py"
APPLIER_SPEC = importlib.util.spec_from_file_location("apply_submission_metadata", APPLIER_PATH)
assert APPLIER_SPEC is not None
applier = importlib.util.module_from_spec(APPLIER_SPEC)
sys.modules[APPLIER_SPEC.name] = applier
assert APPLIER_SPEC.loader is not None
APPLIER_SPEC.loader.exec_module(applier)


def test_render_mit_license_passes_submission_license_validation(tmp_path: Path) -> None:
    text = writer.render_license("MIT", year="2026", holder="Example Authors")
    path = tmp_path / "LICENSE"
    writer.write_output(path, text, force=False)

    assert "MIT License" in text
    assert "Copyright (c) 2026 Example Authors" in text
    assert len(text) > applier.MIN_LICENSE_CHARS
    assert applier.validate_license_file(path) is None


def test_render_apache_license_passes_submission_license_validation(tmp_path: Path) -> None:
    text = writer.render_license("Apache-2.0", year=None, holder=None)
    path = tmp_path / "LICENSE"
    writer.write_output(path, text, force=False)

    assert "Apache License" in text
    assert "Version 2.0" in text
    assert "Copyright [yyyy] [name of copyright owner]" in text
    assert len(text) > applier.MIN_LICENSE_CHARS
    assert applier.validate_license_file(path) is None


def test_render_bsd_requires_year_and_holder() -> None:
    try:
        writer.render_license("BSD-3-Clause", year="2026", holder=None)
    except writer.LicenseTemplateError as exc:
        assert "--holder is required" in str(exc)
    else:
        raise AssertionError("BSD-3-Clause without holder should fail")


def test_apache_rejects_unused_year_holder() -> None:
    try:
        writer.render_license("Apache-2.0", year="2026", holder="Example Authors")
    except writer.LicenseTemplateError as exc:
        assert "does not use --year/--holder" in str(exc)
    else:
        raise AssertionError("Apache-2.0 with year/holder should fail")


def test_write_output_refuses_to_overwrite_different_file(tmp_path: Path) -> None:
    path = tmp_path / "LICENSE"
    path.write_text("Existing license text\n", encoding="utf-8")

    try:
        writer.write_output(path, writer.render_license("MIT", year="2026", holder="Example Authors"), force=False)
    except writer.LicenseTemplateError as exc:
        assert "already exists and differs" in str(exc)
    else:
        raise AssertionError("different existing output should require --force")
