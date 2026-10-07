import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.analysis_notices import build_analysis_diagnostics
from app.config import Settings
from app.main import analysis_request_for_signature_spec
from app.r_runner import ensure_svg_artifact
from app.schemas import (
    SignatureGene,
    SignaturePanelAnalysisRequest,
    SignatureSpec,
)
from app.signature_panel import (
    build_signature_panel_records,
    run_signature_panel_r,
    signature_gene_overlap,
    standardize_signature_scores,
    write_signature_panel_audit,
    write_signature_panel_reproduction_capsule,
)
from app.survival import ClinicalOutcome


def signature(
    name: str,
    *genes: str,
    method: str = "zscore",
) -> SignatureSpec:
    return SignatureSpec(
        name=name,
        gene_symbol=", ".join(genes),
        signature_method=method,
        signature_genes=[
            SignatureGene(gene_symbol=gene)
            for gene in genes
        ],
    )


def test_signature_panel_request_accepts_two_to_six_unique_signatures() -> None:
    request = SignaturePanelAnalysisRequest(
        cohort="TCGA-KIRC",
        panel_name="Immune states",
        signatures=[
            signature("Effector", "IFNG", "GZMB"),
            signature("Exhaustion", "PDCD1", "LAG3"),
        ],
        adjustment_covariates=["age_at_index", "stage", "stage"],
    )

    assert request.panel_name == "Immune states"
    assert len(request.signatures) == 2
    assert request.adjustment_covariates == ["age_at_index", "stage"]

    score_request = analysis_request_for_signature_spec(
        request,
        request.signatures[0],
    )
    assert score_request.show_confidence_interval is True
    assert score_request.show_risk_table is False


def test_signature_panel_request_rejects_ambiguous_panels() -> None:
    with pytest.raises(ValidationError, match="unique ignoring case"):
        SignaturePanelAnalysisRequest(
            cohort="TCGA-KIRC",
            signatures=[
                signature("Effector", "IFNG", "GZMB"),
                signature("effector", "PDCD1", "LAG3"),
            ],
        )

    with pytest.raises(ValidationError, match="duplicate signature definitions"):
        SignaturePanelAnalysisRequest(
            cohort="TCGA-KIRC",
            signatures=[
                signature("First", "IFNG", "GZMB"),
                signature("Second", "GZMB", "IFNG"),
            ],
        )

    with pytest.raises(ValidationError, match="duplicate signature definitions"):
        SignaturePanelAnalysisRequest(
            cohort="TCGA-KIRC",
            signatures=[
                SignatureSpec(
                    name="Mean one",
                    gene_symbol="IFNG, GZMB",
                    signature_method="mean",
                    signature_genes=[
                        SignatureGene(gene_symbol="IFNG", weight=1),
                        SignatureGene(gene_symbol="GZMB", weight=1),
                    ],
                ),
                SignatureSpec(
                    name="Mean two",
                    gene_symbol="IFNG, GZMB",
                    signature_method="mean",
                    signature_genes=[
                        SignatureGene(gene_symbol="IFNG", weight=1),
                        SignatureGene(gene_symbol="GZMB", weight=1),
                    ],
                ),
            ],
        )

    with pytest.raises(ValidationError):
        SignaturePanelAnalysisRequest(
            cohort="TCGA-KIRC",
            signatures=[signature("Only one", "IFNG")],
        )

    with pytest.raises(ValidationError, match="requires exactly one gene"):
        SignaturePanelAnalysisRequest(
            cohort="TCGA-KIRC",
            signatures=[
                signature("Ambiguous single", "IFNG", "GZMB", method="single"),
                signature("Valid", "PDCD1", "LAG3"),
            ],
        )

    with pytest.raises(ValidationError, match="weights must be finite"):
        SignaturePanelAnalysisRequest(
            cohort="TCGA-KIRC",
            signatures=[
                SignatureSpec(
                    name="Invalid weight",
                    gene_symbol="IFNG",
                    signature_method="weighted",
                    signature_genes=[
                        SignatureGene(gene_symbol="IFNG", weight=float("inf")),
                    ],
                ),
                signature("Valid", "PDCD1"),
            ],
        )


def test_panel_scores_share_one_population_and_one_sd_unit() -> None:
    samples = [
        SimpleNamespace(barcode=f"S{index:02d}")
        for index in range(1, 13)
    ]
    first = {
        sample.barcode: float(index)
        for index, sample in enumerate(samples, start=1)
    }
    second = {
        sample.barcode: float(index * 2 + 1)
        for index, sample in enumerate(samples, start=1)
        if index != 1
    }
    second[samples[1].barcode] = float("nan")

    scores, summaries = standardize_signature_scores(
        samples,
        [first, second],
        ["First", "Second"],
    )

    assert len(scores[0]) == len(scores[1]) == 10
    assert set(scores[0]) == set(scores[1])
    assert sum(scores[0].values()) == pytest.approx(0)
    assert summaries[0]["effect_unit"] == "+1 within-panel score SD"
    assert summaries[1]["has_variation"] is True


def test_panel_records_preserve_endpoint_and_competing_event_coding() -> None:
    samples = [
        SimpleNamespace(
            patient_id=f"P{index:02d}",
            barcode=f"S{index:02d}",
            sample_type="Primary Tumor",
            stage="Stage II",
            grade="G2",
            gender="female",
            race="WHITE",
            age_at_index=60 + index,
            os_time_days=None,
            os_event=None,
        )
        for index in range(1, 13)
    ]
    scores = [
        {sample.barcode: float(index) for index, sample in enumerate(samples)},
        {
            sample.barcode: float(index) / 2
            for index, sample in enumerate(samples)
        },
    ]
    outcomes = {
        sample.patient_id: ClinicalOutcome(
            endpoint="DSS",
            time_days=float(100 + index),
            event=1 if index <= 5 else 0,
            source="test",
            competing_risk_status=1 if index <= 5 else 2 if index == 6 else 0,
            competing_event=1 if index == 6 else 0,
            competing_risk_source="test",
        )
        for index, sample in enumerate(samples, start=1)
    }

    records = build_signature_panel_records(
        samples,
        scores,
        endpoint_by_patient=outcomes,
        endpoint="DSS",
        max_time_days=None,
    )

    assert len(records) == 12
    assert sum(record["event"] for record in records) == 5
    assert records[5]["competing_risk_status"] == 2
    assert set(key for key in records[0] if key.startswith("signature_")) == {
        "signature_1",
        "signature_2",
    }


def test_gene_overlap_is_descriptive_and_allows_shared_genes() -> None:
    overlap = signature_gene_overlap(
        [
            {
                "name": "A",
                "genes": [
                    {"resolved_symbol": "IFNG"},
                    {"resolved_symbol": "GZMB"},
                ],
            },
            {
                "name": "B",
                "genes": [
                    {"resolved_symbol": "GZMB"},
                    {"resolved_symbol": "PDCD1"},
                ],
            },
        ]
    )

    assert overlap["status"] == "reported"
    assert overlap["pairs"][0]["shared_genes"] == ["GZMB"]
    assert overlap["pairs"][0]["jaccard"] == pytest.approx(1 / 3)


def test_panel_diagnostics_fall_back_to_joint_unadjusted_primary() -> None:
    metrics = {
        "clinical_adjustment": {"status": "requested"},
        "signature_panel_cox_models": [
            {
                "model": "panel_joint_unadjusted",
                "label": "Joint unadjusted",
                "family": "joint",
                "status": "completed",
                "information_diagnostics": {"status": "adequate"},
                "marker_terms": [],
                "warnings": [],
            },
            {
                "model": "panel_joint_adjusted",
                "label": "Joint adjusted",
                "family": "adjusted",
                "status": "skipped",
                "reason": "Fewer than 10 complete patients.",
                "marker_terms": [],
                "warnings": [],
            },
        ],
    }

    notices, diagnostics = build_analysis_diagnostics([], metrics)

    assert diagnostics["primary_result_model"] == "panel_joint_unadjusted"
    assert diagnostics["primary_result_status"] == "clean"
    assert diagnostics["selected_adjusted_status"] == "not_evaluable"
    adjusted = [
        notice
        for notice in notices
        if notice["code"] == "adjusted_model_not_evaluable"
    ]
    assert adjusted[0]["scope"] == "requested_adjustment"
    assert adjusted[0]["priority"] == "medium"


def test_panel_diagnostics_escalate_only_when_joint_primary_is_unavailable() -> None:
    notices, diagnostics = build_analysis_diagnostics(
        [],
        {
            "signature_panel_cox_models": [
                {
                    "model": "panel_univariable_1",
                    "label": "A univariable",
                    "family": "univariable",
                    "status": "completed",
                    "marker_terms": [],
                    "warnings": [],
                },
                {
                    "model": "panel_joint_unadjusted",
                    "label": "Joint unadjusted",
                    "family": "joint",
                    "status": "failed",
                    "reason": "The joint fit was singular.",
                    "marker_terms": [],
                    "warnings": [],
                },
            ],
        },
    )

    assert diagnostics["primary_result_status"] == "not_evaluable"
    primary = [
        notice
        for notice in notices
        if notice["code"] == "primary_model_not_evaluable"
    ]
    assert primary[0]["severity"] == "error"
    assert primary[0]["scope"] == "primary"
    assert primary[0]["priority"] == "high"


def test_signature_panel_r_engine_writes_joint_and_adjusted_artifacts(
    tmp_path,
) -> None:
    records = []
    for index in range(1, 49):
        records.append(
            {
                "patient_id": f"P{index:03d}",
                "sample_barcode": f"S{index:03d}",
                "endpoint": "OS",
                "time_days": float(100 + ((index * 37) % 811)),
                "event": int(((index * 11) % 17) < 8),
                "competing_risk_status": None,
                "competing_event": None,
                "competing_risk_source": None,
                "sample_type": "Primary Tumor",
                "stage": ["Stage I", "Stage II", "Stage III"][index % 3],
                "grade": ["G1", "G2", "G3"][index % 3],
                "gender": "female" if index % 2 else "male",
                "race": "WHITE",
                "age_at_index": 40 + (index % 31),
                "signature_1": ((index * 7) % 23 - 11) / 6,
                "signature_2": ((index * 13) % 29 - 14) / 7,
            }
        )
    settings = Settings(
        artifact_dir=tmp_path,
        public_base_url="https://example.test/tcga-trace",
        attestation_enabled=True,
        attestation_auto_generate=True,
        attestation_private_key_path=tmp_path / "keys" / "ed25519-private.pem",
    )
    metrics = run_signature_panel_r(
        settings=settings,
        analysis_id="panel-integration",
        payload={
            "panel_name": "Integration panel",
            "endpoint": "OS",
            "signatures": [
                {"name": "Effector"},
                {"name": "Checkpoint"},
            ],
            "adjustment_covariates": ["age_at_index", "stage"],
            "external_adjustment_covariates": [],
            "external_covariates": {"definitions": []},
            "plot_style": {
                "base_font_size": 12,
                "plot_aspect": "landscape",
                "cox_forest": {
                    "model_layout": "separate",
                    "show_title": True,
                },
            },
        },
        records=records,
    )

    assert metrics["model_families"]["joint"]["status"] == "completed", (
        metrics["model_families"]["joint"].get("reason")
    )
    assert metrics["model_families"]["adjusted"]["status"] == "completed", (
        metrics["model_families"]["adjusted"].get("reason")
    )
    forest_output = metrics["cox_forest_output"]
    assert forest_output["model_layout"] == "separate"
    assert forest_output["shared_axis_across_model_families"] is True
    assert forest_output["export_width_inches"] == 9.4
    assert forest_output["signature_row_slots"] == 2
    assert forest_output["row_spacing_inches"] == 0.42
    assert 0 < forest_output["shared_log10_axis_limits"][0] < 1
    assert forest_output["shared_log10_axis_limits"][1] > 1
    artifacts = metrics["artifact_paths"]
    assert Path(artifacts["png"]).is_file()
    assert Path(artifacts["signature_panel_joint_png"]).is_file()
    assert Path(artifacts["signature_panel_adjusted_png"]).is_file()
    assert Path(artifacts["model_results_csv"]).is_file()
    assert Path(artifacts["correlations_csv"]).is_file()
    reproduction_manifest = json.loads(
        Path(artifacts["reproduction_manifest"]).read_text(
            encoding="utf-8"
        )
    )
    assert (
        reproduction_manifest["files"]["expected_results"]["filename"]
        == "expected_results.json"
    )
    expected_results_path = Path(
        artifacts["reproduction_expected_results"]
    )
    expected_results_before = expected_results_path.read_bytes()
    reproduction_manifest_path = Path(
        artifacts["reproduction_manifest"]
    )
    reproduction_manifest_before = (
        reproduction_manifest_path.read_bytes()
    )

    metrics_json_before = Path(artifacts["json"]).read_bytes()
    Path(artifacts["svg"]).unlink()
    Path(artifacts["signature_panel_joint_svg"]).unlink()
    regenerated_svg = ensure_svg_artifact(
        settings,
        "panel-integration",
    )
    assert regenerated_svg.is_file()
    assert Path(artifacts["signature_panel_joint_svg"]).is_file()
    assert Path(artifacts["json"]).read_bytes() == metrics_json_before

    Path(artifacts["json"]).write_text(
        json.dumps(
            {**metrics, "endpoint_label": "Enriched after R"},
            ensure_ascii=False,
            allow_nan=False,
        ),
        encoding="utf-8",
    )
    write_signature_panel_reproduction_capsule(
        tmp_path / "panel-integration",
        script_path=(
            Path(__file__).resolve().parents[1]
            / "scripts"
            / "signature_panel.R"
        ),
        renv_lock_path=(
            Path(__file__).resolve().parents[1] / "renv.lock"
        ),
    )
    assert expected_results_path.read_bytes() == expected_results_before
    assert (
        reproduction_manifest_path.read_bytes()
        == reproduction_manifest_before
    )

    audit = write_signature_panel_audit(
        settings=settings,
        analysis_id="panel-integration",
        request_payload={
            "cohort": "TCGA-SKCM",
            "endpoint": "OS",
            "pipeline_version": "test-panel-v1",
        },
        metrics=metrics,
        records=records,
        scoring_provenance={"signatures": []},
        data_provenance={"dataset": "test"},
        data_dates={"snapshot": "test"},
        warnings=[],
    )
    audit_report = Path(
        tmp_path / "panel-integration" / "audit_report.json"
    )
    report = json.loads(
        audit_report.read_text(encoding="utf-8")
    )
    assert audit["schema_version"] == "tcga-trace-signature-panel-audit-v1"
    assert "json" not in report["artifacts"]
    assert (
        report["artifacts"]["reproduction_expected_results"]["filename"]
        == "expected_results.json"
    )
    assert "reproduction_manifest" in report["artifacts"]
