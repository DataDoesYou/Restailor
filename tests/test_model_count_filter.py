from __future__ import annotations

from decimal import Decimal
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from main import app
from restailor.db import SessionLocal
from restailor.models import Charge, User, UserBalance
from tests.utils import signup_and_mark_test, login, upsert_balance

import pytest
pytestmark = pytest.mark.critical


def _add_charge(s: Session, *, user_id: int, request_type: str, model: str, price: float, output_models: int, input_models: int = 0):
    ch = Charge(
        user_id=user_id,
        job_id=None,
        request_type=request_type,
        provider="testprov",
        model=model,
        output_models=output_models,
        input_models=input_models,
        prompt_tokens=10,
        completion_tokens=10,
        cost_usd=Decimal("0.10"),
        price_to_user_usd=Decimal(str(price)),
        currency="USD",
        pricing_version=1,
        is_test=True,
    )
    s.add(ch)
    s.commit()


def test_pricing_averages_output_models_filter():
    client = TestClient(app)
    email = "mcfilter@example.com"
    signup_and_mark_test(client, email)
    tok = login(client, email)
    headers = {"Authorization": f"Bearer {tok}", "X-Client-Id": "test-client"}

    with SessionLocal() as s:
        u = s.query(User).filter(User.username == email).first()
        assert u is not None
        upsert_balance(s, u.id, 10_000)
        # Seed charges: tailor single-model and judge multi-model (output_models=3)
        for i in range(3):
            _add_charge(s, user_id=u.id, request_type="tailor", model=f"modelA", price=1.00 + i, output_models=1)
        for i in range(2):
            _add_charge(s, user_id=u.id, request_type="judge", model=f"modelJ", price=5.00 + i, output_models=3)

    # Fetch averages with output_models=1 (should exclude 3-count rows)
    r1 = client.get("/pricing/averages", params={"scope": "user", "output_models": 1}, headers=headers)
    assert r1.status_code == 200, r1.text
    data1 = r1.json()
    assert all(r.get("request_type") != "judge" for r in data1), data1

    # Fetch with output_models=3 (should show judge rows if any averages computed)
    r2 = client.get("/pricing/averages", params={"scope": "user", "output_models": 3}, headers=headers)
    assert r2.status_code == 200, r2.text
    data2 = r2.json()
    assert any(r.get("request_type") == "judge" for r in data2), data2

    # Median with output_models filter
    med_single = client.get("/pricing/median", params={"output_models": 1})
    assert med_single.status_code == 200
    med_multi = client.get("/pricing/median", params={"output_models": 3})
    assert med_multi.status_code == 200
    assert med_single.json() != med_multi.json()  # differing underlying dataset likely
