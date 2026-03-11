"""add job access_token for per-job authZ

Revision ID: add_job_access_token_0100
Revises: 20250815_0008_add_source_page
Create Date: 2025-08-15 01:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
import secrets


# revision identifiers, used by Alembic.
revision = "add_job_access_token_0100"
down_revision = "20250815_0008_add_source_page"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("access_token", sa.String(length=128), nullable=True))
    op.create_index("ix_jobs_access_token", "jobs", ["access_token"], unique=False)
    # Backfill existing rows with random tokens
    conn = op.get_bind()
    res = conn.execute(sa.text("SELECT id FROM jobs WHERE access_token IS NULL"))
    rows = res.fetchall()
    for r in rows:
        token = secrets.token_urlsafe(48)
        conn.execute(sa.text("UPDATE jobs SET access_token = :t WHERE id = :id"), {"t": token, "id": str(r.id)})
    # Set not-null constraint after backfill
    op.alter_column("jobs", "access_token", existing_type=sa.String(length=128), nullable=False)


def downgrade() -> None:
    op.drop_index("ix_jobs_access_token", table_name="jobs")
    op.drop_column("jobs", "access_token")
