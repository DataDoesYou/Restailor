"""rename analytics snapshot stage flags to match application fields

Revision ID: 20250929_rename_snapshot_flags
Revises: 20250929_drop_snapshot_stage
Create Date: 2025-09-29 11:05:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20250929_rename_snapshot_flags"
down_revision = "20250929_drop_snapshot_stage"
branch_labels = None
depends_on = None


def _existing_columns() -> set[str]:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    return {col["name"] for col in inspector.get_columns("analytics_job_snapshot_state")}


def upgrade() -> None:
    columns = _existing_columns()
    renames = [
        ("count_interviewing", "is_interviewing"),
        ("count_offer", "is_offer"),
        ("count_hired", "is_hired"),
    ]
    rename_ops = [(old, new) for old, new in renames if old in columns and new not in columns]
    if rename_ops:
        with op.batch_alter_table("analytics_job_snapshot_state", schema=None) as batch_op:
            for old, new in rename_ops:
                batch_op.alter_column(old, new_column_name=new)


def downgrade() -> None:
    columns = _existing_columns()
    renames = [
        ("is_interviewing", "count_interviewing"),
        ("is_offer", "count_offer"),
        ("is_hired", "count_hired"),
    ]
    rename_ops = [(old, new) for old, new in renames if old in columns and new not in columns]
    if rename_ops:
        with op.batch_alter_table("analytics_job_snapshot_state", schema=None) as batch_op:
            for old, new in rename_ops:
                batch_op.alter_column(old, new_column_name=new)
