"""merge heads for output/input models branch

Revision ID: 20250913_1310_merge_heads
Revises: 20250913_1300, 20250908_app_is_applied
Create Date: 2025-09-13 13:10:00
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op  # noqa: F401
import sqlalchemy as sa  # noqa: F401

revision: str = "20250913_1310_merge_heads"
# Removed missing 20250906_norm_judge_req_type to allow linearization without data loss.
down_revision: Union[str, Sequence[str], None] = ("20250913_1300", "20250908_app_is_applied")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:  # pragma: no cover - merge only
    pass


def downgrade() -> None:  # pragma: no cover - unsafe to unmerge
    pass
