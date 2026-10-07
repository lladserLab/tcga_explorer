from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import Settings
from app.jobs import (
    compute_job_out,
    expire_compute_artifacts,
    publicize_download_links,
    submit_compute_job,
)
from app.hierarchical_pancancer_service import hierarchical_scan_identity
from app.models import ComputeJob, ComputeSubmission
from app.pipeline_versions import (
    HIERARCHICAL_PANCANCER_PIPELINE_VERSION,
    compute_cache_context,
)
from app.schemas import HierarchicalPanCancerRequest
from app.r_runner import stable_hash
from app.sample_population import SAMPLE_POPULATION_CONTRACT_VERSION


@pytest.fixture()
def job_db():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    ComputeJob.__table__.create(engine)
    ComputeSubmission.__table__.create(engine)
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
        compute_pancancer_hourly_limit=2,
        artifact_retention_days=90,
    )


def test_hierarchical_job_has_distinct_versioned_cache_and_result_route(
    job_db,
    public_settings,
) -> None:
    cache_context = compute_cache_context(
        "pancancer_hierarchical",
        data_version={"tcga": "fixture"},
    )
    assert cache_context == {
        "pipeline_version": HIERARCHICAL_PANCANCER_PIPELINE_VERSION,
        "sample_population_contract": SAMPLE_POPULATION_CONTRACT_VERSION,
        "data_version": {"tcga": "fixture"},
    }
    job = submit_compute_job(
        job_db,
        kind="pancancer_hierarchical",
        request_payload={"gene_symbol": "TP53"},
        client_key="contract-client",
        settings=public_settings,
        cache_context=cache_context,
    )
    job.status = "completed"
    job.result_id = "pch_0123456789abcdef01234567"
    job.result_json = {"scan_id": job.result_id, "status": "completed"}
    job_db.commit()

    output = compute_job_out(job, public_settings)

    assert output.result_url == (
        "https://example.test/tcga_explorer/api/v1/pancancer/"
        "hierarchical-survival/pch_0123456789abcdef01234567"
    )
    assert output.kind == "pancancer_hierarchical"


@pytest.mark.parametrize(
    ("alias", "canonical"),
    [("P53", "TP53"), ("HER2", "ERBB2")],
)
def test_gene_alias_and_canonical_symbol_share_estimand_but_not_provenance_cache(
    alias: str,
    canonical: str,
    job_db,
    public_settings,
) -> None:
    alias_request = HierarchicalPanCancerRequest(gene_symbol=alias)
    canonical_request = HierarchicalPanCancerRequest(gene_symbol=canonical)

    assert alias_request.gene_symbol == canonical
    assert alias_request.requested_gene_symbol == alias
    assert alias_request.resolved_gene_symbol == canonical
    assert canonical_request.requested_gene_symbol == canonical
    assert alias_request.model_dump(mode="json") == (
        canonical_request.model_dump(mode="json")
    )
    assert stable_hash(alias_request.model_dump(mode="json")) == stable_hash(
        canonical_request.model_dump(mode="json")
    )
    queued_alias = HierarchicalPanCancerRequest(
        **alias_request.worker_payload()
    )
    assert queued_alias.requested_gene_symbol == alias
    assert queued_alias.resolved_gene_symbol == canonical
    assert queued_alias.gene_resolution["resolution"] == "alias"
    assert queued_alias.model_dump(mode="json") == (
        canonical_request.model_dump(mode="json")
    )

    cache_context = compute_cache_context(
        "pancancer_hierarchical",
        data_version={"tcga": "alias-contract-fixture"},
    )
    alias_job = submit_compute_job(
        job_db,
        kind="pancancer_hierarchical",
        request_payload=alias_request.worker_payload(),
        client_key="alias-contract-client",
        settings=public_settings,
        cache_context=cache_context,
    )
    canonical_job = submit_compute_job(
        job_db,
        kind="pancancer_hierarchical",
        request_payload=canonical_request.worker_payload(),
        client_key="canonical-contract-client",
        settings=public_settings,
        cache_context=cache_context,
    )

    assert canonical_job.id != alias_job.id
    assert canonical_job.params_hash != alias_job.params_hash
    assert canonical_job.cached is False

    alias_identity = hierarchical_scan_identity(
        HierarchicalPanCancerRequest(**alias_job.request_payload),
        tcga_data_version={"tcga": "fixture"},
        repository_version={"registry": "fixture"},
    )
    canonical_identity = hierarchical_scan_identity(
        HierarchicalPanCancerRequest(**canonical_job.request_payload),
        tcga_data_version={"tcga": "fixture"},
        repository_version={"registry": "fixture"},
    )
    assert alias_identity["request"] == canonical_identity["request"]
    assert alias_identity["gene_resolution"]["requested_gene_symbol"] == alias
    assert canonical_identity["gene_resolution"]["requested_gene_symbol"] == (
        canonical
    )
    assert stable_hash(alias_identity) != stable_hash(canonical_identity)


def test_hierarchical_expiration_removes_only_its_family_directory(
    job_db,
    public_settings,
) -> None:
    scan_id = "pch_0123456789abcdef01234567"
    result_dir = (
        public_settings.artifact_dir / "pancancer_hierarchical" / scan_id
    )
    sibling_dir = public_settings.artifact_dir / "pancancer" / scan_id
    result_dir.mkdir(parents=True)
    sibling_dir.mkdir(parents=True)
    (result_dir / "result.json").write_text("{}", encoding="utf-8")
    (sibling_dir / "result.json").write_text("{}", encoding="utf-8")
    job = submit_compute_job(
        job_db,
        kind="pancancer_hierarchical",
        request_payload={"gene_symbol": "TP53"},
        client_key="expiration-client",
        settings=public_settings,
    )
    job.status = "completed"
    job.result_id = scan_id
    job.result_json = {"scan_id": scan_id, "status": "completed"}
    job.expires_at = (
        datetime.now(timezone.utc).replace(tzinfo=None)
        - timedelta(seconds=1)
    )
    job_db.commit()

    assert expire_compute_artifacts(job_db, public_settings) == 1
    assert not result_dir.exists()
    assert sibling_dir.exists()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("min_patients", 19),
        ("min_events", 9),
        ("min_censored", 4),
    ],
)
def test_primary_thresholds_cannot_be_relaxed_below_20_10_5(
    field: str,
    value: int,
) -> None:
    with pytest.raises(ValidationError):
        HierarchicalPanCancerRequest(
            gene_symbol="TP53",
            **{field: value},
        )


def test_hierarchical_cancer_selection_supports_128_without_changing_tcga() -> None:
    request = HierarchicalPanCancerRequest(
        gene_symbol="TP53",
        cancers=[f"EXT-{index:03d}" for index in range(128)],
    )

    assert len(request.cancers) == 128
    with pytest.raises(ValidationError):
        HierarchicalPanCancerRequest(
            gene_symbol="TP53",
            cancers=[f"EXT-{index:03d}" for index in range(129)],
        )


def test_public_download_conversion_keeps_hierarchical_route_inside_v1() -> None:
    assert publicize_download_links(
        {
            "ledger": (
                "/api/pancancer/hierarchical-survival/"
                "pch_0123456789abcdef01234567/download/ledger"
            )
        }
    ) == {
        "ledger": (
            "/api/v1/pancancer/hierarchical-survival/"
            "pch_0123456789abcdef01234567/download/ledger"
        )
    }
