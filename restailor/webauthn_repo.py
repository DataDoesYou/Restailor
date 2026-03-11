from __future__ import annotations

from typing import Any, Optional
from sqlalchemy.orm import Session
import sqlalchemy as sa


def insert_credential(
    db: Session,
    user_id: int,
    credential_id: str,
    public_key: bytes,
    sign_count: int,
    transports: Optional[list[str]] = None,
    aaguid: Optional[str] = None,
    nickname: Optional[str] = None,
) -> int:
    """Insert a WebAuthn credential for the user; returns row id."""
    stmt = sa.text(
        """
        INSERT INTO webauthn_credentials
            (user_id, credential_id, public_key, sign_count, transports, aaguid, nickname)
        VALUES (:uid, :cid, :pkey, :sc, :tr, :ag, :nick)
        RETURNING id
        """
    )
    row = db.execute(
        stmt,
        {
            "uid": int(user_id),
            "cid": str(credential_id),
            "pkey": public_key,
            "sc": int(sign_count or 0),
            "tr": transports or None,
            "ag": aaguid or None,
            "nick": nickname or None,
        },
    ).first()
    db.commit()
    return int(row[0]) if row else 0


def update_sign_count(db: Session, credential_id: str, new_sign_count: int) -> int:
    stmt = sa.text(
        """
        UPDATE webauthn_credentials
        SET sign_count = :sc,
            updated_at = now()
        WHERE credential_id = :cid
        """
    )
    res = db.execute(stmt, {"sc": int(new_sign_count or 0), "cid": str(credential_id)})
    db.commit()
    return int(getattr(res, "rowcount", 0) or 0)


def list_user_credentials(db: Session, user_id: int) -> list[dict[str, Any]]:
    stmt = sa.text(
        """
        SELECT id, user_id, credential_id, public_key, sign_count, transports, aaguid, created_at, nickname
        FROM webauthn_credentials
        WHERE user_id = :uid
        ORDER BY created_at DESC
        """
    )
    rows = db.execute(stmt, {"uid": int(user_id)}).mappings().all()
    return [dict(r) for r in rows]


def has_credentials(db: Session, user_id: int) -> bool:
    """Check if user has any WebAuthn credentials registered."""
    stmt = sa.text(
        """
        SELECT EXISTS(SELECT 1 FROM webauthn_credentials WHERE user_id = :uid)
        """
    )
    result = db.execute(stmt, {"uid": int(user_id)}).scalar()
    return bool(result)


def get_credential(db: Session, credential_id: str) -> Optional[dict[str, Any]]:
    stmt = sa.text(
        """
        SELECT id, user_id, credential_id, public_key, sign_count, transports, aaguid, created_at, nickname
        FROM webauthn_credentials
        WHERE credential_id = :cid
        LIMIT 1
        """
    )
    row = db.execute(stmt, {"cid": str(credential_id)}).mappings().first()
    return dict(row) if row else None


def enable_2fa(db: Session, user_id: int) -> int:
    """Enable 2FA for a user (used when registering first WebAuthn credential).
    
    Returns number of rows updated (0 or 1).
    """
    stmt = sa.text(
        """
        UPDATE users
        SET two_factor_enabled = :en, updated_at = now()
        WHERE id = :uid
        """
    )
    res = db.execute(stmt, {"en": True, "uid": int(user_id)})
    db.commit()
    return int(getattr(res, "rowcount", 0) or 0)


def delete_credential(db: Session, user_id: int, credential_id: str) -> int:
    """Delete a WebAuthn credential for this user. Returns number of rows deleted."""
    stmt = sa.text(
        """
        DELETE FROM webauthn_credentials
        WHERE user_id = :uid AND credential_id = :cid
        """
    )
    res = db.execute(stmt, {"uid": int(user_id), "cid": str(credential_id)})
    db.commit()
    return int(getattr(res, "rowcount", 0) or 0)


def update_nickname(db: Session, user_id: int, credential_id: str, nickname: Optional[str]) -> int:
    """Update nickname for a credential owned by user. Returns number of rows updated."""
    stmt = sa.text(
        """
        UPDATE webauthn_credentials
        SET nickname = :nick,
            updated_at = now()
        WHERE user_id = :uid AND credential_id = :cid
        """
    )
    res = db.execute(stmt, {"uid": int(user_id), "cid": str(credential_id), "nick": nickname})
    db.commit()
    return int(getattr(res, "rowcount", 0) or 0)
