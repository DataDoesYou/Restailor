import uuid, httpx, pytest
from main import app
from restailor.db import SessionLocal
from restailor.models import User
import sqlalchemy as sa

pytestmark = pytest.mark.critical

async def _signup(ac: httpx.AsyncClient, username: str, password: str) -> str:
    r = await ac.post("/signup", json={"username": username, "password": password}, headers={"X-Client-Id": "e2e"})
    assert r.status_code == 200, r.text
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
async def test_benchmark_rank_requires_tailor(monkeypatch):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        email = f"precond_rank_{uuid.uuid4().hex[:6]}@example.com"
        bearer = await _signup(ac, email, "Str0ngP@ss!123")
        headers = {"Authorization": f"Bearer {bearer}", "X-Client-Id": f"benchmark:{uuid.uuid4().hex[:6]}"}
        class _DummyRedis:
            async def enqueue_job(self, *a, **k):
                return None
        try: app.state.redis = _DummyRedis()
        except Exception: pass
        resp = await ac.post("/benchmark/rank", json={"base_resume": "B","jd_text": "JD","candidates": {"A":"r1"},"judge_provider": "openai","judge_model_id": "GPT-X"}, headers=headers)
        assert resp.status_code == 400, resp.text
        assert "tailored resume" in resp.text.lower()

@pytest.mark.asyncio
async def test_single_judge_requires_tailor(monkeypatch):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        email = f"precond_judge_{uuid.uuid4().hex[:6]}@example.com"
        bearer = await _signup(ac, email, "Str0ngP@ss!123")
        headers = {"Authorization": f"Bearer {bearer}", "X-Client-Id": f"cj:{uuid.uuid4().hex[:6]}"}
        class _DummyRedis:
            async def enqueue_job(self, *a, **k):
                return None
        try: app.state.redis = _DummyRedis()
        except Exception: pass
        resp = await ac.post("/judge", json={"resume_text": "R","jd_text": "JD","candidate_text": "Cand","judge_provider": "openai","judge_model_id": "GPT-X"}, headers=headers)
        assert resp.status_code == 400, resp.text
        assert "tailored resume" in resp.text.lower()
