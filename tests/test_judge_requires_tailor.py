from __future__ import annotations

from fastapi.testclient import TestClient

from main import app
from restailor.db import SessionLocal
from restailor.models import User
from tests.utils import signup_and_mark_test, login, upsert_balance
import pytest
pytestmark = pytest.mark.critical


def test_judge_requires_tailor_before_run():
    client = TestClient(app)
    email = "judge_need_tailor@example.com"
    signup_and_mark_test(client, email)
    tok = login(client, email)
    headers = {"Authorization": f"Bearer {tok}", "X-Client-Id": "judge-need-tailor"}
    # Give user balance so credit gate passes and we exercise new validation
    with SessionLocal() as s:
        u = s.query(User).filter(User.username == email).first()
        assert u is not None
        upsert_balance(s, u.id, 50_00)
    # Attempt judge without any tailor job for this user
    body = {
        "resume_text": "My resume text",
        "jd_text": "Job description text",
        "candidate_text": "Candidate tailored resume placeholder",  # Provided but no actual tailor job present
        "judge_provider": "openai",
        "judge_model_id": "gpt-4o-mini",
    }
    r = client.post("/judge", json=body, headers=headers)
    assert r.status_code == 400, r.text
    detail = (r.json().get("detail") or "").lower()
    assert ("requires an existing tailored resume" in detail) or detail.startswith("judge_precondition_failed"), detail
