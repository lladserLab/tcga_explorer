"""Add independent access tokens for private user datasets.

Revision ID: 20260810_04
Revises: 20260728_03
Create Date: 2026-08-10
"""

from alembic import op
import sqlalchemy as sa


revision = "20260810_04"
down_revision = "20260728_03"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {
        column["name"]
        for column in sa.inspect(op.get_bind()).get_columns(
            "repository_datasets"
        )
    }
    if "access_token_hash" not in columns:
        op.add_column(
            "repository_datasets",
            sa.Column("access_token_hash", sa.String(64)),
        )


def downgrade() -> None:
    columns = {
        column["name"]
        for column in sa.inspect(op.get_bind()).get_columns(
            "repository_datasets"
        )
    }
    if "access_token_hash" in columns:
        op.drop_column("repository_datasets", "access_token_hash")
