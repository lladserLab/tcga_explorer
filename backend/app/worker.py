from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import logging
import signal
import threading
import time
from typing import Any

from fastapi import HTTPException

from app.config import get_settings
from app.database import SessionLocal, init_db, wait_for_database
from app.jobs import (
    claim_next_compute_job,
    expire_compute_artifacts,
    fail_compute_job,
    finish_compute_job,
    requeue_stale_jobs,
    touch_compute_job,
)
from app.models import ComputeJob
from app.signature_scoring import SignatureScoringTimeout
from app.schemas import (
    AnalysisBatchRequest,
    AnalysisRequest,
    CombinedSignatureAnalysisRequest,
    ExpressionComparisonRequest,
    ExploratorySessionExportRequest,
    GseaAnalysisRequest,
    HierarchicalPanCancerRequest,
    MultiverseAnalysisRequest,
    PanCancerSurvivalRequest,
    SignaturePanelAnalysisRequest,
)
from app.user_datasets import expire_user_datasets


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("tcga_trace.worker")
settings = get_settings()
shutdown_event = threading.Event()


def _signal_handler(signum, _frame) -> None:
    logger.info("Received signal %s; stopping after active jobs finish.", signum)
    shutdown_event.set()


def _heartbeat(job_id: str, attempt_token: str, stop_event: threading.Event) -> None:
    while not stop_event.wait(30):
        try:
            with SessionLocal() as db:
                if not touch_compute_job(job_id, db, attempt_token=attempt_token):
                    return
        except Exception:
            logger.exception("Unable to update heartbeat for job %s", job_id)


def _execute_job(job: ComputeJob) -> tuple[dict[str, Any], str | None]:
    # Importing here avoids loading the web application before the worker has
    # initialized its database connection.
    from app.main import (
        _create_analysis,
        _create_analysis_batch,
        _create_combined_analysis,
        _create_expression_comparison,
        _create_exploratory_session,
        _create_gsea_analysis,
        _create_hierarchical_pancancer,
        _create_multiverse_analysis,
        _create_pancancer_survival,
        _create_signature_panel_analysis,
    )

    if job.kind == "analysis":
        request = AnalysisRequest(**job.request_payload)
        with SessionLocal() as db:
            result = _create_analysis(request, db)
        return result.model_dump(mode="json"), result.id

    if job.kind == "combined":
        request = CombinedSignatureAnalysisRequest(**job.request_payload)
        with SessionLocal() as db:
            result = _create_combined_analysis(request, db)
        return result.model_dump(mode="json"), result.id
    if job.kind == "signature_panel":
        request = SignaturePanelAnalysisRequest(**job.request_payload)
        with SessionLocal() as db:
            result = _create_signature_panel_analysis(request, db)
        return result.model_dump(mode="json"), result.id

    if job.kind == "batch":
        request = AnalysisBatchRequest(**job.request_payload)
        # Each worker thread already occupies one of the global compute slots.
        # Run child analyses serially inside that slot so the process-wide
        # concurrency ceiling is never exceeded.
        request.max_concurrency = 1
        result = _create_analysis_batch(request)
        return result.model_dump(mode="json"), job.id

    if job.kind == "multiverse":
        request = MultiverseAnalysisRequest(**job.request_payload)
        with SessionLocal() as db:
            result = _create_multiverse_analysis(request, db)
        return result.model_dump(mode="json"), result.session_id

    if job.kind == "pancancer":
        request = PanCancerSurvivalRequest(**job.request_payload)
        with SessionLocal() as db:
            result = _create_pancancer_survival(request, db)
        return result.model_dump(mode="json"), result.scan_id

    if job.kind == "pancancer_hierarchical":
        request = HierarchicalPanCancerRequest(**job.request_payload)
        with SessionLocal() as db:
            result = _create_hierarchical_pancancer(request, db)
        return result.model_dump(mode="json"), result.scan_id

    if job.kind == "session":
        request = ExploratorySessionExportRequest(
            **job.request_payload
        )
        with SessionLocal() as db:
            result = _create_exploratory_session(request, db)
        return result.model_dump(mode="json"), result.report_id

    if job.kind == "gsea":
        request = GseaAnalysisRequest(**job.request_payload)
        with SessionLocal() as db:
            result = _create_gsea_analysis(request, db)
        return result.model_dump(mode="json"), result.gsea_id

    if job.kind == "expression_comparison":
        request = ExpressionComparisonRequest(**job.request_payload)
        with SessionLocal() as db:
            result = _create_expression_comparison(request, db)
        return result.model_dump(mode="json"), result.comparison_id

    raise ValueError(f"Unsupported compute job kind: {job.kind}")


def _failure_payload(exc: Exception) -> tuple[str, str, dict[str, Any]]:
    if isinstance(exc, HTTPException):
        detail = exc.detail
        if isinstance(detail, dict):
            return (
                str(detail.get("code") or f"HTTP_{exc.status_code}"),
                str(detail.get("message") or detail),
                {"status_code": exc.status_code},
            )
        return f"HTTP_{exc.status_code}", str(detail), {"status_code": exc.status_code}
    if isinstance(exc, ValueError):
        message = str(exc) or "The analysis request is not valid."
        return "INVALID_ANALYSIS", message[:1000], {}
    if isinstance(exc, SignatureScoringTimeout):
        return "SIGNATURE_SCORING_TIMEOUT", str(exc), {"timeout_seconds": 900}
    if isinstance(exc, RuntimeError) and "Rscript failed" in str(exc):
        return (
            "R_FAILED",
            "The statistical engine could not complete this analysis.",
            {},
        )
    return (
        "COMPUTE_FAILED",
        "The analysis could not be completed. Contact the service operator with the job ID.",
        {},
    )


def _worker_loop(worker_index: int) -> None:
    logger.info("Compute worker slot %s started.", worker_index)
    while not shutdown_event.is_set():
        try:
            with SessionLocal() as db:
                job = claim_next_compute_job(db)
        except Exception:
            logger.exception("Worker slot %s could not claim a job.", worker_index)
            shutdown_event.wait(2)
            continue

        if job is None:
            shutdown_event.wait(1)
            continue

        logger.info("Worker slot %s running %s job %s.", worker_index, job.kind, job.id)
        heartbeat_stop = threading.Event()
        heartbeat_thread = threading.Thread(
            target=_heartbeat,
            args=(job.id, job.attempt_token, heartbeat_stop),
            name=f"heartbeat-{job.id}",
            daemon=True,
        )
        heartbeat_thread.start()
        try:
            result, result_id = _execute_job(job)
            with SessionLocal() as db:
                finished = finish_compute_job(
                    job.id,
                    result=result,
                    result_id=result_id,
                    db=db,
                    attempt_token=job.attempt_token,
                    settings=settings,
                )
            if finished is not None:
                logger.info("Compute job %s completed.", job.id)
            else:
                logger.info("Discarded completion from superseded attempt for %s.", job.id)
        except Exception as exc:
            code, message, details = _failure_payload(exc)
            logger.exception("Compute job %s failed with %s.", job.id, code)
            with SessionLocal() as db:
                fail_compute_job(
                    job.id,
                    code=code,
                    message=message,
                    details=details,
                    db=db,
                    attempt_token=job.attempt_token,
                )
        finally:
            heartbeat_stop.set()
            heartbeat_thread.join(timeout=2)


def main() -> int:
    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)
    wait_for_database()
    init_db()
    with SessionLocal() as db:
        requeued = requeue_stale_jobs(db, settings)
        expired = expire_compute_artifacts(db, settings)
        expired_user_datasets = expire_user_datasets(db, settings)
    logger.info(
        "Worker startup recovered %s jobs, expired %s artifact sets and removed %s private datasets.",
        requeued,
        expired,
        expired_user_datasets,
    )

    cleanup_deadline = time.monotonic() + 3600
    with ThreadPoolExecutor(
        max_workers=max(1, settings.compute_global_concurrency),
        thread_name_prefix="compute",
    ) as executor:
        futures = [
            executor.submit(_worker_loop, index + 1)
            for index in range(max(1, settings.compute_global_concurrency))
        ]
        while not shutdown_event.wait(5):
            if time.monotonic() >= cleanup_deadline:
                try:
                    with SessionLocal() as db:
                        expire_compute_artifacts(db, settings)
                        expire_user_datasets(db, settings)
                        requeue_stale_jobs(db, settings)
                except Exception:
                    logger.exception("Scheduled compute maintenance failed.")
                cleanup_deadline = time.monotonic() + 3600
            failed = [future for future in futures if future.done() and future.exception() is not None]
            if failed:
                for future in failed:
                    logger.error("Worker slot stopped unexpectedly: %s", future.exception())
                shutdown_event.set()
                break

    logger.info("Compute worker stopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
