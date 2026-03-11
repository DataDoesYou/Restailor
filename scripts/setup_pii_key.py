"""One-time script to generate and store a PII encryption key in the OS keychain.

Service: restailor-app
Username: pii_encryption_key

Run:
  poetry run python scripts/setup_pii_key.py
"""
from __future__ import annotations

import os
import secrets
import string

try:
    import keyring  # type: ignore
except Exception as e:
    raise SystemExit(f"keyring is required. Install it first (poetry add keyring). Error: {e}")


def generate_key(length: int = 64) -> str:
    """Generate a high-entropy URL-safe key that works with pgp_sym_encrypt.

    64 chars ~ 384 bits of entropy (suitable for a symmetric passphrase).
    """
    alphabet = string.ascii_letters + string.digits + "-_!@#$%^&*()[]{}<>.,:;?"  # avoid quotes and backslashes
    return "".join(secrets.choice(alphabet) for _ in range(length))


def main() -> None:
    # Refuse to overwrite unless explicit
    existing = keyring.get_password("restailor-app", "pii_encryption_key")
    if existing:
        print("An encryption key already exists in keyring for 'pii_encryption_key'.")
        print("If you need to rotate, delete it manually or set OVERWRITE=1.")
        if os.getenv("OVERWRITE") != "1":
            return
    key = generate_key()
    keyring.set_password("restailor-app", "pii_encryption_key", key)
    print("Stored new PII encryption key in keyring (service='restailor-app').")


if __name__ == "__main__":
    main()
