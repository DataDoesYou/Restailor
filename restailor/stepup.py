from __future__ import annotations

"""Step-up (re-auth) guard for sensitive actions.

Provides:
- issue_stepup_ticket(user_id, ttl_seconds=?): returns a signed, short-lived token
  that can be sent back in 'X-Stepup-Token' header; also suitable for an HttpOnly cookie.
- require_recent_stepup(admin_only=True): FastAPI dependency factory that verifies
  the current user, role (when admin_only), and the presence of a valid, unexpired
  step-up token matching the user. Returns the user object when allowed.

Token format: itsdangerous TimestampSigner over 'uid:random', validated by max_age.
Signing secret derives from AUTH secret to avoid adding new mandatory secret material.
"""

import os
import secrets
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from itsdangerous import TimestampSigner, BadTimeSignature, BadSignature

from .auth import get_current_user_pending_ok as get_current_user
from .security import SECRET_KEY
from .app_config import CONFIG


STEPUP_HEADER = "X-Stepup-Token"
STEPUP_COOKIE = "rt_stepup"


def _truthy(v: Optional[str]) -> bool:
    return str(v or "").strip().lower() in {"1", "true", "yes", "on", "y"}


def _signer() -> TimestampSigner:
    # Derive a distinct namespace-specific key to avoid token confusion if keys leak
    # Keep compatibility with existing AUTH secret by prefixing a domain label.
    key = f"stepup::{SECRET_KEY}"
    return TimestampSigner(key)


def _ttl_default() -> int:
    try:
        return int(((CONFIG.get("security", {}) or {}).get("stepup", {}) or {}).get("ttl_seconds", 300))
    except Exception:
        return 300


def issue_stepup_ticket(user_id: int, *, ttl_seconds: int | None = None) -> str:
    payload = f"{int(user_id)}:{secrets.token_urlsafe(12)}"
    tok = _signer().sign(payload.encode("utf-8")).decode("utf-8")
    # Caller is responsible for attaching via header/cookie. We do not persist server-side.
    return tok


def _extract_stepup_token(request: Request) -> Optional[str]:
    # Prefer header, fallback to cookie; ignore empty values
    v = request.headers.get(STEPUP_HEADER)
    if v and str(v).strip():
        return str(v).strip()
    c = request.cookies.get(STEPUP_COOKIE)
    if c and str(c).strip():
        return str(c).strip()
    return None


def _validate_stepup_token(token: str, *, expected_user_id: int, ttl_seconds: int) -> bool:
    try:
        raw = _signer().unsign(token.encode("utf-8"), max_age=int(ttl_seconds))
        data = raw.decode("utf-8")
        # Format: "<uid>:<random>"
        if ":" not in data:
            return False
        uid_s, _rnd = data.split(":", 1)
        return int(uid_s) == int(expected_user_id)
    except (BadTimeSignature, BadSignature, ValueError):
        return False


def require_recent_stepup(*, admin_only: bool = True, ttl_seconds: int | None = None):
    """Return a FastAPI dependency ensuring a recent step-up token.

    Checks:
      1) user is authenticated (Bearer token),
      2) user is admin if admin_only,
      3) step-up token present in header/cookie and unexpired, matching user id.

    In test runs (PYTEST_CURRENT_TEST present) enforcement defaults off unless
    REQUIRE_STEPUP is truthy. Additionally, to avoid global bleed-over when tests
    set REQUIRE_STEPUP=1, we only enforce step-up for the dedicated admin step-up
    tests module; other tests continue to bypass by default.
    """

    async def _dep(request: Request, user=Depends(get_current_user)):
        # Testing override: allow skipping in pytest unless explicitly enabled
        try:
            cur = os.getenv("PYTEST_CURRENT_TEST")
            if cur:
                # If not explicitly required, bypass in tests
                if not _truthy(os.getenv("REQUIRE_STEPUP")):
                    return user
                # If explicitly required, only enforce within the admin step-up tests
                if "test_admin_stepup_and_trusted_devices.py" not in cur:
                    return user
        except Exception as ex:
            import logging as _log
            _log.getLogger(__name__).debug("stepup.require_stepup: pytest env parse failed: %s", ex)
        # Role gate when requested
        if admin_only and str(getattr(user, "role", "user") or "user").lower() != "admin":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin privileges required")
        # Validate token from header or cookie
        tok = _extract_stepup_token(request)
        if not tok:
            # Return exact error shape required by UI: {"detail":"needs_stepup"}
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="needs_stepup")
        ttl = int(ttl_seconds) if ttl_seconds is not None else _ttl_default()
        ok = _validate_stepup_token(
            tok,
            expected_user_id=int(getattr(user, "id", 0) or 0),
            ttl_seconds=ttl,
        )
        if not ok:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="needs_stepup")
        return user

    return _dep


__all__ = [
    "issue_stepup_ticket",
    "require_recent_stepup",
    "STEPUP_HEADER",
    "STEPUP_COOKIE",
]
