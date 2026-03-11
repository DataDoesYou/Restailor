"""
NOTE: These tests must be run via scripts/run_tests_local.ps1 (Doppler env + DB), not bare pytest.
This ensures proper environment, migrations, and Postgres are available.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Iterable

from fastapi.testclient import TestClient

from restailor.db import SessionLocal
from restailor.models import User, Charge, CreditLedger
from tests.utils import signup_and_mark_test, login, upsert_balance, add_charge
from main import app


def _auth_headers(tok: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {tok}", "X-Client-Id": "test-client"}


def test_summary_aggregations_and_csv_export():
    client = TestClient(app)

    # Create user and seed data
    email = "analytics_suite@example.com"
    signup_and_mark_test(client, email)
    tok = login(client, email)

    # Seed two weeks of mixed charges and ledger entries
    with SessionLocal() as s:
        u = s.query(User).filter(User.username == email).first()
        assert u is not None
        upsert_balance(s, u.id, 10_00)

        base = datetime.now(timezone.utc) - timedelta(days=14)
        # Ledger deltas across time
        for i in range(6):
            # Positive credit to ledger (grant)
            s.add(CreditLedger(user_id=u.id, delta_cents=+500, type="grant", note=None, provider_ref=None, created_at=base + timedelta(days=i*2)))
            # Negative adjustment in ledger (admin adjustment), not spend; charges table records spend
            s.add(CreditLedger(user_id=u.id, delta_cents=-100, type="adjust", note=None, provider_ref=None, created_at=base + timedelta(days=i*2+1)))
        s.commit()

        # Charges: tailor/judge on different models; include some multi-model charges
        # Totals we expect by type
        expect_counts = {"tailor": 0, "judge": 0}
        expect_spend = {"tailor": 0.0, "judge": 0.0}

        def seed(rt: str, model: str, price: float, days_offset: int, multi: bool = False):
            nonlocal expect_counts, expect_spend
            add_charge(
                s,
                user_id=u.id,
                request_type=rt,
                provider="openai",
                model=model,
                price_to_user_usd=price,
                cost_usd=price / 2.0,
                created_at=base + timedelta(days=days_offset),
                output_models=(3 if multi else 1),
            )
            expect_counts[rt] += 1
            expect_spend[rt] += price

        # Week 1
        seed("tailor", "gpt-4o", 0.10, 1)
        seed("tailor", "gpt-4o", 0.20, 2, multi=True)
        seed("judge", "gpt-4o-mini", 0.05, 3)
        # Week 2
        seed("tailor", "gpt-4o", 0.30, 9)
        seed("judge", "gpt-4o-mini", 0.15, 10, multi=True)
        seed("judge", "gpt-4o-mini", 0.25, 11)

    # Fetch summary (auto bucket by range)
    r = client.get("/analytics/summary", params={"from": (datetime.now(timezone.utc) - timedelta(days=14)).isoformat(), "to": datetime.now(timezone.utc).isoformat()}, headers=_auth_headers(tok))
    assert r.status_code == 200, r.text
    data = r.json()

    # requests_by_type totals match seeded rows
    by_type = data.get("by_type") or {}
    assert by_type.get("tailor", {}).get("count") == expect_counts["tailor"]
    assert by_type.get("judge", {}).get("count") == expect_counts["judge"]

    # spend_by_type equals sum of price_to_user_usd
    def _f(x):
        try:
            return float(x)
        except Exception:
            return 0.0
    assert abs(_f(by_type.get("tailor", {}).get("spend_usd")) - expect_spend["tailor"]) < 1e-6
    assert abs(_f(by_type.get("judge", {}).get("spend_usd")) - expect_spend["judge"]) < 1e-6

    # multi_model single vs multi counts
    mm = data.get("multi_model") or {}
    single = int(mm.get("1", 0))
    multi = sum(int(v) for k, v in mm.items() if str(k) != "1")
    assert single + multi == expect_counts["tailor"] + expect_counts["judge"]
    assert multi >= 1

    # CSV export removed - verify endpoint returns 404
    r2 = client.get("/analytics/export.csv", params={"from": (datetime.now(timezone.utc) - timedelta(days=14)).isoformat(), "to": datetime.now(timezone.utc).isoformat()}, headers=_auth_headers(tok))
    assert r2.status_code == 404, "CSV export endpoint should be removed"
