"""Add curated external RNA-seq repository.

Revision ID: 20260726_02
Revises: 20260723_01
Create Date: 2026-07-26
"""

from alembic import op
import sqlalchemy as sa


revision = "20260726_02"
down_revision = "20260723_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "cancer_types" not in tables:
        op.create_table(
            "cancer_types",
            sa.Column("code", sa.String(8), primary_key=True),
            sa.Column("tcga_cohort", sa.String(16), nullable=False, unique=True),
            sa.Column("name", sa.Text(), nullable=False),
            sa.Column("primary_site", sa.Text()),
            sa.Column("sort_order", sa.Integer(), nullable=False),
            sa.Column("coverage_status", sa.String(32), nullable=False),
            sa.Column("coverage_metadata", sa.JSON()),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_cancer_types_tcga_cohort", "cancer_types", ["tcga_cohort"])
        op.create_index("ix_cancer_types_coverage_status", "cancer_types", ["coverage_status"])

    if "repository_datasets" not in tables:
        op.create_table(
            "repository_datasets",
            sa.Column("id", sa.String(128), primary_key=True),
            sa.Column("cancer_code", sa.String(8), sa.ForeignKey("cancer_types.code", ondelete="RESTRICT"), nullable=False),
            sa.Column("name", sa.Text(), nullable=False),
            sa.Column("description", sa.Text()),
            sa.Column("cohort_context", sa.Text()),
            sa.Column("source_provider", sa.String(64), nullable=False),
            sa.Column("source_accession", sa.String(128), nullable=False),
            sa.Column("source_url", sa.Text(), nullable=False),
            sa.Column("publication_citation", sa.Text()),
            sa.Column("publication_id", sa.String(128)),
            sa.Column("organism", sa.String(64), nullable=False),
            sa.Column("assay", sa.String(64), nullable=False),
            sa.Column("independence_status", sa.String(32), nullable=False),
            sa.Column("license_id", sa.String(64)),
            sa.Column("license_url", sa.Text()),
            sa.Column("redistribution_allowed", sa.Boolean(), nullable=False),
            sa.Column("status", sa.String(32), nullable=False),
            sa.Column("active_release_id", sa.String(128)),
            sa.Column("metadata_json", sa.JSON()),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
        for name, columns in [
            ("ix_repository_datasets_cancer_code", ["cancer_code"]),
            ("ix_repository_datasets_source_provider", ["source_provider"]),
            ("ix_repository_datasets_source_accession", ["source_accession"]),
            ("ix_repository_datasets_independence_status", ["independence_status"]),
            ("ix_repository_datasets_status", ["status"]),
            ("ix_repository_datasets_active_release_id", ["active_release_id"]),
        ]:
            op.create_index(name, "repository_datasets", columns)

    if "repository_releases" not in tables:
        op.create_table(
            "repository_releases",
            sa.Column("id", sa.String(128), primary_key=True),
            sa.Column("dataset_id", sa.String(128), sa.ForeignKey("repository_datasets.id", ondelete="CASCADE"), nullable=False),
            sa.Column("version", sa.String(128), nullable=False),
            sa.Column("status", sa.String(32), nullable=False),
            sa.Column("manifest_hash", sa.String(64), nullable=False, unique=True),
            sa.Column("manifest_path", sa.Text(), nullable=False),
            sa.Column("repository_path", sa.Text(), nullable=False),
            sa.Column("source_snapshot", sa.String(256)),
            sa.Column("source_retrieved_at", sa.DateTime()),
            sa.Column("patient_count", sa.Integer(), nullable=False),
            sa.Column("sample_count", sa.Integer(), nullable=False),
            sa.Column("gene_count", sa.Integer(), nullable=False),
            sa.Column("qc_status", sa.String(32), nullable=False),
            sa.Column("qc_json", sa.JSON()),
            sa.Column("published_at", sa.DateTime()),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("dataset_id", "version", name="uq_repository_release_dataset_version"),
        )
        for name, columns in [
            ("ix_repository_releases_dataset_id", ["dataset_id"]),
            ("ix_repository_releases_status", ["status"]),
            ("ix_repository_releases_manifest_hash", ["manifest_hash"]),
            ("ix_repository_releases_qc_status", ["qc_status"]),
        ]:
            op.create_index(name, "repository_releases", columns)

    _create_child_tables()

    analysis_columns = {column["name"] for column in sa.inspect(bind).get_columns("analysis_jobs")}
    if "dataset_id" not in analysis_columns:
        op.add_column("analysis_jobs", sa.Column("dataset_id", sa.String(128)))
        op.create_index("ix_analysis_jobs_dataset_id", "analysis_jobs", ["dataset_id"])
    if "dataset_release_id" not in analysis_columns:
        op.add_column("analysis_jobs", sa.Column("dataset_release_id", sa.String(128)))
        op.create_index(
            "ix_analysis_jobs_dataset_release_id",
            "analysis_jobs",
            ["dataset_release_id"],
        )


def _create_child_tables() -> None:
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())
    if "repository_expression_layers" not in tables:
        op.create_table(
            "repository_expression_layers",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("release_id", sa.String(128), sa.ForeignKey("repository_releases.id", ondelete="CASCADE"), nullable=False),
            sa.Column("layer_id", sa.String(64), nullable=False),
            sa.Column("label", sa.Text(), nullable=False),
            sa.Column("source_unit", sa.String(64), nullable=False),
            sa.Column("analysis_unit", sa.String(128), nullable=False),
            sa.Column("transform", sa.String(64), nullable=False),
            sa.Column("matrix_path", sa.Text(), nullable=False),
            sa.Column("matrix_sha256", sa.String(64), nullable=False),
            sa.Column("metadata_path", sa.Text(), nullable=False),
            sa.Column("gene_count", sa.Integer(), nullable=False),
            sa.Column("sample_count", sa.Integer(), nullable=False),
            sa.Column("is_default", sa.Boolean(), nullable=False),
            sa.Column("downloadable", sa.Boolean(), nullable=False),
            sa.Column("metadata_json", sa.JSON()),
            sa.UniqueConstraint("release_id", "layer_id", name="uq_repository_expression_layer_release_id"),
        )
        op.create_index("ix_repository_expression_layers_release_id", "repository_expression_layers", ["release_id"])
        op.create_index("ix_repository_expression_layers_layer_id", "repository_expression_layers", ["layer_id"])

    definitions = [
        (
            "repository_patients",
            [
                sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
                sa.Column("release_id", sa.String(128), sa.ForeignKey("repository_releases.id", ondelete="CASCADE"), nullable=False),
                sa.Column("patient_id", sa.String(128), nullable=False),
                sa.Column("stage", sa.String(128)),
                sa.Column("grade", sa.String(128)),
                sa.Column("gender", sa.String(64)),
                sa.Column("race", sa.String(128)),
                sa.Column("age_at_index", sa.Float()),
                sa.Column("raw_metadata", sa.JSON()),
                sa.UniqueConstraint("release_id", "patient_id", name="uq_repository_patient_release_id"),
            ],
        ),
        (
            "repository_samples",
            [
                sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
                sa.Column("release_id", sa.String(128), sa.ForeignKey("repository_releases.id", ondelete="CASCADE"), nullable=False),
                sa.Column("sample_id", sa.String(128), nullable=False),
                sa.Column("patient_id", sa.String(128), nullable=False),
                sa.Column("sample_type", sa.String(128)),
                sa.Column("sample_role", sa.String(128)),
                sa.Column("selection_rank", sa.Integer(), nullable=False),
                sa.Column("raw_metadata", sa.JSON()),
                sa.UniqueConstraint("release_id", "sample_id", name="uq_repository_sample_release_id"),
            ],
        ),
        (
            "repository_endpoint_definitions",
            [
                sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
                sa.Column("release_id", sa.String(128), sa.ForeignKey("repository_releases.id", ondelete="CASCADE"), nullable=False),
                sa.Column("endpoint_id", sa.String(32), nullable=False),
                sa.Column("standard_code", sa.String(32)),
                sa.Column("label", sa.Text(), nullable=False),
                sa.Column("time_origin", sa.Text(), nullable=False),
                sa.Column("event_definition", sa.Text(), nullable=False),
                sa.Column("source_time_column", sa.String(128), nullable=False),
                sa.Column("source_event_column", sa.String(128), nullable=False),
                sa.Column("source_time_unit", sa.String(32), nullable=False),
                sa.Column("patient_count", sa.Integer(), nullable=False),
                sa.Column("event_count", sa.Integer(), nullable=False),
                sa.Column("available", sa.Boolean(), nullable=False),
                sa.Column("reason", sa.Text()),
                sa.Column("metadata_json", sa.JSON()),
                sa.UniqueConstraint("release_id", "endpoint_id", name="uq_repository_endpoint_definition_release_id"),
            ],
        ),
        (
            "repository_endpoint_values",
            [
                sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
                sa.Column("release_id", sa.String(128), sa.ForeignKey("repository_releases.id", ondelete="CASCADE"), nullable=False),
                sa.Column("endpoint_id", sa.String(32), nullable=False),
                sa.Column("patient_id", sa.String(128), nullable=False),
                sa.Column("time_days", sa.Float(), nullable=False),
                sa.Column("event", sa.Integer(), nullable=False),
                sa.Column("raw_time", sa.Float()),
                sa.Column("raw_event", sa.String(128)),
                sa.Column("raw_metadata", sa.JSON()),
                sa.UniqueConstraint("release_id", "endpoint_id", "patient_id", name="uq_repository_endpoint_value_release_id"),
            ],
        ),
    ]
    for table_name, columns in definitions:
        if table_name not in tables:
            op.create_table(table_name, *columns)

    if "repository_genes" not in tables:
        op.create_table(
            "repository_genes",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("expression_layer_id", sa.Integer(), sa.ForeignKey("repository_expression_layers.id", ondelete="CASCADE"), nullable=False),
            sa.Column("gene_symbol", sa.String(128), nullable=False),
            sa.Column("original_gene_id", sa.String(128), nullable=False),
            sa.Column("row_number", sa.Integer(), nullable=False),
            sa.Column("mapping_source", sa.String(128), nullable=False),
            sa.UniqueConstraint("expression_layer_id", "gene_symbol", name="uq_repository_gene_expression_layer_symbol"),
        )

    for table_name, columns in [
        ("repository_patients", ["release_id", "patient_id", "stage", "grade", "gender", "race"]),
        ("repository_samples", ["release_id", "sample_id", "patient_id", "sample_type"]),
        ("repository_endpoint_definitions", ["release_id", "endpoint_id", "standard_code", "available"]),
        ("repository_endpoint_values", ["release_id", "endpoint_id", "patient_id", "time_days", "event"]),
        ("repository_genes", ["expression_layer_id", "gene_symbol", "original_gene_id"]),
    ]:
        existing = {index["name"] for index in sa.inspect(bind).get_indexes(table_name)}
        for column in columns:
            name = f"ix_{table_name}_{column}"
            if name not in existing:
                op.create_index(name, table_name, [column])


def downgrade() -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("analysis_jobs")}
    if "dataset_release_id" in columns:
        op.drop_index("ix_analysis_jobs_dataset_release_id", table_name="analysis_jobs")
        op.drop_column("analysis_jobs", "dataset_release_id")
    if "dataset_id" in columns:
        op.drop_index("ix_analysis_jobs_dataset_id", table_name="analysis_jobs")
        op.drop_column("analysis_jobs", "dataset_id")
    for table in [
        "repository_genes",
        "repository_endpoint_values",
        "repository_endpoint_definitions",
        "repository_samples",
        "repository_patients",
        "repository_expression_layers",
        "repository_releases",
        "repository_datasets",
        "cancer_types",
    ]:
        op.drop_table(table)
