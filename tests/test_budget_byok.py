import uuid

from fastapi.testclient import TestClient

from main import app
from restailor.db import SessionLocal
from restailor.models import CreditLedger, User, UserProviderKey
from .utils import signup_and_mark_test, login


def _auth_client():
    client = TestClient(app)
    email = f"budget_byok_{uuid.uuid4().hex}@example.com"
    signup_and_mark_test(client, email, "TestPassword123!")
    token = login(client, email, "TestPassword123!")
    return client, email, {"Authorization": f"Bearer {token}", "Origin": "http://localhost:3000"}


def test_budget_adjust_add_and_remove_clamps_and_writes_ledger():
    client, email, headers = _auth_client()

    add = client.post("/budget/credits/adjust", headers=headers, json={"amount_usd": 10, "direction": "add"})
    assert add.status_code == 200, add.text
    assert add.json()["balance"]["balance_cents"] >= 1000

    remove = client.post("/budget/credits/adjust", headers=headers, json={"amount_usd": 100, "direction": "remove"})
    assert remove.status_code == 200, remove.text
    assert remove.json()["balance"]["balance_cents"] == 0

    with SessionLocal() as s:
        user = s.query(User).filter(User.username == email).one()
        rows = s.query(CreditLedger).filter(CreditLedger.user_id == user.id, CreditLedger.note.like("budget_%")).all()
        assert len(rows) >= 2
        assert all(str(r.provider_ref or "").startswith(f"budget:self:{user.id}:") for r in rows)


def test_provider_key_metadata_never_returns_raw_key():
    client, email, headers = _auth_client()

    put = client.put("/users/me/provider-keys/openai", headers=headers, json={"api_key": "sk-test-abcdef123456"})
    assert put.status_code == 200, put.text
    body = put.json()
    assert body["configured"] is True
    assert body["key_tail"] == "sk...56"
    assert "abcdef123456" not in str(body)

    listed = client.get("/users/me/provider-keys", headers=headers)
    assert listed.status_code == 200
    assert "sk-test" not in listed.text

    with SessionLocal() as s:
        user = s.query(User).filter(User.username == email).one()
        row = s.query(UserProviderKey).filter(UserProviderKey.user_id == user.id, UserProviderKey.provider == "openai").one()
        assert row.key_tail == "sk...56"
        assert b"sk-test" not in bytes(row.key_enc)
