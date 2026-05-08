from __future__ import annotations

import json
import secrets
import time
from dataclasses import dataclass
from typing import Any

import sqlalchemy as sa
from sqlalchemy import bindparam, cast, Text
from sqlalchemy.orm import Session

from restailor.db import get_pii_key
from restailor.models import UserProviderKey


SUPPORTED_PROVIDERS = {
    "openai": "OpenAI",
    "anthropic": "Anthropic",
    "gemini": "Google",
    "google": "Google",
    "xai": "xAI",
}
RUNTIME_SECRET_TTL_SECONDS = 10 * 60
_RUNTIME_SECRET_MEM: dict[str, dict[str, Any]] = {}


@dataclass(frozen=True)
class ResolvedByokKey:
    provider: str
    api_key: str
    source: str


def canonical_provider(provider: str | None) -> str:
    p = str(provider or "").strip().lower()
    if p not in SUPPORTED_PROVIDERS:
        raise ValueError("unsupported_provider")
    return "gemini" if p == "google" else p


def mask_tail(api_key: str) -> str:
    value = str(api_key or "")
    return value[-4:] if len(value) >= 4 else value


def mask_key_preview(api_key: str) -> str:
    value = str(api_key or "").strip()
    if not value:
        return ""
    if len(value) <= 6:
        return f"{value[:1]}...{value[-1:]}"
    return f"{value[:2]}...{value[-2:]}"


def provider_key_metadata(row: UserProviderKey | None, provider: str) -> dict[str, Any]:
    return {
        "provider": provider,
        "configured": row is not None,
        "key_tail": getattr(row, "key_tail", None) if row is not None else None,
        "updated_at": getattr(row, "updated_at", None).isoformat() if getattr(row, "updated_at", None) else None,
        "storage_mode": getattr(row, "storage_mode", None) if row is not None else None,
    }


def decrypt_server_key(db: Session, *, user_id: int, provider: str) -> str | None:
    provider = canonical_provider(provider)
    key = get_pii_key()
    row = db.execute(
        sa.select(
            sa.func.pgp_sym_decrypt(UserProviderKey.key_enc, cast(bindparam("pg_key", value=key), Text)).label("api_key")
        ).where(
            UserProviderKey.user_id == int(user_id),
            UserProviderKey.provider == provider,
        )
    ).first()
    value = getattr(row, "api_key", None) if row is not None else None
    return str(value) if value else None


async def store_runtime_secret(
    redis: Any,
    *,
    user_id: int,
    provider: str,
    api_key: str,
    intended_use: str,
    ttl: int = RUNTIME_SECRET_TTL_SECONDS,
) -> str:
    provider = canonical_provider(provider)
    secret_id = secrets.token_urlsafe(32)
    payload = {
        "user_id": int(user_id),
        "provider": provider,
        "api_key": str(api_key),
        "intended_use": str(intended_use or "model_run"),
        "expires_at": time.time() + int(ttl),
    }
    if redis is not None and hasattr(redis, "set"):
        await redis.set(f"byok:runtime:{secret_id}", json.dumps(payload), ex=int(ttl))  # type: ignore[attr-defined]
    else:
        _RUNTIME_SECRET_MEM[secret_id] = payload
    return secret_id


async def consume_runtime_secret(
    redis: Any,
    *,
    secret_id: str | None,
    user_id: int,
    provider: str,
    intended_use: str | None = None,
    delete: bool = False,
) -> str | None:
    if not secret_id:
        return None
    provider = canonical_provider(provider)
    payload: dict[str, Any] | None = None
    key = f"byok:runtime:{secret_id}"
    if redis is not None and hasattr(redis, "get"):
        raw = await redis.get(key)  # type: ignore[attr-defined]
        if raw:
            payload = json.loads(raw if isinstance(raw, str) else raw.decode("utf-8", errors="ignore"))
            if delete and hasattr(redis, "delete"):
                await redis.delete(key)  # type: ignore[attr-defined]
    else:
        payload = _RUNTIME_SECRET_MEM.get(str(secret_id))
        if delete:
            _RUNTIME_SECRET_MEM.pop(str(secret_id), None)
    if not payload:
        return None
    if float(payload.get("expires_at") or 0) < time.time():
        _RUNTIME_SECRET_MEM.pop(str(secret_id), None)
        return None
    if int(payload.get("user_id") or 0) != int(user_id):
        return None
    if str(payload.get("provider") or "") != provider:
        return None
    if intended_use and str(payload.get("intended_use") or "") != str(intended_use):
        return None
    api_key = str(payload.get("api_key") or "")
    return api_key or None


async def resolve_byok_key(
    db: Session,
    redis: Any,
    *,
    user_id: int,
    provider: str,
    runtime_secret_id: str | None = None,
    intended_use: str | None = None,
) -> ResolvedByokKey:
    provider = canonical_provider(provider)
    local_key = await consume_runtime_secret(
        redis,
        secret_id=runtime_secret_id,
        user_id=int(user_id),
        provider=provider,
        intended_use=intended_use,
        delete=False,
    )
    if local_key:
        return ResolvedByokKey(provider=provider, api_key=local_key, source="runtime_secret")
    server_key = decrypt_server_key(db, user_id=int(user_id), provider=provider)
    if server_key:
        return ResolvedByokKey(provider=provider, api_key=server_key, source="server")
    raise PermissionError("missing_byok_key")
