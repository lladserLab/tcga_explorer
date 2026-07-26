#!/usr/bin/env python3
"""Benchmark public TCGA-TRACE workflows and freeze reproducible evidence."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import threading
import time
from typing import Any
import urllib.error
import urllib.request


ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = ROOT / "docs" / "publication" / "benchmark" / "runtime_concurrency"
RAW_PATH = OUTPUT_DIR / "benchmark_results.raw.json"
CANDIDATE_PATH = OUTPUT_DIR / "benchmark_results.candidate.json"
CSV_PATH = OUTPUT_DIR / "summary.csv"
SUMMARY_PATH = OUTPUT_DIR / "summary.md"
MANIFEST_PATH = OUTPUT_DIR / "manifest.json"
TABLE_PATH = (
    ROOT
    / "manuscript"
    / "bioinformatics_app_note"
    / "tables"
    / "runtime_concurrency_benchmark.tex"
)
SCHEMA_VERSION = "tcga-trace-runtime-concurrency-benchmark-v1"
ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
EXPECTED_WORKLOADS = (
    "single_uncached",
    "single_cached_repeat",
    "two_job_concurrency",
    "batch_10",
    "multiverse_72",
    "pancancer_all_cohorts",
)

BENCHMARK_GENES = [
    "CA9",
    "VEGFA",
    "SLC2A1",
    "LDHA",
    "PGK1",
    "BIRC5",
    "MKI67",
    "CD274",
    "PDCD1",
    "CXCL9",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Measure wall time, queue time and Docker memory for representative "
            "TCGA-TRACE public workflows."
        )
    )
    parser.add_argument(
        "--api-base-url",
        default="http://localhost:3000/tcga_explorer",
    )
    parser.add_argument(
        "--run-id",
        default=None,
        help="Optional stable run identifier. The default is a UTC timestamp.",
    )
    parser.add_argument("--poll-seconds", type=float, default=1.0)
    parser.add_argument("--timeout-seconds", type=float, default=3600.0)
    parser.add_argument(
        "--compose-project-dir",
        type=Path,
        default=ROOT,
        help="Compose project used to sample backend and worker memory.",
    )
    parser.add_argument(
        "--no-docker-memory",
        action="store_true",
        help="Run API timings without Docker cgroup memory sampling.",
    )
    parser.add_argument(
        "--reuse-raw",
        action="store_true",
        help="Validate frozen raw results and regenerate summary artifacts.",
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Validate frozen evidence without rewriting generated files.",
    )
    return parser.parse_args()


class ApiClient:
    def __init__(
        self,
        base_url: str,
        *,
        client_session_id: str | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.client_session_id = client_session_id

    def get(self, path: str) -> Any:
        return self._request("GET", path)

    def post(self, path: str, payload: dict[str, Any]) -> Any:
        return self._request("POST", path, payload)

    def _request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
    ) -> Any:
        body = (
            json.dumps(payload, separators=(",", ":")).encode("utf-8")
            if payload is not None
            else None
        )
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "tcga-trace-runtime-benchmark/1",
        }
        if self.client_session_id:
            headers["Mcp-Session-Id"] = self.client_session_id
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=body,
            method=method,
            headers=headers,
        )
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"HTTP {exc.code} for {path}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(
                f"Could not reach {self.base_url}{path}: {exc}"
            ) from exc


class DockerMemorySampler:
    """Sample aggregate backend/worker cgroup memory through Docker stats."""

    def __init__(self, compose_project_dir: Path, enabled: bool = True) -> None:
        self.compose_project_dir = compose_project_dir.resolve()
        self.enabled = enabled
        self.container_ids: list[str] = []
        self.container_names: dict[str, str] = {}
        self.baseline: dict[str, int] = {}
        self.peak: dict[str, int] = {}
        self.latest: dict[str, int] = {}
        self.peak_total = 0
        self.sample_count = 0
        self.error: str | None = None
        self._process: subprocess.Popen[str] | None = None
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    def start(self) -> None:
        if not self.enabled:
            self.error = "Docker memory sampling was disabled."
            return
        try:
            self.container_ids = self._compose_container_ids()
            if not self.container_ids:
                raise RuntimeError("No backend or worker containers were found.")
            for item in self._stats_snapshot():
                self._record(item, baseline=True)
            command = [
                "docker",
                "stats",
                "--format",
                "{{json .}}",
                *self.container_ids,
            ]
            self._process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
            self._thread = threading.Thread(
                target=self._consume,
                name="docker-memory-sampler",
                daemon=True,
            )
            self._thread.start()
        except Exception as exc:
            self.error = str(exc)

    def stop(self) -> dict[str, Any]:
        if self._process is not None:
            self._process.terminate()
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait(timeout=5)
        if self._thread is not None:
            self._thread.join(timeout=5)

        with self._lock:
            baseline_total = sum(self.baseline.values())
            peak_total = max(self.peak_total, baseline_total)
            containers = {
                name: {
                    "baseline_bytes": self.baseline.get(name),
                    "peak_bytes": self.peak.get(name),
                    "peak_delta_bytes": max(
                        0,
                        (self.peak.get(name) or 0)
                        - (self.baseline.get(name) or 0),
                    ),
                }
                for name in sorted(set(self.baseline) | set(self.peak))
            }
            return {
                "available": bool(containers) and self.error is None,
                "method": (
                    "Docker cgroup MemUsage sampled with streaming docker stats; "
                    "absolute peaks include the resident application baseline."
                ),
                "sampling_interval": "Docker stats stream, approximately 1 second",
                "sample_count": self.sample_count,
                "baseline_total_bytes": baseline_total or None,
                "peak_total_bytes": peak_total or None,
                "peak_delta_bytes": (
                    max(0, peak_total - baseline_total)
                    if peak_total and baseline_total
                    else None
                ),
                "containers": containers,
                "error": self.error,
            }

    def _compose_container_ids(self) -> list[str]:
        result = run_command(
            ["docker", "compose", "ps", "-q", "backend", "worker"],
            cwd=self.compose_project_dir,
        )
        return [line.strip() for line in result.splitlines() if line.strip()]

    def _stats_snapshot(self) -> list[dict[str, Any]]:
        output = run_command(
            [
                "docker",
                "stats",
                "--no-stream",
                "--format",
                "{{json .}}",
                *self.container_ids,
            ],
            cwd=self.compose_project_dir,
        )
        return [
            json.loads(line)
            for line in output.splitlines()
            if line.strip()
        ]

    def _consume(self) -> None:
        if self._process is None or self._process.stdout is None:
            return
        try:
            for line in self._process.stdout:
                item = parse_docker_stats_line(line)
                if item is None:
                    # Docker can emit a partial terminal line when the stats
                    # stream is intentionally terminated after the workload.
                    continue
                self._record(item, baseline=False)
        except Exception as exc:
            self.error = str(exc)

    def _record(self, item: dict[str, Any], *, baseline: bool) -> None:
        name = str(item.get("Name") or item.get("Container") or "unknown")
        memory = parse_memory_bytes(str(item.get("MemUsage") or ""))
        if memory is None:
            return
        with self._lock:
            if baseline or name not in self.baseline:
                self.baseline.setdefault(name, memory)
            self.latest[name] = memory
            self.peak[name] = max(memory, self.peak.get(name, 0))
            self.peak_total = max(self.peak_total, sum(self.latest.values()))
            self.sample_count += 1


def parse_memory_bytes(value: str) -> int | None:
    match = re.match(r"\s*([0-9.]+)\s*([KMGT]?i?B)\b", value)
    if not match:
        return None
    amount = float(match.group(1))
    unit = match.group(2)
    factors = {
        "B": 1,
        "KB": 1000,
        "MB": 1000**2,
        "GB": 1000**3,
        "TB": 1000**4,
        "KiB": 1024,
        "MiB": 1024**2,
        "GiB": 1024**3,
        "TiB": 1024**4,
    }
    factor = factors.get(unit)
    return round(amount * factor) if factor is not None else None


def parse_docker_stats_line(value: str) -> dict[str, Any] | None:
    clean_value = ANSI_ESCAPE_RE.sub("", value).strip()
    if not clean_value:
        return None
    try:
        parsed = json.loads(clean_value)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def main() -> int:
    args = parse_args()
    if args.check_only or args.reuse_raw:
        result = read_json(RAW_PATH)
        validate_result(result)
        if not args.check_only:
            write_outputs(result)
        print(
            f"Validated {RAW_PATH} with "
            f"{len(result.get('workloads') or [])} workloads."
        )
        return 0

    run_id = args.run_id or datetime.now(timezone.utc).strftime(
        "%Y%m%dT%H%M%S%fZ"
    )
    client_session_id = f"runtime-benchmark-{run_id}"
    client = ApiClient(
        args.api_base_url,
        client_session_id=client_session_id,
    )
    health = client.get("/api/v1/health")
    cohorts = [
        str(item["id"])
        for item in client.get("/api/v1/cohorts")
    ]
    memory_factory = lambda: DockerMemorySampler(  # noqa: E731
        args.compose_project_dir,
        enabled=not args.no_docker_memory,
    )

    single_payload = analysis_payload(
        gene="CA9",
        title=f"Runtime benchmark {run_id} single",
    )
    workloads = [
        run_job(
            client,
            benchmark_id="single_uncached",
            label="Single analysis, uncached result",
            submit_path="/api/v1/analyses",
            payload=single_payload,
            workload_size=1,
            poll_seconds=args.poll_seconds,
            timeout_seconds=args.timeout_seconds,
            memory_sampler=memory_factory(),
        ),
        run_job(
            client,
            benchmark_id="single_cached_repeat",
            label="Single analysis, exact cached repeat",
            submit_path="/api/v1/analyses",
            payload=single_payload,
            workload_size=1,
            poll_seconds=args.poll_seconds,
            timeout_seconds=args.timeout_seconds,
            memory_sampler=memory_factory(),
        ),
        run_concurrency_probe(
            client,
            run_id=run_id,
            poll_seconds=args.poll_seconds,
            timeout_seconds=args.timeout_seconds,
            memory_sampler=memory_factory(),
        ),
        run_job(
            client,
            benchmark_id="batch_10",
            label="Public batch, 10 analyses",
            submit_path="/api/v1/analyses/batch",
            payload=batch_payload(run_id),
            workload_size=10,
            poll_seconds=args.poll_seconds,
            timeout_seconds=args.timeout_seconds,
            memory_sampler=memory_factory(),
        ),
        run_job(
            client,
            benchmark_id="multiverse_72",
            label="Prespecified multiverse, 72 cells",
            submit_path="/api/v1/analyses/multiverse",
            payload=multiverse_payload(run_id),
            workload_size=72,
            poll_seconds=args.poll_seconds,
            timeout_seconds=args.timeout_seconds,
            memory_sampler=memory_factory(),
        ),
        run_job(
            client,
            benchmark_id="pancancer_all_cohorts",
            label=f"Pan-cancer scan, {len(cohorts)} requested cohorts",
            submit_path="/api/v1/pancancer/survival",
            payload=pancancer_payload(run_id, cohorts),
            workload_size=len(cohorts),
            poll_seconds=args.poll_seconds,
            timeout_seconds=args.timeout_seconds,
            memory_sampler=memory_factory(),
        ),
    ]

    result = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "api_base_url": args.api_base_url,
        "definitions": {
            "uncached": (
                "No completed compute job or analysis artifact matched the exact "
                "request. A unique display-only plot title or session label forced "
                "a cache miss without changing the statistical specification."
            ),
            "cached_repeat": (
                "The exact single-analysis request was resubmitted after completion "
                "and returned the retained compute job."
            ),
            "wall_time": (
                "Client-observed time from the start of POST submission through the "
                "first terminal job response."
            ),
            "queue_wait": "Job started_at minus created_at.",
            "compute_time": "Job completed_at minus started_at.",
            "memory": (
                "Backend plus worker Docker cgroup memory. Absolute peak includes "
                "resident baseline; delta is peak minus pre-request baseline."
            ),
            "cold_scope": (
                "Cold denotes an analysis-result cache miss, not a cold operating-"
                "system page cache or a fresh TCGA data import."
            ),
        },
        "service": {
            "health": health,
            "queue_limits": (health.get("queue") or {}).get("limits") or {},
            "benchmark_client_session_id": client_session_id,
            "client_limit_scope": (
                "All jobs in this run share one isolated session key, so the "
                "published per-client limits apply within the benchmark without "
                "being contaminated by unrelated local requests."
            ),
        },
        "environment": environment_snapshot(
            args.compose_project_dir,
            health,
        ),
        "workloads": workloads,
    }
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    write_json(CANDIDATE_PATH, result)
    validate_result(result)
    write_outputs(result)
    CANDIDATE_PATH.unlink(missing_ok=True)
    print(f"Wrote {RAW_PATH}")
    print(f"Wrote {SUMMARY_PATH}")
    print(f"Wrote {TABLE_PATH}")
    return 0


def run_job(
    client: ApiClient,
    *,
    benchmark_id: str,
    label: str,
    submit_path: str,
    payload: dict[str, Any],
    workload_size: int,
    poll_seconds: float,
    timeout_seconds: float,
    memory_sampler: DockerMemorySampler,
) -> dict[str, Any]:
    memory_sampler.start()
    try:
        wall_started = time.perf_counter()
        submit_started = time.perf_counter()
        submitted = client.post(submit_path, payload)
        submit_seconds = time.perf_counter() - submit_started
        terminal = wait_for_job(
            client,
            str(submitted["id"]),
            poll_seconds=poll_seconds,
            timeout_seconds=timeout_seconds,
        )
        wall_seconds = time.perf_counter() - wall_started
    finally:
        memory = memory_sampler.stop()
    if terminal.get("status") != "completed":
        raise RuntimeError(
            f"{benchmark_id} ended with {terminal.get('status')}: "
            f"{terminal.get('error')}"
        )
    cached = bool(submitted.get("cached"))
    queue_seconds, compute_seconds = job_intervals(terminal)
    return {
        "benchmark_id": benchmark_id,
        "label": label,
        "kind": terminal.get("kind"),
        "workload_size": workload_size,
        "status": terminal.get("status"),
        "cached_at_submission": cached,
        "job_id": terminal.get("id"),
        "result_id": terminal.get("result_id"),
        "timing": {
            "wall_seconds": round(wall_seconds, 6),
            "submit_seconds": round(submit_seconds, 6),
            "queue_wait_seconds": None if cached else queue_seconds,
            "compute_seconds": None if cached else compute_seconds,
            "retained_source_queue_wait_seconds": (
                queue_seconds if cached else None
            ),
            "retained_source_compute_seconds": (
                compute_seconds if cached else None
            ),
        },
        "memory": memory,
        "result_summary": summarize_job_result(
            benchmark_id,
            terminal.get("result") or {},
        ),
    }


def run_concurrency_probe(
    client: ApiClient,
    *,
    run_id: str,
    poll_seconds: float,
    timeout_seconds: float,
    memory_sampler: DockerMemorySampler,
) -> dict[str, Any]:
    requests = [
        analysis_payload(
            gene="VEGFA",
            title=f"Runtime benchmark {run_id} concurrency A",
        ),
        analysis_payload(
            gene="SLC2A1",
            title=f"Runtime benchmark {run_id} concurrency B",
        ),
    ]
    memory_sampler.start()
    try:
        wall_started = time.perf_counter()
        submitted = [
            client.post("/api/v1/analyses", payload)
            for payload in requests
        ]
        terminal: dict[str, dict[str, Any]] = {}
        peak_running = 0
        deadline = time.monotonic() + timeout_seconds
        while len(terminal) < len(submitted):
            for job in submitted:
                job_id = str(job["id"])
                if job_id in terminal:
                    continue
                status = client.get(f"/api/v1/jobs/{job_id}")
                if status.get("status") in {"completed", "failed", "expired"}:
                    terminal[job_id] = status
            queue = (client.get("/api/v1/health").get("queue") or {})
            peak_running = max(peak_running, int(queue.get("running") or 0))
            if len(terminal) == len(submitted):
                break
            if time.monotonic() >= deadline:
                raise TimeoutError("Two-job concurrency probe timed out.")
            time.sleep(max(0.25, poll_seconds))
        wall_seconds = time.perf_counter() - wall_started
    finally:
        memory = memory_sampler.stop()
    failed = [
        job
        for job in terminal.values()
        if job.get("status") != "completed"
    ]
    if failed:
        raise RuntimeError(f"Concurrency probe failed: {failed}")
    ordered = [terminal[str(item["id"])] for item in submitted]
    intervals = [job_intervals(item) for item in ordered]
    overlap_seconds = timestamp_overlap_seconds(ordered)
    return {
        "benchmark_id": "two_job_concurrency",
        "label": "Two independent single analyses",
        "kind": "concurrency_probe",
        "workload_size": 2,
        "status": "completed",
        "cached_at_submission": any(
            bool(item.get("cached")) for item in submitted
        ),
        "job_id": None,
        "result_id": None,
        "job_ids": [item.get("id") for item in ordered],
        "timing": {
            "wall_seconds": round(wall_seconds, 6),
            "submit_seconds": None,
            "queue_wait_seconds": round(
                max(value[0] or 0 for value in intervals),
                6,
            ),
            "compute_seconds": round(
                max(value[1] or 0 for value in intervals),
                6,
            ),
            "retained_source_queue_wait_seconds": None,
            "retained_source_compute_seconds": None,
            "execution_overlap_seconds": overlap_seconds,
        },
        "memory": memory,
        "result_summary": {
            "submitted_jobs": 2,
            "completed_jobs": 2,
            "peak_running_jobs_observed": peak_running,
            "execution_overlap_seconds": overlap_seconds,
        },
    }


def wait_for_job(
    client: ApiClient,
    job_id: str,
    *,
    poll_seconds: float,
    timeout_seconds: float,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    while True:
        job = client.get(f"/api/v1/jobs/{job_id}")
        if job.get("status") in {"completed", "failed", "expired"}:
            return job
        if time.monotonic() >= deadline:
            raise TimeoutError(f"Compute job {job_id} timed out.")
        time.sleep(max(0.25, poll_seconds))


def job_intervals(job: dict[str, Any]) -> tuple[float | None, float | None]:
    created = parse_timestamp(job.get("created_at"))
    started = parse_timestamp(job.get("started_at"))
    completed = parse_timestamp(job.get("completed_at"))
    queue_seconds = (
        round((started - created).total_seconds(), 6)
        if created and started
        else None
    )
    compute_seconds = (
        round((completed - started).total_seconds(), 6)
        if started and completed
        else None
    )
    return queue_seconds, compute_seconds


def timestamp_overlap_seconds(jobs: list[dict[str, Any]]) -> float | None:
    if len(jobs) != 2:
        return None
    starts = [parse_timestamp(job.get("started_at")) for job in jobs]
    ends = [parse_timestamp(job.get("completed_at")) for job in jobs]
    if any(value is None for value in starts + ends):
        return None
    overlap = (
        min(ends) - max(starts)
    ).total_seconds()
    return round(max(0.0, overlap), 6)


def parse_timestamp(value: Any) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def analysis_payload(*, gene: str, title: str) -> dict[str, Any]:
    return {
        "cohort": "TCGA-KIRC",
        "gene_symbol": gene,
        "signature_method": "single",
        "signature_genes": [],
        "endpoint": "OS",
        "expression_scale": "log2_tpm",
        "cutpoint_method": "median",
        "adjustment_covariates": ["age_at_index"],
        "filters": {},
        "time_unit": "days",
        "show_confidence_interval": False,
        "show_risk_table": False,
        "plot_style": {
            "show_title": False,
            "plot_title": title,
            "show_grid": False,
            "plot_aspect": "rectangular",
        },
    }


def batch_payload(run_id: str) -> dict[str, Any]:
    return {
        "analyses": [
            analysis_payload(
                gene=gene,
                title=f"Runtime benchmark {run_id} batch {index:02d}",
            )
            for index, gene in enumerate(BENCHMARK_GENES, start=1)
        ],
        "max_concurrency": 1,
    }


def multiverse_payload(run_id: str) -> dict[str, Any]:
    return {
        "cohort": "TCGA-LIHC",
        "genes": [
            {"gene_symbol": "CDC20", "weight": 1.0},
            {"gene_symbol": "BIRC5", "weight": -1.0},
        ],
        "signature_name": "Runtime CDC20-BIRC5",
        "endpoints": ["OS", "PFI", "DFI", "DSS"],
        "scoring_methods": ["mean", "zscore", "weighted"],
        "cutpoint_methods": [
            "maxstat",
            "median",
            "tertiles",
            "upper_quartile",
            "upper_lower_quartile",
            "percentile",
        ],
        "expression_scale": "log2_tpm",
        "custom_percentile": 60,
        "filters": {},
        "adjustment_covariates": ["age_at_index"],
        "time_unit": "days",
        "show_confidence_interval": False,
        "plot_style": {
            "show_title": False,
            "plot_title": f"Runtime benchmark {run_id} multiverse",
            "show_grid": False,
            "plot_aspect": "rectangular",
        },
        "session_label": f"Runtime benchmark {run_id}",
    }


def pancancer_payload(run_id: str, cohorts: list[str]) -> dict[str, Any]:
    if not cohorts:
        raise ValueError("Pan-cancer benchmark requires at least one cohort.")
    offset = int(hashlib.sha256(run_id.encode("utf-8")).hexdigest()[:8], 16)
    offset %= len(cohorts)
    rotated = cohorts[offset:] + cohorts[:offset]
    return {
        "gene_symbol": "BIRC5",
        "signature_method": "single",
        "signature_genes": [],
        "index_cohort": rotated[0],
        "cohorts": rotated,
        "endpoint": "OS",
        "endpoint_mode": "same_endpoint",
        "expression_scale": "log2_tpm",
        "filters": {},
        "min_patients": 10,
        "min_events": 5,
        "fdr_threshold": 0.10,
    }


def summarize_job_result(
    benchmark_id: str,
    result: dict[str, Any],
) -> dict[str, Any]:
    if benchmark_id.startswith("single_"):
        metrics = result.get("metrics") or {}
        return {
            "patients": metrics.get("n_patients"),
            "events": metrics.get("n_events"),
            "pipeline_version": metrics.get("pipeline_version")
            or (result.get("request") or {}).get("pipeline_version"),
        }
    if benchmark_id == "batch_10":
        return {
            "total": result.get("total"),
            "completed": result.get("completed"),
            "failed": result.get("failed"),
            "effective_child_concurrency": result.get("max_concurrency"),
        }
    if benchmark_id == "multiverse_72":
        summary = result.get("summary") or {}
        return {
            "planned": summary.get("planned"),
            "completed": summary.get("completed"),
            "failed": summary.get("failed"),
            "pipeline_version": result.get("pipeline_version"),
        }
    if benchmark_id == "pancancer_all_cohorts":
        summary = result.get("summary") or {}
        return {
            "cohorts_requested": summary.get("total_cohorts"),
            "cohorts_completed": summary.get("completed"),
            "cohorts_skipped": summary.get("skipped"),
            "pipeline_version": result.get("pipeline_version"),
        }
    return {}


def environment_snapshot(
    compose_project_dir: Path,
    health: dict[str, Any],
) -> dict[str, Any]:
    host_memory = host_memory_bytes()
    snapshot = {
        "host": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "processor": host_cpu_model(),
            "logical_cpus": os.cpu_count(),
            "physical_memory_bytes": host_memory,
            "model": host_model(),
        },
        "python": platform.python_version(),
        "docker": docker_snapshot(compose_project_dir),
        "source": {
            "git_commit": optional_command(
                ["git", "rev-parse", "HEAD"],
                cwd=ROOT,
            ),
            "dirty": bool(
                optional_command(
                    ["git", "status", "--porcelain"],
                    cwd=ROOT,
                )
            ),
        },
        "pipeline_versions": health.get("pipeline_versions") or {},
        "data_manifest_hash": (
            health.get("data_dates") or {}
        ).get("data_manifest_hash"),
    }
    return snapshot


def host_cpu_model() -> str | None:
    if platform.system() == "Darwin":
        return optional_command(["sysctl", "-n", "machdep.cpu.brand_string"])
    cpuinfo = Path("/proc/cpuinfo")
    if cpuinfo.exists():
        for line in cpuinfo.read_text(encoding="utf-8").splitlines():
            if line.lower().startswith("model name"):
                return line.split(":", 1)[-1].strip()
    return platform.processor() or None


def host_model() -> str | None:
    if platform.system() == "Darwin":
        return optional_command(["sysctl", "-n", "hw.model"])
    return None


def host_memory_bytes() -> int | None:
    if platform.system() == "Darwin":
        value = optional_command(["sysctl", "-n", "hw.memsize"])
        return int(value) if value and value.isdigit() else None
    meminfo = Path("/proc/meminfo")
    if meminfo.exists():
        match = re.search(
            r"^MemTotal:\s+(\d+)\s+kB$",
            meminfo.read_text(encoding="utf-8"),
            flags=re.MULTILINE,
        )
        if match:
            return int(match.group(1)) * 1024
    return None


def docker_snapshot(compose_project_dir: Path) -> dict[str, Any]:
    info_raw = optional_command(
        [
            "docker",
            "info",
            "--format",
            (
                '{"server_version":{{json .ServerVersion}},'
                '"architecture":{{json .Architecture}},'
                '"operating_system":{{json .OperatingSystem}},'
                '"cpus":{{json .NCPU}},"memory_bytes":{{json .MemTotal}}}'
            ),
        ],
        cwd=compose_project_dir,
    )
    info = json.loads(info_raw) if info_raw else {}
    containers = {}
    for service in ("backend", "worker"):
        container_id = optional_command(
            ["docker", "compose", "ps", "-q", service],
            cwd=compose_project_dir,
        )
        if not container_id:
            continue
        inspect_raw = optional_command(
            [
                "docker",
                "inspect",
                "--format",
                (
                    '{"name":{{json .Name}},"image":{{json .Image}},'
                    '"memory_limit":{{json .HostConfig.Memory}},'
                    '"nano_cpus":{{json .HostConfig.NanoCpus}}}'
                ),
                container_id,
            ],
            cwd=compose_project_dir,
        )
        if inspect_raw:
            containers[service] = json.loads(inspect_raw)
    return {**info, "containers": containers}


def validate_result(result: dict[str, Any]) -> None:
    if result.get("schema_version") != SCHEMA_VERSION:
        raise RuntimeError("Unexpected runtime benchmark schema.")
    workloads = result.get("workloads") or []
    by_id = {row.get("benchmark_id"): row for row in workloads}
    if tuple(row for row in EXPECTED_WORKLOADS if row not in by_id):
        missing = [row for row in EXPECTED_WORKLOADS if row not in by_id]
        raise RuntimeError(f"Runtime benchmark is missing workloads: {missing}")
    if by_id["single_uncached"].get("cached_at_submission"):
        raise RuntimeError("The uncached single analysis unexpectedly hit cache.")
    if not by_id["single_cached_repeat"].get("cached_at_submission"):
        raise RuntimeError("The exact single-analysis repeat did not hit cache.")
    if (
        by_id["multiverse_72"].get("result_summary", {}).get("planned")
        != 72
    ):
        raise RuntimeError("The multiverse benchmark did not plan 72 cells.")
    if (
        by_id["batch_10"].get("result_summary", {}).get("total")
        != 10
    ):
        raise RuntimeError("The batch benchmark did not contain 10 analyses.")
    if any(row.get("status") != "completed" for row in workloads):
        raise RuntimeError("At least one runtime benchmark workload failed.")
    if not (result.get("service") or {}).get("queue_limits"):
        raise RuntimeError("Queue limits were not recorded from public health.")
    for row in workloads:
        memory = row.get("memory") or {}
        if not memory.get("available"):
            raise RuntimeError(
                f"{row.get('benchmark_id')} has no Docker memory evidence: "
                f"{memory.get('error')}"
            )
        if not memory.get("peak_total_bytes"):
            raise RuntimeError(
                f"{row.get('benchmark_id')} has no peak memory measurement."
            )
        if (
            (row.get("timing") or {}).get("wall_seconds", 0) >= 2
            and int(memory.get("sample_count") or 0) <= 2
        ):
            raise RuntimeError(
                f"{row.get('benchmark_id')} has no in-workload memory samples."
            )
    concurrency = by_id["two_job_concurrency"].get("result_summary") or {}
    if (concurrency.get("execution_overlap_seconds") or 0) <= 0:
        raise RuntimeError("The two-job probe did not observe execution overlap.")


def write_outputs(result: dict[str, Any]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    TABLE_PATH.parent.mkdir(parents=True, exist_ok=True)
    write_json(RAW_PATH, result)
    rows = summary_rows(result)
    write_csv(CSV_PATH, rows)
    SUMMARY_PATH.write_text(
        render_markdown(result, rows),
        encoding="utf-8",
    )
    TABLE_PATH.write_text(
        render_latex(rows),
        encoding="utf-8",
    )
    manifest = {
        "schema_version": "tcga-trace-runtime-benchmark-manifest-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "run_id": result["run_id"],
        "files": {
            str(path.relative_to(ROOT)): {
                "bytes": path.stat().st_size,
                "sha256": file_sha256(path),
            }
            for path in (RAW_PATH, CSV_PATH, SUMMARY_PATH, TABLE_PATH)
        },
    }
    write_json(MANIFEST_PATH, manifest)


def summary_rows(result: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for workload in result.get("workloads") or []:
        timing = workload.get("timing") or {}
        memory = workload.get("memory") or {}
        rows.append(
            {
                "benchmark_id": workload.get("benchmark_id"),
                "workflow": workload.get("label"),
                "units": workload.get("workload_size"),
                "cached": workload.get("cached_at_submission"),
                "wall_seconds": timing.get("wall_seconds"),
                "queue_wait_seconds": timing.get("queue_wait_seconds"),
                "compute_seconds": timing.get("compute_seconds"),
                "peak_memory_mib": bytes_to_mib(
                    memory.get("peak_total_bytes")
                ),
                "peak_delta_mib": bytes_to_mib(
                    memory.get("peak_delta_bytes")
                ),
                "status": workload.get("status"),
            }
        )
    return rows


def render_markdown(
    result: dict[str, Any],
    rows: list[dict[str, Any]],
) -> str:
    environment = result.get("environment") or {}
    host = environment.get("host") or {}
    docker = environment.get("docker") or {}
    limits = (result.get("service") or {}).get("queue_limits") or {}
    lines = [
        "# Runtime and concurrency benchmark",
        "",
        f"- Run ID: `{result.get('run_id')}`",
        f"- Generated: `{result.get('generated_at')}`",
        f"- API: `{result.get('api_base_url')}`",
        f"- Source commit: `{(environment.get('source') or {}).get('git_commit')}`",
        f"- Dirty worktree: `{(environment.get('source') or {}).get('dirty')}`",
        f"- Host: {host.get('model') or host.get('system')} / {host.get('processor')} / {host.get('logical_cpus')} logical CPUs / {format_mib(host.get('physical_memory_bytes'))}",
        f"- Docker engine: {docker.get('server_version')} / {docker.get('architecture')} / {docker.get('cpus')} CPUs / {format_mib(docker.get('memory_bytes'))}",
        f"- Pipeline versions: `{json.dumps(environment.get('pipeline_versions') or {}, sort_keys=True)}`",
        f"- Data manifest: `{environment.get('data_manifest_hash')}`",
        "",
        "## Definitions",
        "",
        *[
            f"- **{key.replace('_', ' ').title()}:** {value}"
            for key, value in (result.get("definitions") or {}).items()
        ],
        "",
        "## Queue contract",
        "",
        f"- Global worker concurrency: {limits.get('global_concurrency')}",
        f"- Queue capacity: {limits.get('queue_size')}",
        f"- Active jobs per anonymous client: {limits.get('active_per_client')}",
        f"- Hourly limits per client: `{json.dumps(limits.get('hourly_per_client') or {}, sort_keys=True)}`",
        f"- Request-size limits: `{json.dumps(limits.get('request_size') or {}, sort_keys=True)}`",
        "- Public batch children execute serially inside one worker slot, so a batch never bypasses the global concurrency ceiling.",
        "",
        "## Results",
        "",
        "| Workflow | Units | Cached | Wall (s) | Queue (s) | Compute (s) | Peak MiB | Delta MiB | Status |",
        "| --- | ---: | :---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in rows:
        lines.append(
            f"| {row['workflow']} | {row['units']} | "
            f"{'yes' if row['cached'] else 'no'} | "
            f"{format_number(row['wall_seconds'])} | "
            f"{format_number(row['queue_wait_seconds'])} | "
            f"{format_number(row['compute_seconds'])} | "
            f"{format_number(row['peak_memory_mib'])} | "
            f"{format_number(row['peak_delta_mib'])} | {row['status']} |"
        )
    lines.extend(
        [
            "",
            "Memory is the aggregate backend plus worker Docker cgroup usage. "
            "The approximately one-second sampler can miss sub-second spikes; "
            "reported values are observed peaks rather than allocator maxima.",
            "",
        ]
    )
    return "\n".join(lines)


def render_latex(rows: list[dict[str, Any]]) -> str:
    body = "\n".join(
        " & ".join(
            [
                latex_escape(str(row["workflow"])),
                str(row["units"]),
                "yes" if row["cached"] else "no",
                format_number(row["wall_seconds"]),
                format_number(row["queue_wait_seconds"]),
                format_number(row["compute_seconds"]),
                format_number(row["peak_memory_mib"]),
            ]
        )
        + r" \\"
        for row in rows
    )
    return (
        "% Generated by scripts/publication/run_runtime_benchmark.py\n"
        "\\begin{table*}[t]\n"
        "\\centering\n"
        "\\caption{Observed runtime and memory for representative public "
        "TCGA-TRACE workflows. Uncached denotes an analysis-result cache miss, "
        "not a cold operating-system or data-import cache. Memory is aggregate "
        "backend plus worker Docker cgroup usage.}\n"
        "\\label{tab:runtime-benchmark}\n"
        "\\scriptsize\n"
        "\\begin{tabular}{lrrrrrr}\n"
        "\\toprule\n"
        "Workflow & Units & Cached & Wall (s) & Queue (s) & Compute (s) & "
        "Peak MiB \\\\\n"
        "\\midrule\n"
        f"{body}\n"
        "\\bottomrule\n"
        "\\end{tabular}\n"
        "\\end{table*}\n"
    )


def latex_escape(value: str) -> str:
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
    }
    return "".join(replacements.get(character, character) for character in value)


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, allow_nan=False, indent=2)
        + "\n",
        encoding="utf-8",
    )


def read_json(path: Path) -> Any:
    if not path.exists():
        raise RuntimeError(f"Missing frozen runtime benchmark: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def run_command(command: list[str], *, cwd: Path) -> str:
    result = subprocess.run(
        command,
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Command failed ({' '.join(command)}): "
            f"{result.stderr.strip() or result.stdout.strip()}"
        )
    return result.stdout.strip()


def optional_command(command: list[str], *, cwd: Path | None = None) -> str | None:
    try:
        return run_command(command, cwd=cwd or ROOT) or None
    except (OSError, RuntimeError, subprocess.TimeoutExpired):
        return None


def bytes_to_mib(value: Any) -> float | None:
    if value in (None, ""):
        return None
    return round(float(value) / (1024**2), 2)


def format_mib(value: Any) -> str:
    converted = bytes_to_mib(value)
    return f"{converted:.0f} MiB" if converted is not None else "not available"


def format_number(value: Any) -> str:
    if value in (None, ""):
        return "--"
    number = float(value)
    if abs(number) >= 100:
        return f"{number:.1f}"
    if abs(number) >= 10:
        return f"{number:.2f}"
    return f"{number:.3f}"


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
