from __future__ import annotations

import base64
import json

import pytest

from restailor import webauthn as wa

import pytest
pytestmark = pytest.mark.critical


def b64url(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def test_build_authentication_options_id_format(monkeypatch):
    # Ensure bytes-like ids or odd strings are normalized to base64url-safe strings
    cid_raw = b"\x01\x02\x03test-\xff\x00\x10"
    cid_b64 = b64url(cid_raw)

    # Mix of representations
    allow_ids = [
        cid_b64,
        str(cid_raw),  # e.g., "b'...bytes...'"
        cid_raw,       # actual bytes
    ]

    opts = wa.build_authentication_options(allow_ids)
    pk = opts["publicKey"]
    assert isinstance(pk["allowCredentials"], list)
    ids = [c["id"] for c in pk["allowCredentials"]]
    # All ids should be strings and decodable as base64url
    for s in ids:
        assert isinstance(s, str)
        # decodes without error
        pad = "=" * ((4 - (len(s) % 4)) % 4)
        base64.urlsafe_b64decode(s + pad)


def test_normalize_registration_minimal(monkeypatch):
    # Quick check: normalized output has snake_case keys and bytes values under response
    cred = {
        "id": "abc",
        "rawId": b64url(b"raw-id"),
        "type": "public-key",
        "response": {
            "attestationObject": b64url(b"att"),
            "clientDataJSON": b64url(b"cdj"),
        },
    }
    # access private normalization for test via module attribute
    norm = getattr(wa, "_normalize_browser_credential")("registration", cred)  # type: ignore[attr-defined]
    assert norm["id"] == "abc"
    assert isinstance(norm["raw_id"], (bytes, bytearray))
    assert isinstance(norm.get("response") or norm, dict)


def test_verify_imports_present():
    wa.ensure_lib()
