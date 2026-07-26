import json
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.attestation import (
    attestation_key_document,
    verify_attestation_receipt,
)
from app.config import Settings
from app.models import ComputeJob
from app.schemas import (
    ExploratorySessionExportRequest,
    ExploratorySessionOut,
)
from app.session_history import (
    build_exploratory_session_report,
    write_exploratory_session_artifacts,
)


def session_request(entries):
    return ExploratorySessionExportRequest(
        browser_session_id="browser_session_123",
        session_label="Exploratory checkpoint",
        entries=entries,
    )


def session_entry(event_id, job_id, label="CDC20"):
    return {
        "event_id": event_id,
        "job_id": job_id,
        "recorded_at": "2026-07-25T12:00:00Z",
        "label": label,
        "source_view": "analysis",
    }


def cox_model(model_id, p_value=0.01, hazard_ratio=1.5):
    return {
        "model": model_id,
        "label": model_id,
        "status": "completed",
        "n_patients": 100,
        "n_events": 40,
        "hazard_ratio": hazard_ratio,
        "hr_conf_low": hazard_ratio * 0.8,
        "hr_conf_high": hazard_ratio * 1.2,
        "standard_error": 0.1,
        "p_value": p_value,
        "ph_p_value": 0.3,
        "ph_global_p_value": 0.4,
        "information_diagnostics": {
            "parameter_count": 2,
            "events_per_parameter": 20,
            "status": "adequate",
        },
    }


def analysis_result(
    analysis_id,
    *,
    cutpoint,
    grouped_p,
    corrected_p=None,
):
    return {
        "id": analysis_id,
        "status": "completed",
        "cohort": "TCGA-LIHC",
        "gene_symbol": "CDC20",
        "cutpoint_method": cutpoint,
        "metrics": {
            "n_patients": 100,
            "n_events": 40,
            "logrank_p_value": grouped_p,
            "cutpoint_details": {
                "method": cutpoint,
                "corrected_p_status": (
                    "completed" if corrected_p is not None else None
                ),
                "corrected_p_value": corrected_p,
            },
            "clinical_adjustment": {
                "continuous_model": "continuous_user_adjusted",
                "grouped_model": "user_adjusted",
            },
            "continuous_analysis": {
                "linear_models": [
                    cox_model(
                        "continuous_user_adjusted",
                        p_value=0.01,
                        hazard_ratio=1.5,
                    )
                ]
            },
            "cox_models": [
                cox_model(
                    "user_adjusted",
                    p_value=0.02,
                    hazard_ratio=1.6,
                )
            ],
            "audit_report": {
                "reproducibility_hash": f"audit-{analysis_id}",
                "patient_records_sha256": f"group-{analysis_id}",
                "continuous_patient_records_sha256": "same-continuous-population",
            },
        },
        "downloads": {},
    }


def analysis_request(cutpoint, *, external=None):
    return {
        "cohort": "TCGA-LIHC",
        "gene_symbol": "CDC20",
        "signature_method": "single",
        "signature_genes": [],
        "endpoint": "OS",
        "expression_scale": "log2_tpm",
        "cutpoint_method": cutpoint,
        "custom_percentile": None,
        "filters": {},
        "adjustment_covariates": ["age_at_index"],
        "external_covariates": external,
        "external_adjustment_covariates": [],
    }


def add_job(
    db,
    *,
    job_id,
    kind,
    request_payload,
    result_json,
    result_id,
    status="completed",
):
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    job = ComputeJob(
        id=job_id,
        kind=kind,
        params_hash=f"params-{job_id}",
        client_key_hash="client",
        status=status,
        request_payload=request_payload,
        result_json=result_json,
        result_id=result_id,
        error_json=None,
        attempt_count=1,
        cached=False,
        created_at=now,
        started_at=now,
        heartbeat_at=now,
        completed_at=now,
        expires_at=None,
    )
    db.add(job)
    db.commit()
    return job


@pytest.fixture()
def session_db():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    ComputeJob.__table__.create(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as db:
        yield db
    engine.dispose()


def test_session_contract_rejects_duplicate_event_ids():
    job_id = "a" * 32
    with pytest.raises(ValidationError, match="event_id values must be unique"):
        session_request(
            [
                session_entry("event-001", job_id),
                session_entry("event-001", job_id),
            ]
        )


def test_session_deduplicates_continuous_test_and_separates_grouped_family(
    session_db,
):
    first_id = "a" * 32
    second_id = "b" * 32
    add_job(
        session_db,
        job_id=first_id,
        kind="analysis",
        request_payload=analysis_request("maxstat"),
        result_json=analysis_result(
            "analysis-maxstat",
            cutpoint="maxstat",
            grouped_p=0.0001,
            corrected_p=0.02,
        ),
        result_id="analysis-maxstat",
    )
    add_job(
        session_db,
        job_id=second_id,
        kind="analysis",
        request_payload=analysis_request("median"),
        result_json=analysis_result(
            "analysis-median",
            cutpoint="median",
            grouped_p=0.04,
        ),
        result_id="analysis-median",
    )

    result = build_exploratory_session_report(
        request=session_request(
            [
                session_entry("event-001", first_id),
                session_entry("event-002", second_id),
            ]
        ),
        db=session_db,
        pipeline_version="session-test-v1",
        generated_at="2026-07-25T12:05:00+00:00",
    )

    ExploratorySessionOut(**result)
    continuous = [
        row
        for row in result["hypotheses"]
        if row["family"] == "continuous_primary"
    ]
    grouped = [
        row
        for row in result["hypotheses"]
        if row["family"] == "grouped_sensitivity"
    ]
    assert len(continuous) == 1
    assert continuous[0]["occurrence_count"] == 2
    assert continuous[0]["source_event_ids"] == [
        "event-001",
        "event-002",
    ]
    assert continuous[0]["bh_q_value"] == pytest.approx(0.01)
    assert len(grouped) == 2
    assert {
        row["inference_test"] for row in grouped
    } == {"maxstat_lau94_corrected", "logrank"}
    assert [row["bh_q_value"] for row in grouped] == pytest.approx(
        [0.04, 0.04]
    )
    assert (
        result["analysis_families"]["continuous_primary"][
            "evaluable_tests"
        ]
        == 1
    )
    assert (
        result["analysis_families"]["grouped_sensitivity"][
            "evaluable_tests"
        ]
        == 2
    )
    assert result["analysis_families"][
        "session_scope_is_complete_claim"
    ] is False


def test_session_redacts_external_covariate_rows(session_db):
    job_id = "c" * 32
    external = {
        "schema_version": "tcga-trace-external-covariates-v1",
        "source_label": "Private clinical annotations",
        "definitions": [
            {
                "name": "idh",
                "label": "IDH",
                "value_type": "categorical",
                "levels": ["WT", "Mut"],
                "reference_level": "WT",
            }
        ],
        "rows": [
            {
                "patient_id": "TCGA-AB-1234",
                "values": {"idh": "Mut"},
            }
        ],
    }
    add_job(
        session_db,
        job_id=job_id,
        kind="analysis",
        request_payload=analysis_request(
            "median",
            external=external,
        ),
        result_json=analysis_result(
            "analysis-private",
            cutpoint="median",
            grouped_p=0.03,
        ),
        result_id="analysis-private",
    )

    result = build_exploratory_session_report(
        request=session_request(
            [session_entry("event-003", job_id)]
        ),
        db=session_db,
        pipeline_version="session-test-v1",
    )
    serialized = json.dumps(result)

    assert "TCGA-AB-1234" not in serialized
    assert '"idh": "Mut"' not in serialized
    assert (
        result["audit"]["privacy_contract"][
            "external_covariate_rows_embedded"
        ]
        is False
    )
    assert result["audit"]["source_jobs"][0]["request_sha256"]


def test_managed_multiverse_is_referenced_without_recounting(session_db):
    job_id = "d" * 32
    add_job(
        session_db,
        job_id=job_id,
        kind="multiverse",
        request_payload={"cohort": "TCGA-LIHC"},
        result_json={
            "session_id": "mv_example",
            "summary": {"planned": 5, "completed": 5},
            "analysis_family": {
                "primary_continuous_family": {
                    "evaluable_tests": 1
                }
            },
            "audit": {
                "family_reproducibility_hash": "mv-family-hash"
            },
        },
        result_id="mv_example",
    )

    result = build_exploratory_session_report(
        request=session_request(
            [session_entry("event-004", job_id, "Multiverse")]
        ),
        db=session_db,
        pipeline_version="session-test-v1",
    )

    assert result["hypotheses"] == []
    assert len(result["managed_family_references"]) == 1
    reference = result["managed_family_references"][0]
    assert reference["kind"] == "multiverse"
    assert reference["recounted_in_session_family"] is False
    assert reference["audit_reproducibility_hash"] == "mv-family-hash"


def test_session_bundle_is_attested_and_contains_no_patient_rows(
    session_db,
    tmp_path,
):
    job_id = "e" * 32
    add_job(
        session_db,
        job_id=job_id,
        kind="analysis",
        request_payload=analysis_request("median"),
        result_json=analysis_result(
            "analysis-bundle",
            cutpoint="median",
            grouped_p=0.02,
        ),
        result_id="analysis-bundle",
    )
    result = build_exploratory_session_report(
        request=session_request(
            [session_entry("event-005", job_id)]
        ),
        db=session_db,
        pipeline_version="session-test-v1",
    )
    settings = Settings(
        _env_file=None,
        artifact_dir=tmp_path,
        public_base_url="https://example.test/tcga-trace",
        attestation_private_key_path=tmp_path / "key.pem",
    )

    paths = write_exploratory_session_artifacts(
        tmp_path,
        result,
        settings=settings,
    )

    assert all(path.exists() for path in paths.values())
    receipt = json.loads(paths["attestation"].read_text())
    key = attestation_key_document(
        settings,
        receipt["signature"]["key_id"],
    )
    verification = verify_attestation_receipt(
        receipt,
        key,
        audit_bytes=paths["audit_json"].read_bytes(),
    )
    assert verification["status"] == "passed"
    assert "post hoc record" in paths["methodology"].read_text()
    assert "No retained/not-retained verdict" in paths[
        "methodology"
    ].read_text()
