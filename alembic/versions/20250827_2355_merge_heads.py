"""merge multiple heads

Revision ID: 20250827_2355_merge_heads
Revises: 27td_lu, 20250827_2300_audit_events, 20250827_idx_created
Create Date: 2025-08-27 23:55:00.000000

"""
from __future__ import annotations

# This is a merge revision, no-op upgrade/downgrade.
from alembic import op  # noqa: F401
import sqlalchemy as sa  # noqa: F401

# revision identifiers, used by Alembic.
revision = "20250827_2355_merge_heads"

down_revision = (
    "27td_lu",
    "20250827_2300_audit_events",
    "20250827_idx_created",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
