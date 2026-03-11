"""Two-factor auth (2FA/MFA) helpers.

Includes:
- TOTP secret generation and provisioning URI
- QR code rendering to base64 PNG
- Recovery codes (generate, hash, verify)
- Encrypt/decrypt TOTP secret with Fernet
- Trusted device cookie signing/unsigning via itsdangerous TimestampSigner
- Small date/time utils and code validators
"""
from __future__ import annotations

import base64
import io
import os
import secrets
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Iterable, List, Optional, Tuple

import pyotp
import qrcode
from qrcode.constants import ERROR_CORRECT_M
from cryptography.fernet import Fernet, InvalidToken
from itsdangerous import BadSignature, BadTimeSignature, TimestampSigner
from passlib.hash import bcrypt as bcrypt_hash

from .app_config import CONFIG
from .constants import days_to_seconds

# Module-level caches for test/dev defaults when strict secrets are disabled
_FERNET: Optional[Fernet] = None
_REMEMBER_SECRET: Optional[str] = None


def _truthy(v: Optional[str]) -> bool:
    return str(v or "").strip().lower() in {"1", "true", "yes", "y", "on"}


def _strict_secrets_enabled() -> bool:
    """Return True if secrets must be provided (prod), else False (tests/dev)."""
    try:
        if os.getenv("STRICT_SECRETS") is not None:
            return _truthy(os.getenv("STRICT_SECRETS"))
    except Exception as ex:
        import logging as _log
        _log.getLogger(__name__).debug("twofa._strict_secrets_enabled: env parse failed: %s", ex)
    try:
        return bool((CONFIG.get("security", {}) or {}).get("strict_secrets", False))
    except Exception:
        return False


# -------- Time helpers --------
def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def in_days(days: int) -> datetime:
    return now_utc() + timedelta(days=int(days))


# -------- TOTP helpers --------
def generate_totp_secret() -> str:
    """Generate a new base32 TOTP secret suitable for authenticator apps."""
    return pyotp.random_base32()


def build_totp_uri(secret: str, email: str, issuer: str) -> str:
    """Return otpauth provisioning URI for QR code enrollment.

    Args:
        secret: TOTP shared secret (base32)
        email: account name (user email)
        issuer: app/organization name (e.g., "Restailor")

    Follow the standard: set account name to the email and issuer_name separately.
    Most authenticator apps will render this as "<issuer>: <email>" automatically.
    """
    totp = pyotp.TOTP(secret)
    return totp.provisioning_uri(name=email, issuer_name=issuer)


def render_qr_base64(uri: str) -> str:
    """Render a QR code PNG for the given URI and return as data URL base64 string."""
    qr = qrcode.QRCode(version=1, error_correction=ERROR_CORRECT_M, box_size=8, border=3)
    qr.add_data(uri)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, "PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{b64}"


# -------- Recovery codes --------
def generate_recovery_codes(n: int = 10) -> List[str]:
    """Generate n recovery codes as 8-char hex strings.

    Default count may be overridden by config at call sites.
    """
    n = max(1, int(n))
    return [secrets.token_hex(4) for _ in range(n)]  # 4 bytes -> 8 hex chars


def hash_recovery_code(code: str) -> str:
    """Hash a single recovery code with bcrypt."""
    return bcrypt_hash.hash(code)


def hash_recovery_codes(codes: Iterable[str]) -> List[str]:
    return [hash_recovery_code(c) for c in codes]


def verify_recovery_code(code: str, hashed_codes: Iterable[str]) -> Optional[int]:
    """Return index of matching hashed code if valid, else None."""
    for idx, h in enumerate(hashed_codes):
        try:
            ok = bcrypt_hash.verify(code, h)
        except (ValueError, TypeError):
            # Malformed hash input; treat as non-match
            ok = False
        if ok:
            return idx
    return None


# -------- Fernet encryption for TOTP secrets --------
def _get_fernet() -> Fernet:
    global _FERNET
    if _FERNET is not None:
        return _FERNET
    # Prefer keyring, then env; do not load secrets from config file
    key = ""
    try:
        import keyring  # type: ignore
        kv = keyring.get_password("restailor", "TOTP_FERNET_KEY")  # type: ignore[attr-defined]
        if kv and kv.strip():
            key = kv
    except Exception as ex:
        import logging as _log
        _log.getLogger(__name__).debug("twofa._get_fernet: keyring read failed: %s", ex)
    if not key:
        key = os.getenv("TOTP_FERNET_KEY") or ""
    if not key:
        if _strict_secrets_enabled():
            raise RuntimeError("TOTP_FERNET_KEY not configured")
        # Non-strict mode (tests/dev): generate a process-local key
        key = Fernet.generate_key().decode("ascii")
    try:
        _FERNET = Fernet(key)
        return _FERNET
    except Exception as ex:
        raise RuntimeError("Invalid TOTP_FERNET_KEY; expected urlsafe base64 32-byte key") from ex


def encrypt_totp_secret(secret: str) -> str:
    f = _get_fernet()
    token = f.encrypt(secret.encode("utf-8"))
    return token.decode("ascii")


def decrypt_totp_secret(token: str) -> str:
    f = _get_fernet()
    try:
        plain = f.decrypt(token.encode("ascii"))
        return plain.decode("utf-8")
    except (InvalidToken, ValueError, TypeError) as ex:
        raise ValueError("Invalid or corrupted TOTP secret token") from ex


# -------- Trusted devices cookie helpers --------
def _get_remember_secret() -> str:
    global _REMEMBER_SECRET
    if _REMEMBER_SECRET:
        return _REMEMBER_SECRET
    # Prefer keyring, then env; do not load from config file
    v = None
    try:
        import keyring  # type: ignore
        v = keyring.get_password("restailor", "SECURITY_REMEMBER_SIGNER_SECRET")  # type: ignore[attr-defined]
    except Exception:
        v = None
    if not v:
        v = os.getenv("SECURITY_REMEMBER_SIGNER_SECRET")
    if v and v.strip():
        _REMEMBER_SECRET = v
        return _REMEMBER_SECRET
    # Do not load signer secret from config file; require keyring/env in strict mode
    if _strict_secrets_enabled():
        raise RuntimeError("SECURITY_REMEMBER_SIGNER_SECRET not configured")
    # Non-strict mode (tests/dev): generate a process-local random secret
    _REMEMBER_SECRET = secrets.token_urlsafe(48)
    return _REMEMBER_SECRET


def _signer() -> TimestampSigner:
    return TimestampSigner(_get_remember_secret())


def make_trusted_cookie_value(user_id: int, raw_token: str) -> str:
    """Create a signed cookie value that encodes user_id and a random token."""
    payload = f"{int(user_id)}:{raw_token}"
    signed = _signer().sign(payload.encode("utf-8"))
    return signed.decode("utf-8")


def unsign_trusted_cookie(value: str, max_age_days: int) -> Optional[Tuple[int, str]]:
    """Validate a trusted device cookie and return (user_id, raw_token) if ok.

    max_age_days controls the timestamp validity window embedded by TimestampSigner.
    """
    try:
        unsigned = _signer().unsign(value.encode("utf-8"), max_age=days_to_seconds(max_age_days))
        data = unsigned.decode("utf-8")
        if ":" not in data:
            return None
        uid_s, tok = data.split(":" ,1)
        return (int(uid_s), tok)
    except (BadTimeSignature, BadSignature, ValueError):
        return None


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


# -------- Input validators --------
def _digits_only(code: str) -> str:
    c = (code or "").strip().replace(" ", "")
    if not c.isdigit():
        raise ValueError("Code must contain digits only")
    return c


def validate_totp_code(code: str, *, length: int = 6) -> str:
    c = _digits_only(code)
    if length and len(c) != length:
        raise ValueError(f"TOTP code must be {length} digits")
    return c


def validate_email_code(code: str, *, length: int = 6) -> str:
    c = _digits_only(code)
    if length and len(c) != length:
        raise ValueError(f"Email code must be {length} digits")
    return c


__all__ = [
    "now_utc",
    "in_days",
    "generate_totp_secret",
    "build_totp_uri",
    "render_qr_base64",
    "generate_recovery_codes",
    "hash_recovery_code",
    "hash_recovery_codes",
    "verify_recovery_code",
    "encrypt_totp_secret",
    "decrypt_totp_secret",
    "make_trusted_cookie_value",
    "unsign_trusted_cookie",
    "sha256_hex",
    "validate_totp_code",
    "validate_email_code",
]
