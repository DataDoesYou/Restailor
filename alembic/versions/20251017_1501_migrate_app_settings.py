"""migrate app_settings from JSON to database

Revision ID: 20251017_1501_migrate_settings
Revises: 20251017_1500_system_settings
Create Date: 2025-10-17 15:01:00.000000

This migration copies existing settings from config/app_settings.json
to the new system_settings table.
"""
from __future__ import annotations

import json
from pathlib import Path
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import insert

# revision identifiers, used by Alembic.
revision = "20251017_1501_migrate_settings"
down_revision = "20251017_1500_system_settings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Migrate settings from JSON file to database."""
    bind = op.get_bind()
    
    # Try to load existing JSON settings
    json_path = Path("config") / "app_settings.json"
    if not json_path.exists():
        # No existing settings to migrate
        return
    
    try:
        with json_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        
        if not isinstance(data, dict):
            return
        
        # Insert each key-value pair into system_settings
        system_settings = sa.table(
            "system_settings",
            sa.column("key", sa.String),
            sa.column("value", postgresql.JSONB),
            sa.column("updated_at", sa.DateTime(timezone=True)),
        )
        
        for key, value in data.items():
            stmt = insert(system_settings).values(
                key=key,
                value=value,
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["key"],
                set_={"value": value, "updated_at": sa.func.now()},
            )
            bind.execute(stmt)
        
        print(f"Migrated {len(data)} settings from {json_path} to database")
        
    except Exception as ex:
        print(f"Warning: Failed to migrate settings from JSON: {ex}")
        # Don't fail the migration if JSON file is corrupt or missing


def downgrade() -> None:
    """No downgrade needed - we keep the data in the database."""
    pass
