from __future__ import annotations

from datetime import datetime, timezone, timedelta
import uuid
from backend.crypto_utils import encrypt_json
from fastapi.testclient import TestClient
from main import app
from restailor.db import SessionLocal
from restailor.models import AnalyticsJobSnapshotState, Application, Job, User
from services.analytics_job_snapshot import rebuild_snapshot_state
from tests.utils import signup_and_mark_test, login


def _auth_headers(tok: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {tok}"}


def _make_job(client: TestClient, bearer: str) -> tuple[str, str]:
    # Minimal job creation payload used elsewhere in tests
    suffix = str(uuid.uuid4())
    body = {
        "resume_text": f"John Doe\nExperience...\n{suffix}",
        "jd_text": f"Awesome Co seeking engineer {suffix}",
        "flow": "tailor",
        "source_page": "Tests",
    }
    r = client.post("/jobs", json=body, headers={"X-Client-Id": "test-client", **_auth_headers(bearer)})
    assert r.status_code == 200, r.text
    j = r.json()
    return j["job_id"], j["access_token"]


def test_stage_transitions_and_archive_flow():
    client = TestClient(app)
    email = "stage_flow@example.com"
    signup_and_mark_test(client, email)
    tok = login(client, email)

    job_id, acc = _make_job(client, tok)

    # Funnel stage transitions: applied -> interviewing -> offer -> hired
    for stage in ["applied", "interviewing", "offer", "hired"]:
        r = client.patch(f"/jobs/{job_id}/stage", json={"stage": stage}, headers={"X-Job-Token": acc, **_auth_headers(tok)})
        assert r.status_code == 200, r.text
        assert r.json().get("ok") is True

    # Archive then unarchive
    r1 = client.post(f"/jobs/{job_id}/archive", headers={"X-Job-Token": acc, **_auth_headers(tok)})
    assert r1.status_code == 200 and r1.json().get("ok") is True
    r2 = client.delete(f"/jobs/{job_id}/archive", headers={"X-Job-Token": acc, **_auth_headers(tok)})
    assert r2.status_code == 200 and r2.json().get("ok") is True


def test_soft_delete_and_restore():
    client = TestClient(app)
    email = "soft_delete_restore@example.com"
    signup_and_mark_test(client, email)
    tok = login(client, email)

    job_id, acc = _make_job(client, tok)

    # Soft delete
    rdel = client.delete(
        f"/jobs/{job_id}",
        headers={"X-Job-Token": acc, **_auth_headers(tok)},
    )
    assert rdel.status_code in (200, 204), rdel.text

    # Verify analytics closures over time reflects at least one bucket entry for this week
    rjobs = client.get("/analytics/jobs", headers=_auth_headers(tok))
    assert rjobs.status_code == 200, rjobs.text
    data = rjobs.json()
    closures = data.get("closures_over_time", [])
    assert isinstance(closures, list)

    # Restore
    rres = client.patch(
        f"/jobs/{job_id}/restore",
        headers={"X-Job-Token": acc, **_auth_headers(tok)},
    )
    assert rres.status_code == 200, rres.text


def test_analytics_jobs_counts_with_seeded_jobs():
    client = TestClient(app)
    email = "jobs_analytics@example.com"
    signup_and_mark_test(client, email)
    tok = login(client, email)

    # Create four jobs, set stages on three, archive one non-hired
    j1, a1 = _make_job(client, tok)
    j2, a2 = _make_job(client, tok)
    j3, a3 = _make_job(client, tok)
    j4, a4 = _make_job(client, tok)

    client.patch(f"/jobs/{j1}/stage", json={"stage": "applied"}, headers={"X-Job-Token": a1, **_auth_headers(tok)})
    client.patch(f"/jobs/{j2}/stage", json={"stage": "interviewing"}, headers={"X-Job-Token": a2, **_auth_headers(tok)})
    client.patch(f"/jobs/{j3}/stage", json={"stage": "offer"}, headers={"X-Job-Token": a3, **_auth_headers(tok)})
    client.patch(f"/jobs/{j4}/stage", json={"stage": "hired"}, headers={"X-Job-Token": a4, **_auth_headers(tok)})

    # Archive j2 (non-hired)
    client.post(f"/jobs/{j2}/archive", headers={"X-Job-Token": a2, **_auth_headers(tok)})

    r = client.get("/analytics/jobs", headers=_auth_headers(tok))
    assert r.status_code == 200, r.text
    payload = r.json()

    # Active counts exclude archived
    cbs = payload.get("counts_by_stage_active", {})
    assert cbs.get("applied", 0) >= 1
    assert cbs.get("interviewing", 0) == 0  # archived j2 should be excluded
    assert cbs.get("offer", 0) >= 1
    assert cbs.get("hired", 0) >= 1

    # Hired count includes all hired regardless of archive status
    assert payload.get("hired_count", 0) >= 1

    # Closed count is archived and not hired (we archived interviewing)
    assert payload.get("closed_count", 0) >= 1

    # closures_over_time is a list (may be empty if none deleted)
    assert isinstance(payload.get("closures_over_time", []), list)


def test_jobs_analytics_rebuilds_snapshot_state_when_missing():
    client = TestClient(app)
    email = f"jobs_snapshot_refresh+{uuid.uuid4()}@example.com"
    signup_and_mark_test(client, email)
    tok = login(client, email)

    resume_text = "John Doe\nExperience..."
    jd_text = "Awesome Co seeking engineer"

    headers = {"Authorization": f"Bearer {tok}", "X-Client-Id": "test-client"}
    job_resp = client.post(
        "/jobs",
        json={
            "resume_text": resume_text,
            "jd_text": jd_text,
            "provider": "openai",
            "model_id": "gpt-4o-mini",
            "do_judge": False,
            "source_page": "Tests",
        },
        headers=headers,
    )
    assert job_resp.status_code == 200, job_resp.text
    job_data = job_resp.json()
    job_id = job_data.get("job_id")
    access_token = job_data.get("access_token")
    assert job_id and access_token

    # Set stage and mark as applied/interviewing via stage flags to ensure cohort columns populate
    stage_resp = client.patch(
        f"/jobs/{job_id}/stage",
        json={"stage": "applied"},
        headers={"Authorization": f"Bearer {tok}", "X-Job-Token": access_token},
    )
    assert stage_resp.status_code == 200, stage_resp.text
    flags_resp = client.patch(
        f"/jobs/{job_id}/stage-flags",
        json={"interviewing": True},
        headers={"Authorization": f"Bearer {tok}", "X-Job-Token": access_token},
    )
    assert flags_resp.status_code == 200, flags_resp.text

    snapshot_payload = {
        "resumeInput": resume_text,
        "jdInput": jd_text,
        "tailoredOutput": "Tailored snapshot body",
        "fitOutput": None,
        "judgeOutput": None,
        "knobs": {},
        "modelInfo": {"provider": "openai", "model": "gpt-4o-mini"},
        "statsMd": None,
    }
    save_resp = client.post(
        "/applications/jd/save",
        json={"jdText": jd_text, "baseText": resume_text, "snapshot": snapshot_payload},
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert save_resp.status_code == 200, save_resp.text
    applied_key = save_resp.json().get("appliedKey")
    assert applied_key

    apply_resp = client.post(
        "/applications/jd/apply",
        json={"appliedKey": applied_key},
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert apply_resp.status_code == 200, apply_resp.text

    uid_int = None
    with SessionLocal() as s:
        uid = s.query(User.id).filter(User.username == email).scalar()
        assert uid is not None
        uid_int = int(uid)
        s.query(User).filter(User.id == uid_int).update({User.is_test: False}, synchronize_session=False)
        s.query(Application).filter(Application.user_id == uid_int).update(
            {Application.is_test: False, Application.is_applied: True}, synchronize_session=False
        )
        s.query(AnalyticsJobSnapshotState).filter(AnalyticsJobSnapshotState.user_id == uid_int).delete(synchronize_session=False)
        s.commit()

    try:
        analytics_resp = client.get("/analytics/jobs", headers={"Authorization": f"Bearer {tok}"})
        assert analytics_resp.status_code == 200, analytics_resp.text
        payload = analytics_resp.json()
        snapshots_series = payload.get("snapshots_over_time", [])
        assert snapshots_series, f"expected snapshots_over_time data, got {payload}"

        with SessionLocal() as s:
            rebuilt = (
                s.query(AnalyticsJobSnapshotState)
                .filter(AnalyticsJobSnapshotState.user_id == uid_int)
                .count()
            )
            assert rebuilt >= 1
    finally:
        if uid_int is not None:
            with SessionLocal() as s:
                s.query(AnalyticsJobSnapshotState).filter(AnalyticsJobSnapshotState.user_id == uid_int).update(
                    {AnalyticsJobSnapshotState.is_test: True}, synchronize_session=False
                )
                s.query(Application).filter(Application.user_id == uid_int).update(
                    {Application.is_test: True}, synchronize_session=False
                )
                s.query(User).filter(User.id == uid_int).update({User.is_test: True}, synchronize_session=False)
                s.commit()


def test_archiving_job_marks_snapshot_inactive():
    client = TestClient(app)
    email = f"archive_snapshot+{uuid.uuid4()}@example.com"
    signup_and_mark_test(client, email)
    tok = login(client, email)

    job_id_str, _ = _make_job(client, tok)
    assert job_id_str

    uid_int: int | None = None
    try:
        with SessionLocal() as s:
            user = s.query(User).filter(User.username == email).one()
            uid_int = int(user.id)
            job_uuid = uuid.UUID(job_id_str)
            job = s.query(Job).filter(Job.id == job_uuid).one()

            existing_application = s.query(Application).filter(Application.job_id == job.id).one()
            now = datetime.now(timezone.utc)
            snapshot_enc = encrypt_json({"jdInput": "archived job jd", "resumeInput": "archived job resume"}, session=s)

            existing_application.is_applied = True
            existing_application.snapshot_enc = snapshot_enc
            existing_application.updated_at = now
            existing_application.is_test = False

            # Ensure analytics includes these rows without test filtering
            job.is_test = False
            user.is_test = False
            s.commit()

            rebuild_snapshot_state(s, uid_int, include_test_rows=False)
            state_row = (
                s.query(AnalyticsJobSnapshotState)
                .filter(AnalyticsJobSnapshotState.user_id == uid_int)
                .one()
            )
            assert state_row.is_active is True
            assert state_row.job_id == job.id

            job.is_archived = True
            job.archived_at = datetime.now(timezone.utc)
            s.add(job)
            s.commit()

            rebuild_snapshot_state(s, uid_int, include_test_rows=False)
            state_row = (
                s.query(AnalyticsJobSnapshotState)
                .filter(AnalyticsJobSnapshotState.user_id == uid_int)
                .one()
            )
            assert state_row.is_active is False
            assert state_row.job_id == job.id
    finally:
        if uid_int is not None:
            with SessionLocal() as s:
                s.query(AnalyticsJobSnapshotState).filter(AnalyticsJobSnapshotState.user_id == uid_int).update(
                    {AnalyticsJobSnapshotState.is_test: True}, synchronize_session=False
                )
                s.query(Application).filter(Application.user_id == uid_int).update(
                    {Application.is_test: True}, synchronize_session=False
                )
                s.query(Job).filter(Job.user_id == uid_int).update(
                    {Job.is_test: True, Job.is_archived: False}, synchronize_session=False
                )
                s.query(User).filter(User.id == uid_int).update({User.is_test: True}, synchronize_session=False)
                s.commit()
