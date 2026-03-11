"""add created_at composite indexes for recency queries

Revision ID: 20250827_idx_created
Revises: 20250827_fix_trg
Create Date: 2025-08-27 14:25:00.000000

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20250827_idx_created"
down_revision = "20250827_fix_trg"
branch_labels = None
depends_on = None


def _index_exists(conn, table: str, index_name: str) -> bool:
    res = conn.execute(
        sa.text(
            """
            SELECT 1
            FROM pg_indexes
            WHERE schemaname = 'public'
              AND tablename = :table
              AND indexname = :index
            """
        ),
        {"table": table, "index": index_name},
    ).scalar()
    return bool(res)


def upgrade() -> None:
    bind = op.get_bind()

    # jobs: index recent jobs per user
    idx_jobs_user_created = "ix_jobs_user_created_at_desc"
    if not _index_exists(bind, "jobs", idx_jobs_user_created):
        op.create_index(
            idx_jobs_user_created,
            "jobs",
            ["user_id", sa.text("created_at DESC")],
            unique=False,
        )

    # job_outputs: index recent outputs per job
    idx_outputs_job_created = "ix_job_outputs_job_created_at_desc"
    if not _index_exists(bind, "job_outputs", idx_outputs_job_created):
        op.create_index(
            idx_outputs_job_created,
            "job_outputs",
            ["job_id", sa.text("created_at DESC")],
            unique=False,
        )


def downgrade() -> None:
    bind = op.get_bind()

    for table, idx in (
        ("job_outputs", "ix_job_outputs_job_created_at_desc"),
        ("jobs", "ix_jobs_user_created_at_desc"),
    ):
        if _index_exists(bind, table, idx):
            op.drop_index(idx, table_name=table)
