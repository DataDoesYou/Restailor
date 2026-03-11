"""add admin_id to credit_ledger with FK to users and composite index

Revision ID: 20250826_2105_admin_id_ledger
Revises: 20250826_2000_add_is_test_flags
Create Date: 2025-08-26 21:05:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
# Note: users.id is Integer in this project; admin_id must match that type

# revision identifiers, used by Alembic.
revision = "20250826_2105_admin_id_ledger"
down_revision = "20250826_2000_add_is_test_flags"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add nullable admin_id (Integer) referencing users(id) with ON DELETE SET NULL
    op.add_column(
        "credit_ledger",
        sa.Column("admin_id", sa.Integer(), nullable=True),
    )

    op.create_foreign_key(
        "fk_credit_ledger_admin_id_users",
        "credit_ledger",
        "users",
        ["admin_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # Create index on (admin_id, created_at DESC) using helpers
    op.create_index(
        "ix_credit_ledger_admin_created_at",
        "credit_ledger",
        ["admin_id", sa.text("created_at DESC")],
        unique=False,
    )


def downgrade() -> None:
    # Drop index, FK, then column
    op.drop_index("ix_credit_ledger_admin_created_at", table_name="credit_ledger")
    op.drop_constraint("fk_credit_ledger_admin_id_users", "credit_ledger", type_="foreignkey")
    op.drop_column("credit_ledger", "admin_id")
