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


class AnalysisJob(Base):
    __tablename__ = "analysis_jobs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    params_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    cohort: Mapped[str] = mapped_column(String(16), index=True)
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
