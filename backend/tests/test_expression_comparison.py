from dataclasses import dataclass
import hashlib
import io
import json
import math
from pathlib import Path
from types import SimpleNamespace
import xml.etree.ElementTree as ET
import zipfile

import pytest
from fastapi import Request
from pydantic import ValidationError

from app import main as main_module
from app.expression_comparison import (
    extract_expression_value_rows,
    finalize_expression_comparison_artifacts,
    resolve_expression_genes,
    run_expression_comparison_engine,
)
from app.gsea import ExpressionMatrix, MatrixGene
from app.models import Cohort
from app.repository.storage import write_float32le_matrix
from app.r_runner import stable_hash
from app.schemas import (
    ExpressionComparisonRequest,
    GseaGroupingDefinition,
)


@dataclass
class MockSample:
    patient_id: str
    barcode: str
    sample_type: str = "Primary Tumor"
    stage: str | None = None
    grade: str | None = None
    gender: str | None = None
    race: str | None = None
    age_at_index: float | None = None
    cohort: str = "TCGA-TEST"


def clinical_grouping() -> GseaGroupingDefinition:
    return GseaGroupingDefinition(
        source="clinical",
        clinical_variable="stage",
        group_a_label="Early",
        group_b_label="Advanced",
        group_a_values=["Stage I"],
        group_b_values=["Stage II"],
    )


def test_expression_comparison_request_normalizes_genes_and_bounds() -> None:
    request = ExpressionComparisonRequest(
        cohort="TCGA-TEST",
        genes=[" tp53 ", "TP53", "egfr"],
        grouping=clinical_grouping(),
    )
    assert request.genes == ["TP53", "EGFR"]
    assert request.fdr_threshold == 0.05
    assert request.heatmap_max_samples == 300

    with pytest.raises(ValidationError, match="supplied together"):
        ExpressionComparisonRequest(
            cohort="TCGA-TEST",
            dataset_id="dataset",
            genes=["TP53"],
            grouping=clinical_grouping(),
        )
    with pytest.raises(ValidationError):
        ExpressionComparisonRequest(
            cohort="TCGA-TEST",
            genes=[f"G{index}" for index in range(26)],
            grouping=clinical_grouping(),
        )


def test_matrix_resolution_and_extraction_preserve_b_minus_a_direction(
    tmp_path: Path,
) -> None:
    matrix_path = tmp_path / "matrix.bin"
    write_float32le_matrix(
        matrix_path,
        [
            [1, 2, 3, 4, 5, 6],
            [10, 9, 8, 7, 6, 5],
        ],
    )
    matrix = ExpressionMatrix(
        path=matrix_path,
        sample_ids=[f"S{index}" for index in range(6)],
        genes=[
            MatrixGene(symbol="TP53", row_number=0),
            MatrixGene(symbol="EGFR", row_number=1),
        ],
        dtype="float32",
        byte_order="little",
        expression_scale="log2_tpm",
        expression_scale_label="log2(TPM + 1)",
        source_sha256=hashlib.sha256(matrix_path.read_bytes()).hexdigest(),
    )
    resolved, warnings = resolve_expression_genes(
        matrix,
        ["P53", "EGFR"],
    )
    assert [row["gene_symbol"] for row in resolved] == ["TP53", "EGFR"]
    assert any("alias" in warning.lower() for warning in warnings)
    assignments = {
        **{f"S{index}": "a" for index in range(3)},
        **{f"S{index}": "b" for index in range(3, 6)},
    }
    samples = [MockSample(f"P{index}", f"S{index}") for index in range(6)]
    rows = extract_expression_value_rows(
        matrix,
        resolved,
        assignments,
        samples,
        group_a_label="A",
        group_b_label="B",
    )
    tp53_a = [
        row["expression_value"]
        for row in rows
        if row["gene_symbol"] == "TP53" and row["group_key"] == "a"
    ]
    tp53_b = [
        row["expression_value"]
        for row in rows
        if row["gene_symbol"] == "TP53" and row["group_key"] == "b"
    ]
    assert sum(tp53_b) / len(tp53_b) - sum(tp53_a) / len(tp53_a) == 3


def test_r_engine_has_separate_bh_families_and_excludes_circular_gene(
    tmp_path: Path,
) -> None:
    sample_ids = [f"A{index}" for index in range(6)] + [
        f"B{index}" for index in range(6)
    ]
    assignments = {
        **{sample_id: "a" for sample_id in sample_ids[:6]},
        **{sample_id: "b" for sample_id in sample_ids[6:]},
    }
    samples = [MockSample(f"P-{sample_id}", sample_id) for sample_id in sample_ids]
    rows: list[dict] = []
    series = {
        "UP": ([1, 2, 2, 3, 3, 4], [7, 8, 8, 9, 9, 10]),
        "DOWN": ([8, 9, 9, 10, 10, 11], [3, 4, 4, 5, 5, 6]),
        "CIRC": ([1, 2, 3, 4, 5, 6], [8, 9, 10, 11, 12, 13]),
        "TIE": ([4] * 6, [4] * 6),
    }
    for gene, (values_a, values_b) in series.items():
        for sample_id, value in zip(sample_ids, values_a + values_b, strict=True):
            rows.append(
                {
                    "patient_id": f"P-{sample_id}",
                    "sample_barcode": sample_id,
                    "gene_symbol": gene,
                    "group_key": assignments[sample_id],
                    "group_label": "A" if assignments[sample_id] == "a" else "B",
                    "expression_value": value,
                }
            )
    assignment_rows = [
        {
            "patient_id": sample.patient_id,
            "sample_barcode": sample.barcode,
            "group_key": assignments[sample.barcode],
            "group_label": "A" if assignments[sample.barcode] == "a" else "B",
        }
        for sample in samples
    ]
    resolved = [
        {
            "requested_symbol": gene,
            "gene_symbol": gene,
            "row_number": index,
            "resolution": "exact",
        }
        for index, gene in enumerate(series)
    ]
    policies = {
        gene: {
            "inferential_status": (
                "descriptive_only" if gene == "CIRC" else "inferential"
            ),
            "included_in_multiplicity": gene != "CIRC",
            "circularity_reason": (
                "grouping overlap" if gene == "CIRC" else None
            ),
        }
        for gene in series
    }
    output_dir = tmp_path / "expression_comparisons" / "exprcmp-fixture"
    scientific_input = {
        "schema_version": "tcga-trace-expression-comparison-input-v1",
        "request": {"cohort": "TCGA-TEST", "genes": list(series)},
    }
    metrics = run_expression_comparison_engine(
        output_dir,
        request_payload=scientific_input,
        value_rows=rows,
        assignment_rows=assignment_rows,
        resolved_genes=resolved,
        gene_policies=policies,
        group_a_label="A",
        group_b_label="B",
        fdr_threshold=0.05,
        heatmap_max_samples=20,
        pipeline_version="fixture-v1",
    )
    by_gene = {row["gene_symbol"]: row for row in metrics["statistics"]}
    assert by_gene["UP"]["mean_difference_b_minus_a"] > 0
    assert by_gene["UP"]["welch_t"]["statistic"] > 0
    assert by_gene["UP"]["rank_biserial"] > 0
    assert by_gene["DOWN"]["mean_difference_b_minus_a"] < 0
    assert by_gene["CIRC"]["inferential_status"] == "descriptive_only"
    assert by_gene["CIRC"]["welch_t"]["p_value"] is None
    assert by_gene["CIRC"]["mann_whitney"]["p_value"] is None
    assert by_gene["CIRC"]["significant_at_fdr"] is False
    assert by_gene["TIE"]["welch_t"]["p_value"] == 1
    assert by_gene["TIE"]["mann_whitney"]["p_value"] == 1
    assert by_gene["TIE"]["rank_biserial"] == 0
    assert metrics["summary"]["heatmap_samples"] == 12

    result_payload = {
        "grouping": {"group_a_label": "A", "group_b_label": "B"},
        "summary": {
            "fdr_threshold": 0.05,
            **metrics["summary"],
        },
        "statistics": metrics["statistics"],
        "warnings": ["fixture"],
        "data_provenance": {"matrix_sha256": "a" * 64},
    }
    audit = finalize_expression_comparison_artifacts(
        output_dir,
        request_payload=scientific_input,
        result_payload=result_payload,
        pipeline_version="fixture-v1",
    )
    assert audit["request_sha256"] == stable_hash(
        json.loads((output_dir / "input.json").read_text(encoding="utf-8"))
    )
    assert set(
        record["filename"] for record in audit["artifacts"].values()
    ) == {
        "input.json",
        "expression_values.csv",
        "sample_groups.csv",
        "gene_statistics.csv",
        "violin_plot.svg",
        "boxplot.svg",
        "heatmap.svg",
        "methodology.txt",
    }
    for filename in ["violin_plot.svg", "boxplot.svg", "heatmap.svg"]:
        root = ET.parse(output_dir / filename).getroot()
        assert root.attrib["role"] == "img"

    # An indexed all-missing row is valid in private datasets. It must produce
    # neutral placeholders and a not-evaluable row, not abort the whole job.
    missing_dir = tmp_path / "expression_comparisons" / "exprcmp-all-missing"
    missing_metrics = run_expression_comparison_engine(
        missing_dir,
        request_payload={
            "schema_version": "tcga-trace-expression-comparison-input-v1",
            "request": {"cohort": "PRIVATE", "genes": ["ALL_MISSING"]},
        },
        value_rows=[],
        assignment_rows=assignment_rows,
        resolved_genes=[
            {
                "requested_symbol": "ALL_MISSING",
                "gene_symbol": "ALL_MISSING",
                "row_number": 0,
                "resolution": "exact",
            }
        ],
        gene_policies={
            "ALL_MISSING": {
                "inferential_status": "inferential",
                "included_in_multiplicity": True,
            }
        },
        group_a_label="A",
        group_b_label="B",
        fdr_threshold=0.05,
        heatmap_max_samples=20,
        pipeline_version="fixture-v1",
    )
    missing_row = missing_metrics["statistics"][0]
    assert missing_row["status"] == "not_evaluable"
    assert missing_row["group_a"]["n"] == 0
    assert missing_row["group_b"]["n"] == 0
    for filename in ["violin_plot.svg", "boxplot.svg", "heatmap.svg"]:
        ET.parse(missing_dir / filename)


def test_expression_comparison_orchestration_and_download_bundle(
    tmp_path: Path,
    monkeypatch,
) -> None:
    sample_ids = [f"A{index}" for index in range(5)] + [
        f"B{index}" for index in range(5)
    ]
    matrix_path = tmp_path / "matrix.bin"
    write_float32le_matrix(
        matrix_path,
        [
            [1, 2, 2, 3, 4, 7, 8, 8, 9, 10],
            [10, 9, 9, 8, 7, 4, 3, 3, 2, 1],
        ],
    )
    matrix = ExpressionMatrix(
        path=matrix_path,
        sample_ids=sample_ids,
        genes=[
            MatrixGene(symbol="UP", row_number=0),
            MatrixGene(symbol="DOWN", row_number=1),
        ],
        dtype="float32",
        byte_order="little",
        expression_scale="log2_tpm",
        expression_scale_label="log2(TPM + 1)",
        source_sha256=hashlib.sha256(matrix_path.read_bytes()).hexdigest(),
    )
    samples = [
        MockSample(
            patient_id=f"P-{sample_id}",
            barcode=sample_id,
            stage="Stage I" if sample_id.startswith("A") else "Stage II",
        )
        for sample_id in sample_ids
    ]
    artifact_root = tmp_path / "artifacts"
    fake_settings = SimpleNamespace(
        artifact_dir=artifact_root,
        tcga_data_dir=tmp_path / "tcga",
    )

    class FakeSession:
        def get(self, model, key):
            if model is Cohort and key == "TCGA-TEST":
                return SimpleNamespace(id=key)
            return None

    def fake_receipt(_settings, *, subject_id, subject_type, **_kwargs):
        receipt_path = (
            artifact_root
            / "expression_comparisons"
            / subject_id
            / "attestation_receipt.json"
        )
        receipt_path.write_text(
            json.dumps(
                {
                    "subject": {"type": subject_type, "id": subject_id},
                    "audit_report": {},
                }
            ),
            encoding="utf-8",
        )
        return {"path": str(receipt_path)}

    monkeypatch.setattr(main_module, "settings", fake_settings)
    monkeypatch.setattr(
        main_module,
        "resolve_expression_matrix",
        lambda *_args, **_kwargs: matrix,
    )
    monkeypatch.setattr(
        main_module,
        "dataset_samples",
        lambda *_args, **_kwargs: samples,
    )
    monkeypatch.setattr(
        main_module,
        "resolve_gene_symbol",
        lambda *_args, **_kwargs: {
            "resolved": _args[-1].strip().upper(),
            "warnings": [],
        },
    )
    monkeypatch.setattr(
        main_module,
        "current_data_version",
        lambda _db: {"fixture": {"manifest_hash": "fixture-hash"}},
    )
    monkeypatch.setattr(main_module, "write_attestation_receipt", fake_receipt)
    request = ExpressionComparisonRequest(
        cohort="TCGA-TEST",
        genes=["UP", "DOWN"],
        grouping=clinical_grouping(),
        heatmap_max_samples=20,
    )
    result = main_module._create_expression_comparison_unlocked(
        request,
        FakeSession(),
    )
    result_dir = (
        artifact_root / "expression_comparisons" / result.comparison_id
    )
    assert result.status == "completed"
    assert result.summary["genes_analyzed"] == 2
    assert result.summary["patients"] == 10
    assert result.statistics[0]["mean_difference_b_minus_a"] > 0
    assert result.audit["report_type"] == "expression_comparison_audit"
    assert result_dir.is_dir()

    def expression_derived_clinical_assignments(
        selected_samples,
        grouping,
        **_kwargs,
    ):
        assignments = {
            sample.barcode: "a" if sample.stage == "Stage I" else "b"
            for sample in selected_samples
        }
        return (
            assignments,
            {
                "source": "clinical",
                "variable": "paper_BRCA_Subtype_PAM50",
                "variable_label": "PAM50 intrinsic subtype",
                "variable_source": "TCGA publication annotation",
                "expression_derived_grouping": True,
                "contrast": "group_b_minus_group_a",
                "group_a_label": grouping.group_a_label,
                "group_b_label": grouping.group_b_label,
                "group_a_definition": "Luminal A",
                "group_b_definition": "Basal-like",
            },
            [],
            {},
        )

    monkeypatch.setattr(
        main_module,
        "_resolved_clinical_group_assignments",
        expression_derived_clinical_assignments,
    )
    derived_result = main_module._create_expression_comparison_unlocked(
        request,
        FakeSession(),
    )
    inference = derived_result.grouping["comparison_inference"]
    assert inference["expression_derived_clinical_grouping"] is True
    assert inference["all_targets_descriptive_only"] is True
    assert inference["descriptive_only_genes"] == ["UP", "DOWN"]
    assert derived_result.summary["genes_at_fdr_welch"] == 0
    assert derived_result.summary["genes_at_fdr_mann_whitney"] == 0
    for statistic in derived_result.statistics:
        assert statistic["inferential_status"] == "descriptive_only"
        assert statistic["welch_t"]["p_value"] is None
        assert statistic["welch_t"]["fdr"] is None
        assert statistic["mann_whitney"]["p_value"] is None
        assert statistic["mann_whitney"]["fdr"] is None
        assert statistic["significant_at_fdr"] is False
    assert any(
        "clinical grouping itself was derived from transcriptomic expression"
        in warning
        for warning in derived_result.warnings
    )

    monkeypatch.setattr(
        main_module,
        "_public_expression_comparison_job",
        lambda *_args, **_kwargs: SimpleNamespace(),
    )
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [],
            "client": ("127.0.0.1", 1234),
            "server": ("testserver", 80),
            "scheme": "http",
            "query_string": b"",
        }
    )
    svg_response = main_module.download_public_expression_comparison_artifact(
        result.comparison_id,
        "violin_svg",
        request,
        FakeSession(),
    )
    assert Path(svg_response.path).name == "violin_plot.svg"
    zip_response = main_module.download_public_expression_comparison_artifact(
        result.comparison_id,
        "zip",
        request,
        FakeSession(),
    )
    with zipfile.ZipFile(io.BytesIO(zip_response.body)) as archive:
        assert {
            "expression_values.csv",
            "sample_groups.csv",
            "gene_statistics.csv",
            "violin_plot.svg",
            "boxplot.svg",
            "heatmap.svg",
            "result.json",
            "input.json",
            "methodology.txt",
            "audit_report.json",
            "attestation_receipt.json",
        } == set(archive.namelist())


def test_expression_comparison_openapi_routes_and_operation_ids() -> None:
    paths = main_module.app.openapi()["paths"]
    collection = paths["/api/v1/analyses/expression-comparisons"]
    result = paths[
        "/api/v1/analyses/expression-comparisons/{comparison_id}"
    ]
    assert collection["post"]["operationId"] == "submitExpressionComparison"
    assert result["get"]["operationId"] == "getExpressionComparison"
