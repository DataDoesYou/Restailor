"""make pricing_version integer

Revision ID: 20250830_1700_pricing_version_int
Revises: 20250827_2410_users_trial_columns
Create Date: 2025-08-30 17:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "v_30_1700_pv_int"
down_revision: Union[str, Sequence[str], None] = "422e27868829"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Convert existing text pricing_version to integer with default 1
    # 1) Backfill non-numeric to '1'
    op.execute("UPDATE charges SET pricing_version = '1' WHERE pricing_version IS NULL OR pricing_version !~ '^[0-9]+$'")
    # 2) Drop existing default to allow type change
    op.alter_column(
        "charges",
        "pricing_version",
        server_default=None,
        existing_type=sa.Text(),
        existing_nullable=False,
    )
    # 3) Alter type to integer using USING cast
    op.alter_column(
        "charges",
        "pricing_version",
        existing_type=sa.Text(),
        type_=sa.Integer(),
        existing_nullable=False,
        postgresql_using="pricing_version::integer",
    )
    # 4) Set server default to 1
    op.alter_column(
        "charges",
        "pricing_version",
        server_default="1",
        existing_type=sa.Integer(),
        existing_nullable=False,
    )


def downgrade() -> None:
    # Revert to text with default 'v1'
    op.alter_column(
        "charges",
        "pricing_version",
        existing_type=sa.Integer(),
        type_=sa.Text(),
        existing_nullable=False,
        postgresql_using="pricing_version::text",
    )
    op.alter_column(
        "charges",
        "pricing_version",
        server_default=sa.text("'v1'"),
        existing_type=sa.Text(),
        existing_nullable=False,
    )
