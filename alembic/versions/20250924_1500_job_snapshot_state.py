"""analytics job snapshot state table

Revision ID: 20250924_job_snapshot_state
Revises: 20250925_0900_stage_flags
Create Date: 2025-09-24 15:00:00
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20250924_job_snapshot_state"
down_revision: Union[str, Sequence[str], None] = "20250925_0900_stage_flags"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "analytics_job_snapshot_state",
        sa.Column("snapshot_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("is_applied", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("is_interviewing", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_offer", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_hired", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_test", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.PrimaryKeyConstraint("snapshot_id"),
    )
    op.create_index(
        "ix_analytics_job_snapshot_state_user_id",
        "analytics_job_snapshot_state",
        ["user_id"],
    )
    op.create_index(
        "ix_analytics_job_snapshot_state_user_created",
        "analytics_job_snapshot_state",
        ["user_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_analytics_job_snapshot_state_user_created", table_name="analytics_job_snapshot_state")
    op.drop_index("ix_analytics_job_snapshot_state_user_id", table_name="analytics_job_snapshot_state")
    op.drop_table("analytics_job_snapshot_state")
