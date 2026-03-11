"""merge heads 20250916_0220_drop_reason_real and 20250916_1200_drop_job_cols

Revision ID: 20250916_1300_merge
Revises: 20250916_0220_drop_reason_real, 20250916_1200_drop_job_cols
Create Date: 2025-09-16 13:00:00.000000
"""
from __future__ import annotations

from alembic import op  # noqa: F401
import sqlalchemy as sa  # noqa: F401

# revision identifiers, used by Alembic.
revision = "20250916_1300_merge"
down_revision = ("20250916_0220_drop_reason_real", "20250916_1200_drop_job_cols")
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Merge migration; no-op.
    pass


def downgrade() -> None:
    # Cannot automatically un-merge branches; no-op.
    pass
