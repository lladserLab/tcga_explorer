from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "capture_reviewer_screenshots.py"
SPEC = importlib.util.spec_from_file_location("capture_reviewer_screenshots", MODULE_PATH)
assert SPEC is not None
screenshots = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = screenshots
assert SPEC.loader is not None
SPEC.loader.exec_module(screenshots)


def test_normalize_base_url_adds_trailing_slash() -> None:
    assert screenshots.normalize_base_url("http://example.test/tcga_explorer") == (
        "http://example.test/tcga_explorer/"
    )
    assert screenshots.normalize_base_url("http://example.test/tcga_explorer/") == (
        "http://example.test/tcga_explorer/"
    )


def test_output_paths_are_expected_publication_figures(tmp_path: Path) -> None:
    paths = screenshots.output_paths(tmp_path)

    assert paths == [
        tmp_path / "tcga_trace_ui_analysis.png",
        tmp_path / "tcga_trace_ui_multiverse.png",
        tmp_path / "tcga_trace_ui_pancancer.png",
        tmp_path / "tcga_trace_ui_methods.png",
    ]


def test_build_docker_command_mounts_repo_runner_and_outputs(tmp_path: Path) -> None:
    args = argparse.Namespace(
        base_url="http://host.docker.internal:3000/tcga_explorer",
        output_dir=Path("manuscript/bioinformatics_app_note/figures"),
        playwright_image="playwright-image:test",
    )

    command = screenshots.build_docker_command(tmp_path, tmp_path / "runner", args)

    assert command[:3] == ["docker", "run", "--rm"]
    assert "BASE_URL=http://host.docker.internal:3000/tcga_explorer/" in command
    assert "OUTPUT_DIR=/work/manuscript/bioinformatics_app_note/figures" in command
    assert "MULTIVERSE_SCREENSHOT=tcga_trace_ui_multiverse.png" in command
    assert "PANCANCER_SCREENSHOT=tcga_trace_ui_pancancer.png" in command
    assert f"{tmp_path.resolve()}:/work" in command
    assert f"{(tmp_path / 'runner').resolve()}:/runner:ro" in command
    assert "playwright-image:test" in command
    assert "node /runner/capture_screenshots.js" in command[-1]
