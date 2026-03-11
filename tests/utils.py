from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, Tuple
import uuid

from fastapi.testclient import TestClient
from urllib.parse import urlparse, parse_qs

from restailor.db import SessionLocal
from restailor.models import User, UserBalance, Charge, CreditLedger
from sqlalchemy import func, select, literal
from sqlalchemy.orm import Session
from main import app


DEFAULT_PASSWORD = "Str0ngP@ss!123"


def login_user(client: TestClient, email: str, password: str = DEFAULT_PASSWORD) -> str:
    """Backward-compatible alias used by some tests."""
    return login(client, email, password)


def create_test_user(
    db: Session,
    *,
    email: str,
    password: str = DEFAULT_PASSWORD,
    role: str = "user",
    is_verified: bool = True,
) -> User:
    """Create a DB user with a real password hash (no API call)."""
    from restailor import crud, schemas

    visitor_id = f"test-vid-{uuid.uuid4().hex}"
    user_in = schemas.UserCreate(username=email, password=password, visitorId=visitor_id)
    u = crud.create_user(db, user_in)
    u.role = str(role)
    u.is_verified = bool(is_verified)
    u.is_test = True
    db.add(u)
    db.flush()
    return u


def setup_admin_with_totp(db: Session, email: str = "admin@test.com", password: str = "admin123") -> User:
    """Create an admin user in the DB; TOTP can be enabled via API in tests."""
    return create_test_user(db, email=email, password=password, role="admin", is_verified=True)


def get_stepup_token(client: TestClient, bearer_token: str, admin_user: User) -> str:
    """Enable TOTP for the admin user and return the X-Stepup-Token."""
    # Start TOTP enrollment
    r_s = client.post("/2fa/totp/start", headers={"Authorization": f"Bearer {bearer_token}"})
    assert r_s.status_code == 200, r_s.text
    secret = totp_secret_from_start_payload(r_s.json())

    # Confirm
    import pyotp

    code = pyotp.TOTP(secret, digits=6, interval=30).now()
    r_c = client.post(
        "/2fa/totp/confirm",
        json={"code": code},
        headers={"Authorization": f"Bearer {bearer_token}"},
    )
    assert r_c.status_code == 200, r_c.text

    # Step-up using current TOTP code
    curr = pyotp.TOTP(secret, digits=6, interval=30).now()
    r_st = client.post(
        "/auth/stepup/start",
        json={"totp_code": curr},
        headers={"Authorization": f"Bearer {bearer_token}"},
    )
    assert r_st.status_code == 200, r_st.text
    step = r_st.headers.get("X-Stepup-Token")
    assert step
    return str(step)


def signup_and_mark_test(client: TestClient, email: str, password: str = DEFAULT_PASSWORD) -> dict:
    """Sign up a user via the API, mark them verified and is_test=True, and return the signup payload.

    This helper also bypasses captcha by writing into app.state where supported.
    """
    # Bypass captcha where supported
    try:
        client_id = f"test-client-{uuid.uuid4().hex}"
        app.state.captcha_ok_mem[client_id] = ("ok", 60 + 999999999)
        headers = {"X-Client-Id": client_id}
    except Exception:
        headers = {}
    # Ensure we don't hit the per-browser-fingerprint signup cap during tests.
    visitor_id = f"test-vid-{uuid.uuid4().hex}"
    r = client.post(
        "/signup",
        json={"username": email, "password": password, "visitorId": visitor_id},
        headers=headers,
    )
    if r.status_code != 200:
        raise AssertionError(f"/signup failed: {r.status_code} {r.text}")
    data = r.json() or {}
    if not data.get("ok"):
        raise AssertionError("/signup did not return ok=true")
    # Mark as verified and test user
    with SessionLocal() as s:
        u = s.query(User).filter(User.username == email).first()
        if u is not None:
            u.is_verified = True
            u.is_test = True
            s.commit()
    return data


def login(client: TestClient, email: str, password: str = DEFAULT_PASSWORD) -> str:
    client_id = f"test-client-{email}".lower()
    r = client.post("/token", data={"username": email, "password": password}, headers={"X-Client-Id": client_id})
    if r.status_code != 200:
        raise AssertionError(f"/token failed: {r.status_code} {r.text}")
    tok = (r.json() or {}).get("access_token")
    if not tok:
        raise AssertionError("missing access_token")
    return tok


def upsert_balance(s, user_id: int, cents: int) -> None:
    """Ensure UserBalance exists for user_id, set balance and is_test=True.

    Additionally, mirror the desired net balance into CreditLedger so that the
    live DB-derived balance used by pre-enqueue gates matches `cents`.

    Implementation detail: compute current derived = sum(ledger) - sum(charges in cents)
    and insert a single CreditLedger delta to reach the target `cents`.
    """
    uid = int(user_id)
    # Upsert UserBalance row
    ub = s.get(UserBalance, uid)
    if ub is None:
        ub = UserBalance(user_id=uid, balance_cents=0, is_test=True)
        s.add(ub)
    ub.balance_cents = int(cents)
    ub.is_test = True
    s.commit()

    # Compute current derived balance from ledger minus charges
    try:
        lsum = s.execute(select(func.coalesce(func.sum(CreditLedger.delta_cents), 0)).where(CreditLedger.user_id == uid)).scalar_one() or 0
    except Exception:
        lsum = 0
    try:
        csum = s.execute(
            select(func.coalesce(func.sum(func.round(Charge.price_to_user_usd * literal(100), 0)), 0)).where(Charge.user_id == uid)
        ).scalar_one() or 0
    except Exception:
        csum = 0
    current_net = int(lsum) - int(csum)
    target = int(cents)
    delta_needed = target - current_net
    if delta_needed != 0:
        # Positive => grant; Negative => adjust
        entry = CreditLedger(
            user_id=uid,
            delta_cents=int(delta_needed),
            type=("grant" if delta_needed > 0 else "adjust"),
            note="tests.utils.upsert_balance",
            provider_ref=None,
            is_test=True,
        )
        s.add(entry)
        s.commit()


def add_charge(
    s,
    *,
    user_id: int,
    request_type: str,
    provider: str,
    model: str,
    price_to_user_usd: float | int,
    cost_usd: float | int = 0,
    created_at: Optional[datetime] = None,
    output_models: int = 1,
    input_models: int = 0,
) -> Charge:
    """Insert a Charge row; returns the persistent instance.

    Charges created in tests are flagged as test rows so they are excluded from production analytics
    while still being cleaned up automatically by fixtures.
    """
    ch = Charge(
        user_id=int(user_id),
        job_id=None,
        request_type=request_type,
        provider=provider,
        model=model,
        output_models=output_models,
        input_models=input_models,
        prompt_tokens=10,
        completion_tokens=10,
        cost_usd=cost_usd,
        price_to_user_usd=price_to_user_usd,
        currency="USD",
        pricing_version=1,
        created_at=(created_at or datetime.now(timezone.utc)),
        is_test=True,
    )
    s.add(ch)
    s.commit()
    # refresh to load server defaults
    s.refresh(ch)
    return ch


def totp_secret_from_start_payload(payload: dict) -> str:
    """Extract the TOTP secret from /2fa/totp/start response.

    In non-strict mode, the backend returns a "secret" field directly.
    In strict mode, we must parse it from the otpauth URI (otpauth_uri or uri).
    """
    if not isinstance(payload, dict):
        raise AssertionError("invalid TOTP start payload")
    sec = (payload.get("secret") or "").strip()
    if sec:
        return sec
    uri = (payload.get("otpauth_uri") or payload.get("uri") or "").strip()
    if not uri:
        raise AssertionError("TOTP start payload missing otpauth_uri/uri")
    try:
        q = parse_qs(urlparse(uri).query)
        sec2 = (q.get("secret") or [""])[0].strip()
        if not sec2:
            raise AssertionError("TOTP secret not present in otpauth URI")
        return sec2
    except Exception as ex:
        raise AssertionError(f"failed to parse otpauth URI: {ex}")
