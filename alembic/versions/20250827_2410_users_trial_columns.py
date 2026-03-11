"""add trial columns to users (optional)

Revision ID: 20250827_2410_users_trial
Revises: v_27_role_check
Create Date: 2025-08-27 24:10:00.000000

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20250827_2410_users_trial"

down_revision = "v_27_role_check"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    cols = {c["name"] for c in insp.get_columns("users")}

    if "trial_granted_at" not in cols:
        op.add_column(
            "users",
            sa.Column("trial_granted_at", sa.DateTime(timezone=True), nullable=True),
        )

    if "trial_method" not in cols:
        op.add_column(
            "users",
            sa.Column("trial_method", sa.Text(), nullable=True),
        )

    if "trial_revoked_at" not in cols:
        op.add_column(
            "users",
            sa.Column("trial_revoked_at", sa.DateTime(timezone=True), nullable=True),
        )


def downgrade() -> None:
    # Keep data by default; drop columns only if they exist
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = {c["name"] for c in insp.get_columns("users")}

    for name in ("trial_revoked_at", "trial_method", "trial_granted_at"):
        if name in cols:
            op.drop_column("users", name)
