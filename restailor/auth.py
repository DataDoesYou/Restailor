from __future__ import annotations

from fastapi import Depends, HTTPException, status, Request, Header
from fastapi.security import OAuth2PasswordBearer
import jwt
from sqlalchemy.orm import Session

from .db import SessionLocal
from . import twofa_repo
from . import crud, schemas
import restailor.security as security  # use dynamic module to keep SECRET_KEY/ALGORITHM in sync


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")
# Optional bearer for endpoints that can work without auth
oauth2_scheme_optional = OAuth2PasswordBearer(tokenUrl="token", auto_error=False)


# Prefer Authorization header, else fall back to HttpOnly session cookie (rt_session)
async def bearer_or_cookie_token(
    request: Request,
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> str:
    if authorization:
        try:
            scheme, token = authorization.split(" ", 1)
            if scheme.lower() == "bearer" and token:
                return token.strip()
        except Exception:
            pass
    # Cookie fallback
    try:
        token = request.cookies.get("rt_session")
        if token:
            return token
    except Exception:
        pass
    # Let the normal 401 flow occur in callers
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not validate credentials", headers={"WWW-Authenticate": "Bearer"})


# Dependency: DB session per request (local to this module)
async def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


async def get_current_user(
    token: str = Depends(bearer_or_cookie_token),
    db: Session = Depends(get_db),
):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, security.SECRET_KEY, algorithms=[security.ALGORITHM])
        # Only allow bearer (normal) tokens here. Tokens with an explicit scope other than 'bearer'
        # (e.g., 'pending_2fa', 'reauth') must not grant access to standard endpoints.
        scope = payload.get("scope")
        if scope and str(scope).lower() != "bearer":
            raise credentials_exception
        username = payload.get("sub")  # type: ignore[assignment]
        if not username:
            raise credentials_exception
        token_data = schemas.TokenData(username=str(username).lower())
    except jwt.PyJWTError:
        raise credentials_exception

    user = crud.get_user_by_username(db, username=token_data.username) if token_data.username else None
    if user is None:
        raise credentials_exception
    # Enforce email verification before allowing full app usage
    if not getattr(user, "is_verified", False):
        raise HTTPException(status_code=403, detail="Please verify your email address before using the app.")
    return user


async def get_current_user_allow_unverified(
    token: str = Depends(bearer_or_cookie_token),
    db: Session = Depends(get_db),
):
    """Variant of get_current_user that authenticates but does NOT enforce is_verified.

    Use this for endpoints that help users complete verification (e.g., send token).
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, security.SECRET_KEY, algorithms=[security.ALGORITHM])
        scope = payload.get("scope")
        if scope and str(scope).lower() != "bearer":
            raise credentials_exception
        username = payload.get("sub")  # type: ignore[assignment]
        if not username:
            raise credentials_exception
        token_data = schemas.TokenData(username=str(username).lower())
    except jwt.PyJWTError:
        raise credentials_exception

    user = crud.get_user_by_username(db, username=token_data.username) if token_data.username else None
    if user is None:
        raise credentials_exception
    return user


async def try_get_current_user_allow_unverified(
    token: str | None = Depends(oauth2_scheme_optional),
    db: Session = Depends(get_db),
):
    """Optional variant: returns a user if a valid token is provided; otherwise None.

    Does not enforce email verification to keep behavior consistent with
    get_current_user_allow_unverified.
    """
    if not token:
        return None
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, security.SECRET_KEY, algorithms=[security.ALGORITHM])
        scope = payload.get("scope")
        if scope and str(scope).lower() != "bearer":
            raise credentials_exception
        username = payload.get("sub")  # type: ignore[assignment]
        if not username:
            raise credentials_exception
        token_data = schemas.TokenData(username=str(username).lower())
    except jwt.PyJWTError:
        raise credentials_exception

    user = crud.get_user_by_username(db, username=token_data.username) if token_data.username else None
    if user is None:
        raise credentials_exception
    return user


async def try_get_current_user_allow_unverified_cookie_ok(
    request: Request,
    authorization: str | None = Header(default=None, alias="Authorization"),
    db: Session = Depends(get_db),
):
    """Optional auth that accepts Bearer header OR rt_session cookie and does NOT enforce email verification.

    - If no token is present, returns None.
    - If a token is present but invalid, raises 401.
    - If valid, returns the user without checking is_verified.
    """
    token: str | None = None
    # Try Authorization: Bearer first
    if authorization:
        try:
            scheme, value = authorization.split(" ", 1)
            if scheme.lower() == "bearer" and value:
                token = value.strip()
        except Exception:
            token = None
    # Fall back to HttpOnly session cookie
    if not token:
        try:
            token = request.cookies.get("rt_session")
        except Exception:
            token = None
    # Optional behavior: if still no token, return None
    if not token:
        return None

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, security.SECRET_KEY, algorithms=[security.ALGORITHM])
        scope = payload.get("scope")
        if scope and str(scope).lower() != "bearer":
            raise credentials_exception
        username = payload.get("sub")  # type: ignore[assignment]
        if not username:
            raise credentials_exception
        token_data = schemas.TokenData(username=str(username).lower())
    except jwt.PyJWTError:
        raise credentials_exception

    user = crud.get_user_by_username(db, username=token_data.username) if token_data.username else None
    if user is None:
        raise credentials_exception
    return user


async def get_current_user_pending_ok(
    token: str = Depends(bearer_or_cookie_token),
    db: Session = Depends(get_db),
):
    """Authenticate a user allowing either a normal bearer token or a pending_2fa token.

    Use this for 2FA enrollment/confirmation endpoints so an admin who receives a
    pending_2fa token at login can complete setup. Does NOT allow 'reauth' tokens.
    Also enforces email verification status before returning the user.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, security.SECRET_KEY, algorithms=[security.ALGORITHM])
        scope = str(payload.get("scope") or "").lower()
        if scope and scope not in ("bearer", "pending_2fa"):
            raise credentials_exception
        username = payload.get("sub")  # type: ignore[assignment]
        if not username:
            raise credentials_exception
        token_data = schemas.TokenData(username=str(username).lower())
    except jwt.PyJWTError:
        raise credentials_exception

    user = crud.get_user_by_username(db, username=token_data.username) if token_data.username else None
    if user is None:
        raise credentials_exception
    # Enforce email verification before allowing enrollment
    if not getattr(user, "is_verified", False):
        raise HTTPException(status_code=403, detail="Please verify your email address before using the app.")
    return user


async def require_admin(
    user=Depends(get_current_user_pending_ok),
    db: Session = Depends(get_db),
):
    if getattr(user, "role", "user") != "admin":
        raise HTTPException(status_code=403, detail="Admin privileges required")
    # Enforce policy: admins must have 2FA confirmed unless explicitly disabled via config/env (primarily for tests)
    import os as _os
    try:
        from restailor.app_config import CONFIG as _CFG  # local import to avoid cycles
        enforce = bool((_CFG.get("security", {}) or {}).get("require_admin_2fa", True))
    except Exception:
        enforce = True
    # During pytest runs, default to NOT enforcing 2FA unless explicitly enabled via env.
    try:
        if "PYTEST_CURRENT_TEST" in _os.environ:
            # Explicit opt-in for tests
            enforce = _os.getenv("REQUIRE_ADMIN_2FA", "0").strip().lower() in {"1","true","yes","on"}
        else:
            # In non-test environments, allow env to override config
            if _os.getenv("REQUIRE_ADMIN_2FA", "").strip():
                enforce = _os.getenv("REQUIRE_ADMIN_2FA", "1").strip().lower() in {"1","true","yes","on"}
    except Exception as ex:
        import logging as _log
        _log.getLogger(__name__).debug("auth.require_admin: env override parse failed: %s", ex)
    if not enforce:
        return user
    # Enforce 2FA when enabled
    try:
        state = twofa_repo.get_user_2fa_state(db, int(getattr(user, "id", 0) or 0))
    except Exception:
        state = None
    
    # Admin must have 2FA enabled with either TOTP secret or WebAuthn credentials
    if not (state and state.get("two_factor_enabled")):
        raise HTTPException(status_code=403, detail="admin_requires_2fa")
    
    # Check for either TOTP or WebAuthn credentials
    has_totp = bool(state.get("totp_secret"))
    has_webauthn = False
    if not has_totp:
        try:
            from restailor import webauthn_repo
            has_webauthn = webauthn_repo.has_credentials(db, int(getattr(user, "id", 0) or 0))
        except Exception:
            pass
    
    if not (has_totp or has_webauthn):
        raise HTTPException(status_code=403, detail="admin_requires_2fa")
    
    return user
