"""Private reports, quota retries and stale workers use isolated databases."""
from datetime import datetime, timedelta, timezone
import importlib.util
import io
import threading
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi import Request, Response
import pytest
from sqlalchemy import create_engine, func, inspect, select, text
from sqlalchemy.orm import Session

from app import main
from app.database import Base
from app.jobs import (
    ComputeQueueError, claim_next_compute_job, expire_compute_artifacts,
    fail_compute_job, finish_compute_job, requeue_stale_jobs,
    submit_compute_job, touch_compute_job,
)
from app.models import ComputeJob, ComputeSubmission, RepositoryDataset
from app.schemas import ExploratorySessionExportRequest
from app.user_datasets import (
    UserDatasetError, create_user_dataset, delete_user_dataset, expire_user_datasets,
    private_dataset_ids, user_dataset_ids_in_payload, user_dataset_access_token_hash,
)
from test_user_datasets import (
    _database, _settings, _seed_cancer, _genes_by_rows_table, _clinical_table, _mapping,
)


@pytest.fixture()
def lifecycle(tmp_path):
    settings = _settings(tmp_path)
    settings.compute_single_hourly_limit = 2
    settings.compute_stale_seconds = 60
    with _database()() as db:
        yield db, settings


def enqueue(db, settings, **kwargs):
    return submit_compute_job(db, kind=kwargs.pop("kind", "analysis"),
        request_payload=kwargs.pop("payload", {"gene_symbol": "TP53"}),
        client_key=kwargs.pop("client", "fixture"), settings=settings, **kwargs)


def fail_current(db, job):
    return fail_compute_job(job.id, db=db, attempt_token=job.attempt_token,
        code="FIXTURE_FAILURE", message="Synthetic failure", details={})


def complete_current(db, settings, job, result_id="fixture-result"):
    return finish_compute_job(job.id, db=db, attempt_token=job.attempt_token,
        result={"id": result_id}, result_id=result_id, settings=settings)


def test_failed_retries_count_each_submission(lifecycle):
    db, settings = lifecycle
    ids = []
    for _ in range(2):
        ids.append(enqueue(db, settings).id)
        fail_current(db, claim_next_compute_job(db))
    assert len(set(ids)) == 1  # Cache identity may be reused; admission events may not.
    assert db.scalar(select(func.count()).select_from(ComputeSubmission)) == 2
    with pytest.raises(ComputeQueueError) as error:
        enqueue(db, settings)
    assert error.value.code == "HOURLY_LIMIT"
    assert error.value.details["used"] == 2
    assert 3590 <= error.value.retry_after <= 3600
    assert db.scalar(select(func.count()).select_from(ComputeSubmission)) == 2


def test_cache_hits_are_free_and_rolling_window_uses_events(lifecycle):
    db, settings = lifecycle
    settings.compute_single_hourly_limit = 1
    first = enqueue(db, settings)
    assert enqueue(db, settings, client="another-client").id == first.id
    complete_current(db, settings, claim_next_compute_job(db))
    assert enqueue(db, settings).id == first.id
    assert db.scalar(select(func.count()).select_from(ComputeSubmission)) == 1
    with pytest.raises(ComputeQueueError):
        enqueue(db, settings, payload={"gene_symbol": "EGFR"})
    event = db.scalar(select(ComputeSubmission))
    event.created_at -= timedelta(hours=2)
    db.commit()
    assert enqueue(db, settings, payload={"gene_symbol": "EGFR"}).status == "queued"
    expire_compute_artifacts(db, settings)
    assert db.scalar(select(func.count()).select_from(ComputeSubmission)) == 1


@pytest.mark.parametrize("phase", ["queued", "running", "completed"])
def test_superseded_attempt_cannot_heartbeat_finish_or_fail(lifecycle, phase):
    db, settings = lifecycle
    enqueue(db, settings)
    first = claim_next_compute_job(db)
    old_token = first.attempt_token
    first.heartbeat_at -= timedelta(hours=1)
    db.commit()
    assert requeue_stale_jobs(db, settings) == 1
    if phase != "queued":
        current = claim_next_compute_job(db)
        assert current.attempt_token != old_token
        if phase == "completed":
            complete_current(db, settings, current, result_id="new-result")
    job = db.get(ComputeJob, first.id)
    before = (job.status, job.heartbeat_at, job.result_json, job.error_json)
    assert touch_compute_job(job.id, db, attempt_token=old_token) is False
    assert finish_compute_job(job.id, db=db, attempt_token=old_token,
        result={"id": "old-result"}, result_id="old-result", settings=settings) is None
    assert fail_compute_job(job.id, db=db, attempt_token=old_token,
        code="OLD_FAILURE", message="Old attempt", details={}) is None
    db.refresh(job)
    assert (job.status, job.heartbeat_at, job.result_json, job.error_json) == before


def test_manual_retry_cannot_reuse_an_old_attempt_token(lifecycle):
    db, settings = lifecycle
    enqueue(db, settings)
    old = claim_next_compute_job(db)
    old_token = old.attempt_token
    fail_current(db, old)
    enqueue(db, settings)
    current = claim_next_compute_job(db)
    assert current.attempt_count == 1
    assert current.attempt_token != old_token
    assert touch_compute_job(current.id, db, attempt_token=old_token) is False
    assert touch_compute_job(current.id, db, attempt_token=current.attempt_token) is True
    assert complete_current(db, settings, current).status == "completed"


@pytest.mark.parametrize("fails", [False, True])
def test_worker_supplies_its_claimed_attempt_to_finalization(lifecycle, monkeypatch, fails):
    from app import worker
    from sqlalchemy.orm import sessionmaker

    db, settings = lifecycle
    queued = enqueue(db, settings)
    stop = threading.Event()
    monkeypatch.setattr(worker, "shutdown_event", stop)
    monkeypatch.setattr(worker, "SessionLocal", sessionmaker(bind=db.get_bind()))
    monkeypatch.setattr(worker, "settings", settings)

    def execute(job):
        assert job.attempt_token
        stop.set()
        if fails:
            raise ValueError("Synthetic invalid request")
        return {"id": "worker-result"}, "worker-result"

    monkeypatch.setattr(worker, "_execute_job", execute)
    worker._worker_loop(1)
    db.refresh(queued)
    assert queued.status == ("failed" if fails else "completed")
    if fails:
        assert queued.error_json["code"] == "INVALID_ANALYSIS"
    else:
        assert queued.result_id == "worker-result"


def private_session(db, settings, monkeypatch):
    _seed_cancer(db)
    token = "private-session-fixture-token"
    dataset = create_user_dataset(db, settings,
        expression_source=io.BytesIO(_genes_by_rows_table()),
        clinical_source=io.BytesIO(_clinical_table()), mapping=_mapping(),
        owner_key_hash="fixture", access_token_hash=user_dataset_access_token_hash(token))
    source = ComputeJob(id="a" * 32, kind="analysis", params_hash="b" * 64,
        client_key_hash="fixture", status="completed",
        request_payload={"dataset_id": dataset["id"], "gene_symbol": "TP53"},
        result_json={"id": "source-fixture"}, result_id="source-fixture")
    db.add(source)
    db.get(RepositoryDataset, dataset["id"]).expires_at = (
        datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(minutes=5))
    db.commit()
    body = ExploratorySessionExportRequest(browser_session_id="browser-session-fixture", entries=[{
        "event_id": "event-fixture", "job_id": source.id, "recorded_at": datetime.now(timezone.utc)}])
    request = Request({"type": "http", "method": "POST", "path": "/api/v1/analyses/sessions",
        "client": ("192.0.2.1", 1234), "headers": [(b"authorization", f"Bearer {token}".encode())]})
    monkeypatch.setattr(main, "settings", settings)
    monkeypatch.setattr(main, "current_data_version", lambda db: {"fixture": "v1"})
    result = main.submit_public_exploratory_session(body, request, Response(), db)
    return dataset["id"], db.get(ComputeJob, result.id)


def test_private_session_lease_retention_and_explicit_deletion(lifecycle, monkeypatch):
    db, settings = lifecycle
    dataset_id, session = private_session(db, settings, monkeypatch)
    assert private_dataset_ids(session.request_payload) == {dataset_id}
    assert user_dataset_ids_in_payload(session.request_payload) == {dataset_id}
    assert db.get(RepositoryDataset, dataset_id).expires_at > (
        datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=23))
    with pytest.raises(UserDatasetError, match="cannot be deleted"):
        delete_user_dataset(db, settings, dataset_id)
    db.rollback()
    claimed = claim_next_compute_job(db)
    report_dir = settings.artifact_dir / "sessions" / "sh_fixture"
    report_dir.mkdir(parents=True)
    (report_dir / "session_report.json").write_text('{"synthetic": true}')
    completed = complete_current(db, settings, claimed, "sh_fixture")
    assert completed.expires_at - completed.completed_at == timedelta(hours=24)
    delete_user_dataset(db, settings, dataset_id)
    assert db.get(ComputeJob, session.id) is None
    assert not report_dir.exists()


def test_expiry_protects_queued_private_sessions_then_cleans_completed(lifecycle, monkeypatch):
    db, settings = lifecycle
    dataset_id, session = private_session(db, settings, monkeypatch)
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None)
    dataset = db.get(RepositoryDataset, dataset_id)
    dataset.expires_at = cutoff - timedelta(seconds=1)
    db.commit()
    assert expire_user_datasets(db, settings, now=cutoff) == 0
    assert dataset.expires_at == cutoff + timedelta(hours=24)
    complete_current(db, settings, claim_next_compute_job(db), "sh_fixture")
    dataset.expires_at = cutoff - timedelta(seconds=1)
    db.commit()
    assert expire_user_datasets(db, settings, now=cutoff) == 1
    assert db.get(ComputeJob, session.id) is None


def test_migration_adds_fence_and_backfills_only_observable_recent_submissions():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    ComputeJob.__table__.create(engine)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    with Session(engine) as db:
        for name, age in [("recent", 10), ("old", 90)]:
            db.add(ComputeJob(id=name, kind="analysis", params_hash=name,
                client_key_hash="fixture", status="failed", request_payload={},
                created_at=now - timedelta(minutes=age)))
        db.commit()
    path = Path(__file__).parents[1] / "alembic/versions/20260907_05_compute_attempts_and_submissions.py"
    spec = importlib.util.spec_from_file_location("compute_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE compute_jobs DROP COLUMN attempt_token"))
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
            migration.upgrade()  # Safe with create_all and already-created tables.
        assert "attempt_token" in {c["name"] for c in inspect(connection).get_columns("compute_jobs")}
        assert connection.execute(text("SELECT id FROM compute_submissions")).scalars().all() == ["legacy-recent"]
        assert connection.execute(text("SELECT COUNT(*) FROM compute_jobs")).scalar() == 2
    engine.dispose()
