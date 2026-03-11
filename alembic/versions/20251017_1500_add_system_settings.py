"""add system_settings table for admin configuration

Revision ID: 20251017_1500_system_settings
Revises: 20251016_indexes_for_incremental
Create Date: 2025-10-17 15:00:00.000000

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "20251017_1500_system_settings"
down_revision = "20251016_indexes_for_incremental"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create system_settings table for storing admin-configurable settings."""
    bind = op.get_bind()
    insp = sa.inspect(bind)
    
    # Check if table already exists
    tables = insp.get_table_names()
    if "system_settings" in tables:
        return
    
    op.create_table(
        "system_settings",
        sa.Column("key", sa.String(length=255), nullable=False, primary_key=True),
        sa.Column(
            "value",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    
    # Create index on updated_at for tracking changes
    op.create_index(
        "ix_system_settings_updated_at",
        "system_settings",
        ["updated_at"],
    )


def downgrade() -> None:
    """Drop system_settings table."""
    bind = op.get_bind()
    insp = sa.inspect(bind)
    
    tables = insp.get_table_names()
    if "system_settings" in tables:
        op.drop_index("ix_system_settings_updated_at", table_name="system_settings")
        op.drop_table("system_settings")
