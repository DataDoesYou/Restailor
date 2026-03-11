from __future__ import annotations

from fastapi.testclient import TestClient

from main import app
from tests.utils import signup_and_mark_test, login
from restailor.db import SessionLocal
from restailor.models import Application, User
from restailor.applications_api import _derive_jd_projection, _derive_job_input_hashes
from backend.crypto_utils import encrypt_json
from backend.hash_utils import compute_applied_key


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_job(client: TestClient, token: str, *, resume_text: str, jd_text: str) -> tuple[str, str]:
    body = {
        "resume_text": resume_text,
        "jd_text": jd_text,
        "flow": "tailor",
        "source_page": "Tests",
    }
    resp = client.post("/jobs", json=body, headers={"X-Client-Id": "test-client", **_auth(token)})
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    return payload["job_id"], payload["access_token"]


def _set_stage(client: TestClient, token: str, job_id: str, job_token: str, stage: str) -> None:
    resp = client.patch(
        f"/jobs/{job_id}/stage",
        json={"stage": stage},
        headers={"X-Job-Token": job_token, **_auth(token)},
    )
    assert resp.status_code == 200, resp.text


def _label_from_flags(item: dict) -> str:
    if item.get("hired"):
        return "hired"
    if item.get("offer"):
        return "offer"
    if item.get("interviewing"):
        return "interviewing"
    if item.get("isApplied"):
        return "applied"
    return "unlabeled"


def _archive_job(client: TestClient, token: str, job_id: str, job_token: str) -> None:
    resp = client.post(
        f"/jobs/{job_id}/archive",
        headers={"X-Job-Token": job_token, **_auth(token)},
    )
    assert resp.status_code == 200, resp.text


def test_applications_list_stage_filter_fast_path():
    client = TestClient(app)
    email = "stage-filter-fast@example.com"
    signup_and_mark_test(client, email)
    token = login(client, email)

    job_applied_id, job_applied_token = _create_job(
        client,
        token,
        resume_text="Alice Applicant Resume",
        jd_text="Company A seeks engineer",
    )
    _set_stage(client, token, job_applied_id, job_applied_token, "applied")

    job_interview_id, job_interview_token = _create_job(
        client,
        token,
        resume_text="Bob Interview Resume",
        jd_text="Company B hiring",
    )
    _set_stage(client, token, job_interview_id, job_interview_token, "interviewing")

    job_offer_id, job_offer_token = _create_job(
        client,
        token,
        resume_text="Carol Offer Resume",
        jd_text="Company C offer role",
    )
    _set_stage(client, token, job_offer_id, job_offer_token, "offer")

    resp_interview = client.get(
        "/applications/list",
        params={"pageSize": 50, "archived": 0, "stages": "interviewing"},
        headers=_auth(token),
    )
    assert resp_interview.status_code == 200, resp_interview.text
    data_interview = resp_interview.json()
    assert data_interview["total"] == 2
    stage_set = {_label_from_flags(item) for item in data_interview["items"]}
    assert stage_set == {"interviewing", "offer"}

    resp_offer = client.get(
        "/applications/list",
        params={"pageSize": 50, "archived": 0, "stages": "offer"},
        headers=_auth(token),
    )
    assert resp_offer.status_code == 200, resp_offer.text
    data_offer = resp_offer.json()
    assert data_offer["total"] == 1
    offer_item = data_offer["items"][0]
    assert _label_from_flags(offer_item) == "offer"
    assert offer_item["interviewing"] is True
    assert offer_item["offer"] is True

    resp_applied = client.get(
        "/applications/list",
        params={"pageSize": 50, "archived": 0, "stages": "applied"},
        headers=_auth(token),
    )
    assert resp_applied.status_code == 200, resp_applied.text
    data_applied = resp_applied.json()
    assert data_applied["total"] == 1
    applied_item = data_applied["items"][0]
    assert _label_from_flags(applied_item) == "applied"
    assert applied_item["interviewing"] is False
    assert applied_item["offer"] is False
    assert applied_item["hired"] is False


def test_applications_list_archived_toggle_fast_path():
    client = TestClient(app)
    email = "archive-toggle-fast@example.com"
    signup_and_mark_test(client, email)
    token = login(client, email)

    job_active_id, job_active_token = _create_job(
        client,
        token,
        resume_text="Active Resume",
        jd_text="Active JD",
    )
    _set_stage(client, token, job_active_id, job_active_token, "applied")

    job_archived_id, job_archived_token = _create_job(
        client,
        token,
        resume_text="Archived Resume",
        jd_text="Archived JD",
    )
    _set_stage(client, token, job_archived_id, job_archived_token, "applied")
    _archive_job(client, token, job_archived_id, job_archived_token)

    resp_active = client.get(
        "/applications/list",
        params={"pageSize": 50, "archived": 0},
        headers=_auth(token),
    )
    assert resp_active.status_code == 200, resp_active.text
    data_active = resp_active.json()
    assert data_active["total"] == 1
    active_item = data_active["items"][0]
    assert active_item["isArchived"] in (False, None)
    assert active_item["appliedKey"] != ""

    resp_archived = client.get(
        "/applications/list",
        params={"pageSize": 50, "archived": 1},
        headers=_auth(token),
    )
    assert resp_archived.status_code == 200, resp_archived.text
    data_archived = resp_archived.json()
    assert data_archived["total"] == 1
    archived_item = data_archived["items"][0]
    assert archived_item["isArchived"] is True
    assert archived_item["jobId"] is not None


def test_applications_list_actions_sort_fast_path():
    client = TestClient(app)
    email = "actions-sort-fast@example.com"
    signup_and_mark_test(client, email)
    token = login(client, email)

    stages = ["applied", "interviewing", "offer", "hired"]
    for idx, stage in enumerate(stages):
        job_id, job_token = _create_job(
            client,
            token,
            resume_text=f"Resume {idx}",
            jd_text=f"JD {stage}",
        )
        _set_stage(client, token, job_id, job_token, stage)

    resp_desc = client.get(
        "/applications/list",
        params={"pageSize": 50, "archived": 0, "sort": "actions", "dir": "desc"},
        headers=_auth(token),
    )
    assert resp_desc.status_code == 200, resp_desc.text
    items_desc = resp_desc.json()["items"]
    stage_order_desc = [_label_from_flags(item) for item in items_desc[:4]]
    assert stage_order_desc == ["hired", "offer", "interviewing", "applied"]

    resp_asc = client.get(
        "/applications/list",
        params={"pageSize": 50, "archived": 0, "sort": "actions", "dir": "asc"},
        headers=_auth(token),
    )
    assert resp_asc.status_code == 200, resp_asc.text
    items_asc = resp_asc.json()["items"]
    stage_order_asc = [_label_from_flags(item) for item in items_asc[:4]]
    assert stage_order_asc == ["applied", "interviewing", "offer", "hired"]


def test_applications_list_dedup_job_variant_fast_and_slow_paths():
    client = TestClient(app)
    email = "dedup-variant@example.com"
    signup_and_mark_test(client, email)
    token = login(client, email)

    resume_text = "Resume Content For Dedup"
    jd_text = "Unique Deduplication JD text for verification"

    job_id, job_token = _create_job(
        client,
        token,
        resume_text=resume_text,
        jd_text=jd_text,
    )

    _set_stage(client, token, job_id, job_token, "interviewing")

    with SessionLocal() as session:
        user = session.query(User).filter(User.username == email).first()
        assert user is not None
        jd_hash, base_hash, _applied_key = compute_applied_key(user.id, jd_text, resume_text)
        snapshot_payload = {"jdInput": jd_text, "resumeInput": resume_text}
        jd_snippet, jd_text_norm = _derive_jd_projection(jd_text, snapshot_payload)
        job_hashes = _derive_job_input_hashes(resume_text, jd_text, snapshot_payload)
        snapshot_enc = encrypt_json(snapshot_payload, session=session)
        Application.upsert(
            session,
            user_id=user.id,
            jd_hash=jd_hash,
            base_hash=base_hash,
            snapshot_enc=snapshot_enc,
            company="Dedup Co",
            role="Engineer",
            jd_url=None,
            jd_snippet=jd_snippet,
            jd_text_norm=jd_text_norm,
            is_test=True,
            is_applied=False,
            job_input_hashes=job_hashes,
        )
        session.commit()

    resp_fast = client.get(
        "/applications/list",
        params={"pageSize": 50, "archived": 0},
        headers=_auth(token),
    )
    assert resp_fast.status_code == 200, resp_fast.text
    data_fast = resp_fast.json()
    assert data_fast["total"] == 1
    assert len(data_fast["items"]) == 1
    fast_item = data_fast["items"][0]
    assert "#job:" not in fast_item["appliedKey"]
    assert _label_from_flags(fast_item) == "interviewing"
    assert fast_item["interviewing"] is True

    resp_slow = client.get(
        "/applications/list",
        params={"pageSize": 50, "archived": 0, "search": "Deduplication"},
        headers=_auth(token),
    )
    assert resp_slow.status_code == 200, resp_slow.text
    data_slow = resp_slow.json()
    assert data_slow["total"] == 1
    assert len(data_slow["items"]) == 1
    slow_item = data_slow["items"][0]
    assert "#job:" not in slow_item["appliedKey"]
    assert _label_from_flags(slow_item) == "interviewing"
    assert slow_item["interviewing"] is True
