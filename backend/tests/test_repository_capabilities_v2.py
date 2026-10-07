import csv
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import (
    CancerType,
    RepositoryDataset,
    RepositoryExpressionLayer,
    RepositoryRelease,
    RepositorySample,
)
from app.pancancer_study_universes import (
    SourceKind,
    StudyUniverseCategory,
)
from app.repository import importer
from app.repository import rank_attestation
from app.repository import capabilities as repository_capability_rules
from app.repository.adapters import cbioportal
from app.repository.capabilities import (
    RANK_SIGNATURE_MAXIMUM_MATRIX_ENTRIES,
    derive_repository_capabilities,
    rank_signature_capability_from_qc,
)
from app.repository.adapters.gdc import (
    resolve_gdc_sample_type_priority,
    select_gdc_expression_files,
    validate_gdc_project_policy,
)
from app.repository.contracts import (
    BUNDLE_SCHEMA_VERSION_V1,
    BUNDLE_SCHEMA_VERSION_V2,
    STUDY_SPEC_SCHEMA_VERSION_V1,
    STUDY_SPEC_SCHEMA_VERSION_V2,
)
from app.repository.service import (
    list_repository_datasets,
    repository_capabilities,
    repository_dataset_detail,
    repository_expression_layers,
    repository_expression_layer_coverage,
    require_repository_capability,
    resolve_repository_context,
)
from app.repository.storage import sha256_file, write_float32le_matrix


def _write_tsv(
    path: Path,
    fieldnames: list[str],
    rows: list[dict[str, object]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fieldnames,
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def _build_bundle(
    root: Path,
    *,
    schema_version: str = BUNDLE_SCHEMA_VERSION_V2,
    endpoint_rows: list[dict[str, object]] | None = None,
    cancer_code: str = "SKCM",
) -> Path:
    derived = root / "derived"
    source = root / "source"
    source.mkdir(parents=True)
    (source / "LICENSE").write_text(
        "Fixture license\n", encoding="utf-8"
    )
    patient_ids = [f"P{index:02d}" for index in range(10)]
    sample_ids = [f"S{index:02d}" for index in range(10)]
    _write_tsv(
        derived / "patients.tsv",
        ["patient_id"],
        [{"patient_id": patient_id} for patient_id in patient_ids],
    )
    _write_tsv(
        derived / "samples.tsv",
        ["sample_id", "patient_id", "selection_rank"],
        [
            {
                "sample_id": sample_id,
                "patient_id": patient_id,
                "selection_rank": 0,
            }
            for sample_id, patient_id in zip(
                sample_ids, patient_ids, strict=True
            )
        ],
    )
    _write_tsv(
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
    (derived / "expression.metadata.json").write_text(
        json.dumps(
            {
                "dtype": "float32_le",
                "layout": "row_major_gene_by_sample",
                "gene_count": 2,
                "sample_count": 10,
                "sample_ids": sample_ids,
            }
        ),
        encoding="utf-8",
    )
    endpoint_definitions = []
    relative_files = [
        "derived/patients.tsv",
        "derived/samples.tsv",
        "derived/genes.tsv",
        "derived/expression.float32le.bin",
        "derived/expression.metadata.json",
    ]
    if endpoint_rows is not None:
        _write_tsv(
            derived / "endpoint_os.tsv",
            ["patient_id", "time_days", "event"],
            endpoint_rows,
        )
        relative_files.append("derived/endpoint_os.tsv")
        endpoint_definitions.append(
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
        )
    manifest = {
        "schema_version": schema_version,
        "dataset": {
            "id": "fixture-study",
            "cancer_code": cancer_code,
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
            "id": "fixture-release-v2",
            "version": "v2",
            "source_snapshot": "fixture-sha",
        },
        "files": {
            "patients": "derived/patients.tsv",
            "samples": "derived/samples.tsv",
        },
        "endpoints": endpoint_definitions,
        "expression_layers": [
            {
                "layer_id": "expression",
                "label": "Expression",
                "source_unit": "TPM",
                "analysis_unit": "log2(TPM + 1)",
                "transform": "identity",
                "is_default": True,
                "downloadable": True,
                "genes_file": "derived/genes.tsv",
                "matrix_file": "derived/expression.float32le.bin",
                "metadata_file": "derived/expression.metadata.json",
            }
        ],
        "source_files": {"license": "source/LICENSE"},
        "checksums": {
            relative: sha256_file(root / relative)
            for relative in [*relative_files, "source/LICENSE"]
        },
    }
    (root / "manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    return root


def _seed_cancer(db) -> None:
    db.add(
        CancerType(
            code="SKCM",
            tcga_cohort="TCGA-SKCM",
            name="Skin Cutaneous Melanoma",
            primary_site="Skin",
            sort_order=0,
            coverage_status="candidate_validated",
        )
    )
    db.commit()


def _database():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def test_layer_patient_counts_and_endpoints_do_not_inherit_release_totals():
    qc = {
        "status": "passed", "patients": 135,
        "molecular_population": {"patients": 135, "samples": 201, "genes": 15926},
        "endpoints": {"OS": {"patients": 135, "available": True}},
        "layers": {"paired": {"samples": 66, "patients": 66, "genes": 15926,
            "nonfinite_values": 0, "endpoints": {"OS": {"patients": 60, "available": True}}}},
    }
    result = derive_repository_capabilities(qc, "paired")
    assert result["expression"]["patient_count"] == 66
    assert result["gsea"]["patient_count"] == 66
    assert result["survival"]["patient_count"] == 60
    qc["layers"]["paired"]["patients"] = 0
    qc["layers"]["paired"]["endpoints"] = {}
    empty = derive_repository_capabilities(qc, "paired")
    assert empty["expression"]["patient_count"] == 0
    assert empty["survival"]["patient_count"] == 0
    assert not empty["survival"]["available"]


def test_legacy_layer_coverage_links_unique_patients_and_outcomes(tmp_path, monkeypatch):
    from app.repository import service

    monkeypatch.setattr(importer, "MIN_GENES", 2)
    _stub_registry_disposition(monkeypatch)
    bundle = _build_bundle(tmp_path / "bundle", endpoint_rows=[
        {"patient_id": f"P{index:02d}", "time_days": index + 10, "event": int(index % 2 == 0)}
        for index in range(10) if index != 3
    ])
    with _database()() as db:
        _seed_cancer(db)
        importer.promote_bundle(db, bundle, tmp_path / "repository", tmp_path / "registry")
        context = resolve_repository_context(db, "fixture-study")
        frozen_qc = json.loads(json.dumps(context.release.qc_json))
        # Legacy non-default layer, with two RNA columns from the same patient.
        sample = db.scalar(select(RepositorySample).where(RepositorySample.sample_id == "S01"))
        sample.patient_id = "P00"
        db.flush()
        metadata = tmp_path / "subset.metadata.json"
        metadata.write_text(json.dumps({"dtype": "float32_le", "layout": "row_major_gene_by_sample",
            "sample_ids": ["S00", "S01", "S02", "S03"], "sample_count": 4}))
        layer = RepositoryExpressionLayer(layer_id="subset", sample_count=4, transform="identity")
        monkeypatch.setattr(service, "repository_expression_layer_paths", lambda *_args: (tmp_path / "unused", metadata))
        coverage = repository_expression_layer_coverage(db, context, layer)
        assert coverage["sample_count"] == 4
        assert coverage["patient_count"] == 3
        assert coverage["endpoints"]["OS"]["patients"] == 2
        assert coverage["endpoints"]["OS"]["events"] == 2
        assert not coverage["endpoints"]["OS"]["available"]
        assert context.release.qc_json == frozen_qc

        metadata.write_text(json.dumps({"dtype": "float32_le", "layout": "row_major_gene_by_sample",
            "sample_ids": ["S00", "S01", "S02", "UNKNOWN"], "sample_count": 4}))
        with pytest.raises(ValueError, match="linkage could not be verified"):
            repository_expression_layer_coverage(db, context, layer)


def test_importer_freezes_patient_and_endpoint_coverage_per_layer(tmp_path, monkeypatch):
    monkeypatch.setattr(importer, "MIN_GENES", 2)
    qc = importer.validate_bundle(_build_bundle(tmp_path / "bundle"))["qc"]
    assert qc["layers"]["expression"]["patients"] == 10
    assert qc["layers"]["expression"]["endpoints"] == {}


def test_rank_signature_capability_is_derived_and_can_be_prohibited() -> None:
    qc = {
        "status": "passed",
        "thresholds": {"minimum_patients": 10, "minimum_genes": 1000},
        "molecular_population": {
            "patients": 10,
            "samples": 10,
            "genes": 1200,
        },
        "default_expression_layer_id": "broad",
        "layers": {
            "broad": {
                "genes": 1200,
                "samples": 10,
                "is_default": True,
                "nonfinite_values": 0,
            }
        },
        "endpoints": {},
    }
    available = derive_repository_capabilities(qc)
    assert available["rank_based_signature_scoring"] == {
        "available": True,
        "reason": None,
        "expression_layer_id": "broad",
        "gene_count": 1200,
        "sample_count": 10,
        "minimum_genes": 1000,
        "matrix_entry_count": 12_000,
        "maximum_matrix_entries": RANK_SIGNATURE_MAXIMUM_MATRIX_ENTRIES,
        "missing_value_count": 0,
        "complete_matrix_verified": True,
        "methods": ["singscore", "ssgsea", "aucell"],
    }

    prohibited = derive_repository_capabilities(
        {
            **qc,
            "capability_policy": {
                "prohibited": {
                    "rank_based_signature_scoring": "Feature universe is not suitable."
                }
            },
        }
    )
    assert prohibited["rank_based_signature_scoring"]["available"] is False
    assert prohibited["rank_based_signature_scoring"]["methods"] == []
    assert "not suitable" in prohibited["rank_based_signature_scoring"]["reason"]


def test_rank_signature_capability_follows_selected_expression_layer() -> None:
    qc = {
        "status": "passed",
        "thresholds": {"minimum_patients": 10, "minimum_genes": 10},
        "molecular_population": {
            "patients": 20,
            "samples": 20,
            "genes": 12_000,
        },
        "default_expression_layer_id": "broad",
        "layers": {
            "broad": {
                "genes": 12_000,
                "samples": 20,
                "is_default": True,
                "nonfinite_values": 0,
            },
            "targeted": {
                "genes": 420,
                "samples": 20,
                "is_default": False,
                "nonfinite_values": 0,
            },
        },
        "endpoints": {},
    }

    broad = derive_repository_capabilities(qc, "broad")
    targeted = derive_repository_capabilities(qc, "targeted")

    assert broad["rank_based_signature_scoring"]["available"] is True
    assert broad["rank_based_signature_scoring"]["gene_count"] == 12_000
    assert targeted["rank_based_signature_scoring"]["available"] is False
    assert targeted["rank_based_signature_scoring"]["gene_count"] == 420
    assert "selected layer contains 420" in targeted[
        "rank_based_signature_scoring"
    ]["reason"]


def test_rank_signature_capability_rejects_broad_layer_with_missing_values() -> None:
    qc = {
        "status": "passed",
        "thresholds": {"minimum_patients": 10, "minimum_genes": 10},
        "molecular_population": {
            "patients": 20,
            "samples": 20,
            "genes": 12_000,
        },
        "default_expression_layer_id": "broad",
        "layers": {
            "broad": {
                "genes": 12_000,
                "samples": 20,
                "is_default": True,
                "nonfinite_values": 7,
            }
        },
        "endpoints": {},
    }

    rank = derive_repository_capabilities(qc, "broad")[
        "rank_based_signature_scoring"
    ]

    assert rank["available"] is False
    assert rank["missing_value_count"] == 7
    assert rank["complete_matrix_verified"] is False
    assert "7 missing or non-finite values" in rank["reason"]


def test_rank_signature_capability_enforces_engine_matrix_entry_limit() -> None:
    sample_count = 5_050
    gene_count = RANK_SIGNATURE_MAXIMUM_MATRIX_ENTRIES // sample_count + 1
    matrix_entry_count = gene_count * sample_count
    qc = {
        "status": "passed",
        "thresholds": {"minimum_patients": 10, "minimum_genes": 10},
        "molecular_population": {
            "patients": sample_count,
            "samples": sample_count,
            "genes": gene_count,
        },
        "default_expression_layer_id": "scan_b",
        "layers": {
            "scan_b": {
                "genes": gene_count,
                "samples": sample_count,
                "is_default": True,
                "nonfinite_values": 0,
            }
        },
        "endpoints": {},
    }

    rank = derive_repository_capabilities(qc, "scan_b")[
        "rank_based_signature_scoring"
    ]

    assert rank["available"] is False
    assert rank["matrix_entry_count"] == matrix_entry_count
    assert (
        rank["maximum_matrix_entries"]
        == RANK_SIGNATURE_MAXIMUM_MATRIX_ENTRIES
    )
    assert rank["complete_matrix_verified"] is True
    assert f"{matrix_entry_count:,} matrix entries" in rank["reason"]
    assert (
        f"current limit is {RANK_SIGNATURE_MAXIMUM_MATRIX_ENTRIES:,}"
        in rank["reason"]
    )


def test_rank_signature_capability_does_not_guess_missing_layer_dimensions() -> None:
    rank = rank_signature_capability_from_qc(
        {
            "status": "passed",
            "thresholds": {"minimum_patients": 10, "minimum_genes": 10},
            "molecular_population": {
                "patients": 20,
                "samples": 20,
                "genes": 12_000,
            },
            "default_expression_layer_id": "legacy",
            "layers": {
                "legacy": {
                    "genes": 12_000,
                    "is_default": True,
                    "nonfinite_values": 0,
                }
            },
            "endpoints": {},
        },
        expression_layer_id="legacy",
    )

    assert rank["available"] is False
    assert rank["sample_count"] is None
    assert rank["matrix_entry_count"] is None
    assert "could not verify the dimensions" in rank["reason"]


def _stub_registry_disposition(
    monkeypatch,
    *,
    cancer_code: str = "SKCM",
    active: bool = True,
    category: StudyUniverseCategory = StudyUniverseCategory.CATALOG_ONLY,
    catalog: bool = True,
    expression_comparison: bool = True,
    gsea: bool = True,
    survival: bool = False,
    hierarchical_pancancer: bool = False,
    endpoint_class: str | None = None,
    endpoint_id: str | None = None,
) -> None:
    def capability(available: bool) -> SimpleNamespace:
        return SimpleNamespace(available=available)

    disposition = SimpleNamespace(
        universe_id="fixture-study",
        source_kind=SourceKind.EXTERNAL,
        cancer_code=cancer_code,
        active=active,
        registry_category=category,
        endpoint_class=endpoint_class,
        endpoint_id=endpoint_id,
        capabilities=SimpleNamespace(
            catalog=capability(catalog),
            expression_comparison=capability(expression_comparison),
            gsea=capability(gsea),
            survival=capability(survival),
            hierarchical_pancancer=capability(hierarchical_pancancer),
        ),
    )
    monkeypatch.setattr(
        importer,
        "require_study_registry_disposition",
        lambda registry_root, dataset_id: disposition,
    )
    monkeypatch.setattr(
        importer,
        "load_dataset_candidate_registry",
        lambda path: {"candidates": []},
    )


def _promoted_candidate_record(**overrides):
    def capability(available: bool) -> dict[str, object]:
        return {
            "available": available,
            "decision": "enabled" if available else "disabled",
            "reason": "Fixture decision",
        }

    candidate = {
        "id": "fixture-study",
        "status": "promoted",
        "decisions": {
            "catalog_state": "promoted_release",
            "promotion_state": "promoted",
            "hierarchical_state": "not_eligible",
            "target_category": "catalog_only",
        },
        "capabilities": {
            "catalog": capability(True),
            "expression_comparison": capability(True),
            "gsea": capability(True),
            "survival": capability(False),
            "hierarchical_pancancer": capability(False),
        },
        "blockers": [],
    }
    for path, value in overrides.items():
        section, key = path.split("__", maxsplit=1)
        if section == "root":
            candidate[key] = value
        else:
            candidate[section][key] = value
    return candidate


def test_v2_expression_only_bundle_passes_and_derives_capabilities(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(importer, "MIN_GENES", 2)
    bundle = _build_bundle(tmp_path / "bundle")

    validation = importer.validate_bundle(bundle)

    assert validation["qc"]["status"] == "passed"
    assert validation["qc"]["endpoints"] == {}
    assert validation["qc"]["molecular_population"] == {
        "patients": 10,
        "samples": 10,
        "genes": 2,
    }
    assert validation["qc"]["capabilities"]["survival"][
        "available"
    ] is False
    assert validation["qc"]["available_modules"] == [
        "expression",
        "gsea",
    ]


def test_manifest_must_checksum_every_referenced_release_file(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(importer, "MIN_GENES", 2)
    bundle = _build_bundle(tmp_path / "bundle")
    manifest_path = bundle / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["checksums"].pop("derived/patients.tsv")
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    validation = importer.validate_bundle(bundle)

    assert validation["qc"]["status"] == "failed"
    assert (
        "Referenced bundle file is not checksum-protected: "
        "derived/patients.tsv."
    ) in validation["qc"]["errors"]


def test_manifest_rejects_malformed_checksum(tmp_path, monkeypatch):
    monkeypatch.setattr(importer, "MIN_GENES", 2)
    bundle = _build_bundle(tmp_path / "bundle")
    manifest_path = bundle / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["checksums"]["derived/patients.tsv"] = "not-a-sha256"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    validation = importer.validate_bundle(bundle)

    assert validation["qc"]["status"] == "failed"
    assert any(
        "Invalid SHA-256 checksum for derived/patients.tsv" in error
        for error in validation["qc"]["errors"]
    )


def test_public_repository_rejects_reserved_private_dataset_prefix(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(importer, "MIN_GENES", 2)
    bundle = _build_bundle(tmp_path / "bundle")
    manifest_path = bundle / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["dataset"]["id"] = "user-public-collision"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    validation = importer.validate_bundle(bundle)

    assert validation["qc"]["status"] == "failed"
    assert any("reserved user- prefix" in error for error in validation["qc"]["errors"])


def test_matrix_qc_rejects_nonfinite_values(tmp_path, monkeypatch):
    monkeypatch.setattr(importer, "MIN_GENES", 2)
    bundle = _build_bundle(tmp_path / "bundle")
    matrix_path = bundle / "derived/expression.float32le.bin"
    write_float32le_matrix(
        matrix_path,
        [
            [float("nan"), *[float(index) for index in range(1, 10)]],
            [float(index + 10) for index in range(10)],
        ],
    )
    manifest_path = bundle / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["checksums"]["derived/expression.float32le.bin"] = sha256_file(
        matrix_path
    )
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    validation = importer.validate_bundle(bundle)

    assert validation["qc"]["status"] == "failed"
    assert validation["qc"]["layers"]["expression"]["nonfinite_values"] == 1
    assert any("non-finite expression values" in error for error in validation["qc"]["errors"])


def test_matrix_qc_rejects_an_all_constant_matrix(tmp_path, monkeypatch):
    monkeypatch.setattr(importer, "MIN_GENES", 2)
    bundle = _build_bundle(tmp_path / "bundle")
    matrix_path = bundle / "derived/expression.float32le.bin"
    write_float32le_matrix(matrix_path, [[1.0] * 10, [2.0] * 10])
    manifest_path = bundle / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["checksums"]["derived/expression.float32le.bin"] = sha256_file(
        matrix_path
    )
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    validation = importer.validate_bundle(bundle)

    assert validation["qc"]["status"] == "failed"
    assert validation["qc"]["layers"]["expression"]["variable_genes"] == 0
    assert any("no gene with variable expression" in error for error in validation["qc"]["errors"])


def test_gene_rows_must_match_contiguous_matrix_order(tmp_path, monkeypatch):
    monkeypatch.setattr(importer, "MIN_GENES", 2)
    bundle = _build_bundle(tmp_path / "bundle")
    genes_path = bundle / "derived/genes.tsv"
    rows = importer.read_tsv(genes_path)
    rows[1]["row_number"] = "0"
    _write_tsv(genes_path, list(rows[0]), rows)
    manifest_path = bundle / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["checksums"]["derived/genes.tsv"] = sha256_file(genes_path)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    validation = importer.validate_bundle(bundle)

    assert validation["qc"]["status"] == "failed"
    assert any(
        "row_number values must be unique, contiguous" in error
        for error in validation["qc"]["errors"]
    )


def test_v1_subthreshold_endpoint_preserves_molecular_capabilities(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(importer, "MIN_GENES", 2)
    endpoint_rows = [
        {
            "patient_id": f"P{index:02d}",
            "time_days": 100 + index,
            "event": 1,
        }
        for index in range(10)
    ]
    bundle = _build_bundle(
        tmp_path / "bundle",
        schema_version=BUNDLE_SCHEMA_VERSION_V1,
        endpoint_rows=endpoint_rows,
    )

    validation = importer.validate_bundle(bundle)

    assert validation["qc"]["status"] == "passed"
    assert validation["qc"]["endpoints"]["OS"] == {
        "patients": 10,
        "events": 10,
        "censored": 0,
        "available": False,
    }
    assert validation["qc"]["capabilities"]["expression"][
        "available"
    ] is True
    assert validation["qc"]["capabilities"]["gsea"][
        "available"
    ] is True
    assert validation["qc"]["capabilities"]["survival"][
        "available"
    ] is False


def test_v1_endpointless_bundle_requires_explicit_survival_prohibition(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(importer, "MIN_GENES", 2)
    bundle = _build_bundle(
        tmp_path / "bundle", schema_version=BUNDLE_SCHEMA_VERSION_V1
    )

    without_policy = importer.validate_bundle(bundle)["qc"]

    assert without_policy["status"] == "failed"
    assert any(
        "must explicitly prohibit survival analysis" in error
        for error in without_policy["errors"]
    )

    manifest_path = bundle / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["capability_policy"] = {
        "prohibited": {
            "survival": "No outcome endpoint is provided by this release."
        }
    }
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with_policy = importer.validate_bundle(bundle)["qc"]

    assert with_policy["status"] == "passed"
    assert with_policy["capabilities"]["expression"]["available"] is True
    assert with_policy["capabilities"]["survival"] == {
        "available": False,
        "reason": "No outcome endpoint is provided by this release.",
        "patient_count": 0,
        "endpoint_ids": [],
    }


def test_subthreshold_endpoint_does_not_mask_invalid_expression(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(importer, "MIN_GENES", 2)
    endpoint_rows = [
        {
            "patient_id": f"P{index:02d}",
            "time_days": 100 + index,
            "event": 1,
        }
        for index in range(10)
    ]
    bundle = _build_bundle(
        tmp_path / "bundle",
        schema_version=BUNDLE_SCHEMA_VERSION_V1,
        endpoint_rows=endpoint_rows,
    )
    matrix_path = bundle / "derived/expression.float32le.bin"
    write_float32le_matrix(
        matrix_path,
        [
            [float("nan"), *[float(index) for index in range(1, 10)]],
            [float(index + 10) for index in range(10)],
        ],
    )
    manifest_path = bundle / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["checksums"]["derived/expression.float32le.bin"] = (
        sha256_file(matrix_path)
    )
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    qc = importer.validate_bundle(bundle)["qc"]

    assert qc["status"] == "failed"
    assert qc["endpoints"]["OS"]["available"] is False
    assert qc["layers"]["expression"]["nonfinite_values"] == 1
    assert all(not details["available"] for details in qc["capabilities"].values())


def test_v2_sparse_endpoint_does_not_shrink_molecular_population(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(importer, "MIN_GENES", 2)
    endpoint_rows = [
        {
            "patient_id": f"P{index:02d}",
            "time_days": 100 + index,
            "event": int(index < 3),
        }
        for index in range(6)
    ]
    validation = importer.validate_bundle(
        _build_bundle(tmp_path / "bundle", endpoint_rows=endpoint_rows)
    )

    assert validation["qc"]["status"] == "passed"
    assert validation["qc"]["patients"] == 10
    assert validation["qc"]["endpoints"]["OS"] == {
        "patients": 6,
        "events": 3,
        "censored": 3,
        "available": False,
    }
    assert validation["qc"]["capabilities"]["survival"][
        "available"
    ] is False


def test_v2_capability_policy_can_prohibit_but_not_enable_survival(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(importer, "MIN_GENES", 2)
    endpoint_rows = [
        {
            "patient_id": f"P{index:02d}",
            "time_days": 100 + index,
            "event": int(index < 5),
        }
        for index in range(10)
    ]
    bundle = _build_bundle(
        tmp_path / "bundle", endpoint_rows=endpoint_rows
    )
    manifest_path = bundle / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["capability_policy"] = {
        "prohibited": {
            "survival": "Outcome-conditioned ascertainment."
        }
    }
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    qc = importer.validate_bundle(bundle)["qc"]

    assert qc["status"] == "passed"
    assert qc["endpoints"]["OS"]["available"] is True
    assert qc["capabilities"]["survival"] == {
        "available": False,
        "reason": "Outcome-conditioned ascertainment.",
        "patient_count": 10,
        "endpoint_ids": [],
    }
    assert qc["available_modules"] == ["expression", "gsea"]


def test_capability_cache_cannot_override_qc_or_curated_prohibition():
    cached_all_available = {
        capability: {"available": True}
        for capability in (
            "expression",
            "expression_comparison",
            "gsea",
            "survival",
        )
    }
    failed_qc = {
        "status": "failed",
        "patients": 100,
        "molecular_population": {
            "patients": 100,
            "samples": 100,
            "genes": 20_000,
        },
        "endpoints": {
            "OS": {
                "patients": 100,
                "events": 50,
                "censored": 50,
                "available": True,
            }
        },
        "capabilities": cached_all_available,
    }
    prohibited_survival = {
        **failed_qc,
        "status": "passed",
        "capability_policy": {
            "prohibited": {"survival": "Curated survival prohibition."}
        },
    }

    failed = derive_repository_capabilities(failed_qc)
    prohibited = derive_repository_capabilities(prohibited_survival)

    assert all(not row["available"] for row in failed.values())
    assert prohibited["expression"]["available"] is True
    assert prohibited["survival"] == {
        "available": False,
        "reason": "Curated survival prohibition.",
        "patient_count": 100,
        "endpoint_ids": [],
    }


def test_v2_validation_rejects_duplicate_endpoint_patients_and_unsafe_ids(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(importer, "MIN_GENES", 2)
    endpoint_rows = [
        {
            "patient_id": f"P{index:02d}",
            "time_days": 100 + index,
            "event": int(index < 5),
        }
        for index in range(10)
    ]
    bundle = _build_bundle(
        tmp_path / "bundle", endpoint_rows=endpoint_rows
    )
    endpoint_path = bundle / "derived/endpoint_os.tsv"
    endpoint_rows.append(dict(endpoint_rows[0]))
    _write_tsv(
        endpoint_path,
        ["patient_id", "time_days", "event"],
        endpoint_rows,
    )
    manifest_path = bundle / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["dataset"]["id"] = "../unsafe"
    manifest["checksums"]["derived/endpoint_os.tsv"] = sha256_file(
        endpoint_path
    )
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    qc = importer.validate_bundle(bundle)["qc"]

    assert qc["status"] == "failed"
    assert "The dataset ID contains unsafe path characters." in qc["errors"]
    assert "Endpoint OS contains duplicate patient rows." in qc["errors"]


def test_catalog_capability_filter_and_stable_require_helper(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(importer, "MIN_GENES", 2)
    _stub_registry_disposition(monkeypatch)
    bundle = _build_bundle(tmp_path / "bundle")
    factory = _database()
    repository_root = tmp_path / "repository"

    with factory() as db:
        _seed_cancer(db)
        importer.promote_bundle(
            db,
            bundle,
            repository_root,
            tmp_path / "registry",
        )
        [dataset] = list_repository_datasets(
            db, analysis_type="expression"
        )
        assert dataset["available_modules"] == ["expression", "gsea"]
        assert dataset["capabilities"]["gsea"]["available"] is True
        assert list_repository_datasets(db, analysis_type="survival") == []

        release = db.get(RepositoryRelease, "fixture-release-v2")
        assert repository_capabilities(release)["expression"][
            "available"
        ] is True
        assert require_repository_capability(release, "gsea")[
            "available"
        ] is True
        with pytest.raises(
            ValueError,
            match="Repository data do not support 'survival'",
        ):
            require_repository_capability(release, "survival")

        context = resolve_repository_context(db, "fixture-study")
        detail = repository_dataset_detail(db, context)
        assert detail["capabilities"] == dataset["capabilities"]
        [layer] = repository_expression_layers(db, context)
        layer_rank = layer["capabilities"]["rank_based_signature_scoring"]
        assert layer_rank["expression_layer_id"] == "expression"
        assert layer_rank["gene_count"] == 2
        assert layer_rank["missing_value_count"] == 0
        assert layer_rank["complete_matrix_verified"] is True

        release.qc_status = "failed"
        db.commit()
        assert list_repository_datasets(db) == []
        assert len(
            list_repository_datasets(db, include_unavailable=True)
        ) == 1


def test_legacy_rank_attestation_is_dry_run_by_default_and_checksum_gated(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(importer, "MIN_GENES", 2)
    monkeypatch.setattr(
        repository_capability_rules,
        "RANK_SIGNATURE_MINIMUM_GENES",
        2,
    )
    _stub_registry_disposition(monkeypatch)
    bundle = _build_bundle(tmp_path / "bundle")
    factory = _database()
    repository_root = tmp_path / "repository"

    with factory() as db:
        _seed_cancer(db)
        importer.promote_bundle(
            db,
            bundle,
            repository_root,
            tmp_path / "registry",
        )
        release = db.get(RepositoryRelease, "fixture-release-v2")
        legacy_qc = json.loads(json.dumps(release.qc_json))
        legacy_qc["layers"]["expression"].pop("nonfinite_values")
        legacy_qc["layers"]["expression"].pop("finite_values")
        release.qc_json = legacy_qc
        db.commit()
        layer = db.scalar(
            select(RepositoryExpressionLayer).where(
                RepositoryExpressionLayer.release_id == release.id
            )
        )
        monkeypatch.setattr(
            rank_attestation,
            "repository_expression_layer_paths",
            lambda _context, selected: (
                Path(selected.matrix_path),
                Path(selected.metadata_path),
            ),
        )

        before = json.loads(json.dumps(release.qc_json))
        rank_before = repository_capabilities(
            release,
            expression_layer_id="expression",
        )["rank_based_signature_scoring"]
        assert rank_before["complete_matrix_verified"] is False
        assert "could not verify" in rank_before["reason"]

        dry_run = rank_attestation.attest_legacy_rank_layers(
            db,
            release_id=release.id,
        )
        db.refresh(release)
        assert dry_run["apply"] is False
        assert dry_run["pending_layers"] == 1
        assert dry_run["updated_layers"] == 0
        assert release.qc_json == before

        applied = rank_attestation.attest_legacy_rank_layers(
            db,
            release_id=release.id,
            apply=True,
        )
        db.refresh(release)
        assert applied["updated_layers"] == 1
        layer_qc = release.qc_json["layers"]["expression"]
        assert layer_qc["nonfinite_values"] == 0
        assert layer_qc["rank_scoring_attestation"]["matrix_sha256"] == (
            layer.matrix_sha256
        )
        rank_after = repository_capabilities(
            release,
            expression_layer_id="expression",
        )["rank_based_signature_scoring"]
        assert rank_after["complete_matrix_verified"] is True
        assert rank_after["missing_value_count"] == 0

        # A mismatched immutable checksum blocks a fresh attestation before any
        # QC JSON can be written.
        layer.matrix_sha256 = "0" * 64
        legacy_again = json.loads(json.dumps(release.qc_json))
        legacy_again["layers"]["expression"].pop("nonfinite_values")
        legacy_again["layers"]["expression"].pop("rank_scoring_attestation")
        release.qc_json = legacy_again
        db.commit()
        with pytest.raises(ValueError, match="checksum"):
            rank_attestation.attest_legacy_rank_layers(
                db,
                release_id=release.id,
                apply=True,
            )
        db.refresh(release)
        assert "nonfinite_values" not in release.qc_json["layers"]["expression"]


def test_promotion_preflight_and_rollback_leave_no_orphan_release(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(importer, "MIN_GENES", 2)
    repository_root = tmp_path / "repository"
    factory = _database()

    unknown_bundle = _build_bundle(
        tmp_path / "unknown", cancer_code="NOPE"
    )
    _stub_registry_disposition(monkeypatch, cancer_code="NOPE")
    with factory() as db:
        with pytest.raises(ValueError, match="Unknown cancer type"):
            importer.promote_bundle(
                db,
                unknown_bundle,
                repository_root,
                tmp_path / "registry",
            )
    assert not (repository_root / "studies" / "fixture-study").exists()

    valid_bundle = _build_bundle(tmp_path / "valid")
    _stub_registry_disposition(monkeypatch)
    destination = (
        repository_root
        / "studies"
        / "fixture-study"
        / "releases"
        / "fixture-release-v2"
    )
    with factory() as db:
        _seed_cancer(db)

        def fail_import(*args, **kwargs):
            raise RuntimeError("fixture database failure")

        monkeypatch.setattr(importer, "_import_release_rows", fail_import)
        with pytest.raises(RuntimeError, match="fixture database failure"):
            importer.promote_bundle(
                db,
                valid_bundle,
                repository_root,
                tmp_path / "registry",
            )
        assert db.scalar(select(RepositoryDataset)) is None
        assert db.scalar(select(RepositoryRelease)) is None
    assert not destination.exists()


def test_promotion_registry_gate_is_required_and_read_only_on_failure(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(importer, "MIN_GENES", 2)
    bundle = _build_bundle(tmp_path / "bundle")
    repository_root = tmp_path / "repository"
    factory = _database()

    def missing_disposition(registry_root, dataset_id):
        raise ValueError("Study registry manifest is missing")

    monkeypatch.setattr(
        importer,
        "require_study_registry_disposition",
        missing_disposition,
    )
    with factory() as db:
        _seed_cancer(db)
        with pytest.raises(ValueError, match="registry manifest is missing"):
            importer.promote_bundle(
                db,
                bundle,
                repository_root,
                tmp_path / "registry",
            )
        assert db.scalar(select(RepositoryDataset)) is None
        assert db.scalar(select(RepositoryRelease)) is None
    assert not repository_root.exists()


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"active": False}, "is inactive"),
        ({"cancer_code": "BRCA"}, "Cancer code mismatch"),
        ({"catalog": False}, "does not permit catalog publication"),
        (
            {"expression_comparison": False},
            "Capability mismatch.*expression_comparison",
        ),
        ({"gsea": False}, "Capability mismatch.*gsea"),
        ({"survival": True}, "Capability mismatch.*survival"),
        (
            {"hierarchical_pancancer": True},
            "Hierarchical target mismatch",
        ),
        (
            {
                "category": StudyUniverseCategory.HIERARCHICAL_ACTIVE,
                "hierarchical_pancancer": True,
            },
            "requires an available survival endpoint",
        ),
    ],
)
def test_promotion_registry_gate_rejects_incompatible_dispositions(
    tmp_path,
    monkeypatch,
    overrides,
    message,
):
    monkeypatch.setattr(importer, "MIN_GENES", 2)
    bundle = _build_bundle(tmp_path / "bundle")
    _stub_registry_disposition(monkeypatch, **overrides)

    with pytest.raises(ValueError, match=message):
        importer.preflight_bundle_promotion(
            bundle,
            tmp_path / "registry",
        )


def test_promotion_registry_gate_accepts_matching_hierarchical_target(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(importer, "MIN_GENES", 2)
    endpoint_rows = [
        {
            "patient_id": f"P{index:02d}",
            "time_days": 100 + index,
            "event": int(index < 5),
        }
        for index in range(10)
    ]
    bundle = _build_bundle(
        tmp_path / "bundle",
        endpoint_rows=endpoint_rows,
    )
    _stub_registry_disposition(
        monkeypatch,
        category=StudyUniverseCategory.HIERARCHICAL_ACTIVE,
        survival=True,
        hierarchical_pancancer=True,
        endpoint_class="OS",
        endpoint_id="OS",
    )

    validation = importer.preflight_bundle_promotion(
        bundle,
        tmp_path / "registry",
    )

    assert validation["qc"]["status"] == "passed"


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"root__status": "under_review"}, "status='promoted'"),
        (
            {"decisions__promotion_state": "audit_required"},
            "promotion_state='promoted'",
        ),
        (
            {"decisions__catalog_state": "catalog_only"},
            "catalog_state='promoted_release'",
        ),
        (
            {
                "root__blockers": [
                    {"code": "qc_pending", "detail": "QC is pending."}
                ]
            },
            "unresolved promotion blockers",
        ),
        (
            {"decisions__target_category": "hierarchical_active"},
            "Candidate target mismatch",
        ),
        (
            {
                "capabilities__survival": {
                    "available": False,
                    "decision": "pending",
                    "reason": "Fixture decision",
                }
            },
            "Candidate capability mismatch.*survival",
        ),
        (
            {
                "capabilities__gsea": {
                    "available": False,
                    "decision": "disabled",
                    "reason": "Fixture decision",
                }
            },
            "Candidate capability mismatch.*gsea",
        ),
    ],
)
def test_promotion_gate_requires_final_candidate_ledger_state(
    tmp_path,
    monkeypatch,
    overrides,
    message,
):
    monkeypatch.setattr(importer, "MIN_GENES", 2)
    bundle = _build_bundle(tmp_path / "bundle")
    _stub_registry_disposition(monkeypatch)
    candidate = _promoted_candidate_record(**overrides)
    monkeypatch.setattr(
        importer,
        "load_dataset_candidate_registry",
        lambda path: {"candidates": [candidate]},
    )

    with pytest.raises(ValueError, match=message):
        importer.preflight_bundle_promotion(
            bundle,
            tmp_path / "registry",
        )


def test_promotion_gate_accepts_matching_promoted_candidate_record(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(importer, "MIN_GENES", 2)
    bundle = _build_bundle(tmp_path / "bundle")
    _stub_registry_disposition(monkeypatch)
    candidate = _promoted_candidate_record()
    monkeypatch.setattr(
        importer,
        "load_dataset_candidate_registry",
        lambda path: {"candidates": [candidate]},
    )

    validation = importer.preflight_bundle_promotion(
        bundle,
        tmp_path / "registry",
    )

    assert validation["qc"]["status"] == "passed"


def test_gdc_target_requires_exact_v2_opt_in_and_never_allows_tcga():
    with pytest.raises(ValueError, match="TARGET projects require"):
        validate_gdc_project_policy(
            STUDY_SPEC_SCHEMA_VERSION_V1, {}, "TARGET-AML"
        )
    with pytest.raises(ValueError, match="TARGET projects require"):
        validate_gdc_project_policy(
            STUDY_SPEC_SCHEMA_VERSION_V2,
            {"target_project_opt_in": "TARGET-ALL-P2"},
            "TARGET-AML",
        )
    validate_gdc_project_policy(
        STUDY_SPEC_SCHEMA_VERSION_V2,
        {"target_project_opt_in": "TARGET-AML"},
        "TARGET-AML",
    )
    with pytest.raises(ValueError, match="TCGA"):
        validate_gdc_project_policy(
            STUDY_SPEC_SCHEMA_VERSION_V2,
            {"target_project_opt_in": "TCGA-BRCA"},
            "TCGA-BRCA",
        )


def test_gdc_v2_requires_an_explicit_sample_type_allowlist():
    with pytest.raises(ValueError, match="explicit sample_type_priority"):
        resolve_gdc_sample_type_priority(
            STUDY_SPEC_SCHEMA_VERSION_V2, {}
        )
    with pytest.raises(ValueError, match="duplicates"):
        resolve_gdc_sample_type_priority(
            STUDY_SPEC_SCHEMA_VERSION_V2,
            {"sample_type_priority": ["Primary Tumor", "primary tumor"]},
        )
    assert resolve_gdc_sample_type_priority(
        STUDY_SPEC_SCHEMA_VERSION_V2,
        {"sample_type_priority": ["Primary Tumor"]},
    ) == ["Primary Tumor"]


def test_gdc_v2_selection_can_preserve_patients_without_survival():
    def hit(patient_id: str, sample_id: str, file_id: str):
        return {
            "file_id": file_id,
            "file_name": f"{file_id}.tsv",
            "file_size": 100,
            "md5sum": "a" * 32,
            "cases": [
                {
                    "case_id": f"case-{patient_id}",
                    "submitter_id": patient_id,
                    "samples": [
                        {
                            "sample_id": f"uuid-{sample_id}",
                            "submitter_id": sample_id,
                            "sample_type": "Primary Tumor",
                            "tissue_type": "Tumor",
                            "portions": [
                                {
                                    "analytes": [
                                        {
                                            "aliquots": [
                                                {
                                                    "aliquot_id": (
                                                        f"uuid-{sample_id}-R"
                                                    ),
                                                    "submitter_id": (
                                                        f"{sample_id}-R"
                                                    ),
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
        [hit("P1", "P1-01A", "F1"), hit("P2", "P2-01A", "F2")],
        None,
        sample_type_priority=["Primary Tumor"],
    )

    assert [row["patient_id"] for row in selected] == ["P1", "P2"]
    assert summary["survival_filter_applied"] is False
    assert summary["survival_expression_overlap"] is None


def test_central_v2_builder_keeps_endpoint_incomplete_samples(
    tmp_path, monkeypatch
):
    def materialize_source(spec, source_dir):
        patients = source_dir / "patients.tsv"
        samples = source_dir / "samples.tsv"
        expression = source_dir / "expression.tsv"
        license_path = source_dir / "LICENSE"
        patient_ids = [f"P{index:02d}" for index in range(10)]
        sample_ids = [f"S{index:02d}" for index in range(10)]
        _write_tsv(
            patients,
            ["PATIENT_ID", "OS_DAYS", "OS_STATUS"],
            [
                {
                    "PATIENT_ID": patient_id,
                    "OS_DAYS": 100 + index if index < 4 else "",
                    "OS_STATUS": (
                        "1:DECEASED" if index < 2 else "0:CENSORED"
                    )
                    if index < 4
                    else "",
                }
                for index, patient_id in enumerate(patient_ids)
            ],
        )
        _write_tsv(
            samples,
            ["SAMPLE_ID", "PATIENT_ID", "SAMPLE_TYPE"],
            [
                {
                    "SAMPLE_ID": sample_id,
                    "PATIENT_ID": patient_id,
                    "SAMPLE_TYPE": "Primary Tumor",
                }
                for sample_id, patient_id in zip(
                    sample_ids, patient_ids, strict=True
                )
            ],
        )
        with expression.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
            writer.writerow(["Hugo_Symbol", *sample_ids])
            for index in range(10_000):
                writer.writerow(
                    [f"GENE{index}", *[index + sample for sample in range(10)]]
                )
        license_path.write_text("Fixture license\n", encoding="utf-8")
        return (
            {
                "patients": patients,
                "samples": samples,
                "expression": expression,
                "license": license_path,
            },
            "a" * 40,
            "2026-08-20T00:00:00Z",
            {},
        )

    monkeypatch.setattr(
        cbioportal,
        "materialize_cbioportal_api_source",
        materialize_source,
    )
    spec = {
        "schema_version": STUDY_SPEC_SCHEMA_VERSION_V2,
        "dataset": {
            "id": "builder-v2-fixture",
            "cancer_code": "SKCM",
            "name": "Builder v2 fixture",
            "source_provider": "fixture",
            "source_accession": "FIXTURE-V2",
            "source_url": "https://example.test/fixture-v2",
            "assay": "bulk_rna_seq",
            "independence_status": "verified_external",
            "license_id": "LicenseRef-Fixture",
            "license_url": "https://example.test/license",
            "redistribution_allowed": True,
        },
        "source": {"provider": "cbioportal_api"},
        "samples": {
            "sample_type_column": "SAMPLE_TYPE",
            "sample_role": "RNA-seq tumor sample",
            "selection_rank": 0,
        },
        "expression": {
            "feature_id_type": "provided_hugo_symbol",
            "feature_column_count": 1,
            "layer_id": "expression",
            "label": "Expression",
            "source_unit": "TPM",
            "analysis_unit": "TPM",
            "transform": "identity",
            "mapping_source": "source_hugo_symbol",
        },
        "endpoints": [
            {
                "endpoint_id": "OS",
                "label": "Overall survival",
                "time_origin": "Diagnosis",
                "event_definition": "Death from any cause",
                "time_column": "OS_DAYS",
                "event_column": "OS_STATUS",
                "time_unit": "days",
            }
        ],
    }
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(json.dumps(spec), encoding="utf-8")

    manifest = cbioportal.build_cbioportal_bundle(
        spec_path, tmp_path / "bundle"
    )
    validation = importer.validate_bundle(tmp_path / "bundle")

    assert manifest["schema_version"] == BUNDLE_SCHEMA_VERSION_V2
    assert manifest["build"]["eligible_expression_samples"] == 10
    assert manifest["build"]["endpoint_complete_expression_samples"] == 4
    assert validation["qc"]["status"] == "passed"
    assert validation["qc"]["molecular_population"]["patients"] == 10
    assert validation["qc"]["endpoints"]["OS"]["patients"] == 4
