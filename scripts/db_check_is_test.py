from __future__ import annotations

import os
from dotenv import load_dotenv
from sqlalchemy import text

# Reuse the app's engine config
from restailor.db import engine


def main() -> None:
    load_dotenv(override=False)

    tables = [
        "users",
        "jobs",
        "job_outputs",
        "charges",
        "credit_ledger",
        "user_balance",
        "email_logs",
    ]
    allowed = set(tables)

    def _validate_table(t: str) -> str:
        if t not in allowed:
            raise ValueError(f"Unexpected table name: {t!r}")
        return t

    with engine.connect() as conn:
        result = conn.execute(text("select current_database(), current_user")).fetchone()
        if result is not None:
            db, user = result
            print(f"Connected to: db={db} user={user}")
        else:
            print("ERROR: Could not fetch current_database and current_user.")
        for t in tables:
            try:
                # Table names are from a hardcoded allowlist validated by _validate_table
                total = conn.execute(text(f"select count(*) from {_validate_table(t)}"))  # nosec B608: identifier validated against allowlist
                total = total.scalar_one()
                has_flag = conn.execute(
                    text(
                        "select count(*) from information_schema.columns where table_schema='public' and table_name=:t and column_name='is_test'"
                    ),
                    {"t": t},
                ).scalar_one()
                if has_flag:
                    q = text(f"select count(*) from {_validate_table(t)} where is_test = true")  # nosec B608: identifier validated
                    flagged = conn.execute(q).scalar_one()
                else:
                    flagged = None
                print(f"{t:15} total={total} is_test_col={'yes' if has_flag else 'no '} flagged={flagged}")
            except Exception as e:
                print(f"{t:15} ERROR: {e}")


if __name__ == "__main__":
    main()
