"""Simple end-to-end test using the HTTP API.

Creates a job via POST /jobs, then polls GET /jobs/{id}/status until completed
or timeout. Uses only the Python standard library (no extra deps).

Usage:
  poetry run python scripts/enqueue_test.py

Optional env:
    API_BASE_URL (default: http://127.0.0.1:8000)
"""
from __future__ import annotations

import json
import os
import time
from urllib.parse import urljoin

import requests


def _post_json(url: str, payload: dict, timeout: float = 5.0) -> dict:
    resp = requests.post(url, json=payload, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def _get_json(url: str, timeout: float = 5.0, headers: dict | None = None) -> dict:
    resp = requests.get(url, headers=headers or {}, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def main() -> int:
    base = os.getenv("API_BASE_URL", os.getenv("BACKEND_BASE_URL", "http://127.0.0.1:8000"))
    try:
        created = _post_json(
            f"{base}/jobs",
            {"resume_text": "my resume text", "jd_text": "my jd text"},
        )
    except requests.RequestException as e:
        print("ERROR: cannot reach API:", e)
        return 2

    job_id = created.get("job_id")
    token = created.get("access_token")
    if not job_id:
        print("ERROR: API did not return job_id:", created)
        return 2

    print("Enqueued job:", job_id)

    # Poll up to ~60s (override with ENQUEUE_MAX_POLLS and ENQUEUE_POLL_SLEEP_S)
    try:
        max_polls = int(os.getenv("ENQUEUE_MAX_POLLS") or 60)
    except Exception:
        max_polls = 60
    try:
        sleep_s = float(os.getenv("ENQUEUE_POLL_SLEEP_S") or 1.0)
    except Exception:
        sleep_s = 1.0
    for i in range(max_polls):
        try:
            hdrs = {"X-Job-Token": token} if token else {}
            status = _get_json(f"{base}/jobs/{job_id}/status", headers=hdrs)
        except requests.RequestException as e:
            print("WARN: status poll error:", e)
            time.sleep(sleep_s)
            continue

        print(time.strftime("%H:%M:%S"), "=>", status.get("status"))
        if status.get("status") == "completed":
            print("RESULT:", status.get("result"))
            return 0
        if status.get("status") == "failed":
            print("ERROR: job failed")
            return 1
    time.sleep(sleep_s)

    print("TIMEOUT waiting for completion")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
