"""Run against an isolated PostgreSQL test DB; never the application's DB URL."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import importlib.util
import os
from pathlib import Path
import threading
import uuid

import pytest
from sqlalchemy import create_engine, func, inspect, select, text
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.orm import Session
from sqlalchemy.schema import CreateSchema, DropSchema

from app.config import Settings
from app.jobs import ComputeQueueError, submit_compute_job
from app.models import ComputeJob, ComputeSubmission

TEST_URL = os.environ.get("TRACE_LIFECYCLE_TEST_POSTGRES_URL")
pytestmark = pytest.mark.skipif(not TEST_URL, reason="Isolated PostgreSQL test URL not supplied")


@pytest.fixture()
def postgres_queue():
    admin = create_engine(TEST_URL)
    if not (admin.url.database or "").endswith("_test"):
        raise ValueError("Concurrency checks require a dedicated *_test database")
    schema = "trace_test_" + uuid.uuid4().hex
    with admin.begin() as connection:
        connection.execute(CreateSchema(schema))
    engine = create_engine(TEST_URL, connect_args={"options": f"-csearch_path={schema}"})
    try:
        ComputeJob.__table__.create(engine)
        ComputeSubmission.__table__.create(engine)
        yield engine
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(DropSchema(schema, cascade=True))
        admin.dispose()


@pytest.mark.parametrize("boundary", ["hourly", "active", "queue", "deduplicate"])
def test_simultaneous_admissions_cannot_exceed_limits(postgres_queue, boundary):
    settings = Settings(_env_file=None, compute_single_hourly_limit=1 if boundary == "hourly" else 100,
        compute_max_active_per_client=1 if boundary == "active" else 100,
        compute_queue_max_size=1 if boundary == "queue" else 100)
    barrier = threading.Barrier(6)

    def submit(index):
        with Session(postgres_queue, expire_on_commit=False) as db:
            barrier.wait(timeout=15)
            try:
                job = submit_compute_job(db, kind="analysis",
                    request_payload={"gene_symbol": "TP53" if boundary == "deduplicate" else f"GENE{index}"},
                    client_key=f"client{index}" if boundary == "queue" else "same-client", settings=settings)
                return job.id, None
            except ComputeQueueError as error:
                return None, error.code

    with ThreadPoolExecutor(max_workers=6) as pool:
        responses = list(pool.map(submit, range(6)))
    with Session(postgres_queue) as db:
        assert db.scalar(select(func.count()).select_from(ComputeJob)) == 1
        assert db.scalar(select(func.count()).select_from(ComputeSubmission)) == 1
    if boundary == "deduplicate":
        assert len({job_id for job_id, _ in responses}) == 1
        assert all(error is None for _, error in responses)
    else:
        assert sum(job_id is not None for job_id, _ in responses) == 1
        expected = {"hourly": "HOURLY_LIMIT", "active": "CLIENT_ACTIVE_LIMIT", "queue": "QUEUE_FULL"}[boundary]
        assert [error for _, error in responses if error] == [expected] * 5


@pytest.mark.parametrize("legacy", [True, False])
def test_migration_on_postgres_preserves_jobs_and_observable_quota(postgres_queue, legacy):
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    with Session(postgres_queue) as db:
        for name, minutes in [("recent", 5), ("old", 90)]:
            db.add(ComputeJob(id=name, kind="analysis", params_hash=name, client_key_hash="fixture",
                status="completed", request_payload={}, result_json={"unchanged": True},
                created_at=now - timedelta(minutes=minutes)))
        db.commit()
    path = Path(__file__).parents[1] / "alembic/versions/20260907_05_compute_attempts_and_submissions.py"
    spec = importlib.util.spec_from_file_location("compute_pg_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    with postgres_queue.begin() as connection:
        if legacy:
            connection.execute(text("DROP TABLE compute_submissions"))
            connection.execute(text("ALTER TABLE compute_jobs DROP COLUMN attempt_token"))
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
            migration.upgrade()
        assert "attempt_token" in {c["name"] for c in inspect(connection).get_columns("compute_jobs")}
        assert connection.execute(text("SELECT id FROM compute_submissions")).scalars().all() == ["legacy-recent"]
        results = connection.execute(text("SELECT result_json FROM compute_jobs")).scalars().all()
        assert results == [{"unchanged": True}, {"unchanged": True}]
