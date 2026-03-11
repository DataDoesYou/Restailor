"""add webauthn credentials table

Revision ID: 20250827_wa_creds
Revises: 20250826_2300_mfa_and_2fa_tables
Create Date: 2025-08-27 10:00:00.000000

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as psql

# revision identifiers, used by Alembic.
revision = "20250827_wa_creds"

down_revision = "20250826_2300_mfa_and_2fa_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if "webauthn_credentials" not in insp.get_table_names():
        op.create_table(
            "webauthn_credentials",
            sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column(
                "user_id",
                sa.Integer(),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False,
                index=True,  # creates ix_webauthn_credentials_user_id automatically
            ),
            sa.Column("credential_id", sa.Text(), nullable=False, unique=True),  # base64url
            sa.Column("public_key", sa.LargeBinary(), nullable=False),
            sa.Column("sign_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("transports", psql.ARRAY(sa.Text()), nullable=True),
            sa.Column("aaguid", sa.Text(), nullable=True),
            sa.Column("nickname", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        )


def downgrade() -> None:
    op.drop_table("webauthn_credentials")
