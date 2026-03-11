"""rename application stage flags to use is_ prefix

Revision ID: 20250926_app_stage_flags_is
Revises: 20250926_app_stage
Create Date: 2025-09-26 14:05:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20250926_app_stage_flags_is"
down_revision = "20250926_app_stage"
branch_labels = None
depends_on = None


_COLUMN_RENAMES = (
    ("has_interviewing", "is_interviewing"),
    ("has_offer", "is_offer"),
    ("has_hired", "is_hired"),
)

_INDEX_RENAMES = (
    ("ix_applications_has_interviewing", "ix_applications_is_interviewing"),
    ("ix_applications_has_offer", "ix_applications_is_offer"),
    ("ix_applications_has_hired", "ix_applications_is_hired"),
)


def upgrade() -> None:
    for old, new in _COLUMN_RENAMES:
        try:
            op.alter_column("applications", old, new_column_name=new)
        except Exception:
            # If the column is already renamed (e.g., manual hotfix), skip gracefully.
            pass

    for old_idx, new_idx in _INDEX_RENAMES:
        try:
            op.execute(sa.text(f"ALTER INDEX {old_idx} RENAME TO {new_idx}"))
        except Exception:
            pass


def downgrade() -> None:
    for old_idx, new_idx in reversed(_INDEX_RENAMES):
        try:
            op.execute(sa.text(f"ALTER INDEX {new_idx} RENAME TO {old_idx}"))
        except Exception:
            pass

    for old, new in reversed(_COLUMN_RENAMES):
        try:
            op.alter_column("applications", new, new_column_name=old)
        except Exception:
            pass
