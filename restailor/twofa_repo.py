from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
import logging

import sqlalchemy as sa
from sqlalchemy.orm import Session


# Note: We intentionally use SQL (text/expressions) instead of ORM models here
# because the new 2FA columns/tables are not mapped in models.py. This keeps
# the change surface small and avoids touching existing ORM models.


_LOG = logging.getLogger(__name__)

def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


# -----------------------------
# Users 2FA state management
# -----------------------------

def set_user_totp_secret(
    db: Session,
    user_id: int,
    encrypted_secret: str,
) -> int:
    """Set/replace the user's encrypted TOTP secret. 2FA is NOT enabled until confirmation.

    Returns number of rows updated (0 or 1).
    """
    stmt = sa.text(
        """
        UPDATE users
        SET
            totp_secret = :secret,
            updated_at = now()
        WHERE id = :uid
        """
    )
    res = db.execute(stmt, {"secret": encrypted_secret, "uid": user_id})
    db.commit()
    return int(getattr(res, "rowcount", 0) or 0)


def confirm_user_totp(
    db: Session,
    user_id: int,
    hashed_recovery_codes: list[str],
) -> int:
    """Enable 2FA by confirming TOTP setup and storing recovery codes.

    Returns number of rows updated (0 or 1).
    """
    stmt = sa.text(
        """
        UPDATE users
        SET
            two_factor_enabled = TRUE,
            recovery_codes = :codes,
            updated_at = now()
        WHERE id = :uid
        """
    )
    # PostgreSQL ARRAY bind: SQLAlchemy will map Python list -> ARRAY when paramstyle is text
    res = db.execute(stmt, {"codes": hashed_recovery_codes, "uid": user_id})
    db.commit()
    return int(getattr(res, "rowcount", 0) or 0)


def disable_user_2fa(db: Session, user_id: int) -> int:
    """Disable and clear all 2FA-related fields for a user.

    Returns number of rows updated (0 or 1).
    """
    stmt = sa.text(
        """
        UPDATE users
        SET
            two_factor_enabled = FALSE,
            totp_secret = NULL,
            recovery_codes = NULL,
            last_2fa_at = NULL,
            updated_at = now()
        WHERE id = :uid
        """
    )
    res = db.execute(stmt, {"uid": user_id})
    db.commit()
    return int(getattr(res, "rowcount", 0) or 0)


def update_last_2fa_at(db: Session, user_id: int) -> int:
    """Update last_2fa_at to now(). Returns number of rows updated."""
    stmt = sa.text(
        """
        UPDATE users
        SET last_2fa_at = now()
        WHERE id = :uid
        """
    )
    res = db.execute(stmt, {"uid": user_id})
    db.commit()
    return int(getattr(res, "rowcount", 0) or 0)


def get_user_2fa_state(db: Session, user_id: int) -> dict[str, Any] | None:
    """Fetch 2FA-related state for a user. Returns a dict or None if user not found.

    Keys: two_factor_enabled (bool), totp_secret (str|None), recovery_codes (list[str]|None)
    """
    stmt = sa.text(
        """
        SELECT two_factor_enabled, totp_secret, recovery_codes
        FROM users
        WHERE id = :uid
        """
    )
    row = db.execute(stmt, {"uid": user_id}).mappings().first()
    return dict(row) if row else None


# -----------------------------
# Trusted devices repository
# -----------------------------

def store_trusted_device(
    db: Session,
    user_id: int,
    token_hash: str,
    user_agent: Optional[str],
    ip_prefix: Optional[str],
    expires_at: datetime,
) -> int:
    """Insert a trusted device row; returns its id."""
    # Prefer inserting ip_prefix when column exists; fall back for older schemas
    try:
        # Prefer inserting last_used_at = now() and ip_prefix when columns exist
        stmt = sa.text(
            """
            INSERT INTO user_trusted_devices (user_id, token_hash, user_agent, ip_prefix, expires_at, last_used_at)
            VALUES (:uid, :thash, :ua, :ipx, :exp, now())
            RETURNING id
            """
        )
        row = db.execute(
            stmt,
            {"uid": user_id, "thash": token_hash, "ua": user_agent, "ipx": ip_prefix, "exp": expires_at},
        ).first()
        db.commit()
        return int(row[0]) if row else 0
    except Exception as e:
        # If last_used_at or ip_prefix are missing, retry with reduced columns
        msg = str(e)
        # Ensure the failed transaction is cleared before retrials
        try:
            db.rollback()
        except Exception as rb_err:
            _LOG.debug("twofa_repo.store_trusted_device: rollback failed after initial insert error: %s", rb_err)
        try:
            if "last_used_at" in msg and "ip_prefix" in msg:
                stmt2 = sa.text(
                    """
                    INSERT INTO user_trusted_devices (user_id, token_hash, user_agent, expires_at)
                    VALUES (:uid, :thash, :ua, :exp)
                    RETURNING id
                    """
                )
                row = db.execute(stmt2, {"uid": user_id, "thash": token_hash, "ua": user_agent, "exp": expires_at}).first()
                db.commit()
                return int(row[0]) if row else 0
            if "last_used_at" in msg:
                try:
                    db.rollback()
                except Exception as rb_err2:
                    _LOG.debug("twofa_repo.store_trusted_device: rollback failed before retry without last_used_at: %s", rb_err2)
                stmt3 = sa.text(
                    """
                    INSERT INTO user_trusted_devices (user_id, token_hash, user_agent, ip_prefix, expires_at)
                    VALUES (:uid, :thash, :ua, :ipx, :exp)
                    RETURNING id
                    """
                )
                row = db.execute(stmt3, {"uid": user_id, "thash": token_hash, "ua": user_agent, "ipx": ip_prefix, "exp": expires_at}).first()
                db.commit()
                return int(row[0]) if row else 0
            if "ip_prefix" in msg:
                try:
                    db.rollback()
                except Exception as rb_err3:
                    _LOG.debug("twofa_repo.store_trusted_device: rollback failed before retry without ip_prefix: %s", rb_err3)
                stmt4 = sa.text(
                    """
                    INSERT INTO user_trusted_devices (user_id, token_hash, user_agent, expires_at, last_used_at)
                    VALUES (:uid, :thash, :ua, :exp, now())
                    RETURNING id
                    """
                )
                row = db.execute(stmt4, {"uid": user_id, "thash": token_hash, "ua": user_agent, "exp": expires_at}).first()
                db.commit()
                return int(row[0]) if row else 0
        except Exception as retry_err:
            _LOG.debug("twofa_repo.store_trusted_device: retry path failed: %s", retry_err)
        # Final fallback (legacy schemas)
        try:
            db.rollback()
        except Exception as rb_err4:
            _LOG.debug("twofa_repo.store_trusted_device: rollback failed before final fallback: %s", rb_err4)
        stmt5 = sa.text(
            """
            INSERT INTO user_trusted_devices (user_id, token_hash, user_agent, expires_at)
            VALUES (:uid, :thash, :ua, :exp)
            RETURNING id
            """
        )
        row = db.execute(stmt5, {"uid": user_id, "thash": token_hash, "ua": user_agent, "exp": expires_at}).first()
        db.commit()
        return int(row[0]) if row else 0


def has_trusted_device(db: Session, user_id: int, token_hash: str) -> bool:
    """Check whether a non-expired trusted device exists and touch last_used_at if supported."""
    # Attempt to update last_used_at when present; fall back to SELECT
    try:
        stmt = sa.text(
            """
            UPDATE user_trusted_devices
            SET last_used_at = now()
            WHERE user_id = :uid AND token_hash = :thash AND (expires_at IS NULL OR expires_at > now())
            RETURNING 1
            """
        )
        row = db.execute(stmt, {"uid": user_id, "thash": token_hash}).first()
        db.commit()
        if row is not None:
            return True
    except Exception as e:
        # If column missing, fall back to simple existence check
        if "last_used_at" not in str(e):
            # Unknown failure; propagate
            raise
        # Clear failed transaction before fallback SELECT
        try:
            db.rollback()
        except Exception as rb_err:
            _LOG.debug("twofa_repo.has_trusted_device: rollback failed after update error: %s", rb_err)
    stmt2 = sa.text(
        """
        SELECT 1 FROM user_trusted_devices
        WHERE user_id = :uid AND token_hash = :thash AND (expires_at IS NULL OR expires_at > now())
        LIMIT 1
        """
    )
    row2 = db.execute(stmt2, {"uid": user_id, "thash": token_hash}).first()
    return row2 is not None


def has_trusted_device_checked(
    db: Session,
    user_id: int,
    token_hash: str,
    expected_user_agent: Optional[str],
    expected_ip_prefix: Optional[str],
    *,
    enforce_user_agent: bool = False,
    enforce_ip_prefix: bool = False,
) -> bool:
    """Check if a trusted device is valid with optional UA/IP enforcement.

    - Returns True only if a non-expired device exists with matching token_hash (and user_id),
      and, when enforcement flags are True, matches the expected UA/IP prefix.
    - Touches last_used_at when the column exists.
    - If the schema lacks ip_prefix, IP enforcement is skipped (treated as pass).
    """
    has_ipx = _trusted_devices_has_ip_prefix(db)
    # Fetch the device row and relevant columns
    if has_ipx:
        sel = sa.text(
            """
            SELECT user_agent, ip_prefix
            FROM user_trusted_devices
            WHERE user_id = :uid AND token_hash = :thash AND (expires_at IS NULL OR expires_at > now())
            LIMIT 1
            """
        )
    else:
        sel = sa.text(
            """
            SELECT user_agent
            FROM user_trusted_devices
            WHERE user_id = :uid AND token_hash = :thash AND (expires_at IS NULL OR expires_at > now())
            LIMIT 1
            """
        )
    row = db.execute(sel, {"uid": user_id, "thash": token_hash}).first()
    if row is None:
        _LOG.info(f"has_trusted_device_checked: NO ROW FOUND for user_id={user_id}, token_hash={token_hash[:20]}...")
        return False
    # Unpack
    stored_ua = None
    stored_ipx = None
    try:
        if has_ipx:
            stored_ua = row[0]
            stored_ipx = row[1]
        else:
            stored_ua = row[0]
    except Exception as unpack_err:
        _LOG.debug("twofa_repo.has_trusted_device_checked: failed unpacking row: %s", unpack_err)
    # Enforce UA match when requested (compare normalized UA fingerprints, tolerant of stored labels)
    if enforce_user_agent:
        try:
            from .device_fp import normalize_user_agent as _norm
            exp_norm = _norm(str(expected_user_agent or ""))
            sto_norm = _norm(str(stored_ua or ""))
            # Compare core fields; allow None vs '' by str() normalization
            same = (
                str(exp_norm.get("browser_family")) == str(sto_norm.get("browser_family")) and
                str(exp_norm.get("browser_major")) == str(sto_norm.get("browser_major")) and
                str(exp_norm.get("os_family")) == str(sto_norm.get("os_family")) and
                str(exp_norm.get("os_major")) == str(sto_norm.get("os_major")) and
                str(exp_norm.get("arch")) == str(sto_norm.get("arch"))
            )
            if not same:
                _LOG.info(f"has_trusted_device_checked: UA MISMATCH for user_id={user_id}, expected={exp_norm}, stored={sto_norm}")
                return False
        except Exception:
            # Fallback to strict string compare if normalization fails
            if not expected_user_agent or not stored_ua or str(stored_ua) != str(expected_user_agent):
                return False
    # Enforce IP prefix match when requested and column present
    if enforce_ip_prefix and has_ipx:
        if not expected_ip_prefix or not stored_ipx or str(stored_ipx) != str(expected_ip_prefix):
            _LOG.info(f"has_trusted_device_checked: IP MISMATCH for user_id={user_id}, expected={expected_ip_prefix}, stored={stored_ipx}")
            return False
    # Touch last_used_at when available (best-effort)
    try:
        stmt_upd = sa.text(
            """
            UPDATE user_trusted_devices
            SET last_used_at = now()
            WHERE user_id = :uid AND token_hash = :thash AND (expires_at IS NULL OR expires_at > now())
            """
        )
        db.execute(stmt_upd, {"uid": user_id, "thash": token_hash})
        db.commit()
    except Exception as upd_err:
        _LOG.debug("twofa_repo.has_trusted_device_checked: touch last_used_at failed: %s", upd_err)
        try:
            db.rollback()
        except Exception as rb_err:
            _LOG.debug("twofa_repo.has_trusted_device_checked: rollback after touch failure failed: %s", rb_err)
    _LOG.info(f"has_trusted_device_checked: SUCCESS for user_id={user_id}, token_hash={token_hash[:20]}...")
    return True


def delete_all_trusted_devices(db: Session, user_id: int) -> int:
    """Delete all trusted devices for the given user. Returns number of rows deleted."""
    stmt = sa.text("DELETE FROM user_trusted_devices WHERE user_id = :uid")
    res = db.execute(stmt, {"uid": user_id})
    db.commit()
    return int(getattr(res, "rowcount", 0) or 0)


def revoke_device(db: Session, user_id: int, token_hash: str) -> int:
    """Delete a specific trusted device by hash. Returns number of rows deleted."""
    stmt = sa.text(
        "DELETE FROM user_trusted_devices WHERE user_id = :uid AND token_hash = :thash"
    )
    res = db.execute(stmt, {"uid": user_id, "thash": token_hash})
    db.commit()
    return int(getattr(res, "rowcount", 0) or 0)


def revoke_device_by_id(db: Session, user_id: int, device_id: int) -> int:
    stmt = sa.text(
        "DELETE FROM user_trusted_devices WHERE user_id = :uid AND id = :did"
    )
    res = db.execute(stmt, {"uid": user_id, "did": device_id})
    db.commit()
    return int(getattr(res, "rowcount", 0) or 0)


def _trusted_devices_has_ip_prefix(db: Session) -> bool:
    """Detect if user_trusted_devices has ip_prefix column (for backward compat)."""
    try:
        probe = sa.text(
            """
            SELECT 1
            FROM information_schema.columns
            WHERE table_name = 'user_trusted_devices' AND column_name = 'ip_prefix'
            LIMIT 1
            """
        )
        row = db.execute(probe).first()
        return bool(row)
    except Exception:
        return False


def _trusted_devices_has_last_used(db: Session) -> bool:
    try:
        probe = sa.text(
            """
            SELECT 1
            FROM information_schema.columns
            WHERE table_name = 'user_trusted_devices' AND column_name = 'last_used_at'
            LIMIT 1
            """
        )
        row = db.execute(probe).first()
        return bool(row)
    except Exception:
        return False


def list_trusted_devices(db: Session, user_id: int) -> list[dict[str, Any]]:
    has_ipx = _trusted_devices_has_ip_prefix(db)
    has_last = _trusted_devices_has_last_used(db)
    if has_ipx and has_last:
        stmt = sa.text(
            """
            SELECT id, created_at, expires_at, user_agent, ip_prefix, last_used_at
            FROM user_trusted_devices
            WHERE user_id = :uid
            ORDER BY created_at DESC
            """
        )
    elif has_ipx and not has_last:
        stmt = sa.text(
            """
            SELECT id, created_at, expires_at, user_agent, ip_prefix
            FROM user_trusted_devices
            WHERE user_id = :uid
            ORDER BY created_at DESC
            """
        )
    elif (not has_ipx) and has_last:
        stmt = sa.text(
            """
            SELECT id, created_at, expires_at, user_agent, last_used_at
            FROM user_trusted_devices
            WHERE user_id = :uid
            ORDER BY created_at DESC
            """
        )
    else:
        stmt = sa.text(
            """
            SELECT id, created_at, expires_at, user_agent
            FROM user_trusted_devices
            WHERE user_id = :uid
            ORDER BY created_at DESC
            """
        )
    rows = db.execute(stmt, {"uid": user_id}).mappings().all()
    # Normalize shape: ensure optional keys exist for callers
    out: list[dict[str, Any]] = []
    for r in rows:
        d = dict(r)
        if "ip_prefix" not in d:
            d["ip_prefix"] = None
        if "last_used_at" not in d:
            d["last_used_at"] = None
        out.append(d)
    return out


def count_trusted_devices(db: Session, user_id: int) -> int:
    stmt = sa.text(
        """
        SELECT COUNT(*) FROM user_trusted_devices WHERE user_id = :uid
        """
    )
    row = db.execute(stmt, {"uid": int(user_id)}).first()
    try:
        return int(row[0]) if row else 0
    except Exception:
        return 0


def find_trusted_device_by_fingerprint(
    db: Session,
    user_id: int,
    user_agent: Optional[str],
    ip_prefix: Optional[str],
) -> Optional[dict[str, Any]]:
    """Find most recent, non-expired trusted device for a user that matches a normalized UA
    and optional IP prefix. We fetch a few recent rows and compare normalized UA in Python
    to avoid schema changes. Returns mapping with at least {id, token_hash} or None.
    """
    from .device_fp import normalize_user_agent
    cand = normalize_user_agent(user_agent or "")
    has_ipx = _trusted_devices_has_ip_prefix(db)
    try:
        if has_ipx:
            stmt = sa.text(
                """
                SELECT id, token_hash, user_agent, ip_prefix
                FROM user_trusted_devices
                WHERE user_id = :uid
                  AND (expires_at IS NULL OR expires_at > now())
                ORDER BY created_at DESC
                LIMIT 10
                """
            )
        else:
            stmt = sa.text(
                """
                SELECT id, token_hash, user_agent
                FROM user_trusted_devices
                WHERE user_id = :uid
                  AND (expires_at IS NULL OR expires_at > now())
                ORDER BY created_at DESC
                LIMIT 10
                """
            )
        rows = db.execute(stmt, {"uid": int(user_id)}).mappings().all()
        for r in rows:
            try:
                n = normalize_user_agent(str(r.get("user_agent") or ""))
                # Compare core fields; ignore None vs '' differences
                same = (
                    (str(cand.get("browser_family")) == str(n.get("browser_family"))) and
                    (str(cand.get("browser_major")) == str(n.get("browser_major"))) and
                    (str(cand.get("os_family")) == str(n.get("os_family"))) and
                    (str(cand.get("os_major")) == str(n.get("os_major"))) and
                    (str(cand.get("arch")) == str(n.get("arch")))
                )
                if not same:
                    continue
                if has_ipx and ip_prefix is not None:
                    if str(r.get("ip_prefix") or "") != str(ip_prefix or ""):
                        continue
                return dict(r)
            except Exception:
                continue
        return None
    except Exception as ex:
        _LOG.debug("twofa_repo.find_trusted_device_by_fingerprint failed: %s", ex)
        return None


def rotate_trusted_device_token(
    db: Session,
    user_id: int,
    device_id: int,
    new_token_hash: str,
    expires_at: datetime,
    new_user_agent: Optional[str] = None,
) -> int:
    """Rotate token for an existing trusted device row and refresh expiry.

    Tries to also touch last_used_at = now() when column exists.
    Returns number of rows updated.
    """
    try:
        if new_user_agent is not None:
            stmt = sa.text(
                """
                UPDATE user_trusted_devices
                SET token_hash = :thash, expires_at = :exp, user_agent = :ua, last_used_at = now()
                WHERE user_id = :uid AND id = :did
                """
            )
            res = db.execute(stmt, {"thash": new_token_hash, "exp": expires_at, "ua": new_user_agent, "uid": int(user_id), "did": int(device_id)})
            db.commit()
            return int(getattr(res, "rowcount", 0) or 0)
        else:
            stmt = sa.text(
                """
                UPDATE user_trusted_devices
                SET token_hash = :thash, expires_at = :exp, last_used_at = now()
                WHERE user_id = :uid AND id = :did
                """
            )
            res = db.execute(stmt, {"thash": new_token_hash, "exp": expires_at, "uid": int(user_id), "did": int(device_id)})
            db.commit()
            return int(getattr(res, "rowcount", 0) or 0)
    except Exception as e:
        if "last_used_at" not in str(e):
            # If user_agent column is missing (legacy), fall through to minimal update
            if new_user_agent is not None and "user_agent" in str(e):
                try:
                    db.rollback()
                except Exception:
                    pass
                stmt_min = sa.text(
                    """
                    UPDATE user_trusted_devices
                    SET token_hash = :thash, expires_at = :exp
                    WHERE user_id = :uid AND id = :did
                    """
                )
                res_min = db.execute(stmt_min, {"thash": new_token_hash, "exp": expires_at, "uid": int(user_id), "did": int(device_id)})
                db.commit()
                return int(getattr(res_min, "rowcount", 0) or 0)
            raise
        # Handle schemas without last_used_at
        try:
            db.rollback()
        except Exception:
            pass
        if new_user_agent is not None:
            stmt2 = sa.text(
                """
                UPDATE user_trusted_devices
                SET token_hash = :thash, expires_at = :exp, user_agent = :ua
                WHERE user_id = :uid AND id = :did
                """
            )
            res2 = db.execute(stmt2, {"thash": new_token_hash, "exp": expires_at, "ua": new_user_agent, "uid": int(user_id), "did": int(device_id)})
            db.commit()
            return int(getattr(res2, "rowcount", 0) or 0)
        else:
            stmt3 = sa.text(
                """
                UPDATE user_trusted_devices
                SET token_hash = :thash, expires_at = :exp
                WHERE user_id = :uid AND id = :did
                """
            )
            res3 = db.execute(stmt3, {"thash": new_token_hash, "exp": expires_at, "uid": int(user_id), "did": int(device_id)})
            db.commit()
            return int(getattr(res3, "rowcount", 0) or 0)


def evict_oldest_trusted_devices(db: Session, user_id: int, n: int = 1) -> int:
    """Delete n oldest trusted device rows for user; returns rows deleted."""
    n = max(0, int(n))
    if n == 0:
        return 0
    # Delete by id of oldest rows
    stmt = sa.text(
        """
        DELETE FROM user_trusted_devices
        WHERE id IN (
            SELECT id FROM user_trusted_devices
            WHERE user_id = :uid
            ORDER BY created_at ASC
            LIMIT :lim
        )
        """
    )
    res = db.execute(stmt, {"uid": int(user_id), "lim": int(n)})
    db.commit()
    return int(getattr(res, "rowcount", 0) or 0)


def update_trusted_device_expiry(
    db: Session,
    user_id: int,
    token_hash: str,
    expires_at: datetime,
) -> int:
    """Refresh expires_at and touch last_used_at for a trusted device. Returns rows updated.

    Works with schemas that may not have last_used_at by retrying without it.
    """
    try:
        stmt = sa.text(
            """
            UPDATE user_trusted_devices
            SET expires_at = :exp, last_used_at = now()
            WHERE user_id = :uid AND token_hash = :thash
            """
        )
        res = db.execute(stmt, {"exp": expires_at, "uid": int(user_id), "thash": token_hash})
        db.commit()
        return int(getattr(res, "rowcount", 0) or 0)
    except Exception as e:
        if "last_used_at" not in str(e):
            # Unknown failure; propagate
            raise
        try:
            db.rollback()
        except Exception:
            pass
        stmt2 = sa.text(
            """
            UPDATE user_trusted_devices
            SET expires_at = :exp
            WHERE user_id = :uid AND token_hash = :thash
            """
        )
        res2 = db.execute(stmt2, {"exp": expires_at, "uid": int(user_id), "thash": token_hash})
        db.commit()
        return int(getattr(res2, "rowcount", 0) or 0)


def delete_stale_unused_trusted_devices(db: Session, older_than_days: int = 14) -> int:
    """Delete devices never used (last_used_at is NULL) older than cutoff days.

    Returns rows deleted. Uses created_at timestamp for age.
    """
    try:
        from datetime import timedelta
        cutoff = _utc_now() - timedelta(days=int(max(1, older_than_days)))
        stmt = sa.text(
            """
            DELETE FROM user_trusted_devices
            WHERE last_used_at IS NULL AND created_at <= :cut
            """
        )
        res = db.execute(stmt, {"cut": cutoff})
        db.commit()
        return int(getattr(res, "rowcount", 0) or 0)
    except Exception as ex:
        _LOG.debug("twofa_repo.delete_stale_unused_trusted_devices failed: %s", ex)
        try:
            db.rollback()
        except Exception:
            pass
        return 0


# -----------------------------
# Email OTP lifecycle repository
# -----------------------------

def delete_expired_email_otps(db: Session) -> int:
    """Delete email OTPs past their expires_at; returns number of rows deleted."""
    stmt = sa.text("DELETE FROM email_otps WHERE expires_at IS NOT NULL AND expires_at <= now()")
    res = db.execute(stmt)
    db.commit()
    return int(getattr(res, "rowcount", 0) or 0)


def delete_expired_trusted_devices(db: Session) -> int:
    """Delete trusted devices past their expires_at; returns number of rows deleted."""
    stmt = sa.text("DELETE FROM user_trusted_devices WHERE expires_at IS NOT NULL AND expires_at <= now()")
    res = db.execute(stmt)
    db.commit()
    return int(getattr(res, "rowcount", 0) or 0)


def delete_user_email_otps(db: Session, user_id: int) -> int:
    """Delete all email OTP rows for a user. Returns number of rows deleted."""
    stmt = sa.text("DELETE FROM email_otps WHERE user_id = :uid")
    res = db.execute(stmt, {"uid": int(user_id)})
    db.commit()
    return int(getattr(res, "rowcount", 0) or 0)


def purge_user_twofa_artifacts(db: Session, user_id: int) -> dict[str, int]:
    """Clear all 2FA-related data for a user (trusted devices, email OTPs, user columns).

    Returns a dict with counts: {"trusted": n1, "otps": n2, "user": 1 or 0}
    """
    # Delete trusted devices
    r1 = db.execute(sa.text("DELETE FROM user_trusted_devices WHERE user_id = :uid"), {"uid": int(user_id)})
    # Delete email OTPs
    r2 = db.execute(sa.text("DELETE FROM email_otps WHERE user_id = :uid"), {"uid": int(user_id)})
    # Clear user columns
    r3 = db.execute(
        sa.text(
            """
            UPDATE users
            SET
                two_factor_enabled = FALSE,
                totp_secret = NULL,
                recovery_codes = NULL,
                last_2fa_at = NULL
            WHERE id = :uid
            """
        ),
        {"uid": int(user_id)},
    )
    db.commit()
    return {
        "trusted": int(getattr(r1, "rowcount", 0) or 0),
        "otps": int(getattr(r2, "rowcount", 0) or 0),
        "user": int(getattr(r3, "rowcount", 0) or 0),
    }


# -----------------------------
# Recovery codes maintenance
# -----------------------------

def update_recovery_codes(db: Session, user_id: int, codes: list[str]) -> int:
    """Replace the user's recovery_codes array with the provided list.

    Returns number of rows updated (0 or 1).
    """
    stmt = sa.text(
        """
        UPDATE users
        SET recovery_codes = :codes
        WHERE id = :uid
        """
    )
    res = db.execute(stmt, {"codes": codes, "uid": user_id})
    db.commit()
    return int(getattr(res, "rowcount", 0) or 0)


def get_active_email_otp(db: Session, user_id: int) -> Optional[dict[str, Any]]:
    """Fetch the latest, non-consumed, non-expired OTP for a user (if any)."""
    stmt = sa.text(
        """
        SELECT id, user_id, code_hash, sent_to, ip, user_agent, created_at, expires_at, consumed_at, attempts, max_attempts
        FROM email_otps
        WHERE user_id = :uid
          AND consumed_at IS NULL
          AND (expires_at IS NULL OR expires_at > now())
        ORDER BY created_at DESC
        LIMIT 1
        """
    )
    row = db.execute(stmt, {"uid": user_id}).mappings().first()
    return dict(row) if row else None


def insert_email_otp(
    db: Session,
    user_id: int,
    code_hash: str,
    sent_to: str,
    ip: Optional[str],
    user_agent: Optional[str],
    ttl_seconds: int,
    max_attempts: int = 5,
) -> int:
    """Insert a new OTP and return its id."""
    # Compute expires_at in the DB for consistency
    stmt = sa.text(
        """
        INSERT INTO email_otps (user_id, code_hash, sent_to, ip, user_agent, expires_at, max_attempts)
        VALUES (:uid, :chash, :sent, :ip, :ua, now() + (:ttl || ' seconds')::interval, :maxa)
        RETURNING id
        """
    )
    row = db.execute(
        stmt,
        {"uid": user_id, "chash": code_hash, "sent": sent_to, "ip": ip, "ua": user_agent, "ttl": int(ttl_seconds), "maxa": int(max_attempts)},
    ).first()
    db.commit()
    return int(row[0]) if row else 0


def increment_email_otp_attempts(db: Session, otp_id: int) -> tuple[int, int]:
    """Increment attempts counter; returns (attempts, max_attempts)."""
    stmt = sa.text(
        """
        UPDATE email_otps
        SET attempts = attempts + 1
        WHERE id = :oid
        RETURNING attempts, max_attempts
        """
    )
    row = db.execute(stmt, {"oid": otp_id}).first()
    db.commit()
    if not row:
        return (0, 0)
    return int(row[0]), int(row[1])


def consume_email_otp(db: Session, otp_id: int) -> int:
    """Mark an OTP as consumed; returns number of rows updated."""
    stmt = sa.text(
        """
        UPDATE email_otps
        SET consumed_at = now()
        WHERE id = :oid AND consumed_at IS NULL
        """
    )
    res = db.execute(stmt, {"oid": otp_id})
    db.commit()
    return int(getattr(res, "rowcount", 0) or 0)
