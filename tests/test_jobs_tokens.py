import asyncio
import json
from typing import AsyncIterator

from datetime import datetime, timedelta, timezone
import pytest
import httpx
import jwt

from main import app, _verification_secret
from restailor.db import SessionLocal
from restailor.models import User, UserBalance, CreditLedger
from restailor.security import ALGORITHM


pytestmark = pytest.mark.critical


async def _signup_and_login(ac: httpx.AsyncClient, email: str, password: str) -> str:
    # Mark CAPTCHA OK for signup
    try:
        app.state.captcha_ok_mem["e2e"] = ("ok", 9999999999)
    except Exception:
        pass
    r = await ac.post("/signup", json={"username": email, "password": password}, headers={"X-Client-Id": "e2e"})
    assert r.status_code == 200, r.text
    # Mark user verified and test for downstream writes
    with SessionLocal() as s:
        u = s.query(User).filter(User.username == email).first()
        if u is not None:
            u.is_verified = True
            u.is_test = True
            s.commit()
    # Login to get bearer
    tok = await ac.post("/token", data={"username": email, "password": password}, headers={"X-Client-Id": "e2e"})
    assert tok.status_code == 200, tok.text
    return tok.json()["access_token"]


class _Rec:
    def __init__(self):
        self.lines: list[bytes] = []
        self.events: list[tuple[str, dict]] = []

    def feed(self, chunk: bytes):
        self.lines.append(chunk)
        try:
            s = chunk.decode()
        except Exception:
            return
        for raw in s.splitlines():
            if raw.startswith("event: "):
                self._cur = raw.split(": ", 1)[1].strip()
            elif raw.startswith("data: "):
                try:
                    data = json.loads(raw.split(": ", 1)[1])
                except Exception:
                    data = {}
                self.events.append((getattr(self, "_cur", ""), data))


@pytest.mark.asyncio
async def test_jobs_tokens_stream_and_persist(monkeypatch):
    # Force mock streaming
    monkeypatch.setenv("E2E_MODE", "mock")
    # Make mock chunks concise for fast tests
    from config_loader import load_config
    cfg = load_config() or {}
    # Use default testing mock settings via env

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        import uuid
        email = f"jt1_{uuid.uuid4().hex}@example.com"
        bearer = await _signup_and_login(ac, email, "Str0ngP@ss!123")
        import uuid as _uuid
        cid = f"e2e-jobs-{_uuid.uuid4().hex[:8]}"
        headers = {"Authorization": f"Bearer {bearer}", "X-Client-Id": cid}

        # Verify email to pass protected endpoints
        exp = datetime.now(timezone.utc) + timedelta(minutes=15)
        vtoken = jwt.encode({"sub": email.lower(), "scope": "verify", "exp": exp}, _verification_secret(), algorithm=ALGORITHM)
        vr = await ac.get(f"/users/verify-email?token={vtoken}&format=json")
        assert vr.status_code == 200, vr.text

        # Seed a healthy balance so pre-enqueue pricing passes
        with SessionLocal() as s:
            u = s.query(User).filter(User.username == email).first()
            assert u is not None
            ub = s.query(UserBalance).filter(UserBalance.user_id == int(u.id)).one_or_none()
            if ub is None:
                ub = UserBalance(user_id=int(u.id), balance_cents=0, is_test=True)
                s.add(ub)
            ub.balance_cents = 10000  # $100.00
            ub.is_test = True
            s.commit()
            # Mirror in ledger so DB-derived balance matches
            s.add(
                CreditLedger(
                    user_id=int(u.id),
                    delta_cents=10000,
                    type="grant",
                    note="test_seed",
                    provider_ref=None,
                    is_test=True,
                )
            )
            s.commit()

        # Create a /jobs job
        body = {
            "resume_text": "SUMMARY\nExperience...",
            "jd_text": "Role description...",
            "provider": "openai",
            "model_id": "GPT-5",
            "do_judge": False,
        }
        r = await ac.post("/jobs", json=body, headers=headers)
        assert r.status_code == 200, r.text
        job = r.json()
        jid = job["job_id"]
        tok = job["access_token"]

        # Stream tokens
        rec = _Rec()
        async with ac.stream(
            "GET",
            f"/jobs/{jid}/tokens",
            headers={**headers, "X-Job-Token": tok},
            params={"provider": "openai", "model_id": "GPT-5", "role": "tailor"},
        ) as resp:
            assert resp.status_code == 200
            async for chunk in resp.aiter_bytes():
                rec.feed(chunk)

        # Must have at least one token; 'done' may occasionally be missing if stream ends abruptly
        kinds = [k for k, _ in rec.events]
        assert "token" in kinds
        done_payload = next((d for (k, d) in reversed(rec.events) if k == "done"), None)
        if done_payload is not None:
            assert (done_payload.get("status") in ("completed", "failed"))

        # Poll status (meta may reflect queued/processing if worker isn't running)
        s = await ac.get(f"/jobs/{jid}/status", headers=headers)
        # Redis may be disabled for tests; 404 is acceptable
        if s.status_code == 200:
            js = s.json()
            assert "state" in js

        # If completed, result endpoint should 200 with artifact
        if rec.events and rec.events[-1][0] == "done" and rec.events[-1][1].get("status") == "completed":
            out = await ac.get(f"/jobs/{jid}/result", headers={**headers, "X-Job-Token": tok})
            # artifact may be 404 if Redis artifact buffer is not set; accept 200 or 404 detail
            assert out.status_code in (200, 404)


@pytest.mark.asyncio
async def test_fit_and_judge_tokens_and_cancel(monkeypatch):
    # Mock streaming mode
    monkeypatch.setenv("E2E_MODE", "mock")

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        import uuid
        email = f"jt2_{uuid.uuid4().hex}@example.com"
        bearer = await _signup_and_login(ac, email, "Str0ngP@ss!123")
        import uuid as _uuid
        cid_fit = f"e2e-fit-{_uuid.uuid4().hex[:8]}"
        headers_fit = {"Authorization": f"Bearer {bearer}", "X-Client-Id": cid_fit}

        # Verify email before hitting job endpoints
        exp = datetime.now(timezone.utc) + timedelta(minutes=15)
        vtoken = jwt.encode({"sub": email.lower(), "scope": "verify", "exp": exp}, _verification_secret(), algorithm=ALGORITHM)
        vr = await ac.get(f"/users/verify-email?token={vtoken}&format=json")
        assert vr.status_code == 200, vr.text

        # Seed balance for this user
        with SessionLocal() as s:
            u = s.query(User).filter(User.username == email).first()
            assert u is not None
            ub = s.query(UserBalance).filter(UserBalance.user_id == int(u.id)).one_or_none()
            if ub is None:
                ub = UserBalance(user_id=int(u.id), balance_cents=0, is_test=True)
                s.add(ub)
            ub.balance_cents = 10000
            ub.is_test = True
            s.commit()
            # Mirror in ledger so DB-derived balance matches
            s.add(
                CreditLedger(
                    user_id=int(u.id),
                    delta_cents=10000,
                    type="grant",
                    note="test_seed",
                    provider_ref=None,
                    is_test=True,
                )
            )
            s.commit()

        # Fit
        fbody = {
            "resume_text": "SUMMARY\nGood stuff",
            "jd_text": "Role desc",
            "provider": "openai",
            "model_id": "GPT-5",
        }
        fr = await ac.post("/fit", json=fbody, headers=headers_fit)
        assert fr.status_code == 200
        fj = fr.json(); fid = fj["job_id"]; ftok = fj["access_token"]

        # Judge
        # New precondition: require at least one prior tailored resume/job. Seed a completed tailor job for this user.
        with SessionLocal() as s:
            u = s.query(User).filter(User.username == email).first()
            assert u is not None
            from restailor.models import Job
            tj = Job(user_id=int(u.id), status="completed", job_flow="tailor", input_hash="h", access_token="tok", is_test=True)
            s.add(tj); s.commit()
        jbody = {
            "resume_text": "R",
            "jd_text": "J",
            "candidate_text": "C",
            "judge_provider": "openai",
            "judge_model_id": "GPT-5",
        }
        cid_judge = f"e2e-judge-{_uuid.uuid4().hex[:8]}"
        headers_judge = {"Authorization": f"Bearer {bearer}", "X-Client-Id": cid_judge}
        jr = await ac.post("/judge", json=jbody, headers=headers_judge)
        assert jr.status_code == 200
        jj = jr.json(); jid = jj["job_id"]; jtok = jj["access_token"]

        # Start streaming on judge and cancel mid-stream
        rec2 = _Rec()
        # Kick off stream task
        async def _consume():
            async with ac.stream(
                "GET",
                f"/jobs/{jid}/tokens",
                headers={**headers_judge, "X-Job-Token": jtok},
                params={"provider": "openai", "model_id": "GPT-5", "role": "judge"},
            ) as resp:
                assert resp.status_code == 200
                async for chunk in resp.aiter_bytes():
                    rec2.feed(chunk)

        t = asyncio.create_task(_consume())
        # Give it a moment to receive a token
        await asyncio.sleep(0.1)
        # Request cancel
        cr = await ac.post(f"/jobs/{jid}/cancel", headers=headers_judge)
        assert cr.status_code in (200, 202, 409)
        # Wait for stream to finish
        try:
            await asyncio.wait_for(t, timeout=5)
        except asyncio.TimeoutError:
            t.cancel()
            with pytest.raises(asyncio.CancelledError):
                await t

        # We expect at least one token, and if a final 'done' event is present, its status should reflect termination.
        kinds2 = [k for k, _ in rec2.events]
        assert "token" in kinds2
        last_done = next((d for (k, d) in reversed(rec2.events) if k == "done"), None)
        if last_done is not None:
            assert last_done.get("status") in ("canceled", "failed", "completed")
