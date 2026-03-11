"""
Ephemeral run registry utilities.

- Tracks a run_id -> set[job_id] mapping with TTL.
- Supports marking a run as canceled and checking cancel state.
- Uses Redis when available via app.state.redis.pool, else in-memory fallback.

Safe to use in tests or without Redis.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Iterable, List, Any

# In-memory fallback store
_MEM: dict[str, dict] = {}
_LOCK = asyncio.Lock()


def _now() -> float:
    return time.time()


async def _mem_cleanup() -> None:
    """Remove expired entries from the in-memory store."""
    now = _now()
    to_del = [k for k, v in _MEM.items() if float(v.get("expires", 0)) <= now]
    for k in to_del:
        _MEM.pop(k, None)


async def set_run_jobs(
    run_id: str,
    jobs: Iterable[str],
    ttl_sec: int = 86400,
    redis: Any | None = None,
) -> None:
    jobs_list = [str(j) for j in jobs]
    if redis is not None and getattr(redis, "pool", None) is not None:
        client: Any = getattr(redis, "pool")  # aioredis client
        key = f"rt:run:{run_id}"
        payload = json.dumps({"jobs": jobs_list, "canceled": False})
        # EX sets TTL in seconds
        await client.set(key, payload, ex=max(60, int(ttl_sec)))
        return
    async with _LOCK:
        await _mem_cleanup()
        _MEM[run_id] = {
            "jobs": set(jobs_list),
            "canceled": False,
            "expires": _now() + max(60, int(ttl_sec)),
        }


async def add_job_to_run(
    run_id: str,
    job_id: str,
    ttl_sec: int = 86400,
    redis: Any | None = None,
) -> None:
    if not run_id or not job_id:
        return
    if redis is not None and getattr(redis, "pool", None) is not None:
        client: Any = getattr(redis, "pool")  # aioredis client
        key = f"rt:run:{run_id}"
        raw = await client.get(key)
        try:
            obj = json.loads(raw) if raw else {"jobs": [], "canceled": False}
        except Exception:
            obj = {"jobs": [], "canceled": False}
        jobs: list[str] = [str(j) for j in (obj.get("jobs") or [])]
        if str(job_id) not in jobs:
            jobs.append(str(job_id))
        obj["jobs"] = jobs
        await client.set(key, json.dumps(obj), ex=max(60, int(ttl_sec)))
        return
    async with _LOCK:
        await _mem_cleanup()
        entry = _MEM.get(run_id) or {"jobs": set(), "canceled": False, "expires": _now() + max(60, int(ttl_sec))}
        entry["jobs"].add(str(job_id))
        entry["expires"] = _now() + max(60, int(ttl_sec))
        _MEM[run_id] = entry


async def get_run_jobs(run_id: str, redis: Any | None = None) -> List[str]:
    if not run_id:
        return []
    if redis is not None and getattr(redis, "pool", None) is not None:
        client: Any = getattr(redis, "pool")
        key = f"rt:run:{run_id}"
        raw = await client.get(key)
        if not raw:
            return []
        try:
            obj = json.loads(raw)
            return [str(j) for j in (obj.get("jobs") or [])]
        except Exception:
            return []
    async with _LOCK:
        await _mem_cleanup()
        entry = _MEM.get(run_id)
        if not entry:
            return []
        return [str(j) for j in sorted(entry.get("jobs", set()))]


async def mark_run_canceled(run_id: str, redis: Any | None = None, ttl_sec: int = 86400) -> None:
    if not run_id:
        return
    if redis is not None and getattr(redis, "pool", None) is not None:
        client: Any = getattr(redis, "pool")
        key = f"rt:run:{run_id}"
        raw = await client.get(key)
        try:
            obj = json.loads(raw) if raw else {"jobs": [], "canceled": True}
        except Exception:
            obj = {"jobs": [], "canceled": True}
        obj["canceled"] = True
        await client.set(key, json.dumps(obj), ex=max(60, int(ttl_sec)))
        return
    async with _LOCK:
        await _mem_cleanup()
        entry = _MEM.get(run_id) or {"jobs": set(), "canceled": False, "expires": _now() + max(60, int(ttl_sec))}
        entry["canceled"] = True
        entry["expires"] = _now() + max(60, int(ttl_sec))
        _MEM[run_id] = entry


async def is_run_canceled(run_id: str, redis: Any | None = None) -> bool:
    if not run_id:
        return False
    if redis is not None and getattr(redis, "pool", None) is not None:
        client: Any = getattr(redis, "pool")
        key = f"rt:run:{run_id}"
        raw = await client.get(key)
        if not raw:
            return False
        try:
            obj = json.loads(raw)
            return bool(obj.get("canceled") or False)
        except Exception:
            return False
    async with _LOCK:
        await _mem_cleanup()
        entry = _MEM.get(run_id)
        return bool(entry.get("canceled") if entry else False)
