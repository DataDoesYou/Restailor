"""remove last_resume_enc and last_jd_enc, add current_snapshot_key

Revision ID: 28snapshot
Revises: 27td_lu
Create Date: 2025-10-29 14:00:00.000000

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "28snapshot"
down_revision = "20251022_1100"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    
    if "users" in insp.get_table_names():
        cols = {c["name"] for c in insp.get_columns("users")}
        
        # Add current_snapshot_key to track which snapshot user is viewing
        if "current_snapshot_key" not in cols:
            op.add_column(
                "users",
                sa.Column("current_snapshot_key", sa.Text, nullable=True),
            )
        
        # Remove old user-level resume/JD fields (no longer needed - data lives in snapshots)
        if "last_resume_enc" in cols:
            op.drop_column("users", "last_resume_enc")
        
        if "last_jd_enc" in cols:
            op.drop_column("users", "last_jd_enc")


def downgrade() -> None:
    """Restore old columns"""
    bind = op.get_bind()
    insp = sa.inspect(bind)
    
    if "users" in insp.get_table_names():
        cols = {c["name"] for c in insp.get_columns("users")}
        
        # Add back encrypted resume/JD columns
        if "last_resume_enc" not in cols:
            op.add_column(
                "users",
                sa.Column("last_resume_enc", sa.LargeBinary, nullable=True),
            )
        
        if "last_jd_enc" not in cols:
            op.add_column(
                "users",
                sa.Column("last_jd_enc", sa.LargeBinary, nullable=True),
            )
        
        # Remove snapshot tracking
        if "current_snapshot_key" in cols:
            op.drop_column("users", "current_snapshot_key")
