import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.main import _compute_dataset_summary, pancancer_cohorts
from app.database import Base
from app.models import Cohort
from app.schemas import PanCancerSurvivalRequest


@pytest.fixture()
def cohort_db():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Cohort.__table__.create(engine)
    with Session(engine) as db:
        db.add_all([
            Cohort(id="EXT-ALCL", data_path="external", status="external_only"),
            Cohort(id="TCGA-KIRC", data_path="tcga-kirc", status="ready"),
            Cohort(id="TCGA-LUAD", data_path="tcga-luad", status="ready"),
        ])
        db.commit()
        yield db
    engine.dispose()


def test_default_tcga_reference_does_not_attempt_external_only_categories(cohort_db):
    rows = pancancer_cohorts(cohort_db, PanCancerSurvivalRequest(gene_symbol="CA9"))
    assert [row.id for row in rows] == ["TCGA-KIRC", "TCGA-LUAD"]


@pytest.mark.parametrize("selection", [{"cohorts": ["EXT-ALCL"]}, {"index_cohort": "EXT-ALCL"}])
def test_external_categories_require_the_separate_hierarchical_mode(cohort_db, selection):
    with pytest.raises(HTTPException) as raised:
        pancancer_cohorts(cohort_db, PanCancerSurvivalRequest(gene_symbol="CA9", **selection))
    assert raised.value.status_code == 400


def test_unknown_tcga_cohort_still_reports_not_found(cohort_db):
    with pytest.raises(HTTPException) as raised:
        pancancer_cohorts(cohort_db, PanCancerSurvivalRequest(gene_symbol="CA9", cohorts=["TCGA-NONE"]))
    assert raised.value.status_code == 404


def test_tcga_dataset_summary_excludes_external_only_categories(monkeypatch):
    import app.main as main
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    monkeypatch.setattr(main, "load_cache_manifest", lambda _: {})
    monkeypatch.setattr(main, "dataset_dates", lambda *_: {})
    monkeypatch.setattr(main, "data_sync_summary", lambda *_: {})
    monkeypatch.setattr(main, "biological_annotations", lambda *_: {})
    with Session(engine) as db:
        db.add_all([
            Cohort(id="EXT-ALCL", data_path="external", n_genes=0),
            Cohort(id="TCGA-KIRC", data_path="kirc", n_genes=18000),
            Cohort(id="TCGA-LUAD", data_path="luad", n_genes=18000),
        ])
        db.commit()
        summary = _compute_dataset_summary(db)
        assert summary["totals"]["cohorts"] == 2
        assert summary["totals"]["genes_per_cohort"] == 18000
        assert {c["id"] for c in summary["cohorts"]} == {"TCGA-KIRC", "TCGA-LUAD"}
        assert len(summary["endpoint_coverage"]) == 8
        assert all(row["cohort"].startswith("TCGA-") for row in summary["endpoint_coverage"])
        with pytest.raises(HTTPException) as raised:
            _compute_dataset_summary(db, "EXT-ALCL")
        assert raised.value.status_code == 400
        assert raised.value.detail["code"] == "DATASET_REQUIRED"
    engine.dispose()
