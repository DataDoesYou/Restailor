"""add mfa fields and 2FA support tables

Revision ID: 20250826_2300_mfa_and_2fa_tables
Revises: 20250826_2200_credit_ref_idx
Create Date: 2025-08-26 23:00:00.000000

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as psql


# revision identifiers, used by Alembic.
revision = "20250826_2300_mfa_and_2fa_tables"

down_revision = "20250826_2200_credit_ref_idx"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    # --- Users: MFA/2FA fields ---
    user_cols = {c["name"] for c in insp.get_columns("users")}
    if "two_factor_enabled" not in user_cols:
        op.add_column(
            "users",
            sa.Column("two_factor_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        )
    if "two_factor_type" not in user_cols:
        op.add_column("users", sa.Column("two_factor_type", sa.Text(), nullable=True))
    if "two_factor_confirmed" not in user_cols:
        op.add_column(
            "users",
            sa.Column("two_factor_confirmed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        )
    if "two_factor_confirmed_at" not in user_cols:
        op.add_column("users", sa.Column("two_factor_confirmed_at", sa.DateTime(timezone=True), nullable=True))
    if "totp_secret" not in user_cols:
        op.add_column("users", sa.Column("totp_secret", sa.Text(), nullable=True))
    if "recovery_codes" not in user_cols:
        op.add_column("users", sa.Column("recovery_codes", psql.ARRAY(sa.Text()), nullable=True))
    if "last_2fa_at" not in user_cols:
        op.add_column("users", sa.Column("last_2fa_at", sa.DateTime(timezone=True), nullable=True))

    # --- Trusted devices table ---
    if "user_trusted_devices" not in insp.get_table_names():
        op.create_table(
            "user_trusted_devices",
            sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("token_hash", sa.Text(), nullable=False),
            sa.Column("user_agent", sa.Text(), nullable=True),
            sa.Column("ip_prefix", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        )
    # Ensure index on user_id exists
    existing_ud_idx = {ix["name"] for ix in insp.get_indexes("user_trusted_devices")} if "user_trusted_devices" in insp.get_table_names() else set()
    if "ix_user_trusted_devices_user_id" not in existing_ud_idx:
        op.create_index("ix_user_trusted_devices_user_id", "user_trusted_devices", ["user_id"], unique=False)
    # If table exists, ensure ip_prefix column exists
    else:
        cols = {c["name"] for c in insp.get_columns("user_trusted_devices")}
        if "ip_prefix" not in cols:
            op.add_column("user_trusted_devices", sa.Column("ip_prefix", sa.Text(), nullable=True))

    # --- Email OTPs table ---
    if "email_otps" not in insp.get_table_names():
        op.create_table(
            "email_otps",
            sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("code_hash", sa.Text(), nullable=False),
            sa.Column("sent_to", sa.Text(), nullable=False),
            sa.Column("ip", sa.Text(), nullable=True),
            sa.Column("user_agent", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("attempts", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("max_attempts", sa.Integer(), nullable=False, server_default=sa.text("5")),
        )
    existing_eo_idx = {ix["name"] for ix in insp.get_indexes("email_otps")} if "email_otps" in insp.get_table_names() else set()
    if "ix_email_otps_user_expires" not in existing_eo_idx:
        op.create_index(
            "ix_email_otps_user_expires",
            "email_otps",
            ["user_id", "expires_at"],
            unique=False,
        )


def downgrade() -> None:
    # Drop OTP table and indexes
    op.drop_index("ix_email_otps_user_expires", table_name="email_otps")
    op.drop_table("email_otps")

    # Drop trusted devices table and indexes
    op.drop_index("ix_user_trusted_devices_user_id", table_name="user_trusted_devices")
    op.drop_table("user_trusted_devices")

    # Remove user columns (reverse order of addition for safety)
    for col in (
        "last_2fa_at",
        "recovery_codes",
        "totp_secret",
        "two_factor_confirmed_at",
        "two_factor_confirmed",
        "two_factor_type",
        "two_factor_enabled",
    ):
        op.drop_column("users", col)
