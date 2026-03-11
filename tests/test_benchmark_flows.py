import asyncio
from datetime import datetime, timedelta, timezone
import uuid as _uuid

import httpx
import jwt
import pytest
from urllib.parse import urlparse, parse_qs

from main import app, _verification_secret
from restailor.db import SessionLocal
from restailor.models import User, Job
from restailor.security import ALGORITHM

pytestmark = pytest.mark.critical


async def _signup_admin_and_login(ac: httpx.AsyncClient, email: str, password: str) -> str:
    # Bypass CAPTCHA for tests
    try:
        app.state.captcha_ok_mem["e2e"] = ("ok", 9999999999)
    except Exception:
        pass
    r = await ac.post("/signup", json={"username": email, "password": password}, headers={"X-Client-Id": "e2e"})
    assert r.status_code == 200, r.text
    # Verify email so protected endpoints are accessible
    exp = datetime.now(timezone.utc) + timedelta(minutes=15)
    vtoken = jwt.encode({"sub": email.lower(), "scope": "verify", "exp": exp}, _verification_secret(), algorithm=ALGORITHM)
    vr = await ac.get(f"/users/verify-email?token={vtoken}&format=json")
    assert vr.status_code == 200, vr.text
    # Promote to admin
    with SessionLocal() as s:
        u = s.query(User).filter(User.username == email).first()
        assert u is not None
        u.role = "admin"
        u.is_test = True
        s.commit()
    # Login (admins require 2FA; login returns a pending_2fa token until step2 completes)
    tok = await ac.post("/token", data={"username": email, "password": password}, headers={"X-Client-Id": "e2e"})
    assert tok.status_code == 200, tok.text
    pending = tok.json()["access_token"]

    # Enroll TOTP for the admin (tests expose secret with STRICT_SECRETS=0)
    r_totp = await ac.post("/2fa/totp/start", headers={"Authorization": f"Bearer {pending}"})
    assert r_totp.status_code == 200, r_totp.text
    data = r_totp.json() or {}
    # Prefer direct secret, else parse from otpauth URI
    secret = (data.get("secret") or "").strip()
    if not secret:
        uri = (data.get("otpauth_uri") or data.get("uri") or "").strip()
        assert uri, data
        q = parse_qs(urlparse(uri).query)
        secret = (q.get("secret") or [""])[0].strip()
    assert secret, data
    import pyotp
    code = pyotp.TOTP(secret, digits=6, interval=30).now()
    r_conf = await ac.post("/2fa/totp/confirm", json={"code": code}, headers={"Authorization": f"Bearer {pending}"})
    assert r_conf.status_code == 200, r_conf.text

    # Complete step2 to exchange pending token for a real bearer token
    curr = pyotp.TOTP(secret, digits=6, interval=30).now()
    r_step2 = await ac.post("/auth/step2", json={"code": curr}, headers={"Authorization": f"Bearer {pending}"})
    assert r_step2.status_code == 200, r_step2.text
    bearer = (r_step2.json() or {}).get("access_token")
    assert isinstance(bearer, str) and bearer, r_step2.text
    return bearer


@pytest.mark.asyncio
async def test_benchmark_start_rank_await_and_save(monkeypatch):
    # Prefer in-memory run registry
    monkeypatch.setenv("DISABLE_REDIS", "1")

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        # Minimal fake redis to satisfy enqueue_job usage in /benchmark/rank
        class _FakeRedis:
            pool = None
            async def enqueue_job(self, *args, **kwargs):
                return None

        # Ensure attribute exists on state before hitting endpoints
        try:
            app.state.redis = getattr(app.state, "redis", None) or _FakeRedis()
        except Exception:
            pass
        email = f"bench_{_uuid.uuid4().hex}@example.com"
        bearer = await _signup_admin_and_login(ac, email, "Str0ngP@ss!123")
        common_headers = {"Authorization": f"Bearer {bearer}", "X-Client-Id": f"benchmark:e2e-{_uuid.uuid4().hex[:8]}"}

        # 1) Start returns run id (container job id)
        src = f"Model Benchmark {_uuid.uuid4().hex[:6]}"
        sr = await ac.post("/benchmark/start", json={"source_page": src}, headers=common_headers)
        assert sr.status_code == 200, sr.text
        sdata = sr.json(); run_id = sdata["job_id"]; assert run_id

        # Seed a completed tailor job for this admin to satisfy judge/history precondition used by benchmark rank
        from restailor.db import SessionLocal
        from restailor.models import Job, User
        with SessionLocal() as s:
            u = s.query(User).filter(User.username == email).first()
            if u is not None:
                tj = Job(user_id=int(u.id), status="completed", job_flow="tailor", input_hash="h", access_token="tok", is_test=True)
                s.add(tj); s.commit()

        # 2) Create a ranking job attached to the run
        rr = await ac.post(
            "/benchmark/rank",
            json={
                "base_resume": "Base R",
                "jd_text": "JD",
                "candidates": {"m1": "R1", "m2": "R2"},
                "judge_provider": "openai",
                "judge_model_id": "GPT-5",
                "source_page": src,
            },
            headers={**common_headers, "X-Run-Id": run_id},
        )
        assert rr.status_code == 200, rr.text
        rdata = rr.json(); rank_job_id = rdata["job_id"]; rank_tok = rdata["access_token"]

        # 3) Persist a snapshot via /benchmark/save using the job token
        # Ensure the job has an owner so persistence checks pass
        with SessionLocal() as s:
            u = s.query(User).filter(User.username == email).first()
            j = s.get(Job, rank_job_id)
            if j is not None and u is not None:
                j.user_id = int(u.id)
                s.commit()
        bench_md = "# Ranked Results\n\n- m1\n- m2"
        sv = await ac.post(
            "/benchmark/save",
            json={"job_id": rank_job_id, "bench_md": bench_md, "raw_md": "*raw*"},
            headers={**common_headers, "X-Job-Token": rank_tok},
        )
        assert sv.status_code == 200, sv.text
        assert sv.json().get("ok") is True

        # 4) Simulate worker completion of the ranking job
        with SessionLocal() as s:
            job = s.get(Job, rank_job_id)
            assert job is not None
            job.status = "completed"
            s.commit()

        # 5) Await returns ranked results
        aw = await ac.post(
            "/benchmark/await_and_judge",
            json={"run_id": run_id, "timeout_sec": 5},
            headers={k: v for k, v in common_headers.items() if k != "X-Client-Id"},
        )
        assert aw.status_code == 200, aw.text
        ad = aw.json(); assert ad.get("status") == "completed"
        assert isinstance(ad.get("ranked_text"), str) and ad["ranked_text"].strip()


@pytest.mark.asyncio
async def test_benchmark_invalids(monkeypatch):
    monkeypatch.setenv("DISABLE_REDIS", "1")

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        email = f"bench_bad_{_uuid.uuid4().hex}@example.com"
        bearer = await _signup_admin_and_login(ac, email, "Str0ngP@ss!123")
        headers = {"Authorization": f"Bearer {bearer}", "X-Client-Id": f"benchmark:e2e-{_uuid.uuid4().hex[:8]}"}

        # Invalid run id for await: returns failed (not a 4xx)
        aw = await ac.post("/benchmark/await_and_judge", json={"run_id": "nonexistent", "timeout_sec": 5}, headers=headers)
        assert aw.status_code == 200
        assert aw.json().get("status") == "failed"

        # Invalid save: unknown job id -> 404 (or 400/403 depending on access check ordering)
        from uuid import uuid4
        bad_id = str(uuid4())
        sv = await ac.post(
            "/benchmark/save",
            json={"job_id": bad_id, "bench_md": "# Hi"},
            headers={**headers, "X-Job-Token": "bad"},
        )
        assert sv.status_code in (400, 403, 404)
