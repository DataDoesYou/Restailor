"""
List trusted devices for a user by email.
Usage:
  poetry run python scripts/list_trusted_devices.py --email you@example.com
"""
from __future__ import annotations
import argparse
import sys
from datetime import datetime
from restailor.db import SessionLocal
from restailor.models import User
from restailor import twofa_repo
from sqlalchemy import select


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--email", required=True)
    args = ap.parse_args()
    email = (args.email or "").strip().lower()
    if not email:
        print("email is required", file=sys.stderr)
        return 2
    with SessionLocal() as s:
        user = s.execute(select(User).where(User.username == email)).scalar_one_or_none()
        if not user:
            print(f"no user found for email: {email}")
            return 1
        rows = twofa_repo.list_trusted_devices(s, int(user.id))
        print(f"user_id={user.id} email={email} trusted_devices={len(rows)}")
        for i, r in enumerate(rows):
            print(
                {
                    "idx": i,
                    "id": r.get("id"),
                    "created_at": r.get("created_at"),
                    "expires_at": r.get("expires_at"),
                    "user_agent": r.get("user_agent"),
                    "ip_prefix": r.get("ip_prefix"),
                    "last_used_at": r.get("last_used_at"),
                }
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
