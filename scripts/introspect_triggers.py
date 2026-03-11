from __future__ import annotations

from sqlalchemy import text
from restailor.db import engine


def main() -> None:
    with engine.begin() as conn:
        print("TRIGGERS:")
        rows = conn.execute(
            text(
                """
                SELECT tg.tgname, c.relname AS table_name, p.proname AS func
                FROM pg_trigger tg
                JOIN pg_class c ON c.oid = tg.tgrelid
                JOIN pg_proc p ON p.oid = tg.tgfoid
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = 'public' AND c.relname IN ('users','jobs','user_balance','webauthn_credentials')
                  AND NOT tg.tgisinternal
                ORDER BY c.relname, tg.tgname
                """
            )
        ).fetchall()
        for r in rows:
            print(r)

        cols = conn.execute(
            text(
                """
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_schema='public' AND table_name='users'
                ORDER BY ordinal_position
                """
            )
        ).fetchall()
        print("USERS COLS:", cols)


if __name__ == "__main__":
    main()
