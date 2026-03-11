from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from sqlalchemy import text
from sqlalchemy.engine import Engine

from restailor.db import engine


@dataclass
class TablePlan:
    name: str
    where: str = "is_test = true"


# Child-first deletion order, then parents
DELETE_ORDER: Sequence[TablePlan] = [
    TablePlan("job_outputs"),
    TablePlan("charges"),
    TablePlan("email_logs"),
    TablePlan("audit_events"),
    TablePlan("credit_ledger"),
    TablePlan("user_balance"),
    TablePlan("jobs"),
    TablePlan("users"),
]

ALLOWED_TABLES = {t.name for t in DELETE_ORDER}


def _validate_table_name(table: str) -> str:
    """Defense-in-depth: ensure we only interpolate known identifiers.

    Although this script only uses hard-coded table names, validate anyway.
    """
    if table not in ALLOWED_TABLES:
        raise ValueError(f"Refusing to operate on unexpected table name: {table!r}")
    return table


def count_flagged(conn, table: str) -> int:
    table = _validate_table_name(table)
    # Identifier is strictly validated against ALLOWED_TABLES above; no user input.
    sql = text(f"select count(*) from {table} where is_test = true")  # nosec B608: identifier validated via ALLOWED_TABLES
    return conn.execute(sql).scalar_one()


def count_total(conn, table: str) -> int:
    table = _validate_table_name(table)
    # Identifier is strictly validated against ALLOWED_TABLES above; no user input.
    sql = text(f"select count(*) from {table}")  # nosec B608: identifier validated via ALLOWED_TABLES
    return conn.execute(sql).scalar_one()


def purge_is_test(engine: Engine) -> None:
    with engine.begin() as conn:
        print("Pre-delete counts (total | is_test):")
        for t in DELETE_ORDER:
            try:
                total = count_total(conn, t.name)
                flagged = count_flagged(conn, t.name)
                print(f"  {t.name:15} {total:6} | {flagged:6}")
            except Exception as e:
                print(f"  {t.name:15} ERROR: {e}")

        print("\nDeleting is_test rows...")
        for t in DELETE_ORDER:
            try:
                _validate_table_name(t.name)
                # Table and WHERE are statically defined (no user input)
                sql = text(f"delete from {t.name} where {t.where}")  # nosec B608: hard-coded identifiers (TablePlan)
                result = conn.execute(sql)
                print(f"  {t.name:15} deleted {result.rowcount}")
            except Exception as e:
                print(f"  {t.name:15} ERROR during delete: {e}")

        # Best-effort: purge related tables without is_test flags
        # webauthn_credentials, user_trusted_devices reference users by user_id
        # Delete rows where user_id in (select id from users where is_test = true)
        def _purge_child(table: str, fk_col: str = "user_id") -> None:
            try:
                sql = text(
                    f"DELETE FROM {table} WHERE {fk_col} IN (SELECT id FROM users WHERE is_test = true)"
                )
                res = conn.execute(sql)
                print(f"  {table:15} deleted {res.rowcount}")
            except Exception as e:
                print(f"  {table:15} skip/ERROR: {e}")

        print("\nDeleting related rows for test users (no is_test flag on these tables)...")
        _purge_child("webauthn_credentials")
        _purge_child("user_trusted_devices")

        print("\nPost-delete counts (total | is_test):")
        for t in DELETE_ORDER:
            try:
                total = count_total(conn, t.name)
                flagged = count_flagged(conn, t.name)
                print(f"  {t.name:15} {total:6} | {flagged:6}")
            except Exception as e:
                print(f"  {t.name:15} ERROR: {e}")


if __name__ == "__main__":
    purge_is_test(engine)
