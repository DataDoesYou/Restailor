import uuid
import pytest

from fastapi.testclient import TestClient

from restailor.db import SessionLocal
from restailor.models import User, Job, JobOutput, Charge, UserBalance
from tests.utils import signup_and_mark_test, login, upsert_balance, totp_secret_from_start_payload
from main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _enable_totp_and_stepup(client: TestClient, bearer: str) -> str:
    """Enable TOTP for the user and perform step-up, returning X-Stepup-Token."""
    r_s = client.post("/2fa/totp/start", headers=_auth(bearer))
    assert r_s.status_code == 200, r_s.text
    secret = totp_secret_from_start_payload(r_s.json())
    import pyotp
    code = pyotp.TOTP(secret, digits=6, interval=30).now()
    r_c = client.post("/2fa/totp/confirm", json={"code": code}, headers=_auth(bearer))
    assert r_c.status_code == 200, r_c.text
    # step-up
    curr = pyotp.TOTP(secret, digits=6, interval=30).now()
    r_st = client.post("/auth/stepup/start", json={"totp_code": curr}, headers=_auth(bearer))
    assert r_st.status_code == 200, r_st.text
    step = r_st.headers.get("X-Stepup-Token")
    assert step
    return step


@pytest.mark.security
@pytest.mark.critical
@pytest.mark.parametrize("endpoint", ["/jobs", "/fit"])
def test_balance_gate_blocks_and_no_charge_then_allows_after_multiplier_drop(endpoint: str, tmp_path, client: TestClient):
    # Use a temp override path so pricing changes don’t leak across tests
    import os
    os.environ["PRICING_OVERRIDE_PATH"] = str(tmp_path / "pricing_override.json")

    email = f"bal_{uuid.uuid4()}@example.com"
    signup_and_mark_test(client, email)
    bearer = login(client, email)

    # Seed a very low balance (e.g., $0.25)
    user_id: int | None = None
    with SessionLocal() as s:
        u = s.query(User).filter(User.username == email).first()
        assert u is not None
        user_id = int(u.id)
        upsert_balance(s, user_id, 25)

    assert user_id is not None

    # Baseline counters (repo may have non-test data)
    with SessionLocal() as s:
        base_jobs = s.query(Job).filter(Job.user_id == user_id).count()
        base_charges = s.query(Charge).filter(Charge.user_id == user_id).count()
        base_charge_events = (
            s.query(JobOutput)
            .join(Job, JobOutput.job_id == Job.id)
            .filter(Job.user_id == user_id, JobOutput.type == "charge")
            .count()
        )

    # Construct a minimal request that still estimates > balance when multiplier is huge
    body_jobs = {
        "resume_text": "A",
        "jd_text": "B",
        "provider": "openai",
        "model_id": "GPT-5",
        "do_judge": False,
    }
    body_fit = {
        "resume_text": "A",
        "jd_text": "B",
        "provider": "openai",
        "model_id": "GPT-5",
        "source_page": "Test",
    }
    body = body_jobs if endpoint == "/jobs" else body_fit

    # First, push multiplier extremely high via admin override to force 402 on tiny input
    # Promote this user to admin and step-up
    with SessionLocal() as s:
        u = s.query(User).filter(User.username == email).first()
        assert u is not None
        u.role = "admin"
        s.add(u)
        s.commit()

    admin_bearer = login(client, email)
    stepup = _enable_totp_and_stepup(client, admin_bearer)
    r_admin = client.post(
        "/admin/pricing",
        headers=_auth(admin_bearer) | {"X-Stepup-Token": stepup},
        json={"multiplier": 1_000_000.0},
    )
    assert r_admin.status_code == 200, r_admin.text

    # Now call the target endpoint; expect 402 and no job/charge rows created
    r_block = client.post(endpoint, headers=_auth(bearer) | {"X-Client-Id": f"cid-{uuid.uuid4()}"}, json=body)
    assert r_block.status_code == 402, r_block.text
    j = r_block.json()
    assert j.get("detail") == "insufficient_funds"

    with SessionLocal() as s:
        # No new rows should have been created on 402
        assert s.query(Job).filter(Job.user_id == user_id).count() == base_jobs
        assert s.query(Charge).filter(Charge.user_id == user_id).count() == base_charges
        assert (
            s.query(JobOutput)
            .join(Job, JobOutput.job_id == Job.id)
            .filter(Job.user_id == user_id, JobOutput.type == "charge")
            .count()
            == base_charge_events
        )
        # Balance never goes negative
        ub = s.get(UserBalance, user_id)
        assert ub is not None and int(ub.balance_cents) >= 0
        bal_after_block = int(ub.balance_cents)

    # Drop multiplier low so the same input becomes affordable
    r_admin2 = client.post(
        "/admin/pricing",
        headers=_auth(admin_bearer) | {"X-Stepup-Token": stepup},
        json={"multiplier": 1.0},
    )
    assert r_admin2.status_code == 200, r_admin2.text

    # Retry; should now pass and create a job (ack), still no immediate ledger charge
    r_ok = client.post(endpoint, headers=_auth(bearer) | {"X-Client-Id": f"cid-{uuid.uuid4()}"}, json=body)
    assert r_ok.status_code == 200, r_ok.text
    data = r_ok.json()
    assert data.get("job_id") and data.get("access_token")

    with SessionLocal() as s:
        # One new job exists now relative to baseline
        assert s.query(Job).filter(Job.user_id == user_id).count() == base_jobs + 1
        # Worker not run in tests: no Charge rows incremented by enqueue alone
        assert s.query(Charge).filter(Charge.user_id == user_id).count() == base_charges
        # Balance still non-negative and unchanged by enqueue
        ub = s.get(UserBalance, user_id)
        assert ub is not None and int(ub.balance_cents) == bal_after_block
