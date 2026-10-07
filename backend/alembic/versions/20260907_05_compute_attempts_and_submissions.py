"""Fence compute attempts and retain individual quota submissions.

Revision ID: 20260907_05
Revises: 20260810_04
"""
from datetime import datetime, timedelta, timezone

from alembic import op
import sqlalchemy as sa

revision = "20260907_05"
down_revision = "20260810_04"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    columns = {c["name"] for c in sa.inspect(bind).get_columns("compute_jobs")}
    if "attempt_token" not in columns:
        op.add_column("compute_jobs", sa.Column("attempt_token", sa.String(32)))
    # create_all may already have created this table on a fresh deployment.
    if not sa.inspect(bind).has_table("compute_submissions"):
        op.create_table(
            "compute_submissions",
            sa.Column("id", sa.String(80), primary_key=True),
            sa.Column("client_key_hash", sa.String(64), nullable=False),
            sa.Column("kind", sa.String(32), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
    indexes = {i["name"] for i in sa.inspect(bind).get_indexes("compute_submissions")}
    for name, fields in [
        ("ix_compute_submissions_client_kind_created", ["client_key_hash", "kind", "created_at"]),
        ("ix_compute_submissions_created_at", ["created_at"]),
    ]:
        if name not in indexes:
            op.create_index(name, "compute_submissions", fields)
    # Preserve the observable portion of the current window. Earlier retries
    # were overwritten by the old implementation and cannot be reconstructed.
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=1)
    bind.execute(sa.text("""
        INSERT INTO compute_submissions (id, client_key_hash, kind, created_at)
        SELECT 'legacy-' || j.id, j.client_key_hash, j.kind, j.created_at
        FROM compute_jobs j WHERE j.created_at >= :cutoff
        AND NOT EXISTS (SELECT 1 FROM compute_submissions s WHERE s.id = 'legacy-' || j.id)
    """), {"cutoff": cutoff})


def downgrade() -> None:
    op.drop_table("compute_submissions")
    op.drop_column("compute_jobs", "attempt_token")
