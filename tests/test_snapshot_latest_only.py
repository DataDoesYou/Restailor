import json, time
from fastapi.testclient import TestClient
from main import app
import pytest
pytestmark = pytest.mark.critical
from tests.utils import signup_and_mark_test, login

def _post_tailor(client, token, resume_text, jd_text, body):
    # Use current /jobs endpoint for tailoring-only by omitting do_judge or setting it False
    r = client.post('/jobs', json={
        'resume_text': resume_text,
        'jd_text': jd_text,
        'provider': body.get('tailor_provider') or body.get('provider') or 'openai',
        'model_id': body.get('tailor_model_id') or body.get('model_id') or 'gpt-4o-mini',
        'do_judge': False,
        'source_page': body.get('source_page') or 'TestSuite',
    }, headers={'Authorization': f'Bearer {token}', 'X-Client-Id': 'test-client'})
    assert r.status_code == 200, r.text
    return r.json()['job_id'], r.json()['access_token']

def _wait_stream_done(client: TestClient, job_id: str, access_token: str):
    # Poll the stream until terminal
    with client.stream('GET', f'/jobs/{job_id}/stream?access_token={access_token}') as s:
        full = ''
        for line in s.iter_lines():
            if not line:
                continue
            if line.startswith('data: '):
                payload = json.loads(line[6:])
                st = payload.get('status')
                if st in ('completed','failed','cancelled','canceled'):
                    return payload
    raise AssertionError('stream ended without terminal payload')

# NOTE: relies on existing single-snapshot semantics; we issue three tailor jobs sequentially simulating out-of-order completion by sleeping.
# Simplification: we just run sequentially and assume each overwrites; last (C) should persist.

def test_latest_snapshot_overwrites():
    client = TestClient(app)
    # Use a unique email per run to allow repeated executions without conflicts
    email = f"snaptest+{int(time.time()*1000)}@example.com"
    signup_and_mark_test(client, email)
    token = login(client, email)
    resume = 'Base Resume'
    jd = 'JD text'

    contents = {'A': 'Tailored A', 'B': 'Tailored B', 'C': 'Tailored C'}
    for key in ['A','B','C']:
        body = {
            'resume_text': resume,
            'jd_text': jd,
            'tailor_provider': 'openai',
            'tailor_model_id': 'gpt-4o-mini',
            'source_page': 'TestSuite'
        }
        job_id, access = _post_tailor(client, token, resume, jd, body)
        # Don't wait on SSE stream; persistence test does not require job completion
        # Simulate overwrite by directly posting snapshot save (mirrors frontend) with deterministic text
        snap = {
            'resumeInput': resume,
            'jdInput': jd,
            'fitOutput': None,
            'tailoredOutput': contents[key],
            'judgeOutput': None,
            'statsMd': None,
            'knobs': {},
            'modelInfo': {'provider': 'openai', 'model': 'gpt-4o-mini'}
        }
        # Persist snapshot for this JD on each iteration; latest should overwrite prior
        r_save = client.post(
            '/applications/jd/save',
            json={'jdText': jd, 'baseText': resume, 'snapshot': snap},
            headers={'Authorization': f'Bearer {token}'}
        )
        assert r_save.status_code == 200, r_save.text

    # Fetch applied snapshot and assert it equals C
    from hashlib import sha256
    jd_hash = sha256(jd.encode('utf-8')).hexdigest()
    # Lookup latest-applied snapshot for this JD
    r = client.get('/applications/jd/apply', params={'jdHash': jd_hash}, headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get('found') is True, f"not found: {data}"
    snap = (data.get('row') or {}).get('snapshot')
    assert isinstance(snap, dict) and 'tailoredOutput' in snap, f"invalid snapshot payload: {data}"
    assert snap['tailoredOutput'] == contents['C']
