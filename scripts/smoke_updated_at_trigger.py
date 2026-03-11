from __future__ import annotations

from sqlalchemy import text
from restailor.db import engine


def verify_users_updated_at() -> None:
    with engine.begin() as conn:
        row = conn.execute(
            text(
                """
                SELECT id, username, created_at, updated_at, is_test
                FROM users
                ORDER BY id ASC
                LIMIT 1
                """
            )
        ).mappings().first()
        if not row:
            print("NO_USERS")
            return
        print("BEFORE:", dict(row))
        conn.execute(text("UPDATE users SET username=username WHERE id=:id"), {"id": row["id"]})
        row2 = conn.execute(
            text(
                """
                SELECT id, username, created_at, updated_at, is_test
                FROM users WHERE id=:id
                """
            ),
            {"id": row["id"]},
        ).mappings().first()
        print("AFTER:", dict(row2))


if __name__ == "__main__":
    verify_users_updated_at()
