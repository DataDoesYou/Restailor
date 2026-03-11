from __future__ import annotations

# PERF: Minimal, zero-behavior-change observability helpers (request timing, SQL timing, outbound timers).

import asyncio
import hashlib
import logging
import re
import time
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Callable, Optional, Awaitable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

try:
    from sqlalchemy import event  # type: ignore
except Exception:  # pragma: no cover
    event = None  # type: ignore

logger = logging.getLogger("perf")


# PERF: FastAPI middleware to time total request duration
class RequestTimingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]):  # type: ignore[override]
        start = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            try:
                status = int(getattr(response, "status_code", 500))
            except Exception:
                status = 500
            return response
        finally:
            dur_ms = (time.perf_counter() - start) * 1000.0
            path = request.url.path
            method = request.method
            
            # Best-effort client ip (may be None)
            client_ip: Optional[str] = None
            try:
                client_ip = getattr(getattr(request, "client", None), "host", None)
            except Exception:
                client_ip = None
            
            # Skip logging automated health checks & polling (except failures)
            # Distinguish automated requests from user requests by checking for authentication
            has_auth = bool(request.headers.get("authorization") or request.headers.get("cookie"))
            
            # Only skip if: no auth + noisy endpoint + success status (= automated infrastructure check)
            skip_if_automated_success = {"/health", "/healthz", "/users/me/balance", "/billing/summary", "/pricing/averages", "/pricing/estimate"}
            should_log = not (
                not has_auth and  # No authentication = automated/infrastructure
                path in skip_if_automated_success and 
                status < 400
            ) and method != "OPTIONS"  # Never log CORS preflight
            
            if should_log:
                payload = {
                    "evt": "http_request",
                    "method": method,
                    "path": path,
                    "status": status,
                    "dur_ms": round(dur_ms, 2),
                    "client": client_ip,
                }
                try:
                    logger.info(payload)
                except Exception as ex:  # pragma: no cover
                    logger.debug("request timing log failed: %r", ex)


# PERF: SQLAlchemy slow query logging (queries > threshold_ms)
def install_sqlalchemy_timing(engine: Any, *, threshold_ms: float = 50.0) -> None:
    if event is None or engine is None:
        return

    @event.listens_for(engine, "before_cursor_execute")
    def _before_cursor_execute(conn, cursor, statement, parameters, context, executemany):  # type: ignore
        try:
            context._query_start_time = time.perf_counter()  # type: ignore[attr-defined]
        except Exception as ex:
            logger.debug("sql timing before_cursor_execute failed to set start time: %r", ex)

    @event.listens_for(engine, "after_cursor_execute")
    def _after_cursor_execute(conn, cursor, statement, parameters, context, executemany):  # type: ignore
        try:
            start = getattr(context, "_query_start_time", None)
            if start is None:
                return
            dur_ms = (time.perf_counter() - float(start)) * 1000.0
            if dur_ms < float(threshold_ms):
                return
            # Hash parameters to avoid leaking secrets/PII. Include counts only.
            try:
                param_repr = repr(parameters)
            except Exception:
                param_repr = "<unrepr>"
            phash = hashlib.sha256(param_repr.encode("utf-8", errors="ignore")).hexdigest()[:16]
            pcount = 0
            try:
                if isinstance(parameters, (list, tuple)):
                    pcount = len(parameters)
                elif isinstance(parameters, dict):
                    pcount = len(parameters.keys())
                else:
                    pcount = 1 if parameters else 0
            except Exception:
                pcount = 0
            stmt = (statement or "").strip().replace("\n", " ")
            if len(stmt) > 300:
                stmt = stmt[:300] + "…"
            payload = {
                "evt": "sql_slow",
                "dur_ms": round(dur_ms, 2),
                "rows": getattr(cursor, "rowcount", None),
                "params": {"count": pcount, "hash": phash},
                "stmt": stmt,
            }
            logger.warning(payload)
        except Exception as ex:  # pragma: no cover
            logger.debug("sql timing hook failed: %r", ex)


# PERF: Generic async outbound timer (HTTP/SMTP/SDK calls)
@asynccontextmanager
async def outbound_timed(kind: str, target: str, **fields: Any):
    start = time.perf_counter()
    ok = True
    err: Optional[str] = None
    try:
        yield
    except Exception as ex:
        ok = False
        try:
            err = type(ex).__name__
        except Exception:
            err = "Error"
        raise
    finally:
        dur_ms = (time.perf_counter() - start) * 1000.0
        payload = {"evt": "outbound", "kind": kind, "target": target, "dur_ms": round(dur_ms, 2), "ok": ok}
        if fields:
            payload.update({k: v for k, v in fields.items() if k not in payload})
        if err:
            payload["err"] = err
        try:
            logger.info(payload)
        except Exception as ex:  # pragma: no cover
            logger.debug("outbound timing log failed: %r", ex)


# PERF: Optional shared httpx client factories
_shared_client: Any | None = None  # Async
_shared_client_lock = asyncio.Lock()
_shared_sync_client: Any | None = None  # Sync
try:
    import threading as _thr
    _shared_sync_lock = _thr.Lock()
except Exception:  # pragma: no cover
    _shared_sync_lock = None  # type: ignore


async def get_shared_async_client() -> Any:
    """Return a process-wide httpx.AsyncClient with sane limits and no behavior changes for callers.

    Only created on first use. Callers remain responsible for closing if they explicitly create their own clients.
    """
    global _shared_client
    try:
        import httpx  # type: ignore
    except Exception:  # pragma: no cover
        return None
    if _shared_client is not None:
        return _shared_client
    async with _shared_client_lock:
        if _shared_client is None:
            # Keep defaults close to library defaults; allow tuning via CONFIG.perf
            try:
                from restailor.app_config import CONFIG as _CFG  # lazy import to avoid circulars
            except Exception:
                _CFG = {}
            perf = (_CFG.get("perf", {}) or {}) if isinstance(_CFG, dict) else {}
            try:
                _max_conn = int(perf.get("httpx_max_connections", 100))
            except Exception:
                _max_conn = 100
            try:
                _max_keep = int(perf.get("httpx_max_keepalive", 20))
            except Exception:
                _max_keep = 20
            try:
                _to_s = float(perf.get("httpx_timeout_ms", 10000.0)) / 1000.0
            except Exception:
                _to_s = 10.0
            try:
                _cto_s = float(perf.get("httpx_connect_timeout_ms", 5000.0)) / 1000.0
            except Exception:
                _cto_s = 5.0
            limits = httpx.Limits(max_connections=_max_conn, max_keepalive_connections=_max_keep)
            timeout = httpx.Timeout(_to_s, connect=_cto_s)
            _shared_client = httpx.AsyncClient(limits=limits, timeout=timeout)
        return _shared_client


def get_shared_client() -> Any:
    """Return a process-wide httpx.Client with sane limits/timeouts.

    Safe to call multiple times; constructed on first use. If httpx is unavailable, returns None.
    """
    global _shared_sync_client
    try:
        import httpx  # type: ignore
    except Exception:  # pragma: no cover
        return None
    if _shared_sync_client is not None:
        return _shared_sync_client
    lock = _shared_sync_lock
    if lock is None:
        # Fallback without locking
        pass
    else:
        lock.acquire()
    try:
        if _shared_sync_client is None:
            try:
                from restailor.app_config import CONFIG as _CFG
            except Exception:
                _CFG = {}
            perf = (_CFG.get("perf", {}) or {}) if isinstance(_CFG, dict) else {}
            try:
                _max_conn = int(perf.get("httpx_max_connections", 100))
            except Exception:
                _max_conn = 100
            try:
                _max_keep = int(perf.get("httpx_max_keepalive", 20))
            except Exception:
                _max_keep = 20
            try:
                _to_s = float(perf.get("httpx_timeout_ms", 10000.0)) / 1000.0
            except Exception:
                _to_s = 10.0
            try:
                _cto_s = float(perf.get("httpx_connect_timeout_ms", 5000.0)) / 1000.0
            except Exception:
                _cto_s = 5.0
            limits = httpx.Limits(max_connections=_max_conn, max_keepalive_connections=_max_keep)
            timeout = httpx.Timeout(_to_s, connect=_cto_s)
            _shared_sync_client = httpx.Client(limits=limits, timeout=timeout)
        return _shared_sync_client
    finally:
        if lock is not None:
            try:
                lock.release()
            except Exception as ex:
                logger.debug("shared sync client lock.release failed: %r", ex)


__all__ = [
    "RequestTimingMiddleware",
    "install_sqlalchemy_timing",
    "outbound_timed",
    "get_shared_async_client",
    "get_shared_client",
]
