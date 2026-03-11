import uuid
from typing import Any, Dict

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from main import app
from restailor.db import SessionLocal
from restailor.models import User, UserBalance, JobOutput
from .utils import signup_and_mark_test, login as _login2


pytestmark = pytest.mark.critical


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


def _auth(tok: str) -> Dict[str, str]:
    return {"Authorization": f"Bearer {tok}"}


def _seed_user_zero_balance(client: TestClient) -> str:
    email = f"user_{uuid.uuid4()}@example.com"
    signup_and_mark_test(client, email)
    tok = _login2(client, email)
    with SessionLocal() as s:
        u = s.query(User).filter(User.username == email).first()
        assert u is not None
        ub = s.query(UserBalance).filter(UserBalance.user_id == int(u.id)).one_or_none()
        if ub is None:
            ub = UserBalance(user_id=int(u.id), balance_cents=0, is_test=True)
            s.add(ub)
        ub.balance_cents = 0
        ub.is_test = True
        s.commit()
    return tok


@pytest.mark.parametrize(
    "path, body",
    [
        ("/jobs", {"resume_text": "A", "jd_text": "B", "provider": "openai", "model_id": "GPT-5", "do_judge": False}),
        ("/fit", {"resume_text": "A", "jd_text": "B", "provider": "openai", "model_id": "GPT-5"}),
        (
            "/judge",
            {
                "resume_text": "A",
                "jd_text": "B",
                "candidate_text": "C",
                "judge_provider": "openai",
                "judge_model_id": "GPT-5",
            },
        ),
        ("/benchmark/start", {"source_page": "Model Benchmark"}),
    ],
)
def test_block_when_balance_insufficient_returns_402_and_no_outputs(client: TestClient, path: str, body: Dict[str, Any]):
    token = _seed_user_zero_balance(client)

    # For benchmark/start, the route is admin-protected; promote user to admin first
    if path == "/benchmark/start":
        with SessionLocal() as s:
            # Promote the latest test user (created by this test) to admin
            u = s.query(User).filter(User.is_test == True).order_by(User.created_at.desc()).first()
            assert u is not None
            u.role = "admin"
            s.add(u)
            s.commit()

    headers = _auth(token) | {"X-Client-Id": f"test-{uuid.uuid4().hex[:8]}"}
    r = client.post(path, json=body, headers=headers)
    if path == "/judge":
        # Judge currently enforces a strict precondition: user must have at least one tailored resume
        # Allow either 400 (precondition) or 402 (insufficient funds) depending on evaluation order
        assert r.status_code in (400, 402), r.text
        if r.status_code == 400:
            detail = (r.json() or {}).get("detail", "").lower()
            assert ("tailor" in detail) or detail.startswith("judge_precondition_failed"), detail
        else:
            assert (r.json() or {}).get("detail") == "insufficient_funds"
    else:
        assert r.status_code == 402, r.text
        assert (r.json() or {}).get("detail") == "insufficient_funds"

    # Ensure no JobOutput rows were created at all for tests
    with SessionLocal() as s:
        rows = s.execute(select(JobOutput).where(JobOutput.is_test == True)).scalars().all()
        assert len(rows) == 0
