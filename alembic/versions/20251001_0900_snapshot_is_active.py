"""rename analytics snapshot include flag to is_active

Revision ID: 20251001_snapshot_is_active
Revises: 20250929_rename_snapshot_flags
Create Date: 2025-10-01 09:00:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20251001_snapshot_is_active"
down_revision = "20250929_rename_snapshot_flags"
branch_labels = None
depends_on = None


def _existing_columns() -> set[str]:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    try:
        return {col["name"] for col in inspector.get_columns("analytics_job_snapshot_state")}
    except Exception:
        return set()


def upgrade() -> None:
    columns = _existing_columns()
    if "include_in_cohort" in columns and "is_active" not in columns:
        with op.batch_alter_table("analytics_job_snapshot_state", schema=None) as batch_op:
            batch_op.alter_column("include_in_cohort", new_column_name="is_active")


def downgrade() -> None:
    columns = _existing_columns()
    if "is_active" in columns and "include_in_cohort" not in columns:
        with op.batch_alter_table("analytics_job_snapshot_state", schema=None) as batch_op:
            batch_op.alter_column("is_active", new_column_name="include_in_cohort")
