from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest


MODULE_PATH = Path(__file__).resolve().parents[1] / "run_browser_compatibility.py"
SPEC = importlib.util.spec_from_file_location("run_browser_compatibility", MODULE_PATH)
assert SPEC is not None
browser = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = browser
assert SPEC.loader is not None
SPEC.loader.exec_module(browser)


def test_parse_engines_requires_known_unique_engines() -> None:
    assert browser.parse_engines("chromium, firefox,webkit") == (
        "chromium",
        "firefox",
        "webkit",
    )
    with pytest.raises(ValueError, match="Unsupported"):
        browser.parse_engines("safari")
    with pytest.raises(ValueError, match="repeated"):
        browser.parse_engines("chromium,chromium")


def test_resolve_base_url_uses_compose_binding(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args=args,
            returncode=0,
            stdout="192.168.1.31:3000\n",
            stderr="",
        ),
    )

    assert browser.resolve_base_url("auto", tmp_path) == (
        "http://192.168.1.31:3000/tcga_explorer/"
    )
    assert browser.resolve_base_url("https://example.org/app", tmp_path) == (
        "https://example.org/app/"
    )


def test_validate_final_release_requires_https_clean_exact_tag() -> None:
    browser.validate_final_release(
        "https://example.org/tcga_explorer/",
        {"dirty": False, "exact_tag": "v1.0.0"},
    )
    with pytest.raises(ValueError, match="HTTPS"):
        browser.validate_final_release(
            "http://example.org/tcga_explorer/",
            {"dirty": False, "exact_tag": "v1.0.0"},
        )
    with pytest.raises(ValueError, match="clean worktree"):
        browser.validate_final_release(
            "https://example.org/tcga_explorer/",
            {"dirty": True, "exact_tag": "v1.0.0"},
        )
    with pytest.raises(ValueError, match="exactly one release tag"):
        browser.validate_final_release(
            "https://example.org/tcga_explorer/",
            {"dirty": False, "exact_tag": None},
        )


def test_build_docker_command_is_engine_isolated(tmp_path: Path) -> None:
    runner = tmp_path / "runner.js"
    runner.write_text("", encoding="utf-8")
    result_dir = tmp_path / "results"
    result_dir.mkdir()

    command = browser.build_docker_command(
        tmp_path,
        runner,
        result_dir,
        engine="firefox",
        base_url="http://host.docker.internal:3000/tcga_explorer/",
        playwright_image="playwright:test",
        expected_release_commit="b" * 40,
        expected_release_ref="v1.2.3",
    )

    assert command[:3] == ["docker", "run", "--rm"]
    assert "ENGINE=firefox" in command
    assert "RESULT_PATH=/results/firefox.json" in command
    assert "BASE_URL=http://host.docker.internal:3000/tcga_explorer/" in command
    assert f"EXPECTED_RELEASE_COMMIT={'b' * 40}" in command
    assert "EXPECTED_RELEASE_REF=v1.2.3" in command
    assert "playwright:test" in command
    assert f"{runner.resolve()}:/runner/browser_compatibility.js:ro" in command


def complete_payload(status: str = "passed_provisional") -> dict:
    return {
        "schema_version": browser.SCHEMA_VERSION,
        "status": status,
        "generated_at": "2026-07-25T12:00:00+00:00",
        "base_url": "http://example.test/tcga_explorer/",
        "tester": "Automated test",
        "playwright": {"version": browser.PLAYWRIGHT_VERSION, "image": "playwright:test"},
        "release": {
            "commit": "a" * 40,
            "dirty": status != "passed_final_release",
            "tags_at_head": [] if status != "passed_final_release" else ["v1.0.0"],
            "exact_tag": None if status != "passed_final_release" else "v1.0.0",
        },
        "required_engines": list(browser.ENGINES),
        "required_checks": list(browser.REQUIRED_CHECKS),
        "results": [
            {
                "engine": engine,
                "browser_version": "1.2.3",
                "runtime_os": "Linux test x64",
                "status": "passed",
                "duration_ms": 1000,
                "checks": [
                    {
                        "id": check,
                        "status": "passed",
                        "duration_ms": 1,
                        "details": (
                            {
                                "release_commit": "a" * 40,
                                "release_ref": (
                                    "v1.0.0"
                                    if status == "passed_final_release"
                                    else "development"
                                ),
                            }
                            if check == "landing_and_keyboard"
                            else {}
                        ),
                    }
                    for check in browser.REQUIRED_CHECKS
                ],
                "console_errors": [],
                "page_errors": [],
            }
            for engine in browser.ENGINES
        ],
        "scope": {},
    }


def test_render_browser_record_preserves_provisional_blocker() -> None:
    provisional = browser.render_browser_record(complete_payload())
    final = browser.render_browser_record(complete_payload("passed_final_release"))

    assert browser.FINAL_RETEST_TOKEN in provisional
    assert "final tagged HTTPS release verified" in final
    assert browser.FINAL_RETEST_TOKEN not in final
    for label in ("Chromium", "Gecko", "WebKit"):
        assert label in provisional


def test_final_payload_requires_deployed_commit_match() -> None:
    payload = complete_payload("passed_final_release")
    browser.validate_payload(payload, require_final=True)

    payload["results"][0]["checks"][0]["details"]["release_commit"] = "b" * 40
    with pytest.raises(SystemExit, match="tested deployment commit"):
        browser.validate_payload(payload, require_final=True)


def test_final_payload_requires_deployed_ref_match() -> None:
    payload = complete_payload("passed_final_release")
    payload["results"][0]["checks"][0]["details"]["release_ref"] = "v0.9.0"

    with pytest.raises(SystemExit, match="tested deployment ref"):
        browser.validate_payload(payload, require_final=True)


def test_check_frozen_output_validates_checksums_and_final_state(tmp_path: Path) -> None:
    output = tmp_path / "output"
    output.mkdir()
    record = tmp_path / "browser.md"
    payload = complete_payload()
    raw = output / browser.RAW_FILENAME
    summary = output / browser.SUMMARY_FILENAME
    raw.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    summary.write_text(browser.render_summary(payload), encoding="utf-8")
    record.write_text(browser.render_browser_record(payload), encoding="utf-8")
    manifest = {
        "schema_version": browser.SCHEMA_VERSION,
        "status": payload["status"],
        "files": {
            browser.RAW_FILENAME: browser.file_record(raw),
            browser.SUMMARY_FILENAME: browser.file_record(summary),
        },
    }
    (output / browser.MANIFEST_FILENAME).write_text(
        json.dumps(manifest),
        encoding="utf-8",
    )

    assert browser.check_frozen_output(output, record, require_final=False) == 0
    with pytest.raises(SystemExit, match="not acceptable"):
        browser.check_frozen_output(output, record, require_final=True)
