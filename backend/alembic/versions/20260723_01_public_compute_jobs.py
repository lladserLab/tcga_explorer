"""Add persistent public compute jobs.

Revision ID: 20260723_01
Revises:
Create Date: 2026-07-23
"""

from alembic import op
import sqlalchemy as sa


revision = "20260723_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("compute_jobs"):
        op.create_table(
            "compute_jobs",
            sa.Column("id", sa.String(length=64), nullable=False),
            sa.Column("kind", sa.String(length=32), nullable=False),
            sa.Column("params_hash", sa.String(length=64), nullable=False),
            sa.Column("client_key_hash", sa.String(length=64), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("request_payload", sa.JSON(), nullable=False),
            sa.Column("result_json", sa.JSON(), nullable=True),
            sa.Column("result_id", sa.String(length=64), nullable=True),
            sa.Column("error_json", sa.JSON(), nullable=True),
            sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("cached", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("started_at", sa.DateTime(), nullable=True),
            sa.Column("heartbeat_at", sa.DateTime(), nullable=True),
            sa.Column("completed_at", sa.DateTime(), nullable=True),
            sa.Column("expires_at", sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("kind", "params_hash", name="uq_compute_job_kind_params_hash"),
        )

    existing_indexes = {index["name"] for index in sa.inspect(bind).get_indexes("compute_jobs")}
    for name, columns in [
        ("ix_compute_jobs_kind", ["kind"]),
        ("ix_compute_jobs_params_hash", ["params_hash"]),
        ("ix_compute_jobs_client_key_hash", ["client_key_hash"]),
        ("ix_compute_jobs_status", ["status"]),
        ("ix_compute_jobs_result_id", ["result_id"]),
        ("ix_compute_jobs_created_at", ["created_at"]),
        ("ix_compute_jobs_heartbeat_at", ["heartbeat_at"]),
        ("ix_compute_jobs_expires_at", ["expires_at"]),
    ]:
        if name not in existing_indexes:
            op.create_index(name, "compute_jobs", columns, unique=False)


def downgrade() -> None:
    op.drop_table("compute_jobs")
