"""Add audit_events table for 2FA/step-up auditing.

Revision ID: 20250827_2300_audit_events
Revises: 20250827_wa_creds
Create Date: 2025-08-27 23:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as psql

# revision identifiers, used by Alembic.
revision = "20250827_2300_audit_events"

down_revision = "20250827_wa_creds"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "audit_events" not in insp.get_table_names():
        op.create_table(
            "audit_events",
            sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("event_type", sa.Text(), nullable=False),
            sa.Column("severity", sa.Text(), nullable=False, server_default=sa.text("'info'")),
            sa.Column("ip", sa.Text(), nullable=True),
            sa.Column("user_agent", sa.Text(), nullable=True),
            sa.Column("meta", psql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("is_test", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        )
        op.create_index("ix_audit_events_user", "audit_events", ["user_id"], unique=False)
        op.create_index("ix_audit_events_type", "audit_events", ["event_type"], unique=False)
        op.create_index("ix_audit_events_type_created", "audit_events", ["event_type", sa.text("created_at DESC")], unique=False)
        op.create_index("ix_audit_events_created", "audit_events", [sa.text("created_at DESC")], unique=False)


def downgrade() -> None:
    op.drop_index("ix_audit_events_created", table_name="audit_events")
    op.drop_index("ix_audit_events_type_created", table_name="audit_events")
    op.drop_index("ix_audit_events_type", table_name="audit_events")
    op.drop_index("ix_audit_events_user", table_name="audit_events")
    op.drop_table("audit_events")
