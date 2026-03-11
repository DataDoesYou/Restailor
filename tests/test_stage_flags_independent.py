from __future__ import annotations

from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from main import app
from restailor.db import SessionLocal
from restailor.models import Application, Job, AnalyticsJobSnapshotState
from tests.utils import signup_and_mark_test, login


def _auth(tok: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {tok}"}


def _make_job(client: TestClient, bearer: str) -> tuple[str, str]:
    suffix = str(uuid4())
    body = {
        "resume_text": f"Jane Doe\nExperience...\n{suffix}",
        "jd_text": f"Great Co seeks engineer {suffix}",
        "flow": "tailor",
        "source_page": "Tests",
    }
    r = client.post("/jobs", json=body, headers={"X-Client-Id": "test-client", **_auth(bearer)})
    assert r.status_code == 200, r.text
    payload = r.json()
    return payload["job_id"], payload["access_token"]


def _load_job(job_id: str) -> Job:
    with SessionLocal() as session:
        row = session.get(Job, UUID(job_id))
        assert row is not None
        session.refresh(row)
        return row


def _load_application(job_id: str) -> Application:
    with SessionLocal() as session:
        job = session.get(Job, UUID(job_id))
        assert job is not None
        app = (
            session.query(Application)
            .filter(Application.user_id == job.user_id)
            .order_by(Application.updated_at.desc())
            .first()
        )
        assert app is not None
        session.refresh(app)
        return app


def test_stage_flags_updates_stage_and_degrades_to_applied():
    client = TestClient(app)
    email = "ioh-flags@example.com"
    signup_and_mark_test(client, email)
    token = login(client, email)

    job_id, job_token = _make_job(client, token)

    # Promote job to interviewing via stage endpoint first (legacy flow)
    r_stage = client.patch(
        f"/jobs/{job_id}/stage",
        json={"stage": "interviewing"},
        headers={"X-Job-Token": job_token, **_auth(token)},
    )
    assert r_stage.status_code == 200, r_stage.text

    # Set interviewing flag true via new endpoint, expect interviewing flag to persist
    r_flag_on = client.patch(
        f"/jobs/{job_id}/stage-flags",
        json={"interviewing": True},
        headers={"X-Job-Token": job_token, **_auth(token)},
    )
    assert r_flag_on.status_code == 200, r_flag_on.text
    data_on = r_flag_on.json()
    assert data_on.get("interviewing") is True
    assert data_on.get("offer") in (False, None)
    assert data_on.get("hired") in (False, None)

    app_mid = _load_application(job_id)
    assert app_mid.is_interviewing is True

    # Now clear the interviewing flag and expect flags to revert to false
    r_flag_off = client.patch(
        f"/jobs/{job_id}/stage-flags",
        json={"interviewing": False},
        headers={"X-Job-Token": job_token, **_auth(token)},
    )
    assert r_flag_off.status_code == 200, r_flag_off.text
    data_off = r_flag_off.json()
    assert data_off.get("interviewing") is False
    assert data_off.get("offer") in (False, None)
    assert data_off.get("hired") in (False, None)

    app_final = _load_application(job_id)
    assert app_final.is_interviewing is False


def test_stage_flags_promotes_highest_stage():
    client = TestClient(app)
    email = "ioh-flags-promote@example.com"
    signup_and_mark_test(client, email)
    token = login(client, email)

    job_id, job_token = _make_job(client, token)

    # Starting flags should be cleared.
    initial_app = _load_application(job_id)
    assert initial_app.is_interviewing is False
    assert initial_app.is_offer is False
    assert initial_app.is_hired is False

    # Turn offer flag on -> offer flag should be true
    r_offer = client.patch(
        f"/jobs/{job_id}/stage-flags",
        json={"offer": True},
        headers={"X-Job-Token": job_token, **_auth(token)},
    )
    assert r_offer.status_code == 200, r_offer.text
    state_offer = r_offer.json()
    assert state_offer.get("offer") is True
    assert state_offer.get("hired") in (False, None)

    mid_app = _load_application(job_id)
    assert mid_app.is_offer is True

    # Turning hired on should set hired flag even if offer remains true
    r_hired = client.patch(
        f"/jobs/{job_id}/stage-flags",
        json={"hired": True},
        headers={"X-Job-Token": job_token, **_auth(token)},
    )
    assert r_hired.status_code == 200, r_hired.text
    state_hired = r_hired.json()
    assert state_hired.get("hired") is True
    assert state_hired.get("offer") is True

    final_app = _load_application(job_id)
    assert final_app.is_hired is True
    assert final_app.is_offer is True  # previously set


def test_application_stage_flags_patch_without_job_refreshes_snapshot():
    client = TestClient(app)
    email = "ioh-flags-no-job@example.com"
    signup_and_mark_test(client, email)
    token = login(client, email)

    body = {
        "company": "Example Co",
        "role": "Engineer",
        "jdText": "Awesome role",
        "baseText": "Great resume",
        "snapshot": {
            "jdInput": "Awesome role",
            "resumeInput": "Great resume",
        },
        "consent": True,
    }
    r_upsert = client.post("/applications/upsert", json=body, headers=_auth(token))
    assert r_upsert.status_code == 200, r_upsert.text
    applied_key = r_upsert.json()["appliedKey"]

    with SessionLocal() as session:
        app_row = session.query(Application).filter(Application.applied_key == applied_key).one()
        assert app_row.job_id is None
        user_id = app_row.user_id

    r_patch = client.patch(
        "/applications/stage-flags",
        json={"appliedKey": applied_key, "interviewing": True},
        headers=_auth(token),
    )
    assert r_patch.status_code == 200, r_patch.text
    payload = r_patch.json()
    assert payload.get("ok") is True
    assert payload.get("interviewing") is True

    with SessionLocal() as session:
        app_row = session.query(Application).filter(Application.applied_key == applied_key).one()
        assert app_row.is_interviewing is True
        snapshot_row = (
            session.query(AnalyticsJobSnapshotState)
            .filter(AnalyticsJobSnapshotState.user_id == user_id, AnalyticsJobSnapshotState.snapshot_id == app_row.id)
            .one()
        )
        assert snapshot_row.is_interviewing is True
        assert snapshot_row.is_active is True
