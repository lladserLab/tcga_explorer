import csv
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.main import latest_data_manifest
from app.models import DataManifest
from app.multiverse import expand_multiverse_request, summarize_multiverse
from app.repository import importer
from app.repository.adapters.cbioportal import apply_expression_transform
from app.repository.discovery import discover_cbioportal_candidates
from app.repository.storage import (
    read_float32le_row,
    safe_bundle_path,
    sha256_file,
    write_float32le_matrix,
)
from app.schemas import (
    AnalysisRequest,
    MultiverseAnalysisOut,
    MultiverseAnalysisRequest,
    SignatureGene,
)
from app.survival import (
    ClinicalOutcome,
    filter_sample_candidates,
    select_expression_complete_samples,
)


class EmptyFilters:
    sample_types: list[str] = []
    stages: list[str] = []
    grades: list[str] = []
    genders: list[str] = []
    races: list[str] = []
    age_min = None
    age_max = None
    max_time_days = None


class ExternalSample:
    def __init__(self, patient_id: str, sample_id: str, rank: int):
        self.patient_id = patient_id
        self.barcode = sample_id
        self.selection_rank = rank
        self.sample_type = "Tumor"
        self.stage = None
        self.grade = None
        self.gender = None
        self.race = None
        self.age_at_index = None
        self.os_time_days = None
        self.os_event = None


def write_tsv(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)


def build_minimal_bundle(root: Path) -> Path:
    derived = root / "derived"
    patient_ids = [f"P{index:02d}" for index in range(10)]
    sample_ids = [f"S{index:02d}" for index in range(10)]
    write_tsv(
        derived / "patients.tsv",
        ["patient_id"],
        [{"patient_id": patient_id} for patient_id in patient_ids],
    )
    write_tsv(
        derived / "samples.tsv",
        ["sample_id", "patient_id"],
        [
            {"sample_id": sample_id, "patient_id": patient_id}
            for sample_id, patient_id in zip(
                sample_ids, patient_ids, strict=True
            )
        ],
    )
    write_tsv(
        derived / "endpoint_os.tsv",
        ["patient_id", "time_days", "event"],
        [
            {
                "patient_id": patient_id,
                "time_days": 100 + index,
                "event": int(index < 5),
            }
            for index, patient_id in enumerate(patient_ids)
        ],
    )
    write_tsv(
        derived / "genes.tsv",
        ["gene_symbol", "original_gene_id"],
        [
            {"gene_symbol": "GENEA", "original_gene_id": "1"},
            {"gene_symbol": "GENEB", "original_gene_id": "2"},
        ],
    )
    write_float32le_matrix(
        derived / "expression.float32le.bin",
        [
            [float(index) for index in range(10)],
            [float(index + 10) for index in range(10)],
        ],
    )
    metadata = {
        "dtype": "float32_le",
        "layout": "row_major_gene_by_sample",
        "gene_count": 2,
        "sample_count": 10,
        "sample_ids": sample_ids,
    }
    (derived / "expression.metadata.json").write_text(
        json.dumps(metadata),
        encoding="utf-8",
    )
    relative_files = [
        "derived/patients.tsv",
        "derived/samples.tsv",
        "derived/endpoint_os.tsv",
        "derived/genes.tsv",
        "derived/expression.float32le.bin",
        "derived/expression.metadata.json",
    ]
    manifest = {
        "schema_version": importer.BUNDLE_SCHEMA_VERSION,
        "dataset": {
            "id": "fixture-study",
            "cancer_code": "SKCM",
            "name": "Fixture study",
            "source_provider": "fixture",
            "source_accession": "FIXTURE",
            "source_url": "https://example.test/fixture",
            "assay": "bulk_rna_seq",
            "independence_status": "verified_external",
        },
        "release": {
            "id": "fixture-release-v1",
            "version": "v1",
            "source_snapshot": "fixture-sha",
        },
        "files": {
            "patients": "derived/patients.tsv",
            "samples": "derived/samples.tsv",
        },
        "endpoints": [
            {
                "endpoint_id": "OS",
                "label": "Overall survival",
                "values_file": "derived/endpoint_os.tsv",
            }
        ],
        "expression_layers": [
            {
                "layer_id": "log2_rpkm",
                "label": "log2(RPKM + 1)",
                "source_unit": "RPKM",
                "analysis_unit": "log2(RPKM + 1)",
                "transform": "log2p",
                "is_default": True,
                "downloadable": True,
                "genes_file": "derived/genes.tsv",
                "matrix_file": "derived/expression.float32le.bin",
                "metadata_file": "derived/expression.metadata.json",
            }
        ],
        "checksums": {
            relative: sha256_file(root / relative)
            for relative in relative_files
        },
    }
    (root / "manifest.json").write_text(
        json.dumps(manifest),
        encoding="utf-8",
    )
    return root


def test_repository_matrix_round_trip_and_safe_paths(tmp_path):
    matrix = tmp_path / "matrix.bin"
    write_float32le_matrix(matrix, [[1.25, 2.5], [3.75, 4.0]])

    assert read_float32le_row(
        matrix,
        row_number=1,
        sample_ids=["S1", "S2"],
    ) == pytest.approx({"S1": 3.75, "S2": 4.0})
    assert safe_bundle_path(tmp_path, "derived/matrix.bin").parent == (
        tmp_path / "derived"
    )
    with pytest.raises(ValueError, match="escapes"):
        safe_bundle_path(tmp_path, "../outside.bin")


def test_bundle_validation_enforces_checksums_and_qc(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(importer, "MIN_GENES", 2)
    bundle = build_minimal_bundle(tmp_path)

    validation = importer.validate_bundle(bundle)
    assert validation["qc"]["status"] == "passed"
    assert validation["qc"]["endpoints"]["OS"] == {
        "patients": 10,
        "events": 5,
        "available": True,
    }

    matrix = bundle / "derived/expression.float32le.bin"
    matrix.write_bytes(matrix.read_bytes()[:-4])
    invalid = importer.validate_bundle(bundle)
    assert invalid["qc"]["status"] == "failed"
    assert any(
        "Checksum mismatch" in error for error in invalid["qc"]["errors"]
    )
    assert any(
        "matrix size" in error for error in invalid["qc"]["errors"]
    )


def test_external_analysis_contract_requires_pinned_release():
    with pytest.raises(
        ValidationError,
        match="dataset_id and dataset_release_id",
    ):
        AnalysisRequest(
            cohort="TCGA-SKCM",
            dataset_id="fixture-study",
            gene_symbol="TMEM176B",
        )

    request = AnalysisRequest(
        cohort="TCGA-SKCM",
        dataset_id="fixture-study",
        dataset_release_id="fixture-release-v1",
        expression_layer_id="log2_rpkm",
        gene_symbol="TMEM176B",
    )
    assert request.dataset_release_id == "fixture-release-v1"


def test_multiverse_propagates_external_release_to_every_cell():
    request = MultiverseAnalysisRequest(
        cohort="TCGA-SKCM",
        dataset_id="fixture-study",
        dataset_release_id="fixture-release-v1",
        expression_layer_id="log2_rpkm",
        genes=[SignatureGene(gene_symbol="TMEM176B")],
        endpoints=["OS"],
        scoring_methods=["single"],
        cutpoint_methods=["median", "upper_quartile"],
    )
    specifications = expand_multiverse_request(request)
    assert {
        row["analysis_request"].dataset_release_id
        for row in specifications
    } == {"fixture-release-v1"}

    result = summarize_multiverse(
        session_id="mv_external_fixture",
        request=request,
        specifications=specifications,
        completed_items=[],
        pipeline_version="test",
        data_version={
            "external_repository": {
                "dataset_id": "fixture-study",
                "release_id": "fixture-release-v1",
            }
        },
    )
    validated = MultiverseAnalysisOut(**result)
    assert validated.dataset_id == "fixture-study"
    assert validated.dataset_release_id == "fixture-release-v1"
    assert result["audit"]["data_version"]["external_repository"][
        "release_id"
    ] == "fixture-release-v1"


def test_external_sample_selection_uses_release_rank():
    preferred = ExternalSample("P1", "S-Z", 0)
    fallback = ExternalSample("P1", "S-A", 1)
    second_patient = ExternalSample("P2", "S-2", 0)
    candidates, warnings, summary = filter_sample_candidates(
        [fallback, preferred, second_patient],
        EmptyFilters(),
        endpoint_by_patient={
            "P1": ClinicalOutcome(
                endpoint="OS",
                time_days=100,
                event=1,
                source="external:fixture",
            ),
            "P2": ClinicalOutcome(
                endpoint="OS",
                time_days=200,
                event=0,
                source="external:fixture",
            ),
        },
        selection_rule="external_curated",
        endpoint_source="external:fixture",
    )
    retained, warnings, summary = select_expression_complete_samples(
        candidates,
        {preferred.barcode, fallback.barcode, second_patient.barcode},
        warnings=warnings,
        summary=summary,
    )

    assert {row.patient_id: row.barcode for row in retained} == {
        "P1": "S-Z",
        "P2": "S-2",
    }
    assert summary["selection_rule_kind"] == "external_curated"
    assert summary["priority_order"] == ["selection_rank", "sample_id"]


def test_expression_transform_is_explicit_and_does_not_double_log():
    assert apply_expression_transform([0.0, 3.0], "log2p") == [0.0, 2.0]
    provided = [1.25, -0.5]
    assert apply_expression_transform(provided, "identity") is provided
    with pytest.raises(ValueError, match="Unsupported"):
        apply_expression_transform([1.0], "inferred")


def test_cbioportal_discovery_keeps_screening_separate_from_promotion(
    tmp_path,
):
    (tmp_path / "studies").mkdir()
    (tmp_path / "cancer_types.json").write_text(
        json.dumps(
            {
                "cancer_types": [
                    {
                        "code": "BLCA",
                        "tcga_cohort": "TCGA-BLCA",
                        "name": "Bladder cancer",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "coverage.json").write_text(
        json.dumps(
            {
                "cancers": [
                    {
                        "code": "BLCA",
                        "status": "available",
                        "candidates": [
                            {
                                "accession": "blca_external",
                                "review_status": "promoted",
                            }
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "studies" / "blca.json").write_text(
        json.dumps(
            {
                "dataset": {
                    "id": "fixture-blca",
                    "source_accession": "blca_external",
                }
            }
        ),
        encoding="utf-8",
    )

    def requester(url, **_kwargs):
        if "/studies?" in url:
            return [
                {
                    "studyId": "blca_external",
                    "cancerTypeId": "blca",
                    "name": "Independent bladder cohort",
                    "description": "Bulk RNA cohort",
                    "allSampleCount": 20,
                    "mrnaRnaSeqSampleCount": 20,
                },
                {
                    "studyId": "blca_tcga",
                    "cancerTypeId": "blca",
                    "name": "TCGA",
                    "description": "TCGA cohort",
                    "allSampleCount": 400,
                    "mrnaRnaSeqSampleCount": 400,
                },
            ]
        if "/molecular-profiles?" in url:
            return [
                {
                    "studyId": "blca_external",
                    "molecularProfileId": "blca_external_rna_seq_mrna",
                    "molecularAlterationType": "MRNA_EXPRESSION",
                    "datatype": "CONTINUOUS",
                    "name": "mRNA expression (RPKM)",
                }
            ]
        if url.endswith("/blca_external/clinical-attributes"):
            return [
                {
                    "clinicalAttributeId": "OS_STATUS",
                    "patientAttribute": True,
                },
                {
                    "clinicalAttributeId": "OS_MONTHS",
                    "patientAttribute": True,
                },
            ]
        raise AssertionError(url)

    result = discover_cbioportal_candidates(
        tmp_path,
        requester=requester,
    )
    assert result["summary"]["candidate_studies"] == 1
    candidate = result["cancers"][0]["candidates"][0]
    assert candidate["study_id"] == "blca_external"
    assert candidate["review_status"] == "promoted"
    assert candidate["endpoint_pairs"][0]["endpoint"] == "OS"


def test_external_manifests_do_not_replace_tcga_summary_manifest():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    with factory() as db:
        db.add_all(
            [
                DataManifest(
                    source_id="tcga_cdr",
                    status="ready",
                    manifest_hash="tcga-hash",
                    created_at=now,
                ),
                DataManifest(
                    source_id="external:fixture",
                    status="ready",
                    manifest_hash="external-hash",
                    created_at=now + timedelta(seconds=1),
                ),
            ]
        )
        db.commit()
        assert latest_data_manifest(db).manifest_hash == "tcga-hash"
