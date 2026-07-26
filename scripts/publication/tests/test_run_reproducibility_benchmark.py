from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import sys


MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "run_reproducibility_benchmark.py"
)
SPEC = importlib.util.spec_from_file_location(
    "run_reproducibility_benchmark",
    MODULE_PATH,
)
assert SPEC is not None
sys.path.insert(0, str(MODULE_PATH.parent))
benchmark = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(benchmark)


def test_artifact_boundary_detects_plot_mutation_without_rehashing_run(
    tmp_path: Path,
) -> None:
    plot = tmp_path / "plot.png"
    plot.write_bytes(b"frozen plot")
    report = {
        "artifacts": {
            "png": {
                "filename": plot.name,
                "bytes": plot.stat().st_size,
                "sha256": hashlib.sha256(plot.read_bytes()).hexdigest(),
            }
        }
    }

    boundary = benchmark.artifact_mutation_boundary(
        tmp_path,
        report,
        preferred_labels=("png",),
    )

    assert boundary == {
        "label": "png",
        "hash_unchanged": True,
        "checksum_failed": True,
    }


def test_clean_reproduction_aggregates_worst_numeric_error(
    tmp_path: Path,
) -> None:
    result = {
        "schema_version": "tcga-trace-clean-reproduction-benchmark-v1",
        "design": {"numeric_comparison": {"policy_version": "test-v1"}},
        "negative_controls": {
            "input_tamper": True,
            "snapshot_mutation": True,
        },
        "environments": [
            {
                "image_metadata": {"architecture": "arm64"},
                "cases": [
                    {
                        "label": "Single gene",
                        "status": "passed",
                        "numeric_comparison": {
                            "observed_errors": {
                                "effects": {
                                    "comparisons": 8,
                                    "max_absolute_error": 1e-12,
                                    "max_relative_error": 2e-12,
                                }
                            }
                        },
                    }
                ],
            },
            {
                "image_metadata": {"architecture": "amd64"},
                "cases": [
                    {
                        "label": "Single gene",
                        "status": "passed",
                        "numeric_comparison": {
                            "observed_errors": {
                                "effects": {
                                    "comparisons": 8,
                                    "max_absolute_error": 3e-12,
                                    "max_relative_error": 1e-12,
                                }
                            }
                        },
                    }
                ],
            },
        ],
    }
    path = tmp_path / "clean.json"
    path.write_text(json.dumps(result), encoding="utf-8")

    evidence = benchmark.load_clean_container_evidence(path)

    assert evidence["status"] == "passed"
    assert evidence["cases"]["Single gene"] == {
        "passed": 2,
        "total": 2,
        "numeric_comparisons": 8,
        "max_absolute_error": 3e-12,
        "max_relative_error": 2e-12,
    }


def test_attach_clean_reproduction_publishes_isolated_numeric_errors() -> None:
    rows = [
        {
            "label": "Single gene",
            "status": "passed",
            "numeric_comparisons": 0,
            "max_absolute_error": 0.0,
            "max_relative_error": 0.0,
        }
    ]
    evidence = {
        "cases": {
            "Single gene": {
                "passed": 2,
                "total": 2,
                "numeric_comparisons": 730,
                "max_absolute_error": 1e-13,
                "max_relative_error": 4e-14,
            }
        }
    }

    benchmark.attach_clean_reproduction(rows, evidence)

    assert rows[0]["clean_reruns_passed"] == 2
    assert rows[0]["clean_reruns"] == 2
    assert rows[0]["numeric_comparisons"] == 730
    assert rows[0]["max_absolute_error"] == 1e-13
    assert rows[0]["max_relative_error"] == 4e-14
