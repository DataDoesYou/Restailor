"""add index on credit_ledger.provider_ref

Revision ID: 20250826_2200_credit_ref_idx
Revises: 20250826_2105_admin_id_ledger
Create Date: 2025-08-26 22:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20250826_2200_credit_ref_idx"

down_revision = "20250826_2105_admin_id_ledger"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create an index to accelerate idempotency lookups by provider_ref
    op.create_index(
        "ix_credit_ledger_provider_ref",
        "credit_ledger",
        ["provider_ref"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_credit_ledger_provider_ref", table_name="credit_ledger")
