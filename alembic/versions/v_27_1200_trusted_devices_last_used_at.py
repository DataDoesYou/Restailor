"""add last_used_at to user_trusted_devices

Revision ID: 27td_lu
Revises: 20250826_2300_mfa_and_2fa_tables
Create Date: 2025-08-27 12:00:00.000000

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "27td_lu"

down_revision = "20250826_2300_mfa_and_2fa_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    # Only add column if table exists and column missing
    if "user_trusted_devices" in insp.get_table_names():
        cols = {c["name"] for c in insp.get_columns("user_trusted_devices")}
        if "last_used_at" not in cols:
            op.add_column(
                "user_trusted_devices",
                sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
            )
        # Optional: index for queries/cleanup/analytics
        existing_idx = {ix["name"] for ix in insp.get_indexes("user_trusted_devices")}
        if "ix_user_trusted_devices_last_used" not in existing_idx:
            op.create_index(
                "ix_user_trusted_devices_last_used",
                "user_trusted_devices",
                ["user_id", "last_used_at"],
                unique=False,
            )


def downgrade() -> None:
    try:
        op.drop_index("ix_user_trusted_devices_last_used", table_name="user_trusted_devices")
    except Exception:
        pass
    try:
        op.drop_column("user_trusted_devices", "last_used_at")
    except Exception:
        pass
