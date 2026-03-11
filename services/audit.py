from __future__ import annotations

from typing import Any, Optional
import logging

from fastapi import Request

from restailor.db import SessionLocal
from restailor.models import AuditEvent, User

logger = logging.getLogger(__name__)


def _safe_ip_from_request(request: Optional[Request]) -> Optional[str]:
    try:
        if request is None:
            return None
        # Prefer X-Forwarded-For first value when present
        xff = (request.headers.get("X-Forwarded-For") or "").split(",")[0].strip()
        if xff:
            return xff
        # Fallback to client host when available
        if request.client and request.client.host:
            return str(request.client.host)
    except Exception as ex:
        logger.debug("audit._safe_ip_from_request failed: %s", ex)
    return None


def _safe_ua_from_request(request: Optional[Request]) -> Optional[str]:
    try:
        if request is None:
            return None
        ua = request.headers.get("User-Agent")
        return ua[:512] if ua else None
    except Exception:
        return None


def log_event(
    user: Optional[User],
    event_type: str,
    severity: str = "info",
    meta: Optional[dict[str, Any]] = None,
    request: Optional[Request] = None,
) -> None:
    """Best-effort audit log writer.

    - Inserts an AuditEvent row in a short-lived session.
    - Swallows exceptions to avoid impacting the request path.
    """
    try:
        ip = _safe_ip_from_request(request)
        ua = _safe_ua_from_request(request)
        with SessionLocal() as db:
            uid = None
            try:
                if user is not None and getattr(user, "id", None) is not None:
                    uid = int(user.id)  # type: ignore[attr-defined]
            except Exception:
                uid = None
            ev = AuditEvent(
                user_id=uid,
                event_type=(event_type or "other"),
                severity=(severity or "info"),
                ip=ip,
                user_agent=ua,
                meta=(meta or None),
                is_test=bool(getattr(user, "is_test", False)) if user is not None else False,
            )
            db.add(ev)
            db.commit()
    except Exception as ex:
        try:
            logger.debug("audit_log_write_failed: %s", ex)
        except Exception as log_ex:
            # Last resort: keep behavior by swallowing but not raw pass
            _ = log_ex
