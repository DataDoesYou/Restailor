import uuid, httpx, pytest, re, json
from main import app
from restailor.db import SessionLocal
from restailor.models import User, JobOutput, Job
import sqlalchemy as sa
pytestmark = pytest.mark.critical

async def _signup(ac: httpx.AsyncClient, username: str, password: str) -> str:
    r = await ac.post('/signup', json={'username': username, 'password': password}, headers={'X-Client-Id': 'e2e'})
    assert r.status_code == 200, r.text
    with SessionLocal() as s:
        u = s.query(User).filter(User.username == username).first(); assert u
        s.execute(
            sa.text('UPDATE users SET is_verified = true, is_test = true WHERE id = :id').bindparams(id=u.id)
        ); s.commit()
    tok = await ac.post('/token', data={'username': username, 'password': password}, headers={'X-Client-Id': 'e2e'})
    assert tok.status_code == 200, tok.text
    return tok.json()['access_token']

@pytest.mark.asyncio
async def test_benchmark_alias_map_persisted(monkeypatch):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url='http://test') as ac:
        email = f"alias_rank_{uuid.uuid4().hex[:6]}@example.com"
        bearer = await _signup(ac, email, 'Str0ngP@ss!123')
        headers = {'Authorization': f'Bearer {bearer}', 'X-Client-Id': f'benchmark:{uuid.uuid4().hex[:6]}'}
        class _DummyRedis:
            async def enqueue_job(self,*a,**k):
                return None
        try: app.state.redis = _DummyRedis()
        except Exception: pass
        # Insert a completed tailor job to satisfy precondition
        with SessionLocal() as s:
            u = s.query(User).filter(User.username == email).first(); assert u
            tj = Job(
                status='completed',
                input_hash='x',
                job_flow='tailor',
                source_page='Resume Tailor',
                access_token='t',
                client_id=None,
                user_id=u.id,
                is_test=True,
            )
            s.add(tj); s.commit()
        # Start ranking with model-like keys that should be hidden
        resp = await ac.post('/benchmark/rank', json={
            'base_resume': 'Base','jd_text': 'JD',
            'candidates': {'openai:gpt-4o':'r1','anthropic:claude-opus':'r2'},
            'judge_provider': 'openai','judge_model_id': 'GPT-5'
        }, headers=headers)
        assert resp.status_code == 200, resp.text
        job_id = resp.json()['job_id']
        # Verify alias_map and bench_cands_json outputs exist and contain aliased keys
        from restailor.db import get_pii_key
        key = get_pii_key()
        with SessionLocal() as s:
            # alias_map
            alias_map_row = s.execute(sa.text("SELECT pgp_sym_decrypt(content_enc, CAST(:k AS TEXT)) FROM job_outputs WHERE job_id = :jid AND type='alias_map' ORDER BY created_at DESC LIMIT 1").bindparams(k=key, jid=job_id)).scalar()
            assert alias_map_row, 'alias_map missing'
            amap = json.loads(alias_map_row)
            assert set(amap.values()) == {'openai:gpt-4o','anthropic:claude-opus'}
            # bench_cands_json
            cand_json = s.execute(sa.text("SELECT pgp_sym_decrypt(content_enc, CAST(:k AS TEXT)) FROM job_outputs WHERE job_id = :jid AND type='bench_cands_json' ORDER BY created_at DESC LIMIT 1").bindparams(k=key, jid=job_id)).scalar()
            assert cand_json, 'bench_cands_json missing'
            cands = json.loads(cand_json)
            assert all(re.fullmatch(r'R[0-9A-F]{6,}', k) for k in cands.keys())
            # Ensure no original keys leaked
            assert not any(k in cands for k in ['openai:gpt-4o','anthropic:claude-opus'])
