"""add user provider keys

Revision ID: 20260508_1200
Revises: 28snapshot
Create Date: 2026-05-08 12:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260508_1200"
down_revision = "28snapshot"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_provider_keys",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("key_enc", sa.LargeBinary(), nullable=False),
        sa.Column("key_tail", sa.String(length=16), nullable=False),
        sa.Column("storage_mode", sa.String(length=32), server_default="server", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "provider", name="uq_user_provider_keys_user_provider"),
    )
    op.create_index("ix_user_provider_keys_user_id", "user_provider_keys", ["user_id"], unique=False)
    op.create_index("ix_user_provider_keys_user_provider", "user_provider_keys", ["user_id", "provider"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_user_provider_keys_user_provider", table_name="user_provider_keys")
    op.drop_index("ix_user_provider_keys_user_id", table_name="user_provider_keys")
    op.drop_table("user_provider_keys")
