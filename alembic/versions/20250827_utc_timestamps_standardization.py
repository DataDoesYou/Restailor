"""standardize utc timestamps, add triggers

Revision ID: 20250827_ts_std
Revises: 20250827_wa_creds
Create Date: 2025-08-27 13:30:00.000000

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20250827_ts_std"
down_revision = "20250827_wa_creds"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    # Helper to check and add columns
    def add_col_if_missing(table: str, column: sa.Column) -> None:
        cols = {c["name"] for c in insp.get_columns(table)}
        if column.name not in cols:
            op.add_column(table, column)

    # Users: ensure created_at, updated_at (tz-aware)
    add_col_if_missing(
        "users",
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    add_col_if_missing(
        "users",
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    # UserBalance: ensure created_at
    add_col_if_missing(
        "user_balance",
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    # WebAuthn credentials: ensure updated_at (mutable nickname/sign_count)
    if "webauthn_credentials" in insp.get_table_names():
        add_col_if_missing(
            "webauthn_credentials",
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        )

    # Backfill updated_at from created_at where possible (and vice versa if needed)
    op.execute(
        sa.text(
            """
            UPDATE users SET updated_at = COALESCE(updated_at, created_at, now());
            UPDATE users SET created_at = COALESCE(created_at, updated_at, now());
            UPDATE user_balance SET created_at = COALESCE(created_at, updated_at, now());
            UPDATE webauthn_credentials SET updated_at = COALESCE(updated_at, created_at, now())
            """
        )
    )

    # Create trigger function to auto-update updated_at
    # Note: idempotent create with CREATE OR REPLACE FUNCTION
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

    def attach_trigger(table: str) -> None:
        # Drop existing trigger if exists, then create
        op.execute(
            sa.text(
                f"DROP TRIGGER IF EXISTS trg_{table}_set_updated_at ON {table};"
            )
        )
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

    # Attach triggers to mutable tables
    for tbl in ("users", "jobs", "user_balance", "webauthn_credentials"):
        if tbl in insp.get_table_names():
            # Ensure the table has updated_at; jobs and user_balance already do, users added above; webauthn added above
            cols = {c["name"] for c in insp.get_columns(tbl)}
            if "updated_at" in cols:
                attach_trigger(tbl)


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    def drop_trigger_if_exists(table: str) -> None:
        if table in insp.get_table_names():
            op.execute(sa.text(f"DROP TRIGGER IF EXISTS trg_{table}_set_updated_at ON {table};"))

    for tbl in ("users", "jobs", "user_balance", "webauthn_credentials"):
        drop_trigger_if_exists(tbl)

    # Optionally drop function (safe if unused elsewhere)
    op.execute(sa.text("DROP FUNCTION IF EXISTS set_updated_at();"))

    # We keep columns on downgrade to avoid data loss.
