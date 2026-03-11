"""enforce at most one active job per client via partial unique index

Revision ID: add_active_job_guard_0120
Revises: add_client_id_0110
Create Date: 2025-08-15 02:20:00.000000
"""
from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "add_active_job_guard_0120"
down_revision = "add_client_id_0110"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Unique per client_id where job is not in a terminal state
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_active_job_per_client
        ON jobs (client_id)
        WHERE client_id IS NOT NULL AND status NOT IN ('completed','failed');
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_active_job_per_client;")
