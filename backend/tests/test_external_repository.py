import csv
from datetime import datetime, timedelta, timezone
import gzip
import json
from pathlib import Path
import zipfile
import xml.etree.ElementTree as ET

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.main import latest_data_manifest
from app.models import (
    CancerType,
    DataManifest,
    RepositoryDataset,
    RepositoryEndpointDefinition,
)
from app.multiverse import expand_multiverse_request, summarize_multiverse
from app.repository import importer
from app.repository.adapters.cbioportal import (
    apply_expression_transform,
    build_recipe_metadata,
    duplicated_source_feature_symbols,
    fetch_provided_ensembl_hugo_mapping,
    merge_gdc_survival_into_patients,
    read_expression_header,
    resolve_source_file_spec,
    sample_passes_eligibility,
    sample_selection_rank,
    source_feature_ids_match,
)
from app.repository.adapters.geo import parse_geo_date, parse_geo_family_soft
from app.repository.adapters.gdc import (
    gdc_case_passes_eligibility,
    gdc_star_tpm_iterator,
    materialize_gdc_star_tpm_matrix,
    select_gdc_expression_files,
)
from app.repository.adapters.icgc import (
    parse_object_listing,
    resolve_icgc_os,
    select_expression_analysis,
)
from app.repository.adapters.pmc import (
    detect_creative_commons_license,
    materialize_geo_rpkm_matrix,
    normalize_curated_records,
    parse_gencode_gene_map,
    publication_expression_sample_ids,
    read_xlsx_sheet,
    selected_sample_indexes,
)
from app.repository.discovery import (
    _rna_seq_sample_count,
    discover_cbioportal_candidates,
)
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
    source = root / "source"
    source.mkdir(parents=True)
    (source / "LICENSE").write_text("Fixture license\n", encoding="utf-8")
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
        [
            "gene_symbol",
            "original_gene_id",
            "row_number",
            "mapping_source",
        ],
        [
            {
                "gene_symbol": "GENEA",
                "original_gene_id": "1",
                "row_number": 0,
                "mapping_source": "fixture",
            },
            {
                "gene_symbol": "GENEB",
                "original_gene_id": "2",
                "row_number": 1,
                "mapping_source": "fixture",
            },
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
            "license_id": "LicenseRef-Fixture",
            "license_url": "https://example.test/license",
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
                "time_origin": "Diagnosis",
                "event_definition": "Death from any cause",
                "source_time_column": "OS_DAYS",
                "source_event_column": "OS_STATUS",
                "source_time_unit": "days",
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
        "source_files": {
            "license": "source/LICENSE",
        },
        "checksums": {
            relative: sha256_file(root / relative)
            for relative in [*relative_files, "source/LICENSE"]
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
        "censored": 5,
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


def test_bundle_validation_rejects_event_only_survival_follow_up(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(importer, "MIN_GENES", 2)
    bundle = build_minimal_bundle(tmp_path)
    endpoint_path = bundle / "derived/endpoint_os.tsv"
    rows = importer.read_tsv(endpoint_path)
    write_tsv(
        endpoint_path,
        ["patient_id", "time_days", "event"],
        [{**row, "event": 1} for row in rows],
    )
    manifest_path = bundle / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["checksums"]["derived/endpoint_os.tsv"] = sha256_file(endpoint_path)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    validation = importer.validate_bundle(bundle)

    assert validation["qc"]["status"] == "failed"
    assert validation["qc"]["endpoints"]["OS"] == {
        "patients": 10,
        "events": 10,
        "censored": 0,
        "available": False,
    }
    assert any(
        "5 censored observations" in error
        for error in validation["qc"]["errors"]
    )


def test_bundle_validation_rejects_expression_fields_that_exceed_db_limits(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(importer, "MIN_GENES", 2)
    bundle = build_minimal_bundle(tmp_path)
    manifest_path = bundle / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["expression_layers"][0]["source_unit"] = "x" * 65
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    validation = importer.validate_bundle(bundle)

    assert validation["qc"]["status"] == "failed"
    assert any(
        "source_unit exceeds 64 characters" in error
        for error in validation["qc"]["errors"]
    )


def test_active_release_revalidation_disables_newly_ineligible_dataset(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(importer, "MIN_GENES", 2)
    bundle = build_minimal_bundle(tmp_path / "bundle")
    repository_root = tmp_path / "repository"
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as db:
        db.add(
            CancerType(
                code="SKCM",
                tcga_cohort="TCGA-SKCM",
                name="Skin Cutaneous Melanoma",
                sort_order=0,
                coverage_status="available",
            )
        )
        db.commit()
        importer.promote_bundle(db, bundle, repository_root)
        assert db.get(RepositoryDataset, "fixture-study").status == "available"

        monkeypatch.setattr(importer, "MIN_CENSORED", 6)
        result = importer.revalidate_active_releases(db)

        dataset = db.get(RepositoryDataset, "fixture-study")
        endpoint = db.scalars(
            select(RepositoryEndpointDefinition)
        ).one()
        assert result["available"] == 0
        assert result["qc_failed"] == 1
        assert dataset.status == "qc_failed"
        assert endpoint.available is False
        assert endpoint.reason == (
            "Requires at least 6 censored observations."
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


def test_source_feature_match_only_normalizes_hugo_symbol_case():
    assert source_feature_ids_match("C2orf15", "C2ORF15", "hugo_symbol")
    assert not source_feature_ids_match("PARK2", "PRKN", "hugo_symbol")
    assert not source_feature_ids_match("101", "0101", "entrez_gene_id")


def test_importer_treats_cbioportal_missing_tokens_as_null():
    assert importer._optional_float("[Not Available]") is None
    assert importer._optional_float("[Not Applicable]") is None
    assert importer._optional_float("62.5") == 62.5


def test_build_recipe_changes_with_spec_source_or_adapter():
    baseline = build_recipe_metadata(
        {"dataset": {"id": "example"}},
        "source-a",
        "adapter-a",
    )
    assert baseline == build_recipe_metadata(
        {"dataset": {"id": "example"}},
        "source-a",
        "adapter-a",
    )
    assert baseline["build_recipe_sha256"] != build_recipe_metadata(
        {"dataset": {"id": "changed"}},
        "source-a",
        "adapter-a",
    )["build_recipe_sha256"]
    assert baseline["build_recipe_sha256"] != build_recipe_metadata(
        {"dataset": {"id": "example"}},
        "source-b",
        "adapter-a",
    )["build_recipe_sha256"]
    assert baseline["build_recipe_sha256"] != build_recipe_metadata(
        {"dataset": {"id": "example"}},
        "source-a",
        "adapter-b",
    )["build_recipe_sha256"]
    assert baseline["build_recipe_sha256"] != build_recipe_metadata(
        {"dataset": {"id": "example"}},
        "source-a",
        "adapter-a",
        adapter_version="cbioportal_api_v1",
    )["build_recipe_sha256"]


def test_gdc_survival_merge_restores_censored_follow_up():
    patients = {
        "P-DEAD": {"OS_STATUS": "1:DECEASED"},
        "P-ALIVE": {"OS_STATUS": "0:LIVING"},
        "P-UPDATED": {"OS_STATUS": "0:LIVING"},
        "P-MISSING": {"OS_STATUS": "0:LIVING"},
    }
    payload = {
        "results": [
            {
                "donors": [
                    {
                        "submitter_id": "P-DEAD",
                        "project_id": "CPTAC-3",
                        "id": "case-dead",
                        "time": 100,
                        "censored": False,
                    },
                    {
                        "submitter_id": "P-ALIVE",
                        "project_id": "CPTAC-3",
                        "id": "case-alive",
                        "time": 250.5,
                        "censored": True,
                    },
                    {
                        "submitter_id": "P-UPDATED",
                        "project_id": "CPTAC-3",
                        "id": "case-updated",
                        "time": 300,
                        "censored": False,
                    },
                ]
            }
        ]
    }

    summary = merge_gdc_survival_into_patients(
        patients,
        set(patients),
        payload,
        project_id="CPTAC-3",
    )

    assert summary["matched_patients"] == 3
    assert summary["events"] == 2
    assert summary["censored"] == 1
    assert summary["missing_patients"] == 1
    assert summary["source_status_updates"] == 1
    assert patients["P-DEAD"]["GDC_OS_STATUS"] == "1:DECEASED"
    assert patients["P-ALIVE"]["GDC_OS_STATUS"] == "0:CENSORED"
    assert patients["P-ALIVE"]["GDC_OS_DAYS"] == "250.5"


def test_gdc_file_selection_is_patient_level_and_deterministic():
    def hit(
        patient: str,
        sample: str,
        aliquot: str,
        file_id: str,
        sample_type: str = "Primary Tumor",
    ):
        return {
            "file_id": file_id,
            "file_name": f"{file_id}.tsv",
            "file_size": 100,
            "md5sum": "a" * 32,
            "cases": [
                {
                    "case_id": f"case-{patient}",
                    "submitter_id": patient,
                    "samples": [
                        {
                            "sample_id": f"uuid-{sample}",
                            "submitter_id": sample,
                            "sample_type": sample_type,
                            "tissue_type": "Tumor",
                            "portions": [
                                {
                                    "analytes": [
                                        {
                                            "aliquots": [
                                                {
                                                    "aliquot_id": (
                                                        f"uuid-{aliquot}"
                                                    ),
                                                    "submitter_id": aliquot,
                                                }
                                            ]
                                        }
                                    ]
                                }
                            ],
                        }
                    ],
                }
            ],
        }

    selected, summary = select_gdc_expression_files(
        [
            hit("P1", "P1-01B", "P1-01B-01R", "file-c"),
            hit("P1", "P1-01A", "P1-01A-02R", "file-b"),
            hit("P1", "P1-01A", "P1-01A-01R", "file-a"),
            hit("P2", "P2-06A", "P2-06A-01R", "file-d", "Metastatic"),
            hit("P3", "P3-10A", "P3-10A-01R", "file-e", "Blood Derived Normal"),
        ],
        {"P1", "P2", "P3"},
        sample_type_priority=["Primary Tumor", "Metastatic"],
    )

    assert [row["file_id"] for row in selected] == ["file-a", "file-d"]
    assert summary["discarded_duplicate_file_candidates"] == 2
    assert summary["excluded_sample_types"] == {"Blood Derived Normal": 1}


def test_gdc_file_link_uses_associated_biospecimen_entity():
    hit = {
        "file_id": "file-1",
        "file_name": "file-1.tsv",
        "file_size": 100,
        "md5sum": "a" * 32,
        "associated_entities": [
            {
                "entity_id": "aliquot-b",
                "entity_type": "aliquot",
            }
        ],
        "cases": [
            {
                "case_id": "case-1",
                "submitter_id": "P1",
                "samples": [
                    {
                        "sample_id": "sample-a",
                        "submitter_id": "P1-01A",
                        "sample_type": "Primary Tumor",
                        "portions": [
                            {
                                "analytes": [
                                    {
                                        "aliquots": [
                                            {
                                                "aliquot_id": "aliquot-a",
                                                "submitter_id": "A",
                                            }
                                        ]
                                    }
                                ]
                            }
                        ],
                    },
                    {
                        "sample_id": "sample-b",
                        "submitter_id": "P1-01B",
                        "sample_type": "Primary Tumor",
                        "portions": [
                            {
                                "analytes": [
                                    {
                                        "aliquots": [
                                            {
                                                "aliquot_id": "aliquot-b",
                                                "submitter_id": "B",
                                            }
                                        ]
                                    }
                                ]
                            }
                        ],
                    },
                ],
            }
        ],
    }

    selected, _ = select_gdc_expression_files(
        [hit],
        {"P1"},
        sample_type_priority=["Primary Tumor"],
    )

    assert selected[0]["sample_id"] == "P1-01B"
    assert selected[0]["aliquot_id"] == "aliquot-b"
    assert selected[0]["linked_sample_candidates"] == 1


def test_gdc_case_eligibility_uses_prespecified_clinical_fields():
    case = {
        "primary_site": "Brain",
        "diagnoses": [
            {
                "diagnosis_id": "secondary",
                "diagnosis_is_primary_disease": False,
                "primary_diagnosis": "Astrocytoma, NOS",
            },
            {
                "diagnosis_id": "primary",
                "diagnosis_is_primary_disease": True,
                "primary_diagnosis": "Glioblastoma",
            },
        ],
        "demographic": {"sex_at_birth": "female"},
    }
    rules = [
        {
            "field": "case.primary_site",
            "include": ["Brain"],
            "required": True,
        },
        {
            "field": "diagnosis.primary_diagnosis",
            "include": ["Glioblastoma"],
            "required": True,
        },
    ]

    assert gdc_case_passes_eligibility(case, rules)
    assert not gdc_case_passes_eligibility(
        case,
        [
            *rules[:1],
            {
                "field": "diagnosis.primary_diagnosis",
                "include": ["Oligodendroglioma, NOS"],
            },
        ],
    )


def test_gdc_star_counts_are_materialized_in_shared_gene_order(tmp_path):
    def star(path: Path, sample_offset: int) -> None:
        path.write_text(
            "# gene-model: GENCODE v36\n"
            "gene_id\tgene_name\tgene_type\tunstranded\tstranded_first\t"
            "stranded_second\ttpm_unstranded\tfpkm_unstranded\t"
            "fpkm_uq_unstranded\n"
            "N_unmapped\t\t\t1\t1\t1\t\t\t\n"
            f"ENSG000001.1\tGENEA\tprotein_coding\t1\t1\t1\t"
            f"{1 + sample_offset}.0\t0\t0\n"
            f"ENSG000002.2\tGENEB\tprotein_coding\t1\t1\t1\t"
            f"{2 + sample_offset}.0\t0\t0\n",
            encoding="utf-8",
        )

    first = tmp_path / "first.tsv"
    second = tmp_path / "second.tsv"
    star(first, 0)
    star(second, 10)
    records = [
        {"file_id": "F1", "sample_id": "S1"},
        {"file_id": "F2", "sample_id": "S2"},
    ]
    output = tmp_path / "matrix.tsv"

    # Lower the production gene floor only by exercising the shard primitive
    # through a padded fixture.
    iterator, model = gdc_star_tpm_iterator(first)
    assert model == "GENCODE v36"
    assert list(iterator) == [
        ("ENSG000001.1", "GENEA", "1"),
        ("ENSG000002.2", "GENEB", "2"),
    ]

    def large_star(path: Path, sample_offset: int) -> None:
        rows = [
            "# gene-model: GENCODE v36",
            (
                "gene_id\tgene_name\tgene_type\tunstranded\t"
                "stranded_first\tstranded_second\ttpm_unstranded\t"
                "fpkm_unstranded\tfpkm_uq_unstranded"
            ),
        ]
        rows.extend(
            f"ENSG{index:011d}.1\tGENE{index}\tprotein_coding\t1\t1\t1\t"
            f"{index + sample_offset}.0\t0\t0"
            for index in range(1, 10_001)
        )
        path.write_text("\n".join(rows) + "\n", encoding="utf-8")

    large_star(first, 0)
    large_star(second, 10)
    summary = materialize_gdc_star_tpm_matrix(
        records,
        {"F1": first, "F2": second},
        output,
        shard_size=2,
    )
    with output.open(encoding="utf-8") as handle:
        reader = csv.reader(handle, delimiter="\t")
        assert next(reader) == [
            "Ensembl_Gene_Id|Hugo_Symbol",
            "S1",
            "S2",
        ]
        assert next(reader) == [
            "ENSG00000000001.1|GENE1",
            "1",
            "11",
        ]
    assert summary["materialized_genes"] == 10_000
    assert summary["gene_models"] == ["GENCODE v36"]


def test_gdc_embedded_ensembl_hugo_mapping_is_offline_and_explicit():
    mapping = fetch_provided_ensembl_hugo_mapping(
        [
            "ENSG00000141510.18|TP53",
            "ENSG00000146648.22|EGFR",
            "N_unmapped|",
        ]
    )
    assert mapping == {
        "ENSG00000141510.18|TP53": "TP53",
        "ENSG00000146648.22|EGFR": "EGFR",
    }


def test_geo_soft_and_compressed_csv_are_parsed_without_expansion(
    tmp_path,
):
    soft = tmp_path / "family.soft.gz"
    with gzip.open(soft, "wt", encoding="utf-8") as handle:
        handle.write(
            "^SERIES = GSE1\n"
            "!Series_title = Fixture series\n"
            "!Series_last_update_date = Jan 02 2024\n"
            "^SAMPLE = GSM1\n"
            "!Sample_title = F1\n"
            "!Sample_geo_accession = GSM1\n"
            "!Sample_characteristics_ch1 = overall survival days: 100\n"
            "!Sample_characteristics_ch1 = overall survival event: 0\n"
            "^SAMPLE = GSM2\n"
            "!Sample_title = F1repl\n"
            "!Sample_geo_accession = GSM2\n"
            "!Sample_characteristics_ch1 = overall survival days: 100\n"
            "!Sample_characteristics_ch1 = overall survival event: 0\n"
        )
    series, samples = parse_geo_family_soft(soft)
    assert series["title"] == "Fixture series"
    assert [sample["title"] for sample in samples] == ["F1", "F1repl"]
    assert samples[0]["characteristics"]["overall survival days"] == "100"

    expression = tmp_path / "expression.csv.gz"
    with gzip.open(
        expression, "wt", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.writer(handle)
        writer.writerow(["", "F1", "F1repl"])
        writer.writerow(["TP53", 1.5, 1.6])
    assert read_expression_header(expression) == ["", "F1", "F1repl"]
    assert duplicated_source_feature_symbols(
        ["LRRc37A", "LRRC37A", "TP53"],
        "provided_hugo_symbol",
    ) == {"LRRC37A"}
    assert parse_geo_date(series["last_update_date"]) == (
        "2024-01-02T00:00:00Z"
    )
    assert "retrieved_at" not in series


def test_icgc_listing_endpoint_and_analysis_selection_are_deterministic():
    listing = ET.fromstring(
        """
        <ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">
          <Contents>
            <Key>release_28/data/LIRI-JP/DO2/exp_seq/file.tsv.gz</Key>
            <LastModified>2019-11-26T00:00:00.000Z</LastModified>
            <ETag>"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"</ETag>
            <Size>20</Size>
          </Contents>
          <Contents>
            <Key>release_28/data/LIRI-JP/DO1/exp_seq/file.tsv.gz</Key>
            <LastModified>2019-11-25T00:00:00.000Z</LastModified>
            <ETag>"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"</ETag>
            <Size>10</Size>
          </Contents>
          <IsTruncated>true</IsTruncated>
          <NextContinuationToken>page-2</NextContinuationToken>
        </ListBucketResult>
        """
    )
    records, truncated, token = parse_object_listing(listing)
    assert records == [
        {
            "key": "release_28/data/LIRI-JP/DO2/exp_seq/file.tsv.gz",
            "etag": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
            "size": 20,
            "last_modified": "2019-11-26T00:00:00.000Z",
        },
        {
            "key": "release_28/data/LIRI-JP/DO1/exp_seq/file.tsv.gz",
            "etag": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "size": 10,
            "last_modified": "2019-11-25T00:00:00.000Z",
        },
    ]
    assert truncated is True
    assert token == "page-2"
    assert all("retrieved_at" not in record for record in records)

    assert resolve_icgc_os(
        {
            "donor_vital_status": "deceased",
            "donor_survival_time": "730.5",
            "donor_interval_of_last_followup": "700",
        }
    ) == {
        "time_days": 730.5,
        "event": 1,
        "time_source": "donor_survival_time",
    }
    assert resolve_icgc_os(
        {
            "donor_vital_status": "alive",
            "donor_survival_time": "",
            "donor_interval_of_last_followup": "900",
        }
    ) == {
        "time_days": 900.0,
        "event": 0,
        "time_source": "donor_interval_of_last_followup",
    }

    primary = {
        "icgc_sample_id": "SA-PRIMARY",
        "icgc_specimen_id": "SP-PRIMARY",
        "analysis_id": "AN-Z",
        "gene_model": "RefSeq",
        "normalization_algorithm": "FKPM",
        "gene_rows": 13_405,
    }
    later_analysis_id = {
        **primary,
        "analysis_id": "AN-A",
    }
    metastatic = {
        **primary,
        "icgc_sample_id": "SA-MET",
        "icgc_specimen_id": "SP-MET",
        "analysis_id": "AN-0",
    }
    selected = select_expression_analysis(
        [primary, metastatic, later_analysis_id],
        {
            "SA-PRIMARY": {
                "icgc_specimen_id": "SP-PRIMARY",
                "submitted_sample_id": "SUB-PRIMARY",
            },
            "SA-MET": {
                "icgc_specimen_id": "SP-MET",
                "submitted_sample_id": "SUB-MET",
            },
        },
        {
            "SP-PRIMARY": {
                "specimen_type": "Primary tumour - solid tissue",
            },
            "SP-MET": {
                "specimen_type": (
                    "Metastatic tumour - metastasis to distant location"
                ),
            },
        },
        specimen_priority=(
            "Primary tumour - solid tissue",
            "Metastatic tumour - metastasis to distant location",
        ),
        required_gene_model="RefSeq",
        required_normalization_algorithm="FKPM",
    )
    assert selected is later_analysis_id


def test_publication_adapter_reads_named_xlsx_sheet_and_header_row(
    tmp_path,
):
    workbook = tmp_path / "clinical.xlsx"
    spreadsheet_ns = (
        "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    )
    relationship_ns = (
        "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    )
    package_relationship_ns = (
        "http://schemas.openxmlformats.org/package/2006/relationships"
    )
    with zipfile.ZipFile(workbook, "w") as archive:
        archive.writestr(
            "xl/sharedStrings.xml",
            (
                f'<sst xmlns="{spreadsheet_ns}">'
                "<si><t>Sample ID</t></si>"
                "<si><t>OS days</t></si>"
                "<si><t>S1</t></si>"
                "</sst>"
            ),
        )
        archive.writestr(
            "xl/workbook.xml",
            (
                f'<workbook xmlns="{spreadsheet_ns}" '
                f'xmlns:r="{relationship_ns}"><sheets>'
                '<sheet name="Summary" sheetId="1" r:id="rId1"/>'
                '<sheet name="Patient data" sheetId="2" r:id="rId2"/>'
                "</sheets></workbook>"
            ),
        )
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            (
                f'<Relationships xmlns="{package_relationship_ns}">'
                '<Relationship Id="rId1" Target="worksheets/sheet1.xml"/>'
                '<Relationship Id="rId2" Target="worksheets/sheet2.xml"/>'
                "</Relationships>"
            ),
        )
        archive.writestr(
            "xl/worksheets/sheet2.xml",
            (
                f'<worksheet xmlns="{spreadsheet_ns}"><sheetData>'
                '<row r="3"><c r="A3" t="s"><v>0</v></c>'
                '<c r="B3" t="s"><v>1</v></c></row>'
                '<row r="4"><c r="A4" t="s"><v>2</v></c>'
                '<c r="B4"><v>365</v></c></row>'
                "</sheetData></worksheet>"
            ),
        )

    assert read_xlsx_sheet(
        workbook,
        sheet_name="Patient data",
        header_row=3,
    ) == [{"Sample ID": "S1", "OS days": "365"}]


def test_publication_adapter_preserves_curated_records_and_license(
    tmp_path,
):
    records = normalize_curated_records(
        [
            {"ID": "1T", "Death": "Yes", "OS": 14.3},
            {"ID": "2T", "Death": "No", "OS": None},
        ]
    )
    assert records == [
        {"ID": "1T", "Death": "Yes", "OS": "14.3"},
        {"ID": "2T", "Death": "No", "OS": ""},
    ]

    full_text = tmp_path / "article.xml"
    full_text.write_text(
        '<article xmlns:xlink="http://www.w3.org/1999/xlink">'
        '<license xlink:href="https://creativecommons.org/licenses/'
        'by-nc/4.0/">CC BY-NC 4.0</license></article>',
        encoding="utf-8",
    )
    assert (
        detect_creative_commons_license(full_text)
        == "CC-BY-NC-4.0"
    )


def test_publication_expression_layouts_are_explicit_and_deterministic(
    tmp_path,
):
    gencode = tmp_path / "gencode.gtf.gz"
    with gzip.open(gencode, "wt", encoding="utf-8") as handle:
        handle.write(
            "chr1\tHAVANA\tgene\t1\t2\t.\t+\t.\t"
            'gene_id "ENSG000001.4"; gene_name "GENEA";\n'
            "chr1\tHAVANA\ttranscript\t1\t2\t.\t+\t.\t"
            'gene_id "ENSG000001.4"; gene_name "GENEA";\n'
        )
    assert parse_gencode_gene_map(gencode) == {
        "ENSG000001": "GENEA",
        "ENSG000001.4": "GENEA",
    }
    assert selected_sample_indexes(
        ["feature", "az-1", "AZ-2"],
        ["AZ-1", "az-2"],
        case_insensitive=True,
    ) == [1, 2]

    source = tmp_path / "rpkm.txt.gz"
    with gzip.open(
        source, "wt", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.writer(handle, delimiter="\t")
        writer.writerow(
            [
                "No",
                "Chr",
                "Ensembl",
                "Symbol",
                "Start",
                "Stop",
                "Length",
                "source-a",
                "source-b",
            ]
        )
        writer.writerow(["", "", "", "", "", "", "", "1T", "2T"])
        for index in range(10_000):
            writer.writerow(
                [
                    index,
                    "chr1",
                    f"ENSG{index:011d}",
                    f"GENE{index}",
                    1,
                    2,
                    2,
                    1.0,
                    2.0,
                ]
            )
    assert publication_expression_sample_ids(
        source,
        {
            "layout": "geo_rpkm_two_row_header",
            "delimiter": "\t",
            "metadata_columns": 7,
        },
    ) == ["1T", "2T"]
    output = tmp_path / "selected.tsv"
    summary = materialize_geo_rpkm_matrix(
        source,
        output,
        ["2T", "1T"],
        delimiter="\t",
        metadata_columns=7,
        ensembl_column=2,
        symbol_column=3,
    )
    assert summary["mapped_expression_gene_rows"] == 10_000
    with output.open(encoding="utf-8") as handle:
        reader = csv.reader(handle, delimiter="\t")
        assert next(reader) == [
            "Ensembl_Gene_Id|Hugo_Symbol",
            "2T",
            "1T",
        ]
        assert next(reader) == [
            "ENSG00000000000|GENE0",
            "2.0",
            "1.0",
        ]


def test_cbioportal_source_and_sample_rules_are_declarative():
    assert resolve_source_file_spec(
        "public/example",
        "data_mrna_seq.txt",
    ) == ("public/example/data_mrna_seq.txt", "data_mrna_seq.txt")
    assert resolve_source_file_spec(
        "public/example",
        {
            "path": "README.md",
            "scope": "repository",
            "target_name": "DATAHUB_LICENSE.md",
        },
    ) == ("README.md", "DATAHUB_LICENSE.md")
    with pytest.raises(ValueError, match="Invalid source"):
        resolve_source_file_spec("public/example", "../LICENSE")

    patient = {"DISEASE": "AML"}
    initial = {
        "STAGE": "Initial Diagnosis",
        "SPECIMEN": "Bone Marrow",
    }
    relapse = {
        "STAGE": "Relapse",
        "SPECIMEN": "Peripheral Blood",
    }
    rules = [
        {
            "field": "patient.DISEASE",
            "include": ["AML"],
            "required": True,
        },
        {
            "field": "sample.STAGE",
            "include": ["Initial Diagnosis"],
        },
    ]
    assert sample_passes_eligibility(patient, initial, rules)
    assert not sample_passes_eligibility(patient, relapse, rules)
    sample_spec = {
        "selection_rank_rules": [
            {
                "field": "sample.SPECIMEN",
                "order": ["Bone Marrow", "Peripheral Blood"],
            }
        ]
    }
    assert sample_selection_rank(patient, initial, sample_spec) == 0
    assert sample_selection_rank(patient, relapse, sample_spec) == 1


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
    assert result["schema_version"] == "tcga-trace-cbioportal-discovery-v2"
    assert result["cancers"][0]["rejection_reasons"] == {
        "disallowed_accession": 1
    }
    assert result["cancers"][0]["rejections"][0]["study_id"] == "blca_tcga"


def test_cbioportal_rna_sample_lists_recover_missing_summary_count():
    assert _rna_seq_sample_count(
        [
            {
                "category": "all_cases_with_mrna_rnaseq_data",
                "sampleIds": ["S1", "S2"],
            },
            {
                "category": "all_cases_with_mrna_rnaseq_data",
                "sampleIds": ["S2", "S3"],
            },
            {
                "category": "all_cases_with_mrna_array_data",
                "sampleIds": ["A1"],
            },
        ]
    ) == 3


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
