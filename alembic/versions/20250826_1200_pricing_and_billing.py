"""create pricing and billing tables

Revision ID: 20250826_1200_pricing_billing
Revises: 20250824_0200_user_settings
Create Date: 2025-08-26 12:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20250826_1200_pricing_billing"
down_revision: Union[str, Sequence[str], None] = "20250824_0200_user_settings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create charges, credit_ledger, and user_balance tables plus indexes."""
    # charges
    op.create_table(
        "charges",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        # NOTE: existing users.id is Integer in this project; use Integer FK to match
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "request_type",
            sa.Text(),
            nullable=False,
        ),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completion_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cost_usd", sa.Numeric(12, 6), nullable=False),
        sa.Column("price_to_user_usd", sa.Numeric(12, 6), nullable=False),
        sa.Column("currency", sa.Text(), nullable=False, server_default=sa.text("'USD'")),
        sa.Column("pricing_version", sa.Text(), nullable=False, server_default=sa.text("'v1'")),
        sa.CheckConstraint(
            "request_type IN ('tailor','fit','judge','tailor+judge')",
            name="ck_charges_request_type",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE", name="fk_charges_user_id_users"),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="SET NULL", name="fk_charges_job_id_jobs"),
    )

    # Add useful composite indexes; use raw SQL to enforce DESC ordering where requested
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_charges_req_model_created_at ON charges (request_type, model, created_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_charges_user_created_at ON charges (user_id, created_at DESC)"
    )

    # credit_ledger
    op.create_table(
        "credit_ledger",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("delta_cents", sa.Integer(), nullable=False),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("provider_ref", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "type IN ('purchase','grant','refund','adjust')",
            name="ck_credit_ledger_type",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE", name="fk_credit_ledger_user_id_users"),
    )

    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_credit_ledger_user_created_at ON credit_ledger (user_id, created_at DESC)"
    )

    # user_balance
    op.create_table(
        "user_balance",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("balance_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )


def downgrade() -> None:
    """Drop indexes and tables for pricing/billing."""
    # Drop indexes first
    op.drop_index("ix_credit_ledger_user_created_at", table_name="credit_ledger")
    op.drop_index("ix_charges_user_created_at", table_name="charges")
    op.drop_index("ix_charges_req_model_created_at", table_name="charges")

    # Drop tables (reverse order of creation where FKs apply)
    op.drop_table("user_balance")
    op.drop_table("credit_ledger")
    op.drop_table("charges")
