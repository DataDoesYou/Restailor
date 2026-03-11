"""add targeted perf indexes for active jobs and job_outputs fetches

Revision ID: 20250828_perf_idx
Revises: 20250827_idx_created
Create Date: 2025-08-28 10:30:00.000000

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20250828_perf_idx"
down_revision = "20250827_idx_created"
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

    # jobs: partial index for "active" (non-terminal) jobs per client_id used by the concurrency guard
    # Mirrors query shape: WHERE client_id = :client_id AND status NOT IN ('completed','failed')
    idx_active_jobs = "ix_jobs_client_active"
    if not _index_exists(bind, "jobs", idx_active_jobs):
        op.create_index(
            idx_active_jobs,
            "jobs",
            ["client_id"],
            unique=False,
            postgresql_where=sa.text("status NOT IN ('completed','failed')"),
        )

    # job_outputs: accelerate lookups by (job_id, type) ordered by created_at DESC
    # Common pattern when fetching latest output of a given type for a job
    idx_outputs_cover = "ix_job_outputs_job_type_created_at_desc"
    if not _index_exists(bind, "job_outputs", idx_outputs_cover):
        op.create_index(
            idx_outputs_cover,
            "job_outputs",
            ["job_id", "type", sa.text("created_at DESC")],
            unique=False,
        )


def downgrade() -> None:
    bind = op.get_bind()

    for table, idx in (
        ("job_outputs", "ix_job_outputs_job_type_created_at_desc"),
        ("jobs", "ix_jobs_client_active"),
    ):
        if _index_exists(bind, table, idx):
            op.drop_index(idx, table_name=table)
