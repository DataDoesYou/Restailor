from __future__ import annotations

import time
from typing import Literal, Tuple, Dict, Any

from fastapi import Request

from restailor.app_config import CONFIG
import logging
logger = logging.getLogger(__name__)


def _now_ms() -> int:
    return int(time.time() * 1000)


def _fixed_window_key(prefix: str, key: str, window_s: int, now_ms: int) -> Tuple[str, int]:
    window_start = (now_ms // (window_s * 1000)) * (window_s * 1000)
    k = f"rate:{prefix}:{key}:{window_s}:{window_start}"
    reset_ms = window_start + window_s * 1000
    return k, reset_ms


async def _incr_window(redis, key: str, window_s: int) -> int:
    n = await redis.incr(key)
    # Ensure the key expires slightly after the window ends
    await redis.pexpire(key, int(window_s * 1000) + 2000)
    return int(n)


def client_id_from_request(request: Request) -> str:
    hdr = CONFIG.get("app", {}).get("client_id_header", "X-Client-Id")
    cid = request.headers.get(hdr) or (getattr(request.client, "host", "unknown") if request.client else "unknown")
    cid = cid.strip() if isinstance(cid, str) else "unknown"
    return cid[:64] or "unknown"


def ip_from_request(request: Request) -> str:
    trust_proxy = bool(CONFIG.get("app", {}).get("trust_proxy", False))
    if trust_proxy:
        xff = request.headers.get("X-Forwarded-For")
        if xff:
            # First IP in the list is the original client
            ip = xff.split(",")[0].strip()
            if ip:
                return ip
    return getattr(request.client, "host", "unknown") if request.client else "unknown"


async def check_rates(
    redis,
    *,
    kind: Literal["tailor", "fit", "judge"],
    client_id: str,
    ip: str,
) -> Tuple[bool, Dict[str, Any]]:
    """Check per-user and per-IP fixed-window rates.

    Returns (ok, detail). On not ok, detail contains:
      {error, code, limit, remaining, resetEpochMs, retryAfter}
    """
    now = _now_ms()
    # Limits from config with safe defaults
    rate = (CONFIG.get("limits", {}).get("rate", {}) if isinstance(CONFIG.get("limits", {}), dict) else {})
    # judge follows fit if not specified
    use_kind = kind if kind in ("tailor", "fit") else "fit"
    # Defaults aligned with restailor.app_config
    user_minute = int(rate.get(f"{use_kind}_minute", 30 if use_kind == "tailor" else 60) or (30 if use_kind == "tailor" else 60))
    user_hour = int(rate.get(f"{use_kind}_hour", 200 if use_kind == "tailor" else 400) or (200 if use_kind == "tailor" else 400))
    ip_minute = int(rate.get("ip_rate_minute", 60) or 60)
    ip_hour = int(rate.get("ip_rate_hour", 600) or 600)

    # Evaluate: user minute/hour, ip minute/hour
    # User minute
    k, reset = _fixed_window_key(f"user:{kind}:m", client_id, 60, now)
    c = await _incr_window(redis, k, 60)
    if c > user_minute:
        retry = max(1, (reset - now + 999) // 1000)
        return False, {"error": "rate_limited", "code": 429, "limit": f"{kind}_minute", "remaining": 0, "resetEpochMs": reset, "retryAfter": retry}
    # User hour
    k, reset = _fixed_window_key(f"user:{kind}:h", client_id, 3600, now)
    c = await _incr_window(redis, k, 3600)
    if c > user_hour:
        retry = max(1, (reset - now + 999) // 1000)
        return False, {"error": "rate_limited", "code": 429, "limit": f"{kind}_hour", "remaining": 0, "resetEpochMs": reset, "retryAfter": retry}
    # IP minute
    k, reset = _fixed_window_key("ip:m", ip, 60, now)
    c = await _incr_window(redis, k, 60)
    if c > ip_minute:
        retry = max(1, (reset - now + 999) // 1000)
        return False, {"error": "rate_limited", "code": 429, "limit": "ip_minute", "remaining": 0, "resetEpochMs": reset, "retryAfter": retry}
    # IP hour
    k, reset = _fixed_window_key("ip:h", ip, 3600, now)
    c = await _incr_window(redis, k, 3600)
    if c > ip_hour:
        retry = max(1, (reset - now + 999) // 1000)
        return False, {"error": "rate_limited", "code": 429, "limit": "ip_hour", "remaining": 0, "resetEpochMs": reset, "retryAfter": retry}
    # OK
    return True, {"remaining": 1}


async def try_acquire_stream(redis, client_id: str) -> Tuple[bool, int]:
    """Acquire per-user and global concurrency slots.

    Returns (ok, retry_after_seconds_if_denied).
    Caps: user<=3, global<=100. Keys auto-expire to recover on crashes.
    """
    user_key = f"conc:user:{client_id}"
    glob_key = "conc:global"
    conc = (CONFIG.get("limits", {}).get("concurrency", {}) if isinstance(CONFIG.get("limits", {}), dict) else {})
    # Default per_user cap aligned with app_config (2)
    per_user_cap = int(conc.get("per_user", 2) or 2)
    global_cap = int(conc.get("global", 100) or 100)
    user_n = await redis.incr(user_key)
    await redis.expire(user_key, 600)
    if int(user_n) > per_user_cap:
        # rollback
        await redis.decr(user_key)
        return False, 1
    glob_n = await redis.incr(glob_key)
    await redis.expire(glob_key, 600)
    if int(glob_n) > global_cap:
        # rollback
        await redis.decr(glob_key)
        await redis.decr(user_key)
        return False, 1
    return True, 0


async def release_stream(redis, client_id: str) -> None:
    user_key = f"conc:user:{client_id}"
    glob_key = "conc:global"
    try:
        await redis.decr(user_key)
        await redis.decr(glob_key)
    except Exception as ex:
        logger.debug("limits.release_stream cleanup failed: %s", ex)


async def incr_daily_tokens(redis, client_id: str, amount: int) -> None:
    """Charge tokens to a per-user, per-day counter (UTC)."""
    if amount <= 0:
        return
    import datetime as _dt
    try:
        day = _dt.datetime.now(_dt.UTC).strftime("%Y%m%d")
    except AttributeError:
        # Py<3.11 fallback: use timezone-aware UTC via tzinfo
        day = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%d")
    k = f"tokens:{client_id}:{day}"
    await redis.incrby(k, int(amount))
    # Expire in 3 days to allow late reads
    await redis.expire(k, 3 * 86400)
