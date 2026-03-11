"""create test_checkbox table

Revision ID: 20251015_0100_test_checkbox
Revises: 27td_lu
Create Date: 2025-10-15 01:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "20251015_0100_test_checkbox"
down_revision: Union[str, Sequence[str], None] = "723e77199c93"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create test_checkbox table for testing checkbox persistence."""
    op.create_table(
        "test_checkbox",
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "is_checked",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    # Index for faster lookups by user_id (though it's already PK)
    op.create_index(
        op.f("ix_test_checkbox_user_id"),
        "test_checkbox",
        ["user_id"],
        unique=True,
    )


def downgrade() -> None:
    """Drop test_checkbox table."""
    op.drop_index(op.f("ix_test_checkbox_user_id"), table_name="test_checkbox")
    op.drop_table("test_checkbox")
