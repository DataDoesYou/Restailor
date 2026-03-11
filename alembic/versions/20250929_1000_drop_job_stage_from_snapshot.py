"""drop job_stage column from analytics snapshot state

Revision ID: 20250929_drop_snapshot_stage
Revises: 20250928_fix_app_user_jd_partial
Create Date: 2025-09-29 10:00:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20250929_drop_snapshot_stage"
down_revision = "20250928_fix_app_user_jd_partial"
branch_labels = None
depends_on = None

def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = {col["name"] for col in inspector.get_columns("analytics_job_snapshot_state")}
    if "job_stage" in columns:
        with op.batch_alter_table("analytics_job_snapshot_state", schema=None) as batch_op:
            batch_op.drop_column("job_stage")


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = {col["name"] for col in inspector.get_columns("analytics_job_snapshot_state")}
    if "job_stage" not in columns:
        with op.batch_alter_table("analytics_job_snapshot_state", schema=None) as batch_op:
            batch_op.add_column(sa.Column("job_stage", sa.Text(), nullable=True))
