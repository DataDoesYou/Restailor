"""Quick abort sanity check.

Usage (from repo root, with Redis running and worker active):

  poetry run python scripts/abort_sanity.py

This enqueues `_abort_sanity_job` with a 10s sleep, waits ~1s, then calls abort().
Logs should show:
  - "abort_sanity: start"
  - "abort_sanity: cancelled"
"""
from __future__ import annotations

import asyncio
from arq import create_pool
from arq.jobs import Job
from arq.connections import RedisSettings
import os
from restailor.app_config import CONFIG


async def main():
  # Build Redis settings from config/env
  try:
    rconf = (CONFIG.get("redis", {}) or {})
  except Exception:
    rconf = {}
  host = str(os.getenv("REDIS_HOST") or rconf.get("host") or "127.0.0.1")
  try:
    port = int(os.getenv("REDIS_PORT") or rconf.get("port") or 6379)
  except Exception:
    port = 6379
  try:
    database = int(os.getenv("REDIS_DB") or rconf.get("database") or 0)
  except Exception:
    database = 0
  password = os.getenv("REDIS_PASSWORD") or rconf.get("password") or None
  r = await create_pool(RedisSettings(host=host, port=port, database=database, password=password))
  try:
    # Enqueue the synthetic job with configurable sleep seconds (default 10)
    try:
      _seconds = int(os.getenv("ABORT_SANITY_SECONDS") or 10)
    except Exception:
      _seconds = 10
    j: Job | None = await r.enqueue_job("_abort_sanity_job", seconds=_seconds)
    if j is None:
      print("Failed to enqueue job (got None)")
      return
    # Give worker a moment to start
    try:
      _delay = float(os.getenv("ABORT_SANITY_START_DELAY_S") or 1.0)
    except Exception:
      _delay = 1.0
    await asyncio.sleep(_delay)
    # Abort should cancel promptly (requires WorkerSettings.allow_abort_jobs = True)
    await j.abort()
    try:
      try:
        _result_timeout = float(os.getenv("ABORT_SANITY_RESULT_TIMEOUT_S") or 5.0)
      except Exception:
        _result_timeout = 5.0
      res = await j.result(timeout=_result_timeout)
      print("Job result:", res)
    except Exception as e:
      print("Job aborted (expected). Exception:", e)
  finally:
    await r.close()


if __name__ == "__main__":
    asyncio.run(main())
