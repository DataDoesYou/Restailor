"""add is_test to analytics snapshot state table

Revision ID: 20250926_snapshot_is_test
Revises: 20250924_job_snapshot_state
Create Date: 2025-09-26 11:00:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20250926_snapshot_is_test"
down_revision = "20250924_job_snapshot_state"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Check if column already exists before adding
    from sqlalchemy import inspect
    conn = op.get_bind()
    inspector = inspect(conn)
    columns = [col['name'] for col in inspector.get_columns('analytics_job_snapshot_state')]
    
    if 'is_test' not in columns:
        with op.batch_alter_table("analytics_job_snapshot_state") as batch_op:
            batch_op.add_column(
                sa.Column(
                    "is_test",
                    sa.Boolean(),
                    nullable=False,
                    server_default=sa.text("false"),
                )
            )


def downgrade() -> None:
    with op.batch_alter_table("analytics_job_snapshot_state") as batch_op:
        try:
            batch_op.drop_column("is_test")
        except Exception:
            pass
