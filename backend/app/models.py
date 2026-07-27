from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Cohort(Base):
    __tablename__ = "cohorts"

    id: Mapped[str] = mapped_column(String(16), primary_key=True)
    disease_type: Mapped[str | None] = mapped_column(Text)
    primary_site: Mapped[str | None] = mapped_column(Text)
    n_samples_paired: Mapped[int | None] = mapped_column(Integer)
    n_patients_paired: Mapped[int | None] = mapped_column(Integer)
    n_primary_tumor: Mapped[int | None] = mapped_column(Integer)
    n_solid_normal: Mapped[int | None] = mapped_column(Integer)
    n_other_samples: Mapped[int | None] = mapped_column(Integer)
    n_genes: Mapped[int | None] = mapped_column(Integer)
    design_formula: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str | None] = mapped_column(String(64))
    data_path: Mapped[str] = mapped_column(Text)
    imported_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    samples: Mapped[list["Sample"]] = relationship(back_populates="cohort_ref", cascade="all, delete-orphan")
    genes: Mapped[list["GeneIndex"]] = relationship(back_populates="cohort_ref", cascade="all, delete-orphan")


class Sample(Base):
    __tablename__ = "samples"
    __table_args__ = (UniqueConstraint("cohort", "barcode", name="uq_sample_cohort_barcode"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cohort: Mapped[str] = mapped_column(ForeignKey("cohorts.id", ondelete="CASCADE"), index=True)
    patient_id: Mapped[str] = mapped_column(String(32), index=True)
    barcode: Mapped[str] = mapped_column(String(128), index=True)
    sample_type: Mapped[str | None] = mapped_column(String(128), index=True)
    stage: Mapped[str | None] = mapped_column(String(128), index=True)
    grade: Mapped[str | None] = mapped_column(String(128), index=True)
    gender: Mapped[str | None] = mapped_column(String(64), index=True)
    race: Mapped[str | None] = mapped_column(String(128), index=True)
    age_at_index: Mapped[float | None] = mapped_column(Float)
    vital_status: Mapped[str | None] = mapped_column(String(64))
    os_time_days: Mapped[float | None] = mapped_column(Float, index=True)
    os_event: Mapped[int | None] = mapped_column(Integer, index=True)
    library_size: Mapped[float | None] = mapped_column(Float)
    raw_metadata: Mapped[dict | None] = mapped_column(JSON)

    cohort_ref: Mapped[Cohort] = relationship(back_populates="samples")


class GeneIndex(Base):
    __tablename__ = "gene_index"
    __table_args__ = (UniqueConstraint("cohort", "gene_symbol", name="uq_gene_cohort_symbol"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cohort: Mapped[str] = mapped_column(ForeignKey("cohorts.id", ondelete="CASCADE"), index=True)
    gene_symbol: Mapped[str] = mapped_column(String(128), index=True)
    row_number: Mapped[int] = mapped_column(Integer)

    cohort_ref: Mapped[Cohort] = relationship(back_populates="genes")


class DataSource(Base):
    __tablename__ = "data_sources"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    label: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(64), index=True)
    source_url: Mapped[str | None] = mapped_column(Text)
    source_path: Mapped[str | None] = mapped_column(Text)
    source_file_modified_at: Mapped[datetime | None] = mapped_column(DateTime)
    imported_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    metadata_json: Mapped[dict | None] = mapped_column(JSON)


class DataManifest(Base):
    __tablename__ = "data_manifests"
    __table_args__ = (UniqueConstraint("source_id", "manifest_hash", name="uq_data_manifest_source_hash"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_id: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(64), index=True, default="ready")
    manifest_hash: Mapped[str] = mapped_column(String(64), index=True)
    data_release: Mapped[str | None] = mapped_column(String(128))
    data_through_date: Mapped[datetime | None] = mapped_column(DateTime)
    file_count: Mapped[int | None] = mapped_column(Integer)
    manifest_path: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class DataSyncRun(Base):
    __tablename__ = "data_sync_runs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(64), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    changes_json: Mapped[dict | None] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[dict | None] = mapped_column(JSON)


class ClinicalEndpoint(Base):
    __tablename__ = "clinical_endpoints"
    __table_args__ = (
        UniqueConstraint("source_id", "patient_id", "endpoint", name="uq_clinical_endpoint_source_patient_endpoint"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("data_sources.id", ondelete="CASCADE"), index=True)
    cohort: Mapped[str] = mapped_column(String(16), index=True)
    patient_id: Mapped[str] = mapped_column(String(32), index=True)
    endpoint: Mapped[str] = mapped_column(String(16), index=True)
    time_days: Mapped[float] = mapped_column(Float, index=True)
    event: Mapped[int] = mapped_column(Integer, index=True)
    raw_metadata: Mapped[dict | None] = mapped_column(JSON)


class CancerType(Base):
    __tablename__ = "cancer_types"

    code: Mapped[str] = mapped_column(String(8), primary_key=True)
    tcga_cohort: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    name: Mapped[str] = mapped_column(Text)
    primary_site: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer)
    coverage_status: Mapped[str] = mapped_column(
        String(32), index=True, default="unsearched"
    )
    coverage_metadata: Mapped[dict | None] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class RepositoryDataset(Base):
    __tablename__ = "repository_datasets"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    cancer_code: Mapped[str] = mapped_column(
        ForeignKey("cancer_types.code", ondelete="RESTRICT"), index=True
    )
    name: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    cohort_context: Mapped[str | None] = mapped_column(Text)
    source_provider: Mapped[str] = mapped_column(String(64), index=True)
    source_accession: Mapped[str] = mapped_column(String(128), index=True)
    source_url: Mapped[str] = mapped_column(Text)
    publication_citation: Mapped[str | None] = mapped_column(Text)
    publication_id: Mapped[str | None] = mapped_column(String(128))
    organism: Mapped[str] = mapped_column(String(64), default="Homo sapiens")
    assay: Mapped[str] = mapped_column(String(64), default="bulk_rna_seq")
    independence_status: Mapped[str] = mapped_column(String(32), index=True)
    license_id: Mapped[str | None] = mapped_column(String(64))
    license_url: Mapped[str | None] = mapped_column(Text)
    redistribution_allowed: Mapped[bool] = mapped_column(
        Boolean, default=False
    )
    status: Mapped[str] = mapped_column(String(32), index=True, default="staged")
    active_release_id: Mapped[str | None] = mapped_column(String(128), index=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class RepositoryRelease(Base):
    __tablename__ = "repository_releases"
    __table_args__ = (
        UniqueConstraint(
            "dataset_id", "version", name="uq_repository_release_dataset_version"
        ),
    )

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    dataset_id: Mapped[str] = mapped_column(
        ForeignKey("repository_datasets.id", ondelete="CASCADE"), index=True
    )
    version: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(32), index=True, default="staged")
    manifest_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    manifest_path: Mapped[str] = mapped_column(Text)
    repository_path: Mapped[str] = mapped_column(Text)
    source_snapshot: Mapped[str | None] = mapped_column(String(256))
    source_retrieved_at: Mapped[datetime | None] = mapped_column(DateTime)
    patient_count: Mapped[int] = mapped_column(Integer, default=0)
    sample_count: Mapped[int] = mapped_column(Integer, default=0)
    gene_count: Mapped[int] = mapped_column(Integer, default=0)
    qc_status: Mapped[str] = mapped_column(String(32), index=True)
    qc_json: Mapped[dict | None] = mapped_column(JSON)
    published_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class RepositoryExpressionLayer(Base):
    __tablename__ = "repository_expression_layers"
    __table_args__ = (
        UniqueConstraint(
            "release_id",
            "layer_id",
            name="uq_repository_expression_layer_release_id",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    release_id: Mapped[str] = mapped_column(
        ForeignKey("repository_releases.id", ondelete="CASCADE"), index=True
    )
    layer_id: Mapped[str] = mapped_column(String(64), index=True)
    label: Mapped[str] = mapped_column(Text)
    source_unit: Mapped[str] = mapped_column(String(64))
    analysis_unit: Mapped[str] = mapped_column(String(128))
    transform: Mapped[str] = mapped_column(String(64))
    matrix_path: Mapped[str] = mapped_column(Text)
    matrix_sha256: Mapped[str] = mapped_column(String(64))
    metadata_path: Mapped[str] = mapped_column(Text)
    gene_count: Mapped[int] = mapped_column(Integer)
    sample_count: Mapped[int] = mapped_column(Integer)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    downloadable: Mapped[bool] = mapped_column(Boolean, default=False)
    metadata_json: Mapped[dict | None] = mapped_column(JSON)


class RepositoryPatient(Base):
    __tablename__ = "repository_patients"
    __table_args__ = (
        UniqueConstraint(
            "release_id", "patient_id", name="uq_repository_patient_release_id"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    release_id: Mapped[str] = mapped_column(
        ForeignKey("repository_releases.id", ondelete="CASCADE"), index=True
    )
    patient_id: Mapped[str] = mapped_column(String(128), index=True)
    stage: Mapped[str | None] = mapped_column(String(128), index=True)
    grade: Mapped[str | None] = mapped_column(String(128), index=True)
    gender: Mapped[str | None] = mapped_column(String(64), index=True)
    race: Mapped[str | None] = mapped_column(String(128), index=True)
    age_at_index: Mapped[float | None] = mapped_column(Float)
    raw_metadata: Mapped[dict | None] = mapped_column(JSON)


class RepositorySample(Base):
    __tablename__ = "repository_samples"
    __table_args__ = (
        UniqueConstraint(
            "release_id", "sample_id", name="uq_repository_sample_release_id"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    release_id: Mapped[str] = mapped_column(
        ForeignKey("repository_releases.id", ondelete="CASCADE"), index=True
    )
    sample_id: Mapped[str] = mapped_column(String(128), index=True)
    patient_id: Mapped[str] = mapped_column(String(128), index=True)
    sample_type: Mapped[str | None] = mapped_column(String(128), index=True)
    sample_role: Mapped[str | None] = mapped_column(String(128))
    selection_rank: Mapped[int] = mapped_column(Integer, default=0)
    raw_metadata: Mapped[dict | None] = mapped_column(JSON)


class RepositoryEndpointDefinition(Base):
    __tablename__ = "repository_endpoint_definitions"
    __table_args__ = (
        UniqueConstraint(
            "release_id",
            "endpoint_id",
            name="uq_repository_endpoint_definition_release_id",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    release_id: Mapped[str] = mapped_column(
        ForeignKey("repository_releases.id", ondelete="CASCADE"), index=True
    )
    endpoint_id: Mapped[str] = mapped_column(String(32), index=True)
    standard_code: Mapped[str | None] = mapped_column(String(32), index=True)
    label: Mapped[str] = mapped_column(Text)
    time_origin: Mapped[str] = mapped_column(Text)
    event_definition: Mapped[str] = mapped_column(Text)
    source_time_column: Mapped[str] = mapped_column(String(128))
    source_event_column: Mapped[str] = mapped_column(String(128))
    source_time_unit: Mapped[str] = mapped_column(String(32))
    patient_count: Mapped[int] = mapped_column(Integer)
    event_count: Mapped[int] = mapped_column(Integer)
    available: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    reason: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[dict | None] = mapped_column(JSON)


class RepositoryEndpointValue(Base):
    __tablename__ = "repository_endpoint_values"
    __table_args__ = (
        UniqueConstraint(
            "release_id",
            "endpoint_id",
            "patient_id",
            name="uq_repository_endpoint_value_release_id",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    release_id: Mapped[str] = mapped_column(
        ForeignKey("repository_releases.id", ondelete="CASCADE"), index=True
    )
    endpoint_id: Mapped[str] = mapped_column(String(32), index=True)
    patient_id: Mapped[str] = mapped_column(String(128), index=True)
    time_days: Mapped[float] = mapped_column(Float, index=True)
    event: Mapped[int] = mapped_column(Integer, index=True)
    raw_time: Mapped[float | None] = mapped_column(Float)
    raw_event: Mapped[str | None] = mapped_column(String(128))
    raw_metadata: Mapped[dict | None] = mapped_column(JSON)


class RepositoryGene(Base):
    __tablename__ = "repository_genes"
    __table_args__ = (
        UniqueConstraint(
            "expression_layer_id",
            "gene_symbol",
            name="uq_repository_gene_expression_layer_symbol",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    expression_layer_id: Mapped[int] = mapped_column(
        ForeignKey("repository_expression_layers.id", ondelete="CASCADE"),
        index=True,
    )
    gene_symbol: Mapped[str] = mapped_column(String(128), index=True)
    original_gene_id: Mapped[str] = mapped_column(String(128), index=True)
    row_number: Mapped[int] = mapped_column(Integer)
    mapping_source: Mapped[str] = mapped_column(String(128))


class AnalysisJob(Base):
    __tablename__ = "analysis_jobs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    params_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    cohort: Mapped[str] = mapped_column(String(16), index=True)
    dataset_id: Mapped[str | None] = mapped_column(String(128), index=True)
    dataset_release_id: Mapped[str | None] = mapped_column(String(128), index=True)
    gene_symbol: Mapped[str] = mapped_column(String(128), index=True)
    cutpoint_method: Mapped[str] = mapped_column(String(64))
    request_payload: Mapped[dict] = mapped_column(JSON)
    metrics: Mapped[dict | None] = mapped_column(JSON)
    warnings: Mapped[list[str] | None] = mapped_column(JSON)
    png_path: Mapped[str | None] = mapped_column(Text)
    svg_path: Mapped[str | None] = mapped_column(Text)
    csv_path: Mapped[str | None] = mapped_column(Text)
    json_path: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    cached: Mapped[bool] = mapped_column(Boolean, default=False)


class ComputeJob(Base):
    __tablename__ = "compute_jobs"
    __table_args__ = (UniqueConstraint("kind", "params_hash", name="uq_compute_job_kind_params_hash"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    kind: Mapped[str] = mapped_column(String(32), index=True)
    params_hash: Mapped[str] = mapped_column(String(64), index=True)
    client_key_hash: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), index=True, default="queued")
    request_payload: Mapped[dict] = mapped_column(JSON)
    result_json: Mapped[dict | None] = mapped_column(JSON)
    result_id: Mapped[str | None] = mapped_column(String(64), index=True)
    error_json: Mapped[dict | None] = mapped_column(JSON)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    cached: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)
