import hashlib
import json
from pathlib import Path
import subprocess

from app.reproduction_capsule import (
    BASE_IMAGE,
    CRAN_SNAPSHOT,
    ENGINE_FILENAMES,
    REPRODUCTION_TOLERANCE_POLICY,
    REPRODUCTION_TOLERANCE_POLICY_VERSION,
    reproduction_runner_source,
    write_reproduction_capsule,
)


def test_write_reproduction_capsule_copies_complete_frozen_contract(tmp_path) -> None:
    engine_dir = tmp_path / "engine"
    engine_dir.mkdir()
    for filename in ENGINE_FILENAMES:
        (engine_dir / filename).write_text(f"# {filename}\n", encoding="utf-8")

    analysis_dir = tmp_path / "analysis"
    analysis_dir.mkdir()
    (analysis_dir / "input.json").write_text('{"records":[]}\n', encoding="utf-8")
    (analysis_dir / "metrics.json").write_text('{"n_patients":0}\n', encoding="utf-8")
    lock_path = tmp_path / "renv.lock"
    lock_path.write_text('{"R":{"Version":"4.4.2"},"Packages":{}}\n', encoding="utf-8")

    paths = write_reproduction_capsule(
        analysis_dir,
        r_script_path=engine_dir / "km_analysis.R",
        renv_lock_path=lock_path,
    )

    assert set(paths) == {
        "reproduction_km_analysis",
        "reproduction_clinical_covariates",
        "reproduction_cox_diagnostics",
        "reproduction_competing_risks",
        "reproduction_renv_lock",
        "reproduction_r_runner",
        "reproduction_dockerfile",
        "reproduction_readme",
        "reproduction_manifest",
    }
    manifest = json.loads((analysis_dir / "reproduction_manifest.json").read_text())
    assert manifest["schema_version"] == "tcga-trace-reproduction-capsule-v1"
    assert manifest["base_image"] == BASE_IMAGE
    assert manifest["cran_snapshot"] == CRAN_SNAPSHOT
    assert (
        manifest["numeric_comparison"]["policy_version"]
        == REPRODUCTION_TOLERANCE_POLICY_VERSION
    )
    assert (
        manifest["numeric_comparison"]["classes"]
        == REPRODUCTION_TOLERANCE_POLICY
    )
    assert "expected_results" not in manifest["files"]
    assert manifest["files"]["input"]["sha256"] == hashlib.sha256(
        (analysis_dir / "input.json").read_bytes()
    ).hexdigest()
    assert "docker run --rm --network none --read-only" in (
        analysis_dir / "REPRODUCE.md"
    ).read_text()
    assert f"FROM {BASE_IMAGE}" in (
        analysis_dir / "Dockerfile.reproduce"
    ).read_text()
    runner = (analysis_dir / "rerun_analysis.R").read_text()
    assert "reproduction_result.json" in runner
    assert "absolute_error <= absolute + relative" in runner
    assert "max_absolute_error" in runner


def test_write_reproduction_capsule_requires_expected_metrics(tmp_path) -> None:
    engine_dir = tmp_path / "engine"
    engine_dir.mkdir()
    for filename in ENGINE_FILENAMES:
        (engine_dir / filename).write_text("", encoding="utf-8")
    analysis_dir = tmp_path / "analysis"
    analysis_dir.mkdir()
    (analysis_dir / "input.json").write_text("{}\n", encoding="utf-8")
    lock_path = tmp_path / "renv.lock"
    lock_path.write_text("{}\n", encoding="utf-8")

    try:
        write_reproduction_capsule(
            analysis_dir,
            r_script_path=engine_dir / "km_analysis.R",
            renv_lock_path=lock_path,
        )
    except FileNotFoundError as exc:
        assert "metrics.json" in str(exc)
    else:
        raise AssertionError("Expected a missing metrics.json failure")


def test_generated_reproduction_runner_parses_as_r(tmp_path) -> None:
    runner = tmp_path / "rerun_analysis.R"
    runner.write_text(reproduction_runner_source(), encoding="utf-8")

    result = subprocess.run(
        [
            "Rscript",
            "-e",
            f"parse(file={json.dumps(str(runner))})",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
