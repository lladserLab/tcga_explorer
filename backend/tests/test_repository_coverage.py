from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.main import build_repository_coverage, health, public_health
from app.models import CancerType, Cohort, RepositoryDataset, RepositoryRelease


def _dataset(
    dataset_id: str,
    cancer_code: str,
    release_id: str,
    *,
    status: str = "available",
    visibility: str = "public",
) -> RepositoryDataset:
    return RepositoryDataset(
        id=dataset_id,
        cancer_code=cancer_code,
        name=dataset_id,
        description=None,
        cohort_context="Independent fixture cohort",
        source_provider="fixture",
        source_accession=dataset_id,
        source_url="https://example.org/fixture",
        publication_citation=None,
        publication_id=None,
        organism="Homo sapiens",
        assay="bulk_rna_seq",
        independence_status="independent",
        license_id="CC0-1.0",
        license_url=None,
        redistribution_allowed=True,
        status=status,
        visibility=visibility,
        active_release_id=release_id,
        metadata_json={},
    )


def _release(
    release_id: str,
    dataset_id: str,
    *,
    version: str,
    patient_count: int,
    sample_count: int,
) -> RepositoryRelease:
    return RepositoryRelease(
        id=release_id,
        dataset_id=dataset_id,
        version=version,
        status="published",
        manifest_hash=f"manifest-{release_id}",
        manifest_path=f"/{release_id}/manifest.json",
        repository_path=f"/{release_id}",
        source_snapshot=f"snapshot-{release_id}",
        patient_count=patient_count,
        sample_count=sample_count,
        gene_count=1000,
        qc_status="passed",
        qc_json={},
    )


def _coverage_session():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    db = factory()
    db.add_all(
        [
            CancerType(
                code="BRCA",
                tcga_cohort="TCGA-BRCA",
                name="Breast invasive carcinoma",
                sort_order=0,
                coverage_status="available",
            ),
            CancerType(
                code="LUAD",
                tcga_cohort="TCGA-LUAD",
                name="Lung adenocarcinoma",
                sort_order=1,
                coverage_status="available",
            ),
            CancerType(
                code="GBC",
                tcga_cohort="EXT-GBC",
                name="Gallbladder cancer",
                sort_order=2,
                coverage_status="available",
            ),
            CancerType(
                code="PAAD",
                tcga_cohort="TCGA-PAAD",
                name="Pancreatic adenocarcinoma",
                sort_order=3,
                coverage_status="evidence_gap",
            ),
            Cohort(
                id="TCGA-BRCA",
                status="ready",
                data_path="/tcga/brca",
            ),
            Cohort(
                id="TCGA-LUAD",
                status=None,
                data_path="/tcga/luad",
            ),
            Cohort(
                id="EXT-GBC",
                status="external_only",
                data_path="external_repository",
            ),
        ]
    )
    db.add_all(
        [
            _dataset("public-brca", "BRCA", "public-brca-v2"),
            _dataset("public-gbc", "GBC", "public-gbc-v1"),
            _dataset(
                "private-brca",
                "BRCA",
                "private-brca-v1",
                visibility="private",
            ),
            _dataset(
                "staged-luad",
                "LUAD",
                "staged-luad-v1",
                status="staged",
            ),
        ]
    )
    db.add_all(
        [
            _release(
                "public-brca-v1",
                "public-brca",
                version="v1",
                patient_count=900,
                sample_count=950,
            ),
            _release(
                "public-brca-v2",
                "public-brca",
                version="v2",
                patient_count=100,
                sample_count=120,
            ),
            _release(
                "public-gbc-v1",
                "public-gbc",
                version="v1",
                patient_count=40,
                sample_count=42,
            ),
            _release(
                "private-brca-v1",
                "private-brca",
                version="v1",
                patient_count=800,
                sample_count=810,
            ),
            _release(
                "staged-luad-v1",
                "staged-luad",
                version="v1",
                patient_count=700,
                sample_count=720,
            ),
        ]
    )
    db.commit()
    return db


def test_repository_coverage_sums_only_active_public_available_releases():
    db = _coverage_session()
    try:
        coverage = build_repository_coverage(db, include_search=False)
    finally:
        db.close()

    assert coverage["schema_version"] == "tcga-trace-repository-coverage-v2"
    assert coverage["datasets"] == 2
    assert coverage["patient_records_across_active_releases"] == 140
    assert coverage["rna_samples_across_active_releases"] == 162


def test_repository_coverage_counts_union_of_tcga_and_external_cancer_types():
    db = _coverage_session()
    try:
        coverage = build_repository_coverage(db, include_search=False)
    finally:
        db.close()

    # BRCA and LUAD are represented by TCGA; GBC is represented by an
    # available external release. PAAD has neither in this fixture.
    assert coverage["represented_cancer_types"] == 3


def test_health_contracts_expose_release_record_semantics():
    db = _coverage_session()
    try:
        legacy_payload = health(db)
        public_payload = public_health(db).model_dump()
    finally:
        db.close()

    expected = {
        "patient_records_across_active_releases": 140,
        "rna_samples_across_active_releases": 162,
        "represented_cancer_types": 3,
    }
    for payload in (legacy_payload, public_payload):
        repository = payload["external_repository"]
        for field, value in expected.items():
            assert repository[field] == value
