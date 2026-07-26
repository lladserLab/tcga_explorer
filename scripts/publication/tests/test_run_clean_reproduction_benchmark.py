import importlib.util
import json
from pathlib import Path

import pytest


MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "run_clean_reproduction_benchmark.py"
)
SPEC = importlib.util.spec_from_file_location(
    "run_clean_reproduction_benchmark",
    MODULE_PATH,
)
assert SPEC is not None
benchmark = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(benchmark)
verifier = benchmark.verifier


def write_test_capsule(
    destination: Path,
    *,
    analysis_id: str,
    omit: set[str] | None = None,
    declare_omitted: bool = False,
) -> None:
    omit = omit or set()
    destination.mkdir(parents=True, exist_ok=True)
    for filename in benchmark.CURRENT_CAPSULE_FILENAMES:
        if filename in omit or filename == "reproduction_manifest.json":
            continue
        payload = "{}\n"
        if filename == "audit_report.json":
            payload = json.dumps({"analysis_id": analysis_id}) + "\n"
        elif filename == "renv.lock":
            payload = json.dumps(
                {"Packages": {"cmprsk": {"Version": "2.2-12"}}}
            ) + "\n"
        (destination / filename).write_text(payload, encoding="utf-8")

    labels = {
        "input": "input.json",
        "reproduction_dockerfile": "Dockerfile.reproduce",
        "reproduction_km_analysis": "km_analysis.R",
        "reproduction_r_runner": "rerun_analysis.R",
        "reproduction_renv_lock": "renv.lock",
    }
    manifest_files = {}
    for label, filename in labels.items():
        path = destination / filename
        if path.is_file():
            manifest_files[label] = {
                "filename": filename,
                "bytes": path.stat().st_size,
                "sha256": benchmark.file_sha256(path),
            }
        elif declare_omitted:
            manifest_files[label] = {
                "filename": filename,
                "bytes": 1,
                "sha256": "0" * 64,
            }
    benchmark.write_json(
        destination / "reproduction_manifest.json",
        {
            "schema_version": "tcga-trace-reproduction-capsule-v1",
            "files": manifest_files,
        },
    )


def test_docker_run_contract_disables_network_and_mounts_capsule_read_only(
    tmp_path,
) -> None:
    capsule = tmp_path / "capsule"
    output = tmp_path / "output"
    capsule.mkdir()
    output.mkdir()

    command = benchmark.docker_run_command(
        capsule=capsule,
        output=output,
        image="reproduction:test",
        requested_platform="linux/amd64",
    )

    assert command[:5] == [
        "docker",
        "run",
        "--rm",
        "--platform",
        "linux/amd64",
    ]
    assert ["--network", "none"] == command[5:7]
    assert "--read-only" in command
    assert f"type=bind,src={capsule},dst=/analysis,readonly" in command


def test_data_snapshot_tamper_changes_reproducibility_hash(tmp_path) -> None:
    capsule = tmp_path / "capsule"
    capsule.mkdir()
    report = {
        "schema_version": "tcga-trace-analysis-audit-v3",
        "request": {"cohort": "TCGA-LIHC"},
        "data": {
            "data_dates": {"data_through_date": "2026-07-25"},
            "provenance": {
                "expression_files": [
                    {"filename": "matrix.bin", "sha256": "a" * 64}
                ]
            },
        },
        "analysis_design": {"scoring_provenance": {}},
        "cohort_selection": {
            "patient_records_sha256": "b" * 64,
            "continuous_patient_records": [],
        },
        "results": {"n_patients": 10},
    }
    payload = verifier.reproducibility_payload_from_report(
        report,
        request_payload=report["request"],
        patient_digest="b" * 64,
    )
    report["reproducibility_hash"] = verifier.stable_hash(payload)
    (capsule / "audit_report.json").write_text(
        json.dumps(report),
        encoding="utf-8",
    )

    assert benchmark.data_snapshot_tamper_detected(capsule)


def test_check_only_validates_manifest_and_negative_controls(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(benchmark, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(benchmark, "verify_frozen_capsules", lambda: None)
    results = {
        "schema_version": "tcga-trace-clean-reproduction-benchmark-v1",
        "environments": [
            {
                "cases": [
                    {
                        "status": "passed",
                        "numeric_comparison": {
                            "policy_version": (
                                benchmark.REPRODUCTION_TOLERANCE_POLICY_VERSION
                            )
                        },
                    }
                ],
                "input_tamper": {"detected": True},
            }
        ],
        "negative_controls": {
            "data_snapshot_hash_change_detected": True,
            "mutated_input_rejected_by_all_environments": True,
        },
    }
    benchmark.write_json(tmp_path / "benchmark_results.raw.json", results)
    (tmp_path / "summary.md").write_text("clean\n", encoding="utf-8")
    benchmark.write_manifest()

    benchmark.verify_frozen_outputs()


def test_check_only_rejects_modified_file(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(benchmark, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(benchmark, "verify_frozen_capsules", lambda: None)
    results = {
        "schema_version": "tcga-trace-clean-reproduction-benchmark-v1",
        "environments": [
            {
                "cases": [
                    {
                        "status": "passed",
                        "numeric_comparison": {
                            "policy_version": (
                                benchmark.REPRODUCTION_TOLERANCE_POLICY_VERSION
                            )
                        },
                    }
                ],
                "input_tamper": {"detected": True},
            }
        ],
        "negative_controls": {
            "data_snapshot_hash_change_detected": True,
            "mutated_input_rejected_by_all_environments": True,
        },
    }
    benchmark.write_json(tmp_path / "benchmark_results.raw.json", results)
    summary = tmp_path / "summary.md"
    summary.write_text("clean\n", encoding="utf-8")
    benchmark.write_manifest()
    summary.write_text("dirty\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="SHA-256 mismatch"):
        benchmark.verify_frozen_outputs()


def test_prepare_capsules_uses_verified_frozen_copy_without_runtime_artifacts(
    tmp_path,
    monkeypatch,
) -> None:
    root = tmp_path / "repo"
    capsule_dir = root / "frozen"
    destination = capsule_dir / "single_gene"
    destination.mkdir(parents=True)
    analysis_id = "analysis-123"
    summary = root / "summary.csv"
    summary.write_text(
        f"label,analysis_id\nSingle gene,{analysis_id}\n",
        encoding="utf-8",
    )
    write_test_capsule(destination, analysis_id=analysis_id)
    monkeypatch.setattr(benchmark, "ROOT", root)
    monkeypatch.setattr(benchmark, "RECONSTRUCTION_SUMMARY", summary)
    monkeypatch.setattr(benchmark, "CAPSULE_DIR", capsule_dir)
    monkeypatch.setattr(
        benchmark,
        "FROZEN_CAPSULE_LABELS",
        {"single_gene": "Single gene"},
    )

    capsules = benchmark.prepare_capsules()

    assert capsules == {"Single gene": destination}


def test_refresh_capsules_requires_matching_source_artifact(
    tmp_path,
    monkeypatch,
) -> None:
    root = tmp_path / "repo"
    capsule_dir = root / "frozen"
    analysis_id = "missing-analysis"
    summary = root / "summary.csv"
    summary.parent.mkdir(parents=True)
    summary.write_text(
        f"label,analysis_id\nSingle gene,{analysis_id}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(benchmark, "ROOT", root)
    monkeypatch.setattr(benchmark, "RECONSTRUCTION_SUMMARY", summary)
    monkeypatch.setattr(benchmark, "CAPSULE_DIR", capsule_dir)

    with pytest.raises(FileNotFoundError, match="source artifact"):
        benchmark.prepare_capsules(refresh=True)


def test_check_only_rejects_manifest_recorded_missing_engine(
    tmp_path,
    monkeypatch,
) -> None:
    root = tmp_path / "repo"
    capsule_dir = root / "frozen"
    destination = capsule_dir / "single_gene"
    destination.mkdir(parents=True)
    analysis_id = "analysis-123"
    summary = root / "summary.csv"
    summary.write_text(
        f"label,analysis_id\nSingle gene,{analysis_id}\n",
        encoding="utf-8",
    )
    write_test_capsule(
        destination,
        analysis_id=analysis_id,
        omit={"km_analysis.R"},
        declare_omitted=True,
    )

    monkeypatch.setattr(benchmark, "ROOT", root)
    monkeypatch.setattr(benchmark, "RECONSTRUCTION_SUMMARY", summary)
    monkeypatch.setattr(benchmark, "CAPSULE_DIR", capsule_dir)
    monkeypatch.setattr(
        benchmark,
        "FROZEN_CAPSULE_LABELS",
        {"single_gene": "Single gene"},
    )

    with pytest.raises(RuntimeError, match="integrity check failed"):
        benchmark.verify_frozen_capsules()


def test_package_versions_match_lock_normalizes_r_version_separator(
    tmp_path,
    monkeypatch,
) -> None:
    capsule = tmp_path / "capsule"
    capsule.mkdir()
    benchmark.write_json(
        capsule / "renv.lock",
        {"Packages": {"cmprsk": {"Version": "2.2-12"}}},
    )
    monkeypatch.setattr(
        benchmark,
        "REQUIRED_RUNTIME_PACKAGES",
        {"cmprsk"},
    )

    assert benchmark.package_versions_match_lock(
        capsule=capsule,
        observed={"cmprsk": "2.2.12"},
    )


def test_package_versions_match_lock_requires_runtime_package_set(
    tmp_path,
    monkeypatch,
) -> None:
    capsule = tmp_path / "capsule"
    capsule.mkdir()
    benchmark.write_json(
        capsule / "renv.lock",
        {
            "Packages": {
                "survival": {"Version": "3.8-9"},
                "jsonlite": {"Version": "2.0.0"},
            }
        },
    )
    monkeypatch.setattr(
        benchmark,
        "REQUIRED_RUNTIME_PACKAGES",
        {"survival", "jsonlite"},
    )

    assert not benchmark.package_versions_match_lock(
        capsule=capsule,
        observed={"survival": "3.8.9"},
    )
