"""
Setup AUTH_SECRET_KEY in the OS keyring for Resume Tailor.

- Service: "restailor"
- Username: "AUTH_SECRET_KEY"

Usage (from repo root):
  poetry run python scripts/setup_auth_secret.py

Notes:
- On Windows, this stores the secret in Credential Manager.
- On macOS, this stores it in Keychain.
- On Linux, this uses Secret Service (e.g., gnome-keyring) if available.
"""
from __future__ import annotations

import os
import sys
import secrets
import argparse
from getpass import getpass

SERVICE = "restailor"
USERNAME = "AUTH_SECRET_KEY"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Store AUTH secret in OS keyring for Resume Tailor")
    parser.add_argument(
        "--value",
        help="Secret value to store (non-interactive). If omitted, prompts for input.",
        default=None,
    )
    parser.add_argument(
        "--random",
        help="Generate a strong random secret (non-interactive). Ignored if --value is provided.",
        action="store_true",
    )
    parser.add_argument(
        "--force",
        help="Overwrite existing secret without confirmation.",
        action="store_true",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        import keyring  # type: ignore
    except Exception as e:
        print(
            "keyring is required. Install it first (poetry add keyring). Error:",
            e,
            file=sys.stderr,
        )
        return 1

    existing = None
    try:
        existing = keyring.get_password(SERVICE, USERNAME)  # type: ignore[attr-defined]
    except Exception:
        existing = None

    if existing and not args.force:
        print("An AUTH secret already exists in keyring.")
        ans = input("Replace it? [y/N]: ").strip().lower()
        if ans not in {"y", "yes"}:
            print("No changes made.")
            return 0

    pw: str | None = None
    if args.value is not None:
        pw = str(args.value)
    elif args.random:
        pw = secrets.token_urlsafe(32)
        print("Generated a random secret.")
    else:
        print("Enter a new secret (leave blank to auto-generate a strong random key):")
        entered = getpass("Secret: ")
        if not entered:
            # 32 bytes URL-safe token (Base64-ish) ~ 43 chars
            pw = secrets.token_urlsafe(32)
            print("Generated a random secret.")
        else:
            pw = entered

    if len(pw) < 16:
        print("Warning: secret is quite short; consider at least 16+ characters.")

    try:
        keyring.set_password(SERVICE, USERNAME, pw)  # type: ignore[attr-defined]
        print(f"Stored AUTH secret in keyring (service='{SERVICE}', username='{USERNAME}').")
    except Exception as e:
        print("Failed to store secret in keyring:", e, file=sys.stderr)
        return 1

    # Optional: sanity check by importing the app security module which reads from keyring/env
    try:
        import importlib
        sec = importlib.import_module("restailor.security")
        if getattr(sec, "SECRET_KEY", None):
            print("Verified: restailor.security loaded SECRET_KEY successfully.")
    except Exception as e:
        print("Warning: could not verify import of restailor.security:", e, file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
