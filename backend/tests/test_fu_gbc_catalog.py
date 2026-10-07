from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.cache_warmup import warm_startup_cache
from app.config import Settings
from app.models import CancerType, Cohort
from app.pancancer_study_universes import load_study_universe_registry
from app.repository.catalog import sync_repository_catalog


def test_all_external_only_disease_cohorts_are_registered():
    registry = Path(__file__).resolve().parents[2] / "repository_registry"
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine) as db:
        sync_repository_catalog(db, registry)
        expected = {
            "GBC": ("FU-GBC", 135, 15926),
            "CLL": ("EXT-CLL", 566, 54994),
            "NBL": ("EXT-NBL", 498, 23146),
            "PLGG": ("EXT-PLGG", 62, 18205),
            "SCLC": ("EXT-SCLC", 39, 51131),
        }
        for cancer_code, (cohort_id, patients, genes) in expected.items():
            cancer = db.get(CancerType, cancer_code)
            cohort = db.get(Cohort, cohort_id)
            assert cancer is not None
            assert cancer.tcga_cohort == cohort_id
            assert cohort is not None
            assert cohort.status == "external_only"
            assert cohort.n_patients_paired == patients
            assert cohort.n_genes == genes


def test_external_only_gbc_cohort_is_registered(tmp_path):
    registry = tmp_path / "registry"
    registry.mkdir()
    (registry / "cancer_types.json").write_text(
        json.dumps(
            {
                "cancer_types": [
                    {
                        "code": "GBC",
                        "tcga_cohort": "FU-GBC",
                        "name": "Gallbladder cancer",
                        "primary_site": "Gallbladder",
                        "cohort_kind": "external_only",
                        "summary": {
                            "samples": 201,
                            "patients": 135,
                            "primary_tumor_samples": 135,
                            "adjacent_non_tumor_samples": 66,
                            "genes": 15926,
                        },
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (registry / "coverage.json").write_text(
        json.dumps(
            {
                "cancers": [
                    {"code": "GBC", "status": "candidate_validated"}
                ]
            }
        ),
        encoding="utf-8",
    )

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        result = sync_repository_catalog(db, registry)
        cancer = db.get(CancerType, "GBC")
        cohort = db.get(Cohort, "FU-GBC")

        assert result["cancer_types"] == 1
        assert cancer is not None
        assert cancer.tcga_cohort == "FU-GBC"
        assert cohort is not None
        assert cohort.status == "external_only"
        assert cohort.n_patients_paired == 135
        assert cohort.n_primary_tumor == 135
        assert cohort.n_solid_normal == 66
        assert cohort.n_genes == 15926


def test_external_only_cohort_is_not_sent_to_tcga_cache_warmup(tmp_path):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(
            Cohort(
                id="FU-GBC",
                disease_type="Gallbladder cancer",
                primary_site="Gallbladder",
                n_samples_paired=201,
                n_patients_paired=135,
                n_primary_tumor=135,
                n_solid_normal=66,
                n_other_samples=0,
                n_genes=15926,
                design_formula="~ tissue_type",
                status="external_only",
                data_path="external_repository",
            )
        )
        db.commit()
        report = warm_startup_cache(
            db,
            Settings(
                tcga_data_dir=tmp_path / "tcga",
                derived_expression_dir=tmp_path / "derived",
                preload_cache_strict=True,
            ),
        )

        assert report["status"] == "ready"
        assert report["cohort_count"] == 0
        assert report["skipped_external_cohorts"] == ["FU-GBC"]
        assert report["errors"] == []


def test_external_only_cohort_is_not_misclassified_as_tcga():
    registry = load_study_universe_registry()

    assert "FU-GBC" not in {
        definition.universe_id for definition in registry.tcga_definitions
    }
    assert len(registry.tcga_definitions) == 33


@pytest.mark.parametrize("cohort_id", ["FU-GBC", "EXT-CLL"])
@pytest.mark.parametrize("endpoint", ["search_genes", "resolve_gene", "public_cohort_genes", "public_resolve_gene"])
def test_tcga_gene_routes_explain_external_dataset_selection(cohort_id, endpoint, monkeypatch):
    from app import main

    def unexpected_tcga_lookup(*args, **kwargs):
        pytest.fail("External-only cohorts must never load a TCGA count matrix")

    monkeypatch.setattr(main, "ensure_gene_index", unexpected_tcga_lookup)
    monkeypatch.setattr(main, "resolve_gene_symbol", unexpected_tcga_lookup)
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        sync_repository_catalog(db, Path(__file__).resolve().parents[2] / "repository_registry")
        with pytest.raises(HTTPException) as error:
            getattr(main, endpoint)(cohort_id, db, query="TP53")
        assert error.value.status_code == 422
        assert error.value.detail["code"] == "DATASET_REQUIRED"
        assert "/api/v1/datasets/{dataset_id}/genes" in error.value.detail["message"]


@pytest.mark.parametrize("cohort_id", ["FU-GBC", "EXT-CLL"])
@pytest.mark.parametrize("endpoint,resource", [
    ("cohort_endpoint_options", "endpoints"),
    ("public_cohort_endpoints", "endpoints"),
    ("filter_options", "filters"),
    ("public_cohort_filters", "filters"),
])
def test_external_metadata_requires_a_dataset(cohort_id, endpoint, resource):
    from app import main

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        sync_repository_catalog(db, Path(__file__).resolve().parents[2] / "repository_registry")
        with pytest.raises(HTTPException) as error:
            getattr(main, endpoint)(cohort_id, db)
        assert error.value.status_code == 422
        assert error.value.detail["code"] == "DATASET_REQUIRED"
        assert f"/api/v1/datasets/{{dataset_id}}/{resource}" in error.value.detail["message"]
