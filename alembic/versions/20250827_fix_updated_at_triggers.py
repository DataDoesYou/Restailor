"""ensure updated_at triggers exist on users and webauthn_credentials

Revision ID: 20250827_fix_trg
Revises: 20250827_ts_std
Create Date: 2025-08-27 14:05:00.000000

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20250827_fix_trg"
down_revision = "20250827_ts_std"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    # Ensure trigger function exists
    op.execute(
        sa.text(
            """
            CREATE OR REPLACE FUNCTION set_updated_at()
            RETURNS TRIGGER AS $$
            BEGIN
                NEW.updated_at = now();
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;
            """
        )
    )

    def attach_if_has_updated_at(table: str) -> None:
        if table not in insp.get_table_names():
            return
        cols = {c["name"] for c in insp.get_columns(table)}
        if "updated_at" not in cols:
            return
        op.execute(sa.text(f"DROP TRIGGER IF EXISTS trg_{table}_set_updated_at ON {table};"))
        op.execute(
            sa.text(
                f"""
                CREATE TRIGGER trg_{table}_set_updated_at
                BEFORE UPDATE ON {table}
                FOR EACH ROW
                EXECUTE FUNCTION set_updated_at();
                """
            )
        )

    # Explicitly ensure on users and webauthn_credentials; harmless to re-ensure others
    for tbl in ("users", "webauthn_credentials"):
        attach_if_has_updated_at(tbl)


def downgrade() -> None:
    # No-op: keep triggers
    pass
