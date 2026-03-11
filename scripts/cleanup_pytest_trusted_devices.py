"""
Delete any trusted device entries created by test tooling (user_agent='pytest-agent').

Usage: run this script in the app environment (with DATABASE_URL configured)
"""
from restailor.db import SessionLocal
import sqlalchemy as sa

if __name__ == "__main__":
    with SessionLocal() as s:
        try:
            # Get count first, then delete
            cnt = s.execute(sa.text("SELECT COUNT(*) FROM user_trusted_devices WHERE user_agent = :ua"), {"ua": "pytest-agent"}).scalar() or 0
            s.execute(sa.text("DELETE FROM user_trusted_devices WHERE user_agent = :ua"), {"ua": "pytest-agent"})
            s.commit()
            print(f"deleted {int(cnt)} trusted device rows with user_agent='pytest-agent'")
        except Exception as ex:
            try:
                s.rollback()
            except Exception:
                pass
            print("cleanup failed:", ex)
