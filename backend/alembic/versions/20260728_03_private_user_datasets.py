"""Add temporary private user datasets.

Revision ID: 20260728_03
Revises: 20260726_02
Create Date: 2026-07-28
"""

from alembic import op
import sqlalchemy as sa


revision = "20260728_03"
down_revision = "20260726_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {
        column["name"]
        for column in inspector.get_columns("repository_datasets")
    }
    if "visibility" not in columns:
        op.add_column(
            "repository_datasets",
            sa.Column(
                "visibility",
                sa.String(16),
                nullable=False,
                server_default="public",
            ),
        )
        op.create_index(
            "ix_repository_datasets_visibility",
            "repository_datasets",
            ["visibility"],
        )
    if "owner_key_hash" not in columns:
        op.add_column(
            "repository_datasets",
            sa.Column("owner_key_hash", sa.String(64)),
        )
        op.create_index(
            "ix_repository_datasets_owner_key_hash",
            "repository_datasets",
            ["owner_key_hash"],
        )
    if "expires_at" not in columns:
        op.add_column(
            "repository_datasets",
            sa.Column("expires_at", sa.DateTime()),
        )
        op.create_index(
            "ix_repository_datasets_expires_at",
            "repository_datasets",
            ["expires_at"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    columns = {
        column["name"]
        for column in sa.inspect(bind).get_columns("repository_datasets")
    }
    if "expires_at" in columns:
        op.drop_index(
            "ix_repository_datasets_expires_at",
            table_name="repository_datasets",
        )
        op.drop_column("repository_datasets", "expires_at")
    if "owner_key_hash" in columns:
        op.drop_index(
            "ix_repository_datasets_owner_key_hash",
            table_name="repository_datasets",
        )
        op.drop_column("repository_datasets", "owner_key_hash")
    if "visibility" in columns:
        op.drop_index(
            "ix_repository_datasets_visibility",
            table_name="repository_datasets",
        )
        op.drop_column("repository_datasets", "visibility")
