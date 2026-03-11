from __future__ import annotations

import json
from typing import Any, Dict
import sqlalchemy as sa
from sqlalchemy import select, func, literal
from sqlalchemy.orm import Session

from restailor.db import get_pii_key, SessionLocal

# We use pgp_sym_encrypt/pgp_sym_decrypt via database round trip to ensure identical
# behavior to existing encrypted columns (pgcrypto). These helpers perform a short,
# single-statement query. Callers can pass an existing Session for batching.

_TEXT = sa.Text


def _ensure_session(session: Session | None) -> Session:
    return session if session is not None else SessionLocal()


def encrypt_json(data: Dict[str, Any], session: Session | None = None) -> bytes:
    """Encrypt a JSON-serializable dict using pgcrypto (pgp_sym_encrypt).

    Returns raw bytes (bytea) suitable for storing in LargeBinary columns.
    """
    local = False
    if session is None:
        session = _ensure_session(None)
        local = True
    try:
        key = get_pii_key()
        payload = json.dumps(data, separators=(",", ":"), ensure_ascii=False)
        stmt = select(func.pgp_sym_encrypt(literal(payload), literal(key, type_=_TEXT)))
        enc: bytes = session.execute(stmt).scalar_one()
        return enc
    finally:
        if local:
            session.close()


def decrypt_json(blob: bytes, session: Session | None = None) -> Dict[str, Any]:
    """Decrypt a pgcrypto-encrypted JSON blob back into a dict.

    Raises json.JSONDecodeError if payload is not valid JSON.
    """
    local = False
    if session is None:
        session = _ensure_session(None)
        local = True
    try:
        key = get_pii_key()
        stmt = select(func.pgp_sym_decrypt(literal(blob), literal(key, type_=_TEXT)))
        payload: str = session.execute(stmt).scalar_one()
        return json.loads(payload) if payload else {}
    finally:
        if local:
            session.close()
