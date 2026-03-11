from __future__ import annotations

from typing import Optional
import logging
from sqlalchemy.orm import Session
from restailor.db import SessionLocal
from restailor.models import EmailLog, User

logger = logging.getLogger(__name__)


def _get_user_id_safe(db: Session, email: Optional[str]) -> Optional[int]:
    if not email:
        return None
    try:
        e = (email or "").strip().lower()
        u = db.query(User).filter(User.username == e).one_or_none()
        return getattr(u, "id", None) if u else None
    except Exception:
        return None


def record_email_event(
    *,
    recipient: str,
    subject: Optional[str],
    kind: str,
    source: Optional[str],
    status: str,
    error: Optional[str] = None,
    client_id: Optional[str] = None,
    ip: Optional[str] = None,
) -> None:
    """Fire-and-forget style insert of an EmailLog row.

    - Opens a short-lived Session to avoid impacting request transaction scope.
    - Swallows exceptions to never block the request path.
    """
    try:
        with SessionLocal() as db:
            uid = _get_user_id_safe(db, recipient)
            from restailor.test_flags import is_automated_test_run as _is_auto
            row = EmailLog(
                user_id=uid,
                recipient=(recipient or "").strip().lower(),
                subject=subject,
                kind=(kind or "other")[:20],
                source=(source or None),
                status=(status or "sent")[:16],
                error=(error or None),
                client_id=(client_id or None),
                ip=(ip or None),
                is_test=(
                    _is_auto() or
                    ((recipient or "").lower().endswith("@example.com"))
                    or (str(client_id or "").lower().startswith("test"))
                    or (str(client_id or "").lower().startswith("e2e"))
                    or (str(client_id or "").lower().startswith("benchmark:"))
                    or (str(client_id or "").lower().startswith("admin-tests"))
                    or (str(client_id or "").lower().startswith("limits-"))
                ),
            )
            db.add(row)
            db.commit()
    except Exception as ex:
        try:
            logger.debug("email_log_insert_failed: %s", ex)
        except Exception as log_ex:
            # Last-resort: avoid silent pass but keep behavior unchanged
            # nosec B110: fallback logging failed; swallow to preserve request path
            _ = log_ex
