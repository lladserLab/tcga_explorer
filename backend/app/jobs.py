from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import shutil
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.models import ComputeJob
from app.paper_examples import publication_example_result_ids
from app.pipeline_versions import compute_cache_context as default_compute_cache_context
from app.r_runner import stable_hash
from app.schemas import ComputeJobOut, ErrorDetail


TERMINAL_JOB_STATUSES = {"completed", "failed", "expired"}
ACTIVE_JOB_STATUSES = {"queued", "running"}
JOB_KINDS = {
    "analysis",
    "combined",
    "batch",
    "multiverse",
    "pancancer",
    "session",
}


def utc_now() -> datetime:
    """Return naive UTC for the existing TIMESTAMP WITHOUT TIME ZONE schema."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class ComputeQueueError(RuntimeError):
    def __init__(self, code: str, message: str, status_code: int, retry_after: int | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.retry_after = retry_after


def anonymous_client_key(value: str) -> str:
    normalized = value.strip() or "anonymous"
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def submit_compute_job(
    db: Session,
    *,
    kind: str,
    request_payload: dict[str, Any],
    client_key: str,
    settings: Settings | None = None,
    cache_context: dict[str, Any] | None = None,
) -> ComputeJob:
    settings = settings or get_settings()
    if kind not in JOB_KINDS:
        raise ValueError(f"Unsupported compute job kind: {kind}")

    now = utc_now()
    payload_hash = stable_hash(
        {
            "kind": kind,
            "request": request_payload,
            "cache_context": cache_context or default_compute_cache_context(kind),
        }
    )
    existing = db.scalar(
        select(ComputeJob)
        .where(ComputeJob.kind == kind)
        .where(ComputeJob.params_hash == payload_hash)
    )
    if existing is not None:
        if existing.status in ACTIVE_JOB_STATUSES:
            existing.cached = True
            db.commit()
            db.refresh(existing)
            return existing
        if existing.status == "completed" and (existing.expires_at is None or existing.expires_at > now):
            existing.cached = True
            db.commit()
            db.refresh(existing)
            return existing

    client_hash = anonymous_client_key(client_key)
    active_count = int(
        db.scalar(
            select(func.count())
            .select_from(ComputeJob)
            .where(ComputeJob.client_key_hash == client_hash)
            .where(ComputeJob.status.in_(ACTIVE_JOB_STATUSES))
        )
        or 0
    )
    if active_count >= settings.compute_max_active_per_client:
        raise ComputeQueueError(
            "CLIENT_ACTIVE_LIMIT",
            f"At most {settings.compute_max_active_per_client} active compute jobs are allowed per anonymous client.",
            429,
            retry_after=60,
        )

    queued_count = int(
        db.scalar(
            select(func.count()).select_from(ComputeJob).where(ComputeJob.status.in_(ACTIVE_JOB_STATUSES))
        )
        or 0
    )
    if queued_count >= settings.compute_queue_max_size:
        raise ComputeQueueError(
            "QUEUE_FULL",
            "The public compute queue is full. Retry after current analyses finish.",
            503,
            retry_after=120,
        )

    one_hour_ago = now - timedelta(hours=1)
    hourly_count = int(
        db.scalar(
            select(func.count())
            .select_from(ComputeJob)
            .where(ComputeJob.client_key_hash == client_hash)
            .where(ComputeJob.created_at >= one_hour_ago)
            .where(ComputeJob.kind == kind)
        )
        or 0
    )
    hourly_limit = _hourly_limit(kind, settings)
    if hourly_count >= hourly_limit:
        raise ComputeQueueError(
            "HOURLY_LIMIT",
            f"The anonymous hourly limit for {kind} jobs is {hourly_limit}.",
            429,
            retry_after=3600,
        )

    if existing is None:
        job = ComputeJob(
            id=uuid.uuid4().hex,
            kind=kind,
            params_hash=payload_hash,
            client_key_hash=client_hash,
            status="queued",
            request_payload=request_payload,
            result_json=None,
            result_id=None,
            error_json=None,
            cached=False,
            created_at=now,
        )
        db.add(job)
    else:
        job = existing
        job.client_key_hash = client_hash
        job.status = "queued"
        job.request_payload = request_payload
        job.result_json = None
        job.result_id = None
        job.error_json = None
        job.attempt_count = 0
        job.cached = False
        job.created_at = now
        job.started_at = None
        job.heartbeat_at = None
        job.completed_at = None
        job.expires_at = None

    try:
        db.commit()
    except IntegrityError:
        # Two anonymous callers can submit an identical payload at the same
        # instant. The unique hash is the authority; return the winner rather
        # than surfacing an internal error to the second caller.
        db.rollback()
        concurrent = db.scalar(
            select(ComputeJob)
            .where(ComputeJob.kind == kind)
            .where(ComputeJob.params_hash == payload_hash)
        )
        if concurrent is None:
            raise
        concurrent.cached = True
        db.commit()
        db.refresh(concurrent)
        return concurrent
    db.refresh(job)
    return job


def _hourly_limit(kind: str, settings: Settings) -> int:
    if kind == "batch":
        return settings.compute_batch_hourly_limit
    if kind == "multiverse":
        return settings.compute_multiverse_hourly_limit
    if kind == "pancancer":
        return settings.compute_pancancer_hourly_limit
    if kind == "session":
        return settings.compute_session_hourly_limit
    return settings.compute_single_hourly_limit


def claim_next_compute_job(db: Session) -> ComputeJob | None:
    job = db.scalar(
        select(ComputeJob)
        .where(ComputeJob.status == "queued")
        .order_by(ComputeJob.created_at, ComputeJob.id)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    if job is None:
        db.rollback()
        return None
    now = utc_now()
    job.status = "running"
    job.started_at = now
    job.heartbeat_at = now
    job.attempt_count += 1
    job.cached = False
    db.commit()
    db.refresh(job)
    return job


def touch_compute_job(job_id: str, db: Session) -> None:
    job = db.get(ComputeJob, job_id)
    if job is not None and job.status == "running":
        job.heartbeat_at = utc_now()
        db.commit()


def finish_compute_job(
    job_id: str,
    *,
    result: dict[str, Any],
    result_id: str | None,
    db: Session,
    settings: Settings | None = None,
) -> ComputeJob:
    settings = settings or get_settings()
    job = db.get(ComputeJob, job_id)
    if job is None:
        raise RuntimeError(f"Compute job {job_id} disappeared while running.")
    now = utc_now()
    job.status = "completed"
    job.result_json = publicize_download_links(result)
    job.result_id = result_id
    job.error_json = None
    job.completed_at = now
    job.heartbeat_at = now
    job.expires_at = now + timedelta(days=settings.artifact_retention_days)
    db.commit()
    db.refresh(job)
    return job


def fail_compute_job(
    job_id: str,
    *,
    code: str,
    message: str,
    details: dict[str, Any] | None,
    db: Session,
) -> ComputeJob:
    job = db.get(ComputeJob, job_id)
    if job is None:
        raise RuntimeError(f"Compute job {job_id} disappeared while failing.")
    now = utc_now()
    job.status = "failed"
    job.error_json = {
        "code": code,
        "message": message,
        "details": details or {},
    }
    job.completed_at = now
    job.heartbeat_at = now
    db.commit()
    db.refresh(job)
    return job


def requeue_stale_jobs(db: Session, settings: Settings | None = None) -> int:
    settings = settings or get_settings()
    cutoff = utc_now() - timedelta(seconds=settings.compute_stale_seconds)
    jobs = list(
        db.scalars(
            select(ComputeJob)
            .where(ComputeJob.status == "running")
            .where(ComputeJob.heartbeat_at.is_not(None))
            .where(ComputeJob.heartbeat_at < cutoff)
        ).all()
    )
    requeued = 0
    for job in jobs:
        if job.attempt_count < settings.compute_max_attempts:
            job.status = "queued"
            job.started_at = None
            job.heartbeat_at = None
            requeued += 1
        else:
            job.status = "failed"
            job.completed_at = utc_now()
            job.error_json = {
                "code": "WORKER_LOST",
                "message": "The compute worker stopped before this job completed.",
                "details": {"attempt_count": job.attempt_count},
            }
    db.commit()
    return requeued


def queue_summary(
    db: Session,
    settings: Settings | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    counts = dict(
        db.execute(
            select(ComputeJob.status, func.count()).group_by(ComputeJob.status)
        ).all()
    )
    return {
        "available": True,
        "queued": int(counts.get("queued", 0)),
        "running": int(counts.get("running", 0)),
        "limits": {
            "global_concurrency": settings.compute_global_concurrency,
            "queue_size": settings.compute_queue_max_size,
            "active_per_client": settings.compute_max_active_per_client,
            "hourly_per_client": {
                "analysis_or_combined": settings.compute_single_hourly_limit,
                "batch": settings.compute_batch_hourly_limit,
                "multiverse": settings.compute_multiverse_hourly_limit,
                "pancancer": settings.compute_pancancer_hourly_limit,
                "session": settings.compute_session_hourly_limit,
            },
            "request_size": {
                "batch_analyses": settings.public_batch_max_analyses,
                "multiverse_specifications": (
                    settings.public_multiverse_max_analyses
                ),
            },
        },
    }


def compute_job_out(job: ComputeJob, settings: Settings | None = None) -> ComputeJobOut:
    settings = settings or get_settings()
    base = settings.public_base_url.rstrip("/")
    status_url = f"{base}/api/v1/jobs/{job.id}"
    result_url = None
    if job.status == "completed":
        if job.kind in {"analysis", "combined"} and job.result_id:
            result_url = f"{base}/api/v1/analyses/{job.result_id}"
        elif job.kind == "batch":
            result_url = f"{base}/api/v1/analyses/batches/{job.id}"
        elif job.kind == "multiverse" and job.result_id:
            result_url = f"{base}/api/v1/analyses/multiverses/{job.result_id}"
        elif job.kind == "pancancer" and job.result_id:
            result_url = f"{base}/api/v1/pancancer/survival/{job.result_id}"
        elif job.kind == "session" and job.result_id:
            result_url = (
                f"{base}/api/v1/analyses/sessions/{job.result_id}"
            )

    error = None
    if job.error_json:
        error = ErrorDetail(
            code=str(job.error_json.get("code") or "COMPUTE_FAILED"),
            message=str(job.error_json.get("message") or "Compute job failed."),
            details=job.error_json.get("details") or {},
        )
    elif job.status == "expired":
        error = ErrorDetail(
            code="ARTIFACT_EXPIRED",
            message="Generated artifacts expired after the public retention period. Submit the same request to regenerate them.",
        )

    return ComputeJobOut(
        id=job.id,
        kind=job.kind,
        status=job.status,
        cached=bool(job.cached),
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
        expires_at=job.expires_at,
        status_url=status_url,
        result_url=result_url,
        result_id=job.result_id,
        result=job.result_json if job.status == "completed" else None,
        error=error,
    )


def publicize_download_links(value: Any) -> Any:
    if isinstance(value, str):
        if value.startswith("/api/") and not value.startswith("/api/v1/"):
            return f"/api/v1/{value.removeprefix('/api/')}"
        return value
    if isinstance(value, list):
        return [publicize_download_links(item) for item in value]
    if isinstance(value, dict):
        return {key: publicize_download_links(item) for key, item in value.items()}
    return value


def compute_jobs_referencing_analysis(db: Session, analysis_id: str) -> list[ComputeJob]:
    references = list(
        db.scalars(
            select(ComputeJob)
            .where(ComputeJob.kind.in_({"analysis", "combined"}))
            .where(ComputeJob.result_id == analysis_id)
        ).all()
    )
    family_jobs = db.scalars(
        select(ComputeJob)
        .where(ComputeJob.kind.in_({"batch", "multiverse"}))
        .where(ComputeJob.result_json.is_not(None))
    ).all()
    for family_job in family_jobs:
        payload = family_job.result_json or {}
        if family_job.kind == "batch":
            result_ids = {
                str((item.get("result") or {}).get("id") or "")
                for item in payload.get("results", [])
            }
        else:
            result_ids = {
                str(item.get("analysis_id") or "")
                for item in payload.get("specifications", [])
            }
        if analysis_id in result_ids:
            references.append(family_job)
    return references


def job_retains_artifacts(job: ComputeJob, now: datetime | None = None) -> bool:
    now = now or utc_now()
    if job.status in ACTIVE_JOB_STATUSES:
        return True
    return job.status == "completed" and (job.expires_at is None or job.expires_at > now)


def expire_compute_artifacts(db: Session, settings: Settings | None = None) -> int:
    settings = settings or get_settings()
    now = utc_now()
    pinned_result_ids = publication_example_result_ids(
        settings.publication_benchmark_dir
    )
    jobs = list(
        db.scalars(
            select(ComputeJob)
            .where(ComputeJob.status == "completed")
            .where(ComputeJob.expires_at.is_not(None))
            .where(ComputeJob.expires_at <= now)
        ).all()
    )
    expired = 0
    for job in jobs:
        if _job_result_ids(job) & pinned_result_ids:
            job.expires_at = None
            continue
        _remove_job_artifacts(job, settings, db)
        job.status = "expired"
        expired += 1
    db.commit()
    return expired


def _job_result_ids(job: ComputeJob) -> set[str]:
    result_ids: set[str] = set()
    if job.result_id:
        result_ids.add(str(job.result_id))
    if job.kind == "batch":
        for item in (job.result_json or {}).get("results", []):
            result = item.get("result") or {}
            analysis_id = result.get("id")
            if analysis_id:
                result_ids.add(str(analysis_id))
    elif job.kind == "multiverse":
        for item in (job.result_json or {}).get("specifications", []):
            analysis_id = item.get("analysis_id")
            if analysis_id:
                result_ids.add(str(analysis_id))
    return result_ids


def _remove_job_artifacts(job: ComputeJob, settings: Settings, db: Session) -> None:
    analysis_ids: set[str] = set()
    if job.kind in {"analysis", "combined"} and job.result_id:
        analysis_ids.add(job.result_id)
    elif job.kind == "batch":
        for item in (job.result_json or {}).get("results", []):
            result = item.get("result") or {}
            analysis_id = result.get("id")
            if analysis_id:
                analysis_ids.add(str(analysis_id))
    elif job.kind == "multiverse":
        for item in (job.result_json or {}).get("specifications", []):
            analysis_id = item.get("analysis_id")
            if analysis_id:
                analysis_ids.add(str(analysis_id))

    for analysis_id in analysis_ids:
        retained_elsewhere = any(
            reference.id != job.id and job_retains_artifacts(reference)
            for reference in compute_jobs_referencing_analysis(db, analysis_id)
        )
        if retained_elsewhere:
            continue
        candidate = settings.artifact_dir / analysis_id
        if _is_safe_child(candidate, settings.artifact_dir) and candidate.is_dir():
            shutil.rmtree(candidate)

    if job.kind == "pancancer" and job.result_id:
        candidate = settings.artifact_dir / "pancancer" / job.result_id
        if _is_safe_child(candidate, settings.artifact_dir / "pancancer") and candidate.is_dir():
            shutil.rmtree(candidate)
    elif job.kind == "multiverse" and job.result_id:
        candidate = settings.artifact_dir / "multiverse" / job.result_id
        if _is_safe_child(candidate, settings.artifact_dir / "multiverse") and candidate.is_dir():
            shutil.rmtree(candidate)
    elif job.kind == "session" and job.result_id:
        candidate = settings.artifact_dir / "sessions" / job.result_id
        if _is_safe_child(candidate, settings.artifact_dir / "sessions") and candidate.is_dir():
            shutil.rmtree(candidate)


def _is_safe_child(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return path.resolve() != parent.resolve()
