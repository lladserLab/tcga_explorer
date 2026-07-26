import json
import re

import pytest
from pydantic import ValidationError

import app.multiverse as multiverse_module
from app.analysis_notices import (
    DSS_COMPETING_RISK_MESSAGE,
    ZSCORE_TRANSPORTABILITY_MESSAGE,
)
from app.attestation import (
    attestation_key_document,
    verify_attestation_receipt,
)
from app.config import Settings
from app.multiverse import (
    benjamini_hochberg,
    expand_multiverse_request,
    summarize_multiverse,
    write_multiverse_artifacts,
)
from app.schemas import MultiverseAnalysisOut, MultiverseAnalysisRequest, SignatureGene


def multiverse_request(**overrides):
    payload = {
        "cohort": "TCGA-LIHC",
        "genes": [SignatureGene(gene_symbol="CDC20")],
        "endpoints": ["OS"],
        "scoring_methods": ["single"],
        "cutpoint_methods": ["maxstat", "median"],
        "adjustment_covariates": ["age_at_index"],
    }
    payload.update(overrides)
    return MultiverseAnalysisRequest(**payload)


def model(model_id, *, hazard_ratio, p_value, label=None):
    return {
        "model": model_id,
        "label": label or model_id,
        "status": "completed",
        "hazard_ratio": hazard_ratio,
        "hr_conf_low": hazard_ratio * 0.8,
        "hr_conf_high": hazard_ratio * 1.2,
        "p_value": p_value,
        "ph_p_value": 0.45,
        "ph_global_p_value": 0.32,
        "n_patients": 100,
        "n_events": 40,
        "information_diagnostics": {
            "parameter_count": 2,
            "events_per_parameter": 20,
            "status": "adequate",
        },
        "penalized_sensitivity": {"status": "not_triggered"},
    }


def completed_item(specification, *, logrank_p, corrected_p=None):
    method = specification["cutpoint_method"]
    metrics = {
        "n_patients": 100,
        "n_events": 40,
        "group_counts": {"Low": 50, "High": 50},
        "event_counts": {"Low": 15, "High": 25},
        "logrank_p_value": logrank_p,
        "cutpoint_details": {
            "method": method,
            "corrected_p_status": "completed" if corrected_p is not None else None,
            "corrected_p_value": corrected_p,
        },
        "cox_models": [
            model("univariable", hazard_ratio=1.7, p_value=0.01),
            model(
                "user_adjusted",
                hazard_ratio=1.6,
                p_value=0.02,
                label="User-adjusted for Age",
            ),
        ],
        "continuous_analysis": {
            "n_patients": 100,
            "n_events": 40,
            "linear_models": [
                model(
                    "continuous_univariable",
                    hazard_ratio=1.5,
                    p_value=0.005,
                ),
                model(
                    "continuous_user_adjusted",
                    hazard_ratio=1.45,
                    p_value=0.01,
                    label="Continuous expression user-adjusted for Age",
                ),
            ],
        },
        "rmst": {
            "status": "completed",
            "tau_days": 1826.25,
            "at_risk_at_tau": {"Low": 10, "High": 11},
            "difference": {
                "estimate_days": -120,
                "conf_low": -210,
                "conf_high": -30,
                "p_value": 0.01,
            },
        },
        "audit_report": {
            "reproducibility_hash": f"audit-{specification['specification_id']}",
            "patient_records_sha256": f"group-{specification['specification_id']}",
            "continuous_patient_records_sha256": "continuous-population",
        },
    }
    return {
        "index": specification["index"],
        "status": "completed",
        "result": {
            "id": f"analysis-{specification['specification_id']}",
            "metrics": metrics,
            "downloads": {"zip": f"/analyses/{specification['specification_id']}.zip"},
        },
    }


def test_multiverse_contract_rejects_incompatible_scoring():
    with pytest.raises(ValidationError, match="exactly one gene"):
        multiverse_request(
            genes=[
                SignatureGene(gene_symbol="CDC20"),
                SignatureGene(gene_symbol="BIRC5"),
            ]
        )

    with pytest.raises(ValidationError, match="at least two genes"):
        multiverse_request(scoring_methods=["zscore"])


def test_expand_multiverse_request_is_deterministic_and_cartesian():
    request = multiverse_request(
        genes=[
            SignatureGene(gene_symbol="CDC20", weight=1),
            SignatureGene(gene_symbol="BIRC5", weight=-1),
        ],
        endpoints=["OS", "DSS"],
        scoring_methods=["mean", "zscore"],
        cutpoint_methods=["median", "percentile"],
        custom_percentile=65,
    )

    first = expand_multiverse_request(request)
    second = expand_multiverse_request(request)

    assert len(first) == 8
    assert [row["specification_id"] for row in first] == [
        f"S{index:03d}" for index in range(1, 9)
    ]
    assert [row["analysis_request_hash"] for row in first] == [
        row["analysis_request_hash"] for row in second
    ]
    percentile = next(
        row for row in first if row["cutpoint_method"] == "percentile"
    )
    assert percentile["analysis_request"].custom_percentile == 65
    median = next(row for row in first if row["cutpoint_method"] == "median")
    assert median["analysis_request"].custom_percentile is None


def test_benjamini_hochberg_preserves_missing_positions():
    assert benjamini_hochberg([0.01, None, 0.04, 0.03]) == pytest.approx(
        [0.03, None, 0.04, 0.04],
        nan_ok=True,
    )


def test_multiverse_uses_separate_families_and_corrected_maxstat():
    request = multiverse_request()
    specifications = expand_multiverse_request(request)
    items = [
        completed_item(specifications[0], logrank_p=0.0001, corrected_p=0.02),
        completed_item(specifications[1], logrank_p=0.04),
    ]

    result = summarize_multiverse(
        session_id="mv_test",
        request=request,
        specifications=specifications,
        completed_items=items,
        pipeline_version="test-v1",
        data_version={"manifest": "abc"},
        generated_at="2026-07-25T12:00:00+00:00",
    )

    MultiverseAnalysisOut(**result)
    assert result["analysis_family"]["binary_verdict"] is False
    assert result["analysis_family"]["primary_continuous_family"]["planned_tests"] == 1
    assert result["analysis_family"]["grouped_sensitivity_family"]["planned_tests"] == 2
    assert result["specifications"][0]["inference_test"] == "maxstat_lau94_corrected"
    assert result["specifications"][0]["inference_p_value"] == pytest.approx(0.02)
    assert result["specifications"][0]["grouped_bh_q_value"] == pytest.approx(0.04)
    assert result["specifications"][1]["grouped_bh_q_value"] == pytest.approx(0.04)
    assert len(result["continuous_references"]) == 1
    reference = result["continuous_references"][0]
    assert reference["continuous_bh_q_value"] == pytest.approx(0.01)
    assert reference["effect"]["model"] == "continuous_user_adjusted"
    assert result["specifications"][0]["grouped_effect"]["model"] == "user_adjusted"
    assert len(result["execution_ledger"]) == 2


def test_multiverse_records_failed_specifications_and_writes_bundle(tmp_path):
    request = multiverse_request()
    specifications = expand_multiverse_request(request)
    items = [
        completed_item(specifications[0], logrank_p=0.02, corrected_p=0.03),
        {
            "index": specifications[1]["index"],
            "status": "failed",
            "code": "ENDPOINT_UNAVAILABLE",
            "error": "Endpoint did not pass QC.",
        },
    ]
    result = summarize_multiverse(
        session_id="mv_bundle",
        request=request,
        specifications=specifications,
        completed_items=items,
        pipeline_version="test-v1",
        data_version={"manifest": "abc"},
    )

    settings = Settings(
        _env_file=None,
        artifact_dir=tmp_path,
        public_base_url="https://example.test/tcga-trace",
        attestation_private_key_path=tmp_path / "key.pem",
    )
    paths = write_multiverse_artifacts(
        tmp_path,
        result,
        settings=settings,
    )

    assert result["status"] == "completed_with_failures"
    assert result["summary"]["failed"] == 1
    assert all(path.exists() for path in paths.values())
    receipt = json.loads(paths["attestation"].read_text())
    key = attestation_key_document(
        settings,
        receipt["signature"]["key_id"],
    )
    assert verify_attestation_receipt(
        receipt,
        key,
        audit_bytes=paths["audit_json"].read_bytes(),
    )["status"] == "passed"
    assert "No binary evidence verdict" in paths["audit_html"].read_text()
    ledger = json.loads(paths["ledger"].read_text())
    assert ledger["entries"][1]["error_code"] == "ENDPOINT_UNAVAILABLE"
    svg = paths["svg"].read_text()
    assert "<title>TCGA-TRACE prespecified specification curve</title>" in svg
    endpoint_tracks = re.findall(
        r'<rect x="([0-9.]+)" y="338" width="([0-9.]+)"',
        svg,
    )
    centers = [float(x) + float(width) / 2 for x, width in endpoint_tracks]
    assert len(centers) == 2
    assert centers[1] - centers[0] > 300


def test_multiverse_zscore_dss_context_is_visible_and_audited(tmp_path):
    request = multiverse_request(
        genes=[
            SignatureGene(gene_symbol="BAP1"),
            SignatureGene(gene_symbol="EZH2"),
        ],
        endpoints=["DSS"],
        scoring_methods=["zscore"],
        cutpoint_methods=["median"],
    )
    specifications = expand_multiverse_request(request)
    result = summarize_multiverse(
        session_id="mv_context",
        request=request,
        specifications=specifications,
        completed_items=[
            completed_item(specifications[0], logrank_p=0.02),
        ],
        pipeline_version="test-v1",
        data_version={"manifest": "abc"},
    )

    assert ZSCORE_TRANSPORTABILITY_MESSAGE in result["warnings"]
    assert DSS_COMPETING_RISK_MESSAGE in result["warnings"]
    context = result["analysis_family"]["interpretation_context"]
    assert (
        context["score_transportability"][
            "numerically_transportable_across_runs"
        ]
        is False
    )
    assert context["endpoint_estimands"]["DSS"]["fine_gray_provided"] is False
    assert result["audit"]["interpretation_context"] == context

    paths = write_multiverse_artifacts(tmp_path, result)
    methodology = paths["methodology"].read_text()
    html = paths["audit_html"].read_text()
    assert ZSCORE_TRANSPORTABILITY_MESSAGE in methodology
    assert DSS_COMPETING_RISK_MESSAGE in methodology
    assert ZSCORE_TRANSPORTABILITY_MESSAGE in html
    assert DSS_COMPETING_RISK_MESSAGE in html


def test_multiverse_result_is_not_published_before_artifacts_complete(
    tmp_path,
    monkeypatch,
):
    request = multiverse_request()
    specifications = expand_multiverse_request(request)
    result = summarize_multiverse(
        session_id="mv_atomic",
        request=request,
        specifications=specifications,
        completed_items=[
            completed_item(specifications[0], logrank_p=0.02, corrected_p=0.03),
            completed_item(specifications[1], logrank_p=0.04),
        ],
        pipeline_version="test-v1",
        data_version={"manifest": "abc"},
    )

    def fail_svg(_result):
        raise RuntimeError("synthetic renderer failure")

    monkeypatch.setattr(
        multiverse_module,
        "render_specification_curve_svg",
        fail_svg,
    )

    with pytest.raises(RuntimeError, match="synthetic renderer failure"):
        write_multiverse_artifacts(tmp_path, result)

    result_path = (
        tmp_path
        / "multiverse"
        / "mv_atomic"
        / "multiverse_result.json"
    )
    assert not result_path.exists()
