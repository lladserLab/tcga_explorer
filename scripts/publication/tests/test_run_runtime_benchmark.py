from __future__ import annotations

from datetime import datetime, timedelta, timezone
import importlib.util
from pathlib import Path
import sys

import pytest


MODULE_PATH = Path(__file__).resolve().parents[1] / "run_runtime_benchmark.py"
SPEC = importlib.util.spec_from_file_location("run_runtime_benchmark", MODULE_PATH)
assert SPEC is not None
runtime = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = runtime
assert SPEC.loader is not None
SPEC.loader.exec_module(runtime)

EXPECTED_WORKLOADS = runtime.EXPECTED_WORKLOADS
SCHEMA_VERSION = runtime.SCHEMA_VERSION
job_intervals = runtime.job_intervals
multiverse_payload = runtime.multiverse_payload
parse_docker_stats_line = runtime.parse_docker_stats_line
parse_memory_bytes = runtime.parse_memory_bytes
render_latex = runtime.render_latex
summary_rows = runtime.summary_rows
timestamp_overlap_seconds = runtime.timestamp_overlap_seconds
validate_result = runtime.validate_result


def test_parse_memory_bytes_supports_docker_binary_units() -> None:
    assert parse_memory_bytes("94.42MiB / 7.748GiB") == round(
        94.42 * 1024**2
    )
    assert parse_memory_bytes("1.5GiB / 8GiB") == round(1.5 * 1024**3)
    assert parse_memory_bytes("not available") is None


def test_parse_docker_stats_line_removes_terminal_control_codes() -> None:
    line = (
        "\x1b[H"
        '{"MemUsage":"320.7MiB / 7.748GiB","Name":"worker"}'
        "\x1b[K\n"
    )

    assert parse_docker_stats_line(line) == {
        "MemUsage": "320.7MiB / 7.748GiB",
        "Name": "worker",
    }
    assert parse_docker_stats_line("\x1b[K\x1b[J") is None


def test_multiverse_payload_has_exactly_72_declared_cells() -> None:
    payload = multiverse_payload("test")

    planned = (
        len(payload["endpoints"])
        * len(payload["scoring_methods"])
        * len(payload["cutpoint_methods"])
    )
    assert planned == 72
    assert payload["adjustment_covariates"] == ["age_at_index"]
    assert payload["session_label"] == "Runtime benchmark test"


def test_job_intervals_and_overlap_use_server_timestamps() -> None:
    start = datetime(2026, 7, 25, 12, 0, tzinfo=timezone.utc)
    first = {
        "created_at": start.isoformat(),
        "started_at": (start + timedelta(seconds=2)).isoformat(),
        "completed_at": (start + timedelta(seconds=8)).isoformat(),
    }
    second = {
        "created_at": start.isoformat(),
        "started_at": (start + timedelta(seconds=3)).isoformat(),
        "completed_at": (start + timedelta(seconds=10)).isoformat(),
    }

    assert job_intervals(first) == (2.0, 6.0)
    assert timestamp_overlap_seconds([first, second]) == 5.0


def test_validate_result_requires_cache_contrast_and_concurrency() -> None:
    result = valid_result()

    validate_result(result)

    result["workloads"][1]["cached_at_submission"] = False
    with pytest.raises(RuntimeError, match="did not hit cache"):
        validate_result(result)


def test_summary_and_latex_keep_all_workloads() -> None:
    result = valid_result()

    rows = summary_rows(result)
    latex = render_latex(rows)

    assert len(rows) == len(EXPECTED_WORKLOADS)
    assert "Prespecified multiverse, 72 cells" in latex
    assert "\\label{tab:runtime-benchmark}" in latex


def valid_result() -> dict:
    workloads = []
    for benchmark_id in EXPECTED_WORKLOADS:
        summary = {}
        if benchmark_id == "batch_10":
            summary = {"total": 10}
        elif benchmark_id == "multiverse_72":
            summary = {"planned": 72}
        elif benchmark_id == "two_job_concurrency":
            summary = {
                "execution_overlap_seconds": 2.0,
                "peak_running_jobs_observed": 2,
            }
        workloads.append(
            {
                "benchmark_id": benchmark_id,
                "label": {
                    "multiverse_72": "Prespecified multiverse, 72 cells",
                }.get(benchmark_id, benchmark_id),
                "kind": "analysis",
                "workload_size": 1,
                "status": "completed",
                "cached_at_submission": (
                    benchmark_id == "single_cached_repeat"
                ),
                "timing": {
                    "wall_seconds": 1.0,
                    "queue_wait_seconds": 0.1,
                    "compute_seconds": 0.8,
                },
                "memory": {
                    "available": True,
                    "sample_count": 6,
                    "peak_total_bytes": 256 * 1024**2,
                    "peak_delta_bytes": 64 * 1024**2,
                },
                "result_summary": summary,
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": "test",
        "service": {
            "queue_limits": {
                "global_concurrency": 2,
            }
        },
        "workloads": workloads,
    }
