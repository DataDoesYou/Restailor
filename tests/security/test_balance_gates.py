import uuid
import pytest

from fastapi.testclient import TestClient

from restailor.db import SessionLocal
from restailor.models import User, Job, JobOutput, Charge, UserBalance
from tests.utils import signup_and_mark_test, login, upsert_balance
from main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.security
@pytest.mark.critical
@pytest.mark.parametrize("endpoint", ["/jobs", "/fit"])
def test_balance_gate_blocks_and_no_charge_then_allows_after_topup(endpoint: str, client: TestClient):
    email = f"bal_{uuid.uuid4()}@example.com"
    signup_and_mark_test(client, email)
    bearer = login(client, email)

    # Seed a very low balance ($0.05)
    user_id: int | None = None
    with SessionLocal() as s:
        u = s.query(User).filter(User.username == email).first()
        assert u is not None
        user_id = int(u.id)
        upsert_balance(s, user_id, 5)

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

    # Use max-allowed request sizes so estimate exceeds tiny balance under fixed TOML pricing.
    resume_text = "A" * 120000
    jd_text = "B" * 80000
    body_jobs = {
        "resume_text": resume_text,
        "jd_text": jd_text,
        "provider": "openai",
        "model_id": "GPT-5",
        "do_judge": False,
    }
    body_fit = {
        "resume_text": resume_text,
        "jd_text": jd_text,
        "provider": "openai",
        "model_id": "GPT-5",
        "source_page": "Test",
    }
    body = body_jobs if endpoint == "/jobs" else body_fit

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

    # Top up balance so the same request becomes affordable.
    with SessionLocal() as s:
        upsert_balance(s, user_id, 10000)

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
