"""add model_count column to charges

Revision ID: 20250906_model_count
Revises: 20250906_add_job_indexes
Create Date: 2025-09-06
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "20250906_model_count"  # Keep <=32 chars (alembic_version.version_num is VARCHAR(32))
down_revision: Union[str, Sequence[str], None] = "20250906_add_job_indexes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Idempotent upgrade: only add column / index if missing (DB already has column in some envs)
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    existing_cols = {c["name"] for c in inspector.get_columns("charges")}
    if "model_count" not in existing_cols:
        op.add_column(
            "charges",
            sa.Column("model_count", sa.Integer(), nullable=False, server_default="1"),
        )
        # Backfill (safety); should be instantaneous with default
        op.execute("UPDATE charges SET model_count = 1 WHERE model_count IS NULL")
    else:
        # Ensure any NULLs (from a manual add) are fixed
        op.execute("UPDATE charges SET model_count = 1 WHERE model_count IS NULL")

    # Create index if not present
    existing_indexes = {ix["name"] for ix in inspector.get_indexes("charges")}
    if "ix_charges_model_count" not in existing_indexes:
        op.create_index("ix_charges_model_count", "charges", ["model_count"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_charges_model_count", table_name="charges")
    op.drop_column("charges", "model_count")
