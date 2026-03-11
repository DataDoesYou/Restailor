from __future__ import annotations

import os
import secrets
import signal
import subprocess  # nosec B404
import sys
import time
from pathlib import Path

import requests
import pyotp

ROOT = Path(__file__).resolve().parents[1]
# Prefer 8101 to avoid conflicts with any existing dev server on 8000
BACKEND_PORT = int(os.environ.get("BACKEND_PORT", "8101"))
BACKEND_URL = os.environ.get("BACKEND_BASE_URL", f"http://127.0.0.1:{BACKEND_PORT}")


def wait_http(url: str, timeout_s: float = 60.0) -> None:
    t0 = time.time()
    last_err: Exception | None = None
    while time.time() - t0 < timeout_s:
        try:
            r = requests.get(url, timeout=2)
            if r.status_code < 500:
                return
        except requests.RequestException as ex:
            last_err = ex
        time.sleep(0.5)
    raise RuntimeError(f"Service at {url} not ready: {last_err}")


essential_env = {
    "E2E_TEST_MODE": "1",
    # Avoid external deps in tests
    "LOGIN_CAPTCHA_REQUIRED": "0",
    "SIGNUP_CAPTCHA_REQUIRED": "0",
    "STRICT_SECRETS": "0",
    # Prefer in-memory fallbacks
    "DISABLE_REDIS": os.environ.get("DISABLE_REDIS", "1"),
}


def main() -> int:
    env = os.environ.copy()
    env.update(essential_env)
    # Ensure Python can import modules from repo root when cwd=e2e
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")

    # 1) Start API (uvicorn)
    api = subprocess.Popen(  # nosec B603
        [
            sys.executable,
            "-m",
            "uvicorn",
            "main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(BACKEND_PORT),
        ],
        cwd=str(ROOT),
        env=env,
        stdout=None,
        stderr=None,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
    )

    try:
        wait_http(f"{BACKEND_URL}/healthz", timeout_s=90)

        # 2) Scenario: Admin must use 2FA and step-up for sensitive actions
        email = os.environ.get("E2E_TEST_EMAIL") or ("admin-" + secrets.token_hex(4) + "@example.com")
        password = os.environ.get("E2E_TEST_PASSWORD") or "Passw0rd!@#"

        # Signup
        s = requests.post(
            f"{BACKEND_URL}/signup",
            json={"username": email, "password": password, "visitorId": None},
            timeout=20,
        )
        if not s.ok and not (s.status_code == 400 and ("exists" in s.text.lower() or "already" in s.text.lower())):
            raise RuntimeError(f"Signup failed: {s.status_code} {s.text}")

        # Verify email + make admin (test-only endpoints)
        v = requests.post(f"{BACKEND_URL}/__test/verify-user", json={"username": email}, timeout=10)
        v.raise_for_status()
        m = requests.post(f"{BACKEND_URL}/__test/make-admin", json={"username": email}, timeout=10)
        m.raise_for_status()

        # Login -> pending_2fa expected
        r0 = requests.post(
            f"{BACKEND_URL}/token",
            data={"username": email, "password": password},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=10,
        )
        r0.raise_for_status()
        j0 = r0.json()
        if j0.get("scope") != "pending_2fa":
            raise AssertionError(f"Expected pending_2fa on admin login, got: {j0}")
        pending = j0.get("access_token")
        if not pending:
            raise AssertionError("No pending_2fa token from /token")

        # Start TOTP (allowed for pending_2fa)
        r_s = requests.post(
            f"{BACKEND_URL}/2fa/totp/start",
            headers={"Authorization": f"Bearer {pending}"},
            timeout=10,
        )
        r_s.raise_for_status()
        secret = r_s.json().get("secret")
        if not secret:
            raise AssertionError("No secret from /2fa/totp/start")

        # Confirm with current code
        code = pyotp.TOTP(secret, digits=6, interval=30).now()
        r_c = requests.post(
            f"{BACKEND_URL}/2fa/totp/confirm",
            json={"code": code},
            headers={"Authorization": f"Bearer {pending}"},
            timeout=10,
        )
        r_c.raise_for_status()
        if True is not r_c.json().get("ok"):
            raise AssertionError(f"TOTP confirm failed: {r_c.text}")

        # Fresh login -> pending_2fa for step2
        r1 = requests.post(
            f"{BACKEND_URL}/token",
            data={"username": email, "password": password},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=10,
        )
        r1.raise_for_status()
        j1 = r1.json()
        if j1.get("scope") != "pending_2fa":
            raise AssertionError(f"Expected pending_2fa after enabling 2FA, got: {j1}")
        pending2 = j1.get("access_token")
        reauth = r1.headers.get("X-Reauth-Token")
        if not pending2 or not reauth:
            raise AssertionError("Missing pending_2fa or X-Reauth-Token for step2")

        # Step2 with TOTP to obtain bearer
        code2 = pyotp.TOTP(secret, digits=6, interval=30).now()
        r2 = requests.post(
            f"{BACKEND_URL}/auth/step2",
            json={"code": code2, "remember_device": False},
            headers={"Authorization": f"Bearer {pending2}", "X-Reauth-Token": reauth},
            timeout=10,
        )
        r2.raise_for_status()
        bearer = r2.json().get("access_token")
        if not bearer:
            raise AssertionError(f"No bearer token from step2: {r2.text}")

        # Admin action without step-up -> 403 needs_stepup
        a0 = requests.post(
            f"{BACKEND_URL}/admin/credits/sim-purchase",
            json={"by_email": email, "amount_cents": 100},
            headers={"Authorization": f"Bearer {bearer}"},
            timeout=10,
        )
        if a0.status_code != 403 or (a0.json().get("detail") != "needs_stepup"):
            raise AssertionError(f"Expected 403 needs_stepup, got: {a0.status_code} {a0.text}")

        # Start step-up with current TOTP
        code3 = pyotp.TOTP(secret, digits=6, interval=30).now()
        st = requests.post(
            f"{BACKEND_URL}/auth/stepup/start",
            json={"totp_code": code3},
            headers={"Authorization": f"Bearer {bearer}"},
            timeout=10,
        )
        st.raise_for_status()
        stepup = st.headers.get("X-Stepup-Token")
        if not stepup:
            raise AssertionError("No X-Stepup-Token from step-up start")

        # Retry with step-up -> 200 OK
        a1 = requests.post(
            f"{BACKEND_URL}/admin/credits/sim-purchase",
            json={"by_email": email, "amount_cents": 50},
            headers={"Authorization": f"Bearer {bearer}", "X-Stepup-Token": stepup},
            timeout=10,
        )
        a1.raise_for_status()
        j_ok = a1.json()
        if True is not j_ok.get("ok"):
            raise AssertionError(f"Admin action failed after step-up: {a1.text}")

        print("E2E admin 2FA + step-up: PASS")
        return 0
    finally:
        try:
            if os.name == "nt":
                api.send_signal(signal.CTRL_BREAK_EVENT)  # type: ignore[attr-defined]
            else:
                api.terminate()
            api.wait(timeout=10)
        except Exception:
            try:
                api.kill()
            except Exception:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
