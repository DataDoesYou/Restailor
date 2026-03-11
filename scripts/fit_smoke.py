#!/usr/bin/env python3
"""One-shot /fit smoke test.

Runs: signup (ignore already-exists), login, call /fit, print status + JSON.
Use when you just want to see what /fit returns (e.g. 400/402/200) fast.

Requirements:
  - API running at http://localhost:8000 (override with --base)
  - PII_ENCRYPTION_KEY set (backend requirement) or keyring populated

Example:
  poetry run python scripts/fit_smoke.py --email test1@example.com --password Str0ngPass!123
"""
from __future__ import annotations
import argparse, json, sys, uuid
import requests

DEF_RESUME = "Quick resume sample."
DEF_JD = "Quick JD sample."

def _post(base: str, path: str, **kw):
    url = base.rstrip('/') + path
    try:
        r = requests.post(url, timeout=30, **kw)
    except Exception as ex:
        return None, f"REQUEST_ERROR: {ex}"
    try:
        data = r.json()
    except Exception:
        data = r.text
    return r, data

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', default='http://localhost:8000')
    ap.add_argument('--email', required=True)
    ap.add_argument('--password', required=True)
    ap.add_argument('--resume', default=DEF_RESUME)
    ap.add_argument('--jd', default=DEF_JD)
    ap.add_argument('--provider', default='openai')
    ap.add_argument('--model', default='gpt-4')
    ap.add_argument('--client-id', default='smoke-fit')
    args = ap.parse_args()

    base = args.base
    email = args.email
    pw = args.password

    # 1. Signup
    print('[signup]')
    r, data = _post(base, '/signup', json={'username': email, 'password': pw})
    if r is None:
        print(data); return 1
    print(f"status={r.status_code}")
    if r.status_code not in (200, 400):
        print(data); return 1
    # 2. Login
    print('\n[login]')
    form = {'username': email, 'password': pw}
    r, data = _post(base, '/token', data=form)
    if r is None:
        print(data); return 1
    print(f"status={r.status_code}")
    if r.status_code != 200:
        print(data); return 1
    if not isinstance(data, dict) or 'access_token' not in data:
        print('Unexpected login response:', data); return 1
    tok = data['access_token']
    # 3. /fit
    print('\n[fit]')
    body = {
        'resume_text': args.resume,
        'jd_text': args.jd,
        'provider': args.provider,
        'model_id': args.model,
        'source_page': 'Smoke'
    }
    headers = {
        'Authorization': f'Bearer {tok}',
        'X-Client-Id': args.client_id,
        'Idempotency-Key': str(uuid.uuid4()),
        'Content-Type': 'application/json'
    }
    r, data = _post(base, '/fit', json=body, headers=headers)
    if r is None:
        print(data); return 1
    print(f"status={r.status_code}")
    try:
        print(json.dumps(data, indent=2, ensure_ascii=False))
    except Exception:
        print(data)
    # Exit code 0 even for 400/402 so caller just sees output
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
