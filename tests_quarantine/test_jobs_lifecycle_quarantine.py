# Quarantine copy for slower CI runs or flakes
from __future__ import annotations

from fastapi.testclient import TestClient
from main import app
from tests.utils import signup_and_mark_test, login


def _auth_headers(tok: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {tok}"}


def test_jobs_analytics_endpoint_smoke():
    client = TestClient(app)
    email = "jobs_analytics_smoke@example.com"
    signup_and_mark_test(client, email)
    tok = login(client, email)

    r = client.get("/analytics/jobs", headers=_auth_headers(tok))
    assert r.status_code == 200
    data = r.json()
    assert set(["counts_by_stage_active", "hired_count", "closed_count", "closures_over_time", "funnel_active"]).issubset(data.keys())
