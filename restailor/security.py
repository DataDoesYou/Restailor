from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import jwt
from passlib.context import CryptContext
import re
import hmac

# Load auth signing secret with keyring-first, then env; no dev fallback
def _load_auth_secret() -> str:
    # Try OS keyring first (Windows Credential Manager/macOS Keychain/Secret Service)
    try:
        import keyring  # type: ignore
        v = keyring.get_password("restailor", "AUTH_SECRET_KEY")  # type: ignore[attr-defined]
        if v and v.strip():
            return v
    except Exception as ex:
        import logging as _log
        _log.getLogger(__name__).debug("security._load_auth_secret: keyring read failed: %s", ex)
    # Fallback to environment variable
    v = os.getenv("AUTH_SECRET_KEY")
    if v and v.strip():
        return v
    # Dev/test fallback: allow a weak default ONLY if explicitly in dev/test environment
    # We require strict handling by default. Fallback is only permitted if:
    # 1. STRICT_SECRETS is explicitly false
    # 2. AND APP_ENV indicate development/testing

    try:
        strict_env = os.getenv("STRICT_SECRETS", "1")
        strict = str(strict_env).strip().lower() not in {"0", "false", "no", "off"}
    except Exception as ex:
        import logging as _log
        _log.getLogger(__name__).debug("security._load_auth_secret: STRICT_SECRETS parse failed: %s", ex)
        strict = True

    app_env = str(os.getenv("APP_ENV", "")).lower().strip()
    is_dev_env = app_env in {"development", "dev", "local", "test", "testing"}

    if not strict and is_dev_env:
        return "dev-insecure-secret-change-me"

    # Otherwise, fail fast to avoid insecure defaults in prod
    raise RuntimeError(
        "AUTH_SECRET_KEY is not set. "
        "For production, store it in OS keyring (service='restailor', username='AUTH_SECRET_KEY') or set the environment variable. "
        "For local dev, set APP_ENV=development and STRICT_SECRETS=0."
    )

from .app_config import CONFIG

SECRET_KEY = _load_auth_secret()
ALGORITHM = "HS256"

def _int_env_or_cfg(env: str, cfg_path: list[str], default: int) -> int:
    v = os.getenv(env)
    if v is not None:
        try:
            return int(v)
        except Exception:
            return default
    try:
        cur: Any = CONFIG
        for k in cfg_path:
            if not isinstance(cur, dict):
                return default
            cur = cur.get(k)
        return int(cur) if cur is not None else default
    except Exception:
        return default

ACCESS_TOKEN_EXPIRE_MINUTES = _int_env_or_cfg("ACCESS_TOKEN_EXPIRE_MINUTES", ["auth", "tokens", "access_token_expire_minutes"], 60)
REAUTH_TOKEN_EXPIRE_MINUTES = _int_env_or_cfg("REAUTH_TOKEN_EXPIRE_MINUTES", ["auth", "tokens", "reauth_token_expire_minutes"], 5)
PENDING2_TOKEN_EXPIRE_MINUTES = _int_env_or_cfg("PENDING2_TOKEN_EXPIRE_MINUTES", ["auth", "tokens", "pending2_token_expire_minutes"], 15)
REFRESH_TOKEN_EXPIRE_DAYS = _int_env_or_cfg("REFRESH_TOKEN_EXPIRE_DAYS", ["auth", "tokens", "refresh_token_expire_days"], 30)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def create_access_token(data: dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def create_reauth_token(sub: str, minutes: int | None = None, scope: str = "reauth") -> str:
    exp_m = int(minutes) if minutes is not None else REAUTH_TOKEN_EXPIRE_MINUTES
    payload = {"sub": sub, "scope": scope, "exp": datetime.now(timezone.utc) + timedelta(minutes=exp_m)}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(sub: str, days: int | None = None) -> str:
    """Create a long-lived refresh token for renewing access tokens without re-authentication.
    
    Args:
        sub: Username/subject for the token
        days: Optional override for expiration (defaults to REFRESH_TOKEN_EXPIRE_DAYS)
    
    Returns:
        JWT refresh token string with scope='refresh'
    """
    exp_days = int(days) if days is not None else REFRESH_TOKEN_EXPIRE_DAYS
    payload = {
        "sub": sub,
        "scope": "refresh",
        "exp": datetime.now(timezone.utc) + timedelta(days=exp_days)
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def create_pending2_token(sub: str, minutes: int | None = None) -> str:
    """Short-lived token to mark a successful password stage pending 2FA."""
    exp_m = int(minutes) if minutes is not None else PENDING2_TOKEN_EXPIRE_MINUTES
    payload = {"sub": sub, "scope": "pending_2fa", "exp": datetime.now(timezone.utc) + timedelta(minutes=exp_m)}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def verify_token_scope(token: str, scope: str) -> dict[str, Any]:
    """Decode token and ensure scope matches; returns payload or raises."""
    data = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    if data.get("scope") != scope:
        raise jwt.PyJWTError("invalid scope")
    return data


# ---- Helpers for API hardening ----
def constant_time_equals(a: str, b: str) -> bool:
    """Constant-time string comparison to avoid timing side channels."""
    try:
        return hmac.compare_digest(str(a or ""), str(b or ""))
    except Exception:
        return False


def csrf_protection_protected() -> None:
    """Note: CSRF protection is enforced by CsrfProtectMiddleware in main.py.
    
    The middleware checks Origin/Referer or custom headers for state-changing requests
    when cookie authentication is present.
    """
    return None


# ---- Password strength policy ----
def _truthy(v: str | None) -> bool:
    return str(v or "").strip().lower() in {"1","true","yes","on","y"}

def _cfg_password(key: str, default: int | bool) -> int | bool:
    try:
        sec = (CONFIG.get("security", {}) or {})
        pwd = (sec.get("password", {}) or {})
        val = pwd.get(key)
        if isinstance(default, bool):
            if val is None:
                env = os.getenv("PASSWORD_" + key.upper())
                return _truthy(env) if env is not None else bool(default)
            return bool(val)
        else:
            if val is None:
                env = os.getenv("PASSWORD_" + key.upper())
                try:
                    return int(env) if env is not None else int(default)
                except Exception:
                    return int(default)
            return int(val)
    except Exception:
        return default

_DEFAULT_MIN_LEN = int(_cfg_password("min_length", 8))
_REQUIRE_SYMBOLS = bool(_cfg_password("require_symbols", False))
_COMMON_WEAK = {
    "password","123456","12345678","123456789","1234567890","qwerty","qwertyuiop","letmein","welcome",
    "admin","iloveyou","monkey","dragon","football","baseball","abc123","111111","123123","sunshine",
    "princess","login","freedom","passw0rd","password1","zaq12wsx","1qaz2wsx","qazwsx","trustno1",
}


def check_password_strength(password: str, username: str | None = None) -> tuple[bool, str]:
    """Return (ok, reason) for a reasonable password policy.

    Policy (standard strength, light):
    - Min length PASSWORD_MIN_LENGTH (default 8)
    - Contains at least one letter and at least one number (symbols optional)
    - Not a very common/obvious password
    - Must not include the email local part (before @) as a substring
    - No leading/trailing whitespace; internal spaces allowed
    """
    pw = password or ""
    if pw != pw.strip():
        return False, "Password must not start or end with whitespace."
    if len(pw) < _DEFAULT_MIN_LEN:
        return False, f"Password must be at least {_DEFAULT_MIN_LEN} characters long."
    # Character classes
    has_letter = bool(re.search(r"[A-Za-z]", pw))
    has_digit = bool(re.search(r"\d", pw))
    has_symbol = bool(re.search(r"[^A-Za-z0-9]", pw))
    if not (has_letter and has_digit):
        return False, "Include both letters and numbers."
    if _REQUIRE_SYMBOLS and not has_symbol:
        return False, "Include at least one symbol (e.g., !@#$)."
    # Reject trivial/common passwords (case-insensitive exact match)
    if pw.lower() in _COMMON_WEAK:
        return False, "That password is too common. Choose something more unique."
    # Simple repeated or sequential checks
    if len(set(pw)) <= 2:
        return False, "Password is too simple or repetitive."
    if re.fullmatch(r"(\d)\1{5,}", pw):
        return False, "Password cannot be a repeated number sequence."
    if re.search(r"(12345|23456|34567|45678|56789|67890)", pw):
        return False, "Avoid simple numeric sequences like 12345."
    # Avoid including username/email local part
    if username:
        u = str(username).strip().lower()
        local = u.split("@", 1)[0] if "@" in u else u
        if local and local in pw.lower():
            return False, "Password must not contain your email/username."
    return True, "ok"
