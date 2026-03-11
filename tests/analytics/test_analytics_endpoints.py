from __future__ import annotations

from datetime import datetime, timedelta, timezone
import uuid

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from restailor.db import SessionLocal
from restailor.models import User, UserBalance, Charge, CreditLedger
from tests.utils import signup_and_mark_test, login, upsert_balance, add_charge
from main import app


def _auth_headers(tok: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {tok}", "X-Client-Id": "test-client"}


def test_analytics_summary_and_export_csv(tmp_path):
    client = TestClient(app)

    email = f"analytics_tester+{uuid.uuid4()}@example.com"
    signup_and_mark_test(client, email)
    tok = login(client, email)

    # Seed ledger and charges for last 10 days
    with SessionLocal() as s:
        u = s.query(User).filter(User.username == email).first()
        assert u is not None
        upsert_balance(s, u.id, 5000)
        now = datetime.now(timezone.utc)
        # Ledger
        s.add(CreditLedger(user_id=u.id, delta_cents=+1000, type="grant", note=None, provider_ref=None))
        s.add(CreditLedger(user_id=u.id, delta_cents=-150, type="adjust", note=None, provider_ref=None))
        s.commit()
        # Charges across two request types and models
        add_charge(s, user_id=u.id, request_type="tailor", provider="openai", model="gpt-4o", price_to_user_usd=0.12)
        add_charge(s, user_id=u.id, request_type="judge", provider="openai", model="gpt-4o-mini", price_to_user_usd=0.08, output_models=3)
        add_charge(s, user_id=u.id, request_type="tailor", provider="openai", model="gpt-4o", price_to_user_usd=0.10)

    r = client.get("/analytics/summary", params={"period": "7d", "bucket": "day"}, headers=_auth_headers(tok))
    assert r.status_code == 200, r.text
    data = r.json()
    assert "series" in data and isinstance(data["series"], list)
    assert "by_type" in data and "tailor" in data["by_type"]
    assert "by_model" in data and "gpt-4o" in data["by_model"]
    assert "multi_model" in data and isinstance(data["multi_model"], dict)

    # CSV export removed - should return 404
    r2 = client.get("/analytics/export.csv", params={"period": "30d"}, headers=_auth_headers(tok))
    assert r2.status_code == 404, "CSV export endpoint should be removed"
