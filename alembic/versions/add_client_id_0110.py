"""add client_id to jobs for per-client concurrency limits

Revision ID: add_client_id_0110
Revises: add_job_access_token_0101
Create Date: 2025-08-15 02:10:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "add_client_id_0110"
down_revision = "add_job_access_token_0101"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("client_id", sa.String(length=64), nullable=True))
    op.create_index("ix_jobs_client_id", "jobs", ["client_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_jobs_client_id", table_name="jobs")
    op.drop_column("jobs", "client_id")
