import uuid
import pytest
import httpx

from main import app
from restailor.db import SessionLocal
from restailor.models import User, Charge, Job
from worker import judge_ranking
import sqlalchemy as sa

pytestmark = pytest.mark.critical


async def _signup(ac: httpx.AsyncClient, username: str, password: str) -> str:
    r = await ac.post("/signup", json={"username": username, "password": password}, headers={"X-Client-Id": "e2e"})
    assert r.status_code == 200, r.text
    # Mark user verified directly (stay non-admin to avoid pending_2fa)
    with SessionLocal() as s:
        u = s.query(User).filter(User.username == username).first()
        assert u is not None
        s.execute(
            sa.text("UPDATE users SET is_verified = true, is_test = true WHERE id = :id").bindparams(id=u.id)
        )
        s.commit()
    tok = await ac.post("/token", data={"username": username, "password": password}, headers={"X-Client-Id": "e2e"})
    assert tok.status_code == 200, tok.text
    return tok.json()["access_token"]


@pytest.mark.asyncio
async def test_judge_output_models_charge(monkeypatch):
    monkeypatch.setenv("DISABLE_REDIS", "1")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        user_email = f"judge_mc_{uuid.uuid4().hex[:8]}@example.com"
        bearer = await _signup(ac, user_email, "Str0ngP@ss!123")
        headers = {"Authorization": f"Bearer {bearer}", "X-Client-Id": f"benchmark:{uuid.uuid4().hex[:6]}"}
        # Provide dummy redis so /benchmark/rank can enqueue without real Redis
        class _DummyRedis:
            async def enqueue_job(self, *a, **k):
                return None
        try:
            app.state.redis = _DummyRedis()  # type: ignore[attr-defined]
        except Exception:
            pass
        # Insert a completed tailor job for this user to satisfy precondition
        with SessionLocal() as s:
            u = s.query(User).filter(User.username == user_email).first()
            assert u is not None
            tj = Job(
                status="completed",
                input_hash="x",
                job_flow="tailor",
                source_page="Resume Tailor",
                access_token="t",
                client_id=None,
                user_id=u.id,
                is_test=True,
            )
            s.add(tj)
            s.commit()
        # Start ranking job with 3 candidates
        resp = await ac.post(
            "/benchmark/rank",
            json={
                "base_resume": "Base",
                "jd_text": "JD",
                "candidates": {"A": "r1", "B": "r2", "C": "r3"},
                "judge_provider": "openai",
                "judge_model_id": "GPT-5",
                "source_page": "Model Benchmark"
            },
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        job_id = resp.json()["job_id"]
        # Ensure user ownership (already set by endpoint) and status processing
        with SessionLocal() as s:
            job = s.get(Job, job_id)
            assert job is not None
            assert job.user_id is not None
        # Monkeypatch stream_model to emit deterministic small output quickly
        async def _fake_stream(**kwargs):  # type: ignore
            yield "tok1"
            yield "tok2"
        import services.llm as llm_mod
        monkeypatch.setattr(llm_mod, "stream_model", lambda *a, **k: _fake_stream())
        # Run worker ranking (direct invocation)
        ctx = {"redis": None}
        res = await judge_ranking(ctx, job_id=str(job_id), candidates={"A": "r1", "B": "r2", "C": "r3"}, judge_provider="openai", judge_model_id="GPT-5")
        assert res == "OK"
        # Verify charge row
        with SessionLocal() as s:
            chs = s.query(Charge).filter(Charge.job_id == job_id).all()
            assert len(chs) == 1, "expected exactly one charge for ranking job"
            ch = chs[0]
            assert ch.request_type == "judge"
            assert ch.output_models == 3, f"output_models should be 3, got {ch.output_models}"
            # Ranking job has no upstream tailor batch; input_models should be 0 or null (schema makes it nullable). Accept 0 or None.
            assert (ch.input_models in (0, None)), f"input_models should be 0/None, got {ch.input_models}"
            assert ch.prompt_tokens >= 0 and ch.completion_tokens >= 0
