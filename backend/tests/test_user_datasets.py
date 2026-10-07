from __future__ import annotations

import io
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi import HTTPException, Request, Response
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker

from app.config import Settings
from app.database import Base
from app import main as main_module
from app import user_datasets as user_datasets_module
from app.models import (
    CancerType,
    ComputeJob,
    RepositoryDataset,
    RepositoryEndpointDefinition,
    RepositoryExpressionLayer,
    RepositoryPatient,
)
from app.repository.service import (
    list_repository_datasets,
    repository_capabilities,
    repository_expression_layers,
    repository_gene_expression,
    repository_samples,
    resolve_repository_context,
)
from app.repository.capabilities import RANK_SIGNATURE_MAXIMUM_MATRIX_ENTRIES
from app.gsea import select_gsea_samples
from app.clinical_grouping import (
    clinical_grouping_context,
    filter_samples_by_clinical_variable,
    resolve_clinical_grouping_variable,
)
from app.schemas import AnalysisFilters, AnalysisRequest, UserDatasetMapping
from app.survival import ClinicalOutcome, filter_sample_candidates
from app.user_datasets import (
    UserDatasetError,
    authorize_user_dataset,
    create_user_dataset,
    delete_user_dataset,
    expire_user_datasets,
    user_dataset_access_token_hash,
)


def _database():
    engine = create_engine("sqlite+pysqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _record):
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        user_dataset_dir=tmp_path / "user_uploads",
        artifact_dir=tmp_path / "artifacts",
        user_dataset_retention_hours=24,
        user_dataset_max_active_per_client=3,
    )


def _seed_cancer(db) -> None:
    db.add(
        CancerType(
            code="LUAD",
            tcga_cohort="TCGA-LUAD",
            name="Lung Adenocarcinoma",
            primary_site="Lung",
            sort_order=0,
            coverage_status="available",
        )
    )
    db.commit()


def _clinical_table(*, event_count: int = 6) -> bytes:
    rows = [
        "sample_id,os_months,os_status,age,stage,grade",
        *[
            (
                f"S{index:02d},{8 + index * 3},"
                f"{'event' if index <= event_count else 'censored'},"
                f"{45 + index},Stage {1 + index % 4},G{1 + index % 3}"
            )
            for index in range(1, 13)
        ],
    ]
    return ("\n".join(rows) + "\n").encode()


def _genes_by_rows_table() -> bytes:
    sample_ids = [f"S{index:02d}" for index in range(1, 13)]
    tp53 = [2.0, 3.1, 2.4, 3.3, 2.8, 3.5, 2.2, 3.2, 2.6, 3.4, 3.0, 3.6]
    rows = [
        ",".join(["gene_symbol", *sample_ids]),
        ",".join(["TP53", *[f"{value:.2f}" for value in tp53]]),
        ",".join(["MKI67", *[f"{4 + index / 20:.2f}" for index in range(12)]]),
        ",".join(["BAX", *[f"{3 - index / 30:.2f}" for index in range(12)]]),
    ]
    return ("\n".join(rows) + "\n").encode()


def _gsea_genes_by_rows_table() -> bytes:
    """Broad deterministic fixture for tests that must pass GSEA preflight."""

    rows = _genes_by_rows_table().decode().strip().splitlines()
    rows.extend(
        ",".join(
            [
                f"GSEA_FIXTURE_{gene_index:03d}",
                *[
                    f"{1 + gene_index / 100 + sample_index / 1000:.3f}"
                    for sample_index in range(12)
                ],
            ]
        )
        for gene_index in range(97)
    )
    return ("\n".join(rows) + "\n").encode()


def _rank_genes_by_rows_table(*, missing: bool = False) -> bytes:
    """Broad upload fixture with an optional unavailable matrix value."""

    sample_ids = [f"S{index:02d}" for index in range(1, 13)]
    rows = [",".join(["gene_symbol", *sample_ids])]
    for gene_index in range(1_000):
        values = [
            f"{1 + gene_index / 1000 + sample_index / 100:.4f}"
            for sample_index in range(12)
        ]
        if missing and gene_index == 500:
            values[4] = "NA"
        rows.append(",".join([f"RANK_FIXTURE_{gene_index:04d}", *values]))
    return ("\n".join(rows) + "\n").encode()


def _samples_by_rows_table() -> bytes:
    rows = ["sample_id,TP53,MKI67,BAX"]
    rows.extend(
        f"S{index:02d},{2 + index / 10:.2f},{4 + index / 20:.2f},{3 - index / 30:.2f}"
        for index in range(1, 13)
    )
    return ("\n".join(rows) + "\n").encode()


def _mapping(
    *,
    orientation: str = "genes_by_rows",
    expression_id_column: str = "gene_symbol",
    custom_variables: list[dict] | None = None,
) -> UserDatasetMapping:
    return UserDatasetMapping(
        name="Private LUAD validation cohort",
        cancer_code="LUAD",
        expression_orientation=orientation,
        expression_id_column=expression_id_column,
        clinical_id_column="sample_id",
        time_column="os_months",
        event_column="os_status",
        event_value="event",
        censored_value="censored",
        time_unit="months",
        endpoint="OS",
        expression_unit="log2_tpm",
        covariates={
            "age_at_index": "age",
            "stage": "stage",
            "grade": "grade",
        },
        custom_variables=custom_variables or [],
        confirm_deidentified=True,
    )


def test_private_dataset_access_requires_the_independent_token(tmp_path):
    factory = _database()
    settings = _settings(tmp_path)
    access_token = "independent-private-dataset-token"
    with factory() as db:
        _seed_cancer(db)
        result = create_user_dataset(
            db,
            settings,
            expression_source=io.BytesIO(_genes_by_rows_table()),
            clinical_source=io.BytesIO(_clinical_table()),
            mapping=_mapping(),
            owner_key_hash="browser-owner",
            access_token_hash=user_dataset_access_token_hash(access_token),
        )

        assert (
            authorize_user_dataset(db, result["id"], access_token).id
            == result["id"]
        )
        for invalid_token in (None, "incorrect-token"):
            with pytest.raises(UserDatasetError) as caught:
                authorize_user_dataset(db, result["id"], invalid_token)
            assert caught.value.code == "USER_DATASET_NOT_FOUND"


def test_private_user_dataset_uses_repository_analysis_contract(tmp_path):
    factory = _database()
    settings = _settings(tmp_path)
    with factory() as db:
        _seed_cancer(db)
        result = create_user_dataset(
            db,
            settings,
            expression_source=io.BytesIO(_genes_by_rows_table()),
            clinical_source=io.BytesIO(_clinical_table()),
            mapping=_mapping(),
            owner_key_hash="browser-owner",
        )

        assert result["kind"] == "user"
        assert result["patient_count"] == 12
        assert result["event_count"] == 6
        assert result["gene_count"] == 3
        assert result["endpoint"]["source_time_unit"] == "months"
        assert result["expression_layer"]["analysis_unit"] == "log2(TPM + 1)"
        assert result["privacy"] == {
            "visibility": "private",
            "enumerated": False,
            "original_files_retained": False,
            "retention_hours": 24,
            "retention_policy": "temporary",
            "delete_supported": True,
        }

        dataset_id = result["id"]
        release_id = result["active_release_id"]
        dataset_path = settings.user_dataset_dir / dataset_id
        assert dataset_path.joinpath("expression.float32le.bin").is_file()
        assert dataset_path.joinpath("clinical.normalized.tsv").is_file()
        assert not dataset_path.joinpath("expression-upload").exists()
        assert not dataset_path.joinpath("clinical-upload").exists()
        assert list_repository_datasets(db) == []
        with pytest.raises(ValueError, match="not available"):
            resolve_repository_context(db, dataset_id)

        context = resolve_repository_context(
            db,
            dataset_id,
            release_id,
            include_private=True,
        )
        values, _, gene = repository_gene_expression(
            db,
            context,
            "tp53",
            "uploaded_expression",
        )
        assert gene.gene_symbol == "TP53"
        assert len(values) == 12
        assert values["S01"] == pytest.approx(2.0)
        patient = db.scalar(
            select(RepositoryPatient).where(
                RepositoryPatient.release_id == release_id
            )
        )
        assert patient is not None
        assert patient.stage
        endpoint = db.scalar(
            select(RepositoryEndpointDefinition).where(
                RepositoryEndpointDefinition.release_id == release_id
            )
        )
        assert endpoint is not None
        assert endpoint.event_count == 6

        gsea_id = "gsea-private-fixture"
        gsea_dir = settings.artifact_dir / "gsea" / gsea_id
        gsea_dir.mkdir(parents=True)
        (gsea_dir / "sample_groups.csv").write_text(
            "patient_id,group\nprivate,High\n",
            encoding="utf-8",
        )
        db.add(
            ComputeJob(
                id="private-gsea-job",
                kind="gsea",
                params_hash="private-gsea-hash",
                client_key_hash="browser-owner",
                status="completed",
                request_payload={"dataset_id": dataset_id},
                result_json={"gsea_id": gsea_id},
                result_id=gsea_id,
                error_json=None,
            )
        )
        comparison_id = "exprcmp-private-fixture"
        comparison_dir = (
            settings.artifact_dir
            / "expression_comparisons"
            / comparison_id
        )
        comparison_dir.mkdir(parents=True)
        (comparison_dir / "expression_values.csv").write_text(
            "patient_id,gene,expression_value\nprivate,TP53,1.0\n",
            encoding="utf-8",
        )
        db.add(
            ComputeJob(
                id="private-expression-comparison-job",
                kind="expression_comparison",
                params_hash="private-expression-comparison-hash",
                client_key_hash="browser-owner",
                status="completed",
                request_payload={"dataset_id": dataset_id},
                result_json={"comparison_id": comparison_id},
                result_id=comparison_id,
                error_json=None,
            )
        )
        db.commit()

        deleted = delete_user_dataset(db, settings, dataset_id)
        assert deleted["status"] == "deleted"
        assert deleted["compute_jobs_deleted"] == 2
        assert db.get(RepositoryDataset, dataset_id) is None
        assert not dataset_path.exists()
        assert not gsea_dir.exists()
        assert not comparison_dir.exists()


@pytest.mark.parametrize("active_status", ["queued", "running"])
def test_delete_private_dataset_rejects_active_compute_jobs(
    tmp_path,
    active_status,
):
    factory = _database()
    settings = _settings(tmp_path)
    with factory() as db:
        _seed_cancer(db)
        result = create_user_dataset(
            db,
            settings,
            expression_source=io.BytesIO(_genes_by_rows_table()),
            clinical_source=io.BytesIO(_clinical_table()),
            mapping=_mapping(),
            owner_key_hash="browser-owner",
        )
        dataset_id = result["id"]
        dataset_path = settings.user_dataset_dir / dataset_id
        job = ComputeJob(
            id=f"active-private-{active_status}",
            kind="gsea",
            params_hash=f"active-private-{active_status}-hash",
            client_key_hash="browser-owner",
            status=active_status,
            request_payload={"dataset_id": dataset_id},
            result_json=None,
            result_id=None,
            error_json=None,
        )
        db.add(job)
        db.commit()

        with pytest.raises(UserDatasetError) as caught:
            delete_user_dataset(db, settings, dataset_id)

        assert caught.value.code == "USER_DATASET_IN_USE"
        assert caught.value.details == {
            "active_job_count": 1,
            "active_job_statuses": [active_status],
        }
        assert main_module._user_dataset_http_error(
            caught.value
        ).status_code == 409
        assert db.get(RepositoryDataset, dataset_id) is not None
        assert db.get(ComputeJob, job.id) is not None
        assert dataset_path.is_dir()


def test_samples_in_rows_are_transposed_to_repository_layout(tmp_path):
    factory = _database()
    settings = _settings(tmp_path)
    with factory() as db:
        _seed_cancer(db)
        result = create_user_dataset(
            db,
            settings,
            expression_source=io.BytesIO(_samples_by_rows_table()),
            clinical_source=io.BytesIO(_clinical_table()),
            mapping=_mapping(
                orientation="samples_by_rows",
                expression_id_column="sample_id",
            ),
            owner_key_hash="browser-owner",
        )
        context = resolve_repository_context(
            db,
            result["id"],
            result["active_release_id"],
            include_private=True,
        )
        layer = db.scalar(
            select(RepositoryExpressionLayer).where(
                RepositoryExpressionLayer.release_id
                == result["active_release_id"]
            )
        )
        assert layer is not None
        values, _, _ = repository_gene_expression(
            db,
            context,
            "MKI67",
            layer.layer_id,
        )
        assert values["S01"] == pytest.approx(4.05)
        assert values["S12"] == pytest.approx(4.6)


def test_private_dataset_expiration_is_leased_while_compute_is_active(
    tmp_path,
):
    factory = _database()
    settings = _settings(tmp_path)
    with factory() as db:
        _seed_cancer(db)
        result = create_user_dataset(
            db,
            settings,
            expression_source=io.BytesIO(_genes_by_rows_table()),
            clinical_source=io.BytesIO(_clinical_table()),
            mapping=_mapping(),
            owner_key_hash="browser-owner",
        )
        dataset = db.get(RepositoryDataset, result["id"])
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        dataset.expires_at = now - timedelta(minutes=1)
        db.add(
            ComputeJob(
                id="active-private-gsea",
                kind="gsea",
                params_hash="active-private-gsea-hash",
                client_key_hash="browser-owner",
                status="running",
                request_payload={"dataset_id": dataset.id},
                result_json=None,
                result_id=None,
                error_json=None,
            )
        )
        db.commit()

        assert expire_user_datasets(
            db,
            settings,
            now=now,
        ) == 0
        retained = db.get(RepositoryDataset, dataset.id)
        assert retained is not None
        assert retained.expires_at >= now + timedelta(hours=23)


def test_private_dataset_is_leased_when_compute_job_is_accepted(
    tmp_path,
    monkeypatch,
):
    factory = _database()
    settings = _settings(tmp_path)
    monkeypatch.setattr(main_module, "settings", settings)
    with factory() as db:
        _seed_cancer(db)
        access_token = "lease-test-token"
        result = create_user_dataset(
            db,
            settings,
            expression_source=io.BytesIO(_gsea_genes_by_rows_table()),
            clinical_source=io.BytesIO(_clinical_table()),
            mapping=_mapping(),
            owner_key_hash="browser-owner",
            access_token_hash=user_dataset_access_token_hash(access_token),
        )
        dataset = db.get(RepositoryDataset, result["id"])
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        dataset.expires_at = now + timedelta(minutes=1)
        db.commit()

        request = Request(
            {
                "type": "http",
                "method": "POST",
                "path": "/api/v1/analyses/gsea",
                "headers": [
                    (b"x-trace-dataset-token", access_token.encode("ascii")),
                ],
                "client": ("127.0.0.1", 1234),
                "server": ("testserver", 80),
                "scheme": "http",
                "query_string": b"",
            }
        )
        output = main_module._submit_public_job(
            "gsea",
            {"dataset_id": dataset.id},
            request,
            Response(),
            db,
        )

        retained = db.get(RepositoryDataset, dataset.id)
        assert output.status == "queued"
        assert retained is not None
        assert retained.expires_at >= now + timedelta(hours=23)


def test_completed_cached_job_does_not_extend_private_dataset_lease(
    tmp_path,
    monkeypatch,
):
    factory = _database()
    settings = _settings(tmp_path)
    monkeypatch.setattr(main_module, "settings", settings)
    with factory() as db:
        _seed_cancer(db)
        access_token = "cached-job-test-token"
        result = create_user_dataset(
            db,
            settings,
            expression_source=io.BytesIO(_gsea_genes_by_rows_table()),
            clinical_source=io.BytesIO(_clinical_table()),
            mapping=_mapping(),
            owner_key_hash="browser-owner",
            access_token_hash=user_dataset_access_token_hash(access_token),
        )
        request = Request(
            {
                "type": "http",
                "method": "POST",
                "path": "/api/v1/analyses/gsea",
                "headers": [
                    (b"x-trace-dataset-token", access_token.encode("ascii")),
                ],
                "client": ("127.0.0.1", 1234),
                "server": ("testserver", 80),
                "scheme": "http",
                "query_string": b"",
            }
        )
        payload = {"dataset_id": result["id"]}
        first = main_module._submit_public_job(
            "gsea",
            payload,
            request,
            Response(),
            db,
        )
        job = db.get(ComputeJob, first.id)
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        original_expiry = now + timedelta(minutes=5)
        job.status = "completed"
        job.expires_at = now + timedelta(hours=1)
        db.get(RepositoryDataset, result["id"]).expires_at = original_expiry
        db.commit()

        cached = main_module._submit_public_job(
            "gsea",
            payload,
            request,
            Response(),
            db,
        )

        assert cached.id == first.id
        assert cached.cached is True
        assert db.get(RepositoryDataset, result["id"]).expires_at == original_expiry


def test_rejected_compute_job_rolls_back_private_dataset_lease(
    tmp_path,
    monkeypatch,
):
    factory = _database()
    settings = _settings(tmp_path)
    settings.compute_max_active_per_client = 0
    monkeypatch.setattr(main_module, "settings", settings)
    with factory() as db:
        _seed_cancer(db)
        access_token = "rejected-job-test-token"
        result = create_user_dataset(
            db,
            settings,
            expression_source=io.BytesIO(_gsea_genes_by_rows_table()),
            clinical_source=io.BytesIO(_clinical_table()),
            mapping=_mapping(),
            owner_key_hash="browser-owner",
            access_token_hash=user_dataset_access_token_hash(access_token),
        )
        dataset = db.get(RepositoryDataset, result["id"])
        original_expiry = (
            datetime.now(timezone.utc).replace(tzinfo=None)
            + timedelta(minutes=5)
        )
        dataset.expires_at = original_expiry
        db.commit()
        request = Request(
            {
                "type": "http",
                "method": "POST",
                "path": "/api/v1/analyses/gsea",
                "headers": [
                    (b"x-trace-dataset-token", access_token.encode("ascii")),
                ],
                "client": ("127.0.0.1", 1234),
                "server": ("testserver", 80),
                "scheme": "http",
                "query_string": b"",
            }
        )

        with pytest.raises(HTTPException) as caught:
            main_module._submit_public_job(
                "gsea",
                {"dataset_id": dataset.id},
                request,
                Response(),
                db,
            )

        assert caught.value.status_code == 429
        assert db.get(RepositoryDataset, dataset.id).expires_at == original_expiry
        assert db.scalar(select(ComputeJob)) is None


def test_expiry_rechecks_each_dataset_after_prior_delete_commit(
    tmp_path,
    monkeypatch,
):
    factory = _database()
    settings = _settings(tmp_path)
    with factory() as db:
        _seed_cancer(db)
        results = [
            create_user_dataset(
                db,
                settings,
                expression_source=io.BytesIO(_genes_by_rows_table()),
                clinical_source=io.BytesIO(_clinical_table()),
                mapping=_mapping(),
                owner_key_hash="browser-owner",
            )
            for _ in range(2)
        ]
        cutoff = datetime.now(timezone.utc).replace(tzinfo=None)
        dataset_ids = sorted(result["id"] for result in results)
        for dataset_id in dataset_ids:
            db.get(RepositoryDataset, dataset_id).expires_at = (
                cutoff - timedelta(minutes=1)
            )
        db.commit()

        original_delete = user_datasets_module.delete_user_dataset
        calls: list[str] = []

        def delete_with_interleaved_lease(db_session, active_settings, dataset_id):
            output = original_delete(
                db_session,
                active_settings,
                dataset_id,
            )
            calls.append(dataset_id)
            if len(calls) == 1:
                survivor_id = next(
                    item for item in dataset_ids if item != dataset_id
                )
                survivor = db_session.get(RepositoryDataset, survivor_id)
                survivor.expires_at = cutoff + timedelta(hours=24)
                db_session.add(
                    ComputeJob(
                        id="interleaved-private-job",
                        kind="gsea",
                        params_hash="interleaved-private-job-hash",
                        client_key_hash="browser-owner",
                        status="queued",
                        request_payload={"dataset_id": survivor_id},
                        result_json=None,
                        result_id=None,
                        error_json=None,
                    )
                )
                db_session.commit()
            return output

        monkeypatch.setattr(
            user_datasets_module,
            "delete_user_dataset",
            delete_with_interleaved_lease,
        )

        assert expire_user_datasets(
            db,
            settings,
            now=cutoff,
        ) == 1
        survivor_id = next(item for item in dataset_ids if item not in calls)
        assert db.get(RepositoryDataset, survivor_id) is not None
        assert db.get(ComputeJob, "interleaved-private-job") is not None


def test_upload_keeps_molecular_dataset_when_survival_is_not_evaluable(tmp_path):
    factory = _database()
    settings = _settings(tmp_path)
    with factory() as db:
        _seed_cancer(db)
        dataset = create_user_dataset(
            db,
            settings,
            expression_source=io.BytesIO(_genes_by_rows_table()),
            clinical_source=io.BytesIO(_clinical_table(event_count=10)),
            mapping=_mapping(),
            owner_key_hash="browser-owner",
        )

        assert dataset["patient_count"] == 12
        assert dataset["endpoint"]["available"] is False
        assert dataset["capabilities"]["survival"]["available"] is False
        assert dataset["capabilities"]["expression_comparison"]["available"] is True
        assert dataset["capabilities"]["gsea"]["available"] is False
        assert (
            dataset["capabilities"]["rank_based_signature_scoring"]["available"]
            is False
        )
        assert "at least 100 genes" in dataset["capabilities"]["gsea"]["reason"]
        assert "5 censored" in dataset["endpoint"]["reason"]


@pytest.mark.parametrize(
    ("missing", "expected_available", "expected_missing"),
    [(False, True, 0), (True, False, 1)],
)
def test_private_broad_upload_rank_capability_requires_a_complete_matrix(
    tmp_path,
    missing,
    expected_available,
    expected_missing,
):
    factory = _database()
    settings = _settings(tmp_path)
    with factory() as db:
        _seed_cancer(db)
        dataset = create_user_dataset(
            db,
            settings,
            expression_source=io.BytesIO(
                _rank_genes_by_rows_table(missing=missing)
            ),
            clinical_source=io.BytesIO(_clinical_table()),
            mapping=_mapping(),
            owner_key_hash="browser-owner",
        )

        rank = dataset["capabilities"]["rank_based_signature_scoring"]
        assert rank["available"] is expected_available
        assert rank["gene_count"] == 1_000
        assert rank["sample_count"] == 12
        assert rank["matrix_entry_count"] == 12_000
        assert (
            rank["maximum_matrix_entries"]
            == RANK_SIGNATURE_MAXIMUM_MATRIX_ENTRIES
        )
        assert rank["missing_value_count"] == expected_missing
        assert rank["complete_matrix_verified"] is (not missing)
        if missing:
            assert "1 missing or non-finite value" in rank["reason"]
        else:
            assert rank["reason"] is None

        context = resolve_repository_context(
            db,
            dataset["id"],
            dataset["active_release_id"],
            include_private=True,
        )
        service_rank = repository_capabilities(
            context,
            expression_layer_id="uploaded_expression",
        )["rank_based_signature_scoring"]
        assert service_rank["available"] is expected_available
        assert service_rank["missing_value_count"] == expected_missing
        [layer] = repository_expression_layers(db, context)
        rest_rank = layer["capabilities"]["rank_based_signature_scoring"]
        assert rest_rank["available"] is expected_available
        assert rest_rank["missing_value_count"] == expected_missing


def test_metadata_only_upload_preserves_three_breast_subtypes(tmp_path):
    metadata = ["sample_id,subtype"]
    subtype_values = ["Luminal A"] * 6 + ["Basal-like"] * 6 + ["HER2-enriched"] * 6
    metadata.extend(
        f"S{index:02d},{subtype}"
        for index, subtype in enumerate(subtype_values, start=1)
    )
    sample_ids = [f"S{index:02d}" for index in range(1, 19)]
    expression_rows = [",".join(["gene_symbol", *sample_ids])]
    expression_rows.extend(
        ",".join(
            [
                f"GENE{gene_index}",
                *[
                    f"{2 + gene_index / 100 + sample_index / 10:.2f}"
                    for sample_index in range(18)
                ],
            ]
        )
        for gene_index in range(1, 121)
    )
    expression = ("\n".join(expression_rows) + "\n").encode()
    mapping = _mapping(
        custom_variables=[
            {
                "source_column": "subtype",
                "id": "breast_subtype",
                "label": "Breast cancer subtype",
                "value_type": "categorical",
                "timing": "baseline",
                "expression_derived": False,
            }
        ]
    ).model_copy(
        update={
            "name": "Private breast subtype cohort",
            "has_survival_outcome": False,
            "time_column": None,
            "event_column": None,
            "event_value": None,
            "censored_value": None,
            "time_unit": None,
            "covariates": _mapping().covariates.model_copy(
                update={
                    "stage": None,
                    "grade": None,
                    "age_at_index": None,
                    "gender": None,
                    "race": None,
                }
            ),
        }
    )
    factory = _database()
    settings = _settings(tmp_path)
    with factory() as db:
        _seed_cancer(db)
        dataset = create_user_dataset(
            db,
            settings,
            expression_source=io.BytesIO(expression),
            clinical_source=io.BytesIO(("\n".join(metadata) + "\n").encode()),
            mapping=mapping,
            owner_key_hash="browser-owner",
        )

        assert dataset["endpoint"] is None
        assert dataset["event_count"] == 0
        assert dataset["capabilities"]["survival"] == {
            "available": False,
            "patient_count": 0,
            "event_count": 0,
            "reason": "No time-to-event outcome was supplied.",
        }
        assert dataset["capabilities"]["gsea"]["available"] is True
        assert dataset["capabilities"]["gsea"]["gene_count"] == 120
        assert (
            dataset["capabilities"]["rank_based_signature_scoring"]["available"]
            is False
        )
        assert (
            dataset["capabilities"]["rank_based_signature_scoring"]["minimum_genes"]
            == 1000
        )
        variable = dataset["qc"]["custom_clinical"]["variables"][0]
        assert variable["observed_levels"] == [
            {"value": "Basal-like", "count": 6},
            {"value": "HER2-enriched", "count": 6},
            {"value": "Luminal A", "count": 6},
        ]
        assert variable["analysis_eligible"] is True
        assert db.scalars(select(RepositoryEndpointDefinition)).all() == []

        context = resolve_repository_context(
            db,
            dataset["id"],
            dataset["active_release_id"],
            include_private=True,
        )
        samples = repository_samples(db, context)
        catalog, values = clinical_grouping_context(
            samples,
            cohort=dataset["tcga_cohort"],
            repository=True,
        )
        subtype = next(item for item in catalog if item["id"] == "breast_subtype")
        assert [level["value"] for level in subtype["levels"]] == [
            "Basal-like",
            "HER2-enriched",
            "Luminal A",
        ]
        selected, audit, warnings = filter_samples_by_clinical_variable(
            samples,
            subtype,
            values["breast_subtype"],
            categorical_levels=["Basal-like", "Luminal A"],
            analysis_context="expression",
        )
        assert len(selected) == 12
        assert audit["filter"] == {"levels": ["Basal-like", "Luminal A"]}
        assert warnings == []


def test_partial_outcome_excludes_patients_only_from_survival(tmp_path):
    rows = ["sample_id,os_months,os_status,subtype"]
    for index in range(1, 13):
        if index <= 5:
            outcome = f"{10 + index},event"
        elif index <= 10:
            outcome = f"{10 + index},censored"
        else:
            outcome = ","
        rows.append(
            f"S{index:02d},{outcome},{'Luminal A' if index <= 6 else 'Basal-like'}"
        )
    mapping = _mapping(
        custom_variables=[
            {
                "source_column": "subtype",
                "id": "breast_subtype",
                "label": "Breast cancer subtype",
                "value_type": "categorical",
                "timing": "baseline",
            }
        ]
    ).model_copy(
        update={
            "covariates": _mapping().covariates.model_copy(
                update={
                    "stage": None,
                    "grade": None,
                    "age_at_index": None,
                    "gender": None,
                    "race": None,
                }
            )
        }
    )
    factory = _database()
    settings = _settings(tmp_path)
    with factory() as db:
        _seed_cancer(db)
        dataset = create_user_dataset(
            db,
            settings,
            expression_source=io.BytesIO(_genes_by_rows_table()),
            clinical_source=io.BytesIO(("\n".join(rows) + "\n").encode()),
            mapping=mapping,
            owner_key_hash="browser-owner",
        )

        assert dataset["patient_count"] == 12
        assert dataset["endpoint"]["available"] is True
        assert dataset["endpoint"]["patient_count"] == 10
        assert dataset["event_count"] == 5
        assert dataset["capabilities"]["expression_comparison"]["patient_count"] == 12
        assert dataset["capabilities"]["survival"]["patient_count"] == 10
        assert dataset["qc"]["clinical"]["excluded_incomplete_outcome"] == 2
        assert any(
            notice["code"] == "INCOMPLETE_OUTCOMES_EXCLUDED_FROM_SURVIVAL"
            for notice in dataset["qc"]["notices"]
        )


def test_uploaded_dataset_runs_the_same_survival_pipeline(
    tmp_path,
    monkeypatch,
):
    factory = _database()
    settings = _settings(tmp_path)
    settings.r_script_path = Path("/app/scripts/km_analysis.R")
    settings.attestation_enabled = True
    settings.attestation_auto_generate = True
    settings.attestation_private_key_path = tmp_path / "attestation" / "key.pem"
    settings.attestation_public_key_dir = tmp_path / "attestation" / "public"
    monkeypatch.setattr(main_module, "settings", settings)

    with factory() as db:
        _seed_cancer(db)
        dataset = create_user_dataset(
            db,
            settings,
            expression_source=io.BytesIO(_genes_by_rows_table()),
            clinical_source=io.BytesIO(_clinical_table()),
            mapping=_mapping(),
            owner_key_hash="browser-owner",
        )
        request = AnalysisRequest(
            cohort=dataset["tcga_cohort"],
            dataset_id=dataset["id"],
            dataset_release_id=dataset["active_release_id"],
            expression_layer_id=dataset["expression_layer"]["value"],
            gene_symbol="TP53",
            endpoint="OS",
            cutpoint_method="median",
            adjustment_covariates=[],
        )

        result = main_module._create_analysis(request, db)

        assert result.status == "completed"
        assert result.metrics["dataset"]["kind"] == "user"
        assert result.metrics["dataset"]["dataset_id"] == dataset["id"]
        assert result.metrics["endpoint_source"] == "user_upload"
        assert result.metrics["n_patients"] == 12
        audit = json.loads(
            (settings.artifact_dir / result.id / "audit_report.json").read_text()
        )
        assert audit["data"]["provenance"]["dataset_kind"] == "user"
        assert audit["data"]["provenance"]["privacy"]["visibility"] == "private"


def _clinical_table_with_custom_metadata() -> bytes:
    rows = [
        "sample_id,os_months,os_status,age,stage,grade,pam50,immune_score,response,post_tx_marker"
    ]
    for index in range(1, 13):
        rows.append(
            ",".join(
                [
                    f"S{index:02d}",
                    str(8 + index * 3),
                    "event" if index <= 6 else "censored",
                    str(45 + index),
                    f"Stage {1 + index % 4}",
                    f"G{1 + index % 3}",
                    "LumA" if index <= 6 else "Basal",
                    f"{index / 2:.1f}",
                    "CR" if index <= 6 else "PD",
                    "High" if index <= 6 else "Low",
                ]
            )
        )
    return ("\n".join(rows) + "\n").encode()


def _custom_variable_mapping() -> UserDatasetMapping:
    return _mapping(
        custom_variables=[
            {
                "source_column": "pam50",
                "id": "pam50_private",
                "label": "Private PAM50 subtype",
                "value_type": "categorical",
                "timing": "baseline",
                "expression_derived": True,
                "description": "Synthetic expression-derived subtype.",
            },
            {
                "source_column": "immune_score",
                "id": "immune_score",
                "label": "Immune score",
                "value_type": "numeric",
                "unit": "score",
                "timing": "pre_treatment",
            },
            {
                "source_column": "response",
                "id": "best_response",
                "label": "Best response",
                "value_type": "categorical",
                "timing": "outcome",
            },
            {
                "source_column": "post_tx_marker",
                "id": "post_tx_marker",
                "label": "Post-treatment marker",
                "value_type": "categorical",
                "timing": "post_treatment",
            },
        ]
    )


def test_private_custom_metadata_is_versioned_groupable_and_not_automatic_cox(
    tmp_path,
):
    factory = _database()
    settings = _settings(tmp_path)
    mapping = _custom_variable_mapping()
    assert mapping.custom_variables == mapping.custom_clinical_variables
    assert set(mapping.covariates.model_dump()) == {
        "stage",
        "grade",
        "age_at_index",
        "gender",
        "race",
    }

    with factory() as db:
        _seed_cancer(db)
        dataset = create_user_dataset(
            db,
            settings,
            expression_source=io.BytesIO(_genes_by_rows_table()),
            clinical_source=io.BytesIO(_clinical_table_with_custom_metadata()),
            mapping=mapping,
            owner_key_hash="browser-owner",
        )
        custom_qc = dataset["qc"]["custom_clinical"]
        assert custom_qc["schema_version"] == "trace-user-custom-clinical-v1"
        assert custom_qc["automatic_cox_adjustment"] is False
        assert len(custom_qc["variables"]) == 4
        assert any(
            notice["code"]
            == "CUSTOM_CLINICAL_EXPRESSION_DERIVED:pam50_private"
            for notice in dataset["qc"]["notices"]
        )
        assert any(
            notice["code"] == "CUSTOM_CLINICAL_OUTCOME_TIMING:best_response"
            for notice in dataset["qc"]["notices"]
        )
        assert any(
            notice["code"]
            == "CUSTOM_CLINICAL_POST_BASELINE_TIMING:post_tx_marker"
            for notice in dataset["qc"]["notices"]
        )

        patient = db.scalar(
            select(RepositoryPatient).where(
                RepositoryPatient.release_id == dataset["active_release_id"]
            )
        )
        payload = patient.raw_metadata["user_custom_clinical"]
        assert payload["schema_version"] == "trace-user-custom-clinical-v1"
        assert payload["values"]["pam50_private"] in {"LumA", "Basal"}

        context = resolve_repository_context(
            db,
            dataset["id"],
            dataset["active_release_id"],
            include_private=True,
        )
        samples = repository_samples(db, context)
        catalog, values = clinical_grouping_context(
            samples,
            cohort=dataset["tcga_cohort"],
            repository=True,
        )
        subtype = next(item for item in catalog if item["id"] == "pam50_private")
        score = next(item for item in catalog if item["id"] == "immune_score")
        response = next(item for item in catalog if item["id"] == "best_response")
        post_treatment = next(
            item for item in catalog if item["id"] == "post_tx_marker"
        )
        assert subtype["analysis_eligible"] is True
        assert subtype["expression_derived"] is True
        assert subtype["declared_source_column"] == "pam50"
        assert "circular" in subtype["analysis_note"]
        assert score["numeric_summary"] == {
            "min": 0.5,
            "max": 6.0,
            "median": 3.25,
            "unit": "score",
        }
        assert response["survival_eligible"] is False
        assert "Outcome-defined" in response["survival_unavailable_reason"]
        assert post_treatment["survival_eligible"] is False
        assert "Post-baseline" in post_treatment["survival_unavailable_reason"]

        selected, audit, warnings = filter_samples_by_clinical_variable(
            samples,
            subtype,
            values["pam50_private"],
            categorical_levels=["LumA"],
            analysis_context="expression",
        )
        assert len(selected) == 6
        assert audit["automatic_cox_adjustment"] is False
        assert any("circular" in warning for warning in warnings)

        numeric_selected, numeric_audit, _ = (
            filter_samples_by_clinical_variable(
                samples,
                score,
                values["immune_score"],
                numeric_min=3.0,
                numeric_max=5.0,
                analysis_context="survival",
            )
        )
        assert len(numeric_selected) == 5
        assert numeric_audit["filter"] == {"min": 3.0, "max": 5.0}
        with pytest.raises(ValueError, match="Outcome-defined"):
            resolve_clinical_grouping_variable(
                samples,
                "best_response",
                cohort=dataset["tcga_cohort"],
                repository=True,
                analysis_context="survival",
            )

        subtype_filter = AnalysisFilters(
            custom_filters=[
                {
                    "variable_id": "pam50_private",
                    "categorical_levels": ["LumA"],
                }
            ]
        )
        molecular_samples, molecular_audit, molecular_warnings = (
            select_gsea_samples(
                samples,
                subtype_filter,
                [sample.barcode for sample in samples],
                analysis_context="expression",
                selection_rule="external",
            )
        )
        assert len(molecular_samples) == 6
        assert molecular_audit["custom_clinical_filter_count"] == 1
        assert molecular_audit["custom_clinical_filters"][0][
            "automatic_cox_adjustment"
        ] is False
        assert any("circular" in warning for warning in molecular_warnings)

        endpoint_by_patient = {
            sample.patient_id: ClinicalOutcome(
                endpoint="OS",
                time_days=365.0,
                event=index % 2,
                source="test",
            )
            for index, sample in enumerate(samples)
        }
        survival_samples, _, survival_audit = filter_sample_candidates(
            samples,
            subtype_filter,
            endpoint_by_patient=endpoint_by_patient,
            selection_rule="repository",
        )
        assert len(survival_samples) == 6
        assert survival_audit["custom_clinical_filter_count"] == 1
        assert survival_audit[
            "custom_clinical_automatic_cox_adjustment"
        ] is False
        with pytest.raises(ValueError, match="Outcome-defined"):
            filter_sample_candidates(
                samples,
                AnalysisFilters(
                    custom_filters=[
                        {
                            "variable_id": "best_response",
                            "categorical_levels": ["CR"],
                        }
                    ]
                ),
                endpoint_by_patient=endpoint_by_patient,
                selection_rule="repository",
            )


def test_custom_mapping_rejects_identifier_endpoint_and_duplicate_columns():
    with pytest.raises(ValueError, match="already assigned"):
        _mapping(
            custom_variables=[
                {
                    "source_column": "os_months",
                    "id": "followup_copy",
                    "label": "Follow-up copy",
                    "value_type": "numeric",
                }
            ]
        )
    with pytest.raises(ValueError, match="direct identifiers"):
        _mapping(
            custom_variables=[
                {
                    "source_column": "patient_identifier",
                    "id": "secondary_identifier",
                    "label": "Secondary identifier",
                    "value_type": "categorical",
                }
            ]
        )
    with pytest.raises(ValueError, match="must be unique"):
        _mapping(
            custom_variables=[
                {
                    "source_column": "subtype_a",
                    "id": "subtype",
                    "label": "Subtype A",
                    "value_type": "categorical",
                },
                {
                    "source_column": "subtype_b",
                    "id": "SUBTYPE",
                    "label": "Subtype B",
                    "value_type": "categorical",
                },
            ]
        )


def test_custom_filter_contract_requires_one_selector_and_unique_variables():
    categorical = AnalysisFilters(
        custom_filters=[
            {
                "variable_id": "subtype",
                "categorical_levels": [" LumA ", "luma", "Basal"],
            }
        ]
    )
    assert categorical.custom_filters[0].categorical_levels == [
        "LumA",
        "Basal",
    ]
    numeric = AnalysisFilters(
        custom_filters=[
            {
                "variable_id": "score",
                "numeric_min": 0,
                "numeric_max": 1,
            }
        ]
    )
    assert numeric.custom_filters[0].numeric_min == 0
    with pytest.raises(ValueError, match="Select either"):
        AnalysisFilters(custom_filters=[{"variable_id": "subtype"}])
    with pytest.raises(ValueError, match="Select either"):
        AnalysisFilters(
            custom_filters=[
                {
                    "variable_id": "subtype",
                    "categorical_levels": ["LumA"],
                    "numeric_min": 0,
                }
            ]
        )
    with pytest.raises(ValueError, match="filtered only once"):
        AnalysisFilters(
            custom_filters=[
                {"variable_id": "subtype", "categorical_levels": ["LumA"]},
                {"variable_id": "SUBTYPE", "categorical_levels": ["Basal"]},
            ]
        )


def test_custom_mapping_limits_variables_and_keeps_v1_default_compatible():
    legacy_mapping = _mapping()
    assert legacy_mapping.custom_clinical_variables == []
    assert legacy_mapping.model_dump(mode="json")[
        "custom_clinical_variables"
    ] == []
    with pytest.raises(ValueError, match="at most 10 items"):
        _mapping(
            custom_variables=[
                {
                    "source_column": f"feature_{index}",
                    "id": f"feature_{index}",
                    "label": f"Feature {index}",
                    "value_type": "numeric",
                }
                for index in range(11)
            ]
        )


def test_private_custom_categorical_high_cardinality_is_rejected(tmp_path):
    sample_ids = [f"S{index:02d}" for index in range(1, 32)]
    expression = (
        ",".join(["gene_symbol", *sample_ids])
        + "\nTP53,"
        + ",".join(str(2 + index / 10) for index in range(31))
        + "\n"
    ).encode()
    clinical_rows = [
        "sample_id,os_months,os_status,age,stage,grade,site_code"
    ]
    clinical_rows.extend(
        (
            f"S{index:02d},{6 + index},"
            f"{'event' if index <= 16 else 'censored'},"
            f"{40 + index},Stage II,G2,SITE-{index:02d}"
        )
        for index in range(1, 32)
    )
    mapping = _mapping(
        custom_variables=[
            {
                "source_column": "site_code",
                "id": "site_code",
                "label": "Site code",
                "value_type": "categorical",
                "timing": "baseline",
            }
        ]
    )
    factory = _database()
    settings = _settings(tmp_path)
    with factory() as db:
        _seed_cancer(db)
        with pytest.raises(UserDatasetError) as caught:
            create_user_dataset(
                db,
                settings,
                expression_source=io.BytesIO(expression),
                clinical_source=io.BytesIO(
                    ("\n".join(clinical_rows) + "\n").encode()
                ),
                mapping=mapping,
                owner_key_hash="browser-owner",
            )
        assert caught.value.code == "CUSTOM_CATEGORICAL_HIGH_CARDINALITY"
        assert caught.value.details["observed_levels"] == 31


def test_private_custom_numeric_values_must_be_finite_or_missing(tmp_path):
    clinical = _clinical_table_with_custom_metadata().decode()
    clinical = clinical.replace(",0.5,CR,", ",not-a-number,CR,", 1)
    factory = _database()
    settings = _settings(tmp_path)
    with factory() as db:
        _seed_cancer(db)
        with pytest.raises(UserDatasetError) as caught:
            create_user_dataset(
                db,
                settings,
                expression_source=io.BytesIO(_genes_by_rows_table()),
                clinical_source=io.BytesIO(clinical.encode()),
                mapping=_custom_variable_mapping(),
                owner_key_hash="browser-owner",
            )
        assert caught.value.code == "INVALID_CUSTOM_NUMERIC_VALUE"
        assert caught.value.details["variables"]["immune_score"]["count"] == 1


def test_private_custom_categorical_eligibility_requires_two_levels_of_five(
    tmp_path,
):
    lines = _clinical_table_with_custom_metadata().decode().splitlines()
    for index in (7, 8):
        lines[index] = lines[index].replace(",Basal,", ",LumA,")
    factory = _database()
    settings = _settings(tmp_path)
    with factory() as db:
        _seed_cancer(db)
        dataset = create_user_dataset(
            db,
            settings,
            expression_source=io.BytesIO(_genes_by_rows_table()),
            clinical_source=io.BytesIO(("\n".join(lines) + "\n").encode()),
            mapping=_custom_variable_mapping(),
            owner_key_hash="browser-owner",
        )
        subtype = next(
            item
            for item in dataset["qc"]["custom_clinical"]["variables"]
            if item["id"] == "pam50_private"
        )
        assert subtype["analysis_eligible"] is False
        assert subtype["observed_levels"] == [
            {"value": "LumA", "count": 8},
            {"value": "Basal", "count": 4},
        ]


def test_local_project_retains_data_without_expiry(tmp_path):
    """Local projects survive the sweeper and compute leases; web stays temporary."""
    from app.user_datasets import get_user_dataset, extend_user_dataset_compute_leases
    settings = _settings(tmp_path)
    settings.local_desktop_mode = True
    with _database()() as db:
        _seed_cancer(db)
        token = 'local-test-capability'
        created = create_user_dataset(db, settings,
            expression_source=io.BytesIO(_genes_by_rows_table()),
            clinical_source=io.BytesIO(_clinical_table()),
            mapping=UserDatasetMapping(name='Local project', cancer_code='LUAD',
                expression_orientation='genes_by_rows', expression_id_column='gene_symbol',
                clinical_id_column='sample_id', time_column='os_months', event_column='os_status',
                event_value='event', censored_value='censored', time_unit='months',
                endpoint='OS', expression_unit='log2_tpm', confirm_deidentified=True),
            owner_key_hash='local-test-owner', access_token_hash=user_dataset_access_token_hash(token))
        assert created['expires_at'] is None
        assert created['privacy']['retention_policy'] == 'local_until_deleted'
        dataset = authorize_user_dataset(db, created['id'], token)
        extend_user_dataset_compute_leases([dataset], settings)
        assert dataset.expires_at is None
        assert expire_user_datasets(db, settings, now=datetime(2099, 1, 1)) == 0
        assert get_user_dataset(db, created['id'])['patient_count'] == 12
        context = resolve_repository_context(db, created['id'], include_private=True)
        assert context.dataset.id == created['id']
        with pytest.raises(UserDatasetError):
            authorize_user_dataset(db, created['id'], 'incorrect-token')
