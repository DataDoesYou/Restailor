from __future__ import annotations

"""WebAuthn (FIDO2) helpers.

This module centralizes configuration, challenge management, and calls to the
`webauthn` library for verifying registration and authentication responses.

We keep state-light: challenges are stored in Redis when available, with a
short TTL; otherwise, we store them in an in-memory dict on app.state.
"""

from typing import Any, Optional
import ast
import os
import secrets
import time
import json

from fastapi import HTTPException

from .app_config import CONFIG

def _lib():
    try:  # local import to avoid hard dependency at import-time
        from webauthn.helpers import bytes_to_base64url as _b2b64
        from webauthn.helpers.base64url_to_bytes import base64url_to_bytes as _b64tob
        from webauthn.helpers.structs import (
            RegistrationCredential as _RegCred,
            AuthenticationCredential as _AuthCred,
            AuthenticatorAttestationResponse as _AttResp,
            AuthenticatorAssertionResponse as _AssResp,
        )
        # In webauthn >=2.x, import verification callables from their modules
        from webauthn.registration.verify_registration_response import (
            verify_registration_response as _verify_reg,
        )
        from webauthn.authentication.verify_authentication_response import (
            verify_authentication_response as _verify_auth,
        )
        return {
            "b2b64": _b2b64,
            "b64tob": _b64tob,
            "RegCred": _RegCred,
            "AuthCred": _AuthCred,
            "AttResp": _AttResp,
            "AssResp": _AssResp,
            "verify_reg": _verify_reg,
            "verify_auth": _verify_auth,
        }
    except Exception:
        raise HTTPException(status_code=500, detail="WebAuthn library not installed or incompatible. Ensure 'webauthn>=2.0.0' is installed.")


def _truthy(v: Optional[str]) -> bool:
    return str(v or "").strip().lower() in {"1", "true", "yes", "on", "y"}


def _e2e_disable_redis() -> bool:
    try:
        return _truthy(os.getenv("E2E_DISABLE_REDIS"))
    except Exception:
        return False


def cfg() -> dict[str, Any]:
    sec = (CONFIG.get("security") or {}) if isinstance(CONFIG.get("security"), dict) else {}
    wa = (sec.get("webauthn") or {}) if isinstance(sec, dict) else {}
    # Defaults tuned for local dev; override in config/app.toml or env
    rp_id = os.getenv("WEBAUTHN_RP_ID") or str(wa.get("rp_id") or "localhost")
    rp_name = os.getenv("WEBAUTHN_RP_NAME") or str(wa.get("rp_name") or CONFIG.get("app", {}).get("name", "Restailor"))
    origins = wa.get("origins") or [
        os.getenv("WEBAUTHN_ORIGIN") or "http://localhost:3000",
    ]
    user_ver = str(wa.get("user_verification") or os.getenv("WEBAUTHN_USER_VERIFICATION") or "preferred")
    attestation = str(wa.get("attestation") or os.getenv("WEBAUTHN_ATTESTATION") or "none")
    timeout_ms = int(wa.get("timeout_ms") or os.getenv("WEBAUTHN_TIMEOUT_MS") or 60000)
    return {
        "rp_id": rp_id,
        "rp_name": rp_name,
        "origins": origins,
        "user_verification": user_ver,
        "attestation": attestation,
        "timeout_ms": timeout_ms,
    }


def _challenge_bytes_default() -> int:
    try:
        return int((((CONFIG.get("security") or {}).get("webauthn") or {}).get("challenge_bytes") or 32))
    except Exception:
        return 32


def generate_challenge(nbytes: int | None = None) -> bytes:
    size = int(nbytes) if nbytes is not None else _challenge_bytes_default()
    return secrets.token_bytes(max(16, size))


def _challenge_ttl_default() -> int:
    try:
        return int((((CONFIG.get("security") or {}).get("webauthn") or {}).get("challenge_ttl_seconds") or 180))
    except Exception:
        return 180


async def store_challenge(app_state: Any, key: str, challenge: bytes, ttl_seconds: int | None = None) -> None:
    r = None if _e2e_disable_redis() else getattr(app_state, "redis", None)
    L = None
    ttl = int(ttl_seconds) if ttl_seconds is not None else _challenge_ttl_default()
    try:
        L = _lib()
        b64 = L["b2b64"](challenge)
    except Exception:
        b64 = None  # will fall back to memory hex
    if r is not None and b64:
        try:
            await r.setex(key, ttl, b64)  # type: ignore[attr-defined]
            return
        except Exception as ex:
            import logging as _log
            _log.getLogger(__name__).debug("webauthn.store_challenge redis setex failed: %s", ex)
    # Fallback: in-memory store
    mem = getattr(app_state, "captcha_mem", None)
    if not isinstance(mem, dict):
        setattr(app_state, "captcha_mem", {})
        mem = app_state.captcha_mem
    inner = mem.setdefault("webauthn", {})
    inner[key] = (b64 or challenge.hex(), time.time() + ttl)


async def pop_challenge(app_state: Any, key: str) -> Optional[bytes]:
    r = None if _e2e_disable_redis() else getattr(app_state, "redis", None)
    if r is not None:
        try:
            v = await r.getdel(key)  # type: ignore[attr-defined]
        except Exception as ex:
            import logging as _log
            _log.getLogger(__name__).debug("webauthn.pop_challenge getdel failed: %s", ex)
        if v:
            try:
                if isinstance(v, (bytes, bytearray)):
                    v = v.decode("utf-8", errors="ignore")
                L = _lib()
                return L["b64tob"](v)
            except Exception as ex:
                import logging as _log
                _log.getLogger(__name__).debug("webauthn.pop_challenge decode b64 failed: %s", ex)
                return None
    # Fallback memory
    mem = getattr(app_state, "captcha_mem", None)
    if isinstance(mem, dict):
        inner = mem.get("webauthn") or {}
        rec = inner.pop(key, None)
        if rec and isinstance(rec, (list, tuple)) and len(rec) == 2:
            raw, exp = rec
            if exp and float(exp) > time.time():
                try:
                    L = _lib()
                    return L["b64tob"](raw)
                except Exception as ex:
                    import logging as _log
                    _log.getLogger(__name__).debug("webauthn.pop_challenge mem b64 decode failed: %s", ex)
                    try:
                        # Old hex fallback
                        return bytes.fromhex(str(raw))
                    except Exception as hex_ex:
                        _log.getLogger(__name__).debug("webauthn.pop_challenge hex decode failed: %s", hex_ex)
                        return None
    return None


def ensure_lib():
    _ = _lib()


def build_registration_options(user_id: int, username: str) -> dict[str, Any]:
    """Return PublicKeyCredentialCreationOptions as dict for the browser.

    We generate the challenge here; caller is responsible for storing it.
    """
    L = _lib()
    c = cfg()
    challenge = generate_challenge()
    user_handle = str(int(user_id)).encode("utf-8")
    # Build algorithm list from config (safe defaults)
    algs = c.get("algs") or ((CONFIG.get("security") or {}).get("webauthn") or {}).get("algs") or [-7, -257]
    valid_algs: list[int] = []
    try:
        for a in (algs or []):
            ai: Optional[int]
            try:
                ai = int(a)
            except (TypeError, ValueError):
                ai = None
            if ai is not None:
                valid_algs.append(ai)
    except Exception:
        valid_algs = [-7, -257]
    if not valid_algs:
        valid_algs = [-7, -257]

    opts = {
        "rp": {"id": c["rp_id"], "name": c["rp_name"]},
        "user": {
            "id": L["b2b64"](user_handle),
            "name": username,
            "displayName": username,
        },
        "challenge": L["b2b64"](challenge),
        "pubKeyCredParams": [{"type": "public-key", "alg": a} for a in valid_algs],
        "timeout": c["timeout_ms"],
        "authenticatorSelection": {
            "residentKey": "preferred",
            "userVerification": c["user_verification"],
            "requireResidentKey": False,
        },
        "attestation": c["attestation"],
    }
    return {"publicKey": opts, "_challenge_bytes": challenge}


def _normalize_browser_credential(kind: str, cred: dict[str, Any]) -> dict[str, Any]:
    """Normalize a browser WebAuthn credential to the library's expected schema.

    - Convert camelCase keys to snake_case (rawId -> raw_id, clientDataJSON -> client_data_json, etc.)
    - Base64url-decode binary fields to bytes
    - Preserve id/type/extension fields if present
    """
    L = _lib()
    b64tob = L["b64tob"]

    def b2b(v: Any) -> Any:
        if isinstance(v, (bytes, bytearray)):
            return bytes(v)
        if isinstance(v, str):
            try:
                return b64tob(v)
            except Exception:
                return v
        return v

    out: dict[str, Any] = {}
    # Top-level
    out["id"] = cred.get("id")
    if "raw_id" in cred:
        out["raw_id"] = b2b(cred.get("raw_id"))
    elif "rawId" in cred:
        out["raw_id"] = b2b(cred.get("rawId"))
    t = cred.get("type")
    if t:
        out["type"] = t
    # Optional top-level passthroughs with name conversion
    if "authenticatorAttachment" in cred:
        out["authenticator_attachment"] = cred.get("authenticatorAttachment")
    if "clientExtensionResults" in cred:
        out["client_extension_results"] = cred.get("clientExtensionResults")
    if "transports" in cred:
        out["transports"] = cred.get("transports")

    # Response mapping (flatten to top-level as expected by python-webauthn 2.x)
    resp = cred.get("response") or {}
    if kind == "registration":
        # attestationObject, clientDataJSON
        if "attestation_object" in resp:
            out["attestation_object"] = b2b(resp.get("attestation_object"))
        if "attestationObject" in resp:
            out["attestation_object"] = b2b(resp.get("attestationObject"))
        if "client_data_json" in resp:
            out["client_data_json"] = b2b(resp.get("client_data_json"))
        if "clientDataJSON" in resp:
            out["client_data_json"] = b2b(resp.get("clientDataJSON"))
        # Some browsers include transports in response
        if "transports" in resp and "transports" not in out:
            out["transports"] = resp.get("transports")
    else:
        # authentication: clientDataJSON, authenticatorData, signature, userHandle
        if "client_data_json" in resp:
            out["client_data_json"] = b2b(resp.get("client_data_json"))
        if "clientDataJSON" in resp:
            out["client_data_json"] = b2b(resp.get("clientDataJSON"))
        if "authenticator_data" in resp:
            out["authenticator_data"] = b2b(resp.get("authenticator_data"))
        if "authenticatorData" in resp:
            out["authenticator_data"] = b2b(resp.get("authenticatorData"))
        if "signature" in resp:
            out["signature"] = b2b(resp.get("signature"))
        if "user_handle" in resp:
            out["user_handle"] = b2b(resp.get("user_handle"))
        if "userHandle" in resp:
            out["user_handle"] = b2b(resp.get("userHandle"))
    return out


def verify_registration(origin: str, expected_challenge: bytes, credential: dict[str, Any]) -> dict[str, Any]:
    """Verify the registration response and return parsed fields for storage.

    Returns dict with keys: credential_id (b64url), public_key (bytes), sign_count (int), aaguid (str|None), transports (list[str]|None)
    """
    L = _lib()
    c = cfg()
    # Origin allowlist check
    allowed = set(map(str, c.get("origins", []) or []))
    if allowed and not any(str(origin or "").startswith(a) for a in allowed):
        raise HTTPException(status_code=400, detail="origin_not_allowed")
    # Normalize browser payload and build RegistrationCredential; support multiple library variants
    RegCred = L["RegCred"]
    AttResp = L["AttResp"]
    try:
        normalized = _normalize_browser_credential("registration", credential)
        # Response object is required by library
        resp = normalized.get("response") or {
            "attestation_object": normalized.get("attestation_object"),
            "client_data_json": normalized.get("client_data_json"),
        }
        att = AttResp(
            attestation_object=resp.get("attestation_object"),
            client_data_json=resp.get("client_data_json"),
        )
        reg_cred = RegCred(
            id=normalized.get("id"),
            raw_id=normalized.get("raw_id"),
            type=normalized.get("type"),
            response=att,
        )  # type: ignore[call-arg]
    except Exception:
        try:
            if hasattr(RegCred, "model_validate"):
                reg_cred = RegCred.model_validate({
                    "id": normalized.get("id"),
                    "raw_id": normalized.get("raw_id"),
                    "type": normalized.get("type"),
                    "response": {
                        "attestation_object": normalized.get("attestation_object"),
                        "client_data_json": normalized.get("client_data_json"),
                    },
                })  # type: ignore[attr-defined]
            elif hasattr(RegCred, "parse_obj"):
                reg_cred = RegCred.parse_obj({
                    "id": normalized.get("id"),
                    "raw_id": normalized.get("raw_id"),
                    "type": normalized.get("type"),
                    "response": {
                        "attestation_object": normalized.get("attestation_object"),
                        "client_data_json": normalized.get("client_data_json"),
                    },
                })  # type: ignore[attr-defined]
            elif hasattr(RegCred, "parse_raw"):
                reg_cred = RegCred.parse_raw(json.dumps({
                    "id": normalized.get("id"),
                    "raw_id": normalized.get("raw_id"),
                    "type": normalized.get("type"),
                    "response": {
                        "attestation_object": normalized.get("attestation_object"),
                        "client_data_json": normalized.get("client_data_json"),
                    },
                }))  # type: ignore[attr-defined]
            else:
                raise
        except Exception:
            raise
    ver = L["verify_reg"](
        credential=reg_cred,  # type: ignore[arg-type]
        expected_challenge=expected_challenge,
        expected_rp_id=c["rp_id"],
        expected_origin=origin,
        require_user_verification=(c["user_verification"] == "required"),
    )
    # Normalize credential_id to base64url string for storage
    cred_id_val = getattr(ver, "credential_id", None)
    if isinstance(cred_id_val, (bytes, bytearray)):
        try:
            cred_id_b64 = L["b2b64"](bytes(cred_id_val))
        except Exception:
            cred_id_b64 = cred_id_val.hex()
    else:
        cred_id_b64 = str(cred_id_val)
    return {
        "credential_id": cred_id_b64,  # base64url str
        "public_key": ver.credential_public_key,  # bytes
        "sign_count": int(ver.sign_count or 0),
        "aaguid": getattr(ver, "aaguid", None) or None,
        "transports": getattr(reg_cred, "transports", None) or None,
    }


def build_authentication_options(allow_credential_ids_b64: list[str]) -> dict[str, Any]:
    L = _lib()
    c = cfg()
    challenge = generate_challenge()
    allow: list[dict[str, Any]] = []
    for cid in allow_credential_ids_b64:
        cid_val: Any = cid
        # If value is bytes (or looks like bytes repr), convert to base64url
        try:
            if isinstance(cid_val, (bytes, bytearray)):
                cid_b64 = L["b2b64"](bytes(cid_val))
            else:
                s = str(cid_val)
                if s.startswith("b'") or s.startswith('b"'):
                    try:
                        b = ast.literal_eval(s)
                        if isinstance(b, (bytes, bytearray)):
                            cid_b64 = L["b2b64"](bytes(b))
                        else:
                            cid_b64 = s
                    except Exception:
                        cid_b64 = s
                else:
                    # If already decodable base64url, keep as-is; else leave string
                    try:
                        _ = L["b64tob"](s)
                        cid_b64 = s
                    except Exception:
                        cid_b64 = s
        except Exception:
            cid_b64 = str(cid_val)
        allow.append({"type": "public-key", "id": cid_b64})
    opts = {
        "challenge": L["b2b64"](challenge),
        "timeout": c["timeout_ms"],
        "rpId": c["rp_id"],
        "allowCredentials": allow,
        "userVerification": c["user_verification"],
    }
    return {"publicKey": opts, "_challenge_bytes": challenge}


def verify_authentication(origin: str, expected_challenge: bytes, credential: dict[str, Any], public_key: bytes, prev_sign_count: int) -> dict[str, Any]:
    L = _lib()
    c = cfg()
    # Origin allowlist check
    allowed = set(map(str, c.get("origins", []) or []))
    if allowed and not any(str(origin or "").startswith(a) for a in allowed):
        raise HTTPException(status_code=400, detail="origin_not_allowed")
    AuthCred = L["AuthCred"]
    AssResp = L["AssResp"]
    try:
        normalized = _normalize_browser_credential("authentication", credential)
        resp = normalized.get("response") or {
            "client_data_json": normalized.get("client_data_json"),
            "authenticator_data": normalized.get("authenticator_data"),
            "signature": normalized.get("signature"),
            "user_handle": normalized.get("user_handle"),
        }
        ass = AssResp(
            client_data_json=resp.get("client_data_json"),
            authenticator_data=resp.get("authenticator_data"),
            signature=resp.get("signature"),
            user_handle=resp.get("user_handle"),
        )
        auth_cred = AuthCred(
            id=normalized.get("id"),
            raw_id=normalized.get("raw_id"),
            type=normalized.get("type"),
            response=ass,
        )  # type: ignore[call-arg]
    except Exception:
        try:
            if hasattr(AuthCred, "model_validate"):
                auth_cred = AuthCred.model_validate({
                    "id": normalized.get("id"),
                    "raw_id": normalized.get("raw_id"),
                    "type": normalized.get("type"),
                    "response": {
                        "client_data_json": normalized.get("client_data_json"),
                        "authenticator_data": normalized.get("authenticator_data"),
                        "signature": normalized.get("signature"),
                        "user_handle": normalized.get("user_handle"),
                    },
                })  # type: ignore[attr-defined]
            elif hasattr(AuthCred, "parse_obj"):
                auth_cred = AuthCred.parse_obj({
                    "id": normalized.get("id"),
                    "raw_id": normalized.get("raw_id"),
                    "type": normalized.get("type"),
                    "response": {
                        "client_data_json": normalized.get("client_data_json"),
                        "authenticator_data": normalized.get("authenticator_data"),
                        "signature": normalized.get("signature"),
                        "user_handle": normalized.get("user_handle"),
                    },
                })  # type: ignore[attr-defined]
            elif hasattr(AuthCred, "parse_raw"):
                auth_cred = AuthCred.parse_raw(json.dumps({
                    "id": normalized.get("id"),
                    "raw_id": normalized.get("raw_id"),
                    "type": normalized.get("type"),
                    "response": {
                        "client_data_json": normalized.get("client_data_json"),
                        "authenticator_data": normalized.get("authenticator_data"),
                        "signature": normalized.get("signature"),
                        "user_handle": normalized.get("user_handle"),
                    },
                }))  # type: ignore[attr-defined]
            else:
                raise
        except Exception:
            raise
    ver = L["verify_auth"](
        credential=auth_cred,  # type: ignore[arg-type]
        expected_challenge=expected_challenge,
        expected_rp_id=c["rp_id"],
        expected_origin=origin,
        credential_public_key=public_key,
        credential_current_sign_count=int(prev_sign_count or 0),
        require_user_verification=(c["user_verification"] == "required"),
    )
    return {
        "new_sign_count": int(ver.new_sign_count or 0),
        "credential_id": ver.credential_id,  # base64url str
    }


__all__ = [
    "cfg",
    "build_registration_options",
    "verify_registration",
    "build_authentication_options",
    "verify_authentication",
    "store_challenge",
    "pop_challenge",
]
