import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from main import app
from restailor.db import SessionLocal
from restailor.models import User, UserBalance, Charge, CreditLedger
from .utils import signup_and_mark_test, login as _login2, upsert_balance, add_charge
# Note: If future tests create Job/JobOutput rows, set is_test=True so our cleanup fixture purges them.


pytestmark = pytest.mark.critical


@pytest.fixture()
def client():
    return TestClient(app)


@pytest.fixture()
def db_session():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


def _signup(client: TestClient, email: str, password: str = "Str0ngP@ss!123") -> dict:
    return signup_and_mark_test(client, email, password)


def _login(client: TestClient, email: str, password: str = "Str0ngP@ss!123") -> str:
    return _login2(client, email, password)


def _auth_headers(tok: str) -> dict:
    return {"Authorization": f"Bearer {tok}"}


def test_pricing_averages_and_balance_and_model_filter(client: TestClient, db_session: Session):
    email = f"user_{uuid.uuid4()}@example.com"
    _signup(client, email)
    tok = _login(client, email)

    # Find user id and seed pricing data
    with SessionLocal() as s:
        u = s.query(User).filter(User.username == email).first()
        assert u is not None
        uid = int(u.id)
        # Seed balance: $100.00
        upsert_balance(s, uid, 10000)
        # Insert 120 charges for one (request_type, model) so only last 100 count
        base_time = datetime.now(timezone.utc) - timedelta(minutes=120)
        # First 20 expensive, then 100 cheap → average should be cheap value
        for i in range(20):
            add_charge(s, user_id=uid, request_type="tailor", provider="testprov", model="GPT-5", price_to_user_usd=10, cost_usd=1, created_at=base_time + timedelta(minutes=i))
        for i in range(100):
            add_charge(s, user_id=uid, request_type="tailor", provider="testprov", model="GPT-5", price_to_user_usd=2, cost_usd=1, created_at=base_time + timedelta(minutes=20 + i))
        # Add a few for another model to ensure filter works
        for i in range(3):
            add_charge(s, user_id=uid, request_type="tailor", provider="testprov", model="Claude Sonnet 4.5", price_to_user_usd=3, cost_usd=1, created_at=base_time + timedelta(minutes=200 + i))

    # After seeding charges, ensure the live DB-derived balance equals $100.00
    with SessionLocal() as s:
        u2 = s.query(User).filter(User.username == email).first()
        assert u2 is not None
        # Use helper to mirror ledger so derived balance (ledger - charges) == 10000 cents
        upsert_balance(s, int(u2.id), 10000)

    # Balance endpoint formatting (should reflect 10000 cents)
    rb = client.get("/users/me/balance", headers=_auth_headers(tok))
    assert rb.status_code == 200
    bj = rb.json()
    assert bj["balance_cents"] == 10000
    assert bj["balance_usd"] == "100.00"
    assert bj["currency"] == "USD"

    # Averages for user scope, model filter → returns dict by request_type
    ra = client.get(
        "/pricing/averages",
        params={"scope": "user", "model": "GPT-5"},
        headers=_auth_headers(tok),
    )
    assert ra.status_code == 200, ra.text
    aj = ra.json()
    # Only 'tailor' key present
    assert set(aj.keys()) == {"tailor"}
    assert aj["tailor"]["n"] == 100
    assert aj["tailor"]["avg_price_usd"] == "2.00"


def test_pricing_estimate_unknown_model_returns_400(client: TestClient):
    r = client.get("/pricing/estimate", params={"request_type": "tailor", "model": "NoSuchModel", "expected_prompt_tokens": 10, "expected_completion_tokens": 0})
    assert r.status_code == 400
    assert r.json().get("detail") == "unknown_model"


def test_pricing_estimate_includes_usd_fields(client: TestClient):
    # Public endpoint; verify both cents and formatted USD are present
    r = client.get(
        "/pricing/estimate",
        params={
            "request_type": "tailor",
            "model": "GPT-5",
            "expected_prompt_tokens": 10,
            "expected_completion_tokens": 0,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert isinstance(body.get("estimate_cents"), int)
    assert isinstance(body.get("estimate_usd"), str)
    assert body.get("currency") == "USD"


def test_pre_enqueue_blocks_when_insufficient_funds(client: TestClient, db_session: Session):
    email = f"user_{uuid.uuid4()}@example.com"
    _signup(client, email)
    tok = _login(client, email)

    # Seed tiny balance: $0.05
    with SessionLocal() as s:
        u = s.query(User).filter(User.username == email).first()
        assert u is not None
        upsert_balance(s, int(u.id), 5)

    # Use max-allowed input sizes so fixed TOML pricing estimate exceeds tiny balance.
    resume_text = "A" * 120000
    jd_text = "B" * 80000
    body = {
        "resume_text": resume_text,
        "jd_text": jd_text,
        "provider": "openai",
        "model_id": "GPT-5",  # present in config
        "do_judge": False,
    }
    rj = client.post("/jobs", headers=_auth_headers(tok) | {"X-Client-Id": "c"}, json=body)
    assert rj.status_code == 402


def test_fit_and_judge_pre_enqueue_block(client: TestClient, db_session: Session):
    email = f"user_{uuid.uuid4()}@example.com"
    _signup(client, email)
    tok = _login(client, email)

    # Seed tiny balance: $0.05
    with SessionLocal() as s:
        u = s.query(User).filter(User.username == email).first()
        assert u is not None
        upsert_balance(s, int(u.id), 5)

    resume_text = "A" * 120000
    jd_text = "B" * 80000

    # Fit should block with 402
    fit_body = {
        "resume_text": resume_text,
        "jd_text": jd_text,
        "provider": "openai",
        "model_id": "GPT-5",
        "source_page": "Test",
    }
    r_fit = client.post("/fit", headers=_auth_headers(tok) | {"X-Client-Id": "fit"}, json=fit_body)
    assert r_fit.status_code == 402, r_fit.text

    # Judge-only may block with either 400 (precondition: requires existing tailored resume) or 402 (insufficient funds)
    judge_body = {
        "resume_text": resume_text,
        "jd_text": jd_text,
        "candidate_text": "C",
        "judge_provider": "openai",
        "judge_model_id": "GPT-5",
        "source_page": "Test",
    }
    r_j = client.post("/judge", headers=_auth_headers(tok) | {"X-Client-Id": "j"}, json=judge_body)
    assert r_j.status_code in (400, 402), r_j.text
    if r_j.status_code == 400:
        assert "tailor" in (r_j.json().get("detail", "").lower())


def test_zero_and_negative_balance_block_all_jobs(client: TestClient, db_session: Session):
    email = f"user_{uuid.uuid4()}@example.com"
    _signup(client, email)
    tok = _login(client, email)

    # Set zero balance
    with SessionLocal() as s:
        u = s.query(User).filter(User.username == email).first()
        assert u is not None
        upsert_balance(s, int(u.id), 0)

    body = {"resume_text": "A", "jd_text": "B", "provider": "openai", "model_id": "GPT-5", "do_judge": False}
    r1 = client.post("/jobs", headers=_auth_headers(tok) | {"X-Client-Id": "c1"}, json=body)
    assert r1.status_code == 402
    fit_body = {"resume_text": "A", "jd_text": "B", "provider": "openai", "model_id": "GPT-5"}
    r2 = client.post("/fit", headers=_auth_headers(tok) | {"X-Client-Id": "c2"}, json=fit_body)
    assert r2.status_code == 402
    judge_body = {"resume_text": "A", "jd_text": "B", "candidate_text": "C", "judge_provider": "openai", "judge_model_id": "GPT-5"}
    r3 = client.post("/judge", headers=_auth_headers(tok) | {"X-Client-Id": "c3"}, json=judge_body)
    assert r3.status_code in (400, 402)
    if r3.status_code == 400:
        assert "tailor" in (r3.json().get("detail", "").lower())

    # Set negative balance
    with SessionLocal() as s:
        u = s.query(User).filter(User.username == email).first()
        assert u is not None
        upsert_balance(s, int(u.id), -50)

    r4 = client.post("/jobs", headers=_auth_headers(tok) | {"X-Client-Id": "c4"}, json=body)
    assert r4.status_code == 402
    r5 = client.post("/fit", headers=_auth_headers(tok) | {"X-Client-Id": "c5"}, json=fit_body)
    assert r5.status_code == 402
    r6 = client.post("/judge", headers=_auth_headers(tok) | {"X-Client-Id": "c6"}, json=judge_body)
    assert r6.status_code in (400, 402)
    if r6.status_code == 400:
        assert "tailor" in (r6.json().get("detail", "").lower())
