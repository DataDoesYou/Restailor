import httpx
import sys
import os

base = os.getenv('BASE_URL', os.getenv('BACKEND_BASE_URL', 'http://127.0.0.1:8000'))

def main():
    # Create a benchmark container job (no Redis needed)
    r = httpx.post(f'{base}/benchmark/start', json={'source_page': 'Token Test'}, timeout=30)
    print('START', r.status_code, r.text)
    r.raise_for_status()
    data = r.json()
    jid = data['job_id']
    tok = data['access_token']

    # Status without token
    r = httpx.get(f'{base}/jobs/{jid}/status', timeout=30)
    print('STATUS no token', r.status_code, r.text)

    # Status wrong token
    r = httpx.get(f'{base}/jobs/{jid}/status', headers={'X-Job-Token': 'bad'}, timeout=30)
    print('STATUS wrong token', r.status_code, r.text)

    # Status correct token
    r = httpx.get(f'{base}/jobs/{jid}/status', headers={'X-Job-Token': tok}, timeout=30)
    print('STATUS ok', r.status_code, r.text)

    # Save benchmark text wrong token
    r = httpx.post(f'{base}/benchmark/save', json={'job_id': jid, 'bench_md': '# Hi'}, timeout=30)
    print('SAVE no token', r.status_code, r.text)
    r = httpx.post(f'{base}/benchmark/save', json={'job_id': jid, 'bench_md': '# Hi'}, headers={'X-Job-Token': 'bad'}, timeout=30)
    print('SAVE wrong token', r.status_code, r.text)

    # Save with correct token
    r = httpx.post(f'{base}/benchmark/save', json={'job_id': jid, 'bench_md': '# Hi', 'raw_md': '*raw*'}, headers={'X-Job-Token': tok}, timeout=30)
    print('SAVE ok', r.status_code, r.text)

if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print('ERROR', e)
        sys.exit(1)
