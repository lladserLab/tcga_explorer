from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from app.config import Settings
from app.jobs import (
    ComputeQueueError,
    claim_next_compute_job,
    compute_job_out,
    expire_compute_artifacts,
    publicize_download_links,
    queue_summary,
    requeue_stale_jobs,
    submit_compute_job,
)
from app.models import ComputeJob


@pytest.fixture()
def job_db():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    ComputeJob.__table__.create(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as db:
        yield db
    engine.dispose()


@pytest.fixture()
def public_settings(tmp_path):
    return Settings(
        database_url="sqlite+pysqlite:///:memory:",
        public_base_url="https://example.test/tcga_explorer",
        artifact_dir=tmp_path / "artifacts",
        derived_expression_dir=tmp_path / "derived",
        compute_global_concurrency=2,
        compute_queue_max_size=50,
        compute_max_active_per_client=5,
        compute_single_hourly_limit=10,
        compute_batch_hourly_limit=2,
        compute_multiverse_hourly_limit=1,
        compute_pancancer_hourly_limit=2,
        artifact_retention_days=90,
    )


def test_identical_active_jobs_are_deduplicated(job_db, public_settings):
    first = submit_compute_job(
        job_db,
        kind="analysis",
        request_payload={"cohort": "TCGA-BRCA", "gene_symbol": "TP53"},
        client_key="rest:192.0.2.1",
        settings=public_settings,
    )
    second = submit_compute_job(
        job_db,
        kind="analysis",
        request_payload={"cohort": "TCGA-BRCA", "gene_symbol": "TP53"},
        client_key="rest:198.51.100.2",
        settings=public_settings,
    )

    assert second.id == first.id
    assert second.cached is True
    assert job_db.scalar(select(func.count()).select_from(ComputeJob)) == 1


def test_pipeline_or_data_change_invalidates_completed_job_cache(job_db, public_settings):
    payload = {"cohort": "TCGA-BRCA", "gene_symbol": "TP53"}
    first = submit_compute_job(
        job_db,
        kind="analysis",
        request_payload=payload,
        client_key="rest:192.0.2.1",
        settings=public_settings,
        cache_context={"pipeline_version": "v1", "data_version": {"rna": "snapshot-a"}},
    )
    first.status = "completed"
    first.expires_at = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=1)
    job_db.commit()

    pipeline_changed = submit_compute_job(
        job_db,
        kind="analysis",
        request_payload=payload,
        client_key="rest:192.0.2.1",
        settings=public_settings,
        cache_context={"pipeline_version": "v2", "data_version": {"rna": "snapshot-a"}},
    )
    data_changed = submit_compute_job(
        job_db,
        kind="analysis",
        request_payload=payload,
        client_key="rest:192.0.2.1",
        settings=public_settings,
        cache_context={"pipeline_version": "v2", "data_version": {"rna": "snapshot-b"}},
    )

    assert pipeline_changed.id != first.id
    assert data_changed.id not in {first.id, pipeline_changed.id}
    assert job_db.scalar(select(func.count()).select_from(ComputeJob)) == 3


def test_hourly_limit_returns_structured_queue_error(job_db, public_settings):
    public_settings.compute_single_hourly_limit = 1
    submit_compute_job(
        job_db,
        kind="analysis",
        request_payload={"gene_symbol": "TP53"},
        client_key="same-client",
        settings=public_settings,
    )

    with pytest.raises(ComputeQueueError) as raised:
        submit_compute_job(
            job_db,
            kind="analysis",
            request_payload={"gene_symbol": "BAP1"},
            client_key="same-client",
            settings=public_settings,
        )

    assert raised.value.code == "HOURLY_LIMIT"
    assert raised.value.status_code == 429
    assert raised.value.retry_after == 3600


def test_queue_summary_exposes_operational_limits(job_db, public_settings):
    summary = queue_summary(job_db, public_settings)

    assert summary["queued"] == 0
    assert summary["running"] == 0
    assert summary["limits"] == {
        "global_concurrency": 2,
        "queue_size": 50,
        "active_per_client": 5,
        "hourly_per_client": {
            "analysis_or_combined": 10,
            "batch": 2,
            "multiverse": 1,
            "pancancer": 2,
            "session": 5,
        },
        "request_size": {
            "batch_analyses": 25,
            "multiverse_specifications": 72,
        },
    }


def test_claim_and_recover_stale_job(job_db, public_settings):
    queued = submit_compute_job(
        job_db,
        kind="pancancer",
        request_payload={"gene_symbol": "BIRC5"},
        client_key="client",
        settings=public_settings,
    )
    claimed = claim_next_compute_job(job_db)

    assert claimed is not None
    assert claimed.id == queued.id
    assert claimed.status == "running"
    assert claimed.attempt_count == 1

    claimed.heartbeat_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=1)
    job_db.commit()
    public_settings.compute_stale_seconds = 60

    assert requeue_stale_jobs(job_db, public_settings) == 1
    job_db.refresh(claimed)
    assert claimed.status == "queued"


def test_expiration_removes_only_job_artifact_directory(job_db, public_settings):
    job = submit_compute_job(
        job_db,
        kind="analysis",
        request_payload={"gene_symbol": "TP53"},
        client_key="client",
        settings=public_settings,
    )
    analysis_id = "analysis-safe-id"
    artifact_dir = public_settings.artifact_dir / analysis_id
    artifact_dir.mkdir(parents=True)
    (artifact_dir / "metrics.json").write_text("{}", encoding="utf-8")

    job.status = "completed"
    job.result_id = analysis_id
    job.result_json = {"id": analysis_id}
    job.expires_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=1)
    job_db.commit()

    assert expire_compute_artifacts(job_db, public_settings) == 1
    job_db.refresh(job)
    assert job.status == "expired"
    assert not artifact_dir.exists()
    assert public_settings.artifact_dir.exists()


def test_shared_artifact_survives_while_another_job_retains_it(job_db, public_settings):
    analysis_id = "shared-analysis"
    artifact_dir = public_settings.artifact_dir / analysis_id
    artifact_dir.mkdir(parents=True)
    (artifact_dir / "metrics.json").write_text("{}", encoding="utf-8")

    direct = submit_compute_job(
        job_db,
        kind="analysis",
        request_payload={"gene_symbol": "TP53"},
        client_key="direct",
        settings=public_settings,
    )
    direct.status = "completed"
    direct.result_id = analysis_id
    direct.result_json = {"id": analysis_id}
    direct.expires_at = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=1)

    batch = submit_compute_job(
        job_db,
        kind="batch",
        request_payload={"analyses": [{"gene_symbol": "TP53"}]},
        client_key="batch",
        settings=public_settings,
    )
    batch.status = "completed"
    batch.result_id = batch.id
    batch.result_json = {
        "results": [{"status": "completed", "result": {"id": analysis_id}}],
    }
    batch.expires_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=1)
    job_db.commit()

    assert expire_compute_artifacts(job_db, public_settings) == 1
    assert artifact_dir.exists()

    direct.expires_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=1)
    job_db.commit()
    assert expire_compute_artifacts(job_db, public_settings) == 1
    assert not artifact_dir.exists()


def test_publication_example_artifact_is_pinned(job_db, public_settings, tmp_path):
    analysis_id = "paper-example-analysis"
    benchmark_dir = tmp_path / "benchmark"
    case_dir = benchmark_dir / "example_benchmark"
    case_dir.mkdir(parents=True)
    (case_dir / "summary.csv").write_text(
        "analysis_id,method\n"
        f"{analysis_id},median\n",
        encoding="utf-8",
    )
    public_settings.publication_benchmark_dir = benchmark_dir

    artifact_dir = public_settings.artifact_dir / analysis_id
    artifact_dir.mkdir(parents=True)
    (artifact_dir / "plot.png").write_bytes(b"png")

    job = submit_compute_job(
        job_db,
        kind="analysis",
        request_payload={"gene_symbol": "CDC20"},
        client_key="paper",
        settings=public_settings,
    )
    job.status = "completed"
    job.result_id = analysis_id
    job.result_json = {"id": analysis_id}
    job.expires_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=1)
    job_db.commit()

    assert expire_compute_artifacts(job_db, public_settings) == 0
    job_db.refresh(job)
    assert job.status == "completed"
    assert job.expires_at is None
    assert artifact_dir.exists()


def test_public_job_contract_and_download_link_rewrite(job_db, public_settings):
    job = submit_compute_job(
        job_db,
        kind="analysis",
        request_payload={"gene_symbol": "TP53"},
        client_key="client",
        settings=public_settings,
    )
    output = compute_job_out(job, public_settings)

    assert output.status_url == f"https://example.test/tcga_explorer/api/v1/jobs/{job.id}"
    assert output.result is None
    assert publicize_download_links(
        {
            "png": "/api/analyses/a/download/png",
            "stable": "/api/v1/analyses/a/download/png",
        }
    ) == {
        "png": "/api/v1/analyses/a/download/png",
        "stable": "/api/v1/analyses/a/download/png",
    }


def test_multiverse_job_exposes_result_and_retains_child_artifacts(
    job_db,
    public_settings,
):
    analysis_id = "multiverse-child"
    child_dir = public_settings.artifact_dir / analysis_id
    child_dir.mkdir(parents=True)
    (child_dir / "metrics.json").write_text("{}", encoding="utf-8")
    session_id = "mv_session"
    session_dir = public_settings.artifact_dir / "multiverse" / session_id
    session_dir.mkdir(parents=True)
    (session_dir / "multiverse_result.json").write_text("{}", encoding="utf-8")

    direct = submit_compute_job(
        job_db,
        kind="analysis",
        request_payload={"gene_symbol": "TP53"},
        client_key="direct",
        settings=public_settings,
    )
    direct.status = "completed"
    direct.result_id = analysis_id
    direct.result_json = {"id": analysis_id}
    direct.expires_at = (
        datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=1)
    )

    family = submit_compute_job(
        job_db,
        kind="multiverse",
        request_payload={"cohort": "TCGA-BRCA"},
        client_key="family",
        settings=public_settings,
    )
    family.status = "completed"
    family.result_id = session_id
    family.result_json = {
        "session_id": session_id,
        "specifications": [{"analysis_id": analysis_id}],
    }
    family.expires_at = (
        datetime.now(timezone.utc).replace(tzinfo=None)
        - timedelta(seconds=1)
    )
    job_db.commit()

    output = compute_job_out(family, public_settings)
    assert output.result_url == (
        "https://example.test/tcga_explorer/api/v1/analyses/"
        f"multiverses/{session_id}"
    )
    assert expire_compute_artifacts(job_db, public_settings) == 1
    assert child_dir.exists()
    assert not session_dir.exists()


def test_exploratory_session_job_exposes_and_expires_its_own_bundle(
    job_db,
    public_settings,
):
    report_id = "sh_test_session"
    report_dir = (
        public_settings.artifact_dir / "sessions" / report_id
    )
    report_dir.mkdir(parents=True)
    (report_dir / "session_report.json").write_text(
        "{}",
        encoding="utf-8",
    )
    job = submit_compute_job(
        job_db,
        kind="session",
        request_payload={
            "browser_session_id": "browser_session",
            "entries": [],
        },
        client_key="session-client",
        settings=public_settings,
    )
    job.status = "completed"
    job.result_id = report_id
    job.result_json = {"report_id": report_id}
    job.expires_at = (
        datetime.now(timezone.utc).replace(tzinfo=None)
        - timedelta(seconds=1)
    )
    job_db.commit()

    output = compute_job_out(job, public_settings)
    assert output.result_url == (
        "https://example.test/tcga_explorer/api/v1/analyses/"
        f"sessions/{report_id}"
    )
    assert expire_compute_artifacts(job_db, public_settings) == 1
    assert not report_dir.exists()
